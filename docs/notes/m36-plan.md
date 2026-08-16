# M36 结构化澄清恢复与轻量 Thread Checkpoint 开发计划

> 状态：已确认可执行
>
> 能力里程碑：Phase 4 `P4`；本模块只闭环 P4/G5 的首个顶层恢复切片“澄清后在同一 thread 恢复一次”，不等于完成 P4 的 Evidence 复用、通用 Tool 恢复或完整 Context Builder
>
> 主要问题：M35 能正确返回 `clarification_required`，但该状态现在是死胡同；用户补充条件时系统无法证明这是同一任务、同一可信 caller，也不能受控地恢复取证

## 1. 模块定义与范围判断

M35 已完成单轮 Harness，`phase4-harness-v1` 也固定包含一条 clarification Scenario；当前最小但完整的下一步，不是为所有 Tool 失败增加重试，而是把已经可观察的“需要澄清”从终止文案变成一次有界恢复。这个切片对应 P4/G5，并以 M29 已冻结的 `p4_clarification_time_window` 蓝图和 M35 的 `clarification_required` 事实为入口。

范围按“第一次请求暂停、第二次请求恢复并终止”形成纵向闭环：首次缺条件时不调用 Tool，保存最小 pending task；用户通过同一 thread 补齐结构化条件后，系统重新校验 caller/owner 和状态版本，只允许消费一次 checkpoint，并至多调用一个现有深 Tool。它既能演示 Agent 的暂停/恢复，也能独立验收 thread ownership、过期、显式清理、重复/并发恢复和预算停止。

本模块不把整个 P4 一次做完。Evidence 复用/失效、SQL 跨轮复用、Tool 技术失败重试、跨 Tool 补证据、自由文本长对话、通用历史摘要和持久 checkpoint 都有独立风险与验收面，放进 M36 会把一个可讲清的澄清闭环扩成会话平台。完成 M36 后，用户可以理解、演示和验收：

- 为什么 `thread_id` 只是定位符，不是授权凭证；恢复时仍要重新解析可信 caller 并核对 owner；
- 为什么 pending clarification 只保存当前任务和待补条件，不保存完整聊天历史、SQL rows、Document Evidence 或模型思维链；
- 为什么同一 checkpoint 只能被成功消费一次，过期、重启丢失、旧版本、重复或并发恢复都不会静默重复 Tool Call；
- 为什么补齐条件后仍沿用 M35 的 Router、深 Tool 和唯一 `AgentRunResult`，而不是在 API/thread 层另建一套回答控制器。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| M35 的 clarification 路径固定为 `route=none / execution=not_started / answer=clarification_required`，随后 Graph 到 `END` | 系统能说“请补充”，但没有可恢复任务状态 | `engine/harness/graph.py::_controller_node`、`engine/harness/router.py::DeterministicRouter.decide` |
| `HarnessRequest` 只有本轮 question/run/caller/SQL 选项，Graph 无 checkpointer，`run_harness()` 每次都从空状态 invoke | 下一次 HTTP 请求无法证明自己延续哪一轮、消费哪一版状态 | `engine/harness/contracts.py::HarnessRequest`、`engine/harness/graph.py::build_harness / run_harness` |
| `QueryRequest`、`AgentResponse` 和 Trace 没有 thread、turn、checkpoint version、pending fields 或 resume action | API、前端和 Eval 无法表达暂停/恢复、冲突与过期 | `app/schemas/agent.py`、`app/api/query.py::_project_response / _record_trace` |
| `TrustedCaller` 已预留 `thread_owner_ref`，但当前 fixture caller 没有实际 thread，M35 只保存 `caller_safe_ref` | P4 已有 owner seam，但尚未形成绑定、重校验和非泄露失败语义 | `engine/governance.py::TrustedCaller / demo_caller / test_caller`、`docs/notes/m29-phase4-entry-contract-notes.md` |
| M29 已冻结 `budget_exhausted`、`state_version_incompatible`，并要求未知 reason fail closed | M36 应扩展同一 registry，不能用异常文本或 HTTP 404 猜恢复语义 | `docs/notes/m29-phase4-entry-contract-notes.md`「reason code registry」 |
| M35 Harness Eval 只有单次 invocation 的 clarification 断言，没有 turn 序列、owner、过期、版本或并发断言 | 现有全绿只能证明“正确停下”，不能证明“安全恢复” | `eval/harness_contracts.py::SCENARIOS / HarnessExecutionEvidence`、`tests/test_m35_harness_eval.py` |
| 当前默认 RAG、模型、outbound 和两套 Knowledge profile 均已冻结，M34 质量缺口属于独立候选 | 澄清恢复不需要切模型、改检索或接 external profile；把它们捆绑会失去单变量归因 | `docs/state/AI_CONTEXT.md`、`docs/state/rag-current-state.md`、`docs/state/eval-baselines.md` |

