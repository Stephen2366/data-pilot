"""M41 RAG Eval 的产品链路执行 adapter。

★ 本 module 的外部 interface 只有 ``execute``。内部临时注入 RAG Tool factory，真实经过
FastAPI endpoint、caller resolver、turn、Harness、RAG Tool 和 Trace；退出时恢复 app state，
普通请求永远看不到 eval-only Composer。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient

from app.main import app
from engine.harness.adapters import RAGToolAdapter
from engine.harness.caller import FixtureCallerResolver
from engine.harness.router import Router
from engine.harness.contracts import HarnessRequest, RouteDecision
from engine.harness.thread import ThreadCheckpointManager
from engine.rag.answer_flow import (
    ANSWER_FLOW_RUNTIME_IDENTITY,
    EvidenceComposer,
    RAGAnswerFlow,
    RAGAnswerResult,
)
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import DocumentEvidencePayload, STAGE_ORDER
from engine.rag.release import load_active_release
from engine.rag.retrieval import DETERMINISTIC_RETRIEVAL_IDENTITY, DeterministicLexicalRetrievalAdapter
from eval.rag_e2e_contracts import (
    RAGExecutionEvidence,
    RAGResolvedRuntime,
    RAGScenario,
    RAG_E2E_RUNTIME_FAMILY,
    RAGEvalContractError,
)
from eval.rag_b4_projection import project_b4_eval_diagnostics


@dataclass(frozen=True)
class ComposerRuntimeMetadata:
    """CLI 显式提供的真实 provider 配置；不会从请求体推断。"""

    model: str
    provider: str = "qwen"
    timeout_seconds: float = 60.0
    retry_count: int = 0
    generation_outbound_policy_identity: str = "not_applicable"


class FixedRAGEvalRouter:
    """external benchmark 已预选 RAG；该 seam 不宣称评测自然语言 Router 能力。"""

    identity = "eval-fixed-rag-router-v1"

    def decide(self, request: HarnessRequest) -> RouteDecision:
        """将已预选的 external benchmark 请求稳定路由到 RAG。"""

        return RouteDecision(
            "rag",
            "eval_rag_route_preselected",
            True,
            "answer",
            requirement=AnswerEvidenceRequirement(),
            decision_source="deterministic",
        )


class RAGProductExecutor:
    """一次请求经过真实产品 seam，并返回安全且足够评分的共享 Evidence。"""

    def __init__(
        self,
        *,
        composer: EvidenceComposer,
        runtime_metadata: ComposerRuntimeMetadata,
        trace_root: Path,
        answer_flow_factory: Callable[[], RAGAnswerFlow] | None = None,
        resolved_runtime_override: RAGResolvedRuntime | None = None,
        router: Router | None = None,
        knowledge_runtime_kind: str = "business_release",
    ) -> None:
        self._composer = composer
        self._metadata = runtime_metadata
        self._trace_root = trace_root
        self._answer_flow_factory = answer_flow_factory
        self._resolved_runtime_override = resolved_runtime_override
        self._router = router
        self._knowledge_runtime_kind = knowledge_runtime_kind

    def resolved_runtime(self) -> RAGResolvedRuntime:
        """从 active release 与实际 Composer 形成可比较身份。"""

        if self._resolved_runtime_override is not None:
            return self._resolved_runtime_override
        _pointer, bundle = load_active_release()
        return RAGResolvedRuntime(
            runtime_family=RAG_E2E_RUNTIME_FAMILY,
            answer_flow_identity=ANSWER_FLOW_RUNTIME_IDENTITY,
            composer_identity=self._composer.identity,
            model=self._metadata.model,
            provider=self._metadata.provider,
            timeout_seconds=self._metadata.timeout_seconds,
            retry_count=self._metadata.retry_count,
            release_identity=bundle.release_identity,
            corpus_identity=bundle.corpus_identity,
            retrieval_adapter_identity=DETERMINISTIC_RETRIEVAL_IDENTITY,
            retrieval_recipe_identity=DeterministicLexicalRetrievalAdapter.recipe_identity,
            authorization_policy_identity=bundle.authorization_policy_identity,
            release_outbound_policy_identity=bundle.outbound_policy_identity,
            generation_outbound_policy_identity=self._metadata.generation_outbound_policy_identity,
            caller_fixture_identity="phase4-rag-e2e-test-fixture-v1",
            route_policy_identity="deterministic-router-v1",
        )

    def execute(self, *, scenario: RAGScenario, replicate: int) -> RAGExecutionEvidence:
        """执行恰好一次 HTTP 产品请求；任何 scorer 都不能再次调用本方法。"""

        trace_path = self._trace_root / f"{scenario.scenario_id}-r{replicate}.jsonl"
        if trace_path.exists() and trace_path.stat().st_size:
            # 进程若在 Trace 落盘后、checkpoint 提交前中断，不能自动再次付费执行同一格。
            raise RAGEvalContractError("rag_execution_uncommitted_trace", str(trace_path))
        observed: list[RAGAnswerResult] = []
        attempts_before = len(getattr(self._composer, "attempts", ()))
        usage_fn = getattr(self._composer, "usage_projection", None)
        usage_before = dict(usage_fn()) if callable(usage_fn) else {}

        def tool_factory() -> RAGToolAdapter:
            """为当前 HTTP 执行创建隔离的 AnswerFlow 与结果观察器。"""

            flow = self._answer_flow_factory() if self._answer_flow_factory is not None else RAGAnswerFlow(composer=self._composer)
            return RAGToolAdapter(
                answer_flow=flow,
                knowledge_runtime_kind=self._knowledge_runtime_kind,  # type: ignore[arg-type]
                result_observer=observed.append,
            )

        previous = {
            "rag_tool_factory": getattr(app.state, "rag_tool_factory", None),
            "caller_resolver": getattr(app.state, "caller_resolver", None),
            "thread_checkpoint_manager": getattr(app.state, "thread_checkpoint_manager", None),
            "trace_path": getattr(app.state, "trace_path", None),
            "harness_router": getattr(app.state, "harness_router", None),
        }
        app.state.rag_tool_factory = tool_factory
        app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
        app.state.thread_checkpoint_manager = ThreadCheckpointManager()
        app.state.trace_path = trace_path
        app.state.harness_router = self._router
        try:
            # raise_server_exceptions=False 很重要：真实产品 500 也必须成为 Eval Evidence，
            # 不能让 pytest/CLI 在保存 checkpoint 前丢掉本次付费尝试。
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/query",
                    json={"question": scenario.question, "user_role": scenario.user_role},
                )
            try:
                body = response.json()
            except ValueError:
                body = {}
        finally:
            app.state.rag_tool_factory = previous["rag_tool_factory"]
            app.state.caller_resolver = previous["caller_resolver"]
            app.state.thread_checkpoint_manager = previous["thread_checkpoint_manager"]
            app.state.harness_router = previous["harness_router"]
            if previous["trace_path"] is None:
                if hasattr(app.state, "trace_path"):
                    delattr(app.state, "trace_path")
            else:
                app.state.trace_path = previous["trace_path"]

        if len(observed) > 1:
            raise RAGEvalContractError("rag_execution_duplicate", "一次产品请求观察到多个 RAGAnswerResult")
        result = observed[0] if observed else None
        trace = _read_single_trace(trace_path)
        stage_keys, stage_counts, identities_redacted = _funnel_projection(result)
        trace_observation = trace.get("tool_observation") or {}
        diagnostics = (
            result.diagnostics.safe_projection()
            if result is not None
            else dict(trace_observation.get("diagnostics") or {})
        )
        attempts = tuple(dict(item) for item in getattr(self._composer, "attempts", ())[attempts_before:])
        usage_after = dict(usage_fn()) if callable(usage_fn) else {}
        usage = {
            str(key): int(usage_after.get(key, 0)) - int(usage_before.get(key, 0))
            for key in set(usage_after) | set(usage_before)
        }
        # ★ M41 顶层 artifact schema 保持不变；只有明确的 M46 runtime 才在既有
        # diagnostics/provider_usage 容器中追加 child ledger 与分项账本。
        runtime_family = self.resolved_runtime().runtime_family
        trace_validity = (
            (trace_observation.get("diagnostics") or {}).get("evidence_validity")
            if isinstance(trace_observation.get("diagnostics"), dict)
            else None
        )
        diagnostics, usage = project_b4_eval_diagnostics(
            runtime_family=runtime_family,
            rag_diagnostics=diagnostics,
            result_evidence_validity=result.evidence_validity if result is not None else None,
            trace_evidence_validity=trace_validity if isinstance(trace_validity, dict) else None,
            composer_usage=usage,
        )
        return RAGExecutionEvidence(
            scenario_id=scenario.scenario_id,
            replicate=replicate,
            trace_id=str(body.get("trace_id") or trace.get("trace_id") or "unavailable"),
            status_code=response.status_code,
            route=str(body.get("route") or trace.get("route") or "none"),
            execution_status=str(body.get("execution_status") or trace.get("execution_status") or "failed"),
            answer_status=str(body.get("answer_status") or trace.get("answer_status") or "no_answer"),
            safety_status=str(body.get("safety_status") or trace.get("safety_status") or "passed"),
            reason_code=str(body.get("reason_code") or trace.get("reason_code") or "product_execution_failed"),
            answer=body.get("answer") if isinstance(body.get("answer"), str) else None,
            graph_steps=tuple(str(item) for item in trace.get("graph_steps") or ()),
            graph_invocation_count=int(body.get("graph_invocation_count") or trace.get("graph_invocation_count") or 0),
            rag_tool_calls=(
                int(diagnostics.get("knowledge_tool_calls") or 0)
                or sum(item.get("tool_name") == "rag_answer_flow" for item in trace.get("tool_calls") or ())
            ),
            stage_document_keys=stage_keys,
            stage_counts=stage_counts,
            identities_redacted=identities_redacted,
            citations=tuple(dict(item) for item in body.get("citations") or ()),
            docs_used=tuple(dict(item) for item in body.get("docs_used") or ()),
            rag_diagnostics=diagnostics,
            trace_runtime_identity=dict(trace.get("runtime_identity") or {}),
            provider_attempts=attempts,
            provider_usage={str(key): int(value) for key, value in usage.items()},
            response_trace_consistent=_response_trace_consistent(body, trace),
        )


def _read_single_trace(path: Path) -> dict[str, Any]:
    """正常产品请求应恰好落一条 Trace；异常前退出允许无 Trace。"""

    if not path.exists():
        return {}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 1:
        raise RAGEvalContractError("rag_trace_mismatch", "一次 Scenario 必须对应零或一条 Trace")
    return records[0]


def _funnel_projection(
    result: RAGAnswerResult | None,
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], tuple[tuple[str, int], ...], bool]:
    """从内部 ledger 形成累计 funnel；安全拒绝只保留计数，不保存文档 key。"""

    if result is None:
        empty = tuple((stage, ()) for stage in STAGE_ORDER)
        return empty, tuple((stage, 0) for stage in STAGE_ORDER), False
    redact = result.safety_status == "blocked"
    current_stages = dict(result.ledger.stages)
    keys_by_threshold: list[tuple[str, tuple[str, ...]]] = []
    counts: list[tuple[str, int]] = []
    for threshold in STAGE_ORDER:
        threshold_index = STAGE_ORDER.index(threshold)
        keys: list[str] = []
        count = 0
        for evidence in result.ledger.evidence:
            if STAGE_ORDER.index(current_stages[evidence.ref.evidence_id]) < threshold_index:
                continue
            count += 1
            if not redact and isinstance(evidence.payload, DocumentEvidencePayload):
                coordinates = evidence.payload.context_coordinates
                keys.append(coordinates.logical_document_id if coordinates is not None else evidence.payload.document_key)
        keys_by_threshold.append((threshold, tuple(keys)))
        counts.append((threshold, count))
    return tuple(keys_by_threshold), tuple(counts), redact


def _response_trace_consistent(response: dict[str, Any], trace: dict[str, Any]) -> bool:
    """只比较两侧都应公开的稳定事实，不比较耗时或私有 Evidence。"""

    if not response or not trace:
        return False
    keys = ("trace_id", "route", "execution_status", "answer_status", "safety_status", "reason_code")
    return all(response.get(key) == trace.get(key) for key in keys)
