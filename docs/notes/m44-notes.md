# M44 Phase 4B B2 开发素材

> 本文是 M44 实施过程的事实记录。关键决策、踩坑、取舍和验证结果在发生时立即追加；最终技术收工由 `finish-module` 基于本文整理。

## Implementation checklist

- [x] M44-A：新增 additive B2 contract/identity、TaskState v2 与 closed-world Knowledge Runtime Resolver。
- [x] M44-B：实现 typed Requirement/Action/Budget/Consumption/EvidenceDelta/Progress/Termination 深合同。
- [x] M44-C：实现唯一 `run_agent_loop(...)` interface、确定性回边、实际 node Context 和稳定停止。
- [x] M44-D：实现 T3 Observation 驱动的原因→商品 SQL 动作链，以及 allowlisted 单次 SQL dialect repair。
- [x] M44-E：实现 T4 SQL→business Document Hybrid 与 T5 correction/invalidation/reauthorization。
- [x] M44-F：实现安全 Response/Trace 投影、Agent Scenario v3 和零 provider rehearsal。
- [x] M44-G：完成聚焦、前序兼容、legacy 与全仓 deterministic 验证，更新运行说明并技术收工。

## 已冻结实施边界

- G44-1～G44-4 均按用户确认的方案 A：服务端 runtime resolver、确定性 Controller、三次 Evidence action 父预算、独立最小 `sql_repair` purpose。
- M44 只完成 B2 顶层 Loop；不准入 B3 recovery action，不实现 B4 RAG Subgraph，不触碰 sealed reserve。
- 普通非 task RAG 保持 M44A Enterprise semantic 默认；task Document requirement 只能由服务端 typed scope 选择 business/external runtime。
- 本轮不自动运行真实 provider、RAG Eval、held-out/all 或 sealed reserve；设计确认不等于运行授权。

## 开工检查（2026-08-24）

- 已完整回读 `AGENTS.md`、`docs/state/runbook.md`、`docs/state/AI_CONTEXT.md` 和 `docs/notes/m44-plan.md` 至 EOF。
- 已读取 `codebase-design` skill：外部 seam 保持一个 `run_agent_loop` interface，复杂 Action/预算/进展/停止逻辑收进深 module；生产与 fake adapter 共用同一 seam。
- 工作区已有用户文档修改：`docs/state/AI_CONTEXT.md` 与未跟踪的 `docs/notes/m44-plan.md`；实施时保留且不覆盖。

## 过程记录

### 2026-08-24：开始实施

- 当前阶段：M44-A 调查与 contract/schema 设计。
- 待补读：Phase 4B roadmap/reference、Text2SQL/RAG 专项 runbook 与状态、Eval 基线、Phase 4B 历史索引和当前代码/测试。

### 2026-08-24：M44-A/B 首批合同落点

- 新增 B2 additive contract/manifest，content identity `a808b321...d485b`，predecessor 精确绑定 M43 B1 `383fbf51...e9d32`；Action、termination、双 knowledge scope 和 G44-3 方案 A exact budget 均 closed-world。
- 新增 `loop_contracts` 纯 typed 事实：EvidenceRequirement、BudgetProfile/Ledger、ResourceConsumption、EvidenceDelta、ProgressDecision、ActionAttempt、TerminationFact。Controller 后续只消费这些 interface，不逐个解析 SQL/RAG 私有实现。
- 新增 `knowledge_runtime` seam：registry 只接受 `business_release/external_profile`，resolver 只读取服务端 requirement scope；factory 异常或 scope 缺失直接 unavailable，不 fallback。
- 设计取舍：TaskState v2 将保留旧 `requirements` 字符串投影用于 M43 兼容，同时新增 typed `evidence_requirements` 作为 M44 authority；不改写 M42 v1/M43 v2 artifact。

### 2026-08-24：M44-C/D Loop 与 repair seam