## 3. 参考源码定点复核

DataPilot 的真实问题是“如何保留一个未完成任务，并在下一 turn 安全、有限地继续”，不是建设开放研究循环。因此只按 `phase4-reference.md` 的“有界 Loop、短期状态与 Context”能力卡复核 ARAG 的 clarification、checkpoint、reducer 和预算源码。

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| clarification 如何暂停并保留待处理任务 | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph` | `InMemorySaver`、`interrupt_before=["request_clarification"]` 证明 pending state 与后续恢复可以在 Graph 生命周期中显式表达 | M36 先把“pending task → resume once → resolved”定义成独立 turn interface；具体是否直接采用 LangGraph interrupt/checkpointer 由 G-M36-1 决定 | 不把全局 `InMemorySaver` 本身当 owner、TTL、版本、并发或生产持久化保证；不复制主图+研究子图 |
| 原问题与用户补充如何进入下一次判断 | `agentic-rag-for-dummies/project/rag_agent/nodes.py::rewrite_query / _recent_conversation` | 分开保存 `pendingQuery` 与 `pendingClarifications`，恢复时显式区分原任务和补充信息 | 只保存 typed pending task、闭集 missing fields 和用户确认值；由最小 Clarification Context Builder 形成当前 Router/Tool 输入 | 不默认调用 LLM rewrite，不拼完整聊天历史，不默认 summary/compact，也不把自由文本拼接当安全结构化条件 |
| checkpoint state 如何避免覆盖或重复累积 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::State / accumulate_or_reset / append_unique` | 不同状态字段需要明确替换、去重或累积语义 | pending task 使用单调状态迁移和 compare-and-set version；条件 key 不允许重复/未知，恢复消费原子化 | 不继承 `MessagesState` 万能状态，不保存完整 messages，不为一个 pending task 暴露通用 reducer 体系 |
| 恢复为什么必须有硬预算和停止路径 | `agentic-rag-for-dummies/project/rag_agent/edges.py::route_after_orchestrator_call` | 在执行 Tool 前检查 iteration/tool budget，并显式进入 fallback/终止 | M36 固定为每个 pending checkpoint 最多一次成功 resume、每个 HTTP turn 至多一个 Tool；合并后仍需澄清则以预算 reason 结束 | 不照搬开放 Tool loop、LLM fallback answer、强制检索、`MAX_ITERATIONS/MAX_TOOL_CALLS` 参数或“有数据就尽量回答” |

这些源码能证明 clarification/checkpoint/budget 的局部机制，但不能证明 DataPilot 所需的 trusted caller 绑定、四轴、Evidence、安全投影和 closed-world Eval。后者仍以 Phase 4 roadmap、M29、M31–M35 的现有合同为准。

## 4. 目标、优先级与非目标

### 模块完成状态

`/api/query` 能增量表达一个 pending clarification：首次请求返回结构化待补字段和安全 thread 投影且不调用 Tool；同一可信 owner 带正确 checkpoint version 补齐字段后，系统原子消费该状态，构造最小当前任务 Context，再通过同一个 M35 Harness 完成一次 route → 至多一个深 Tool/terminal → controller。所有成功、拒绝和失效路径都能由 AgentResponse、JSONL Trace 与独立多 turn Eval 还原。

