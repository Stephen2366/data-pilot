"""M46-E：API、Trace、Eval 共用的 Agent Scenario source identity。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from engine.phase4b.identity import canonical_hash


def agent_scenario_source_identity(
    *,
    actions: Sequence[Mapping[str, Any]],
    budget: Mapping[str, Any],
    termination: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
) -> str:
    """只 hash 已公开的运行事实；不纳入 question、answer、rows 或 Evidence 正文。"""

    return canonical_hash({
        "actions": list(actions),
        "budget": dict(budget),
        "termination": dict(termination),
        "runtime_identity": dict(runtime_identity),
    })
