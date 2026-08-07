"""M26 审计包命令入口：冻结已有 run 并可选写入人工 verdict，不发起任何 LLM 调用。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.audit import apply_audit_verdicts, build_audit_records, write_audit_json, write_audit_markdown
from eval.run_eval import CASE_CONTRACT_VERSION, PROJECT_ROOT, load_cases


def main(argv: list[str] | None = None) -> int:
    """显式要求 case/trace/report/triage/run identity，避免意外审计到另一轮运行。"""

    parser = argparse.ArgumentParser(description="Build M26 audit evidence from an existing eval run")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--extra-cases", type=Path, action="append", default=[])
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--triage", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-metadata-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--verdicts-json", type=Path)
    args = parser.parse_args(argv)

    metadata = json.loads(args.runtime_metadata_json.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("runtime metadata must be a JSON object")
    manifest, records = build_audit_records(
        cases=load_cases(args.cases, args.extra_cases),
        trace_path=args.trace,
        report_path=args.report,
        triage_path=args.triage,
        project_root=PROJECT_ROOT,
        run_id=args.run_id,
        case_contract_version=CASE_CONTRACT_VERSION,
        runtime_metadata=metadata,
    )
    if args.verdicts_json:
        verdicts = json.loads(args.verdicts_json.read_text(encoding="utf-8"))
        if not isinstance(verdicts, dict):
            raise ValueError("audit verdicts must be a JSON object keyed by case_id")
        records = apply_audit_verdicts(records, verdicts)
    write_audit_json(args.output_json, manifest=manifest, records=records)
    write_audit_markdown(args.output_report, manifest=manifest, records=records)
    print(f"audit_json={args.output_json}")
    print(f"audit_report={args.output_report}")
    print(f"audit_records={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
