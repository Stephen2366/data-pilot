# M43 Phase 4B B1 Task Runtime、自然多轮 v1 与 node-level Context 开发计划

> 能力里程碑：Phase 4B B1；本模块完整承担 B1，不提前实现 B2 的同次运行 Decision Loop、B4 的 RAG Subgraph、B5 的 durable adapter 或 B6 的 Context Compact
>
> 主要问题：当前统一 turn seam 只能承载单轮、一次 clarification 或一次签名 follow-up，尚不能把连续自然语言 turn 受控合并为可评测的 TaskState，也不能证明条件修改后旧 Evidence 正确失效并重新取证

## 1. 模块定义与范围判断

用户已冻结“B0–B6 各对应一个模块和一份 module plan”，因此 M43 完整对应 B1，并在模块内部按 M43-A～M43-F 形成纵向闭环，不再拆出额外模块。

M43 完成后，用户能够从同一 `/api/query` 明确选择新的 agent task 请求：先自然语言查询 2026 年 7 月实际净退款金额，再说“改成 8 月，并与 7 月同口径比较”。系统会把第二句话理解成受控 TaskDelta，更新 TaskState，使不再适用的旧 SQL Evidence 失效，重新执行一次现有 Text2SQL 深 Tool，并在响应、Trace 和 Agent Scenario Eval 中回查状态前后、字段变化、Evidence validity、节点实际 Context 和任务版本。

模块还必须用独立 Scenario 证明 correction、switch 和 cancel：correction 不能靠预写北极星整句或退款专用状态字段；switch/cancel 不继承旧 pending question、Evidence 或执行权。自然语言不确定时保守澄清，不能自由猜测 TaskDelta。

本计划按用户已确认的冲突处理方案 A 推进：M42 的 `phase4b-b0-contracts-v1`、`phase4b-agent-scenario-v1`、manifest、identity 和首次 artifact 全部只读保留；M43 新增 B1 canonical sequence 与 Agent Scenario v2，后续 M44–M48 消费新版本。禁止原位改签 M42 artifact，也禁止用 sidecar 拼接掩盖 v1 缺少 typed TaskDelta/State/Context 的事实。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| legacy `/api/query` 只识别 initial、clarification resume 和一次 follow-up，三类请求由扁平 thread 字段组合判断 | 新 task continuation 若继续靠字段是否为空猜 family，容易与旧 resume/follow-up 混用或误路由 | `app/schemas/agent.py::QueryRequest`、`engine/harness/turn.py::TurnRequest/run_turn` |
| `AgentTurnResult` 冻结 legacy accepted turn 恰好一次 Graph、lifecycle rejection 零次 Graph | B1 需要区分 task-boundary invoke 与深 Harness invoke；澄清/cancel 可以零深 Tool，但不能改写旧 family 的计数语义 | `engine/harness/turn.py::AgentTurnResult`、M35–M37 tests |
| `m37-thread-v2` 只保存一次 clarification/follow-up 卡，状态、字段和生命周期都围绕旧模板设计 | 扩字段会把 legacy checkpoint 伪装成 TaskState，并破坏旧 owner/version/budget 合同 | `engine/harness/thread.py::PendingThreadCheckpoint/ThreadCheckpointManager` |
| 当前 Graph 是固定 `route → Tool/branches → controller`，普通 SQL/RAG 各至多一次深 Tool | B1 可复用一次深 Tool 完成纵向 slice，但不能宣称已经有 Observation-driven 多动作 Loop | `engine/harness/graph.py::build_harness/run_harness`、`docs/state/AI_CONTEXT.md` |
| API、Trace 和 Eval 已从同一 `AgentTurnResult` 投影；Trace 不保存 raw thread 参数、完整 rows/正文或模型 Thought | 新 TaskState/Context 必须继续从同一 turn fact 安全投影，不能另跑 pipeline 补评分证据 | `app/api/query.py::_project_response/_record_trace`、`engine/trace/recorder.py::TraceRecord` |
| M42 已冻结 agent runtime identity、最小 `ops + customer_service` caller、Phase 4B seed/oracle 与 7/8 月真实 SQL 事实 | M43 应直接消费这些输入，不能重定义角色、seed、指标口径或新 Hybrid operator | `domain_pack/phase4b/b0_contracts.json`、`docs/notes/m42-notes.md` |
| roadmap 的 B1 canonical prefix 是“7 月初始查询 → 改为 8 月并比较”，但 M42 v1 catalog 的 T1 已比较 7/8 月、T2 改为原因拆分 | 直接消费 v1 T1→T2 无法证明时间条件修改使旧 SQL Evidence 失效 | `docs/phase4b-roadmap.md` §5.1/§8、`domain_pack/phase4b/b0_contracts.json` |
| `phase4b-agent-scenario-v1` 的 turn 只有 execution status、Evidence kind/ref 和 assertion status，closed-world validator 拒绝额外字段 | B1 required Gate 无法直接读取 TaskDelta、State transition、Evidence validity 和 node Context | `eval/agent_scenario_contracts.py::TurnExecutionEvidence/validate_completed_artifact` |
| Pydantic 当前没有统一 `extra=forbid`，未知字段是否被忽略不是既有兼容保证 | 新 task payload 必须显式冻结 unknown-field 策略，同时避免把 legacy 未声明行为误写成保证 | `app/schemas/agent.py::QueryRequest`、roadmap §4.7 |
| SQL Evidence 没有可靠业务 snapshot，任务条件、指标、维度或 route 改变后必须重新查询 | TaskDelta merge 不能因为持有旧 EvidenceRef 就复用旧结果 | `docs/state/AI_CONTEXT.md`、`docs/state/database-current-state.md`、roadmap §4.2 |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 如何让自然语言 turn 先进入明确状态，再决定继续、澄清或执行 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::State/AgentState/accumulate_or_reset/append_unique`；`graph.py::create_agent_graph`；`nodes.py::summarize_history/rewrite_query/request_clarification` | 主任务状态与检索子状态分离；字段 reducer 显式声明；rewrite 后通过 conditional edge 进入 clarification 或执行 | DataPilot 把入口拆为 adapter-neutral TaskDelta、受控 merge/invalidator 和独立 TaskState family；不确定结果在 task boundary 澄清，下一 turn 从 State 重进 | `MessagesState` 全历史、LLM 自由 summary/rewrite、把 `pendingQuery + clarifications` 拼成新权威问题、固定 clarification 循环、默认 `InMemorySaver` 冒充 durable state |
| 如何避免节点自行发明不同的 state 合并方式 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java::nl2sqlGraph` 中 `KeyStrategyFactory` 与固定 `StateGraph` 接线 | 先冻结每个 key 的 replace/merge 语义，再让 node/edge 消费；checkpointer 与 Graph 组装保持 seam | DataPilot 为 TaskDelta 可写字段、TaskState merge、Evidence invalidation 和 node Context allowlist 建立单一 registry/深 interface；B1 只让当前真实消费者读取投影 | 大而平的全图 state、所有 key 一律 `REPLACE`、Java 平台结构、完整 Planner/Python/repair/human-review 编排 |

