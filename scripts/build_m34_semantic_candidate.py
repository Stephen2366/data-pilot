"""流式构建/恢复 M34 DashScope + Milvus semantic candidate。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.core.config import get_settings
from engine.rag.enterprise_semantic import (
    KNOWLEDGE_EMBEDDING_POLICY,
    build_enterprise_semantic_candidate,
)
from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument("--semantic-root", type=Path)
    parser.add_argument("--milvus-uri", default="http://127.0.0.1:19530")
    parser.add_argument("--model", default="qwen3.7-text-embedding")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--max-units", type=int, help="provider smoke 专用；不会生成 candidate manifest。")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise SystemExit("DASHSCOPE_API_KEY 未配置")
    profile_root = args.profile_root or args.dataset_root / "derived" / "enterprise_profiles"
    semantic_root = args.semantic_root or args.dataset_root / "derived" / "enterprise_semantic"
    if args.concurrency < 1 or args.concurrency > 4:
        raise SystemExit("concurrency 必须在 1..4")
    providers = tuple(
        DashScopeEmbeddingProvider(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_embedding_base_url,
            model=args.model,
            dimensions=args.dimensions,
            text_type="document",
            outbound_policy=KNOWLEDGE_EMBEDDING_POLICY,
            outbound_node_purpose="knowledge_embedding",
            outbound_data_class="public_benchmark_document",
            timeout=60,
        )
        for _ in range(args.concurrency)
    )
    result = build_enterprise_semantic_candidate(
        profile_root=profile_root,
        profile_identity=args.profile_identity,
        semantic_root=semantic_root,
        provider=providers[0],
        parallel_providers=providers[1:],
        milvus_uri=args.milvus_uri,
        model=args.model,
        dimensions=args.dimensions,
        max_units=args.max_units,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
