# M26 Diagnostic Human Audit / Eval Reconciliation Notes

## Implementation checklist（2026-08-07）

- [x] 完整读取 `AGENTS.md`、`docs/state/AI_CONTEXT.md` 及其要求的运行、评测和数据库事实源。
- [x] 确认 M25 已于 2026-08-07 验收，M26 P0 入口门禁通过。
- [x] 冻结 `qwen3.7-plus + inmemory/deterministic + weighted` round 2 的 32 条输入、身份与 hash，不调用 LLM。
- [x] 建立可复用 audit record / Markdown adapter 与确定性 fixtures。
- [x] 完成 32 条人工审计、差异矩阵和五张决策卡。
- [x] 在中间确认门暂停，等待用户决定 P2 的长期安全/评测合同改动。
- [x] 用户确认后实施定点修复、targeted replay、验证与收工。

## 开工记录

- M26 只先实施 P0/P1：审计结论不回写历史 `EvalResult.passed`、LangFuse score 或正式报告；SQL Guard、fidelity、scorer、case 与正式统计在用户确认前保持不变。
- 首轮主样本固定为现有 M25 round 2 的 Qwen `qwen3.7-plus` + local deterministic/weighted run（计划指定 `28/32`），输入位于 `.agent_work/temp/`；可复核 manifest、audit records 与人工审计结论将输出到 `eval/reports/`。
- 踩坑：M25 历史 run 没有单独保存 `EvalResult.score_details` JSON，只有 report 的 Score Summary。P0 初版若重新调用 rule scorer，会让 `result_match` 执行 SQLite reference SQL，既拖慢审计又违背“先整理已有证据”的边界；已改为有界 legacy adapter，只提取冻结报告的自动 score 明细，并在 audit record 明示来源与 report hash。后续新的 runner 可再补结构化 score artifact，不能以本次 adapter 取代它。
- 踩坑：旧 triage 为通过 case 默认填 `needs_action=manual_review`，不能把该字段直接当作人工待审数；M26 汇总改用 runner 的真实 `review_required`，并与人工 `fail`、`unavailable` 分开计数。这是审计展示校正，尚未改变旧 triage 或正式报告字段。

## P0/P1 冻结审计与人工对账（2026-08-07）

### 冻结输入与产物

- 首轮输入严格固定为 `m25-round2-qwen37plus-local`：Qwen `qwen3.7-plus`、`inmemory + deterministic + weighted`、45s / retry0、SQLite deterministic oracle、LangFuse off、完整 32 条完成 run。原始 trace/report/triage 均来自 `.agent_work/temp/`，其 SHA-256、大小和运行配置已固化到 `eval/reports/m26-qwen37plus-local-round2-audit.json` manifest。
- 新增 `eval.audit` 深 module 和 `eval.run_audit` 明确 CLI：只能提供同一 run 的 case / trace / report / triage / runtime identity；缺 trace、case/triage 集合不一致、题面不一致或 score 明细缺失会立即失败，不从其它 run 补洞。
- 历史自动 score 明细仅存在冻结 report 的 Score Summary；因此 audit record 标记为 `legacy_frozen_report_score_summary`。该有界 adapter 不执行 scorer/reference SQL；后续若补 runner 的结构化 score artifact，应替换它而非把 Markdown 作为长期主事实源。
- 输出：32 条结构化 audit records、完整 SQL（或明确 unavailable/blocked/execution_failed）、最小脱敏结果样本、自动评分与 triage、人工 verdict / reconciliation，以及 Markdown 人读 adapter。

### 人工审计结果

| 口径 | 结果 |
|---|---:|
| raw cases / semantic groups | 32 / 26 |
| audit pass / fail / unavailable / insufficient evidence | 26 / 2 / 3 / 1 |
| reconciliation（raw） | agree 26；false positive 1；status mismatch 4；unresolved 1 |
| reconciliation（semantic group） | agree 20；false positive 1；status mismatch 4；unresolved 1 |
| 已观察的真实 pipeline failure / review pending / external unavailable | 2 / 1 / 3 |

