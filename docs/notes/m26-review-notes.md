# M26 Review Handoff Notes

> 用途：供下一次会话快速接续 M26-v1 diagnostic 的人工 SQL 审查与后续规划。
>
> 范围：只记录已有证据和待决策项；**不代表已经批准修改 case、scorer、数据库 fixture、默认模型或检索配置**。

## 当前状态

- M26 已完成代码与收工；默认仍是 Qwen `qwen3.7-plus` + `inmemory/deterministic + weighted`，未因本轮诊断切换模型、Milvus、embedding、fusion、retry 或 timeout。
- `m26-v1` 已完成两轮四组完整 diagnostic：`qwen3.7-plus / qwen3.7-max × local / Milvus`，每组 2 次，每次 32 raw cases（26 个语义组），共 256 次 raw 执行。
- 本文重点的第二轮 Qwen Plus 两组已完成逐条人工 SQL 审查：
  - `m26-v1-r2-qwen37plus-local`
  - `m26-v1-r2-qwen37plus-milvus`
- 审查只读取冻结 case / trace / report / triage，不重跑 LLM；审计卷宗会校验同一 run 的输入 hash，禁止跨 run 混用证据。

## 先不要混淆的三种通过率

| 读数 | 全部 8 次聚合 | 正确含义 |
|---|---:|---|
| runner raw pass | 206 / 256 = **80.5%** | 整个评测最终显示 passed 的端到端比例；混有超时、人工题、非阻塞诊断题和不同 scorer。 |
| blocking pass | 177 / 200 = **88.5%** | 预先标记为 `phase3a_blocking: true` 的 25 条核心合同题的流程通过率；不是删失败题后计算。 |
| semantic answer observed pass | 78 / 81 = **96.3%** | 只看实际产出并进入确定性语义评分的业务答案；8 轮共 96 次机会，其中 78 正确、3 已观察错误、12 external unavailable、3 未形成语义答案但不属 external unavailable。不能外推成系统整体 96.3%。 |

- 每轮有 7 条预先定义的 non-blocking 题：`db_hard_001`、`db_hard_003`、`db_schema_003`、`db_join_003`、`db_plan_003`、`db_plan_004`、`db_prompt_002`。
- `review_required` 与 passed/failed 正交；`db_hard_003` 即使流程通过，也仍是 SCD 人工题，不能算作自动语义能力已验证。

## 已完成的人工审查

### 产物与验证

- local：`eval/reports/m26-v1-r2-qwen37plus-local-human-audit.{json,md}`
- Milvus：`eval/reports/m26-v1-r2-qwen37plus-milvus-human-audit.{json,md}`
- 两份卷宗都包含 32 条 case 的题面合同、候选 SQL、trace / transport 证据、自动 score、triage 和人工 verdict。
- 运行命令：`python -m eval.run_audit ...` 已成功各生成 32 条 records；不发起 LLM 或 scorer/SQLite replay。
- `git diff --check` 已通过；只有既有 Windows LF→CRLF warning。

### 人工结果（不是新的正式 baseline）

| 组合 | runner raw | 人工 pass | 人工 fail | 无 SQL / unavailable | 与自动不一致 |
|---|---:|---:|---:|---:|---|
| Qwen Plus + local | 25 / 32 | **23** | **5** | **4** | 2 个自动 false positive；4 个自动 failed 实为 external unavailable。 |
| Qwen Plus + Milvus | 25 / 32 | **24** | **3** | **5** | 1 个自动 false positive；5 个自动 failed 实为 external unavailable。 |

“人工 pass”只能表示：基于本次冻结证据，SQL / 正确阻断满足当前合同；它不是跨 seed、跨生产数据的最终真实正确率。

### 人工额外发现的自动 false positive

1. **local `db_join_001` — 退款率语义错误**
   - 自动仅检查 join path，故通过。
   - SQL 用 `refunds.id IS NOT NULL` 统计所有退款状态，漏掉固定业务口径 `refund_status = 'completed'`。
   - local 结果约 `0.2254`；同轮 Milvus SQL 带 completed 过滤，结果约 `0.0564`。
   - 结论：local 自动通过是 false positive，根因是模型 SQL 语义错误。

2. **local `db_hard_003` — SCD NULL 三值逻辑错误**
   - SQL 同时写 `(valid_to IS NULL OR valid_to > '2026-06-01')` 和 `valid_to != '2026-06-01'`。
   - 后一个条件会把 `valid_to IS NULL` 的持续有效记录过滤掉；正确半开区间只需前者。
   - 自动 manual pass 只代表流程未阻断，不能代表 SCD 语义正确。
   - 结论：false positive，模型 SQL 语义错误。

3. **Milvus `db_prompt_002` — SCD 时间上界早一天**
   - SQL 用 `valid_from < '2026-06-30'`，合同要求 `valid_from < '2026-07-01'`。
   - 会漏掉 6 月 30 日生效的记录。
   - 自动只检查 SchemaContext size，故通过。
   - 结论：false positive，模型 SQL 语义错误。

### 自动失败但人工能补充的结论

