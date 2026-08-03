# DataPilot Eval Baselines

> 本文是 DataPilot 长期评测账本：记录 formal / challenge / diagnostic 基线、模型/检索 A/B、失败结构和典型错因。Trigger：只要涉及 eval 数字、模型 A/B、failure_stage、benchmark、pass rate、case 口径或失败归因，必须先读本文。AI 续接时先读 `docs/state/AI_CONTEXT.md`。

更新时间：2026-08-03

## 当前摘要

- 当前默认主模型：DeepSeek `deepseek-v4-flash`，配置入口为 `LLM_PROVIDER=deepseek` + `LLM_MODEL=deepseek-v4-flash`。
- 当前显式候选模型：Qwen `qwen3.7-plus` / `qwen3.7-max`，配置入口为 `LLM_PROVIDER=qwen` + `QWEN_MODEL=...`；M21 当前受控 A/B 使用 `qwen3.7-plus`。
- 最新默认模型快照：M19 DeepSeek flash formal `7/10`、challenge `9/16`、diagnostic `19/32`。
- 最新候选模型对照：M19 qwen3.7-max formal `8/10`、challenge `12/16`、diagnostic `22/32`。
- 当前优先改进方向：M22 先看 output table/column contract 和 `QueryPlan → SQL` 的漏表、alias、生成稳定性；retrieval / rerank 留到后续单变量实验。换模型或 embedding 不能替代这些结构性修复。
- 当前结论：Qwen 3.7 max 可作为后续 A/B 组；默认模型、默认 embedding、正式 eval case 集都属于长期基线选择，不在普通实验中自动切换或改写。
- M20 结论：clean Milvus 链路上 Qwen `qwen3.7-max` diagnostic `21/32`（首次完整 clean Qwen 链路，高于同链路 DeepSeek `17/32`）；`schema_context` 7 仍是主问题；默认 embedding / Milvus / 模型不切换。
- M21 结论：Qwen embedding 的 vector-only recall 从 deterministic `0.787` 提升到 `0.929`，但 weighted merged recall 仍为 `0.738`；RRF merged recall 为 `0.929`。同模型 Qwen-plus 端到端 weighted `21/32`、RRF `20/32`，因此 RRF 仍是显式候选，不切默认 fusion。
- M21 controlled embedding A/B：固定 Qwen-plus + weighted 后，本地 deterministic 与 Milvus + Qwen embedding 都为 `21/32`；`schema_context` 和 `failure_subtype` 分布完全相同，当前没有端到端 embedding 提分证据。
- M21 诊断修正：`failure_stage=schema_context` 过粗，新增 `failure_subtype` 区分 `output_table_contract`、`output_column_contract`、`result_contract` 和 `scorer_contract`；旧 `failure_stage` 保持兼容。

## 如何读这些数字

- `formal`：主线回归对照，样本少但最贴近“应该稳定过”的基础能力。
- `challenge`：数据库升级后的困难题，适合观察复杂 join、指标、口径和安全边界。
- `diagnostic`：定位边界和失败结构，不追满分；更适合回答“下一步修哪一层”。
- 三类测试虽然题集有包含关系，但如果分三次真实 LLM run 执行，结果会受非确定性影响。严格比较包含关系时，应跑一次 superset，再从同一份结果切子集统计。
- M19 `triage summary failed` 可能比命令行 `passed` 推算的失败数多，因为 `review_required / manual_review` 会进入待处理清单；它不是算错，而是保留人工复核样本。
- 不只看总分。优先看 `failure_stage` 和 `needs_action`：例如 `schema_context` 降了但 `result_match` 升了，说明改动可能让字段更多但 SQL 口径更乱，不能简单算作纯提升。

## 相关文档分工

- `docs/state/AI_CONTEXT.md`：AI 续接入口，保留当前状态、默认链路、操作入口和最新摘要。
- `docs/state/runbook.md`：运行入口，保留模型、embedding、LangFuse、eval 命令矩阵和运行纪律。
- `docs/state/eval-baselines.md`：长期评测账本，保留基线、A/B、失败结构、报告路径和典型错因。
- `docs/state/database-current-state.md`：数据库事实、14 表清单、固定 seed 和指标口径；排查 `result_match`、漏表漏列、指标口径类 eval 失败时必须对照。
- `docs/state/schema-retrieval-milvus-embedding.md`：Schema Retrieval / Milvus / embedding 速查，保留默认值、collection 纪律、`schema_docs_hash`、报告字段和排查菜单。
- `docs/eval-observability-guide.md`：面向用户的 Eval / Trace / LangFuse 说明文档；AI 只有在需要理解 eval 功能设计、写说明或讲解报告时再读，不作为日常续接必读。