- **false positive — `db_core_002`**：自动 `result_match` 通过，但候选 SQL 只经 `refunds.order_item_id` 归因，缺少权威合同的 `COALESCE(oi.product_id, r.product_id)` 整单退款 fallback。当前 seed 的 Top1 恰好未暴露差异；审计判为模型 SQL 语义失败，不能以自动通过解释为口径已覆盖。
- **status mismatch — `db_multi_002` / `db_hard_001` / `db_join_003`**：均为 QueryPlan timeout，SQL unavailable；runner failed 与人工 unavailable 不是同一语义状态，不能计入 observed semantic wrong。
- **status mismatch — `db_schema_003`**：SchemaGraph 只含 `orders_wide` 物理字段、没有 alternatives 所要求的 `gmv` 语义，人工也判 fail；但自动 scorer 通过最终输出 `column_recall` 碰巧报错，并没有真正消费 `expected_tables_alternatives` 或 SchemaGraph，因此必须按 Context scorer 方案修复，不可把这条现状误读为已验证 alternatives。
- **unresolved — `db_hard_003`**：manual SCD case 没有确定性 result/reference oracle；候选 SQL 与 reference 的时间边界和排序不同，不能只凭 SQL 文本硬判。
- 其余安全阻断、明确 plan validation block、result_match、trace 和 SchemaContext size contract 都有直接证据；所有人工 verdict 记录在 `eval/reports/m26-qwen37plus-local-round2-audit-verdicts.json`。

### 中间确认门：待用户决定（P2 前禁止修改）

1. **CTE / RBAC**：A 在 AST 区分已声明 CTE 名和内部物理表，CTE 名不做 RBAC、内部真实表仍检查；B 保持误拦；C 广泛放行 CTE/derived（可能越权）。建议 **A**。
2. **ratio `* 1.0` fidelity**：A 仅对审计证据支持的 ratio/cast 类型提升作窄等价；B 继续 `indeterminate` 人工复核；C 通用代数化简（可能忽略 NULL/类型/溢出）。建议在 **A/B** 中确认，拒绝 C。
3. **`schema_context_match`**：A 直接使用同请求 SchemaGraph 按 `expected_tables_alternatives` 判分；B 删除/改名，只保留诊断展示。`db_schema_003` 已证实当前检查对象错误，若该 case 目标仍是 Context，建议 **A**。
4. **manual / triage 状态**：A 保留兼容 `failed`，新增/突出正交 `execution_failed`、`review_pending`；B 直接改写 `failed` 含义（破坏历史脚本）。建议 **A**。
5. **题面/业务合同**：`db_hard_001` 要确认是订单 GMV 还是严格 `item_gmv`，以及 root label 是否必需；`db_hard_003` 的 SCD 边界/排序应是否进入自动合同；`db_core_002` 是否用 targeted deterministic counterfactual 让整单退款 fallback 成为可区分的自动证据。不能为模型通过率放宽 expected。建议按数据库事实源和产品题意逐题确认后递增 contract version。

## 用户确认与 P2 定点修复（2026-08-07）

### 用户选择

用户回复“按照你的建议，继续”，确认按中间确认门的推荐方案执行：

1. CTE/RBAC 采用 A：AST scope 区分 CTE/derived 临时名和内部物理表；不降低物理表/敏感字段检查。
2. ratio fidelity 采用 A：仅接受已审计的 `* 1.0` + `NULLIF(..., 0)` 类型提升，不做通用代数化简。
3. `schema_context_match` 采用 A：从同请求 SchemaGraph 的 tables/fields/metrics 按 `expected_tables_alternatives` 做 any-of 评分。
4. manual/triage 采用 A：保留 `failed` 兼容字段，增加 `execution_failed` / `review_pending` 正交状态并在报告突出。
5. 题面/合同：`db_hard_001` 明确为商品销售额 `item_gmv` 并要求 root label；`db_hard_003` 保持 manual、明确半开 SCD 时间边界和排序；为 `db_core_002` 增加 SQLite counterfactual，避免整单退款 fallback 被既有 seed 的 Top1 偶然掩盖。

