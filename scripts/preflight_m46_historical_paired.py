"""M46-F historical 60×2 的零 provider candidate freeze / dry-run preflight。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.identity import canonical_hash, file_sha256
from eval.rag_external_catalog import load_external_rag_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESERVE_MANIFEST = PROJECT_ROOT / "eval/cases/agent/phase4b_reserve_manifest.json"
CANDIDATE_FILES = (
    "domain_pack/phase4b/b4_contracts.json",
    "domain_pack/phase4b/b4_contracts.manifest.json",
    "engine/phase4b/b4_contracts.py",
    "engine/phase4b/rag_strategy.py",
    "engine/phase4b/rag_subgraph.py",
    "engine/phase4b/external_requirement_formation.py",
    "engine/phase4b/rag_recovery_requirement_proposal.py",
    "engine/rag/evidence_acquisition.py",
    "engine/rag/answer_flow.py",
    "engine/phase4b/agent_loop.py",
    "eval/agent_scenario_v4_contracts.py",
    "eval/rag_b4_projection.py",
    "eval/rag_e2e_runtime.py",
    "eval/run_rag_external_eval.py",
    "eval/rag_e2e_scoring.py",
    "eval/rag_e2e_review.py",
    "scripts/preflight_m46_historical_paired.py",
    "scripts/run_m46_historical_paired.py",
)


def build_preflight(*, dataset_root: Path) -> dict[str, Any]:
    """只读 dev catalog/安全 reserve manifest；不加载 Milvus、模型或 reserve 外部逐题文件。"""

    bundle = load_b4_contract_bundle()
    catalog, selector = load_external_rag_catalog(
        dataset_root=dataset_root,
        dataset_recipe_path=PROJECT_ROOT / "eval/cases/enterprise-rag-bench-v1.0.0-dataset.json",
        split_path=PROJECT_ROOT / "eval/cases/enterprise-rag-bench-v1.0.0-split.json",
        partition="diagnostic_dev",
        suite="full",
    )
    reserve = json.loads(RESERVE_MANIFEST.read_text(encoding="utf-8"))
    if (
        reserve.get("decision_status") != "sealed"
        or reserve.get("reserve_identity") != bundle.payload["reserve"]["source_identity"]
    ):
        raise ValueError("m46_reserve_preflight_failed")
    selected = tuple(selector.selected_scenario_ids)
    if len(selected) != 60 or len(set(selected)) != 60:
        raise ValueError("m46_historical_selector_invalid")
    file_hashes = {
        relative: file_sha256(PROJECT_ROOT / relative)
        for relative in CANDIDATE_FILES
    }
    arms = tuple(bundle.payload["reserve"]["paired_arms"])
    protocol = {
        "partition": "diagnostic_dev",
        "suite": "full",
        "scenario_count": len(selected),
        "replicate_count": selector.replicate_count,
        "arms": list(arms),
        "physical_executions": len(selected) * selector.replicate_count * len(arms),
        "arm_order": ["pipeline", "subgraph"],
        "retry_count": 0,
        "allowed_arm_differences": [
            "runtime_family",
            "retrieval_snapshot.acquisition_strategy",
            "b4_subgraph_child_ledger",
        ],
    }
    budgets = {
        # Pipeline：initial embedding + Composer；Subgraph：initial + proposal + 最多2 rewrite + Composer。
        "pipeline_max_provider_attempts": len(selected) * 2,
        "subgraph_max_provider_attempts": len(selected) * 5,
        "paired_max_provider_attempts": len(selected) * 7,
        # B4 parent 每题最多 24k observed tokens；paired 两臂均用同一保守上限。
        "per_execution_max_observed_tokens": int(bundle.payload["parent_budget"]["max_total_tokens"]),
        "paired_max_observed_tokens": (
            len(selected) * len(arms) * int(bundle.payload["parent_budget"]["max_total_tokens"])
        ),
    }
    freeze_payload = {
        "schema_version": "phase4b-b4-candidate-freeze-v1",
        "b4_contract_identity": bundle.content_identity,
        "catalog_identity": catalog.catalog_identity,
        "selector_identity": selector.selector_identity,
        "profile_identity": reserve["profile_identity"],
        "reserve_identity": reserve["reserve_identity"],
        "candidate_files": file_hashes,
        "protocol": protocol,
        "budgets": budgets,
    }
    return {
        **freeze_payload,
        "candidate_identity": canonical_hash(freeze_payload),
        "preflight": {
            "status": "ready_for_historical_authorization",
            "provider_calls": 0,
            "reserve_records_read": 0,
            "reserve_state": "sealed",
        },
    }


def main() -> None:
    """生成零 provider 调用、reserve sealed 的 historical 候选快照。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_preflight(dataset_root=args.dataset_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["preflight"]["status"],
        "candidate_identity": payload["candidate_identity"],
        "physical_executions": payload["protocol"]["physical_executions"],
        "max_provider_attempts": payload["budgets"]["paired_max_provider_attempts"],
        "max_observed_tokens": payload["budgets"]["paired_max_observed_tokens"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
