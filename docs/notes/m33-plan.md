# M33 可信 RAG 回答与 Citation 闭环开发计划

> 状态：已确认可执行（G-M33 = 方案 A；G4 等闭环证据形成后再确认）
>
> 能力里程碑：Phase 4 **P2「确定性 RAG 垂直切片」的第二个能力切片**；M33 把 M32 的 selected Document Evidence 推进为经过 Gate、Composer 和 Citation Validator 的可信回答结果，但不接公开 HTTP 路由，因此不宣称 P2 的公开 API 交付已经完成
>
> 主要问题：系统已经能安全取到 selected Document Evidence，却还不能证明生成器实际看见了哪些证据、回答中的 claim 是否全部被本轮合法 Evidence 支持，以及失败时应返回什么四轴状态

## 1. 模块定义与范围判断

M32 已经闭环 active release → ACL 前置过滤 → deterministic retrieval → Document Evidence candidate/selected → pre-generation 复核。下一步最自然的能力切片不是更换检索后端，也不是提前画 LangGraph，而是把这批 selected Evidence 安全地变成一份可以验证的回答结果。

M33 冻结为一个“可信回答子闭环”：

1. Shared Answer Evidence Gate 只允许本轮、当前有效、用途匹配且已通过生成前授权的 selected Evidence 进入回答上下文；
2. Evidence 真正交给 Composer 时才推进为 `generation_visible`，不能把 M32 的预检查冒充实际入模；
3. 首版使用离线确定性、证据绑定的 Composer，产出结构化 claim draft，不调用远程模型；
4. 代码为 claim 分配 citation slot，Citation Validator 对同轮 identity、stage、revision、anchor 和授权做最终校验；
5. 只有全部 citation 通过后才公开回答和 citation，并把相关 Evidence 推进为 `cited`；
6. 薄应用流程集中投影 route/execution/answer/safety 四轴和稳定 reason，形成 P3 可直接调用的深 module interface；
7. 建立独立 answer/citation Eval family，与 M32 retrieval-only 证据分层。

用户完成本模块后，可以沿一次调用解释“检索到的材料为什么还不能直接成为答案、何时才算生成器真正看见、citation 为什么不是在答案末尾拼文件名，以及引用失败后为什么整份未验证答案不能展示”。

