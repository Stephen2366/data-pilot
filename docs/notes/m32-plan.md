# M32 确定性知识取证与 Knowledge Tool 开发计划

> 状态：已确认可执行（G-M32 = 方案 A）
>
> 能力里程碑：Phase 4 **P2「确定性 RAG 垂直切片」的第一个能力切片**；M32 只闭环 active Knowledge release 到授权 Document Evidence 的确定性取证，不代表 P2 已整体完成
>
> 主要问题：系统已有可信知识发布和 Evidence 安全地基，但还不能把一个问题稳定、授权、可归因地转换成 Knowledge Tool 的 Document Evidence

## 1. 模块定义与范围判断

M31 已把 11 条知识发布为 active release，并建立 trusted caller、ACL 双检、typed Evidence、citation validator 和默认拒绝 outbound seam。当前缺口不再是“知识从哪里来”，而是“怎样从 active release 中安全找到本轮真正需要的知识，并把检索成功、无候选、无权限和后端不可用分开表达”。

P2 若一次性塞入检索、Knowledge Tool、Evidence Gate、Composer、citation 用户视图和 `/api/query`，会同时调试取证正确性、答案充分性、生成行为和公开兼容投影。任何失败都难以判断是没召回、没选中、没入模还是生成错误，不利于学习和验收。

因此推荐把 M32 冻结为一个可独立验收的“安全取证子闭环”：

1. 从 `load_active_release()` 读取唯一运行时知识快照；
2. 在未授权正文进入 retriever 前完成 pre-selection ACL；
3. 通过可替换 adapter 做本地确定性候选检索、排序和去重；
4. 生成 Document Evidence，完成 candidate → selected 账本，并在返回前完成 pre-generation ACL 复核；
5. 以结构化 `RetrievalOutcome` 返回 Evidence、稳定 reason code 和安全 diagnostics；
6. 建立独立 retrieval-only baseline 与 Phase 4 RAG contract Eval。

