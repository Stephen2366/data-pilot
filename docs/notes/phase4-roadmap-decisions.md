# DataPilot Phase 4 Roadmap 决策备忘录

> **文档定位**：本文服务于 Phase 4 roadmap 编写前的决策确认。它回答“阶段四要解决什么问题、哪些语义必须先定、哪些技术选择应交给实验”，不是 roadmap 草稿，也不安排模块编号、文件结构、施工顺序或参数。
>
> **分析基线**：2026-08-10。结论基于 DataPilot 当前代码与状态文档、`docs/phase4-reference.md`、总路线图的阶段四原始设想，以及其中已定点复核的参考项目源码结论。

## 0. 当前商讨出的阶段四的大致方案

> **商讨更新（2026-08-11）**：用户已确认阶段四需要使用 LangGraph。本文据此将 LangGraph 从候选实验调整为顶层编排主线；复杂循环、持久化和多 Agent 等能力仍不随之自动进入范围。
>
> **本次优化（2026-08-11）**：为增强阶段四的 Agent 工程与面试表达，主线补入有界 Agent Loop、结构化工具失败恢复、thread 内短期记忆、有限多轮和最小上下文治理；跨会话长期记忆、开放 ReAct、复杂 compact、多 Agent 等单列为阶段四后按时间补强。
>
> **RAG 讨论吸收（2026-08-11）**：进一步补强“是否需要重新取证”、Evidence Gate 双层裁决、受控 Query Rewriting、Context 四阶段证据链、Agentic RAG typed assertions，以及运行成本与用户反馈关联；不采用未经验证的效果数字、默认 HyDE/多跳、知识自动沉淀或提前平台化。

### 方案定位

阶段四准备在现有 Text2SQL 基础上补齐 Knowledge/RAG，并使用 **LangGraph 作为顶层 Agent Harness**。LangGraph 负责保存运行状态、选择和调度工具、观察 Evidence 或错误、决定继续、澄清或停止，以及组织 Hybrid 汇合；它不负责替代 SQL Guard、知识检索、权限校验或 Evidence 生成等专业逻辑。

可以把整体关系理解为：

```text
用户问题
  → 读取身份与 thread 内短期状态
  → Router 判断是否已有有效 Evidence、是否需要重新取证
      ├─ 无需取证：复用仍有效且有权限的 Evidence
      └─ 需要取证：选择 SQL、RAG、Hybrid，或先澄清
  → 调用受控 Tool
      ├─ Text2SQL Tool → SQL Evidence / 结构化错误
      └─ Knowledge Tool → Document Evidence / 结构化错误
  → Observation + Evidence Gate
      ├─ 证据充分 → 生成答案
      ├─ 可恢复 → 改写或有限重试 → 再观察
      ├─ 条件不足 → 暂停并澄清
      ├─ 仅部分成功 → 返回有边界的 partial result
      └─ 不可恢复 / 越权 → 停止或拦截
  → 更新必要的短期状态
  → 统一输出 AgentResponse、Trace 与 Eval evidence
```

这里坚持一个重要原则：**LangGraph 管“下一步做什么”，SQL 和 RAG module 管“各自怎么把事情做好”。** 现有 Text2SQL pipeline 继续作为一个完整 Tool 被调用，不会为了画 Graph 被拆成大量只转发参数的浅节点；RAG 内部的检索、权限和引用也封装在自己的 interface 后面。这样既能展示真正的 Agent Loop 和 tool use，又不会破坏已经稳定的 Text2SQL 链路。

### 大致建设路线

#### 1. 先准备可信知识与 Evidence 地基

- 将当前 Python seed 中的 10 条短知识作为草稿，整理、审查并适度扩写成正式知识文档；首版优先使用便于 Git 审查和引用定位的 Markdown，PDF 作为后续增强。
- 明确文件是知识原件，数据库记录和检索索引是可重建的运行时投影，避免同一政策出现两个无法判断真假的版本。
- 先确定 document、revision、chunk、anchor、权限和 corpus identity 的稳定语义，再讨论具体切分与检索参数。
- 建立统一 Evidence interface：Document Evidence 保存实际检索片段和来源，SQL Evidence 保存 SQL 结果及其运行身份；citation 只能引用本次生成器实际看到且有权使用的 Evidence。
- 正式 corpus 按目标 Scenario 和 gold Evidence 建设，不以文档数量作为完成标准；持续区分“缺少权威知识”“已有知识但检索不到”和“检索到了但回答不会使用”。
- 入库时按知识形态保留标题、章节、列表、表格列名和原文位置；短政策优先作为天然知识单元，复杂语义切分和 parent/child 由长文档实验决定。

这一部分不是单纯“准备几份文档”，而是在给 RAG、Hybrid、Trace 和 Eval 建立共同事实基础。没有这层基础，后续即使回答看起来正确，也无法证明它为什么正确。

#### 2. 建立独立、可验证的 RAG Tool

- RAG 只负责文档知识：先按调用者权限和文档状态过滤，再检索候选 Evidence，最后返回 Document Evidence 或结构化错误。
- Knowledge Tool 对外保持较小 interface，内部封装关键词/语义检索、权限复核和 citation 所需来源；不把 embedding、向量搜索、rerank 分别暴露成大量浅工具。
- 找不到足够证据时返回 `insufficient_evidence`，不依赖模型常识补齐公司政策。
- 检索前过滤与生成前复核都由确定性代码执行；文档中的伪系统指令、伪 citation 和诱导工具调用一律视为不可信内容。
- 首版先跑通稳定基线。是否增加混合检索、rerank、parent/child 或 query rewrite，由固定 corpus 和 RAG Eval 决定。

RAG 与 Text2SQL 是两条独立链路：前者取得文档 Evidence，后者取得数据库 Evidence。它们可以分别测试、分别失败，也可以被 LangGraph 组合使用。

#### 3. 建立 LangGraph Harness、Router 和统一状态

- Router 先判断当前问题是否需要重新取证，再按“需要什么证据”选择 SQL、RAG、Hybrid 或暂不可执行，而不是只做关键词分类。
- “已有上下文可以回答”必须建立在仍有效、仍有权限且能支持当前 claim 的 Evidence 上；模型自称知道公司政策不能成为跳过检索的理由。
- Text2SQL 与 Knowledge/RAG 以结构化 Tool interface 接入：成功返回 typed Evidence，失败返回稳定错误类型，Graph 不解析各自内部实现细节。
- Graph state 保存调用者身份、route 决策、工具观察结果、Evidence reference、citation、回答状态、安全状态和可诊断错误；后端配置、模型内部细节和完整敏感原文不应成为所有节点都必须理解的公共状态。
- `route` 只表示选择了哪条能力路径；澄清、部分成功、证据不足、拦截和失败由独立回答状态表达。
- Router 无法可靠判断时保守进入澄清或不支持状态，不默认落到 RAG，也不把路由模型错误伪装成业务知识不存在。

