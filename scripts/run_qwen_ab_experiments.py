"""Qwen / DeepSeek 与 embedding provider A/B 实验脚本。

本脚本只负责实验，不改变项目默认配置：
1. 主模型 A/B：DeepSeek vs Qwen，固定默认 schema retrieval。
2. Embedding A/B：SiliconFlow BGE-M3 vs DashScope Qwen embedding，固定主模型。

输出统一放到 `.agent_work/temp/qwen-ab/`，避免覆盖 Phase 3A 正式报告。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = r"D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"
OUTPUT_DIR = PROJECT_ROOT / ".agent_work" / "temp" / "qwen-ab"

REGRESSION_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
CHALLENGE_CASES = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
DIAGNOSTIC_EXTRA = PROJECT_ROOT / "eval" / "cases" / "phase3a-diagnostic-benchmark.yaml"


@dataclass(frozen=True)
class EvalSuite:
    """一组 eval 输入，formal/challenge/diagnostic 共享同一 runner。"""

    name: str
    cases: Path
    extra_cases: Path | None = None


@dataclass(frozen=True)
class Experiment:
    """一次 A/B 实验配置。"""

    name: str
    description: str
    env: dict[str, str]
    suites: tuple[str, ...]


SUITES = {
    "formal": EvalSuite(name="formal", cases=REGRESSION_CASES),
    "challenge": EvalSuite(name="challenge", cases=CHALLENGE_CASES),
    "diagnostic": EvalSuite(name="diagnostic", cases=CHALLENGE_CASES, extra_cases=DIAGNOSTIC_EXTRA),
}


def _load_dotenv(path: Path) -> dict[str, str]:
    """读取简单 KEY=VALUE `.env`，只供子进程实验使用。"""

    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _base_env() -> dict[str, str]:
    """合并当前进程环境与 `.env`，让脚本能读取用户本地 API key。"""

    merged = os.environ.copy()
    merged.update(_load_dotenv(PROJECT_ROOT / ".env"))
    return merged


def _experiments(selected: str) -> list[Experiment]:
    """按用户选择返回实验矩阵。"""

    main_model = [
        Experiment(
            name="main-deepseek",
            description="主模型 DeepSeek，默认 in-memory deterministic schema retrieval",
            env={
                "LLM_PROVIDER": "deepseek",
                "SCHEMA_VECTOR_BACKEND": "inmemory",
                "SCHEMA_EMBEDDING_PROVIDER": "deterministic",
            },
            suites=("formal", "challenge", "diagnostic"),
        ),
        Experiment(
            name="main-qwen37-plus",
            description="主模型 Qwen qwen3.7-plus，默认 in-memory deterministic schema retrieval",
            env={
                "LLM_PROVIDER": "qwen",
                "QWEN_MODEL": "qwen3.7-plus",
                "SCHEMA_VECTOR_BACKEND": "inmemory",
                "SCHEMA_EMBEDDING_PROVIDER": "deterministic",
            },
            suites=("formal", "challenge", "diagnostic"),
        ),
    ]
    embedding = [
        Experiment(
            name="embedding-siliconflow-bge-m3",
            description="主模型 DeepSeek，Milvus + SiliconFlow BAAI/bge-m3 embedding",
            env={
                "LLM_PROVIDER": "deepseek",
                "SCHEMA_VECTOR_BACKEND": "milvus",
                "SCHEMA_EMBEDDING_PROVIDER": "siliconflow",
                "SILICONFLOW_EMBEDDING_MODEL": "BAAI/bge-m3",
            },
            suites=("formal", "challenge", "diagnostic"),
        ),
        Experiment(
            name="embedding-qwen37",
            description="主模型 DeepSeek，Milvus + DashScope qwen3.7-text-embedding",
            env={
                "LLM_PROVIDER": "deepseek",
                "SCHEMA_VECTOR_BACKEND": "milvus",
                "SCHEMA_EMBEDDING_PROVIDER": "dashscope",
                "QWEN_EMBEDDING_MODEL": "qwen3.7-text-embedding",
                "QWEN_EMBEDDING_DIMENSIONS": "1024",
            },
            suites=("formal", "challenge", "diagnostic"),
        ),
    ]
    if selected == "main":
        return main_model
    if selected == "embedding":
        return embedding
    return main_model + embedding


def _run_eval(experiment: Experiment, suite: EvalSuite, env: dict[str, str]) -> tuple[int, Path, Path]:
    """运行单个 eval suite，并返回退出码与输出路径。"""

    report = OUTPUT_DIR / f"{experiment.name}-{suite.name}.md"
    trace = OUTPUT_DIR / f"{experiment.name}-{suite.name}-traces.jsonl"
    cmd = [
        PYTHON,
        "-m",
        "eval.run_eval",
        "--pipeline-mode",
        "new_text2sql",
        "--cases",
        str(suite.cases),
        "--report",
        str(report),
        "--trace",
        str(trace),
    ]
    if suite.extra_cases is not None:
        cmd.extend(["--extra-cases", str(suite.extra_cases)])

    print(f"[ab] {experiment.name} / {suite.name}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return result.returncode, report, trace


def _parse_score(report: Path) -> str:
    """从 Markdown 报告头部提取 passed/total。"""

    if not report.exists():
        return "missing"
    text = report.read_text(encoding="utf-8")
    total = re.search(r"^- total: (\d+)", text, flags=re.MULTILINE)
    passed = re.search(r"^- passed: (\d+)", text, flags=re.MULTILINE)
    failed = re.search(r"^- failed: (\d+)", text, flags=re.MULTILINE)
    if not total or not passed or not failed:
        return "unknown"
    return f"{passed.group(1)}/{total.group(1)} failed={failed.group(1)}"


def main() -> int:
    """运行 A/B 实验入口。"""

    parser = argparse.ArgumentParser(description="Run DataPilot Qwen A/B experiments.")
    parser.add_argument(
        "--group",
        choices=["main", "embedding", "all"],
        default="main",
        help="默认先跑主模型 A/B；embedding 组需要本地 Milvus 可用。",
    )
    parser.add_argument(
        "--experiment",
        action="append",
        default=None,
        help="只运行指定 experiment name；可重复传入，例如 --experiment main-qwen37-plus。",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUITES),
        default=None,
        help="只运行指定 suite；可重复传入，例如 --suite formal --suite challenge。",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now()
    base_env = _base_env()
    summary: list[tuple[str, str, int, Path, Path]] = []

    selected_experiments = set(args.experiment or [])
    selected_suites = set(args.suite or SUITES)

    for experiment in _experiments(args.group):
        if selected_experiments and experiment.name not in selected_experiments:
            continue
        env = base_env.copy()
        env.update(experiment.env)
        for suite_name in experiment.suites:
            if suite_name not in selected_suites:
                continue
            rc, report, trace = _run_eval(experiment, SUITES[suite_name], env)
            summary.append((experiment.name, suite_name, rc, report, trace))

    summary_path = OUTPUT_DIR / f"summary-{started_at.strftime('%Y%m%d-%H%M%S')}.md"
    lines = [
        "# Qwen A/B Experiment Summary",
        "",
        f"- generated_at: {started_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- group: {args.group}",
        "",
        "| experiment | suite | exit | score | report | trace |",
        "|---|---|---:|---|---|---|",
    ]
    for experiment_name, suite_name, rc, report, trace in summary:
        lines.append(
            f"| {experiment_name} | {suite_name} | {rc} | {_parse_score(report)} | {report} | {trace} |"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ab] summary -> {summary_path}")
    return 1 if any(rc != 0 for _, _, rc, _, _ in summary) else 0


if __name__ == "__main__":
    raise SystemExit(main())
