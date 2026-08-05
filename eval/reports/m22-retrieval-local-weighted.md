# Schema Retrieval Embedding Benchmark

- generated_at: 2026-08-04 23:00:00
- total_cases: 10
- avg_overall_recall: 0.738
- avg_keyword_overall_recall: 0.738
- avg_vector_overall_recall: 0.787
- avg_table_recall: 0.817
- avg_column_recall: 0.900
- avg_metric_recall: 0.600
- avg_relation_recall: 0.633

## Runtime Metadata

| key | value |
|---|---|
| fusion_strategy | weighted |
| milvus_collection | datapilot_schema_docs |
| milvus_dimension | None |
| milvus_final_row_count | None |
| qwen_embedding_dimensions | 1024 |
| qwen_embedding_model | qwen3.7-text-embedding |
| schema_docs_count | 194 |
| schema_docs_hash | 58534cb68ec4264d4b75579d9f5a6f08bb1908475d89bbab63941e558cb92a6f |
| schema_embedding_provider | deterministic |
| schema_retrieval_profile | default |
| schema_vector_backend | inmemory |
| top_k | 12 |

## Category Summary

| category | count | avg_overall | avg_table | avg_column | avg_metric | avg_relation |
|---|---:|---:|---:|---:|---:|---:|
| hard_negative | 3 | 0.667 | 0.833 | 0.833 | 0.333 | 0.667 |
| relation | 2 | 0.698 | 0.750 | 0.875 | 0.500 | 0.667 |
| semantic | 3 | 0.785 | 0.889 | 0.917 | 0.667 | 0.667 |
| synonym | 2 | 0.812 | 0.750 | 1.000 | 1.000 | 0.500 |

## Case Summary

| case_id | category | keyword_overall | vector_overall | merged_overall | table | column | metric | relation | missing |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| emb_syn_001 | synonym | 0.625 | 0.562 | 0.625 | 0.500 | 1.000 | 1.000 | 0.000 | tables=channels; relations=orders_channel |
| emb_syn_002 | synonym | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_sem_001 | semantic | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_sem_002 | semantic | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_relation_001 | relation | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_relation_002 | relation | 0.396 | 0.792 | 0.396 | 0.500 | 0.750 | 0.000 | 0.333 | tables=orders,products; columns=product_name; metrics=refund_rate; relations=order_items_order,order_items_product |
| emb_hardneg_001 | hard_negative | 0.750 | 0.271 | 0.750 | 1.000 | 1.000 | 0.000 | 1.000 | metrics=refund_rate |
| emb_hardneg_002 | hard_negative | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.000 | 1.000 | tables=channels; columns=gmv; metrics=gmv |
| emb_hardneg_003 | hard_negative | 0.750 | 1.000 | 0.750 | 1.000 | 1.000 | 1.000 | 0.000 | relations=refunds_order |
| emb_sem_003 | semantic | 0.354 | 0.750 | 0.354 | 0.667 | 0.750 | 0.000 | 0.000 | tables=order_items; columns=line_amount; metrics=item_gmv; relations=order_items_order,order_items_product |

## Top Docs

