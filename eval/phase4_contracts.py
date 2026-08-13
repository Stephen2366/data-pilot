"""Phase 4 `phase4-v1` 确定性 contract/security Eval family。

它与 M27 Text2SQL Eval 完全分离：每个 Scenario 只执行一次，ExecutionEvidence 与多条
typed assertion 共用同一份观察；completed artifact 必须通过 closed-world 对账后才能投影
required Gate。这里不调用 API、LLM、向量库，也不把安全 fixture 冒充 RAG 答案质量。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Mapping

from engine.governance import (
    DOCUMENT_AUTHORIZATION_POLICY_IDENTITY,
    OUTBOUND_POLICY_IDENTITY,
    OutboundRequest,
    authorize_document,
    decide_outbound,
    test_caller,
    unverified_request_caller,
)
from engine.rag.catalog import StagedCatalog
from engine.rag.evidence import (
    CitationDraft,
    EvidenceContractError,
    EvidenceLedger,
    allocate_citation_slot,
    make_document_evidence,
    validate_citations,
)
from engine.rag.release import (
    G3Approval,
    PHASE4_CONTRACT_VERSION,
    ReleaseError,
    activate_release,
    build_candidate_release,
    load_active_release,
    rollback_active_release,
)

AssertionStatus = Literal["passed", "failed", "not_observed"]
CALLER_FIXTURE_IDENTITY = "phase4-contract-callers-v1"
RUNTIME_IDENTITY = "phase4-deterministic-local-v1"


class Phase4ContractError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _hash(payload: Mapping[str, Any] | list[Any]) -> str:
    """生成 contract/artifact 的规范 SHA-256 identity。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Phase4Scenario:
    """一个确定性 contract/security 场景及其 closed-world assertions。"""

    scenario_id: str
    assertion_ids: tuple[str, ...]
    required: bool = True


SCENARIOS: tuple[Phase4Scenario, ...] = (
    Phase4Scenario("caller_role_tamper", ("caller_untrusted", "document_denied")),
    Phase4Scenario("acl_non_disclosure", ("admin_not_super_reader", "deny_projection_safe")),
    Phase4Scenario("outbound_missing_policy", ("knowledge_outbound_denied", "fallback_explicit")),
    Phase4Scenario("evidence_stage_guard", ("generation_requires_recheck",)),
    Phase4Scenario("citation_invalid", ("forged_slot_rejected",)),
    Phase4Scenario("candidate_publish", ("candidate_reloadable", "candidate_not_active")),
    Phase4Scenario("startup_active_load", ("active_reloadable",)),
    Phase4Scenario("rollback_safety", ("missing_previous_rejected",)),
)


def contract_identity(scenarios: tuple[Phase4Scenario, ...] = SCENARIOS) -> str:
    """冻结 Scenario 与 assertion closed-world 集合。"""

    return _hash({"contract_version": PHASE4_CONTRACT_VERSION, "scenarios": [asdict(item) for item in scenarios]})


@dataclass(frozen=True)
class Phase4ExecutionEvidence:
    """一次 Scenario 执行产生、由多条 assertion 共享的安全证据。"""

    scenario_id: str
    replicate: int
    observed: bool
    outcome: str
    facts: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class Phase4AssertionResult:
    """一条 typed assertion 对共享执行证据的投影。"""

    scenario_id: str
    assertion_id: str
    status: AssertionStatus
    evidence_ref: str


@dataclass(frozen=True)
class Phase4Artifact:
    """通过 closed-world 校验后才能进入 required Gate 的 completed artifact。"""

    artifact_identity: str
    contract_version: str
    contract_identity: str
    authorization_policy_identity: str
    outbound_policy_identity: str
    caller_fixture_identity: str
    runtime_identity: str
    corpus_identity: str
    release_identity: str
    selected_scenario_ids: tuple[str, ...]
    execution_evidence: tuple[Phase4ExecutionEvidence, ...]
    assertion_results: tuple[Phase4AssertionResult, ...]
    lifecycle_status: str = "completed"

    def unsigned_payload(self) -> dict[str, Any]:
        """返回参与 artifact identity 的全部 completed 事实。"""

        return {
            "contract_version": self.contract_version,
            "contract_identity": self.contract_identity,
            "authorization_policy_identity": self.authorization_policy_identity,
            "outbound_policy_identity": self.outbound_policy_identity,
            "caller_fixture_identity": self.caller_fixture_identity,
            "runtime_identity": self.runtime_identity,
            "corpus_identity": self.corpus_identity,
            "release_identity": self.release_identity,
            "selected_scenario_ids": list(self.selected_scenario_ids),
            "execution_evidence": [asdict(item) for item in self.execution_evidence],
            "assertion_results": [asdict(item) for item in self.assertion_results],
            "lifecycle_status": self.lifecycle_status,
        }

    def to_dict(self) -> dict[str, Any]:
        """附加 artifact identity，供后续持久化/报告投影。"""

        return {**self.unsigned_payload(), "artifact_identity": self.artifact_identity}


