"""App-2 DataPilot companion：安全 Langfuse sidecar 与正式来源合同测试。"""

from __future__ import annotations

import json
import math
import builtins
from pathlib import Path
import tomllib
from typing import Any

import pytest

from app.core.config import Settings
from engine.trace.langfuse_backend import LangFuseBackend
from engine.trace.lifecycle import build_trace_context
from engine.trace.recorder import JSONLBackend, TraceRecord, TraceRouter, TraceStep
from engine.trace.recorder import build_trace_router
from eval.contracts import (
    ARTIFACT_SCHEMA_VERSION,
    CONTRACT_VERSION,
    ObservabilityEvidence,
    build_observability_evidence,
    dataclass_payload,
    langfuse_host_identity,
    normalize_source_observability,
)
from eval.review import REVIEW_BUNDLE_SCHEMA_VERSION, build_review_bundle, verify_review_bundle_sources
from eval.scorers.base import LangFuseScorePayload
from eval.scorers.langfuse_scores import LangFuseScoreWriter


FORBIDDEN_CANARIES = (
    "原始问题-canary",
    "原始答案-canary",
    "SELECT secret FROM customers",
    "prompt-canary",
    "response-canary",
    "hidden-canary",
    "C:\\Users\\alice\\secret.txt",
    "sk-live-secret",
)
FIXTURE_ROOT = Path("tests/fixtures/app2_langfuse_source")


class _FakeSpan:
    """模拟 4.15.1 observation，只记录安全 adapter 实际提交的更新。"""

    _next_id = 0

    def __init__(self) -> None:
        type(self)._next_id += 1
        self.id = f"0123456789abcdef0123456789abc{type(self)._next_id:03x}"[-32:]
        self.updates: list[dict[str, Any]] = []
        self.ended = False

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def end(self) -> None:
        self.ended = True


class _FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.client_kwargs = kwargs
        self.observations: list[dict[str, Any]] = []
        self.spans: list[_FakeSpan] = []
        self.scores: list[dict[str, Any]] = []
        self.flushed = False

    def start_observation(self, **kwargs: Any) -> _FakeSpan:
        self.observations.append(kwargs)
        span = _FakeSpan()
        self.spans.append(span)
        return span

    def create_score(self, **kwargs: Any) -> None:
        self.scores.append(kwargs)

    def flush(self) -> None:
        self.flushed = True


class _Factory:
    def __init__(self) -> None:
        self.client: _FakeClient | None = None

    def __call__(self, **kwargs: Any) -> _FakeClient:
        self.client = _FakeClient(**kwargs)
        return self.client


