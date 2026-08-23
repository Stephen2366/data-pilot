"""M42-C 最小双角色 caller adapter。

现有 ``FixtureCallerResolver`` 继续服务 legacy local/demo/test 并拥有全部已知角色；本 adapter
只给 Phase 4B rehearsal 使用，避免为了演示 SQL+政策跨 turn 而修改默认 caller 或放宽文档 ACL。
"""

from __future__ import annotations

from engine.governance import demo_caller, test_caller
from engine.harness.caller import CallerResolution
from engine.phase4b.contracts import B0ContractBundle, load_b0_contract_bundle


class Phase4BFixtureCallerResolver:
    """只解析已冻结的 ``ops`` active role，并返回 ``ops + customer_service`` caller。"""

    def __init__(self, *, fixture_kind: str = "demo", bundle: B0ContractBundle | None = None) -> None:
        if fixture_kind not in {"demo", "test"}:
            raise ValueError("fixture_kind 只能是 demo 或 test")
        self._fixture_kind = fixture_kind
        self._bundle = bundle or load_b0_contract_bundle()

    def resolve(self, requested_role: str) -> CallerResolution | None:
        """请求只能选择冻结 active role；不能借请求体临时增删 resolved roles。"""

        fixture = self._bundle.payload["caller_fixture"]
        role = requested_role.strip()
        if role != fixture["active_sql_role"]:
            return None
        factory = demo_caller if self._fixture_kind == "demo" else test_caller
        caller = factory(
            caller_id=f"{self._fixture_kind}-phase4b-fixture",
            roles=fixture["resolved_roles"],
            tenant_id=fixture["tenant_id"],
        )
        return CallerResolution(caller=caller, active_sql_role=role)
