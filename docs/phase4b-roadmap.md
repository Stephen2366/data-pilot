# DataPilot Phase 4B Roadmap：Evidence-driven Bounded Agent

> **文档定位**：本文是 Phase 4B 的高层推进事实源，位于“阶段方向”与“具体 module plan”之间。它冻结最终能力、演进顺序、依赖、纵向切片、核心合同、交付物、验收语义和决策门，但不提前固定模块编号、类名、文件结构、存储后端、模型、Prompt、阈值、循环次数、token 上限或性能目标。
>
> **历史关系**：Phase 4 已按其 roadmap 完成可信 Knowledge/RAG、typed Evidence/citation、顶层 Harness、最小 bounded recovery/thread、保守 Hybrid、P6 readiness audit 与 P7 technical assurance。M39 P6 `no_go` 是在当时冻结 Evidence 下作出的正确结论，不是开发失败，也不被本文回写为“当时应强行实现”。Phase 4B 是在已完成基线之上的新能力阶段，不是 Phase 4 欠债清单。
>
> **效力关系**：本文只拥有 Phase 4B 的路线决策权。Phase 4 的历史目标与合同来源见 `docs/phase4-roadmap.md`；当前运行、数据库、RAG、Eval 与默认配置分别以 `docs/state/` 对应事实源和实际代码为准；外部设计参考统一从 `docs/phase4-reference.md` 进入。进入任一能力切片后，仍须结合最新 state、失败证据、相关源码和 reference 编写独立 module plan 与 notes，不能直接把本文当逐文件施工清单。
>
> **路线决策基线**：2026-08-22。本文由 `docs/notes/phase4-rag-capability-status.md` 第 12 节的已确认方案升格而来。

## 1. 阶段目标与完成故事

Phase 4B 的目标，是把当前“固定 DAG + 一次结构化恢复/追问”的可信 Agent 基线，升级为一个能够围绕同一企业分析任务持续推进、依据 Evidence 变化选择下一动作、在多轮和重启后保持任务语义、并对每个决策与上下文进行评测的 **bounded task-oriented Agent**。

阶段最终必须完整交付六项能力，任何一项都不能因为实现或验收更容易而降级为模糊后续项：

1. **Evidence-driven bounded Agent Loop**：同次任务运行中读取 typed Observation，以 Evidence requirement、EvidenceDelta、Budget 与 Progress 为依据，从已登记动作中选择 Next Action 或确定性停止；它是 Decision Loop，不是自由 Thought Loop。
2. **Bounded Agentic RAG**：Knowledge Tool 内存在真实、有父子预算的 RAG Subgraph；全局 action catalog 至少包含两种经 Evidence 证明合格的恢复动作，每次运行依据 runtime/corpus、ACL 与首次 Observation 形成 eligible action set 并选择动作或停止，且至少一个 runtime/corpus 能在不同真实 Observation/Scenario 下分别触发两种动作；确定性 Pipeline 长期保留为 baseline/fallback。
3. **任务级自然多轮**：自然语言 turn 经 Typed TaskDelta 受控合并到 TaskState，支持连续修改条件、解释旧结果、追加 Evidence requirement、纠正理解、切换任务、取消及 SQL/RAG/Hybrid 间的受控 route 变化。
4. **持久任务状态与 node-level Context Builder**：任务可在进程重启和多 worker 下按 owner/tenant/role、TTL、版本与原子 claim 合同恢复；每个节点只接收自己需要的 typed 最小上下文，并留下实际入模投影。
5. **Context Compact 基础版**：session 内 typed turn/event ledger 可收敛为可追溯、可验证的结构化 Task Compact；compact 前后关键任务行为等价，失败时保守降级。
6. **贯穿建设的北极星多轮 Scenario 与 Agent Scenario Eval**：从第一片开始用同一复杂任务牵引能力演进，并用独立、版本化、非 happy-path 配套齐全的 Agent Scenario family 验证每个 turn 的状态、动作、Evidence、Context、预算、安全与终止。

阶段完成后的可展示故事是：

> 用户从“查询 7 月实际净退款金额”开始，改为查询 8 月并与 7 月同口径比较，追问 8 月为何上涨、要求结合公司的退款规则解释、再纠正为按渠道分析。DataPilot 能在同一任务中安全地合并条件、使旧 Evidence 失效、根据 Observation 补取 SQL/Document Evidence、必要时在 RAG 子图内恢复检索，并在重启和 context compact 后继续；每个结论、动作、预算与停止原因都可由 Trace 和 Eval 回查。

这条故事同时服务项目展示和面试：它展示的不是“节点很多”，而是企业 Agent 的控制权、安全、状态、Evidence、上下文与评测如何形成闭环。

## 2. Phase 4B 起点与真实增量

### 2.1 已完成、直接继承的 Phase 4 基线

| 已有能力 | Phase 4B 的复用方式 | 不得改写的边界 |
|---|---|---|
| `/api/query` → turn seam → 顶层 LangGraph Harness | 继续作为唯一业务入口和全局控制 seam | 不另建多轮/Agentic RAG API 旁路；accepted turn 的执行事实仍由统一 turn/result 投影 |
| SQL/RAG 深 Tool 与 M38 Hybrid 双 Evidence | 作为允许动作的底层执行能力 | 不把 Text2SQL、RAG AnswerFlow 拆成大量顶层浅节点；Hybrid 不消费两个自然语言子答案 |
| 四轴 route/execution/answer/safety | 扩展到多动作、多 turn 与持久恢复 | 技术不可用、安全拒绝、证据不足和 partial 继续保持正交 |
| 四阶段 Evidence、Shared Gate、Composer、Citation Validator | 作为 Loop、Subgraph、Compact 和 Eval 的共同事实基础 | Progress Policy 不能成为第二个 Answer Gate；Subgraph 不复制 Composer/Citation |
| trusted caller、文档 ACL 双检与 outbound 默认拒绝 | 覆盖 TaskState、checkpoint、Context、模型动作与 RAG 子图 | 请求体 role、thread id、collection 或模型自觉都不能授权 |
| `m37-thread-v2` 进程内 clarification/follow-up | 作为旧回归与持久状态语义的最小先例 | 它从未持久化；不得伪装成在线可迁移状态或多 worker 能力 |
| M31–M40 deterministic contract 与 M34 external 基线 | 作为 Phase 4B 回归锚点和 RAG 失败证据输入 | 不补写、不混算、不重跑来制造 Phase 4B 新分数 |
| M39 P6 strict `no_go` | 作为“为什么必须先产生 action-level Evidence”的历史证据 | 不回写成失败；也不扩大解释为永久禁止 Agentic RAG |

Phase 4B 不用一套新语义覆盖这些历史合同。旧 M35–M38 fixture 必须显式固定 legacy bounded runtime family，继续验证“一次 Graph、单路至多一个深 Tool、Hybrid 每支至多一次”等原合同；北极星与新 Agent Scenario 使用独立的 versioned agent runtime family。二者可以共享深 Tool、Evidence、四轴和安全底座，但旧 family 不必伪造新 TaskState，也不得通过放宽旧 assertion 来兼容新 Loop。

### 2.2 Phase 4B 必须新增的能力

当前代码仍是固定的 `route → Tool/branches → controller → END`；Graph 不会根据本次 Observation 自主选择第二个允许动作。现有 thread 只覆盖一次 clarification 或一次 signed follow-up，Router/Hybrid 仍是 closed-world，Context Builder 只有少量固定模板，checkpoint 只存在于当前进程，Knowledge Tool 每次调用只执行固定单次 retrieval，且没有 TaskState/TaskDelta、父子预算、EvidenceDelta、持久 turn ledger 或 Compact。

Phase 4B 的增量因此不是“再加一个检索器”，而是同时建设：

- 任务语义层：Natural-language Turn → Typed TaskDelta → Controlled TaskState Merge；
- 控制层：Action → Observation → EvidenceDelta → Progress/No-progress → Next Action/Stop；
- 取证层：顶层全局动作与 RAG 内部恢复动作分权，父预算覆盖子预算；
- 状态层：安全的 durable task boundary state，不恢复任意 Graph program counter；
- 上下文层：node-level typed projection、token/context budget、实际入模证据与结构化 Compact；
- 评测层：一次 sequence 执行、多 turn/multi-action typed assertions、closed-world identity、sealed decision reserve 与 historical regression 分账纪律。

## 3. 目标架构与控制权

```text
Natural-language Turn
  → Turn Understanding / Typed TaskDelta
  → Controlled TaskState Merge + Evidence validity
  → node-level Context Builder
  → Top-level Evidence-driven Decision Loop（唯一全局控制者）
       ├─ clarify / wait for user（在 turn boundary 停止）
       ├─ Text2SQL Tool → SQL Evidence
       ├─ Knowledge Tool
       │    ├─ deterministic Pipeline（baseline / fallback）
       │    └─ bounded RAG Subgraph（只负责 Document Evidence acquisition）
       ├─ Hybrid thin plan / required branches
       └─ partial / stop
  → Shared Answer Evidence Gate（唯一回答充分性 Gate）
  → Composer / Hybrid Synthesizer
  → Citation Validator
  → AgentResponse + Trace + Agent Scenario ExecutionEvidence

Task boundary
  ↔ versioned durable checkpoint
  ↔ typed turn/event ledger
  ↔ structured Task Compact + recent raw turns
```

控制权固定如下：

