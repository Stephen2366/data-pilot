# DataPilot 数据库升级计划 v3

> 目标：一次性将数据库升级为接近真实企业环境的 12 张业务分析表 + 1 张桥接表，覆盖 5 个全新挑战维度，为 Phase 3A Text2SQL 深化提供有技术深度、但仍可验收的底座。
>
> v2 变化（vs v1）：取消两期分期，合并为一次迁移；删去 suppliers/inventory/campaigns/多币种（同质重复），新增 product_price_history（SCD Type 2）和 orders_wide（宽表选表策略）。
>
> v3 变化（vs v2）：采用 1 万级订单数据；将 Phase 3A 验收从 10 条改为 16 条分层用例；保留复杂数据库但区分“必须答对”和“困难诊断”；修正物理表数量、脏数据与外键/唯一约束冲突、orders_wide 全量快照策略和施工时间估算。

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
| 初始准确率会很差 | **会的**。13 张物理表 + 多对多 + 递归 CTE + 宽表 vs 星型模型选择，LLM 一开始选表/选字段/选 join path 都会出错 | 这正是 Phase 3A 要解决的问题。低准确率 = 优化空间大 = 技术故事好 |
| seed 脚本复杂度失控 | 13 张物理表的 seed 约 1000~1300 行，但 7 张旧表的主逻辑不变 | 新增表各自独立函数，不耦合；固定事实和数据质量彩蛋集中管理 |
| Schema 描述文档工作量 | 5 个新 .md + 更新 products.md | 每份文档按现有模板写，约 10~15 min/份 |
| 测试修复范围大 | 硬编码数字散落多处 | 统一用 EXPECTED_SEED_COUNTS 字典，测试引用一处 |

**核心逻辑**：准确率低不可怕——可怕的是准确率低但不知道从哪优化。Phase 3A 的 Schema Retriever、QueryPlanStep 自检、trace_steps 恰恰就是为了定位“为什么错了”。13 张物理表给这个诊断链路提供了充足的优化素材。

### 1.3 为什么不加全部（A+B）类表

B 类表（suppliers、inventory、campaigns、多币种）不加的理由不是“做不动”，而是它们不引入**新的技术维度**：

| B 类表 | 实际挑战 | 为什么不加 |
|--------|---------|-----------|
| suppliers + purchase_orders | 另一组“维表 + 事实表” | 和 orders/products 模式完全相同，纯增加表数量但不增加技术多样性 |
| inventory | 又一张事实表 | 和 orders 的查询模式类似（时间范围 + 聚合 + JOIN 维表） |
| marketing_campaigns | 归因分析 | 概念有趣但 seed 数据极难造出合理分布，且真正的归因需要多步骤 agent，Phase 3A 做不了 |
| 多币种/多时区 | JOIN + 乘法换算 | 概念简单（加 currency + exchange_rate 表 + 乘法），面试能讲但技术挑战薄 |

**设计原则**：每一张新表都必须引入一种“旧表没有的 SQL 生成难题”。加 12 张精心设计的表，比加 20 张模式重复的表，对 agent 的技术锻炼价值更高。

---

## 2. 升级前后对照

### 2.1 表结构全景

| 表 | 类型 | 来源 | 引入的挑战维度 |
|----|------|------|--------------|
| users | 维表 | 原有 | — |
| products | 维表 | 原有（改造：新增 category_id FK + 保留旧 category 字符串冗余列） | 字段歧义（category 字符串 vs category_id 外键） |
| channels | 维表 | 原有 | — |
| orders | 事实表 | 原有（改造：新增 discount_amount / actual_amount 列） | 金额口径歧义（标价 vs 折扣后 vs 实付） |
| refunds | 事实表 | 原有 | — |
| tickets | 事实表 | 原有 | — |
| knowledge_docs | 文档表 | 原有 | — |
| **product_categories** | **层级维表** | **新增** | **递归 CTE、层级语义消歧** |
| **coupons** | **维表** | **新增** | **多对多关系（通过 order_coupons）** |
| **order_coupons** | **桥接表** | **新增** | **多对多 JOIN、金额口径（标价-优惠券=实付）** |
| **user_behavior_log** | **事件日志** | **新增** | **大表、漏斗分析、事件序列** |
| **product_price_history** | **SCD Type 2** | **新增** | **“当时价格 vs 现在价格”、时间窗口 JOIN** |
| **orders_wide** | **宽表（反范式）** | **新增** | **星型模型 vs 宽表的选择策略** |

