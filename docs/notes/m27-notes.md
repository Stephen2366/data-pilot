# M27 Diagnostic / Eval Case 体系优化笔记

> 用途：记录 M27 P0 盘点、用户确认门方案、实现中的关键判断与验证快照。新合同与旧 `formal / challenge / diagnostic` 历史口径严格隔离。

## Implementation checklist

- [ ] P0：盘点 smoke、formal、challenge、diagnostic、exception、reliability 与 retrieval-only case，形成 canonical migration matrix。
- [ ] A1：提交逐题 Scenario / assertions / classification / selectors 方案，等待用户确认。
- [ ] A2：提交 `EvalRunSpec`、环境、port、snapshot、runtime identity、evidence、状态边界方案，等待用户确认。
- [ ] A3：提交 hash、version、checkpoint 与脱敏证据策略，等待用户确认。
- [ ] 在确认范围内实现 M27A，并运行确定性针对性测试；不运行新的真实 LLM 基线。

## P0 工作记录

- 2026-08-09：已开始。遵循 `m27-plan.md`，先核对真实 case 重复与业务合同；尚未修改正式 case、分母、gate、runner、scorer 或默认运行配置。
- 2026-08-09：以 YAML loader 盘点并逐一校验了 51 个 pipeline case ID（smoke 6、formal 10、challenge 16、diagnostic 16、exception 3）；migration matrix / legacy-only 清单均覆盖这些 ID。`git diff --check` 通过。此为静态 P0 验证，未调用 LLM、未运行新的 eval 或更改运行环境。

### 已核对的实现事实

- 现有主 runner 是 `EvalCase -> /api/query -> EvalResult -> Markdown/triage/LangFuse`；`run_cases()` 会按 raw case 逐条请求，故同一 `semantic_group_id` 仍会再次调用 pipeline。
- `result_match` scorer 会在**每一条 case** 内重新创建 SQLite seed 并执行 `expected_sql`；候选 SQL 与 reference SQL 不共享同一个 `RunEnvironment`/snapshot。这是 M27 P2 必须消除的真实实现边界。
- `metric_mapping_match`、`join_path_match`、`plan_structure_match`、`trace_steps_complete` 均未在旧 `_score_output_check()` 中实际 dispatch，最终会落入默认 `rule:<type>=ok`。它们不能迁移为已验证的正式通过事实。
- `schema_context_match` / `schema_context_size` 与 `plan_validation_blocked` 已有针对 trace 的 scorer；但仍被旧 runner 的早返回及整题 `passed/review_required` 汇总语义包裹。
- M26 audit 是冻结历史产物的只读 adapter：它从 Markdown `Score Summary` 重建旧评分，再与 JSONL trace / triage 对齐；不得作为新 EvalRun 的数据来源。

### 盘点口径与数量

- `formal(10) + challenge(16) + diagnostic extra(16)` 共 **42 raw case**；按当前 `semantic_group_id` 与题面/合同核对为 **26 个旧语义组**。其中 6 组是在 diagnostic 运行中重复调用的同题不同 check。
- 加入 smoke 后，有 4 条明确是弱化复制（`sql_001`、`agg_001`、`agg_002`、`sec_001` 映射既有业务问题），另有 `sql_006` 和 `join_002` 没有可迁移的完整业务 oracle；不把它们误记为新的稳定能力题。
- `database-exception-suite.yaml` 与 `m25-reliability-suite.yaml` 都是**引用型 selector**，不定义新题面；exception 新增 3 个业务问题，reliability 不增加独立问题。
- 因此旧输入中可审计到 **31 个** pipeline 业务问题（26 旧组 + 2 个 smoke 独有题 + 3 个 exception 独有题）。按 M27 计划候选把“商品退款率 Top 1 / 排名”合并、并淘汰两个无完整合同的 smoke 复制题后，建议形成 **28 个 canonical scenario 候选**；这个数量尚未确认，不能用于新分母或 Gate。
- `schema-retrieval-embedding-benchmark.yaml` 的 10 条是 retrieval-only benchmark，走 `run_schema_retrieval_benchmark`，不调用 `/api/query`、不共享 EvalRun evidence。建议保持独立 read-only benchmark，**不混入 M27 Scenario catalog 或分母**。

## P0 canonical migration matrix（A1 提案，未生效）

表中 `result` 指同 snapshot 的 deterministic `result_match`（标量题可由它覆盖旧 `expected_value`）；`backlog` 表示业务题可保留，但尚缺真实 scorer、完整 oracle 或反事实，不能伪装成自动通过。`legacy` 表示旧 formal/challenge/diagnostic 文件和历史结果只读保留。

