"""按 difficulty suite × 冻结 partition 运行 EnterpriseRAG-Bench 产品 Harness RAG Eval。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from engine.rag.answer_flow import ANSWER_FLOW_RUNTIME_IDENTITY, RAGAnswerFlow
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.enterprise_product_runtime import (
    EnterpriseProductRuntimeConfig,
    load_enterprise_product_runtime,
)
from engine.rag.enterprise_semantic import KNOWLEDGE_GENERATION_POLICY
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.phase4b.rag_recovery_requirement_proposal import make_b4_qwen_requirement_proposal_client
from engine.phase4b.rag_strategy import configure_external_acquisition
from eval.rag_e2e_contracts import RAGResolvedRuntime
from eval.rag_e2e_runner import run_rag_eval
from eval.rag_e2e_runtime import ComposerRuntimeMetadata, FixedRAGEvalRouter, RAGProductExecutor
from eval.rag_external_catalog import build_external_scenario_selector, load_external_rag_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_external_resolved_runtime(
    *,
    product_identity: Any,
    bundle: Any,
    composer: Any,
    model: str,
    timeout_seconds: float,
    runtime_family: str = "phase4-rag-external-product-harness-fixed-route-v1",
) -> RAGResolvedRuntime:
    """把共用 resolver identity 投影为 artifact 合同，避免 CLI 另拼一套 backend 事实。"""

    return RAGResolvedRuntime(
        runtime_family=runtime_family,
        answer_flow_identity=ANSWER_FLOW_RUNTIME_IDENTITY,
        composer_identity=composer.identity,
        model=model,
        provider="qwen",
        timeout_seconds=timeout_seconds,
        retry_count=0,
        release_identity=bundle.release_identity,
        corpus_identity=bundle.corpus_identity,
        retrieval_adapter_identity=product_identity.retrieval_adapter_identity,
        retrieval_recipe_identity=product_identity.retrieval_recipe_identity,
        authorization_policy_identity=bundle.authorization_policy_identity,
        release_outbound_policy_identity=bundle.outbound_policy_identity,
        generation_outbound_policy_identity=KNOWLEDGE_GENERATION_POLICY.identity,
        caller_fixture_identity="phase4-rag-e2e-test-fixture-v1",
        route_policy_identity=FixedRAGEvalRouter.identity,
        retrieval_mode=product_identity.retrieval_mode,
        semantic_identity=product_identity.semantic_identity,
        semantic_manifest_identity=product_identity.semantic_manifest_identity,
        embedding_provider=product_identity.embedding_provider,
        embedding_model=product_identity.embedding_model,
        embedding_dimensions=product_identity.embedding_dimensions,
        milvus_collection=product_identity.milvus_collection,
        unit_set_identity=product_identity.unit_set_identity,
    )


def main() -> None:
    """一次只运行一个冻结 partition；不会自动从 dev 扩到 held-out。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path, required=True)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument(
        "--retrieval-mode",
        choices=("semantic", "lexical"),
        help="Enterprise retrieval；省略时使用配置默认（M44A 默认 semantic）。",
    )
    parser.add_argument("--semantic-root", type=Path)
    parser.add_argument("--semantic-identity")
    parser.add_argument(
        "--partition",
        choices=("diagnostic_dev", "held_out", "all"),
        default="diagnostic_dev",
        help="默认 diagnostic_dev（日常诊断集）；held_out/all 必须显式指定。",
    )
    selector_group = parser.add_mutually_exclusive_group()
    selector_group.add_argument(
        "--suite",
        choices=("smoke", "basic", "core", "hard", "reliability", "full"),
        help="难度/协议套件；与 partition 做交集。smoke/reliability 只允许 diagnostic_dev。",
    )
    selector_group.add_argument(
        "--scenario",
        help="精确单题诊断；仍受 partition 约束，不能从默认 dev 越到 held-out。",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--phase4b-strategy",
        choices=("pipeline", "subgraph"),
        help="M46 paired arm；省略时保持 M41 legacy runtime identity。客户端请求仍无开关。",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--checkpoint-dir", type=Path, default=PROJECT_ROOT / ".agent_work/temp/m41-rag-external-checkpoints")
    parser.add_argument("--artifact-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m41-rag-external-artifacts")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.dashscope_api_key:
        raise SystemExit("DASHSCOPE_API_KEY 未配置")
    catalog, selector = load_external_rag_catalog(
        dataset_root=args.dataset_root,
        dataset_recipe_path=PROJECT_ROOT / "eval/cases/enterprise-rag-bench-v1.0.0-dataset.json",
        split_path=PROJECT_ROOT / "eval/cases/enterprise-rag-bench-v1.0.0-split.json",
        partition=args.partition,
        suite=args.suite or "full",
    )
    if args.scenario:
        selector = build_external_scenario_selector(
            catalog=catalog,
            partition=args.partition,
            scenario_id=args.scenario,
        )
    composer = make_qwen_evidence_composer(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.qwen_model or "qwen3.7-plus",
        timeout=args.timeout,
    )
    artifact_path = args.artifact_dir / f"{args.run_id}.json"
    triage_path = args.triage or args.report.with_name(f"{args.report.stem}-triage.json")
    runtime_config = EnterpriseProductRuntimeConfig(
        retrieval_mode=args.retrieval_mode or settings.enterprise_rag_retrieval_mode,
        profile_root=args.profile_root,
        profile_identity=args.profile_identity,
        semantic_root=(
            args.semantic_root
            or settings.enterprise_rag_semantic_root
            or args.dataset_root / "derived" / "enterprise_semantic"
        ),
        semantic_identity=args.semantic_identity or settings.enterprise_rag_semantic_identity,
        dashscope_api_key=settings.dashscope_api_key,
        dashscope_embedding_base_url=settings.dashscope_embedding_base_url,
        embedding_model=settings.qwen_embedding_model,
        embedding_dimensions=settings.qwen_embedding_dimensions,
        timeout_seconds=args.timeout,
        allow_cross_thread=True,
    )
    with load_enterprise_product_runtime(config=runtime_config) as product:
        external = product.runtime
        identity = product.identity
        bundle = external.bundle
        resolved = build_external_resolved_runtime(
            product_identity=identity,
            bundle=bundle,
            composer=composer,
            model=settings.qwen_model or "qwen3.7-plus",
            timeout_seconds=args.timeout,
            runtime_family=(
                f"phase4b-b4-external-product-harness:{args.phase4b_strategy}:v1"
                if args.phase4b_strategy
                else "phase4-rag-external-product-harness-fixed-route-v1"
            ),
        )

        def answer_flow_factory() -> RAGAnswerFlow:
            """M41 legacy 与 M46 arm 共用产品组装；strategy 只来自本次可信 RunSpec。"""

            knowledge_tool = external.knowledge_tool()
            retrieval_snapshot = identity.safe_projection()
            if args.phase4b_strategy is None:
                return RAGAnswerFlow(
                    knowledge_tool=knowledge_tool,
                    composer=composer,
                    active_loader=external.active_loader,
                    retrieval_snapshot=retrieval_snapshot,
                )
            proposal_transport = None
            expansion_adapter = None
            if args.phase4b_strategy == "subgraph":
                proposal_transport = make_b4_qwen_requirement_proposal_client(
                    api_key=settings.dashscope_api_key,
                    base_url=settings.dashscope_base_url,
                    model=settings.qwen_model or "qwen3.7-plus",
                    timeout=args.timeout,
                )
                expansion_adapter = EnterpriseSiblingExpansionAdapter(external)
            configured = configure_external_acquisition(
                strategy=args.phase4b_strategy,
                knowledge_tool=knowledge_tool,
                active_loader=external.active_loader,
                proposal_transport=proposal_transport,
                expansion_adapter=expansion_adapter,
            )
            return RAGAnswerFlow(
                knowledge_tool=knowledge_tool,
                composer=composer,
                active_loader=external.active_loader,
                evidence_acquirer=configured.acquirer,
                retrieval_snapshot={
                    **retrieval_snapshot,
                    "acquisition_strategy": configured.safe_projection(),
                },
            )

        executor = RAGProductExecutor(
            composer=composer,
            runtime_metadata=ComposerRuntimeMetadata(
                model=settings.qwen_model or "qwen3.7-plus",
                timeout_seconds=args.timeout,
                generation_outbound_policy_identity=KNOWLEDGE_GENERATION_POLICY.identity,
            ),
            trace_root=args.checkpoint_dir / args.run_id / "traces",
            answer_flow_factory=answer_flow_factory,
            resolved_runtime_override=resolved,
            router=FixedRAGEvalRouter(),
            knowledge_runtime_kind="external_profile",
        )
        artifact = run_rag_eval(
            catalog=catalog,
            selector=selector,
            run_id=args.run_id,
            executor=executor,
            checkpoint_root=args.checkpoint_dir,
            artifact_path=artifact_path,
            report_path=args.report,
            triage_path=triage_path,
            resume=args.resume,
        )
    print(json.dumps({
        "status": artifact["status"],
        "artifact_identity": artifact["artifact_identity"],
        "gate": artifact["gate"],
        "artifact": str(artifact_path),
        "report": str(args.report),
        "triage": str(triage_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
