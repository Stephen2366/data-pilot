# M40 P7 跨路径 Trace 运行身份与阶段保证包开发计划

> 能力里程碑：Phase 4 `P7`；本模块完成 P7 的技术收口切片：把既有 P1–P6 的确定性合同、M39 的严格 no-go 与 SQL/RAG/Hybrid/多轮的真实 Trace 关联为一个可复核的保证包。它不新增业务 Tool、检索策略或 Agent loop。
>
> 主要问题：现有各模块分别证明了安全、取证、回答、Harness、thread 和 Hybrid 合同，但 Trace 的运行身份仍分散在 Tool diagnostics / Evidence 中，且没有一个拒绝“跨合同、跨历史 artifact 拼出表面通过”的 P7 闭合工件。

## 1. 模块定义与范围判断

M39 已按用户确认的方案 A 完成 P6 严格 `no_go`，因此当前正确入口是 roadmap 的 P7，而不是把 M34 的 retrieval/context/Composer 失败重新包装为 Subgraph、rerank 或默认切换。P7 的职责是收口既有能力，不再创造新的大能力。

本模块以“从一条用户可见结果能否安全回查到本轮状态、Evidence、运行身份和已通过的合同”为单一问题，形成可独立演示和验收的闭环。完成后，用户可以用五条固定路径（SQL、RAG、Hybrid、澄清恢复、安全拒绝）展示：响应与 JSONL Trace 由同一 turn 投影、运行身份没有靠猜测补齐、已有合同不能被遗漏/历史结果伪装为当前 P7 通过。

范围适合一个模块：Trace 运行身份、跨路径演示和保证 artifact 必须共享同一份 runtime 事实；若拆开，后者会退化为手工文档拼接。P7 的最终人工验收仍在 M40 `finish-module → finish-docs → 用户人工检查 → accept-module` 后发生，不由自动 Gate 冒充完成。没有预设 M41。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| `TraceRecord` 已保存四轴、route decision、EvidenceRef、Hybrid branch 和 thread lifecycle；`/api/query` 从同一 `AgentTurnResult` 投影响应与 Trace | 主链路事实已经统一，但没有独立、统一的安全 runtime identity 外壳 | `engine/trace/recorder.py::TraceRecord`；`app/api/query.py::_record_trace` |
| SQL runtime identity 写入 SQL Evidence，RAG 的 AnswerFlow / retrieval / release / corpus identity 在安全 diagnostics 中 | Trace 消费者要按 route 猜字段；SQL/RAG/Hybrid 无可比较的 Trace runtime 视图 | `engine/harness/adapters.py::_project_text2sql_result`；`engine/rag/answer_flow.py::AnswerFlowDiagnostics`；`engine/rag/knowledge_tool.py::RetrievalDiagnostics.safe_projection` |
| M31、M32、M33、M35–M38 各有独立 closed-world artifact / Gate；M39 是只读、固定输入的 P6 `no_go` 审计 | 单项通过不等于 P7 需要的全部合同、当前身份和 P6 决策均被完整纳入；不能用 M27 历史 artifact 或 M34 质量数字补洞 | `eval/{phase4_contracts,rag_retrieval_contracts,rag_answer_contracts,harness_contracts,harness_turn_contracts,harness_followup_contracts,harness_hybrid_contracts}.py`；`eval/reports/m39-p6-readiness.json` |
| API Trace 回归已分别覆盖 SQL/RAG、resume/follow-up 与 Hybrid 的若干投影和非泄露 | 尚无一份固定的跨路径 P7 rehearsal，能同时证明 trace/response 同源、citation/Evidence、运行身份和 lifecycle 语义 | `tests/test_m35_api_trace.py`；`tests/test_m36_api_trace.py`；`tests/test_m37_api_trace.py`；`tests/test_m38_hybrid_api_trace.py` |
| M34 external lexical 仍是默认，M39 的 `observation_driven_new_evidence_action` 与 `comparable_extra_budget` 均未满足 | P7 不能把 no-go 改写成质量通过、Subgraph 已实现或默认可切换 | `docs/state/rag-current-state.md`；`eval/reports/m39-p6-readiness.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 怎样保存真实执行过的上下文/动作，供之后验证而不是从最终答案倒推 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::AgentState / append_unique / set_union` | state 显式累计 retrieval keys、contexts、Tool/iteration count，方便解释何时停止 | 只把 DataPilot 已有的安全 `EvidenceRef`、Graph/Tool 次数、turn lifecycle 和 runtime identity 归入 Trace assurance；正文仍留在受控运行态 | `MessagesState`、完整 context、history summary、强制搜索、开放循环和其 checkpointer |
| 如何先固化实际运行输出再进行评测 | `agentic-rag-for-dummies/notebooks/evaluation.ipynb::query_rag / assert_saved_outputs_match_dataset / score_answer` | 评分读取与数据集匹配的已保存 answer/context，而不是另跑一次检索 | P7 assurance 只读取同次 API Trace 和 fresh deterministic contract artifact，并逐项校验 identity；Trace 与 Gate 不重新执行业务路径 | RAGAS 均值、LLM Judge、其 CSV 格式、单跳题集和用最终平均分宣布安全通过 |
| retrieval 观察与 answer / contract 门必须分层 | `DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/retriever.py::RetrieverSimilarityMetric / RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator` | retrieval 指标是独立 evaluator，不等于回答质量 | 保持 DataPilot required Gate、advisory 质量视图与 M34 基线分账；P7 manifest 只登记身份和结论，不平均不同 family 的分数 | 空结果一律记零、DB-GPT DAG、embedding scorer、把 M34 coverage 或 M27 历史数字并入 P7 required Gate |

