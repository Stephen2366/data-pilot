# M37 受控有限追问与 Document Evidence 窄复用开发计划

> 状态：已开发并完成技术收工，等待用户人工检查与验收（2026-08-17）
>
> 能力里程碑：Phase 4 `P4`；本模块闭环“成功 SQL/RAG 回答后的单次受控追问 → 旧 Evidence 有效性裁决 → 业务 Document Evidence 窄复用或重新取证 → 新答案”的能力切片，不等于完成通用多轮 Context Builder、通用 Evidence 缓存或整个 P4
>
> 主要问题：M36 只能恢复 pending clarification；成功回答后 thread 已终止，系统既不能安全理解有限追问，也不能证明新 claim 使用的是重新授权、仍有效的新 Evidence

## 1. 模块定义与范围判断

M36 已完成 P4/G5 的首个澄清恢复闭环，但它有意把 checkpoint 限定为 pre-Tool 待办卡：成功 SQL/RAG 回答不会形成可追问状态，resolved checkpoint 也不保存上一轮任务条件或 EvidenceRef。与此同时，roadmap 要求有限追问重新判断旧 Evidence 是否支持新 claim；SQL 当前没有可靠业务 snapshot/freshness identity，Document Evidence 又必须在新回答前重新检查 revision、ACL 和用途。

因此 M37 不先建设更一般的历史摘要或自由文本 Context Builder。那会先扩大输入面，却仍没有回答“旧证据还能不能用”。本模块选择一个可独立演示和验收的纵向切片：在明确启用的短期 thread 中，允许成功 SQL/RAG 结果各完成一次 closed-world follow-up；Context Builder 只合并上一任务中已确认的必要条件与结构化变更；controller 先形成 Evidence validity 决定。SQL 和 EnterpriseRAG-Bench external profile 始终重新取证；只有 22 条业务 knowledge release 中、由服务端声明为“同一 Evidence requirement”的解释/重述类追问，才允许在重新加载当前原件并复核 revision/content/anchor、ACL 和用途后重建本轮 Evidence。

完成本模块后，用户可以理解、演示和验收：

- 为什么“继续聊同一个问题”不等于把上一轮答案直接塞回模型；
- SQL 为什么在没有可靠数据版本时必须重新查询；业务 Document Evidence 如何区分“仍可安全复用”和“必须重新检索”，以及 external profile 为什么暂不复用；
- 一次受控追问如何保留原条件、只修改允许字段，并继续由同一个 Harness 调用至多一个深 Tool；
- revision、权限或结果发生变化时，Trace/Eval 如何证明旧 Evidence 没有被静默当成永久事实。

M37 规模适中：它同时覆盖 SQL/RAG 两个代表性 follow-up，形成完整的跨证据类型学习故事；但把自由文本长对话、连续多次追问、持久化、Hybrid 和 RAG 内部增强排除，避免扩成会话平台。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| M36 checkpoint 只保存 pending clarification task，状态为 pending/claimed/resolved/cleared；resolved 后不能再次 claim | 成功回答后没有可消费的 follow-up task/lifecycle，也不能表达“一次追问预算” | `engine/harness/thread.py::PendingTask / PendingThreadCheckpoint / ThreadCheckpointManager` |
| M36 Context Builder 只有 `subject` 与 `analytics_scope` 两个 clarification 模板 | 它能补齐缺失条件，但不能表达“保留原指标，只替换时间/分组”或“围绕同一政策主题追问一个受控细节” | `engine/harness/contracts.py::ClarificationSpec`、`engine/harness/thread.py::ClarificationContextBuilder.build` |
| `run_turn()` 只区分 initial、resume、rejected；每个 accepted turn 恰好一次 Graph | M37 必须在现有 turn seam 内增加 follow-up，不能让 API 绕过 Harness 或另造答案裁决 | `engine/harness/turn.py::TurnRequest / AgentTurnResult / run_turn` |
| SQL Evidence 的 `revision` 实际来自查询时间；当前环境没有可靠业务 snapshot identity | 旧 SQL 结果不能跨轮声明仍然新鲜；追问必须重新执行受 Guard 保护的查询 | `engine/rag/evidence.py::SQLEvidencePayload / make_sql_evidence`、`docs/phase4-roadmap.md` 4.5/10 节 |
| Document Evidence 有 revision/content identity/anchor，M33 会在单轮 generation 前复核 active revision 与 ACL | 具备判断失效的坐标，但当前复核只覆盖同轮 retrieval→generation，不等于已具备跨轮复用 | `engine/rag/evidence.py::EvidenceRef`、`engine/rag/answer_flow.py::RAGAnswerFlow._gate` |
| ToolObservation/Trace 已有安全 EvidenceRef/ledger 投影，RAG 正文不离开 AnswerFlow | 可以保存旧 Evidence 的审计坐标和比较结果；不能据此把正文、SQL rows 或旧 answer 放入 checkpoint | `engine/harness/contracts.py::ToolObservation`、`app/api/query.py::_observation_projection / _record_trace` |
| M36 sequence Eval 只覆盖 clarification、owner/version/TTL/clear/concurrency/budget | 目前没有“一轮成功 → 一次 follow-up → 新 Evidence”的 closed-world 执行证据 | `eval/harness_turn_contracts.py`、`docs/state/rag-current-state.md` |
| M34 的 lexical 漏召回和 multi-document context packing 是独立失败簇 | 它们不能被 M37 偷换成 query rewrite、parent expansion 或 RAG 内部循环 | `docs/state/rag-current-state.md`、`docs/state/AI_CONTEXT.md` |

