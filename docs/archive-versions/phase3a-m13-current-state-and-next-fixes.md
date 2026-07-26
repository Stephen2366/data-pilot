# Phase 3A M13 后当前状态与后续修复建议

> 写于 2026-07-26。用途：给新开的 AI 会话快速了解 DataPilot 在 Phase 3A / M13 之后的真实状态、剩余问题和后续修改建议。
>
> 先读本文，再按需查 `docs/AI_CONTEXT.md`、`docs/dev-log.md`、`eval/reports/phase3a-*.md`、`docs/archive-dormant/phase3a-issues-and-fixes-v5.md`。

## 1. 一句话结论

M13 已验收。Phase 3A 的新 Text2SQL pipeline 已经从“测不准 + 指标口径断链”的状态，修到 formal 10/10、challenge 14/16、diagnostic 23/32。当前不建议为了追满 diagnostic 继续大改 prompt；如果进入阶段三 RAG / Hybrid 前想再收口，建议只做一个小的 M14-lite：补最小 `result_match`、改善 LLM 失败 trace、整理安全/diagnostic 口径。

## 2. 当前状态

### 模块状态

- 当前模块：M13 Phase 3A 新 pipeline 质量修复（已验收）
- 下一模块：阶段三 RAG / Hybrid（待定）
- 验收记录：`accept-M13-20260726.md`
- 当前阶段计划文件：`docs/phase3a-plan.md`

### 最新评测结果

| 评测集 | M13 后结果 | 说明 |
|---|---:|---|
| formal 10 | 10/10 | 正式回归已全过 |
| challenge 16 | 14/16 | 仍有 2 条，含 1 条非阻塞 manual-review 类 |
| diagnostic 32 | 23/32 | 诊断集仍暴露 9 条问题，其中 3 条需要/涉及 manual review |
| pytest | 78 passed | 仅 1 个既有 Starlette/httpx warning |

如果按“真实通过”口径复盘 M13 前基线，可在面试中谨慎描述为：formal 约 4/10 -> 10/10，challenge 约 6/16 -> 14/16，diagnostic 约 12/32 -> 23/32。这里的“约”很重要，因为 M12 原报告的 6/10、8/16、15/32 里包含旧 eval 误判。

## 3. M13 已经修掉了什么

### 3.1 评测尺子不准

旧 eval 主要看列名和文本包含。典型问题是 GMV 查询 SQL 算出 `NULL`，但因为响应里有 `gmv` 字样仍可能 pass。

M13 已完成：

- 新增 `expected_value` 固定事实检查。
- GMV、净收入等确定性 seed 事实改成数值断言。
- 单指标题只有一列时，允许列名漂移但必须数值正确。
- 为语义等价列名补 `expected_column_aliases`，例如 `usage_count` 可视为 `coupon_order_count`。

### 3.2 metrics -> prompt 管道断裂

`domain_pack/metrics.yaml` 里早就定义了 `filter` 和 `default_time_field`，但新 pipeline 的 `_format_plan_metrics()` 重写时漏传。模型不知道 GMV 要用 `orders.paid_at`，容易错用 `orders.created_at` 或幻想不存在的 `unpaid` 状态。

M13 已完成：

- `_format_plan_metrics()` 输出 `filter/default_time_field`。
- QueryPlan 和局部 SQL prompt 都能看到指标口径。
- QueryPlan / SQL generation 使用不同 system prompt。

### 3.3 商品/类目销售额口径漂移

模型容易把“销售额”统一理解为订单头 GMV，即 `orders.order_amount`。但商品/类目销售额应该走 `item_gmv`，聚合 `order_items.line_amount`，再通过 `order_items.product_id = products.id` 关联商品和类目。

M13 已完成：

- QueryPlan prompt 增加商品/类目销售额约束。
- SQL prompt 增加 `item_gmv` 和商品表 join 约束。
- 转化率补浮点除法要求，避免 SQLite 整数除法。

### 3.4 trace 可观测性不足

M13 前看失败报告时，很难区分是 Schema Retrieval 没召回、QueryPlan 没写对，还是 SQL 生成没遵守计划。

M13 已完成：

- `schema_retrieval.metadata.metric_doc_hits`
- `sql_generation.metadata.plan_step_tables`
- `plan_step_columns`
- `plan_step_filters`
- `plan_step_metrics`
- `plan_step_joins`
- `plan_step_output_columns`

## 4. 当前剩余问题

### 4.1 challenge 剩余问题

#### `db_multi_002 一级类目销售额排名`