本模块不接 `/api/query`。原因是当前 HTTP 入口没有可信文档 caller，也没有合法 RAG 选择入口；此时接线只能提前实现 Router、增加临时公开 route hint，或错误信任请求体 `user_role`。用户已确认 G-M33 方案 A：先把回答能力做深，P3 再由唯一顶层 Harness 负责路由、caller 接线和 HTTP 投影。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| `KnowledgeTool.retrieve()` 已返回 selected Evidence、截至 selected 的 ledger 和 pre-generation decisions | 还没有唯一 owner 决定哪些 Evidence 足以回答，也没有真实的 `generation_visible` 迁移 | `engine/rag/knowledge_tool.py`、`docs/notes/m32-notes.md` |
| `EvidenceLedger` 已支持 selected → generation-visible → cited，并在入模时要求二次授权 | 现有测试只直接调用底层 transition；没有真实 Composer 调用把阶段迁移与上下文消费绑定起来 | `engine/rag/evidence.py::EvidenceLedger.transition`、`tests/test_m31_evidence_citation.py` |
| citation slot 和 validator 已能检查 run、claim、stage、revision/content identity、anchor 与 ACL | 当前没有 claim draft、slot 分配编排、用户可见 citation 或“任一引用失败则答案不展示”的上层合同 | `engine/rag/evidence.py::allocate_citation_slot / validate_citations` |
| M32 的 6 个 Scenario、20 条 required 只证明 retrieval，ledger 最远到 selected | 把该 family 原地扩写为 answer Eval 会改写 M32 completed artifact 的含义 | `eval/rag_retrieval_contracts.py`、`docs/state/AI_CONTEXT.md` |
| 新 Knowledge generation/sufficiency/judge 远端用途仍默认 deny | M33 不能静默复用 Text2SQL 的 Qwen 权限；首版 Composer 和 Gate 必须离线、可复现并有保守失败语义 | `engine/governance.py::DEFAULT_OUTBOUND_POLICY`、M29 G1-O、M32 handoff |
| 当前 `/api/query` 无条件进入 Text2SQL，`QueryRequest.user_role` 只是客户端声明 | M33 若直接接 HTTP，要么提前实现 P3 Router，要么增加临时公开合同，要么形成文档越权 | `app/api/query.py::query`、`app/schemas/agent.py::QueryRequest`、`engine/governance.py::unverified_request_caller` |
| G0=A 已确认同一 `/api/query` 未来增量扩展四轴状态和 citations，`docs_used` 只能由验证后的 citation 派生 | M33 应提供稳定安全投影供 P3 复用，但不能修改现有 `AgentResponse` 后又没有合法入口消费它 | `docs/notes/m29-phase4-entry-contract-notes.md` 第 4 节 |
| 首批 corpus 只有 11 条短政策/指标说明，且现有 retrieval 是本地词法 baseline | 可以确定性验证引用真实性和结构化事实，但不能把结果外推为开放语义回答、长文或真实 LLM 能力 | `domain_pack/kb_docs/`、`docs/state/AI_CONTEXT.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| Composer 怎样同时拿到正文与稳定 reference | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py :: RetrieverResource.get_resources / _get_references` | Resource 同时返回 chunks、prompt template 和带 chunk ID/score/retriever 的 references，说明内容与身份应一起越过生成 seam | M33 的 Composer 只接收 Gate 允许并已推进 `generation_visible` 的 typed Evidence context；claim draft 继续携带本轮 Evidence identity，不从文本末尾反推 source | 不把文档名、score 或 retriever 名当 citation；不把开放 dict reference 当内部事实；不继承 rerank 和 prompt 参数 |
| 为什么不能让 Tool 直接返回最终答案 | `DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py :: make_knowledge_retrieve.knowledge_retrieve` | 该 Tool 把正文、零结果和异常都包装为字符串 Observation，能直接看到 retrieval fact 与回答/错误文本混在一起的风险 | 保持 M32 Knowledge Tool 只负责取证；M33 在 Tool 外由 Gate、Composer、Validator 和薄 controller 分别拥有唯一职责 | 不只使用第一个 resource；不把异常字符串送入生成上下文；不让 Tool 决定最终 answer/safety 状态 |
| 怎样保证评分和 citation 使用生成器真实看到的 context | `agentic-rag-for-dummies/project/rag_agent/nodes.py :: _retrieval_contexts`；`graph_state.py :: AgentState.retrieved_contexts` | 从真实 ToolMessage 收集并去重 retrieval context，而不是事后重跑检索或猜测模型看过什么 | M33 在调用 Composer 的同一处固化 generation context identity、EvidenceRef 和 ledger stage；Eval 只读本次 AnswerFlow execution evidence | 不以字符串列表代替 typed Evidence；不引入 Graph、history compact、Tool loop 或 message reducer |
| 最终拼 sources 为什么不等于 citation 闭环 | `GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py :: _collect_sources / finalize` | `finalize` 先生成答案，再从多个可选 metadata 字段猜 source；这是 answer 与 source 身份可能断裂的直接反例 | M33 先由代码按 claim 分配 slot，再校验 claim draft 指向的 generation-visible Evidence；只有 validator 成功后才形成用户 citation 和答案 | 不照搬 PostgreSQL→Milvus fallback、LLM 失败后直接回显原始 context、末尾 sources 去重或“有 source 就算支持” |

以上参考只能证明内容/identity seam、真实 context 留存和 source 断裂风险，不能提供 DataPilot 所需的 claim-level validator、ACL、四轴状态、outbound 或 closed-world Eval。M33 的核心合同继续以 Phase 4 roadmap、M29-M32 已确认合同和当前代码为准。

`codebase-design` 对本计划的影响：M33 对 P3 暴露一个回答流程 interface，把 Gate、generation context、Composer、slot、validator、四轴结果和安全投影收在内部；不把每个步骤做成需要调用者按顺序拼装的浅 module，也不为只有一个离线实现的内部算法提前制造公开 adapter 层。远程 Composer 真正进入候选时，再在真实变化 seam 上引入 adapter。

## 4. 目标、优先级与非目标

### 模块完成状态

在固定 active release 和 M32 deterministic Knowledge Tool 下，受控调用者提交 RAG 回答请求后，系统能在一次 AnswerFlow 中完成取证、Gate、真实入模阶段迁移、确定性 claim 生成、citation 校验和四轴结果投影。正常答案中的每条 citation 都来自本轮 generation-visible Evidence；无候选、语义不足、ACL/revision 失效、投毒内容、retriever 不可用或 citation 篡改均得到可验证且不泄露的失败结果。

