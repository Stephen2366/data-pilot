"""M46-P2/P3：external B4 Subgraph 的单题 Live Dev Probe runner。

这个脚本只允许两个已解封 historical diagnostic 场景，且 runtime 从 server Settings 读取；它不读取
reserve、gold、title 或 expected document ID。输出是可写入 notes 的安全摘要，prompt/raw response
不落仓库。
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from engine.governance import test_caller
from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.phase4b.external_requirement_formation import (
    B4QuestionObligationSupplier,
    ExternalRequirementFormer,
)
from engine.phase4b.rag_recovery_requirement_proposal import (
    make_b4_qwen_requirement_proposal_client,
)
from engine.phase4b.rag_subgraph import BoundedRAGSubgraphAcquirer, ExternalFormationSlotProvider
from engine.rag.answer_flow import AnswerEvidenceRequirement, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.enterprise_product_runtime import EnterpriseProductRuntimeConfig, load_enterprise_product_runtime
from engine.rag.evidence_acquisition import PipelineEvidenceAcquirer


_SCENARIOS = {
    "qst_0420": "For EXP-002 (eu-west→us-east), what egress cost rate and measurement basis does the cost penalty catalog use?",
    "qst_0431": "What is the procedure for an emergency rollback of a Serving Runtime release (Hosted and Dedicated)?",
}
_PROBE_IDS = {"qst_0420": "M46-P2", "qst_0431": "M46-P3"}


class _RecordingKnowledgeTool:
    """Probe-only wrapper：不改请求，只记录 hash、typed结果和adapter call可见性。"""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.attempts: list[dict[str, Any]] = []

    def retrieve(self, request: Any) -> Any:
        row: dict[str, Any] = {
            "ordinal": len(self.attempts) + 1,
            "query_fingerprint": canonical_hash(request.question),
            "status": "started",
            "reason_code": "not_observed",
            "adapter_calls": None,
        }
        self.attempts.append(row)
        try:
            outcome = self._delegate.retrieve(request)
        except Exception as exc:  # noqa: BLE001 - 只记录allowlist类别，不记录message。
            row.update({
                "status": "raised",
                "reason_code": (
                    "knowledge_tool_contract" if type(exc).__name__ == "KnowledgeToolContractError"
                    else "retrieval_adapter" if type(exc).__name__ == "RetrievalAdapterError"
                    else "evidence_contract" if type(exc).__name__ == "EvidenceContractError"
                    else "unexpected"
                ),
            })
            raise
        row.update({
            "status": outcome.execution_outcome,
            "reason_code": outcome.reason_code,
            "adapter_calls": outcome.diagnostics.adapter_calls,
        })
        return outcome


class _RecordingSlotProvider:
    """Probe-only wrapper：保存本次private requirement，绝不写入safe artifact。"""

    def __init__(self, delegate: ExternalFormationSlotProvider) -> None:
        self._delegate = delegate
        self.identity = delegate.identity
        self.last_resolution: Any | None = None

    def resolve(self, *, request: Any, initial: Any) -> Any:
        self.last_resolution = self._delegate.resolve(request=request, initial=initial)
        return self.last_resolution


def _safe_payload(
    *,
    scenario_id: str,
    result: Any,
    composer_usage: dict[str, int],
    composer_attempt: dict[str, Any] | None,
    retrieval_attempts: list[dict[str, Any]],
    runtime_identity: dict[str, Any],
) -> dict[str, Any]:
    """把子图事实压成可长期保存的 Probe 摘要。

    admission 字段只能是 subgraph 已经脱敏后的枚举；此处绝不从 request、slot 或 Evidence
    提取题面、token、正文、标题或 document identity，避免“为排障而重新泄露私有输入”。
    """

    validity = dict(result.evidence_validity)
    child = dict(validity.get("subgraph", {}))
    attempts = [
        {key: item.get(key) for key in ("ordinal", "action", "status", "eligible_actions", "rejected_actions", "progress_reason")}
        for item in child.get("attempts", [])
        if isinstance(item, dict)
    ]
    consumption = dict(child.get("consumption") or {})
    retrieval_attempts_observed = all(
        isinstance(item.get("adapter_calls"), int) for item in retrieval_attempts
    )
    embedding_attempts = sum(
        int(item["adapter_calls"])
        for item in retrieval_attempts
        if isinstance(item.get("adapter_calls"), int)
    )
    formation_calls = int(consumption.get("proposal_calls", 0))
    formation_tokens = int(consumption.get("total_tokens", 0))
    composer_calls = int(composer_usage.get("request_count", 0))
    composer_tokens = int(composer_usage.get("total_tokens", 0))
    composer_successes = int(composer_usage.get("successful_response_count", 0))
    composer_token_usage_observed = composer_calls == 0 or composer_successes == composer_calls
    return {
        "schema_version": "phase4b-m46-live-probe-v1",
        "probe_id": _PROBE_IDS[scenario_id],
        "probe_scenario": scenario_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "available": result.execution_status != "external_unavailable",
        "result_four_axes": {
            "route_status": result.route_status,
            "execution_status": result.execution_status,
            "safety_status": result.safety_status,
            "answer_status": result.answer_status,
            "reason_code": result.reason_code,
        },
        "answer_fingerprint": canonical_hash(result.answer) if result.answer else "not_observed",
        "claim_count": len(result.claims),
        "citation_count": len(result.citations),
        "docs_used_count": len(result.docs_used),
        "answer_flow_diagnostics": result.diagnostics.safe_projection(),
        "child_termination": child.get("termination"),
        "child_detail_code": child.get("detail_code"),
        "child_admission_decision": child.get("admission_decision"),
        "child_admission_reason_code": child.get("admission_reason_code"),
        "child_formed_requirements": child.get("formed_requirements", []),
        "child_attempts": attempts,
        "child_consumption": child.get("consumption"),
        "retrieval_attempts": retrieval_attempts,
        "provider_usage": {
            "embedding_attempts": embedding_attempts,
            "formation_calls": formation_calls,
            "formation_tokens": formation_tokens,
            "composer_calls": composer_calls,
            "composer_tokens": composer_tokens,
            "total_attempts": embedding_attempts + formation_calls + composer_calls,
            "total_observed_tokens": formation_tokens + composer_tokens,
            "token_usage_observed": (
                bool(consumption.get("token_usage_observed", False))
                and composer_token_usage_observed
            ),
            "retrieval_attempts_observed": (
                retrieval_attempts_observed
                and bool(consumption.get("retrieval_attempts_observed", False))
            ),
            "composer_token_usage_observed": composer_token_usage_observed,
            "composer_successful_responses": composer_successes,
        },
        "composer_attempt": composer_attempt,
        "runtime_identity": runtime_identity,
        "reserve_access_state": "sealed",
    }


def run_probe(scenario_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行恰好一题；qst ID 只在 runner 外层选择问题，绝不进入 Subgraph input。"""

    question = _SCENARIOS[scenario_id]
    settings = get_settings()
    product = load_enterprise_product_runtime(config=EnterpriseProductRuntimeConfig.from_settings(settings))
    try:
        tool = _RecordingKnowledgeTool(product.runtime.knowledge_tool())
        supplier = B4QuestionObligationSupplier(make_b4_qwen_requirement_proposal_client(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=settings.qwen_model or "qwen3.7-plus",
            timeout=settings.llm_timeout_seconds,
        ))
        composer = make_qwen_evidence_composer(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=settings.qwen_model or "qwen3.7-plus",
            timeout=settings.llm_timeout_seconds,
        )
        slot_provider = _RecordingSlotProvider(ExternalFormationSlotProvider(ExternalRequirementFormer(
            structured_supplier=supplier,
        )))
        acquirer = BoundedRAGSubgraphAcquirer(
            initial_acquirer=PipelineEvidenceAcquirer(
                knowledge_tool=tool, active_loader=product.runtime.active_loader,
            ),
            knowledge_tool=tool,
            active_loader=product.runtime.active_loader,
            slot_provider=slot_provider,
            runtime_scope="external_profile",
            expansion_adapter=EnterpriseSiblingExpansionAdapter(product.runtime),
        )
        flow = RAGAnswerFlow(
            knowledge_tool=tool,
            composer=composer,
            active_loader=product.runtime.active_loader,
            evidence_acquirer=acquirer,
            retrieval_snapshot=product.identity.safe_projection(),
        )
        result = flow.run(RAGAnswerRequest(
            question=question,
            caller=test_caller(caller_id=f"m46-{scenario_id}", roles=("demo_user",)),
            run_id=f"m46-{scenario_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            requirement=AnswerEvidenceRequirement(),
            knowledge_runtime_kind="external_profile",
        ))
        safe = _safe_payload(
            scenario_id=scenario_id,
            result=result,
            composer_usage=composer.usage_projection(),
            composer_attempt=composer.attempts[-1] if composer.attempts else None,
            retrieval_attempts=tool.attempts,
            runtime_identity=product.identity.safe_projection(),
        )
        resolution = slot_provider.last_resolution
        private = {
            "schema_version": "phase4b-m46-live-probe-private-v1",
            "probe_scenario": scenario_id,
            "answer": result.answer,
            "claims": [asdict(item) for item in result.claims],
            "citations": [asdict(item) for item in result.citations],
            "formed_requirements": [] if resolution is None else [
                {
                    "identity": item.slot.identity,
                    "focused_query": item.slot.focused_query,
                    "support_marker_groups": item.slot.support_marker_groups,
                    "value_shape": item.slot.value_shape,
                    "allowed_recovery_actions": item.allowed_recovery_actions,
                }
                for item in resolution.formed_requirements
            ],
        }
        return safe, private
    finally:
        product.close()