| 候选 canonical scenario | 旧 case 映射 | 候选分类 | 候选 typed assertions | selector / 迁移判断 |
|---|---|---|---|---|
| `active_products_top10` | `p3a_simple_001`, `db_simple_001`, smoke `sql_001` | Core | result, output, context | 前两条 reference SQL/投影完全一致；smoke 是弱化复制，改由 selector 复用严格题面。 |
| `june_fixed_coupon_basic_info` | `p3a_simple_002`, `db_simple_003` | Core | result, output | 精确重复，reference SQL/投影一致。 |
| `june_gmv` | `p3a_agg_001`, `db_core_001`, `db_trace_001` | Core | result, output, trace | 同题；旧 expected-value 由 result oracle 覆盖，Trace 共享同次证据。 |
| `june_net_revenue` | `p3a_agg_002`, `db_core_003` | Core | result, output | 同题；旧 expected-value 由 result oracle 覆盖。 |
| `top_device_conversion` | `p3a_agg_003`, `db_hard_002` | Core | result, output, context | 精确重复，reference SQL/投影一致。 |
| `june_fixed_coupon_top_channel` | `p3a_multi_001`, `db_multi_001`, `db_trace_002` | Core | result, output, trace | 同题；保留桥表去重合同。也是现 reliability selector 的来源之一。 |
| `june_product_sales_top5` | `p3a_multi_002`, `db_multi_004`, `db_prompt_001` | Core | result, output, context | 同题；Context 复用同次 evidence。 |
| `june_root_category_sales` | `p3a_multi_003`, `db_multi_002` | Stress | result, output, context, plan, trace | reference SQL/投影一致；递归 CTE 不应因旧 formal 身份自动成为 Core。现 reliability 来源。 |
| `unsafe_drop_orders` | `p3a_sec_001`, `db_sec_001`, smoke `sec_001` | Core | safety_block | 精确重复；smoke 复用严格安全 scenario。 |
| `unsafe_delete_refund` | `p3a_sec_002`, `db_sec_002` | Core | safety_block | 精确重复。 |
| `june_completed_orders_top10` | `db_simple_002` | Core | result, output | 独立题；成交状态、`paid_at`、排序与 LIMIT 已有 reference SQL。 |
| `product_refund_rate_top1` | `db_core_002`, smoke `agg_001` | Stress | result, output, join_path | 旧 challenge 为“Top 1”；保留 completed、成交订单、明细优先/整单 `refunds.product_id` 回退反事实。见下方与 ranking 的合并确认项。现 exception/reliability 来源。 |
| `channel_order_ranking` | `db_core_004`, smoke `agg_002` | Core | result, output, context | smoke 缺时间/排序/全量结果合同，不能原样迁移；候选 selector 复用此严格 scenario。 |
| `june_channel_gmv_ranking` | `db_multi_003`, `db_plan_001` | Stress | result, output, query_plan, join_path | 同题；旧 `plan_structure_match` 尚无 scorer，迁移后须有正反 fixture。 |
| `digital_electronics_recursive_item_gmv` | `db_hard_001` | Stress | result, output, context, query_plan | 业务合同已明确为 root label + `item_gmv`；将 manual 改自动前需保留 M25 recursive counterfactual。现 reliability 来源。 |
| `june_avg_price_history` | `db_hard_003`, `db_prompt_002` | Stress / automation backlog | result, output, context | 题面共享 SCD 合同；M26 审计发现自动通过也会漏 `valid_to IS NULL` / 6 月 30 日边界，需补 NULL/月底反事实后才升为自动 assertion。 |
| `june_actual_amount_sum` | `db_schema_002` | Stress / automation backlog | metric_mapping（待定义） | 现 check 无 scorer、无 reference SQL。A1 必须决定检查 SchemaGraph、QueryPlan 的 metric binding，还是增加最终 result oracle。 |
| `june_channel_gmv_dashboard` | `db_schema_003` | Stress | schema_context（alternatives） | 已有真实 alternatives scorer；候选仅检查受支持的 dashboard schema 选择，不把它误报为结果正确。 |
| `channel_refund_rate_ranking` | `db_join_001` | Stress / automation backlog | join_path（待定义）, result（候选） | 当前 join check 无 scorer且无 reference SQL；M26 审计发现“统计所有退款状态”会旧 runner 假通过，需确认 completed 过滤、排序与结果 oracle。 |
| `coupon_type_gmv` | `db_join_002`, `db_prompt_003` | Stress / automation backlog | context, join_path（待定义）, result（候选） | 两条同题、不同观察角度；当前没有 result oracle，须确认后补。 |
| `missing_product_supplier_rejection` | `db_plan_002` | Core | expected_rejection | 受支持的产品边界，保留 `missing_column` + `semantic_request_validation` 接受路径。 |
| `knowledge_doc_order_attribution_rejection` | `db_plan_003` | Core | expected_rejection | 计划已要求去除 `manual_review` 混合语义；保留 `unsupported_relation` 明确拒绝。 |
| `unsupported_multi_step_rejection` | `db_plan_004` | Core | expected_rejection | 当前明确不支持多步，自动判断 `unsupported_multi_step_plan`。 |
| `pii_email_phone_block` | `db_sec_003` | Core | safety_block | 独立敏感字段阻断场景，不能与 DDL/DML 安全题合并。 |
| `admin_contact_block` | `db_sec_004` | Core | safety_block | admin 也不能直出 PII；独立角色边界。 |
| `signed_net_refund_amount` | `db_anomaly_001` | Stress | result, output | exception selector；completed + `processed_at` + 保留负数冲销。 |
| `channel_net_refund_amount` | `db_anomaly_002` | Stress | result, output, join_path | exception selector；必须走 `refunds.order_id -> orders.id -> channels.id`。 |
| `order_item_amount_reconciliation` | `db_anomaly_003` | Stress | result, output | exception selector；确认 5 条不一致而非清洗数据。 |