def _settings(**overrides: str) -> Settings:
    values = {
        "LANGFUSE_ENABLED": "true",
        "LANGFUSE_PUBLIC_KEY": "pk-app2-public",
        "LANGFUSE_SECRET_KEY": "sk-live-secret",
        "LANGFUSE_BASE_URL": "https://JP.Cloud.Langfuse.com/",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _record() -> TraceRecord:
    from app.schemas.agent import CostInfo

    return TraceRecord(
        trace_id="dp-app2-trace-001",
        question=FORBIDDEN_CANARIES[0],
        user_role="ops",
        route="sql",
        answer=FORBIDDEN_CANARIES[1],
        sql=FORBIDDEN_CANARIES[2],
        columns=["secret"],
        rows=[{"secret": FORBIDDEN_CANARIES[5]}],
        safety_status="passed",
        execution_status="completed",
        answer_status="answered",
        cost=CostInfo(latency_ms=12.5),
        trace_steps=[
            TraceStep(
                name="sql_execution",
                step_index=1,
                step_type="sql_query",
                status="success",
                input_summary=FORBIDDEN_CANARIES[3],
                output_summary=FORBIDDEN_CANARIES[4],
                latency_ms=4.25,
                metadata={"has_chart": False},
            )
        ],
    )


def _serialized_client(client: _FakeClient) -> str:
    return json.dumps(
        {"observations": client.observations, "updates": [span.updates for span in client.spans], "scores": client.scores},
        ensure_ascii=False,
    )


def test_live_root_child_use_safe_payload_and_real_root_parent() -> None:
    factory = _Factory()
    context = build_trace_context(
        trace_id="dp-app2-trace-001",
        question=FORBIDDEN_CANARIES[0],
        user_role="ops",
        settings=_settings(),
        client_factory=factory,
    )
    span = context.start_span(name="sql_execution", step_type="sql_query", input_summary=FORBIDDEN_CANARIES[3])
    span.end(output_summary=FORBIDDEN_CANARIES[4], status="success", metadata={"has_chart": False})
    snapshot = context.snapshot(status="success", output_summary=FORBIDDEN_CANARIES[1])

    assert snapshot.langfuse_write_status == "ok"
    assert factory.client is not None
    assert factory.client.flushed is True
    assert len(factory.client.observations) == 2
    root, child = factory.client.observations
    assert root == {
        "trace_context": {"trace_id": snapshot.langfuse_trace_id},
        "name": "datapilot-query",
        "as_type": "span",
        "metadata": {"projection_version": "datapilot-langfuse-safe-v1", "datapilot_trace_id": "dp-app2-trace-001"},
    }
    assert child["trace_context"]["trace_id"] == snapshot.langfuse_trace_id
    assert child["trace_context"]["parent_span_id"] == factory.client.spans[0].id
    assert child["metadata"]["step_type"] == "sql_query"
    assert factory.client.spans[1].updates == [{
        "metadata": {
            "projection_version": "datapilot-langfuse-safe-v1",
            "step_index": 1,
            "step_type": "sql_query",
            "status": "success",
            "latency_ms": pytest.approx(snapshot.trace_steps[0].latency_ms),
            "has_chart": False,
        }
    }]
    uploaded = _serialized_client(factory.client)
    assert all(canary not in uploaded for canary in FORBIDDEN_CANARIES)


def test_optional_dependency_is_exact_and_default_router_never_imports_sdk(monkeypatch) -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["optional-dependencies"]["observability"] == ["langfuse==4.15.1"]

    real_import = builtins.__import__
    attempted: list[str] = []

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "langfuse" or name.startswith("langfuse."):
            attempted.append(name)
            raise AssertionError("default-disabled path must not load Langfuse SDK")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    router = build_trace_router(Settings(_env_file=None, LANGFUSE_ENABLED="false"))

    assert [backend.name for backend in router.backends] == ["jsonl"]
    assert attempted == []


def test_post_hoc_writer_omits_raw_content_and_keeps_allowed_facts() -> None:
    factory = _Factory()
    record = _record()

    LangFuseBackend(_settings(), client_factory=factory).record(record)

    assert record.langfuse_write_status == "ok"
    assert factory.client is not None
    assert factory.client.flushed is True
    assert len(factory.client.observations) == 2
    root, child = factory.client.observations
    assert root["metadata"] == {
        "projection_version": "datapilot-langfuse-safe-v1",
        "datapilot_trace_id": record.trace_id,
        "route": "sql",
        "execution_status": "completed",
        "answer_status": "answered",
        "safety_status": "passed",
        "trace_step_count": 1,
    }
    assert child["metadata"]["step_type"] == "sql_query"
    assert factory.client.spans[1].updates[0]["metadata"]["step_index"] == 1
    assert factory.client.spans[1].updates[0]["metadata"]["latency_ms"] == 4.25
    uploaded = _serialized_client(factory.client)
    assert all(canary not in uploaded for canary in FORBIDDEN_CANARIES)


def test_unknown_child_metadata_fails_sidecar_but_jsonl_keeps_local_facts(tmp_path: Path) -> None:
    factory = _Factory()
    record = _record()
    record.trace_steps[0].metadata = {"unknown_free_text": FORBIDDEN_CANARIES[5]}
    path = tmp_path / "trace.jsonl"

    TraceRouter([LangFuseBackend(_settings(), client_factory=factory), JSONLBackend()]).record(record, path=path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["langfuse_write_status"] == "failed"
    assert saved["question"] == FORBIDDEN_CANARIES[0]
    assert saved["answer"] == FORBIDDEN_CANARIES[1]
    assert factory.client is not None
    assert FORBIDDEN_CANARIES[5] not in _serialized_client(factory.client)


def test_score_writer_only_sends_finite_numeric_and_stable_allowlist_metadata() -> None:
    factory = _Factory()
    writer = LangFuseScoreWriter(_settings(), client_factory=factory)
    payload = LangFuseScorePayload(
        trace_id="0123456789abcdef0123456789abcdef",
        name="rule:table_hit",
        value=1.0,
        comment=FORBIDDEN_CANARIES[4],
        metadata={"case_id": "case_app2_001", "scorer_version": "m27-v4", "passed": True},
    )

    assert writer.write_scores([payload]) == {"ok": 1, "skipped": 0, "failed": 0}
    assert factory.client is not None
    assert factory.client.scores == [{
        "trace_id": payload.trace_id,
        "name": "rule:table_hit",
        "value": 1.0,
        "data_type": "NUMERIC",
        "metadata": {
            "projection_version": "datapilot-langfuse-safe-v1",
            "case_id": "case_app2_001",
            "scorer_version": "m27-v4",
            "passed": True,
        },
    }]
    assert FORBIDDEN_CANARIES[4] not in _serialized_client(factory.client)


def test_eval_score_payload_drops_local_reason_issue_tags_and_open_metadata(tmp_path: Path) -> None:
    """正式 builder 也必须先缩成白名单，不能只靠 writer 在最后一步报失败。"""

    from eval.scorers.base import EvalScoreDetail
    from eval.scorers.langfuse_scores import build_langfuse_score_payloads
    from eval.run_eval import EvalResult
    from tests.test_m17_scorers import _body, _case

    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(json.dumps({
        "trace_id": "dp-app2-trace-001",
        "langfuse_trace_id": "0123456789abcdef0123456789abcdef",
        "langfuse_write_status": "ok",
    }), encoding="utf-8")
    result = EvalResult(
        case=_case(), passed=True, reason="local aggregate", issue_tags=[], review_required=False,
        skipped_due_to_pipeline_mode=False, status_code=200, route="sql", safety_status="passed",
        error_type=None, trace_id="dp-app2-trace-001", sql="SELECT secret FROM customers",
        response_body=_body(), actual_pipeline_mode="new_text2sql",
        score_details=[EvalScoreDetail(
            name="rule:table_hit", value=1.0, passed=True, reason="response-canary",
            issue_tags=["hidden-canary"], metadata={"prompt": "prompt-canary"},
        )],
    )

    payload = build_langfuse_score_payloads(results=[result], trace_path=trace_path)[0]
    assert payload.comment == ""
    assert payload.metadata == {
        "case_id": result.case.case_id,
        "scorer_id": "rule:table_hit",
        "passed": True,
        "review_required": False,
    }


@pytest.mark.parametrize(
    "payload",
    [
        LangFuseScorePayload(trace_id="0123456789abcdef0123456789abcdef", name="rule:bad", value=math.inf),
        LangFuseScorePayload(
            trace_id="0123456789abcdef0123456789abcdef",
            name="rule:bad",
            value=1.0,
            metadata={"unknown_free_text": "do-not-upload"},
        ),
    ],
)
def test_unsafe_score_payload_isolated_as_failed(payload: LangFuseScorePayload) -> None:
    factory = _Factory()
    writer = LangFuseScoreWriter(_settings(), client_factory=factory)

    assert writer.write_scores([payload]) == {"ok": 0, "skipped": 0, "failed": 1}
    assert factory.client is not None
    assert factory.client.scores == []


def test_new_contract_versions_and_observability_state_machine() -> None:
    assert CONTRACT_VERSION == "m27-v4"
    assert ARTIFACT_SCHEMA_VERSION == "m27-artifact-v2"
    assert REVIEW_BUNDLE_SCHEMA_VERSION == "m27-review-bundle-v3"
    succeeded = ObservabilityEvidence(
        backend="langfuse",
        status="succeeded",
        datapilot_trace_id="dp-app2-trace-001",
        trace_id="0123456789abcdef0123456789abcdef",
        host_identity="0" * 64,
        project_identity="1" * 64,
        span_mode="live",
    )
    assert normalize_source_observability(
        succeeded.__dict__,
        contract_version="m27-v4",
        artifact_schema_version="m27-artifact-v2",
        expected_datapilot_trace_id="dp-app2-trace-001",
    ) == succeeded
    for status in ("disabled", "not_observed", "failed"):
        normalized = normalize_source_observability(
            {
                "backend": "langfuse",
                "status": status,
                "datapilot_trace_id": "dp-app2-trace-001",
                "trace_id": None,
                "host_identity": None,
                "project_identity": None,
                "span_mode": None,
            },
            contract_version="m27-v4",
            artifact_schema_version="m27-artifact-v2",
            expected_datapilot_trace_id="dp-app2-trace-001",
        )
        assert normalized.status == status


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"backend": "langfuse", "status": "succeeded", "datapilot_trace_id": "dp", "trace_id": None, "host_identity": "0" * 64, "project_identity": "1" * 64, "span_mode": "live"}, "requires"),
        ({"backend": "langfuse", "status": "failed", "datapilot_trace_id": "dp", "trace_id": "0123456789abcdef0123456789abcdef", "host_identity": None, "project_identity": None, "span_mode": None}, "must not"),
        ({"backend": "langfuse", "status": "succeeded", "datapilot_trace_id": "wrong", "trace_id": "0123456789abcdef0123456789abcdef", "host_identity": "0" * 64, "project_identity": "1" * 64, "span_mode": "live"}, "binding"),
        ({"backend": "langfuse", "status": "succeeded", "datapilot_trace_id": "dp", "trace_id": "bad id", "host_identity": "0" * 64, "project_identity": "1" * 64, "span_mode": "live"}, "opaque"),
    ],
)
def test_malformed_observability_fails_strict_reading(payload: dict[str, Any], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        normalize_source_observability(
            payload,
            contract_version="m27-v4",
            artifact_schema_version="m27-artifact-v2",
            expected_datapilot_trace_id="dp",
        )


def test_legacy_source_normalizes_to_not_observed_without_guessing() -> None:
    normalized = normalize_source_observability(
        None,
        contract_version="m27-v3",
        artifact_schema_version="m27-artifact-v1",
        expected_datapilot_trace_id="legacy-dp-trace",
    )

    assert normalized == ObservabilityEvidence(
        backend="langfuse",
        status="not_observed",
        datapilot_trace_id=None,
        trace_id=None,
        host_identity=None,
        project_identity=None,
        span_mode=None,
    )


def _write_source_tree(tmp_path: Path, observability: ObservabilityEvidence) -> tuple[Path, Path, Path]:
    """写一题三件套；期望值均为手写 literal，不复用 reader 的验证逻辑。"""

    run_id = "app2-source-fixture"
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        """
contract_version: m27-v4
scenarios:
  - id: app2_safe_case
    question: synthetic fixture question
    user_role: ops
    classification: core
    tags: [fixture]
    assertions:
      - id: safety
        kind: safety_block
""".strip(),
        encoding="utf-8",
    )
    observation = dataclass_payload(observability)
    checkpoint = {
        "scenario_id": "app2_safe_case",
        "replicate_id": 1,
        "evidence": {
            "run_id": run_id,
            "scenario_id": "app2_safe_case",
            "replicate_id": 1,
            "execution_status": "rejected",
            "response": {
                "trace_id": "dp-app2-trace-001",
                "route": "sql",
                "safety_status": "blocked",
                "columns": [],
                "rows": [],
            },
            "trace_steps": [{"step_type": "sql_guard", "status": "blocked", "metadata": {}}],
            "expected_rows": None,
            "observability": observation,
        },
        "assertion_results": [
            {"assertion_id": "safety", "kind": "safety_block", "status": "passed", "reason": "fixture", "metadata": {}}
        ],
    }
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_path = checkpoint_root / run_id / "checkpoints" / "app2_safe_case--r1.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    artifact = {
        "run_id": run_id,
        "run_status": "completed",
        "contract_version": "m27-v4",
        "artifact_schema_version": "m27-artifact-v2",
        "catalog_hash": "fixture-catalog",
        "selected_contract_hash": "fixture-selected",
        "scenario_runs": [
            {
                "scenario_id": "app2_safe_case",
                "replicate_id": 1,
                "evidence": {"observability": observation},
                "assertion_results": checkpoint["assertion_results"],
            }
        ],
    }
    artifact_path = tmp_path / "artifacts" / f"{run_id}.json"
    artifact_path.parent.mkdir()
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    return catalog_path, artifact_path, checkpoint_root