**共 12 张业务分析表 + 1 张桥接表（order_coupons），即 13 张物理表。**

### 2.2 数据量对照

| 表 | 当前行数 | 升级后 | 倍数 |
|----|---------|--------|------|
| users | 50 | 200 | 4x |
| products | 30 | 50 | 1.7x |
| channels | 6 | 6 | — |
| orders | 500 | 10,000 | 20x |
| refunds | 80 | 1,000 | 12.5x |
| tickets | 120 | 300 | 2.5x |
| knowledge_docs | 8 | 10 | — |
| product_categories | — | ~15 | 新增 |
| coupons | — | 10 | 新增 |
| order_coupons | — | ~3,000 | 新增 |
| user_behavior_log | — | 10,000 | 新增 |
| product_price_history | — | ~150 | 新增 |
| orders_wide | — | 10,000 | 新增（与 orders 全量同步） |

**数据量口径**：v3 选择 1 万级订单，不上 2 万。这个规模足够支撑“非 toy 数据集”和面试中的一万级数据量讲法，同时不会让 seed、pytest 和本地 smoke 变成主要成本。`user_behavior_log` 同样设为 1 万行，作为事件日志大表的代表；后续如果要展示事件流压力，可以单独扩到 2 万行，不影响订单主事实表。

### 2.3 固定业务事实

升级后的 seed 仍必须保留一组固定业务事实，作为 M8-M12 eval、smoke 和面试演示的锚点。建议至少固化以下事实：

| 编号 | 固定事实 | 用途 |
|------|----------|------|
| FACT-01 | 2026 年 6 月 GMV 有稳定数值，且默认排除 `cancelled/canceled` 和 `paid_at IS NULL` 订单 | 核心指标回归 |
| FACT-02 | Aurora Noise Cancelling Headphones 仍是 6 月退款率最高商品 | 继承阶段二锚点，验证新库不破旧能力 |
| FACT-03 | Mobile App 仍是 6 月 GMV 最高渠道或订单量 Top 渠道 | 继承阶段二锚点，验证渠道聚合 |
| FACT-04 | 某个满减券在 Mobile App 或另一个固定渠道使用率最高 | 验证 coupons / order_coupons 桥接表 |
| FACT-05 | 数码电子一级类目 GMV Top 或包含固定子类目贡献 | 验证 product_categories 类目关系 |
| FACT-06 | Aurora Headphones 在 6 月存在稳定历史均价 | 验证 product_price_history SCD 查询 |
| FACT-07 | 某设备类型加购到支付转化率最高 | 验证 user_behavior_log 漏斗查询 |
| FACT-08 | orders_wide 与星型模型在“各渠道 GMV”上默认结果一致 | 验证宽表选择策略 |

固定事实的目标不是让数据变假，而是保证复杂 seed 在每次重置后仍能产出可解释、可复现的验收答案。

### 2.4 指标口径单一事实源

复杂 schema 里最大的风险不是表多，而是同一个业务词有多个候选字段。v3 要求在 `domain_pack/metrics.yaml` 和对应 `schema_desc/*.md` 中明确以下默认口径：

| 业务词 | 默认口径 |
|--------|----------|
| GMV | `SUM(orders.order_amount)`，默认排除 `order_status IN ('cancelled', 'canceled')` 且 `paid_at IS NOT NULL` |
| 净收入 / 实付金额 | 优先使用 `SUM(orders.actual_amount)`；如需要校验明细优惠，再对比 `order_amount - SUM(order_coupons.discount_amount)` |
| 优惠金额 | 订单级汇总看 `orders.discount_amount`，优惠券明细分析看 `order_coupons.discount_amount` |
| 退款总额 | `SUM(refunds.refund_amount)`，保留负数冲销记录，不默认取绝对值 |
| 当前价格 | 优先使用 `products.price`；`product_price_history.is_current=1` 用于校验同步一致性 |
| 历史售价 / 当时价格 | 使用 `product_price_history.valid_from/valid_to` 做时间窗口匹配 |
| 宽表数据 | `orders_wide` 适合汇总看板；明细追溯和强一致问题回到规范化星型模型 |

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

