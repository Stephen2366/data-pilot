# M42 Phase 4B B0 阶段入口、北极星前置与 Agent Eval 骨架开发计划

> 能力里程碑：Phase 4B B0；本模块完整承担 B0，不提前实现 B1–B6 的 Task runtime、Decision Loop、RAG Subgraph、durable state 或 Context Compact
>
> 主要问题：Phase 4B 的连续任务故事目前缺少可执行的 7/8 月业务事实、最小权限身份、真实 RAG 恢复 case、可泛化 Hybrid 语义、独立 Agent Eval 身份和未污染默认决策集，直接开发后续能力会围绕错误或不可验证的前提施工

## 1. 模块定义与范围判断

用户已冻结“B0–B6 各对应一个模块和一份 module plan”，因此 M42 完整对应 B0，不再把 B0 拆成多个模块；模块内部以 M42-A～M42-F 纵向切片推进。

M42 只闭环一个主要问题：把 Phase 4B 北极星所需的数据、身份、知识、Hybrid 语义、兼容方向和评测身份变成可执行、可审计、可在后续模块复用的前置合同。模块完成后，用户能够：

- 用真实 SQL 验证 T1–T5 所依赖的 7/8 月净退款、原因、渠道和商品分解；
- 说明同一 demo caller 为什么能以最小角色集安全跨 SQL 与政策文档任务，而不是依赖“拥有全部角色”；
- 展示一条自然、确需双文档、且不是人为压低检索预算制造的 business RAG case；
- 查看一份把 legacy runtime、agent runtime、旧 thread payload 和未来 task payload 分开的兼容矩阵；
- 生成并篡改测试一份独立 Agent Scenario completed artifact skeleton，证明漏 turn、额外 execution、重复 assertion 或身份漂移都不能通过；
- 解释新 decision reserve 如何在动作、Prompt 和参数选择前密封，以及 M34 既有 120 题为什么只能作 historical regression。

M42 不以“已经设计了后续 schema”冒充 B1–B6 能力完成。B0 完成时北极星仍不会连续自然多轮执行，系统也没有 Observation-driven Loop、RAG Subgraph、跨进程恢复或 Compact；这些缺口分别由 M43/B1、M44/B2、M45/B3、M46/B4、M47/B5、M48/B6 强制承接，且各自必须达到对应 roadmap 最终验收标准后才能宣称里程碑完成。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| 当前 10,000 个订单只分布在 2026 年 5/6 月；退款 `processed_at` 由订单时间加 4–8 天派生，无法形成同口径 7→8 月净退款故事 | T1/T2 没有真实 7/8 月 SQL oracle，T3/T5 也没有可验证的原因/渠道/商品变化 | `scripts/seed_data.py::_build_orders_and_items / _build_refunds`、`docs/state/database-current-state.md` |
| `verify_business_facts()` 只冻结 6 月事实；`orders_wide` 固定使用 2026-07-01 snapshot/batch | 新 profile 若只改退款或订单而不升级事实验证与宽表身份，会出现星型表、宽表和 oracle 漂移 | `scripts/seed_data.py::verify_business_facts / _build_orders_wide`、`tests/test_m1_models.py` |
| M27 RunSpec 默认只写标签 `sqlite_deterministic_seed`，没有绑定实际 seed recipe/content/config fingerprint | 修改数据后仍可能保留相同 oracle label，使旧新结果被误判为可比 | `eval/contracts.py::EvalRunSpec`、`eval/run_eval.py`、`eval/scorers/rule_scorers.py` |
| 当前 `FixtureCallerResolver` 给 demo/test caller 注入全部 `KNOWN_ROLES`，请求 `user_role` 只选择 active SQL role | 能通过现有测试，但不能证明北极星只需 `ops + customer_service`，也不能展示跨 turn 重新授权的最小权限故事 | `engine/harness/caller.py::FixtureCallerResolver` |
| `net_refund_amount` 与 SQL RBAC 需要 `ops`；基础/质量退款政策只允许 `customer_service` | 单 active SQL role 不能替代 resolved role 集；为 demo 放宽知识 ACL 会改变正式 release 与安全合同 | `domain_pack/metrics.yaml`、`engine/sql_guard/rbac.py`、active release `7d0d0937...409a` |
| 当前 business RAG 的双文档题直接点名“基础退款政策和质量问题专项规则”，默认 lexical 一次即可取全 | 该题只能证明单次 Pipeline 已工作，不能承担 B3/B4 的恢复动作证据 | `eval/cases/rag/scenarios.yaml::refund_policy_multi_document`、`docs/state/AI_CONTEXT.md` |
| 当前 Hybrid `refund_reason_and_policy` 固定生成“退款原因排名 + 质量问题退款规则”，且没有时间、比较、原因或渠道 Task 语义 | 不能继承 8 月相对 7 月的任务状态，也不能支撑 T4/T5 | `engine/harness/router.py::_hybrid_plan_for`、`engine/harness/contracts.py::HybridPlan`、`docs/notes/m38-notes.md` |
| M35–M38 artifact 分别冻结一次 Graph、单路至多一个深 Tool、Hybrid 两支各一次；API 当前最大 `graph_invocation_count=1` | 新 Agent family 若不显式隔离，会静默破坏 legacy assertion 和客户端解释 | `eval/harness*_contracts.py`、`app/schemas/agent.py::AgentResponse` |
| `QueryRequest` 只严格校验已知 resume/follow-up 组合，Pydantic 未建立统一 `extra=forbid` 合同 | B1 新 task payload 不能靠字段是否为空或未知字段被忽略来猜 runtime family | `app/schemas/agent.py::QueryRequest` |
| M41 已提供 RAG 一次执行、funnel、closed-world artifact 和 review 来源哈希，但合同只覆盖单题/replicate，不表达多 turn TaskState、Action、Budget 或 Context | 可复用 EvalOps 纪律，不能把 M41 artifact 改字段后冒充 Agent Scenario | `eval/rag_e2e_contracts.py`、`docs/notes/m41-notes.md` |
| M34 的 180 题和 120 held-out 已用于 retrieval/Answer 默认决策并形成完整结果 | 原 held-out 已被解封，不能继续称 Phase 4B 未污染 decision reserve | `docs/state/eval-baselines.md`、`docs/notes/m34-notes.md` |
| 22 条短业务 release 与 36,417 文档 external corpus 的规模、长度和失败可见性差异很大 | 小 business fixture 合同全绿不能证明大 corpus 的召回、packing 或多文档质量底座 | `docs/state/rag-current-state.md`、M34/M41 completed artifacts |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| Agent Eval 必须评分真实运行看到的 answer/context，而不是评分时重跑 | `agentic-rag-for-dummies/notebooks/evaluation.ipynb::query_rag / assert_saved_outputs_match_dataset / score_answer` | 一次运行后保存实际 answer/context；评分前验证保存材料与当前数据集一致；pipeline failure 不伪装正常分数 | M42 只冻结独立 sequence/turn/ExecutionEvidence skeleton；后续 scorer 只读同一任务运行的安全投影，closed-world validator 先校验 identity 和执行闭集 | notebook CSV 唯一事实源、每题独立 reset 冒充多轮、简单均值、跳过失败后不保留 `not_observed`、RAGAS 直接决定 required Gate |
| retrieval 与 answer 需要分层，不让单一分数掩盖失败位置 | `DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/retriever.py::RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator`；`answer.py::AnswerRelevancyMetric / LLMAnswerEvaluator` | retrieval 与 answer 使用不同输入和 evaluator | Agent Scenario skeleton 为后续 turn/action/Evidence/Context assertion 留独立 typed 槽位；RAG 质量仍保留 retrieval→answer 分账 | evaluator 为评分重新执行 operator、空结果统一计 0、不区分不可观察、单个 LLM 0–5 分替代安全 Gate 和人工复核 |
| seed、case、release 的 source 与 derived identity 必须分开 | `WrenAI/core/wren/src/wren/memory/index_backend.py::MemoryIndex.reset / LanceDBIndex.rebuild`；`watch.py::compute_fingerprint / poll_once` | 原件与派生索引分离；重建成功后才推进 observed state | seed recipe/content/config、oracle projection 与数据库实例分别有 identity；只有校验和构建成功才发布 Phase 4B profile pointer/manifest | 只用 path/size/mtime fingerprint 冒充内容 identity、watcher 冒充原子发布、自动 fallback 未校验旧 profile |
| 如需新增知识语料，替换过程不能覆盖旧 active release | `DataAgent/.../AgentVectorStoreServiceImpl.java::replaceDocumentsByMetadata` | metadata 身份过滤、先加入新文档再删除旧文档、异常时尝试清理新文档 | 仍使用 DataPilot immutable staged release → validation → active pointer；候选失败不改变当前 `7d0d0937...409a` | best-effort cleanup 冒充事务式替换或完整回滚、随机新 ID 冒充稳定 Evidence identity、Java 平台结构 |
| Hybrid 汇合不能靠末尾拼自然语言与 sources | `GustoBot/.../multi_tool.py::local_search / finalize / _collect_sources` | 仅借鉴多数据面结果分开保存、末端汇合的失败形态 | M42 只冻结 versioned Hybrid operator 语义方向；M44 继续消费 SQL/Document typed Evidence 和唯一 Synthesizer/Citation 合同 | Router 未指定 Tool 时 postgres+milvus 自动兜底、把文件名列表当 citation、任一结果命中即视作 complete、自动 fallback 扩大预算 |