## 基线索引

| 日期 | 模块/来源 | 链路 | formal | challenge | diagnostic | 结论 |
|---|---|---|---:|---:|---:|---|
| 2026-07-26 | M13 | DeepSeek + 本地 retrieval 稳定快照 | 10/10 | 14/16 | 23/32 | Phase 3A 上一轮稳定基线。 |
| 2026-07-27 | M14-lite | DeepSeek + 本地 retrieval 临时快照 | 8/10 最新补测 | 12/16 | 24/32 | result_match / 安全 / trace 口径更严格，不能直接当退化结论。 |
| 2026-07-27 | M14-lite A/B | Qwen `qwen3.7-plus` | 9/10 | 13/16 | 21/32 | 可作为候选，但 diagnostic 低于 DeepSeek。 |
| 2026-07-27 | M14-lite A/B | Qwen `qwen3.7-max` | 未补跑 | 未补跑 | 22/32 | 略高于 plus；仍不切默认。 |
| 2026-08-02 | M19 | DeepSeek `deepseek-v4-flash` | 7/10 | 9/16 | 19/32 | M19 triage 验证快照，低于 M13；真实 LLM 有波动。 |
| 2026-08-02 | M19 follow-up | Qwen `qwen3.7-max` | 8/10 | 12/16 | 22/32 | 本轮优于 DeepSeek flash，但 schema 上下文仍是主问题；不自动切默认。 |
| 2026-08-02 | M20 clean Milvus | DeepSeek + Milvus + Qwen embedding | 未跑 | 未跑 | 17/32 | clean collection `row_count=193`，低于 M19 污染链路 19/32；不切默认 embedding。 |
| 2026-08-02 | M20 clean Milvus | Qwen `qwen3.7-max` + Milvus + Qwen embedding | 未跑 | 未跑 | 21/32 | 首次完整 clean Qwen 链路，同链路高于 DeepSeek 17/32；schema_context 7 仍是主问题；不切默认。 |
| 2026-08-03 | M21 retrieval-only | inmemory + deterministic | — | — | — | vector-only `0.787`、weighted merged `0.738`、RRF merged `0.802`；10 题离线基准。 |
| 2026-08-03 | M21 retrieval-only | clean Milvus + Qwen embedding | — | — | — | vector-only `0.929`、weighted merged `0.738`、RRF merged `0.929`；向量信号存在，但 weighted merge 未兑现。 |
| 2026-08-03 | M21 diagnostic A/B | Qwen `qwen3.7-plus` + clean Milvus/Qwen embedding | — | — | 21/32 weighted；20/32 RRF | 同模型同 32 题；RRF 未带来端到端提升。 |
| 2026-08-03 | M21 controlled embedding A/B | Qwen `qwen3.7-plus`：inmemory/deterministic vs clean Milvus/Qwen embedding | weighted | 21/32 vs 21/32 | 同一 32 题、同一 oracle 和 schema hash；failure_subtype 完全相同，不支持 embedding 端到端提分结论。 |
| 2026-08-03 | M21 supplementary A/B | DeepSeek + clean Milvus/Qwen embedding | — | — | 21/32 weighted → 18/32 RRF | fusion 负向证据；不替换 M20 clean `17/32` 事实锚点。 |

## M20 Clean Milvus / Qwen Embedding

配置：

- `LLM_PROVIDER=deepseek`
- `LLM_MODEL=deepseek-v4-flash`
- `SCHEMA_VECTOR_BACKEND=milvus`
- `SCHEMA_EMBEDDING_PROVIDER=dashscope`
- `QWEN_EMBEDDING_MODEL=qwen3.7-text-embedding`
- `QWEN_EMBEDDING_DIMENSIONS=1024`
- `MILVUS_COLLECTION=datapilot_schema_docs_m20_deepseek_qwenemb_20260802_a`
- `LANGFUSE_ENABLED=false`

