# M45 Phase 4B B3 RAG 失败漏斗与 Action-level Evidence 开发计划

> 能力里程碑：B3；本模块完整承担 B3，只诊断并准入 RAG recovery action，不提前实现 M46/B4 RAG Subgraph
>
> 主要问题：现有 RAG 能看见“第一次检索没有取全”，却还不能证明应在什么 Observation 下选择哪一种恢复动作，以及该动作是否会在有界成本内新增有效 Document Evidence

## 1. 模块定义与范围判断

M42 已留下 business T4 的真实首次漏选 Observation，M39/M41/M44A 已留下 external retrieval、context packing 与回答失败分层，M44 则提供了顶层 Action、EvidenceDelta、Budget、Progress 和稳定停止 seam。M45 的顺序因此合适：先把这些失败变成可执行、可拒绝、可计费的 action-level Evidence，再允许 M46 建 RAG Subgraph。

本模块围绕一个主要问题形成闭环：**在不接入产品 Loop、不解封 decision reserve 的前提下，用冻结的 diagnostic/dev 场景证明 `query_rewrite_candidate` 与 `context_expansion_candidate` 是否具备进入 B4 allowed action catalog 的资格。** 它不再拆成“先做漏斗、以后再找动作”的两个模块，因为没有同一次 campaign 的 Observation、EvidenceDelta 和预算，单独漏斗不能完成 B3；反过来，直接写动作又会重演 M39 缺少入场证据的问题。

用户完成 M45 后应能：

- 沿 `retrieved → selected → generation-visible → support → cited → answer` 解释失败首先发生在哪一层；
- 展示同一个 external runtime 如何在不同真实 Observation 下分别准入 rewrite 或 context expansion，并排除错误动作；
- 查看每张 action card 的 trigger、Evidence gain、额外调用、延迟、安全边界、duplicate/no-progress 和 stop；
- 明确判断 M46 能否开工，而不是用“Graph 已经能循环”或“一种动作加 stop”冒充 Agentic RAG 已具备。

M45 只有两种合法终局：