### 必须完成

- 建立 P3 可直接调用的 RAG AnswerFlow 深 interface；调用者不需要编排 Gate、ledger、Composer 和 validator。
- 实现 Shared Answer Evidence Gate 的确定性硬约束与保守充分性合同，区分可以回答、证据不足、安全拒绝和技术不可用。
- 只把 Gate 允许且实际交给 Composer 的 Evidence 推进为 `generation_visible`，并固化本次 generation context identity。
- 实现离线确定性、证据绑定的 Composer；输出结构化 claim draft 和支持关系，不调用模型、不接受自造 citation slot。
- 由代码分配 claim/citation identity；Citation Validator 成功后才推进 `cited` 并公开答案。
- 形成 route/execution/answer/safety 四轴运行结果、稳定 reason 和最小安全投影；未验证 claim、正文、ACL 内部原因和未授权 identity 不得进入投影。
- 建立独立版本化 RAG answer/citation Eval family，一次 AnswerFlow 执行支撑 Gate、stage、citation、answer、state、safety 和 runtime assertions。
- 保持 M31 `phase4-v1`、M32 `phase4-rag-retrieval-v1`、M27 v3 和历史 artifact/report 只读。

### 建议完成

- 记录 Knowledge Tool、Gate、Composer、validator 的调用次数、局部耗时、context 数量/字符规模、release/corpus/adapter/composer/policy identity。
- 提供安全的 citation 用户视图和 `docs_used` 兼容投影函数，供 P3 接 `AgentResponse` 时直接复用；本模块不修改现有 Pydantic 响应。
- 对确定性支持范围给出显式 capability/reason，避免把 extractive baseline 描述成通用自然语言生成器。

### 条件触发

- **触发条件**：M33 required answer/citation Gate 全绿，并形成足够证据判断 M32 deterministic adapter 是否可作为 P3 首个默认 Knowledge Tool adapter。
- **允许动作**：整理 G4 候选证据，向用户比较“将 deterministic adapter 设为 P3 初始默认”和“暂缓 P3、先增加检索候选”的影响；只在用户确认后更新长期默认结论。
- **未触发时**：不选择 P3 默认 adapter，不实验 embedding/hybrid/rerank/parent-child，不进入 P3 Router。

### 明确非目标

- `/api/query`、`AgentResponse`、Streamlit、全局 JSONL Trace 的实际接线。
- Router、LangGraph Harness、Text2SQL Tool、Hybrid、thread、Loop 或通用 Context Builder。
- 远程 LLM Composer、远程充分性判断、Eval Judge、embedding/rerank、Milvus 或 LangFuse Cloud。
- 开放语义答案质量、长文/PDF、parent-child、query rewrite 或 RAG Subgraph。
- 生产 JWT/OAuth，或把请求体/前端选择的 `user_role` 升级为可信文档 caller。
- 修改 corpus、release、ACL、outbound 默认、模型默认或历史 Eval 合同。

## 5. 关键合同

### C1：RAG AnswerFlow 深 interface 与控制权合同

- 输入：非空问题、明确来源的 `TrustedCaller`、run identity、Evidence 用途/回答要求、有限预算，以及可注入的 Knowledge Tool；输入不包含 HTTP request、公开响应对象或完整会话历史。
- 成功输出：不可变 RAG 运行结果，包含四轴状态、稳定 reason、验证后的回答/claims/citations、最终 Evidence ledger、各步骤安全 execution refs 和最小公开投影。
- 失败语义：Knowledge Tool、Gate、Composer 或 validator 的失败先保留结构化 owner/root cause，再由本流程唯一投影 answer/safety；编程错误和非法合同输入失败关闭，不能吞成普通 `insufficient_evidence`。
- 必须保持的不变量：AnswerFlow 是薄应用层的唯一 controller；Knowledge Tool 只取证，Gate 只裁决 Evidence，Composer 只产 claim draft，Validator 只校验 citation；任何子模块都不能自行构造最终四轴状态或公开答案。
- 本模块不冻结的实现细节：具体文件/类名、同步或异步形态、P3 Graph node 布局和 HTTP dependency injection 方式。

### C2：Shared Answer Evidence Gate 与 generation context 合同

