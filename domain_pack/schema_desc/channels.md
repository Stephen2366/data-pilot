# channels

## 业务含义

渠道维表，用于分析不同流量来源或销售渠道的订单量和 GMV 表现。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 渠道主键 | join_key | normal |
| channel_code | 渠道编码 | dimension | normal |
| channel_name | 渠道名称 | dimension | normal |
| channel_type | 渠道类型：owned / marketplace / paid / partner | dimension | normal |
| status | 渠道状态 | filter | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 评测锚点

- `Mobile App` 是 2026-06 GMV 最高渠道。
