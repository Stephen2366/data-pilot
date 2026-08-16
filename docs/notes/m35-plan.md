# M35 顶层 LangGraph Harness 与 SQL/RAG Router 开发计划

> 状态：已确认可执行
>
> 能力里程碑：Phase 4 `P3`；本模块闭环 P3 的“单轮顶层 Harness + 保守 Router + SQL/RAG 受控 Tool + 四轴/API/Trace/Eval 投影”，不进入 P4 的 Loop、thread 和 Context Builder
>
> 主要问题：当前 SQL 与 RAG 各自能完成深链，但系统还没有一个真正控制 `/api/query` 的唯一顶层 Agent，无法稳定决定“该查数、查文档、澄清还是拒绝不支持请求”

## 1. 模块定义与范围判断

M29–M33 已先后建立 Phase 4 合同、可信知识、Evidence/安全发布、Knowledge Tool 和 `RAGAnswerFlow.run()`；M34 又证明独立大语料 profile 可复用这条链。用户本轮明确要求在 M34 补强后回归主线，因此 M35 按 `P0 → P1 → P2 → P3` 顺序进入顶层 Harness，不继续把 M34 的 lexical 漏召回和 multi-document packing 扩大成本模块。

本模块不拆成“只在内部测试里画 Graph”与“下个模块再接 API”两段。原因是：只要 `/api/query` 仍直接调 Text2SQL，LangGraph 就还不是唯一顶层控制者，route/execution/answer/safety 也会继续在新旧两条路径漂移。反过来，本模块也不扩到 P4/P5：首版只允许每轮最多调用一个证据 Tool，不做重试循环、澄清后恢复、Evidence 跨轮复用、Hybrid 或 checkpoint。

完成后，用户可以理解和验收：

- 一个问题如何先形成可审计 `RouteDecision`，再只调用 Text2SQL 或 RAG 中的一条深链；
- SQL 成功如何转成 typed SQL Evidence，RAG 如何原样复用已验证 AnswerFlow，且 Graph 不拆开它们的内部细节；
- 技术不可用、证据不足、安全拦截、澄清和不支持为什么是不同状态；
- `/api/query`、JSONL Trace 与 Phase 4 Eval 如何共用同一次 Graph 运行事实，而不是各自猜 route 或重跑 Tool。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| `/api/query` 当前直接进入 Text2SQL，`rag/hybrid` 只是响应枚举 | 没有真正 Router/Harness，RAG 虽已可用但 HTTP 用户不可达 | `app/api/query.py::query`、`app/schemas/agent.py::AgentResponse` |
| Text2SQL 技术失败和无 `tool_result` 分支当前被 API 统一包成 `safety_status=blocked` | execution 与 safety 继续混用，不符合 M29 四轴真值表 | `engine/nl2sql/pipeline.py::Text2SQLPipelineResult.safety_status`、`app/api/query.py::_blocked_response` |
| `make_sql_evidence()` 已冻结 SQL Evidence 类型，但尚未接入现有 SQL API | Graph 无法用统一 Evidence 语义记录 SQL 取证成功 | `engine/rag/evidence.py::make_sql_evidence`、`SQLEvidencePayload` |
| `RAGAnswerFlow.run()` 已完整返回四轴、Gate、ledger、answer 与 validated citations | P3 应直接复用这个深 interface，不应在 Graph 内重写 retrieval/composer/validator | `engine/rag/answer_flow.py::RAGAnswerFlow.run`、`RAGAnswerResult.safe_projection` |
| G4 已确认业务 Knowledge 默认为 `knowledge-deterministic-lexical-v1` | M35 可用 22 条业务 active release 做确定性 RAG 路径，不需要等 M34 外部 profile 优化 | `docs/state/rag-current-state.md`、`docs/state/AI_CONTEXT_CHANGELOG.md` M33 |
| M34 external profile 与 22 条业务 release 明确隔离，且 external 存在明显质量失败簇 | 不能把 external benchmark 默认接入产品 Router，也不能用 `complete` 充当 route/answer 正确性 | `docs/state/rag-current-state.md`、`docs/state/eval-baselines.md`、`docs/notes/m34-notes.md` |
| `user_role` 是请求体自报字符串；M31 已有 `TrustedCaller` 和 unverified/demo/test/authenticated adapter seam | P3 不能让 Router 直接把 `user_role=admin` 当成文档或 thread 权限，也不能在 SQL/RAG 之间使用两套互相矛盾的 caller 事实 | `app/schemas/agent.py::QueryRequest`、`engine/governance.py::TrustedCaller` |
| 项目 `pyproject.toml` 未直接声明 LangGraph，当前项目 Python 环境实测存在 `langgraph 1.1.2` | 不能依赖本机偶然安装；开工时要按当时官方 API 确认直接依赖与兼容范围 | `pyproject.toml`；项目 Python `importlib.metadata` 只读检查；[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) |
| Streamlit 和旧 API/Trace 测试依赖当前字段 | 四轴与 citations 必须增量迁移，不能删掉 `sql/rows/docs_used/safety_status` | `demo/streamlit_app.py`、`tests/test_m3_query.py`、`tests/test_m5_agent_response.py`、`tests/test_m16_trace_router.py` |

