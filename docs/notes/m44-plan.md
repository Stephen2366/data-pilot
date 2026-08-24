# M44 Phase 4B B2 顶层 Evidence-driven Bounded Decision Loop 开发计划

> 能力里程碑：Phase 4B B2；本模块完整承担顶层 Evidence-driven bounded Decision Loop，不提前实现 M45/B3 的 RAG recovery action 准入、M46/B4 的 RAG Subgraph、M47/B5 的 durable state 或 M48/B6 的 Context Compact
>
> 主要问题：M43 的 Agent task 每个 accepted turn 仍只执行零或一次固定 Harness，无法在同一次运行中根据真实 Observation 判断缺失 Evidence、选择下一项已登记动作并以预算、进展或稳定原因停止

## 2026-08-24 post-finish defect repair addendum

本 addendum 只修复收工后真实 smoke 已证实的两个 M44 合同缺陷，不改变 B2 能力范围、G44-1～G44-4、默认模型、parent budget、数据库、Knowledge runtime 或 M45/B3 路线：

- 修复真实 `run_sql_tool` 数据库错误形状与 Harness dialect classifier 的 `blocked/passed` 条件错位，使精确 `DATE_TRUNC`/MySQL 错误能安全归一化为既有 allowlisted issue，并进入至多一次的 `repair_sql_evidence`；generic DB error、timeout、Guard deny 仍不可 repair。
- API Response 与 SQL 单路 JSONL Trace 可沿用历史兼容投影保存已经 Guard/授权的 `columns/rows`；action Observation、node Context、Scenario artifact 与 Hybrid Trace 不得携带完整 rows。所有公开/持久投影均不得包含底层驱动/SQLAlchemy 异常、stack 或凭据；详细异常只允许进入受控本地日志。
- 增加 real-shape deterministic regression，必须使用与真实 `run_sql_tool` 一致的 `blocked/sql_execution_error` 输入，同时覆盖 dialect allowlist、generic error 排除和 Response/Trace 非泄漏。

### Live Probe checkpoint

- Probe ID：`M44-PFIX-1`。
- 时点：**after defect code + focused deterministic tests / before broader regression and renewed finish-module**；它是本次重开开发的切片门，不把先前 post-module exploratory smoke 倒填为 Probe。
- 场景：通过真实 `/api/query`、Qwen 与 MySQL 只执行 canonical T1→T2 一次；T1 建立 task，T2 触发双月比较。不得延伸到 T3～T5、RAG Eval、held-out 或 sealed reserve。
- 观察：T2 是否得到 `120000/180000/60000` 或形成可解释安全失败、action/budget/usage 是否闭合，以及 Response/Trace 是否不含底层数据库异常文本。SQL 生成器已产出可信 MySQL 等价式时允许零 repair；只有真实执行形成 allowlisted typed dialect error 时才要求恰好一次 `repair_sql_evidence`，禁止为了展示 repair 故意执行无效 SQL。
- 预算：首次 attempt 原为最多 6 provider calls、20000 observed tokens。首次失败后，用户于 2026-08-24 确认方案 A 并批准本次修复 Probe 的首次+最小重验累计上限调整为 10 calls、35000 observed tokens；只允许具体修复落盘后额外重验 T1→T2 一次。单次已开始响应意外越界时保留 usage 后停止，不继续重跑、不换模型/backend。
- 决策：passed→`continue` 进入 broader regression；failed→`revise` 并先定位修复，只有具体修复落盘后才允许最小重验一次；依赖不可用→`inconclusive/stop`。所有 attempt 当时写入 notes。

### PFIX-G1：月份方言窄等价（已确认方案 A）

- 问题：首次 Probe 的 QueryPlan 使用 `DATE_TRUNC('month', processed_at)`，SQL generator 已正确翻译为 MySQL `DATE_FORMAT(processed_at, '%Y-%m-01')`，但 fidelity Gate 将其误判为排序表达式不等价，数据库与 repair 均未到达。
- 方案 A（用户确认）：在 SQL fidelity 深 module 登记精确 `month_bucket_dialect_translation`。只允许同一已解析 base column、计划粒度严格为 `month`、候选格式严格为 `%Y-%m-01` 的 `DATE_TRUNC → DATE_FORMAT`；继续检查方向、顺序、LIMIT、输出投影与其他表达式。
- 未选 B：故意保留无效 `DATE_TRUNC` 再等待数据库报错和 repair，会主动制造失败并浪费调用。
- 未选 C：保持误杀会让 canonical 双月比较继续不可用。
- 安全边界：这是窄等价登记，不是关闭 fidelity 或把 `sql_plan_contract_failed` 扩成 repair；不同 column/unit/format、额外函数或真实表达式变化必须继续 failed/indeterminate。

### PFIX-G2：repair 候选 A/B（已授权受控比较）

- 问题：第二次 Probe 已走到真实 `repair_sql_evidence`，但最小上下文 LLM 在修正 `DATE_TRUNC` 时删除了 `diff/change_rate`，随后被 projection Gate 正确拦截；不得通过放宽 Gate 或盲目重试解决。
- 候选 A：本地确定性 AST dialect repair。只对 typed `mysql_unsupported_date_trunc` 和可解析的单条 MySQL SELECT 生效，把月粒度 `DATE_TRUNC` 编译为 MySQL 等价 AST，不产生 repair provider call；其余 SQL 结构保持不变，之后仍重走 fidelity、Guard 与执行。
- 候选 B：增强 LLM repair prompt。除既有安全字段外，只增加已验证 QueryPlan 的 required output aliases，明确要求按原顺序保留；仍不得外发 raw DB error、rows、Schema、metric 或 join details，之后仍重走同一组 Gate。
- 隔离方式：两种策略均由服务端 closed-world 配置注入，客户端不能选择；旧 `llm_minimal` 暂时保持 production 默认。候选真实验证完成前不自动切默认，也不根据“实现方便”宣称胜出。
- 真实验证：A、B 各执行一次 canonical T1→T2，真实 `/api/query`、Qwen 与 MySQL、事务内官方 seed + rollback；不触碰 T3～T5、RAG、held-out、reserve，不换模型/backend，不为任一候选重复抽样。两次并非统计学 A/B，只用于发现真实链缺陷与比较工程行为。
- 用户授权：2026-08-24 批准两种候选均实现并各验证一次；连同既有两次 attempt 的累计硬上限为 18 provider calls / 65000 observed tokens，已开始的单次响应若越界则保留 usage 后停止后续候选。最终 production 选择仍需用户根据证据确认。

### PFIX-G3：收敛 repair 核心合同（已确认缩小版方案 A）

