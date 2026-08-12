# DataPilot Phase 4 技术参考地图

> **文档定位**：本文是 Phase 4 制定 module plan 和实施关键技术前按能力切片读取的参考索引，回答“优先参考谁、看哪些源码、借鉴什么、不要照搬什么、何时重新核对”。它不是 DataPilot 当前状态文档，也不是 roadmap 的决策副本。
>
> **权威关系**：`docs/phase4-roadmap.md` 是 Phase 4 高层边界、核心合同、能力顺序和决策门的唯一推进事实源；当前运行、数据库、Eval 与索引事实以 `docs/state/` 和实际代码为准。本文只保存外部项目分析与源码导航，冲突时先服从 roadmap 和最新事实，再修订本文。
>
> **复核基线**：五个参考项目的分析与关键源码在 2026-08-12 完成定点复核。日期只表示证据时间边界；本文列出的项目不是白名单，后续可以根据真实问题补充新项目、论文和官方文档。

## 1. 怎么使用这份参考地图

进入一个 Phase 4 能力切片时，按以下顺序工作：

1. 阅读 roadmap 第 4 节跨阶段不变量、当前里程碑、决策门和第 16 节参考使用合同；
2. 按 `docs/state/AI_CONTEXT.md` 的必读规则确认当前 state、代码、测试和 Eval 失败证据；
3. 在本文第 2.1 节找到对应能力和 reference ID，再到第 2.2 节打开精确源码；只有需要了解项目全貌时，才补读第 2.3 节的 analysis；
4. 影响 interface、控制权、安全或默认路径的结论，开工时必须重新看源码，不能只引用本文或 analysis 摘要；
5. 在 module plan 或 notes 中记录借鉴内容、DataPilot 适配、不照搬内容和验证方式。

本文不维护以下内容：

- DataPilot 当前实现和缺口，去看代码与 `docs/state/`；
- Phase 4 主线、条件能力和用户待确认项，去看 roadmap；
- chunk、top-k、阈值、循环次数、模型和存储默认值，由 module plan 与 Eval 决定；
- 单个模块的一次性 workaround，留在对应 module notes。

## 2. 参考导航

### 2.1 按能力选择参考

#### 知识原件、发布与索引生命周期

- **优先参考**：`WREN-INDEX`、`WREN-WATCH`、`DATAAGENT-REPLACE`
- **重点借鉴**：原件与派生物分离；reindex 成功后才推进已观察 fingerprint；替换时先形成新文档再删除旧文档，异常时尝试清理新文档。
- **明确不照搬**：把 watcher fingerprint 或 best-effort replacement 当成原子发布、完整回滚或 active index 切换；完整语义编译层、常驻 watch 服务、Java 平台服务结构。
- **重新核对条件**：增量发布、多知识源、在线切换或回滚语义进入 module plan。

#### 文档建模、切分与 parent/child

- **优先参考**：`ARAG-CHUNK`、`ARAG-TOOLS`
- **重点借鉴**：Markdown 标题切 parent；小块命中后按需补 parent；来源和 parent ID 随 chunk 保留。
- **明确不照搬**：直接继承字符参数、顺序型 ID、所有短政策默认 parent/child。
- **重新核对条件**：正式 corpus 出现长文碎片化或 anchor 不足失败簇。

#### 检索、过滤、融合与 rerank

- **优先参考**：`DATAAGENT-REPLACE`、`GUSTO-WORKFLOW`、`ARAG-TOOLS`、`DBGPT-RESOURCE`
- **重点借鉴**：metadata 硬过滤与语义排序分工；候选检索与上下文扩展分层；rerank 可独立观察。
- **明确不照搬**：把级联顺序当普遍真理；继承参考阈值；把 hybrid fusion 写成 rerank。
- **重新核对条件**：单路基线出现稳定漏召回或排序失败，并具备可比 dev/held-out 数据。

#### Evidence、citation 与回答边界