LangGraph 在这里承担 Harness 的调度职责，但 DataPilot 自己定义 Tool 合同、失败策略、上下文选择和 Eval 语义。这样面试时不仅能说明“用了 LangGraph”，还能解释一次 Agent 运行如何选择工具、保存 observation、恢复失败并终止。

#### 4. 加入有界 Agent Loop 和工具失败恢复

- Tool 执行后不直接生成最终答案，而是先由 Evidence Gate 判断证据是否充分、权限是否允许、结果是否仍需要其他工具。
- Evidence Gate 分两层：确定性代码检查 Evidence 是否存在、授权、版本有效、citation 可绑定和必需分支是否完成；结构化模型判断这些 Evidence 是否足以回答当前问题。模型判断不能覆盖权限与安全裁决。
- 只有明确可恢复的失败才能进入循环，例如检索问题表达不佳时改写后再查；外部服务不可用、权限不足或业务知识不存在不能靠换关键词无限重试。
- 每次循环必须记录稳定 reason code；只有约定的可恢复原因才能触发 Query Rewriting，改写结果还要保留与原问题、已确认条件和本轮检索结果的关系，防止越改越偏。
- 首版 Query Rewriting 只处理口语别名、已确认条件补全和明显检索表达问题；HyDE、step-back 和自动多跳拆解不作为默认路径。
- Loop 必须有预算和稳定终止条件：证据充分就回答，条件不足就澄清，单支可用就按合同返回 partial，不可恢复就停止或拦截。
- 不保存或展示模型原始思维链，只记录结构化的 Tool 选择、Observation、Evidence Gate 结果和下一步动作。
- Eval 检查是否选择了正确 Tool、是否进行了无意义重复调用、失败后是否走了正确恢复路径，以及是否在应停止时终止。

这形成受控的 `Action → Observation → Evidence Gate → Next Action` 循环，体现 ReAct 思想，但不开放无限自主探索。

#### 5. 完成保守的 Hybrid 组合

- Hybrid 不复用 SQL QueryPlan 的具体结构做万能计划，只保留一个很薄的跨能力计划：需要哪些子任务、依赖什么 Evidence、哪些分支是组合结论的必需条件。
- SQL 和 RAG 分支返回原始结构化 Evidence，不先各写一段自然语言再让模型二次总结。
- 只有 SQL 与文档两个必需分支都成功，才能生成同时包含“数据表现”和“政策建议”的组合结论。
- 一支失败时可以保留另一支安全且独立成立的结果，但必须标成 partial，并明确缺少什么；不得继续生成看似完整的跨来源建议。
- 合成、图表或长报告失败时，不重复执行已经完成的分支；优先保留表格、文档引用和可解释的部分结果。

LangGraph 在这里负责分支、汇合和失败流转，Evidence Gate 负责判断是否满足合成条件，模型只负责在允许的证据范围内组织语言。

#### 6. 增加 thread 内短期记忆和有限多轮

- 支持两类高价值场景：用户补充澄清条件后恢复任务，以及用户基于上一轮结果继续追问。
- 短期记忆只在同一 thread 内保存当前任务、必要条件、已确认指代、有效 Evidence reference 和安全摘要，不把完整历史无限追加到 prompt。
- 重新使用旧 Evidence 前检查 document revision、数据库快照、调用者身份和权限；旧证据失效时重新取证，而不是把历史答案当成永久事实。
- 使用 LangGraph 的 thread 状态或轻量 checkpoint 支持暂停与恢复，但不在阶段四建设跨会话用户画像和通用长期记忆平台。

#### 7. 建立最小上下文治理

- State 保存可审计运行事实，Context Builder 只为当前节点选择最小必要上下文；“系统保存了什么”和“模型这一刻看见什么”必须分开。
- 检索证据链显式区分四个阶段：Tool 返回的候选 Evidence、过滤/去重后选中的 Evidence、实际进入生成器的 Evidence，以及最终被 citation 使用的 Evidence；不能用一个 `docs_used` 混掉全过程。
- SQL 节点不接收全部文档，RAG 节点不接收完整数据库结果，生成节点只接收最终选中的 Evidence。
- Tool 的长结果优先转成结构化摘要、结果 fingerprint 和 Evidence reference；Trace 可以更完整，但不能原样回灌模型。
- 压缩或摘要不能替代原始 Evidence reference；政策例外、时间条件、适用角色和 SQL 口径等高风险信息必须能够回到原证据复核。
- 对话增长时先裁剪无关历史、保留已确认条件和有效证据；复杂多层 compact 等到真实长对话 Eval 证明有需要后再补。

#### 8. 将安全、Trace 与 Eval 一起收口

- 文档采用公开或显式角色 allowlist，检索前过滤、生成前复核；SQL 安全和文档安全共享调用者身份，但各自保留独立实现。
- 所有远程 embedding、rerank、生成模型和 Cloud 观测都经过 outbound policy；不同外部接收方分别授权，默认不发送完整文档、数据库结果或敏感 Trace。
- LangGraph 每次运行留下 route、Tool Call、Observation、循环次数与终止原因、四阶段 Evidence 的安全投影、citation、分支错误和 resolved runtime identity；同时记录 Tool 延迟、调用次数、上下文规模和可用的 cache hit/miss，但不在阶段四提前建设分布式缓存或高并发平台。
- trace id 作为运行证据关联键：用户反馈、Eval assertion、corpus/document revision 和失败归因都回到同一次运行；JSONL 继续作为本地主事实，外部观测保持可选旁路。
- RAG/Hybrid Eval 继续使用“一题一次执行、多条 typed assertion 共享同一证据”。除路由、citation、Hybrid、ACL 和出站外，还应覆盖是否需要检索、Evidence 复用、Tool 选择、Query Rewriting、Evidence Gate 充分性、失败恢复、Loop 终止、短期记忆指代、上下文利用和裁剪后的条件保真；开放语义 judge 先作为旁证。
- LLM Judge 或反思判断自身失败时，对应开放语义 assertion 记为 `not_observed`，不能改变确定性安全、权限、引用真实性和循环预算的 Gate。

### 阶段四完成后应形成的能力

阶段四完成后，DataPilot 应能稳定演示三类问题：

- 数据问题由 Text2SQL 回答，并保留现有 SQL 安全与可解释 Trace；
- 政策问题由 RAG 回答，答案带可回查 citation，缺证据或无权限时能够正确停下来；
- 数据加政策问题由 LangGraph 编排两条链路，组合原始 Evidence 得出有出处的建议，并能在任一分支失败时返回诚实、可解释的部分结果。
- Tool 失败或证据不足时，Agent 能在有限范围内重试、澄清、部分返回或停止，并解释终止原因；
- 同一 thread 内可以完成澄清恢复和基于上一轮结果的追问，同时控制进入模型的上下文。
- Agent 能说明本轮为什么需要或不需要重新取证、哪些 Evidence 进入了生成器、最终引用了哪些来源，以及用户反馈关联到哪次运行。