报告路径：

- Diagnostic report：`eval/reports/m20-deepseek-qwenemb-diagnostic-report.md`
- Diagnostic triage：`eval/reports/m20-deepseek-qwenemb-diagnostic-triage.json`
- M19 polluted vs M20 clean compare：`eval/reports/m20-m19-polluted-vs-clean-deepseek-qwenemb-compare.md`
- Milvus index smoke：`eval/reports/m20-milvus-index-smoke.md`

索引卫生：

- `schema_docs_count=193`
- `schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`
- Clean smoke collection `datapilot_schema_docs_m20_20260802_203949_007d1e09`：`final_row_count=193`
- Diagnostic collection `datapilot_schema_docs_m20_deepseek_qwenemb_20260802_a`：`milvus_final_row_count=193`，`schema_vector_index_reuse=run_scoped`
- Report 明确 `result_match_oracle_backend=sqlite_deterministic_seed`

结果：

| 集合 | 命令行通过率 | failure_stage 分布 | needs_action 聚合 |
|---|---:|---|---|
| diagnostic | 17/32 | `schema_context=5`、`query_plan=5`、`plan_validation=2`、`result_match=1`、`sql_guard=1`、`schema_retrieval=1` | `fix_schema_desc=5`、`fix_pipeline=7`、`manual_review=3` |

M19 polluted DeepSeek + Qwen embedding vs M20 clean DeepSeek + Qwen embedding diagnostic failure distribution：

| failure_stage | M19 polluted | M20 clean | clean - polluted |
|---|---:|---:|---:|
| plan_validation | 1 | 2 | +1 |
| query_plan | 4 | 5 | +1 |
| result_match | 2 | 1 | -1 |
| schema_context | 4 | 5 | +1 |
| schema_retrieval | 1 | 1 | 0 |
| sql_guard | 1 | 1 | 0 |
| unknown | 2 | 0 | -2 |

结论：

- M20 解决的是索引可信度，不是追求 diagnostic 提分。clean collection 后 diagnostic 为 `17/32`，没有显示 Qwen embedding 稳定收益。
- M19 的污染链路结果不能再作为 embedding 模型优劣结论；M20 clean run 也不足以直接判定 Qwen embedding “无效”，因为真实 LLM 有波动且 schema doc 粒度未调整。
- Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic 已完整跑通：`21/32`（见下方 `M20 Clean Milvus + Qwen 3.7 Max` 子节），这是首次完整的 clean Qwen 链路数据点。
- 默认仍保持 `inmemory + deterministic`；Milvus / DashScope embedding 继续作为显式实验路径。

### M20 Clean Milvus + Qwen 3.7 Max

配置：

- `LLM_PROVIDER=qwen`
- `QWEN_MODEL=qwen3.7-max`
- `SCHEMA_VECTOR_BACKEND=milvus`
- `SCHEMA_EMBEDDING_PROVIDER=dashscope`
- `QWEN_EMBEDDING_MODEL=qwen3.7-text-embedding`
- `QWEN_EMBEDDING_DIMENSIONS=1024`
- `MILVUS_COLLECTION=datapilot_schema_docs_m20_qwen37max_qwenemb_20260802_214810`（日期+时间戳命名）
- `LANGFUSE_ENABLED=false`

报告路径：

- Diagnostic report：`eval/reports/m20-qwen37max-qwenemb-diagnostic-report.md`
- Diagnostic triage：`eval/reports/m20-qwen37max-qwenemb-diagnostic-triage.json`
- Clean DeepSeek vs Qwen compare：`eval/reports/m20-clean-deepseek-vs-qwen37max-compare.md`
- M19 polluted vs M20 clean Qwen compare：`eval/reports/m20-polluted-vs-clean-qwen37max-compare.md`

索引卫生：

- `schema_docs_count=193`、`milvus_final_row_count=193`、`schema_vector_index_reuse=run_scoped`、`milvus_dimension=1024`
- `schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`
- `result_match_oracle_backend=sqlite_deterministic_seed`

结果：

| 集合 | 命令行通过率 | failure_stage 分布 | needs_action 聚合 |
|---|---:|---|---|
| diagnostic | 21/32 | `schema_context=7`、`sql_generation=2`、`result_match=1`、`schema_retrieval=1`、`unknown=2` | `fix_schema_desc=7`、`fix_pipeline=3`、`manual_review=3` |

