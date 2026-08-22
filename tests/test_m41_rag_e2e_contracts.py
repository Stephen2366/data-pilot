"""M41 catalog、funnel、Gate、lifecycle 和 artifact closed-world。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.rag_e2e_contracts import (
    RAGEvalContractError,
    load_rag_catalog,
    load_rag_selector,
    validate_completed_artifact,
)
from eval.rag_e2e_runner import run_rag_eval
from eval.rag_e2e_runtime import ComposerRuntimeMetadata, RAGProductExecutor
from tests.test_m41_rag_e2e_runtime import RecordingComposer


CATALOG = Path("eval/cases/rag/scenarios.yaml")
BUSINESS = Path("eval/cases/rag/selectors/business.yaml")


def _run(tmp_path: Path) -> dict:
    catalog = load_rag_catalog(CATALOG)
    selector = load_rag_selector(BUSINESS, catalog)
    executor = RAGProductExecutor(
        composer=RecordingComposer(),
        runtime_metadata=ComposerRuntimeMetadata(model="fake"),
        trace_root=tmp_path / "checkpoints/run/traces",
    )
    return run_rag_eval(
        catalog=catalog,
        selector=selector,
        run_id="m41-test-business",
        executor=executor,
        checkpoint_root=tmp_path / "checkpoints",
        artifact_path=tmp_path / "artifact.json",
        report_path=tmp_path / "report.md",
        triage_path=tmp_path / "triage.json",
    )


def test_business_lifecycle_builds_completed_artifact_report_and_triage(tmp_path: Path) -> None:
    artifact = _run(tmp_path)

    validate_completed_artifact(artifact)
    assert artifact["gate"]["status"] == "passed"
    assert len(artifact["executions"]) == 5
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# Phase 4 RAG E2E Eval Report")
    triage = json.loads((tmp_path / "triage.json").read_text(encoding="utf-8"))
    assert [item["primary_stage"] for item in triage["cases"]] == ["passed"] * 5
    manifest = json.loads((tmp_path / "checkpoints/m41-test-business/manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"


def test_completed_artifact_rejects_tamper_and_duplicate_run(tmp_path: Path) -> None:
    artifact = _run(tmp_path)
    artifact["executions"] = artifact["executions"][:-1]
    with pytest.raises(RAGEvalContractError, match="identity|execution|hash"):
        validate_completed_artifact(artifact)

    catalog = load_rag_catalog(CATALOG)
    selector = load_rag_selector(BUSINESS, catalog)
    executor = RAGProductExecutor(
        composer=RecordingComposer(),
        runtime_metadata=ComposerRuntimeMetadata(model="fake"),
        trace_root=tmp_path / "other-traces",
    )
    with pytest.raises(ValueError, match="completed"):
        run_rag_eval(
            catalog=catalog,
            selector=selector,
            run_id="m41-test-business",
            executor=executor,
            checkpoint_root=tmp_path / "checkpoints",
            artifact_path=tmp_path / "artifact.json",
            report_path=tmp_path / "report.md",
            triage_path=tmp_path / "triage.json",
        )


def test_selector_identity_is_stable_and_unknown_scenario_is_rejected(tmp_path: Path) -> None:
    catalog = load_rag_catalog(CATALOG)
    first = load_rag_selector(BUSINESS, catalog)
    second = load_rag_selector(BUSINESS, catalog)
    assert first == second

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("selector_id: bad\nselected_scenario_ids: [missing]\nreplicate_count: 1\n", encoding="utf-8")
    with pytest.raises(RAGEvalContractError, match="未知 Scenario"):
        load_rag_selector(invalid, catalog)


def test_failed_run_requires_explicit_resume_and_reuses_legal_prefix(tmp_path: Path) -> None:
    catalog = load_rag_catalog(CATALOG)
    selector = load_rag_selector(BUSINESS, catalog)
    composer = RecordingComposer()
    product = RAGProductExecutor(
        composer=composer, runtime_metadata=ComposerRuntimeMetadata(model="fake"),
        trace_root=tmp_path / "checkpoints/resume-run/traces",
    )

    class FailAfterFirst:
        def __init__(self) -> None:
            self.calls = 0

        def resolved_runtime(self):
            return product.resolved_runtime()

        def execute(self, *, scenario, replicate):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated interruption")
            return product.execute(scenario=scenario, replicate=replicate)

    paths = {
        "checkpoint_root": tmp_path / "checkpoints",
        "artifact_path": tmp_path / "artifact.json",
        "report_path": tmp_path / "report.md",
        "triage_path": tmp_path / "triage.json",
    }
    with pytest.raises(RuntimeError, match="simulated"):
        run_rag_eval(
            catalog=catalog, selector=selector, run_id="resume-run", executor=FailAfterFirst(), **paths
        )
    assert not paths["artifact_path"].exists()
    with pytest.raises(ValueError, match="resume"):
        run_rag_eval(
            catalog=catalog, selector=selector, run_id="resume-run", executor=product, **paths
        )

    resumed = run_rag_eval(
        catalog=catalog, selector=selector, run_id="resume-run", executor=product, resume=True, **paths
    )
    assert resumed["status"] == "completed"
    # 第一题来自 checkpoint；恢复阶段执行剩余四题，其中三题需要 Composer。
    assert len(composer.attempts) == 4