def _succeeded_observability() -> ObservabilityEvidence:
    return ObservabilityEvidence(
        backend="langfuse",
        status="succeeded",
        datapilot_trace_id="dp-app2-trace-001",
        trace_id="0123456789abcdef0123456789abcdef",
        host_identity="0" * 64,
        project_identity="1" * 64,
        span_mode="live",
    )


def test_new_artifact_checkpoint_review_cross_check_valid_source(tmp_path: Path) -> None:
    from eval.catalog import load_catalog

    catalog_path, artifact_path, checkpoint_root = _write_source_tree(tmp_path, _succeeded_observability())
    bundle = build_review_bundle(
        run_id="app2-source-fixture",
        catalog=load_catalog(catalog_path),
        artifact_path=artifact_path,
        checkpoint_root=checkpoint_root,
    )

    assert bundle["review_bundle_schema_version"] == "m27-review-bundle-v3"
    assert bundle["records"][0]["observability"] == dataclass_payload(_succeeded_observability())
    assert verify_review_bundle_sources(bundle) == {"artifact": 1, "checkpoints": 1}


def test_review_verifier_recomputes_observability_from_artifact_and_checkpoint(tmp_path: Path) -> None:
    from eval.catalog import load_catalog

    catalog_path, artifact_path, checkpoint_root = _write_source_tree(tmp_path, _succeeded_observability())
    bundle = build_review_bundle(
        run_id="app2-source-fixture",
        catalog=load_catalog(catalog_path),
        artifact_path=artifact_path,
        checkpoint_root=checkpoint_root,
    )
    bundle["records"][0]["observability"]["trace_id"] = "fedcba9876543210fedcba9876543210"

    with pytest.raises(ValueError, match="review/source observability mismatch"):
        verify_review_bundle_sources(bundle)


