"""M12 Phase 3A Text2SQL 一键 smoke 脚本。

运行顺序：
1. 新 pipeline 10 条 formal 回归 → phase3a-new-pipeline.md
2. 新 pipeline 16 条 challenge → phase3a-challenge-new-pipeline.md
3. 新 pipeline 32 条 diagnostic → phase3a-diagnostic-new-pipeline.md
4. 对照报告（formal baseline vs new）→ phase3a-comparison.md
5. 输出摘要

★ 这个脚本依赖 LLM（DeepSeek），运行前确认 API key 可用。基线报告沿用 M8/M8.5 已有文件，
不重新生成。
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = r"D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"

# 路径常量 ============================================================================
BASELINE_FORMAL_TRACE = PROJECT_ROOT / ".agent_work" / "temp" / "phase3a-baseline-traces.jsonl"
BASELINE_CHALLENGE_TRACE = PROJECT_ROOT / ".agent_work" / "temp" / "phase3a-challenge-baseline-traces.jsonl"
BASELINE_DIAGNOSTIC_TRACE = PROJECT_ROOT / ".agent_work" / "temp" / "phase3a-diagnostic-baseline-traces.jsonl"

NEW_FORMAL_REPORT = PROJECT_ROOT / "eval" / "reports" / "phase3a-new-pipeline.md"
NEW_FORMAL_TRACE = PROJECT_ROOT / ".agent_work" / "temp" / "phase3a-new-traces.jsonl"
NEW_CHALLENGE_REPORT = PROJECT_ROOT / "eval" / "reports" / "phase3a-challenge-new-pipeline.md"
NEW_CHALLENGE_TRACE = PROJECT_ROOT / ".agent_work" / "temp" / "phase3a-challenge-new-traces.jsonl"
NEW_DIAGNOSTIC_REPORT = PROJECT_ROOT / "eval" / "reports" / "phase3a-diagnostic-new-pipeline.md"
NEW_DIAGNOSTIC_TRACE = PROJECT_ROOT / ".agent_work" / "temp" / "phase3a-diagnostic-new-traces.jsonl"

COMPARISON_FORMAL = PROJECT_ROOT / "eval" / "reports" / "phase3a-comparison.md"
COMPARISON_CHALLENGE = PROJECT_ROOT / "eval" / "reports" / "phase3a-challenge-comparison.md"
COMPARISON_DIAGNOSTIC = PROJECT_ROOT / "eval" / "reports" / "phase3a-diagnostic-comparison.md"

REGRESSION_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
CHALLENGE_CASES = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
DIAGNOSTIC_EXTRA = PROJECT_ROOT / "eval" / "cases" / "phase3a-diagnostic-benchmark.yaml"

SUMMARY_PATH = PROJECT_ROOT / ".agent_work" / "temp" / "m12-smoke-summary.md"


def run_cmd(cmd: list[str], description: str) -> int:
    """运行子进程并打印状态。"""

    print(f"\n{'='*60}")
    print(f"[smoke] {description}")
    print(f"[smoke] {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"[smoke] FAILED (exit={result.returncode}): {description}")
    else:
        print(f"[smoke] OK: {description}")
    return result.returncode


def main() -> int:
    """运行 Phase 3A 全部新 pipeline 评测和对照报告。"""

    started_at = datetime.now()
    errors: list[str] = []

    # 步骤 1：新 pipeline 10 条 formal 回归 =================================================
    rc = run_cmd(
        [
            PYTHON,
            "-m",
            "eval.run_eval",
            "--pipeline-mode", "new_text2sql",
            "--cases", str(REGRESSION_CASES),
            "--report", str(NEW_FORMAL_REPORT),
            "--trace", str(NEW_FORMAL_TRACE),
        ],
        "新 pipeline 10 条 formal 回归",
    )
    if rc != 0:
        errors.append("新 pipeline formal 回归失败")

    # 步骤 2：新 pipeline 16 条 challenge ==================================================
    rc = run_cmd(
        [
            PYTHON,
            "-m",
            "eval.run_eval",
            "--pipeline-mode", "new_text2sql",
            "--cases", str(CHALLENGE_CASES),
            "--report", str(NEW_CHALLENGE_REPORT),
            "--trace", str(NEW_CHALLENGE_TRACE),
        ],
        "新 pipeline 16 条 challenge",
    )
    if rc != 0:
        errors.append("新 pipeline challenge 失败")

    # 步骤 3：新 pipeline 32 条 diagnostic =================================================
    rc = run_cmd(
        [
            PYTHON,
            "-m",
            "eval.run_eval",
            "--pipeline-mode", "new_text2sql",
            "--cases", str(CHALLENGE_CASES),
            "--extra-cases", str(DIAGNOSTIC_EXTRA),
            "--report", str(NEW_DIAGNOSTIC_REPORT),
            "--trace", str(NEW_DIAGNOSTIC_TRACE),
        ],
        "新 pipeline 32 条 diagnostic",
    )
    if rc != 0:
        errors.append("新 pipeline diagnostic 失败")

    # 步骤 4：对照报告 ===================================================================
    if BASELINE_FORMAL_TRACE.exists() and NEW_FORMAL_TRACE.exists():
        rc = run_cmd(
            [
                PYTHON,
                "-m",
                "eval.compare_phase3a",
                "--baseline-trace", str(BASELINE_FORMAL_TRACE),
                "--new-trace", str(NEW_FORMAL_TRACE),
                "--report", str(COMPARISON_FORMAL),
            ],
            "对照报告（formal 10 条）",
        )
        if rc != 0:
            errors.append("对照报告 formal 生成失败")

    if BASELINE_CHALLENGE_TRACE.exists() and NEW_CHALLENGE_TRACE.exists():
        rc = run_cmd(
            [
                PYTHON,
                "-m",
                "eval.compare_phase3a",
                "--baseline-trace", str(BASELINE_CHALLENGE_TRACE),
                "--new-trace", str(NEW_CHALLENGE_TRACE),
                "--report", str(COMPARISON_CHALLENGE),
            ],
            "对照报告（challenge 16 条）",
        )
        if rc != 0:
            errors.append("对照报告 challenge 生成失败")

    if BASELINE_DIAGNOSTIC_TRACE.exists() and NEW_DIAGNOSTIC_TRACE.exists():
        rc = run_cmd(
            [
                PYTHON,
                "-m",
                "eval.compare_phase3a",
                "--baseline-trace", str(BASELINE_DIAGNOSTIC_TRACE),
                "--new-trace", str(NEW_DIAGNOSTIC_TRACE),
                "--report", str(COMPARISON_DIAGNOSTIC),
            ],
            "对照报告（diagnostic 32 条）",
        )
        if rc != 0:
            errors.append("对照报告 diagnostic 生成失败")

    # 步骤 5：输出摘要 ===================================================================
    elapsed = (datetime.now() - started_at).total_seconds()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary_lines = [
        "# M12 Phase 3A Smoke Summary",
        "",
        f"- 运行时间：{started_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 总耗时：{elapsed:.0f}s",
        f"- 错误数：{len(errors)}",
        "",
        "## 生成文件",
        "",
        f"- formal 新链路报告：{NEW_FORMAL_REPORT}",
        f"- challenge 新链路报告：{NEW_CHALLENGE_REPORT}",
        f"- diagnostic 新链路报告：{NEW_DIAGNOSTIC_REPORT}",
        f"- formal 对照报告：{COMPARISON_FORMAL}",
        f"- challenge 对照报告：{COMPARISON_CHALLENGE}",
        f"- diagnostic 对照报告：{COMPARISON_DIAGNOSTIC}",
        "",
    ]
    if errors:
        summary_lines.extend(
            [
                "## 错误",
                "",
                *(f"- {e}" for e in errors),
                "",
            ]
        )
    else:
        summary_lines.extend(["## 全部通过 ✓", ""])
    SUMMARY_PATH.write_text("\n".join(summary_lines), encoding="utf-8")

    print(f"\n[smoke] summary → {SUMMARY_PATH}")
    print(f"[smoke] total time: {elapsed:.0f}s, errors: {len(errors)}")

    if errors:
        print("[smoke] 存在错误，请检查上述 FAILED 步骤。")
        return 1
    print("[smoke] Phase 3A smoke 全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
