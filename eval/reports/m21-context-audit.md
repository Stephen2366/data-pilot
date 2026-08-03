# M21 Context Repair 地基体检（2026-08-03）

## 体检范围

- 固定同一主模型：`qwen3.7-plus`。
- 固定同一 clean Milvus collection：`datapilot_schema_docs_m21_qwen_weighted_20260803_001`。
- 固定 Qwen embedding 1024 维、schema docs hash、32 条 diagnostic、`top_k` 和 context 配置。
- 对齐产物：
  - `.agent_work/temp/m21-qwen-plus-weighted-traces.jsonl`
  - `.agent_work/temp/m21-qwen-plus-rrf-traces.jsonl`
  - `.agent_work/temp/m21-qwen-plus-weighted-diagnostic-triage.json`
  - `.agent_work/temp/m21-qwen-plus-rrf-diagnostic-triage.json`
  - `.agent_work/temp/m21-qwen-plus-weighted-vs-rrf-compare.md`

## 基线结果

| 配置 | 通过 | failure stage 摘要 |
|---|---:|---|
| plus + weighted | `21/32` | `schema_context=6`、`schema_retrieval=2`、`result_match=1`、`query_plan=1`、`unknown=2`、`sql_generation=1` |
| plus + RRF | `20/32` | `schema_context=5`、`schema_retrieval=2`、`result_match=2`、`query_plan=2`、`unknown=1`、`sql_generation=1` |

## 关键发现

### 1. `schema_context` 目前是“schema 相关失败桶”，不是上下文丢失的直接证据

- `eval/triage.py:396-401` 把所有 `rule:column_recall` 直接映射为 `schema_context`。
- `eval/scorers/rule_scorers.py:164-200` 的 `column_recall` 实际比较的是最终响应 `body.columns`，也就是模型生成 SQL 的输出列 / alias，不是 `SchemaGraph.fields` 是否包含字段。
- `engine/nl2sql/pipeline.py:162-170` 的 trace 只记录 context 的表名、字段总数和指标名，没有记录完整字段集合。
- 因此当前 triage 的 `schema_context=6` 只能说明“输出列或 schema 相关检查失败”，不能直接推出“embedding 没召回”或“context assembly 丢字段”。

### 2. 已对齐的失败 case 中，多个 case 的 context 实际包含目标表，问题发生在 SQL 输出或评测契约

- `db_core_002`：weighted / RRF 的 `schema_context` 都包含 `products`，但生成 SQL 的实际表只有 `order_items, orders, refunds`；这是 SQL 生成遗漏表，不是 retrieval 未召回。
- `db_multi_001`：两种策略都包含 `channels, coupons, order_coupons, orders`，实际输出列为 `channel_name, used_order_count`，而 case 期望 `coupon_order_count`，只配置了 `usage_count` alias；更像 SQL alias / scorer 契约问题。
- `db_prompt_001` / `db_prompt_002` / `db_prompt_003`：两种策略都得到预期的核心表和较大的 SchemaGraph，但 `column_recall` 仍按最终 SQL 输出列报缺失；这不能直接作为 embedding 或 context assembly 失败证据。
- `db_plan_003`：RRF 的 context 包含 `knowledge_docs`、`orders`，但 `doc_title` / `order_amount` 缺失来自输出列检查；weighted 则在更早的 SQL generation 阶段失败。
- `engine/schema_retrieval/graph.py:145-150` 会把每个已选表的完整 domain-schema fields 放进 `SchemaGraph`；因此只要目标物理表已进入 context，当前实现并没有证据表明物理字段在 graph 构建时被截断。缺失的很多是最终 SQL 输出列 / alias，不是 graph 字段缺失。

对 weighted 的失败 case 做 `expected_tables` → `schema_context.metadata.tables` 对齐后，当前失败样本的目标表都已进入 SchemaGraph；例如 `db_core_002`、`db_hard_001`、`db_join_003` 的目标表都在 context 中，但生成 SQL / 输出检查仍失败。因此目前没有“目标表明确未进入 context”的 plus weighted 证据。

### 3. RRF 确实会改变上下文组成，但目前更像引入噪声迁移，而不是修复

- `db_multi_001` 的 RRF context 从 weighted 的 8 张表变为 9 张表，并引入 `orders_wide` / `user_behavior_log`，但 alias 问题没有变化。
- `db_hard_003`、`db_prompt_002` 等 case 中，RRF 增加了表或指标数量，却没有消除最终输出缺失。
- 同模型 A/B 的总分 `21/32 → 20/32`，并且 `query_plan`、`result_match` 各增加 1 条失败；这支持“RRF 改变了上下文，尚未证明改变方向正确”的判断。

## 当前瓶颈分类（第一版）

| 类别 | 当前证据 | 后续处理 |
|---|---|---|
| 真实 retrieval 未召回 | 现有 plus weighted/RRF trace 尚未证明一条纯粹的“目标表不在 context”案例；`schema_retrieval` 失败样本中至少有 case 的 context 已含目标表 | 不先改 embedding；需要逐 case 对齐 expected tables 与 SchemaGraph 后再判断 |
| merge / context 噪声 | RRF 改变表 / metric 集合，部分引入额外表，但端到端未提升 | 作为 M22 候选方向输入，不在本轮直接调 top_k / reranker |
| SQL 输出 / alias 契约 | `coupon_order_count`、`line_amount`、`paid_at` 等被 scorer 按最终列名检查；部分 case 的 context 表已正确 | 单独列为 scorer / prompt / SQL generation 风险，不能归咎 embedding |
| QueryPlan / SQL generation / timeout | plus 仍有少量 query_plan / sql_generation 错误；max 还有大量 45s timeout 型错误 | 与 embedding 链路分开统计 |
| 可观测性缺口 | trace 只有 field_count，没有完整字段名或“expected 是否进入 graph”的证据 | 后续可增加诊断输出，但不改变线上排序逻辑 |

## 地基结论

1. embedding API、Milvus collection、vector recall 和 fusion 参数传递链路目前没有发现阻塞性基础故障。
2. 当前 triage 的 `schema_context` 归因粒度过粗，直接拿它指导 rerank 可能会把 SQL alias / scorer 问题误修成检索问题。
3. M21 后续应收口为“证据分类和风险冻结”：先补齐逐 case 的 context / output 对齐证据，再把真正的 merge/context 噪声交给 M22 做 rerank、doc_type weighting 或 schema docs 实验。
4. 本轮没有修改代码、默认配置、正式 case、scorer 或 oracle，也没有新增长时间 LLM eval。

## M21 后续门禁结论

- 当前没有发现一个可以被证据明确证明为“embedding 已召回、但 Context Assembly 把目标物理表 / 字段丢掉”的 plus weighted case。
- 因此不在 M21 临时实现一个未经定位的 rerank / doc_type weighting / top_k 修复；否则容易把 SQL 输出契约或 triage 误归因当成检索问题。
- M21 地基目标已达到：embedding / Milvus / fusion 的基本事实、triage 归因缺口、上下文噪声风险和 M22 的实验边界均已记录。M22 可以在固定基线下大胆尝试 reranker、doc_type weighting 或 schema docs 方案。

## 下一道门

- 先补一份逐 case 的 `expected_tables / SchemaGraph.tables / body.tables_used / body.columns` 对齐表。
- 如果仍无法判断字段是否进入 context，再考虑只增加诊断字段（完整选中字段或文档 ID），不改变排序逻辑。
- 只有确认存在真实 merge/context 丢失后，才进入候选修复；正式 reranker 等方案留到 M22。
