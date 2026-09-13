"""M27 plan-only CLI：只生成运行前身份，不创建 Runtime 或调用模型。"""

from __future__ import annotations

import argparse
from pathlib import Path

from eval.planning import build_explicit_run_plan, write_run_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """解析显式参数并独占发布一份 plan-only 机器文件。"""

    parser = argparse.ArgumentParser(description="Build an M27 machine run plan without Runtime, DB, checkpoint, or provider calls")
    parser.add_argument("--catalog", type=Path, default=PROJECT_ROOT / "eval" / "cases" / "catalog" / "scenarios.yaml")
    parser.add_argument("--scenario", action="append", required=True)
    parser.add_argument("--pipeline-mode", choices=("baseline", "new_text2sql"), required=True)
    parser.add_argument("--schema-fusion-strategy", choices=("weighted", "rrf"), required=True)
    parser.add_argument("--replicate-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    plan = build_explicit_run_plan(
        catalog_path=args.catalog,
        scenario_ids=tuple(args.scenario),
        pipeline_mode=args.pipeline_mode,
        schema_fusion_strategy=args.schema_fusion_strategy,
        replicate_count=args.replicate_count,
    )
    write_run_plan(plan, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
