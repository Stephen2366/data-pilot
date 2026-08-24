"""LLM SQL Generator：调用 OpenAI-compatible provider，并解析 QueryPlan / SQL。

★ provider transport、attempt 与 retry 由 M25 ``llm_call`` module 统一执行；本模块专注
DataPilot 的业务 prompt、结构化解析和 SQL/计划合同，不在 parser 里复制网络可靠性逻辑。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import get_settings
from engine.governance import (
    DEFAULT_OUTBOUND_POLICY,
    GovernanceError,
    OutboundPolicy,
    OutboundRequest,
    require_outbound,
)
from engine.nl2sql.fidelity_contract import SQLPlanFidelityResult, evaluate_sql_plan_fidelity
from engine.nl2sql.llm_call import LLMCallEvidence, LLMGenerationError, execute_llm_call
from engine.nl2sql.planner import QueryPlan, QueryPlanStep
from engine.nl2sql.prompt import build_local_schema_sql_prompt, build_query_plan_prompt, build_sql_prompt
from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.objects import SchemaGraph

PostJson = Callable[[str, dict[str, str], dict[str, object], float], dict[str, object]]


def _post_json(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict[str, object]:
    """发送 JSON POST 请求；provider 测试可替换这个 transport，避免真实联网。"""

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class QueryPlanExtractionError(LLMGenerationError):
    """QueryPlan 解析失败，固定映射到 M10 的 `invalid_query_plan`。"""

    issue_tag = "invalid_query_plan"


class SQLPlanContractError(LLMGenerationError):
    """SQL 没有履行已验证 QueryPlan 的排序 / limit / projection 契约。"""

    issue_tag = "sql_plan_contract_failed"

    def __init__(self, message: str, *, contract_result: SQLPlanFidelityResult) -> None:
        super().__init__(
            message,
            stage="sql_generation",
            error_subtype=f"plan_contract_{contract_result.reason_code}",
        )
        self.contract_result = contract_result
        categories = {issue.category for issue in contract_result.issues}
        if contract_result.status == "indeterminate":
            self.issue_tag = "sql_plan_contract_indeterminate"
        elif categories == {"projection"}:
            self.issue_tag = "output_projection_contract_failed"


class LLMClient(Protocol):
    """最小 LLM client 协议，方便测试替换真实 DeepSeek 调用。"""

    def complete(
        self, *, prompt: str, system_prompt: str | None = None, node_purpose: str = "sql_generation"
    ) -> str:
        """输入完整 prompt，返回模型原始文本。"""


class GeneratedSQL(BaseModel):
    """LLM 生成 SQL 的结构化结果。"""

    sql: str = Field(min_length=1)
    tables_used: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning_summary: str = ""


class OpenAICompatibleChatClient:
    """OpenAI-compatible chat completion 客户端基类。

    ★ DeepSeek 和 Qwen 都提供兼容 `/chat/completions` 的接口。把 HTTP 契约收在这里，
    后续做主模型 A/B 时只切 provider 配置，不复制整套网络调用和错误处理。
    """

    provider_label = "LLM"
    default_base_url = ""
    default_model = ""
    missing_key_message = "LLM API key 缺失。"
    outbound_receiver = "unknown_chat"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        post_json: PostJson = _post_json,
        timeout: float = 45.0,
        max_retries: int = 0,
        retry_backoff_seconds: float = 1.0,
        outbound_policy: OutboundPolicy | None = DEFAULT_OUTBOUND_POLICY,
        outbound_data_class: str = "text2sql_prompt",
        enable_thinking: bool | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") or self.default_base_url
        self.model = model or self.default_model
        self._post_json = post_json
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._outbound_policy = outbound_policy
        self._outbound_data_class = outbound_data_class
        if max_tokens is not None and max_tokens < 1:
            raise ValueError("max_tokens 必须为正数")
        # ``None`` 表示完全沿用 provider 默认，避免 M34 改到既有 Text2SQL/Qwen 行为。
        self.enable_thinking = enable_thinking
        self.max_tokens = max_tokens
        # 只记录计费/可靠性所需的数字，不保存 prompt、response 或 API key。
        self.request_count = 0
        self.successful_response_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def complete(
        self, *, prompt: str, system_prompt: str | None = None, node_purpose: str = "sql_generation"
    ) -> str:
        """调用 OpenAI-compatible 接口；网络前必须通过精确用途的出站裁决。"""

        if not self.api_key:
            raise LLMGenerationError(self.missing_key_message)

        # 步骤 1：按 OpenAI-compatible chat 格式组装请求 -------------------------------
        resolved_system_prompt = system_prompt or "你只负责把中文业务问题转换为安全的单条 SELECT SQL。"
        try:
            require_outbound(
                OutboundRequest(
                    receiver=self.outbound_receiver,
                    node_purpose=node_purpose,
                    data_class=self._outbound_data_class,
                    fields=frozenset({"prompt", "system_prompt", "model"}),
                    fallback_available=False,
                ),
                policy=self._outbound_policy,
            )
        except GovernanceError as exc:
            raise LLMGenerationError(
                f"{self.provider_label} 出站策略拒绝本次调用。",
                stage=node_purpose,
                error_subtype="outbound_denied",
            ) from exc
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": resolved_system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        # 直接 HTTP 调用时，百炼要求非标准参数与 model/messages 同级放在 body 顶层。
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        # 步骤 2：真实网络调用只在这里发生；失败统一转成 LLMGenerationError。
        self.request_count += 1
        try:
            response_payload = self._post_json(
                f"{self.base_url}/chat/completions",
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                payload,
                self.timeout,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            normalized_detail = detail.lower()
            if "arrearage" in normalized_detail:
                subtype = "account_arrearage"
            elif exc.code == 429:
                subtype = "rate_limited"
            else:
                subtype = f"http_{exc.code}"
            raise LLMGenerationError(
                f"{self.provider_label} HTTP 调用失败：{exc.code} {detail[:300]}",
                error_subtype=subtype,
                retryable=exc.code in {408, 429} or exc.code >= 500,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            error_text = str(exc).lower()
            if isinstance(exc, TimeoutError) or "timed out" in error_text:
                subtype = "timeout"
            elif "winerror 10013" in error_text:
                subtype = "network_permission_denied"
            else:
                subtype = "network_error"
            raise LLMGenerationError(
                f"{self.provider_label} 网络调用失败：{exc}",
                error_subtype=subtype,
                retryable=subtype != "network_permission_denied",
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMGenerationError(
                f"{self.provider_label} 返回非 JSON：{exc}", error_subtype="transport_response_invalid_json"
            ) from exc

        # 步骤 3：只把模型正文交给上层 parser；attempt 证据由 llm_call 统一产出。
        try:
            content = str(response_payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGenerationError(
                f"{self.provider_label} 返回结构缺少 choices/message/content：{response_payload}",
                error_subtype="transport_response_contract",
            ) from exc
        usage = response_payload.get("usage", {})
        if isinstance(usage, dict):
            self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            self.total_tokens += int(usage.get("total_tokens", 0) or 0)
        self.successful_response_count += 1
        return content


class DeepSeekChatClient(OpenAICompatibleChatClient):
    """DeepSeek OpenAI-compatible chat completion 客户端。"""

    provider_label = "DeepSeek"
    default_base_url = "https://api.deepseek.com"
    # ★ 默认模型只兜底；.env 的 LLM_MODEL 会优先覆盖（见 get_default_llm_client）。
    # 2026-07-31 主模型从 deepseek-v4-pro 切换为 deepseek-v4-flash（更快更便宜的非推理模型）。
    default_model = "deepseek-v4-flash"
    missing_key_message = "DeepSeek API key 缺失，请配置 DEEPSEEK_API_KEY 或 LLM_API_KEY。"
    outbound_receiver = "deepseek_chat"


class QwenChatClient(OpenAICompatibleChatClient):
    """Qwen / DashScope OpenAI-compatible chat completion 客户端。"""

    provider_label = "Qwen"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_model = "qwen3.7-plus"
    missing_key_message = "Qwen API key 缺失，请配置 DASHSCOPE_API_KEY。"
    outbound_receiver = "qwen_chat"


def get_default_llm_client() -> LLMClient:
    """按当前配置创建默认 LLM client。

    如果 `.env` 仍是 `LLM_PROVIDER=mock`，但已经配置 DeepSeek key，则按 M4 确认方案走
    DeepSeek 主路径，避免因为旧默认值误判为只能 mock。
    """

    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider not in {"deepseek", "mock", "qwen"}:
        raise LLMGenerationError(f"当前仅支持 DeepSeek / Qwen 主模型，LLM_PROVIDER={settings.llm_provider}。")

    if provider == "qwen":
        model = settings.qwen_model or (settings.llm_model if settings.llm_model != "mock-sql-generator" else "qwen3.7-plus")
        return QwenChatClient(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
        )

    api_key = settings.deepseek_api_key or settings.llm_api_key
    # ★ LLM_MODEL 是主模型单一事实源；"mock-sql-generator" 只是未配置时的占位，此时兜底用默认模型。
    model = settings.llm_model if settings.llm_model != "mock-sql-generator" else "deepseek-v4-flash"
    return DeepSeekChatClient(
        api_key=api_key,
        base_url=settings.deepseek_base_url or "https://api.deepseek.com",
        model=model,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
    )


LLMEvidenceSink = Callable[[LLMCallEvidence], None]


def _complete_with_evidence(
    client: LLMClient,
    *,
    prompt: str,
    system_prompt: str,
    stage: str,
    evidence_sink: LLMEvidenceSink | None,
) -> str:
    """通过深调用 module 执行，并把成功证据显式交给当前请求的 caller。"""

    result = execute_llm_call(client, prompt=prompt, system_prompt=system_prompt, stage=stage)
    if evidence_sink is not None:
        evidence_sink(result.evidence)
    return result.content


def extract_generated_sql(raw_text: str) -> GeneratedSQL:
    """从模型原始输出中提取 `GeneratedSQL`。

    优先解析结构化 JSON；如果模型返回了 ```sql fenced code block，则降级只提取 SQL，并
    把 confidence 设为 0.5，表示格式可信度一般。
    """

    stripped = raw_text.strip()

    # 步骤 1：优先走约定的 JSON 结构。
    try:
        payload = json.loads(stripped)
        return GeneratedSQL(**payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # 步骤 2：兼容模型偶尔返回 markdown fenced SQL 的情况。
    fenced_match = re.search(r"```(?:sql)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        return GeneratedSQL(sql=fenced_match.group(1).strip(), confidence=0.5, reasoning_summary="从 fenced SQL 提取。")

    # 步骤 3：最后兜底纯 SQL 文本；再失败就交给调用方结构化拦截。
    if stripped.lower().startswith("select"):
        return GeneratedSQL(sql=stripped, confidence=0.5, reasoning_summary="从纯 SQL 文本提取。")

    message = "无法从 LLM 输出中提取 SQL。"
    raise LLMGenerationError(
        message,
        raw_response_preview=stripped[:500],
        parse_error=message,
    )


