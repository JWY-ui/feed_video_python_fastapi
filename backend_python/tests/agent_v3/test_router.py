"""HTTP 层：端点形状、认证、SSE 帧格式，以及「没配 key 就 503」。

测试用一个只挂 agent 路由的最小 app，并覆盖认证依赖 —— 不拉起整个应用，
所以跑得快，也不会碰开发库。
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import delete

from app.agent_v3.deps import get_service
from app.agent_v3.graph import build_graph
from app.agent_v3.router import _stream, router, stream_router
from app.agent_v3.service import AgentV3Service
from app.database import AsyncSessionLocal
from app.middleware.jwt_auth import get_current_user, get_current_user_stateless
from app.models.agent_v3 import AgentV3Conversation
from stubs import EXECUTED, StubChatModel, wants

# 本文件的测试都要 Redis：会话锁在 Redis 里（app/agent_v3/lock.py），限流也是。
pytestmark = pytest.mark.usefixtures("redis_client", "isolate_chat_rate_limit")


ACCOUNT = 900004
USERNAME = "我"


@pytest.fixture
async def clean_conversations():
    async def wipe():
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AgentV3Conversation).where(
                    AgentV3Conversation.account_id == ACCOUNT
                )
            )
            await session.commit()

    await wipe()
    yield
    await wipe()


def _service(script: list[AIMessage]) -> AgentV3Service:
    graph = build_graph(llm=StubChatModel(script), checkpointer=InMemorySaver())
    return AgentV3Service(graph)


def _app(service: AgentV3Service | None) -> FastAPI:
    app = FastAPI()
    # 与 app/main.py 的挂法一致：两个路由器共用 /agent 前缀，各自的依赖不同。
    app.include_router(router, prefix="/agent")
    app.include_router(stream_router, prefix="/agent")
    app.dependency_overrides[get_current_user] = lambda: {
        "account_id": ACCOUNT, "username": USERNAME,
    }
    app.dependency_overrides[get_current_user_stateless] = lambda: {
        "account_id": ACCOUNT, "username": USERNAME,
    }
    if service is not None:
        app.dependency_overrides[get_service] = lambda: service
    return app


async def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _frames(text: str) -> list[dict]:
    """把 SSE 响应体解析成事件 dict 列表。"""
    return [
        json.loads(line[len("data: "):])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


async def test_create_then_list_conversations(stub_tools, clean_conversations):
    app = _app(_service([AIMessage(content="好的")]))
    async with await _client(app) as client:
        created = (await client.post("/agent/conversations")).json()

        listed = (await client.post("/agent/conversations/list")).json()

    assert [c["thread_id"] for c in listed] == [created["thread_id"]]


async def test_chat_streams_sse_frames(stub_tools, clean_conversations):
    app = _app(_service([wants("t_read"), AIMessage(content="找到啦")]))
    async with await _client(app) as client:
        response = await client.post("/agent/chat", json={"message": "帮我看看"})

    assert response.headers["content-type"].startswith("text/event-stream")
    events = _frames(response.text)
    names = [e["event"] for e in events]
    assert "tool_start" in names
    assert "tool_end" in names
    assert names[-1] == "done"
    assert any(e["event"] == "token" and e["data"]["text"] == "找到啦"
               for e in events)


async def test_chat_can_resume_an_existing_thread(stub_tools, clean_conversations):
    app = _app(_service([AIMessage(content="好的"), AIMessage(content="又说一句")]))
    async with await _client(app) as client:
        created = (await client.post("/agent/conversations")).json()
        thread = created["thread_id"]

        first = await client.post(
            "/agent/chat", json={"message": "第一句", "thread_id": thread}
        )
        second = await client.post(
            "/agent/chat", json={"message": "接着说", "thread_id": thread}
        )

    assert "好的" in first.text
    assert "又说一句" in second.text, "第二轮该在新调用里接着走同一个 thread"


async def test_history_returns_the_transcript(stub_tools, clean_conversations):
    app = _app(_service([wants("t_read"), AIMessage(content="找到啦")]))
    async with await _client(app) as client:
        created = (await client.post("/agent/conversations")).json()
        await client.post("/agent/chat", json={
            "message": "帮我看看", "thread_id": created["thread_id"],
        })

        history = (await client.post(
            "/agent/conversations/history",
            json={"thread_id": created["thread_id"]},
        )).json()

    assert history[0] == {"role": "user", "content": "帮我看看", "tool_calls": []}
    assert any(m["role"] == "assistant" and m["content"] == "找到啦"
               for m in history)

    # 工具结果要带上工具名 —— 否则前端回放历史时只看到一坨 JSON，认不出是哪个工具的
    tool_rows = [m for m in history if m["role"] == "tool"]
    assert tool_rows, "历史里应该有工具结果"
    assert all(m["tool"] == "t_read" for m in tool_rows), (
        f"工具结果没带工具名，前端认不出是哪条：{tool_rows}"
    )


async def test_confirm_endpoint_resumes_the_graph(stub_tools, clean_conversations):
    app = _app(_service([wants("t_write"), AIMessage(content="好了")]))
    async with await _client(app) as client:
        created = (await client.post("/agent/conversations")).json()
        thread = created["thread_id"]
        paused = await client.post("/agent/chat", json={
            "message": "发条消息", "thread_id": thread,
        })
        assert EXECUTED == []

        resumed = await client.post("/agent/confirm", json={
            "thread_id": thread, "approved": True,
        })

    assert [e["event"] for e in _frames(paused.text) if
            e["event"] == "confirm_required"]
    assert EXECUTED == [("write", 1)]
    tool_end = [e for e in _frames(resumed.text) if e["event"] == "tool_end"]
    assert tool_end[0]["data"]["ui"] == [{"action": "navigate", "to": "/messages/42"}]


async def test_deleting_someone_elses_conversation_is_404(stub_tools, clean_conversations):
    app = _app(_service([AIMessage(content="好的")]))
    async with await _client(app) as client:
        created = (await client.post("/agent/conversations")).json()

        response = await client.post(
            "/agent/conversations/delete",
            json={"thread_id": "nonexistent-thread"},
        )

    assert response.status_code == 404
    assert created["thread_id"]


class _FakeRequest:
    """只实现 _stream 用到的那一个方法。disconnect_after=None 表示一直连着。"""

    def __init__(self, disconnect_after: int | None = None):
        self._disconnect_after = disconnect_after
        self._calls = 0

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._disconnect_after is not None and self._calls > self._disconnect_after


def _endless_events(closed: asyncio.Event):
    """一个永不结束、被关闭时置位的事件流 —— 代替 service.chat_stream。"""

    async def events():
        try:
            while True:
                yield {"event": "token", "data": {"text": "x"}}
                await asyncio.sleep(0)
        finally:
            closed.set()

    return events()


async def test_a_client_disconnect_closes_the_upstream_generator():
    """客户端断开时上游生成器必须被显式关闭 —— 会话锁就挂在它身上。

    只 break 不关，回收就交给 GC 的异步生成器终结器，时机不确定；锁没释放的
    那个会话要到 TTL 到期才打得开。
    """
    closed = asyncio.Event()
    stream = _stream(_FakeRequest(disconnect_after=1), _endless_events(closed))

    assert (await anext(stream)).startswith("data: ")
    with pytest.raises(StopAsyncIteration):
        await anext(stream)

    assert closed.is_set(), "断开时没有关闭上游生成器"


async def test_closing_the_response_closes_the_upstream_generator():
    """ASGI 服务器取消响应任务走的是 aclose，同样必须把上游关掉。"""
    closed = asyncio.Event()
    stream = _stream(_FakeRequest(), _endless_events(closed))

    await anext(stream)
    await stream.aclose()

    assert closed.is_set(), "aclose 没有传导到上游生成器"


async def test_returns_503_when_no_api_key_is_configured():
    """agent 没有降级模式：不配 key 就明确不可用，而不是静默出错。"""
    app = _app(service=None)
    async with await _client(app) as client:
        response = await client.post("/agent/chat", json={"message": "你好"})

    assert response.status_code == 503


async def test_chat_returns_503_when_the_lock_backend_is_down(
    stub_tools, clean_conversations, redis_client, monkeypatch
):
    """Redis 挂掉 → 503，而不是 200 里塞一条 error 事件。

    与上面那条对称：这是依赖层面的不可用，应该在 HTTP 状态码上就看得见，
    而不是要人去读 SSE 正文。会话锁是 agent 的硬依赖（见 app/agent_v3/lock.py）。
    """
    monkeypatch.setattr(redis_client, "_available", False)
    app = _app(_service([AIMessage(content="好的")]))

    async with await _client(app) as client:
        response = await client.post("/agent/chat", json={"message": "你好"})

    assert response.status_code == 503


async def test_the_conversation_endpoints_keep_working_without_redis(
    stub_tools, clean_conversations, redis_client, monkeypatch
):
    """锁不可用只该影响需要串行化的那两个端点。

    侧栏列表 / 历史 / 删除是纯 DB 查询，不碰会话锁 —— 用户至少还能看和清理
    自己的会话，而不是整个 /agent/* 一起黑掉。
    """
    monkeypatch.setattr(redis_client, "_available", False)
    app = _app(_service([AIMessage(content="好的")]))

    async with await _client(app) as client:
        response = await client.post("/agent/conversations")

    assert response.status_code == 200


async def test_chat_is_rate_limited(stub_tools, clean_conversations, monkeypatch):
    """/chat 是全站最贵的端点（每次调用都烧 token），必须限流。

    其余路由在 main.py 里通过 include_router 挂限流；agent 有一半端点是廉价的
    DB 查询，不能整路由一刀切，所以限流挂在 stream_router 上。

    额度在测试体内调小：conftest 的 _isolate_rate_limits 已经把前缀和额度设好，
    这里再覆盖，顺序上必定生效。
    """
    from app.agent_v3.deps import chat_rate_limiter

    monkeypatch.setattr(chat_rate_limiter, "max_requests", 2)
    app = _app(_service([AIMessage(content="好的")] * 10))

    async with await _client(app) as client:
        codes = [
            (await client.post("/agent/chat", json={"message": "你好"})).status_code
            for _ in range(5)
        ]

    assert 429 in codes, f"限流没生效：{codes}"
    assert codes[0] == 200, "第一条不该被拦"


async def test_the_conversation_endpoints_are_not_rate_limited(
    stub_tools, clean_conversations, monkeypatch
):
    """廉价端点不该跟着一起被限 —— 侧栏刷新本来就很频繁。

    这里同样把额度调到 2：如果限流被误挂到廉价路由器上，这条会立刻发现。
    """
    from app.agent_v3.deps import chat_rate_limiter

    monkeypatch.setattr(chat_rate_limiter, "max_requests", 2)
    app = _app(_service([AIMessage(content="好的")]))

    async with await _client(app) as client:
        codes = [
            (await client.post("/agent/conversations")).status_code
            for _ in range(5)
        ]

    assert codes == [200] * 5
