# M24 SQL Plan Contract Semantic Equivalence / Plan-to-SQL Fidelity Notes

## 审查范围与结论（2026-08-06）

本文件是对 `docs/phase3b-langfuse-plan-v6.md` 中 M24 的**执行前审查**，本次不改业务代码、case、scorer 或默认配置。

结论先说：M24 的大方向是对的。M23 已把数据库事实、reference SQL 和自动判分的地基收紧；在新合同的本地首跑里，已经没有“目标 schema 没召回”的失败证据，主要乌云落在 SQL 计划合同、QueryPlan 到 SQL 的信息丢失，以及最终输出契约。因此下一步不应继续把分数差先归咎于 embedding / Milvus。

但 M24 还不能直接按当前文字开工。计划中混入了两处统计口径矛盾，也还缺少“拿什么历史事实来验证 AST 比较器”的可复现实验。先收口这些前置事实，才能避免把真正漏掉 `LIMIT` 的 SQL 和“只是写法不同”的正确 SQL 一起处理错。

## 已核对的事实

| 事实 | 证据与解读 |
|---|---|
| M23 local 新合同首跑为 `23/32`，自动能力为 `20/27`，人工/诊断为 `3/5`。 | `eval/reports/m23-qwen-local-weighted-diagnostic-report.md`、`eval-baselines.md` 的 M23-E03。它是 195-doc/hash `ce04fe4f...` 下的第一条基线，不能与 M22 的 194-doc `24~28/32` 横比。 |
| 本地首跑有 9 条硬失败、3 条 review 标记，合并去重后是 10 条 failed-or-review。 | 3 条 review 中有 2 条同时是硬失败；`db_hard_003` 是唯一额外的 review-only。三条自动结果问题分别是：`db_simple_001` 缺稳定排序、`db_simple_002` 漏 `LIMIT 10` 且投影超量、`db_simple_003` 多投影 7 列。 |
| 9 条 failed 中并非都是自动 case。 | `20/27` 意味自动失败应是 **7 条**；总 failed 是 9 条，因此另有 **2 条人工/诊断**失败。这与 M23/M24 文本里的“9 个自动失败”不一致。 |
| 已有可确认的字符串误拦。 | `db_trace_002` 的 trace 显示计划要 `COUNT(DISTINCT order_coupons.order_id) DESC`，候选 SQL 用等价的 `ORDER BY coupon_usage_count DESC`（SELECT alias），却被 `normalized_string_contains` 拦截。M24 用 AST 做窄语义比较有直接证据。 |
| Milvus + Qwen embedding 的同合同单次报告已经存在，分数为 `21/32`。 | `eval/reports/m23-qwen-milvus-qwenemb-diagnostic-report.md` 有 195 docs、hash、1024 维和 `run_scoped` 元数据；所以 M24 的 `21/32` 并非凭空数字。但截至审查时 `AI_CONTEXT.md`、`eval-baselines.md` 和 changelog 还写“待跑”，状态文档已过期。 |
| `21/32` 不是 embedding 退化的结论。 | 两组各仅一次真实 LLM run；而且 Milvus run 额外暴露的 `db_multi_001/002`、`db_hard_001` 等现有 triage 仍有“最终输出表/列契约被旧桶标成 schema_context/retrieval”的历史包袱。它只说明：先消除合同与生成噪音，比再调 embedding 更优先。 |

## 通过率上的“乌云”是什么

1. **新旧合同混用的乌云**：M22 是 194-doc/旧 case-scoring 合同，M23 是 195-doc/新合同；`24~28/32` 与 `23/32` 不表示模型突然变差，也不能用于判断 M24 是否“提分”。
2. **总分和自动能力分混用的乌云**：32 条总分包括人工/诊断项；M24 应同时报告 `automated_capability`、manual/review、以及 `failed`，不能只写一个 `passed/32`。
3. **“合同误拦”和“真生成错误”混用的乌云**：`db_trace_002` 这类是正确 SQL 被字符串规则挡住；`db_simple_002` 真漏 LIMIT；两者都能让分数下降，却需要完全相反的处理。
4. **旧 triage 桶名的乌云**：`table_hit` / `column_recall` 有时检验的是最终结果 `tables_used` / `body.columns`，并不是 SchemaGraph 是否召回。因此报告中出现 `schema_context` 或 `schema_retrieval` 标签，不能不看 trace 就当成检索失败。
5. **单次真实 LLM 的乌云**：M23 local `23/32` 与 Milvus `21/32` 各只有一次。其差值不能归因给 embedding，更不应据此切默认检索路径。
6. **历史 trace 不能完整复演的乌云**：当前失败 trace 通常只留 `candidate_sql_preview`、计划排序/limit 摘要和观察到的子句，未稳定保留完整候选 SQL 与完整结构化 QueryPlan。M24 想用 AST 给“每个放行”留证据时，不能假设可由旧 trace 精确重放所有案例。

## 对当前 M24 计划的优化建议（按优先级）

### P0 — 先统一事实账本，再开始任何实现或 A/B

- 将 M23 Milvus 结果登记为已完成的**单次诊断快照**：`21/32`，并记录报告、trace、triage 路径和运行元数据；删除或修正所有“同合同对照待跑”的表述。
- 将“9 个自动失败”改为“自动失败 7 条；总 failed 9 条，其中 2 条属于人工/诊断集合”，并在计划、changelog、eval-baselines、AI_CONTEXT 使用同一口径。
- M24 的基线表固定同时列出：`total`、`automated_capability`、`manual/review`、`contract_false_block`、`true_fidelity_failure`。否则后续合同修复会让总分看似上涨，却无法说明是修复了误拦还是模型真的少犯错。

