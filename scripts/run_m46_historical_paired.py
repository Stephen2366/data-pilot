"""M46-F：同一 logical run 下顺序执行 historical dev Pipeline/Subgraph 两臂。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from engine.phase4b.identity import canonical_hash, file_sha256
from eval.rag_e2e_review import compare_completed
from scripts.preflight_m46_historical_paired import build_preflight

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _aggregate_b4_usage(artifact: dict[str, Any]) -> dict[str, Any]:
    """从 execution 同源投影汇总 M46 usage，并保留完整性而非伪造精确总数。"""

    numeric_keys = (
        "composer_requests",
        "composer_total_tokens",
        "formation_requests",
        "formation_total_tokens",
        "retrieval_requests_known",
        "provider_requests_known_total",
        "provider_tokens_known_total",
    )
    totals = {key: 0 for key in numeric_keys}
    projected = 0
    retrieval_complete = True
    source_consistent = True
    for execution in artifact.get("executions") or ():
        projection = (execution.get("rag_diagnostics") or {}).get("b4_acquisition") or {}
        if projection.get("projection_status") == "not_observed":
            retrieval_complete = False
        else:
            projected += 1
        source_consistent = source_consistent and projection.get("source_consistent") is True
        usage = projection.get("provider_usage") or {}
        retrieval_complete = retrieval_complete and usage.get("retrieval_attempts_observed") is True
        for key in numeric_keys:
            totals[key] += int(usage.get(key, 0) or 0)
    execution_count = len(artifact.get("executions") or ())
    return {
        **totals,
        "execution_count": execution_count,
        "projected_execution_count": projected,
        "request_count_complete": projected == execution_count and retrieval_complete and source_consistent,
        # embedding provider 不返回 token usage，token 总量只能陈述 chat 的 known lower bound。
        "token_count_complete": False,
        "source_consistent": source_consistent,
    }


def _migrate_launch_failure(manifest: dict[str, Any]) -> dict[str, Any]:
    """把旧 active failure 字段迁入不可混淆的启动 lineage。"""

    migrated = dict(manifest)
    if "failed_arm" not in migrated:
        return migrated
    history = list(migrated.get("launch_history") or ())
    history.append({
        "status": "failed",
        "arm": migrated.pop("failed_arm"),
        "exit_code": migrated.pop("failed_exit_code", None),
    })
    migrated["launch_history"] = history
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path, required=True)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument("--semantic-root", type=Path, required=True)
    parser.add_argument("--semantic-identity", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m46")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=PROJECT_ROOT / ".agent_work/temp/m46-historical-paired",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    frozen = json.loads(args.preflight.read_text(encoding="utf-8"))
    current = build_preflight(dataset_root=args.dataset_root)
    if frozen.get("candidate_identity") != current.get("candidate_identity"):
        raise SystemExit("m46_candidate_identity_drift")
    if frozen.get("preflight", {}).get("status") != "ready_for_historical_authorization":
        raise SystemExit("m46_historical_preflight_not_ready")

    parent_root = args.checkpoint_dir / args.run_id
    manifest_path = parent_root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": "phase4b-b4-paired-run-manifest-v1",
        "run_id": args.run_id,
        "candidate_identity": frozen["candidate_identity"],
        "partition": "diagnostic_dev",
        "suite": "full",
        "arm_order": ["pipeline", "subgraph"],
        "status": "running",
        "completed_arms": [],
        "reserve_state": "sealed",
    }
    if args.resume and manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("run_id") != args.run_id or existing.get("candidate_identity") != frozen["candidate_identity"]:
            raise SystemExit("m46_paired_resume_identity_mismatch")
        manifest = existing
        # 旧版首次失败字段描述的是某次 launch，不是最终 arm 状态。resume 时迁移到 lineage，
        # 既保留事故证据，也避免 completed manifest 同时声称“当前仍有失败臂”。
        manifest = _migrate_launch_failure(manifest)
    _write_json(manifest_path, manifest)

    artifact_dir = args.output_dir / "artifacts"
    arm_artifacts: dict[str, Path] = {}
    for arm in ("pipeline", "subgraph"):
        arm_run_id = f"{args.run_id}-{arm}"
        artifact_path = artifact_dir / f"{arm_run_id}.json"
        arm_artifacts[arm] = artifact_path
        if arm in manifest.get("completed_arms", []):
            if not artifact_path.is_file():
                raise SystemExit("m46_paired_completed_arm_missing")
            continue
        command = [
            sys.executable, "-m", "eval.run_rag_external_eval",
            "--dataset-root", str(args.dataset_root),
            "--profile-root", str(args.profile_root),
            "--profile-identity", args.profile_identity,
            "--retrieval-mode", "semantic",
            "--semantic-root", str(args.semantic_root),
            "--semantic-identity", args.semantic_identity,
            "--partition", "diagnostic_dev",
            "--suite", "full",
            "--phase4b-strategy", arm,
            "--run-id", arm_run_id,
            "--report", str(args.output_dir / f"{arm_run_id}.md"),
            "--triage", str(args.output_dir / f"{arm_run_id}-triage.json"),
            "--timeout", str(args.timeout),
            "--checkpoint-dir", str(parent_root / "arms"),
            "--artifact-dir", str(artifact_dir),
        ]
        if args.resume:
            command.append("--resume")
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)  # noqa: S603 - 全参数闭集。
        if completed.returncode != 0:
            manifest["status"] = "inconclusive"
            manifest["failed_arm"] = arm
            manifest["failed_exit_code"] = completed.returncode
            _write_json(manifest_path, manifest)
            raise SystemExit(completed.returncode)
        manifest["completed_arms"] = [*manifest.get("completed_arms", []), arm]
        _write_json(manifest_path, manifest)

    pipeline = json.loads(arm_artifacts["pipeline"].read_text(encoding="utf-8"))
    subgraph = json.loads(arm_artifacts["subgraph"].read_text(encoding="utf-8"))
    comparison = compare_completed(
        pipeline,
        subgraph,
        allowed_runtime_differences=("runtime_family",),
    )
    comparison["m46_provider_usage"] = {
        "pipeline": _aggregate_b4_usage(pipeline),
        "subgraph": _aggregate_b4_usage(subgraph),
        "interpretation_boundary": (
            "requests 在 projection/retrieval observed 时可闭合；tokens 不含 embedding token，"
            "只表示 Composer + formation 的已知总量。"
        ),
    }
    comparison_path = args.output_dir / f"{args.run_id}-compare.json"
    _write_json(comparison_path, comparison)
    paired_payload = {
        "schema_version": "phase4b-b4-historical-paired-artifact-v1",
        "status": "completed_pending_review",
        "run_id": args.run_id,
        "candidate_identity": frozen["candidate_identity"],
        "arm_artifacts": {
            arm: {
                "artifact_identity": payload["artifact_identity"],
                "sha256": file_sha256(arm_artifacts[arm]),
            }
            for arm, payload in (("pipeline", pipeline), ("subgraph", subgraph))
        },
        "comparison_identity": canonical_hash(comparison),
        "reserve_state": "sealed",
    }
    paired = {**paired_payload, "artifact_identity": canonical_hash(paired_payload)}
    paired_path = args.output_dir / f"{args.run_id}-paired.json"
    _write_json(paired_path, paired)
    manifest.update({
        "status": "completed_pending_review",
        "paired_artifact_identity": paired["artifact_identity"],
        "comparison_identity": paired["comparison_identity"],
    })
    manifest.pop("failed_arm", None)
    manifest.pop("failed_exit_code", None)
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": paired["status"],
        "run_id": args.run_id,
        "paired_artifact": str(paired_path),
        "artifact_identity": paired["artifact_identity"],
        "reserve_state": "sealed",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
