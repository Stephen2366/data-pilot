# M43 Phase 4B B1 开发记录

> 模块 plan：`docs/notes/m43-plan.md`
>
> 范围：完整交付 B1 的 Task runtime、自然多轮 v1、Evidence invalidation、首批 node Context 和 Agent Scenario v2；不提前实现 M44–M48 的 Decision Loop、RAG Subgraph、durable state 或 Context Compact。

## Implementation checklist

- [x] M43-A：新增 B1 canonical catalog/identity 与 Agent Scenario v2；M42 v1 source/artifact/validator 保持只读。
- [x] M43-B：实现 closed-world TaskDelta、TaskState、字段级 merge、Evidence invalidator、fingerprint 和 typed turn/event。
- [x] M43-C：实现独立 in-memory task boundary，覆盖 owner/version/claim/commit/switch/cancel/clear/TTL 和安全投影。
- [x] M43-D：实现本地 deterministic Turn Understanding、保守澄清与首批 node Context projection。
- [x] M43-E：以嵌套 task envelope 接入同一 `/api/query`，完成 agent turn、一次深 Tool、response/Trace 与 task clear。
- [x] M43-F：实现 Agent Scenario v2 closed-world artifact/rehearsal，完成 canonical、correction、switch/cancel 和非 happy-path Gate。
- [x] 运行聚焦测试、M42 v1/legacy 受影响回归、全仓 deterministic pytest、compileall 与 `git diff --check`。
- [x] 调用 `finish-module` 完成注释审查、notes 素材、Phase 4B changelog、`AI_CONTEXT` 和命中专项 state 收口。

## 开工基线与已确认决策

- G43-1：采用 additive v2；M42 的 `phase4b-b0-contracts-v1`、`phase4b-agent-scenario-v1`、manifest、identity 和首次 artifact 全部只读保留。
- G43-2：采用嵌套 `task` envelope；只有新 agent family 严格拒绝 unknown，legacy 当前解析行为不被全局改成 breaking strictness。
- G43-3：采用本地 deterministic Turn Understanding + 保守澄清；本模块零新增 provider/outbound，除非命中 plan 的重开门并再次取得用户确认。
- M43 只允许每个 task turn 至多一次现有安全深 Harness/Tool；Observation-driven 多动作、父子预算和新 Hybrid runtime 属于 M44/B2。
- M46 reserve 保持 sealed；不运行真实 LLM/embedding/RAG Eval，不修改默认模型、active Knowledge release、retrieval、Composer、数据库 schema 或 legacy seed。

## 开发过程记录

### 2026-08-23：启动

