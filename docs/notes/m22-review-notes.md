# M22 Eval Contract / Database / Semantic Layer Review Notes

> 本文件记录 M22 计划制定前的只读审计素材。审计目标是区分“reference SQL / case 契约问题、确定性数据库事实问题、语义层或 QueryPlan → SQL 问题”；不在本轮修改业务代码、case、scorer、数据库或默认配置。

## 审计清单

- [x] 盘点三套 eval case 的 check 类型、expected SQL 和输出契约覆盖范围。
- [x] 在独立确定性 SQLite seed 上重放全部允许 SQL 的 expected SQL，记录执行 / 非空 / 固定事实一致性。
- [x] 核对 `metrics.yaml`、schema descriptions、relations 与 case 的指标 / 表 / 列期望是否存在明显冲突。
- [x] 对 M21 Qwen-plus controlled A/B 的 output contract / result contract 失败逐 case 审查，判断失败层和 reference 争议。
- [x] 运行现有数据库与 eval 契约回归，记录其能证明和不能证明的边界。
- [x] 汇总问题、证据强度、修复候选与 M22 plan 前需要用户确认的决策。

## 审计范围与固定条件

- Eval 输入：`eval/cases/phase3a-regression.yaml`、`database-upgrade-challenge.yaml`、`phase3a-diagnostic-benchmark.yaml`。
- 语义事实源：`domain_pack/metrics.yaml`、`domain_pack/schema_desc/*.md`、`domain_pack/schema_desc/relations.yaml`。
- 数据库 oracle：`scripts.seed_data.seed_database()` 创建的 in-memory SQLite；它与 `result_match` scorer 的 oracle 一致。
- 近期端到端证据：M21 Qwen-plus local deterministic / clean Milvus + Qwen embedding controlled A/B，均为 diagnostic `21/32`。

## 过程素材

### A. Case / oracle 静态审计（2026-08-04）

审计使用与 `rule:result_match` 完全相同的 in-memory SQLite + `seed_database()` oracle，只读检查三份 case 文件。一次性脚本与 JSON 结果已在审计完成后从临时目录清理；本表保留全部结论性素材。

| 检查项 | 结果 | 说明 |
|---|---:|---|
| Case 总数 | 42 | formal 10、challenge 16、diagnostic extra 16；实际 diagnostic run 复用 challenge，因此为 32 条。 |
| allow case | 36 | 其余 6 条为安全拦截 case。 |
| 含 `expected_sql` case | 14 | 全部来自当前可重放的 SQL 类 case。 |
| reference SQL 可执行 / 非空 | `14/14` | 未出现语法错误、缺表、缺字段或空结果。 |
| `expected_metrics` 悬空引用 | `0` | 每个 metric key 都存在于 `metrics.yaml`。 |
| `expected_tables` 悬空引用 | `0` | 每个 table 都存在于 DomainSchema。 |
| 固定业务事实 | 全部复现 | GMV `11285752.00`、Mobile App 渠道 GMV / JUNE_FIXED_50 使用第一、Aurora 退款率第一、数码电子一级类目 GMV 第一等均与 `database-current-state.md` 一致。 |

结论边界：这证明 reference SQL 与确定性数据库的**可执行性和数据一致性**，不能证明自然语言问题、指标口径、expected SQL 与 scorer 的输出契约三者必然语义一致。

### B. 已确认的 case / 语义契约问题

