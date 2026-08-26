# DataPilot 数据库当前事实速查

> 给后续 AI / Agent 接手用：先用这份文档快速理解当前数据库底座、指标口径、固定 seed 事实和 SQL 业务边界。Trigger：只要涉及 SQL、字段、表、指标、seed、expected SQL、`result_match` 或数据库事实，必须先读本文。
>
> **事实来源分工**：表字段、索引和迁移以 Alembic / ORM 为准；指标公式以 `domain_pack/metrics.yaml` 为准；表关系以 `domain_pack/schema_desc/relations.yaml` 为准；本文只负责把这些当前事实和容易踩坑的业务规则讲清楚。归档设计背景见 `docs/archive-versions/database-upgrade-plan-v5.md`，完整技术取舍统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

更新时间：2026-08-27

## 一句话结论

DataPilot 当前 schema 有 **14 张业务物理表 + 2 张 Agent task 状态基础设施表**；Text2SQL 只暴露其中 **13 张可查询分析表**，明确排除 `knowledge_docs` 和两张基础设施表。主路径是 **MySQL `datapilot_dev` + SQLAlchemy ORM + Alembic**，seed 由 `scripts/seed_data.py` 确定性生成 **1 万级真实感业务数据**。知识 authority 位于 `domain_pack/kb_docs/` 与 `metrics.yaml`，物理 `knowledge_docs` 只是 source-backed builder 生成的 legacy 兼容投影。M48 Probe 只在隔离库 `datapilot_m48_test` 验证了 0005、Context 原子提交与清理；本机 `datapilot_dev` 按用户禁区仍未迁移，产品 task runtime 启动前必须正常升级到 0005。

## 关键入口

- 基础升级迁移：`alembic/versions/20260722_0002_database_upgrade_14_tables.py`
- 审查后 polish 迁移：`alembic/versions/20260722_0003_phase27_database_polish.py`
- M47 durable task state：`alembic/versions/20260826_0004_m47_durable_task_state.py`
- M48 task Context/Compact：`alembic/versions/20260827_0005_m48_task_context_compact.py`
- Seed 主逻辑：`scripts/seed_data.py`
- ORM 模型：`app/models/`
- Alembic metadata 注册：`app/db/base.py`
- 表结构自然语言描述：`domain_pack/schema_desc/*.md`
- 结构化关系事实源：`domain_pack/schema_desc/relations.yaml`
- 指标口径事实源：`domain_pack/metrics.yaml`
- 政策/规则事实源：`domain_pack/kb_docs/*.md`
- Staged catalog builder：`engine/rag/catalog.py`
- Few-shot 示例：`domain_pack/sql_examples/basic.yaml`
- M27 当前 case catalog：`eval/cases/catalog/scenarios.yaml`
- 当前 Eval 运行入口与 Gate：`docs/state/runbook.md`
- 当前 Eval 基线与失败归因：`docs/state/eval-baselines.md`
- 数据库升级测试：`tests/test_database_upgrade.py`
- Seed 摘要输出：`eval/reports/database-upgrade-seed-summary.md`

## 当前 14 张业务表与 2 张状态基础设施表

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
| `knowledge_docs` | 11（本机现有库）/ 22（当前 reset 目标） | legacy 知识投影 | 兼容既有物理表/seed | 当前 `scripts/seed_data.py --reset` 会由 22-entry staged catalog 派生 22 行；不属于 Text2SQL queryable universe，字段有损，不得作为 authority、正式 ACL 或 runtime catalog |
| `coupons` | 10 | 优惠券 | 券信息、券类型、有效期 | 固定券码 `JUNE_FIXED_50` |
| `order_coupons` | 3000 | 订单-优惠券桥接 | 优惠券使用率、券渠道分析 | 多对多桥接表，一单可多券，订单数要去重 |
| `user_behavior_log` | 10000 | 用户行为事件 | 加购到支付转化率、设备分析 | 转化率按 `event_type` 事件计数，不是订单表 |
| `product_price_history` | 150 | 商品价格版本 | 历史售价、指定时间价格 | 查询历史价格必须匹配 `valid_from` / `valid_to` |
| `orders_wide` | 10000 | 订单宽表快照 | 看板类渠道 / 商品 / 用户 / 退款汇总 | 业务月份按 `paid_at`；`snapshot_at/batch_id` 只选快照版本；精确明细、退款链路回星型表 |