def test_new_source_rejects_artifact_checkpoint_observability_mismatch(tmp_path: Path) -> None:
    from eval.catalog import load_catalog

    catalog_path, artifact_path, checkpoint_root = _write_source_tree(tmp_path, _succeeded_observability())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["scenario_runs"][0]["evidence"]["observability"]["trace_id"] = "fedcba9876543210fedcba9876543210"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ValueError, match="observability mismatch"):
        build_review_bundle(
            run_id="app2-source-fixture",
            catalog=load_catalog(catalog_path),
            artifact_path=artifact_path,
            checkpoint_root=checkpoint_root,
        )


def test_new_source_rejects_missing_artifact_observability(tmp_path: Path) -> None:
    from eval.catalog import load_catalog

    catalog_path, artifact_path, checkpoint_root = _write_source_tree(tmp_path, _succeeded_observability())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    del artifact["scenario_runs"][0]["evidence"]["observability"]
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ValueError, match="observability is required"):
        build_review_bundle(
            run_id="app2-source-fixture",
            catalog=load_catalog(catalog_path),
            artifact_path=artifact_path,
            checkpoint_root=checkpoint_root,
        )


def test_trace_projection_hashes_normalized_host_and_public_key_without_exposing_them() -> None:
    settings = _settings()
    evidence = build_observability_evidence(
        {
            "trace_id": "dp-app2-trace-001",
            "langfuse_trace_id": "0123456789abcdef0123456789abcdef",
            "langfuse_write_status": "ok",
            "langfuse_span_mode": "post_hoc",
        },
        settings,
    )

    assert evidence.host_identity == langfuse_host_identity("https://jp.cloud.langfuse.com")
    assert evidence.project_identity is not None and len(evidence.project_identity) == 64
    serialized = json.dumps(dataclass_payload(evidence))
    assert "jp.cloud.langfuse.com" not in serialized
    assert "pk-app2-public" not in serialized
    assert "sk-live-secret" not in serialized


