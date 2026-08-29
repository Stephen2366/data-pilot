import type { AgentResponse, TaskControlResponse, TaskStatusResponse } from "@datapilot/contracts";

import { RESULT_MAX_BYTES, type DataPilotToolOutput } from "./contracts.js";
import type { BackendResult } from "./http-adapter.js";

const ANSWER_MAX_BYTES = 16 * 1024;
const SQL_MAX_BYTES = 16 * 1024;
const COLUMN_LIMIT = 20;
const ROW_LIMIT = 50;
const CELL_MAX_BYTES = 2 * 1024;
const CITATION_LIMIT = 16;

type Scalar = string | number | boolean | null;

function jsonBytes(value: unknown): number {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

/** 按 Unicode code point 裁剪，避免在多字节中文字符中间截断。 */
export function clipUtf8(value: string, maxBytes: number): { value: string; removed: number } {
  const originalBytes = Buffer.byteLength(value, "utf8");
  if (originalBytes <= maxBytes) return { value, removed: 0 };
  const suffix = "…";
  const suffixBytes = Buffer.byteLength(suffix, "utf8");
  let used = 0;
  let result = "";
  for (const character of value) {
    const size = Buffer.byteLength(character, "utf8");
    if (used + size + suffixBytes > maxBytes) break;
    result += character;
    used += size;
  }
  const clipped = result + suffix;
  return { value: clipped, removed: originalBytes - Buffer.byteLength(clipped, "utf8") };
}

function projectCell(value: unknown): { value: Scalar; truncated: boolean } {
  if (value === null || typeof value === "number" || typeof value === "boolean") return { value, truncated: false };
  const text = typeof value === "string" ? value : JSON.stringify(value) ?? String(value);
  const clipped = clipUtf8(text, CELL_MAX_BYTES);
  return { value: clipped.value, truncated: clipped.removed > 0 };
}

function safeTask(task: AgentResponse["task"] | TaskControlResponse["task"] | TaskStatusResponse["task"]) {
  if (task === null) return null;
  return {
    task_id: task.task_id,
    task_version: task.task_version,
    status: task.status,
    expires_at: task.expires_at,
  };
}

function projectQuery(response: AgentResponse): DataPilotToolOutput {
  const answer = clipUtf8(response.answer, ANSWER_MAX_BYTES);
  const sql = response.sql === null ? null : clipUtf8(response.sql, SQL_MAX_BYTES);
  const selectedColumns = response.columns.slice(0, COLUMN_LIMIT);
  const columnPairs = selectedColumns.map((source) => ({ source, projected: clipUtf8(source, CELL_MAX_BYTES).value }));
  const columns = columnPairs.map((column) => column.projected);
  let cellsTruncated = 0;
  const rows = response.rows.slice(0, ROW_LIMIT).map((row) => {
    const projected: Record<string, Scalar> = {};
    for (const column of columnPairs) {
      if (!(column.source in row)) continue;
      const cell = projectCell(row[column.source]);
      projected[column.projected] = cell.value;
      if (cell.truncated) cellsTruncated += 1;
    }
    return projected;
  });
  const citations = response.citations.slice(0, CITATION_LIMIT).map((citation) => {
    const projected: { evidence_id?: string; title?: string; anchor?: string } = {};
    for (const key of ["evidence_id", "title", "anchor"] as const) {
      if (typeof citation[key] === "string") projected[key] = clipUtf8(citation[key] as string, CELL_MAX_BYTES).value;
    }
    return projected;
  });
  const citationFieldsTruncated = response.citations
    .slice(0, CITATION_LIMIT)
    .reduce((count, citation) => count + ["evidence_id", "title", "anchor"].filter((key) => typeof citation[key] === "string" && Buffer.byteLength(citation[key] as string, "utf8") > CELL_MAX_BYTES).length, 0);

  const output: DataPilotToolOutput = {
    ok: response.task_action !== "rejected",
    operation: "query",
    route: response.route,
    execution_status: response.execution_status,
    answer_status: response.answer_status,
    safety_status: response.safety_status,
    reason_code: response.reason_code,
    trace_id: response.trace_id,
    answer: answer.value,
    sql: sql?.value ?? null,
    columns,
    rows,
    citations,
    task: safeTask(response.task),
    ...(response.task_action === "rejected" ? { message: "DataPilot 拒绝了本次 task mutation；任务版本未推进。" } : {}),
    truncated: {
      answer_bytes_removed: answer.removed,
      sql_bytes_removed: sql?.removed ?? 0,
      columns_removed: Math.max(0, response.columns.length - columns.length),
      rows_removed: Math.max(0, response.rows.length - rows.length),
      cells_truncated: cellsTruncated,
      citations_removed: Math.max(0, response.citations.length - citations.length),
      citation_fields_truncated: citationFieldsTruncated,
    },
  };

  // 先删最占空间、同时已有明确 removed 计数的 collection；四轴、reason、trace 和 task
  // identity/version 永远不参与总大小降级。
  while (jsonBytes(output) > RESULT_MAX_BYTES && output.rows!.length > 0) {
    output.rows!.pop();
    output.truncated!.rows_removed += 1;
  }
  while (jsonBytes(output) > RESULT_MAX_BYTES && output.citations!.length > 0) {
    output.citations!.pop();
    output.truncated!.citations_removed += 1;
  }
  if (jsonBytes(output) > RESULT_MAX_BYTES) {
    const compactAnswer = clipUtf8(output.answer!, 4 * 1024);
    const compactSql = output.sql === null ? null : clipUtf8(output.sql!, 4 * 1024);
    output.truncated!.answer_bytes_removed += compactAnswer.removed;
    output.truncated!.sql_bytes_removed += compactSql?.removed ?? 0;
    output.answer = compactAnswer.value;
    output.sql = compactSql?.value ?? null;
  }
  if (jsonBytes(output) > RESULT_MAX_BYTES) throw new Error("bounded_projection_failed");
  return output;
}

function projectLifecycle(operation: "status" | "clear", response: TaskStatusResponse | TaskControlResponse): DataPilotToolOutput {
  const message = clipUtf8(response.message, CELL_MAX_BYTES).value;
  return {
    ok: response.ok,
    operation,
    safety_status: response.safety_status,
    reason_code: response.reason_code,
    message,
    task: safeTask(response.task),
  };
}

/** 从已通过共享网络 schema 的响应，生成 MCP 唯一可见的 bounded projection。 */
export function projectBackendResult(result: BackendResult): DataPilotToolOutput {
  if (result.operation === "query") return projectQuery(result.value);
  return projectLifecycle(result.operation, result.value);
}

export function structuredResultBytes(result: DataPilotToolOutput): number {
  return jsonBytes(result);
}
