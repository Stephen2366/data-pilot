"""检查 EnterpriseRAG-Bench profile/semantic/Milvus 是否可供产品 runtime 使用。

本脚本不执行检索、不调用 embedding/Composer，也不会创建、reset 或重建 collection；它只
复用 M44A resolver 的强身份校验并输出安全摘要，适合在启动 Uvicorn/Eval 前做 preflight。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from engine.rag.enterprise_product_runtime import (
    EnterpriseProductRuntimeConfig,
    load_enterprise_product_runtime,
)
from engine.rag.retrieval import RetrievalAdapterError


def main() -> None:
    """解析可信配置并恰好 acquire/release 一次 runtime。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path)
    parser.add_argument("--profile-identity")
    parser.add_argument("--semantic-root", type=Path)
    parser.add_argument("--semantic-identity")
    parser.add_argument("--retrieval-mode", choices=("semantic", "lexical"))
    args = parser.parse_args()
    settings = get_settings()
    config = EnterpriseProductRuntimeConfig(
        retrieval_mode=args.retrieval_mode or settings.enterprise_rag_retrieval_mode,
        profile_root=args.profile_root or settings.enterprise_rag_profile_root,
        profile_identity=args.profile_identity or settings.enterprise_rag_profile_identity,
        semantic_root=args.semantic_root or settings.enterprise_rag_semantic_root,
        semantic_identity=args.semantic_identity or settings.enterprise_rag_semantic_identity,
        dashscope_api_key=settings.dashscope_api_key,
        dashscope_embedding_base_url=settings.dashscope_embedding_base_url,
        embedding_model=settings.qwen_embedding_model,
        embedding_dimensions=settings.qwen_embedding_dimensions,
        timeout_seconds=settings.llm_timeout_seconds,
        allow_cross_thread=True,
    )
    try:
        with load_enterprise_product_runtime(config=config) as product:
            result = {
                "status": "ready",
                "runtime_identity": product.identity.safe_projection(),
                "embedding_transport_called": False,
                "composer_called": False,
            }
    except RetrievalAdapterError as exc:
        raise SystemExit(
            json.dumps(
                {
                    "status": "unavailable",
                    "reason_code": exc.reason_code,
                    "runtime_identity": None,
                },
                ensure_ascii=False,
            )
        ) from None
    except Exception as exc:
        # profile verifier/Milvus SDK 可能抛出自己的异常；preflight 只暴露稳定分类和类型，
        # 绝不把含本机绝对路径、URI 或 provider 细节的异常正文直接打印到终端/CI。
        raise SystemExit(
            json.dumps(
                {
                    "status": "unavailable",
                    "reason_code": "enterprise_rag_runtime_unavailable",
                    "exception_type": type(exc).__name__,
                    "runtime_identity": None,
                },
                ensure_ascii=False,
            )
        ) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
