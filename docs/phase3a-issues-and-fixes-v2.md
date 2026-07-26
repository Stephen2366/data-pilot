# Phase 3A 现存问题与修改方案 v2（已过时）

> ⚠️ **本文档已被 v4 取代，请阅读 [phase3a-issues-and-fixes-v4.md](phase3a-issues-and-fixes-v4.md)。**
>
> 基于 M12 新 pipeline 58 条真实 LLM 运行数据 + Phase 2.7 数据质量彩蛋背景的分析。
> 写于 2026-07-25。
>
> v1 → v2 变化：补入 Phase 2.7 数据质量彩蛋信息，重新归类失败根因。

## 背景

### M12 运行结果

| 评测集 | 结果 |
|---|---|
| formal 10 条 | 6/10 passed（安全 2/2 blocked，允许类 SQL 5/8） |
| challenge 16 条 | 8/16 passed（安全 2/2 blocked） |
| diagnostic 32 条 | 15/32 passed |

对照报告：`eval/reports/phase3a-comparison.md`（三份）。新 pipeline trace：`.agent_work/temp/phase3a-*-traces.jsonl`。

### Phase 2.7 数据库升级埋了什么

Phase 2.7 把数据底座从 7 表扩展为 14 表，**同时故意加入了真实业务中常见的数据质量问题**（称为"数据质量彩蛋"）。设计意图是测试后续 Text2SQL pipeline 能否应对真实数据复杂度，而非只处理干净数据。

| 彩蛋 | 具体表现 | 影响的查询类型 |
|---|---|---|
| `orders.paid_at IS NULL` | 部分订单创建了但未支付，`paid_at` 可空 | **所有财务指标查询**（GMV、净收入、各渠道 GMV） |
| `canceled` / `cancelled` 拼写差异 | 两种拼写都存在于 `order_status` 中 | 需要排除取消订单的查询 |
| 弱关联退款 | 部分退款通过 `refunds.source_order_no` 关联而非 `order_id`，`order_id` 可能为空 | 退款率、退款商品统计 |
| 金额不一致（5 条） | `orders.order_amount ≠ SUM(order_items.line_amount)` | 涉及 `order_items` 的商品销售额查询 |
| 重复源单号 | `orders.source_order_no` / `orders.external_order_no` 存在重复值 | `COUNT(DISTINCT)` 场景 |
| 负数退款冲销 | `refunds.refund_amount` 存在负值 | 退款金额汇总 |
| SCD 价格历史 | `products.price` 是当前价，`product_price_history` 按时间窗口记录历史价 | "当时售价"类查询 |

**关键设计约束**：这些彩蛋不破坏主键、外键和唯一约束。它们是"逻辑脏数据"——真实业务会乱，但数据模型本身是规范的。

---

## 失败 case 根因重新归类

v1 把大部分失败归为"别名漂移"和"LLM 时间字段用错"。**结合 Phase 2.7 彩蛋重新审视后，真实分布如下：**

### formal 10 条允许类 SQL（8 条，5 passed / 3 failed）

| case | eval 判 | 数据正确？ | v1 判断 | v2 修正根因 |
|---|---|---|---|---|
| p3a_simple_001 商品列表 | ❌ fail | ✅ 对 | 别名漂移（缺 category 列） | **不变**——LLM 没 SELECT category |
| p3a_agg_001 GMV | ✅ pass | ❌ **NULL** | 时间字段用错 | **`paid_at` 彩蛋**——LLM 不知道 GMV 必须用 paid_at |
| p3a_agg_002 净收入 | ✅ pass | ❌ **NULL** | 时间字段用错 | **`paid_at` 彩蛋** + `canceled/cancelled` 彩蛋 |
| p3a_agg_003 转化率 | ❌ fail | ✅ 对（0.7） | 别名漂移 | **eval 误判**——列名 `conversion_rate` 实际有，eval 可能匹配逻辑有问题 |
| p3a_multi_001 优惠券渠道 | ❌ fail | ✅ 对（650） | 中文列名 | **eval 评分问题**——数据对，列名是中文 `渠道`/`使用次数` |
| p3a_multi_002 商品销售额 Top5 | ❌ fail | ❌ **0 行** | 表召回不足 | **`paid_at` 彩蛋** + **金额不一致彩蛋**（LLM 选了 order_items）+ `products` 表召回遗漏 |
| p3a_multi_003 类目销售额 | ❌ fail | ⚠️ 仅 1 行 | 别名 + 结果不全 | `paid_at` 彩蛋 + 列名漂移（`category_name` vs `category`） |

