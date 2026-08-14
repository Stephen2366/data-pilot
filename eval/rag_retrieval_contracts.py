"""M32 `phase4-rag-retrieval-v1` 确定性 Knowledge retrieval Eval family。

本 family 与 M31 ``phase4-v1``、Text2SQL ``m27-v3`` 完全分离。每个 Scenario 恰好调用
一次 Knowledge Tool，required 合同和 advisory retrieval 效果共享同一 ExecutionEvidence；
技术不可用时，root-cause 合同仍可观察，而 gold coverage 为 ``not_observed``。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from typing import Any, Literal, Mapping

from engine.governance import (
    AuthorizationDecision,
    authorize_document,
    document_safe_ref,
    test_caller,
    unverified_request_caller,
)
from engine.rag.evidence import DocumentEvidencePayload, Evidence
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool, RetrievalOutcome
from engine.rag.release import ReleaseBundle, load_active_release
from engine.rag.retrieval import (
    DeterministicLexicalRetrievalAdapter,
    RetrievalAdapterError,
    RetrievalBatch,
    RetrievalBudget,
)

RAG_RETRIEVAL_CONTRACT_VERSION = "phase4-rag-retrieval-v1"
RAG_RETRIEVAL_RUNTIME_IDENTITY = "phase4-rag-retrieval-local-fixture-v1"
RAG_RETRIEVAL_CALLER_FIXTURE_IDENTITY = "phase4-rag-retrieval-callers-v1"

AssertionStatus = Literal["passed", "failed", "not_observed"]
AssertionEffect = Literal["required", "advisory"]


class RAGRetrievalContractError(ValueError):
    """Eval catalog、执行器或 completed artifact 的 closed-world 失败。"""

    def __init__(self, reason_code: str, message: str) -> None:
        """保存 closed-world 校验失败的稳定 reason。"""

        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _hash(payload: Mapping[str, Any] | list[Any]) -> str:
    """用 canonical JSON 生成 catalog/artifact 的稳定 identity。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RAGRetrievalAssertionSpec:
    """一条 assertion 的 closed-world ID 和 Gate effect。"""

    assertion_id: str
    effect: AssertionEffect


@dataclass(frozen=True)
class RAGRetrievalScenario:
    """M32 首批 retrieval Scenario；不包含 answer/citation 的未来字段。"""

    scenario_id: str
    question: str
    caller_kind: Literal["customer_service", "ops", "unverified"]
    expected_reason: str
    gold_document_keys: tuple[str, ...]
    mode: Literal["normal", "stale_revision", "retrieval_unavailable"]
    assertions: tuple[RAGRetrievalAssertionSpec, ...]


def _spec(*required: str, advisory: tuple[str, ...] = ()) -> tuple[RAGRetrievalAssertionSpec, ...]:
    """用短写法声明 required 与 advisory，effect 仍会进入 contract identity。"""

    return tuple(RAGRetrievalAssertionSpec(item, "required") for item in required) + tuple(
        RAGRetrievalAssertionSpec(item, "advisory") for item in advisory
    )


