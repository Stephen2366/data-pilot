# M22 Eval Contract / Semantic Output Stabilization Notes

## 开发中素材

### 已确认的长期口径（2026-08-04）

- 用户确认先修正 case / scorer 契约，再评估 pipeline；M21 `21/32` 保留为历史快照，M22 后的分数不得直接宣传为模型提分。
- 用户确认商品退款率以 `refunds.order_item_id -> order_items.product_id` 的订单明细归因为唯一默认口径；`orders.product_id` 只保留为兼容关系，不再作为本题 reference。
- 用户确认“一级类目”使用 `products.category_id -> product_categories` 规范类目树；不再用 `products.category` 兼容字段作为默认事实。
- 用户确认 manual / diagnostic 分开展示：报告新增自动能力分、人工审查分和 case/scorer 契约重分类清单。

### 已实施的关键设计

- Context Contract 从同请求 JSONL trace 的 `schema_context.metadata.tables/fields` 读取 SchemaGraph 证据，不再拿最终 `body.columns` 充当内部上下文；API 响应契约不新增字段。
- `plan_validation_blocked` 进入专属 scorer 优先路径，结构化语义拒绝不会被空输出列或 allow 安全状态抢先遮蔽。
- 新增窄范围 `semantic_validation`：仅识别当前 Schema 明确没有 supplier 字段、知识库文档到订单无归因关系、以及显式多步对比三类已证实的不支持需求；统一返回 trace 可见的 `blocked_via=semantic_request_validation`，不把它们伪装成 LLM generation error。
- SQL generation 增加 QueryPlan 已显式给出的 `order_by` / `limit` 合同检查；不分析或改写任意 SQL，避免泛化正则规则误拦合法语句。
- 新增 `coupon_order_count` 派生指标会让 Schema document corpus 从 193 增至 194；当前 hash 为 `58534cb68ec4264d4b75579d9f5a6f08bb1908475d89bbab63941e558cb92a6f`。这是用户确认“优惠券使用订单数”单独建模的直接结果，不切换 embedding / Milvus / fusion，但后续 retrieval 对照必须记录新 hash，不能与 M21 的 193-doc hash 混用。

### 中途验证快照

- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q tests\test_m22_eval_contract.py tests\test_phase3a_eval.py tests\test_phase3a_planner.py --basetemp=.agent_work\temp\m22-contract-pytest` → `42 passed, 1 warning`。warning 为既有 Starlette/httpx `TestClient` deprecation，不影响 M22。
- 首次扩大 focused 集合（含 pipeline/database tests）为 `50 passed, 2 failed, 1 warning`；失败是新测试误把兼容汇总 reason 期待为细节 reason（实际 `summarize_score_details()` 成功统一为 `ok`），已修正测试断言，非业务代码失败。
- 首次全量 pytest：`142 passed, 2 skipped, 1 failed, 1 warning`；失败为 `tests/test_m20_schema_index_hygiene.py` 固定期待 193 docs，但 M22 新 metric 实际构建 194 docs，已更新该基线断言后待复跑。其余 142 条通过；warning 为既有 Starlette/httpx deprecation。
- 全量 pytest 复跑：`143 passed, 2 skipped, 1 warning`，耗时 `438.67s`；唯一 warning 为既有 Starlette/httpx `TestClient` deprecation。
- 初次默认 DeepSeek + local deterministic + weighted、`LANGFUSE_ENABLED=false` 的 32 条 diagnostic 为 `26/32`；报告三视图的插入位置随后被发现破坏了 Score Summary Markdown 表格，因此修复布局并添加回归测试后，最终重跑快照为 `25/32`（automated `22/27`，manual `3/5`）。report 为 `eval/reports/m22-default-diagnostic-report.md`，triage 为 `eval/reports/m22-default-diagnostic-triage.json`，trace 为 `eval/traces/m22-default-diagnostic-traces.jsonl`。这是 M22 改动后的口径快照，不能同 M21 `21/32` 直接解释为模型提分。`db_plan_002/003/004` 均结构化通过；`db_prompt_002` 实际 SQL 已采用 SCD overlap 条件。`db_core_004` 仍未在 QueryPlan 中规划排序，下一步补充该题的 QueryPlan prompt 约束；`db_simple_001` 显示 SQL generation 丢了计划中的 products.id ASC，因此被 SQL plan contract 拦截，属于 M22 输出合同发现的真实生成缺口，不扩大到通用列表排序优化。
- `db_core_004` 单 case 默认链路复测（补充排序 QueryPlan 约束后）：`result_match_ok`，SQL 已生成 `ORDER BY order_count DESC, channels.channel_name ASC`；trace 为 `.codex/temp_work/m22-db-core-004-trace.jsonl`。这是 SQLite deterministic oracle 下的回归证据；仍不把一次实时 LLM 成功外推为整个 32 条快照都已刷新。

## 模块名称与改动文件清单

- 模块：M22 Eval Contract / Semantic Output Stabilization。
- 代码与测试：`engine/nl2sql/semantic_validation.py`、`engine/nl2sql/pipeline.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/prompt.py`、`eval/scorers/rule_scorers.py`、`eval/run_eval.py`、`tests/test_m22_eval_contract.py`、`tests/test_m20_schema_index_hygiene.py`。
- 事实源与用例：`domain_pack/metrics.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`eval/cases/phase3a-regression.yaml`。
- 产物：`eval/reports/m22-default-diagnostic-report.md`、`eval/reports/m22-default-diagnostic-triage.json`、`eval/traces/m22-default-diagnostic-traces.jsonl`（默认 gitignore）、`.codex/temp_work/m22-db-core-004-trace.jsonl`（一次性复测 trace）。`docs/dev-log.md` 和 `docs/state/AI_CONTEXT_CHANGELOG.md` 的已有用户改动不属于 M22，收工时保留并只追加模块档案。

## 阶段 1 注释小结

- 覆盖扫描：M22 新增 `semantic_validation` 类/函数、SQL plan contract、Context / Plan scorer、trace 读取与报告三视图，以及 10 条回归测试均具有中文模块或函数 docstring；0 处缺失。
- 质量扫描：已明确“trace 过程证据不进入 API 响应”“语义拒绝不是 SQL Guard / LLM transport error”“只检查 QueryPlan 已声明的排序 / limit，不能泛化解析 SQL”三项设计边界。
- 内部可读性：`pipeline.py` 为语义预检和只读 SQL 合同顺序补充步骤注释；`rule_scorers.py` 标注专属 contract 必须在输出列检查前执行；`run_eval.py` 标注 scorer 私有 trace 字段不改变 API 契约。
- 形式扫描：新增注释以中文为主，关键边界使用 ★，长流程采用既有步骤分隔线；未发现过时注释或需要额外对齐的格式问题。

## 阶段 2 最终验证快照

- M22 contract / planner focused：`pytest -q tests\test_m22_eval_contract.py tests\test_phase3a_eval.py tests\test_phase3a_planner.py --basetemp=.agent_work\temp\m22-contract-pytest` → `42 passed, 1 warning`。
- M22 pipeline / planner focused：`pytest -q tests\test_m22_eval_contract.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\m22-pipeline-contract-pytest` → `28 passed, 1 warning`。
- 全量 pytest（最终）：`pytest -q --basetemp=.agent_work\temp\m22-full-pytest-report-final` → `144 passed, 2 skipped, 1 warning`，耗时 `407.64s`。
- 默认 diagnostic（报告布局修复后重跑）：32 条 `new_text2sql`、DeepSeek 默认链路、local deterministic、weighted、SQLite deterministic oracle、LangFuse disabled → `25/32`（automated `22/27`；manual `3/5`）；详见上述报告与 triage。M21 `21/32` 是历史快照，两个总分不作模型能力的直接比较。
- 额外 SQL 行为证据：`db_prompt_002` trace 的两次 SQL 均使用 `valid_from < 2026-07-01 AND (valid_to IS NULL OR valid_to > 2026-06-01)` overlap；`db_core_004` 单 case `result_match_ok`。
- warning：仅既有 Starlette/httpx `TestClient` deprecation；Windows LF/CRLF 提示不属于 whitespace error，`git diff --check` 无 whitespace error。

