# DataPilot 数据库升级计划

> 目标：将当前"干净小库"升级为更接近真实企业环境的数据库，提升 data agent 的技术挑战度和面试说服力。

## 1. 现状评估

### 1.1 当前数据库画像

| 维度 | 当前状态 | 评价 |
|------|---------|------|
| 表数量 | 7 张（users, products, channels, orders, refunds, tickets, knowledge_docs） | 偏少，真实电商通常 30~100+ |
| 数据量 | 50 用户 / 30 商品 / 6 渠道 / 500 订单 / 80 退款 / 120 工单 | 太小，agent 不需要考虑查询性能 |
| 表关系 | 简单星型（事实表 → 维表），最多 3 表 JOIN | 真实企业常见 5~8 表 JOIN |
| 命名规范 | 统一 snake_case，英文清晰 | 真实企业常有中英混合、缩写不一致、历史遗留 |
| 数据质量 | 无 NULL 陷阱、无重复、无脏数据 | 这是 agent 最大的"舒适区" |
| 业务复杂度 | 单渠道电商，单一币种，无时区 | 缺乏多业务线、多币种等真实复杂度 |
| 指标定义 | `metrics.yaml` 5 个 KPI，定义清晰 | 真实企业可能有几十个指标，且口径打架 |

### 1.2 对 Data Agent 挑战度的影响

当前数据库下，agent 的 NL2SQL 能力验证偏弱：

- **找表太容易**：总共 7 张表，LLM 几乎不会选错表
- **JOIN 太简单**：关系一目了然，不需要推理 join path
- **没有歧义**：字段名和业务含义一一对应，不需要消歧
- **数据太干净**：agent 不会遇到 NULL/重复/不一致等真实世界问题
- **没有 Schema 理解门槛**：不需要在 50 张表中定位正确的那 3 张

**结论：M1 阶段骨架正确，但需要分阶段升级以匹配 data agent 项目的技术深度。**

---

## 2. 真实企业数据库的"乱"从哪来

理解"乱"的来源，才能有针对性地设计升级方案：

### 2.1 Schema 层面

| 真实问题 | 对 Agent 的挑战 |
|---------|----------------|
| 表多（50~200+），且命名不规范 | 用户问"上个月销售额"，agent 需要在 `order_header`、`sale_fact`、`交易明细` 中找到正确的表 |
| 同一业务概念存多张表（历史遗留） | `order_v1` + `order_v2` 并存，agent 需判断用哪张 |
| 字段名歧义 | `status` 在不同表含义完全不同；`amount` 有 `order_amount`、`paid_amount`、`actual_amount` 三个 |
| 隐式关系 | 没有外键约束，JOIN 条件靠"约定"或文档 |
| EAV 模式（实体-属性-值） | 商品属性不存列，存行，查询需要行转列 |

### 2.2 数据层面

| 真实问题 | 对 Agent 的挑战 |
|---------|----------------|
| NULL 值陷阱 | `paid_at IS NULL` 的订单不应计入 GMV，agent 容易漏 |
| 重复数据 | 数据同步 bug 导致同一订单出现两次，agent 需要 `DISTINCT` 或去重 |
| 不一致的状态值 | `'cancelled'` 和 `'canceled'` 共存，`WHERE status = 'cancelled'` 会漏数据 |
| 孤儿记录 | refund 的 `order_id` 指向已删除的订单 |
| 边界值 | 金额为 0、负数、极大值；时间为 1970-01-01 |

### 2.3 业务层面

| 真实问题 | 对 Agent 的挑战 |
|---------|----------------|
| 指标口径不统一 | 财务部 GMV = 含税，运营部 GMV = 不含税 |
| 多对多关系 | 一个订单用多张优惠券，一张优惠券可用于多个订单 |
| 层级维度 | 类目树（一级→二级→三级），需要递归 CTE |
| 缓慢变化维度 | 商品价格变了，历史订单应该关联旧价格还是新价格？ |
| 多时区/多币种 | `created_at` 是 UTC 还是北京时间？`amount` 是人民币还是美元？ |

---

## 3. 升级方案总览