`knowledge_docs` 是当前唯一需要区分“本机既有物理数据”和“当前 seed 合同”的表：2026-08-17 只读查询本机 `datapilot_dev` 仍为 11 行，而代码与测试已冻结下一次 reset 为 22 行。该差异不影响当前 Knowledge runtime，因为权威输入和 active release 都不读取此表；只有明确执行 seed reset 后，本机物理行数才会变为 22。

M47 另增加两张不进入 Text2SQL schema、RBAC 表集或业务 seed 的基础设施表：

| 表 | 当前职责 | 关键边界 |
|---|---|---|
| `agent_task_checkpoints` | 保存当前 task lifecycle、owner/tenant/active-role binding、version/claim token/TTL、closed-world TaskState 与 bounded Context/Compact payload | state/context/event 同 claim 原子提交；terminal/clear/expiry 立即 scrub；不保存 rows、正文、答案、Prompt、凭据、Thought 或 program counter |
| `agent_task_events` | 保存按 task/version 排序的 typed lifecycle/action 安全摘要；M48 新写 event v2，旧 v1 仍可读但不能冒充完整 Compact source | 只保存不可逆 safe ref 和 allowlisted typed summary，不保存 raw recent turn，也不作为正文/Trace 旁路 |

两张表由 0004 创建，0005 只给 checkpoint additive 增加 context schema/identity/payload/source watermark 四列，表数量不变；它们不属于 `EXPECTED_SEED_COUNTS` 的 14 张业务表，模型回归分别核对业务表集合与基础设施表集合。M48 真实 MySQL Probe 只在 `datapilot_m48_test` 创建 Agent synthetic 行并最终清零；为 SQL oracle 写入的 Phase 4B deterministic business seed按授权保留，未访问 `datapilot_dev`。

## 兼容字段和新旧口径

- `orders.product_id` 仍保留，表示订单主商品，主要为了阶段二旧 API、模板 SQL、M6 smoke 兼容。
- 商品维度 GMV / 销量默认不要用 `orders.product_id`，应走 `orders -> order_items -> products`。
- `products.category` 仍保留，表示旧版冗余类目字符串；规范类目层级走 `products.category_id -> product_categories.id`。
- `orders.paid_at` 现在允许为空；GMV、净收入等成交口径默认排除 `paid_at IS NULL`。
- `order_status` 完整取值：`delivered`（3371）、`paid`（3091）、`shipped`（3089）、`cancelled`（421，双 l）、`pending_payment`（20，即 `paid_at IS NULL` 的 20 条）、`canceled`（8，单 l）。成交口径需同时排除 `cancelled` 和 `canceled`；`pending_payment` 不需要显式排除（`paid_at IS NOT NULL` 已将其过滤），但写 prompt / schema_desc 时不应漏掉此状态。
- `orders.source_order_no` / `orders.external_order_no` 格式为 `SRC-2026-XXXXX`，`orders.order_no` 格式为 `ORD-2026-XXXXX`——两者是**不同的编号体系，不能 join**。`refunds.source_order_no` 同为 SRC 格式，模拟外部源系统追溯；退款关联订单的唯一正确路径是 `refunds.order_id -> orders.id`。
- `orders_wide` 保留 `refund_count` / `total_refund` / `has_refund` / `item_count` 等快照字段，用于快速看板汇总；强一致诊断仍回到星型模型。
- `product_price_history.price_source` 是数据来源，`change_reason` 是业务调价原因；后续写 prompt / plan 时不要混成一个字段。

## 宽表使用规则

`orders_wide` 是为看板查询准备的订单快照，不是星型模型的替代品：

- **按月看板**：按 `orders_wide.paid_at` 过滤订单业务月份；`snapshot_at` 是抽取时间，`batch_id` 是快照批次，二者只用于选择版本。
- **渠道 / 商品 / 用户的快速汇总**：可使用宽表已有的快照与预聚合字段。
- **精确订单金额、退款归因、复杂 Join 或强一致对账**：回到 `orders`、`order_items`、`refunds` 等星型明细表，并套用对应指标口径。

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

更完整的机器可读关系在 `domain_pack/schema_desc/relations.yaml`；任何 relation document / JoinPath 都应优先从这里生成，不要靠 prompt 临场猜。