1. 两种动作都通过第 8 节 required Gate，且 external runtime 完成两类 Observation-driven 选择，则 B3 完成并允许制定 M46/B4 plan；
2. 任一动作未通过、只能按 runtime 静态分摊，或 campaign 到达冻结边界仍证据不足，则进入 `review_required/no_go`。此时只表示调查按预算结束，**不得宣称 M45/B3 完成，不得运行 `finish-module` 把 B3 标为完成，也不得启动 M46**；必须由用户重新规划 B3 的真实 Scenario/corpus/排期或显式修改阶段最终范围。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| B0 全局 catalog 已有 `stop`、`query_rewrite_candidate`、`context_expansion_candidate`；除 `stop` 外均为 `unproven`，business 不适用 expansion | M45 应验证既有候选，不应另造第三套同义 action；“global/applicable”仍不能冒充“eligible” | `domain_pack/phase4b/b0_contracts.json`、`engine/phase4b/contracts.py::B0ContractBundle.action_views` |
| M42 business T4 在 gold-first、默认 budget 下只选中 `refund_policy_quality`，遗漏 `refund_policy_basic` | 已有非测试陷阱的真实 business recovery 输入，但没有第二动作及 Evidence gain | `eval/reports/m42/m42-business-first-observation.json` |
| M39 将 external dev 分为 retrieval 11、context/packing 13、Composer 10、provider unavailable 2、不可分类 24，并因缺少 action-level Evidence 与可比额外预算判定 `no_go` | 不能从旧单次 Pipeline artifact 推断 rewrite/expansion 有效；M45 必须补的正是 Observation→Action→EvidenceDelta→Budget | `eval/reports/m39-p6-readiness.md`、`docs/state/change-history/phase4.md` 的 M39 条目 |
| M44A semantic Smoke 中 `qst_0420` 存在 multi-document candidate gap；`qst_0431`、`qst_0461` 已命中 gold 但人工复核显示完整性不足 | 同一 external semantic runtime 已有两类可区分的真实诊断输入，可分别检查 rewrite 与 context expansion，而无需触碰 sealed reserve | `eval/reports/m41-rag-external-artifacts/m44a-rag-external-semantic-smoke-20260824-023039.json` 及其 reviewed artifact |
| 对 active external profile 做只读 unit 对账后，`qst_0431` 的两篇 gold 文档与 `qst_0461` 的 gold 文档都各有 2 个 retrieval units；历史 generation-visible anchor 只覆盖其中一个 unit | expansion 场景至少具备真实相邻 unit 结构，不是为了测试临时改 chunk/top-k；是否真正新增有效 Evidence 仍须由 M45 Probe 判断 | active profile `knowledge.sqlite3::units` 只读查询 + 上述 M44A completed artifact |
| Knowledge Tool 当前一次调用只执行一次 adapter retrieval，并在同次 bundle 内完成 ACL 双检、materialize、selected Evidence 与安全投影 | recovery prototype 必须复用授权、Evidence identity 与 loader seam；不能绕开 Tool 直接拼正文或从 gold 构造 Evidence | `engine/rag/knowledge_tool.py::KnowledgeTool.retrieve` |
| external SQLite profile 保存 physical/logical document、unit 与 normalized offset，Milvus 只返回 unit identity | external context expansion 可以从已授权 seed Evidence 出发补相邻 unit，但必须回到 SQLite authority 重水化和重新授权，不能信任向量库正文/metadata | `engine/rag/enterprise_runtime.py`、`engine/rag/enterprise_semantic.py::EnterpriseMilvusSemanticAdapter.retrieve` |
| B2 `BudgetProfile` 生产合同最多一次 Knowledge/retrieval；Controller 对同 requirement 的既有 document Observation 不会再选第二动作 | M45 只能在隔离 diagnostic runtime 证明候选子预算，不能修改 production B2 budget 或宣称产品已会恢复；父子预算接线留给 M46 | `engine/phase4b/loop_contracts.py`、`engine/phase4b/agent_loop.py::_choose_action/_declared_cost` |
| M44 action 安全投影只保留有限 diagnostics，完整 rows/正文/gold 不进入 Action/Context/Trace | B3 artifact 需要可复核 funnel，但仓库投影仍必须安全；大 context 应进项目外 immutable store并由仓库 manifest 对账 | `engine/phase4b/agent_loop.py::_safe_observation`、`docs/phase4b-roadmap.md` §14.5 |
| Phase 4B 60 题 reserve `f70c5fc...e505` 的首次解封 owner 是 M46 | M45 只能使用 business canonical 与已解封 historical/diagnostic dev；任何逐题 reserve 访问都会污染 B4 决策集 | `eval/cases/agent/phase4b_reserve_manifest.json`、`docs/state/rag-current-state.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 首次检索与恢复动作需要分权 | `agentic-rag-for-dummies/project/rag_agent/tools.py::ToolFactory._search_child_chunks/_retrieve_parent_chunks` | child search 与 parent context retrieval 是两个独立 Tool；第二步消费第一步返回的 parent identity | M45 把首次 retrieval 与 recovery action 分成两个 typed Observation；expansion 只能消费本轮已授权 seed Evidence 的 physical document/unit/offset，输出新的 EvidenceRef 与 EvidenceDelta | 字符串 Observation、顺序 parent ID、错误正文直接返回、默认 parent expansion、LLM 自由选择 Tool |
| action 必须由状态和停止条件约束 | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph`、`graph_state.py::AgentState/append_unique`、`nodes.py::_retrieval_contexts/should_compress_context/compress_context` | 条件边、Tool/iteration count、retrieval key/context 去重以及每条回边最终停止 | M45 diagnostic artifact 显式记录 initial Observation、eligible set、chosen/rejected action、duplicate key、子预算、EvidenceDelta 和 stop；M46 才把合格卡接成子图 | `MessagesState` 全历史、强制首搜、开放 rewrite、fallback answer、模型摘要、InMemorySaver 及参考阈值 |
| context expansion 需要真实结构而非“多取几条” | `agentic-rag-for-dummies/project/document_chunker.py::create_chunks_single/__create_child_chunks` | 标题 parent 与 child unit 的层级说明“命中单元”和“回答上下文”可分离 | DataPilot 不改 corpus recipe；只在 external profile 已有 logical/physical document 与 normalized offsets 上原型化有界 neighbor expansion，并由 SQLite authority 回切正文 | 为 22 条短 business 文档强造 parent/child、复制字符参数、用 `<stem>.pdf` 或顺序 ID 作为 Evidence identity |
| 诊断时不能丢 reference identity | `DB-GPT/.../resource/knowledge.py::RetrieverResource.get_resources/_get_references`；对照 `.../tools/knowledge_retrieve.py::make_knowledge_retrieve.knowledge_retrieve` | chunks 与 structured references 同步返回；纯编号正文 Tool 会丢失可验证来源 | M45 funnel 从现有 Evidence ledger 读取 candidate/selected/generation-visible identity；recovery 新增项仍生成 DataPilot EvidenceRef/anchor 并重新授权 | 只取第一个 resource、正文/异常字符串进入 Observation、文档名列表冒充 citation、reference 存在即等于 claim support |
| retrieval 与 answer failure 需要分开解释 | `DB-GPT/.../rag/evaluation/retriever.py::RetrieverMRRMetric/RetrieverHitRateMetric/RetrieverEvaluator`、`answer.py::AnswerRelevancyMetric/LLMAnswerEvaluator` | retrieval 与 answer 使用不同输入和评价器 | M45 scorer 分层报告 candidate/selected/context/support/citation/answer；上游未观察时下游为 `not_observed`，required Gate 不由 LLM Judge替代 | evaluator 为评分重跑 pipeline、空结果一律计零、默认 embedding/阈值、单个 LLM 分数决定 action admission |

定点复核得到的限制：ARAG 只证明 action seam 和 context 层级可实现，DB-GPT 只证明 reference/evaluator 可分层；二者都没有 DataPilot 的 22 条 business、36,417 文档/139,214 units external 规模、ACL 双检、typed Evidence、sealed reserve 或父子预算。动作有效性只能由本模块冻结 campaign 证明。

本模块不修改 corpus/release/index recipe，因此不触发 `WREN-INDEX/WATCH` 或 `DATAAGENT-REPLACE` 的发布实现分支。若实施中必须新增/改写文档、unit recipe、semantic snapshot 或 active pointer，视为范围冲突，停止并重开第 7 节决策门，不能在 M45 内顺手处理。

## 4. 目标、优先级与非目标

### 模块完成状态