- **顶层 Harness/Controller** 独占任务级 route、澄清、跨 Tool 补 Evidence、Evidence 失效重取证、父预算、partial、最终四轴与停止；它只表达“缺少哪类 Evidence”，不指定 query rewrite、parent expansion 等 RAG 内部策略。
- **RAG Subgraph** 只在 Knowledge Tool 的 Document Evidence acquisition 内消费子预算，负责根据检索 Observation 选择已登记的文档恢复动作、合并/去重 Evidence 和停止；无权调用 SQL、改变 Hybrid、生成最终答案或扩大全局预算。
- **Shared Answer Evidence Gate** 仍是唯一回答充分性裁决者；顶层与 RAG 内部的 Progress Policy 只判断 Evidence 是否增加、requirement 是否仍有可用动作，不生成答案，也不成为第二个 Gate。
- **模型节点**只能提出结构化 TaskDelta 或 action proposal；确定性控制层必须校验 schema、allowlist、预算、ACL、outbound、安全和 no-progress。模型不可用或未获授权时不能自由猜测。
- **durable checkpoint** 只保存安全任务边界状态；clarification 结束当前 invoke，用户下一轮从 TaskState 重新进入 Loop。Phase 4B 不保存或恢复任意节点栈、Graph program counter、模型 Thought 或隐藏执行过程。

## 4. 跨里程碑核心合同

### 4.1 TaskState、TaskDelta 与 turn/event

- TaskState 表达当前 goal、confirmed/corrected constraints、pending questions、Evidence requirements、route/允许动作、active EvidenceRef/validity、预算与 termination 等任务事实；它不是聊天记录或万能对象。
- TaskDelta 至少区分 `continue`、`modify_constraint`、`ask_about_existing_result`、`add_evidence_requirement`、`switch_task`、`correct_previous_understanding`、`cancel/stop`；具体字段随 module plan 冻结，不能硬编码退款/月/渠道。
- TaskDelta 只能修改合同允许的 TaskState 部分；模型或客户端不能一次覆盖整份 State。switch/cancel/correction 必须有显式 Evidence 失效与 pending action 处理语义。
- 每个 turn/event 至少记录 turn identity/order、TaskDelta、TaskState 前后 fingerprint、EvidenceRef/validity、route/action、状态/termination 和安全 runtime identity；最近用户原文只按 delta/指代、审计和 compact 所需的最小范围与 TTL 保存。
- 不保存旧完整 answer、SQL rows、Document 正文、无限消息历史或模型思维链。

### 4.2 Evidence 复用与失效

- TaskDelta 只描述任务变化，不自动赋予旧 Evidence 复用权。
- 没有可靠业务 snapshot/freshness identity 时，SQL Evidence 在条件、指标、维度或 route 变化后重新查询；解释旧结果也必须区分“解释已冻结事实”与“重新证明当前事实”。
- external Document Evidence 默认重新检索。
- business same-requirement 只有重新核对 active authority、revision、content identity、anchor、purpose 与 ACL 后才能重水化，并签发本轮新的 Evidence/ledger/citation；requirement 或 identity 变化重新取证。
- denied/revoked/stale Evidence 不进入 Context、Composer、citation 或 Compact；ACL/用途拒绝不能通过补查泄露文档存在性。

### 4.3 Action、Observation、Budget、Progress 与 Termination

每个允许动作必须有：

```text
trigger / Evidence requirement
→ action identity + allowed scope
→ budget before / consumed
→ typed Observation
→ EvidenceDelta（added / removed / invalidated / duplicate）
→ progress / no-progress
→ next action or termination reason
```

- action allowlist 是 closed-world 合同；运行时不得生成、注册或执行新 Tool/动作。
- 预算不能折叠成一个不可解释的综合分。至少分别记录 action、Tool call、retrieval call/candidate/selected/context、model call/token 与 timeout/latency；计数和资源上限承担确定性停止，延迟/费用作为观测与 A/B 维度。
- 顶层持有总账并分配子账；RAG Subgraph 的每次消费回写总账。父子两层不得对同一取证失败分别循环。
- recoverable、需要用户信息、不可恢复、unsafe、no-progress、budget exhausted 与 external unavailable 都有稳定终止语义；重复动作没有新 Evidence 时必须停止。
- Loop 是 Evidence-driven Decision Loop，不保存或依赖自由文本 Thought 来证明进展。

#### Runtime family 兼容合同

- Phase 4B Agent Loop 只在新的 versioned agent runtime family 中启用；同一 accepted turn 仍是一份统一 turn/result 事实，但一次 Graph invoke 内可以按预算执行多个已登记动作。
- 历史 legacy bounded runtime family 保持原有 Tool/branch 预算、request shape、Trace/Eval 投影与 assertion；旧 Eval fixture 必须显式 pin 该 family，不能依赖“当前默认碰巧仍兼容”。
- 新旧 family 共用安全深 Tool、Evidence/citation、四轴和 caller/ACL/outbound seam；是否具有 TaskState、Action ledger 和多动作预算由 family identity 明示，不能靠字段是否为空猜测。
- `/api/query` 的产品默认何时从 legacy 切换到 agent runtime 必须单独经过兼容回归、演示与用户确认；内部兼容 family 不直接变成客户端可任意选择、可绕过安全门的公开开关。
- Phase 4B Gate 同时要求旧 M31–M40 原合同通过和新 Agent family 通过；禁止改写旧 assertion、向旧 artifact 补字段或把旧 family 静默排除在回归之外。

### 4.4 State、Context 与 Compact

- State 保存事实；Context Builder 决定节点此刻能看到什么；完整 State/历史不能无差别进入 prompt。
- Router、Turn Understanding、SQL、RAG、RAG Subgraph、Composer、Hybrid Synthesizer、Controller 分别使用 typed context projection；每个投影有允许字段、来源、identity/fingerprint、context/token budget 和实际入模记录。
- SQL 节点不看全部文档，RAG 节点不看完整 SQL rows，Router 不看 Document 正文，Composer 只看 Gate 允许的 generation-visible Evidence。
- Task Compact 是 typed turn/event ledger 的确定性结构化派生物，至少保留 goal、confirmed/corrected constraints、pending questions、unresolved Evidence requirements、active EvidenceRef/validity、action/budget/termination 与高风险原始 reference。
- Compact 必须记录来源 turn 范围、版本/fingerprint、触发原因和失败降级；不得用不可验证摘要替代时间、金额、指标口径、否定、政策例外或 Evidence identity。
- 基础版不依赖 LLM 自由摘要。未来若引入叙述性摘要，它只能作为不可信派生字段，并单独通过 outbound、faithfulness 与降级门。

### 4.5 Durable checkpoint

- B1 先建立独立于 `m37-thread-v2` 的 versioned TaskState family，并通过 task-boundary interface 接 in-memory adapter；B5 在该稳定任务边界上增加 durable adapter 和必要的 schema version 演进。
- 新 durable state family 从第一版携带 schema version、owner/tenant/active role、TTL、显式 clear、乐观版本与原子 claim；claim、version bump、clear 和过期处理必须由存储层条件更新保证，而不是应用“先读后写”模拟。
- 新 TaskState 的持久 adapter 与 in-memory adapter 通过同一任务边界语义对接，in-memory 只服务快速测试、不能冒充持久化；历史 manager 独立服务 M36/M37 legacy 回归。
- 历史 `m37-thread-v2` 从未跨进程持久，只服务 legacy clarification/follow-up 回归；禁止扩字段把它改造成新 TaskState，也不要求在线迁移。不兼容 family/version 必须拒绝恢复。
- owner 不只绑定 raw thread id；恢复时重新验证 caller、tenant、active role、ACL、Evidence validity 与 outbound 条件。wrong owner/missing 继续保持不可区分的安全公开语义。
- checkpoint 不成为长期记忆仓库；TTL、数据最小化、删除、tombstone/清扫、失败恢复和审计保留必须在存储决策时闭合。

### 4.6 安全、出站、四轴与 Trace

- Phase 4 的 caller、文档 ACL、SQL Guard、outbound 默认拒绝、四轴状态、Evidence/citation 与非泄露合同全部继承。
- Turn Understanding、decision proposal、query rewrite、Evidence requirement split/subquestion、rerank、Compact summary 等每种模型用途都按 receiver/node purpose/data class/fields 单独登记；不能继承既有 Text2SQL 或同 provider 的出站许可。
- 未授权、provider unavailable 或结构化解析失败时，只能执行触发条件可由确定性事实确认的动作；否则澄清或停止。
- Trace 记录 TaskDelta/State fingerprint、action、Observation、EvidenceDelta、父子预算、Context identity、checkpoint lifecycle、Compact identity 和 termination 的安全投影；不保存原始凭据、raw thread 参数副本、完整正文/rows 或模型 Thought。
- Trace/API/Eval 继续从同一 task/turn/action 事实投影；不得为评分重跑一条不同 pipeline 来补证据。

### 4.7 公开 turn seam 与 API 增量演进

- `/api/query` 保持唯一业务端点；新自然多轮通过版本化 task-turn 请求/响应投影增量接入，不新建 Agent 或多轮旁路。
- M36/M37 的 `thread_id + expected_version + clarification/follow-up payload` 继续由 legacy family 承载；新 task payload 与旧 payload 必须互斥，服务端不能猜测请求属于哪个 family。
- Phase 4B 内不删除、不改名旧公开字段，也不把旧 `ThreadView`、一次 follow-up budget 或旧 `turn_action` 生硬扩成万能 TaskState。新 TaskState/version/termination 使用独立安全投影，具体字段名由 B1 module plan 冻结。
- B1 必须给出 request/response/Trace/Eval compatibility matrix，明确 initial、legacy resume/follow-up、新 task continuation、switch/cancel 和错误组合分别解析到哪个 family、返回什么稳定错误，以及旧客户端的弃用但可用边界。
- 当前 Pydantic 请求只对已知 thread/follow-up 组合做严格校验，未知字段并未形成统一的 `extra=forbid` 合同；B1 必须显式决定新 task payload 的 unknown-field 策略，不能把现状误写成既有保证。

