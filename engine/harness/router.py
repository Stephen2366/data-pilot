"""M35 首个本地 deterministic Router。

Router 的职责是决定“是否取证、取哪一种”，不是理解 Tool 输出或生成答案。规则故意偏窄：
宁可澄清/拒绝，也不能为了看起来聪明而默认调用某个后端。
"""

from __future__ import annotations

from typing import Protocol

from engine.harness.contracts import HarnessRequest, RouteDecision
from engine.rag.answer_flow import AnswerEvidenceRequirement


class Router(Protocol):
    """可替换 Router seam；测试可注入 fake，生产首版使用 deterministic adapter。"""

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """只根据最小请求事实返回一个闭合决定。"""


class DeterministicRouter:
    """首版保守 Router：覆盖固定演示/合同问题，不把未知问题猜成 SQL 或 RAG。"""

    _WRITE_PREFIXES = ("drop ", "delete ", "update ", "insert ", "alter ", "truncate ")
    _RAG_HINTS = ("政策", "规则", "口径", "定义", "说明", "流程", "怎么办", "如何处理")
    _SQL_HINTS = ("多少", "查询", "统计", "排名", "top", "gmv", "退款率", "订单", "工单", "渠道", "商品")
    _HYBRID_HINTS = ("同时", "并且", "结合", "一边", "以及政策")
    _CLARIFY_HINTS = ("这个", "那个", "它", "详细", "再说说")

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """按“安全拒绝 → 缺条件 → 取证类型 → 保守停止”固定顺序裁决。"""

        text = request.question.strip()
        normalized = text.lower()
        if any(normalized.startswith(prefix) for prefix in self._WRITE_PREFIXES):
            # SQL Guard 需要看到原始危险 SQL，故这里仍选择 SQL Tool，而不是提前把它吞掉。
            return RouteDecision("sql", "sql_guard_required", True, "answer")
        if len(text) < 3 or text in {"?", "？"} or any(hint in text for hint in self._CLARIFY_HINTS):
            return RouteDecision("none", "clarification_required", False, "clarify")

        has_rag = any(hint in text for hint in self._RAG_HINTS)
        has_sql = any(hint in normalized for hint in self._SQL_HINTS)
        if has_rag and (has_sql or any(hint in text for hint in self._HYBRID_HINTS)):
            return RouteDecision("none", "hybrid_unsupported", False, "unsupported")
        if has_rag:
            return RouteDecision(
                "rag",
                "document_evidence_required",
                True,
                "answer",
                requirement=AnswerEvidenceRequirement(),
            )
        if has_sql:
            return RouteDecision("sql", "sql_evidence_required", True, "answer")
        return RouteDecision("none", "unsupported_request", False, "unsupported")
