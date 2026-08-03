"""EvalOps-lite：读取 YAML 用例，调用 `/api/query`，输出 Markdown 评测报告。

★ 这个模块不是完整评测平台，而是从阶段二 smoke 延伸到 Phase 3A diagnostic benchmark 的
最小闭环：case -> API -> AgentResponse -> pass/fail/skipped/error_type。M8.5 只补多文件合并、
pipeline_mode 覆盖和诊断报告字段，复杂 scorer / 历史库 / HTML 仪表盘仍留给独立 EvalOps。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from eval.scorers.base import EvalScoreDetail, summarize_score_details
from eval.scorers.factory import score_case as score_case_details
from eval.scorers.langfuse_scores import LangFuseScoreWriter, build_langfuse_score_payloads
from eval.scorers.llm_judge import resolve_judge_model
from eval.scorers.rule_scorers import score_case_rules, should_skip_due_to_pipeline_mode
from eval.triage import (
    FailureTriage,
    build_triage_score_payloads,
    compare_triage_files,
    triage_results,
    triage_summary,
    write_triage_json,
)
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.retriever import build_configured_schema_vector_index
from engine.schema_retrieval.vector_index import VectorIndex
from scripts.seed_data import seed_database

DEFAULT_CASES_PATH = PROJECT_ROOT / "eval" / "cases" / "smoke.yaml"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "eval" / "reports" / "latest.md"
DEFAULT_TRACE_PATH = PROJECT_ROOT / ".agent_work" / "temp" / "m6-eval-traces.jsonl"


@dataclass(frozen=True)
class EvalCase:
    """一条 eval case 的稳定结构。

    ★ M8.5 起同一个 loader 同时服务 M6 smoke、Phase 3A regression 和 32 条 diagnostic：
    旧 smoke 字段不能被新字段反向绑架，新字段则先在数据结构里预留，方便 M9-M12 继续扩展。
    """

    case_id: str
    task_type: str
    question: str
    user_role: str
    expected_tables: list[str]
    expected_columns: list[str]
    expected_metrics: list[str]
    expected_trace_steps: list[Any]
    pipeline_mode: str
    security_expectation: Literal["allow", "block"]
    check_type: str
    check_value: str
    source_file: str = ""
    phase3a_capabilities: list[str] = field(default_factory=list)
    phase3a_blocking: bool = True
    case_properties: list[str] = field(default_factory=list)
    linked_case_id: str | None = None
    expected_tables_alternatives: list[dict[str, Any]] = field(default_factory=list)
    expected_plan: dict[str, Any] = field(default_factory=dict)
    expected_plan_result: str = ""
    expected_issue_tag: str = ""
    expected_schema_context: dict[str, Any] = field(default_factory=dict)
    expected_column_aliases: dict[str, list[str]] = field(default_factory=dict)
    security_subtype: str | None = None
    expected_sql: str = ""
    check: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalScore:
    """评分函数的结构化输出。

    reason 给人读，issue_tags 给后续报告 / 对照脚本稳定消费；M8 只落最小标签集合，不提前做
    完整 scorer 平台。
    """

    passed: bool
    reason: str
    issue_tags: list[str]
    review_required: bool = False
    skipped_due_to_pipeline_mode: bool = False


@dataclass(frozen=True)
class EvalResult:
    """单条 case 的执行结果，Markdown 报告只消费这个结构。"""

    case: EvalCase
    passed: bool
    reason: str
    issue_tags: list[str]
    review_required: bool
    skipped_due_to_pipeline_mode: bool
    status_code: int
    route: str | None
    safety_status: str | None
    error_type: str | None
    trace_id: str | None
    sql: str | None
    response_body: dict[str, Any]
    actual_pipeline_mode: str
    score_details: list[EvalScoreDetail] = field(default_factory=list)


def _source_file_label(path: Path) -> str:
    """把 case 来源路径转成报告里稳定、跨机器可读的相对路径。"""

    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _load_cases_from_path(path: Path) -> list[EvalCase]:
    """从单个 YAML 加载 cases，并把 M8.5 诊断字段保留下来。

    ★ 这里做轻量结构化转换，不重新定义字段口径；如果 YAML 缺字段，直接抛错提醒用例不完整。
    """

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases: list[EvalCase] = []
    for item in payload.get("cases") or []:
        check = item.get("check") or {}
        cases.append(
            EvalCase(
                case_id=str(item["id"]),
                task_type=str(item["task_type"]),
                question=str(item["question"]),
                user_role=str(item.get("user_role", "ops")),
                expected_tables=list(item.get("expected_tables") or []),
                expected_columns=list(item.get("expected_columns") or []),
                expected_metrics=list(item.get("expected_metrics") or []),
                expected_trace_steps=list(item.get("expected_trace_steps") or []),
                pipeline_mode=str(item.get("pipeline_mode", "baseline")),
                security_expectation=item.get("security_expectation", "allow"),
                check_type=str(check.get("type", "contains")),
                check_value=str(check.get("value", "")),
                source_file=_source_file_label(path),
                phase3a_capabilities=list(item.get("phase3a_capabilities") or []),
                phase3a_blocking=bool(item.get("phase3a_blocking", True)),
                case_properties=list(item.get("case_properties") or []),
                linked_case_id=item.get("linked_case_id"),
                expected_tables_alternatives=list(item.get("expected_tables_alternatives") or []),
                expected_plan=dict(item.get("expected_plan") or {}),
                expected_plan_result=str(item.get("expected_plan_result", "")),
                expected_issue_tag=str(item.get("expected_issue_tag", "")),
                expected_schema_context=dict(item.get("expected_schema_context") or {}),
                expected_column_aliases={
                    str(column): [str(alias) for alias in aliases]
                    for column, aliases in dict(item.get("expected_column_aliases") or {}).items()
                },
                security_subtype=item.get("security_subtype"),
                expected_sql=str(item.get("expected_sql", "")),
                check=dict(check),
            )
        )
    return cases


def load_cases(path: Path = DEFAULT_CASES_PATH, extra_cases: list[Path] | None = None) -> list[EvalCase]:
    """加载主 case 文件，并可按顺序合并额外 case 文件。

    ★ M8.5 不做 includes 语法，保持显式 `--cases + --extra-cases`：调用者一眼能看出
    32 条 diagnostic benchmark 是由哪两个文件拼出来的。
    """

    paths = [path, *(extra_cases or [])]
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for case_path in paths:
        for case in _load_cases_from_path(case_path):
            if case.case_id in seen_ids:
                raise ValueError(f"duplicate eval case id: {case.case_id}")
            seen_ids.add(case.case_id)
            cases.append(case)
    return cases


def _prepare_sqlite_seed() -> Any:
    """创建带 M1 确定性 seed 的内存 SQLite engine。

    Eval 默认不碰 MySQL 开发库，避免“跑评测”变成隐式写库操作；但 API seam 仍然是真实
    `/api/query`，只是数据库依赖在进程内被 FastAPI 覆盖。
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)
    return engine


