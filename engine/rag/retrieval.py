"""M32 Knowledge corpus 的可替换检索 adapter 与本地确定性基线。

本模块刻意不知道 caller、ACL、Evidence、active pointer 和最终答案。调用方只能把已经通过
pre-selection 授权的 ``CatalogEntry`` 交进来，adapter 负责把问题变成一组稳定、有序的
``RetrievalMatch``。这样将来替换成向量或混合检索时，安全边界仍留在 Knowledge Tool，
不会散落进每一种后端。
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from engine.rag.catalog import CatalogEntry

DETERMINISTIC_RETRIEVAL_IDENTITY = "knowledge-deterministic-lexical-v1"
DETERMINISTIC_MIN_SCORE = 0.05
_ASCII_WORD_RE = re.compile(r"[a-z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_NON_SEARCHABLE_RE = re.compile(r"[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+")


class RetrievalAdapterError(RuntimeError):
    """检索后端的结构化技术失败；零命中不使用异常表达。"""

    def __init__(self, reason_code: str, message: str) -> None:
        """保存机器可判定 reason，同时保留面向开发者的解释。"""

        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class RetrievalBudget:
    """一次 Tool 调用允许产生的候选与最终选择上限。"""

    max_candidates: int = 5
    max_selected: int = 3

    def __post_init__(self) -> None:
        """在进入 Tool 前拒绝非法或倒挂的候选/选择预算。"""

        if self.max_candidates < 1 or self.max_selected < 1:
            raise RetrievalAdapterError("retrieval_budget_invalid", "检索预算必须为正整数")
        if self.max_selected > self.max_candidates:
            raise RetrievalAdapterError("retrieval_budget_invalid", "selected 上限不能超过 candidate 上限")


@dataclass(frozen=True)
class RetrievalMatch:
    """adapter 返回的稳定命中坐标，不携带可被误当成授权事实的正文。"""

    document_key: str
    revision: str
    content_identity: str
    anchor: str
    score: float
    rank: int


@dataclass(frozen=True)
class RetrievalBatch:
    """一次后端调用的完整结果与可比较 runtime identity。"""

    adapter_identity: str
    recipe_identity: str
    query_fingerprint: str
    matches: tuple[RetrievalMatch, ...]


class RetrievalAdapter(Protocol):
    """Knowledge Tool 依赖的最小 adapter interface。"""

    identity: str
    recipe_identity: str

    def retrieve(
        self,
        *,
        question: str,
        confirmed_conditions: tuple[str, ...],
        entries: tuple[CatalogEntry, ...],
        limit: int,
    ) -> RetrievalBatch:
        """只在传入的已授权 entries 中检索。"""


def query_fingerprint(question: str, confirmed_conditions: tuple[str, ...] = ()) -> str:
    """生成不保存原始问题的稳定 query identity。"""

    normalized = _normalize("\n".join((question, *confirmed_conditions)))
    return f"query:{sha256(normalized.encode('utf-8')).hexdigest()}"


def _normalize(value: str) -> str:
    """NFKC + 小写 + 去标点，避免全角字符或空白导致同义输入漂移。"""

    normalized = unicodedata.normalize("NFKC", value).lower()
    return _NON_SEARCHABLE_RE.sub("", normalized)


def _features(value: str) -> frozenset[str]:
    """抽取英文词和中文 2-4 gram，作为无需第三方分词器的离线 baseline。

    中文没有天然空格；直接按整句相等会漏掉“质量问题退款需要哪些材料”这类问法，按短
    n-gram 又比单字重合更能抑制“的、可、用”等噪声。它只是首个可解释基线，不承诺
    代替未来由失败簇证明必要的 embedding 或 rerank。
    """

    normalized = unicodedata.normalize("NFKC", value).lower()
    tokens = set(_ASCII_WORD_RE.findall(normalized))
    for run in _CJK_RUN_RE.findall(normalized):
        for size in (2, 3, 4):
            if len(run) < size:
                continue
            tokens.update(run[index : index + size] for index in range(len(run) - size + 1))
    return frozenset(tokens)


def _entry_score(question: str, confirmed_conditions: tuple[str, ...], entry: CatalogEntry) -> float:
    """以 title/key 的明确命中优先，再用正文特征覆盖补足自然语言表达。"""

    query_text = "\n".join((question, *confirmed_conditions))
    query_normalized = _normalize(query_text)
    if not query_normalized:
        return 0.0

    title_normalized = _normalize(entry.title)
    key_normalized = _normalize(entry.document_key.replace("_", " "))
    query_terms = _features(query_text)
    if not query_terms:
        return 0.0

    title_terms = _features(entry.title)
    metadata_terms = _features(
        " ".join((entry.document_key.replace("_", " "), entry.knowledge_type, entry.anchor))
    )
    content_terms = _features(entry.content)

    # ★ title/key 是人工治理过的检索锚点，正文重合只负责补充，不反过来压过明确主题。
    title_overlap = len(query_terms & title_terms) / len(query_terms)
    metadata_overlap = len(query_terms & metadata_terms) / len(query_terms)
    content_overlap = len(query_terms & content_terms) / len(query_terms)
    exact_bonus = 1.0 if title_normalized and title_normalized in query_normalized else 0.0
    key_bonus = 0.5 if key_normalized and key_normalized in query_normalized else 0.0
    return round(exact_bonus + key_bonus + 0.55 * title_overlap + 0.25 * metadata_overlap + 0.20 * content_overlap, 8)


class DeterministicLexicalRetrievalAdapter:
    """★ 面向 11 条短政策/指标说明的首个本地、可复现检索基线。

    该 adapter 没有网络、缓存或可变索引。相同 question、conditions、entries 和 limit 必须
    给出相同结果；并列时按 document/revision/anchor 排序，避免集合迭代顺序污染 Eval。
    """

    identity = DETERMINISTIC_RETRIEVAL_IDENTITY
    # identity 显式包含低相关性门；以后调整阈值必须产生新 recipe，不能污染同名 Eval。
    recipe_identity = "title-key-content-ngram-min005-v1"

    def retrieve(
        self,
        *,
        question: str,
        confirmed_conditions: tuple[str, ...] = (),
        entries: tuple[CatalogEntry, ...],
        limit: int,
    ) -> RetrievalBatch:
        """对授权后的短知识单元排序；零分条目不进入候选。"""

        if limit < 1:
            raise RetrievalAdapterError("retrieval_budget_invalid", "limit 必须为正整数")
        if not question.strip():
            raise RetrievalAdapterError("retrieval_query_invalid", "question 不能为空")

        unique_entries: dict[tuple[str, str, str, str], CatalogEntry] = {}
        for entry in entries:
            identity = (entry.document_key, entry.revision, entry.content_identity, entry.anchor)
            if identity in unique_entries:
                raise RetrievalAdapterError("retrieval_entry_duplicate", "adapter 输入包含重复 entry identity")
            unique_entries[identity] = entry

        scored: list[tuple[float, CatalogEntry]] = []
        for entry in unique_entries.values():
            score = _entry_score(question, confirmed_conditions, entry)
            if not math.isfinite(score):
                raise RetrievalAdapterError("retrieval_score_invalid", "检索 score 必须是有限数")
            # 只共享“平台”等公共词时分数通常接近 0；保留它会把知识缺失误报成有候选。
            if score >= DETERMINISTIC_MIN_SCORE:
                scored.append((score, entry))

        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].document_key,
                item[1].revision,
                item[1].anchor,
                item[1].content_identity,
            )
        )
        matches = tuple(
            RetrievalMatch(
                document_key=entry.document_key,
                revision=entry.revision,
                content_identity=entry.content_identity,
                anchor=entry.anchor,
                score=score,
                rank=rank,
            )
            for rank, (score, entry) in enumerate(scored[:limit], start=1)
        )
        return RetrievalBatch(
            adapter_identity=self.identity,
            recipe_identity=self.recipe_identity,
            query_fingerprint=query_fingerprint(question, confirmed_conditions),
            matches=matches,
        )
