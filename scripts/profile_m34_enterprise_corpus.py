"""扫描并 profile M34 三来源规范化文本，不生成 chunk 或索引。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from engine.rag.enterprise_parser import DEFAULT_PARSER_RECIPE, profile_normalized_corpus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_RECIPE = (
    PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-dataset.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=os.environ.get("ENTERPRISE_RAG_BENCH_ROOT"),
    )
    parser.add_argument("--dataset-recipe", type=Path, default=DEFAULT_DATASET_RECIPE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dataset_root is None:
        raise SystemExit("必须提供 --dataset-root 或 ENTERPRISE_RAG_BENCH_ROOT")

    audit = audit_enterprise_dataset(
        args.dataset_root, load_dataset_recipe(args.dataset_recipe)
    )
    profile = profile_normalized_corpus(audit, DEFAULT_PARSER_RECIPE)
    rendered = json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