M45 完成后，系统拥有一个与产品 runtime 隔离、可复现的 B3 diagnostic runtime：它能从同一次真实 retrieval 的 typed Observation 形成 eligible action set，执行至多一个恢复候选，记录新的 EvidenceDelta 和逐维子预算，并生成 funnel/action card/review artifact。两张 B0 candidate card 都满足 C4 准入，且 external semantic runtime 在不同冻结 Scenario 下分别正确选择 rewrite 与 expansion；M46 可以直接消费这些卡和 budget，不重新用 reserve 调动作。

### 必须完成

- 建立 C1 失败漏斗，将 retrieval、selection、generation context、support、citation、answer 分开，保持 `not_observed` 和首个失败层。
- 建立 C2 diagnostic artifact/closed-world validator，保证 initial Observation、eligible/rejected action、EvidenceDelta、budget、runtime/corpus/ACL identity 同源且不可补跑伪造。
- 在 business T4 与 external `qst_0420` 上验证 `query_rewrite_candidate`；rewrite 输入只来自服务端 Evidence requirement + initial Observation，不读取 gold document key/title/正文。
- 在 external `qst_0431`、`qst_0461` 上验证 `context_expansion_candidate`；expansion 只从已授权 seed Evidence 的 source coordinates 补有界相邻 unit，并逐项重新授权。
- 证明 external runtime 在不同 Observation 下分别准入两种动作：预签名 requirement slot 在首次 selected Evidence 后仍 unsupported 时准入 rewrite、seed context fragment 准入 expansion；错误动作不进入 eligible set，`stop` 始终存在。
- 冻结两张 C4 action card 的 trigger、scope、子预算、ACL/outbound、expected/actual gain、duplicate/no-progress 和 termination；不足两张时按 C5 停门。
- 保持 M46 reserve sealed；历史 M34/M41/M44A 只作 diagnostic/historical 输入，不冒充新默认决策集。

### 建议完成

- 提供一个零 provider 的 deterministic rehearsal，方便用户先演示 eligible/rejected/duplicate/no-progress，再看少量真实 Probe。
- 生成安全失败切片，展示 retrieval gap、context gap、ACL deny、runtime unavailable 和 duplicate stop，而不提交题面、正文或敏感 identity。

### 条件触发

- **触发条件**：现有 safe artifact 缺少构造 C1 funnel 或 C2 initial Observation 所需、但产品运行已实际产生的非敏感 stage identity。
- **允许动作**：additive 扩展 diagnostic/private artifact schema 或同源 projector，并为旧 artifact 保持只读兼容；不得扩大公共 API/Trace 正文投影。
- **未触发时**：复用 M41/M44 现有 ExecutionEvidence、ledger 和 scorer，不新建平行 RAG Eval 平台。

- **触发条件**：某个冻结 Scenario 的 initial Observation 不满足对应 action 的 runtime trigger，或 action 在 C3 预算内没有新增有效 Evidence。
- **允许动作**：把该 action/scenario 如实记为 failed 或 inconclusive并进入 C5 review；只有确定为实现偏离已冻结 card 时，才允许按 runbook 做一次最小修复重验。
- **未触发时**：不得换题、改 query 文案、调 top-k、扩大邻居窗口、切 lexical/semantic、重复抽样或解封 reserve 来追求通过。

- **触发条件**：实现需要模型生成 rewrite、rerank、改 embedding/recipe、发布新 corpus、重建索引或改 active/default runtime。
- **允许动作**：暂停对应分支，按第 7 节 G45-1/G45-2 或新决策门向用户提交 receiver/purpose/data class、identity、成本和可比性方案。
- **未触发时**：M45 全部候选保持 deterministic/local policy；external semantic 仅使用既有 query embedding 产品依赖，零 Composer/decision/rewrite 模型调用。

### 明确非目标

- 不实现、编译或公开 M46 bounded RAG Subgraph；不修改 `agent_loop.py` 让产品自动执行第二个 Knowledge action。
- 不修改 B2 production parent budget、Knowledge runtime resolver、TaskState、API request shape、默认模型、active business release 或 Enterprise semantic 默认。
- 不解封、运行或读取 Phase 4B 60 题 decision reserve；不运行 M34 held-out/all。
- 不把 fixed rerank、hybrid retrieval 或一次性扩大 top-k 包装成 Observation-driven action；若作为 Pipeline control，只能在未来独立候选计划中比较。
- 不解决 Composer prompt/structure/support、citation validator 或答案措辞问题；它们可被 C1 诊断，但不能为 retrieval action 制造 eligibility。
- 不改 external parser/unit recipe，不新增 parent 索引，不建设生产 connector ACL、性能/多 worker、durable state 或 Context Compact。

## 5. 关键合同

### C1：RAG 失败漏斗合同

- 输入：同一次 execution 的 initial retrieval outcome、Evidence ledger、AnswerFlow/Composer/citation 事实、人工 review（若已有）和 resolved runtime identity。
- 成功输出：每个 Scenario 的 `retrieved/candidate → selected → generation_visible → support → cited → answer correctness/completeness` 三态视图，以及唯一首个失败层；support 只是回答诊断，不新增第五个 Evidence stage。
- 失败语义：上游缺失、provider unavailable、artifact identity 不闭合时，下游保持 `not_observed`；不能把无答案统一算 retrieval failure，也不能把 complete/cited 冒充正确完整。
- 必须保持的不变量：scorer 不重跑 pipeline；business/external、lexical/semantic、historical/diagnostic/reserve 分账；gold 只用于离线评分，不能进入 action runtime。
- 本模块不冻结的实现细节：内部 scorer 类名、report 布局和可视化形式。