### P0 — 先做“历史失败逐条定性表”，不要一上来泛化 AST 规则

M24 应在实现前列出每个候选 case 的：完整 QueryPlan step、完整 candidate SQL、SQL Guard 结果、执行结果（若有）、`result_match`、目标 schema 是否已在 context，以及人工定性。建议状态只能是：

- `semantic_false_block`：SQL 等价，但旧字符串合同误拦；
- `true_order_or_limit_loss`：计划有，SQL 真缺；
- `projection_mismatch`：漏列/多列/别名等价，需按输出政策判定；
- `generation_or_plan_error`：没有可用候选 SQL，不能归为合同问题；
- `insufficient_evidence`：旧 trace 不够，必须重新采样。

这样 `db_trace_002` 可以先成为 AST comparator 的正例；`db_simple_002` 成为必须拒绝的反例。`db_core_002`、`db_join_003` 等 LLM error 则不能被“语义等价”模块假装解决。

### P1 — 把 AST 等价规则写成可拒绝的、小范围规格

当前计划写了“唯一可解析”和“保守失败”，方向正确，但应补齐机器可执行的边界：

- 明确 SQL dialect（SQLite eval 与 MySQL 审计分别如何 parse），以及 parser 失败时的固定失败分类；
- 明确别名作用域：只允许同一个 SELECT scope 内 `ORDER BY select_alias` 回溯，不能跨 CTE/子查询猜测；
- 限定无表名前缀表达式只在相关列唯一时放行；多表同名列、函数语义不同、ordinal order（如 `ORDER BY 1`）一律保守失败，除非另立有测试的规则；
- 对多个排序项必须按顺序、方向逐项匹配；`LIMIT` 应区分数值、参数、`LIMIT offset,count` 等形式；
- 明确 AST 正规化只是**比较证据**，绝不向 SQL 回填/改写。

这会把 `SQLPlanFidelityContract` 真正做成深模块，而不是把旧的字符串 if-else 换成更复杂的一堆 AST if-else。

### P1 — 输出投影先定“产品政策”，再写判定器

`db_simple_003` 的额外 7 列是确凿问题，但“任何额外列都失败”还是“允许非敏感额外列”是 API/评测语义选择，不是 parser 能自动决定的事。M24 应先确认并记录：自动 `result_match` case 是否要求列名、顺序和列集合完全一致；对人工 case 是否只报告差异；敏感列始终不能因“允许额外列”而放过。

在未确认前，建议临时沿用当前自动 case 的**精确投影合同**，并把政策切换列为独立决策门，不混入 AST 等价修复。

### P1 — 让 trace 能成为将来的可复现实验材料

M24 需要在设计中明确新增的证据字段：完整（可脱敏/长度受限但不可截断到无法解析的）candidate SQL、结构化 QueryPlan step、解析 dialect、计划 AST 摘要、SQL AST 摘要、别名绑定表、比较结果和拒绝原因。仅保留 `candidate_sql_preview` 无法支持以后复演或审计。

### P2 — A/B 设计采用交错重复，而不是“两个三连跑后看平均”

每组至少 3 次是下限，但建议 local 与 Milvus 交错运行（例如 L/M/L/M/L/M），每次记录 run 序号、时间、完整 runtime metadata 和每 case 成败。主读数应是每 case 的通过次数、自动能力分的范围/中位数、合同误拦数量与真保真失败数量；不要只比较均值或单个总分。

## 正式执行 M24 前建议的前置实验

### 实验 A：离线合同回放 spike（必须先做）

**问题**：历史失败里哪些真的能由 AST 证明“等价但被误拦”？

**做法**：从 M22/M23 trace 提取完整资料；若旧 trace 没有完整 SQL/计划，则为每个候选 case 用固定输入重新收集一次完整的 QueryPlan 与候选 SQL，不计入能力分。用一个纯函数原型只比较，不接入 pipeline。

**最小样本**：

- 正例：表别名、反引号、限定名省略、SELECT alias 排序（至少含 `db_trace_002`）；
- 反例：方向反了、排序项顺序变了、真缺 `ORDER BY`（`db_simple_001`）、真缺 `LIMIT 10`（`db_simple_002`）；
- 边界：歧义无前缀列、CTE/子查询、多个排序项、`SELECT *` 和额外输出列。

**通过条件**：每个正例有明确 alias/scope 证据并放行；每个反例保持拒绝；无法解析或歧义的 SQL 均返回 `indeterminate/failed`，不猜测。

### 实验 B：输出投影政策审计（必须先做）

**问题**：自动 case 的“列不一样”应怎样计分，是否有任何允许额外列的业务场景？

**做法**：抽取 formal/challenge 中所有自动 `result_match` case，生成“计划输出列 / SQL SELECT 列 / 实际 body.columns / expected result columns”的差异表，特别检查 `db_simple_003`、`db_multi_001/002` 和敏感字段 case。

**产出与决策**：得到一页明确政策：自动 case 是否 exact columns + exact order；允许何种别名等价；人工 case 只如何报告；敏感列一律怎样处理。未经该决定，不实施“额外投影”放宽。