## 3. 参考源码定点复核

本模块的真实问题是“如何用少量有独立决策意义的节点，把两个已完成的深 Tool 收到一个唯一顶层控制者下”。因此按 `phase4-reference.md` 的 P3/Router 能力卡复核 Graph/state/conditional edge/fallback，不复制参考项目的业务链、Prompt 和多 Agent 平台。本次参考仓库 HEAD 为 ARAG `f4db3dde...`、DataAgent `6f9ef46e...`、GustoBot `e91b74d6...`。

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 顶层图只保留有决策意义的节点 | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph`、`edges.py::route_after_orchestrator_call` | `START`、conditional edge、fallback 与 `END` 显式表达控制权；超预算时不再执行 Tool | 收敛为 route → 唯一 Tool → controller/project 的单轮图；所有边的返回值使用闭集枚举/`Literal` | 不照搬主图+研究子图、fan-out、强制 search、query rewrite、history summary、context compact 和开放 Tool loop |
| Graph state 如何避免被节点隐式覆盖 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::AgentState / accumulate_or_reset / set_union / append_unique` | 为累计步骤、去重 key 和替换值明确 reducer 语义 | M35 状态默认单写入；只对 graph steps/tool observations 等真正需要累加的字段使用可复算 reducer，未声明的字段不并发写 | 不使用 `MessagesState` 作万能状态，不把完整历史、文档正文、DB Session 或模型消息放入可持久 State |
| 深模块接入 Graph 时如何分责 | `DataAgent/.../DataAgentConfiguration.java::nl2sqlGraph` | 节点、conditional dispatcher、repair/终止路径和 state key 替换策略都是显式的 | 只借鉴“控制边和深执行模块分开”；Text2SQL 继续作为一个 Tool，SQL Guard 不拆成 Graph 节点 | 不复制其 NL2SQL 内部十余个浅节点、PlanExecutor、Python 执行、人工审批和修复循环 |
| Router 未给出合法决定时应如何处理 | `GustoBot/.../multi_tool.py::router / router_edge / finalize / create_kb_multi_tool_workflow` | 结构化 route 与 conditional edge 使路径可观察；失败后有明确 finalize | DataPilot 的 Router 输出封闭 `sql/rag/none`；不确定、缺条件或不支持时进入澄清/不支持，不默认某 Tool | 不照搬“Router 没选 Tool 就 postgres+milvus 全调”、external fallback、末尾拼 `sources` 或以自然语言结果充当 typed Evidence |
| 依赖和运行对象如何不污染 State | LangGraph 官方 `StateGraph(..., context_schema=...)`、`Runtime.context`、`add_conditional_edges`、`compile` | runtime context 用于单次 invoke 的数据库连接/adapter 等依赖；State 保存会变的审计事实 | DB Session、Tool adapter、caller resolver 等放 run-scoped context；State 只留请求安全投影、四轴、Observation、EvidenceRef、citation 和终止事实 | 不依赖本机未声明包，不固定参考项目版本/参数，不在 M35 启用 checkpointer、interrupt 或 Store |

