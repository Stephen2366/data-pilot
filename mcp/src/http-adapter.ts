import {
  agentResponseSchema,
  taskControlResponseSchema,
  taskStatusResponseSchema,
  type AgentResponse,
  type TaskControlResponse,
  type TaskStatusResponse,
} from "@datapilot/contracts";

import type { AdapterConfig } from "./config.js";
import type { DataPilotToolInput } from "./contracts.js";

export type AdapterErrorCode =
  | "backend_rejected"
  | "backend_unreachable"
  | "backend_timeout"
  | "backend_invalid_response"
  | "response_contract_invalid";

export class AdapterError extends Error {
  constructor(
    public readonly code: AdapterErrorCode,
    public readonly outcome: "not_sent" | "known_rejected" | "unknown",
    public readonly status?: number,
  ) {
    super(safeMessage(code, status));
    this.name = "AdapterError";
  }
}

function safeMessage(code: AdapterErrorCode, status?: number): string {
  const messages: Record<AdapterErrorCode, string> = {
    backend_rejected: `DataPilot API 拒绝了请求${status === undefined ? "" : `（HTTP ${status}）`}。`,
    backend_unreachable: "无法连接本地 DataPilot API。",
    backend_timeout: "等待 DataPilot 超时；本次 mutation 的结果可能未知。",
    backend_invalid_response: "DataPilot API 返回了无法读取的响应。",
    response_contract_invalid: "DataPilot API 响应未通过公开合同校验。",
  };
  return messages[code];
}

export type BackendResult =
  | { operation: "query"; value: AgentResponse }
  | { operation: "status"; value: TaskStatusResponse }
  | { operation: "clear"; value: TaskControlResponse };

/**
 * 单次、无重试 HTTP delegation。
 *
 * ★ mutation 一旦发出后遇到 timeout/5xx/坏 JSON，就不能知道 FastAPI 是否已经提交 task；
 * 因此 query/clear 返回 unknown，绝不自动重放。redirect 设为 manual，防止 loopback 起点
 * 被 30x 带到非本机地址。
 */
export async function callDataPilot(
  input: DataPilotToolInput,
  config: AdapterConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<BackendResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);
  const mutation = input.operation !== "status";
  let path: string;
  let init: RequestInit;
  if (input.operation === "query") {
    const continuing = input.task_id !== undefined;
    path = "/api/query";
    init = {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        question: input.question,
        user_role: config.userRole,
        task: continuing
          ? { action: "continue", task_id: input.task_id, expected_version: input.expected_version }
          : { action: "start" },
      }),
    };
  } else {
    const encodedTask = encodeURIComponent(input.task_id!);
    const query = new URLSearchParams({ user_role: config.userRole });
    if (input.operation === "clear") query.set("expected_version", String(input.expected_version));
    path = `/api/query/tasks/${encodedTask}?${query.toString()}`;
    init = { method: input.operation === "status" ? "GET" : "DELETE" };
  }

  let response: Response;
  try {
    response = await fetchImpl(new URL(path, config.apiBaseUrl), {
      ...init,
      redirect: "manual",
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    throw new AdapterError(
      timedOut ? "backend_timeout" : "backend_unreachable",
      mutation ? "unknown" : "not_sent",
    );
  } finally {
    clearTimeout(timeout);
  }

  if (response.status >= 300 && response.status < 400) {
    throw new AdapterError("backend_rejected", mutation ? "unknown" : "known_rejected", response.status);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new AdapterError(
      "backend_invalid_response",
      !response.ok && response.status < 500 ? "known_rejected" : mutation ? "unknown" : "not_sent",
      response.status,
    );
  }
  if (!response.ok) {
    throw new AdapterError(
      "backend_rejected",
      response.status < 500 ? "known_rejected" : mutation ? "unknown" : "not_sent",
      response.status,
    );
  }

  const schema =
    input.operation === "query"
      ? agentResponseSchema
      : input.operation === "status"
        ? taskStatusResponseSchema
        : taskControlResponseSchema;
  const parsed = schema.safeParse(payload);
  if (!parsed.success) throw new AdapterError("response_contract_invalid", mutation ? "unknown" : "not_sent", response.status);
  return { operation: input.operation, value: parsed.data } as BackendResult;
}
