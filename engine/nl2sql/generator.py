"""M4 LLM SQL Generator：调用 DeepSeek 生成 SQL，并把模型输出解析成结构化结果。

★ 本模块只做一个最小 provider 适配层。阶段二先跑通 DeepSeek 主路径，不把工程复杂度
花在多厂商抽象上；如果密钥缺失或网络失败，向上返回可诊断错误。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import get_settings
from engine.nl2sql.planner import QueryPlan, QueryPlanStep
from engine.nl2sql.prompt import build_local_schema_sql_prompt, build_query_plan_prompt, build_sql_prompt
from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.objects import SchemaGraph


class LLMGenerationError(RuntimeError):
    """LLM SQL 生成失败，调用方应转成结构化拦截响应。"""

    def __init__(
        self,
        message: str,
        *,
        raw_response_preview: str | None = None,
        parse_error: str | None = None,
        prompt_length: int | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response_preview = raw_response_preview
        self.parse_error = parse_error
        self.prompt_length = prompt_length
        self.stage = stage


class QueryPlanExtractionError(LLMGenerationError):
    """QueryPlan 解析失败，固定映射到 M10 的 `invalid_query_plan`。"""

    issue_tag = "invalid_query_plan"


class LLMClient(Protocol):
    """最小 LLM client 协议，方便测试替换真实 DeepSeek 调用。"""

    def complete(self, *, prompt: str, system_prompt: str | None = None) -> str:
        """输入完整 prompt，返回模型原始文本。"""


class GeneratedSQL(BaseModel):
    """LLM 生成 SQL 的结构化结果。"""

    sql: str = Field(min_length=1)
    tables_used: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning_summary: str = ""


class DeepSeekChatClient:
    """DeepSeek OpenAI-compatible chat completion 客户端。"""

    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") or "https://api.deepseek.com"
        self.model = model or "deepseek-v4-pro"

    def complete(self, *, prompt: str, system_prompt: str | None = None) -> str:
        """调用 DeepSeek chat completions 接口。"""

        if not self.api_key:
            raise LLMGenerationError("DeepSeek API key 缺失，请配置 DEEPSEEK_API_KEY 或 LLM_API_KEY。")

        # 步骤 1：按 OpenAI-compatible chat 格式组装请求 -------------------------------
        resolved_system_prompt = system_prompt or "你只负责把中文业务问题转换为安全的单条 SELECT SQL。"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": resolved_system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        # 步骤 2：真实网络调用只在这里发生；失败统一转成 LLMGenerationError。
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise LLMGenerationError(f"DeepSeek HTTP 调用失败：{exc.code} {detail[:300]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMGenerationError(f"DeepSeek 网络调用失败：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMGenerationError(f"DeepSeek 返回非 JSON：{exc}") from exc

        # 步骤 3：只把模型正文交给 SQL 提取器；token / cost 等细节留给 M5 trace。
        try:
            return str(response_payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGenerationError(f"DeepSeek 返回结构缺少 choices/message/content：{response_payload}") from exc


def get_default_llm_client() -> LLMClient:
    """按当前配置创建默认 LLM client。

    如果 `.env` 仍是 `LLM_PROVIDER=mock`，但已经配置 DeepSeek key，则按 M4 确认方案走
    DeepSeek 主路径，避免因为旧默认值误判为只能 mock。
    """

    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider not in {"deepseek", "mock"}:
        raise LLMGenerationError(f"M4 仅支持 DeepSeek 主路径，当前 LLM_PROVIDER={settings.llm_provider}。")

    api_key = settings.deepseek_api_key or settings.llm_api_key
    model = settings.llm_model if settings.llm_model != "mock-sql-generator" else "deepseek-v4-pro"
    return DeepSeekChatClient(
        api_key=api_key,
        base_url=settings.deepseek_base_url or "https://api.deepseek.com",
        model=model,
    )


def _complete_with_system_prompt(client: LLMClient, *, prompt: str, system_prompt: str) -> str:
    """兼容新旧 fake client：真实客户端用 system prompt，旧测试替身仍可只接收 prompt。"""

    try:
        return client.complete(prompt=prompt, system_prompt=system_prompt)
    except TypeError as exc:
        if "system_prompt" not in str(exc):
            raise
        return client.complete(prompt=prompt)


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
    return exc


def generate_sql(
    *,
    question: str,
    user_role: str,
    domain_schema: DomainSchema,
    llm_client: LLMClient | None = None,
) -> GeneratedSQL:
    """构造 prompt、调用 LLM，并返回结构化 SQL 结果。"""

    client = llm_client or get_default_llm_client()
    prompt = build_sql_prompt(question=question, user_role=user_role, domain_schema=domain_schema)
    raw_text = _complete_with_system_prompt(
        client,
        prompt=prompt,
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
) -> QueryPlan:
    """调用 LLM 生成 M10 `QueryPlan`，不可解析时交给上层结构化拦截。"""

    client = llm_client or get_default_llm_client()
    prompt = build_query_plan_prompt(
        question=question,
        schema_graph=schema_graph,
        metrics=domain_schema.metrics,
        join_paths=schema_graph.join_paths,
    )
    raw_text = _complete_with_system_prompt(
        client,
        prompt=prompt,
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
    raw_text = _complete_with_system_prompt(
        client,
        prompt=prompt,
        system_prompt="你是 DataPilot 的 SQL 生成器。根据已验证的 QueryPlanStep 和局部 Schema 生成安全的只读 SELECT SQL。",
    )
    try:
        return extract_generated_sql(raw_text)
    except LLMGenerationError as exc:
        raise _add_error_context(exc, stage="sql_generation", prompt=prompt, raw_text=raw_text) from exc