- **local `db_core_002`**：自动已因额外 `product_id` 投影失败；人工进一步确认 SQL 也漏了 `refund_status='completed'`，并且没有 `COALESCE(order_items.product_id, refunds.product_id)` 的整单退款 fallback。是明确 SQL 语义错误。
- **两组 `db_schema_003`**：稳定 `schema_context_alternatives_no_match`。wide-table 候选用了 `actual_amount/created_at`，而 case alternatives 要求看板 GMV 语义及 `snapshot_at`；这是 schema/context 合同缺口，**不能泛化表述为 Milvus 检索坏了**。
- **两组 `db_trace_002`**：计数公式语义正确，但输出 `coupon_usage_count` 不在 `coupon_order_count` 的允许别名（`usage_count` / `used_order_count`）中；按当前稳定输出合同判 fail。
- no-SQL 题应标为 unavailable，不应叫“模型答错”：local 的 `db_multi_002` / `db_multi_004` / `db_hard_001` / `db_join_003`，Milvus 的 `db_core_002` / `db_multi_002` / `db_hard_001` / `db_hard_003` / `db_join_003`。证据是 QueryPlan 或 SQL generation 的 `llm_generation_error` / timeout。

## 当前人工审查能做到什么，不能做到什么

### 已足够支持的判断

- 有候选 SQL 且业务合同明确时，能精确指出字段、过滤、join、聚合、时间边界、NULL 语义、输出 alias 等错误。
- 可区分“SQL 错误”和“服务失败导致无 SQL”。
- 可发现固定 seed 的自动 result_match 或结构 scorer 没覆盖的 false positive。

### 仍不能承诺的事情

- 无 SQL 的 timeout 只能定位到失败阶段，不能判断模型原本会写出什么 SQL。
- 现有结果主要基于固定 deterministic seed 与少量输出样本；没有自动为每条 SQL 构造边界反例，仍可能有“当前 seed 恰好通过”的隐藏错误。
- triage 的 `root_cause` 是证据驱动归因，不是外部服务、网络、代理、模型负载之间的因果证明。
- 审查 verdict 由 Codex 一次性判定，虽带证据，但没有独立第二审或自动 mutation 验证。

## 新发现：审计 adapter 的 review 证据缺口

- 原始 eval report 每轮都记录 `review_required=3`。
- `eval.audit._automated_summary()` 目前只从冻结 Markdown Score Summary 是否出现 `rule:manual_review` 重建 review 状态。
- 如果 LLM 在 manual scorer 前超时，Score Summary 不会出现该 rule；所以此次审计卷宗重建为 local 1、Milvus 0，而源报告实际都是 3。
- 人工审查时应以 triage 的 `review_pending` 和源 report 为准。**这只是已发现的审计展示层问题，尚未改代码、回写历史审计或改变统计口径。**

## 运行可靠性背景

- 当前 8-run triage 需解释项按根因聚合：external_service 25、model_capability 17、retrieval_issue 8（均为 `db_schema_003` context 合同）、mixed_or_unknown 6。
- Qwen max 出现过 44–68 秒的成功请求；当前 45 秒配置与“最终 HTTP 200 但耗时很长”并不矛盾，流水线有 QueryPlan 和 SQL generation 多段调用。
- DeepSeek 也曾有同类外部可用性问题：M25 DeepSeek `deepseek-v4-flash` 的完整 diagnostic 为 25/32，triage 有 external_service 3、QueryPlan 3、not_observed 5。不要依据当前少量 run 断言 Qwen 或 DeepSeek 天生更容易超时。

## 下一步的候选优化（需先确认，不要自行实施）

这些选项会影响长期评测证据结构、case / fixture 合同或历史兼容性，下一会话应先向用户说明取舍并取得确认。

1. **结构化证据补全（建议先做）**
   - runner 直接落盘结构化 `score_details`、真实 `review_required`、执行摘要及 reference result hash/diff，避免人工审计反解析 Markdown。
   - 收益：修复 review 证据缺口，提高卷宗可靠性；风险较低，但需定义新 artifact 的版本与历史兼容策略。

2. **审查结论细分（建议与 1 一起讨论）**
   - 将 audit 结论显式分为业务 SQL 错误、输出合同错误、schema/context 错误、external unavailable、manual pending 等，而非仅 pass/fail。
   - 收益：避免把超时、别名契约和业务逻辑混成单一“失败率”；代价是需要决定对历史报告的兼容展示。

3. **高风险 SQL 的 deterministic counterfactual / mutation 验证**
   - 为退款 completed 状态、整单退款 fallback、SCD NULL / 时间边界、输出别名等构造最小反例。
   - 收益：把人工发现变成未来自动防回归的测试；风险：会扩展 eval case、SQLite fixture 或 case contract，必须先确认业务口径与是否升级 contract version。

4. **固定人工审查覆盖策略**
   - 每次 diagnostic 后审全部 failed、全部 manual、全部高风险指标，并对自动通过题做固定比例抽查；高风险 case 可全量审。
   - 收益：持续捕捉 false positive；代价是时间成本，需要决定是否作为人工流程规范还是写入 runner / CI。

## 新会话建议阅读顺序

1. 本文件。
2. `AGENTS.md`、`docs/state/AI_CONTEXT.md` 及其必读的 `runbook.md`、`eval-baselines.md`、`database-current-state.md`。
3. 本轮审计报告：local / Milvus `*-human-audit.md`。
4. `docs/notes/m26-notes.md` 的“8 次 M26-v1 diagnostic 审查”和“第二轮 Qwen plus 人工 SQL 审查”章节。
5. 若准备改长期证据结构或 case 合同，再读 `docs/phase3b-langfuse-plan-v6.md` 的 M26 约束，并先提出确认门。
