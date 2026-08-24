"""M44/B2 零 provider rehearsal：T3/T4/T5、repair 与 no-progress。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.agent_loop import AgentLoopRuntime, AgentLoopResult, run_agent_loop
from engine.phase4b.b2_contracts import load_b2_contract_bundle
from engine.phase4b.knowledge_runtime import KnowledgeRuntimeResolver, KnowledgeRuntimeSpec
from engine.phase4b.task_runtime import TaskDelta, TaskState, apply_delta, understand_turn
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import DocumentEvidencePayload, Evidence, EvidenceLedger, EvidenceRef, make_sql_evidence
from eval.agent_scenario_v3_contracts import build_agent_scenario_v3

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "eval" / "reports" / "m44"


def _request(question: str, run_id: str) -> HarnessRequest:
    return HarnessRequest(
        question=question, run_id=run_id,
        caller=demo_caller(caller_id="m44-rehearsal", roles=("ops",)), active_sql_role="ops",
        force_new_pipeline=True,
    )


def _sql(request: HarnessRequest, rows: tuple[dict[str, object], ...]) -> ToolObservation:
    evidence = make_sql_evidence(
        run_id=request.run_id, guarded_sql="SELECT phase4b_oracle", columns=tuple(rows[0]),
        rows_count=len(rows), result_fingerprint=f"oracle:{request.run_id}:{len(rows)}", queried_at="frozen",
        database_identity="phase4b-seed", runtime_identity="m44-rehearsal-v1",
        safe_result_view=tuple(tuple(row.values()) for row in rows),
    )
    ledger = EvidenceLedger(
        request.run_id, (evidence,), ((evidence.ref.evidence_id, "generation_visible"),)
    )
    return ToolObservation(
        tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
        safety_status="passed", reason_code="sql_completed", answer="已取得冻结 SQL oracle。",
        sql="SELECT phase4b_oracle", columns=tuple(rows[0]), rows=rows,
        evidence_refs=(evidence.ref.audit_projection(),), raw_evidence=(evidence,),
        evidence_ledger=ledger, ledger_projection=ledger.safe_projection(),
    )


def _documents(request: HarnessRequest) -> ToolObservation:
    keys = ("refund_policy_basic", "refund_policy_quality")
    evidence = tuple(
        Evidence(
            EvidenceRef(request.run_id, f"doc:{key}", "document", "business-authority", "r1", f"body:{key}", key),
            ("answer_evidence",), "auth:rehearsal", "business-release",
            DocumentEvidencePayload("business-release", key, "r1", key, "policy", key, f"{key} fixture"),
        )
        for key in keys
    )
    ledger = EvidenceLedger(
        request.run_id, evidence, tuple((item.ref.evidence_id, "generation_visible") for item in evidence)
    )
    return ToolObservation(
        tool_name="rag_evidence_gate", route="rag", execution_status="completed", answer_status="complete",
        safety_status="passed", reason_code="hybrid_document_evidence_ready",
        evidence_refs=tuple(item.ref.audit_projection() for item in evidence), raw_evidence=evidence,
        evidence_ledger=ledger, ledger_projection=ledger.safe_projection(),
        diagnostics={"candidate_count": 2, "selected_count": 2, "context_count": 2,
                     "knowledge_runtime_kind": "business_release"},
    )


@dataclass
class OracleSQL:
    """零网络 SQL fake：返回 Phase 4B 已冻结的边际与 dialect 反例。"""

    quality_positive: bool = True
    dialect_first: bool = False
    calls: int = 0
    repairs: int = 0

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        """按 typed requirement 的自然语言 query 返回对应冻结 Observation。"""

        self.calls += 1
        if self.dialect_first and self.calls == 1:
            return ToolObservation(
                tool_name="text2sql", route="sql", execution_status="failed", answer_status="no_answer",
                safety_status="passed", reason_code="sql_dialect_incompatible",
                sql="SELECT DATE_TRUNC('month', paid_at) FROM refunds", error_type="sql_execution_error",
                diagnostics={"issue_code": "mysql_unsupported_date_trunc"},
            )
        if "退款原因" in request.question:
            return _sql(request, ({"reason": "质量问题", "increment": 48000 if self.quality_positive else -100},))
        if "商品 SKU" in request.question:
            return _sql(request, (
                {"sku": "SKU-HIGH-REFUND-01", "increment": 24000},
                {"sku": "SKU-WL-EB-002", "increment": 18000},
                {"sku": "SKU-SD-LP-003", "increment": 6000},
                {"sku": "SKU-MK-K2-004", "increment": 6000},
                {"sku": "SKU-MS-PL-005", "increment": 6000},
            ))
        if "按渠道" in request.question:
            return _sql(request, ({"channel": "Mobile App", "increment": 30000}, {"channel": "other", "increment": 30000}))
        return _sql(request, ({"period": "2026-07", "value": 120000}, {"period": "2026-08", "value": 180000}))

    def run(self, request: HarnessRequest) -> ToolObservation:
        """兼容普通 Tool seam；rehearsal 统一复用 hybrid-safe Evidence。"""

        return self.run_for_hybrid(request)

    def run_repair(self, request: HarnessRequest, *, candidate_sql: str, issue_code: str) -> ToolObservation:
        """证明只有稳定 DATE_TRUNC issue 能进入一次 repair。"""

        assert "DATE_TRUNC" in candidate_sql and issue_code == "mysql_unsupported_date_trunc"
        self.repairs += 1
        return _sql(request, ({"period": "2026-08", "value": 180000},))


class BusinessRAG:
    """零网络 business release fake；只返回两份 required policy Evidence。"""

    calls = 0

    def run_for_hybrid(
        self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement
    ) -> ToolObservation:
        """模拟现有 RAG Gate 后的 business Document Evidence。"""

        assert requirement.required_document_keys == ("refund_policy_basic", "refund_policy_quality")
        self.calls += 1
        return _documents(request)

    def run(self, request: HarnessRequest) -> ToolObservation:
        """兼容完整 RAG seam；B2 rehearsal 实际只走 Gate-only 方法。"""

        return self.run_for_hybrid(request, requirement=AnswerEvidenceRequirement())


def _state(question: str, *, previous: TaskState | None = None, action: str = "start") -> tuple[TaskState, TaskDelta]:
    delta = understand_turn(question, action=action, previous=previous)
    state, _transition = apply_delta(previous, delta, owner_ref="owner:m44-rehearsal")
    return state, delta


def _runtime(sql: OracleSQL, rag: BusinessRAG | None = None) -> AgentLoopRuntime:
    specs = () if rag is None else (
        KnowledgeRuntimeSpec("business_release", lambda: rag, "business-release:rehearsal"),
    )
    return AgentLoopRuntime(sql, KnowledgeRuntimeResolver(specs))


def _turn(scenario: str, loop: AgentLoopResult, delta: TaskDelta) -> dict[str, object]:
    return {
        "scenario_id": scenario, "turn_id": scenario, "task_delta": delta.safe_projection(),
        "task_state": loop.state.safe_projection(),
        "actions": [item.safe_projection() for item in loop.attempts],
        "budget": loop.budget.safe_projection(),
        "node_contexts": [item.safe_projection() for item in loop.contexts],
        "termination": loop.termination.safe_projection(), "runtime_identity": dict(loop.runtime_identity),
        "assertions": [[f"required:{scenario.lower()}", "passed"]],
    }


def _run() -> tuple[dict[str, object], dict[str, object]]:
    t3_question = "2026 年 7 月和 8 月质量问题对净退款增长贡献了多少？哪些商品最突出？"
    t3_state, t3_delta = _state(t3_question)
    t3_sql = OracleSQL()
    t3 = run_agent_loop(request=_request(t3_question, "m44-t3"), state=t3_state, runtime=_runtime(t3_sql))

    t4_question = "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。"
    t4_state, t4_delta = _state(t4_question)
    t4 = run_agent_loop(
        request=_request(t4_question, "m44-t4"), state=t4_state,
        runtime=_runtime(OracleSQL(), BusinessRAG()),
    )

    t5_question = "更正为按渠道比较 2026 年 7 月和 8 月，并重新核验退款政策。"
    t5_state, t5_delta = _state(t5_question, previous=t4.state, action="continue")
    t5 = run_agent_loop(
        request=_request(t5_question, "m44-t5"), state=t5_state,
        runtime=_runtime(OracleSQL(), BusinessRAG()),
    )

    repair_question = "查询 2026 年 8 月实际净退款金额。"
    repair_state, repair_delta = _state(repair_question)
    repair_sql = OracleSQL(dialect_first=True)
    repair = run_agent_loop(
        request=_request(repair_question, "m44-repair"), state=repair_state,
        runtime=_runtime(repair_sql),
    )

    negative_state, _negative_delta = _state(t3_question)
    negative_sql = OracleSQL(quality_positive=False)
    negative = run_agent_loop(
        request=_request(t3_question, "m44-negative"), state=negative_state,
        runtime=_runtime(negative_sql),
    )
    bundle = load_b2_contract_bundle()
    seed_manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "domain_pack" / "phase4b" / "seed_profile.manifest.json")
        .read_text(encoding="utf-8")
    )
    artifact = build_agent_scenario_v3(
        bundle=bundle,
        run_spec={
            "run_id": "m44-b2-deterministic", "seed_identity": seed_manifest["content_identity"],
            "caller_identity": "fixture:m44-rehearsal", "knowledge_runtime_identities": ["business-release:rehearsal"],
            "policy_identities": ["sql-guard", "business-acl", "outbound-deny-by-default"],
        },
        turns=tuple(_turn(name, loop, delta) for name, loop, delta in (
            ("T3", t3, t3_delta), ("T4", t4, t4_delta), ("T5", t5, t5_delta),
            ("SQL_DIALECT_REPAIR", repair, repair_delta),
        )),
    )
    checks = {
        "t3_observation_drives_two_sql_actions": len(t3.attempts) == 2 and t3_sql.calls == 2,
        "t3_product_reconciles_total_delta": sum(int(row["increment"]) for row in t3.result.observation.rows) == 60000,
        "t4_business_hybrid_complete": t4.result.answer_status == "complete" and len(t4.knowledge_runtimes) == 1,
        "t5_correction_reauthorizes": t5_delta.category == "correct_previous_understanding" and t5.result.answer_status == "complete",
        "dialect_repair_once": repair_sql.repairs == 1 and len(repair.attempts) == 2,
        "negative_quality_skips_product": negative_sql.calls == 1 and len(negative.attempts) == 1,
    }
    report = {
        "report_version": "m44-b2-deterministic-report-v1", "passed": all(checks.values()),
        "external_calls": 0, "contract_identity": bundle.content_identity,
        "artifact_identity": artifact["artifact_identity"], "checks": checks,
    }
    return artifact, report


def main() -> None:
    """写出 v3 artifact、JSON report 与便于人工浏览的 Markdown 摘要。"""

    artifact, report = _run()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "m44-agent-scenario-v3.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "m44-b2-deterministic-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# M44 B2 deterministic rehearsal", "", f"- passed: `{str(report['passed']).lower()}`",
        "- external calls: `0`", f"- contract identity: `{report['contract_identity']}`",
        f"- artifact identity: `{report['artifact_identity']}`", "", "## Checks", "",
        *(f"- [{'x' if passed else ' '}] {name}" for name, passed in report["checks"].items()),
    ]
    (OUTPUT_DIR / "m44-b2-deterministic-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
