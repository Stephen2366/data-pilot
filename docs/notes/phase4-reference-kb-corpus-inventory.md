# Phase 4 参考项目知识库规模与存放方式盘点

> 调查日期：2026-08-15  
> 调查对象：本地 `D:\.Work\Practice\Python-Practice\references` 中与 RAG/Knowledge 直接相关的参考项目  
> 文档性质：参考调查材料，不是新模块 plan，不改变 Phase 4 roadmap、当前默认配置或已冻结合同

## 1. 调查目的与口径

本次调查专门回答两个问题：

1. 参考项目实际附带了多少知识内容，单篇和整体规模多大；
2. 原始知识、处理中间物、chunk、向量索引、图谱和运行时元数据分别存在哪里。

统计只把实际可作为知识原件或明确派生物的数据纳入结论，不把 README、项目文档、依赖锁文件和普通测试代码混成“知识库规模”。PDF 页数与可抽取文本字符数通过 `pypdf` 只读统计；Markdown、JSON、CSV、Excel 直接按本地文件读取。所有数字只代表当前本地参考快照，不代表项目在线部署的最大容量或生产数据量。

## 2. DataPilot 当前对照基线

`domain_pack/kb_docs/` 当前包含：

- 10 份 Markdown，合计 `7,706 bytes`、约 `4,550` 个字符；
- 平均每份约 `455` 字符，最短 `396`、最长 `543` 字符；
- 12 条从 `metrics.yaml` 派生的 metric projection，配置文件约 `4.6 KB`；
- catalog 共 22 个逻辑 entry，但这不等于 22 份完整企业文档。

因此，当前 corpus 的准确定位是：用于验证 authority、release、ACL、Evidence、citation 和 Eval 合同的小型 fixture corpus。它尚不足以证明长文、多文档或企业规模检索能力。

## 3. `all-in-rag`

### 3.1 项目不是单一知识库，而是多种规模的数据集

| 数据集 | 原件规模 | 主要用途 |
|---|---:|---|
| `data/C1/markdown/easy-rl-chapter1.md` | `56.3 KB` | 单篇长 Markdown 的基础 RAG |
| `data/C2/pdf/rag.pdf` | `3.37 MB`、5 页、约 7,956 个可抽取字符 | PDF 加载与解析示例 |
| `data/C3/pdf/IPCC_AR6_WGII_Chapter03.pdf` | `20.74 MB`、172 页、约 1,069,770 个可抽取字符 | sentence-window、索引优化和 Eval 等长文实验 |
| `data/C8/cook/dishes/**/*.md` | 323 份、合计 `528.4 KB` | 多文档领域知识库 |
| `data/C9/cypher/nodes.csv` | 5,760 行、`810.7 KB` | 菜谱图谱节点 |
| `data/C9/cypher/relationships.csv` | 6,055 行、`275.6 KB` | 菜谱图谱关系 |

C8 菜谱 Markdown 的大小分布：平均约 `1.6 KB`，中位数约 `1.5 KB`，最小约 `0.4 KB`，最大约 `11.5 KB`。这些文件按水产、早餐、调料、甜品、饮品、肉类、主食、汤和蔬菜等目录组织。

### 3.2 C8 多文档知识库的存放链路

```text
data/C8/cook/dishes/**/*.md       # 原始 Markdown，323 份
    ↓ 递归读取
MarkdownHeaderTextSplitter        # 按 Markdown 标题切分
    ↓
BAAI/bge-small-zh-v1.5            # embedding
    ↓
FAISS                             # 派生向量索引
    ↓
code/C8/vector_index              # 默认本地保存目录
```

关键源码：

- `all-in-rag/code/C8/config.py`
- `all-in-rag/code/C8/rag_modules/data_preparation.py`
- `all-in-rag/code/C8/rag_modules/index_construction.py`

### 3.3 C9 图谱链路