### 实验 C：小规模稳定性校准（建议在接入前做）

**问题**：同一模型对“有明确 order/limit/output 要求”的 case 本身波动有多大？

**做法**：在不改任何合同规则的前提下，先对 M23 的 3 个真保真 case 与 2~3 个疑似误拦 case 重复 3 次，只收集 QueryPlan、candidate SQL 和阻断类别。

**为什么有用**：它能区分“规则修复后确实少拦了等价 SQL”与“恰好这次 LLM 自己生成得更好”。这不是 embedding A/B，也不修改默认配置。

### 实验 D：合同修复后的受控 A/B（M24 收尾，不是前置代码验证）

在 A/B/C 完成、规则实现并通过确定性回归后才做。固定 195-doc/hash、Qwen `qwen3.7-plus`、weighted、SQLite deterministic oracle、LangFuse off、同代理、32 条 diagnostic；local 与 clean Milvus/Qwen embedding 各至少 3 次并交错执行。结论必须按“检索确实缺上下文 / 合同误拦 / 真生成失败”分层，不能仅用 `passed/32` 下判断。

## 建议的 M24 验收补充

- 给出一张逐 case 的最终归因表，并标明证据等级；`insufficient_evidence` 不能硬塞进 retrieval 或 SQL generation。
- SQL Plan Contract 的单测应同时覆盖 SQLite 和 MySQL 可解析的语法边界，或显式声明只验证生成目标 dialect；不能只在一种 parser 默认方言下悄悄通过。
- 任何从阻断改为放行的历史 case，都必须同时有 SQL Guard 通过、比较证据和（自动 case 时）结果正确证据；只通过“合同检查”不等于回答正确。
- state 文档中的 M23-E03、M24 前置事实和实验索引在运行后同一轮同步，避免再次出现“报告已存在、账本仍写待跑”。

## 本次审查未做的事

- 未修改代码、eval case、scorer、默认模型、embedding、Milvus、fusion、数据库或计划文件。
- 未把任何真实 LLM 单次结果改写成能力结论；M23 的 local `23/32` 与 Milvus `21/32` 仅作为 M24 排序优先级的诊断证据。

## 开工前置关卡执行记录（2026-08-06）

### Checklist

- [x] 同步 M23 local / Milvus 单次诊断事实账本。
- [x] 建立 M22/M23 历史失败逐 case 定性表。
- [x] 执行只读离线 AST 合同回放 spike。
- [x] 审计 formal / challenge 自动 `result_match` 输出投影政策与现状。
- [x] 用户确认“精确投影 + 显式 alias + 严格展示顺序”，并授权按 6 点修订 M24 plan 后进入实现。

### Implementation checklist（2026-08-06，用户确认后）

- [x] 新增 `SQLPlanFidelityContract` 深模块，interface 同时服务 pipeline 与 focused tests。
- [x] 用 sqlglot AST 替换 `normalized_string_contains`，保持保守 scope / ambiguity / limit 边界。
- [x] 在合同中独立记录 order/limit 与 output projection/display order 证据。
- [x] SQL Guard 预检查先于 fidelity contract；危险 SQL 不因合同解析失败改变安全归因。
- [x] trace 保存完整 candidate SQL、结构化 QueryPlan、dialect、AST/alias/reason code/evidence level。
- [x] 修正 final-output 失败的 triage 归因，补 pure module / pipeline / scorer focused regression。
- [x] 只运行本地 focused 验证；不运行完整 formal / challenge / diagnostic，交由用户手动执行。

### 事实账本最终口径

| 组 | total | automated_capability | manual_or_diagnostic | failed / review 解释 |
|---|---:|---:|---:|---|
| local deterministic / weighted | `23/32` | `20/27` | `3/5` | 9 条硬失败；7 自动 + 2 人工/诊断。3 条 review 与硬失败重叠 2 条，因此 failed-or-review 去重为 10。 |
| clean Milvus + DashScope Qwen embedding / weighted | `21/32` | `20/27` | `1/5` | 11 条硬失败；自动分与 local 相同，差异来自人工/诊断项。 |

Milvus 运行元数据：collection `datapilot_schema_docs_m23_qwen_plus_qwenemb_20260806_154117`，195 docs，hash `ce04fe4fefc1cfb9226562f55154a1ed59eb91e9e41c3a83823c53ea491061b1`，1024 维，run-scoped，首次写入 195、final row count 195，SQLite deterministic oracle。它是 clean 新建快照，不是旧污染 collection 的复用。两组各只有一次真实 LLM run，不能将 `23→21` 解释为 embedding 退化；更关键的是两组自动能力都为 `20/27`。

状态同步位置：`AI_CONTEXT.md`、`eval-baselines.md`（新增 `M23-E04`）、`AI_CONTEXT_CHANGELOG.md`、`schema-retrieval-milvus-embedding.md`。旧 changelog 中“9 个自动失败”和“Milvus 待跑”已以修正注记收口。

### M22/M23 历史失败逐 case 定性表

证据等级：A = trace 有可解析完整候选 SQL或最终 SQL、计划 order/limit 摘要与运行结果；B = candidate 只有 preview，但计划/观察摘要足以定位合同层；C = 旧 trace 缺完整 QueryPlan / candidate，不能离线复演。`Context=有` 表示目标表/字段已在同请求 SchemaGraph；旧 `table_hit/column_recall` 若读取最终输出，不作为 retrieval 证据。