- **优先参考**：`DBGPT-TOOL`、`DBGPT-RESOURCE`、`GUSTO-VECTOR`、`GUSTO-WORKFLOW`、`ARAG-STATE`
- **重点借鉴**：对照结构化 references 与纯文本 Tool 输出；保留生成时真实 Tool context；检查 source 是否贯穿。
- **明确不照搬**：最终拼文件名或 `sources` 就宣称 citation 闭环；让 Tool 同时生成最终答案。
- **覆盖边界**：这些入口能证明 reference identity 和 context 断裂问题，但没有直接实现 DataPilot 所需的 claim-level citation validator。
- **重新核对条件**：Evidence/citation 合同、公开投影或 Tool 返回 interface 发生变化。

#### Router 与顶层 LangGraph Harness

- **优先参考**：`ARAG-GRAPH`、`DATAAGENT-GRAPH`、`GUSTO-WORKFLOW`
- **重点借鉴**：主图/子图职责、conditional edge、状态 reducer、固定分支和 fallback。
- **明确不照搬**：多层 Prompt、多 Agent、把深模块拆成浅节点、默认某后端兜底。
- **重新核对条件**：Router taxonomy、Graph state 或跨 Tool 控制权进入设计。

#### 有界 Loop、短期状态与 Context

- **优先参考**：`ARAG-GRAPH`、`ARAG-STATE`、`ARAG-TOOLS`
- **重点借鉴**：Tool call 计数、去重 context、interrupt、fallback、压缩前后的状态处理。
- **明确不照搬**：强制搜索、开放动作空间、默认 query rewrite、默认 history compact。
- **重新核对条件**：新恢复动作、checkpoint、Evidence 复用或上下文裁剪进入 module plan。

#### Hybrid 与报告汇合

- **优先参考**：`DATAAGENT-GRAPH`、`GUSTO-WORKFLOW`
- **重点借鉴**：Evidence/问题增强/计划/执行/报告的固定控制思路；多数据面汇合的失败形态。
- **明确不照搬**：复制完整 PlanExecutor/Python 分析平台；只汇总两个自然语言子答案。
- **覆盖边界**：这里只是邻近类比；DataAgent 不是 SQL/RAG Hybrid，GustoBot 的 hybrid 也没有 typed 双 Evidence、required branch、partial 或 conflict 合同。
- **重新核对条件**：SQL/RAG required/optional、conflict 或 partial 语义需要调整。

#### ACL、数据出站与 Tool 失败

- **优先参考**：`GUSTO-WORKFLOW`、`GUSTO-VECTOR`、`DBGPT-TOOL`
- **重点借鉴**：主要作为反例检查：collection 不是授权、正文 Tool 输出会扩大泄露面、错误文本也可能泄露内部事实。
- **明确不照搬**：将 prompt guardrail、前端选择、collection 名或模型自觉当安全边界。
- **覆盖边界**：现有入口以反例为主，没有提供完整的正向 ACL/outbound 实现；module plan 还必须核对当时的 provider 数据政策、依赖官方安全文档和 DataPilot 自身合同。
- **重新核对条件**：新 provider、模型节点用途、外发字段、文档角色或错误投影出现。

#### Trace 与 RAG/Hybrid Eval

- **优先参考**：`ARAG-STATE`、`ARAG-EVAL`、`DBGPT-EVAL`
- **重点借鉴**：保存生成时实际看到的 context 和 Tool 次数；区分 retrieval similarity/MRR/Hit Rate 与 answer judge；观察将实际 Agent 输出固化后再评分的做法。
- **明确不照搬**：简单平均 notebook 指标、把空结果直接计为零但不区分不可观察、或为评分重新执行一条与线上证据身份不一致的 pipeline。
- **覆盖边界**：外部入口只提供局部 Eval 方法；一题一次执行、typed assertion、分母、`not_observed`、required Gate 和 held-out 分集以 DataPilot M27 与 roadmap 为准。
- **重新核对条件**：新 assertion、RAG Subgraph A/B、默认切换或失败归因进入设计。

安全、出站、四轴状态和 Eval 分集没有任何一个参考项目能完整覆盖。这里应以 DataPilot roadmap、现有安全合同和 M27 Eval 纪律为主，外部项目只提供局部实现或反例。

### 2.2 Reference ID 与精确源码

