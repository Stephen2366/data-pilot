# DataPilot 数据库当前状态速查（Phase 2.7 / 2.7.1 后）

> 给后续 AI / Agent 接手用：先用这份文档快速理解当前数据库底座、指标口径、固定 seed 事实和后续写 plan 时的边界。Trigger：只要涉及 SQL、字段、表、指标、seed、expected SQL、`result_match` 或数据库事实，必须先读本文。当前数据库事实以本文档和 migrations `20260722_0002` / `20260722_0003` 为准；归档设计背景见 `docs/archive-versions/database-upgrade-plan-v5.md`，完整技术取舍见 `docs/state/AI_CONTEXT_CHANGELOG.md`「变更记录」Phase 2.7 / 2.7.1 条目。

更新时间：2026-08-02

## 一句话结论

DataPilot 当前数据库已经从阶段二的 7 表 demo 底座升级为 **14 张物理表**，并通过 `20260722_0003` polish 补齐宽表字段、优惠券有效期索引和价格历史调价原因字段。主路径是 **MySQL `datapilot_dev` + SQLAlchemy ORM + Alembic**，seed 由 `scripts/seed_data.py` 确定性生成 **1 万级真实感业务数据**。Phase 3A 之后的 Text2SQL / Eval / RAG-Hybrid 工作都默认基于这个 14 表新库，不再回到旧 7 表库。

## 关键入口

- 基础升级迁移：`alembic/versions/20260722_0002_database_upgrade_14_tables.py`
- 审查后 polish 迁移：`alembic/versions/20260722_0003_phase27_database_polish.py`
- Seed 主逻辑：`scripts/seed_data.py`
- ORM 模型：`app/models/`
- Alembic metadata 注册：`app/db/base.py`
- 表结构自然语言描述：`domain_pack/schema_desc/*.md`
- 结构化关系事实源：`domain_pack/schema_desc/relations.yaml`
- 指标口径事实源：`domain_pack/metrics.yaml`
- Few-shot 示例：`domain_pack/sql_examples/basic.yaml`
- 数据库升级挑战集：`eval/cases/database-upgrade-challenge.yaml`
- Phase 3A 正式回归输入：`eval/cases/phase3a-regression.yaml`（10 条 formal 主硬门）
- Phase 3A challenge 输入：`eval/cases/database-upgrade-challenge.yaml`（16 条 challenge superset，包含 10 条 formal question）
- 数据库升级测试：`tests/test_database_upgrade.py`
- Seed 摘要输出：`eval/reports/database-upgrade-seed-summary.md`

## 当前 14 张物理表

| 表 | 行数 | 粒度 | 主要用途 | 使用提醒 |
| --- | ---: | --- | --- | --- |
| `users` | 200 | 用户 | 用户维度、角色、状态、客服归属 | `email` / `phone` 是敏感字段；Text2SQL 明文直出按敏感字段优先策略拦截 |
| `product_categories` | 15 | 商品类目节点 | 一级类目、子类目、递归层级 | 查父类目及所有子类目时用递归 CTE |
| `products` | 50 | 商品 | 商品基础信息、当前价、兼容旧类目字段 | `category` 是兼容冗余，规范类目优先 `category_id` |
| `channels` | 6 | 渠道 | 渠道 GMV、订单量、行为来源 | 固定事实常用 `Mobile App` |
| `orders` | 10000 | 订单头 | 订单级 GMV、净收入、订单状态 | 订单级指标优先用这张表 |
| `order_items` | 18000 | 订单明细行 | 商品维度 GMV、销量、明细退款归因 | Join 后统计订单量必须 `COUNT(DISTINCT orders.id)` |
| `refunds` | 1000 | 退款单 | 退款量、退款原因、退款率 | `order_item_id` 有 100 条为空（10%），属于整单退款，只能通过 `order_id` 关联；商品维度退款率必须用 LEFT JOIN，INNER JOIN 会丢 10% |
| `tickets` | 300 | 客服工单 | 高优先级待处理、客服问题分析 | `order_id` 可空，咨询类工单不一定绑定订单 |
| `knowledge_docs` | 10 | 知识库文档 | RAG / 客服规则语料 | 后续 RAG 会继续使用 |
| `coupons` | 10 | 优惠券 | 券信息、券类型、有效期 | 固定券码 `JUNE_FIXED_50` |
| `order_coupons` | 3000 | 订单-优惠券桥接 | 优惠券使用率、券渠道分析 | 多对多桥接表，一单可多券，订单数要去重 |
| `user_behavior_log` | 10000 | 用户行为事件 | 加购到支付转化率、设备分析 | 转化率按 `event_type` 事件计数，不是订单表 |
| `product_price_history` | 150 | 商品价格版本 | 历史售价、指定时间价格 | 查询历史价格必须匹配 `valid_from` / `valid_to` |
| `orders_wide` | 10000 | 订单宽表快照 | 看板类渠道 / 商品 / 用户 / 退款汇总 | 含预聚合退款字段，适合快速汇总，不适合强一致明细追溯 |

