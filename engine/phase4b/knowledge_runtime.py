"""M44-A：Agent task 专用的可信 Knowledge Runtime Resolver。

普通非 task API 仍直接消费 M44A Enterprise factory；只有服务端 typed requirement 能跨过
本 seam。自然语言、请求字段、backend/collection 名都不是 resolver 输入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from engine.governance import TrustedCaller
from engine.harness.adapters import RAGTool
from engine.phase4b.loop_contracts import EvidenceRequirement


class KnowledgeRuntimeResolutionError(ValueError):
    """未知 scope、未加载 adapter 或 caller 不可信时失败关闭。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class KnowledgeRuntimeSpec:
    """registry 中的一项可信 adapter factory 与安全身份。"""

    scope: str
    factory: Callable[[], RAGTool]
    runtime_identity: str

    def __post_init__(self) -> None:
        if self.scope not in {"business_release", "external_profile"} or not self.runtime_identity.strip():
            raise ValueError("knowledge_runtime_spec_invalid")


@dataclass(frozen=True)
class ResolvedKnowledgeRuntime:
    """Controller 可执行的 adapter；公开层只投影 identity，不序列化 factory。"""

    scope: str
    adapter: RAGTool
    runtime_identity: str

    def safe_projection(self) -> dict[str, str]:
        return {"scope": self.scope, "runtime_identity": self.runtime_identity}


class KnowledgeRuntimeResolver:
    """closed-world registry：选择逻辑只依赖 requirement.runtime_scope。"""

    identity = "phase4b-knowledge-runtime-resolver-v1"

    def __init__(self, specs: tuple[KnowledgeRuntimeSpec, ...]) -> None:
        indexed: Mapping[str, KnowledgeRuntimeSpec] = {item.scope: item for item in specs}
        if len(indexed) != len(specs) or not set(indexed) <= {"business_release", "external_profile"}:
            raise ValueError("knowledge_runtime_registry_invalid")
        self._specs = dict(indexed)

    def resolve(
        self,
        *,
        requirement: EvidenceRequirement,
        caller: TrustedCaller | None,
    ) -> ResolvedKnowledgeRuntime:
        """解析唯一 adapter；绝不 fallback 到另一 corpus。"""

        if caller is None:
            raise KnowledgeRuntimeResolutionError("caller_untrusted")
        if requirement.kind != "document" or requirement.runtime_scope == "not_applicable":
            raise KnowledgeRuntimeResolutionError("knowledge_requirement_scope_invalid")
        spec = self._specs.get(requirement.runtime_scope)
        if spec is None:
            raise KnowledgeRuntimeResolutionError("knowledge_runtime_unavailable")
        try:
            adapter = spec.factory()
        except Exception as exc:  # noqa: BLE001 - factory 失败不能触发另一 runtime fallback
            raise KnowledgeRuntimeResolutionError("knowledge_runtime_unavailable") from exc
        if adapter is None or not callable(getattr(adapter, "run_for_hybrid", None)):
            raise KnowledgeRuntimeResolutionError("knowledge_runtime_unavailable")
        return ResolvedKnowledgeRuntime(spec.scope, adapter, spec.runtime_identity)

    def safe_projection(self) -> dict[str, object]:
        return {"identity": self.identity, "registered_scopes": sorted(self._specs)}