@dataclass(frozen=True)
class Phase4Gate:
    """required assertion 的 passed/failed/inconclusive 汇总。"""

    status: Literal["passed", "failed", "inconclusive"]
    passed: int
    failed: int
    not_observed: int


def _result(
    *, scenario: Phase4Scenario, evidence: Phase4ExecutionEvidence, checks: Mapping[str, bool]
) -> tuple[Phase4AssertionResult, ...]:
    """把同一次 ExecutionEvidence 投影成该题的全部 typed assertions。"""

    if set(checks) != set(scenario.assertion_ids):
        raise Phase4ContractError("executor_assertion_mismatch", f"{scenario.scenario_id} executor 输出不完整")
    evidence_ref = f"execution:{scenario.scenario_id}:{evidence.replicate}"
    return tuple(
        Phase4AssertionResult(
            scenario_id=scenario.scenario_id,
            assertion_id=assertion_id,
            status=("passed" if checks[assertion_id] else "failed") if evidence.observed else "not_observed",
            evidence_ref=evidence_ref,
        )
        for assertion_id in scenario.assertion_ids
    )


def _entry_for(catalog: StagedCatalog, role: str):
    """为安全 Scenario 选择当前 catalog 中的真实角色受限 entry。"""

    for entry in catalog.entries:
        if role in entry.allowed_roles:
            return entry
    raise Phase4ContractError("fixture_missing", f"catalog 没有 {role} fixture")


