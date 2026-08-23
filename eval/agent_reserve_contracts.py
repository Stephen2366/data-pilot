"""M42-E：sealed decision reserve、污染账本与外部 artifact 对账。

仓库只保存安全 manifest；60 题正文、gold 和访问账本位于项目外 immutable store。这个模块
把“全局有一份 reserve”和“当前开发允许看到逐题内容”分开：默认 interface 只验证身份，
只有创建/封存阶段显式调用 ``seal_reserve`` 才读取逐题材料。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from engine.phase4b.identity import canonical_hash, file_sha256

RESERVE_SCHEMA = "phase4b-agent-decision-reserve-v1"
EXPECTED_DISTRIBUTION = {"basic": 20, "core": 20, "hard": 20}


class ReserveContractError(ValueError):
    """reserve 数量、去重、gold、hash 或访问状态不闭合。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class ReserveManifest:
    """仓库可安全保存的 reserve 摘要；不含题面、gold 或正文。"""

    schema_version: str
    reserve_identity: str
    corpus_identity: str
    profile_identity: str
    question_count: int
    distribution: Mapping[str, int]
    multi_document_counts: Mapping[str, int]
    files: Mapping[str, str]
    decision_status: Literal["sealed", "unsealed", "retired"]
    first_unseal_module: str
    historical_regression_identity: str

    def payload(self) -> dict[str, Any]:
        """返回可落库的安全 manifest，不携带外部路径或逐题材料。"""

        return {
            "schema_version": self.schema_version,
            "reserve_identity": self.reserve_identity,
            "corpus_identity": self.corpus_identity,
            "profile_identity": self.profile_identity,
            "question_count": self.question_count,
            "distribution": dict(self.distribution),
            "multi_document_counts": dict(self.multi_document_counts),
            "files": dict(self.files),
            "decision_status": self.decision_status,
            "first_unseal_module": self.first_unseal_module,
            "historical_regression_identity": self.historical_regression_identity,
        }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取非空 JSONL object；任一坏行都让整份 reserve 失败关闭。"""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReserveContractError("reserve_source_unavailable", f"{path}: {exc}") from exc
    if any(not isinstance(value, dict) for value in values):
        raise ReserveContractError("reserve_shape_invalid", f"{path} 必须逐行 object")
    return values


def validate_reserve_records(
    records: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]],
    *,
    excluded_question_ids: set[str],
    excluded_document_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """校验 60 题分层、gold 双审、source 排除与题面近重复的确定性下限。"""

    rows = [dict(item) for item in records]
    review_rows = [dict(item) for item in reviews]
    if len(rows) != 60:
        raise ReserveContractError("reserve_count_invalid", f"期望 60，实际 {len(rows)}")
    required = {"reserve_question_id", "difficulty", "question", "expected_doc_ids", "gold_answer", "answer_facts", "source_signature"}
    for row in rows:
        if set(row) != required:
            raise ReserveContractError("reserve_shape_invalid", str(row.get("reserve_question_id")))
    ids = [row["reserve_question_id"] for row in rows]
    questions = [" ".join(str(row["question"]).lower().split()) for row in rows]
    if len(ids) != len(set(ids)) or len(questions) != len(set(questions)):
        raise ReserveContractError("reserve_duplicate", "ID 或规范化题面重复")
    token_sets = [set(question.replace("?", "").replace(",", "").split()) for question in questions]
    for left in range(len(token_sets)):
        for right in range(left + 1, len(token_sets)):
            union = token_sets[left] | token_sets[right]
            similarity = len(token_sets[left] & token_sets[right]) / len(union) if union else 1.0
            if similarity >= 0.9:
                raise ReserveContractError("reserve_near_duplicate", f"{ids[left]} ~ {ids[right]}")
    if set(ids) & excluded_question_ids:
        raise ReserveContractError("reserve_contaminated", "复用了历史 question id")
    used_docs = {doc_id for row in rows for doc_id in row["expected_doc_ids"]}
    if used_docs & excluded_document_ids:
        raise ReserveContractError("reserve_contaminated", "复用了历史 gold 文档")
    distribution = {difficulty: sum(row["difficulty"] == difficulty for row in rows) for difficulty in EXPECTED_DISTRIBUTION}
    if distribution != EXPECTED_DISTRIBUTION:
        raise ReserveContractError("reserve_distribution_invalid", str(distribution))
    core_multi = sum(row["difficulty"] == "core" and len(row["expected_doc_ids"]) > 1 for row in rows)
    hard_multi = sum(row["difficulty"] == "hard" and len(row["expected_doc_ids"]) > 1 for row in rows)
    if core_multi < 8 or hard_multi != 20:
        raise ReserveContractError("reserve_distribution_invalid", f"core_multi={core_multi}, hard_multi={hard_multi}")
    if any(not row["expected_doc_ids"] or not str(row["gold_answer"]).strip() or not row["answer_facts"] for row in rows):
        raise ReserveContractError("reserve_gold_invalid", "gold 坐标、答案和 facts 必须非空")

    review_required = {"reserve_question_id", "reviewer", "verdict", "source_hashes", "gold_hash"}
    if any(set(row) != review_required for row in review_rows):
        raise ReserveContractError("reserve_review_invalid", "review 字段不闭合")
    by_id: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in ids}
    for review in review_rows:
        if review["reserve_question_id"] not in by_id:
            raise ReserveContractError("reserve_review_invalid", "review 指向未知题")
        by_id[review["reserve_question_id"]].append(review)
    for row in rows:
        item_reviews = by_id[row["reserve_question_id"]]
        if len(item_reviews) != 2 or len({item["reviewer"] for item in item_reviews}) != 2:
            raise ReserveContractError("reserve_review_invalid", f"{row['reserve_question_id']} 未完成双审")
        if any(item["verdict"] != "approved" for item in item_reviews):
            raise ReserveContractError("reserve_review_invalid", f"{row['reserve_question_id']} 审核未通过")
        expected_gold_hash = canonical_hash({"gold_answer": row["gold_answer"], "answer_facts": row["answer_facts"]})
        if any(item["gold_hash"] != expected_gold_hash for item in item_reviews):
            raise ReserveContractError("reserve_review_invalid", f"{row['reserve_question_id']} gold hash 漂移")
    return rows, review_rows


def seal_reserve(
    *,
    reserve_path: Path,
    review_path: Path,
    ledger_path: Path,
    source_pool_path: Path,
    corpus_identity: str,
    profile_identity: str,
    excluded_question_ids: set[str],
    excluded_document_ids: set[str],
) -> ReserveManifest:
    """在 action/Prompt/参数选择前校验并密封 reserve；本函数不运行任何候选。"""

    rows, reviews = validate_reserve_records(
        _read_jsonl(reserve_path), _read_jsonl(review_path),
        excluded_question_ids=excluded_question_ids, excluded_document_ids=excluded_document_ids,
    )
    try:
        source_pool = json.loads(source_pool_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReserveContractError("reserve_source_pool_invalid", str(exc)) from exc
    if not isinstance(source_pool, dict) or set(source_pool) != {"selection_identity", "exclusion", "sources"}:
        raise ReserveContractError("reserve_source_pool_invalid", "source pool 字段不闭合")
    sources = source_pool["sources"]
    if not isinstance(sources, list):
        raise ReserveContractError("reserve_source_pool_invalid", "sources 必须是 list")
    source_index: dict[str, str] = {}
    for source in sources:
        expected_source_fields = {"document_id", "source_type", "relative_path", "bytes", "sha256"}
        if not isinstance(source, dict) or set(source) != expected_source_fields:
            raise ReserveContractError("reserve_source_pool_invalid", "source record 字段不闭合")
        document_id = str(source["document_id"])
        if document_id in source_index or document_id in excluded_document_ids:
            raise ReserveContractError("reserve_contaminated", f"source pool 非唯一或历史污染: {document_id}")
        source_index[document_id] = str(source["sha256"])
    for row in rows:
        expected_hashes = [source_index.get(doc_id) for doc_id in row["expected_doc_ids"]]
        if any(item is None for item in expected_hashes):
            raise ReserveContractError("reserve_source_pool_invalid", f"{row['reserve_question_id']} 指向 pool 外文档")
        item_reviews = [item for item in reviews if item["reserve_question_id"] == row["reserve_question_id"]]
        if any(item["source_hashes"] != expected_hashes for item in item_reviews):
            raise ReserveContractError("reserve_review_invalid", f"{row['reserve_question_id']} source hash 漂移")
    ledger = _read_jsonl(ledger_path)
    if ledger != [{"event": "created", "purpose": "sealed_decision_reserve", "module": "M42"}, {"event": "sealed", "purpose": "future_B4_decision", "module": "M42"}]:
        raise ReserveContractError("reserve_ledger_invalid", "创建时账本只能是 created→sealed")
    distribution = {difficulty: sum(row["difficulty"] == difficulty for row in rows) for difficulty in EXPECTED_DISTRIBUTION}
    multi = {difficulty: sum(row["difficulty"] == difficulty and len(row["expected_doc_ids"]) > 1 for row in rows) for difficulty in EXPECTED_DISTRIBUTION}
    file_hashes = {
        "reserve.jsonl": file_sha256(reserve_path),
        "gold_review.jsonl": file_sha256(review_path),
        "access_ledger.jsonl": file_sha256(ledger_path),
        "source_pool.json": file_sha256(source_pool_path),
    }
    identity = canonical_hash(
        {"schema_version": RESERVE_SCHEMA, "corpus_identity": corpus_identity, "profile_identity": profile_identity,
         "distribution": distribution, "multi_document_counts": multi, "files": file_hashes}
    )
    return ReserveManifest(
        schema_version=RESERVE_SCHEMA, reserve_identity=identity, corpus_identity=corpus_identity,
        profile_identity=profile_identity, question_count=60, distribution=distribution,
        multi_document_counts=multi, files=file_hashes, decision_status="sealed",
        first_unseal_module="M46", historical_regression_identity="m34-180-historical-only",
    )


def validate_external_store(manifest: Mapping[str, Any], *, external_root: Path) -> None:
    """B3 默认只能对账文件 hash；不返回逐题内容。"""

    if manifest.get("schema_version") != RESERVE_SCHEMA or manifest.get("decision_status") != "sealed":
        raise ReserveContractError("reserve_manifest_invalid", "schema/status 非法")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"reserve.jsonl", "gold_review.jsonl", "access_ledger.jsonl", "source_pool.json"}:
        raise ReserveContractError("reserve_manifest_invalid", "文件闭集非法")
    for name, expected_hash in files.items():
        path = external_root / name
        if not path.is_file() or file_sha256(path) != expected_hash:
            raise ReserveContractError("reserve_artifact_mismatch", name)


def apply_access_event(manifest: ReserveManifest, *, event: str, module: str) -> ReserveManifest:
    """用显式状态机表达首次解封与污染；污染后永远退出 decision set。"""

    if event == "first_unseal" and module == manifest.first_unseal_module and manifest.decision_status == "sealed":
        status: Literal["sealed", "unsealed", "retired"] = "unsealed"
    elif event in {"used_for_tuning", "gold_accessed_before_gate", "candidate_result_accessed_before_gate"}:
        status = "retired"
    else:
        raise ReserveContractError("reserve_access_invalid", f"{event}@{module}")
    return ReserveManifest(**{**manifest.__dict__, "decision_status": status})
