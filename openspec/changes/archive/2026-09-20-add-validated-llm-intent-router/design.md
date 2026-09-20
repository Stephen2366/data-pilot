## Context

见 `proposal.md`。当前 Harness 已通过 `Router` protocol/runtime context 提供注入 seam，但默认实例是关键词驱动的 `DeterministicRouter`（`engine/harness/router.py:15-134`、`engine/harness/graph.py:60-73`）；`RouteDecision.decision_source` 只有 `deterministic/controller`（`engine/harness/contracts.py:239-268`）。API 组装层保留 `application.state.harness_router = None`，普通请求因此使用 deterministic 默认（`app/main.py:289`、`app/api/query.py:322-326`）。

现有 M35 Router Eval 只有固定 SQL/RAG/clarification/unsupported 场景，M38 Hybrid Eval 使用 fake Router 和固定计划；它们是控制合同证据，不是开放语义质量基线（`eval/harness_contracts.py:31-36`、`eval/harness_hybrid_contracts.py:23-39,146-191`）。2026-09-05 唯一登记的自然路由误判已经由确定性规则修复并通过单题 exploratory Probe（`docs/state/AI_CONTEXT.md:64`），但用户现已明确取消“必须先有稳定失败簇才能引入”的前置门。

共享硬约束继续来自当前代码和 state：Router 不读取 Evidence/Tool 输出；caller 未确认仍在 Router 前失败关闭；Hybrid 只执行已登记计划，两分支各至多一次；每个新增模型 purpose 必须独立通过 outbound policy，不能继承 Text2SQL 授权（`docs/state/AI_CONTEXT.md:44`、`docs/phase4b-roadmap.md` 的 receiver × purpose × data-class 约束）。

## Goals / Non-Goals

**Goals:**

- 在不交出 Tool 控制权的前提下，让模型处理开放、改写和词义重叠的顶层意图。
- 保留低延迟 deterministic fast path，并让模型失败时行为稳定、可解释、可回滚。
- 为 Router 建立独立出站授权、运行身份和 usage/latency 证据。
- 通过聚焦合同测试、真实纵向链 Probe 和受影响回归后，把 `llm_fallback` 作为服务端默认完成态。

**Non-Goals:**

- 不改 Phase 4B Turn Understanding、TaskDelta、next-action proposal 或 bounded Agent Loop。
- 不让模型生成 SQL、回答、RAG query rewrite、任意 Hybrid 分解或新 operator；本 change 只选择/编译现有顶层能力。
- 不修改 Text2SQL/RAG provider、模型、embedding、Knowledge release、数据库、ACL、深 Tool 预算或 Answer Eval 基线。
- 不建立通用 prompt/model registry、生产级多租户路由平台、自动在线学习或客户端可选 Router。

## Decisions

### D1：使用组合 Router，不做 model-only 替换

新增一个组合 Router，固定执行三步：

1. 本地前置裁决处理 caller/safety 已关闭路径、危险 SQL 交给 SQL Guard、缺对象/范围的 closed-world 澄清和 canonical fast path。
2. 对开放、冲突、重叠、deterministic `unsupported/hybrid_unsupported` 场景调用一次模型。
3. 将模型候选交给纯确定性 compiler；compiler 失败时返回调用前的保守决定。

选择理由：它复用现有 `Router` seam，不改变 LangGraph 拓扑；canonical 请求不增加延迟，模型不可用时仍有稳定行为。未采用 model-only，因为它会让已稳定的安全与 canonical 路径新增成本和 provider 单点；未采用继续扩关键词，因为用户已明确要求本 change 引入 LLM Router。

### D2：模型只分类，服务端拥有 RouteDecision

模型 schema 冻结为：

- `intent`: `sql | rag | hybrid | clarify | unsupported`
- `hybrid_operator`: 仅 `intent=hybrid` 时允许，值必须来自服务端 registry
- `clarification_kind`: 仅 `intent=clarify` 时允许，值必须来自服务端 registry

禁止自由 rationale 参与控制，也不接受 confidence 阈值、SQL、Tool 名、required terms、分支问题或答案。compiler 根据 intent 构造 `RouteDecision`：SQL 使用现有 SQL Evidence 语义；RAG 使用服务端受控默认 requirement；Hybrid 从 registry 取完整 `HybridPlan`；clarify 从 registry 取完整 `ClarificationSpec`；unsupported 形成 terminal 决定。