## 指标默认口径

- `gmv`：`SUM(orders.order_amount)`，过滤 `orders.order_status NOT IN ('cancelled', 'canceled') AND orders.paid_at IS NOT NULL`。
- `item_gmv`：`SUM(order_items.line_amount)`，关联 `orders` 后套用成交过滤。
- `net_revenue`：`SUM(orders.actual_amount)`，其中 `actual_amount = order_amount + shipping_amount - discount_amount`。
- `refund_rate`：成交订单内的已完成退款去重订单数 / 成交去重订单数；分子只统计 `refund_status='completed'`。商品维度优先用 `refunds.order_item_id -> order_items.product_id` 的订单明细归因。整单退款的 `order_item_id` 为空时，使用 `refunds.product_id` 作为唯一兼容回退，不能因 INNER JOIN 被丢弃，也不能复制归因给同订单每个商品。
- `net_refund_amount`：实际已完成退款的带符号金额，`SUM(refunds.refund_amount)`，过滤 `refund_status = 'completed'` 并按 `processed_at` 取时间窗口；负数是冲销修正，必须保留。
- `coupon_usage_rate`：`COUNT(DISTINCT order_coupons.order_id) / COUNT(DISTINCT orders.id)`。
- `add_to_pay_conversion_rate`：从 `user_behavior_log` 计算支付成功事件数 / 加购事件数，可按 `device_type` 分组。
- `avg_selling_price`：从 `product_price_history` 取与时间窗口相交的有效记录，按记录条数计算 `price` 算术平均值，不按有效天数加权。

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

### Phase 4B 显式 seed profile

M42 新增与默认 legacy 隔离的 `phase4b` profile；它仍只使用既有 14 张业务表，不读写 M47 两张状态基础设施表。只有调用 `seed_database(..., profile_alias="phase4b")` 才会在隔离副本内追加 23 条订单/明细/退款/宽表事实，并生成 content-bound identity；默认调用和命令行仍保持 legacy。

- profile identity：`9c49407708bcc8c1ce8b9e990fbfbff8d9a75dc1cd0dee798fb165f93af00673`
- oracle identity：`be813a868e7cb163807f3d9559121c11ef837b8960c2ef466e75b6dddd57ef80`
- 2026-07 / 2026-08 `net_refund_amount`：`120000.00 / 180000.00`；原因、渠道、商品三种分解各自守恒；星型表与该 profile 的宽表总额一致；每月各保留 1 条负数冲销。
- legacy 6 月末退款会自然滑入 7 月。显式 profile 为保持同一产品 SQL 口径，只在该隔离副本内把 103 条 spillover 固定到 6 月末；不会修改默认 legacy recipe 或历史 artifact。

完整边际表和 recipe 以 `domain_pack/phase4b/seed_profile.json` 为事实源；本节只保存运行时需立即知道的 identity、总额和隔离边界。

## 数据质量与易错规则

Phase 2.7 的 seed 有意保留少量真实业务异常，供 Text2SQL 诊断使用；它们不是默认要清掉的脏数据。写 SQL 或排查结果时，优先按下表处理：

| 场景 | 应该怎么写 / 查 | 当前事实 | 容易错在哪里 |
|---|---|---|---|
| 未支付订单 | 成交指标使用 `paid_at IS NOT NULL` | `pending_payment` 20 条，`paid_at IS NULL` | 多算 GMV / 净收入；误写不存在的 `unpaid` 状态 |
| 取消状态拼写差异 | 同时排除 `cancelled` 和 `canceled` | 双 l 421 条；单 l 8 条 | 只排一种拼写，成交指标偏高 |
| 外部单号 | 退款只按 `refunds.order_id -> orders.id` 关联 | `SRC-*` 与 `ORD-*` 是两套编号；外部单号各有 20 条重复 | 用不同命名空间的单号 join，得到空或错结果；把外部单号当唯一主键 |
| 整单退款 | 商品退款率用 LEFT JOIN；空 `order_item_id` 回退 `refunds.product_id` | 100 条退款单的 `order_item_id` 为空 | INNER JOIN 丢掉整单退款；把退款重复分给同订单每个商品 |
| 负数退款冲销 | `completed` 退款按 `processed_at` 聚合，保留带符号金额 | 3 条 `refund_amount=-20.00` | 擅自过滤负数，破坏财务冲销口径 |
| 订单头 / 明细金额 | `gmv` 用订单头，`item_gmv` 用明细；需要时单独对账 | 5 条 `orders.order_amount ≠ SUM(order_items.line_amount)` | 混用两种金额，导致结果或判分争议 |