本阶段的重点不是一次加入所有 Agent/RAG 技巧，而是形成一条可以演示、可以评测、可以解释失败的有界 Agent 主线。具体模型、向量后端、切分参数、召回数量、阈值、rerank 和高级 Graph 能力仍保留为后续实验决策。

### 阶段四结束后再根据时间补强

以下能力有面试价值，但会显著增加事实源、隐私、状态和 Eval 复杂度，不进入阶段四主线：

- **跨会话长期记忆**：用户偏好、历史任务摘要和长期知识召回，同时补齐过期、纠错、删除和权限变化语义；
- **复杂 context compact**：自动摘要、多层压缩和超长会话治理，在长对话 Eval 证明当前裁剪策略不足后再建设；
- **更开放的 ReAct / 研究循环**：允许更多自主 Tool 选择和多轮研究，但仍需要预算、终止和可审计 Evidence；
- **多 Agent 协作**：只有出现能够证明角色分工收益的复杂任务时再引入，不为展示而拆多个 Agent；
- **更多专业检索 Tool**：例如代码库 `grep`、网页或外部系统检索，只在 DataPilot 范围真实扩展到对应知识形态时加入。

阶段四应先把“有界 Loop + Tool use + 短期记忆 + Context Builder + Eval”做成可信闭环，再决定这些补强是否值得投入。

### 参考项目使用策略

Phase 4 不宜像 Text2SQL 那样只围绕一个项目展开，因为本阶段同时包含知识治理、RAG、LangGraph、Router、Hybrid、安全和 Eval，没有任何一个参考项目完整覆盖这些问题。建议采用“**两个主参考 + 三个专题参考**”：

- **总体业务架构主参考：Alibaba DataAgent**。它最接近 DataPilot 的业务形态，适合参考业务 Evidence 如何参与问题理解、数据查询、分析约束和最终报告，以及核心结果与图表/报告增强如何分开。
- **LangGraph / RAG 实现主参考：agentic-rag-for-dummies**。它适合参考 Graph state、RAG tool、节点流转、澄清状态，以及如何把生成器实际看见的工具结果保留为后续回答和 Eval 的证据。
- **知识治理专题参考：WrenAI**。重点参考“可审查源文件是事实源、索引是可重建派生物”、fingerprint 和重建成功后再切换版本。
- **Router 专题参考：GustoBot**。重点参考按数据形态和证据需求分流 SQL、文档知识与其他数据面，同时把其多套 RAG 包装和来源断裂作为反例。
- **检索能力与平台反例参考：DB-GPT**。需要了解 keyword、semantic、hybrid、rerank、Resource/Tool 等能力时定点阅读，不把它的平台规模和多套不一致 interface 搬进 DataPilot。

各部分的主要参考关系如下：

| 阶段四部分 | 优先参考 | 借鉴重点 |
|---|---|---|
| 知识原件、版本与索引生命周期 | WrenAI、Alibaba DataAgent | source/artifact 分离、fingerprint、替换式更新与失败清理 |
| 文档切分与长文上下文 | agentic-rag-for-dummies | Markdown 结构切分、parent/child 思路；是否采用仍由语料实验决定 |
| 独立 RAG 链路 | agentic-rag-for-dummies | Retriever tool、Graph state、实际工具 context 留存 |
| LangGraph 顶层编排 | agentic-rag-for-dummies、Alibaba DataAgent | 前者参考 LangGraph 写法，后者参考固定、受控的业务流程 |
| Router | GustoBot | 按“需要什么证据和动作”分流，而不是复制其具体多分类 prompt |
| SQL + RAG Hybrid | Alibaba DataAgent | 知识参与分析与报告、原始 Evidence 贯穿、核心结果优先 |
| 检索增强实验 | DB-GPT、agentic-rag-for-dummies、GustoBot | 比较 hybrid、rerank、级联和上下文扩展的收益与复杂度 |
| citation | 五个项目只提供局部参考 | 重点吸收其来源断裂问题，DataPilot 自建 claim-to-Evidence 闭环 |
| 文档权限与数据出站 | 主要由 DataPilot 自己定义 | 外部项目普遍不足；复用 DataPilot 的身份、Trace 和安全纪律 |
| RAG / Hybrid Eval | 以 DataPilot 现有 Eval 为主 | 外部只参考实际 context 留存与 retrieval 指标，不另起一套评分事实源 |

参考项目的定位是帮助找到成熟做法和提前看到失败模式，不是决定 DataPilot 的 interface。具体使用时应遵守以下取舍：

- 不照搬 Alibaba DataAgent 的语言、类结构或完整计划模型，只借鉴业务 Evidence 贯穿分析链路的思想；
- 不照搬 agentic-rag-for-dummies 的复杂研究循环、默认 parent/child 和上下文压缩，只吸收与当前 Graph 状态和 RAG 主线直接相关的部分；
- 不复制 WrenAI 的完整语义编译层；
- 不复制 GustoBot 的多 Agent、多存储和多套 RAG 包装；
- 不复制 DB-GPT 的通用平台、动态资源生态和新旧 interface 并存结构。

Evidence/citation、文档 ACL、数据出站和 Scenario + typed assertion Eval 是 DataPilot 的核心差异点。这些部分可以借鉴参考项目暴露的问题，但应以 DataPilot 当前安全与评测事实链为主自行设计，不能指定某个外部项目作为实现真相。

## 1. 结论先行

Phase 4 最值得建设的不是“给 SQL Agent 接一个向量库”，而是把 DataPilot 从单一 Text2SQL 链路升级为一个**按证据类型工作、答案可以回查、安全边界可以验证**的数据分析 Agent：

```text
用户问题
  → 判断需要数据库事实、文档事实、二者组合，还是暂时不能执行
  → SQL / RAG 各自在自己的受控 interface 内取得原始 Evidence
  → 只基于实际取得且已授权的 Evidence 形成回答
  → citation 能回到同一次执行实际使用的证据
  → Trace / Eval 能解释路由、召回、引用、合成、安全与失败位置
```

建议在 roadmap 前确认以下核心选择：