### C2：Diagnostic Observation 与 artifact 合同

- 输入：预注册 Scenario/runtime、首次 retrieval 的 typed Observation、服务端 Evidence requirement、ACL/purpose 和 C3 campaign budget。
- 成功输出：closed-world execution 记录 initial Observation identity、applicable/eligible/rejected action、chosen action、input/duplicate fingerprint、budget before/consumed/after、actual EvidenceDelta、progress/termination 与安全 runtime identity。
- 失败语义：缺 initial Observation、额外/重复 action、identity 漂移、预算不守恒、从 gold 派生 runtime query、正文/私有 Evidence 进入仓库投影，均拒绝 completed。
- 必须保持的不变量：一条 Scenario 只有一次 initial retrieval 和至多一个 recovery action；`stop` 始终 eligible；Response/Trace/Eval 不为评分重跑另一条 pipeline；repository artifact 不保存正文、raw query/gold、凭据或 Thought。
- 本模块不冻结的实现细节：diagnostic runner 文件结构，以及未来 B4 Subgraph state/edge 布局。

### C3：有界 diagnostic campaign 合同

- 输入：固定 cohort：business T4；external semantic `qst_0420`、`qst_0431`、`qst_0461`。固定候选只有 B0 的 rewrite、expansion 与 stop。
- 成功输出：Round 1 对四个 Scenario 各首次执行一次；每题在 initial Observation 后至多执行一项 eligible recovery action。Round 2 只允许在已确认“实现偏离冻结 card”并完成具体修复后，对受影响最小 Scenario 各重验一次；质量无增益、trigger 不成立或依赖不可用不构成自动重跑理由。
- 失败语义：到达 Round 1/允许的最小重验、任一单动作预算或模块总边界后立即进入 C5 review；不继续找题、调参或换 backend。
- 必须保持的不变量：四个 Scenario 是 `diagnostic/dev`、`exploratory`、`baseline-ineligible`；不运行 Composer generation；external 只使用现有 semantic snapshot，business 只使用 active 22-entry lexical；reserve/held-out 访问为零。
- 本模块收紧预算：4 个 Scenario；每个 initial retrieval 1 次、recovery action 1 次；rewrite action 内至多包含 C4 允许的 2 个 child retrieval batches。模块首次尝试预计真实 provider calls ≤5（仅 external query embedding）、chat/model calls=0、observed chat tokens=0。若实现发现 embedding transport 实际调用数会超过 8，或需新增模型用途，必须先进入 G45-1，不得依赖 standing authorization 扩大。
- 本模块不冻结的实现细节：运行命令、run ID 与并行度；它们在 notes 开工清单中按 runbook 登记。

### C4：Recovery action card 与准入合同

- 输入：runtime/corpus、ACL/purpose、initial Observation、剩余子预算和本轮已执行 action/Evidence identity。
- 成功输出：
  - `query_rewrite_candidate`：仅当首次 retrieval 后仍有**预检索已冻结的 typed requirement slot**未被 selected Evidence 支撑时 applicable；slot 来自服务端 requirement 分解，不能来自 gold document key/title 或运行后人工 verdict。动作采用 deterministic requirement split/focused rewrite，最多 2 个子问题、2 个额外 retrieval batches、每批最多 5 candidates，合并后最多 5 个 unique candidates/3 个 selected Evidence；model/Composer calls=0。至少在 business T4 与 external `qst_0420` 各新增一个原缺失且通过 ACL 的 EvidenceRef。
  - `context_expansion_candidate`：仅 external；必须已有相关且已授权 seed Evidence，并由 unit coordinates 证明上下文是可扩展 fragment；最多消费 2 个 seed Evidence，每个至多补前/后各 1 个相邻 unit，新增最多 4 个 unique EvidenceRef，query embedding/retrieval/model calls=0。至少在 `qst_0431`、`qst_0461` 各新增与 unresolved requirement 相关且通过 ACL 的 EvidenceRef。
  - 两者都记录 expected/actual EvidenceDelta、latency、candidate/selected/context consumption、duplicate/no-progress 和 stop。
- 失败语义：无 seed Evidence 时 expansion 不适用；所有 typed requirement slot 已由 selected Evidence 支撑时 rewrite 不因“也许有帮助”自动适用；ACL/identity/runtime unavailable、duplicate、无新 Evidence 或预算耗尽均停止，不能 fallback 到另一 corpus/backend。
- 必须保持的不变量：requirement slot 在首次 retrieval 前签名并进入 Observation 对账；runtime trigger 不读取 gold、人工 verdict 或答案文本；rewrite 不使用 document key/title 作为隐藏 oracle；expansion 从 SQLite authority 重水化并重新授权；Progress 只看 Evidence gain，不成为 Answer Gate。
- 本模块不冻结的实现细节：rewrite 文案模板、neighbor loader/helper 名称和 B4 action node 类名；实现可以在不改变上述输入、预算和准入语义的前提下保持深模块。

### C5：B3 review point 与 M46 开工门合同