## 兼容字段和新旧口径

- `orders.product_id` 仍保留，表示订单主商品，主要为了阶段二旧 API、模板 SQL、M6 smoke 兼容。
- 商品维度 GMV / 销量默认不要用 `orders.product_id`，应走 `orders -> order_items -> products`。
- `products.category` 仍保留，表示旧版冗余类目字符串；规范类目层级走 `products.category_id -> product_categories.id`。
- `orders.paid_at` 现在允许为空；GMV、净收入等成交口径默认排除 `paid_at IS NULL`。
- `order_status` 完整取值：`delivered`（3371）、`paid`（3091）、`shipped`（3089）、`cancelled`（421，双 l）、`pending_payment`（20，即 `paid_at IS NULL` 的 20 条）、`canceled`（8，单 l）。成交口径需同时排除 `cancelled` 和 `canceled`；`pending_payment` 不需要显式排除（`paid_at IS NOT NULL` 已将其过滤），但写 prompt / schema_desc 时不应漏掉此状态。
- `orders.source_order_no` / `orders.external_order_no` 格式为 `SRC-2026-XXXXX`，`orders.order_no` 格式为 `ORD-2026-XXXXX`——两者是**不同的编号体系，不能 join**。`refunds.source_order_no` 同为 SRC 格式，模拟外部源系统追溯；退款关联订单的唯一正确路径是 `refunds.order_id -> orders.id`。
- `orders_wide` 保留 `refund_count` / `total_refund` / `has_refund` / `item_count` 等快照字段，用于看板选表挑战；强一致诊断仍回到星型模型。
- `product_price_history.price_source` 是数据来源，`change_reason` 是业务调价原因；后续写 prompt / plan 时不要混成一个字段。

## 关键关系

- `orders.user_id -> users.id`：按用户状态、角色、用户维度分析时使用。
- `orders.channel_id -> channels.id`：渠道订单量、渠道 GMV、渠道退款分析使用。
- `orders.product_id -> products.id`：仅作为主商品兼容关系，商品维度分析优先避开。
- `order_items.order_id -> orders.id`：订单明细回订单头，用于商品维度指标套用支付 / 取消过滤。
- `order_items.product_id -> products.id`：商品 TopN、商品销量、商品退款归因使用。
- `refunds.order_item_id -> order_items.id`：商品退款率优先关系，但可空，不能无脑 inner join。
- `orders -> order_coupons -> coupons`：多对多桥接，一单多券会放大行数。
- `products.category_id -> product_categories.id`：规范类目关系。
- `product_categories.parent_id -> product_categories.id`：类目树递归关系。
- `product_price_history.product_id -> products.id`：SCD Type 2 风格价格历史，查询历史价要带时间窗口。
- `user_behavior_log` 当前采用显式 `product_id` / `channel_id` 外键，而不是 plan 草案里的 `target_type` / `target_id` 多态列；这是为了参照完整性和 SQL 可生成性保留的有意偏离。

更完整的机器可读关系在 `domain_pack/schema_desc/relations.yaml`，后续 M9 relation_doc / JoinPath 应优先从这里生成，不要靠 prompt 临场猜。