| 决策 | 推荐选择 | 现在还是以后 |
|---|---|---|
| 知识事实源 | 版本库中的可审查知识文件作为阶段四权威源；`knowledge_docs` 作为运行时投影，不允许双向自由修改 | 现在确定 |
| 正式 corpus 范围 | 先纳入经过审查的政策、客服规则、安全规则和指标口径；按“回答证据 / 分析约束 / 生成上下文”标明用途 | 现在确定 |
| Evidence | 使用统一外壳 + 文档/SQL typed payload；内部保留完整证据，对外只做安全投影 | 现在确定 |
| citation | 由代码分配和校验引用 ID；claim 只能引用本次生成器实际看见的 Evidence | 现在确定 |
| 路由语义 | `route` 只表示证据路径；clarify、unsupported、partial、insufficient evidence 等由独立回答状态表达 | 现在确定 |
| Hybrid 成功语义 | 跨来源结论默认要求所声明的 SQL 与 RAG 分支都成功；单支失败可保留安全的部分结果，但不能继续生成组合结论 | 现在确定 |
| 文档权限 | 显式公开或角色 allowlist；检索前过滤、检索后复核，暂不引入通用多租户 ACL 平台 | 现在确定 |
| 数据出站 | 按外部接收方和数据类别做默认拒绝、显式放行；LangFuse 继续本地 JSONL 主路、Cloud 默认关闭 | 现在确定 |
| Eval | 继承 Scenario + typed assertion + 一题一次执行；确定性合同做 required，开放语义 judge 先作旁证 | 现在确定语义，具体 case 后定 |
| 编排骨架 | 使用 LangGraph 统一承载 Router、SQL/RAG 分支、Hybrid 汇合和最终状态；各能力仍保持独立深 module | 现在确定 |
| 检索与高级编排 | 切分、向量库、融合、rerank，以及并行执行、开放研究循环、跨会话状态等高级能力由实际需求和实验决定 | 后续实验 |

这组选择让 Phase 4 形成一个完整的求职项目故事：**DataPilot 不只是会“查数”和“搜文档”，而是知道一个结论需要什么证据，能在权限允许的范围内取得它，并能说明结论从哪里来、哪里失败了。**

## 2. 当前基础与需要修正的旧假设

### 2.1 当前真实基础

DataPilot 已具备几项可以直接承接 Phase 4 的工程基础：

- Text2SQL 已形成 Schema Retrieval → QueryPlan → SQL Guard → SQL execution 的受控链路，SQL 分支不需要因引入 Hybrid 被重写。
- SQL Guard 已有只读 AST、表级 RBAC 和敏感字段策略，可以继续承担数据库侧安全，但不能直接充当文档权限模块。
- `AgentResponse` 已预留 `route=rag/hybrid` 和 `docs_used`，Trace 也已有 `tool_calls`、`trace_steps` 与 JSONL 主路，因此外部响应和观测骨架可以增量演进。
- Schema Retrieval 已积累 keyword/vector adapter、corpus hash、clean index、runtime identity 和 run-scoped 生命周期经验；这些方法可复用，但 Schema corpus 和 Knowledge corpus 必须分开。
- Eval 已形成 canonical Scenario、typed assertion、一题一次执行、共享 ExecutionEvidence、版本化 runtime identity、Gate 与 `not_observed` 语义，这是 RAG/Hybrid 评测最重要的现成资产。
- 数据库已有确定性业务事实和 10 条短知识 seed，能为 Hybrid 案例提供初始素材，但这些 seed 还不是正式、经过治理的知识 corpus。
- LangFuse 已被定位为可选旁路，JSONL 是本地主路；外部观测失败不拖垮业务的原则可以直接保留。

### 2.2 当前不能假装已经具备的能力

- `/api/query` 目前实际仍全部进入 SQL 路径；预留 `rag/hybrid` 枚举不等于已有 Router 或 RAG。
- `docs_used: list[dict]` 没有稳定身份、revision、anchor、权限、实际使用文本或 citation 关系，不能当作审计级来源。
- `knowledge_docs` 只有 `doc_key/doc_type/audience_role/status/content` 等初始字段；缺少正式 revision、content hash、原文位置、索引 manifest 和 citation 合同。
- `domain_pack/kb_docs/` 仍为空。数据库 seed 与文件目录目前是两个潜在入口，但两者尚未定义权威关系。
- 现有 Eval 的 assertion 主要面向 Text2SQL；RAG/Hybrid 所需的 route、retrieval、citation、faithfulness、ACL 和分支失败合同尚未建立。

### 2.3 总路线图中不应直接继承的旧假设

总路线图的阶段四原始描述提供了正确方向，但其中三项不能直接成为新 roadmap 的既定事实：

1. **“Milvus 主路径”不等于阶段四必须默认使用某个向量后端。** 当前证据只支持“索引必须可重建、可识别、可比较”，没有证明某个后端或 embedding 的端到端优势。
2. **“优先复用 QueryPlanStep”应解释为复用方法，而不是复用 SQL 计划结构。** SQL 的 tables、joins、metrics 不应泄漏成 RAG 和 Hybrid 调用者都必须理解的万能 interface。
3. **“使用 LangGraph”不等于把所有函数都拆成节点。** LangGraph 已确定作为阶段四顶层编排骨架，并承载 Router、SQL/RAG Tool、Hybrid 汇合、有界循环、失败恢复和 thread 内短期状态；并行研究、开放循环、跨会话长期记忆和长期持久化仍需真实需求才能进入主线。

## 3. Phase 4 的目标、能力边界与非目标

### 3.1 目标

Phase 4 的目标应定义为“建立可信的多证据回答闭环”，具体包括：

1. 有一个可审查、可版本化、可恢复的知识事实源，索引只是可删除重建的派生物。
2. RAG 能返回结构化 Document Evidence，并生成可验证、可回到原文的 citation。
3. Router 能区分 SQL、RAG、Hybrid 与暂不可执行请求，且不把不确定性伪装成某个成功路由。
4. Hybrid 能保留 SQL 原始结果和文档原始 Evidence，再形成跨来源结论，而不是汇总两个自然语言子答案。
5. 缺证据、权限不足、外部服务不可用或增强功能失败时，系统有稳定且可解释的降级语义。
6. 文档 ACL、间接 prompt injection 和数据出站由确定性代码保护，而不是依赖模型“自觉”。
7. RAG/Hybrid 接入现有 Eval 事实链，同一次执行支撑 route、retrieval、citation、answer、safety 等多维评分。

### 3.2 能力边界

阶段四主线应限制在：

- 单一 DataPilot 业务域内的只读数据分析与知识问答；
- 经过审查的短政策、规则、指标口径，以及少量能够证明价值的长文档；
- SQL、RAG 和少量受控 Hybrid 案例；
- 有界、可枚举的工具调用，不执行任意代码，不写回业务系统；
- 单轮问题优先；需要澄清时先能正确表达状态，不承诺完整多轮会话恢复；
- 核心表格、文档引用和组合结论优先，图表与长报告属于可降级增强。

### 3.3 非目标

以下内容不应进入 Phase 4 主线：

- 通用聊天机器人或开放域问答；
- ReAct 自主循环、多 Agent 协作、动态 Skills/Connector 平台；
- GraphRAG、知识图谱、另一套并行 RAG 体系；
- 任意 Python/Shell 执行、自动写库、自动发消息或其他有副作用的动作；
- 生产级多租户知识管理后台、复杂组织树和通用 ABAC 引擎；
- OCR、多格式全覆盖、大规模增量同步平台；
- 为展示技术名词而固定 rerank、parent/child、长上下文压缩或多模型编排；
- 在 DataPilot 内继续膨胀成完整独立 Eval 平台。

