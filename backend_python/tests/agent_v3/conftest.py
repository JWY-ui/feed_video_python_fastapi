import pytest

from stubs import install_synthetic_tools, remove_synthetic_tools


@pytest.fixture
def stub_tools():
    """注册合成工具，用完撤销，避免污染其它测试。"""
    install_synthetic_tools()
    yield
    remove_synthetic_tools()


@pytest.fixture
async def isolate_chat_rate_limit(redis_client, monkeypatch):
    """把 /chat 的限流器挪到测试专用键前缀、抬到高额度，用完清掉。

    限流键是 `feedsystem:ratelimit:<prefix>:<ip>`，窗口 60 秒，而测试全都从同一个
    IP 发请求。沿用默认前缀的话计数会跨测试甚至跨**测试轮次**累积，跑到第 11 次
    /chat 突然吃 429，失败点取决于跑了多少次、什么顺序 —— 最难查的一类不稳定。
    要真验限流的那两条在测试体内再把额度调小（那一定发生在这个 fixture 之后）。

    只有真的会打到 /chat 的测试需要它；直接调 `service.chat_stream()` 的那些
    （test_concurrency / test_service_stream）不经过限流中间件。

    注意它会拉起 `redis_client` —— 所以别把它挂到只读 feed 工具的测试上，
    见 tests/conftest.py 里 redis_client 的说明。
    """
    from app.agent_v3.deps import chat_rate_limiter

    monkeypatch.setattr(chat_rate_limiter, "prefix", "agent_chat_test")
    monkeypatch.setattr(chat_rate_limiter, "max_requests", 10_000)
    yield

    stale = await redis_client._redis.keys("feedsystem:ratelimit:agent_chat_test:*")
    if stale:
        await redis_client.delete(*stale)


# 需要 Redis 的测试文件在模块顶部声明（`redis_client` 定义在 tests/conftest.py）：
#     pytestmark = pytest.mark.usefixtures("redis_client")
# 打到 /chat 的再加一个 "isolate_chat_rate_limit"。
#
# feed 工具的测试（test_tools_*.py）刻意不声明，保持 Redis 不可用的冷路径 ——
# 它们测的是「工具把 FeedService 的结果投影成什么」，不是 FeedService 的缓存策略，
# 而后者已经有专门的 tests/test_feed_service.py（含热冷两条路径的等价性）。


@pytest.fixture
async def checkpointer():
    """生产同款 checkpointer，并做完启动时该做的对齐。

    顺序与 app.main 的 lifespan 一致：setup() 建表 → 对齐排序规则。
    """
    from app.agent_v3.checkpointer import ensure_checkpoint_collation
    from app.agent_v3.deps import db_uri
    from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver

    async with AsyncMySaver.from_conn_string(db_uri()) as saver:
        await saver.setup()
        await ensure_checkpoint_collation()
        yield saver
