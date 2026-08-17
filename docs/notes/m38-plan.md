# M38 保守 Hybrid 双 Evidence 编排开发计划

> 能力里程碑：Phase 4 `P5`；本模块一次闭环保守 Hybrid 的完整纵向基线，包括薄计划、SQL/RAG 双分支、原始 typed Evidence 汇合、required branch、partial/conflict、Synthesizer 降级、双来源 citation、Trace/API 与 sequence Eval；完成后可按 roadmap 口径验收 P5，但不等于开放式跨数据源研究 Agent
>
> 主要问题：当前 Harness 遇到同时需要数据库事实和业务规则的问题只会返回 `hybrid_unsupported`，既不能取得两类 Evidence，也没有在分支失败、证据冲突或合成器不可用时安全保留独立成立结果的统一合同

## 1. 模块定义与范围判断

### P4 关闭口径

M37 单独不等于 P4，但 M36 与 M37 已共同完成 roadmap 定义的 P4 最小可验收基线。下表冻结本轮选择 P5 的依据，不把更宽会话能力误写成 P4 欠账。

| P4 条款 | 已有闭环 | 结论 |
|---|---|---|
| 有界 controller、预算、可枚举停止和无增量不重试 | M36 一次 resume budget、原子 claim、拒绝零 Graph/Tool；M37 一次 follow-up budget、SQL/external 强制重取证、业务 Document 窄重水化 | 已完成 P4 必需基线 |
| 澄清后从同一 thread 恢复并保留已确认条件 | M36 的 subject / analytics scope closed-world Context Builder、owner/version/TTL/clear/concurrency/state-version 合同 | 已完成 P4 必需基线 |
| 基于上一轮结果的有限追问与 Evidence 复核 | M37 显式 opt-in 的一次 SQL/RAG follow-up；旧 Evidence 只作有效性输入，新 run 重新授权并形成新 Evidence/citation | 已完成 P4 必需基线 |
| Context 输入与循环事实可由 Eval 直接检查 | `phase4-harness-turn-v1` 8 sequences；`phase4-harness-followup-v1` 10 sequences / 22 turn evidence / 50 required | 已完成 P4 必需基线 |
| 第二次成功追问、自由文本长历史、多层 compact | roadmap 未列为 P4 硬门；长会话 compact 明确属于 Phase 4 后能力 | 不为关闭 P4 扩建 |
| 持久 checkpoint、多 worker 共享、生产认证 | 分别是条件能力与 Phase 4 后部署门；当前 required Scenario 未触发 | 不为关闭 P4 扩建 |
| 跨 route / 跨 Tool 补齐另一类 Evidence | 当前最有价值的落点就是 P5 Hybrid 的显式双分支计划，而不是继续藏在 follow-up 中 | 由 M38 正式承接 |

因此 M38 不再机械增加追问轮数，而是进入主干 `P4 → P5`。用户确认本 plan 与 G-M38-1 后，`AI_CONTEXT.md` 已同步为：“M37 单独不等于 P4，但 M36 + M37 已共同完成 roadmap 定义的 P4 最小可验收基线；不宣称通用多轮。”

M38 按一个完整模块推进，而不拆成“先让 Graph 调两个 Tool”和“以后再补 partial/conflict”。只实现双 Tool 会留下最危险的部分——缺一支仍给完整建议、冲突静默消解、合成失败重跑分支——无法形成可独立理解和验收的 P5 故事。

完成本模块后，用户可以理解、演示和验收：

