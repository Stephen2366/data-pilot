"""M17 scorer factory：集中创建本次 eval 需要运行的 scorer 集合。"""

from __future__ import annotations

from typing import Any

from eval.scorers.base import EvalScoreDetail
from eval.scorers.llm_judge import score_case_correctness
from eval.scorers.rule_scorers import score_case_rules


def score_case(
    *,
    case: Any,
    body: dict[str, Any],
    status_code: int,
    actual_pipeline_mode: str,
    judge_model: str = "",
    judge_client: Any | None = None,
) -> list[EvalScoreDetail]:
    """运行当前启用的 scorer：L1/L2 永远开启，L3 只有显式 judge model 时追加。"""

    details = score_case_rules(
        case=case,
        body=body,
        status_code=status_code,
        actual_pipeline_mode=actual_pipeline_mode,
    )
    if judge_model:
        details.append(
            score_case_correctness(
                case=case,
                body=body,
                judge_model=judge_model,
                judge_client=judge_client,
            )
        )
    return details
