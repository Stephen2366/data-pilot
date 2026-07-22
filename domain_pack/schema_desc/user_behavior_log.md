# user_behavior_log

## 业务含义

用户行为事件日志，用于漏斗分析、设备转化率和事件序列分析。

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