- 输入：C1 请求、M32 `RetrievalOutcome`、selected Evidence、pre-generation decisions、当前 active release/runtime identity，以及本轮结构化 Evidence requirement。
- 成功输出：稳定 `GateDecision`、只包含允许 Evidence 的最小 generation context、context identity，以及从 selected 单步推进到 `generation_visible` 的新 ledger。
- 失败语义：无候选或结构化支持不足为 `insufficient_evidence`；revision 失效为证据不足；caller/ACL/用途或文档指令安全失败为 blocked；retrieval/provider 技术不可用保持 execution root cause。Gate deny 时不调用 Composer，也不产生 generation-visible/citation。
- 必须保持的不变量：硬约束由确定性代码裁决；远程 sufficiency 未授权时只能使用本地保守判断；只有 Evidence 真正作为本次 Composer 输入时才能推进 `generation_visible`；candidate、未选中、失效或未授权 Evidence 永不进入 context。
- 本模块不冻结的实现细节：充分性内部规则、文本扫描细节、阈值和未来远程判断 adapter；任何未来变化必须保持同一 GateDecision 语义并经 Eval 证明。

### C3：证据绑定 Composer 与 claim draft 合同

- 输入：C2 已批准的 generation context、问题/已确认条件、有限输出预算和 composer runtime identity。
- 成功输出：稳定有序、非空的结构化 claim drafts；每条包含用户可见文本和声明的支持 Evidence/anchor，但不包含调用者或模型自造的最终 citation slot。
- 失败语义：空输出、未知/重复 Evidence、越预算、未支持内容或异常为结构化 composer failure；不得回退到模型常识、原始错误文本或未经验证的 context 直出。
- 必须保持的不变量：Composer 只看 generation-visible Evidence；首版离线且确定性；文档正文始终是数据，不能改变控制流、请求 Tool 或伪造系统/citation 指令；同输入/runtime identity 产出一致。
- 本模块不冻结的实现细节：句子切分、claim 合并、措辞模板和未来远程 Composer 的 prompt/model；这些属于后续效果实验，不进入当前长期默认。

### C4：Citation、最终答案与安全投影合同

- 输入：C3 claim drafts、代码分配的 claim/citation slots、C2 generation-visible ledger、当前 active entries 和对应 pre-generation authorizations。
- 成功输出：全部通过的 validated citations、推进到 `cited` 的 ledger、只由已验证 claims 组成的回答，以及不含正文/内部策略的 citation 用户视图和兼容 `docs_used` 投影。
- 失败语义：unknown slot/Evidence、跨 run、错误 stage/revision/anchor/ACL、缺引用、额外引用或部分验证失败统一为 `citation_invalid`；整份未验证回答不公开，不返回“部分看似可信”的 citation。
- 必须保持的不变量：slot/claim identity 由代码分配；citation 只能指向本轮 generation-visible Evidence；用户 citation 可回到当前 active revision/anchor；`docs_used` 只能从 validated citations 派生，不能反向构造 Evidence。
- 本模块不冻结的实现细节：未来前端 citation 样式、展开正文、URL 形态和已撤销历史正文保留期。

### C5：四轴结果与 RAG Answer Eval 合同

- 输入：一次真实 AnswerFlow 执行产生的安全 ExecutionEvidence、版本化 Scenario catalog、caller/corpus/release/adapter/composer/policy/runtime identity 和 typed assertion specs。
- 成功输出：route/execution/answer/safety、Gate、generation stage、claim/citation integrity、结构化事实支持、非泄露、调用次数和 runtime identity assertions；required Gate 与开放语义 advisory 视图分开。
- 失败语义：技术不可用导致答案质量不可观察时相关效果 assertion 为 `not_observed`，但 root-cause/state 合同仍可判断；预期 insufficient/blocked 是已观察产品行为；completed artifact 缺失、额外、重复或 identity 不匹配时整体拒绝。
- 必须保持的不变量：一个 Scenario 只执行一次 AnswerFlow，scorer 不重跑 retrieval/Composer；确定性安全、citation 和状态进入 required；开放措辞/语义支持度只作 advisory；旧 Eval family/artifact 不改写、不混算。
- 本模块不冻结的实现细节：真实 LLM judge、长期 baseline 登记、P3 Router assertions 和 held-out 数量。

## 6. 工作切片与执行顺序

### M33-A：合同、notes 与开工基线

