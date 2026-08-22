"""严格比较两个 completed M41 RAG Eval artifact。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.rag_e2e_review import compare_completed


def main() -> None:
    """加载两个 artifact，完成严格可比性检查后写出 JSON 对照。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-runtime-difference",
        action="append",
        default=[],
        help="显式允许变化的 RAGResolvedRuntime 字段；可重复。未声明的漂移继续拒绝。",
    )
    args = parser.parse_args()
    result = compare_completed(
        json.loads(args.left.read_text(encoding="utf-8")),
        json.loads(args.right.read_text(encoding="utf-8")),
        allowed_runtime_differences=tuple(args.allow_runtime_difference),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
