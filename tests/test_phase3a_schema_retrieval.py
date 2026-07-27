"""Phase 3A M9 Schema Retrieval 与 JoinPath 测试。

★ M9 的目标不是直接生成 SQL，而是先证明“问题里说的业务词”能召回正确表、字段、指标和
关系。后续 M10/M11 的 QueryPlan 与局部 prompt 都会站在这个局部 Schema 上继续工作。
"""

from pathlib import Path

from eval.run_eval import EvalCase, load_cases
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.retriever import retrieve_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE3A_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
CHALLENGE_CASES = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
DIAGNOSTIC_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-diagnostic-benchmark.yaml"
RELATIONS_PATH = PROJECT_ROOT / "domain_pack" / "schema_desc" / "relations.yaml"


def _allow_formal_cases() -> list[EvalCase]:
    """取 8 条非安全 formal case，作为 M9 的硬召回门。"""

    return [case for case in load_cases(PHASE3A_CASES) if case.security_expectation == "allow"]


def test_build_schema_documents_has_field_metric_and_relation_docs() -> None:
    """Schema 文档必须分成字段、指标、关系三类，并保留后续过滤需要的 metadata。"""

    documents = build_schema_documents(load_domain_schema(), relations_path=RELATIONS_PATH)
    doc_types = {document.doc_type for document in documents}
    field_doc = next(document for document in documents if document.doc_type == "field_doc")
    metric_doc = next(document for document in documents if document.doc_type == "metric_doc")
    relation_doc = next(document for document in documents if document.doc_type == "relation_doc")

    assert {"field_doc", "metric_doc", "relation_doc"} <= doc_types
    assert field_doc.metadata["doc_type"] == "field_doc"
    assert field_doc.metadata["table_name"] == field_doc.table
    assert field_doc.metadata["column_name"] == field_doc.column
    assert metric_doc.metadata["metric_key"] == metric_doc.metric_key
    assert relation_doc.metadata["relation_id"] == relation_doc.relation["id"]


def test_keyword_text_contains_business_aliases_from_domain_pack() -> None:
    """中文业务说法要能直接打到文档，别名优先来自 schema_desc 与 metrics。"""

    documents = build_schema_documents(load_domain_schema(), relations_path=RELATIONS_PATH)
    corpus = "\n".join(document.keyword_text for document in documents)

    assert "订单表" in corpus
    assert "渠道 GMV" in corpus
    assert "退款商品" in corpus
    assert "优惠券使用率" in corpus


def test_retrieve_schema_returns_keyword_vector_and_merged_hits() -> None:
    """Retriever 至少要有 keyword + vector 两路召回，并输出稳定 hit 字段。"""

    result = retrieve_schema(
        question="JUNE_FIXED_50 在哪个渠道使用最多？",
        user_role="ops",
        top_k=12,
        domain_schema=load_domain_schema(),
        relations_path=RELATIONS_PATH,
    )

    assert result.keyword_hits
    assert result.vector_hits
    assert result.merged_hits
    assert {hit.source for hit in result.keyword_hits} == {"keyword"}
    assert {hit.source for hit in result.vector_hits} == {"vector"}
    assert all(hit.score >= 0 for hit in result.merged_hits)
    assert all(hit.rank >= 1 for hit in result.merged_hits)
    assert all(hit.doc_type in {"field_doc", "metric_doc", "relation_doc"} for hit in result.merged_hits)


def test_retrieve_schema_default_backend_stays_inmemory_deterministic(monkeypatch) -> None:
    """未显式配置时仍走 in-memory + deterministic，pytest 不依赖 Milvus 或联网 embedding。"""

    from app.core.config import get_settings

    monkeypatch.delenv("SCHEMA_VECTOR_BACKEND", raising=False)
    monkeypatch.delenv("SCHEMA_EMBEDDING_PROVIDER", raising=False)
    get_settings.cache_clear()
    try:
        result = retrieve_schema(
            question="2026 年 6 月 GMV 是多少？",
            user_role="ops",
            top_k=8,
            domain_schema=load_domain_schema(),
            relations_path=RELATIONS_PATH,
        )
    finally:
        get_settings.cache_clear()

    assert result.vector_hits
    assert {hit.source for hit in result.vector_hits} == {"vector"}


