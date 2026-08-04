# DataPilot Schema Retrieval / Milvus / Embedding 速查

> 本文是 DataPilot 的 Schema Retrieval、Milvus 向量库和 embedding 实验速查。Trigger：只要涉及 `SCHEMA_VECTOR_BACKEND`、`SCHEMA_EMBEDDING_PROVIDER`、Milvus collection、embedding A/B、`schema_docs_hash`、schema retrieval 召回质量或 M20 clean run 结论，必须先读本文。当前运行命令入口仍以 `docs/state/runbook.md` 为准，长期 eval 数字以 `docs/state/eval-baselines.md` 为准。

更新时间：2026-08-03

## 一句话结论

默认链路仍是 **`inmemory + deterministic`**，Milvus / SiliconFlow / DashScope-Qwen embedding 只作为显式实验路径。M20 已修复“固定 Milvus collection 被重复灌入”的实验污染问题：后续 clean 实验必须使用唯一 collection 或干净 collection，并在报告中检查 `schema_docs_hash`、row_count、embedding 配置和 `schema_vector_index_reuse`。

## 当前默认与边界

| 项目 | 当前值 / 口径 | 说明 |
|---|---|---|
| 默认向量后端 | `SCHEMA_VECTOR_BACKEND=inmemory` | 不依赖 Docker、不联网，服务本地开发和默认 eval。 |
| 默认 embedding | `SCHEMA_EMBEDDING_PROVIDER=deterministic` | 稳定可复现，不代表真实 embedding 能力上限。 |
| Milvus | `SCHEMA_VECTOR_BACKEND=milvus` | 只在显式实验时开启；需要本地 Milvus 服务。 |
| SiliconFlow embedding | `SCHEMA_EMBEDDING_PROVIDER=siliconflow` | 需要 API key；当前不切默认。 |
| DashScope / Qwen embedding | `SCHEMA_EMBEDDING_PROVIDER=dashscope` 或 `qwen` | 常用模型 `qwen3.7-text-embedding`，维度 `1024`；当前不切默认。 |
| `result_match` oracle | SQLite deterministic seed | M20 只做 MySQL audit 和报告标注，未切换 scorer oracle。 |

长期选择边界：

- 不自动把 Milvus 升级为正式默认路径。
- 不自动更换默认 embedding 模型或维度。
- 不因一次 clean eval 好看或难看就宣布某个 embedding 胜出 / 失败。
- 不在未确认前改变 formal / challenge / diagnostic case 集或 `result_match` oracle backend。

## 关键代码入口

| 文件 | 作用 | 阅读重点 |
|---|---|---|
| `engine/schema_retrieval/document_builder.py` | 构建 field / metric / relation 三类 schema docs | `build_schema_documents()` 当前生成 193 条文档；`schema_documents_hash()` 给文档版本打指纹。 |
| `engine/schema_retrieval/vector_index.py` | In-memory 与 Milvus vector index | `MilvusVectorIndex` 会检查 collection row_count / vector dimension，拒绝污染 collection。 |
| `engine/schema_retrieval/retriever.py` | keyword + vector + merged hits | `build_configured_schema_vector_index()` 供 eval run 内复用 index。 |
| `engine/nl2sql/pipeline.py` | Text2SQL pipeline 调用 retrieval | 可接收外部 `schema_vector_index`，不改变默认调用。 |
| `eval/run_eval.py` | Eval runner / Markdown 报告 | Milvus eval 时预建 run-scoped index，并写 `Eval Runtime Metadata`。 |
| `scripts/smoke_m20_milvus_index.py` | M20 Milvus clean collection smoke | 验证 `row_count == len(schema_documents)`。 |
| `scripts/audit_m20_eval_ground_truth.py` | M20 MySQL ground truth audit | 用 MySQL 执行 expected SQL，但不改 scorer oracle。 |

核心流向：

`build_schema_documents()`
→ `schema_documents_hash()`
→ `MilvusVectorIndex`
→ `app.state.schema_vector_index`
→ `run_text2sql_pipeline()`
→ `retrieve_schema()`
→ `Eval Runtime Metadata`

## Milvus Collection 纪律

M20 前的旧固定 collection `datapilot_schema_docs` 已确认被重复灌入污染：schema docs 实际 193 条，历史 row_count 曾达到 19493。因此后续实验不要直接复用这个旧 collection 作为可信对照。

