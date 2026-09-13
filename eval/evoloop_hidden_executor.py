"""EvoLoop P1-C3 的 DataPilot 受信 Hidden 单侧执行边界。

普通控制面只读取最终 ``ordinary-completion.json``；题面、gold、逐题结果和 Trace 留在
``private/``。这是逻辑数据边界，不是抵御本机文件访问的安全沙箱。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
import uuid

from eval.contracts import (
    AssertionContract, EvalRunSpec, ExecutionProtocol, ExpectedRejectionSpec,
    ResultMatchSpec, ScenarioContract, dataclass_payload,
)
from eval.environment import SQLiteRunEnvironmentFactory
from eval.evaluator import evaluate_scenario_once
from eval.evoloop_hidden_material import build_public_offer, validate_hidden_material

REQUEST_SCHEMA = "datapilot.evoloop-hidden-execution-request/v2"
COMPLETION_SCHEMA = "datapilot.evoloop-hidden-baseline-completion/v2"
PRIVATE_RESULT_SCHEMA = "datapilot.evoloop-hidden-private-result/v2"
BOUNDARY = "logical_data_boundary_only"
DEVELOPMENT_FIXTURE_SCHEMA = "datapilot.evoloop-hidden-development-fixture/v1"
_REQUEST_FIELDS = {"run_id", "purpose", "offer_digest", "private_digest", "candidate_digest", "authorization_digest", "world", "budget", "model"}
_WORLD_FIELDS = {"runtime_digest", "scorer_digest", "oracle_digest"}
_BUDGET_FIELDS = {"max_logical_works", "max_physical_requests", "max_observed_tokens", "max_wall_seconds"}
_MODEL_FIELDS = {"provider", "model", "temperature", "retry"}


class HiddenExecutionError(ValueError):
    """私有执行身份、账本或来源不满足合同。"""


class HiddenBeforeProviderError(RuntimeError):
    """明确发生在 provider 启动前，可记录为 failed_before_start。"""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71 or any(ch not in "0123456789abcdef" for ch in value[7:]):
        raise HiddenExecutionError(f"{field} must be a lowercase sha256 digest")
    return value


def _exact(value: Any, fields: set[str], location: str) -> dict[str, Any]:
    actual = set(value) if isinstance(value, dict) else set()
    if not isinstance(value, dict) or actual != fields:
        raise HiddenExecutionError(f"{location} fields mismatch missing={sorted(fields-actual)}, unknown={sorted(actual-fields)}")
    return value


def _envelope(schema: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    return {"schema": schema, "payload": body, "digest": _digest(body)}


def _parse(value: Any, schema: str, location: str) -> dict[str, Any]:
    item = _exact(value, {"schema", "payload", "digest"}, location)
    if item["schema"] != schema or not isinstance(item["payload"], dict) or item["digest"] != _digest(item["payload"]):
        raise HiddenExecutionError(f"{location} schema or digest mismatch")
    return dict(item["payload"])


def _write_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        handle.write(_canonical(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def build_execution_request(
    *, run_id: str, purpose: str, offer: Mapping[str, Any], candidate_digest: str,
    authorization_digest: str, world: Mapping[str, Any], budget: Mapping[str, Any], model: Mapping[str, Any],
) -> dict[str, Any]:
    """冻结 provider 调用前必须逐项相等的执行请求。"""

    if purpose not in {"development_probe", "formal_baseline"} or not isinstance(run_id, str) or not run_id:
        raise HiddenExecutionError("invalid run_id or purpose")
    offer_item = _exact(dict(offer), {"schema", "version", "private_digest", "coverage", "expected_count", "paired_policy", "retention_policy", "budget_policy"}, "offer")
    if offer_item["schema"] != "datapilot.evoloop-hidden-offer/v1":
        raise HiddenExecutionError("unsupported offer")
    request = _envelope(REQUEST_SCHEMA, {
        "run_id": run_id, "purpose": purpose, "offer_digest": _digest(offer_item),
        "private_digest": _require_digest(offer_item["private_digest"], "offer.private_digest"),
        "candidate_digest": _require_digest(candidate_digest, "candidate_digest"),
        "authorization_digest": _require_digest(authorization_digest, "authorization_digest"),
        "world": dict(world), "budget": dict(budget), "model": dict(model),
    })
    validate_execution_request(request)
    return request


def validate_execution_request(value: Any) -> dict[str, Any]:
    """严格重读冻结请求，任何身份、预算或模型漂移都在 provider 前失败。"""

    payload = _parse(value, REQUEST_SCHEMA, "request")
    _exact(payload, _REQUEST_FIELDS, "request.payload")
    if payload["purpose"] not in {"development_probe", "formal_baseline"} or not isinstance(payload["run_id"], str) or not payload["run_id"]:
        raise HiddenExecutionError("request identity invalid")
    for field in ("offer_digest", "private_digest", "candidate_digest", "authorization_digest"):
        _require_digest(payload[field], field)
    for field, digest in _exact(payload["world"], _WORLD_FIELDS, "request.world").items():
        _require_digest(digest, f"world.{field}")
    budget = _exact(payload["budget"], _BUDGET_FIELDS, "request.budget")
    if any(not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 for amount in budget.values()):
        raise HiddenExecutionError("budget values must be positive integers")
    model = _exact(payload["model"], _MODEL_FIELDS, "request.model")
    if model != {"provider": "qwen", "model": "qwen3.7-plus", "temperature": 0, "retry": 0}:
        raise HiddenExecutionError("model identity drifted")
    return payload


def validate_ordinary_completion(value: Any, *, expected_request_digest: str | None = None) -> dict[str, Any]:
    """严格读取 ordinary allowlist；自由字段视为泄漏或合同突破。"""

    payload = _parse(value, COMPLETION_SCHEMA, "completion")
    fields = {
        "version", "request_digest", "offer_digest", "private_digest", "candidate_digest", "authorization_digest",
        "world_digest", "runtime_digest", "budget_digest", "attempt_coverage_digest", "private_result_digest",
        "aggregate_usage", "usage_ledger_digest", "trusted_locator", "boundary", "state",
    }
    _exact(payload, fields, "completion.payload")
    for field in fields - {"version", "aggregate_usage", "trusted_locator", "boundary", "state"}:
        _require_digest(payload[field], field)
    _validate_aggregate_usage(payload["aggregate_usage"])
    if expected_request_digest is not None and payload["request_digest"] != expected_request_digest:
        raise HiddenExecutionError("completion request mismatch")
    if payload["boundary"] != BOUNDARY or payload["state"] != "completed":
        raise HiddenExecutionError("completion boundary/state invalid")
    if not isinstance(payload["trusted_locator"], str) or not payload["trusted_locator"].startswith("trusted://"):
        raise HiddenExecutionError("completion locator invalid")
    text = json.dumps(value, ensure_ascii=False).lower()
    for forbidden in ("case_id", "question", "gold", "expected_rows", "verdict", "passed_count", "failed_count", "not_observed_count"):
        if forbidden in text:
            raise HiddenExecutionError(f"ordinary completion leaked {forbidden}")
    return payload


def _validate_request_usage(value: Any) -> dict[str, Any]:
    """验证一个 Hidden logical work 的逐物理请求 usage。"""

    payload = _exact(
        value,
        {"logical_work_count", "physical_request_count", "input_tokens", "output_tokens", "total_tokens", "requests"},
        "private_result.usage",
    )
    if payload["logical_work_count"] != 1 or not isinstance(payload["requests"], list) or len(payload["requests"]) > 2:
        raise HiddenExecutionError("private usage work/request count invalid")
    seen: set[str] = set()
    for raw in payload["requests"]:
        item = _exact(raw, {"stage", "provider", "model", "request_count", "input_tokens", "output_tokens", "total_tokens"}, "private_result.usage.request")
        if not all(isinstance(item[name], str) and item[name] for name in ("stage", "provider", "model")) or item["stage"] in seen:
            raise HiddenExecutionError("private usage request identity invalid")
        seen.add(item["stage"])
        if item["request_count"] != 1:
            raise HiddenExecutionError("private usage requires one physical request per stage")
        if any(isinstance(item[name], bool) or not isinstance(item[name], int) or item[name] < 0 for name in ("input_tokens", "output_tokens", "total_tokens")):
            raise HiddenExecutionError("private usage tokens invalid")
        if item["total_tokens"] != item["input_tokens"] + item["output_tokens"]:
            raise HiddenExecutionError("private request token total drifted")
    if payload["requests"] != sorted(payload["requests"], key=lambda item: item["stage"]):
        raise HiddenExecutionError("private usage requests must be sorted")
    expected = {
        "physical_request_count": len(payload["requests"]),
        "input_tokens": sum(item["input_tokens"] for item in payload["requests"]),
        "output_tokens": sum(item["output_tokens"] for item in payload["requests"]),
        "total_tokens": sum(item["total_tokens"] for item in payload["requests"]),
    }
    if any(payload[name] != amount for name, amount in expected.items()):
        raise HiddenExecutionError("private usage aggregate drifted")
    return payload


def _validate_aggregate_usage(value: Any) -> dict[str, Any]:
    payload = _exact(value, {"physical_request_count", "input_tokens", "output_tokens", "total_tokens"}, "completion.aggregate_usage")
    if any(isinstance(amount, bool) or not isinstance(amount, int) or amount < 0 for amount in payload.values()):
        raise HiddenExecutionError("completion aggregate usage must be non-negative integers")
    if payload["total_tokens"] != payload["input_tokens"] + payload["output_tokens"]:
        raise HiddenExecutionError("completion aggregate token total drifted")
    return payload


def validate_development_fixture(value: Any) -> dict[str, Any]:
    """读取 Probe 专用单例材料；它不能冒充正式四类 Hidden material。"""

    root = _exact(dict(value), {"schema", "version", "cases"}, "development_fixture")
    if root["schema"] != DEVELOPMENT_FIXTURE_SCHEMA or root["version"] != "datapilot-hidden-development-probe-v1":
        raise HiddenExecutionError("unsupported development fixture identity")
    cases = root["cases"]
    if not isinstance(cases, list) or len(cases) != 1:
        raise HiddenExecutionError("development fixture must contain exactly one case")
    case = _exact(
        cases[0],
        {"case_id", "coverage", "question", "user_role", "fixture", "oracle", "assertion"},
        "development_fixture.case",
    )
    if case["coverage"] != "numeric_time" or not all(isinstance(case[name], str) and case[name] for name in ("case_id", "question", "user_role")):
        raise HiddenExecutionError("development fixture is limited to one numeric_time case")
    fixture = _exact(case["fixture"], {"fixture_id", "setup_sql"}, "development_fixture.fixture")
    oracle = _exact(case["oracle"], {"kind", "sql", "expected_columns", "expected_rows", "expected_status"}, "development_fixture.oracle")
    assertion = _exact(case["assertion"], {"kind", "tolerance", "reason_code"}, "development_fixture.assertion")
    if (
        not isinstance(fixture["fixture_id"], str)
        or not isinstance(fixture["setup_sql"], list)
        or not fixture["setup_sql"]
        or not all(isinstance(item, str) and item.strip() for item in fixture["setup_sql"])
        or oracle["kind"] != "sqlite_result"
        or not isinstance(oracle["sql"], str)
        or not isinstance(oracle["expected_columns"], list)
        or not isinstance(oracle["expected_rows"], list)
        or oracle["expected_status"] is not None
        or assertion["kind"] != "result_match"
        or not isinstance(assertion["tolerance"], (int, float))
        or assertion["reason_code"] is not None
    ):
        raise HiddenExecutionError("development fixture SQL/oracle/assertion contract invalid")
    return {"schema": root["schema"], "version": root["version"], "cases": [dict(case)]}


def build_development_offer(material: Mapping[str, Any]) -> dict[str, Any]:
    """构造与正式 offer 同形但身份独立的 Probe 单例 offer。"""

    normalized = validate_development_fixture(material)
    return {
        "schema": "datapilot.evoloop-hidden-offer/v1",
        "version": normalized["version"],
        "private_digest": _digest(normalized),
        "coverage": ["numeric_time"],
        "expected_count": 1,
        "paired_policy": "development_probe_only",
        "retention_policy": "private_probe_results",
        "budget_policy": {"baseline_executions": 1, "candidate_executions": 0, "retries": 0},
    }


@dataclass(frozen=True)
class HiddenStoreView:
    """由私有 ledger 派生的恢复视图；started 无终态自然保持 unknown。"""

    states: dict[str, str]
    terminal_digests: dict[str, str]
    last_sequence: int
    last_digest: str


class HiddenPrivateStore:
    """私有 append-only store；ordinary reader 不需要也不应实例化它。"""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.private = self.root / "private"
        self.request_path = self.private / "request.json"
        self.events_path = self.private / "events.jsonl"
        self.completion_path = self.root / "ordinary-completion.json"

    @classmethod
    def create(cls, root: str | Path, request: Mapping[str, Any]) -> "HiddenPrivateStore":
        """创建全新的私有账本；已有目录意味着同一 Run 不得被覆盖。"""

        store = cls(root)
        if store.root.exists():
            raise FileExistsError(store.root)
        validate_execution_request(request)
        _write_atomic(store.request_path, request)
        store.events_path.touch(exist_ok=False)
        return store

    def request(self) -> dict[str, Any]:
        """从磁盘重读并验签冻结请求，禁止依赖调用者内存中的旧对象。"""

        try:
            value = json.loads(self.request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HiddenExecutionError(f"cannot read request: {exc}") from exc
        validate_execution_request(value)
        return value

    def read(self) -> HiddenStoreView:
        """校验完整 hash chain，并把 started 无终态保守投影为未完成状态。"""

        states: dict[str, str] = {}
        terminals: dict[str, str] = {}
        previous, sequence = "sha256:" + "0" * 64, 0
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise HiddenExecutionError(f"cannot read private ledger: {exc}") from exc
        for raw in lines:
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HiddenExecutionError("private ledger contains malformed event") from exc
            _exact(event, {"sequence", "previous_digest", "payload", "digest"}, "event")
            unsigned = {"sequence": event["sequence"], "previous_digest": previous, "payload": event["payload"]}
            if event["sequence"] != sequence + 1 or event["previous_digest"] != previous or event["digest"] != _digest(unsigned):
                raise HiddenExecutionError("private ledger chain mismatch")
            payload = _exact(event["payload"], {"attempt_id", "case_id", "state", "source_digest"}, "event.payload")
            case_id, state = payload["case_id"], payload["state"]
            if not all(isinstance(item, str) and item for item in (case_id, payload["attempt_id"])) or state not in {"started", "completed", "failed_before_start"}:
                raise HiddenExecutionError("private event semantics invalid")
            prior = states.get(case_id)
            if state == "started" and prior is not None:
                raise HiddenExecutionError("old private Attempt cannot be overwritten")
            if state != "started" and prior != "started":
                raise HiddenExecutionError("terminal private event requires started")
            if state == "completed":
                terminals[case_id] = _require_digest(payload["source_digest"], "event.source_digest")
            elif payload["source_digest"] is not None:
                raise HiddenExecutionError("non-completed event cannot claim source")
            states[case_id] = state
            sequence, previous = event["sequence"], event["digest"]
        return HiddenStoreView(states, terminals, sequence, previous)

    def append(self, *, attempt_id: str, case_id: str, state: str, source_digest: str | None = None) -> dict[str, Any]:
        """以 fsync 追加单个 Attempt 事件，并立即全链重读确认落盘有效。"""

        view = self.read()
        unsigned = {"sequence": view.last_sequence + 1, "previous_digest": view.last_digest, "payload": {"attempt_id": attempt_id, "case_id": case_id, "state": state, "source_digest": source_digest}}
        event = {**unsigned, "digest": _digest(unsigned)}
        with self.events_path.open("ab") as handle:
            handle.write(_canonical(event) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.read()
        return event

    def write_private_result(self, attempt_id: str, result: Mapping[str, Any]) -> str:
        """验签并原子保存私有逐题结果；同一 Attempt 的结果不可覆盖。"""

        payload = _parse(result, PRIVATE_RESULT_SCHEMA, "private_result")
        _exact(payload, {"attempt_id", "case_id", "scenario_run", "runtime", "usage", "source"}, "private_result.payload")
        if payload["attempt_id"] != attempt_id:
            raise HiddenExecutionError("private result Attempt mismatch")
        _validate_request_usage(payload["usage"])
        path = self.private / "results" / f"{attempt_id}.json"
        if path.exists():
            raise HiddenExecutionError("private result already exists")
        _write_atomic(path, result)
        return result["digest"]


def _scenario_from_material(case: Mapping[str, Any]) -> ScenarioContract:
    """把私有材料映射成 DataPilot 原生 typed assertion，不建立第二套 scorer。"""

    coverage, oracle, assertion = case["coverage"], case["oracle"], case["assertion"]
    if coverage in {"numeric_time", "cross_table"}:
        contract = AssertionContract(
            "hidden-required", "result_match",
            ResultMatchSpec(oracle["sql"], tuple(oracle["expected_columns"]), float(assertion["tolerance"] or 0.000001)),
        )
    elif coverage == "safety_block":
        contract = AssertionContract("hidden-required", "safety_block", None)
    else:
        contract = AssertionContract(
            "hidden-required", "expected_rejection",
            ExpectedRejectionSpec((assertion["reason_code"],), "plan_validation"),
        )
    return ScenarioContract(case["case_id"], case["question"], case["user_role"], "manual_lab", (coverage,), (contract,))


def _provider_usage_from_scenario_run(scenario_run: Any) -> dict[str, Any]:
    """从 DataPilot 原生 TraceStep 的 ``llm_call`` 读取真实 provider usage。"""

    requests: list[dict[str, Any]] = []
    for step in scenario_run.evidence.trace_steps:
        # DataPilot 的 ScenarioRun 在 API/投影边界可能保留 TraceStep dataclass，也可能已经
        # 通过 ``dataclass_payload`` 变成 dict。二者语义相同，Hidden usage seam 必须都能读；
        # 否则业务失败路径虽有完整 provider usage，却会被误记为 started_unknown。
        metadata = step.get("metadata") if isinstance(step, Mapping) else step.metadata
        if not isinstance(metadata, Mapping) or "llm_call" not in metadata:
            continue
        call = _exact(
            metadata["llm_call"],
            {
                "stage", "provider", "model", "configured_timeout_seconds", "max_retries", "attempt_count",
                "prompt_length", "system_prompt_length", "final_outcome", "attempts", "usage",
            },
            "scenario_run.trace.llm_call",
        )
        if call["max_retries"] != 0 or call["attempt_count"] != 1:
            raise HiddenExecutionError("Hidden provider retry/attempt identity drifted")
        attempts = call["attempts"]
        if not isinstance(attempts, list) or len(attempts) != 1:
            raise HiddenExecutionError("Hidden llm_call must contain one physical request")
        attempt = _exact(attempts[0], {"attempt", "latency_ms", "outcome", "error_subtype", "retryable", "error_message"}, "scenario_run.trace.llm_call.attempt")
        if attempt["attempt"] != 1 or attempt["retryable"] is not False:
            raise HiddenExecutionError("Hidden physical request identity drifted")
        usage = _exact(call["usage"], {"observed", "request_count", "prompt_tokens", "completion_tokens", "total_tokens"}, "scenario_run.trace.llm_call.usage")
        if usage["observed"] is not True or usage["request_count"] != 1:
            raise HiddenExecutionError("started Hidden provider request requires observed usage")
        requests.append({
            "stage": call["stage"], "provider": call["provider"], "model": call["model"],
            "request_count": 1, "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"], "total_tokens": usage["total_tokens"],
        })
    requests.sort(key=lambda item: item["stage"])
    value = {
        "logical_work_count": 1,
        "physical_request_count": len(requests),
        "input_tokens": sum(item["input_tokens"] for item in requests),
        "output_tokens": sum(item["output_tokens"] for item in requests),
        "total_tokens": sum(item["total_tokens"] for item in requests),
        "requests": requests,
    }
    _validate_request_usage(value)
    return value


class DataPilotHiddenRuntime:
    """真实 DataPilot API/SQLite/oracle/assertion adapter；每个 work 一个隔离 snapshot。"""

    def __init__(self, *, trace_root: Path):
        self.factory = SQLiteRunEnvironmentFactory(trace_root=trace_root)

    def __call__(self, case: Mapping[str, Any], request: Mapping[str, Any], attempt_id: str) -> dict[str, Any]:
        spec = EvalRunSpec(
            run_id=f"{request['run_id']}-{attempt_id}", scenario_ids=(case["case_id"],),
            execution_protocol=ExecutionProtocol("new_text2sql", "weighted", 1),
            requested_runtime_constraints={
                "llm_provider": "qwen", "llm_model": "qwen3.7-plus", "schema_vector_backend": "inmemory",
                "schema_embedding_provider": "deterministic", "schema_fusion_strategy": "weighted",
                "llm_max_retries": 0, "oracle_fixture_identity": case["fixture"]["fixture_id"],
            },
            oracle_fixture_identity=case["fixture"]["fixture_id"],
        )
        environment = self.factory.create(spec)
        try:
            environment.install_trusted_fixture(case["fixture"]["setup_sql"])
            scenario = _scenario_from_material(case)
            if scenario.assertions[0].kind == "result_match":
                rows = [dict(item) for item in environment.oracle.execute(case["oracle"]["sql"])]
                expected = [dict(zip(case["oracle"]["expected_columns"], row)) for row in case["oracle"]["expected_rows"]]
                if rows != expected:
                    raise HiddenBeforeProviderError("private fixture/oracle drift")
            scenario_run = evaluate_scenario_once(environment, spec, scenario, 1)
            return _envelope(PRIVATE_RESULT_SCHEMA, {
                "attempt_id": attempt_id, "case_id": case["case_id"], "scenario_run": dataclass_payload(scenario_run),
                "runtime": dataclass_payload(environment.resolved_runtime_identity),
                "usage": _provider_usage_from_scenario_run(scenario_run),
                "source": {"execution_status": scenario_run.evidence.execution_status, "physical_attempts": scenario_run.evidence.physical_attempts, "trace_present": bool(scenario_run.evidence.trace_steps)},
            })
        finally:
            environment.close()


def execute_hidden_baseline(
    *, material_value: Mapping[str, Any], request: Mapping[str, Any], store: HiddenPrivateStore,
    executor: Callable[[Mapping[str, Any], Mapping[str, Any], str], Mapping[str, Any]],
) -> dict[str, Any]:
    """执行或保守恢复一侧 Hidden；全部私有来源重读后才发布 completion。"""

    request_payload = validate_execution_request(request)
    if request_payload["purpose"] == "development_probe":
        material = validate_development_fixture(dict(material_value))
        offer = build_development_offer(material)
    else:
        material = validate_hidden_material(dict(material_value))
        offer = build_public_offer(material)
    if store.request() != request or request_payload["private_digest"] != _digest(material):
        raise HiddenExecutionError("stored request or private material drifted")
    if request_payload["offer_digest"] != _digest(offer):
        raise HiddenExecutionError("request offer drifted")
    if store.completion_path.exists():
        value = json.loads(store.completion_path.read_text(encoding="utf-8"))
        validate_ordinary_completion(value, expected_request_digest=request["digest"])
        return value

    for index, case in enumerate(material["cases"]):
        state = store.read().states.get(case["case_id"])
        if state == "completed":
            continue
        if state is not None:
            raise HiddenExecutionError(f"private work cannot resume automatically from {state}")
        attempt_id = f"ha-{index:02d}-{uuid.uuid4().hex[:12]}"
        store.append(attempt_id=attempt_id, case_id=case["case_id"], state="started")
        try:
            result = dict(executor(case, request_payload, attempt_id))
        except HiddenBeforeProviderError:
            store.append(attempt_id=attempt_id, case_id=case["case_id"], state="failed_before_start")
            raise
        source_digest = store.write_private_result(attempt_id, result)
        store.append(attempt_id=attempt_id, case_id=case["case_id"], state="completed", source_digest=source_digest)

    view = store.read()
    expected_ids = {item["case_id"] for item in material["cases"]}
    if set(view.terminal_digests) != expected_ids or any(state != "completed" for state in view.states.values()):
        raise HiddenExecutionError("private execution incomplete")
    # 步骤 3：从私有 result 重建批次 usage；ordinary 侧只得到资源总量和账本摘要。
    private_results: list[tuple[str, dict[str, Any]]] = []
    for path in sorted((store.private / "results").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HiddenExecutionError(f"cannot reopen private result: {exc}") from exc
        payload = _parse(value, PRIVATE_RESULT_SCHEMA, "private_result")
        _exact(payload, {"attempt_id", "case_id", "scenario_run", "runtime", "usage", "source"}, "private_result.payload")
        _validate_request_usage(payload["usage"])
        private_results.append((value["digest"], payload["usage"]))
    if {digest for digest, _ in private_results} != set(view.terminal_digests.values()):
        raise HiddenExecutionError("private result files and terminal ledger differ")
    aggregate_usage = {
        "physical_request_count": sum(usage["physical_request_count"] for _, usage in private_results),
        "input_tokens": sum(usage["input_tokens"] for _, usage in private_results),
        "output_tokens": sum(usage["output_tokens"] for _, usage in private_results),
        "total_tokens": sum(usage["total_tokens"] for _, usage in private_results),
    }
    _validate_aggregate_usage(aggregate_usage)
    budget = request_payload["budget"]
    if (
        len(private_results) > budget["max_logical_works"]
        or aggregate_usage["physical_request_count"] > budget["max_physical_requests"]
        or aggregate_usage["total_tokens"] > budget["max_observed_tokens"]
    ):
        raise HiddenExecutionError("Hidden execution exceeded frozen usage budget")
    usage_ledger_digest = _digest([
        {"private_result_digest": digest, "usage_digest": _digest(usage)}
        for digest, usage in sorted(private_results)
    ])
    completion = _envelope(COMPLETION_SCHEMA, {
        "version": offer["version"], "request_digest": request["digest"], "offer_digest": request_payload["offer_digest"],
        "private_digest": request_payload["private_digest"], "candidate_digest": request_payload["candidate_digest"],
        "authorization_digest": request_payload["authorization_digest"], "world_digest": _digest(request_payload["world"]),
        "runtime_digest": request_payload["world"]["runtime_digest"], "budget_digest": _digest(request_payload["budget"]),
        "attempt_coverage_digest": _digest({"ledger": view.last_digest, "all_terminal": True}),
        "private_result_digest": _digest(sorted(view.terminal_digests.values())),
        "aggregate_usage": aggregate_usage, "usage_ledger_digest": usage_ledger_digest,
        "trusted_locator": f"trusted://datapilot-hidden/{request_payload['run_id']}", "boundary": BOUNDARY, "state": "completed",
    })
    validate_ordinary_completion(completion, expected_request_digest=request["digest"])
    _write_atomic(store.completion_path, completion)
    return completion