def test_retrieve_schema_can_explicitly_select_milvus_backend_without_changing_default(monkeypatch) -> None:
    """Milvus 后端必须显式开启；测试用 fake adapter 证明配置被消费，不连接真实服务。"""

    from app.core.config import get_settings
    from engine.schema_retrieval import retriever

    calls: dict[str, object] = {}

    class FakeMilvusVectorIndex:
        """记录构造参数并返回空向量召回，避免单元测试依赖 Milvus。"""

        def __init__(self, **kwargs: object) -> None:
            calls.update(kwargs)

        def search(self, query: str, *, top_k: int) -> list[object]:
            calls["query"] = query
            calls["top_k"] = top_k
            return []

    monkeypatch.setenv("SCHEMA_VECTOR_BACKEND", "milvus")
    monkeypatch.setenv("SCHEMA_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MILVUS_COLLECTION", "schema_docs_test")
    monkeypatch.setattr(retriever, "MilvusVectorIndex", FakeMilvusVectorIndex, raising=False)
    get_settings.cache_clear()
    try:
        result = retrieve_schema(
            question="2026 年 6 月 GMV 是多少？",
            user_role="ops",
            top_k=8,
            domain_schema=load_domain_schema(),
            relations_path=RELATIONS_PATH,
        )
    finally:
        get_settings.cache_clear()

    assert result.keyword_hits
    assert calls["collection_name"] == "schema_docs_test"
    assert calls["reset_collection"] is False
    assert calls["query"] == "2026 年 6 月 GMV 是多少？"