def _execute_scenario(
    scenario: Phase4Scenario,
    *,
    staged: StagedCatalog,
    candidate_release_identity: str,
    root: Path,
) -> tuple[Phase4ExecutionEvidence, tuple[Phase4AssertionResult, ...]]:
    """每个 Scenario 恰好执行一次并返回共享证据与断言。"""

    facts: dict[str, Any] = {}
    checks: dict[str, bool]

    if scenario.scenario_id == "caller_role_tamper":
        caller = unverified_request_caller(caller_id="phase4-request", claimed_roles={"admin"})
        entry = _entry_for(staged, "admin")
        decision = authorize_document(
            caller=caller, entry=entry, purpose=entry.purposes[0], phase="pre_selection"
        )
        facts = {"trust_level": caller.trust_level, "reason_code": decision.reason_code}
        checks = {"caller_untrusted": not caller.may_authorize_documents, "document_denied": not decision.allowed}
    elif scenario.scenario_id == "acl_non_disclosure":
        entry = _entry_for(staged, "customer_service")
        decision = authorize_document(
            caller=test_caller(caller_id="phase4-admin", roles={"admin"}),
            entry=entry, purpose=entry.purposes[0], phase="pre_selection",
        )
        projection = decision.public_projection()
        rendered = json.dumps(projection, ensure_ascii=False)
        facts = {"allowed": decision.allowed, "public_reason": projection["reason_code"]}
        checks = {
            "admin_not_super_reader": not decision.allowed,
            "deny_projection_safe": all(value not in rendered for value in (entry.document_key, entry.title, entry.content)),
        }
    elif scenario.scenario_id == "outbound_missing_policy":
        decision = decide_outbound(
            OutboundRequest(
                receiver="qwen_chat", node_purpose="answer_composer", data_class="document_evidence",
                fields=frozenset({"content"}), fallback_available=True,
            )
        )
        facts = {"reason_code": decision.reason_code, "fallback": decision.fallback_action}
        checks = {
            "knowledge_outbound_denied": not decision.allowed and decision.reason_code == "policy_missing",
            "fallback_explicit": decision.fallback_action == "continue_locally",
        }
    elif scenario.scenario_id in {"evidence_stage_guard", "citation_invalid"}:
        entry = _entry_for(staged, "customer_service")
        caller = test_caller(caller_id="phase4-cs", roles={"customer_service"})
        selected_auth = authorize_document(
            caller=caller, entry=entry, purpose=entry.purposes[0], phase="pre_selection"
        )
        evidence = make_document_evidence(
            run_id=f"phase4-{scenario.scenario_id}", release_identity=candidate_release_identity,
            entry=entry, purpose=entry.purposes[0], authorization=selected_auth, runtime_ref="phase4-fixture",
        )
        ledger = EvidenceLedger.from_candidates(run_id=evidence.ref.run_id, evidence=(evidence,))
        ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
        if scenario.scenario_id == "evidence_stage_guard":
            try:
                ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible")
                rejected = False
            except EvidenceContractError:
                rejected = True
            facts = {"without_pre_generation_rejected": rejected}
            checks = {"generation_requires_recheck": rejected}
        else:
            generation_auth = authorize_document(
                caller=caller, entry=entry, purpose=entry.purposes[0], phase="pre_generation"
            )
            ledger = ledger.transition(
                evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible",
                generation_authorizations={evidence.ref.evidence_id: generation_auth},
            )
            slot = allocate_citation_slot(run_id=evidence.ref.run_id, claim_ref="claim", ordinal=1)
            draft = CitationDraft(evidence.ref.run_id, "forged", "claim", evidence.ref.evidence_id, entry.anchor)
            try:
                validate_citations(
                    ledger=ledger, slots=(slot,), drafts=(draft,),
                    current_entries={(entry.document_key, entry.revision): entry},
                    generation_authorizations={evidence.ref.evidence_id: generation_auth},
                )
                rejected = False
            except EvidenceContractError:
                rejected = True
            facts = {"forged_slot_rejected": rejected}
            checks = {"forged_slot_rejected": rejected}
    elif scenario.scenario_id == "candidate_publish":
        candidate = build_candidate_release(staged=staged, root=root)
        state = root / "active.json"
        facts = {"candidate_release_identity": candidate.release_identity, "pointer_exists": state.exists()}
        checks = {
            "candidate_reloadable": candidate.release_identity == candidate_release_identity,
            "candidate_not_active": not state.exists(),
        }
    elif scenario.scenario_id == "startup_active_load":
        candidate = build_candidate_release(staged=staged, root=root)
        activate_release(
            bundle=candidate, staged=staged,
            approval=G3Approval("A", "phase4-contract-fixture", "2026-08-13"), root=root,
        )
        pointer, active = load_active_release(root=root)
        facts = {"current": pointer.current_release_identity, "loaded": active.release_identity}
        checks = {"active_reloadable": pointer.current_release_identity == active.release_identity}
    elif scenario.scenario_id == "rollback_safety":
        candidate = build_candidate_release(staged=staged, root=root)
        activate_release(
            bundle=candidate, staged=staged,
            approval=G3Approval("A", "phase4-contract-fixture", "2026-08-13"), root=root,
        )
        try:
            rollback_active_release(
                current_authority=staged,
                approval=G3Approval("A", "phase4-contract-fixture", "2026-08-13"), root=root,
            )
            rejected = False
        except ReleaseError as exc:
            rejected = exc.reason_code == "rollback_previous_missing"
        facts = {"missing_previous_rejected": rejected}
        checks = {"missing_previous_rejected": rejected}
    else:  # pragma: no cover - catalog 是 closed-world 常量，保留防御性分支。
        raise Phase4ContractError("scenario_unknown", scenario.scenario_id)

    evidence = Phase4ExecutionEvidence(
        scenario_id=scenario.scenario_id,
        replicate=1,
        observed=True,
        outcome="completed",
        facts=tuple(sorted(facts.items())),
    )
    return evidence, _result(scenario=scenario, evidence=evidence, checks=checks)


def run_phase4_contract_suite(*, staged: StagedCatalog, root: Path) -> Phase4Artifact:
    """运行全部 required fixture；调用方为每次 run 提供隔离目录。"""

    candidate = build_candidate_release(staged=staged, root=root / "candidate")
    evidence_items: list[Phase4ExecutionEvidence] = []
    results: list[Phase4AssertionResult] = []
    for scenario in SCENARIOS:
        evidence, scenario_results = _execute_scenario(
            scenario,
            staged=staged,
            candidate_release_identity=candidate.release_identity,
            root=root / "scenarios" / scenario.scenario_id,
        )
        evidence_items.append(evidence)
        results.extend(scenario_results)
    artifact = Phase4Artifact(
        artifact_identity="",
        contract_version=PHASE4_CONTRACT_VERSION,
        contract_identity=contract_identity(),
        authorization_policy_identity=DOCUMENT_AUTHORIZATION_POLICY_IDENTITY,
        outbound_policy_identity=OUTBOUND_POLICY_IDENTITY,
        caller_fixture_identity=CALLER_FIXTURE_IDENTITY,
        runtime_identity=RUNTIME_IDENTITY,
        corpus_identity=staged.corpus_identity,
        release_identity=candidate.release_identity,
        selected_scenario_ids=tuple(item.scenario_id for item in SCENARIOS),
        execution_evidence=tuple(evidence_items),
        assertion_results=tuple(results),
    )
    artifact = replace(artifact, artifact_identity=_hash(artifact.unsigned_payload()))
    validate_completed_artifact(
        artifact,
        expected_corpus_identity=staged.corpus_identity,
        expected_release_identity=candidate.release_identity,
    )
    return artifact