### 必须完成

- 冻结 thread/turn/pending clarification 的最小合同和安全公开投影，延续 G0=A 的同端点增量兼容。
- 支持至少两类 deterministic clarification fixture：缺主体/指代，以及分析问题缺时间范围或分组维度；首次均不得调用 Tool。
- 建立最小 checkpoint 生命周期：pending、原子 claim/consume、resolved/cleared、TTL expiry、进程重启丢失、state version 不兼容。
- 恢复时重新解析可信 caller，并以安全 owner ref 绑定 thread；错误 owner 不泄露 thread 是否存在或待补内容。
- 用 `expected_version` 做 optimistic concurrency；重复或并发旧恢复只允许一个请求取得执行权，其余不调用 Tool。
- 建立 Clarification Context Builder，只向 Router/Tool提供原任务、已确认条件和必要运行选项；不传完整历史或 Evidence 正文。
- 把一次恢复纳入顶层预算：一个 checkpoint 最多成功恢复一次，一个 turn 最多调用一个现有 SQL/RAG 深 Tool；仍不清楚或出现不可恢复失败时确定性停止。
- 新建版本化多 turn Harness Eval family；每个 accepted turn 只执行一次 compiled Graph，前置拒绝 attempt 为 0 次，多条 assertion 共享对应 ExecutionEvidence，并做 closed-world 序列完整性校验。

### 建议完成

- Streamlit 最小支持显示 clarification fields、thread/version，并提交一次结构化补充；不做聊天 UI 重构。
- 提供可注入 fake clock，使 TTL/过期测试不依赖真实等待。

### 条件触发

- **触发条件**：实现期间证明仅靠结构化 pending task 无法满足同一模块已冻结 Scenario，且问题来自 LangGraph 暂停/恢复语义而不是 Router 规则或 API 投影。
- **允许动作**：按 G-M36-1 重新打开原生 LangGraph interrupt/checkpointer 方案，并先补 owner、TTL、version、重启和 Trace 设计后再改默认。
- **未触发时**：不引入持久数据库 checkpoint，不启用 remote Router/query rewrite，不把自由文本历史交给模型压缩。

### 明确非目标

- P4 后续的 Document Evidence 复用/失效、SQL Evidence 跨轮复用、通用 follow-up、长历史 Context Builder 与多层 compact。
- 对 `retrieval_unavailable`、provider timeout、SQL driver 错误或 Knowledge zero-hit 自动重试；这些 reason 当前均不可因本模块获得恢复权限。
- P5 Hybrid、跨 Tool 补证据、P6 RAG Subgraph、query rewrite、parent/child、rerank 或 M34 context packing。
- 生产 JWT/OAuth/SSO、跨进程/跨实例会话、数据库持久 checkpoint、分布式锁与长期记忆。
- 修改默认模型、embedding、Knowledge adapter、outbound policy、LangFuse Cloud 或现有 M27/M31–M35 artifact。

## 5. 关键合同

本节只冻结 M36 新增的 turn/thread clarification interface；M35 C1–C6、roadmap 第 4 节、M29 reason registry 和既有 SQL/RAG 深 Tool 合同继续有效。

### C1：Pending Clarification

- 输入：本轮 `HarnessRequest`、可信 caller safe owner、Router 返回的 clarification decision，以及 closed-world clarification spec（问题文案、missing field keys、字段类型/约束）。
- 成功输出：一个 schema-versioned pending checkpoint 和安全公开投影；包含 opaque thread id、checkpoint version、状态、待补字段、过期时间及本轮 turn identity，不包含 Tool Observation/Evidence。
- 失败语义：clarification spec 未登记、字段不闭合或状态无法保存时 fail closed 为 `failed / no_answer / passed`，不返回一个无法恢复的假 thread。
- 必须保持的不变量：首次 clarification 不调用 Tool；thread id 不是授权；checkpoint 只保存当前任务、受控运行选项、已确认条件、owner ref、预算/版本/时间事实，不保存完整历史、SQL rows、文档正文、citation 或思维链。
- 本模块不冻结的实现细节：具体 dataclass/file 名、thread id 算法、内部容器布局和 TTL 数值；TTL 必须有限、可配置并进入 runtime identity/测试。