推荐做法：

- 每次实验使用唯一 collection 名，命名格式固定为 `datapilot_schema_docs_m20_<model>_<embedding>_<YYYYMMDD_HHMMSS>`（日期 + 秒级时间戳），不要手动使用 `_a` / `_b` 序号后缀（2026-08-02 起要求，防止重复 / 误复用）。
- 示例：`datapilot_schema_docs_m20_qwen37max_qwenemb_20260802_214810`；命名前先用 `date +%Y%m%d_%H%M%S` 取当前时间戳。
- clean collection 的验收条件至少包括：
  - `schema_docs_count=193`
  - `milvus_final_row_count=193`
  - `schema_vector_index_reuse=run_scoped`
  - `schema_docs_hash` 有记录
  - embedding provider / model / dimension 有记录
- 如果已有 collection 的 row_count 或 vector dimension 不匹配，当前代码会拒绝复用。不要为了继续跑分临时绕过这个错误。

### clean collection 的安全复用

同一个 clean collection 可以被多个独立 eval run 复用，但必须同时满足：

- `schema_docs_hash` 相同；
- embedding provider / model / dimension 相同；
- `milvus_initial_row_count == schema_docs_count`；
- `milvus_inserted_document_count == 0`；
- `milvus_final_row_count == schema_docs_count`。

M21 多次复用 `datapilot_schema_docs_m21_qwen_weighted_20260803_001` 时，均满足 `193 → 0 → 193`，因此是复用 clean collection，不是重复灌入。

注意：`schema_vector_index_reuse=run_scoped` 表示“单个 eval run 内只创建并复用一个 vector index”，不表示每次 eval run 都必须新建 collection。

可接受但要说明用途的方案：

| 方案 | 使用场景 | 风险 |
|---|---|---|
| 唯一 collection | 推荐的 eval / smoke 实验方式 | collection 会变多，需要后续显式清理。 |
| `MILVUS_RESET_COLLECTION=true` | 一次性本地重建验证 | 固定 collection reset 有误删和并发风险，不建议作为长期默认。 |
| upsert / delete-by-doc-id | 后续正式服务形态 | 需要单独验证 Milvus API 一致性；M20 未实现。 |

## 报告字段怎么读

M20 后，`eval/run_eval.py` 的 Markdown 报告会出现 `Eval Runtime Metadata`。重点看：

| 字段 | 含义 |
|---|---|
| `result_match_oracle_backend` | 当前 `result_match` 标准答案来源；M20 为 `sqlite_deterministic_seed`。 |
| `schema_vector_backend` | 本轮是否真的走 Milvus。 |
| `schema_embedding_provider` | 本轮 embedding provider。 |
| `schema_vector_index_reuse` | `run_scoped` 表示一个 eval run 内复用同一个 index。 |
| `schema_docs_count` | 当前 schema docs 数量，M20 为 193。 |
| `schema_docs_hash` | schema docs 内容指纹，用于复现实验版本。 |
| `milvus_collection` | 本轮 collection 名；应优先是唯一实验名。 |
| `milvus_initial_row_count` | 本次 eval 开始时 collection 的行数。 |
| `milvus_inserted_document_count` | 本次 eval 实际新增的 schema docs 数量；复用 clean collection 时应为 `0`。 |
| `milvus_final_row_count` | clean collection 应等于 `schema_docs_count`。 |
| `milvus_dimension` | 当前 embedding 向量维度。 |

读 embedding A/B 时，不只看 passed/total，还要看 failure distribution。比如 clean run 后 `schema_context` 降了但 `query_plan` 升了，说明检索和生成之间可能发生了能力转移，不能简单宣布总分提升。

## 当前实验结论

M19 污染链路：

- Qwen `qwen3.7-max` + Qwen embedding：formal `8/10`、challenge `12/16`、diagnostic `20/32`。
- DeepSeek `deepseek-v4-flash` + Qwen embedding diagnostic：`19/32`。
- 由于固定 collection 被重复灌入，不能用这批结果直接判断 embedding 模型优劣。

M20 clean 链路：

- Milvus smoke：clean collection `row_count=193`，`schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`。
- DeepSeek `deepseek-v4-flash` + clean Milvus + DashScope `qwen3.7-text-embedding` diagnostic：`17/32`。
- Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic：`21/32`（collection `datapilot_schema_docs_m20_qwen37max_qwenemb_20260802_214810`，`row_count=193`、run_scoped）。

