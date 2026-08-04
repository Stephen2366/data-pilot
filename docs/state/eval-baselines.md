# DataPilot Eval Baselines

> 本文是 DataPilot 的长期评测账本，优先回答“当前应据什么决策、哪些结果可直接比较”。完整报告和历史叙事分别保留在 `eval/reports/` 与 `docs/state/AI_CONTEXT_CHANGELOG.md`。

更新时间：2026-08-04

## 1. 当前决策摘要

| 项目 | 当前结论 | 证据 |
|---|---|---|
| 默认主模型 | DeepSeek `deepseek-v4-flash`；不因单轮 A/B 自动切换。 | `M19-E01`、`M19-E02` |
| 默认检索 | `inmemory + deterministic + weighted`；Milvus、Qwen embedding、RRF 均仅作显式实验路径。 | `M20-E01`、`M21-E02`、`M21-E03` |
| 当前优化方向 | M22 已完成契约拆分与窄 QueryPlan→SQL 合同；M23 需在 194-doc、新 case/scorer 口径上重新验证 retrieval 假设。 | `M22-E01`、`M22-E02` |
| 已收口的假设 | Qwen embedding 有向量召回信号，但尚无端到端可归因提分；RRF 也未带来端到端收益。 | `M21-E01`、`M21-E02`、`M21-E03` |
| 不可作决策的证据 | 旧固定 Milvus collection 的重复灌入污染结果只保留作历史对照。 | `M20-E01` |

运行命令、环境变量和执行纪律以 `docs/state/runbook.md` 为准；Schema Retrieval 的 collection、hash、维度与排查菜单以 `docs/state/schema-retrieval-milvus-embedding.md` 为准。

## 2. 评测口径与可比性规则

### 测试集定位

| 集合 | 用途 | 读数原则 |
|---|---|---|
| `formal` | 主线回归；验证基础能力是否稳定。 | 样本少，适合作回归信号。 |
| `challenge` | 复杂 join、指标、业务口径与安全边界。 | 适合看困难题的失败类别。 |
| `diagnostic` | 定位失败结构和下一步修复层。 | 不以追满分为目标。 |
| retrieval-only benchmark | 测量召回链路本身。 | 不可直接推出端到端 Text2SQL 收益。 |

### 结果标签

| 标签 | 含义 | 是否可作长期决策 |
|---|---|---|
| 事实锚点 | 链路可信、口径明确的关键数据点。 | 可以，但仍需考虑 LLM 波动。 |
| 受控 A/B | 固定其他条件，只改变声明的唯一变量。 | 可以回答该变量的局部问题。 |
| 诊断快照 | 用于观察失败簇或验证工具链。 | 不单独等同能力升降。 |
| 补充/负向证据 | 支撑风险判断，但不替代事实锚点。 | 仅与其他证据合并解读。 |
| 历史污染对照 | 数据链路已知不可信或口径已变化。 | 不可以。 |

### 比较纪律

- 只有 `可比对象` 指向彼此、且固定条件一致的行，才可对总分或失败分布作因果归因。
- formal / challenge / diagnostic 若来自不同的真实 LLM run，即使 case 集有包含关系，也不能把它们当作同一份结果的切片。严格比较应从一次 superset run 切子集统计。
- `triage summary failed` 可能高于由命令行 `passed` 推算的失败数：`review_required / manual_review` 会进入待处理清单。
- 总分不是唯一信号。`schema_context` 下降但 `result_match` 上升时，不能简单判为改进。

## 3. 权威基线与实验矩阵

> “固定条件”只列影响可比性的关键项；完整配置和原始数字见“报告索引”。`—` 表示该实验未运行该集合，不表示失败。