沿真实 turn 通路复核后的结论：ARAG 会把消息历史/摘要、pending query 和 clarification 文本直接交给 LLM rewrite，随后把 `rewrittenQuestions` 交给子图；它没有字段级 TaskDelta、Evidence validity 或安全 Context 投影。DataAgent 明确列出了 state key strategy，但多数 key 只是平铺替换，也没有证明 owner/tenant、Evidence invalidation 或最小入模。M43 只借鉴“状态合并语义先于 Graph 消费”和“任务状态与执行状态分权”，正向保证由 DataPilot 自身 typed contract、ACL、Trace 和 Scenario Gate 提供。

规模与代表性边界：B1 的关键风险是多 turn 语义、权限和状态漂移，不是大 corpus 召回质量；因此本模块使用 Phase 4B 确定性 SQL profile、非退款 correction/switch/cancel 和 payload/security 反例证明接口泛化。22 条 business 与 36,417 文档 external 的质量差异留给 M45/B3、M46/B4，不能用本模块 SQL 场景全绿外推 RAG 能力。

## 4. 目标、优先级与非目标

### 模块完成状态

M43 完成后，项目具备独立 `phase4b-agent-runtime-v1` 的 TaskState/TaskDelta/turn-event 语义、首版进程内 task-boundary adapter、确定性自然语言 Turn Understanding、字段级 merge/Evidence invalidation、首批 node Context projection，以及同一 `/api/query` 上与 legacy payload 互斥的新 task 请求/响应。B1 canonical prefix 和 correction/switch/cancel required Gate 全部从真实 task runtime 事实评分。

### 必须完成

- 以 additive 版本演进冻结 B1 canonical sequence；M42 v1 source/artifact/identity 保持只读。
- 建立 closed-world TaskDelta，至少区分 `start_task`、`continue`、`modify_constraint`、`ask_about_existing_result`、`add_evidence_requirement`、`switch_task`、`correct_previous_understanding`、`cancel`；不允许客户端或模型提交整份 TaskState。
- 建立 adapter-neutral、versioned TaskState、字段级 merge/invalidator、前后 fingerprint 和 typed turn/event ledger；不保存旧完整 answer、SQL rows、Document 正文或模型 Thought。
- 建立独立于 `m37-thread-v2` 的 in-memory task-boundary adapter，覆盖 owner/tenant/active role、TTL、乐观版本、单 claim、commit、switch、cancel、clear 和失败关闭；明确不具备跨进程 durability。
- 让自然语言 T1→T2 连续推进：第二 turn 修改时间条件、使旧 SQL Evidence 失效，并重新执行同口径 SQL；不得直接注入 TaskDelta 冒充自然语言 seam。
- 用独立 paraphrase Scenario 证明 correction，不硬编码退款/月/渠道专用字段；switch/cancel 清空旧 pending/Evidence 并终止旧执行权。
- 从 Turn Understanding、Router/执行适配、SQL 和 Controller/response 本片真实消费者开始建设 node Context；每份投影有 allowlist、来源、identity、预算和实际输入安全记录。
- 在同一 `/api/query` 增量接入新 task payload；冻结 request/response/Trace/Eval compatibility matrix、unknown-field 策略和稳定错误。
- 新建 Agent Scenario v2，使 Eval 能直接读取 TaskDelta、State transition、Evidence validity、Context 和 runtime family；v1 回归继续通过。
- 保持最小双角色 caller、SQL Guard、outbound 默认拒绝、四轴、Evidence/citation 与 API/Trace/Eval 同源。

