"""Phase 4 共用的可信身份、文档授权与数据出站策略。

这个文件刻意提供一个小而深的接口：业务代码只提交已解析的 caller、文档 metadata 或
出站 payload 描述，模块内部统一完成 closed-world 校验、默认拒绝和安全投影。它不读取
HTTP token/cookie，也不负责未来的 JWT/OAuth；因此请求体自报角色永远不会在这里被“顺手”
升级成可信身份。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Literal

from engine.rag.catalog import CatalogEntry, KNOWN_PURPOSES, KNOWN_ROLES

TrustLevel = Literal[
    "production_authenticated",
    "demo_fixture",
    "test_fixture",
    "unverified_request_claim",
]
AuthorizationPhase = Literal["pre_selection", "pre_generation"]

TRUSTED_DOCUMENT_LEVELS = frozenset(
    {"production_authenticated", "demo_fixture", "test_fixture"}
)
DOCUMENT_AUTHORIZATION_POLICY_IDENTITY = "document-authorization-v1"
OUTBOUND_POLICY_IDENTITY = "phase4-outbound-v1"


class GovernanceError(ValueError):
    """治理输入本身非法；正常 allow/deny 使用 decision，而不是异常控制流。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _safe_ref(namespace: str, *parts: str) -> str:
    """生成不可逆审计引用，避免拒绝路径暴露 caller 或 document 主键。"""

    payload = "\0".join((namespace, *parts)).encode("utf-8")
    return f"{namespace}:{sha256(payload).hexdigest()[:20]}"


def document_safe_ref(entry: CatalogEntry) -> str:
    """返回 Authorization/Evidence 共用的不可逆 document revision 引用。"""

    return _safe_ref("document", entry.document_key, entry.revision, entry.content_identity, entry.anchor)


def _validated_roles(roles: Iterable[str]) -> frozenset[str]:
    """规范化角色集合并拒绝未知枚举。"""

    normalized = frozenset(str(role).strip() for role in roles if str(role).strip())
    unknown = normalized - KNOWN_ROLES
    if unknown:
        raise GovernanceError("invalid_role", f"包含未知角色: {sorted(unknown)}")
    return normalized


@dataclass(frozen=True)
class TrustedCaller:
    """业务模块可消费的最小 caller 事实，不携带原始认证凭据。"""

    caller_id: str
    resolved_roles: frozenset[str]
    trust_level: TrustLevel
    identity_source: str
    audit_ref: str
    tenant_id: str | None = None
    thread_owner_ref: str | None = None

    @property
    def may_authorize_documents(self) -> bool:
        return self.trust_level in TRUSTED_DOCUMENT_LEVELS


def _caller(
    *,
    caller_id: str,
    roles: Iterable[str],
    trust_level: TrustLevel,
    identity_source: str,
    tenant_id: str | None = None,
    thread_owner_ref: str | None = None,
) -> TrustedCaller:
    """所有 caller adapter 共用的 closed-world 构造器。"""

    caller_id = caller_id.strip()
    identity_source = identity_source.strip()
    if not caller_id or not identity_source:
        raise GovernanceError("caller_identity_missing", "caller_id 与 identity_source 不能为空")
    resolved_roles = _validated_roles(roles)
    if trust_level != "unverified_request_claim" and not resolved_roles:
        raise GovernanceError("caller_role_missing", "可信 caller 至少需要一个已解析角色")
    return TrustedCaller(
        caller_id=caller_id,
        resolved_roles=resolved_roles,
        trust_level=trust_level,
        identity_source=identity_source,
        audit_ref=_safe_ref("caller", trust_level, identity_source, caller_id),
        tenant_id=tenant_id.strip() if tenant_id else None,
        thread_owner_ref=thread_owner_ref.strip() if thread_owner_ref else None,
    )


def authenticated_caller(
    *, caller_id: str, roles: Iterable[str], identity_source: str, tenant_id: str | None = None
) -> TrustedCaller:
    """生产认证完成后的适配 seam；M31 不实现认证 provider 本身。"""

    return _caller(
        caller_id=caller_id,
        roles=roles,
        trust_level="production_authenticated",
        identity_source=identity_source,
        tenant_id=tenant_id,
    )


def demo_caller(
    *, caller_id: str, roles: Iterable[str], tenant_id: str | None = None
) -> TrustedCaller:
    """仅供明确 demo 入口使用，不能伪装成生产认证身份。"""

    return _caller(
        caller_id=caller_id,
        roles=roles,
        trust_level="demo_fixture",
        identity_source="demo_fixture",
        tenant_id=tenant_id,
    )


