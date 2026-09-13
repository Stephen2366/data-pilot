"""向 EvoLoop 暴露 M27 catalog 的最小只读投影。

★ DataPilot 仍拥有题面、oracle 与评分语义；这里故意只给角色治理所需的 ID、classification
和 assertion kind。这样 EvoLoop 可以冻结 Regression/Safety 清单，却不会复制第二份 catalog。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.catalog import load_catalog


def project_catalog_for_evoloop(path: Path) -> dict[str, Any]:
    """通过 canonical loader 读取 catalog，再生成稳定、非敏感的治理投影。"""

    catalog = load_catalog(path)
    return {
        "contract_version": catalog.contract_version,
        # M27 的 catalog hash 是裸 SHA-256；交换边界显式补算法前缀，不重新解释内容。
        "catalog_hash": f"sha256:{catalog.catalog_hash}",
        "scenarios": [
            {
                "scenario_id": scenario.scenario_id,
                "classification": scenario.classification,
                "assertions": [
                    {"assertion_id": assertion.assertion_id, "kind": assertion.kind}
                    for assertion in sorted(scenario.assertions, key=lambda item: item.assertion_id)
                ],
            }
            for scenario in sorted(catalog.scenarios, key=lambda item: item.scenario_id)
        ],
    }
