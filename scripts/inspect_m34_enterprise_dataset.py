"""只读检查 EnterpriseRAG-Bench v1.0.0，并输出轻量 JSON 摘要。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECIPE = PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-dataset.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=os.environ.get("ENTERPRISE_RAG_BENCH_ROOT"),
        help="项目外 v1.0.0 根目录；也可通过 ENTERPRISE_RAG_BENCH_ROOT 提供。",
    )
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument(
        "--output",
        type=Path,
        help="可选 JSON 输出；开发期请写入 .agent_work/temp/。未提供时打印到 stdout。",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.dataset_root is None:
        raise SystemExit("必须提供 --dataset-root 或 ENTERPRISE_RAG_BENCH_ROOT")
    recipe = load_dataset_recipe(args.recipe)
    audit = audit_enterprise_dataset(args.dataset_root, recipe)
    rendered = json.dumps(audit.summary(), ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
