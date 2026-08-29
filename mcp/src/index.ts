#!/usr/bin/env node
import { serveStdio } from "@modelcontextprotocol/server/stdio";

import { createDataPilotServer } from "./server.js";

// stdout 是 JSON-RPC 专用通道；人类可读日志只写 stderr。
void serveStdio(() => createDataPilotServer());
console.error("DataPilot MCP server listening on stdio");
