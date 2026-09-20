"""Validated LLM Intent Router 的聚焦合同测试。

这些测试把模型限定成“只提建议的分类器”：最终 RouteDecision、HybridPlan 与澄清模板
必须全部由本地 registry 编译，模型不能直接生成 Tool 参数或扩大权限。
"""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.api.query import QueryRequest
from app.core.config import Settings
from app.main import create_app
from engine.governance import OutboundRequest, decide_outbound, demo_caller
from engine.harness.contracts import HarnessContractError, HarnessRequest, RouteDecision, RouterRunEvidence
from engine.harness.llm_router import (
    CompositeIntentRouter,
    EvidenceDeterministicRouter,
    ROUTER_OUTBOUND_POLICY,
    RouterCandidate,
    build_configured_router,
    build_router_prompt,
    compile_router_candidate,
    parse_router_candidate,
)
from engine.nl2sql.generator import LLMGenerationError, QwenChatClient


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


def test_informative_long_question_with_pronoun_remains_model_eligible() -> None:
    """长问法中的“它”不等于缺主体；旧短澄清模板仍由上一测试锁定。"""

    client = FakeRouterClient(
        '{"intent":"hybrid","hybrid_operator":"metric_value_and_definition"}'
    )
    decision = CompositeIntentRouter(client_factory=lambda: client).decide(
        _request("请把 2026 年 6 月的成交额结果和它的计算含义一起给我。")
    )

    assert decision.route == "hybrid"
    assert decision.decision_source == "model"
    assert client.calls == 1


def test_unregistered_hybrid_candidate_fails_closed_without_tool() -> None:
    """模型发明 operator 时严格回到调用前 unsupported 决定，不能默认挑一个 Tool。"""

    client = FakeRouterClient(
        '{"intent":"hybrid","hybrid_operator":"shipping_policy_and_orders"}'
    )
    decision = CompositeIntentRouter(client_factory=lambda: client).decide(
        _request("对照一下履约承诺和近期交易表现")
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


def test_route_decision_and_router_evidence_reject_illegal_runtime_facts() -> None:
    """decision source、usage、attempt 与 fallback 必须一起闭合。"""

    with pytest.raises(HarnessContractError):
        RouterRunEvidence(
            mode="llm_fallback",
            router_identity="router-v1",
            model_attempted=True,
            attempt_count=2,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            validation_status="accepted",
        )
    with pytest.raises(HarnessContractError):
        RouterRunEvidence(
            mode="llm_fallback",
            router_identity="router-v1",
            model_attempted=True,
            attempt_count=1,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=99,
            latency_ms=1,
            validation_status="accepted",
        )
    with pytest.raises(HarnessContractError):
        RouteDecision("sql", "bad_model_source", True, "answer", decision_source="model")


def test_router_outbound_policy_allows_only_exact_purpose_class_and_fields() -> None:
    """合法 Router 调用可达；复用其他 purpose 或夹带字段在 transport 前被拒绝。"""

    posts: list[dict[str, object]] = []

    def fake_post(_url: str, _headers: dict[str, str], payload: dict[str, object], _timeout: float) -> dict[str, object]:
        """记录最终出站 payload，并模拟一次合法 provider 响应。"""

        posts.append(payload)
        return {
            "choices": [{"message": {"content": '{"intent":"sql"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }

    client = QwenChatClient(
        api_key="test-key",
        base_url="https://example.invalid",
        model="router-test",
        post_json=fake_post,
        outbound_policy=ROUTER_OUTBOUND_POLICY,
        outbound_data_class="router_prompt",
        max_retries=0,
    )
    assert client.complete(prompt="q", system_prompt="s", node_purpose="intent_route") == '{"intent":"sql"}'
    with pytest.raises(LLMGenerationError):
        client.complete(prompt="q", system_prompt="s", node_purpose="sql_generation")
    assert len(posts) == 1

    for forbidden in ("caller", "schema", "rows", "document", "evidence", "history"):
        denied = decide_outbound(
            OutboundRequest(
                receiver="qwen_chat",
                node_purpose="intent_route",
                data_class="router_prompt",
                fields=frozenset({"prompt", "system_prompt", "model", forbidden}),
                fallback_available=True,
            ),
            policy=ROUTER_OUTBOUND_POLICY,
        )
        assert denied.allowed is False


def test_per_request_clients_keep_usage_isolated_under_concurrency() -> None:
    """并发请求必须各自创建 client，calls/tokens 不能跨请求累计。"""

    created: list[FakeRouterClient] = []
    lock = Lock()

    def factory() -> FakeRouterClient:
        """为每次 Router 决策创建并登记独立 client。"""

        client = FakeRouterClient('{"intent":"sql"}')
        with lock:
            created.append(client)
        return client

    router = CompositeIntentRouter(client_factory=factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(router.decide, (_request("盘点六月成交额"), _request("看看夏季成交表现"))))

    assert len(created) == 2 and created[0] is not created[1]
    assert [client.calls for client in created] == [1, 1]
    assert [decision.router_evidence.total_tokens for decision in decisions if decision.router_evidence] == [40, 40]


def test_provider_failure_is_one_safe_attempt_and_never_raises_into_harness() -> None:
    """timeout/缺 key 等 provider failure 只形成一次安全 evidence，并回到原 unsupported。"""

    class TimeoutClient(FakeRouterClient):
        """模拟 provider 在一次传输尝试中超时。"""

        def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str = "") -> str:
            """记录唯一尝试后抛出不应泄漏到 Harness 的异常。"""

            self.calls += 1
            self.request_count += 1
            raise TimeoutError("private transport detail")

    client = TimeoutClient('{"intent":"sql"}')
    decision = CompositeIntentRouter(client_factory=lambda: client).decide(_request("盘点夏季成交表现"))

    assert decision.route == "none"
    assert decision.router_evidence is not None
    assert decision.router_evidence.attempt_count == 1
    assert decision.router_evidence.validation_status == "failed"
    assert decision.router_evidence.fallback_reason == "provider_failed"
    assert "private" not in str(decision.router_evidence.safe_projection())


def test_server_only_mode_configuration_and_request_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认启用组合 Router；显式回滚和客户端不可控合同同时成立。"""

    # 全仓 deterministic 验证会显式设置回滚环境变量；本断言验证的是代码默认值，
    # 因此先隔离进程级覆盖，避免把“默认值”和“运维回滚值”混为一谈。
    monkeypatch.delenv("HARNESS_ROUTER_MODE", raising=False)
    assert Settings(_env_file=None).harness_router_mode == "llm_fallback"
    deterministic = build_configured_router("deterministic")
    candidate = build_configured_router("llm_fallback")
    assert isinstance(deterministic, EvidenceDeterministicRouter)
    assert isinstance(candidate, CompositeIntentRouter)
    with pytest.raises(ValueError):
        build_configured_router("llm_only")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, HARNESS_ROUTER_MODE="llm_only")
    assert not ({"router_mode", "router_model", "hybrid_operator"} & set(QueryRequest.model_fields))

    default_application = create_app(
        Settings(_env_file=None, APP_ENV="test", TASK_BOUNDARY_BACKEND="memory")
    )
    assert isinstance(default_application.state.harness_router, CompositeIntentRouter)
    assert TestClient(default_application).get("/health").status_code == 200

    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            TASK_BOUNDARY_BACKEND="memory",
            HARNESS_ROUTER_MODE="deterministic",
        )
    )
    assert isinstance(application.state.harness_router, EvidenceDeterministicRouter)