def _extract_json_object(raw_text: str) -> str:
    """从 LLM 原文中提取 JSON 对象，兼容 fenced JSON 和少量前后解释。"""

    stripped = raw_text.strip()

    # 步骤 1：优先兼容 ```json ... ```，这是真实模型最常见的格式波动。--------------
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    # 步骤 2：如果模型在 JSON 前后加了短解释，只取第一个对象边界。-------------------
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]
    return stripped


def extract_query_plan(raw_text: str) -> QueryPlan:
    """从模型原始输出中提取 M10 `QueryPlan`。

    与 SQL 提取器不同，这里不接受纯文本兜底；计划不可解析就返回 `invalid_query_plan`，
    避免新链路悄悄降级回不可校验的自由文本。
    """

    try:
        return QueryPlan.model_validate_json(_extract_json_object(raw_text))
    except (ValueError, TypeError) as exc:
        message = "无法从 LLM 输出中提取 QueryPlan。"
        raise QueryPlanExtractionError(
            message,
            raw_response_preview=raw_text.strip()[:500],
            parse_error=f"{message} {exc}",
        ) from exc


def _add_error_context(
    exc: LLMGenerationError,
    *,
    stage: str,
    prompt: str,
    raw_text: str | None = None,
) -> LLMGenerationError:
    """给 LLM 异常补充 trace 需要的上下文，同时保留原异常类型。"""

    exc.stage = exc.stage or stage
    exc.prompt_length = exc.prompt_length or len(prompt)
    if raw_text is not None and not exc.raw_response_preview:
        exc.raw_response_preview = raw_text.strip()[:500]
    if not exc.parse_error:
        exc.parse_error = str(exc)
    if not exc.error_subtype:
        exc.error_subtype = "response_parse_error"
    return exc