### 实施记录

- SQL Guard 改用 sqlglot `Scope` 逐层收集物理表与字段：外层 CTE 名不进入 RBAC 表集合，CTE 内 `product_categories` / `orders` / `users.email` 仍进入检查。覆盖 recursive CTE 正例、CTE 内越权表、CTE 内敏感字段和 CTE 同名遮蔽物理表。
- fidelity 只在计划和 SQL 的分母均为相同 `NULLIF(..., 0)` 时，将 `numerator * 1.0 / denominator` 视为计划 `numerator / denominator` 的类型提升等价；trace metadata 写入 `narrow_equivalences`。修改分子、移除 NULLIF 或其他表达式变化仍失败。
- `schema_context_match` 在最终表/列 scorer 之前直接评分 SchemaGraph；alternative 的 `required_columns` 可由物理 fields 或 metrics 满足，并记录每个未命中 alternative 的缺表/缺列原因。`db_schema_003` 的冻结 Context 仍因没有 `gmv` metric 而失败，但失败阶段现在是 `schema_context`，不再伪装成 final output column 缺失。
- `FailureTriage` 新增 `execution_failed` 和 `review_pending`；旧 `failed` 不改含义，报告与 JSON 单列三条队列。M26 审计没有回写旧 run。
- `CASE_CONTRACT_VERSION` 升级为 `m26-v1`；历史 M25 audit manifest 保持 `m25-v1`，不得混算。

### P2 targeted 验证快照

- focused：`pytest tests/test_m26_targeted_contracts.py tests/test_m26_audit.py tests/test_m24_sql_plan_fidelity.py tests/test_m25_eval_trustworthiness.py tests/test_m4_nl2sql.py tests/test_phase3a_eval.py` → **62 passed, 1 warning, 73.16s**。
- 覆盖：合法 recursive CTE 与 CTE 内越权/敏感/遮蔽反例；`db_hard_002` 风格 `* 1.0` 正例和改变分子反例；`db_schema_003` alternatives 正反例；manual / external timeout 状态拆分；`db_core_002` 整单退款 fallback counterfactual（correct `Beta, 1.0`，缺 fallback 错为 `Alpha, 0.0`）。
- warning：既有 `StarletteDeprecationWarning`，不影响 M26。

## M26-v1 完整 diagnostic（2026-08-08，用户明确授权）

- 固定配置：Qwen `qwen3.7-plus`、`inmemory + deterministic + weighted`、45s / retry0、SQLite deterministic oracle、LangFuse off、`case_contract_version=m26-v1`；完整输入为 challenge + diagnostic extra 共 32 条。运行从日志约 14:02:04 至 14:23:00，生成独立 trace/report/triage，未覆盖 M25-v1 文件。
- 产物：`eval/traces/m26-v1-qwen37plus-local-diagnostic-traces.jsonl`（32 条 trace）、`eval/reports/m26-v1-qwen37plus-local-diagnostic-report.md`、`eval/reports/m26-v1-qwen37plus-local-diagnostic-triage.json`，以及 `eval/reports/m26-v1-vs-m25-round2-triage-compare.md`。
- 结果：runner raw `26/32`，failed `6`，review_required `3`；triage 的失败/待审队列为 7（execution_failed 4、review_pending 3），external_unavailable 4。semantic status 为 observed_correct 10、observed_wrong 1、not_observed 4、not_applicable 17；root cause 为 model_capability 1、external_service 4、retrieval_issue 1、mixed_or_unknown 1。
- 关键验证：`db_core_002` 从 M25-v1 的自动通过变为真实 `result_match` mismatch（expected `0.11516`、actual `0.44914`），与审计发现的整单退款 fallback 缺失一致；`db_schema_003` 从旧的 `output_contract/column_recall` 误归因改为 `schema_context` 的 `schema_context_alternatives_no_match`；`db_hard_002` ratio 题通过，未再出现 `* 1.0` fidelity 假阴性；`db_hard_003` 仍是 manual。
- 重要边界：`db_multi_002`、`db_hard_001`、`db_join_003` 以及新增的 `db_prompt_002` 发生 QueryPlan / LLM generation external failure，CTE 代表题没有生成 SQL，故本轮不能声称 CTE 修复已完成端到端验证。raw `26/32` 不能与 M25 `28/32` 直接解释为退化或提升：合同版本变了，且真实 LLM run 非确定。
- triage 对照：`output_contract` 失败从 1 降为 0；`query_plan` 3→4、`result_match` 0→1、`schema_context` 0→1，变化主要来自新合同和正确归因；详细分布见 compare report。未做模型、embedding、retry 或第二轮重复实验。

