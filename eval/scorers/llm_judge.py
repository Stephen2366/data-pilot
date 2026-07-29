"""M17 最小 L3 LLM-as-Judge：只在显式配置 judge model 时启用。

L1/L2 规则能判断表、列、安全和固定数值；L3 只补语义正确性。它默认关闭，因为外部 LLM
有费用、延迟和抖动，不能成为每次 eval 的隐式成本。
"""

from __future__ import annotations

import json
from time import sleep
from typing import Any

from app.core.config import Settings, get_settings
from engine.nl2sql.generator import DeepSeekChatClient, LLMGenerationError, QwenChatClient
from eval.scorers.base import EvalScoreDetail


def resolve_judge_model(cli_judge_model: str | None = None, settings: Settings | None = None) -> str:
    """按 M17 口径解析 judge model：CLI > EVAL_JUDGE_MODEL > 空字符串。"""

    if cli_judge_model:
        return cli_judge_model
    resolved_settings = settings or get_settings()
    return resolved_settings.eval_judge_model.strip()


def score_case_correctness(
    *,
    case: Any,
    body: dict[str, Any],
    judge_model: str,
    judge_client: Any | None = None,
    settings: Settings | None = None,
    max_retries: int = 3,
) -> EvalScoreDetail:
    """调用 judge model 给最终回答做 0-1 correctness 评分。"""

    reference = _reference_answer(case)
    if not judge_model:
        return EvalScoreDetail(name="llm:correctness", value=None, skipped=True, reason="judge_model_empty")
    if not reference:
        return EvalScoreDetail(name="llm:correctness", value=None, skipped=True, reason="reference_answer_empty")

    prompt = _build_correctness_prompt(case=case, body=body, reference=reference)
    client = judge_client or _build_judge_client(judge_model=judge_model, settings=settings)
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            raw_text = client.complete(
                prompt=prompt,
                system_prompt="你是严格但简洁的 DataPilot 评测裁判，只返回 JSON。",
            )
            payload = _extract_json(raw_text)
            value = float(payload["score"])
            value = max(0.0, min(1.0, value))
            reason = str(payload.get("reason") or "llm_correctness_ok")
            return EvalScoreDetail(
                name="llm:correctness",
                value=value,
                passed=value >= 0.8,
                reason=reason,
                issue_tags=[] if value >= 0.8 else ["llm_correctness_low"],
                metadata={"judge_model": judge_model, "reference": reference[:300]},
            )
        except Exception as exc:  # noqa: BLE001 - judge 失败要降级为 null score
            last_error = exc
            if attempt < max_retries - 1:
                sleep(2**attempt)

    return EvalScoreDetail(
        name="llm:correctness",
        value=None,
        passed=None,
        skipped=True,
        reason=f"judge_failed: {last_error}",
        metadata={"judge_model": judge_model},
    )


def _build_judge_client(*, judge_model: str, settings: Settings | None) -> Any:
    """按主 LLM provider 构造 judge client，并把 timeout 固定为 30s。"""

    resolved_settings = settings or get_settings()
    provider = resolved_settings.llm_provider.lower()
    if provider == "qwen":
        return QwenChatClient(
            api_key=resolved_settings.dashscope_api_key,
            base_url=resolved_settings.dashscope_base_url,
            model=judge_model,
            timeout=30.0,
        )
    if provider not in {"deepseek", "mock"}:
        raise LLMGenerationError(f"当前 judge provider 仅支持 DeepSeek / Qwen，LLM_PROVIDER={resolved_settings.llm_provider}。")
    return DeepSeekChatClient(
        api_key=resolved_settings.deepseek_api_key or resolved_settings.llm_api_key,
        base_url=resolved_settings.deepseek_base_url or "https://api.deepseek.com",
        model=judge_model,
        timeout=30.0,
    )


def _reference_answer(case: Any) -> str:
    """从现有 EvalCase 字段提取最小 reference；没有 reference 时跳过 L3。"""

    if case.check_type in {"contains", "equals"} and case.check_value:
        return str(case.check_value)
    if case.check_type == "expected_value" and case.check:
        field = case.check.get("field")
        value = case.check.get("value")
        return f"{field}={value}" if field and value is not None else ""
    if case.expected_sql:
        return f"Expected SQL result should match: {case.expected_sql[:500]}"
    return ""


def _build_correctness_prompt(*, case: Any, body: dict[str, Any], reference: str) -> str:
    """构造最小 correctness judge prompt。"""

    return json.dumps(
        {
            "task": "判断 DataPilot 的回答是否满足参考答案。只返回 JSON: {\"score\": 0到1之间数字, \"reason\": \"简短原因\"}",
            "question": case.question,
            "reference": reference,
            "answer": body.get("answer"),
            "sql": body.get("sql"),
            "rows_preview": (body.get("rows") or [])[:3],
            "safety_status": body.get("safety_status"),
            "error_type": body.get("error_type"),
        },
        ensure_ascii=False,
    )


def _extract_json(raw_text: str) -> dict[str, Any]:
    """解析 judge JSON，兼容模型在 JSON 前后加少量说明。"""

    stripped = raw_text.strip()
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if "score" not in payload:
        raise ValueError(f"judge response missing score: {payload}")
    return payload
