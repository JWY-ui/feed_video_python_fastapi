from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.llm_base_url,
        temperature=0.7,
        max_retries=settings.agent_llm_max_retries,
        request_timeout=settings.agent_llm_timeout,
        stream_usage=True,
    )
