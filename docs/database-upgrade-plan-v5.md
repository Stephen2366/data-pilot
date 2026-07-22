# DataPilot 数据库升级计划 v5

> 目标：一次性将数据库升级为接近真实企业环境的 13 张业务分析表 + 1 张桥接表（14 张物理表），覆盖 6 个全新挑战维度，为 Phase 3A Text2SQL 深化提供有技术深度、但仍可验收的底座。
>
> v2 变化（vs v1）：取消两期分期，合并为一次迁移；删去 suppliers/inventory/campaigns/多币种（同质重复），新增 product_price_history（SCD Type 2）和 orders_wide（宽表选表策略）。
>
> v3 变化（vs v2）：采用 1 万级订单数据；将 Phase 3A 验收从 10 条改为 16 条分层用例；保留复杂数据库但区分“必须答对”和“困难诊断”；修正物理表数量、脏数据与外键/唯一约束冲突、orders_wide 全量快照策略和施工时间估算。

> v4 变化（vs v3）：新增 order_items 订单明细表，补齐真实电商订单粒度；将 16 条用例拆成“数据库挑战集”，Phase 3A 正式 regression 仍保留 10 条；补结构化 relations.yaml、paid_at 可空与 orders_wide 兼容、脏数据字段、SCD 数量口径和免运费券所需 shipping_amount。

> v5 变化（vs v4）：补齐执行前门禁问题。① 明确 seed reset 不依赖自增 ID 从 1 开始，固定事实优先用稳定业务键定位。② 修正 orders_wide DDL 的 category 索引字段，并把 snapshot_at / batch_id / source_updated_at 写入正式 DDL。③ 明确退款粒度：新增 refunds.order_item_id 可空外键，商品退款率优先按 order_item_id / product_id 兼容口径计算。④ 将数据库升级验收门和 Phase 3A trace_steps 验收门拆开。⑤ 扩展 relations.yaml 结构，支持粒度、桥接表、递归关系、时间窗口 JOIN 和聚合风险提示。⑥ 补充遗漏的协同修改文件和 seed summary 要求。

## 1. 为什么一步到位

### 1.1 两期方案的移植代价

如果分两期，第二期加表时会产生以下返工：

| 返工项 | 影响 | 工作量 |
|--------|------|--------|
| Schema Retriever 重新调优 | M9 的召回策略基于旧的表/字段集合 tuning，加新表后 recall 必然下降，需要重新调整 prompt、权重、召回策略 | 中 |
| Baseline 全部作废 | M8 在旧库跑的 baseline 报告、trace、通过率全部过期，需要重新跑 -> 重新对照 -> 重新写 M12 comparison 报告 | 高 |
| Regression cases 补丁 | 10 条 cases 需要扩展以覆盖新表场景，但旧 cases 在新库上可能行为变化（expected_tables 增加等） | 中 |
| QueryPlanStep 校验规则补丁 | 新增的 join path（如 order_coupons 的多对多）需要补校验规则 | 低 |

**核心浪费**：Schema Retriever + Baseline + Comparison 是 Phase 3A 最核心的三个交付物。两期意味着这三样都要做两遍。

### 1.2 一步到位的风险与应对

| 风险 | 现实评估 | 应对策略 |
|------|---------|---------|
| 初始准确率会很差 | **会的**。14 张物理表 + 订单头/明细粒度 + 多对多 + 递归 CTE + 宽表 vs 星型模型选择，LLM 一开始选表/选字段/选 join path 都会出错 | 这正是 Phase 3A 要解决的问题。低准确率 = 优化空间大 = 技术故事好 |
| seed 脚本复杂度失控 | 14 张物理表的 seed 约 1200~1500 行，但 7 张旧表的主逻辑不变 | 新增表各自独立函数，不耦合；固定事实和数据质量彩蛋集中管理 |
| Schema 描述文档工作量 | 7 个新 .md + 更新 products.md / orders.md / refunds.md | 每份文档按现有模板写，并用 relations.yaml 统一结构化关系，避免 M9 再解析散装自然语言 |
| 测试修复范围大 | 硬编码数字散落多处 | 统一用 EXPECTED_SEED_COUNTS 字典，测试引用一处 |

**核心逻辑**：准确率低不可怕——可怕的是准确率低但不知道从哪优化。Phase 3A 的 Schema Retriever、QueryPlanStep 自检、trace_steps 恰恰就是为了定位“为什么错了”。14 张物理表给这个诊断链路提供了充足的优化素材。

### 1.3 为什么不加全部（A+B）类表

B 类表（suppliers、inventory、campaigns、多币种）不加的理由不是“做不动”，而是它们不引入**新的技术维度**：

| B 类表 | 实际挑战 | 为什么不加 |
|--------|---------|-----------|
| suppliers + purchase_orders | 另一组“维表 + 事实表” | 和 orders/products 模式完全相同，纯增加表数量但不增加技术多样性 |
| inventory | 又一张事实表 | 和 orders 的查询模式类似（时间范围 + 聚合 + JOIN 维表） |
| marketing_campaigns | 归因分析 | 概念有趣但 seed 数据极难造出合理分布，且真正的归因需要多步骤 agent，Phase 3A 做不了 |
| 多币种/多时区 | JOIN + 乘法换算 | 概念简单（加 currency + exchange_rate 表 + 乘法），面试能讲但技术挑战薄 |

**设计原则**：每一张新表都必须引入一种“旧表没有的 SQL 生成难题”。本次新增的 7 张业务表 + 1 张桥接表各自承担不同挑战，比盲目堆 20 张模式重复的表，对 agent 的技术锻炼价值更高。

---

## 2. 升级前后对照

### 2.1 表结构全景

| 表 | 类型 | 来源 | 引入的挑战维度 |
|----|------|------|--------------|
| users | 维表 | 原有 | — |
| products | 维表 | 原有（改造：新增 category_id FK + 保留旧 category 字符串冗余列） | 字段歧义（category 字符串 vs category_id 外键） |
| channels | 维表 | 原有 | — |
| orders | 订单头事实表 | 原有（改造：新增 shipping_amount / discount_amount / actual_amount / source_order_no / external_order_no；paid_at 改可空） | 订单头 vs 订单明细、金额口径歧义、未支付订单 |
| **order_items** | **订单明细事实表** | **新增** | **一单多商品、商品维度聚合、订单头金额与明细金额一致性** |
| refunds | 事实表 | 原有（改造：新增 source_order_no + order_item_id 可空 FK） | 订单头退款 vs 明细退款、兼容旧 product_id 冗余字段 |
| tickets | 事实表 | 原有 | — |
| knowledge_docs | 文档表 | 原有 | — |
| **product_categories** | **层级维表** | **新增** | **递归 CTE、层级语义消歧** |
| **coupons** | **维表** | **新增** | **多对多关系（通过 order_coupons）** |
| **order_coupons** | **桥接表** | **新增** | **多对多 JOIN、金额口径（标价-优惠券=实付）** |
| **user_behavior_log** | **事件日志** | **新增** | **大表、漏斗分析、事件序列** |
| **product_price_history** | **SCD Type 2** | **新增** | **“当时价格 vs 现在价格”、时间窗口 JOIN** |
| **orders_wide** | **宽表（反范式）** | **新增** | **星型模型 vs 宽表的选择策略** |

