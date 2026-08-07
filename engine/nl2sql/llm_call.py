"""LLM 调用执行器：集中管理重试边界，并产出可归因的 attempt 证据。

★ 这个 module 只负责一次“逻辑调用”的运行可靠性，不理解 QueryPlan、SQL 或业务语义。
调用方拿到正文后继续做自己的解析；失败时则能区分 transport、限流、服务端和解析问题。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class LLMGenerationError(RuntimeError):
    """LLM 生成失败，并携带 trace / triage 所需的稳定证据。"""

    def __init__(
        self,
        message: str,
        *,
        raw_response_preview: str | None = None,
        parse_error: str | None = None,
        prompt_length: int | None = None,
        stage: str | None = None,
        error_subtype: str | None = None,
        retryable: bool = False,
        call_evidence: LLMCallEvidence | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response_preview = raw_response_preview
        self.parse_error = parse_error
        self.prompt_length = prompt_length
        self.stage = stage
        self.error_subtype = error_subtype
        self.retryable = retryable
        self.call_evidence = call_evidence


class SupportsComplete(Protocol):
    """真实 client 与测试 fake 共用的最小接口。"""

    def complete(self, *, prompt: str, system_prompt: str | None = None) -> str: ...


@dataclass(frozen=True)
class LLMAttemptEvidence:
    """一次物理请求的结果；不保存 prompt 正文或密钥。"""

    attempt: int
    latency_ms: float
    outcome: str
    error_subtype: str | None = None
    retryable: bool = False
    error_message: str | None = None


@dataclass(frozen=True)
class LLMCallEvidence:
    """一次逻辑调用的完整证据链。"""

    stage: str
    provider: str
    model: str
    configured_timeout_seconds: float | None
    max_retries: int
    prompt_length: int
    system_prompt_length: int
    attempts: tuple[LLMAttemptEvidence, ...]

    def to_trace_metadata(self) -> dict[str, Any]:
        """转换成 JSONL / LangFuse 都能消费的普通字典。"""

        return {
            "stage": self.stage,
            "provider": self.provider,
            "model": self.model,
            "configured_timeout_seconds": self.configured_timeout_seconds,
            "max_retries": self.max_retries,
            "attempt_count": len(self.attempts),
            "prompt_length": self.prompt_length,
            "system_prompt_length": self.system_prompt_length,
            "final_outcome": self.attempts[-1].outcome if self.attempts else "not_started",
            "attempts": [asdict(attempt) for attempt in self.attempts],
        }


@dataclass(frozen=True)
class LLMCallResult:
    """把正文和证据一起返回，避免 stateful `last_call_metadata` 串请求。"""

    content: str
    evidence: LLMCallEvidence


def _complete_compat(client: SupportsComplete, *, prompt: str, system_prompt: str) -> str:
    """兼容历史 fake client；真实 client 始终接收 system prompt。"""

    try:
        return client.complete(prompt=prompt, system_prompt=system_prompt)
    except TypeError as exc:
        if "system_prompt" not in str(exc):
            raise
        return client.complete(prompt=prompt)


def execute_llm_call(
    client: SupportsComplete,
    *,
    prompt: str,
    system_prompt: str,
    stage: str,
    max_retries: int | None = None,
    retry_backoff_seconds: float | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> LLMCallResult:
    """执行 LLM 调用并记录每次 attempt。

    默认从 client 读取配置；没有配置的 fake client 等价于 0 次重试。只有异常明确标记
    `retryable=True` 才会重试，4xx、解析失败和业务合同失败不会被重复请求掩盖。
    """

    resolved_retries = max(0, max_retries if max_retries is not None else int(getattr(client, "max_retries", 0)))
    backoff = max(
        0.0,
        retry_backoff_seconds
        if retry_backoff_seconds is not None
        else float(getattr(client, "retry_backoff_seconds", 1.0)),
    )
    attempts: list[LLMAttemptEvidence] = []

    for attempt_number in range(1, resolved_retries + 2):
        started = time.perf_counter()
        try:
            content = _complete_compat(client, prompt=prompt, system_prompt=system_prompt)
        except LLMGenerationError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            attempts.append(
                LLMAttemptEvidence(
                    attempt=attempt_number,
                    latency_ms=latency_ms,
                    outcome="error",
                    error_subtype=exc.error_subtype or "llm_generation_error",
                    retryable=exc.retryable,
                    error_message=str(exc)[:500],
                )
            )
            evidence = _build_evidence(client, stage, prompt, system_prompt, resolved_retries, attempts)
            exc.call_evidence = evidence
            exc.stage = exc.stage or stage
            exc.prompt_length = exc.prompt_length or len(prompt)
            if not exc.retryable or attempt_number > resolved_retries:
                raise
            if backoff:
                sleeper(backoff * attempt_number)
        except Exception as exc:
            # 未分类异常默认不重试，防止代码 bug 被当成外部服务抖动。
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            attempts.append(
                LLMAttemptEvidence(
                    attempt=attempt_number,
                    latency_ms=latency_ms,
                    outcome="error",
                    error_subtype="client_exception",
                    error_message=str(exc)[:500],
                )
            )
            evidence = _build_evidence(client, stage, prompt, system_prompt, resolved_retries, attempts)
            raise LLMGenerationError(
                f"LLM client 调用异常：{exc}",
                stage=stage,
                prompt_length=len(prompt),
                error_subtype="client_exception",
                call_evidence=evidence,
            ) from exc
        else:
            attempts.append(
                LLMAttemptEvidence(
                    attempt=attempt_number,
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    outcome="success",
                )
            )
            return LLMCallResult(
                content=content,
                evidence=_build_evidence(client, stage, prompt, system_prompt, resolved_retries, attempts),
            )

    raise AssertionError("LLM attempt loop should always return or raise")


def _build_evidence(
    client: SupportsComplete,
    stage: str,
    prompt: str,
    system_prompt: str,
    max_retries: int,
    attempts: list[LLMAttemptEvidence],
) -> LLMCallEvidence:
    """集中提取非敏感 client 属性，保持 trace metadata 稳定。"""

    return LLMCallEvidence(
        stage=stage,
        provider=str(getattr(client, "provider_label", client.__class__.__name__)),
        model=str(getattr(client, "model", "unknown")),
        configured_timeout_seconds=getattr(client, "timeout", None),
        max_retries=max_retries,
        prompt_length=len(prompt),
        system_prompt_length=len(system_prompt),
        attempts=tuple(attempts),
    )
