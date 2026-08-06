# M24 controlled diagnostic execution manifest

执行日期：2026-08-06  
主模型：Qwen `qwen3.7-plus`  
Fusion：`weighted`  
数据集：`database-upgrade-challenge.yaml` + `phase3a-diagnostic-benchmark.yaml`，共 32 条  
LangFuse：关闭；oracle：SQLite deterministic seed  
Schema docs：195 条，hash `ce04fe4fefc1cfb9226562f55154a1ed59eb91e9e41c3a83823c53ea491061b1`

## 运行矩阵

| run | generated_at | backend | total | automated | manual/diagnostic | report | trace | triage |
|---|---|---|---:|---:|---:|---|---|---|
| L1 | 19:47:02 | in-memory + deterministic | 24/32 | 21/27 | 3/5 | `m24-ab-l1b-local-weighted-diagnostic-report.md` | `m24-ab-l1b-local-weighted-diagnostic-traces.jsonl` | `m24-ab-l1b-local-weighted-diagnostic-triage.json` |
| M1 | 20:08:11 | Milvus + DashScope/Qwen embedding | 25/32 | 22/27 | 3/5 | `m24-ab-m1-milvus-qwenemb-weighted-diagnostic-report.md` | `m24-ab-m1-milvus-qwenemb-weighted-diagnostic-traces.jsonl` | `m24-ab-m1-milvus-qwenemb-weighted-diagnostic-triage.json` |
| L2 | 20:27:50 | in-memory + deterministic | 24/32 | 21/27 | 3/5 | `m24-ab-l2-local-weighted-diagnostic-report.md` | `m24-ab-l2-local-weighted-diagnostic-traces.jsonl` | `m24-ab-l2-local-weighted-diagnostic-triage.json` |
| M2 | 20:48:09 | Milvus + DashScope/Qwen embedding | 25/32 | 22/27 | 3/5 | `m24-ab-m2-milvus-qwenemb-weighted-diagnostic-report.md` | `m24-ab-m2-milvus-qwenemb-weighted-diagnostic-traces.jsonl` | `m24-ab-m2-milvus-qwenemb-weighted-diagnostic-triage.json` |
| L3 | 21:09:02 | in-memory + deterministic | 25/32 | 22/27 | 3/5 | `m24-ab-l3-local-weighted-diagnostic-report.md` | `m24-ab-l3-local-weighted-diagnostic-traces.jsonl` | `m24-ab-l3-local-weighted-diagnostic-triage.json` |
| M3 | 21:30:30 | Milvus + DashScope/Qwen embedding | 25/32 | 22/27 | 3/5 | `m24-ab-m3-milvus-qwenemb-weighted-diagnostic-report.md` | `m24-ab-m3-milvus-qwenemb-weighted-diagnostic-traces.jsonl` | `m24-ab-m3-milvus-qwenemb-weighted-diagnostic-triage.json` |

有效样本的自动能力分：Local 为 `21,21,22`，中位数 `21`，范围 `21–22`；Milvus 为 `22,22,22`，中位数 `22`，范围 `22–22`。总分只作描述，不单独作为 embedding 结论。

## Milvus 健康检查

- collection：`datapilot_schema_docs_m24_qwen_weighted_20260806_194900`
- 三次 M1/M2/M3 均报告 `milvus_final_row_count=195`。
- schema hash、1024 维和 Qwen embedding 配置一致；M2/M3 复用同一 clean collection，未发现重复灌入或 hash mismatch。

## 逐 case 通过矩阵

`P` = 该次自动/人工评分通过，`F` = 失败或 review。

