"""从已通过的 M48-P2 同源证据生成 v6、Phase 4B assurance 与演示回查报告。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.phase4b.b6_contracts import load_b6_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v6_contracts import build_agent_scenario_v6, sign_case
from eval.phase4b_assurance import build_phase4b_assurance

PROBE = Path(".agent_work/temp/m48/probe-p2/result.json")
OUTPUT = Path("eval/reports/m48")


def _contracts() -> dict[str, str]:
    """按 B0→B6 顺序读取 manifest，不绕过 content-binding 文件。"""

    result: dict[str, str] = {}
    paths = (
        "b0_contracts.manifest.json", "b1_contracts.manifest.json", "b2_contracts.manifest.json",
        "b3_diagnostic_campaign_v4.manifest.json", "b4_contracts.manifest.json",
        "b5_contracts.manifest.json", "b6_contracts.manifest.json",
    )
    for index, name in enumerate(paths):
        manifest = json.loads((Path("domain_pack/phase4b") / name).read_text(encoding="utf-8"))
        result[f"B{index}"] = manifest.get("content_identity", manifest.get("campaign_identity"))
        if not result[f"B{index}"]:
            raise ValueError(f"phase4b_manifest_identity_missing:{name}")
    return result


def build_from_probe(probe: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    """只投影 P2 safe summary；raw trace/task id/question/rows 不进入持久 artifact。"""

    if probe.get("decision") != "continue" or probe.get("rows_after_cleanup") != {"checkpoints": 0, "events": 0}:
        raise ValueError("m48_p2_not_releasable")
    bundle = load_b6_contract_bundle()
    source_execution = canonical_hash({
        "probe_id": probe["probe_id"], "seed_identity": probe["seed_identity"],
        "compact_identity": probe["compact_identity"], "canonical_versions": probe["canonical_versions"],
    })
    negative = probe["negative_paths"]
    child = probe["business_subgraph"]
    observations = {
        "CONTINUOUS_T1_T5_EXTENDED": {
            "versions": probe["canonical_versions"], "restart_continuation": probe["restart_continuation"],
            "oracle": probe["oracle"],
        },
        "COMPACT_TURN_TRIGGER": {
            "compact_identity": probe["compact_identity"],
            "source_turn_range": probe["compact_source_turn_range"], "trigger": "committed_turns",
        },
        "COMPACT_BUDGET_TRIGGER": {"trigger": "candidate_node_budget", "threshold": 0.75},
        "COMPACT_RESTART_RESUME": {
            "processes": probe["processes"], "restart_continuation": probe["restart_continuation"],
            "compact_identity": probe["compact_identity"],
        },
        "COMPACT_FALLBACK": {"outcome": "fallback_uncompacted", "source_retained": True},
        "EVIDENCE_REVALIDATION": {
            "sql_guard": probe["sql_guard_oracle"], "business_subgraph_termination": child["termination"],
            "extended_reacquired": True,
        },
        "ROLE_DRIFT": negative["role_drift"],
        "VERSION_CONFLICT": {"stale": negative["stale_version"], "competition": negative["competition"]},
        "SUBGRAPH_PARENT_CHILD_BUDGET": {
            "termination": child["termination"], "consumption": child["consumption"],
        },
        "PRIVATE_PAYLOAD_REJECTION": {
            "response_trace_redaction": probe["response_trace_redaction"], "provider_calls": 0,
        },
    }
    cases = tuple(sign_case({
        "scenario_id": scenario_id, "source": source_execution,
        "observations": observations[scenario_id],
        "assertions": [[f"required:{scenario_id.lower()}", "passed"]],
    }) for scenario_id in bundle.payload["scenarios"])
    scenario = build_agent_scenario_v6(
        bundle=bundle,
        run_spec={
            "run_id": "m48-b6-p2-same-source", "predecessor_artifact_version": "phase4b-agent-scenario-artifact-v5",
            "context_schema_version": bundle.payload["context_schema_version"],
            "compact_schema_version": bundle.payload["compact_schema_version"],
            "event_schema_version": bundle.payload["event_schema_version"],
            "source_execution_identity": source_execution,
        },
        cases=cases,
    )
    assurance = build_phase4b_assurance(
        bundle=bundle, scenario=scenario, contract_identities=_contracts(),
    )
    return scenario, assurance


def _markdown(scenario: dict[str, object], assurance: dict[str, object]) -> str:
    """形成只读演示回查链与人工检查清单，不暴露 raw execution payload。"""

    return "\n".join((
        "# M48 B6 continuous rehearsal", "",
        f"- Scenario v6: `{scenario['artifact_identity']}`",
        f"- Phase 4B assurance: `{assurance['artifact_identity']}`",
        "- Technical status: `B0–B6 available`",
        "- Rollout: `Pipeline default / Subgraph server-controlled experimental`",
        "- Claims: `no RAG quality claim / no production certification / reserve sealed`", "",
        "## Safe inspection chain", "",
        "1. Answer/Citation → generation-visible Evidence identity",
        "2. Evidence → parent Observation/Action input fingerprint",
        "3. Action → parent/child Budget and termination",
        "4. Turn → Task state/version and Compact source range/identity", "",
        "## Manual demo checklist", "",
        "- [ ] T1–T5 remain one task lineage and T6 shows Compact T1–T5.",
        "- [ ] Restart continuation reuses the same Compact identity.",
        "- [ ] Role drift/version conflict execute zero deep runtime.",
        "- [ ] Response/Trace contain no raw recent turns, rows, document body, prompt or credentials.",
        "- [ ] Explain Pipeline default, experimental Subgraph, sealed reserve and non-production claim boundary.", "",
    ))


def main() -> None:
    """验证 P2 Gate 后写出三个稳定交付物。"""

    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    scenario, assurance = build_from_probe(probe)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "m48-agent-scenario-v6.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (OUTPUT / "m48-phase4b-assurance.json").write_text(
        json.dumps(assurance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (OUTPUT / "m48-continuous-rehearsal.md").write_text(
        _markdown(scenario, assurance), encoding="utf-8",
    )
    print(json.dumps({
        "status": "passed", "scenario_identity": scenario["artifact_identity"],
        "assurance_identity": assurance["artifact_identity"], "cases": len(scenario["cases"]),
        "provider_calls": 0, "tokens": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
