# M34 EnterpriseRAG-Bench 真实语料接入与 RAG 证据升级计划

> 状态：计划已重制，暂未开始实现；G-M34-1 的架构方向已由现状调查形成建议，检索/runtime 与出站选择必须在实施中取得可比证据和用户确认
>
> 能力里程碑：Phase 4 **P2「确定性 RAG 垂直切片」的真实语料扩展切片**，并为后续 P3 提供更可信的 Knowledge Tool / AnswerFlow 输入；本模块不进入 Router、Hybrid、UI 或通用 Eval 平台
>
> 主要问题：M31–M33 已建立可信发布、权限、Evidence、citation、回答和 Eval 合同，但它们只在 22 条短知识上成立；EnterpriseRAG-Bench 已下载却仍停留在项目外文件，尚未形成可重建 corpus、可查询索引、真实回答上下文或可复现的端到端 Eval 证据

## 1. 模块定义与范围判断

M34 不是“把下载目录登记进文档”，也不是“单独写一个 benchmark 脚本”。完成状态必须同时满足：

1. 项目外的 Confluence、Google Drive、Jira 原始语料经过可复现筛选、解析、规范化和身份冻结；
2. 形成可重建、可校验、失败不切换半成品的文档目录、检索单元和物理索引；
3. DataPilot 的 `KnowledgeTool` 与 `RAGAnswerFlow` 能通过受控 runtime profile 真实消费该 corpus，而不是 Eval 直接绕过生产模块读取 gold 文档；
4. selected Evidence、真实 generation context、validated citation 和答案来自同一次运行；
5. 形成完整 corpus 上的 retrieval Eval，以及真实回答链路的 answer/citation Eval；
6. 现有 22 条业务知识、M31–M33 contract family 和默认业务路径继续作为回归基线。

这个范围比 M32/M33 单个切片大，但不能再拆成“先离线导入、以后再接运行链”的两个模块：那会允许 M34 在没有检索、回答和 Eval 证据时被误写成接入完成。执行时仍按第 6 节分阶段推进，每个决策门只冻结下一步；任一阶段失败都必须保留失败证据，不能跳过链路接线直接跑一个 gold-doc answer 脚本。

M34 调整了 AI_CONTEXT 中“下一步自然进入 P3”的旧顺序，但不推翻 Phase 4 架构：它先补齐 M33 明确未证明的规模、长文、语义和多文档证据，再把更可靠的 P2 产物交给 P3。M34 不实现顶层 Harness，也不把外部 benchmark corpus 混成 DataPilot 的业务权威知识。

