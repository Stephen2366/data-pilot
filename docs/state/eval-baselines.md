# DataPilot Eval Baselines

> 本文是 DataPilot 的长期评测账本，优先回答“当前应据什么决策、哪些结果可直接比较”。完整报告和历史叙事分别保留在 `eval/reports/` 与 `docs/state/AI_CONTEXT_CHANGELOG.md`。

更新时间：2026-08-06

> 模型名称统一写完整标识：主模型写 provider + exact model id（例如 `DeepSeek deepseek-v4-flash`、`Qwen qwen3.7-plus`、旧入口 `Qwen qwen-plus`）；embedding 写 provider + exact embedding model（例如 `DashScope qwen3.7-text-embedding`）。实验矩阵不再使用 `Qwen-plus`、`DeepSeek`、`Qwen embedding` 等容易混淆的简称。

## 1. 当前决策摘要

| 项目 | 当前结论 | 证据 |
|---|---|---|
| 默认主模型 | Qwen `qwen3.7-plus`；本次基于 M22 三次 C1 稳定性结果切换。 | `M22-E04` |
| 默认检索 | `inmemory + deterministic + weighted`；Milvus、DashScope `qwen3.7-text-embedding`、RRF 均仅作显式实验路径。 | `M20-E01`、`M21-E02`、`M21-E03` |
| 当前优化方向 | M23 新合同的 local / clean Milvus 单次诊断均已建立；M24 先清理 SQL 合同误拦、真实 order/limit 丢失和输出投影边界，再做重复交错 A/B。两组单次分数不能作为 embedding 结论。 | `M23-E03`、`M23-E04` |
| 已收口的假设 | DashScope `qwen3.7-text-embedding` 有向量召回信号，但尚无端到端可归因提分；RRF 也未带来端到端收益。 | `M21-E01`、`M21-E02`、`M21-E03` |
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

## 2.5 数据库异常彩蛋：处理原则、覆盖边界与专项评测

> 这是跨模块的数据库 / 评测知识，不属于某一次 M22 模型实验。查 SQL 结果争议、reference SQL、数据质量、异常 case 或后续会话续接时，优先读本节，并结合 `docs/state/database-current-state.md` 的异常菜单。

评测使用确定性 SQLite seed。`result_match` 只执行某条 case 自己的 `expected_sql`，再比较结果；它不会因为数据库里存在异常数据，就自动检查模型是否正确处理了全部异常。因此，不能只问“case 有没有碰到彩蛋”，还要问：**这类数据在该业务问题中该保留、该排除，还是该作为异常查出来。**

M22 原审计描述的是当时的合同：`db_core_002` 只按 `order_item_id` 连接，漏掉整单退款，也没有成交订单过滤。M23 已修正该 reference；M22 的 C0-C3 分数仍是旧合同历史快照，不能拿来证明 M23 对异常数据的鲁棒性。

### 处理原则与当前三类评测覆盖

