"""M46-D0：external requirement formation 使用的独立 Qwen transport policy。

本模块只拥有 receiver/purpose/data class 与真实 transport factory。prompt、schema、source-span
validator 和 coverage 全部封装在 ``external_requirement_formation`` deep module 内，避免调用方
重新拼装一个浅 proposal pipeline。
"""

from __future__ import annotations

from typing import Protocol

from engine.governance import OutboundPolicy, OutboundRule
from engine.nl2sql.generator import QwenChatClient

B4_PROPOSAL_OUTBOUND_IDENTITY = "phase4b-b4-recovery-requirement-proposal-outbound-v1"
B4_PROPOSAL_DATA_CLASS = "public_benchmark_question_with_authorized_evidence"
B4_PROPOSAL_PURPOSE = "rag_recovery_requirement_proposal"
B4_PROPOSAL_OUTBOUND_POLICY = OutboundPolicy(
    identity=B4_PROPOSAL_OUTBOUND_IDENTITY,
    rules=(
        OutboundRule(
            "qwen_chat", B4_PROPOSAL_PURPOSE, B4_PROPOSAL_DATA_CLASS,
            frozenset({"prompt", "system_prompt", "model"}),
        ),
    ),
)


class B4ProposalTransport(Protocol):
    """真实 Qwen 与测试 fake 共同满足的最小 transport。"""

    model: str
    request_count: int
    total_tokens: int

    def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str) -> str: ...


def make_b4_qwen_requirement_proposal_client(
    *, api_key: str, base_url: str, model: str = "qwen3.7-plus", timeout: float = 120.0,
) -> QwenChatClient:
    """创建 B4 专属 client；不会沿用 M45 diagnostic outbound policy。"""

    return QwenChatClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        max_retries=0,
        outbound_policy=B4_PROPOSAL_OUTBOUND_POLICY,
        outbound_data_class=B4_PROPOSAL_DATA_CLASS,
        enable_thinking=False,
        max_tokens=1200,
    )