参考规模与保证边界：ARAG Eval 是 notebook 级、逐题独立评估；DB-GPT evaluator 提供局部 retrieval/answer 指标；Wren/DataAgent 只证明局部 source/index 或替换顺序；GustoBot 没有 DataPilot 的 typed 双 Evidence、ACL、四轴和 claim-level citation。它们均不能证明 22 条 business release 或 36,417 文档 external corpus 已足以支持 Phase 4B。M42 的正向安全、身份、closed-world 和不污染保证仍由 DataPilot 自身合同与测试负责。

### M41 与 Phase 4B 的继承关系

Phase 4B 不回退到 M41 之前的 Eval 做法，也不另起一套互不相干的评测基础设施。roadmap 继续负责定义 B0–B6 要达到的能力和验收终点；M41 作为已经完成并验证过的 EvalOps 基线，被 M42–M48 继续沿用和向上扩展：

- **原样沿用**：一次真实执行后评分、resolved runtime identity、retrieval→answer funnel、`not_observed`、closed-world execution、review source hash、安全投影与失败可见性。
- **在新 family 中扩展**：M42 新增独立 `phase4b-agent-scenario-v1`，表达 sequence、turn、TaskState/Action/Budget/Context、双 Evidence 和跨 turn assertion；其 validator/scorer 复用 M41 的纪律和通用组件，但使用独立 schema、identity、报告和 Gate。
- **不原位修改**：M41 已完成 artifact、签名、基线与单题/replicate 合同保持只读，不补字段、不改签、不用新 scorer 重算成“新版 M41 分数”；否则会破坏历史可比性并重现 Eval 事故。
- **回归关系**：M42–M48 每次涉及 Eval 合同的修改，都必须跑 M41 受影响回归；只有能证明通用实现变化不改变 M41 冻结语义时才允许共享底层代码。

因此施工原则不是“只按旧 roadmap”或“直接继续改 M41”二选一，而是：**按现有 Phase 4B roadmap 推进能力，在 M41 已验证的 Eval 地基上新增 Agent Scenario 上层合同，并保持 M41 历史证据只读。**

## 4. 目标、优先级与非目标

### 模块完成状态

