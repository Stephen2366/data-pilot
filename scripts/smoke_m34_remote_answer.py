"""M34 仅 3 道 diagnostic/dev 的真实 Qwen AnswerFlow smoke。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.core.config import get_settings
from engine.governance import demo_caller
from engine.rag.answer_flow import AnswerFlowContractError, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.enterprise_cases import load_enterprise_case_split
from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.enterprise_runtime import load_enterprise_profile_runtime
from engine.rag.retrieval import RetrievalBudget

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """运行固定或显式指定的少量 remote AnswerFlow smoke，并逐题写 checkpoint。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile-root", type=Path, required=True)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--question-id",
        action="append",
        dest="question_ids",
        help="只运行指定 diagnostic/dev 题；可重复传入。缺省仍选择 semantic/multi/basic 三题。",
    )
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
    allowed = set(split.diagnostic_dev_question_ids)
    questions = [item for item in audit.selected_questions if item.question_id in allowed]
    if args.question_ids:
        by_id = {item.question_id: item for item in questions}
        if len(set(args.question_ids)) != len(args.question_ids) or not set(args.question_ids) <= set(by_id):
            raise SystemExit("--question-id 必须是互不重复的 diagnostic/dev question ID")
        chosen = tuple(by_id[item] for item in args.question_ids)
    else:
        chosen = (
            next(item for item in questions if item.question_type == "semantic"),
            next(item for item in questions if len(item.expected_document_ids) > 1),
            next(item for item in questions if item.question_type == "basic"),
        )
    composer = make_qwen_evidence_composer(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.qwen_model or "qwen3.7-plus",
        timeout=args.timeout,
    )
    executions = []

    def write_artifact(*, status: str) -> None:
        """每题后原子覆盖 checkpoint；中断时绝不伪造 completed artifact。"""

        payload = {
            "format": "m34-remote-answer-smoke-v2",
            "status": status,
            "profile_identity": args.profile_identity,
            "requested_question_ids": [item.question_id for item in chosen],
            "execution_count": len(executions),
            "provider_usage": composer.usage_projection(),
            "composer_attempts": list(composer.attempts),
            "executions": executions,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)

    write_artifact(status="in_progress")
    with load_enterprise_profile_runtime(
        root=args.profile_root, profile_identity=args.profile_identity
    ) as runtime:
        flow = RAGAnswerFlow(
            knowledge_tool=runtime.knowledge_tool(),
            composer=composer,
            active_loader=runtime.active_loader,
        )
        for ordinal, question in enumerate(chosen, start=1):
            try:
                result = flow.run(
                    RAGAnswerRequest(
                        question=question.question,
                        caller=demo_caller(caller_id="m34-remote-answer-smoke", roles=("demo_user",)),
                        run_id=f"m34-remote-answer-{ordinal:02d}-{question.question_id}",
                        retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=3),
                    )
                )
                execution = {
                    "question_id": question.question_id,
                    "question_type": question.question_type,
                    "outcome": "answer_result",
                    "result": result.safe_projection(),
                }
            except AnswerFlowContractError as exc:
                # 严格 support/citation 合同拒绝是预期 Eval 结果，不应让 checkpoint 丢失。
                execution = {
                    "question_id": question.question_id,
                    "question_type": question.question_type,
                    "outcome": "contract_rejected",
                    "reason_code": exc.reason_code,
                }
            executions.append(execution)
            write_artifact(status="in_progress")
    write_artifact(status="completed")
    print(
        json.dumps(
            {
                "status": "completed",
                "execution_count": len(executions),
                "provider_usage": composer.usage_projection(),
                "composer_attempts": composer.attempts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
