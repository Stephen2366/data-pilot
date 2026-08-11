# DataPilot Phase 4 参考项目横向技术分析

> **文档定位**：本文是 Phase 4 roadmap 的技术输入，回答“DataPilot 下一阶段应该形成什么能力、借鉴哪些设计、避免哪些复杂度、还需要做哪些决策”。它不是开发计划，不规定模块编号、文件结构、具体模型、阈值、chunk 大小或上线顺序。
>
> **分析基线**：2026-08-10。主要输入为 GustoBot、agentic-rag-for-dummies、Alibaba DataAgent、DB-GPT、WrenAI 五份源码分析，并结合 DataPilot 当前状态、Phase 3B 下半阶段总结、路线图及关键源码复核。准备采纳、存在冲突或证据不足的结论已回到源码定点核对。

## 1. 结论先行

Phase 4 不宜被定义为“接一个向量库，再用 LangGraph 把 SQL 和 RAG 连起来”。结合 DataPilot 当前基础和五个参考项目，下一阶段真正需要建立的是一条新的可信证据链：

```text
问题
  → 判断需要结构化数据、文档知识、二者组合，还是应拒答/澄清
  → SQL 与 RAG 各自在自己的受控接口内取得证据
  → 将数据库结果和文档片段归一为可追溯 Evidence
  → 只基于这些证据合成答案、建议、图表和报告
  → 用同一次执行留下的 route / retrieval / citation / answer / safety evidence 评测
```

这条主线的优先级应高于“多 Agent”“自主循环”“GraphRAG”“Python 沙箱”或平台化工具生态。Phase 3B 已经证明：如果运行身份、事实口径和评分合同不可信，继续堆能力只会增加无法解释的结果。Phase 4 应延续同一纪律，把可信度从 Text2SQL 扩展到 RAG 与 Hybrid。

横向比较后的核心判断如下：

1. **优先采用统一 Evidence，而不是先采用复杂 Graph。** 五个项目都不同程度存在“检索到了内容，但来源没有贯穿到最终答案”的断点。DataPilot 已有 `docs_used`、`tool_calls`、`trace_steps`，却还没有文档证据的稳定内部模型。Evidence 是 RAG、Hybrid、引用、安全和 Eval 的共同 seam，应先于 Router/Graph 定型。
2. **采用“知识源是事实来源，索引是可重建派生物”。** WrenAI 的 source/artifact 分离和 DataAgent 的替换式更新，与 DataPilot 已建立的 corpus hash、clean collection、runtime identity 纪律高度一致。向量库不能成为唯一知识副本。
3. **切分按知识形态决定，不把 parent/child 当默认答案。** agentic-rag-for-dummies 的“小块命中、大块补上下文”值得保留，但 DataPilot 当前 10 条 seed 知识本身就是短小、独立的政策/口径单元。应先验证语料形态，再决定整文档、段落、parent/child 或其他结构感知切分。
4. **Router 应按“需要什么证据和动作”路由，而不只是按关键词贴标签。** GustoBot 的数据形态分治值得借鉴；但 DataPilot 不需要复制其多层 prompt、多套子图和多存储包装。明显请求可走确定性快路径，模糊请求再用结构化模型判断。
5. **Hybrid 需要一个很薄的跨能力计划，而不是把 SQL QueryPlan 扩成万能计划。** Phase 3A 的 QueryPlan 是 Text2SQL 内部合同。Phase 4 应复用其版本化、校验、保守裁决和 trace 方法，但跨 SQL/RAG 的计划只描述子任务、依赖和输出证据；SQL 细节仍由 Text2SQL 模块自己负责。
6. **先做确定性 RAG 基线，再让 Agent 决定重搜、扩展和压缩。** 复杂 Agent loop 只有在 Eval 证明单次检索无法覆盖目标问题时才有净收益。对当前政策问答和少量混合案例，固定流程更容易测试、解释和控制延迟。
7. **RAG Eval 必须复用 M27 的 Scenario + typed assertion。** 同一个知识问题只执行一次，route、retrieval、citation、faithfulness、output、safety 等断言共享实际检索证据。不能为每个指标重新检索，更不能只对成功样本算均值。

## 2. DataPilot 当前基础与真实缺口

### 2.1 已经可以复用的基础

DataPilot 并不是从零开始建设 RAG/Hybrid，现有几项基础已经比多数参考项目更扎实：