### 不直接进入 canonical catalog 的现有输入

| 旧输入 | 结论 | 原因与建议 |
|---|---|---|
| diagnostic `db_join_003`：商品退款率**排名** | 与 `product_refund_rate_top1` 的合并候选，待 A1 决定 | 业务口径相同但输出合同不同（全排名 vs Top 1），不是“精确重复”。建议以更强的**排名**题面作为唯一 canonical scenario，Top 1 变成 selector/view 派生；这会改变新题面，必须确认。 |
| smoke `sql_006`：Mobile App 基本信息 | legacy-only，候选从新 Smoke selector 移除 | 只有 `contains`，无完整列/排序/oracle；不应为了保留 6 条 smoke 而新造弱合同。若仍需保留，需用户确认完整输出 contract。 |
| smoke `join_002`：各渠道退款数量 | legacy-only 或 Manual Lab 候选 | 缺时间范围、退款状态、`refund_count` 粒度与 oracle；当前业务合同不足，不能擅自改为 completed/全退款。建议从 Smoke selector 移除，除非用户确认合同。 |
| `database-exception-suite.yaml` | 迁移为 selector | 当前 7 个引用型 source 映射为：`june_completed_orders_top10`、`june_fixed_coupon_top_channel`、`product_refund_rate_*`、`channel_refund_rate_ranking`、3 个 anomaly；不复制题面。 |
| `m25-reliability-suite.yaml` | 迁移为 selector + protocol | 映射为：`product_refund_rate_*`、`june_root_category_sales`、`digital_electronics_recursive_item_gmv`、`product_refund_rate_ranking`；replicate 不增加独立 Scenario 分母。 |
| `schema-retrieval-embedding-benchmark.yaml`（10） | 保持独立 legacy/retrieval-only benchmark | 这是检索隔离实验，不是 PipelinePort/EvalRun 业务场景；M27 不改变其模型、embedding、检索或分母。 |

### A1 前需要用户决策的合同风险

1. **商品退款率合并**：建议以 `db_join_003` 的“排名 + 明细优先归因”为 canonical question，并让旧 `db_core_002` Top 1 成为结果投影/selector；或保留两个 Scenario（业务口径相同但输出合同不同）。若合并，必须新增排名的 reference SQL 与 counterfactual，不能用 Top 1 oracle 冒充完整排名。
2. **弱 smoke 两题**：建议退休 `sql_006`、`join_002` 的旧 contains 合同，并在新 Smoke selector 选择已有严格 Scenario；如果保留，需要确认完整题面、时间/状态/粒度、reference SQL 与输出契约。
3. **尚无真实 scorer 的三类能力题**：`june_actual_amount_sum`（metric mapping）、`channel_refund_rate_ranking`（join path）、`june_channel_gmv_ranking`（plan structure）与 `coupon_type_gmv`（join path）在新合同中必须先明确“检查哪份 evidence、哪些边/字段/指标、正反例是什么”。它们不能沿用历史 `ok` 或直接计入新自动分母。
4. **SCD 自动化**：`june_avg_price_history` 已有 reference SQL，但单 seed 的结果不足以抵抗 `NULL valid_to` 和月底窗口误写；建议列为 Stress automation backlog，补共享 counterfactual 后才参与自动 gate。

### 当前临时取舍

- 在 A1 之前，矩阵只记录“候选”，不创建 `eval/cases/catalog/`，不改旧 YAML、reference SQL、selector、`CASE_CONTRACT_VERSION`、score 分母或报告。
- 现有 `formal/challenge/diagnostic` 与 M25/M26 数字继续仅作 legacy evidence；上述 28 不是新 benchmark 数字，也不是通过目标。

## A2 / A3 方案摘要（待用户确认，未实现）

### A2：运行、证据与状态边界

- 对外唯一入口：`Evaluator.evaluate(EvalRunSpec) -> EvalRun`。CLI、Markdown、LangFuse 与未来 audit adapter 都只消费其结果，不自行执行 pipeline 或重算事实。
- `EvalRunSpec` 仅冻结：run id、已选择 scenario/contract、replicate policy、execution protocol、gate policy、oracle fixture identity 与**显式** requested runtime constraints；CLI/CI 的 exit code 由独立 `ExitPolicy` 决定，不进入 spec。
- 一轮只创建一个 `RunEnvironment`：它唯一拥有 SQLite seed/counterfactual snapshot、FastAPI/TestClient 的 DB 注入、OraclePort、run-scoped vector index、resolved runtime identity 与 cleanup。每个 `(run_id, scenario_id, replicate_id)` 最多一次 PipelinePort 调用。
- `ExecutionStatus` 固定为 `completed/rejected/pipeline_error/external_unavailable`；`AssertionStatus` 固定为 `passed/failed/not_observed`。expected rejection 和 safety 是 assertion，不伪装成 execution status；manual evidence 为 `not_observed(manual_evidence_required)`，不新增人工队列。
- scorer 只接收已构建的 `ExecutionEvidence` 做纯比较；不得重新读全局 trace、调用 LLM、执行 reference SQL 或重建 seed。Evidence Builder 在同一 snapshot 中产生候选/reference 证据，reference SQL 失败属于 eval/oracle error，不归为模型答错。
- 旧 `EvalCase`、`EvalResult`、Markdown parser 和 M26 audit 仅走最小只读 legacy adapter；新 Interface 不携带 `check_type`、`phase3a_blocking`、`review_required` 等兼容语义。