| 历史观察 | 计划 / SQL / 运行证据 | Context / Guard / result | 定性 | 等级 |
|---|---|---|---|---|
| M22 C0 `db_simple_001` | plan `products.id ASC, LIMIT 10`；candidate `ORDER BY id ASC LIMIT 10` | 合同前阻断；完整 candidate 可解析 | `semantic_false_block`（限定名省略） | A |
| M23 local + Milvus `db_simple_001` | 最终 SQL 只有 `LIMIT 10`，无 `ORDER BY`；返回首行与 reference 不同 | Context 有；Guard / SQL 执行通过；`result_match` 失败 | `true_order_or_limit_loss` | A |
| M22 C0 `db_simple_002` | plan `orders.paid_at [ASC]`；candidate `ORDER BY paid_at [ASC]` | 合同前阻断；完整 candidate 可解析 | `semantic_false_block`（限定名省略） | A |
| M23 local + Milvus `db_simple_002` | 最终 SQL `ORDER BY paid_at DESC` 且无 `LIMIT 10`；投影 9 列而非 3 列，返回 6681 行 | Context 有；Guard / SQL 执行通过；`result_match` 失败 | `true_order_or_limit_loss`（主）；同时存在 projection mismatch | A |
| M23 local + Milvus `db_simple_003` | 最终 SQL 输出 10 列，合同只要 `coupon_code/name/type` 3 列 | Context 有；Guard / SQL 执行通过；列集合失败 | `projection_mismatch` | A |
| M22 C0/C2/C3 `db_core_004` | plan `order_count DESC, channels.channel_name ASC`；candidate 使用 `order_count` SELECT alias、`c/t1.channel_name` 与反引号 | Context 有；合同前阻断；多份完整 candidate | `semantic_false_block` | A |
| M22/M23 `db_multi_001` | plan 聚合表达式 DESC + `LIMIT 1`；candidate 用 `usage_count/used_order_count` SELECT alias，观察到 limit=1 | Context 有；多份 M22 candidate 完整，部分 M23 preview 截断 | `semantic_false_block`；M23 Milvus 放行后的额外 `channel_code` 另属 projection mismatch | A/B |
| M23 local `db_multi_002` | QueryPlan LLM error，无候选 SQL | Context 已有六张目标相关表；无 Guard / execution / result | `generation_or_plan_error` | A |
| M23 Milvus `db_multi_002` | SQL 可执行，但用非递归一级类目过滤，输出 `name,item_gmv`，合同要 `root_category,item_gmv` | Context 有；Guard / SQL 执行通过；最终列合同失败 | `projection_mismatch`（同时有 plan/语义错误，AST 合同不能修） | A |
| M23 local + Milvus `db_core_002` | SQL generation LLM error，无候选 SQL | Context 精确含 products/order_items/orders/refunds；无执行结果 | `generation_or_plan_error` | A |
| M23 local `db_hard_001` | QueryPlan LLM error，无候选 SQL | Context 含全部目标表；无执行结果 | `generation_or_plan_error` | A |
| M23 Milvus `db_hard_001` | SQL 执行但改走 `orders_wide + product_categories`，输出订单 GMV `gmv`，而 case 要星型模型 `item_gmv` | Context 已含星型目标表；旧 triage 标成 retrieval 只因最终 `tables_used` 不符 | `generation_or_plan_error` | A |
| M22/M23 Milvus `db_hard_003` 与 `db_prompt_002` | plan `products.product_name`；candidate `ORDER BY p.product_name` | Context 有；合同前阻断；candidate 完整 | `semantic_false_block`（表别名） | A |
| M23 local `db_hard_003` | SQL 已生成并执行，属于 manual review，未做自动 reference 判定 | Context 有；Guard / SQL 执行通过 | `insufficient_evidence`（不是硬失败，不能凭 manual 标签判语义正确） | A |
| M23 local + Milvus `db_join_003` | SQL generation LLM error，无候选 SQL | Context 精确含四张目标表 | `generation_or_plan_error` | A |
| M22 C2 `db_plan_001` | plan `gmv DESC`；candidate `ORDER BY \`gmv\` DESC`；其他 run 为聚合表达式 vs SELECT alias | Context 有；合同前阻断 | `semantic_false_block`（反引号 / SELECT alias） | A/B |
| M22 C1/C2/C3 `db_schema_003` | plan `SUM(orders_wide.actual_amount) DESC` 或 `gmv DESC`；candidate 为 `SUM(actual_amount)` 或 `ORDER BY gmv/\`gmv\`` | Context 有；合同前阻断 | `semantic_false_block`（唯一限定名省略 / SELECT alias / 反引号） | A/B |
| M22/M23 `db_trace_002` | plan `COUNT(DISTINCT ...id) DESC, LIMIT 1`；candidate 用 `usage_count/coupon_usage_count` alias，观察到 limit=1 | Context 有；多份 M22 完整 candidate，M23 preview 截断 | `semantic_false_block` | A/B |
| M22 default `db_simple_001/002/core_004` 最早快照 | 只记录 `sql_plan_contract_failed`，没有 candidate / planned / observed 结构化字段 | 无法精确回放 | `insufficient_evidence`；由后续 C0-C3 更强证据覆盖 | C |