## 3. 参考源码定点复核

DataPilot 的真实问题不是“怎样做一个开放聊天 Agent”，而是“怎样把上一任务、允许修改的条件、旧 EvidenceRef、重新取证决定和预算分开保存”。本轮按 `docs/phase4-reference.md` 的 P4 能力卡重新查看了 ARAG 源码；外部项目没有实现 DataPilot 所需的跨轮 revision/ACL/freshness 合同，因此 Evidence validity 仍以 DataPilot roadmap 和现有 Evidence/安全代码为准。

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 任务条件与追问增量如何分离 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::State / AgentState`；`nodes.py::_recent_conversation / rewrite_query` | unresolved query、clarification 与 recent conversation 分开表达，避免把所有消息视为同一种状态 | checkpoint 只保存受控 task snapshot、confirmed conditions、follow-up spec/budget 和安全 EvidenceRef；Context Builder 由结构化 delta 生成 current task | 不保存 `MessagesState` 全历史，不调用 LLM rewrite，不默认 summary/compact，不把消息文本当授权或 Evidence |
| 如何阻止重复 Tool 和无限追问 | `agentic-rag-for-dummies/project/rag_agent/edges.py::route_after_orchestrator_call`；`graph_state.py::tool_call_count / iteration_count` | 在控制边显式检查 iteration/Tool budget，并提供终止路径 | M37 由确定性 turn controller 限制一次 follow-up；accepted follow-up 恰好一次 Graph、至多一个深 Tool，无预算时在 Tool 前停止 | 不采用开放 Tool loop、模型自选下一动作、fallback 生成或父子双循环 |
| 如何保存可比较的 context/动作事实 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::append_unique`；`nodes.py::_retrieval_contexts / should_compress_context` | 去重记录检索动作/实际 Tool context，并把“已经执行过什么”作为停止依据 | 只记录旧/新 EvidenceRef 的安全比较、reacquisition reason、Context ref 和 Tool 次数；正文仍留在深 Tool 内 | 不把 ToolMessage 正文跨轮累计，不用自然语言 summary 代替 Evidence identity，不因 token 阈值默认压缩 |
| 是否把 follow-up 放进原生 checkpointer | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph` | 直接源码再次证明其主图用 `InMemorySaver` + interrupt 管理更开放的会话暂停 | 延续 M36 已确认的应用持有进程内状态；只在现有 turn seam 增加 follow-up lifecycle | 不重开 LangGraph checkpointer、持久 checkpoint 或 Graph 中间节点恢复；这些仍按 M36 决策门触发 |

参考边界：ARAG 的 `retrieved_contexts` 是字符串列表，`context_summary` 由 LLM 生成，不能证明旧文档仍 active、当前 caller 仍有权或 SQL 结果仍新鲜；这些能力不进入 DataPilot 的 Evidence validity 决定。

## 4. 目标、优先级与非目标

### 模块完成状态

在已确认的 G-M37-1 方案 A 下，只有请求显式开启 bounded thread 时，一次成功 SQL/RAG turn 才形成有限 TTL、owner/version 绑定、最多一次消费的 follow-up-ready checkpoint；旧单轮请求继续保持 `thread=None`。客户端按公开 closed-world spec 提交结构化追问后，系统保留必要原条件、拒绝额外字段和跨能力偷渡，形成可审计的旧 Evidence validity 决定；随后按已确认的 G-M37-2 窄 B 取得支持新 claim 的 Evidence，并仍由一次 M35 Graph 产生唯一结果。响应、JSONL Trace 和新 sequence Eval 能共同证明没有直接把旧 answer、rows、正文或旧 run-scoped Evidence 当作新答案事实。

### 必须完成

- 建立成功 turn → follow-up-ready → claimed → resolved/cleared 的单调生命周期，并延续 owner/tenant/active-role、TTL、version、并发单 claim 与重启失效语义。
- 至少覆盖一个 SQL follow-up 和一个 RAG follow-up；两者都使用 closed-world action/fields，不把自由文本历史直接回灌 Router/Tool。
- 建立 Evidence validity/reacquisition 决定：新 claim requirement、Evidence kind、freshness/revision、ACL/用途和前后 Evidence 安全 diff 可观察。
- SQL 在没有可靠 snapshot identity 时总是重新取证；不得直接返回旧 rows、旧 fingerprint 或旧答案。
- 业务 Document 只在服务端声明新旧 Evidence requirement 等价、当前原件可无歧义重载、revision/content identity/anchor 一致且 ACL/用途重新授权通过时复用；复用时必须重建本轮 Evidence/ledger/citation identity。
- RAG follow-up 若改变 Evidence requirement、旧 revision/content/anchor 已变化或当前原件不可复用，则在同一个 RAG 深 Tool 内最多回退一次 Knowledge Tool；ACL/用途拒绝不靠重新检索绕过。
- EnterpriseRAG-Bench external profile 的 Document Evidence 始终重新取证，不建立跨 profile rehydrate/reuse seam。
- accepted follow-up 恰好一次 compiled Graph、至多一个深 Tool；无效 action、owner/version/lifecycle/budget 拒绝为零次 Graph/Tool。
- 增量接入 `/api/query`、安全 Thread 投影、JSONL Trace 和独立版本化 sequence Eval；旧 M35/M36 artifact 只读。

### 建议完成

- Streamlit 增加最小 follow-up 表单，严格由服务端返回的 action/field spec 驱动，不建设聊天 UI。
- Trace 增加便于人工回查的 Evidence delta 分类（unchanged/current、changed、unavailable、not comparable），但不公开旧文档存在性或内部 ACL 原因。

### 条件触发

- **触发条件**：业务 release 的安全 EvidenceRef 无法通过 authority/revision/content/anchor 在当前 active bundle 中唯一定位原件，或复用路径无法复用现有 ACL/Gate/citation 合同。
- **允许动作**：暂停复用分支并提交冲突；经用户确认后可将业务 Document 回落为重新取证，但不能静默把 G-M37-2 已确认的窄 B 改回 A。
- **未触发时**：只实现业务 release 专用 rehydrate seam；不扩展 external profile，不新增通用 Evidence store、正文缓存、跨 run ledger 合并或持久化 adapter。

### 明确非目标

- 自由文本开放追问、任意指代解析、连续多次 follow-up、长历史、自动摘要或多层 compact。
- SQL Evidence 跨轮缓存复用，或为本模块虚构数据库 snapshot/version 能力。
- EnterpriseRAG-Bench external profile 的 Evidence 复用，以及跨不同 knowledge runtime 的统一 rehydrate 平台。
- Tool 技术失败 retry、query rewrite、parent/context expansion、rerank、M34 context packing 优化或 RAG Subgraph。
- 跨 Tool 补 Evidence、route 切换、Hybrid、partial/conflict 合成。
- LangGraph `InMemorySaver`/interrupt、持久/分布式 checkpoint、生产认证或多 worker 会话共享。
- 默认模型、embedding、检索 adapter、corpus、数据库、安全策略或 LangFuse Cloud 切换。

## 5. 关键合同

这是 M37 新增合同的单一事实源；roadmap 第 4 节、M31–M36 既有 Evidence/安全/四轴/turn 合同继续有效，不在本计划重写。

### C1：Follow-up-ready Checkpoint 与生命周期

- 输入：请求已按 G-M37-1 方案 A 显式开启 bounded thread 的成功 SQL/RAG `AgentTurnResult`、生成该结果的 current task 安全快照、重新解析的 trusted owner、旧 EvidenceRef 安全投影、knowledge runtime kind 和有限 TTL/预算。
- 成功输出：schema-versioned follow-up-ready checkpoint 与安全公开投影；包含 opaque thread id、version、owner ref、原任务必要条件、允许的 follow-up spec、旧 EvidenceRef/route 的安全摘要、剩余一次 follow-up 预算和过期事实。
- 失败语义：结果不完整/被安全拦截、task 不能结构化、EvidenceRef 不闭合或 checkpoint 无法保存时，不返回可追问 thread；原业务结果保持真实，不因附加状态保存失败被伪写成 Tool 失败，并记录稳定 thread-state reason。
- 必须保持的不变量：checkpoint 不保存完整 answer、SQL rows、Document 正文、完整 citation、prompt、消息历史或思维链；thread id 不是授权；同一 version 最多一个 follow-up claim；clear/expiry/restart/incompatible state 后不可恢复。
- 本模块不冻结的实现细节：内部 dataclass/file 名、容器布局和具体 TTL；状态必须与 M36 clarification 共享一套 owner/version/lifecycle 规则，不能在 API 再建第二个字典。

### C2：Closed-world Follow-up Context

- 输入：C1 task snapshot、服务端声明的 follow-up action/fields、合法 owner/active role、expected version。
- 成功输出：保留原任务高风险条件并只应用允许 delta 的最小 current task，以及不含原值的不可逆 Context ref；至少覆盖 SQL 时间/分组调整、业务 RAG 同一已引用规则的解释/重述，以及需要新 Evidence 的受控 RAG 追问。
- 失败语义：缺字段、额外字段、类型/长度非法、要求换 route/跨 Tool、覆盖受保护条件或无法确定新 Evidence requirement 时，在 claim/Tool 前拒绝且不消费合法 pending version。
- 必须保持的不变量：不使用 LLM rewrite；不拼完整历史或上一 answer；不把旧 rows/正文交给 Router/Tool；生成的新 task 必须可由现有 Harness 选择预期的同一路由。
- 本模块不冻结的实现细节：内部模板文案、字段展示顺序和 helper 名；不得借模板数量之名扩展成通用自然语言槽位系统。

### C3：旧 Evidence Validity 与新取证

- 输入：旧 EvidenceRef 安全摘要、新 current task/Evidence requirement、当前 trusted caller/active role、当前 catalog/revision/policy/runtime 事实。
- 成功输出：一个 closed-world validity decision（至少说明 runtime kind、新旧 requirement 是否等价、旧 Evidence 是否具备 freshness/revision、是否要求 reauthorization/rehydration/reacquisition）和支持新 turn 的 Evidence；前后 Evidence 用 authority/revision/content identity/anchor/runtime 等安全坐标比较，不用 run-scoped `evidence_id` 是否相等冒充内容是否相等。
- 失败语义：旧 Evidence 不完整、SQL 无 snapshot、Document inactive/revoked、ACL/用途变化、当前 Tool 不可用或新 Evidence 不足时，沿用既有四轴/reason 安全停止；不得回退旧答案。未授权路径不暴露旧/新文档标题、revision、命中数或 EvidenceRef。
- 必须保持的不变量：SQL 总是重新执行；external profile 总是重新检索；业务 Document 只有在服务端 action 声明 requirement 等价、active bundle 唯一重载同一 authority/revision/content/anchor 且重新授权通过时才复用。复用必须创建本轮 Evidence/ledger/citation identity，旧 run 的 Evidence/citation 不能直接支持新 run claim。requirement 不等价或 revision/content/anchor 变化时，最多重新检索一次；ACL/用途拒绝直接安全停止。
- 本模块不冻结的实现细节：validity evaluator、业务 release rehydrator 的类名、diff 存储形状和 adapter 内部调用方式；不得为了统一接口提前扩展 external profile。

### C4：单次 Follow-up 与唯一 Harness 事实

- 输入：C1 原子 claim、C2 current task、C3 validity/reacquisition policy 和 M35 `HarnessRuntime`。
- 成功输出：follow-up turn 的唯一 `AgentRunResult`；恰好一次 compiled Graph、至多一个同 route 深 Tool，API/Trace/Eval 只从该 result、lifecycle 和 validity fact 单向投影。
- 失败语义：无效 follow-up/lifecycle/budget 为 0 次 Graph/Tool；accepted follow-up 的 Tool blocked/unavailable/insufficient 沿用原四轴且不自动重试、不恢复旧结果、不创建第二个 follow-up-ready checkpoint。业务 Document 的“复用不适用 → 一次 Knowledge Tool 重新取证”是同一 RAG 深 Tool 内的受控 fallback，不算 Tool 技术失败 retry。
- 必须保持的不变量：一次 bounded thread 最多消费一个 clarification resume 和一个 evidence follow-up；M37 不允许跨 route、跨 Tool 或无限链式追问；controller 不进入 RAG 内部检索策略。
- 本模块不冻结的实现细节：是否为 follow-up 增加独立 Graph node；外部仍必须是同一个 `run_turn`/turn-level interface。

### C5：Follow-up Trace 与 Sequence Eval

- 输入：初次成功或 clarification→成功、唯一 follow-up、可选 lifecycle/ACL/revision/concurrency 反例。
- 成功输出：安全 thread/turn/version/action/budget、old/new Evidence safe refs 或不可泄露替代摘要、validity/reuse/rehydration/reacquisition reason、Context ref、Graph/顶层 Tool/Knowledge retrieval 次数、四轴和终止事实；同一 sequence 的多断言复用同次真实执行。
- 失败语义：漏 turn、重复 execution、旧 Evidence 直接出现在新 run ledger/citation、eligible reuse 仍发生 retrieval、应重新取证却 retrieval count 为 0、未授权 Evidence 泄露或 assertion 集不闭合时，completed artifact 拒绝生成。
- 必须保持的不变量：Trace 不保存完整 answer 历史、rows、正文、raw thread id、follow-up 字段值或思维链；旧 `phase4-harness-turn-v1` 不补字段、不混算。
- 本模块不冻结的实现细节：artifact 文件名、报告样式和 P7 retention/debug bundle。

## 6. 工作切片与执行顺序

### M37-A：开工快照、决策生效与合同矩阵

- 优先级：必须完成
- 依赖：M36 已人工检查并通过 `accept-module`；G-M37-1 已固定为方案 A；G-M37-2 已固定为窄 B；开工时最新 state/runbook。
- 实施内容：创建 `m37-notes.md` checklist；核对工作树、实际 API/Trace/Eval seam；冻结 follow-up action、state/version、validity/reacquisition reason 和四轴映射；列出所有新增 consumer。
- 关键合同：C1–C5。
- 交付物：开工快照、state/action/reason 真值表、consumer 清单。
- 验证方式：closed-world 枚举/未知值 fail-closed 测试和旧 reason 回归。
- 完成门：没有用异常文本、HTTP 状态或 `blocked_reason` 代替 validity/lifecycle reason。

### M37-B：成功 Turn 的最小 Task/Evidence Snapshot

- 优先级：必须完成
- 依赖：M37-A；M36 owner/version/TTL/clear 深 module。
- 实施内容：按 G-M37-1 在成功 SQL/RAG turn 后创建或推进 follow-up-ready checkpoint；状态升级为新 schema version，保存必要 task/condition、follow-up spec/budget 和 EvidenceRef 安全摘要，不保存业务内容。
- 关键合同：C1。
- 交付物：follow-up-ready 生命周期、兼容安全投影、并发/clear/expiry/state-version 测试。
- 验证方式：initial success 与 clarification→success 两条路径；无 Evidence、blocked、failed、unsupported 不产生假 follow-up；owner/version/concurrency 反例为 0 Tool。
- 完成门：删除该 module 会迫使 API 同时理解 owner、task、Evidence、budget 和 version，证明深 module 边界成立；checkpoint 内容通过敏感字段审查。

### M37-C：Follow-up Context 与 Evidence Validity 决定

- 优先级：必须完成
- 依赖：M37-B；已确认的 G-M37-2 窄 B。
- 实施内容：实现 SQL/RAG 两类 closed-world follow-up；形成新 claim requirement；对旧 Evidence 给出 validity/rehydration/reacquisition 决定和安全 diff。SQL 与 external profile 固定重新取证；业务 release 增加只读 rehydrate seam，并在 requirement 等价、identity/current/ACL/用途全部通过时重建本轮 Evidence，否则按合同停止或在同一 RAG 深 Tool 内最多重新检索一次。
- 关键合同：C2、C3。
- 交付物：最小 Context Builder 增量、validity decision、Evidence comparison、表驱动合同测试。
- 验证方式：条件保真、额外字段/跨 route 拒绝、SQL 无 snapshot、业务 Document reused/revised/revoked/ACL changed/purpose changed/requirement changed，以及 external always-retrieve 场景。
- 完成门：任何成功新答案都能指出本轮 Evidence 来源；没有路径直接用旧 answer/rows/body/citation 生成新结果。

### M37-D：Turn Controller、API 与 Trace 接线

- 优先级：必须完成；Streamlit 表单为建议完成
- 依赖：M37-B/C；M35 Graph 与 M36 `run_turn`。
- 实施内容：在唯一 turn seam 接入 follow-up claim/执行/resolve；增量扩展请求和 ThreadView；Trace 记录 action/budget/validity/reuse/rehydration/reacquisition/diff，以及顶层 Tool 与内部 Knowledge retrieval 的独立次数；旧 initial/clarification/resume/clear 行为保持兼容。
- 关键合同：C1–C5。
- 交付物：完整一次 follow-up 链、兼容 API/Trace、可选 demo 表单。
- 验证方式：TestClient 跑 SQL/RAG sequence；accepted follow-up 1 Graph/1 Tool，拒绝 0/0；响应、Trace、Eval 对同一 turn/result 对账。
- 完成门：API 不读写 checkpoint 内部状态、不自行拼旧 Evidence、不生成第二套四轴或答案。

### M37-E：版本化 Sequence Eval 与安全反例

- 优先级：必须完成
- 依赖：M37-D。
- 实施内容：新增独立 follow-up sequence family；覆盖 SQL 重查询、业务 RAG safe reuse/requirement change/revised/revoked、external RAG 重新检索、ACL/owner/version/TTL/clear/concurrency、非法 delta、预算和旧 run Evidence non-reuse；completed validator 保持 closed-world。
- 关键合同：C3–C5。
- 交付物：sequence ExecutionEvidence、typed assertions、artifact validator 和篡改反例。
- 验证方式：见第 8 节；所有 assertion 从每个 turn 的唯一执行事实投影，不为评分重跑 Tool。
- 完成门：能直接证明旧 run Evidence/citation 未被新 claim 使用；未授权场景没有 Evidence/title/revision 侧信道。

### M37-F：回归、注释与收工素材

- 优先级：必须完成
- 依赖：M37-A–E。
- 实施内容：按聚焦顺序运行 M37→M36→M35→M31–M33→受影响 API/SQL/RAG→全仓 deterministic 回归与静态检查；在 notes 固化决策、失败证据和验证快照。
- 关键合同：C1–C5。
- 交付物：可靠测试终态、注释审计、`m37-notes.md`、finish-module 所需技术素材。
- 验证方式：见第 8 节和 AGENTS 长时间命令规则。
- 完成门：required 合同全绿；真实 LLM/远程能力若未运行，明确标为未证明；随后再进入 `finish-module`。

## 7. 决策门

### G-M37-1：成功回答何时建立 bounded follow-up thread（已确认）

#### 方案 A：请求显式开启 bounded thread（用户已选择）

- 做法：为 QueryRequest 增加一个向后兼容的受控开关；只有显式开启时，成功 SQL/RAG turn 才返回 follow-up-ready thread。clarification checkpoint 继承该意图，resume 成功后再按预算转为 follow-up-ready。
- 影响：旧调用默认仍是单轮、`thread=None`；内存/隐私增长与 tombstone 风险只落在明确需要追问的请求；演示多一步开关。
- 适用条件：当前仍是单机 demo/test，且 resolved/cleared tombstone 尚无清扫机制。
- 风险：调用方忘记开启时不能事后追问；需要明确区分普通请求和 bounded conversation。

#### 方案 B：所有成功 SQL/RAG 自动建立 thread

- 做法：任何 safety passed + complete 的请求都创建 follow-up-ready checkpoint并返回 thread。
- 影响：用户体验最直接，旧请求也自动获得追问能力；但每个成功请求都会占用进程内状态，旧响应从 `thread=None` 变为非空，扩大兼容、容量和隐私面。
- 适用条件：希望 demo 默认就是短对话，并愿意同步实现可靠的过期 tombstone 清扫与容量边界。
- 风险：当前已知的进程内容器增长问题被放大；容易让调用方误以为具备持久会话。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：M37 只需证明一次有限追问，不应让所有单轮查询默认进入会话存储；显式开启也更容易诚实展示内存态、TTL 和重启失效边界。
- 用户选择：2026-08-17 确认方案 A；旧单轮请求不自动创建 follow-up-ready checkpoint。
- 用户确认前允许推进：已确认；当前仍需等待 M36 人工验收。
- 用户确认前禁止推进：不再适用；但禁止把显式 activation 静默改为所有成功请求默认开启。
- 需要确认的时点：已完成。
- 重开决策的条件：人工体验证明显式开关严重破坏核心 demo，或后续已具备容量、清扫、隐私和兼容证据支持默认开启。

### G-M37-2：Document Evidence 在首个 follow-up 中复用还是重新取证（已确认）

#### 方案 A：SQL/RAG 都重新调用深 Tool（原建议）

- 做法：旧 EvidenceRef 只作为 validity/audit 输入；SQL 必定重查，RAG 也重新调用 Knowledge Tool→Gate→Composer→Citation。新旧 Evidence 事后按安全坐标比较。
- 影响：合同最简单，天然获得当前 revision/ACL/用途和新的 run-scoped ledger/citation；每个 follow-up 有一次 Tool 成本，但仍满足全局最多一个 Tool。
- 适用条件：当前没有独立、成熟的 Document Evidence rehydrate/reuse seam，且业务 corpus 检索成本可接受。
- 风险：相同文档也会重复检索；本模块证明的是 invalidation/reacquisition，不证明低成本 Evidence reuse。

#### 方案 B：业务 Document 窄复用；SQL/external 仍重新取证（用户已选择）

- 做法：只对 22 条业务 knowledge release 尝试复用。服务端 follow-up spec 必须先声明新旧 Evidence requirement 等价；随后从当前 active bundle 以 authority/revision/content identity/anchor 唯一重载原件，重新校验 owner、ACL、用途和 Gate，再创建本轮 Evidence/ledger/citation。requirement 不等价或 revision/content/anchor 已变化时，在同一 RAG 深 Tool 内最多重新调用一次 Knowledge Tool；ACL/用途拒绝直接停止。SQL 和 EnterpriseRAG-Bench external profile 始终重新取证。
- 影响：能演示真正的 `no_retrieval_needed`、失效重取证和新 run citation，同时把 rehydrate seam 限制在现有业务 active bundle，不建立跨 profile 通用平台。
- 适用条件：M37 的学习目标包含真实 Evidence reuse；业务 release 能通过安全 ref 唯一定位当前原件，且复用继续经过 M31–M33 的授权/Gate/citation 合同。
- 风险：比方案 A 多一条 rehydrate/fallback 分支；若 requirement 等价定义过宽，会把“同主题但需要新证据”的追问误判成可复用，因此只允许服务端 closed-world action 声明等价。

#### 建议与确认时点

- 原建议：方案 A，优先建立全部重新取证的正确性基线。
- 用户选择：2026-08-17 选择窄 B；只复用业务 22 条 release，SQL/external 始终重新取证，不建设跨 runtime 通用复用。
- 选择后的控制理由：把真实 reuse/invalidation 纳入 P4 展示，同时用 closed-world requirement equivalence、业务 active bundle 唯一重载、重新授权和一次 fallback 限制复杂度。
- 用户确认前允许推进：已确认；当前仍需等待 M36 验收。
- 用户确认前禁止推进：不再适用；但禁止把窄 B 扩成 external profile、SQL Evidence、正文缓存或通用 Evidence store 复用。
- 需要确认的时点：已完成。
- 重开决策的条件：业务 EvidenceRef 无法唯一重载当前原件、复用无法继续经过既有 ACL/Gate/citation，或 deterministic required case 证明 requirement-equivalence seam 不安全。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 activation/兼容 | API + manager 测试 | 仅显式开启请求产生 follow-up-ready thread；旧单轮/clarification 合同不回归；失败业务结果不产生假 thread | 必须完成 |
| C1 owner/lifecycle | wrong owner/tenant/role、expiry、clear、restart、state version、stale expected version | 非 owner 不获知 thread/Evidence；合法 owner 获得稳定 reason；拒绝均 0 Graph/Tool | 必须完成 |
| C1 并发/预算 | 两个相同 version 的 follow-up claim + 重复提交 | 恰好一个 accepted；总 follow-up Tool 最多 1 次；成功后不能链式再次消费 | 必须完成 |
| C2 SQL Context fidelity | 原指标/过滤 + 时间/分组 delta 表驱动 | 原条件不丢、只修改允许字段；额外/跨 route 字段不消费 version | 必须完成 |
| C2 RAG Context fidelity | 同一 Evidence 解释/重述、需要新 Evidence 的细节追问、额外字段与指令型输入反例 | 只有服务端声明的等价 action 可进入复用候选；其他追问重新取证；新 task 不携带旧 answer/body/history | 必须完成 |
| C3 SQL freshness | fake DB/SQL Tool 在两 turn 返回不同 fingerprint | follow-up 必有第二次 SQL Tool；新响应只来自新 rows/fingerprint；old ref 仅审计 | 必须完成 |
| C3 业务 Document 窄复用 | 同 requirement + 同 active revision/content/anchor + ACL/用途未变 | Knowledge retrieval count 为 0；从当前原件重建本轮 Evidence/ledger/citation；旧 run evidence_id/citation 不直接进入新答案 | 必须完成 |
| C3 requirement 变化 | 同主题但 follow-up 需要不同 Evidence | 复用门拒绝，Knowledge Tool 在同一 RAG 深 Tool 内恰好调用 1 次；新答案只用新 Evidence | 必须完成 |
| C3 revision 变化 | rev1 成功后切 rev2、revoke 或 inactive fixture | 使用 rev2 新 Evidence 或返回 insufficient；绝不回退 rev1 答案/citation | 必须完成 |
| C3 ACL/用途变化 | owner 合法但当前 policy/role/purpose 不再允许 | 安全停止且无标题/revision/ref/命中数泄露；旧授权不跨轮继承 | 必须完成 |
| C3 external 隔离 | external profile 同 revision follow-up | 不进入业务 rehydrate seam；Knowledge Tool 恰好重新检索 1 次；profile identity 不被业务 locator 消费 | 必须完成 |
| C4 唯一 Harness | initial success、clarification→success→follow-up、accepted/rejected 对照 | accepted turn 各 1 Graph、≤1 Tool；pre-Graph rejected 为 0/0；API 不绕行 | 必须完成 |
| C5 Trace 安全与一致性 | AgentResponse/JSONL/sequence evidence 对账 | action/version/budget/context/validity/reuse/reacquisition、顶层 Tool 与内部 retrieval 次数一致；无 raw thread id、delta value、正文、rows 历史 | 必须完成 |
| C5 closed-world Eval | 漏 turn、重复 execution、旧 Evidence 注入、缺 assertion、超预算 artifact 反例 | completed validator 全部拒绝；正常 family 所有 required assertion 通过 | 必须完成 |
| M36/M35 兼容 | 既有 turn/Harness/API/Trace/Eval suites | initial/pending/resume/clear、一次 Graph/Tool、四轴和旧 artifact 语义不变 | 必须完成 |
| M31–M33 安全回归 | caller/ACL/outbound/Evidence/citation required suites | 既有 required Gate 全绿 | 必须完成 |
| 全仓 deterministic 回归 | 聚焦通过后运行全仓 pytest | 获得可靠终态；失败先定位，不靠重复全量掩盖 | 必须完成 |
| 静态交付 | `compileall`、`git diff --check`、注释/interface/敏感字段审查 | 无语法/whitespace 错误；新增代码符合 AGENTS 注释；checkpoint/Trace 无禁止内容 | 必须完成 |
| Streamlit 最小交互 | 组件/人工检查 | 能显式开启 bounded thread、按服务端 spec 提交一次 follow-up | 建议完成 |

聚焦测试顺序：reason/state/action → task snapshot/lifecycle/concurrency → SQL/RAG Context → validity/reacquisition → turn controller → API/Trace → sequence Eval → M36 → M35 → M31–M33 → 受影响 Text2SQL/RAG → 全仓 deterministic pytest → compileall/diff check。Windows pytest 使用新的 `.agent_work/temp/m37-focus-basetemp`、`.agent_work/temp/m37-full-basetemp` 等互不复用的目录；预计超过 2 分钟的全仓验证按 AGENTS 后台任务规则执行。

本模块不自动运行真实 LLM Router/Text2SQL Eval、M34 external Answer Eval、Milvus/embedding、remote Composer/Judge 或 LangFuse Cloud。历史 M27、M31–M36 artifact、M34 profile/split 和 baseline 全部只读；新 family 不与它们补字段或混算。人工验收重点是两条 follow-up 演示、revision/ACL/SQL-freshness 反例和 Trace 回查，不把 deterministic Context 模板说成开放对话能力。

## 9. 依赖与交付物

### 依赖

- M36 完成用户人工检查与 `accept-module`；在此之前只允许审查计划，不开始 M37 实现。
- Phase 4 roadmap P4 的有限追问、Evidence 失效/重新取证、Context/State/安全/Eval 不变量。
- M31 trusted caller、EvidenceRef/ACL/revision/citation；M32 Knowledge Tool；M33 AnswerFlow；M35 唯一 Harness/深 Tool/四轴；M36 owner/version/TTL/并发/turn seam。
- G-M37-1 已于 2026-08-17 确认为方案 A；G-M37-2 已于同日确认为窄 B。开工时重新读取最新 `AI_CONTEXT.md`、runbook 及被其规则触发的 state 文档。

### 交付物

- 一个仍为进程内、但能表达 clarification 与单次 successful follow-up 的 versioned thread/task lifecycle 深 module。
- SQL/RAG closed-world follow-up spec、最小 Context Builder 增量、业务 Document rehydrate seam、Evidence validity/reuse/reacquisition decision 和安全 diff。
- `/api/query`/ThreadView/JSONL Trace 的兼容投影与可选 Streamlit 最小表单。
- 独立版本化 follow-up sequence Eval、typed assertions、closed-world validator、聚焦/回归测试和 `m37-notes.md` 素材。

只冻结职责和合同，不提前固定类名、文件拆分、TTL 数值、具体清扫算法或未来持久 adapter。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：真正的多次对话、跨 route/cross-Tool follow-up、Hybrid、Tool retry、长历史 compact、持久 checkpoint、生产认证、M34 检索/context packing 优化。
- 下一模块可直接消费的产物：成功 turn 的最小 task/Evidence snapshot、validity/reacquisition fact、一次 follow-up budget、旧/新 Evidence 安全 diff 和扩展后的 sequence Eval。
- 后续需要根据真实失败重新规划的内容：是否把业务窄复用扩到 external profile、是否扩展第二次追问、是否需要更一般的 Context Builder、何时触发持久 checkpoint 或 LangGraph 原生 interrupt。
- 可能存在的风险：follow-up spec 对开放问法仍窄；进程重启/多 worker 仍丢状态；opt-in 可能降低 demo 直觉性；automatic 模式会放大 tombstone/容量风险；错误保存 task/Evidence 摘要可能形成隐私或侧信道；重新取证增加一次 Tool 成本。

## 11. 开工条件

- 开工前无需确认：M37 对应 P4 的有限追问 + Evidence 失效/重新取证切片；继续使用应用持有的进程内 checkpoint、M35 Graph 和现有 SQL/RAG 深 Tool；SQL 无 snapshot 时必须重查；不进入 Hybrid、开放 loop、持久化或 M34 优化。
- 实施中需要确认：无；G-M37-1 已确认方案 A，G-M37-2 已确认窄 B。M36 必须先通过人工检查与 `accept-module`，这是当前唯一开工门。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；特别是任何要求默认保存完整 answer/rows/正文、信任旧授权、跨 run 直接复用 citation、允许跨 route/多 Tool 或引入持久化的情况。