SCENARIOS: tuple[RAGRetrievalScenario, ...] = (
    RAGRetrievalScenario(
        "quality_refund_retrieval",
        "质量问题退款需要提供哪些材料？",
        "customer_service",
        "evidence_retrieved",
        ("refund_policy_quality",),
        "normal",
        _spec(
            "reason_correct", "gold_candidate_covered", "gold_selected_covered", "selected_stage_correct",
            advisory=("gold_rank_top1",),
        ),
    ),
    RAGRetrievalScenario(
        "gmv_definition_retrieval",
        "GMV 指标口径是什么？",
        "ops",
        "evidence_retrieved",
        ("gmv_metric_note",),
        "normal",
        _spec("reason_correct", "gold_selected_covered", "runtime_identity_complete", advisory=("gold_rank_top1",)),
    ),
    RAGRetrievalScenario(
        "warranty_no_candidate",
        "平台有没有五年整机保修？",
        "customer_service",
        "no_candidate",
        (),
        "normal",
        _spec("reason_correct", "no_evidence_returned", "adapter_called_once"),
    ),
    RAGRetrievalScenario(
        "unverified_acl_non_disclosure",
        "敏感字段访问规范是什么？",
        "unverified",
        "no_authorized_evidence",
        (),
        "normal",
        _spec("reason_correct", "adapter_prefilter_empty", "safe_projection_non_disclosure", "adapter_called_once"),
    ),
    RAGRetrievalScenario(
        "quality_revision_stale",
        "质量问题退款规则",
        "customer_service",
        "stale_revision",
        ("refund_policy_quality",),
        "stale_revision",
        _spec("reason_correct", "no_evidence_returned", "candidate_not_advanced"),
    ),
    RAGRetrievalScenario(
        "retriever_unavailable",
        "质量问题退款规则",
        "customer_service",
        "retrieval_unavailable",
        ("refund_policy_quality",),
        "retrieval_unavailable",
        _spec(
            "execution_external_unavailable", "reason_correct", "adapter_called_once",
            advisory=("gold_candidate_covered",),
        ),
    ),
)


def contract_identity(scenarios: tuple[RAGRetrievalScenario, ...] = SCENARIOS) -> str:
    """冻结题面、caller、gold、mode、assertion 和 effect 的完整身份。"""

    return _hash(
        {
            "contract_version": RAG_RETRIEVAL_CONTRACT_VERSION,
            "scenarios": [asdict(item) for item in scenarios],
        }
    )


@dataclass(frozen=True)
class RAGRetrievalExecutionEvidence:
    """一次 Tool 调用产生的安全证据；不保存 question 或正文。"""

    scenario_id: str
    replicate: int
    execution_outcome: str
    reason_code: str
    query_fingerprint: str
    candidate_refs: tuple[str, ...]
    selected_refs: tuple[str, ...]
    candidate_ranks: tuple[tuple[str, int], ...]
    selected_stages: tuple[tuple[str, str], ...]
    adapter_calls: int
    adapter_prefilter_empty: bool
    safe_projection_non_disclosure: bool
    adapter_identity: str
    recipe_identity: str


@dataclass(frozen=True)
class RAGRetrievalAssertionResult:
    """一次 assertion 的 effect、状态和共享执行证据引用。"""

    scenario_id: str
    assertion_id: str
    effect: AssertionEffect
    status: AssertionStatus
    evidence_ref: str


@dataclass(frozen=True)
class RAGRetrievalArtifact:
    """closed-world completed artifact；通过校验后才能投影 Gate/summary。"""

    artifact_identity: str
    contract_version: str
    contract_identity: str
    runtime_identity: str
    caller_fixture_identity: str
    release_identity: str
    corpus_identity: str
    adapter_identity: str
    recipe_identity: str
    selected_scenario_ids: tuple[str, ...]
    execution_evidence: tuple[RAGRetrievalExecutionEvidence, ...]
    assertion_results: tuple[RAGRetrievalAssertionResult, ...]
    lifecycle_status: str = "completed"

    def unsigned_payload(self) -> dict[str, Any]:
        """返回参与 artifact hash 的全部封闭世界字段。"""

        return {
            "contract_version": self.contract_version,
            "contract_identity": self.contract_identity,
            "runtime_identity": self.runtime_identity,
            "caller_fixture_identity": self.caller_fixture_identity,
            "release_identity": self.release_identity,
            "corpus_identity": self.corpus_identity,
            "adapter_identity": self.adapter_identity,
            "recipe_identity": self.recipe_identity,
            "selected_scenario_ids": list(self.selected_scenario_ids),
            "execution_evidence": [asdict(item) for item in self.execution_evidence],
            "assertion_results": [asdict(item) for item in self.assertion_results],
            "lifecycle_status": self.lifecycle_status,
        }

    def to_dict(self) -> dict[str, Any]:
        """生成含 identity 的可序列化 artifact。"""

        return {**self.unsigned_payload(), "artifact_identity": self.artifact_identity}


