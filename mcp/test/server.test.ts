import { createServer as createHttpServer } from "node:http";
import { once } from "node:events";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { Client, InMemoryTransport } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AdapterConfig } from "../src/config.js";
import { TOOL_NAME } from "../src/contracts.js";
import { createDataPilotServer } from "../src/server.js";

const fixture = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../web/test/fixtures/sql-complete.json", import.meta.url)), "utf8"),
);
const config: AdapterConfig = { apiBaseUrl: new URL("http://127.0.0.1:8000"), userRole: "ops", timeoutMs: 300_000 };
const clients: Client[] = [];

afterEach(async () => {
  await Promise.all(clients.splice(0).map((client) => client.close()));
});

describe("MCP protocol integration", () => {
  it("lists exactly one annotated tool and calls it over an SDK in-memory transport", async () => {
    const fakeFetch = vi.fn(async () => Response.json(fixture));
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    const server = createDataPilotServer({ config, fetch: fakeFetch as typeof fetch });
    const client = new Client({ name: "m51-test", version: "0.1.0" });
    clients.push(client);
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    const listed = await client.listTools();
    expect(listed.tools).toHaveLength(1);
    expect(listed.tools[0]).toMatchObject({ name: TOOL_NAME, annotations: { readOnlyHint: false, idempotentHint: false } });
    const result = await client.callTool({ name: TOOL_NAME, arguments: { operation: "query", question: "查询七月退款" } });
    expect(result.isError).not.toBe(true);
    expect(result.structuredContent).toMatchObject({ ok: true, route: "sql", task: { task_version: 1 } });
    expect(fakeFetch).toHaveBeenCalledOnce();
    await server.close();
  });

  it("rejects invalid input in the SDK before the HTTP handler runs", async () => {
    const fakeFetch = vi.fn(async () => Response.json(fixture));
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    const server = createDataPilotServer({ config, fetch: fakeFetch as typeof fetch });
    const client = new Client({ name: "m51-test", version: "0.1.0" });
    clients.push(client);
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    const result = await client.callTool({ name: TOOL_NAME, arguments: { operation: "query", user_role: "admin" } });
    expect(result.isError).toBe(true);
    expect(fakeFetch).not.toHaveBeenCalled();
    await server.close();
  });

  it("returns a typed stale-version rejection as isError", async () => {
    const rejected = {
      ...fixture,
      route: "none",
      answer: "",
      execution_status: "not_started",
      answer_status: "no_answer",
      reason_code: "task_version_conflict",
      task_action: "rejected",
      task_runtime_invocation_count: 0,
      task: null,
    };
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    const server = createDataPilotServer({ config, fetch: vi.fn(async () => Response.json(rejected)) as typeof fetch });
    const client = new Client({ name: "m51-test", version: "0.1.0" });
    clients.push(client);
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    const result = await client.callTool({
      name: TOOL_NAME,
      arguments: { operation: "query", question: "继续", task_id: "task-1", expected_version: 1 },
    });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({ ok: false, reason_code: "task_version_conflict", task: null });
    await server.close();
  });

  it("spawns the built stdio entry and keeps stdout usable as JSON-RPC", async () => {
    const httpServer = createHttpServer((_request, response) => {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(fixture));
    });
    httpServer.listen(0, "127.0.0.1");
    await once(httpServer, "listening");
    const address = httpServer.address();
    if (address === null || typeof address === "string") throw new Error("test server did not bind TCP");
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [fileURLToPath(new URL("../dist/index.js", import.meta.url))],
      env: { ...process.env, DATAPILOT_API_BASE_URL: `http://127.0.0.1:${address.port}` },
    });
    const client = new Client({ name: "m51-spawn-test", version: "0.1.0" });
    clients.push(client);
    try {
      await client.connect(transport);
      expect((await client.listTools()).tools.map((tool) => tool.name)).toEqual([TOOL_NAME]);
      const result = await client.callTool({ name: TOOL_NAME, arguments: { operation: "query", question: "查询七月退款" } });
      expect(result.structuredContent).toMatchObject({ ok: true, trace_id: "trace-m50-fixture" });
    } finally {
      httpServer.close();
      await once(httpServer, "close");
    }
  });
});
