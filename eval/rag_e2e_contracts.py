"""M41 Phase 4 RAG 真实产品链路 Eval 的版本化合同。

本 module 只定义调用者必须知道的 interface：Scenario、selector、一次执行证据、assertion、
RunSpec 与 completed artifact。执行器、provider 和报告实现都隐藏在这些小 interface 后面。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal, Mapping

import yaml


RAG_E2E_CONTRACT_VERSION = "phase4-rag-e2e-v1"
RAG_E2E_ARTIFACT_FORMAT = "phase4-rag-e2e-artifact-v1"
RAG_E2E_RUNTIME_FAMILY = "phase4-rag-product-harness-real-composer-v1"
RAG_RUNTIME_ADDITIVE_FIELDS = (
    "retrieval_mode",
    "semantic_identity",
    "semantic_manifest_identity",
    "embedding_provider",
    "embedding_model",
    "embedding_dimensions",
    "milvus_collection",
    "unit_set_identity",
)
RAG_ASSERTION_IDS = frozenset({
    "route_correct", "axes_correct", "reason_correct", "graph_path_correct", "rag_tool_once",
    "retrieved_gold", "selected_gold", "generation_visible_gold", "cited_gold",
    "answer_present", "answer_absent", "safe_fallback_answer", "required_answer_terms",
    "forbidden_terms_absent", "no_generation", "response_trace_consistent",
    "runtime_identity_complete", "provider_observed", "composer_support_valid",
    "answer_facts_exact_lower_bound",
})

AssertionStatus = Literal["passed", "failed", "not_observed"]
AssertionEffect = Literal["required", "advisory"]
GateStatus = Literal["passed", "failed", "inconclusive"]


class RAGEvalContractError(ValueError):
    """catalog、运行身份或 completed artifact 违反闭集合同。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def canonical_hash(payload: Any) -> str:
    """统一 identity 计算，避免 YAML key 顺序或格式化导致漂移。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RAGScenario:
    """一条业务 RAG 题面的 gold、四轴和 assertion policy。"""

    scenario_id: str
    classification: Literal["core", "diagnostic", "external_dev", "external_heldout"]
    question: str
    user_role: str
    expected_axes: tuple[str, str, str, str]
    expected_reason: str
    expected_document_keys: tuple[str, ...]
    required_answer_terms: tuple[str, ...]
    forbidden_public_terms: tuple[str, ...]
    required_assertions: tuple[str, ...]
    advisory_assertions: tuple[str, ...]
    question_type: str = "business"
    source_types: tuple[str, ...] = ()
    document_cardinality: str = "not_applicable"
    # ★ difficulty 描述题目本身，classification 描述业务/数据分区；二者不能混用。
    # 例如 held-out 里也同时存在 basic/core/hard，不能把“没看过”误叫成“困难”。
    difficulty: Literal["basic", "core", "hard", "not_applicable"] = "not_applicable"
    gold_answer: str = ""
    answer_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (self.scenario_id, self.question, self.user_role, self.expected_reason)
        if any(not item.strip() for item in values):
            raise RAGEvalContractError("rag_scenario_invalid", "Scenario 必填文本不能为空")
        if len(set(self.required_assertions + self.advisory_assertions)) != len(
            self.required_assertions + self.advisory_assertions
        ):
            raise RAGEvalContractError("rag_scenario_invalid", "assertion ID 重复或 effect 冲突")
        if self.classification not in {"core", "diagnostic", "external_dev", "external_heldout"}:
            raise RAGEvalContractError("rag_scenario_invalid", "classification 未登记")
        if self.difficulty not in {"basic", "core", "hard", "not_applicable"}:
            raise RAGEvalContractError("rag_scenario_invalid", "difficulty 未登记")
        if len(self.expected_axes) != 4:
            raise RAGEvalContractError("rag_scenario_invalid", "expected_axes 必须恰好包含四轴")
        if not self.required_assertions:
            raise RAGEvalContractError("rag_scenario_invalid", "每题至少有一条 required assertion")


@dataclass(frozen=True)
class RAGScenarioCatalog:
    """题面单一事实源；selector 只能引用，不能复制题面。"""

    contract_version: str
    scenarios: tuple[RAGScenario, ...]
    catalog_identity: str

    def by_id(self) -> dict[str, RAGScenario]:
        return {item.scenario_id: item for item in self.scenarios}


@dataclass(frozen=True)
class RAGSelector:
    """只声明选择集合和 replicate protocol。"""

    selector_id: str
    selected_scenario_ids: tuple[str, ...]
    replicate_count: int
    selector_identity: str


@dataclass(frozen=True)
class RAGResolvedRuntime:
    """真实运行到底用了什么，而不是命令行声称用了什么。"""

    runtime_family: str
    answer_flow_identity: str
    composer_identity: str
    model: str
    provider: str
    timeout_seconds: float
    retry_count: int
    release_identity: str
    corpus_identity: str
    retrieval_adapter_identity: str
    retrieval_recipe_identity: str
    authorization_policy_identity: str
    release_outbound_policy_identity: str
    generation_outbound_policy_identity: str
    caller_fixture_identity: str
    route_policy_identity: str = "deterministic-router-v1"
    # M44A additive fields：旧 lexical/business artifact 缺失时由 dataclass 默认表达不适用。
    retrieval_mode: str | None = None
    semantic_identity: str | None = None
    semantic_manifest_identity: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    milvus_collection: str | None = None
    unit_set_identity: str | None = None


@dataclass(frozen=True)
class RAGRunSpec:
    """一次授权范围的不可变快照。"""

    run_id: str
    catalog_identity: str
    selector_identity: str
    selected_scenario_ids: tuple[str, ...]
    replicate_count: int
    runtime: RAGResolvedRuntime
    assertion_plan: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]
    scorer_identity: str = "phase4-rag-funnel-scorer-v1"
    scenario_metadata: tuple[tuple[str, dict[str, Any]], ...] = ()

    @property
    def identity(self) -> str:
        return canonical_hash(asdict(self))


@dataclass(frozen=True)
class RAGExecutionEvidence:
    """★ 一次产品请求的共享答卷；所有 scorer/review 都只读此对象。"""

    scenario_id: str
    replicate: int
    trace_id: str
    status_code: int
    route: str
    execution_status: str
    answer_status: str
    safety_status: str
    reason_code: str
    answer: str | None
    graph_steps: tuple[str, ...]
    graph_invocation_count: int
    rag_tool_calls: int
    stage_document_keys: tuple[tuple[str, tuple[str, ...]], ...]
    stage_counts: tuple[tuple[str, int], ...]
    identities_redacted: bool
    citations: tuple[dict[str, Any], ...]
    docs_used: tuple[dict[str, Any], ...]
    rag_diagnostics: dict[str, Any]
    trace_runtime_identity: dict[str, Any]
    provider_attempts: tuple[dict[str, Any], ...]
    provider_usage: dict[str, int]
    response_trace_consistent: bool

    @property
    def evidence_ref(self) -> str:
        return f"execution:{self.scenario_id}:{self.replicate}:{self.trace_id}"


@dataclass(frozen=True)
class RAGAssertionResult:
    """一条 assertion 对共享答卷的判断。"""

    scenario_id: str
    replicate: int
    assertion_id: str
    effect: AssertionEffect
    status: AssertionStatus
    reason: str
    evidence_ref: str


@dataclass(frozen=True)
class RAGGate:
    """required assertions 的独立视图。"""

    status: GateStatus
    passed: int
    failed: int
    not_observed: int


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise RAGEvalContractError("rag_catalog_invalid", f"{key} 不能为空")
    return value


def load_rag_catalog(path: Path) -> RAGScenarioCatalog:
    """读取并冻结 canonical RAG catalog。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("contract_version") != RAG_E2E_CONTRACT_VERSION:
        raise RAGEvalContractError("rag_catalog_invalid", "contract_version 不匹配")
    scenarios: list[RAGScenario] = []
    for raw in payload.get("scenarios") or []:
        if not isinstance(raw, dict):
            raise RAGEvalContractError("rag_catalog_invalid", "scenarios 必须是对象列表")
        assertions = raw.get("assertions") or {}
        scenarios.append(
            RAGScenario(
                scenario_id=_required_text(raw, "scenario_id"),
                classification=_required_text(raw, "classification"),  # type: ignore[arg-type]
                question=_required_text(raw, "question"),
                user_role=_required_text(raw, "user_role"),
                expected_axes=tuple(raw.get("expected_axes") or ()),  # type: ignore[arg-type]
                expected_reason=_required_text(raw, "expected_reason"),
                expected_document_keys=tuple(str(item) for item in raw.get("expected_document_keys") or ()),
                required_answer_terms=tuple(str(item) for item in raw.get("required_answer_terms") or ()),
                forbidden_public_terms=tuple(str(item) for item in raw.get("forbidden_public_terms") or ()),
                required_assertions=tuple(str(item) for item in assertions.get("required") or ()),
                advisory_assertions=tuple(str(item) for item in assertions.get("advisory") or ()),
                question_type=str(raw.get("question_type") or "business"),
                source_types=tuple(str(item) for item in raw.get("source_types") or ()),
                document_cardinality=str(raw.get("document_cardinality") or "not_applicable"),
                difficulty=str(raw.get("difficulty") or "not_applicable"),  # type: ignore[arg-type]
                gold_answer=str(raw.get("gold_answer") or ""),
                answer_facts=tuple(str(item) for item in raw.get("answer_facts") or ()),
            )
        )
    ids = [item.scenario_id for item in scenarios]
    if not scenarios or len(ids) != len(set(ids)):
        raise RAGEvalContractError("rag_catalog_invalid", "Scenario 为空或 ID 重复")
    unknown_assertions = {
        assertion
        for item in scenarios
        for assertion in item.required_assertions + item.advisory_assertions
        if assertion not in RAG_ASSERTION_IDS
    }
    if unknown_assertions:
        raise RAGEvalContractError("rag_assertion_unknown", f"未知 assertions: {sorted(unknown_assertions)}")
    identity = canonical_hash(
        {"contract_version": RAG_E2E_CONTRACT_VERSION, "scenarios": [asdict(item) for item in scenarios]}
    )
    return RAGScenarioCatalog(RAG_E2E_CONTRACT_VERSION, tuple(scenarios), identity)


