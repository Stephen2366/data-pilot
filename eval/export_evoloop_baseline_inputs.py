"""零 provider 导出 P1-C3 所需的公开 catalog 投影与两类 Hidden offer。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.evoloop_hidden_executor import build_development_offer, validate_development_fixture
from eval.evoloop_hidden_material import build_public_offer, load_hidden_material
from eval.evoloop_projection import project_catalog_for_evoloop

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """只经 canonical readers 读取输入并独占写一份非敏感机器包。"""

    parser = argparse.ArgumentParser(description="Export public P1-C3 preparation inputs without Runtime/provider calls")
    parser.add_argument("--catalog", type=Path, default=PROJECT_ROOT / "eval/cases/catalog/scenarios.yaml")
    # ★ Hidden 题面属于仓库外受信输入，不能用仓库内默认路径让人误以为它应被提交。
    parser.add_argument("--formal-material", type=Path, required=True)
    parser.add_argument("--development-material", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists; refusing overwrite")
    development = validate_development_fixture(json.loads(args.development_material.read_text(encoding="utf-8")))
    value = {
        "schema": "datapilot.evoloop-baseline-public-inputs/v1",
        "catalog_projection": project_catalog_for_evoloop(args.catalog),
        "formal_hidden_offer": build_public_offer(load_hidden_material(args.formal_material)),
        "development_hidden_offer": build_development_offer(development),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": "exported", "provider_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
