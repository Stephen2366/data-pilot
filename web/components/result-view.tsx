"use client";

import type { AgentResponse } from "@/lib/contracts";
import { presentResponse } from "@/lib/presenter";
import { VegaChart } from "@/components/vega-chart";

/** 将网络边界中的标量安全地格式化为表格文本，不执行 HTML 注入或业务换算。 */
function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** 结果表是权威回退：即使 Vega 动态加载失败，原始公开 rows 仍可核对。 */
function DataTable({ response }: { response: AgentResponse }) {
  if (response.columns.length === 0) return null;
  return (
    <div className="table-wrap" tabIndex={0} aria-label="查询结果表格，可横向滚动">
      <table>
        <thead>
          <tr>{response.columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {response.rows.length === 0 ? (
            <tr><td colSpan={response.columns.length} className="empty-cell">查询成功，但没有符合条件的数据。</td></tr>
          ) : response.rows.map((row, index) => (
            <tr key={index}>{response.columns.map((column) => <td key={column}>{displayValue(row[column])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Inspector 只做 JSON 可读化；null 明确显示为“未公开/未触发”。 */
function JsonSummary({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="muted">本轮未公开 / 未触发</span>;
  return <pre className="safe-json">{JSON.stringify(value, null, 2)}</pre>;
}

/**
 * 将一个已通过 Zod 的 AgentResponse 渲染为业务结果、证据和逐级 Inspector。
 * 主状态只来自纯 Presenter，组件不根据 answer 文案猜测成功与否。
 */
export function ResultView({ response }: { response: AgentResponse }) {
  const presented = presentResponse(response);
  // Tool message 仍可能含 provider/driver 原文；Inspector 只展示闭集诊断字段，不把它复制到 UI。
  const safeToolCalls = response.tool_calls.map(({ tool_name, status, latency_ms, tables_used, error_type }) => ({
    tool_name,
    status,
    latency_ms,
    tables_used,
    error_type,
  }));
  return (
    <article className="result-card">
      <header className={`status-banner tone-${presented.tone}`}>
        <div>
          <p className="eyebrow">{presented.eyebrow}</p>
          <h3>{presented.title}</h3>
          <p>{presented.detail}</p>
        </div>
        <span className="route-pill">{response.route.toUpperCase()}</span>
      </header>

      {response.answer ? <div className="answer-copy">{response.answer}</div> : (
        <p className="empty-copy">服务端本轮没有签发答案；请查看上方状态和停止原因。</p>
      )}

      {response.chart_spec ? <VegaChart spec={response.chart_spec} /> : null}
      <DataTable response={response} />

      {response.citations.length > 0 ? (
        <section className="evidence-section">
          <div className="section-heading"><h4>引用证据</h4><span>{response.citations.length} 条</span></div>
          <ol className="citation-list">
            {response.citations.map((citation, index) => (
              <li key={index}>
                <strong>{String(citation.title ?? citation.document_key ?? citation.evidence_id ?? `引用 ${index + 1}`)}</strong>
                <span>{String(citation.anchor ?? citation.source_type ?? "已验证公开引用")}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {response.hybrid_branches.length > 0 ? (
        <section className="evidence-section">
          <div className="section-heading"><h4>Hybrid 分支</h4><span>服务端公开投影</span></div>
          <div className="branch-grid">
            {response.hybrid_branches.map((branch, index) => (
              <div className="branch-card" key={index}>
                <strong>{String(branch.branch ?? `branch ${index + 1}`)}</strong>
                <span>{String(branch.answer_status ?? "unknown")}</span>
                <small>{String(branch.reason_code ?? "—")}</small>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <details className="inspector">
        <summary><span>本轮决策</span><small>TaskDelta · Action · Budget · Stop</small></summary>
        <div className="inspector-grid">
          <div><h5>Task delta</h5><JsonSummary value={response.task_delta} /></div>
          <div><h5>Transition</h5><JsonSummary value={response.task_transition} /></div>
          <div><h5>Action attempts</h5><JsonSummary value={response.action_attempts} /></div>
          <div><h5>Budget / termination</h5><JsonSummary value={{ budget: response.agent_budget, termination: response.agent_termination }} /></div>
        </div>
      </details>
      <details className="inspector">
        <summary><span>技术细节</span><small>只显示公开安全摘要</small></summary>
        <div className="inspector-grid">
          <div><h5>Runtime</h5><JsonSummary value={{ family: response.runtime_family, task: response.task_action, knowledge: response.knowledge_runtimes, loop: response.agent_loop_runtime }} /></div>
          <div><h5>Context / Compact</h5><JsonSummary value={{ context: response.task_context, compact: response.compact_decision }} /></div>
          <div><h5>Tool calls</h5><JsonSummary value={safeToolCalls} /></div>
          <div><h5>Trace</h5><JsonSummary value={{ trace_id: response.trace_id, latency_ms: response.cost.latency_ms, scenario_source: response.agent_scenario_source_identity }} /></div>
        </div>
      </details>
    </article>
  );
}
