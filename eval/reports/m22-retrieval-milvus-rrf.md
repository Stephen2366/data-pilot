# Schema Retrieval Embedding Benchmark

- generated_at: 2026-08-04 23:00:51
- total_cases: 10
- avg_overall_recall: 0.929
- avg_keyword_overall_recall: 0.738
- avg_vector_overall_recall: 0.929
- avg_table_recall: 0.925
- avg_column_recall: 0.925
- avg_metric_recall: 0.900
- avg_relation_recall: 0.967

## Runtime Metadata

| key | value |
|---|---|
| fusion_strategy | rrf |
| milvus_collection | datapilot_schema_docs_m22_retrieval_milvus_rrf_20260804_001 |
| milvus_dimension | 1024 |
| milvus_final_row_count | 194 |
| qwen_embedding_dimensions | 1024 |
| qwen_embedding_model | qwen3.7-text-embedding |
| schema_docs_count | 194 |
| schema_docs_hash | 58534cb68ec4264d4b75579d9f5a6f08bb1908475d89bbab63941e558cb92a6f |
| schema_embedding_provider | dashscope |
| schema_retrieval_profile | default |
| schema_vector_backend | milvus |
| top_k | 12 |

## Category Summary

| category | count | avg_overall | avg_table | avg_column | avg_metric | avg_relation |
|---|---:|---:|---:|---:|---:|---:|
| hard_negative | 3 | 0.833 | 0.833 | 0.833 | 0.667 | 1.000 |
| relation | 2 | 0.896 | 0.875 | 0.875 | 1.000 | 0.833 |
| semantic | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| synonym | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## Case Summary

| case_id | category | keyword_overall | vector_overall | merged_overall | table | column | metric | relation | missing |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| emb_syn_001 | synonym | 0.625 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_syn_002 | synonym | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_sem_001 | semantic | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_sem_002 | semantic | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_relation_001 | relation | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_relation_002 | relation | 0.396 | 0.792 | 0.792 | 0.750 | 0.750 | 1.000 | 0.667 | tables=products; columns=product_name; relations=order_items_product |
| emb_hardneg_001 | hard_negative | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_hardneg_002 | hard_negative | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.000 | 1.000 | tables=channels; columns=gmv; metrics=gmv |
| emb_hardneg_003 | hard_negative | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |
| emb_sem_003 | semantic | 0.354 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | - |

## Top Docs

