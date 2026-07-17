# users

## 业务含义

系统用户与客户基础信息表。既用于订单、退款、工单关联，也用于后续 RBAC 权限判断。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 用户主键 | join_key | normal |
| user_name | 用户展示名 | dimension | normal |
| role | 角色：admin / ops / customer_service / demo_user | filter | normal |
| email | 邮箱 | identifier | sensitive |
| phone | 手机号 | identifier | sensitive |
| status | 用户状态 | filter | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 关联关系

- `orders.user_id -> users.id`
- `refunds.user_id -> users.id`
- `tickets.user_id -> users.id`
- `tickets.assigned_user_id -> users.id`
