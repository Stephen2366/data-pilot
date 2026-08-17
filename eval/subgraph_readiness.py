"""M39 P6 readiness audit：用已冻结的 M34 证据决定是否有资格建设 RAG Subgraph。

这个模块刻意不是一个新的 retriever，也不会重新执行 Knowledge Tool 或 AnswerFlow。它像一次
“赛后录像复盘”：只读取 M34 已完成运行留下的结构化 artifact，把 retrieval、context 和
Composer 的失败拆开。这样可以避免把“答案不够好”误判成“需要多轮 Agent 搜索”。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Mapping


ReadinessStatus = Literal["met", "not_met", "not_observed"]
FailureLayer = Literal[
    "retrieval_candidate_gap",
    "context_selection_or_packing_gap",
    "composer_support_gap",
    "provider_unavailable",
    "not_classifiable",
]

_LOGICAL_DOCUMENT_ID = re.compile(r"dsid_[0-9a-f]{32}")

# M34 已登记的五份 completed artifact 与 split 的原始文件 SHA-256。它们让 M39 的“只读
# 复盘”不仅检查 JSON 自报 identity，也能拒绝被替换或改写后的本地输入。
M34_READINESS_INPUT_SHA256 = {
    "split": "8ec4b4395b74796a9a606947f1cabf736ce8b6efb8cbdda205e7f1d647e27a95",
    "lexical_dev": "ea5022c4bf89229d2515fb71e9ff2e8ddbb162cf22178f572c57837abc56edd2",
    "lexical_held_out": "649a3899147b2e8e33486277e15aa9f327472c548784e6b55431aa4548f645e5",
    "semantic_dev": "92d72f1a4230bea8e1f4b1c89d84811b9e7b9940249e86989537293ebc371ccb",
    "semantic_held_out": "7b022f7bc0d6785c1dfaaad5bc83f02d66125984ecc0c122e20a78857c8b5957",
    "answer": "75592af855ab05993fe5593c2e90210d0f42f74b10fda18a56b3023578fd99fa",
}


class ReadinessAuditError(ValueError):
    """M34 输入不再是同一冻结基线时的失败关闭错误。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class P6Condition:
    """一项 P6 入场条件的机器可读结论，不把模糊推测伪装成通过。"""

    status: ReadinessStatus
    evidence: str
    gap: str | None = None


@dataclass(frozen=True)
class DevFailureClassification:
    """dev 单题的主失败层；只保存 question ID 和统计事实，不保存题目或正文。"""

    question_id: str
    layer: FailureLayer
    candidate_gold_count: int
    generation_visible_gold_count: int
    cited_gold_count: int
    expected_gold_count: int


@dataclass(frozen=True)
class P6ReadinessAudit:
    """★ M39 最终审计产物：输入闭合、dev 失败层和保守的 P6 结论。"""

    format: str
    split_identity: str
    profile_identity: str
    input_artifact_identities: dict[str, str]
    input_runtime_identities: dict[str, str]
    input_file_sha256: dict[str, str]
    dev_case_count: int
    held_out_case_count: int
    classifications: tuple[DevFailureClassification, ...]
    layer_counts: dict[str, int]
    conditions: dict[str, P6Condition]
    recommendation: Literal["no_go", "go_ready"]
    no_provider_call_count: int
    audit_identity: str

    def safe_projection(self) -> dict[str, Any]:
        """投影出可提交的审计结果，始终排除问题、答案、正文和完整 Evidence。"""

        return asdict(self)


@dataclass(frozen=True)
class ReadinessArtifactPaths:
    """M39 所需的六个只读输入；路径由调用者明确提供，避免隐式扫描临时目录。"""

    split: Path
    lexical_dev: Path
    lexical_held_out: Path
    semantic_dev: Path
    semantic_held_out: Path
    answer: Path


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    """读取一个既有 JSON 并返回原始文件 hash；此函数没有任何运行时 Tool 副作用。"""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ReadinessAuditError("readiness_input_missing", str(path)) from exc
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ReadinessAuditError("readiness_input_invalid", str(path)) from exc
    if not isinstance(decoded, dict):
        raise ReadinessAuditError("readiness_input_invalid", f"{path} 不是 JSON object")
    return decoded, sha256(payload).hexdigest()