- 输入：两张 completed C4 card、C3 完整预算账、external 同 runtime 选择证据、错误动作排除和安全/identity Gate。
- 成功输出：只有两张 action card 全部 required 通过，且 external semantic runtime 在 `qst_0420` 选择 rewrite、在 `qst_0431/qst_0461` 选择 expansion，才输出 `go_for_M46`。
- 失败语义：零/一种动作合格、动作只按 corpus 静态分摊、trigger 依赖 gold/答案、Evidence gain 不稳定、unsafe/duplicate/no-progress 未闭合或 campaign 越界，输出 `review_required/no_go`。
- 必须保持的不变量：`no_go` 不改写 M39 为错误，也不等于 B3/B4 完成；不允许用一种动作+stop、business 固定 A/external 固定 B 或调低验收标准替代 roadmap 最终目标。
- 本模块不冻结的实现细节：若 no-go 后用户选择新 Scenario/corpus，必须另行修订/替换 M45 plan；不会预留模糊的“以后优化”。

## 6. 工作切片与执行顺序

### M45-A：campaign manifest、漏斗和 diagnostic artifact 骨架

- 优先级：必须完成
- 依赖：M42 business Observation、M39/M41/M44A historical/dev artifact、M44 typed Action/Budget/EvidenceDelta seam、C1–C3。
- 实施内容：冻结四个 Scenario、两张候选卡、Round/budget/runtime identity；建立 C1 funnel projector、C2 artifact/validator 和安全 manifest；只读导入历史 initial Evidence，不执行 candidate。
- 关键合同：C1、C2、C3。
- 交付物：campaign manifest、funnel taxonomy、diagnostic artifact schema/validator、历史输入 SHA-256 对账和 deterministic fixtures。
- 验证方式：artifact closed-world/tamper tests；retrieval/context/provider/Composer/citation 分层样例；reserve/held-out ID 进入 selector 时失败关闭。
- Live Probe checkpoint：不适用；本切片只做离线投影和 deterministic tests。完成后才允许实现候选。
- 完成门：能在零外部调用下重建四个 initial failure view；缺/多/重复 action、身份或预算漂移均不能完成 artifact。

### M45-B：deterministic query rewrite diagnostic action

- 优先级：必须完成
- 依赖：M45-A、C4 rewrite card、既有 Knowledge Tool/semantic adapter/ACL seam。
- 实施内容：实现隔离 diagnostic executor；从预签名 typed requirement slots + initial unsupported-slot Observation 生成最多两个 focused subquestions，逐批复用同一 runtime、ACL、Evidence construction，合并/去重后计算 EvidenceDelta；不接产品 Loop。
- 关键合同：C2–C4。
- 交付物：rewrite action prototype、trigger/错误动作排除/duplicate/no-progress tests、business/external fixtures。
- 验证方式：正常增益、无 Observation、无 coverage gap、gold/title 注入、ACL deny、runtime unavailable、重复 query/Evidence、超子预算测试。
- Live Probe checkpoint：`M45-P1` after M45-B / before M45-C，先执行 business T4；结果为 `continue` 才允许把 rewrite card带入 external 候选验证和实现 expansion。
- 完成门：deterministic Gate 通过；P1 已按时形成三态与 `continue/revise/stop`，无未处理 revise。

### M45-C：external context expansion diagnostic action

- 优先级：必须完成
- 依赖：M45-B/P1 continue、C4 expansion card、external profile coordinates/context loader。
- 实施内容：从已授权 seed Evidence 获取 physical document/unit/normalized offsets，在同一 authority 中有界补相邻 unit；每个新增 unit 重新 pre-generation authorization 并形成独立 EvidenceRef；无结构 seed 时不适用。
- 关键合同：C2–C4。
- 交付物：expansion action prototype、neighbor/identity/ACL/duplicate/budget tests、external fixtures。
- 验证方式：前后邻居、文档边界、跨 physical document 禁止、identity 漂移、revoked ACL、重复 unit、空/不可扩 seed、预算耗尽测试。
- Live Probe checkpoint：`M45-P2` after M45-C / before M45-D，先在 external `qst_0420` 验证同 runtime 的 rewrite trigger；其 `continue` 才允许进入 expansion 实景。随后 `M45-P3` 在 `qst_0431/qst_0461` 验证 expansion，并阻塞 M45-D review。
- 完成门：P2/P3 都已按时形成三态和处置；同一 external runtime 的两类 Observation、错误动作排除和 stop 均有同源证据。

### M45-D：action qualification、review point 与 B4 handoff

- 优先级：必须完成
- 依赖：M45-A～C、全部 Probe 处置闭合、C5。
- 实施内容：汇总两张 action card 的实际 gain/cost、安全与停止；生成 machine-readable qualification、funnel/action 报告、项目外 artifact manifest 和仓库安全失败切片；执行 C5 go/no-go。
- 关键合同：C1–C5。
- 交付物：两张 completed/failed action card、campaign budget/review report、artifact SHA-256/retention manifest、M46 handoff 或正式 no-go。
- 验证方式：closed-world qualification tests；删除任一 trigger/gain/budget/negative assertion 后不得 `go_for_M46`；检查 M46 reserve 访问状态仍 sealed。
- Live Probe checkpoint：无新增 Probe；本切片只消费 P1–P3 已形成的真实证据，不在收工阶段补跑。
- 完成门：只有 `go_for_M46` 才能完成 M45/B3 技术收工；`review_required/no_go` 必须停在用户 review，不得标模块完成。

## 7. 决策门

### G45-1：rewrite 是否引入模型用途

**已确认决策（2026-08-25）**：采用方案 A。M45 首轮只实现 deterministic requirement split/focused rewrite；方案 B 不属于本模块默认实现或失败后的备用重跑路径，只按下述重开条件进入未来独立 module plan。