- 独立 LangGraph Decision Loop 已落盘并通过语法编译；一次节点只执行一个 Evidence action，回边前由 typed requirement、依赖事实、duplicate key 与父预算重新裁决。
- SQL repair 新增独立 `sql_repair` outbound purpose；只接受稳定 issue code `mysql_unsupported_date_trunc` 和 candidate SQL，不传 raw DB error、rows 或 stack。repair 重新经过 QueryPlan validation、SQL fidelity、Guard、执行和 Evidence 构造。
- 真实 OpenAI-compatible client 的 token/request counter 以单次调用 delta 写入 Trace；没有 counter 的 fake 明确为 `observed=false`，避免把未知 token 当作 0。
- 阶段验证：相关模块 `py_compile` 通过；M31 governance + M25 Eval trustworthiness 共 22 tests passed。

### 2026-08-24：M44-E/F 纵向路径、同源投影与 v3

- task envelope 已改接独立 B2 Loop；legacy 非 task Harness 拓扑不变。API、JSONL Trace 与 Agent Scenario v3 均从同一 `TaskTurnResult/AgentLoopResult` 投影 action、budget、EvidenceDelta、progress、termination 和 runtime identity。
- T3 踩坑 1：原 period parser 对“2026 年 7 月和 8 月”只识别 7 月；现改为同句后续月份继承最近显式年份，并补齐“净退款增长”到已冻结指标。
- T3 踩坑 2：跨 turn 初始 coverage 原先忽略 TaskState 中 active Evidence，会重复执行 T2 的旧 requirement；现只把 active Evidence 所属旧 requirement 视为已覆盖，T3 当前 run 仍按 reason Observation 决定 product action。
- Budget 踩坑：最初把 SQL ledger stage 误计入 RAG candidate/selected/context 配额，导致 T4 文档动作执行前被阻断；现这些维度只由 RAG Observation 消费。Tool 实际超额时保留已发生 action/consumption 后立即 `budget_exhausted`，不从审计账本抹掉调用。
- Partial 踩坑：只找到 quality 政策时已有 EvidenceDelta，但 required basic key 未闭合；现明确 `budget_exhausted/required_coverage_incomplete`，且不重复同一 Knowledge query。
- 安全投影：Action Observation 与顶层 task Trace 去除 raw DB error/technical message、rows、正文、Prompt、stack、Thought；Document typed payload 只在同进程 Gate/Synthesizer 私有边界。
- Agent Scenario v3 对 run/contract/seed/caller/knowledge/policy identity、turn/action 顺序、duplicate key、EvidenceDelta、逐步 budget 守恒、termination、三态 assertion 与 private payload 做 closed-world 校验；M42 v1/M43 v2 validator 未改。
- 零 provider rehearsal：`python -m scripts.rehearse_m44_b2` 通过，external calls=0；Context v2 固化后的最终 artifact 为 `63c9483c8d55b958b48925085d99c9bb14164c1120a7d364c0b1c611dabac700`，T3/T4/T5、repair once、negative skip 共 6 checks passed。
- 聚焦验证：M44 + M43 task + v1/v2 artifact compatibility 共 34 tests passed；随后扩展聚焦集共 34 tests passed（最终完整矩阵见收工记录）。

## 模块名称与改动文件清单

- 模块：M44 / Phase 4B B2 顶层 Evidence-driven Bounded Decision Loop。
- 起始 commit：本轮没有单独创建或记录 module base commit；范围以开工时工作区事实、当前 `git status --short`、`git diff --name-only` 与未跟踪文件归并。开工前已有用户确认的 `docs/notes/m44-plan.md` 和 `AI_CONTEXT.md` 防遗忘账本修改，均保留并纳入 M44 文档范围。
- 组装/API/Trace：`AGENTS.md`、`app/api/query.py`、`app/main.py`、`app/schemas/agent.py`、`engine/trace/recorder.py`。
- B2/Task runtime：`engine/phase4b/{b2_contracts,loop_contracts,knowledge_runtime,agent_loop,task_runtime,task_turn}.py`、`domain_pack/phase4b/b2_contracts{,.manifest}.json`。
- Text2SQL/既有 Harness：`engine/governance.py`、`engine/harness/{adapters,contracts}.py`、`engine/nl2sql/{generator,llm_call,pipeline}.py`。
- Eval/rehearsal/tests：`eval/agent_scenario_v3_contracts.py`、`eval/reports/m44/*`、`scripts/rehearse_m44_b2.py`、`tests/test_m44_{b2_contracts,agent_loop,agent_scenario_v3,api_trace}.py`。
- 文档/状态：`docs/notes/m44-{plan,notes}.md`、`docs/state/{runbook,AI_CONTEXT,eval-baselines,rag-current-state}.md`、`docs/state/change-history/phase4b.md`。

