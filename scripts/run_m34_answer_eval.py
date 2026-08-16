"""运行冻结 180 题的 M34 AnswerFlow Eval；支持逐题原子 checkpoint/resume。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.core.config import get_settings
from engine.governance import demo_caller
from engine.rag.answer_flow import AnswerFlowContractError, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.enterprise_answer_eval import (
    ANSWER_EVAL_FORMAT,
    answer_eval_summaries,
    build_answer_execution,
    finalize_answer_artifact,
)
from engine.rag.enterprise_cases import load_enterprise_case_split, validate_enterprise_case_split
from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.enterprise_runtime import load_enterprise_profile_runtime
from engine.rag.retrieval import RetrievalBudget

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _atomic_write(path: Path, payload: dict) -> None:
    """在同目录替换 checkpoint，避免中断留下半个 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    """执行冻结题序的 180 题 AnswerFlow Eval，支持合法前缀续跑。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path, required=True)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.dashscope_api_key:
        raise SystemExit("DASHSCOPE_API_KEY 未配置")
    audit = audit_enterprise_dataset(
        args.dataset_root,
        load_dataset_recipe(PROJECT_ROOT / "eval/cases/enterprise-rag-bench-v1.0.0-dataset.json"),
    )
    split = load_enterprise_case_split(PROJECT_ROOT / "eval/cases/enterprise-rag-bench-v1.0.0-split.json")
    validate_enterprise_case_split(split, audit.selected_questions, audit.question_set_identity)
    question_ids = tuple(item.question_id for item in audit.selected_questions)
    questions = {item.question_id: item for item in audit.selected_questions}
    composer = make_qwen_evidence_composer(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.qwen_model or "qwen3.7-plus",
        timeout=args.timeout,
    )

    executions: list[dict] = []
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if checkpoint.get("status") == "completed":
            raise SystemExit("output 已是 completed artifact；拒绝重复付费运行")
        if checkpoint.get("format") != ANSWER_EVAL_FORMAT:
            raise SystemExit("checkpoint format 不匹配")
        executions = list(checkpoint.get("executions", []))
        completed_ids = [item.get("question_id") for item in executions]
        if completed_ids != list(question_ids[: len(completed_ids)]):
            raise SystemExit("checkpoint 不是冻结 question 顺序的合法前缀")

    def checkpoint() -> None:
        """写入当前前缀及其分组摘要；未完成时永远标记 in_progress。"""
        _atomic_write(
            args.output,
            {
                "format": ANSWER_EVAL_FORMAT,
                "status": "in_progress",
                "dataset_identity": audit.dataset_identity,
                "question_set_identity": audit.question_set_identity,
                "split_identity": split.split_identity,
                "profile_identity": args.profile_identity,
                "composer_identity": composer.identity,
                "question_ids": list(question_ids),
                "question_count": len(executions),
                "summaries": answer_eval_summaries(executions),
                "executions": executions,
            },
        )

    checkpoint()
    with load_enterprise_profile_runtime(root=args.profile_root, profile_identity=args.profile_identity) as runtime:
        flow = RAGAnswerFlow(
            knowledge_tool=runtime.knowledge_tool(),
            composer=composer,
            active_loader=runtime.active_loader,
        )
        for ordinal, question_id in enumerate(question_ids[len(executions) :], start=len(executions) + 1):
            question = questions[question_id]
            usage_before = composer.usage_projection()
            attempt_before = len(composer.attempts)
            result = None
            contract_error = None
            try:
                result = flow.run(
                    RAGAnswerRequest(
                        question=question.question,
                        caller=demo_caller(caller_id="m34-answer-eval", roles=("demo_user",)),
                        run_id=f"m34-answer-all-{ordinal:03d}-{question_id}",
                        retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=3),
                    )
                )
            except AnswerFlowContractError as exc:
                contract_error = exc
            usage_after = composer.usage_projection()
            attempts = composer.attempts[attempt_before:]
            executions.append(
                build_answer_execution(
                    question=question,
                    result=result,
                    contract_error=contract_error,
                    provider_usage_delta={key: usage_after[key] - usage_before[key] for key in usage_after},
                    composer_attempt=attempts[-1] if attempts else None,
                )
            )
            checkpoint()

    artifact = finalize_answer_artifact(
        dataset_identity=audit.dataset_identity,
        question_set_identity=audit.question_set_identity,
        split_identity=split.split_identity,
        profile_identity=args.profile_identity,
        composer_identity=composer.identity,
        question_ids=question_ids,
        executions=executions,
    )
    _atomic_write(args.output, artifact)
    print(json.dumps({"status": "completed", "artifact_identity": artifact["artifact_identity"], "overall": artifact["summaries"]["overall"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
