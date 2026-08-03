# DataPilot Eval Baselines

> 本文是 DataPilot 长期评测账本：记录 formal / challenge / diagnostic 基线、模型/检索 A/B、失败结构和典型错因。Trigger：只要涉及 eval 数字、模型 A/B、failure_stage、benchmark、pass rate、case 口径或失败归因，必须先读本文。AI 续接时先读 `docs/state/AI_CONTEXT.md`。

更新时间：2026-08-02

## 当前摘要

- 当前默认主模型：DeepSeek `deepseek-v4-flash`，配置入口为 `LLM_PROVIDER=deepseek` + `LLM_MODEL=deepseek-v4-flash`。
- 当前显式候选模型：Qwen `qwen3.7-max`，配置入口为 `LLM_PROVIDER=qwen` + `QWEN_MODEL=qwen3.7-max`。
- 最新默认模型快照：M19 DeepSeek flash formal `7/10`、challenge `9/16`、diagnostic `19/32`。
- 最新候选模型对照：M19 qwen3.7-max formal `8/10`、challenge `12/16`、diagnostic `22/32`。
- 当前优先改进方向：先看 `schema_context / schema_retrieval`，再看 `result_match / plan_validation / query_plan / sql_generation`。换模型能缓解部分生成失败，但不能替代 schema 上下文修复。
- 当前结论：Qwen 3.7 max 可作为后续 A/B 组；默认模型、默认 embedding、正式 eval case 集都属于长期基线选择，不在普通实验中自动切换或改写。
- M20 结论：clean Milvus 链路上 Qwen `qwen3.7-max` diagnostic `21/32`（首次完整 clean Qwen 链路，高于同链路 DeepSeek `17/32`）；`schema_context` 7 仍是主问题；默认 embedding / Milvus / 模型不切换。

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

- Diagnostic report：`.agent_work/temp/m20-deepseek-qwenemb-diagnostic-report.md`
- Diagnostic triage：`.agent_work/temp/m20-deepseek-qwenemb-diagnostic-triage.json`
- M19 polluted vs M20 clean compare：`.agent_work/temp/m20-m19-polluted-vs-clean-deepseek-qwenemb-compare.md`
- Milvus index smoke：`.agent_work/temp/m20-milvus-index-smoke.md`

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

- Diagnostic report：`.agent_work/temp/m20-qwen37max-qwenemb-diagnostic-report.md`
- Diagnostic triage：`.agent_work/temp/m20-qwen37max-qwenemb-diagnostic-triage.json`
- Clean DeepSeek vs Qwen compare：`.agent_work/temp/m20-clean-deepseek-vs-qwen37max-compare.md`
- M19 polluted vs M20 clean Qwen compare：`.agent_work/temp/m20-polluted-vs-clean-qwen37max-compare.md`

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

## M19 DeepSeek Flash

配置：

- `LLM_PROVIDER=deepseek`
- `LLM_MODEL=deepseek-v4-flash`
- `LANGFUSE_ENABLED=false` 用于三类本地 eval；另有 LangFuse enabled smoke 验证 Cloud score 回写。

报告路径：

- Formal：`.agent_work/temp/m19-formal-report.md`
- Challenge：`.agent_work/temp/m19-challenge-report.md`
- Diagnostic：`.agent_work/temp/m19-diagnostic-report.md`
- Diagnostic triage：`.agent_work/temp/m19-diagnostic-triage.json`

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

- Formal：`.agent_work/temp/m19-qwen37max-formal-report.md`
- Challenge：`.agent_work/temp/m19-qwen37max-challenge-report.md`
- Diagnostic：`.agent_work/temp/m19-qwen37max-diagnostic-report.md`
- Diagnostic triage：`.agent_work/temp/m19-qwen37max-diagnostic-triage.json`
- DeepSeek vs Qwen diagnostic 对比：`.agent_work/temp/m19-deepseek-vs-qwen37max-diagnostic-triage-compare.md`

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
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\phase3a-regression.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-formal-traces.jsonl --report .agent_work\temp\<name>-formal-report.md --triage-json .agent_work\temp\<name>-formal-triage.json

# challenge
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-challenge-traces.jsonl --report .agent_work\temp\<name>-challenge-report.md --triage-json .agent_work\temp\<name>-challenge-triage.json

# diagnostic
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-diagnostic-traces.jsonl --report .agent_work\temp\<name>-diagnostic-report.md --triage-json .agent_work\temp\<name>-diagnostic-triage.json

# failure distribution compare
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --compare-triage-left <left>.json --compare-triage-right <right>.json --compare-triage-report .agent_work\temp\<name>-compare.md
```
