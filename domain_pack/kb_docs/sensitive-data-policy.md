---
document_key: sensitive_data_policy
revision: "2026-08-13-r1"
title: 敏感字段访问规范
knowledge_type: security_policy
status: active
anchor: sensitive-data-policy
data_class: security_policy
purposes: [answer_evidence, analysis_constraint]
public: false
allowed_roles: [admin]
---
# 敏感字段访问规范

邮箱、手机号、精确地址和可定位个人的行为轨迹属于敏感数据。自然语言 Text2SQL 默认不得返回这些字段的明文；该限制同样适用于 admin，角色名称不能替代明确的数据出站授权。

需要使用敏感数据时，应走专门、可审计且最小化披露的受控流程。M30 不实现该流程，也不允许通过查询知识原件绕过 SQL Guard。