**共 13 张业务分析表 + 1 张桥接表（order_coupons），即 14 张物理表。** `order_items` 是 v4/v5 相比 v3 最关键的变化：它把“订单”从一单一商品升级为真实的“订单头 + 多条商品明细”，后续商品维度 GMV、销量、退款率等查询默认应走明细表。

### 2.2 数据量对照

| 表 | 当前行数 | 升级后 | 倍数 |
|----|---------|--------|------|
| users | 50 | 200 | 4x |
| products | 30 | 50 | 1.7x |
| channels | 6 | 6 | — |
| orders | 500 | 10,000 | 20x |
| order_items | — | ~18,000 | 新增（平均每单 1.8 个商品） |
| refunds | 80 | 1,000 | 12.5x |
| tickets | 120 | 300 | 2.5x |
| knowledge_docs | 8 | 10 | — |
| product_categories | — | ~15 | 新增 |
| coupons | — | 10 | 新增 |
| order_coupons | — | ~3,000 | 新增 |
| user_behavior_log | — | 10,000 | 新增 |
| product_price_history | — | ~150 | 新增 |
| orders_wide | — | 10,000 | 新增（与 orders 订单头全量同步） |

**数据量口径**：v5 选择 1 万级订单，不上 2 万。这个规模足够支撑“非 toy 数据集”和面试中的一万级数据量讲法，同时不会让 seed、pytest 和本地 smoke 变成主要成本。`order_items` 约 1.8 万行，用来体现订单粒度；`user_behavior_log` 同样设为 1 万行，作为事件日志大表的代表。后续如果要展示事件流压力，可以单独扩到 2 万行，不影响订单主事实表。

### 2.2.1 Seed reset 与 ID 策略

当前 MySQL 开发库已经多次 reset，Navicat 中看到的 `id` 不一定从 1 开始，这是正常现象。v5 明确要求：**seed 逻辑不能依赖自增 ID 从 1 开始**。

**执行规则**：
- Seed 构造外键时优先使用 ORM 对象关系或插入后真实 `id`，不要写死 `channel_id=1`、`product_id=1`、`category_id=1`。
- 固定业务事实优先用稳定业务键定位：`sku`、`coupon_code`、`channel_name`、`category.name`、`device_type`，不要用自增主键定位。
- 文档中的类目树 `id=1...15` 只是逻辑示意，不代表真实数据库必须插入这些 ID。
- MySQL `--reset` 若使用 `DELETE`，需要接受自增 ID 继续增长；若为了截图或人工检查希望 ID 从 1 开始，可在安全确认后使用 `TRUNCATE` 或显式重置 `AUTO_INCREMENT`。
- SQLite 自动化测试如果需要稳定 ID，可在测试 reset 后清理 `sqlite_sequence`；但主路径仍应避免依赖具体 ID。
- Seed 结束后生成 `seed_summary`（返回值 + 可选写入 `.agent_work/temp/database-upgrade-seed-summary.md`），记录实际行数和 9 个固定事实的真实值，测试断言引用该事实摘要或同一套查询函数。

### 2.3 固定业务事实

升级后的 seed 仍必须保留一组固定业务事实，作为 M8-M12 eval、smoke 和面试演示的锚点。建议至少固化以下事实：

| 编号 | 固定事实 | 用途 |
|------|----------|------|
| FACT-01 | 2026 年 6 月 GMV 有稳定数值，且默认排除 `cancelled/canceled` 和 `paid_at IS NULL` 订单 | 核心指标回归 |
| FACT-02 | Aurora Noise Cancelling Headphones 仍是 6 月退款率最高商品 | 继承阶段二锚点，验证新库不破旧能力 |
| FACT-03 | Mobile App 仍是 6 月 GMV 最高渠道或订单量 Top 渠道 | 继承阶段二锚点，验证渠道聚合 |
| FACT-04 | 固定券 `JUNE_FIXED_50` 在 `Mobile App` 渠道使用率最高 | 验证 coupons / order_coupons 桥接表 |
| FACT-05 | `数码电子` 一级类目 GMV Top，且包含 `电脑办公` / `智能穿戴` 等子类目贡献 | 验证 product_categories 类目关系 |
| FACT-06 | `Aurora Noise Cancelling Headphones` 在 6 月存在稳定历史均价 | 验证 product_price_history SCD 查询 |
| FACT-07 | `mobile_app` 设备类型加购到支付转化率最高 | 验证 user_behavior_log 漏斗查询 |
| FACT-08 | orders_wide 与星型模型在“各渠道 GMV”上默认结果一致 | 验证宽表选择策略 |
| FACT-09 | `orders.order_amount` 与 `SUM(order_items.line_amount)` 默认一致，少量 DQ 彩蛋故意不一致 | 验证订单头/明细金额校验 |

固定事实的目标不是让数据变假，而是保证复杂 seed 在每次重置后仍能产出可解释、可复现的验收答案。执行时必须把 9 个事实的**实际查询结果**写入 seed summary，避免计划文档里的业务描述和测试硬编码值分裂。

### 2.4 指标口径单一事实源

复杂 schema 里最大的风险不是表多，而是同一个业务词有多个候选字段。v5 要求在 `domain_pack/metrics.yaml` 和对应 `schema_desc/*.md` 中明确以下默认口径：

| 业务词 | 默认口径 |
|--------|----------|
| GMV | `SUM(orders.order_amount)`，默认排除 `order_status IN ('cancelled', 'canceled')` 且 `paid_at IS NOT NULL`；GMV 默认不含运费、不扣优惠 |
| 商品维度 GMV / 商品销售额 | 默认使用 `SUM(order_items.line_amount)`，并通过 `order_items -> orders` 套用已支付和未取消过滤；如果问题是订单级总 GMV，才使用 `orders.order_amount` |
| 净收入 / 实付金额 | 优先使用 `SUM(orders.actual_amount)`；默认公式为 `order_amount + shipping_amount - discount_amount`；`discount_amount` 包含商品优惠和免运费抵扣，避免再重复扣减 |
| 优惠金额 | 订单级汇总看 `orders.discount_amount`，优惠券明细分析看 `order_coupons.discount_amount` |
| 运费 | `SUM(orders.shipping_amount)`；GMV 默认不含运费，净收入 / 实付金额含运费 |
| 退款总额 | `SUM(refunds.refund_amount)`，保留负数冲销记录，不默认取绝对值 |
| 当前价格 | 优先使用 `products.price`；`product_price_history.is_current=1` 用于校验同步一致性 |
| 历史售价 / 当时价格 | 使用 `product_price_history.valid_from/valid_to` 做时间窗口匹配 |
| 宽表数据 | `orders_wide` 适合汇总看板；明细追溯和强一致问题回到规范化星型模型 |