结论：可证明的合同误拦集中在**同一 SELECT scope 的表别名、反引号、唯一限定名省略、SELECT 输出 alias**；真正的缺排序 / limit 与没有候选 SQL 的生成错误也都有独立反例。AST module 不能把后两类“修成通过”。

### 离线合同回放 spike

执行方式：用项目 Python、现有 `sqlglot` 和 SQLAlchemy `Base.metadata` 做一次性只读原型；未创建脚本、未接入 pipeline、未修改默认配置。原型以 MySQL dialect 解析（当前 LLM 生成目标 / MySQL 主路径），只比较同一顶层 SELECT 的 `ORDER BY` / `LIMIT`，并用真实表字段判断无前缀列是否唯一。

| 样本 | 期望 | spike 结果 | 证据 |
|---|---|---|---|
| `channels.channel_name` vs `c.channel_name` | 放行 | passed | alias → base table 绑定一致 |
| `gmv` vs `` `gmv` `` | 放行 | passed | identifier 名一致，quoted flag 不改变语义 |
| `SUM(orders_wide.actual_amount)` vs `SUM(actual_amount)` | 放行 | passed | 单表 scope 内 `actual_amount` 唯一 |
| 聚合表达式 vs同 scope SELECT alias `used_order_count` | 放行 | passed | alias 回溯到 `COUNT(DISTINCT order_coupons.order_id)` |
| ASC vs DESC | 拒绝 | failed | direction mismatch |
| 排序项顺序颠倒 | 拒绝 | failed | 第 1 项表达式 / 顺序 mismatch |
| 真缺 `ORDER BY` | 拒绝 | failed | missing order |
| 真缺 `LIMIT 10` | 拒绝 | failed | `10 != None` |
| 多表同名无前缀 `id` | 保守 | indeterminate | unqualified column not unique |
| CTE / 子查询跨 scope | 保守 | indeterminate | nested scope not supported |
| `ORDER BY 1` | 保守 | indeterminate | ordinal order not supported |

spike 证明 AST 路线能同时认出四类历史正例并守住核心反例，但也暴露两个实现要求：

1. “排序项顺序颠倒”必须在 alias 解析前先按位置比较；若计划写的是未绑定输出 alias，缺少 QueryPlan 的结构化 alias→expression 关系时应保守失败，不能猜。
2. SQL dialect 不能偷懒只写“SQLite/MySQL 都支持”。建议生成合同统一按 MySQL dialect 解析；SQLite 只负责 deterministic result oracle。若未来允许 SQLite 方言生成，再单独加 dialect 参数和双 dialect 测试。

### 输出投影政策审计

审计范围：challenge 的 12 条自动 `result_match` + formal 的 6 条自动 `result_match`。formal 6 条与 diagnostic 中 challenge question 重复，因此声明合同共 18 条，但独立问题 / 运行样本只有 12 组；不能把重复定义当成 18 次独立证据。

静态合同：18/18 的 `expected_columns` 与 reference SQL SELECT 列集合一致。当前 scorer 的真实政策是：

- 行列集合必须完全一致，额外列或缺列失败；
- `expected_column_aliases` 白名单先归一到 canonical 名再比较；
- 行按列名对齐，因此**列顺序当前不判分**；既有测试明确允许 `body.columns=[b,a]` 与 reference `[a,b]` 通过；
- 默认行顺序敏感，只有 case 显式 `order_insensitive=true` 才忽略行顺序。

M23 12 个独立自动样本的投影结果：

| 组 | exact / 白名单 alias | projection mismatch | 无最终 SQL |
|---|---:|---:|---:|
| local | 7 | 2（`db_simple_002/003` 额外列） | 3（`db_core_002`、`db_multi_001/002`） |
| Milvus | 7 | 4（`db_simple_002/003`、`db_multi_001` 额外列；`db_multi_002` 输出 `name` 不在 alias 白名单） | 1（`db_core_002`） |

其他关键发现：

- `db_simple_002` 不只是丢 `LIMIT`，还把 3 列扩大为 9 列，且排序方向从 reference ASC 变成 DESC。
- `db_multi_001` Milvus SQL 的核心两列正确，但额外输出 `channel_code`；若未来允许“非敏感额外列”，它可能通过，而 `db_simple_003` 的 7 个额外列也会一起被放宽，产品影响很大。
- `db_hard_002` 的 `add_to_pay_conversion_rate` 之所以通过，是 case 明示它等价于 `conversion_rate`；这证明 alias 必须白名单化，不能按字符串相似度猜。
- 安全列策略是独立硬门：无论选择哪种非敏感投影政策，`users.email/phone` 等敏感列永不因“允许 extras”放行。

### 建议的 AST 规则边界

1. 输入必须是已验证的单个 `QueryPlanStep` + 候选只读 SQL + 显式生成 dialect；输出 `passed/failed/indeterminate` 和结构化证据，不改写 SQL。
2. SQL Guard 先执行；合同只验证同一顶层 SELECT。多语句、CTE / 子查询跨 scope alias、ordinal order、参数化 / offset limit 在 M24 首版一律 `indeterminate` 并保守阻断。
3. 只放行四类有历史证据的等价：表别名、quoted identifier、字段在当前 scope 唯一时的限定名省略、同 scope SELECT alias 回溯。
4. 多排序项必须数量、位置、表达式和方向逐项一致；额外排序项也不静默接受。`ASC` 默认值需规范化，但不能与 DESC 混同。
5. `LIMIT` 首版只接受非负整数字面量且必须精确相等；参数、`LIMIT offset,count` / `OFFSET` 先保守失败，后续有真实需求再扩。
6. 计划若只给 `gmv/order_count` 等输出 alias，必须依赖 QueryPlan 结构化的 alias→expression / output column 绑定；没有绑定则 `indeterminate`，不能从问题文本猜指标。
7. contract pass 只表示“计划的 order/limit 被保留”。自动 case 还必须 SQL Guard 通过、SQL 执行成功并通过 result/output contract；不能把 contract pass 等同答案正确。

