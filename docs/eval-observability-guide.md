# DataPilot Eval 与可观测链路说明

> 本文档说明当前 DataPilot 的 eval 功能、JSONL Trace 主链路、Phase 3B 新增 LangFuse 链路、它们之间如何切换，以及后续排查 / 扩展时要注意什么。
>
> 当前口径：**JSONL + Markdown report 是主链路，LangFuse 是可选观测旁路，LLM-as-Judge 是显式开启的增强评分，不是默认验收依赖。**

## 先用大白话讲

DataPilot 现在有三层“检查系统好不好”的能力：

1. **报告层**：跑完一批问题后，生成 Markdown 报告，告诉你哪些 case 过了、哪些没过。
2. **录像层**：每个实际进入 `/api/query` 的请求都会写一行 JSONL trace，记录这次 Agent 到底走了哪些步骤、生成了什么 SQL、用了哪些表、有没有被安全拦截。
3. **看板层**：如果打开 LangFuse，系统会把关键 span 和 score 写到 LangFuse Cloud，方便在网页上看过程和分数。

最重要的边界是：

- **不打开 LangFuse，eval 仍然能跑。**
- **LangFuse 挂了，JSONL trace 和 Markdown report 仍然应该可用。**
- **网页 UI 里没有跑通 Experiment，不代表 DataPilot eval 失败；当前主要验证方式是本地 eval 脚本跑完后写 trace / score。**

## 当前已有能力

### 1. Eval 执行链路

入口文件：[eval/run_eval.py](D:/.Work/Practice/AI-Project/data-pilot/eval/run_eval.py)

当前 eval 的基本流程是：

```text
YAML cases
-> FastAPI TestClient 调 /api/query
-> 得到 AgentResponse
-> L1/L2 规则 scorer 打分
-> 可选 L3 LLM-as-Judge 打分
-> 写 Markdown report
-> 写 JSONL trace
-> 若 LangFuse 可用，按 langfuse_trace_id 回写 Scores
```

默认 eval 使用内存 SQLite seed，不直接碰 MySQL 开发库。这样做是为了让评测可复现，也避免“跑评测”顺手改了本地数据库状态。

注意：如果某条 case 因 pipeline mode 不支持而被 eval 直接标记为 skipped，它不会真正调用 `/api/query`，因此也不会产生对应 JSONL trace。

### 2. JSONL Trace 主链路

入口文件：[engine/trace/recorder.py](D:/.Work/Practice/AI-Project/data-pilot/engine/trace/recorder.py)

JSONL 是当前最稳定的本地观测数据。每一行对应一次实际进入 `/api/query` 的请求 trace，常见字段包括：

```text
trace_id
question
user_role
route
answer
sql
columns
rows
tables_used
chart_spec
safety_status
blocked_reason
cost
tool_calls
trace_steps
error_type
langfuse_trace_id
langfuse_trace_url
langfuse_write_status
langfuse_span_mode
```

其中 `trace_steps` 是最重要的过程信息。完整步骤主要覆盖 `new_text2sql` / `force_new_pipeline`；baseline 或 skipped case 可能没有完整 `trace_steps`。它记录类似这些步骤：

```text
schema_retrieval
schema_context
join_path
query_plan
plan_validation
sql_generation
sql_guard
sql_execution
chart_generation
```

当前 `parent_step_id` 主要用于保留 QueryPlan step 引用，还不是一个可直接还原完整 span tree 的父子关系字段。后续如果要构建真正的 DAG / span tree，应拆出 `TraceStep.step_id` 和 `plan_step_id`。

### 3. LangFuse 可观测旁路

相关文件：

- [engine/trace/lifecycle.py](D:/.Work/Practice/AI-Project/data-pilot/engine/trace/lifecycle.py)
- [engine/trace/langfuse_backend.py](D:/.Work/Practice/AI-Project/data-pilot/engine/trace/langfuse_backend.py)
- [eval/scorers/langfuse_scores.py](D:/.Work/Practice/AI-Project/data-pilot/eval/scorers/langfuse_scores.py)

Phase 3B 后，LangFuse 可以做两件事：

1. **写 trace / span**：把 DataPilot 的关键过程写到 LangFuse。
2. **写 score**：把本地 scorer 的评分回写到对应 LangFuse trace 上。