**formal 允许类 SQL 失败中，直接由彩蛋导致的占 4/5（80%）。** 纯别名漂移只有 1 条（p3a_simple_001）。

### challenge 16 条中彩蛋影响

| case | 失败原因 | 相关彩蛋 |
|---|---|---|
| db_simple_002 已支付订单 | 0 行 | **`paid_at` 彩蛋**（用了 created_at） |
| db_core_002 退款率最高商品 | 0 行 | **弱关联退款彩蛋**（JOIN 条件没覆盖 source_order_no 路径） |
| db_multi_002 类目销售额 | 0 行 | **`paid_at` 彩蛋** + order_items 表遗漏 |
| db_multi_003 各渠道 GMV | 0 行 | **`paid_at` 彩蛋** |
| db_hard_003 历史均价 | missing `avg_price` | **SCD 价格历史彩蛋**（LLM 不知道要用 product_price_history 的时间窗口） |

---

## 问题列表

### 一、Eval 评分体系问题

#### 问题 1：eval 不检查数据正确性 ★ 最严重

**现象**：GMV 返回 `{"gmv": null}`，eval 判了 **passed**。

**为什么**：`eval/run_eval.py` 的 `_score_case()` 评分顺序完全不检查 `rows` 里的数据值：

```
1. HTTP 200？                  2. route == "sql"？
3. 安全期望 allow/block        4. expected_tables 是否命中
5. expected_columns 是否出现   6. contains/equals 文本匹配
```

这是 M6 smoke 时代的设计——"API 有没有崩"。Phase 3A 需要"SQL 对不对"。

**影响**：2 条 case（GMV、净收入）数据是错的但被判 pass。**导致 v1 一开始根本没发现 `paid_at` 彩蛋的问题。**

#### 问题 2：expected_columns 精确字符串匹配太脆弱

LLM 输出中文列名（`渠道`、`使用次数`），数据完全正确，eval 因找不到英文字符串而判 fail。**在彩蛋背景下更严重**——它让人们把注意力放在了"列名不对"上，而忽略了更关键的"数据本身就是错的"。

#### 问题 3：contains 检查既太松又太窄

- 太松：GMV=NULL 也能 contains `gmv` → 误判 pass
- 太窄：`Aurora Noise Cancelling Headphones` 在 rows 里但不在 answer 话术里 → 误判 fail

---

### 二、业务知识断层问题（Phase 2.7 彩蛋暴露的核心缺陷）

#### 问题 4：指标口径未注入 LLM prompt ★ 影响最大的根因

**现象**：新 pipeline 的 GMV、净收入、各渠道 GMV 都用了 `created_at` 而非 `paid_at`，返回 NULL。**这影响了 formal + challenge 中至少 5 条 case。**

**根因**：`domain_pack/metrics.yaml` 里写了 GMV 定义，但 M9 Schema Retrieval → SchemaGraph → prompt 这个链路中，**只有字段名流过去了，指标的计算规则没有流过去**。

```
正确链路应该是：
metrics.yaml "GMV=SUM(order_amount) WHERE paid_at BETWEEN..."
  → SchemaGraph（带上指标口径）
  → SQL prompt（"如果你要查 GMV，必须用 paid_at 过滤，排除 NULL"）

当前实际链路：
metrics.yaml "GMV=..."
  → SchemaGraph（只有字段名列表：orders.id, orders.created_at, orders.paid_at, ...）
  → SQL prompt（"你能用的字段：..."）
  → LLM 自己猜该用哪个时间字段 → 猜错
```

