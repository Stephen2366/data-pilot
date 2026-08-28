import { afterEach, describe, expect, it, vi } from "vitest";
import { DataPilotClient } from "@/lib/data-pilot-client";
import completeFixture from "./fixtures/sql-complete.json";

afterEach(() => vi.restoreAllMocks());

describe("DataPilotClient", () => {
  it("发送严格 task envelope 并校验响应", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(completeFixture), { status: 200, headers: { "content-type": "application/json" } }),
    );
    const response = await new DataPilotClient().query({
      question: "查询 7 月退款",
      user_role: "ops",
      task: { action: "start" },
    });
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.task).toEqual({ action: "start" });
    expect(response.task?.task_version).toBe(1);
  });

  it("合同漂移标记 unknown 且不重试", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ...completeFixture, runtime_family: "future" }), { status: 200 }),
    );
    const promise = new DataPilotClient().query({ question: "query", user_role: "ops", task: { action: "start" } });
    await expect(promise).rejects.toMatchObject({ failure: { outcome: "unknown" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["422", 422, "known_rejected", "backend_rejected"],
    ["version conflict", 409, "known_rejected", "backend_rejected"],
    ["timeout", 504, "unknown", "backend_timeout"],
  ] as const)("BFF %s 失败保持分层且不重试", async (_label, status, outcome, code) => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: false, error: { code, message: "安全摘要", outcome, status } }), { status }),
    );
    await expect(new DataPilotClient().query({ question: "query", user_role: "ops", task: { action: "start" } }))
      .rejects.toMatchObject({ failure: { code, outcome, status, message: "安全摘要" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("non-JSON adapter 响应冻结为 unknown 且不重试", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("upstream html", { status: 502, headers: { "content-type": "text/html" } }),
    );
    await expect(new DataPilotClient().query({ question: "query", user_role: "ops", task: { action: "start" } }))
      .rejects.toMatchObject({ failure: { code: "backend_invalid_response", outcome: "unknown" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("网络不可达不重试 mutation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network down"));
    await expect(new DataPilotClient().query({ question: "query", user_role: "ops", task: { action: "start" } }))
      .rejects.toMatchObject({ failure: { code: "backend_unreachable", outcome: "unknown" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("客户端请求合同失败时网络调用为零", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(new DataPilotClient().query({ question: "", user_role: "ops", task: { action: "start" } }))
      .rejects.toMatchObject({ failure: { code: "request_invalid", outcome: "not_sent" } });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("unknown 后的 status 对账使用只读 GET 且校验最小投影", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        ok: true,
        reason_code: "task_status_ready",
        safety_status: "passed",
        message: "任务状态已核对。",
        task: {
          task_id: "task_m50_fixture_001", task_version: 3, status: "active",
          expires_at: "2026-08-28T08:00:00+00:00",
        },
      }), { status: 200 }),
    );
    const response = await new DataPilotClient().getTaskStatus("task_m50_fixture_001", "ops");
    expect(response.task?.task_version).toBe(3);
    expect(fetchMock.mock.calls[0][1]?.method).toBe("GET");
    expect(fetchMock.mock.calls[0][0]).toContain("user_role=ops");
  });

  it.each([
    ["task_version_conflict", "任务版本已变化"],
    ["task_unavailable", "任务不可用或身份不匹配"],
  ] as const)("HTTP 200 typed rejection %s 不作为成功 turn 返回", async (reasonCode, message) => {
    const rejected = {
      ...completeFixture,
      action_attempts: [],
      agent_budget: null,
      agent_loop_runtime: null,
      agent_termination: null,
      answer: "本轮未执行。",
      answer_status: "no_answer",
      chart_spec: null,
      columns: [],
      execution_status: "not_started",
      graph_invocation_count: 0,
      reason_code: reasonCode,
      route: "none",
      rows: [],
      safety_status: reasonCode === "task_unavailable" ? "blocked" : "passed",
      sql: null,
      tables_used: [],
      task: null,
      task_action: "rejected",
      task_context: null,
      task_delta: null,
      task_runtime_invocation_count: 0,
      task_transition: null,
      turn_action: "rejected",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(rejected), { status: 200 }),
    );
    await expect(new DataPilotClient().query({
      question: "continue",
      user_role: "ops",
      task: { action: "continue", task_id: "task_m50_fixture_001", expected_version: 1 },
    })).rejects.toMatchObject({ failure: { code: "backend_rejected", outcome: "known_rejected", message: expect.stringContaining(message) } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