def test_caller(
    *, caller_id: str, roles: Iterable[str], tenant_id: str | None = None
) -> TrustedCaller:
    """确定性测试 fixture；生产入口不得调用。"""

    return _caller(
        caller_id=caller_id,
        roles=roles,
        trust_level="test_fixture",
        identity_source="test_fixture",
        tenant_id=tenant_id,
    )


def unverified_request_caller(*, caller_id: str, claimed_roles: Iterable[str]) -> TrustedCaller:
    """记录客户端声明但清空授权角色，防止把 ``user_role=admin`` 当认证结果。"""

    _validated_roles(claimed_roles)  # 非法声明仍应尽早显式失败，而不是宽松修复。
    return _caller(
        caller_id=caller_id,
        roles=(),
        trust_level="unverified_request_claim",
        identity_source="request_body_claim",
    )


@dataclass(frozen=True)
class AuthorizationDecision:
    """完整内部裁决；对外只能使用 ``public_projection``。"""

    allowed: bool
    reason_code: str
    phase: AuthorizationPhase
    policy_identity: str
    caller_safe_ref: str
    evidence_safe_ref: str
    allowed_purpose: str | None

    def public_projection(self) -> dict[str, Any]:
        """拒绝统一收敛，不能泄露文档存在性、标题、revision 或具体 ACL。"""

        return {
            "allowed": self.allowed,
            "reason_code": "authorized" if self.allowed else "not_authorized",
            "policy_identity": self.policy_identity,
            "caller_ref": self.caller_safe_ref,
        }


@dataclass(frozen=True)
class DocumentAuthorizationPolicy:
    """文档 trust/revision/purpose/role 的唯一确定性裁决器。"""

    identity: str = DOCUMENT_AUTHORIZATION_POLICY_IDENTITY

    def authorize(
        self,
        *,
        caller: TrustedCaller,
        entry: CatalogEntry,
        purpose: str,
        phase: AuthorizationPhase,
    ) -> AuthorizationDecision:
        """按 trust → revision → purpose → ACL 的固定顺序裁决，所有失败都关闭。"""

        if phase not in {"pre_selection", "pre_generation"}:
            raise GovernanceError("authorization_phase_invalid", f"未知授权阶段: {phase}")
        if purpose not in KNOWN_PURPOSES:
            reason = "purpose_unknown"
        elif not caller.may_authorize_documents:
            reason = "caller_untrusted"
        elif entry.status != "active":
            reason = "revision_unavailable"
        elif purpose not in entry.purposes:
            reason = "purpose_not_allowed"
        elif not entry.public and not (caller.resolved_roles & entry.allowed_roles):
            reason = "role_not_allowed"
        else:
            reason = "authorized"
        return AuthorizationDecision(
            allowed=reason == "authorized",
            reason_code=reason,
            phase=phase,
            policy_identity=self.identity,
            caller_safe_ref=caller.audit_ref,
            evidence_safe_ref=document_safe_ref(entry),
            allowed_purpose=purpose if reason == "authorized" else None,
        )


def authorize_document(
    *,
    caller: TrustedCaller,
    entry: CatalogEntry,
    purpose: str,
    phase: AuthorizationPhase,
    policy: DocumentAuthorizationPolicy | None = DocumentAuthorizationPolicy(),
) -> AuthorizationDecision:
    """统一入口；策略缺失返回 deny，不能由调用方自行补一个 allow。"""

    if policy is None:
        return AuthorizationDecision(
            allowed=False,
            reason_code="policy_missing",
            phase=phase,
            policy_identity="missing",
            caller_safe_ref=caller.audit_ref,
            evidence_safe_ref=_safe_ref("document", "undisclosed"),
            allowed_purpose=None,
        )
    return policy.authorize(caller=caller, entry=entry, purpose=purpose, phase=phase)


@dataclass(frozen=True)
class OutboundRequest:
    """远程调用前由调用点声明的最小数据出站事实。"""

    receiver: str
    node_purpose: str
    data_class: str
    fields: frozenset[str]
    fallback_available: bool
    caller_safe_ref: str | None = None
    evidence_safe_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutboundDecision:
    """出站 allow/deny、字段与保守 fallback 的结构化结果。"""

    allowed: bool
    reason_code: str
    policy_identity: str
    receiver: str
    node_purpose: str
    data_class: str
    allowed_fields: tuple[str, ...]
    fallback_action: Literal["continue_locally", "stop"]

    def public_projection(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "policy_identity": self.policy_identity,
            "fallback_action": self.fallback_action,
        }