M42 完成后，项目拥有一套经用户确认、与 legacy 隔离的 Phase 4B 前置包：versioned seed/oracle profile、北极星与非 happy-path catalog、最小 demo caller、真实 business RAG gold case、Hybrid operator 方向、Agent Scenario artifact skeleton、兼容矩阵、sealed decision reserve manifest/污染账本和 capability matrix。所有材料都能被 M43/B1 与 M45/B3 直接消费，且不会改变产品默认 runtime。

### 必须完成

- 建立独立 Phase 4B seed/oracle profile，并让 identity 绑定 seed recipe/content/config；legacy profile 与历史 artifact 保持只读。
- 以真实 SQL 冻结 7/8 月 `net_refund_amount` 及原因、渠道、商品分解，验证分解可与政策适用范围合成，但不把政策写成上涨因果。
- 同步 `orders_wide` snapshot/batch、`verify_business_facts()`、相关 oracle/schema/state 和新旧 profile 解析的 fail-closed 合同。
- 冻结最小 resolved role 集、active SQL role 和每 turn 重新授权规则；不修改生产认证边界。
- 冻结 T1–T5 canonical、extended 与非 happy-path Scenario；每 turn 说明 TaskDelta 类别、Evidence requirement/失效、route/action、四轴、required/advisory assertion 和安全 identity。
- 实际观察至少一个自然 business 双文档 case 的首次默认检索；gold 必须先于观察结果冻结，且不得用测试专用预算/metadata 制造失败。
- 冻结 legacy/agent runtime family 与 API/state 增量演进矩阵初版；旧 payload 保留，新 task payload 与其互斥。
- 建立独立版本化 Agent Scenario skeleton、ExecutionEvidence、RunSpec/completed artifact 与 closed-world validator。
- 建立新 sealed decision reserve 的生成/抽样/gold/污染/首次解封规则和不可变 manifest；M34 120 题只保留 historical regression 用途。
- 冻结 action catalog 的 global catalog、runtime/corpus applicability、single-run eligible set 与 `stop` 三层语义；不提前批准 B3 尚未证明的动作。

### 建议完成

- 提供安全的人读版北极星/兼容/capability matrix renderer，避免 YAML/JSON 成为唯一验收入口。
- 为 seed/profile、Agent Scenario 和 reserve manifest 共用 canonical content hash 规则，但不为“代码复用”合并业务合同。
- 提供一条零 provider 的本地 rehearsal：加载新 profile、解析最小 caller、执行确定性首次 retrieval、构造并校验 skeleton artifact。

### 条件触发

- **触发条件**：当前 22-entry release 无法形成业务合理、确需双文档且非测试陷阱的 case。
- **允许动作**：先基于独立业务理由完成语料内容和 gold 审查，再按 immutable release 流程发布候选并回归 ACL/identity。
- **未触发时**：不修改 `domain_pack/kb_docs/`、active release、文档 ACL 或默认 retrieval。

- **触发条件**：实施中发现拟定 seed 结构无法同时满足金额、原因、渠道、商品四种 oracle，或会破坏 legacy 固定事实。
- **允许动作**：停在新 profile 内调整 recipe 和 exact facts，重新提交 G1；必要时升级新 profile identity。
- **未触发时**：禁止修改 legacy canonical seed/oracle identity。

### 明确非目标

- 不实现自然语言 Turn → TaskDelta、TaskState merge、Evidence invalidator 或 node Context Builder；这些属于 M43/B1。
- 不实现 Observation-driven 顶层 Decision Loop、Action/Budget/Progress/Termination runtime；这些属于 M44/B2。
- 不开展 RAG action diagnostic campaign，不准入恢复动作；这些属于 M45/B3。
- 不实现或切换 RAG Subgraph；这些属于 M46/B4。
- 不实现 durable adapter、数据库 checkpoint schema、restart/multi-worker 恢复；这些属于 M47/B5。
- 不实现 Context Compact；这些属于 M48/B6。
- 不运行真实 LLM、remote embedding/Milvus、LangFuse Cloud、M34/M41 真实 Eval 或 decision reserve A/B。
- 不修改默认模型、embedding、external lexical、business retrieval、普通 Composer、active Knowledge release 或产品 `/api/query` 默认 runtime。

## 5. 关键合同

### C1：Phase 4B seed/oracle profile 合同

- 输入：经 G1 确认的 seed recipe、exact 7/8 月事实、schema/metric/release 配置和 profile family/version。
- 成功输出：可复现数据库实例及 manifest；profile identity 绑定 recipe/content/config fingerprint；真实 SQL 验证金额和多维分解，星型表/宽表/oracle 一致。
- 失败语义：未知 profile、fingerprint 漂移、宽表 batch 不匹配、事实不闭合或 legacy/new profile 混用时在执行前失败关闭。
- 必须保持的不变量：`net_refund_amount` 使用 completed + `processed_at` + 带符号金额；旧 artifact/legacy profile identity 不变；政策只能解释处理规则，不能证明业务因果。
- 本模块不冻结的实现细节：profile loader、builder 或 manifest 的具体类名和文件拆分；但不能只用字符串标签代替内容身份。

### C2：北极星任务与最小 caller 合同

- 输入：T1–T5/extended/非 happy-path Scenario、经 G2 确认的 resolved role 集、active SQL role 和 current caller/tenant identity。
- 成功输出：每个 turn 的预期 TaskDelta 类别、Evidence requirement/失效、route/action、四轴、安全 identity 和 assertion plan；caller 能以最小权限跨 SQL/Document turn 重新授权。
- 失败语义：角色不足、owner/tenant/active role 漂移、ACL/revision/purpose 失效或题面无法映射到稳定 gold 时保守拒绝/澄清，不临时扩权。
- 必须保持的不变量：请求体 role 只能选择、不能授权；local/demo/test 不冒充生产认证；T1–T5 不是退款/月/渠道专用状态 schema。
- 本模块不冻结的实现细节：B1 TaskDelta/TaskState 字段名、自然语言 adapter、Context projection 和 API task payload 的具体字段。

### C3：business RAG case 与 Hybrid 语义合同