def test_retrieve_schema_can_select_dashscope_embedding_with_milvus(monkeypatch) -> None:
    """Qwen embedding 只在显式配置 Milvus 时启用，避免默认 pytest 联网。"""

    from app.core.config import get_settings
    from engine.schema_retrieval import retriever

    calls: dict[str, object] = {}

    class FakeMilvusVectorIndex:
        """记录 embedding provider 类型，避免测试连接真实 Milvus。"""

        def __init__(self, **kwargs: object) -> None:
            calls.update(kwargs)

        def search(self, query: str, *, top_k: int) -> list[object]:
            calls["query"] = query
            calls["top_k"] = top_k
            return []

    monkeypatch.setenv("SCHEMA_VECTOR_BACKEND", "milvus")
    monkeypatch.setenv("SCHEMA_EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("QWEN_EMBEDDING_MODEL", "qwen3.7-text-embedding")
    monkeypatch.setenv("QWEN_EMBEDDING_DIMENSIONS", "1024")
    monkeypatch.setattr(retriever, "MilvusVectorIndex", FakeMilvusVectorIndex, raising=False)
    get_settings.cache_clear()
    try:
        retrieve_schema(
            question="2026 年 6 月 GMV 是多少？",
            user_role="ops",
            top_k=8,
            domain_schema=load_domain_schema(),
            relations_path=RELATIONS_PATH,
        )
    finally:
        get_settings.cache_clear()

    assert calls["embedding_provider"].__class__.__name__ == "DashScopeEmbeddingProvider"
    assert calls["dimension"] == 1024
    assert calls["query"] == "2026 年 6 月 GMV 是多少？"


def test_retrieve_schema_profile_can_select_milvus_qwen_embedding_without_env_backend(monkeypatch) -> None:
    """演示页按钮使用 profile 切换 Milvus + Qwen embedding，不污染默认环境变量。"""

    from app.core.config import get_settings
    from engine.schema_retrieval import retriever

    calls: dict[str, object] = {}

    class FakeMilvusVectorIndex:
        """记录 profile 预设展开后的 Milvus 参数。"""

        def __init__(self, **kwargs: object) -> None:
            calls.update(kwargs)

        def search(self, query: str, *, top_k: int) -> list[object]:
            calls["query"] = query
            calls["top_k"] = top_k
            return []

    monkeypatch.delenv("SCHEMA_VECTOR_BACKEND", raising=False)
    monkeypatch.delenv("SCHEMA_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setattr(retriever, "MilvusVectorIndex", FakeMilvusVectorIndex, raising=False)
    get_settings.cache_clear()
    try:
        retrieve_schema(
            question="2026 年 6 月 GMV 是多少？",
            user_role="ops",
            top_k=8,
            domain_schema=load_domain_schema(),
            relations_path=RELATIONS_PATH,
            schema_retrieval_profile="milvus_qwen37",
        )
    finally:
        get_settings.cache_clear()

    assert calls["embedding_provider"].__class__.__name__ == "DashScopeEmbeddingProvider"
    assert calls["dimension"] == 1024
    assert calls["collection_name"] == "datapilot_schema_docs"
    assert calls["query"] == "2026 年 6 月 GMV 是多少？"


def test_allow_formal_cases_recall_expected_tables_columns_and_metrics() -> None:
    """8 条允许类 formal case：表 100% 命中，字段/指标总体召回不低于 80%。"""

    domain_schema = load_domain_schema()
    total_expected_items = 0
    total_recalled_items = 0

    for case in _allow_formal_cases():
        result = retrieve_schema(
            question=case.question,
            user_role=case.user_role,
            top_k=24,
            domain_schema=domain_schema,
            relations_path=RELATIONS_PATH,
        )
        graph = build_schema_graph(result.merged_hits, domain_schema=domain_schema, relations_path=RELATIONS_PATH)
        recalled_tables = set(graph.tables)
        recalled_items = set(graph.field_names) | set(graph.metrics)
        expected_items = set(case.expected_columns) | set(case.expected_metrics)

        assert set(case.expected_tables) <= recalled_tables, case.case_id
        total_expected_items += len(expected_items)
        total_recalled_items += len(expected_items & recalled_items)

    assert total_recalled_items / total_expected_items >= 0.8


def test_multi_table_formal_cases_have_join_paths_from_relations_yaml() -> None:
    """多表 formal case 的 JoinPath 必须来自 relations.yaml，而不是靠 LLM 猜 join。"""

    domain_schema = load_domain_schema()
    cases = {case.case_id: case for case in _allow_formal_cases()}

    for case_id in ["p3a_multi_001", "p3a_multi_002", "p3a_multi_003"]:
        case = cases[case_id]
        result = retrieve_schema(
            question=case.question,
            user_role=case.user_role,
            top_k=30,
            domain_schema=domain_schema,
            relations_path=RELATIONS_PATH,
        )
        graph = build_schema_graph(result.merged_hits, domain_schema=domain_schema, relations_path=RELATIONS_PATH)
        relation_ids = {edge.relation_id for path in graph.join_paths for edge in path.edges}

        assert graph.join_paths, case_id
        assert set(case.expected_tables) <= set(graph.tables), case_id
        assert relation_ids, case_id
        assert all(edge.source == "relations.yaml" for path in graph.join_paths for edge in path.edges)


def test_challenge_and_diagnostic_schema_capabilities_have_recall_summary() -> None:
    """M9 要同步看 challenge / diagnostic 的 schema_retrieval 与 join_path 诊断覆盖。"""

    domain_schema = load_domain_schema()
    cases = [
        case
        for case in load_cases(CHALLENGE_CASES, extra_cases=[DIAGNOSTIC_CASES])
        if {"schema_retrieval", "join_path"} & set(case.phase3a_capabilities)
    ]
    table_misses: dict[str, list[str]] = {}
    join_path_case_count = 0

    for case in cases:
        result = retrieve_schema(
            question=case.question,
            user_role=case.user_role,
            top_k=30,
            domain_schema=domain_schema,
            relations_path=RELATIONS_PATH,
        )
        graph = build_schema_graph(result.merged_hits, domain_schema=domain_schema, relations_path=RELATIONS_PATH)
        if case.expected_tables:
            missing = sorted(set(case.expected_tables) - set(graph.tables))
            if missing:
                table_misses[case.case_id] = missing
        if "join_path" in case.phase3a_capabilities and len(graph.tables) > 1:
            assert graph.join_paths or not case.phase3a_blocking, case.case_id
            join_path_case_count += 1

    assert len(cases) >= 20
    assert not table_misses
    assert join_path_case_count >= 10