def generate_sql(
    *,
    question: str,
    user_role: str,
    domain_schema: DomainSchema,
    llm_client: LLMClient | None = None,
    llm_evidence_sink: LLMEvidenceSink | None = None,
) -> GeneratedSQL:
    """构造 prompt、调用 LLM，并返回结构化 SQL 结果。"""

    client = llm_client or get_default_llm_client()
    prompt = build_sql_prompt(question=question, user_role=user_role, domain_schema=domain_schema)
    raw_text = _complete_with_evidence(
        client,
        prompt=prompt,
        stage="sql_generation",
        evidence_sink=llm_evidence_sink,
        system_prompt="你是 DataPilot 的 NL2SQL 生成器。请把中文业务问题转换为安全的单条 SELECT SQL，并按要求返回结构化结果。",
    )
    try:
        return extract_generated_sql(raw_text)
    except LLMGenerationError as exc:
        raise _add_error_context(exc, stage="sql_generation", prompt=prompt, raw_text=raw_text) from exc


def generate_query_plan(
    *,
    question: str,
    schema_graph: SchemaGraph,
    domain_schema: DomainSchema,
    llm_client: LLMClient | None = None,
    llm_evidence_sink: LLMEvidenceSink | None = None,
) -> QueryPlan:
    """调用 LLM 生成 M10 `QueryPlan`，不可解析时交给上层结构化拦截。"""

    client = llm_client or get_default_llm_client()
    prompt = build_query_plan_prompt(
        question=question,
        schema_graph=schema_graph,
        metrics=domain_schema.metrics,
        join_paths=schema_graph.join_paths,
    )
    raw_text = _complete_with_evidence(
        client,
        prompt=prompt,
        stage="query_plan",
        evidence_sink=llm_evidence_sink,
        system_prompt="你是 DataPilot 的查询规划器。根据用户问题和局部 Schema 信息输出结构化 JSON 查询计划，不直接生成 SQL。",
    )
    try:
        return extract_query_plan(raw_text)
    except QueryPlanExtractionError as exc:
        raise _add_error_context(exc, stage="query_plan", prompt=prompt, raw_text=raw_text) from exc


