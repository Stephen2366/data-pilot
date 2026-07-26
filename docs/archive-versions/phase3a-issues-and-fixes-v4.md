# Phase 3A 现存问题与修改方案 v4

> 基于 M12 新 pipeline 58 条真实 LLM 运行数据 + Phase 2.7 数据质量彩蛋（已查库验证）+ DeepSeek v4-pro 行为分析 + AskData 参考项目对比。
> 写于 2026-07-25，供后续 AI 会话快速了解现状。
>
> **v3 → v4 变化**：① 展开第 6 步 trace 增强为分层具体方案（①~⑥）；② 新增问题十（AskData 两段式 + 不强制 JSON 参考）及部分对齐建议；③ 问题三实验方案精化为三组对照；④ 彩蛋表已查库验证。

## 致 AI（新会话速览）

**项目**：DataPilot，企业数据分析 Agent 系统（FastAPI + DeepSeek + MySQL）。

**当前状态**：Phase 3A（Text2SQL 深化）M8-M12 代码全部完成，M12 刚收工。新 Text2SQL pipeline 已实现但评测通过率偏低（允许类 SQL ~50%）。用户正在分析根因和制定修复计划。

**你需要知道的 3 句话**：

1. `metrics.yaml` 里 `filter` 和 `default_time_field` 字段**已定义**，`MetricDescription` 也正确加载了。旧 M4 路径的 `_format_metrics()` 早就读了这 2 个字段，但新 pipeline（M11）的 `_format_plan_metrics()` **重写时漏掉了**，只读了 `name/formula/description`。这是典型的重写回归（rewrite regression），不是全局设计遗漏。**管道在最后几行代码断了。**

2. 由此导致 LLM 不知道"GMV 必须用 `paid_at` 过滤"，加上 Phase 2.7 故意埋的数据质量彩蛋（`paid_at` 可空），~50% 的 case 数据查出来是错的。

3. **最高优先级修复**：改 `prompt.py` 的 `_format_plan_metrics()`（~8 行）+ system prompt 顺手一起改（~10 行）→ 第一批发包。eval 最小修复（新增 `expected_value` check 类型，直接比固定事实数值）**必须和管道修复同步做**——否则当前 `contains: gmv` 检查连 NULL 都判 pass，修了管道也测不出效果。`expected_value` 只需 ~20 行代码 + 改几条 YAML，可复用 Phase 2.7 已埋好的固定事实（GMV=11285752.00 等）。管道修好后，再加 trace 信息增强（~20 行），方便后续排查残留问题。AskData 参考项目的做法验证了"规划层保持 JSON、SQL 层放开 JSON"的方向。

**用户已确认的结论**：

- 不修别名漂移（那是症状不是根因）
- `metrics.yaml` 方式是正确的，比 AskData 和 DB-GPT 的做法更结构化
- eval 评分需要从"列名匹配"升级为"执行结果对比"。**不先修 eval 就修管道等于盲飞**——当前 `contains: gmv` 检查连 NULL 都判 pass。至少先上 `expected_value`（固定事实断言），利用 Phase 2.7 已埋好的 GMV=11285752.00 等数值，代价 ~20 行 + 改几条 YAML
- 第 1 步（管道修复）+ 第 2 步（system prompt）+ eval 最小修复（`expected_value`）可以第一批发包，合计不到 50 行。第 3 步（JSON 模式实验）后续再做
- 不全盘照搬 AskData 的两段式，做分层处理

**相关会话历史**：用户问了"AskData 和 DB-GPT 怎么做指标定义"→ 结论是 DataPilot 的 `metrics.yaml` 更结构化。用户问了"会不会和 LLM 有关"→ 发现 system prompt 错配和 JSON 模式可能压制 v4-pro 的 thinking。用户要求查库验证彩蛋→ 发现 source_order_no 命名空间完全不同、pending_payment 状态未在文档列出等问题。用户要求对比 AskData 的模型策略→ 两段式 + 不强制 JSON，验证了部分对齐的方向。

**旧版本文档**：v1（纯别名视角，已过时）、v2（补了 Phase 2.7 彩蛋分析，已过时）、v3（补 LLM 行为分析 + 源码复核，已过时）在同目录下，**v4 是最新且唯一的权威版本**。

---

## 背景

### M12 运行结果

| 评测集 | 结果 |
|---|---|
| formal 10 条 | 6/10 passed（安全 2/2 blocked，允许类 SQL 5/8） |
| challenge 16 条 | 8/16 passed（安全 2/2 blocked） |
| diagnostic 32 条 | 15/32 passed |

### Phase 2.7 数据质量彩蛋

Phase 2.7 在数据库中故意埋入了真实业务常见的数据质量问题。以下数据来自 2026-07-25 对 MySQL `datapilot_dev` 的实际查询：

