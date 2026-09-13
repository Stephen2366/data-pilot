"""P1-C3 Hidden companion CLI：prepare 零调用，execute 必须重读冻结请求。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.evoloop_hidden_executor import (
    DataPilotHiddenRuntime,
    HiddenPrivateStore,
    build_development_offer,
    build_execution_request,
    execute_hidden_baseline,
    validate_development_fixture,
    validate_ordinary_completion,
)
from eval.evoloop_hidden_material import build_public_offer, load_hidden_material


def main(argv: list[str] | None = None) -> int:
    """提供 prepare / execute / inspect 三个显式阶段，禁止隐式启动 provider。"""

    parser = argparse.ArgumentParser(description="Run trusted EvoLoop Hidden Baseline side")
    parser.add_argument("action", choices=("prepare", "execute", "inspect"))
    parser.add_argument("--material", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--purpose", choices=("development_probe", "formal_baseline"))
    parser.add_argument("--candidate-digest")
    parser.add_argument("--authorization-digest")
    parser.add_argument("--runtime-digest")
    parser.add_argument("--scorer-digest")
    parser.add_argument("--oracle-digest")
    args = parser.parse_args(argv)

    store = HiddenPrivateStore(args.output_root)
    if args.action == "prepare":
        required = (
            args.run_id, args.purpose, args.candidate_digest, args.authorization_digest,
            args.runtime_digest, args.scorer_digest, args.oracle_digest,
        )
        if not all(required) or args.request.exists():
            parser.error("prepare requires a fresh request path and all frozen identities")
        if args.purpose == "development_probe":
            material = validate_development_fixture(json.loads(args.material.read_text(encoding="utf-8")))
            offer = build_development_offer(material)
        else:
            material = load_hidden_material(args.material)
            offer = build_public_offer(material)
        request = build_execution_request(
            run_id=args.run_id,
            purpose=args.purpose,
            offer=offer,
            candidate_digest=args.candidate_digest,
            authorization_digest=args.authorization_digest,
            world={
                "runtime_digest": args.runtime_digest,
                "scorer_digest": args.scorer_digest,
                "oracle_digest": args.oracle_digest,
            },
            budget=(
                {"max_logical_works": 1, "max_physical_requests": 2, "max_observed_tokens": 12000, "max_wall_seconds": 300}
                if args.purpose == "development_probe"
                else {"max_logical_works": 4, "max_physical_requests": 8, "max_observed_tokens": 100000, "max_wall_seconds": 1200}
            ),
            model={"provider": "qwen", "model": "qwen3.7-plus", "temperature": 0, "retry": 0},
        )
        HiddenPrivateStore.create(args.output_root, request)
        args.request.parent.mkdir(parents=True, exist_ok=True)
        args.request.write_text(json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"state": "prepared", "request_digest": request["digest"]}, sort_keys=True))
        return 0

    request = json.loads(args.request.read_text(encoding="utf-8"))
    purpose = request.get("payload", {}).get("purpose")
    material = (
        validate_development_fixture(json.loads(args.material.read_text(encoding="utf-8")))
        if purpose == "development_probe"
        else load_hidden_material(args.material)
    )
    if args.action == "execute":
        completion = execute_hidden_baseline(
            material_value=material,
            request=request,
            store=store,
            executor=DataPilotHiddenRuntime(trace_root=args.output_root / "private" / "traces"),
        )
    else:
        completion = json.loads(store.completion_path.read_text(encoding="utf-8"))
        validate_ordinary_completion(completion, expected_request_digest=request["digest"])
    print(json.dumps(completion, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