当前采用双 ID 策略：

| ID | 用途 |
|---|---|
| `trace_id` | DataPilot 自己的请求 ID，用于 API 响应、响应头、JSONL、Markdown report |
| `langfuse_trace_id` | LangFuse 自己的 trace ID，用于 LangFuse Cloud trace / score |

不要把这两个 ID 混成一个。eval 回写 score 时，会先从 JSONL 中读取：

```text
DataPilot trace_id -> langfuse_trace_id
```

然后再按 `langfuse_trace_id` 写 LangFuse Score。

### 4. Scorer 分层

相关目录：[eval/scorers](D:/.Work/Practice/AI-Project/data-pilot/eval/scorers)

当前 scorer 分三层：

| 层级 | 当前状态 | 说明 |
|---|---|---|
| L1 规则评分 | 默认开启 | 安全、表命中、列召回、SQL 执行成功、延迟等 |
| L2 结果评分 | 默认开启 | `expected_value`、`result_match`、`contains`、`equals` 等 |
| L3 LLM-as-Judge | 默认关闭 | 只有传 `--judge-model` 或配置 `EVAL_JUDGE_MODEL` 才运行 |

当前常见 score 名称：

```text
rule:safety_compliance
rule:table_hit
rule:column_recall
rule:sql_success
rule:latency_p95
rule:expected_value
rule:result_match
rule:contains
rule:equals
rule:manual_review
llm:correctness
```

## 三条链路怎么切换

### 链路 A：只跑本地 eval

适合日常开发、回归检查、没有网络或不想上传 LangFuse 时使用。

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"
$env:LANGFUSE_ENABLED = "false"

& $py -m eval.run_eval `
  --pipeline-mode new_text2sql `
  --cases eval\cases\phase3a-regression.yaml `
  --report .agent_work\temp\eval-regression-report.md `
  --trace .agent_work\temp\eval-regression-traces.jsonl
```

输出：

- `.agent_work/temp/eval-regression-report.md`
- `.agent_work/temp/eval-regression-traces.jsonl`

这条链路不需要 LangFuse。

### 链路 B：本地 eval + LangFuse trace / score

适合需要在 LangFuse Cloud 看 span 和 score 时使用。

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"
$env:LANGFUSE_ENABLED = "true"
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"

& $py -m eval.run_eval `
  --pipeline-mode new_text2sql `
  --cases eval\cases\phase3a-regression.yaml `
  --report .agent_work\temp\eval-langfuse-report.md `
  --trace .agent_work\temp\eval-langfuse-traces.jsonl
```

跑完后看命令输出里的：

```text
langfuse_scores=ok:<n> skipped:<n> failed:<n>
passed=<x>/<total>
```

同时 Markdown report 会包含 `Score Summary` 和 `LangFuse Score Write`。然后打开 JSONL，找到 `langfuse_trace_url` 或 `langfuse_trace_id`，就能去 LangFuse UI 反查。只有 `langfuse_write_status=ok` 的 trace 才会被用于 score 回写。

### 链路 C：一键 smoke 检查 LangFuse 是否真的通

适合 Phase 3B 收工、网络不确定、怀疑 LangFuse 写入失败时使用。

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"
$env:LANGFUSE_ENABLED = "true"
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"

& $py scripts\smoke_phase3b_langfuse.py `
  --trace .agent_work\temp\phase3b-smoke-traces.jsonl `
  --require-langfuse `
  --visibility-timeout-seconds 45
```

这个脚本检查：

```text
config.snapshot
config.langfuse
api.query
jsonl.trace
jsonl.langfuse_mapping
langfuse.score
langfuse.trace_visibility
```

注意：`PENDING` 不一定是失败，可能只是 LangFuse ingestion 还没完成；`FAIL` 才表示明确失败。

## pipeline 怎么切换

当前 eval 有两种 pipeline 口径：

| 口径 | 命令 | 说明 |
|---|---|---|
| baseline | 不传 `--pipeline-mode`，或 case 自己配置 baseline | 老链路，部分 Phase 3A 新能力无法验证 |
| new_text2sql | `--pipeline-mode new_text2sql` | 新 Text2SQL 主链路，Phase 3B 的 live lifecycle spans 主要服务它 |