| ID | 日期 | 证据类型 | 目的 | 固定条件 / 唯一变量 | 结果 | 可比对象 | 决策 |
|---|---|---|---|---|---|---|---|
| `M13-E01` | 07-26 | 事实锚点 | Phase 3A 稳定回归快照 | DeepSeek + local retrieval | formal `10/10`；challenge `14/16`；diagnostic `23/32` | — | 上一轮稳定基线。 |
| `M14-E01` | 07-27 | 诊断快照 | 更严格口径下复测默认链路 | DeepSeek + local retrieval | formal `8/10`；challenge `12/16`；diagnostic `24/32` | `M13-E01` 不可直接比较 | 口径收紧，不能据此判退化。 |
| `M14-E02` | 07-27 | 补充证据 | 模型候选初筛 | Qwen `qwen3.7-plus` | formal `9/10`；challenge `13/16`；diagnostic `21/32` | 同轮 DeepSeek 快照 | 保留候选，不切默认。 |
| `M14-E03` | 07-27 | 补充证据 | 模型候选初筛 | Qwen `qwen3.7-max` | diagnostic `22/32` | 同轮快照 | 保留候选，不切默认。 |
| `M19-E01` | 08-02 | 诊断快照 | 验证 triage 闭环 | DeepSeek flash | formal `7/10`；challenge `9/16`；diagnostic `19/32` | `M19-E02` 仅作同轮模型参考 | 不单独判定默认能力下降。 |
| `M19-E02` | 08-02 | 补充证据 | 主模型候选对照 | Qwen `qwen3.7-max` | formal `8/10`；challenge `12/16`；diagnostic `22/32` | `M19-E01` | 生成类失败较少，但 schema 问题未解；不切默认。 |
| `M20-E01` | 08-02 | 事实锚点 | 修复索引卫生并重测 | DeepSeek + clean Milvus/Qwen embedding；193 docs、run-scoped | diagnostic `17/32` | 旧污染结果不可比 | 证明 clean 链路可信，不证明 embedding 无效。 |
| `M20-E02` | 08-02 | 补充证据 | clean 链路模型对照 | `M20-E01` 同检索链路，唯一变量为 Qwen `qwen3.7-max` | diagnostic `21/32` | `M20-E01` | 同链路高于 DeepSeek，但单次 run 不切默认。 |
| `M21-E01` | 08-03 | 受控 A/B | 检查 embedding 与 fusion 的离线召回 | 10 题、`top_k=12`；变量为 backend/embedding/fusion | vector `0.787→0.929`；weighted merged 均 `0.738`；RRF `0.802→0.929` | 两行 benchmark 同口径 | embedding 有信号；RRF 是候选，不能推导端到端收益。 |
| `M21-E02` | 08-03 | 受控 A/B | 验证 fusion 的端到端收益 | Qwen-plus + clean Milvus/Qwen embedding；唯一变量为 weighted/RRF | diagnostic `21/32→20/32` | 同行两组 | RRF 不切默认。 |
| `M21-E03` | 08-03 | 受控 A/B | 验证 embedding 的端到端收益 | Qwen-plus + weighted + 32 题 + 同 oracle/hash；唯一变量为 local/Milvus embedding | `21/32 vs 21/32`；subtype 相同 | 同行两组 | 没有 embedding 可归因提分证据。 |
| `M21-E04` | 08-03 | 补充/负向证据 | 检验 RRF 风险 | DeepSeek + clean Milvus/Qwen embedding；唯一变量为 weighted/RRF | diagnostic `21/32→18/32` | 同行两组 | RRF 有端到端负向风险。 |
| `M21-E05` | 08-03 | 评测口径修正 | 修正过粗的 schema 归因 | 仅增加 `failure_subtype`，不改评分或默认配置 | output table/column、result、scorer contract 分开显示 | 历史 `failure_stage` 保持兼容 | M22 应先处理输出契约，而非继续归因 retrieval。 |
| `M22-E01` | 08-04 | 评测口径修正 | 分离 Context / Output / Result / Manual contract | case、scorer 与新增 coupon_order_count metric；schema docs `193→194`，hash `58534cb6...` | trace SchemaGraph 评分、等价 alias、三类报告视图、结构化语义拒绝 | M21 结果只作历史快照 | 不改变默认模型/检索；后续新 benchmark 不可跨 193/194 docs 比较。 |
| `M22-E02` | 08-04 | 诊断快照 | 验证 M22 后默认链路 | DeepSeek + local deterministic + weighted、32 条、SQLite oracle、LangFuse off | total `25/32`；automated `22/27`；manual `3/5` | M21 `21/32` 不可比较 | `db_plan_002/003/004` 均结构化通过；`db_core_004` 单 case 排序复测通过，但批量实时 LLM 仍波动；不把总分视为模型提升。 |

