"""M22 请求语义预检：在调用 LLM 前识别当前单步 Text2SQL 明确不支持的需求。

这不是 SQL Guard，也不尝试用关键词理解任意业务问题；它只处理已经由 diagnostic case
证明会被模型静默改写或变成 transport error 的三类窄契约，结果仍统一记为 plan validation。
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.nl2sql.schema_loader import DomainSchema


@dataclass(frozen=True)
class SemanticValidationIssue:
    """一条可观测的语义拒绝，供 pipeline trace 与 eval scorer 共用。"""

    issue_tag: str
    message: str
    blocked_via: str = "semantic_request_validation"


def validate_request_semantics(question: str, *, domain_schema: DomainSchema) -> SemanticValidationIssue | None:
    """只拒绝当前 Schema / 单步能力明确无法表达的需求，避免用泛化规则误伤合法查询。"""

    normalized = question.replace(" ", "")
    available_columns = {field.name for table in domain_schema.tables.values() for field in table.fields.values()}

    # ★ “供应商名称”是数据库没有任何替代字段的明确缺口；拒绝比偷偷返回 product_name 更诚实。
    if "供应商" in normalized and not {"supplier_name", "supplier_id"} & available_columns:
        return SemanticValidationIssue("missing_column", "当前业务 Schema 未定义商品供应商字段，无法生成可靠查询。")
    if "知识库文档" in normalized and ("订单金额" in normalized or "订单" in normalized):
        return SemanticValidationIssue("unsupported_relation", "知识库文档与订单之间没有可验证归因关系，属于后续 Hybrid 能力。")
    if "先查" in normalized and "再查" in normalized and ("最后" in normalized or "对比" in normalized):
        return SemanticValidationIssue("unsupported_multi_step_plan", "当前 Text2SQL 只支持单个 SQL 查询步骤，不能执行多步对比。")
    return None