**旧链路为什么没这个问题？** GMV 是模板 SQL 命中的——模板是人写的，已经知道 `paid_at`。**旧链路的好成绩部分来自人工规避了彩蛋**，不是 LLM 更聪明。

#### 问题 5：数据结构复杂性未告知 LLM ★

**现象**：涉及退款率、商品销售额的查询返回 0 行或错误结果。

**根因**：Phase 2.7 的新数据结构（`order_items` 明细表、弱关联退款、金额不一致）对 LLM 是透明但未知的。LLM 看到 `order_items` 表存在，但不知道：
- 用 `order_items.line_amount` 汇总和 `orders.order_amount` 可能不一致（金额不一致彩蛋）
- `refunds.order_id` 可能为 NULL（弱关联退款彩蛋）
- 需要通过 `source_order_no` 做备选关联

#### 问题 6：SCD 时间窗口语义缺失

`product_price_history` 是 SCD Type 2 表——查"6 月历史均价"需要 `valid_from <= '2026-06-30' AND valid_to >= '2026-06-01'`。LLM 不知道这个时间窗口逻辑，可能直接 JOIN 后不做窗口过滤。

---

### 三、Schema Retrieval 问题

#### 问题 7：关键表召回遗漏

`p3a_multi_002`（商品销售额 Top 5）没召回 `products` 表。M9 的 keyword + vector 双路召回偏向了 `order_items`（金额字段命中），`products` 表的关键词权重不足。

#### 问题 8：0 行结果缺乏区分

多个查询返回 0 行，但不清楚是 SQL 写错了（时间窗口 / Join 条件），还是数据确实不满足条件。

---

### 四、Pipeline 层面

#### 问题 9：新链路评测时无模板兜底 ★ 架构级

旧链路对 GMV、退款率等是模板命中 → 秒级、稳定。新链路 `force_new_pipeline=true` 全部走 LLM → 慢（10-40 秒/条）、不稳定。**这是设计意图**——评测需要测量新 pipeline 裸奔质量。但要注意：旧 link 的好成绩来自**人工写好的模板规避了所有彩蛋**，不能直接和新链路裸奔对比。

#### 问题 10：LLM 生成失败时 trace 信息不足

`db_hard_001` 失败原因是 DeepSeek API 超时，trace 只有 `llm_generation_error`，没有 prompt 长度、重试次数、超时阈值。

---

### 五、M12 过程中已修复

| 问题 | 修复位置 |
|---|---|
| DeepSeek API 废弃 `deepseek-chat` → `deepseek-v4-pro` | `engine/nl2sql/generator.py` |
| 新 pipeline 绕过危险 SQL 预检 | `app/api/query.py` |
| plan validation 误判聚合表达式 | `engine/nl2sql/planner.py` |

---

## 修改方案

### 第 1 步：升级 eval 为"执行结果对比" ★★★ 最高优先级

**为什么先做**：不修这个，所有质量判断都是瞎的。v1 分析因为 eval 漏判，花了大量精力讨论"别名漂移"，而真正的根因（`paid_at` 彩蛋导致数据错误）被完全掩盖。

**方案**：在 eval case YAML 里新增 `expected_sql`（已知正确的参考 SQL），评分时执行两条 SQL 并比较结果集。

```yaml
- id: p3a_agg_001
  question: 2026 年 6 月 GMV 是多少？
  check:
    type: result_match
    expected_sql: |
      SELECT ROUND(SUM(o.order_amount), 2) AS gmv
      FROM orders o
      WHERE o.paid_at >= '2026-06-01'
        AND o.paid_at < '2026-07-01'
        AND o.order_status NOT IN ('cancelled', 'canceled')
```

```python
# _score_case() 新增
if case.check_type == "result_match":
    expected_rows = _execute_sql(case.expected_sql, db)
    actual_rows = body["rows"]
    if _rows_equal(expected_rows, actual_rows):
        return EvalScore(True, "result_match")
    else:
        return EvalScore(False, "result_mismatch", ["result_mismatch"])
```