这些参考实现能证明 Graph 结构、state reducer 和 conditional fallback 的局部做法，不能证明 DataPilot 的四轴、trusted caller、SQL/Document typed Evidence、citation 和 Eval 合同。后者继续以 Phase 4 roadmap、M29–M33 代码和现有 required Gate 为准。

## 4. 目标、优先级与非目标

### 模块完成状态

`/api/query` 的新默认路径只通过一个已编译的 LangGraph Harness 运行；Router 为每轮形成结构化决定，只调用一个完整 Text2SQL 或 RAG Tool，或在不取证时返回澄清/不支持。成功、技术不可用、证据不足和安全拦截保留 route/execution/answer/safety 四轴真值，AgentResponse、JSONL Trace 和 Eval 从同一 Graph 结果投影。

### 必须完成

- 直接声明并验证 LangGraph 依赖，建立单轮、可编译、可注入、无 checkpointer 的顶层 Harness。
- 冻结 `HarnessRequest / RouteDecision / ToolObservation / AgentRunResult` 等最小跨节点合同，落实四轴、reason code、tool call count 和终止事实。
- 建立 deterministic/conservative Router：稳定识别代表性 SQL、RAG、clarification 和 unsupported 请求；未覆盖问题保守停止，不默认某 Tool。
- 将现有 Text2SQL pipeline 整体封装为 Tool adapter，正确区分 SQL Guard 拦截与 provider/执行失败；成功后构造 SQL Evidence 与稳定 result fingerprint。
- 将业务 22 条 active release 的 `RAGAnswerFlow.run()` 整体封装为 Tool adapter，原样保留 Gate/Composer/Validator 与安全投影。
- 让 `/api/query` 经 Harness 运行，增量提供 `execution_status`、`answer_status`、结构化 `citations` 与安全 reason，保留旧 SQL/表格/图表/`docs_used` 兼容投影。
- 在 API 组装层建立 caller resolver seam：请求体 role 只是 requested role，必须由明确 demo/test/authenticated adapter 解析为 `TrustedCaller`；未解析时失败关闭。
- 建立独立 Harness/Router Eval family 和 API/Trace 回归，每个 Scenario 只运行一次 Graph，多断言共享这份 ExecutionEvidence。

### 建议完成

- 让 Streamlit 显示新四轴与 citations，但不重做 UI 架构或视觉改版。
- 提供可读 Graph 拓扑快照或结构断言，便于用户检查没有隐藏边、嵌套循环或浅节点。

### 条件触发

- **触发条件**：deterministic Router 在已冻结 dev 题上出现可复现的边界失败，且用户明确批准 Router 的 receiver × `router` node purpose × query/caller-safe fields 出站。
- **允许动作**：以同一 `RouteDecision` interface 加入结构化模型 candidate，只在确定性快路无法裁决时使用；解析失败/超时保守澄清，并以独立 identity/A-B 比较。
- **未触发时**：不调用远程 Router，不因现有 Qwen Text2SQL 已授权就继承 Router 出站权限。

### 明确非目标

- P4 的 Tool retry/recovery loop、澄清后同 thread 恢复、Evidence 跨轮复用/失效、Context Builder、checkpointer 与并发冲突处理。
- P5 Hybrid；M35 的 Router 对同时要求 SQL+RAG 的问题保守标记未支持/需要后续能力，不偷跑两支再拼文本。
- P6 RAG Subgraph、query rewrite、parent/child、hybrid retrieval、rerank 或 M34 external recipe/context packing 改进。
- 生产 JWT/OAuth/SSO、企业用户目录、持久会话平台和通用记忆。
- 默认模型、embedding、Knowledge adapter、M34 external profile、M27 v3 catalog/artifact 或 LangFuse Cloud 切换。
- 真实 LLM Router Eval、M34 180 题 Answer Eval 重跑或 Text2SQL 真实 LLM 全量基线。

## 5. 关键合同

本节只冻结 M35 新增的单轮控制 seam。Phase 4 跨里程碑不变量、M29 四轴/reason registry、M31 Evidence/安全、M32 Knowledge Tool 和 M33 AnswerFlow 仍以原事实源为准，不在本计划重新定义。

