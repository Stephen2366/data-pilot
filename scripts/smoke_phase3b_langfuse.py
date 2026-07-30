"""Phase 3B LangFuse 一键 smoke：验证 API、JSONL、Trace 映射和 Score 回写闭环。

这个脚本是 M18 的收尾工具，不替代正式 eval，也不自动创建 LangFuse Experiment。它只回答
一个很具体的问题：当前环境下，DataPilot 能不能跑一条真实 `/api/query`，把 trace 写进
JSONL，并在启用 LangFuse 时把 trace id 用于 Score 回写和可见性检查。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings, get_settings
from eval.run_eval import seeded_api_client
from eval.scorers.base import LangFuseScorePayload
from eval.scorers.langfuse_scores import LangFuseScoreWriter
from engine.trace.recorder import build_trace_router, configure_trace_router

DEFAULT_TRACE_PATH = PROJECT_ROOT / ".agent_work" / "temp" / "m18-phase3b-smoke-traces.jsonl"

CheckStatus = Literal["PASS", "FAIL", "PENDING", "SKIP"]


@dataclass(frozen=True)
class CheckResult:
    """单个 smoke 检查点的结构化结果，最后统一打印。"""

    name: str
    status: CheckStatus
    detail: str


def _settings_snapshot(settings: Settings) -> dict[str, Any]:
    """返回可打印配置摘要，刻意不包含 secret。"""

    return {
        "langfuse_enabled": settings.langfuse_enabled,
        "langfuse_base_url": settings.langfuse_base_url,
        "has_public_key": bool(settings.langfuse_public_key),
        "has_secret_key": bool(settings.langfuse_secret_key),
        "eval_judge_model": settings.eval_judge_model or "<disabled>",
    }


def _langfuse_ready(settings: Settings) -> tuple[bool, str]:
    """判断当前环境是否具备真实 LangFuse smoke 条件。"""

    if not settings.langfuse_enabled:
        return False, "LANGFUSE_ENABLED=false"
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return False, "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY missing"
    try:
        import langfuse  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - smoke 需要把 SDK 缺失报成可读状态
        return False, f"langfuse SDK unavailable: {exc}"
    return True, "enabled"


def _read_last_trace(trace_path: Path) -> dict[str, Any] | None:
    """读取 JSONL 最后一行 trace；空文件或坏 JSON 返回 None。"""

    if not trace_path.exists():
        return None
    lines = [line for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def _run_api_smoke(trace_path: Path, settings: Settings) -> tuple[list[CheckResult], dict[str, Any], dict[str, Any] | None]:
    """通过真实 FastAPI TestClient 发一条 `/api/query`，并检查 JSONL trace 映射。"""

    results: list[CheckResult] = []
    request_payload = {
        "question": "各渠道订单量是多少？",
        "user_role": "ops",
        "force_new_pipeline": True,
    }

    # ★ build_trace_router 在 import 时已按旧环境初始化过；smoke 运行前显式重建，避免环境开关
    # 被模块级单例锁住。这和 M16/M17 测试里的切换口径一致。
    configure_trace_router(build_trace_router(settings))

    with seeded_api_client(trace_path=trace_path) as client:
        response = client.post("/api/query", json=request_payload)
        try:
            body = response.json()
        except Exception:  # noqa: BLE001 - FastAPI 正常应返回 JSON；异常时给出状态码即可
            body = {}

    if response.status_code == 200 and body.get("trace_id"):
        results.append(CheckResult("api.query", "PASS", f"status=200 trace_id={body['trace_id']}"))
    else:
        results.append(CheckResult("api.query", "FAIL", f"status={response.status_code} body_keys={sorted(body.keys())}"))
        return results, body, None

    trace = _read_last_trace(trace_path)
    if trace is None:
        results.append(CheckResult("jsonl.trace", "FAIL", f"trace file empty or invalid: {trace_path}"))
        return results, body, None

    if trace.get("trace_id") == body.get("trace_id"):
        results.append(CheckResult("jsonl.trace", "PASS", f"trace_id matched path={trace_path}"))
    else:
        results.append(
            CheckResult(
                "jsonl.trace",
                "FAIL",
                f"response_trace_id={body.get('trace_id')} jsonl_trace_id={trace.get('trace_id')}",
            )
        )

    if settings.langfuse_enabled and trace.get("langfuse_trace_id"):
        results.append(
            CheckResult(
                "jsonl.langfuse_mapping",
                "PASS",
                f"status={trace.get('langfuse_write_status')} langfuse_trace_id={trace.get('langfuse_trace_id')}",
            )
        )
    elif settings.langfuse_enabled:
        results.append(
            CheckResult(
                "jsonl.langfuse_mapping",
                "FAIL",
                f"enabled but missing langfuse_trace_id; status={trace.get('langfuse_write_status')}",
            )
        )
    else:
        results.append(CheckResult("jsonl.langfuse_mapping", "SKIP", "langfuse disabled"))

    return results, body, trace


def _write_smoke_score(settings: Settings, trace: dict[str, Any] | None, *, require_langfuse: bool) -> CheckResult:
    """给本次 trace 写一条 M18 smoke score。"""

    if trace is None:
        return CheckResult("langfuse.score", "SKIP", "no trace")
    langfuse_trace_id = trace.get("langfuse_trace_id")
    if not langfuse_trace_id:
        status: CheckStatus = "FAIL" if require_langfuse else "SKIP"
        return CheckResult("langfuse.score", status, "missing langfuse_trace_id")

    payload = LangFuseScorePayload(
        trace_id=str(langfuse_trace_id),
        name="rule:m18_smoke",
        value=1.0,
        data_type="NUMERIC",
        comment="M18 phase3b smoke score",
        metadata={
            "datapilot_trace_id": trace.get("trace_id"),
            "langfuse_span_mode": trace.get("langfuse_span_mode"),
        },
    )
    result = LangFuseScoreWriter(settings).write_scores([payload])
    if result["ok"] == 1:
        return CheckResult("langfuse.score", "PASS", f"ok=1 trace_id={langfuse_trace_id}")
    if result["skipped"]:
        status = "FAIL" if require_langfuse else "SKIP"
        return CheckResult("langfuse.score", status, f"skipped={result['skipped']}")
    return CheckResult("langfuse.score", "FAIL", f"failed={result['failed']}")


def _query_trace_visibility(settings: Settings, trace: dict[str, Any] | None, *, timeout_seconds: int) -> CheckResult:
    """轮询 LangFuse observations，确认 trace 最终可查。"""

    if trace is None or not trace.get("langfuse_trace_id"):
        return CheckResult("langfuse.trace_visibility", "SKIP", "no langfuse_trace_id")

    langfuse_trace_id = str(trace["langfuse_trace_id"])
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
        )
    except Exception as exc:  # noqa: BLE001 - query 失败不应伪装成 trace 不存在
        return CheckResult("langfuse.trace_visibility", "FAIL", f"client unavailable: {exc}")

    waited = 0
    delays = [1, 2, 4, 8, 15, 30]
    for delay in delays:
        try:
            observations = client.api.observations.get_many(trace_id=langfuse_trace_id, limit=10)
            count = len(getattr(observations, "data", []) or [])
            if count > 0:
                return CheckResult("langfuse.trace_visibility", "PASS", f"observations={count} waited={waited}s")
        except Exception as exc:  # noqa: BLE001 - 网络/API 错误和 ingestion pending 分开显示
            return CheckResult("langfuse.trace_visibility", "FAIL", f"query failed: {exc}")
        if waited >= timeout_seconds:
            break
        sleep_for = min(delay, max(0, timeout_seconds - waited))
        if sleep_for <= 0:
            break
        sleep(sleep_for)
        waited += sleep_for

    return CheckResult("langfuse.trace_visibility", "PENDING", f"trace_id={langfuse_trace_id} waited={waited}s")


def run_smoke(*, trace_path: Path, require_langfuse: bool, visibility_timeout_seconds: int) -> list[CheckResult]:
    """执行完整 M18 smoke，并返回每个检查点的状态。"""

    settings = get_settings()
    results: list[CheckResult] = [
        CheckResult("config.snapshot", "PASS", json.dumps(_settings_snapshot(settings), ensure_ascii=False)),
    ]

    ready, reason = _langfuse_ready(settings)
    if ready:
        results.append(CheckResult("config.langfuse", "PASS", reason))
    elif require_langfuse:
        results.append(CheckResult("config.langfuse", "FAIL", reason))
    else:
        results.append(CheckResult("config.langfuse", "SKIP", reason))

    api_results, _body, trace = _run_api_smoke(trace_path, settings)
    results.extend(api_results)

    if ready:
        results.append(_write_smoke_score(settings, trace, require_langfuse=require_langfuse))
        results.append(_query_trace_visibility(settings, trace, timeout_seconds=visibility_timeout_seconds))
    else:
        skip_status: CheckStatus = "FAIL" if require_langfuse else "SKIP"
        results.append(CheckResult("langfuse.score", skip_status, reason))
        results.append(CheckResult("langfuse.trace_visibility", skip_status, reason))

    return results


def _exit_code(results: list[CheckResult]) -> int:
    """FAIL 返回 1；PENDING 不算失败，用于区分 ingestion 延迟。"""

    return 1 if any(result.status == "FAIL" for result in results) else 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="Run Phase 3B LangFuse smoke.")
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE_PATH, help="JSONL trace output path.")
    parser.add_argument(
        "--require-langfuse",
        action="store_true",
        help="Fail when LangFuse is disabled, keys are missing, SDK is unavailable, or score/query checks fail.",
    )
    parser.add_argument(
        "--visibility-timeout-seconds",
        type=int,
        default=45,
        help="Max seconds to wait for LangFuse trace observations to become queryable.",
    )
    args = parser.parse_args(argv)

    results = run_smoke(
        trace_path=args.trace,
        require_langfuse=args.require_langfuse,
        visibility_timeout_seconds=args.visibility_timeout_seconds,
    )
    for result in results:
        print(f"{result.status} {result.name}: {result.detail}")
    return _exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
