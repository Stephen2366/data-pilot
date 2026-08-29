import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import type { AdapterConfig } from "../src/config.js";
import { AdapterError, callDataPilot } from "../src/http-adapter.js";

const sqlFixture = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../web/test/fixtures/sql-complete.json", import.meta.url)), "utf8"),
);
const config: AdapterConfig = { apiBaseUrl: new URL("http://127.0.0.1:8000"), userRole: "ops", timeoutMs: 300_000 };

describe("single-attempt HTTP adapter", () => {
  it("constructs a task start request without exposing runtime controls", async () => {
    const fakeFetch = vi.fn(async (_url: URL | RequestInfo, init?: RequestInit) => {
      expect(init?.redirect).toBe("manual");
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        question: "查询七月退款",
        user_role: "ops",
        task: { action: "start" },
      });
      return Response.json(sqlFixture);
    });
    const result = await callDataPilot({ operation: "query", question: "查询七月退款" }, config, fakeFetch as typeof fetch);
    expect(result.operation).toBe("query");
    expect(fakeFetch).toHaveBeenCalledOnce();
  });

  it("uses the exact acknowledged task identity for continue", async () => {
    const fakeFetch = vi.fn(async (_url: URL | RequestInfo, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body)).task).toEqual({ action: "continue", task_id: "task-1", expected_version: 3 });
      return Response.json(sqlFixture);
    });
    await callDataPilot(
      { operation: "query", question: "继续", task_id: "task-1", expected_version: 3 },
      config,
      fakeFetch as typeof fetch,
    );
    expect(fakeFetch).toHaveBeenCalledOnce();
  });

  it("maps status and clear to their dedicated methods and query parameters", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fakeFetch = vi.fn(async (url: URL | RequestInfo, init?: RequestInit) => {
      calls.push({ url: String(url), method: String(init?.method) });
      if (init?.method === "GET") {
        return Response.json({ ok: true, reason_code: "task_status_available", safety_status: "passed", message: "ok", task: { task_id: "task/1", task_version: 4, status: "active", expires_at: "later" } });
      }
      return Response.json({ ok: true, reason_code: "task_cleared", safety_status: "passed", message: "cleared", task: { ...sqlFixture.task, task_id: "task/1", task_version: 5, status: "cleared" } });
    });
    await callDataPilot({ operation: "status", task_id: "task/1" }, config, fakeFetch as typeof fetch);
    await callDataPilot({ operation: "clear", task_id: "task/1", expected_version: 4 }, config, fakeFetch as typeof fetch);
    expect(calls).toEqual([
      { url: "http://127.0.0.1:8000/api/query/tasks/task%2F1?user_role=ops", method: "GET" },
      { url: "http://127.0.0.1:8000/api/query/tasks/task%2F1?user_role=ops&expected_version=4", method: "DELETE" },
    ]);
  });

  it.each([
    [302, "backend_rejected", "unknown"],
    [422, "backend_rejected", "known_rejected"],
    [503, "backend_rejected", "unknown"],
  ] as const)("does not retry HTTP %i and returns a safe outcome", async (status, code, outcome) => {
    const fakeFetch = vi.fn(async () => new Response("{}", { status, headers: status === 302 ? { location: "https://example.com" } : {} }));
    await expect(callDataPilot({ operation: "query", question: "x" }, config, fakeFetch as typeof fetch)).rejects.toMatchObject<Partial<AdapterError>>({ code, outcome, status });
    expect(fakeFetch).toHaveBeenCalledOnce();
  });

  it("fails closed on non-JSON and contract drift without leaking the payload", async () => {
    const nonJson = vi.fn(async () => new Response("secret-driver-detail", { status: 200 }));
    await expect(callDataPilot({ operation: "query", question: "x" }, config, nonJson as typeof fetch)).rejects.toMatchObject({ code: "backend_invalid_response", outcome: "unknown" });
    const drift = vi.fn(async () => Response.json({ ...sqlFixture, execution_status: "new-secret-state" }));
    await expect(callDataPilot({ operation: "query", question: "x" }, config, drift as typeof fetch)).rejects.toMatchObject({ code: "response_contract_invalid", outcome: "unknown" });
    expect(nonJson).toHaveBeenCalledOnce();
    expect(drift).toHaveBeenCalledOnce();
  });

  it("aborts a timed-out mutation once and reports unknown without retry", async () => {
    const fastTimeout = { ...config, timeoutMs: 5 };
    const fakeFetch = vi.fn(
      async (_url: URL | RequestInfo, init?: RequestInit) =>
        await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
        }),
    );
    await expect(callDataPilot({ operation: "query", question: "x" }, fastTimeout, fakeFetch as typeof fetch)).rejects.toMatchObject({
      code: "backend_timeout",
      outcome: "unknown",
    });
    expect(fakeFetch).toHaveBeenCalledOnce();
  });
});
