# M20 Milvus Index Hygiene Smoke

- generated_at: 2026-08-02 20:39:49
- collection_name: datapilot_schema_docs_m20_20260802_203949_007d1e09
- milvus_uri: http://localhost:19530
- schema_docs_count: 193
- schema_docs_hash: 7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644
- embedding_provider: deterministic
- qwen_embedding_model: qwen3.7-text-embedding
- qwen_embedding_dimensions: 1024
- siliconflow_embedding_model: BAAI/bge-m3
- siliconflow_embedding_dimensions: None

## Collection Check

- status: PASS
- initial_row_count: None
- inserted_document_count: 193
- final_row_count: 193
- expected_row_count: 193

## Retrieval Samples

| question | keyword_hits | vector_hits | merged_hits | top_docs |
|---|---:|---:|---:|---|
| 2026 年 6 月 GMV 是多少？ | 10 | 10 | 10 | metric:gmv, field:order_coupons.applied_at, field:order_coupons.coupon_id, field:order_coupons.created_at, field:order_coupons.discount_amount |
| JUNE_FIXED_50 在哪个渠道使用最多？ | 10 | 10 | 10 | metric:coupon_usage_rate, relation:orders_channel, relation:refunds_order, field:order_coupons.applied_at, field:order_coupons.coupon_id |
| 2026 年 6 月一级类目 GMV Top 是什么？ | 10 | 10 | 10 | field:orders_wide.category, relation:product_category_tree, field:product_categories.parent_id, field:product_categories.id, field:product_categories.level |
| 2026 年 6 月退款率最高的商品是什么？ | 10 | 10 | 10 | field:order_items.item_discount_amount, metric:refund_rate, field:refunds.source_order_no, field:order_items.created_at, field:order_items.id |
| Aurora 耳机 2026 年 6 月历史均价是多少？ | 10 | 10 | 10 | field:product_price_history.is_current, field:product_price_history.change_reason, field:product_price_history.product_id, field:product_price_history.id, field:product_price_history.price_source |

## Cleanup

- kept_collection: no
- dropped_collection: yes