## 4. 当前活跃实验卡片

### M22 — Eval Contract / Semantic Output Stabilization

**问题**：怎样让内部 Schema 上下文、最终输出、结果对照、人工诊断各自有证据，并把真实 QueryPlan→SQL 缺口与评测口径调整分开？

**固定边界**：默认模型、embedding、Milvus、weighted fusion、SQLite deterministic oracle 和 seed 均未切换；新增 `coupon_order_count` 因确认的语义事实改变 schema document corpus 至 194。

**结论链**：

1. `schema_context_size` 改从同请求 trace 的 SchemaGraph `tables/fields` 评分，最终 `body.columns` 不再冒充上下文证据。
2. `db_plan_002/003/004` 用 `blocked_via=semantic_request_validation` 和明确 issue tag 区分不支持需求与 LLM generation error。
3. SCD overlap 已在默认 trace 实际出现；渠道订单量排序以 QueryPlan prompt + SQL plan contract 固化，并在单 case SQLite oracle 中通过。
4. 32 条 `25/32` 是口径变化后的诊断快照，只可用于下一步定位，不可同 M21 `21/32` 做能力归因。

**当前决策**：M22 收口，M23 如研究 retrieval 必须先固定 194-doc corpus、新 case/scorer 与同一模型条件；RRF、rerank、默认 embedding/Milvus 仍需单独确认。

### M21 — Schema Retrieval Fusion / Context Repair

**问题**：embedding 或 fusion 是否修复 Schema Retrieval，并转化为端到端收益？

**固定实验边界**：`schema_docs_count=193`、`schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`、Qwen embedding `qwen3.7-text-embedding`（1024 维）；端到端使用 SQLite deterministic oracle 且关闭 LangFuse。

**结论链**：

1. `M21-E01` 证明 Qwen embedding 的 vector-only recall 有提升，但 weighted merge 没有保住信号。
2. `M21-E02` 和 `M21-E04` 显示 RRF 在端到端没有收益，且存在负向风险。
3. `M21-E03` 在严格单变量条件下没有观察到 embedding 端到端收益。
4. `M21-E05` 发现旧 `schema_context` 混入输出列、alias、结果契约等问题，因此后续优化转向 M22。

**当前决策**：M21 的 embedding / fusion 线收口；默认保持 `weighted` 与本地 deterministic。若后续研究 retrieval，应以 rerank 等新的单变量假设重新立项，不复用“embedding 必然提分”的前提。

## 5. 失败分类速查

| 分类 | 何时使用 | 排查方向 |
|---|---|---|
| `schema_retrieval` | SchemaGraph / retrieval trace 明确缺少目标表或字段。 | retrieval、召回、索引或 schema docs。 |
| `schema_context` | 旧兼容大类；不能单独证明检索失败。 | 先查看 `failure_subtype`。 |
| `output_table_contract` | 最终 `tables_used` 不满足 expected table contract。 | QueryPlan 到 SQL 的漏表。 |
| `output_column_contract` | 最终 `columns` 不满足 expected column contract。 | 选择列、join、alias 或生成稳定性。 |
| `result_contract` | SQL 可执行，但结果列、排序、口径或数值不符合 expected。 | result_match、指标口径与 SQL 输出。 |
| `scorer_contract` | 评分规则或证据需要人工复核。 | scorer 与 case 契约。 |
| `query_plan` / `plan_validation` / `sql_generation` | 计划偏题、不可解析或 SQL 生成失败。 | QueryPlan、prompt、解析与生成约束。 |
| `sql_guard` | 安全策略拦截。 | 必须先确认真风险或误拦，不能直接放宽。 |