| 现有基础 | Phase 4 可复用价值 | 边界 |
|---|---|---|
| 14 表业务数据库、明确指标与确定性 seed | Hybrid 中的 SQL 结果有稳定业务事实和 counterfactual oracle | 只覆盖结构化数据，不证明文档答案正确 |
| 新 Text2SQL pipeline：Schema Retrieval → QueryPlan → SQL Guard | SQL 分支已经有较深的模块接口，不必因引入 Graph 重写 | 当前仍有递归、两阶段聚合、稳定输出等已知能力缺口 |
| SQL AST、RBAC、敏感字段和只读保护 | Hybrid 可以把 SQL 分支视作受控执行器 | 文档 ACL、prompt injection 和远程模型数据边界尚未建立 |
| `AgentResponse` 已预留 `route=rag/hybrid`、`docs_used` | 对外响应可以增量扩展，不必推倒重来 | `docs_used: list[dict]` 目前没有稳定语义，不能直接当审计级引用 |
| JSONL `TraceRecord`、`ToolCallTrace`、`TraceStep` | RAG 节点、检索调用和 Hybrid 合成可沿用同一观测骨架 | 当前 trace 主要服务 SQL；文档版本、chunk、citation 尚无事实源 |
| M27 Scenario / typed assertion / evidence / projector | 可直接承载 RAG 与 Hybrid 的一次执行、多维评分 | 当前 catalog 和 assertion 仍以 Text2SQL 为主 |
| Schema Retrieval 的 keyword/vector/index adapter 与索引卫生 | 可复用 adapter、hash、runtime identity 和 run-scoped 生命周期经验 | Schema 文档与业务知识是不同 corpus，不应默认共用 collection 或检索参数 |
| LangFuse 旁路、JSONL 主路 | 可以继续做可选观测，且外部服务失败不阻断业务 | 上传文档片段、问题和答案前仍有脱敏 backlog，当前默认应保持关闭 |

这些基础意味着 Phase 4 不需要重新设计 SQL、安全、Trace 和 Eval 的底层框架。更合理的方向是增加一个深的 Knowledge/RAG 模块，并通过窄接口接到现有系统，而不是把稳定能力拆散后重新塞进一个“大 Agent”。

### 2.2 当前缺口不能被已有字段掩盖

源码复核显示，Phase 4 的关键能力目前尚未实现：

- `engine/` 下没有 RAG 或 Router 模块；`/api/query` 当前无论请求内容如何，实际都进入 SQL 路径。
- `domain_pack/kb_docs/` 只有 `.gitkeep`，还没有可审查的文件语料。
- 数据库已有 10 条 `knowledge_docs` seed，包含退款、物流、发票、敏感数据、GMV 和优惠券等短知识，但它们只是初始业务素材，不是经过版本、切分、引用和检索评测治理的正式 corpus。
- `knowledge_docs` 有稳定 `doc_key`、`doc_type`、`audience_role`、`status` 和正文，这是一个不错的源数据起点；但没有 revision/content hash、原始 URI、段落锚点、chunk manifest 或索引状态。
- `docs_used` 只是开放字典列表，尚未定义 document、revision、chunk、位置、分数、ACL 与 citation 之间的关系。
- 现有 Eval 问题清单里已有 RAG/Hybrid 示例，但当前 canonical M27 catalog、evidence 和 scorer 还没有形成 RAG 合同。

因此，Phase 4 的起点不是“选哪种 embedding”，而是先明确知识事实来源、Evidence 合同和回答边界。

## 3. 横向能力比较与取舍

### 3.1 知识治理与索引生命周期

#### 值得借鉴

WrenAI 最有价值的原则是：人工可审查的 MDL/Markdown 是事实来源，LanceDB 只是可以删除和重建的派生索引；其 watch 逻辑只有在重建成功后才推进 fingerprint，失败时保留旧 fingerprint 以便下次重试。DataAgent 也采用“先写新文档，再删除旧文档；失败时尝试清理新文档”的替换策略，避免先删后写导致知识完全消失。

这与 DataPilot M20–M28 的 clean collection、corpus hash、embedding identity 和 run-scoped index 经验完全同向。Phase 4 应将这套纪律提升为所有知识索引的公共原则：

- 知识源可 review、可 diff、可恢复；
- 索引能说明自己由哪一版 corpus、哪种切分、哪种 embedding 构建；
- 重建失败不能静默切到半成品；
- 查询能记录实际使用的 corpus/index identity；
- 删除或更新必须能定位属于某个 document revision 的全部派生 chunk。

#### DataPilot 的调整点