| 彩蛋 | 实际数据 | 影响 | LLM 易犯错误 |
|---|---|---|---|
| `orders.paid_at IS NULL` | 20 条订单，状态均为 `pending_payment`，`paid_at` 为空 | 所有财务指标查询 | 用 `created_at` 代替 `paid_at` 做时间过滤；或以为"未支付"对应 `order_status = 'unpaid'`（实际不存在此状态） |
| `canceled` / `cancelled` 拼写差异 | `cancelled`（双 l）421 条 + `canceled`（单 l）8 条 = 共 429 条取消订单 | 排除取消订单的查询 | 只过滤 `cancelled` 漏掉 8 条 `canceled`（约 1.9%） |
| 弱关联退款：`source_order_no` 命名空间不同 | 退款 `source_order_no` 格式为 `SRC-2026-XXXXX`，订单 `order_no` 格式为 `ORD-2026-XXXXX`——**两者不能 join** | 退款率统计：必须用 `refunds.order_id -> orders.id` 关联 | 试图 `refunds.source_order_no = orders.order_no` → 0 行结果 |
| 整单退款（`order_item_id` 可空） | 1000 条退款中 100 条 `order_item_id IS NULL`（10%），只能通过 `order_id` 关联 | 商品维度退款率：INNER JOIN `order_items` 会丢 10% | `refunds JOIN order_items ON order_item_id`（inner join）→ 丢失整单退款 |
| 金额不一致（5 条） | `orders.order_amount ≠ SUM(order_items.line_amount)` 的订单共 5 条 | 商品销售额查询：`item_gmv` 与 `gmv` 口径不同 | 假设 orders.order_amount = SUM(order_items.line_amount) |
| 重复源单号 | `source_order_no` 10000 条中 9980 distinct（重复 20）；`external_order_no` 同 | COUNT DISTINCT 场景 | 用 `COUNT(source_order_no)` 代替 `COUNT(DISTINCT source_order_no)` |
| 负数退款冲销 | 3 条 `refund_amount = -20.00`，状态分别为 completed / requested / rejected | 退款汇总：`SUM(refund_amount)` 会偏低 | 不知道负数退款的业务含义（冲销/调整） |
| SCD 价格历史 | 150 行覆盖 50 个商品，`valid_from` 范围 2026-01-01 ~ 2026-07-01 | 历史价格查询：必须匹配时间窗口 | 不加 `valid_from <= target < valid_to` 直接查最新价 |

> **关键数据速查**：orders 10000 行，6 月（`paid_at` 口径）GMV = `11285752.00`；`order_status` 分布：delivered 3371 / paid 3091 / shipped 3089 / cancelled 421 / pending_payment 20 / canceled 8；`user_behavior_log` 事件：view_product 4900 / add_to_cart 2600 / search 1280 / payment_success 1220。

---

## 失败根因重新归类

### formal 10 条允许类 SQL（8 条）

| case | eval 判 | 数据正确？ | 根因 |
|---|---|---|---|
| p3a_simple_001 商品列表 | ❌ | ✅ | LLM 没 SELECT category 列 |
| p3a_agg_001 GMV | ✅ | ❌ NULL | `paid_at` 彩蛋 + **prompt 没注入 `default_time_field`** |
| p3a_agg_002 净收入 | ✅ | ❌ NULL | 同上 |
| p3a_agg_003 转化率 | ❌ | ✅ 0.7 | eval 列名匹配误判 |
| p3a_multi_001 优惠券渠道 | ❌ | ✅ 650 | LLM 输出中文列名，eval 不认 |
| p3a_multi_002 商品销售额 Top5 | ❌ | ❌ 0 行 | `paid_at` 彩蛋 + 金额不一致 + products 表未召回 |
| p3a_multi_003 类目销售额 | ❌ | ⚠️ 仅 1 行 | `paid_at` 彩蛋 + 列名漂移 |

**核心结论**：失败中 ~80% 和 `paid_at` 相关。根因是 `metrics.yaml` 已定义了 `filter` 和 `default_time_field`，但 prompt 构建函数没把它们传给 LLM。

---

## 问题列表

### 一、metrics → prompt 管道断裂 ★★★ 最严重、最容易修

**`metrics.yaml` 已经写得很完整了：**

```yaml
gmv:
    name: GMV
    formula: SUM(orders.order_amount)
    filter: orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL
    default_time_field: orders.paid_at
    description: 成交总额，默认不含运费、不扣优惠，排除未支付和已取消订单。
```

**但 `prompt.py` 的 `_format_plan_metrics()` 只取了 `name`、`formula`、`description`：**

```python
# prompt.py 当前代码 —— 只读三个字段
name = getattr(metric, "name", metric_key)
formula = getattr(metric, "formula", "")
description = getattr(metric, "description", "")
lines.append(f"- {metric_key}（{name}）：{formula}。{description}")
# ↑ filter 和 default_time_field 被丢弃了！
```

**LLM 实际看到的 prompt 内容：**

```
- gmv（GMV）：SUM(orders.order_amount)。成交总额，默认不含运费、不扣优惠，排除未支付和已取消订单。
```

LLM 不知道 `default_time_field: orders.paid_at`，也不知道 `filter: ... AND orders.paid_at IS NOT NULL`。它看到 `orders.created_at` 和 `orders.paid_at` 两个时间字段，只能猜。猜错了。

**而且 `description` 里写"排除未支付"，LLM 把它理解成了 `order_status` 过滤：**

```sql
-- LLM 理解的"排除未支付"
AND order_status NOT IN ('unpaid', 'cancelled')

-- 实际需要的
AND paid_at IS NOT NULL AND order_status NOT IN ('cancelled', 'canceled')
```

"未支付"在数据库里不是 `order_status` 值——它是 `paid_at IS NULL`。LLM 不知道这个映射关系。这就是自然人语言描述和结构化规则之间的差距。

**修复**：`_format_plan_metrics()` 补 4 行代码，把 `filter` 和 `default_time_field` 也写进 prompt。

**补充说明——旧链路其实没这个问题**：

`prompt.py` 里有两个指标格式化函数。旧 M4 的 `_format_metrics()` 已经正确注入了 `filter` 和 `default_time_field`：

```python
# _format_metrics() —— 旧 M4 路径，已正确实现 ✅
filter_text = f"；过滤条件：{metric.filter}" if metric.filter else ""
time_text = f"；默认时间字段：{metric.default_time_field}" if metric.default_time_field else ""
lines.append(f"- {metric.name}（{metric.key}）：{metric.formula}{filter_text}{time_text}。{metric.description}")
```

新 M11 的 `_format_plan_metrics()` 重写时漏掉了这两个字段：