- 输入：先冻结 gold requirement 的自然业务问法、当前 active release/caller/ACL/default budget，以及经 G4 确认的 versioned Hybrid operator 方向。
- 成功输出：首次 retrieval Observation 的不可变诊断证据；case 逻辑上确需基础政策与质量专项规则；Hybrid 语义能表达“比较事实 + 规则解释”，不继承固定 6 月/原因排名字符串。
- 失败语义：一次已取全是合法 Pipeline 结果，不算 recovery 失败；gold 不合理、题面点名答案、需要测试专用预算或 ACL 放宽时拒绝成为 canonical case。
- 必须保持的不变量：B0 不制造漏召回、不执行恢复动作；现有 `refund_reason_and_policy` v1 和 M38 legacy fixture 不改写；RAG Tool 不生成 Hybrid 子答案。
- 本模块不冻结的实现细节：B2/B4 的 TaskState-to-plan adapter、具体 rewrite/expansion 动作、父子预算和 Subgraph 拓扑。

### C4：Agent Scenario skeleton 与 runtime family 合同

- 输入：versioned sequence catalog、turn catalog、assertion plan、seed/caller/release/runtime/policy identity 和一次 sequence ExecutionEvidence。
- 成功输出：独立 `phase4b-agent-scenario-v1` completed artifact skeleton；每个 selected sequence/turn/execution/assertion 恰好闭合，identity 可复算并可生成安全报告。
- 失败语义：缺 turn、额外/重复 execution、重复/未知 assertion、顺序漂移、seed/caller/release/runtime identity 漂移或 artifact hash 不符均拒绝 completed。
- 必须保持的不变量：一条 sequence 一次执行；Trace/API/Eval 将来从同一 task/turn/action 事实投影；旧 M31–M41 artifact 不补字段、不改签、不混算。
- 本模块不冻结的实现细节：B1–B6 逐步加入的能力 assertion、runner/checkpoint 内部组织和真实 task runtime 实现。

### C5：legacy/agent 兼容与 action catalog 语义合同

- 输入：legacy initial/resume/follow-up、新 task initial/continuation/switch/cancel 的请求类别，以及 runtime family identity、runtime/corpus、ACL 和首次 Observation。
- 成功输出：兼容矩阵明确每类请求由哪个 family 解析、允许的执行预算和稳定错误；action card schema 表达 trigger/scope/budget/ACL/outbound/Evidence gain/stop。
- 失败语义：旧/new payload 混用、未知 family、字段猜测、runtime/corpus 不适用或没有 Observation 时失败关闭；`stop` 始终合法。
- 必须保持的不变量：同一 `/api/query`；legacy 字段和旧预算不改；agent family 独立版本化；全局 catalog 有候选不等于单次 eligible，也不等于动作已获 B3 准入。
- 本模块不冻结的实现细节：B1 task payload 字段名和 unknown-field 最终策略、B2 预算数值、B3/B4 的具体 action identity。

### C6：sealed decision reserve 与 artifact 保留合同

- 输入：经 G5/G6 确认的 reserve 来源、规模、抽样/gold protocol、immutable storage、污染账本和仓库 manifest。
- 成功输出：在任何 action/Prompt/参数选择前密封的 reserve identity；记录创建、访问、首次解封、用途、退出状态与文件 hash；仓库保留安全汇总和失败切片。
- 失败语义：逐题结果或 gold 被用于调动作后立即退出 decision reserve；identity/hash/访问账本不闭合时不得用于默认切换。
- 必须保持的不变量：M34 120 题只是 historical regression；reserve 不进入 B0/B3 参数选择；长期 artifact 不保存完整正文、SQL rows、凭据或模型 Thought。
- 本模块不冻结的实现细节：B4 A/B 的模型/预算/动作参数和最终默认结论。

## 6. 工作切片与执行顺序

### M42-A：决策包、identity 规则与北极星合同冻结

- 优先级：必须完成
- 依赖：Phase 4B roadmap、当前 database/RAG/Eval state、G1–G6 用户确认。
- 实施内容：把 T1–T5、extended、非 happy-path、seed/caller/release/runtime/policy identity、兼容方向、reserve/action 语义冻结为机器可读合同和人读矩阵；先建立 canonical hash/fail-closed 规则。
- 关键合同：C1–C6。
- 交付物：北极星 catalog、决策记录、identity schema、兼容矩阵初版、capability matrix 初版。
- 验证方式：schema/identity 单测；删除或篡改任一 identity 后加载失败；审查没有硬编码退款/月/渠道专用 TaskState 字段。
- 完成门：后续切片只消费已确认合同，不再各自重新定义 seed、caller、runtime 或 case 语义。

### M42-B：Phase 4B seed/oracle profile

- 优先级：必须完成
- 依赖：M42-A、G1。
- 实施内容：建立与 legacy 隔离的新 profile；生成 7/8 月净退款与原因/渠道/商品分解；同步宽表 snapshot/batch、事实 verifier、oracle identity 和 profile resolver。
- 关键合同：C1。
- 交付物：seed recipe/profile manifest、真实 SQL oracle、相关 schema/state 更新和新旧 profile 回归。
- 验证方式：SQLite 确定性重建两次 identity/事实完全一致；金额与三类分解各自守恒；legacy 固定事实与 M27 fixture 在显式 pin 后不变。
- 完成门：任意消费者若只写 `sqlite_deterministic_seed` 或混用 profile，都无法通过 Phase 4B identity Gate。

### M42-C：最小 caller、business RAG case 与 Hybrid 方向