选择理由：DataPilot 的 `RouteDecision` 同时承载 Evidence、Hybrid plan 和终止不变量，不能把参考项目的字符串 route 直接当执行许可。未采用让模型自由拆 SQL/RAG 子问题，因为那会把本 change 扩张成 Hybrid planner，并绕开当前 operator 合同。

### D3：复用 transport，隔离 Router purpose 与调用实例

复用现有 OpenAI-compatible chat transport、错误归一化和 JSON response format，不复制 HTTP client。新增专用 client factory，为每次 Router attempt 创建隔离的 usage 计数实例，沿用当前服务端 provider/model，但强制：

- node purpose：`intent_route`
- data class：`router_prompt`
- fields：`prompt/system_prompt/model`
- retry：`0`
- temperature：`0`
- 单次决定 max model calls：`1`

Router prompt 由固定 taxonomy/operator catalog 和当前 question 构造；caller、role、tenant、history、Schema、rows、Document/Evidence 均不进入投影。选择独立 factory 是为了避免共享 client 的累计 usage 在并发请求间串线。

### D4：additive Router evidence，不污染 Tool evidence

为最终决定增加安全的 Router evidence：mode、router identity、decision source、attempt count、usage、latency、validation status、fallback reason。`decision_source` additive 扩展为 `deterministic/model/controller`；模型失败但 deterministic 结果生效时，source 仍是 deterministic，同时 evidence 记录 model attempt/fallback。

Router 调用不是 deep Tool，不进入 SQL/RAG Tool call count；但它必须进入 Trace 和 Eval consumption，不能成为隐藏调用。公开 `AgentResponse` 保持兼容，不新增 prompt/response 字段；历史 artifact 不回写、不重签。

### D5：服务端模式与完成时默认

新增 closed-world 服务端模式：

- `deterministic`：历史行为、回归 baseline 和一键 rollback。
- `llm_fallback`：本 change 的组合 Router。

不存在 `llm_only`，客户端请求/schema/MCP 均不能选择模式。开发期间先显式启用 candidate；只有 P1 Live Dev Probe、聚焦合同测试与受影响回归通过后，才将配置默认切到 `llm_fallback`。任一必需验证未通过时默认保留 deterministic，change 状态保持未完成。

### D6：展示型完成门，不建设独立 Router Eval 平台

用户于 2026-09-20 确认采用展示型收口：本 change 不再建设 40 题 decision set、paired runner、独立 artifact validator/report，也不以统计准确率门槛决定默认切换。原因是本项目目标是形成可运行、可讲解的 LLM Router 闭环；为单个路由改动额外建设一套 Formal Eval 基础设施会显著扩大交付面，而不会加强运行时的闭集编译、失败关闭或权限边界。

完成证据改为最小充分组合：表驱动 fake 测试覆盖全部候选类型、非法字段、失败降级、调用/Tool 预算和 Trace 私有载荷；真实 `LLMR-P1` 覆盖 SQL、RAG、Hybrid 三条纵向链；随后运行共享合同的受影响回归和一次全仓 deterministic 测试。Probe 只证明这三条开发场景可运行，不登记为质量基线，也不外推开放问法的总体准确率。

### D7：参考项目只做设计迁移，不直接复制代码

| Reference ID | 复核版本与许可证 | 采用 | 不采用及原因 |
|---|---|---|---|
| `ARAG-GRAPH` | `agentic-rag-for-dummies` `f4db3ddef0e2cf5ae1e3fcd91fd14bb9ce79a8ad`（`v2.3-1-gf4db3dd`），MIT | `graph.py`/`edges.py` 的显式 conditional edge、Tool/迭代预算、fallback/END；`graph_state.py` 的明确 reducer 责任 | 不采用主图+研究子图、fan-out、开放 Tool loop、MessagesState 大状态；DataPilot 顶层已有更深的 typed Tool seam |
| `DATAAGENT-GRAPH` | `DataAgent` `6f9ef46eebb55dceb566b030a2f163bde01b9b07`（`1.0.0-rc7-4-g6f9ef46`），Apache-2.0 | `IntentRecognitionNode` 的结构化模型 DTO、独立 dispatcher、空结果终止；`DataAgentConfiguration` 的显式 state key/conditional edge | 不复制 Java 代码和“闲聊/可能数据分析”二分类；taxonomy 太窄，且其大 NL2SQL 图会拆浅现有深模块 |
| `GUSTO-WORKFLOW` | `GustoBot` `e91b74d660dfd45d67267e4d2866ef6f0398e47e`（`v0.1.2-3-ge91b74d-dirty`），Apache-2.0；引用文件和 LICENSE 本身 clean | `KBRouteDecision` 的 structured output，以及模型 route 后由本地能力开关修正执行路径 | 不采用领域 Prompt、external fallback 和空 tools 自动改成 postgres+milvus；后者会把非法/拒绝候选变成宽权限执行 |