**改动范围**：`eval/run_eval.py` + 3 个 YAML（补 `expected_sql`）。向后兼容，`smoke.yaml` 不受影响。

**直接效果**：
- GMV=NULL 不会再漏判
- 列名别名问题**自动消失**——只要结果对，列名叫什么无所谓
- 对齐 Spider/BIRD 等主流 Text2SQL 评测标准

---

### 第 2 步：metrics 口径注入 schema context ★★★ 与第 1 步同等重要

**为什么优先级升高**：v1 把它标为 ★★，但 Phase 2.7 彩蛋分析表明——**这是导致 formal 中 ~50% 允许类 SQL 失败的根因**。不是 LLM "笨"，是它没拿到关键信息。

**方案**：在 `metrics.yaml` 中补计算口径声明，让它们一路流到 SQL prompt。

```yaml
# metrics.yaml 扩展
gmv:
  key: gmv
  description: 已支付订单金额总和
  formula: SUM(orders.order_amount)
  key_filter_field: orders.paid_at      # ★ 核心过滤字段
  key_filter_null_behavior: exclude     # NULL 值排除
  exclude_status: [cancelled, canceled] # 排除的订单状态
  time_window_semantics: calendar_month # 时间窗口语义

net_revenue:
  key: net_revenue
  formula: SUM(orders.actual_amount)
  key_filter_field: orders.paid_at
  note: |
    净收入 = actual_amount 总和。actual_amount = order_amount 
    - discount_amount + shipping_amount。注意与 order_items.line_amount 
    汇总可能不一致（金额不一致彩蛋）。
```

`build_local_schema_sql_prompt()` 生成 prompt 时增加到"指标口径"段落：

```
## 指标口径（必须严格遵守）

查询以下指标时，TEXT2SQL 必须使用指定的过滤条件：

- **gmv**（已支付订单金额总和）
  - 时间过滤字段：**orders.paid_at**（不是 created_at）
  - 排除 orders.paid_at IS NULL 的订单
  - 排除 order_status IN ('cancelled', 'canceled') 的订单
  - 公式：SUM(orders.order_amount)

- **net_revenue**（净收入）
  - 时间过滤字段：**orders.paid_at**
  - 使用 orders.actual_amount 而非 order_amount
  - ⚠️ 注意：不要用 order_items.line_amount 替代
```

**改动范围**：

| 文件 | 改动 |
|---|---|
| `domain_pack/metrics.yaml` | 补 `key_filter_field`、`exclude_status`、`note` 等 |
| `engine/schema_retrieval/document_builder.py` | metric_doc 构建时带上口径信息 |
| `engine/nl2sql/prompt.py` | `build_local_schema_sql_prompt()` 增加指标口径段落 |

---

### 第 3 步：数据结构说明注入 prompt ★★

**目标**：让 LLM 知道 Phase 2.7 的数据结构特点（弱关联退款、金额不一致、SCD 时间窗口）。

**方案**：在 `relations.yaml` 或 `schema_desc/*.md` 中增加数据质量注释，并在 `build_local_schema_sql_prompt()` 中注入。

```
## 数据质量提示

- refunds 表：部分退款通过 source_order_no 弱关联，order_id 可能为 NULL。
  查询退款相关指标时，应考虑两种关联路径。
- orders vs order_items：orders.order_amount 和 SUM(order_items.line_amount)
  可能不一致（已知 5 条）。查询销售额时，优先使用 order_items 明细汇总。
- product_price_history：SCD Type 2 价格历史表。查询"历史价格"需要
  valid_from <= 目标时间 AND valid_to >= 目标时间。
```

**改动范围**：`domain_pack/schema_desc/` 或 `relations.yaml` + `engine/nl2sql/prompt.py`。

---

### 第 4 步：补 58 条 expected_sql ★★

**目标**：让 `result_match` 评分覆盖所有可自动评测的 case。

