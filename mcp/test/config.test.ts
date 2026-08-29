import { describe, expect, it } from "vitest";

import { loadConfig } from "../src/config.js";

describe("adapter configuration", () => {
  it.each(["http://127.0.0.1:8000", "http://127.9.8.7:8000", "http://localhost:8000", "http://[::1]:8000"])(
    "accepts a credential-free loopback origin: %s",
    (base) => expect(loadConfig({ DATAPILOT_API_BASE_URL: base })).toMatchObject({ userRole: "ops", timeoutMs: 310_000 }),
  );

  it.each([
    "https://127.0.0.1:8000",
    "http://example.com:8000",
    "http://127.0.0.1:8000/api",
    "http://user:password@127.0.0.1:8000",
    "http://127.0.0.1:8000?next=http://example.com",
  ])("rejects a backend outside the exact local origin boundary: %s", (base) => {
    expect(() => loadConfig({ DATAPILOT_API_BASE_URL: base })).toThrow("configuration_invalid");
  });

  it("does not allow a timeout below the Web 300 second baseline", () => {
    expect(() => loadConfig({ DATAPILOT_MCP_TIMEOUT_MS: "299999" })).toThrow("configuration_invalid");
  });
});
