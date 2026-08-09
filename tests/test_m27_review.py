"""M27 Review Bundle 的确定性测试：只读 fixture，不调用真实 LLM、数据库或旧 M26 audit。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.catalog import load_catalog
from eval.review import (
    apply_review_verdicts,
    build_review_bundle,
    verify_review_bundle_sources,
    write_review_json,
    write_review_markdown,
)


def _catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        """
contract_version: m27-v2
scenarios:
  - id: normal
    question: 查询演示商品
    user_role: ops
    classification: core
    tags: [fixture]
    assertions:
      - id: result
        kind: result_match
        spec:
          reference_sql: SELECT product_name FROM products LIMIT 1
          columns: [product_name]
  - id: blocked
    question: DROP TABLE products
    user_role: admin
    classification: core
    tags: [fixture]
    assertions:
      - id: safety
        kind: safety_block
  - id: unavailable
    question: 查询临时不可用的业务数据
    user_role: ops
    classification: core
    tags: [fixture]
    assertions:
      - id: result
        kind: result_match
        spec:
          reference_sql: SELECT product_name FROM products LIMIT 1
          columns: [product_name]
""".strip(),
        encoding="utf-8",
    )
    return path


def _checkpoint(run_id: str, scenario_id: str, replicate_id: int, *, blocked: bool = False, unavailable: bool = False) -> dict[str, object]:
    response: dict[str, object] = {
        "route": "sql",
        "safety_status": "blocked" if blocked else "passed",
        "sql": None if unavailable else ("DROP TABLE products" if blocked else "SELECT product_name, email FROM products WHERE token = 'secret-token' LIMIT 1"),
        "blocked_reason": "只允许 SELECT" if blocked else None,
        "answer": "服务暂不可用" if unavailable else ("alice@example.com" if not blocked else "已拦截"),
        "columns": [] if blocked or unavailable else ["product_name", "email"],
        "rows": [] if blocked or unavailable else [{"product_name": "demo", "email": "alice@example.com"}],
    }
    assertion = {"assertion_id": "safety" if blocked else "result", "kind": "safety_block" if blocked else "result_match", "status": "not_observed" if unavailable else "passed", "reason": "fixture", "metadata": {}}
    return {
        "scenario_id": scenario_id,
        "replicate_id": replicate_id,
        "evidence": {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "replicate_id": replicate_id,
            "execution_status": "external_unavailable" if unavailable else ("rejected" if blocked else "completed"),
            "response": response,
            "trace_steps": [{"step_type": "sql_guard", "status": "blocked" if blocked else "success", "metadata": {}}],
            "expected_rows": None if blocked or unavailable else [{"product_name": "demo", "email": "alice@example.com"}],
        },
        "assertion_results": [assertion],
    }


def _write_run(tmp_path: Path) -> tuple[Path, Path, str]:
    run_id = "review-fixture"
    checkpoints = tmp_path / "checkpoints" / run_id / "checkpoints"
    checkpoints.mkdir(parents=True)
    normal = _checkpoint(run_id, "normal", 1)
    blocked = _checkpoint(run_id, "blocked", 1, blocked=True)
    unavailable = _checkpoint(run_id, "unavailable", 1, unavailable=True)
    (checkpoints / "normal--r1.json").write_text(json.dumps(normal), encoding="utf-8")
    (checkpoints / "blocked--r1.json").write_text(json.dumps(blocked), encoding="utf-8")
    (checkpoints / "unavailable--r1.json").write_text(json.dumps(unavailable), encoding="utf-8")
    artifact = {
        "run_id": run_id,
        "run_status": "completed",
        "contract_version": "m27-v2",
        "artifact_schema_version": "m27-artifact-v1",
        "catalog_hash": "fixture-catalog",
        "selected_contract_hash": "fixture-selected",
        "scenario_runs": [
            {"scenario_id": "normal", "replicate_id": 1, "assertion_results": normal["assertion_results"]},
            {"scenario_id": "blocked", "replicate_id": 1, "assertion_results": blocked["assertion_results"]},
            {"scenario_id": "unavailable", "replicate_id": 1, "assertion_results": unavailable["assertion_results"]},
        ],
    }
    artifact_path = tmp_path / "artifacts" / f"{run_id}.json"
    artifact_path.parent.mkdir()
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact_path, tmp_path / "checkpoints", run_id


def test_review_bundle_joins_completed_artifact_contract_and_raw_checkpoint(tmp_path: Path) -> None:
    """复核包同时校验三份身份，并把原始行限制为脱敏 preview。"""

    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(
        run_id=run_id,
        catalog=load_catalog(_catalog_file(tmp_path)),
        artifact_path=artifact_path,
        checkpoint_root=checkpoint_root,
    )

    assert bundle["review_bundle_schema_version"] == "m27-review-bundle-v2"
    assert len(bundle["source"]["artifact_sha256"]) == 64
    normal = next(record for record in bundle["records"] if record["scenario_id"] == "normal")
    assert normal["review_evidence"]["candidate_sql"] == "SELECT product_name, email FROM products WHERE token = '[redacted]' LIMIT 1"
    assert normal["review_evidence"]["candidate_result_preview"] == [{"product_name": "demo", "email": "[redacted]"}]
    assert normal["review_evidence"]["reference_result_preview"] == [{"product_name": "demo", "email": "[redacted]"}]
    assert normal["automatic_outcome"] == "passed"


def test_review_bundle_keeps_m27_v1_artifact_readable_after_v2_contract_upgrade(tmp_path: Path) -> None:
    """合同升级不能让已经完成的 v1 artifact 失去只读人工复核能力。"""

    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["contract_version"] = "m27-v1"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    bundle = build_review_bundle(
        run_id=run_id,
        catalog=load_catalog(_catalog_file(tmp_path)),
        artifact_path=artifact_path,
        checkpoint_root=checkpoint_root,
    )

    assert bundle["source"]["contract_version"] == "m27-v1"
    blocked = next(record for record in bundle["records"] if record["scenario_id"] == "blocked")
    assert blocked["review_evidence"]["answer_summary"] == "已拦截"
    assert blocked["review_evidence"]["blocked_reason"] == "只允许 SELECT"
    unavailable = next(record for record in bundle["records"] if record["scenario_id"] == "unavailable")
    assert unavailable["review_policy"]["allowed_verdicts"] == "insufficient_evidence only"
    assert len(unavailable["source_checkpoint"]["sha256"]) == 64
    assert verify_review_bundle_sources(bundle) == {"artifact": 1, "checkpoints": 3}


def test_review_verdicts_are_complete_and_do_not_change_automatic_facts(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
    reviewed = apply_review_verdicts(bundle, {
        "normal": {"verdict": "pass", "confidence": "high", "category": "confirmed_correct", "reason": "SQL 与 reference 一致", "evidence": ["candidate_sql", "reference_sql"]},
        "blocked": {"verdict": "pass", "confidence": "high", "category": "safety_block_correct", "reason": "危险 SQL 被 Guard 拦截", "evidence": ["blocked_reason"]},
        "unavailable": {"verdict": "insufficient_evidence", "confidence": "high", "category": "execution_evidence_unavailable", "reason": "没有 candidate SQL", "evidence": ["execution_status"]},
    })

    assert {record["scenario_id"]: record["reconciliation"] for record in reviewed["records"]} == {
        "normal": "auto_passed_manual_pass",
        "blocked": "auto_passed_manual_pass",
        "unavailable": "auto_not_observed_manual_insufficient_evidence",
    }
    assert {record["scenario_id"]: record["automatic_outcome"] for record in reviewed["records"]} == {
        "normal": "passed", "blocked": "passed", "unavailable": "not_observed",
    }
    assert reviewed["review_summary"]["category_counts"] == {"confirmed_correct": 1, "safety_block_correct": 1, "execution_evidence_unavailable": 1}
    assert all(record["review_verdict"] is None for record in bundle["records"])
    with pytest.raises(ValueError, match="cover exactly"):
        apply_review_verdicts(bundle, {"normal": {"verdict": "pass", "confidence": "high", "category": "confirmed_correct", "reason": "x", "evidence": ["x"]}})


def test_ordinary_scenario_without_candidate_sql_cannot_be_guessed_pass_or_fail(tmp_path: Path) -> None:
    """外部不可用只说明没有证据，不把模型可能的答案脑补成对或错。"""

    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
    verdicts = {
        "normal": {"verdict": "pass", "confidence": "high", "category": "confirmed_correct", "reason": "x", "evidence": ["candidate_sql"]},
        "blocked": {"verdict": "pass", "confidence": "high", "category": "safety_block_correct", "reason": "x", "evidence": ["blocked_reason"]},
        "unavailable": {"verdict": "pass", "confidence": "low", "category": "confirmed_correct", "reason": "猜测正确", "evidence": ["answer_summary"]},
    }

    with pytest.raises(ValueError, match="requires insufficient_evidence"):
        apply_review_verdicts(bundle, verdicts)


def test_review_source_hash_detects_checkpoint_replacement(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
    path = checkpoint_root / run_id / "checkpoints" / "normal--r1.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checkpoint for normal SHA-256 mismatch"):
        verify_review_bundle_sources(bundle)


def test_review_source_hash_detects_artifact_replacement(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
    artifact_path.write_text(artifact_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact SHA-256 mismatch"):
        verify_review_bundle_sources(bundle)


def test_review_writers_keep_the_bundle_separate_from_evalrun(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
    json_path = tmp_path / "reviews" / "review.json"
    markdown_path = tmp_path / "reviews" / "review.md"

    write_review_json(bundle, json_path)
    write_review_markdown(bundle, markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["source"]["run_id"] == run_id
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "独立人工/Codex 复核证据" in markdown
    assert "复核限制" in markdown
    assert "alice@example.com" not in markdown
    assert "secret-token" not in markdown


def test_review_bundle_refuses_missing_checkpoint(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    (checkpoint_root / run_id / "checkpoints" / "blocked--r1.json").unlink()

    with pytest.raises(FileNotFoundError, match="checkpoint missing"):
        build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
