import json
import logging
import time

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.config import settings
from app.agent_v2.repo import AgentV2Repository
from app.agent_v2.deps import get_llm
from app.agent_v2.tools import make_tools

logger = logging.getLogger("agent_v2.service")

MAX_HISTORY = 20
MAX_TOOL_TURNS = 10
SYSTEM_PROMPT = "You are a helpful AI assistant. Be concise and friendly."


def _make_title(message: str) -> str:
    message = message.strip().replace("\n", " ")
    return message[:50] + "..." if len(message) > 50 else message


class ChatService:

    def __init__(self, db: AsyncSession | None = None):
        self._db = db

    # ── 非流式 ──────────────────────────────────────────────────

    async def create_conversation(self, account_id: int) -> dict:
        repo = AgentV2Repository(self._db)
        conv = await repo.create_conversation(account_id)
        return conv

    async def delete_conversation(self, thread_id: str,
                                  account_id: int) -> None:
        repo = AgentV2Repository(self._db)
        conv = await repo.get_conversation(thread_id)
        if not conv or conv["account_id"] != account_id:
            raise ValueError("conversation not found")
        await repo.delete_conversation(thread_id)

    async def list_conversations(self, account_id: int,
                                 limit: int = 20,
                                 before_id: int | None = None) -> list[dict]:
        repo = AgentV2Repository(self._db)
        return await repo.list_conversations(account_id, limit, before_id)

    async def get_history(self, account_id: int, thread_id: str,
                          limit: int = 20,
                          before_id: int | None = None) -> list[dict]:
        repo = AgentV2Repository(self._db)
        conv = await repo.get_conversation(thread_id)
        if not conv or conv["account_id"] != account_id:
            raise ValueError("conversation not found")
        return await repo.get_messages(thread_id, limit, before_id)

    # ── 流式 chat ───────────────────────────────────────────────

    async def chat_stream(self, account_id: int, username: str,
                          thread_id: str, message: str):
        """ReAct loop: LLM → tool → LLM → ... 全在这个生成器里。"""
        try:
            thread_id = await self._setup_thread(account_id, thread_id)
            await self._save_user_message(account_id, thread_id, message)
            context = await self._prepare_context(account_id, thread_id)
        except ValueError as e:
            yield {"event": "error",
                   "data": json.dumps({"error": str(e)})}
            return

        llm = get_llm()
        tools = make_tools(account_id, username)
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = llm.bind_tools(tools)

        messages = list(context)
        full_text = ""
        start = time.time()
        tool_call_count = 0
        last_usage_chunk = None

        try:
            for turn in range(MAX_TOOL_TURNS):
                last_chunk = None
                async for chunk in llm_with_tools.astream(messages):
                    if chunk.content:
                        full_text += chunk.content
                        yield {"event": "token",
                               "data": json.dumps({"text": chunk.content})}
                    last_chunk = chunk

                if not last_chunk or not last_chunk.tool_calls:
                    last_usage_chunk = last_chunk
                    break

                last_usage_chunk = last_chunk
                for tc in last_chunk.tool_calls:
                    tool_call_count += 1
                    fn = tools_by_name.get(tc["name"])
                    yield {"event": "tool_start",
                           "data": json.dumps({"tool": tc["name"],
                                               "input": tc["args"]})}

                    if fn:
                        try:
                            result = await fn.ainvoke(tc["args"])
                            result_text = str(result)
                        except Exception as e:
                            result_text = f"Error: {e}"
                            logger.exception("tool %s failed", tc["name"])
                    else:
                        result_text = f"Tool '{tc['name']}' does not exist."

                    yield {"event": "tool_end",
                           "data": json.dumps({"tool": tc["name"],
                                               "output": result_text[:300]})}

                    messages.append(AIMessage(content="", tool_calls=[{
                        "name": tc["name"], "args": tc["args"], "id": tc["id"],
                    }]))
                    messages.append(ToolMessage(content=result_text,
                                                tool_call_id=tc["id"]))

                if turn == MAX_TOOL_TURNS - 1:
                    full_text += "\n[已达到最大工具调用次数]"

            duration_ms = int((time.time() - start) * 1000)
            prompt_tokens = None
            completion_tokens = None
            total_tokens = None
            if last_usage_chunk and hasattr(last_usage_chunk, "usage_metadata") and last_usage_chunk.usage_metadata:
                prompt_tokens = last_usage_chunk.usage_metadata.get("input_tokens")
                completion_tokens = last_usage_chunk.usage_metadata.get("output_tokens")
                total_tokens = last_usage_chunk.usage_metadata.get("total_tokens")

            if full_text:
                await self._save_response(
                    account_id, thread_id, full_text,
                    model=settings.llm_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    duration_ms=duration_ms,
                )

            yield {"event": "done",
                   "data": json.dumps({"thread_id": thread_id,
                                       "tool_calls": tool_call_count})}
        except Exception as e:
            logger.exception("chat stream error")
            yield {"event": "error",
                   "data": json.dumps({"error": str(e)})}

    # ── 内部 session 管理 ──────────────────────────────────────

    async def _setup_thread(self, account_id: int,
                            thread_id: str = "") -> str:
        async with AsyncSessionLocal() as session:
            repo = AgentV2Repository(session)
            if thread_id:
                conv = await repo.get_conversation(thread_id)
                if not conv or conv["account_id"] != account_id:
                    raise ValueError("conversation not found")
                return thread_id
            conv = await repo.create_conversation(account_id)
            await session.commit()
            return conv["thread_id"]

    async def _save_user_message(self, account_id: int,
                                 thread_id: str, content: str) -> int:
        async with AsyncSessionLocal() as session:
            repo = AgentV2Repository(session)
            msg_id = await repo.add_message(thread_id, account_id,
                                            "user", content)
            conv = await repo.get_conversation(thread_id)
            if conv and not conv["title"]:
                await repo.update_title(thread_id, _make_title(content))
            await session.commit()
            return msg_id

    async def _prepare_context(self, account_id: int,
                               thread_id: str) -> list:
        async with AsyncSessionLocal() as session:
            repo = AgentV2Repository(session)
            history = await repo.get_messages(thread_id, MAX_HISTORY)
            messages = [SystemMessage(content=SYSTEM_PROMPT)]
            for m in history:
                if m["role"] == "user":
                    messages.append(HumanMessage(content=m["content"]))
                else:
                    messages.append(AIMessage(content=m["content"]))
            return messages

    async def _save_response(self, account_id: int, thread_id: str,
                             content: str, model: str,
                             prompt_tokens: int | None,
                             completion_tokens: int | None,
                             total_tokens: int | None,
                             duration_ms: int) -> None:
        async with AsyncSessionLocal() as session:
            repo = AgentV2Repository(session)
            await repo.add_message(
                thread_id, account_id, "assistant", content,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
            )
            await session.commit()
