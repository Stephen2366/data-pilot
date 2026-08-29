import { z } from "zod/v4";

export const TOOL_NAME = "data_pilot_query";
export const QUESTION_MAX_BYTES = 4096;
export const RESULT_MAX_BYTES = 64 * 1024;

const utf8Length = (value: string): number => Buffer.byteLength(value, "utf8");

/**
 * MCP Client 只拥有三个业务动作，不拥有 role、模型、语料库或后端地址。
 *
 * ★ `superRefine` 把 operation 对应的字段组合收成闭集：start 不能夹带 task identity，
 * continue/status/clear 也不能让 adapter 猜 version。
 */
export const dataPilotToolInputSchema = z
  .object({
    operation: z.enum(["query", "status", "clear"]),
    question: z
      .string()
      .min(1)
      .refine((value) => utf8Length(value) <= QUESTION_MAX_BYTES, "question exceeds 4096 UTF-8 bytes")
      .optional(),
    task_id: z.string().min(1).max(128).optional(),
    expected_version: z.number().int().positive().optional(),
  })
  .strict()
  .superRefine((value, context) => {
    if (value.operation === "query") {
      if (value.question === undefined) {
        context.addIssue({ code: "custom", path: ["question"], message: "query requires question" });
      }
      if ((value.task_id === undefined) !== (value.expected_version === undefined)) {
        context.addIssue({ code: "custom", path: ["task_id"], message: "continue requires task_id and expected_version" });
      }
      return;
    }
    if (value.question !== undefined) {
      context.addIssue({ code: "custom", path: ["question"], message: `${value.operation} forbids question` });
    }
    if (value.task_id === undefined) {
      context.addIssue({ code: "custom", path: ["task_id"], message: `${value.operation} requires task_id` });
    }
    if (value.operation === "status" && value.expected_version !== undefined) {
      context.addIssue({ code: "custom", path: ["expected_version"], message: "status forbids expected_version" });
    }
    if (value.operation === "clear" && value.expected_version === undefined) {
      context.addIssue({ code: "custom", path: ["expected_version"], message: "clear requires expected_version" });
    }
  });

const safeTaskSchema = z.object({
  task_id: z.string(),
  task_version: z.number().int().positive(),
  status: z.string(),
  expires_at: z.string(),
});

const truncationSchema = z.object({
  answer_bytes_removed: z.number().int().nonnegative(),
  sql_bytes_removed: z.number().int().nonnegative(),
  columns_removed: z.number().int().nonnegative(),
  rows_removed: z.number().int().nonnegative(),
  cells_truncated: z.number().int().nonnegative(),
  citations_removed: z.number().int().nonnegative(),
  citation_fields_truncated: z.number().int().nonnegative(),
});

/** MCP output 只描述 adapter 的安全投影，不复刻完整 AgentResponse。 */
export const dataPilotToolOutputSchema = z
  .object({
    ok: z.boolean(),
    operation: z.enum(["query", "status", "clear"]),
    route: z.enum(["sql", "rag", "hybrid", "none"]).optional(),
    execution_status: z.enum(["not_started", "completed", "external_unavailable", "failed"]).optional(),
    answer_status: z
      .enum(["complete", "partial", "clarification_required", "unsupported", "insufficient_evidence", "no_answer"])
      .optional(),
    safety_status: z.enum(["passed", "blocked"]).optional(),
    reason_code: z.string().nullable().optional(),
    trace_id: z.string().optional(),
    answer: z.string().optional(),
    sql: z.string().nullable().optional(),
    columns: z.array(z.string()).optional(),
    rows: z.array(z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()]))).optional(),
    citations: z
      .array(z.object({ evidence_id: z.string().optional(), title: z.string().optional(), anchor: z.string().optional() }).strict())
      .optional(),
    message: z.string().optional(),
    task: safeTaskSchema.nullable().optional(),
    truncated: truncationSchema.optional(),
    error: z
      .object({
        code: z.enum([
          "backend_rejected",
          "backend_unreachable",
          "backend_timeout",
          "backend_invalid_response",
          "response_contract_invalid",
          "configuration_invalid",
        ]),
        message: z.string(),
        outcome: z.enum(["not_sent", "known_rejected", "unknown"]),
        status: z.number().int().optional(),
      })
      .strict()
      .optional(),
  })
  .strict();

export type DataPilotToolInput = z.infer<typeof dataPilotToolInputSchema>;
export type DataPilotToolOutput = z.infer<typeof dataPilotToolOutputSchema>;