- 优先级：必须完成
- 依赖：已确认 G-M33=A；M31 active release/caller/ACL/Evidence；M32 Knowledge Tool/retrieval family
- 实施内容：创建 `m33-notes.md` checklist；记录 Git/status、active/corpus、M31/M32 Gate 和测试基线；冻结 C1-C5 的 result、Gate、claim、citation、reason 与安全投影枚举。
- 关键合同：C1-C5
- 交付物：开工素材、closed-world reason/status/Scenario 清单、现有 consumer 反向检查。
- 验证方式：静态 identity 对账；M29 真值表、M31/M32 类型与本计划逐项映射。
- 完成门：同一失败的 owner、四轴投影或可见性仍有歧义时不得进入实现。

### M33-B：Shared Gate 与真实 generation-visible 上下文

- 优先级：必须完成
- 依赖：M33-A、M32 selected Evidence/pre-generation decisions、active release loader
- 实施内容：实现确定性 Gate、最小 generation context 和 context identity；检查同轮、stage、用途、revision、ACL、结构化充分性和文档指令安全；在同一 Composer 调用边界推进 `generation_visible`。
- 关键合同：C2
- 交付物：GateDecision、generation context、安全 diagnostics/runtime refs 和聚焦反例测试。
- 验证方式：正常 selected、candidate-only、缺 decision、跨 run、旧 revision、错误用途、语义不足、投毒文本、remote sufficiency deny/fallback case。
- 完成门：Gate deny 路径 Composer 调用为零且 ledger 不越过 selected；allow 路径 context 与 generation-visible Evidence 精确一致。

### M33-C：离线 Evidence-bound Composer 与 claim slots

- 优先级：必须完成
- 依赖：M33-B
- 实施内容：实现确定性 Composer 和结构化 claim draft；保证只消费 generation context、固定输入稳定、输出有界；由流程代码为 claim 分配稳定 identity/slot 并构造 citation draft。
- 关键合同：C3、C4
- 交付物：首个离线 composer runtime、claim drafts、slot/draft 编排和篡改测试。
- 验证方式：质量退款、GMV 口径、多 Evidence 顺序/去重、空输出、未知 Evidence、越预算、伪 citation/Tool 指令、异常注入。
- 完成门：Composer 无网络/authority/legacy 旁路，不接收 candidate ledger，不拥有最终 citation 或 answer 状态控制权。

### M33-D：Citation Validator 接线与四轴 RAG 结果

- 优先级：必须完成
- 依赖：M33-C、M31 validator、当前 active entries
- 实施内容：把 claim slots/drafts 接入现有 validator；成功后构造验证回答、citation 用户视图和 `docs_used` 兼容投影；失败时丢弃未验证答案；集中完成四轴状态/reason 映射。
- 关键合同：C1、C4
- 交付物：RAG AnswerFlow 深 interface、不可变运行结果、最终 ledger 和安全投影。
- 验证方式：合法 citation、多 claim 复用 Evidence、unknown/selected-only/跨轮/错误 anchor/revision/ACL、部分 citation 缺失、状态真值表和非泄露 snapshot。
- 完成门：只有 validator 全部成功的 claims 可见；所有结果只通过 AnswerFlow interface 验收，调用者无需自行编排内部步骤。

### M33-E：独立 RAG Answer/Citation Eval

- 优先级：必须完成
- 依赖：M33-D、M29 Scenario blueprint、M32 retrieval ExecutionEvidence 纪律
- 实施内容：新建独立 answer/citation contract family；至少覆盖质量退款、GMV 定义、no candidate、语义不足、ACL 非泄露、prompt injection、stale revision、retriever unavailable 和 citation invalid；同次 AnswerFlow evidence 投影 required/advisory assertions。
- 关键合同：C5
- 交付物：Scenario catalog/runner/projector、closed-world artifact、required Gate 和分层 summary。
- 验证方式：正常 completed artifact；缺/多/重 Scenario/replicate/assertion、runtime/corpus/release/policy/composer identity 篡改反例；重复执行确定性对账。
- 完成门：M32 retrieval family 的 6 Scenario/20 required/3 advisory 定义不变；答案结果不回填 retrieval artifact。

### M33-F：回归、G4 证据包与交接