## 追加对照运行（2026-08-08，已完成）

- 固定条件：`m26-v1`、32 条 challenge + diagnostic、`new_text2sql`、weighted、SQLite deterministic oracle、LangFuse off、45s/retry0；Milvus 两组均使用 clean collection `datapilot_schema_docs_m25_qwen37plus_qwenemb_20260807_192300`，195 docs、1024 维、schema hash `8a8b6626...`，两组均 `initial=195 / inserted=0 / final=195`。
- `qwen3.7-max + local deterministic/weighted`：runner `25/32`、failed `7`、review_required `3`；triage execution_failed `5`、review_pending `3`、external_unavailable `3`。主要证据为 `db_core_002` SQL generation external failure、`db_schema_003` alternatives mismatch、`db_join_003` 缺 `products` 的 output-table contract、`db_hard_002` 通过、`db_hard_003` manual。
- `qwen3.7-plus + Milvus`：runner `26/32`、failed `6`、review_required `3`；triage execution_failed `3`、review_pending `3`、external_unavailable `4`。Milvus collection 元数据和 hash 校验通过；`db_schema_003` 仍是 schema_context alternatives mismatch。
- `qwen3.7-max + Milvus`：runner `27/32`、failed `5`、review_required `3`；triage execution_failed `3`、review_pending `3`、external_unavailable `3`。`db_schema_003` 仍暴露 alternatives mismatch，`db_join_003` 仍需 manual review；个别 max 请求耗时约 45–73 秒，最终 HTTP 200，但属于本轮延迟异常素材。
- 同一轮可观察到：max+Milvus raw 通过数最高（27/32），plus+Milvus 与 plus+local 均为 26/32，max+local 为 25/32；这只是每组合一次的非确定性快照，不能单独归因于模型或 Milvus/embedding，也不改变默认 local weighted 路线。Milvus 宿主健康通过把 health 端口从 `9091:9091` 调整为 `19091:9091`，保留内部端口和绑定数据卷。

## M26-v1 第二轮完整对照（2026-08-08）

