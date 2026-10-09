"""HTTP 层：端点形状、认证、SSE 帧格式，以及「没配 key 就 503」。

测试用一个只挂 agent 路由的最小 app，并覆盖认证依赖 —— 不拉起整个应用，
所以跑得快，也不会碰开发库。
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import delete

from app.agent_v3.deps import get_service
from app.agent_v3.graph import build_graph
from app.agent_v3.router import router
from app.agent_v3.service import AgentV3Service
from app.database import AsyncSessionLocal
from app.middleware.jwt_auth import get_current_user, get_current_user_stateless
from app.models.agent_v3 import AgentV3Conversation
from stubs import EXECUTED, StubChatModel, wants

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
    app.include_router(router, prefix="/agent")
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


async def test_returns_503_when_no_api_key_is_configured():
    """agent 没有降级模式：不配 key 就明确不可用，而不是静默出错。"""
    app = _app(service=None)
    async with await _client(app) as client:
        response = await client.post("/agent/chat", json={"message": "你好"})

    assert response.status_code == 503
