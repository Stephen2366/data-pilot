# knowledge_docs

## 业务含义

知识库文档表，阶段二先放政策和规则草稿，后续 RAG 模块会用于文档检索。

## 字段说明

| 字段 | 含义 | 语义角色 | 敏感级别 |
|---|---|---|---|
| id | 文档主键 | join_key | normal |
| doc_key | 文档编码 | identifier | normal |
| title | 文档标题 | text | normal |
| doc_type | 文档类型：refund_policy / support_rule / security_policy / metric_definition | filter | normal |
| audience_role | 可见角色 | filter | normal |
| status | 文档状态 | filter | normal |
| content | 文档正文 | text | normal |
| created_at | 创建时间 | time | normal |
| updated_at | 更新时间 | time | normal |

## 安全说明

- 当前文档不存放手机号、邮箱等用户敏感信息。