如果要看 Phase 3B 的完整过程信息，优先使用：

```powershell
--pipeline-mode new_text2sql
```

因为 M16B 的 lifecycle span 下沉主要覆盖 `force_new_pipeline` / `new_text2sql`。

## 用例集怎么选

当前常用 case 文件：

| 文件 | 用途 |
|---|---|
| `eval/cases/smoke.yaml` | 最小冒烟，快速确认 eval 能跑 |
| `eval/cases/phase3a-regression.yaml` | formal / 回归主线，适合看核心能力有没有退化 |
| `eval/cases/database-upgrade-challenge.yaml` | challenge，适合看困难 SQL、复杂边界 |
| `eval/cases/phase3a-diagnostic-benchmark.yaml` | diagnostic，适合定位失败模式，不追满分 |

建议顺序：

1. 先跑 `smoke.yaml`，确认命令和环境没问题。
2. 再跑 `phase3a-regression.yaml`，看主线有没有退化。
3. 再跑 `database-upgrade-challenge.yaml`，看困难 case。
4. 最后跑 `phase3a-diagnostic-benchmark.yaml`，专门分析失败原因。

## 三类常用验证命令

### 1. formal / regression

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"

& $py -m eval.run_eval `
  --pipeline-mode new_text2sql `
  --cases eval\cases\phase3a-regression.yaml `
  --report .agent_work\temp\phase3b-regression-report.md `
  --trace .agent_work\temp\phase3b-regression-traces.jsonl
```

### 2. challenge

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"

& $py -m eval.run_eval `
  --pipeline-mode new_text2sql `
  --cases eval\cases\database-upgrade-challenge.yaml `
  --report .agent_work\temp\phase3b-challenge-report.md `
  --trace .agent_work\temp\phase3b-challenge-traces.jsonl
```

### 3. diagnostic

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"

& $py -m eval.run_eval `
  --pipeline-mode new_text2sql `
  --cases eval\cases\phase3a-diagnostic-benchmark.yaml `
  --report .agent_work\temp\phase3b-diagnostic-report.md `
  --trace .agent_work\temp\phase3b-diagnostic-traces.jsonl
```

## 如何输出流程数据给 AI / LLM-as-Judge

当前最推荐的方式是输出 JSONL trace：

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"

& $py -m eval.run_eval `
  --pipeline-mode new_text2sql `
  --cases eval\cases\phase3a-regression.yaml `
  --report .agent_work\temp\review-report.md `
  --trace .agent_work\temp\review-traces.jsonl
```

然后让 AI 读取：

```text
.agent_work/temp/review-report.md
.agent_work/temp/review-traces.jsonl
```

建议提问：

```text
请阅读 .agent_work/temp/review-report.md 和 .agent_work/temp/review-traces.jsonl，
按 case 分析失败原因。重点判断失败发生在 schema_retrieval、query_plan、
sql_generation、sql_guard、sql_execution、answer/result_match 还是 scorer 本身。
不要只看最终 pass/fail，要结合 trace_steps 和 response body。
```

如果要喂给 LLM-as-Judge，理想输入不是完整原始 JSONL，而是后续新增一个 `trace_summary` 工具，把每条 trace 压成：

```json
{
  "case_id": "db_xxx",
  "question": "...",
  "final_answer": "...",
  "generated_sql": "...",
  "tables_used": ["orders", "order_items"],
  "safety_status": "passed",
  "steps": [
    {"name": "schema_retrieval", "status": "success", "summary": "..."},
    {"name": "query_plan", "status": "success", "summary": "..."},
    {"name": "sql_generation", "status": "success", "summary": "..."},
    {"name": "sql_execution", "status": "success", "summary": "..."}
  ],
  "rule_scores": {
    "rule:table_hit": 1.0,
    "rule:expected_value": 0.0
  }
}
```

当前 Phase 3B 已经有原始 trace 数据，但还没有正式的 `trace_summary` 工具。这是后续 eval 深化时最值得补的一小层。

## 网页 UI 与本地 eval 的关系

LangFuse UI 适合：

- 人工查看 trace / span。
- 人工从 trace 创建 Dataset item。
- 查看 score 附着在哪个 trace 上。
- 做少量 workflow smoke。