## 5. 北极星 Scenario 与前置合同

### 5.1 Canonical sequence

| Turn / 变体 | 任务变化与预期行为 | 主要能力锚点 |
|---|---|---|
| T1：查询 7 月实际净退款金额 | 建立任务，route=SQL，按 `refunds.processed_at` 取得 7 月 `net_refund_amount` SQL Evidence | B1 |
| T2：改成 8 月，并与 7 月比较 | 只修改时间范围，重新取得同指标、同时间口径的 8 月 Evidence，并给出变化量/变化率；旧单月 SQL Evidence 失效 | B1 |
| T3：为什么 8 月比 7 月上涨 | 增加原因分析 Evidence requirement，由 Observation 驱动允许的 SQL/全局补证据动作；输出限于证据支持的结构分解/归因，不冒充已证明的业务因果 | B2 |
| T4：结合公司的退款规则解释 | 增加需要基础政策与质量问题专项规则共同支撑的 Document Evidence requirement，SQL → Hybrid；业务检索若缺证据，由 RAG 子图恢复 | B2 顶层、B3/B4 RAG |
| T5：不对，改成按渠道维度分析 | correction 受控修改维度，相关 SQL Evidence 失效；政策 Evidence 重新核验后才可复用 | B1/B2 |
| 重启、多 worker、并发旧版本后继续 | 从安全任务边界恢复，不恢复 Graph 执行栈 | B5 |
| extended sequence 触发 compact 后继续 | compact 前后 typed 任务行为等价 | B6 |

北极星 sequence 是贯穿建设的用户故事，不是唯一测试题。配套 Scenario 必须覆盖任务切换、取消、连续 clarification、指代/省略、ACL 拒绝、Evidence revision 变化、无进展、预算耗尽、provider unavailable、重复请求、版本冲突、TTL、clear 和 unsafe action。

### 5.2 正式开工前置

1. **versioned seed/oracle profile 与可合成叙事**：现有订单支付月份只有 2026 年 5/6 月，退款请求/处理时间可延伸到 7 月，但仍不能支持同口径的 7→8 月故事。B0 必须建立独立 Phase 4B deterministic seed/oracle profile，旧 M27/M31–M40 fixture 显式 pin legacy profile；profile identity 必须绑定可复现的 seed recipe/content/config fingerprint，并在环境解析时 fail closed，不能只沿用或重命名 `sqlite_deterministic_seed` 标签。新 profile 按 `refunds.processed_at` 增加可比较的 7/8 月 `net_refund_amount` 结构，并同步 `orders_wide` snapshot/batch、`verify_business_facts()`、数据库 state、受影响 oracle/schema；旧 artifact 只读冻结，新旧结果禁止直接比较。若 B0 证据迫使修改 canonical seed，则必须显式升级 oracle fixture identity、run spec/hash、受影响 Scenario/oracle 与可比性说明，不得让数据变化而评测身份不变。7/8 月结构还必须冻结可验证的原因/渠道/商品分解，使 SQL Evidence 的业务归因键能与政策的适用范围安全合成；只允许表达“观测到的驱动结构 + 对应处理规则”，不得把政策条款写成退款上涨的因果证明。
2. **最小权限 demo caller**：北极星只在 local/demo fixture 演示，不冒充生产认证。当前 fixture 拥有全部已知角色，而两篇退款政策要求 `customer_service`、分析 SQL 通常需要 `ops`；B0 必须冻结完成故事所需的最小 resolved role 集、active SQL role 和跨 turn 权限复核。优先验证 `ops + customer_service` 的最小双角色 fixture、active SQL role=`ops` 是否足够；若政策 ACL 需要调整，必须走正式 Knowledge release/identity 与 ACL 回归，不能为 demo 临时放宽。
3. **业务 RAG failure case 与非测试陷阱纪律**：现有默认 business retrieval 对直接点名“基础退款政策和质量问题专项规则”的 T4 问法会稳定选中 `refund_policy_basic`、`refund_policy_quality`，因此该原句不能直接承担 recovery 证明。B0 应在正式 case 冻结前改用真实用户会提出、但逻辑上确需双文档的自然问法，或选择其他已观察到的业务多文档失败簇；不能通过压低 top-k、测试专用 metadata 或反复改词制造漏召回。只有现有 corpus 无法形成真实案例时，才可基于独立业务理由自然补充语料，并在观察 retrieval 结果前完成内容合理性审查、gold requirement 与正式 release identity 冻结；新增文档不得以“必须挤掉某篇文档”为写作目标。
4. **Hybrid operator 复核**：现有 `refund_reason_and_policy` 只是固定薄计划，不能自动继承 8 月 TaskState。B0/B2 必须决定对其做 versioned 语义泛化还是新增边界更准确的 operator；不能靠关键词命中宣称已覆盖北极星。
5. **Agent Eval family skeleton**：在 B0 冻结 sequence identity、turn identity、seed/caller/release/runtime family identity、ExecutionEvidence 和 closed-world 完整性规则；旧 M31–M40 fixture 显式 pin legacy family，新北极星显式使用 agent family，具体能力 assertion 随纵向切片递增。
6. **API/state 兼容矩阵方向**：B0 先冻结“同一 `/api/query`、legacy request 保留、新 task-turn 增量投影、两类 payload 互斥”的路线边界；具体字段和弃用说明由 B1 module plan 完成，不能等施工时再临时决定。
7. **sealed decision reserve**：M34 已运行并用于默认决策的 120 题 held-out 降级为 historical regression set，不再承担 Phase 4B 的“未污染”默认切换证明。B0 必须冻结新的 decision reserve identity、生成/抽样与 gold 规则、污染账本、允许用途和首次解封条件；优先采用同一冻结 corpus 上独立编写的新问题集或新的 corpus/question split。仅当访问审计能证明逐题结果从未被查看、子集选择完全盲化时，才可把旧集合的 nested reserve 作为较弱证据，且不得宣称恢复了最高等级的未污染性。
8. **RAG action catalog 验收口径**：全局 catalog 至少两种合格动作；每张 action card 声明适用 runtime/corpus、trigger、预算、ACL/outbound、Evidence gain 与停止边界。单次运行的 eligible action set 可为零、一或多个，`stop` 始终可用；至少一个 runtime/corpus 必须在不同真实 Observation/Scenario 下分别证明两种动作的正确选择与错误动作排除，不要求同一道题同时暴露两种动作。

精确 seed 数字、role 集、知识 ACL、operator 语义和 Eval case 内容会改变长期默认或正式合同，必须在 B0 module plan 中给出选项、风险与建议，按 `AI_CONTEXT.md` 规则取得用户确认后实施；本文不替代该决策。

## 6. 能力路线总览与依赖

B0–B6 是能力里程碑，不与模块编号一一对应。每个里程碑可拆成多个最小纵向 module plan，但同一时间只维护一个 active module plan。

| 里程碑 | 纵向能力切片 | 主要依赖 | 北极星推进 | 路线属性 |
|---|---|---|---|---|
| B0 | 入口、北极星前置与 Agent Eval 骨架 | Phase 4 完成基线 | 冻结 T1–T5 与非 happy-path | 主线必做 |
| B1 | Task runtime + 自然多轮 v1 + node Context 起步 | B0 | 跑通 T1–T2，独立证明 correction | 主线必做 |
| B2 | 顶层 Evidence-driven bounded Decision Loop | B1 | 跑通 T3、顶层 T4、整合 T5 | 主线必做 |
| B3 | RAG 失败漏斗与 action-level Evidence | B0；可与 B1/B2 交错 | 为 T4 找到真实恢复动作 | 主线必做 |
| B4 | bounded Agentic RAG Subgraph + A/B | B2 父子预算、B3 合格动作 | 完成 T4 内部多步取证 | 主线必做；默认化单独决策 |
| B5 | durable task state | B1 稳定 TaskState，B2 turn boundary | 北极星跨重启/多 worker 继续 | 主线必做 |
| B6 | Context Compact 基础版与阶段集成 | B1 Context/ledger、B5 durable state；最终汇合 B2/B4 | extended sequence + 全链闭环 | 主线必做 |

能力依赖为：

```text
B0 → B1 → B2 ───────┐
  └────→ B3 → B4 ───┼→ B6 final integration
         B1 → B5 ───┘
```

B3 可在 B1/B2 施工间隙交错推进；B5 不必机械等待 B4，但 B4 必须消费 B2 的父子预算合同。持久 checkpoint 不阻塞首个多轮/Loop 演示，Compact 不阻塞早期 Context Builder；二者仍是 Phase 4B 最终硬交付，不能被降级为“以后按需”。

## 7. B0：阶段入口、北极星前置与 Eval 骨架

### 目标

把故事所需的数据、身份、知识、Hybrid 语义和评测身份先变成真实可执行合同，避免后续围绕不存在的 7/8 月数据或伪造的 RAG 失败开发抽象。

### 参考项目小结

- **Eval 骨架**：定点复核 `ARAG-EVAL` 与 `DBGPT-EVAL`，借鉴“先保存实际 Agent answer/context，再评分”和 retrieval/answer 分层；不照搬 notebook 简单均值、空结果统一记零或评分时重跑 pipeline。
- **数据与发布身份**：若 B0 新增 seed、decision reserve 或业务语料，定点复核 `WREN-INDEX/WATCH` 与 `DATAAGENT-REPLACE`，只借鉴 source/derived 分离和成功后推进状态；不把 mtime fingerprint、best-effort cleanup 或“有索引”当成可复现 identity、原子发布或回滚保证。
- **规模教训必须在 B0 落地**：参考复核必须回答当前 fixture/corpus 的文档数、长度/结构、问题类型、失败可观测性与产品链路差异。M29–M33 虽逐模块定点看过源码，但 11/22 条短知识仍无法暴露大 corpus 上的召回、context packing 与多文档失败，最终由 M34 的 36,417 文档、180 题与真实 Tool 链路补底座。B0 不得再用小 fixture 合同全绿推断 Agent/RAG 质量底座已足够。