| Case | 证据 | 审计判断 | 影响 | 修复候选 |
|---|---|---|---|---|
| `db_core_002`（退款率最高商品） | `metrics.yaml` 规定商品维度退款率优先 `refunds.order_item_id -> order_items.product_id`；reference SQL 却使用兼容关系 `orders.product_id -> products`。M21 生成 SQL 采用 `order_items + refunds.order_item_id`，却因没 join `products`、输出 `product_name_snapshot` 被 table contract 判失败。 | reference SQL / expected table 与当前正式指标口径冲突；该次失败不能直接归因 retrieval。 | 高：可能把更符合口径的答案判错。 | 由用户确认唯一的商品退款率口径；若选明细归因，reference SQL、expected tables / columns、alias 一起改为该口径。 |
| `db_multi_001` 与 `db_trace_002`（JUNE_FIXED_50 使用最多渠道） | 问题和 reference SQL计算的是 `COUNT(DISTINCT order_id)`，但 `expected_metrics=[coupon_usage_rate]`；M21 SQL 使用等价计数 alias `used_order_count`，而 case 仅允许 `coupon_order_count / usage_count`。 | metric 标签与问题/SQL 不一致；输出 alias 白名单过窄。 | 高：错误的 metric doc 可干扰 SchemaGraph；等价 SQL 也会被扣分。 | 将指标改为 `order_count` 或新增明确的 `coupon_order_count` 派生指标；将 `used_order_count` 加入 alias，或统一输出别名。两个重复题保留时应明确一个测 trace、一个测结果，避免重复放大。 |
| `db_multi_002`（一级类目销售额排名） | reference SQL 聚合兼容冗余字段 `products.category`；数据库事实源明确“规范类目层级优先 `products.category_id -> product_categories`”。 | “一级类目”自然语言与 reference SQL 的层级语义不一致；当前 seed 的首行名称碰巧一致，不能消除口径风险。 | 中高：以后数据有多级类目时会误评。 | 把问题改为“商品旧类目字段销售额”，或把 reference SQL 改为类目树 / 一级类目关系口径。 |
| `db_hard_001`（数码电子及子类目 GMV） | `expected_metrics=[item_gmv]`，reference SQL 输出别名却为 `gmv`。 | 同一 case 将商品明细 GMV 口径和订单 GMV 名称混用。 | 中：manual case，但会误导 prompt / plan 语义。 | 若保持明细口径，输出与 expected column 统一为 `item_gmv`；若业务要称 GMV，需在 metrics / case 中显式说明它是商品维度 GMV。 |

### C. 已确认的 scorer / 失败归因问题

`score_case_rules()` 固定在 `table_hit → column_recall → output check` 顺序早返回；`table_hit` 和 `column_recall` 都读取最终 API 响应的 `tables_used` / `columns`，不是 SchemaGraph 或 local prompt 的上下文。

| Case | M21 local weighted 实际 SQL / 结果 | 审计判断 | 解决方向 |
|---|---|---|---|
| `db_prompt_001` | SQL 正确使用 `order_items.line_amount`、`orders.order_amount/paid_at/order_status`，并正确得到商品 Top 5；但最终输出列只有 `product_name, item_gmv`。 | `schema_context_size` case 被最终输出列契约提前判失败，不能衡量预期的 local schema context。 | 为 context 类型 case 从 trace / SchemaGraph metadata 评分，或将它们的输出列检查改为非阻断；不要要求最终结果返回内部计算字段。 |
| `db_prompt_002` | 输出的平均价使用 `pph.valid_from >= 6 月初`，没有实现 reference SQL 的“与 6 月时间窗口重叠”条件。 | 这是**真实语义层 SQL 错误**，但当前同时被输出列失败遮蔽。 | M22 应加入 SCD overlap 的 QueryPlan / SQL contract，并为该题建立可执行 result check 或结构化 SQL 断言。 |
| `db_prompt_003` | SQL 的 `coupon_type + SUM(order_amount)` 合理，但问题未给时间范围；case 却要求输出内部字段 `coupon_code/order_amount/paid_at`。 | 输出列契约对问题本身过度约束；是否应带 6 月过滤也没有由自然语言或 check 定义。 | 明确问题时间范围和指标口径；将内部 context 字段从最终输出列期望中拆出。 |
| `db_plan_002`（不存在 supplier_name） | 实际生成 `SELECT products.id, products.product_name FROM products`，未按 case 期望 blocked；随后被 `missing_columns` 早返回。 | 真实问题是 QueryPlan / validation 未可靠地阻断不存在字段；当前 scorer 的早返回使报告没有展示本应检查的 `plan_validation_blocked`。 | 先使 block case 优先运行其专属 contract；再改 planner / generator 的不存在字段阻断行为。 |
| `db_core_004`（渠道订单量） | 生成 SQL 使用正确表、正确计数和分组，但遗漏 `ORDER BY order_count DESC, channel_name ASC`；实际首行 Douyin，reference 首行 Mobile App。 | 这是**真实 SQL 输出契约错误**，不是 reference 或数据库问题；严格 `result_match` 合理。 | 在 QueryPlan 显式携带排序，SQL prompt / validator 校验 `order_by` 传递，保留该 case 的严格行序断言。 |
| `db_plan_003` / `db_plan_004` | 预期阻断，但本轮在 `llm_generation_error` 处失败。 | 还不能验证 expected block contract；错误处理与 “模型识别不支持需求” 被混为一谈。 | 分离 LLM transport / generation error 和 semantic rejection；block case 必须有可观测的 `blocked_via` / issue tag。 |

