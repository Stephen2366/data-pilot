"""M27 Review Bundle 的确定性测试：只读 fixture，不调用真实 LLM、数据库或旧 M26 audit。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.catalog import load_catalog
from eval.review import apply_review_verdicts, build_review_bundle, write_review_json, write_review_markdown


def _catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        """
contract_version: m27-v1
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
""".strip(),
        encoding="utf-8",
    )
    return path


def _checkpoint(run_id: str, scenario_id: str, replicate_id: int, *, blocked: bool = False) -> dict[str, object]:
    response: dict[str, object] = {
        "route": "sql",
        "safety_status": "blocked" if blocked else "passed",
        "sql": "DROP TABLE products" if blocked else "SELECT product_name, email FROM products WHERE token = 'secret-token' LIMIT 1",
        "blocked_reason": "只允许 SELECT" if blocked else None,
        "answer": "alice@example.com" if not blocked else "已拦截",
        "columns": [] if blocked else ["product_name", "email"],
        "rows": [] if blocked else [{"product_name": "demo", "email": "alice@example.com"}],
    }
    assertion = {"assertion_id": "safety" if blocked else "result", "kind": "safety_block" if blocked else "result_match", "status": "passed", "reason": "fixture", "metadata": {}}
    return {
        "scenario_id": scenario_id,
        "replicate_id": replicate_id,
        "evidence": {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "replicate_id": replicate_id,
            "execution_status": "rejected" if blocked else "completed",
            "response": response,
            "trace_steps": [{"step_type": "sql_guard", "status": "blocked" if blocked else "success", "metadata": {}}],
            "expected_rows": None if blocked else [{"product_name": "demo", "email": "alice@example.com"}],
        },
        "assertion_results": [assertion],
    }


def _write_run(tmp_path: Path) -> tuple[Path, Path, str]:
    run_id = "review-fixture"
    checkpoints = tmp_path / "checkpoints" / run_id / "checkpoints"
    checkpoints.mkdir(parents=True)
    normal = _checkpoint(run_id, "normal", 1)
    blocked = _checkpoint(run_id, "blocked", 1, blocked=True)
    (checkpoints / "normal--r1.json").write_text(json.dumps(normal), encoding="utf-8")
    (checkpoints / "blocked--r1.json").write_text(json.dumps(blocked), encoding="utf-8")
    artifact = {
        "run_id": run_id,
        "run_status": "completed",
        "contract_version": "m27-v1",
        "artifact_schema_version": "m27-artifact-v1",
        "catalog_hash": "fixture-catalog",
        "selected_contract_hash": "fixture-selected",
        "scenario_runs": [
            {"scenario_id": "normal", "replicate_id": 1, "assertion_results": normal["assertion_results"]},
            {"scenario_id": "blocked", "replicate_id": 1, "assertion_results": blocked["assertion_results"]},
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

    assert bundle["review_bundle_schema_version"] == "m27-review-bundle-v1"
    normal = next(record for record in bundle["records"] if record["scenario_id"] == "normal")
    assert normal["review_evidence"]["candidate_sql"] == "SELECT product_name, email FROM products WHERE token = '[redacted]' LIMIT 1"
    assert normal["review_evidence"]["candidate_result_preview"] == [{"product_name": "demo", "email": "[redacted]"}]
    assert normal["review_evidence"]["reference_result_preview"] == [{"product_name": "demo", "email": "[redacted]"}]
    assert normal["automatic_outcome"] == "passed"
    blocked = next(record for record in bundle["records"] if record["scenario_id"] == "blocked")
    assert blocked["review_evidence"]["answer_summary"] == "已拦截"
    assert blocked["review_evidence"]["blocked_reason"] == "只允许 SELECT"


def test_review_verdicts_are_complete_and_do_not_change_automatic_facts(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    bundle = build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
    reviewed = apply_review_verdicts(bundle, {
        "normal": {"verdict": "pass", "confidence": "high", "reason": "SQL 与 reference 一致", "evidence": ["candidate_sql", "reference_sql"]},
        "blocked": {"verdict": "pass", "confidence": "high", "reason": "危险 SQL 被 Guard 拦截", "evidence": ["blocked_reason"]},
    })

    assert all(record["reconciliation"] == "auto_passed_manual_pass" for record in reviewed["records"])
    assert all(record["automatic_outcome"] == "passed" for record in reviewed["records"])
    assert all(record["review_verdict"] is None for record in bundle["records"])
    with pytest.raises(ValueError, match="cover exactly"):
        apply_review_verdicts(bundle, {"normal": {"verdict": "pass", "confidence": "high", "reason": "x", "evidence": ["x"]}})


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
    assert "alice@example.com" not in markdown
    assert "secret-token" not in markdown


def test_review_bundle_refuses_missing_checkpoint(tmp_path: Path) -> None:
    artifact_path, checkpoint_root, run_id = _write_run(tmp_path)
    (checkpoint_root / run_id / "checkpoints" / "blocked--r1.json").unlink()

    with pytest.raises(FileNotFoundError, match="checkpoint missing"):
        build_review_bundle(run_id=run_id, catalog=load_catalog(_catalog_file(tmp_path)), artifact_path=artifact_path, checkpoint_root=checkpoint_root)
