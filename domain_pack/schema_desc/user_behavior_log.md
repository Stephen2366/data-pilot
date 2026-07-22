# user_behavior_log

## 业务含义

用户行为事件日志，用于漏斗分析、设备转化率和事件序列分析。

## 粒度

一行对应一次用户行为事件。同一个 `session_id` 下可出现多个事件类型。

## 设计说明

Plan v5 曾设想用 `target_type` / `target_id` 多态关联。当前实现改为显式
`product_id` / `channel_id` 外键，并补充 `page_url`、`referrer`，目的是保留参照完整性和更稳定的 SQL 生成路径。

## 何时使用

- 漏斗分析、设备转化率、事件趋势、页面行为分析。

## 何时避免

- 成交 GMV、退款率、净收入等交易指标不要从行为日志推断，应使用订单和退款事实表。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 事件主键 | join_key | normal |
| user_id | 行为用户 | join_key | normal |
| product_id | 关联商品，可为空 | join_key | normal |
| channel_id | 关联渠道，可为空 | join_key | normal |
| session_id | 会话 ID | dimension | normal |
| event_type | 事件类型，如 view_product / add_to_cart / payment_success | filter | normal |
| device_type | 设备类型，如 mobile_app / desktop_web | dimension | normal |
| page_url | 页面路径 | dimension | normal |
| referrer | 来源 | dimension | normal |
| duration_ms | 停留时长，约 10% 为空 | metric | normal |
| event_time | 事件发生时间 | time | normal |
| created_at | 创建时间 | time | normal |

## 关联关系

- user_behavior_log.user_id -> users.id
- user_behavior_log.product_id -> products.id
- user_behavior_log.channel_id -> channels.id

## 指标口径

- 加购到支付转化率：`payment_success` 事件数 / `add_to_cart` 事件数，可按 `device_type` 分组。

## 数据质量说明

- `duration_ms` 约 10% 为空，求平均时数据库会自动跳过 NULL。
- 当前 seed 的 `session_id` 是可复现的会话分组，不承诺完整真实点击路径；Phase 3A 不应把它作为困难 trace 的硬门。
