# Phase 2.7 database upgrade notes

- [x] 表结构：新增 7 张业务表 + 1 张桥接表，旧表保留兼容字段。
- [x] Migration：生成单个可升级 / 可回滚版本，Alembic metadata 能看到 14 张物理表。
- [x] Seed：确定性生成 1 万级订单、约 1.8 万明细、9 个固定事实和 seed summary。
- [x] 兼容：M2 API、M6 smoke、现有模板 SQL 仍能跑旧问题。
- [x] Domain pack：补 schema_desc、relations.yaml、metrics、few-shot examples。
- [x] Eval：新增 database-upgrade challenge 与 phase3a regression YAML，不要求 trace_steps。
- [x] 测试：覆盖表数量、seed 行数、固定事实、challenge 可加载、安全基础用例。
- [x] 收尾：把计划 / 代码冲突与验证结果写入 AI_CONTEXT.md。

## Decisions / gotchas

- 兼容字段保留：`orders.product_id` 和 `products.category` 没有下线，旧模板 SQL / M2 API / M6 smoke 继续可用；商品维度新口径在 metrics 和 schema_desc 中指向 `order_items`。
- 固定事实定位：seed 外键用 ORM 对象关系，固定事实用 `sku/coupon_code/channel_code/category/device_type` 等业务键，不依赖自增 ID 从 1 开始。
- MySQL downgrade：新 seed 有 20 条 `orders.paid_at IS NULL`，downgrade 回旧 schema 前需要回填 `paid_at=COALESCE(created_at, NOW())`；新表 drop table 优先，避免外键索引逐个 drop 被 MySQL 拦截。
- `coupons.coupon_code` 只保留 unique constraint，不额外建普通索引；否则 Alembic check 会报告 metadata diff。
- `scripts.seed_data` 命令行入口必须先导入 `app.db.base` 再导入 `app.models` 聚合包，沿用现有循环导入规避方式。
