"""Validated LLM Intent Router：模型提案，本地编译，失败回到保守决定。

模块刻意只有三个深接口：严格 ``RouterCandidate``、纯确定性 compiler，以及每次请求只
创建一个 client 的组合 Router。模型看不到 caller/Schema/Evidence，也不能生成 SQL、Tool
参数或答案；这延续了 DataPilot “控制面窄、深 Tool 自治”的边界。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from engine.governance import OutboundPolicy, OutboundRule
from engine.harness.contracts import HarnessRequest, RouteDecision, RouterRunEvidence
from engine.harness.router import (
    ClarificationKind,
    DeterministicRouter,
    HybridOperator,
    Router,
    registered_clarification,
    registered_hybrid_plan,
)
from engine.nl2sql.generator import LLMClient, get_default_llm_client
from engine.rag.answer_flow import AnswerEvidenceRequirement

RouterMode = Literal["deterministic", "llm_fallback"]
RouterIntent = Literal["sql", "rag", "hybrid", "clarify", "unsupported"]

ROUTER_IDENTITY = "validated-llm-intent-router-v1"
ROUTER_OUTBOUND_POLICY_IDENTITY = "phase4-router-intent-outbound-v1"
ROUTER_CHAT_FIELDS = frozenset({"prompt", "system_prompt", "model"})
ROUTER_OUTBOUND_POLICY = OutboundPolicy(
    identity=ROUTER_OUTBOUND_POLICY_IDENTITY,
    rules=(
        OutboundRule("qwen_chat", "intent_route", "router_prompt", ROUTER_CHAT_FIELDS),
        OutboundRule("deepseek_chat", "intent_route", "router_prompt", ROUTER_CHAT_FIELDS),
    ),
)

ROUTER_SYSTEM_PROMPT = """你是 DataPilot 的受限意图分类器。
只返回一个 JSON 对象，不要 Markdown、解释或第二个对象。
允许字段只有 intent、hybrid_operator、clarification_kind。
intent 只能是 sql、rag、hybrid、clarify、unsupported。
hybrid 只允许 metric_value_and_definition 或 refund_reason_and_policy。
clarify 只允许 subject 或 analytics_scope。
SQL 表示需要业务数据计算；RAG 表示只需要政策、规则、流程或指标定义材料；
Hybrid 表示同一问题同时要求已登记的数据值与材料解释；信息不足用 clarify；范围外用 unsupported。
不要生成 SQL、答案、工具名、分支问题、权限、字段名或数据内容。"""


class RouterCandidate(BaseModel):
    """模型唯一可返回的闭集 DTO；任何额外字段或非法组合都拒绝。"""

    model_config = ConfigDict(extra="forbid")

    intent: RouterIntent
    hybrid_operator: HybridOperator | None = None
    clarification_kind: ClarificationKind | None = None

    @model_validator(mode="after")
    def validate_field_combination(self) -> "RouterCandidate":
        """确保附加枚举只在对应 intent 出现，避免候选语义含糊。"""

        if (self.intent == "hybrid") != (self.hybrid_operator is not None):
            raise ValueError("hybrid intent 必须且只能携带 hybrid_operator")
        if (self.intent == "clarify") != (self.clarification_kind is not None):
            raise ValueError("clarify intent 必须且只能携带 clarification_kind")
        return self


def build_router_prompt(question: str) -> str:
    """形成最小 user prompt；调用接口故意不接受 caller、history 或 Tool 上下文。"""

    normalized = question.strip()
    if not normalized:
        raise ValueError("Router question 不能为空")
    return f"请分类下面这个用户问题：\n<question>{normalized}</question>"


def parse_router_candidate(raw_text: str) -> RouterCandidate:
    """严格解析单个 JSON 对象；不做 fenced/前后解释/多对象容错。"""

    if not raw_text.strip():
        raise ValueError("Router candidate 不能为空")
    return RouterCandidate.model_validate_json(raw_text.strip())


def compile_router_candidate(candidate: RouterCandidate, *, question: str) -> RouteDecision:
    """把枚举提案编译成服务端 owned 的最终决定；本函数不读取模型原文。"""

    del question  # 当前 registry 使用冻结模板；保留参数是为了未来显式版本升级，而非暗中抽取。
    if candidate.intent == "sql":
        return RouteDecision("sql", "model_sql_evidence_required", True, "answer")
    if candidate.intent == "rag":
        return RouteDecision(
            "rag",
            "model_document_evidence_required",
            True,
            "answer",
            requirement=AnswerEvidenceRequirement(),
        )
    if candidate.intent == "hybrid":
        assert candidate.hybrid_operator is not None
        return RouteDecision(
            "hybrid",
            "model_hybrid_plan_required",
            True,
            "answer",
            hybrid_plan=registered_hybrid_plan(candidate.hybrid_operator),
        )
    if candidate.intent == "clarify":
        assert candidate.clarification_kind is not None
        return RouteDecision(
            "none",
            "model_clarification_required",
            False,
            "clarify",
            clarification_spec=registered_clarification(candidate.clarification_kind),
        )
    return RouteDecision("none", "model_unsupported_request", False, "unsupported")


RouterClientFactory = Callable[[], LLMClient]


def create_router_client() -> LLMClient:
    """复用现有 provider transport，但隔离 policy、purpose、usage 和 retry。"""

    return get_default_llm_client(
        outbound_policy=ROUTER_OUTBOUND_POLICY,
        outbound_data_class="router_prompt",
        max_retries=0,
    )


def _usage(client: object) -> tuple[int, int, int]:
    """读取单请求 client 的累计 usage；total 由两个分量重算以保持合同闭合。"""

    prompt_tokens = max(0, int(getattr(client, "prompt_tokens", 0) or 0))
    completion_tokens = max(0, int(getattr(client, "completion_tokens", 0) or 0))
    return prompt_tokens, completion_tokens, prompt_tokens + completion_tokens


def _evidence(
    *,
    mode: RouterMode,
    client: object | None,
    attempted: bool,
    started_at: float,
    status: Literal["not_attempted", "accepted", "rejected", "failed"],
    fallback_reason: str | None = None,
) -> RouterRunEvidence:
    """集中生成安全 evidence，异常消息和模型正文永远不会进入投影。"""

    prompt_tokens, completion_tokens, total_tokens = _usage(client) if client is not None else (0, 0, 0)
    return RouterRunEvidence(
        mode=mode,
        router_identity=ROUTER_IDENTITY,
        model_attempted=attempted,
        attempt_count=1 if attempted else 0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=(perf_counter() - started_at) * 1000 if attempted else 0.0,
        validation_status=status,
        fallback_reason=fallback_reason,
        provider=str(getattr(client, "provider_label", "unknown")) if client is not None else None,
        model=str(getattr(client, "model", "unknown")) if client is not None else None,
    )


class EvidenceDeterministicRouter:
    """显式 deterministic mode；附带零调用 identity，便于回滚与 Trace 核对。"""

    def __init__(self, router: Router | None = None) -> None:
        """包装指定确定性 Router；未传入时使用产品默认实现。"""

        self._router = router or DeterministicRouter()

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """执行确定性裁决，并补上证明零模型调用的 Router evidence。"""

        started_at = perf_counter()
        decision = self._router.decide(request)
        return replace(
            decision,
            router_evidence=_evidence(
                mode="deterministic",
                client=None,
                attempted=False,
                started_at=started_at,
                status="not_attempted",
            ),
        )


class CompositeIntentRouter:
    """★ 确定性 fast path + 至多一次 LLM fallback + 保守回退。"""

    def __init__(
        self,
        *,
        client_factory: RouterClientFactory = create_router_client,
        deterministic_router: Router | None = None,
    ) -> None:
        """注入请求级 client factory 与确定性前置 Router。"""

        self._client_factory = client_factory
        self._deterministic = deterministic_router or DeterministicRouter()

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """只有 deterministic unsupported 才 model-eligible；其余前置决定全部锁定。"""

        started_at = perf_counter()
        # 步骤 1：先让旧 Router 处理安全拒绝、缺条件和稳定关键词路径。
        fallback = self._deterministic.decide(request)
        if fallback.termination_action != "unsupported":
            return replace(
                fallback,
                router_evidence=_evidence(
                    mode="llm_fallback",
                    client=None,
                    attempted=False,
                    started_at=started_at,
                    status="not_attempted",
                ),
            )

        client: LLMClient | None = None
        try:
            # 步骤 2：仅向专用 Router client 发送当前问题，且整个请求最多调用一次。
            client = self._client_factory()
            raw = client.complete(
                prompt=build_router_prompt(request.question),
                system_prompt=ROUTER_SYSTEM_PROMPT,
                node_purpose="intent_route",
            )
        except Exception:
            return replace(
                fallback,
                router_evidence=_evidence(
                    mode="llm_fallback",
                    client=client,
                    attempted=True,
                    started_at=started_at,
                    status="failed",
                    fallback_reason="provider_failed",
                ),
            )

        try:
            # 步骤 3：模型只提议受限候选；最终 RouteDecision 仍由本地编译器生成。
            candidate = parse_router_candidate(raw)
            compiled = compile_router_candidate(candidate, question=request.question)
        except (ValueError, TypeError):
            return replace(
                fallback,
                router_evidence=_evidence(
                    mode="llm_fallback",
                    client=client,
                    attempted=True,
                    started_at=started_at,
                    status="rejected",
                    fallback_reason="candidate_rejected",
                ),
            )

        evidence = _evidence(
            mode="llm_fallback",
            client=client,
            attempted=True,
            started_at=started_at,
            status="accepted",
        )
        return replace(compiled, decision_source="model", router_evidence=evidence)


def build_configured_router(mode: RouterMode) -> Router:
    """应用唯一 mode 组装入口；非法值启动即失败，不接受请求级覆盖。"""

    if mode == "deterministic":
        return EvidenceDeterministicRouter()
    if mode == "llm_fallback":
        return CompositeIntentRouter()
    raise ValueError(f"不支持的 HARNESS_ROUTER_MODE: {mode}")