def load_rag_selector(path: Path, catalog: RAGScenarioCatalog) -> RAGSelector:
    """读取 selector，并拒绝未知题、重复题或非法 replicate。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RAGEvalContractError("rag_selector_invalid", "selector 必须是对象")
    selector_id = _required_text(payload, "selector_id")
    selected = tuple(str(item) for item in payload.get("selected_scenario_ids") or ())
    replicate_count = int(payload.get("replicate_count") or 0)
    if not selected or len(selected) != len(set(selected)) or replicate_count < 1:
        raise RAGEvalContractError("rag_selector_invalid", "selector 题集或 replicate 非法")
    unknown = set(selected) - set(catalog.by_id())
    if unknown:
        raise RAGEvalContractError("rag_selector_invalid", f"未知 Scenario: {sorted(unknown)}")
    identity = canonical_hash(
        {"selector_id": selector_id, "selected_scenario_ids": selected, "replicate_count": replicate_count}
    )
    return RAGSelector(selector_id, selected, replicate_count, identity)


def build_explicit_selector(
    *, scenario_ids: tuple[str, ...], replicate_count: int, catalog: RAGScenarioCatalog
) -> RAGSelector:
    """CLI 精确单题/多题选择，不复制 Scenario 题面。"""

    selected = tuple(scenario_ids)
    if not selected or len(selected) != len(set(selected)) or replicate_count < 1:
        raise RAGEvalContractError("rag_selector_invalid", "explicit scenario/replicate 非法")
    unknown = set(selected) - set(catalog.by_id())
    if unknown:
        raise RAGEvalContractError("rag_selector_invalid", f"未知 Scenario: {sorted(unknown)}")
    payload = {"selector_id": "explicit", "selected_scenario_ids": selected, "replicate_count": replicate_count}
    return RAGSelector("explicit", selected, replicate_count, canonical_hash(payload))


def artifact_payload(
    *,
    run_spec: RAGRunSpec,
    executions: tuple[RAGExecutionEvidence, ...],
    assertions: tuple[RAGAssertionResult, ...],
    gate: RAGGate,
) -> dict[str, Any]:
    """形成 completed artifact，并在返回前执行 closed-world 校验。"""

    expected = [
        (scenario_id, replicate)
        for scenario_id in run_spec.selected_scenario_ids
        for replicate in range(1, run_spec.replicate_count + 1)
    ]
    actual = [(item.scenario_id, item.replicate) for item in executions]
    if actual != expected or len(actual) != len(set(actual)):
        raise RAGEvalContractError("rag_artifact_execution_mismatch", "execution 不匹配或顺序漂移")
    assertion_keys = [(item.scenario_id, item.replicate, item.assertion_id) for item in assertions]
    if len(assertion_keys) != len(set(assertion_keys)):
        raise RAGEvalContractError("rag_artifact_assertion_mismatch", "assertion 重复")
    unsigned = {
        "format": RAG_E2E_ARTIFACT_FORMAT,
        "status": "completed",
        "run_spec": asdict(run_spec),
        "run_spec_identity": run_spec.identity,
        "executions": [asdict(item) for item in executions],
        "assertions": [asdict(item) for item in assertions],
        "gate": asdict(gate),
    }
    return {**unsigned, "artifact_identity": canonical_hash(unsigned)}


def validate_completed_artifact(payload: Mapping[str, Any]) -> None:
    """只读校验 completed artifact 的格式、identity 与闭集 execution。"""

    if payload.get("format") != RAG_E2E_ARTIFACT_FORMAT or payload.get("status") != "completed":
        raise RAGEvalContractError("rag_artifact_not_completed", "artifact 不是 completed v1")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload.get("artifact_identity") != canonical_hash(unsigned):
        raise RAGEvalContractError("rag_artifact_hash_mismatch", "artifact identity 不匹配")
    spec = payload.get("run_spec") or {}
    if not isinstance(spec, dict):
        raise RAGEvalContractError("rag_artifact_identity_mismatch", "run_spec 必须是对象")
    if payload.get("run_spec_identity") != canonical_hash(spec):
        raise RAGEvalContractError("rag_artifact_identity_mismatch", "RunSpec identity 不匹配")
    expected = [
        (scenario_id, replicate)
        for scenario_id in spec.get("selected_scenario_ids") or []
        for replicate in range(1, int(spec.get("replicate_count") or 0) + 1)
    ]
    actual = [(item.get("scenario_id"), item.get("replicate")) for item in payload.get("executions") or []]
    if actual != expected or len(actual) != len(set(actual)):
        raise RAGEvalContractError("rag_artifact_execution_mismatch", "completed execution 闭集不匹配")
    assertion_plan = spec.get("assertion_plan") or []
    plan_by_scenario: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for item in assertion_plan:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise RAGEvalContractError("rag_artifact_assertion_mismatch", "assertion_plan 非法")
        plan_by_scenario[str(item[0])] = (tuple(item[1]), tuple(item[2]))
    expected_assertions = [
        (scenario_id, replicate, assertion_id, effect)
        for scenario_id, replicate in expected
        for effect, ids in (("required", plan_by_scenario.get(scenario_id, ((), ()))[0]), ("advisory", plan_by_scenario.get(scenario_id, ((), ()))[1]))
        for assertion_id in ids
    ]
    actual_assertions = [
        (item.get("scenario_id"), item.get("replicate"), item.get("assertion_id"), item.get("effect"))
        for item in payload.get("assertions") or []
    ]
    if actual_assertions != expected_assertions or len(actual_assertions) != len(set(actual_assertions)):
        raise RAGEvalContractError("rag_artifact_assertion_mismatch", "completed assertion 闭集不匹配")
    required_statuses = [
        item.get("status") for item in payload.get("assertions") or [] if item.get("effect") == "required"
    ]
    recomputed = {
        "status": "failed" if "failed" in required_statuses else "inconclusive" if "not_observed" in required_statuses else "passed",
        "passed": required_statuses.count("passed"),
        "failed": required_statuses.count("failed"),
        "not_observed": required_statuses.count("not_observed"),
    }
    if payload.get("gate") != recomputed:
        raise RAGEvalContractError("rag_artifact_gate_mismatch", "Gate 与 required assertions 不一致")