- 优先级：必须完成
- 依赖：M42-A/B、G2–G4、当前 active business release。
- 实施内容：建立最小 demo fixture；先冻结自然问题的 gold，再用当前默认 budget 实际观察首次 retrieval；如确有业务需要才走候选 release；冻结 versioned Hybrid operator 的语义输入/输出和 legacy 保留边界。
- 关键合同：C2、C3。
- 交付物：caller fixture identity、跨 turn 权限矩阵、canonical RAG case/Observation、Hybrid operator contract/direction。
- 验证方式：`ops + customer_service` 正向；缺任一角色、active role 错误、ACL/revision/purpose 漂移反例；首次 retrieval 零 provider、无测试专用参数；legacy M38 operator 仍按原合同运行。
- 完成门：case 无论一次取全还是漏证据，都是真实可解释 Observation；不得为了得到 recovery case 改参数或语料。

### M42-D：Agent Scenario artifact skeleton 与 closed-world validator

- 优先级：必须完成
- 依赖：M42-A～C。
- 实施内容：建立独立 sequence/turn/ExecutionEvidence/RunSpec/assertion/completed artifact interface；实现安全序列化、identity、validator 和人读投影；首版用 deterministic fixture 填充尚未实现能力的 expected/unavailable 状态。
- 关键合同：C4、C5。
- 交付物：Agent Scenario contract family、catalog/selector skeleton、artifact validator、报告/capability matrix renderer、篡改测试。
- 验证方式：缺 turn、额外 execution、重复 execution/assertion、身份漂移、hash 篡改、legacy family 注入全部失败；合法 skeleton 完成且零产品重跑。
- 完成门：M43–M48 只能递增 assertion，不需要改写 M42 的一次 sequence/closed-world interface。

### M42-E：sealed reserve、污染账本与长期 artifact manifest

- 优先级：必须完成
- 依赖：M42-A、G5/G6；不依赖 B3 动作实现。
- 实施内容：按确认 protocol 创建/抽样并密封新 reserve，冻结 gold 与分层 identity；建立只追加访问/污染/首次解封账本；定义项目外 immutable artifact 与仓库内安全 manifest 的映射。
- 关键合同：C6。
- 交付物：reserve manifest/identity、污染账本、访问与退出规则、artifact retention manifest、M34 historical regression 标签。
- 验证方式：集合互斥/唯一/分层闭合、hash 可复算、访问状态机和污染退出测试；B0 测试不得读取 reserve 逐题内容或运行结果。
- 完成门：后续 B3 只能看到 reserve 的 identity/规模/规则，看不到逐题 gold/结果；B4 到预定时点才可首次解封。

### M42-F：B0 集成 rehearsal、回归与交接

- 优先级：必须完成
- 依赖：M42-A～E。
- 实施内容：运行零 provider 集成 rehearsal，验证新 profile、最小 caller、首次 retrieval、artifact skeleton、兼容矩阵和 reserve manifest；生成 M43/B1 与 M45/B3 首批 fixture/handoff。
- 关键合同：C1–C6。
- 交付物：B0 deterministic report、最终 capability matrix、B1/B3 fixture、模块 notes/state/changelog 技术档案。
- 验证方式：聚焦测试 → M27/M31–M41 受影响回归 → 全仓 deterministic pytest；compileall、`git diff --check`；不运行真实 provider/held-out/reserve A/B。
- 完成门：第 8 节 required 全部通过，旧/new family 同时闭合，且所有未实现能力在矩阵中明确指向 M43–M48。

## 7. 决策门

> 决策记录（2026-08-23）：用户确认 G1–G6 全部采用方案 A。下列 A 为 M42 实施基线；只有命中各门列出的“重开决策条件”时才暂停对应分支并重新提交选项，不能自行降级到 B。

### G1：Phase 4B seed profile 与 exact business facts

#### 方案 A：独立 additive Phase 4B profile（已确认）

- 做法：保留 legacy seed recipe，新增独立 Phase 4B profile/manifest；候选精确事实冻结为 2026-07 `120,000.00`、2026-08 `180,000.00`，变化 `+60,000.00 / +50%`。原因分解为 7 月 `quality_issue 48,000 / late_delivery 36,000 / wrong_item 24,000 / changed_mind 12,000`，8 月 `96,000 / 42,000 / 27,000 / 15,000`。渠道按 `Mobile App / Web Store / Tmall / JD / Douyin / Partner` 冻结为 7 月 `48,000 / 24,000 / 18,000 / 12,000 / 12,000 / 6,000`、8 月 `78,000 / 36,000 / 24,000 / 18,000 / 18,000 / 6,000`。商品按 `SKU-HIGH-REFUND-01 / SKU-WL-EB-002 / SKU-SD-LP-003 / SKU-MK-K2-004 / SKU-MS-PL-005` 冻结为 7 月 `30,000 / 24,000 / 24,000 / 24,000 / 18,000`、8 月 `54,000 / 42,000 / 30,000 / 30,000 / 24,000`。通过同一组行级事实让三个分解各自守恒，并保留负数冲销语义。
- 影响：北极星事实清楚、T3 可解释为 quality_issue 对增量贡献 80%，T5 有渠道变化；旧 M27/Phase 4 artifact 不变。
- 适用条件：愿意承担新 profile loader/identity 和双 profile 回归。
- 风险：recipe 更复杂；四种边际分解必须由行级数据共同满足，不能各写一份互不一致的 oracle。

#### 方案 B：升级现有 canonical seed/oracle identity

- 做法：直接把 7/8 月数据加入当前 `seed_database()` 默认输出，同时升级所有 oracle fixture、RunSpec/hash、Scenario 和历史可比性说明。
- 影响：运行入口较少，但 M1/M27/M31–M41 fixture、固定事实、宽表和历史解释都需要大面积重新 pin/升级。
- 适用条件：用户希望以后所有本地测试统一使用 7/8 月新世界，且接受旧新 Eval 完全不可直接比较。
- 风险：回归面大，容易让旧 artifact 看似仍使用同一 `sqlite_deterministic_seed`；与 roadmap“legacy 显式 pin”方向相比收益不足。

#### 建议与确认时点