```python
# _format_plan_metrics() —— 新 M11 路径，遗漏 filter/time_field ❌
lines.append(f"- {metric_key}（{name}）：{formula}。{description}")
```

所以这个 bug 只影响新 pipeline（QueryPlan 和局部 Schema SQL 两个 prompt 都会调用 `_format_plan_metrics()`）。

**信息流冗余（好的一面）**：修好后，filter/time_field 会**两次**注入 SQL 生成阶段——第一次在 QueryPlan prompt 里（LLM 应该写进 plan 的 `filters` 字段），第二次在 SQL prompt 里（直接作为局部指标描述）。即使 LLM 生成 QueryPlan 时没忠实复制 filter，SQL 生成时还有第二次机会看到它。

---

### 二、System Prompt 错配 ★（原 ★★→下调）

`generator.py` 的 `DeepSeekChatClient.complete()` 对**所有调用**使用同一个 system prompt：

```python
{"role": "system", "content": "你只负责把中文业务问题转换为安全的单条 SELECT SQL。"}
```

但实际有两个不同的任务：
- **QueryPlan 生成**：输出 JSON 格式的查询计划（不是 SQL）
- **SQL 生成**：输出 JSON，里面包含 SQL 语句

System prompt 和实际任务对不上。类比：你跟厨师说"你只负责炒菜"，然后递给他一张纸说"请先写一份菜单设计"。

**但也别高估它的影响**：各 user prompt 的第一句就已经写了正确的角色——QueryPlan prompt 开头是"你是 DataPilot 的 QueryPlan 规划器"，SQL prompt 开头是"你是 DataPilot 的局部 Schema SQL 生成器"。LLM 通常会优先遵循更近、更具体的 user 层指令。system prompt 错配更像一个"噪音源"而非致命错误——修了有益，但不要期望单独修它能明显提升通过率。

**修复**：让 `complete()` 支持传入 system prompt；QueryPlan 调用用"你是 DataPilot 的查询规划器"，SQL 生成用"你是 DataPilot 的 SQL 生成器"。建议和 Step 1 顺手一起改（改同一个文件 `generator.py`），不单独花时间验证效果。

---

### 三、`response_format: json_object` 可能压制 DeepSeek v4-pro 的 thinking ★★

DeepSeek v4-pro 是一个 **thinking/推理模型**。这类模型的正常工作是：先在内部做推理（thinking），再输出结论。

但当前代码强制了：

```python
"response_format": {"type": "json_object"}
```

很多推理模型在强制 JSON 模式时，会**跳过 thinking 阶段**，直接把结论输出为 JSON。这就像一个分析师被要求"不许在脑子里想，直接写结论"——对于 SQL 生成这种需要多步推理的任务，质量会明显下降。

当前代码也只读了 `choices[0]["message"]["content"]`，忽略了可能存在的 `reasoning_content`。

**另外 `temperature=0` + `json_object` 组合**：有些模型在这个组合下会把所有注意力花在满足 JSON 格式上，SQL 内容质量反而下降。

**修复方向**（需要实验验证）：
- 方案 A：去掉 `response_format: json_object`，让 prompt 自己约束输出格式，保留 thinking
- 方案 B：如果必须保留 JSON 模式，改用 `deepseek-v4-flash`（非推理模型）
- 方案 C：保留 JSON 模式，但读取 `reasoning_content` 做诊断

**实验设计补充**：除了 A/B 对比 JSON vs 自由文本，**加一个对照组——旧链路（M4 `generate_sql()`）也用同一个 `json_object` 模式跑同样的问题**。如果旧链路结果也差，说明 JSON 模式是全局问题；如果旧链路结果明显更好，说明问题在别处（比如新链路的局部 Schema 信息量不足，而非 JSON 压制 thinking）。

---

### 四、Eval 评分体系问题

#### 问题 4：eval 不检查数据正确性 ★★★

GMV 返回 `{"gmv": null}`，eval 判了 **passed**。评分只看列名和文本包含关系，完全不检查数据值。

#### 问题 5：expected_columns 精确字符串匹配太脆弱

LLM 输出中文列名（`渠道`、`使用次数`），数据完全正确，eval 找不到英文字符串判 fail。

#### 问题 6：contains 检查既太松又太窄

GMV=NULL 也能 contains `gmv` → 误判 pass。但 `Aurora Noise Cancelling Headphones` 在 rows 里不在 answer 话术里 → 误判 fail。

---

### 五、Schema Retrieval 问题

#### 问题 7：关键表召回遗漏

`p3a_multi_002` 没召回 `products` 表。keyword + vector 偏向 `order_items` 的金额字段。

#### 问题 8：0 行结果缺乏区分

返回 0 行时不知道是 SQL 错了还是数据真没有。

---

### 六、Pipeline 层面

#### 问题 9：新链路评测时无模板兜底

旧链路模板 SQL 是人写的，已经规避了所有彩蛋。新链路裸奔面对彩蛋。这是设计意图，但对比时需要注意这个不对称。

#### 问题 10：LLM 失败时 trace 信息不足

只有 `llm_generation_error`，没有 prompt 长度、重试次数、超时阈值。

---

### 七、已修复（M12 过程中）

| 问题 | 位置 |
|---|---|
| DeepSeek API 废弃 `deepseek-chat` → `deepseek-v4-pro` | `generator.py` |
| 新 pipeline 绕过危险 SQL 预检 | `app/api/query.py` |
| plan validation 误判聚合表达式 | `planner.py` |

---

### 八、MetricDescription 静默丢弃 numerator / denominator ★★（潜伏型，不影响当前 eval）

`metrics.yaml` 里 `refund_rate` 等比例类指标定义了 `numerator` 和 `denominator`：