上述源码只支持“保存真实执行事实、按层评测”的局部做法；四轴、ACL、outbound、closed-world、M39 no-go 和阶段验收语义仍以 Phase 4 roadmap 与现有 DataPilot 合同为准。

## 4. 目标、优先级与非目标

### 模块完成状态

系统能生成一份版本化的 P7 technical assurance artifact：其中每条 required 证据都有明确 family、contract/runtime identity、结果和来源；五条 API/Trace rehearsal 也能从用户响应回查同一次安全 Trace。缺项、重复、身份漂移、required 失败或把 P6 no-go 伪装为通过时，artifact 必须失败关闭。

### 必须完成

- 为 SQL、RAG、Hybrid 与 lifecycle path 建立统一、最小化的 Trace runtime identity 投影，并保持 Trace 旁路不影响业务响应。
- 建立五条跨路径 API/Trace rehearsal，验证同源四轴、citation/Evidence、runtime identity、预算/lifecycle 与非泄露。
- 建立 P7 closed-world assurance manifest，聚合当前 P1–P5 deterministic contract 结果和冻结的 M39 P6 decision，而不混入 M27 历史或 M34 质量分数。
- 生成可读 capability matrix / 演示说明，明确已完成、条件保留和未进入范围；自动 Gate 不得宣称 Phase 4 已人工验收。

### 建议完成

- 提供只读 CLI 或等价的可重复入口，输出安全 JSON 与 Markdown assurance report，便于用户人工检查。

### 条件触发

- **触发条件**：运行时新增 route、Tool、Trace receiver、Evidence consumer 或改变当前 Trace / runtime identity 语义。
- **允许动作**：先扩充 P7 catalog、rehearsal 和 required assertion，再把新路径纳入 assurance manifest。
- **未触发时**：不引入 LangFuse Cloud、LLM Judge、真实 provider、大规模 M34 重跑、Subgraph 或检索参数实验。

### 明确非目标

- 不实现 RAG Subgraph、query rewrite、parent/child、rerank、hybrid retrieval、默认 adapter 切换或 M34 A/B。
- 不改变 Knowledge Tool、AnswerFlow、citation、ACL、outbound、Router、Hybrid required/optional 或 thread 预算的既有产品合同。
- 不把 P7 变成生产认证、持久 checkpoint、长历史/长期记忆、通用 Eval 平台或 README 整理。
- 不运行真实 LLM、远程 embedding/Milvus、LangFuse Cloud、M34 external 大评测，亦不把已有 M27 历史 artifact 解释成当前合同基线。

