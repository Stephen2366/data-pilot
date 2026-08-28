import {
  agentResponseSchema,
  bffErrorSchema,
  queryRequestSchema,
  taskControlResponseSchema,
  taskStatusResponseSchema,
  type AgentResponse,
  type BffError,
  type QueryRequest,
  type TaskControlResponse,
  type TaskStatusResponse,
} from "@/lib/contracts";

export type ClientFailure = BffError["error"];

/** 把 BFF 的闭集失败投影保留下来，供页面决定“可继续”还是“冻结 lineage”。 */
export class DataPilotClientError extends Error {
  constructor(public readonly failure: ClientFailure) {
    super(failure.message);
    this.name = "DataPilotClientError";
  }
}

/**
 * 先识别 BFF 安全错误，再校验成功 payload。
 *
 * ★ HTTP 状态本身不够表达 mutation 是否执行；页面只相信 BFF 签发的 outcome，任何无法
 * 解析或合同漂移都按 unknown 处理，避免误推进 last-acknowledged version。
 */
async function decode<T>(response: Response, parse: (value: unknown) => T): Promise<T> {
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    throw new DataPilotClientError({
      code: "backend_invalid_response",
      message: "Web adapter 返回了无法读取的响应。",
      outcome: "unknown",
      status: response.status,
    });
  }
  const knownError = bffErrorSchema.safeParse(raw);
  if (knownError.success) throw new DataPilotClientError(knownError.data.error);
  try {
    return parse(raw);
  } catch {
    throw new DataPilotClientError({
      code: "response_contract_invalid",
      message: "页面无法验证 DataPilot 响应合同，已停止推进任务版本。",
      outcome: "unknown",
      status: response.status,
    });
  }
}

/**
 * 页面访问 DataPilot 的唯一 client interface。
 *
 * 组件只需要 query/clearTask 两个动作；请求校验、AbortSignal、错误分类、响应运行时校验
 * 全部藏在模块内部。这里故意没有 retry：task mutation 的结果未知时，重发可能制造双提交。
 */
export class DataPilotClient {
  async query(request: QueryRequest, signal?: AbortSignal): Promise<AgentResponse> {
    const validated = queryRequestSchema.safeParse(request);
    if (!validated.success) {
      throw new DataPilotClientError({
        code: "request_invalid",
        message: "当前输入不符合 DataPilot 请求合同。",
        outcome: "not_sent",
      });
    }
    let response: Response;
    try {
      response = await fetch("/api/datapilot/query", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(validated.data),
        signal,
      });
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === "AbortError";
      throw new DataPilotClientError({
        code: aborted ? "request_aborted" : "backend_unreachable",
        message: aborted ? "已停止等待；这次任务提交结果未知。" : "无法连接 Web adapter。",
        outcome: "unknown",
      });
    }
    const result = await decode(response, (raw) => agentResponseSchema.parse(raw));
    // FastAPI 对 stale version / role drift 使用 HTTP 200 + typed rejected response，避免把
    // owner/task 是否存在编码进 transport。它仍然是“已知未执行”的产品拒绝，不能提交成
    // 新 turn，否则 latest response.task=null 会让浏览器丢掉最后确认的 lineage/version。
    const lineageRejection = result.reason_code === "task_version_conflict" || result.reason_code === "task_unavailable";
    if (result.runtime_family === "agent_task" && result.task_action === "rejected" && lineageRejection) {
      const versionConflict = result.reason_code === "task_version_conflict";
      throw new DataPilotClientError({
        code: "backend_rejected",
        message: versionConflict
          ? "任务版本已变化，本轮未执行；当前确认版本保持不变。"
          : "当前任务不可用或身份不匹配，本轮未执行。",
        outcome: "known_rejected",
      });
    }
    return result;
  }

  async clearTask(taskId: string, version: number, role: string): Promise<TaskControlResponse> {
    // clear 同样是 mutation；网络失败时不能假设服务端没有清理，因此返回 unknown。
    let response: Response;
    try {
      response = await fetch(
        `/api/datapilot/tasks/${encodeURIComponent(taskId)}?expected_version=${version}&user_role=${encodeURIComponent(role)}`,
        { method: "DELETE" },
      );
    } catch {
      throw new DataPilotClientError({
        code: "backend_unreachable",
        message: "无法确认任务是否已被清理。",
        outcome: "unknown",
      });
    }
    return decode(response, (raw) => taskControlResponseSchema.parse(raw));
  }

  async getTaskStatus(taskId: string, role: string): Promise<TaskStatusResponse> {
    // status 是只读对账，可在 unknown 后显式调用；它不会重放上一条 mutation。
    let response: Response;
    try {
      response = await fetch(
        `/api/datapilot/tasks/${encodeURIComponent(taskId)}?user_role=${encodeURIComponent(role)}`,
        { method: "GET" },
      );
    } catch {
      throw new DataPilotClientError({
        code: "backend_unreachable",
        message: "无法核对当前任务状态。",
        outcome: "unknown",
      });
    }
    return decode(response, (raw) => taskStatusResponseSchema.parse(raw));
  }
}
