"""M37 sequence Eval：成功 turn → 一次 follow-up → 新 run Evidence。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from threading import Barrier, Lock
from typing import Literal

from engine.governance import demo_caller
from engine.harness.adapters import RAGToolAdapter
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.graph import HarnessRuntime
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.turn import AgentTurnResult, TurnRequest, run_turn
from engine.rag.answer_flow import RAGAnswerFlow
from engine.rag.evidence import EvidenceRef
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import load_active_release

FOLLOW_UP_CONTRACT_VERSION = "phase4-harness-followup-v1"
ASSERTION_IDS = (
    "sequence_closed",
    "graph_tool_budget",
    "retrieval_policy",
    "new_run_evidence",
    "safe_terminal",
)


@dataclass(frozen=True)
class FollowUpScenario:
    """每个 sequence 只改变一个复用/失效/lifecycle 条件。"""

    scenario_id: str
    kind: Literal[
        "sql", "business_reuse", "requirement_change", "revision_change",
        "acl_change", "external", "wrong_owner", "invalid_delta", "budget_replay", "concurrent"
    ]


SCENARIOS = (
    FollowUpScenario("sql_always_requeries", "sql"),
    FollowUpScenario("business_same_evidence_rehydrates", "business_reuse"),
    FollowUpScenario("business_requirement_change_retrieves", "requirement_change"),
    FollowUpScenario("business_revision_change_retrieves", "revision_change"),
    FollowUpScenario("business_acl_change_denies", "acl_change"),
    FollowUpScenario("external_always_retrieves", "external"),
    FollowUpScenario("wrong_owner_pregraph_rejected", "wrong_owner"),
    FollowUpScenario("invalid_delta_pregraph_rejected", "invalid_delta"),
    FollowUpScenario("follow_up_budget_replay_rejected", "budget_replay"),
    FollowUpScenario("concurrent_single_follow_up", "concurrent"),
)


@dataclass(frozen=True)
class FollowUpExecutionEvidence:
    """同一真实 turn 的安全投影；不保存问题、字段值、正文、answer 或 rows。"""

    sequence_id: str
    turn_id: str
    turn_index: int
    turn_action: str
    graph_invocation_count: int
    route: str
    reason_code: str
    safety_status: str
    top_level_tool_count: int
    knowledge_retrieval_count: int
    validity_decision: str | None
    validity_reason: str | None
    old_evidence_id_reused: bool
    new_evidence_run_matches: bool
    version_before: int | None
    version_after: int | None


@dataclass(frozen=True)
class FollowUpAssertion:
    """一条 sequence × contract assertion 的确定性判定。"""

    sequence_id: str
    assertion_id: str
    status: Literal["passed", "failed"]


@dataclass(frozen=True)
class HarnessFollowUpArtifact:
    """M37 closed-world Eval 的完整、可校验交付物。"""

    contract_version: str
    selected_sequence_ids: tuple[str, ...]
    execution_evidence: tuple[FollowUpExecutionEvidence, ...]
    assertions: tuple[FollowUpAssertion, ...]
    artifact_identity: str


class _SQLTool:
    """每次执行都签发当前 run 的不同 SQL Evidence。"""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = Lock()

    def run(self, request: HarnessRequest) -> ToolObservation:
        with self._lock:
            self.calls += 1
            ordinal = self.calls
        ref = EvidenceRef(
            request.run_id, f"sql-{request.run_id}-{ordinal}", "sql", "eval-db",
            f"queried-{ordinal}", f"fingerprint-{ordinal}", "sql-result"
        )
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="sql",
            evidence_refs=(ref.audit_projection(),), diagnostics={"result_fingerprint": ref.content_identity},
        )


def _request(question: str, run_id: str, *, role: str, owner: str = "eval-owner", enabled: bool = False) -> HarnessRequest:
    """构造只含安全 caller 与本轮开关的 Eval 请求。"""

    return HarnessRequest(
        question=question,
        run_id=run_id,
        caller=demo_caller(caller_id=owner, roles=(role,)),
        active_sql_role=role,
        enable_bounded_follow_up=enabled,
    )


def _rag_adapter(kind: str, refs: tuple[dict[str, str], ...] = ()) -> RAGToolAdapter:
    """按 scenario 构造当前业务 release 的正常/变更/ACL runtime。"""

    if kind not in {"revision_change", "acl_change"}:
        return RAGToolAdapter(knowledge_runtime_kind="external_profile" if kind == "external" else "business_release")
    pointer, bundle = load_active_release()
    authorities = {item["authority_identity"] for item in refs}
    if kind == "revision_change":
        entries = tuple(
            replace(
                entry,
                content=entry.content + "\nM37 current revision.",
                content_identity=entry.content_identity + "-m37",
            )
            if entry.authority_ref in authorities else entry
            for entry in bundle.entries
        )
        bundle = replace(bundle, release_identity=bundle.release_identity + "-m37", entries=entries)
    else:
        entries = tuple(
            replace(entry, public=False, allowed_roles=frozenset({"admin"}))
            if entry.authority_ref in authorities else entry
            for entry in bundle.entries
        )
        bundle = replace(bundle, entries=entries)
    loader = lambda: (pointer, bundle)
    flow = RAGAnswerFlow(knowledge_tool=KnowledgeTool(active_loader=loader), active_loader=loader)
    return RAGToolAdapter(answer_flow=flow, knowledge_runtime_kind="business_release")


def _project(
    scenario_id: str,
    turn_id: str,
    index: int,
    turn: AgentTurnResult,
    *,
    old_ids: frozenset[str] = frozenset(),
) -> FollowUpExecutionEvidence:
    """把一次真实 turn 投影为断言共享的安全证据，不复制业务载荷。"""

    observation = turn.result.observation
    refs = tuple(observation.evidence_refs) if observation else ()
    diagnostics = observation.diagnostics if observation else {}
    validity = diagnostics.get("evidence_validity", {})
    lifecycle = turn.lifecycle
    return FollowUpExecutionEvidence(
        sequence_id=scenario_id,
        turn_id=turn_id,
        turn_index=index,
        turn_action=turn.turn_action,
        graph_invocation_count=turn.graph_invocation_count,
        route=turn.result.route,
        reason_code=turn.result.reason_code,
        safety_status=turn.result.safety_status,
        top_level_tool_count=1 if observation is not None else 0,
        knowledge_retrieval_count=int(diagnostics.get("knowledge_tool_calls", 0)),
        validity_decision=validity.get("decision"),
        validity_reason=validity.get("reason"),
        old_evidence_id_reused=any(item.get("evidence_id") in old_ids for item in refs),
        new_evidence_run_matches=all(item.get("run_id") == turn_id for item in refs) if refs else False,
        version_before=lifecycle.version_before if lifecycle else None,
        version_after=lifecycle.version_after if lifecycle else None,
    )


def _run_sequence(scenario: FollowUpScenario) -> list[FollowUpExecutionEvidence]:
    """执行一条完整序列；并发场景仍由同一 checkpoint 决定唯一赢家。"""

    manager = ThreadCheckpointManager()
    sql = _SQLTool()
    is_sql = scenario.kind in {"sql", "wrong_owner", "invalid_delta", "budget_replay", "concurrent"}
    role = "ops" if is_sql else "customer_service"
    question = "各渠道订单量是多少？" if is_sql else "质量问题退款规则如何处理？"
    initial_rag_kind = "external" if scenario.kind == "external" else "business_reuse"
    runtime = HarnessRuntime(sql_tool=sql, rag_tool=_rag_adapter(initial_rag_kind))
    initial = run_turn(
        request=TurnRequest(_request(question, "initial", role=role, enabled=True)),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    if initial.thread is None or initial.result.observation is None:
        raise ValueError(f"{scenario.scenario_id} 未形成 follow-up-ready")
    evidence = [_project(scenario.scenario_id, "initial", 1, initial)]
    old_refs = tuple(initial.result.observation.evidence_refs)
    old_ids = frozenset(item["evidence_id"] for item in old_refs)
    action = "adjust_sql_scope" if is_sql else (
        "ask_related_evidence" if scenario.kind == "requirement_change" else "explain_same_evidence"
    )
    fields = {"time_range": "2026年7月", "group_by": "商品"} if is_sql else (
        {"detail": "质量问题退款的补充材料"} if scenario.kind == "requirement_change" else {"style": "通俗说明"}
    )

    def follow(turn_id: str, *, owner: str = "eval-owner", payload: dict[str, str] | None = None):
        """用初始响应签发的 spec/version 发起一次受控追问。"""

        return run_turn(
            request=TurnRequest(
                _request("follow-up", turn_id, role=role, owner=owner),
                thread_id=initial.thread.thread_id,
                expected_version=initial.thread.checkpoint_version,
                follow_up_action=action,
                follow_up_fields=payload or fields,
            ),
            runtime=HarnessRuntime(sql_tool=sql, rag_tool=_rag_adapter(scenario.kind, old_refs)),
            checkpoint_manager=manager,
        )

    if scenario.kind == "wrong_owner":
        evidence.append(_project(scenario.scenario_id, "intruder", 2, follow("intruder", owner="intruder"), old_ids=old_ids))
    elif scenario.kind == "invalid_delta":
        evidence.append(_project(
            scenario.scenario_id, "invalid", 2,
            follow("invalid", payload={**fields, "route": "rag"}), old_ids=old_ids
        ))
    elif scenario.kind == "concurrent":
        barrier = Barrier(2)

        def compete(turn_id: str):
            """让两个候选同时越过 barrier，真实竞争同一原子 claim。"""

            barrier.wait()
            return turn_id, follow(turn_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(compete, ("candidate-a", "candidate-b")))
        for index, (turn_id, turn) in enumerate(sorted(outcomes), start=2):
            evidence.append(_project(scenario.scenario_id, turn_id, index, turn, old_ids=old_ids))
    else:
        accepted = follow("follow")
        evidence.append(_project(scenario.scenario_id, "follow", 2, accepted, old_ids=old_ids))
        if scenario.kind == "budget_replay":
            evidence.append(_project(scenario.scenario_id, "replay", 3, follow("replay"), old_ids=old_ids))
    return evidence


def run_harness_followup_contracts(
    *, scenarios: tuple[FollowUpScenario, ...] = SCENARIOS
) -> HarnessFollowUpArtifact:
    """运行一次 closed-world family；所有 assertion 只读同组真实 ExecutionEvidence。"""

    executions: list[FollowUpExecutionEvidence] = []
    assertions: list[FollowUpAssertion] = []
    for scenario in scenarios:
        sequence = _run_sequence(scenario)
        executions.extend(sequence)
        after_initial = sequence[1:]
        accepted = [item for item in after_initial if item.turn_action == "follow_up"]
        rejected = [item for item in after_initial if item.turn_action == "rejected"]
        expected_retrieval = {
            "business_reuse": 0,
            "requirement_change": 1,
            "revision_change": 1,
            "external": 1,
            "acl_change": 0,
        }.get(scenario.kind)
        retrieval_ok = True if expected_retrieval is None else (
            bool(accepted) and accepted[0].knowledge_retrieval_count == expected_retrieval
        )
        checks = {
            "sequence_closed": [item.turn_index for item in sequence] == list(range(1, len(sequence) + 1)),
            "graph_tool_budget": len(accepted) <= 1
            and all(item.graph_invocation_count == 1 and item.top_level_tool_count <= 1 for item in accepted)
            and all(item.graph_invocation_count == 0 and item.top_level_tool_count == 0 for item in rejected),
            "retrieval_policy": retrieval_ok,
            "new_run_evidence": all(
                not item.old_evidence_id_reused
                and (item.new_evidence_run_matches or item.safety_status == "blocked")
                for item in accepted
            ),
            "safe_terminal": (
                scenario.kind not in {"wrong_owner", "invalid_delta", "budget_replay", "concurrent"}
                or bool(rejected)
            ) and not any(item.safety_status == "blocked" and item.top_level_tool_count for item in rejected),
        }
        assertions.extend(
            FollowUpAssertion(scenario.scenario_id, assertion_id, "passed" if checks[assertion_id] else "failed")
            for assertion_id in ASSERTION_IDS
        )

    unsigned = {
        "contract_version": FOLLOW_UP_CONTRACT_VERSION,
        "selected_sequence_ids": [item.scenario_id for item in scenarios],
        "execution_evidence": [asdict(item) for item in executions],
        "assertions": [asdict(item) for item in assertions],
    }
    artifact = HarnessFollowUpArtifact(
        contract_version=FOLLOW_UP_CONTRACT_VERSION,
        selected_sequence_ids=tuple(item.scenario_id for item in scenarios),
        execution_evidence=tuple(executions),
        assertions=tuple(assertions),
        artifact_identity=sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    )
    validate_completed_followup_artifact(artifact, scenarios=scenarios)
    return artifact


def validate_completed_followup_artifact(
    artifact: HarnessFollowUpArtifact,
    *,
    scenarios: tuple[FollowUpScenario, ...] = SCENARIOS,
) -> None:
    """拒绝漏 sequence/turn、重复执行、缺 assertion、旧 Evidence 注入或超预算。"""

    expected_ids = tuple(item.scenario_id for item in scenarios)
    if artifact.contract_version != FOLLOW_UP_CONTRACT_VERSION or artifact.selected_sequence_ids != expected_ids:
        raise ValueError("Harness follow-up artifact contract/sequence 不匹配")
    keys = [(item.sequence_id, item.turn_id) for item in artifact.execution_evidence]
    if len(keys) != len(set(keys)) or {item.sequence_id for item in artifact.execution_evidence} != set(expected_ids):
        raise ValueError("Harness follow-up execution 重复或缺 sequence")
    for sequence_id in expected_ids:
        turns = [item for item in artifact.execution_evidence if item.sequence_id == sequence_id]
        if [item.turn_index for item in turns] != list(range(1, len(turns) + 1)):
            raise ValueError("Harness follow-up execution 缺 turn")
        if sum(item.turn_action == "follow_up" for item in turns) > 1:
            raise ValueError("Harness follow-up 超过一次 accepted 预算")
        if any(item.old_evidence_id_reused for item in turns if item.turn_action == "follow_up"):
            raise ValueError("Harness follow-up 直接复用了旧 run Evidence id")
    expected_assertions = [(sid, aid) for sid in expected_ids for aid in ASSERTION_IDS]
    actual_assertions = [(item.sequence_id, item.assertion_id) for item in artifact.assertions]
    if actual_assertions != expected_assertions or any(item.status != "passed" for item in artifact.assertions):
        raise ValueError("Harness follow-up assertion 缺失、重复或未通过")
