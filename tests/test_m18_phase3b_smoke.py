"""M18 Phase 3B smoke 脚本测试。

这些测试不访问真实 LangFuse Cloud，只验证 smoke 的门禁语义：默认关闭时可以只跑 API/JSONL，
显式要求 LangFuse 时缺配置必须失败，PENDING 不能和 FAIL 混在一起。
"""

from __future__ import annotations

import json
from pathlib import Path

import scripts.smoke_phase3b_langfuse as smoke
from app.core.config import Settings


class _SmokeLLMClient:
    """为 smoke 的真实 API/Trace seam 提供确定性 Plan 与 SQL，不访问 provider。"""

    def complete(self, *, prompt: str) -> str:
        if "QueryPlan JSON Schema" in prompt:
            return json.dumps(
                {
                    "steps": [
                        {
                            "step_id": "step_1",
                            "step_index": 1,
                            "step_type": "sql_query",
                            "purpose": "按渠道统计订单量",
                            "depends_on": [],
                            "task_type": "aggregation",
                            "tables": ["channels", "orders"],
                            "columns": ["channels.channel_name", "orders.id", "orders.channel_id"],
                            "metrics": ["order_count"],
                            "filters": [],
                            "joins": ["orders_channel"],
                            "aggregations": ["COUNT(orders.id)"],
                            "group_by": ["channels.channel_name"],
                            "order_by": ["order_count DESC", "channels.channel_name ASC"],
                            "limit": None,
                            "output_columns": ["channels.channel_name", "order_count"],
                            "output_expressions": {"order_count": "COUNT(orders.id)"},
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "sql": "SELECT c.channel_name, COUNT(o.id) AS order_count FROM channels c JOIN orders o ON o.channel_id = c.id GROUP BY c.id, c.channel_name ORDER BY order_count DESC, c.channel_name ASC",
                "tables_used": ["channels", "orders"],
                "confidence": 0.9,
                "reasoning_summary": "确定性测试 SQL",
            },
            ensure_ascii=False,
        )


def test_smoke_passes_api_and_jsonl_when_langfuse_disabled(tmp_path: Path, monkeypatch) -> None:
    """默认禁用 LangFuse 时，API/JSONL 必须照常 PASS，Cloud 检查显示 SKIP。"""

    monkeypatch.setattr(smoke, "get_settings", lambda: Settings(_env_file=None, LANGFUSE_ENABLED="false"))
    from engine.nl2sql import pipeline

    monkeypatch.setattr(pipeline, "get_default_llm_client", lambda: _SmokeLLMClient())

    results = smoke.run_smoke(
        trace_path=tmp_path / "m18-disabled.jsonl",
        require_langfuse=False,
        visibility_timeout_seconds=0,
    )
    by_name = {result.name: result for result in results}

    assert by_name["api.query"].status == "PASS"
    assert by_name["jsonl.trace"].status == "PASS"
    assert by_name["jsonl.langfuse_mapping"].status == "SKIP"
    assert by_name["langfuse.score"].status == "SKIP"
    assert smoke._exit_code(results) == 0


def test_require_langfuse_fails_when_disabled(tmp_path: Path, monkeypatch) -> None:
    """显式 `--require-langfuse` 时，禁用或缺 key 不能被误报成通过。"""

    monkeypatch.setattr(smoke, "get_settings", lambda: Settings(_env_file=None, LANGFUSE_ENABLED="false"))
    from engine.nl2sql import pipeline

    monkeypatch.setattr(pipeline, "get_default_llm_client", lambda: _SmokeLLMClient())

    results = smoke.run_smoke(
        trace_path=tmp_path / "m18-require.jsonl",
        require_langfuse=True,
        visibility_timeout_seconds=0,
    )
    by_name = {result.name: result for result in results}

    assert by_name["config.langfuse"].status == "FAIL"
    assert by_name["langfuse.score"].status == "FAIL"
    assert by_name["langfuse.trace_visibility"].status == "FAIL"
    assert smoke._exit_code(results) == 1


def test_exit_code_treats_pending_as_non_fatal() -> None:
    """trace ingestion 短时不可见是 PENDING，不应和真实 FAIL 混淆。"""

    assert smoke._exit_code([smoke.CheckResult("visibility", "PENDING", "waited=0s")]) == 0
    assert smoke._exit_code([smoke.CheckResult("score", "FAIL", "write failed")]) == 1


def test_api_smoke_requires_ok_langfuse_mapping_when_enabled(tmp_path: Path, monkeypatch) -> None:
    """enabled 时有 langfuse_trace_id 但状态 failed，mapping 也不能误报 PASS。"""

    settings = Settings(
        _env_file=None,
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
    )

    monkeypatch.setattr(smoke, "_read_last_trace", lambda _path: {
        "trace_id": "datapilot-trace-1",
        "langfuse_trace_id": "lf-trace-1",
        "langfuse_write_status": "failed",
    })

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"trace_id": "datapilot-trace-1"}

    class FakeClient:
        def post(self, *_args, **_kwargs):
            return FakeResponse()

    class FakeSeededClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return FakeClient()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(smoke, "seeded_api_client", FakeSeededClient)

    results, _body, _trace = smoke._run_api_smoke(tmp_path / "trace.jsonl", settings)
    by_name = {result.name: result for result in results}

    assert by_name["jsonl.langfuse_mapping"].status == "FAIL"