### C1：单轮 Harness 输入与唯一控制权

- 输入：问题、run/trace identity、`TrustedCaller`、已解析 active SQL role、受控运行选项，以及通过 runtime context 注入的 DB Session/Tool adapters。
- 成功输出：一份闭合 `AgentRunResult`，包含四轴、稳定 reason、RouteDecision、最多一份 ToolObservation、安全 Evidence/ledger 投影、用户结果与终止事实。
- 失败语义：合同未知、route/edge 非法、Tool 返回未登记 reason 或结果不闭合时 fail closed 为可识别的 contract failure；不返回半成品答案。
- 必须保持的不变量：顶层 Graph 是跨 Tool route、最终四轴、公开投影和终止的唯一裁决者；单轮最多执行一个证据 Tool；节点不读写隐式全局可变业务状态。
- 本模块不冻结的实现细节：具体文件/类名、TypedDict/dataclass 的选择、Graph 拓扑展示方式和非合同性能参数。

### C2：Router 决定与保守停止

- 输入：问题和最小 caller/task 事实；不包含文档正文、SQL rows、完整历史或 Tool 内部状态。
- 成功输出：结构化 `RouteDecision`，route 只能为 `sql/rag/none`，并携带决定来源、稳定 reason、是否需要取证、RAG Evidence requirement 的受控投影或 clarification/unsupported 终止动作。
- 失败语义：重叠冲突、信心不足、未覆盖意图或候选 Router 不可用时，保守返回 `none + clarification_required/unsupported`，不默认 SQL/RAG，不一次返回多个 route。
- 必须保持的不变量：Router 不调 Tool、不看 Evidence 正文、不生成答案、不改 ACL/预算；`hybrid` 在 M35 不是可执行 route。
- 本模块不冻结的实现细节：具体关键词/规则、阈值、Prompt、远程模型或 Router 候选 identity；这些只能由 dev 失败证据驱动。

### C3：Text2SQL ToolObservation 与 SQL Evidence

- 输入：问题、run/trace identity、经 caller resolver 确认且属于 `resolved_roles` 的单个 active SQL role、DB Session 和现有 pipeline 选项。
- 成功输出：现有 Text2SQL 深 pipeline 的结构化 Observation；Guard 通过且执行成功时，从实际 SQL/columns/rows/runtime 构造 SQL Evidence，按真实消费阶段记录 ledger，再产生表格/图表/答案投影。
- 失败语义：SQL Guard/policy 拒绝是 `execution=completed + safety=blocked`；QueryPlan/provider/SQL 执行等技术不可用是 `external_unavailable/failed + safety=passed`（除非同时有独立安全失败）；不再用 `blocked_reason` 吞掉技术失败。
- 必须保持的不变量：不拆 Schema Retrieval/QueryPlan/SQL Guard/execution；不绕过 Guard 构造 Evidence；结果 fingerprint 由规范 columns/rows 稳定计算，不伪造不存在的数据 snapshot identity。
- 本模块不冻结的实现细节：重构 Text2SQL 内部步骤、改模型/检索/数据库默认或增加 SQL 跨轮复用。

### C4：RAG ToolObservation 与 AnswerFlow 复用

- 输入：问题、`TrustedCaller`、run identity、受控 `AnswerEvidenceRequirement`、现有业务 RAG budget/adapter。
- 成功输出：`RAGAnswerFlow.run()` 的四轴、稳定 reason、validated answer/citations、safe ledger/gate/diagnostics 投影；`docs_used` 只从 validated citations 派生。
- 失败语义：完全沿用 M33 的 zero-hit、evidence insufficient、ACL、stale revision、retrieval/composer unavailable、prompt injection 和 citation invalid 语义；Graph 只校验映射是否闭合，不二次裁决答案充分性。
- 必须保持的不变量：只使用 22 条业务 active release 默认路径；不默认启用 M34 external profile/remote Composer；Graph 不重写 Gate、Composer 或 Citation Validator。
- 本模块不冻结的实现细节：Knowledge Tool 内部索引、retrieval recipe、top-k、parent/context expansion 和语义 Judge。

### C5：Caller 解析与 active role