C9 从 C8 菜谱 Markdown 读取内容，用 LLM 提取菜谱、食材、步骤等实体和关系，生成 `nodes.csv`、`relationships.csv` 与导入 Cypher，再进入 Neo4j。它展示的是“同一批领域原件可派生向量索引和图谱”，而不是让图 CSV 取代原件。

### 3.4 对 DataPilot 的直接启示

- 长文实验应至少包含真正的十万至百万字符级材料，不能只在几百字短文上调整 chunk；
- 多文档实验可以同时使用大量小知识单元和少数长文，两者解决的问题不同；
- 原件、FAISS/向量索引和 Neo4j 图谱应视为不同层次，派生物不能反过来冒充 authority。

## 4. GustoBot

GustoBot 同时存在多套相互独立的知识资产和存储链路，不能把它们误算成一个整洁的单库。

### 4.1 大型结构化菜谱数据

| 原件 | 规模 | 记录长度 |
|---|---:|---:|
| `data/recipe.json` | 约 `23.3 MB`、19,669 条菜谱 | 平均约 407 字符，中位数 370，最大 2,855 |
| `data/excipients.json` | 约 `1.25 MB`、1,234 条食材/辅料 | 平均约 369 字符，中位数 346，最大 1,269 |

菜谱记录包含主食材、辅料、耗时、口味、工艺、做法和类型等结构化字段。它说明领域知识库不一定表现为几十份长文，也可以是上万条结构化知识记录。

### 4.2 Excel 入库与 PostgreSQL + pgvector

仓库附带的 `data/kb/历史菜谱源头.xlsx` 只有 1 个 sheet、8 行，是入库流程样例，不等于主菜谱数据规模。处理链路为：

```text
Excel 多 sheet / 多行
    ↓
逐行扁平化，或由 LLM 重写成可检索文本
    ↓
save/<timestamp>/processed_data.csv
save/<timestamp>/processed_data.txt
    ↓
PostgreSQL searchable_documents
```

`searchable_documents` 同时保存 `source_table`、`source_id`、`content`、`embedding`、公司、年份、metadata、content hash 等字段，并用 `(source_table, source_id)` 唯一约束支持增量更新。检索层使用 pgvector 相似度，可选 reranker；workflow 还存在 PostgreSQL 无结果后转 Milvus 的级联路径。

关键源码：

- `GustoBot/kb_ingest/kb_service/services/processor.py`
- `GustoBot/kb_ingest/kb_service/services/vector_store.py`
- `GustoBot/kb_ingest/kb_service/services/search.py`

### 4.3 LightRAG 派生数据

`data/lightrag/` 当前保存：

- 50 个 full documents；
- 50 个 text chunks；
- 50 个 chunk vector records；
- 134 个 entity vector records；
- 83 个 relationship vector records；
- embedding dimension 为 1024；
- 另有 GraphML、KV JSON、LLM response cache 和向量 JSON。

这是一套文件化 LightRAG/图谱派生数据，与大菜谱 JSON、Excel→pgvector 和另一套 Milvus wrapper 并行存在。

### 4.4 对 DataPilot 的直接启示

- 企业知识既可能来自长文，也可能来自上万条结构化业务记录；
- source ID、业务字段、正文、hash 和 embedding 可以在关系库中形成可检索投影；
- GustoBot 的规模值得参考，但多套知识系统并存、source/revision/ACL 不统一的问题不应照搬。

## 5. DB-GPT

### 5.1 仓库内附带的长 PDF

`docker/examples/fin_report/pdf/` 有 5 份上市公司 2019 年年报：

- 合计 857 页；
- 可抽取文本合计约 775,415 个字符；
- 单份 121～204 页、约 1～1.4 MB。

`examples/agents/example_files/` 另有：

| 文件 | 大小 | 页数 | 可抽取文本 |
|---|---:|---:|---:|
| `Nuclear_power.pdf` | `3.29 MB` | 53 | 约 187,096 字符 |
| `Taylor_Swift.pdf` | `6.81 MB` | 83 | 约 305,594 字符 |

这些是仓库内的长文示例，不代表 DB-GPT 正式 Knowledge Space 的容量上限。