## 参考资料

- 无外部资料。实现依据为 M22 计划、`m22-review-notes.md` 的只读审计、项目既有 trace/scorer/pipeline 代码；未引入 reranker、AST 泛化改写或新的数据库机制。

## 遗留 / 后续

- `db_simple_001` 真实 LLM 仍可能在 SQL generation 丢失已规划的 `products.id ASC`，现在会被 `sql_plan_contract_failed` 结构化暴露；这不是 M22 的核心修复目标，不在本模块扩展成所有列表题的排序策略。
- 由于 `coupon_order_count` 新增 metric document，后续 retrieval benchmark 要使用 194-doc corpus 与新 hash；M21 193-doc A/B 只保留历史事实，不可跨 corpus 直接对比。
- 用户确认将 Qwen / Milvus / RRF 的新口径对照作为 M22 实验扩展；首轮仅待确认执行一次，后续复测和任何默认切换都不自动进行。

## 待确认实验扩展：M22 新口径下的 Qwen / Milvus / RRF 对照

> 用户确认将本组实验归入 M22 范围。以下是执行前方案，不代表已运行结果；默认配置不会因任何单次结果改变。

### 目标与固定条件

- 目标：在 M22 已修正 case/scorer、194-doc corpus 和 QueryPlan→SQL 合同后，重新检查 Qwen `qwen3.7-plus` 主模型、clean Milvus + Qwen embedding、RRF 是否存在可解释的候选收益。
- 全部端到端组固定：32 条 diagnostic、M22 case/scorer、`new_text2sql`、SQLite deterministic oracle、LangFuse disabled、同一 seed、194-doc corpus（hash `58534cb68ec4264d4b75579d9f5a6f08bb1908475d89bbab63941e558cb92a6f`）。
- 主读数：自动能力 27 条的 pass、失败 subtype 与逐 case trace；manual/diagnostic 5 条单列观察，不混入自动硬分。总分不单独作为默认切换依据。
- Milvus 组使用 run-scoped clean collection 与 Qwen `qwen3.7-text-embedding`（1024 维）；每次记录 collection、row_count、embedding 配置和 corpus hash，避免复现 M20 的索引污染。

### 首轮：仅运行未测候选组一次（待用户确认后执行）

| 组 | 主模型 | 检索 | Fusion | 唯一新增比较目的 |
|---|---|---|---|---|
| C0（已完成） | DeepSeek `deepseek-v4-flash` | inmemory + deterministic | weighted | M22-E02 已有默认快照：`25/32`，自动 `22/27`、人工/诊断 `3/5` |
| C1 | Qwen `qwen3.7-plus` | inmemory + deterministic | weighted | C1 vs C0：主模型变化 |
| C2 | Qwen `qwen3.7-plus` | clean Milvus + Qwen embedding | weighted | C2 vs C1：检索 backend / embedding 变化 |
| C3 | Qwen `qwen3.7-plus` | clean Milvus + Qwen embedding | RRF | C3 vs C2：fusion 变化 |

- 首轮只执行 C1/C2/C3，不重复 C0；同时运行 retrieval-only 三组：local deterministic + weighted、Milvus + Qwen embedding + weighted、Milvus + Qwen embedding + RRF；固定 194-doc/hash、benchmark case、`top_k=12`。它只评价召回，不能替代端到端结论。
- C0 与 C1/C2/C3 并非同一实验窗口，首轮只能用于筛选和定位，不宣称严格的模型 / 检索因果收益；输出报告、triage、trace 与逐 case 对比材料。

### 复测门

