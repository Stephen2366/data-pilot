"""M45-H：把 P5 与 v3 predecessor 固化为 additive v4 final review。"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from engine.phase4b.identity import canonical_hash
from eval.rag_action_diagnostics import (
    build_continuation_review_artifact,
    load_continuation_diagnostic_campaign,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _verified(path: Path) -> dict[str, Any]:
    """读取 artifact 并复算 canonical identity，拒绝被修改的历史证据。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise ValueError(f"m45_continuation_artifact_hash_mismatch:{path.name}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """写出换行结尾的稳定 JSON，便于 SHA-256 manifest 对账。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> None:
    """核验 P5/private lineage，生成 external manifest 与仓库安全 v4 review。"""

    parser = argparse.ArgumentParser(description="Build M45 continuation review artifacts")
    parser.add_argument("--p5-safe", type=Path, required=True)
    parser.add_argument("--p5-private", type=Path, required=True)
    parser.add_argument("--external-manifest-output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m45")
    args = parser.parse_args()

    campaign = load_continuation_diagnostic_campaign()
    predecessor = _verified(PROJECT_ROOT / "eval/reports/m45/m45-b3-repair-review.json")
    p5 = _verified(args.p5_safe)
    private = _verified(args.p5_private)
    if (
        private.get("safe_artifact_identity") != p5.get("artifact_identity")
        or private.get("campaign_identity") != campaign.identity
        or p5.get("gate") != "passed"
    ):
        raise ValueError("m45_continuation_private_lineage_invalid")

    external: dict[str, Any] = {
        "schema_version": "phase4b-m45-external-diagnostic-manifest-v4",
        "store_version": "phase4b-rag-action-diagnostics/v1.3.0",
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "artifacts": [{
            "path": str(args.p5_private.name),
            "sha256": sha256(args.p5_private.read_bytes()).hexdigest(),
            "artifact_identity": private["artifact_identity"],
            "safe_artifact_identity": private["safe_artifact_identity"],
        }],
        "retention": "immutable_module_evidence",
        "reserve_access_state": "sealed",
    }
    external["manifest_identity"] = canonical_hash(external)
    external_bytes = (json.dumps(external, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    review = build_continuation_review_artifact(
        campaign=campaign,
        predecessor_review=predecessor,
        p5_payload=p5,
        external_artifact_manifest={
            "store_version": external["store_version"],
            "manifest_identity": external["manifest_identity"],
            "sha256": sha256(external_bytes).hexdigest(),
            "artifact_count": 1,
        },
    )
    report = "\n".join((
        "# M45 B3 continuation diagnostic review",
        "",
        f"- Decision: `{review['qualification']['decision']}`",
        f"- Campaign: `{campaign.identity}`",
        f"- Review artifact: `{review['artifact_identity']}`",
        "- P5 provider attempts: `0`; module cumulative: `8 embedding + 3 chat = 11`",
        "- Action cards: `query rewrite = completed`, `context expansion = completed`",
        "- Reserve: `sealed`; baseline eligible: `false`",
        "",
        "qst_0431 的既有 coverage 虽显示完整，但 procedure boundary trigger 发现 selected fragment 后仍有同文档 forward unit；P5 确定性补入 2 条后续 Evidence，未调用 retrieval、embedding、chat proposal 或 Composer。M45/B3 已满足 M46 handoff 门。",
        "",
    ))
    _write_json(args.external_manifest_output, external)
    _write_json(args.report_dir / "m45-b3-continuation-review.json", review)
    (args.report_dir / "m45-b3-continuation-review.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "decision": review["qualification"]["decision"],
        "review_artifact_identity": review["artifact_identity"],
        "external_manifest_identity": external["manifest_identity"],
        "provider_attempts": review["qualification"]["provider_attempts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
