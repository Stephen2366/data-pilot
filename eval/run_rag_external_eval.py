"""按 difficulty suite × 冻结 partition 运行 EnterpriseRAG-Bench 产品 Harness RAG Eval。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from engine.rag.answer_flow import ANSWER_FLOW_RUNTIME_IDENTITY, RAGAnswerFlow
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.enterprise_runtime import load_enterprise_profile_runtime
from engine.rag.enterprise_semantic import KNOWLEDGE_GENERATION_POLICY
from eval.rag_e2e_contracts import RAGResolvedRuntime
from eval.rag_e2e_runner import run_rag_eval
from eval.rag_e2e_runtime import ComposerRuntimeMetadata, FixedRAGEvalRouter, RAGProductExecutor
from eval.rag_external_catalog import load_external_rag_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """一次只运行一个冻结 partition；不会自动从 dev 扩到 held-out。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path, required=True)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument(
        "--partition",
        choices=("diagnostic_dev", "held_out", "all"),
        default="diagnostic_dev",
        help="默认 diagnostic_dev（日常诊断集）；held_out/all 必须显式指定。",
    )
    parser.add_argument(
        "--suite",
        choices=("smoke", "basic", "core", "hard", "reliability", "full"),
        default="full",
        help="难度/协议套件；与 partition 做交集。smoke/reliability 只允许 diagnostic_dev。",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--timeout", type=float, default=60.0)
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
        suite=args.suite,
    )
    composer = make_qwen_evidence_composer(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.qwen_model or "qwen3.7-plus",
        timeout=args.timeout,
    )
    artifact_path = args.artifact_dir / f"{args.run_id}.json"
    triage_path = args.triage or args.report.with_name(f"{args.report.stem}-triage.json")
    with load_enterprise_profile_runtime(
        root=args.profile_root,
        profile_identity=args.profile_identity,
        allow_cross_thread=True,
    ) as external:
        bundle = external.bundle
        resolved = RAGResolvedRuntime(
            runtime_family="phase4-rag-external-product-harness-fixed-route-v1",
            answer_flow_identity=ANSWER_FLOW_RUNTIME_IDENTITY,
            composer_identity=composer.identity,
            model=settings.qwen_model or "qwen3.7-plus",
            provider="qwen",
            timeout_seconds=args.timeout,
            retry_count=0,
            release_identity=bundle.release_identity,
            corpus_identity=bundle.corpus_identity,
            retrieval_adapter_identity=external.adapter.identity,
            retrieval_recipe_identity=external.adapter.recipe_identity,
            authorization_policy_identity=bundle.authorization_policy_identity,
            release_outbound_policy_identity=bundle.outbound_policy_identity,
            generation_outbound_policy_identity=KNOWLEDGE_GENERATION_POLICY.identity,
            caller_fixture_identity="phase4-rag-e2e-test-fixture-v1",
            route_policy_identity=FixedRAGEvalRouter.identity,
        )
        executor = RAGProductExecutor(
            composer=composer,
            runtime_metadata=ComposerRuntimeMetadata(
                model=settings.qwen_model or "qwen3.7-plus",
                timeout_seconds=args.timeout,
                generation_outbound_policy_identity=KNOWLEDGE_GENERATION_POLICY.identity,
            ),
            trace_root=args.checkpoint_dir / args.run_id / "traces",
            answer_flow_factory=lambda: RAGAnswerFlow(
                knowledge_tool=external.knowledge_tool(),
                composer=composer,
                active_loader=external.active_loader,
            ),
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