当前同时存在两个潜在知识入口：数据库 `knowledge_docs` 与空的 `domain_pack/kb_docs/`。路线图阶段四也曾把两者都称为语料入口。这里必须避免形成“双事实源”：同一政策若在数据库和文件中各有一份，迟早会出现内容、版本和权限不一致。

Phase 4 roadmap 在进入开发计划前，应明确以下关系之一：

- 数据库是权威源，文件只用于 seed/导入；
- 文件是权威源，数据库是运行时投影；
- 两者分别管理不同知识类型，并且每种类型只有一个权威源。

本文不替 roadmap 固定选择，但不建议让两个入口无规则地同时写索引。

#### 结论

**采用** source-of-truth / derived-index 分离与可重建索引；**调整后采用** DataAgent 的替换式更新思想；**不采用** GustoBot 式多套入库、embedding、rerank 和存储配置各自演进。

### 3.2 文档建模、切分与 metadata

#### 值得借鉴

五个项目共同说明：切分不是一个全局字符参数，而是知识建模的一部分。

- agentic-rag-for-dummies 先按 Markdown 标题形成 parent，再合并过小块、拆分过大块，child 负责检索，parent 按需补上下文。
- DataAgent 将表、列、术语、FAQ 视为天然检索单元；只有普通文档才进入可选 splitter。
- WrenAI 按 model、column、relationship、view、measure 等语义实体建索引，而不是固定窗口切所有内容。
- GustoBot 的表格行重写保留稳定主键和原始字段，说明结构化行与长文不应使用同一种 ingestion 策略。

#### 对 DataPilot 的判断

DataPilot 初始的政策、规则、指标口径大多是短小独立条目。它们更接近 DataAgent 的“天然知识单元”，而不是需要 parent/child 的长篇技术文档。parent/child 很适合未来的长政策、产品说明或多章节手册，但现在直接设为默认会增加双存储一致性、额外检索调用和引用定位复杂度。

无论采用何种切分，metadata 至少要能回答以下问题：

- 这段内容属于哪份稳定文档、哪一版内容；
- 它在原文中的位置是什么，能否回到可读原文；
- 它是什么知识类型、适用于哪些角色或范围；
- 它是否 active，何时生效或失效；
- 它由哪次 ingestion、哪种切分策略产生；
- 它与父级段落或完整文档有什么关系。

这些是调用者和 Eval 必须知道的 interface 事实，不等同于现在就确定数据库字段或 chunk 大小。

#### 结论

**采用**按知识形态选择检索单元；**调整后采用** parent/child；**暂缓**表格行 LLM 重写、语义切分和 OCR，除非正式 corpus 出现对应需求；**不采用**仅靠文件名与顺序生成不稳定 chunk ID。

### 3.3 检索、融合、rerank 与上下文扩展

#### 参考项目给出的共同教训

1. GustoBot 的“结构化 pgvector 优先，命中后跳过 Milvus”说明级联检索可以降低重复、冲突和成本，但成立前提是两个源确实存在稳定的主备关系。
2. agentic-rag-for-dummies 的 hybrid child retrieval 说明 dense + sparse 对术语、编号和自然语言混合问题有价值，但它没有独立 reranker，不能把 hybrid fusion 写成 rerank。
3. DataAgent 的“先语义召回表，再按 metadata 精确取列”说明语义排序与确定性过滤应分工：相似度不承担租户、类型和权限隔离。
4. DB-GPT 展示了 semantic、keyword、tree、hybrid、rerank 等丰富能力，也暴露了多检索器分数不统一、路径能力不一致和引用断裂的代价。
5. WrenAI 对小 schema 直接返回全量、大 schema 才检索，提醒我们：检索不是越早引入越先进，能稳定装入上下文时全量或确定性读取可能更可靠。

#### 对 DataPilot 的判断

Phase 3B 已经得到过非常重要的否定结论：Schema retrieval-only recall 提升并未稳定转化为 Text2SQL 端到端提升。因此 Phase 4 也不能把“混合检索 + rerank”直接写成答案质量提升。

更合适的技术方向是：

- 先建立可重复的确定性/关键词与向量候选检索基线；
- ACL、status、doc type 等硬条件先做确定性过滤；
- 记录每一路候选、分数、融合和最终进入 prompt 的 evidence；
- 把 rerank 视为可消融的独立层，而不是向量库的附属开关；
- 只有当固定 RAG dataset 证明排序是主要瓶颈时，才引入额外模型；
- parent 扩展或二次检索只服务“首轮证据碎片化/不足”的问题，不作为每题固定动作。