- 优先级：必须完成
- 依赖：M33-A 至 M33-E
- 实施内容：按聚焦顺序运行测试和静态检查；把实现决策、失败修正和真实数字写入 notes；整理 G4 所需闭环可靠性、适用边界和候选比较材料，但不替用户选择默认。
- 关键合同：C1-C5
- 交付物：验证快照、文件清单、G4 决策材料和 P3 handoff。
- 验证方式：按 runbook 使用项目 Python与 `.agent_work/temp/` 新 basetemp；聚焦、P1/P2、API/Text2SQL/Eval 受影响回归、全仓 pytest、compileall、`git diff --check`。
- 完成门：不调用真实 provider/Milvus/LangFuse；确定性门全绿；默认配置、现有 API 和历史 artifact 无变化；G4 状态如实记录为已确认或仍待确认。

## 7. 决策门

### G-M33：M33 与公开 API 的模块边界（已确认）

#### 方案 A：先完成可信回答深 module，P3 再接 HTTP（用户已选择）

- 做法：M33 完成 Gate、deterministic Composer、generation-visible/cited、四轴结果和安全投影，不修改 `/api/query`；P3 Router/Harness 通过同一 AnswerFlow interface 接入。
- 影响：M33 可以独立证明回答可信性和 citation 闭环，避免临时 route hint；P2 的公开 API 交付推迟到 P3 接线，不把 M33 写成完整公开 RAG。
- 适用条件：当前没有可信 HTTP caller 或 Router，而 M32 已提供稳定 Knowledge Tool seam。
- 风险：模块结束后仍需通过内部调用/Eval 演示，普通 HTTP 用户暂时看不到 RAG。

#### 方案 B：M33 增加显式 RAG 请求开关并接 `/api/query`（未选择）

- 做法：扩展 QueryRequest 或增加临时入口，由调用方显式选择 RAG，并额外设计 HTTP trusted caller resolver。
- 影响：本模块即可 HTTP 演示，但会新增 P3 可能废弃的公开合同，并把身份、Trace、兼容响应和路由责任提前耦合。
- 适用条件：用户要求 M33 必须以公开 HTTP demo 验收，并接受临时合同的迁移成本。
- 风险：route 可被客户端控制；错误使用 `user_role` 会直接造成文档越权；模块范围显著扩大。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：让回答能力成为一个深 module，P3 只负责“何时调用”，不需要理解“怎样生成可信答案”；同时守住顶层控制权和 caller 安全。
- 用户确认前允许推进：只允许调查和形成计划。
- 用户确认前禁止推进：生产代码、测试、Eval 和 notes 实施。
- 需要确认的时点：M33 plan 定稿前。
- 重开决策的条件：用户明确要求 M33 必须提供公开 HTTP demo，或实现调查证明 AnswerFlow 离开 HTTP 无法独立验收。

用户已确认 **G-M33 = 方案 A**。

### G4：首个 Knowledge Tool 运行时默认 adapter（实施后确认）

#### 方案 A：将 M32 deterministic adapter 设为 P3 初始默认

- 做法：M33 回答/citation required Gate 全绿后，把当前本地 deterministic adapter 作为 P3 第一条 RAG baseline；保持可替换，不宣称语义最优。
- 影响：P3 可直接进入 Router/Harness，默认链路离线、稳定、可解释。
- 适用条件：canonical P2 闭环可靠、已知词法适用范围可接受，且没有必须先解决的稳定漏召回失败簇。
- 风险：中文开放问法、长文和语义同义表达能力有限；默认只能代表首个工程 baseline。

#### 方案 B：暂不选择 P3 默认，先立新的检索候选模块

- 做法：M33 完成后保持 adapter 仅为 P2 baseline，根据真实 dev 失败簇规划 embedding/hybrid/rerank 等单变量候选和 held-out。
- 影响：P3 主线暂停，但可以先补检索效果证据。
- 适用条件：M33 发现当前 adapter 无法覆盖关键闭环 Scenario，且失败不是 corpus、ACL、gold 或实现 bug。
- 风险：可能在没有稳定失败簇时提前扩大检索复杂度，延误 Router/Agent 主线。

#### 建议与确认时点