#### 方案 A：deterministic requirement split/focused rewrite（已选）

- 做法：只消费首次 retrieval 前已签名的 typed requirement slots 和 initial unsupported-slot Observation，以 closed-world 规则生成至多两个子问题；不调用 decision/rewrite LLM。
- 影响：可在当前 standing Probe 预算内验证 action seam，outbound 仍为 `none_by_default`，失败可归因。
- 适用条件：business T4 与 external `qst_0420` 能由通用 requirement slots 表达，不需要文档 key/title 或题目专用字符串。
- 风险：开放措辞覆盖有限；若只靠硬编码 canonical 问句才能成功，C4 必须判失败而不是继续扩规则。

#### 方案 B：结构化模型 rewrite proposal（未选，保留为条件候选）

- 做法：模型只提出 closed-world 子问题，再由确定性 validator 审核；需新增 receiver/purpose/data class/字段、outbound policy、model/token 子预算和真实 E2E。
- 影响：可能提高语言泛化，但扩大出站、调用与失败面，并会让本轮 action gain 混入模型变量。
- 适用条件：方案 A 在多个已冻结 dev paraphrase 上形成稳定失败簇，且失败明确来自 requirement 表达而非 retrieval/corpus。
- 风险：污染单变量 campaign；provider 不稳定可能让 B3 无法判断 action 本身。

#### 建议与确认时点

- 决策理由：B0 已冻结 `outbound=none_by_default`，当前问题是证明 Observation-driven Evidence gain，不是先比较 rewrite 模型。
- 当前允许推进：M45-A 离线漏斗、artifact 骨架、deterministic prototype/tests，以及本 plan 冻结的 P1–P3。
- 当前禁止推进：任何 rewrite/decision 模型调用、新 outbound policy 或模型 rewrite 真实 provider E2E。
- 后续确认时点：只有满足重开条件并另立 module plan 后，才单独确认 receiver/purpose/数据字段和额度。
- 重开决策的条件：A 在非 canonical、已冻结 dev paraphrase 上形成稳定且不可接受的 understanding/rewrite failure cluster，而 retrieval action seam本身已证明可行。

### G45-2：B3 大 artifact 保存位置

**已确认决策（2026-08-25）**：采用方案 A。长期完整诊断 artifact 放入与 sealed reserve 物理分离的 versioned 项目外目录；仓库只保存安全投影、identity、SHA-256 与汇总。具体绝对路径在首次长期写入前登记到开工 notes 并核对不位于 reserve store 内，这只是执行落点确认，不再重开 A/B 选择。

#### 方案 A：独立 external diagnostic store（已选）

- 做法：使用与 sealed reserve 分离的新 versioned 项目外目录保存含 context/逐题 action 的 immutable artifact；仓库只提交 identity、SHA-256、汇总和安全失败切片。
- 影响：避免 B3 诊断材料与 M46 reserve 混放或误访问，保留真实 context 可复核性。
- 适用条件：用户允许在项目外 dataset 根下创建明确的新诊断目录。
- 风险：新增外部路径和保留/清理责任；实施时需要写入授权。

#### 方案 B：仓库内仅保存裁剪后的安全 artifact（未选）

- 做法：不建立项目外存储，只提交不含正文的逐题 Evidence/action 投影。
- 影响：迁移简单，但 context expansion 的真实相邻内容和人工复核可能无法重建。
- 适用条件：M45-A 证明所有 required Gate 都能只靠 coordinates/hash 完整复核。
- 风险：为省存储丢掉 B4 需要的可审计证据，或让 `.agent_work/temp/` 成为唯一事实源。

#### 建议与确认时点

- 决策理由：M46 reserve 必须继续 sealed，B3 context/action artifact 又需要比仓库安全投影更强的复核材料。
- 当前允许推进：仓库内 schema/tests、`.agent_work/temp/` 一次性 prototype；核对具体项目外落点后，可创建并写入独立 diagnostic store，但不能把 temp 当长期交付物。
- 当前禁止推进：修改或读取 reserve store/访问账本，或把诊断 artifact 写入 `phase4b-agent-eval/v1.0.0`。
- 路径核对时点：M45-A 首次落盘长期 artifact 前，在开工 notes 登记绝对路径、版本、与 reserve 的分离断言及写入授权结果。
- 重开决策的条件：安全投影已足以闭合全部 required review，或外部保留策略无法满足访问/清理要求。

除 G45-1/G45-2 外，本模块无默认模型、embedding、release、active runtime、正式 case 或安全策略决策。C5 的 `go_for_M46/review_required` 是按冻结证据推导的 review point，不授权 M46 默认切换。

## 8. 验证与验收矩阵

### Live Dev Probe（开发期真实探针）

本模块修改真实 business RAG、Enterprise semantic/Milvus diagnostic 行为，并以 action gain 作为后续路线依据，pytest/fake 不能替代真实 Probe。standing authorization、计数、禁区、重验和 Formal Eval 分账统一引用 `docs/state/runbook.md`「Live Dev Probe」；本节只冻结场景、时点和更严格边界。

