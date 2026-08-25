"""离线恢复首次 P4R runner crash 的最小证据；绝不调用 provider。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from engine.phase4b.identity import canonical_hash
from eval.rag_action_diagnostics import load_repair_diagnostic_campaign


def _verified(path: Path) -> dict[str, Any]:
    """核验恢复输入未被篡改；恢复流程绝不重新调用 provider。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise ValueError(f"m45_p4r_recovery_hash_mismatch:{path.name}")
    return payload


def main() -> None:
    """从已知 call count 与离线 qst0461 证据恢复显式不完整的 P4R artifact。"""

    parser = argparse.ArgumentParser(description="Recover M45-P4R failed runner evidence offline")
    parser.add_argument("--offline-safe", type=Path, required=True)
    parser.add_argument("--offline-private", type=Path, required=True)
    parser.add_argument("--p4-safe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    campaign = load_repair_diagnostic_campaign()
    offline = _verified(args.offline_safe)
    offline_private = _verified(args.offline_private)
    p4 = _verified(args.p4_safe)
    if (
        offline.get("offline_preflight_only") is not True
        or len(offline.get("scenarios") or ()) != 1
        or offline["scenarios"][0].get("scenario_id") != "qst_0461"
        or offline["scenarios"][0].get("gate") != "passed"
        or offline_private.get("safe_artifact_identity") != offline.get("artifact_identity")
        or p4.get("campaign_identity") != campaign.predecessor_campaign_identity
    ):
        raise ValueError("m45_p4r_recovery_lineage_invalid")
    failed_431 = {
        "scenario_id": "qst_0431",
        "proposal_status": "failed",
        "proposal_error": "proposal_no_unsupported_requirement",
        "execution": {
            "chosen_action": "stop",
            "status": "blocked",
            "termination_reason": "proposal_no_unsupported_requirement",
        },
        "assertions": {
            "proposal_transport_completed": True,
            "proposal_valid": False,
            "expected_action_selected": False,
            "failure_artifact_complete": False,
        },
        "gate": "failed",
        "decision": "stop",
        "usage": {
            "retrieval_calls": 0,
            "embedding_provider_attempts": 0,
            "chat_model_calls": 1,
            "composer_calls": 0,
            "observed_chat_tokens": None,
            "token_usage_observed": False,
        },
        "runtime_identity": offline["scenarios"][0]["runtime_identity"],
    }
    safe: dict[str, Any] = {
        "schema_version": "phase4b-m45-live-probe-v3-recovered",
        "probe_id": "M45-P4R",
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "source_artifact_identities": {
            "p4": p4["artifact_identity"],
            "qst_0461_offline": offline["artifact_identity"],
        },
        "recovered_at": datetime.now(timezone.utc).isoformat(),
        "recovery_reason": "runner_uncaught_proposal_error_after_provider_success",
        "evidence_completeness": "incomplete_raw_response_and_token_usage_lost",
        "scenarios": [offline["scenarios"][0], failed_431],
        "gate": "failed",
        "decision": "stop",
        "usage": {
            "retrieval_calls": 0,
            "embedding_provider_attempts": 0,
            "chat_model_calls": 1,
            "composer_calls": 0,
            "observed_chat_tokens": None,
            "token_usage_observed": False,
        },
        "budget_respected": "not_observed",
        "reserve_access_state": "sealed",
    }
    safe["artifact_identity"] = canonical_hash(safe)
    private: dict[str, Any] = {
        "schema_version": "phase4b-m45-private-probe-v3-recovered",
        "probe_id": "M45-P4R",
        "safe_artifact_identity": safe["artifact_identity"],
        "campaign_identity": campaign.identity,
        "source_artifact_identities": safe["source_artifact_identities"],
        "scenarios": [
            offline_private["scenarios"][0],
            {
                "scenario_id": "qst_0431",
                "proposal_error": "proposal_no_unsupported_requirement",
                "raw_response": None,
                "token_usage": None,
                "loss_reason": "runner_uncaught_exception_after_successful_transport",
            },
        ],
    }
    private["artifact_identity"] = canonical_hash(private)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.private_output.write_text(
        json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "gate": safe["gate"],
        "decision": safe["decision"],
        "artifact_identity": safe["artifact_identity"],
        "chat_model_calls": 1,
        "token_usage_observed": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
