"""Phase 2.7 数据库升级测试：challenge 用例、固定事实和安全基础门。

★ 这里验证的是“新数据底座可用”，不是 Phase 3A 新 Text2SQL pipeline。困难诊断题只要求
有 expected SQL 和口径说明，完整 trace_steps 留到 M11/M12。
"""

from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.base import Base
from engine.sql_guard.guard import validate_readonly_sql
from scripts.seed_data import seed_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_PATH = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
REGRESSION_PATH = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"


def _load_cases(path: Path) -> list[dict[str, object]]:
    """读取 YAML cases，测试只关心结构完整性，不绑定 eval.run_eval 的阶段二字段。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(payload.get("cases") or [])


def test_database_upgrade_challenge_cases_are_complete() -> None:
    """16 条 challenge 必须覆盖简单、核心指标、多表、困难诊断和安全。"""

    cases = _load_cases(CHALLENGE_PATH)
    task_types = [case["task_type"] for case in cases]

    assert len(cases) == 16
    assert task_types.count("simple_sql") == 3
    assert task_types.count("core_metric") == 4
    assert task_types.count("multi_table") == 4
    assert task_types.count("difficult_diagnosis") == 3
    assert task_types.count("security") == 2

    for case in cases:
        assert case["question"]
        assert case["expected_tables"] is not None
        assert case["expected_columns"] is not None
        assert case["security_expectation"] in {"allow", "block"}
        assert isinstance(case["check"], dict)
        if case["security_expectation"] == "allow":
            assert str(case.get("expected_sql", "")).strip()


def test_phase3a_regression_keeps_ten_case_gate_without_running_m8() -> None:
    """Phase 3A regression 只在数据库升级阶段落文件，比例仍是 2/3/3/2。"""

    cases = _load_cases(REGRESSION_PATH)
    task_types = [case["task_type"] for case in cases]

    assert len(cases) == 10
    assert task_types.count("simple_sql") == 2
    assert task_types.count("aggregation") == 3
    assert task_types.count("multi_table") == 3
    assert task_types.count("security") == 2


def test_challenge_expected_sql_is_stable_for_database_upgrade_gate() -> None:
    """执行 11 条基础 / 核心 / 中等 SQL，验证新库固定事实可复现。"""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    cases = _load_cases(CHALLENGE_PATH)
    executable_types = {"simple_sql", "core_metric", "multi_table"}

    with Session(engine) as session:
        seed_database(session, reset_existing=True)
        checked = 0
        for case in cases:
            if case["task_type"] not in executable_types:
                continue
            rows = session.execute(text(str(case["expected_sql"]))).mappings().all()
            assert rows, case["id"]
            check = case["check"]
            if isinstance(check, dict) and check.get("type") == "contains":
                assert str(check["value"]) in str(rows), case["id"]
            checked += 1

    assert checked == 11


def test_challenge_security_cases_are_blocked_by_existing_sql_guard() -> None:
    """安全基础门仍然只验证 SQL Guard，不要求 Phase 3A trace_steps。"""

    security_cases = [case for case in _load_cases(CHALLENGE_PATH) if case["security_expectation"] == "block"]

    assert len(security_cases) == 2
    for case in security_cases:
        result = validate_readonly_sql(str(case["question"]))
        assert result.is_allowed is False
        assert result.blocked_reason
