"""Phase 2.7 数据库升级测试：challenge 用例、固定事实和安全基础门。

★ 这里验证的是“新数据底座可用”，不是 Phase 3A 新 Text2SQL pipeline。困难诊断题只要求
有 expected SQL 和口径说明，完整 trace_steps 留到 M11/M12。
"""

from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.base import Base
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents
from engine.sql_guard.guard import validate_readonly_sql
from eval.run_eval import load_case_set
from scripts.seed_data import seed_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_PATH = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
REGRESSION_PATH = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
EXCEPTION_CASES_PATH = PROJECT_ROOT / "eval" / "cases" / "database-exception-cases.yaml"
EXCEPTION_SUITE_PATH = PROJECT_ROOT / "eval" / "cases" / "database-exception-suite.yaml"


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


def test_automatic_reference_sql_cases_use_result_match() -> None:
    """M23：自动 case 的 reference SQL 必须参与行集判分，不能只当说明文字。"""

    for path in [CHALLENGE_PATH, REGRESSION_PATH]:
        for case in _load_cases(path):
            if case["security_expectation"] != "allow":
                continue
            properties = set(case.get("case_properties") or [])
            if case["check"]["type"] == "manual" or "manual_review" in properties:
                continue
            assert case["check"]["type"] in {"result_match", "expected_value"}, case["id"]


def test_database_exception_cases_are_explicit_automatic_contracts() -> None:
    """异常专项新增题必须有 reference SQL 和自动结果判定，不能只停留在说明文档。"""

    cases = _load_cases(EXCEPTION_CASES_PATH)

    assert [case["id"] for case in cases] == ["db_anomaly_001", "db_anomaly_002", "db_anomaly_003"]
    assert all(case["check"]["type"] == "result_match" for case in cases)
    assert all(str(case["expected_sql"]).strip() for case in cases)


def test_database_exception_suite_references_existing_cases_without_copying() -> None:
    """专项只选取原文件 case，避免 formal/challenge/diagnostic 的重复定义漂移。"""

    cases = load_case_set(EXCEPTION_SUITE_PATH)

    assert [case.case_id for case in cases] == [
        "db_simple_002",
        "db_multi_001",
        "db_core_002",
        "db_join_003",
        "db_anomaly_001",
        "db_anomaly_002",
        "db_anomaly_003",
    ]
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.source_file for case in cases} == {
        "eval/cases/database-upgrade-challenge.yaml",
        "eval/cases/phase3a-diagnostic-benchmark.yaml",
        "eval/cases/database-exception-cases.yaml",
    }


def test_database_exception_reference_sql_catches_signed_amount_join_and_reconciliation() -> None:
    """三道新增异常题要真的撞到 seed 彩蛋，而不是在纯净数据上也会通过。"""

    cases = {case["id"]: case for case in _load_cases(EXCEPTION_CASES_PATH)}
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            seed_database(session, reset_existing=True)
            signed_amount = session.execute(text(str(cases["db_anomaly_001"]["expected_sql"]))).scalar_one()
            completed_positive_amount = session.execute(
                text(
                    "SELECT ROUND(SUM(refund_amount), 2) FROM refunds "
                    "WHERE refund_status = 'completed' "
                    "AND processed_at < '2026-08-01 00:00:00' "
                    "AND refund_amount > 0"
                )
            ).scalar_one()
            by_channel = session.execute(text(str(cases["db_anomaly_002"]["expected_sql"]))).mappings().all()
            mismatch_count = session.execute(text(str(cases["db_anomaly_003"]["expected_sql"]))).scalar_one()
            wrong_namespace_join = session.execute(
                text(
                    "SELECT COUNT(*) FROM refunds r "
                    "JOIN orders o ON r.source_order_no = o.order_no "
                    "WHERE r.refund_status = 'completed'"
                )
            ).scalar_one()

        assert signed_amount is not None
        # 至少一笔 completed 负数冲销落在窗口内；否则 signed SUM 与只加正数没有差别。
        assert signed_amount < completed_positive_amount
        assert by_channel
        assert mismatch_count == 5
        # SRC-* 与 ORD-* 不在同一命名空间，错误 join 必须无法伪装为正确关联。
        assert wrong_namespace_join == 0
    finally:
        Base.metadata.drop_all(engine)


def test_runtime_schema_documents_include_m23_join_and_status_facts() -> None:
    """M23：会影响 SQL join / 过滤的事实必须进入运行时可检索文档。"""

    schema = load_domain_schema()
    documents = {document.doc_id: document for document in build_schema_documents(schema)}

    assert "pending_payment" in documents["field:orders.order_status"].keyword_text
    assert "不能与 order_no" in documents["field:orders.source_order_no"].keyword_text
    assert "整单退款" in documents["relation:refunds_order_item"].keyword_text
    assert schema.metrics["order_count"].formula == "COUNT(DISTINCT orders.id)"
    assert schema.metrics["refund_rate"].filter
    assert schema.metrics["net_refund_amount"].filter == "refunds.refund_status = 'completed'"


def test_challenge_security_cases_are_blocked_by_existing_sql_guard() -> None:
    """安全基础门仍然只验证 SQL Guard，不要求 Phase 3A trace_steps。"""

    security_cases = [case for case in _load_cases(CHALLENGE_PATH) if case["security_expectation"] == "block"]

    assert len(security_cases) == 2
    for case in security_cases:
        result = validate_readonly_sql(str(case["question"]))
        assert result.is_allowed is False
        assert result.blocked_reason