### 3.2 coupons + order_coupons（优惠券体系）

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

**Orders 表改造**：
- 新增 discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0 — 该订单的优惠券抵扣总额（冗余字段）
- 新增 actual_amount DECIMAL(12,2) NOT NULL — 实付金额 = order_amount - discount_amount

**Agent 挑战场景**：
- 用户问「GMV」→ agent 必须知道 GMV = SUM(order_amount)，不是 SUM(actual_amount)
- 用户问「净收入」→ 需要选择 actual_amount 或 order_amount - SUM(discount_amount)
- 用户问「优惠券使用率最高的渠道」→ orders → order_coupons → coupons 三表 JOIN
- 金额字段多义：order_amount / discount_amount / actual_amount / refund_amount
- discount_amount 冗余不一致：orders.discount_amount（汇总）vs SUM(order_coupons.discount_amount)（明细聚合），两个值可能不一致，agent 该信哪个？

### 3.3 user_behavior_log（用户行为日志）

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

### 3.4 product_price_history（SCD Type 2 价格历史）

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

**Seed 数据（约 150 行，30 个商品 x 平均 5 个历史版本）**：
- 每个商品有 3~8 个价格版本，覆盖过去 6 个月
- 锚点商品 Aurora Headphones：899 → 799（促销）→ 899（恢复）→ 849（永久降价）
- 部分 SaaS 商品只有涨价历史，没有降价（模拟真实）
- is_current = 1 的价格和 products.price 一致（冗余），但刻意让 1~2 个商品不一致（模拟数据同步延迟）

**Agent 挑战场景**：
- 用户问「Aurora 耳机现在的价格是多少」→ 查 products.price 还是 product_price_history WHERE is_current=1？
- 用户问「6 月的平均售价」→ SCD Type 2 经典查询：WHERE valid_from <= date AND (valid_to > date OR valid_to IS NULL)
- 用户问「历史订单金额是否要按当时价格重新计算」→ 架构级理解：orders.order_amount 已经是下单时锁定价格
- **面试讲法**：数仓中「缓慢变化维度（SCD）Type 2」经典实现，用 valid_from/valid_to 区间 + is_current 标志位

### 3.5 orders_wide（宽表 / 反范式视图）

**引入的挑战**：多表源选择——agent 需要在规范化星型模型和反范式宽表之间做出选择。

```sql
CREATE TABLE orders_wide (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    order_id        INT NOT NULL UNIQUE,
    order_no        VARCHAR(64) NOT NULL,
    order_status    VARCHAR(32) NOT NULL,
    order_amount    DECIMAL(12,2) NOT NULL,
    discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    actual_amount   DECIMAL(12,2) NOT NULL,
    quantity        INT NOT NULL,
    paid_at         DATETIME NOT NULL,
    user_name       VARCHAR(80) NOT NULL,
    user_role       VARCHAR(32) NOT NULL,
    product_name    VARCHAR(160) NOT NULL,
    category        VARCHAR(80) NOT NULL,
    product_price   DECIMAL(12,2) NOT NULL,
    channel_name    VARCHAR(120) NOT NULL,
    channel_type    VARCHAR(48) NOT NULL,
    refund_count    INT NOT NULL DEFAULT 0,
    total_refund    DECIMAL(12,2) NOT NULL DEFAULT 0,
    has_refund      TINYINT(1) NOT NULL DEFAULT 0,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_paid_at (paid_at),
    INDEX ix_channel (channel_type),
    INDEX ix_category (category),
    INDEX ix_status (order_status)
);
```

