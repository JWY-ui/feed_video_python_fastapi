import pytest

from stubs import install_synthetic_tools, remove_synthetic_tools


@pytest.fixture
def stub_tools():
    """注册合成工具，用完撤销，避免污染其它测试。"""
    install_synthetic_tools()
    yield
    remove_synthetic_tools()
