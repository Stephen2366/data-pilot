"""M40：从已验证的五路径 rehearsal 生成 P7 assurance JSON 与 Markdown 报告。

这是纯本地、确定性的收口入口：它不会请求真实模型、重跑 M34，也不会把 M39 no-go
改写为质量通过。调用者先用 API rehearsal 生成安全 C2 JSON，再把其交给此脚本。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.phase4_assurance import (
    rehearsal_artifact_from_json,
    render_assurance_markdown,
    run_phase4_assurance,
)


def main() -> None:
    """读取 C2 JSON，运行当前 deterministic families，并写出同源 P7 报告。"""

    parser = argparse.ArgumentParser(description="生成 M40 P7 technical assurance report")
    parser.add_argument("--rehearsal", type=Path, required=True, help="五路径 Trace rehearsal JSON")
    parser.add_argument("--output", type=Path, required=True, help="assurance JSON 输出路径")
    parser.add_argument("--report", type=Path, required=True, help="assurance Markdown 输出路径")
    parser.add_argument(
        "--m39-audit", type=Path, default=Path("eval/reports/m39-p6-readiness.json"),
        help="冻结的 M39 P6 audit JSON（默认项目事实源）",
    )
    args = parser.parse_args()

    rehearsal = rehearsal_artifact_from_json(json.loads(args.rehearsal.read_text(encoding="utf-8")))
    artifact = run_phase4_assurance(
        root=args.output.parent / "m40-assurance-work",
        rehearsal=rehearsal,
        m39_audit_path=args.m39_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({**artifact.unsigned_payload(), "artifact_identity": artifact.artifact_identity}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report.write_text(render_assurance_markdown(artifact), encoding="utf-8")


if __name__ == "__main__":
    main()