@dataclass(frozen=True)
class RAGRetrievalGate:
    """required assertions 的唯一门禁投影。"""

    status: Literal["passed", "failed", "inconclusive"]
    passed: int
    failed: int
    not_observed: int


@dataclass(frozen=True)
class RetrievalEffectSummary:
    """retrieval-only assertion 读数；与 required Gate 分开解释。"""

    eligible: int
    observed: int
    passed: int
    failed: int
    not_observed: int


class _CountingAdapter:
    """测试执行环境中的透明计数器，不改变 resolved adapter identity。"""

    def __init__(self, delegate=None) -> None:
        """包装确定性 adapter 或故障 fixture，并保留其运行身份。"""

        self.delegate = delegate or DeterministicLexicalRetrievalAdapter()
        self.identity = self.delegate.identity
        self.recipe_identity = self.delegate.recipe_identity
        self.calls: list[tuple[Any, ...]] = []

    def retrieve(self, *, question, confirmed_conditions, entries, limit):
        """记录唯一一次 Tool→adapter 调用并透明转发。"""

        self.calls.append(entries)
        return self.delegate.retrieve(
            question=question,
            confirmed_conditions=confirmed_conditions,
            entries=entries,
            limit=limit,
        )


class _UnavailableAdapter:
    """保持正式 adapter identity 的确定性技术故障 fixture。"""

    identity = DeterministicLexicalRetrievalAdapter.identity
    recipe_identity = DeterministicLexicalRetrievalAdapter.recipe_identity

    def retrieve(self, **_kwargs):
        """以结构化异常模拟后端不可用，不伪造空候选。"""

        raise RetrievalAdapterError("retrieval_backend_failed", "deterministic fault fixture")


def _caller(scenario: RAGRetrievalScenario):
    """由受控 fixture kind 创建 caller，拒绝从 Scenario 注入任意角色集合。"""

    if scenario.caller_kind == "unverified":
        return unverified_request_caller(caller_id="rag-unverified", claimed_roles={"admin"})
    return test_caller(caller_id=f"rag-{scenario.caller_kind}", roles={scenario.caller_kind})


def _gold_refs(bundle: ReleaseBundle, document_keys: tuple[str, ...]) -> frozenset[str]:
    """把受控 gold key 映射为不含原始 key 的 active document safe refs。"""

    indexed = {entry.document_key: entry for entry in bundle.entries}
    try:
        return frozenset(document_safe_ref(indexed[key]) for key in document_keys)
    except KeyError as exc:
        raise RAGRetrievalContractError("scenario_gold_missing", "gold document 不在 active release") from exc


def _stale_authorization(*, caller, entry, purpose, phase, policy) -> AuthorizationDecision:
    """模拟同一 Tool 调用内 gold revision 在 pre-generation 前失效。"""

    decision = authorize_document(caller=caller, entry=entry, purpose=purpose, phase=phase, policy=policy)
    if phase == "pre_generation" and entry.document_key == "refund_policy_quality":
        return replace(decision, allowed=False, reason_code="revision_unavailable", allowed_purpose=None)
    return decision