- 首轮完成后暂停，向用户报告 C1/C2/C3 与三组 retrieval-only 的原始结果、耗时、失败结构与 trace 证据。
- 只有在用户再次确认后，才在同一实验窗口对 C0/C1/C2/C3 执行第 2、3 次，并补跑 C0 的第 1 次；复测时不改模型、case/scorer、corpus/hash、oracle、`top_k`、context budget 或 LangFuse 开关。
- 这三次同窗口 run 完整后，才以自动能力 27 条的中位数、范围、每 case 通过次数和失败 subtype 判断；manual/diagnostic 保持单列。若候选没有稳定证据，不切默认。

### 边界与风险

- C0/C1/C2/C3 的完整复测是逐层比较设计，不是完整 `2×2×2` 因子实验；它不能证明 DeepSeek 下 Milvus/RRF 的交互效应。只有首轮出现候选收益且用户需要分析交互时，才单独讨论是否补完整因子实验。
- 不在本轮盲跑 RRF 参数、reranker、top_k、context budget、schema docs bundle 或默认切换；这些会引入第二个变量或改变长期评测口径，需另行确认。
- 当前已知 `sql_plan_contract_failed` / `llm_generation_error` 先按生成链路和实时模型波动解释，不预设为 retrieval 缺陷。

### M22 默认 diagnostic 耗时事实（2026-08-04）

- 从 `eval/traces/m22-default-diagnostic-traces.jsonl` 的 32 条实际 trace 汇总：总 wall time `512.0s`（约 8.5 分钟），单 case p50 `13.19s`、p95 `45.32s`。
- `query_plan` 共 `355.3s`（69.4%，p50 `11.04s`、p95 `40.09s`），`sql_generation` 共 `155.3s`（30.3%，p50 `4.55s`、p95 `18.81s`）；Schema Retrieval、schema context、SQLite SQL execution、SQL Guard、评分和报告合计不足 0.3%。
- 结论：当前耗时几乎完全来自一次请求通常需要两次远程 LLM 调用，且 case 在 eval runner 中串行执行；不能通过优化 Milvus、SQLite 或 rule scorer 获得实质缩短。首轮实验采用“一次一组”，待用户根据结果确认后再做第 2、3 次，避免在稳定性尚未确认前放大远程调用成本。

### 复审修复素材（2026-08-04）

