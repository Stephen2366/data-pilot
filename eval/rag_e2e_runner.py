"""M41 RAG Eval 的一次执行、checkpoint、completed artifact 与报告生命周期。"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from eval.rag_e2e_contracts import (
    RAGAssertionResult,
    RAGExecutionEvidence,
    RAGRunSpec,
    RAGScenarioCatalog,
    RAGSelector,
    artifact_payload,
    validate_completed_artifact,
)
from eval.rag_e2e_runtime import RAGProductExecutor
from eval.rag_e2e_scoring import project_gate, render_report, score_execution, triage_execution


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """同目录 replace，避免中断留下半个 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _execution_from_dict(raw: dict[str, Any]) -> RAGExecutionEvidence:
    """恢复 checkpoint 时重新构造 typed Evidence。"""

    return RAGExecutionEvidence(
        scenario_id=str(raw["scenario_id"]),
        replicate=int(raw["replicate"]),
        trace_id=str(raw["trace_id"]),
        status_code=int(raw["status_code"]),
        route=str(raw["route"]),
        execution_status=str(raw["execution_status"]),
        answer_status=str(raw["answer_status"]),
        safety_status=str(raw["safety_status"]),
        reason_code=str(raw["reason_code"]),
        answer=raw.get("answer"),
        graph_steps=tuple(raw.get("graph_steps") or ()),
        graph_invocation_count=int(raw.get("graph_invocation_count") or 0),
        rag_tool_calls=int(raw.get("rag_tool_calls") or 0),
        stage_document_keys=tuple(
            (str(stage), tuple(str(item) for item in keys)) for stage, keys in raw.get("stage_document_keys") or ()
        ),
        stage_counts=tuple((str(stage), int(count)) for stage, count in raw.get("stage_counts") or ()),
        identities_redacted=bool(raw.get("identities_redacted")),
        citations=tuple(dict(item) for item in raw.get("citations") or ()),
        docs_used=tuple(dict(item) for item in raw.get("docs_used") or ()),
        rag_diagnostics=dict(raw.get("rag_diagnostics") or {}),
        trace_runtime_identity=dict(raw.get("trace_runtime_identity") or {}),
        provider_attempts=tuple(dict(item) for item in raw.get("provider_attempts") or ()),
        provider_usage={str(key): int(value) for key, value in (raw.get("provider_usage") or {}).items()},
        response_trace_consistent=bool(raw.get("response_trace_consistent")),
    )


