"""生成并验证 M47 Agent Scenario v5 的零 provider rehearsal artifact。"""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.phase4b.b5_contracts import load_b5_contract_bundle
from eval.agent_scenario_v5_contracts import build_deterministic_agent_scenario_v5, validate_agent_scenario_v5


def main() -> None:
    """生成、复验并保存六场景 v5 技术 artifact。"""

    bundle = load_b5_contract_bundle()
    artifact = build_deterministic_agent_scenario_v5(bundle)
    validate_agent_scenario_v5(artifact, bundle=bundle)
    output = Path("eval/reports/m47/m47-agent-scenario-v5-rehearsal.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({**artifact, "provider_calls": 0, "tokens": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "artifact_identity": artifact["artifact_identity"], "cases": len(artifact["cases"]), "provider_calls": 0, "tokens": 0}))


if __name__ == "__main__":
    main()