| case_id | keyword_top_docs | vector_top_docs | merged_top_docs |
|---|---|---|---|
| emb_syn_001 | metric:gmv, field:order_coupons.applied_at, field:order_coupons.coupon_id, field:order_coupons.created_at, field:order_coupons.discount_amount | metric:gmv, metric:net_revenue, field:order_coupons.discount_amount, field:order_coupons.created_at, field:order_coupons.id | metric:gmv, field:order_coupons.discount_amount, field:order_coupons.created_at, field:order_coupons.applied_at, field:order_coupons.id, field:order_coupons.order_id, field:order_coupons.coupon_id, metric:add_to_pay_conversion_rate |
| emb_syn_002 | field:channels.channel_code, field:channels.channel_name, field:channels.channel_type, field:channels.created_at, field:channels.id | field:channels.created_at, field:channels.updated_at, field:channels.channel_code, field:channels.channel_name, field:channels.id | field:channels.created_at, field:channels.updated_at, field:channels.channel_code, field:channels.channel_name, field:channels.id, field:channels.status, field:channels.channel_type, metric:coupon_usage_rate |
| emb_sem_001 | metric:add_to_pay_conversion_rate, field:user_behavior_log.channel_id, field:user_behavior_log.created_at, field:user_behavior_log.device_type, field:user_behavior_log.duration_ms | metric:add_to_pay_conversion_rate, field:user_behavior_log.device_type, field:orders.quantity, field:user_behavior_log.user_id, field:orders.actual_amount | metric:add_to_pay_conversion_rate, field:user_behavior_log.device_type, field:user_behavior_log.created_at, field:user_behavior_log.referrer, field:user_behavior_log.session_id, field:user_behavior_log.page_url, field:user_behavior_log.channel_id, field:user_behavior_log.duration_ms |
| emb_sem_002 | field:product_price_history.is_current, relation:product_price_history_temporal, field:product_price_history.valid_to, metric:avg_selling_price, field:product_price_history.change_reason | metric:avg_selling_price, relation:product_price_history_temporal, field:product_price_history.is_current, field:product_price_history.price, field:product_price_history.valid_to | relation:product_price_history_temporal, field:product_price_history.is_current, metric:avg_selling_price, field:product_price_history.valid_to, field:product_price_history.price, field:product_price_history.created_at, field:product_price_history.change_reason, field:product_price_history.valid_from |
| emb_relation_001 | metric:item_gmv, metric:gmv, relation:product_category_tree, relation:products_category, field:product_categories.created_at | field:product_categories.level, field:product_categories.parent_id, field:product_categories.created_at, field:product_categories.sort_order, field:product_categories.updated_at | metric:item_gmv, relation:products_category, relation:product_category_tree, metric:gmv, field:product_categories.level, field:product_categories.parent_id, field:product_categories.created_at, field:product_categories.sort_order |
| emb_relation_002 | relation:refunds_order_item, field:refunds.order_item_id, field:refunds.created_at, field:refunds.id, field:refunds.order_id | metric:refund_rate, field:refunds.product_id, field:refunds.order_item_id, field:refunds.refund_reason, field:refunds.id | relation:refunds_order_item, field:refunds.order_item_id, field:refunds.product_id, field:refunds.refund_reason, field:refunds.id, field:refunds.refund_no, field:refunds.created_at, field:refunds.order_id |
| emb_hardneg_001 | field:refunds.order_item_id, field:refunds.source_order_no, relation:order_items_product, field:order_items.item_discount_amount, field:order_items.line_no | field:refunds.product_id, field:refunds.order_item_id, field:refunds.id, field:refunds.refund_no, field:refunds.requested_at | field:refunds.order_item_id, field:refunds.source_order_no, field:refunds.product_id, field:refunds.id, field:refunds.refund_no, field:refunds.created_at, field:refunds.order_id, field:refunds.processed_at |
| emb_hardneg_002 | field:orders_wide.external_order_no, field:orders_wide.source_order_no, field:orders_wide.actual_amount, field:orders_wide.batch_id, field:orders_wide.category | field:orders_wide.channel_id, field:orders_wide.channel_code, field:orders_wide.channel_name, field:orders_wide.channel_type, field:orders_wide.id | field:orders_wide.source_order_no, field:orders_wide.channel_id, field:orders_wide.channel_code, field:orders_wide.channel_name, field:orders_wide.channel_type, field:orders_wide.actual_amount, field:orders_wide.created_at, field:orders_wide.external_order_no |
| emb_hardneg_003 | field:refunds.source_order_no, field:orders.external_order_no, field:order_items.order_id, field:orders_wide.external_order_no, field:refunds.order_id | field:refunds.source_order_no, relation:refunds_order, field:orders.external_order_no, field:orders.source_order_no, field:orders.order_no | field:refunds.source_order_no, field:orders.external_order_no, field:refunds.order_id, field:refunds.order_item_id, field:order_items.order_id, field:orders_wide.external_order_no, field:users.phone, field:users.created_at |
| emb_sem_003 | relation:orders_primary_product, field:orders.id, field:orders_wide.category_id, field:orders_wide.primary_product_price, field:orders_wide.product_id | relation:orders_primary_product, field:products.id, field:products.price, field:products.product_name, field:products.sku | relation:orders_primary_product, field:orders.id, field:orders_wide.category_id, field:orders_wide.primary_product_price, field:orders_wide.product_id, field:orders_wide.product_name, field:orders_wide.sku, field:order_coupons.id |