当前结论：

- Clean Milvus 链路上 Qwen `qwen3.7-max` 为 `21/32`，高于同链路 DeepSeek `17/32` 和 M19 污染 Qwen `20/32`；差距主要来自 LLM 本身（Qwen 消除 query_plan / plan_validation 失败），不是 embedding 优劣结论。
- `schema_context` 仍是最大失败簇（7/32），换模型不能替代 schema 上下文修复。
- M21 controlled Qwen-plus A/B：固定 `qwen3.7-plus`、weighted、同一 32 题和 oracle，只比较 `inmemory + deterministic` 与 clean Milvus/Qwen embedding；两组均为 `21/32`，`schema_context=6` 和 `failure_subtype` 分布完全相同，没有端到端 embedding 提分证据。
- M21 collection reuse audit：`datapilot_schema_docs_m21_qwen_weighted_20260803_001` 在多次 Qwen-plus weighted / RRF / embedding A/B 中均记录 `milvus_initial_row_count=193`、`milvus_inserted_document_count=0`、`milvus_final_row_count=193`，且 schema hash 与 embedding 配置一致；这些测试是安全复用 clean collection，不构成 Milvus 污染。
- 单次真实 LLM run 有非确定性；不据此切换默认 embedding / Milvus / 默认模型，默认仍保持 `inmemory + deterministic`。

## Retrieval-only Benchmark

完整 Text2SQL diagnostic 会混入 LLM 生成能力，所以已新增 retrieval-only benchmark 专门观察 Milvus + embedding 的召回能力：

- 用例集：`eval/cases/schema-retrieval-embedding-benchmark.yaml`
- Runner：`eval/run_schema_retrieval_benchmark.py`
- 测试：`tests/test_schema_retrieval_embedding_benchmark.py`

这个 benchmark 不调用 LLM、不执行 SQL，只检查问题能否召回期望的 tables / columns / metrics / relations。报告同时输出三条链路：

| 指标 | 含义 |
|---|---|
| `avg_keyword_overall_recall` | 只看关键词召回 hits 构造出的 SchemaGraph。 |
| `avg_vector_overall_recall` | 只看向量召回 hits 构造出的 SchemaGraph，最能体现 embedding 能力。 |
| `avg_overall_recall` | 当前真实 pipeline 使用的 merged hits 召回结果。 |

首轮数据：

| 链路 | avg_overall_recall | avg_keyword_overall_recall | avg_vector_overall_recall | 说明 |
|---|---:|---:|---:|---|
| `inmemory + deterministic` | 0.738 | 0.738 | 0.787 | 默认基线。 |
| `Milvus + DashScope qwen3.7-text-embedding` | 0.738 | 0.738 | 0.929 | Qwen embedding 的 vector-only 明显更好，但 merged recall 没变。 |

解读：

- Qwen embedding 在 **vector-only recall** 上确实显示出能力，尤其更容易把 relation / metric 文档放进 vector top docs。
- 当前完整 merged recall 没提升，说明瓶颈可能在 **keyword + vector 融合策略**：keyword 分数较强时，vector 命中的好文档未必进入最终 merged top_k。
- 因此下一步如果继续优化检索，不应直接换默认 embedding，而应先单独评估 fusion / RRF / rerank / top_k 策略。

## M21 Fusion 实验结论

M21 保持默认 `weighted` merge，新增只可显式传入的 `rrf` 实验策略；它只使用候选 hit 的线上 rank，任何 `expected_*` benchmark 标签都不能进入排序。

- retrieval-only（`top_k=12`）：deterministic merged overall `0.738 → 0.802`；Milvus + Qwen embedding merged `0.738 → 0.929`、metric `0.600 → 0.900`、relation `0.633 → 0.967`。
- 端到端同配置 DeepSeek diagnostic（Qwen embedding、clean collection `datapilot_schema_docs_m21_qwen_weighted_20260803_001`、row_count `193`、hash `7b531e...`）：weighted `21/32`，RRF `18/32`；RRF 让 `schema_context 5 → 4`，但新增 `plan_validation 0 → 3`、`schema_retrieval 0 → 1`。
- 结论：**RRF 是否定实验，不切默认。**retrieval-only 覆盖提升不能替代同配置 Text2SQL / triage 验证；下一步先逐 case 看 context assembly 与 QueryPlan 耦合，不能直接增大 top_k 或引入 reranker。

