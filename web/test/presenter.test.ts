import { describe, expect, it } from "vitest";
import { agentResponseSchema } from "@/lib/contracts";
import { presentResponse } from "@/lib/presenter";
import completeFixture from "./fixtures/sql-complete.json";
import partialFixture from "./fixtures/hybrid-partial.json";
import blockedFixture from "./fixtures/blocked.json";
import unavailableFixture from "./fixtures/external-unavailable.json";
import clarificationFixture from "./fixtures/legacy-clarification.json";

const complete = agentResponseSchema.parse(completeFixture);

describe("ResponsePresenter closed-world table", () => {
  it.each([
    [completeFixture, "complete"],
    [partialFixture, "partial"],
    [blockedFixture, "blocked"],
    [unavailableFixture, "external_unavailable"],
    [clarificationFixture, "clarification"],
    [{ ...completeFixture, answer_status: "unsupported" }, "unsupported"],
    [{ ...completeFixture, answer_status: "insufficient_evidence" }, "insufficient"],
    [{ ...completeFixture, execution_status: "failed", answer_status: "no_answer" }, "failed"],
  ])("映射为唯一主状态 %#", (fixture, expected) => {
    expect(presentResponse(agentResponseSchema.parse(fixture)).state).toBe(expected);
  });

  it("安全 blocked 优先于看似 complete 的 answer", () => {
    expect(presentResponse({ ...complete, safety_status: "blocked" }).state).toBe("blocked");
  });

  it("未登记组合不会冒充成功", () => {
    expect(presentResponse({ ...complete, execution_status: "not_started", answer_status: "complete" }).state).toBe("unrecognized");
  });
});
