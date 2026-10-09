"""会话表的 CRUD。

消息不在这张表里 —— 它们由 LangGraph checkpointer 持有，这张薄表只管
「谁的会话、叫什么名字」，以及归属校验。

隔离方式：全程不 commit，fixture 结束时 rollback，所以测试不会在库里留痕。
"""
from __future__ import annotations

import pytest

from app.agent_v3.repo import AgentV3Repository
from app.database import AsyncSessionLocal

ACCOUNT = 900001


@pytest.fixture
async def repo():
    async with AsyncSessionLocal() as session:
        yield AgentV3Repository(session)
        await session.rollback()


async def test_create_assigns_a_thread_id_and_remembers_the_owner(repo):
    conv = await repo.create_conversation(ACCOUNT)

    assert conv["thread_id"]
    assert conv["account_id"] == ACCOUNT
    assert conv["title"] == ""


async def test_get_returns_none_for_an_unknown_thread(repo):
    assert await repo.get_conversation("does-not-exist") is None


async def test_get_round_trips(repo):
    created = await repo.create_conversation(ACCOUNT)

    fetched = await repo.get_conversation(created["thread_id"])

    assert fetched["thread_id"] == created["thread_id"]


async def test_list_returns_only_this_accounts_conversations(repo):
    mine = await repo.create_conversation(ACCOUNT)
    await repo.create_conversation(ACCOUNT + 1)

    listed = await repo.list_conversations(ACCOUNT)

    assert [c["thread_id"] for c in listed] == [mine["thread_id"]]


async def test_list_is_newest_first(repo):
    first = await repo.create_conversation(ACCOUNT)
    second = await repo.create_conversation(ACCOUNT)

    listed = await repo.list_conversations(ACCOUNT)

    assert [c["thread_id"] for c in listed] == [second["thread_id"], first["thread_id"]]


async def test_update_title(repo):
    conv = await repo.create_conversation(ACCOUNT)

    await repo.update_title(conv["thread_id"], "找做菜的视频")

    assert (await repo.get_conversation(conv["thread_id"]))["title"] == "找做菜的视频"


async def test_delete_removes_the_conversation(repo):
    conv = await repo.create_conversation(ACCOUNT)

    await repo.delete_conversation(conv["thread_id"])

    assert await repo.get_conversation(conv["thread_id"]) is None


async def test_thread_ids_do_not_collide(repo):
    ids = {(await repo.create_conversation(ACCOUNT))["thread_id"] for _ in range(5)}

    assert len(ids) == 5