### C2：Owner、Lifecycle 与并发

- 输入：thread id、`expected_version`、本轮重新解析的 `TrustedCaller`、受控 clarification answers，以及可注入 clock。
- 成功输出：同一 owner 对 pending checkpoint 的一次原子 claim；成功消费后 version 单调推进并进入 resolved/cleared，不可再次触发 Tool。
- 失败语义：owner 不匹配统一安全投影为 conversation unavailable；missing/expired/restart-lost/cleared、state version incompatible、stale version、重复或并发 claim 使用稳定 reason，均在 Tool 前停止。owner mismatch 属安全失败；其余生命周期/冲突属于 execution/answer 失败，不借用 `blocked_reason`。
- 必须保持的不变量：检查顺序不能形成存在性侧信道；同一 expected version 最多一个恢复者成功；显式 clear 和 TTL 后不再恢复；进程内 checkpoint 丢失时如实返回不可恢复，不伪造 continuation。
- 本模块不冻结的实现细节：锁原语、清理扫描频率、HTTP 清理入口的具体路径；但显式清理必须可从应用 interface 调用并可测试。

### C3：Clarification Context Builder

- 输入：pending task、闭集 missing fields、与 spec 精确匹配的非空 typed answers，以及仍允许的本轮运行选项。
- 成功输出：供 Router/Harness 使用的最小 current task context，能区分原问题和用户确认条件，并保存可审计的 field/value 安全摘要。
- 失败语义：缺字段、额外字段、类型/长度非法或合并后仍触发 clarification 时，不调用 Tool；非法输入不消费 checkpoint，合并后仍不清楚则结束本 checkpoint 并返回 `budget_exhausted` 的安全投影。
- 必须保持的不变量：不使用自由文本 LLM rewrite；不覆盖原条件；不把历史消息、SQL rows、Document Evidence 或未授权事实带入 Router/Tool；SQL/RAG 内部仍只看到完成当前取证所需的输入。
- 本模块不冻结的实现细节：内部规范化 helper、展示文案和字段排序；不得提前冻结通用多轮 Context Builder interface。

### C4：单次有界恢复与唯一 Harness 事实

- 输入：C2 原子 claim 后的 checkpoint、C3 current task context、M35 `HarnessRuntime`。
- 成功输出：同一次恢复 turn 的唯一 `AgentRunResult`；route 后至多调用一个现有深 Tool，AgentResponse、Trace、Eval 只从该结果和 thread lifecycle fact 单向投影。
- 失败语义：恢复后的 route unsupported、Tool blocked/unavailable/failed 沿用 M35 四轴和 reason，不自动再次恢复；仍需澄清则预算耗尽并终止，不创建嵌套 pending checkpoint。
- 必须保持的不变量：thread module 不生成业务答案、不裁决 Tool Evidence、不重写 SQL/RAG 失败；API 不绕过顶层 Harness module；本模块只允许 clarification 这一种恢复动作。通过 owner/version/lifecycle 检查的 turn 恰好 invoke 一次 compiled Graph；被这些前置检查拒绝的 resume attempt 为 0 次 Graph/Tool，并由同一 Harness controller seam 形成闭合结果。
- 本模块不冻结的实现细节：Graph 是否增加独立 resume node、turn wrapper 的类名和拓扑展示形式；若采用 G-M36-1 方案 A，外部 seam 仍必须表现为一次 `run_turn`，不能让 API 手工拼状态迁移或自行构造四轴。

### C5：多 Turn Trace 与 Eval