### 主要交付物

- 北极星 canonical sequence、extended sequence 与配套非 happy-path catalog；
- 经用户确认且与 legacy 隔离的 versioned seed/oracle profile、最小 demo caller、业务双文档 gold requirement 与 Hybrid operator 方向；
- 独立版本化 Agent Scenario artifact skeleton、ExecutionEvidence、closed-world validator 与 runtime identity；
- 新 sealed decision reserve 及污染/解封账本；M34 historical regression set 的用途边界；
- legacy/agent runtime、API request/response、TaskState family 的兼容矩阵初版；
- Phase 4B capability matrix 初版，明确继承、待建和范围外；
- B1/B3 首批 deterministic fixture 与不调用真实 provider 的合同测试边界。

### 完成标志

1. T1–T5 每一 turn 都能说明 TaskDelta、预期 Evidence、失效规则、route/action、required/advisory assertion 与安全身份；
2. Phase 4B seed/oracle profile identity 能校验到实际 recipe/content/config；7/8 月同口径净退款金额由真实 SQL 可验证，legacy profile、旧 artifact 与历史不受影响项边界清楚；
3. 数据变化可分解到能与政策适用范围合成的业务键，且没有把政策冒充因果证据；
4. demo caller 不再依靠“拥有全部角色”证明任务可行，跨 SQL/Document turn 的最小角色与 active role 已冻结；
5. RAG case 的首次检索结果已实际观察；若新增语料，其业务合理性、正式发布和非测试陷阱审查已通过；
6. Agent Eval completed artifact 能拒绝缺 turn、额外 execution、重复 assertion、seed/caller/release/runtime identity 漂移；
7. legacy/agent family 与 API/state 演进方向闭合，且未冻结模型、存储后端、预算数值或具体实现结构。
8. 新 decision reserve 在任何动作、Prompt 或参数选择前已密封，污染与退出规则可审计；当前 M34 120 题只按 historical regression set 使用。
9. action catalog 的全局、runtime/corpus 适用和单次 eligible set 三层语义已冻结，不以跨 runtime 各有一个静态动作冒充 Observation-driven 选择。

### 决策门 G4B-0

确认 exact seed/business facts、seed/oracle profile identity 与数据—政策可合成关系、demo role 集、必要的 Knowledge release/ACL、真实 business RAG case、Hybrid operator 语义、runtime/API/state 兼容方向、sealed decision reserve 和首版 Agent Eval/action catalog。未确认前可以做只读调查和 deterministic prototype，不能改变长期 seed、release、默认权限、正式 case 或解封 decision reserve。

## 8. B1：Task Runtime、自然多轮 v1 与 node-level Context 起步

### 目标

建立 adapter-neutral 的 TaskState/TaskDelta/turn-event 语义，并立即通过 T1–T2 证明自然语言条件修改与 Evidence 失效，而不是只建设横向数据类。

### 参考项目小结

- 定点复核 `ARAG-STATE/GRAPH` 的 `State/AgentState`、reducer、主图/子图边界和 clarification interrupt，借鉴显式状态字段、去重与任务/检索状态分离；对照源码同时记录其 `MessagesState` 全历史、LLM rewrite/summary、`InMemorySaver` 和固定 clarification 循环不能直接支撑 DataPilot 的 typed TaskDelta、Evidence validity 与安全投影。
- 定点复核 `DATAAGENT-GRAPH` 中 state key strategy 与固定 Graph 接线，仅借鉴“先冻结状态合并语义，再由节点/边消费”的思路；不复制其大而平的全图 state、Java 平台层或完整 NL2SQL 节点编排。
- B1 的阅读证据必须跟踪一条真实自然语言 turn 如何进入 state、被节点裁剪并导致 Evidence 失效；只摘录 state class 字段或 LangGraph 概念不算完成参考复核。

### 能力范围

- 自然语言 turn 投影为 typed TaskDelta；确定性/保守 adapter 是必需 fallback，若使用模型需单独通过 outbound 门；
- 建立新的 versioned TaskState family 和首版 in-memory task-boundary adapter；禁止扩展 `m37-thread-v2` 承载新字段，legacy manager 继续独立服务旧回归；
- 受控 merge 生成新 TaskState，保留前后 fingerprint、字段级变化、pending question 与 Evidence invalidation reason；
- 支持 continue、modify、ask existing result、add Evidence requirement、switch、correction、cancel 的合同语义，但首个纵向 slice 只需按真实 Scenario 逐步接入执行能力；
- 建立 typed turn/event ledger 和 Task boundary；不再依赖一次 signed follow-up 的固定 action/field 模板表达所有多轮；
- node-level Context Builder 从 Router/Turn Understanding/SQL/Controller 等本片实际调用节点开始建设，记录允许字段、来源、identity、预算与实际入模投影；
- 继续继承 M37 Evidence reuse/invalidation，不用新 TaskDelta 绕过重查/重授权；
- 在同一 `/api/query` 上增量接入新 task continuation，并按 §4.7 完成旧 clarification/follow-up 与新 task payload 的互斥、兼容和稳定错误投影。

### 主要交付物

- Task runtime 合同及安全 merge/invalidator；
- 可连续消费自然语言 turn 的统一 turn seam；
- request/response/Trace/Eval compatibility matrix 与旧字段弃用但可用说明；
- typed turn/event ledger 与首批 node context projection；
- T1–T2 sequence、独立 correction/switch/cancel contract，以及 provider/outbound 保守降级 case；
- Agent Eval 的 TaskDelta、State transition、Evidence validity 与 Context assertions。

### 完成标志

1. T1→T2 以自然语言 turn 连续推进并正确使旧 SQL Evidence 失效、重新取证；不得只用直接注入 TaskDelta 冒充自然语言 seam；
2. correction 由独立 Scenario 证明，不通过预写北极星整句或关键词模板硬编码；
3. TaskState、TaskDelta、turn/event 和实际 node context 都是 Eval 可直接读取的 typed 事实；
4. 模型未授权、不可用或解析不确定时，不自由猜测 delta；
5. switch/cancel 不继承旧任务的 pending action/Evidence；
6. 仍不宣称同次运行 Observation-driven Loop、持久恢复或 Compact 已完成。
7. 三层证据分账闭合：直接 TaskDelta 测试证明 merge/invalidation，确定性自然语言 fixture 或可控 adapter 证明 turn seam，若正式 adapter 使用模型则另有一次经授权的 real-provider T1→T2 E2E；三者不互相替代。

### 决策门 G4B-1

若 Turn Understanding 需要模型，确认 receiver、purpose、data class、字段、fallback 和真实 E2E 授权；否则首版保持本地/确定性。无论选择哪种 adapter，B1 都必须真实消费自然语言 turn；模型方案的 real-provider showcase 与 deterministic required Gate 分账，但属于该方案的 E2E 交付证据。该选择不能改变 TaskDelta 的 adapter-neutral 合同。

## 9. B2：顶层 Evidence-driven Bounded Decision Loop

### 目标

让顶层 Controller 真正消费 Observation 并在同次任务运行中选择下一动作，使 Agent 能完成原因分析、跨 Tool 补 Evidence 或停止，而不是依赖固定 DAG 或要求用户每次手工触发下一步。

### 参考项目小结

- 定点复核 `ARAG-GRAPH/STATE` 的 conditional edges、Tool/iteration counter、fallback/collect-answer 终止和已执行 retrieval key，借鉴“边读取状态并且每条回边都有停止”；不照搬 LLM 自由 tool call、强制首次搜索、开放 query rewrite、fan-out 或 fallback 生成答案。
- 定点复核 `DATAAGENT-GRAPH` 中 Planner/Executor/repair/human-review 的显式 conditional edge，借鉴深模块与固定控制边界；不将其平台级 PlanExecutor、Python 执行或修复循环搬入 DataPilot。
- B2 的参考结论必须用 DataPilot 的 `Observation → eligible Action → EvidenceDelta → Progress/Termination` 通路重述，并指出移除哪个 Observation/边后能力应失败；只说“参考项目也用 LangGraph”不构成设计证据。

### 能力范围

- 随真实消费方建立 first-class Action、Budget ledger、EvidenceDelta、Progress/Termination；
- 在新的 agent runtime family 内加入 Loop；legacy M35–M38 runtime 保持原图与原 Tool/branch 预算，由旧 fixture 显式 pin，不通过修改旧断言适配新能力；
- 加入受控回边和 allowed action catalog，覆盖至少一种 SQL/全局补 Evidence、跨 Tool 转换、clarification boundary、no-progress 与 budget stop；
- T3 的“为什么 8 月比 7 月上涨”必须由同口径 SQL Observation 触发原因分析/补证据动作；T4 顶层能从 SQL 任务受控增加 Document requirement 并转为 Hybrid，即使此时 RAG 内部仍走 Pipeline/fallback；
- T5 correction 在整合路径使受影响 Evidence 失效并重新取证；
- clarification 在当前 invoke 结束，不保存执行栈；下一 turn 从 TaskState 重新进入 Decision Loop；
- decision proposal 如使用模型，必须结构化、单独 outbound，并由确定性 Controller 审核。

### 主要交付物

- 顶层 action/progress/termination 与多维总预算合同；
- Observation-driven Graph 控制回边及停止路径；
- T3、顶层 T4、整合 T5 的 sequence evidence；
- recoverable/clarification/no-progress/budget/unsafe/external failure contract；
- Trace/Eval 的 action trigger、budget before/after、EvidenceDelta 与 termination 投影。