@contextmanager
def seeded_api_client(
    trace_path: Path = DEFAULT_TRACE_PATH,
    *,
    schema_vector_index: VectorIndex | None = None,
    schema_vector_index_metadata: dict[str, Any] | None = None,
) -> Generator[TestClient, None, None]:
    """返回一个连接内存 seed 数据库的 FastAPI TestClient。"""

    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")
    engine = _prepare_sqlite_seed()

    def override_get_db() -> Generator[Session, None, None]:
        """把正式数据库 Session 替换成内存 SQLite Session。"""

        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    if schema_vector_index is not None:
        app.state.schema_vector_index = schema_vector_index
        app.state.schema_vector_index_metadata = schema_vector_index_metadata or {}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        if hasattr(app.state, "schema_vector_index"):
            delattr(app.state, "schema_vector_index")
        if hasattr(app.state, "schema_vector_index_metadata"):
            delattr(app.state, "schema_vector_index_metadata")
        Base.metadata.drop_all(engine)


def _score_expected_value(case: EvalCase, body: dict[str, Any]) -> EvalScore:
    """兼容旧测试入口：实际评分逻辑已迁移到 `eval.scorers.rule_scorers`。"""

    detail = score_case_rules(case=case, body=body, status_code=200, actual_pipeline_mode=case.pipeline_mode)[-1]
    return EvalScore(bool(detail.passed), detail.reason, detail.issue_tags, review_required=detail.review_required)

def _score_result_match(case: EvalCase, body: dict[str, Any]) -> EvalScore:
    """兼容旧测试入口：实际评分逻辑已迁移到 `eval.scorers.rule_scorers`。"""

    detail = score_case_rules(case=case, body=body, status_code=200, actual_pipeline_mode=case.pipeline_mode)[-1]
    return EvalScore(bool(detail.passed), detail.reason, detail.issue_tags, review_required=detail.review_required)