- 已完整读取 `finish-module` skill、`AGENTS.md`、`docs/state/runbook.md`、`docs/state/AI_CONTEXT.md` 和 M43 plan。
- 起始 commit：`8ae217c8904dfe808c32b346028bff251bbf2f7d`。启动时工作树在创建 notes 前为 clean；M43 plan 与已确认 G43-1～G43-3 已进入该 commit。
- 初步 State impact：API/runbook、Eval contract/`eval-baselines`、数据库/SQL oracle 命中；RAG 只继承 Evidence/ACL 边界，是否需要更新在 finish-module 按最终 diff 复核；Schema Retrieval/Milvus/embedding 未命中。
- 首次 pytest 在 Windows sandbox 清理 `basetemp` 时触发 `WinError 5`，与代码断言无关；按 runbook 获批后在沙箱外重跑，同一 M42 聚焦回归 5 项通过。
- 首轮 M43 聚焦测试 9 项中 6 通过、3 失败。两个真实问题均已定位：确定性理解只识别带年份月份，漏掉 canonical T2 的“8 月/7 月”上下文省略；task clarification 误先构造了 M36 `clarify` RouteDecision，却没有 M36 表单 spec。修正仍在 plan 内：年份只从已确认 TaskState 继承；task pending questions 用 task 自身投影，Harness 兼容结果保持零 Graph。
- 最终代码审查发现 switch 若直接在 previous state 上 merge，会把旧约束/requirement/Evidence 串入新 task，虽能跑通 canonical 同指标题，却违反独立切换合同。已改为 manager 同锁原子退休旧 task + 创建 generation=1 新 task；旧 Evidence 标 `task_switched` invalidated，新 task 不继承。cancel/clear 同样显式使 active Evidence 失效。
- node Context 经复核改为真实阶段输入：Turn Understanding 指向 prior state identity；route/SQL 使用执行前 TaskState fingerprint；controller 才看到本轮新 EvidenceRef。Trace runtime 外层为 `phase4b-agent-task-runtime-v1`，内嵌既有深 Harness identity，避免 task family 被误标成 legacy thread runtime。
- 新增 B1 contract `383fbf51016c1baf525657552eb14dbb507edce5ba1d566c1557d3ac6f7e9d32`；deterministic Scenario v2 artifact `cc9f6968ba57da8ce3ffc570a2f305291caf34f0134135022b5895fbf9b27c92`。rehearsal 8/8 checks passed，external calls=0；冻结 oracle 仍为 July 120000、August 180000、delta 60000、rate 0.5。
- 验证快照：M43 聚焦 `13 passed, 1 warning`；M35–M43 受影响回归 `117 passed, 1 warning in 109.43s`；compileall 与 `git diff --check` 通过。后台全仓结果已按 exit/done/log 三方检查：exit `0`，done `2026-08-23T22:25:18.9238549+08:00`，日志结论 `500 passed, 3 skipped, 1 warning in 584.22s`。warning 均为既有 Starlette TestClient/httpx deprecation。

## 关键决策与取舍

- 当前无未决选择；G43-1～G43-3 的选项、风险、建议与用户最终选择以 plan 第 7 节为准，实施不得自行重开。

## 参考资料

- plan 调查已沿 ARAG `graph_state.py / graph.py / nodes.py` 的真实 turn→state→clarification 通路，以及 DataAgent `DataAgentConfiguration.nl2sqlGraph` 的 KeyStrategy/固定 Graph 接线定点复核。借鉴显式 state merge seam 和主任务/执行状态分权；不照搬 `MessagesState` 全历史、LLM 自由 rewrite/summary、扁平大 state 或 `InMemorySaver` 冒充 durable。

## Handoff

- checkpoint（全仓后台验证前）：实现、聚焦测试、受影响回归、rehearsal、代码/注释复核、runbook 与 eval 账本更新已完成。未发现需要改变 plan、默认行为、安全边界或后续路线的新选择。
- 待完成：启动并检查全仓 pytest；依据最终结果补 Phase 4B changelog、`AI_CONTEXT`、最终验证快照与 checklist。M42 v1、legacy 请求默认、模型/embedding/RAG release/数据库 schema 均未改。
- 全仓后台验证已启动（当前状态：**运行中，待检查，不得提前记为通过**）：PID `30436`；wrapper `.agent_work/temp/run_m43_full_pytest.ps1`；pytest basetemp `.agent_work/temp/m43-full-pytest-approved`；日志 `.agent_work/temp/m43-full-pytest.log`；退出码 `.agent_work/temp/m43-full-pytest.exit`；完成标记 `.agent_work/temp/m43-full-pytest.done`。检查时必须同时读取 exit、done 与日志尾部，不能只看 PID 消失。

### 最终 Handoff

- M43/B1 技术开发与 finish-module 已完成。入口是同一 `/api/query` 的 nested task envelope；核心事实源为 B1 contract `383fbf5...e9d32`、TaskState/transition、task Trace 与 Scenario v2 artifact `cc9f696...b27c92`。
- 默认与兼容边界：无 task 信封时 legacy 行为不变；M42 v1 不改签；task boundary 明确 non-durable；未运行真实 LLM/RAG/embedding/reserve，未改变模型、RAG release、数据库 schema 或 seed 默认。
- 风险与遗留：当前只有 B1 单次深执行，没有 Observation-driven Loop、恢复策略、RAG Subgraph、durable state 或 Context Compact。下一步只能从 M44/B2 独立 plan 开始；M46 reserve 继续 sealed。
- 最终验证：M43 `13 passed`；M35–M43 `117 passed`；rehearsal 8/8、external calls=0；全仓 `500 passed, 3 skipped, 1 warning`；compileall/diff check 通过。

