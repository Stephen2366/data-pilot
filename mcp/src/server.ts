import { McpServer } from "@modelcontextprotocol/server";

import { loadConfig, type AdapterConfig } from "./config.js";
import { dataPilotToolInputSchema, dataPilotToolOutputSchema, TOOL_NAME, type DataPilotToolOutput } from "./contracts.js";
import { AdapterError, callDataPilot } from "./http-adapter.js";
import { projectBackendResult } from "./projector.js";

export type ServerDependencies = {
  config?: AdapterConfig;
  fetch?: typeof fetch;
};

function textSummary(output: DataPilotToolOutput): string {
  if (!output.ok) return output.error?.message ?? output.message ?? "DataPilot 未完成本次操作。";
  if (output.operation === "query") {
    const task = output.task ? ` task=${output.task.task_id}@v${output.task.task_version}` : "";
    return `${output.answer_status ?? "no_answer"}/${output.route ?? "none"}${task}: ${output.answer ?? ""}`.slice(0, 4096);
  }
  return output.message ?? "DataPilot lifecycle 操作完成。";
}

/**
 * 创建每条 MCP 连接独享的 server instance。
 *
 * Tool handler 只做三件事：调用一次 HTTP seam、执行 bounded projection、返回 SDK 结果。
 * 所有业务状态仍由 FastAPI/Python 管理，adapter 不缓存 task/version，也不猜测 unknown outcome。
 */
export function createDataPilotServer(dependencies: ServerDependencies = {}): McpServer {
  const server = new McpServer({ name: "datapilot", version: "0.1.0" });
  server.registerTool(
    TOOL_NAME,
    {
      title: "DataPilot Query",
      description: "查询企业数据、核对任务状态或按精确版本清理任务。task_id/version 必须沿用上次返回值。",
      inputSchema: dataPilotToolInputSchema,
      outputSchema: dataPilotToolOutputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    async (input) => {
      try {
        const config = dependencies.config ?? loadConfig();
        const output = projectBackendResult(await callDataPilot(input, config, dependencies.fetch));
        return {
          content: [{ type: "text", text: textSummary(output) }],
          structuredContent: output,
          isError: !output.ok,
        };
      } catch (error) {
        const known = error instanceof AdapterError;
        const output: DataPilotToolOutput = {
          ok: false,
          operation: input.operation,
          error: known
            ? { code: error.code, message: error.message, outcome: error.outcome, ...(error.status === undefined ? {} : { status: error.status }) }
            : {
                code: error instanceof Error && error.message.startsWith("configuration_invalid")
                  ? "configuration_invalid"
                  : "response_contract_invalid",
                message: error instanceof Error && error.message.startsWith("configuration_invalid")
                  ? "DataPilot MCP 启动配置无效。"
                  : "DataPilot 响应无法安全投影。",
                outcome: "not_sent",
              },
        };
        return { content: [{ type: "text", text: textSummary(output) }], structuredContent: output, isError: true };
      }
    },
  );
  return server;
}