### A3：身份、产物与脱敏

- 四个独立 hash：`catalog_hash`（全部 catalog）、`selected_contract_hash`（本轮题面/assertion/reference/已解析指标合同）、`suite_policy_hash`（selector、resolved ids、classification、gate）、`run_spec_hash`（上述选择 + replicate/protocol/oracle/requested runtime）。规范化忽略排版、键顺序和文件路径，但保留有语义的步骤顺序；SQL 只归一空白。
- 三个独立 version：`contract_version=m27-v1`、`artifact_schema_version`、`projector_version`。projector 拒绝未知 artifact schema，不猜字段语义。
- checkpoint 语义：启动时原子写 `running` manifest；每个 scenario/replicate 写幂等 checkpoint；完成后校验并原子生成最终 JSON。已存在 run id 拒绝覆盖；可捕获异常写 `interrupted/failed`；遗留 `running` 读作 `abandoned/incomplete`，禁止进入 projector/gate；M27A 不实现 resume。
- 产物建议：临时 manifest/checkpoint 放项目 gitignored 临时目录（实现时遵守 `.codex/temp_work/` 纪律）；完成后的脱敏 `EvalRun` JSON 放 `eval/reports/m27-runs/<run_id>.json`，Markdown 是其单向 projector。旧 YAML/report/trace/triage/audit 不移动、不覆盖。
- 长期 evidence bundle 仅保留：脱敏 candidate/reference SQL、结果 schema/row count/normalized hash、有界脱敏差异样本、trace step 摘要、issue tags、allowlist provider metadata。默认不保存完整 rows、完整 prompt/response、API 凭证或 PII；raw JSONL 仍只作短期、可清理调试证据。删除 raw trace 后，bundle 仍能重算自动 scorer 并复核 SQL/结构化差异。

## 已确认后的实现记录

- 2026-08-09：用户确认 A1–A3，开始 M27A；旧 `eval.run_eval` 仍未切换，新合同以并行模块实现，避免覆盖 M26 历史入口。
- 已新增 `eval.contracts`（typed Scenario / Assertion / EvalRun 结构与三个 version）、`eval.catalog`（严格 loader + catalog/selected/policy/run-spec 四类 hash）、`eval.ports`、`eval.environment`、`eval.assertions`、`eval.evaluator`。对外深 Interface 为 `Evaluator.evaluate(EvalRunSpec) -> EvalRun`。
- `RunEnvironment` 默认 adapter 让 FastAPI candidate 路径和 OraclePort 共用同一 SQLite engine；显式 requested/resolved runtime 不一致会在首题前失败。`engine.nl2sql.pipeline` 的 query-plan trace 新增结构化 `plan_steps` 摘要，供 Plan / Join / Metric assertion 消费同一次证据，不保存 prompt 或 LLM 原文。
- P3a fake vertical slice 已验证：一个 Scenario 的 Result + Output + Trace 三个 assertion 只触发一次 PipelinePort 调用，写一份 checkpoint，环境随后关闭；未知 assertion kind 在加载阶段失败；hash 不受 YAML mapping key 顺序影响。
- P3a 已提交首个 canonical `june_gmv` 到 `eval/cases/catalog/scenarios.yaml`，同时覆盖 Result / Output / SchemaContext / QueryPlan / Trace。核对真实 TraceStep 后采用 machine type `sql_query`（不是旧计划示意中的 `sql_execution`）；后续报告可投影为人类语义“SQL execution”，但 typed contract 不能对不存在的 machine 值评分。
- 新增 `FileCheckpointStore`：`running` manifest、逐 scenario checkpoint、completed artifact 均走原子替换；同 run id 直接拒绝（M27A 不实现 resume）。暂未把它接到旧 CLI，避免在 B 门前切换入口。
- 验证：`pytest -q tests/test_m27_foundation.py tests/test_phase3a_pipeline.py --basetemp=.codex/temp_work/pytest-m27-p1`：`10 passed, 1 warning`（既有 Starlette/httpx deprecation，87.95s）。未调用真实 LLM，未变更模型/检索/embedding/数据库默认配置。
- 追加验证：`pytest -q tests/test_m27_foundation.py tests/test_m22_eval_contract.py --basetemp=.codex/temp_work/pytest-m27-p3a`：`19 passed, 1 warning`（既有 Starlette/httpx deprecation，49.46s）；`git diff --check` 通过。
- P3b 进行中：completed artifact 已改为 allowlist 表示，不保存完整 response/answer/rows 或 PII；临时 checkpoint 仍保留 raw evidence 供本机崩溃排障。新增测试确认长期 JSON 不含 email / rows，保留 row count 和 assertion evidence。
- SQLiteRunEnvironment 的真实 FastAPI/TestClient 拒绝路径已通过 `missing_column` 场景验证：语义校验在 LLM 调用之前形成 `execution_status=rejected`，`expected_rejection` assertion 通过。验证：`pytest -q tests/test_m27_foundation.py --basetemp=.codex/temp_work/pytest-m27-environment`：`7 passed, 1 warning`（既有 Starlette/httpx deprecation，12.14s）。
- catalog migration 进行中：已迁移 18 个无歧义 Scenario（`june_gmv`、4 个 safety block、3 个 expected rejection、7 个 Core result/output、3 个 Stress result/output/plan）。旧 source YAML 未修改；迁移的 reference SQL 均来自已审计的 challenge 合同。`june_channel_gmv_ranking` 首次以单题同时检查 result/output/QueryPlan/JoinPath，取代旧 `db_multi_003` + `db_plan_001` 的双请求。
- 最新验证：`pytest -q tests/test_m27_foundation.py --basetemp=.codex/temp_work/pytest-m27-stress-catalog`：`7 passed, 1 warning`（既有 Starlette/httpx deprecation，11.62s）；`git diff --check` 通过。
- 继续迁移 exception 三题后，catalog 已有 21/28 个确认 Scenario；`database-exception` 仍只是后续 selector，不重复定义 case。`channel_net_refund_amount` 的 result 与 `refunds_order -> orders_channel` JoinPath 共享同次 evidence。
- Plan / Join / Metric 三类新 scorer 已补正反测试，明确消费 query-plan trace 的 `plan_steps`；不会再落入旧 `rule:<check>=ok` 默认路径。验证：`pytest -q tests/test_m27_foundation.py --basetemp=.codex/temp_work/pytest-m27-assertions`：`8 passed, 1 warning`（既有 Starlette/httpx deprecation，11.65s）；`git diff --check` 通过。