### 完成标志

1. T3 能在同次任务运行中从 Observation 选择允许动作并获得新 Evidence 或正确停止；
2. T4 顶层 SQL→Hybrid 变化不依赖关键词重新开启一张无关任务；
3. 所有路径有确定性预算和终止，移除控制回边后相关能力测试会失败；
4. 顶层只表达缺失 Evidence requirement，不指定 RAG 内部 rewrite/expansion；
5. 不可恢复、ACL、outbound deny 和 no-progress 不产生重复 Tool call；
6. Response/Trace/Eval 的四轴、action、Evidence 与预算来自同次运行。
7. 新 Agent family 的多动作合同与旧 M31–M40 legacy 回归同时通过，旧 artifact 和 assertion 未被改写。

### 决策门 G4B-2

确认首版 allowed action catalog、父预算维度和各动作准入事实；具体数值由 module plan 和 contract Scenario 固定。若采用模型 action proposal，另行确认 outbound 与真实 E2E 范围。

## 10. B3：RAG 失败漏斗与 Action-level Evidence

### 目标

产生 M39 当时缺少的新 Evidence：知道 RAG 失败发生在哪一层，并证明哪些动作只有在首次 Observation 后执行才会稳定新增有效 Document Evidence。

### 参考项目小结

- 定点复核 `ARAG-CHUNK/TOOLS/STATE/EVAL`：标题 parent、child search、parent expansion 和真实 Tool context 证明检索单元与回答上下文可以分层；但顺序 parent ID、固定字符参数、字符串 Observation、LLM 自主扩展和 notebook 评分都不是 DataPilot action card 的正向合同。
- 定点复核 `DBGPT-RESOURCE/EVAL`，借鉴 chunk/reference 同步返回与 retrieval/answer 分评；对照 `DBGPT-TOOL` 仅取第一个 resource、编号正文/错误字符串直接进 Observation 的反例，确保失败层与 reference identity 不会在诊断时丢失。
- **禁止在玩具规模上选 action**：B3 必须同时检查参考实现的 corpus 假设和 DataPilot business/M34 的文档规模、长度、多文档题、Tool 延迟及失败漏斗。参考源码只能证明 action seam 可实现，不能证明该 action 在当前 corpus 有效；准入仍必须由真实 diagnostic Evidence 与可比预算决定。
- 若 action 需要改 chunk/release/corpus，追加复核 `WREN-INDEX/WATCH` 和 `DATAAGENT-REPLACE`，但仍使用 DataPilot 独立 candidate identity、不可变 artifact 和 active pointer 决策门。

### 能力范围

- 分开记录 retrieved、selected、generation-visible、Composer/support、cited 和 answer correctness/completeness；support 是回答诊断，不新增第五个 Evidence stage；
- 在 diagnostic/dev 上单变量比较候选：requirement split/subquestion、受控 rewrite、基于进展的 parent/neighbor expansion 等；固定一次的 parent 补取、rerank、hybrid retrieval 仍作为 Pipeline 单变量实验，不为使用 Subgraph 强行包装成 loop；
- 每个候选动作必须冻结 trigger、expected/actual EvidenceDelta、预算、延迟、ACL/outbound、失败与停止边界；
- 每轮 diagnostic campaign 必须在运行前冻结候选动作清单、单动作预算、总预算、最大诊断轮次和 review point；达到边界立即停止并出具结论，禁止以“继续找”为由无限延期；
- 优先使用北极星双政策 business case，同时利用 M34 external dev 失败结构检验可迁移性；M34 的 120 题 historical regression set 只承担历史回归，新 sealed decision reserve 在 action catalog、Prompt 与参数冻结前不得解封或逐题消费；
- 全局至少两种动作不要求在所有 corpus 都生效，但不能仅由“business 固定动作 A + external 固定动作 B”凑数；每张 action card 必须声明适用 runtime/corpus、失败层和 trigger，且至少一个 runtime/corpus 要在不同真实 Observation/Scenario 下分别证明两种动作，至少一种动作必须支撑 business T4；
- 如果候选动作未形成合格 Evidence，只能在已冻结 campaign 预算内补 diagnostic Evidence或放弃该动作，不能降低准入标准，也不能为凑动作数量制造 corpus failure。

### 主要交付物

- multi-document/RAG funnel 与安全逐题失败分类；
- 至少两种合格恢复动作的 action card 和单变量 diagnostic 报告；
- 有界 diagnostic campaign protocol、预算消费和 review/no-go 记录；
- business canonical recovery case 与 external diagnostic 对照；
- 冻结的 Pipeline/Subgraph sealed decision reserve protocol、污染账本、可比预算与 runtime identity；
- 项目外不可变大 artifact 的保存方案，以及仓库内 identity/SHA-256/汇总/安全失败切片。

### 完成标志

1. 失败可定位到 retrieval、selection、generation context、support、citation 或 answer；
2. 至少两种不同动作各自有正确触发、实际 Evidence gain、额外成本和安全边界；至少一个 runtime/corpus 能在不同真实 Observation/Scenario 下分别准入两者；
3. 动作选择需要读取 Observation，移除该 Observation 后不能合法作出同一决定；
4. 每次运行由 runtime/corpus、ACL 与 Observation 形成 eligible action set，错误、不适用、no-progress、duplicate、unsafe action 能被正确拒绝，`stop` 始终可用；
5. 新 decision reserve 未参与动作、Prompt、参数选择，污染与退出规则明确；M34 120 题只作为 historical regression set；
6. 未把 M39 `no_go` 改写为错误，而是用新实验补齐其明确缺口。
7. diagnostic campaign 在冻结预算和 review point 内结束；不足两种动作时形成显式暂停/重规划结论，没有无限“继续寻找”。

### 决策门 G4B-3

只有满足上述 action-level 准入的动作才能进入 B4 allowed action catalog。每次 campaign 到达冻结预算或 review point 后必须停止：两种动作合格，且至少一个 runtime/corpus 能用不同真实 Observation/Scenario 分别准入两者，才进入 B4；若只有一种/零种合格，或两种动作只能按 runtime 静态分摊，则形成正式 review/no-go，暂停 B4 并由用户决定更换真实 Scenario/corpus、调整阶段排期或显式修改最终范围。该 review 是调查闭环，不等于 B3/B4 或 Phase 4B 能力完成；在用户未修改最终范围前，不能用“一种动作 + stop”或“每个 runtime 各固定一种动作”替代既定目标，也不能无界继续寻找。

## 11. B4：Bounded Agentic RAG

### 目标

在不改变 Knowledge Tool 对上层语义、Evidence/ACL/AnswerFlow 或顶层控制权的前提下，完整交付可运行、可回退、可追踪的 experimental RAG Subgraph，并用可比 A/B 决定是否默认化。

### 参考项目小结

- 定点复核 `ARAG-GRAPH/STATE/TOOLS`，借鉴主图/子图分工、child search 与 parent expansion 独立动作、retrieval key/context 去重及显式 Tool/iteration stop；不照搬 `MessagesState`、强制搜索、开放 LLM 动作、字符串 Tool output、子图答案或其预算参数。
- 定点复核 `DBGPT-TOOL/RESOURCE` 和 `GUSTO-WORKFLOW`，用“纯正文 Observation/末尾拼 sources”与 structured references 的差异检查 Subgraph 是否丢失 Evidence identity；不照搬 PostgreSQL→Milvus级联、自动多后端 fallback、“任一命中就 complete”或最后去重文档名作 citation。
- B4 必须把参考项目的实际控制流与 DataPilot 的父子预算、eligible action set、Shared Gate/Composer/Citation 唯一所有者逐项对照，并在 business 与大规模 reserve 上分别验证；只跑通参考项目的 toy demo 或 DataPilot 单条 T4 不算完成。

### 能力范围

- Subgraph 在首次 retrieval Observation 后，按 runtime/corpus、ACL、Observation 与剩余预算形成 eligible action set，并从其中选择恢复动作或停止；全局 catalog 至少两种动作，至少一个 runtime/corpus 能在不同真实 Observation/Scenario 下分别选择两种动作，不要求单题同时暴露两者；
- action set 只含 Observation-driven 多步取证；Evidence merge/deduplicate、Progress/no-progress、子预算消费与确定性终止闭合；
- 顶层父预算覆盖所有子图 retrieval/model/context 动作，子消费回写总账；
- Subgraph 不调用 SQL、不生成答案、不决定产品四轴、不放宽 ACL/outbound、不复制 Shared Gate/Composer/Citation Validator；
- Pipeline 与 Subgraph 通过同一 Knowledge Tool/AnswerFlow 合同，Pipeline 长期保留 baseline/fallback；
- business T4 演示与新 sealed decision reserve A/B 都必须完成，不能只在 external benchmark 或只在 demo 成功；M34 historical regression set 另行报告，不冒充新决策证据。

### 主要交付物

- bounded RAG Subgraph experimental adapter；
- Pipeline/Subgraph 同合同 dev、sealed decision reserve、historical regression、contract/security 视图；
- business canonical Observation→Action→Evidence gain→Answer/Stop 证据；
- 父子预算、无双循环、ACL/outbound/prompt injection、fallback 与 Trace/Eval 回归；
- default/experimental/fallback 决策记录。

### 完成标志