- 用户确认：2026-08-24 选择缩小版方案 A。首次 SQL 执行形成不可变的私有 repair snapshot，至少绑定已验证 QueryPlanStep、candidate SQL 与 typed issue；repair 复用该 snapshot，不再次调用 QueryPlan provider，也不换一份新计划验收。
- 默认选择：服务端 dialect repair 默认切为 `deterministic_ast`；客户端仍不能选择策略。`llm_minimal/llm_enriched` 只保留非默认候选代码，不继续真实抽样，不宣称质量胜出。
- 观测修复：SQL 已生成后在 fidelity/Guard/output 等后置 Gate 失败时，必须把已发生的 LLM evidence 与实际 repair strategy 写入 Trace，使 B2 action budget 能按真实发生计数；不得因失败结果而漏账。
- 明确不做：不为 canonical T2 硬编码 `diff/change_rate`，不建立通用 required-output 平台，不让 dialect repair 补业务计算或重写答案。QueryPlan 偶发少列是独立 planning 质量证据；本 addendum 只保证 repair 不再制造第二份漂移合同。
- 验证边界：先完成 deterministic snapshot/reuse/default/usage tests 与受影响回归。既有真实调用额度已耗尽且 usage 发现不完整，本切片不再运行 provider；是否另行真实重验必须在计量修复后重新授权。

### PFIX-G4：typed comparison completion（已确认方案 A）

- 用户确认：2026-08-24 选择窄范围的服务端 typed comparison completion。它只消费可信 TaskState/Evidence requirement 中的 `purpose=metric_comparison` 与 SQL Tool 已验证的结构化结果，不解析用户关键词，也不允许客户端指定计算方式。
- 完成合同：当且仅当结果能闭合为两个不同 period、同一数值 metric 时，确定性计算 absolute difference 与 change rate，并把这些派生事实纳入安全 Answer/Trace；输入不足、重复 period、非数值、基期为零或投影不匹配时保守停止/partial，不能仅因 requirement 已取得 EvidenceRef 就 `answer_ready`。
- 边界：不要求 QueryPlan/SQL 强制生成 `diff/change_rate`，不修改 SQL repair，不建立任意 required-output DSL，不支持多期趋势、任意公式或自然语言自由计算。completion 只消费已验证 SQL rows 并新增最小 typed 派生事实；API 及 SQL 单路 Trace 仍沿用已有 rows 兼容投影，不新增绕过它的任意 rows 通道。
- 验证：先用 deterministic tests 覆盖成功、形状错误、基期为零、安全投影、预算与 legacy 非比较路径；再跑受影响回归。新的真实 Probe 是否执行及额度仍需遵守 runbook，不能复用已结束 artifact 或自动重跑。

#### Live Probe checkpoint（已执行并通过）

- Probe ID：`M44-PFIX-G4-1`；时点为 **after G4 implementation + full deterministic regression / before renewed finish-module**。这是 G4 新增真实行为的开发门，不改写或复用已结束的 G3 artifact。
- 场景：真实 `/api/query` canonical T1→T2 恰好一次，Qwen/MySQL、事务内官方 seed + rollback；只观察 typed comparison completion，不执行 T3～T5、RAG、held-out、reserve，不换模型/backend、不重跑。
- 通过标准：T1=`120000`；T2 取得 `120000/180000` 并由服务端 completion 产生 `delta=60000/rate=0.5`，最终 Answer 同时表达差额与 50%，termination=`answer_ready`；API/Trace same-source、usage 完整、raw DB error 缺席、数据库恢复。依赖不可用记 inconclusive；任何语义/安全/计量失败均 failed/stop。
- 用户已批准独立上限 ≤5 provider calls / ≤22000 observed tokens；实际 `4 calls / 15762 tokens`，T2 给出 `120000/180000/delta=60000/rate=0.5`、`answer_ready`，raw DB marker=0，数据库回滚恢复，Gate passed。

## 1. 模块定义与范围判断

用户已冻结“B0–B6 各对应一个模块和一份 module plan”，因此 M44 完整对应 B2，并在模块内部按 M44-A～M44-G 形成一个可独立学习、演示和验收的纵向闭环，不再把 B2 拆成额外模块。

M44 完成后，用户能够从 M43 已跑通的 T1→T2 继续同一 task：

- T3 追问“为什么 8 月比 7 月上涨”时，系统先取得同口径原因分解 SQL Observation；只有 Observation 证明质量问题是有效增量结构后，才让商品维度补证据动作进入 eligible set，并在同一次 Graph invoke 内继续执行或按稳定原因停止；
- T4 增加退款政策 Evidence requirement 时，系统从 SQL 任务受控进入 Hybrid，先后取得 SQL 与业务 Document Evidence；业务检索仍是现有确定性 Pipeline，若漏掉基础政策则如实 partial / insufficient evidence，不把 B3/B4 尚未交付的 RAG recovery 伪装成已完成；
- T5 更正为渠道维度时，相关 SQL Evidence 失效并重查，Document Evidence 重新授权/取证后才能参与 Hybrid；
- 每个动作都能回查 trigger、requirement、budget before/after、Tool Observation、EvidenceDelta、progress/no-progress、node Context 和 termination，且 Response、Trace、Agent Scenario Eval 来自同一次执行事实。

本模块的外部 seam 仍是 M43 的 task turn interface；Decision Loop 是其内部的深 module。调用方只提交自然语言 turn 与 task identity，不提交 Action、Budget、State、route、Evidence 或 runtime。legacy 请求继续进入冻结的 M35–M38 Harness；M44 不把循环加进旧 Graph，也不放宽旧“单路至多一个 Tool、Hybrid 每支至多一次”的断言。