## 直接执行授权后的 M27A / M27B 收尾记录

- 2026-08-09：用户在确认尚余迁移、projector、入口切换和验证后指示“直接执行”。此处按该授权完成 M27 的确定性实现；**仍未**运行真实 LLM 新基线，且未修改模型、检索、embedding、数据库、oracle、timeout/retry 或可靠性默认配置。
- P3b migration 完成：canonical catalog 现为 **28/28 Scenario**。新增的 7 条为 `june_product_refund_rate_ranking`、`digital_electronics_recursive_item_gmv`、`june_avg_price_history`、`june_actual_amount_sum`、`june_channel_gmv_dashboard`、`june_channel_refund_rate_ranking`、`june_coupon_type_gmv`。旧 YAML 与历史 report 均未移动或改写。
- 商品退款率以“完整排名”替代旧 Top 1 输出：reference oracle 保留成交订单分母、completed 退款、明细优先/整单 product 回退，并删除 `LIMIT 1`。这实现了 A1 已确认的合并，但新结果不与旧 `Top1` 分数比较。
- 对原来没有真正 scorer 的题，不再沿用旧 `ok`：`june_actual_amount_sum` 采用 QueryPlan 的 `orders.actual_amount + net_revenue` metric binding；`june_channel_gmv_dashboard` 采用明确的两套 SchemaContext alternatives；其余退款/优惠券题补了 deterministic result oracle。所有此类 assertion 都消费一次执行的结构化 evidence。
- 反事实已固化到 `tests/test_m27_oracle_counterfactuals.py`：SCD 必须保留 `valid_to IS NULL` 的开放区间；渠道退款率必须排除非 completed 退款；递归类目必须纳入子类。这些坏 SQL 在最小 SQLite fixture 上均与 canonical oracle 分离，避免单一 seed 的偶然通过。
- artifact 进一步完善：Result assertion 现在保存 row count、tolerance、order policy 和 candidate/reference 的稳定 SHA-256 fingerprint，而不保存完整结果行；可捕获 `KeyboardInterrupt` 写为 `interrupted`；遗留 `running` manifest 读取为 `abandoned`；非 `completed` EvalRun 被 projector 拒绝。
- P4/P5/P6 已实现：新增 Core/Stress/Manual classification policy、Smoke/Reliability/Database Exception YAML selector（只引用 canonical ids）、versioned projector、Markdown 与严格 LangFuse payload adapter。Reliability 多 replicate 先归约为一个逻辑 `(scenario, assertion)`，不会扩大 scenario/assertion 分母。`eval.run_eval.main` 已切换到 M27 `Evaluator.evaluate()` CLI；旧 runner 函数保留为 `legacy_main`/历史读取支持，不能产生 M27 分数。
- 新报告固定展示 Gate、execution 与各 assertion view 的 `eligible / observed / passed / failed / not_observed / unavailable / manual`，不再生成单一 diagnostic 总分。CLI 的 `inconclusive` exit 行为由 `exit_code_for_gate` 独立控制，不写入 EvalRun。

### 本轮验证快照

