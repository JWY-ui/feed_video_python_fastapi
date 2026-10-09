"""装配层的判断：什么算"配了 key"。"""
from __future__ import annotations

from app.agent_v3.deps import is_configured
from app.config import settings


def test_empty_key_means_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert is_configured() is False


def test_whitespace_only_key_also_means_unconfigured(monkeypatch):
    """`.env` 里留一个空格是很常见的 —— 那不该算配好了，否则会在构造 OpenAI
    客户端时抛一句 "Missing credentials"，很难看懂。"""
    monkeypatch.setattr(settings, "openai_api_key", "   ")
    assert is_configured() is False


def test_a_real_key_means_configured(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-abc")
    assert is_configured() is True