- 输入：请求的 requested role/caller metadata 与应用组装层注入的 demo/test/authenticated resolver。
- 成功输出：`TrustedCaller` 和一个明确 active SQL role；active role 必须是 `resolved_roles` 成员，不得按“权限最大”隐式选择。
- 失败语义：无 resolver、caller 未验证、requested role 不在 resolved roles、多角色却没有明确 active role 时，在 Tool 前失败关闭为 `caller_untrusted`，不暴露任何文档或数据库存在性。
- 必须保持的不变量：请求体 `user_role` 不能单独提升权限；demo/test 信任必须在 runtime/Trace 中如实标记；SQL 与文档权限共享 caller 事实但不共享 allowlist 实现。
- 本模块不冻结的实现细节：生产认证 provider、token/JWT 格式、企业目录、tenant 管理和 thread owner。

### C6：AgentResponse、Trace 与 Eval 单向投影

- 输入：唯一 `AgentRunResult` 及其安全 Evidence/diagnostics 投影。
- 成功输出：AgentResponse 增加四轴所需字段和结构化 citations，保留 G0=A 的旧字段兼容视图；JSONL 增加 route decision、graph steps、caller safe ref、Tool Observation、EvidenceRef、四轴与终止事实；Eval 只读同次运行证据。
- 失败语义：投影不能表达合同状态时 fail closed；技术不可用不写成 safety blocked，未验证 claim/citation 不进入公开答案。
- 必须保持的不变量：`docs_used` 只从 citations 派生；`blocked_reason` 只服务安全文案；`error_type` 只是兼容诊断，不反向驱动 controller；Trace 不保存模型思维链。
- 本模块不冻结的实现细节：P7 的完整 retention/debug bundle 管理、LangFuse Cloud 恢复和 UI 大改。

## 6. 工作切片与执行顺序

### M35-A：开工事实、依赖与 notes 门禁

- 优先级：必须完成
- 依赖：G-M35-1 已确认方案 A；M34 已验收；当时 `AI_CONTEXT`/runbook 与工作树。
- 实施内容：建立 `docs/notes/m35-notes.md` implementation checklist；记录 Git/依赖/环境快照；按当时官方 API 复核 `StateGraph`、runtime context、conditional edge 和 compile；将 LangGraph 收入项目直接依赖，不依赖本机透传安装。
- 关键合同：C1、C6。
- 交付物：notes 快照、直接依赖、最小 import/compile 验证。
- 验证方式：干净进程 import 和最小 Graph compile；项目依赖文件静态检查。
- 完成门：新环境不再需要手工预装 LangGraph，且未提前启用 checkpoint/store。

### M35-B：四轴 Graph state 与单轮拓扑

- 优先级：必须完成
- 依赖：M35-A；M29 四轴/reason registry。
- 实施内容：建立 Harness input/state/output/runtime context；实现 `START → route → (sql_tool | rag_tool | terminal) → controller/project → END` 的最小拓扑；对非法边、多 Tool Observation、缺终止事实做 fail-closed 校验。
- 关键合同：C1、C6。
- 交付物：可编译 Harness、状态/结果合同、拓扑结构测试。
- 验证方式：注入 fake Router/Tool 执行每条边；断言每轮最多一个 Tool call、所有路径可终止、状态不被 reducer 隐式覆盖。
- 完成门：移除任一有决策意义节点会破坏合同；不存在只转发参数的浅节点。

### M35-C：保守 Router 与终止分支

- 优先级：必须完成
- 依赖：M35-B；M29 canonical Scenario 意图。
- 实施内容：实现可注入 Router interface 与首个 deterministic adapter；覆盖代表性 SQL、政策/指标口径 RAG、缺时间/对象澄清、明确副作用请求拒绝；冲突/未知时保守停止。
- 关键合同：C2。
- 交付物：RouteDecision adapter、固定路由 fixture/dataset、边界与冲突测试。
- 验证方式：表驱动方式断言 route/reason/Tool call count；对不支持的 Hybrid 问题断言不运行两个 Tool。
- 完成门：每条 fixture 的决定可复现，无广泛 catch-all 默认 SQL/RAG，无真实 Router 出站。