def _require_string(payload: Mapping[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ReadinessAuditError("readiness_identity_missing", f"{label}.{field}")
    return value


def _require_unique_ids(payload: Mapping[str, Any], field: str, label: str) -> tuple[str, ...]:
    raw_ids = payload.get(field)
    if not isinstance(raw_ids, list) or not all(isinstance(item, str) and item for item in raw_ids):
        raise ReadinessAuditError("readiness_split_invalid", f"{label}.{field}")
    ids = tuple(raw_ids)
    if len(ids) != len(set(ids)):
        raise ReadinessAuditError("readiness_split_duplicate", f"{label}.{field}")
    return ids


def _execution_index(
    payload: Mapping[str, Any],
    *,
    label: str,
    expected_ids: set[str],
    call_field: str,
) -> dict[str, Mapping[str, Any]]:
    """校验“一题一次执行”的闭合性；不能用缺题结果拼出貌似完整的审计。"""

    executions = payload.get("executions")
    if not isinstance(executions, list):
        raise ReadinessAuditError("readiness_execution_missing", label)
    indexed: dict[str, Mapping[str, Any]] = {}
    for execution in executions:
        if not isinstance(execution, Mapping):
            raise ReadinessAuditError("readiness_execution_invalid", label)
        question_id = execution.get("question_id")
        if not isinstance(question_id, str) or question_id in indexed:
            raise ReadinessAuditError("readiness_execution_invalid", label)
        indexed[question_id] = execution
    if set(indexed) != expected_ids:
        raise ReadinessAuditError("readiness_execution_closed_world_mismatch", label)
    if payload.get("question_count") != len(expected_ids) or payload.get(call_field) != len(expected_ids):
        raise ReadinessAuditError("readiness_execution_count_mismatch", label)
    return indexed


def _validate_retrieval_artifact(
    payload: Mapping[str, Any],
    *,
    label: str,
    expected_ids: set[str],
    expected_split_name: str,
    common_identity: Mapping[str, str],
) -> dict[str, Mapping[str, Any]]:
    """验证 retrieval artifact 只属于指定 split；held-out 只在这里做身份核验。"""

    if payload.get("format") != "enterprise-rag-retrieval-eval-v1" or payload.get("status") != "completed":
        raise ReadinessAuditError("readiness_retrieval_contract_mismatch", label)
    if payload.get("split_name") != expected_split_name:
        raise ReadinessAuditError("readiness_retrieval_split_mismatch", label)
    for field, expected in common_identity.items():
        if _require_string(payload, field, label) != expected:
            raise ReadinessAuditError("readiness_identity_mismatch", f"{label}.{field}")
    return _execution_index(payload, label=label, expected_ids=expected_ids, call_field="tool_call_count")


def _retrieval_runtime_identity(payload: Mapping[str, Any], label: str) -> str:
    """冻结 retrieval 的 adapter 与 recipe；同一 split 不能混入另一种运行条件。"""

    adapter = _require_string(payload, "adapter_identity", label)
    recipe = _require_string(payload, "retrieval_recipe_identity", label)
    return f"{adapter}::{recipe}"


def _logical_document_ids(values: object) -> Counter[str]:
    """从 Evidence safe ref 取得 logical ID；不读取或保留 Document 正文。"""

    found: Counter[str] = Counter()
    if not isinstance(values, list):
        return found
    for item in values:
        if not isinstance(item, Mapping):
            continue
        authority_identity = item.get("authority_identity")
        if not isinstance(authority_identity, str):
            continue
        matched = _LOGICAL_DOCUMENT_ID.search(authority_identity)
        if matched:
            found[matched.group(0)] += 1
    return found


def _stage_document_counts(result: Mapping[str, Any]) -> dict[str, Counter[str]] | None:
    """把 M31 四阶段 ledger 还原为 document count；缺失时保持不可观察而不是猜测。"""

    ledger = result.get("ledger")
    if not isinstance(ledger, Mapping):
        return None
    evidence = ledger.get("evidence")
    stages = ledger.get("stages")
    if not isinstance(evidence, list) or not isinstance(stages, list):
        return None
    evidence_by_id: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, Mapping):
            return None
        ref = item.get("ref")
        if not isinstance(ref, Mapping) or not isinstance(ref.get("evidence_id"), str):
            return None
        evidence_by_id[ref["evidence_id"]] = ref

    stage_by_id: dict[str, str] = {}
    for item in stages:
        if not isinstance(item, Mapping):
            return None
        evidence_id = item.get("evidence_id")
        stage = item.get("stage")
        if evidence_id not in evidence_by_id or stage not in {
            "candidate",
            "selected",
            "generation_visible",
            "cited",
        }:
            return None
        stage_by_id[evidence_id] = stage
    if set(stage_by_id) != set(evidence_by_id):
        return None

    result: dict[str, Counter[str]] = {
        "candidate": Counter(),
        "selected": Counter(),
        "generation_visible": Counter(),
        "cited": Counter(),
    }
    ordered_stages = ("candidate", "selected", "generation_visible", "cited")
    for evidence_id, ref in evidence_by_id.items():
        stage = stage_by_id[evidence_id]
        authority_identity = ref.get("authority_identity")
        if not isinstance(authority_identity, str):
            return None
        matched = _LOGICAL_DOCUMENT_ID.search(authority_identity)
        if not matched:
            return None
        logical_id = matched.group(0)
        # ★ ledger 的阶段是当前最终阶段；后续阶段必然意味着之前阶段已实际经历。
        for visible_stage in ordered_stages[: ordered_stages.index(stage) + 1]:
            result[visible_stage][logical_id] += 1
    return result


def _coverage_count(expected: Counter[str], observed: Counter[str]) -> int:
    """保留 M34 duplicate logical gold 的 multiset 语义，不能偷换成 set。"""

    return sum(min(required, observed.get(logical_id, 0)) for logical_id, required in expected.items())


def _retrieval_top20_gold_count(execution: Mapping[str, Any], expected: Counter[str]) -> int | None:
    coverage = execution.get("coverage")
    if not isinstance(coverage, Mapping):
        return None
    at_twenty = coverage.get("20")
    if not isinstance(at_twenty, Mapping) or not isinstance(at_twenty.get("covered"), int):
        return None
    covered = at_twenty["covered"]
    if covered < 0 or covered > sum(expected.values()):
        return None
    return covered


def _classify_dev_execution(
    answer_execution: Mapping[str, Any], retrieval_execution: Mapping[str, Any]
) -> DevFailureClassification:
    """按最接近用户可见失败的层级做互斥归因，宁可 not_classifiable 也不猜。"""

    question_id = answer_execution.get("question_id")
    expected_raw = answer_execution.get("expected_document_ids")
    if not isinstance(question_id, str) or not isinstance(expected_raw, list):
        raise ReadinessAuditError("readiness_execution_invalid", "answer dev execution")
    if not all(isinstance(item, str) and item for item in expected_raw):
        raise ReadinessAuditError("readiness_execution_invalid", question_id)
    expected = Counter(expected_raw)
    expected_count = sum(expected.values())

    outcome = answer_execution.get("outcome")
    reason = answer_execution.get("internal_reason_code")
    result = answer_execution.get("result")
    stage_counts = _stage_document_counts(result) if isinstance(result, Mapping) else None
    candidate_count = _coverage_count(expected, stage_counts["candidate"]) if stage_counts else 0
    generation_count = _coverage_count(expected, stage_counts["generation_visible"]) if stage_counts else 0
    cited_count = _coverage_count(expected, stage_counts["cited"]) if stage_counts else 0

    # 步骤 1：外部与 Composer 失败不允许被升级成“检索需要循环”。========================
    if reason == "composer_unavailable":
        layer: FailureLayer = "provider_unavailable"
    elif outcome == "contract_rejected" and reason == "composer_output_invalid":
        layer = "composer_support_gap"
    elif not isinstance(result, Mapping) or stage_counts is None:
        layer = "not_classifiable"
    else:
        top20_count = _retrieval_top20_gold_count(retrieval_execution, expected)
        # 步骤 2：固定 @20 仍未命中时，才是候选检索漏召回；不能从最终 citation 倒推。------
        if top20_count is None:
            layer = "not_classifiable"
        elif top20_count < expected_count:
            layer = "retrieval_candidate_gap"
        # 步骤 3：@20 已有 gold 但单轮 context 没带入生成，是固定 Pipeline 的预算/packing 候选。
        elif generation_count < expected_count:
            layer = "context_selection_or_packing_gap"
        # 步骤 4：Evidence 已可见却没有形成 gold citation，属于 Composer/citation 层。------
        elif cited_count < expected_count:
            layer = "composer_support_gap"
        else:
            layer = "not_classifiable"

    return DevFailureClassification(
        question_id=question_id,
        layer=layer,
        candidate_gold_count=candidate_count,
        generation_visible_gold_count=generation_count,
        cited_gold_count=cited_count,
        expected_gold_count=expected_count,
    )


def _identity(value: Mapping[str, Any]) -> str:
    """为安全投影计算稳定身份；hash 输入已排除自身 identity 字段。"""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_p6_readiness_audit(
    *,
    split: Mapping[str, Any],
    lexical_dev: Mapping[str, Any],
    lexical_held_out: Mapping[str, Any],
    semantic_dev: Mapping[str, Any],
    semantic_held_out: Mapping[str, Any],
    answer: Mapping[str, Any],
    input_file_sha256: Mapping[str, str] | None = None,
) -> P6ReadinessAudit:
    """★ 只从已完成的 M34 JSON 构造 P6 no-go / go-ready 证据，绝不执行 RAG runtime。

    held-out 的 execution 只用于 closed-world identity 验证，分类循环严格只迭代
    ``diagnostic_dev_question_ids``。这是保护未来默认决策集的关键边界。
    """

    dev_ids = _require_unique_ids(split, "diagnostic_dev_question_ids", "split")
    held_out_ids = _require_unique_ids(split, "held_out_question_ids", "split")
    if set(dev_ids) & set(held_out_ids):
        raise ReadinessAuditError("readiness_split_overlap", "dev / held-out")
    split_identity = _require_string(split, "split_identity", "split")
    question_set_identity = _require_string(split, "question_set_identity", "split")

    if answer.get("format") != "enterprise-rag-answer-eval-v1" or answer.get("status") != "completed":
        raise ReadinessAuditError("readiness_answer_contract_mismatch", "answer")
    common_identity = {
        "dataset_identity": _require_string(answer, "dataset_identity", "answer"),
        "question_set_identity": question_set_identity,
        "split_identity": split_identity,
        "profile_identity": _require_string(answer, "profile_identity", "answer"),
    }
    for field, expected in common_identity.items():
        if _require_string(answer, field, "answer") != expected:
            raise ReadinessAuditError("readiness_identity_mismatch", f"answer.{field}")

    dev_set, held_out_set = set(dev_ids), set(held_out_ids)
    lexical_dev_index = _validate_retrieval_artifact(
        lexical_dev,
        label="lexical_dev",
        expected_ids=dev_set,
        expected_split_name="diagnostic_dev",
        common_identity=common_identity,
    )
    # ★ 以下三个输入只确认它们仍是同一冻结 M34 基线；不会读取 held-out 的逐题失败做设计。
    _validate_retrieval_artifact(
        lexical_held_out,
        label="lexical_held_out",
        expected_ids=held_out_set,
        expected_split_name="held_out",
        common_identity=common_identity,
    )
    _validate_retrieval_artifact(
        semantic_dev,
        label="semantic_dev",
        expected_ids=dev_set,
        expected_split_name="diagnostic_dev",
        common_identity=common_identity,
    )
    lexical_runtime = _retrieval_runtime_identity(lexical_dev, "lexical_dev")
    if lexical_runtime != _retrieval_runtime_identity(lexical_held_out, "lexical_held_out"):
        raise ReadinessAuditError("readiness_runtime_mismatch", "lexical dev / held-out")
    semantic_runtime = _retrieval_runtime_identity(semantic_dev, "semantic_dev")
    if semantic_runtime != _retrieval_runtime_identity(semantic_held_out, "semantic_held_out"):
        raise ReadinessAuditError("readiness_runtime_mismatch", "semantic dev / held-out")
    # Answer artifact 不携带 retrieval adapter；冻结 Composer 身份，防止把不同回答合同的
    # 失败混入本次 lexical AnswerFlow 分层。
    composer_identity = _require_string(answer, "composer_identity", "answer")
    _validate_retrieval_artifact(
        semantic_held_out,
        label="semantic_held_out",
        expected_ids=held_out_set,
        expected_split_name="held_out",
        common_identity=common_identity,
    )
    answer_index = _execution_index(
        answer,
        label="answer",
        expected_ids=dev_set | held_out_set,
        call_field="answer_flow_call_count",
    )

    classifications = tuple(
        _classify_dev_execution(answer_index[question_id], lexical_dev_index[question_id])
        for question_id in sorted(dev_ids)
    )
    layer_counts = dict(sorted(Counter(item.layer for item in classifications).items()))

    stable_failure_count = sum(
        count
        for layer, count in layer_counts.items()
        if layer in {"retrieval_candidate_gap", "context_selection_or_packing_gap"}
    )
    conditions = {
        "reproducible_non_provider_failure_cluster": P6Condition(
            status="met" if stable_failure_count else "not_met",
            evidence=f"dev 中有 {stable_failure_count} 个 retrieval/context 主层 Scenario",
            gap=None if stable_failure_count else "没有可复核的 retrieval/context 失败 cohort",
        ),
        "observation_driven_new_evidence_action": P6Condition(
            status="not_met",
            evidence="现有 artifact 只记录一次固定 retrieval，没有任何第二动作的新增 Evidence 证据",
            gap="尚未验证由首次 Observation 选择、且能新增 Evidence 的允许动作",
        ),
        "dev_and_unpolluted_held_out_protocol": P6Condition(
            status="met",
            evidence="60/120 split 闭合；本审计只分类 dev，held-out 只做 identity 校验",
        ),
        "comparable_extra_budget": P6Condition(
            status="not_met",
            evidence="已有单轮 latency/call/token 基线，但没有第二动作或父子预算定义",
            gap="无法比较额外调用、延迟、出站与调试成本",
        ),
    }
    recommendation: Literal["no_go", "go_ready"] = (
        "go_ready" if all(condition.status == "met" for condition in conditions.values()) else "no_go"
    )
    artifact_identities = {
        "lexical_dev": _require_string(lexical_dev, "artifact_identity", "lexical_dev"),
        "lexical_held_out": _require_string(lexical_held_out, "artifact_identity", "lexical_held_out"),
        "semantic_dev": _require_string(semantic_dev, "artifact_identity", "semantic_dev"),
        "semantic_held_out": _require_string(semantic_held_out, "artifact_identity", "semantic_held_out"),
        "answer": _require_string(answer, "artifact_identity", "answer"),
    }
    runtime_identities = {
        "lexical_retrieval": lexical_runtime,
        "semantic_retrieval": semantic_runtime,
        "answer_composer": composer_identity,
    }
    unsigned = {
        "format": "phase4-rag-subgraph-readiness-v1",
        "split_identity": split_identity,
        "profile_identity": common_identity["profile_identity"],
        "input_artifact_identities": artifact_identities,
        "input_runtime_identities": runtime_identities,
        "input_file_sha256": dict(sorted((input_file_sha256 or {}).items())),
        "dev_case_count": len(dev_ids),
        "held_out_case_count": len(held_out_ids),
        "classifications": [asdict(item) for item in classifications],
        "layer_counts": layer_counts,
        "conditions": {key: asdict(value) for key, value in conditions.items()},
        "recommendation": recommendation,
        "no_provider_call_count": 0,
    }
    return P6ReadinessAudit(
        format=unsigned["format"],
        split_identity=split_identity,
        profile_identity=common_identity["profile_identity"],
        input_artifact_identities=artifact_identities,
        input_runtime_identities=runtime_identities,
        input_file_sha256=dict(sorted((input_file_sha256 or {}).items())),
        dev_case_count=len(dev_ids),
        held_out_case_count=len(held_out_ids),
        classifications=classifications,
        layer_counts=layer_counts,
        conditions=conditions,
        recommendation=recommendation,
        no_provider_call_count=0,
        audit_identity=_identity(unsigned),
    )


def audit_paths(
    paths: ReadinessArtifactPaths,
    *,
    expected_file_sha256: Mapping[str, str] = M34_READINESS_INPUT_SHA256,
) -> P6ReadinessAudit:
    """从明确的只读路径加载全部输入，并拒绝与已登记 M34 hash 不一致的文件。"""

    sources = {
        "split": paths.split,
        "lexical_dev": paths.lexical_dev,
        "lexical_held_out": paths.lexical_held_out,
        "semantic_dev": paths.semantic_dev,
        "semantic_held_out": paths.semantic_held_out,
        "answer": paths.answer,
    }
    loaded = {label: _read_json(path) for label, path in sources.items()}
    if set(expected_file_sha256) != set(sources):
        raise ReadinessAuditError("readiness_hash_spec_invalid", "expected input labels")
    for label, (_payload, actual_hash) in loaded.items():
        if expected_file_sha256[label] != actual_hash:
            raise ReadinessAuditError("readiness_file_hash_mismatch", label)
    return build_p6_readiness_audit(
        split=loaded["split"][0],
        lexical_dev=loaded["lexical_dev"][0],
        lexical_held_out=loaded["lexical_held_out"][0],
        semantic_dev=loaded["semantic_dev"][0],
        semantic_held_out=loaded["semantic_held_out"][0],
        answer=loaded["answer"][0],
        input_file_sha256={label: digest for label, (_payload, digest) in loaded.items()},
    )


def render_readiness_markdown(audit: P6ReadinessAudit) -> str:
    """渲染只含统计和身份的阅读版报告，故意不输出 dev question ID 或 Evidence identity。"""

    lines = [
        "# M39 P6 RAG Subgraph Readiness Audit",
        "",
        "> 本报告只复盘已完成的 M34 artifact；没有调用 Knowledge Tool、AnswerFlow 或外部 provider。",
        "",
        "## 输入闭合",
        "",
        f"- audit identity: `{audit.audit_identity}`",
        f"- split identity: `{audit.split_identity}`",
        f"- profile identity: `{audit.profile_identity}`",
        f"- lexical retrieval: `{audit.input_runtime_identities['lexical_retrieval']}`",
        f"- semantic retrieval: `{audit.input_runtime_identities['semantic_retrieval']}`",
        f"- answer Composer: `{audit.input_runtime_identities['answer_composer']}`",
        f"- dev / held-out: `{audit.dev_case_count} / {audit.held_out_case_count}`",
        f"- provider calls: `{audit.no_provider_call_count}`",
        "",
        "## Dev failure taxonomy",
        "",
        "| 主层 | Scenario 数 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{layer}` | {count} |" for layer, count in sorted(audit.layer_counts.items()))
    lines.extend(
        [
            "",
            "## P6 entrance conditions",
            "",
            "| 条件 | 结论 | 证据 / 缺口 |",
            "| --- | --- | --- |",
        ]
    )
    for name, condition in audit.conditions.items():
        detail = condition.evidence if condition.gap is None else f"{condition.evidence}；缺口：{condition.gap}"
        lines.append(f"| `{name}` | `{condition.status}` | {detail} |")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- recommendation: `{audit.recommendation}`",
            "- `no_go` 表示当前保持确定性 lexical Pipeline 默认；它不等于永不优化 RAG。",
            "- 只有新的 dev 证据证明 Observation 驱动动作能新增 Evidence，并冻结可比预算和未污染 held-out 后，才能另行规划 M40。",
            "",
        ]
    )
    return "\n".join(lines)