## 5. 关键合同

### C1：Trace Runtime Identity Envelope

- 输入：同一 `AgentTurnResult`、route decision、仅已安全投影的 Tool Observation / EvidenceRef / Hybrid branch / thread lifecycle；不得额外读取正文、完整 SQL rows、raw thread id、denied branch 内部原因或私有 Evidence。
- 成功输出：Trace 内稳定、版本化的 runtime envelope。它按 route 表达 Harness/Graph、SQL runtime 或 RAG AnswerFlow / release / corpus / retrieval adapter / recipe / Composer / policy identity；Hybrid 还表达薄计划与 Synthesizer identity，拒绝分支只保留允许公开的摘要。
- 失败语义：缺少可安全投影的必需 identity 时 Trace 记录稳定的 `unavailable` 诊断而不回显异常或阻断 API；P7 rehearsal / assurance 对本应完整的 canonical path 判失败，不能用空字典冒充 identity。
- 必须保持的不变量：响应、JSONL Trace 与 Eval 仍从同一 turn/result 事实投影；Trace 默认不保存正文、完整 Hybrid rows、raw `thread_id` 或 `clarification_answers` / `follow_up_fields` 的结构化参数副本、模型思维链或 denied branch identity。既有用户可见 `answer` 仍按现有 Trace 合同保存，其自然复述业务主题不视作 thread 参数持久化；写 Trace 仍是业务路径的旁路。**用户于 2026-08-17 选择方案 A 固定此边界。**
- 本模块不冻结的实现细节：具体数据类/字段嵌套、内部 helper 名称、未来 receiver 的 identity 以及非当前路径的 runtime schema。

### C2：Cross-path API / Trace Rehearsal

- 输入：隔离 SQLite、fixture caller、deterministic SQL/RAG adapter、临时 JSONL，以及 SQL、RAG、Hybrid、clarification→resume、安全拒绝五类 canonical request/turn sequence。
- 成功输出：每个 Scenario 恰好产生预期数量的同源 response / Trace / lifecycle 证据；断言验证 trace id、四轴、route/Graph/Tool 预算、citation/Evidence 映射、C1 runtime envelope 和非泄露。
- 失败语义：漏路径、重复/额外 Trace、response/Trace identity 或四轴不一致、预算越界、citation 指向非本轮 Evidence、runtime unavailable、正文/rows/raw `thread_id` 或结构化 thread 参数副本/denied branch 侧信道泄露时，rehearsal artifact 失败关闭；不把既有 answer 中自然出现的业务主题误判为参数泄露。
- 必须保持的不变量：每个 Scenario 的业务执行只发生一次；澄清和安全拒绝正确是可观察通过，不拿 `not_observed` 或最终自然语言措辞替代合同判断；不访问真实 provider。
- 本模块不冻结的实现细节：开放路由正确率、自然语言答案质量、长期 Trace 保留期、真实模型延迟或真实外部 profile 的质量数字。

### C3：P7 Closed-world Assurance Manifest

- 输入：当前可复跑的 P1–P5 deterministic contract artifacts、C2 artifact，以及冻结 `eval/reports/m39-p6-readiness.json` 的 format / audit identity / input identities / `no_go` 结论；每份来源均携带 family 与 contract/runtime identity。
- 成功输出：带自身 identity 的 assurance manifest、required Gate 和 capability matrix。它逐项列出 P1 security/release、P2 retrieval/answer、P3 Harness、P4 turn/follow-up、P5 Hybrid、P6 decision、P7 Trace rehearsal 的事实与边界。
- 失败语义：任何 required family 缺失、重复、未知、身份/hash 不闭合、Gate 非 passed，或 M39 不再是已验证的 `no_go`，均拒绝输出 `passed`。M27 历史 artifact、M34 retrieval/Answer 数值、advisory 指标和人工说明都不能填补 required 槽位。
- 必须保持的不变量：一题一次、各 family 的原有分母/`not_observed` 语义与 policy/runtime 边界不变；P6 no-go 是路线决策证据，不是 RAG 质量通过；technical assurance `passed` 不等于 Phase 4 人工验收或生产就绪。
- 本模块不冻结的实现细节：未来 Scenario 数量、报告版式、非 required 的趋势指标、真实 LLM baseline 是否/何时由用户授权运行。