### 2.5 Schema 关系事实源

Phase 3A M9 需要构建 `relation_doc` 和 `JoinPath`。v5 不再只依赖各表 Markdown 里的自然语言关联说明，而是新增一个结构化事实源：

`domain_pack/schema_desc/relations.yaml`

建议格式：

```yaml
relations:
  - id: orders_user
    relation_type: foreign_key
    grain: order
    from_table: orders
    from_column: user_id
    to_table: users
    to_column: id
    cardinality: many_to_one
    join_type: inner
    when_to_use: 订单按用户、用户状态、用户角色分析时使用
    avoid_when: 只做订单级总量且不需要用户维度时不要 join users
    aggregation_warning: null
  - id: order_items_order
    relation_type: foreign_key
    grain: order_item_to_order
    from_table: order_items
    from_column: order_id
    to_table: orders
    to_column: id
    cardinality: many_to_one
    join_type: inner
    when_to_use: 商品维度 GMV、销量、订单明细追溯时使用
    avoid_when: 只做订单级 GMV 或订单量时优先直接查 orders
    aggregation_warning: join order_items 后统计订单量必须 COUNT(DISTINCT orders.id)，避免一单多商品放大订单数
  - id: orders_coupons
    relation_type: bridge
    grain: order_to_coupon
    from_table: orders
    from_column: id
    through_table: order_coupons
    through_from_column: order_id
    through_to_column: coupon_id
    to_table: coupons
    to_column: id
    cardinality: many_to_many
    join_type: left
    when_to_use: 优惠券使用率、优惠金额、券类型分析时使用
    avoid_when: 只计算 GMV 时不要 join coupons
    aggregation_warning: 一单可用多张券，统计订单量时必须 COUNT(DISTINCT orders.id)
  - id: product_category_tree
    relation_type: recursive_hierarchy
    grain: category
    from_table: product_categories
    from_column: parent_id
    to_table: product_categories
    to_column: id
    cardinality: many_to_one
    join_type: recursive_cte
    when_to_use: 查询一级类目及其所有子类目 GMV / 销量时使用
    avoid_when: 只按 products.category 冗余字符串做粗略展示时不要强行递归
    aggregation_warning: 递归展开后再 join products，避免只统计父类目直属商品
  - id: product_price_history_temporal
    relation_type: temporal
    grain: product_price_version
    from_table: product_price_history
    from_column: product_id
    to_table: products
    to_column: id
    cardinality: many_to_one
    join_type: inner
    temporal_condition: "target_time >= valid_from AND (target_time < valid_to OR valid_to IS NULL)"
    when_to_use: 查询历史售价、当时价格、指定月份平均售价时使用
    avoid_when: 查询当前标价时优先使用 products.price
    aggregation_warning: 每个商品同一时间点应只命中一个价格版本，测试需保证无重叠窗口
```

**落地规则**：
- 每条外键关系至少有一条 relation。
- `order_items -> orders -> users/products/channels`、`orders -> order_coupons -> coupons`、`refunds -> order_items/orders/products`、`products -> product_categories`、`products -> product_price_history` 必须覆盖。
- M9 的 relation_doc 直接从 `relations.yaml` 生成；各表 `.md` 继续负责字段含义、grain、when_to_use 和 data_quality_notes。

---

## 3. 新增表详细设计

### 3.1 product_categories（类目树）

**引入的挑战**：递归 CTE，这是 SQL 新手和 LLM 都容易出错的领域。

```sql
CREATE TABLE product_categories (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(80) NOT NULL,
    parent_id   INT NULL,
    level       TINYINT NOT NULL DEFAULT 1,
    sort_order  INT NOT NULL DEFAULT 0,
    status      VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_parent (parent_id),
    INDEX ix_level (level),
    FOREIGN KEY (parent_id) REFERENCES product_categories(id)
);
```

**Seed 数据（约 15 个节点，3 层）**：

```
数码电子 (id=1, parent=NULL, level=1)
  ├── 手机通讯 (id=2, parent=1, level=2)
  ├── 电脑办公 (id=3, parent=1, level=2)
  │   ├── 笔记本 (id=6, parent=3, level=3)
  │   └── 台式机 (id=7, parent=3, level=3)
  └── 智能穿戴 (id=4, parent=1, level=2)
家居生活 (id=5, parent=NULL, level=1)
  ├── 家纺 (id=8, parent=5, level=2)
  └── 厨具 (id=9, parent=5, level=2)
个护美妆 (id=10, parent=NULL, level=1)
  ├── 护肤 (id=11, parent=10, level=2)
  └── 彩妆 (id=12, parent=10, level=2)
户外运动 (id=13, parent=NULL, level=1)
  └── 露营装备 (id=14, parent=13, level=2)
SaaS 软件 (id=15, parent=NULL, level=1)
```

**Agent 挑战场景**：
- 用户问「数码电子类目的 GMV」→ agent 需要判断「数码电子」包含其所有子类目，生成递归 CTE
- 用户问「一级类目销售额排名」→ agent 需要理解 level=1 的过滤 + GROUP BY
- Schema 检索需要暴露「类目是层级概念、不是平铺列表」

**Products 表改造**：
- 新增 category_id INT FK → product_categories.id（多数商品指向 level=3 叶子类目）
- 保留旧 category VARCHAR(80) 字符串列为冗余（模拟历史遗留：两个字段都在，agent 需要判断用哪个来 JOIN）

### 3.2 order_items（订单明细）

**引入的挑战**：真实订单粒度。阶段二的 `orders.product_id` 等价于“一单一商品”，面试里容易被看成 toy；v5 改为订单头 + 订单明细，让商品维度分析默认走明细表。