- 建议：方案 A，并采用上述 exact facts 作为首版候选。
- 建议理由：它把 Phase 4B 新故事与历史基线隔离；数值能形成清楚的金额、原因、渠道和商品分解，又不会把政策当作增长因果。
- 用户确认前允许推进：只读审计、recipe 原型和守恒计算草案。
- 用户确认前禁止推进：修改 seed、oracle、宽表 batch、正式 Scenario 或任何长期 identity。
- 需要确认的时点：M42-B 开工前。
- 重开决策的条件：行级 recipe 无法同时满足四类守恒，或新 profile 会迫使 legacy consumer 静默使用新数据。

### G2：最小 demo caller 与政策 ACL

#### 方案 A：专用双角色 Phase 4B fixture（已确认）

- 做法：resolved roles 只含 `ops + customer_service`，active SQL role 固定 `ops`；每 turn 仍重新验证 caller/tenant/active role，Knowledge ACL 使用 resolved role 集。
- 影响：无需修改退款政策 ACL 或 active release；能演示同一可信主体具备两个职责角色，但 SQL 只按 `ops` 执行。
- 适用条件：现有 governance caller 支持多 resolved roles，且 Knowledge Tool 不错误地只读取 active SQL role。
- 风险：必须用反例证明删除任一角色会在正确层失败，而不是被全角色测试 fixture 掩盖。

#### 方案 B：继续使用全角色 fixture 或把政策 ACL 放宽给 ops

- 做法：沿用 `KNOWN_ROLES` 全集，或把两篇退款政策改为 `ops` 可读。
- 影响：实现更少，但不能证明最小权限；放宽 ACL 还会产生新 release identity 和安全回归。
- 适用条件：只有业务权限事实确实要求 ops 直接读取客服政策时才可讨论 ACL 变更。
- 风险：为了 demo 扩权，削弱 Phase 4B 安全故事。

#### 建议与确认时点

- 建议：方案 A；本模块不调整政策 ACL。
- 建议理由：当前 caller seam 已支持多角色，缺的是最小 fixture 和验证，不是权限能力。
- 用户确认前允许推进：只读验证 caller/ACL 通路和设计反例。
- 用户确认前禁止推进：更改 active release、政策 allowed_roles 或默认 caller。
- 需要确认的时点：M42-C 开工前。
- 重开决策的条件：实际通路证明 Knowledge ACL 只能消费 active SQL role，且在不破坏 seam 的前提下无法修正。

### G3：business RAG canonical recovery case

#### 方案 A：复用当前 release，先冻 gold 再观察自然问法（已确认）

- 做法：候选自然问法为“如果最近质量问题退款明显增多，客服受理这类退款时可以直接按全额退款处理吗？需要哪些前提和材料？”；gold 冻结为 `refund_policy_basic + refund_policy_quality`，要求覆盖可定位订单、质量范围/材料、质检确认和原支付路径。冻结 gold 后才用当前默认 budget 检索一次。
- 影响：不改语料、不制造失败；若一次取全，它仍是合法 Pipeline case，但不能作为 recovery 证明，M42 需继续在预注册候选问法/现有失败簇内调查。
- 适用条件：当前两篇政策确实共同支撑问法，且业务评审认可用户表达自然。
- 风险：小 corpus 很可能仍一次取全；B3 可能需要从其他真实 business/external failure 寻找动作证据。

#### 方案 B：基于独立业务理由新增语料/release

- 做法：仅在当前 corpus 无法形成任何真实双文档 case 时，先设计业务上本来就需要的新政策/例外/处理规则，冻结内容合理性和 gold，再发布新 immutable release；不得以挤掉现有文档为写作目标。
- 影响：能扩大真实业务覆盖，但改变 corpus/release identity，需要 ACL、发布、检索和历史兼容回归。
- 适用条件：方案 A 的候选均不能形成合理 case，且新增规则本身有独立产品价值。
- 风险：最容易滑向“为了测试造语料”；必须保留审查先于首次 retrieval 的证据。

#### 建议与确认时点

- 建议：先执行方案 A；只有明确触发条件成立才重新提交方案 B 的具体文档与 ACL。
- 建议理由：B0 要观察真实底座，不是制造一个必失败的玩具题。
- 用户确认前允许推进：只读语义审查和候选题/gold 草案。
- 用户确认前禁止推进：运行正式首次 retrieval、改 top-k/metadata、修改知识原件或发布 release。
- 需要确认的时点：M42-C 首次 retrieval 前；方案 B 另需二次确认具体 release/ACL。
- 重开决策的条件：预注册候选全部一次取全或 gold 经业务审查不成立。

### G4：Hybrid operator 演进方向

#### 方案 A：新增 versioned `refund_change_and_policy` operator（已确认）

- 做法：保留 legacy `refund_reason_and_policy` v1；新增 operator 语义只冻结“比较期/指标/分解维度的 SQL requirement + 适用政策 Document requirement + 双 Evidence required”，具体问题由未来 TaskState 投影，不再写死 6 月或“退款原因排名”。
- 影响：M38 fixture 和旧 Router 不变，M44 可消费真实 T1–T4 TaskState；兼容矩阵能明确哪个 family 使用哪个 operator。
- 适用条件：接受两个 operator 并存，agent family 显式选择新版本。
- 风险：B0 只能冻结语义，不能用未实现 TaskState 宣称新 operator 已可执行。

#### 方案 B：原位泛化 `refund_reason_and_policy` v1

- 做法：修改现有 operator 的 branch question/字段，使其接受时间、比较和维度。
- 影响：类目更少，但会改变 M38 legacy fixture 和历史语义，迫使旧 artifact/断言重解释。
- 适用条件：只有能证明旧 operator 从未构成稳定合同、且可无损迁移时才成立；当前证据不支持。
- 风险：静默破坏 legacy family，与 Phase 4B runtime isolation 合同冲突。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：新增 versioned operator 能保持 legacy 回归，又为真实任务状态留出小 interface。
- 用户确认前允许推进：写 operator semantics 和兼容矩阵草案。
- 用户确认前禁止推进：修改 M38 Router/fixtures、接新 Graph 或宣称 T4 已执行。
- 需要确认的时点：M42-A/C 冻结合同前。
- 重开决策的条件：M43 TaskState 证明该 operator interface 仍包含退款专用、无法泛化的字段。