@pytest.mark.parametrize("status", ["disabled", "failed"])
def test_trace_projection_keeps_non_success_references_null(status: str) -> None:
    settings = _settings(**({"LANGFUSE_ENABLED": "false"} if status == "disabled" else {}))
    evidence = build_observability_evidence(
        {
            "trace_id": "dp-app2-trace-001",
            "langfuse_trace_id": "0123456789abcdef0123456789abcdef",
            "langfuse_write_status": "skipped" if status == "disabled" else "failed",
            "langfuse_span_mode": "live",
        },
        settings,
    )

    assert evidence.status == status
    assert (evidence.trace_id, evidence.host_identity, evidence.project_identity, evidence.span_mode) == (None, None, None, None)


def test_legacy_review_v2_source_is_still_verifiable(tmp_path: Path) -> None:
    from eval.catalog import load_catalog

    catalog_path, artifact_path, checkpoint_root = _write_source_tree(tmp_path, _succeeded_observability())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["contract_version"] = "m27-v3"
    artifact["artifact_schema_version"] = "m27-artifact-v1"
    artifact["scenario_runs"][0].pop("evidence")
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    checkpoint_path = checkpoint_root / "app2-source-fixture" / "checkpoints" / "app2_safe_case--r1.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["evidence"].pop("observability")
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    bundle = build_review_bundle(
        run_id="app2-source-fixture",
        catalog=load_catalog(catalog_path),
        artifact_path=artifact_path,
        checkpoint_root=checkpoint_root,
    )
    bundle["review_bundle_schema_version"] = "m27-review-bundle-v2"
    for record in bundle["records"]:
        record.pop("observability")

    assert verify_review_bundle_sources(bundle) == {"artifact": 1, "checkpoints": 1}


def test_portable_fixture_reopens_and_contains_no_sensitive_values_or_absolute_paths() -> None:
    review = json.loads((FIXTURE_ROOT / "review.json").read_text(encoding="utf-8"))

    assert verify_review_bundle_sources(review) == {"artifact": 1, "checkpoints": 1}
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(FIXTURE_ROOT.rglob("*"))
        if path.is_file()
    )
    lowered = serialized.lower()
    assert all(canary.lower() not in lowered for canary in FORBIDDEN_CANARIES)
    assert "langfuse_secret_key" not in lowered
    assert "langfuse_public_key" not in lowered
    assert "bearer " not in lowered
    assert "c:\\" not in lowered and "d:\\" not in lowered