def _execution_evidence(
    scenario: RAGRetrievalScenario,
    outcome: RetrievalOutcome,
    adapter: _CountingAdapter,
    bundle: ReleaseBundle,
) -> RAGRetrievalExecutionEvidence:
    """把一次 Tool outcome 固化成无 question/正文的共享评分证据。"""

    entry_index = {(entry.document_key, entry.revision): entry for entry in bundle.entries}

    def safe_document_ref(evidence: Evidence) -> str:
        """只允许本次 active bundle 中的 Document Evidence 进入 Eval artifact。"""

        if not isinstance(evidence.payload, DocumentEvidencePayload):
            raise RAGRetrievalContractError("execution_evidence_kind_invalid", "RAG retrieval 只能记录文档 Evidence")
        key = (evidence.payload.document_key, evidence.payload.revision)
        try:
            return document_safe_ref(entry_index[key])
        except KeyError as exc:
            raise RAGRetrievalContractError(
                "execution_evidence_release_mismatch", "Evidence 不属于本次 active release"
            ) from exc

    candidate_refs = tuple(safe_document_ref(item) for item in outcome.ledger.evidence)
    selected_refs = tuple(safe_document_ref(item) for item in outcome.selected_evidence)
    # rank 与 candidate Evidence 顺序一致；adapter match 不写正文或原始 document key。
    candidate_ranks = tuple((ref, rank) for rank, ref in enumerate(candidate_refs, start=1))
    selected_stages = tuple(
        (safe_document_ref(item), outcome.ledger.stage_of(item.ref.evidence_id))
        for item in outcome.selected_evidence
    )
    projection = str(outcome.safe_projection())
    return RAGRetrievalExecutionEvidence(
        scenario_id=scenario.scenario_id,
        replicate=1,
        execution_outcome=outcome.execution_outcome,
        reason_code=outcome.reason_code,
        query_fingerprint=outcome.diagnostics.query_fingerprint,
        candidate_refs=candidate_refs,
        selected_refs=selected_refs,
        candidate_ranks=candidate_ranks,
        selected_stages=selected_stages,
        adapter_calls=outcome.diagnostics.adapter_calls,
        adapter_prefilter_empty=bool(adapter.calls and adapter.calls[0] == ()),
        safe_projection_non_disclosure=(
            "敏感字段" not in projection
            and "sensitive_data_policy" not in projection
            and "authorized_entry_count" not in projection
            and "candidate_count" not in projection
        ),
        adapter_identity=outcome.diagnostics.adapter_identity,
        recipe_identity=outcome.diagnostics.recipe_identity,
    )


def _assertions(
    scenario: RAGRetrievalScenario,
    evidence: RAGRetrievalExecutionEvidence,
    gold_refs: frozenset[str],
) -> tuple[RAGRetrievalAssertionResult, ...]:
    """只读 ExecutionEvidence 评分；禁止为每条 assertion 重跑 Tool。"""

    candidate = set(evidence.candidate_refs)
    selected = set(evidence.selected_refs)
    statuses: dict[str, AssertionStatus] = {
        "reason_correct": "passed" if evidence.reason_code == scenario.expected_reason else "failed",
        "gold_candidate_covered": "passed" if gold_refs <= candidate else "failed",
        "gold_selected_covered": "passed" if gold_refs <= selected else "failed",
        "selected_stage_correct": "passed" if evidence.selected_stages and all(
            stage == "selected" for _, stage in evidence.selected_stages
        ) else "failed",
        "gold_rank_top1": "passed" if gold_refs and evidence.candidate_ranks and evidence.candidate_ranks[0][0] in gold_refs else "failed",
        "runtime_identity_complete": "passed" if evidence.adapter_identity and evidence.recipe_identity else "failed",
        # candidate 是受控内部账本；Tool 对外实际返回的是 selected_evidence。
        "no_evidence_returned": "passed" if not selected else "failed",
        "adapter_called_once": "passed" if evidence.adapter_calls == 1 else "failed",
        "adapter_prefilter_empty": "passed" if evidence.adapter_prefilter_empty else "failed",
        "safe_projection_non_disclosure": "passed" if evidence.safe_projection_non_disclosure else "failed",
        "candidate_not_advanced": "passed" if candidate and not selected and not evidence.selected_stages else "failed",
        "execution_external_unavailable": "passed" if evidence.execution_outcome == "external_unavailable" else "failed",
    }
    # 技术不可用时没有检索答卷，coverage 是不可观察，不是业务错误。
    if evidence.execution_outcome == "external_unavailable":
        statuses["gold_candidate_covered"] = "not_observed"
        statuses["gold_selected_covered"] = "not_observed"
        statuses["gold_rank_top1"] = "not_observed"

    results: list[RAGRetrievalAssertionResult] = []
    for spec in scenario.assertions:
        if spec.assertion_id not in statuses:
            raise RAGRetrievalContractError("executor_assertion_mismatch", "Scenario assertion 没有 scorer")
        results.append(
            RAGRetrievalAssertionResult(
                scenario_id=scenario.scenario_id,
                assertion_id=spec.assertion_id,
                effect=spec.effect,
                status=statuses[spec.assertion_id],
                evidence_ref=f"execution:{scenario.scenario_id}:1",
            )
        )
    return tuple(results)