最新 challenge 报告中该 case 是 `llm_generation_error`，但 diagnostic 同题曾跑过。它更像 LLM JSON/生成稳定性问题，不是稳定的 schema 召回或 SQL 语义错误。

建议：

- 不为这一条单独调 prompt。
- 若做 M14-lite，可补 raw response preview、JSON parse error、必要时单次 retry。

#### `db_hard_001 数码电子及其子类目 2026 年 6 月 GMV`

递归类目题被 SQL Guard 拦截。这里涉及 `WITH RECURSIVE` 是否允许、如何限制只读递归 CTE、类目树应该用 `item_gmv` 还是订单头 GMV。

建议：

- 不建议在 RAG 前硬修。
- 后续如果要做，应作为“SQL Guard 支持安全递归 CTE + 类目树语义”的独立小设计。

### 4.2 diagnostic 剩余问题

当前 9 条未过可以粗分为 5 类：

| 类别 | 代表 case | 问题本质 | 建议 |
|---|---|---|---|
| 输出列 / alias / 诊断评分严格 | `db_schema_002`、`db_join_002`、`db_prompt_001`、`db_prompt_002`、`db_prompt_003` | SQL 可能接近正确，但 eval 期待某些列名或字段出现 | M14-lite 可少量清理；不要无限补 alias |
| 计划校验或 guard 边界 | `db_join_003`、`db_plan_003` | QueryPlan / plan validation / SQL Guard 对复杂关系处理不足 | 留到后续语义层或 guard 设计 |
| 递归类目 | `db_hard_001` | 需要递归 CTE 安全策略和类目树口径 | 不建议当前硬补 |
| 权限语义 | `db_sec_004` | admin 查询管理员联系方式是否应该被敏感字段策略拦截，口径未完全定清 | M14-lite 可优先定规则 |
| 复杂业务归因 | 知识库文档带来的订单金额、商品退款率归因等 | 需要 Hybrid / semantic layer，而不是单纯 Text2SQL prompt | 留到阶段三或后续 |

## 5. 除了当前 failed case，还存在的潜伏问题

这些未必影响 M13 最新分数，但后续继续做 RAG / Hybrid 或面试包装时要知道。

### 5.1 `MetricDescription` 未加载 `numerator/denominator`

`metrics.yaml` 中部分比例类指标定义了 `numerator` 和 `denominator`，但当前 `MetricDescription` 只建模 `name/formula/description/filter/default_time_field` 等字段。退款率、优惠券使用率这类复杂比例指标以后可能需要更精确公式。

建议：等进入 semantic layer 或 result_match 扩展时一起处理。

### 5.2 schema_desc 中部分业务枚举仍可能不完整

例如 `orders.order_status` 涉及 `cancelled` / `canceled` / `pending_payment`。M13 已通过 metrics filter 缓解核心指标问题，但 schema_desc 源头仍值得后续清理。

建议：作为低风险文档/配置卫生项，后续小修即可。

### 5.3 宽表和标准星型表选择策略仍不清晰

`orders_wide` 对看板口径很方便，但商品、类目、退款归因等问题通常必须走标准明细表。当前主要靠 prompt 和检索结果引导，还没有明确的 table selection policy。

建议：RAG / Hybrid 前不必大修；后续可抽象成“查询意图 -> 表选择策略”。

### 5.4 Eval 仍不是完整企业级

M13 后 eval 已经比 M12 好很多，但仍未完成：

- `expected_sql` 双执行对比。
- 全量 `result_match`。
- 多轮运行稳定性统计。
- 自动错误归因更细化。
- manual_review case 的稳定处理规则。

建议：如果开 M14-lite，做最小 `result_match` 雏形即可，不要试图一步到位做完整 EvalOps。

## 6. 后续修改建议

### 推荐路线 A：直接进入阶段三 RAG / Hybrid

适合目标：不再纠结 diagnostic 满分，开始构建更完整 Agent 能力。

理由：

- formal 已 10/10，challenge 已 14/16。
- diagnostic 本来就是诊断素材，不是正式硬门。
- 剩余复杂问题多与 Hybrid、权限、安全、语义层相关，阶段三能自然覆盖一部分。

进入阶段三前，新会话建议先读：

1. `docs/AI_CONTEXT.md`
2. `docs/phase3a-m13-current-state-and-next-fixes.md`
3. `docs/phase3a-plan.md`
4. `docs/database-current-state.md`
5. 最新 eval reports

### 推荐路线 B：新增 M14-lite，做 Phase 3A 收口

适合目标：进入 RAG 前把 Text2SQL / Eval 的基础卫生再整理一下，但不追满分。

建议范围：

