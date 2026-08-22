"""离线生成 M34 Answer artifact 的 historical 兼容视图。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.rag_m34_history import import_m34_answer_history


def main() -> None:
    """验证并投影既有 M34 artifact；入口本身不构造任何 runtime。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    view = import_m34_answer_history(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(view, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
