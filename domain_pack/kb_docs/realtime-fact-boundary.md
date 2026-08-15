---
document_key: realtime_fact_boundary
revision: "2026-08-15-r1"
title: 实时业务事实查询边界
knowledge_type: support_rule
status: active
anchor: realtime-fact-boundary
data_class: role_restricted_policy_text
purposes: [answer_evidence, analysis_constraint]
public: false
allowed_roles: [customer_service, ops]
---
# 实时业务事实查询边界

静态知识文档用于解释规则和指标口径，不能单独证明某个订单、退款、物流、发票、优惠券或客户资格在查询时点的真实状态。问题涉及具体对象当前能否办理、是否达标或实际金额时，应先取得能够定位对象的信息，再查询对应业务系统。

没有实时 SQL 或 Tool Evidence 时，只能说明一般规则和仍需核实的条件，不能把静态说明写成已经发生的业务事实。本文不修改退款、物流、发票、优惠券或 VIP 专项规则；专项规则有更明确要求时，以对应专项规则为准。
