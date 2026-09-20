"""执行 LLMR-P1：三题真实 `/api/query` 开发期纵向探针。

本脚本只保存安全 API/Trace 投影与 usage 汇总，不保存 Router prompt、模型原文、Thought
或凭据。它不是 Formal Eval，也不会读取 held-out/reserve。
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


PROBE_ID = "LLMR-P1"
MAX_ATTEMPTS = 12
MAX_TOKENS = 50_000
MAX_SECONDS = 12 * 60

SCENARIOS = (
    {
        "id": "open_sql",
        "question": "请帮我盘点 2026 年 6 月的交易总额表现。",
        "expected_route": "sql",
        "force_new_pipeline": True,
    },
    {
        "id": "policy_rag",
        "question": "质量问题退款通常要准备哪些材料？",
        "expected_route": "rag",
        "force_new_pipeline": False,
    },
    {
        "id": "metric_value_definition_hybrid",
        "question": "请把 2026 年 6 月的成交额结果和它的计算含义一起给我。",
        "expected_route": "hybrid",
        "force_new_pipeline": False,
    },
)


def _git(*args: str) -> str:
    """读取当前版本事实；不修改工作区。"""

    return subprocess.check_output(("git", *args), text=True, encoding="utf-8").strip()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    """读取本轮 Trace；每个 API 请求必须恰好对应一行。"""

    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _collect_llm_usage(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """汇总 Router 与 Text2SQL Trace 中已经存在的逐调用计量。"""

    calls: list[dict[str, Any]] = []
    router = (trace.get("route_decision") or {}).get("router_evidence") or {}
    if router.get("model_attempted"):
        calls.append(
            {
                "stage": "intent_route",
                "provider": router.get("provider"),
                "model": router.get("model"),
                "attempt_count": int(router.get("attempt_count", 0)),
                "usage": dict(router.get("usage") or {}),
                "validation_status": router.get("validation_status"),
            }
        )
    for step in trace.get("trace_steps") or []:
        call = (step.get("metadata") or {}).get("llm_call")
        if isinstance(call, dict):
            calls.append(
                {
                    "stage": call.get("stage"),
                    "provider": call.get("provider"),
                    "model": call.get("model"),
                    "attempt_count": int(call.get("attempt_count", 0)),
                    "usage": dict(call.get("usage") or {}),
                    "validation_status": call.get("final_outcome"),
                }
            )
    return calls


def _forbidden_keys(value: Any, *, path: str = "") -> set[str]:
    """递归检查私有字段名；`prompt_length` 等安全数字不在禁区。"""

    forbidden = {"prompt", "system_prompt", "raw_response", "raw_response_preview", "thought", "api_key", "content"}
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            # clarification.prompt 是服务端 registry 的公开模板，不是发送给模型的 Router prompt。
            if str(key).lower() in forbidden and child_path != ".route_decision.clarification.prompt":
                found.add(str(key).lower())
            found |= _forbidden_keys(item, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found |= _forbidden_keys(item, path=f"{path}[{index}]")
    return found


def _scenario_checks(
    scenario: dict[str, Any], response: dict[str, Any], trace: dict[str, Any]
) -> dict[str, bool]:
    """只判断 design 冻结的技术合同，不外推自然回答质量。"""

    expected = scenario["expected_route"]
    router = (trace.get("route_decision") or {}).get("router_evidence") or {}
    checks = {
        "route": response.get("route") == expected == trace.get("route"),
        "model_adopted": (trace.get("route_decision") or {}).get("decision_source") == "model",
        "router_single_attempt": router.get("attempt_count") == 1,
        "router_usage_complete": int((router.get("usage") or {}).get("total_tokens", 0)) > 0,
        "router_validation": router.get("validation_status") == "accepted",
        "safety": response.get("safety_status") == "passed",
        "private_payload_absent": not _forbidden_keys(trace),
    }
    if expected == "sql":
        values = [value for row in response.get("rows") or [] for value in row.values()]
        checks.update(
            {
                "graph": trace.get("graph_steps") == ["route", "sql_tool", "controller"],
                "tool_budget": len(response.get("tool_calls") or []) == 1,
                "answer_complete": response.get("answer_status") == "complete",
                "guarded_result": any(str(value) in {"11285752", "11285752.0", "11285752.00"} for value in values),
            }
        )
    elif expected == "rag":
        checks.update(
            {
                "graph": trace.get("graph_steps") == ["route", "rag_tool", "controller"],
                "tool_budget": len(response.get("tool_calls") or []) == 1,
                "answer_complete": response.get("answer_status") == "complete",
                "citation": bool(response.get("citations")),
            }
        )
    else:
        branches = trace.get("hybrid_branches") or []
        checks.update(
            {
                "graph": trace.get("graph_steps")
                == ["route", "hybrid_sql_tool", "hybrid_rag_tool", "controller"],
                "operator": (trace.get("route_decision") or {}).get("hybrid_plan_identity")
                == "hybrid-metric-value-and-definition-v1",
                "tool_budget": [item.get("branch") for item in branches] == ["sql", "rag"],
                "answer_complete": response.get("answer_status") == "complete",
                "citation": bool(response.get("citations")),
            }
        )
    return checks


def run_probe(
    output_dir: Path,
    *,
    scenario_ids: tuple[str, ...] = (),
    prior_artifact_path: Path | None = None,
) -> dict[str, Any]:
    """执行完整三题或指定失败场景重验，并返回可复核的整轮安全 artifact。"""

    output_dir.mkdir(parents=True, exist_ok=False)
    trace_path = output_dir / "trace.jsonl"
    started_at = perf_counter()
    started_utc = datetime.now(UTC).isoformat()
    settings = Settings(HARNESS_ROUTER_MODE="llm_fallback")
    application = create_app(settings)
    # 政策/指标场景必须走已批准的 22-entry business release；这仍是真实 Knowledge Tool、
    # ACL、Evidence、Gate 与 citation 链，不用 fake 或 external benchmark 替代业务知识。
    application.state.rag_tool_factory = application.state.business_rag_tool_factory
    application.state.trace_path = trace_path
    selected = tuple(
        scenario for scenario in SCENARIOS if not scenario_ids or scenario["id"] in scenario_ids
    )
    if len(selected) != (len(scenario_ids) if scenario_ids else len(SCENARIOS)):
        raise ValueError("包含未知或重复 Probe scenario id")
    prior_artifact = (
        json.loads(prior_artifact_path.read_text(encoding="utf-8")) if prior_artifact_path is not None else None
    )
    results: list[dict[str, Any]] = []

    with TestClient(application) as client:
        for scenario in selected:
            before = len(_jsonl(trace_path))
            response = client.post(
                "/api/query",
                json={
                    "question": scenario["question"],
                    "user_role": "ops",
                    "force_new_pipeline": scenario["force_new_pipeline"],
                },
            )
            traces = _jsonl(trace_path)
            if len(traces) != before + 1:
                raise RuntimeError(f"{scenario['id']} 没有形成唯一 Trace")
            body = response.json()
            trace = traces[-1]
            checks = _scenario_checks(scenario, body, trace)
            results.append(
                {
                    "scenario_id": scenario["id"],
                    "http_status": response.status_code,
                    "response": body,
                    "trace_safe": {
                        "trace_id": trace.get("trace_id"),
                        "route": trace.get("route"),
                        "route_decision": trace.get("route_decision"),
                        "graph_steps": trace.get("graph_steps"),
                        "tool_calls": trace.get("tool_calls"),
                        "hybrid_branches": trace.get("hybrid_branches"),
                        "runtime_identity": trace.get("runtime_identity"),
                    },
                    "llm_calls": _collect_llm_usage(trace),
                    "checks": checks,
                    "passed": response.status_code == 200 and all(checks.values()),
                }
            )

    elapsed = perf_counter() - started_at
    all_calls = [call for result in results for call in result["llm_calls"]]
    attempts = sum(int(call["attempt_count"]) for call in all_calls)
    tokens = sum(int((call.get("usage") or {}).get("total_tokens", 0) or 0) for call in all_calls)
    usage_complete = all(bool((call.get("usage") or {}).get("observed", True)) for call in all_calls)
    run_budget = {
        "attempts": attempts,
        "tokens": tokens,
        "elapsed_seconds": round(elapsed, 3),
        "usage_complete": usage_complete,
    }
    prior_budget = dict(prior_artifact.get("budget") or {}) if prior_artifact else {}
    budget = {
        "attempts": attempts + int(prior_budget.get("attempts", 0)),
        "max_attempts": MAX_ATTEMPTS,
        "tokens": tokens + int(prior_budget.get("tokens", 0)),
        "max_tokens": MAX_TOKENS,
        "elapsed_seconds": round(elapsed + float(prior_budget.get("elapsed_seconds", 0.0)), 3),
        "max_seconds": MAX_SECONDS,
        "usage_complete": usage_complete and bool(prior_budget.get("usage_complete", True)),
    }
    campaign_by_id = {
        result["scenario_id"]: result for result in (prior_artifact.get("results") or [])
    } if prior_artifact else {}
    campaign_by_id.update({result["scenario_id"]: result for result in results})
    campaign_results = [campaign_by_id[scenario["id"]] for scenario in SCENARIOS if scenario["id"] in campaign_by_id]
    passed = (
        len(campaign_results) == len(SCENARIOS)
        and all(result["passed"] for result in campaign_results)
        and budget["attempts"] <= MAX_ATTEMPTS
        and budget["tokens"] <= MAX_TOKENS
        and budget["elapsed_seconds"] <= MAX_SECONDS
        and budget["usage_complete"]
    )
    artifact = {
        "probe_id": PROBE_ID,
        "evidence_class": "exploratory_baseline_ineligible_dev_probe",
        "started_at": started_utc,
        "finished_at": datetime.now(UTC).isoformat(),
        "head": _git("rev-parse", "HEAD"),
        "dirty_files": _git("status", "--short").splitlines(),
        "runtime": {
            "router_mode": settings.harness_router_mode,
            "provider": settings.llm_provider,
            "model": settings.qwen_model if settings.llm_provider.lower() == "qwen" else settings.llm_model,
            "llm_max_retries": settings.llm_max_retries,
            "database_kind": settings.database_url.split(":", 1)[0],
            "knowledge_runtime": "business_release_active",
        },
        "results": results,
        "campaign_results": campaign_results,
        "prior_artifact": str(prior_artifact_path) if prior_artifact_path else None,
        "run_budget": run_budget,
        "budget": budget,
        "status": "passed" if passed else "failed",
        "decision": "continue" if passed else "revise",
        "trace_path": str(trace_path),
    }
    encoded = json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8")
    artifact["artifact_identity"] = sha256(encoded).hexdigest()
    (output_dir / "artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return artifact


def main() -> int:
    """解析 Probe 参数、运行指定轮次，并向终端输出最小结果摘要。"""

    parser = argparse.ArgumentParser(description="Run LLMR-P1 live development probe")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--prior-artifact", type=Path)
    args = parser.parse_args()
    artifact = run_probe(
        args.output_dir,
        scenario_ids=tuple(args.scenario),
        prior_artifact_path=args.prior_artifact,
    )
    print(
        json.dumps(
            {
                "probe_id": artifact["probe_id"],
                "status": artifact["status"],
                "decision": artifact["decision"],
                "budget": artifact["budget"],
                "artifact_identity": artifact["artifact_identity"],
                "artifact": str(args.output_dir / "artifact.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if artifact["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
