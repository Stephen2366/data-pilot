"""M27 plan-only companion：证明计划稳定、可复用且无 Runtime/运行产物。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.planning import PLAN_SCHEMA_VERSION, build_explicit_run_plan, write_run_plan
from eval.run_plan import main

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG = PROJECT_ROOT / "eval" / "cases" / "catalog" / "scenarios.yaml"


def test_explicit_june_plan_is_stable_and_contains_all_pre_run_identities(tmp_path: Path) -> None:
    first = build_explicit_run_plan(
        catalog_path=CATALOG,
        scenario_ids=("june_gmv",),
        pipeline_mode="new_text2sql",
        schema_fusion_strategy="weighted",
        replicate_count=1,
    )
    second = build_explicit_run_plan(
        catalog_path=CATALOG,
        scenario_ids=("june_gmv",),
        pipeline_mode="new_text2sql",
        schema_fusion_strategy="weighted",
        replicate_count=1,
    )
    assert first == second
    assert first["plan_schema_version"] == PLAN_SCHEMA_VERSION
    assert first["scenario_ids"] == ["june_gmv"]
    assert first["execution_protocol"] == {
        "pipeline_mode": "new_text2sql", "schema_fusion_strategy": "weighted", "replicate_count": 1
    }
    assert first["expected_runtime"]["llm_provider"] == "qwen"
    assert first["expected_runtime"]["schema_vector_backend"] == "inmemory"
    assert first["expected_runtime"]["schema_embedding_provider"] == "deterministic"
    assert all(len(first[name]) == 64 for name in ("catalog_hash", "selected_contract_hash", "suite_policy_hash", "run_spec_hash", "plan_digest"))
    assert list(tmp_path.iterdir()) == []


def test_cli_writes_only_requested_plan_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "plan.json"
    arguments = [
        "--catalog", str(CATALOG), "--scenario", "june_gmv", "--pipeline-mode", "new_text2sql",
        "--schema-fusion-strategy", "weighted", "--replicate-count", "1", "--output", str(output),
    ]
    assert main(arguments) == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["scenario_ids"] == ["june_gmv"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["plan.json"]
    with pytest.raises(FileExistsError):
        main(arguments)


def test_writer_rejects_existing_plan_without_modifying_it(tmp_path: Path) -> None:
    output = tmp_path / "plan.json"
    output.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_run_plan({"plan_schema_version": PLAN_SCHEMA_VERSION}, output)
    assert output.read_text(encoding="utf-8") == "original"