- 用户确认 `db_simple_002` 的“已支付订单”按“成交订单”解释：题面改为“2026 年 6 月成交订单”，reference SQL 显式排除 `cancelled / canceled`。
- Context Contract 补齐 `must_include_join_keys` 硬检查，以及 `max_tables` / `must_not_include_tables` 的 warn 记录；warn 仍不改变 pass/fail，避免把诊断噪音误作硬门失败。
- `plan_validation_blocked` 改为将 `accept_paths[].via` 与 issue tag 成对核验；`db_plan_002/003/004` 统一声明 M22 的 `semantic_request_validation` 来源。
- SQL Plan Contract 暂不升级 AST：失败 trace 记录候选 SQL preview、计划排序/limit、观察到的 ORDER BY/LIMIT 和当前字符串比较规则；先根据真实证据判断是否存在等价误拦。
- 聚焦测试首次 `13 passed, 1 failed`：失败是测试错误取到 `rule:safety_compliance` 而非随后产生的 `rule:schema_context`，不涉及业务实现；已改为按 scorer 名称取 detail 后复跑。
- 复跑验证：M22 专属 `14 passed, 1 warning`；相关 eval / planner / pipeline / database / schema-index 回归 `64 passed, 1 warning`；全量 `147 passed, 2 skipped, 1 warning`。warning 均为既有 Starlette/httpx `TestClient` deprecation。
- 本次复审修复后未重跑真实 LLM default diagnostic：`25/32` 仍是修复前的 C0 快照，只用于首轮候选筛选参照，不被标注为本次代码修复后的新结果；Qwen / Milvus / RRF 实验继续待用户确认。
- C0-refresh 已获确认并启动一次，但在评测初始化阶段因现有 `milvus-standalone` / `milvus-minio` 容器停止而失败；进一步确认 Windows 当前排除了宿主机端口 `9001`、`9091`，导致原端口映射无法恢复。该次没有进入 LLM case，也不计入实验结果；改宿主机端口或重建容器属于基础设施变更，待单独确认。
- 电脑重启后 Milvus 三个容器均恢复 healthy；C0-refresh 首次真正连接时发现旧 collection 仍是 M21 的 193-doc，而 M22 当前 corpus 为 194-doc，索引卫生检查按设计拒绝复用。后续使用唯一的 M22 collection 重建，保留旧 collection 不动。
- C0-refresh 最终完成：DeepSeek `deepseek-v4-flash` + Milvus + DashScope Qwen embedding + weighted，194 rows / 当前 corpus hash，32 条通过 `24/32`，自动能力 `20/27`、manual/diagnostic `4/5`，耗时约 536 秒。报告：`eval/reports/m22-c0-refresh-report.md`，trace：`eval/traces/m22-c0-refresh-traces.jsonl`，triage：`eval/reports/m22-c0-refresh-triage.json`。8 个未通过/需审查项中，3 个为 `sql_plan_contract_failed`（`db_simple_001/002`、`db_core_004`），其余主要为 schema context / retrieval 和人工审查；不把它与修复前 `25/32` 直接解释为分数下降，需按失败结构对照。
- M22 首轮端到端候选已各跑 1 次：C1 Qwen `qwen3.7-plus` + inmemory/deterministic + weighted 为 `27/32`；C2 同主模型 + clean Milvus/Qwen embedding + weighted 为 `25/32`；C3 同 C2 但 RRF 为 `24/32`。三者均固定当前 194-doc corpus/scorer，结果只作候选筛选，不宣称稳定收益或默认切换。对应报告/trace/triage 以 `m22-c1-qwen-local-weighted-*`、`m22-c2-qwen-milvus-weighted-*`、`m22-c3-qwen-milvus-rrf-*` 命名。
- 首轮 retrieval-only 也完成：local deterministic + weighted `overall=0.738`；Milvus/Qwen embedding + weighted `0.738`（vector `0.929`）；Milvus/Qwen embedding + RRF `0.929`（table `0.925`、column `0.925`、metric `0.900`、relation `0.967`）。这再次说明 RRF / embedding 能改善隔离召回，但端到端 C3 未超过 C2；不据此切换默认 fusion。
- 在开始第 2/3 次重复前补做异常彩蛋审计：eval 每次在同一份确定性 SQLite seed 上运行，`result_match` 只比较 case `expected_sql` 的结果；取消状态 / `paid_at IS NULL` 已在 GMV、净收入、商品 GMV、渠道 GMV 等成交类 reference 中显式处理；优惠券桥接用 `COUNT(DISTINCT order_id)`，SCD 价格用 `valid_to IS NULL OR valid_to > 窗口开始`。但外部单号重复/命名空间、负数退款、金额头明细不一致没有独立 case；`db_core_002` 的商品退款率 reference 只接 `order_item_id`，会排除 `order_item_id IS NULL` 的整单退款，且未显式排除取消状态。该边界会影响是否直接复测，待用户确认是否保持当前合同或先扩展 case 口径。
- 用户确认暂不处理异常彩蛋口径，继续当前 M22 case/scorer 的 C0-C3 第 2、3 次重复；重复只用于同一现有合同下的稳定性统计，不宣称异常数据鲁棒性。

### C0-C3 三次重复结果（2026-08-05）