def validate_completed_artifact(
    artifact: Phase4Artifact,
    *,
    scenarios: tuple[Phase4Scenario, ...] = SCENARIOS,
    expected_corpus_identity: str | None = None,
    expected_release_identity: str | None = None,
) -> None:
    """closed-world 校验：selected/evidence/assertion/identity 必须恰好一致。"""

    if artifact.lifecycle_status != "completed" or artifact.contract_version != PHASE4_CONTRACT_VERSION:
        raise Phase4ContractError("artifact_contract_mismatch", "artifact lifecycle/contract 不匹配")
    if artifact.contract_identity != contract_identity(scenarios):
        raise Phase4ContractError("artifact_contract_mismatch", "contract identity 不匹配")
    if (
        artifact.authorization_policy_identity != DOCUMENT_AUTHORIZATION_POLICY_IDENTITY
        or artifact.outbound_policy_identity != OUTBOUND_POLICY_IDENTITY
    ):
        raise Phase4ContractError("artifact_policy_mismatch", "policy identity 不匹配")
    if artifact.caller_fixture_identity != CALLER_FIXTURE_IDENTITY:
        raise Phase4ContractError("artifact_caller_mismatch", "caller fixture identity 不匹配")
    if artifact.runtime_identity != RUNTIME_IDENTITY:
        raise Phase4ContractError("artifact_runtime_mismatch", "runtime identity 不匹配")
    if not artifact.corpus_identity or (
        expected_corpus_identity is not None and artifact.corpus_identity != expected_corpus_identity
    ):
        raise Phase4ContractError("artifact_corpus_mismatch", "corpus identity 不匹配")
    if not artifact.release_identity or (
        expected_release_identity is not None and artifact.release_identity != expected_release_identity
    ):
        raise Phase4ContractError("artifact_release_mismatch", "release identity 不匹配")
    expected_scenarios = tuple(item.scenario_id for item in scenarios)
    if artifact.selected_scenario_ids != expected_scenarios or len(set(artifact.selected_scenario_ids)) != len(expected_scenarios):
        raise Phase4ContractError("artifact_scenario_mismatch", "selected Scenario 缺失、额外、重复或乱序")
    evidence_keys = [(item.scenario_id, item.replicate) for item in artifact.execution_evidence]
    expected_evidence = [(scenario_id, 1) for scenario_id in expected_scenarios]
    if evidence_keys != expected_evidence or len(set(evidence_keys)) != len(evidence_keys):
        raise Phase4ContractError("artifact_execution_mismatch", "ExecutionEvidence 必须每题恰好一份")
    expected_assertions = [
        (scenario.scenario_id, assertion_id) for scenario in scenarios for assertion_id in scenario.assertion_ids
    ]
    actual_assertions = [(item.scenario_id, item.assertion_id) for item in artifact.assertion_results]
    if actual_assertions != expected_assertions or len(set(actual_assertions)) != len(actual_assertions):
        raise Phase4ContractError("artifact_assertion_mismatch", "assertion 缺失、额外、重复或乱序")
    if any(item.evidence_ref != f"execution:{item.scenario_id}:1" for item in artifact.assertion_results):
        raise Phase4ContractError("artifact_evidence_ref_mismatch", "assertion 未引用同题唯一执行证据")
    if _hash(artifact.unsigned_payload()) != artifact.artifact_identity:
        raise Phase4ContractError("artifact_hash_mismatch", "artifact identity 校验失败")


def project_required_gate(artifact: Phase4Artifact) -> Phase4Gate:
    validate_completed_artifact(artifact)
    statuses = [item.status for item in artifact.assertion_results]
    passed = statuses.count("passed")
    failed = statuses.count("failed")
    not_observed = statuses.count("not_observed")
    status: Literal["passed", "failed", "inconclusive"]
    if failed:
        status = "failed"
    elif not_observed:
        status = "inconclusive"
    else:
        status = "passed"
    return Phase4Gate(status, passed, failed, not_observed)