Clean 链路 DeepSeek vs Qwen（同一 Milvus + Qwen embedding 链路）：

| failure_stage | DeepSeek 17/32 | Qwen 21/32 | Qwen - DeepSeek |
|---|---:|---:|---:|
| plan_validation | 2 | 0 | -2 |
| query_plan | 5 | 0 | -5 |
| result_match | 1 | 1 | 0 |
| schema_context | 5 | 7 | +2 |
| schema_retrieval | 1 | 1 | 0 |
| sql_generation | 0 | 2 | +2 |
| sql_guard | 1 | 0 | -1 |
| unknown | 0 | 2 | +2 |

M19 污染 vs M20 clean（同一 Qwen 模型）：

| failure_stage | M19 polluted 20/32 | M20 clean 21/32 | clean - polluted |
|---|---:|---:|---:|
| plan_validation | 1 | 0 | -1 |
| query_plan | 1 | 0 | -1 |
| result_match | 1 | 1 | 0 |
| schema_context | 7 | 7 | 0 |
| schema_retrieval | 1 | 1 | 0 |
| sql_generation | 1 | 2 | +1 |
| unknown | 1 | 2 | +1 |

结论：

- 首次完整 clean Qwen 链路数据点；Qwen `qwen3.7-max` 在同链路上 `21/32` 高于 DeepSeek `17/32`，提升主要来自 query_plan / plan_validation 类失败消失。
- `schema_context` 从 5 升到 7 仍是最大失败簇，说明换模型不能替代 schema 上下文修复；优化优先级不变。
- 单次真实 LLM run 有非确定性；不据此切换默认模型 / embedding / Milvus，默认仍为 `inmemory + deterministic`。

## M21 Schema Retrieval Fusion / Context Repair

### 固定实验元数据

- Schema collection：`datapilot_schema_docs_m21_qwen_weighted_20260803_001`
- `schema_docs_count=193`
- `schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`
- Qwen embedding：`qwen3.7-text-embedding`，维度 `1024`
- retrieval-only `top_k=12`
- 端到端报告：`result_match_oracle_backend=sqlite_deterministic_seed`，`LANGFUSE_ENABLED=false`

### Retrieval-only benchmark

| backend | embedding | vector-only recall | weighted merged recall | RRF merged recall |
|---|---|---:|---:|---:|
| inmemory | deterministic | `0.787` | `0.738` | `0.802` |
| clean Milvus | Qwen `qwen3.7-text-embedding` | `0.929` | `0.738` | `0.929` |

解读：Qwen embedding 的向量召回有明确提升（`0.787 → 0.929`），但 weighted merge 后整体仍为 `0.738`；RRF 能在离线 benchmark 中保住向量信号，但离线 recall 不能直接等同端到端 Text2SQL 提升。

fusion A/B 报告：

- deterministic weighted：`eval/reports/m21-baseline-deterministic-weighted.md`
- deterministic RRF：`eval/reports/m21-candidate-deterministic-rrf.md`
- Milvus + Qwen embedding weighted：`eval/reports/m21-baseline-qwen-milvus-weighted.md`
- Milvus + Qwen embedding RRF：`eval/reports/m21-candidate-qwen-milvus-rrf.md`

### 同模型端到端 fusion A/B

| 模型 | fusion | diagnostic | failure_stage 摘要 |
|---|---|---:|---|
| Qwen `qwen3.7-plus` | weighted | `21/32` | `schema_context=6`、`schema_retrieval=2`、`query_plan=1`、`result_match=1`、`sql_generation=1`、`unknown=2` |
| Qwen `qwen3.7-plus` | RRF | `20/32` | `schema_context=5`、`schema_retrieval=2`、`query_plan=2`、`result_match=2`、`sql_generation=1`、`unknown=1` |

weighted → RRF 的同模型 triage 变化为：`schema_context 6→5`、`query_plan 1→2`、`result_match 1→2`、`unknown 2→1`、`schema_retrieval 2→2`、`sql_generation 1→1`。总体没有显示 RRF 带来稳定端到端收益，因此默认 fusion 仍保持 weighted。

