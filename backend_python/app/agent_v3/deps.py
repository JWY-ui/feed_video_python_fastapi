"""agent_v3 的装配：LLM / 图 / service 的构造与持有。

**没有 OPENAI_API_KEY 时 /agent/* 一律 503。** agent 没有降级模式 —— 不配 key
就是不可用，而不是静默返回错误结果。这与项目"Redis 缺失时降级"的哲学不同，
因为降级后的 agent 只会胡说。
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from app.agent_v3.service import AgentV3Service
from app.config import settings

logger = logging.getLogger("agent_v3.deps")

_service: AgentV3Service | None = None


def is_configured() -> bool:
    # .strip()：`.env` 里留个空格很常见，那不该算配好了 —— 否则会在构造 OpenAI
    # 客户端时抛 "Missing credentials"，报错看不懂。
    return bool(settings.openai_api_key.strip())


def db_uri() -> str:
    """给 AsyncMySaver 用的连接串（它自己开连接池，不走 SQLAlchemy engine）。

    密码可能含 @ / : 等字符，必须转义，否则连接串会被解析错。
    """
    from urllib.parse import quote_plus

    return (
        f"mysql://{quote_plus(settings.mysql_user)}:{quote_plus(settings.mysql_password)}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )


def build_llm():
    """真模型。DeepSeek 走 OpenAI 兼容协议，所以直接用 ChatOpenAI。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.llm_base_url,
        temperature=0.7,
        max_retries=settings.agent_llm_max_retries,
        request_timeout=settings.agent_llm_timeout,
        stream_usage=True,
    )


def init_service(service: AgentV3Service | None) -> None:
    """由 lifespan 调用（或测试里直接注入）。"""
    global _service
    _service = service


def get_service() -> AgentV3Service:
    """FastAPI 依赖。没装配好就 503，而不是 500。"""
    if _service is None:
        raise HTTPException(
            status_code=503, detail="agent 不可用：未配置 OPENAI_API_KEY"
        )
    return _service
