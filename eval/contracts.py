"""M27 的新评测合同：把“题目、执行、断言、产物”分成可单独演进的类型。

旧 ``EvalCase`` 是一个围绕单一 ``check_type`` 的 DTO；为了检查结果、Context、Plan 和
Trace，过去只能把同一题复制多遍。这里的 ``ScenarioContract`` 改为一题多个 typed assertion。

★ 本文件刻意不认识 FastAPI、SQLite、Markdown 或 LangFuse。它只定义稳定的数据形状，避免
调用方把旧 runner 的 ``review_required`` / ``phase3a_blocking`` 等历史语义带进新合同。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import re
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit


Classification = Literal["core", "stress", "manual_lab"]
ExecutionStatus = Literal["completed", "rejected", "pipeline_error", "external_unavailable"]
AssertionStatus = Literal["passed", "failed", "not_observed"]
RunStatus = Literal["running", "completed", "interrupted", "failed"]

# M27 v3 把 Schema Context 的物理字段、metric key、输出 alias 三个命名空间彻底分开，
# 并在 catalog 加载时验证合同确实能由当前 domain schema 满足。旧 v1/v2 artifact 仍可
# 只读复核，但合同 hash 和判分语义不同，不能与 v3 直接比较。
CONTRACT_VERSION = "m27-v4"
LEGACY_REVIEWABLE_CONTRACT_VERSIONS = frozenset({"m27-v1", "m27-v2", "m27-v3"})
ARTIFACT_SCHEMA_VERSION = "m27-artifact-v2"
LEGACY_ARTIFACT_SCHEMA_VERSION = "m27-artifact-v1"
PROJECTOR_VERSION = "m27-projector-v2"

ObservabilityStatus = Literal["disabled", "not_observed", "succeeded", "failed"]
ObservabilitySpanMode = Literal["live", "post_hoc"]
_OBSERVABILITY_FIELDS = {
    "backend", "status", "datapilot_trace_id", "trace_id", "host_identity", "project_identity", "span_mode"
}
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ResultMatchSpec:
    """结果集 oracle：reference SQL 与候选 SQL 共用同一 RunEnvironment snapshot。"""

    reference_sql: str
    columns: tuple[str, ...]
    tolerance: float = 0.000001
    column_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    order_insensitive: bool = False


@dataclass(frozen=True)
class OutputContractSpec:
    """用户可见列的精确集合和顺序；它不替代结果行值的 result assertion。"""

    columns: tuple[str, ...]
    column_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaContextSpec:
    """局部 SchemaGraph 合同；alternatives 表示任一明确业务口径可接受。"""

    alternatives: tuple[dict[str, tuple[str, ...]], ...] = ()
    required_tables: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    required_metrics: tuple[str, ...] = ()
    required_join_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryPlanSpec:
    """QueryPlan 的可观察结构合同，消费 trace 中的结构化 plan 摘要。"""

    tables: tuple[str, ...] = ()
    joins: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()
    output_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class TraceCompleteSpec:
    """Trace 步骤合同；顺序有业务含义，因此保留声明顺序。"""

    required_steps: tuple[tuple[str, str], ...]
    allow_skipped: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectedRejectionSpec:
    """产品明确不支持的需求应如何被结构化拒绝。"""

    issue_tags: tuple[str, ...]
    blocked_via: str


@dataclass(frozen=True)
class JoinPathSpec:
    """JoinPath 的 relation id 合同；检查计划而不是把最终结果偶然正确当作连表正确。"""

    relation_ids: tuple[str, ...]


@dataclass(frozen=True)
class MetricMappingSpec:
    """指标绑定的最小可裁决合同。

    当前 QueryPlan 没有自由文本公式 AST；所以先严格检查计划选择的表、字段和 metric key，
    不把 ``SUM`` 字符串匹配伪装成完整指标证明。
    """

    tables: tuple[str, ...]
    columns: tuple[str, ...]
    metrics: tuple[str, ...] = ()


AssertionSpec = (
    ResultMatchSpec
    | OutputContractSpec
    | SchemaContextSpec
    | QueryPlanSpec
    | TraceCompleteSpec
    | ExpectedRejectionSpec
    | JoinPathSpec
    | MetricMappingSpec
    | None
)


@dataclass(frozen=True)
class AssertionContract:
    """一条 typed assertion；``kind`` 与 ``spec`` 的配对由 catalog loader 严格校验。"""

    assertion_id: str
    kind: str
    spec: AssertionSpec
    authority_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioContract:
    """唯一业务问题及其多条 assertion。"""

    scenario_id: str
    question: str
    user_role: str
    classification: Classification
    tags: tuple[str, ...]
    assertions: tuple[AssertionContract, ...]
    authority_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    """完整 canonical catalog；只由严格 loader 构造。"""

    contract_version: str
    scenarios: tuple[ScenarioContract, ...]
    catalog_hash: str


@dataclass(frozen=True)
class ExecutionProtocol:
    """一次 run 的执行方式；retry/timeout 仅记录请求值，不改变全局默认。"""

    pipeline_mode: Literal["baseline", "new_text2sql"] = "new_text2sql"
    schema_fusion_strategy: Literal["weighted", "rrf"] = "weighted"
    replicate_count: int = 1


@dataclass(frozen=True)
class EvalRunSpec:
    """Evaluator 的唯一输入。

    Exit policy 不属于它：同一份 EvalRun 的 gate fact 可以被本地开发和 CI 以不同策略消费。
    """

    run_id: str
    scenario_ids: tuple[str, ...]
    execution_protocol: ExecutionProtocol = field(default_factory=ExecutionProtocol)
    requested_runtime_constraints: dict[str, Any] = field(default_factory=dict)
    oracle_fixture_identity: str = "sqlite_deterministic_seed"
    # 只冻结 selector / gate 的声明，不把其 effect 写入 AssertionResult。
    suite_policy: dict[str, Any] = field(default_factory=dict)
    selected_contract_hash: str = ""
    suite_policy_hash: str = ""
    run_spec_hash: str = ""


@dataclass(frozen=True)
class ResolvedRuntimeIdentity:
    """实际运行事实；报告与后续基线比较只应消费它，而非命令行表象。"""

    values: dict[str, Any]


@dataclass(frozen=True)
class ObservabilityEvidence:
    """一次 DataPilot execution 的外部观测引用；不携带 URL 或任何 key。"""

    backend: Literal["langfuse"]
    status: ObservabilityStatus
    datapilot_trace_id: str | None
    trace_id: str | None
    host_identity: str | None
    project_identity: str | None
    span_mode: ObservabilitySpanMode | None


@dataclass(frozen=True)
class ExecutionEvidence:
    """一个 scenario replicate 的共享运行事实，所有 scorer 都只读它。"""

    run_id: str
    scenario_id: str
    replicate_id: int
    execution_status: ExecutionStatus
    status_code: int | None
    response: dict[str, Any]
    trace_steps: tuple[dict[str, Any], ...]
    # 当前 adapter 没有内部 retry；显式保留 1，让未来 retry 不必改 artifact schema。
    physical_attempts: int = 1
    expected_rows: tuple[dict[str, Any], ...] | None = None
    oracle_error: str | None = None
    observability: ObservabilityEvidence | None = None


@dataclass(frozen=True)
class AssertionResult:
    """断言观察事实；不掺入 required/advisory/excluded 等 suite policy。"""

    assertion_id: str
    kind: str
    status: AssertionStatus
    reason: str
    issue_tags: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioRun:
    """一题一次 replicate 的执行与断言结果。"""

    scenario_id: str
    replicate_id: int
    evidence: ExecutionEvidence
    assertion_results: tuple[AssertionResult, ...]


@dataclass(frozen=True)
class EvalRun:
    """M27 的结构化事实源；不保存可从明细重新推导的报告汇总。"""

    run_id: str
    run_status: RunStatus
    contract_version: str
    artifact_schema_version: str
    catalog_hash: str
    selected_contract_hash: str
    suite_policy_hash: str
    suite_policy: dict[str, Any]
    run_spec_hash: str
    requested_runtime_constraints: dict[str, Any]
    resolved_runtime_identity: ResolvedRuntimeIdentity | None
    scenario_runs: tuple[ScenarioRun, ...]
    failure_reason: str | None = None


def dataclass_payload(value: Any) -> Any:
    """把嵌套 dataclass 转成 JSON 友好对象，供 checkpoint/artifact adapter 复用。"""

    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_payload(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): dataclass_payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [dataclass_payload(item) for item in value]
    return value


def safe_eval_run_payload(run: EvalRun) -> dict[str, Any]:
    """构造长期 EvalRun artifact 的 allowlist 表示。

    checkpoint 可以保留短期 raw evidence 以便崩溃排障；而 ``eval/reports`` 中的 completed
    artifact 默认不保存 answer、完整 rows、完整 prompt/response 或凭证。自动 scorer 所需的
    pass/fail、列合同、row count、结构化差异和 trace 摘要仍随 AssertionResult 保留。
    """

    payload = dataclass_payload(run)
    protected = {"email", "phone", "authorization", "api_key", "token", "password"}
    for scenario_run in payload.get("scenario_runs", []):
        evidence = scenario_run.get("evidence", {})
        observability = evidence.get("observability")
        if not isinstance(observability, dict):
            raise ValueError("m27-v4 execution evidence requires observability")
        expected_trace_id = str(observability.get("datapilot_trace_id") or "")
        evidence["observability"] = dataclass_payload(normalize_source_observability(
            observability,
            contract_version=run.contract_version,
            artifact_schema_version=run.artifact_schema_version,
            expected_datapilot_trace_id=expected_trace_id,
        ))
        response = evidence.get("response", {})
        if isinstance(response, dict):
            cost = response.get("cost") if isinstance(response.get("cost"), dict) else {}
            evidence["response"] = {
                key: _safe_response_value(key, response.get(key), protected)
                for key in ("route", "safety_status", "error_type", "issue_tags", "columns", "tables_used")
                if key in response
            }
            if cost:
                evidence["response"]["cost"] = {
                    key: value for key, value in cost.items() if key in {"latency_ms", "input_tokens", "output_tokens", "total_tokens"}
                }
            evidence["candidate_row_count"] = len(response.get("rows") or [])
        # reference rows 只在本次内存评分使用；长期 artifact 用 assertion evidence 表达比较结论。
        evidence["expected_rows"] = None
        evidence["trace_steps"] = [
            {
                "step_type": step.get("step_type") or step.get("name"),
                "status": step.get("status"),
                "error_type": step.get("error_type"),
                "metadata": _safe_trace_metadata(step.get("metadata") or {}, protected),
            }
            for step in evidence.get("trace_steps") or []
            if isinstance(step, dict)
        ]
    return payload


def build_observability_evidence(trace_record: dict[str, Any], settings: Any) -> ObservabilityEvidence:
    """从同一 JSONL trace 构造正式来源引用，避免 artifact 再猜 Cloud 状态。"""

    datapilot_trace_id = _require_opaque(trace_record.get("trace_id"), "datapilot_trace_id")
    if not settings.langfuse_enabled:
        return ObservabilityEvidence("langfuse", "disabled", datapilot_trace_id, None, None, None, None)
    write_status = trace_record.get("langfuse_write_status")
    if write_status == "failed":
        return ObservabilityEvidence("langfuse", "failed", datapilot_trace_id, None, None, None, None)
    if write_status != "ok":
        return ObservabilityEvidence("langfuse", "not_observed", datapilot_trace_id, None, None, None, None)
    candidate = ObservabilityEvidence(
        backend="langfuse",
        status="succeeded",
        datapilot_trace_id=datapilot_trace_id,
        trace_id=trace_record.get("langfuse_trace_id"),
        host_identity=langfuse_host_identity(settings.langfuse_base_url),
        project_identity=_sha256_identity(settings.langfuse_public_key, "LANGFUSE_PUBLIC_KEY"),
        span_mode=trace_record.get("langfuse_span_mode"),
    )
    return normalize_source_observability(
        dataclass_payload(candidate),
        contract_version=CONTRACT_VERSION,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        expected_datapilot_trace_id=datapilot_trace_id,
    )


def normalize_source_observability(
    raw: dict[str, Any] | None,
    *,
    contract_version: str,
    artifact_schema_version: str,
    expected_datapilot_trace_id: str,
) -> ObservabilityEvidence:
    """严格读取新来源，并把旧 m27 artifact 显式归一为 ``not_observed``。"""

    if contract_version in LEGACY_REVIEWABLE_CONTRACT_VERSIONS:
        if artifact_schema_version != LEGACY_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("legacy contract/artifact schema mismatch")
        if raw is not None:
            raise ValueError("legacy exact fields must not contain observability")
        return ObservabilityEvidence("langfuse", "not_observed", None, None, None, None, None)
    expected = _require_opaque(expected_datapilot_trace_id, "expected datapilot trace binding")
    if contract_version != CONTRACT_VERSION or artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
        raise ValueError("unsupported contract/artifact schema pair")
    if not isinstance(raw, dict) or set(raw) != _OBSERVABILITY_FIELDS:
        raise ValueError("observability must contain exact fields")
    if raw.get("backend") != "langfuse" or raw.get("status") not in {"disabled", "not_observed", "succeeded", "failed"}:
        raise ValueError("observability backend/status is invalid")
    datapilot_trace_id = _require_opaque(raw.get("datapilot_trace_id"), "datapilot_trace_id")
    if datapilot_trace_id != expected:
        raise ValueError("observability datapilot trace binding mismatch")
    status = raw["status"]
    references = (raw.get("trace_id"), raw.get("host_identity"), raw.get("project_identity"), raw.get("span_mode"))
    if status == "succeeded":
        if any(value is None for value in references):
            raise ValueError("succeeded observability requires trace/project/span references")
        trace_id = _require_opaque(raw.get("trace_id"), "trace_id")
        host_identity = _require_sha256(raw.get("host_identity"), "host_identity")
        project_identity = _require_sha256(raw.get("project_identity"), "project_identity")
        span_mode = raw.get("span_mode")
        if span_mode not in {"live", "post_hoc"}:
            raise ValueError("succeeded observability requires a valid span_mode")
    else:
        if any(value is not None for value in references):
            raise ValueError("non-succeeded observability must not contain external references")
        trace_id = host_identity = project_identity = span_mode = None
    return ObservabilityEvidence("langfuse", status, datapilot_trace_id, trace_id, host_identity, project_identity, span_mode)


def normalize_langfuse_host(host: str) -> str:
    """规范化受信 host 后再做摘要；不把 URL 本身写进 artifact。"""

    if not isinstance(host, str) or not host.strip():
        raise ValueError("LANGFUSE_BASE_URL is required")
    parsed = urlsplit(host.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("LANGFUSE_BASE_URL must be an http(s) origin without credentials")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def langfuse_host_identity(host: str) -> str:
    return hashlib.sha256(normalize_langfuse_host(host).encode("utf-8")).hexdigest()


def _sha256_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_opaque(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        raise ValueError(f"{label} must be an opaque identifier")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 identity")
    return value


def _safe_response_value(key: str, value: Any, protected: set[str]) -> Any:
    """处理 response 白名单字段中显而易见的敏感值。"""
    if key.lower() in protected:
        return "[redacted]"
    if isinstance(value, list):
        return ["[redacted]" if str(item).lower() in protected else item for item in value]
    return value


def _safe_trace_metadata(metadata: dict[str, Any], protected: set[str]) -> dict[str, Any]:
    """只保留 M27 assertion 常用的结构化 metadata，拒绝 LLM/raw SQL 等开放字段。"""

    allowed = {"tables", "fields", "metrics", "relation_ids", "relations", "plan_steps", "issue_tags", "errors", "blocked_via", "row_count", "column_count", "error_subtype"}
    result: dict[str, Any] = {}
    for key in allowed & set(metadata):
        value = metadata[key]
        result[key] = "[redacted]" if key.lower() in protected else value
    return result