| 数据异常 / 业务边界 | 普通经营分析的正确处理 | formal（主线回归） | challenge（业务口径） | diagnostic（定位工具） | 当前结论 |
|---|---|---|---|---|---|
| 未支付、`cancelled` / `canceled` 两种拼写 | 对成交 GMV、净收入、成交订单排除；对“订单状态分布”应保留并统计 | GMV / 净收入的 expected value 已受正确成交口径约束 | `db_simple_002`、GMV、净收入、商品/渠道 GMV reference 显式过滤 | 多为 schema / plan / trace 检查，不能证明最终数值 | 已覆盖成交类口径；不是所有“订单查询”都应过滤 |
| 一单多券 | 保留订单，但通过 `COUNT(DISTINCT order_id)` 防止桥接表放大订单数 | `p3a_multi_001` 自动结果校验 | `db_multi_001` 自动结果校验 | `db_trace_002` 只检查流程步骤 | 已覆盖“用券订单数”去重 |
| 整单退款 `order_item_id IS NULL` | 不应丢弃；商品归因时明细退款优先，整单退款回退 `refunds.product_id`，不能复制给订单每个商品 | 无独立题 | M23 后 `db_core_002` 自动结果校验该 fallback 和成交过滤 | `db_join_003` 仍为人工归因素材 | 已覆盖一个明确的商品退款率口径；不是“把空值绕开” |
| 外部单号重复、`SRC-*` 与 `ORD-*` 命名空间不同 | 不把外部单号当主键，也不能跨命名空间 join；订单关联走真实外键 `refunds.order_id -> orders.id` | 无 | 无 | 无 | 未覆盖；当前只有语义文档提示，不能证明模型不会错误 join |
| 负数退款冲销 | 金额分析保留正负号，不能默认取绝对值或直接删除；是否计入退款“笔数/率”必须先定义业务含义 | 无 | 无退款金额题 | 无 | 未覆盖，且当前 `refund_rate` 对 requested / rejected / 冲销记录的计数边界尚未确认 |
| 订单头金额与明细金额不一致 | 不强行把两张表算成相等：订单 GMV 用 `orders.order_amount`，商品 GMV 用 `order_items.line_amount`；需要时另做对账诊断 | 已分别使用正确粒度，但不验证差异 | 已分别使用正确粒度，但不验证差异 | 无专门对账题 | 仅间接覆盖，未验证“发现 5 条不一致订单” |
| SCD `valid_to IS NULL` | 按生效时间窗口保留当前版本，不是要过滤的脏数据 | 无 | `db_hard_003` 有 reference，但为 manual | 有 schema context / manual 素材 | 有参考素材，非自动硬门 |

### 三类测评各自该负责什么

- **formal**：验证日常、稳定的业务查询没有回归。异常只在它会直接改变常用指标时进入，例如成交状态和一单多券；不应把所有对账题都塞入 formal。
- **challenge**：验证“看起来能跑、但会因真实数据边界而算错”的 SQL，是整单退款 fallback、错误 join、退款冲销等口径题的主要落点。
- **diagnostic**：验证系统在哪一层理解错、选表错、连表错或被拦截；它可以保留人工诊断题，但不能拿“流程成功”替代异常结果的自动正确性证明。

### 异常数据专项评测（M23）

专项清单是 `eval/cases/database-exception-suite.yaml`，通过 `python -m eval.run_eval --case-set ...` 从原文件挑选 case；它不复制 formal / challenge / diagnostic 的 YAML，避免同一题因重复定义被重复计分或日后 reference 漂移。

| 类型 | case | 判定 |
|---|---|---|
| 已有成交口径 | `db_simple_002` | 自动：未支付和两种取消拼写不进入成交订单。 |
| 已有桥接去重 | `db_multi_001` | 自动：一单多券不放大订单数。 |
| 已有整单退款 | `db_core_002` | 自动：成交订单过滤 + 明细优先 / `refunds.product_id` fallback。 |
| 既有归因诊断 | `db_join_003` | 人工：检查商品退款率的 join / grain 理解，不计入自动能力分。 |
| 新增带符号退款金额 | `db_anomaly_001` | 自动：只统计 `completed`、按 `processed_at` 过滤、`SUM(refund_amount)` 保留负数冲销。 |
| 新增真实外键关联 | `db_anomaly_002` | 自动：渠道退款金额只能经 `refunds.order_id -> orders.id -> channels.id`。 |
| 新增金额对账 | `db_anomaly_003` | 自动：报告订单头与明细金额不一致的订单数，而不篡改数据。 |

当前专项为 **6 条自动 + 1 条人工素材**。它已覆盖当前 seed 的关键异常边界，但仍不代表完整企业数据质量能力；例如外部源系统“重复单号应如何按业务幂等去重”仍需具体接入语义，不能由本地 seed 擅自定义。

## 3. 权威基线与实验矩阵

> “固定条件”只列影响可比性的关键项；完整配置和原始数字见“报告索引”。`—` 表示该实验未运行该集合，不表示失败。