### 建议完成

- 提供 TaskState/turn ledger/Context 的安全人读 renderer，便于用户逐 turn 验收。
- 提供零 provider 的 B1 deterministic rehearsal，输出 canonical、correction、switch/cancel 和 compatibility 摘要。
- 将 delta merge policy、Evidence invalidation policy 和 Context allowlist 由可枚举 registry 统一呈现，避免散落条件分支。

### 条件触发

- **触发条件**：预注册 deterministic paraphrase/指代/省略集合无法稳定形成唯一 TaskDelta，且失败不是可接受的 clarification，而是阻塞 B1 required natural-turn Gate。
- **允许动作**：进入 G43-3，设计独立结构化模型 Turn Understanding adapter、专用 outbound policy 和一次真实 provider T1→T2 E2E。
- **未触发时**：保持本地 deterministic adapter；不新增模型调用、Prompt、出站许可或真实 provider 验收。

- **触发条件**：实现调查证明新 task payload 无法在不破坏旧字段语义的前提下通过嵌套 envelope 接入。
- **允许动作**：重开 G43-2，提交新的 additive API 版本方案。
- **未触发时**：禁止扁平添加一组可与 legacy thread 字段混用的新字段，也不把整个旧 `QueryRequest` 静默切为严格 unknown-field 拒绝。

### 明确非目标

- 不实现同次运行 Observation→Action→EvidenceDelta 的多动作 Decision Loop、父子预算或多次深 Tool；这些属于 M44/B2。
- 不实现 `refund_change_and_policy` runtime、SQL→Hybrid T4/T5 整合或 Hybrid follow-up；这些属于 M44/B2。
- 不诊断/准入 RAG recovery action，不运行 M42 business failure campaign；这些属于 M45/B3。
- 不实现或默认化 RAG Subgraph，不解封 M46 decision reserve；这些属于 M46/B4。
- 不新增 MySQL/Redis checkpoint schema，不承诺 restart/multi-worker；durable adapter 属于 M47/B5。
- 不实现 Task Compact、LLM summary 或长历史；这些属于 M48/B6。
- 不切换普通 `/api/query` 产品默认到 agent family；无新 task payload 的旧客户端继续进入 legacy family。
- 不修改默认模型、embedding、active Knowledge release、business/external retrieval、Composer、数据库 schema 或 legacy seed。

## 5. 关键合同

### C1：B1 canonical 与 Agent Scenario 版本演进合同

- 输入：用户确认的 additive v2 方案、roadmap canonical sequence、M42 v1 bundle/artifact/identity。
- 成功输出：新的 B1 canonical sequence identity，T1 为 7 月实际净退款，T2 为改到 8 月并与 7 月同口径比较；Agent Scenario v2 能直接承载 B1 typed facts，后续 M44–M48 明确消费新 identity。
- 失败语义：任何调用者混用 v1/v2 catalog、runtime 或 artifact 时以稳定 version/identity mismatch 拒绝；v1 仍可独立加载和验证。
- 必须保持的不变量：不修改、重签或补字段到 M42 v1；sequence 一次执行、turn 顺序和 closed-world assertion 继续成立；路线/state 在实施时同步消除双 canonical。
- 本模块不冻结的实现细节：v2 文件名、loader/validator 的内部复用结构；不能通过 sidecar 拼接规避 schema version。

### C2：TaskDelta 与 TaskState 受控合并合同

- 输入：可信 caller 下的当前自然语言 turn、当前 TaskState 安全投影，以及 Turn Understanding adapter 返回的 closed-world TaskDelta proposal。
- 成功输出：TaskDelta、字段级 change set、TaskState before/after fingerprint、pending question、Evidence validity transition 和确定的 next execution requirement。
- 失败语义：未知类别、非法字段、整份 State 覆盖、互相矛盾的条件、歧义或低置信唯一性时不猜测，返回 clarification/blocked，且不改变已提交 State。
- 必须保持的不变量：TaskState 至少表达 schema/version、task generation/status、owner binding、goal、confirmed/corrected constraints、pending questions、Evidence requirements、route intent、active EvidenceRef/validity 和 termination；不得出现 refund/month/channel 专用顶层字段。
- 本模块不冻结的实现细节：后续 B2 Action/Budget/Progress 的完整 schema；B1 只保留兼容扩展 seam，不预造无消费者字段。