### G5：新 sealed decision reserve 的来源与规模

#### 方案 A：同一 immutable external corpus 上新编 60 题（已确认）

- 做法：在不看任何新 Pipeline/Subgraph 结果的前提下，从冻结 corpus 独立编写并双重审核 60 题及 gold；先按 source type、文档长度和 content identity 稳定抽样 source pool，优先排除现有 180 题 gold 文档并执行题面近重复检查，再冻结 `20 basic single-document + 20 core（至少 8 multi-document）+ 20 hard multi-document`。manifest 密封后，B3 只能看 action-level dev/historical 证据，B4 到预定时点才首次解封 reserve 运行结果。
- 影响：与 M34 historical regression 共享 corpus，便于控制 corpus 变量；新 question/gold identity 能恢复较强的默认决策证据。
- 适用条件：能完成 60 题 gold 复核和访问审计，且题目不复制现有 180 题。
- 风险：编题/复核成本高；作者会看 source/gold，但不能看候选运行结果，账本必须区分两者。

#### 方案 B：同 corpus 新编 36 题的预算版 reserve

- 做法：每个 difficulty 12 题；source pool、排除/去重、双重 gold 审核和污染纪律与 A 相同，core 至少 4 道、hard 12 道为 multi-document。
- 影响：人工与 provider 成本较低，但动作触发和错误排除的统计稳定性更弱，默认切换结论需要更保守。
- 适用条件：60 题 gold 审核超出当前阶段预算，且接受较弱证据等级。
- 风险：少数题可能主导结论；B4 更可能只能得到 experimental-only 而非默认切换证据。

#### 建议与确认时点

- 建议：方案 A；M42 只创建/密封，不运行 reserve。
- 建议理由：Phase 4B 的 Subgraph 默认决策是长期选择，60 题与现有 dev 规模对称，能覆盖两类动作和多文档失败。
- 用户确认前允许推进：题源可行性、重复检测和 gold rubric 原型。
- 用户确认前禁止推进：查看任何 reserve candidate 输出、用 reserve 选动作/Prompt/参数或运行 provider。
- 需要确认的时点：M42-E 创建 manifest 前。
- 重开决策的条件：题源去重后不足 60，或 gold 复核成本/质量不达门。

### G6：大 artifact 的不可变保存位置

#### 方案 A：项目外版本化 immutable store + 仓库 manifest（已确认）

- 做法：在项目外数据根建立独立 `phase4b-agent-eval/v1.0.0`（最终绝对路径在实施前确认）；保存 reserve、大 execution artifact 和访问账本，仓库只提交 identity、SHA-256、安全汇总和必要失败切片。
- 影响：不会把正文/大 context 推入 Git，也不依赖 `.agent_work/temp/` 长期存在；实施时需要对项目外目录的明确写入授权。
- 适用条件：沿用 M34 external dataset 的项目外资产纪律。
- 风险：跨机器需要 manifest 指引和缺资产 fail-closed；备份/权限/清理需写清。

#### 方案 B：仓库内只保存全量脱敏 artifact

- 做法：所有材料强制裁剪为仓库可提交的小 JSON，只保存 Evidence coordinates/安全投影，不保存正文或 rows。
- 影响：迁移简单，但可能无法在 B3/B4 复核真实 context/action 失败；大规模后仍会膨胀 Git。
- 适用条件：能证明所有 required/review 都不依赖被裁掉的上下文，且总量稳定很小。
- 风险：为省存储丢失可复核证据，或后续又把大材料塞回 `.agent_work/temp/`。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：它满足 roadmap 的长期可复核与数据最小化要求，也与现有 external corpus 资产管理一致。
- 用户确认前允许推进：manifest/schema 和安全投影设计。
- 用户确认前禁止推进：在项目外创建目录或写入 artifact；把正文、rows、Thought 提交仓库。
- 需要确认的时点：M42-E 实际创建存储前。
- 重开决策的条件：项目外存储无法获得授权，或出现明确的组织级 artifact 平台可替代本地目录。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 profile identity | 同 recipe 重建两次；篡改 recipe/content/config；未知 profile | 两次 identity/事实完全一致；任一漂移和未知 profile 执行前失败 | 必须完成 |
| C1 业务 oracle | SQLite 真实 SQL 分别聚合 7/8 月金额、原因、渠道、商品和宽表对账 | exact facts 命中；各分解守恒；负数冲销保留；星型/宽表一致 | 必须完成 |
| C1 legacy 隔离 | 显式 legacy profile 跑 M1/M27 seed 相关聚焦回归 | 旧固定事实、oracle label/identity 和 artifact 解释不变；无隐式新 profile | 必须完成 |
| C2 北极星 catalog | schema/identity 测试 + 人工逐 turn 审查 | T1–T5 均含 delta 类别、Evidence/失效、route/action、四轴、assertion 和安全身份；无领域专用 state schema | 必须完成 |
| C2 最小 caller | 双角色正向及缺 `ops`、缺 `customer_service`、wrong active role、owner/tenant/ACL 变化反例 | 只在正确权限下分别调用 SQL/Knowledge；拒绝发生在 Tool 前或授权层且无侧信道 | 必须完成 |
| C3 business RAG case | gold-first 审计 + 当前默认 deterministic retrieval 一次 | gold 合理、题面自然、无测试参数；Observation 原样保留；一次取全不伪装 recovery | 必须完成 |
| C3 Hybrid 兼容 | operator schema/compatibility tests；M38 原合同回归 | 新语义不含固定 6 月/排名；legacy v1 结果与预算不变 | 必须完成 |
| C4 skeleton closed-world | 正向 completed + 缺/多/重复 turn/execution/assertion、顺序/identity/hash 篡改 | 合法 artifact 可复算；所有非法形状拒绝 completed | 必须完成 |
| C5 family/API 兼容 | compatibility matrix contract tests | legacy initial/resume/follow-up 与 future task 类别互斥；旧 family 预算/字段不变；不靠空字段猜 family | 必须完成 |
| C5 action 三层语义 | action card schema 和不适用/无 Observation/stop 反例 | global catalog、applicability、eligible set 可区分；未准入动作不能执行；stop 始终合法 | 必须完成 |
| C6 reserve 密封 | split/去重/gold/manifest/hash/访问状态机测试 | reserve 在 B3/B4 前无运行结果访问；污染后自动退出 decision set；M34 标 historical | 必须完成 |
| C6 artifact retention | 外部资产缺失/篡改与仓库 manifest 对账 | identity/hash 不符 fail closed；仓库无正文、rows、凭据、Thought；temp 不是唯一事实源 | 必须完成 |

