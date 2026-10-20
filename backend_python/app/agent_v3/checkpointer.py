"""把 checkpoint 表对齐到 utf8mb4 的默认排序规则。

**为什么需要这个。** `langgraph-checkpoint-mysql` 的 SQL 里有一段：

    json_table(json_keys(checkpoint, '$.channel_versions'), '$[*]'
               columns (channel VARCHAR(150) CHARACTER SET utf8mb4 PATH '$'))

这个派生列只声明了字符集、**没有声明 COLLATE**，于是它取的是 *字符集的* 默认排序
规则（MySQL 8 上是 `utf8mb4_0900_ai_ci`）。而本项目的库是 `utf8mb4_unicode_ci`
（建库时显式指定），`checkpoint_writes.channel` 就是 unicode_ci。两边都是 IMPLICIT
的列级排序规则，MySQL 一比就报 `Illegal mix of collations` —— 第一次真实对话会直接
挂在写 checkpoint 上，而且是那种单测看不出来（内存 checkpointer 不碰这条 SQL）、
一上线就炸的问题。

**为什么这样修。** 让这几张表跟库 SQL 里那个派生列取同一个排序规则即可。它们只归
checkpointer 使用、不与任何业务表 JOIN，所以对齐是安全的。

**为什么不改整个库的默认排序规则。** 那会让新表变 0900、老表还是 unicode_ci，
业务表之间的 JOIN 会步上完全一样的后尘 —— 只是把 bug 挪个地方。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncmy

from app.config import settings

CHECKPOINT_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
)


async def _connect():
    """不指定默认库 —— 目标库不存在时也能连上，交给查询自然返回空。"""
    return await asyncmy.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        autocommit=True,
    )


async def utf8mb4_default_collation() -> str:
    conn = await _connect()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COLLATION_NAME FROM information_schema.COLLATIONS "
                "WHERE CHARACTER_SET_NAME = 'utf8mb4' AND IS_DEFAULT = 'Yes'"
            )
            row = await cur.fetchone()
            return row[0]
    finally:
        conn.close()


async def ensure_checkpoint_collation(database: str | None = None) -> list[str]:
    """对齐 checkpoint 表，返回**实际被改动**的表名。

    幂等：已经一致的表会跳过（CONVERT TO 会重建表，每次启动都做就太贵了）。
    """
    schema = database or settings.mysql_database
    target = await utf8mb4_default_collation()

    conn = await _connect()
    try:
        async with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(CHECKPOINT_TABLES))
            await cur.execute(
                "SELECT TABLE_NAME, TABLE_COLLATION FROM information_schema.TABLES "
                f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})",
                (schema, *CHECKPOINT_TABLES),
            )
            stale = [name for name, collation in await cur.fetchall()
                     if collation != target]

            for table in stale:
                # 库名限定：这个连接没有默认库（见 _connect）
                await cur.execute(
                    f"ALTER TABLE `{schema}`.`{table}` "
                    f"CONVERT TO CHARACTER SET utf8mb4 COLLATE {target}"
                )
            return stale
    finally:
        conn.close()


# The saver's own `from_conn_string()` opens ONE connection and never reconnects:
# if MySQL drops it (wait_timeout, container restart, network blip), every
# checkpointer call fails with InterfaceError: (0, 'Not connected') until the
# process is restarted. A pool hands out a fresh connection when the old one is
# dead, and `pool_recycle` retires connections before the server times them out.
CHECKPOINTER_POOL_SIZE = 10
CHECKPOINTER_POOL_RECYCLE_SECONDS = 1800


@asynccontextmanager
async def checkpointer_saver(conn_string: str) -> AsyncIterator:
    """Create an AsyncMySaver backed by an asyncmy connection pool.

    Use this instead of `AsyncMySaver.from_conn_string(...)`.
    """
    from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver

    params = {
        key: value
        for key, value in AsyncMySaver.parse_conn_string(conn_string).items()
        if value is not None
    }
    pool = await asyncmy.create_pool(
        **params,
        autocommit=True,
        minsize=1,
        maxsize=CHECKPOINTER_POOL_SIZE,
        pool_recycle=CHECKPOINTER_POOL_RECYCLE_SECONDS,
    )
    try:
        yield AsyncMySaver(conn=pool)
    finally:
        pool.close()
        await pool.wait_closed()
