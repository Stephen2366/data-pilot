# M41 Phase 4 RAG 真实链路 EvalOps 与诊断体系开发计划

> 能力里程碑：Phase 4 Eval 补完；补齐 M35–M40 完成产品 Harness 接线后一直缺失的真实 LLM RAG 端到端评测与诊断闭环
>
> 主要问题：当前只有 M31–M40 deterministic contract Gate 和绕过产品 Harness 的 M34 external AnswerFlow Eval，无法像 M27 Text2SQL 一样对真实 RAG 产品链路进行一次执行、分层评分、失败归因、复核和可比运行管理
>
> 路线边界：本模块属于 **Phase 4 RAG Eval 缺口收口**。M41 只是顺延模块编号，不表示执行 Phase 4B；本计划不建设 TaskState、TaskDelta、Agent Loop、Agentic RAG Subgraph、durable checkpoint、Context Compact 或 Phase 4B Agent Scenario Eval。

## 1. 模块定义与范围判断

M31–M40 已完成可信 Knowledge/RAG、Evidence/citation、顶层 Harness、有限 turn/follow-up、Hybrid 与技术 assurance，但这些模块对 RAG 的验证主要是 deterministic contract。M34 虽然真实调用过 Qwen Composer，却直接运行 external `RAGAnswerFlow`，没有经过 `/api/query → turn → Router → Harness → RAG Tool → AnswerFlow → API/Trace` 产品链路。

M41 只闭环一个主要问题：建立一套与 M27 Text2SQL EvalOps 纪律对齐、但采用 RAG 专属 failure funnel 和质量指标的 **Phase 4 RAG 真实链路 Eval**。模块完成后，用户能够：

- 用稳定 CLI 选择 smoke/core/diagnostic/reliability 等 RAG 场景；
- 让每个 Scenario 恰好执行一次真实产品 RAG 链路，并使用真实 Qwen Composer；
- 从同一份 ExecutionEvidence 判断失败发生在 retrieval、selection、generation context、Composer/support、citation、answer correctness/completeness、Harness/API/Trace 或 provider；
- 获得 completed artifact、Markdown report、逐题 triage 和可校验来源的人工 review bundle；
- 区分 deterministic 安全 Gate、真实模型质量、external unavailable 与人工证据不足；
- 在不修改默认业务 runtime 的前提下形成可复现的真实 RAG 基线与后续 A/B 入口。