- `pytest -q tests/test_m27_foundation.py tests/test_m27_oracle_counterfactuals.py --basetemp=.codex/temp_work/pytest-m27-counterfactuals`：**14 passed, 1 warning**（既有 Starlette/httpx deprecation，11.83s）。
- `pytest -q tests/test_phase3a_eval.py tests/test_m22_eval_contract.py --basetemp=.codex/temp_work/pytest-m27-legacy-eval`：**37 passed, 1 warning**（90.83s）。
- `pytest -q tests/test_phase3a_pipeline.py tests/test_m27_foundation.py tests/test_m27_oracle_counterfactuals.py --basetemp=.codex/temp_work/pytest-m27-pipeline`：**21 passed, 1 warning**（91.33s）。
- 尚待执行：全仓 pytest、`git diff --check`，以及模块收工技能（仅在全部确定性门禁完成后）。

## 收工素材（finish-module）

### 模块范围与改动文件

- 本模块：**M27 Diagnostic / Eval Case 体系优化**。用户未提供模块起始 commit；收工范围按当前工作树的 M27 文件核对。改动归并为：`eval/{contracts,catalog,ports,environment,assertions,evaluator,selectors,projectors,reporting}.py`、`eval/cases/catalog/{scenarios,selectors}/*.yaml`、`eval/run_eval.py`、`engine/nl2sql/pipeline.py`、`tests/test_m27_*.py`、本 notes 文件。
- 未改动旧 `formal/challenge/diagnostic` YAML、历史 report/triage/audit、默认模型/检索/embedding/数据库/oracle/retry 配置；retrieval-only benchmark 继续隔离。

### 关键决策与取舍

- 用户确认 A1–A3 后，选择 **28 个 canonical Scenario + 多个 typed assertion**，而非继续用同题复制和旧整题分数。主要风险是把 Top1/排名、SCD、退款归因等近似题误合并；因此商品退款率采用完整排名 oracle，SCD/退款/递归另加反事实。
- 用户随后明确“直接执行”，据此完成 B 门的 selector、分母、gate、report 与入口切换；但没有把该授权扩展为真实 LLM 基线授权。新数字不与冻结的 M26 分数比较。
- 安全 artifact 选择保存 schema、行数、容差、稳定 fingerprint 与 trace 摘要，不保存 rows/prompt/answer/凭证。代价是不能恢复完整业务行；收益是 raw trace 清理后仍可核验自动比较身份，并避免报告携带 PII。
- 旧 `eval.run_eval` 的历史函数保留为 legacy read-only 支持，CLI `main` 切到 M27 `Evaluator.evaluate()`。这是短期兼容边界，不把 `check_type`、`review_required`、`phase3a_blocking` 扩散进新数据结构。

### 注释小结

- 覆盖扫描：M27 新增模块的公开类/函数均已有中文职责 docstring；为 catalog/assertion/evaluator/selector/projector 的 34 个私有解析、比较和归约函数补了短 docstring。Protocol 方法、纯赋值构造器和 pytest 自描述测试函数按 skill 豁免。
- 质量扫描：深化了“同一张答卷多科阅卷”“selector 不复制题面”“replicate 不扩大分母”“artifact fingerprint 不存结果行”四个新概念；关键取舍已在 `Evaluator`、`project_eval_run`、`safe_eval_run_payload` 周边注释说明。
- 内部可读性：为 hash 规范化、Result fingerprint、interrupted/abandoned 生命周期、QueryPlan 结构化 evidence 添加说明；未发现需要额外分隔线的长线性逻辑。

### 最终验证快照

- `python -m pytest -q tests/test_m27_foundation.py tests/test_m27_oracle_counterfactuals.py --basetemp=.codex/temp_work/pytest-m27-counterfactuals`：**14 passed, 1 warning**；warning 是既有 Starlette/httpx deprecation，不影响 M27 断言或 artifact。
- `python -m pytest -q tests/test_phase3a_eval.py tests/test_m22_eval_contract.py --basetemp=.codex/temp_work/pytest-m27-legacy-eval`：**37 passed, 1 warning**；验证 legacy Eval 合同仍可读取/测试。
- `python -m pytest -q tests/test_phase3a_pipeline.py tests/test_m27_foundation.py tests/test_m27_oracle_counterfactuals.py --basetemp=.codex/temp_work/pytest-m27-pipeline`：**21 passed, 1 warning**；验证 QueryPlan trace 增强未破坏 pipeline 回归。
- `python -m pytest -q --basetemp=.codex/temp_work/pytest-m27-full`：**208 passed, 1 warning**，509.65s；未发生真实 LLM 新基线调用。
- `git diff --check`：通过；只有 Git 的 LF→CRLF 工作区提示，无 whitespace error。
- `python -m eval.run_eval --help`：成功展示 `m27-v1` canonical CLI 参数；仅解析帮助文本，未执行 Pipeline 或模型调用。

### 参考资料与后续

- 参考资料：本模块未检索外部资料；以 `m27-plan.md`、M26 notes、已有代码/trace 合同和项目 state 文档为依据，没有照搬外部评测平台。
- 后续：用户人工检查后可运行 `accept-module`。真实 LLM `m27-v1` 新基线仍须单独确认运行范围/调用数/成本；LangFuse 当前只提供严格 payload adapter，实际上传策略保持显式授权。

### 文档迁移补记

- 2026-08-09：用户确认将旧评测账本整体移入 `docs/archive-versions/eval-baselines-old.md`，新建 `docs/state/eval-baselines.md` 只记录 M27 事实、分母与后续真实基线；`runbook.md` 与 `eval/cases/README.md` 同步改为 canonical Scenario / selector 入口。旧 formal/challenge/diagnostic 内容保留为 legacy/read-only，不再宣称可由当前 `eval.run_eval` 生成新分数。

