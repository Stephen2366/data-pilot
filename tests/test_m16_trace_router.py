"""M16 TraceRouter / LangFuse 双写测试。

★ 这一组测试只验证 trace 存储层，不跑真实 LangFuse Cloud。目标是守住三条底线：
默认 JSONL 行为不变、LangFuse 失败不影响 JSONL、API 响应契约不出现 LangFuse 内部字段。
"""

from __future__ import annotations

import builtins
import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.schemas.agent import CostInfo
from engine.trace.recorder import (
    JSONLBackend,
    TraceRecord,
    TraceRouter,
    TraceStep,
    append_trace,
    build_trace_router,
    configure_trace_router,
)
from engine.trace.lifecycle import build_trace_context
from engine.trace.langfuse_backend import LangFuseBackend
from scripts.seed_data import seed_database


def _sample_record() -> TraceRecord:
    """构造一条最小 TraceRecord，避免每个测试重复手写大对象。"""

    return TraceRecord(
        trace_id="datapilot-trace-1",
        question="各渠道订单量是多少？",
        user_role="ops",
        route="sql",
        answer="ok",
        sql="SELECT 1",
        columns=["value"],
        rows=[{"value": 1}],
        tables_used=["orders"],
        safety_status="passed",
        cost=CostInfo(latency_ms=1.0, sql_time_ms=0.5),
        trace_steps=[
            TraceStep(
                name="sql_generation",
                step_index=1,
                step_type="llm",
                status="success",
                input_summary="question",
                output_summary="sql",
                latency_ms=2.0,
                metadata={"provider": "mock"},
            )
        ],
    )


class FailingBackend:
    """模拟 LangFuse 挂掉：router 应捕获异常，后续 JSONL 仍然落盘。"""

    name = "langfuse"

    def record(self, record: TraceRecord, *, path: Path | None = None) -> None:
        """无条件抛错，模拟 Cloud / SDK 不可用。"""

        raise RuntimeError("langfuse unavailable")


class FakeSpan:
    """模拟 LangFuse span，只记录是否调用了 end。"""

    def __init__(self) -> None:
        """初始化为未结束状态。"""

        self.ended = False
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        """模拟 SDK 的 span.update()。"""

        self.updates.append(kwargs)

    def end(self) -> None:
        """模拟 SDK 的 span.end()。"""

        self.ended = True


class FakeLangFuseClient:
    """模拟 SDK 4.x client，避免单元测试访问真实 Cloud。"""

    def __init__(self, *, public_key: str, secret_key: str, base_url: str) -> None:
        """记录构造参数，证明 backend 使用 Settings 而不是硬编码。"""

        self.public_key = public_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.observations: list[dict[str, Any]] = []
        self.spans: list[FakeSpan] = []
        self.flush_called = False

    def start_observation(self, **kwargs: Any) -> FakeSpan:
        """记录 observation 参数，并返回一个可 end 的 fake span。"""

        span = FakeSpan()
        self.observations.append(kwargs)
        self.spans.append(span)
        return span

    def flush(self) -> None:
        """记录 flush 被调用；真实 SDK 会在这里发送队列中的事件。"""

        self.flush_called = True


class FakeLangFuseFactory:
    """可调用 factory，用于断言 backend 构造 client 时没有硬编码配置。"""

    def __init__(self) -> None:
        """保存最近一次创建的 fake client，方便测试断言。"""

        self.client: FakeLangFuseClient | None = None

    def __call__(self, **kwargs: Any) -> FakeLangFuseClient:
        """模拟 Langfuse(...) 构造器。"""

        self.client = FakeLangFuseClient(**kwargs)
        return self.client