## 指标默认口径

- `gmv`：`SUM(orders.order_amount)`，过滤 `orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL`。
- `item_gmv`：`SUM(order_items.line_amount)`，关联 `orders` 后套用成交过滤。
- `net_revenue`：`SUM(orders.actual_amount)`，其中 `actual_amount = order_amount + shipping_amount - discount_amount`。
- `refund_rate`：退款数 / 订单数；商品维度优先用 `refunds.order_item_id -> order_items.product_id`，兼容 `refunds.product_id`。
- `coupon_usage_rate`：`COUNT(DISTINCT order_coupons.order_id) / COUNT(DISTINCT orders.id)`。
- `add_to_pay_conversion_rate`：从 `user_behavior_log` 计算支付成功事件数 / 加购事件数，可按 `device_type` 分组。
- `avg_selling_price`：从 `product_price_history` 按时间窗口匹配后聚合。

指标口径唯一事实源是 `domain_pack/metrics.yaml`。写 SQL、写 plan 或改 prompt 时，先看这里，不要把 GMV / 净收入 / 商品 GMV 混成一个概念。

## 固定业务事实

当前 seed 的固定事实用于测试和后续 Text2SQL baseline：

- 2026 年 6 月 GMV：`11285752.00`
- 2026 年 6 月退款率最高商品：`Aurora Noise Cancelling Headphones`
- 2026 年 6 月 GMV 最高渠道：`Mobile App`
- Top 退款原因：`quality_issue`
- 待处理高优先级工单数：`12`
- `JUNE_FIXED_50` 使用最多渠道：`Mobile App`
- 2026 年 6 月一级类目 GMV Top：`数码电子`
- Aurora 耳机 2026 年 6 月历史均价：`899.00`
- 加购到支付转化率最高设备类型：`mobile_app`
- `orders_wide` 与星型模型按渠道 GMV 对账：`True`
- 模拟金额不一致订单数：`5`

这些事实由 `scripts/seed_data.py` 的 `verify_business_facts()` 用真实 SQL 查询得出。不要依赖自增 ID 从 1 开始定位这些事实，必须使用 `sku`、`coupon_code`、`channel_code`、`category.name`、`device_type` 等稳定业务键。

## 数据质量设计

Phase 2.7 的 seed 不是纯净玩具数据，包含少量真实业务常见问题：

- 未支付订单：20 条 `order_status = 'pending_payment'` 且 `paid_at IS NULL`。成交指标必须用 `paid_at IS NOT NULL` 排除；不要猜 `order_status = 'unpaid'`——该状态不存在。
- 取消状态拼写差异：`cancelled`（421 条，双 l）/ `canceled`（8 条，单 l）都可能出现，成交口径要同时排除。
- 外部源系统单号重复：各 20 条重复（10000 条中 9980 distinct），不破坏主键和唯一约束。
- 外部源系统单号命名空间不兼容：`source_order_no` 格式为 `SRC-2026-XXXXX`，`order_no` 为 `ORD-2026-XXXXX`，**不能 join**。退款关联订单的唯一正确路径是 `refunds.order_id -> orders.id`。
- 整单退款：`refunds.order_item_id` 有 100 条为空（10%），只通过 `order_id` 关联。商品维度退款率必须 LEFT JOIN `order_items`；INNER JOIN 会丢失这 100 条。
- 负数退款冲销：3 条 `refund_amount = -20.00`，状态分别为 completed / requested / rejected。
- 金额不一致样例：固定 5 条 `orders.order_amount ≠ SUM(order_items.line_amount)`。

写 plan 时不要把这些当成 bug 清掉，除非用户明确要求“清洗数据”。它们是后续 Text2SQL 诊断能力的训练素材。

## 数据异常菜单

