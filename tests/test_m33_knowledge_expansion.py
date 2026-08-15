"""M33 后续 Knowledge corpus 扩充的 authority、检索、回答和 release 合同。"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.governance import test_caller as make_test_caller
from engine.rag import build_staged_catalog
from engine.rag.answer_flow import AnswerEvidenceRequirement, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import (
    G3Approval,
    activate_release,
    build_candidate_release,
    load_active_release,
)
from engine.rag.retrieval import RetrievalBudget


NEW_METRIC_KEYS = {
    "refund_rate",
    "item_gmv",
    "net_revenue",
    "order_count",
    "refund_count",
    "net_refund_amount",
    "avg_selling_price",
    "pending_high_priority_ticket_count",
}
NEW_POLICY_KEYS = {
    "realtime_fact_boundary",
    "evidence_escalation_rule",
    "coupon_application_boundary",
}


@pytest.fixture
def expanded_loader(tmp_path: Path):
    """在隔离目录发布完整 candidate，生产 pointer 切换前也能验证 AnswerFlow。"""

    staged = build_staged_catalog()
    bundle = build_candidate_release(staged=staged, root=tmp_path)
    activate_release(
        bundle=bundle,
        staged=staged,
        approval=G3Approval(
            decision="A",
            approved_by_ref="user-confirmed-m33-corpus-expansion",
            approved_at="2026-08-15",
        ),
        root=tmp_path,
    )
    return lambda: load_active_release(root=tmp_path)


def _answer(question: str, *, role: str, document_key: str, term: str, active_loader):
    """通过公开 AnswerFlow interface 验证新增 authority 能形成 cited answer。"""

    return RAGAnswerFlow(
        knowledge_tool=KnowledgeTool(active_loader=active_loader),
        active_loader=active_loader,
    ).run(
        RAGAnswerRequest(
            question=question,
            caller=make_test_caller(caller_id=f"m33-expansion-{role}", roles={role}),
            run_id=f"m33-expansion-{document_key}",
            requirement=AnswerEvidenceRequirement(
                required_document_keys=(document_key,),
                required_terms=(term,),
                max_claims=1,
            ),
            retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=1),
        )
    )


def test_expanded_catalog_has_22_unique_authority_backed_entries() -> None:
    """扩充后仍由 10 份 Markdown 与 12 条 metric projection 唯一构建。"""

    catalog = build_staged_catalog()
    metric_keys = {entry.source_key for entry in catalog.entries if entry.source_kind == "metric_projection"}
    policy_keys = {entry.document_key for entry in catalog.entries if entry.source_kind == "policy_markdown"}

    assert len(catalog.entries) == len(catalog.usable_entries) == 22
    assert catalog.summary()["counts_by_source"] == {"metric_projection": 12, "policy_markdown": 10}
    assert NEW_METRIC_KEYS <= metric_keys
    assert NEW_POLICY_KEYS <= policy_keys
    assert len({entry.anchor for entry in catalog.entries}) == 22
    assert len({entry.content_identity for entry in catalog.entries}) == 22


def test_boundary_documents_add_no_numeric_business_promise() -> None:
    """三份补充文档只冻结处理边界，不创造金额、时限或资格数字。"""

    catalog = build_staged_catalog()
    contents = {
        entry.document_key: entry.content
        for entry in catalog.entries
        if entry.document_key in NEW_POLICY_KEYS
    }
    assert set(contents) == NEW_POLICY_KEYS
    assert all(not any(character.isdigit() for character in content) for content in contents.values())
    assert "以对应专项规则为准" in contents["realtime_fact_boundary"]
    assert "不提高任何专项规则的默认材料要求" in contents["evidence_escalation_rule"]
    assert "不能证明某张优惠券可用于某个订单" in contents["coupon_application_boundary"]


def test_new_metric_projection_is_derived_and_answerable(expanded_loader) -> None:
    """新增退款率正文来自 metrics authority，并可形成 validated citation。"""

    catalog = build_staged_catalog()
    entry = next(item for item in catalog.entries if item.document_key == "refund_rate_note")
    assert entry.authority_ref == "domain_pack/metrics.yaml#metrics.refund_rate"
    assert "completed_refunded_order_count / completed_order_count" in entry.content

    result = _answer(
        "退款率指标口径和公式是什么？",
        role="ops",
        document_key="refund_rate_note",
        term="completed_refunded_order_count / completed_order_count",
        active_loader=expanded_loader,
    )
    assert (result.answer_status, result.safety_status) == ("complete", "passed")
    assert result.citations[0].anchor == "metric-refund-rate"


def test_new_boundary_documents_are_answerable_without_overriding_specialized_rules(expanded_loader) -> None:
    """三类附加说明可检索回答，同时明确把专项规则和实时事实留在原事实源。"""

    cases = (
        ("具体订单当前的实时业务事实能只看静态知识文档吗？", "realtime_fact_boundary", "不能单独证明"),
        ("申请材料不足、规则无法确定时客服应该怎么处理？", "evidence_escalation_rule", "转人工复核"),
        ("优惠券是否有效、适用商品和实际抵扣额以什么为准？", "coupon_application_boundary", "业务事实"),
    )
    for question, key, term in cases:
        result = _answer(
            question,
            role="customer_service",
            document_key=key,
            term=term,
            active_loader=expanded_loader,
        )
        assert (result.answer_status, result.safety_status) == ("complete", "passed")
        assert len(result.claims) == len(result.citations) == 1


def test_active_release_contains_expansion_and_keeps_previous_identity() -> None:
    """发布后 active 必须是完整 22-entry bundle，previous 精确指向旧 11-entry release。"""

    pointer, bundle = load_active_release()
    assert len(bundle.entries) == 22
    assert NEW_POLICY_KEYS <= {entry.document_key for entry in bundle.entries}
    assert pointer.previous_release_identity == "4e86bdddbf15ca7ce1284f27b7507fedac70a69c098f5a1952cf6e71001e95a7"
