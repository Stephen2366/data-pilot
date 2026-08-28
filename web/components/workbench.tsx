"use client";

import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import type { QueryRequest, TaskStatusView } from "@/lib/contracts";
import { DataPilotClient, DataPilotClientError } from "@/lib/data-pilot-client";
import { DEMO_PRESETS } from "@/lib/presets";
import { clearSession, loadSession, saveSession, type RuntimeMode, type StoredTurn } from "@/lib/session-store";
import { ResultView } from "@/components/result-view";

type TaskAction = "start" | "continue" | "switch" | "cancel";

/** 只把最后一条服务端确认且仍 active 的 task 投影作为下一次 mutation 身份。 */
function activeTask(turns: StoredTurn[]) {
  const latest = turns.at(-1)?.response.task;
  return latest && latest.status === "active" ? latest : null;
}

/**
 * DataPilot 的 task-first 浏览器工作台。
 *
 * ★ 组件只编排表单和 last-acknowledged snapshot；task version、状态迁移和安全判断全部来自
 * FastAPI。unknown outcome 会冻结当前 lineage；用户显式 GET 对账后才能采用服务端新版本，
 * known rejection 则保留最后确认版本继续展示。
 */
export function Workbench() {
  const client = useMemo(() => new DataPilotClient(), []);
  const [mode, setMode] = useState<RuntimeMode>("agent_task");
  const [role, setRole] = useState("ops");
  const [question, setQuestion] = useState(DEMO_PRESETS[0].turns[0]);
  const [outboundQuestion, setOutboundQuestion] = useState<string | null>(null);
  const [turns, setTurns] = useState<StoredTurn[]>([]);
  const [pending, setPending] = useState(false);
  const [frozen, setFrozen] = useState(false);
  const [recoveredTask, setRecoveredTask] = useState<TaskStatusView | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const [legacyValues, setLegacyValues] = useState<Record<string, string>>({});
  const [legacyAction, setLegacyAction] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const acknowledgedTask = activeTask(turns);
  const task = recoveredTask ? (recoveredTask.status === "active" ? recoveredTask : null) : acknowledgedTask;
  const statusIdentity = recoveredTask ?? acknowledgedTask;
  const latestThread = turns.at(-1)?.response.thread ?? null;
  const clarification = mode === "legacy" && latestThread?.status === "pending" ? latestThread.clarification : null;
  const followUp = mode === "legacy" && latestThread?.status === "follow_up_ready" ? latestThread.follow_up : null;
  const selectedFollowUp = followUp?.actions.find((item) => item.action === legacyAction) ?? null;

  useEffect(() => {
    const restored = loadSession();
    if (restored) {
      startTransition(() => {
        setMode(restored.mode);
        setRole(restored.role);
        setTurns(restored.turns);
        setFrozen(restored.frozen);
        setOutboundQuestion(restored.outboundQuestion);
        setRecoveredTask(restored.recoveredTask);
      });
    }
  }, []);

  // ★ 新消息出现后只滚动聊天时间线，不推动整个页面。CSS 的 scroll-behavior 会自动尊重
  // prefers-reduced-motion，避免在用户频繁发送时增加多余的全屏运动。
  useEffect(() => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    timeline.scrollTo({ top: timeline.scrollHeight });
  }, [pending, turns]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/datapilot/health", { signal: controller.signal })
      .then((response) => setApiReady(response.ok))
      .catch(() => setApiReady(false));
    return () => controller.abort();
  }, []);

  function persist(
    nextTurns: StoredTurn[],
    nextFrozen: boolean,
    nextOutbound: string | null,
    nextRecovered: TaskStatusView | null,
  ) {
    setTurns(nextTurns);
    setFrozen(nextFrozen);
    setOutboundQuestion(nextOutbound);
    setRecoveredTask(nextRecovered);
    saveSession({ mode, role, turns: nextTurns, frozen: nextFrozen, outboundQuestion: nextOutbound, recoveredTask: nextRecovered });
  }

  /** 根据当前 runtime 组装互斥的 task 或 legacy envelope，成功后才提交本地快照。 */
  async function submit(action: TaskAction = task ? "continue" : "start") {
    const clean = question.trim();
    const isLegacyStructured = Boolean(clarification || selectedFollowUp);
    if ((!clean && !isLegacyStructured) || pending || frozen) return;
    const sentQuestion = action === "cancel"
      ? "取消当前任务。"
      : clean || (clarification ? "补充结构化条件" : "执行结构化追问");
    const controller = new AbortController();
    abortRef.current = controller;
    setPending(true);
    setNotice(null);
    setOutboundQuestion(sentQuestion);
    setQuestion("");
    const request: QueryRequest = mode === "agent_task"
      ? {
          question: action === "cancel" ? "取消当前任务。" : clean,
          user_role: role,
          force_new_pipeline: true,
          task: action === "start"
            ? { action: "start" }
            : { action, task_id: task?.task_id, expected_version: task?.task_version },
        }
      : clarification && latestThread
        ? {
            question: clean || "补充结构化条件",
            user_role: role,
            force_new_pipeline: true,
            thread_id: latestThread.thread_id,
            expected_version: latestThread.checkpoint_version,
            clarification_answers: legacyValues,
          }
        : selectedFollowUp && latestThread
          ? {
              question: clean || "执行结构化追问",
              user_role: role,
              force_new_pipeline: true,
              thread_id: latestThread.thread_id,
              expected_version: latestThread.checkpoint_version,
              follow_up_action: selectedFollowUp.action,
              follow_up_fields: legacyValues,
            }
          : { question: clean, user_role: role, force_new_pipeline: true, enable_bounded_follow_up: true };
    try {
      const response = await client.query(request, controller.signal);
      const next = [...turns, { question: sentQuestion, response }].slice(-8);
      persist(next, response.task_action === "cancel", null, null);
      setLegacyValues({});
      setLegacyAction(null);
    } catch (error) {
      if (error instanceof DataPilotClientError) {
        setNotice(error.failure.message);
        if (error.failure.outcome === "unknown") {
          const lastKnown = task
            ? { task_id: task.task_id, task_version: task.task_version, status: task.status, expires_at: task.expires_at }
            : null;
          persist(turns, true, sentQuestion, lastKnown);
        } else {
          // 服务端明确未接纳时允许用户修改后再发；未知结果则保留已发送气泡并冻结。
          setQuestion(clean);
          setOutboundQuestion(null);
        }
      } else {
        setNotice("页面发生未识别错误，任务版本没有推进。");
        persist(turns, true, sentQuestion, statusIdentity);
      }
    } finally {
      abortRef.current = null;
      setPending(false);
    }
  }

  /** clear 只有拿到服务端 ok 后才同步抹掉浏览器快照；unknown 时保留现场并冻结。 */
  async function clearCurrentTask() {
    if (!task || pending) return;
    setPending(true);
    setNotice(null);
    try {
      const control = await client.clearTask(task.task_id, task.task_version, role);
      if (control.ok) {
        setTurns([]);
        setFrozen(false);
        setRecoveredTask(null);
        setOutboundQuestion(null);
        clearSession();
        setNotice("任务已在服务端清理，本地公开快照也已移除。");
      } else {
        setNotice(control.message);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "任务清理失败。");
      if (error instanceof DataPilotClientError && error.failure.outcome === "unknown") setFrozen(true);
    } finally {
      setPending(false);
    }
  }

  /** unknown 后只发 GET 对账：不重放 mutation，也不猜测服务端版本。 */
  async function checkTaskStatus() {
    if (!statusIdentity || pending) return;
    setPending(true);
    setNotice(null);
    try {
      const control = await client.getTaskStatus(statusIdentity.task_id, role);
      if (!control.ok || !control.task) {
        setNotice(control.message);
        return;
      }
      const next = control.task;
      if (next.status === "claimed") {
        persist(turns, true, outboundQuestion, next);
        setNotice("服务端仍在执行这轮任务；可以稍后再次检查，页面不会自动重发。 ");
      } else if (next.status === "active") {
        const advanced = next.task_version > statusIdentity.task_version;
        persist(turns, !advanced, outboundQuestion, next);
        setNotice(advanced
          ? `服务端已完成并提交到 v${next.task_version}；原响应未送达，但现在可以继续提问或清理任务。`
          : "服务端尚未提交新版本，当前 lineage 继续冻结。 ");
      } else {
        persist(turns, false, outboundQuestion, next);
        setNotice(`服务端任务状态为 ${next.status}；现在可以开始新任务。`);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "任务状态核对失败。");
    } finally {
      setPending(false);
    }
  }

  function selectPreset(id: string) {
    // ★ active task 的 role/lineage 已由服务端签发；此时切到 legacy preset 会让界面模式与
    // task identity 分叉。必须先 clear/cancel，而不是只靠按钮 disabled 假设调用不会发生。
    if (task || pending) return;
    const preset = DEMO_PRESETS.find((item) => item.id === id);
    if (!preset) return;
    setMode(preset.runtime);
    setRole(preset.role);
    setQuestion(preset.turns[0]);
    setLegacyValues({});
    setLegacyAction(null);
    setNotice(`${preset.title}：${preset.boundary}`);
  }

  function startFresh() {
    // 这里只重置本地 UI；unknown mutation 的服务端 task 状态不可被浏览器猜测。
    setTurns([]);
    setFrozen(false);
    setRecoveredTask(null);
    clearSession();
    setOutboundQuestion(null);
    setQuestion(DEMO_PRESETS[0].turns[0]);
    setNotice("已仅清理本地工作区。若旧 task 仍 active，请先使用“清理任务”。");
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a href="#workspace" className="brand" aria-label="DataPilot 首页">
          <span className="brand-mark">DP</span>
          <span><strong>DataPilot</strong><small>Evidence-first analytics agent</small></span>
        </a>
        <div className={`runtime-badge ${apiReady === false ? "offline" : ""}`}>
          <i /> {apiReady === null ? "CHECKING API" : apiReady ? "API READY" : "API OFFLINE"}
        </div>
      </header>

      <section className="workspace" id="workspace">
        <aside className="preset-rail">
          <div className="rail-heading"><span>演示场景</span><small>真实 API</small></div>
          {DEMO_PRESETS.map((preset) => (
            <button key={preset.id} className="preset-button" onClick={() => selectPreset(preset.id)} disabled={pending || Boolean(task)}>
              <span className="preset-icon">{preset.runtime === "agent_task" ? "↗" : "↺"}</span>
              <span><strong>{preset.title}</strong><small>{preset.description}</small></span>
            </button>
          ))}
          <div className="dependency-note">
            <span>运行边界</span>
            <p>SQL 演示使用 <code>datapilot_demo</code>。RAG strategy 只能由服务端配置。</p>
            <p className={apiReady ? "ready-copy" : "offline-copy"}>{apiReady ? "FastAPI 已就绪" : "FastAPI 未就绪，真实 preset 暂不可运行"}</p>
          </div>
        </aside>

        <div className="conversation-panel">
          <div className="panel-toolbar">
            <div className="segmented" aria-label="运行模式">
              <button className={mode === "agent_task" ? "active" : ""} onClick={() => setMode("agent_task")} disabled={Boolean(task)}>Agent task</button>
              <button className={mode === "legacy" ? "active" : ""} onClick={() => setMode("legacy")} disabled={Boolean(task)}>Legacy</button>
            </div>
            <div className="task-meta">
              {task ? <><span>v{task.task_version}</span><code>{task.task_id.slice(0, 10)}…</code></> : <span>尚未开始 task</span>}
            </div>
          </div>

          <div className="timeline" ref={timelineRef} aria-live="polite">
            {turns.length === 0 ? (
              <div className="empty-stage">
                <div className="orb">◎</div>
                <h2>从一个清晰问题开始</h2>
                <p>选择左侧场景，或直接描述你想验证的业务指标。</p>
              </div>
            ) : turns.map((turn, index) => (
              <div className="turn" key={`${turn.response.trace_id}-${index}`}>
                <div className="question-bubble"><span>YOU · TURN {index + 1}</span><p>{turn.question}</p></div>
                <ResultView response={turn.response} />
              </div>
            ))}
            {outboundQuestion ? (
              <div className="outbound-turn">
                <div className="question-bubble"><span>YOU · SENT</span><p>{outboundQuestion}</p></div>
                {pending ? <div className="pending-card"><span className="spinner" /><div><strong>DataPilot 正在查询和分析</strong><p>正在等待服务端返回。</p></div></div> : null}
              </div>
            ) : null}
          </div>

          <div className="composer-wrap">
            {notice ? <div className="notice" role="status">{notice}</div> : null}
            {frozen ? (
              <div className="frozen-banner">
                <div><strong>当前 lineage 已冻结</strong><span>上次 mutation 结果未知或任务已结束；不会自动重试。</span></div>
                <div className="frozen-actions">
                  {statusIdentity ? <button onClick={() => void checkTaskStatus()} disabled={pending}>检查任务状态</button> : null}
                  <button onClick={startFresh}>新建本地工作区</button>
                </div>
              </div>
            ) : null}
            {clarification ? (
              <div className="legacy-form">
                <div><strong>{clarification.prompt}</strong><span>服务端签发的澄清字段</span></div>
                <div className="legacy-fields">
                  {clarification.fields.map((field) => (
                    <label key={field.key}>{field.label}
                      {field.value_type === "enum" ? (
                        <select value={legacyValues[field.key] ?? ""} onChange={(event) => setLegacyValues({ ...legacyValues, [field.key]: event.target.value })}>
                          <option value="">请选择</option>
                          {field.allowed_values.map((value) => <option key={value} value={value}>{value}</option>)}
                        </select>
                      ) : (
                        <input maxLength={field.max_length} value={legacyValues[field.key] ?? ""} onChange={(event) => setLegacyValues({ ...legacyValues, [field.key]: event.target.value })} />
                      )}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
            {followUp ? (
              <div className="legacy-form">
                <div><strong>选择一次受控追问</strong><span>预算剩余 {latestThread?.follow_up_budget_remaining ?? 0}</span></div>
                <div className="follow-up-actions">
                  {followUp.actions.map((item) => (
                    <button className={legacyAction === item.action ? "active" : ""} key={item.action} onClick={() => { setLegacyAction(item.action); setLegacyValues({}); }}>
                      {item.label}
                    </button>
                  ))}
                </div>
                {selectedFollowUp ? <div className="legacy-fields">
                  {selectedFollowUp.fields.map((field) => (
                    <label key={field.key}>{field.label}
                      <input maxLength={field.max_length} value={legacyValues[field.key] ?? ""} onChange={(event) => setLegacyValues({ ...legacyValues, [field.key]: event.target.value })} />
                    </label>
                  ))}
                </div> : null}
              </div>
            ) : null}
            <div className="composer">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit();
                  }
                }}
                placeholder="例如：比较 2026 年 7 月和 8 月实际净退款金额…"
                disabled={pending || frozen}
                aria-label="输入数据分析问题"
              />
              <div className="composer-actions">
                <label>角色
                  <select value={role} onChange={(event) => setRole(event.target.value)} disabled={pending || Boolean(task)}>
                    <option value="ops">ops</option>
                    <option value="customer_service">customer_service</option>
                    <option value="demo_user">demo_user</option>
                  </select>
                </label>
                <div className="action-buttons">
                  {pending ? <button className="ghost-button" onClick={() => abortRef.current?.abort()}>停止等待</button> : null}
                  {task && !pending ? <button className="ghost-button" onClick={() => void submit("switch")}>切换任务</button> : null}
                  <button className="send-button" onClick={() => void submit()} disabled={apiReady !== true || pending || frozen || (!question.trim() && !clarification && !selectedFollowUp)}>
                    {clarification ? "提交澄清" : selectedFollowUp ? "执行追问" : task ? "继续任务" : "开始分析"}<span>↗</span>
                  </button>
                </div>
              </div>
            </div>
            {task ? (
              <div className="task-controls">
                <button onClick={() => void submit("cancel")} disabled={pending}>取消任务</button>
                <button onClick={() => void clearCurrentTask()} disabled={pending}>清理任务与本地快照</button>
              </div>
            ) : null}
            <p className="composer-footnote">Enter 提交 · Shift + Enter 换行 · mutation 从不自动重试</p>
          </div>
        </div>
      </section>
    </main>
  );
}
