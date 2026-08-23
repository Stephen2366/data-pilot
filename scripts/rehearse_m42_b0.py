"""M42-F 零 provider 集成 rehearsal。

脚本在内存 SQLite 中构建显式 Phase 4B profile，执行一次默认 deterministic business
retrieval，构造 Agent Scenario skeleton，并只用仓库 manifest 对账外部 sealed reserve。
它不执行 M43+ runtime、真实 LLM、remote embedding 或 reserve candidate。
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from engine.phase4b.caller import Phase4BFixtureCallerResolver
from engine.phase4b.contracts import load_b0_contract_bundle
from engine.phase4b.identity import canonical_hash
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool
from eval.agent_reserve_contracts import validate_external_store
from eval.agent_scenario_contracts import (
    build_b0_fixture_evidence,
    build_completed_artifact,
    render_capability_report,
)
from scripts.seed_data import seed_database

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESERVE_MANIFEST = PROJECT_ROOT / "eval" / "cases" / "agent" / "phase4b_reserve_manifest.json"


def _json_safe(value: Any) -> Any:
    """只把 rehearsal 中的 Decimal 转成稳定文本，其余容器递归保留。"""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def rehearse(*, output_dir: Path, external_reserve_root: Path) -> dict[str, Any]:
    """从六份已冻结输入生成 B0 deterministic report，并返回安全摘要。"""

    immutable_outputs = (
        "m42-business-first-observation.json", "m42-agent-scenario-skeleton.json",
        "m42-capability-matrix.md", "m42-b0-deterministic-report.json", "m42-b0-deterministic-report.md",
    )
    if any((output_dir / name).exists() for name in immutable_outputs):
        raise ValueError("M42 rehearsal 输出已存在；首次 Observation 不得覆盖或伪装重跑")

    bundle = load_b0_contract_bundle()

    # 步骤 1：真实建库与 SQL oracle =================================================
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_summary = seed_database(session, reset_existing=True, profile_alias="phase4b")

    # 步骤 2：最小 caller 与首次默认 retrieval =====================================
    resolution = Phase4BFixtureCallerResolver(fixture_kind="test", bundle=bundle).resolve("ops")
    if resolution is None:
        raise RuntimeError("phase4b caller fixture 无法解析")
    t4 = bundle.scenario("T4")["turns"][0]
    expected_docs = sorted(item.split(":", 1)[1] for item in t4["evidence_requirements"])
    outcome = KnowledgeTool().retrieve(
        KnowledgeRequest(
            question=t4["question"], caller=resolution.caller, purpose="answer_evidence",
            run_id="m42-b0-business-first-observation",
        )
    )
    selected_docs = sorted(item.payload.document_key for item in outcome.selected_evidence)
    observation_unsigned = {
        "schema_version": "phase4b-business-first-observation-v1",
        "question_identity": canonical_hash({"question": t4["question"], "gold": expected_docs}),
        "gold_frozen_before_run": True,
        "expected_document_keys": expected_docs,
        "selected_document_keys": selected_docs,
        "all_gold_selected": set(expected_docs) <= set(selected_docs),
        "execution_outcome": outcome.execution_outcome,
        "reason_code": outcome.reason_code,
        "diagnostics": outcome.diagnostics.safe_projection(),
        "budget": {"max_candidates": 5, "max_selected": 2, "source": "KnowledgeRequest default"},
        "provider_calls": 0,
    }
    observation = {**observation_unsigned, "observation_identity": canonical_hash(observation_unsigned)}

    # 步骤 3：Agent skeleton 与 sealed reserve 只读对账 =============================
    agent_artifact = build_completed_artifact(
        bundle=bundle,
        run_id="m42-b0-agent-skeleton",
        executions=build_b0_fixture_evidence(bundle),
        runtime_identity={
            "runtime_family": "phase4b-agent-runtime-v1", "seed_profile_identity": seed_summary["seed_profile"]["profile_identity"],
            "oracle_identity": seed_summary["phase4b_facts"]["oracle_identity"], "caller_fixture": bundle.payload["caller_fixture"]["identity"],
            "business_release_identity": observation["diagnostics"]["release_identity"], "provider": "none",
        },
    )
    reserve_manifest = json.loads(RESERVE_MANIFEST.read_text(encoding="utf-8"))
    external_projection = {key: value for key, value in reserve_manifest.items() if key != "external_store"}
    validate_external_store(external_projection, external_root=external_reserve_root)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "m42-business-first-observation.json").write_text(
        json.dumps(observation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "m42-agent-scenario-skeleton.json").write_text(
        json.dumps(agent_artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    render_capability_report(agent_artifact, output=output_dir / "m42-capability-matrix.md")

    safe_seed = _json_safe({
        "seed_profile": seed_summary["seed_profile"],
        "phase4b_facts": seed_summary["phase4b_facts"],
    })
    report = {
        "contract_identity": bundle.content_identity,
        "seed": safe_seed,
        "caller": {
            "roles": sorted(resolution.caller.resolved_roles), "active_sql_role": resolution.active_sql_role,
            "tenant_id": resolution.caller.tenant_id, "caller_ref": resolution.caller.audit_ref,
        },
        "business_observation_identity": observation["observation_identity"],
        "agent_artifact_identity": agent_artifact["artifact_identity"],
        "reserve_identity": reserve_manifest["reserve_identity"],
        "provider_calls": 0,
    }
    (output_dir / "m42-b0-deterministic-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# M42 Phase 4B B0 Deterministic Report", "",
        f"- Contract identity: `{report['contract_identity']}`",
        f"- Seed profile identity: `{report['seed']['seed_profile']['profile_identity']}`",
        f"- Oracle identity: `{report['seed']['phase4b_facts']['oracle_identity']}`",
        f"- Business Observation: `{report['business_observation_identity']}`; all gold selected = `{observation['all_gold_selected']}`",
        f"- Agent skeleton: `{report['agent_artifact_identity']}`",
        f"- Sealed reserve: `{report['reserve_identity']}`",
        "- Provider calls: `0`",
        "", "M42 only proves B0 prerequisites; M43–M48 capabilities remain unavailable as shown in the capability matrix.",
    ]
    (output_dir / "m42-b0-deterministic-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    """解析只读 reserve 位置并执行不可覆盖的首次 B0 rehearsal。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("eval/reports/m42"))
    parser.add_argument("--external-reserve-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rehearse(output_dir=args.output_dir, external_reserve_root=args.external_reserve_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