def _should_skip_due_to_pipeline_mode(case: EvalCase, actual_pipeline_mode: str) -> bool:
    """兼容旧入口；实际判断在 `eval.scorers.rule_scorers`。"""

    return should_skip_due_to_pipeline_mode(case, actual_pipeline_mode)


def _score_case(
    case: EvalCase,
    body: dict[str, Any],
    status_code: int,
    actual_pipeline_mode: str | None = None,
) -> EvalScore:
    """兼容旧报告的薄壳评分入口，内部调用 M17 scorer 单一事实源。"""

    actual_mode = actual_pipeline_mode or case.pipeline_mode
    details = score_case_rules(case=case, body=body, status_code=status_code, actual_pipeline_mode=actual_mode)
    summary = summarize_score_details(details)
    return EvalScore(
        summary.passed,
        summary.reason,
        summary.issue_tags,
        review_required=summary.review_required,
        skipped_due_to_pipeline_mode=summary.skipped_due_to_pipeline_mode,
    )


def run_cases(
    cases: list[EvalCase],
    client: TestClient,
    pipeline_mode: str | None = None,
    judge_model: str = "",
    judge_client: Any | None = None,
    schema_fusion_strategy: str = "weighted",
) -> list[EvalResult]:
    """逐条调用 `/api/query` 并收集 pass / fail / error_type。

    M21 的 fusion 仅通过此显式参数进入请求体，默认 ``weighted`` 不改变旧 eval 路径。
    """

    results: list[EvalResult] = []
    for case in cases:
        actual_pipeline_mode = pipeline_mode or case.pipeline_mode
        if _should_skip_due_to_pipeline_mode(case, actual_pipeline_mode):
            score_details = score_case_rules(
                case=case,
                body={},
                status_code=0,
                actual_pipeline_mode=actual_pipeline_mode,
            )
            score_summary = summarize_score_details(score_details)
            results.append(
                EvalResult(
                    case=case,
                    passed=score_summary.passed,
                    reason=score_summary.reason,
                    issue_tags=score_summary.issue_tags,
                    review_required=score_summary.review_required,
                    skipped_due_to_pipeline_mode=score_summary.skipped_due_to_pipeline_mode,
                    status_code=0,
                    route=None,
                    safety_status=None,
                    error_type=None,
                    trace_id=None,
                    sql=None,
                    response_body={},
                    actual_pipeline_mode=actual_pipeline_mode,
                    score_details=score_details,
                )
            )
            continue

        request_body: dict[str, Any] = {"question": case.question, "user_role": case.user_role}
        if actual_pipeline_mode != "baseline":
            request_body["force_new_pipeline"] = True
            request_body["schema_fusion_strategy"] = schema_fusion_strategy
        response = client.post(
            "/api/query",
            json=request_body,
        )
        body = response.json()
        score_details = score_case_details(
            case=case,
            body=body,
            status_code=response.status_code,
            actual_pipeline_mode=actual_pipeline_mode,
            judge_model=judge_model,
            judge_client=judge_client,
        )
        score_summary = summarize_score_details(score_details)
        results.append(
            EvalResult(
                case=case,
                passed=score_summary.passed,
                reason=score_summary.reason,
                issue_tags=score_summary.issue_tags,
                review_required=score_summary.review_required,
                skipped_due_to_pipeline_mode=score_summary.skipped_due_to_pipeline_mode,
                status_code=response.status_code,
                route=body.get("route"),
                safety_status=body.get("safety_status"),
                error_type=body.get("error_type"),
                trace_id=body.get("trace_id"),
                sql=body.get("sql"),
                response_body=body,
                actual_pipeline_mode=actual_pipeline_mode,
                score_details=score_details,
            )
        )
    return results


