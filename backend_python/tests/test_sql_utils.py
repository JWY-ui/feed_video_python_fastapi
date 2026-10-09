"""LIKE 通配符转义。

用户输入里出现 % 或 _ 时，未转义的 `LIKE %q%` 会被 MySQL 当成通配符：
搜 "%" 会匹配整张表，搜 "a_b" 会连 "axb" 一起返回。绑参数挡不住这个 ——
它们不是注入，是 LIKE 自己的语法。
"""
from __future__ import annotations

from app.utils.sql import escape_like


def test_plain_text_is_untouched():
    assert escape_like("做菜") == "做菜"


def test_percent_becomes_literal():
    assert escape_like("100%") == "100\\%"


def test_underscore_becomes_literal():
    assert escape_like("a_b") == "a\\_b"


def test_backslash_is_escaped_first():
    """顺序要紧：先转义反斜杠，否则会把它自己新增的转义符再转一遍。"""
    assert escape_like("a\\b") == "a\\\\b"


def test_percent_inside_a_backslash_sequence():
    assert escape_like("\\%") == "\\\\\\%"