但当前 DataPilot 不依赖 UI 完成 eval。原因是 LangFuse `Run experiment` 有两条路径：

| UI 路径 | 当前状态 |
|---|---|
| via User Interface | 需要 LangFuse 项目里配置 LLM API key、prompt version 和模型参数 |
| via Webhook | 需要 DataPilot / EvalBench 提供 remote experiment URL |

当前 DataPilot 没有实现 webhook runner，也不在 Phase 3B 临时实现。正式自动化 Experiment 更适合留给 EvalBench。

所以当前正确口径是：

```text
本地 eval 脚本负责执行 case；
JSONL 负责保存完整流程；
LangFuse 负责可视化 trace/span 和承载 score；
网页 UI 只是观察和少量手动 smoke，不是当前主验收入口。
```

## 关键注意事项

### 1. LangFuse 默认关闭

默认配置：

```text
LANGFUSE_ENABLED=false
```

这不是功能缺失，而是有意设计：观测系统不能成为本地开发和 CI 的硬依赖。

### 2. Windows 网络建议显式代理

当前环境曾出现 LangFuse Cloud 裸连 `WinError 10013`。真实 Cloud smoke 建议设置：

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
```

### 3. Score 写入和 trace 可见性要分开看

可能出现：

```text
score 写入 PASS
trace visibility PENDING / FAIL
```

这不一定表示 score 逻辑错了，可能是 LangFuse ingestion 延迟或网络查询失败。M18 smoke 已经把这两个检查拆开。

当前 score payload 只会从 `langfuse_write_status=ok` 的 JSONL 映射生成；如果 trace 写入状态是 `failed`，本地 Markdown 仍然可用，但不会继续给该 LangFuse trace 回写 score。

### 4. JSONL 里可能有业务数据

JSONL trace 会保存问题、SQL、结果行、表名、字段等信息。临时 eval 输出默认放 `.agent_work/temp/`，不要随手提交。

长期 trace 默认路径是：

```text
eval/traces/traces.jsonl
```

该目录只保留 `.gitkeep`，实际 JSONL 默认不提交。

### 5. Dataset CSV 不等于正式 benchmark

M18 中导出的 LangFuse Dataset CSV 只是 workflow smoke 素材。后续如果做正式 EvalBench dataset，应从 YAML case 或 root trace 生成，避免误选中间 span 作为样本。

### 6. LLM-as-Judge 不能替代规则 scorer

当前原则是：

```text
能用规则判断的，不用 LLM；
规则判断不了的语义正确性，再显式打开 judge。
```

LLM judge 适合辅助判断，不适合作为唯一真相。

### 7. 当前 span 主要覆盖 Text2SQL

Phase 3B 的 span 当前主要服务 `new_text2sql`。RAG / Hybrid 还没进入主阶段，所以 retrieval chunk、faithfulness、context relevancy、multi-tool orchestration 等 span 还没覆盖。

## 当前还差什么

从“DataPilot 当前阶段可用”角度看，eval 已经够支撑 Phase 3B 收口。

从“完整 Agent Eval 系统”角度看，还差：

1. **trace_summary 工具**：把 JSONL trace 自动压成适合 AI / judge 阅读的摘要。
2. **失败归因器**：自动判断 case 失败主要发生在哪一层。
3. **RAG / Hybrid 专用 scorer**：例如 context coverage、retrieval recall、faithfulness。
4. **LangFuse DatasetRun / Webhook 自动化**：当前不做，后续 EvalBench 更适合承接。
5. **长期评测结果库**：当前 Markdown + JSONL 足够阶段开发，趋势分析可以后续迁 SQLite / EvalBench。

## 推荐使用习惯

日常开发：

```text
先跑 smoke -> 再跑 regression -> 看 report -> 必要时读 JSONL trace_steps
```

Phase 收口：

```text
跑 regression + challenge + diagnostic -> 保留 report 和 trace -> 用 AI 做失败归因审查
```

验证 LangFuse：

```text
只在需要看 Cloud trace / score 时打开 LANGFUSE_ENABLED=true；
遇到网络问题先跑 smoke_phase3b_langfuse.py；
不要把 UI Experiment 是否成功当作当前 DataPilot eval 是否成功的标准。
```
