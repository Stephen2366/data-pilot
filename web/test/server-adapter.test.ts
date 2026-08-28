import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { agentResponseSchema, queryRequestSchema } from "@/lib/contracts";
import { proxyFastApi } from "@/lib/server-adapter";
import completeFixture from "./fixtures/sql-complete.json";

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.DATAPILOT_API_BASE_URL;
  delete process.env.DATAPILOT_BFF_TIMEOUT_MS;
});

function request(body: string) {
  return new Request("http://web.test/api/datapilot/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
}

/** 用与 Route Handler 相同的 schema 调 adapter，避免测试绕开真实边界配置。 */
async function proxy(input: Request) {
  return proxyFastApi({
    path: "/api/query",
    method: "POST",
    request: input,
    requestSchema: queryRequestSchema,
    responseSchema: agentResponseSchema,
  });
}

describe("thin BFF server adapter", () => {
  it("非法 JSON/字段在 FastAPI 前拒绝", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const invalidJson = await proxy(request("{"));
    expect(await invalidJson.json()).toMatchObject({ error: { code: "request_invalid", outcome: "not_sent" } });
    const invalidShape = await proxy(request(JSON.stringify({ question: "missing role" })));
    expect(await invalidShape.json()).toMatchObject({ error: { code: "request_invalid", outcome: "not_sent" } });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("FastAPI 422 被净化为 known rejection，不泄漏 detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ loc: ["body", "task"], msg: "private validation detail" }] }), { status: 422 }),
    );
    const response = await proxy(request(JSON.stringify({ question: "query", user_role: "ops", task: { action: "start" } })));
    const text = await response.text();
    expect(JSON.parse(text)).toMatchObject({ error: { code: "backend_rejected", outcome: "known_rejected", status: 422 } });
    expect(text).not.toContain("private validation detail");
  });

  it.each([
    [200, "unknown"],
    [500, "known_rejected"],
  ] as const)("non-JSON HTTP %s 保持 outcome=%s", async (status, outcome) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>private stack</html>", { status }));
    const response = await proxy(request(JSON.stringify({ question: "query", user_role: "ops", task: { action: "start" } })));
    const text = await response.text();
    expect(JSON.parse(text)).toMatchObject({ error: { code: "backend_invalid_response", outcome } });
    expect(text).not.toContain("private stack");
  });

  it("成功 HTTP 的合同漂移失败关闭", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ...completeFixture, runtime_family: "future" }), { status: 200 }),
    );
    const response = await proxy(request(JSON.stringify({ question: "query", user_role: "ops", task: { action: "start" } })));
    expect(await response.json()).toMatchObject({ error: { code: "response_contract_invalid", outcome: "unknown" } });
  });

  it("backend unreachable 与 timeout 都只调用一次", async () => {
    const unreachable = vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("private host"));
    const first = await proxy(request(JSON.stringify({ question: "query", user_role: "ops", task: { action: "start" } })));
    expect(await first.json()).toMatchObject({ error: { code: "backend_unreachable", outcome: "unknown" } });
    expect(unreachable).toHaveBeenCalledTimes(1);

    process.env.DATAPILOT_BFF_TIMEOUT_MS = "1";
    unreachable.mockImplementationOnce((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    }));
    const second = await proxy(request(JSON.stringify({ question: "query", user_role: "ops", task: { action: "start" } })));
    expect(await second.json()).toMatchObject({ error: { code: "backend_timeout", outcome: "unknown" } });
    expect(unreachable).toHaveBeenCalledTimes(2);
  });
});