| case_id | keyword_top_docs | vector_top_docs | merged_top_docs |
|---|---|---|---|
| emb_syn_001 | metric:gmv, field:order_coupons.applied_at, field:order_coupons.coupon_id, field:order_coupons.created_at, field:order_coupons.discount_amount | relation:orders_channel, field:channels.created_at, field:channels.channel_name, metric:gmv, field:channels.updated_at | metric:gmv, relation:orders_channel, field:channels.created_at, field:order_coupons.applied_at, field:channels.channel_name, field:order_coupons.coupon_id, field:order_coupons.created_at, field:channels.updated_at |
| emb_syn_002 | field:channels.channel_code, field:channels.channel_name, field:channels.channel_type, field:channels.created_at, field:channels.id | metric:coupon_usage_rate, relation:orders_coupons, metric:coupon_order_count, field:channels.channel_name, field:channels.created_at | field:channels.channel_name, field:channels.channel_code, metric:coupon_usage_rate, field:channels.created_at, field:channels.channel_type, field:channels.updated_at, field:channels.id, field:order_coupons.discount_amount |
| emb_sem_001 | metric:add_to_pay_conversion_rate, field:user_behavior_log.channel_id, field:user_behavior_log.created_at, field:user_behavior_log.device_type, field:user_behavior_log.duration_ms | metric:add_to_pay_conversion_rate, field:user_behavior_log.device_type, field:user_behavior_log.product_id, field:user_behavior_log.created_at, field:user_behavior_log.event_type | metric:add_to_pay_conversion_rate, field:user_behavior_log.device_type, field:user_behavior_log.created_at, field:user_behavior_log.channel_id, field:user_behavior_log.event_type, field:user_behavior_log.event_time, field:user_behavior_log.product_id, field:user_behavior_log.duration_ms |
| emb_sem_002 | field:product_price_history.is_current, relation:product_price_history_temporal, field:product_price_history.valid_to, metric:avg_selling_price, field:product_price_history.change_reason | metric:avg_selling_price, relation:product_price_history_temporal, field:product_price_history.created_at, field:product_price_history.price, field:product_price_history.id | relation:product_price_history_temporal, metric:avg_selling_price, field:product_price_history.is_current, field:product_price_history.created_at, field:product_price_history.valid_to, field:product_price_history.price, field:product_price_history.id, field:product_price_history.change_reason |
| emb_relation_001 | metric:item_gmv, metric:gmv, relation:product_category_tree, relation:products_category, field:product_categories.created_at | relation:product_category_tree, field:products.category_id, relation:products_category, metric:item_gmv, field:products.category | relation:product_category_tree, metric:item_gmv, relation:products_category, field:product_categories.name, field:product_categories.created_at, field:product_categories.parent_id, field:product_categories.sort_order, field:product_categories.status |
| emb_relation_002 | relation:refunds_order_item, field:refunds.order_item_id, field:refunds.created_at, field:refunds.id, field:refunds.order_id | field:refunds.product_id, field:refunds.order_id, field:refunds.refund_reason, metric:refund_rate, field:refunds.order_item_id | field:refunds.order_id, field:refunds.order_item_id, field:refunds.product_id, field:refunds.created_at, field:refunds.id, field:refunds.refund_reason, field:refunds.processed_at, field:refunds.refund_amount |
| emb_hardneg_001 | field:refunds.order_item_id, field:refunds.source_order_no, relation:order_items_product, field:order_items.item_discount_amount, field:order_items.line_no | field:refunds.product_id, metric:refund_rate, field:refunds.order_item_id, field:refunds.refund_status, field:refunds.order_id | field:refunds.order_item_id, field:refunds.product_id, field:refunds.order_id, field:refunds.created_at, field:refunds.processed_at, field:refunds.source_order_no, metric:refund_rate, relation:order_items_product |
| emb_hardneg_002 | field:orders_wide.external_order_no, field:orders_wide.source_order_no, field:orders_wide.actual_amount, field:orders_wide.batch_id, field:orders_wide.category | field:orders_wide.channel_name, field:orders_wide.order_amount, field:orders_wide.channel_type, field:orders_wide.channel_id, field:orders_wide.channel_code | field:orders_wide.actual_amount, field:orders_wide.channel_name, field:orders_wide.channel_id, field:orders_wide.channel_code, field:orders_wide.channel_type, field:orders_wide.discount_amount, field:orders_wide.external_order_no, field:orders_wide.order_amount |
| emb_hardneg_003 | field:refunds.source_order_no, field:orders.external_order_no, field:order_items.order_id, field:orders_wide.external_order_no, field:refunds.order_id | relation:refunds_order, relation:refunds_order_item, relation:refunds_product, field:refunds.source_order_no, field:refunds.order_id | field:refunds.source_order_no, field:refunds.order_id, field:refunds.order_item_id, relation:refunds_order, field:orders.external_order_no, relation:refunds_order_item, field:order_items.order_id, relation:refunds_product |
| emb_sem_003 | relation:orders_primary_product, field:orders.id, field:orders_wide.category_id, field:orders_wide.primary_product_price, field:orders_wide.product_id | metric:item_gmv, metric:gmv, field:products.price, field:products.product_name, field:products.launched_at | relation:orders_primary_product, metric:item_gmv, field:orders.id, metric:gmv, field:orders_wide.category_id, field:products.price, field:orders_wide.primary_product_price, field:products.product_name |
