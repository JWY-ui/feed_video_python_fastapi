"""模糊搜用户 —— agent_v3 需要的新后端能力。

原有的 `find_by_username` 是精确匹配且查不到就抛异常，所以模型说「关注小明」
在用户名实际是「小明123」时会直接失败。搜索要能返回候选，让模型自己挑。
"""
from __future__ import annotations

from app.database import AsyncSessionLocal
from app.repositories.account_repo import AccountRepository
from app.services.account_service import AccountService


async def _search(query: str, limit: int = 10) -> list[dict]:
    async with AsyncSessionLocal() as session:
        return await AccountService(AccountRepository(session)).search(query, limit)


async def test_matches_part_of_a_username(data):
    await data.account("小明123")
    await data.account("小红")

    results = await _search("小明")

    assert [u["username"] for u in results] == ["小明123"]


async def test_returns_every_candidate_rather_than_raising(data):
    await data.account("小明")
    await data.account("小明123")

    results = await _search("小明")

    assert [u["username"] for u in results] == ["小明", "小明123"]


async def test_an_exact_match_comes_first(data):
    """用户名正好是「小明」时，它应当排在「小明123」前面 —— 模型多半取第一个。"""
    await data.account("小明123")
    await data.account("小明")

    results = await _search("小明")

    assert results[0]["username"] == "小明"


async def test_no_match_is_an_empty_list_not_an_error(data):
    await data.account("小明")

    assert await _search("不存在的人") == []


async def test_wildcards_are_treated_as_literal_text(data):
    """搜 % 不能变成"匹配所有人" —— 那是 LIKE 的语法，不是注入。"""
    await data.account("小明")
    await data.account("小红")

    assert await _search("%") == []


async def test_blank_query_returns_nothing(data):
    await data.account("小明")

    assert await _search("   ") == []
