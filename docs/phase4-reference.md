# DataPilot Phase 4 技术参考地图与横向分析

> **文档定位**：本文是 Phase 4 持续维护的技术参考地图，回答“某类问题优先参考谁、看哪些源码、借鉴什么、避免什么、何时需要重新评估”。它是制定 module plan 和实施关键技术前按能力切片必读的输入，但不是开发计划，不规定模块编号、文件结构、具体模型、阈值、chunk 大小或上线顺序。
>
> **权威关系**：`docs/phase4-roadmap.md` 是 Phase 4 高层边界、核心合同、能力顺序和决策门的唯一推进事实源；`docs/state/` 保存当前运行、数据库、Eval 与索引事实；本文只保存参考分析、源码导航、适用条件和反例。三者发生冲突时，先以 roadmap 和最新 state 为准，再更新本文的过期结论。
>
> **分析基线**：首次横向分析完成于 2026-08-10，2026-08-11 按当前 roadmap 对齐。主要输入为 GustoBot、agentic-rag-for-dummies、Alibaba DataAgent、DB-GPT、WrenAI 五份源码分析，并结合 DataPilot 当时状态、Phase 3B 下半阶段总结和关键源码复核。日期只表示已复核证据的时间边界，不意味着此后的模块只能使用这些项目或结论。

## 1. 文档职责、使用方式与结论

### 1.1 使用方式

进入 Phase 4 任一能力切片时，AI 应按以下顺序工作：

1. 先读 `docs/phase4-roadmap.md` 的跨阶段不变量、当前里程碑和决策门，明确不能改变的边界；
2. 按 `docs/state/AI_CONTEXT.md` 的必读规则读取相关 state 文档，并检查当前代码、测试和 Eval 失败证据；
3. 在本文定位对应能力、优先项目、analysis 和源码入口，重新定点复核影响 interface、控制权、安全或默认路径的代码；
4. 在 module plan 或 `docs/notes/<module>-notes.md` 记录当前问题、借鉴内容、DataPilot 适配、不照搬内容和验证方式；
5. 若现有参考不能解释当前问题，可以补充新项目、论文或官方文档。新增资料只形成候选设计，是否采用仍由 DataPilot 合同与 Eval 决定。

本文不要求每个机械步骤都绑定参考项目，也不保证源码路径永久不变。只读本文摘要而不复核关键源码，不能算完成 roadmap 第 16.1 节的参考门禁。

### 1.2 结论先行

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
6. **先做确定性 RAG 基线，再用失败证据约束 Agentic RAG。** 顶层有界 Loop 负责澄清、Tool 重调许可、跨 Tool 补证据、全局预算和停止；query rewrite、parent/context expansion 等文档内部动作只在 P6 RAG Subgraph 实验中引入。复杂再取证只有在 Eval 证明单次检索无法覆盖目标问题时才可能有净收益。
7. **RAG Eval 必须复用 M27 的 Scenario + typed assertion。** 同一个知识问题只执行一次，route、retrieval、citation、faithfulness、output、safety 等断言共享实际检索证据。不能为每个指标重新检索，更不能只对成功样本算均值。

## 2. DataPilot 当前基础与真实缺口

本节是横向分析时的起点快照，用于解释为什么形成后续判断，不作为持续更新的当前状态事实源。模块开工时若与 `docs/state/` 或当前代码不一致，以后两者为准，并按第 8 节判断是否需要修订本文。

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

横向分析时同时存在数据库 `knowledge_docs` 与空的 `domain_pack/kb_docs/` 两个潜在入口，因此最初把“双事实源”列为开工前风险。当前 roadmap 已固定：政策、客服规则等文档型知识以 `domain_pack/kb_docs/` 中经审查的文件为权威源，指标继续以 `metrics.yaml` 为权威源；数据库目录、chunk store 和各类索引都是可重建投影，不能反向编辑正文。

