# Phase 3A 现存问题与修改方案 v1（已过时）

> ⚠️ **本文档已被 v4 取代，请阅读 [phase3a-issues-and-fixes-v4.md](phase3a-issues-and-fixes-v4.md)。**
>
> 基于 M12 新 pipeline 58 条真实 LLM 运行数据的分析。写于 2026-07-25。
> v1 的核心判断"主要问题是别名漂移"已被 v2/v3/v4 推翻——根因是管道断裂 + 数据质量彩蛋。

## 背景

M12 跑完了新 Text2SQL pipeline 的全部评测：

| 评测集 | 结果 |
|---|---|
| formal 10 条 | 6/10 passed（安全 2/2 blocked，允许类 SQL 5/8） |
| challenge 16 条 | 8/16 passed（安全 2/2 blocked） |
| diagnostic 32 条 | 15/32 passed |

对照报告已生成至 `eval/reports/phase3a-comparison.md` 等三份文件。新 pipeline trace 在 `.agent_work/temp/phase3a-*-traces.jsonl`。

下文按严重程度从高到低列出发现的问题。

---

## 一、Eval 评分体系问题

### 问题 1：eval 不检查数据正确性 ★ 最严重

**现象**：GMV 查询因为 LLM 用了 `created_at` 而非 `paid_at`，返回 `{"gmv": null}`，**eval 判了 passed**。

**为什么**：`eval/run_eval.py` 的 `_score_case()` 当前评分顺序：

```
1. HTTP 200？                          → 不是就 fail
2. route == "sql"？                    → 不是就 fail
3. 安全期望 allow/block               → 安全 case 看 blocked_reason
4. expected_tables 是否全部命中        → 缺就 fail（missing_table）
5. expected_columns 是否全部出现       → 缺就 fail（missing_column）
6. check_type 为 contains/equals 时    → 响应 JSON 里含不含某段文本
```

**从未检查 `rows` 里的数据值是否正确**。这是 M6 smoke 时代的设计——当时目标是"API 有没有崩"，不是"SQL 对不对"。Phase 3A 58 条正式评测需要更严格的评分。

**影响**：当前 6/10 的 formal 通过率是**虚高**的。至少 2 条 case（GMV、净收入）数据是错的但被判 pass。真实通过率可能只有 4/10 甚至更低。

**具体错误案例**：

```sql
-- LLM 生成的 GMV SQL（错误）
SELECT SUM(orders.order_amount) AS gmv
FROM orders
WHERE orders.created_at >= '2026-06-01'   -- ★ 应该是 paid_at
  AND orders.created_at < '2026-07-01'

-- 正确的 GMV SQL（模板里的）
SELECT ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= '2026-06-01'
  AND o.paid_at < '2026-07-01'
  AND o.order_status NOT IN ('cancelled', 'canceled')
```

### 问题 2：expected_columns 精确字符串匹配太脆弱

**现象**：LLM 输出中文列名（`渠道`、`使用次数`），数据完全正确，eval 因为找不到 `coupon_order_count` 这个英文字符串而判 fail。

**为什么**：强制 LLM 使用特定列别名违背了 LLM 的工作方式——它理解语义但不擅长精确字符串约束。这不是 bug，是评分策略选错了。

**案例**：

| eval 期望列名 | LLM 实际输出 | 数据正确？ | eval 判定 |
|---|---|---|---|
| `category` | `category_name` | ✅ | ❌ fail |
| `coupon_order_count` | `使用次数` | ✅ | ❌ fail |
| `avg_price` | `avg_selling_price` | ✅ | ❌ fail |
| `item_gmv` | `gmv` | 可能 | ❌ fail |

### 问题 3：contains 检查既太松又太窄

- **太松**：GMV=NULL 也能 contains `gmv` 文本 → 误判 pass
- **太窄**：`Aurora Noise Cancelling Headphones` 在 rows 数据里但不在 answer 话术里 → 误判 fail