### Qwen-plus 本地 vs Qwen embedding 对照

固定主模型 `qwen3.7-plus`、`weighted` fusion、`new_text2sql`、同一 diagnostic 32 题、同一 SQLite deterministic oracle、`LANGFUSE_ENABLED=false`，只改变 Schema Retrieval 链路：

| 组别 | Schema Retrieval | 通过率 | failure_stage | failure_subtype |
|---|---|---:|---|---|
| A | `inmemory + deterministic` | `21/32` | `schema_context=6`、`schema_retrieval=2`、`sql_generation=2`、`result_match=1`、`unknown=2` | `output_column_contract=6`、`output_table_contract=2`、`result_contract=1` |
| B | clean Milvus + Qwen `qwen3.7-text-embedding`（1024 维） | `21/32` | `schema_context=6`、`schema_retrieval=2`、`query_plan=1`、`result_match=1`、`sql_generation=1`、`unknown=1` | `output_column_contract=6`、`output_table_contract=2`、`result_contract=1` |

逐 case 只有 3 个失败形态变化：`db_hard_001` 从 `schema_retrieval` 变为 `query_plan`、`db_join_003` 从 `unknown` 变为 `schema_retrieval`、`db_plan_004` 从失败变为通过。两组总分、`schema_context` 数量和全部 `failure_subtype` 数量相同；因此在这一次严格控制的端到端 A/B 中，没有观察到 Qwen embedding 带来可归因的提分，也没有发现新的明确 retrieval 修复证据。

报告：

- 本地组：`eval/reports/m21-qwen-plus-local-weighted-report.md`、`eval/reports/m21-qwen-plus-local-weighted-triage.json`
- Qwen embedding 组：`eval/reports/m21-qwen-plus-qwenemb-weighted-report.md`、`eval/reports/m21-qwen-plus-qwenemb-weighted-triage.json`
- triage 对比：`eval/reports/m21-qwen-plus-local-vs-qwenemb-triage-compare.md`

fusion A/B 报告：

- weighted report：`eval/reports/m21-qwen-plus-weighted-diagnostic-report.md`
- weighted triage：`eval/reports/m21-qwen-plus-weighted-diagnostic-triage.json`
- RRF report：`eval/reports/m21-qwen-plus-rrf-diagnostic-report.md`
- RRF triage：`eval/reports/m21-qwen-plus-rrf-diagnostic-triage.json`
- A/B compare：`eval/reports/m21-qwen-plus-weighted-vs-rrf-compare.md`

### DeepSeek supplementary fusion A/B

- DeepSeek weighted `21/32` → RRF `18/32`；该轮用于说明 RRF 的端到端负向风险，不替换 M20 clean 链路事实锚点（DeepSeek `17/32`）。
- RRF 相比 weighted 新增 `plan_validation` 失败，不能只看 retrieval-only recall 决定 fusion。
- 报告：`eval/reports/m21-deepseek-weighted-diagnostic-report.md`、`eval/reports/m21-deepseek-rrf-diagnostic-report.md`。

### M21 失败归因修正

旧版 `failure_stage=schema_context` 会混入最终生成结果缺列、alias 或 scorer 契约问题。当前代码新增 `failure_subtype`：

| failure_subtype | 含义 |
|---|---|
| `output_table_contract` | 最终 `tables_used` 未满足 expected table contract |
| `output_column_contract` | 最终 `columns` 未满足 expected column contract |
| `result_contract` | SQL 可执行，但结果列、alias、排序、口径或数值不满足 expected |
| `scorer_contract` | 评分器规则或证据需要人工复核 |

只有 SchemaGraph / retrieval trace 明确缺少目标表或字段时，才把问题归入 `schema_retrieval`；`rule:table_hit` 和 `rule:column_recall` 单独不能证明 embedding 或 fusion 失败。旧 `failure_stage` 保留，避免破坏历史报告。

相关审查素材：`eval/reports/m21-context-audit.md`；triage focused tests：`7 passed`。

### M21 当前结论