| ID | 日期 | 证据类型 | 目的 | 固定条件 / 唯一变量 | 结果 | 可比对象 | 决策 |
|---|---|---|---|---|---|---|---|
| `M13-E01` | 07-26 | 事实锚点 | Phase 3A 稳定回归快照 | DeepSeek `deepseek-v4-flash` + local retrieval | formal `10/10`；challenge `14/16`；diagnostic `23/32` | — | 上一轮稳定基线。 |
| `M14-E01` | 07-27 | 诊断快照 | 更严格口径下复测默认链路 | DeepSeek `deepseek-v4-flash` + local retrieval | formal `8/10`；challenge `12/16`；diagnostic `24/32` | `M13-E01` 不可直接比较 | 口径收紧，不能据此判退化。 |
| `M14-E02` | 07-27 | 补充证据 | 模型候选初筛 | Qwen `qwen3.7-plus` | formal `9/10`；challenge `13/16`；diagnostic `21/32` | 同轮 DeepSeek `deepseek-v4-flash` 快照 | 保留候选，不切默认。 |
| `M14-E03` | 07-27 | 补充证据 | 模型候选初筛 | Qwen `qwen3.7-max` | diagnostic `22/32` | 同轮快照 | 保留候选，不切默认。 |
| `M19-E01` | 08-02 | 诊断快照 | 验证 triage 闭环 | DeepSeek `deepseek-v4-flash` | formal `7/10`；challenge `9/16`；diagnostic `19/32` | `M19-E02` 仅作同轮模型参考 | 不单独判定默认能力下降。 |
| `M19-E02` | 08-02 | 补充证据 | 主模型候选对照 | Qwen `qwen3.7-max` | formal `8/10`；challenge `12/16`；diagnostic `22/32` | `M19-E01` | 生成类失败较少，但 schema 问题未解；不切默认。 |
| `M20-E01` | 08-02 | 事实锚点 | 修复索引卫生并重测 | DeepSeek `deepseek-v4-flash` + clean Milvus + DashScope `qwen3.7-text-embedding`；193 docs、run-scoped | diagnostic `17/32` | 旧污染结果不可比 | 证明 clean 链路可信，不证明 embedding 无效。 |
| `M20-E02` | 08-02 | 补充证据 | clean 链路模型对照 | `M20-E01` 同检索链路，唯一变量为 Qwen `qwen3.7-max` | diagnostic `21/32` | `M20-E01` | 同链路高于 DeepSeek `deepseek-v4-flash`，但单次 run 不切默认。 |
| `M21-E01` | 08-03 | 受控 A/B | 检查 embedding 与 fusion 的离线召回 | 10 题、`top_k=12`；变量为 backend/embedding/fusion | vector `0.787→0.929`；weighted merged 均 `0.738`；RRF `0.802→0.929` | 两行 benchmark 同口径 | embedding 有信号；RRF 是候选，不能推导端到端收益。 |
| `M21-E02` | 08-03 | 受控 A/B | 验证 fusion 的端到端收益 | Qwen `qwen3.7-plus` + clean Milvus + DashScope `qwen3.7-text-embedding`；唯一变量为 weighted/RRF | diagnostic `21/32→20/32` | 同行两组 | RRF 不切默认。 |
| `M21-E03` | 08-03 | 受控 A/B | 验证 embedding 的端到端收益 | Qwen `qwen3.7-plus` + weighted + 32 题 + 同 oracle/hash；唯一变量为 local/Milvus + DashScope `qwen3.7-text-embedding` | `21/32 vs 21/32`；subtype 相同 | 同行两组 | 没有 embedding 可归因提分证据。 |
| `M21-E04` | 08-03 | 补充/负向证据 | 检验 RRF 风险 | DeepSeek `deepseek-v4-flash` + clean Milvus + DashScope `qwen3.7-text-embedding`；唯一变量为 weighted/RRF | diagnostic `21/32→18/32` | 同行两组 | RRF 有端到端负向风险。 |
| `M21-E05` | 08-03 | 评测口径修正 | 修正过粗的 schema 归因 | 仅增加 `failure_subtype`，不改评分或默认配置 | output table/column、result、scorer contract 分开显示 | 历史 `failure_stage` 保持兼容 | M22 应先处理输出契约，而非继续归因 retrieval。 |
| `M22-E01` | 08-04 | 评测口径修正 | 分离 Context / Output / Result / Manual contract | case、scorer 与新增 coupon_order_count metric；schema docs `193→194`，hash `58534cb6...` | trace SchemaGraph 评分、等价 alias、三类报告视图、结构化语义拒绝 | M21 结果只作历史快照 | 不改变默认模型/检索；后续新 benchmark 不可跨 193/194 docs 比较。 |
| `M22-E02` | 08-04 | 诊断快照 | 验证 M22 后默认链路 | DeepSeek `deepseek-v4-flash` + local deterministic + weighted、32 条、SQLite oracle、LangFuse off | total `25/32`；automated `22/27`；manual `3/5` | M21 `21/32` 不可比较 | `db_plan_002/003/004` 均结构化通过；`db_core_004` 单 case 排序复测通过，但批量实时 LLM 仍波动；不把总分视为模型提升。⚠️ 注：该快照早于 M22 复审修复（Context warn / via 核验 / SQL evidence / 成交订单语义），本次仅完成代码测试，未重跑真实 LLM diagnostic。 |
| `M22-E03` | 08-05 | 首轮受控候选 + 异常覆盖审计 | 在 194-doc、新 case/scorer 口径下筛选 Qwen / Milvus / RRF，并审计数据库异常彩蛋覆盖 | C0-refresh `24/32`；C1 `27/32`；C2 `25/32`；C3 `24/32`；retrieval-only local weighted `0.738`、Milvus weighted `0.738`、Milvus RRF `0.929` | C0-C3 只作同口径首轮筛选，不是稳定性结论；M21 的 193-doc 结果不可混比 | C1 单次最高但不切默认；C2 未显示可归因端到端收益；C3 召回提高但端到端未提高。成交类过滤、优惠券去重、SCD 窗口已覆盖；外部单号、负数退款、金额对账无独立 case；`db_core_002` 排除整单退款且未显式排除取消订单，退款率口径待确认。 |
| `M23-E01` | 08-05 | 评测/语义基线修正 | 先治理非 pipeline 因素，再建立下一轮 retrieval 基线 | 退款率改为成交订单 + 明细优先 / 整单退款回退；订单量去重；formal 8 条、challenge 12 条自动 SQL case 均为 result/value 对照；新增不复制既有 YAML 的 7 条异常专项（6 自动 + 1 人工）；SQLite + MySQL 双端审计 | M22 所有真实 LLM 分数均属旧 case/scorer 合同，不可直接比较 | 原 20 条与新增 3 条 reference SQL 两端均可执行；专项 focused `32 passed`。需从此合同重新跑真实 LLM 基线，默认模型/检索不变。 |
| `M23-E02` | 08-06 | 诊断快照 | 首次运行 7 条数据库异常专项，确认新 case 能否进入真实 Text2SQL 链路 | Qwen `qwen3.7-plus`、`new_text2sql`、`inmemory + deterministic + weighted`、SQLite deterministic oracle、LangFuse off、HTTP/HTTPS proxy；195-doc corpus | total `1/7`；自动 `1/6`；人工 `0/1 review`。唯一通过为 `db_anomaly_001`：completed + `processed_at` + signed refund amount。 | 无同合同重复 run；不能与 M22 194-doc 总分比较 | 有效首轮暴露成交订单 limit、coupon 输出列、退款率口径、内部外键关联和金额对账输出缺口；`db_join_003` 为 Qwen generation error。无代理启动的 `WinError 10013` 未计入结果。 |
| `M23-E03` | 08-06 | 事实锚点 | M23 新合同 32 条 local 首跑基线 | Qwen `qwen3.7-plus` + `inmemory/deterministic` + weighted、32 条 diagnostic、195-doc corpus/hash `ce04fe4f...`、SQLite deterministic oracle、LangFuse off、proxy | total `23/32`；automated `20/27`；manual/diagnostic `3/5`；硬失败 9，failed-or-review 10 | M23-E02 为 7 条专项（不同 case 集）；M22 194-doc 分数不可比 | 自动硬失败 7 条：3 条 result/output fidelity、2 条 generation/plan error、2 条 SQL plan contract false block；另有 2 条人工/诊断硬失败。`db_hard_003` 是额外 review-only，不是硬失败。Context 无目标 schema 缺失证据。 |
| `M23-E04` | 08-06 | 单次诊断快照 | 在 M23 同合同下核对 clean Milvus / Qwen embedding 链路 | Qwen `qwen3.7-plus` + clean run-scoped Milvus + DashScope `qwen3.7-text-embedding` + weighted；32 条、195 docs/hash `ce04fe4f...`、1024 维、final row count 195、SQLite oracle、LangFuse off | total `21/32`；automated `20/27`；manual/diagnostic `1/5` | `M23-E03` 只作同合同单次参照；两组均未重复 | 自动能力与 local 同为 `20/27`；总分差来自人工/诊断项。旧 triage 的 `schema_context/retrieval` 中含最终表列合同，不能据 `23→21` 判断 embedding 退化；默认检索不变。 |