### 授权后的真实 LLM Smoke（非基线）

- 2026-08-09：用户授权执行一次 M27 `smoke`。固定现有默认 runtime：Qwen `qwen3.7-plus`、inmemory deterministic/weighted、45s/retry0、SQLite deterministic seed、LangFuse off；没有切模型、检索、embedding、数据库、oracle 或可靠性配置。
- 首次 `m27-smoke-20260809-01` 受工具 60 秒时限中断，已完成 `june_gmv`、`unsafe_drop_orders`、`missing_product_supplier_rejection` 的 checkpoint，manifest 保持 `running`。M27 不支持 resume，故该 run 不生成 completed artifact/report，也不进入 Gate。
- 使用新 run id `m27-smoke-20260809-02` 完成完整 selector：4 个 logical Scenario、4 个 physical attempts、9 条 required assertion 全通过，Gate `passed`，无 failed/not_observed/unavailable。产物为 `eval/reports/m27-artifacts/m27-smoke-20260809-02.json` 和 `eval/reports/m27-smoke-20260809-02.md`；既有 Starlette/httpx deprecation warning 未影响结论。
- 解释边界：Smoke 仅验证当前运行环境下 API、Guard、Trace、artifact 与报告闭环，不是完整 Core/Stress 评测，不能推出稳定模型能力、成本或可靠性，也不得与 M26 的 `25/32` 等旧口径相比较。
- 2026-08-09：用户再次执行相同 M27 `smoke`，`m27-smoke-20260809-03` 为 **4/4 logical Scenario 完成、9/9 required assertion passed、Gate passed**，无 failed/not_observed/unavailable。随后 `eval.run_review` 读取同 run artifact/checkpoint/catalog，4 条 Codex verdict 均为 high-confidence `pass`，reconciliation 全为 `auto_passed_manual_pass`。resolved runtime 与 `-02` 相同；它仍只是第二次链路快照，不升级为完整基线或可靠性结论。
- 2026-08-09：用户授权 M27 Core 的 Qwen plus local / Milvus 对照。local `m27-core-20260809-qwen37plus-local-01` 完成：19/19 logical execution，Core required assertion `29 passed / 5 failed / 0 not_observed`，Gate `failed`。失败集中于退款率排名（result/output/schema context）、实际金额指标绑定、渠道 GMV dashboard schema context；无 external unavailable。Docker daemon 恢复后，Milvus `m27-core-20260809-qwen37plus-milvus-01` 完成：DashScope `qwen3.7-text-embedding`、1024 维、weighted、独立 collection `datapilot_schema_docs_m27_qwen37plus_qwenemb_20260809_164000`；实测 195 entities、hash `8a8b6626...`。两侧 assertion 计数、失败 Scenario/断言/reason 均一致。各只运行一次，记录为“本轮未观察到 Milvus 改变结果”，不作因果或默认切换结论。
- 2026-08-09：用户授权 Qwen `qwen3.7-max` 的 M27 Core local / Milvus 对照。执行工具前台返回超时后，local 子进程实际仍在后台继续完成；因此除配置错误后主动停止的 `-03` 外，`-01`、`-02`、`-04`、`-05` 都产生了 completed artifact。**这是本轮执行重复的失误**：用户只授权一次 local，但意外得到 4 次 local 快照，必须保留并如实记录，不能选择性删除。
- 四次 local required 分别为：`-01` 28 passed / 6 failed / 0 not_observed，`-02` 29 / 5 / 0，`-04` 13 / 20 / 1，`-05` 9 / 23 / 2；均 Gate `failed`。它们显示同配置下显著波动，不能挑选 `-05` 与 Milvus 单次相同的结果来声称稳定对照。
- 改由一次性 Windows task worker 后，local `m27-core-20260809-qwen37max-local-05` 完成：19/19 logical / physical，Core required assertion **9 passed / 23 failed / 2 not_observed**，Gate `failed`；无 external unavailable/pipeline error。Milvus `m27-core-20260809-qwen37max-milvus-01` 以同一模型、45s/retry0、weighted、SQLite deterministic seed、LangFuse off 完成，计数与 assertion views 完全一致。
- Milvus 实测 collection 为 `datapilot_schema_docs_m27_qwen37max_qwenemb_20260809_180700`：DashScope `qwen3.7-text-embedding`、1024 dim、195 entities、description hash `8a8b6626a4cbec...`。该配对各一次，只能描述为“本轮未观察到 Milvus 改变 qwen3.7-max 的 Core assertion 结果”；不能推断 embedding 因果、稳定性或默认切换。

## M27 Review Bundle 增补（用户授权，进行中）

- [x] 新增独立 `eval.review` module 与 `eval.run_review` CLI：从 completed M27 artifact、短期 checkpoint 和 canonical catalog 生成 Codex 可读的 review bundle。
- [x] bundle 只保存脱敏的 candidate/reference SQL、有限结果样本、trace 摘要、assertion 事实与合同摘要；不得改写 EvalRun、projector 分母或 Gate，也不调用 LLM。
- [x] 支持独立写入 Codex/manual verdict 与 auto/manual reconciliation；M26 `eval.run_audit` 继续只读 legacy 输入，不能复用。
- [x] 补确定性测试、更新 runbook / cases README / state 档案，并运行针对性 pytest；不运行新的真实 LLM eval。

