import { agentResponseSchema, taskStatusViewSchema, type AgentResponse, type TaskStatusView } from "@/lib/contracts";

const STORAGE_KEY = "datapilot.m50.session.v1";
const MAX_TURNS = 8;

export type RuntimeMode = "agent_task" | "legacy";
export type StoredTurn = { question: string; response: AgentResponse };
export type StoredSession = {
  mode: RuntimeMode;
  role: string;
  turns: StoredTurn[];
  frozen: boolean;
  outboundQuestion: string | null;
  recoveredTask: TaskStatusView | null;
};

/**
 * sessionStorage 只保存当前 tab 的公开响应与最小 recovery 快照，并限制为最近 8 轮。
 * ★ frozen/outbound/recoveredTask 让刷新不会假装 unknown 已解决；schema 漂移时整份丢弃，
 * 绝不拿不兼容旧版本继续提交 task mutation。
 */
export function loadSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if ((value.mode !== "agent_task" && value.mode !== "legacy") || typeof value.role !== "string" || !Array.isArray(value.turns)) {
      throw new Error("invalid");
    }
    const turns = value.turns.slice(-MAX_TURNS).map((turn) => {
      const candidate = turn as { question?: unknown; response?: unknown };
      if (typeof candidate.question !== "string") throw new Error("invalid");
      return { question: candidate.question, response: agentResponseSchema.parse(candidate.response) };
    });
    const frozen = typeof value.frozen === "boolean" ? value.frozen : false;
    const outboundQuestion = typeof value.outboundQuestion === "string" ? value.outboundQuestion : null;
    const recoveredTask = value.recoveredTask == null ? null : taskStatusViewSchema.parse(value.recoveredTask);
    return { mode: value.mode, role: value.role, turns, frozen, outboundQuestion, recoveredTask };
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveSession(session: StoredSession): void {
  if (typeof window === "undefined") return;
  const turns = session.turns.slice(-MAX_TURNS);
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...session, turns }));
}

export function clearSession(): void {
  if (typeof window !== "undefined") window.sessionStorage.removeItem(STORAGE_KEY);
}