## 4. 可以直接复用的基础及其边界

| 现有基础 | 可以复用什么 | 不能误用成什么 |
|---|---|---|
| Text2SQL module | 受控取得数据库结果、SQL、列、表、执行状态 | 不能把内部 QueryPlan 暴露成跨能力万能计划 |
| SQL Guard / RBAC | 共享调用者身份、安全审计思路 | 不能用 SQL 字段 allowlist 实现文档 ACL |
| `AgentResponse` | 保留响应外壳、表格、图表、trace id 等兼容价值 | `docs_used` 开放字典不能直接升级为 Evidence 事实源 |
| Trace lifecycle | step、tool call、失败不拖垮主路、JSONL 主路 | 不能默认把完整文档和答案上传到 Cloud |
| Scenario / assertion / evidence | 一题一次执行、多断言共享同一份实际答卷 | 不能把旧 Text2SQL assertion 名字硬套到 RAG |
| Eval runtime identity | 版本、hash、provider、索引身份和可比性纪律 | 不能把旧 Schema corpus identity 当 Knowledge corpus identity |
| Schema Retrieval adapters | 可替换 adapter、确定性测试替身、索引卫生经验 | Schema 与业务知识不能共用大索引或同一参数结论 |
| `knowledge_docs` | 稳定 `doc_key`、类型、状态、角色和内容的初始投影 | 不能在缺少 revision/anchor 时宣称 citation 闭环 |
| 10 条知识 seed | 初始业务素材和 ACL/Hybrid 测试候选 | 不能未经审查直接宣布为正式 gold corpus |
| 确定性数据库与 oracle | Hybrid 的结构化事实、反事实和结果核验 | 不能证明文档检索或引用正确 |
| LangFuse 旁路 | 可选观测 adapter、失败隔离 | 不能成为本地 Evidence 或 Eval 的唯一事实源 |

## 5. Roadmap 前必须确认的关键决策

### 5.1 知识事实源：文件、数据库，还是分区双源？

#### 主要方案

| 方案 | 优点 | 主要问题 |
|---|---|---|
| 数据库为权威源，文件只负责 seed/import | 贴近在线管理；状态和权限查询自然 | 当前没有知识管理入口；内容修改不易 code review/diff；本地复现实验更依赖数据库快照 |
| 文件为权威源，数据库为运行时投影 | 可审查、可 diff、可恢复；与 `domain_pack` 的可替换业务包定位一致；易冻结 corpus hash | 需要明确导入/投影关系；不能允许数据库被独立编辑后反向漂移 |
| 按知识类型分区，文件和数据库各管一类 | 将来可容纳静态政策和动态知识 | 当前语料很小，过早引入两套生命周期、身份和冲突处理 |

#### 推荐选择

**阶段四采用“文件为权威源，`knowledge_docs` 为运行时投影”。**

这里的关键不是 Markdown 还是其他格式，而是单向关系：人工维护和审查发生在权威源；运行时表、chunk、向量和关键词索引都能从某一版权威源重建。数据库中的内容若与权威 revision 不一致，应被视为投影漂移，而不是第二份同等有效的政策。

推荐理由：

- DataPilot 目前是版本库驱动的求职项目，没有在线 CMS；文件权威能得到最强的可复现性和审查价值。
- `domain_pack` 本来就承担“换行业只换业务配置”的职责，知识也属于业务包，而不是通用引擎代码。
- corpus revision、hash、权限 metadata 与 Eval authority reference 可以跟随代码版本冻结。
- `knowledge_docs` 仍有价值：它可以作为运行时目录、SQL 可见投影或未来管理入口的基础，而不是被废弃。

#### 风险与约束

- 必须禁止无规则的双向同步；否则“哪个版本是真的”会重新变得不清楚。
- 发布新 corpus 时只能在完整校验和索引构建成功后切换可见版本，失败时继续使用旧的完整版本。
- 删除、更新和停用必须能按 document revision 找回全部派生 chunk；不能只按模糊标题删除。
- 将来若真正出现在线编辑需求，应重新决定是否把数据库提升为权威源，而不是悄悄改变写入方向。

#### 留给后续的决策

- 是否需要在线编辑、审批和发布工作流；
- 是否存在必须来自数据库或外部系统的动态知识类型；
- 投影是每次启动校验、发布时构建，还是独立同步。

### 5.2 首批正式 corpus：收什么，不收什么？

#### 主要方案

1. 把所有看起来像“文本”的内容都放进一个知识库。
2. 只收退款政策和客服规则，指标口径仍只留在 Text2SQL 配置。
3. 建立一个受治理的知识目录，但明确每条知识的类型与用途。

#### 推荐选择

选择方案 3。首批正式 corpus 可以覆盖：

- 政策与客服规则：直接支撑用户可见回答；
- 安全与使用范围规则：支撑拒答、权限解释和安全测试；
- 指标口径与分析规则：支撑“这个指标怎么定义”和 Hybrid 解释，但不能覆盖数据库实际结果；
- 产品说明：只有在内容经过审查、存在目标问题和 gold evidence 时才纳入，不为了凑文档类型提前扩张。

每条知识必须声明它在系统中的用途：

| 用途 | 含义 | citation 要求 |
|---|---|---|
| 回答证据 | 直接支持用户可见事实、规则或建议 | 用到就必须可引用 |
| 分析约束 | 帮助解释 SQL 结果或限制建议适用条件 | 影响最终 claim 时必须可引用 |
| 生成上下文 | 只用于 route、query rewrite 或表达风格 | 不得被模型当成无条件业务事实 |

不建议把以下内容混入首批回答 corpus：Schema Retrieval 文档、SQL few-shot、原始工单、用户行为日志、Eval 标签、模型生成总结。它们各自有不同的权限、噪声和泄漏风险。

#### 风险与后续决策

- 同一条内容可能同时承担回答证据和分析约束，需要显式声明允许用途，不能靠 prompt 猜。
- 指标口径若同时存在于 `metrics.yaml` 与知识文档，必须指定谁是定义源、谁是可读投影，不能复制后各自更新。
- 具体纳入哪些产品说明、是否需要长文，以及文档有效期语义，可以在目标 Scenario 明确后再定。

### 5.3 Evidence 与 citation 的最低合同

#### 主要方案

| 方案 | 判断 |
|---|---|
| 继续扩展 `docs_used: list[dict]` | interface 看似简单，实际字段语义散落，调用者和 Eval 都要猜 |
| 只定义 Document Evidence | 能完成 RAG，但 Hybrid 仍会把 SQL 结果降成自然语言，组合证据不完整 |
| 统一 Evidence 外壳 + typed payload | 同一合成器可消费不同证据，同时保留各类型自己的语义 |

#### 推荐选择

采用**统一外壳 + typed payload**，而不是一个包含所有可选字段的大字典。

共同外壳至少表达：