### 需要用户确认的输出政策

建议采用“**精确投影 + 显式 alias 白名单 + 展示顺序稳定**”：

- 自动 case：最终列集合必须与明确的 `QueryPlan.output_columns` / case `expected_columns` 完全一致，禁止额外列；alias 只接受 case/metric 明示白名单。
- 顺序：新增独立的 `body.columns` 展示顺序合同，要求与计划 / expected columns 一致；行值比较仍按列名对齐。这样既不把 JSON object key 顺序当数据语义，又能保证 API 表格 / chart 输入稳定。
- 人工 case：只报告 missing / extra / reordered / alias-unresolved，不因投影差异自动判能力硬失败。
- 敏感列：始终硬拒绝，不受 extras 政策影响。

待用户决策的替代方案是继续沿用当前“精确列集合但顺序不敏感”。不建议采用“允许任何非敏感额外列”：它会同时放过 `db_multi_001` 的一个辅助列和 `db_simple_003` 的七个无关列，使 API、图表和 eval 输出不稳定。

### M24 plan 需要修订的地方

1. v6.7 的“沿用当前精确列名 + 顺序 + 集合”应改为：“当前只保证 exact set + explicit aliases，列顺序尚未判分；是否增加展示顺序合同由用户确认”。
2. M24 基线表应补 Milvus `automated=20/27`、`manual=1/5`；只写 `21/32` 会掩盖两组自动分其实相同。
3. `contract_false_block` / `true_fidelity_failure` 目前不是 runner 原生统计字段。实现前应先定义聚合映射与 evidence level，不能把 notes 的人工标签直接冒充自动报告能力。
4. “保存完整 candidate SQL”与“长度受限但不可截断”有内在冲突。建议 trace 保存完整 SQL 的结构化字段（按既有 trace 安全边界），另设 preview 供报告展示；若必须脱敏，保存可复演的结构化 AST 摘要与稳定 hash，不能只剩 300 字 preview。
5. 首版 dialect 建议明确为 MySQL generation contract；SQLite 继续只做 result oracle。计划中“SQLite eval / MySQL audit 分别如何 parse”容易误导成同一 SQL 要双 dialect 同时判定。
6. 历史表应按“观察”而非仅按 case 定性：`db_simple_001/002` 在 M22 是字符串误拦，在 M23 是真实信息丢失，同一 case 可以随 LLM 输出落入不同类别。

### 前置关卡结论

前置关卡已完成到用户决策门；未修改 SQL 合同、pipeline、case、scorer 或默认配置。进入实现前只剩两项确认：是否采用建议的精确投影 + 展示顺序合同，以及是否按上述 6 点回写 M24 plan 后再实现。

## M24 代码实现与本地验证（2026-08-06）

### 实现快照

- 新增 `engine/nl2sql/fidelity_contract.py`，公开 seam 为 `evaluate_sql_plan_fidelity(plan_step, candidate_sql, domain_schema, dialect="mysql")`；返回 `passed / failed / indeterminate`、稳定 reason code、完整候选 SQL、SHA256、规范 SQL、计划/观察排序与 limit、输出投影和 alias 绑定证据。module 只比较，不改写 SQL。
- `generator.py` 的旧字符串 contains 合同已由该 seam 替换；`pipeline.py` 先执行完整 SQL policy 预检，再执行 fidelity，SQL Tool 执行时仍重复 Guard，保持 defense in depth。
- `QueryPlanStep.output_columns` 固化为精确 API 展示投影；新增向后兼容默认空字典字段 `output_expressions`，用于可信地声明 `order_count -> COUNT(orders.id)` 等聚合 alias。计划校验拒绝空 `output_columns`、未声明的绑定 key，以及排序使用却未绑定的非物理输出 alias，避免候选 SQL 自证语义。
- AST 首版只证明同一顶层 SELECT 中的表 alias、quoted identifier、唯一限定名省略和 SELECT alias；多语句、derived scope、歧义无前缀字段、ordinal order、非字面量/offset limit 均 `indeterminate` 并阻断。
- SQL 执行后新增 `output_contract` trace step，实际 `body.columns` 必须与计划列集合和顺序完全相同；自动 `result_match` scorer 同样先按 case 显式 alias 白名单归一，再严格比较 `expected_columns` 顺序。行值仍按列名对齐。
- triage 新增独立 `output_contract` stage；最终列、table_hit/column_recall 及投影 scorer 失败不再归入 retrieval/schema context，避免错误推断 embedding。
- 新生成 trace 保存完整结构化 QueryPlan、完整 candidate SQL + preview + hash、MySQL dialect、规范化比较结果、reason code 和 evidence level。完整 SQL 只进入既有私有 trace 边界。

### 实现中发现并修正的 plan 缺口