- 固定条件与第一轮相同，四组均写入独立 `r2` 产物；Milvus 继续复用同一 clean collection，四项 runtime metadata 均校验为 `initial=195 / inserted=0 / final=195`、hash `8a8b6626...`。
- `qwen3.7-plus + local`：`25/32`，failed `7`，review_required `3`；triage execution_failed `5`、review_pending `3`、external_unavailable `4`；semantic observed_correct `9`、observed_wrong `1`、not_observed `4`、not_applicable `18`。
- `qwen3.7-plus + Milvus`：`25/32`，failed `7`，review_required `3`；triage execution_failed `4`、review_pending `3`、external_unavailable `5`；semantic observed_correct `10`、not_observed `5`、not_applicable `17`。
- `qwen3.7-max + local`：`26/32`，failed `6`，review_required `3`；triage execution_failed `4`、review_pending `3`、external_unavailable `1`；semantic observed_correct `10`、not_observed `3`、not_applicable `19`。
- `qwen3.7-max + Milvus`：`26/32`，failed `6`，review_required `3`；triage execution_failed `4`、review_pending `3`、external_unavailable `1`；semantic observed_correct `10`、not_observed `2`、not_applicable `20`。
- 两轮 raw 通过区间：plus+local `25–26`、plus+Milvus `25–26`、max+local `25–26`、max+Milvus `26–27`。这说明四组在这两次采样中处于相近区间，但样本仍只有每组 2 次；不能把 max+Milvus 的半分优势解释成稳定模型或 embedding 因果，也不改变默认 local deterministic/weighted。
- 新发现：第二轮中 `db_schema_003` 四组仍保持 schema_context alternatives mismatch，说明该问题具有重复性；`db_core_002`、`db_trace_002`、`db_multi_002` 等输出/计划失败在不同组间发生迁移，说明 LLM 生成存在非确定性。max 两组仍出现 44–68 秒级请求，需单独看作延迟风险而非语义失败。

## 8 次 M26-v1 diagnostic 审查（2026-08-08）

### 审查范围与前提

- 本次逐一核对第一、二轮的四组组合：`qwen3.7-plus / qwen3.7-max × local deterministic / Milvus`。每次都是同一份 `m26-v1` 的 32 条 raw cases（26 个独立语义组）、`new_text2sql + weighted`、SQLite deterministic oracle、LangFuse off、45s / retry0；共 **256 次 raw 执行**。
- 四次 Milvus 运行都使用同一 clean collection：195 docs、1024 维、相同 schema hash，metadata 为 `initial=195 / inserted=0 / final=195`。因此这次可以比较“同一输入在两种 schema 后端下的运行表现”，但不能把两轮的小样本波动归因成模型或 Milvus 的稳定因果效果。
- 本节审查的是已有 trace / report / triage，不重跑 LLM，不修改模型、检索、case contract 或默认配置。

### 先区分三个不能互相替代的数字

| 读数 | 聚合结果 | 它回答的问题 | 不能据此回答什么 |
|---|---:|---|---|
| runner raw pass | **206 / 256 = 80.5%**（单次 25–27 / 32） | 整个评测流程最终显示为 `passed` 的比例 | 不能直接叫作“模型 SQL 正确率”；其中混有非阻塞诊断题、manual 题、超时/外部不可用和不同评分维度。 |
| blocking pass | **177 / 200 = 88.5%**（单次 21–23 / 25） | 25 条 blocking 合同在流程层面能否通过；更接近日常核心链路的运行成功率 | 仍包含模型生成、计划、评分和外部服务，不能等同于“已拿到 SQL 后的语义准确率”。 |
| semantic answer（已观察） | **78 / 81 = 96.3%** | 在 semantic-answer 视图中，确实拿到可评分业务结果的样本里，有多少通过 | 该视图每轮只有 12 条、8 轮共 96 个机会：78 条正确、3 条已观察但错误、12 条 external unavailable、另 3 条没有语义结果但并非外部 unavailable。它不能外推成整套系统 96.3% 通过。 |

- 8 份 triage 还合计标出 **24 次 `review_required`**（每次 3 条）。它是与 runner `passed/failed` 正交的人工复核队列，不是“又多失败了 24 次”。典型例子是 `db_hard_003`：有些 run 的流程可通过，但 8 次都必须人工判断 SCD 语义，不能算为自动能力已经验证。
- 因此，当前最诚实的结论不是给出一个唯一“真实通过率”，而是同时报告：**端到端 raw 80.5%、核心 blocking 88.5%、已观察业务答案 96.3%**，并明确每个数字的边界。

