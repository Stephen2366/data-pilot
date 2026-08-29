import { describe, expect, it } from "vitest";

import { QUESTION_MAX_BYTES, dataPilotToolInputSchema } from "../src/contracts.js";

describe("data_pilot_query input contract", () => {
  it("accepts only the three closed operation shapes", () => {
    expect(dataPilotToolInputSchema.safeParse({ operation: "query", question: "七月退款" }).success).toBe(true);
    expect(
      dataPilotToolInputSchema.safeParse({
        operation: "query",
        question: "继续比较",
        task_id: "task-1",
        expected_version: 1,
      }).success,
    ).toBe(true);
    expect(dataPilotToolInputSchema.safeParse({ operation: "status", task_id: "task-1" }).success).toBe(true);
    expect(dataPilotToolInputSchema.safeParse({ operation: "clear", task_id: "task-1", expected_version: 2 }).success).toBe(true);
  });

  it.each([
    { operation: "query" },
    { operation: "status", task_id: "task-1", expected_version: 1 },
    { operation: "clear", task_id: "task-1" },
    { operation: "query", question: "x", task_id: "task-1" },
    { operation: "query", question: "x", user_role: "admin" },
    { operation: "query", question: "x", model: "other" },
    { operation: "query", question: "x", backend_url: "http://example.com" },
  ])("rejects an invalid or privileged shape %#", (input) => {
    expect(dataPilotToolInputSchema.safeParse(input).success).toBe(false);
  });

  it("measures the question limit in UTF-8 bytes", () => {
    expect(Buffer.byteLength("数".repeat(1365), "utf8")).toBeLessThanOrEqual(QUESTION_MAX_BYTES);
    expect(dataPilotToolInputSchema.safeParse({ operation: "query", question: "数".repeat(1365) }).success).toBe(true);
    expect(dataPilotToolInputSchema.safeParse({ operation: "query", question: "数".repeat(1366) }).success).toBe(false);
  });
});
