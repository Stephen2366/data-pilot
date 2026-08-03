# M20 Eval Ground Truth Audit

- generated_at: 2026-08-02 20:37:06
- configured_database_url: 127.0.0.1:3306/datapilot_dev?charset=utf8mb4
- oracle_backend_for_current_result_match: SQLite deterministic seed (`eval.scorers.rule_scorers._prepare_sqlite_seed`)
- M20_decision: do not switch result_match oracle to MySQL in this module; this file records the MySQL audit baseline.

## Case Counts

| suite | count |
|---|---:|
| formal | 10 |
| challenge | 16 |
| diagnostic_extra | 16 |
| total_loaded_separately | 42 |

- duplicate_case_ids_across_files: -

## Check Type Counts

| check_type | count |
|---|---:|
| contains | 13 |
| expected_value | 2 |
| join_path_match | 2 |
| manual | 3 |
| metric_mapping_match | 1 |
| plan_structure_match | 1 |
| plan_validation_blocked | 3 |
| result_match | 5 |
| schema_context_match | 1 |
| schema_context_size | 3 |
| sql_guard_block | 6 |
| trace_steps_complete | 2 |

## Expected SQL Execution On Configured MySQL

- expected_sql_cases: 14
- ok: 14
- error: 0

| case_id | source_file | status | row_count | preview_or_error |
|---|---|---|---:|---|
| db_simple_001 | eval/cases/database-upgrade-challenge.yaml | ok | 10 | {product_name=27 寸 4K 显示器, category=数码电子, status=active}; {product_name=4K 高清摄像头, category=数码电子, status=active}; {product_name=5G 商务手机 SE, category=数码电子, status=active} ... total=10 |
| db_simple_002 | eval/cases/database-upgrade-challenge.yaml | ok | 10 | {order_no=ORD-2026-05293, order_amount=1799.00, paid_at=2026-06-01 09:01:00}; {order_no=ORD-2026-01261, order_amount=1799.00, paid_at=2026-06-01 09:02:00}; {order_no=ORD-2026-06553, order_amount=4699.00, paid_at=2026-06-01 09:03:00} ... total=10 |
| db_simple_003 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {coupon_code=JUNE_FIXED_50, coupon_name=六月满 300 减 50, coupon_type=fixed_amount} |
| db_core_001 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {gmv=11285752.00} |
| db_core_002 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {product_name=Aurora Noise Cancelling Headphones, refund_rate=0.50376} |
| db_core_003 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {net_revenue=11293058.25} |
| db_core_004 | eval/cases/database-upgrade-challenge.yaml | ok | 6 | {channel_name=Mobile App, order_count=4500}; {channel_name=Douyin, order_count=1100}; {channel_name=JD, order_count=1100} ... total=6 |
| db_multi_001 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {channel_name=Mobile App, coupon_order_count=650} |
| db_multi_002 | eval/cases/database-upgrade-challenge.yaml | ok | 5 | {category=数码电子, item_gmv=8505886.00}; {category=SaaS 软件, item_gmv=1020709.00}; {category=户外运动, item_gmv=874394.00} ... total=5 |
| db_multi_003 | eval/cases/database-upgrade-challenge.yaml | ok | 6 | {channel_name=Mobile App, gmv=7260071.00}; {channel_name=Partner, gmv=896017.00}; {channel_name=Web Store, gmv=805068.00} ... total=6 |
| db_multi_004 | eval/cases/database-upgrade-challenge.yaml | ok | 5 | {product_name=轻薄商务笔记本 14 寸, item_gmv=2481996.00}; {product_name=迷你主机 i5 办公版, item_gmv=1612401.00}; {product_name=5G 商务手机 SE, item_gmv=1177128.00} ... total=5 |
| db_hard_001 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {root_category=数码电子, gmv=8505886.00} |
| db_hard_002 | eval/cases/database-upgrade-challenge.yaml | ok | 1 | {device_type=mobile_app, conversion_rate=0.70000} |
| db_hard_003 | eval/cases/database-upgrade-challenge.yaml | ok | 50 | {product_name=27 寸 4K 显示器, avg_price=1799.00}; {product_name=4K 高清摄像头, avg_price=679.00}; {product_name=5G 商务手机 SE, avg_price=2199.00} ... total=50 |

## Known Case Hygiene Notes

- `result_match` currently uses SQLite deterministic seed as the oracle, not the configured MySQL database.
- Formal multi-table cases with `contains` checks may be too weak for long-term benchmark use; M20 records this but does not change YAML.
- `db_core_002` refund-rate wording and `db_simple_002` paid-order wording remain unchanged in M20; both need a separate benchmark口径 decision before edits.