### C3：Evidence validity 与安全 switch/cancel 合同

- 输入：已校验 TaskDelta、当前 active EvidenceRef、requirement/constraint/route identity 和当前 caller/authority facts。
- 成功输出：每条 Evidence 的 `active/invalidated/stale/denied` 状态、稳定 invalidation reason、来源 turn 和新 requirement identity；需要重取证时只把 valid requirement 交给执行层。
- 失败语义：无法证明复用安全时默认失效/重取证；ACL/用途/owner 拒绝时零 Tool 且不泄露旧 Evidence 是否存在。
- 必须保持的不变量：SQL 条件、指标、维度或 route 变化后一律重查；switch 终止旧任务并签发新 task identity，旧 pending/Evidence 不继承；cancel 终止当前任务且零 Graph/Tool；correction 只保留仍可证明有效的事实。
- 本模块不冻结的实现细节：B2 跨 Tool Action、B5 durable 事务实现和业务 snapshot/freshness 新能力。

### C4：Task boundary 与 turn/event ledger 合同

- 输入：task initial 或携带 task id/expected version 的 continue/switch/cancel，请求解析后的 trusted caller。
- 成功输出：通过同一 interface 完成 create、atomic claim、commit、switch、cancel、clear/expire；每个 accepted turn 追加 typed event，版本单调递增。
- 失败语义：missing/wrong owner 保持不可区分；version conflict、duplicate claim、expired、cancelled/cleared、role/tenant drift、incompatible schema 或 commit failure 均稳定拒绝，禁止重复 Tool。
- 必须保持的不变量：独立 `phase4b-task-state-v1` family，不扩展 `m37-thread-v2`；应用持有 manager，endpoint 不直接读写字典；raw task id 只返回合法 owner，Trace/Eval 使用不可逆 safe ref；B1 adapter 明示 in-memory/non-durable。
- 本模块不冻结的实现细节：B5 存储后端、schema migration、数据库 CAS 和跨 worker 实现；B1 的锁只能证明同进程原子语义。

### C5：自然语言理解与 node-level Context 合同

- 输入：当前自然语言 turn，以及按 node purpose 构造的最小 typed Context。
- 成功输出：deterministic TaskDelta proposal 或 clarification；每个实际消费者留下 projection version、allowed fields、source identities、context budget、actual-input fingerprint 和安全投影。
- 失败语义：adapter 不可用、解析不唯一、指代缺 antecedent 或字段不在 allowlist 时不调用深 Tool；模型路径若未获 G43-3/outbound 授权则网络前拒绝。
- 必须保持的不变量：Turn Understanding 不看旧 rows/Document 正文/完整 answer/无限历史；SQL Context 不看文档或完整 ledger；Router/Controller 不获得无关敏感字段；Context Builder 不改变 State authority。
- 本模块不冻结的实现细节：模型/Prompt/token 数值、B2 RAG/Hybrid/Subgraph/Composer Context 和 B6 Compact trigger。

### C6：统一 turn seam、API 与 runtime family 兼容合同

- 输入：legacy 请求，或按 G43-2 冻结的新 task envelope；两类 payload 必须互斥。显式 task clear 只进入独立 lifecycle control seam，不执行业务 Graph。
- 成功输出：旧请求继续进入 `phase4-harness-legacy-v1`；新 task 请求进入 `phase4b-agent-runtime-v1`，响应增量返回 runtime family、task version/status/termination 和安全 TaskDelta 投影；合法 owner 可按 expected version 显式 clear。
- 失败语义：payload family 混用、非法 action、缺 task id/version、client 注入 delta/route/action/Evidence、unknown task field 或 incompatible family 返回稳定 4xx/安全 reason，零 Graph/Tool。
- 必须保持的不变量：同一 `/api/query`；旧字段不删除、不改名，legacy initial/resume/follow-up 行为和 `graph_invocation_count` 断言不变；agent task boundary 与深 Harness invocation 分别计数，不能混算成旧 family 语义。
- 本模块不冻结的实现细节：产品默认何时切 agent family、旧字段删除时间和 B2 同次多动作预算。

### C7：同源 Trace/Eval 与三层证据合同

- 输入：同一 task turn 产生的 TaskDelta、State transition、Context、Harness result、Evidence validity、lifecycle 和 runtime identity。
- 成功输出：API、JSONL Trace 和 Agent Scenario v2 从同一 turn fact 投影；v2 completed artifact 对 selected sequence/turn/execution/assertion、catalog/runtime/seed/caller/policy identity closed-world 校验。
- 失败语义：缺 turn、额外/重复 execution、State fingerprint 不闭合、Context allowlist 漂移、Evidence transition 不一致、identity/hash 篡改或评分侧重跑 pipeline 均拒绝 completed。
- 必须保持的不变量：直接 TaskDelta 测试、deterministic natural-turn seam、真实 provider E2E（仅模型方案）三层分账且互不替代；Trace/artifact 不保存 raw task 参数副本、旧 answer/rows、正文或 Thought。
- 本模块不冻结的实现细节：B2 action/budget assertion、B5 checkpoint assertion 和 B6 Compact assertion 的具体字段。