聚焦测试顺序：identity/profile → seed/oracle → caller/RAG/Hybrid → Agent artifact → compatibility/action → reserve/retention → 集成 rehearsal。

全量回归范围：M1/M27 seed/oracle、M31–M34 Knowledge/Evidence、M35–M38 Harness/thread/follow-up/Hybrid、M40 assurance、M41 RAG Eval contracts，以及全仓 deterministic pytest。预计超过 2 分钟的全量验证按 `AGENTS.md` 进入后台并写 checkpoint/log/exit/done。

不属于本模块的验证：真实 LLM、remote embedding/Milvus、LangFuse、M34/M41 provider Eval、sealed reserve A/B、RAG recovery action 收益、跨重启/multi-worker、Context Compact 和 Phase 4B 完整 T1→T5 执行。

历史 artifact 和既有合同只读：M27/M31–M41 artifact 不补字段、不改签、不重跑制造 M42 分数；M34 60/120/180 只作为 historical regression 与失败证据，不承担新 reserve 默认裁决。

## 9. 依赖与交付物

### 依赖

- Phase 4 已完成的 `/api/query`、turn seam、Harness、SQL/RAG 深 Tool、M38 Hybrid、四轴、Evidence/citation、caller/ACL/outbound 和 Trace。
- 当前 14 表 schema、`net_refund_amount` 指标、seed builder、业务 22-entry active release 和 external immutable profile。
- M27 EvalOps 与 M41 RAG Eval 的一次执行、resolved runtime、closed-world、review hash 纪律。
- G1–G6 已确认采用方案 A；项目外存储仍需要在实际创建目录时取得该绝对路径的写入授权。

### 交付物

- Phase 4B versioned seed/oracle profile、manifest、真实 SQL oracle 与 legacy compatibility view。
- 北极星 canonical/extended/非 happy-path catalog 和 capability matrix。
- 最小双角色 demo caller fixture 与跨 turn 权限矩阵。
- business RAG gold-first case、首次 Observation 和 Hybrid operator 语义方向。
- `phase4b-agent-scenario-v1` contract/artifact skeleton、closed-world validator 和安全报告。
- legacy/agent runtime 与 API/state compatibility matrix 初版、action card schema。
- sealed decision reserve manifest、污染/访问账本和 artifact retention manifest。
- M43/B1 与 M45/B3 可直接消费的 deterministic fixtures；实现过程记录进入 `docs/notes/m42-notes.md`，收工后按项目规则更新 state/changelog。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：自然语言 TaskDelta/TaskState、顶层 Loop、RAG action campaign/Subgraph、durable state、Compact、真实 provider 与默认切换。
- 下一模块可直接消费的产物：M43/B1 消费 seed/caller/sequence/family/compatibility skeleton；M44/B2 消费 Hybrid 方向和 action card schema；M45/B3 消费 business Observation、historical failure 和 sealed reserve protocol；M46/B4 在预定门后消费 reserve；M47/M48 消费 sequence/state/context identity。
- 后续需要根据真实失败重新规划的内容：B3 的具体 action catalog、business case 是否形成 recovery、external failure 的动作迁移性、B4 的 experimental/default/fallback 结论。
- 可能存在的风险：新 seed 分解过度为北极星定制；自然问法在小 corpus 仍一次取全；60 题 reserve 的 gold 审核成本；项目外 artifact 的权限与可迁移性；skeleton 过早冻结 B1 字段。对应控制分别是 profile 隔离+非 happy-path、如实记录 Observation、有界题集/审查、manifest/hash、只冻结 interface 不冻结 TaskState 字段。
- 强制开工条件：M43 只能在 C1/C2/C4/C5 required 通过后开工；M45 只能在 C3 Observation 和 C6 reserve protocol 密封后开工；M46 仍须满足 B3 两种合格动作和至少一个 runtime/corpus 的 Observation-driven 选择门，M42 不会提前满足或降低该标准。
- 最终验收标准：M42 只以 B0 第 8 节 required 全部通过宣称 B0 完成；Phase 4B 对自然多轮、Loop、两种 RAG 动作、durable state、Compact 和完整 Agent Eval 的最终目标仍以 M43–M48 及阶段 Definition of Done 为准。

## 11. 开工条件

- 开工前无需确认：B0 对应 M42；同一 `/api/query`；legacy/agent family 隔离；旧 artifact 只读；M34 120 题降为 historical regression；B0 零真实 provider；action catalog 三层语义和 `stop` 永远可用。这些已由 roadmap/state/用户本轮模块映射确定。
- 已确认：G1 seed/profile/exact facts、G2 最小 caller、G3 business RAG case、G4 Hybrid operator、G5 60 题 reserve、G6 项目外 immutable store 均采用方案 A。
- 实施中仍需单独授权或重开：G6 实际项目外绝对路径及写入授权；若 G3 的 A 命中重开条件并拟新增 release，需对具体文档内容与 ACL 二次确认；其余只有命中对应重开条件才重新提请决策。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得通过缩减最终能力、改写 legacy assertion、制造 RAG 失败或解封 reserve 继续施工。
