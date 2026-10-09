import pytest

from stubs import install_synthetic_tools, remove_synthetic_tools


@pytest.fixture
def stub_tools():
    """注册合成工具，用完撤销，避免污染其它测试。"""
    install_synthetic_tools()
    yield
    remove_synthetic_tools()


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
