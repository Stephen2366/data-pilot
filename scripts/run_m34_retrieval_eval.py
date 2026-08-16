"""运行 M34 external profile 的真实 Knowledge Tool retrieval Eval。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.core.config import get_settings
from engine.governance import demo_caller
from engine.rag.enterprise_cases import load_enterprise_case_split, validate_enterprise_case_split
from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from engine.rag.enterprise_retrieval_eval import run_enterprise_retrieval_eval
from engine.rag.enterprise_runtime import load_enterprise_profile_runtime
from engine.rag.enterprise_semantic import (
    KNOWLEDGE_EMBEDDING_POLICY,
    load_enterprise_semantic_runtime,
)
from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_RECIPE = PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-dataset.json"
DEFAULT_SPLIT = PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-split.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=os.environ.get("ENTERPRISE_RAG_BENCH_ROOT"))
    parser.add_argument("--dataset-recipe", type=Path, default=DEFAULT_DATASET_RECIPE)
    parser.add_argument("--case-split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--profile-root", type=Path)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument("--semantic-root", type=Path)
    parser.add_argument("--semantic-identity", help="提供时改走已完成的 Milvus semantic candidate。")
    parser.add_argument(
        "--scope",
        choices=("diagnostic_dev", "held_out", "all"),
        default="diagnostic_dev",
        help="held_out/all 只能在候选冻结后按 M34 决策门运行。",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.dataset_root is None:
        raise SystemExit("必须提供 --dataset-root 或 ENTERPRISE_RAG_BENCH_ROOT")
    audit = audit_enterprise_dataset(args.dataset_root, load_dataset_recipe(args.dataset_recipe))
    split = load_enterprise_case_split(args.case_split)
    validate_enterprise_case_split(split, audit.selected_questions, audit.question_set_identity)
    if args.scope == "diagnostic_dev":
        question_ids = split.diagnostic_dev_question_ids
    elif args.scope == "held_out":
        question_ids = split.held_out_question_ids
    else:
        question_ids = tuple(item.question_id for item in audit.selected_questions)
    profile_root = args.profile_root or args.dataset_root / "derived" / "enterprise_profiles"
    if args.semantic_identity:
        settings = get_settings()
        if not settings.dashscope_api_key:
            raise SystemExit("DASHSCOPE_API_KEY 未配置")
        semantic_root = args.semantic_root or args.dataset_root / "derived" / "enterprise_semantic"
        query_provider = DashScopeEmbeddingProvider(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_embedding_base_url,
            model=settings.qwen_embedding_model,
            dimensions=settings.qwen_embedding_dimensions,
            text_type="query",
            outbound_policy=KNOWLEDGE_EMBEDDING_POLICY,
            outbound_node_purpose="knowledge_embedding",
            outbound_data_class="public_benchmark_document",
            timeout=60,
        )
        runtime = load_enterprise_semantic_runtime(
            profile_root=profile_root,
            profile_identity=args.profile_identity,
            semantic_root=semantic_root,
            semantic_identity=args.semantic_identity,
            query_provider=query_provider,
        )
    else:
        runtime = load_enterprise_profile_runtime(
            root=profile_root, profile_identity=args.profile_identity
        )
    with runtime:
        artifact = run_enterprise_retrieval_eval(
            audit=audit,
            question_ids=question_ids,
            split_identity=split.split_identity,
            split_name=args.scope,
            tool=runtime.knowledge_tool(),
            caller=demo_caller(caller_id="m34-retrieval-eval", roles=("demo_user",)),
            profile_identity=runtime.manifest.profile_identity,
            adapter_identity=runtime.adapter.identity,
            retrieval_recipe_identity=runtime.adapter.recipe_identity,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "scope": artifact["split_name"],
                "question_count": artifact["question_count"],
                "artifact_identity": artifact["artifact_identity"],
                "overall": artifact["summaries"]["overall"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