## 6. 历史快照与报告索引

### 不再作为当前决策依据的历史信息

- M19 的 formal、challenge、diagnostic 为三次独立真实 LLM run；重复 case 曾出现 alias、生成错误和失败阶段变化。这是 LLM 波动的例证，不是同批结果的横向比较。
- M20 之前固定 collection `datapilot_schema_docs` 出现重复灌入（193 schema docs 对应 `row_count=19493`）。污染链路数据保留作“索引卫生为何必要”的历史证据，不用于 embedding 优劣判断。
- M14-lite 的模型和 embedding 初筛保留在矩阵中，供追溯候选来源；它们不覆盖 M20/M21 的 clean-link 结论。

### 报告索引

| 实验 | 主要报告 / 对比 |
|---|---|
| `M19-E01` | `eval/reports/m19-formal-report.md`；`m19-challenge-report.md`；`m19-diagnostic-report.md`；`m19-diagnostic-triage.json` |
| `M19-E02` | `eval/reports/m19-qwen37max-formal-report.md`；`m19-qwen37max-challenge-report.md`；`m19-qwen37max-diagnostic-report.md`；`m19-deepseek-vs-qwen37max-diagnostic-triage-compare.md` |
| `M20-E01` | `eval/reports/m20-deepseek-qwenemb-diagnostic-report.md`；`m20-deepseek-qwenemb-diagnostic-triage.json`；`m20-milvus-index-smoke.md` |
| `M20-E02` | `eval/reports/m20-qwen37max-qwenemb-diagnostic-report.md`；`m20-clean-deepseek-vs-qwen37max-compare.md` |
| `M21-E01` | `eval/reports/m21-baseline-deterministic-weighted.md`；`m21-candidate-deterministic-rrf.md`；`m21-baseline-qwen-milvus-weighted.md`；`m21-candidate-qwen-milvus-rrf.md` |
| `M21-E02` | `eval/reports/m21-qwen-plus-weighted-diagnostic-report.md`；`m21-qwen-plus-rrf-diagnostic-report.md`；`m21-qwen-plus-weighted-vs-rrf-compare.md` |
| `M21-E03` | `eval/reports/m21-qwen-plus-local-weighted-report.md`；`m21-qwen-plus-qwenemb-weighted-report.md`；`m21-qwen-plus-local-vs-qwenemb-triage-compare.md` |
| `M21-E04` | `eval/reports/m21-deepseek-weighted-diagnostic-report.md`；`m21-deepseek-rrf-diagnostic-report.md` |
| `M21-E05` | `eval/reports/m21-context-audit.md` |
| `M22-E02` | `eval/reports/m22-default-diagnostic-report.md`；`m22-default-diagnostic-triage.json`；`eval/traces/m22-default-diagnostic-traces.jsonl` |

## 7. 维护规则

- 每次真实 eval、A/B 或重要 smoke 先新增一行矩阵，并声明证据类型、固定条件、唯一变量和可比对象。
- 只有改变当前路线的实验，才新增“活跃实验卡片”；不重复粘贴完整配置与所有 failure 分布。
- 报告路径只在本节维护一次；运行命令只维护在 `runbook.md`。
- 新结论覆盖旧路线判断时，在旧行的“决策”列标明“被 `Mxx-Exx` 覆盖”，不改写历史数字。
- 默认模型、默认 embedding、正式 case 集的切换仍须单独决策；账本记录证据，不代替决策确认。
