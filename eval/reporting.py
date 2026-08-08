"""M27 安全 artifact 的 Markdown / LangFuse payload adapter。

报告只读取 ``ProjectedEval`` 和已脱敏 ``EvalRun``，绝不解析旧 Markdown 或回头读取 raw trace。
LangFuse adapter 在本模块只构造 allowlist payload；真正上传仍由调用方显式启用，避免评测命令
因展示需求泄露 rows、prompt 或 SQL literal。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.contracts import EvalRun
from eval.projectors import ProjectedEval


def render_markdown(run: EvalRun, projected: ProjectedEval) -> str:
    """渲染 M27 diagnostic view；所有汇总来自 projector，不制造单一 diagnostic 总分。"""

    if run.run_id != projected.run_id:
        raise ValueError("run/projected identity mismatch")
    lines = [
        "# DataPilot M27 Eval Report",
        "",
        f"- run_id: `{run.run_id}`",
        f"- run_status: `{run.run_status}`",
        f"- contract_version: `{run.contract_version}`",
        f"- artifact_schema_version: `{run.artifact_schema_version}`",
        f"- projector_version: `{projected.projector_version}`",
        f"- catalog_hash: `{run.catalog_hash}`",
        f"- selected_contract_hash: `{run.selected_contract_hash}`",
        f"- suite_policy_hash: `{run.suite_policy_hash}`",
        f"- run_spec_hash: `{run.run_spec_hash}`",
        "",
        "## Gate",
        "",
        f"- suite: `{projected.gate.suite_id}`",
        f"- outcome: **{projected.gate.outcome}**",
        f"- required: passed={projected.gate.required_passed}, failed={projected.gate.required_failed}, not_observed={projected.gate.required_not_observed}",
        "",
        "## Execution",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(projected.execution.items()))
    lines.extend([
        "",
        "## Assertion views",
        "",
        "| View | Eligible | Observed | Passed | Failed | Not observed | Unavailable | Manual evidence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for kind, counts in projected.assertion_views.items():
        lines.append(
            f"| {kind} | {counts.eligible} | {counts.observed} | {counts.passed} | {counts.failed} | "
            f"{counts.not_observed} | {counts.unavailable} | {counts.manual_evidence_required} |"
        )
    lines.extend(["", "自动能力率仅在 observed > 0 时计算：`passed / (passed + failed)`。unavailable 是 not_observed 的原因切片，不计为 semantic wrong。", ""])
    return "\n".join(lines)


def write_markdown(run: EvalRun, projected: ProjectedEval, path: Path) -> None:
    """原子写入 Markdown；最终报告与 artifact 一样不应出现半写文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(render_markdown(run, projected), encoding="utf-8")
    temporary.replace(path)


def build_langfuse_assertion_payloads(run: EvalRun, projected: ProjectedEval) -> list[dict[str, Any]]:
    """构造严格 allowlist 的 observed assertion payload；不上传 rows、SQL、prompt 或 provider body。"""

    if run.run_id != projected.run_id:
        raise ValueError("run/projected identity mismatch")
    payloads: list[dict[str, Any]] = []
    for scenario_run in run.scenario_runs:
        for result in scenario_run.assertion_results:
            if result.status == "not_observed":
                continue
            payloads.append({
                "run_id": run.run_id,
                "scenario_id": scenario_run.scenario_id,
                "replicate_id": scenario_run.replicate_id,
                "assertion_id": result.assertion_id,
                "kind": result.kind,
                "status": result.status,
                "reason": result.reason,
                "issue_tags": list(result.issue_tags),
                "projector_version": projected.projector_version,
            })
    return payloads
