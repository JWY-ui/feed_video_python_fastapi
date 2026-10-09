"""SQL 小工具。"""
from __future__ import annotations


def escape_like(value: str) -> str:
    """把 LIKE 的通配符转成字面量。

    绑参数挡不住 `%` 和 `_` —— 它们不是注入，是 LIKE 自己的语法。不转义的话
    搜 "%" 会匹配整张表。

    反斜杠必须**最先**替换，否则随后给 % / _ 加上的转义符会被这一步再转一遍。
    MySQL 默认就以反斜杠为转义符，配合绑参数即可，不需要 ESCAPE 子句。
    """
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
