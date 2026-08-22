"""Phase 4 RAG 真实产品链路 Eval CLI。真实调用必须遵守 runbook 的单次精确授权。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from eval.rag_e2e_contracts import build_explicit_selector, load_rag_catalog, load_rag_selector
from eval.rag_e2e_generation import RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY, make_business_qwen_eval_composer
from eval.rag_e2e_runner import run_rag_eval
from eval.rag_e2e_runtime import ComposerRuntimeMetadata, RAGProductExecutor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT_ROOT / "eval/cases/rag/scenarios.yaml"
DEFAULT_SELECTOR_ROOT = PROJECT_ROOT / "eval/cases/rag/selectors"


def main() -> None:
    """解析一次授权范围并运行；CLI 不自动扩大 selector 或重跑。"""

    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--selector")
    choice.add_argument("--suite", choices=("core", "diagnostic", "reliability"))
    choice.add_argument("--scenario", action="append", help="精确 Scenario ID；可重复传入")
    parser.add_argument("--replicate-count", type=int, default=1, help="仅与 --scenario 一起使用")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--checkpoint-dir", type=Path, default=PROJECT_ROOT / ".agent_work/temp/m41-rag-checkpoints")
    parser.add_argument("--artifact-dir", type=Path, default=PROJECT_ROOT / "eval/reports/m41-rag-artifacts")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--resume", action="store_true", help="显式恢复同 RunSpec 的合法 checkpoint 前缀")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.dashscope_api_key:
        raise SystemExit("DASHSCOPE_API_KEY 未配置")
    catalog = load_rag_catalog(args.catalog)
    if args.scenario:
        selector = build_explicit_selector(
            scenario_ids=tuple(args.scenario), replicate_count=args.replicate_count, catalog=catalog
        )
    else:
        if args.replicate_count != 1:
            parser.error("--replicate-count 只能与 --scenario 一起使用")
        selector_name = args.suite or args.selector or "smoke"
        selector_path = Path(selector_name)
        if not selector_path.suffix:
            selector_path = DEFAULT_SELECTOR_ROOT / f"{selector_name}.yaml"
        selector = load_rag_selector(selector_path, catalog)
    composer = make_business_qwen_eval_composer(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.qwen_model or "qwen3.7-plus",
        timeout=args.timeout,
    )
    artifact_path = args.artifact_dir / f"{args.run_id}.json"
    triage_path = args.triage or args.report.with_name(f"{args.report.stem}-triage.json")
    executor = RAGProductExecutor(
        composer=composer,
        runtime_metadata=ComposerRuntimeMetadata(
            model=settings.qwen_model or "qwen3.7-plus", timeout_seconds=args.timeout,
            generation_outbound_policy_identity=RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY,
        ),
        trace_root=args.checkpoint_dir / args.run_id / "traces",
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
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "artifact_identity": artifact["artifact_identity"],
                "gate": artifact["gate"],
                "artifact": str(artifact_path),
                "report": str(args.report),
                "triage": str(triage_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