## 关键决策与取舍

- G44-1：用户选 A。普通 API 保持 M44A Enterprise semantic；task requirement 由服务端 closed-world resolver 在 business/external 中选择。风险是双 runtime identity/ACL 必须闭合；缺失时失败关闭，不 fallback。
- G44-2：用户选 A。首版 next Action 完全确定性，decision model calls/tokens=0。未选的结构化模型 proposal 方案 B 已按用户要求写入 `AI_CONTEXT` 防遗忘账本，只有稳定 paraphrase 失败簇和重新授权才能重开。
- G44-3：用户选 A。最多 3 Evidence actions / 3 deep Tools、1 Knowledge action、每 requirement 1 repair、6 model calls、24000 observed tokens。风险是复杂链保守停止；不为尚不存在的动作扩大预算。
- G44-4：用户选 A。新增独立最小 `sql_repair` outbound purpose；prompt 仅含当前 question、MySQL、稳定 issue code、safe candidate SQL 和输出格式，不外发 Schema/metric/join、raw DB error、rows 或 stack。repair 仍重走 QueryPlan validation、SQL fidelity、Guard 和执行。
- 深 module 取舍：外部仍只有一次 task turn / 一次 `run_agent_loop` invoke；Controller、Action、Budget、Progress 与 termination 收进内部。借鉴参考项目的 conditional edge/dispatcher/去重思想，不照搬 LLM 自由 tool call、字符串 Observation、平台级 PlanExecutor 或框架 recursion limit 预算。

## 阶段 1 注释小结

- 完整审查 18 个本模块 Python 代码文件，共扫描 285 个 class/function 符号；AST 初检列出 34 个无 docstring 的 public 名称，补写 12 处后剩 22 处，均为简单 `safe_projection`/property、Protocol method、局部 lifespan closure 或本轮未改的既有简单治理方法，符合豁免条件。
- 深化内容：确定性 Controller 为什么独占 next action、token usage 为什么区分 observed/unknown、实际消费超额为什么仍保留账本、SQL repair 为什么不携带 Schema/raw error、Context v2 为什么同时冻结 allowlist/field/token budget。
- 修正过时注释：task turn 从“固定一次 Harness”改为“一次 agent Loop”；clarification/cancel 只投影实际执行的 understanding/controller Context，不再预生成 route/SQL Context。
- 仍缺失：无非豁免缺失；未为简单投影函数机械堆叠注释。

## 阶段 2 验证快照（后台全仓前 checkpoint）

- `py_compile` / `compileall -q`：B2、Text2SQL repair、API/Trace、Eval/rehearsal 模块通过；无语法错误。
- `pytest ... test_m31_governance.py test_m25_eval_trustworthiness.py -q`：22 passed，验证新增 outbound rule 未放宽既有 exact-match deny。
- 多轮 M44 聚焦修复后，代码冻结命令覆盖 M44 合同/Loop/v3/API、M42 v1、M43 v2/task、M44A API、M31 governance、M35 SQL adapter：57 passed，1 个既有 Starlette `httpx` deprecation warning；warning 不影响本模块。
- `python -m scripts.rehearse_m44_b2`：passed=true、6/6 checks、external_calls=0，artifact `63c9483...ac700`。
- `git diff --check` 与 `compileall -q` 在代码冻结点通过；技术档案写入后已再次通过，路径存在性检查也全部为 true。
- 一次扩大 Text2SQL/Phase 回归前台运行耗时超出预期，因工具未返回完整 exit/summary而不计为验证通过；为严格避免无法证明的 provider 边界，曾预防性停止其中一条 pytest 进程。随后定点检查测试源码确认相关用例使用 fake client，没有证据表明发生真实 provider 调用。最终完整回归将按 AGENTS 后台规则记录日志/exit/done。