Schema Retrieval 与 Knowledge Retrieval 可以共享 adapter、runtime identity 和索引卫生实现，但应有独立 corpus identity、collection 和评测合同。二者文档粒度、召回目标和失败代价不同，不能为省事混成一个大索引。

#### 结论

**采用**硬过滤与语义排序分工、检索全过程留 evidence；**调整后采用**混合检索、级联和 parent 扩展；**暂缓**reranker 默认化与 Agent 多轮重搜；**不采用**未经目标语料标定的参考项目阈值、top-k 和融合参数。

### 3.4 Evidence、引用与回答忠实度

这是五个参考项目最一致的缺口，也是 DataPilot Phase 4 最值得做深的模块。

GustoBot 的接口有 `sources`，但主 Milvus schema 不保存通用 source/url，fallback 和 GraphRAG/Text2SQL 分支也没有统一回传来源。agentic-rag-for-dummies 只要求模型输出文件名，最终聚合器看不到原始 context。DataAgent 将来源拼在 Prompt 字符串中，最终报告没有结构化 claim-to-source 关系。DB-GPT 的传统 Knowledge Resource 能生成结构化 references，但新 ReAct `knowledge_retrieve` 工具只返回编号正文。它们共同证明：**“检索结果里带 source”不等于引用闭环。**

DataPilot 应优先建立内部 `Evidence` interface。其稳定语义应覆盖：

- evidence/document/chunk 的稳定身份与文档 revision；
- 标题、知识类型、来源位置或原文锚点；
- 进入生成器的实际文本；
- retrieval、fusion、rerank 等排序事实；
- ACL/status 判断与实际 corpus identity；
- 数据库结果类证据时，对应的 SQL、列和结果 fingerprint；
- 最终 citation 使用了哪些 evidence，以及是否能回到原文。

这里不要求立刻把所有字段暴露进 `AgentResponse`。更稳妥的 seam 是：RAG Tool 和 SQL Tool 都返回结构化 Evidence；回答/报告模块只消费 Evidence；对外再投影成当前 `docs_used`、`tables_used`、SQL、图表和引用视图。这样能保持外部 interface 小，同时把复杂度集中在模块内部。

回答忠实度也不应依赖一个“检查幻觉”的二次 prompt。更可靠的组合是：

1. 生成器明确只能使用给定 Evidence；
2. citation ID 由代码分配和校验，不让模型自由编文件名；
3. 关键事实或 claim 能映射到 evidence ID；
4. 缺少支持证据时返回 insufficient evidence、澄清或拒答；
5. Eval 同时检查引用存在性、引用支持度、覆盖度和答案正确性。

#### 结论

**优先采用**统一 Evidence 与结构化 citation；**调整后采用**引用生成和答案后核验；**不采用**prompt-only Sources、只保存最终答案、或在最终聚合前丢弃原始 evidence。

### 3.5 Router、Graph 与 Hybrid 编排

#### Router 应按能力需求分类

GustoBot 最值得借鉴的是“叙事知识、关系知识、聚合统计交给不同数据面”，而不是它的具体七分类和多层 prompt。对 DataPilot，更稳定的路由语义应围绕请求需要的证据与动作：

| 路由语义 | 需要的核心证据 | 典型问题 |
|---|---|---|
| SQL | 数据库结果 | “6 月 GMV 最高渠道是什么？” |
| RAG | 文档 evidence 与 citation | “质量问题退款规则是什么？” |
| Hybrid | SQL 结果 + 文档 evidence | “退款率最高商品结合售后政策怎么处理？” |
| Clarify / Unsupported / Chat（是否进入公开枚举待定） | 无足够执行条件，或不属于业务域 | 含糊问题、越界请求、闲聊 |

当前 `AgentResponse.route` 只有 `sql/rag/hybrid`，旧路线图示例曾包含 chat。Phase 4 roadmap 必须明确澄清、闲聊、缺证据和不支持请求如何表达；不能继续让它们伪装成 SQL Guard blocked，也不能在没有 route 语义的情况下默认落到 RAG。

明显请求可由附件、命令形态、确定性规则或高置信 taxonomy 快速判断；模糊请求再交给结构化 LLM Router。模型失败时的 fallback 应保守，不应像部分参考实现那样默认选某个知识后端并生成可能无证据的答案。

#### Graph 应服务真实状态，不应成为阶段目标

agentic-rag-for-dummies 的主图/研究子图、澄清 interrupt、预算和压缩很有学习价值；DataAgent 的固定状态图、PlanExecutor 和 checkpoint 更适合复杂长任务；DB-GPT 则展示了通用 ReAct、Skills、Tools 和长上下文压缩的平台形态。

