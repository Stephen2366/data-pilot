# products

## 业务含义

商品维表，用于按商品、类目分析订单、GMV、退款率和售后问题。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 商品主键 | join_key | normal |
| sku | 商品编码 | dimension | normal |
| product_name | 商品名称 | dimension | normal |
| category | 商品类目 | dimension | normal |
| status | 商品状态 | filter | normal |
| price | 商品标价 | metric | normal |
| launched_at | 上架时间 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 评测锚点

- `Aurora Noise Cancelling Headphones` 是 2026-06 退款率最高商品。