- 本次执行中的 `evidence_id` 与证据类型；
- 权威来源身份、revision/content identity；
- 证据用途；
- 授权裁决结果与所依据的调用者上下文；
- 实际被生成器看到的内容或其受控表示；
- 对应 corpus/index/runtime identity；
- 可供 Trace/Eval 引用的稳定 evidence reference。

Document Evidence 另外表达：稳定 document/chunk 身份、标题、知识类型、原文 anchor、实际片段、候选/最终排名与检索来源。

SQL Evidence 另外表达：已通过 Guard 的 SQL、列、行数、结果 fingerprint、数据库/oracle snapshot identity，以及允许对外展示的结果视图。

Citation 应与 Evidence 分开：

- `citation_id` 是本次回答内由代码分配的短 ID，不让模型自由编文件名或 URL；
- citation 指向一个实际进入生成上下文的 Evidence；
- citation 记录它支持哪个 claim 或答案片段；
- 代码校验 citation 存在、可见、用途允许且能回到原文；
- SQL 与文档都可成为 claim support，但外部展示可分别投影为“数据依据”和“文档引用”。

#### 为什么这是一个值得做深的 module

回答器只需要学习一个较小的 Evidence interface，却能获得身份、权限、引用、Trace 和 Eval 的完整能力。检索、索引、数据库、脱敏和排序复杂度留在实现内部，调用者不需要知道每种后端的字段。这比让 Router、报告器、Eval 和前端分别解析若干 `dict` 更有 leverage，也让问题集中在一个 seam 内修复。

#### 风险与后续决策

- 完整 Evidence 可能含敏感正文或结果，因此“运行时内部证据”和“长期 artifact / 对外响应”必须是不同投影；长期记录默认保存 identity、摘要、hash 和安全白名单字段。
- claim 粒度与 UI 引用样式可以后续迭代；但 ID、revision、anchor、实际使用关系和授权事实必须先定。
- citation 支持度的开放语义判断可以后续增强，citation ID 真实性不能交给模型或 judge。

### 5.4 路由语义：route 与回答状态必须分开

#### 问题

当前公开 `route` 只有 `sql/rag/hybrid`。如果继续把 clarify、unsupported、chat、blocked、insufficient evidence 和 partial 都塞进 route，系统会把三种不同问题混在一起：**打算去哪条能力路径、最终发生了什么、是否安全允许。**

#### 主要方案

| 方案 | 主要问题 |
|---|---|
| 把 clarify、unsupported、chat、partial 都扩成 route | 把“走哪条证据路径”和“路径执行结果”混为一谈，Hybrid partial 尤其难表达 |
| 保持三类 route，其他情况都返回 SQL blocked/error | 兼容改动最少，但会继续制造错误归因，甚至把业务不支持伪装成安全拦截 |
| route、answer status、safety status 分开 | 语义最清楚，Eval 也能分别判路由、回答与安全 |

#### 推荐选择

将三条轴正交表达：

| 轴 | 建议语义 |
|---|---|
| route | `sql` / `rag` / `hybrid` / `none`，只表示选中的证据路径 |
| answer status | `completed` / `partial` / `clarification_required` / `unsupported` / `insufficient_evidence` / `blocked` / `failed` |
| safety status | 保留独立的安全裁决；不能用普通失败掩盖权限或安全拦截 |

关键例子：

- 问题含糊，尚不能决定查哪个月：`route=none`，回答状态为 `clarification_required`。
- 问题明确问退款政策，但 corpus 没有适用规则：`route=rag`，回答状态为 `insufficient_evidence`。
- Hybrid 的 RAG 分支不可用但 SQL 已成功：`route=hybrid`，回答状态可能为 `partial`，而不是把 route 改写成 SQL。
- 闲聊不属于阶段四目标：`route=none`，回答状态为 `unsupported`；暂不为了礼貌对话建设 chat route。
- 危险 SQL 或越权文档请求：安全轴必须明确 blocked，不能伪装成“没搜到”。

Router 的 fallback 也应保守：结构化分类失败或置信不足时返回澄清/暂不可执行，不默认落到 RAG，更不能把 Router 自己的模型失败投影成业务知识不存在。

#### 风险与后续决策

- 这会触及公开响应合同，但越早明确，后续兼容成本越低。
- answer status 的最终命名可以在 roadmap 中统一；其语义不能再与 route、execution status 或 safety status 混用。
- 确定性规则与模型路由各占多少、是否需要置信度阈值，应由路由数据集实验决定。

### 5.5 Hybrid 的成功语义与失败边界

#### 主要方案

| 方案 | 优点 | 主要问题 |
|---|---|---|
| 两支必须全部成功，否则整体失败 | 最保守、最容易解释 | 会丢掉已经安全取得且对用户仍有价值的部分结果 |
| 任一支有结果就让模型 best-effort 合成 | 表面完成率高 | 容易把一般政策说成针对实际数据的结论，或用模型常识补齐缺失证据 |
| 必需证据控制组合 claim，成功分支可作为 partial result | 同时保住忠实度与可用性 | 需要先定义 required/optional 和稳定状态合同 |

#### 推荐选择

Hybrid 的跨能力计划保持很薄，只表达：子任务类型、依赖关系、期望 Evidence、该证据是否是组合 claim 的必需条件，以及失败后允许保留什么。SQL 和 RAG 的内部计划不向上泄漏。

首版采用保守语义：**凡是一个结论同时声称“数据表现如何”和“按规则应如何处理”，SQL Evidence 与 Document Evidence 都是必需证据。缺任一支时，不生成跨来源结论。**

| SQL 分支 | RAG 分支 | 推荐结果 |
|---|---|---|
| 可用 | 可用 | 可以生成带双来源支持的完整结论 |
| 可用 | 不足/不可用 | 保留安全的 SQL 表格，明确缺少政策依据；不生成处理建议 |
| 不足/不可用 | 可用 | 可以展示适用政策的一般说明，但不能声称它已针对实际高风险商品或指标成立 |
| 被权限拦截 | 任意 | 不使用被拦截 Evidence，也不泄露标题、命中数量或内容存在性；是否保留另一支取决于是否会造成侧信道推断 |
| 两支均不可用 | 两支均不可用 | 返回失败或证据不足，不让合成器自由补全 |
| 两支均可用但相互冲突 | 两支均可用但相互冲突 | 展示冲突和来源，返回证据不足/需人工确认，不自动选择“更像真的”一方 |

另外两条边界必须固定：

- 合成或报告生成失败时，已成功取得的 SQL 结果和文档引用仍可作为 partial result 返回，不重复执行子分支制造另一张答卷。
- 图表、长报告和表达润色是增强能力；它们失败不能拖垮核心 Evidence 与表格结果。

#### 主要风险

- 保守策略会让首版 partial 较多，但它能阻止“有数据没政策也照样给建议”的高风险幻觉。
- “另一支能否安全单独返回”不能由模型临场决定，应由计划中的 required/optional 和安全策略裁决。
- 后续可以通过 Eval 证明某些问题的一支只是增强项，再放宽；不能先宽松回答，再依赖人工发现越界。

