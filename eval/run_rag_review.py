"""生成、校验或合并 M41 RAG 人工 review bundle。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.rag_e2e_review import apply_verdicts, build_review_bundle, verify_review_sources


def main() -> None:
    """按参数生成/校验 bundle，或把闭集人工 verdict 合并为旁路结果。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--reviewer", default="human")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--verdicts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.bundle:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    elif args.artifact and args.checkpoint_dir:
        bundle = build_review_bundle(artifact_path=args.artifact, checkpoint_root=args.checkpoint_dir, reviewer=args.reviewer)
    else:
        parser.error("需提供 --bundle，或同时提供 --artifact/--checkpoint-dir")
    verified = verify_review_sources(bundle)
    if args.verdicts and not args.verify_only:
        verdicts = json.loads(args.verdicts.read_text(encoding="utf-8"))
        bundle = apply_verdicts(bundle, verdicts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "verified", **verified, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
