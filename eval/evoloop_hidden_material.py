"""P1-C2 DataPilot 受信 Hidden 材料合同与零模型 rehearsal。

本模块属于 DataPilot companion。EvoLoop 普通控制面只能消费 ``build_public_offer`` 的
非敏感输出，不能读取本模块返回的逐题对象。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


HIDDEN_MATERIAL_SCHEMA = "datapilot.evoloop-hidden-material/v1"
HIDDEN_OFFER_SCHEMA = "datapilot.evoloop-hidden-offer/v1"
REQUIRED_COVERAGE = frozenset({"numeric_time", "cross_table", "safety_block", "expected_rejection"})


class HiddenMaterialError(ValueError):
    """受信材料不完整；``issues`` 一次返回全部可定位问题。"""

    def __init__(self, issues: list[str]):
        self.issues = tuple(issues)
        super().__init__("; ".join(issues))


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _exact(value: Any, fields: set[str], path: str, issues: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        issues.append(f"{path}: must be an object")
        return None
    missing, unknown = sorted(fields - set(value)), sorted(set(value) - fields)
    if missing or unknown:
        issues.append(f"{path}: fields mismatch missing={missing}, unknown={unknown}")
        # 有未知字段但必填项齐全时继续深挖，才能一次返回更多可定位问题；缺字段则不能安全读取。
        if missing:
            return None
    return value


def load_hidden_material(path: Path) -> dict[str, Any]:
    """读取私有 JSON，再委派同一个内存 validator。"""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HiddenMaterialError([f"$: cannot read material: {exc}"]) from exc
    return validate_hidden_material(raw)


def validate_hidden_material(raw: Any) -> dict[str, Any]:
    """集中验证私有 schema、唯一性、fixture/oracle/assertion 与 coverage。"""

    issues: list[str] = []
    root = _exact(raw, {"schema", "version", "cases"}, "$", issues)
    if root is None:
        raise HiddenMaterialError(issues)
    if root["schema"] != HIDDEN_MATERIAL_SCHEMA:
        issues.append("schema: unsupported version")
    if not isinstance(root["version"], str) or not root["version"].strip():
        issues.append("version: must be non-empty")
    cases = root["cases"]
    if not isinstance(cases, list) or len(cases) < 4:
        issues.append("cases: must contain at least four cases")
        cases = []
    seen_ids: set[str] = set()
    seen_fixtures: set[str] = set()
    observed_coverage: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, candidate in enumerate(cases):
        path_label = f"cases[{index}]"
        item = _exact(
            candidate,
            {"case_id", "coverage", "question", "user_role", "fixture", "oracle", "assertion"},
            path_label,
            issues,
        )
        if item is None:
            continue
        for field in ("case_id", "coverage", "question", "user_role"):
            if not isinstance(item[field], str) or not item[field].strip():
                issues.append(f"{path_label}.{field}: must be non-empty")
        case_id = item.get("case_id")
        if isinstance(case_id, str):
            if case_id in seen_ids:
                issues.append(f"{path_label}.case_id: duplicate={case_id}")
            seen_ids.add(case_id)
        coverage = item.get("coverage")
        if coverage not in REQUIRED_COVERAGE:
            issues.append(f"{path_label}.coverage: unsupported={coverage!r}")
        else:
            observed_coverage.add(coverage)
        fixture = _exact(item.get("fixture"), {"fixture_id", "setup_sql"}, f"{path_label}.fixture", issues)
        if fixture is not None:
            fixture_id = fixture.get("fixture_id")
            if not isinstance(fixture_id, str) or not fixture_id:
                issues.append(f"{path_label}.fixture.fixture_id: must be non-empty")
            elif fixture_id in seen_fixtures:
                issues.append(f"{path_label}.fixture.fixture_id: duplicate={fixture_id}")
            else:
                seen_fixtures.add(fixture_id)
            setup_sql = fixture.get("setup_sql")
            if not isinstance(setup_sql, list) or not setup_sql or not all(isinstance(sql, str) and sql.strip() for sql in setup_sql):
                issues.append(f"{path_label}.fixture.setup_sql: must be non-empty SQL strings")
        oracle = _exact(item.get("oracle"), {"kind", "sql", "expected_columns", "expected_rows", "expected_status"}, f"{path_label}.oracle", issues)
        assertion = _exact(item.get("assertion"), {"kind", "tolerance", "reason_code"}, f"{path_label}.assertion", issues)
        if oracle is not None and assertion is not None and coverage in REQUIRED_COVERAGE:
            if coverage in {"numeric_time", "cross_table"}:
                if oracle.get("kind") != "sqlite_result" or not isinstance(oracle.get("sql"), str) or not oracle["sql"].strip():
                    issues.append(f"{path_label}.oracle: SQL coverage requires sqlite_result and SQL")
                if not isinstance(oracle.get("expected_columns"), list) or not isinstance(oracle.get("expected_rows"), list):
                    issues.append(f"{path_label}.oracle: expected columns/rows must be lists")
                if oracle.get("expected_status") is not None or assertion.get("kind") != "result_match":
                    issues.append(f"{path_label}: SQL coverage contract drift")
            else:
                expected_kind = coverage
                if oracle.get("kind") != "expected_control" or oracle.get("expected_status") not in {"blocked", "rejected"}:
                    issues.append(f"{path_label}.oracle: control coverage requires blocked/rejected status")
                if oracle.get("sql") is not None or oracle.get("expected_columns") != [] or oracle.get("expected_rows") != []:
                    issues.append(f"{path_label}.oracle: control coverage must not carry SQL result gold")
                if assertion.get("kind") != expected_kind or not isinstance(assertion.get("reason_code"), str):
                    issues.append(f"{path_label}.assertion: control kind/reason code mismatch")
        normalized.append(dict(item))
    missing_coverage = sorted(REQUIRED_COVERAGE - observed_coverage)
    if missing_coverage:
        issues.append(f"cases: missing coverage={missing_coverage}")
    duplicated_coverage = sorted(name for name in REQUIRED_COVERAGE if sum(item.get("coverage") == name for item in normalized) != 1)
    if duplicated_coverage:
        issues.append(f"cases: each required coverage must appear exactly once; invalid={duplicated_coverage}")
    if issues:
        raise HiddenMaterialError(issues)
    return {"schema": root["schema"], "version": root["version"], "cases": normalized}


def rehearse_hidden_material(material: dict[str, Any]) -> dict[str, Any]:
    """零模型执行 fixture/oracle 与确定性 assertion，证明四类材料可消费。"""

    results: list[dict[str, str]] = []
    for item in material["cases"]:
        coverage, oracle = item["coverage"], item["oracle"]
        if coverage in {"numeric_time", "cross_table"}:
            connection = sqlite3.connect(":memory:")
            try:
                for statement in item["fixture"]["setup_sql"]:
                    connection.execute(statement)
                cursor = connection.execute(oracle["sql"])
                columns = [description[0] for description in cursor.description or ()]
                rows = [list(row) for row in cursor.fetchall()]
            finally:
                connection.close()
            passed = columns == oracle["expected_columns"] and rows == oracle["expected_rows"]
        else:
            # 控制类 rehearsal 不调用 Agent，只验证冻结的预期动作可由 typed assertion 判定。
            passed = oracle["expected_status"] == ("blocked" if coverage == "safety_block" else "rejected")
        results.append({"case_id": item["case_id"], "state": "passed" if passed else "failed"})
    return {"material_digest": _digest(material), "state": "passed" if all(item["state"] == "passed" for item in results) else "failed", "results": results}


def build_public_offer(material: dict[str, Any]) -> dict[str, Any]:
    """生成 ordinary side 唯一允许获得的非敏感 Hidden offer。"""

    return {
        "schema": HIDDEN_OFFER_SCHEMA,
        "version": material["version"],
        "private_digest": _digest(material),
        "coverage": sorted(REQUIRED_COVERAGE),
        "expected_count": len(material["cases"]),
        "paired_policy": "one_baseline_one_final_candidate",
        "retention_policy": "private_results_until_pair_release",
        "budget_policy": {"baseline_executions": 1, "candidate_executions": 1, "retries": 0},
    }
