"""Validated LLM Intent Router 的聚焦合同测试。

这些测试把模型限定成“只提建议的分类器”：最终 RouteDecision、HybridPlan 与澄清模板
必须全部由本地 registry 编译，模型不能直接生成 Tool 参数或扩大权限。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest
from engine.harness.llm_router import (
    CompositeIntentRouter,
    RouterCandidate,
    build_router_prompt,
    compile_router_candidate,
    parse_router_candidate,
)


def _request(question: str) -> HarnessRequest:
    """构造带私有 caller/run 信息的请求，验证它们不会进入 Router prompt。"""

    return HarnessRequest(
        question=question,
        run_id="private-run-id",
        caller=demo_caller(caller_id="private-caller", roles=("ops",)),
        active_sql_role="ops",
    )


@dataclass
class FakeRouterClient:
    """最小计数 client；字段名与真实 OpenAI-compatible transport 的 usage 一致。"""

    response: str
    calls: int = 0
    request_count: int = 0
    successful_response_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = "fake-router-model"
    provider_label: str = "Fake"

    def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str = "") -> str:
        """模拟一次成功调用并提供请求级 usage。"""

        assert node_purpose == "intent_route"
        assert system_prompt
        self.calls += 1
        self.request_count += 1
        self.successful_response_count += 1
        self.prompt_tokens += 31
        self.completion_tokens += 9
        self.total_tokens += 40
        return self.response


def test_behavior_lock_keeps_canonical_fast_paths_and_uses_model_only_for_open_paraphrase() -> None:
    """Canonical 零调用；旧规则不认识的开放改写才有资格请求模型一次。"""

    client = FakeRouterClient('{"intent":"sql"}')
    router = CompositeIntentRouter(client_factory=lambda: client)

    assert router.decide(_request("各渠道订单量是多少？")).route == "sql"
    assert router.decide(_request("退款政策是什么？")).route == "rag"
    assert client.calls == 0

    decision = router.decide(_request("帮我盘点一下六月成交额表现"))
    assert (decision.route, decision.decision_source) == ("sql", "model")
    assert decision.router_evidence is not None
    assert decision.router_evidence.attempt_count == 1
    assert decision.router_evidence.total_tokens == 40
    assert client.calls == 1


def test_model_cannot_override_pretool_safety_or_closed_world_clarification() -> None:
    """危险 SQL 与已登记澄清永远走 deterministic fast path，模型零调用。"""

    client = FakeRouterClient('{"intent":"rag"}')
    router = CompositeIntentRouter(client_factory=lambda: client)

    dangerous = router.decide(_request("DROP TABLE orders"))
    clarification = router.decide(_request("这个怎么办？"))

    assert (dangerous.route, dangerous.reason_code) == ("sql", "sql_guard_required")
    assert clarification.termination_action == "clarify"
    assert client.calls == 0


def test_unregistered_hybrid_candidate_fails_closed_without_tool() -> None:
    """模型发明 operator 时严格回到调用前 unsupported 决定，不能默认挑一个 Tool。"""

    client = FakeRouterClient(
        '{"intent":"hybrid","hybrid_operator":"shipping_policy_and_orders"}'
    )
    decision = CompositeIntentRouter(client_factory=lambda: client).decide(
        _request("对照一下配送承诺和最近订单表现")
    )

    assert (decision.route, decision.termination_action, decision.decision_source) == (
        "none",
        "unsupported",
        "deterministic",
    )
    assert decision.router_evidence is not None
    assert decision.router_evidence.validation_status == "rejected"
    assert decision.router_evidence.fallback_reason == "candidate_rejected"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        '{"intent":"sql"}{"intent":"rag"}',
        '{"intent":"sql","sql":"SELECT * FROM users"}',
        '{"intent":"rag","document":"secret"}',
        '{"intent":"hybrid"}',
        '{"intent":"clarify"}',
        '{"intent":"unsupported","hybrid_operator":"metric_value_and_definition"}',
    ],
)
def test_candidate_parser_rejects_empty_multiple_extra_and_illegal_field_combinations(raw: str) -> None:
    """单 JSON、闭集字段与 intent/附加字段组合同时失败关闭。"""

    with pytest.raises((ValidationError, ValueError)):
        parse_router_candidate(raw)


def test_candidate_compiler_owns_all_final_plans_and_clarification_templates() -> None:
    """模型只给枚举；SQL/RAG/Hybrid/澄清的最终对象全部由本地代码创建。"""

    sql = compile_router_candidate(RouterCandidate(intent="sql"), question="开放 SQL 问法")
    rag = compile_router_candidate(RouterCandidate(intent="rag"), question="开放政策问法")
    hybrid = compile_router_candidate(
        RouterCandidate(intent="hybrid", hybrid_operator="metric_value_and_definition"),
        question="看看六月 GMV 再解释口径",
    )
    subject = compile_router_candidate(
        RouterCandidate(intent="clarify", clarification_kind="subject"), question="说详细点"
    )
    analytics = compile_router_candidate(
        RouterCandidate(intent="clarify", clarification_kind="analytics_scope"), question="分析退款"
    )
    unsupported = compile_router_candidate(RouterCandidate(intent="unsupported"), question="写首诗")

    assert (sql.route, rag.route, hybrid.route) == ("sql", "rag", "hybrid")
    assert rag.requirement is not None
    assert hybrid.hybrid_plan is not None
    assert hybrid.hybrid_plan.operator == "metric_value_and_definition"
    assert subject.clarification_spec is not None
    assert subject.clarification_spec.identity == "clarification-subject-v1"
    assert analytics.clarification_spec is not None
    assert analytics.clarification_spec.identity == "clarification-analytics-scope-v1"
    assert unsupported.termination_action == "unsupported"


def test_prompt_contains_only_question_and_fixed_taxonomy() -> None:
    """Router prompt 不允许携带 caller、run、Schema、rows、Document、Evidence 或 history。"""

    prompt = build_router_prompt("帮我盘点一下六月成交额表现")

    assert "六月成交额表现" in prompt
    assert "private-caller" not in prompt
    assert "private-run-id" not in prompt
    for forbidden in ("schema_context", "rows", "document_body", "evidence_ledger", "chat_history"):
        assert forbidden not in prompt.lower()