## 6. 工作切片与执行顺序

### M43-A：版本演进、兼容矩阵与 B1 catalog

- 优先级：必须完成
- 依赖：M42 B0 required 已通过；用户已确认 G43-1 方案 A。
- 实施内容：冻结 B1 canonical sequence、Agent Scenario v2 schema 方向、runtime/API/Trace/Eval compatibility matrix；记录 v1→v2 additive 演进与后续模块消费 identity。
- 关键合同：C1、C6、C7。
- 交付物：B1 catalog/manifest、v1/v2 compatibility view、能力矩阵更新、稳定错误表。
- 验证方式：v1 原 artifact/hash 复验；v2 catalog identity/closed-world 测试；跨版本混用失败。
- 完成门：后续切片只有一个当前 B1 canonical，且无需修改 M42 v1 才能表达 typed facts。

### M43-B：TaskDelta、TaskState merge 与 Evidence invalidator

- 优先级：必须完成
- 依赖：M43-A、Phase 4B seed/metric/Evidence 事实。
- 实施内容：建立 closed-world delta/state/event schema、字段级 merge registry、requirement fingerprint 和 invalidator；实现 start/continue/modify/correction/add requirement/ask existing/switch/cancel 的合同语义。
- 关键合同：C2、C3。
- 交付物：adapter-neutral Task runtime contracts、merge/invalidator、fingerprint 和 direct-delta contract tests。
- 验证方式：表驱动合法/非法 delta；条件/指标/维度/route/correction 失效矩阵；删除一个 merge/invalidator rule 后对应测试必须失败。
- 完成门：任何 State 变化都可解释到具体 delta/change/invalidation reason，客户端不能覆盖整份 State。

### M43-C：进程内 task boundary 与 lifecycle

- 优先级：必须完成
- 依赖：M43-B、trusted caller seam。
- 实施内容：建立独立 in-memory adapter/interface，完成 create/claim/commit/switch/cancel/clear/TTL/version/owner 语义；应用生命周期只注入 interface。
- 关键合同：C3、C4。
- 交付物：task-boundary interface、in-memory adapter、安全 projection/lifecycle fact、并发与过期 fixture。
- 验证方式：同 version 并发只一个 claim；wrong owner/missing 无差别；role/tenant drift、duplicate、TTL、cancel/clear、commit failure 均零重复 Tool。
- 完成门：B1 在单进程内具备与未来 durable adapter 相同的任务边界语义，同时明确重启后不可恢复。

### M43-D：自然语言 Turn Understanding 与首批 Context Builder

- 优先级：必须完成
- 依赖：M43-B/C、已确认的 G43-3 方案 A。
- 实施内容：实现 adapter protocol、本地 deterministic adapter 和保守 clarification；从 Turn Understanding、route/execution、SQL、Controller/response 建立实际 node projection，并记录 actual-input identity。
- 关键合同：C2、C5。
- 交付物：natural-turn adapter、Context registry/builder、安全 context evidence、canonical/paraphrase/指代/省略 fixture。
- 验证方式：自然语言正向、同义改写、缺 antecedent、矛盾条件、未知指标/维度、context 越权与注入反例；测试不得直接提交 TaskDelta。
- 完成门：T1/T2 与独立 correction 都通过自然语言 seam，删除自然 adapter 或 Context allowlist 后对应能力测试失败。

### M43-E：agent turn seam、一次深 Tool 与 API 增量接入

- 优先级：必须完成
- 依赖：M43-A～D、已确认的 G43-2 方案 A。
- 实施内容：在统一应用入口解析 family；agent task turn 先完成 claim/understand/merge/context，再按 B1 单动作边界调用现有安全 Harness/深 Tool 至多一次，commit 后统一投影 response/Trace；澄清/cancel/clear/前置拒绝零深 Tool。
- 关键合同：C3～C7。
- 交付物：agent task turn result、API request/response projection、runtime-specific invocation counters、Trace task facts。
- 验证方式：真实 Phase 4B SQLite profile 跑 T1→T2；旧 EvidenceRef 失效、新 SQL Evidence 签发、金额命中；payload mix/unknown field/role drift/version conflict 零 Graph/Tool；legacy API 回归不变。
- 完成门：T1→T2 在同一 task identity 连续完成，API/Trace/State/Eval 指向同一两次 turn 事实，没有评分侧重跑。

### M43-F：Agent Scenario v2、B1 rehearsal 与全量回归