### M35-D：Text2SQL/RAG 受控 Tool adapter

- 优先级：必须完成
- 依赖：M35-B/C；现有 Text2SQL pipeline、SQL Evidence 和 `RAGAnswerFlow` 合同。
- 实施内容：包装两条深 interface；为 SQL 成功结果生成 result fingerprint/SQL Evidence/ledger；建立 Text2SQL 错误到四轴的显式映射；RAG 只做 `RAGAnswerResult` 的闭合校验和 Graph Observation 安全投影。
- 关键合同：C3、C4。
- 交付物：SQL/RAG adapters、SQL Evidence 接线、failure mapping registry、聚焦合同测试。
- 验证方式：注入 fake provider/DB/AnswerFlow；验证 SQL success/Guard/provider unavailable/execution failure 与 RAG success/zero-hit/ACL/stale/unavailable/citation invalid。
- 完成门：Graph 不依赖两个 Tool 的内部节点；每类失败的 execution/safety 可区分；只有 Guard 成功的 SQL 能形成 Evidence。

### M35-E：Caller resolver、API 与兼容投影

- 优先级：必须完成
- 依赖：M35-B–D；G-M35-1。
- 实施内容：在应用组装层注入 caller resolver；将 `/api/query` 新默认路径切到 Harness；增量扩展 AgentResponse 并将旧 SQL/RAG 字段单向投影；保留 `force_new_pipeline=false` 的诊断能力为 Text2SQL adapter 内部选项，不让它绕过顶层 Harness。
- 关键合同：C1、C5、C6。
- 交付物：API caller seam、扩展 AgentResponse/citation schema、单一 response projector、Streamlit 最小兼容更新。
- 验证方式：TestClient 注入 demo/test resolver；验证 SQL/RAG/none 响应，role tamper 失败关闭，技术错误不再误标 blocked，旧字段仍可消费。
- 完成门：`/api/query` 不再存在绕过 Harness 的 SQL/RAG 默认路径；请求体 role 无法单独提升权限。

### M35-F：Graph Trace 与独立 Harness Eval

- 优先级：必须完成
- 依赖：M35-B–E；M27/M31–M33 Eval 完整性纪律。
- 实施内容：扩展 JSONL 安全投影以记录 route/graph/tool/four-axis/termination/EvidenceRef；新建 Harness 独立版本化 Eval family，覆盖 SQL/RAG/clarification/unsupported/caller tamper/Guard/tool unavailable/route exclusivity/Trace 一致性；对 completed artifact 做 closed-world 完整性。
- 关键合同：C1–C6。
- 交付物：Graph Trace 投影、ExecutionEvidence/assertions/artifact/Gate、对应测试。
- 验证方式：每题恰好一次 Graph invoke；同题 route/tool/state/evidence/trace 断言引用同一 execution ref；技术不可用按 `not_observed` 规则投影开放能力，但确定性降级合同仍可判定。
- 完成门：required contract/security Gate 全部可观测并通过；旧 `phase4-v1`、retrieval/answer family 和 M27 artifact 无改写/混算。

### M35-G：回归、结构审查与收工素材

- 优先级：必须完成
- 依赖：M35-A–F。
- 实施内容：运行聚焦测试、M31–M33 required Gate、API/Text2SQL/RAG 回归、全仓确定性回归与 compileall/diff check；检查 Graph 无浅节点/双控制权/隐藏循环；按 `finish-module` 固化 notes。
- 关键合同：C1–C6。
- 交付物：验证快照、决策/失败/注释素材、handoff。
- 验证方式：见第 8 节矩阵；Windows 下使用 fresh `.agent_work/temp/<m35-basetemp>`，超时或权限问题不伪写成测试通过。
- 完成门：实现、测试、Graph 拓扑和 notes 一致；未运行的真实 LLM/远程服务如实列为未证明。

## 7. 决策门

### G-M35-1：`/api/query` 的 demo caller 组装方式

#### 方案 A：显式 local/demo resolver，其他环境失败关闭（建议）