- 输入：同一 thread 的 initial clarification turn、可选非法/冲突尝试和唯一成功 resume turn；每个 turn 各有独立 run/trace identity。
- 成功输出：安全 thread/turn/checkpoint ref、owner audit ref、前后 version、action、budget、Graph invocation count/steps、Tool count、终止 reason；Eval 用 sequence identity 把 initial/resume turn 与被拒绝的 lifecycle attempt 关联起来。
- 失败语义：sequence 缺 turn、重复 execution、version 不连续、成功 resume 多于一次或 assertion 集不闭合时，completed artifact 拒绝生成。
- 必须保持的不变量：每个被接受的 initial/resume turn 恰好一次 compiled Graph invocation；owner/version/lifecycle 前置拒绝为 0 次 Graph/Tool；两类路径都从同一 Harness controller seam 投影，Trace 不保存认证凭据、完整 checkpoint、原始思维链或 Document Evidence 正文；历史 M35 artifact 不补写新字段、不与新 family 混算。
- 本模块不冻结的实现细节：artifact 文件名、报告样式和 P7 最终 retention/debug bundle 方案。

## 6. 工作切片与执行顺序

### M36-A：开工快照、reason 与 notes 门禁

- 优先级：必须完成
- 依赖：G-M36-1 已确认；M35 已验收；当时最新 state/runbook。
- 实施内容：建立 `m36-notes.md` checklist；复核工作树、LangGraph 实际版本和受影响 API/Trace/Eval；把新增 lifecycle/owner/conflict reason 纳入 M29 registry 的同一闭集和公开安全投影。
- 关键合同：C1、C2、C5。
- 交付物：开工快照、reason/state 真值表、受影响 consumer 清单。
- 验证方式：静态 closed-world reason 测试；未知 code fail closed；四轴/公开文案非泄露审查。
- 完成门：没有用 HTTP 状态、异常文本或 `blocked_reason` 代替 lifecycle reason。

### M36-B：轻量 pending checkpoint 与 owner lifecycle

- 优先级：必须完成
- 依赖：M36-A；M31 `TrustedCaller`；G-M36-1 方案 A 时使用进程内实现。
- 实施内容：实现 C1/C2 的深 module；提供有限 TTL、schema version、opaque id、单调 version、原子 claim、resolve/clear 和 fake clock；应用组装层注入单一实例，不让 endpoint 直接操作字典。
- 关键合同：C1、C2。
- 交付物：pending checkpoint module、owner binding、lifecycle/concurrency 合同测试。
- 验证方式：new→pending→claim→resolved；wrong owner、missing、expired、cleared、restart-lost、incompatible、stale/repeated/concurrent version 表驱动测试；断言失败路径 Tool count 为 0。
- 完成门：一个 expected version 在并发测试中最多一个 claim 成功；删除 module 后这些规则会扩散到 API/Graph，证明 module 具有 Depth。

### M36-C：结构化 clarification 与最小 Context Builder

- 优先级：必须完成
- 依赖：M36-B；M35 Router/Harness seam。
- 实施内容：让 clarification decision 携带 closed-world spec；至少覆盖“缺主体/指代”和“分析问题缺时间范围或分组维度”；校验 typed answers，并生成最小 current task context。
- 关键合同：C1、C3。
- 交付物：clarification specs、Context Builder、deterministic Router fixtures。
- 验证方式：初次请求无 Tool；合法补充保留原条件并选择预期 SQL/RAG route；缺/多/非法字段不消费 checkpoint；合并后仍不清楚时预算停止。
- 完成门：Router/Tool 不读取完整 thread/checkpoint；测试只通过 C3 interface 观察输出，不穿透内部 helper。

### M36-D：有界 resume controller 与 Harness 接线