**Seed 数据**：与 orders 表全量同步生成（10000 行），通过 INSERT INTO ... SELECT 从 orders + users + products + channels + refunds 聚合写入。

**宽表策略**：
- `orders_wide` 是“分析快照宽表”，不是权威交易源。
- 新增建议字段：`snapshot_at` / `batch_id` / `source_updated_at`，用于解释宽表的同步时间和延迟。
- 经营汇总、看板类问题可优先用宽表；强一致、明细追溯、退款实时口径优先回到星型模型。
- 不建议只同步 500 行样例数据，否则 agent 还要额外判断宽表数据不完整，噪音大于收益。

**Agent 挑战场景**：
- 用户问「各渠道 GMV」→ agent 有两条路：
  - 方案 A：宽表单表查询（简单但数据可能延迟）
  - 方案 B：星型模型 JOIN（标准且实时）
  - 两条路结果应该一致，考验 agent 的**选表策略**
- 用户问「退款率最高的商品」→ 宽表已有 refund_count/total_refund，但口径可能与 refunds 表实时计算有微妙差异（模拟「宽表数据延迟」）
- **核心面试价值**：体现「数据仓库建模」中的经典权衡——星型模型（规范、无冗余、查询灵活）vs 宽表（反规范、有冗余、查询快）

---

## 4. 数据质量彩蛋设计

在 seed 脚本中刻意引入以下问题，每类问题占对应表总行数的 1%~5%。

**约束原则**：主业务表仍保留外键和唯一约束，不为了制造脏数据破坏工程规范。真实企业的“乱”不等于完全无约束；本项目优先模拟那些能落库、能测试、能解释的数据质量问题。若要展示违反外键/唯一性的原始脏数据，后续可单独新增 `raw_import_*` 原始导入表，不放进本次主线。

| 编号 | 表 | 问题类型 | 具体表现 | 期望 Agent 行为 |
|------|-----|---------|---------|---------------|
| DQ-01 | orders | NULL 值陷阱 | 约 20 条订单 paid_at IS NULL（下单未支付） | 计算"GMV"时不纳入这些订单 |
| DQ-02 | orders | 逻辑重复 | 约 10 条订单共享同一个 `source_order_no` / `external_order_no`，但 `order_no` 仍保持唯一 | 使用业务源单号去重，而不是破坏主表唯一约束 |
| DQ-03 | orders | 不一致状态值 | 约 8 条订单 order_status = 'canceled'（单 l 拼写，正确是 cancelled） | 兼容处理，或至少不影响正常统计 |
| DQ-04 | orders | 金额不一致 | 约 5 条订单 actual_amount + discount_amount != order_amount | agent 算"实付"时信哪个字段？ |
| DQ-05 | refunds | 弱关联记录 | 约 5 条退款的 `source_order_no` 指向不存在的外部订单号，但 `order_id` 仍指向可落库的占位订单或保持可空设计（需二选一） | 区分数据库外键关系和外部业务单号关系 |
| DQ-06 | refunds | 金额负数 | 约 3 条退款 refund_amount < 0（模拟修正冲销） | 计算"总退款额"时需要考虑负数场景 |
| DQ-07 | users | 已禁用用户有数据 | 约 4 个 status='disabled' 用户仍有订单 | 按用户筛选时是否过滤 disabled？ |
| DQ-08 | user_behavior_log | NULL 字段 | 约 10% 记录 duration_ms IS NULL | AVG(duration_ms) 自动跳过 NULL，但 COUNT 可能误算 |
| DQ-09 | products | 已停售商品有订单 | 约 3 个 status='paused' 商品仍有历史订单 | agent 需判断"当前在售"和"历史销售"是两个概念 |
| DQ-10 | product_price_history | 冗余不一致 | 1~2 个商品的 products.price != product_price_history WHERE is_current=1 的价格 | agent 需要决策以哪个为准 |

> **面试价值**：这 10 类彩蛋覆盖了数据质量问题的 5 大类型——完整性（NULL）、唯一性（重复）、一致性（状态值/金额/冗余）、参照完整性（孤儿记录）、准确性（负数），可以作为面试中展示"工程严谨性"的具体案例。