1. 全局 catalog 至少有两种合格动作；每次首次 Observation 能正确形成 eligible action set 并选择动作或停止，且至少一个 runtime/corpus 通过不同真实 Scenario 分别证明两种动作的 Observation-driven 选择、错误动作排除与 no-progress stop；
2. 每次恢复可看到 EvidenceDelta、budget consumption、progress/no-progress 和终止；
3. 顶层与子图不会对同一失败各循环一次；
4. Pipeline/Subgraph 在同 corpus、合同、AnswerFlow、provider 条件和可比预算下完成新 sealed decision reserve A/B；reserve 的首次解封、访问和退出状态可审计；
5. experimental adapter 即使不切默认也完整可运行、可回退、可追踪；
6. 没有稳定净收益时 Pipeline 继续默认，不能把“实现 Subgraph”写成“效果提升”。

### 决策门 G4B-4

**实现与默认化分离**：B4 实现是 Phase 4B 硬交付；是否切换默认由新 sealed decision reserve 的 Evidence/answer/citation/stop 净收益、额外调用、延迟、成本和安全等价性决定，并需用户确认；M34 historical regression set 只提供历史连续性，不能单独切默认。默认、experimental-only、fallback 三种结论都必须有正式记录。

## 12. B5：Durable Task State

### 目标

把已稳定的 TaskState/turn boundary 语义落到真正持久的 checkpoint，使同一任务在重启、多 worker、并发和重复请求下仍能安全恢复。

### 参考项目小结

- 定点复核 `DATAAGENT-GRAPH` 的 `mysqlCheckpointSaver/memoryCheckpointSaver/nl2sqlGraphCompileConfig`，借鉴 checkpointer 作为可替换编译依赖、使用 Graph serializer 和 interrupt point 的接线 seam；源码只证明“接了 MySQL saver”，没有自动证明 owner/tenant/role、TTL、CAS claim、重复提交、隐私或清理合同。
- 对照 `ARAG-GRAPH` 默认 `InMemorySaver + interrupt_before`，将其作为“能暂停不等于能持久恢复”的反例；B5 不保存 Graph 执行栈，而是从 DataPilot 的安全 task boundary 重进 Decision Loop。
- B5 的参考阅读必须沿一次 write/claim/version bump/resume/clear 通路追到存储语义或明确其未覆盖处，不能看到 saver 构造器就宣称 durability 设计已有参考依据；参考项目缺口必须由当时依赖官方文档、存储后端能力与 DataPilot 并发测试补齐。

### 能力范围

- 通过稳定 task boundary interface 提供 in-memory 与 durable adapter；不提前规定 MySQL/Redis/其他后端，由 module plan 根据事务/CAS、部署和清理要求选择；
- 存储层条件更新保证 claim/version bump/clear/TTL，覆盖重复提交、并发旧版本与 worker 竞争；
- 保存 TaskState、必要 turn/event、EvidenceRef/validity、预算/termination 和 Compact reference 的最小集合，不保存完整业务结果或执行栈；
- 进程重启后从任务边界重进 Decision Loop，重新授权并复核 Evidence；
- schema migration、incompatible version、TTL/clear/tombstone、存储不可用和数据清理都有保守语义；
- 历史 `m37-thread-v2` 继续用于回归，不伪造在线迁移。

### 主要交付物

- durable checkpoint adapter 与 schema/lifecycle contract；
- restart/multi-worker/concurrency/duplicate/version/TTL/clear 测试环境与 Agent Scenario；
- checkpoint 安全投影、审计、清理与失败降级；
- in-memory/durable adapter 行为等价回归及旧 M36/M37 compatibility view。

### 完成标志

1. 北极星可在重启后继续，TaskState/TaskDelta/Evidence validity 与 route/action 不漂移；
2. 多 worker 同 version 只有一个 claim 成功，不重复 Tool call；
3. wrong owner/missing、role/tenant 变化、TTL、clear 和 incompatible version 有可预测且无侧信道结果；
4. 旧 Evidence 恢复后始终重新检查 freshness/revision/purpose/ACL；
5. 持久存储不可用不会回退成不受控新任务或重复执行；
6. 另一种内存 saver 不被宣传为 durable upgrade。

### 决策门 G4B-5

在实现前确认存储后端、事务/CAS 能力、schema migration、TTL/清理、数据分类、保留期、加密/访问边界与故障降级。若需要新增数据库结构或默认服务，按项目规则单独取得用户确认。

## 13. B6：Context Compact 基础版与全阶段集成

### 目标

在 node-level Context Builder 和 durable typed ledger 稳定后，加入可验证的结构化 Compact，并用同一条连续任务完成全阶段验收。

### 参考项目小结

- 定点复核 `ARAG-STATE` 中 `_retrieval_contexts`、`should_compress_context`、`compress_context`、retrieval keys 和 recent-history 处理，借鉴触发前计算 context 规模、保留已执行搜索/parent 身份、压缩后防重复动作；不照搬 LLM 自由摘要、将 Tool 正文整段注入 summary、删除历史消息后以摘要作 authority 或其 token 阈值。
- 结合 `ARAG-EVAL` “保存实际 answer/context 再评分”的思路，但 compact 验收必须是 DataPilot typed behavior equivalence，包括 goal、constraint、Evidence validity、permission、action/budget/termination，不是摘要文本相似度或最终答案逐字相同。
- B6 的阅读证据必须追踪压缩前哪些原始事实被删除、压缩后哪些字段成为节点真实入模 context，并标记参考实现无法证明的高风险保真项；只阅读 prompt 或 summary 函数不足以支撑 Compact 设计。

### 能力范围

- 正式配置按 turn 数与 context/token budget 触发；contract test 可用显式、带 identity 的低阈值或 extended sequence 强制触发，不能静默改生产阈值；
- Task Compact 由 typed TaskState/turn-event 确定性投影和裁剪形成，携带来源 turn range、version/fingerprint、trigger 与高风险原始 reference；
- Compact 与少量 recent raw turns、当前 turn 共同组成 node Context；每节点仍应用自己的 projection/预算；
- compact 后重新核验 active Evidence validity，不把摘要当 authority；
- compact 失败或不兼容时保守保留未压缩的最小安全状态、澄清或停止，不丢关键事实；
- 最终整合 T1–T5、RAG Subgraph、重启、多 worker 和 compact，完成 Trace/Eval/演示闭环。

### 主要交付物

- Task Compact schema、builder、trigger、identity 与失败降级；
- compact 前后 typed behavioral equivalence assertions；
- extended north-star sequence 与完整 Phase 4B assurance/capability matrix；
- 项目展示材料：答案→citation/Evidence→Observation/Action→Budget/Context/State 的可回查链；
- Phase 4B 技术验收、人工演示与面试叙事。

### 完成标志

1. 每个节点只收到合同允许的最小 Context，实际入模投影可直接 Eval；
2. compact 前后 goal、关键约束、pending question、Evidence validity、route/action、权限、预算和终止行为等价；不要求自然语言答案逐字相同；
3. 时间、金额、指标、否定、政策例外与 Evidence identity 未被不可验证摘要覆盖；
4. compact failure 有保守降级，高风险原始 reference 可追溯；
5. 同一连续任务贯通 TaskDelta、顶层 Loop、SQL/RAG/Hybrid、RAG Subgraph、durable resume 和 Compact；
6. 配套非 happy-path required Gate 全部闭合，不存在权限绕过、无界调用、双循环或 compact 后语义漂移。

### 决策门 G4B-6

确认正式 compact trigger、recent raw turn 窗口、TTL/保留、安全 reference 与 debug artifact 策略。基础版不得因模型摘要效果不稳定而推迟交付；正式能力以 deterministic typed compact 为准。

## 14. Agent Scenario Eval 与安全门

### 14.1 独立合同与一次 sequence 执行

- Phase 4B 建立新的版本化 Agent Scenario family；不向 M27、M31–M40 或 M34 历史 artifact 补字段。
- 一条 sequence 执行一次；同一 ExecutionEvidence 支撑每个 turn 的 TaskDelta、State transition、Evidence validity、route/action、Tool call、node Context、Budget/Progress/Termination、checkpoint/Compact、ACL/outbound 和最终回答断言。
- completed artifact 进入报告/Gate 前执行 closed-world 校验：selected sequence、turn、action、replicate、assertion、seed/caller/release/runtime/policy identity 必须恰好匹配。
- expected clarification、insufficient evidence、partial、blocked、no-progress 和 budget stop 是可观察的正确行为；provider 不可用或证据缺失不能伪装成业务错误。

### 14.2 Scenario 分集

| 分集 | 用途 | 纪律 |
|---|---|---|
| north-star canonical | 持续展示纵向能力增长 | 每片新增跑通一段，但不能单独承担泛化证明 |
| required contract/security | 权限、预算、停止、Context、并发、恢复、Compact | 可重复运行，承担硬门 |
| diagnostic/dev | 失败归因、动作选择、参数开发 | 可迭代；结果不能单独切默认 |
| sealed decision reserve | Pipeline/Subgraph、模型/策略默认决策 | 使用新的 identity；实验前密封，记录首次解封与访问；一旦用于动作、Prompt 或参数选择即退出 decision set |
| historical regression | M34 既有 120 题及其他已解封集合的历史连续性 | 可做回归和退化检测，不得再称未污染或单独承担默认切换证明 |
| real-provider showcase | 少量真实自然语言交互与项目演示 | 与 deterministic Gate 分账；按 runbook 单次精确授权 |

### 14.3 Required Gate

Phase 4B required assertions 至少覆盖：

- TaskDelta schema/merge、TaskState fingerprint 与 switch/cancel/correction；
- Evidence reuse/invalidation、revision/ACL/purpose/freshness；
- allowed action、trigger、Observation、EvidenceDelta、no-progress 与 termination；
- 顶层/子图父子预算、重复 Tool call 和双循环禁止；
- Router/SQL/RAG/Subgraph/Composer/Controller 的实际 node Context allowlist 与预算；
- durable owner/tenant/role、CAS claim、restart、multi-worker、TTL、clear、version conflict；
- Compact provenance、关键事实保真、行为等价和失败降级；
- SQL Guard、Document ACL、prompt injection、outbound 默认拒绝与非泄露；
- legacy/agent runtime family 选择、旧/new payload 互斥、旧请求兼容和稳定错误；
- API/Trace/Eval 同源、resolved runtime identity 和 closed-world 完整性。