## 4. 当前活跃实验卡片

### M22 — Eval Contract / Semantic Output Stabilization

**问题**：怎样让内部 Schema 上下文、最终输出、结果对照、人工诊断各自有证据，并把真实 QueryPlan→SQL 缺口与评测口径调整分开？

**固定边界**：默认模型、embedding、Milvus、weighted fusion、SQLite deterministic oracle 和 seed 均未切换；新增 `coupon_order_count` 因确认的语义事实改变 schema document corpus 至 194。

**结论链**：

1. `schema_context_size` 改从同请求 trace 的 SchemaGraph `tables/fields` 评分，最终 `body.columns` 不再冒充上下文证据。
2. `db_plan_002/003/004` 用 `blocked_via=semantic_request_validation` 和明确 issue tag 区分不支持需求与 LLM generation error。
3. SCD overlap 已在默认 trace 实际出现；渠道订单量排序以 QueryPlan prompt + SQL plan contract 固化，并在单 case SQLite oracle 中通过。
4. 复审后 C0-refresh 为 `24/32`；C1/C2/C3 首轮分别为 `27/32`、`25/32`、`24/32`。这些是同一 194-doc 新口径下的单次筛选结果，不能据此证明稳定收益。数据库异常彩蛋边界与当前专项见本文 §2.5。