调查发现并已由用户确认的 runtime 冲突按方案 A 解决：普通非 task `/api/query` 继续保持 M44A 的 Enterprise semantic 产品默认；Agent task 的 Document action 由服务端 typed Evidence requirement 经 closed-world Knowledge Runtime Resolver 选择 `business_release` 或 `external_profile`。请求体不能指定 corpus、backend、collection 或 release。这样北极星 T4/T5 可读取 22 条业务退款政策，同时不撤销 M44A 的默认合同，也不合并两套知识分母。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| `run_task_turn()` 目前把自然语言 turn 合并为 TaskState 后只调用一次 `run_harness()`，并把 `graph_invocation_count` 固定为 0/1 | 同一 accepted task turn 不能形成多项 Observation→Action→EvidenceDelta；但 Graph invoke 计数仍可保持 1，由 Graph 内部 action ledger 表达多动作 | `engine/phase4b/task_turn.py::run_task_turn`、`tests/test_m43_task_api_trace.py` |
| legacy Harness 拓扑固定为 `route → Tool/Hybrid branches → controller → END`，controller 没有回边 | 直接修改它会破坏 M35–M38 frozen family；M44 必须新增 agent-family Loop，而不是给 legacy Graph 打补丁 | `engine/harness/graph.py::build_harness/run_harness` |
| M43 `TaskState.requirements` 只是字符串 tuple，Evidence 只有 `active/invalidated`，State 没有 action/budget/progress facts | 现有 State 无法可靠形成 eligible action set、按 requirement 对账 EvidenceDelta 或为 B5 保存任务级预算/termination | `engine/phase4b/task_runtime.py::TaskState/TaskEvidence` |
| `project_node_contexts()` 会预先生成固定的 Turn/route/SQL/controller 四份 Context，即使某节点没有实际执行 | B2 需要按实际 action/node 构造 Context，并证明 SQL、RAG、decision、Hybrid synthesis 各自只看到白名单事实 | `engine/phase4b/task_runtime.py::project_node_contexts` |
| `ToolObservation` 已提供四轴、EvidenceRef、ledger、Tool calls 和部分 diagnostics，但 SQL provider usage、统一 action consumption 与 EvidenceDelta 尚未形成 first-class facts | 父预算无法从两个深 Tool 的异构字段可靠汇总；Trace/Eval 也无法直接证明“额外调用换来了什么” | `engine/harness/contracts.py::ToolObservation`、`engine/harness/adapters.py` |
| Phase 4B seed 已冻结 7/8 月净退款 `120000/180000`、质量问题增量 `48000`，并有 reason/channel/product 守恒分解 | T3/T5 可以使用真实 oracle 验证结构归因，但不得把政策条款写成上涨因果 | `domain_pack/phase4b/seed_profile.json`、`docs/state/database-current-state.md` |
| B0 的 `refund_change_and_policy` operator 仍是 contract-only；当前 Router 只有 M38 `refund_reason_and_policy` 等窄 operator | T4/T5 不能靠旧关键词 Router 或旧固定问题继承 TaskState，必须在 agent family 内实现 versioned Hybrid operator | `domain_pack/phase4b/b0_contracts.json`、`engine/harness/router.py::_hybrid_plan_for` |
| M42 首次业务双政策检索只选中 quality、漏掉 basic | M44 必须保留该真实不足并正确停止；query rewrite/context expansion 仍是 M45 未准入候选，不能在 B2 偷跑 | `docs/state/rag-current-state.md`、`eval/reports/m42/m42-business-first-observation.json` |
| M44A 后普通 API 只有一个 Enterprise `rag_tool_factory`，而北极星 T4/T5 需要业务 release | 不增加可信 runtime resolver 就会查错 corpus；把全局默认切回业务 RAG 又会破坏 M44A 已确认合同 | `app/api/query.py::query`、`docs/notes/m44a-notes.md`、roadmap T4/T5 |
| M43 后真实 Qwen 曾出现 MySQL 不支持的 `DATE_TRUNC`，以及 timeout、计划自检失败 | B2 必须区分 recoverable dialect failure、不可恢复失败、provider unavailable 与 safety deny；不能把所有失败自动重跑 | `docs/state/change-history/phase4b.md` 的 M43 后交互记录 |
| Agent Scenario v2 只允许 0/1 Graph 和 task/context facts，没有 Action、Observation、Budget、EvidenceDelta、Progress/Termination | B2 required Gate 需要 additive v3；M42 v1、M43 v2 artifact 必须保持只读可验证 | `eval/agent_scenario_v2_contracts.py`、`docs/state/eval-baselines.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| Observation 后怎样走回边并保证停止 | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph`；`edges.py::route_after_orchestrator_call` | conditional edge 从当前 state 选择 Tool、collect 或 fallback；iteration/tool counter 在执行下一 Tool 前参与停止 | 新 agent-family Graph 让 decision node 读取 typed Observation、未满足 requirement、EvidenceDelta 和剩余预算；每条回边只能去已登记 Action executor 或确定性 termination | LLM 自由 tool call、强制首次 search、fan-out、字符串 Tool output、到预算边界再让模型生成 fallback answer |
| 怎样防止重复检索和把实际上下文留作证据 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::AgentState/append_unique`；`nodes.py::_retrieval_contexts/should_compress_context/collect_answer` | 已执行 retrieval key 去重；实际 Tool context 与最终 answer 一起保存供评测 | 以 `action_id + requirement_identity + input_fingerprint` 做 duplicate key；只保存安全 Observation/EvidenceRef/Context fingerprint，正文仍留在深 Tool 私有边界 | `MessagesState` 全历史、把正文字符串直接当 Observation、LLM compact、从 token 阈值推导业务 progress |
| Planner/Executor/repair 的控制权应放在哪里 | `DataAgent/.../DataAgentConfiguration.java::nl2sqlGraph` 中 `PLANNER_NODE → PLAN_EXECUTOR_NODE`、`PlanExecutorDispatcher` 和 SQL repair conditional edges | 显式 state key、固定 dispatcher、repair 回到登记节点、达到 repair 上限后 END | 顶层 Controller 独占 eligible set 与 parent budget；SQL repair 是 allowlisted action 且每 requirement 至多一次，深 Text2SQL 仍是一个 Tool module | 平台级 PlanExecutor、Python 执行、人审循环、大而平的 REPLACE state、开放 repair 次数或 Java/Spring 平台结构 |
| LangGraph 当前版本怎样表达循环和依赖注入 | [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 的 conditional edges、runtime context、loop/recursion limit；[StateGraph.add_conditional_edges reference](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges) | 每个动态出口只使用一种 routing mechanism；runtime context 注入 DB/Tool；循环必须有显式 END 条件，recursion limit 只作最后保险 | Action executor 依赖继续通过 `Runtime` context 注入；decision node 使用 typed path map；业务 Budget 先主动终止，另设固定 recursion limit 捕获实现缺陷 | 把框架 recursion limit 当业务预算、同一节点混用静态 edge 与动态 routing、依赖框架异常代替可解释 termination |

源码通路结论：ARAG 的 `orchestrator → tools → should_compress_context → orchestrator` 证明 conditional edge 与计数回边可行，但它的选择依据是 LLM tool call，Tool 结果是字符串，fallback 还能生成答案；这不能证明 Evidence gain、安全或 no-progress。DataAgent 的显式 dispatcher/repair 回边说明固定控制边界能承载多步执行，但其平台状态和 repair 语义也不能替代 DataPilot 的 owner、Evidence、四轴和预算合同。M44 因此采用“deterministic Controller + typed Action executor + injected deep Tool adapter”的深 module：移除 Observation 或 decision 回边后，T3 第二项 SQL Evidence 和 T4 跨 Tool 转换必须失败。

规模与代表性边界：M44 的控制合同用 Phase 4B SQLite oracle、22 条业务 release 和 non-happy-path fake adapters 验证；这能证明顶层 Loop、预算和安全，不能证明 36,417 文档上的恢复动作有效。M44A semantic smoke 的 retrieval 失败和 M42 business 漏选只作为停止/后续输入；动作诊断属于 M45，60 题 sealed reserve 在 M46 前继续不可访问。

## 4. 目标、优先级与非目标

### 模块完成状态

M44 完成后，`phase4b-agent-runtime-v1` 的 accepted task turn 仍只有一次 task runtime/Graph invoke，但该 invoke 内可在 hard parent budget 下执行多项已登记 Evidence action。系统具备 typed EvidenceRequirement、ActionAttempt、BudgetLedger、EvidenceDelta、ProgressDecision、TerminationFact、实际 node Context 和安全 runtime selection；T3、顶层 T4、整合 T5 及 recoverable/clarification/no-progress/budget/unsafe/external failure required Gate 闭合。legacy family、M42 v1、M43 v2、M44A 默认与 M46 reserve 均不改签。

### 必须完成

- 新增 additive B2 contract、TaskState v2 与 Agent Scenario v3；旧 B0/B1 contract 和 v1/v2 artifact 只读可验证。
- 建立 first-class typed EvidenceRequirement、ActionSpec/Attempt、BudgetLedger/Consumption、EvidenceDelta、ProgressDecision 和 TerminationFact；不把这些事实散落成 Graph 节点私有 dict。
- 在 agent runtime family 内新增独立 Decision Loop Graph；外部 interface 保持一个 task turn，legacy `DEFAULT_HARNESS` 拓扑和断言不变。
- 首版 action catalog 至少覆盖 SQL Evidence、受控 SQL repair、Document Evidence、clarify 和 stop；answer/Hybrid synthesis 是 Controller termination，不伪装成取证 Action。
- 用 `action_id + requirement_identity + input_fingerprint` 拒绝重复；EvidenceDelta 无新增且无新的合法失效修正时立即 `no_progress`。
- 顶层 parent budget 先检查再执行、执行后对账实际 consumption；SQL、Knowledge/retrieval/model/token/context/latency/timeout 分维度记录，不能折叠成总分。
- T3 在同一次 invoke 内由真实原因分解 Observation 准入商品补证据；不得把第二动作写死成无条件固定 DAG。
- T4 由同一 task 的 typed requirement 进入 Hybrid，使用已确认的 Knowledge Runtime Resolver 选择业务 release；顶层不指定 rewrite/parent expansion 等 RAG 内部策略。
- T5 correction 使不适用 SQL Evidence 失效并重新取证；Document Evidence 必须重新核对 runtime/authority/revision/purpose/ACL 后才可使用。
- clarification 结束当前 invoke；下一 turn 从已提交 TaskState 重进 Loop，不保存 Graph program counter、节点栈或 Thought。
- safety blocked、outbound deny、external unavailable、不可恢复、no-progress、budget exhausted 都有稳定终止，且不产生重复 Tool call。
- Response、JSONL Trace、Agent Scenario v3 从同一 AgentLoopResult/TaskTurnResult 投影 action、budget、Evidence 和四轴事实；不为评分重跑 pipeline。
- required Gate 同时覆盖新 agent family 与显式 pin 的 M31–M40 legacy 回归；旧 request/response 字段不删除、不改名。

### 建议完成

- 提供零 provider 的 `scripts.rehearse_m44_b2`，输出 T3/T4/T5、预算、动作顺序、Evidence gain 和 external call count 的安全报告。
- 提供 Action catalog/Budget profile 的人读 renderer，便于用户从 Trace 快速回答“为什么执行下一步、为什么停”。
- 将异构 Tool diagnostics 收敛为统一 `ResourceConsumption` 投影，原有 ToolObservation 字段保留兼容，不要求调用方理解 SQL/RAG 内部结构。

### 条件触发

- **本模块未触发**：G44-2 已确认方案 A，Controller 完全确定性，decision model calls/tokens 固定为 0；深 Text2SQL/Composer 的既有模型调用仍按各自用途记录。
- **后续重开门**：只有 required paraphrase 集形成稳定且不可接受的 deterministic clarification 失败簇，才允许另立 plan 评估结构化模型 action proposal、独立 decision purpose/outbound policy、deterministic validator 与经用户精确授权的真实 E2E；该能力已记入 `AI_CONTEXT.md` 防遗忘能力账本，不属于 M44 交付物。

- **本模块已触发**：G44-4 已确认方案 A，受控 SQL repair 可登记独立 `sql_repair` purpose/data class/allowed fields；网络前继续 exact-match deny-by-default。
- **硬边界**：不得把 raw DB error、stack trace、rows 或未授权字段塞进 `sql_repair` 或既有 `query_plan` prompt；不合法的 repair 直接停止。

- **触发条件**：业务/external runtime identity、active release/profile 或 ACL 校验不闭合。
- **允许动作**：当前 Document action 以 `external_unavailable` 或安全拒绝停止，并保留安全 identity mismatch；修复对应 runtime 后重新发起新 turn。
- **未触发时**：禁止 fallback 到另一 corpus、lexical/semantic backend 或仓库小语料。

### 明确非目标

- 不准入或执行 `query_rewrite_candidate`、`context_expansion_candidate`；它们仍是 M45/B3 的 unproven RAG recovery candidates。
- 不实现 RAG Subgraph、父子双层循环或解封 M46 reserve；M46/B4 才消费 M44 的 parent budget interface。
- 不保证 T4 业务双政策检索恢复成功；M44 正确保留 Pipeline 漏选和 insufficient/partial，最终恢复目标、强制开工条件与完成标准见第 10 节。
- 不实现跨进程/多 worker checkpoint、数据库 CAS 或 schema migration；M47/B5 才增加 durable adapter。
- 不实现 Task Compact、LLM summary 或长历史；M48/B6 才基于 typed ledger 交付。
- 不切换无 task 请求的产品默认，不让客户端选择 agent/legacy family、Knowledge runtime、Action、预算或 backend。
- 不修改 seed、指标口径、业务 active release、Enterprise profile/semantic snapshot、embedding、默认模型或 M34/M41 长期基线。
- 不运行真实 LLM Eval、RAG suite、held-out/all 或 sealed reserve；任何真实 showcase 需按 runbook 取得精确一次授权。

## 5. 关键合同

### C1：版本演进与 runtime family 隔离合同

- 输入：M42 B0、M43 B1 contract/artifact、roadmap T3–T5 和 nested task request。
- 成功输出：additive B2 contract、`phase4b-task-state-v2`、Agent Scenario v3 与 agent-loop runtime identity；M42 v1、M43 v2 可继续独立加载验证。
- 失败语义：family/state/contract/artifact identity 混用时稳定 mismatch，零 Tool；进程内旧 v1 task 不尝试猜测迁移。
- 必须保持的不变量：legacy request 继续进入冻结 Harness；agent task 一次 Graph invoke 可含多 Action，但 `graph_invocation_count` 仍是 0/1，Tool/action 次数另行记录。
- 本模块不冻结的实现细节：文件名、内部 dataclass 拆分和 loader 复用方式；禁止 sidecar 拼接或原位补字段。

### C2：可信 Knowledge Runtime Resolver 合同（已确认方案 A）

- 输入：服务端形成的 typed Document EvidenceRequirement、可信 caller/tenant/roles，以及已加载的 business release / Enterprise product runtime registry。
- 成功输出：`business_release` requirement 只得到 22 条业务 Knowledge adapter；`external_profile` requirement 只得到 M44A Enterprise adapter，并返回安全 resolved identity。
- 失败语义：scope 缺失/未知、runtime 未加载、identity/ACL/purpose 不匹配时零 retrieval/Composer 或零后续 synthesis，稳定 unavailable/blocked；绝不换另一 runtime。
- 必须保持的不变量：普通非 task API 继续使用 M44A Enterprise semantic 默认；请求体不能提交 scope/release/profile/backend/collection；两套 catalog、Evidence identity、Eval 分母和失败结论继续分账。
- 本模块不冻结的实现细节：app state 持有两个 factory 还是一个 registry；interface 必须能注入至少 business、external 和测试 fake adapters，形成真实 seam。

### C3：EvidenceRequirement 与 allowed Action 合同

- 输入：TaskDelta 合并后的 unresolved typed requirements、当前有效 Evidence、caller/ACL/runtime facts、最近 Observation 和剩余预算。
- 成功输出：closed-world eligible set，只含 `collect_sql_evidence`、`repair_sql_evidence`、`collect_document_evidence`、`clarify`、`stop` 中满足准入事实的动作；同一个 generic SQL action 可服务不同 requirement identity。
- 失败语义：未知 Action、客户端/模型注入、错误 runtime、无 requirement、重复 key、预算不足或安全前置不满足时拒绝执行；`stop` 始终可用。
- 必须保持的不变量：Action 只描述顶层缺哪类 Evidence，不指定 RAG rewrite/expansion；`repair_sql_evidence` 只对 allowlisted recoverable dialect Observation 每 requirement 至多一次；answer/synthesis 不计作取证 Action。
- 本模块不冻结的实现细节：类名和 catalog 存储形式；首版使用 G44-2 已确认的确定性 Controller，不实现模型 decision adapter。

### C4：父预算与实际消费合同

- 输入：可信 BudgetProfile、每个 Action 的声明 cost、Tool 执行后规范化 consumption。
- 成功输出：每次 ActionAttempt 都有各维度 budget before/consumed/after；达到任一 hard limit 时在下一外部调用前 `budget_exhausted`。
- 失败语义：负数、倒挂、未登记维度、Tool 报告超预算、usage 缺失却声称已观察或消费对不上时合同失败并停止；不得补跑取得数字。
- 必须保持的不变量：action、deep Tool、SQL、Knowledge、retrieval、candidate、selected、generation context、model call/token、timeout/latency 分维度；次数/资源上限负责确定性停止，延迟/费用主要作观测；子图未来消费必须能回写同一父账本。
- 本模块不冻结的实现细节：内部计数器数据结构；首版精确数值按 G44-3 已确认方案 A，B4 的 RAG 子预算数值不在 M44 预造。

### C5：Observation、EvidenceDelta 与 Progress 合同

- 输入：动作前 active Evidence/requirements、一次 typed ToolObservation、动作后 Evidence/validity。
- 成功输出：`added/removed/invalidated/duplicate` EvidenceDelta，以及只回答“requirement coverage 是否增加、是否还有 eligible action”的 ProgressDecision。
- 失败语义：Observation route/action/requirement 不一致、EvidenceRef identity 不闭合或相同 key 没有新 Evidence 时停止；不能用 answer 文本、Tool 成功状态或模型自评冒充 progress。
- 必须保持的不变量：Progress 不是第二 Answer Gate，不生成答案；denied/revoked/stale/invalidated Evidence 不进入 Context、synthesis、citation 或 active coverage。
- 本模块不冻结的实现细节：集合差分的内部算法；对外必须是稳定 typed projection。

### C6：Decision Loop Graph 与终止合同

- 输入：一个 accepted task turn 的合并后 TaskState、Action catalog、parent budget、注入的深 Tool/runtime adapters。
- 成功输出：`decide → execute action → observe/delta/progress → decide` 的有界通路，最后形成唯一 AgentLoopResult 与 `answer_ready/clarification_required/no_progress/budget_exhausted/unsafe/external_unavailable/unrecoverable` termination。
- 失败语义：Graph recursion/contract exception 关闭为 `agent_loop_contract_failure`，不产生半成品 answer；业务预算应在触发框架 recursion limit 前主动停止。
- 必须保持的不变量：Controller 独占全局 next action/termination；深 Tool 仍是深 module；clarification 结束 invoke；不保存/恢复 program counter 或 Thought；同一 failure 不被顶层和未来 RAG 子图各循环一次。
- 本模块不冻结的实现细节：节点名称和 StateGraph 文件布局；外部 interface 只暴露一次 `run_agent_loop(...) -> AgentLoopResult`。

### C7：T3、T4、T5 纵向行为合同

- 输入：M43 T1/T2 后的同一 task 与 roadmap T3/T4/T5 自然语言 turn。
- 成功输出：T3 原因 Observation 准入商品补证据并验证质量问题增量 48000；T4 受控 SQL→Hybrid、使用 business runtime，并以 SQL/Document 实际 Evidence 决定 complete/partial/insufficient；T5 渠道 correction 失效相关 SQL、重新取证并重新核验 Document Evidence。
- 失败语义：T3 原因 Observation 不支持质量驱动时不执行商品动作；T4 漏 basic 政策时不宣称全额退款规则完整；T5 任一 required branch 不足时只给已验证独立 partial 或停止。
- 必须保持的不变量：reason/channel/product 均与 7/8 月总额守恒；只表达观测驱动结构与适用政策，不声称政策导致退款上涨；Hybrid 最终 claims/citations 继续通过唯一 validator。
- 本模块不冻结的实现细节：canonical SQL 具体文本、Prompt 和表选择；oracle 口径仍以 seed profile/metrics 为准。

### C8：node Context 与同源投影合同

- 输入：TaskState/Delta、当前 requirement/action、最近安全 Observation/EvidenceDelta、budget 和最终 Gate-visible Evidence。
- 成功输出：Turn Understanding、decision、SQL action、Document action、Hybrid synthesis、controller 各自按实际执行生成的 Context，包含 purpose/version、allowlist、source identities、field/token budget、input fingerprint 和安全 actual-input projection。
- 失败语义：未执行节点出现 Context、Context 带 rows/正文/完整历史答案/raw task id、字段超 allowlist/budget 或 fingerprint 不闭合时 required Gate 失败。
- 必须保持的不变量：State 是事实 authority，Context 只做投影；decision 不看正文/rows，SQL 不看文档，RAG 不看完整 SQL rows，synthesis 只看 Gate-visible Evidence。
- 本模块不冻结的实现细节：B6 Compact 与正式长上下文 token trigger。

### C9：受控 SQL repair 合同

- 输入：`collect_sql_evidence` 的 safety-passed Observation、allowlisted `sql_dialect_incompatible` 分类、原 requirement 与剩余 repair/Tool/model budget。
- 成功输出：至多一次 `repair_sql_evidence`，使用 typed dialect/issue context重新生成并重新经过 QueryPlan validation、SQL Guard 和执行；新 Observation 与旧 Observation 都进入 action ledger。
- 失败语义：safety blocked、provider unavailable/timeout、generic DB failure、重复 repair、预算不足或新 SQL 仍失败时立即对应 termination，不自动第三次尝试。
- 必须保持的不变量：不执行字符串替换式 SQL 修补；不外发 raw DB error/stack/rows；新模型用途如需新增字段必须先通过 G44-4；repair 不绕过 SQL Guard 或输出投影校验。
- 本模块不冻结的实现细节：dialect classifier 的内部规则；必须用 `DATE_TRUNC`/MySQL 反例和错误动作排除测试证明准入边界。

### C10：Agent Scenario v3、Trace 与安全合同

- 输入：同一 TaskTurnResult/AgentLoopResult 的 delta/state/action attempts/observations/EvidenceDelta/budget/contexts/termination/runtime identity。
- 成功输出：API、Trace、v3 artifact 同源；completed artifact 对 sequence/turn/action/execution/assertion、contract/seed/caller/knowledge/runtime/policy identity closed-world 校验。
- 失败语义：缺/多/重复 Action、budget 不守恒、Observation 与 EvidenceDelta 不一致、评分侧重跑、private payload、identity 漂移或旧 artifact 被补字段时拒绝 completed。
- 必须保持的不变量：raw task id、Document 正文、Prompt、凭据和 Thought 不落 Trace/artifact；action Observation、node Context、Scenario artifact 和 Hybrid Trace 不保存完整 rows。SQL 单路 JSONL Trace 沿用已有的 Guarded rows 兼容合同；M42 v1、M43 v2 和 M31–M40 legacy Gate 同时保留。
- 本模块不冻结的实现细节：report renderer 的排版；typed assertion 语义不能依赖 Markdown 文案。

## 6. 工作切片与执行顺序

### M44-A：B2 contract、TaskState v2 与 runtime resolver

- 优先级：必须完成
- 依赖：M42/M43 完成；用户已确认 C2 方案 A；M44A Enterprise runtime 和业务 active release 均可注入。
- 实施内容：新增 additive B2 catalog/manifest/identity；把 TaskState requirements/Evidence validity/termination 演进为 v2；建立 trusted Knowledge Runtime Resolver；冻结 v1/v2/v3 compatibility matrix。
- 关键合同：C1、C2、C3、C10。
- 交付物：B2 contract bundle、TaskState v2 typed facts、runtime resolver interface/adapters、版本与安全测试。
- 验证方式：business/external/fake 三 adapter 表驱动；请求注入 scope/backend 被 422/contract reject；普通非 task API 仍解析到 M44A Enterprise，task T4 只解析到 business；v1/v2 artifact 原件 hash/validator 不变。
- 完成门：两套知识 runtime 不再依赖一个隐含 factory 猜测，且版本演进不改签前序 artifact。

### M44-B：Action、Budget、EvidenceDelta 与 Progress 深合同

- 优先级：必须完成
- 依赖：M44-A；G44-2/G44-3 已确认方案 A。
- 实施内容：实现 typed requirement/action/attempt、BudgetLedger、ResourceConsumption、EvidenceDelta、ProgressDecision、duplicate key 与 termination policy；将 Tool diagnostics 规范化为统一消费投影。
- 关键合同：C3～C5。
- 交付物：纯状态机/registry、budget profile、SQL/RAG consumption adapters、表驱动 contract tests。
- 验证方式：预算逐维守恒、执行前阻断、added/duplicate/invalidated/no-progress、wrong route/runtime/action、usage not-observed；删除 duplicate/no-progress 规则后测试必须失败。
- 完成门：Controller 不需要读取 Tool 私有结构即可决定 eligible set、progress 和 stop。

### M44-C：agent-family Decision Loop Graph 与实际 Context Builder

- 优先级：必须完成
- 依赖：M44-B、现有深 SQL/RAG Tool interfaces。
- 实施内容：新增 agent-family StateGraph 与唯一 `run_agent_loop` interface；按实际节点构造 Context；将 `run_task_turn` 的一次固定 Harness 替换为一次 agent-loop invoke，legacy path 不变。
- 关键合同：C5、C6、C8。
- 交付物：Loop module、Action executors、Context projections、AgentLoopResult、Graph/recursion/non-happy-path tests。
- 验证方式：多动作仍 `graph_invocation_count=1`；Tool/action count 独立；clarification/cancel/pre-rejection 仍零 Graph；移除 decision 回边后 T3/T4 contract test 必须失败。
- 完成门：外部 task turn interface 没有变复杂，但内部已能基于 Observation 有界推进。

### M44-D：T3 SQL 原因→商品补证据与受控 repair

- 优先级：必须完成
- 依赖：M44-C；G44-4 已确认方案 A 的 repair 出站边界。
- 实施内容：扩展通用 Turn Understanding/requirement merge 以表达 breakdown dimension 和原因分析；第一项 SQL Observation 决定是否准入第二项商品 Evidence；实现一次 dialect repair 与错误动作排除。
- 关键合同：C3～C7、C9。
- 交付物：T3 execution path、SQL action adapter/repair context、Phase 4B oracle assertions、recoverable/unrecoverable tests。
- 验证方式：质量增量 48000、product margins/total reconciliation、negative correction；替换首个 Observation 为非质量驱动时第二动作不执行；`DATE_TRUNC` allowlisted repair 至多一次，timeout/deny/generic error 零 retry。
- 完成门：T3 的第二动作由 Observation 改变 eligible set，而不是固定接线或退款问题字符串直接触发。

### M44-E：顶层 T4 Hybrid 与整合 T5 correction

- 优先级：必须完成
- 依赖：M44-C/D、C2 business resolver、B0 `refund_change_and_policy` contract。
- 实施内容：把 versioned Hybrid operator 接入 agent family；T4 依次满足 SQL/Document requirements 并复用唯一 Hybrid synthesis/validator；T5 修改 channel constraint、失效/重取证并重新授权 Document Evidence。
- 关键合同：C2、C5～C8。
- 交付物：T4/T5 sequence、business Pipeline success/漏选/ACL/unavailable adapters、Hybrid complete/partial/insufficient facts。
- 验证方式：Tool order、runtime identity、SQL/Document required branches、M42 真实漏选保持可见；RAG action diagnostics 中不得出现 rewrite/expansion；删除 runtime scope 或错误选 Enterprise 时测试失败。
- 完成门：T4/T5 在同一 task 中完成受控 route 变化和安全停止，但不冒充 B3/B4 RAG recovery。

### M44-F：Trace、Agent Scenario v3 与 deterministic rehearsal

- 优先级：必须完成
- 依赖：M44-A～E。
- 实施内容：扩展 Response/Trace 安全 additive projection；构建 v3 artifact/validator/Gate；加入 canonical T3–T5 与 recoverable/clarification/no-progress/budget/unsafe/external/duplicate cases；提供零 provider rehearsal。
- 关键合同：C1、C4、C8、C10。
- 交付物：Scenario v3、rehearsal/report、API/Trace/Eval same-source tests、B2 capability matrix。
- 验证方式：closed-world 缺/多 Action、预算漂移、Context 超界、private payload、runtime mismatch；rehearsal external calls=0；M42 v1/M43 v2 validators 继续通过。
- 完成门：用户可从一次 v3 artifact 回查每个 turn 的完整决策链，无需重跑 Tool。

### M44-G：回归、运行说明与技术收口

- 优先级：必须完成
- 依赖：M44-A～F required 全绿。
- 实施内容：更新 task 请求/Trace/预算/Knowledge runtime 的 runbook；运行聚焦测试、M31–M44A 受影响回归和全仓 deterministic pytest；执行 compileall/diff check；按 `finish-module` 固化 notes/state/changelog。
- 关键合同：C1～C10。
- 交付物：`docs/notes/m44-notes.md`、验证快照、runbook/state/history 更新和最终 Handoff。
- 验证方式：按第 8 节顺序；预计超过 2 分钟的全仓测试按 AGENTS 长任务纪律后台执行并检查 exit/done/log。
- 完成门：B2 required 与 legacy regression 同时通过，且未运行未授权 provider/RAG Eval/reserve；完成后进入 M45/B3，而不是宣称 Phase 4B 或 Agentic RAG 已完成。

## 7. 决策门

### G44-1：Agent task 的 Knowledge runtime 选择（已确认）

#### 已确认方案 A：服务端 typed requirement + closed-world resolver

- 做法：普通非 task RAG 保持 Enterprise semantic 默认；task Document requirement 由服务端 scope 选择 business/external adapter，请求不能选择。
- 影响：M44 增加一个必要的 runtime seam 和两套 adapter 等价测试；M45/B3、M46/B4 可继续分 corpus 诊断和预算。
- 适用条件：北极星业务政策与 M44A Enterprise 产品默认同时存在。
- 风险：resolver 若读取自然语言关键词或请求字段会重新制造越权/错 corpus；必须只消费 typed server facts。

#### 建议与确认时点

- 建议：已确认采用方案 A。
- 建议理由：同时满足 roadmap T4/T5、M44A 默认合同、两套知识分账和请求不可选 backend。
- 用户确认前允许推进：只读调查。
- 用户确认前禁止推进：冻结 runtime/corpus 选择合同。
- 需要确认的时点：已于制定本 plan 前确认。
- 重开决策的条件：新增第三类正式知识 runtime、公开 corpus 选择需求，或 M44A 产品默认被用户另行修改。

### G44-2：首版 next-action 决策方式（已确认方案 A）

#### 已确认方案 A：确定性 Controller

- 做法：按 typed requirement、Observation、EvidenceDelta、ACL/runtime 与 budget 形成 eligible set，再用固定优先级选择 Action；decision model calls/tokens 为 0。
- 影响：required Gate 可完全离线、选择可解释；开放自然语言仍由 Turn Understanding 保守投影，不由模型自由规划。
- 适用条件：B2 catalog 很小且触发事实可结构化；当前 T3–T5 满足。
- 风险：规则覆盖有限，未知组合会 clarification/stop；这是首版受控边界，不改变后续最终能力。

#### 未选方案 B：结构化模型 proposal + 确定性审核

- 做法：模型只能从同一 allowlist 提议 Action，Controller 再校验 requirement、budget、ACL/outbound、duplicate/no-progress。
- 影响：可能覆盖更多表达，但新增 decision purpose、Prompt、模型预算、出站政策和真实 E2E；required deterministic Gate 仍不能被替代。
- 适用条件：预注册 paraphrase 无法用确定性事实区分 eligible Action，且 clarification 会阻塞 B2 核心 Scenario。
- 风险：扩大出站与不稳定性，模型 proposal 也不提供新的 Evidence。

#### 确认结果与重开时点

- 用户确认：2026-08-24 选择方案 A。
- 固定理由：B2 的核心是证明 Observation 控制动作，不是证明模型会规划；现有结构化事实足以完成 T3–T5，并延续 M43 零新增决策出站。
- 本模块禁止：实现 decision adapter、登记 decision outbound 或运行 decision provider。
- 后续能力：未选方案 B 已记入 `AI_CONTEXT.md` 防遗忘能力账本；它不是 M44 缺口，也不会自动成为下一模块。
- 重开决策的条件：required paraphrase 集形成稳定且不可接受的 deterministic clarification 失败簇，并另立 module plan、重新取得 outbound 与真实 E2E 授权。

### G44-3：首版 parent budget profile（已确认方案 A）

#### 已确认方案 A：三次 Evidence action 的保守预算

- 做法：每 accepted turn 最多 3 次 Evidence Action / 3 次 deep Tool；SQL 最多 3、Knowledge 最多 1、同 requirement repair 最多 1；B2 Pipeline 每次 Knowledge action最多 1 次 retrieval batch，沿用 `5 candidates / 3 selected / 3 generation-visible`；decision model 0 次；深 Tool model 总调用硬上限 6，累计 token 观测上限 24000，达到后禁止下一动作；timeout/latency 逐次记录且 Loop 不自动 retry timeout。
- 影响：T3 两次 SQL、T4/T5 SQL+Document 均有空间，并额外容纳一次合法 dialect repair；足以暴露预算停止且成本清楚。
- 适用条件：首版无 RAG Subgraph，Text2SQL 每次 action 受两次模型调用子额度约束。
- 风险：复杂 Text2SQL 若需要更多 plan step 会保守停止；token 只能在响应后对账，不能撤回已发生的单次调用。

#### 未选方案 B：四次 Evidence action 的宽预算

- 做法：Action/Tool 上限 4、model calls 8、token 32000，其他单项上限不变。
- 影响：容纳更多补证据或 repair，但 B2 尚无第三种合格恢复动作，容易让重复调用看似合理并提高费用。
- 适用条件：实现前有确定性 required Scenario 证明三次上限会错误截断合法动作链。
- 风险：当前没有支持该额外调用的 Evidence，扩大预算会削弱 no-progress 门。

#### 确认结果与重开时点

- 用户确认：2026-08-24 选择方案 A。
- 固定理由：预算由当前最长合法链 T3/T4/T5 + 一次 repair 推导，不为未知未来预留无主调用；B4 子图通过同一父账本另行分配 retrieval 子预算。
- 本模块固定：production budget identity 使用方案 A 的 exact limits，并以 required Gate 验证守恒与执行前阻断。
- 重开决策的条件：required deterministic Scenario 证明合法链必需更多调用，或 B4 为已准入子动作提出父预算升级；重开必须重新版本化 budget profile，不能静默放宽。

### G44-4：SQL dialect repair 的模型出站（已确认方案 A）

#### 已确认方案 A：独立最小 `sql_repair` purpose

- 做法：仅 `sql_dialect_incompatible` 可触发一次；新增 exact receiver/purpose/data-class rule，只允许 `prompt/system_prompt/model` transport fields，prompt 内容只含当前 question、MySQL dialect、稳定 issue code 和必要的安全 candidate SQL，不含 raw DB error/rows/stack。
- 影响：能把已观察的 `DATE_TRUNC` 失败闭合为真实 recoverable action；仍经过 QueryPlan/Guard/执行并计入 parent budget。
- 适用条件：使用现有 Qwen/DeepSeek Text2SQL adapter，且用户允许新增该用途。
- 风险：增加一次模型调用和新 outbound policy identity；修复仍可能失败，失败后必须停止。

#### 未选方案 B：只分类并停止，不新增 repair 出站

- 做法：识别 dialect incompatibility，记录 recoverable-but-unavailable 后停止，等待用户新 turn。
- 影响：安全和可解释性闭合，但生产路径没有真正恢复动作；B2 只能通过 fake repair adapter 证明控制合同。
- 适用条件：用户不接受新增模型用途或当前数据政策不允许 candidate SQL 外发。
- 风险：已观察的 M43 后失败仍未在同次运行恢复，弱于 roadmap 对 recoverable Loop 的预期。

#### 确认结果与重开时点

- 用户确认：2026-08-24 选择方案 A。
- 固定理由：它使用与现有 Text2SQL 相同的数据类别和 receiver，但以独立用途接受审计；比偷偷复用 `query_plan` purpose 或字符串改 SQL 更安全、可评测。
- 本模块允许：修改默认 outbound policy 以登记最小 `sql_repair` 用途；真实 provider/showcase 仍须按 runbook 获得精确次数授权，不能由本次方案确认代替运行授权。
- 重开决策的条件：官方/provider 数据政策变化，或 deterministic SQL dialect compiler 能在不降低正确性的情况下替代模型 repair。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 版本/family 隔离 | B0/B1 bundle 与 v1/v2 artifact 回读；legacy/task API matrix | 旧 identity/hash/断言不变；新 task 多动作仍单 Graph invoke | 必须完成 |
| C2 runtime resolver | business/external/fake 表驱动 + API test | T4 只用 business；普通 RAG 仍 Enterprise；错误 scope 零 fallback | 必须完成 |
| C3 Action catalog | registry/eligible set/注入/duplicate tests | 只有 allowlist 动作；错误动作和客户端注入零 Tool | 必须完成 |
| C4 Budget | 纯 ledger 守恒 + Graph budget-stop | before-consumed-after 闭合；达到任一 hard limit 后下一外部调用为 0 | 必须完成 |
| C5 EvidenceDelta/Progress | added/invalidated/duplicate/no-progress cases | progress 只由 requirement coverage/Evidence identity决定；重复立即停 | 必须完成 |
| C6 Loop/termination | Graph edge、recursion、clarify/unsafe/unavailable tests | 每条回边有主动停止；框架异常不产生半答案；clarify 结束 invoke | 必须完成 |
| C7 T3 | Phase 4B oracle + Observation mutation | 质量增量 48000；不同 Observation 不准入商品动作；两次 SQL 最多 | 必须完成 |
| C7 T4 | SQL→business Document sequence + M42 漏选 fixture | runtime/Tool order正确；漏 basic 时 partial/insufficient，不假 complete | 必须完成 |
| C7 T5 | correction/invalidation/reauthorization sequence | channel SQL 重查；旧不适用 Evidence 不进入 synthesis/citation | 必须完成 |
| C8 Context | actual-node allowlist/fingerprint/private payload tests | 未执行节点无 Context；rows/正文/完整历史/raw id 均不出现 | 必须完成 |
| C9 SQL repair | DATE_TRUNC/dialect、timeout/deny/generic error cases | 仅 allowlisted dialect failure repair一次；其余零 retry；Guard 不绕过 | 必须完成 |
| C10 same-source | API/Trace/v3 artifact 三方对账 | action、budget、delta、termination、runtime identity 完全一致 | 必须完成 |
| C10 closed-world Eval | 缺/多/重复 Action、budget 漂移、private payload、hash 篡改 | 非法 artifact 全部拒绝 completed；required 三态分母闭合 | 必须完成 |
| legacy 回归 | M31–M40 与 M42/M43/M44A 受影响测试 | 原断言通过，不放宽 Tool/branch 预算或 payload | 必须完成 |
| deterministic rehearsal | `scripts.rehearse_m44_b2` | T3/T4/T5 与非 happy-path checks 全通过，external calls=0 | 建议完成 |

聚焦验证顺序：纯合同/状态机 → Loop Graph 与 fake Tool → T3 oracle → T4/T5 runtime/Hybrid → API/Trace/v3 → M42/M43/M44A → M31–M40 legacy。失败后只重跑相关子集；全部代码修改完成后再执行全仓 deterministic pytest、compileall 与 `git diff --check`。

本模块不自动运行真实 Qwen、embedding、Milvus/RAG Eval、M34 historical 180、held-out/all 或 M46 sealed reserve。G44-2 已确认不使用模型 decision；若需要真实 SQL repair showcase，另按 runbook 请求精确 Scenario/次数授权。deterministic required Gate 与真实 showcase 分账，二者不互相替代。历史 artifact 只读，不因新增字段补写或重签。

## 9. 依赖与交付物

### 依赖

- 已完成的 M42/B0 seed/oracle、最小 caller、Hybrid operator direction、Agent Scenario skeleton 与 sealed reserve。
- 已完成的 M43/B1 TaskDelta/TaskState、task boundary、natural turn seam、Evidence invalidation、node Context 与 v2 artifact。
- 已完成的 M44A Enterprise product runtime/fail-closed；22 条业务 active release 和 Enterprise runtime 继续隔离。
- 现有 Text2SQL/RAG 深 Tool、Shared Gate、Hybrid synthesizer/citation validator、trusted caller/ACL/outbound/四轴/Trace。
- 用户已确认 G44-1～G44-4 均选择方案 A；真实 provider 运行授权仍与设计确认分离。

### 交付物

- B2 contract/manifest/identity、TaskState v2 和 Agent Scenario v3。
- 顶层 Decision Loop 深 module、Action/Requirement/Budget/EvidenceDelta/Progress/Termination contracts。
- trusted Knowledge Runtime Resolver 及 business/external/test adapters。
- T3、顶层 T4、整合 T5 与 recoverable/non-happy-path execution evidence。
- actual node Context、Response/Trace/Eval same-source projection 和 deterministic rehearsal/report。
- 聚焦/受影响/全仓验证、M44 notes、runbook/state/Phase 4B changelog 与 finish-module Handoff。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：RAG 内部只运行一次现有 Pipeline；M42 business 漏选和 M44A external retrieval 失败不会在 M44 通过 rewrite/expansion 恢复。
- 下一模块可直接消费的产物：M45/B3 使用 M44 的 typed RAG Observation、EvidenceDelta、parent budget、runtime scope 和 termination，开展有界 failure campaign并准入至少两种 action card。
- 最终目标与当前缺口：Phase 4B 最终仍必须完整实现 bounded RAG Subgraph；M44 只完成顶层 Loop，未完成 RAG 内部多步取证，因此不得宣称 Agentic RAG 或 B4 完成。
- 后续模块编号：M45=B3 failure funnel/action-level Evidence；M46=B4 bounded RAG Subgraph+A/B；M47=B5 durable state；M48=B6 Compact/集成。
- M45 强制开工条件：M44 required/legacy Gate 通过；business/external Observation 可分层读取；candidate/action/预算/review point 在运行前冻结；M46 reserve 继续 sealed。
- M46 强制开工条件：M45 至少两种动作达到 action-level 准入，且至少一个 runtime/corpus 在不同真实 Observation/Scenario 下分别证明两种动作；不足时按 roadmap 正式 review/no-go 并由用户重规划，不能降低标准。
- M46 最终验收标准：experimental RAG Subgraph 完整可运行/回退/追踪；父子预算无双循环；business T4 和新 sealed reserve A/B 完成；是否切默认与实现分离。
- 后续风险：Text2SQL usage 目前没有统一向 ToolObservation 投影，预算 instrumentation 可能暴露更深的 adapter 改造；必须收进 M44-B 的深 interface，不能让 Controller逐个解析私有字段。
- 后续风险：业务与 Enterprise 双 runtime 若被实现成自然语言关键词路由，会导致错 corpus/越权；C2 required Gate 必须在 M44 内闭合，不能推给 B3。

## 11. 开工条件

- 开工前无需确认：M44 完整对应 B2；legacy/agent family 隔离；additive v3；TaskState v2；G44-1～G44-4 已全部确认方案 A；T3/T4/T5、M46 reserve sealed、M44 不自动运行真实 Eval等均由 roadmap/state/既有决策确定。
- 实施中仍需单独授权：任何真实 provider/showcase、RAG Eval、held-out/all 或 sealed reserve 运行；设计方案确认不等于运行授权。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得为开发便利修改 seed、active release、M44A 默认、outbound、安全、正式 case 或后续 B3/B4 完成标准。