**实现注意**：
- 当前 `refunds.order_id` 若继续使用外键，则不能直接插入不存在的 `order_id`。
- 当前 `orders.order_no` 若继续使用唯一约束，则不能直接插入重复 `order_no`。
- 因此 v3 将“物理约束冲突”改为“逻辑脏数据”：既保留工程边界，又能让 agent 面对真实业务里的源系统脏数据。

---

## 5. 对现有模块的影响分析

### 5.1 需要协同修改的文件

| 文件 | 改动 | 风险 |
|------|------|------|
| app/models/ | 新增 6 个模型文件 + 修改 products.py（加 category_id）+ 修改 orders.py（加 discount_amount / actual_amount） | 低 |
| alembic/versions/ | 新增 1 个 migration（全部 DDL 在一个版本中完成） | 低 |
| scripts/seed_data.py | 新表 seed + 1 万级数据量 + 固定业务事实 + 彩蛋逻辑 + orders_wide 全量同步写入 | **中**（最大改动点） |
| domain_pack/schema_desc/ | 新增 6 个 .md + 更新 products.md、orders.md，并补 grain / when_to_use / data_quality_notes | 低 |
| domain_pack/metrics.yaml | 新增 NAR、优惠券使用率、转化率、漏斗指标等 | 低 |
| domain_pack/sql_examples/basic.yaml | 新增 5~8 条涉及新表的 few-shot SQL | 低 |
| eval/cases/phase3a-regression.yaml | 新增 16 条分层评测用例（简单、核心指标、中等多表、困难诊断、安全） | 中 |
| tests/test_m1_*.py | 更新表数量、seed 行数等硬编码断言 | 低 |
| tests/test_m2_api.py | products API 筛选参数可能调整（category 列仍保留所以改动小） | 低 |
| tests/test_m5_agent_response.py | 固定事实的硬编码值更新（新数据量下 GMV 等数值会变） | 低 |

### 5.2 不受影响的模块

- **M3 模板 SQL**：现有模板 SQL 涉及的表字段不变（category 列保留为冗余字段，order_amount 列不变）
- **M4 NL2SQL / prompt**：_format_tables() 自动从 domain_pack 读取新表
- **M5 AgentResponse / Trace**：响应结构不变
- **M6 EvalOps-lite**：smoke 用例仍能运行（旧表字段不变）
- **M8~M12 Phase 3A**：Schema Retrieval / QueryPlanStep 本身就是针对最终 schema 设计，新表直接进入 scope

### 5.3 新旧库的 Phase 3A 策略

升级后 Phase 3A 的所有工作都基于新库（13 张物理表），不需要"先跑旧库 baseline 再跑新库"。但为了避免复杂度一次性压垮验收，Phase 3A 需要把“新库 v1 baseline 记录”和“新 pipeline 分层验收”区分开。

| Phase 3A 模块 | 调整 |
|--------------|------|
| M8 回归基线 | 在新库上跑 v1 baseline，记录真实通过率；baseline 不要求 7/8 或 10/14 达标，只要求报告完整、失败可归因 |
| M9 Schema Retrieval | 召回文档覆盖 13 张物理表的字段/指标/关系；expected_tables 要求覆盖新表 |
| M10 QueryPlanStep | 校验规则优先覆盖普通 JOIN、多对多 JOIN、金额口径和宽表选择；递归 CTE / 漏斗 / SCD 作为困难诊断能力纳入 |
| M11 新 Pipeline | force_new_pipeline 路径覆盖新表场景 |
| M12 对照报告 | **不再做旧库 vs 新库对照**；改为报告 v1 baseline vs Phase 3A 新 pipeline 在同一新库上的表现、局部 Schema prompt 的收敛效果、困难 case 的 trace_steps 和 issue tags |

---

## 6. 技术深度提升对照

### 6.1 面试场景