### 14.4 质量与净收益视图

RAG/Answer 继续分开报告 retrieval coverage、selected/generation-visible coverage、correctness、support/faithfulness、completeness 与 citation。Loop/Subgraph 另报告 trigger precision、recovery success、Evidence gain per extra call、duplicate/no-progress、Tool/retrieval/model calls、budget exhaustion、latency/token/cost 与 unsafe recovery prevention。

实现 Subgraph 不等于质量提升；默认切换必须证明稳定净收益。真实 provider 抖动不能覆盖 deterministic 安全失败，deterministic case 也不能冒充开放自然语言质量。

### 14.5 Artifact 保留

- 可安全提交的 contract/report、identity、SHA-256、汇总和逐题失败分类进入仓库事实源；
- 含大上下文或敏感数据的逐题 artifact 不长期只放 `.agent_work/temp/`，应进入项目外不可变评测存储，并由仓库 manifest 指向；
- 具体介质、保留期、访问和清理策略在 B0/B3 module plan 冻结；默认长期 artifact 不保存完整 Document 正文、SQL rows 或模型 Thought。

## 15. 阶段交付物与总完成标志

### 15.1 阶段级交付物

- Evidence-driven top-level Decision Loop 与多维父子预算；
- bounded RAG Subgraph experimental adapter、Pipeline fallback、新 sealed decision reserve A/B 与 historical regression 视图；
- TaskState/TaskDelta/turn-event 自然多轮 runtime；
- durable checkpoint 与 in-memory compatibility adapter；
- node-level Context Builder、实际入模投影与 Task Compact 基础版；
- 与 legacy 隔离且绑定实际 recipe/content/config 的 versioned seed/oracle profile、最小 demo caller、business RAG recovery case 与泛化后的 Hybrid operator；
- Phase 4B Agent Scenario catalog、runner/artifact、required Gate、quality/net-benefit view 与 durable artifact manifest；
- 北极星/非 happy-path 演示、Trace 回查链和 capability matrix。

### 15.2 Phase 4B Definition of Done

Phase 4B 只有在以下条件全部满足后才能收工：

1. 六项最终能力全部交付，不存在被改写成“未来按需优化”的持久状态、Compact 或 Subgraph；
2. 北极星从 T1 连续执行到 T5，并分别通过 restart/multi-worker 与 compact extended variants；
3. 顶层 Loop 由 Observation/EvidenceDelta 驱动，所有动作有预算、进展与确定性终止；
4. RAG Subgraph 的全局 catalog 至少有两种合格动作，每次运行按 runtime/corpus、ACL 与 Observation 形成 eligible action set 并选择动作或停止；至少一个 runtime/corpus 在不同真实 Scenario 下分别证明两种动作，Pipeline 保留，默认决策有新 sealed decision reserve 证据；
5. 自然多轮支持任务修改、追问、补 Evidence、correction、switch、cancel 与受控 route 变化，不是固定字符串模板；
6. durable checkpoint 通过 owner/tenant/role、CAS、restart、多 worker、TTL、clear 和不兼容版本门；
7. node Context 与 Compact 可直接 Eval，compact 前后关键 typed 行为等价；
8. ACL、SQL Guard、outbound、Evidence/citation、四轴、非泄露与父子预算没有被新循环绕过；
9. Agent Scenario required Gate 和显式 pin legacy runtime 的现有 M31–M40 原合同回归同时通过；旧 assertion/artifact 未被改写，真实 provider showcase 与 deterministic Gate 分账记录；
10. 每个纵向切片完成 `finish-module → finish-docs → 用户人工检查 → accept-module`，阶段末完成完整人工演示与文档收口。

## 16. 明确不做的范围

以下边界是为了保持企业 Agent 可控，不削弱本文已经承诺的最终能力：

- 不在运行时自动生成、注册或执行新 Tool，不允许未登记动作进入 allowlist；
- 不做无限 Agent Loop、自由 Thought Loop、开放研究型 ReAct、任意 fan-out 或无界子任务树；
- 不提供自动修改数据库/业务数据、执行任意 Python/Shell、发消息等高风险副作用 Tool；
- 不建设开放领域 ChatGPT clone、通用自主规划器、多 Agent 系统或动态 Skills/Connector 平台；
- 不建设跨会话长期记忆、用户画像、偏好召回或永久聊天历史；durable checkpoint 只服务同一有 TTL 的任务；
- 不把生产 SSO/OAuth/JWT、企业目录、真实 connector ACL/同步/删除传播纳入主线；Phase 4B 继续使用明确标记的 demo/test caller seam，生产认证另立项目；
- 不要求 LangFuse Cloud、GraphRAG/Neo4j/LightRAG、OCR/多格式、完整知识管理平台或独立 Eval 平台；
- 不以 semantic/vector、rerank、parent/child、远程 Router/Composer 的标签作为阶段完成条件；它们只有作为已证明动作或单变量候选时进入；
- 不要求 RAG Subgraph 必须切默认，但必须完整实现、可运行、可回退、可评测。

## 17. 外部参考项目使用地图

Phase 4B 参考顺序固定为：**本文合同 → 最新 state/代码/失败 Evidence → `docs/phase4-reference.md` 能力卡 → 外部源码定点复核**。参考项目只提供局部 seam、反例和实现证据，不能替代 DataPilot 的 ACL、outbound、四轴、Evidence 或 Eval 决策。

### 17.1 禁止走马观花式源码阅读

外部参考是为了暴露设计假设和缺口，不是为 module plan 填一张“已阅读”表。不规定通读整仓、固定文件数或行数，但每个里程碑的 module plan/notes 必须留下足以让后续 AI 复核的最小证据：

1. **先有问题，后有入口**：写明当前 DataPilot 失败 Evidence/设计问题，再选 reference ID 和源码符号；不得只读 README、analysis、本文小结或搜索命中片段就宣称已复核。
2. **追到能回答问题的真实通路**：至少查看直接实现，并按风险补读必要的 caller/callee、state/edge、存储/测试或数据入口，直到能说清输入、状态变化、输出、失败/停止与实际保证边界。深度由决策风险决定，不为形式强制阅读无关文件。
3. **必须检查规模与代表性**：回答参考项目和 DataPilot 在 corpus/数据量、文档长度、问题多样性、调用链、并发/持久性、安全和 Eval 上的差异。小 demo 没有出现某类失败，只能记为“未覆盖/不可观测”，不得推断问题不存在。
4. **形成可执行取舍**：notes 至少记录源码直接事实、借鉴 seam、DataPilot 适配、明确不照搬、参考未覆盖项和验证方式。结论必须能改变或确认 interface、边界、Scenario 或实验；简单罗列项目名/函数名不算完成。
5. **承认外部覆盖空白**：现有项目不足以支撑持久化、Compact、ACL/outbound 或真实规模结论时，按问题补读当时依赖官方文档、新参考项目或 DataPilot 自身实验；不得从“没看到”推导“不需要”。

M29–M33 的教训是：**每个模块都读过参考源码，不等于阶段底座已被验证**。当时定点复核帮助建立 Evidence、Tool、citation 和发布 seam，但 11/22 条短知识无法诊断大 corpus 召回和多文档回答，因而额外开 M34 引入 EnterpriseRAG-Bench 才暴露稳定失败结构。Phase 4B 每个里程碑的参考小结都必须与其实际 Scenario/Eval 规模联动，不得再把 interface 复核冒充成能力底座验证。

### 17.2 能力快速索引

| 能力 | 优先参考与源码入口 | 主要借鉴 | 明确不照搬 |
|---|---|---|---|
| 顶层 Loop / 状态 / Context | `ARAG-GRAPH/STATE`：`agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph`、`graph_state.py::AgentState/append_unique`、`nodes.py::should_compress_context/compress_context` | conditional edge、Tool/iteration count、去重 context、显式压缩前后状态与停止 | `MessagesState` 全历史、强制首搜、开放动作、LLM 自由 rewrite/summary、默认 InMemorySaver、其预算/阈值 |
| RAG recovery actions | `ARAG-TOOLS`：`agentic-rag-for-dummies/project/rag_agent/tools.py::ToolFactory._search_child_chunks/_retrieve_parent_chunks`，并结合上述 graph/nodes | 把首次检索和按 Observation 扩上下文拆成独立动作，保留已执行动作与 context | 默认 parent expansion、顺序 parent ID、字符串 Tool Observation、fallback answer、开放循环 |
| 顶层固定编排与持久接线邻近例 | `DATAAGENT-GRAPH`：`DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java::nl2sqlGraph`；持久化定点看同文件 `mysqlCheckpointSaver/nl2sqlGraphCompileConfig` | 深模块接固定 StateGraph、conditional edge、checkpointer 作为可替换运行依赖的思路 | Java 平台结构、完整 PlanExecutor/repair/human-review、把“有 checkpointer”当成 owner/TTL/CAS/隐私已解决 |
| Hybrid 汇合与失败形态 | `DATAAGENT-GRAPH` 上述入口；`GUSTO-WORKFLOW`：`GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py::local_search/finalize` | 多数据面结果分开保存、末端统一汇合、核心结果与增强失败分层 | 拼接自然语言子答案、末尾 `sources` 冒充 citation、任一后端命中即 complete、自动多后端 fallback |
| Evidence/reference 连续性 | `DBGPT-TOOL/RESOURCE`：`DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py::make_knowledge_retrieve.knowledge_retrieve`、`DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py::RetrieverResource.get_resources/_get_references` | 对比纯正文 Tool output 与结构化 reference，检查 source identity 是否贯穿 | 错误/正文字符串直接进入 Observation、只拼文档名、把 references 存在当 claim-level citation 闭环 |
| Eval | `ARAG-EVAL`：`agentic-rag-for-dummies/notebooks/evaluation.ipynb::query_rag/assert_saved_outputs_match_dataset/score_answer`；`DBGPT-EVAL`：`DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/retriever.py` 与 `answer.py` 的 retrieval/answer evaluators | 保存实际 Agent answer/context 后再评分，retrieval 与 answer 分层 | notebook 简单均值、空结果一律计零、为评分重跑 pipeline、LLM Judge 取代 required Gate/`not_observed` |
| corpus/release 若需新增业务语料 | `WREN-INDEX/WATCH`：`WrenAI/core/wren/src/wren/memory/index_backend.py::MemoryIndex.reset/LanceDBIndex.rebuild`、`watch.py::compute_fingerprint/poll_once`；`DATAAGENT-REPLACE`：`AgentVectorStoreServiceImpl.java::replaceDocumentsByMetadata` | source/derived 分离、成功后推进 observed state、替换失败清理 | mtime fingerprint 冒充 corpus identity、best-effort replacement 冒充原子发布/完整回滚、常驻 watcher/平台服务 |

