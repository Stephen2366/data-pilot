# product_price_history

## 业务含义

商品价格历史表，使用 SCD Type 2 表达一个商品在不同时间窗口内的售价。

## 粒度

一行对应一个商品的一段价格生效窗口。

## 何时使用

- 查询某个历史时间点或时间窗口内的商品售价。
- 分析调价原因、促销恢复、当前价与历史价差异。

## 何时避免

- 只问商品当前标价时，优先用 `products.price`。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 价格版本主键 | join_key | normal |
| product_id | 关联商品 | join_key | normal |
| price | 该时间窗口内的售价 | metric | normal |
| valid_from | 价格生效时间 | time | normal |
| valid_to | 价格失效时间，NULL 表示当前价 | time | normal |
| is_current | 是否当前价格版本 | filter | normal |
| price_source | 价格来源 | dimension | normal |
| change_reason | 调价原因 | dimension | normal |
| created_at | 创建时间 | time | normal |

## 关联关系

- product_price_history.product_id -> products.id

## 指标口径

- 查询历史售价时用 `target_time >= valid_from AND (target_time < valid_to OR valid_to IS NULL)`。
- 查询当前标价优先用 `products.price`。

## 数据质量说明

- `price_source` 是数据来源元数据，`change_reason` 是业务调价原因；两者语义不同，不要混用。