| Probe ID / 执行时点 | 探针场景 | 真实产品链路/依赖 | 需要观察的结果与 Trace 事实 | 通过/失败/不确定标准 | 决策与停止条件 |
| --- | --- | --- | --- | --- | --- |
| `M45-P1` / after M45-B、before M45-C | business T4：“如果最近质量问题退款明显增多，客服受理这类退款时可以直接按全额退款处理吗？需要哪些前提和材料？” | active 22-entry release → trusted `ops+customer_service` caller → Knowledge Tool initial lexical → diagnostic rewrite action；零模型 | initial 仍复现缺 basic/已有 quality 或如实记录当前 identity变化；rewrite 由 requirement/Observation 触发；新增 basic Evidence 且 quality 不丢；ACL 双检、EvidenceRef、budget、wrong expansion rejected、stop；零 gold/title runtime input | passed：缺失 Evidence 新增且所有安全/预算负断言通过；failed：trigger/增益/安全/身份确定失败；inconclusive：依赖/active identity 无法形成有效观察 | passed→continue M45-C；实现缺陷→revise 后最小重验一次；case 已自然取全或无恢复需要→inconclusive/stop，不能制造 failure，进入 C5 review |
| `M45-P2` / after M45-C、before P3 | external `diagnostic_dev/qst_0420` | existing semantic profile/Milvus → SQLite authority → initial retrieval → diagnostic rewrite；不运行 Composer | 预检索已签名的多部分 requirement slot 中至少一项在 initial selected Evidence 后仍 unsupported；rewrite eligible、expansion rejected；新增缺失 Document Evidence；semantic/profile/unit-set identity、embedding calls、ACL、EvidenceDelta、duplicate/no-progress、子预算；gold 只在动作后离线评分 | 三态同 P1；passed 还要求新增 Evidence 来自当前 authority/ACL，且 trigger/query 不是 gold/title 驱动 | continue 才执行 P3；systemic identity/readiness failure立即 stop；不切 lexical、不换题、不自动重跑 |
| `M45-P3` / after P2 continue、before M45-D | external `diagnostic_dev/qst_0431`、`qst_0461` 各首次一次 | existing semantic profile/Milvus initial retrieval → authorized seed Evidence → SQLite neighbor load/reauthorize；零额外 embedding/Composer | 两题均形成 fragment Observation；expansion eligible、rewrite rejected；每题新增有效相邻 Evidence；跨文档禁止、ACL/revision、EvidenceDelta、duplicate/no-progress、unit/context预算与 stop | passed：两题 required 均通过；任一确定失败则整体 failed；seed structure/依赖不可观察则对应 inconclusive且整体不得准入 action | 两题均 passed 才把 expansion card交 M45-D；否则进入 revise或 C5 no-go，不扩大窗口/换题 |

Probe 业务 oracle 与安全负断言：

- P1 只判断两篇已冻结政策的 Evidence coverage、authority/revision/ACL，不运行 Composer，因此不声称最终自然语言答案正确；
- P2/P3 的 gold 只在 action 完成后离线评分 actual EvidenceDelta，不进入 runtime trigger/query；
- 全部 Probe 禁止 Document 正文、raw query/gold、凭据、Prompt、Thought 进入 API/Trace/仓库 artifact；
- 只读运行，不 reset、不写数据库/active release/索引；运行前后核对 release/profile/semantic/collection/unit-set/reserve access state 未变化；
- 初次 campaign 最多 4 个 Scenario，external 每题 initial 1 次、recovery action 1 次；rewrite 内最多 2 个 child retrieval batches，因此预计 embedding provider attempts≤5、chat/model/Composer=0；任何意外越界如实记账并停止。

模块完成后建议用户执行的 Formal Eval：**当前无需正式 Eval**。M45 只负责 diagnostic/dev action admission，不能解封 reserve；M46 完成 Subgraph 后才按其 plan 首次运行 sealed decision reserve Pipeline/Subgraph A/B。历史 M34/M41/M44A 仅作回归/诊断，不自动重跑。

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 failure funnel | scorer/projector tests + M39/M41/M44A frozen artifact replay | 六层三态和唯一首失败层正确；上游缺失传递 `not_observed`；不重跑 pipeline | 必须完成 |
| C2 diagnostic artifact | completed artifact + 缺/多/重复 execution/action/assertion、identity/hash/budget 篡改 | 合法 artifact identity 可复算；所有 closed-world 反例失败关闭；仓库投影无正文/gold/private payload | 必须完成 |
| C3 campaign boundary | selector/manifest/round/budget tests + notes/usage audit | 只有四个 Scenario；Round/重验符合合同；reserve/held-out访问为零；未换 backend/参数 | 必须完成 |
| C4 rewrite card | deterministic tests + P1/P2 | business/external 各有实际 Evidence gain；external 错误 expansion 被拒；ACL/duplicate/no-progress/budget闭合 | 必须完成 |
| C4 expansion card | deterministic tests + P3 | 两个 external Scenario 各新增有效相邻 Evidence；错误 rewrite、跨文档、ACL/identity/duplicate被拒 | 必须完成 |
| C5 same-runtime choice | qualification validator | external semantic 在不同 Observation 分别选择 rewrite/expansion；移除 Observation 后同一选择不再合法 | 必须完成 |
| C5 M46 gate | go/no-go projector + tamper tests | 只有两卡全通过才输出 `go_for_M46`；零/一卡/静态分摊只能 `review_required/no_go` | 必须完成 |
| legacy/默认不变 | M31–M44A RAG/Harness/Phase4B 回归 | legacy/agent 原 assertion 不改；B2 production budget/Loop、active release、semantic默认和API不变 | 必须完成 |

聚焦测试顺序：C1 funnel → C2 artifact/identity → rewrite → expansion → qualification/no-go → reserve-seal/compatibility。

