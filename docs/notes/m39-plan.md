# M39 P6 RAG Subgraph 入场证据审计与 go/no-go 开发计划

> 能力里程碑：Phase 4 `P6`；本模块闭环 P6 必做的失败证据审查与可复核 go/no-go，不实现 RAG Subgraph。若结论为 no-go，P6 按 roadmap 口径完成；只有所有入场条件随后成立，才由独立 M40 进入实验 adapter。
>
> 主要问题：M34 已经证明 external RAG 存在 lexical 漏召回、selected/context packing 和 Composer support 拒绝，但现有证据还不能证明“根据第一次 Observation 再做一次取证”会新增有效 Evidence，因此不能把质量缺口直接等同为建设 Agentic RAG 的理由。

## 1. 模块定义与范围判断

M38 已完成 P5 保守 Hybrid；路线规定下一步必须先完成 P6 的失败证据审查，而不是放宽 Router、接远程 Synthesizer，或为展示直接搭一个 Graph。M34 已留下可追溯的 lexical/semantic retrieval、180 题 Answer/Citation 及其 dev/held-out 身份，但这些是不同层的证据，不能用 `complete`、gold coverage 或某一次 semantic 失败直接推出“多轮检索有收益”。

本模块以“现有失败到底属于哪里”为一个主要问题，完整交付可重复的证据审计和 P6 决策记录。它不与后续的单变量 Pipeline 增强或真正的 Subgraph A/B 混做：前者可在以后独立验证，后者只有审计满足 P6 全部入场条件后才有资格立项。

完成后，用户能理解、演示和验收：