但 DataPilot 当前核心案例只有 SQL、RAG 和少量 Hybrid。首版更需要可枚举、可测试的固定路径：

```text
route
  ├─ SQL → 现有 Text2SQL module
  ├─ RAG → Knowledge/RAG module
  └─ Hybrid → 有限子任务 → Evidence synthesis
```

当出现以下真实需求时，LangGraph 才开始体现净收益：需要暂停澄清后恢复、多个独立子问题 fan-out、有界循环检索、持久 checkpoint、或复杂失败恢复。单纯为了画 Graph 而把现有 Text2SQL pipeline 拆成很多浅节点，会降低模块深度和可测试性。

#### Hybrid 计划的 seam

路线图曾写“优先复用 QueryPlanStep”。这里应理解为复用**方法**，而不是复用同一个 SQL 数据模型。SQL QueryPlan 的 tables、joins、metrics、group_by 是 Text2SQL 内部 interface；RAG 需要 query、filters、evidence requirements；报告需要 claims、audience 和输出约束。

跨能力计划宜保持很薄，只表达：任务类型、依赖、调用哪个受控模块、期望拿到哪类 Evidence、失败时是否还能部分回答。每个模块内部继续维护自己的计划和校验。这样删除 Hybrid 编排后，SQL 与 RAG 的复杂度不会泄漏到调用者，模块才真正有 depth。

#### 结论

**采用**按证据/动作路由、确定性快路径与结构化 LLM fallback；**调整后采用**固定 Graph、受限计划 IR 和 checkpoint；**暂缓**ReAct 循环、fan-out、上下文压缩和通用 Skill/Tool 平台；**不采用**把所有内部细节暴露成顶层工具或为每个函数建一个浅 Graph 节点。

### 3.6 业务知识、SQL 与报告的联动

DataAgent 提供了最直接的联动参考：业务 Evidence 先用于问题规范化，再进入 Schema、可行性、计划、SQL 语义检查和最终报告，而不是只在 SQL 执行后追加一段文档摘要。这个思想适合 DataPilot，但应做范围收敛。

对 Phase 4，业务知识可以有三种作用，roadmap 应明确区分：

1. **回答证据**：政策、客服规则直接支持用户可见答案，需要 citation。
2. **分析约束**：指标说明、处理规则帮助解释 SQL 结果或生成建议，但不能偷偷改写数据库事实。
3. **生成上下文**：用于 query rewrite、route 或报告风格；这类内容不一定都应被当作最终事实引用。

如果三者混成一个 prompt 字符串，后续很难判断“模型答错、文档检索错、SQL 错，还是知识只用于改写却被误当结论”。Evidence 应记录用途，Hybrid 报告则同时保留 SQL 结果和文档原始 evidence，而不是只接收两个子 Agent 的自然语言答案后二次总结。

图表和报告属于核心结果之上的增强。DataAgent 的“表格结果先成功，图表失败不拖垮主路径”值得采用。报告生成失败也应保留 SQL 表格、文档引用和可解释的部分结果。

#### 结论

**采用**业务知识贯穿规范化、解释与报告，但保持用途可区分；**采用**核心结果优先、展示增强可降级；**暂缓**Python 二次分析、容器沙箱和通用 HTML 应用生成；**不采用**以自然语言子答案代替原始 SQL/RAG evidence。

### 3.7 权限、安全与外部数据边界

参考项目普遍在这一层不够完整：知识空间或 collection 名称被误当租户隔离，文档内容直接进入 prompt，上传路径或 parent ID 缺少 allowlist，远程 embedding/rerank/LLM 可能接收原文，LLM guardrail 被当作安全边界。

DataPilot 已有 SQL RBAC，但文档权限是新的独立问题：

- 检索前必须按调用者、知识状态和范围做确定性过滤，不能“先召回敏感 chunk，再要求模型别说”。
- 检索后与生成前还要校验证据确实属于本次允许范围，防止 adapter 或索引错误绕过过滤。
- 当前 `audience_role` 是单值字段，如何表达 admin 继承、多个角色共享、公开文档或更细 ACL，仍需 roadmap 决策；不能直接假设字符串相等就是最终权限模型。
- 文档内容属于不可信数据，必须与系统指令分离，测试 indirect prompt injection、伪造 citation 和诱导工具调用。
- 若使用远程 embedding、rerank、生成模型或 LangFuse，必须明确哪些 query/chunk/answer 可以出站、如何脱敏、如何记录 provider identity。
- SQL 与文档安全可以共享用户身份和审计上下文，但不应共享同一套“字段 allowlist”实现；它们是同一安全目标下的两个模块。

