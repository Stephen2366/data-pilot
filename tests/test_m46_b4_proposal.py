"""M46-D0：C2-ERF deep module 的 interface、负断言和 M45 action-card 兼容。"""

from __future__ import annotations

from dataclasses import replace

from engine.governance import demo_caller
from engine.nl2sql.generator import LLMGenerationError
from engine.phase4b.external_requirement_formation import (
    B4QuestionObligationSupplier,
    ExternalRequirementFormationInput,
    ExternalRequirementFormer,
)
from engine.phase4b.rag_subgraph import ChildLedger, ExternalFormationSlotProvider
from engine.phase4b.rag_diagnostics import RAGRecoveryDiagnostic
from engine.rag.answer_flow import RAGAnswerRequest
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool


QUESTION = (
    "For EXP-002 (eu-west→us-east), what egress cost rate and measurement basis "
    "does the cost penalty catalog use?"
)


def _input(*, content: str, question: str = QUESTION) -> ExternalRequirementFormationInput:
    """用真实 typed Evidence 外壳构造离线 replay；不访问 external profile/provider。"""

    caller = demo_caller(caller_id="m46-d0", roles=("ops", "customer_service"))
    initial = KnowledgeTool().retrieve(KnowledgeRequest(
        question="质量问题退款需要哪些材料？",
        caller=caller,
        purpose="answer_evidence",
        run_id="m46-d0",
    ))
    evidence = tuple(
        replace(item, payload=replace(item.payload, content=content))
        for item in initial.selected_evidence
    )
    return ExternalRequirementFormationInput(question=question, current_evidence=evidence)


class _ObligationTransport:
    """返回 question-grounded atomic obligations；不返回 query、marker 或 coverage。"""

    model = "fixture-qwen"

    def __init__(self, raw: str | None = None) -> None:
        self.request_count = 0
        self.total_tokens = 0
        self.prompt = ""
        self.raw = raw or (
            '{"obligations":['
            '{"reason_category":"requested_fact",'
            '"question_anchor":"EXP-002","requested_aspect":"egress cost rate",'
            '"entity_constraints":["EXP-002","eu-west","us-east"],'
            '"qualifier_category":"current_authority","value_shape":"numeric"},'
            '{"reason_category":"requested_fact",'
            '"question_anchor":"EXP-002","requested_aspect":"measurement basis",'
            '"entity_constraints":["EXP-002","eu-west","us-east"],'
            '"qualifier_category":"current_authority","value_shape":"none"}'
            ']}'
        )

    def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str) -> str:
        del system_prompt
        assert node_purpose == "rag_recovery_requirement_proposal"
        self.request_count += 1
        self.total_tokens += 321
        self.prompt = prompt
        return self.raw


class _FailingTransport(_ObligationTransport):
    def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str) -> str:
        del prompt, system_prompt
        assert node_purpose == "rag_recovery_requirement_proposal"
        self.request_count += 1
        raise LLMGenerationError("fixture", error_subtype="network_error")


def test_question_obligation_supplier_forms_two_action_card_compatible_requirements() -> None:
    """qst_0420 离线 replay：实体来自题面，query/coverage 归服务端，M45 executor 可直接消费 slot。"""

    transport = _ObligationTransport()
    formation_input = _input(
        content="EXP-002 egress cost penalty catalog overview for eu-west and us-east regions."
    )
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(transport)
    ).form(formation_input)

    assert result.decision == "structured_question_obligations"
    assert result.reason_code == "eligible"
    assert result.usage.calls == 1 and result.usage.total_tokens == 321
    assert result.prompt_fingerprint != "not_observed"
    assert result.response_fingerprint != "not_observed"
    assert all(item.slot.identity.startswith("question_obligation_") for item in result.requirements)
    assert len({item.slot.identity for item in result.requirements}) == 2
    assert all(item.supplier_identity.endswith("question-obligation-supplier-v1") for item in result.requirements)
    assert all(item.allowed_recovery_actions == (
        "query_rewrite_candidate", "context_expansion_candidate",
    ) for item in result.requirements)
    assert all(not item.slot.supported_by(formation_input.current_evidence) for item in result.requirements)
    assert '"focused_query"' not in transport.prompt
    assert "Do not write a focused query" in transport.prompt
    # 用户给出的 identifier/region 是合法检索约束；模型没有获得创造答案值的权限。
    assert "EXP-002" in result.requirements[0].slot.focused_query
    assert "eu-west" in result.requirements[0].slot.focused_query
    # 普通 does/use 只是英语现在时，不足以要求“最新权威版本”；模型误分类由服务端降级。
    assert all("current authoritative effective" not in item.slot.focused_query for item in result.requirements)
    assert "Ordinary present-tense wording" in transport.prompt


def test_explicit_current_cue_keeps_current_authority_qualifier() -> None:
    """题面明确说 current 时保留 freshness requirement，不能一律降级成 none。"""

    question = "What is the current egress cost rate for EXP-002?"
    raw = (
        '{"obligations":[{"reason_category":"requested_fact",'
        '"question_anchor":"current egress cost rate","requested_aspect":"egress cost rate",'
        '"entity_constraints":["EXP-002"],"qualifier_category":"current_authority",'
        '"value_shape":"numeric"}]}'
    )
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport(raw))
    ).form(_input(question=question, content="EXP-002 egress catalog overview."))

    assert result.decision == "structured_question_obligations"
    assert "current authoritative effective" in result.requirements[0].slot.focused_query