---

## 二、LLM SQL 质量问题

### 问题 4：时间字段语义混淆 ★ 影响最大的 LLM 质量 bug

**现象**：新 pipeline 的 GMV 和净收入查询都用了 `created_at` 而不是 `paid_at`，导致返回 NULL。

**根因**：`domain_pack/metrics.yaml` 里 GMV 的定义写了"按 paid_at 过滤"，但 M9 Schema Retrieval 召回的只是 `orders` 表的字段名列表，**指标定义的过滤条件没有有效注入 SQL 生成 prompt**。LLM 看到 `orders.created_at` 和 `orders.paid_at` 两个时间字段，它不知道该用哪个。

旧链路为什么没这个问题？因为 GMV 是模板 SQL 命中的——模板是人工写的，`paid_at` 写死在 SQL 里。新链路 `force_new_pipeline=true` 不走模板，全靠 LLM 猜。

### 问题 5：0 行结果缺乏区分

**现象**：多个查询返回 0 行（商品销售额 Top5、已支付订单、退款率最高商品、各渠道 GMV），但不清楚是：
- SQL 写错了（时间窗口不对 / Join 条件不对）
- seed 数据里确实没有满足条件的数据

**根因**：eval 只看有没有返回 rows，不区分"返回了空结果"和"返回了错误结果"。

---

## 三、Schema Retrieval 问题

### 问题 6：关键表召回遗漏

**现象**：`p3a_multi_002`（2026 年 6 月商品销售额 Top 5）没召回 `products` 表。但 SQL 需要 JOIN products 拿 `product_name`。

**根因**：M9 的 keyword + vector 双路召回对"商品销售额"这个 query 偏向了 `order_items`（明细金额字段命中），`products` 表的关键词权重不足以进入 top_k。

### 问题 7：指标定义的关键字段未注入 schema context

**现象**：与问题 4 同源。`metrics.yaml` 里 GMV 写了 `paid_at`，但 M9 `SchemaGraph` 构建时只列出表的字段，没有把"GMV 依赖 `paid_at`"这个关键关联标注出来。

---

## 四、Pipeline 层面

### 问题 8：新链路评测时无模板兜底，全部走 LLM ★ 架构级设计

**现象**：旧链路对 GMV、退款率等高价值问题秒级返回、结果稳定（模板命中）。新链路 `force_new_pipeline=true` 时模板被完全跳过，全部走 LLM → 慢（10-40 秒/条）、结果不稳定。

**这不是 bug，是设计意图**——评测需要强制绕过模板才能测量新 pipeline 的真实质量。但需要注意：
- 新 pipeline 在评测中的 **低通过率不代表生产切换后的表现**，因为生产环境仍然模板优先
- eval 用的 `--pipeline-mode new_text2sql` 只在评测场景有意义

### 问题 9：LLM 生成失败时 trace 信息不足

**现象**：`db_hard_001` 失败原因是"DeepSeek API 超时"，trace step 里只有 `llm_generation_error`，没有记录 prompt 长度、重试次数、超时阈值。

---

## 五、M12 过程中已修复的问题

| 问题 | 修复位置 | 说明 |
|---|---|---|
| DeepSeek API 废弃 `deepseek-chat` | `engine/nl2sql/generator.py` | 默认模型名改为 `deepseek-v4-pro` |
| 新 pipeline 绕过了危险 SQL 预检 | `app/api/query.py` | `force_new_pipeline` 分支前增加 `_looks_like_dangerous_sql` |
| plan validation 误判聚合表达式 | `engine/nl2sql/planner.py` | `COUNT(DISTINCT orders.id)` 不再被当成未知列名 |

---

## 修改方案

### 第 1 步：升级 eval 为"执行结果对比" ★★★ 最高优先级

**目标**：让 eval 能区分"列名不对"和"数据不对"。

**方案**：在 eval case YAML 里新增 `expected_sql`（一条已知正确的参考 SQL），评分时执行两条 SQL 并比较结果集：