- 优先级：必须完成
- 依赖：M36-B/C；M35 `run_harness()`、深 Tool adapters。
- 实施内容：把现有 Harness module 加深为 turn-level orchestration seam；initial turn 创建 pending，resume turn 在 owner/version 检查和 claim 后调用同一 compiled Graph；前置拒绝也由该 seam 形成闭合结果。恢复后不再创建第二个 clarification checkpoint，Tool 失败不重试。
- 关键合同：C2、C4。
- 交付物：一次有界恢复链、预算/停止事实、Graph/turn 测试。
- 验证方式：SQL resume、RAG resume、仍不清楚、unsupported、Guard blocked、provider unavailable；逐条断言 resume count、Harness invocation 与 Tool call count。
- 完成门：一个 pending checkpoint 最多一次成功 resume；每个 accepted turn 最多一个 Tool；API/thread 存储层没有第二套答案/四轴裁决。

### M36-E：API、Trace 与最小 demo 投影

- 优先级：必须完成；Streamlit 输入交互为建议完成
- 依赖：M36-D；G0=A 兼容策略。
- 实施内容：为同一 `/api/query` 增量加入 pending/resume 输入和 thread 安全投影；提供可调用的显式清理 interface；Trace 记录 turn action、version、owner safe ref、budget 和终止原因；旧无 thread 请求保持 M35 行为。
- 关键合同：C1–C5。
- 交付物：兼容请求/响应、清理接线、JSONL Trace、可选 Streamlit 最小交互。
- 验证方式：TestClient 完成两 turn SQL/RAG；旧 M35 SQL/RAG/none fixture 不变；owner 篡改、stale version、clear/expiry 均不泄露、不调 Tool；response/Trace 指向同一 turn result。
- 完成门：旧调用者无需提供 thread 字段；新调用者能只凭安全公开投影完成一次恢复；thread id 不能绕过 caller resolver。

### M36-F：多 Turn Eval、回归与收工素材

- 优先级：必须完成
- 依赖：M36-A–E。
- 实施内容：建立新版本化 Eval family，覆盖 initial/resume/owner/version/expiry/clear/concurrency/budget/context fidelity；运行聚焦、M35、M31–M33 required 和受影响全仓 deterministic 回归；固化 notes/handoff。
- 关键合同：C1–C5。
- 交付物：sequence ExecutionEvidence、typed assertions、closed-world artifact validator、验证快照与 notes。
- 验证方式：见第 8 节；并发用 deterministic barrier/atomic assertion，不用 sleep 猜时序；accepted turn 与 lifecycle-rejected attempt 分别断言 Graph invocation 为 1 和 0。
- 完成门：所有 required sequence assertion 可由同次 turn 事实复核；未运行的真实 LLM/远程能力如实标为未证明。

## 7. 决策门

### G-M36-1：首个 clarification checkpoint 机制

#### 方案 A：应用持有的轻量进程内 checkpoint（建议）

- 做法：在 Harness 外围建立一个深的 turn/thread module，只保存 pending clarification 所需 typed state；API 调用该 interface，恢复后仍通过现有 `run_harness()` 得到唯一 `AgentRunResult`。存储先是进程内且明确可失效。
- 影响：保留 M35 已稳定的“一次 invoke → 一份闭合结果”interface，owner/TTL/version/并发规则集中且容易确定性测试；未来真的需要持久化时再形成第二个 storage adapter。
- 适用条件：M36 只做一次 pre-Tool clarification resume，不需要恢复任意 Graph 节点、Tool 中间态或 Evidence。
- 风险：没有直接展示 LangGraph 原生 interrupt/checkpointer；进程重启后 thread 明确失效，后续若进入持久 checkpoint 需单独迁移。

#### 方案 B：LangGraph `InMemorySaver` + interrupt/resume