## State impact

- `runbook.md`：新增 nested task envelope、task clear、进程内非 durable 边界和 rehearsal 命令。
- `eval-baselines.md`：登记 Scenario v2 deterministic artifact 的身份和“非质量基线”边界。
- `database-current-state.md`：未修改；M43 只消费 M42 已登记的 7/8 月 oracle，没有新 schema/seed/SQL 口径。
- `rag-current-state.md`：未修改；没有运行 RAG、改变 release/retrieval/Composer/ACL 或形成新 RAG 事实。
- Schema Retrieval/Milvus/embedding state：未命中；没有任何配置、collection 或出站变化。

## finish-module 技术档案交付清单

- [x] 完成最终代码与注释审查，并修正 switch 状态串线、cancel/clear Evidence validity、真实 node Context fingerprint 和 task runtime identity。
- [x] 聚焦测试、受影响回归、deterministic rehearsal、compileall、diff check 与后台全仓 pytest 均已检查并记录真实结果。
- [x] notes 包含模块范围、用户决策、关键修正、验证证据、安全/兼容边界、风险、遗留和最终 Handoff。
- [x] 已先读 `CHANGELOG_INDEX.md`，再将结构化 M43 模块档案写入当前 Phase 4B 历史文件。
- [x] 已更新 `AI_CONTEXT.md` 当前模块、默认运行事实、最新验证与路线边界。
- [x] 已更新命中的 `runbook.md` 与 `eval-baselines.md`；数据库/RAG/Schema Retrieval 状态经影响扫描确认无需改动。
- [x] 已完整回读本清单相关技术事实；未把 B1、deterministic artifact 或 non-durable boundary 夸大为完整 Agent、质量基线或 B5。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有 5 条一级编号。
- [x] 每个编号点交代原问题/影响、通俗概念、解决方式、取舍、验证证据和未证明边界；长内容已拆成短段与 bullets。
- [x] 英文/代码术语首次出现时有就地解释；测试、oracle 和 invocation 对照数字使用表格或列表。
- [x] “新概念”和“代码阅读路线”按真实 HTTP→task turn→boundary/runtime→Harness→Trace/Eval 调用链解释职责与协作关系。
- [x] 有“设计要点”，末句按 skill 要求以“汪。”结尾。
- [x] 面试亮点围绕状态增量、Evidence validity、原子边界、Context fingerprint 和兼容合同，可独立讲述且未强行凑数。
- [x] 5 个追问围绕真实理解流程、存储取舍、崩溃边界、同源事实和“是否算 Agent”的压力问题展开；压力回答以“喵。”结尾。
- [x] “验证与下一步”只引用 notes 已记录的 13/117/8/8/500 快照；命令标明不调用真实 LLM、不访问 reserve，并说明环境前置。
- [x] 可交互模块提供 uvicorn + Swagger 的 start/continue 体验流程，并明确 Phase 4B profile/模型前置和不可固定照抄 version。
- [x] 各小节使用适量加粗关键词，便于扫读，没有整段加粗。
- [x] 已完整回读 M43 新增章节；自检补写了 API、SQL、canonical、switch/cancel、Tool、Context、artifact、pytest 等首次术语解释。
- [x] finish-docs 阶段只修改 `docs/dev-log.md` 与 `docs/notes/m43-notes.md`；AI_CONTEXT/changelog/runbook/eval 差异均来自此前已完成的 finish-module，本阶段未再修改。
- [x] `git diff --check` 通过；仅显示既有 LF→CRLF 提示，无 whitespace error，Track A 交付门全部闭合。