- C0（DeepSeek + Milvus/Qwen embedding + weighted）：首轮 `24/32`，第2次 `24/32`，第3次 `25/32`；范围 `24–25`。
- C1（Qwen-plus + inmemory/deterministic + weighted）：首轮 `27/32`，第2次 `28/32`，第3次 `28/32`；范围 `27–28`。
- C2（Qwen-plus + Milvus/Qwen embedding + weighted）：首轮 `25/32`，第2次有效复测 `27/32`，第3次 `25/32`；范围 `25–27`。第2次首次启动因工具 120 秒上限中断，未计入；有效结果写入 `m22-c2-qwen-milvus-weighted-r2b-*`。
- C3（Qwen-plus + Milvus/Qwen embedding + RRF）：首轮 `24/32`，第2次 `26/32`，第3次 `27/32`；范围 `24–27`。
- 重复结论：C1 在三次中均为最高或并列最高，C2/C3 没有稳定超过 C1 的证据；C3 的 retrieval-only 优势未转化为端到端稳定优势。当前不切换默认模型、Milvus 或 RRF。
- 运行约束：所有 Milvus 复测使用独立 collection，194 rows 和同一 schema hash；LangFuse disabled、SQLite deterministic oracle、32 条 diagnostic、`new_text2sql` 不变。上述结果仍只代表当前 case/scorer 合同，不代表对数据库异常彩蛋的鲁棒性。

### Qwen 3.8 追加测试（2026-08-05）

- 按用户要求执行 `qwen3.8-max + inmemory/deterministic + weighted`，其余保持 32 条 diagnostic、`new_text2sql`、SQLite deterministic oracle、LangFuse disabled 和当前 M22 scorer/case。
- 结果：`22/32`。模型调用可用，因此没有继续执行备用的 `qwen3.7-max`；该快照仅作候选证据，不改变默认模型。
- 报告：`eval/reports/m22-qwen38-local-weighted-report.md`；trace：`eval/traces/m22-qwen38-local-weighted-traces.jsonl`；triage：`eval/reports/m22-qwen38-local-weighted-triage.json`。

### Qwen 3.7 Max 追加测试（2026-08-05）

- 按用户后续要求执行 `qwen3.7-max + inmemory/deterministic + weighted`，其余条件与 Qwen 3.8 及当前 M22 diagnostic 保持一致。
- 结果：`26/32`。这是单次追加对照，不纳入 C0-C3 三次重复稳定性矩阵，也不改变默认模型。
- 报告：`eval/reports/m22-qwen37max-local-weighted-report.md`；trace：`eval/traces/m22-qwen37max-local-weighted-traces.jsonl`；triage：`eval/reports/m22-qwen37max-local-weighted-triage.json`。

### C1 本地 vs C2 embedding 逐 case 初步审计（2026-08-05）

- 三次配对中，C1→C2 的通过数为 `27→25`、`28→27`、`28→25`。C2 并非每题都更差：首轮 `db_core_002` 反而由 C1 失败、C2 通过；净差主要来自少数下游生成/合同失败。
- C2 相对 C1 的额外失败：首轮 `db_core_004`、`db_plan_001`、`db_prompt_002`；第2次 `db_join_003`；第3次 `db_core_004`、`db_schema_003`、`db_trace_002`。
- 已见证据：`db_core_004` 的 C2 trace 上下文仍含相同 7 张表/101 个字段，但候选 SQL 使用 `c.channel_name`，QueryPlan 写的是 `channels.channel_name ASC`，被当前字符串比较规则误拦；`db_plan_001` 的 `` `gmv` DESC``、`db_prompt_002` 的 `p.product_name`、`db_trace_002` 的 `used_order_count DESC` 也属于计划表达与 SQL 别名/引用形式差异。`db_schema_003` 出现 `GMV` 与 expected `gmv` 的大小写列名差异；`db_join_003` 一次生成 SQL 未使用 expected 的 `products` 表。
- 初步判断：当前 1–3 分差不能直接归因于 embedding 召回下降；Milvus weighted retrieval-only 与本地 weighted 总体同为 `0.738`，且多项失败发生在 schema context 已包含目标表之后。更可能是远程 LLM 生成波动、文档排序改变提示输入，以及 SQL Plan/Output Contract 对别名和大小写的敏感共同作用。后续先按 trace 分阶段隔离，再决定是否需要合同规范化或检索策略改动。