原计划要求“输出 alias 依赖 QueryPlan 的结构化 alias→expression 绑定”，但旧 `QueryPlanStep` 实际没有该字段。若直接用候选 SQL 的 `SELECT ... AS order_count` 解释计划里的 `ORDER BY order_count`，错误表达式也能自证通过。现已在 M24 plan 补记 `output_expressions`，并以缺绑定 `indeterminate` / 计划校验失败的测试固定边界。

### 本地验证快照

- `py_compile`：fidelity contract、planner、prompt、generator、pipeline、scorer、triage 全部通过。
- pure contract + planner focused 最终重跑：`32 passed`；覆盖四类历史正例、方向/顺序/limit/投影反例、scope 歧义、alias 自证漏洞、精确输出声明与 prompt 合同。
- pipeline + scorer + triage + 相关既有回归：`77 passed, 1 warning`；warning 是既有 Starlette/httpx 弃用提示。
- 合计本轮最终有效回归：`109 passed`。另一次组合首跑因旧 pytest 临时目录被 Windows 占用产生 19 个 setup error，并发现 1 个测试夹具把 `COUNT(*)` 错绑定成 `COUNT(orders.id)`；夹具修正后改用独立 `--basetemp=.agent_work/temp/m24-pytest-20260806-b`，上述 77 项全绿。未删除被占用目录。
- `git diff --check` 通过；环境未安装 ruff（`No module named ruff`），未临时下载依赖。
- 按用户边界，未运行任何完整 formal / challenge / diagnostic，也未运行真实 LLM 或 Milvus；后续能力数字必须由用户手工评测产生，不能用本地单测替代。

## M24 真实评测尝试（2026-08-06，外部账户阻塞）

- focused 回归门禁由当前会话复跑通过：`70 passed, 1 warning`；warning 仍为既有 Starlette/httpx 弃用提示。
- 第一次 Local L1 diagnostic 运行 15 分钟后超时，只落下 25 条 trace，没有完整 report/triage，因此不计入样本。
- 使用更长超时重跑完整 Local L1，32 条 trace/report/triage 均生成，但结果不能作为能力样本：除 4 条预期安全/计划阻断外，大多数 case 的 `QueryPlan` 请求都收到 DashScope/Qwen HTTP `400 Arrearage`，错误信息为“Access denied, please make sure your account is in good standing”，即账户欠费/状态不可用。
- 该次报告表面为 `7/32`，其中安全拒绝题通过；它反映的是外部模型账户不可用，不是 M24 合同、Local 检索或 embedding 能力。未启动 Milvus M1–M3，避免重复制造同一外部失败。
- 产物：`eval/reports/m24-ab-l1r-local-weighted-diagnostic-report.md`、对应 triage，以及 `eval/traces/m24-ab-l1r-local-weighted-diagnostic-traces.jsonl`；首次超时的部分 trace 另保留为 `m24-ab-l1-local-weighted-diagnostic-traces.jsonl`。
- 后续动作：账户恢复且 Qwen API health check 成功后，再按 `L1 → M1 → L2 → M2 → L3 → M3` 交错执行；在此之前不得使用 `7/32`、`20/27` 等数字解释 M24 或 embedding。

## M24 受控 A/B 完成快照（2026-08-06）

- Qwen 账户恢复后 health check 返回 `{"status":"ok"}`，随后完成 6 次有效 diagnostic；之前的 `Arrearage` 失败运行仍保留但不计入样本。
- 交错结果：Local `24/32, 24/32, 25/32`，自动能力 `21/27, 21/27, 22/27`；Milvus/Qwen embedding `25/32, 25/32, 25/32`，自动能力稳定 `22/27`。两组 manual/diagnostic 均为 `3/5`。
- Milvus 使用唯一 collection `datapilot_schema_docs_m24_qwen_weighted_20260806_194900`；M1/M2/M3 均 `milvus_final_row_count=195`，schema hash 与 1024 维配置一致，未发现重复灌入或 corpus mismatch。
- 逐 case 矩阵已固化到 `eval/reports/m24-ab-execution-manifest.md`。稳定通过的历史 SQL alias/限定名合同样本没有出现新的 `semantic_false_block`；M1 的 `db_core_002` 明确暴露了计划 `orders.id` 与候选 `order_items.id` 的真实表达式保真错误。
- `db_simple_002/003` 六次均捕获额外投影；`db_simple_001` 六次均结果首行错误；`db_core_002`、`db_multi_002`、`db_join_003`、`db_hard_001` 等稳定失败仍主要是生成/计划、结果语义或人工语义问题。六次 135 个可执行 SQL trace 的 pipeline `output_contract` span 均成功，说明部分投影问题发生在 QueryPlan 已声明过宽之后的 case scorer 合同。
- 结论边界：Milvus 自动分在这三次样本中稳定高于 Local 一分，但这不是 embedding 因果证明；当前更可靠的 M24 结论是 AST 合同误拦已被压住，剩余主要工作转为 QueryPlan 输出投影、真实生成保真和少数结果语义失败。默认 backend/embedding 不因该 A/B 自动切换。

## M24 收尾素材（finish-module，2026-08-06）

### 模块名称与改动文件清单

模块：**M24 SQL Plan Contract Semantic Equivalence / Plan-to-SQL Fidelity**。