- 建议：当前不预选；若 M33 required 全绿且没有合格检索失败簇，届时建议方案 A。
- 建议理由：G4 依据是完整回答/citation 可靠性，不是 M32 单项 retrieval 通过；当前尚缺 M33 执行证据。
- 用户确认前允许推进：M33 全部确定性实现、测试、Eval 和 G4 证据整理。
- 用户确认前禁止推进：把任一 adapter 写成 P3 长期默认、修改默认配置或启动远程检索实验。
- 需要确认的时点：M33 required Gate 与适用边界可展示后、模块收工前。
- 重开决策的条件：后续出现可复现检索失败簇、新 corpus/长文、adapter 候选或 held-out 对照证据。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 AnswerFlow 正常闭环 | 授权 caller + quality/metric gold 问题 + counting dependencies | 一次 Tool、一次 Gate、一次 Composer、一次 validator 路径；四轴为 rag/completed/complete/passed | 必须完成 |
| C1 失败 owner/状态 | no candidate、semantic insufficient、ACL deny、retriever/composer unavailable、citation invalid | root cause 不互相冒充；execution/answer/safety 正交；未验证答案不可见 | 必须完成 |
| C2 Gate 硬约束 | candidate-only、跨 run、用途错误、缺/拒绝 authorization、inactive revision | 任一不合格 Evidence 不入 context；Composer 调用为零；ledger 不越过 selected | 必须完成 |
| C2 generation-visible 真实性 | capture Composer 输入与 ledger/context identity 对账 | 只有实际传入 Composer 的 selected Evidence 推进 generation-visible，顺序和 identity 精确一致 | 必须完成 |
| C2 充分性与投毒 | 结构化事实不足、伪系统/Tool/citation 指令 fixture | 不足返回 insufficient；投毒不改变控制流或产生越权 Tool，公开投影不回显危险正文 | 必须完成 |
| C3 deterministic Composer | 固定输入重复、多 Evidence、顺序/预算/异常/非法 support | 输出稳定有界；claims 只引用输入 Evidence；无网络、authority 或 legacy 旁路 | 必须完成 |
| C4 citation 完整性 | legal、unknown、selected-only、cross-run、wrong anchor/revision/ACL、缺/额外 slot | 只有合法 generation-visible Evidence 可 cited；任一失败整份答案不公开 | 必须完成 |
| C4 用户/兼容投影 | validated citation 与安全 projection snapshot | 用户 citation 可回查 revision/anchor；`docs_used` 只由 validated citation 派生且无正文/ACL 细节 | 必须完成 |
| C5 一题一次执行 | dependency counters + 多 typed assertions | 一个 Scenario 只执行一次 AnswerFlow，全部 scorer 共享同一 ExecutionEvidence | 必须完成 |
| C5 closed-world artifact | 缺/额外/重复 Scenario、replicate、assertion、effect 与 identity 反例 | 任一不一致整体拒绝，不投影可信 Gate | 必须完成 |
| answer/citation 分层 | 结构化事实 required + 开放措辞/support advisory | required 不被 advisory 覆盖；技术不可用效果项为 not_observed | 必须完成 |
| 历史/API/default 边界 | M31/M32/M27、现有 AgentResponse/API、governance 配置回归 | 旧合同/artifact 不变；`/api/query` 仍保持当前 SQL 行为；无远程 Knowledge 放行或默认变化 | 必须完成 |
| 代码与回归 | 聚焦 → 受影响 → 全仓 pytest；compileall；diff check | 新增 required 全通过；skip/warning 如实记录；无真实 provider 调用 | 必须完成 |
| G4 | M33 required Gate、失败簇和 runtime/cost 摘要 + 用户选择 | 只有用户确认后才记录 P3 默认；未确认时保持候选状态 | 条件触发 |

聚焦测试顺序固定为 Gate/stage → Composer/claim → citation/final result → answer Eval → M32 retrieval → M31 governance/Evidence/release → API/Text2SQL/Eval 受影响回归 → 全仓确定性测试。失败先记录和定位，不用改 assertion、重跑外部服务或扩大 corpus 掩盖。

本模块不运行真实 LLM、remote sufficiency/generation/judge、embedding/rerank、Milvus、LangFuse Cloud 或公开 HTTP RAG Eval。因此验收不包含开放答案质量、真实 provider 可用性、语义检索收益、HTTP 路由/caller、P3 Graph 或远端成本结论。

M27 v1/v2/v3、M31 `phase4-v1`、M32 `phase4-rag-retrieval-v1` 的合同、artifact 和报告全部只读。M33 新 family 可以消费相同 active release 和调用接口，但不能修改旧 Scenario 集、补写旧字段或混算 Gate。

## 9. 依赖与交付物

### 依赖