- 优先级：必须完成
- 依赖：M43-A～E。
- 实施内容：构建 v2 completed artifact/validator/report；覆盖 canonical prefix、correction、switch、cancel、provider deny、payload mix、ACL/Context/invalidator non-happy paths；更新 capability handoff 和技术档案。
- 关键合同：C1～C7。
- 交付物：Agent Scenario v2 deterministic artifact/report、B1 capability matrix、M44/B2 handoff、`docs/notes/m43-notes.md` 和收工时的 state/changelog 更新。
- 验证方式：聚焦合同/API/Scenario → M42 v1 → M35–M41 受影响回归 → 全仓 deterministic pytest；compileall、`git diff --check`；不运行真实 provider。
- 完成门：第 8 节所有 required 通过；M42 v1 与 M43 v2 同时闭合；未把 Loop/durable/Compact 标为 available。

## 7. 决策门

### G43-1：B0 sequence 与 Agent Scenario schema 冲突处理（已确认）

#### 方案 A：additive v2（已确认）

- 做法：M42 v1 只读保留；M43 新增 roadmap 对齐的 B1 canonical 和可承载 typed facts 的 Agent Scenario v2。
- 影响：历史 identity/可比性不变，后续模块得到真实可扩展的任务证据；需要维护 v1/v2 双版本 validator 回归。
- 适用条件：接受显式版本演进，不要求历史 skeleton 原位获得新能力。
- 风险：若 compatibility view 不明确，调用者可能混用两个 catalog；由 C1 closed-world 门控制。

#### 方案 B：保留 v1 canonical，另加旁路 Scenario/sidecar（未选择）

- 做法：不升级主 schema，只额外增加时间修改题和 typed sidecar。
- 影响：改动较少，但形成两个 canonical/两份事实，且 v1 artifact 不能直接读取 B1 typed state。
- 适用条件：只追求局部测试，不要求统一 Agent Eval；不符合当前路线。
- 风险：长期双事实源和评分拼接。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：这是唯一同时保持 M42 不可变和满足 B1 direct typed Eval 的方案。
- 用户确认前允许推进：只读调查和 v2 schema 草案。
- 用户确认前禁止推进：修改 v1 source/manifest/artifact，或固定 sidecar 旁路。
- 需要确认的时点：本计划定稿前；用户已于 2026-08-23 确认。
- 重开决策的条件：实施证明 v2 无法在保持 v1 validator 独立可运行的前提下落地。

### G43-2：新 task API envelope 与 unknown-field 策略（已确认）

#### 方案 A：嵌套 task envelope，仅新 family 严格拒绝 unknown（已确认）

- 做法：保留顶层 `question/user_role/...`；新增单一 `task` envelope，含 `action=start|continue|switch|cancel` 及按 action 要求的 `task_id/expected_version`。显式 hard clear 使用与旧 thread control 对称的 task lifecycle control endpoint，并强制 owner + expected version；它不是第二条业务执行入口。出现 `task` 时，顶层与 envelope 都按新 family allowlist 严格拒绝 unknown；没有 `task` 时保持 legacy 当前解析行为。客户端不能提交 TaskDelta、route、Evidence 或 runtime identity。
- 影响：family 选择明确、旧客户端不被全局 strictness 突然破坏；需要 request pre-validation 和完整 compatibility tests。
- 适用条件：同一端点 additive 演进，且 agent family 仍是显式 opt-in。
- 风险：同一模型存在 family-aware validation，错误实现可能让 task unknown 字段在 Pydantic 丢弃后才被忽略。

#### 方案 B：扁平 task 字段并把整个 QueryRequest 改为 `extra=forbid`

- 做法：顶层新增 task id/version/action 等字段，并让所有请求统一拒绝 unknown。
- 影响：实现表面直接，但组合空间大；旧客户端若曾发送未声明字段会从忽略变成 422。
- 适用条件：愿意把全局 strictness 作为单独 breaking API 变更并审计所有客户端。
- 风险：runtime family 继续靠字段组合猜测，且扩大本模块兼容范围。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：它满足同端点、payload 互斥和新 family fail-closed，同时不把 legacy 未声明行为擅自升级为 breaking guarantee。
- 用户确认前允许推进：内部 TaskState/merge/adapter 与 compatibility test 草案。
- 用户确认前禁止推进：修改公开 QueryRequest/AgentResponse 或锁定稳定错误码。
- 需要确认的时点：M43-A/E 公共 schema 实施前；用户已于 2026-08-23 确认。
- 重开决策的条件：已知客户端或 FastAPI/Pydantic 限制证明 envelope 无法稳定区分 family。

### G43-3：Turn Understanding 首版 adapter（已确认）

#### 方案 A：本地 deterministic + 保守澄清（已确认）