- Router 如何把混合问题变成很薄的双分支计划，而不是让 SQL QueryPlan 升级成万能计划；
- SQL 与 RAG 深 Tool 如何各执行至多一次，并把同一 run 的原始 typed Evidence 交给唯一 Hybrid controller；
- 为什么跨来源结论默认必须同时绑定 SQL Evidence 与 Document Evidence；
- 一支失败、权限拒绝、两支冲突或 Synthesizer 失败时，系统如何只保留安全且独立成立的 partial，而不伪造完整建议；
- 响应、Trace 与 Eval 如何从同一次 Hybrid 运行证明分支使用、Evidence/citation、预算和终止事实。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| 内部 `Route`、`RouteDecision` 与 `AgentRunResult` 只支持 `sql / rag / none`；deterministic Router 把混合问法投影为 `hybrid_unsupported` | `AgentResponse.route=hybrid` 只是公开枚举占位，当前没有可执行 Hybrid 合同 | `engine/harness/contracts.py`、`engine/harness/router.py::DeterministicRouter.decide`、`tests/test_m35_harness.py` |
| M35 Graph 固定为 `route → 单个 sql_tool/rag_tool/terminal → controller`，每轮至多一个 ToolObservation | 不能在同一 Harness run 中表达两条分支、每支状态、汇合与两次总预算 | `engine/harness/graph.py::HarnessState / build_harness / _controller_node` |
| SQL adapter 已构造完整 `Evidence`，RAG `RAGAnswerResult` 的 ledger 也持有完整 Document Evidence，但 `ToolObservation` 只上送 rows、答案和 EvidenceRef/安全投影 | Hybrid Synthesizer 若只消费现有 Observation，就只能拼两个子答案或缺少可验证的原始 Document Evidence；若把完整 Evidence 塞进公开投影，又会扩大泄露面 | `engine/harness/adapters.py::_sql_observation / RAGToolAdapter.run`、`engine/rag/answer_flow.py::RAGAnswerResult`、`engine/rag/evidence.py::Evidence` |
| 单路 RAG Tool 当前运行完整 `RAGAnswerFlow`，包含 Gate、Composer 与 Citation Validator | Hybrid 不能再消费该自然语言子答案后生成第二份答案；Hybrid RAG 分支需要复用取证与 Gate，但把最终跨来源 claim 留给唯一 Synthesizer/Validator | `engine/rag/answer_flow.py::RAGAnswerFlow.run`、roadmap P5 控制权不变量 |
| 默认 outbound policy 只登记 Text2SQL chat 与 Schema embedding；没有 Hybrid synthesis 的 receiver/purpose/data class | 远程 Synthesizer 当前必须失败关闭，不能继承现有 Qwen 或 M34 public benchmark 授权 | `engine/governance.py::DEFAULT_OUTBOUND_POLICY`、`docs/state/AI_CONTEXT.md` |
| M29 已有“完整 Hybrid / Hybrid partial”蓝图，但旧 `eval/cases_plan.md` 仍把 `knowledge_docs` 当 SQL 表，且没有可运行 Hybrid scorer | 旧候选题不能直接升级为 canonical P5 Eval；M38 必须基于当前 authority、SQL oracle 和 Evidence 合同重新冻结 Scenario | `docs/notes/m29-phase4-entry-contract-plan.md`、`eval/cases_plan.md` |
| M34 已暴露 lexical 漏召回、多文档 packing 与 Composer support rejection，但这些属于 P6/单变量 RAG 增强证据 | 不能把检索优化或 RAG Subgraph 混进 M38，借 Hybrid 顺手改变默认 RAG profile | `docs/state/eval-baselines.md`、`docs/state/rag-current-state.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 薄计划如何保留全局控制权并显式进入执行/报告阶段 | Alibaba DataAgent，`DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java::nl2sqlGraph`，尤其 `PLANNER_NODE → PLAN_EXECUTOR_NODE → SQL/PYTHON/REPORT` conditional edges | 计划、执行、汇合/报告是显式状态迁移；dispatcher 只允许登记过的下一节点 | 只保留一个很薄的 `HybridPlan` 和 SQL/RAG 两个既有深 Tool；controller 依据 branch observation 决定合成、partial、conflict 或停止 | 不复制 EvidenceRecall→SchemaRecall→Planner→Python→Report 平台，不引入任意 Python、repair loop、Human Review 或 MySQL checkpoint；参考图也不能证明 DataPilot 的双 Evidence/citation 合同 |
| 多来源结果如何汇合，以及哪些 fallback 会破坏 required branch | GustoBot，`GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py::create_kb_multi_tool_workflow / local_search / finalize / _collect_sources` | 观察本地/外部结果分开保存、最终节点统一汇合，以及核心结果可在生成失败时保留的思路 | SQL/RAG 分支分别保存 typed status 与 Evidence；Synthesizer 失败时保留已经安全成立的分支视图，不重跑 Tool | 不照搬 postgres 命中即跳过 Milvus、空 tools 自动兜底、local/external 自动降级、截断文本拼 Prompt、末尾拼 `sources`；它不是 SQL + Document Hybrid，也没有 required/optional、claim-level 双 Evidence、ACL 非披露或 conflict 合同 |

参考源码与 roadmap 没有形成新的范围冲突。它们能支持固定状态迁移和失败降级的局部设计，但 P5 的 branch requirement、四轴、Evidence/citation、安全和 Eval 仍以 DataPilot roadmap 与现有合同为准。

## 4. 目标、优先级与非目标

### 模块完成状态

M38 完成后，`/api/query` 能在现有顶层 Harness 内处理一类明确的 SQL + RAG 混合请求：Router 产生薄计划，两个深 Tool 各至多执行一次，controller 只用本轮 typed SQL/Document Evidence 决定完整回答、partial、conflict 或停止。所有用户可见跨来源 claim 都能回到所需 Evidence；分支失败或 Synthesizer 失败不会重跑已经成功的分支。

### 必须完成

- 正式加入 `hybrid` 内部 route、薄 `HybridPlan`、双分支状态与父级预算，保持 SQL/RAG 单路行为兼容。
- 在不扩大公开/长期 Trace 投影的前提下，建立 Harness 内部可消费的 typed Evidence branch result；禁止 Hybrid 消费两个自然语言子答案。
- SQL/RAG 分支默认都标为 required；M38 不触发 G6 optional 放宽。
- 覆盖完整成功、SQL-only safe partial、RAG-only safe partial、权限非披露、conflict、Synthesizer unavailable/invalid 和分支失败停止。
- 建立 Hybrid claim-to-Evidence validator：跨来源结论至少绑定一份本轮 SQL Evidence 与一份本轮 Document Evidence；单来源 partial 只能生成计划明确允许的独立 claim。
- 接入现有 Harness、API、Trace 与 caller/safety/outbound seam，不另建 Hybrid endpoint 或旁路 controller。
- 新建版本化 Hybrid sequence Eval；一题一次执行，多断言共享同一 run evidence，completed artifact closed-world 校验。
- 同步 P4 正式关闭口径和 M38/P5 当前状态，但不改写 M27、M31–M37 或 M34 历史 artifact。

### 建议完成

- Streamlit 增加一个完整 Hybrid、一个 partial/conflict 的最小演示视图，优先展示两类来源和“不能下的结论”，不建设报告平台。
- 为分支执行顺序/并行方式保留内部 seam；只有聚焦证据显示值得并行且 DB/session 与 Trace 安全时才实现并行，本计划不以并行为验收条件。

### 条件触发

- **触发条件**：G-M38-1 已选择方案 A；只有后续满足第 7 节重开条件，用户重新选择远程或双 adapter，并明确批准 receiver、`hybrid_synthesis` 节点用途、问题/SQL safe result/Document Evidence/identity 等数据类别与字段时，才进入远程分支；对应真实 provider 验证另有一次精确运行授权。
- **允许动作**：实现与本地 adapter 同合同的结构化远程 Synthesizer、transport 前 outbound 强制门、输出 validator、provider failure 降级和独立 runtime identity；如需默认切换，再准备可比 held-out 证据。
- **未触发时**：不新增 Hybrid 远程白名单，不发送 SQL rows、Document Evidence 或完整问题；正式 deterministic adapter 作为 P5 默认，不把它称为临时桩。

### 明确非目标

- 第二次 follow-up、Hybrid follow-up、跨会话记忆、长历史 compact、持久 checkpoint 或生产认证。
- P6 RAG Subgraph、query rewrite、parent/child、hybrid retrieval、rerank、M34 context packing 或 semantic 默认切换。
- 远程 Router、开放式任务分解、并行 fan-out、多 Agent、Python 分析、长报告或图表增强重构。
- G6 optional branch 放宽；M38 可以在计划结构中保留 required/optional 语义，但首个 canonical Hybrid 跨来源结论的 SQL/RAG 都是 required。
- 自动解决业务规则冲突，或把模型判断当作权限、Evidence 完整性和 conflict 的最终裁决。

## 5. 关键合同

### C1：薄 HybridPlan 与 Router 合同

- 输入：当前问题、trusted caller、已确认条件和本轮预算；Router 不接收正文、SQL rows、旧答案或 Tool Observation。
- 成功输出：`route=hybrid` 的闭合计划，至少声明两个 branch 的类型、Evidence requirement、required 标记、跨来源 claim 目标、允许的独立 partial claim，以及稳定 plan identity。
- 失败语义：混合意图不完整时 clarification；不支持的跨能力动作返回 unsupported；plan 未登记 branch、重复 branch、空 requirement 或 optional 未获 G6 放行时，在 Tool 前失败关闭。
- 必须保持的不变量：Router 只计划、不执行 Tool、不生成答案、不决定权限；Text2SQL QueryPlan 与 RAG requirement 继续只服务各自深模块。
- 本模块不冻结的实现细节：规则 Router 的具体词表、plan 类名和未来远程 Router；canonical 题面与 closed-world plan 必须可确定性复现。

### C2：双分支执行、预算与 typed Evidence 合同

- 输入：有效 HybridPlan、同一 trusted caller/run、SQL/RAG 深 Tool 与父级预算。
- 成功输出：两个独立 `BranchResult`，各含 branch execution/answer/safety/reason、调用次数、内部 typed Evidence/ledger 和安全投影；父级记录每支恰好零或一次执行。
- 失败语义：未执行、技术不可用、证据不足和安全拦截保持分支级四轴；一个分支失败不触发另一个分支重跑，也不把失败文本当 Evidence。
- 必须保持的不变量：SQL/RAG 单路仍最多一个深 Tool；Hybrid 最多各一次、总计最多两个不同深 Tool；两支共享 caller 但不共享 ACL 实现；内部完整 Evidence 不直接进入 AgentResponse 或长期 Trace。Hybrid 的 RAG 分支复用 Knowledge Tool 与 Shared Gate，但不先生成一份最终 RAG 子答案再交给 Synthesizer。
- 本模块不冻结的实现细节：分支串行或安全并行、内部结果容器类名和 Graph 节点的精确拆分。

### C3：required branch、partial 与全局四轴合同

- 输入：HybridPlan 与两个 BranchResult。
- 成功输出：两支 required Evidence 都可用时才允许跨来源 `complete`；一支失败时，只能输出 plan 预先声明、由另一支 Evidence 独立支持且不会泄露失败分支存在性的 `partial`。
- 失败语义：无独立 claim 时为 `insufficient_evidence` 或 `no_answer`；安全拦截分支的标题、EvidenceRef、命中数和内部 reason 不进入另一支 partial；全局 execution 反映整条 Hybrid flow，分支 execution 保留 root cause。
- 必须保持的不变量：`complete` 不能靠 best-effort 降低 required；global safety 只表示最终公开结果是否通过安全裁决，不抹掉内部 branch safety；partial 必须明确已有事实、缺失证据以及不能下的跨来源结论。
- 本模块不冻结的实现细节：公开文案和 reason code 的最终命名，但必须 closed-world、机器可判且不泄露被拒分支。

### C4：Hybrid Synthesizer、conflict 与双来源 citation 合同

- 输入：仅限 Gate 允许的本轮 typed SQL/Document Evidence、HybridPlan、已确认条件和 claim 预算；不得消费两个分支的自然语言 answer。
- 成功输出：结构化 claim drafts；跨来源 claim 显式绑定至少一个 SQL 和一个 Document evidence_id，单来源 partial 只绑定其合法来源；Validator 通过后产生 typed SQL/Document citation 用户视图和最终 claim。
- 失败语义：同一 plan fact key 的结构化值/适用条件出现不可调和冲突时，输出 `hybrid_evidence_conflict`，展示允许公开的冲突与来源但不生成建议性跨来源 claim；Synthesizer unavailable、非法输出、伪 Evidence ID、错 run、缺任一来源或 citation 不闭合时，丢弃跨来源草稿，并按 C3 保留安全 partial 或停止。
- 必须保持的不变量：conflict 由确定性可复核 facts/validator 裁决，模型不能静默选边；Synthesizer 失败不重跑 SQL/RAG；SQL citation 至少指向本轮 query/result identity，Document citation 延续 revision/anchor/authority 合同。
- 本模块不冻结的实现细节：自然语言模板、claim 类名和未来远程 Prompt；G-M38-1 已冻结本模块采用正式本地确定性结构化 Synthesizer。

### C5：唯一 Harness、API 与 Trace 投影合同

- 输入：initial Hybrid request；M38 不接受 Hybrid resume/follow-up。
- 成功输出：现有 Graph invocation seam 中的 `hybrid` 路径、branch steps、父子预算、最终四轴、typed citations、表格/图表兼容视图和安全 Trace；API 仍只调用 `run_turn`/Harness 出站事实。
- 失败语义：plan/lifecycle 前置拒绝为零 Tool；branch 或 synthesis 失败按 C2–C4 投影，不调用隐藏 fallback endpoint，不回退成单路 complete。
- 必须保持的不变量：API、Trace、Eval 只从同一 AgentRunResult/Hybrid result 单向投影；默认 Trace 不保存 Document 正文、完整 SQL rows、远程 Prompt、思维链或未授权分支存在性；M37 follow-up eligibility 仍只覆盖其已登记 SQL/RAG 合同。
- 本模块不冻结的实现细节：公开 citation 的展示字段顺序、Graph 节点名与 Streamlit 布局。

### C6：Hybrid sequence Eval 与完成身份合同

- 输入：完整、partial、conflict、ACL/安全、Synthesizer failure、预算与篡改 Scenario；每题一次真实 Harness execution。
- 成功输出：branch plan/use/status、Tool count、Evidence kinds/stages、claim support、citation、partial/conflict、outbound、四轴、runtime identity 和终止事实的 typed assertions；selected Scenario/execution/assertion/policy/runtime 恰好闭合。
- 失败语义：漏 branch、重复 Tool、缺 assertion、跨 run Evidence、用子答案冒充 Evidence、required 缺失仍 complete、conflict 被静默合成、ACL 侧信道、合成失败后重跑或 runtime/outbound identity 不匹配时 completed artifact 拒绝生成。
- 必须保持的不变量：不为每个 assertion 重跑 Tool；新 family 不补写或混算 M27、`phase4-v1`、M31–M37、M34 artifact。
- 本模块不冻结的实现细节：artifact 文件名、报告排版和 P7 总 capability matrix。

## 6. 工作切片与执行顺序

### M38-A：P4 关闭、开工快照与 Hybrid 真值表

- 优先级：必须完成
- 依赖：M37 已验收；本 plan 与 G-M38-1 方案 A；最新 state/runbook。
- 实施内容：建立 `m38-notes.md` checklist；按第 1 节正式同步 P4 关闭口径；核对工作树与现有 consumers；冻结 HybridPlan、branch/父级四轴、reason、budget、partial/conflict 与 follow-up 非目标真值表。
- 关键合同：C1–C6。
- 交付物：P4 验收映射、Hybrid 状态矩阵、consumer/敏感字段清单、state 修正。
- 验证方式：closed-world 枚举与未知值 fail-closed 合同测试；反向检索旧 `hybrid_unsupported` consumer。
- 完成门：P4 不再因第二次追问/持久化被错误标为未完成；Hybrid complete/partial/blocked/insufficient/conflict 各有唯一四轴解释。

### M38-B：HybridPlan、内部 Evidence seam 与 branch result

- 优先级：必须完成
- 依赖：M38-A；现有 RouteDecision、SQL Evidence、Knowledge Tool/Shared Gate 和 RAGAnswerFlow。
- 实施内容：扩展内部 route/plan；让 SQL/RAG adapter 在 Harness 内提供完整 typed Evidence branch result，同时保留现有安全投影；为 Hybrid RAG branch 提供“取证 + Gate、停止在跨来源合成前”的深接口，避免先生成 RAG 子答案。
- 关键合同：C1、C2。
- 交付物：薄计划、branch observation/evidence bundle、单路兼容 adapter。
- 验证方式：typed payload、run/allowed-use/stage/authorization、无自然语言子答案消费、公开/Trace 无正文与 rows 泄露测试。
- 完成门：Synthesizer 能只通过受控内部 interface 取得两类原始 Evidence；删掉该 seam 会迫使 Graph 解析 RAG/SQL 内部对象或 API 保存敏感 Evidence。

### M38-C：现有 Graph 内的双分支预算与 controller

- 优先级：必须完成
- 依赖：M38-B。
- 实施内容：在现有 Harness 加入 hybrid edge/branch/join；每支最多一次；controller 按 required branch 与安全矩阵决定进入 Synthesizer、partial、conflict 检查或停止；保持 SQL/RAG/none 路径不变。
- 关键合同：C1–C3、C5。
- 交付物：Hybrid Graph 路径、branch use/status、父子预算与停止 reason。
- 验证方式：完整/单支失败/ACL/两支失败/异常分支输出/重复调用反例；Graph topology 与调用计数测试。
- 完成门：没有 API 旁路、隐式 fallback、第三次 Tool 或分支失败后的重跑；单路仍符合 M35–M37 预算。

### M38-D：正式 Synthesizer adapter、conflict 与 citation validator

- 优先级：必须完成
- 依赖：M38-B/C；G-M38-1 已确认的方案 A。
- 实施内容：按用户选择实现正式 adapter；冻结 claim/support binding、结构化 conflict fact 和 SQL/Document typed citation；非法或不可用时按 C3 降级。若选择远程方案，先完成精确 outbound 决策与 transport 前强制门。
- 关键合同：C3、C4。
- 交付物：Synthesizer interface/adapter、Hybrid claims、conflict decision、双来源 validator 与 runtime identity。
- 验证方式：跨来源 claim 双绑定、单来源 partial、伪造/错 run/错 kind/错 anchor/缺支、冲突、provider unavailable/invalid output、outbound deny 测试。
- 完成门：完整 Hybrid claim 可同时回到真实 SQL result identity 与当前 Document revision/anchor；移除任一绑定时 validator 必须拒绝。

### M38-E：API、Trace 与安全投影

- 优先级：必须完成；Streamlit 为建议完成
- 依赖：M38-C/D。
- 实施内容：把 Hybrid result 增量投影到现有 AgentResponse、ToolCallTrace、JSONL Trace 和图表/表格兼容字段；展示 branch summary、partial/conflict 和 typed citations；明确 Hybrid 不签发 M37 follow-up-ready thread。
- 关键合同：C3–C5。
- 交付物：同端点 Hybrid 响应、安全 Trace、可选 demo 视图。
- 验证方式：TestClient 完整/partial/conflict/ACL/synth failure 对账；Trace 敏感字段与 denied branch 非披露检查。
- 完成门：响应、Trace 与 controller 使用同一事实；旧 SQL/RAG/clarification/follow-up 客户端合同不回归。

### M38-F：版本化 Hybrid sequence Eval

- 优先级：必须完成
- 依赖：M38-E。
- 实施内容：新建独立 Hybrid contract family；至少覆盖完整“数据事实 + 退款规则”、完整“指标值 + 指标口径”、SQL-only partial、RAG-only partial、ACL 非披露、SQL safety、conflict、Synthesizer failure、预算和 citation 篡改；从当前 authority 与 SQL oracle 重新冻结题面，不复用旧 `knowledge_docs` SQL 蓝图。
- 关键合同：C1–C6。
- 交付物：sequence execution evidence、typed assertions、closed-world validator、required Gate 与安全失败归因。
- 验证方式：同题唯一执行；branch/Tool/Evidence/claim/citation/status/runtime/outbound 对账；缺失、额外、重复和篡改 artifact 全部拒绝。
- 完成门：完整 P5 基线的所有 required assertions 通过；partial/conflict 不是靠最终文本关键词猜测，而由 typed facts 判断。

### M38-G：回归、注释与技术收工素材

- 优先级：必须完成
- 依赖：M38-A–F。
- 实施内容：依次运行 M38 专项、M35 Harness、M36/M37 turn、M31–M33 安全/RAG、受影响 API/Text2SQL、Phase 4 Eval 与全仓 deterministic 回归；完成静态检查、注释审计与 notes 素材固化。
- 关键合同：C1–C6。
- 交付物：可靠验证终态、`m38-notes.md`、state/changelog/runbook 命中清单和 finish-module 素材。
- 验证方式：见第 8 节；超过 2 分钟的全仓测试按 AGENTS 后台任务规则执行。
- 完成门：required 合同全绿；未运行的远程/真实 LLM 能力明确标为未证明，然后进入 `finish-module`。

## 7. 决策门

### G-M38-1：首个 Hybrid Synthesizer adapter 与出站边界（已确认）

#### 方案 A：正式本地确定性结构化 Synthesizer（用户已选择）

- 做法：实现稳定 `HybridSynthesizer` interface，并以 closed-world HybridPlan/operator、结构化 branch facts 和 typed Evidence 生成 claim；模板只是 adapter 的展示层，cross-source binding、partial/conflict 和 citation 均由代码合同裁决。
- 影响：M38 可在不新增数据出站的情况下完成完整 P5 控制与安全基线；结果可复现、易归因，适合 canonical 业务演示。该 adapter 是正式默认和长期 fallback，不是“先凑一个简单版”。
- 适用条件：当前首要目标是证明可信双 Evidence 编排；业务 Scenario 能把跨来源操作表达为受控 plan/operator。
- 风险：开放问法和自然语言推理覆盖较窄；未登记的跨来源关系必须 clarification/unsupported，不能宣称通用 Hybrid reasoning。

#### 方案 B：正式远程 Qwen 结构化 Synthesizer

- 做法：实现同一 interface 的远程 adapter；只输入 Gate 允许的 question/conditions、SQL safe result view、Document Evidence 与 identity，要求结构化 claim/support binding，再由本地 validator 裁决。新增精确 receiver/purpose/data-class/field outbound rules。
- 影响：自然表达和开放跨来源归纳更强，更接近真实 Agent 演示；但问题、SQL 结果和文档片段会同时离开本地，provider/模型失败会新增 `external_unavailable + partial/no_answer` 分支。
- 适用条件：用户明确批准 Qwen（或指定 receiver）的 `hybrid_synthesis` 用途及每类字段；能够为真实 provider 验证提供一次精确运行授权，并接受调用成本与波动。
- 风险：当前默认 policy 没有任何对应授权；M34 public benchmark policy 不能复用。单次效果不能证明默认化，模型也不能裁决 ACL、required branch、conflict 或 citation 真实性。

#### 方案 C：同模块实现双 adapter，确定性默认、远程作为候选

- 做法：A/B 都实现；本地承担 required Gate 与 fallback，远程只在明确配置/授权下运行；默认是否切远程需另用未污染 held-out、多轮可比证据决定。
- 影响：学习和对照最完整，但 M38 同时增加 adapter、出站、安全、真实运行与 A/B 工作，显著扩大模块规模；在没有 Hybrid held-out 与远程授权时，候选只能停在未验证状态。
- 适用条件：用户希望 M38 同时承担 P5 基线与远程 Synthesizer 实验，并愿意追加数据授权、时间和 provider 预算。
- 风险：容易把 P5 控制合同和模型效果实验混在一起；未授权或未跑真实 Eval 时，第二个 adapter 只有代码存在，不能宣称质量提升。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：P5 的核心难点是双 Evidence、required/partial/conflict 和单一控制权，而不是自然措辞；当前 Hybrid 出站为明确 deny。把 A 做成正式 adapter 能完整验收 P5，又保留未来 B 的同合同替换点，不制造“临时实现债”。
- 用户选择：2026-08-17 确认方案 A；M38 实现正式本地确定性结构化 Synthesizer，不新增 Hybrid 数据出站。
- 用户确认前允许推进：已确认，可按本 plan 开工。
- 用户确认前禁止推进：不再阻塞方案 A；但禁止顺手实现 B/C、修改 Hybrid outbound policy、外发 question/SQL rows/Document Evidence、运行远程 smoke/Eval 或改变默认 adapter。
- 需要确认的时点：已完成。
- 重开决策的条件：canonical Hybrid 无法用受控 operators 表达；真实开放问法形成稳定失败簇；用户批准精确出站范围且已有未污染 held-out 与可比 provider 预算。

G6 optional branch 放宽在 M38 不触发：首个跨来源结论的 SQL/RAG 都保持 required。未来只有 Eval 证明某一类分支确属展示增强且不会误导或产生侧信道，才另行提交用户决策。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| P4 关闭口径 | roadmap P4 条款对 M36/M37 plan/notes/Eval 的静态映射 | 每个必需条款有真实实现/证据；条件项和 Phase 4 后能力未被冒充欠账；state 不再歧义 | 必须完成 |
| C1 Router/HybridPlan | 表驱动 SQL/RAG/Hybrid/clarify/unsupported 与非法 plan | 混合题产生唯一薄计划；Router 零 Tool/零正文；未知/optional 未放行失败关闭 | 必须完成 |
| C2 branch budget | fake SQL/RAG Tool 计数与 Graph topology | 单路 ≤1 Tool；Hybrid SQL=1、RAG=1、总计≤2；任一失败不重跑 | 必须完成 |
| C2 typed Evidence | SQL/Document payload、ledger、run/allowed-use/authorization/stage 检查 | Synthesizer 只见本轮 Gate 允许 Evidence；不读两个子答案；公开/Trace 不泄露完整 payload | 必须完成 |
| C3 complete | 两支成功的 deterministic canonical Scenario | 只有两支 required Evidence 都可用时为 complete；跨来源 claim 明确双绑定 | 必须完成 |
| C3 SQL-only partial | RAG no candidate/unavailable，SQL 独立 claim 可成立 | 只返回 SQL 事实、缺失政策依据和不能下的结论；不伪造规则/citation | 必须完成 |
| C3 RAG-only partial | SQL external unavailable，Document 独立 claim 可成立 | 只返回一般规则，不声称已针对实际数据成立；SQL failure 不伪装 safety blocked | 必须完成 |
| C3 ACL 非披露 | required RAG branch 被文档 ACL 拒绝 | 无 title/revision/ref/hit count/内部 reason 泄露；另一支只按显式 safe-partial policy 输出或停止 | 必须完成 |
| C3 SQL safety | SQL Guard/语义安全拒绝 + RAG 可用 | 不借 RAG 答案淡化危险请求；全局与 branch safety 按真值表一致，无跨来源结论 | 必须完成 |
| C4 conflict | 同 fact key 的不一致结构化 SQL/Document fixture | 返回稳定 conflict 状态/来源，不静默选边、不生成建议性跨来源 claim | 必须完成 |
| C4 Synthesizer failure | unavailable、非法 JSON/shape、超预算、伪 Evidence、错 run/kind/anchor | 草稿不公开；不重跑分支；仅保留允许的独立 partial 或停止 | 必须完成 |
| C4 双来源 citation | 删除 SQL 或 Document binding、伪 citation slot、inactive revision | 任一篡改均被 deterministic validator 拒绝；正常 claim 可回查两类 Evidence | 必须完成 |
| C5 API/Trace | TestClient 与 JSONL 对同一 run 对账 | branch status/use、预算、claim/citation、四轴、runtime/outbound 一致；无正文/完整 rows/denied side channel | 必须完成 |
| C5 M35–M37 兼容 | 既有 Harness、turn、follow-up、API/Trace suites | SQL/RAG/none、clarification/resume/follow-up 行为不变；Hybrid 不产生 follow-up thread | 必须完成 |
| C6 sequence Eval | 新 family 正常与篡改 artifact | 每题一次运行；required assertions 全通过；漏/重/额外/错 identity 均拒绝 completed | 必须完成 |
| M31–M33 安全/RAG | caller/ACL/outbound/Evidence/citation required suites | 既有 required Gate 全绿；Hybrid 未形成 Knowledge/SQL 安全旁路 | 必须完成 |
| 全仓 deterministic 回归 | 聚焦通过后执行全仓 pytest | 获得可靠终态；失败先定位修复，不重复全量掩盖 | 必须完成 |
| 静态交付 | `compileall`、`git diff --check`、注释/敏感字段/interface 审查 | 无语法/whitespace 错误；新增代码符合 AGENTS 注释；无禁止数据落盘 | 必须完成 |
| Streamlit 演示 | 组件/人工检查 | 能区分完整、partial、conflict，并显示 SQL/Document 两类安全来源 | 建议完成 |

聚焦测试顺序：plan/route/reason → branch result/typed Evidence → Graph/预算 → required/partial/conflict controller → Synthesizer/validator → API/Trace → Hybrid sequence Eval → M35 → M36/M37 → M31–M33 → 受影响 Text2SQL/RAG/API → 全仓 deterministic pytest → compileall/diff check。Windows pytest 使用新的 `.agent_work/temp/m38-*` basetemp；预计超过 2 分钟的全仓验证按 AGENTS 后台任务规则执行。

若选择方案 A，本模块不运行真实 Hybrid LLM、远程 embedding/Milvus、M34 external 大评测、M27 真实 Text2SQL Eval、LangFuse Cloud 或 P6 Subgraph 实验。若选择 B/C，远程运行仍须遵守 runbook 的一次精确授权，不能因 plan 获批自动扩大到大评测。历史 M27、M31–M37、M34 artifact 全部只读，新 family 不补字段或混算。

## 9. 依赖与交付物

### 依赖

- M36/M37 已验收并共同满足 P4 最小基线；M35 唯一 Harness/Router/深 Tool/四轴；M31–M33 trusted caller、Evidence/ACL/outbound、Knowledge Tool、Shared Gate、Composer/citation。
- Phase 4 roadmap P5 的 required branch、partial/conflict/增强降级和 G6 边界；第 4 节 Evidence/状态/安全/Context/Eval 不变量。
- 当前 22-entry 业务 knowledge release、现有 SQL oracle/SQLite fixture 与 `metrics.yaml` 派生说明；M34 external profile 不作为首个 P5 默认语料。
- G-M38-1 已确认方案 A；未来若重开 B/C，仍需精确出站授权与真实 provider 运行授权。

### 交付物

- 薄 HybridPlan、`hybrid` route、双 branch result/预算与现有 Graph 内的 join/controller。
- Harness 内部 typed SQL/Document Evidence bundle，以及不消费两个自然语言子答案的 Hybrid RAG branch seam。
- 正式 Hybrid Synthesizer adapter、结构化 conflict、cross-source claim validator 与 SQL/Document citation 视图。
- required branch、safe partial、ACL 非披露、Synthesizer failure 降级的稳定四轴/reason 合同。
- `/api/query`、JSONL Trace、可选 Streamlit 的兼容投影。
- 独立版本化 Hybrid sequence Eval、typed assertions、closed-world validator、聚焦/回归测试和 `m38-notes.md` 素材。
- P4 正式关闭与 M38/P5 当前状态的 state/runbook/changelog 同步材料。

只冻结职责、合同和验收，不提前固定没有必要的文件拆分、类名、节点名、并行实现、Prompt、模型参数或未来 optional branch。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：开放式 Hybrid 推理、Hybrid follow-up、optional branch 放宽、长报告/图表增强平台、生产认证、持久 checkpoint、远程 Router、P6 RAG 增强。
- 下一模块可直接消费的产物：双分支 typed Evidence/run identity、branch status/use、父子预算、Hybrid claims/citations、partial/conflict facts 和版本化 Hybrid Eval。
- 后续需要根据真实失败重新规划的内容：远程 Synthesizer 是否有稳定净收益；哪些 branch 真正 optional；开放问法是否需要模型 Router；P6 对 M34 lexical/context packing 失败簇的 go/no-go 与单变量候选。
- 可能存在的风险：为 Hybrid 暴露完整 Evidence 时误入公开/Trace；RAG branch 与 standalone AnswerFlow 形成双 Composer；partial 泄露被拒分支存在性；deterministic operator 覆盖过窄；远程方案扩大 SQL/document 出站；Graph 为双分支膨胀成浅节点集合。
- M38 完成后，P5 可按 roadmap 口径验收，但仍必须完成 P6 go/no-go 证据审查和 P7 收口后才能宣称整个 Phase 4 完成。

## 11. 开工条件

- 开工前无需确认：M36 + M37 已共同关闭 P4 最小基线；M38 进入 P5；一次完成完整保守 Hybrid 基线；SQL/RAG 默认 required；复用现有 Harness/深 Tool/caller/safety/Trace；G-M38-1 已确认方案 A；不进入 P6、持久化或生产认证。
- 实施中需要确认：无。B/C 只在第 7 节重开条件成立后重新提交用户决定，不能在 M38 实施中顺手加入。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；特别是任何要求消费两个自然语言子答案、让缺 required 分支仍 complete、自动解决 conflict、把完整 Evidence 写入公开/长期 Trace、绕过现有 Harness、或未经授权外发 SQL/文档数据的情况。