### 5.2 正式 Knowledge Space 存放链路

```text
用户上传 PDF / Markdown / Word / Excel / CSV / PPTX / HTML 等
    ↓
FileStorage 保存原文件并返回 file URI
    ↓
knowledge_document 表保存文档元数据、状态、chunk_size、vector_ids、summary
    ↓
document_chunk 表保存切分正文和 meta_info
    ↓
Knowledge Space 选择的 vector store 保存 embedding
    ↓
KnowledgeSpaceRetriever 检索
```

关键源码：

- `DB-GPT/packages/dbgpt-app/src/dbgpt_app/knowledge/api.py`
- `DB-GPT/packages/dbgpt-serve/src/dbgpt_serve/rag/models/document_db.py`
- `DB-GPT/packages/dbgpt-serve/src/dbgpt_serve/rag/models/chunk_db.py`
- `DB-GPT/packages/dbgpt-ext/src/dbgpt_ext/rag/knowledge/`

它的核心特点不是“源码目录里固定放多少文档”，而是运行时创建 Knowledge Space、上传原件、管理 document/chunk 元数据并选择向量后端。

## 6. `agentic-rag-for-dummies`

当前本地快照没有附带可用于统计的正式业务 PDF/Markdown corpus。`notebooks/data/curated_ragas_qa.json` 约 25 KB，是 Eval 问答集，不是知识原件。

它预期由用户上传文档，存放链路为：

```text
docs/*.pdf                         # 用户原始 PDF
    ↓ PDF → Markdown
markdown_docs/*.md                # 转换后的 Markdown
    ↓ parent/child chunking
parent_store/*.json               # parent chunk 文件存储
qdrant_db                         # child dense + sparse 向量
```

默认 child 约 500 字符、overlap 100，parent 目标 2,000～4,000 字符。该项目能证明承载和检索方式，不能用仓库内置数据证明实际企业 corpus 规模。

关键源码与说明：

- `agentic-rag-for-dummies/project/README.md`
- `agentic-rag-for-dummies/project/config.py`
- `agentic-rag-for-dummies/project/document_chunker.py`
- `agentic-rag-for-dummies/project/db/parent_store_manager.py`
- `agentic-rag-for-dummies/project/db/vector_db_manager.py`

## 7. WrenAI 与 Alibaba DataAgent 的适用边界

### WrenAI

WrenAI 当前参考入口主要把 `knowledge/sql/*.md` 当作 NL→SQL 示例记忆：Markdown 是 source，Grep 或 LanceDB 是派生索引。它适合参考原件/索引分离和重建生命周期，不是通用企业文档 corpus 的长度对照。

### Alibaba DataAgent

DataAgent 的 vector documents 主要来自数据源、Schema、Evidence 等平台对象，并提供 metadata replacement、Graph、checkpoint 和 Human-in-the-loop。它没有随仓库附带一套可与政策长文直接比较的企业文档 corpus，适合参考控制流和更新机制，不适合证明文档知识库规模。

## 8. 横向结论

| 项目 | 实际知识规模特征 | 原件位置 | 主要派生存储 |
|---|---|---|---|
| DataPilot 当前 | 10 份 Markdown、约 4,550 字符 + 12 metric entries | `domain_pack/kb_docs/`、`metrics.yaml` | immutable release；当前无正式文档向量索引 |
| all-in-rag | 172 页百万字符长 PDF；323 份 Markdown；5,760 节点/6,055 关系 | `data/C1-C9/` | FAISS、LlamaIndex、Milvus、Neo4j，按章节实验 |
| GustoBot | 19,669 菜谱 + 1,234 食材；另有 50-doc LightRAG 快照 | `data/*.json`、Excel、TXT | PostgreSQL+pgvector、Milvus、LightRAG JSON/GraphML、Neo4j |
| DB-GPT | 仓库示例含 857 页年报和其他长 PDF；生产规模由上传决定 | FileStorage / Knowledge Space | 关系库 document/chunk metadata + 可插拔 vector store |
| agentic-rag-for-dummies | 仓库不附正式 corpus，用户上传任意 PDF | `docs/` → `markdown_docs/` | parent JSON + Qdrant child dense/sparse vectors |
| WrenAI | NL→SQL 示例 Markdown，不是通用文档库 | `knowledge/sql/*.md` | Grep 或 LanceDB |
| DataAgent | 数据源/Schema/Evidence 文档，不附企业政策 corpus | 平台数据库与 metadata | vector store + Graph state/checkpoint |

