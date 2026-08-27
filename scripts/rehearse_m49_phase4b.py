"""M49：从显式 evidence package 生成 Scenario v7 与 assurance v2。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

# 允许从仓库根目录直接执行 ``python scripts/...``，与其他 rehearsal 入口一致。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.phase4b.b6_contracts import load_b6_contract_bundle
from eval.agent_scenario_v7_contracts import build_agent_scenario_v7, sign_case
from eval.phase4b_assurance_v2 import build_phase4b_assurance_v2


def build_from_evidence_package(package: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """缺失场景只投影 not_observed；绝不从常量或合同身份补一张通过票。"""

    bundle = load_b6_contract_bundle()
    provided = package.get("scenario_evidence", {})
    if not isinstance(provided, Mapping):
        raise ValueError("m49_scenario_evidence_invalid")
    cases = []
    for scenario_id in bundle.payload["scenarios"]:
        evidence = provided.get(scenario_id)
        if evidence is None:
            cases.append(sign_case({
                "scenario_id": scenario_id,
                "required": True,
                "status": "not_observed",
                "observations": {},
                "evidence_locator": None,
                "evidence_identity": None,
                "assertions": [{
                    "assertion_id": f"required:{scenario_id.lower()}",
                    "status": "not_observed",
                    "evidence_locator": None,
                    "evidence_identity": None,
                }],
            }))
            continue
        cases.append(sign_case({
            "scenario_id": scenario_id,
            "required": True,
            "status": evidence["status"],
            "observations": dict(evidence["observations"]),
            "evidence_locator": evidence["evidence_locator"],
            "evidence_identity": evidence["evidence_identity"],
            "assertions": [dict(item) for item in evidence["assertions"]],
        }))
    scenario = build_agent_scenario_v7(
        bundle=bundle,
        run_spec={
            "run_id": package["run_id"],
            "predecessor_artifact_version": "phase4b-agent-scenario-artifact-v6",
            "source_execution_identity": package["source_execution_identity"],
        },
        cases=tuple(cases),
    )
    assurance = build_phase4b_assurance_v2(
        bundle=bundle,
        scenario=scenario,
        contract_identities=package["contract_identities"],
        milestone_evidence=package["milestone_evidence"],
    )
    return scenario, assurance


def main() -> int:
    """从已冻结的 safe evidence package 生成两份可重复校验的正式 artifact。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-package", type=Path, required=True)
    parser.add_argument("--scenario-output", type=Path, required=True)
    parser.add_argument("--assurance-output", type=Path, required=True)
    args = parser.parse_args()
    package = json.loads(args.evidence_package.read_text(encoding="utf-8"))
    if not isinstance(package, dict):
        raise ValueError("m49_evidence_package_root_invalid")
    scenario, assurance = build_from_evidence_package(package)
    for path, payload in (
        (args.scenario_output, scenario),
        (args.assurance_output, assurance),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "scenario_status": scenario["status"],
        "scenario_identity": scenario["artifact_identity"],
        "assurance_status": assurance["status"],
        "assurance_identity": assurance["artifact_identity"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
