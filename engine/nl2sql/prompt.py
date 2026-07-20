"""M4 Prompt Builder：把业务 Schema、KPI 和 few-shot 示例组装给 LLM。

Prompt 的职责是“尽量让模型生成好 SQL”；真正的安全门仍在 SQL Guard / RBAC。
"""

from __future__ import annotations

from engine.nl2sql.schema_loader import DomainSchema


def _format_tables(domain_schema: DomainSchema) -> str:
    """把可用表和字段说明压成 prompt 友好的文本。"""

    lines: list[str] = []
    for table in domain_schema.tables.values():
        lines.append(f"- 表 `{table.name}`：{table.business_meaning}")
        for field in table.fields.values():
            sensitive_note = "，敏感字段" if field.sensitivity == "sensitive" else ""
            lines.append(f"  - {table.name}.{field.name}：{field.meaning}；角色={field.semantic_role}{sensitive_note}")
    return "\n".join(lines)


def _format_metrics(domain_schema: DomainSchema) -> str:
    """把 KPI 口径写进 prompt，减少 GMV / 退款率这类业务词歧义。"""

    lines: list[str] = []
    for metric in domain_schema.metrics.values():
        filter_text = f"；过滤条件：{metric.filter}" if metric.filter else ""
        time_text = f"；默认时间字段：{metric.default_time_field}" if metric.default_time_field else ""
        lines.append(f"- {metric.name}（{metric.key}）：{metric.formula}{filter_text}{time_text}。{metric.description}")
    return "\n".join(lines)


def _format_examples(domain_schema: DomainSchema) -> str:
    """把 M3 模板 SQL 作为 few-shot 示例，沿用已验证口径。"""

    lines: list[str] = []
    for example in domain_schema.examples[:5]:
        lines.append(f"### few-shot {example.example_id}")
        lines.append(f"问题：{example.question}")
        lines.append("SQL：")
        lines.append(example.sql)
    return "\n".join(lines)


def build_sql_prompt(*, question: str, user_role: str, domain_schema: DomainSchema) -> str:
    """构造 M4 NL2SQL prompt。

    ★ 这里明确告诉模型输出 JSON，但后续仍会兼容 fenced SQL；因为真实 LLM 偶尔会不听话，
    不能让响应格式小波动直接拖垮主链路。
    """

    sensitive_fields = ", ".join(sorted(domain_schema.sensitive_fields)) or "无"
    return f"""你是 DataPilot 的 NL2SQL 生成器。请严格遵守：
1. 只生成单条 SELECT 查询；禁止 DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE。
2. 不要查询敏感字段。当前敏感字段：{sensitive_fields}。
3. 遵守用户角色 `{user_role}` 的权限边界；如果问题需要越权数据，也先生成最接近的安全 SELECT，后续 SQL Guard 会拦截。
4. SQL 使用 MySQL 兼容语法，尽量避免方言专属函数；日期范围使用明确字面值。
5. 只返回 JSON：{{"sql": "...", "tables_used": ["..."], "confidence": 0.0-1.0, "reasoning_summary": "一句话说明"}}。

可用表和字段：
{_format_tables(domain_schema)}

业务指标口径：
{_format_metrics(domain_schema)}

few-shot 示例：
{_format_examples(domain_schema)}

用户问题：{question}
"""