本 change 不直接复制第三方代码，因此没有 vendor 文件或本地 patch；实现时若实际复制任何表达性代码，必须在落盘前补充来源文件、commit、许可证头和本地改动说明。

### D8：Live Dev Probe

该 change 修改真实 LLM 与 `/api/query` 外部行为，Live Dev Probe 适用。冻结 checkpoint `LLMR-P1`：

- **时点**：完成首条 `question → Router model → deterministic compiler → Harness Tool → API/Trace` 真实纵向链并通过聚焦 deterministic 测试后；在默认切换和依赖这些证据的回归任务前执行。只有 `continue` 放行后续任务。
- **场景**：通过真实 `/api/query` 依次执行三题各一次：开放改写 SQL（预期 SQL 和正确受 Guard 结果）、政策材料 RAG（预期 RAG 和有效 citation）、已登记“指标值+定义”混合问法（预期 Hybrid、SQL/RAG 各一次）。使用当时项目默认 Qwen、数据库和已批准 Knowledge runtime；不访问 held-out/reserve，不改问法凑成功。
- **证据**：保存每题 request/response 安全投影、RouteDecision/Router evidence、Graph steps、Tool counts、citations、provider attempts/usage/latency、runtime identities、HEAD 与相关 dirty files；不得保存 prompt、原始模型响应、Thought 或凭据。
- **通过**：三题 route/operator/Tool budget 正确；SQL/RAG/Hybrid 结果分别满足现有 Guard/Evidence/citation 合同；Router 每题不超过一次、retry0、usage 完整；API/Trace 同源且无私有载荷。
- **三态**：全部满足为 `passed → continue`；语义、合同、安全、计量或超预算为 `failed → revise/stop`；provider/DB/Knowledge 依赖在形成语义判断前不可用为 `inconclusive → stop`。
- **整轮预算**：首次三题加上“定位 → 一次最小修复 → 只重验失败题一次”的全周期累计上限为 **12 次 provider attempts、50,000 observed tokens、12 分钟 wall time**。首次执行后只能在有明确代码修复落盘时重验一次；达到任一上限、identity 漂移、出现未登记 Tool/出站或安全泄漏立即停止。Probe 不是 Formal Eval，也不能登记 Router 质量基线。

## Risks / Trade-offs

- [模型提高语义覆盖但增加延迟和成本] → canonical fast path 零调用；fallback 单次/retry0；Trace 与 Eval 强制记录 usage/latency。
- [模型输出看似合法但控制含义错误] → 模型只选闭集标签；服务端 registry/compiler 拥有 requirement、plan、clarification 和 Tool 权限。
- [deterministic 快路继续吞掉应由模型判断的边界问法] → fast-path eligibility 用表驱动测试冻结，不能用新增 catch-all 扩张；真实 Probe 至少覆盖自然改写和指代场景，但本 change 不声明总体语义准确率。
- [provider 不可用导致体验退化] → 调用前保留保守决定；失败回到澄清/unsupported，不默认 Tool；deterministic 模式可立即回滚。
- [新 Router 调用成为隐藏成本] → 独立 per-request evidence、usage completeness 断言和 Trace 审计。
- [错误把三题 Probe 外推为总体质量] → notes/state 明示其仅为有限纵向证据；本 change 不生成或登记 Router 质量基线。

## Migration Plan

1. 先以 additive contract、outbound policy、Router evidence 和 `deterministic` 兼容模式落盘；默认行为不变。
2. 接入组合 Router 与 fake client tests，在显式 `llm_fallback` 模式完成聚焦验证。
3. 执行 `LLMR-P1`；未获 `continue` 不进入默认切换。
4. Probe、聚焦合同测试通过后切换服务端默认，运行受影响回归与唯一一次全仓完成门，更新 state/changelog/notes。回滚只需把服务端模式设为 `deterministic`，不删除 additive contracts 或重写历史证据。
