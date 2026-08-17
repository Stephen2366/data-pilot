"""M39：P6 readiness audit 只能复盘 M34 证据，不能启动新的 RAG 运行。"""

from __future__ import annotations

from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp

import pytest

from eval.subgraph_readiness import (
    ReadinessArtifactPaths,
    ReadinessAuditError,
    audit_paths,
    build_p6_readiness_audit,
    render_readiness_markdown,
)


_DATASET = "dataset-1"
_QUESTION_SET = "questions-1"
_SPLIT = "split-1"
_PROFILE = "profile-1"


def _retrieval_execution(question_id: str, expected_document_id: str, covered: int) -> dict:
    """构造最小 retrieval evidence；@20 覆盖是 M39 区分候选与 context 层的唯一输入。"""

    return {
        "question_id": question_id,
        "expected_document_ids": [expected_document_id],
        "coverage": {"20": {"covered": covered}},
    }


def _retrieval_artifact(*, split_name: str, executions: list[dict], identity: str) -> dict:
    return {
        "format": "enterprise-rag-retrieval-eval-v1",
        "status": "completed",
        "split_name": split_name,
        "dataset_identity": _DATASET,
        "question_set_identity": _QUESTION_SET,
        "split_identity": _SPLIT,
        "profile_identity": _PROFILE,
        "adapter_identity": "adapter-1",
        "retrieval_recipe_identity": "recipe-1",
        "question_count": len(executions),
        "tool_call_count": len(executions),
        "artifact_identity": identity,
        "executions": executions,
    }


def _ledger(*, logical_document_id: str, stage: str) -> dict:
    evidence_id = f"evidence-{logical_document_id}"
    return {
        "evidence": [
            {
                "ref": {
                    "evidence_id": evidence_id,
                    "authority_identity": f"enterprise/synthetic/{logical_document_id}#anchor",
                }
            }
        ],
        "stages": [{"evidence_id": evidence_id, "stage": stage}],
    }


def _answer_execution(
    question_id: str,
    expected_document_id: str,
    *,
    stage: str = "candidate",
    outcome: str = "answer_result",
    reason: str = "answer_completed",
    include_result: bool = True,
) -> dict:
    result = {"ledger": _ledger(logical_document_id=expected_document_id, stage=stage)} if include_result else None
    return {
        "question_id": question_id,
        "expected_document_ids": [expected_document_id],
        "outcome": outcome,
        "internal_reason_code": reason,
        "result": result,
    }