def _build_eval_schema_vector_index(
    *,
    pipeline_mode: str | None,
    schema_fusion_strategy: str = "weighted",
) -> tuple[VectorIndex | None, dict[str, Any]]:
    """按 M20 规则为一次 eval run 预建可复用的 Schema vector index。

    默认 `inmemory + deterministic` 不需要走这条路径；只有显式 new_text2sql + Milvus 实验才
    预建 index。这样一个 eval run 内 10/16/32 个 case 会复用同一个 Milvus collection，不再
    每个 case 重复插入同一批 schema docs。
    """

    settings = get_settings()
    runtime_metadata: dict[str, Any] = {
        "result_match_oracle_backend": "sqlite_deterministic_seed",
        "schema_vector_backend": settings.schema_vector_backend,
        "schema_embedding_provider": settings.schema_embedding_provider,
        "schema_fusion_strategy": schema_fusion_strategy,
    }
    if pipeline_mode != "new_text2sql" or settings.schema_vector_backend.lower() != "milvus":
        runtime_metadata["schema_vector_index_reuse"] = "not_applicable"
        return None, runtime_metadata

    vector_index, documents, docs_hash = build_configured_schema_vector_index(
        domain_schema=load_domain_schema(),
        schema_retrieval_profile="default",
    )
    runtime_metadata.update(
        {
            "schema_vector_index_reuse": "run_scoped",
            "schema_docs_count": len(documents),
            "schema_docs_hash": docs_hash,
            "milvus_collection": settings.milvus_collection,
            "milvus_uri": settings.milvus_uri,
            "milvus_reset_collection": settings.milvus_reset_collection,
            "milvus_dimension": getattr(vector_index, "dimension", None),
            "milvus_initial_row_count": getattr(vector_index, "initial_row_count", None),
            "milvus_inserted_document_count": getattr(vector_index, "inserted_document_count", None),
            "milvus_final_row_count": getattr(vector_index, "final_row_count", None),
            "qwen_embedding_model": settings.qwen_embedding_model,
            "qwen_embedding_dimensions": settings.qwen_embedding_dimensions,
            "siliconflow_embedding_model": settings.siliconflow_embedding_model,
            "siliconflow_embedding_dimensions": settings.siliconflow_embedding_dimensions,
        }
    )
    return vector_index, runtime_metadata