- 做法：把 clarification 变成原生暂停点，以 thread config 和 resume command 继续 Graph；另加 wrapper 处理 caller owner、TTL、state version、并发和安全投影。
- 影响：更直接学习 LangGraph human-in-the-loop/checkpoint 机制，也为以后恢复 Graph 内部节点留下形态；但会把 M35 的 invocation/result 生命周期改成“可能 suspended”，API、Trace、异常关闭和测试都要适配两种返回形态。
- 适用条件：近期明确要演示 LangGraph 原生暂停/恢复，且愿意让 M36 承担 invocation contract 迁移成本。
- 风险：`InMemorySaver` 仍不自动提供 owner、TTL、幂等或生产持久化；wrapper 与 checkpointer 双状态容易漂移，模块范围更大，也更接近为未来能力预付复杂度。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：当前唯一真实缺口是“pending clarification 可安全恢复一次”，不是“任意 Graph 节点可持久恢复”。方案 A 把 owner、生命周期、并发和 Context 复杂度藏在小 interface 后，继续复用 M35 的闭合 `AgentRunResult`；也符合 roadmap 允许的“轻量 checkpoint”。
- 用户选择：2026-08-16 确认方案 A；M36 按应用持有的轻量进程内 checkpoint 实施，不启用 LangGraph 原生 interrupt/checkpointer。
- 用户确认前允许推进：只读调查、reason/Scenario/测试设计，以及本计划审查。
- 用户确认前禁止推进：创建 M36 notes 后的实现、修改 `/api/query` thread 字段、改变 Graph compile/checkpointer 或默认运行路径。
- 需要确认的时点：已于 M36 开工前完成。
- 重开决策的条件：后续真实需求必须恢复 Tool 中间态、Evidence 或任意 Graph 节点；进程重启恢复成为 required Scenario；或方案 A 无法满足本模块冻结的 clarification sequence。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 首次 pending | Router/turn module + fake Tool | clarification 返回闭合 spec/thread/version；compiled Graph 1 次、Tool 0 次；checkpoint 无 Evidence/正文/rows | 必须完成 |
| C2 owner 非泄露 | wrong caller/role/tenant/thread id 组合 | 不泄露 thread 是否存在或 pending 字段；Tool 0 次；安全四轴/reason 正确 | 必须完成 |
| C2 lifecycle | fake clock + restart/clear/version fixture | expiry、clear、missing/restart-lost、incompatible、stale version 均可预测且不恢复 | 必须完成 |
| C2 并发/幂等 | 两个相同 expected version 的并发 claim | 恰好一个成功；另一个冲突停止；深 Tool 总计最多 1 次 | 必须完成 |
| C3 Context fidelity | closed-world subject/time/group fixtures | 原问题与确认条件均保真；未知/额外字段拒绝；Router/Tool 看不到完整 checkpoint/history | 必须完成 |
| C4 SQL/RAG resume | fake SQL/RAG + 代表性 API fixture | 每个 resume turn 恰好一次 Harness；只调用预期深 Tool；四轴沿用 M35 | 必须完成 |
| C4 budget/stop | 合并后仍 clarify、Tool blocked/unavailable | 不创建嵌套 pending、不自动 retry；预算/原失败 reason 与终止动作可解释 | 必须完成 |
| C5 API/Trace | 两 turn TestClient 对照 JSONL | thread/turn/version/action/budget/owner safe ref 一致；无凭据、正文、checkpoint dump 或思维链 | 必须完成 |
| C5 Eval closed-world | 新 sequence artifact 篡改/缺 turn/重复 execution 反例 | accepted turn 各一次 Graph invoke，前置拒绝 0 次；version 连续；唯一成功 resume；required assertions 恰好闭合 | 必须完成 |
| M35 兼容 | M35 Harness/API/Trace/Eval suites | 无 thread 的 SQL/RAG/clarify/unsupported/caller fail-closed 语义不回归；旧 artifact 不改 | 必须完成 |
| P1/P2 安全回归 | M31–M33 required 聚焦 suites | caller/ACL/outbound/Evidence/citation 既有 required 合同全绿 | 必须完成 |
| 全仓确定性回归 | 受影响聚焦测试后运行全仓 pytest | 得到可靠终态；失败先定位，不用重复全量掩盖问题 | 必须完成 |
| 静态交付 | `compileall`、`git diff --check`、注释/interface 审查 | 无语法/空白错误；新增代码符合 AGENTS 注释；外部 interface 小于被隐藏的生命周期复杂度 | 必须完成 |
| Streamlit 最小交互 | 组件/人工检查 | 能展示待补字段并提交一次 resume，不重做聊天 UI | 建议完成 |