## 6. 工作切片与执行顺序

### M40-A：统一 Trace runtime identity

- 优先级：必须完成
- 依赖：M35–M38 的 `AgentTurnResult` / API projector、M31–M33 的 Evidence 和 runtime diagnostics。
- 实施内容：设计并接入 C1 的最小安全 envelope；补齐 SQL、RAG、Hybrid 与 lifecycle 路径的 identity 来源与 unavailable 降级，避免 API / Trace 各自猜字段。
- 关键合同：C1。
- 交付物：Trace schema/projector、针对安全投影和 identity 缺失的单元/API 测试。
- 验证方式：现有 SQL/RAG/Hybrid/resume/follow-up/denied Trace 测试增量回归；字段白名单与禁止字段检查。
- 完成门：五类路径均能得到可解释的 runtime 状态；无路径因 Trace 投影错误改变业务四轴或泄露私有数据。

### M40-B：跨路径 rehearsal 与演示证据

- 优先级：必须完成
- 依赖：M40-A；M35–M38 的确定性 API/Trace test fixture。
- 实施内容：以一次执行、多断言共享证据的方式实现 C2，固定五条 Phase 4 用户故事，并把 response、Trace、citation/Evidence、生命周期和预算关系投影为安全 artifact。
- 关键合同：C1、C2。
- 交付物：版本化 rehearsal runner/artifact、专项测试、可读的五路径演示说明。
- 验证方式：正常、缺 identity、重复/漏 Trace、response/Trace 不一致、泄露与预算篡改反例。
- 完成门：所有 canonical Scenario 通过且任一闭合/安全反例无法生成可信 artifact。

### M40-C：P7 assurance manifest 与 capability matrix

- 优先级：必须完成
- 依赖：M40-B；M31–M38 contract runner；冻结 M39 P6 audit 报告。
- 实施内容：实现 C3，明确 catalog 的 required family 与 identity 规则，保留每个 family 的原有通过/不观察语义；生成安全 JSON/Markdown report 和 Phase 4 capability matrix，记录 M39 no-go、条件能力和技术边界。
- 关键合同：C2、C3。
- 交付物：P7 assurance runner/validator/report、篡改/缺项测试、状态与 notes 收工素材。
- 验证方式：fresh deterministic assurance run、M39 frozen report integrity 检查、family 缺失/重复/未知/失败和历史 artifact 注入反例。
- 完成门：只有全部 required 当前证据闭合时 Gate 为 passed；报告明确 technical gate 与用户人工阶段验收的边界。

### M40-D：回归、收工与人工验收准备

- 优先级：必须完成
- 依赖：M40-A–C。
- 实施内容：执行聚焦与受影响回归，固化 notes、P7 capability matrix 和必要 state/changelog；准备用户可复现演示与人工检查清单。
- 关键合同：C1–C3。
- 交付物：验证快照、M40 notes、技术档案、人工检查入口。
- 验证方式：按第 8 节顺序；全量 pytest 依 AGENTS 长时间规则处理。
- 完成门：不宣称 Phase 4 完成，直到收工流程、用户人工检查和 `accept-module` 均实际完成。

## 7. 决策门

本模块无新的用户决策门。M39 的 P6 方案 A 已确认；M40 只消费其 `no_go` 事实，不改变默认 adapter、模型、embedding、出站策略或安全合同。

