"""M39 的只读 CLI：将既有 M34 artifact 投影为 P6 readiness JSON，不调用任何 provider。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 直接执行 scripts/ 下文件时，Python 只把 scripts 加到模块搜索路径；显式补回项目根，
# 才能导入同仓库的 eval 包。这个 shim 不改变审计输入，也不会触发任何运行时 RAG 调用。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.subgraph_readiness import ReadinessArtifactPaths, audit_paths, render_readiness_markdown


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读审计 M34 evidence，判断 P6 RAG Subgraph readiness")
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--lexical-dev", type=Path, required=True)
    parser.add_argument("--lexical-held-out", type=Path, required=True)
    parser.add_argument("--semantic-dev", type=Path, required=True)
    parser.add_argument("--semantic-held-out", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="可选的脱敏 Markdown 阅读版报告")
    return parser


def main() -> int:
    """显式读取六份历史 JSON 并写出安全审计；不创建 external runtime 或模型客户端。"""

    args = _parser().parse_args()
    audit = audit_paths(
        ReadinessArtifactPaths(
            split=args.split,
            lexical_dev=args.lexical_dev,
            lexical_held_out=args.lexical_held_out,
            semantic_dev=args.semantic_dev,
            semantic_held_out=args.semantic_held_out,
            answer=args.answer,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit.safe_projection(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_readiness_markdown(audit), encoding="utf-8")
    print(f"recommendation={audit.recommendation}")
    print(f"audit_identity={audit.audit_identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
