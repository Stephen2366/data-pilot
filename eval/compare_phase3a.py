"""M12 新旧链路对照报告生成器。

读取 baseline trace JSONL 和新 pipeline trace JSONL，按 question 文本匹配 case，
输出结构化 Markdown 对照报告。不依赖 LLM，只做纯数据对比。

★ 设计意图：M8/M8.5 已通过 eval/run_eval.py 分别生成 baseline 和新 pipeline 的
trace JSONL；本脚本负责把两份 trace 并排对比，证明新链路在 schema 精简度、
trace 可观测性和 issue tag 归因方面的改进。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_traces(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL trace 文件，返回 trace 列表。"""

    if not path.exists():
        print(f"[compare_phase3a] WARNING: trace file not found: {path}")
        return []
    traces: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[compare_phase3a] WARNING: skip malformed JSON line in {path}")
    return traces


def _index_by_question(traces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按 question 文本建索引，重复 question 取第一条。"""

    index: dict[str, dict[str, Any]] = {}
    for trace in traces:
        question = trace.get("question", "")
        if question and question not in index:
            index[question] = trace
    return index


# 新链路专属的 trace step 名称 ============================================================
# 这些 step 在 baseline trace 中不会出现，只在新 pipeline trace 中有。
NEW_PIPELINE_STEPS = [
    "schema_retrieval",
    "schema_context",
    "join_path",
    "query_plan",
    "plan_validation",
    "sql_generation",
    "sql_guard",
    "sql_execution",
    "chart_decision",
]


def _extract_schema_context_size(trace: dict[str, Any]) -> dict[str, int]:
    """从新 pipeline trace_steps 里提取 schema_context 的表/字段/指标数量。"""

    trace_steps: list[dict[str, Any]] = trace.get("trace_steps") or []
    for step in trace_steps:
        if step.get("name") == "schema_context":
            meta = step.get("metadata") or {}
            return {
                "tables": meta.get("table_count", 0),
                "fields": meta.get("field_count", 0),
                "metrics": meta.get("metric_count", 0),
            }
    return {"tables": 0, "fields": 0, "metrics": 0}


def _extract_join_path_info(trace: dict[str, Any]) -> dict[str, Any]:
    """从新 pipeline trace_steps 里提取 join_path 信息。"""

    trace_steps: list[dict[str, Any]] = trace.get("trace_steps") or []
    for step in trace_steps:
        if step.get("name") == "join_path":
            meta = step.get("metadata") or {}
            return {
                "join_path_count": meta.get("join_path_count", 0),
                "relation_ids": meta.get("relation_ids", []),
                "relations": meta.get("relations", []),
            }
    return {"join_path_count": 0, "relation_ids": [], "relations": []}


def _extract_trace_steps_summary(trace: dict[str, Any]) -> dict[str, Any]:
    """提取 trace_steps 的完整性摘要。"""

    trace_steps: list[dict[str, Any]] = trace.get("trace_steps") or []
    step_names = [step.get("name") for step in trace_steps]
    failed_steps = [step.get("name") for step in trace_steps if step.get("status") not in ("success", "skipped")]
    return {
        "total_steps": len(trace_steps),
        "step_names": step_names,
        "failed_steps": failed_steps,
        "missing_steps": [name for name in NEW_PIPELINE_STEPS if name not in step_names],
    }


def _extract_full_schema_estimate(trace: dict[str, Any]) -> dict[str, int]:
    """从 baseline trace AgentResponse 估算全量 schema 规模。

    baseline 走模板优先或全量 schema prompt，无法精确知道 prompt 中表/字段数。
    这里用 tables_used + columns 作为"实际用时涉及的表字段"的保底估算，
    对比报告中标注为"实际使用"而非"prompt 可见"。
    """

    tables_used: list[str] = trace.get("tables_used") or []
    columns: list[str] = trace.get("columns") or []
    return {
        "tables_used": len(tables_used),
        "columns_returned": len(columns),
    }


def _classify_result(trace: dict[str, Any]) -> str:
    """把 trace 归类为 passed / blocked / error / skipped。"""

    safety = trace.get("safety_status", "")
    error_type = trace.get("error_type")
    if safety == "blocked":
        return "blocked"
    if error_type:
        return "error"
    if trace.get("route") == "sql":
        return "passed"
    return "error"


def _issue_tags_from_trace(trace: dict[str, Any]) -> list[str]:
    """从 trace 延伸分析 issue tags。

    新 pipeline trace_steps 中失败的步骤会记录 error_type，可作为 issue tag。
    """

    trace_steps: list[dict[str, Any]] = trace.get("trace_steps") or []
    tags: list[str] = []
    for step in trace_steps:
        if step.get("status") not in ("success", "skipped"):
            error_type = step.get("error_type")
            if error_type:
                tags.append(error_type)
    return tags


def _compare_tables(baseline_trace: dict[str, Any], new_trace: dict[str, Any]) -> dict[str, Any]:
    """对比两张 trace 的 tables_used。"""

    old_tables = set(baseline_trace.get("tables_used") or [])
    new_tables = set(new_trace.get("tables_used") or [])
    return {
        "old_tables": sorted(old_tables),
        "new_tables": sorted(new_tables),
        "old_count": len(old_tables),
        "new_count": len(new_tables),
        "same": old_tables == new_tables,
        "only_old": sorted(old_tables - new_tables),
        "only_new": sorted(new_tables - old_tables),
    }


def generate_comparison(
    baseline_traces: list[dict[str, Any]],
    new_traces: list[dict[str, Any]],
    report_path: Path,
) -> None:
    """生成新旧链路对照 Markdown 报告。"""

    baseline_index = _index_by_question(baseline_traces)
    new_index = _index_by_question(new_traces)

    # 找出双方共有的 question ----------------------------------------------------------------
    common_questions = sorted(set(baseline_index.keys()) & set(new_index.keys()))
    only_baseline = sorted(set(baseline_index.keys()) - set(new_index.keys()))
    only_new = sorted(set(new_index.keys()) - set(baseline_index.keys()))

    if not common_questions:
        print("[compare_phase3a] ERROR: no common questions found between baseline and new traces")
        return

    # 统计 ================================================================================
    old_passed = sum(1 for q in common_questions if _classify_result(baseline_index[q]) == "passed")
    old_blocked = sum(1 for q in common_questions if _classify_result(baseline_index[q]) == "blocked")
    old_error = sum(1 for q in common_questions if _classify_result(baseline_index[q]) == "error")
    new_passed = sum(1 for q in common_questions if _classify_result(new_index[q]) == "passed")
    new_blocked = sum(1 for q in common_questions if _classify_result(new_index[q]) == "blocked")
    new_error = sum(1 for q in common_questions if _classify_result(new_index[q]) == "error")

    # 找 2 个多表 case 展示 JoinPath -------------------------------------------------------
    multi_table_cases: list[str] = []
    for question in common_questions:
        new_trace = new_index[question]
        join_info = _extract_join_path_info(new_trace)
        if join_info["join_path_count"] > 0:
            multi_table_cases.append(question)
            if len(multi_table_cases) >= 2:
                break

    # Schema 精简度对比 --------------------------------------------------------------------
    schema_sizes: list[dict[str, Any]] = []
    for question in common_questions[:20]:  # 只取前 20 条展示
        new_trace = new_index[question]
        schema_ctx = _extract_schema_context_size(new_trace)
        baseline_trace = baseline_index[question]
        full_est = _extract_full_schema_estimate(baseline_trace)
        schema_sizes.append(
            {
                "question": question[:80],
                "new_tables": schema_ctx["tables"],
                "new_fields": schema_ctx["fields"],
                "new_metrics": schema_ctx["metrics"],
                "old_tables_used": full_est["tables_used"],
                "old_columns": full_est["columns_returned"],
            }
        )

    # Trace steps 完整性 -------------------------------------------------------------------
    trace_completeness: list[dict[str, Any]] = []
    for question in common_questions[:20]:
        new_trace = new_index[question]
        summary = _extract_trace_steps_summary(new_trace)
        trace_completeness.append(
            {
                "question": question[:80],
                "total_steps": summary["total_steps"],
                "failed_steps": summary["failed_steps"],
                "missing_steps": summary["missing_steps"],
            }
        )

    # 生成 Markdown =======================================================================
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # 标题与总览
    lines.extend(
        [
            "# Phase 3A 新旧链路对照报告",
            "",
            f"- 生成时间：{generated_at}",
            f"- 共同 case 数：{len(common_questions)}",
            f"- 仅在 baseline 中出现：{len(only_baseline)}",
            f"- 仅在新 pipeline 中出现：{len(only_new)}",
            "",
            "## 1. 通过率对比",
            "",
            "| 指标 | 旧链路 (baseline) | 新链路 (new_text2sql) | 变化 |",
            "|---|---:|---:|---|",
            f"| passed | {old_passed} | {new_passed} | {_delta_str(old_passed, new_passed)} |",
            f"| blocked | {old_blocked} | {new_blocked} | {_delta_str(old_blocked, new_blocked)} |",
            f"| error | {old_error} | {new_error} | {_delta_str(old_error, new_error)} |",
            f"| 通过率 | {old_passed}/{len(common_questions)} ({_pct(old_passed, len(common_questions))}) | {new_passed}/{len(common_questions)} ({_pct(new_passed, len(common_questions))}) | — |",
            "",
        ]
    )

    # Schema 精简度
    lines.extend(
        [
            "## 2. Schema 精简度对比",
            "",
            "新链路通过 M9 Schema Retrieval 只给 LLM 看当前问题相关的局部表/字段/指标，",
            "旧链路（模板命中时直接用模板 SQL，模板未命中时走全量 schema prompt）。",
            "下表展示新链路 `schema_context` trace step 中实际可见的规模。",
            "",
            "| question | 新链路 tables | 新链路 fields | 新链路 metrics | 旧链路 tables_used | 旧链路 columns |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in schema_sizes:
        lines.append(
            f"| {row['question']} | {row['new_tables']} | {row['new_fields']} | {row['new_metrics']} | {row['old_tables_used']} | {row['old_columns']} |"
        )

    # JoinPath 展示
    lines.extend(
        [
            "",
            "## 3. 多表 JoinPath 示例",
            "",
        ]
    )
    for question in multi_table_cases:
        new_trace = new_index[question]
        join_info = _extract_join_path_info(new_trace)
        tables_compare = _compare_tables(baseline_index[question], new_trace)
        lines.extend(
            [
                f"### {question[:100]}",
                "",
                f"- JoinPath 数量：{join_info['join_path_count']}",
                f"- 使用的 relation：{', '.join(join_info['relation_ids']) or '-'}",
                f"- relations 详情：{', '.join(join_info['relations']) or '-'}",
                f"- 旧链路 tables：{', '.join(tables_compare['old_tables']) or '-'}",
                f"- 新链路 tables：{', '.join(tables_compare['new_tables']) or '-'}",
                f"- tables 一致：{'✓' if tables_compare['same'] else '✗（仅旧：' + ', '.join(tables_compare['only_old']) + '；仅新：' + ', '.join(tables_compare['only_new']) + '）'}",
                "",
            ]
        )

    # Trace Steps 完整性
    lines.extend(
        [
            "## 4. Trace Steps 完整性",
            "",
            "新 pipeline 每次请求应包含以下 9 个 trace step。表格标出缺失或失败的步骤。",
            "",
            "| question | total_steps | failed_steps | missing_steps |",
            "|---|---|---|---|",
        ]
    )
    for row in trace_completeness:
        failed_str = ", ".join(row["failed_steps"]) or "—"
        missing_str = ", ".join(row["missing_steps"]) or "—"
        lines.append(
            f"| {row['question']} | {row['total_steps']} | {failed_str} | {missing_str} |"
        )

    # Issue Tags 对比
    lines.extend(
        [
            "",
            "## 5. Issue Tags 对比",
            "",
            "| question | 旧链路 issue_tags | 新链路 issue_tags | 旧链路 SQL 预览 | 新链路 SQL 预览 |",
            "|---|---|---|---|---|",
        ]
    )
    for question in common_questions[:30]:
        old_trace = baseline_index[question]
        new_trace = new_index[question]
        old_tags = _issue_tags_from_trace(old_trace)
        new_tags = _issue_tags_from_trace(new_trace)

        # baseline 没有 trace_steps，通过 error_type 推断
        old_error_type = old_trace.get("error_type")
        if old_error_type and not old_tags:
            old_tags = [old_error_type]

        old_sql = (old_trace.get("sql") or "")[:100]
        new_sql = (new_trace.get("sql") or "")[:100]
        lines.append(
            f"| {question[:60]} | {', '.join(old_tags) or '—'} | {', '.join(new_tags) or '—'} | {old_sql} | {new_sql} |"
        )

    # 分 case 明细
    lines.extend(
        [
            "",
            "## 6. 分 Case 明细",
            "",
            "| question | 旧链路状态 | 新链路状态 | 旧 sql_preview | 新 sql_preview | 新 trace_steps 数 |",
            "|---|---|---|---:|---:|",
        ]
    )
    for question in common_questions:
        old_trace = baseline_index[question]
        new_trace = new_index[question]
        old_status = _classify_result(old_trace)
        new_status = _classify_result(new_trace)
        old_sql = (old_trace.get("sql") or "")[:80]
        new_sql = (new_trace.get("sql") or "")[:80]
        new_steps_count = len(new_trace.get("trace_steps") or [])
        lines.append(
            f"| {question[:60]} | {old_status} | {new_status} | {old_sql} | {new_sql} | {new_steps_count} |"
        )

    # 写文件 ============================================================================
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[compare_phase3a] comparison report written to: {report_path}")


def _delta_str(old: int, new: int) -> str:
    """格式化变化量。"""

    delta = new - old
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return str(delta)
    return "0"


def _pct(numerator: int, denominator: int) -> str:
    """格式化百分比。"""

    if denominator == 0:
        return "N/A"
    return f"{numerator / denominator:.0%}"


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="Generate Phase 3A old-vs-new pipeline comparison report.")
    parser.add_argument(
        "--baseline-trace",
        type=Path,
        required=True,
        help="Path to baseline trace JSONL",
    )
    parser.add_argument(
        "--new-trace",
        type=Path,
        required=True,
        help="Path to new pipeline trace JSONL",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "eval" / "reports" / "phase3a-comparison.md",
        help="Output Markdown report path",
    )
    args = parser.parse_args(argv)

    baseline_traces = _load_traces(args.baseline_trace)
    new_traces = _load_traces(args.new_trace)

    if not baseline_traces:
        print(f"[compare_phase3a] ERROR: no traces loaded from {args.baseline_trace}")
        return 1
    if not new_traces:
        print(f"[compare_phase3a] ERROR: no traces loaded from {args.new_trace}")
        return 1

    generate_comparison(baseline_traces, new_traces, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
