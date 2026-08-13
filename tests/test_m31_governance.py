"""M31 caller、ACL 与 outbound 的确定性安全合同。"""

from __future__ import annotations

import pytest

from engine.governance import (
    OutboundPolicy,
    OutboundRequest,
    OutboundRule,
    authenticated_caller,
    authorize_document,
    decide_outbound,
    demo_caller,
    test_caller as make_test_caller,
    unverified_request_caller,
)
from engine.rag.catalog import CatalogEntry, build_staged_catalog
from engine.nl2sql.generator import LLMGenerationError, QwenChatClient


def _entry_for_role(role: str, *, status: str = "active", purpose: str = "answer_evidence") -> CatalogEntry:
    return CatalogEntry(
        document_key=f"doc-{role}", revision="1", authority_ref="authority#anchor", source_kind="test",
        source_key="test", title="内部标题", knowledge_type="policy", status=status, anchor="anchor",
        data_class="role_restricted_policy_text", purposes=(purpose,), public=False,
        allowed_roles=frozenset({role}), content="不得出现在拒绝投影里的正文", content_identity="content-hash",
    )


@pytest.mark.parametrize("factory", [make_test_caller, demo_caller])
def test_explicit_fixture_callers_can_authorize_matching_role(factory) -> None:
    caller = factory(caller_id="fixture-1", roles={"ops"})
    decision = authorize_document(
        caller=caller, entry=_entry_for_role("ops"), purpose="answer_evidence", phase="pre_selection"
    )
    assert decision.allowed is True
    assert decision.reason_code == "authorized"


def test_authenticated_seam_is_trusted_but_request_role_tamper_is_not() -> None:
    entry = _entry_for_role("admin")
    authenticated = authenticated_caller(caller_id="subject-1", roles={"admin"}, identity_source="verified-sso")
    tampered = unverified_request_caller(caller_id="request-1", claimed_roles={"admin"})

    assert authorize_document(
        caller=authenticated, entry=entry, purpose="answer_evidence", phase="pre_selection"
    ).allowed
    denied = authorize_document(
        caller=tampered, entry=entry, purpose="answer_evidence", phase="pre_selection"
    )
    assert denied.allowed is False
    assert denied.reason_code == "caller_untrusted"
    assert tampered.resolved_roles == frozenset()


def test_admin_is_not_implicit_super_reader_and_denial_projection_has_no_side_channel() -> None:
    decision = authorize_document(
        caller=make_test_caller(caller_id="admin-1", roles={"admin"}),
        entry=_entry_for_role("customer_service"),
        purpose="answer_evidence",
        phase="pre_selection",
    )
    assert decision.allowed is False
    assert decision.reason_code == "role_not_allowed"
    projection = decision.public_projection()
    rendered = str(projection)
    assert projection["reason_code"] == "not_authorized"
    assert "doc-customer_service" not in rendered
    assert "内部标题" not in rendered
    assert "正文" not in rendered


@pytest.mark.parametrize(
    ("entry", "purpose", "expected"),
    [
        (_entry_for_role("ops", status="revoked"), "answer_evidence", "revision_unavailable"),
        (_entry_for_role("ops"), "generation_context", "purpose_not_allowed"),
    ],
)
def test_revision_and_purpose_fail_closed(entry: CatalogEntry, purpose: str, expected: str) -> None:
    decision = authorize_document(
        caller=make_test_caller(caller_id="ops-1", roles={"ops"}),
        entry=entry,
        purpose=purpose,
        phase="pre_generation",
    )
    assert (decision.allowed, decision.reason_code) == (False, expected)


def test_missing_authorization_policy_fails_closed() -> None:
    decision = authorize_document(
        caller=make_test_caller(caller_id="ops-1", roles={"ops"}),
        entry=_entry_for_role("ops"),
        purpose="answer_evidence",
        phase="pre_selection",
        policy=None,
    )
    assert (decision.allowed, decision.reason_code, decision.policy_identity) == (False, "policy_missing", "missing")


def test_current_catalog_acl_matrix_is_exact_for_every_role_and_purpose() -> None:
    catalog = build_staged_catalog()
    for entry in catalog.entries:
        for role in ("admin", "ops", "customer_service", "demo_user"):
            caller = make_test_caller(caller_id=f"fixture-{role}", roles={role})
            for purpose in ("answer_evidence", "analysis_constraint", "generation_context"):
                decision = authorize_document(caller=caller, entry=entry, purpose=purpose, phase="pre_selection")
                expected = purpose in entry.purposes and (entry.public or role in entry.allowed_roles)
                assert decision.allowed is expected, (entry.document_key, role, purpose, decision.reason_code)


def test_outbound_is_exact_by_receiver_purpose_data_class_and_fields() -> None:
    allowed = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat", node_purpose="query_plan", data_class="text2sql_prompt",
            fields=frozenset({"prompt", "system_prompt", "model"}), fallback_available=False,
        )
    )
    wrong_purpose = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat", node_purpose="answer_composer", data_class="text2sql_prompt",
            fields=frozenset({"prompt"}), fallback_available=True,
        )
    )
    knowledge = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat", node_purpose="sql_generation", data_class="document_evidence",
            fields=frozenset({"content"}), fallback_available=False,
        )
    )
    extra_field = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat", node_purpose="sql_generation", data_class="text2sql_prompt",
            fields=frozenset({"prompt", "secret"}), fallback_available=False,
        )
    )
    assert allowed.allowed
    assert (wrong_purpose.reason_code, wrong_purpose.fallback_action) == ("policy_missing", "continue_locally")
    assert (knowledge.allowed, knowledge.reason_code) == (False, "policy_missing")
    assert (extra_field.allowed, extra_field.reason_code) == (False, "fields_not_allowed")


def test_missing_outbound_policy_and_duplicate_rule_fail_closed() -> None:
    request = OutboundRequest("receiver", "purpose", "class", frozenset({"field"}), False)
    assert decide_outbound(request, policy=None).reason_code == "policy_missing"
    rule = OutboundRule("receiver", "purpose", "class", frozenset({"field"}))
    with pytest.raises(ValueError, match="outbound_policy_duplicate"):
        OutboundPolicy(rules=(rule, rule))


def test_real_chat_transport_checks_outbound_before_fake_network_capture() -> None:
    calls: list[dict[str, object]] = []

    def fake_post(_url, _headers, payload, _timeout):
        calls.append(payload)
        return {"choices": [{"message": {"content": "{}"}}]}

    client = QwenChatClient(api_key="fake", base_url="https://example.invalid", model="qwen", post_json=fake_post)
    assert client.complete(prompt="plan", system_prompt="system", node_purpose="query_plan") == "{}"
    assert len(calls) == 1

    with pytest.raises(LLMGenerationError) as captured:
        client.complete(prompt="knowledge", system_prompt="system", node_purpose="answer_composer")
    assert captured.value.error_subtype == "outbound_denied"
    assert len(calls) == 1  # deny 发生在 transport 之前，fake network 没看到第二个 payload。