def generate_sql_from_plan_step(
    *,
    question: str,
    user_role: str,
    plan_step: QueryPlanStep,
    schema_graph: SchemaGraph,
    domain_schema: DomainSchema,
    llm_client: LLMClient | None = None,
    enforce_plan_contract: bool = False,
    llm_evidence_sink: LLMEvidenceSink | None = None,
) -> GeneratedSQL:
    """基于已验证的 QueryPlanStep 和局部 Schema 生成 SQL。"""

    client = llm_client or get_default_llm_client()
    prompt = build_local_schema_sql_prompt(
        question=question,
        user_role=user_role,
        plan_step=plan_step,
        schema_graph=schema_graph,
        metrics=domain_schema.metrics,
        join_paths=schema_graph.join_paths,
    )
    raw_text = _complete_with_evidence(
        client,
        prompt=prompt,
        stage="sql_generation",
        evidence_sink=llm_evidence_sink,
        system_prompt="你是 DataPilot 的 SQL 生成器。根据已验证的 QueryPlanStep 和局部 Schema 生成安全的只读 SELECT SQL。",
    )
    try:
        generated = extract_generated_sql(raw_text)
        if enforce_plan_contract:
            validate_sql_plan_contract(
                generated.sql,
                plan_step=plan_step,
                domain_schema=domain_schema,
            )
        return generated
    except LLMGenerationError as exc:
        raise _add_error_context(exc, stage="sql_generation", prompt=prompt, raw_text=raw_text) from exc


def generate_sql_repair_from_plan_step(
    *,
    question: str,
    user_role: str,
    plan_step: QueryPlanStep,
    schema_graph: SchemaGraph,
    domain_schema: DomainSchema,
    candidate_sql: str,
    issue_code: str,
    llm_client: LLMClient | None = None,
    llm_evidence_sink: LLMEvidenceSink | None = None,
) -> GeneratedSQL:
    """只修复已分类的 MySQL 方言错误；不重新规划，也不接受自由错误正文。"""

    if issue_code != "mysql_unsupported_date_trunc":
        raise ValueError("sql_repair_issue_not_allowed")
    client = llm_client or get_default_llm_client()
    # G44-4 冻结了最小 outbound 内容：这些本地对象只在返回后做 validation，不能为了让
    # repair 更“聪明”就把 Schema/metric/join details 一并外发。
    del user_role, plan_step, schema_graph, domain_schema
    prompt = (
        "【受限修复任务】\n"
        "数据库方言固定为 MySQL 8。仅修复下列候选 SQL 的 DATE_TRUNC 方言不兼容；"
        "不得改变 QueryPlan、表、字段、过滤、聚合、排序、LIMIT 或输出列。\n"
        "只输出 JSON：{\"sql\": \"...\", \"tables_used\": [], \"confidence\": 0.0, "
        "\"reasoning_summary\": \"...\"}。\n"
        f"当前问题：{question}\nissue_code: {issue_code}\n候选 SQL:\n{candidate_sql}"
    )
    raw_text = _complete_with_evidence(
        client,
        prompt=prompt,
        stage="sql_repair",
        evidence_sink=llm_evidence_sink,
        system_prompt="你是 DataPilot 的受限 MySQL SQL 修复器。只修复已确认的 DATE_TRUNC 方言问题并输出结构化 JSON。",
    )
    try:
        return extract_generated_sql(raw_text)
    except LLMGenerationError as exc:
        raise _add_error_context(exc, stage="sql_repair", prompt=prompt, raw_text=raw_text) from exc


def validate_sql_plan_contract(
    sql: str,
    *,
    plan_step: QueryPlanStep,
    domain_schema: DomainSchema,
    dialect: str = "mysql",
) -> SQLPlanFidelityResult:
    """通过 M24 深 module interface 验证 SQL；兼容旧 caller 的异常式控制流。"""

    result = evaluate_sql_plan_fidelity(
        plan_step=plan_step,
        candidate_sql=sql,
        domain_schema=domain_schema,
        dialect=dialect,
    )
    if result.passed:
        return result
    message = "；".join(issue.message for issue in result.issues) or "SQL 保真合同无法确认。"
    raise SQLPlanContractError(message, contract_result=result)