```yaml
refund_rate:
    formula: refund_count / order_count
    numerator: COUNT(DISTINCT refunds.id)
    denominator: COUNT(DISTINCT orders.id)
```

但 `MetricDescription`（[schema_loader.py:42-50](engine/nl2sql/schema_loader.py#L42-L50)）只建模了 6 个字段，**没有 `numerator` 和 `denominator`**。`_load_metrics()` 也只读 `name/formula/description/filter/default_time_field`，完全不碰这两个字段。

**影响**：formal 10 里没有退款率 case，所以当前评测没暴露。但比例类指标（退款率、转化率、优惠券使用率）的精确计算公式——涉及哪些表、COUNT DISTINCT 逻辑——被丢了。LLM 只能从 `formula: "refund_count / order_count"` 这个抽象表达式去猜，不知道 `refund_count` 其实是 `COUNT(DISTINCT refunds.id)`。

**修复方向**（二选一，等当前主线修复完成后再处理）：
- 方案 A：`MetricDescription` 补 `numerator`/`denominator` 可选字段，两个 `_format_*` 函数输出到 prompt
- 方案 B：如果认为 `formula` + `description` + `filter` 已经给够信息，就把 `numerator`/`denominator` 从 YAML 里删掉，避免死配置误导后续开发者

---

### 九、`orders.md` schema_desc 的 `order_status` 取值说明不完整 ★★（潜伏型）

[orders.md:18](domain_pack/schema_desc/orders.md#L18) 把 `order_status` 的合法值描述为：

```
paid / shipped / delivered / cancelled
```

只有 `cancelled`（双 l）。但同一文件底部的"数据质量说明"又写了：

> 少量订单使用 `canceled` 单 l 拼写，统计取消订单时需要兼容。

`metrics.yaml` 的 filter **已经正确处理了两种拼写**：`NOT IN ('cancelled', 'canceled')`。但 schema_desc 是整条 prompt 链路的源头——LLM 读到 `order_status` 的字段含义时，只看到 `cancelled` 一种拼写。如果 LLM 根据 schema_desc 自己推导过滤条件（而不是直接抄 metrics 的 `filter`），就会漏掉 `canceled` 的数据。

本质上是信息在三个位置不一致：
| 位置 | cancelled（双 l） | canceled（单 l） |
|---|---|---|
| `orders.md` 字段说明 | ✅ 有 | ❌ 没有 |
| `orders.md` 数据质量说明 | ✅ 有 | ✅ 有 |
| `metrics.yaml` filter | ✅ 有 | ✅ 有 |

**修复方向**：`orders.md` 字段说明行补上 `canceled` → `paid / shipped / delivered / cancelled / canceled`。改动一行。

---

### 十、参考：AskData 两段式 + 不强制 JSON —— DataPilot 要不要看齐？ ★★

通过阅读 AskData 参考项目源码（`cot_planning/thinking_client.py`、`sql_generation/coder_client.py`、`cot_planning/cot_planner.py`、`askdata_pipeline/text2sql_pipeline.py`）：

#### AskData 的模型策略

**两个独立模型，都不强制 JSON 输出：**

| | Thinking Model | Coder Model |
|---|---|---|
| 用途 | CoT 四元组规划 | SQL 生成 |
| 默认模型 | `qwen-plus`（标准模型，非 reasoning） | `qwen-plus` |
| API | 阿里云 DashScope | 阿里云 DashScope |
| `response_format` | **不设**（自由文本） | **不设**（自由文本） |
| 解析方式 | 正则 `步骤N：(数据库:...处理对象:...操作指令:...输出目标:...)` | `clean_sql()` 正则提取 SQL |
| 温度 | 0 | 0 |
| Mock 降级 | 有 | 有 |

注意：AskData 的 "Thinking" 指的是 **CoT 输出格式**（让模型按"步骤1/步骤2"输出推理过程），不是模型的内部推理能力。`qwen-plus` 是标准大模型。

**AskData 不强制 JSON 的代价**：正则解析比 Pydantic 脆弱（格式偏差→空列表），没有 schema validation（编造表/字段要到 SQL 执行才暴露），换模型可能需调正则。

#### DataPilot 要不要全盘照搬？

**不建议。建议"部分对齐"——保留 QueryPlan 的 JSON 强制，只对 SQL 生成放开。**

| 资产 | 价值 | 丢掉可惜吗 |
|---|---|---|
| `QueryPlan` Pydantic schema + `validate_query_plan()` | 10+ 字段的结构化校验，拦截编造的表/字段/Join | 很可惜。M10 核心产出 |
| `extract_generated_sql()` | JSON + fenced SQL + 纯文本三层兼容 | 不用丢，已比 AskData 的 `clean_sql()` 更鲁棒 |
| `QueryPlanStep.filters` 字段 | 计划层过滤条件的结构化传递 | 改成自由文本就丢了 |

**分层策略**：

- **QueryPlan 生成：保持 `response_format: json_object`。** 需要严格校验，Pydantic 价值 > JSON 压制 thinking 的风险。结构固定，LLM 只需"填空"。
- **SQL 生成：去掉 `response_format: json_object`。** 创作型任务，强制 JSON 可能让模型花注意力在格式包装上。`extract_generated_sql()` 已有 fenced SQL 兜底。
- **暂不拆成两个模型。** AskData 拆模型是为了用不同规格（规划用强的、生成用快的）。DataPilot 只有一个 `deepseek-v4-pro`，拆了也没收益。等接入多 provider 再拆。

#### 对比总表

| | AskData | DataPilot 现状 | DataPilot 建议 |
|---|---|---|---|
| 规划输出格式 | 自由文本（四元组） | JSON（Pydantic） | **保持 JSON** |
| SQL 输出格式 | 自由文本 | JSON | **改为自由文本** |
| 模型数量 | 2 个（可不同模型） | 1 个 | **保持 1 个**（暂不拆） |
| 解析方式 | 正则 | Pydantic | **Pydantic（规划）+ fenced SQL（生成）** |
| system prompt | 各自独立 | 共用一条 | **各自独立**（v3 Step 2） |

#### AskData 的 trace/log 做法参考

AskData 的 `StepExecutionLog` 对每一步**完整保留输入原文和输出原文**，不做摘要。代价是 log 体积大，好处是排查不用复现。DataPilot 用摘要合理——但需确保关键字段（如 `plan_step.filters`）不被摘要掉。第 6 步的改进思路正是：摘要继续做，诊断关键字段原样保留在 metadata。

---

## 修改方案

### 第 1 步：接通 metrics → prompt 管道 ★★★ 最高优先级

**改什么**：`engine/nl2sql/prompt.py` 的 `_format_plan_metrics()`

**怎么改**：把 `filter` 和 `default_time_field` 也写进 prompt。

```python
# 改后
def _format_plan_metrics(domain_schema_metrics, schema_graph):
    lines = []
    for metric_key in schema_graph.metrics:
        metric = domain_schema_metrics.get(metric_key)
        if metric is None:
            continue
        name = getattr(metric, "name", metric_key)
        formula = getattr(metric, "formula", "")
        description = getattr(metric, "description", "")
        filter_rule = getattr(metric, "filter", "")       # ← 新增
        time_field = getattr(metric, "default_time_field", "")  # ← 新增

        line = f"- {metric_key}（{name}）：{formula}。{description}"
        if time_field:
            line += f" 时间过滤字段：{time_field}（必须用此字段做时间范围过滤）"
        if filter_rule:
            line += f" 附加过滤条件：{filter_rule}"
        lines.append(line)
    return "\n".join(lines) or "无"
```

**效果**：LLM 看到的 prompt 从：

```
- gmv（GMV）：SUM(orders.order_amount)。成交总额...
```

变成：

```
- gmv（GMV）：SUM(orders.order_amount)。成交总额...
  时间过滤字段：orders.paid_at（必须用此字段做时间范围过滤）
  附加过滤条件：orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL
```

**预计修复**：GMV、净收入、各渠道 GMV、商品销售额 Top5、已支付订单等 `paid_at` 相关失败。

**改动量**：~8 行。

---

### 第 2 步：修复 System Prompt ★

**改什么**：`engine/nl2sql/generator.py` 的 `DeepSeekChatClient.complete()`

**怎么改**：让 `complete()` 接受可选的 system prompt 参数。

```python
def complete(self, *, prompt: str, system_prompt: str = "") -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": self.model,
        "messages": messages,
        "temperature": 0,
        # response_format 暂时保留，等第 3 步实验后再决定
        "response_format": {"type": "json_object"},
    }
```

然后在调用处分别传入：
- QueryPlan：`system_prompt="你是 DataPilot 的查询规划器。根据用户问题和 Schema 信息输出结构化的 JSON 查询计划。"`
- SQL 生成：`system_prompt="你是 DataPilot 的 SQL 生成器。根据查询计划和局部 Schema 生成安全的只读 SELECT 语句。"`

**改动量**：~10 行。

---

### 第 3 步：实验验证 JSON 模式对 v4-pro 的影响 ★★

**目标**：确认 `response_format: json_object` 是否压制了 thinking 导致 SQL 质量下降。

**做法**：写一个快速 smoke 脚本，对同一组问题分别用"JSON 模式"和"自由文本模式"各跑一次，对比结果。

```python
# 实验设计
test_questions = [
    "2026 年 6 月 GMV 是多少？",
    "2026 年 6 月净收入是多少？",
]

# 方案 A：当前（json_object 模式）
# 方案 B：去掉 json_object，prompt 里自己约束格式
# 方案 C：json_object + 显式开启 thinking（如果 API 支持）
```

**如果发现去掉 json_object 后质量明显提升**，则：
- 保留 `response_format: json_object` 仅用于 QueryPlan（它需要严格 JSON）
- SQL 生成改为无 JSON 模式，依赖 `extract_generated_sql()` 的 fenced SQL 兼容提取

**如果质量没差别**，JSON 模式保留不动。

**改动量**：实验脚本 ~30 行；如果方案确认，改 `generator.py` ~5 行。

**精化实验设计——三组对照**（参考问题十中 AskData 的做法）：

| 组 | QueryPlan | SQL 生成 | 目的 |
|---|---|---|---|
| A（当前） | `json_object` | `json_object` | 基线 |
| B | `json_object` | **无 json_object** | 验证"SQL 层放开 JSON 是否提升质量"（问题十建议方向） |
| C | **无 json_object** | **无 json_object** | 验证"全部放开是否更好" |

- 如果 B 组 SQL 质量明显好于 A 组 → 正式去掉 SQL 生成的 `json_object`
- 如果 C 组更好 → 考虑连 QueryPlan 也放开（但需先实现正则解析 QueryPlan 的 fallback）
- 如果三组没差别 → JSON 模式不是问题，恢复现状，问题在 schema/prompt 侧

---

### 第 4 步：升级 eval 为"执行结果对比" ★★★

**改什么**：`eval/run_eval.py` 的 `_score_case()`，新增 `result_match` check type。

在 eval case YAML 里补 `expected_sql`（已知正确的参考 SQL），评分时执行两条 SQL 比较结果集。

```yaml
- id: p3a_agg_001
  check:
    type: result_match
    expected_sql: |
      SELECT ROUND(SUM(o.order_amount), 2) AS gmv
      FROM orders o
      WHERE o.paid_at >= '2026-06-01'
        AND o.paid_at < '2026-07-01'
        AND o.order_status NOT IN ('cancelled', 'canceled')
```

**改动范围**：`eval/run_eval.py` + 3 个 YAML 补 `expected_sql`。

---

### 第 5 步：Schema Retrieval 召回优化 ★（原第 5 步→现第 5 步，原"补 expected_sql"已并入第 4 步）

修复个别 case 的表召回遗漏。调整 keyword_text 权重或增加表级关联召回。

**改动范围**：`engine/schema_retrieval/document_builder.py` 或 `retriever.py`。

---

### 第 6 步：trace 信息增强 ★

**当前状态**：LLM 调用失败时 trace 只有 `llm_generation_error`，以及 `input_summary` / `output_summary` 的摘要。排查时必须重新跑代码才能看到 prompt 内容和 LLM 原始输出。

**改进思路**：不改业务逻辑，只增量追加 trace step 的 `metadata` 字段。不改变 trace 结构，不影响 `compare_phase3a.py`。

#### 第 1 层：立即可做（每次 < 5 行）

**① LLM 调用时记录 prompt 长度。** 在 `query_plan` 和 `sql_generation` trace step 的 metadata 里加 `prompt_chars`。一眼判断"prompt 膨胀导致截断"还是"模型理解偏差"。

**② 失败时记录 LLM 原始返回的前 500 字符。** 在 metadata 里加 `raw_response_preview`。QueryPlan 解析失败时能立刻区分"JSON 模式被无视了（返回自由文本）"还是"JSON 结构不对（字段缺失）"。需要 `generator.py` 的 exception 携带 `raw_text`。

**③ 记录 token 用量。** 从 DeepSeek API 响应里读 `usage.prompt_tokens` / `usage.completion_tokens`，写入 trace step metadata 和 `CostInfo`。当前 `CostInfo` 的这两个字段永远为 0。

#### 第 2 层：后续值得做（各 < 15 行）

**④ 调试模式下 dump 完整 prompt 到文件。** 环境变量 `DUMP_PROMPTS=1` 时，把每次 LLM 调用的完整 prompt 写入 `.agent_work/temp/prompt-{step_name}-{trace_id}.txt`。

**⑤ SQL 生成 trace step 记录 plan_step 的关键字段。** metadata 里加 `plan_step_filters`、`plan_step_metrics`、`plan_step_joins`。区分"prompt 有 filter 但 LLM 没写进 plan" vs "plan 有 filter 但 SQL 没体现" vs "plan 根本没有 filter"。

**⑥ Schema Retrieval trace step 记录指标文档命中。** metadata 里加 `metric_doc_hits`（从 merged_hits 中筛出 `doc_type=metric_doc` 的 doc_id 列表）。判断"某指标没召回"还是"召回了但 pipeline 后面没用到"。

**改动范围**：`engine/nl2sql/pipeline.py`（trace step metadata 扩展）、`engine/nl2sql/generator.py`（exception 携带 raw_text、读 usage）。

#### 不改的理由（列出但不实施）

| 不记什么 | 原因 |
|---|---|
| 完整 prompt 文本到 JSONL trace | 会让 trace 文件膨胀 10x，且 prompt 可能含敏感 schema 信息 |
| LLM 响应的完整 JSON | 同上；`raw_response_preview`（500 字符）足够诊断 |
| 每次重试的详情 | 当前无重试逻辑；加上重试后再考虑记录 |
| 数据库返回的完整 rows | 已在 `sql_execution` trace step 中有 `row_count` 和 `column_count`；完整数据走 `AgentResponse.rows` |

---

## 优先级总览

| 优先级 | 做什么 | 解决什么 | 改动量 | 预计效果 |
|---|---|---|---|---|
| ★★★ | 接通 metrics → prompt 管道 | `paid_at` 彩蛋导致的 ~50% 失败 | ~8 行 | 最明显 |
| ★★★ | eval 最小修复：新增 `expected_value` check + 改 YAML | **测量工具不准——当前 NULL 也判 pass，修了管道看不出效果** | ~20 行 + 改几条 YAML | 让修复效果可见 |
| ★★★ | eval：完整 `result_match`（双 SQL 执行对比） | 测量工具不准（比 expected_value 更完整） | 中 | 修复测量 |
| ★★ | 实验 JSON 模式影响（三组对照） | thinking 被压制 + SQL 格式负担 | 实验 ~30 行 | 待验证 |
| ★ | 修复 system prompt（和 Step 1 顺手改） | 模型困惑（有限） | ~10 行 | user prompt 已部分补偿 |
| ★ | trace 信息增强（①~⑥ 分层） | LLM 调试效率 | ~20 行 | 排查提速 |
| ★ | Schema Retrieval 召回优化 | 个别表遗漏 | 小 | 个别 case |
| 💤 | 补 numerator/denominator 或清理 YAML 死配置 | 比例类指标计算细节丢失 | 小 | 待定（不影响当前 eval） |
| 💤 | `orders.md` order_status 补 `canceled` | schema_desc 信息不完整 | 1 行 | schema_desc 源头修正 |

> **改动说明**（v4 修订）：第 6 步 trace 增强从一句话展开为分层方案（①~⑥），但不提高优先级（仍是 ★）。新增"问题十"——AskData 两段式 + 不强制 JSON 参考及部分对齐建议；结论是不全盘照搬，保留 QueryPlan 的 JSON 强制、只对 SQL 生成放开。问题三实验方案精化为三组对照（A/B/C）。

**`result_match` 的 fallback 设计**：优先用 `expected_sql` 做双 SQL 执行对比；如果没有 `expected_sql`，降级用"固定事实断言"——例如 `expected_value: {gmv: 11285752.00}`（Phase 2.7 已埋好的确定 seed 数值），直接比较 LLM SQL 的执行结果和预期值。

**建议执行顺序**：第 1 批 = 第 1 步（修 `_format_plan_metrics()` ~8 行）+ 顺便带第 2 步（修 system prompt ~10 行）+ **eval 最小修复（新增 `expected_value` check ~20 行 + 改几条 YAML）**。合计不到 50 行，三个改动互不阻塞。然后重跑 formal 10 条看数字——此时 eval 已能区分"SQL 列名对但数据错"和"真的对了"。如果 `paid_at` 问题消失但 SQL 质量仍差 → 做第 3 步实验（三组对照 A/B/C，优先验证 B 组"SQL 层放开 JSON"）。效果确认后做完整 `result_match`（双 SQL 执行对比），覆盖更多 case。

---

## 关键认知修正（v1 → v4）

| v1/v2/v3 判断 | v4 修正/补充 |
|---|---|
| "metrics 没有注入 prompt，需要扩展 metrics.yaml" | **metrics.yaml 已经写得很完整了**，是 `_format_plan_metrics()` 没读。旧 `_format_metrics()` 早就正确——rewrite regression |
| "需要给 LLM 写说明书" | **说明书已经有了**，是管道断了。不是设计问题，是实现遗漏 |
| "GMV 时间字段用错是 LLM 的 bug" | 不是 bug。LLM 的 prompt 里没收到 `default_time_field`，只能猜 |
| "主要问题是别名漂移" | 别名漂移占比很小。**管道断裂** 和 **数据质量彩蛋** 才是主因 |
| "system prompt 没大问题" | system prompt 和实际任务**完全对不上**，但 user prompt 已部分补偿，影响被高估 |
| "整个项目都忘了注入 filter/time_field" | **只有新 pipeline 的 `_format_plan_metrics()` 漏了**。旧 M4 早已正确注入 |
| "AskData 做法可能更好，要照搬吗" | **不全盘照搬**。保留 QueryPlan 的 JSON（Pydantic 校验价值大），SQL 层放开 JSON（创作型 + 已有 fenced SQL 兜底），暂不拆两模型 |
| "trace 信息够用了" | **不够**。失败时看不到 prompt 长度、LLM 原始返回、token 用量、plan_step 关键字段。分层补齐 ①~⑥ |

---

## 相关文件速查

| 用途 | 路径 |
|---|---|
| **prompt 构建（管道断裂位置）** | `engine/nl2sql/prompt.py` → `_format_plan_metrics()` |
| **LLM 客户端（system prompt + JSON 模式）** | `engine/nl2sql/generator.py` → `DeepSeekChatClient.complete()` |
| **指标定义（数据已有，管道没接）** | `domain_pack/metrics.yaml` |
| **pipeline 编排（trace step 构造处）** | `engine/nl2sql/pipeline.py` |
| trace step 定义 | `engine/trace/recorder.py` → `TraceStep` |
| eval 评分逻辑 | `eval/run_eval.py` → `_score_case()` |
| plan 校验 | `engine/nl2sql/planner.py` |
| Schema 检索 | `engine/schema_retrieval/retriever.py` |
| Schema 文档构建 | `engine/schema_retrieval/document_builder.py` |
| 关系定义 | `domain_pack/schema_desc/relations.yaml` |
| **orders schema_desc（order_status 值不完整）** | `domain_pack/schema_desc/orders.md` |
| **MetricDescription 定义（缺 numerator/denominator）** | `engine/nl2sql/schema_loader.py` → `MetricDescription` |
| Phase 2.7 数据库详情 | `docs/database-current-state.md` |
| **AskData Thinking Client（参考）** | `references/askdata_agent/cot_planning/thinking_client.py` |
| **AskData Coder Client（参考）** | `references/askdata_agent/sql_generation/coder_client.py` |
| **AskData Pipeline 两段串联（参考）** | `references/askdata_agent/askdata_pipeline/text2sql_pipeline.py` |
| v1 问题分析（已过时→v4） | `docs/phase3a-issues-and-fixes.md` |
| v2 问题分析（已过时→v4） | `docs/phase3a-issues-and-fixes-v2.md` |
| v3 问题分析（已过时→v4） | `docs/phase3a-issues-and-fixes-v3.md` |

---

## 本文档修订记录

> v4 基于 v3 全部内容，新增第 6 步 trace 分层方案、问题十（AskData 参考）、三组对照实验设计。

### 2026-07-25：源码复核 + 补充潜伏问题（v3 内修订）

**背景**：用户要求通读全部源码（pipeline、prompt、generator、schema_retrieval、eval、domain_pack），判断 v3 分析是否有遗漏。复核确认 v3 覆盖了影响当前通过率的主要问题，并发现两个潜伏型问题。

**修订内容**：

| 类别 | 改动 | 位置 |
|---|---|---|
| 精度修正 | "致 AI"第 1 句补"旧 M4 `_format_metrics()` 早已正确实现，新 pipeline 重写时漏掉——rewrite regression" | 致 AI |
| 精度修正 | "问题一"补旧 `_format_metrics()` vs 新 `_format_plan_metrics()` 代码对比，补充信息流冗余分析（filter/time_field 两次注入 SQL 生成阶段） | 问题一 |
| 优先级调整 | "问题二"system prompt 错配从 ★★ 下调为 ★，补"user prompt 已部分补偿，不是致命问题"的判断 | 问题二、优先级表 |
| 实验设计 | "问题三"实验方案补旧链路对照组，排除"JSON 模式是全局问题"的混淆变量 | 问题三 |
| 结构优化 | 优先级表 Step 4+5 合并（"补 expected_sql"是实现 `result_match` 的前置，不应独立成步）；新增 `result_match` 的固定事实断言 fallback 方案 | 优先级表 |
| 补充发现 | 新增"问题八"：`MetricDescription` 静默丢弃 `metrics.yaml` 的 `numerator`/`denominator` 字段 | 问题八 |
| 补充发现 | 新增"问题九"：`orders.md` schema_desc 的 `order_status` 取值说明只列了 `cancelled`（双 l），漏了 `canceled`（单 l） | 问题九 |
| 补充发现 | "关键认知修正"表新增两行：system prompt 影响被高估 / rewrite regression 定性 | 关键认知修正 |

### 2026-07-25：数据库实地验证彩蛋

**背景**：用户要求直接查询 MySQL `datapilot_dev` 验证 Phase 2.7 数据质量彩蛋的实际情况。此前 v3 的彩蛋描述来自文档推导，未实际查库。

**实际查询结果与修正**：

| 彩蛋 | 原描述 | 查库后发现 |
|---|---|---|
| `paid_at IS NULL` | "部分订单创建了但未支付" | 精确为 20 条，状态全部为 `pending_payment`。**不存在 `unpaid` 状态**——验证了 v3 的核心论点：LLM 猜 `order_status = 'unpaid'` 一定是错的 |
| 拼写差异 | "两种拼写共存" | `cancelled` 421 条 + `canceled` 8 条 = 429 条。单 l 只占 1.9%，但确实存在 |
| 弱关联退款 | "部分退款通过 `source_order_no` 关联" | **描述不够精确**：`source_order_no` 格式为 `SRC-2026-XXXXX`，`order_no` 格式为 `ORD-2026-XXXXX`——**两者是完全不同的命名空间，不能 join**。正确关联方式只有 `refunds.order_id -> orders.id` |
| 整单退款 | **原文档未提及** | 1000 条退款中 100 条 `order_item_id IS NULL`（10%），只能通过 `order_id` 关联。INNER JOIN `order_items` 会丢 10% 退款 |
| 金额不一致 | "5 条" | 确认 5 条 |
| 重复源单号 | "重复" | 确认 10000 条中 9980 distinct（重复 20） |
| 负数退款 | "负值" | 确认 3 条 `-20.00`，状态为 completed / requested / rejected |
| SCD 价格 | "时间窗口" | 确认 150 行覆盖 50 商品，`valid_from` 2026-01 ~ 2026-07 |

**修订内容**：
- Phase 2.7 彩蛋表重写：每项补"实际数据"列和"LLM 易犯错误"列
- 新增 `pending_payment` 状态说明（LLM 猜 `unpaid` 的对照）
- 新增整单退款（`order_item_id IS NULL`）作为独立彩蛋行
- 补关键数据速查行（order_status 分布、behavior events 分布）

**复核结论**：v3 的修复方案和优先级整体靠谱。第 1 步（改 `_format_plan_metrics()`，~8 行）是最高优先级，第 2 步（system prompt）可顺手改。两个新发现的潜伏型问题（💤）不影响当前 formal 10 评测，等主线修复完成后再处理。

### 2026-07-25：v3 → v4 迭代

**背景**：用户要求把"记录流程信息方便排查 bug"和"AskData 模型策略对比"写入迭代文档。同时用户指出 v1/v2 缺少废弃声明。

**修订内容**：

| 类别        | 改动                                                         | 位置         |
| ----------- | ------------------------------------------------------------ | ------------ |
| 标题与致 AI | 更新为 v4，补充 v3→v4 变化说明和 AskData 相关会话历史        | 标题、致 AI  |
| 展开方案    | 第 6 步 trace 增强从一句话展开为分层方案（①~⑥ + 不改的理由） | 第 6 步      |
| 新增参考    | 新增"问题十"：AskData 两段式 + 不强制 JSON 的详细对比及部分对齐建议 | 问题十       |
| 实验精化    | 第 3 步实验方案从 A/B 扩展为三组对照（A/B/C），引用问题十的分层策略 | 第 3 步      |
| 优先级表    | 第 6 步标注分层（①~⑥），第 3 步标注三组对照                  | 优先级表     |
| 认知修正    | 新增两行：不全盘照搬 AskData / trace 信息不够用              | 关键认知修正 |
| 文件速查    | 补 AskData 参考文件路径、pipeline.py 作为 trace 构造处、recorder.py | 相关文件速查 |
| 修订记录    | 本文档修订记录重构为层级结构（v3 两次修订 + v4 一次迭代）    | 修订记录     |

### 2026-07-25：eval 优先级调整（v4 内修订）

**背景**：用户要求评估 v4 修复文档的分析和优先级是否靠谱，并指出 eval 修复不应放在第 4 步——不先修测量工具就修管道等于盲飞。

**修订内容**：

| 类别       | 改动                                                         | 位置                       |
| ---------- | ------------------------------------------------------------ | -------------------------- |
| 优先级调整 | eval 最小修复（`expected_value` check）从"第 4 步"提前到"第 1 批"，和管道修复同步做 | 优先级总览表、建议执行顺序 |
| 精度修正   | "致 AI"第 3 句补"eval 最小修复必须和管道修复同步做——否则 `contains: gmv` 连 NULL 都判 pass" | 致 AI                      |
| 结论更新   | "用户已确认的结论"eval 相关两条重写：明确 `expected_value` 代价 ~20 行 + 改几条 YAML，第 1 批合计不到 50 行 | 致 AI                      |
| 优先级表   | 新增 ★★★ 行 "eval 最小修复"，排在管道修复之后、完整 `result_match` 之前 | 优先级总览表               |
| 执行顺序   | 重写为 "第 1 批 = 管道修复 + system prompt + eval 最小修复"  | 建议执行顺序               |
