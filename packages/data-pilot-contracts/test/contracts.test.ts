import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { agentResponseSchema } from "../src/index.js";

const fixtureDirectory = fileURLToPath(new URL("../../../web/test/fixtures/", import.meta.url));

describe("Python-authoritative response fixtures", () => {
  it("keeps every generated AgentResponse fixture valid at the shared TypeScript gate", () => {
    const fixtures = readdirSync(fixtureDirectory).filter((name) => name.endsWith(".json"));
    expect(fixtures.length).toBeGreaterThanOrEqual(5);
    for (const name of fixtures) {
      const raw = JSON.parse(readFileSync(`${fixtureDirectory}/${name}`, "utf8"));
      expect(agentResponseSchema.safeParse(raw), name).toMatchObject({ success: true });
    }
  });

  it("fails closed when a Python core axis drifts", () => {
    const raw = JSON.parse(readFileSync(`${fixtureDirectory}/sql-complete.json`, "utf8"));
    raw.execution_status = "secret_new_state";
    expect(agentResponseSchema.safeParse(raw).success).toBe(false);
  });
});