### D. 近期失败结构复核

M21 Qwen-plus local deterministic + weighted 的 32 条 diagnostic：`21/32`；失败 subtype 为 `output_column_contract=6`、`output_table_contract=2`、`result_contract=1`。clean Milvus + Qwen embedding 组同为 `21/32`，subtype 分布完全相同。

- 这支持“当前主要瓶颈不在 embedding / DB 可用性”的判断。
- 其中至少 `db_core_002`、`db_multi_001`、三个 `db_prompt_*` 失败含 case / scorer 契约成分，不能把 9 个 subtype 失败全计为模型能力缺失。
- 同时 `db_core_004`、`db_prompt_002`、`db_plan_002` 给出明确的 QueryPlan → SQL / semantic validation 缺口，不能把问题完全推给 eval。

### E. 回归验证

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q tests\test_database_upgrade.py tests\test_phase3a_eval.py --basetemp=.agent_work\temp\eval-diagnosis-pytest
```

结果：`25 passed, 1 warning`（既有 Starlette/httpx `TestClient` deprecation warning）。这些测试覆盖数据库固定事实、challenge reference SQL 的可执行性、case 结构和部分 result-match 契约；不覆盖上表指出的自然语言—指标—reference SQL 三方语义一致性。

## 审计结论与 M22 plan 前决策点

### 结论

1. **不是数据库损坏主导。** 确定性 oracle、14 条 reference SQL 和固定业务事实均正常；数据库中 5 条金额不一致、整单退款等是刻意的诊断数据，应由口径处理而非清洗。
2. **reference / case 契约存在实质性语义债务。** 至少 `db_core_002`、`db_multi_001`、`db_multi_002`、`db_hard_001` 有口径、指标标签或别名的不一致；其中前两项会直接影响受控诊断分数的解释。
3. **scorer 将“上下文应包含什么”和“最终 SQL 应输出什么”混为一层。** 三个 `schema_context_size` case 的失败不能作为缺 schema context 的充分证据。
4. **语义层 / QueryPlan → SQL 确有真实缺口。** 排序、SCD overlap、未知字段阻断与“不支持需求”的结构化拒绝都需要 M22 处理。

### 等待用户确认的范围选择

- 是否授权 M22 先修正上述 case / scorer 评测契约，再以修正后的固定基线处理 pipeline？推荐：**是**。否则模型分数会混入可避免的 false negative，难以衡量 pipeline 改进。
- `db_core_002` 的商品退款率是否以“订单明细归因”为唯一默认口径？推荐：**是**，与 `metrics.yaml` 和数据库事实源一致。
- `db_multi_002` 的“一级类目”是否采用规范类目树，而不是兼容字段 `products.category`？推荐：**是**。
- 对 manual / diagnostic case，是否继续计入当前 `diagnostic 21/32` 总分？推荐：保留展示，但单列“可评分能力分”和“人工审查分”，不将 manual case 冒充为稳定硬门。
