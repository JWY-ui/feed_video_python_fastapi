"""pytest 全局配置。

两件事：
1. `app` 包的导入路径由 pytest.ini 的 `pythonpath = .` 提供（rootdir = backend_python/）。
2. **测试走独立的库**，绝不碰开发库。为此必须在任何 `app.*` 被导入之前改掉环境
   变量 —— 环境变量优先于 `.env` 文件，所以下方赋值会先于 config 生效。

MySQL 和 Redis 都要隔离，理由一样但 Redis 那边更隐蔽：feed 的时间线 ZSET、热榜、
限流计数、agent 的会话锁全都住在 Redis 里，而它们**不带库名**，测试和开发会写到
同一批键上。踩过的实况：开发库的残留视频 id 留在 timeline ZSET 里，测试的热路径
拿到这个悬空 id、查不到行，首页就整页空白 —— 看起来像业务 bug，其实是测试读到了
别人的键。
"""
from __future__ import annotations

import asyncio
import os

# 必须在 import app.* 之前（见模块 docstring）
os.environ["MYSQL_DATABASE"] = "feedsystem_test"
os.environ["REDIS_DB"] = "15"  # 测试专用，与开发用的 0 分开

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


@pytest.fixture
async def data():
    """造测试数据的工具，前后各清一次库。放在这里，各层测试都能用。"""
    from factories import Maker, wipe

    await wipe()
    yield Maker()
    await wipe()


@pytest.fixture
async def redis_client():
    """真连 Redis —— 测 Redis 路径的测试才用它。

    **故意不是 autouse**：一旦连上，`redis_client.available` 就是 True，
    FeedService 会从 MySQL 冷路径切到 Redis 热路径、限流会生效 —— 那些测试的语义
    就变了。要求它 = 明确声明「这条测试测的是 Redis 路径」。

    每个测试接一次（而不是 session 级）：pytest-asyncio 给每个测试开新的事件循环，
    而 redis 的连接池绑在创建它的那个循环上，跨测试复用会报 attached to a
    different loop —— 与下面 _dispose_engine_between_tests 同一个原因。
    """
    from app.utils.redis_client import redis_client as client

    await client.connect()
    assert client.available, (
        f"Redis 不可用（db={os.environ.get('REDIS_DB')}）—— 这条测试测的就是 Redis 路径"
    )
    yield client
    await client.close()


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
