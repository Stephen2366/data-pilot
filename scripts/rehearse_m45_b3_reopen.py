"""M45-F：把 predecessor no-go + P4 固化为 additive v2 review artifact。"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from engine.phase4b.identity import canonical_hash
from eval.rag_action_diagnostics import (
    build_reopened_review_artifact,
    load_reopened_diagnostic_campaign,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _verified(path: Path) -> dict[str, Any]:
    """读取并复算 artifact identity。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise ValueError(f"m45_reopened_artifact_hash_mismatch:{path.name}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """稳定写出 review JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> None:
    """把 predecessor no-go 与 P4 证据固化为 additive v2 review。"""

    parser = argparse.ArgumentParser(description="Build M45 reopened review artifacts")
    parser.add_argument("--p4-safe", type=Path, required=True)
    parser.add_argument("--p4-private", type=Path, required=True)
    parser.add_argument("--external-manifest-output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m45")
    args = parser.parse_args()

    campaign = load_reopened_diagnostic_campaign()
    predecessor = _verified(PROJECT_ROOT / "eval/reports/m45/m45-b3-diagnostic-review.json")
    p4 = _verified(args.p4_safe)
    private = _verified(args.p4_private)
    if (
        private.get("safe_artifact_identity") != p4.get("artifact_identity")
        or private.get("campaign_identity") != campaign.identity
    ):
        raise ValueError("m45_reopened_private_lineage_invalid")

    external: dict[str, Any] = {
        "schema_version": "phase4b-m45-external-diagnostic-manifest-v2",
        "store_version": "phase4b-rag-action-diagnostics/v1.1.0",
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "artifacts": [{
            "path": str(args.p4_private.name),
            "sha256": sha256(args.p4_private.read_bytes()).hexdigest(),
            "artifact_identity": private["artifact_identity"],
            "safe_artifact_identity": private["safe_artifact_identity"],
        }],
        "retention": "immutable_module_evidence",
        "reserve_access_state": "sealed",
    }
    external["manifest_identity"] = canonical_hash(external)
    external_bytes = (json.dumps(external, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    review = build_reopened_review_artifact(
        campaign=campaign,
        predecessor_review=predecessor,
        p4_payload=p4,
        external_artifact_manifest={
            "store_version": external["store_version"],
            "manifest_identity": external["manifest_identity"],
            "sha256": sha256(external_bytes).hexdigest(),
            "artifact_count": 1,
        },
    )
    failures: dict[str, Any] = {
        "schema_version": "phase4b-m45-safe-failure-slices-v2",
        "review_artifact_identity": review["artifact_identity"],
        "slices": [
            {
                "scenario_id": "qst_0431",
                "first_failure_layer": "proposal_validation",
                "reason_code": "proposal_marker_group_invalid",
                "status": "failed",
            },
            {
                "scenario_id": "qst_0461",
                "first_failure_layer": "action_admission",
                "reason_code": "structured_marker_phrase_not_supported_by_sibling",
                "status": "failed",
            },
        ],
        "reserve_access_state": "sealed",
    }
    failures["artifact_identity"] = canonical_hash(failures)
    report = "\n".join((
        "# M45 B3 reopened diagnostic review",
        "",
        f"- Decision: `{review['qualification']['decision']}`",
        f"- Campaign: `{campaign.identity}`",
        f"- Review artifact: `{review['artifact_identity']}`",
        "- Existing embedding attempts: `8`; P4 chat attempts: `2`; total: `10`",
        f"- P4 observed chat tokens: `{review['qualification']['observed_chat_tokens']}`",
        "- Reserve: `sealed`; baseline eligible: `false`",
        "",
        "qst_0431 在 proposal schema validator 停止；qst_0461 proposal 合法，但整句 marker 与语义等价 sibling 不做字面全等，未准入 expansion。当前仍不得启动 M46。",
        "",
    ))
    _write_json(args.external_manifest_output, external)
    _write_json(args.report_dir / "m45-b3-reopened-review.json", review)
    _write_json(args.report_dir / "m45-b3-reopened-failure-slices.json", failures)
    (args.report_dir / "m45-b3-reopened-review.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "decision": review["qualification"]["decision"],
        "review_artifact_identity": review["artifact_identity"],
        "external_manifest_identity": external["manifest_identity"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
