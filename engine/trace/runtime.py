"""M40：把已存在的运行事实整理成 Trace 的最小 runtime identity。

它像快递单的物流编号：只说明本轮用了哪套 Harness、Tool 与受控知识版本，
不把正文、SQL rows 或 thread 参数放进长期 JSONL。
"""

from __future__ import annotations

from typing import Any, Mapping

from engine.harness.contracts import AgentRunResult, ToolObservation

TRACE_RUNTIME_IDENTITY_FORMAT = "phase4-trace-runtime-v1"
HARNESS_RUNTIME_IDENTITY = "phase4-harness-langgraph-v1"


def build_trace_runtime_identity(*, result: AgentRunResult, checkpoint_runtime: Mapping[str, object]) -> dict[str, Any]:
    """★ 从同一 turn 的安全事实构造 runtime envelope，不为凑字段读取 private Evidence。

    Trace 是旁路：identity 缺失时返回 ``unavailable``，不会让完成的 API 请求失败；
    P7 assurance 会把 canonical 成功路径的 unavailable 判为合同失败。
    """

    envelope: dict[str, Any] = {
        "format": TRACE_RUNTIME_IDENTITY_FORMAT,
        "status": "complete",
        "harness_identity": HARNESS_RUNTIME_IDENTITY,
        "route": result.route,
        "checkpoint_runtime": dict(checkpoint_runtime),
        "route_runtime": {},
        "missing": [],
    }
    if result.route == "none":
        envelope["route_runtime"] = {"kind": "none", "reason_code": result.reason_code}
        return envelope
    if result.route == "sql":
        envelope["route_runtime"] = _single_tool_runtime(result.observation, kind="sql")
    elif result.route == "rag":
        envelope["route_runtime"] = _single_tool_runtime(result.observation, kind="rag")
    else:
        envelope["route_runtime"] = _hybrid_runtime(result)
    missing = _collect_missing(envelope["route_runtime"])
    if missing:
        envelope["status"] = "unavailable"
        envelope["missing"] = missing
    return envelope


def _single_tool_runtime(observation: ToolObservation | None, *, kind: str) -> dict[str, Any]:
    """只提取 Tool 已安全公开的 runtime 字段，不重新访问其内部对象。"""

    if observation is None:
        return {"kind": kind, "status": "unavailable", "missing": ["tool_observation"]}
    if kind == "sql":
        return {"kind": "sql", "tool": observation.tool_name, "runtime_ref": _runtime_ref(observation.ledger_projection)}
    diagnostics = observation.diagnostics
    return {
        "kind": "rag", "tool": observation.tool_name,
        "answer_flow_identity": diagnostics.get("runtime_identity"),
        "composer_identity": diagnostics.get("composer_identity"),
        "release_identity": diagnostics.get("release_identity"),
        "corpus_identity": diagnostics.get("corpus_identity"),
        "retrieval_adapter_identity": diagnostics.get("retrieval_adapter_identity"),
        "retrieval_recipe_identity": diagnostics.get("retrieval_recipe_identity"),
        "authorization_policy_identity": diagnostics.get("authorization_policy_identity"),
        "outbound_policy_identity": diagnostics.get("outbound_policy_identity"),
    }


def _hybrid_runtime(result: AgentRunResult) -> dict[str, Any]:
    """汇总双 branch 的安全身份；被拒分支只写不可公开，不暴露内部 reason/ref。"""

    hybrid = result.hybrid
    branches: list[dict[str, Any]] = []
    if hybrid is not None:
        for branch in hybrid.branches:
            if branch.observation.safety_status == "blocked":
                branches.append({"branch": branch.branch, "status": "not_disclosed"})
            else:
                branches.append({"branch": branch.branch, "status": "available", "runtime": _single_tool_runtime(branch.observation, kind=branch.branch)})
    plan = result.route_decision.hybrid_plan
    return {"kind": "hybrid", "plan_identity": plan.identity if plan else None,
            "synthesizer_identity": hybrid.synthesizer_identity if hybrid else None, "branches": branches}


def _runtime_ref(ledger: Mapping[str, Any] | None) -> str | None:
    """SQL identity 只从长期安全 ledger 的 ``runtime_ref`` 读取。"""

    evidence = ledger.get("evidence") if isinstance(ledger, Mapping) else None
    first = evidence[0] if isinstance(evidence, list) and evidence else None
    return first.get("runtime_ref") if isinstance(first, Mapping) else None


def _collect_missing(value: Any, *, path: str = "route_runtime") -> list[str]:
    """列出空 identity；`not_disclosed` 是安全成功，不是缺失。"""

    if isinstance(value, Mapping):
        if value.get("status") == "not_disclosed":
            return []
        return [missing for key, item in value.items() if key not in {"kind", "tool", "status"}
                for missing in _collect_missing(item, path=f"{path}.{key}")]
    if isinstance(value, list):
        return [missing for index, item in enumerate(value) for missing in _collect_missing(item, path=f"{path}[{index}]")]
    return [path] if value is None or value == "" else []