结论不是“企业级必须有固定文档数”，而是 DataPilot 当前规模连长文切分、多文档召回和真实索引压力都无法触发。参考项目展示的有效尺度包括百万字符长文、数百文件领域库、近两万条结构化知识、数百页企业年报，以及原件/document/chunk/vector/graph 分层存储。

## 9. 外部语料能否直接复用

结论是：**可以复用，但只能在来源和许可证允许的范围内，并且必须区分“外部工程压力语料”和“DataPilot 正式业务语料”**。不能因为某个 GitHub 仓库整体开源，就默认其中转载的 PDF、年报、网页导出或第三方数据也都获得了相同的再分发授权。

### 9.1 当前参考项目的许可证线索

| 项目 | 仓库声明 | 当前可得出的结论 | 仍需单独核对的内容 |
|---|---|---|---|
| `all-in-rag` | README 声明 CC BY-NC-SA 4.0 | 非商业学习项目可在署名、非商业和相同方式共享条件下复用本项目作品 | 单独下载或转载的 PDF、数据集是否另有来源声明；对外分发改编语料时的署名与 ShareAlike 要求 |
| GustoBot | Apache License 2.0 | 可按许可证复用仓库中的代码和由项目有权许可的作品，并保留许可证/NOTICE 要求 | `recipe.json`、`excipients.json`、Excel、LightRAG 数据的原始来源与项目是否有权覆盖这些数据 |
| DB-GPT | MIT License | 可按 MIT 复用代码和由项目有权许可的仓库内容，并保留版权与许可声明 | 上市公司年报、示例 PDF 等第三方文档的内容权利不应仅凭仓库 MIT 推断 |
| `agentic-rag-for-dummies` | MIT License | 可复用其代码和入库/切分实现；当前仓库本身没有正式业务 corpus 可直接搬用 | 用户自行上传文档的来源、授权和隐私仍由使用者负责 |

因此，实际复制任何语料前至少要建立一条来源记录，包含：

- 原项目、原始相对路径和可回查 URL；
- 文件或数据集的作者/来源说明；
- 仓库许可证与数据自己的许可证，二者不一致时以更具体的数据许可为准；
- 是否允许修改、再分发和商业使用；
- 本地 SHA-256、获取日期和是否做过改写/裁剪；
- 在 DataPilot 中的用途：只做本地压力测试、可提交测试 fixture，还是允许进入正式业务 corpus。

来源或授权说不清的文件，可以本地临时研究，但不进入 Git、不进入可发布 release，也不作为 DataPilot 的正式 authority。

### 9.2 两套 corpus 必须隔离

#### A. 外部工程压力 corpus

用途是验证通用 ingestion、长文切分、多文档检索、索引重建和性能，不要求与 DataPilot 电商业务一致。例如：

- `all-in-rag` C8 的 323 份菜谱 Markdown：适合多文件、目录递归、短文档分布和真实索引压力；
- 许可证和来源另行核准后的长 PDF：适合页级解析、标题层级、parent/child、跨章节检索；
- 许可证和来源另行核准后的大 JSON/CSV：适合上万条结构化知识记录的增量入库与更新。

它们应放在独立的外部 benchmark/fixture 目录或由本地脚本按来源下载，保留 LICENSE/ATTRIBUTION/manifest；不能进入 `domain_pack/kb_docs/`，不能成为客服政策 citation，也不能用来证明 DataPilot 已具备电商业务知识。

#### B. DataPilot 正式业务 corpus

