#!/usr/bin/env node
/**
 * M51 Live Dev Probe 的 SDK 客户端入口。
 *
 * 它始终通过 `StdioClientTransport` 拉起正式 build，而不是直接调用 handler；输出只包含
 * tool list 与 MCP 返回的公开 result，可安全写入 `.agent_work/temp/m51/<probe-id>/`。
 */
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";

import { TOOL_NAME } from "./contracts.js";

// SDK 默认请求时限短于 adapter 的 310 秒预算；Probe 要允许服务端正常收口，但仍不自动重放 mutation。
const PROBE_CALL_TIMEOUT_MS = 330_000;

function argument(name: string): string | undefined {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function requiredArgument(name: string): string {
  const value = argument(name);
  if (value === undefined) throw new Error(`missing --${name}`);
  return value;
}

async function main(): Promise<void> {
  const operation = requiredArgument("operation");
  const outputPath = requiredArgument("output");
  const toolArguments: Record<string, unknown> = { operation };
  const question = argument("question");
  const taskId = argument("task-id");
  const expectedVersion = argument("expected-version");
  if (question !== undefined) toolArguments.question = question;
  if (taskId !== undefined) toolArguments.task_id = taskId;
  if (expectedVersion !== undefined) toolArguments.expected_version = Number(expectedVersion);

  const environment = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [fileURLToPath(new URL("./index.js", import.meta.url))],
    env: environment,
  });
  const client = new Client({ name: "datapilot-m51-probe", version: "0.1.0" });
  try {
    await client.connect(transport);
    const tools = await client.listTools();
    const result = await client.callTool(
      { name: TOOL_NAME, arguments: toolArguments },
      { timeout: PROBE_CALL_TIMEOUT_MS },
    );
    const evidence = {
      format: "m51-mcp-probe-v1",
      negotiated_protocol: client.getNegotiatedProtocolVersion(),
      tools: tools.tools,
      call: { name: TOOL_NAME, arguments: toolArguments },
      result,
    };
    await writeFile(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    process.stdout.write(`${JSON.stringify({ output: outputPath, tool_count: tools.tools.length, is_error: result.isError === true })}\n`);
  } finally {
    await client.close();
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : "M51 probe failed");
  process.exitCode = 1;
});