分两期执行，第一期（Phase 3A 同期）做轻量升级，第二期（Phase 4/5）做企业级模拟。

### 3.1 第一期：Phase 3A 期间（轻量升级） 🎯 当前执行

**目标**：不大改现有表结构，新增 3~4 张表 + 放大数据量 + 引入数据质量问题。

| 改动 | 内容 | 挑战点 |
|------|------|--------|
| 新增 `product_categories` | 类目树，自引用 `parent_id` | 递归 CTE、"一级类目 vs 二级类目"的语义理解 |
| 新增 `coupons` + `order_coupons` | 优惠券 + 订单-优惠券关联表 | 多对多关系、金额计算（原价 − 优惠券 − 退款） |
| 新增 `user_behavior_log` | 用户行为日志（浏览/加购/下单） | 大表（seed 2000+ 行），"浏览转化率"等多步骤指标 |
| 数据量放大 | orders 500→5000，users 50→200 | agent 需要考虑查询性能（虽然 MySQL 仍能秒出） |
| 数据质量"彩蛋" | NULL 值、重复行、不一致状态值 | 考验 agent SQL 的鲁棒性 |

### 3.2 第二期：Phase 4/5 期间（企业级模拟） 🔮 后续

| 改动 | 内容 | 挑战点 |
|------|------|--------|
| 新增 `suppliers` + `purchase_orders` | 供应商与采购链路 | 供应链场景，新业务域 |
| 新增 `inventory` | 库存表 | "缺货分析""库存周转天数" |
| 新增 `marketing_campaigns` | 营销活动 + 归因 | 活动 ROI 分析 |
| 多币种/多时区 | `currency`、`timezone` 字段 | 金额换算、时区转换 |
| 缓慢变化维度 | 商品价格历史表 | Type 2 SCD，"当时的价格" vs "现在的价格" |
| 数据仓库模拟 | 一份 `orders_wide` 宽表（反范式） | agent 需要在星型模型和宽表之间选择 |

---

## 4. 第一期详细设计

### 4.1 新增表：`product_categories`（类目树）

```sql
CREATE TABLE product_categories (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(80) NOT NULL COMMENT '类目名称',
    parent_id   INT NULL COMMENT '父类目ID，NULL=一级类目',
    level       TINYINT NOT NULL DEFAULT 1 COMMENT '层级：1/2/3',
    sort_order  INT NOT NULL DEFAULT 0,
    status      VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX ix_parent (parent_id),
    INDEX ix_level (level),
    FOREIGN KEY (parent_id) REFERENCES product_categories(id)
);
```

**对 Agent 的挑战**：
- 用户问"数码电子类目下有多少订单"→ 需要理解"数码电子"可能包含子类目（手机、电脑、配件），要用递归 CTE
- 当前 `products.category` 是字符串，升级后改为 `category_id` 外键 → 多一层 JOIN
- Schema 检索需要理解"类目"是一个层级概念，不是平铺列表

**Seed 数据示例**：

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
...
```

**Products 表改造**：`category` 字符串列 → 新增 `category_id INT FK → product_categories.id`，旧 `category` 列保留为冗余字段（模拟历史遗留：两个字段都在，agent 需判断用哪个）。

### 4.2 新增表：`coupons` + `order_coupons`（优惠券体系）

```sql
CREATE TABLE coupons (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    coupon_code     VARCHAR(32) NOT NULL UNIQUE COMMENT '优惠券编码',
    coupon_type     VARCHAR(24) NOT NULL COMMENT '类型：fixed / percentage / free_shipping',
    discount_value  DECIMAL(12,2) NOT NULL COMMENT '优惠值（固定金额或百分比）',
    min_order_amount DECIMAL(12,2) NULL COMMENT '最低订单金额门槛',
    valid_from      DATETIME NOT NULL,
    valid_to        DATETIME NOT NULL,
    status          VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX ix_valid_range (valid_from, valid_to),
    INDEX ix_type (coupon_type)
);