```yaml
# phase3a-regression.yaml 示例
- id: p3a_agg_001
  question: 2026 年 6 月 GMV 是多少？
  check:
    type: result_match              # 新 check type
    expected_sql: |                 # 参考 SQL（已知正确）
      SELECT ROUND(SUM(o.order_amount), 2) AS gmv
      FROM orders o
      WHERE o.paid_at >= '2026-06-01'
        AND o.paid_at < '2026-07-01'
        AND o.order_status NOT IN ('cancelled', 'canceled')
```

`_score_case()` 新增逻辑：

```python
if case.check_type == "result_match":
    expected_rows = _execute_sql(case.expected_sql, db)
    actual_rows = body["rows"]
    if _rows_equal(expected_rows, actual_rows):
        return EvalScore(True, "result_match")
    else:
        return EvalScore(False, f"result_mismatch", ["result_mismatch"])
```

**改动范围**：

| 文件 | 改动 |
|---|---|
| `eval/run_eval.py` | `_score_case()` 新增 `result_match` check type；新增 `_execute_sql()` 和 `_rows_equal()` |
| `eval/cases/phase3a-regression.yaml` | 10 条 case 补 `expected_sql` |
| `eval/cases/database-upgrade-challenge.yaml` | 16 条 case 补 `expected_sql` |
| `eval/cases/phase3a-diagnostic-benchmark.yaml` | 16 条 case 中可自动评分的补 `expected_sql` |

向后兼容：旧的 `contains`/`equals`/`manual` check type 不受影响，`smoke.yaml` 不需要改。

**效果**：
- GMV=NULL 不会再被误判为 pass
- 列名别名问题**自动消失**——只要结果集一样，列名叫什么无所谓
- 对齐 Spider/BIRD 等主流 Text2SQL 评测标准，面试好讲

---

### 第 2 步：metrics 口径注入 schema context ★★

**目标**：让 LLM 知道"GMV 必须用 `paid_at` 过滤"，不再猜错时间字段。

**方案**：在 M9 构建 SchemaGraph 时，把命中的 metrics 的关键计算口径一并注入 prompt：

```yaml
# metrics.yaml 扩展示例
gmv:
  key: gmv
  description: 已支付订单金额总和
  formula: SUM(orders.order_amount)
  key_filter: orders.paid_at BETWEEN :start AND :end
  key_fields: [orders.paid_at, orders.order_amount]
  exclude_status: [cancelled, canceled]
```

`build_local_schema_sql_prompt()` 在生成 SQL prompt 时，把上述信息编入"指标口径"小节：

```
## 指标口径（必须严格遵守）
- gmv：已支付订单金额总和
  公式：SUM(orders.order_amount)
  过滤：orders.paid_at 在查询时间范围内
  排除状态：cancelled, canceled
```

**改动范围**：

| 文件 | 改动 |
|---|---|
| `domain_pack/metrics.yaml` | 补 `key_filter`、`key_fields` 字段 |
| `engine/schema_retrieval/document_builder.py` | `build_schema_documents()` 构建 metric_doc 时带上口径 |
| `engine/nl2sql/prompt.py` | `build_local_schema_sql_prompt()` 增加指标口径段落 |

---

### 第 3 步：补 58 条 expected_sql ★★

**目标**：让 `result_match` 评分能覆盖所有可自动评测的 case。

**方案**：参考 SQL 来源优先级——
1. 已有模板 SQL（`engine/nl2sql/templates.py`）→ 直接复用
2. M8 baseline 跑过的正确结果 SQL → 从 baseline trace JSONL 提取
3. 新写并经人工验证的 SQL

**改动范围**：3 个 YAML 文件，约 50 条可自动评测的 case（排除 `check.type=manual` 的困难诊断题）。

**可分批做**：先把 10 条 formal 的 `expected_sql` 补齐，跑通 result_match 逻辑；然后补 challenge 和 diagnostic。

