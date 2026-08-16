"""EnterpriseRAG-Bench 原件扫描、身份冻结与 closed-world 校验。

这一层只回答“我们拿到的是不是同一份数据”。它不会切 chunk、建立索引或读取 gold
文档替代真实检索。这样数据身份和后续检索实验可以独立变化，也能在任何昂贵构建前失败
关闭（fail closed）。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence


_DOCUMENT_FILE_PATTERN = re.compile(r"^(dsid_[0-9a-f]{32})__(.+)\.txt$")


class EnterpriseDatasetError(RuntimeError):
    """数据集不能被安全识别时抛出的结构化错误。"""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class RequiredAsset:
    """官方 release 中 M34 真正依赖的一个不可变资产。"""

    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class DatasetExpectations:
    """防止扫描结果“差不多”时仍继续构建的 closed-world 分母。"""

    source_instances: int
    selected_questions: int
    unique_gold_document_ids: int
    missing_gold_document_ids: int
    conflicting_logical_document_ids: int
    source_counts: Mapping[str, int]


@dataclass(frozen=True)
class DatasetRecipe:
    """项目内轻量 recipe；项目外 raw/extracted 才是数据原件。"""

    recipe_version: str
    release_tag: str
    source_types: tuple[str, ...]
    question_filter: str
    required_assets: tuple[RequiredAsset, ...]
    expected: DatasetExpectations
    repository: str = ""
    release_page: str = ""
    license_spdx: str = ""
    license_url: str = ""


@dataclass(frozen=True)
class SourceInstance:
    """物理文件身份；logical ID 重复时也绝不能互相覆盖。"""

    source_type: str
    relative_path: str
    logical_document_id: str
    semantic_name: str
    byte_size: int
    content_sha256: str
    physical_identity: str


@dataclass(frozen=True)
class BenchmarkQuestion:
    """严格筛选后的官方问题；gold 仅用于运行后的 Eval 对账。"""

    question_id: str
    question_type: str
    source_types: tuple[str, ...]
    question: str
    expected_document_ids: tuple[str, ...]
    gold_answer: str
    answer_facts: tuple[str, ...]


@dataclass(frozen=True)
class DatasetAudit:
    """完整扫描结果；CLI 默认只投影 summary，避免提交 3.6 万条大清单。"""

    recipe: DatasetRecipe
    dataset_root: Path
    source_instances: tuple[SourceInstance, ...]
    selected_questions: tuple[BenchmarkQuestion, ...]
    conflicting_logical_document_ids: tuple[str, ...]
    missing_gold_document_ids: tuple[str, ...]
    corpus_identity: str
    question_set_identity: str
    dataset_identity: str

    def summary(self) -> dict[str, Any]:
        """生成适合报告和 inspect 的轻量、确定性摘要。"""

        source_counts = Counter(item.source_type for item in self.source_instances)
        type_counts = Counter(item.question_type for item in self.selected_questions)
        question_source_counts = Counter(
            "+".join(item.source_types) for item in self.selected_questions
        )
        gold_count_distribution = Counter(
            len(item.expected_document_ids) for item in self.selected_questions
        )
        unique_gold = {
            document_id
            for item in self.selected_questions
            for document_id in item.expected_document_ids
        }
        return {
            "recipe_version": self.recipe.recipe_version,
            "release_tag": self.recipe.release_tag,
            "source_instance_count": len(self.source_instances),
            "source_counts": dict(sorted(source_counts.items())),
            "selected_question_count": len(self.selected_questions),
            "question_type_counts": dict(sorted(type_counts.items())),
            "question_source_counts": dict(sorted(question_source_counts.items())),
            "gold_document_count_distribution": {
                str(key): value for key, value in sorted(gold_count_distribution.items())
            },
            "unique_gold_document_count": len(unique_gold),
            "missing_gold_document_ids": list(self.missing_gold_document_ids),
            "conflicting_logical_document_ids": list(
                self.conflicting_logical_document_ids
            ),
            "corpus_identity": self.corpus_identity,
            "question_set_identity": self.question_set_identity,
            "dataset_identity": self.dataset_identity,
            "license": {
                "spdx": self.recipe.license_spdx,
                "url": self.recipe.license_url,
                "note": "Repository-level license metadata; downloaded release did not bundle a local LICENSE file.",
            },
        }


def canonical_identity(value: Any) -> str:
    """对 JSON 可表达合同生成稳定 SHA-256 身份。"""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_dataset_recipe(path: Path) -> DatasetRecipe:
    """从项目内 JSON 加载 recipe，并拒绝缺字段或重复资产。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected_payload = payload["expected"]
        assets = tuple(
            RequiredAsset(
                name=item["name"], size=int(item["size"]), sha256=item["sha256"]
            )
            for item in payload["required_assets"]
        )
        recipe = DatasetRecipe(
            recipe_version=payload["recipe_version"],
            release_tag=payload["release_tag"],
            source_types=tuple(payload["source_types"]),
            question_filter=payload["question_filter"],
            required_assets=assets,
            expected=DatasetExpectations(
                source_instances=int(expected_payload["source_instances"]),
                selected_questions=int(expected_payload["selected_questions"]),
                unique_gold_document_ids=int(
                    expected_payload["unique_gold_document_ids"]
                ),
                missing_gold_document_ids=int(
                    expected_payload["missing_gold_document_ids"]
                ),
                conflicting_logical_document_ids=int(
                    expected_payload["conflicting_logical_document_ids"]
                ),
                source_counts={
                    key: int(value)
                    for key, value in expected_payload["source_counts"].items()
                },
            ),
            repository=payload.get("repository", ""),
            release_page=payload.get("release_page", ""),
            license_spdx=payload.get("license_spdx", ""),
            license_url=payload.get("license_url", ""),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnterpriseDatasetError("invalid_recipe", str(exc)) from exc

    if not recipe.source_types or len(set(recipe.source_types)) != len(recipe.source_types):
        raise EnterpriseDatasetError("invalid_recipe", "source_types must be unique and non-empty")
    asset_names = [asset.name for asset in recipe.required_assets]
    if len(set(asset_names)) != len(asset_names):
        raise EnterpriseDatasetError("invalid_recipe", "required asset names must be unique")
    return recipe


def _verify_release_and_assets(root: Path, recipe: DatasetRecipe) -> None:
    raw_root = root / "raw"
    release_path = raw_root / "release-api.json"
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EnterpriseDatasetError("dataset_path_missing", str(release_path)) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnterpriseDatasetError("invalid_release_metadata", str(exc)) from exc

    if release.get("tag_name") != recipe.release_tag:
        raise EnterpriseDatasetError(
            "release_tag_mismatch",
            f"expected {recipe.release_tag}, got {release.get('tag_name')!r}",
        )
    official_assets = {item.get("name"): item for item in release.get("assets", ())}
    for asset in recipe.required_assets:
        path = raw_root / asset.name
        if not path.is_file():
            raise EnterpriseDatasetError("required_asset_missing", asset.name)
        if path.stat().st_size != asset.size:
            raise EnterpriseDatasetError("required_asset_size_mismatch", asset.name)
        if _file_sha256(path) != asset.sha256:
            raise EnterpriseDatasetError("required_asset_hash_mismatch", asset.name)

        official = official_assets.get(asset.name)
        official_digest = str(official.get("digest", "")) if official else ""
        if official is None or official.get("size") != asset.size:
            raise EnterpriseDatasetError("release_asset_mismatch", asset.name)
        if official_digest.removeprefix("sha256:") != asset.sha256:
            raise EnterpriseDatasetError("release_asset_mismatch", asset.name)


def _scan_source_instances(root: Path, recipe: DatasetRecipe) -> tuple[SourceInstance, ...]:
    extracted_root = root / "extracted"
    if not extracted_root.is_dir():
        raise EnterpriseDatasetError("dataset_path_missing", str(extracted_root))
    actual_sources = {path.name for path in extracted_root.iterdir() if path.is_dir()}
    unknown_sources = actual_sources - set(recipe.source_types)
    missing_sources = set(recipe.source_types) - actual_sources
    if unknown_sources:
        raise EnterpriseDatasetError("unknown_extracted_source", ",".join(sorted(unknown_sources)))
    if missing_sources:
        raise EnterpriseDatasetError("dataset_path_missing", ",".join(sorted(missing_sources)))

    records: list[SourceInstance] = []
    for source_type in sorted(recipe.source_types):
        source_root = extracted_root / source_type
        for path in sorted(source_root.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            if path.suffix.lower() != ".txt":
                raise EnterpriseDatasetError("unexpected_source_file", str(path))
            match = _DOCUMENT_FILE_PATTERN.fullmatch(path.name)
            if match is None:
                raise EnterpriseDatasetError("invalid_document_filename", str(path))
            content = path.read_bytes()
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise EnterpriseDatasetError("invalid_document_encoding", str(path)) from exc
            if not decoded.strip():
                raise EnterpriseDatasetError("empty_document", str(path))

            relative_path = path.relative_to(extracted_root).as_posix()
            content_hash = sha256(content).hexdigest()
            physical_identity = canonical_identity(
                {
                    "source_type": source_type,
                    "relative_path": relative_path,
                    "content_sha256": content_hash,
                }
            )
            records.append(
                SourceInstance(
                    source_type=source_type,
                    relative_path=relative_path,
                    logical_document_id=match.group(1),
                    semantic_name=match.group(2),
                    byte_size=len(content),
                    content_sha256=content_hash,
                    physical_identity=physical_identity,
                )
            )
    return tuple(records)


def _read_selected_questions(root: Path, recipe: DatasetRecipe) -> tuple[BenchmarkQuestion, ...]:
    if recipe.question_filter != "source_types_nonempty_subset_of_selected_sources":
        raise EnterpriseDatasetError("unsupported_question_filter", recipe.question_filter)
    question_path = root / "raw" / "questions.jsonl"
    selected: list[BenchmarkQuestion] = []
    seen_ids: set[str] = set()
    allowlist = set(recipe.source_types)
    try:
        lines = question_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise EnterpriseDatasetError("required_asset_missing", "questions.jsonl") from exc
    except UnicodeDecodeError as exc:
        raise EnterpriseDatasetError("invalid_question_encoding", str(exc)) from exc

    for line_number, line in enumerate(lines, start=1):
        try:
            item = json.loads(line)
            question_id = str(item["question_id"])
            raw_sources = item["source_types"]
            if not isinstance(raw_sources, list):
                raise TypeError("source_types must be a list")
            source_types = tuple(sorted(str(value) for value in raw_sources))
            expected_ids = tuple(str(value) for value in item["expected_doc_ids"])
            question = BenchmarkQuestion(
                question_id=question_id,
                question_type=str(item["question_type"]),
                source_types=source_types,
                question=str(item["question"]),
                expected_document_ids=expected_ids,
                gold_answer=str(item["gold_answer"]),
                answer_facts=tuple(str(value) for value in item["answer_facts"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EnterpriseDatasetError(
                "invalid_question_record", f"line {line_number}: {exc}"
            ) from exc
        if question_id in seen_ids:
            raise EnterpriseDatasetError("duplicate_question_id", question_id)
        seen_ids.add(question_id)
        # ★ 空 source_types 不能算“空集合是任意集合的子集”，否则会把 30 道
        # high-level / info-not-found 题错误纳入，分母从 180 漂成 210。
        if source_types and set(source_types).issubset(allowlist):
            if len(set(source_types)) != len(source_types):
                raise EnterpriseDatasetError("duplicate_question_source", question_id)
            if not expected_ids:
                raise EnterpriseDatasetError("invalid_expected_document_ids", question_id)
            selected.append(question)
    return tuple(sorted(selected, key=lambda item: item.question_id))


def _validate_expectations(
    recipe: DatasetRecipe,
    records: Sequence[SourceInstance],
    questions: Sequence[BenchmarkQuestion],
    conflicts: Sequence[str],
    missing_gold: Sequence[str],
) -> None:
    expected = recipe.expected
    source_counts = Counter(item.source_type for item in records)
    unique_gold = {
        document_id for item in questions for document_id in item.expected_document_ids
    }
    checks = {
        "source_instances": (len(records), expected.source_instances),
        "selected_questions": (len(questions), expected.selected_questions),
        "unique_gold_document_ids": (len(unique_gold), expected.unique_gold_document_ids),
        "missing_gold_document_ids": (len(missing_gold), expected.missing_gold_document_ids),
        "conflicting_logical_document_ids": (
            len(conflicts),
            expected.conflicting_logical_document_ids,
        ),
    }
    for name, (actual, wanted) in checks.items():
        if actual != wanted:
            raise EnterpriseDatasetError(
                "dataset_expectation_mismatch", f"{name}: expected {wanted}, got {actual}"
            )
    if dict(source_counts) != dict(expected.source_counts):
        raise EnterpriseDatasetError(
            "dataset_expectation_mismatch",
            f"source_counts: expected {dict(expected.source_counts)}, got {dict(source_counts)}",
        )


def _validate_gold_multiplicity(
    questions: Sequence[BenchmarkQuestion],
    logical_map: Mapping[str, Sequence[SourceInstance]],
) -> None:
    """验证 gold 的重复次数确实能由多个物理 source instance 解释。

    官方 `qst_0413` 两次列出同一个 logical ID，同时该 ID 对应两份不同 Jira
    文件。这里保留 multiset 语义：后续 Eval 才能要求两份都被召回，而不是静默
    `set()` 后把多文档题降成单文档题。
    """

    for question in questions:
        requested = Counter(question.expected_document_ids)
        for logical_id, count in requested.items():
            available = len(logical_map.get(logical_id, ()))
            # 缺失 logical ID 由独立的 missing-gold closed-world 分母报告；这里
            # 只判断“存在，但物理实例数不足以解释重复 gold”的情况。
            if available and count > available:
                raise EnterpriseDatasetError(
                    "gold_multiplicity_mismatch",
                    f"{question.question_id}: {logical_id} requested {count}, available {available}",
                )


def audit_enterprise_dataset(root: Path, recipe: DatasetRecipe) -> DatasetAudit:
    """完整验证 release、原件和问题集，并生成三层稳定身份。"""

    root = root.resolve()
    _verify_release_and_assets(root, recipe)
    records = _scan_source_instances(root, recipe)
    questions = _read_selected_questions(root, recipe)

    logical_map: defaultdict[str, list[SourceInstance]] = defaultdict(list)
    for record in records:
        logical_map[record.logical_document_id].append(record)
    conflicts = tuple(
        sorted(
            logical_id
            for logical_id, instances in logical_map.items()
            if len(instances) > 1
        )
    )
    unique_gold = {
        document_id for item in questions for document_id in item.expected_document_ids
    }
    missing_gold = tuple(sorted(unique_gold - logical_map.keys()))
    _validate_gold_multiplicity(questions, logical_map)
    _validate_expectations(recipe, records, questions, conflicts, missing_gold)

    corpus_identity = canonical_identity(
        {
            "release_tag": recipe.release_tag,
            "recipe_version": recipe.recipe_version,
            "source_instances": [
                {
                    "source_type": item.source_type,
                    "relative_path": item.relative_path,
                    "logical_document_id": item.logical_document_id,
                    "byte_size": item.byte_size,
                    "content_sha256": item.content_sha256,
                    "physical_identity": item.physical_identity,
                }
                for item in records
            ],
        }
    )
    question_set_identity = canonical_identity(
        {
            "filter": recipe.question_filter,
            "questions": [
                {
                    "question_id": item.question_id,
                    "question_type": item.question_type,
                    "source_types": item.source_types,
                    "question": item.question,
                    "expected_document_ids": item.expected_document_ids,
                    "gold_answer": item.gold_answer,
                    "answer_facts": item.answer_facts,
                }
                for item in questions
            ],
        }
    )
    dataset_identity = canonical_identity(
        {
            "recipe_version": recipe.recipe_version,
            "release_tag": recipe.release_tag,
            "assets": [asset.__dict__ for asset in recipe.required_assets],
            "corpus_identity": corpus_identity,
            "question_set_identity": question_set_identity,
        }
    )
    return DatasetAudit(
        recipe=recipe,
        dataset_root=root,
        source_instances=records,
        selected_questions=questions,
        conflicting_logical_document_ids=conflicts,
        missing_gold_document_ids=missing_gold,
        corpus_identity=corpus_identity,
        question_set_identity=question_set_identity,
        dataset_identity=dataset_identity,
    )