### M22-E04 — C0-C3 三次重复稳定性（2026-08-05）

固定条件：32 条 diagnostic、`new_text2sql`、SQLite deterministic oracle、LangFuse disabled、194-doc corpus/hash；Milvus 每次使用独立 collection。

| 组 | 配置 | 首轮 | 第2次 | 第3次 | 范围 | 决策 |
|---|---|---:|---:|---:|---:|---|
| C0 | DeepSeek `deepseek-v4-flash` + Milvus + DashScope `qwen3.7-text-embedding` + weighted | 24/32 | 24/32 | 25/32 | 24–25 | 基线 |
| C1 | Qwen `qwen3.7-plus` + inmemory/deterministic + weighted | 27/32 | 28/32 | 28/32 | 27–28 | 当前最稳定候选，不自动切换 |
| C2 | Qwen `qwen3.7-plus` + Milvus + DashScope `qwen3.7-text-embedding` + weighted | 25/32 | 27/32 | 25/32 | 25–27 | 未稳定超过 C1 |
| C3 | Qwen `qwen3.7-plus` + Milvus + DashScope `qwen3.7-text-embedding` + RRF | 24/32 | 26/32 | 27/32 | 24–27 | 未稳定超过 C1 |

第2次 C2 首次启动被工具 120 秒上限中断，未计入；重启后的有效结果写入 `m22-c2-qwen-milvus-weighted-r2b-*`。实验结论：C1 三次均为最高或并列最高；C2/C3 无稳定端到端收益，不切换默认 embedding、Milvus 或 RRF。随后用户基于 C1 三次结果确认切换默认主模型为 Qwen `qwen3.7-plus`。该实验仍不代表对数据库异常彩蛋的鲁棒性。