- 做法：从当前 TaskState、指标配置、时间/比较/维度等通用 slot 和 closed-world delta cue 生成 proposal；同义改写进入预注册 fixture，不能唯一解析时澄清。退款只作为 Scenario 数据，不进入 TaskState 顶层 schema。
- 影响：零 provider/outbound，required Gate 稳定；开放表达覆盖有限，但未知输入不会自由猜测。
- 适用条件：能通过 canonical、独立 correction、paraphrase/指代/省略和非退款泛化 Gate。
- 风险：规则可能退化成关键词模板；以删除测试、配置驱动 slot 和多表达 Scenario 控制。

#### 方案 B：结构化模型 adapter + deterministic fallback

- 做法：模型只提出 TaskDelta proposal，Controller 校验 schema/allowlist/权限；另建 receiver/purpose/data class/fields outbound policy，并执行一次获授权的真实 T1→T2 E2E。
- 影响：自然语言覆盖可能更强，但引入 Prompt、provider 不可用、数据出站和真实 E2E 成本；deterministic required Gate 仍不能省略。
- 适用条件：方案 A 在冻结自然语言 Gate 上确实阻塞 B1，而非只是希望“更智能”。
- 风险：把模型输出误当 State authority、静默复用 Text2SQL 出站许可或用 provider 抖动掩盖确定性失败。

#### 建议与确认时点

- 建议：方案 A；只有命中第 4 节条件触发才重开 B。
- 建议理由：roadmap 明确允许首版本地/确定性，B1 的核心是 typed merge、Evidence invalidation 和 Context，不是引入新的模型用途。
- 用户确认前允许推进：方案 A 全部 deterministic 实施与验证。
- 用户确认前禁止推进：任何 Turn Understanding 模型调用、Prompt、出站 policy 或真实 provider 运行。
- 需要确认的时点：本模块开工前；用户已于 2026-08-23 确认方案 A。只有命中重开条件并准备采用 B 时才需再次确认。
- 重开决策的条件：预注册 required natural-turn set 存在无法由澄清接受、且阻塞 B1 完成的稳定失败簇。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 v1/v2 演进 | M42 v1 artifact/hash 回归；v2 catalog/validator 正反例 | v1 原件不变且仍通过；v2 typed schema closed-world；跨版本混用失败 | 必须完成 |
| C2 direct TaskDelta | 表驱动 direct delta/merge tests | 所有类别只有允许字段可写；整 State/未知字段/冲突 delta 失败；before/after fingerprint 闭合 | 必须完成 |
| C2 natural seam | canonical T1→T2、paraphrase、指代/省略与独立 correction | 全部从自然语言生成 typed delta；测试不直接注入 delta；不唯一时澄清而非猜测 | 必须完成 |
| C3 SQL Evidence invalidation | Phase 4B SQLite profile 两 turn E2E | T1 7 月 Evidence 在 T2 时间修改后 invalidated；T2 重新查询 7/8 月并得到 `120000/180000`、差额 `60000`、变化率 `50%` | 必须完成 |
| C3 correction/switch/cancel | 独立 task sequence | correction 只失效受影响事实；switch 返回新 task identity且不继承 pending/Evidence；cancel 零 Graph/Tool并禁止继续 | 必须完成 |
| C4 task lifecycle | owner/version/claim/TTL/clear/commit fault 与并发 tests | 同 version 仅一个 claim；wrong owner/missing 无差别；失败不重复 Tool；runtime 明示 non-durable | 必须完成 |
| C5 node Context | 各实际 node allowlist、actual-input 与篡改 tests | Turn/SQL/route/controller 只见允许字段；无 rows/正文/完整历史/旧 answer；identity/budget 可复算 | 必须完成 |
| C5 provider/outbound fallback | provider adapter 未注册/未授权 case | deterministic 路径正常；模型用途网络前拒绝且不影响 State；若选择 B 则另有一次授权 E2E | 必须完成 |
| C6 API compatibility | legacy initial/resume/follow-up + task start/continue/switch/cancel/clear + payload mix/unknown | 正确 family/响应；旧字段语义不变；task strict unknown；混用/注入零 Graph/Tool | 必须完成 |
| C6 invocation accounting | accepted/rejected/clarification/cancel matrix | legacy 仍为 accepted=1/rejected=0；agent task-boundary 与深 Harness 次数分列，所有路径可解释 | 必须完成 |
| C7 Trace/Eval 同源 | API response、JSONL Trace、State ledger、v2 artifact 对账 | task/delta/state/evidence/context/runtime identity 来自同一 turn；零评分重跑；安全投影无敏感正文/rows | 必须完成 |
| C7 Agent Scenario v2 | canonical、correction、switch/cancel、role drift、payload mix、context leak、tamper | selected sequence/turn/execution/assertion 恰好闭合；required 全 observed/pass；非法 artifact 拒绝 completed | 必须完成 |
| legacy/历史回归 | M35–M38、M40/M41、M42 v1 聚焦回归 | legacy runtime、thread/follow-up、Hybrid、Trace、Eval 和 B0 identity/断言未改变 | 必须完成 |