---

### 第 4 步：Schema Retrieval 召回优化 ★

**目标**：修复个别 case 的表召回遗漏（如 `p3a_multi_002` 没召回 `products`）。

**方案**：调整 keyword_text 权重。当 query 包含"商品 + 销售额/金额"时，`products` 表的字段（`product_name`）应该增加表级关联召回信号。具体做法：
- 在 `document_builder.py` 中，为 `field_doc` 的 `keyword_text` 增加**所属表名**的重复出现（提高表级命中率）
- 或在 `retriever.py` 的 keyword 召回中，命中 3 个以上同表字段时，自动补入该表的其他关键字段

**改动范围**：`engine/schema_retrieval/document_builder.py` 或 `retriever.py`

---

### 第 5 步：trace 错误信息增强 ★

**目标**：LLM 调用失败时能快速定位原因。

**方案**：在 `query_plan` 和 `sql_generation` trace step 的 metadata 中增加：
- `prompt_length`：发送给 LLM 的 prompt 字符数
- `timeout_seconds`：本次调用的超时阈值
- `attempt_number`：如果有重试逻辑，记录第几次尝试

**改动范围**：`engine/nl2sql/pipeline.py` 的 `run_text2sql_pipeline()`

---

## 优先级总览

| 优先级 | 做什么 | 为什么 | 改动量 | 依赖 |
|---|---|---|---|---|
| ★★★ | eval 升级为 `result_match` | 不修这个，所有质量判断都是瞎的 | 中 | 无 |
| ★★ | metrics 口径注入 schema context | 解决 GMV 等核心指标的时间字段错误 | 小 | 无 |
| ★★ | 补 58 条 `expected_sql` | 让 result_match 能跑起来 | 中 | 第 1 步 |
| ★ | Schema Retrieval 召回优化 | 修复个别 case 表遗漏 | 小 | 第 1 步（需要先有准确测量） |
| ★ | trace 信息增强 | 提升 LLM 失败调试效率 | 小 | 无 |

**建议执行顺序**：第 1 步 → 重跑 eval 看清真实质量 → 根据真实失败分布决定后续步骤优先级。**不要在测量工具不准的情况下盲目修质量**。

---

## 相关文件速查

| 用途 | 路径 |
|---|---|
| 新 pipeline formal trace | `.agent_work/temp/phase3a-new-traces.jsonl` |
| 新 pipeline challenge trace | `.agent_work/temp/phase3a-challenge-new-traces.jsonl` |
| 新 pipeline diagnostic trace | `.agent_work/temp/phase3a-diagnostic-new-traces.jsonl` |
| baseline formal trace | `.agent_work/temp/phase3a-baseline-traces.jsonl` |
| baseline challenge trace | `.agent_work/temp/phase3a-challenge-baseline-traces.jsonl` |
| baseline diagnostic trace | `.agent_work/temp/phase3a-diagnostic-baseline-traces.jsonl` |
| formal 对照报告 | `eval/reports/phase3a-comparison.md` |
| challenge 对照报告 | `eval/reports/phase3a-challenge-comparison.md` |
| diagnostic 对照报告 | `eval/reports/phase3a-diagnostic-comparison.md` |
| eval 评分逻辑 | `eval/run_eval.py` → `_score_case()` |
| LLM 生成器 | `engine/nl2sql/generator.py` |
| 新 pipeline 编排 | `engine/nl2sql/pipeline.py` |
| SQL prompt 构建 | `engine/nl2sql/prompt.py` |
| plan 校验 | `engine/nl2sql/planner.py` → `_check_table_and_column_scope()` |
| Schema 检索 | `engine/schema_retrieval/retriever.py` |
| 指标定义 | `domain_pack/metrics.yaml` |
| M12 阶段计划 | `docs/phase3a-plan.md` → M12 小节 |
| M12 开发笔记 | `.agent_work/temp/m12-notes.md` |
