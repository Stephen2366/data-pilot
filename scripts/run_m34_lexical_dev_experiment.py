"""在冻结 60 题 dev split 上运行 full-corpus local lexical unit 对照。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from engine.rag.enterprise_cases import (
    load_enterprise_case_split,
    validate_enterprise_case_split,
)
from engine.rag.enterprise_dataset import (
    audit_enterprise_dataset,
    canonical_identity,
    load_dataset_recipe,
)
from engine.rag.enterprise_units import (
    PARAGRAPH_1200_RECIPE,
    PARAGRAPH_2400_OVERLAP_1_RECIPE,
    PARAGRAPH_2400_RECIPE,
    WHOLE_DOCUMENT_RECIPE,
)
from engine.rag.enterprise_lexical_experiment import run_lexical_dev_experiment


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_RECIPE = (
    PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-dataset.json"
)
DEFAULT_SPLIT = (
    PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-split.json"
)
CANDIDATES = (
    WHOLE_DOCUMENT_RECIPE,
    PARAGRAPH_1200_RECIPE,
    PARAGRAPH_2400_RECIPE,
    PARAGRAPH_2400_OVERLAP_1_RECIPE,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=os.environ.get("ENTERPRISE_RAG_BENCH_ROOT"),
    )
    parser.add_argument("--dataset-recipe", type=Path, default=DEFAULT_DATASET_RECIPE)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.dataset_root is None:
        raise SystemExit("必须提供 --dataset-root 或 ENTERPRISE_RAG_BENCH_ROOT")
    if args.work_dir.exists() and any(args.work_dir.iterdir()):
        raise SystemExit(f"work-dir 必须为空或不存在：{args.work_dir}")
    args.work_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_enterprise_dataset(
        args.dataset_root, load_dataset_recipe(args.dataset_recipe)
    )
    split = load_enterprise_case_split(args.split)
    validate_enterprise_case_split(
        split, audit.selected_questions, audit.question_set_identity
    )
    artifacts = []
    for recipe in CANDIDATES:
        artifacts.append(
            run_lexical_dev_experiment(
                audit,
                split,
                recipe,
                args.work_dir / f"{recipe.recipe_version}.sqlite3",
            )
        )
    comparison = {
        "comparison_version": "enterprise-lexical-unit-comparison-v1",
        "lifecycle_status": "completed",
        "dataset_identity": audit.dataset_identity,
        "split_identity": split.split_identity,
        "candidate_artifacts": artifacts,
    }
    comparison["comparison_identity"] = canonical_identity(comparison)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