def write_report(
    results: list[EvalResult],
    path: Path = DEFAULT_REPORT_PATH,
    *,
    langfuse_score_write_result: dict[str, int] | None = None,
    triages: list[FailureTriage] | None = None,
    langfuse_triage_write_result: dict[str, int] | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> None:
    """把评测结果写成 Markdown，方便 README / dev-log / 验收报告引用。"""

    passed_count = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in results)
    skipped_count = sum(result.skipped_due_to_pipeline_mode for result in results)
    failed_count = len(results) - passed_count - skipped_count
    review_count = sum(result.review_required for result in results)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# DataPilot EvalOps-lite Latest Report",
        "",
        f"- generated_at: {generated_at}",
        f"- total: {len(results)}",
        f"- passed: {passed_count}",
        f"- failed: {failed_count}",
        f"- skipped_due_to_pipeline_mode: {skipped_count}",
        f"- review_required: {review_count}",
        "",
        "## Score Summary",
        "",
        "| case_id | name | value | passed | skipped | reason |",
        "|---|---|---:|---|---|---|",
    ]
    has_score_details = any(result.score_details for result in results)
    if has_score_details:
        for result in results:
            for detail in result.score_details:
                value = "-" if detail.value is None else detail.value
                lines.append(
                    f"| {result.case.case_id} | {detail.name} | {value} | {detail.passed} | {detail.skipped} | {detail.reason or '-'} |"
                )
    else:
        lines.append("| - | - | - | - | - | no_score_details |")
    if runtime_metadata is not None:
        lines.extend(
            [
                "",
                "## Eval Runtime Metadata",
                "",
                "| key | value |",
                "|---|---|",
            ]
        )
        for key, value in sorted(runtime_metadata.items()):
            lines.append(f"| {key} | {value} |")
    if langfuse_score_write_result is not None:
        lines.extend(
            [
                "",
                "## LangFuse Score Write",
                "",
                f"- ok: {langfuse_score_write_result.get('ok', 0)}",
                f"- skipped: {langfuse_score_write_result.get('skipped', 0)}",
                f"- failed: {langfuse_score_write_result.get('failed', 0)}",
            ]
        )
    if triages is not None:
        _append_failure_triage_summary(
            lines,
            triages=triages,
            langfuse_triage_write_result=langfuse_triage_write_result,
        )
    lines.extend(
        [
            "",
            "## Blocking Summary",
            "",
            "| group | total | passed | failed | skipped | review_required |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for label, expected_blocking in [("blocking", True), ("non_blocking", False)]:
        group = [result for result in results if result.case.phase3a_blocking is expected_blocking]
        group_passed = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in group)
        group_skipped = sum(result.skipped_due_to_pipeline_mode for result in group)
        group_failed = len(group) - group_passed - group_skipped
        group_review = sum(result.review_required for result in group)
        lines.append(f"| {label} | {len(group)} | {group_passed} | {group_failed} | {group_skipped} | {group_review} |")

    capability_names = sorted(
        {
            capability
            for result in results
            for capability in result.case.phase3a_capabilities
        }
    )
    if capability_names:
        lines.extend(
            [
                "",
                "## Capability Summary",
                "",
                "| capability | coverage | passed | failed | skipped | review_required |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for capability in capability_names:
            group = [result for result in results if capability in result.case.phase3a_capabilities]
            group_passed = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in group)
            group_skipped = sum(result.skipped_due_to_pipeline_mode for result in group)
            group_failed = len(group) - group_passed - group_skipped
            group_review = sum(result.review_required for result in group)
            lines.append(
                f"| {capability} | {len(group)} | {group_passed} | {group_failed} | {group_skipped} | {group_review} |"
            )

    lines.extend(
        [
            "",
            "## Case Summary",
            "",
            "| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |",
            "|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for result in results:
        lines.append(
            "| {id} | {type} | {passed} | {skipped} | {reason} | {issue_tags} | {review_required} | {safety} | {error_type} | {trace_id} | {source_file} | {configured_pipeline_mode} | {actual_pipeline_mode} | {blocking} | {capabilities} |".format(
                id=result.case.case_id,
                type=result.case.task_type,
                passed="yes" if result.passed else "no",
                skipped="yes" if result.skipped_due_to_pipeline_mode else "no",
                reason=result.reason,
                issue_tags=",".join(result.issue_tags) or "-",
                review_required="yes" if result.review_required else "no",
                safety=result.safety_status,
                error_type=result.error_type,
                trace_id=result.trace_id,
                source_file=result.case.source_file,
                configured_pipeline_mode=result.case.pipeline_mode,
                actual_pipeline_mode=result.actual_pipeline_mode,
                blocking="yes" if result.case.phase3a_blocking else "no",
                capabilities=",".join(result.case.phase3a_capabilities) or "-",
            )
        )
    lines.extend(["", "## Case Details", ""])
    for result in results:
        sql = result.sql or ""
        lines.extend(
            [
                f"### {result.case.case_id} {result.case.question}",
                "",
                f"- user_role: {result.case.user_role}",
                f"- source_file: {result.case.source_file}",
                f"- configured_pipeline_mode: {result.case.pipeline_mode}",
                f"- actual_pipeline_mode: {result.actual_pipeline_mode}",
                f"- phase3a_capabilities: {', '.join(result.case.phase3a_capabilities) or '-'}",
                f"- phase3a_blocking: {'yes' if result.case.phase3a_blocking else 'no'}",
                f"- case_properties: {', '.join(result.case.case_properties) or '-'}",
                f"- security_subtype: {result.case.security_subtype or '-'}",
                f"- expected_metrics: {', '.join(result.case.expected_metrics) or '-'}",
                f"- status_code: {result.status_code}",
                f"- route: {result.route}",
                f"- safety_status: {result.safety_status}",
                f"- error_type: {result.error_type}",
                f"- issue_tags: {', '.join(result.issue_tags) or '-'}",
                f"- review_required: {'yes' if result.review_required else 'no'}",
                f"- skipped_due_to_pipeline_mode: {'yes' if result.skipped_due_to_pipeline_mode else 'no'}",
                f"- trace_id: {result.trace_id}",
                f"- score_details: {_format_score_details(result.score_details)}",
                "",
                "```sql",
                sql.replace("`", ""),
                "```",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _append_failure_triage_summary(
    lines: list[str],
    *,
    triages: list[FailureTriage],
    langfuse_triage_write_result: dict[str, int] | None,
) -> None:
    """把 M19 failure triage 汇总写入 Markdown 报告。

    ★ 这里只负责展示，不做归因判断；归因单一事实源在 `eval.triage`，避免报告函数越写越胖。
    """

    summary = triage_summary(triages)
    failed_triages = [triage for triage in triages if triage.failed]
    lines.extend(
        [
            "",
            "## Failure Triage Summary",
            "",
            f"- triaged_cases: {summary['total']}",
            f"- failed_or_review_cases: {summary['failed']}",
            "",
            "### Failure Stage Counts",
            "",
            "| failure_stage | count |",
            "|---|---:|",
        ]
    )
    if summary["failure_stage_counts"]:
        for stage, count in sorted(summary["failure_stage_counts"].items()):
            lines.append(f"| {stage} | {count} |")
    else:
        lines.append("| - | 0 |")

    lines.extend(
        [
            "",
            "### Failure Subtype Counts",
            "",
            "| failure_subtype | count |",
            "|---|---:|",
        ]
    )
    if summary.get("failure_subtype_counts"):
        for subtype, count in sorted(summary["failure_subtype_counts"].items()):
            lines.append(f"| {subtype} | {count} |")
    else:
        lines.append("| - | 0 |")

    lines.extend(
        [
            "",
            "### Needs Action Counts",
            "",
            "| needs_action | count |",
            "|---|---:|",
        ]
    )
    if summary["needs_action_counts"]:
        for action, count in sorted(summary["needs_action_counts"].items()):
            lines.append(f"| {action} | {count} |")
    else:
        lines.append("| - | 0 |")

    lines.extend(
        [
            "",
            "### Top Cases",
            "",
            "| case_id | failure_stage | failure_subtype | needs_action | confidence | evidence_step | regression_candidate | reason |",
            "|---|---|---|---:|---|---|---|---|",
        ]
    )
    top_cases = summary["top_cases"]
    if top_cases:
        for item in top_cases:
            lines.append(
                "| {case_id} | {failure_stage} | {failure_subtype} | {needs_action} | {confidence} | {evidence_step} | {candidate} | {reason} |".format(
                    case_id=item["case_id"],
                    failure_stage=item["failure_stage"],
                    failure_subtype=item.get("failure_subtype") or "-",
                    needs_action=item["needs_action"],
                    confidence=item["confidence"],
                    evidence_step=item["evidence_step"],
                    candidate="yes" if item["regression_candidate"] else "no",
                    reason=item["failure_reason"],
                )
            )
    else:
        lines.append("| - | - | - | - | 0 | - | no | no_failed_cases |")

    lines.extend(
        [
            "",
            "### Case Triage Details",
            "",
            "| case_id | failed | failure_stage | failure_subtype | needs_action | evidence_step | confidence | reason |",
            "|---|---|---|---|---|---|---:|---|",
        ]
    )
    for triage in failed_triages:
        lines.append(
            "| {case_id} | yes | {stage} | {subtype} | {action} | {evidence} | {confidence} | {reason} |".format(
                case_id=triage.case_id,
                stage=triage.failure_stage,
                subtype=triage.failure_subtype or "-",
                action=triage.needs_action,
                evidence=triage.evidence_step,
                confidence=triage.confidence,
                reason=triage.failure_reason,
            )
        )
    if not failed_triages:
        lines.append("| - | no | - | - | - | - | 0 | no_failed_cases |")

    if langfuse_triage_write_result is not None:
        lines.extend(
            [
                "",
                "### LangFuse Triage Score Write",
                "",
                f"- ok: {langfuse_triage_write_result.get('ok', 0)}",
                f"- skipped: {langfuse_triage_write_result.get('skipped', 0)}",
                f"- failed: {langfuse_triage_write_result.get('failed', 0)}",
            ]
        )


def _format_score_details(details: list[EvalScoreDetail]) -> str:
    """把 scorer 明细压成一行，避免 Case Details 过度膨胀。"""

    if not details:
        return "-"
    parts = []
    for detail in details:
        value = "-" if detail.value is None else detail.value
        status = "skipped" if detail.skipped else detail.passed
        parts.append(f"{detail.name}={value}/{status}/{detail.reason or '-'}")
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    """命令行入口：加载 cases，执行 API smoke，并写入 latest.md。"""

    parser = argparse.ArgumentParser(description="Run DataPilot M6 EvalOps-lite smoke cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--extra-cases", type=Path, action="append", default=[])
    parser.add_argument("--pipeline-mode", choices=["baseline", "new_text2sql"], default=None)
    parser.add_argument(
        "--schema-fusion-strategy",
        choices=["weighted", "rrf"],
        default="weighted",
        help="M21 显式 fusion 实验；默认 weighted 保持既有 pipeline 行为。",
    )
    parser.add_argument("--judge-model", default="", help="显式启用 L3 llm:correctness；优先级高于 EVAL_JUDGE_MODEL。")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE_PATH)
    parser.add_argument("--triage-json", type=Path, default=None, help="输出 M19 failure triage JSON，供本地 A/B 分布对比。")
    parser.add_argument("--compare-triage-left", type=Path, default=None, help="本地 A/B 对比左侧 triage JSON。")
    parser.add_argument("--compare-triage-right", type=Path, default=None, help="本地 A/B 对比右侧 triage JSON。")
    parser.add_argument("--compare-triage-report", type=Path, default=None, help="本地 A/B failure distribution Markdown 输出路径。")
    args = parser.parse_args(argv)

    if args.compare_triage_left or args.compare_triage_right or args.compare_triage_report:
        if not (args.compare_triage_left and args.compare_triage_right and args.compare_triage_report):
            parser.error("--compare-triage-left/--compare-triage-right/--compare-triage-report must be used together")
        compare_triage_files(
            left_path=args.compare_triage_left,
            right_path=args.compare_triage_right,
            output_path=args.compare_triage_report,
        )
        print(f"triage_compare_report={args.compare_triage_report}")
        return 0

    cases = load_cases(args.cases, extra_cases=args.extra_cases)
    judge_model = resolve_judge_model(args.judge_model)
    schema_vector_index, runtime_metadata = _build_eval_schema_vector_index(
        pipeline_mode=args.pipeline_mode,
        schema_fusion_strategy=args.schema_fusion_strategy,
    )
    try:
        with seeded_api_client(
            args.trace,
            schema_vector_index=schema_vector_index,
            schema_vector_index_metadata=runtime_metadata,
        ) as client:
            results = run_cases(
                cases,
                client,
                pipeline_mode=args.pipeline_mode,
                judge_model=judge_model,
                schema_fusion_strategy=args.schema_fusion_strategy,
            )
    finally:
        close_index = getattr(schema_vector_index, "close", None)
        if callable(close_index):
            close_index()
    score_payloads = build_langfuse_score_payloads(results=results, trace_path=args.trace)
    score_write_result = LangFuseScoreWriter().write_scores(score_payloads)
    triages = triage_results(results, trace_path=args.trace)
    triage_payloads = build_triage_score_payloads(triages)
    triage_write_result = LangFuseScoreWriter().write_scores(triage_payloads)
    triage_write_result["skipped"] += max(0, len(triages) * 4 - len(triage_payloads))
    if args.triage_json is not None:
        write_triage_json(triages, args.triage_json)
    write_report(
        results,
        args.report,
        langfuse_score_write_result=score_write_result,
        triages=triages,
        langfuse_triage_write_result=triage_write_result,
        runtime_metadata=runtime_metadata,
    )

    passed_count = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in results)
    skipped_count = sum(result.skipped_due_to_pipeline_mode for result in results)
    print(f"report={args.report}")
    print(f"trace_path={args.trace}")
    print(f"judge_model={judge_model or '<disabled>'}")
    print(f"result_match_oracle_backend={runtime_metadata.get('result_match_oracle_backend')}")
    if runtime_metadata.get("schema_vector_index_reuse") == "run_scoped":
        print(f"schema_docs_hash={runtime_metadata.get('schema_docs_hash')}")
        print(f"milvus_collection={runtime_metadata.get('milvus_collection')}")
        print(f"milvus_final_row_count={runtime_metadata.get('milvus_final_row_count')}")
    print(
        "langfuse_scores="
        f"ok:{score_write_result['ok']} skipped:{score_write_result['skipped']} failed:{score_write_result['failed']}"
    )
    print(
        "langfuse_triage_scores="
        f"ok:{triage_write_result['ok']} skipped:{triage_write_result['skipped']} failed:{triage_write_result['failed']}"
    )
    if args.triage_json is not None:
        print(f"triage_json={args.triage_json}")
    print(f"passed={passed_count}/{len(results)}")
    print(f"skipped_due_to_pipeline_mode={skipped_count}/{len(results)}")
    for result in results:
        print(
            f"{result.case.case_id}: passed={result.passed} reason={result.reason} "
            f"issue_tags={','.join(result.issue_tags) or '-'} review_required={result.review_required} "
            f"skipped_due_to_pipeline_mode={result.skipped_due_to_pipeline_mode} "
            f"actual_pipeline_mode={result.actual_pipeline_mode} "
            f"safety={result.safety_status} "
            f"error_type={result.error_type} trace_id={result.trace_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