| 异常 / 彩蛋 | 表 / 字段 | 数量 | 设计目的 | 容易导致的 eval 问题 |
|---|---|---:|---|---|
| 未支付订单 | `orders.order_status='pending_payment'`，`paid_at IS NULL` | 20 | 检查成交口径是否用 `paid_at IS NOT NULL` 过滤 | GMV / 净收入多算；模型幻想不存在的 `unpaid` 状态 |
| 取消状态拼写差异 | `orders.order_status` | `cancelled=421`，`canceled=8` | 检查状态枚举鲁棒性 | 只排除一种拼写导致成交指标偏高 |
| 外部源系统单号重复 | `orders.source_order_no` / `external_order_no` | 各 20 条重复；9980 distinct | 模拟外部系统幂等 / 去重边界 | 错把外部单号当唯一业务主键 |
| 外部单号命名空间不兼容 | `source_order_no` vs `order_no` | 全量格式不同 | 检查 join path 是否尊重真实关系 | 用 `SRC-*` join `ORD-*` 导致空结果或错结果 |
| 整单退款 | `refunds.order_item_id IS NULL` | 100（退款单 10%） | 检查商品退款率的 LEFT JOIN / 归因边界 | INNER JOIN 丢退款；商品维度退款率偏低 |
| 负数退款冲销 | `refunds.refund_amount=-20.00` | 3 | 模拟退款冲销 / 财务修正 | 退款金额求和、异常值过滤口径争议 |
| 订单头与明细金额不一致 | `orders.order_amount` vs `SUM(order_items.line_amount)` | 5 | 检查订单头口径和明细口径能否区分 | `result_match` 争议；模型混用 `gmv` / `item_gmv` |

排查 eval 时，先判断失败是否撞上了这张菜单。菜单里的异常是**有意设计的数据质量素材**，不是默认要修掉的脏数据。

## Eval 失败排查入口

| failure_stage / 现象 | 优先查什么 | 不要先做什么 |
|---|---|---|
| `result_match` | 固定业务事实、指标默认口径、数据异常菜单、expected SQL 是否使用正确粒度 | 不要立刻改模型 prompt 或放宽 scorer |
| `schema_context` / 漏列 | 字段是否真实存在、`domain_pack/schema_desc/*.md` 是否漏写、字段别名是否清楚 | 不要直接把缺列写进 eval case 当标准 |
| `schema_retrieval` / 漏表 | 当前 14 表用途、`relations.yaml`、指标依赖的表和 join path | 不要让 LLM 临场猜 join |
| 安全拦截相关 | RBAC / 敏感字段策略、SQL Guard 是否正确识别只读和敏感字段 | 不要为了通过率放宽安全策略 |
| 指标口径争议 | `domain_pack/metrics.yaml`、本文件「指标默认口径」、固定业务事实 | 不要混用订单头 GMV 和明细 GMV |
| Qwen / DeepSeek 重跑差异 | `docs/state/eval-baselines.md` 的重复 case 波动说明 | 不要把三次独立 LLM run 当作同一次 superset 切片 |

## RBAC / 安全边界

- 底层表级 RBAC：`admin` 可访问全部 14 表；`ops` 可访问全部 14 表但不应访问敏感字段；`customer_service` / `demo_user` 只允许访问有限业务表。
- Text2SQL 安全口径：**敏感字段优先于角色权限**，`admin` 也不能通过自然语言 Text2SQL 直出 `users.email` / `users.phone` 明文字段；如后续确需查看，应设计脱敏 / 审计 / 专门接口。
- `ops`：可访问全部 14 表，但不能查 `users.email` / `users.phone` 等敏感字段。
- `customer_service`：仅可访问 `tickets`、`knowledge_docs`。
- `demo_user`：仅可访问 `products`、`channels`、`knowledge_docs`、`product_categories`、`orders_wide`。
- SQL Guard 仍要求只读 SQL；`DROP` / `DELETE` / `UPDATE` / 多语句 / 越权表字段都应拦截。

权限事实源是 `engine/sql_guard/rbac.py`。新增表或新增角色时，要同步测试安全 case。

## Phase 3A 历史使用边界