B0–B6 分别按本文各里程碑的“参考项目小结”重新定点核对相关源码；进入 B2、B4、B5、B6 这些会改变控制权、循环、持久化或 context 的里程碑时，还必须核对当时依赖官方文档。module plan/notes 按§17.1 保留可复核证据。持久 checkpoint 和 Compact 是 `phase4-reference.md` 现有地图中覆盖较弱的新重点；若定点复核形成长期可复用结论，应同步更新 reference，而不是在 module plan 里复制一份公共参考地图。

## 18. 主要风险与控制

| 风险 | 早期信号 | 控制方式 |
|---|---|---|
| 把 Phase 4B 写成 Phase 4 返工 | 文档称 M39 no-go 为失败、称 M36/M37 未完成 | 明确历史基线；新能力使用新 family/里程碑，不改写旧 artifact |
| 新 Loop 静默打破旧单 Tool 合同 | M35–M38 fixture 跟随默认 runtime 变红或被放宽 | legacy/agent runtime family 分离并显式 pin；旧原合同与新 Agent Gate 同时通过 |
| API/state 演进靠字段猜测 | legacy follow-up 与新 task payload 同时出现或旧客户端语义漂移 | 单端点增量投影、payload 互斥、compatibility matrix、独立 TaskState family |
| TaskState 变万能大对象 | 各节点直接读取完整 State/历史 | typed node Context allowlist、实际入模 Eval、State/Context 分权 |
| TaskDelta 自由重写状态 | 模型一次返回整份 TaskState | delta closed-world、字段级 merge/invalidator、保守降级 |
| 顶层与 RAG 双循环 | 同一失败被两层 rewrite/retry | Evidence requirement 边界、父子预算、action owner 与双循环 assertion |
| Progress Policy 变第二个 Gate | 子图宣布“可回答”并生成答案 | Progress 只看 EvidenceDelta/可用动作；Shared Answer Gate 唯一 |
| 循环只增加调用 | Evidence 不变仍继续 | Evidence gain/no-progress/duplicate 指标与确定性停止 |
| 为 B4 伪造 RAG 失败 | 人工压低 top-k 或造语料证明 rewrite | B3 先观察真实 failure；单变量、business+external、sealed decision reserve 隔离 |
| B3 为凑两动作无限延期 | campaign 无候选边界、预算或 review 点 | 预注册候选与预算；到点停止并由用户显式重规划，no-go 不冒充能力完成 |
| 跨 runtime 各固定一个动作冒充选择 | action 只由 corpus identity 决定，不读取 Observation | 至少一个 runtime/corpus 用不同真实 Observation/Scenario 分别触发两种动作；验证错误动作排除与 stop |
| 已解封集合冒充未污染决策集 | 继续用 M34 120 题调动作后又切默认 | historical regression 与新 sealed decision reserve 分账；记录 identity、首次解封、访问和退出状态 |
| 实现 Subgraph 即宣称提升 | 只展示 Graph 图或 dev case | implementation/default 分离；新 sealed decision reserve、成本/安全等价 A/B |
| checkpoint 变长期隐私库 | 保存完整历史、rows、正文或 answer | task boundary 最小 schema、TTL/clear/retention、访问与清理门 |
| 应用层伪 CAS | 多 worker 同时 claim 成功 | 存储层条件更新与并发/重复 Scenario |
| Compact 造成语义漂移 | 月份、否定、Evidence identity 丢失 | typed deterministic compact、high-risk refs、behavioral equivalence Gate |
| 模型用途静默扩大出站 | Turn/decision/rewrite 继承 Text2SQL 许可 | receiver/purpose/data class/fields 独立规则、deny/fallback case |
| 北极星硬编码 | TaskState 出现 refund/month/channel 专用字段 | canonical + 非 happy-path catalog、adapter-neutral contract、删除测试 |
| Eval artifact 只在 temp | 清理后无法复核动作/默认决策 | 项目外 immutable store + repo manifest/hash/安全失败切片 |

## 19. 推进原则

1. **最终能力不缩水，施工按纵向切片**：每片必须推进北极星的一段并带非 happy-path 证据；早期不交付持久/Compact，不等于它们变成条件项。
2. **先真实 Observation，再允许动作**：Subgraph 是明确目标，但动作仍必须由失败 Evidence 准入；不把固定 Pipeline 机械拆成 Graph。
3. **控制合同随消费方建设**：TaskState/Context 在 B1 落地，Action/Budget/Progress 在 B2 由真实 Loop 消费，Compact 在 typed ledger 稳定后落地，不预造无消费者抽象。
4. **路线并行、施工交错**：Task/Loop 与 RAG Evidence 两条线逻辑并行；同一时间只维护一个 active module plan，完成并更新 state 后再选择下一片。
5. **默认切换与能力实现分离**：Subgraph 必须实现；是否默认、是否启用远程模型或检索增强仍由新 sealed decision reserve、成本、安全和用户确认决定；已解封历史集只承担回归。
6. **安全与 Eval 是能力组成**：ACL、outbound、Trace、Context、预算和 assertions 随每片进入，不留到 B6 补。
7. **失败也是正确输出**：clarification、insufficient evidence、partial、blocked、external unavailable、no-progress 和 budget exhausted 都必须可解释、可评测。
8. **保留实现空间**：roadmap 冻结 seam 和语义，不冻结类名、文件布局、框架 API、存储后端或参数；具体方案由当时代码、官方文档与 Eval 证据决定。
9. **每片完成后滚动规划**：按 `finish-module → finish-docs → 用户人工检查 → accept-module` 收口，更新 `AI_CONTEXT`/专项 state/技术历史，再依据最新证据制定下一 module plan。

## 20. 修订记录

### 2026-08-23：参考项目下沉到各里程碑与反走马观花门

- 重读 `phase4-reference.md` 并定点复核 WrenAI、DataAgent、agentic-rag-for-dummies、GustoBot 与 DB-GPT 对应源码，在 B0–B6 每个里程碑增加参考项目小结，明确借鉴、不照搬与本里程碑必须追踪的实际通路。
- 将 M29–M33 “逐模块定点阅读但仍未暴露大 corpus 底座缺口，后由 M34 补齐”固化为规模/代表性教训。新门禁止只看 README、analysis 或搜索片段，但不规定通读整仓、固定文件数或行数；验收改为能回答真实通路、规模差异、保证边界与 DataPilot 取舍。

### 2026-08-22：新旧合同衔接与决策门有界化

- 增加 legacy/agent runtime family 兼容合同：旧 M31–M40 原断言继续显式 pin，新 Loop 使用独立 versioned family，两类 Gate 同时通过。
- 明确 `/api/query` 采用增量 task-turn 投影，旧 clarification/follow-up 保留且与新 payload 互斥；B1 必须交付 API/Trace/Eval 兼容矩阵。
- 明确 B1 新建 TaskState family 和 in-memory adapter，B5 再接 durable adapter；禁止扩写 `m37-thread-v2`。
- 将 B3 改为预注册候选、预算、轮次与 review point 的有界 campaign；动作不足时暂停并由用户重规划，no-go 不冒充能力完成。
- 强化 B0 的 seed—政策可合成性、最小双角色 caller、真实 business RAG case 与非测试陷阱纪律；将 T4 改为自然业务问法，并记录当前直接点名双政策的原问法会一次取全。
- 将 B1 验收拆为 TaskDelta、确定性自然语言 seam、模型方案 real-provider E2E 三层证据，三者分账且不互相替代。

### 2026-08-22：北极星、seed、reserve 与 RAG 动作语义闭合

- 将 T1–T3 统一为按 `refunds.processed_at` 比较 7/8 月 `net_refund_amount`，并限制 T3 为证据支持的结构分解/归因。
- 要求 Phase 4B 使用与 legacy 隔离、绑定实际 recipe/content/config fingerprint 的 seed/oracle profile；修正现有 seed 月份表述并禁止数据身份漂移。
- 将 M34 已解封的 120 题改列 historical regression set，新增带污染、访问和首次解封账本的 sealed decision reserve。
- 明确全局 action catalog、runtime/corpus 适用范围与单次 eligible action set；要求至少一个 runtime/corpus 在不同真实 Scenario 下分别证明两种 Observation-driven 动作，不以跨 runtime 静态分摊或单题强行同时暴露两种动作验收。