- 做法：应用组装层在明确 local/demo/test 运行模式下注入 `demo_caller/test_caller` resolver；请求体 `user_role` 只作为 active role 选择，必须属于 resolver 给出的 roles。非 demo/test 或没有 authenticated resolver 时失败关闭。
- 影响：保留当前学习/演示体验，同时让 Trace 如实显示 `demo_fixture`；未来接生产认证时只替换 resolver，Harness/Tool 合同不变。
- 适用条件：当前项目主要是本地学习与 demo，且 roadmap 明确允许 Phase 4 首版使用如实标记的 demo/test adapter。
- 风险：环境模式配置错误可能让部署误以 demo 身份运行；必须增加启动/安全测试和清晰的非生产标识，默认不声称生产认证。

#### 方案 B：所有运行都必须外部显式注入 resolver

- 做法：`create_app()` 不自动提供 demo resolver；测试、演示和任何本地 API 启动者都必须手工注入 caller resolver，否则 SQL/RAG 取证均拒绝。
- 影响：失败关闭最彻底，但当前 `uvicorn app.main:app` 和 Streamlit 默认体验会中断，还需要额外的安全组装入口。
- 适用条件：近期就要接入真实认证 provider，或用户愿意牺牲当前默认 demo 启动体验。
- 风险：为了“先跑起来”，后续开发者可能在 API 内部偷加回请求体 role 直信，反而重建旁路。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：它同时满足 roadmap 的 trusted caller seam 和当前本地学习/demo 目标；信任层级是显式事实，不伪装成 production auth。
- 用户选择：2026-08-16 确认方案 A；M35 实施时按“显式 local/demo/test resolver + 其他环境无可信 resolver 则失败关闭”落地。
- 用户确认前允许推进：只读调查、合同/测试设计和依赖复核。
- 用户确认前禁止推进：实现 `create_app()` caller 默认组装、切换 `/api/query` 默认路径或更改现有 role 行为。
- 需要确认的时点：已于 M35 开工前完成。
- 重开决策的条件：引入真实认证 provider、要求非本地部署、修改 role/tenant 模型，或安全测试证明 local/demo 组装容易误用。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 拓扑/唯一控制权 | Graph compile + topology/edge 单测 + fake Tool invoke | 所有路径可达 `END`；单轮最多一个 Tool call；无 API 默认旁路、无隐藏循环 | 必须完成 |
| C2 Router | 冻结 SQL/RAG/clarification/unsupported/conflict 数据集 | route/reason/action 精确符合 fixture；未知问题不默认调 Tool；Hybrid 不偷跑双支 | 必须完成 |
| C3 SQL adapter/Evidence | fake provider + SQLite/Test Session + Guard 反例 | success 有稳定 SQL Evidence/fingerprint；Guard 前无 Evidence；Guard blocked 与 technical unavailable 四轴不混用 | 必须完成 |
| C4 RAG adapter | M33 成功/失败 fixture 通过 Graph 再跑 | AnswerFlow 每轮恰好一次；四轴/reason/citations/ledger 不被 Graph 改写；失败不泄露 | 必须完成 |
| C5 Caller | resolver/role tamper/多角色/无 resolver 反例 | request role 不能单独授权；active role 必须属于 resolved roles；demo/test 信任在 runtime/Trace 可识别 | 必须完成 |
| C6 AgentResponse | TestClient SQL/RAG/none/safety/technical failure | 新四轴/citations 正确；旧 SQL/rows/chart/docs_used 兼容；`blocked_reason` 不承载技术失败 | 必须完成 |
| C6 Trace | 同一 trace id 对照 Graph result/JSONL | route/steps/tool/four-axis/termination/EvidenceRef/caller safe ref 一致；无文档正文、未授权 ref 或思维链 | 必须完成 |
| C1–C6 Harness Eval | 新独立 family completed artifact + closed-world validator | 每题一次 invoke；selected Scenario/execution/assertion/identity 恰好闭合；required Gate passed | 必须完成 |
| 旧 P1/P2 合同 | M31/M32/M33 聚焦 required suites | 既有 12/12、20/20、60/60 required 语义不回归 | 必须完成 |
| API/Text2SQL/RAG 回归 | 受影响聚焦 pytest → 全仓 deterministic pytest | 聚焦先通过；全仓得到可靠终态，否则如实记为 inconclusive/失败 | 必须完成 |
| 静态交付 | `compileall`、`git diff --check`、注释/拓扑审查 | 无语法/空白错误；新代码符合 AGENTS 注释规则；拓扑与 plan 一致 | 必须完成 |
| Streamlit 最小展示 | 手工/组件级检查 | 新状态/citation 可读；旧 SQL 展示不中断 | 建议完成 |