聚焦顺序：reason/thread contract → owner/lifecycle/concurrency → Context Builder → resume controller/Graph → API/Trace → sequence Eval → M35 → M31–M33 required → 受影响 API/Text2SQL/RAG → 全仓 deterministic pytest → compileall/diff check。Windows pytest 使用新的 `.agent_work/temp/<m36-basetemp>`。

本模块不自动运行真实 LLM Router/Text2SQL Eval、M34 external Answer Eval、Milvus/embedding、remote Composer/Judge 或 LangFuse Cloud。历史 M27、M31–M35 artifact 和 M34 profile/split 全部只读；新 sequence family 不与它们补字段或混算。人工验收重点是两 turn 演示、并发/过期/owner 反例和 Trace 回查，不把 deterministic clarification fixture 说成开放对话理解能力。

## 9. 依赖与交付物

### 依赖

- Phase 4 roadmap 的 P4/G5、状态/Context/安全/Eval 不变量，以及 G0=A 的增量响应策略。
- M29 四轴、trusted caller/thread owner 预留、reason registry 和 clarification Scenario 蓝图。
- M31 `TrustedCaller`/安全投影，M35 唯一 Harness、Router、深 Tool、`AgentRunResult`、API/Trace/Eval seam。
- G-M36-1 已确认方案 A；开工时按 `AI_CONTEXT` 必读规则重新检查 runbook/state。只有未来按重开条件改选方案 B 时，才需按项目实际 LangGraph 版本复核官方 interrupt/checkpointer interface。

### 交付物

- 一个有 Depth 的 pending clarification/thread lifecycle module，以及一次有界 resume 的 turn interface。
- 结构化 clarification spec、最小 Context Builder、owner/version/TTL/clear/concurrency 安全语义。
- `/api/query` 增量兼容投影、显式清理接线、多 turn JSONL Trace。
- 新版本化 sequence Eval family、required assertions、聚焦/回归测试和 `m36-notes.md` 素材。

交付物只冻结职责，不提前固定目录、类名、TTL 数值、锁实现或后续持久化 adapter。方案 A 下只有一个进程内实现时不先制造通用 storage port；等持久实现有真实入场条件时再形成第二个 adapter 和迁移合同。

## 10. 遗留与后续

- 本模块完成但刻意不处理：Evidence reuse/invalidation、SQL 跨轮复用、自由文本多轮追问、通用 Context Builder、Tool failure recovery、跨 Tool 补证据、持久/分布式 checkpoint。
- 下一模块可直接消费：thread/turn/owner/version/lifecycle 事实、原子 resume、最小 current task context、预算与 sequence Eval；后续可据真实失败决定继续 P4 的 Evidence 失效重取证，还是先补更一般的 Context Builder。
- 后续需要根据真实失败重新规划：哪些 reason 允许重新取证、是否需要第二次 clarification、是否引入持久 checkpoint、是否值得采用 LangGraph 原生 interrupt、长历史何时需要 compact。
- 可能存在的风险：deterministic clarification spec 对开放问法较窄；进程内状态会在重启后失效；前端若不回传 expected version 会频繁冲突；把 thread id 误当授权或把完整问题/回答无限存入 checkpoint 会重新制造安全与隐私旁路。

## 11. 开工条件

- 开工前无需确认：M36 对应 P4/G5 的首个 clarification 恢复切片；继续复用 M35 Router/深 Tool/`AgentRunResult`；每 turn 至多一个 Tool；不做 Evidence 复用、通用 retry、Hybrid、远程 Router 或默认切换。
- 实施中需要确认：无；G-M36-1 已于 2026-08-16 确认方案 A。若未来触发重开条件并考虑方案 B，必须先修订 M36-B/D/E 的 suspended Graph interface 与验证矩阵，再开始对应实现。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；特别是任何要信任 thread id/request role、持久保存完整历史/Evidence、恢复 Tool 中间态、启用远程 rewrite 或允许多次 Tool retry 的情况。