### 哪些失败是稳定问题，哪些是随机波动

| case | 8 次结果 | 审查结论 |
|---|---:|---|
| `db_schema_003` | 0 / 8 raw pass | 每次都是 `schema_context_alternatives_no_match`。M26 已证明归因位置正确：同请求的 SchemaGraph 没有 alternatives 所需的 `gmv` 语义。这是 **schema 描述 / context 合同缺口**，不是“Milvus 没检到”或向量库整体失效的证据。 |
| `db_core_002` | 0 / 8 raw pass | M25 审计发现的整单退款 fallback 问题已被 counterfactual 暴露；后续真实运行仍在结果错误、额外投影列、QueryPlan/LLM timeout 间迁移。结论是：该题的端到端合同尚未稳定满足，不能因某一种错误表现消失就宣布修好。 |
| `db_multi_002` | 0 / 8 raw pass | 出现 root category 缺失、行数不匹配或超时。M26 的 CTE/RBAC 修复避免了错误安全拦截，但这 8 次没有形成“CTE 代表题端到端稳定通过”的证据。 |
| `db_hard_001`、`db_join_003` | 均 0 / 8 raw pass，且均 8 / 8 review | 分别表现为 root label / `products` 缺失或超时；它们是 non-blocking / review 诊断题，不能拿来压低核心 blocking 能力，也不能当作已经自动判错的业务答案。 |
| `db_hard_003` | 6 / 8 raw pass，8 / 8 review | SCD 手工题没有确定性最终 oracle；raw pass 只说明流程未阻断，不代表业务语义已自动验证。 |
| `db_join_001`、`db_trace_002` | 5 / 8、6 / 8 raw pass | 前者主要是 plan validation，后者主要少 `coupon_order_count`；属于值得定点复现的非稳定问题。 |
| `db_multi_001`、`db_multi_004`、`db_prompt_002` | 均 7 / 8 raw pass | 各有一次缺列或 LLM timeout，当前更像单次运行波动，不能先把它们固化成模型能力结论。 |

- 其余 **21 / 32** 条 raw cases 在 8 次中均通过；4 条安全 case 也都稳定按预期阻断。这个结果支持“本次 M26 的合同修复没有破坏已覆盖的安全基线”，但不构成全面安全证明。

### 失败原因的汇总：不要把不同队列硬加成一种失败

8 份 triage 一共给出 56 条“需解释项”；该队列包含 failed 和 review，故**不能**与 raw 的 50 次 failed 一一相等。按 triage 根因聚合如下：

| 根因 | 次数 | 含义 |
|---|---:|---|
| `external_service` | **25（44.6%）** | QueryPlan / LLM generation timeout 等外部可用性或响应时间问题，是当前最大的单类不稳定来源。 |
| `model_capability` | **17（30.4%）** | 已生成内容缺列、结果错误、计划不满足等；`db_core_002`、`db_multi_002` 是最需要认真看的重复案例。 |
| `retrieval_issue` | **8（14.3%）** | 全部对应 `db_schema_003` 的 SchemaGraph alternatives 缺口；应理解成待确认的 schema/context 设计问题，而非泛化的 local/Milvus 检索故障。 |
| `mixed_or_unknown` | **6（10.7%）** | 主要是 manual 或证据不足的复合情况，不能强行归责给模型。 |

### 本轮审查结论

1. **现有两轮足以排除几种常见误读**：不是单纯“max 更好”、也不是“Milvus 明显更好”；`db_schema_003` 不是向量库故障；`db_hard_003` 不能被 raw pass 当成自动语义成功；M26 修正了旧报告把 context 问题错归到最终输出列的问题。
2. **现有两轮还不足以宣布稳定能力排名或切默认**：每组合只有 2 次，四组 raw 区间高度重叠（plus local 25–26、plus Milvus 25–26、max local 25–26、max Milvus 26–27）。无论模型还是检索后端，都需要更多同口径重复样本才有资格谈稳定差异。
3. **真正优先要处理的是“证据与合同”而不是追单一分数**：`db_schema_003` 需要在确认业务预期后决定是否补齐 schema 语义；`db_core_002`、`db_multi_002` 需要保留为重复失败的定点问题；manual cases 需要人工定义何时才可转自动。上述任何一个都涉及长期 case/schema 合同，未获得新的确认前不应自行改动。

