"""编排：会话生命周期 + 消费图的流 + 翻译成 SSE 事件。

图本身不知道 SSE 的存在（除了工具轨迹那几条 custom 事件）；这里负责把图的几种流
模式折叠成前端能消费的一条事件序列。

每个方法自己开短 session，不把 DB 连接绑在长生命周期的响应上 —— 这是 v2 做对了
的判断，也是刚修完的 SSE 连接池问题的同一个道理。
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.agent_v3.lock import LockTimeout, LockUnavailable, thread_lock
from app.agent_v3.repo import AgentV3Repository
from app.database import AsyncSessionLocal

TITLE_MAX_LEN = 50


def _event(name: str, data: dict) -> dict:
    return {"event": name, "data": data}


def _clip_title(message: str) -> str:
    text = " ".join(message.split())
    if len(text) > TITLE_MAX_LEN:
        return text[:TITLE_MAX_LEN] + "..."
    return text


def _message_to_dto(message) -> dict | None:
    """把 checkpointer 里的消息转成前端好渲染的 DTO。

    工具调用一并带上 —— 否则用户看不到 agent 到底做了什么（v2 正是把它丢了）。
    """
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content, "tool_calls": []}
    if isinstance(message, AIMessage):
        return {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {"tool": call["name"], "args": call["args"]}
                for call in (getattr(message, "tool_calls", None) or [])
            ],
        }
    if isinstance(message, ToolMessage):
        # 带上工具名：只给 role/content 的话，前端回放历史时认不出这坨 JSON 是谁的
        return {
            "role": "tool",
            "tool": getattr(message, "name", None),
            "content": message.content,
            "tool_calls": [],
        }
    return None


class AgentV3Service:

    def __init__(self, graph):
        self._graph = graph
        # 同一个会话上的图运行必须串行 —— 否则两个运行会同时读写同一份 checkpoint，
        # 实测后果是：其中一轮的消息被静默丢掉、checkpointer 报主键冲突、以及写操作
        # 被执行两遍（私信发两条）。锁本身在 Redis 里，见 app/agent_v3/lock.py
        # （跨进程；Redis 不可用就直接拒绝，不退回无锁）。

    # ── 会话管理 ────────────────────────────────────────────────

    async def create_conversation(self, account_id: int) -> dict:
        async with AsyncSessionLocal() as session:
            conv = await AgentV3Repository(session).create_conversation(account_id)
            await session.commit()
            return conv

    async def list_conversations(
        self, account_id: int, limit: int = 20
    ) -> list[dict]:
        async with AsyncSessionLocal() as session:
            return await AgentV3Repository(session).list_conversations(
                account_id, limit
            )

    async def delete_conversation(self, account_id: int, thread_id: str) -> None:
        # 归属检查单独开一个短 session，不把连接挂在整个清理过程上。
        async with AsyncSessionLocal() as session:
            conv = await AgentV3Repository(session).get_conversation(thread_id)
            if not conv or conv["account_id"] != account_id:
                raise ValueError("conversation not found")

        # 清理期间不能让同一会话的图运行继续写 checkpoint。
        async with thread_lock(thread_id):
            # 先删 checkpoint：消息是对话的唯一真相源，用户点了「删除」之后内容
            # 不该还留在库里。业务行随后删；两步不在同一个事务里（checkpointer
            # 有自己的连接池），所以先做不可逆的那一步，避免「业务行没了、历史
            # 还在」这种更难处理的状态。
            await self._graph.checkpointer.adelete_thread(thread_id)
            async with AsyncSessionLocal() as session:
                await AgentV3Repository(session).delete_conversation(thread_id)
                await session.commit()

    async def get_history(self, account_id: int, thread_id: str) -> list[dict]:
        """从 checkpointer 读 transcript —— 它是消息的唯一真相源。"""
        await self._require_owned(account_id, thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = await self._graph.aget_state(config)
        messages = (snapshot.values or {}).get("messages", []) if snapshot else []
        return [dto for dto in (_message_to_dto(m) for m in messages) if dto]

    # ── 对话 ────────────────────────────────────────────────────

    async def chat_stream(
        self,
        account_id: int,
        username: str,
        message: str,
        thread_id: str | None = None,
    ) -> AsyncIterator[dict]:
        try:
            conv = await self._prepare_conversation(account_id, thread_id, message)
        except ValueError as e:
            yield _event("error", {"message": str(e)})
            return

        config = {"configurable": {"thread_id": conv["thread_id"]}}
        state = {
            "messages": [HumanMessage(content=message)],
            "account_id": account_id,
            "username": username,
        }
        try:
            async with thread_lock(conv["thread_id"]):
                # 有待确认的操作时不能再开新一轮。实测那样会**静默销毁**那个待确认的
                # 操作 —— 用户随后点「发送」，写操作一次都不执行，且没有任何报错。
                snapshot = await self._graph.aget_state(config)
                if snapshot.interrupts:
                    yield _event("error", {
                        "message": "还有一条待确认的操作，请先发送或取消它",
                    })
                    return

                async for event in self._run(state, config):
                    yield event
        except (LockUnavailable, LockTimeout) as e:
            yield _event("error", {"message": str(e)})

    async def confirm(
        self, account_id: int, thread_id: str, approved: bool
    ) -> AsyncIterator[dict]:
        try:
            await self._require_owned(account_id, thread_id)
        except ValueError as e:
            yield _event("error", {"message": str(e)})
            return

        config = {"configurable": {"thread_id": thread_id}}
        try:
            async with thread_lock(thread_id):
                # 幂等：没有待确认的操作时，重复的「确认」必须是空操作。
                # 点两下确认卡、或前端重试，第二次 resume 会把 tools 节点再跑一遍，
                # 于是私信发两条 —— 不可撤回。锁 + 这道检查一起才成立：锁保证两次
                # 检查不重叠，检查保证第二次什么都不做。
                snapshot = await self._graph.aget_state(config)
                if not snapshot.interrupts:
                    yield _event("done", {"thread_id": thread_id, "tool_calls": 0})
                    return

                async for event in self._run(
                    Command(resume={"approved": approved}), config
                ):
                    yield event
        except (LockUnavailable, LockTimeout) as e:
            yield _event("error", {"message": str(e)})

    # ── 内部 ────────────────────────────────────────────────────

    async def _prepare_conversation(
        self, account_id: int, thread_id: str | None, message: str
    ) -> dict:
        async with AsyncSessionLocal() as session:
            repo = AgentV3Repository(session)
            if thread_id:
                conv = await repo.get_conversation(thread_id)
                if not conv or conv["account_id"] != account_id:
                    raise ValueError("conversation not found")
                return conv

            conv = await repo.create_conversation(account_id)
            await repo.update_title(conv["thread_id"], _clip_title(message))
            await session.commit()
            return conv

    async def _require_owned(self, account_id: int, thread_id: str) -> None:
        async with AsyncSessionLocal() as session:
            conv = await AgentV3Repository(session).get_conversation(thread_id)
        if not conv or conv["account_id"] != account_id:
            raise ValueError("conversation not found")

    @staticmethod
    def _interrupt_event(interrupts) -> dict:
        calls: list[dict] = []
        for item in interrupts or ():
            value = getattr(item, "value", None) or {}
            calls.extend(value.get("calls", []))
        return _event("confirm_required", {"calls": calls})

    async def _run(self, graph_input: Any, config: dict) -> AsyncIterator[dict]:
        """把图的三种流模式折叠成一条事件序列。"""
        tool_calls = 0
        try:
            async for mode, chunk in self._graph.astream(
                graph_input, config, stream_mode=["messages", "updates", "custom"]
            ):
                if mode == "custom":
                    # 工具轨迹：图在执行工具时自己推的
                    yield chunk

                elif mode == "messages":
                    message, _meta = chunk
                    text = getattr(message, "content", "") or ""
                    # 只要模型说的话。工具结果是喂模型的，不该混进给用户看的内容流。
                    if isinstance(message, AIMessage) and text:
                        yield _event("token", {"text": text})

                else:  # updates
                    if "__interrupt__" in chunk:
                        yield self._interrupt_event(chunk["__interrupt__"])
                    for node, update in chunk.items():
                        if node == "__interrupt__":
                            continue
                        tool_calls += len((update or {}).get("usage") or [])

        except Exception as e:
            yield _event("error", {"message": str(e)})
            return

        yield _event(
            "done",
            {
                "thread_id": config["configurable"]["thread_id"],
                "tool_calls": tool_calls,
            },
        )