## 数据库相关 Eval 失败排查入口

> 本表更新于 M27 时期

| assertion / 现象 | 优先查什么 | 不要先做什么 |
|---|---|---|
| `result_match` | 固定业务事实、指标默认口径、数据质量与易错规则、oracle 是否使用正确粒度 | 不要立刻改模型 prompt 或放宽 scorer |
| `schema_context` / 漏列 | 字段是否真实存在、`domain_pack/schema_desc/*.md` 是否漏写、字段别名是否清楚 | 不要直接把缺列写进 eval case 当标准 |
| `schema_retrieval` / 漏表 | 当前 14 表用途、`relations.yaml`、指标依赖的表和 join path | 不要让 LLM 临场猜 join |
| 安全拦截相关 | RBAC / 敏感字段策略、SQL Guard 是否正确识别只读和敏感字段 | 不要为了通过率放宽安全策略 |
| 指标口径争议 | `domain_pack/metrics.yaml`、本文件「指标默认口径」、固定业务事实 | 不要混用订单头 GMV 和明细 GMV |
| timeout / `not_observed` | 同一 `run_id` 的 checkpoint、artifact 与运行环境 | 不要把外部不可用误当成业务 failed；处理方式看 `runbook.md` |

## RBAC / 安全边界

- Text2SQL 表级 RBAC 只面向 13 张 queryable tables；SQLAlchemy/Alembic 的 14 张业务表加 2 张状态基础设施表不是权限全集，后两张也绝不进入 NL2SQL schema。
- Text2SQL 安全口径：**敏感字段优先于角色权限**，`admin` 也不能通过自然语言 Text2SQL 直出 `users.email` / `users.phone` 明文字段；如后续确需查看，应设计脱敏 / 审计 / 专门接口。
- `admin` / `ops`：可访问全部 13 张 queryable tables，但不能查 `users.email` / `users.phone` 等敏感字段。
- `customer_service`：Text2SQL 仅可访问 `tickets`。
- `demo_user`：Text2SQL 仅可访问 `products`、`channels`、`product_categories`、`orders_wide`。
- 所有角色都不能通过 Text2SQL 查询 `knowledge_docs`；当前文档访问已经走 trusted caller + Knowledge Tool ACL seam。生产认证 resolver 尚未建设，不能把本地 fixture 身份外推为生产权限。
- SQL Guard 仍要求只读 SQL；`DROP` / `DELETE` / `UPDATE` / 多语句 / 越权表字段都应拦截。

权限事实源是 `engine/sql_guard/rbac.py`。新增表或新增角色时，要同步测试安全 case。

## 改库时的注意事项

- 任何表结构变化都要同步：ORM 模型、Alembic migration、`app/db/base.py` metadata 注册、schema_desc、relations、metrics 或 examples、测试。
- Seed 要保持确定性和可复现，不要逐行写死大数据量，也不要依赖自增 ID 起始值。
- 固定事实要用业务键定位，避免 MySQL `DELETE` 不重置自增导致测试脆弱。
- MySQL DDL 非事务性：downgrade 失败后可能留下半迁移状态，修 migration 时要考虑表和索引真实存在情况。
- 回滚 `orders.paid_at` 为 NOT NULL 前必须先处理 NULL 值。
- `coupons.coupon_code` 当前只保留 unique constraint，不额外建同名普通索引，避免 Alembic diff。
- `coupons` 已有 `ix_valid_range(valid_from, valid_to)`，优惠券有效期查询优先使用这组字段。
- `app.db.base` 目前兼具 Base 定义和模型注册，导入顺序不当可能触发循环导入；脚本入口优先导入 `app.db.base` 再用模型。

## 数据库验证入口

数据库维护、seed 重建、Alembic 检查和回归命令统一维护在 `docs/state/runbook.md`；本文只定义应当被验证的当前数据库事实。当前 pytest / Eval / 模型 A/B 数字统一查 `docs/state/eval-baselines.md`，历史设计与验收从 `docs/state/CHANGELOG_INDEX.md` 进入。