## 参考资料

- `docs/phase4-reference.md` 与 roadmap reference 要求；定点复核 ARAG `graph.py/edges.py/graph_state.py/nodes.py` 的 conditional edge、计数与去重，DataAgent `DataAgentConfiguration.java/PlanExecutorDispatcher` 的显式 dispatcher/repair 回边，以及 LangGraph Graph API 的 `Runtime` context、conditional edge、recursion limit。
- 借鉴：typed state 驱动回边、固定 dispatcher、执行 key 去重、实际 Context 留痕。
- 不照搬：LLM 自由 action/tool call、字符串 Tool output、压缩/fallback answer、Java 平台大状态、人审/Python executor、把 recursion limit 当业务预算。

## Handoff

### 已完成且可依赖

- B2 contract identity `a808b321...d485b`、TaskState v2、typed requirement/action/budget/progress/termination、Knowledge Runtime Resolver 和独立 agent-family LangGraph Loop。
- T3 reason Observation→product action、T4 business SQL→Document Hybrid、T5 correction/invalidation/reauthorization、allowlisted DATE_TRUNC repair once，以及 no-progress/budget/unsafe/unavailable/unrecoverable/contract failure 停止语义。
- API/Trace/v3 同源安全投影、actual-node Context v2、零 provider v3 rehearsal；M42 v1/M43 v2 validator 与 legacy Harness 未改写。

### 未完成与风险

- M44 未实现 B3 recovery action admission、B4 RAG Subgraph、B5 durable state 或 B6 Compact；不能宣称 Agentic RAG/B4/Phase 4B 完成。
- 未运行真实 SQL repair showcase、真实 RAG Eval、held-out/all 或 sealed reserve；deterministic fake/fixture 证明控制合同，不证明真实模型或 36,417 文档质量。
- 业务首次检索漏 basic 的真实失败仍保留；B2 只会正确 partial/budget stop，不做 rewrite/parent expansion。

### 必须延续的边界与决策门

- G44-1～G44-4 方案 A 与 M46 reserve sealed 继续生效；任何模型 decision proposal、父预算放宽、新 repair 字段/用途、runtime fallback 或真实 provider 运行都需满足 plan 重开门并重新取得对应授权。
- 普通非 task Enterprise semantic 与 task business/external resolver 必须继续分账；不能用自然语言、请求字段或“开发方便”选择 corpus/backend。

### 下一模块入口与必读指针

- 下一模块建议 M45/B3 从 `engine/phase4b/agent_loop.py` 的 document Observation/termination、`engine/phase4b/loop_contracts.py` 的 parent budget/EvidenceDelta，以及 M42 business 漏选与 M44A external semantic retrieval failures 开始。
- 必读：`docs/phase4b-roadmap.md` B3、`docs/phase4-reference.md` action-level Evidence/review point、`docs/state/{AI_CONTEXT,rag-current-state,eval-baselines}.md`、M44 plan/notes 与 `eval/reports/m44/`。M45 只诊断并准入 action card，不提前实现 B4 子图。

## State impact（阶段 4 最终）

- 已更新：`docs/state/runbook.md`（B2 task/repair/rehearsal/Trace 入口）、`AI_CONTEXT.md`（当前模块、默认 Loop/runtime、验证、路线与活跃坑）、索引指定的 Phase 4B changelog、`eval-baselines.md`（v3 deterministic artifact，不登记质量基线）、`rag-current-state.md`（task resolver 与普通 Enterprise 默认分账）。
- 已完整复核且无需修改：`database-current-state.md`（只消费既有 Phase 4B oracle，未改 schema/seed/指标）；已检查且未命中：`schema-retrieval-milvus-embedding.md`（未改 embedding/Milvus/Schema Retrieval 默认）。

## 后台完整回归启动前 checkpoint