后续 module plan 仍需决定运行时 catalog 的具体投影形态，但不能重新打开“数据库正文与 Markdown 同时可编辑”的路线。若未来出现新的知识类型，应先为该类型指定唯一 authority，再讨论如何发布到运行时存储。

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

**采用**按知识形态选择检索单元；**条件引入** parent/child；**暂缓**表格行 LLM 重写、语义切分和 OCR，除非正式 corpus 出现对应需求；**不采用**仅靠文件名与顺序生成不稳定 chunk ID。

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

**采用**硬过滤与语义排序分工、检索全过程留 evidence；**条件引入**混合检索、级联、rerank、query rewrite 和 parent/context expansion；**不采用**未经目标语料标定的参考项目阈值、top-k、融合参数或打包式“高级 RAG”默认方案。

### 3.4 Evidence、引用与回答忠实度

这是五个参考项目最一致的缺口，也是 DataPilot Phase 4 最值得做深的模块。

GustoBot 的接口有 `sources`，但主 Milvus schema 不保存通用 source/url，fallback 和 GraphRAG/Text2SQL 分支也没有统一回传来源。agentic-rag-for-dummies 只要求模型输出文件名，最终聚合器看不到原始 context。DataAgent 将来源拼在 Prompt 字符串中，最终报告没有结构化 claim-to-source 关系。DB-GPT 的传统 Knowledge Resource 能生成结构化 references，但新 ReAct `knowledge_retrieve` 工具只返回编号正文。它们共同证明：**“检索结果里带 source”不等于引用闭环。**

DataPilot 应优先建立内部 `Evidence` interface，但不把所有运行细节塞进一个万能对象。当前 roadmap 已把稳定 seam 收敛为：精简公共外壳表达 Evidence 身份、类型、权威来源、revision/content identity、允许用途、受控内容和稳定 reference；Document/SQL 使用各自 typed payload；授权决策、检索诊断、runtime identity 与对外安全投影独立演进。

Knowledge Tool 只负责文档取证，返回 `RetrievalOutcome`、Document Evidence、稳定 reason code 和诊断 reference；Text2SQL Tool 返回 SQL Evidence 或结构化失败。共享 Evidence Gate 判断是否足以回答，Answer Composer/Hybrid Synthesizer 生成用户可见 claim，Citation Validator 校验 claim-to-Evidence，顶层 controller 再投影最终状态。对外可以兼容 `docs_used`、`tables_used`、SQL、图表和引用视图，但这些投影不能反向成为内部事实源。

回答忠实度也不应依赖一个“检查幻觉”的二次 prompt。更可靠的组合是：

1. 生成器明确只能使用给定 Evidence；
2. citation ID 由代码分配和校验，不让模型自由编文件名；
3. 关键事实或 claim 能映射到 evidence ID；
4. 缺少支持证据时，由 Tool 报告具体取证事实，再由顶层 controller 决定 insufficient evidence、澄清、拒答或其他最终状态；
5. Eval 同时检查引用存在性、引用支持度、覆盖度和答案正确性。

#### 结论

**优先采用**统一 Evidence 与结构化 citation；**调整后采用**引用生成和答案后核验；**不采用**prompt-only Sources、只保存最终答案、或在最终聚合前丢弃原始 evidence。

### 3.5 Router、Graph 与 Hybrid 编排

#### Router 应按能力需求分类

GustoBot 最值得借鉴的是“叙事知识、关系知识、聚合统计交给不同数据面”，而不是它的具体七分类和多层 prompt。对 DataPilot，route 只表达当前需要哪类取证路径：

| route 语义 | 需要的核心证据 | 典型问题 |
|---|---|---|
| SQL | 数据库结果 | “6 月 GMV 最高渠道是什么？” |
| RAG | Document Evidence 与 citation | “质量问题退款规则是什么？” |
| Hybrid | SQL Evidence + Document Evidence | “退款率最高商品结合售后政策怎么处理？” |
| 暂不选择证据路径 | 信息不足、越界或不属于支持范围 | 含糊问题、越权请求、闲聊 |