#### 结论

**采用**检索前硬过滤、生成前复核和对抗性测试；**调整后采用**现有 RBAC 上下文；**暂缓**多租户管理后台；**不采用**prompt guardrail、collection 名称或前端选择作为唯一授权依据。

### 3.8 Eval、运行身份与失败归因

Phase 4 最应直接继承 Phase 3B 的地方是 Eval 结构，而不是某个参考项目的 RAGAS notebook。

agentic-rag-for-dummies 有一项非常值得采纳：将生成时实际看见的工具结果累计到 state，Eval 直接评分这些 context，而不是事后重新检索。DB-GPT 提供 retrieval MRR/Hit Rate 与答案 judge，但不同 RAG 路径的 citation 能力并不一致。其他项目普遍缺少固定 gold set、成功率、引用正确性或安全门禁。

DataPilot 的 RAG/Hybrid Scenario 应继续遵守“一题一次执行、多条 typed assertion 共享 evidence”：

| assertion 维度 | 回答的问题 |
|---|---|
| Route | 是否选择了正确能力，是否把 unsupported/clarify 误路由 |
| Retrieval | gold document/evidence 是否进入候选与最终上下文；覆盖而非只做文本全等 |
| Citation | citation ID 是否存在、是否指向实际使用的 evidence、是否支持相邻 claim |
| Faithfulness | 回答是否超出 evidence，缺证据时是否诚实表达 |
| Answer / Business | 关键事实、适用条件和处理建议是否正确 |
| Hybrid | SQL 与文档是否都被使用，结论是否错误混合两个来源 |
| Output | `AgentResponse`、docs、table、chart、partial result 是否符合合同 |
| Safety | ACL、敏感内容、文档投毒、tool 参数和拒答是否正确 |
| Trace / Runtime | corpus、index、embedding、retrieval strategy、实际工具输出和失败 stage 是否完整 |

仍需保留三条正交状态：执行是否完成、root cause 属于哪类、业务语义是否被观察到。Embedding 超时、索引不可用或 judge 失败不能投影成 RAG 业务错误；同样，retrieval 命中也不能自动投影为答案正确。

离线检索与端到端答案继续分开：Recall@K/MRR/coverage 回答“证据有没有被找到”，citation/faithfulness/answer correctness 回答“系统有没有正确使用”。任何检索策略切换仍需要同 corpus、同合同、多轮、单变量证据。

#### 结论

**直接采用**真实工具证据进入 Eval、Scenario + typed assertion、版本化 runtime identity 和 `not_observed`；**调整后采用**LLM-as-Judge，仅作开放语义旁证；**不采用**只汇报成功样本均值、为每个 metric 重新运行 pipeline、或用单一总分掩盖 route/retrieval/answer/safety 差异。

## 4. 采纳决策总表

