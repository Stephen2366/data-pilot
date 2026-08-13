---
document_key: demo_user_scope
revision: "2026-08-13-r1"
title: 演示账号数据范围
knowledge_type: security_policy
status: active
anchor: demo-user-scope
data_class: security_policy
purposes: [answer_evidence, analysis_constraint]
public: false
allowed_roles: [demo_user]
---
# 演示账号数据范围

demo_user 只能访问项目 seed 生成的模拟数据，并且仍需遵守 Text2SQL 的表级与字段级 allowlist。演示账号默认关闭导出、删除和外部系统集成能力。

本文不扩大 demo_user 的 SQL 权限，也不能作为读取政策正文或其他角色文档的授权凭据。
