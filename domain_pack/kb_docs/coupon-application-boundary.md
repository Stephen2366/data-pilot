---
document_key: coupon_application_boundary
revision: "2026-08-15-r1"
title: 优惠券适用信息边界
knowledge_type: support_rule
status: active
anchor: coupon-application-boundary
data_class: role_restricted_policy_text
purposes: [answer_evidence, analysis_constraint]
public: false
allowed_roles: [customer_service]
---
# 优惠券适用信息边界

优惠券是否有效、是否满足使用条件、适用于哪些商品，以及某个订单的实际抵扣金额，属于查询时点的业务事实，应以当前优惠券、订单和订单优惠券关联数据为准。静态知识文档和指标口径不能替代这次事实查询。

优惠券使用订单数、使用率等指标只解释统计口径，不能证明某张优惠券可用于某个订单。退款规则提到按当期规则发放优惠券时，具体券种和权益仍需读取当前客服补偿规则或业务系统，不得从历史回答或指标公式猜测。
