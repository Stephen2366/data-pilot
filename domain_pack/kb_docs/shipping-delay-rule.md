---
document_key: shipping_delay_rule
revision: "2026-08-13-r1"
title: 物流延迟处理规则
knowledge_type: support_rule
status: active
anchor: shipping-delay-rule
data_class: role_restricted_policy_text
purposes: [answer_evidence]
public: false
allowed_roles: [customer_service]
---
# 物流延迟处理规则

现货订单应在 48 小时内出库。包裹出库后，物流轨迹连续超过 120 小时没有更新时，按物流延迟处理；尚未出库的订单不使用“轨迹无更新”条件判断。

符合延迟条件的订单按实际延迟天数发放优惠券。具体订单是否满足条件属于实时业务事实，应查询订单和物流系统，不能由本文档直接断言。
