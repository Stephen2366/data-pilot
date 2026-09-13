"""M35 首个本地 deterministic Router。

Router 的职责是决定“是否取证、取哪一种”，不是理解 Tool 输出或生成答案。规则故意偏窄：
宁可澄清/拒绝，也不能为了看起来聪明而默认调用某个后端。
"""

from __future__ import annotations

from typing import Protocol

from engine.harness.contracts import ClarificationFieldSpec, ClarificationSpec, HarnessRequest, HybridPlan, RouteDecision
from engine.rag.answer_flow import AnswerEvidenceRequirement


class Router(Protocol):
    """可替换 Router seam；测试可注入 fake，生产首版使用 deterministic adapter。"""

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """只根据最小请求事实返回一个闭合决定。"""


class DeterministicRouter:
    """首版保守 Router：覆盖固定演示/合同问题，不把未知问题猜成 SQL 或 RAG。"""

    _WRITE_PREFIXES = ("drop ", "delete ", "update ", "insert ", "alter ", "truncate ")
    _RAG_HINTS = ("政策", "规则", "定义", "说明", "流程", "怎么办", "如何处理")
    _METRIC_EXPLANATION_HINTS = ("口径是什么", "说明口径", "解释口径", "口径定义", "口径说明")
    _SQL_HINTS = ("多少", "查询", "统计", "排名", "top", "gmv", "退款率", "订单", "工单", "渠道", "商品")
    _HYBRID_HINTS = ("同时", "并且", "结合", "一边", "以及政策")
    _CLARIFY_HINTS = ("这个", "那个", "它", "详细", "再说说")
    _TIME_HINTS = ("年", "月", "日", "季度", "本周", "上周", "本月", "上月")
    _GROUP_HINTS = ("按渠道", "按商品", "按退款原因", "各渠道", "各商品")

    _SUBJECT_CLARIFICATION = ClarificationSpec(
        identity="clarification-subject-v1",
        prompt="请说明你指的是哪个政策、规则、指标或业务对象。",
        fields=(
            ClarificationFieldSpec(key="subject", label="具体对象", value_type="text", max_length=80),
        ),
        context_template="subject",
    )
    _ANALYTICS_SCOPE_CLARIFICATION = ClarificationSpec(
        identity="clarification-analytics-scope-v1",
        prompt="请补充统计时间范围和分组维度。",
        fields=(
            ClarificationFieldSpec(key="time_range", label="时间范围", value_type="time_range", max_length=80),
            ClarificationFieldSpec(
                key="group_by",
                label="分组维度",
                value_type="enum",
                allowed_values=("渠道", "商品", "退款原因"),
                max_length=20,
            ),
        ),
        context_template="analytics_scope",
    )

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """按“安全拒绝 → 缺条件 → 取证类型 → 保守停止”固定顺序裁决。"""

        text = request.question.strip()
        normalized = text.lower()
        if any(normalized.startswith(prefix) for prefix in self._WRITE_PREFIXES):
            # SQL Guard 需要看到原始危险 SQL，故这里仍选择 SQL Tool，而不是提前把它吞掉。
            return RouteDecision("sql", "sql_guard_required", True, "answer")
        # M29 已冻结“退款情况怎么样”作为缺范围/维度的 clarification 蓝图。M36 只覆盖这一类
        # closed-world 分析意图，不把 Router 扩张成通用自然语言槽位抽取器。
        if (
            "退款情况" in text
            and not any(hint in text for hint in self._TIME_HINTS)
            and not any(hint in text for hint in self._GROUP_HINTS)
        ):
            return RouteDecision(
                "none",
                "clarification_required",
                False,
                "clarify",
                clarification_spec=self._ANALYTICS_SCOPE_CLARIFICATION,
            )
        if len(text) < 3 or text in {"?", "？"} or any(hint in text for hint in self._CLARIFY_HINTS):
            return RouteDecision(
                "none",
                "clarification_required",
                False,
                "clarify",
                clarification_spec=self._SUBJECT_CLARIFICATION,
            )

        # ★ “使用 orders.actual_amount 的业务口径”是在约束 SQL 怎么算，不是要求再查一份
        # 指标说明。只有明确要求解释/定义口径时，才把“口径”提升为 Document Evidence 意图；
        # 这样不会因一个领域术语把 canonical Text2SQL 问题误判成未登记 Hybrid。
        has_rag = any(hint in text for hint in self._RAG_HINTS) or any(
            hint in text for hint in self._METRIC_EXPLANATION_HINTS
        )
        has_sql = any(hint in normalized for hint in self._SQL_HINTS)
        if has_rag and (has_sql or any(hint in text for hint in self._HYBRID_HINTS)):
            plan = self._hybrid_plan_for(text)
            if plan is None:
                return RouteDecision("none", "hybrid_unsupported", False, "unsupported")
            return RouteDecision("hybrid", "hybrid_plan_required", True, "answer", hybrid_plan=plan)
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

    @staticmethod
    def _hybrid_plan_for(text: str) -> HybridPlan | None:
        """把两类 canonical 演示问法投影为薄计划；未登记组合不猜测分支任务。"""

        normalized = text.lower()
        if "gmv" in normalized and any(hint in text for hint in ("口径", "定义", "说明")):
            return HybridPlan(
                identity="hybrid-metric-value-and-definition-v1",
                operator="metric_value_and_definition",
                sql_question="查询 2026 年 6 月 GMV",
                rag_question="GMV 的定义和统计口径是什么？",
                requirement=AnswerEvidenceRequirement(required_terms=("GMV",)),
            )
        if "退款" in text and any(hint in text for hint in ("政策", "规则", "材料")):
            return HybridPlan(
                identity="hybrid-refund-reason-and-policy-v1",
                operator="refund_reason_and_policy",
                sql_question="退款原因排名",
                rag_question="质量问题退款规则",
                requirement=AnswerEvidenceRequirement(required_terms=("质量问题",)),
            )
        return None