| 面试官可能问的 | 升级前（7 表） | 升级后（12 表） |
|--------------|-------------|--------------|
| "你的 agent 怎么在十余张表中找对表？" | 才 7 张，不需要检索策略 | 13 张物理表 + 5 种不同表类型（维表/事实表/桥接表/事件日志/宽表），能讲 Schema Retriever 的设计 |
| "SQL 生成怎么处理歧义？" | 几乎没有歧义 | 金额字段多义、类目层级、category 冗余列 vs category_id FK、宽表 vs 星型模型 |
| "怎么保证生成的 SQL 在脏数据上也能跑对？" | 数据太干净 | 10 类彩蛋覆盖完整性/唯一性/一致性/参照完整性/准确性 |
| "多对多关系怎么处理？" | 没有 | 订单-优惠券多对多 |
| "层级维度怎么查？" | 没有 | 递归 CTE |
| "缓慢变化维度是什么？你怎么处理？" | 没有 | SCD Type 2 价格历史 |
| "数据仓库建模中星型模型和宽表怎么选？" | 没有 | orders_wide 制造了这个选择 |
| "转化漏斗怎么用 SQL 实现？" | 没有 | user_behavior_log 事件序列分析 |
| "金额字段不一致怎么处理？" | 没有 | discount_amount 汇总 vs 明细聚合不一致 |

### 6.2 评测用例扩展

Phase 3A v3 改为 **16 条分层验收用例**，不再用 10 条同时承载所有难题。核心思想是：简单题和核心指标必须稳定；中等题验证新 schema 的主路径；困难题允许部分失败，但必须能通过 trace 解释失败原因。

| 类别 | 数量 | 通过要求 | 示例问题 | 涉及能力 |
|------|------|----------|----------|----------|
| 简单查询 | 3 | 3/3 通过 | "查询 active 商品列表前 10 条"、"查询 2026 年 6 月已支付订单" | 单表筛选、时间字段、基础列选择 |
| 核心指标 | 4 | 至少 3/4 通过 | "本月 GMV"、"各渠道订单量"、"退款率最高商品"、"本月净收入" | 指标口径、金额字段选择、聚合 |
| 中等多表 | 4 | 至少 3/4 通过 | "满减券使用率最高的渠道"、"一级类目销售额排名"、"各渠道 GMV"、"高优先级工单关联订单" | JOIN、桥接表、类目维表、宽表 vs 星型选择 |
| 困难诊断 | 3 | 至少 1/3 结果正确；3/3 必须有完整 trace 和 issue tag | "数码电子及其子类目 GMV"、"加购到支付转化率"、"6 月各商品平均售价" | 递归 CTE、漏斗、SCD 时间窗口 |
| 安全 | 2 | 2/2 必须拦截 | `DROP TABLE orders`、`DELETE FROM refunds WHERE id = 1` | SQL Guard、RBAC 不绕过 |

**阶段三A最低硬门**：
- 安全：2/2 blocked。
- 简单查询：3/3 正确。
- 核心指标 + 中等多表：8 条中至少 6 条正确。
- 困难诊断：3 条中至少 1 条结果正确，且 3 条都必须记录 `schema_retrieval`、`join_path`、`query_plan`、`plan_validation`、`sql_generation`、`sql_guard`、`sql_execution` 和明确 issue tag。
- 总体允许类 SQL：14 条中建议至少 10 条正确；若低于 10 条，先修 schema retrieval / plan validation / prompt，不通过删除困难 case 掩盖问题。

> 具体 16 条的最终构成由 M8 从候选池中选定，以上为候选方向。

---

## 7. 施工计划

### 7.1 执行顺序

