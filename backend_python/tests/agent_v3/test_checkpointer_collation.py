"""checkpoint 表的排序规则必须与库 SQL 里 utf8mb4 的默认排序规则一致。

不这么做的话，第一次真实对话就会失败：库的 SQL 用
`json_table(... columns (channel VARCHAR(150) CHARACTER SET utf8mb4 PATH '$'))`
派生出一个 channel 列，**没有写 COLLATE**，所以它取的是字符集的默认排序规则
（MySQL 8 上是 utf8mb4_0900_ai_ci）。而本项目的库是 utf8mb4_unicode_ci，
checkpoint_writes.channel 就是 unicode_ci。两个都是 IMPLICIT（列级），
比较直接报 "Illegal mix of collations"。

这几张表只归 checkpointer 使用、不与业务表 JOIN，所以按字符集默认值对齐是安全的；
反过来去改整个库的默认排序规则才危险（老表是 unicode_ci，新表变 0900，业务表之间
的 JOIN 会步上同样的后尘）。
"""
from __future__ import annotations

import asyncmy
import pytest

from app.agent_v3.checkpointer import (
    CHECKPOINT_TABLES,
    ensure_checkpoint_collation,
    utf8mb4_default_collation,
)
from app.config import settings


async def _admin():
    return await asyncmy.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        autocommit=True,
    )


async def _collations() -> dict[str, str]:
    conn = await _admin()
    try:
        async with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(CHECKPOINT_TABLES))
            await cur.execute(
                "SELECT TABLE_NAME, TABLE_COLLATION FROM information_schema.TABLES "
                f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})",
                (settings.mysql_database, *CHECKPOINT_TABLES),
            )
            return {row[0]: row[1] for row in await cur.fetchall()}
    finally:
        conn.close()


async def _force_collation(collation: str) -> None:
    """把表改成"错的"排序规则，好让测试真的在验修复而不是在验现状。"""
    conn = await _admin()
    try:
        async with conn.cursor() as cur:
            for table in CHECKPOINT_TABLES:
                await cur.execute(
                    f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 "
                    f"COLLATE {collation}"
                )
    finally:
        conn.close()


async def test_aligns_every_checkpoint_table(checkpointer):
    await _force_collation("utf8mb4_general_ci")

    changed = await ensure_checkpoint_collation()

    assert set(changed) == set(CHECKPOINT_TABLES), "每一张都要被修正"
    expected = await utf8mb4_default_collation()
    assert set((await _collations()).values()) == {expected}


async def test_leaves_already_aligned_tables_alone(checkpointer):
    """幂等：启动时每次都会调，不能每次都去重建表。"""
    await ensure_checkpoint_collation()

    assert await ensure_checkpoint_collation() == []


async def test_survives_tables_that_do_not_exist_yet(checkpointer):
    """setup() 之前的调用不该炸 —— 那时表还不存在。用不存在的库名来模拟。"""
    changed = await ensure_checkpoint_collation(database="feedsystem_no_such_db")

    assert changed == []
