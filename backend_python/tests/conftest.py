"""pytest 全局配置。

两件事：
1. `app` 包的导入路径由 pytest.ini 的 `pythonpath = .` 提供（rootdir = backend_python/）。
2. **测试走独立的 `feedsystem_test` 库**，绝不碰开发库 `feedsystem`。为此必须在
   任何 `app.*` 被导入之前改掉环境变量 —— 环境变量优先于 `.env` 文件，
   所以下方赋值会先于 config 生效。
"""
from __future__ import annotations

import asyncio
import os

# 必须在 import app.* 之前（见模块 docstring）
os.environ["MYSQL_DATABASE"] = "feedsystem_test"

import pytest  # noqa: E402


async def _create_database_and_tables() -> None:
    """等价于 app.main 的 lifespan 前两步：建库、建表。"""
    import asyncmy

    from app.config import settings

    conn = await asyncmy.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()

    from app.database import Base, engine
    import app.models  # noqa: F401  触发模型注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """整个测试会话只建一次库和表。

    用独立的 `asyncio.run`：它自带事件循环并在结束时关闭，与每个测试自己的循环解耦，
    避免和 pytest-asyncio 的 loop 作用域纠缠。
    """
    asyncio.run(_create_database_and_tables())


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    """每个测试结束后释放连接池。

    pytest-asyncio 默认每个测试开一个新事件循环，而 SQLAlchemy 的连接池挂在模块级的
    engine 上。若不释放，下一个测试会复用到绑定在已关闭循环上的连接，报出
    `'NoneType' object has no attribute 'send'` 这类错。在这里 dispose 是在**当前**
    循环上关闭连接，因此安全。
    """
    yield
    from app.database import engine

    await engine.dispose()
