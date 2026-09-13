"""P1-C2 EvoLoop catalog 投影的 DataPilot 所有权测试。"""

from pathlib import Path

from eval.catalog import load_catalog
from eval.evoloop_projection import project_catalog_for_evoloop


CATALOG = Path("eval/cases/catalog/scenarios.yaml")


def test_projection_matches_current_canonical_catalog_without_sensitive_fields() -> None:
    catalog = load_catalog(CATALOG)
    projection = project_catalog_for_evoloop(CATALOG)

    assert projection["contract_version"] == "m27-v4"
    assert projection["catalog_hash"] == f"sha256:{catalog.catalog_hash}"
    assert len(projection["scenarios"]) == len(catalog.scenarios) == 28
    assert sum(item["classification"] == "core" for item in projection["scenarios"]) == 19
    safety = {
        item["scenario_id"]
        for item in projection["scenarios"]
        if any(assertion["kind"] in {"safety_block", "expected_rejection"} for assertion in item["assertions"])
    }
    assert len(safety) == 7
    assert all(set(item) == {"scenario_id", "classification", "assertions"} for item in projection["scenarios"])
    serialized = repr(projection).lower()
    assert "question" not in serialized
    assert "reference_sql" not in serialized
    assert "authority_refs" not in serialized