- M29 已确认的 G0=A、G1=A、G1-O=A、四轴真值表、reason registry 和 P2 Scenario blueprint。
- M31 trusted caller、ACL/outbound、active immutable release、typed Evidence、ledger 和 Citation Validator。
- M32 Knowledge Tool、selected Evidence、pre-generation decisions、safe diagnostics 和 retrieval ExecutionEvidence。
- `docs/phase4-roadmap.md` P2、跨里程碑不变量、G4 与 `docs/phase4-reference.md` Evidence/citation、Eval 能力卡。
- `docs/state/runbook.md` 的项目 Python、临时目录、默认配置和真实 Eval 纪律。

### 交付物

- 一个可被 P3 直接调用的 RAG AnswerFlow 深 interface 和不可变运行结果。
- Shared Answer Evidence Gate、generation context identity 与真实 `generation_visible` 迁移。
- 离线 Evidence-bound Composer、结构化 claim draft 和代码分配的 citation slots。
- Citation Validator 编排、`cited` ledger、验证回答、citation 用户视图和兼容投影函数。
- 独立版本化 RAG answer/citation Scenario/Eval family、required Gate 与 advisory 视图。
- 聚焦/回归测试、故障注入、`m33-notes.md` 过程素材、G4 证据包和 P3 handoff。

只冻结交付物职责，不提前固定具体文件名、类名、目录拆分、句子切分算法、阈值或未来模型参数。实现时优先让测试和调用者穿过 AnswerFlow interface；内部 Gate/Composer/validator 只保留确有独立变化或安全语义的 seam。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：公开 `/api/query` RAG 路径、可信 HTTP caller、Router/LangGraph、全局 Trace 接线、真实远程生成和开放语义质量。
- 下一模块可直接消费的产物：AnswerFlow interface、四轴 RAG 结果、安全响应/citation 投影、Tool/Gate/Composer/validator execution refs 和 answer Eval fixtures。
- 下一步路线：M33/G4 完成后进入 P3 顶层 LangGraph Harness 与 Router，由唯一 controller 选择 SQL/RAG 并把可信 caller 和结果投影接入 `/api/query`；不能在 P3 重新实现一套 Gate/Composer/Validator。
- 后续需要根据真实失败重新规划的内容：开放问法下的 answer/retrieval 失败簇、远程 Composer/outbound、held-out decision set，以及 embedding/hybrid/rerank/parent-child 等单变量候选。
- 可能存在的风险：确定性 extractive Composer 容易忠实但不够自然；结构化充分性策略可能保守；追加后的 22 条短知识仍不能代表长文；P3 接 HTTP 时仍需同时解决 trusted caller、兼容响应和安全 Trace。
- 路线表述边界：M33 完成后可以宣称“内部可信 RAG 回答/citation baseline 成立”，不能宣称“普通 `/api/query` 已支持 RAG”或“Phase 4 RAG 已有真实 LLM 质量基线”。

## 11. 开工条件

- 开工前无需确认：G-M33=A；继续只读 active release；继续使用 M32 deterministic adapter 和 M31 安全接口；Knowledge 远端用途全部 deny；不接 HTTP/Graph/Router/Hybrid；历史 Eval 只读。
- 实施中需要确认：仅 G4；M33 required 证据形成后再由用户选择 P3 初始默认 adapter。G4 前不阻塞 M33-A 至 M33-F 的实现与验证。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；尤其不得自行新增 route hint、信任请求体 role、开放远程 Document Evidence、改变 citation 失败语义、选择默认 adapter 或改写旧 Eval family。

## 12. 2026-08-15 内容追加（仍属于 M33）

- 用户确认方案 A 后，在不改变 M33 核心合同、G4 默认 adapter、ACL/outbound 或公开 API 边界的前提下，补充 8 条由 `metrics.yaml` 派生的指标说明，以及 3 份“实时事实、证据不足转人工、优惠券实际适用性”的边界文档。
- 新内容不得创造金额、时限、优惠门槛或用户资格；指标口径仍以 `metrics.yaml` 为唯一 authority，边界文档只说明何时查实时系统、专项规则或转人工。
- 完整 catalog 从 11 条增至 22 条，并通过 candidate 隔离验证后发布 immutable release；新增测试归入 M33，不另立模块。
- 验收仍以原 M33 AnswerFlow/Evidence/citation 合同为主，同时检查新增内容可检索、可引用、旧 Eval family 分母和安全行为不回归。