- 关键决策与代码范围：已冻结，见上文；没有待用户确认的合同变化。
- 已完成验证：最终聚焦 57 passed；rehearsal 6/6、external calls=0；compile/diff 静态检查已阶段通过。
- 已知风险：完整回归预计超过 2 分钟；尚未获得带 exit code 的最终全仓结果，M44-G 和 finish-module 均不得标完成。
- 待完成：按后台规则运行全仓 deterministic pytest，检查 log/exit/done；随后完成 state/changelog 更新、完整回读、最终 diff/link 检查。

### 后台任务指针

- 状态：已结束并复核通过。
- 命令脚本：`.agent_work/temp/run_m44_full_pytest.ps1`。
- PID：`63628`。
- pytest 日志：`.agent_work/temp/m44-full-pytest.log`。
- 退出码：`.agent_work/temp/m44-full-pytest.exit`（任务结束后生成）。
- 完成标记：`.agent_work/temp/m44-full-pytest.done`（任务结束后生成）。
- 检查方法：确认 done/exit 均存在且 exit 为 `0`，再读取日志末尾的 passed/skipped/warning 摘要；失败时先定位失败用例，不直接重跑全仓。

### 后台完整回归结果（2026-08-24）

- done：`2026-08-24T04:44:28.5699683+08:00`；exit：`0`。
- 结果：`539 passed, 1 warning in 599.47s (0:09:59)`；warning 为既有 Starlette TestClient/httpx deprecation，不阻塞 M44。
- 本结果覆盖 legacy、M42/M43/M44A、M44 B2 与既有 Phase 3/4 回归；未触发真实 provider、RAG Eval、held-out 或 sealed reserve。

## finish-module 技术档案交付清单

- [x] 注释审查与豁免说明已记录。
- [x] 聚焦、兼容、rehearsal、全仓验证证据已记录。
- [x] `CHANGELOG_INDEX.md` 已先读，M44 模块档案已写入其指定的 Phase 4B 历史文件。
- [x] `AI_CONTEXT.md`、`eval-baselines.md`、`rag-current-state.md` 已同步；数据库专项状态已复核为无需修改。
- [x] M44 最终能力边界、遗留项、下一模块入口和必读指针已写入 Handoff。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代原问题/影响、概念解释、解决方式、取舍、验证证据和未证明边界中的适用项。
- [x] 每个编号点用独立结论句和短段或 `- **小标题**：` 拆分，没有无断点大段。
- [x] 正文英文/代码术语首次出现时有括号或就地解释。
- [x] 需要对照的数字使用列表或表格呈现。
- [x] 新概念已用通俗语言解释，没有强行编造。
- [x] “代码阅读路线”按真实调用或数据流组织，并解释为什么这样协作。
- [x] 有“设计要点”。
- [x] “有面试价值的亮点”可背、可独立展开且没有强行凑数。
- [x] 追问优先围绕亮点，包含真实工程压力且没有低价值问题。
- [x] “验证与下一步”只引用 notes 的真实验证快照。
- [x] 复制命令安全、可重复并标明前置条件。
- [x] 各小节使用适量加粗帮助扫读，没有整段加粗。
- [x] 已完整回读 M44 新增章节，并以第一次阅读者视角复核可读性。
- [x] 本阶段只修改 `docs/dev-log.md` 和 `docs/notes/m44-notes.md`，未改技术档案或代码。
- [x] `git diff --check` 通过。

### finish-docs 检查结果

- Track A 模块记录交付门全部通过；新增章节为 `★ M44 Phase 4B B2：让 Agent 根据证据连续行动，但始终有预算和刹车`。
- 第一次完整回读后补写了两类缺口：给 API/RAG/Harness 等首次出现术语增加就地解释；为多动作、预算、runtime resolver 和 SQL repair 四个核心编号补上对应验证锚点。
- 数字只取自本 notes 和已完成技术档案：57 passed、rehearsal 6/6 且 external calls=0、全仓 539 passed / 1 warning / 599.47 秒；没有在 finish-docs 阶段新跑模块验证。
- finish-docs 阶段只编辑 `docs/dev-log.md` 与本 notes；`AI_CONTEXT.md` 和 Phase 4B changelog 的现有修改均来自先行完成的 finish-module，没有在本阶段继续改写。
