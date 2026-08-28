import { describe, expect, it } from "vitest";
import { agentResponseSchema } from "@/lib/contracts";
import sqlComplete from "./fixtures/sql-complete.json";
import hybridPartial from "./fixtures/hybrid-partial.json";
import blocked from "./fixtures/blocked.json";
import unavailable from "./fixtures/external-unavailable.json";
import clarification from "./fixtures/legacy-clarification.json";

describe("Python-authoritative response fixtures", () => {
  it.each([sqlComplete, hybridPartial, blocked, unavailable, clarification])(
    "通过前端 runtime validator",
    (fixture) => expect(agentResponseSchema.safeParse(fixture).success).toBe(true),
  );

  it("核心 enum 漂移时失败关闭", () => {
    expect(agentResponseSchema.safeParse({ ...sqlComplete, answer_status: "mostly_done" }).success).toBe(false);
  });

  it("核心 identity 缺失时失败关闭", () => {
    const withoutTrace: Record<string, unknown> = { ...sqlComplete };
    delete withoutTrace.trace_id;
    expect(agentResponseSchema.safeParse(withoutTrace).success).toBe(false);
  });
});
