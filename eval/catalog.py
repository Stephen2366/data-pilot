"""M27 canonical catalog 的严格 loader 与内容 hash。

这里是 Scenario 合同的唯一入口：YAML 只是便于人工维护的源文件，加载后得到的 typed contract
才会交给 Evaluator。未知 assertion、重复 ID、悬空 selector 等错误必须在网络/LLM 调用前失败。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from eval.contracts import (
    CONTRACT_VERSION,
    AssertionContract,
    Catalog,
    ExpectedRejectionSpec,
    JoinPathSpec,
    MetricMappingSpec,
    OutputContractSpec,
    QueryPlanSpec,
    ResultMatchSpec,
    ScenarioContract,
    SchemaContextSpec,
    TraceCompleteSpec,
)


class CatalogError(ValueError):
    """合同不合法时的明确报错；调用者无需猜测是 YAML 还是 scorer 问题。"""


_SPEC_BY_KIND = {
    "result_match": ResultMatchSpec,
    "output_contract": OutputContractSpec,
    "schema_context": SchemaContextSpec,
    "query_plan": QueryPlanSpec,
    "trace_complete": TraceCompleteSpec,
    "safety_block": type(None),
    "expected_rejection": ExpectedRejectionSpec,
    "join_path": JoinPathSpec,
    "metric_mapping": MetricMappingSpec,
}


def load_catalog(path: Path) -> Catalog:
    """加载 canonical Scenario YAML，并在 IO 后立刻完成类型/ID/合同校验。"""

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("contract_version") != CONTRACT_VERSION:
        raise CatalogError(f"contract_version must be {CONTRACT_VERSION}: {path}")
    raw_scenarios = raw.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise CatalogError("catalog.scenarios must be a non-empty list")
    scenarios = tuple(_parse_scenario(item) for item in raw_scenarios)
    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    _assert_unique("scenario_id", scenario_ids)
    normalized = _normalize_catalog(scenarios)
    return Catalog(contract_version=CONTRACT_VERSION, scenarios=scenarios, catalog_hash=_hash(normalized))


def select_scenarios(catalog: Catalog, scenario_ids: tuple[str, ...]) -> tuple[ScenarioContract, ...]:
    """按显式 ID 选择本轮场景，拒绝重复和悬空引用。"""

    _assert_unique("selected scenario_id", list(scenario_ids))
    by_id = {scenario.scenario_id: scenario for scenario in catalog.scenarios}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in by_id]
    if missing:
        raise CatalogError(f"selected scenarios not found: {missing}")
    return tuple(by_id[scenario_id] for scenario_id in scenario_ids)


def selected_contract_hash(scenarios: tuple[ScenarioContract, ...]) -> str:
    """只 hash 本轮场景及其 typed assertions；未选题修改不污染本轮合同身份。"""

    return _hash(_normalize_catalog(scenarios))


def suite_policy_hash(*, scenario_ids: tuple[str, ...], classifications: dict[str, str], gate_policy: dict[str, str]) -> str:
    """M27A 先冻结 policy identity；真实 gate projector 留给已确认后的 M27B。"""

    return _hash({"scenario_ids": sorted(scenario_ids), "classifications": classifications, "gate_policy": gate_policy})


def run_spec_hash(*, selected_hash: str, policy_hash: str, protocol: dict[str, Any], oracle_fixture_identity: str, constraints: dict[str, Any]) -> str:
    """为一次可复现运行编码其选择、协议、oracle 与显式运行约束。"""

    return _hash(
        {
            "selected_contract_hash": selected_hash,
            "suite_policy_hash": policy_hash,
            "execution_protocol": protocol,
            "oracle_fixture_identity": oracle_fixture_identity,
            "requested_runtime_constraints": constraints,
        }
    )


def _parse_scenario(item: Any) -> ScenarioContract:
    """把 YAML mapping 收紧为不携带旧 runner 字段的 ScenarioContract。"""
    if not isinstance(item, dict):
        raise CatalogError("scenario must be a mapping")
    scenario_id = _required_text(item, "id")
    classification = str(item.get("classification") or "")
    if classification not in {"core", "stress", "manual_lab"}:
        raise CatalogError(f"scenario {scenario_id}: invalid classification={classification!r}")
    raw_assertions = item.get("assertions")
    if not isinstance(raw_assertions, list) or not raw_assertions:
        raise CatalogError(f"scenario {scenario_id}: assertions must be a non-empty list")
    assertions = tuple(_parse_assertion(scenario_id, raw) for raw in raw_assertions)
    _assert_unique(f"assertion_id in {scenario_id}", [assertion.assertion_id for assertion in assertions])
    return ScenarioContract(
        scenario_id=scenario_id,
        question=_required_text(item, "question"),
        user_role=str(item.get("user_role") or "ops"),
        classification=classification,  # type: ignore[arg-type]
        tags=tuple(str(value) for value in item.get("tags") or []),
        assertions=assertions,
        authority_refs=tuple(str(value) for value in item.get("authority_refs") or []),
    )


def _parse_assertion(scenario_id: str, item: Any) -> AssertionContract:
    """验证 kind 后委派专属 spec parser，禁止延迟解释大字典。"""
    if not isinstance(item, dict):
        raise CatalogError(f"scenario {scenario_id}: assertion must be a mapping")
    assertion_id = _required_text(item, "id")
    kind = _required_text(item, "kind")
    if kind not in _SPEC_BY_KIND:
        raise CatalogError(f"scenario {scenario_id} assertion {assertion_id}: unknown kind={kind}")
    spec = _parse_spec(kind, item.get("spec"), scenario_id=scenario_id, assertion_id=assertion_id)
    return AssertionContract(
        assertion_id=assertion_id,
        kind=kind,
        spec=spec,
        authority_refs=tuple(str(value) for value in item.get("authority_refs") or []),
    )


def _parse_spec(kind: str, raw: Any, *, scenario_id: str, assertion_id: str) -> Any:
    """按 kind 解析唯一合法的 typed spec，并给出可定位的合同错误。"""
    if kind == "safety_block":
        if raw not in (None, {}):
            raise CatalogError(f"scenario {scenario_id} assertion {assertion_id}: safety_block has no spec")
        return None
    if not isinstance(raw, dict):
        raise CatalogError(f"scenario {scenario_id} assertion {assertion_id}: {kind}.spec must be a mapping")
    if kind == "result_match":
        sql = _required_text(raw, "reference_sql")
        return ResultMatchSpec(
            reference_sql=_normalize_sql(sql),
            columns=_tuple_text(raw, "columns", required=True),
            tolerance=float(raw.get("tolerance", 0.000001)),
            column_aliases=_aliases(raw.get("column_aliases") or {}),
            order_insensitive=bool(raw.get("order_insensitive", False)),
        )
    if kind == "output_contract":
        return OutputContractSpec(columns=_tuple_text(raw, "columns", required=True), column_aliases=_aliases(raw.get("column_aliases") or {}))
    if kind == "schema_context":
        alternatives = []
        for alternative in raw.get("alternatives") or []:
            if not isinstance(alternative, dict):
                raise CatalogError(f"scenario {scenario_id} assertion {assertion_id}: alternative must be a mapping")
            alternatives.append({key: _tuple_text(alternative, key) for key in ("tables", "columns", "metrics", "join_keys")})
        return SchemaContextSpec(
            alternatives=tuple(alternatives),
            required_tables=_tuple_text(raw, "required_tables"),
            required_columns=_tuple_text(raw, "required_columns"),
            required_metrics=_tuple_text(raw, "required_metrics"),
            required_join_keys=_tuple_text(raw, "required_join_keys"),
        )
    if kind == "query_plan":
        return QueryPlanSpec(**{key: _tuple_text(raw, key) for key in ("tables", "joins", "metrics", "group_by", "order_by", "output_columns")})
    if kind == "trace_complete":
        steps = raw.get("required_steps")
        if not isinstance(steps, list) or not steps:
            raise CatalogError(f"scenario {scenario_id} assertion {assertion_id}: trace required_steps must be non-empty")
        normalized_steps: list[tuple[str, str]] = []
        for step in steps:
            if not isinstance(step, dict) or not step.get("type") or not step.get("status"):
                raise CatalogError(f"scenario {scenario_id} assertion {assertion_id}: invalid trace step")
            normalized_steps.append((str(step["type"]), str(step["status"])))
        return TraceCompleteSpec(tuple(normalized_steps), _tuple_text(raw, "allow_skipped"))
    if kind == "expected_rejection":
        return ExpectedRejectionSpec(issue_tags=_tuple_text(raw, "issue_tags", required=True), blocked_via=_required_text(raw, "blocked_via"))
    if kind == "join_path":
        return JoinPathSpec(relation_ids=_tuple_text(raw, "relation_ids", required=True))
    if kind == "metric_mapping":
        return MetricMappingSpec(tables=_tuple_text(raw, "tables", required=True), columns=_tuple_text(raw, "columns", required=True), metrics=_tuple_text(raw, "metrics"))
    raise AssertionError(f"registered assertion kind missing parser: {kind}")


def _normalize_catalog(scenarios: tuple[ScenarioContract, ...]) -> dict[str, Any]:
    """使用稳定 ID 排序；只对 SQL 做保守空白归一，绝不 AST 改写 SQL。"""

    def assertion_payload(assertion: AssertionContract) -> dict[str, Any]:
        """生成稳定的断言 hash 表示，排除文件路径等非语义信息。"""
        spec = assertion.spec
        data = vars(spec) if spec is not None else {}
        return {
            "id": assertion.assertion_id,
            "kind": assertion.kind,
            "spec": _canonicalize(data),
            "authority_refs": sorted(assertion.authority_refs),
        }

    return {
        "contract_version": CONTRACT_VERSION,
        "scenarios": [
            {
                "id": scenario.scenario_id,
                "question": scenario.question.strip(),
                "user_role": scenario.user_role,
                "classification": scenario.classification,
                "tags": sorted(scenario.tags),
                "authority_refs": sorted(scenario.authority_refs),
                "assertions": [assertion_payload(item) for item in sorted(scenario.assertions, key=lambda value: value.assertion_id)],
            }
            for scenario in sorted(scenarios, key=lambda value: value.scenario_id)
        ],
    }


def _canonicalize(value: Any) -> Any:
    """递归稳定 mapping key；SQL 只做安全的空白归一。"""
    if isinstance(value, str):
        return _normalize_sql(value) if "\n" in value or value.lstrip().upper().startswith(("SELECT", "WITH")) else value
    if isinstance(value, dict):
        return {str(key): _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        # 只有 trace required_steps 的顺序有语义；它已编码为 tuple of pairs，保持顺序。
        return [_canonicalize(item) for item in value]
    return value


def _hash(value: Any) -> str:
    """为已规范化内容生成 UTF-8 SHA-256 identity。"""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _normalize_sql(value: str) -> str:
    """只消除无意义空白，不做可能改变 dialect 的 AST 重写。"""
    return re.sub(r"\s+", " ", value.strip())


def _required_text(source: dict[str, Any], key: str) -> str:
    """读取必填非空文本字段，防止缺值静默进入 runtime。"""
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"missing non-empty {key}")
    return value.strip()


def _tuple_text(source: dict[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    """把 YAML 标量列表规范化为不可变字符串 tuple。"""
    value = source.get(key)
    if value is None:
        if required:
            raise CatalogError(f"missing {key}")
        return ()
    if not isinstance(value, list) or any(not isinstance(item, (str, int, float)) for item in value):
        raise CatalogError(f"{key} must be a list of scalar values")
    return tuple(str(item) for item in value)


def _aliases(value: Any) -> dict[str, tuple[str, ...]]:
    """校验 canonical column 到候选别名的显式映射。"""
    if not isinstance(value, dict):
        raise CatalogError("column_aliases must be a mapping")
    if any(not isinstance(aliases, list) for aliases in value.values()):
        raise CatalogError("each column_aliases value must be a list")
    return {str(key): tuple(str(alias) for alias in aliases) for key, aliases in value.items()}


def _assert_unique(label: str, values: list[str]) -> None:
    """对稳定 ID 执行早失败的重复检查。"""
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise CatalogError(f"duplicate {label}: {duplicates}")