当前 roadmap 已将产品状态拆成 route、execution、answer、safety 四轴。clarification、unsupported、insufficient、partial 和 blocked 不再挤进 route 枚举，也不能伪装成 SQL Guard blocked。明显请求可走确定性快路径，模糊请求再交给结构化模型；模型失败时保守澄清或停止，不默认落到某个知识后端。

#### 顶层 Graph 已进入主线，但仍服务真实状态

agentic-rag-for-dummies 的主图/研究子图、澄清 interrupt、预算和压缩很有学习价值；DataAgent 的固定状态图、PlanExecutor 和 checkpoint 更适合复杂长任务；DB-GPT 则展示了通用 ReAct、Skills、Tools 和长上下文压缩的平台形态。

当前 roadmap 已确认 LangGraph 是唯一顶层 Agent Harness，用于 SQL/RAG/Hybrid 路由、Tool Observation、Evidence Gate、澄清恢复、全局预算与停止。固定路线仍应保持可枚举、可测试：

```text
route
  ├─ SQL → 现有 Text2SQL module
  ├─ RAG → Knowledge/RAG module
  └─ Hybrid → 有限子任务 → Evidence synthesis
```

采用 LangGraph 不意味着自动采用开放 ReAct、fan-out、持久 checkpoint、多 Agent 或复杂上下文压缩。现有 Text2SQL 和 Knowledge Tool 仍是深模块；只有具有独立状态迁移、控制权或失败语义的步骤才适合成为顶层节点。RAG Subgraph 是后续同合同实验 adapter，是否成为默认路径仍由 held-out A/B 决定。

#### Hybrid 计划的 seam

当前 roadmap 已明确只复用 QueryPlan 的**方法**，而不是复用同一个 SQL 数据模型。SQL QueryPlan 的 tables、joins、metrics、group_by 是 Text2SQL 内部 interface；RAG 需要 query、filters、evidence requirements；报告需要 claims、audience 和输出约束。

跨能力计划宜保持很薄，只表达：任务类型、依赖、调用哪个受控模块、期望拿到哪类 Evidence、失败时是否还能部分回答。每个模块内部继续维护自己的计划和校验。这样删除 Hybrid 编排后，SQL 与 RAG 的复杂度不会泄漏到调用者，模块才真正有 depth。

#### 结论

**采用**按证据需求路由、确定性快路径与结构化模型 fallback、顶层固定 Graph 和有界全局 Loop；**调整后采用**薄 Hybrid plan、thread 内短期状态和按需轻量 checkpoint；**条件实验**RAG Subgraph 内部再取证；**Phase 4 后再评估**开放 ReAct、fan-out、多层上下文压缩和通用 Skill/Tool 平台；**不采用**把所有内部细节暴露成顶层工具或为每个函数建一个浅 Graph 节点。

### 3.6 业务知识、SQL 与报告的联动

DataAgent 提供了最直接的联动参考：业务 Evidence 先用于问题规范化，再进入 Schema、可行性、计划、SQL 语义检查和最终报告，而不是只在 SQL 执行后追加一段文档摘要。这个思想适合 DataPilot，但应做范围收敛。

当前 roadmap 要求区分业务知识的三种作用：

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
- 横向分析时的 `audience_role` 只是单值字段，不能直接假设字符串相等就是最终权限模型。当前 roadmap 已固定首版使用 `public` 或显式 `allowed_roles`，不默认 admin 隐式全读；具体存储投影可在 P1 prototype 决定，但不能改变这项授权语义。
- 文档内容属于不可信数据，必须与系统指令分离，测试 indirect prompt injection、伪造 citation 和诱导工具调用。
- 若使用远程 embedding、rerank、生成模型或 LangFuse，必须明确哪些 query/chunk/answer 可以出站、如何脱敏、如何记录 provider identity；即使是同一 provider，Router、充分性判断、答案合成、Query Rewriting、Eval Judge 等模型节点也按用途分别取得 OutboundDecision。
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