本模块规模虽大于单个 scorer，但这些能力共享同一个“一次真实执行 → 多视图消费”的核心 interface；若拆成多个模块，会再次出现 runner、artifact、triage 与 review 各自定义证据、甚至重复调用真实链路的问题，因此应作为一个完整 EvalOps 闭环交付。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| `/api/query` 已统一进入 turn seam 和 M35 Harness | 具备真实产品链路 Eval 的执行入口，但现有 RAG Eval 没有使用该入口 | `app/api/query.py`、`engine/harness/graph.py` |
| Harness 的 RAG adapter 默认构造 `RAGAnswerFlow()` | 默认 Composer 是 deterministic，不能评价真实 LLM 回答质量 | `engine/harness/adapters.py`、`engine/rag/answer_flow.py` |
| M35 Router 与 M38 Hybrid Synthesizer 均为 deterministic 默认 | M35–M40 contract 证明控制正确，不证明开放自然问法或真实生成质量 | `engine/harness/router.py`、`engine/harness/hybrid.py` |
| M31 `phase4-v1`、M32 retrieval、M33 answer/citation、M35–M40 Harness/assurance artifact 已存在 | 它们是安全/控制回归锚点，不得被改写或混算为真实 RAG 质量分数 | `eval/phase4_contracts.py`、`eval/rag_*_contracts.py`、`eval/harness_*_contracts.py` |
| M34 full Answer Eval 真实调用 Qwen，但脚本直接构造 external `RAGAnswerFlow` | 没有覆盖 Router、Harness、turn、API、Trace 和业务 22-entry release | `scripts/run_m34_answer_eval.py` |
| M34 已记录 retrieval coverage、cited-gold coverage、support reject、usage 和 exact-fact 下限 | 能定位部分 external 失败，但缺 selected/generation-visible 全漏斗、可信 correctness、正式 triage/review/selector/Gate | `engine/rag/enterprise_answer_eval.py`、`docs/state/eval-baselines.md` |
| M27 已具备 selector/suite、run identity、checkpoint、completed artifact、Gate、triage 和 review bundle | 可复用 EvalOps 纪律，但 SQL assertion 与 RAG scorer 不能共用业务语义 | `eval/run_eval.py`、`eval/contracts.py`、`eval/review.py`、`eval/triage.py` |
| 当前业务 Knowledge 默认是 22-entry release + deterministic lexical retrieval | 真实业务 RAG Eval 必须冻结 release/corpus/adapter/recipe/caller/Composer，而不能借 M34 external profile 代替 | `docs/state/rag-current-state.md` |
| 当前无正式 RAG answer correctness 长期基线 | `answer_status=complete`、citation valid 或 gold document recalled 都不能回答“答案是否正确完整” | `docs/notes/phase4-rag-capability-status.md`、`docs/state/eval-baselines.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 实际 Agent 输出与 context 固化后再评分 | `agentic-rag-for-dummies/notebooks/evaluation.ipynb::query_rag / assert_saved_outputs_match_dataset / score_answer` | 保存实际 answer/context，验证保存材料仍匹配 dataset，再执行 answer/context 指标 | 每题只运行一次产品链路；ExecutionEvidence 保存实际安全投影、Evidence coordinates、Trace 与 provider attempt，scorer/review 只读该证据 | notebook 简单平均、CSV 作为唯一事实源、RAGAS 直接决定 required Gate、失败样本跳过后不进入分母 |
| retrieval 与 answer evaluator 分层 | `DB-GPT/.../rag/evaluation/retriever.py::RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator`；`answer.py::AnswerRelevancyMetric / LLMAnswerEvaluator` | retrieval 和 answer 使用不同指标与输入 | 建立 retrieval→selection→generation-visible→support→citation→answer funnel；每层独立 observed/not_observed | scorer 为评分重跑 retriever/answer operator、空结果统一记 0、单个 LLM 0–5 分冒充客观正确性 |
| Eval 生命周期与一次执行纪律 | DataPilot `eval/contracts.py`、`eval/run_eval.py`、`eval/review.py`、`eval/triage.py` | versioned RunSpec、resolved runtime、checkpoint、completed artifact、Gate、review 来源哈希 | 提取可复用的 EvalOps 语义，建立独立 RAG contract family；共享基础设施时保持 M27 artifact/schema 不变 | 把 SQL Scenario/assertion 强塞给 RAG、向 M27 历史 artifact 补字段、用同一个总分混算 SQL/RAG |

参考结论：外部项目只提供“保存真实输出再评分”和“retrieval/answer 分层”的局部证据。M41 的一题一次、四轴、`not_observed`、closed-world、ACL/outbound、Evidence/citation、review 与运行身份仍以 DataPilot 现有合同为准。

## 4. 目标、优先级与非目标

### 模块完成状态

M41 完成后，项目存在独立版本化的 Phase 4 RAG Eval family。它通过显式 eval runtime adapter 给现有产品 Harness 注入真实 Qwen Composer，执行业务 RAG 请求并形成共享 ExecutionEvidence；随后在零额外产品调用的前提下生成 funnel assertions、质量视图、Gate、triage、report 和人工 review bundle。

### 必须完成

- 建立真实 RAG Eval CLI、catalog、selector/suite、run/checkpoint/artifact/report 生命周期。
- 主执行路径必须经过 `/api/query` 对应的真实 turn/Harness/RAG adapter 语义，不得退化为仅直接调用 `RAGAnswerFlow`。
- 为 Eval 显式注入真实 Qwen Composer，但不修改普通 API 的 deterministic 默认。
- 每个 Scenario/replicate 恰好一次产品链路执行；scorer、triage、report、review 不得重跑 retrieval 或 LLM。
- 建立 retrieval、selected、generation-visible、Composer/support、citation、answer correctness/completeness、API/Harness/Trace/provider failure funnel。
- 建立 required/advisory/not_observed、passed/failed/inconclusive Gate，并保持外部不可用与语义失败分离。
- 建立逐题 triage 和来源带 SHA-256 的人工 review bundle。
- 冻结 runtime identity、catalog/selector identity、release/corpus/adapter/recipe/Composer/policy/caller identity 和 provider usage。
- 保持 M27、M31–M40、M34 历史 artifact 不变且分账。
- 更新 runbook，使其能像 Text2SQL 一样说明选择、运行、等待、复核和解释 RAG Eval。

### 建议完成

- 提供两个 completed artifact 的离线 compare，拒绝不可比 runtime/catalog/protocol。
- 把 M34 completed artifact 通过只读 importer 投影为 historical external 诊断视图，验证新 funnel/report 能消费旧证据；不重跑 180 题。
- 为未来 semantic/retrieval/Composer 单变量 A/B 预留小 interface，但不在本模块切默认。

### 条件触发

- **触发条件**：用户明确授权执行某个真实 RAG selector/suite。
- **允许动作**：按同一 run ID、同一 runtime、同一题集执行恰好一次；允许写 checkpoint、artifact、report、trace 和 provider usage。
- **未触发时**：只完成 deterministic runner/adapter/scorer/CLI 测试，不调用真实 Qwen，不登记真实长期基线。

- **触发条件**：deterministic/reference/manual correctness 无法覆盖某类自然答案，且用户确认引入 LLM-as-Judge 实验。
- **允许动作**：增加独立 advisory judge adapter、冻结 rubric/model/prompt identity，并与 answer provider 分账。
- **未触发时**：正确性依赖 deterministic oracle 下限与人工 review；不让 Judge 进入 required Gate。

### 明确非目标

- 不建设或执行 Phase 4B、Agent Loop、Agent Scenario、TaskState/TaskDelta、RAG Subgraph、durable checkpoint 或 Context Compact。
- 不改默认 Router、默认 business Composer、默认 lexical retrieval、active Knowledge release 或 M34 external pointer。
- 不运行新的 M34 180 题 full Answer Eval，不重新解封任何题集。
- 不把 M34 external benchmark 当成业务 RAG 产品链路替代品。
- 不以 RAGAS、LLM Judge 或单一综合分替代 typed assertions 和人工复核。
- 不建设通用独立 Eval 平台；只交付 DataPilot Phase 4 RAG EvalOps-lite。
- 不评价开放 Hybrid 质量；M38 Hybrid 仅作为受影响 deterministic 回归，真实 Hybrid Eval 另立计划。

## 5. 关键合同

### C1：真实产品链路一次执行合同

- 输入：版本化 RAG Scenario、resolved eval runtime、可信 fixture caller、唯一 run/scenario/replicate identity。
- 成功输出：一份不可变 `RAGExecutionEvidence`，包含同一请求的 turn/Harness/result、安全 Trace、RAG diagnostics、Evidence funnel、公开回答/citation 和 provider attempt/usage。
- 失败语义：安全拒绝、证据不足、合同拒绝、provider unavailable、Harness/API/Trace 不一致分别记录；任何失败仍形成可审计 execution evidence。
- 必须保持的不变量：每 Scenario/replicate 恰好一次产品执行；评分、报告和复核零产品调用；业务 API 默认行为不因 Eval 注入而变化。
- 本模块不冻结的实现细节：具体类名、文件拆分、HTTP TestClient 还是共享 in-process query seam；但必须证明执行语义与 `/api/query` 同源。

### C2：显式真实 Composer runtime 合同

- 输入：eval-only runtime profile、Qwen model/timeout/retry/outbound 配置、business Knowledge release。
- 成功输出：resolved identity 明确记录 Composer/model/provider/policy/release/corpus/retrieval recipe，并由 Harness RAG adapter实际使用。
- 失败语义：缺 key、出站拒绝、timeout/network/provider/schema/support contract 均稳定分类，不能回退 deterministic Composer 后冒充真实结果。
- 必须保持的不变量：普通 API 继续使用当前默认；真实 Composer 只在显式 Eval runtime 中注入；retry 默认 0；不得静默切 external profile。
- 本模块不冻结的实现细节：provider client 内部组织和 prompt 文本；正式运行前必须把其 identity 固化进 artifact。

### C3：RAG failure funnel 合同

- 输入：C1 的共享 ExecutionEvidence 和 Scenario gold/reference requirement。
- 成功输出：按层投影 retrieved、selected、generation-visible、Composer/support、cited、answer correctness/completeness 及 Harness/API/Trace/provider 状态。
- 失败语义：某层缺证据时该层为 `not_observed` 并记录原因；上游失败不得自动把所有下游层判错。
- 必须保持的不变量：support 是回答诊断层，不新增 EvidenceLedger stage；retrieval/citation/complete 均不能单独冒充 correctness。
- 本模块不冻结的实现细节：具体 correctness 自动规则集合；规则必须版本化并允许人工复核补充。

### C4：RAG Scenario catalog 与 selector 合同

- 输入：canonical Scenario catalog 和 selector/suite policy。
- 成功输出：确定的 selected scenario、replicate、required/advisory/excluded assertion 集合及其 identity。
- 失败语义：重复 Scenario、未知 assertion、非法 selector、suite/explicit 混用、未冻结 gold/reference 或身份缺失时在运行前失败。
- 必须保持的不变量：smoke/core/diagnostic/reliability 是选择与执行协议，不复制题面形成多个事实源；business 与 external 分集不能混算。
- 本模块不冻结的实现细节：首版题数；真实调用前题集与预算必须单独提交用户确认。

### C5：artifact、生命周期与 closed-world 合同

- 输入：RunSpec、selected catalog、逐题 checkpoint 和所有 ExecutionEvidence/assertion。
- 成功输出：只有全部计划 execution 终态闭合后才生成 completed artifact 和 Markdown report。
- 失败语义：running/interrupted/failed 不生成 completed artifact；缺题、重复 attempt、漏 assertion、identity 漂移、checkpoint 非法前缀或 hash 不符均拒绝。
- 必须保持的不变量：同一授权只对应一个 run ID；前台等待超时不等于 run 结束；不存在 completed artifact 时才允许在明确条件下讨论新 run。
- 本模块不冻结的实现细节：checkpoint store 的内部文件组织；首版仍可使用 `.agent_work/temp/`，长期安全 artifact 进入 `eval/reports/`。

### C6：评分、Gate 与 `not_observed` 合同

- 输入：completed 或逐题 ExecutionEvidence、typed assertion specification。
- 成功输出：`eligible = passed + failed + not_observed`，required Gate 为 passed/failed/inconclusive；质量视图按 funnel 分层展示。
- 失败语义：provider/trace/evidence 不可用归 `not_observed`；观察到的不合格 answer/support/citation 才能记 failed；人工待定不伪装为自动通过。
- 必须保持的不变量：deterministic contract Gate 与真实质量视图分账；advisory 不改变 required Gate；不产生跨 SQL/RAG/M34 的综合总分。
- 本模块不冻结的实现细节：是否展示辅助均值；任何均值都不能覆盖分母和失败切片。

### C7：triage 与人工 review 合同

- 输入：completed artifact 和原始 checkpoint 来源。
- 成功输出：逐题失败层/子类、建议复核原因，以及带 artifact/checkpoint SHA-256 的独立 review bundle。
- 失败语义：来源缺失、被改写或 hash 不符时拒绝复核；没有 answer/context 时只能标 insufficient evidence。
- 必须保持的不变量：review 不修改自动 artifact、分母或 Gate；verdict 分类与自动结果并列保存；普通质量题不能仅凭安全拒绝判正确。
- 本模块不冻结的实现细节：首版人工 verdict UI；CLI + JSON/Markdown 足够。

### C8：历史与可比性合同

- 输入：两个 completed RAG EvalRun，或只读 M34 historical artifact。
- 成功输出：相同 catalog/protocol/runtime/gold/scorer identity 下的分层 compare；M34 只进入 external historical 视图。
- 失败语义：release、corpus、adapter、recipe、Composer、model、prompt/policy、预算、题集或 scorer identity 不同且未显式标为候选条件时拒绝直接升降比较。
- 必须保持的不变量：不改写 M27、M31–M40、M34 artifact；不因 importer 存在而把 M34 声称为产品 Harness E2E。
- 本模块不冻结的实现细节：compare 报告版式。

## 6. 工作切片与执行顺序

### M41-A：真实差距审计与 Eval contract 冻结

- 优先级：必须完成
- 依赖：M27 EvalOps、M31–M40 contracts、M34 artifacts、当前 API/Harness/RAG diagnostics。
- 实施内容：冻结 Scenario、ExecutionEvidence、runtime identity、funnel、assertion、Gate、triage/review 和可比性 schema；画清 deterministic/real-provider/business/external 四类边界。
- 关键合同：C1、C3、C4、C6、C8。
- 交付物：独立 contract family、catalog/schema 草案、能力矩阵和反例测试。
- 验证方式：schema/identity/closed-world deterministic tests；审查没有任何 scorer 需要重跑产品链路。
- 完成门：所有后续切片只消费 C1 Evidence，不再各自定义运行结果。

### M41-B：eval-only 真实 Composer 注入与产品执行 seam

- 优先级：必须完成
- 依赖：M41-A；现有 caller resolver、HarnessRuntime、RAGToolAdapter、AnswerFlow diagnostics。
- 实施内容：建立显式 eval runtime adapter，把真实 Qwen Composer 注入业务 RAG 产品链路；抽取与 `/api/query` 同源的可测试执行 seam并保存安全 Trace。
- 关键合同：C1、C2。
- 交付物：real-provider adapter、in-memory fake adapter、产品执行器、provider failure 分类。
- 验证方式：fake provider 证明成功/timeout/network/schema/support reject；API response、turn result、Trace、ExecutionEvidence 同源对账。
- 完成门：测试可证明 Eval 走过 Router/Harness/RAG Tool，且普通 API 默认仍为 deterministic。

### M41-C：RAG catalog、selector 与生命周期

- 优先级：必须完成
- 依赖：M41-A/B。
- 实施内容：建立 canonical business RAG catalog、smoke/core/diagnostic/reliability selector、RunSpec、checkpoint、resume、completed artifact 和 CLI。
- 关键合同：C4、C5。
- 交付物：版本化 catalog/selectors、runner CLI、manifest/checkpoint store、artifact writer/validator。
- 验证方式：一次执行计数、非法 selector、重复 run、非法前缀、running/interrupted/failed/completed 和 artifact 篡改测试。
- 完成门：fake provider 下可完整跑完所有生命周期，不调用真实模型。

### M41-D：failure funnel、scorer、Gate 与报告

- 优先级：必须完成
- 依赖：M41-C。
- 实施内容：从共享 Evidence 投影 retrieval/selection/generation-visible/support/citation/correctness/completeness 和运行故障；生成 assertion views、Gate、Markdown report。
- 关键合同：C3、C6。
- 交付物：RAG scorer registry、funnel projector、Gate projector、report renderer。
- 验证方式：构造每个失败层的反例；验证上游 unavailable 不会污染下游为 semantic failed；验证分母恒等式。
- 完成门：同一题可唯一定位主要失败层，同时保留多层观察事实。

### M41-E：triage、review 与 compare

- 优先级：必须完成
- 依赖：M41-D。
- 实施内容：生成逐题 failure triage、来源哈希 review bundle、人工 verdict 分类和 completed run compare。
- 关键合同：C7、C8。
- 交付物：review/verify CLI、triage JSON/Markdown、compare 报告。
- 验证方式：来源篡改、insufficient evidence、自动通过误通过抽样、不可比 runtime 拒绝测试。
- 完成门：人工复核不修改自动 Gate，且任何比较都能说明是否严格可比。

### M41-F：M34 historical 兼容视图与 runbook

- 优先级：建议完成
- 依赖：M41-D/E。
- 实施内容：只读导入现有 M34 completed artifact/manifest，生成 external historical funnel/边界说明；重写 runbook 的 RAG Eval 选择、运行、等待、结果、review、compare 和授权章节。
- 关键合同：C8。
- 交付物：historical importer/报告、完善后的 runbook。
- 验证方式：零 Tool/LLM 调用；hash/identity 不符失败；文档命令与 CLI help 对账。
- 完成门：runbook 不再把 deterministic contracts、M34 direct AnswerFlow 和产品 RAG E2E 混为一谈。

### M41-G：首次真实 Qwen 精确运行

- 优先级：条件触发
- 依赖：M41-A 至 M41-F deterministic Gate 全部通过；用户确认 selector、题数、预算、run ID 和当前 provider 配置。
- 实施内容：先执行一次 smoke；检查 completed/inconclusive/failed、usage、funnel 与 review 材料。是否继续 core/reliability 必须基于 smoke 证据重新确认，不自动扩大。
- 关键合同：C1–C8。
- 交付物：真实 completed/inconclusive artifact、report、triage、review bundle 和状态文档证据。
- 验证方式：真实 provider 单次执行与人工逐题复核。
- 完成门：至少形成一条经过产品 Harness 的真实 business RAG execution；若 provider unavailable，则如实形成 inconclusive 证据，不以重跑掩盖。

## 7. 决策门

### G1：首版 answer correctness 裁决方式

#### 方案 A：deterministic oracle 下限 + 强制人工 review

- 做法：结构化 required terms、允许/禁止 claims、reference answer/evidence requirement 提供自动下限；自然语义 correctness/completeness 进入带来源哈希的人工 review。
- 影响：结论保守但可解释，不增加第二个真实 judge provider。
- 适用条件：首版业务题规模有限，用户可以复核自动失败、高风险题和通过抽样。
- 风险：人工成本较高，不能即时产生大规模语义分数。

#### 方案 B：增加独立 LLM-as-Judge advisory

- 做法：使用与 answer model 分离的 judge adapter，冻结 rubric/prompt/model identity，只生成 advisory correctness/faithfulness/completeness。
- 影响：诊断覆盖更广，但增加费用、波动、自评偏差和 judge failure 分类。
- 适用条件：题量扩大、人工复核成为瓶颈，并且用户明确授权 judge 出站。
- 风险：容易把 judge 分数误写成 required truth；同 provider/同模型自评会放大偏差。

#### 建议与确认时点

- 建议：首版采用方案 A；先把产品链路、Evidence、funnel、review 和运行生命周期做正确。
- 建议理由：当前首要缺口是“没有真实产品 RAG 证据”，不是“少一个漂亮的总分”；人工 review 比未经验证的 Judge 更适合建立首条可信基线。
- 用户确认前允许推进：完成 A 的全部 deterministic 实现与测试。
- 用户确认前禁止推进：调用 Judge、把 Judge 结果纳入 required Gate。
- 需要确认的时点：M41-E 完成、准备真实运行前。
- 重开决策的条件：真实 core 题量使人工复核成本明显不可接受，或需要规模化 candidate A/B。

### G2：首次真实运行范围

#### 方案 A：business RAG smoke 后停门

- 做法：先运行少量业务 RAG 场景，证明完整产品 Harness + Qwen + funnel + review。
- 影响：费用低、定位清晰；不会立即形成完整业务质量基线。
- 适用条件：首条新 runner 尚未获得真实 provider 证据。
- 风险：smoke 不能外推整体质量。

#### 方案 B：同轮直接运行 business core

- 做法：deterministic Gate 后直接执行完整 core。
- 影响：更快获得范围性结果，但首个真实运行若存在接线/出站问题会扩大无效调用。
- 适用条件：已有可信 remote smoke 或用户愿意承担一次完整运行风险。
- 风险：费用和无效调用更高，问题定位更慢。

#### 建议与确认时点

- 建议：方案 A；smoke 结果检查后再决定是否授权 core/reliability。
- 建议理由：M35–M40 从未跑过真实 RAG 产品 E2E，首轮应先验证 execution identity 和 failure funnel。
- 用户确认前允许推进：实现和 deterministic 验证。
- 用户确认前禁止推进：任何真实 Qwen RAG Eval。
- 需要确认的时点：M41-F 完成后提交准确题数、调用数和费用预估时。
- 重开决策的条件：用户明确授权 core 或 smoke 已经证明链路稳定。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 一次产品执行 | fake provider + API/Harness/Trace 聚焦测试 | 每 Scenario/replicate 恰好一次；所有下游只读共享 Evidence | 必须完成 |
| C2 real Composer 注入 | fake success/timeout/network/schema/support tests | Eval 使用显式 Composer；普通 API 默认不变；失败不回退 | 必须完成 |
| C3 failure funnel | 每层独立反例 | retrieved 到 answer 各层可观察；上游失败正确投影下游 not_observed | 必须完成 |
| C4 catalog/selector | catalog、selector、replicate 测试 | 题面单一事实源；非法组合运行前拒绝；identity 稳定 | 必须完成 |
| C5 lifecycle/artifact | running/interrupted/failed/completed、resume、tamper tests | 仅 closed-world completed 生成长期 artifact/report | 必须完成 |
| C6 scorer/Gate | 分母、required/advisory/unavailable tests | 恒等式成立；external unavailable 导致 inconclusive 而非 semantic failed | 必须完成 |
| C7 triage/review | 来源 hash、verdict、缺 evidence 测试 | review 来源可验证且不修改自动结果 | 必须完成 |
| C8 compare/history | comparable/non-comparable、M34 importer tests | 不可比运行拒绝升降；M34 明示为 direct AnswerFlow historical | 建议完成 |
| runbook | CLI help、路径和完整回读 | RAG Eval 有真实选择/运行/等待/复核说明，无不存在命令 | 必须完成 |
| 真实 Qwen smoke | 用户单次授权后执行 | 形成真实产品 Harness execution；成功则 completed，外部不可用则诚实 inconclusive | 条件触发 |

聚焦测试顺序：contracts/schema → runtime injection → once-only execution → lifecycle → funnel/scorers → triage/review/compare → API/Trace 回归。

全量回归至少覆盖：M31–M33 Evidence/RAG、M35–M40 Harness/turn/follow-up/Hybrid/assurance、API/Trace 与 M27 EvalOps；完整仓库 pytest 按项目长时间命令规则在收工阶段执行。

不属于本模块默认验证：真实 M34 180 题重跑、remote embedding/Milvus、LangFuse Cloud、真实 Hybrid LLM、LLM Judge、Phase 4B Agent Scenario。

历史 M27、M31–M40、M34 artifact 全部只读；不得为了适配 M41 回填字段或重新签名。

## 9. 依赖与交付物

### 依赖

- M31–M33 的 trusted caller、Knowledge Tool、Evidence Gate、Composer/citation 与 diagnostics。
- M35–M40 的统一 API/turn/Harness/Trace 产品链路。
- M27 的 EvalRun、checkpoint、Gate、triage、review 和可比性纪律。
- M34 的 external retrieval/Answer artifacts 与真实 provider telemetry 经验。
- `docs/state/runbook.md`、`rag-current-state.md`、`eval-baselines.md` 与 Phase 4 changelog。
- 真实运行时需要可用 Qwen provider、明确出站许可和用户一次精确授权。

### 交付物

- 独立版本化 Phase 4 RAG Eval contract family 与 canonical catalog/selectors。
- 产品链路执行 interface、eval-only real Composer adapter 和 fake adapter。
- RAG ExecutionEvidence、runtime identity、checkpoint、artifact validator、CLI。
- funnel/scorers、Gate、Markdown report、triage、review/verify、compare。
- M34 historical 只读兼容视图（建议项）。
- M41 notes、更新后的 runbook、RAG/Eval state 与 Phase 4 技术历史记录。
- 用户授权后产生的真实 run artifact/report/review（条件项）。

## 10. 遗留与后续

- 本模块完成但刻意不处理：真实 Hybrid LLM Eval、开放 Router 质量、Agentic RAG action recovery、Subgraph、长期多轮与持久状态。
- 下一模块可直接消费：真实产品 RAG failure funnel、业务质量基线、可比较 runtime identity、逐题 triage 和 review 证据。
- 后续需要根据真实失败重新规划：retrieval/selection/context packing、Composer prompt/support、语义 correctness scorer、Judge、rerank/semantic/多文档策略。
- 可能存在的风险：现有 API 安全投影不足以提供完整 scorer 输入时，需要在同源内部 Evidence seam 增加 Eval-only 安全投影；不得通过把 Document 正文写进默认 Trace 解决。
- 若首轮真实运行 external unavailable，只证明 provider/网络不可用；不得登记为 RAG 质量结论，也不得未经新授权自动重跑。

## 11. 开工条件

- 开工前无需确认：M41 只补 Phase 4 RAG Eval；不执行 Phase 4B；不改默认 runtime；先完成所有 deterministic 实现与测试。
- 实施中需要确认：G1 是否引入 advisory LLM Judge；G2 首次真实运行 selector、题数、调用数、预算和 run ID。
- 发现新冲突时：若必须改变默认 Composer、Knowledge release、caller 权限、outbound、正式题集或历史 artifact，按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支，未经用户确认不得继续。
