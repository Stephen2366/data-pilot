"""M40 P7：Trace runtime 与最终 assurance 的 closed-world 回归。"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from engine.harness.contracts import AgentRunResult, HarnessRequest, RouteDecision, ToolObservation
from engine.rag.evidence import Evidence, EvidenceLedger, EvidenceRef, SQLEvidencePayload
from engine.trace.runtime import build_trace_runtime_identity
from eval.phase4_assurance import (
    REHEARSAL_SCENARIOS,
    TraceRehearsalEvidence,
    build_trace_rehearsal_artifact,
    rehearsal_artifact_to_json,
    render_assurance_markdown,
    run_phase4_assurance,
    validate_phase4_assurance_artifact,
    validate_trace_rehearsal_artifact,
)
from scripts.run_m40_phase4_assurance import main as run_assurance_cli


def _rehearsal() -> object:
    """构造五路径均已由各自 API Trace 回归证明的安全 rehearsal 投影。"""

    return build_trace_rehearsal_artifact(tuple(
        TraceRehearsalEvidence(
            scenario_id=scenario_id, trace_count=1 if scenario_id != "clarification_resume" else 2,
            response_trace_ids_match=True, axes_match=True, evidence_or_lifecycle_valid=True,
            runtime_status="complete", no_sensitive_payload=True, execution_identity=f"trace-rehearsal:{scenario_id}",
        )
        for scenario_id in REHEARSAL_SCENARIOS
    ))


def test_sql_runtime_identity_uses_safe_ledger_not_private_sql_payload() -> None:
    """SQL Trace 只能记录 Evidence ledger 的 runtime ref，不能把 SQL 或 rows 当运行身份。"""

    ref = EvidenceRef("run", "sql-evidence", "sql", "db", "now", "fingerprint", "sql-result")
    evidence = Evidence(ref, ("answer_evidence",), "guard", "text2sql-pipeline-v1", SQLEvidencePayload(
        "SELECT secret", ("amount",), 1, "fingerprint", "now", "db", "text2sql-pipeline-v1", ((1,),)
    ))
    ledger = EvidenceLedger.from_candidates(run_id="run", evidence=(evidence,)).transition(
        evidence_ids=(ref.evidence_id,), to_stage="selected"
    )
    observation = ToolObservation(
        "text2sql", "sql", "completed", "complete", "passed", "sql_completed", answer="ok",
        ledger_projection=ledger.safe_projection(), evidence_refs=(ref.audit_projection(),),
    )
    result = AgentRunResult(
        "sql", "completed", "complete", "passed", "sql_completed", "ok",
        RouteDecision("sql", "sql", True, "answer"), observation, "answer", ("route", "sql_tool", "controller"), "caller",
    )

    runtime = build_trace_runtime_identity(result=result, checkpoint_runtime={"kind": "inprocess"})
    assert runtime["status"] == "complete"
    assert runtime["route_runtime"] == {"kind": "sql", "tool": "text2sql", "runtime_ref": "text2sql-pipeline-v1"}
    assert "SELECT secret" not in str(runtime) and "fingerprint" not in str(runtime["route_runtime"])


def test_missing_safe_runtime_identity_degrades_trace_without_breaking_result() -> None:
    """C1 缺少可公开 ledger 时只让 Trace 标 unavailable，不伪造身份或抛业务异常。"""

    observation = ToolObservation(
        "text2sql", "sql", "completed", "complete", "passed", "sql_completed", answer="仍可返回的结果"
    )
    result = AgentRunResult(
        "sql", "completed", "complete", "passed", "sql_completed", "仍可返回的结果",
        RouteDecision("sql", "sql", True, "answer"), observation, "answer", ("route", "sql_tool", "controller"), "caller",
    )

    runtime = build_trace_runtime_identity(result=result, checkpoint_runtime={"kind": "inprocess"})
    assert runtime["status"] == "unavailable"
    assert runtime["missing"] == ["route_runtime.runtime_ref"]


def test_assurance_runs_current_families_and_keeps_m39_no_go(tmp_path: Path) -> None:
    """P7 Gate 只接受恰好九个当前 family，M39 只能以 verified no-go 登记。"""

    artifact = run_phase4_assurance(
        root=tmp_path, rehearsal=_rehearsal(),
        m39_audit_path=Path("eval/reports/m39-p6-readiness.json"),
    )
    assert [item.family for item in artifact.entries] == [
        "p1_security_release", "p2_rag_retrieval", "p2_rag_answer", "p3_harness", "p4_turn",
        "p4_followup", "p5_hybrid", "p6_no_go", "p7_trace_rehearsal",
    ]
    assert "仅技术 Gate" in render_assurance_markdown(artifact)


def test_assurance_rejects_missing_family_even_when_hash_is_recomputed(tmp_path: Path) -> None:
    """不能删掉难跑 family 后再重算 identity，来伪造整体通过。"""

    artifact = run_phase4_assurance(
        root=tmp_path, rehearsal=_rehearsal(),
        m39_audit_path=Path("eval/reports/m39-p6-readiness.json"),
    )
    tampered = replace(artifact, entries=artifact.entries[:-1], artifact_identity="recomputed-but-invalid")
    with pytest.raises(ValueError, match="family"):
        validate_phase4_assurance_artifact(tampered)


def test_rehearsal_rejects_a_missing_or_unavailable_canonical_path() -> None:
    """C2 不能用少跑一条路径或 runtime unavailable 伪造通过。"""

    artifact = _rehearsal()
    with pytest.raises(ValueError, match="缺失、重复或乱序"):
        validate_trace_rehearsal_artifact(replace(artifact, execution_evidence=artifact.execution_evidence[:-1]))
    unavailable = replace(artifact.execution_evidence[0], runtime_status="unavailable")
    with pytest.raises(ValueError, match="runtime identity"):
        validate_trace_rehearsal_artifact(replace(artifact, execution_evidence=(unavailable, *artifact.execution_evidence[1:])))


def test_assurance_cli_writes_checked_json_and_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """可重复 CLI 必须先验证 rehearsal，再输出可供人工查看的同一份 assurance。"""

    rehearsal_path = tmp_path / "rehearsal.json"
    output_path = tmp_path / "assurance.json"
    report_path = tmp_path / "assurance.md"
    rehearsal_path.write_text(json.dumps(rehearsal_artifact_to_json(_rehearsal()), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_m40_phase4_assurance.py", "--rehearsal", str(rehearsal_path), "--output", str(output_path),
            "--report", str(report_path), "--m39-audit", "eval/reports/m39-p6-readiness.json",
        ],
    )

    run_assurance_cli()

    assert json.loads(output_path.read_text(encoding="utf-8"))["format"] == "phase4-assurance-v1"
    assert "仅技术 Gate" in report_path.read_text(encoding="utf-8")