运行和评测应保留 route、execution、answer、safety 四条正交产品状态，并另外记录稳定 root cause 与 assertion observation。Embedding 超时、索引不可用或 judge 失败不能投影成 RAG 业务错误；同样，retrieval 命中也不能自动投影为答案正确，安全拦截也不能伪装成普通证据不足。

离线检索与端到端答案继续分开：Recall@K/MRR/coverage 回答“证据有没有被找到”，citation/faithfulness/answer correctness 回答“系统有没有正确使用”。任何检索策略切换仍需要同 corpus、同合同、多轮、单变量证据。

Scenario 还要按用途隔离：diagnostic/dev 用于发现失败簇和调方案；held-out decision 在实验前冻结，只承担默认切换结论；required contract/security 可持续回归 ACL、citation、预算、状态和 outbound。若根据 holdout 失败继续调实现，该集合必须退出保留集身份。

#### 结论

**直接采用**真实工具证据进入 Eval、Scenario + typed assertion、版本化 runtime identity 和 `not_observed`；**调整后采用**LLM-as-Judge，仅作开放语义旁证；**不采用**只汇报成功样本均值、为每个 metric 重新运行 pipeline、或用单一总分掩盖 route/retrieval/answer/safety 差异。

## 4. 当前路线对齐总表

下表是 reference 对当前 roadmap 的导航快照，不是第二份决策源。状态变化时先修改 roadmap，再同步本表。

| 方向 | 当前状态 | 主要参考 | 主要原因与边界 |
|---|---|---|---|
| 权威知识源与派生索引分离 | 主线必做 | WrenAI、DataAgent | Markdown/metrics authority；数据库与索引只做可重建投影 |
| corpus/content、build recipe、physical index identity | 主线必做 | WrenAI、DataPilot 现状 | 防止脏索引、错误复用和不可比较实验 |
| 精简 Evidence 外壳 + typed payload + citation | 主线必做 | 五项目的共同缺口 | Tool、Gate、Composer、Validator 和 controller 职责唯一 |
| 按知识形态建模检索单元 | 主线原则 | DataAgent、WrenAI、GustoBot | 短政策先用天然单元，具体切分由 corpus 与 Eval 决定 |
| parent/child | 条件引入 | agentic-rag-for-dummies | 仅在长文碎片化失败簇证明稳定收益后采用 |
| dense + sparse / hybrid retrieval | 条件引入 | agentic-rag-for-dummies、DataAgent、DB-GPT | 先建立单路基线，再验证互补与端到端收益 |
| rerank、query rewrite、context expansion | 条件引入 | GustoBot、DB-GPT、agentic-rag-for-dummies | 分别做单变量实验，不打包默认化 |
| 真实 Tool context 进入 Eval | 主线必做 | agentic-rag-for-dummies | 避免评分证据与生成证据不一致 |
| dev / held-out / contract-security 分集 | 主线必做 | DataPilot Eval 纪律 | 防止用同一批题发现、调试并证明收益 |
| 按证据需求路由与四轴状态 | 主线必做 | GustoBot、DataPilot 合同 | route 不再承担 partial、blocked 或外部失败语义 |
| 顶层 LangGraph Harness | 主线必做 | agentic-rag-for-dummies、DataAgent | 统一跨 Tool 控制，但不拆散深模块 |
| 有界全局 Loop、澄清恢复、短期状态、Context Builder | 主线必做 | agentic-rag-for-dummies | 动作可枚举、有预算、可停止，只保留最小必要上下文 |
| 薄 Hybrid plan 与原始 Evidence 汇合 | 主线必做 | DataAgent、GustoBot | 不用两个自然语言子答案代替 SQL/Document Evidence |
| 有界 RAG Subgraph adapter | 实验必做，默认化有条件 | agentic-rag-for-dummies | 同 Knowledge Tool 合同 A/B；内部循环不与顶层循环重叠 |
| 轻量持久 checkpoint | 条件引入 | agentic-rag-for-dummies、DataAgent | 仅在暂停恢复和服务重启证明内存 state 不足时采用 |
| ReAct、多 Agent、多层 context compact、长期记忆 | Phase 4 后再评估 | DB-GPT、agentic-rag-for-dummies | 当前任务尚不足以抵偿状态、权限、延迟与治理成本 |
| GraphRAG、Python/Shell 平台、Connector 生态、完整语义编译层 | Phase 4 后再评估 | GustoBot、DB-GPT、DataAgent、WrenAI | 不属于可信 RAG/Hybrid 首要闭环 |
| prompt-only citation / guardrail / tool 状态 | 不采用 | 五项目的共同反例 | 不能承担审计、安全和自动 Eval |