def _inputs() -> dict:
    split = {
        "diagnostic_dev_question_ids": ["q-dev-retrieval", "q-dev-context"],
        "held_out_question_ids": ["q-held"],
        "question_set_identity": _QUESTION_SET,
        "split_identity": _SPLIT,
    }
    lexical_dev = _retrieval_artifact(
        split_name="diagnostic_dev",
        identity="lexical-dev",
        executions=[
            _retrieval_execution("q-dev-retrieval", "dsid_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 0),
            _retrieval_execution("q-dev-context", "dsid_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", 1),
        ],
    )
    lexical_held_out = _retrieval_artifact(
        split_name="held_out",
        identity="lexical-held",
        executions=[_retrieval_execution("q-held", "dsid_cccccccccccccccccccccccccccccccc", 1)],
    )
    semantic_dev = deepcopy(lexical_dev)
    semantic_dev["artifact_identity"] = "semantic-dev"
    semantic_held_out = deepcopy(lexical_held_out)
    semantic_held_out["artifact_identity"] = "semantic-held"
    answer_executions = [
        _answer_execution("q-dev-retrieval", "dsid_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        _answer_execution("q-dev-context", "dsid_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", stage="selected"),
        _answer_execution("q-held", "dsid_cccccccccccccccccccccccccccccccc", stage="cited"),
    ]
    answer = {
        "format": "enterprise-rag-answer-eval-v1",
        "status": "completed",
        "dataset_identity": _DATASET,
        "question_set_identity": _QUESTION_SET,
        "split_identity": _SPLIT,
        "profile_identity": _PROFILE,
        "composer_identity": "composer-1",
        "question_count": len(answer_executions),
        "answer_flow_call_count": len(answer_executions),
        "artifact_identity": "answer-all",
        "executions": answer_executions,
    }
    return {
        "split": split,
        "lexical_dev": lexical_dev,
        "lexical_held_out": lexical_held_out,
        "semantic_dev": semantic_dev,
        "semantic_held_out": semantic_held_out,
        "answer": answer,
    }


def test_audit_keeps_held_out_out_of_dev_taxonomy_and_recommends_no_go() -> None:
    """即使 answer artifact 包含全部 180 题形状，公开 taxonomy 也只能含 dev IDs。"""

    audit = build_p6_readiness_audit(**_inputs(), input_file_sha256={"answer": "sha-answer"})

    assert [item.question_id for item in audit.classifications] == ["q-dev-context", "q-dev-retrieval"]
    assert audit.layer_counts == {
        "context_selection_or_packing_gap": 1,
        "retrieval_candidate_gap": 1,
    }
    assert audit.conditions["reproducible_non_provider_failure_cluster"].status == "met"
    assert audit.conditions["observation_driven_new_evidence_action"].status == "not_met"
    assert audit.conditions["comparable_extra_budget"].status == "not_met"
    assert audit.recommendation == "no_go"
    assert audit.no_provider_call_count == 0
    report = render_readiness_markdown(audit)
    assert "q-dev" not in report
    assert "dsid_" not in report


def test_composer_unavailable_never_becomes_retrieval_loop_evidence() -> None:
    """外部 Composer 故障是 provider 问题，不能为 Subgraph 制造虚假的失败 cohort。"""

    inputs = _inputs()
    inputs["answer"]["executions"][0] = _answer_execution(
        "q-dev-retrieval",
        "dsid_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        outcome="answer_result",
        reason="composer_unavailable",
        include_result=False,
    )
    audit = build_p6_readiness_audit(**inputs)

    layers = {item.question_id: item.layer for item in audit.classifications}
    assert layers["q-dev-retrieval"] == "provider_unavailable"


def test_identity_or_split_mismatch_fails_closed_instead_of_producing_no_go() -> None:
    """缺失或错分集的 artifact 不能被拿来支持任何路线结论。"""

    inputs = _inputs()
    inputs["lexical_held_out"]["split_name"] = "diagnostic_dev"

    with pytest.raises(ReadinessAuditError, match="readiness_retrieval_split_mismatch"):
        build_p6_readiness_audit(**inputs)


def test_retrieval_runtime_mismatch_fails_closed() -> None:
    """同一 lexical 基线若换了 adapter / recipe，就不再是可比的 M34 输入。"""

    inputs = _inputs()
    inputs["lexical_held_out"]["adapter_identity"] = "another-adapter"

    with pytest.raises(ReadinessAuditError, match="readiness_runtime_mismatch"):
        build_p6_readiness_audit(**inputs)


def test_file_hash_mismatch_fails_closed_before_audit() -> None:
    """文件内容被替换时，即使 JSON 仍然可解析，也不能沿用 M34 的路线结论。"""

    # Windows 上 pytest 的 ``tmp_path`` 收尾有时会被文件索引器短暂占用；
    # 使用项目约定的临时目录，避免把平台清理噪声误报成审计逻辑失败。
    temp_dir = Path(mkdtemp(prefix="m39-readiness-", dir=".agent_work/temp"))
    paths: dict[str, Path] = {}
    expected_hashes: dict[str, str] = {}
    for label, payload in _inputs().items():
        path = temp_dir / f"{label}.json"
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        path.write_bytes(encoded)
        paths[label] = path
        expected_hashes[label] = sha256(encoded).hexdigest()
    expected_hashes["answer"] = "0" * 64

    with pytest.raises(ReadinessAuditError, match="readiness_file_hash_mismatch"):
        audit_paths(ReadinessArtifactPaths(**paths), expected_file_sha256=expected_hashes)