CREATE TABLE order_coupons (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    order_id    INT NOT NULL,
    coupon_id   INT NOT NULL,
    discount_amount DECIMAL(12,2) NOT NULL COMMENT '实际抵扣金额',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_order_coupon (order_id, coupon_id),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (coupon_id) REFERENCES coupons(id)
);
```

**对 Agent 的挑战**：
- 多对多关系：一个订单可用多张券 → `orders ← order_coupons → coupons`
- 金额计算变复杂：
  - 用户问"GMV"→ 口径是"原价"还是"实付金额"？还是"优惠后金额"？
  - `order_amount` 是标价，`order_amount − SUM(discount_amount)` 才是实付
- `metrics.yaml` 需要新增"净收入（NAR）""优惠券使用率""平均折扣率"等指标
- 时间维度：优惠券有有效期，agent 需要判断"这张券在订单支付时间点是否有效"

**Seed 数据设计**：
- 10 张优惠券，覆盖满减/折扣/免运费三种类型
- 约 30% 的订单使用优惠券
- 部分券已过期，少量订单关联了已过期券（模拟业务漏洞）

### 4.3 新增表：`user_behavior_log`（用户行为日志）

```sql
CREATE TABLE user_behavior_log (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id     INT NOT NULL,
    event_type  VARCHAR(32) NOT NULL COMMENT '事件类型：view / add_cart / remove_cart / place_order / pay / search',
    target_type VARCHAR(32) NULL COMMENT '目标类型：product / category / search_keyword',
    target_id   VARCHAR(128) NULL COMMENT '目标标识（商品ID/SKU/搜索词等）',
    session_id  VARCHAR(64) NOT NULL COMMENT '会话ID，用于串联用户一次访问',
    event_time  DATETIME NOT NULL COMMENT '事件发生时间',
    duration_ms INT NULL COMMENT '停留时长（毫秒），仅 view 事件有意义',
    device_type VARCHAR(24) NULL COMMENT '设备类型：iOS / Android / Web / MiniProgram',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX ix_user_event_time (user_id, event_time),
    INDEX ix_event_type_time (event_type, event_time),
    INDEX ix_session (session_id)
);
```

**对 Agent 的挑战**：
- **大表**：seed 2000~5000 行（对比 orders 的 500 行），让 agent 感受到"不是所有表都一样大"
- **复杂漏斗指标**："浏览→加购→下单→支付 的转化率"
  - 用户问"上周浏览了耳机但没买的用户有多少"→ 需要 `view` 事件 + 排除有 `place_order` 的用户
  - 这是典型的"行为序列分析"，不是简单的 `COUNT` + `GROUP BY`
- **目标类型歧义**：`target_id` 可能是商品 ID、也可能是搜索词，agent 需要根据 `target_type` 判断
- **多步骤查询**：可能需要子查询或 CTE 才能完成

**Seed 数据设计**：
- 2000~5000 行，覆盖 30 天内的行为
- 约 60% view、20% add_cart、10% place_order、5% pay、5% search
- 制造一些"看了很多但没买"的用户（用于转化率分析）
- 引入一些 `duration_ms IS NULL` 的记录（模拟数据采集缺失）

### 4.4 数据量放大

| 表 | 当前行数 | 升级后 | 说明 |
|----|---------|--------|------|
| users | 50 | 200 | 覆盖更多角色分布 |
| products | 30 | 50 | 对接新的类目树 |
| channels | 6 | 6 | 保持不变 |
| orders | 500 | 5000 | 覆盖 3 个月（5~7月）|
| refunds | 80 | 500 | 按约 10% 退款率 |
| tickets | 120 | 300 | 更多类型分布 |
| knowledge_docs | 8 | 10 | 新增 2 篇 |
| product_categories | - | ~15 | 3 层类目树 |
| coupons | - | 10 | 3 种类型 |
| order_coupons | - | ~1500 | 约 30% 订单使用 |
| user_behavior_log | - | 3000 | 30 天行为 |

### 4.5 数据质量"彩蛋"设计

在 seed 脚本中刻意引入以下问题，每类问题占对应表总行数的小比例（1%~5%）：

| 编号 | 表 | 问题类型 | 具体表现 | 期望 Agent 行为 |
|------|-----|---------|---------|---------------|
| DQ-01 | orders | NULL 值陷阱 | 约 20 条订单 `paid_at IS NULL`（下单未支付） | 计算"GMV"时不纳入这些订单 |
| DQ-02 | orders | 重复数据 | 约 10 条订单出现 2 次（同 order_no，不同 id） | 使用 `DISTINCT` 或合适去重策略 |
| DQ-03 | orders | 不一致状态值 | 约 8 条订单 `order_status = 'canceled'`（单 l 拼写，正确是 `cancelled`） | 需要兼容处理，或至少不影响正常统计 |
| DQ-04 | refunds | 孤儿记录 | 约 5 条退款指向不存在的 `order_id` | JOIN 时用 LEFT JOIN 不会丢数据，但 INNER JOIN 会 |
| DQ-05 | refunds | 金额负数 | 约 3 条退款 `refund_amount < 0`（模拟修正冲销） | 计算"总退款额"时不应直接 SUM，需判断 |
| DQ-06 | users | 已禁用用户有数据 | 约 4 个 `status='disabled'` 用户仍有订单 | 按用户筛选时是否过滤 disabled？ |
| DQ-07 | user_behavior_log | NULL 字段 | 约 10% 记录 `duration_ms IS NULL` | 聚合函数 `AVG(duration_ms)` 自动跳过 NULL，但 `COUNT` 可能误算 |
| DQ-08 | products | 已停售商品有订单 | 约 3 个 `status='paused'` 商品仍有历史订单 | 类似 DQ-06，agent 需判断"当前在售"和"历史销售"是两个概念 |

> **面试价值**：这些"彩蛋"可以作为面试 talking point——"我在项目中模拟了真实企业常见的 8 类数据质量问题，让 data agent 在面对脏数据时也能给出正确结果或合理降级。"

---

## 5. 对现有模块的影响分析

### 5.1 需要协同修改的文件

| 文件 | 改动 | 所属模块 |
|------|------|---------|
| `app/models/` | 新增 3 个模型文件 + 修改 `products.py`（加 `category_id`） | 本次 |
| `alembic/versions/` | 新增 migration | 本次 |
| `scripts/seed_data.py` | 新表 seed + 数据量放大 + 彩蛋逻辑 | 本次 |
| `domain_pack/schema_desc/` | 新增 3 个表的 `.md` 描述 + 更新 products.md | 本次 |
| `domain_pack/metrics.yaml` | 新增 NAR、优惠券使用率、转化率等指标 | 本次 |
| `domain_pack/sql_examples/basic.yaml` | 新增涉及新表的 few-shot SQL | M9 |
| `eval/cases/phase3a-regression.yaml` | 新增涉及新表的评测用例 | M8 |
| `tests/test_m1_*.py` | 更新表数量、seed 行数等硬编码断言 | 本次 |
| `tests/test_m2_api.py` | products API 筛选参数可能调整 | 本次 |

### 5.2 不受影响的模块

- M3 模板 SQL：现有模板 SQL 涉及的表字段不变（`category` 列保留为冗余字段）
- M4 NL2SQL / prompt：`_format_tables()` 自动读取新表
- M5 AgentResponse / Trace：响应结构不变
- M6 EvalOps-lite：smoke 用例仍能运行（新表不影响旧用例）
- M8~M12 Phase 3A：Schema Retrieval / QueryPlanStep 自动覆盖新表

### 5.3 风险点

| 风险 | 缓解 |
|------|------|
| 旧测试硬编码了表数量/行数 | 升级时同步更新测试断言 |
| `products.category` 改为 `category_id` FK 后旧 SQL 不兼容 | `category` 字符串列保留为冗余列，不删除 |
| seed 脚本变复杂，维护成本上升 | 彩蛋逻辑集中在独立的 `_add_data_quality_quirks()` 函数中 |
| 新表可能让 Schema Retrieval 召回率暂时下降 | M9 验收标准只看 8 条允许类 case，新表不在 scope 内 |

---

## 6. 对 Data Agent 技术深度的提升

### 6.1 面试场景对照

| 面试官可能问的 | 当前能否体现 | 升级后能否体现 |
|--------------|-------------|---------------|
| "你的 agent 怎么在几十张表中找对表？" | ❌ 才 7 张表 | ⚠️ 10 张表（仍偏少，但能讲 Schema Retrieval） |
| "SQL 生成怎么处理歧义？" | ❌ 几乎没有歧义场景 | ✅ 金额字段多义、类目层级、状态值不一致 |
| "怎么保证生成的 SQL 在脏数据上也能跑对？" | ❌ 数据太干净 | ✅ 8 类彩蛋 + NULL 陷阱 |
| "多对多关系怎么处理？" | ❌ 没有 | ✅ 订单↔优惠券 |
| "层级维度（类目树）怎么查？" | ❌ 没有 | ✅ 递归 CTE |
| "转化漏斗这种多步骤指标怎么支持？" | ❌ 没有 | ✅ user_behavior_log |
| "怎么处理企业里同一概念多张表的情况？" | ❌ 没有 | ⚠️ 第二期做 |

### 6.2 评测用例扩展

升级后可以在 `phase3a-regression.yaml` 中新增以下类型用例：

| 用例类型 | 示例问题 | 涉及新能力 |
|---------|---------|-----------|
| 类目递归 | "数码电子类目下所有子类目的 GMV 是多少？" | 递归 CTE、类目树理解 |
| 多对多 | "使用优惠券的订单平均折扣金额是多少？" | 多对多 JOIN、金额口径选择 |
| 转化漏斗 | "上周浏览了商品但未下单的用户数？" | 子查询 / NOT EXISTS、行为序列 |
| 数据质量 | "本月退款总额是多少？"（存在负数退款） | NULL 处理、去重、口径判断 |
| 歧义消解 | "订单金额最高的渠道是哪个？"（有标价、实付、折扣后三个金额字段） | 语义消歧 |

---

## 7. 施工计划

### 7.1 执行顺序

```
步骤 1：新表模型 + Migration
  └── app/models/product_categories.py, coupons.py, user_behavior_log.py
  └── alembic revision --autogenerate