| 方向 | 决策 | 主要参考 | 主要原因与边界 |
|---|---|---|---|
| 知识源与派生索引分离 | 采用 | WrenAI、DataAgent | 与 DataPilot 现有 corpus hash/clean index 纪律一致 |
| 版本、hash、index identity 和可重建协议 | 采用 | WrenAI、DataPilot 现状 | 防止脏索引与不可比较实验重演 |
| 统一 Evidence / citation interface | 优先采用 | 五项目的共同缺口 | 同时支撑回答、Hybrid、安全、Trace 和 Eval |
| 按知识形态建模检索单元 | 采用 | DataAgent、WrenAI、GustoBot | 表/术语/短政策/长文的最佳粒度不同 |
| parent/child 检索 | 调整后采用 | agentic-rag-for-dummies | 长文有价值；当前短政策不应默认增加双存储复杂度 |
| 结构化源优先、向量源兜底 | 条件采用 | GustoBot | 仅在两个源有稳定质量优先级时成立 |
| dense + sparse / hybrid retrieval | 调整后采用 | agentic-rag-for-dummies、DataAgent、DB-GPT | 先有数据集和单路基线，再判断融合收益 |
| rerank | 暂缓默认化 | GustoBot、DB-GPT | 额外延迟/成本；必须通过固定 dataset 证明净收益 |
| 真实检索工具输出进入 Eval | 采用 | agentic-rag-for-dummies | 避免评分证据与生成证据不一致 |
| 业务 Evidence 参与规范化和报告 | 调整后采用 | DataAgent | 要区分回答证据、分析约束和生成上下文 |
| 按证据/动作路由 | 采用 | GustoBot | 更贴合 SQL/RAG/Hybrid 的真实差异 |
| 确定性快路径 + 结构化 LLM fallback | 采用 | GustoBot | 降低明显问题的成本和路由波动 |
| 有限 Hybrid plan IR | 调整后采用 | DataAgent | 只编排受控模块，不暴露任意工具或复用 SQL 细节 |
| LangGraph 固定状态图 | 条件采用 | agentic-rag-for-dummies、DataAgent | 有澄清/恢复/分支/循环需求时再引入 |
| ReAct、多 Agent、动态 Skills/Connector 平台 | 暂缓 | DB-GPT、GustoBot | 当前案例不值得承担调用次数、状态和权限面 |
| 长上下文多层压缩 | 暂缓 | DB-GPT、agentic-rag-for-dummies | 当前知识问答与少量 Hybrid 尚未证明需要 |
| GraphRAG / Neo4j / LightRAG | 暂缓 | GustoBot、DB-GPT | 当前政策/规则域没有明确关系路径问题 |
| 完整语义编译层 | 暂缓但保留方向 | WrenAI | DataPilot 已有 metrics/relation/QueryPlan；复制编译器成本过高 |
| Python 沙箱与 Human-in-the-loop | 暂缓 | DataAgent | 属于深度分析和高风险审批能力，不是 RAG/Hybrid 首要闭环 |
| 多套入库、rerank、LightRAG 包装并存 | 不采用 | GustoBot 的反例 | 形成浅模块、配置漂移和不一致 evidence |
| prompt-only citation / guardrail / tool 状态 | 不采用 | 五项目的共同反例 | 不能承担审计、安全和自动 Eval |
| 通用多模型 Worker、20+ connector、多 SDK | 不采用 | DB-GPT、WrenAI | 与 DataPilot 当前求职项目范围不匹配 |

## 5. Phase 4 roadmap 必须回答的决策点

以下问题会显著改变后续设计，应在 roadmap 或开发计划前明确；本文只给出建议方向，不替用户固定最终实现。

### 5.1 开工前应明确

1. **知识事实源是什么？** `knowledge_docs`、`domain_pack/kb_docs/` 各自承担什么角色，如何避免双事实源？
2. **首批正式 corpus 包含哪些知识类型？** 短政策/规则、指标口径、产品说明是否进入同一回答知识库；哪些只服务 Text2SQL 或内部分析约束？
3. **Evidence 与 citation 的最低合同是什么？** 哪些身份、版本、位置、权限和分数必须贯穿到 Trace/Eval；公开响应展示到什么程度？
4. **route taxonomy 如何处理 clarify、unsupported、chat 和 partial answer？** 是否扩展公开 route 枚举，还是用独立状态表达？
5. **Hybrid 的成功语义是什么？** 必须同时取得 SQL 与 RAG evidence，还是允许一支失败后给带边界的部分答案？
6. **文档权限模型是什么？** 当前单值 `audience_role` 如何表达共享、继承、公开与 admin；权限在入库、检索和生成各自如何裁决？
7. **出站数据政策是什么？** 哪些 query/chunk/answer 可以交给远程 embedding、rerank、LLM 或 LangFuse；重新启用 Cloud 前如何完成脱敏？
8. **RAG/Hybrid Eval 的 canonical Scenario 与 required assertion 是什么？** 先定义“什么叫答对、引用对、拒答对”，再讨论模型和检索策略。

### 5.2 可由实验决定，不宜在 roadmap 写死

- 是否需要 parent/child，以及哪些文档类型触发；
- chunk 大小、overlap、top-k、相似度阈值；
- keyword/vector 的融合方式与权重；
- 是否引入 reranker、query rewrite、parent expansion；
- Milvus 是否成为 Knowledge Retrieval 的运行默认，还是先保留为显式路径；
- Router 中确定性规则与模型判断的具体比例；
- 是否需要 LangGraph、澄清 interrupt、fan-out 或 checkpoint；
- 是否需要多轮记忆和上下文压缩；
- 报告生成是否需要额外 judge、模板或 Python 分析。

这些选择都应由同 corpus、同合同、单变量 Eval 证据驱动，不应从参考项目默认值继承。

## 6. 建议的 Phase 4 能力边界

从求职项目价值、现有基础和复杂度收益看，Phase 4 roadmap 可以围绕下面的能力边界展开：

### 应成为主线