## 第二轮 Qwen plus 人工 SQL 审查（进行中，2026-08-08）

- 范围：先审 `m26-v1-r2-qwen37plus-local` 与 `m26-v1-r2-qwen37plus-milvus` 两份 32-case 冻结 run；不重跑 LLM。两份 case/trace/report/triage 已各自生成 M26 audit evidence pack，禁止跨 run 混用证据。
- 已发现的人工语义差异（尚未据此改代码或 case）：
  - local `db_join_001` 虽通过 join-path 自动检查，但 SQL 用 `refunds.id IS NOT NULL` 统计所有退款状态，漏了退款率合同要求的 `refund_status = 'completed'`；其结果 `0.2254` 也与同轮 Milvus 使用 completed 过滤后的 `0.0564` 明显不同。
  - local `db_hard_003` 的条件同时写了 `valid_to IS NULL OR valid_to > '2026-06-01'` 与 `valid_to != '2026-06-01'`。SQL 三值逻辑会让 `valid_to IS NULL` 的有效记录被第二个条件过滤，违反 SCD 半开区间合同；自动 manual pass 不能当作语义正确。
  - Milvus `db_prompt_002` 把窗口上界写为 `valid_from < '2026-06-30'`，而合同是 `< '2026-07-01'`；会漏掉 6 月 30 日生效的记录。该题只自动检查 SchemaContext，故是自动通过但人工 SQL 失败的候选。

### 已完成的两份审计卷宗

- 产物：`eval/reports/m26-v1-r2-qwen37plus-local-human-audit.{json,md}` 与 `eval/reports/m26-v1-r2-qwen37plus-milvus-human-audit.{json,md}`。每份都冻结该 run 的 case / trace / report / triage hash，并为 32 条 case 写入人工 verdict；没有执行新的 LLM 请求或 SQL scorer replay。
- **plus + local**：人工 verdict 为 pass **23**、fail **5**、unavailable **4**。自动与人工一致 26 条；4 条自动 failed 实际是无 SQL 的 external unavailable（`db_multi_002` / `db_multi_004` / `db_hard_001` / `db_join_003`）；另有 2 条自动 false positive：`db_join_001`（漏 completed 退款状态）、`db_hard_003`（SQL NULL 三值逻辑误排 ongoing price history）。其余 3 个人工 fail（`db_core_002` / `db_schema_003` / `db_trace_002`）与自动失败一致，但 `db_core_002` 的人工证据补充了“漏 completed + 整单退款 fallback”两层根因，自动报告当时只显示了额外 `product_id` 投影。
- **plus + Milvus**：人工 verdict 为 pass **24**、fail **3**、unavailable **5**。自动与人工一致 26 条；5 条自动 failed 是无 SQL 的 external unavailable（`db_core_002` / `db_multi_002` / `db_hard_001` / `db_hard_003` / `db_join_003`）；1 条自动 false positive：`db_prompt_002` 的 SCD 上界早一天。另两个人工 fail（`db_schema_003` / `db_trace_002`）与自动失败一致。
- **审计 adapter 新发现**：`eval.audit._automated_summary()` 只靠冻结 Markdown Score Summary 中是否存在 `rule:manual_review` 重建 `review_required`。外部失败会在 manual scorer 前结束，故源 report 的每轮 `review_required=3`，但审计卷宗重建为 local 1 / Milvus 0。人工审查仍以 triage 的 `review_pending` 为准；这是 audit 展示层的证据缺口，尚未修改代码或回写历史报告。

