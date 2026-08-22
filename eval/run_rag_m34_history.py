"""离线生成 M34 Answer artifact 的 historical 兼容视图。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.rag_m34_history import import_m34_answer_history, render_m34_history_report


def main() -> None:
    """验证并投影既有 M34 artifact；入口本身不构造任何 runtime。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, action="append", default=[], help="可重复提供冻结 dev/held-out retrieval artifact")
    parser.add_argument("--split-manifest", type=Path, help="冻结 60/120 split manifest")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    view = import_m34_answer_history(
        args.source,
        retrieval_paths=tuple(args.retrieval),
        split_manifest_path=args.split_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_m34_history_report(view), encoding="utf-8")
    print(json.dumps({
        "format": view["format"],
        "question_count": view["question_count"],
        "group_summaries": view["group_summaries"],
        "output": str(args.output),
        "report": str(args.report) if args.report is not None else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
