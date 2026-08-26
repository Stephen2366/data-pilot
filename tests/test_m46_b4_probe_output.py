"""M46 Probe runner：安全摘要必须带回 admission 枚举，但不能回流私有输入。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.probe_m46_b4_external import _safe_payload


def test_probe_safe_payload_keeps_only_admission_enums() -> None:
    """runner 不能因二次投影丢失子图已经脱敏的排障结论。"""

    result = SimpleNamespace(
        route_status="rag",
        execution_status="completed",
        safety_status="passed",
        answer_status="complete",
        reason_code="answer_completed",
        answer="must-not-be-persisted",
        claims=(object(),),
        citations=(object(),),
        docs_used=({"ref": "safe"},),
        diagnostics=SimpleNamespace(safe_projection=lambda: {"composer_calls": 1}),
        evidence_validity={
            "subgraph": {
                "termination": "contract_failure",
                "detail_code": "proposal_no_unsupported_requirement",
                "admission_decision": "proposal_failed",
                "admission_reason_code": "no_shared_anchor",
                "attempts": (),
                "consumption": {
                    "initial_retrieval_batches": 1,
                    "rewrite_retrieval_batches": 2,
                    "proposal_calls": 1,
                    "total_tokens": 321,
                    "token_usage_observed": True,
                    "retrieval_attempts_observed": True,
                },
                # 这个私有字段模拟未来错误输入；safe payload 不得透传未知内容。
                "question": "must-not-be-persisted",
            }
        },
    )
    payload = _safe_payload(
        scenario_id="qst_0420",
        result=result,
        composer_usage={"request_count": 1, "successful_response_count": 1, "total_tokens": 456},
        composer_attempt={"status": "succeeded", "usage_delta": {"total_tokens": 456}},
        retrieval_attempts=[
            {"ordinal": 1, "adapter_calls": 1},
            {"ordinal": 2, "adapter_calls": 1},
            {"ordinal": 3, "adapter_calls": 1},
        ],
        runtime_identity={"adapter": "fixture"},
    )

    assert payload["child_admission_decision"] == "proposal_failed"
    assert payload["probe_id"] == "M46-P2"
    assert payload["child_admission_reason_code"] == "no_shared_anchor"
    assert "question" not in payload
    assert "must-not-be-persisted" not in str(payload)
    assert payload["answer_fingerprint"] != "not_observed"
    assert payload["claim_count"] == payload["citation_count"] == 1
    assert payload["provider_usage"] == {
        "embedding_attempts": 3,
        "formation_calls": 1,
        "formation_tokens": 321,
        "composer_calls": 1,
        "composer_tokens": 456,
        "total_attempts": 5,
        "total_observed_tokens": 777,
        "token_usage_observed": True,
        "retrieval_attempts_observed": True,
        "composer_token_usage_observed": True,
        "composer_successful_responses": 1,
    }


def test_probe_cli_requires_private_output_inside_temp_boundary() -> None:
    """完整回答只能写入 gitignored private temp，不能误写到 notes/eval安全artifact。"""

    from scripts.probe_m46_b4_external import main

    with pytest.raises(SystemExit):
        # argparse 会在任何真实 runtime 加载前拒绝越界路径。
        import sys

        original = sys.argv
        sys.argv = [
            "probe_m46_b4_external",
            "--scenario", "qst_0420",
            "--output", "docs/notes/safe.json",
            "--private-output", "docs/notes/raw-answer.json",
        ]
        try:
            main()
        finally:
            sys.argv = original


def test_probe_marks_tokens_unobserved_when_composer_request_has_no_response() -> None:
    """网络失败后的0 tokens不是已观测0，不能用于通过预算门。"""

    result = SimpleNamespace(
        route_status="rag",
        execution_status="failed",
        safety_status="passed",
        answer_status="no_answer",
        reason_code="composer_unavailable",
        answer=None,
        claims=(),
        citations=(),
        docs_used=(),
        diagnostics=SimpleNamespace(safe_projection=lambda: {"composer_calls": 1}),
        evidence_validity={"subgraph": {"attempts": (), "consumption": {
            "initial_retrieval_batches": 1,
            "proposal_calls": 1,
            "total_tokens": 100,
            "token_usage_observed": True,
            "retrieval_attempts_observed": False,
        }}},
    )

    payload = _safe_payload(
        scenario_id="qst_0420",
        result=result,
        composer_usage={"request_count": 1, "successful_response_count": 0, "total_tokens": 0},
        composer_attempt={"status": "failed", "usage_delta": {"total_tokens": 0}},
        retrieval_attempts=[{"ordinal": 1, "adapter_calls": None}],
        runtime_identity={"adapter": "fixture"},
    )

    assert payload["provider_usage"]["composer_token_usage_observed"] is False
    assert payload["provider_usage"]["token_usage_observed"] is False
    assert payload["provider_usage"]["retrieval_attempts_observed"] is False
