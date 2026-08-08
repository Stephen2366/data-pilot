"""M27 selector loader：选择 canonical scenario，不再复制或拼接旧 YAML 题面。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from eval.catalog import CatalogError, select_scenarios
from eval.contracts import Catalog, ExecutionProtocol
from eval.projectors import GateEffect, SuitePolicy


@dataclass(frozen=True)
class Selector:
    """可复用的场景选择和明确执行协议。"""

    selector_id: str
    scenario_ids: tuple[str, ...]
    execution_protocol: ExecutionProtocol
    policy: SuitePolicy


def load_selector(path: Path, catalog: Catalog) -> Selector:
    """严格加载 selector，并在任何 pipeline 调用前解析悬空 scenario。"""

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    selector_id = _text(raw, "selector_id")
    scenario_ids = _text_list(raw, "scenario_ids", required=True)
    selected = select_scenarios(catalog, scenario_ids)
    protocol_raw = raw.get("execution_protocol") or {}
    if not isinstance(protocol_raw, dict):
        raise CatalogError(f"selector {selector_id}: execution_protocol must be a mapping")
    try:
        protocol = ExecutionProtocol(
            pipeline_mode=str(protocol_raw.get("pipeline_mode", "new_text2sql")),  # type: ignore[arg-type]
            schema_fusion_strategy=str(protocol_raw.get("schema_fusion_strategy", "weighted")),  # type: ignore[arg-type]
            replicate_count=int(protocol_raw.get("replicate_count", 1)),
        )
    except (TypeError, ValueError) as exc:
        raise CatalogError(f"selector {selector_id}: invalid execution_protocol") from exc
    if protocol.replicate_count < 1:
        raise CatalogError(f"selector {selector_id}: replicate_count must be positive")
    policy_raw = raw.get("gate_policy") or {}
    if not isinstance(policy_raw, dict):
        raise CatalogError(f"selector {selector_id}: gate_policy must be a mapping")
    effects = {str(key): _effect(value, selector_id) for key, value in dict(policy_raw.get("effects_by_classification") or {}).items()}
    overrides = {str(key): _effect(value, selector_id) for key, value in dict(policy_raw.get("assertion_overrides") or {}).items()}
    valid_assertions = {f"{scenario.scenario_id}.{assertion.assertion_id}" for scenario in selected for assertion in scenario.assertions}
    unknown = sorted(set(overrides) - valid_assertions)
    if unknown:
        raise CatalogError(f"selector {selector_id}: assertion override not found: {unknown}")
    policy = SuitePolicy(
        suite_id=selector_id,
        selected_scenario_ids=scenario_ids,
        effects_by_classification=effects,
        assertion_overrides=overrides,
        scenario_classifications={scenario.scenario_id: scenario.classification for scenario in selected},
    )
    return Selector(selector_id, scenario_ids, protocol, policy)


def policy_for_classification(catalog: Catalog, *, suite_id: str, classification: str, gate_effect: GateEffect) -> SuitePolicy:
    """选择一个 Suite classification；用于 Core/Stress/Mannual Lab 全量确定性运行。"""

    selected = tuple(item for item in catalog.scenarios if item.classification == classification)
    if not selected:
        raise CatalogError(f"no scenarios with classification={classification}")
    return SuitePolicy(
        suite_id=suite_id,
        selected_scenario_ids=tuple(item.scenario_id for item in selected),
        effects_by_classification={classification: gate_effect},
        assertion_overrides={},
        scenario_classifications={item.scenario_id: item.classification for item in selected},
    )


def _effect(value: object, selector_id: str) -> GateEffect:
    """把 YAML 字符串收紧为 gate effect 枚举。"""
    if value not in {"required", "advisory", "excluded"}:
        raise CatalogError(f"selector {selector_id}: invalid gate effect={value!r}")
    return value  # type: ignore[return-value]


def _text(source: dict[str, object], key: str) -> str:
    """读取 selector 必填文本字段。"""
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"selector missing non-empty {key}")
    return value.strip()


def _text_list(source: dict[str, object], key: str, *, required: bool = False) -> tuple[str, ...]:
    """读取并去重 selector 的 canonical scenario id 列表。"""
    value = source.get(key)
    if value is None and not required:
        return ()
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise CatalogError(f"selector {key} must be a non-empty string list")
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        raise CatalogError(f"selector {key} contains duplicate scenario ids")
    return result