def _execute_scenario(
    scenario: RAGRetrievalScenario,
    *,
    bundle: ReleaseBundle,
    active_loader,
) -> tuple[RAGRetrievalExecutionEvidence, tuple[RAGRetrievalAssertionResult, ...]]:
    """执行一个 Scenario 一次，并从同一证据产生全部 assertion。"""

    delegate = _UnavailableAdapter() if scenario.mode == "retrieval_unavailable" else None
    adapter = _CountingAdapter(delegate)
    tool = KnowledgeTool(
        adapter=adapter,
        active_loader=active_loader,
        authorization_fn=_stale_authorization if scenario.mode == "stale_revision" else authorize_document,
    )
    request = KnowledgeRequest(
        question=scenario.question,
        caller=_caller(scenario),
        purpose="answer_evidence",
        run_id=f"rag-retrieval:{scenario.scenario_id}",
        budget=RetrievalBudget(max_candidates=5, max_selected=1 if scenario.mode == "stale_revision" else 2),
    )
    outcome = tool.retrieve(request)  # ★ 一个 Scenario 的唯一一次 Tool 执行。
    evidence = _execution_evidence(scenario, outcome, adapter, bundle)
    return evidence, _assertions(scenario, evidence, _gold_refs(bundle, scenario.gold_document_keys))


def run_rag_retrieval_contract_suite() -> RAGRetrievalArtifact:
    """执行完整 closed-world M32 suite；无网络、LLM、向量库或评分重跑。"""

    pointer, bundle = load_active_release()
    active_loader = lambda: (pointer, bundle)
    execution: list[RAGRetrievalExecutionEvidence] = []
    results: list[RAGRetrievalAssertionResult] = []
    for scenario in SCENARIOS:
        scenario_evidence, scenario_results = _execute_scenario(
            scenario, bundle=bundle, active_loader=active_loader
        )
        execution.append(scenario_evidence)
        results.extend(scenario_results)

    adapter = DeterministicLexicalRetrievalAdapter()
    artifact = RAGRetrievalArtifact(
        artifact_identity="",
        contract_version=RAG_RETRIEVAL_CONTRACT_VERSION,
        contract_identity=contract_identity(),
        runtime_identity=RAG_RETRIEVAL_RUNTIME_IDENTITY,
        caller_fixture_identity=RAG_RETRIEVAL_CALLER_FIXTURE_IDENTITY,
        release_identity=bundle.release_identity,
        corpus_identity=bundle.corpus_identity,
        adapter_identity=adapter.identity,
        recipe_identity=adapter.recipe_identity,
        selected_scenario_ids=tuple(item.scenario_id for item in SCENARIOS),
        execution_evidence=tuple(execution),
        assertion_results=tuple(results),
    )
    artifact = replace(artifact, artifact_identity=_hash(artifact.unsigned_payload()))
    validate_completed_artifact(artifact)
    return artifact


