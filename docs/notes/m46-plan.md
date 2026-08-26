# M46 Phase 4B B4 Bounded Agentic RAG 开发计划

> 能力里程碑：B4；本模块完整承担 B4，把 M45 已准入的 recovery action 接成产品内 RAG Subgraph，并完成 Pipeline/Subgraph 决策证据
>
> 主要问题：当前系统已知道哪些 RAG 恢复动作在什么 Observation 下可能有效，但产品 Knowledge Tool 仍只做一次固定检索，尚不能在一次父级文档取证动作内有界地选择、执行、记账并停止

## 1. 模块定义与范围判断

M45/B3 已通过验收并给出 v4 `go_for_M46`：`query_rewrite_candidate` 与 `context_expansion_candidate` 两张 action card 均完成，同一个 external semantic runtime 已在不同真实 Observation 下证明两种动作及错误动作排除。M44/B2 则已经提供顶层 Action、EvidenceDelta、Budget、Progress、Termination 和单次 `collect_document_evidence` seam。M46 的顺序与范围因此成立：**保留顶层一次文档取证动作，在 Knowledge Tool 内部交付真正的 bounded RAG Subgraph，并先用historical判断它是否值得进入sealed decision reserve。**

M46 完整对应 B4，不再拆成“先画子图、后面再做 A/B”的两个模块。2026-08-26 用户在三代 historical 60×2 均未达到 candidate 晋级门后确认 experimental rollout 收口：B4 以“完整 experimental adapter + Pipeline 稳定默认 + historical 闭集诊断证据 + sealed reserve 不消费 + 精确重开门”闭合。该修订替代原计划“必须先运行 reserve 才能验收”的完成门，但不删除 Subgraph、父子预算、Trace/Eval、安全合同或测试，也不把 historical 当作未污染质量胜负。B5 durable state 与 B6 Compact 仍不进入 M46。

用户完成 M46 后应能：

