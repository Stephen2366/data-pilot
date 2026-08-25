"""M45-G：把 P4R 恢复证据固化为 additive v3 no-go review。"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from engine.phase4b.identity import canonical_hash
from eval.rag_action_diagnostics import (
    build_repair_review_artifact,
    load_repair_diagnostic_campaign,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _verified(path: Path) -> dict[str, Any]:
    """读取并校验 content-bound artifact，避免拿损坏文件做最终审查。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise ValueError(f"m45_repair_artifact_hash_mismatch:{path.name}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """稳定写出 JSON，以便 review 保存 manifest 文件哈希。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> None:
    """把 recovered P4R 证据固化为不可冒充成功的 v3 no-go review。"""

    parser = argparse.ArgumentParser(description="Build M45 repair review artifacts")
    parser.add_argument("--p4r-safe", type=Path, required=True)
    parser.add_argument("--p4r-private", type=Path, required=True)
    parser.add_argument("--external-manifest-output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m45")
    args = parser.parse_args()

    campaign = load_repair_diagnostic_campaign()
    predecessor = _verified(PROJECT_ROOT / "eval/reports/m45/m45-b3-reopened-review.json")
    p4r = _verified(args.p4r_safe)
    private = _verified(args.p4r_private)
    if (
        private.get("safe_artifact_identity") != p4r.get("artifact_identity")
        or private.get("campaign_identity") != campaign.identity
        or p4r.get("evidence_completeness")
        != "incomplete_raw_response_and_token_usage_lost"
    ):
        raise ValueError("m45_repair_private_lineage_invalid")

    external: dict[str, Any] = {
        "schema_version": "phase4b-m45-external-diagnostic-manifest-v3",
        "store_version": "phase4b-rag-action-diagnostics/v1.2.0",
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "artifacts": [{
            "path": str(args.p4r_private.name),
            "sha256": sha256(args.p4r_private.read_bytes()).hexdigest(),
            "artifact_identity": private["artifact_identity"],
            "safe_artifact_identity": private["safe_artifact_identity"],
            "evidence_completeness": "incomplete_raw_response_and_token_usage_lost",
        }],
        "retention": "immutable_module_evidence",
        "reserve_access_state": "sealed",
    }
    external["manifest_identity"] = canonical_hash(external)
    external_bytes = (json.dumps(external, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    review = build_repair_review_artifact(
        campaign=campaign,
        predecessor_review=predecessor,
        p4r_payload=p4r,
        external_artifact_manifest={
            "store_version": external["store_version"],
            "manifest_identity": external["manifest_identity"],
            "sha256": sha256(external_bytes).hexdigest(),
            "artifact_count": 1,
            "evidence_completeness": "incomplete_raw_response_and_token_usage_lost",
        },
    )
    failures: dict[str, Any] = {
        "schema_version": "phase4b-m45-safe-failure-slices-v3",
        "review_artifact_identity": review["artifact_identity"],
        "slices": [
            {
                "scenario_id": "qst_0461",
                "status": "passed",
                "reason_code": "offline_proposal_replay_expansion_passed",
            },
            {
                "scenario_id": "qst_0431",
                "status": "failed",
                "first_failure_layer": "proposal_coverage_validation",
                "reason_code": "proposal_no_unsupported_requirement",
            },
            {
                "scenario_id": "M45-P4R",
                "status": "evidence_incomplete",
                "first_failure_layer": "probe_artifact_persistence",
                "reason_code": "raw_response_and_token_usage_lost_after_runner_exception",
            },
        ],
        "reserve_access_state": "sealed",
    }
    failures["artifact_identity"] = canonical_hash(failures)
    report = "\n".join((
        "# M45 B3 repair diagnostic review",
        "",
        f"- Decision: `{review['qualification']['decision']}`",
        f"- Campaign: `{campaign.identity}`",
        f"- Review artifact: `{review['artifact_identity']}`",
        "- Provider attempts: `8 embedding + 3 chat = 11 total`",
        "- P4R chat tokens: `unobserved`（不得估算为 0）",
        "- Reserve: `sealed`; baseline eligible: `false`",
        "",
        "qst_0461 的 proposal 离线重放已通过；qst_0431 的唯一重验仍被本地 coverage validator 判定为没有未覆盖 requirement，因此没有触发 expansion。runner 异常还导致该次响应与 token usage 未落盘。按冻结门，M45/B3 仍为 no-go，M46 不得启动。",
        "",
    ))
    _write_json(args.external_manifest_output, external)
    _write_json(args.report_dir / "m45-b3-repair-review.json", review)
    _write_json(args.report_dir / "m45-b3-repair-failure-slices.json", failures)
    (args.report_dir / "m45-b3-repair-review.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "decision": review["qualification"]["decision"],
        "review_artifact_identity": review["artifact_identity"],
        "external_manifest_identity": external["manifest_identity"],
        "provider_attempts": review["qualification"]["provider_attempts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
