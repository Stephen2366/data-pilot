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
