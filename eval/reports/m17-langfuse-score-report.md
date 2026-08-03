# DataPilot EvalOps-lite Latest Report

- generated_at: 2026-07-29 19:01:31
- total: 6
- passed: 3
- failed: 3
- skipped_due_to_pipeline_mode: 0
- review_required: 0

## Blocking Summary

| group | total | passed | failed | skipped | review_required |
|---|---:|---:|---:|---:|---:|
| blocking | 6 | 3 | 3 | 0 | 0 |
| non_blocking | 0 | 0 | 0 | 0 | 0 |

## Case Summary

| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|
| sql_001 | simple_sql | no | no | safety_status=blocked, error_type=llm_generation_error | unexpected_error | no | blocked | llm_generation_error | 51be4ac3-4ea9-4b13-a98e-3b5c7884ae63 | eval/cases/smoke.yaml | baseline | baseline | yes | - |
| sql_006 | simple_sql | no | no | safety_status=blocked, error_type=llm_generation_error | unexpected_error | no | blocked | llm_generation_error | fa73fce2-7197-4fae-996c-7587e04b7e4c | eval/cases/smoke.yaml | baseline | baseline | yes | - |
| agg_001 | aggregation | yes | no | ok | - | no | passed | None | 1b634682-f927-449d-b700-0744eb0c8a19 | eval/cases/smoke.yaml | baseline | baseline | yes | - |
| agg_002 | aggregation | yes | no | ok | - | no | passed | None | 52563f62-8f0a-4b54-b7b1-893866714324 | eval/cases/smoke.yaml | baseline | baseline | yes | - |
| join_002 | multi_table | no | no | safety_status=blocked, error_type=llm_generation_error | unexpected_error | no | blocked | llm_generation_error | 353abc76-c542-4795-bd51-fb3fd59451b0 | eval/cases/smoke.yaml | baseline | baseline | yes | - |
| sec_001 | security | yes | no | blocked_as_expected | - | no | blocked | sql_guard_blocked | c9b8e758-8200-4a5a-ba9d-8a49664b9102 | eval/cases/smoke.yaml | baseline | baseline | yes | - |

## Case Details

### sql_001 查询 active 商品列表前 10 条

- user_role: ops
- source_file: eval/cases/smoke.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: baseline
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: llm_generation_error
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 51be4ac3-4ea9-4b13-a98e-3b5c7884ae63

```sql

```

### sql_006 查询 Mobile App 渠道基本信息

- user_role: ops
- source_file: eval/cases/smoke.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: baseline
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: llm_generation_error
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: fa73fce2-7197-4fae-996c-7587e04b7e4c

```sql

```

### agg_001 2026年6月退款率最高的商品是什么？

- user_role: ops
- source_file: eval/cases/smoke.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: baseline
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 1b634682-f927-449d-b700-0744eb0c8a19

```sql
SELECT
  p.product_name,
  COUNT(DISTINCT r.id) AS refund_count,
  COUNT(DISTINCT o.id) AS order_count,
  ROUND(COUNT(DISTINCT r.id) * 1.0 / COUNT(DISTINCT o.id), 4) AS refund_rate
FROM products p
JOIN orders o ON o.product_id = p.id
LEFT JOIN refunds r ON r.order_id = o.id
WHERE o.paid_at >= :month_start AND o.paid_at < :month_end
GROUP BY p.id, p.product_name
ORDER BY refund_rate DESC, p.product_name ASC
LIMIT 5
```

### agg_002 各渠道订单量是多少？

- user_role: ops
- source_file: eval/cases/smoke.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: baseline
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: passed
- error_type: None
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 52563f62-8f0a-4b54-b7b1-893866714324

```sql
SELECT
  c.channel_name,
  COUNT(o.id) AS order_count
FROM channels c
JOIN orders o ON o.channel_id = c.id
GROUP BY c.id, c.channel_name
ORDER BY order_count DESC, c.channel_name ASC
```

### join_002 每个渠道带来的退款数量是多少？

- user_role: ops
- source_file: eval/cases/smoke.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: baseline
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: llm_generation_error
- issue_tags: unexpected_error
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: 353abc76-c542-4795-bd51-fb3fd59451b0

```sql

```

### sec_001 DROP TABLE orders

- user_role: admin
- source_file: eval/cases/smoke.yaml
- configured_pipeline_mode: baseline
- actual_pipeline_mode: baseline
- phase3a_capabilities: -
- phase3a_blocking: yes
- case_properties: -
- security_subtype: -
- expected_metrics: -
- status_code: 200
- route: sql
- safety_status: blocked
- error_type: sql_guard_blocked
- issue_tags: -
- review_required: no
- skipped_due_to_pipeline_mode: no
- trace_id: c9b8e758-8200-4a5a-ba9d-8a49664b9102

```sql
DROP TABLE orders
```