聚焦测试顺序：v1/v2 identity → TaskDelta/merge/invalidator → task lifecycle → natural adapter/Context → API T1→T2 → Agent Scenario v2/tamper。

全量回归范围：M27 Phase 4B seed 所触及的 Text2SQL seam、M35–M38 Harness/thread/follow-up/Hybrid、M40 Trace assurance、M41 RAG Eval contracts、M42 全部 B0 contracts，以及最终全仓 deterministic pytest。预计超过 2 分钟的完整验证按 `AGENTS.md` 写 notes checkpoint 后后台运行。

不属于本模块的验证：真实 LLM/embedding（除非 G43-3 选择 B 且另获精确授权）、M41/M34 真实 Eval、RAG recovery、M46 reserve、跨进程重启、多 worker、durable storage、Context Compact 和完整 T1→T5。

历史 artifact/合同只读：M27/M31–M42 completed artifact 不补字段、不改签、不重跑制造 M43 分数；M42 v1 只作 B0 历史/兼容回归，M43 v2 使用新 identity；M46 reserve 继续 sealed。

## 9. 依赖与交付物

### 依赖

- M42 已验收的 B0 bundle、Phase 4B seed/oracle、最小 caller、runtime family 方向和 Agent Scenario v1。
- Phase 4 的统一 `/api/query`、turn seam、深 SQL/RAG Tool、四轴、Evidence/citation、caller/ACL/outbound、Trace 和 legacy regression。
- `net_refund_amount` 当前指标口径与 Phase 4B 7/8 月真实 SQL oracle。
- 用户已确认 G43-1～G43-3 全部采用方案 A。

### 交付物

- B1 canonical sequence/catalog/manifest 与 v1→v2 compatibility/capability view。
- adapter-neutral TaskDelta/TaskState/change set/Evidence validity/turn-event contracts。
- 独立 in-memory task-boundary adapter 和 lifecycle/security projection。
- deterministic natural Turn Understanding adapter 与首批 node Context Builder/actual-input evidence。
- agent task turn seam、同一 `/api/query` 的 request/response/Trace 增量投影和稳定错误矩阵。
- Agent Scenario v2 completed artifact/validator/report 与 B1 deterministic rehearsal。
- M44/B2 可直接消费的稳定 TaskState、turn boundary、Context 和 runtime family seam；实现过程写入 `docs/notes/m43-notes.md`，收工按规则更新 state/changelog。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：同次 Observation-driven 多动作、完整 Action/Budget/Progress、RAG action campaign/Subgraph、durable adapter、Compact 和产品默认切换。
- 下一模块 M44/B2 可直接消费：TaskDelta/State、Evidence validity、task-boundary invoke、node Context、agent runtime family、canonical v2 和 Agent Scenario v2，并加入 Decision Loop、父子预算、T3/顶层 T4/整合 T5。
- M45/B3 仍从 M42 首次 business 漏选 Observation 开始；M43 不修改 retrieval 参数、active release 或 action admission。
- M47/B5 的强制开工条件：C2/C4 的 TaskState/turn boundary 已稳定，M44 的 loop turn boundary 已完成；届时选择真正具备存储层 CAS 的 durable backend，不能把 M43 in-memory adapter 冒充持久化。
- M48/B6 的强制开工条件：typed ledger、node Context 和 durable state 稳定；最终以 deterministic typed Compact 的行为等价 Gate 验收。
- 可能风险：deterministic adapter 退化为关键词模板、TaskState 变万能对象、API family 判定含糊、旧/new invocation count 混算、v1/v2 双 canonical、Evidence invalidator 漏规则。对应控制分别是非退款/paraphrase删除测试、node Context allowlist、嵌套 envelope、runtime-specific counter、版本兼容门和表驱动失效矩阵。
- 最终目标没有缩水：M43 只在第 8 节 required 全部通过后宣称 B1 完成；在 M44–M48 未分别完成前，不宣称 Phase 4B Loop、Agentic RAG、durable state 或 Compact 完成。

## 11. 开工条件

- 开工前无需确认：M43 完整对应 B1；同一 `/api/query`；legacy/agent family 隔离；M42 v1 只读；Phase 4B seed/caller/指标口径不变；B1 使用进程内 task adapter 且不冒充 durable；不解封 reserve。
- 已确认：G43-1 采用 additive v2，M42 v1 保持不可变，M43 及后续模块消费新的 B1 canonical/Agent Scenario v2；G43-2 采用嵌套 task envelope，仅新 family 严格拒绝 unknown；G43-3 采用本地 deterministic adapter + 保守澄清。本模块不需要真实 provider/outbound 授权。
- 实施中需要确认：无。只有命中 G43-1～G43-3 的重开条件，或出现新的范围/核心合同/安全冲突时才暂停并重新提交决策。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得通过改签 v1、直接注入 TaskDelta、弱化 Evidence invalidation、放宽 ACL/outbound 或把后续能力写成模糊优化继续施工。