### 5.6 文档权限：显式 allowlist，前后双重裁决

#### 主要方案

| 方案 | 判断 |
|---|---|
| 继续用单值 `audience_role == user_role` | 简单但不能表达公开、共享角色，且会诱导不同 adapter 各写一套判断 |
| 角色层级自动继承 | 表达力更强，但“admin 天然能看全部”可能与具体文档政策冲突 |
| `public` 或显式 `allowed_roles` | 对当前四类角色足够、容易审计，未来可再升级 |

#### 推荐选择

阶段四采用 `public` 或显式角色 allowlist；**不默认赋予 admin 隐式全读权限**。如果 admin 应看到某文档，就在权威 metadata 或集中策略中明确写出。这样安全策略不会依赖角色名称猜继承关系。

授权至少在两个位置执行：

1. 检索前，用权威文档目录中的 status、角色与范围做硬过滤；相似度不参与授权。
2. 检索后、进入生成器前，再依据权威 metadata 复核每条 Evidence，防止索引陈旧或 adapter 忽略 filter。

还必须遵守：

- collection 名、知识空间名和前端筛选都不是授权凭证；
- 未授权内容不能进入 prompt，也不能通过 citation、标题、命中数、错误信息或 Trace 对外泄露；
- 文档正文是不可信数据，必须与系统指令隔离，忽略其中伪造的 system prompt、citation 或工具调用要求；
- SQL 与文档可以共享调用者身份和审计上下文，但各自保留独立安全实现与测试。

#### 风险与后续决策

- 显式 allowlist 会有少量重复 metadata，但对当前规模更透明。
- 将来出现团队、租户、文档所有者或条件权限后，再评估角色层级或 ABAC；现在不建设通用权限平台。
- 是否按安全域拆物理索引属于实现与出站策略决策，不能替代逻辑授权。

### 5.7 数据出站：按接收方和数据类别显式放行

#### 问题

RAG 中不同外部能力看到的数据并不相同：embedding 可能看到全部入库 chunk，reranker 看到 query 与候选，生成模型看到 query 与最终 Evidence，LangFuse 可能看到问题、答案、工具结果和 Trace。仅写一句“会脱敏”不足以定义边界。

#### 主要方案

| 方案 | 判断 |
|---|---|
| 所有远程能力统一允许，发送前做通用脱敏 | 最省配置，但无法处理业务语义泄漏，也忽略不同接收方看到的数据范围差异 |
| 阶段四一律只允许本地处理 | 安全边界简单，但会把部署选择误写成长期架构限制，也无法做受控远程实验 |
| 按接收方、用途和数据类别默认拒绝、显式放行 | 能兼顾安全与实验，且每次出站都有可审计理由 |

#### 推荐选择

建立统一的 outbound policy seam：每个外部 adapter 在发送前声明“接收方、用途、数据类别、字段集合”，策略默认拒绝，只有显式允许的组合才能出站。

应现在确定的规则：

- 本地处理和本地 JSONL 是默认路径；新增外部接收方默认没有权限。
- 文档必须带数据分类。即使当前 seed 是模拟数据，也应显式标记“允许外发”，不能从“看起来像 demo”自动推断。
- query、Document Evidence、SQL/rows、answer、Trace 分别授权；允许模型生成不等于允许观测平台保存。
- restricted 内容不能依赖简单正则脱敏后整段外发，因为业务语义本身也可能敏感。
- 出站裁决、实际 provider identity、被删除或摘要化的字段要进入本地 Trace；密钥和完整敏感内容不能进入长期 artifact。
- LangFuse Cloud 在完成上传 allowlist 与脱敏验证前继续关闭；未来开启也仍是旁路，不成为业务前提。

#### 留给后续的决策

- 使用本地还是远程 embedding/rerank/generation；
- 哪些正式文档被批准给哪些接收方；
- 是否为某类受限文档使用独立本地索引；
- 是否需要保存外部请求 fingerprint 或供应商侧保留策略证明。

具体模型和 provider 是后续实现选择；数据出站政策必须先于这些选择。

### 5.8 RAG / Hybrid Eval 的 canonical 合同

#### 主要方案

| 方案 | 主要问题 |
|---|---|
| 单独引入一套 RAG notebook / RAGAS 流程 | 容易让每个指标重新检索，和实际回答使用的 Evidence 不一致 |
| 只评最终答案或一个总分 | route、retrieval、citation、Hybrid 与安全错误被平均数掩盖 |
| 扩展现有 Scenario + typed assertion + ExecutionEvidence | 可继承同题一次执行、状态正交和可比性纪律 |

#### 推荐选择

继承现有 Eval 的核心规律：**一个 Scenario 只执行一次，所有 assertion 读取生成时真正使用的 retrieval、Evidence、citation 和分支结果。** 禁止为了评 citation 再检索一次，也禁止只对成功样本计算平均值。

一个 Phase 4 Scenario 至少应能声明：

- question、调用者身份与权威业务参考；
- 期望 route 与回答状态；
- 固定 corpus fixture / revision；
- gold document/evidence 或关键业务事实；
- Hybrid 中哪些分支和 Evidence 是组合结论的必需条件；
- 预期的权限、拒答、证据不足或文档投毒行为。

同一次 ExecutionEvidence 至少保留：

- 实际 route、回答状态、execution/root-cause 状态；
- 每路检索候选、最终进入生成器的 Evidence 与过滤原因；
- citation 到 Evidence 的映射；
- Hybrid 各分支状态、原始 SQL/文档证据和合成结果；
- ACL 与 outbound 决策；
- corpus/index/retrieval/provider 等 resolved runtime identity。

#### Assertion 与 Gate 建议

| 维度 | 首版建议 | 原因 |
|---|---|---|
| Route / answer status | 明确题面上做 required | 可确定性判断，且错误会把问题送入错误数据面 |
| Retrieval gold coverage | 核心封闭语料题做 required；离线指标单独报告 | 先证明证据被找到，但不把召回当答案正确 |
| Citation integrity | required | ID 存在、来自本次上下文、权限允许都能由代码裁决 |
| Citation support / coverage | 封闭事实用规则或人工 gold；开放表达先 advisory | 开放语义 judge 尚需校准，不能过早成为硬门 |
| Answer / business facts | 能结构化的事实做 required | 政策适用条件、数值和拒答可用 typed contract 表达 |
| Faithfulness | 确定性越界规则 required，开放语义 judge advisory | “引用存在”与“引用支持结论”必须分开 |
| Hybrid branch use / partial semantics | required | 防止缺一支仍生成组合结论，或丢失已成功的部分结果 |
| ACL / prompt injection / outbound | required | 安全不能用平均分抵消 |
| Output / Trace / runtime identity | required | 没有实际 Evidence 与运行身份就无法解释分数 |
| 延迟、成本、长报告质量 | advisory | 受环境和表达偏好影响，先用于趋势而非硬门 |