聚焦验证顺序为：Graph/state/Router → Tool adapters → API/caller/Trace → 新 Harness Eval → M31–M33 required 回归 → 受影响 Text2SQL/API/RAG 回归 → 全仓 deterministic pytest → compileall/diff check。Windows pytest 每次使用新的 `.agent_work/temp/` basetemp，不删除受锁历史目录。

本模块不自动运行真实 LLM Router、Text2SQL Eval、M34 external Answer Eval、Milvus/embedding、remote Composer/Judge 或 LangFuse Cloud。历史 M27 v1/v2/v3 artifact、M31–M34 artifact 和 M34 external split/profile 全部只读；不为新 Graph 补写旧字段，不与 Harness family 混算。

## 9. 依赖与交付物

### 依赖

- 已确认 Phase 4 roadmap、G0=A、G4=A 和 M29 四轴/reason registry。
- M31 `TrustedCaller`/ACL/outbound/Evidence/release，M32 Knowledge Tool，M33 `RAGAnswerFlow.run()` 与 22 条业务 active release。
- 现有 Text2SQL pipeline、SQL Guard、SQL Tool、Trace 和 `/api/query` 兼容合同。
- G-M35-1 已确认方案 A。
- 开工时按 `AI_CONTEXT` 必读规则重新检查当时 runbook/state；涉及依赖 API 时以当时 LangGraph 官方文档和项目实际版本为准。

### 交付物

- 单轮顶层 LangGraph Harness、四轴 state/result 和 deterministic Router。
- Text2SQL/RAG 两个受控 Tool adapter、SQL Evidence 接线与稳定 failure mapping。
- caller resolver/active role seam 与 `/api/query` 增量兼容投影。
- Graph 安全 JSONL Trace 与独立 Harness Eval family/required Gate。
- 聚焦/回归测试，必要的 Streamlit 最小兼容更新，以及 `m35-notes.md` 的决策、验证与 handoff 素材。

本节不提前固定具体目录、文件、类名、路由规则、Graph 拓扑绘图工具或性能参数；它们由实施时的深模块边界和测试反馈决定。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：P4 恢复循环/thread/Context Builder，P5 Hybrid，P6 Subgraph go/no-go，生产认证，M34 召回/context packing 优化，远程 Router 和 LangFuse Cloud。
- 下一模块可直接消费的产物：唯一 Harness invocation seam、四轴 Agent state、RouteDecision、ToolObservation、SQL/Document EvidenceRef、caller/run identity、终止原因和 Harness Eval Scenario。
- 后续需要根据真实失败重新规划的内容：P4 首个恢复切片 G5；deterministic Router 的模型 fallback 是否值得授权；M34 lexical/multi-document 候选是否进入新 recipe A/B。
- 可能存在的风险：Router 规则在开放问法上过窄；Text2SQL 历史错误分类不足以完整区分 unavailable/failed/blocked；API 兼容投影可能让旧客户忽略新四轴；demo caller 模式如果标识不清会被误认为生产认证；LangGraph 依赖版本与本机预装版本可能漂移。

## 11. 开工条件

- 开工前无需确认：M35 对应 P3；复用完整 Text2SQL pipeline 和 `RAGAnswerFlow.run()`；使用 22 条业务 release 的 deterministic RAG 默认；G0=A 增量扩展 `/api/query`；单轮最多一个 Tool；不做 P4/P5/P6/M34 优化/远程 Router。
- 实施中需要确认：无；G-M35-1 已确认方案 A。若触发本计划的远程 Router、长期默认切换或新安全边界，再按对应条件单独确认。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；特别是任何要默认启用远程 Router、信任请求体 role、接入 M34 external profile、启用 Hybrid/Loop 或改动长期默认的情况。