```
步骤 1：新表模型 + Migration
  ├── app/models/product_categories.py
  ├── app/models/coupons.py
  ├── app/models/order_coupons.py
  ├── app/models/user_behavior_log.py
  ├── app/models/product_price_history.py
  ├── app/models/orders_wide.py
  ├── 修改 app/models/products.py（新增 category_id）
  ├── 修改 app/models/orders.py（新增 discount_amount / actual_amount）
  └── alembic revision --autogenerate && alembic upgrade head

步骤 2：Schema 描述文档
  ├── domain_pack/schema_desc/product_categories.md
  ├── domain_pack/schema_desc/coupons.md
  ├── domain_pack/schema_desc/order_coupons.md
  ├── domain_pack/schema_desc/user_behavior_log.md
  ├── domain_pack/schema_desc/product_price_history.md
  ├── domain_pack/schema_desc/orders_wide.md
  ├── 更新 products.md / orders.md
  └── 每份文档补 grain / default_time_field / when_to_use / avoid_when / data_quality_notes

步骤 3：Seed 脚本升级（最大工作量）
  ├── 旧表数据量放大（EXPECTED_SEED_COUNTS 更新：orders=10000）
  ├── 新表 seed 函数（按表拆分独立 _build_* 函数）
  ├── 固定业务事实锚定（GMV、退款率、渠道、优惠券、类目、SCD、漏斗、宽表）
  ├── orders_wide 全量同步写入（INSERT INTO ... SELECT 聚合）
  ├── 数据质量彩蛋函数（_add_data_quality_quirks）
  └── products.category_id 关联 + category 冗余列填充

步骤 4：Metrics + SQL Examples 更新
  ├── metrics.yaml：新增 nar / coupon_usage_rate / conversion_rate / avg_selling_price 等
  ├── 明确 GMV / 净收入 / 优惠金额 / 当前价格 / 历史售价 / 宽表默认口径
  └── basic.yaml：新增 5~8 条涉及新表的 few-shot SQL

步骤 5：测试更新
  ├── tests/test_m1_models.py：验证 13 张物理表均可创建
  ├── tests/test_m1_seed.py：更新 EXPECTED_SEED_COUNTS 和固定业务事实断言
  ├── tests/test_m2_api.py：category 筛选值更新
  └── tests/test_m5_agent_response.py：固定事实数值更新

步骤 6：全量验证
  ├── alembic downgrade && alembic upgrade head（验证迁移可逆）
  ├── python -m scripts.seed_data --reset（验证新 seed、1 万级数据量和固定事实）
  ├── pytest 全量（验证无回归）
  └── 验证 8 个固定事实仍稳定
```

### 7.2 时间估算

| 步骤 | 预估时间 | 说明 |
|------|---------|------|
| 模型 + Migration | 1.0h | 6 张新表模型 + 2 张旧表修改 + DDL |
| Schema 描述文档 | 1.0h | 6 个新 .md + 2 个更新，并补 grain / when_to_use / data_quality_notes |
| Seed 脚本升级 | 3.0~4.0h | **最大工作量**：1 万级数据、固定事实、新表 seed、彩蛋逻辑、orders_wide 全量同步 |
| Metrics + Examples | 0.5h | 新增指标 + 默认口径 + few-shot SQL |
| 测试更新 | 1.0h | 硬编码数字、固定事实、筛选值和 eval case 更新 |
| 全量验证 | 0.5~1.0h | pytest + seed + migration 可逆，视本机 DB 和 bulk insert 性能浮动 |
| **合计** | **约 1~1.5 天** | 更接近真实施工成本；4h 仅适合无固定事实、无脏数据、无完整验证的草稿实现 |

---

## 8. 待用户确认

1. **执行时机**：确认在 Phase 3A M8 之前做，作为 Phase 2.7 / 数据底座升级模块；这样 M8 baseline 直接在新库上跑。
2. **products.category 改造**：默认保留冗余字符串列 + 新增 category_id FK，模拟历史遗留字段歧义。
3. **脏数据策略**：默认不破坏主表外键/唯一约束，采用逻辑脏数据；若后续要展示强脏数据，再新增 raw_import 表。
4. **Phase 3A 验收口径**：默认采用 16 条分层用例，硬门为安全 2/2、简单 3/3、核心+中等 6/8、困难 1/3 正确且 3/3 可诊断。

---

> **关联文档**：
> - 阶段三A 计划：[phase3a-plan.md](phase3a-plan.md)
> - 技术档案：[AI_CONTEXT.md](AI_CONTEXT.md)
> - 总路线：[LEARNING_ROADMAP_v3.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP_v3.md)
> - v1 版（两期方案）：[database-upgrade-plan.md](database-upgrade-plan.md)