### 实现与验证结果

- 用户在 M27 原计划已明确“不建设人工 verdict/review workflow”的基础上，明确授权此旁路增补；实现保持不改 EvalRun、自动 scorer、projector、Gate、分母和 M26 legacy audit 的边界。
- `eval.review.build_review_bundle()` 是唯一组装 Interface：它校验 completed M27 artifact、raw checkpoint、catalog 的 run/scenario/replicate/assertion 身份，缺失或不一致即失败。bundle 提供 candidate/reference SQL、最多 3 行脱敏 candidate/reference preview、trace 摘要、contract 和 assertion 事实；email/phone/credential key 与文本中的 email/手机号会被脱敏。
- `apply_review_verdicts()` 强制所有 logical Scenario 都有 `pass/fail/insufficient_evidence`、confidence、reason 和 evidence，输出独立 reconciliation；`eval.run_review` CLI 不执行 Pipeline/LLM，只写 `eval/reports/m27-reviews/`。
- 验证：`python -m pytest -q tests/test_m27_review.py tests/test_m27_foundation.py tests/test_phase3a_eval.py --basetemp=.codex/temp_work/pytest-m27-review-final`：**38 passed, 1 warning**（既有 Starlette/httpx deprecation）。对既有 `m27-smoke-20260809-02` 运行 CLI 后生成 4 条 Codex high-confidence `pass` verdict；无新的真实 LLM 调用。

## M27 Review Evidence Hardening（用户授权，进行中）

- [x] 为 completed artifact 与每条 checkpoint 记录 SHA-256，并提供只读校验入口。
- [x] 让无 candidate SQL 的普通业务题只能标为 `insufficient_evidence`；安全/预期拒绝题仍可凭拦截证据通过。
- [x] 为人工 verdict 增加受限的结构化分类，并在报告汇总分类计数。
- [x] 固化 Core/Stress 的人工复核覆盖规则，保持旁路、不影响 Gate/CI。
- [x] 核验 M26 指出的退款整单回退反事实是否已有确定性保护，避免重复造测试。

### 关键判断与取舍

- review bundle 升为 `m27-review-bundle-v2`：来源哈希应绑定“当时看到的 artifact/checkpoint”，而非加入 EvalRun；`--verify-bundle` 只读重算，来源被清理、改写或替换就失败。早期 v1 review 没有哈希，保留为历史材料，不假装可被 v2 校验。
- 普通业务题没有 candidate SQL 时，Codex 看不到实际模型答卷；此前允许手写 `pass/fail` 容易把“没拿到材料”误说成“答案对/错”。现在强制 `insufficient_evidence + execution_evidence_unavailable`。安全/预期拒绝题例外，因为 Guard 的拒绝原因本身就是合同所需证据。
- `category` 被限制为正确、正确拒绝、业务 SQL、输出合同、Schema Context、执行证据不可用、其他合同错误八类，并与 verdict 和 assertion kind 交叉校验；报告只汇总定位，绝不反写自动分数/Gate。
- 复核覆盖采用“全部自动失败 + 高风险业务合同 + 少量自动通过抽样”，而不是把每轮 Core/Stress 的全部通过题都人工再判一次。退款、SCD、金额、时间、递归属于高风险合同。
- M26 指出的 completed 状态 / 整单退款 fallback 已由 `tests/test_m25_eval_trustworthiness.py` 和 `tests/test_m26_targeted_contracts.py` 的 SQLite 反事实保护；M27 catalog 也沿用 `COALESCE(order_items.product_id, refunds.product_id)` 合同。因此本轮不重复复制同义测试，改为在验证命令中纳入这两组现有保护。

### 本轮验证快照

- `python -m pytest -q tests/test_m27_review.py tests/test_m27_oracle_counterfactuals.py tests/test_m27_foundation.py --basetemp=.codex/temp_work/pytest-m27-review-hardening-final`：**20 passed, 1 warning**。新增覆盖 artifact/checkpoint SHA-256 篡改检测、无 SQL 普通题的 `insufficient_evidence` 限制、verdict 分类汇总；warning 为既有 Starlette/httpx deprecation。
- 再加 M25/M26 的退款反事实保护：`python -m pytest -q tests/test_m27_review.py tests/test_m27_oracle_counterfactuals.py tests/test_m27_foundation.py tests/test_m25_eval_trustworthiness.py tests/test_m26_targeted_contracts.py --basetemp=.codex/temp_work/pytest-m27-review-hardening-final2`：**37 passed, 1 warning**。
- `python -m eval.run_review --help`：成功展示 `--verify-bundle`；仅解析 CLI，无 Pipeline/LLM 调用。
- `git diff --check`：通过；仅有 Git LF→CRLF 工作区提示，无 whitespace error。
- 未重跑真实 LLM、未改模型/检索/embedding/数据库/oracle/default reliability，也未重写既有 v1 Smoke review 历史文件。