用途是验证和展示电商数据分析 Agent 的真实 RAG/Hybrid 能力。它必须围绕同一个虚构企业及一致业务规则建设，至少覆盖政策、SOP、产品/服务说明、FAQ、异常案例、客服处理单元、指标说明和安全规则。

正式业务 corpus 可以参考公开资料的文档形态和主题，但不能把其他平台政策原文改个名字就冒充 DataPilot authority。若内容由 AI 辅助生成，应先冻结业务规则/事实表，再生成文档和案例，最后执行跨文档一致性、指标 authority、版本冲突和人工抽查；在项目说明中如实标记为 synthetic enterprise corpus。

两套 corpus 可以复用同一条 loader/chunker/index adapter，但必须拥有独立的 corpus identity、release、索引、Eval catalog 和结论。外部压力 corpus 通过，只能证明工程承载能力；正式业务 corpus 通过，才能证明 DataPilot 的领域检索与回答能力。

## 10. 对 DataPilot 后续语料建设的修正建议

此前仅建议“40～60 个条目”过于保守，也混淆了逻辑 entry 与真实文档规模。以下目标专指 **DataPilot 正式电商业务 corpus**，不把外部菜谱、年报或教程数据混入数量：

- 总量至少达到约 20万～50万中文字符；
- 包含 10～20 份真正的长政策、SOP 或操作手册，而不是每份几百字；
- 增加约 100～300 条 FAQ、异常案例、客服处理单元和产品规则；
- 保留现有由 `metrics.yaml` 派生的指标说明，不把实时业务数据复制成 RAG 静态知识；
- 明确区分 authority 原件、document、parent、child chunk、release、向量索引和图谱派生物；
- 用长文、跨章节、跨文档、版本变化、ACL 和实时事实边界重新建设 retrieval/answer Eval。

上述数量是用于形成有意义工程压力的建设尺度，不是单独的完成标准；最终仍应以真实 Scenario、held-out 失败簇、citation support、安全合同和可重建发布为验收依据。

外部工程压力 corpus 不使用上述业务数量作为验收口径，而是按格式、文件数、总字符/页数、chunk 数、索引规模、构建/更新耗时和检索压力单独记录。正式业务 corpus 和外部压力 corpus 都应至少留一份固定但不参与调参的 held-out 集，不能用同一批公开题面开发实现后再证明效果。

## 11. 本次调查暴露出的参考复核缺口

此前 `docs/phase4-reference.md` 主要围绕五个项目的架构、接口、安全反例和控制权进行定点复核，没有建立“参考项目语料资产盘点”维度，也漏掉了 `all-in-rag` 对长 PDF、323 份 Markdown、FAISS 和图谱派生的直接证据。

以后涉及知识库内容、chunk、检索增强或“企业级规模”判断时，参考复核至少同时记录：

1. 原件目录、格式、文件数、总大小和典型长度；
2. 原件是否仓库内置、运行时上传或外部下载；
3. document/parent/child 的数量和稳定身份；
4. 关系库、对象存储、向量库、图数据库分别保存什么；
5. corpus 是否只是 demo、教程分章数据，还是项目实际默认知识资产；
6. 相关 Eval 是否真的覆盖该规模和文档形态。
7. 仓库许可证是否覆盖目标数据，数据是否还有独立来源/许可/隐私限制；
8. 该语料属于外部工程压力 corpus 还是 DataPilot 正式业务 corpus，二者的 release/index/Eval 是否隔离。

这份盘点只补充调查事实，不自动授权 DataPilot 引入 PDF、parent/child、图谱、embedding、rerank 或新的默认存储。涉及这些核心范围时，仍需按 roadmap 和 module plan 单独确认。

## 12. 修订记录

- **2026-08-15 复用边界补充**：增加参考仓库许可证与第三方数据需分别核对的提醒；将后续语料拆为“外部工程压力 corpus”和“DataPilot 正式业务 corpus”，明确两者共享 ingestion interface 但隔离 authority、identity、release、index、Eval 和能力结论；原企业化数量建议只适用于正式电商业务 corpus。
