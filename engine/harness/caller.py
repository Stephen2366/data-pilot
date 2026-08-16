"""M35 caller resolver seam：把 HTTP role 选择与可信 caller 事实分开。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from engine.governance import TrustedCaller, demo_caller, test_caller
from engine.rag.catalog import KNOWN_ROLES


@dataclass(frozen=True)
class CallerResolution:
    """解析后 caller 和明确 active SQL role；两者必须来自同一 resolver。"""

    caller: TrustedCaller
    active_sql_role: str

    def __post_init__(self) -> None:
        if self.active_sql_role not in self.caller.resolved_roles:
            raise ValueError("active SQL role 必须属于 resolver 已解析 roles")


class CallerResolver(Protocol):
    """应用组装层的身份 seam；Harness 不读取 HTTP token 或请求体元数据。"""

    def resolve(self, requested_role: str) -> CallerResolution | None:
        """解析请求选择的 fixture/authenticated identity；无法确认时返回 None。"""


class FixtureCallerResolver:
    """明确 local/demo/test 运行模式的 fixture resolver。

    resolver 先给出一个固定、明确标记的本地 fixture identity 及其 role 集；请求体只能从该集
    合选择 active role，不能通过“请求什么 role 就临时造什么 caller”完成自我授权。未知 role
    一律没有可信 caller。
    """

    def __init__(self, *, fixture_kind: str = "demo") -> None:
        if fixture_kind not in {"demo", "test"}:
            raise ValueError("fixture_kind 只能是 demo 或 test")
        self._fixture_kind = fixture_kind

    def resolve(self, requested_role: str) -> CallerResolution | None:
        """先验证请求 role 在固定 fixture role 集内，再返回同一可信 caller。"""

        role = requested_role.strip()
        if role not in KNOWN_ROLES:
            return None
        factory = demo_caller if self._fixture_kind == "demo" else test_caller
        caller = factory(caller_id=f"{self._fixture_kind}-local-fixture", roles=KNOWN_ROLES)
        return CallerResolution(caller=caller, active_sql_role=role)


def build_default_caller_resolver(app_env: str) -> CallerResolver | None:
    """按 G-M35-1 仅在明确本地 fixture 环境自动注入 resolver。"""

    normalized = app_env.strip().lower()
    if normalized in {"local", "demo"}:
        return FixtureCallerResolver(fixture_kind="demo")
    if normalized == "test":
        return FixtureCallerResolver(fixture_kind="test")
    return None
