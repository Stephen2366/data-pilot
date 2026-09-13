"""P1-C2 受信 Hidden 材料的聚焦测试。"""

import json
import copy
from pathlib import Path

import pytest

from eval.catalog import load_catalog
from eval.evoloop_hidden_material import (
    HiddenMaterialError,
    build_public_offer,
    load_hidden_material,
    rehearse_hidden_material,
    validate_hidden_material,
)
from tests.evoloop_sample_material import formal_sample


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_private_material_validates_and_zero_model_rehearsal_passes() -> None:
    material = validate_hidden_material(formal_sample())
    rehearsal = rehearse_hidden_material(material)
    assert rehearsal["state"] == "passed"
    assert len(rehearsal["results"]) == 4
    offer = build_public_offer(material)
    assert offer["expected_count"] == 4
    assert offer["coverage"] == ["cross_table", "expected_rejection", "numeric_time", "safety_block"]
    text = json.dumps(offer, ensure_ascii=False).lower()
    for forbidden in ("case_id", "question", "oracle", "expected_rows", "reason_code"):
        assert forbidden not in text


def test_validator_collects_multiple_material_problems() -> None:
    raw = copy.deepcopy(formal_sample())
    raw["unexpected"] = True
    raw["cases"][1]["case_id"] = raw["cases"][0]["case_id"]
    raw["cases"][2]["coverage"] = "numeric_time"
    raw["cases"][3]["fixture"]["setup_sql"] = []
    with pytest.raises(HiddenMaterialError) as captured:
        validate_hidden_material(raw)
    message = str(captured.value)
    assert "fields mismatch" in message
    assert "duplicate" in message
    assert "missing coverage" in message
    assert "setup_sql" in message


def test_hidden_material_does_not_change_canonical_classification() -> None:
    catalog = load_catalog(PROJECT_ROOT / "eval/cases/catalog/scenarios.yaml")
    assert {scenario.classification for scenario in catalog.scenarios} == {"core", "stress"}
    assert all(scenario.classification != "hidden" for scenario in catalog.scenarios)
