"""M27 review bundle 的 CLI：只读取已完成 run 和短期 checkpoint，不执行 Pipeline 或 LLM。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.catalog import load_catalog
from eval.review import apply_review_verdicts, build_review_bundle, write_review_json, write_review_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """生成待复核包，或将外部提供的 Codex/manual verdict 写入同一份旁路证据。"""

    parser = argparse.ArgumentParser(description="Build an M27 review bundle from one completed EvalRun")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--catalog", type=Path, default=PROJECT_ROOT / "eval" / "cases" / "catalog" / "scenarios.yaml")
    parser.add_argument("--artifact-dir", type=Path, default=PROJECT_ROOT / "eval" / "reports" / "m27-artifacts")
    parser.add_argument("--checkpoint-root", type=Path, default=PROJECT_ROOT / ".codex" / "temp_work" / "m27-checkpoints")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "eval" / "reports" / "m27-reviews")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--verdicts-json", type=Path)
    parser.add_argument("--max-result-rows", type=int, default=3)
    args = parser.parse_args(argv)

    bundle = build_review_bundle(
        run_id=args.run_id,
        catalog=load_catalog(args.catalog),
        artifact_path=args.artifact_dir / f"{args.run_id}.json",
        checkpoint_root=args.checkpoint_root,
        reviewer=args.reviewer,
        max_result_rows=args.max_result_rows,
    )
    if args.verdicts_json:
        verdicts = json.loads(args.verdicts_json.read_text(encoding="utf-8"))
        if not isinstance(verdicts, dict):
            raise ValueError("review verdicts must be a JSON object keyed by scenario_id")
        bundle = apply_review_verdicts(bundle, verdicts)
    json_path = args.output_dir / f"{args.run_id}-review.json"
    markdown_path = args.output_dir / f"{args.run_id}-review.md"
    write_review_json(bundle, json_path)
    write_review_markdown(bundle, markdown_path)
    print(f"review_json={json_path}")
    print(f"review_report={markdown_path}")
    print(f"review_records={len(bundle['records'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
