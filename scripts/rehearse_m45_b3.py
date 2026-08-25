"""M45-D：零 provider 汇总 immutable Probe，生成安全 no-go review artifact。"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from engine.phase4b.identity import canonical_hash
from eval.rag_action_diagnostics import REVIEW_PROBE_KEYS, build_review_artifact, load_diagnostic_campaign


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAFE_INPUTS = {
    "M45-P1": PROJECT_ROOT / ".agent_work/temp/m45-p1-first.json",
    "M45-P2-R1": PROJECT_ROOT / ".agent_work/temp/m45-p2-first.json",
    "M45-P2-R2": PROJECT_ROOT / ".agent_work/temp/m45-p2-round2.json",
    "M45-P2C": PROJECT_ROOT / ".agent_work/temp/m45-p2c-first.json",
    "M45-P2D": PROJECT_ROOT / ".agent_work/temp/m45-p2d-first.json",
    "M45-P3": PROJECT_ROOT / ".agent_work/temp/m45-p3-first.json",
}


def _read_verified(path: Path) -> dict[str, Any]:
    """读取并核验 campaign lineage 中的一份 Probe artifact。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise ValueError(f"artifact_identity_mismatch:{path.name}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    """稳定写出仓库安全或项目外 manifest JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _assert_repository_safe(payload: Any) -> None:
    """仓库投影不允许出现正文、题面或 gold 字段。"""

    forbidden = {"question", "content", "gold", "gold_answer", "answer_facts", "prompt", "thought"}
    if isinstance(payload, dict):
        overlap = forbidden & {str(key).casefold() for key in payload}
        if overlap:
            raise ValueError(f"repository_projection_unsafe:{','.join(sorted(overlap))}")
        for value in payload.values():
            _assert_repository_safe(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_repository_safe(value)


def build_outputs(*, private_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """汇总 P1～P3 与 private manifest，构建首轮 C5 review 输出。"""

    campaign = load_diagnostic_campaign()
    probes = {key: _read_verified(DEFAULT_SAFE_INPUTS[key]) for key in REVIEW_PROBE_KEYS}
    private_files = {
        "M45-P2-R1": private_root / "probes/m45-p2-first-private.json",
        "M45-P2-R2": private_root / "probes/m45-p2-round2-private.json",
        "M45-P2C": private_root / "probes/m45-p2c-first-private.json",
        "M45-P2D": private_root / "probes/m45-p2d-first-private.json",
        "M45-P3": private_root / "probes/m45-p3-first-private.json",
    }
    external_entries = []
    for key, path in private_files.items():
        private = _read_verified(path)
        external_entries.append({
            "probe_key": key,
            "relative_path": path.relative_to(private_root).as_posix(),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "artifact_identity": private["artifact_identity"],
            "safe_artifact_identity": private.get("safe_artifact_identity"),
        })
    external_manifest: dict[str, Any] = {
        "schema_version": "phase4b-m45-external-diagnostic-manifest-v1",
        "store_version": "phase4b-rag-action-diagnostics/v1.0.0",
        "campaign_identity": campaign.identity,
        "artifacts": external_entries,
        "retention": "immutable_module_evidence",
        "reserve_access_state": "sealed",
    }
    external_manifest["manifest_identity"] = canonical_hash(external_manifest)
    external_manifest_bytes = (
        json.dumps(external_manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    # manifest 文件 hash 由 caller 写盘后补进仓库 artifact；这里先用 canonical payload hash，
    # 它与外部正文文件的逐项 SHA 一起形成稳定关联。
    review = build_review_artifact(
        campaign=campaign,
        probe_payloads=probes,
        external_artifact_manifest={
            "store_version": external_manifest["store_version"],
            "manifest_identity": external_manifest["manifest_identity"],
            "sha256": sha256(external_manifest_bytes).hexdigest(),
            "artifact_count": len(external_entries),
        },
    )
    failure_slices = {
        "schema_version": "phase4b-m45-safe-failure-slices-v1",
        "review_artifact_identity": review["artifact_identity"],
        "slices": [
            {
                "scenario_id": scenario_id,
                "first_failure_layer": "action_admission",
                "reason_code": "direct_expansion_trigger_not_observed",
                "observed_action": "stop",
                "expected_action": "context_expansion_candidate",
                "status": "failed",
            }
            for scenario_id in ("qst_0431", "qst_0461")
        ],
        "reserve_access_state": "sealed",
    }
    failure_slices["artifact_identity"] = canonical_hash(failure_slices)
    report = "\n".join((
        "# M45 B3 diagnostic review",
        "",
        "- Decision: `review_required/no_go`",
        f"- Campaign: `{campaign.identity}`",
        f"- Review artifact: `{review['artifact_identity']}`",
        "- Provider attempts: `8 / 8`; chat/model/Composer/tokens: `0`",
        "- Rewrite card: `completed`（business gain + external target fragment + bounded continuation）",
        "- Context expansion card: `failed`（continuation passed；两个 direct expansion trigger 均未观察到）",
        "- Reserve: `sealed`; baseline eligible: `false`",
        "",
        "## Review conclusion",
        "",
        "P2D 证明同文档 sibling expansion 能补齐被 chunk 分散的证据；P3 的两个冻结场景在 initial Evidence 后没有形成 deterministic unsupported requirement，因此安全停在 stop。M46 的两卡全绿与同 runtime Observation-driven choice 条件未满足，不能开工。",
        "",
        "下一步必须先另行确认并修订 M45 plan；不得重跑 P3、换题、扩大 provider 额度或解封 reserve。",
        "",
    ))
    _assert_repository_safe(review)
    _assert_repository_safe(failure_slices)
    return external_manifest, review, failure_slices, report


def main() -> None:
    """解析外部证据根并执行首轮 M45 离线 qualification rehearsal。"""

    parser = argparse.ArgumentParser(description="Build M45 deterministic review artifacts")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--external-manifest-output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m45")
    args = parser.parse_args()
    external, review, failures, report = build_outputs(private_root=args.private_root)
    _write_json(args.external_manifest_output, external)
    _write_json(args.report_dir / "m45-b3-diagnostic-review.json", review)
    _write_json(args.report_dir / "m45-b3-failure-slices.json", failures)
    (args.report_dir / "m45-b3-review.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "decision": review["qualification"]["decision"],
        "review_artifact_identity": review["artifact_identity"],
        "external_manifest_identity": external["manifest_identity"],
        "provider_attempts": review["qualification"]["provider_attempts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
