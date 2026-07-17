# tickets

## 业务含义

客服工单事实表，用于分析售后工作量、优先级、处理状态和问题类型。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 工单主键 | join_key | normal |
| ticket_no | 工单号 | identifier | normal |
| user_id | 提交工单用户 | join_key | normal |
| order_id | 关联订单，可为空 | join_key | normal |
| assigned_user_id | 分配客服，可为空 | join_key | normal |
| ticket_type | 工单类型 | dimension | normal |
| priority | 优先级：low / medium / high / urgent | filter | normal |
| status | 工单状态：pending / processing / resolved / closed | filter | normal |
| subject | 工单标题 | text | normal |
| description | 工单详情 | text | normal |
| resolved_at | 解决时间 | time | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 评测锚点

- 待处理高优先级工单数量固定为 12。