1. **result_match 最小雏形**
   - 给 3-5 条核心 SQL case 加 `expected_sql`。
   - eval 同时执行 expected SQL 和 generated SQL，比结果集。
   - 先覆盖 GMV、净收入、渠道 GMV、商品销售额 TopN、优惠券 GMV 等典型题。

2. **LLM 失败 trace 增强**
   - `llm_generation_error` 记录 raw response preview。
   - 记录 JSON parse error、prompt length。
   - 可选：SQL generation JSON 解析失败时 retry 1 次。

3. **安全口径定稿**
   - 明确敏感字段策略是否优先于 admin 角色。
   - 处理 `db_sec_004` 这类“管理员联系方式”问题。

4. **diagnostic case 口径清理**
   - 明显误杀的列名/alias 做少量修正。
   - 探索性问题标 `manual_review` 或 non_blocking。
   - 不用 alias 掩盖错表、缺表、错口径。

5. **Schema Retrieval 后端配置开关**

当前 `MilvusVectorIndex` 和 `SiliconFlowEmbeddingProvider` 已存在，M9.1/M9.2 smoke 验证过；但正式 `run_text2sql_pipeline()` 调用 `retrieve_schema()` 时没有配置开关，默认仍走 `InMemory + Deterministic`。

M14-lite 可选择新增显式配置：
- `SCHEMA_VECTOR_BACKEND=inmemory|milvus`
- `SCHEMA_EMBEDDING_PROVIDER=deterministic|siliconflow`
- `MILVUS_COLLECTION=...`
- `MILVUS_RESET_COLLECTION=false`

要求：
- 默认仍为 `inmemory + deterministic`；
- Milvus/SiliconFlow 必须显式开启；
- pytest 不依赖外部 Milvus 或联网 embedding；
- 开关用于工程能力和后续 RAG 复用，不作为提升 M13 eval 分数的主线。

备注：2026-07-26 临时 A/B 实验显示 Milvus + SiliconFlow 对 M13 eval 没有提升：formal 10/10 持平，challenge 14/16 持平，diagnostic 23/32 -> 20/32。因此不建议切默认。

不建议 M14-lite 做：

- 递归类目 CTE 支持。
- 知识库文档归因。
- 商品退款率完整归因。
- JSON mode 三组大实验。
- 完整 EvalOps 平台化。

### 不推荐路线 C：继续追 diagnostic 满分

不建议原因：

- 容易变成针对 case 的 prompt 补丁。
- 会把 RAG / Hybrid 阶段真正该解决的问题提前塞进 Text2SQL。
- diagnostic 里有些问题本来就是未来能力探针，不应该作为当前硬门。

## 7. 给新 AI 会话的建议执行方式

如果用户要求“进入阶段三 RAG / Hybrid”：

1. 先确认 M13 已验收，不要回头重修 M13。
2. 只把本文件的剩余问题作为背景，不要默认开 M14。
3. 设计 RAG / Hybrid 时重点考虑权限、知识库归因、SQL + 文档混合 trace。

如果用户要求“先做 M14-lite”：

1. 创建 `.agent_work/temp/m14-lite-notes.md`。
2. 只做 `result_match` 最小雏形 + trace raw error + 安全口径清理。
3. 每项都先写测试，再做最小实现。
4. 不以 diagnostic 满分作为目标，目标是“评测更可信、失败更好查、边界更清楚”。

如果用户要求“把 diagnostic 剩余 9 条修完”：

1. 先提醒这不建议作为当前目标。
2. 解释哪些适合现在修，哪些应留到 RAG / semantic layer。
3. 除非用户明确坚持，否则不要开始大范围 prompt patch。

## 8. 重要文件速查

| 用途 | 路径 |
|---|---|
| 当前技术档案 | `docs/AI_CONTEXT.md` |
| 用户学习复盘 | `docs/dev-log.md` |
| M13 问题与方案归档 | `docs/archive-dormant/phase3a-issues-and-fixes-v5.md` |
| M13 notes | `.agent_work/temp/m13-notes.md` |
| formal 最新报告 | `eval/reports/phase3a-new-pipeline.md` |
| challenge 最新报告 | `eval/reports/phase3a-challenge-new-pipeline.md` |
| diagnostic 最新报告 | `eval/reports/phase3a-diagnostic-new-pipeline.md` |
| eval scorer | `eval/run_eval.py` |
| Text2SQL prompt | `engine/nl2sql/prompt.py` |
| LLM generator | `engine/nl2sql/generator.py` |
| pipeline trace | `engine/nl2sql/pipeline.py` |
| 指标定义 | `domain_pack/metrics.yaml` |
