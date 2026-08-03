# Phase 2.7.1 database polish notes

- [x] 评估外部审查：只执行进入 M8 前必要的数据库 polish。
- [x] 保留 `user_behavior_log` 显式外键实现，改为文档记录偏离。
- [x] 补 `orders_wide` 预聚合字段：item/refund/role/price/update time。
- [x] 补 `coupons(valid_from, valid_to)` 索引。
- [x] 补 `product_price_history.change_reason`，保留 `price_source`。
- [x] 同步 schema_desc / 数据库速查。
- [x] 同步 AI_CONTEXT。
- [x] 执行 migration、seed reset、pytest 验证。
