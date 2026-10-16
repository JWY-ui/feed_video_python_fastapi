"""agent_v3 的装配：LLM / 图 / service 的构造与持有。

**没有 OPENAI_API_KEY 时 /agent/* 一律 503。** agent 没有降级模式 —— 不配 key
就是不可用，而不是静默返回错误结果。这与项目"Redis 缺失时降级"的哲学不同，
因为降级后的 agent 只会胡说。

同理，**Redis 不可用时需要串行化的两个端点（/chat、/confirm）也 503** ——
没有会话锁就谈不上正确性（见 app/agent_v3/lock.py）。这两条 503 是同一个判断：
依赖缺失时明确不可用，而不是降级到一条会出错的路径上。
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from app.agent_v3.service import AgentV3Service
from app.config import settings
from app.middleware.rate_limit import rate_limit
from app.utils.redis_client import redis_client

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


def require_lock_backend() -> None:
    """需要会话锁的端点（/chat、/confirm）在这里挡住 Redis 不可用的情况。

    在 HTTP 层用 503 而不是在 SSE 里回一条 error 事件：这是依赖级的不可用，
    状态码上就该看得见 —— 与上面没配 key 的处理对称。

    只挂在需要串行化的端点上：侧栏列表 / 历史 / 删除是纯 DB 查询，不碰锁，
    Redis 挂了也不该连看会话都看不了。
    """
    if not redis_client.available:
        raise HTTPException(
            status_code=503,
            detail="agent 暂不可用：Redis 未连接，无法保证同一会话串行执行",
        )


# /chat 每轮都要烧 token，是全站最贵的端点。限流挂在这个模块的装配层而不是
# main.py：agent 有一半端点是廉价 DB 查询，不能像 like/social 那样整路由一刀切，
# 所以按端点分组挂 —— 见 router.py 的 stream_router。
chat_rate_limiter = rate_limit("agent_chat", 10, 60)