- 有权威知识源、稳定文档身份和可重建索引；
- RAG 能返回结构化 Evidence 和可验证 citation；
- SQL / RAG / Hybrid / unsupported 等路由语义清楚；
- Hybrid 能把受控 Text2SQL 结果与文档 Evidence 组合成有出处的建议或报告；
- 文档 ACL、prompt injection、远程 provider 数据边界有确定性保护与安全 case；
- RAG/Hybrid 接入 Scenario + typed assertion，一次执行共享实际证据；
- Trace 能解释实际 corpus/index identity、召回、引用、合成和失败位置。

### 可以作为证据驱动增强

- 混合检索、rerank、parent/child、query rewrite；
- 澄清与 bounded retry；
- LangGraph 化和持久 checkpoint；
- 更长文档、更多格式、OCR 和增量同步；
- 更复杂图表和报告模板。

### 不应进入本阶段主线

- 为展示而做的多 Agent / ReAct 自主循环；
- GraphRAG、Neo4j、LightRAG 双体系；
- 通用 Python/Shell 执行平台；
- 多数据源联邦、动态模型平台、Skills/MCP/Connector 生态；
- WrenAI 级别的多方言语义编译器；
- 没有目标 dataset 支撑的参数调优和模型堆叠。

这个边界能让 Phase 4 形成一个完整、可演示、可评测的主故事：**DataPilot 不只会查数据库或搜文档，而是能判断需要哪类证据，让每个模块在自己的安全接口内工作，再把数据事实和业务规则组合成可引用、可复核的分析结论。**

## 7. 证据索引

### 7.1 主要分析文档

- GustoBot：`references/GustoBot/analysis-GustoBot.md`
- agentic-rag-for-dummies：`references/agentic-rag-for-dummies/analysis-agentic-rag-for-dummies.md`
- Alibaba DataAgent：`references/DataAgent/analysis-alibaba-DataAgent.md`
- DB-GPT：`references/DB-GPT/analysis-DB-GPT.md`
- WrenAI：`references/WrenAI/analysis-WrenAI.md`

以上路径均相对于 `D:/.Work/Practice/Python-Practice/`；analysis 是主要输入，下面列出本轮为重要结论定点复核的源码入口。

### 7.2 关键源码复核入口

| 结论 | 源码入口 |
|---|---|
| GustoBot 的 PostgreSQL 优先、Milvus 兜底，以及 sources 聚合 | `GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py` |
| GustoBot 主 Milvus schema 没有通用 source/url/anchor 字段 | `GustoBot/gustobot/infrastructure/knowledge/vector_store.py` |
| parent/child 切分、child 检索和 parent 扩展 | `agentic-rag-for-dummies/project/document_chunker.py`、`project/rag_agent/tools.py` |
| 实际工具 context 被累计到最终 agent evidence | `agentic-rag-for-dummies/project/rag_agent/nodes.py`、`graph_state.py` |
| DataAgent 的 Evidence → Query Enhance → Schema → Plan 固定链 | `DataAgent/data-agent-management/.../config/DataAgentConfiguration.java` |
| DataAgent 的替换式向量更新与失败清理 | `DataAgent/data-agent-management/.../service/vectorstore/AgentVectorStoreServiceImpl.java` |
| DB-GPT 新 ReAct knowledge tool 与 Resource references 能力不一致 | `DB-GPT/packages/dbgpt-app/.../tools/knowledge_retrieve.py`、`packages/dbgpt-core/.../resource/knowledge.py` |
| WrenAI 的 Markdown source、可替换 backend 与重建协议 | `WrenAI/core/wren/src/wren/memory/index_backend.py` |
| WrenAI 仅在重建成功后推进 fingerprint | `WrenAI/core/wren/src/wren/memory/watch.py` |

### 7.3 DataPilot 当前事实入口

- 当前状态与路线：`docs/state/AI_CONTEXT.md`
- Phase 3B 下半阶段总结：`docs/dev-log.md`
- 检索与索引事实：`docs/state/schema-retrieval-milvus-embedding.md`
- Eval 合同与基线：`docs/state/eval-baselines.md`
- 数据库与知识表事实：`docs/state/database-current-state.md`
- 当前响应合同：`app/schemas/agent.py`
- 当前查询入口：`app/api/query.py`
- 当前知识表与 seed：`app/models/knowledge_docs.py`、`scripts/seed_data.py`
- 当前 Trace：`engine/trace/recorder.py`
- 当前 Schema Retrieval 索引 seam：`engine/schema_retrieval/objects.py`、`vector_index.py`