若实施中发现某个现有 required family 的 contract/runtime identity 无法与当前代码闭合，或现有 Trace 需要新增外发数据类别/receiver，按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支，不以兼容字段或人工说明绕过 C1/C3。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 Trace runtime envelope | SQL/RAG/Hybrid/lifecycle API Trace 测试 + identity 缺失反例 | 同源 Trace 有安全、可解释 identity；Trace 不影响业务响应且无私有数据泄露 | 必须完成 |
| C2 cross-path rehearsal | 五条固定 Scenario 的一次执行 artifact + 漏/重/篡改/泄露反例 | response/Trace/Evidence/citation/lifecycle/预算全部闭合；任一反例 fail closed | 必须完成 |
| C3 P7 assurance manifest | fresh deterministic family run + M39 frozen audit integrity + catalog 注入反例 | required family 恰好完整、全部 passed、M39 为 verified no-go；不混入历史/质量数字 | 必须完成 |
| P7 capability matrix | report 内容测试与人工可读检查 | 明确 SQL/RAG/Hybrid/澄清恢复/安全拒绝、P6 no-go、条件项和未完成边界 | 必须完成 |
| 既有回归 | M31–M39 受影响测试与完整 pytest | 既有 Evidence、Harness、thread、Hybrid、M39 合同不回归 | 必须完成 |

聚焦顺序：先 C1 单元/API Trace → C2 rehearsal → C3 manifest → M31–M39 受影响 deterministic 回归 → `compileall` / `git diff --check`。全部代码修改后，若完整 pytest 预计超过两分钟，先在 M40 notes 写 checkpoint，再以独立 `.agent_work/temp/` basetemp 启动后台任务并记录 PID、日志、退出码与完成标记。

不属于本模块的验证：真实 LLM、远程 embedding/Milvus、LangFuse Cloud、M34 external rerun、LLM Judge、M27 v3 新真实基线和生产身份/性能。M27 历史 artifact、M34 原始大 artifact、业务 22-entry release 与 external profile 均保持只读；本模块不改写其身份、分母、默认 pointer 或质量结论。

## 9. 依赖与交付物

### 依赖

- M31–M33 的 Evidence / ACL / outbound / RAG contract family；M35–M38 的 Harness、thread、follow-up、Hybrid 和 API/Trace seam。
- M39 frozen `no_go` audit（`eval/reports/m39-p6-readiness.json`）及其 state 结论。
- `docs/phase4-roadmap.md` 第 4、13、16 节；`docs/state/{AI_CONTEXT,rag-current-state,eval-baselines,runbook}.md`。

### 交付物

- Trace runtime identity 的安全投影和跨路径 API/Trace rehearsal。
- P7 closed-world assurance manifest、Gate、JSON/Markdown report 和 capability matrix。
- 专项/回归测试、M40 notes 与必要状态/历史记录。
- 用户人工检查可直接使用的五路径演示与阶段验收边界说明。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：M34 lexical 质量缺口、single-variable Pipeline 候选、Subgraph、真实 LLM Judge、远程 outbound 授权、生产认证、持久 checkpoint、长历史与开放 Router。
- 下一步可直接消费的产物：P7 assurance manifest、capability matrix 和五路径演示证据，供 M40 收工后的用户人工检查与 `accept-module` 使用。
- 后续需要根据真实失败重新规划的内容：只有未污染 dev 能证明 Observation 驱动的允许动作产生新 Evidence、并冻结 held-out 与可比额外预算时，才可另立新的 P6 条件实验模块；不得复用 M40 模块号或把 no-go 自动翻转。
- 可能存在的风险：若从旧 diagnostics 中无法安全得到同一运行的身份，C1/C3 将失败关闭；这暴露的是现有 Trace 合同缺口，而不是可以用报告文字掩盖的问题。P7 technical gate 通过也不表示生产认证、真实语料生产性或开放质量已验证。

## 11. 开工条件

- 开工前无需确认：用户已确认 M39 验收状态以 `AI_CONTEXT` 为准；P6 `no_go`、external lexical 默认、LangFuse Cloud 关闭及新增 Knowledge/RAG 出站默认拒绝均已固定。
- 实施中需要确认：无。任何默认模型、embedding、检索、出站、安全策略或数据库结构变更均不属于本模块，若意外需要则先暂停并取得用户确认。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支。
