# product_categories

## 业务含义

商品类目层级维表，用于表达一级类目、二级类目和叶子类目的树形关系。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 类目主键 | join_key | normal |
| name | 类目名称 | dimension | normal |
| parent_id | 父类目 ID，NULL 表示一级类目 | join_key | normal |
| level | 类目层级，1 表示一级类目 | filter | normal |
| sort_order | 展示排序 | dimension | normal |
| status | 类目状态 | filter | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 关联关系

- product_categories.parent_id -> product_categories.id
- products.category_id -> product_categories.id

## 指标口径

- 查询一级类目及其所有子类目时，需要递归展开 `parent_id` 后再关联 `products`。