## 5. Roadmap 决策状态与剩余开放项

### 5.1 已由 roadmap 固定

- 文档型知识与指标定义的权威源、数据库/索引的派生投影关系；
- Knowledge Tool 只取证，Evidence Gate、Composer/Synthesizer、Citation Validator 与顶层 controller 的职责；
- route、execution、answer、safety 四轴及 Hybrid 分支状态；
- 顶层 LangGraph 为主线，Text2SQL/Knowledge 保持深 Tool；
- 顶层只管全局恢复，RAG Subgraph 只管文档内部再取证，父预算覆盖子预算；
- 文档首版使用 `public` 或显式 `allowed_roles`，检索前过滤、生成前复核，不默认 admin 全读；
- Hybrid 跨来源 claim 默认要求两支 Evidence，缺支时只能返回不越界的 partial；
- RAG/Hybrid Eval 一题一次执行，并隔离 dev、held-out decision 与 contract/security Scenario。

这些事项不应在 module plan 中被重新当成开放架构选择；若确需改变，应先修订 roadmap，而不是通过局部实现悄悄漂移。

### 5.2 仍需用户在对应决策门确认

- G0：公开响应是在现有 `/api/query` 增量兼容，还是使用版本化端点/响应；
- G1：首批正式 corpus、知识用途、角色 allowlist、数据分类和具体外部接收方；
- P1/P2 prototype 与后续 Gate：运行时 catalog 投影、正式 corpus 发布和首个在线检索默认等阶段性选择。

### 5.3 留给 module plan 与 Eval

- chunk、overlap、top-k、阈值和具体循环预算；
- parent/child、hybrid retrieval、rerank、query rewrite、context expansion 是否分别进入默认；
- Milvus 或其他 adapter 是否成为 Knowledge Retrieval 默认；
- Router 确定性规则与结构化模型判断的具体比例；
- RAG Subgraph 是否切默认、轻量 checkpoint 是否值得引入；
- 报告模板、额外 judge 或其他展示增强是否有净收益。

这些选择必须以开工时的 corpus、合同、失败簇和可比 Eval 为依据，不从本文或参考项目的默认值继承。

## 6. 当前 Phase 4 能力边界

### 主线必做

- 权威知识源、稳定身份、可重建发布、Text2SQL 正文隔离；
- Knowledge Tool、Document/SQL Evidence、Evidence Gate 与可验证 citation；
- 文档 ACL、prompt injection 防护、按模型节点用途授权的 outbound seam；
- 顶层 LangGraph、按证据路由、四轴状态与结构化 Tool failure；
- 有界全局 Loop、澄清恢复、thread 内短期状态和 Context Builder；
- 保守 Hybrid、原始双 Evidence 合成、conflict/partial 与增强降级；
- RAG/Hybrid Scenario、三类数据集隔离、Trace/runtime identity；
- 同合同的 RAG Subgraph 实验 adapter 及是否默认化的证据。