def test_formed_requirements_close_against_future_same_document_evidence() -> None:
    """兼容 M45 action executor 的核心语义：新增 Evidence 后原 slot 能由确定性 coverage 闭合。"""

    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport())
    ).form(_input(content="EXP-002 egress catalog overview for eu-west and us-east."))
    future = _input(content=(
        "The current approved EXP-002 eu-west to us-east egress cost rate is $0.10 USD. "
        "The measurement basis is GiB in the effective catalog."
    )).current_evidence

    assert all(item.slot.supported_by(future) for item in result.requirements)


def test_dev_paraphrase_forms_same_atomic_requirement_family() -> None:
    """换一种自然问法仍形成相同两项业务要求，不靠 qst ID/recipe。"""

    question = (
        "Which measurement basis and egress charge rate does EXP-002 apply "
        "from eu-west to us-east?"
    )
    raw = (
        '{"obligations":['
        '{"reason_category":"requested_fact",'
        '"question_anchor":"EXP-002","requested_aspect":"measurement basis",'
        '"entity_constraints":["EXP-002","eu-west","us-east"],'
        '"qualifier_category":"current_authority","value_shape":"none"},'
        '{"reason_category":"requested_fact",'
        '"question_anchor":"EXP-002","requested_aspect":"egress charge rate",'
        '"entity_constraints":["EXP-002","eu-west","us-east"],'
        '"qualifier_category":"current_authority","value_shape":"numeric"}'
        ']}'
    )
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport(raw))
    ).form(_input(
        question=question,
        content="EXP-002 egress catalog overview for eu-west and us-east.",
    ))

    assert len(result.requirements) == 2
    assert all(item.slot.identity.startswith("question_obligation_") for item in result.requirements)
    assert result.reason_code == "eligible"


def test_model_cannot_invent_answer_value_or_non_question_constraint() -> None:
    """题面给出的值可作 constraint；题面没有的 $0.10 不能伪装成 requested aspect。"""

    raw = (
        '{"obligations":[{'
        '"reason_category":"requested_fact","question_anchor":"EXP-002",'
        '"requested_aspect":"$0.10","entity_constraints":["EXP-002"],'
        '"qualifier_category":"current_authority","value_shape":"numeric"}]}'
    )
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport(raw))
    ).form(_input(content="EXP-002 egress catalog overview."))

    assert result.requirements == ()
    assert result.decision == "structured_supplier_failed"
    assert result.reason_code == "formation_requested_aspect_not_source_spanned"
    assert result.usage.calls == 1


def test_weak_anchor_is_rejected_and_value_shape_is_server_normalized() -> None:
    """exact span 仍需有意义；rate 被模型降成 none 时由服务端恢复 numeric 要求。"""

    weak_anchor = (
        '{"obligations":[{"reason_category":"requested_fact","question_anchor":"the",'
        '"requested_aspect":"egress cost rate","entity_constraints":["EXP-002"],'
        '"qualifier_category":"current_authority","value_shape":"numeric"}]}'
    )
    weak_result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport(weak_anchor))
    ).form(_input(content="The EXP-002 egress catalog overview."))
    assert weak_result.reason_code == "formation_question_anchor_not_source_spanned"

    downgraded = (
        '{"obligations":[{"reason_category":"requested_fact","question_anchor":"EXP-002",'
        '"requested_aspect":"egress cost rate","entity_constraints":["EXP-002"],'
        '"qualifier_category":"current_authority","value_shape":"none"}]}'
    )
    downgraded_result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport(downgraded))
    ).form(_input(content="The EXP-002 egress catalog overview."))
    assert downgraded_result.reason_code == "eligible"
    assert downgraded_result.requirements[0].slot.value_shape == "numeric"
    assert not downgraded_result.requirements[0].slot.supported_by(
        _input(content="The EXP-002 egress cost rate overview has no numeric value.").current_evidence
    )


def test_unrelated_evidence_fails_closed_without_free_query() -> None:
    """无 Evidence anchor 时停止，但已发生的 supplier usage/hash 不能被失败路径抹掉。"""

    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport())
    ).form(_input(content="The kitchen handbook describes weekly cleanup."))

    assert result.requirements == ()
    assert result.reason_code == "formation_no_grounded_evidence_anchor"
    assert result.failure_reason == "formation_no_grounded_evidence_anchor"
    assert result.usage.model == "fixture-qwen"
    assert result.usage.calls == 1 and result.usage.total_tokens == 321
    assert result.usage.token_usage_observed is True
    assert result.prompt_fingerprint != "not_observed"
    assert result.response_fingerprint != "not_observed"