- 从一次 `collect_document_evidence` 展开查看 initial retrieval、eligible action、chosen/rejected action、EvidenceDelta、父子预算、no-progress 和 termination；
- 演示 business T4 在产品 task/Loop seam 内补齐两篇退款政策，而顶层仍只消费一次 Knowledge action；
- 在同一个 external semantic runtime 上展示 rewrite→expansion 与直接 expansion 两条不同恢复路径；
- 对照 Pipeline 与 Subgraph 在同 corpus、AnswerFlow、provider 和冻结预算下的检索、回答、citation、安全、调用、token 与延迟；
- 根据已完成 historical 的真实 no-go 与用户确认，固化“Pipeline 默认 + Subgraph experimental”；明确 reserve 未运行且保持 sealed，不把“子图能跑”写成“质量已提升”。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| M45 v4 review 为 `go_for_M46`，两张 action card completed；P5 仍只是一次结构型 Evidence gain，reserve 保持 sealed | M46 可以消费动作合同，但不能把 diagnostic executor 或 Evidence gain 直接冒充产品 Subgraph、答案正确率或默认净收益 | `eval/reports/m45/m45-b3-continuation-review.json`、`docs/notes/m45-notes.md::Handoff` |
| 顶层 B2 只认识 `collect_document_evidence`，并经 `KnowledgeRuntimeResolver` 解析 business/external `RAGTool` | 正确 seam 是让 Pipeline/Subgraph 隐藏在文档取证模块内部；把 rewrite/expansion 提升为顶层 Action 会泄漏 RAG 策略并制造双循环 | `engine/phase4b/agent_loop.py::_choose_action/_step_node`、`engine/phase4b/knowledge_runtime.py` |
| B2 production budget 目前 `max_knowledge_actions=1`、`max_retrieval_batches=1`，`ResourceConsumption` 没有父子账区分 | 现有预算只能表达单次 Pipeline，无法证明“父动作一次、子图多步”及实际 child calls/candidates/context 消费；直接放宽旧 B2 identity 会改写历史合同 | `engine/phase4b/loop_contracts.py::BudgetProfile/BudgetLedger`、`domain_pack/phase4b/b2_contracts.json` |
| `RAGAnswerFlow` 直接依赖一个 `KnowledgeTool.retrieve()`，随后独占 active authority 重载、Shared Gate、Composer 与 Citation Validator | 这里已有最窄、最深的替换 seam：新增 Pipeline/Subgraph 两个 Evidence acquisition adapter，输出同一 `RetrievalOutcome`，AnswerFlow 后半段无需复制 | `engine/rag/answer_flow.py::RAGAnswerFlow._obtain_evidence/run/prepare_for_hybrid`、`engine/rag/knowledge_tool.py::RetrievalOutcome` |
| M45 diagnostic expansion 可重水化并重新授权 Evidence，但当前返回值没有完整携带生产 Gate 需要的 pre-generation authorization 和合并 ledger | 不能直接把 diagnostic safe projection 塞进 AnswerFlow；M46 必须建立生产 acquisition result，并复用底层 authority/ACL seam而非复制安全逻辑 | `engine/phase4b/rag_enterprise_diagnostics.py::EnterpriseSiblingExpansionAdapter`、`engine/rag/answer_flow.py::_gate` |
| M45 的 external requirement slots 既有 deterministic recipe，也有受控 structured proposal 与 `procedure_boundary_v1`；最终 proposal 仍曾失败且其 outbound 只获 diagnostic 授权 | reserve 泛化不能依赖 qst ID/手写 gold slot；若产品 Subgraph使用模型 proposal，必须新建 receiver/purpose/data class、预算和失败关闭合同，不能继承 M45 或普通 API 权限 | `scripts/probe_m45_b3.py::_external_recipe`、`engine/phase4b/rag_requirement_proposal.py`、M45 P4/P4R/P5 lineage |
| business T4 的 TaskState 已持有服务端 required document keys；external reserve 不能把 gold key/title/答案事实放入 runtime | business 可优先确定性形成缺口；external action eligibility 必须从问题、当前已授权 Evidence、结构坐标和安全 proposal 形成，评分 gold 只能在执行后离线使用 | `engine/phase4b/task_runtime.py`、`engine/phase4b/rag_diagnostics.py::RequirementSlot/RAGRecoveryDiagnostic` |
| sealed reserve `f70c5fc...e505` 为 60 题，原 `access_ledger.jsonl` 的 hash 已进入 v1 identity | historical最终no-go，M46不再解封；原manifest/ledger保持只读sealed。未来只有新假设/新candidate先通过historical后才可重新申请一次决策运行 | `eval/cases/agent/phase4b_reserve_manifest.json`、`eval/agent_reserve_contracts.py::seal_reserve/apply_access_event` |
| external 产品默认是 semantic；历史 lexical/semantic baseline、M41/M44A artifact 与 M34 180 题均已解封且协议不同 | historical 只能承担开发/回归，不能替代新 reserve 或与其混分；B4 candidate 不得顺手换 embedding、recipe、Composer 或 corpus | `docs/state/rag-current-state.md`、`docs/state/eval-baselines.md` |
| 当前依赖实际为 LangGraph `1.1.2`；官方文档允许不同 state schema 的 subgraph 在父节点内显式映射输入/输出，并由 conditional edge 停止 | M46 可以保留顶层/子图私有 state 分权，但不能靠框架 recursion limit、MessagesState 或 checkpoint 冒充业务预算、Trace 或 durable state | `pyproject.toml`、本机 package metadata、LangGraph 官方 Subgraphs/Graph API 文档 |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 主图只调用一次，子图内部按状态回边 | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph`、`edges.py::route_after_orchestrator_call`、`graph_state.py::AgentState` | 编译子图、conditional edge、Tool/iteration counter、retrieval key 去重和显式终止 | 顶层 `collect_document_evidence` 作为父动作；RAG 子图使用独立 typed state、closed-world dispatcher、child budget 与 termination，再映射回统一 acquisition result | `MessagesState` 全历史、强制首搜、LLM 自由 Tool call、fan-out、fallback answer、参考项目阈值和 `InMemorySaver` |
| rewrite 与 context expansion 是不同动作 | `agentic-rag-for-dummies/project/rag_agent/tools.py::ToolFactory._search_child_chunks/_retrieve_parent_chunks`、`nodes.py::should_compress_context` | initial child search 与按已有 parent identity 扩上下文分离；记录已执行 search/parent 防重复 | 沿用 M45 两张 action card：rewrite 重新走现有 Knowledge Tool；expansion 只消费当前已授权 Evidence coordinates，并回 SQLite authority 重水化/重授权 | 字符串 Tool Observation、顺序 parent ID、异常正文回显、默认整 parent 展开、模型自行决定预算 |
| 生产 Evidence identity 不能在子图中丢失 | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py::RetrieverResource.get_resources/_get_references`；对照 `DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py::make_knowledge_retrieve.knowledge_retrieve` | chunks 与 structured references 同步返回；纯正文 Tool 会丢 reference 和失败边界 | 子图每一步保留 EvidenceRef、authority/revision/content/anchor、authorization decision 和 ledger stage；最终仍由 DataPilot Shared Gate/Citation Validator消费 | 只用第一个 resource、编号正文/异常字符串作 Observation、文档名列表冒充 claim citation、reference 存在即代表已授权 |
| 多后端/恢复失败不能自动降级成“已完成” | `GustoBot/.../workflows/multi_agent/multi_tool.py::create_kb_multi_tool_workflow/local_search/finalize/_collect_sources` | 固定节点和末端汇合能暴露 PostgreSQL、Milvus、external 的分层结果 | 只借鉴“结果分开记录后再汇合”；DataPilot 的 Pipeline/Subgraph 由服务端 runtime policy 选择，失败不跨 corpus/backend fallback，答案继续由唯一 AnswerFlow生成 | PostgreSQL 无结果自动 Milvus、local 无结果自动 external、任一命中即 complete、最终去重 source 字符串作 citation |
| 不同 state schema 的子图如何接入当前 Loop | LangGraph 官方 [`Subgraphs`](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)、[`Graph API`](https://docs.langchain.com/oss/python/langgraph/graph-api)、[`add_conditional_edges`](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges)、[`Runtime.context`](https://reference.langchain.com/python/langgraph/runtime/Runtime/context) | 父子 state 不同时由父节点显式映射；run dependencies 走 Runtime context；conditional edge 返回 END 稳定停止 | 子图 state 不共享完整 TaskState/父 Graph state；只接 typed acquisition request、父预算 grant 和可信 adapters，输出 acquisition result/child ledger/termination；采用 per-invocation、无跨 turn 子图记忆 | 依赖当前最新版才有的未核验行为、把子图 checkpointer 当 B5 durable state、依赖 framework state inspection 代替 DataPilot Trace/Eval |

参考复核得到的直接结论：ARAG 证明“子图 + 两类 retrieval action + 去重/停止”可实现，但其 Tool 输出、动作控制和 corpus 规模不足以提供 DataPilot 的安全/质量保证；DB-GPT 与 GustoBot 反而说明 reference identity、失败分层和 fallback 很容易在汇合处丢失。M46 因此采用 **小 acquisition interface + 深 Subgraph implementation**：测试和调用方只跨同一 Evidence acquisition seam，内部复杂度不泄漏。

规模与代表性边界：ARAG 是教学型 child/parent demo，GustoBot 是菜谱知识多后端样板，DB-GPT 是平台资源抽象；它们都没有 DataPilot 的 36,417 documents / 139,214 units、60 题 sealed reserve、双 ACL、typed Evidence、父子预算或一题一次 completed artifact。参考源码只能确认 seam 和反例；本模块historical已证明当前Subgraph不值得进入reserve，未来净收益仍须由新candidate的historical与另行授权的reserve证明。

## 4. 目标、优先级与非目标

### 模块完成状态

M46 完成后，系统在不改变上层 Knowledge Tool/AnswerFlow 语义的前提下拥有两个真实 adapter：固定 Pipeline baseline 与 bounded RAG Subgraph experimental adapter。Subgraph 在一次父级文档取证内完成 initial retrieval → Observation → eligible action → rewrite/expansion/stop → Evidence merge/reauthorize → Progress/Termination；父子预算、Trace、API 和 Agent Scenario v4 同源。business T4、同 runtime 两动作选择、historical dev 60×2 与闭集 failure review 均有证据；rollout 合同明确 Pipeline 默认、Subgraph 受控 experimental、无自动跨策略 fallback。sealed reserve 保持未消费，作为未来新假设/新candidate稳定后才可能使用的决策集。

### 必须完成

- 建立 C1 Evidence acquisition interface，Pipeline/Subgraph 两个 adapter 对 AnswerFlow 返回同一结果合同；Pipeline 行为和 identity 保持可回归。
- 建立真实 LangGraph RAG Subgraph，消费 M45 两张 action card与结构 trigger，不把 diagnostic artifact 当生产结果。
- 建立 C3 父子预算：顶层仍只消费一次 Knowledge action，所有 initial/rewrite/proposal/expansion/candidate/context/model 消费进入 child ledger 并汇总回父账。
- 复用 Knowledge Tool、SQLite authority、ACL 双检、Evidence ledger、Shared Gate、Composer 和 Citation Validator；子图不得复制或绕过这些所有者。
- business T4 通过产品 task/Loop seam补齐基础政策与质量专项政策；external 同 runtime 在不同场景分别证明 rewrite→expansion 与 direct expansion，并排除错误动作。
- 新增 additive B4 runtime/contract/Agent Scenario family；M42 v1、M43 v2、M44 v3、legacy M31–M40 artifact和断言不改签。
- 完成 historical dev paired view与闭集review；若candidate可冻结，原路线才允许另行授权reserve。当前三代均no-go，按用户确认停止该分支并保持reserve sealed。
- 输出内容绑定的 `pipeline_default_subgraph_experimental` rollout 结论；decision basis 与 quality claim 使用 B4 已冻结机器合同，默认行为不得静默漂移。

### 建议完成

- 提供零 provider deterministic rehearsal，按一条 business 与两条 external fixture 展示 child action ledger、父子预算和停止。
- 提供可视化安全报告，把一次父动作展开成 child timeline，但仓库投影不保存问题、正文、gold、Prompt 或 raw response。

### 条件触发

- **触发条件**：deterministic structure trigger 无法从 external 开放问法和已授权 initial Evidence 形成可靠 requirement slots/eligible action，且会阻塞同 runtime 两动作泛化。
- **允许动作**：按 G46-1 使用结构化 proposal；模型只提出 ≤2 个 typed requirement slots/action proposal，确定性 validator 继续掌握 allowlist、marker/structure、ACL、预算、duplicate/no-progress 和最终 dispatch。
- **未触发时**：不调用 proposal model；business T4 始终优先消费服务端 required document keys 的确定性 adapter。

- **触发条件**：Subgraph action 后没有新增 Evidence、新增项仍不闭合 requirement、重复 key、ACL/identity 漂移、child budget耗尽或 runtime unavailable。
- **允许动作**：记录 typed no-progress/failed/unavailable/unsafe termination并返回当前合法 Evidence 或明确无 Evidence；是否能回答仍交 Shared Gate。
- **未触发时**：不跨 corpus/backend fallback，不重复同一 action，不扩大 scan/query/top-k，也不生成子答案。

- **触发条件**：historical dev formal run 发现实现缺陷或安全/合同失败。
- **允许动作**：停止 reserve 解封，修复后只在用户新授权下运行最小受影响 dev 范围；candidate/Prompt/预算任何变化都产生新 identity并重新冻结。
- **未触发时**：historical review 通过后锁定 candidate；reserve 运行期间及结果查看后不得再调参。

### 明确非目标

- 不把 rewrite/expansion 暴露成客户端字段或顶层 Action；不允许请求选择 Pipeline/Subgraph、backend、corpus、proposal 或预算。
- 不做开放 ReAct、自由 Thought、动态 Tool 注册、fan-out、多 Agent、跨 corpus 自动 fallback 或无限循环。
- 不改变 external corpus/parser/unit recipe、semantic snapshot、embedding、Milvus collection、active business release、默认模型或 Composer，除非另触发冲突门并经用户确认；这些不是 B4 为过关可调整的旋钮。
- 不在子图生成最终答案、裁决四轴、复制 Shared Gate/Composer/Citation Validator，或把 Progress 当第二个 Answer Gate。
- 不实现 B5 durable checkpoint、进程重启恢复、multi-worker CAS，也不实现 B6 Context Compact；Subgraph 每次父动作内从 typed input 开始，不保存跨 turn program counter。
- 不运行 M34 held-out/all 作为新 decision set；M34/M41/M44A 只作 historical regression，不能与 reserve 混分。

## 5. 关键合同

### C1：Document Evidence Acquisition 深模块合同

- 输入：`KnowledgeRequest`、服务端 typed Evidence requirement/required document keys、trusted caller/purpose、父预算 grant、resolved runtime/corpus identity 和服务端 strategy policy。
- 成功输出：统一 acquisition result，至少含 selected Evidence、完整内部 ledger、pre-generation authorization、safe diagnostics、实际 consumption、termination 和 acquisition runtime identity；Pipeline/Subgraph 均满足同一 interface。
- 失败语义：unavailable、unsafe、no candidate、insufficient coverage、no-progress、budget exhausted 和 contract failure 保持 typed；不得用另一 adapter/corpus 自动兜底，也不得把 partial Evidence冒充 required coverage complete。
- 必须保持的不变量：上层 `RAGTool`/AnswerFlow request shape、Shared Gate、Composer、Citation 和四轴所有权不变；旧 Pipeline adapter仍可独立选择和测试；调用方不需要理解子图 state/action。
- 本模块不冻结的实现细节：Protocol/类名、文件布局、内部 helper 数量和 LangGraph node 名称。

### C2：Bounded RAG Subgraph 控制合同

- 输入：C1 request、initial Pipeline outcome、M45 action card identities、deterministic structure facts、可选 validated proposal 和 child budget。
- 成功输出：每一步形成 `trigger → applicable/eligible/rejected → chosen action → typed Observation → EvidenceDelta → Progress → next/stop`；closed-world action 只有 `query_rewrite_candidate/context_expansion_candidate/stop`。
- 失败语义：无合法动作、重复/no gain、依赖缺失、proposal deny/unavailable、ACL/identity failure 和 child budget exhausted 均稳定停止；停止可带当前仍合法的 partial Evidence，但不能声明 Answer ready。
- 必须保持的不变量：同 action 每个 requirement 最多一次；链长最多 2 个 recovery actions；rewrite 最多 2 个 child retrieval batches；expansion 最多 2 seeds、每 seed scan 8、最多新增 4 Evidence；`procedure_boundary_v1` 仍默认关闭，只有 signed procedure intent + authority forward unit 同时成立才启用。任何更改这些 B3 action card 上限的需要新合同、dev Evidence 和用户确认。
- 本模块不冻结的实现细节：state dataclass/TypedDict 名称、observe/dispatch/merge 是否拆成几个节点，以及 Graph 编译缓存方式。

### C2-ERF：external requirement formation 合同（范围修订）

- 输入：服务端 external question、当前轮已授权 selected Document Evidence、安全的结构坐标事实、已确认的 supplier policy 与 child budget grant；不含 qst ID、gold、文档 title/key、答案事实或人工 verdict。
- 成功输出：最多两个 typed requirement slots，且每个 slot 标明 supplier identity、形成理由类别、focused query、support/coverage 语义与可允许的 recovery action；下游仍由既有 Observation、ACL、预算、duplicate/no-progress 和 dispatch 掌握执行权。
- 失败语义：supplier 不适用、proposal invalid/unavailable、当前 Evidence 无法形成安全 requirement、身份/ACL/预算不满足时返回稳定 typed stop；不得把“已签 M45 recipe”伪装成开放输入的 product requirement，也不得将失败改写为自由 query。
- 必须保持的不变量：M45 action card 继续只证明 action executor；procedure trigger 继续只对其显式结构条件生效；M46 不新增客户端策略字段、不以 qst/title/gold/答案驱动 supplier/slot/seed/action；任何 supplier 的 prompt/raw response/正文只留在既有私有边界，安全投影仅允许 version、枚举、hash、usage 与 action facts。
- 本模块不冻结的实现细节：最终 supplier 算法、内部 prompt 文字、helper/类名与私有 replay 数据结构；它们必须在 G46-4 后由合同和测试固定。

### C3：父子预算与无双循环合同

- 输入：一次顶层 `collect_document_evidence` 父动作 grant、B4 versioned parent profile 和 Subgraph child profile。
- 成功输出：父账仍记一次 Action/一次 Knowledge deep Tool；子账分别记录 initial/rewrite retrieval batches、candidate examined/unique merged/selected/generation-visible、expansion scan/add、proposal/model calls/tokens、timeouts/latency；实际 child consumption汇总回父 ActionAttempt/Trace/Eval。
- 失败语义：任一 child 调用前预算不足则零调用停止；实际消费越界仍如实入账并立即 `budget_exhausted`，不能抹掉；父/子对同一 requirement 不得各自重试一次。
- 必须保持的不变量：旧 B2 budget identity/artifact只读；M46 使用 additive B4 profile/runtime identity。framework recursion limit 只防实现缺陷，不承担业务停止。顶层只看到一次文档取证完成/失败及聚合消费，不能再次因同一 coverage gap调用第二次 Knowledge action。
- 本模块不冻结的实现细节：预算对象是否组合/嵌套，以及安全投影的内部字段排序。

### C4：Evidence 合并、授权与唯一 AnswerFlow 合同

- 输入：initial 与 recovery Evidence、SQLite/active release authority、每项 authorization decision、duplicate key 和 signed requirement。
- 成功输出：所有新增 Evidence 逐项核对 authority/revision/content/anchor、pre-selection 与 pre-generation ACL，按 identity 合并 ledger；只有最终合法 selected Evidence进入现有 Shared Gate，随后才可能推进 generation-visible/cited。
- 失败语义：跨 physical document、stale/revoked/denied、identity 漂移、正文加载失败、duplicate 或 unsupported requirement 不进入 generation context；公开失败不泄露文档是否存在。
- 必须保持的不变量：Milvus 只选 unit identity，SQLite/profile 或 active release仍是正文 authority；Subgraph不生成 claim/citation/答案，不放宽 exact support/citation合同；仓库/Trace/action/context/artifact不保存完整正文、raw query/gold、Prompt、raw response、Thought 或凭据。
- 本模块不冻结的实现细节：内部 ledger merge helper、authorization batch实现和 context packing容器。

### C5：Runtime 选择、兼容与同源投影合同

- 输入：服务端 strategy policy、runtime scope、resolved product identity、C1/C2/C3/C4 同次事实。
- 成功输出：Pipeline/Subgraph 各有稳定 strategy/runtime/contract identity；API、JSONL Trace、RAG Eval 与 additive Agent Scenario v4 从同一 acquisition facts 投影 child attempts、budget、EvidenceDelta、progress/termination 和 AnswerFlow结果。
- 失败语义：客户端 strategy 字段、未知 runtime、identity漂移、缺 child execution、额外 action/assertion、父子账不守恒或 unsafe private payload 均拒绝 completed。
- 必须保持的不变量：普通 legacy、M42 v1、M43 v2、M44 v3 与 B2 deterministic rehearsal不补字段、不改签；Pipeline旧行为由显式 adapter identity回归。产品默认只由 G46-2 决定，不能由“是否存在 Subgraph字段”猜测。
- 本模块不冻结的实现细节：公开字段名的最终拼写和 report排版，但 schema/allowlist/identity必须在实现前由 B4 contract固定。

### C6：Historical 与 sealed reserve A/B 合同

- 输入：同一 external profile/semantic/Composer/model/outbound/caller 的 Pipeline/Subgraph candidate、paired RunSpec、closed-world assertion/review protocol，以及不可变 reserve v1 manifest。
- 成功输出：historical dev 同一60 questions两臂各执行一次，形成completed artifact、paired compare、完整child/usage投影与闭集failure review。只有historical支持冻结candidate时，才允许另行授权sealed reserve 60×2。
- 当前终局：三代historical均completed，最后一代`m46-historical-paired-20260826-164511`完成闭集rollout评审但未达到candidate晋级门。因此candidate保持experimental，reserve分支按用户确认停止，v1 manifest/ledger继续sealed/只读，逐题records read=0；原始Gate和paired数字由Eval账本保留。
- 失败语义：partial manifest冒充completed、身份漂移、为评分自动重跑、把historical冒充未污染决策、把sealed写成consumed，均fail closed。未来重开必须提出新能力假设、产生新candidate identity、先在historical证明稳定，再取得新的精确授权；不能继承本模块旧运行授权。
- 必须保持的不变量：历史artifact不改签；原reserve/`access_ledger.jsonl`不原位修改；Pipeline/Subgraph两账分离；任何真实运行仍遵守runbook的一次run_id、无自动重跑。
- 本模块不冻结的实现细节：外部 run目录名和并行度；它们必须在不改变一题一次、双臂盲化、provider限流和 artifact identity的前提下于开工 notes登记。

### C7：Default/experimental/fallback 决策合同

- 输入：优先使用C6 completed reserve artifact；若historical连续未达到candidate晋级门且用户明确选择experimental rollout收口，则使用来源哈希通过的最后一次historical closed-set review、paired compare、contract/security Gate、成本视图和sealed audit。
- 成功输出：
  - `subgraph_default`：只有 required安全/身份/预算全绿，Subgraph 在 paired语义 pass与多文档 completeness/cited coverage上形成预注册净正收益、无关键分层退化，且用户接受额外调用/token/latency后成立；Pipeline保留 fallback；
  - `pipeline_default_subgraph_experimental`：净收益不稳定、主要收益被成本抵消、出现关键退化或证据不确定时成立；Subgraph仍完整可运行、可评测，Pipeline继续默认。
- 当前终局：用户于2026-08-26确认`pipeline_default_subgraph_experimental`；reserve=`sealed/not_run`、automatic cross-strategy fallback=`false`，decision basis与quality claim沿用已冻结B4机器合同。该终局交付完整experimental能力，不改变Pipeline稳定默认。
- 失败语义：没有闭集historical review、没有用户rollout收口确认、rollout与服务端默认不一致、把reserve状态写错或隐藏评测结论时只能`review_required`，M46不得收工。
- 必须保持的不变量：实现完成与默认切换分离；默认变化必须由用户确认并记录。没有稳定净收益时不允许把“experimental adapter存在”表述为质量提升。
- 本模块不冻结的实现细节：面向用户的报告措辞；净收益 required/advisory字段和 paired排序在任何 formal run前写入并 hash冻结。

## 6. 工作切片与执行顺序

### M46-A：B4 contract、reserve lifecycle 与 candidate identity

- 优先级：必须完成
- 依赖：M42 sealed reserve、M44 B2 contracts、M45 v4 handoff
- 实施内容：建立 additive B4 contract/manifest、C1–C7 machine-readable identity、Pipeline/Subgraph strategy、父子预算、child action/assertion闭集、reserve v2 run ledger 和 default decision schema；对账原 sealed manifest但不读取逐题内容。
- 关键合同：C3、C5、C6、C7
- 交付物：B4 contract bundle、compatibility matrix、reserve lifecycle validator、tamper fixtures
- 验证方式：identity/hash/closed-world tests；拒绝原位 ledger修改、提前 gold/result访问、额外 arm/execution/action/assertion和旧 artifact改签
- Live Probe checkpoint：不适用；本切片纯静态合同，不访问真实 RAG/provider/reserve逐题内容
- 完成门：candidate/RunSpec尚未执行但所有完成/污染反例可确定性判定；reserve仍为 sealed

### M46-B：C1 深 acquisition seam 与 Pipeline adapter

- 优先级：必须完成
- 依赖：M46-A
- 实施内容：把 AnswerFlow对单个 `KnowledgeTool` 的内部依赖收敛为 Document Evidence Acquisition interface；用 Pipeline adapter封装现有一次 retrieval，保证旧 RAGTool/AnswerFlow行为、diagnostics、Evidence和四轴不变。
- 关键合同：C1、C4、C5
- 交付物：acquisition interface、Pipeline adapter、兼容 projection/tests
- 验证方式：replace-don't-layer：通过 acquisition interface断言行为，不新增只测 pass-through adapter的重复浅测试；M31–M44A Pipeline回归显式 pin旧/新兼容 identity
- Live Probe checkpoint：不适用；此切片只建立等价 seam，不改变真实产品效果
- 完成门：删除该 module会让 acquisition复杂度回流 AnswerFlow/调用方；Pipeline结果与既有 fixture逐字段等价，旧 interface无需调用者学习新参数

### M46-C：business Subgraph 首条纵向链与父子预算

- 优先级：必须完成
- 依赖：M46-B；本切片只走 business 服务端 required keys，不依赖 G46-1 的 external proposal 选择
- 实施内容：建立 per-invocation typed RAG Subgraph、child ledger和 deterministic dispatcher；先接 business initial → rewrite → merge/reauthorize → stop，嵌入一次父级 `collect_document_evidence`，不接 external expansion前先跑通父子账。
- 关键合同：C2、C3、C4
- 交付物：可编译 Subgraph、business recovery action、父子 consumption/termination、安全投影
- 验证方式：fake/real-local tests覆盖缺 basic、一次补齐、错误 expansion拒绝、ACL deny、duplicate/no-progress、budget precheck/actual overrun和Shared Gate唯一性
- Live Probe checkpoint：after M46-C / before M46-D，执行 `M46-P1`；P1 只有 `continue` 才允许继续 external action接线
- 完成门：business T4在一次父 Knowledge action内补齐required Evidence或按三态正确停止；顶层没有第二次 Knowledge call

### M46-D0：external requirement formation 前置能力

- 优先级：必须完成；属于 M46/B4 的内部前置切片，不新增模块编号或里程碑。
- 依赖：M46-P1=`continue`、G46-1、M45 action-card lineage；不依赖 P2/P3。
- 实施内容：建立从服务端问题、当前已授权 selected Evidence 与允许的结构坐标形成 typed external requirement 的独立能力和合同。它必须明确区分“已签 requirement 下的 M45 action executor 已证明有效”与“开放问题 requirement 由谁、按什么证据形成”；不得读取/写入 qst ID、gold、title、答案事实或用它们选择 action。现有 procedure trigger、受控 proposal 与任何新的 deterministic candidate 都只能作为该能力的显式 supplier，不能以单题补丁默认接入。
- 关键合同：C2-ERF（见本节修订）、C2、C3、C4。
- 交付物：versioned requirement-formation contract、supplier/validator 选择闭集、safe/private projection 边界、离线 replay fixtures 与 action-card compatibility matrix；未形成可执行 requirement 时必须 typed stop。
- 验证方式：不以 qst_0420 的既有 recipe 作为产品输入；通过 dev paraphrase、M45 immutable action-card replay、negative（数值/标识、无共同语义、ACL deny、proposal invalid/no requirement）和 action 后 Evidence support 证明输入、输出和失败语义。任何 supplier 都必须在不看 gold/title/答案的情况下形成相同 typed contract；单题自然未触发只记 `not_exercised`，不能用调阈值重跑补齐。
- Live Probe checkpoint：D0 离线合同/重放通过后、M46-D 首条真实 external chain 前，新增 `M46-P0` 最小 historical diagnostic dev Probe；它只观察 requirement formation → eligible action 的实际安全投影与 usage，不执行未预注册的 action。仅 `continue` 放行 M46-D；`revise/stop/inconclusive` 均冻结 P2/P3/E。其精确场景、调用上限和出站面在 G46-4 设计冻结后登记，不能继承已失效的 P2 重验授权。
- 完成门：至少一个非 qst-static supplier 在真实 external runtime 形成可执行 requirement 或以预注册失败语义停止，且离线兼容/负断言证明它没有把 M45 scenario recipe、gold/title/答案事实搬进产品；此时才允许开始 M46-D 的 rewrite→expansion chain。

### M46-D：external rewrite/expansion 与结构 proposal

- 优先级：必须完成
- 依赖：M46-P1=`continue`、M45 action cards、G46-1、M46-D0 requirement formation Gate=`continue`
- 实施内容：接入 external semantic initial、deterministic structure trigger、受控 proposal（若选）、rewrite child retrieval、sibling/forward expansion和合并重授权；同 runtime按 Observation形成 eligible set，不按 qst/runtime静态映射动作。
- 关键合同：C2、C3、C4
- 交付物：external action executors、proposal outbound/validator（若选）、两条闭合子图路径
- 验证方式：qst_0420 rewrite→expansion、qst_0431 direct procedure expansion、qst_0461非 canonical扩展；删除Observation/structure facts后原选择不再合法；gold/title/答案值/跨文档/unsafe proposal拒绝
- Live Probe checkpoint：after 第一条 external rewrite→expansion / before direct expansion收口执行 `M46-P2`；P2=`continue` 后完成 direct expansion并执行 `M46-P3`，P3阻塞 M46-E
- 完成门：P2/P3均有明确 `continue`，或修复后按 runbook最小重验闭合；任何 `stop` 未处理不得继续

### M46-E：产品接线、同源 Trace 与 Agent Scenario v4

- 优先级：必须完成
- 依赖：M46-P2/P3=`continue`
- 实施内容：把 Subgraph作为服务端 experimental strategy接入 business/external RAG factory与task Loop；扩展安全 ToolObservation/Trace/API/Eval投影；建立 additive Agent Scenario v4和deterministic rehearsal；客户端无strategy开关。
- 关键合同：C3、C5
- 交付物：产品 runtime接线、v4 artifact/rehearsal/report、compatibility/security tests
- 验证方式：business T4、external两动作、no-progress/budget/ACL/outbound/prompt-injection/runtime unavailable；API/Trace/Eval同源；旧 v1/v2/v3和legacy family显式回归
- Live Probe checkpoint：P1–P3已覆盖真实影响面；若 E 改变其覆盖的核心策略/调用/安全/预算，按 runbook判定并执行最小受影响重验，不能沿用失效证据
- 完成门：experimental adapter完整可运行、可回退、可追踪；Pipeline仍可显式作为 baseline，产品默认尚不因代码存在而切换

### M46-F：historical dev paired run、闭集review与止损

- 优先级：必须完成
- 依赖：M46-E、G46-3 historical范围精确授权
- 实施内容：完成contract/security回归，并按精确授权运行external historical dev full 60的Pipeline/Subgraph paired view与闭集review。允许在本切片内显式revise；若最后候选仍明确no-go，则执行用户确认的止损，不冻结candidate、不申请reserve。
- 关键合同：C5、C6、C7
- 交付物：三代historical completed artifact/report/compare、最终closed-set review、失败簇与usage账、reserve sealed audit
- 验证方式：120 physical executions恰好闭合、双臂协议仅允许strategy/child-runtime差异；安全/预算/identity全绿；大规模失败层和成本可解释
- Live Probe checkpoint：不适用；本切片是真实 Formal Eval，必须使用G46-3精确授权，不能计入Live Probe或自动运行
- 完成门：最终run双臂60/60 completed、review闭集、失败/usage/identity可解释；结果若支持则冻结candidate，否则必须有用户确认的`no_go_revise_stop`与精确重开门。当前按后一终局闭合。

### M46-G：轻量 rollout 决策与 reserve 保全

- 优先级：必须完成（2026-08-26经用户确认由原reserve运行改为轻量rollout）
- 依赖：M46-F closed-set review、用户 experimental rollout 收口确认
- 实施内容：不解封reserve；校验v1 manifest/ledger仍sealed且逐题read=0。把historical run/review、Pipeline默认、Subgraph server-controlled experimental、无自动跨策略fallback、quality claim未建立和未来重开门写入内容绑定B4 rollout合同。
- 关键合同：C6、C7
- 交付物：内容绑定rollout decision、historical closed-set review、reserve sealed audit、仓库外reopen todo
- 验证方式：合同hash/tamper、服务端默认与rollout一致、客户端不可选strategy、Subgraph仍可显式运行、无自动fallback、reserve manifest/ledger只读对账
- Live Probe checkpoint：不适用；本切片不执行provider、Milvus或reserve逐题读取
- 完成门：C7=`pipeline_default_subgraph_experimental`，basis/no-quality-claim/sealed/reopen字段闭合且与代码、plan、notes/state一致

### M46-H：收工验证与 B5 handoff

- 优先级：必须完成
- 依赖：M46-G 轻量rollout合法终局
- 实施内容：聚焦/受影响/全仓回归、artifact/hash/状态对账、notes Probe与Formal Eval审计、技术档案和capability handoff；按项目流程执行 `finish-module → finish-docs → 用户人工检查 → accept-module`。
- 关键合同：C1–C7
- 交付物：最终验证快照、M46 notes/state/changelog、M47/B5 handoff
- 验证方式：第8节全部required门、全仓deterministic pytest、compileall、diff check、artifact/review/ledger回读
- Live Probe checkpoint：只审计P1–P3是否在切片时点发生；不得在收工阶段首次补跑冒充Probe
- 完成门：B4完整交付且状态文档不把experimental写成default/quality win；M47强制前置清楚

## 7. 决策门

### G46-1：external recovery requirement/proposal adapter

**决策状态：已确认。用户于 2026-08-25 选择方案 A。M46 后续按“deterministic-first + 受控 structured proposal”实施，方案 B 仅保留为已评估但未采用的对照方案。**

#### 方案 A：deterministic-first + 受控 structured proposal（已选择）

- 做法：business继续使用服务端 required keys；external先用 M45 `procedure_boundary_v1` 等确定性结构事实，只有无法可靠判断unsupported requirement时才把问题与**已授权、最小化的当前 Evidence context**发给 Qwen `qwen3.7-plus`，purpose=`rag_recovery_requirement_proposal`。模型只返回≤2个typed slots/action proposal，本地validator掌握所有执行权。
- 影响：能把 M45 diagnostic proposal提升为可泛化的experimental产品能力，reserve不依赖qst手写recipe；增加独立chat call/token/latency和新数据出站面。
- 适用条件：用户接受 external public benchmark question/context用于该新purpose；business role-restricted policy默认不因此获得普通API出站许可。
- 风险：proposal可能不稳定或invalid；必须零动作/保守stop，不能fallback成自由rewrite。该模型变量会与Subgraph整体一起评估，不能宣称单组件因果。

#### 方案 B：纯确定性结构 dispatcher（未选择）

- 做法：只使用服务端 required keys、question-derived结构、Evidence coordinates和M45 deterministic trigger，不新增proposal模型/outbound。
- 影响：安全和成本更简单，但 external开放问题可能无法形成可靠 slots；若只能靠已知qst手写recipe通过，就不能解封reserve或宣称B4泛化。
- 适用条件：M46-D在不使用qst ID/gold/title/答案事实的dev paraphrase与真实Probe上已证明两动作选择和错误动作排除。
- 风险：为避免模型而把能力缩成demo特判；一旦dev Gate失败，必须回到方案A或修订M46，不能降低最终B4标准。

#### 建议与确认时点

- 最终选择：方案A；该决策已完成，不再阻塞 M46-D 的 external 真实接线。
- 建议理由：M45 已证明纯question-derived coverage会把 qst_0431误判为完整，且手写external recipe不能承担60题reserve泛化；方案A把语言理解放在proposal位置，同时保留确定性Controller、预算和安全门。
- 已放行范围：完成前置合同与 business slice 后，可按本计划接入真实 proposal outbound 和 external P2/P3；Formal Eval 仍必须单独通过 G46-3 精确授权。
- 重开决策的条件：A在historical dev形成稳定invalid/no-benefit簇，或安全/成本不可接受；B只有在上述泛化Gate已真实通过时才可替代A。

### G46-4：external requirement formation 范围修订

**决策状态：已确认。用户于 2026-08-25 选择方案 A：先在 M46 内完成 requirement formation 前置能力；2026-08-26 进一步确认采用 question-grounded atomic obligation supplier 具体合同。**

#### 方案 A：M46-D0 独立闭环（已选择）

- 做法：把 external requirement formation 从 action executor 中显式拆出为 D0/C2-ERF。先冻结 supplier、validator、safe/private 投影和 action-card compatibility，再做一次独立最小 Probe；只有 D0=`continue` 才重新进入原 M46-D/P2。
- 影响：M46 仍完整对应 B4，但外部路径多了一个不可跳过的内部 Gate；已失败 P2/P2R 均保留为 exploratory `revise` 证据，不再被当作“再调一次就能放行”的授权。
- 适用条件：当前 M45 的 scenario-specific signed slots 不能直接成为产品输入，且 proposal/heuristic 已形成稳定失败簇。
- 风险：D0 可能证明现有 supplier 都不足，此时 M46 停在明确未完成状态并需要新的路线决策；不得把 requirement formation 简化成 qst recipe 或让 M47 承担。

#### 方案 B：直接继续修 P2 runtime（未选择）

- 做法：只定位 `subgraph_runtime_failure` 并继续 P2R9。
- 影响：短期可能获得 action 执行，但无法证明 requirement 的产品来源合法或可泛化。
- 适用条件：仅当已有非 qst-static requirement supplier 已独立通过 D0 时才可能成立。
- 风险：围绕单题不断改变 heuristic/Prompt，污染 candidate、耗尽开发预算而不解决输入合同缺口。

#### 建议与确认时点

- 已确认范围：只允许 D0 的只读复核、合同/离线 replay/test 实现；禁止 P2R9、P3、M46-E、historical/reserve Formal Eval、默认切换。
- 已确认具体合同：D0 使用独立 `form(input) -> result` deep module；procedure deterministic 优先，其他开放问题由模型只提出最多两个 question-grounded atomic obligations，模型不生成最终 focused query、不裁决 coverage、不生成 action；所有 question anchor/aspect/entity constraint 必须来自题面 source span，value shape/qualifier 本地复核，identity/query/marker/coverage/allowed action 由服务端形成。输出以 additive `FormedRequirement` 包装 M45 `RequirementSlot`，不改签旧 action card；未验证的 `evidence_gap_v1` 从当前候选撤回但历史证据保留。
- 需要再次确认的时点：M46-P0 精确真实调用范围，以及 P0 结果后是否恢复 M46-D。D0 本地实现/测试确认不自动构成真实出站授权。
- 重开决策的条件：D0 发现必须改变 action card、预算、external corpus、默认行为或数据出站安全边界；届时暂停并提交新的选项，不能自行替换。

### G46-2：Pipeline/Subgraph 产品默认

**决策状态：已确认。用户于2026-08-26在最后一次historical v3未达到candidate晋级门后选择方案A；Pipeline保持默认，Subgraph保持server-controlled experimental，不启用自动跨策略fallback。**

#### 方案 A：Pipeline 默认，Subgraph experimental（无净收益时建议）

- 做法：普通产品仍走Pipeline；Subgraph只在服务端受控experiment/eval runtime可选，Pipeline保持baseline与稳定产品路径。
- 影响：B4能力完整但不宣称质量提升；演示和后续研究仍可复现Subgraph。
- 适用条件：reserve净收益不稳定、关键分层退化、成本不被接受或C7为`review_required`。
- 风险：用户体验默认不获得恢复收益，但不会为“Agentic”标签支付不确定成本。

#### 方案 B：Subgraph 默认，Pipeline fallback

- 做法：task/business/external对应服务端runtime默认选择Subgraph；只有在**任何 retrieval/proposal/provider 子调用发生之前**即可确定的 adapter 技术不可用，才允许回到**同 corpus、同 resolved runtime 的 Pipeline**。一旦已有任何子消费，或遇到安全拒绝、ACL deny、contract/identity failure、budget exhausted、no-progress，均不触发fallback重跑。
- 影响：用户默认得到Observation-driven多步取证；调用、token与延迟提高，默认runtime/Trace identity变化。
- 适用条件：C7 `default_eligible`，用户审阅paired语义/coverage/citation/cost后明确确认。
- 风险：reserve单轮仍不能证明生产吞吐/长期稳定性；fallback必须防双执行和预算重复。

#### 建议与确认时点

- 最终选择：方案A。依据是最后一次historical closed-set评审与experimental rollout收口确认，不是reserve胜负；quality claim明确为`not_established`。
- 建议理由：roadmap已冻结“实现与默认化分离”，M44A也证明技术闭链不能等同质量胜出。
- 用户确认前允许推进：完整实现experimental adapter、historical/reserve候选运行和报告。
- 用户确认前禁止推进：修改产品默认、active strategy identity或把实验结果写成质量提升。
- 后续无需在M46再次确认默认；未来只有新候选先在historical形成稳定提升、且用户重新授权decision run时才能重开。
- 重开决策的条件：未来新的sealed candidate证明不同结论；不得用已消费reserve反复调参后重新决策。

### G46-3：历史决策——两次大规模 Formal Eval 精确运行授权

**最终状态：historical已分三代按独立授权完成，最后一代仍no-go；用户确认不执行reserve 60×2，reserve继续sealed。本节以下方案保留为原始决策依据，不再构成本模块待执行项。**

#### 方案 A：按计划完成 historical 60 paired + reserve 60 paired（建议，也是B4完整验收范围）

- 做法：M46-F先运行historical dev 60×2 arms；candidate冻结后，M46-G运行sealed reserve 60×2 arms。每个授权各只创建一个run_id，预计调用/token上限在runner实现和dry-run清单完成后给出精确数字并由用户确认。
- 影响：同时获得可调试的大规模回归与未污染默认决策；真实provider费用和人工review工作量较大。
- 适用条件：runtime/preflight ready、candidate hashes/RunSpec/预算/停止条件已冻结，长任务按AGENTS后台执行。
- 风险：provider unavailable或partial completed造成`inconclusive`；不得自动换ID、重跑或缩分母。

#### 方案 B：暂不授权其中任一大运行

- 做法：停止在M46-E或M46-F前置状态，只保留已实现代码和deterministic/Probe证据。
- 影响：可继续人工看代码，但M46/B4不得宣称完成，reserve保持sealed（若尚未解封），也不能做默认决策。
- 适用条件：当前费用、时间、provider或人工review条件不允许。
- 风险：B4硬交付未闭合；不能把Formal Eval降成模糊后续项或转嫁给M47/B5。

#### 建议与确认时点

- 建议：方案A，但分两次精确授权；historical通过并冻结candidate后才申请reserve授权。
- 建议理由：先用已污染dev发现实现/泛化问题，能保护唯一reserve；两次分账也使失败不会自动消耗decision set。
- 用户确认前允许推进：所有deterministic tests、P1–P3、runner dry-run、RunSpec/hash/预算清单和preflight。
- 用户确认前禁止推进：historical full、reserve逐题读取/运行、任何扩大到M34 held-out/all的执行。
- 需要确认的时点：M46-F运行前一次；M46-G首次解封前再次。
- 重开决策的条件：candidate变化、预算变化、provider/runtime identity变化或上一次run非completed；均需新的精确授权，不自动继承。

## 8. 验证与验收矩阵

### Live Dev Probe（开发期真实探针）

本模块修改真实 business RAG、Enterprise semantic/Milvus、API task与proposal outbound，因此开工时预注册P1–P3。实际开发中P1 passed，D0的P0R passed/continue，P2真实执行为failed/revise；用户随后明确要求暂停其余Dev Probe并把未闭合项移入仓库外todo。2026-08-26 experimental rollout收口进一步确认：P2结果与P3未执行状态如实保留，不倒填passed、不在finish-module补跑；P3从experimental-only终局的完成门豁免，未来重开必须重新登记/授权。standing authorization、计数、禁区、重验和Formal Eval分账仍引用`docs/state/runbook.md`。

| Probe ID / 执行时点 | 探针场景 | 真实产品链路/依赖 | 需要观察的结果与 Trace 事实 | 通过/失败/不确定标准 | 决策与停止条件 |
| --- | --- | --- | --- | --- | --- |
| `M46-P1` / after M46-C、before M46-D | business T4 canonical policy turn；父级SQL前置使用已验证deterministic adapter，文档侧使用active 22-entry release与真实caller/ACL | `/api/query task → B2/B4 parent Loop → collect_document_evidence → business Subgraph initial lexical → rewrite → Answer Gate → Hybrid synthesis`；零remote provider | initial仍为quality present/basic missing；Subgraph补basic且保留quality；父Action=1、child路径/预算/Delta/stop同源；wrong expansion拒绝；API/Trace无正文/Prompt；最终Hybrid只消费Gate允许Evidence | passed：业务oracle、父子账、安全负断言和最终Evidence coverage全绿；failed：任何确定合同/语义错误；inconclusive：active release/identity不可观察 | passed→continue M46-D；实现缺陷→修复后最小重验；identity自然变化已一次取全→记录inconclusive/stop，不制造失败，重新判断business验收路径 |
| `M46-P2` / after M46-D0=`continue` 且 external rewrite→expansion 首链完整、before direct expansion收口 | historical diagnostic dev `qst_0420` 一次 | product fixed-RAG API → existing semantic profile/Milvus → D0 frozen supplier → rewrite child retrieval → sibling expansion → existing Qwen Composer/citation | requirement supplier identity/slot validator、rewrite新增目标fragment、第二Observation准入expansion、最终coverage/citation/answer；actual calls/tokens/latency、child budget、wrong action、reserve access=0 | passed：恢复链与最终语义oracle均通过且安全/预算闭合；failed：确定错误；inconclusive：provider/runtime unavailable或自然未触发所需分支 | passed→continue direct expansion；failed→revise/stop且不换题/backend/参数。D0 前的全部 P2R 仅是 exploratory revise 证据，不能替代本 checkpoint |
| `M46-P3` / after direct expansion、before M46-E | historical diagnostic dev `qst_0431` 一次 | product fixed-RAG API → semantic initial → deterministic `procedure_boundary_v1` direct expansion → existing Composer/citation | 不依赖gold/qst ID或proposal猜缺口；direct expansion eligible、rewrite rejected、forward同文档Evidence gain；budget/no-progress/ACL/identity/answer语义 | passed/failed/inconclusive同P2；自然proposal未调用应记0且passed，不为展示额外调用 | passed→continue产品接线/候选冻结；failed/inconclusive未处置则stop，不解封reserve |

Probe共同收紧项：

- P1只使用deterministic SQL fixture，不写数据库；business release只读。P2/P3只使用已解封historical diagnostic dev，不触碰reserve/M34 held-out/all，不reset/rebuild Milvus，不切lexical/embedding/Composer/default。
- P2/P3每题首次一次；两题累计真实provider attempts预计≤8、observed tokens≤30000。proposal、embedding、Composer、retry均按实际逐次记账；意外越界后记录并停止。
- gold只在执行结束后作离线语义oracle，不进入trigger/query/proposal/seed selection。P1业务required keys来自服务端TaskState，不是评分器注入。
- P2/P3中应自然触发的recovery路径若未触发，该子能力为`inconclusive/not_exercised`，不能靠改query/top-k或重跑展示。
- Probe终局审计：P1=`passed/continue`；P0首次failed/revise后P0R=`passed/continue`；P2=`failed/revise`并成为historical迭代输入；P3=`not_executed/user_deferred`，只对本次Pipeline-default/Subgraph-experimental轻量终局豁免，绝不冒充真实成功证据。
- 本模块Formal Eval终局：historical dev full paired已完成三代，最后一代closed-set review=`no_go_revise_stop`；用户确认停止reserve分支。不得在finish-module阶段补跑reserve或把它记作completed。

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 acquisition interface | Pipeline/Subgraph contract tests + deletion test | 两adapter同interface；Pipeline等价；AnswerFlow/调用方不感知child state/action | 必须完成 |
| C2 Subgraph control | graph/state/edge tests + P1/P0R/P2时间线 + P3豁免记录 + v4 rehearsal | 两动作/stop closed-world；父子预算与安全合同确定性闭合；真实P2失败和P3未执行不被隐藏 | 必须完成（experimental-only） |
| C3 parent-child budget | precheck/actual overrun/tamper tests + API/Trace对账 | 父Action/Knowledge=1；child逐维守恒并汇总；无父子双循环、无框架limit冒充预算 | 必须完成 |
| C4 Evidence/ACL/AnswerFlow | authority/ACL/revision/duplicate/ledger/Gate/citation tests | 每项回源重水化+双授权；只有Gate允许Evidence进Composer；Subgraph零子答案 | 必须完成 |
| C5 runtime/compatibility | Agent Scenario v4 + M31–M45回归 | API/Trace/Eval同源；客户端不能选strategy；旧v1/v2/v3与legacy原断言不改 | 必须完成 |
| C6 historical run | 60×2 completed artifact/review/compare | execution/arm/assertion闭集、identity可比、失败层/成本/语义review完整；不解封reserve | 必须完成 |
| C6 reserve保全 | manifest/ledger sealed audit + 仓库外reopen todo | reserve未解封、逐题read=0、未伪造decision结果；未来重开门精确 | 必须完成（替代原reserve run） |
| C7 rollout | 内容绑定decision + 用户确认记录 | Pipeline默认、Subgraph experimental、no auto fallback、quality未建立、historical/review/sealed identity闭合 | 必须完成 |
| 安全与私密投影 | injection/outbound/ACL/tamper tests + artifact scan | 零正文/raw query/gold/Prompt/raw response/Thought/凭据泄漏；unsafe零recovery | 必须完成 |

聚焦测试顺序：C1 Pipeline等价 → C2 child state/action → C3父子预算 → C4 authority/ACL/ledger → C5 API/Trace/Scenario v4 → C6 runner/ledger/review/compare → C7 rollout。

全量回归范围：M31–M34 Knowledge/Evidence/Answer、M35–M40 legacy Harness/Hybrid/assurance、M41 RAG Eval、M42 reserve/B0、M43 task、M44 B2/Scenario v3、M44A semantic runtime、M45 diagnostic/qualification，以及全仓 deterministic pytest。预计超过2分钟的完整回归按`AGENTS.md`后台规则执行；不再运行新的M46 Formal Eval。

不可外推结论：P1–P3不能证明总体质量、Reliability、吞吐、多worker或default收益；historical dev可用于开发和止损，不能冒充未污染reserve决策。Subgraph Evidence gain不等于答案正确，自动Gate/citation不替代闭集语义review；当前rollout只证明为何保留Pipeline默认，不证明Subgraph的未来上限。

历史artifact边界：M34/M39/M41/M42/M44A/M45 completed artifact只读、不补字段、不改签；M46引用identity/SHA-256并创建additive v4/runtime/reserve artifact。原sealed reserve文件和hash保持不可变。

## 9. 依赖与交付物

### 依赖

- 已完成并验收的 M42/B0、M43/B1、M44/B2、M45/B3，以及不占B里程碑的M44A Enterprise semantic产品runtime。
- M45 v4 action cards、typed Observation/requirement slot/structure trigger、sibling/forward expansion、proposal validator和safe/private lineage。
- B2 TaskState/Loop/KnowledgeRuntimeResolver、现有 Knowledge Tool/AnswerFlow/Shared Gate/Citation、business active release和Enterprise SQLite authority + Milvus semantic runtime。
- `docs/state/runbook.md`、`runbook-rag.md`、`rag-current-state.md`、`eval-baselines.md`与sealed reserve manifest的运行/身份/污染边界。
- G46-1已确认采用方案A；historical三代授权与结果见notes；G46-2已确认Pipeline默认/Subgraph experimental；用户已确认experimental rollout收口并停止reserve分支。

### 交付物

- additive B4 contract/manifest、parent/child budget和Pipeline/Subgraph策略identity；
- Document Evidence Acquisition interface、Pipeline adapter和bounded RAG Subgraph experimental adapter；
- business/external recovery executors、可选structured proposal outbound/validator、Evidence merge/reauthorization；
- 产品task/Knowledge factory接线与安全API/Trace投影；
- additive Agent Scenario v4、deterministic rehearsal、contract/security/tamper tests；
- historical dev paired artifact/review/compare；
- sealed reserve只读保全证据与仓库外精确reopen todo（本模块不产生reserve paired artifact）；
- 内容绑定的default/experimental/no-auto-fallback决策记录、仓库安全manifest和historical immutable artifact；
- M46 notes、技术档案、学习复盘和M47/B5 handoff。

只冻结交付物职责，不提前固定不必要的文件名、类名、Graph node名、并行度、run_id或报告UI。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：B5 durable task state、restart/multi-worker/CAS/TTL持久化；B6 deterministic typed Compact与全阶段extended sequence；生产SSO/connector ACL/吞吐优化仍不在Phase 4B主线。
- 下一模块可直接消费的产物：M47/B5消费稳定TaskState/turn boundary、B4 runtime/termination/child ledger和最终默认策略；恢复后只从任务边界重进Loop，不能恢复RAG Subgraph program counter。
- 后续需要根据真实诊断重新规划的内容：当前`pipeline_default_subgraph_experimental`来自用户确认的historical rollout收口，不是reserve判胜。诊断结构与重开门已写入仓库外todo；未来只有新的Evidence run identity修复、Composer structured-output方案或formation grounding假设形成新candidate，并先通过historical后，才可重新申请使用仍sealed的decision reserve。
- 可能存在的风险：M45 external slots过度依赖已知题；proposal不稳定或新增出站不被接受；child消费无法从现有diagnostics完整观测；expanded Evidence增加context却降低Composer正确性；120+120 paired executions费用/耗时较大；semantic/Milvus运行依赖可能使artifact inconclusive。对应控制是G46-1、同源child ledger、Shared Gate唯一性、historical先行、两次精确授权和三态停止。
- 强制后续开工条件：M47只能在修订后的C1–C7 required全部闭合、G46-2轻量rollout合法、M46完成`finish-module → finish-docs → 用户人工检查 → accept-module`后开工。experimental-only是本次授权的合法B4终局；`review_required`不是。
- 最终验收标准：M46以第8节修订后的必须项、已执行/暂缓Probe事实、historical completed artifact与闭集review、reserve sealed audit和用户轻量rollout决策为准；Phase 4B最终仍须在M47/B5、M48/B6后满足roadmap Definition of Done，不得把B4完成外推为阶段完成。

## 11. 开工条件

- 开工前无需确认：M46完整对应B4；M45 v4 `go_for_M46`与reserve sealed成立；顶层只保留一次`collect_document_evidence`；Pipeline长期保留；Subgraph必须完整实现但默认化分离；不改corpus/embedding/Composer/active release；M47=B5、M48=B6。这些由roadmap/state/用户本轮模块映射要求确定。
- 已确认并放行：G46-1采用方案A，允许在完成前置切片后实施受控external proposal/outbound；该确认不包含任何Formal Eval运行授权。
- 已确认并停止：historical最后候选已运行并no-go；G46-2选择Pipeline默认/Subgraph experimental；reserve保持sealed、不再申请本模块运行授权。
- M46 notes开工checklist必须预登记P1/P2/P3的时点、阻塞切片、预计calls/tokens和reserve=sealed；同时登记外部artifact新版本目录与原v1.0.0只读分离断言。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支。experimental rollout收口只豁免本模块reserve运行，不得删除两张动作、父子预算、business T4、historical view、默认决策或把评测结论改写成质量提升。