用户完成本模块后，可以沿调用顺序演示“同一个问题怎样经过 active release、ACL、retriever、Evidence ledger 变成可供回答链消费的证据”，并能用测试明确区分召回成功、知识缺失、授权后无可见证据、revision/发布异常和 retriever 不可用。M32 不生成最终答案，因此不能宣称 RAG API 或 citation 回答闭环已经完成。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| 11-entry immutable release 已 active，调用者可通过窄接口取得完整、校验后的 `ReleaseBundle.entries` | 已有可靠 corpus 快照，但没有消费它的检索层；新代码若重读 Markdown、legacy 表或 release 文件布局会制造旁路 | `engine/rag/release.py::load_active_release`、`domain_pack/kb_releases/active.json` |
| 文档 ACL 已支持 trusted caller、purpose、revision 的 pre-selection / pre-generation 双检，拒绝投影不泄露文档身份 | 目前只有 fixture 直接调用；还没有保证“先过滤再检索、选中后再复核”的 Knowledge Tool 控制流 | `engine/governance.py::authorize_document`、`tests/test_m31_governance.py` |
| `make_document_evidence()` 只能用 active entry 和成功的 pre-selection decision 构造候选；`EvidenceLedger` 支持 candidate → selected → generation-visible → cited 单步迁移 | 当前没有模块负责从检索命中构造候选并推进到 selected；若 M32 提前标记 generation-visible，会把“准备给生成器”误写成“生成器已真实看见” | `engine/rag/evidence.py` |
| citation validator、slot 和 generation-visible 约束已存在 | M32 可以保持后续接口兼容，但没有 Composer 时不应分配 claim slot 或验证最终 citation | `engine/rag/evidence.py::allocate_citation_slot / validate_citations` |
| `/api/query` 的实际控制流仍全部进入 Text2SQL；`AgentResponse` 仍是旧 SQL 主导投影 | 直接接公开 API 会同时触发四轴状态、兼容响应、answer/citation 和 Trace 迁移，扩大本模块主要问题 | `app/api/query.py`、`app/schemas/agent.py` |
| `phase4-v1` 当前只有 8 个 contract/security Scenario、12 个 required assertion | 它证明 P1 合同，不证明 retrieval；原地改写既有 closed-world Scenario 集会让 M31 最终 artifact 的含义漂移 | `eval/phase4_contracts.py`、`docs/state/AI_CONTEXT.md` |
| 当前没有 Knowledge retrieval 真实或长期 baseline；M27 v3 只服务 Text2SQL 且必须只读 | M32 需要新建 RAG retrieval contract/runtime identity，不能拿旧 Text2SQL 分数或 schema retrieval benchmark 代替 | `docs/state/eval-baselines.md`、`docs/phase4-roadmap.md` 第 4.6/8 节 |
| 新 Knowledge/RAG 远端用途继续默认拒绝，默认检索仍是本地 deterministic | 首个 adapter 必须离线可复现；不能顺手接 Qwen/DashScope/Milvus、rerank 或 Cloud | `docs/state/AI_CONTEXT.md`、`engine/governance.py`、`docs/state/runbook.md` |
| 当前 corpus 是短政策和指标说明，没有长文碎片化失败证据 | 没有理由在 M32 引入 chunk/parent-child、query rewrite 或多轮取证 | `domain_pack/kb_docs/`、`docs/phase4-roadmap.md` 第 14.1 节 |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| Knowledge Tool 应返回正文字符串还是结构化取证结果 | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py :: RetrieverResource.get_resources / _get_references`；`DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py :: make_knowledge_retrieve.knowledge_retrieve` | Resource 路径能把 chunk、ID、score、retriever 与 reference 一起返回；与新 Tool 只返回编号正文/错误文本形成直接对照 | Tool 返回 typed `RetrievalOutcome`、Document Evidence、ledger 和安全 diagnostics reference，正文只存在于内部 Evidence payload | 不返回纯文本 Observation；不把异常字符串放进模型上下文；不只用 `knowledge_resources[0]`；不把文件名、score 或 retriever 名当 citation |
| 候选检索与上下文扩展是否应是一件事 | `agentic-rag-for-dummies/project/rag_agent/tools.py :: ToolFactory._search_child_chunks / _retrieve_parent_chunks` | 候选搜索与按 parent 补上下文是两个独立动作，说明 retrieval seam 不必绑定一种上下文扩展 | M32 只实现短知识单元的候选检索 adapter；返回稳定 entry identity，未来若出现碎片化失败簇可在同 seam 后加入单步扩展 | 不继承其字符 chunk、顺序 parent ID、固定阈值、字符串错误、parent/child 默认和 Agent 自主多次调用 |
| 怎样证明评分使用的是本轮真实检索结果 | `agentic-rag-for-dummies/project/rag_agent/nodes.py :: _retrieval_contexts`；`notebooks/evaluation.ipynb :: query_rag / assert_saved_outputs_match_dataset / score_answer` | 保存 Tool 实际返回 context，去重后随运行结果固化，再对已保存输出评分 | M32 把同一次 Tool 调用的候选/选中 EvidenceRef、adapter/runtime/release identity 固化到同一 ExecutionEvidence；scorer 只读该证据 | 不以字符串 context 为事实源；不引入 Graph/history compact；不让 pipeline error 从平均分中静默消失；不在评分时重跑 Tool |
| retrieval 指标与端到端答案是否应分开 | `DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/retriever.py :: RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator` | Hit Rate、MRR 等检索视图可以独立于答案 evaluator | M32 只建立 gold Evidence 覆盖、最终选择覆盖和排序等 retrieval-only 视图；required 合同与 advisory 趋势分开 | 不继承大型 DAG/operator 框架；不把空结果统一记 0 后丢失 `not_observed`；不使用正文字符串完全相等作为唯一 gold identity |
| 为什么不能在最终阶段再拼 `sources` | `GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py :: local_search / _collect_sources / finalize` | 作为反例证明：多后端级联和从多个 metadata 字段猜 source，会让检索身份与最终 sources 断裂 | 从 active entry 开始就携带 document/revision/content/anchor identity；M32 的 EvidenceRef 可被下一模块直接用于 citation | 不照搬 PostgreSQL→Milvus 级联、模型 Router、fallback 答案、末尾 sources 去重或 Tool 内生成最终答案 |

以上源码只证明局部 interface、context 和 evaluator 设计，不提供 DataPilot 所需的 ACL、outbound、四阶段 Evidence、closed-world Eval 或最终 citation 语义；这些继续以现有项目合同为准。

## 4. 目标、优先级与非目标

### 模块完成状态

固定 active release 和 deterministic adapter 下，授权 caller 提交知识问题后，Knowledge Tool 能返回顺序稳定、去重、带完整 identity 的 selected Document Evidence；无候选、授权后无可见证据、release/revision 异常和 retriever 不可用具有不同内部 reason 与统一安全投影。整个过程不联网、不生成答案、不泄露未授权文档，并由独立 RAG retrieval Eval 和 required contract/security case 验证。

### 必须完成

- 建立 Knowledge Tool 的请求、`RetrievalOutcome`、失败 reason、diagnostics 和 adapter 窄接口。
- 只从 `load_active_release()` 消费当前 release，不读取 authority Markdown、legacy `knowledge_docs` 或 release 文件布局。
- 实现本地 deterministic、可替换的 retrieval baseline；固定输入下结果和排序可复现。
- pre-selection 前置过滤、选中后 pre-generation 复核；未授权 entry 不进入 adapter 输入、Evidence、diagnostics、Trace fixture 或公开错误。
- 构造 Document Evidence，并如实记录 candidate → selected；不提前推进 generation-visible/cited。
- 区分 `no_candidate`、安全收敛后的无可见证据、`stale_revision`/active release 不可用和 `retrieval_unavailable`。
- 建立新的版本化 Phase 4 RAG retrieval contract family；同一 Scenario 只执行一次，多条 typed assertion 共享同一 ExecutionEvidence，并做 closed-world 完整性校验。
- 保持 M31 `phase4-v1`、M27 v3、历史 artifact/report 只读，保持 Text2SQL 默认行为和全仓回归。

### 建议完成

- 为 adapter 输出保留可选稳定 score/rank 诊断，但不让 score 成为 Evidence 或授权事实。
- 记录 release/corpus/adapter/recipe/runtime identity、调用次数、候选/选择数量、查询安全 fingerprint 和本地延迟，供下一模块 Trace/Eval 复用。
- 为 diagnostic/dev 与 required contract/security Scenario 建显式用途；若准备检索策略候选，再在调参前单独冻结 held-out decision 集。

### 条件触发

- **触发条件**：本地 baseline 在已冻结 diagnostic/dev Scenario 上出现可复现的“gold 属于已授权 active corpus，但候选覆盖或最终选择持续失败”，且问题不能归因于 corpus、ACL、gold 或实现 bug。
- **允许动作**：只记录失败簇、候选增强假设和未来单变量实验计划；必要时预留 adapter capability 字段。
- **未触发时**：不实现 parent/child、hybrid retrieval、rerank、query rewrite、远程 embedding、向量库或 RAG Subgraph。

### 明确非目标

- Shared Answer Evidence Gate、Answer Composer、claim 生成、citation slot/validator 的最终回答闭环。
- `/api/query`、`AgentResponse`、`docs_used`、公开四轴状态和用户可见 citations 迁移。
- Router、LangGraph、Text2SQL Tool 接入、Hybrid、thread、Loop 或 Context Builder。
- 真实 LLM、远程 embedding/rerank/judge、Milvus、LangFuse Cloud 或新的 outbound 放行。
- 长文/PDF ingestion、chunk/parent-child、在线增量索引和多实例发布。
- 生产 JWT/OAuth 或把请求体 `user_role` 升级成可信文档身份。

## 5. 关键合同

### C1：Knowledge Tool 取证合同

- 输入：非空问题、明确标注来源的 `TrustedCaller`、证据用途/需求、run identity、有限检索预算，以及可注入的 active release loader 与 retrieval adapter。
- 成功输出：不可变 `RetrievalOutcome`，包含 execution outcome、稳定 reason code、selected Document Evidence、截至 selected 的 Evidence ledger，以及不含未授权正文/身份的 diagnostics reference。
- 失败语义：正常无候选是已观察的 `no_candidate`；安全收敛后的无可用证据不得暴露被拒文档是否存在；active release/revision 异常与 adapter 技术失败分别表达，不伪装成政策不存在或 safety blocked。编程错误/合同非法输入可失败关闭，不能吞成普通零结果。
- 必须保持的不变量：Tool 只负责取证；不生成最终答案、不决定最终 `answer_status`、不分配 claim/citation、不调用 SQL；一次 Tool 调用只执行一次 adapter。
- 本模块不冻结的实现细节：具体类名/文件名、默认数量阈值、score 公式和未来异步/远程 adapter 形态。

### C2：可替换 Retrieval Adapter 合同

- 输入：已通过 pre-selection 的 active release entries、规范化查询/已确认条件、有限预算和只读 runtime context。
- 成功输出：按稳定规则排序且 identity 唯一的 match records；每条只能引用本次输入集合中的 document key/revision/content/anchor，并可带可解释的 rank/score 诊断。
- 失败语义：零命中返回空 match 集；adapter 不可用返回结构化技术失败；未知 entry、重复 identity、越预算、非有限 score 或顺序不稳定视为合同错误。
- 必须保持的不变量：adapter 不负责 ACL、Evidence 构造、回答或 citation；不得自行读取 active release、authority、legacy 表或远程服务；固定 corpus/query/recipe 下结果可复现。
- 本模块不冻结的实现细节：分词、字符 n-gram、字段权重等内部算法和未来向量/混合 adapter 参数。

### C3：ACL、Evidence 阶段与非泄露合同

- 输入：C1 请求、active release entries、pre-selection/pre-generation `AuthorizationDecision` 与 C2 matches。
- 成功输出：仅对授权 entry 构造 candidate Document Evidence；完成选择/去重后推进为 selected，并为选中项取得同轮 pre-generation allow decision，供下一模块在真实入模边界再次核验。
- 失败语义：权限、用途或 revision 在两次检查之间变化时，相关 Evidence 不返回；若最终无可见 Evidence，内部保留可审计 reason，外部安全投影不暴露标题、revision、命中数或存在性。
- 必须保持的不变量：未授权 entry 不进入 adapter；Evidence 必须来自本次 active release；M32 不把“通过 pre-generation 检查”写成 generation-visible，只有下一模块把 Evidence 真正交给 Composer 时才能推进该阶段。
- 本模块不冻结的实现细节：未来 controller 如何把内部 reason 投影成四轴状态、Trace/debug bundle 的最终保留期。

### C4：RAG Retrieval Eval 合同

- 输入：版本化 Scenario catalog、caller fixture、active release/corpus identity、adapter/recipe/runtime identity、gold document/revision/anchor，以及一次真实 Knowledge Tool ExecutionEvidence。
- 成功输出：候选覆盖、selected 覆盖、排序、reason、ACL 非泄露、revision、调用次数和 runtime identity 等 typed assertion；required Gate 与 retrieval-only advisory 视图分开。
- 失败语义：技术不可用导致不能判断效果时为 `not_observed`，不能记成业务 failed；预期 `no_candidate` 或安全无证据是可观察的产品行为，可以通过 required assertion；缺失、额外、重复或 identity 不匹配的 completed artifact 整体拒绝。
- 必须保持的不变量：一个 Scenario 只调用一次 Tool；scorer 不重跑 retrieval；M31 `phase4-v1` 和 M27 v3 不改写；retrieval-only 提升不代表答案或 citation 支持提升。
- 本模块不冻结的实现细节：端到端 answer assertions、LLM judge、P2 完成后的长期 baseline 登记和 P3 默认 adapter 选择。

## 6. 工作切片与执行顺序

### M32-A：合同与开工基线

- 优先级：必须完成
- 依赖：M31 active release、governance/Evidence 接口、已确认的 G0/G1/G2/G3 与本计划 G-M32
- 实施内容：创建 `m32-notes.md` checklist；记录 Git/active release/corpus/测试基线；冻结 C1-C4 的数据语义、reason registry、safe diagnostics allowlist 和最小 Scenario 集。
- 关键合同：C1、C4
- 交付物：可回读的合同/Scenario fixture 与开工素材。
- 验证方式：静态 closed-world loader 测试、active identity 对账、旧合同只读检查。
- 完成门：任何 outcome/reason/identity 未定义时不得进入 adapter 实现。

### M32-B：本地 deterministic Retrieval Adapter

- 优先级：必须完成
- 依赖：M32-A、active entries fixture
- 实施内容：建立 adapter seam 与本地 baseline；实现稳定规范化、候选匹配、排序、去重、预算和结构化技术失败；保持检索算法内部可替换。
- 关键合同：C2
- 交付物：离线 adapter、match record/runtime identity、聚焦单元测试。
- 验证方式：固定 query/corpus 重复运行相同；gold/zero-hit/并列排序/重复/预算/异常注入 case。
- 完成门：adapter 只消费传入 entries，且不存在 authority/legacy/网络旁路。

### M32-C：Knowledge Tool 安全取证编排

- 优先级：必须完成
- 依赖：M32-B、`load_active_release()`、M31 caller/ACL/Evidence
- 实施内容：按 active load → pre-selection filter → adapter → Evidence candidate → select/dedupe → pre-generation recheck → selected outcome 的固定顺序编排；统一内部 reason 与安全投影。
- 关键合同：C1、C3
- 交付物：Knowledge Tool 深接口、RetrievalOutcome、safe diagnostics、故障注入与非泄露测试。
- 验证方式：授权命中、无候选、角色篡改、匹配但无权、ACL/revision 中途变化、release 损坏、adapter error、投毒正文作为普通数据等 case。
- 完成门：未授权正文从未进入 adapter；ledger 最远只到 selected；Tool 不生成答案或最终产品状态。

### M32-D：Phase 4 RAG Retrieval Eval

- 优先级：必须完成
- 依赖：M32-C、M29 Scenario blueprint、M31 closed-world Eval 方法
- 实施内容：新建独立版本化 RAG retrieval contract family；至少覆盖授权 policy/metric 命中、no candidate、ACL 非泄露、stale/release 异常、retriever unavailable、determinism/runtime identity；同次 ExecutionEvidence 投影 required 与 advisory assertions。
- 关键合同：C4
- 交付物：Scenario catalog/runner/projector、completed artifact 校验、required Gate、retrieval-only 报告或安全摘要。
- 验证方式：正常 artifact + 缺/额外/重复 Scenario/assertion/identity 的负向测试；同 runtime root 重复运行结果一致。
- 完成门：M31 `phase4-v1` 的 8 Scenario/12 required 语义不变，M27 v3 文件与 artifact 无修改。

### M32-E：回归、素材固化与交接

- 优先级：必须完成
- 依赖：M32-A 至 M32-D
- 实施内容：聚焦测试、受影响 P1/Text2SQL/Eval 回归、全仓确定性测试、compileall、diff 检查和注释审查；把决策、失败与真实数字写入 `m32-notes.md`。
- 关键合同：C1-C4
- 交付物：验证快照、文件清单、P2 下一切片 handoff。
- 验证方式：按 `docs/state/runbook.md` 使用项目 Python；Windows basetemp 使用 `.agent_work/temp/` 下新的 M32 路径。
- 完成门：不调用真实 provider/Milvus/LangFuse；确定性门全绿，历史只读边界和默认配置未改变。

## 7. 决策门

### G-M32：M32 模块边界

#### 方案 A：先闭环安全取证（推荐）

- 做法：M32 完成 deterministic retrieval adapter、Knowledge Tool、ACL/Evidence 和 retrieval Eval；下一模块再接 Shared Evidence Gate、Composer、generation-visible/citation 和公开 RAG API。
- 影响：本模块没有用户可见答案，但可以单独证明“找对、拿对、没越权、失败能归因”；下一模块可在稳定 Tool 上只调回答闭环。
- 适用条件：当前刚完成 P1，尚无 retrieval 失败证据、答案合同实现或 RAG baseline。
- 风险：P2 需要至少两个模块；M32 演示偏工程内部，需要通过 Eval/trace fixture展示价值。

#### 方案 B：M32 一次完成整个 P2 垂直切片

- 做法：在方案 A 基础上，同模块继续实现 Shared Evidence Gate、deterministic/remote Composer、citation 用户视图、四轴投影和 `/api/query` RAG 路径。
- 影响：单模块结束即可展示用户可见 RAG，但会同时修改取证、生成、公开 API、Trace 和 Eval，失败归因与验收矩阵显著扩大。
- 适用条件：用户更看重一次交付可见 demo，并接受更长施工周期和中途追加模型节点/outbound 决策。
- 风险：容易把“retrieval 命中”误当“答案受支持”；远程 generation 仍默认 deny，若不新增授权只能再设计 deterministic Composer；还可能提前触发 G0 公开响应迁移细节。

#### 建议与确认时点

- 建议：选择方案 A。
- 建议理由：它围绕一个主要问题形成完整闭环，遵守 state 的“先做本地可替换 retrieval + Knowledge Tool，再接薄 Gate/Composer/Citation”顺序；也让用户能分别理解取证层和回答层，而不是看到一条难排障的大流水线。
- 用户确认前允许推进：只允许阅读、计划审查和解释；本轮计划文件可作为决策材料。
- 用户确认前禁止推进：不创建 `m32-notes.md`、不修改生产代码/测试/Eval、不选择 P3 默认 adapter、不放行任何远端用途。
- 需要确认的时点：M32 开工前。
- 重开决策的条件：实现前发现现有 Tool/Eval seam 无法独立验收，或用户明确要求本模块结束必须提供公开 RAG demo。

Roadmap **G4「首个 Knowledge Tool 运行时默认 adapter」本模块不触发**：M32 只产生第一个已验证候选和本地 deterministic baseline；要到 P2 的回答/citation 闭环也通过、能够按闭环可靠性判断时，才决定它是否成为 P3 默认 adapter。M32 不改变任何长期默认配置。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 Knowledge Tool 正常取证 | 固定 active release + 授权 caller + policy/metric gold query | outcome 已观察且成功；Evidence 来自 gold active revision；adapter 恰好调用一次 | 必须完成 |
| C1 失败归因 | zero-hit、release error、adapter error 故障注入 | `no_candidate`、release/revision 异常、`retrieval_unavailable` 不互相冒充；技术不可用不写成业务错误 | 必须完成 |
| C2 可复现与可替换 | 同输入重复、并列/重复/非法 match、fake adapter | 顺序和 identity 稳定；异常 match 失败关闭；Tool 不依赖 adapter 内部算法 | 必须完成 |
| C3 pre-selection ACL | 角色篡改、匹配受限文档、公开投影对照 | 未授权 entry 不进入 adapter；响应/diagnostics 不含其标题、revision、identity、命中数或正文 | 必须完成 |
| C3 pre-generation/revision | 两次检查间撤销 revision、变更用途/ACL | 相关 Evidence 不返回；ledger 不越过 selected；reason 可审计且安全投影收敛 | 必须完成 |
| C3 Evidence identity | candidate/select/dedupe 与 active bundle 对账 | EvidenceRef 的 authority/revision/content/anchor/release 全部匹配；无重复 Evidence | 必须完成 |
| 文档投毒边界 | 注入伪系统指令/伪 citation/诱导 Tool 文本 fixture | 文本只作为 Evidence content；不改变 adapter/ACL/control flow，不产生 Tool Call 或 citation | 必须完成 |
| C4 一题一次执行 | fake adapter call counter + 多 assertion | 一个 Scenario 只调用一次 Tool，全部 scorer 读取同一 ExecutionEvidence | 必须完成 |
| C4 closed-world artifact | 缺失/额外/重复 Scenario、replicate、assertion 和 runtime/corpus/adapter identity 反例 | 任一不一致整体拒绝，不投影可信 Gate | 必须完成 |
| retrieval-only 视图 | gold candidate/selected coverage、rank 视图 | required identity/ACL/reason 与 advisory 排序指标分开；不生成 answer score | 必须完成 |
| 历史与默认边界 | M31 phase4-v1、M27 v3、API/Text2SQL、配置回归 | 既有合同语义不变；无旧 artifact 改写；无模型/embedding/vector/LangFuse 默认变化 | 必须完成 |
| 代码与回归 | 聚焦 → 受影响 → 全仓 pytest；compileall；`git diff --check` | 所有新增 required 测试通过；既有 skip/warning 如实记录；无真实 provider 调用 | 必须完成 |

聚焦顺序固定为 adapter → Tool/ACL/Evidence → RAG retrieval Eval → P1 release/governance/Evidence 回归 → API/Text2SQL/Eval 受影响回归 → 全仓确定性测试。若中途失败，先记录和定位，不用更换 basetemp 之外的方式掩盖真实失败。

本模块不运行真实 LLM、远程 embedding/rerank、Milvus、LangFuse Cloud 或真实端到端 RAG Eval；因此验收不包含开放答案质量、语义 citation support、P3 默认 adapter 或远端成本结论。M27 v1/v2/v3、M31 `phase4-v1` artifact/report 均保持只读，不能与新 retrieval family 混算。

## 9. 依赖与交付物

### 依赖

- M30 source-backed catalog 与 Text2SQL 隔离。
- M31 active immutable release、trusted caller、ACL/outbound、Document Evidence 和 ledger。
- M29 的四轴/reason/Scenario blueprint；其中本模块只消费 retrieval 相关语义。
- `docs/phase4-roadmap.md` P2、跨里程碑不变量和 `docs/phase4-reference.md` P2/Eval 能力卡。
- `docs/state/runbook.md` 的项目 Python、临时目录与默认配置纪律。

### 交付物

- 可替换 retrieval adapter interface 与本地 deterministic baseline。
- 稳定 Knowledge Tool request/outcome/reason/diagnostics 深接口。
- active release → ACL 双检 → Document Evidence candidate/selected 的安全取证流程。
- 独立版本化 RAG retrieval Scenario/Eval family、required Gate 与 retrieval-only 视图。
- 聚焦/回归测试、故障注入、`m32-notes.md` 过程素材和下一切片 handoff。

文件、类名、算法参数和报告路径在实现调查后按现有依赖方向确定；不得为了计划显得具体而提前制造聚合 `engine.rag.__init__` re-export 或万能对象。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：最终 Evidence Gate、Composer、generation-visible/cited、用户可见 citation、公开 API/四轴状态、Trace 投影和真实答案质量。
- 下一模块可直接消费的产物：Knowledge Tool interface、selected Document Evidence、pre-generation decision、safe diagnostics、retrieval ExecutionEvidence 和 Scenario fixtures。
- 后续需要根据真实失败重新规划的内容：词法 baseline 的候选/排序失败簇、是否准备未污染 held-out、是否实验 embedding/hybrid/rerank/parent-child，以及 G4 默认 adapter。
- 可能存在的风险：中文短查询的词法覆盖有限；所有首批文档均为角色受限，demo 需要显式 trusted fixture；安全收敛会让内部“知识不存在”和“无权看”不能在公开层区分；第一版只有 11 条短知识，不能外推长文检索能力。

## 11. 开工条件

- 开工前无需确认：继续只读 active release；继续使用 M31 trusted caller/ACL/Evidence；Knowledge 远端默认 deny；M31 `phase4-v1` 与 M27 v3 只读；不引入 Graph/Router/Hybrid/parent-child/Milvus。
- 实施中需要确认：先确认第 7 节 G-M32 采用方案 A 或 B；推荐 A。若选择 A，实施中无其他预设用户决策门，且 G4 明确延后。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；尤其不得自行改变默认 adapter、公开 API、安全策略、正式 Scenario、远端出站或历史合同。
