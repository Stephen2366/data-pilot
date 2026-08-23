# DataPilot Schema Retrieval / Milvus / Embedding 速查

> 本文只保留当前 Schema Retrieval、Milvus 和 embedding 的运行事实。真实 Eval 命令见 [runbook.md](runbook.md)，M27 分母、Gate 与快照见 [eval-baselines.md](eval-baselines.md)，完整历史实验统一从 [CHANGELOG_INDEX.md](CHANGELOG_INDEX.md) 进入。

更新时间：2026-08-24

## 当前结论

- **Text2SQL Schema Retrieval** 默认仍是 `inmemory + deterministic + weighted`：不依赖 Docker 或网络，是 SQL 本地开发和默认 Eval 主线。
- **EnterpriseRAG-Bench 产品 RAG** 是另一条独立链：M44A 后默认使用 Milvus + DashScope `qwen3.7-text-embedding` / 1024 维；不读取 `SCHEMA_VECTOR_BACKEND`，也不改变 Schema Retrieval 默认。
- M27 Schema Milvus 仍只在用户明确要求时启用；不得用这条规则推断 Enterprise RAG 应回退 lexical。
- SiliconFlow embedding 的代码和配置入口仍保留，但不再是日常/M27 Eval 入口；没有用户明确指定时，不选择它。
- M30 隔离 `knowledge_docs` 后，当前 Text2SQL schema document corpus 为 **186 条**，hash 为 `6b67606d782ec834efa2ffcdb94b3cbb8af148223f5a92a176b64f849e2e418d`。
- 历史 M27 Milvus artifact/collection 的 195-doc hash `8a8b6626...` 仍是只读历史身份；它与当前 186-doc corpus 不匹配，后续新运行不得直接复用这些 collection。
- M27 v2 首个 Qwen plus + Milvus Core 为 `28 passed / 0 failed / 6 not_observed`、Gate `inconclusive`；两题 QueryPlan timeout，不足以判断 Milvus 或 embedding 的收益。详见 [eval-baselines.md](eval-baselines.md)。

## 当前配置与选择规则

| 目标 | 配置 / 选择 | 边界 |
|---|---|---|
| 默认检索 | `SCHEMA_VECTOR_BACKEND=inmemory`；`SCHEMA_EMBEDDING_PROVIDER=deterministic` | 当前主线，不自动切换。 |
| M27 Milvus Eval | `SCHEMA_VECTOR_BACKEND=milvus`；`SCHEMA_EMBEDDING_PROVIDER=dashscope`；Qwen embedding 1024 维 | 用户明确要求 Milvus 时才启用。 |
| Oracle | SQLite deterministic seed | 不因 Milvus 实验切换数据库或 `result_match` oracle。 |
| 融合策略 | `weighted` | `rrf` 是历史否定实验，不切默认。 |
| Enterprise 产品 RAG | `ENTERPRISE_RAG_RETRIEVAL_MODE=semantic`；semantic snapshot `9aec12...e20` | SQLite profile 是 authority，Milvus 只选 unit；完整配置与 preflight 见 `runbook-rag.md`。 |

Enterprise 当前 collection 为 `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`，manifest `22c573...97b`，unit-set `17d5af...905f`。M44A 只读加载既有 139,214-unit snapshot，不新建、reset 或重建；不可用时 RAG 失败关闭，不影响 Schema Retrieval 的 inmemory 默认。

用户只说“模型 + Milvus”时，优先复用**同模型、同 suite 的已有 Milvus 快照**所记录的 embedding、维度、collection 与 fusion；若没有这样的快照，必须先让用户指定 embedding，不能按主模型名称猜测。

## M27 artifact 现在记录什么

从本次更新后的新运行开始，`resolved_runtime_identity` 会记录下列可比性事实：

| 字段 | 用途 |
|---|---|
| `schema_vector_backend` / `schema_embedding_provider` | 确认是否真的走 Milvus，以及 provider。 |
| `schema_embedding_model` / `schema_embedding_dimensions` | 区分同一 provider 的不同 embedding 配置。 |
| `milvus_collection` | 确认本轮使用的 collection。 |
| `schema_docs_count` / `schema_docs_hash` | 确认业务 Schema 语料没有悄悄变化。 |
| `schema_fusion_strategy` / `oracle_fixture_identity` | 避免把排序或 oracle 差异混进模型/embedding 比较。 |

这些字段只读取启动时解析的配置与本地 domain pack，不会新建、reset 或写入 collection。已有 M27 v1/v2 artifact 不回写，缺少这些字段时只能作为历史追溯材料。

## Milvus collection 纪律

- 不使用历史污染 collection `datapilot_schema_docs`；它曾被重复灌入，不能作为可信对照。
- 新建 collection 使用不绑定模块号的名称：`datapilot_schema_docs_<purpose>_<model>_<embedding>_<YYYYMMDD_HHMMSS>`。例如：`datapilot_schema_docs_eval_qwen37plus_qwenemb_20260809_223000`。
- 可安全复用已验证的 clean collection：provider、embedding 模型/维度、`schema_docs_hash`、row count 都必须匹配；本次不应新增文档。
- 不为“继续跑分”绕过 hash / dimension mismatch；换 embedding、换维度或 schema 文档变更时，使用新 collection。
- `MILVUS_RESET_COLLECTION=true` 只适合用户明确要求的一次性重建，不作为日常 Eval 方案。

## 常用排查

| 现象 | 先看什么 | 处理 |
|---|---|---|
| Milvus 连接失败 | Docker 是否运行 | `docker ps`，确认 `milvus-standalone` 为 healthy。Windows 宿主 health 端口使用 `19091:9091`。 |
| hash / dimension mismatch | collection 是否来自不同语料或 embedding | 换新 collection；不要绕过校验。 |
| 不知道“Milvus”该配哪种 embedding | 是否有同条件历史快照 | 有则复用；没有则先询问用户。 |
| Core 很慢或超时 | 同一 `run_id` 的 manifest / checkpoint | 按 runbook 继续等待和检查；不擅自加 timeout、开重试、后台化或换 run ID。 |
| Gate `inconclusive` | `not_observed` 的 trace error subtype | 保留 artifact；不自动重跑或登记 baseline。 |

## 历史结论索引

- M20 前的固定 collection 污染已证实，相关分数不能用于 embedding 优劣判断。
- M21 的 RRF 虽提升 retrieval-only 部分召回，但端到端产生新的 plan 问题，结论为不切默认。
- M23 的 Qwen embedding 在 vector-only recall 上有提升，但当时端到端没有足够证据证明收益。
- M26 及以前的 formal/challenge/diagnostic 数字是冻结历史；不与 M27 v2 直接比较。

需要追溯具体模型、collection、旧命令或实验数字时，先读 [CHANGELOG_INDEX.md](CHANGELOG_INDEX.md)，再定点读取对应 Phase 文件与 `eval/reports/` 历史报告，不在本速查文档继续扩充旧口径。
