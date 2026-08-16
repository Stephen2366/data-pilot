"""M34 自然语言 claim + 逐字 Evidence support 的生成合同。"""

from __future__ import annotations

import json
import re

import pytest

from engine.governance import test_caller as make_test_caller
from engine.rag.answer_flow import AnswerFlowContractError, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.enterprise_generation import (
    RemoteEvidenceComposer,
    _canonicalize_whitespace_only_support,
    make_qwen_evidence_composer,
)
from engine.rag.retrieval import RetrievalBudget


class _SupportAwareFakeClient:
    """从真实 prompt 取回 Evidence 元数据，避免测试伪造链路外的 ID。"""

    def __init__(self, *, support_text: str) -> None:
        self.support_text = support_text
        self.prompts: list[str] = []
        self.request_count = 0
        self.successful_response_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def complete(self, *, prompt: str, **_kwargs) -> str:
        self.prompts.append(prompt)
        self.request_count += 1
        self.successful_response_count += 1
        self.prompt_tokens += 10
        self.completion_tokens += 5
        self.total_tokens += 15
        match = re.search(r"\[evidence_id=([^ ]+) anchor=([^\]]+)\]", prompt)
        assert match is not None
        return json.dumps(
            {
                "claims": [
                    {
                        "text": "质量问题退款时，需要提交能证明问题的材料。",
                        "support_text": self.support_text,
                        "evidence_id": match.group(1),
                        "anchor": match.group(2),
                    }
                ]
            },
            ensure_ascii=False,
        )


def _request(run_id: str) -> RAGAnswerRequest:
    return RAGAnswerRequest(
        question="质量问题退款需要提供什么材料？",
        caller=make_test_caller(caller_id="m34-generation", roles={"customer_service"}),
        run_id=run_id,
        retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=1),
    )


def test_natural_paraphrase_is_allowed_when_exact_support_and_citation_validate() -> None:
    """展示文本不必逐字复制，但 support、Evidence 和 citation 必须形成同一条链。"""

    client = _SupportAwareFakeClient(support_text="质量问题")
    result = RAGAnswerFlow(composer=RemoteEvidenceComposer(client=client)).run(_request("m34-paraphrase"))

    assert result.answer_status == "complete"
    assert result.claims[0].text == "质量问题退款时，需要提交能证明问题的材料。"
    assert len(result.claims[0].citation_ids) == 1
    assert result.claims[0].citation_ids[0] == result.citations[0].citation_id
    assert "support_text" in client.prompts[0]
    assert result.diagnostics.composer_calls == 1


def test_fabricated_support_fails_closed_before_citation_validation() -> None:
    """自然改写不等于放开证据：不存在的逐字 support 仍是合同错误。"""

    client = _SupportAwareFakeClient(support_text="这段原文根本不存在")

    with pytest.raises(AnswerFlowContractError, match="composer_output_invalid"):
        RAGAnswerFlow(composer=RemoteEvidenceComposer(client=client)).run(_request("m34-fake-support"))

    assert client.request_count == 1


def test_qwen_factory_freezes_nonthinking_without_app_output_cap() -> None:
    """M34 专用 factory 关闭思考但不人为截断复杂回答，通用 client 默认值不变。"""

    composer = make_qwen_evidence_composer(
        api_key="key",
        base_url="https://example.test/v1",
        model="qwen3.7-plus",
    )

    assert composer.client.enable_thinking is False
    assert composer.client.max_tokens is None
    assert "nonthinking-unbounded" in composer.identity


def test_support_whitespace_is_canonicalized_without_fuzzy_text_changes() -> None:
    """换行/空格差异可还原；哪怕只改一个标点或字母也不能冒充逐字 support。"""

    content = "alpha\n  beta; gamma"

    assert _canonicalize_whitespace_only_support(content=content, proposed="alpha beta") == "alpha\n  beta"
    assert _canonicalize_whitespace_only_support(content=content, proposed="alpha beta!") == "alpha beta!"