def validate_completed_artifact(
    artifact: RAGRetrievalArtifact,
    *,
    scenarios: tuple[RAGRetrievalScenario, ...] = SCENARIOS,
) -> None:
    """对 Scenario/replicate/assertion/effect/runtime/hash 做 closed-world 对账。"""

    if artifact.lifecycle_status != "completed":
        raise RAGRetrievalContractError("artifact_not_completed", "只有 completed artifact 可投影")
    adapter = DeterministicLexicalRetrievalAdapter()
    expected_top = (
        RAG_RETRIEVAL_CONTRACT_VERSION,
        contract_identity(scenarios),
        RAG_RETRIEVAL_RUNTIME_IDENTITY,
        RAG_RETRIEVAL_CALLER_FIXTURE_IDENTITY,
        adapter.identity,
        adapter.recipe_identity,
    )
    actual_top = (
        artifact.contract_version,
        artifact.contract_identity,
        artifact.runtime_identity,
        artifact.caller_fixture_identity,
        artifact.adapter_identity,
        artifact.recipe_identity,
    )
    if actual_top != expected_top:
        raise RAGRetrievalContractError("artifact_runtime_mismatch", "contract/runtime/caller/adapter identity 不一致")
    if not artifact.release_identity or not artifact.corpus_identity:
        raise RAGRetrievalContractError("artifact_corpus_missing", "release/corpus identity 不能为空")

    expected_ids = tuple(item.scenario_id for item in scenarios)
    if artifact.selected_scenario_ids != expected_ids:
        raise RAGRetrievalContractError("artifact_scenario_mismatch", "selected Scenario 缺失、额外、重复或乱序")
    evidence_keys = tuple((item.scenario_id, item.replicate) for item in artifact.execution_evidence)
    if evidence_keys != tuple((scenario_id, 1) for scenario_id in expected_ids):
        raise RAGRetrievalContractError("artifact_execution_mismatch", "ExecutionEvidence 缺失、额外、重复或乱序")

    expected_assertions = tuple(
        (scenario.scenario_id, spec.assertion_id, spec.effect)
        for scenario in scenarios
        for spec in scenario.assertions
    )
    actual_assertions = tuple(
        (item.scenario_id, item.assertion_id, item.effect) for item in artifact.assertion_results
    )
    if actual_assertions != expected_assertions:
        raise RAGRetrievalContractError("artifact_assertion_mismatch", "assertion/effect 缺失、额外、重复或乱序")
    if any(item.status not in {"passed", "failed", "not_observed"} for item in artifact.assertion_results):
        raise RAGRetrievalContractError("artifact_status_invalid", "assertion status 非法")
    if _hash(artifact.unsigned_payload()) != artifact.artifact_identity:
        raise RAGRetrievalContractError("artifact_hash_mismatch", "artifact canonical hash 校验失败")


def project_required_gate(artifact: RAGRetrievalArtifact) -> RAGRetrievalGate:
    """只投影 required assertion；任何 failed 优先于 not_observed。"""

    validate_completed_artifact(artifact)
    required = [item for item in artifact.assertion_results if item.effect == "required"]
    passed = sum(item.status == "passed" for item in required)
    failed = sum(item.status == "failed" for item in required)
    not_observed = sum(item.status == "not_observed" for item in required)
    status: Literal["passed", "failed", "inconclusive"] = (
        "failed" if failed else "inconclusive" if not_observed else "passed"
    )
    return RAGRetrievalGate(status, passed, failed, not_observed)


def project_retrieval_effect_summary(artifact: RAGRetrievalArtifact) -> RetrievalEffectSummary:
    """只汇总 gold coverage/rank advisory，不与 required Gate 混算。"""

    validate_completed_artifact(artifact)
    effect_ids = {"gold_candidate_covered", "gold_selected_covered", "gold_rank_top1"}
    selected = [
        item
        for item in artifact.assertion_results
        if item.effect == "advisory" and item.assertion_id in effect_ids
    ]
    passed = sum(item.status == "passed" for item in selected)
    failed = sum(item.status == "failed" for item in selected)
    not_observed = sum(item.status == "not_observed" for item in selected)
    return RetrievalEffectSummary(
        eligible=len(selected),
        observed=passed + failed,
        passed=passed,
        failed=failed,
        not_observed=not_observed,
    )