**参考 SQL 来源**：模板 SQL（已有）→ baseline trace 中正确的 SQL → 人工验证的新 SQL。

**可分批**：先补 10 条 formal，跑通逻辑；再补 challenge 和 diagnostic。

---

### 第 5 步：Schema Retrieval 召回优化 ★

修复 `p3a_multi_002` 没召回 `products` 表的问题。调整 keyword_text 权重或增加表级关联召回。

---

### 第 6 步：trace 信息增强 ★

LLM 调用失败时在 trace metadata 中记录 `prompt_length`、`timeout_seconds`、`attempt_number`。

---

## 优先级总览

| 优先级 | 做什么 | 解决什么问题 | 改动量 | 依赖 |
|---|---|---|---|---|
| ★★★ | eval 升级为 `result_match` | 测量工具不准，漏判数据错误 | 中 | 无 |
| ★★★ | metrics 口径注入 prompt | GMV 等指标用错时间字段（~50% 失败） | 小 | 无 |
| ★★ | 数据结构说明注入 prompt | LLM 不知道弱关联退款/金额不一致等彩蛋 | 小-中 | 无 |
| ★★ | 补 `expected_sql` | 让 result_match 覆盖全部 case | 中 | 第 1 步 |
| ★ | Schema Retrieval 召回优化 | 个别 case 表遗漏 | 小 | 第 1 步 |
| ★ | trace 信息增强 | LLM 失败调试效率 | 小 | 无 |

**建议执行顺序**：第 1 步（eval）和第 2 步（metrics 口径）可以并行做 → 重跑 eval 看清真实质量 → 根据真实失败分布决定后续优先级。

---

## 关键认知修正（v1 → v2）

| v1 判断 | v2 修正 |
|---|---|
| "主要问题是别名漂移" | **别名漂移只占失败的一小部分**。主要根因是 Phase 2.7 数据质量彩蛋暴露的业务知识断层 |
| "旧链路 75% 通过率 > 新链路 63%" | 旧链路的好成绩**来自人工模板规避了所有彩蛋**，不是 LLM 更强。新链路裸奔面对彩蛋，成绩低是预期结果 |
| "先修 eval，再修 LLM 质量" | 不变。但"修 LLM 质量"的具体手段更明确了：**不是调 prompt 措辞，而是把 metrics 口径和数据结构知识注入 prompt** |
| "GMV 时间字段用错是 LLM 的 bug" | 这不是 LLM 的 bug。`orders` 表有两个时间字段，LLM 没有理由偏好 `paid_at` 而非 `created_at`。**信息缺失 ≠ 模型错误** |

---

## 相关文件速查

| 用途 | 路径 |
|---|---|
| 新 pipeline trace | `.agent_work/temp/phase3a-*-traces.jsonl` |
| baseline trace | `.agent_work/temp/phase3a-baseline-traces.jsonl` 等 |
| 对照报告 | `eval/reports/phase3a-comparison.md` 等三份 |
| eval 评分逻辑 | `eval/run_eval.py` → `_score_case()` |
| LLM 生成器（模型名在这里） | `engine/nl2sql/generator.py` |
| 新 pipeline 编排 | `engine/nl2sql/pipeline.py` → `run_text2sql_pipeline()` |
| SQL prompt 构建 | `engine/nl2sql/prompt.py` → `build_local_schema_sql_prompt()` |
| plan 校验 | `engine/nl2sql/planner.py` → `_check_table_and_column_scope()` |
| Schema 检索 | `engine/schema_retrieval/retriever.py` |
| Schema 文档构建 | `engine/schema_retrieval/document_builder.py` |
| 指标定义 | `domain_pack/metrics.yaml` |
| 关系定义 | `domain_pack/schema_desc/relations.yaml` |
| Phase 2.7 数据库详情 | `docs/database-current-state.md` |
| Phase 2.7 升级档案 | `docs/archive/database-upgrade-plan-v5.md` |
| v1 问题分析 | `docs/phase3a-issues-and-fixes.md` |