- Phase 3A M8 baseline 直接跑在 14 表新库上，不做旧 7 表 vs 新 14 表对照。
- `eval/cases/phase3a-regression.yaml` 是 Phase 3A 正式 10 条 formal 回归输入，是 M8-M12 主硬门。
- `eval/cases/database-upgrade-challenge.yaml` 是 16 条 challenge superset，包含 10 条 formal question，并额外覆盖 6 条数据库复杂度诊断题；后续每个模块应同步运行并记录诊断摘要。
- 数据库升级阶段已经验证结构、seed、固定事实、challenge 基础用例、安全和 pytest；不要要求 Phase 3A `trace_steps` 在这个阶段全部通过。
- `schema_retrieval`、`join_path`、`query_plan`、`trace_steps` 属于 Phase 3A M9-M12 的主线工作，不要倒灌回 Phase 2.7。

## 后续 Phase 3 / RAG-Hybrid 使用注意

- 新 SQL 链路需要能区分订单头指标和订单明细指标。
- Schema Retrieval 不应只召回表名，还要召回字段、指标、关系和聚合风险。
- JoinPath 要显式处理桥接表、多对多、类目递归、SCD 时间窗口、宽表 vs 星型模型选择。
- QueryPlanStep 应能声明 `grain`、`metrics`、`filters`、`joins`、`aggregation_risks` 和安全期望。
- Prompt 中要强调 `COUNT(DISTINCT)` 的场景：订单 join 明细、订单 join 优惠券、退款 join 订单。
- 对安全题，正确行为是拦截，不是生成“安全版本 SQL”。
- 对困难诊断题，允许先输出可诊断 trace / issue tag；不要把困难题全部压成 M8 baseline 的通过门槛。

## 改库时的注意事项

- 任何表结构变化都要同步：ORM 模型、Alembic migration、`app/db/base.py` metadata 注册、schema_desc、relations、metrics 或 examples、测试。
- Seed 要保持确定性和可复现，不要逐行写死大数据量，也不要依赖自增 ID 起始值。
- 固定事实要用业务键定位，避免 MySQL `DELETE` 不重置自增导致测试脆弱。
- MySQL DDL 非事务性：downgrade 失败后可能留下半迁移状态，修 migration 时要考虑表和索引真实存在情况。
- 回滚 `orders.paid_at` 为 NOT NULL 前必须先处理 NULL 值。
- `coupons.coupon_code` 当前只保留 unique constraint，不额外建同名普通索引，避免 Alembic diff。
- `coupons` 已有 `ix_valid_range(valid_from, valid_to)`，优惠券有效期查询优先使用这组字段。
- `app.db.base` 目前兼具 Base 定义和模型注册，导入顺序不当可能触发循环导入；脚本入口优先导入 `app.db.base` 再用模型。

## 数据库验证命令

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.agent_work/temp/pytest-db-current
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\smoke.yaml --report eval\reports\latest.md --trace eval/traces/db-current-smoke-traces.jsonl
git diff --check
```

Phase 2.7 历史验收快照：

- Alembic head：`20260722_0003`
- `alembic check`：无新增 migration 操作
- Seed：14 表行数与本文件一致，固定事实与本文件一致
- Pytest：Phase 2.7 验收时为 `31 passed, 1 warning`
- M6 smoke：Phase 2.7 验收时为 `6/6 passed`

当前 pytest / eval / 模型 A/B 基线不要看这里，统一查 `docs/state/eval-baselines.md`；运行命令入口查 `docs/state/runbook.md`。

## 后续 AI 开工前检查清单

- 先读 `docs/state/AI_CONTEXT.md` 当前状态，确认当前阶段 / 当前模块。
- 如果要追溯 Phase 3A 历史设计，读 `docs/phase3a-plan.md` 顶部数据库升级前置说明。
- 如果要写 SQL / Text2SQL plan，读本文件、`domain_pack/metrics.yaml`、`domain_pack/schema_desc/relations.yaml`。
- 如果要改数据库，先读本文档和当前 Alembic head；如需理解历史设计取舍，再读 `docs/archive-versions/database-upgrade-plan-v5.md`。
- 如果看到测试中自增 ID 不从 1 开始，不要修成依赖 ID；改用稳定业务键。
- 如果遇到 challenge 用例失败，先判断是数据库固定事实坏了，还是旧 Text2SQL 链路能力不足；不要误判为 Phase 3A 已失败。