```sql
CREATE TABLE order_items (
    id                    INT PRIMARY KEY AUTO_INCREMENT,
    order_id              INT NOT NULL,
    product_id            INT NOT NULL,
    line_no               INT NOT NULL,
    quantity              INT NOT NULL DEFAULT 1,
    unit_price            DECIMAL(12,2) NOT NULL,
    line_amount           DECIMAL(12,2) NOT NULL,
    item_discount_amount  DECIMAL(12,2) NOT NULL DEFAULT 0,
    item_actual_amount    DECIMAL(12,2) NOT NULL,
    sku_snapshot          VARCHAR(64) NOT NULL,
    product_name_snapshot VARCHAR(160) NOT NULL,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_line (order_id, line_no),
    INDEX ix_order_items_product (product_id),
    INDEX ix_order_items_order_product (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

**Seed 数据（约 18000 行）**：
- 约 55% 订单 1 个商品，30% 订单 2 个商品，15% 订单 3 个商品。
- `orders.order_amount` 默认等于 `SUM(order_items.line_amount)`。
- `order_items.line_amount = quantity * unit_price`，表示商品标价金额；`item_discount_amount` 只表示可分摊到明细的商品级优惠，默认不把免运费券重复分摊到商品明细。
- `orders.actual_amount` 默认等于 `orders.order_amount + shipping_amount - discount_amount`；如 seed 做商品级优惠分摊，必须保证 `SUM(order_items.item_actual_amount) + shipping_amount - free_shipping_discount = orders.actual_amount`。
- 保留少量订单头/明细金额不一致彩蛋，进入 DQ-04。

**Orders 表兼容策略**：
- 继续保留 `orders.product_id`，但语义改为 `primary_product_id` / 兼容字段，默认指向订单第一条明细商品。
- Phase 2 旧模板 SQL 可以继续跑，避免 M6 baseline 被数据库升级直接打断。
- Phase 3A 新链路中，商品维度 GMV、销量、退款率默认优先走 `order_items`，只有订单级汇总才直接看 `orders`。

**Refunds 表兼容策略**：
- 新增 `refunds.order_item_id INT NULL`，指向 `order_items.id`，用于表达真实电商中“退某个订单明细”的粒度。
- 继续保留 `refunds.product_id` 作为冗余快照 / 兼容字段；当 `order_item_id IS NOT NULL` 时，seed 必须保证 `refunds.product_id = order_items.product_id`。
- 少量整单退款或历史退款允许 `order_item_id IS NULL`，此时继续通过 `refunds.order_id` 和 `refunds.product_id` 兼容旧查询。
- 商品退款率默认口径：分子优先按 `refunds.order_item_id -> order_items.product_id` 归因，兼容 `order_item_id IS NULL` 时使用 `refunds.product_id`；分母使用同一时间窗内 `order_items` 的订单明细或 `COUNT(DISTINCT orders.id)`，按问题中的“退款件数 / 退款订单数”区分。

**Agent 挑战场景**：
- 用户问「商品销售额」→ 需要走 `order_items`，不是只看 `orders.product_id`。
- 用户问「订单量」→ 需要 `COUNT(DISTINCT orders.id)`，不能被多条明细放大。
- 用户问「销量」→ 需要 `SUM(order_items.quantity)`，不是 `COUNT(orders.id)`。
- 用户问「订单金额是否准确」→ 需要对比订单头金额和明细金额汇总。

### 3.3 coupons + order_coupons（优惠券体系）

**引入的挑战**：多对多关系 + 金额口径爆炸。

```sql
CREATE TABLE coupons (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    coupon_code      VARCHAR(32) NOT NULL UNIQUE,
    coupon_type      VARCHAR(24) NOT NULL,
    discount_value   DECIMAL(12,2) NOT NULL,
    min_order_amount DECIMAL(12,2) NULL,
    valid_from       DATETIME NOT NULL,
    valid_to         DATETIME NOT NULL,
    status           VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_valid_range (valid_from, valid_to),
    INDEX ix_type (coupon_type)
);