def test_server_grounding_uses_full_question_not_model_selected_anchor() -> None:
    """模型选了初检未出现的实体 anchor，也不能遮住题面与 Evidence 的其他真实共同词。"""

    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport())
    ).form(_input(content="The egress catalog contains regional transfer policies."))

    assert result.decision == "structured_question_obligations"
    assert len(result.requirements) == 2
    assert result.usage.calls == 1


def test_procedure_supplier_has_priority_and_is_expansion_only() -> None:
    """M45 procedure trigger 保持窄合同；命中时不得额外调用 structured supplier。"""

    transport = _FailingTransport()
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(transport)
    ).form(_input(
        question="What is the procedure for an emergency rollback (Hosted and Dedicated)?",
        content="Serving Runtime rollback overview for Hosted and Dedicated environments.",
    ))

    assert result.decision == "deterministic_procedure"
    assert result.continuation_policy == "procedure_boundary_v1"
    assert transport.request_count == 0
    assert all(item.allowed_recovery_actions == ("context_expansion_candidate",) for item in result.requirements)


def test_supplier_failure_keeps_usage_and_safe_projection_is_private_free() -> None:
    """provider failure 仍计一次；安全投影不保存 question/Evidence/prompt/raw response。"""

    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_FailingTransport())
    ).form(_input(content="EXP-002 egress catalog overview."))
    projection = result.safe_projection()

    assert result.reason_code == "formation_supplier_network_error"
    assert result.usage.calls == 1 and result.usage.token_usage_observed is False
    assert result.prompt_fingerprint != "not_observed"
    assert result.response_fingerprint == "not_observed"
    serialized = str(projection).casefold()
    assert "exp-002" not in serialized
    assert "question" not in projection
    assert "content" not in serialized
    assert "current authorized evidence" not in serialized
    assert "strict json" not in serialized


def test_adapter_and_child_ledger_expose_only_formed_requirement_hashes() -> None:
    """Subgraph 对账 C2-ERF facts，但不得把模型 identity/query/marker 写入 Trace。"""

    formation_input = _input(content="EXP-002 egress catalog overview for eu-west and us-east.")
    source_caller = demo_caller(caller_id="m46-d0-source", roles=("ops", "customer_service"))
    initial = KnowledgeTool().retrieve(KnowledgeRequest(
        question="质量问题退款需要哪些材料？",
        caller=source_caller,
        purpose="answer_evidence",
        run_id="m46-d0-adapter",
    ))
    initial = replace(initial, selected_evidence=formation_input.current_evidence)
    adapter = ExternalFormationSlotProvider(ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport())
    ))
    resolution = adapter.resolve(
        request=RAGAnswerRequest(
            question=QUESTION,
            caller=demo_caller(caller_id="m46-d0-adapter", roles=("demo_user",)),
            run_id="m46-d0-adapter",
        ),
        initial=initial,
    )
    ledger = ChildLedger(
        admission_decision=resolution.decision,
        admission_reason_code=resolution.admission_reason_code,
        formed_requirements=tuple(item.safe_projection() for item in resolution.formed_requirements),
    )
    serialized = str(ledger.safe_projection()).casefold()

    assert len(resolution.slots) == len(resolution.formed_requirements) == 2
    assert "slot_signature" in serialized
    assert "question_obligation_1_" not in serialized
    assert "measurement basis" not in serialized
    assert "exp-002" not in serialized


def test_formed_slots_feed_m45_observation_without_scenario_recipe() -> None:
    """D0 输出直接穿过 M45 action interface：当前缺口准入 rewrite，而非靠 qst 映射。"""

    formation_input = _input(content="EXP-002 egress catalog overview for eu-west and us-east.")
    source_caller = demo_caller(caller_id="m46-d0-observe", roles=("ops", "customer_service"))
    initial = KnowledgeTool().retrieve(KnowledgeRequest(
        question="质量问题退款需要哪些材料？",
        caller=source_caller,
        purpose="answer_evidence",
        run_id="m46-d0-observe",
    ))
    initial = replace(initial, selected_evidence=formation_input.current_evidence)
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(_ObligationTransport())
    ).form(formation_input)
    observation = RAGRecoveryDiagnostic().observe_existing(
        scenario_id="D0_OFFLINE_REPLAY",
        runtime_scope="external_profile",
        slots=tuple(item.slot for item in result.requirements),
        initial=initial,
        request=KnowledgeRequest(
            question=QUESTION,
            caller=source_caller,
            purpose="answer_evidence",
            run_id="m46-d0-observe",
        ),
    )

    assert observation.eligible_actions == ("query_rewrite_candidate", "stop")
    assert observation.rejected_actions == ("context_expansion_candidate",)
    assert len(observation.unsupported_slot_identities) == 2


def test_missing_document_evidence_is_typed_stop() -> None:
    """D0 不自行检索或扫描 authority；没有授权 Evidence 就在 supplier 前失败关闭。"""

    transport = _ObligationTransport()
    result = ExternalRequirementFormer(
        structured_supplier=B4QuestionObligationSupplier(transport)
    ).form(ExternalRequirementFormationInput(question=QUESTION, current_evidence=()))

    assert result.requirements == ()
    assert result.reason_code == "formation_authorized_evidence_missing"
    assert transport.request_count == 0