@dataclass(frozen=True)
class OutboundRule:
    """一个精确 receiver/purpose/data-class 白名单键。"""

    receiver: str
    node_purpose: str
    data_class: str
    allowed_fields: frozenset[str]


class OutboundPolicy:
    """精确键匹配的出站白名单；没有通配符，也不按 provider 继承用途。"""

    def __init__(
        self,
        *,
        identity: str = OUTBOUND_POLICY_IDENTITY,
        rules: Iterable[OutboundRule] = (),
    ) -> None:
        if not identity.strip():
            raise GovernanceError("outbound_policy_invalid", "policy identity 不能为空")
        indexed: dict[tuple[str, str, str], OutboundRule] = {}
        for rule in rules:
            key = (rule.receiver, rule.node_purpose, rule.data_class)
            if key in indexed:
                raise GovernanceError("outbound_policy_duplicate", f"重复出站规则: {key}")
            indexed[key] = rule
        self.identity = identity
        self._rules = indexed

    def decide(self, request: OutboundRequest) -> OutboundDecision:
        key = (request.receiver, request.node_purpose, request.data_class)
        rule = self._rules.get(key)
        if rule is None:
            reason = "policy_missing"
            allowed_fields: tuple[str, ...] = ()
        elif not request.fields <= rule.allowed_fields:
            reason = "fields_not_allowed"
            allowed_fields = tuple(sorted(rule.allowed_fields))
        else:
            reason = "outbound_allowed"
            allowed_fields = tuple(sorted(request.fields))
        allowed = reason == "outbound_allowed"
        return OutboundDecision(
            allowed=allowed,
            reason_code=reason,
            policy_identity=self.identity,
            receiver=request.receiver,
            node_purpose=request.node_purpose,
            data_class=request.data_class,
            allowed_fields=allowed_fields,
            fallback_action="continue_locally" if (not allowed and request.fallback_available) else "stop",
        )


TEXT2SQL_CHAT_FIELDS = frozenset({"prompt", "system_prompt", "model"})
SCHEMA_EMBEDDING_FIELDS = frozenset({"texts", "model", "dimensions"})
DEFAULT_OUTBOUND_POLICY = OutboundPolicy(
    rules=(
        # ★ 只登记现有 Text2SQL 数据类别；同一 receiver 的 Document Evidence 仍因缺规则而拒绝。
        OutboundRule("qwen_chat", "query_plan", "text2sql_prompt", TEXT2SQL_CHAT_FIELDS),
        OutboundRule("qwen_chat", "sql_generation", "text2sql_prompt", TEXT2SQL_CHAT_FIELDS),
        OutboundRule("qwen_chat", "sql_repair", "text2sql_prompt", TEXT2SQL_CHAT_FIELDS),
        OutboundRule("deepseek_chat", "query_plan", "text2sql_prompt", TEXT2SQL_CHAT_FIELDS),
        OutboundRule("deepseek_chat", "sql_generation", "text2sql_prompt", TEXT2SQL_CHAT_FIELDS),
        OutboundRule("deepseek_chat", "sql_repair", "text2sql_prompt", TEXT2SQL_CHAT_FIELDS),
        OutboundRule("dashscope_embedding", "schema_embedding", "schema_text", SCHEMA_EMBEDDING_FIELDS),
        OutboundRule("siliconflow_embedding", "schema_embedding", "schema_text", SCHEMA_EMBEDDING_FIELDS),
    )
)


def decide_outbound(
    request: OutboundRequest, *, policy: OutboundPolicy | None = DEFAULT_OUTBOUND_POLICY
) -> OutboundDecision:
    """集中裁决入口；显式传入 ``None`` 用于验证 policy missing 失败关闭。"""

    if policy is None:
        return OutboundDecision(
            allowed=False,
            reason_code="policy_missing",
            policy_identity="missing",
            receiver=request.receiver,
            node_purpose=request.node_purpose,
            data_class=request.data_class,
            allowed_fields=(),
            fallback_action="continue_locally" if request.fallback_available else "stop",
        )
    return policy.decide(request)


def require_outbound(
    request: OutboundRequest,
    *,
    policy: OutboundPolicy | None = DEFAULT_OUTBOUND_POLICY,
) -> OutboundDecision:
    """远程 transport 的强制门；调用方可显式注入独立用途策略，默认合同不变。"""

    decision = decide_outbound(request, policy=policy)
    if not decision.allowed:
        raise GovernanceError("outbound_denied", decision.reason_code)
    return decision