def main() -> None:
    """始终先固化安全摘要；即使 provider/runtime 异常也不依赖 stdout 作为唯一证据。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(_SCENARIOS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    private_root = (Path.cwd() / ".agent_work" / "temp").resolve()
    private_output = args.private_output.resolve()
    if private_root != private_output.parent and private_root not in private_output.parents:
        parser.error("--private-output must stay under .agent_work/temp")
    exit_code = 0
    try:
        payload, private_payload = run_probe(args.scenario)
    except Exception as exc:  # noqa: BLE001 - Probe 仍须留下稳定、无 raw detail 的失败证据。
        payload = {
            "schema_version": "phase4b-m46-live-probe-v1",
            "probe_id": _PROBE_IDS[args.scenario],
            "probe_scenario": args.scenario,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "available": False,
            "result_four_axes": {
                "execution_status": "failed", "safety_status": "passed", "answer_status": "no_answer",
            },
            "child_termination": "not_observed",
            "child_detail_code": getattr(exc, "reason_code", type(exc).__name__),
            "child_attempts": [],
            "child_consumption": None,
            "runtime_identity": None,
            "reserve_access_state": "sealed",
        }
        private_payload = {
            "schema_version": "phase4b-m46-live-probe-private-v1",
            "probe_scenario": args.scenario,
            "answer": None,
            "claims": [],
            "citations": [],
        }
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(
        json.dumps(private_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "scenario": args.scenario,
        "probe_id": payload["probe_id"],
        "output": str(args.output),
        "available": payload["available"],
        "child_termination": payload["child_termination"],
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