## 模块名称与改动文件清单

模块：M26 Diagnostic Human Audit / Eval Reconciliation。

- 审计证据层：`eval/audit.py`、`eval/run_audit.py`、`eval/reports/m26-qwen37plus-local-round2-audit*.{json,md}`。
- SQL 安全与保真：`engine/sql_guard/policy.py`、`engine/nl2sql/fidelity_contract.py`。
- Eval / triage / case contract：`eval/run_eval.py`、`eval/scorers/rule_scorers.py`、`eval/triage.py`、`eval/cases/database-upgrade-challenge.yaml`。
- 定点回归：`tests/test_m26_audit.py`、`tests/test_m26_targeted_contracts.py`。
- 过程素材：`docs/notes/m26-notes.md`。

## 阶段 1 注释小结（finish-module）

- 第 1 遍覆盖：对 9 个本模块业务/测试 Python 文件进行 AST 顶层扫描；所有新增或实质修改的类/函数均有中文 docstring，补写 `eval.audit._find_step()` 的证据缺口说明后，0 个非豁免缺失。
- 第 2 遍质量：重点复核并深化了四个新概念：SQL AST scope 与 CTE 临时名、窄 ratio 类型提升等价、SchemaGraph alternatives 与最终输出的边界、`failed` 兼容字段和正交队列；相应注释明确说明为什么不广泛放行 CTE、不做通用代数化简、不拿最终列代替 Context。
- 第 3 遍可读性：检查了 SQL Guard 的逐 scope 收集、fidelity 的 `NULLIF(..., 0)` 前置、Context alternatives 的 any-of 分支、triage 汇总字段和审计 legacy adapter；复杂路径均已有步骤或 ★ 边界注释，未发现连续核心逻辑无解释。
- 第 4 遍形式：新增注释中文为主，★ 仅用于安全/合同边界；YAML 的 `contract_adjustment` 直接记录业务口径原因。未发现需额外调整的分隔线或过密 ★。

## 阶段 2 最终验证快照（finish-module）

- P2 focused：`pytest tests/test_m26_targeted_contracts.py tests/test_m26_audit.py tests/test_m24_sql_plan_fidelity.py tests/test_m25_eval_trustworthiness.py tests/test_m4_nl2sql.py tests/test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m26-focused` → **62 passed, 1 warning, 73.16s**。
- 全仓：`pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m26-full` → **194 passed, 1 warning, 565.30s**。
- 格式：`git diff --check` 通过，无 whitespace error；Git 仅提示既有 LF→CRLF 工作区转换，不影响内容。
- 未运行完整 formal/challenge/diagnostic，也未执行新的 LLM 调用；M26 计划明确只做冻结 trace、确定性回归和 targeted replay。默认模型、检索、embedding、fusion、oracle、数据库结构和 seed 均未改变。

## 参考资料

- 项目内：M26 计划、M25 audit input、`AI_CONTEXT`/runbook/eval baseline/database state、M24 fidelity 和 M4 SQL Guard 既有实现与测试。
- 方法：复用 sqlglot `Scope` 表达“CTE 是临时命名空间”的边界；采用深 module / single source of truth 原则，未引入 LLM-as-Judge 或外部依赖。
- 外部资料：无。

## 遗留 / 后续

- 当前 audit record 对历史 M25 run 的自动 score 明细仍需从冻结 Markdown Score Summary 做有界迁移；未来 runner 如新增结构化 score artifact，应移除这条 legacy adapter，不能让 report 成为长期反向数据源。
- `db_hard_003` 仍保持 manual，M26 没有把它伪装成自动能力分；若未来要自动化，需另行确认业务题面、reference/result oracle 与新的 case contract version。
- M26 未重跑完整 LLM diagnostic；`m26-v1` 的新能力基线应在未来用户明确要求、并按单变量/可比性纪律执行时另建，不回写 M25 历史分数。