| case | L1 | M1 | L2 | M2 | L3 | M3 | pass count |
|---|---|---|---|---|---|---|---:|
| db_core_001 | P | P | P | P | P | P | 6/6 |
| db_core_002 | F | F | F | F | F | F | 0/6 |
| db_core_003 | P | P | P | P | P | P | 6/6 |
| db_core_004 | P | P | P | P | P | P | 6/6 |
| db_hard_001 | F | F | F | F | F | F | 0/6 |
| db_hard_002 | P | P | P | P | P | P | 6/6 |
| db_hard_003 | F | F | F | F | F | F | 0/6 |
| db_join_001 | P | P | P | P | P | P | 6/6 |
| db_join_002 | P | P | P | P | P | P | 6/6 |
| db_join_003 | F | F | F | F | F | F | 0/6 |
| db_multi_001 | P | P | F | P | P | P | 5/6 |
| db_multi_002 | F | F | F | F | F | F | 0/6 |
| db_multi_003 | P | P | P | P | P | P | 6/6 |
| db_multi_004 | P | P | P | P | P | P | 6/6 |
| db_plan_001 | P | P | P | P | P | P | 6/6 |
| db_plan_002 | P | P | P | P | P | P | 6/6 |
| db_plan_003 | P | P | P | P | P | P | 6/6 |
| db_plan_004 | P | P | P | P | P | P | 6/6 |
| db_prompt_001 | P | P | P | P | P | P | 6/6 |
| db_prompt_002 | P | P | P | P | P | P | 6/6 |
| db_prompt_003 | P | P | P | P | P | P | 6/6 |
| db_schema_002 | P | P | P | P | P | P | 6/6 |
| db_schema_003 | P | P | P | P | P | P | 6/6 |
| db_sec_001 | P | P | P | P | P | P | 6/6 |
| db_sec_002 | P | P | P | P | P | P | 6/6 |
| db_sec_003 | P | P | P | P | P | P | 6/6 |
| db_sec_004 | P | P | P | P | P | P | 6/6 |
| db_simple_001 | F | F | F | F | F | F | 0/6 |
| db_simple_002 | F | F | F | F | F | F | 0/6 |
| db_simple_003 | F | F | F | F | F | F | 0/6 |
| db_trace_001 | P | P | P | P | P | P | 6/6 |
| db_trace_002 | F | P | P | P | P | P | 5/6 |

## 证据与失败定性

- 已证实的历史 SQL 合同误拦样本（`db_core_004`、`db_plan_001`、`db_prompt_002` 等）在六次运行中稳定通过，未观察到新的 `semantic_false_block`。
- M1 的 `db_core_002` 出现一次真实保真失败：计划绑定 `refund_rate` 的分母为 `COUNT(DISTINCT orders.id)`，候选 SQL 使用 `COUNT(DISTINCT order_items.id)`；trace 保存了完整 candidate SQL、QueryPlan、MySQL dialect、规范化表达式和 reason code。这属于 `generation_or_plan_error` / true expression fidelity failure，不是 AST 误拦。
- `db_simple_002`、`db_simple_003` 六次均为明确 `projection_mismatch`：候选结果分别输出 7 列、10 列，而 case 精确要求 3 列。它们证明“精确投影”政策确实捕获了额外列。
- `db_simple_001` 六次均为结果首行不匹配，属于真实排序/结果保真问题，不能由 embedding 单独解释。
- `db_core_002`、`db_multi_002`、`db_join_003`、`db_hard_001` 等稳定失败，主要是生成/计划或人工语义题，不是新增的合同误拦证据。
- 六次共有 135 个可执行 SQL trace 的 `output_contract` 成功 span；额外列失败主要发生在 scorer 对 case `expected_columns` 的结果合同，而不是 pipeline 把计划声明的列与实际 `body.columns` 比较时失败。这说明模型生成的 QueryPlan 本身可能已经声明了过宽投影，后续仍需单独收紧计划输出策略。
- `db_trace_002` 只有 L1 失败（缺少 `coupon_order_count`），其余五次通过；该失败是结果/输出字段合同，不是历史 SQL alias 误拦。

## 结论边界

本次三次交错 A/B 显示 Milvus 自动能力原始值稳定为 `22/27`，Local 为 `21,21,22/27`；这是当前固定 Qwen、weighted 和 195-doc corpus 下的观察，不足以单独证明 embedding 因果收益。需要结合逐 case 与失败结构解读：稳定失败集中在生成/计划、结果语义和投影合同；M24 AST 合同未出现可确认的 semantic false block。
