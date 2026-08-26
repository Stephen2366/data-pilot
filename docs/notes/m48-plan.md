# M48 Phase 4B B6 Context Compact 与全阶段集成开发计划

> 能力里程碑：Phase 4B B6；本模块完整承担 Context Compact 基础版、extended north-star 与 Phase 4B 最终技术集成
>
> 主要问题：当前 durable TaskState 与 event ledger 能跨进程恢复任务，却没有可验证的 Compact、bounded recent-turn window 或 compact 前后行为等价证据，Phase 4B 仍不能在长任务中有界保留上下文并完成全链验收

## 1. 模块定义与范围判断

M47/B5 已验收通过，durable checkpoint、typed event ledger、restart/multi-worker/CAS 与安全清理均已闭合；roadmap 规定 B6 最终汇合 B1/B2/B4/B5。用户已冻结 B0–B6 各对应一个模块和一份 module plan，因此 M48 完整对应 B6，不再把 Compact、全阶段 assurance 或演示链拆给 M49；模块内部以 M48-A～M48-G 纵向切片控制风险。

本模块围绕一个主要问题形成闭环：**怎样把同一 task 的 typed 状态与 turn/event 事实收敛成可追溯、可验证、失败关闭的 Task Compact，并让真实节点在 compact 后继续得到最小且语义等价的 Context。** 完成后，用户能够在同一个 task 中连续演示 T1→T5，触发 compact，跨进程继续一个 extended turn，并从 API/Trace/Eval 回查 compact 的来源范围、触发原因、身份、Evidence validity、节点实际入模 Context、动作/预算/终止以及高风险原始 reference。

M48 必须同时交付 B6 Compact 与 Phase 4B 技术集成，不能只做 schema/codec 后把连续任务、RAG Subgraph、durable resume 或 non-happy-path 留作“以后优化”。M48 技术收工后仍需按项目流程执行 `finish-docs → 用户人工检查 → accept-module`，在这些步骤完成前不宣称 Phase 4B 已最终验收；也不把技术控制闭环外推为 RAG 质量提升、生产认证、性能或生产就绪。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| M47 checkpoint 只保存 TaskState v2；`agent_task_events.event_payload` 只有 delta category、transition identity、action count、termination reason | 当前 event ledger 是安全审计骨架，但缺少 Compact 所需的逐 turn typed constraint/requirement/Evidence validity/action-budget lineage 与 recent raw turn | `engine/phase4b/task_boundary.py::TaskBoundaryEvent`、`engine/phase4b/mysql_task_boundary.py::_append_event` |
| `TaskBoundaryPort` 只有 start/claim/commit/switch/clear，没有读取或原子提交 context material/compact 的 seam | Compact 若绕过 boundary 直接查表，会把存储细节扩散到 task runtime，也无法与同一 version/claim 原子提交 | `engine/phase4b/task_boundary.py::TaskBoundaryPort` |
| checkpoint schema 没有 context/compact payload、schema identity、source watermark 或 compact reference | 无法在 restart 后证明恢复的是哪一版 Compact，也无法对 terminal/clear/expiry 同步 scrub | `app/models/agent_task_checkpoint.py`、Alembic `20260826_0004` |
| TaskState v2 已保存 goal、constraints、pending、requirements、EvidenceRef/validity 与 last action/budget/termination，但不会保存完整历史；invalidated Evidence 会继续累积 | State 已是 Compact 的主要 authority 输入，却不能单独证明逐 turn provenance，也存在长任务 payload 增长风险 | `engine/phase4b/task_runtime.py::TaskState`、`engine/phase4b/task_state_codec.py` |
| 当前 `project_node_contexts()` 与 `run_agent_loop()` 分别构造 Context；turn-understanding 看当前 question，Decision/SQL/Controller 看不同 typed payload | 已有 node-level allowlist 与 token budget，但 Context 组装 seam 分散；直接给所有节点注入完整 Compact 会破坏最小权限与测试 locality | `engine/phase4b/task_runtime.py::project_node_contexts`、`engine/phase4b/agent_loop.py::run_agent_loop` |
| B4 business Pipeline 默认、Subgraph 仅 server-controlled experimental，且 historical v3 为 no-go | B6 必须集成并评测 Subgraph 控制链，但不能借“最终集成”切默认、解封 reserve 或宣称质量提升 | `AI_CONTEXT.md`、`rag-current-state.md`、M46 rollout contract |
| M43 rehearsal 只连续执行 T1→T2；M44 的 T3/T4/T5 多为独立状态或局部 continuation；M47 只证明 T1→T2 restart | 现有证据拼起来覆盖各能力，但尚未证明同一个 raw task/version lineage 连续贯通 T1→T5、Subgraph、restart 与 Compact | `scripts/rehearse_m43_b1.py`、`scripts/rehearse_m44_b2.py`、`scripts/rehearse_m47_b5.py` |
| Agent Scenario 当前到 additive v5；B0 capability matrix 仍把 Context Compact 标为 M48 unavailable | B6 需要新 v6 family 和阶段 assurance，不能原位给 v1～v5 artifact 补字段 | `eval/agent_scenario_v5_contracts.py`、`domain_pack/phase4b/b0_contracts.json` |
| 产品 task TTL 为 900 秒、state payload 上限 65536 bytes；terminal/clear/expiry 立即 scrub，24h tombstone 后 purge | Compact/recent raw turn 必须继承同一 task 生命周期并有独立大小门，不能成为更长寿的隐私旁路 | `app/core/config.py`、`domain_pack/phase4b/b5_contracts.json`、`runbook.md` |
| 当前安装 LangGraph 1.1.2，Graph state/reducer 只负责单次 invoke；DataPilot durability 位于自有 task boundary | B6 不应为了使用框架 summary/checkpointer 而恢复 Graph program counter 或迁移到 `MessagesState` 全历史 | `pyproject.toml`、本机 `langgraph==1.1.2`、`engine/phase4b/agent_loop.py` |