CREATE TABLE order_coupons (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    order_id        INT NOT NULL,
    coupon_id       INT NOT NULL,
    discount_amount DECIMAL(12,2) NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_coupon (order_id, coupon_id),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (coupon_id) REFERENCES coupons(id)
);
```

**Seed 数据**：
- 10 张优惠券：4 张满减（fixed）、3 张折扣（percentage）、2 张免运费（free_shipping）、1 张新人专享
- 约 30% 的订单（~3000 单）使用优惠券
- 2 张券已过期，且少量订单关联了过期券（模拟业务漏洞）
- 部分订单使用多张券（满减 + 免运费叠加）
- 免运费券只抵扣 `orders.shipping_amount`，不抵扣商品 GMV

**Orders 表改造**：
- `paid_at` 改为可空：未支付订单允许落库，GMV 默认排除 `paid_at IS NULL`
- 新增 `source_order_no` / `external_order_no` VARCHAR(64) NULL：模拟源系统单号和逻辑重复
- 新增 `shipping_amount` DECIMAL(12,2) NOT NULL DEFAULT 0 — 运费字段，支持免运费券口径
- 新增 discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0 — 该订单的优惠券抵扣总额（冗余字段）
- 新增 actual_amount DECIMAL(12,2) NOT NULL — 实付金额 = order_amount + shipping_amount - discount_amount

**Agent 挑战场景**：
- 用户问「GMV」→ agent 必须知道 GMV = SUM(order_amount)，不是 SUM(actual_amount)
- 用户问「净收入」→ 需要选择 actual_amount 或 order_amount - SUM(discount_amount)
- 用户问「优惠券使用率最高的渠道」→ orders → order_coupons → coupons 三表 JOIN
- 金额字段多义：order_amount / discount_amount / actual_amount / refund_amount
- discount_amount 冗余不一致：orders.discount_amount（汇总）vs SUM(order_coupons.discount_amount)（明细聚合），两个值可能不一致，agent 该信哪个？
- 免运费券抵扣的是 `shipping_amount`，不是商品 `order_amount`，避免 GMV 被错误扣减
 
**金额一致性规则**：
- `order_coupons.discount_amount` 是优惠券实际抵扣金额，包含满减、折扣和免运费抵扣。
- `orders.discount_amount` 是订单级冗余汇总，默认等于 `SUM(order_coupons.discount_amount)`；少量 DQ 彩蛋可以不一致。
- `orders.actual_amount = order_amount + shipping_amount - discount_amount` 是净收入 / 实付金额主口径。
- 不要在净收入里同时扣 `orders.discount_amount` 和 `SUM(order_coupons.discount_amount)`，除非问题明确要求做一致性校验。

### 3.4 user_behavior_log（用户行为日志）

**引入的挑战**：事件序列分析 + 大表感 + 漏斗查询。

```sql
CREATE TABLE user_behavior_log (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id     INT NOT NULL,
    event_type  VARCHAR(32) NOT NULL,
    target_type VARCHAR(32) NULL,
    target_id   VARCHAR(128) NULL,
    session_id  VARCHAR(64) NOT NULL,
    event_time  DATETIME NOT NULL,
    duration_ms INT NULL,
    device_type VARCHAR(24) NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_user_event_time (user_id, event_time),
    INDEX ix_event_type_time (event_type, event_time),
    INDEX ix_session (session_id)
);
```

**Seed 数据（约 10000 行，30 天）**：
- view 60%、add_cart 20%、place_order 10%、pay 5%、search 5%
- 制造 10 个「高浏览零购买」用户（每人 20+ 次 view 但 0 次 place_order），供转化率分析
- 约 10% 记录 duration_ms IS NULL（模拟埋点采集缺失）

**Agent 挑战场景**：
- 用户问「上周浏览了耳机但没下单的用户有多少」→ view 事件 + NOT EXISTS（同一用户的 place_order），不是简单 COUNT + GROUP BY
- 用户问「加购到支付的转化率」→ 需要窗口函数或自 JOIN 串联同一 session 内的行为序列
- 用户问「哪个设备类型的转化率最高」→ 按 device_type 分组 + 漏斗计算
- 「平均浏览时长」→ duration_ms 存在 NULL，AVG 自动跳过但 agent 需要知道
- Schema Retriever 需要理解这是「事件表」、不是「实体表」：event_time vs created_at vs paid_at

### 3.5 product_price_history（SCD Type 2 价格历史）

**引入的挑战**：缓慢变化维度——「当时的价格 vs 现在的价格」。

```sql
CREATE TABLE product_price_history (
    id            INT PRIMARY KEY AUTO_INCREMENT,
    product_id    INT NOT NULL,
    price         DECIMAL(12,2) NOT NULL,
    valid_from    DATETIME NOT NULL,
    valid_to      DATETIME NULL,
    is_current    TINYINT(1) NOT NULL DEFAULT 1,
    change_reason VARCHAR(64) NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_product_current (product_id, is_current),
    INDEX ix_product_valid (product_id, valid_from, valid_to),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

**Seed 数据（约 150 行，50 个商品 x 平均 3 个历史版本）**：
- 每个商品有 2~5 个价格版本，覆盖过去 6 个月
- 锚点商品 Aurora Headphones：899 → 799（促销）→ 899（恢复）→ 849（永久降价）
- 部分 SaaS 商品只有涨价历史，没有降价（模拟真实）
- is_current = 1 的价格和 products.price 一致（冗余），但刻意让 1~2 个商品不一致（模拟数据同步延迟）
- 测试必须保证每个商品恰好一条 `is_current = 1`；DQ-10 只制造 `products.price` 与 current history 不一致，不制造多条 current

**Agent 挑战场景**：
- 用户问「Aurora 耳机现在的价格是多少」→ 查 products.price 还是 product_price_history WHERE is_current=1？
- 用户问「6 月的平均售价」→ SCD Type 2 经典查询：WHERE valid_from <= date AND (valid_to > date OR valid_to IS NULL)
- 用户问「历史订单金额是否要按当时价格重新计算」→ 架构级理解：orders.order_amount 已经是下单时锁定价格
- **面试讲法**：数仓中「缓慢变化维度（SCD）Type 2」经典实现，用 valid_from/valid_to 区间 + is_current 标志位

### 3.6 orders_wide（宽表 / 反范式视图）

**引入的挑战**：多表源选择——agent 需要在规范化星型模型和反范式宽表之间做出选择。

```sql
CREATE TABLE orders_wide (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    order_id        INT NOT NULL UNIQUE,
    order_no        VARCHAR(64) NOT NULL,
    source_order_no VARCHAR(64) NULL,
    order_status    VARCHAR(32) NOT NULL,
    order_amount    DECIMAL(12,2) NOT NULL,
    shipping_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    actual_amount   DECIMAL(12,2) NOT NULL,
    quantity        INT NOT NULL,
    item_count      INT NOT NULL DEFAULT 1,
    paid_at         DATETIME NULL,
    user_name       VARCHAR(80) NOT NULL,
    user_role       VARCHAR(32) NOT NULL,
    primary_product_name VARCHAR(160) NOT NULL,
    primary_category     VARCHAR(80) NOT NULL,
    primary_product_price DECIMAL(12,2) NOT NULL,
    channel_name    VARCHAR(120) NOT NULL,
    channel_type    VARCHAR(48) NOT NULL,
    refund_count    INT NOT NULL DEFAULT 0,
    total_refund    DECIMAL(12,2) NOT NULL DEFAULT 0,
    has_refund      TINYINT(1) NOT NULL DEFAULT 0,
    snapshot_at     DATETIME NOT NULL,
    batch_id        VARCHAR(64) NOT NULL,
    source_updated_at DATETIME NULL,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_paid_at (paid_at),
    INDEX ix_channel (channel_type),
    INDEX ix_category (primary_category),
    INDEX ix_status (order_status)
);
```

**Seed 数据**：与 orders 订单头全量同步生成（10000 行），通过 INSERT INTO ... SELECT 从 orders + users + products + channels + refunds + order_items 聚合写入。宽表是订单粒度，不展开成明细粒度；商品相关字段只保留 primary product 和 item_count，商品维度精确分析仍回到 `order_items`。

**宽表策略**：
- `orders_wide` 是“分析快照宽表”，不是权威交易源。
- `snapshot_at` / `batch_id` / `source_updated_at` 用于解释宽表的同步时间和延迟。
- 经营汇总、看板类问题可优先用宽表；强一致、明细追溯、退款实时口径优先回到星型模型。
- 不建议只同步 500 行样例数据，否则 agent 还要额外判断宽表数据不完整，噪音大于收益。
- `paid_at` 必须允许 NULL，因为 orders_wide 全量同步订单头，未支付订单不能因为宽表字段约束被丢掉。

**Agent 挑战场景**：
- 用户问「各渠道 GMV」→ agent 有两条路：
  - 方案 A：宽表单表查询（简单但数据可能延迟）
  - 方案 B：星型模型 JOIN（标准且实时）
  - 两条路结果应该一致，考验 agent 的**选表策略**
- 用户问「退款率最高的商品」→ 宽表已有 refund_count/total_refund，但口径可能与 refunds 表实时计算有微妙差异（模拟「宽表数据延迟」）
- **核心面试价值**：体现「数据仓库建模」中的经典权衡——星型模型（规范、无冗余、查询灵活）vs 宽表（反规范、有冗余、查询快）

---

## 4. 数据质量彩蛋设计

在 seed 脚本中刻意引入以下问题。多数问题使用固定小数量，目标是“可解释、可复现、能触发诊断”，不是严格按百分比造脏数据；事件日志这类大表可使用 1%~10% 的比例型缺失。

**约束原则**：主业务表仍保留外键和唯一约束，不为了制造脏数据破坏工程规范。真实企业的“乱”不等于完全无约束；本项目优先模拟那些能落库、能测试、能解释的数据质量问题。若要展示违反外键/唯一性的原始脏数据，后续可单独新增 `raw_import_*` 原始导入表，不放进本次主线。

| 编号 | 表 | 问题类型 | 具体表现 | 期望 Agent 行为 |
|------|-----|---------|---------|---------------|
| DQ-01 | orders | NULL 值陷阱 | 约 20 条订单 paid_at IS NULL（下单未支付） | 计算"GMV"时不纳入这些订单 |
| DQ-02 | orders | 逻辑重复 | 约 10 条订单共享同一个 `source_order_no` / `external_order_no`，但 `order_no` 仍保持唯一 | 使用业务源单号去重，而不是破坏主表唯一约束 |
| DQ-03 | orders | 不一致状态值 | 约 8 条订单 order_status = 'canceled'（单 l 拼写，正确是 cancelled） | 兼容处理，或至少不影响正常统计 |
| DQ-04 | orders / order_items | 金额不一致 | 约 5 条订单 `order_amount != SUM(order_items.line_amount)` 或 `actual_amount + discount_amount != order_amount + shipping_amount` | agent 算"实付"或校验金额时信哪个字段？ |
| DQ-05 | refunds | 弱关联记录 | 新增 `refunds.source_order_no`，约 5 条退款的源系统单号指向不存在的外部订单号，但 `order_id` 仍指向可落库订单 | 区分数据库外键关系和外部业务单号关系 |
| DQ-06 | refunds | 金额负数 | 约 3 条退款 refund_amount < 0（模拟修正冲销） | 计算"总退款额"时需要考虑负数场景 |
| DQ-07 | users | 已禁用用户有数据 | 约 4 个 status='disabled' 用户仍有订单 | 按用户筛选时是否过滤 disabled？ |
| DQ-08 | user_behavior_log | NULL 字段 | 约 10% 记录 duration_ms IS NULL | AVG(duration_ms) 自动跳过 NULL，但 COUNT 可能误算 |
| DQ-09 | products | 已停售商品有订单 | 约 3 个 status='paused' 商品仍有历史订单 | agent 需判断"当前在售"和"历史销售"是两个概念 |
| DQ-10 | product_price_history | 冗余不一致 | 1~2 个商品的 products.price != product_price_history WHERE is_current=1 的价格 | agent 需要决策以哪个为准 |

> **面试价值**：这 10 类彩蛋覆盖了数据质量问题的 5 大类型——完整性（NULL）、唯一性（重复）、一致性（状态值/金额/冗余）、参照完整性（孤儿记录）、准确性（负数），可以作为面试中展示"工程严谨性"的具体案例。

**实现注意**：
- 当前 `refunds.order_id` 若继续使用外键，则不能直接插入不存在的 `order_id`。
- 当前 `orders.order_no` 若继续使用唯一约束，则不能直接插入重复 `order_no`。
- v5 明确新增 `orders.source_order_no` / `orders.external_order_no` / `refunds.source_order_no` 来承载源系统脏数据，不破坏主表主键、外键和唯一约束。
- 因此 v5 将“物理约束冲突”改为“逻辑脏数据”：既保留工程边界，又能让 agent 面对真实业务里的源系统脏数据。

---

## 5. 对现有模块的影响分析

### 5.1 需要协同修改的文件

| 文件 | 改动 | 风险 |
|------|------|------|
| app/models/ | 新增 7 个模型文件 + 修改 products.py（加 category_id）+ 修改 orders.py（加 shipping_amount / discount_amount / actual_amount / source_order_no / paid_at nullable）+ 修改 refunds.py（加 source_order_no / order_item_id） | 中 |
| app/db/base.py + app/models/__init__.py | 导入并导出新增 ORM 模型，保证 Alembic metadata 和聚合导入可见 | 中 |
| app/schemas/resources.py | `OrderRead.paid_at` 改可空；按 API 展示需要补 shipping_amount / discount_amount / actual_amount；`RefundRead` 可补 source_order_no / order_item_id | 低 |
| alembic/versions/ | 新增 1 个 migration（全部 DDL 在一个版本中完成） | 低 |
| scripts/seed_data.py | 新表 seed + 1 万级数据量 + 固定业务事实 + 彩蛋逻辑 + orders_wide 全量同步写入 | **中**（最大改动点） |
| domain_pack/schema_desc/ | 新增 7 个 .md + 更新 products.md、orders.md、refunds.md，并补 grain / when_to_use / data_quality_notes | 低 |
| domain_pack/schema_desc/relations.yaml | 新增结构化表关系事实源，供 M9 直接构建 relation_doc / JoinPath；覆盖 bridge / recursive / temporal / aggregation_warning | 中 |
| domain_pack/metrics.yaml | 新增 NAR、优惠券使用率、转化率、漏斗指标等 | 低 |
| domain_pack/sql_examples/basic.yaml | 新增 5~8 条涉及新表的 few-shot SQL | 低 |
| eval/cases/database-upgrade-challenge.yaml | 新增 16 条分层数据库挑战用例（简单、核心指标、中等多表、困难诊断、安全），但数据库升级阶段只要求可加载和基础 SQL 结果稳定 | 中 |
| eval/cases/phase3a-regression.yaml | 保留 10 条 Phase 3A 正式回归用例，用于 v1 baseline vs 新 pipeline 对照 | 中 |
| eval/run_eval.py | 若要提前运行 challenge，需要兼容 challenge YAML 字段；Phase 3A 的 issue tags / trace_steps 字段仍放到 M8-M12 扩展 | 中 |
| engine/nl2sql/schema_loader.py | 当前只读取 `.md`；后续 M9 需读取 `relations.yaml` 生成 relation_doc，数据库升级阶段先保证 YAML 格式可被解析 | 中 |
| tests/test_m1_*.py | 更新表数量、seed 行数等硬编码断言 | 低 |
| tests/test_m2_api.py | products API 筛选参数可能调整（category 列仍保留所以改动小） | 低 |
| tests/test_m5_agent_response.py | 固定事实的硬编码值更新（新数据量下 GMV 等数值会变） | 低 |

### 5.2 不受影响的模块

- **M3 模板 SQL**：现有模板 SQL 涉及的表字段保留（category 列保留为冗余字段，orders.product_id 保留为 primary product 兼容字段，order_amount 列不变）
- **M4 NL2SQL / prompt**：_format_tables() 自动从 domain_pack 读取新表
- **M5 AgentResponse / Trace**：响应结构不变
- **M6 EvalOps-lite**：smoke 用例仍能运行（旧表字段不变）
- **M8~M12 Phase 3A**：Schema Retrieval / QueryPlanStep 本身就是针对最终 schema 设计，新表直接进入 scope

### 5.3 新旧库的 Phase 3A 策略

升级后 Phase 3A 的所有工作都基于新库（14 张物理表），不需要"先跑旧库 baseline 再跑新库"。但为了避免复杂度一次性压垮验收，Phase 3A 需要把“数据库挑战集”和“Phase 3A 正式回归集”分开。

| 用例集 | 文件 | 数量 | 用途 | 是否作为 Phase 3A 硬门 |
|--------|------|------|------|-------------------------|
| 数据库挑战集 | `eval/cases/database-upgrade-challenge.yaml` | 16 | 证明新库复杂度、固定事实、脏数据和困难诊断素材充足 | 否，作为数据库升级验收和诊断素材 |
| Phase 3A 正式回归集 | `eval/cases/phase3a-regression.yaml` | 10 | 跑 v1 baseline vs 新 Text2SQL pipeline 对照 | 是，沿用 `docs/phase3a-plan.md` 的主线验收口径 |

**同步要求**：数据库升级完成后，必须先小修 `docs/phase3a-plan.md`，把“新库已是默认底座”和“16 条 challenge 不替代 10 条 regression”写入单一事实源，避免 M8 开工时出现 10/16 口径冲突。

| Phase 3A 模块 | 调整 |
|--------------|------|
| M8 回归基线 | 在新库上跑 10 条正式 regression 的 v1 baseline，记录真实通过率；16 条 challenge 可同步跑报告，但不替代 M8 主口径 |
| M9 Schema Retrieval | 召回文档覆盖 14 张物理表的字段/指标/关系；relation_doc 直接来自 `relations.yaml`；expected_tables 要求覆盖新表 |
| M10 QueryPlanStep | 校验规则优先覆盖普通 JOIN、多对多 JOIN、金额口径和宽表选择；递归 CTE / 漏斗 / SCD 作为困难诊断能力纳入 |
| M11 新 Pipeline | force_new_pipeline 路径覆盖新表场景 |
| M12 对照报告 | **不再做旧库 vs 新库对照**；改为报告 v1 baseline vs Phase 3A 新 pipeline 在同一新库上的表现、局部 Schema prompt 的收敛效果、困难 case 的 trace_steps 和 issue tags |

---

## 6. 技术深度提升对照

### 6.1 面试场景

| 面试官可能问的 | 升级前（7 表） | 升级后（14 张物理表） |
|--------------|-------------|--------------|
| "你的 agent 怎么在十余张表中找对表？" | 才 7 张，不需要检索策略 | 14 张物理表 + 6 种不同表类型（维表/订单头事实/明细事实/桥接表/事件日志/宽表），能讲 Schema Retriever 的设计 |
| "SQL 生成怎么处理歧义？" | 几乎没有歧义 | 订单头 vs 明细、金额字段多义、类目层级、category 冗余列 vs category_id FK、宽表 vs 星型模型 |
| "怎么保证生成的 SQL 在脏数据上也能跑对？" | 数据太干净 | 10 类彩蛋覆盖完整性/唯一性/一致性/参照完整性/准确性 |
| "多对多关系怎么处理？" | 没有 | 订单-优惠券多对多 |
| "为什么订单要拆头表和明细表？" | 一单一商品，偏简化 | orders + order_items 体现真实订单粒度，商品维度分析不会被订单头字段误导 |
| "层级维度怎么查？" | 没有 | 递归 CTE |
| "缓慢变化维度是什么？你怎么处理？" | 没有 | SCD Type 2 价格历史 |
| "数据仓库建模中星型模型和宽表怎么选？" | 没有 | orders_wide 制造了这个选择 |
| "转化漏斗怎么用 SQL 实现？" | 没有 | user_behavior_log 事件序列分析 |
| "金额字段不一致怎么处理？" | 没有 | discount_amount 汇总 vs 明细聚合不一致 |

### 6.2 评测用例扩展

v5 将评测拆成两层：**16 条数据库挑战集**证明新库真实复杂，**10 条 Phase 3A 正式回归集**证明新 Text2SQL pipeline 相比 v1 baseline 的收益。核心思想是：困难 SQL 可以进入挑战集提供诊断素材，但不直接把 Phase 3A 主线验收压成“复杂 SQL 全能力攻坚”。

#### 6.2.1 数据库挑战集（16 条）

文件：`eval/cases/database-upgrade-challenge.yaml`。

| 类别 | 数量 | 通过要求 | 示例问题 | 涉及能力 |
|------|------|----------|----------|----------|
| 简单查询 | 3 | 3/3 通过 | "查询 active 商品列表前 10 条"、"查询 2026 年 6 月已支付订单" | 单表筛选、时间字段、基础列选择 |
| 核心指标 | 4 | 至少 3/4 通过 | "本月 GMV"、"各渠道订单量"、"退款率最高商品"、"本月净收入" | 指标口径、订单头/明细选择、金额字段选择、聚合 |
| 中等多表 | 4 | 至少 3/4 通过 | "满减券使用率最高的渠道"、"一级类目销售额排名"、"各渠道 GMV"、"商品销售额 Top 5" | JOIN、桥接表、类目维表、order_items、宽表 vs 星型选择 |
| 困难诊断 | 3 | 至少 1/3 结果正确；3/3 必须有完整 trace 和 issue tag | "数码电子及其子类目 GMV"、"加购到支付转化率"、"6 月各商品平均售价" | 递归 CTE、漏斗、SCD 时间窗口 |
| 安全 | 2 | 2/2 必须拦截 | `DROP TABLE orders`、`DELETE FROM refunds WHERE id = 1` | SQL Guard、RBAC 不绕过 |

**数据库升级阶段最低硬门（Phase 2.7）**：
- `database-upgrade-challenge.yaml` 可以被加载，16 条 case 的 question / expected_tables / expected_columns / check 字段完整。
- 安全：2/2 blocked，仍由现有 SQL Guard 验证，不要求新 pipeline。
- 简单查询：3/3 正确。
- 固定事实查询：FACT-01~FACT-09 的实际结果写入 seed summary，并有测试或 smoke 查询覆盖。
- 核心指标 + 中等多表：8 条中至少 6 条在当前 v1 链路或手写 expected SQL 下结果稳定。
- 困难诊断：3 条不要求当前 v1 链路答对，但必须有 expected SQL / 口径说明，作为 Phase 3A 诊断素材。

**Phase 3A 后续增强门（M11/M12）**：
- 困难诊断 3 条中至少 1 条结果正确。
- 3 条困难诊断都必须记录 `schema_retrieval`、`join_path`、`query_plan`、`plan_validation`、`sql_generation`、`sql_guard`、`sql_execution` 和明确 issue tag。
- 总体允许类 SQL：14 条中建议至少 10 条正确；若低于 10 条，先修 schema retrieval / plan validation / prompt，不通过删除困难 case 掩盖问题。

#### 6.2.2 Phase 3A 正式回归集（10 条）

文件：`eval/cases/phase3a-regression.yaml`。

这 10 条仍用于 M8-M12 主线验收：先跑 v1 baseline，再跑新 Text2SQL pipeline，最后生成 `phase3a-comparison.md`。建议构成仍沿用 `docs/phase3a-plan.md` 的 2 simple / 3 aggregation / 3 multi_table / 2 security；其中可以从 16 条 challenge 中挑选稳定且能体现新 schema 的 case，但不要把 3 条困难诊断题全部塞进正式硬门。

**Phase 3A 正式硬门**：
- 安全：2/2 blocked。
- 允许类 SQL：8 条中至少 7 条结果正确。
- Schema Retriever：expected_tables 命中率 100%，expected_columns / expected_metrics 不低于 80%。
- QueryPlanStep：10 条均有结构化 plan 和 trace；失败 case 必须有 issue tag。

> 具体 16 条 challenge 和 10 条 regression 的最终构成由数据库升级模块 / M8 分别固化；两者可以有重叠，但不是同一个验收文件。

---

## 7. 施工计划

### 7.1 执行顺序

```
步骤 1：新表模型 + Migration
  ├── app/models/product_categories.py
  ├── app/models/order_items.py
  ├── app/models/coupons.py
  ├── app/models/order_coupons.py
  ├── app/models/user_behavior_log.py
  ├── app/models/product_price_history.py
  ├── app/models/orders_wide.py
  ├── 更新 app/db/base.py 和 app/models/__init__.py（注册 / 导出新模型）
  ├── 修改 app/models/products.py（新增 category_id）
  ├── 修改 app/models/orders.py（paid_at 可空；新增 source_order_no / external_order_no / shipping_amount / discount_amount / actual_amount）
  ├── 修改 app/models/refunds.py（新增 source_order_no / order_item_id）
  ├── 修改 app/schemas/resources.py（paid_at 可空，必要金额字段补齐）
  └── alembic revision --autogenerate && alembic upgrade head

步骤 2：Schema 描述文档
  ├── domain_pack/schema_desc/product_categories.md
  ├── domain_pack/schema_desc/order_items.md
  ├── domain_pack/schema_desc/coupons.md
  ├── domain_pack/schema_desc/order_coupons.md
  ├── domain_pack/schema_desc/user_behavior_log.md
  ├── domain_pack/schema_desc/product_price_history.md
  ├── domain_pack/schema_desc/orders_wide.md
  ├── domain_pack/schema_desc/relations.yaml（结构化关系事实源）
  ├── 更新 products.md / orders.md / refunds.md
  └── 每份文档补 grain / default_time_field / when_to_use / avoid_when / data_quality_notes

步骤 3：Seed 脚本升级（最大工作量）
  ├── 旧表数据量放大（EXPECTED_SEED_COUNTS 更新：orders=10000）
  ├── reset 策略修正：不依赖自增 ID 从 1 开始，固定事实用业务键定位
  ├── 新表 seed 函数（按表拆分独立 _build_* 函数）
  ├── order_items 明细生成（平均每单 1.8 个商品，订单头金额默认等于明细汇总）
  ├── refunds.order_item_id 归因生成（多数退款指向订单明细，少量保留整单 / 历史兼容退款）
  ├── 固定业务事实锚定（GMV、商品维度销售额、退款率、渠道、优惠券、类目、SCD、漏斗、宽表）
  ├── seed_summary 输出（行数 + FACT-01~FACT-09 实际结果）
  ├── orders_wide 全量同步写入（INSERT INTO ... SELECT 聚合）
  ├── 数据质量彩蛋函数（_add_data_quality_quirks）
  └── products.category_id 关联 + category 冗余列填充

步骤 4：Metrics + SQL Examples 更新
  ├── metrics.yaml：新增 nar / coupon_usage_rate / conversion_rate / avg_selling_price 等
  ├── 明确 GMV / 商品维度 GMV / 净收入 / 运费 / 优惠金额 / 当前价格 / 历史售价 / 宽表默认口径
  └── basic.yaml：新增 5~8 条涉及新表的 few-shot SQL

步骤 5：测试更新
  ├── tests/test_m1_models.py：验证 14 张物理表均可创建
  ├── tests/test_m1_seed.py：更新 EXPECTED_SEED_COUNTS 和固定业务事实断言
  ├── tests/test_m2_api.py：category 筛选值更新
  └── tests/test_m5_agent_response.py：固定事实数值更新

步骤 6：全量验证
  ├── alembic downgrade && alembic upgrade head（验证迁移可逆）
  ├── python -m scripts.seed_data --reset（验证新 seed、1 万级数据量和固定事实）
  ├── python -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --report eval/reports/database-upgrade-challenge.md（验证 challenge 可加载、基础查询、安全和固定事实；不要求 Phase 3A trace_steps）
  ├── pytest 全量（验证无回归）
  └── 验证 9 个固定事实仍稳定
```

### 7.2 时间估算

| 步骤 | 预估时间 | 说明 |
|------|---------|------|
| 模型 + Migration | 1.5h | 7 张新表模型 + 3 张旧表修改 + DDL |
| Schema 描述文档 | 1.5h | 7 个新 .md + 3 个更新 + relations.yaml，并补 grain / when_to_use / data_quality_notes |
| Seed 脚本升级 | 4.0~5.0h | **最大工作量**：1 万级订单、1.8 万级明细、固定事实、新表 seed、彩蛋逻辑、orders_wide 全量同步 |
| Metrics + Examples | 0.75h | 新增指标 + 默认口径 + few-shot SQL |
| 测试更新 | 1.0~1.5h | 硬编码数字、固定事实、筛选值和 eval case 更新 |
| 全量验证 | 0.5~1.0h | pytest + seed + migration 可逆，视本机 DB 和 bulk insert 性能浮动 |
| **合计** | **约 1.5~2 天** | v5 增加订单明细、结构化关系和执行前门禁后更接近真实施工成本；4h 仅适合无固定事实、无脏数据、无完整验证的草稿实现 |

---

## 8. 待用户确认

1. **执行时机**：确认在 Phase 3A M8 之前做，作为 Phase 2.7 / 数据底座升级模块；这样 M8 baseline 直接在新库上跑。
2. **订单粒度**：v5 默认新增 `order_items`，并保留 `orders.product_id` 作为兼容字段；如果后续想进一步纯化模型，可在阶段三之后再考虑把旧兼容字段降级。
3. **products.category 改造**：默认保留冗余字符串列 + 新增 category_id FK，模拟历史遗留字段歧义。
4. **脏数据策略**：默认不破坏主表外键/唯一约束，采用 `source_order_no` / `external_order_no` 等逻辑脏数据；若后续要展示强脏数据，再新增 raw_import 表。
5. **评测口径拆分**：默认 16 条 `database-upgrade-challenge.yaml` 验证新库复杂度；10 条 `phase3a-regression.yaml` 继续作为 Phase 3A 正式新旧链路对照硬门。
6. **免运费券口径**：默认新增 `orders.shipping_amount`，免运费券只抵扣运费，不扣商品 GMV。
7. **自增 ID 策略**：默认不要求 MySQL reset 后 ID 从 1 开始；所有固定事实和外键构造都用业务键或插入后真实 ID。
8. **退款粒度**：默认新增 `refunds.order_item_id` 可空外键；兼容整单退款和历史 `product_id` 冗余字段。

---

> **关联文档**：
> - 阶段三A 计划：[phase3a-plan.md](phase3a-plan.md)
> - 技术档案：[AI_CONTEXT.md](AI_CONTEXT.md)
> - 总路线：[LEARNING_ROADMAP_v3.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP_v3.md)
> - v4 版：[database-upgrade-plan-v4.md](database-upgrade-plan-v4.md)
> - v3 版：[database-upgrade-plan-v3.md](database-upgrade-plan-v3.md)
> - v1 版（两期方案）：[database-upgrade-plan.md](database-upgrade-plan.md)
