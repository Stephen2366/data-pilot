"""SQL Guard 预检：识别用户输入里明显的 DDL / DML 风险词。

这层不替代 `validate_sql_policy()`，只解决一个特定问题：用户直接输入
`DROP TABLE ...` 这类危险 SQL 时，不能先交给 LLM 改写成看似安全的 SELECT。
新 Text2SQL pipeline 会在 lifecycle 里记录 `sql_guard` step；旧模板链路仍在 API 层复用
同一判断，避免两套关键词口径漂移。
"""

from __future__ import annotations

import re

DANGEROUS_SQL_KEYWORDS = ("drop", "delete", "update", "insert", "alter", "truncate")


def looks_like_dangerous_sql(text: str) -> bool:
    """判断输入文本是否明显包含危险 SQL 动词。"""

    normalized = text.lower()
    return any(re.search(rf"\b{keyword}\b", normalized) for keyword in DANGEROUS_SQL_KEYWORDS)