以下源码入口均以 Windows 目录 `D:\.Work\Practice\Python-Practice\references` 为基准。表内统一使用 `/` 表示相对路径分隔符，便于文档检索和跨工具复制；执行时应使用 `Join-Path`、`Resolve-Path` 或文件 API 解析，不要依赖手工拼接斜杠。

| 引用 ID | 源码入口 | 已复核的直接事实 |
|---|---|---|
| `WREN-INDEX` | `WrenAI/core/wren/src/wren/memory/index_backend.py :: MemoryIndex.reset / LanceDBIndex.rebuild` | Markdown 是 source，LanceDB 是 derived index；reset 不删除原件 |
| `WREN-WATCH` | `WrenAI/core/wren/src/wren/memory/watch.py :: compute_fingerprint / poll_once` | fingerprint 由相对路径、大小和修改时间组成，不读取正文；reindex 回调成功后才推进已观察 fingerprint，但这不等于 corpus version 或原子切换 |
| `DATAAGENT-GRAPH` | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java :: nl2sqlGraph` | 显式 StateGraph、节点、conditional edge、repair 与终止路径 |
| `DATAAGENT-REPLACE` | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java :: replaceDocumentsByMetadata` | metadata filter；replacement 先加新、后删旧，异常时 best-effort 清理新文档；不证明事务式替换或旧文档完整回滚 |
| `ARAG-GRAPH` | `agentic-rag-for-dummies/project/rag_agent/graph.py :: create_agent_graph`；`agentic-rag-for-dummies/project/rag_agent/edges.py :: route_after_rewrite / route_after_orchestrator_call` | agent subgraph、主图、conditional edge、interrupt/checkpointer；路由中包含 fan-out、Tool/迭代预算、fallback 与终止条件 |
| `ARAG-STATE` | `agentic-rag-for-dummies/project/rag_agent/graph_state.py :: AgentState / accumulate_or_reset / set_union / append_unique`；`agentic-rag-for-dummies/project/rag_agent/nodes.py :: _retrieval_contexts / should_compress_context / compress_context` | reducer、Tool count、真实 retrieval context 累积、历史与 context 压缩 |
| `ARAG-CHUNK` | `agentic-rag-for-dummies/project/document_chunker.py :: create_chunks_single / __create_child_chunks` | Markdown header parent、过小合并、过大拆分；默认 `source_name` 会写成 `<stem>.pdf`，parent ID 使用顺序号，不适合作为稳定 Evidence identity |
| `ARAG-TOOLS` | `agentic-rag-for-dummies/project/rag_agent/tools.py :: ToolFactory._search_child_chunks / _retrieve_parent_chunks` | child search 与按 parent ID 扩展上下文是两个独立 Tool |
| `ARAG-EVAL` | `agentic-rag-for-dummies/notebooks/evaluation.ipynb :: query_rag / assert_saved_outputs_match_dataset / score_answer` | 保存实际 Agent answer/context 后用 RAGAS 评分并汇总；属于 notebook 级评估，没有 DataPilot 的执行状态、分母、required Gate 和 held-out 决策纪律 |
| `GUSTO-WORKFLOW` | `GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py :: create_kb_multi_tool_workflow / local_search / finalize / _collect_sources` | PostgreSQL/Milvus、本地/外部知识检索和 sources 汇合；这里的 hybrid 不是 SQL Evidence + Document Evidence 的 typed Hybrid |
| `GUSTO-VECTOR` | `GustoBot/gustobot/infrastructure/knowledge/vector_store.py :: VectorStore._create_collection` | Milvus 主 schema 没有通用 source、URL、revision 或 anchor |
| `DBGPT-TOOL` | `DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py :: make_knowledge_retrieve.knowledge_retrieve` | 只使用 `knowledge_resources[0]`，返回编号正文与状态；异常文本会直接进入 Tool Observation，且没有结构化 reference identity |
| `DBGPT-RESOURCE` | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py :: RetrieverResource.get_resources / _get_references` | Resource 返回 chunks 和包含 ID、score、retriever、文档名的 references |
| `DBGPT-EVAL` | `DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/retriever.py :: RetrieverSimilarityMetric / RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator`；`DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/answer.py :: AnswerRelevancyMetric / LLMAnswerEvaluator` | 提供 retrieval 与 answer 两类局部 evaluator；不提供 DataPilot 所需的一题一次执行、`not_observed`、安全合同和 held-out 默认切换纪律 |

实现时还要检查所用依赖的当时官方文档。参考项目展示的是设计证据，不保证其 LangGraph、向量库或模型 API 与 DataPilot 开工时的依赖版本一致。

### 2.3 项目级 analysis 补充入口

下面的 analysis 以解释参考项目自身为目标，编写时没有以 DataPilot 相关信息为约束。它们适合了解项目全貌和发现候选入口，不直接代表 DataPilot 的采纳建议；最终取舍仍以第 2.1 节的能力边界、当时源码和本项目 Eval 为准。

| 项目 | 一句话定位 / 覆盖边界 | analysis 文档 | DataPilot 定向阅读重点 |
|---|---|---|---|
| WrenAI | 语义 SQL 引擎及 schema/example memory，不是通用文档问答系统 | `WrenAI/analysis-WrenAI.md` | source/index 分离、fingerprint、重建生命周期；不扩展到完整语义编译层 |
| Alibaba DataAgent | Java 企业数据分析 Graph，不是 SQL/RAG typed Hybrid | `DataAgent/analysis-alibaba-DataAgent.md` | 固定 Graph、Evidence 分析链、替换式更新；区分可借鉴方法与平台范围 |
| agentic-rag-for-dummies | 教学型 Agentic RAG 实现，不是企业安全与发布模板 | `agentic-rag-for-dummies/analysis-agentic-rag-for-dummies.md` | 主图/子图、state reducer、Tool context、停止路径和 parent 扩展；同时关注强制搜索与压缩成本 |
| GustoBot | 多数据面集成样板，citation、安全和 interface 尚未收敛 | `GustoBot/analysis-GustoBot.md` | 多数据面路由、级联检索、fallback 与 sources/citation 断裂反例 |
| DB-GPT | 大型 Agent/RAG 平台，多代接口并存，不适合整套移植 | `DB-GPT/analysis-DB-GPT.md` | Knowledge Tool/Resource 差异、ReAct 与平台化复杂度边界 |

analysis 只是可选的背景层。如果第 2.1 节已经明确当前问题、第 2.2 节源码足以验证设计，就不要求为完成形式而通读整份 analysis。

## 3. 维护与开放边界

出现以下情况时，必须重新核对源码，必要时更新本文：

- 准备引入 roadmap 中的条件能力或 Phase 4 后能力；
- 参考项目版本、目录、依赖或关键行为变化；
- 新设计会改变全局控制权、Tool interface、Evidence、ACL、outbound、状态或默认路径；
- Eval 出现本文未覆盖的新失败簇，或参考做法在 held-out 上没有稳定收益；
- 新项目、论文或官方文档比当前五个项目更直接。

更新边界：

- 通用设计判断、长期有用的入口、适用条件和重要反例写入本文；
- 路线状态变化先更新 roadmap，不在本文宣布新主线；
- 当前事实变化更新 state，不在本文维护快照；
- 参数、Prompt、一次性实现和单模块实验结果写 module plan/notes；
- 新证据推翻旧判断时，记录“什么证据改变了什么结论”，不要静默改写历史。

允许在复核后不采用任何现成实现。参考工作的验收标准不是“看过多少项目”，而是能解释为什么借鉴某个 seam、为什么拒绝某种复杂度，以及用什么 DataPilot 证据判断它是否有效。

## 4. 修订记录

**2026-08-12 参考地图重构与源码校准**：将文档收敛为能力卡、精确源码入口、项目定位和维护规则；明确 analysis 不是按 DataPilot 约束编写的采纳结论。重新定点复核五个项目，修正 WrenAI/DataAgent 发布保证的过度归因，补充 Graph 路由、RAG/Eval 入口、符号级定位、参考证据类型和关键反例；reference ID 与源码事实只在本文维护。
