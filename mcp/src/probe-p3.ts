#!/usr/bin/env node
/**
 * M51-P3 的单进程 lifecycle/negative 客户端。
 *
 * 同一个 SDK Client 与 stdio server 依次验证：SDK 输入拒绝、旧版本拒绝、status 对账、
 * 按 status 签发版本 clear。脚本不猜 version，也不会在 unknown 后自动重放 mutation。
 */
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";

import { TOOL_NAME } from "./contracts.js";

function requiredArgument(name: string): string {
  const index = process.argv.indexOf(`--${name}`);
  if (index < 0 || process.argv[index + 1] === undefined) throw new Error(`missing --${name}`);
  return process.argv[index + 1];
}

function structured(result: Awaited<ReturnType<Client["callTool"]>>): Record<string, unknown> {
  const value = result.structuredContent;
  if (value === undefined || value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("probe expected object structuredContent");
  }
  return value as Record<string, unknown>;
}

async function main(): Promise<void> {
  const taskId = requiredArgument("task-id");
  const staleVersion = Number(requiredArgument("stale-version"));
  const outputPath = requiredArgument("output");
  const environment = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [fileURLToPath(new URL("./index.js", import.meta.url))],
    env: environment,
  });
  const client = new Client({ name: "datapilot-m51-p3", version: "0.1.0" });
  try {
    await client.connect(transport);
    const invalid = await client.callTool({ name: TOOL_NAME, arguments: { operation: "query" } });
    const stale = await client.callTool({
      name: TOOL_NAME,
      arguments: {
        operation: "query",
        question: "再次比较当前任务结果。",
        task_id: taskId,
        expected_version: staleVersion,
      },
    });
    const status = await client.callTool({ name: TOOL_NAME, arguments: { operation: "status", task_id: taskId } });
    const statusTask = structured(status).task;
    if (statusTask === null || typeof statusTask !== "object" || !("task_version" in statusTask)) {
      throw new Error("status did not return an acknowledged task version");
    }
    const clearVersion = Number((statusTask as Record<string, unknown>).task_version);
    const clear = await client.callTool({
      name: TOOL_NAME,
      arguments: { operation: "clear", task_id: taskId, expected_version: clearVersion },
    });
    await writeFile(
      outputPath,
      `${JSON.stringify(
        {
          format: "m51-mcp-p3-v1",
          negotiated_protocol: client.getNegotiatedProtocolVersion(),
          task_id: taskId,
          stale_version: staleVersion,
          clear_version: clearVersion,
          invalid,
          stale,
          status,
          clear,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
    process.stdout.write(`${JSON.stringify({ output: outputPath, clear_version: clearVersion })}\n`);
  } finally {
    await client.close();
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : "M51 P3 probe failed");
  process.exitCode = 1;
});
