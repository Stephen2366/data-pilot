"""M46-P0：只观察 external requirement formation → eligible action，不执行 recovery。

runner 固定为一条已解封 historical diagnostic dev 问题。qst ID 只在 CLI 外壳选择公开问题，
不会进入 formation/subgraph input；不读取 gold/title/expected docs/reserve，也不调用 Composer。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.config import get_settings
from engine.governance import test_caller
from engine.phase4b.external_requirement_formation import (
    B4QuestionObligationSupplier,
    ExternalRequirementFormationInput,
    ExternalRequirementFormer,
    RequirementFormationResult,
)
from engine.phase4b.rag_diagnostics import RAGRecoveryDiagnostic, RecoveryObservation
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.phase4b.rag_recovery_requirement_proposal import make_b4_qwen_requirement_proposal_client
from engine.rag.answer_flow import RAGAnswerRequest
from engine.rag.enterprise_product_runtime import EnterpriseProductRuntimeConfig, load_enterprise_product_runtime
from engine.rag.evidence_acquisition import AcquisitionResult, PipelineEvidenceAcquirer
from engine.rag.knowledge_tool import KnowledgeRequest


_SCENARIOS = {
    "qst_0420": (
        "For EXP-002 (eu-west→us-east), what egress cost rate and measurement basis "
        "does the cost penalty catalog use?"
    ),
}


def _safe_payload(
    *,
    scenario_id: str,
    initial: AcquisitionResult,
    formation: RequirementFormationResult | None,
    observation: RecoveryObservation | None,
    runtime_identity: dict[str, Any],
) -> dict[str, Any]:
    """只保留 hash/枚举/usage/action facts；不复用含 slot identity 的旧 Observation 投影。"""

    outcome = initial.outcome
    return {
        "schema_version": "phase4b-m46-d0-live-probe-v1",
        "probe_id": "M46-P0",
        "classification": "exploratory",
        "baseline_eligible": False,
        "probe_scenario": scenario_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "initial": {
            "execution_outcome": outcome.execution_outcome,
            "reason_code": (
                "evidence_retrieved" if outcome.reason_code == "evidence_retrieved"
                else "retrieval_unavailable" if outcome.execution_outcome == "external_unavailable"
                else "evidence_not_available"
            ),
            "selected_count": len(outcome.selected_evidence),
            "diagnostics": outcome.diagnostics.safe_projection(),
        },
        "formation": formation.safe_projection() if formation is not None else None,
        "observation": None if observation is None else {
            "requirement_signature": observation.requirement_signature,
            "eligible_actions": list(observation.eligible_actions),
            "rejected_actions": list(observation.rejected_actions),
            "expansion_preview_count": sum(
                len(item.opaque_candidates) for item in observation.expansion_previews
            ),
            "continuation_policy": observation.continuation_policy,
            "trigger_reason_codes": list(observation.trigger_reason_codes),
        },
        "recovery_action_executions": 0,
        "runtime_identity": runtime_identity,
        "reserve_access_state": "sealed",
    }


def run_probe(scenario_id: str) -> dict[str, Any]:
    """执行 initial retrieval + formation + Observation，明确在 action executor 前停止。"""

    question = _SCENARIOS[scenario_id]
    settings = get_settings()
    product = load_enterprise_product_runtime(
        config=EnterpriseProductRuntimeConfig.from_settings(settings)
    )
    try:
        tool = product.runtime.knowledge_tool()
        request = RAGAnswerRequest(
            question=question,
            caller=test_caller(caller_id=f"m46-p0-{scenario_id}", roles=("demo_user",)),
            run_id=f"m46-p0-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            knowledge_runtime_kind="external_profile",
        )
        initial = PipelineEvidenceAcquirer(
            knowledge_tool=tool,
            active_loader=product.runtime.active_loader,
        ).acquire(request=request, started_at=perf_counter())
        formation: RequirementFormationResult | None = None
        observation: RecoveryObservation | None = None
        if initial.outcome.execution_outcome == "completed" and initial.outcome.selected_evidence:
            supplier = B4QuestionObligationSupplier(
                make_b4_qwen_requirement_proposal_client(
                    api_key=settings.dashscope_api_key,
                    base_url=settings.dashscope_base_url,
                    model=settings.qwen_model or "qwen3.7-plus",
                    timeout=settings.llm_timeout_seconds,
                )
            )
            formation = ExternalRequirementFormer(structured_supplier=supplier).form(
                formation_input=ExternalRequirementFormationInput(
                    question=question,
                    current_evidence=initial.outcome.selected_evidence,
                )
            )
            if formation.requirements:
                observation = RAGRecoveryDiagnostic().observe_existing(
                    scenario_id="M46-P0",
                    runtime_scope="external_profile",
                    slots=tuple(item.slot for item in formation.requirements),
                    initial=initial.outcome,
                    request=KnowledgeRequest(
                        question=question,
                        caller=request.caller,
                        purpose=request.purpose,
                        run_id=request.run_id,
                        budget=request.retrieval_budget,
                        confirmed_conditions=request.confirmed_conditions,
                    ),
                    expansion_adapter=EnterpriseSiblingExpansionAdapter(product.runtime),
                    continuation_policy=formation.continuation_policy,
                )
        return _safe_payload(
            scenario_id=scenario_id,
            initial=initial,
            formation=formation,
            observation=observation,
            runtime_identity=product.identity.safe_projection(),
        )
    finally:
        product.close()


def main() -> None:
    """无论成功/失败都持久化安全摘要；当前实现不会执行 recovery action。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(_SCENARIOS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    exit_code = 0
    try:
        payload = run_probe(args.scenario)
    except Exception as exc:  # noqa: BLE001 - 公开摘要不回显 raw exception。
        payload = {
            "schema_version": "phase4b-m46-d0-live-probe-v1",
            "probe_id": "M46-P0",
            "classification": "exploratory",
            "baseline_eligible": False,
            "probe_scenario": args.scenario,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "initial": None,
            "formation": None,
            "observation": None,
            "recovery_action_executions": 0,
            "failure_reason": str(getattr(exc, "reason_code", "probe_runtime_failure")),
            "reserve_access_state": "sealed",
        }
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "probe_id": "M46-P0",
        "scenario": args.scenario,
        "output": str(args.output),
        "initial_status": (payload.get("initial") or {}).get("execution_outcome"),
        "formation_decision": (payload.get("formation") or {}).get("decision"),
        "recovery_action_executions": payload.get("recovery_action_executions"),
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