调查未发现 roadmap、state、现有代码或参考源码之间会改变 M48 最终范围的冲突。真正的实现缺口是：B5 为 B6 预留了概念 seam，但尚无可消费的 context schema/ledger interface；M48 必须显式补齐，而不是把现有四字段 event payload 误称为 Compact 输入已完备。

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 何时触发压缩，怎样保留去重/已执行身份 | `agentic-rag-for-dummies/project/rag_agent/nodes.py::_retrieval_contexts / should_compress_context`；`graph_state.py::AgentState` | 压缩前计算 messages + 既有 summary 的 token 规模；单独保留 retrieval keys，避免压缩后重复检索 | 触发器同时读取 committed turn 数和各节点候选 Context 的 deterministic token estimate；Compact 显式保留 action/requirement/Evidence identity 与 source watermark | 参考项目的 `BASE_TOKEN_THRESHOLD + summary growth` 参数、字符串 query 作为长期 identity、强制首搜、把检索正文留在共享 state |
| 压缩后哪些内容成为节点真实输入 | `agentic-rag-for-dummies/project/rag_agent/nodes.py::compress_context / orchestrator / fallback_response`；`graph.py::create_agent_graph` | summary 与 recent/current input 分层；压缩后删除旧 messages，再回到实际 orchestrator | `TaskCompact + bounded recent raw turns + current turn` 先进入统一 Context Builder，再按 Turn/Decision/SQL/Knowledge/Subgraph/Synthesizer/Controller 各自 allowlist 投影并记录实际输入 identity | LLM 自由摘要作为 authority、把 Tool 正文和自由 Thought 整段写进 summary、`RemoveMessage` 即视为关键事实已保真、summary 直接驱动安全决定 |
| 为什么文本摘要不能证明行为等价 | `agentic-rag-for-dummies/project/rag_agent/nodes.py::compress_context`；`notebooks/evaluation.ipynb::query_rag / assert_saved_outputs_match_dataset / score_answer` | 保存真实运行 context 后再评分；压缩必须观察真实下游输入，而不是只测 summary 函数 | 用同一 next turn 对 pre-compact 与 post-compact typed state/context 做 paired behavioral equivalence；比较 delta、route/action、Evidence validity、权限、预算和 termination，不比较答案逐字 | 文本相似度、RAGAS/LLM Judge 或最终答案相同替代 required Gate；评分时重跑另一条 pipeline |
| 框架 memory/reducer 与 DataPilot task boundary 如何分权 | LangGraph 官方 [Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)、[Context](https://docs.langchain.com/oss/python/concepts/context)、[Graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api) | 官方区分 thread short-term state、runtime context 与 LLM context；trim/delete/summarize 都需要应用自行选择策略；reducer 只定义 state update 语义 | 继续由 MySQL task boundary 持久化 committed task 事实；LangGraph 单次 invoke 只消费已构建的 typed Context，不引入 framework checkpointer 或 message reducer承担 B6 | `MessagesState` 全历史、`InMemorySaver` 冒充 durability、框架 summarization middleware 直接替代 DataPilot Compact、恢复任意 Graph 执行栈 |

定点复核结论：参考实现的真实通路是“计算规模 → LLM 压缩 Tool/message 文本 → 删除旧消息 → summary + 已执行检索 key 再入模”。它能证明触发、recent window 和去重 identity 的 seam 值得保留，但不能证明时间、金额、指标、否定、政策例外、权限或 Evidence validity 不漂移。M48 因此采用 deterministic typed Compact；基础版零 `compact_summary` 模型用途、零新增 outbound。

规模与代表性边界：本模块的主要规模是 task turn 数、checkpoint/context bytes、node token budget 和 compact 次数，不是 external corpus 文档数。B6 必须在 business 北极星与 B4 Subgraph 控制链上做完整纵向验证，但无需重跑 M46 external 60 题或解封 60 题 reserve 来证明 Context Compact；大 corpus 质量结论继续服从 M46 no-go。

## 4. 目标、优先级与非目标

### 模块完成状态

M48 完成后，agent task family 具有版本化 Task Compact、bounded recent-turn context、双条件 deterministic trigger、compact provenance/identity、原子持久化和失败降级；所有实际节点通过统一 Context Builder 获取各自允许的最小 typed payload。一个同源 Agent Scenario v6 能复演 canonical T1→T5、server-controlled experimental Subgraph、compact、restart 与 extended continuation，并把 B0～B6 capability matrix 和 required assurance 收口。

### 必须完成

- M48 完整交付 B6；Compact schema/builder/trigger/provenance、recent raw window、行为等价、failure fallback、extended sequence 和阶段 assurance 都是硬门。
- Compact 只由 trusted TaskState + versioned typed turn/event facts 确定性生成；不使用 LLM 自由摘要。
- Compact 至少保存 goal、confirmed/corrected constraints、pending questions、unresolved Evidence requirements、active EvidenceRef/validity、action/budget/termination 摘要、高风险原始 reference、source turn/version range 和 content identity。
- Context material 通过 task boundary 的小 interface 读取和原子提交；API/runtime 不直接访问 MySQL 表或 event row。
- recent raw turn 是 bounded、版本化、随 task TTL/clear/terminal/expiry scrub 的短期材料；完整 answer、SQL rows、Document 正文、Prompt、Thought、凭据和无限消息历史继续禁止持久化。
- compact 前重新校验来源闭集，compact 后在实际执行前继续复核 Evidence freshness/revision/purpose/ACL；Compact 永远不是业务 authority。
- Turn Understanding、Decision、SQL、Knowledge、RAG Subgraph、Hybrid Synthesizer、Controller 分别使用 typed projection；每个投影带 allowlist、source identities、field/token budget 和实际输入 fingerprint。
- compact trigger 必须在正常产品配置和带 identity 的测试低阈值下可验证；客户端不能选择阈值、强制 compact、上传 compact 或修改 source watermark。
- compact 构建/解码/来源不完整/identity mismatch/预算失败有 closed-world reason，并保守保留可验证的未压缩最小状态、澄清或停止；不得悄悄丢事实后继续。
- additive Agent Scenario v6 与 Phase 4B assurance 同时验证新 family 和 M31～M47 旧合同；v1～v5 artifact 只读。
- 同一 raw task lineage 连续贯通 T1→T5、B4 Subgraph、真实 MySQL task boundary、compact、restart 和 compact 后继续；配套权限、否定、版本冲突、失败降级等 non-happy-path required Gate 闭合。

### 建议完成

- 提供只读、安全的 compact inspect/diagnostic seam，只返回 identity、source range、trigger、字段计数、byte/token estimate、fallback status，不返回 raw recent turn。
- 在阶段 assurance 报告中生成一条“答案 → citation/Evidence → Observation/Action → Budget/Context/State/Compact”的安全回查索引，便于人工演示和面试讲解。

### 条件触发

- **触发条件**：实现证明 checkpoint 单列 bounded context payload 无法在同一 CAS transaction 中满足大小、scrub 或查询需求。
- **允许动作**：暂停 M48-B，按 G48-2 重新选择独立 context segment 表，并追加 migration/parity/cleanup Probe。
- **未触发时**：不新增第三张状态表，不引入 Redis、对象存储或 LangGraph checkpointer。

- **触发条件**：现有 v1 event/checkpoint task 在缺少历史 typed material 时达到 compact trigger。
- **允许动作**：返回 `task_compact_source_incomplete`，保守停止或提示新建 task；保留旧 task 只读证据直至 TTL/clear。
- **未触发时**：不猜测补齐历史 turn，不从 Trace、answer 或 raw rows 反向合成 Compact，也不建设通用在线迁移框架。

- **触发条件**：开发中发现现有 deterministic turn understanding 对 compact 后指代/省略形成稳定失败簇，且 typed recent window 无法修复。
- **允许动作**：先提出最小新 Scenario 和追加 Probe；只有用户另行确认 receiver/purpose/data class/fields/预算后，才可评估结构化模型 proposal。
- **未触发时**：M48 不新增 compact-summary/turn-understanding 模型调用或 outbound policy。

### 明确非目标

- 不实现 LLM 叙述性 summary、长期记忆、跨 task 用户画像、永久聊天历史或跨会话检索。
- 不恢复 LangGraph/RAG Subgraph program counter、节点栈、Tool 中间态或未提交 turn。
- 不修改 M46 Pipeline 默认/Subgraph experimental/no-auto-fallback，不重开 historical 调参，不解封 decision reserve，不宣称 Subgraph 质量提升。
- 不改变默认模型、embedding、Milvus collection、Knowledge release、seed/oracle、SQL 指标或业务数据。
- 不建设生产 SSO/OAuth/JWT、跨地域 HA、吞吐/压测、任意外部 Tool exactly-once 或通用 Eval 平台。
- 不把 Compact 当作 Answer Gate、Evidence authority、权限凭据或累计成本限额；现有 owner/tenant/role、Evidence/ACL/outbound 和父子预算仍是唯一控制事实。

## 5. 关键合同

### C1：Additive B6 Identity 与兼容合同

- 输入：B5 contract identity、TaskState v2、event v1/v2、agent runtime/B4 rollout identity 和旧 Agent Scenario v1～v5。
- 成功输出：内容绑定的 B6 contract、Task Compact/context schema、runtime identity、Agent Scenario v6 与 Phase 4B assurance identity；旧 family 显式 `unchanged_readable`。
- 失败语义：未知 schema、predecessor mismatch、旧 artifact 被改签、runtime/default/reserve identity 漂移均拒绝加载或 completed。
- 必须保持的不变量：M31～M47 旧 API/Trace/Eval 语义与 artifact hash 不变；legacy runtime 不获得 Compact；客户端不能选择 runtime/compact strategy。
- 本模块不冻结的实现细节：contract loader、文件与类名；identity 字段和 predecessor 关系必须唯一。

### C2：Typed Context Window 与 Durable Ledger 合同

- 输入：当前 committed TaskState、同 task/version 的 typed turn event、bounded raw user turn、owner/tenant/active role、TTL 和上一 Compact reference。
- 成功输出：closed-world context window，包含上一 Compact（可空）、compact 后未覆盖的 typed turns、bounded recent raw turns、current watermark 与 context identity；memory/MySQL adapter 公开语义等价。
- 失败语义：缺 turn、顺序/版本洞、重复 ordinal、raw 超限、未知字段、identity mismatch 或 legacy source 不完整均失败关闭。
- 必须保持的不变量：event ledger 保持不可变安全审计事实；raw recent turn 只存在于独立 context payload，不进入 TaskState/event/Trace/Eval；terminal/clear/expiry 与 state payload 同事务 scrub。
- 本模块不冻结的实现细节：checkpoint context 列名与 JSON 内部排列；物理方案已由 G48-2 冻结为 checkpoint additive context payload + event v2。

### C3：Deterministic Task Compact 合同

- 输入：C2 context window、当前 TaskState、trigger fact 与 schema policy。
- 成功输出：Task Compact v1，至少含 goal、constraint/current correction provenance、pending、unresolved requirements、active EvidenceRef/validity、action/budget/termination 摘要、高风险原始 reference、source turn/version range、source identities、trigger、byte/token estimate 与 compact identity。
- 失败语义：任一 required fact 无法从 typed source 唯一派生、high-risk reference 丢失、输入超限或 codec/tamper 失败时不产生新 Compact，并投影稳定 fallback reason。
- 必须保持的不变量：Compact 是 deterministic 派生物，不覆盖 TaskState/Evidence authority；时间、金额、指标、否定、政策例外和 Evidence identity 不由自然语言概括；同输入必得同 identity。
- 本模块不冻结的实现细节：内部 dataclass/codec 的命名和 JSON 字段顺序；schema 的语义字段、上限和 hash 输入必须冻结。

### C4：Trigger、Atomic Commit 与 Failure Fallback 合同

- 输入：committed turns since last compact、每个节点 candidate context estimate、G48-1 正式阈值、current claim/version 与 compact candidate。
- 成功输出：明确 `not_triggered / triggered_and_committed / fallback_uncompacted / blocked`；新 Compact、recent window 裁剪、TaskState 和 boundary event 在同一 claim commit 原子落盘。
- 失败语义：构建失败但原未压缩 context 仍在安全上限内时只允许 `fallback_uncompacted`；来源不完整、原 context 已超预算、原子提交失败或身份不闭合时澄清/停止，零额外深 Tool。
- 必须保持的不变量：旧 worker/fencing token 不能覆盖新 Compact；compact 失败不删除 source；测试低阈值有独立 identity，不能静默成为产品默认。
- 本模块不冻结的实现细节：估算器内部优化；正式阈值和 recent window 已由 G48-1 冻结为 5-turn / 75% dual trigger + 最近 2 turn。

### C5：Node-level Context Builder 合同

- 输入：current turn、TaskState、C2 window、可选 C3 Compact、当前 Evidence authorization 与 node purpose。
- 成功输出：Turn Understanding、Decision、SQL、Knowledge、RAG Subgraph、Hybrid Synthesizer、Controller 各自的 typed `AgentNodeContext`；带 allowed fields、source identities、field/token budget、estimated tokens 和 fingerprint。
- 失败语义：字段越权、token 超限、Compact/State identity 不一致或 denied/stale Evidence 出现在 payload 时，在节点调用前失败关闭。
- 必须保持的不变量：SQL 不看文档正文，RAG 不看 SQL rows，Router/Turn 不看完整 Evidence 内容，Synthesizer 只看本轮 Gate 允许的 generation-visible Evidence；raw recent turn 只给确有指代解析需要的 Turn Understanding 投影。
- 本模块不冻结的实现细节：内部 builder 分层与节点代码移动方式；外部 interface 应保持小而统一。

### C6：Behavioral Equivalence 与 Evidence Revalidation 合同

- 输入：同一 source execution 的 pre-compact context、post-compact context 与同一个 next turn；当前 caller/tenant/role/authority/revision/purpose/freshness。
- 成功输出：goal、关键 constraints、pending、Evidence validity、route/eligible action、权限结果、预算/termination 等价；TaskDelta/TaskState/Context identity 有可解释 lineage，答案文字允许不同。
- 失败语义：任何 required typed 行为漂移即 failed；真实依赖不可用为 inconclusive，不用 fake 结果覆盖；ACL/revision/freshness 失败使 Evidence 失效并重新取证或停止。
- 必须保持的不变量：SQL 无可靠 snapshot 时继续重查；external Document 永远重检索；business Document 只有重新核对 active authority/revision/content/anchor/purpose/ACL 后才重水化；Compact 不改变这些规则。
- 本模块不冻结的实现细节：paired test harness 的对象组织和报告样式。

### C7：同源 API/Trace/Eval、Scenario v6 与阶段 Assurance 合同

- 输入：一次连续 task execution 的 turn/state/context/compact/lifecycle/Loop/Subgraph 事实，以及旧 family/artifact identities。
- 成功输出：API/Trace 安全投影共享 compact status/identity/source range/trigger/fallback、node contexts 和 lifecycle；Agent Scenario v6 一次 sequence closed-world completed；Phase 4B assurance/capability matrix 标明 B0～B6 available 及 rollout/quality 限制。
- 失败语义：缺/多/重复 turn、compact、action/assertion，task/version/source range 断裂，API/Trace/Eval 不同源，private payload 泄露或旧 family 漂移均拒绝 completed。
- 必须保持的不变量：不投影 raw recent turn、raw task id、owner compare value、state/context JSON、rows、正文、answer、Prompt、Thought 或凭据；Subgraph experimental/no-quality-claim 与 reserve sealed 状态显式保留。
- 本模块不冻结的实现细节：v6 report 的视觉排版和演示脚本命名。

## 6. 工作切片与执行顺序

### M48-A：B6 合同、连续 Scenario 与决策冻结

- 优先级：必须完成
- 依赖：M42～M47 accepted artifacts、G48-1/G48-2。
- 实施内容：冻结 C1～C7 的 machine contract、compact/context/event identity、closed-world reason、continuous T1→T5 + extended turn catalog、兼容矩阵、private payload 禁区和 Phase 4B assurance skeleton；明确 default Pipeline 与 experimental Subgraph 两种集成视图。
- 关键合同：C1～C7
- 交付物：B6 contract/manifest、Scenario v6 catalog skeleton、assurance plan、决策记录。
- 验证方式：content-binding、predecessor、closed-world、tamper、旧 contract hash 与 rollout/reserve identity tests。
- Live Probe checkpoint：不适用；本切片没有真实 compact/storage 实现。
- 完成门：G48-1/G48-2 已确认，后续切片只消费一个合同来源；不存在把 M43/M44 分段 rehearsal 冒充连续任务的 assertion。

### M48-B：Context codec、event v2 与 durable boundary seam

- 优先级：必须完成
- 依赖：M48-A、已确认 G48-2。
- 实施内容：实现 bounded raw-turn/typed-turn/context-window/TaskCompact strict codec；扩展 boundary interface，使 claim 能返回 context material、commit/switch 能原子提交 context mutation；MySQL 通过 additive migration 保存 context schema/identity/payload/watermark，event v2 保存足够的安全 typed turn facts；memory adapter 同语义。
- 关键合同：C1～C4
- 交付物：codec、boundary protocol/adapter、migration/ORM、event v2、parity/size/scrub tests。
- 验证方式：round-trip、未知/缺失/篡改/超限、v1 source incomplete、memory/MySQL parity、terminal scrub、old fencing token、upgrade/downgrade/check。
- Live Probe checkpoint：`M48-P1` / after M48-B、before M48-C；只有 `continue` 才允许产品 Context Builder 接线。
- 完成门：P1 证明 context/compact mutation 与 TaskState/event 同一 MySQL CAS transaction，不存在 endpoint 直查表、半提交或 raw payload 残留。

### M48-C：Deterministic Compact Builder 与 dual trigger

- 优先级：必须完成
- 依赖：M48-B、M48-P1=`continue`、已确认 G48-1。
- 实施内容：实现 typed merge/prune/provenance/high-risk-reference 规则、turn-count + candidate-context-budget dual trigger、低阈值测试 identity、source watermark 与 fallback state machine；compact 前执行来源闭集和 Evidence validity 检查。
- 关键合同：C2～C4、C6
- 交付物：Compact builder/trigger、behavior snapshot、failure reason 与 deterministic tests。
- 验证方式：同输入同 identity；月份/金额/指标/否定/政策例外/Evidence identity 保真；边界阈值；构建失败不删 source；删除任一 high-risk fact 后 required test 失败。
- Live Probe checkpoint：不单独运行；本切片的首条完整链需等 M48-D 实际节点消费后由 `M48-P2` 验证，避免只测“生成了一个 JSON”。
- 完成门：Compact 是可验证 typed 派生物，trigger/fallback 可判定，且不含任何 LLM/outbound seam。

### M48-D：统一 Node Context Builder 与全链运行接线

- 优先级：必须完成
- 依赖：M48-C。
- 实施内容：以一个深 Context Builder interface 收拢当前分散投影，让 Turn/Decision/SQL/Knowledge/Subgraph/Synthesizer/Controller 分别消费最小 payload；task turn 在执行前读取/构建 context、执行后用同一 claim 原子提交 state/event/context；API/Trace 增量投影安全 compact facts。
- 关键合同：C4～C7
- 交付物：runtime wiring、node projection、API/Trace schema、pre-node rejection 与 integration tests。
- 验证方式：每节点 allowlist/token budget、actual input fingerprint、denied/stale Evidence 排除、legacy non-task/old task response 兼容；删除 Compact 或 recent window 后对应 extended coreference test 失败。
- Live Probe checkpoint：`M48-P2` / after M48-D、before M48-E；只有 `continue` 才允许冻结 v6 completed artifact 与阶段 assurance。
- 完成门：P2 证明同一个 raw task/version lineage 实际触发 Compact、跨进程继续且行为不漂移；不是仅有 builder 单测或手工注入 compact。

### M48-E：Agent Scenario v6 与 Phase 4B assurance

- 优先级：必须完成
- 依赖：M48-P2=`continue`。
- 实施内容：从 P2 同形的一次连续执行投影 v6；覆盖 canonical/extended、pre/post compact paired equivalence、failure fallback、ACL/role drift、version conflict、duplicate/no-progress、Subgraph parent/child budget 与 private-payload negative；聚合 B0～B6 capability/compatibility/rollout 视图。
- 关键合同：C1、C6、C7
- 交付物：Agent Scenario v6 validator/artifact/report、Phase 4B assurance/capability matrix、tamper tests。
- 验证方式：closed-world completeness、source lineage、compact identity、API/Trace/Eval同源、v1～v5/legacy compatibility；删除 Compact consumer、Evidence revalidation 或父子预算后对应 Gate 必须失败。
- Live Probe checkpoint：不新增；消费 P1/P2 真实证据，不把 deterministic rehearsal 冒充 MySQL 事务或 RAG 质量。
- 完成门：v6 required Gate 与 Phase 4B assurance 全过；B0～B6 可技术标记 available，同时 Pipeline/Subgraph rollout、quality claim、reserve 和生产边界准确保留。

### M48-F：项目演示回查链与人工验收准备

- 优先级：必须完成
- 依赖：M48-E。
- 实施内容：提供可重复的 continuous demo/rehearsal 入口与安全报告，串联 answer/citation/Evidence、Observation/Action、Budget、node Context、TaskState、checkpoint/Compact；编制 required non-happy-path 检查单和面试叙事素材，但不提前执行 `finish-docs` 或 `accept-module`。
- 关键合同：C6、C7
- 交付物：演示脚本/报告、人工检查清单、Phase 4B 技术边界说明。
- 验证方式：脚本从干净隔离环境可复演；报告不依赖 temp-only private artifact；每个链接 identity 可回查且不含敏感内容。
- Live Probe checkpoint：不新增；只整理并复演已冻结的 deterministic evidence，若重新执行真实依赖须按 runbook 另算证据时效。
- 完成门：用户可以按一条路线完成全阶段人工演示，不需要拼接 M43/M44/M46/M47 多份互不连续结果。

### M48-G：验证、技术收工与 Phase 4B handoff

- 优先级：必须完成
- 依赖：M48-A～F。
- 实施内容：按 `finish-module` 审计注释、Probe 时点、migration/数据清理、notes/state/changelog；更新 runbook 的 Compact 配置/诊断入口、database/eval/AI context；形成 Phase 4B 技术完成与人工验收 handoff。
- 关键合同：C1～C7
- 交付物：完整验证快照、技术档案、专项 state、changelog 与后续人工验收入口。
- 验证方式：聚焦→Phase 4B/legacy 受影响→全仓 pytest，migration current/check/upgrade/downgrade、compileall、`git diff --check`；长任务按 AGENTS 后台纪律执行。
- Live Probe checkpoint：审计 P1/P2；不得在收工阶段首次补跑来掩盖缺失时点。
- 完成门：第 8 节所有必须项闭合，无未处理 `revise/stop/development_probe_missing`；技术收工只宣称 B6 与 Phase 4B technical integration 完成，最终验收仍等待 finish-docs、人工检查和 accept-module。

## 7. 决策门

### G48-1：正式 Compact trigger、recent raw window 与保留策略（已确认方案 A）

#### 方案 A：5-turn / 75% dual trigger + 最近 2 turn（已冻结）

- 做法：在下一个 accepted turn 执行前，只要“距上次 compact 已提交 5 个业务 turn”或“任一候选 node Context 预计超过其 token budget 的 75%”任一成立即触发；保留最近 2 个原始 user turn，每个最多 2048 UTF-8 bytes，current turn 只在本次执行中使用。Compact/context payload 继承 task 900 秒 sliding TTL，terminal/clear/expiry 立即 scrub，tombstone 不保留 raw/compact payload；仓库/Trace/debug 只保存 safe identity/provenance。
- 影响：canonical T1→T5 后的第一个 extended turn 会稳定触发，既能演示 turn-count 路径，也能用低阈值 fixture 覆盖 budget 路径；recent window 足以支撑常见“这个/再按渠道”等短指代，隐私与实现复杂度适中。
- 适用条件：Phase 4B 仍是有 TTL 的同一任务，不追求长会话聊天体验。
- 风险：极长单条 question 仍需 bounded raw codec/high-risk refs；两条 recent history 不能解决任意长距离自由指代，歧义时必须澄清。

#### 方案 B：3-turn / 60% trigger + 最近 1 turn（未选）

- 做法：更早触发，recent raw 只保留上一 user turn且最多 1024 bytes；其余生命周期与安全 debug 同 A。
- 影响：原始文本暴露面更小、Compact 触发更频繁；extended sequence 更早进入 compact path。
- 适用条件：更重视最小数据保留，接受更多 compact commit 与更多澄清。
- 风险：指代/省略上下文较弱；频繁 compact 增加 CAS 写入和调试噪声，不能因此降低 behavioral equivalence 门。

#### 决策结果

- 用户于 2026-08-27 确认方案 A；M48-A 必须把 5-turn / 75% dual trigger、最近 2 个 user turn、单 turn 2048 UTF-8 bytes 和既定生命周期写入 machine contract。
- 决策理由：5 个 canonical turn 后触发与 Phase 4B 演示天然对齐；75% 是在硬预算前留出确定性安全余量，2-turn window 在短任务中兼顾指代与隐私。该数值是 M48 正式产品合同，不从 ARAG 参数照搬。
- 重开决策的条件：P2 出现稳定 `context_budget_exceeded`、recent-window 指代失败簇、payload 超限或隐私审查要求进一步收紧。

### G48-2：Context/Compact 持久化形状与真实 Probe 隔离（已确认方案 A）

#### 方案 A：checkpoint additive context payload + event v2；独立 `datapilot_m48_test`（已冻结）

- 做法：以 Alembic 0005 只给 task checkpoint 增加 context schema/identity/payload/source watermark 等最小列；event 表物理结构不变，新 turn 写 additive event v2 safe payload，旧 event 不改签。context payload 用独立 strict codec 保存“Compact + 未覆盖 typed turns + bounded recent raw turns”，每次 claim commit 原子替换；terminal/clear/expiry 同事务 scrub。P1/P2 使用独立 `datapilot_m48_test`，允许完整 migration、Phase 4B deterministic seed、synthetic task/context/event 和精确清理，禁止触碰 `datapilot_dev`、active release/pointer、Milvus index、historical/reserve。
- 影响：不新增第三张表，复用 M47 CAS/fencing/lifecycle；context window 天然 bounded，raw turn 不进入 append-only audit event。真实 Probe 可同时验证状态库与 Phase 4B SQL oracle。
- 适用条件：context payload 在 G48-1 上限内可稳定小于独立 size gate，并且常用读取总是随 checkpoint claim 发生。
- 风险：checkpoint 行变宽；codec、state/context 双 payload 原子更新与 scrub 必须严测；创建/seed 独立测试库需要精确授权和清理记录。

#### 方案 B：独立 context segment 表；同一测试库隔离（未选，条件反例时才重开）

- 做法：checkpoint 只保存 compact ref/watermark，新增第三张 context segment 表保存 bounded raw/typed segment；compact transaction 写新 segment、更新 checkpoint、删除被覆盖 raw segment。Probe 仍使用独立测试库。
- 影响：物理裁剪与查询更灵活，checkpoint 行较小；增加一张表、外键/锁顺序、migration、清理和并发面。
- 适用条件：M48-B prototype 证明单列 JSON 无法满足大小/原子 scrub/查询要求。
- 风险：更容易出现 checkpoint 与 segment 半状态、死锁或 orphan；对当前 900 秒短 task 可能是过度设计。

#### 决策结果

- 用户于 2026-08-27 确认方案 A，并授权创建/使用独立 `datapilot_m48_test` 执行计划中的 P1/P2；Probe 完成后清空 agent task/context/event synthetic rows，业务 seed 是否保留由 notes 记录，不删除数据库本身。
- 决策理由：当前已有两个真实 adapter 和稳定 checkpoint CAS seam，单个 bounded context payload 能形成更深的 boundary interface；独立表只有在真实大小/事务反例出现时才值得引入。
- 隔离红线：禁止把 Probe 静默改到 `datapilot_dev`，禁止触碰 active release/pointer、Milvus index、historical/reserve；超出已冻结范围的真实写入仍须按 runbook 重新申请精确授权。
- 重开决策的条件：M48-B 的确定性 size/transaction prototype 证明方案 A 无法满足 C2/C4，或部署明确要求 context 与 checkpoint 物理隔离。

## 8. 验证与验收矩阵

### Live Dev Probe（开发期真实探针）

M48 修改真实 MySQL task payload、API 多轮、restart 与节点实际 Context，pytest/fake 不能独立证明原子持久化和 compact 后真实纵向行为，因此适用 Live Dev Probe。standing authorization、三态、计数、重验和 Formal Eval 分账统一引用 `docs/state/runbook.md`；数据库写入严格受 G48-2 已冻结的隔离范围约束。

| Probe ID / 执行时点 | 探针场景 | 真实产品链路/依赖 | 需要观察的结果与 Trace 事实 | 通过/失败/不确定标准 | 决策与停止条件 |
| --- | --- | --- | --- | --- | --- |
| M48-P1 / after M48-B、before M48-C | real MySQL 上连续提交 typed turns，触发 context payload 替换；两个 adapter 用同 version 竞争包含 compact mutation 的 commit；随后 clear/expiry/purge | boundary/codec/migration → real MySQL/InnoDB；零 LLM/embedding/RAG | state/context/event schema identity、source watermark、唯一 CAS winner、旧 fencing token 拒绝、原子 rollback、raw/context payload scrub、前后表/行数与 cleanup | `passed`：无半提交、双胜者、identity 漂移或 payload 残留；`failed`：任一原子/隐私/清理断言失败；`inconclusive`：MySQL/权限不可用 | passed→继续 M48-C；failed→revise，只重验受影响操作；inconclusive→暂停 durable Compact，不以 SQLite 覆盖 |
| M48-P2 / after M48-D、before M48-E | 同一 task 经 `/api/query` 连续执行 T1→T5，server-controlled experimental Subgraph 完成 T4，随后触发 compact；停止进程后由新进程执行 extended correction/解释 turn；另测 role drift、compact corruption/source gap 与版本竞争 | API → caller/task → real MySQL durable boundary → deterministic QueryPlan + SQL Guard + Phase 4B SQL oracle → business Knowledge Tool/Subgraph → Response/Trace；provider calls/tokens 固定 0 | 120000/180000/60000/50% 与原因/渠道 oracle；policy Evidence/citation；task/version lineage；compact trigger/source range/identity；高风险 facts；pre/post delta/route/action/Evidence validity/permission/budget/termination；node actual context；无 raw/rows/body 泄露 | `passed`：连续 lineage 和 paired behavior 全等价、Subgraph父子预算闭合、restart 后继续、所有负例零越权/重复 Tool；`failed`：语义漂移、丢高风险 fact、权限绕过、双循环、半 compact 或隐私泄露；`inconclusive`：真实 DB/本地 Knowledge 依赖不可用 | passed→继续 M48-E；failed→revise/stop，不冻结 v6；inconclusive→不得宣称 B6/Phase 4B technical integration complete |

P1/P2 都是 `exploratory / baseline-ineligible` 开发证据，不是 Formal Eval。P2 使用确定性本地 adapter 是为了隔离验证 Compact/Context/控制语义，不宣称真实 LLM、开放问法或 RAG 质量；它不得读取 M46 historical 逐题内容或 Phase 4B reserve。若实现中出现计划外真实失败，需要新增 Probe 时按 runbook 提交场景、链路、预计调用/数据写入、停止条件并取得用户授权。

模块完成后建议用户执行的 Formal Eval：当前无需付费 Formal Text2SQL/RAG Eval，也不运行 historical/held-out/reserve。M48 的硬门由 deterministic Agent Scenario v6 + Phase 4B assurance + real MySQL P1/P2 承担；完成技术收工后进入人工连续演示与 `accept-module`。如果用户希望额外展示真实 Qwen，只能另行精确授权一个 post-compact showcase，标记 baseline-ineligible，不能替代本矩阵或外推质量。

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 identity/compatibility | B6 content-binding/tamper tests；v1～v5 与 legacy fixtures | 新 identity 可复算；旧 hash/语义不变；Subgraph rollout/reserve 不漂移 | 必须完成 |
| C2 context window/ledger | codec round-trip、size/privacy、event order、memory/MySQL parity、migration tests + P1 | source 闭集；bounded recent turns；raw 只在 context payload；scrub/TTL/CAS 闭合 | 必须完成 |
| C3 deterministic compact | golden/negative/property-style fixtures | 同输入同 identity；required typed/high-risk facts 无损；未知/缺失/篡改拒绝 | 必须完成 |
| C4 trigger/atomic fallback | turn/budget 边界、低阈值 identity、fault injection、P1/P2 | 正式/测试阈值分离；commit 原子；失败不删 source且不超预算继续 | 必须完成 |
| C5 node Context | 每节点 allowlist/token/fingerprint 与 actual-input assertions | 节点只见必要字段；denied/stale/private material 永不入模；Compact 被真实消费 | 必须完成 |
| C6 equivalence/revalidation | pre/post paired next-turn、authority/ACL/revision/freshness negative + P2 | delta/state/route/action/permission/budget/termination required 行为等价；旧 Evidence 不越权复用 | 必须完成 |
| C7 continuous v6/assurance | 同一次 T1→T5+extended execution、closed-world/tamper、API/Trace/Eval 对账 | 连续 raw task/version 完整；B0～B6 technical capability available；non-happy-path 全闭合 | 必须完成 |
| legacy/rollout regression | M31～M41 legacy、M42～M47 Agent families、M46 Pipeline/Subgraph tests、全仓 pytest | 旧 assertions 未放宽；Pipeline 默认/Subgraph experimental/no fallback；reserve sealed | 必须完成 |

聚焦测试顺序：identity/schema → codec/privacy/size → memory parity → migration/MySQL CAS → trigger/builder → node Context → paired equivalence → API/Trace → Scenario v6/assurance。P1/P2 只在对应切片首次执行；失败先定位并按 runbook 最小重验。

全量回归范围：M1 database/migration，M27 SQL contract，M31～M41 Evidence/RAG/Harness/Eval，M42 B0 identities/reserve，M43 task runtime/context，M44 top-level Loop/API/v3，M46 Subgraph/parent-child budget/v4，M47 durable boundary/v5，以及最终全仓 deterministic pytest。预计超过 2 分钟的完整验证按 AGENTS 先写 notes checkpoint 后后台运行。

不属于本模块的真实验证：M46 external 60/120/reserve 质量 A/B、Qwen Reliability、semantic/embedding/Milvus 性能、生产认证、吞吐/压测、跨地域数据库故障、长期记忆和叙述性 summary faithfulness。历史 artifact/合同只读，不补字段、不改签、不重跑制造 M48 分数。

## 9. 依赖与交付物

### 依赖

- 已验收 M42～M47：Phase 4B seed/caller/scenario skeleton、TaskState/TaskDelta/Context、Decision Loop、RAG action cards/Subgraph、durable boundary/event ledger。
- M47 MySQL CAS/fencing/TTL/clear/tombstone 与 TaskState v2 strict codec；M46 Pipeline 默认/Subgraph experimental/no-auto-fallback；现有 Evidence/ACL/outbound/四轴/父子预算合同。
- `docs/state/runbook.md` 的 Live Dev Probe、Formal Eval、数据库和长任务纪律；database/RAG/eval state 的当前 identity 与解释边界。
- G48-1/G48-2 已确认并冻结为方案 A；真实 P1/P2 只能在 `datapilot_m48_test` 和已授权数据边界内执行。

### 交付物

- additive B6 machine contract、Task Compact/context/event v2 schema 与 strict codec。
- durable boundary context seam、Alembic/ORM additive migration、memory/MySQL parity、atomic compact commit 与 lifecycle scrub。
- deterministic Compact builder、dual trigger、high-risk references、failure fallback 和 behavioral equivalence harness。
- 统一 node-level Context Builder、API/Trace compact 投影与实际入模 evidence。
- continuous T1→T5 + extended/restart/Subgraph rehearsal、真实 MySQL P1/P2。
- Agent Scenario v6、Phase 4B assurance/capability matrix、演示回查链与人工检查清单。
- M48 notes、runbook/database/eval/RAG/AI context/changelog 更新和 Phase 4B final handoff。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：LLM 叙述性 summary、长期/跨 task memory、生产认证、外部 Tool exactly-once、性能/HA、RAG 新质量 candidate/default 切换。
- 下一步可直接消费的产物：`finish-docs` 编写 M48/Phase 4B 学习复盘；用户按演示清单人工检查；`accept-module` 执行最终验收门。没有预留 M49 来补 B6 必须项。
- 后续需要根据真实失败重新规划的内容：只有形成稳定 compact 指代失败、payload/事务反例、生产隐私要求或新的 RAG quality candidate，才分别另立明确模块；不得留下“以后按需优化 Compact”的模糊尾项。
- 可能存在的风险：event v1 active task 无完整 compact source、checkpoint 行变宽、compact 频繁 CAS、exact raw reference 隐私、Evidence authority 在 compact 时变化、全阶段 rehearsal 过度依赖 canonical fixture。对应控制是 fail-closed legacy source、独立 context size gate、G48-1 dual trigger、TTL/scrub、安全投影、non-happy-path 与删除测试。
- 最终目标不缩水：M48 必须把 B6 和 Phase 4B technical integration 全部闭合；若 P1/P2、v6 required Gate、continuous task 或 behavioral equivalence 任一未完成，只能记录当前切片状态，不得宣称 B6/Phase 4B 完成，也不得把缺口转成无编号后续。

## 11. 开工条件

- 开工条件已满足：M48 完整对应 B6；基础版只用 deterministic typed Compact；不恢复 Graph/Subgraph program counter；Compact 不是 authority；v1～v5/legacy artifact 只读；M46 rollout/default/reserve 不变；不新增模型/outbound；G48-1/G48-2 均已冻结为方案 A。
- 已获授权范围：可按 G48-2 创建/使用独立 `datapilot_m48_test` 执行 P1/P2；不得扩展到 `datapilot_dev`、active release/pointer、Milvus index、historical/reserve 或计划外真实写入。
- 实施中条件确认：只有方案 A 出现确定性 size/transaction 反例才重开 G48-2；只有 typed recent window 出现稳定自然语言失败簇才提出模型方案与追加 Probe，未触发时不得扩权。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得为实现便利缩减 B6、连续任务或 Phase 4B 最终验收标准。