继续保留正交状态：

- 外部 embedding/LLM 不可用导致没有答案，应是 `external_unavailable → not_observed`，不能算成业务错误。
- 系统正确返回 `insufficient_evidence` 的预期拒答题，是可观察的正确行为，不是 `not_observed`。
- 检索命中不代表 citation 正确，citation 正确也不代表最终业务结论正确。
- LLM judge 自己失败时，对应语义 assertion 为 `not_observed`，不能拖累确定性安全 Gate。

#### 离线与端到端必须分开

离线 retrieval benchmark 回答“在固定 corpus 下能否找到 gold evidence”；端到端 Eval 回答“系统是否选对 route、使用正确 Evidence、引用正确并给出合规答案”。任何检索、切分或模型策略切换都应在同 corpus、同合同、单变量和多轮证据下讨论。

## 6. 哪些现在确定，哪些留给实验

### 6.1 Roadmap 编写前应固定的约束

- Phase 4 的主目标是可信 Evidence 闭环，而不是向量库、Graph 或多 Agent 展示。
- LangGraph 作为顶层编排骨架，负责 Router、SQL/RAG 分支、Hybrid 汇合和统一状态；SQL 与 RAG 保持独立深 module。
- 权威知识源与运行时投影的单向关系。
- document/revision/chunk/anchor/corpus/index 的身份语义，以及索引可重建原则。
- Evidence 的统一外壳、typed payload 和安全投影关系。
- citation 必须引用本次实际使用且已授权的 Evidence。
- route、answer status、execution status、safety status 的正交语义。
- Hybrid 必需分支、partial result、冲突和合成失败的边界。
- 文档显式角色 allowlist、检索前过滤和生成前复核。
- outbound 默认拒绝、按接收方/数据类别显式放行，Cloud 观测默认关闭。
- RAG/Hybrid Scenario、typed assertion、真实工具证据共享与 `not_observed` 基本合同。
- 安全、引用真实性、路由/状态和 Hybrid 失败语义属于 required Gate 的方向。

### 6.2 应由后续实验决定的事项

- 不同知识类型采用整条、段落、结构化单元还是 parent/child；
- chunk 大小、重叠、候选数量、相似度阈值；
- 关键词、dense、sparse、融合、级联、rerank 或 query rewrite 的组合；
- Knowledge Retrieval 使用哪种向量后端、embedding 或运行默认；
- Router 的确定性规则与结构化模型判断各占多少；
- 有界 Loop 中哪些失败允许恢复、采用何种改写/重试策略，以及是否需要并行子问题；
- thread 内短期记忆保留哪些状态、何时失效，以及 Context Builder 何时需要进一步 compact；
- 是否需要跨会话长期记忆、复杂长上下文压缩、OCR 或增量同步；
- citation 的 UI 样式、claim 粒度和开放语义 judge；
- 图表、长报告、模板或额外分析能力；
- 性能、成本和开放语义分数的具体阈值。

这些选择只有在正式 corpus、gold evidence 和 Eval 合同冻结后才有可比较意义。参考项目的默认参数或旧总路线图中的技术名词不能代替 DataPilot 自己的实验。

## 7. Roadmap 应保留的决策门

本文建议将后续决策门写成“满足什么证据才升级”，而不是预先承诺某项技术：

| 后续候选能力 | 只有出现什么证据才值得引入 |
|---|---|
| parent/child | 长文 gold evidence 经常只命中碎片，且补 parent 明显改善 citation support |
| 混合检索 | 单路检索在术语、编号或口语问题上呈现稳定互补，而不是单轮偶然提升 |
| rerank | gold 已进入候选但经常排不到最终上下文，并且额外延迟/出站成本可接受 |
| query rewrite / 二次检索 | 首轮失败主要来自 query 表达，而不是 corpus、权限或 gold 定义错误 |
| LangGraph 高级能力 | 真实需求需要并行研究、开放循环、跨会话长期记忆或长期持久化 |
| 更宽松的 Hybrid 降级 | Eval 证明某类分支确实是 optional，且部分回答不会制造误导或侧信道 |
| LLM judge 进入 required Gate | 与人工 gold 有稳定一致性、失败语义清楚、成本和可用性可接受 |
| Cloud 观测恢复 | 上传 allowlist、脱敏、数据分类和失败降级已通过安全 case |

## 8. 建议用户优先确认的六项选择

在开始编写 `phase4-roadmap.md` 前，建议先确认以下六项，因为它们会改变后续所有模块的 interface 与验收合同：

LangGraph 作为顶层编排骨架已于 2026-08-11 确认，不再列为待选项；下面六项仍待后续讨论确认。

1. 是否接受“知识文件为权威源、`knowledge_docs` 为运行时投影”的单向关系。
2. 是否接受“统一 Evidence 外壳 + Document/SQL typed payload”，而不是继续扩展开放 `dict`。
3. 是否接受 route 与 answer status 分离，并把 chat 排除在 Phase 4 主线之外。
4. 是否接受 Hybrid 的保守边界：缺任一必需分支时可返回部分证据，但不生成跨来源结论。
5. 是否接受文档显式角色 allowlist、无隐式 admin 全读，以及 outbound 默认拒绝。
6. 是否接受 Eval 先用确定性 required Gate 守住 route、citation integrity、Hybrid、安全和运行身份，开放语义 judge 暂作 advisory。

其余技术选型不需要在 roadmap 前锁死，可以作为有明确输入、对照条件和升级门的实验决策。

## 9. 事实与设计依据

- 当前状态与必读规则：`docs/state/AI_CONTEXT.md`
- Phase 4 参考项目横向分析：`docs/phase4-reference.md`
- 当前 Eval 口径与可比性：`docs/state/eval-baselines.md`
- 当前数据库、RBAC 与 RAG-Hybrid 注意事项：`docs/state/database-current-state.md`
- Schema Retrieval / Milvus / embedding 当前事实：`docs/state/schema-retrieval-milvus-embedding.md`
- Phase 3B 下半阶段复盘：`docs/dev-log.md`
- 当前响应与查询入口：`app/schemas/agent.py`、`app/api/query.py`
- 当前知识表与 seed：`app/models/knowledge_docs.py`、`scripts/seed_data.py`
- 当前 Trace：`engine/trace/recorder.py`
- 当前 Evidence/Eval 基础：`eval/contracts.py`、`eval/assertions.py`、`eval/cases/catalog/scenarios.yaml`
- 当前 Schema Retrieval adapter 经验：`engine/schema_retrieval/objects.py`、`engine/schema_retrieval/vector_index.py`
- 总路线阶段四原始目标：`D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP_v3.md`

---

**当前状态**：阶段四使用 LangGraph 的方向和大致方案已确认并记录；其余关键合同仍等待用户与后续审查共同确认。确认前不继续编写 `phase4-roadmap.md`。