- 为什么 `top-20` 漏召回、候选进入后被 selected/context budget 截断、Composer 严格 support 拒绝、provider unavailable 是四类不同问题；
- 为什么现有 M34 证据足以要求继续改善 RAG，却不足以授权一个 Observation 驱动的多步子图；
- 如何保护 120 题 held-out：它可作为既有冻结基线核对，但不能按逐题失败倒推新动作；
- no-go 不是“什么也没做”，而是保留确定性 Pipeline、写清缺什么证据和怎样才能重新打开 P6。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| external 默认仍是 lexical；同 corpus/split/@20 的 semantic candidate 在 dev、held-out 均低于 lexical | 不能把“改成 semantic”包装为已验证的 P6 恢复动作或默认改进 | `docs/state/eval-baselines.md`、`.agent_work/temp/m34-{lexical,semantic}-tool-{dev,heldout}-retrieval.json` |
| lexical held-out retrieval @20 的 coverage/all-gold/MRR 为 `0.823125 / 0.775000 / 0.723134`；semantic held-out 明显较低 | 已有稳定漏召回，但只有一次固定检索的结果，尚未显示第二个 Observation 驱动动作能带来新 Evidence | `eval/reports/m34-enterprise-rag-baseline-manifest.md`、`docs/state/rag-current-state.md` |
| 180 题 Answer Eval：146 answer completed、24 `composer_output_invalid`、10 `composer_unavailable`；multi-document 只有 2/38 all-gold cited | “未 complete / 未 all-gold cited”混合了上下文选择、生成 support 合同与外部不可用，不能直接归因到 retrieval loop | `.agent_work/temp/m34-answer-eval-full-v4.json`、`docs/state/eval-baselines.md` |
| AnswerFlow 每题只调用一次 Knowledge Tool；Tool 固定在授权集合中一次 adapter retrieval，再按 candidate/selected/generation-visible/cited ledger 流转 | 当前接口能提供同次 Evidence 阶段事实，适合离线归因；不能因为做审计而改变 ACL、Tool 次数、Gate 或 citation 合同 | `engine/rag/knowledge_tool.py::KnowledgeTool.retrieve`、`engine/rag/answer_flow.py::RAGAnswerFlow.run` |
| external runtime 通过 `EnterpriseProfileRuntime` 把 SQLite FTS adapter 接到同一 Knowledge Tool / AnswerFlow；M37 规定 external Evidence follow-up 永远重检索 | 任何未来 Subgraph 也必须保持同一 Tool/Evidence 外壳、ACL 和顶层预算，不能另建外部 RAG 旁路或复用旧正文 | `engine/rag/enterprise_runtime.py::EnterpriseProfileRuntime`、`docs/state/AI_CONTEXT.md` |
| 60 dev / 120 held-out 已冻结；M34 已跑过一次全 180 题基线 | 后续可用 dev 的逐题证据设计诊断；held-out 的逐题 evidence 不能被用于选择动作、Prompt 或参数，否则失去未来默认决策价值 | `engine/rag/enterprise_cases.py`、`docs/state/rag-current-state.md`、`docs/notes/m34-notes.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 如何判断是否需要一个真正的 RAG 子图 | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph`；`edges.py::route_after_orchestrator_call` | 子图应有明确状态、conditional stop 与 Tool/iteration budget，而不是把固定检索拆成节点 | M39 用它作反向门槛：只有审计能给出“Observation → 允许动作 → 新 Evidence”的恢复假设时，M40 才能设计同 Tool interface 的有界 adapter | 不复制其主图 fan-out、`InMemorySaver`、强制首搜、LLM rewrite、fallback answer 或多层 Prompt |
| 判断“已有 Evidence”和“可继续取证”不能混成同一状态 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py::AgentState`；`nodes.py::_retrieval_contexts / should_compress_context / compress_context` | 记录 Tool count、已取 context 和去重的已执行动作，才能解释停止与避免重复 | readiness artifact 只从 DataPilot 真实 ledger 和调用次数推导阶段/重复风险；将来若 go，必须把 Evidence progress 与回答充分性 Gate 分开 | 不使用其 `MessagesState`、完整 Tool 文本、历史压缩或 LLM 摘要作为 DataPilot Evidence |
| 何时按需扩大上下文，而不是盲目循环 | `agentic-rag-for-dummies/project/rag_agent/tools.py::ToolFactory._search_child_chunks / _retrieve_parent_chunks` | 搜索命中与 parent 扩展是可区分的两种动作；扩展必须由前一次命中触发 | M39 只把“candidate 已有 gold、但 selected/generation-visible 丢失”标为 Pipeline context-packing 候选；它不是直接批准 parent expansion 或 Subgraph | 不继承其字符串 Tool Observation、顺序 parent ID、默认 parent 扩展、参数或向量库 |

参考源码证明的是“有界子图应当具备哪些可观察控制事实”，不能证明 DataPilot 当前适合引入它。当前路线、ACL、Evidence、outbound、分集和决策权仍以 roadmap 与现有合同为准；本模块不需要阅读 reference 的项目级 analysis。

## 4. 目标、优先级与非目标

### 模块完成状态

系统具有一个仅读取冻结 M34 artifact 的、版本化且闭合的 P6 readiness 审计：每个 dev Scenario 可被归到可复核的失败层，held-out 不被用于设计动作；审计明确给出四项入场条件是否满足、建议的 go/no-go 和重开条件。当前证据预期得到严格 **no-go**：确定性 lexical Pipeline 保持 external 默认，P6 不实现子图。

### 必须完成

- 建立 M34 artifact identity / 分集 / 运行条件的只读闭合检查，拒绝缺失、篡改或不可比输入。
- 从真实 Evidence ledger 与已有 retrieval/answer artifact 形成互斥失败分类，区分检索候选、selected/context、Composer support、provider unavailable 与不可观察情况。
- 只用 dev 的逐题失败构造和审查恢复假设；held-out 只核验冻结身份、既有 aggregate baseline 与未被用作调参的边界。
- 对 P6 四个入场条件逐项给出证据、结论、缺口和重开条件；形成用户可审查的 go/no-go 记录。
- 为 audit 的 closed-world、分类、held-out 隔离和 no-go 不改默认建立测试/contract assertion。

### 建议完成

- 为每类失败输出脱敏、可排序的样本引用和计数摘要，便于用户复盘，不写入问题、Document 正文、完整答案或完整 Evidence。

### 条件触发

- **触发条件**：dev 审计同时证明可复现的非 corpus/ACL/gold/provider 根因，存在一种由第一次 Observation 选择、能新增 Evidence 的具体动作，并能在不读 held-out 逐题结果的前提下冻结 M40 的 held-out decision protocol 与可比预算。
- **允许动作**：停止在 M39 的 go-ready 决策与 M40 输入合同；经用户确认后另建 M40，才实现一个同 Knowledge Tool interface 的有界 Subgraph adapter 与 A/B。
- **未触发时**：记录 no-go；不添加 LangGraph RAG 子图、query rewrite、parent/child、rerank、hybrid retrieval、远程模型节点或默认路径变更。

### 明确非目标

- 不运行新的真实 LLM、remote embedding/Milvus、M34 retrieval/Answer Eval、LangFuse Cloud 或修改 external profile/pointer。
- 不把 M34 full Answer Eval 的 `complete` 当正确率，不增加 LLM Judge，也不放宽严格 `support_text` / citation 合同。
- 不改变 `KnowledgeTool`、`RAGAnswerFlow`、Harness、Hybrid、ACL、outbound、M37 external 强制重检索、Router 或 API。
- 不在 M39 实现任何 RAG Subgraph、固定 Pipeline 检索增强或 M40 A/B；这些必须由审计结论和独立计划决定。

## 5. 关键合同

### C1：P6 readiness 输入闭合与零执行合同

- 输入：M34 lexical/semantic dev 与 held-out retrieval artifact、full Answer/Citation artifact、M34 split/profile/runtime identity，以及现有读取它们的只读路径。
- 成功输出：带 canonical input identity、分集用途、每项输入校验结果和分类汇总的 readiness artifact / 可读报告；不改变任何历史 artifact。
- 失败语义：输入缺失、hash/identity/contract 不一致、Scenario 交叉、不能证明可比性或字段不足时为 `not_ready`，不得把它降格成 no-go 或借其他 run 补齐。
- 必须保持的不变量：零 Knowledge Tool / AnswerFlow / provider 调用；M34 180 题、业务 22-entry release、M27 与 Phase 4 contract artifact 都只读且不混算；审计不保存正文、完整问题、完整 answer、SQL 或 private Evidence。
- 本模块不冻结的实现细节：artifact 文件名、报告排版、脱敏 sample 数量、内部数据类和指标阈值。

### C2：失败分层与 held-out 隔离合同

- 输入：C1 已验证的 execution、retrieval coverage、AnswerFlow four-stage ledger、Composer outcome 及 M34 split 身份。
- 成功输出：每个 dev Scenario 仅归入一个主层：`retrieval_candidate_gap`、`context_selection_or_packing_gap`、`composer_support_gap`、`provider_unavailable` 或 `not_classifiable`；报告可额外列该主层之外的安全诊断，不重复计入分母。
- 失败语义：没有足够同次阶段证据的 Scenario 标为 `not_classifiable`；不借 gold、标题或最终文本猜测一次运行未看到的 Evidence；任何 held-out 逐题分类/样本/参数选择尝试被拒绝。
- 必须保持的不变量：gold 只作 offline scorer / 分类锚点，绝不进入运行时 Tool、Gate、Composer 或候选选择；candidate、selected、generation-visible、cited 不互相冒充；`composer_unavailable` 与 `composer_output_invalid` 不被写成 retrieval 失败。
- 本模块不冻结的实现细节：每个主层的展示名称、dev 报告的可视化形式和未来 Pipeline candidate 的参数。

### C3：P6 入场判定与默认保护合同

- 输入：C1/C2 audit、P6 四项入场条件、当前 lexical baseline/semantic candidate 对照与实际 Tool/Harness 合同。
- 成功输出：每项条件的 `met / not_met / not_observed`、直接证据、缺口、推荐 go/no-go；若 no-go，明确保持 `enterprise-lexical` 默认与不可缩短的重开条件。
- 失败语义：任一条件为 `not_met` 或 `not_observed` 时结论只能为 no-go；不得把“有失败”“参考项目有 Graph”“实现会更完整”当条件满足。
- 必须保持的不变量：只有全部条件都满足才允许为 M40 冻结 action hypothesis、dev protocol、未污染 held-out decision protocol、父子预算与可比成本；即使 go-ready，也不能在 M39 改默认或实现 adapter。
- 本模块不冻结的实现细节：未来动作类型、Prompt、chunk/top-k、loop 次数、模型、存储、M40 文件结构或默认切换标准。

## 6. 工作切片与执行顺序

### M39-A：P6 输入清单与 read-only identity 审计

- 优先级：必须完成
- 依赖：M34 已登记的五份 completed artifact、60/120 split、M38 后最新 state/runbook。
- 实施内容：建立 `m39-notes.md` checklist；核对历史 artifact 的 identity、question set、profile、adapter/recipe、分集和一次执行事实；定义 C1 所需的最小安全投影。
- 关键合同：C1。
- 交付物：输入清单、closed-world validator、不可比/缺失反例和 no-provider-call 计数。
- 验证方式：正常、缺 artifact、篡改 identity、错误 split、重复 Scenario 和不兼容 runtime 的 fixture。
- 完成门：每一条后续结论能定位到同一 M34 基线；无法对账时审计安全失败而不是输出方向性建议。

### M39-B：dev 失败分层与 Evidence stage 对账

- 优先级：必须完成
- 依赖：M39-A；M34 retrieval execution、full Answer execution、Knowledge Tool / AnswerFlow ledger 合同。
- 实施内容：只对 dev 逐题建立 C2 分类；比较 retrieval candidate、selected、generation-visible、cited 与 gold 的 offline coverage，分离固定检索漏召回、固定 context/selection 问题、Composer support 拒绝和 provider 不可用。held-out 仅验证固定集合、aggregate baseline 与未被分类消费。
- 关键合同：C1、C2。
- 交付物：可重复失败分类 artifact、分母/互斥性检查、脱敏 summary 及 held-out protection assertion。
- 验证方式：人为构造每类 ledger / result、漏 stage、跨 run Evidence、完整但非 gold citation、provider failure 与试图读取 held-out execution 的反例。
- 完成门：不能再把“citation coverage 低”笼统解释成“应该循环”；所有分类都保留其可观察边界。

### M39-C：恢复假设审查与 P6 判定

- 优先级：必须完成
- 依赖：M39-B、roadmap P6 的全部入场条件、现有 lexical/semantic 对照。
- 实施内容：把每个 dev 主层映射到“是否可能靠 Observation 驱动新增 Evidence”与“是否其实属于单变量 Pipeline / Composer / provider 问题”；对四个入场条件出具 `met / not_met / not_observed`。当前预期为 no-go：已有数据没有一个已验证的、观察后新增 Evidence 的允许动作。
- 关键合同：C2、C3。
- 交付物：P6 decision record、no-go 重开条件，或严格的 go-ready M40 输入说明。
- 验证方式：表驱动条件组合；任一缺项、把 held-out 用作动作选择、把固定 Pipeline 拆图或把 Composer 问题误作检索循环均应得 no-go。
- 完成门：结论可被输入 artifact 复核，并清楚区分“值得后续单变量验证”和“已足以建设 Subgraph”。

### M39-D：回归、资料固化与 P6 状态同步

- 优先级：必须完成
- 依赖：M39-A–C 和第 7 节决策确认。
- 实施内容：运行 audit 专项、M34 artifact validator / enterprise runtime 的既有确定性回归、M31–M33 RAG contract、M35–M38 Harness/Hybrid 受影响回归；审查敏感字段、读写边界和注释。确认决策后才同步 notes、state、eval baseline 与 Phase 4 changelog。
- 关键合同：C1–C3。
- 交付物：可靠验证终态、M39 notes、决策记录和必要的 state/changelog 事实更新。
- 验证方式：见第 8 节；预计超过两分钟的全仓 deterministic pytest 按 `AGENTS.md` 后台规则执行。
- 完成门：no-go / go-ready、验证结果与 state 的表述一致；未运行的 provider 实验不被写成已验证能力。

## 7. 决策门

### G-M39-1：P6 的严格 no-go 还是为 M40 打开实验门

> 用户选择：2026-08-17 确认方案 A；本轮只确认计划，暂不开始 M39 开发。

#### 方案 A：严格证据优先，完成 M39 后按缺项记录 no-go（推荐）

- 做法：实施本计划的只读 audit；只要 C3 任一入场条件缺失，即关闭 P6 Subgraph 实现，保持 lexical Pipeline 默认，并把对应失败拆到后续独立候选。
- 影响：当前预计会得到 no-go；P6 的必做审查完成，P7 可以继续收口，系统不会凭“有失败”增加循环、延迟、出站或调试面。
- 适用条件：现有 M34 artifact 如调查所示只证明检索/packing/Composer 缺口，尚无 Observation 驱动动作的新增 Evidence 证据。
- 风险：暂时不展示 Agentic RAG；若后续真实需求出现，需要重新准备受控 dev 证据和未污染 held-out。

#### 方案 B：仅在 audit 全部入场条件满足后，开启独立 M40 实验门

- 做法：M39 不实现 adapter；若 C3 的每项均为 `met`，用户确认后才创建 M40，单独冻结一种恢复动作、同 Tool interface、父子预算、dev 调试协议和未污染 held-out A/B。
- 影响：可以研究真正的 Agentic RAG，但实现、真实运行、成本、延迟和默认化判断全部延后到 M40，不能借 M39 的计划或代码自动开始。
- 适用条件：dev 有稳定非 corpus/ACL/gold/provider 的失败 cohort，具体行动能由第一次 Observation 选择并可新增 Evidence；held-out 尚未被此行动的设计污染，且可比较预算可测。
- 风险：若把现有 lexical 漏召回、selected budget 或 Composer 拒绝误判为充分证据，M40 会退化为把固定 Pipeline 拆成 Graph，增加复杂度却不提升合同或质量。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：当前 evidence 显示 semantic candidate 已输给 lexical；multi-document / citation 的低覆盖还混有 selected-context 和 Composer 层；没有任何一次“看完首次结果后再取证”的收益证据。先把这个判断固化为可复核 no-go，最符合 P6 的入场纪律。
- 用户确认前允许推进：不适用，方案 A 已确认。
- 用户确认前禁止推进：不适用；用户仍明确要求本轮不开始 M39 开发。
- 需要确认的时点：已于 2026-08-17 确认方案 A；开始实施需用户后续明确发起。若 audit 意外满足 C3 全项，再在 M40 开工前单独确认方案 B。
- 重开决策的条件：新的、未用 held-out 调试的 dev 证据证明某个允许动作根据首次 Observation 能新增有效 Evidence，并能冻结可比预算和新的 held-out decision protocol。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 输入闭合 | M34 artifact fixture + hash/identity/split/runtime 篡改测试 | 只有同一冻结基线进入 audit；缺失/篡改一律 `not_ready`，零真实执行 | 必须完成 |
| C2 失败分层 | 包含 candidate/selected/generation-visible/cited、Composer 与 provider 情形的表驱动 fixture | dev Scenario 主层唯一且分母闭合；阶段/错误不互相冒充 | 必须完成 |
| C2 held-out 隔离 | 访问策略 / fake execution 反例 | held-out 逐题信息不能参与主层、样本或动作选择；只允许身份与既有 aggregate 核验 | 必须完成 |
| C3 入场判定 | 四条件真值表及缺项组合 | 任一 `not_met/not_observed` 必为 no-go；无恢复假设不能得到 go-ready | 必须完成 |
| 默认与安全边界 | enterprise runtime、RAG contract、M35–M38 回归 | lexical 默认、Knowledge Tool/ACL/Evidence/Trace/Hybrid 合同不变，无新增 outbound | 必须完成 |
| 静态交付 | 注释审查、敏感字段扫描、`compileall`、`git diff --check` | 审计不落盘正文/问题/答案/private Evidence；无语法与 whitespace 问题 | 必须完成 |

聚焦顺序：C1 fixture/validator → C2 stage taxonomy → held-out isolation → C3 truth table / decision report → M34 artifact/runtime → M31–M33 RAG contracts → M35–M38 Harness/Hybrid → 全仓 deterministic pytest → static checks。

不属于本模块的验证：新的真实 LLM 或 M34 大评测、remote embedding/Milvus、LangFuse Cloud、LLM Judge、Subgraph A/B、默认切换与人工自然答案正确性。M27、M31–M38、M34 原 artifact 都是只读历史 / 基线；M39 不补字段、不重写结果、不混算数字。

## 9. 依赖与交付物

### 依赖

- P6 目标、入场条件、实验约束与 G7/G8：`docs/phase4-roadmap.md`。
- M34 external profile、60/120 split、lexical/semantic/Answer baseline 与可比性规则：`docs/state/{rag-current-state,eval-baselines}.md`、`eval/reports/m34-enterprise-rag-baseline-manifest.md`。
- M31–M33 的 Knowledge Tool、Evidence ledger、Gate、citation 与 outbound 合同，以及 M35–M38 的唯一 Harness / Hybrid 边界。
- 当前 `m38-notes.md` handoff 与本计划第 3 节定点参考源码。

### 交付物

- 只读、版本化的 P6 readiness audit 及 closed-world / held-out isolation assertions。
- dev 失败分层 artifact 与可读的 P6 入场判定报告。
- 用户确认的 no-go 决策及重开条件；或只为 M40 准备的 go-ready 输入合同。
- 聚焦/回归测试、M39 notes 与必要的 state/changelog 更新材料。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：任何 RAG Subgraph、查询改写、parent/child、rerank、hybrid retrieval、context budget 参数调优、Composer prompt/support 规则变更、LLM Judge、远程模型与默认切换。
- 下一模块可直接消费的产物：带 identity 的 failure taxonomy、P6 条件判定、no-go 重开条件；若 go-ready，消费的是一种明确恢复动作和未污染 held-out protocol，而不是一份“效果不够好”的泛化报告。
- 若 M39 为 no-go：P6 的阶段目标已满足，下一模块进入 P7 收口；Pipeline 的每个单变量增强仍须以独立 module plan 和 dev/held-out 证据决定，不能把 P6 no-go 写成永不优化。
- 若 M39 为 go-ready：**M40 有界 RAG Subgraph 实验**是唯一后续模块。强制开工条件是 C3 四项全 met、用户确认 G-M39-1 方案 B、已冻结同 corpus/contract/provider 的 dev 与未污染 held-out、父子预算/成本观测和精确 outbound 决策均就绪。最终验收是同 Knowledge Tool/Evidence/ACL/citation interface 的单一恢复动作，在 held-out 多轮可比 A/B 中以稳定净收益抵偿成本；否则 Pipeline 继续默认和 fallback。M40 未完成前不得宣称 Subgraph、P6 效果提升或默认切换已完成。
- 可能存在的风险：M34 全量 Answer artifact 已含 held-out 运行事实；M39 必须把它当冻结基线而非调参素材。若无法证明这个隔离边界，应报告 `not_ready`，不做 no-go 以外的效果判断。

## 11. 开工条件

- 开工前无需确认：M38 已完成 P5；P6 必须先做失败证据审查；M34 identity、60/120 split、lexical default、semantic 未激活、严格 support/citation 和 external 强制重检索均为既有事实；本模块不运行新的 provider。
- 实施中需要确认：第 7 节 G-M39-1。默认建议先确认方案 A；若审计结论意外为 go-ready，必须在 M40 前重新确认方案 B，不在 M39 内越过实现门。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；尤其是 held-out 已被用于设计动作、artifact identity 不能闭合、需要新增数据出站、或有人试图把固定 Pipeline 拆图而没有新增 Evidence 假设时。