- embedding 链路不是完全失效，vector-only 已证明有信号。
- weighted merge 是当前离线瓶颈，RRF 是合理候选，但目前端到端未提升，不切默认。
- 尚未发现一个证据完整的“正确召回后被 Context Assembly 丢表/丢字段”案例；不能把所有 `schema_context` 失败继续归因给 embedding。
- 固定参数的 Qwen-plus 本地 vs Qwen embedding 对照已完成：两组均为 `21/32`，没有 subtype 收益；M21 embedding 线收口，M22 转向 output contract 与 QueryPlan → SQL，M23 再尝试 rerank 等 retrieval 方法。

## M19 DeepSeek Flash

配置：

- `LLM_PROVIDER=deepseek`
- `LLM_MODEL=deepseek-v4-flash`
- `LANGFUSE_ENABLED=false` 用于三类本地 eval；另有 LangFuse enabled smoke 验证 Cloud score 回写。

报告路径：

- Formal：`eval/reports/m19-formal-report.md`
- Challenge：`eval/reports/m19-challenge-report.md`
- Diagnostic：`eval/reports/m19-diagnostic-report.md`
- Diagnostic triage：`eval/reports/m19-diagnostic-triage.json`

结果：

| 集合 | 通过率 | failure_stage 分布 | needs_action 聚合 |
|---|---:|---|---|
| formal | 7/10 | `schema_context=1`、`plan_validation=1`、`query_plan=1` | 以 `fix_schema_desc / fix_pipeline` 为主 |
| challenge | 9/16 | `schema_context=1`、`result_match=3`、`query_plan=3`、`unknown=1` | 以 `fix_pipeline` 为主 |
| diagnostic | 19/32 | `schema_context=6`、`schema_retrieval=1`、`result_match=2`、`plan_validation=1`、`sql_guard=1`、`unknown=2`、`query_plan=1`、`sql_generation=1` | `fix_schema_desc=7`、`fix_pipeline=5`、`manual_review=3` |

典型错因：

- `schema_context`：表可能召回了，但局部上下文缺字段，常见表现是 `missing_columns`。
- `schema_retrieval`：需要的表没有进入上下文，后续生成再努力也难补回来。
- `result_match`：SQL 能执行，但列名 alias、排序、口径或数值和 expected SQL 不一致。
- `query_plan / sql_generation`：模型输出不可解析、计划偏题或 SQL 生成失败。
- `sql_guard`：安全拦截相关，必须人工确认是真风险还是误拦，不能贸然放宽。

结论：

- 这轮主要证明 M19 triage 闭环可工作，不直接作为“DeepSeek flash 稳定能力下降”的唯一证据。
- 下一步优化优先级应是 schema 上下文质量，其次才是生成 prompt / plan validation / result_match 口径。

## M19 Qwen 3.7 Max

配置：

- `LLM_PROVIDER=qwen`
- `QWEN_MODEL=qwen3.7-max`
- `LANGFUSE_ENABLED=false`
- 未修改 `.env` 默认值；本轮是显式 shell 环境变量实验。

报告路径：

- Formal：`eval/reports/m19-qwen37max-formal-report.md`
- Challenge：`eval/reports/m19-qwen37max-challenge-report.md`
- Diagnostic：`eval/reports/m19-qwen37max-diagnostic-report.md`
- Diagnostic triage：`eval/reports/m19-qwen37max-diagnostic-triage.json`
- DeepSeek vs Qwen diagnostic 对比：`eval/reports/m19-deepseek-vs-qwen37max-diagnostic-triage-compare.md`

结果：

| 集合 | 命令行通过率 | triage 摘要 | 说明 |
|---|---:|---|---|
| formal | 8/10 | `schema_context=2`；`fix_schema_desc=2` | 失败为 `p3a_multi_001` 缺 `coupon_order_count`、`p3a_multi_003` 缺 `category`。 |
| challenge | 12/16 | `result_match=1`、`schema_context=1`、`query_plan=1`、`schema_retrieval=1`、`unknown=1` | triage summary `failed=5`，多出的 1 条是 `review_required` manual case。 |
| diagnostic | 22/32 | `schema_context=6`、`schema_retrieval=2`、`result_match=1`、`plan_validation=1`、`unknown=1` | triage summary `failed=11`，含 1 条 manual/review case。 |

DeepSeek flash vs qwen3.7-max diagnostic failure distribution：