- 深 module 与 pipeline：`engine/nl2sql/fidelity_contract.py`、`generator.py`、`pipeline.py`、`planner.py`、`prompt.py`。
- eval 与归因：`eval/scorers/rule_scorers.py`、`eval/triage.py`。
- 测试：`tests/test_m24_sql_plan_fidelity.py`、`test_phase3a_planner.py`、`test_phase3a_pipeline.py`、`test_m17_scorers.py`、`test_m19_failure_triage.py`、`test_m22_eval_contract.py`。
- 计划与状态文档：`docs/phase3b-langfuse-plan-v6.md`、本 notes、`docs/state/AI_CONTEXT.md`、`AI_CONTEXT_CHANGELOG.md`、`eval-baselines.md`、`schema-retrieval-milvus-embedding.md`。
- 评测产物：`eval/reports/m24-ab-execution-manifest.md` 与 L1/L2/L3、M1/M2/M3 六组有效 report/triage；`m24-ab-l1r-*` 是账户欠费失败证据，只留作外部故障记录，不计入能力样本。trace 按项目规则保存在 `eval/traces/`。

### 关键决策与取舍

1. **字符串包含 vs AST 等价**：字符串方案简单但已经误拦表 alias、反引号、唯一限定名省略和 SELECT alias；采用独立 SQLGlot AST module。风险是 AST scope 扩张成 SQL 优化器，因此首版只证明有历史证据的同一顶层 SELECT 等价，其他情况统一 `indeterminate` 并阻断。
2. **候选 SQL 自证 vs QueryPlan 显式绑定**：若用候选 SQL 的 alias 表达式反解计划，错误 SQL 也能自证。最终新增 `output_expressions`，由 QueryPlan 明示聚合 alias 的可信表达式；缺绑定不猜。
3. **投影政策**：备选为“精确集合但顺序不敏感”或“允许非敏感 extra”。用户确认采用**精确集合 + 显式 alias 白名单 + 展示顺序稳定**。代价是计划必须更准确，收益是 API 表格、chart 和 eval 的输出合同一致，辅助列不会静默泄露到用户结果。
4. **安全与语义顺序**：SQL policy 预检先于 fidelity；SQL Tool 执行时再做一次 Guard。合同 pass 只说明 SQL 忠实于计划，不代表答案语义正确。
5. **方言与 oracle**：MySQL 是生成/解析合同；SQLite 只做确定性结果 oracle，不要求候选 SQL 同时满足两种 dialect。
6. **检索默认值**：三次 Milvus 自动分均比对应 Local 高约 1 分，但样本仍混有 LLM 波动，不能把单次或小样本总分当作 embedding 因果证据；保持 `inmemory + deterministic + weighted` 默认不变。

### 注释扫描小结

- 按文件/类/函数覆盖、设计深度、复杂流程可读性、注释形式四轮扫描了 M24 的 7 个生产代码文件；新增/修改的核心接口均有中文 docstring，复杂路径有步骤分隔，关键安全与保守边界使用 `★`。
- 收尾补强三处：公开 fidelity interface 标记为模块主角；解释 projection 为什么用 tuple/Counter 而不是 set；解释物理排序列与聚合 alias 的绑定差别，以及 scorer alias 白名单不放宽集合/顺序。
- 测试函数命名已能直接表达场景，不重复添加逐函数注释；简单 `__init__` 等样板方法沿用项目豁免，不堆砌无信息量注释。

### 最终验证快照

- M24 focused：`70 passed, 1 warning in 134.77s`。
- 全仓 pytest：`176 passed, 1 warning in 462.55s`。
- warning 均为既有 `StarletteDeprecationWarning`（Starlette `TestClient` 使用 httpx 的旧兼容入口），与 M24 无关。
- 全仓首轮曾因 300 秒工具上限在约 58% 处终止，终止前无失败；随后换独立 `--basetemp=.agent_work/temp/m24-finish-full-20260806d` 完整重跑并全绿。另有两次 1 秒启动探针被工具主动终止，不计作测试结果。
- 未运行 Alembic / seed（M24 不改 ORM 或数据）；收尾阶段也未重复运行真实 LLM formal/challenge/diagnostic。

### 参考资料

- 项目事实源：`docs/state/AI_CONTEXT.md`、`runbook.md`、`eval-baselines.md`、`AI_CONTEXT_CHANGELOG.md`，以及 M22/M23 notes 与历史 trace/report。
- 设计依据：`docs/phase3b-langfuse-plan-v6.md` M24/v6.7；实现复用项目既有 SQLGlot、SchemaGraph、SQL Guard、trace 与 deterministic SQLite oracle，没有复制外部项目代码。
- 方法论：实现阶段使用 deep-module seam 思路，把复杂等价判断收进单一纯函数接口；没有为未来未出现的 CTE/多 scope 需求预建通用 SQL 优化器。

### 遗留与后续

- M24 已完成开发、真实受控诊断和文档收尾，但尚未执行 `accept-module`，状态应为“未验收”。
- 当前稳定问题已从字符串误拦转向 QueryPlan 过宽投影、生成表达式不忠实和结果语义错误；后续应按逐 case 证据修 QueryPlan/prompt，不扩大 AST 放行边界。
- CTE/derived scope、ordinal ORDER BY、参数化或 offset LIMIT 继续保守阻断；只有真实业务样本出现并补齐正反例后才扩展。
- Milvus 是否切默认必须另做能隔离 LLM 波动的 retrieval/embedding 证据，不使用本轮一分差直接决策。
