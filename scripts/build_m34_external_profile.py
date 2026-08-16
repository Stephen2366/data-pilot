"""构建/验证 M34 独立 external profile；默认只生成 candidate，不切 active pointer。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from engine.rag.enterprise_profile import (
    activate_external_profile,
    build_candidate_external_profile,
    inspect_external_profile_state,
    verify_external_profile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_RECIPE = (
    PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-dataset.json"
)


def _write_or_print(payload: object, output: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        print(rendered, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=os.environ.get("ENTERPRISE_RAG_BENCH_ROOT"),
    )
    parser.add_argument("--dataset-recipe", type=Path, default=DEFAULT_DATASET_RECIPE)
    parser.add_argument(
        "--profile-root",
        type=Path,
        help="默认使用 <dataset-root>/derived/enterprise_profiles。",
    )
    parser.add_argument("--verify-profile", help="只读验证指定 profile identity。")
    parser.add_argument("--inspect", action="store_true", help="只读查看 pointer/profile 摘要。")
    parser.add_argument(
        "--activate",
        action="store_true",
        help="构建验证后切 benchmark pointer；不会修改业务 Knowledge pointer。",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dataset_root is None:
        raise SystemExit("必须提供 --dataset-root 或 ENTERPRISE_RAG_BENCH_ROOT")
    profile_root = args.profile_root or args.dataset_root / "derived" / "enterprise_profiles"
    if args.inspect:
        _write_or_print(inspect_external_profile_state(root=profile_root), args.output)
        return
    if args.verify_profile:
        manifest = verify_external_profile(
            root=profile_root, profile_identity=args.verify_profile
        )
        _write_or_print(manifest.to_dict(), args.output)
        return

    audit = audit_enterprise_dataset(
        args.dataset_root, load_dataset_recipe(args.dataset_recipe)
    )
    manifest = build_candidate_external_profile(root=profile_root, audit=audit)
    result: dict[str, object] = {
        "operation": "build_candidate",
        "manifest": manifest.to_dict(),
        "state": inspect_external_profile_state(root=profile_root),
    }
    if args.activate:
        pointer, active = activate_external_profile(
            root=profile_root, profile_identity=manifest.profile_identity
        )
        result["operation"] = "build_and_activate"
        result["pointer"] = pointer.to_dict()
        result["manifest"] = active.to_dict()
        result["state"] = inspect_external_profile_state(root=profile_root)
    _write_or_print(result, args.output)


if __name__ == "__main__":
    main()