用户完成本模块后，应能演示并解释：一份项目外企业文档怎样获得稳定身份、怎样被切成可检索但仍可回到原文的 Evidence、怎样通过现有 ACL/Gate/Composer/Validator 形成带 citation 的回答，以及 180 道官方问题如何在同一 corpus identity 下证明或否定检索与回答能力。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| 当前 active Knowledge release 只有 22 条短知识：10 个 Markdown 文档条目 + 12 个指标 projection；默认词法 adapter 和 extractive Composer 只在该范围验证 | 现有全绿 Gate 不能证明大规模候选、英文语义问法、长文定位、多文档回答或自然答案质量 | `docs/state/rag-current-state.md`、`docs/state/AI_CONTEXT.md` |
| EnterpriseRAG-Bench `v1.0.0` 已在项目外准备 Confluence 5,189、Google Drive 25,108、Jira 6,120，共 36,417 个文件，约 263.8 MB（251.6 MiB）解压文本 | 数据已下载但还没有可复算 corpus/build/index identity，也没有 runtime consumer | `D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0` |
| 官方 500 题中，只有按“`source_types` 非空且全部属于三类目标来源”筛选才得到 180 题；若把空来源题纳入会误得 210 | M34 必须冻结精确筛选规则、题集 hash 和 closed-world 分母，不能只写“约 180 题” | `raw/questions.jsonl` 本轮只读盘点 |
| 180 题包括 semantic 52、basic 64、constrained 25、completeness 13、conflicting 8、intra-document reasoning 4、project-related 6、miscellaneous 8；其中 38 题需要 2–9 个 expected documents | Eval 不能只报总体 top-k；必须分别观察 semantic 与多文档集合覆盖、上下文和回答/citation | `raw/questions.jsonl` 本轮只读盘点 |
| 180 题引用 274 个唯一 expected document ID，当前下载中缺失 0 个 | gold 文档完整性可作为构建硬门，但只索引 274 个 gold 文档会丢失真实规模和 distractor 难度 | `docs/state/rag-current-state.md` |
| 36,417 个文件中有 3 个 document ID 各对应两份内容不同的文件，涉及同来源和跨来源重复 | benchmark `expected_doc_id` 只能作为 logical gold identity，不能作为物理主键或覆盖写入键 | 本轮文件名 + SHA-256 盘点 |
| Confluence/Jira/Drive 都是 `.txt`，但格式并不统一；已观察到 Google Drive 文档把换行保存为字面量 `\n`，三类来源也有不同结构强度 | 不能把“读取 UTF-8 文本”当作解析完成；需要 source-aware normalization、结构保留和解析质量统计 | 三类实际样本文档 |
| `CatalogEntry` 当前同时承载 document revision、全文、ACL 与单一 anchor；`ReleaseBundle` 将所有全文内嵌到一个 canonical JSON | 直接把 3.6 万文档塞入现有 release 会放大内存、序列化、校验和切换成本，也无法表达文档—chunk—context 三层身份 | `engine/rag/catalog.py`、`engine/rag/release.py` |
| `DeterministicLexicalRetrievalAdapter` 每次遍历全部授权 entry，并针对每份全文重新构造 n-gram feature；预算默认 5 candidates / 3 selected | 算法形态是 22 条短知识 baseline，不是可接受的大 corpus 运行索引；不能只调高 limit 冒充规模化 | `engine/rag/retrieval.py` |
| `DocumentEvidencePayload.content` 当前保存整份 entry 正文；deterministic Composer 对每份 Evidence 基本原样输出全文 | 长文会直接膨胀 generation context 和用户答案；现有 Composer 不能回答官方多文档问题 | `engine/rag/evidence.py`、`engine/rag/answer_flow.py` |
| `KnowledgeTool.retrieve()` 已正确拥有 active load、pre-selection ACL、一次 adapter 调用、Evidence 构造、pre-generation 复核；`RAGAnswerFlow.run()` 已正确拥有 Gate、真实入模、Composer、citation validator 和四轴结果 | M34 应深化 Tool 内部 corpus/index adapter 和 Evidence payload，而不是另写旁路 RAG 或复制第二套 Gate/Composer/Validator | `engine/rag/knowledge_tool.py`、`engine/rag/answer_flow.py` |
| 现有 RAG Eval 是硬编码的 6 题 retrieval / 9 题 answer 确定性 suite，直接调用函数，无面向 180 题长运行的 manifest/checkpoint/CLI | 需要最小、专用的 EnterpriseRAG Eval runner，但不能扩成通用评测平台 | `eval/rag_retrieval_contracts.py`、`eval/rag_answer_contracts.py` |
| 项目已有 `pymilvus`、Schema Retrieval 的 Milvus/embedding 代码和 clean collection 身份纪律，但其对象、配置、collection/hash 均属于 Schema corpus | 可以借鉴生命周期、批量 embedding、维度/hash 校验；不能复用 Schema collection 或把 Schema 类型硬套到 Knowledge corpus | `engine/schema_retrieval/*`、`docs/state/schema-retrieval-milvus-embedding.md` |
| 所有新增 Knowledge embedding/generation/judge 出站用途仍默认 deny | 远程 semantic retrieval 或真实 LLM answer 在取得 receiver × purpose × data class × fields 决策前禁止调用 | `engine/governance.py`、`docs/state/AI_CONTEXT.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 原件、派生 chunk 和索引应怎样分层 | `WrenAI/core/wren/src/wren/memory/index_backend.py :: MemoryIndex.rebuild / reset` | 原件是 source of truth，索引只是可删除重建的查询投影；reset 不删除原件 | 项目外 raw/extracted 是 benchmark source，项目外 derived 保存可再生成文档/chunk/index；项目内只提交 recipe、轻量 manifest、case split 和 Eval 证据 | 不把 Markdown watcher、mtime fingerprint 或 Wren 的 schema/example memory 结构当作 M34 发布合同 |
| 长文切分后如何保持 parent/source 关系 | `agentic-rag-for-dummies/project/document_chunker.py :: create_chunks_single / __create_child_chunks` | 标题结构先形成较大 parent，再产生检索 child；child 保留 parent/source | M34 候选 recipe 必须保留 source instance、logical benchmark doc ID、document revision、parent/section、chunk anchor 与 content hash；切分参数由 corpus profiling + dev/held-out 证据决定 | 不继承其字符阈值、`<stem>.pdf` 默认 source、`<stem>_p{i}` 顺序 ID，也不默认所有文档都需要 parent/child |
| 候选检索与回答上下文是否应分开 | `agentic-rag-for-dummies/project/rag_agent/tools.py :: ToolFactory._search_child_chunks / _retrieve_parent_chunks` | 小检索单元与较完整回答上下文可以是两个动作，parent 补取不必污染候选搜索接口 | Knowledge adapter 返回稳定 retrieval-unit refs；Tool 在 ACL 和预算内解析为 selected Document Evidence/context unit，再由现有 AnswerFlow 入模 | 不引入 Agent 自主循环、字符串 Tool Observation、query rewrite 或无界 parent expansion |
| chunk 内容与 reference 怎样一起越过生成 seam | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py :: RetrieverResource.get_resources / _get_references` | chunk、score、retriever 与 reference 同时返回，避免答案末尾再猜 source | Evidence 外壳继续承载 run/revision/content/anchor；内部 Document payload 增加必要的 retrieval/context coordinates，用户 citation 仍由 validator 单向产生 | 不把开放 metadata dict、文档名或 score 当 citation 真相，不让 Tool 直接生成答案 |
| retrieval 与 answer 证据怎样分层 | `DB-GPT/packages/dbgpt-core/src/dbgpt/rag/evaluation/retriever.py :: RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator`；`agentic-rag-for-dummies/notebooks/evaluation.ipynb :: query_rag / assert_saved_outputs_match_dataset / score_answer` | retrieval 指标与 answer 评分分开；先固化实际运行输出再评分 | M34 retrieval-only A/B 与 AnswerFlow Eval 使用各自 artifact；同一 answer Scenario 的 assertions 只读同次 AnswerFlow Evidence，不重跑检索或用 gold 文档替换真实 context | 不照搬简单均值 notebook、空结果统一记零、评分时重跑、RAGAS/LLM judge 自动 required 或大型 evaluator DAG |
| 新索引何时可切换 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java :: replaceDocumentsByMetadata`；DataPilot 现有 `engine/rag/release.py` | replacement 应先形成新投影，再移除旧投影；DataPilot 已有 candidate 校验后切 pointer 的更强纪律 | M34 build/index 必须使用独立 identity，完整校验后才更新 external profile pointer；失败保留旧的完整 profile，不修改 22 条业务 active release | 不把 best-effort 清理当事务回滚，不在同一 collection 原地追加后声称是 clean build |

参考复核结论：本模块真正需要的新 seam 位于 Knowledge Tool 内部的“授权文档目录 ↔ 可查询 retrieval units/index ↔ 可回查 context loader”，而不是 AnswerFlow 外部。删除该 seam 后，大 corpus 的解析、索引、ACL 过滤、chunk 回查和测试复杂度会重新散落到 Tool、Eval 与 Composer，说明它具备足够 depth；但具体类型名、后端、chunk recipe 和参数仍要经过 M34-A/B 的真实数据证据再冻结。

## 4. 目标、优先级与非目标

### 模块完成状态

M34 完成后，DataPilot 在不改变默认 22 条业务知识的前提下，拥有一个显式 EnterpriseRAG benchmark corpus profile。该 profile 可以从项目外固定版本重建文档目录、retrieval units 和物理索引；`KnowledgeTool` 与 `RAGAnswerFlow` 能在同一 release/index identity 上完成真实检索、最小上下文、回答与 citation；180 题形成 closed-world retrieval artifact，真实 AnswerFlow 形成可复现 answer/citation artifact，并分别展示总体、semantic、长文和多文档结果、性能/成本及未证明边界。

### 必须完成

- 冻结 v1.0.0 来源、资产 hash、精确 180 题筛选、36,417 个 source instances、logical/physical identity 与 3 个冲突 ID 的处理合同。
- 建立 source-aware 解析和规范化质量报告；不得静默丢弃空文档、非法编码、字面量换行、标题/段落或 source metadata。
- 基于真实长度/结构/问题分布比较候选切分方案，冻结一个版本化 build recipe；不以经验值直接选 chunk 参数。
- 为完整三来源 corpus 构建可重建文档目录、retrieval units 与独立物理索引，记录 corpus/build/index/adapter/embedding identities、行数、体积、耗时和失败语义。
- 通过现有 `KnowledgeTool` / `RAGAnswerFlow` interface 接入外部 profile；ACL 双检、四阶段 Evidence、Gate、Composer、Citation Validator、安全投影和四轴状态继续由原 owner 负责。
- 外部 profile 的回答 context 使用受控 chunk/section，不把整篇长文默认原样送入 Composer 或作为最终答案。
- retrieval Eval 覆盖完整 180 题；answer Eval 使用真实 AnswerFlow，不得直接注入 expected docs，不得把 `gold_answer` 当生成输入。
- 现有 22 条业务 catalog/release 和 M31/M32/M33 required suites 全量回归；旧 artifact、分母和 identity 只读。
- 原始大文件与可重建大体积派生物留在项目外；仓库只提交必要 recipe、轻量 manifest/split、runner、报告和可审计 artifact。

### 建议完成

- 使用相同 full corpus、相同 split 和相同 Evidence/answer 合同比较至少一个词法 baseline 与一个 semantic 或 hybrid candidate，形成单变量可解释结论。
- 对 52 道 semantic、38 道 multi-document、不同 source type、不同文档长度桶分别报告结果，避免总体均值掩盖失败簇。
- 记录 build 峰值内存、索引磁盘体积、query p50/p95、context 字符/token 近似量、远程调用数与可得成本。
- 对 answer facts 的开放语义评分保持 advisory；抽样人工复核或校准通过前，不升级为 required。
- 提供只读 inspect/verify 命令，能在不重建、不联网的情况下验证 dataset/build/index/runtime artifact identity。

### 条件触发

- **parent/child 或邻近上下文扩展**：只有 dev 题证明 child 命中但回答/citation 因碎片化失败时才采用；单纯因为文档较长不自动启用。
- **hybrid retrieval**：只有 lexical 与 semantic 在同一 dev 集呈稳定互补，且 held-out 仍有净收益时才进入 external profile 默认。
- **rerank**：只有 gold 已在 candidate 中但持续排不进最终 context，且额外延迟/出站可接受时才进入候选。
- **远程 embedding / generation / judge**：必须先通过 G-M34-3 的精确出站确认；deny 时不允许静默调用或把未运行写成 `failed`。
- **全量 Answer Eval**：smoke、required contract/security 和运行身份检查通过后，才对 180 题执行一次精确运行；中断按同一 run ID/checkpoint 恢复纪律处理。

### 明确非目标

- Router、LangGraph Harness、`/api/query` 路由、Hybrid、thread/Loop、Context Builder 的全局能力或 Streamlit UI。
- 把 EnterpriseRAG-Bench 写入 `domain_pack/kb_docs/`、`knowledge_docs` legacy 表或业务 active release，或宣称它是 DataPilot 业务权威知识。
- 在线抓取 Confluence/Drive/Jira、增量同步、OAuth/SSO、企业 connector 或生产多租户 ACL。
- WixQA、其他 EnterpriseRAG-Bench source types、PDF/OCR、多格式全覆盖。
- GraphRAG、RAG Subgraph、通用 query rewrite、多 Agent、通用评测平台或 LangFuse Cloud 恢复。
- 因 M34 使用 Milvus/embedding 就修改 Schema Retrieval 默认或复用 Schema collection。

## 5. 关键合同

### C1：外部 dataset、corpus 与题集身份合同

- 输入：显式 dataset root、release `v1.0.0`、三类 source allowlist、原始资产/问题文件和版本化筛选 recipe。
- 成功输出：不可变 dataset manifest，至少包含资产 hash、source instance count、logical doc ID 映射、冲突/重复记录、180 个 question IDs、274 个 gold IDs、缺失 gold 数、source/type/multi-doc 分布和 corpus identity。
- 失败语义：路径缺失、资产/hash 漂移、未知来源、非法编码、文件名无法解析、gold 缺失、题集多/少/重复、冲突 ID 未登记时整体失败；不能宽松跳过后继续构建。
- 必须保持的不变量：`source_type + relative source path + content identity` 定位物理 source instance；benchmark document ID 只承担 logical gold 对账；原始文件不进入 Git。
- 本模块不冻结的实现细节：最终 manifest 文件名、哈希序列化细节和项目外 derived 子目录布局。

### C2：解析、检索单元与 anchor 合同

- 输入：C1 source instances、source-aware parser、候选 normalization/chunk recipe。
- 成功输出：稳定 document records 与 retrieval/context units；每个 unit 都能回到 dataset release、source type、source instance、logical doc ID、document content identity、section/parent 和稳定 anchor。
- 失败语义：空正文、规范化后信息丢失、无法回查、重复 unit identity、越界 offset、parser 版本漂移或统计不闭合时 build 失败。
- 必须保持的不变量：normalized content 与 raw source 分离；chunk 是派生物，不反向成为可编辑 authority；identity 不依赖遍历顺序、mtime 或脆弱顺序号；Google Drive 字面量 `\n` 等修复必须进入 parser recipe identity。
- 本模块不冻结的实现细节：按标题、段落、token/字符、overlap、parent/child 或 source-specific 组合；这些由 M34-B 实验门选择。

### C3：可重建 release/index 与 profile 共存合同

- 输入：C1/C2 manifest、明确的 index adapter/build recipe、embedding/runtime 配置和 profile pointer。
- 成功输出：完整 candidate release/index，带 corpus/build/index/adapter/model/dimension/row-count identities；校验通过后原子激活 external profile，能独立 reload/search/inspect。
- 失败语义：部分解析、部分 embedding、row count/hash/dimension 不一致、旧 collection 污染、candidate reload 失败或 pointer 切换失败时不推进 active external profile；上一版保持可用。
- 必须保持的不变量：业务 22 条 active release 与 external benchmark profile 分离；Schema 与 Knowledge collection/identity 分离；相同 profile 不混用不同 recipe/index；索引可删除重建且不删除 raw/extracted source。
- 本模块不冻结的实现细节：Milvus 或其他本地后端、collection schema、批大小、索引参数和是否需要 parent store。

### C4：规模化 Knowledge Tool 与 ACL 合同

- 输入：现有 `KnowledgeRequest` 语义、trusted caller、Evidence purpose/budget、active external profile 和 C3 retrieval adapter。
- 成功输出：现有 `RetrievalOutcome` 语义兼容的 selected Document Evidence、ledger、pre-generation decisions 与安全 diagnostics；Evidence content 是本次回答需要的受控 context unit，不是默认整篇长文。
- 失败语义：profile/index unavailable、no candidate、no authorized evidence、stale revision、unit/document identity mismatch 与 budget exceeded 保持结构化 owner；公开投影继续收敛权限与不存在的侧信道。
- 必须保持的不变量：Knowledge Tool 仍是文档取证唯一 owner；授权 metadata 在候选检索前生效，候选返回后和入模前再次复核；索引/collection/filter 不是授权凭证；adapter 不能生成答案、citation 或最终四轴状态。
- 本模块不冻结的实现细节：授权 scope 如何高效下推、metadata store 形态、检索 match 内部字段与 future async interface。

### C5：长文/多文档 AnswerFlow 与 citation 合同

- 输入：C4 selected Evidence、受控 Evidence requirement、现有 Shared Gate、一个经确认的 Composer runtime 和有限 context/claim 预算。
- 成功输出：真实 generation-visible context、结构化 claims、validated citations、`cited` ledger 和四轴 `RAGAnswerResult`；多文档答案的 claims 整体能覆盖实际支持它们的 Evidence refs，需要联合证据的 claim 必须携带全部支持或拆成可单独引用的原子 claim。
- 失败语义：运行时 Evidence requirement 未满足、上下文超预算、Composer 不可用、claim unsupported、citation 缺失/伪造/跨 run/revision/anchor 或部分失败时不公开未经验证的完整答案；expected document set 只由 Eval 在运行后评分，不参与该运行时裁决。
- 必须保持的不变量：复用 `RAGAnswerFlow.run()`、Gate 和 M31 Validator 的唯一控制权；不得向 Composer 注入 gold answer/answer facts/expected doc IDs；只有真实传入的 units 推进 generation-visible；citation 只来自本轮 context。
- 本模块不冻结的实现细节：Composer provider/model/prompt、claim 粒度、context packing 与开放语义 judge；远程候选必须经过 G-M34-3。

### C6：EnterpriseRAG Retrieval / Answer Eval 合同

- 输入：冻结的 180 题 catalog/split、full corpus/build/index/runtime identities、一次真实 Tool 或 AnswerFlow execution evidence、版本化 assertion policy。
- 成功输出：retrieval 与 answer 两类独立 artifact；closed-world 校验 Scenario/replicate/assertion/runtime/corpus/build/index/adapter/composer/policy identity；报告总体与分组结果、性能/成本和失败结构。
- 失败语义：技术/远程不可用导致效果不可判断时为 `not_observed`；预期业务失败是可观察结果；中断 run 不生成 completed artifact；缺/多/重结果或 identity 漂移时整体拒绝。
- 必须保持的不变量：一个 answer Scenario 只执行一次 AnswerFlow，多 assertion 共享同次 Evidence；retrieval scorer 不重跑检索，answer scorer 不替换 context；required contract/security 与 advisory effect 分开；dev 调参集不承担默认切换结论。
- 本模块不冻结的实现细节：最终 split 数量、top-k、answer judge、replicate 数和长期 baseline 门槛；M34-A 在看见真实分布后冻结，远程重复运行仍需用户精确授权。

### C7：22 条业务知识与历史合同回归合同

- 输入：当前 business active release、M31 `phase4-v1`、M32 `phase4-rag-retrieval-v1`、M33 `phase4-rag-answer-v1` 和全仓确定性测试。
- 成功输出：旧 Scenario/分母/identity 语义不变且 required Gate 继续通过；默认业务 Knowledge path 未被 external profile、index 或配置替换。
- 失败语义：任何旧 Gate、active pointer、ACL/outbound、citation、Text2SQL 隔离或默认配置变化都阻塞 M34 验收，不能以 external benchmark 分数抵消。
- 必须保持的不变量：历史 artifact 只读；M34 新 family 不回填旧结果；external profile 的默认化只对其显式入口生效。
- 本模块不冻结的实现细节：全仓测试拆批方式和收工时的精确数字。

## 6. 工作切片与执行顺序

### M34-A：数据审计、题集冻结与开工基线

- 优先级：必须完成
- 依赖：项目外 v1.0.0 数据、M33 收工状态、C1/C7
- 实施内容：建立 `m34-notes.md` checklist；记录 Git 和 22 条 baseline；校验 release asset/hash、36,417 文件、三来源统计、180 题严格筛选、274 gold、3 个冲突 ID；核对数据许可/归属说明；在任何参数调试前冻结 diagnostic/dev、held-out decision、required contract/security 的用途和 case identity。
- 关键合同：C1、C6、C7
- 交付物：轻量 dataset manifest/split recipe、数据质量报告、外部路径配置与开工快照。
- 验证方式：同一 root 重复扫描得到相同 identity；增删/改文件、错误来源、空 `source_types`、gold 缺失、冲突覆盖等负向 fixture 全部失败关闭。
- 完成门：题集分母、logical/physical identity 或许可证边界仍不明确时，不进入批量解析/embedding。

### M34-B：source-aware 解析、结构 profiling 与 chunk recipe 实验

- 优先级：必须完成
- 依赖：M34-A
- 实施内容：实现三来源 parser/normalizer；输出文档长度、段落/标题结构、字面量换行、空/异常、gold 长度桶等统计；在 dev 题上比较少量可解释的 unit/context 候选，不同时改变 parser、chunk、retriever 和 top-k；冻结 C2 recipe。
- 关键合同：C2、C6
- 交付物：可重建 document/unit manifest、候选 recipe 对照、最终 build recipe identity 和 parser tests。
- 验证方式：raw→normalized→unit→source anchor 往返；稳定重建；三来源代表样本、极短/极长/无标题/转义换行/重复 ID/边界 offset case。
- 完成门：每个 retrieval/context unit 都可回查 source instance，统计总数闭合，且选择 recipe 的理由来自 dev 证据而非参考项目默认值。

### M34-C：完整 corpus 索引候选与原子 external profile

- 优先级：必须完成
- 依赖：M34-B、G-M34-2、必要时 G-M34-3 的 embedding 授权
- 实施内容：先建立可复现 lexical baseline，再按决策门构建 semantic 或 hybrid candidate；完整三来源 corpus 进入候选索引；记录 build/check/reload/rollback、批量失败恢复和运行资源；只在校验通过后激活 external profile。
- 关键合同：C3、C4
- 交付物：index adapter、candidate/active profile、inspect/verify 入口、full-corpus build artifact 和 A/B 证据。
- 验证方式：clean build、同 identity 安全复用、hash/dimension/row count/partial insert mismatch、旧污染 collection、切换故障、删除索引后重建、同 query 稳定搜索。
- 完成门：不能证明完整 corpus 已进入可查询索引、candidate reload 一致和旧 profile 保留时，不得进入 AnswerFlow Eval。

### M34-D：Knowledge Tool / Evidence / AnswerFlow 真实接线

- 优先级：必须完成
- 依赖：M34-C、G-M34-1、G-M34-3 的 Composer 选择
- 实施内容：让 external profile 通过 Knowledge Tool 内部新 seam 被消费；扩展 Document Evidence 的 document/unit/context 坐标但保持公共外壳；维持 ACL 双检与安全投影；让 AnswerFlow 使用受控 context packing 和支持多 Evidence 的 Composer/citation 流程。
- 关键合同：C4、C5、C7
- 交付物：显式 external runtime factory/profile、兼容 RetrievalOutcome、可回查 chunk Evidence、真实 AnswerFlow 结果和聚焦安全测试。
- 验证方式：三来源单文档、semantic、长文中段、多文档、conflict/no-hit、ACL deny/stale/index unavailable、prompt injection、context budget、citation 篡改；捕获 Composer 实际输入与 ledger 精确对账。
- 完成门：Eval 不传 expected docs 也能走完整 Tool→Gate→Composer→Validator；任何 gold shortcut、全文直出或第二套回答控制器都阻塞。

### M34-E：180 题 Retrieval Eval 与候选选择

- 优先级：必须完成
- 依赖：M34-D
- 实施内容：执行 full 180 retrieval-only benchmark；按 overall/source/type/document-count/length 分组，重点单列 52 semantic 与 38 multi-document；报告 candidate/selected gold coverage、MRR/Hit Rate 或 set coverage、no-result、latency 和 runtime identity；用 held-out 决定 external profile adapter。
- 关键合同：C6
- 交付物：versioned retrieval artifact/report、closed-world validator、失败簇和 G-M34-2 最终结论。
- 验证方式：一题一次 Tool、scorer 只读 execution evidence；缺/多/重 Scenario/assertion/identity 反例；同 artifact 可离线复算。
- 完成门：不能只报总体均值；不能用 dev 结果、不同 corpus 或不同 split 宣称 semantic/hybrid 提升。

### M34-F：真实 Answer/Citation Eval 与边界结论

- 优先级：必须完成
- 依赖：M34-E、G-M34-3、answer smoke 与 required safety Gate
- 实施内容：先跑小规模 smoke，确认出站、context、citation、checkpoint 和成本；随后对冻结的 180 题执行一次精确 AnswerFlow Eval；用 answer facts/gold answer 做离线确定性检查与 advisory semantic scoring，按 multi-document/semantic/long-doc 分组；人工抽样复核高风险失败。
- 关键合同：C5、C6
- 交付物：completed answer artifact/report、checkpoint/manifest、调用/成本/性能摘要、answer/citation 失败结构与明确未证明边界。
- 验证方式：同一 Scenario 一次 AnswerFlow；gold 字段不进入 runtime；actual context、claims、citations、axes、provider/runtime identity 可关联；中断不生成 completed artifact。
- 完成门：至少能证明真实 build→retrieve→answer→cite→score 的同次证据链；若全量运行因授权/外部不可用未完成，M34 状态只能是未完成或 Gate inconclusive，不能降格为“接入完成”。

### M34-G：22 条回归、文档固化与交接

- 优先级：必须完成
- 依赖：M34-A 至 M34-F
- 实施内容：运行 M31–M33 required suites、22 条业务 Knowledge/AnswerFlow、Text2SQL 隔离和全仓回归；检查默认配置/active pointers/collection 隔离；固化 build/index/Eval/成本/失败证据到 notes；按 finish-module → finish-docs 流程更新 state。
- 关键合同：C7 及全部合同
- 交付物：最终验证矩阵、回滚说明、`rag-current-state.md` 新事实、P3 handoff。
- 验证方式：聚焦→旧 RAG contracts→安全/发布→受影响全仓→compileall/diff check；项目外大文件与 Git 变更清单交叉检查。
- 完成门：业务 22 条 baseline 和默认路径无回归，外部数据未误提交，M34 的能力声明与 artifact 边界一致。

## 7. 决策门

### G-M34-1：外部 corpus 与业务 active release 如何共存

#### 方案 A：独立 benchmark corpus profile（推荐）

- 做法：保留 22 条业务 active release 为默认；EnterpriseRAG 使用独立 manifest、release/index identity 和显式 runtime factory/profile，Knowledge Tool/AnswerFlow interface 相同。
- 影响：既能真实复用运行链，又不把英文合成 benchmark 冒充业务 authority；P3 以后是否暴露 profile 由新计划决定。
- 适用条件：本轮目标是能力与 Eval 证据，不是产品用户混合查询两个 corpus。
- 风险：需要新增 profile lifecycle 和工厂接线；若 seam 设计过宽会形成平行架构。

#### 方案 B：合并进现有 22 条 active release

- 做法：把外部文档和业务知识构建成一个超大 release/index。
- 影响：调用入口简单，但 authority、ACL、语言、数据分类、回滚和默认检索全部耦合。
- 适用条件：只有产品明确要求默认查询同时覆盖两类知识，且治理/发布合同已统一时。
- 风险：污染业务事实源，破坏当前回归可比性，单个外部 build 失败可能影响业务知识可用性。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：EnterpriseRAG 是英文合成 benchmark，不是 `domain_pack` 权威知识；独立 profile 在同一个 Knowledge Tool interface 下提供隔离，而不是复制 AnswerFlow。
- 用户确认前允许推进：M34-A/B 的只读盘点、parser/chunk 小样和候选 identity 设计。
- 用户确认前禁止推进：修改业务 active pointer、默认 Knowledge profile 或把外部文件写进 `domain_pack`。
- 需要确认的时点：M34-C external profile lifecycle 实现前。
- 重开决策的条件：未来 P3 产品需求明确要求统一跨 corpus 检索，并有独立治理/Eval 证明。

### G-M34-2：external profile 的检索/index runtime

#### 方案 A：仅 lexical/indexed baseline

- 做法：构建本地可重建 lexical index，作为 full-corpus 工程 baseline。
- 影响：离线、可解释、成本低；能证明规模接线，但不满足“语义检索提升”的充分证据。
- 适用条件：semantic provider 未获授权，或 dev 证据显示 lexical 已足够且远程成本不合理。
- 风险：52 道 semantic 题和改写问题可能持续漏召回。

#### 方案 B：semantic vector candidate

- 做法：为相同 retrieval units 构建独立向量索引，并与 lexical 在同 split 比较。
- 影响：能直接检验 semantic 题收益；需要 embedding 出站/本地模型、构建成本和专用 index identity。
- 适用条件：有合规 embedding runtime，且 corpus/build 成本可接受。
- 风险：向量召回可能丢失编号/专名，多文档 completeness 不一定改善。

#### 方案 C：lexical + semantic hybrid candidate

- 做法：两路候选独立观察，再以版本化 fusion recipe 合并；rerank 不与 fusion 混为一体。
- 影响：可能兼顾术语和语义，但变量、索引和归因复杂度最高。
- 适用条件：dev 证据证明两路稳定互补，held-out 能复现净收益。
- 风险：在没有互补证据时会增加延迟、调参和不可解释性。

#### 建议与确认时点

- 建议：先构建 A 作为工程/对照 baseline；只在相同 corpus/split 上比较 B，若出现稳定互补再让 C 入场。最终不预选，按 held-out、性能和成本证据确认。
- 用户确认前允许推进：本地 lexical baseline、semantic 小样成本估算、不会外发正文的接口/fixture。
- 用户确认前禁止推进：远程 full-corpus embedding、修改 `.env` 长期默认、复用 Schema collection 或把未经 held-out 证明的候选设为 external 默认。
- 需要确认的时点：semantic full build 前确认出站；M34-E 后确认 external profile 默认 adapter。
- 重开决策的条件：新失败簇、embedding 模型/维度、chunk recipe 或 corpus revision 变化。

### G-M34-3：外部语料的 embedding、Composer 与 Judge 出站

#### 方案 A：逐用途授权远程 runtime

- 做法：分别登记 embedding、answer generation、Eval judge 的 receiver × node purpose × data class × fields；可只批准其中一项；LangFuse Cloud 继续关闭。
- 影响：可使用现有 DashScope/Qwen transport 形成 semantic 与真实回答证据；必须记录调用、成本、provider 失败和安全投影。
- 适用条件：用户接受公开合成 benchmark 文本/问题按精确字段发送给指定 provider。
- 风险：批量 embedding/180 题 generation 有成本、限流和波动；generation 授权不自动授予 judge。

#### 方案 B：全部本地 runtime

- 做法：embedding、Composer、Judge 都使用本地实现；若当前项目没有合格本地模型，需要另行引入并验证。
- 影响：不外发数据，但模型部署、依赖、GPU/内存和效果验证可能显著扩大 M34。
- 适用条件：数据不得外发，且用户接受本地模型接入成本。
- 风险：本地模型建设可能成为新的主问题，拖延 corpus 接入；不能用 M33 全文 extractive Composer冒充多文档回答。

#### 方案 C：只完成检索与确定性回答合同，不运行真实语义回答

- 做法：保持所有远程 deny，只跑 lexical/安全/citation fixture。
- 影响：可以证明部分工程接线，但不满足本轮“真实回答与可复现 Eval”完成目标。
- 适用条件：只能作为阶段性阻塞状态或用户主动缩小目标。
- 风险：若仍称 M34 完成，会重复 M33 的玩具化证据问题。

#### 建议与确认时点

- 建议：在 M34-A/B 完成 payload、数量和成本估算后，优先选择 A 的最小授权组合：embedding 与 generation 分别确认，Judge 保持 advisory 且可单独 deny；若用户不允许外发，再评估 B，而不是静默采用 C。
- 用户确认前允许推进：数据解析、local lexical、deterministic security tests、payload/cost 清单。
- 用户确认前禁止推进：任何真实 embedding/generation/judge 网络调用、修改默认 outbound policy 或把 provider 失败记成业务失败。
- 需要确认的时点：首次真实 provider smoke 前；full corpus embedding 和 180 题 Answer Eval 各自遵守一次精确运行授权。
- 重开决策的条件：receiver/model/data fields、dataset classification、成本或 provider 数据政策变化。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 dataset closed-world | 全量扫描 + hash + 负向漂移 fixture | 36,417 source instances、180 题、274 gold、0 missing、3 conflict IDs 与 manifest 精确一致 | 必须完成 |
| C2 parser/normalizer | 三来源样本、转义换行、短/长/异常、往返定位 | 无静默丢文；规范化和 unit 统计闭合；每个 anchor 可回 raw source | 必须完成 |
| C2 chunk 选择 | 同 parser/corpus/dev split 的候选对照 | 只改变 unit recipe；选择理由包含 gold coverage/context/citation/成本，不继承参考参数 | 必须完成 |
| C3 full build | candidate build/reload/inspect | 完整 corpus/unit row count、hash、dimension、index identity 对账；项目外 derived 可重建 | 必须完成 |
| C3 原子切换/回滚 | partial insert、hash/dimension、pointer replace 故障 | 半成品不 active；旧 external profile 完整保留；业务 active release 不动 | 必须完成 |
| C4 ACL 与 Tool | allowed/denied/stale/unknown unit/index unavailable | pre-selection 与 pre-generation 都生效；未授权正文不进 adapter/context/projection | 必须完成 |
| C4 规模检索 | 180 题 full-corpus retrieval | 一题一次 Tool；actual candidate/selected refs、latency、identity 可复算 | 必须完成 |
| semantic 能力 | 52 semantic 题同 corpus held-out A/B | 报告 lexical 与 candidate 的配对结果和失败簇；无同条件净收益则不宣称提升 | 必须完成 |
| long-document 能力 | 长度桶 + gold document/context/citation 检查 | 长文 gold 能进入受控 context 并回到稳定 anchor；不以整篇全文直出通过 | 必须完成 |
| multi-document 能力 | 38 题 expected-set coverage + AnswerFlow/citation | 分别报告 all-gold/partial coverage；完整 claim 不缺必需 Evidence/citation | 必须完成 |
| C5 actual context | capture Composer input + ledger | 仅真实 context units 推进 generation-visible；citation 全来自本轮 context | 必须完成 |
| C5 answer safety | injection、unsupported、budget、provider/citation failure | 未验证答案不公开；四轴/root cause 正交；无 gold shortcut | 必须完成 |
| C6 answer run | smoke → 精确 full run → offline projection | completed run 有 180 个唯一 Scenario 证据或如实 inconclusive；artifact/checkpoint/report identities 一致 | 必须完成 |
| answer correctness | answer facts/gold + advisory judge/人工抽样 | required 只含可确定性验证项；开放语义分数标注 judge/runtime/样本边界 | 必须完成 |
| 性能/成本 | build/query/context/provider telemetry | 至少给出 build 时间/体积/row count、query p50/p95、调用数与可得成本 | 必须完成 |
| C7 22 条回归 | M31/M32/M33 suites + business AnswerFlow | 旧 required Gate 全绿、分母/identity 不变、默认 business profile 不变 | 必须完成 |
| 仓库卫生 | Git 文件清单和大文件扫描 | raw/extracted/大 derived/index 未提交；只有必要轻量 manifest/证据进入仓库 | 必须完成 |

聚焦验证顺序：dataset/parser → unit identity → local index lifecycle → Knowledge Tool/ACL → Evidence/Gate/citation → retrieval Eval closed-world → provider smoke（若授权）→ Answer Eval → M31–M33 回归 → 全仓测试和静态检查。

验收证据必须区分四类结论：

1. **规模已接入**：完整三来源 corpus 的 build/index/runtime identity 与真实查询证明；
2. **检索有效**：同 corpus/split 的 gold coverage 和 paired A/B 证明；
3. **回答链有效**：actual context、claims、citations 和 answer artifact 证明；
4. **仍未证明**：合成英文数据能否代表真实企业噪声、生产 ACL/connector、中文跨语料泛化、长期性能/成本和开放答案质量上限。

不能把 22 条业务题与 EnterpriseRAG 180 题做跨 corpus 分数差后称为“提升”。22 条只承担安全/合同回归；semantic/hybrid/chunk 的效果结论必须来自 EnterpriseRAG 内部同 corpus、同 split、同 runtime 合同的对照。

## 9. 依赖与交付物

### 依赖

- M31 trusted caller、ACL/outbound、typed Evidence、Citation Validator、immutable release 纪律。
- M32 `KnowledgeTool` / retrieval adapter seam 与 retrieval-only Eval 纪律。
- M33 `RAGAnswerFlow`、Shared Gate、generation context、四轴结果和 answer/citation Eval 纪律。
- 项目外 EnterpriseRAG-Bench `v1.0.0` 三来源数据与官方 questions。
- `docs/phase4-roadmap.md` 第 4、8、14、16 节和 `docs/phase4-reference.md` 的 chunk/retrieval/Eval 能力卡。
- `docs/state/runbook.md` 的真实 Eval 一次精确运行、checkpoint/artifact 与等待纪律；`schema-retrieval-milvus-embedding.md` 只提供可借鉴的 clean collection 规则。
- 若使用远程 runtime：用户对 G-M34-3 的精确授权、可用 provider key/网络和独立成本预算。

### 交付物

- versioned external dataset/corpus/build/index manifest 与验证入口。
- 三来源 parser/normalizer、document/retrieval/context unit builder 和稳定 anchor/identity。
- 独立 external Knowledge profile、index adapter、candidate/active lifecycle 与 inspect/rollback 证据。
- 复用现有 Knowledge Tool / AnswerFlow 的大 corpus 接线和必要的 Document Evidence payload 演进。
- full 180 retrieval Eval family、真实 AnswerFlow Eval family、closed-world artifact/report/checkpoint。
- lexical/semantic/可能的 hybrid 单变量对照、失败簇、性能/成本与适用边界。
- 22 条业务回归、M34 notes、收工 state/changelog/dev-log 更新和 P3 handoff。

只冻结职责和证据合同，不在计划阶段提前固定类名、文件拆分、chunk/top-k、阈值、融合公式、embedding 模型、Milvus index 参数、Composer prompt 或 Judge。

## 10. 遗留与后续

- 本模块完成但刻意不处理：公开 HTTP/Router 如何选择 external profile、SQL/RAG Hybrid、生产 connector/ACL、在线同步和 UI 展示。
- 下一模块可直接消费：真实规模 Knowledge Tool adapter、可回查 chunk Evidence、AnswerFlow runtime profile、180 题失败簇和已冻结 Eval artifact。
- P3 规划输入将不再只是 22 条短知识 baseline；Router/Harness 仍必须复用同一个 AnswerFlow，不能因 external profile 新建另一条 RAG 顶层链。
- M34 的失败证据可以触发后续独立的 parent/child、hybrid、rerank 或 query rewrite 决策，但这些能力只有满足第 4 节触发条件才立项。
- 即使 180 题表现良好，也只能说明该合成英文 benchmark 和当前三来源 profile；不能直接宣称生产企业知识检索、真实权限系统或中文业务问答已经解决。
- EnterpriseRAG license/数据归属、provider 数据政策或外部路径不可用若无法在 M34-A 关闭，会成为真实 blocker；不得通过复制 raw 大文件进仓库绕过。

## 11. 开工条件

- 开工前无需确认：只读扫描项目外 v1.0.0；严格筛选 180 题；保留 22 条业务 baseline；不进入 Router/Hybrid/UI；不提交 raw 大文件；不调用真实 provider。
- 实施中需要确认：G-M34-1 在 external profile lifecycle 前；G-M34-2 在 semantic full build 与 external adapter 默认化前；G-M34-3 在首次远程 embedding/generation/judge 调用前。
- 首次建立 notes：执行实现前先创建 `docs/notes/m34-notes.md` 并写 implementation checklist；本次只制定计划，不提前创建实现 notes 或改动代码。
- 默认配置纪律：任何模型、embedding、index backend、outbound 或 active profile 的长期默认变化都必须有同条件证据和用户确认；实验优先使用显式 runtime profile，不直接修改 `.env`。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得为了完成表面进度绕过 ACL、gold isolation、closed-world artifact、active switch 或 provider 授权。