| failure_stage | DeepSeek flash | qwen3.7-max | Qwen - DeepSeek |
|---|---:|---:|---:|
| plan_validation | 1 | 1 | 0 |
| query_plan | 1 | 0 | -1 |
| result_match | 2 | 1 | -1 |
| schema_context | 6 | 6 | 0 |
| schema_retrieval | 1 | 2 | +1 |
| sql_generation | 1 | 0 | -1 |
| sql_guard | 1 | 0 | -1 |
| unknown | 2 | 1 | -1 |

典型错因：

- Qwen 3.7 max 本轮少了 DeepSeek flash 的 `query_plan / sql_generation / sql_guard` 类失败，说明生成稳定性在这批题上更好。
- `schema_context=6` 没降，说明模型替换没有解决字段上下文不足问题。
- `schema_retrieval=2` 高于 DeepSeek flash 的 1，说明表召回/上下文入口仍需单独修，不应把所有错误归因给模型。

结论：

- qwen3.7-max 是强候选，适合作为后续 A/B 模型。
- 不在 M19 中切默认模型；默认模型切换必须单独决策，评估成本、稳定性、长期基线和后续 RAG / Hybrid 影响。

## M19 重复 Case 波动

M19 formal / challenge / diagnostic 是三次独立真实 LLM eval，不是同一次 superset run 的切片。challenge 与 diagnostic 中相同 `case_id` 有 6 个结果或失败形态不同：

| case_id | challenge | diagnostic | 说明 |
|---|---|---|---|
| `db_core_001` | fail：`result_match` 列名 `gmv` vs `total_gmv` | pass：`result_match_ok` | 同题重跑后 SQL alias / 输出列口径变了。 |
| `db_core_002` | fail：`llm_generation_error` | fail：`missing_tables=['products']` | 都失败，但失败阶段从生成类变成 schema retrieval。 |
| `db_core_004` | fail：渠道排序/行值不一致 | fail：仍是 result mismatch，但错在另一行 | 都失败，但输出顺序或 SQL 结果波动。 |
| `db_hard_001` | fail：`llm_generation_error` | fail：`sql_guard_blocked` | 困难题失败形态变了，不能只看总分。 |
| `db_multi_002` | fail：`llm_generation_error` | pass | 典型 LLM 重跑波动。 |
| `db_multi_004` | pass | fail：`plan_validation_failed` | 典型 LLM 重跑波动。 |

结论：读包含关系时不能把三次独立运行当作同一批结果；若要严格比较，应跑一次 superset，再按 case 集切子集统计。

## M14-lite 模型与 Embedding A/B

主模型：

- DeepSeek formal `9/10`，challenge `12/16`，diagnostic `24/32`。
- Qwen `qwen3.7-plus` formal `9/10`，challenge `13/16`，diagnostic `21/32`。
- Qwen `qwen3.7-max` diagnostic `22/32`。
- 结论：Qwen 不再用旧 `qwen-plus` 代表整体能力；`qwen3.7-plus/max` 都可作为候选，但默认仍保留 DeepSeek。

Embedding：

- 本地 `inmemory + deterministic` formal 最新补测 `8/10`。
- `Milvus + SiliconFlow BAAI/bge-m3` formal `8/10`。
- `Milvus + qwen3.7-text-embedding` formal `9/10`。
- 结论：Qwen embedding formal 略好，但只差 1 题且受真实 LLM 波动影响；后续 RAG / Hybrid 再测 challenge / diagnostic，不在 Phase 3A 自动切默认。

## 常用命令骨架

```powershell
# formal
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\phase3a-regression.yaml --pipeline-mode new_text2sql --trace eval/reports/<name>-formal-traces.jsonl --report eval/reports/<name>-formal-report.md --triage-json eval/reports/<name>-formal-triage.json

# challenge
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --pipeline-mode new_text2sql --trace eval/reports/<name>-challenge-traces.jsonl --report eval/reports/<name>-challenge-report.md --triage-json eval/reports/<name>-challenge-triage.json

# diagnostic
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --pipeline-mode new_text2sql --trace eval/reports/<name>-diagnostic-traces.jsonl --report eval/reports/<name>-diagnostic-report.md --triage-json eval/reports/<name>-diagnostic-triage.json

# failure distribution compare
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --compare-triage-left <left>.json --compare-triage-right <right>.json --compare-triage-report eval/reports/<name>-compare.md
```