步骤 2：Schema 描述文档
  └── domain_pack/schema_desc/product_categories.md, coupons.md, user_behavior_log.md
  └── 更新 products.md（新增 category_id）

步骤 3：Seed 脚本升级
  └── 新表 seed 数据
  └── orders 500→5000，关联数据同比放大
  └── 数据质量彩蛋函数

步骤 4：Metrics + SQL Examples 更新
  └── metrics.yaml 新增 NAR、转化率等
  └── basic.yaml 新增 3~5 条 few-shot

步骤 5：测试更新
  └── test_m1_*.py 硬编码数字更新
  └── test_m2_api.py 筛选参数调整

步骤 6：验证
  └── pytest 全量
  └── seed --reset 确认新数据
  └── alembic check 确认迁移干净
```

### 7.2 时间估算

| 步骤 | 预估时间 | 说明 |
|------|---------|------|
| 模型 + Migration | 30 min | 3 张新表，字段不多 |
| Schema 描述 | 20 min | 3 个 md，复用现有模板 |
| Seed 升级 | 60 min | 核心工作量在彩蛋逻辑 |
| Metrics + Examples | 20 min | 少量新增 |
| 测试更新 | 20 min | 主要是数字更新 |
| 验证 | 20 min | 跑全量 + 修边角 |
| **合计** | **约 2.5~3h** | |

---

## 8. 待用户确认

1. **执行时机**：在 Phase 3A M8 之前做数据库升级，还是 M8 之后做？（建议 M8 之前，这样 baseline 就在新库上跑）
2. **数据量**：orders 5000 是否合适？还是直接上 20000？（数据量大 = seed 跑得慢，但对 agent 挑战更大）
3. **`products.category` 改造**：保留冗余字符串列 + 新增 `category_id` FK，还是直接替换？（建议保留冗余，模拟历史遗留）
4. **第二期范围**：是否需要现在就把 suppliers / inventory / SCD 也规划详细？还是先聚焦第一期？

---

> **关联文档**：
> - 阶段三A 计划：[phase3a-plan.md](phase3a-plan.md)
> - 技术档案：[AI_CONTEXT.md](AI_CONTEXT.md)
> - 总路线：[LEARNING_ROADMAP_v3.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP_v3.md)