def run_rag_eval(
    *,
    catalog: RAGScenarioCatalog,
    selector: RAGSelector,
    run_id: str,
    executor: RAGProductExecutor,
    checkpoint_root: Path,
    artifact_path: Path,
    report_path: Path,
    triage_path: Path,
    resume: bool = False,
) -> dict[str, Any]:
    """★ 执行或显式恢复同一 run；闭集完成后才生成 artifact/report/triage。"""

    # 步骤 1：冻结实际 runtime 与本次授权的 RunSpec identity ============================
    runtime = executor.resolved_runtime()
    spec = RAGRunSpec(
        run_id=run_id,
        catalog_identity=catalog.catalog_identity,
        selector_identity=selector.selector_identity,
        selected_scenario_ids=selector.selected_scenario_ids,
        replicate_count=selector.replicate_count,
        runtime=runtime,
        assertion_plan=tuple(
            (scenario_id, catalog.by_id()[scenario_id].required_assertions, catalog.by_id()[scenario_id].advisory_assertions)
            for scenario_id in selector.selected_scenario_ids
        ),
    )
    run_root = checkpoint_root / run_id
    manifest_path = run_root / "manifest.json"
    checkpoints = run_root / "checkpoints"
    # 步骤 2：检查生命周期；completed 禁止重跑，未完成必须显式 resume --------------------
    if artifact_path.exists():
        existing = json.loads(artifact_path.read_text(encoding="utf-8"))
        validate_completed_artifact(existing)
        raise ValueError("目标 artifact 已 completed；拒绝重复真实运行")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("run_spec_identity") != spec.identity:
            raise ValueError("已有 manifest 与本次 RunSpec identity 不匹配")
        if manifest.get("status") == "completed":
            raise ValueError("manifest 已 completed 但 artifact 缺失；拒绝静默重跑")
        if not resume:
            raise ValueError("已有未完成 manifest；必须显式 --resume 才能复用合法 checkpoint 前缀")
    _atomic_write(
        manifest_path,
        {"format": "phase4-rag-e2e-manifest-v1", "status": "running", "run_spec": asdict(spec), "run_spec_identity": spec.identity},
    )

    # 步骤 3：验证 checkpoint 是计划顺序的连续前缀，再逐格执行或恢复 --------------------
    scenarios = catalog.by_id()
    executions: list[RAGExecutionEvidence] = []
    try:
        planned_names = [
            f"{scenario_id}-r{replicate}.json"
            for scenario_id in selector.selected_scenario_ids
            for replicate in range(1, selector.replicate_count + 1)
        ]
        existing_names = [item.name for item in checkpoints.glob("*.json")] if checkpoints.exists() else []
        unknown_names = set(existing_names) - set(planned_names)
        present_indices = sorted(planned_names.index(name) for name in existing_names if name in planned_names)
        if unknown_names or present_indices != list(range(len(present_indices))):
            raise ValueError("checkpoint 必须是本 RunSpec 的合法连续前缀")
        for scenario_id in selector.selected_scenario_ids:
            scenario = scenarios[scenario_id]
            for replicate in range(1, selector.replicate_count + 1):
                checkpoint = checkpoints / f"{scenario_id}-r{replicate}.json"
                if checkpoint.exists():
                    raw = json.loads(checkpoint.read_text(encoding="utf-8"))
                    if raw.get("run_spec_identity") != spec.identity:
                        raise ValueError("checkpoint RunSpec identity 不匹配")
                    execution = _execution_from_dict(raw["execution"])
                    if (execution.scenario_id, execution.replicate) != (scenario_id, replicate):
                        raise ValueError("checkpoint execution identity 不匹配")
                else:
                    execution = executor.execute(scenario=scenario, replicate=replicate)
                    _atomic_write(
                        checkpoint,
                        {"format": "phase4-rag-e2e-checkpoint-v1", "run_spec_identity": spec.identity, "execution": asdict(execution)},
                    )
                executions.append(execution)

        # 步骤 4：全部下游只读共享 Evidence，不再次调用产品链路 --------------------------
        assertions: list[RAGAssertionResult] = []
        triage: list[dict[str, object]] = []
        for execution in executions:
            scenario = scenarios[execution.scenario_id]
            scored = score_execution(scenario, execution)
            assertions.extend(scored)
            triage.append(triage_execution(scenario, execution, scored))
        assertion_tuple = tuple(assertions)
        gate = project_gate(assertion_tuple)
        artifact = artifact_payload(
            run_spec=spec,
            executions=tuple(executions),
            assertions=assertion_tuple,
            gate=gate,
        )
        validate_completed_artifact(artifact)
        # 步骤 5：只有 closed-world 校验成功才签发长期 artifact 及其可读投影 ==============
        _atomic_write(artifact_path, artifact)
        _atomic_write(
            triage_path,
            {"format": "phase4-rag-e2e-triage-v1", "artifact_identity": artifact["artifact_identity"], "cases": triage},
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            render_report(artifact=artifact, scenarios=scenarios, triage=tuple(triage)), encoding="utf-8"
        )
        _atomic_write(
            manifest_path,
            {
                "format": "phase4-rag-e2e-manifest-v1",
                "status": "completed",
                "run_spec": asdict(spec),
                "run_spec_identity": spec.identity,
                "artifact_identity": artifact["artifact_identity"],
            },
        )
        return artifact
    except BaseException as exc:
        _atomic_write(
            manifest_path,
            {
                "format": "phase4-rag-e2e-manifest-v1",
                "status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                "run_spec": asdict(spec),
                "run_spec_identity": spec.identity,
                "error_type": type(exc).__name__,
            },
        )
        raise
