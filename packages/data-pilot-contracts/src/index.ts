import { z } from "zod/v4";

/**
 * DataPilot 的 TypeScript 网络边界校验。
 *
 * ★ Python/Pydantic 仍是业务合同 authority；这个私有包只让 Web 与 MCP 复用同一个
 * “不信任网络响应”的 runtime gate。它不包含 UI presenter、MCP projector 或业务状态机。
 */
const publicRecord = z.record(z.string(), z.unknown());

export const taskEnvelopeSchema = z
  .object({
    action: z.enum(["start", "continue", "switch", "cancel"]),
    task_id: z.string().min(1).max(128).nullable().optional(),
    expected_version: z.number().int().positive().nullable().optional(),
  })
  .strict();

export const queryRequestSchema = z
  .object({
    question: z.string().min(1),
    user_role: z.string().min(1),
    force_new_pipeline: z.boolean().optional(),
    enable_bounded_follow_up: z.boolean().optional(),
    task: taskEnvelopeSchema.optional(),
    thread_id: z.string().min(1).max(128).optional(),
    expected_version: z.number().int().positive().optional(),
    clarification_answers: z.record(z.string(), z.string()).optional(),
    follow_up_action: z
      .enum(["adjust_sql_scope", "explain_same_evidence", "ask_related_evidence"])
      .optional(),
    follow_up_fields: z.record(z.string(), z.string()).optional(),
  })
  .strict();

const costSchema = z.object({
  latency_ms: z.number().nonnegative(),
  sql_time_ms: z.number().nonnegative(),
  model: z.string().nullable(),
  prompt_tokens: z.number().int().nonnegative(),
  completion_tokens: z.number().int().nonnegative(),
});

const toolCallSchema = z.object({
  tool_name: z.string(),
  status: z.enum(["success", "blocked", "error", "skipped"]),
  latency_ms: z.number().nonnegative(),
  sql: z.string().nullable(),
  tables_used: z.array(z.string()),
  error_type: z.string().nullable(),
  message: z.string().nullable(),
});

const clarificationFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  value_type: z.enum(["text", "time_range", "enum"]),
  allowed_values: z.array(z.string()),
  max_length: z.number().int().positive(),
});

const threadSchema = z.object({
  thread_id: z.string().min(1),
  checkpoint_version: z.number().int().positive(),
  state_version: z.string(),
  status: z.enum(["pending", "claimed", "follow_up_ready", "follow_up_claimed", "resolved", "cleared"]),
  expires_at: z.string(),
  clarification: z
    .object({
      identity: z.string(),
      prompt: z.string(),
      fields: z.array(clarificationFieldSchema),
    })
    .nullable(),
  follow_up: z
    .object({
      identity: z.string(),
      actions: z.array(
        z.object({
          action: z.enum(["adjust_sql_scope", "explain_same_evidence", "ask_related_evidence"]),
          label: z.string(),
          fields: z.array(clarificationFieldSchema),
        }),
      ),
    })
    .nullable(),
  follow_up_budget_remaining: z.number().int().min(0).max(1),
});

export const taskViewSchema = z.object({
  task_id: z.string().min(1),
  task_version: z.number().int().positive(),
  status: z.enum(["claimed", "active", "cancelled", "switched", "cleared"]),
  expires_at: z.string(),
  state: publicRecord,
  context: publicRecord.nullable(),
});

export const agentResponseSchema = z.object({
  route: z.enum(["sql", "rag", "hybrid", "none"]),
  answer: z.string(),
  sql: z.string().nullable(),
  columns: z.array(z.string()),
  rows: z.array(publicRecord),
  tables_used: z.array(z.string()),
  docs_used: z.array(publicRecord),
  chart_spec: publicRecord.nullable(),
  safety_status: z.enum(["passed", "blocked"]),
  blocked_reason: z.string().nullable(),
  cost: costSchema,
  tool_calls: z.array(toolCallSchema),
  error_type: z.string().nullable(),
  trace_id: z.string().min(1),
  execution_status: z.enum(["not_started", "completed", "external_unavailable", "failed"]),
  answer_status: z.enum([
    "complete",
    "partial",
    "clarification_required",
    "unsupported",
    "insufficient_evidence",
    "no_answer",
  ]),
  citations: z.array(publicRecord),
  reason_code: z.string().nullable(),
  turn_action: z.enum(["initial", "resume", "follow_up", "rejected"]),
  graph_invocation_count: z.number().int().min(0).max(1),
  thread: threadSchema.nullable(),
  hybrid_branches: z.array(publicRecord),
  runtime_family: z.enum(["legacy", "agent_task"]),
  task_action: z.enum(["start", "continue", "switch", "cancel", "rejected"]).nullable(),
  task_runtime_invocation_count: z.number().int().min(0).max(1),
  task: taskViewSchema.nullable(),
  task_delta: publicRecord.nullable(),
  task_transition: publicRecord.nullable(),
  node_contexts: z.array(publicRecord),
  action_attempts: z.array(publicRecord),
  agent_budget: publicRecord.nullable(),
  agent_termination: publicRecord.nullable(),
  knowledge_runtimes: z.array(z.record(z.string(), z.string())),
  agent_loop_runtime: publicRecord.nullable(),
  agent_scenario_source_identity: z.string().nullable(),
  task_context: publicRecord.nullable(),
  compact_decision: publicRecord.nullable(),
});

export const taskControlResponseSchema = z.object({
  ok: z.boolean(),
  reason_code: z.string(),
  safety_status: z.enum(["passed", "blocked"]),
  message: z.string(),
  task: taskViewSchema.nullable(),
});

export const taskStatusViewSchema = z.object({
  task_id: z.string().min(1),
  task_version: z.number().int().positive(),
  status: z.enum(["claimed", "active", "cancelled", "switched", "cleared", "expired"]),
  expires_at: z.string(),
});

export const taskStatusResponseSchema = z.object({
  ok: z.boolean(),
  reason_code: z.string(),
  safety_status: z.enum(["passed", "blocked"]),
  message: z.string(),
  task: taskStatusViewSchema.nullable(),
});

export const bffErrorSchema = z.object({
  ok: z.literal(false),
  error: z.object({
    code: z.enum([
      "request_invalid",
      "backend_rejected",
      "backend_unreachable",
      "backend_timeout",
      "backend_invalid_response",
      "response_contract_invalid",
      "request_aborted",
    ]),
    message: z.string(),
    outcome: z.enum(["not_sent", "known_rejected", "unknown"]),
    status: z.number().int().optional(),
  }),
});

export type QueryRequest = z.infer<typeof queryRequestSchema>;
export type AgentResponse = z.infer<typeof agentResponseSchema>;
export type TaskControlResponse = z.infer<typeof taskControlResponseSchema>;
export type TaskStatusView = z.infer<typeof taskStatusViewSchema>;
export type TaskStatusResponse = z.infer<typeof taskStatusResponseSchema>;
export type BffError = z.infer<typeof bffErrorSchema>;