### M22-E05 — Qwen 3.8 追加对照（2026-08-05）

固定条件：`qwen3.8-max`、`inmemory + deterministic`、`weighted`、32 条 diagnostic、`new_text2sql`、SQLite deterministic oracle、LangFuse disabled。

- 结果：`22/32`。
- 模型调用可用，因此没有执行备用 `qwen3.7-max`。
- 结论：单次结果低于 C1 三次重复的 `27–28/32`，仅作候选记录，不改变默认模型。

### M22-E06 — Qwen 3.7 Max 追加对照（2026-08-05）

固定条件：`qwen3.7-max`、`inmemory + deterministic`、`weighted`、32 条 diagnostic、`new_text2sql`、SQLite deterministic oracle、LangFuse disabled。

- 结果：`26/32`，高于同条件 Qwen 3.8 的 `22/32`。
- 这是单次追加快照，不纳入 C0-C3 三次重复矩阵，不改变默认模型。

### M21 — Schema Retrieval Fusion / Context Repair

**问题**：embedding 或 fusion 是否修复 Schema Retrieval，并转化为端到端收益？

**固定实验边界**：`schema_docs_count=193`、`schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`、DashScope `qwen3.7-text-embedding`（1024 维）；端到端使用 SQLite deterministic oracle 且关闭 LangFuse。

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
| `M22-E04` | `m22-c0-refresh[-r2/-r3]-report.md`；`m22-c1-qwen-local-weighted[-r2/-r3]-report.md`；`m22-c2-qwen-milvus-weighted[-r2b/-r3]-report.md`；`m22-c3-qwen-milvus-rrf[-r2/-r3]-report.md` |
| `M22-E05` | `eval/reports/m22-qwen38-local-weighted-report.md`；`eval/reports/m22-qwen38-local-weighted-triage.json`；`eval/traces/m22-qwen38-local-weighted-traces.jsonl` |
| `M22-E06` | `eval/reports/m22-qwen37max-local-weighted-report.md`；`eval/reports/m22-qwen37max-local-weighted-triage.json`；`eval/traces/m22-qwen37max-local-weighted-traces.jsonl` |
| `M23-E03` | `eval/reports/m23-qwen-local-weighted-diagnostic-report.md`；`eval/reports/m23-qwen-local-weighted-diagnostic-triage.json`；`eval/traces/m23-qwen-local-weighted-diagnostic-traces.jsonl` |
| `M23-E04` | `eval/reports/m23-qwen-milvus-qwenemb-diagnostic-report.md`；`eval/reports/m23-qwen-milvus-qwenemb-diagnostic-triage.json`；`eval/traces/m23-qwen-milvus-qwenemb-diagnostic-traces.jsonl` |

## 7. 维护规则

- 每次真实 eval、A/B 或重要 smoke 先新增一行矩阵，并声明证据类型、固定条件、唯一变量和可比对象。
- 只有改变当前路线的实验，才新增“活跃实验卡片”；不重复粘贴完整配置与所有 failure 分布。
- 报告路径只在本节维护一次；运行命令只维护在 `runbook.md`。
- 新结论覆盖旧路线判断时，在旧行的“决策”列标明“被 `Mxx-Exx` 覆盖”，不改写历史数字。
- 默认模型、默认 embedding、正式 case 集的切换仍须单独决策；账本记录证据，不代替决策确认。
