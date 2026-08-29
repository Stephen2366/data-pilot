import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { agentResponseSchema } from "@datapilot/contracts";
import { describe, expect, it } from "vitest";

import { RESULT_MAX_BYTES } from "../src/contracts.js";
import { clipUtf8, projectBackendResult, structuredResultBytes } from "../src/projector.js";

const fixture = agentResponseSchema.parse(
  JSON.parse(readFileSync(fileURLToPath(new URL("../../web/test/fixtures/sql-complete.json", import.meta.url)), "utf8")),
);

describe("bounded public projector", () => {
  it("keeps the truth axes, trace and acknowledged task identity", () => {
    const result = projectBackendResult({ operation: "query", value: fixture });
    expect(result).toMatchObject({
      ok: true,
      operation: "query",
      route: "sql",
      execution_status: "completed",
      answer_status: "complete",
      safety_status: "passed",
      trace_id: "trace-m50-fixture",
      task: { task_id: "task_m50_fixture_001", task_version: 1 },
    });
    expect(result).not.toHaveProperty("task.state");
    expect(result).not.toHaveProperty("task.context");
    expect(result).not.toHaveProperty("tool_calls");
    expect(result).not.toHaveProperty("cost");
  });

  it.each([
    ["hybrid-partial.json", "hybrid", "partial"],
    ["blocked.json", "none", "no_answer"],
    ["external-unavailable.json", "rag", "no_answer"],
    ["legacy-clarification.json", "none", "clarification_required"],
  ] as const)("projects %s without exposing internal Agent fields", (name, route, answerStatus) => {
    const response = agentResponseSchema.parse(
      JSON.parse(readFileSync(fileURLToPath(new URL(`../../web/test/fixtures/${name}`, import.meta.url)), "utf8")),
    );
    const result = projectBackendResult({ operation: "query", value: response });
    expect(result).toMatchObject({ route, answer_status: answerStatus, trace_id: response.trace_id });
    expect(result).not.toHaveProperty("cost");
    expect(result).not.toHaveProperty("task_context");
  });

  it("marks a typed task rejection as a readable Tool error without inventing a version", () => {
    const rejected = agentResponseSchema.parse({
      ...fixture,
      route: "none",
      answer: "",
      execution_status: "not_started",
      answer_status: "no_answer",
      reason_code: "task_version_conflict",
      task_action: "rejected",
      task_runtime_invocation_count: 0,
      task: null,
    });
    expect(projectBackendResult({ operation: "query", value: rejected })).toMatchObject({
      ok: false,
      reason_code: "task_version_conflict",
      task: null,
      message: expect.stringContaining("版本未推进"),
    });
  });

  it("clips by UTF-8 bytes without splitting Chinese characters", () => {
    const clipped = clipUtf8("退款".repeat(100), 64);
    expect(Buffer.byteLength(clipped.value, "utf8")).toBeLessThanOrEqual(64);
    expect(clipped.value.endsWith("…")).toBe(true);
    expect(clipped.value).not.toContain("�");
  });

  it("enforces every collection/cell/total bound and citation allowlist", () => {
    const oversized = agentResponseSchema.parse({
      ...fixture,
      answer: "答".repeat(20_000),
      sql: "S".repeat(20_000),
      columns: Array.from({ length: 30 }, (_, index) => `c${index}`),
      rows: Array.from({ length: 80 }, (_, row) => Object.fromEntries(Array.from({ length: 30 }, (_, column) => [`c${column}`, `${row}-${column}-${"值".repeat(2_000)}`]))),
      citations: Array.from({ length: 24 }, (_, index) => ({ evidence_id: `ev-${index}`, title: "题".repeat(1_000), anchor: `section:${index}`, private_chunk: "never-export" })),
    });
    const result = projectBackendResult({ operation: "query", value: oversized });
    expect(Buffer.byteLength(result.answer!, "utf8")).toBeLessThanOrEqual(16 * 1024);
    expect(Buffer.byteLength(result.sql!, "utf8")).toBeLessThanOrEqual(16 * 1024);
    expect(result.columns!.length).toBeLessThanOrEqual(20);
    expect(result.rows!.length).toBeLessThanOrEqual(50);
    expect(result.citations!.length).toBeLessThanOrEqual(16);
    expect(result.citations?.[0]).not.toHaveProperty("private_chunk");
    expect(structuredResultBytes(result)).toBeLessThanOrEqual(RESULT_MAX_BYTES);
    expect(result.truncated).toMatchObject({ columns_removed: 10, citations_removed: expect.any(Number) });
  });
});