全量回归范围：M31–M34 Knowledge/Evidence/Answer、M35–M40 Harness/Hybrid/assurance、M41 RAG Eval、M42 reserve/B0、M43 task、M44A semantic product runtime、M44 Loop/Scenario v3，以及全仓 deterministic pytest。预计超过 2 分钟的完整回归按 `AGENTS.md` 后台规则执行。

不可外推结论：四个 dev Probe 不能证明总体 RAG 质量、稳定净收益、默认切换、真实企业 corpus、吞吐或 Reliability；Evidence gain 也不等于最终 answer correctness。M45 不运行真实 Composer、decision/rewrite LLM、Text2SQL/MySQL、held-out/reserve、LangFuse Cloud 或人工产品演示。

历史 artifact 只读边界：M34/M39/M41/M42/M44A completed artifact 不补字段、不改签、不覆盖；新 C2 artifact通过引用 identity/SHA-256关联历史 initial Evidence。任何为评分补执行都必须成为本 campaign 的新 execution，而不能伪装成旧 run 原本存在。

## 9. 依赖与交付物

### 依赖

- 已完成 M42/B0、M43/B1、M44/B2，以及 M44A semantic产品 runtime；M44 defect repair 不改变 M45 路线。
- `docs/state/runbook.md`、`runbook-rag.md`、`rag-current-state.md`、`eval-baselines.md` 的运行、身份、Eval 和 reserve 边界。
- M42 business first Observation、M39 readiness audit、M41/M44A external completed artifact/review。
- Knowledge Tool ACL/Evidence/loader、external SQLite authority + Milvus unit selection、B2 Action/Budget/EvidenceDelta/Progress typed seam。
- G45-1/G45-2 均已确认采用方案 A；首次长期写入前完成 external diagnostic store 具体绝对路径核对；external Probe 时 Milvus/profile/embedding readiness 可用。

### 交付物

- versioned B3 diagnostic campaign/action card contract 与 identity manifest；
- RAG funnel projector/scorer、安全 triage 和 historical input hash manifest；
- rewrite/expansion 隔离 diagnostic executor，不接产品 Loop；
- closed-world diagnostic artifact、qualification validator 与 deterministic rehearsal；
- 四个预注册 Scenario 的 Probe/usage/EvidenceDelta/action selection 证据；
- 项目外 immutable diagnostic artifact 与仓库内 SHA-256/汇总/安全失败切片；
- `go_for_M46` handoff 或正式 `review_required/no_go`，以及对应 notes/state/changelog 技术档案。

只冻结这些交付物的职责，不提前固定文件名、类名、Graph node、report UI 或 M46 Subgraph 拓扑。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：B4 Subgraph 实现/default/fallback、sealed reserve A/B、最终 Answer/Citation 净收益、B5 durable state、B6 Compact。
- 下一模块可直接消费的产物：M46/B4 只在 C5 `go_for_M46` 后消费两张 action card、trigger/eligible set、child budget、Evidence merge/duplicate/no-progress、diagnostic artifact与 reserve protocol；不得重新用 reserve 调 action/Prompt/参数。
- 后续需要根据真实失败重新规划的内容：若 C5 no-go，用户必须在 M45/B3 内明确选择新的真实 Scenario/corpus、排期或阶段范围修订；在新 plan 通过前没有合法的 M46 开工条件。
- 可能存在的风险：deterministic rewrite 过拟合 T4；external review failure 不一定可由 neighbor expansion 解释；现有 unit recipe 无天然 parent；semantic runtime readiness/延迟波动；安全投影不足以复核 context。对应控制是非 canonical external case、typed trigger、不新增 parent 假设、三态/usage、独立 immutable artifact。
- 最终目标与缺口：M45 只完成 action admission，尚无产品 RAG Subgraph；Phase 4B 的最终 B4 标准仍要求 M46 实现同合同 Pipeline/Subgraph、父子预算、business T4、sealed reserve A/B 和 default/experimental/fallback 决策。M45 不得把 action prototype 写成 Agentic RAG 已完成。
- 强制开工条件：M46 必须取得 C5 `go_for_M46`、两卡 required 全绿、同 external runtime 两动作选择证据、M45 技术收工/文档/人工检查/验收完成且 reserve access state 仍 sealed。
- 最终验收标准：B3 以第 8 节全部必须项与 P1–P3 时点证据闭合为准；B4/Phase 4B 仍分别以 M46 plan 和 roadmap Definition of Done 为准。

## 11. 开工条件

- 开工前无需确认：M45 对应完整 B3；复用 B0 两张 unproven candidate；四个已解封 diagnostic/dev Scenario；M46 reserve继续 sealed；产品 B2 Loop/budget、active release、semantic默认、模型/embedding不变；不实现 Subgraph。这些由 roadmap/state/既有确认决定。
- 已确认决策：G45-1、G45-2 均采用方案 A；M45 不启用模型 rewrite，完整长期 artifact 使用独立 external diagnostic store。首次长期写入前仍须在开工 notes 核对并登记具体绝对路径、版本和与 reserve 的物理分离，不再重开方案选择。
- Live Probe：plan 确认后，P1–P3 在本节冻结范围内引用 runbook standing authorization；不另行解读为 Formal Eval、held-out/reserve、模型 rewrite 或默认切换授权。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得通过换题、调低标准、改 corpus/default、解封 reserve或把 no-go 说成完成来继续施工。