## 常用命令

```powershell
# 检查 Milvus 容器是否运行
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# M20 clean collection smoke：预期 final_row_count=193
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.smoke_m20_milvus_index --output eval/reports/m20-milvus-index-smoke.md

# MySQL expected_sql audit：只读审查，不改变 scorer
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.audit_m20_eval_ground_truth

# DeepSeek + clean Milvus + Qwen embedding diagnostic 示例
$env:LANGFUSE_ENABLED='false'
$env:LLM_PROVIDER='deepseek'
$env:LLM_MODEL='deepseek-v4-flash'
$env:SCHEMA_VECTOR_BACKEND='milvus'
$env:SCHEMA_EMBEDDING_PROVIDER='dashscope'
$env:QWEN_EMBEDDING_MODEL='qwen3.7-text-embedding'
$env:QWEN_EMBEDDING_DIMENSIONS='1024'
$env:MILVUS_COLLECTION='datapilot_schema_docs_m20_deepseek_qwenemb_<YYYYMMDD_HHMMSS>'  # 时间戳命名，防重复；先用 date +%Y%m%d_%H%M%S 取时间戳
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --pipeline-mode new_text2sql --trace eval/traces/<name>-traces.jsonl --report eval/reports/<name>-report.md --triage-json eval/reports/<name>-triage.json

# Retrieval-only deterministic baseline
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_schema_retrieval_benchmark --report eval/reports/schema-retrieval-embedding-deterministic-report.md --top-k 12

# Retrieval-only Milvus + Qwen embedding
$env:SCHEMA_VECTOR_BACKEND='milvus'
$env:SCHEMA_EMBEDDING_PROVIDER='dashscope'
$env:QWEN_EMBEDDING_MODEL='qwen3.7-text-embedding'
$env:QWEN_EMBEDDING_DIMENSIONS='1024'
Remove-Item Env:\MILVUS_COLLECTION -ErrorAction SilentlyContinue
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_schema_retrieval_benchmark --report eval/reports/schema-retrieval-embedding-qwen-milvus-report.md --top-k 12 --collection-prefix datapilot_schema_retrieval_bench_qwen
```

## 排查菜单

| 现象 | 优先判断 | 处理 |
|---|---|---|
| Milvus 连接失败 | Docker / Milvus 是否启动 | 先 `docker ps`，确认 `milvus-standalone` healthy。 |
| collection row_count 不是 193 | 旧 collection 污染或 schema docs 变化 | 换唯一 collection；不要直接把结果当 A/B 结论。 |
| vector dimension mismatch | collection 来自不同 embedding 模型 / 维度 | 换唯一 collection 或显式 reset。 |
| 不同 embedding 模型复用同一 collection | row_count 和维度可能仍匹配，但向量语义已经不一致 | 更换 provider / model 时必须使用新 collection。 |
| 多个 eval 进程并发写同一 collection | 可能产生竞态或重复写入 | 不并发写同一实验 collection。 |
| `milvus_inserted_document_count > 0` | 本次 eval 发生了实际写入，结果可能不可与之前 run 直接比较 | 立即停止并把该 run 标记为不可比较。 |
| Qwen / DashScope embedding 报 key 错 | `.env` / 环境变量未设置或账号不可用 | 先跑最小 provider smoke；不要改默认 embedding。 |
| eval 很慢或超时 | 真实 LLM + embedding 调用慢 | 长 run 用更长 timeout 或后台日志方式；partial trace 不纳入结论。 |
| 总分变好但 failure 分布变差 | 可能只是 LLM 波动或错误转移 | 对比 triage JSON，不只看总分。 |

## 后续可选改进

- M22 先处理 output table/column contract 与 QueryPlan → SQL 稳定性；M23 再单独评估 RRF / rerank 等 retrieval 方法，每次只改变一个变量。
- 单独确认是否把 `result_match` oracle 从 SQLite deterministic seed 切到当前 configured database / MySQL。
- 单独确认是否增强 formal 多表题检查强度，或重写退款率 / 已支付订单题面。
- 如果 Milvus 要进入长期服务路径，再设计 upsert / delete-by-doc-id 和 collection cleanup。
- RAG / Hybrid 阶段再评估真实 embedding、rerank、chunk coverage 指标，不在 Text2SQL M20 中提前扩大范围。
