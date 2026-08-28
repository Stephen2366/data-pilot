import "server-only";

import { NextResponse } from "next/server";
import type { ZodType } from "zod";

const DEFAULT_BACKEND = "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 300_000;

type ProxyInput<T> = {
  path: string;
  method: "POST" | "DELETE" | "GET";
  request?: Request;
  requestSchema?: ZodType<T>;
  responseSchema: ZodType<unknown>;
};

/** 统一生成不含 FastAPI detail、driver message 或内部地址的 BFF 失败合同。 */
function failure(
  code: "request_invalid" | "backend_rejected" | "backend_unreachable" | "backend_timeout" | "backend_invalid_response" | "response_contract_invalid",
  message: string,
  outcome: "not_sent" | "known_rejected" | "unknown",
  status: number,
) {
  return NextResponse.json({ ok: false, error: { code, message, outcome, status } }, { status });
}

/**
 * Next Route Handler 共用的唯一 FastAPI adapter。
 *
 * ★ 它只处理 transport，不解释 route/action/Evidence，也绝不重试 mutation。即使超时发生在
 * FastAPI 已提交 task 之后，BFF 也无法证明结果，所以只能返回 outcome=unknown。
 */
export async function proxyFastApi<T>({ path, method, request, requestSchema, responseSchema }: ProxyInput<T>) {
  let body: T | undefined;
  if (requestSchema && request) {
    let raw: unknown;
    try {
      raw = await request.json();
    } catch {
      return failure("request_invalid", "请求不是有效的 JSON。", "not_sent", 400);
    }
    const parsed = requestSchema.safeParse(raw);
    if (!parsed.success) {
      return failure("request_invalid", "请求字段不符合 DataPilot 合同。", "not_sent", 400);
    }
    body = parsed.data;
  }

  const backend = (process.env.DATAPILOT_API_BASE_URL ?? DEFAULT_BACKEND).replace(/\/$/, "");
  const timeoutMs = Number(process.env.DATAPILOT_BFF_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let upstream: Response;
  try {
    upstream = await fetch(`${backend}${path}`, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    return failure(
      timedOut ? "backend_timeout" : "backend_unreachable",
      timedOut ? "DataPilot 本轮等待超时，任务结果未知。" : "无法连接 DataPilot API。",
      method === "GET" ? "not_sent" : "unknown",
      timedOut ? 504 : 503,
    );
  } finally {
    clearTimeout(timeout);
  }

  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return failure(
      "backend_invalid_response",
      "DataPilot API 返回了无法读取的响应。",
      upstream.ok ? "unknown" : "known_rejected",
      502,
    );
  }
  if (!upstream.ok) {
    // 不把 FastAPI/Pydantic/driver 的原始 detail 直接暴露到页面。
    return failure("backend_rejected", `DataPilot API 拒绝了请求（HTTP ${upstream.status}）。`, "known_rejected", upstream.status);
  }
  const validated = responseSchema.safeParse(payload);
  if (!validated.success) {
    return failure("response_contract_invalid", "DataPilot 响应合同无法识别，已停止展示。", "unknown", 502);
  }
  return NextResponse.json(validated.data, { status: upstream.status });
}