### 达到条件后才引入

- hybrid retrieval、rerank、parent/child、query rewrite、context expansion；
- 轻量持久 checkpoint、少量长文/PDF、LangFuse Cloud 恢复；
- 更宽松的 Hybrid optional 分支、required LLM Judge 和更复杂报告增强。

### Phase 4 结束后再评估

- 跨会话长期记忆、用户画像和长期对话记忆召回；
- 开放 ReAct、并行 fan-out、多 Agent、多层 context compact；
- GraphRAG、Neo4j、LightRAG 或第二套知识体系；
- 通用 Python/Shell、动态 Skills/Connector、多模型 Worker；
- OCR/多格式全覆盖、大规模增量同步和完整语义编译层。

这个边界形成的主故事仍然是：**DataPilot 不只会查数据库或搜文档，而是能判断需要哪类证据，让每个模块在自己的安全接口内工作，再把数据事实和业务规则组合成可引用、可复核的分析结论。**

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
| 主图/子图组装、conditional edge、状态与实际 Tool context | `agentic-rag-for-dummies/project/rag_agent/graph.py`、`nodes.py`、`graph_state.py` |
| DataAgent 的 Evidence → Query Enhance → Schema → Plan 固定链 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java` |
| DataAgent 的替换式向量更新与失败清理 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java` |
| DB-GPT 新 ReAct knowledge tool 与 Resource references 能力不一致 | `DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py`、`DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py` |
| WrenAI 的 Markdown source、可替换 backend 与重建协议 | `WrenAI/core/wren/src/wren/memory/index_backend.py` |
| WrenAI 仅在重建成功后推进 fingerprint | `WrenAI/core/wren/src/wren/memory/watch.py` |

### 7.3 DataPilot 当前事实入口

- Phase 4 唯一路线事实源：`docs/phase4-roadmap.md`
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

## 8. 参考复核与维护规则

### 8.1 必须重新核对的触发条件

出现以下情况时，不能直接沿用本文结论，必须重新查看对应源码和当时的 DataPilot 证据：

- 准备引入当前仅为条件项或 Phase 4 后能力的设计；
- 参考项目版本、目录、依赖或关键行为发生变化；
- module plan 会改变全局控制权、Tool interface、Evidence、ACL、outbound、状态或默认路径；
- Eval 出现本文没有解释的新失败簇，或既有做法在 held-out 上没有稳定收益；
- 新项目、官方文档或研究证据比现有五个项目更直接。

### 8.2 何时更新本文，何时只写 module notes

- 修正通用设计判断、新增长期有用的源码入口、改变某能力的适用条件或发现重要反例时，更新本文；
- 具体模型、Prompt、参数、一次性 workaround 和只服务单个模块的实现细节，写入对应 module plan/notes；
- 路线状态变化先更新 `docs/phase4-roadmap.md`，再同步本文第 4～6 节；不能先在 reference 中宣布新主线；
- 若新证据推翻旧判断，应说明“什么证据改变了什么结论”，不要把历史背景删除后写成一直如此。

### 8.3 开放参考边界

本文列出的项目是优先入口，不是白名单。允许根据具体能力补充新的开源项目、论文和官方文档，也允许在复核后不采用任何现成实现。最重要的输出不是“参考过多少项目”，而是能说明 DataPilot 为什么借鉴某个 seam、为什么拒绝某种复杂度，以及准备用什么本项目证据验收。

## 9. 修订记录

1. **2026-08-11 roadmap 对齐与使用机制优化**：明确本文为按能力切片必读、但无路线决策权的持续参考地图；对齐知识事实源、Evidence 分工、四轴状态、顶层 LangGraph、双循环边界、ACL/outbound 和 Eval 分集；将旧待决策清单改为已固定、用户门禁、module/Eval 三类状态，并补充源码复核与开放扩展规则。
