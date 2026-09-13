"""M27 零模型运行计划：在创建 RunEnvironment 前冻结 canonical identity。

★ 这里复用 catalog 与 runtime identity 的唯一实现；只构建 deterministic in-memory schema
index 来取得同源指纹，不创建 RunEnvironment，也不接触 checkpoint、artifact、Trace 或 provider。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from eval.catalog import load_catalog, run_spec_hash, select_scenarios, selected_contract_hash, suite_policy_hash
from app.core.config import get_settings
from eval.contracts import CONTRACT_VERSION, EvalRunSpec, ExecutionProtocol
from eval.environment import _close_vector_index, _resolved_runtime_values
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.retriever import build_configured_schema_vector_index

PLAN_SCHEMA_VERSION = "m27-run-plan-v1"


def build_explicit_run_plan(
    *,
    catalog_path: Path,
    scenario_ids: tuple[str, ...],
    pipeline_mode: str,
    schema_fusion_strategy: str,
    replicate_count: int,
    oracle_fixture_identity: str = "sqlite_deterministic_seed",
    requested_runtime_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """★ 按 `run_eval --scenario` 的同一 policy 生成稳定机器计划。

    关键不是复制一套 hash 算法，而是直接调用运行期已有的 catalog/runtime 函数；这样
    plan 与实际 artifact 若漂移，说明环境真的变了，而不是两个实现各自算出“正确答案”。
    """

    if pipeline_mode not in {"baseline", "new_text2sql"}:
        raise ValueError("unsupported pipeline_mode")
    if schema_fusion_strategy not in {"weighted", "rrf"}:
        raise ValueError("unsupported schema_fusion_strategy")
    if not isinstance(replicate_count, int) or replicate_count < 1:
        raise ValueError("replicate_count must be positive")
    # 步骤 1：复用 canonical catalog、选择与 suite policy ===============================
    catalog = load_catalog(catalog_path)
    scenarios = select_scenarios(catalog, scenario_ids)
    classifications = {item.scenario_id: item.classification for item in scenarios}
    suite_policy = {
        "suite_id": "explicit",
        "selected_scenario_ids": list(scenario_ids),
        "effects_by_classification": {"core": "required", "stress": "advisory", "manual_lab": "excluded"},
        "assertion_overrides": {},
        "scenario_classifications": classifications,
    }
    protocol = {
        "pipeline_mode": pipeline_mode,
        "schema_fusion_strategy": schema_fusion_strategy,
        "replicate_count": replicate_count,
    }
    constraints = dict(requested_runtime_constraints or {})
    settings = get_settings()
    if settings.schema_vector_backend.lower() != "inmemory" or settings.schema_embedding_provider.lower() != "deterministic":
        raise ValueError("P1-B plan-only requires inmemory + deterministic schema retrieval")
    selected_hash = selected_contract_hash(scenarios)
    policy_hash = suite_policy_hash(
        scenario_ids=scenario_ids,
        classifications=classifications,
        gate_policy=suite_policy,
    )
    spec_hash = run_spec_hash(
        selected_hash=selected_hash,
        policy_hash=policy_hash,
        protocol=protocol,
        oracle_fixture_identity=oracle_fixture_identity,
        constraints=constraints,
    )
    # 步骤 2：用与 evaluator 相同的 RunSpec/hash 输入冻结身份 ============================
    run_spec = EvalRunSpec(
        run_id="plan-only",
        scenario_ids=scenario_ids,
        execution_protocol=ExecutionProtocol(pipeline_mode, schema_fusion_strategy, replicate_count),
        requested_runtime_constraints=constraints,
        oracle_fixture_identity=oracle_fixture_identity,
        suite_policy=suite_policy,
        selected_contract_hash=selected_hash,
        suite_policy_hash=policy_hash,
        run_spec_hash=spec_hash,
    )
    # 步骤 3：只构建确定性 schema index 取指纹；绝不创建 DB RunEnvironment/provider =======
    vector_index = None
    try:
        vector_index, documents, documents_hash = build_configured_schema_vector_index(domain_schema=load_domain_schema())
        expected_runtime = _resolved_runtime_values(
            settings,
            run_spec,
            schema_documents=documents,
            schema_docs_hash_value=documents_hash,
            vector_index=vector_index,
        )
    finally:
        _close_vector_index(vector_index)
    unsigned = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "catalog_hash": catalog.catalog_hash,
        "selected_contract_hash": selected_hash,
        "suite_policy_hash": policy_hash,
        "run_spec_hash": spec_hash,
        "scenario_ids": list(scenario_ids),
        "scenario_classifications": classifications,
        "suite_policy": suite_policy,
        "execution_protocol": protocol,
        "oracle_fixture_identity": oracle_fixture_identity,
        "requested_runtime_constraints": constraints,
        "expected_runtime": expected_runtime,
    }
    return {**unsigned, "plan_digest": _canonical_hash(unsigned)}


def write_run_plan(plan: dict[str, Any], output: Path) -> None:
    """独占、原子写计划；旧 plan 不能被一次新请求覆盖。"""

    if output.exists():
        raise FileExistsError(f"run plan already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"run plan temporary file already exists: {temporary}")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def _canonical_hash(value: Any) -> str:
    """生成不受 JSON 键顺序影响的计划摘要。"""

    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