@contextmanager
def _seeded_test_client(trace_path: Path) -> Generator[TestClient, None, None]:
    """创建带 seed 数据和独立 trace 文件的测试客户端。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        Base.metadata.drop_all(engine)


def test_append_trace_keeps_jsonl_path_override_when_langfuse_disabled(tmp_path: Path) -> None:
    """LANGFUSE_ENABLED=false 时，append_trace(path=...) 仍只写指定 JSONL 文件。"""

    trace_path = tmp_path / "custom-traces.jsonl"
    settings = Settings(_env_file=None, LANGFUSE_ENABLED="false")
    configure_trace_router(build_trace_router(settings))

    append_trace(_sample_record(), path=trace_path)

    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert trace["trace_id"] == "datapilot-trace-1"
    assert trace["langfuse_trace_id"] is None
    assert trace["langfuse_trace_url"] is None
    assert trace["langfuse_write_status"] == "skipped"


def test_trace_router_marks_langfuse_failed_and_still_writes_jsonl(tmp_path: Path) -> None:
    """LangFuse backend 抛异常时不能拖垮 JSONL 主链路。"""

    trace_path = tmp_path / "failed-langfuse-traces.jsonl"
    router = TraceRouter(backends=[FailingBackend(), JSONLBackend()])
    configure_trace_router(router)

    append_trace(_sample_record(), path=trace_path)

    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert trace["trace_id"] == "datapilot-trace-1"
    assert trace["langfuse_write_status"] == "failed"


def test_enabled_langfuse_with_missing_keys_degrades_to_jsonl(tmp_path: Path) -> None:
    """误开启 LangFuse 但没配 key 时，append_trace 仍要留下 JSONL。"""

    trace_path = tmp_path / "missing-key-langfuse-traces.jsonl"
    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="",
        LANGFUSE_SECRET_KEY="",
    )
    configure_trace_router(build_trace_router(settings))

    append_trace(_sample_record(), path=trace_path)

    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert trace["trace_id"] == "datapilot-trace-1"
    assert trace["langfuse_write_status"] == "failed"


def test_build_trace_router_can_switch_langfuse_enabled_in_same_process() -> None:
    """测试可在同一进程重置 router，不依赖重新 import recorder 模块。"""

    disabled = build_trace_router(Settings(_env_file=None, LANGFUSE_ENABLED="false"))
    enabled = build_trace_router(
        Settings(
            _env_file=None,
            LANGFUSE_ENABLED="true",
            LANGFUSE_PUBLIC_KEY="pk-test",
            LANGFUSE_SECRET_KEY="sk-test",
            LANGFUSE_BASE_URL="http://localhost:3000",
        )
    )

    assert [backend.name for backend in disabled.backends] == ["jsonl"]
    assert [backend.name for backend in enabled.backends] == ["langfuse", "jsonl"]


def test_langfuse_backend_records_flat_spans_and_flushes() -> None:
    """LangFuseBackend 成功时回填映射字段，并按 M16 约定写 flat spans。"""

    factory = FakeLangFuseFactory()
    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="http://localhost:3000",
    )
    record = _sample_record()
    backend = LangFuseBackend(settings, client_factory=factory)

    backend.record(record)

    assert record.langfuse_trace_id is not None
    assert len(record.langfuse_trace_id) == 32
    assert record.langfuse_trace_url == f"http://localhost:3000/project/traces/{record.langfuse_trace_id}"
    assert record.langfuse_write_status == "ok"
    assert factory.client is not None
    assert factory.client.flush_called is True
    assert len(factory.client.observations) == 2
    assert [observation["name"] for observation in factory.client.observations] == [
        "datapilot-query",
        "sql_generation",
    ]
    assert all(span.ended for span in factory.client.spans)
    assert factory.client.observations[0]["metadata"]["datapilot_trace_id"] == record.trace_id
    assert factory.client.observations[0]["metadata"]["rows_count"] == 1
    assert factory.client.observations[1]["metadata"]["step_index"] == 1


def test_langfuse_backend_skips_post_hoc_spans_when_record_is_live() -> None:
    """M16B live mode 已经在执行中写 span，最终 backend 不能重复拆 TraceStep。"""

    factory = FakeLangFuseFactory()
    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="http://localhost:3000",
    )
    record = _sample_record()
    record.langfuse_span_mode = "live"
    record.langfuse_trace_id = "live-trace-1"
    record.langfuse_write_status = "ok"
    backend = LangFuseBackend(settings, client_factory=factory)

    backend.record(record)

    assert record.langfuse_trace_url == "http://localhost:3000/project/traces/live-trace-1"
    assert record.langfuse_write_status == "ok"
    assert factory.client is None


def test_trace_lifecycle_writes_live_span_and_returns_snapshot() -> None:
    """M16B lifecycle 在执行中写 LangFuse span，并把映射字段交回 JSONL。"""

    factory = FakeLangFuseFactory()
    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="http://localhost:3000",
    )
    trace_context = build_trace_context(
        trace_id="datapilot-trace-1",
        question="各渠道订单量是多少？",
        user_role="ops",
        settings=settings,
        client_factory=factory,
    )

    span = trace_context.start_span(name="schema_retrieval", input_summary="question")
    span.end(output_summary="merged_hits=3", metadata={"merged_hit_count": 3})
    snapshot = trace_context.snapshot()

    assert factory.client is not None
    assert factory.client.flush_called is True
    assert snapshot.langfuse_trace_id is not None
    assert snapshot.langfuse_trace_url == f"http://localhost:3000/project/traces/{snapshot.langfuse_trace_id}"
    assert snapshot.langfuse_write_status == "ok"
    assert snapshot.langfuse_span_mode == "live"
    assert [step.name for step in snapshot.trace_steps] == ["schema_retrieval"]
    assert [observation["name"] for observation in factory.client.observations] == [
        "datapilot-query",
        "schema_retrieval",
    ]
    assert factory.client.spans[0].ended is True
    assert factory.client.spans[1].updates[0]["metadata"]["step_index"] == 1
    assert factory.client.spans[1].ended is True


def test_trace_lifecycle_degrades_when_langfuse_sdk_import_fails(monkeypatch) -> None:
    """LANGFUSE_ENABLED=true 但 SDK 未安装时，新 pipeline lifecycle 不能抛异常。"""

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "langfuse":
            raise ModuleNotFoundError("No module named 'langfuse'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="http://localhost:3000",
    )

    trace_context = build_trace_context(
        trace_id="datapilot-trace-1",
        question="各渠道订单量是多少？",
        user_role="ops",
        settings=settings,
    )
    span = trace_context.start_span(name="schema_retrieval")
    span.end(output_summary="local only")
    snapshot = trace_context.snapshot()

    assert snapshot.langfuse_trace_id is None
    assert snapshot.langfuse_write_status == "failed"
    assert [step.name for step in snapshot.trace_steps] == ["schema_retrieval"]


def test_trace_lifecycle_marks_failed_when_live_flush_fails() -> None:
    """live writer flush 失败时仍返回本地 trace_steps，但状态不能伪装成 ok。"""

    class FlushFailingClient(FakeLangFuseClient):
        """模拟 SDK flush 失败。"""

        def flush(self) -> None:
            raise RuntimeError("flush failed")

    class FlushFailingFactory:
        """返回 flush 失败的 fake client。"""

        def __init__(self) -> None:
            self.client: FlushFailingClient | None = None

        def __call__(self, **kwargs: Any) -> FlushFailingClient:
            self.client = FlushFailingClient(**kwargs)
            return self.client

    factory = FlushFailingFactory()
    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="http://localhost:3000",
    )
    trace_context = build_trace_context(
        trace_id="datapilot-trace-1",
        question="各渠道订单量是多少？",
        user_role="ops",
        settings=settings,
        client_factory=factory,
    )

    span = trace_context.start_span(name="schema_retrieval")
    span.end(output_summary="merged_hits=3")
    snapshot = trace_context.snapshot()

    assert snapshot.langfuse_trace_id is not None
    assert snapshot.langfuse_write_status == "failed"
    assert [step.name for step in snapshot.trace_steps] == ["schema_retrieval"]


def test_force_new_pipeline_dangerous_sql_records_sql_guard_step(tmp_path: Path) -> None:
    """危险 SQL 预检下沉到新 pipeline 后，blocked trace 也必须有 sql_guard step。"""

    trace_path = tmp_path / "dangerous-sql-traces.jsonl"
    configure_trace_router(TraceRouter(backends=[JSONLBackend()]))

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "DROP TABLE orders", "user_role": "ops", "force_new_pipeline": True},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert response.status_code == 200
    assert body["safety_status"] == "blocked"
    assert body["error_type"] == "sql_guard_blocked"
    assert [step["name"] for step in trace["trace_steps"]] == ["sql_guard"]
    assert trace["trace_steps"][0]["status"] == "blocked"


def test_api_response_contract_hides_langfuse_internal_fields(tmp_path: Path) -> None:
    """TraceRecord 可写 LangFuse 字段，但 /api/query 响应体不能新增这些内部字段。"""

    trace_path = tmp_path / "api-traces.jsonl"
    configure_trace_router(TraceRouter(backends=[JSONLBackend()]))

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops"},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert response.status_code == 200
    assert "langfuse_trace_id" not in body
    assert "langfuse_trace_url" not in body
    assert "langfuse_write_status" not in body
    assert "langfuse_write_status" in trace
