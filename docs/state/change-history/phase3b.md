# DataPilot AI Context Changelog — Phase 3B

> 本文件保存 Phase 3B 的完整模块档案、实验记录和历史取舍，按时间倒序排列。当前项目状态以 `docs/state/AI_CONTEXT.md` 为准；跨阶段索引见 `docs/state/CHANGELOG_INDEX.md`。
>
> 默认先按模块号、日期或关键词定位，再读取相关章节，不要无差别全文读取。新结论修正本阶段旧判断时，应在旧条目原位添加 `⚠️ 注`。

标题标签：

- `[模块任务]`：功能、架构、默认行为、安全口径、评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM eval、smoke 或会影响路线判断的实验结论。
- `[小修]`：文档措辞、口径同步、注释补充、轻量整理；只需简写，不要求完整模板。

「变更记录」：小修可以只写一段话；较大的任务建议包含：改动范围、关键记录（比如关键决策、决策原因、实验结果、新发现、用户做出的选择等）、参考资料、验证快照、遗留/后续。

同一模块 / 同一阶段内连续的小修（中间没有被 [模块任务] / [实验] 等其他类型条目隔开时），合并到一个 [小修] 小节。

## 变更记录（新的在上）

### [模块任务] M28 Text2SQL 收尾确定性修复（2026-08-10）

- **改动范围**：因本模块没有单独起始 commit，范围依据为 `git status --short` 与 `git diff --name-only`；逐项对照 M28 notes 后归并为 `engine/nl2sql/prompt.py`、`eval/{contracts,catalog,environment,run_eval}.py`、`eval/cases/catalog/*`、相关 `tests/*`，以及 `docs/{notes,state,dev-log}.md`。工作树中另有用户/其他工具修改的 `docs/ref-discussion/RAG 的讨论.md` 与 `.codex/skills/finish-docs/SKILL.md`，均不属于 M28，未触碰。
- **关键记录**：用户确认实施审查中“建议现在处理”的四项问题。canonical contract 升为 `m27-v3`：Schema Context 将物理字段、metric key、输出 alias 分离，并在 catalog load 阶段校验当前 domain schema 可满足；修正 5 条错位合同，渠道 GMV dashboard 增加 Result/Output，避免零行假通过。`orders_wide.paid_at` 负责业务月份，`snapshot_at/batch_id` 只选快照版本；未改数据库 schema、seed 或 oracle snapshot。
- **关键记录**：`SQLiteRunEnvironmentFactory` 恢复一轮 EvalRun 只构建一次 Schema vector index，通过 `app.state` 注入全部 Scenario，结束时关闭；runtime identity 新增 `schema_vector_index_reuse` 与 Milvus initial/final row count。pytest autouse guard 默认禁止未 mock 的真实 provider；legacy 测试显式走旧路径，新 pipeline/smoke 显式注入 fake。旧 v1/v2 artifact 继续只读兼容。
- **参考资料**：`docs/notes/m28-text2sql-review-notes.md`、M27 计划/笔记、四份 state 事实源、当前 Text2SQL/Schema Retrieval/Eval/Review/Trace 实现与既有 artifact/checkpoint；未新增外部资料。
- **验证快照**：聚焦 M27/Review/数据库测试 `28 passed`；legacy API/Trace `22 passed`；M18 smoke `4 passed`；新 pipeline `8 passed`；全仓确定性 pytest `223 passed, 1 warning`（既有 Starlette/httpx deprecation，`464.31s`）。另通过 `compileall` 与 `eval.run_eval --help`。全程无真实 provider 调用。
- **遗留/后续**：Text2SQL 可以暂时收尾并进入 RAG。F5 Projector 完整性、F6 Review 长期证据、F7 Cloud 脱敏不阻塞阶段切换；F7 必须在 RAG/Hybrid 重新启用 LangFuse Cloud 前处理。未切换模型、检索、embedding、数据库、oracle、timeout/retry 或产品 API 默认，未运行真实 LLM Eval；现有 v2 快照不与 v3 直接比较。

### [实验] M27 Stress / Database Exception：Qwen plus + Milvus（2026-08-10）

- 用户各授权一次：Stress `m27-stress-20260809-qwen37plus-milvus-01`（9 logical / 9 physical）与 Database Exception `m27-database-exception-20260809-qwen37plus-milvus-01`（7 / 7）。两轮都固定 Qwen `qwen3.7-plus`、Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim、clean collection `datapilot_schema_docs_m27_qwen37plus_qwenemb_20260809_164000`、195-doc hash `8a8b6626...`、weighted、45s/retry0、SQLite deterministic oracle、LangFuse off；新 artifact 已完整记录 runtime identity。
- Stress 全部 assertion 为 `7 passed / 14 failed / 4 not_observed`，7 completed / 2 external unavailable；Database Exception 为 `4 / 4 / 11`，3 completed / 4 external unavailable。两套 suite policy 的 required 都是 `0 / 0 / 0`，Gate `inconclusive` 反映没有 required 硬门结论，不是“业务硬门失败”。均为单轮 advisory 证据，不作模型 / Milvus 因果结论、不登记长期 baseline。未改任何默认配置。

### [小修] M27 文档与状态同步（2026-08-09）

- **Eval 账本分层**：`eval-baselines.md` 不再按 v1 / v2 或模块编号持续新增快照标题，改为「当前有效实验快照 → 正式长期基线 → 历史实验记录」：仍可支持当前路线判断的运行留在前者，用户指定的 completed run 才进入长期基线，合同或条件已过时的记录移入历史。首个 v2 Core 明确标为“过渡证据”，不是严格 Milvus/P1 对照；四条 v1 Core 转为历史追溯。仅整理账本结构，未运行真实 LLM、未改合同、分母、Gate 或默认配置。
- **数据库事实文档对齐**：`database-current-state.md` 保留 14 表、指标、seed 与改库事实，但移除了旧 Phase 3A / M23 Eval 入口、`--cases` 命令和过时的异常专项映射；当前评测统一链接到 M27 catalog、runbook 和 eval-baselines。补充事实来源分工，以及 `orders_wide` 的月度 `snapshot_at` 与星型明细回退规则；重复的数据质量说明收敛为一张“应该怎么查 / 容易错在哪里”表。未运行数据库或真实 LLM，未改 schema、seed、指标、oracle 或默认配置。
- **Milvus runtime identity 与速查收敛**：resolved runtime identity 新增 embedding 模型/维度、Milvus collection、schema document count/hash，确保未来 M27 artifact 能区分同为 Milvus 的不同语料和 embedding 条件；只读取配置与 domain pack，不连接或写入 Milvus。首个 v2 Core 早于该字段扩展，已在 eval-baselines 标为过渡快照。`schema-retrieval-milvus-embedding.md` 移除失效 legacy CLI / 数字，明确 DashScope/Qwen 是唯一文档化 M27 Milvus 路径，SiliconFlow 仅保留实现历史。M27 foundation/review `23 passed, 1 warning`；未调用真实 LLM、未切默认配置。
- **临时目录统一与 Gate 指引**：用户确认将 M27 checkpoint 与所有 AI 临时产物统一到 `.agent_work/temp/`：`eval.run_eval` 默认 checkpoint 根目录已迁移，旧临时目录的 66 个直接子项已移动到共享目录；长期 artifact/report/trace 不移动。runbook 同时补齐前台等待超时的精确检查路径，以及 `passed` / `failed` / `inconclusive` 的操作边界。未调用 LLM、未改变 Eval 合同、默认模型或可靠性配置。

### [实验] M27 v2 Core：Qwen plus + Milvus（2026-08-09）

- 用户授权一次运行 `m27-core-20260809-qwen37plus-milvus-02`：Qwen `qwen3.7-plus`、Milvus + DashScope `qwen3.7-text-embedding` / 1024 dim、weighted、45s/retry0、SQLite deterministic oracle、LangFuse off，19 logical / 19 physical。
- completed artifact 结果为 required `28 passed / 0 failed / 6 not_observed`、Gate `inconclusive`。17 个 Scenario 完成；`june_product_sales_top5` 与 `june_product_refund_rate_ranking` 都在 QueryPlan timeout、没有 candidate SQL，P0 正确将各自 Result / Output / Schema Context 投影为 `external_unavailable / not_observed`，没有伪造业务失败。
- P1 的两项相关断言本轮通过：`june_actual_amount_sum` metric mapping、`june_channel_gmv_dashboard` schema context；后者的 QueryPlan 含 `orders_wide.snapshot_at`、`orders_wide.order_amount` 和 `gmv`。各仅一轮，不作稳定性、模型、Milvus 或 embedding 因果结论，也不切默认配置。
- 这是当前首个 M27 v2 Core 快照，已列入 eval-baselines 的“当前可比较快照”，但未由用户指定为正式长期 baseline；不得与 v1 `29/5/0` 直接比较。
- **⚠️ 注（2026-08-10）**：M28 发现 dashboard 将抽取时间 `snapshot_at` 误作业务月份且只有 Context 断言，旧 run 的该项通过不能证明结果正确；当前已由 `m27-v3` 改为 `paid_at` 并补 Result/Output。该 v2 run 现仅作修复前历史证据。

### [模块任务] M27 v2：P0 timeout 判卷修正、P1 Core 定向优化与 API 默认迁移（2026-08-09）

- **改动范围**：M27 canonical contract 升为 `m27-v2`；Evaluator 从 QueryPlan trace 读取 transient `error_subtype`，将无候选答卷的 timeout/network/429/5xx 记为 `external_unavailable`；metric scorer 统一带表前缀与裸字段；渠道 GMV 提升 `gmv` metric 召回并补 `orders_wide.snapshot_at` 计划提示。普通 API 默认切到 `new_text2sql`，Eval adapter 对新旧路径都显式传 `force_new_pipeline`，legacy baseline 保持显式 `false` 回退。
- **关键记录**：用户确认这次 P0 可以改变正式分母/Gate，因此 v1 的 timeout 空答卷不再伪装成业务 failed；相关 assertion 变为 `not_observed`，required Gate 为 `inconclusive`。这是正式可比性变化，故不重写旧 artifact，而是冻结为 v1 追溯快照；review 保持 v1/v2 artifact 只读兼容。`net_revenue = SUM(orders.actual_amount)` 不是业务 binding 错误，修的是命名空间比较；渠道 GMV 不放宽 Scenario/scorer，而是让正确 metric 与快照时间口径进入上下文。
- **验证快照**：`tests/test_m27_foundation.py tests/test_m27_review.py` 为 `22 passed, 1 warning`（含 v1 artifact 只读 review 兼容）；新 API 默认/显式 legacy 测试为 `2 passed, 1 warning`；`tests/test_phase3a_eval.py` 为 `23 passed, 1 warning`；`eval.run_eval --help` 显示 `m27-v2`。warning 均为既有 Starlette/httpx deprecation。未调用真实 LLM，未改模型、检索、embedding、数据库、oracle 或 45s/retry0 默认可靠性配置。
- **参考资料**：`docs/notes/m27-notes.md`「Core 失败复盘与 P0/P1 实施」、`docs/notes/m27-plan.md` §13、v1 冻结快照 artifact（`eval/reports/m27-artifacts/`）、既有 runner/scorer 实现。
- **遗留/后续**：尚未运行 M27 v2 真实 Core，也未登记新的正式长期基线；将来运行须单独授权，且不可将 v2 与 v1 的 `29 passed / 5 failed / 0 not_observed` 直接升降比较。M27 仍待 `accept-module`。
- **⚠️ 注（2026-08-10）**：本节的 `orders_wide.snapshot_at` 月份 guidance 已被 M28 证实为业务语义错误；当前合同为 `m27-v3`，业务月份使用 `paid_at`，v1/v2 artifact 均只读保留。

### [小修] 真实 Eval 的单次执行纪律（2026-08-09）

- runbook 明确：一次用户授权只创建一个 `run_id`；前台等待超时不等于 Eval 停止，必须先检查同 run 的 manifest/checkpoint/artifact。普通 Smoke/Core 不得临时用 `.ps1`、隐藏 PowerShell、计划任务或额外终端重跑；只有原 run 明确失败且没有 completed artifact，才可记录原因后新建 run。

### [实验] M27 Core：Qwen 3.7-max local / Milvus 对照（2026-08-09）

- 用户授权后，当前可比较快照为 local `m27-core-20260809-qwen37max-local-06` 与 Milvus `m27-core-20260809-qwen37max-milvus-02`：均执行 19 logical / 19 physical，required assertion 均为 `29 passed / 5 failed / 0 not_observed`、Gate `failed`。
- Milvus 固定 DashScope `qwen3.7-text-embedding`、1024 dim、weighted，使用 195-doc clean collection（description hash `8a8b6626...`）。该单次配对只说明本轮未观察到 local/Milvus 改变结果；不推断模型、检索或 embedding 因果，不改默认配置。

### [模块任务] M27 Review Evidence Hardening（2026-08-09）

- **改动范围**：将旁路 review bundle 升为 `m27-review-bundle-v2`，为 completed artifact 与每条短期 checkpoint 写入 SHA-256；新增 `python -m eval.run_review --verify-bundle <review.json>` 只读校验入口、结构化人工分类和 review 汇总。同步 runbook、cases README、M27 eval baseline 说明与过程 notes。
- **关键记录**：普通业务题若没有 candidate SQL，只能写 `insufficient_evidence / execution_evidence_unavailable`，不能凭空判模型答对或答错；`safety_block`、`expected_rejection` 则可凭明确拦截证据复核。分类被限制为正确、正确拒绝、业务 SQL / 输出合同 / Schema Context / 其他合同错误或执行证据不可用，并和 verdict / assertion 合同交叉校验。
- **覆盖策略**：Core / Stress 后复核全部自动失败、退款/SCD/金额/时间/递归等高风险合同，并抽样少量自动通过题。review 仍是定位证据，绝不接入 EvalRun、自动分母、Gate 或 CI。既有 v1 review 保留为没有来源哈希的历史材料；需要新保障时按原 run 生成 v2，不改写自动 artifact。
- **反事实复用**：M26 指出的 completed 退款 / 整单退款 fallback 已由 `tests/test_m25_eval_trustworthiness.py` 与 `tests/test_m26_targeted_contracts.py` 的 SQLite 最小反例覆盖；本轮确认 M27 canonical SQL 沿用该 `COALESCE` 合同，不复制同义测试。
- **验证快照**：review、M27 foundation/counterfactual 与 M25/M26 退款保护共 `37 passed, 1 warning`；`eval.run_review --help` 成功展示只读校验入口；`git diff --check` 通过。warning 为既有 Starlette/httpx deprecation；未调用真实 LLM，未改默认运行配置。

### [实验] M27 Core：Qwen plus local / Milvus 对照（2026-08-09）

- 用户授权各运行一次 `qwen3.7-plus + local` 与 `qwen3.7-plus + Milvus` 的 M27 Core。local 已完成：`m27-core-20260809-qwen37plus-local-01` 固定 inmemory deterministic/weighted、45s/retry0、SQLite deterministic seed、LangFuse off，19 logical Scenario / 19 physical attempts。
- 结果：Core Gate `failed`；required assertion `29 passed / 5 failed / 0 not_observed`。失败为 `june_product_refund_rate_ranking` 的 result/output/schema_context、`june_actual_amount_sum` 的 metric_mapping、`june_channel_gmv_dashboard` 的 schema_context；无 external unavailable / pipeline error。
- Docker daemon 恢复后，Milvus `m27-core-20260809-qwen37plus-milvus-01` 已完成：固定 DashScope `qwen3.7-text-embedding`、1024 维、weighted 和新的 collection `datapilot_schema_docs_m27_qwen37plus_qwenemb_20260809_164000`。实际 collection 为 195 entities、1024 维、description hash `8a8b6626...`，满足当前 corpus 的 clean 条件。
- Milvus 结果与 local 完全相同：19 logical Scenario / 19 physical attempts，required `29 passed / 5 failed / 0 not_observed`，Gate `failed`；5 条失败的 Scenario、assertion 和 reason 均一致。该配对只有各一次，且真实 LLM 有非确定性；因此结论仅为“本轮未观察到 Milvus 改变 assertion 结果”，不作 embedding/检索因果、稳定性或默认切换结论。

### [模块任务] M27 Codex Review Bundle（2026-08-09）

- **改动范围**：新增 `eval/review.py` 深 module、`eval/run_review.py` CLI 与 `tests/test_m27_review.py`；同步 M27 runbook / cases README / state 档案。它是用户在 M27 原计划“暂不实现人工 verdict 工作流”之外明确授权的旁路增补，不改 formal case、EvalRun schema、分母、Gate 或旧 M26 audit。
- **关键记录**：review bundle 以 completed M27 artifact、同 run 的短期 raw checkpoint、canonical catalog 三者的 `(run_id, scenario_id, replicate_id)` 和 assertion identity 对齐为前提。它仅输出脱敏 candidate/reference SQL、最多 3 行结果 preview、trace 摘要和合同；缺 checkpoint / 身份不一致即失败，不由 Markdown 猜造人工证据。Codex/manual verdict 固定为 `pass/fail/insufficient_evidence`，另记录 confidence、reason、evidence 与 auto/manual reconciliation，始终独立于自动评分事实。
- **验证快照**：`pytest -q tests/test_m27_review.py tests/test_m27_foundation.py tests/test_phase3a_eval.py --basetemp=.agent_work/temp/pytest-m27-review-final`：`38 passed, 1 warning`；warning 为既有 Starlette/httpx deprecation。review CLI 已对既有 completed M27 输入完成定向校验；未调用新的真实 LLM。
- **遗留/后续**：review bundle 依赖短期 checkpoint，清理后不能重建，这符合默认不长期存完整 rows/prompt 的安全策略。若未来确需长期独立人工复核，应另行确认保留期、访问控制和更严格的 SQL / 结果样本脱敏策略；不得把它接入 Gate 或改写旧 M26 audit。

### [模块任务] M27 Diagnostic / Eval Case 体系优化（2026-08-09）

- **改动范围**：新增 `m27-v1` typed contract/catalog/environment/ports/assertion/evaluator/projector/reporting/selector 模块、28 条 canonical Scenario、三个 selector、反事实与接口测试；`engine/nl2sql/pipeline.py` 补安全的 QueryPlan `plan_steps` 摘要；`eval.run_eval` CLI 切换为 M27 Interface。完整过程素材见 `docs/notes/m27-notes.md`。
- **关键记录**：用户确认 A1–A3 后，按 P0 migration matrix 将旧 formal/challenge/diagnostic 的 42 raw case、26 个旧语义组治理为 28 个唯一 Scenario；用户随后授权直接完成 B 门确定性实施。一个 `(run, scenario, replicate)` 最多一次 Pipeline 调用，所有 assertion 共享同 snapshot Oracle evidence。旧默认 `ok` 的 metric/join/plan/trace 已替换为真实 pure scorer；Reliability replicate 归约为一个逻辑分母；gate 由 projector 推导，`inconclusive` exit policy 与 EvalRun 分离。
- **业务/安全边界**：商品退款率采用完整排名而非旧 Top1 projection；SCD 开放 `valid_to`、completed refund、递归子类都以 SQLite counterfactual 证明。completed artifact 仅保存 allowlist response/trace 摘要、row count 与 result fingerprint，不保存 rows/prompt/answer/凭证；`interrupted` 与遗留 `running -> abandoned` 不能进入 projector。旧 M26 artifact、YAML、报告与 audit 不覆盖、不重算。
- **验证快照**：M27 foundation + counterfactual `14 passed, 1 warning`；legacy Eval 合同 `37 passed, 1 warning`；pipeline + M27 `21 passed, 1 warning`；全仓 `208 passed, 1 warning`（509.65s）；`git diff --check` 通过。warning 均为既有 Starlette/httpx deprecation。
- **参考资料**：`m27-plan.md`、M26 notes、项目 state/runbook/database facts、现有 runner/scorer/trace/audit 实现；未检索或照搬外部平台。
- **遗留/后续**：M27 未验收（待 `accept-module`）。真实 LLM `m27-v1` 基线仍须用户单独确认范围/调用数/成本；不要将其与旧 25/32、26/32 等口径直接升降比较。LangFuse 目前只构造严格 allowlist payload，实际上传仍需显式授权。**⚠️ 注（2026-08-09）**：后续 P0 将合同升为 `m27-v2` 并修正 timeout 语义。**⚠️ 注（2026-08-10）**：M28 又将当前合同升为 `m27-v3`，v1/v2 artifact 均只读保留，新的真实基线必须按 v3 单独登记。

### [审查] M26-v1 第二轮 Qwen plus 人工 SQL 审查（2026-08-08）

- 范围：对 `m26-v1-r2-qwen37plus-local` 与 `m26-v1-r2-qwen37plus-milvus` 两份冻结 run 各 32 条逐题人工审查，不重跑 LLM、不改代码或 case；每份生成独立 audit evidence pack（`eval/reports/m26-v1-r2-qwen37plus-{local,milvus}-human-audit.{json,md}`），禁止跨 run 混用证据。
- 人工 verdict：plus+local 为 pass 23 / fail 5 / unavailable 4；plus+Milvus 为 pass 24 / fail 3 / unavailable 5。两组自动与人工一致均 26 条；自动 failed 中各有 4–5 条是无 SQL 的 external unavailable（QueryPlan/LLM timeout），不属于语义错误。
- **发现 3 条自动通过但业务语义有误的 SQL（已记录，未修复）**：① `db_join_001`（local）用 `refunds.id IS NOT NULL` 统计全部退款状态，漏退款率合同的 `refund_status = 'completed'` 过滤，结果 `0.2254` 与同轮 Milvus completed 过滤后的 `0.0564` 明显不同；② `db_hard_003`（local）同时写 `valid_to IS NULL OR valid_to > '2026-06-01'` 与 `valid_to != '2026-06-01'`，SQL 三值逻辑会误过滤 `valid_to IS NULL` 的现行记录，违反 SCD 半开区间合同；③ `db_prompt_002`（Milvus）窗口上界写 `valid_from < '2026-06-30'`，合同为 `< '2026-07-01'`，漏掉 6 月 30 日生效记录。三者都说明"runner 自动通过"不能直接当业务语义正确。
- 审计 adapter 证据缺口：`eval.audit._automated_summary()` 只靠冻结 Markdown Score Summary 中是否存在 `rule:manual_review` 重建 `review_required`，与 triage 的 `review_pending` 不一致（该两组重建为 local 1 / Milvus 0，源 report 每轮为 3）；人工审查以 triage `review_pending` 为准。这是 audit 展示层的证据缺口，尚未修改代码，后续 runner 补结构化 score artifact 时应一并处理。
- 边界：以上发现均未回写历史报告或改动正式口径；是否修 case / scorer / schema 需用户另行确认。

### [实验] M26-v1 第二轮模型/检索对照（2026-08-08）

- 用户要求在第一轮基础上重复四组完整 diagnostic：Qwen `qwen3.7-plus + local`、`qwen3.7-plus + Milvus`、`qwen3.7-max + local`、`qwen3.7-max + Milvus`。固定 M26-v1、32 条、45s/retry0、weighted、SQLite oracle、LangFuse off；四组均生成独立 `r2` trace/report/triage。
- 第二轮结果：plus+local `25/32`（triage execution 5 / review 3 / external 4）；plus+Milvus `25/32`（4 / 3 / 5）；max+local `26/32`（4 / 3 / 1）；max+Milvus `26/32`（4 / 3 / 1）。两组 Milvus 的 collection runtime metadata 均为 195 initial、0 inserted、195 final，hash `8a8b6626...`。
- 与第一轮合并看，四组 raw 区间分别为 plus+local `25–26`、plus+Milvus `25–26`、max+local `25–26`、max+Milvus `26–27`。两轮结果支持“当前采样下四组接近、max+Milvus略高”的描述，不支持稳定模型/embedding 因果或默认切换；每组仍只有 2 次。
- 诊断层新证据：`db_schema_003` 四组第二轮仍归因于 schema_context alternatives mismatch，重复性较强；`db_core_002`、`db_trace_002`、`db_multi_002` 等失败在组合间迁移，体现真实 LLM 输出非确定性。max 两组再次出现 44–68 秒级请求，需按延迟风险记录，不直接算语义错误。

### [实验] M26-v1 模型/检索追加对照（2026-08-08，已完成）

- 用户要求追加三组完整 diagnostic：Qwen `qwen3.7-plus + Milvus`、Qwen `qwen3.7-max + local`、Qwen `qwen3.7-max + Milvus`。三组均固定 M26-v1、32 条、45s/retry0、weighted、SQLite oracle、LangFuse off；结果分别为 `26/32`、`25/32`、`27/32`，均保留独立 trace/report/triage。
- `qwen3.7-max + local` triage 为 execution_failed `5`、review_pending `3`、external_unavailable `3`；`qwen3.7-plus + Milvus` 为 `3/3/4`；`qwen3.7-max + Milvus` 为 `3/3/3`。三组都仍观察到 `db_schema_003` alternatives mismatch；max+Milvus 还记录到个别 45–73 秒的高延迟请求，但最终 HTTP 200。
- 两组 Milvus 均复用 clean collection `datapilot_schema_docs_m25_qwen37plus_qwenemb_20260807_192300`，195 docs、1024 维、hash `8a8b6626...`，initial/final row count 均 195、inserted `0`，因此没有把 collection 重新灌库差异混入模型比较。为绕过 Windows 保留端口 `9091`，仅把宿主 health 映射调整为 `19091:9091`，内部端口和绑定数据卷保持不变。
- 解释边界：同轮 raw 通过数为 max+Milvus `27/32`、plus+Milvus `26/32`、plus+local `26/32`、max+local `25/32`；每组合只跑一次，且 max 存在明显响应时延波动，不能据此断言稳定的模型或 Milvus/embedding 因果，也不改变默认 local deterministic/weighted。

### [实验] M26-v1 完整 diagnostic（2026-08-08）

- 用户明确授权后，固定 Qwen `qwen3.7-plus`、local deterministic/weighted、45s/retry0、SQLite oracle、LangFuse off，按 `m26-v1` 运行 challenge + diagnostic extra 共 32 条；产物为 `eval/traces/m26-v1-qwen37plus-local-diagnostic-traces.jsonl`、对应 report/triage，以及 `eval/reports/m26-v1-vs-m25-round2-triage-compare.md`。
- 结果为 raw `26/32`、failed `6`、review_required `3`；triage 队列为 execution_failed `4`、review_pending `3`、external_unavailable `4`。semantic status：observed_correct `10`、observed_wrong `1`、not_observed `4`、not_applicable `17`。这不是稳定能力基线，只是新合同的一次诊断快照。
- 新证据：`db_core_002` 真实 result mismatch，确认审计指出的整单退款 fallback 缺口；`db_schema_003` 已从旧 output-column 误归因改为真实 SchemaContext alternatives 不匹配；`db_hard_002` ratio 通过，未重现 `* 1.0` fidelity 假阴性。CTE 代表题 `db_multi_002` 仍 QueryPlan external failure，没有 SQL，因此不能用本轮证明 CTE 端到端收益。
- 解释边界：M25 round2 为 `28/32`、M26-v1 为 `26/32`，不能直接说退化，因为 case contract、scorer 和真实 LLM 运行都发生了变化；本轮没有做第二次重复、模型 A/B、embedding A/B 或 retry 实验。

### [模块任务] M26 Diagnostic Human Audit / Eval Reconciliation（2026-08-07）

- **改动范围**：新增冻结评测审计入口 `eval/audit.py` / `eval/run_audit.py`、M25 round2 的 audit / verdict artifacts、SQL Guard CTE scope 解析、SQL Plan Fidelity 窄等价规则、SchemaGraph alternatives scorer、triage 状态与报告、两个高风险 case 合同和定点回归测试；过程素材见 `docs/notes/m26-notes.md`。
- **审计结论**：固定 M25 Qwen 3.7-plus + local round2 的 trace / report / triage，以 manifest hash 锁定输入；32 raw cases 聚合为 26 个 semantic groups。人工 verdict 后 raw reconciliation 为 26 agree、1 false positive、4 status mismatch、1 unresolved；其中 26 pass、2 fail、3 external unavailable、1 evidence insufficient。历史 Markdown 只保留 Score Summary，audit 因而用只读兼容 adapter 提取历史分数，未回写或重算 M25 结果。
- **用户确认后的 P2 定点修复**：SQL Guard 改为 sqlglot scope 内区分 CTE alias 与物理表，CTE 内访问的物理表 / 敏感字段仍执行严格 RBAC；Fidelity 仅允许 `NULLIF(..., 0)` 分母不变且分子仅多出 `* 1.0` 的 ratio 类型提升，不引入通用代数等价；SchemaGraph scorer 真正消费同一 trace 的 `expected_tables_alternatives`；`failed` 保持向后兼容，另增加正交的 `execution_failed` 与 `review_pending`。
- **合同与反例**：`db_hard_001` 明确为数码电子一级类目的 `item_gmv`；`db_hard_003` 仍保留 manual，但明确 SCD 半开区间与名称排序；`db_core_002` 增加 SQLite 反事实，证明漏掉整单退款 `COALESCE(oi.product_id, r.product_id)` 会在非巧合数据上答错。
- **验证快照**：P2 focused `62 passed, 1 warning`；全仓 `194 passed, 1 warning`。warning 均为既有 Starlette/httpx deprecation。未运行新的完整真实 LLM diagnostic、未更改模型 / retrieval / LangFuse / 数据库默认值，也没有覆盖冻结 M25 历史报告。
- **遗留/后续**：`db_hard_003` 仍需人工 review；历史 M25 报告缺结构化 score detail，audit adapter 仅用于该冻结证据；待用户人工检查后再执行 `accept-module`，新的 M26 合同完整 LLM 基线应在后续单独授权的运行中建立。

### [模块任务] M25 Eval Trustworthiness, Reliability & Evidence-Grounded Attribution（2026-08-07）

- **改动范围**：新增 `engine/nl2sql/llm_call.py` 深 module、`semantic_group_id` / `case_contract_version=m25-v1`、两轴 triage 与六类 report views；同步 LLM 配置/pipeline trace、三套主 case、退款率事实/seed、focused tests、runbook 与模块 notes。完整清单见 `docs/notes/m25-notes.md`。
- **关键决策**：用户确认正式题面补齐列/时间/排序/LIMIT，退款率采用 completed 退款去重订单分子，平均售价保持记录算术平均但不自动升级；归因深化 `eval.triage`，LLM 调用采用显式 content+evidence 而非 stateful `last_call_metadata`；timeout 默认 45 秒，retry 默认 0，只有明确 transient 幂等错误可显式重试。
- **可信评测结构**：42 raw cases 映射为 26 independent groups；报告并列 semantic answer、safety、plan/trace、provider reliability、manual/Judge 与 end-to-end 的 eligible/observed/unavailable。failure stage 继续表示执行断点，root cause 新增 `code_issue/model_capability/retrieval_issue/external_service/eval_contract/mixed_or_unknown`；完整 trace/score 失败链不再被 first-failure summary 丢弃。
- **调用证据**：QueryPlan/SQL generation 的成功和失败都记录 provider、exact model、stage、configured timeout、attempt index/count、逐次 latency、prompt/system length、stable error subtype 和 outcome；timeout、Arrearage、WinError 10013、429/5xx、parse 与合同错误可分别归因，非瞬时错误不重试。
- **能力反例**：退款率 probe 区分多退款记录、非 completed、错误分母和 INNER JOIN 丢整单 fallback；递归 probe 区分漏子类目 `20`、正确 item grain `70` 与订单头重复聚合 `200`。正确 recursive CTE 的 M24 fidelity 仍为保守 `indeterminate`，未扩大 AST scope。
- **参考资料**：M25 计划、M24 六轮 trace/report、M22-M24 notes、state runbook/eval/database facts与既有 triage/fidelity；采用 deep module/seam 设计词汇，没有照搬 Judge 三次 retry，也未查新的外部资料。
- **验证快照**：focused `39 passed, 1 warning`；linked 修复回归 `12 passed`；最终全仓 `184 passed, 3 skipped, 1 warning`；seed reset 成功、14 表规模与固定事实通过；`git diff --check` 无 whitespace error。warning 为既有 Starlette/httpx deprecation。
- **遗留/后续**：按用户要求未跑完整 formal/challenge/diagnostic，M25-v1 完整 baseline 待用户手动执行；`contributing_causes` 已预留但无真实 mixed 证据时保持空；recursive derived scope 以后需独立决策；只有新 trace 证明 SchemaGraph 缺事实时才重开 retrieval/embedding。

### [实验] M25 4-case Timeout / Retry Focused Reliability（2026-08-07）

- 固定 Qwen `qwen3.7-plus`、`inmemory/deterministic + weighted`、SQLite oracle、LangFuse off、代理与 4 条历史超时题；唯一变量是 `LLM_MAX_RETRIES=0/1`，timeout 均 45 秒。
- retry0：4 logical calls / 4 physical attempts，首次/最终成功均 `1/4`，3 次 QueryPlan timeout，总耗时 `179.7s`；有效响应的 `db_multi_002` 在 plan validation 因虚构 `root_category.level/name` 失败，所需 category tree、表和 `item_gmv` 已在 SchemaGraph。
- retry1：4 logical calls / 8 physical attempts，首次/最终成功均 `0/4`，8 个 attempt 全 timeout，总耗时 `377.9s`；没有恢复且调用/延迟约翻倍。
- **否定结论**：本轮不支持默认开启 retry，继续保持 45s/0。每候选仅一次小样本，不能外推总体 SLA；完整 attempt 证据在 `.agent_work/temp/m25-reliability-{default,retry1}-*`，结论素材已固化到 `docs/notes/m25-notes.md`。
- **当前默认复测（2026-08-07）**：固定 Qwen `qwen3.7-plus`、45s/retry0、本地 deterministic/weighted、4 条 M25 reliability suite，4/4 未通过（约 253.5s）。其中 2 条 QueryPlan timeout、1 条 SQL generation timeout、1 条输出表契约缺表（`order_items` / `orders`）；triage 为 `external_service=3`、`model_capability=1`。这说明该套件不能被简单视为 QueryPlan 测试，前三条语义仍为 `not_observed`，不外推为总体能力或 SLA。
- **diagnostic baseline 尝试（2026-08-07）**：按 45s/retry0 当前默认配置启动完整 challenge + diagnostic 扩展集；外层 1200s 上限到达，留下 29 条 partial trace，未生成正式 report/triage。partial 数据不作为 baseline；后续需拆分 case 集或采用可续跑方式完成。
- **DeepSeek diagnostic 对照（2026-08-07）**：临时切换 `deepseek-v4-flash`，其余保持 45s/retry0、inmemory deterministic/weighted、LangFuse off，完整 32 条 M25-v1 diagnostic 用时 `917.1s`，结果 `25/32`。失败 root cause：`external_service=3`、`model_capability=2`、`code_issue=1`、`mixed_or_unknown=1`；仍有 5 条 `not_observed`。Qwen 本轮只有 partial trace，不能做严格分数比较，也不据此切默认模型。
- **Qwen qwen3.7-max diagnostic 对照（2026-08-07）**：临时切换 `QWEN_MODEL=qwen3.7-max`，其余同 DeepSeek 对照，完整 32 条用时 `1152.4s`，结果 `27/32`。失败 root cause：`external_service=2`、`model_capability=3`、`mixed_or_unknown=1`；`not_observed=3`。相对 DeepSeek `25/32`、`917.1s`，本轮得分较高但更慢、失败结构不同；单轮结果不切默认。
- **Qwen qwen3.7-plus diagnostic 复测（2026-08-07）**：临时切换 `QWEN_MODEL=qwen3.7-plus`，其余同对照，完整 32 条用时 `1208.6s`，结果 `26/32`。失败 root cause：`external_service=5`、`model_capability=1`、`mixed_or_unknown=1`；`not_observed=5`。相对 qwen3.7-max `27/32`、`1152.4s`，本轮 plus 更慢且外部服务失败更多；单轮结果不切默认。
- **Qwen qwen3.7-plus + Milvus/Qwen embedding diagnostic（2026-08-07）**：新建唯一 collection `datapilot_schema_docs_m25_qwen37plus_qwenemb_20260807_192300`，195 docs/hash `8a8b6626...`、1024 维、final row count 195，确认实际走 Milvus；完整 32 条用时约 `1280.6s`，结果 `25/32`。失败 root cause：`external_service=6`、`model_capability=1`。同日 local deterministic 为 `26/32`、`1208.6s`；单轮差异不能判定 embedding 退化或改变默认检索。
- **Round 2 四组 diagnostic（2026-08-07）**：在相同 32 条、45s/retry0、weighted、SQLite oracle、LangFuse off 下顺序运行 `qwen3.7-max + Milvus/Qwen embedding = 26/32, 1263.2s`；`qwen3.7-plus + Milvus/Qwen embedding = 21/32, 1242.3s`；`qwen3.7-plus + local deterministic = 28/32, 1222.7s`；`qwen3.8-max + local deterministic = 18/32, 1273.6s`。Milvus 两组复用 clean 195-doc/1024-dim/hash collection。plus 的 Milvus/local 差距不能单轮归因 embedding；qwen3.8-max 本轮 external failure 很多，暂不作稳定能力结论。

### [模块任务] M24 SQL Plan Contract Semantic Equivalence / Plan-to-SQL Fidelity（2026-08-06）

- **改动范围**：新增 `engine/nl2sql/fidelity_contract.py` 深 module，以 SQLGlot AST 比较已验证 QueryPlan 与候选 SQL；同步接入 planner/generator/pipeline、精确输出 scorer、`output_contract` trace/triage，并补齐 focused tests、M24 plan 与状态文档。完整文件清单和过程素材见 `docs/notes/m24-notes.md`。
- **关键决策**：用户确认采用“精确投影 + 显式 alias 白名单 + 展示顺序稳定”。首版只证明同一顶层 SELECT 内有历史证据的表 alias、quoted identifier、唯一限定名省略和 SELECT alias；CTE/derived scope、歧义字段、ordinal ORDER BY、参数化或 offset LIMIT 返回 `indeterminate` 并保守阻断，不改写 SQL。
- **可信绑定与安全边界**：QueryPlan 新增 `output_expressions`，由计划明示聚合 alias→expression，禁止候选 SQL 自证；SQL policy 预检先于 fidelity，SQL Tool 执行时再次 Guard。合同通过只证明计划保真，不等同答案正确。
- **输出与归因**：SQL 执行后的真实 `body.columns` 必须与计划集合/顺序一致；自动 `result_match` 先按 case 明示 alias 白名单归一，再严格比较 expected columns。triage 将最终投影/table/column 合同归入独立 `output_contract`，不再用最终输出失败推断 retrieval/embedding。
- **参考资料**：M22/M23 notes、历史 trace/report、M24/v6.7 计划、项目既有 SQLGlot/SchemaGraph/SQL Guard/trace/SQLite oracle；没有复制外部项目代码，也没有把 module 扩成通用 SQL optimizer。
- **验证快照**：收尾 focused `70 passed, 1 warning`；全仓 `176 passed, 1 warning`。warning 为既有 Starlette/httpx deprecation。M24 不改 ORM/数据，未跑 Alembic/seed；收尾未重复真实 LLM eval。
- **遗留/后续**：稳定问题已转为 QueryPlan 过宽投影、生成表达式不忠实和结果语义错误；只在出现真实正反例后扩展 AST scope。Milvus 三次自动分高约一分不足以证明 embedding 因果收益，默认仍为 `inmemory + deterministic + weighted`。M24 尚待 `accept-module` 验收。

### [实验] M24 受控 Local vs Milvus/Qwen embedding diagnostic（2026-08-06）

- 固定条件：Qwen `qwen3.7-plus`、weighted、32 条 diagnostic、SQLite deterministic oracle、LangFuse disabled、当前 195-doc corpus/hash；Local 使用 `inmemory + deterministic`，Milvus 使用 DashScope `qwen3.7-text-embedding`（1024 维）。
- 按 `Local → Milvus → Local → Milvus → Local → Milvus` 交错完成 6 次有效 run：Local 总分 `24/24/25`，自动能力 `21/21/22/27`；Milvus 总分 `25/25/25`，自动能力 `22/22/22/27`；两组 manual/diagnostic 均 `3/5`。
- Milvus collection `datapilot_schema_docs_m24_qwen_weighted_20260806_194900`：M1 首次写入 195，M2/M3 `inserted_document_count=0`，三次 final row count=195，schema hash 和维度均一致。
- 合同观察：`db_core_004`、`db_plan_001`、`db_prompt_002` 等历史 alias/限定名正例六次稳定通过，没有新的 `semantic_false_block`。M1 `db_core_002` 明确记录计划 `COUNT(DISTINCT orders.id)` 与候选 `COUNT(DISTINCT order_items.id)` 的真实表达式不一致。
- 稳定失败：`db_simple_001/002/003`、`db_core_002`、`db_hard_001/003`、`db_join_003`、`db_multi_002`。135 个可执行 SQL trace 的 pipeline `output_contract` span 均成功，说明部分投影问题来自 QueryPlan 本身声明过宽，随后由 case scorer 捕获。
- 外部故障边界：最早 L1 在 25 条 trace 后超时；L1r 因 DashScope `400 Arrearage` 得到的 `7/32` 无效，只作账户故障证据。账户恢复并通过 health check 后的上述六次才计入样本。
- ⚠️ 注：M25 已把此类 timeout/Arrearage/网络权限升级为稳定 transport subtype 与 `external_service + not_observed`；它们保留执行 stage，但不进入已观察的模型语义错误。见上方 M25 模块档案。
- 结论：Milvus 自动能力在三次样本中稳定高 1 分，但不是 embedding 因果证明，不切默认。完整矩阵见 `eval/reports/m24-ab-execution-manifest.md`，逐 case 证据见 `docs/notes/m24-notes.md`。

### [实验] M23 同合同 clean Milvus / Qwen embedding 单次诊断补登记（2026-08-06）

- 配置：Qwen `qwen3.7-plus` + clean run-scoped Milvus + DashScope `qwen3.7-text-embedding` + weighted；32 条 M23 diagnostic、195 docs/hash `ce04fe4f...`、1024 维、SQLite deterministic oracle、LangFuse off。collection 为 `datapilot_schema_docs_m23_qwen_plus_qwenemb_20260806_154117`，本轮 `None → inserted 195 → final 195`。
- 结果：total `21/32`；automated `20/27`；manual_or_diagnostic `1/5`。local M23-E03 为 `23/32`、automated 同为 `20/27`，两组总分差来自人工/诊断项。
- 解释边界：两组各仅一次真实 LLM run；旧 triage 的 `schema_context/retrieval` 桶混入最终 `tables_used/body.columns` 证据。该结果只证明同合同 clean embedding 链路已跑通，不证明 embedding 退化，也不改变默认 `inmemory + deterministic + weighted`。
- 产物：`eval/reports/m23-qwen-milvus-qwenemb-diagnostic-{report.md,triage.json}`、`eval/traces/m23-qwen-milvus-qwenemb-diagnostic-traces.jsonl`。

### [实验] M23 新合同 32 条全量 diagnostic 首跑（2026-08-06）

- 配置：Qwen `qwen3.7-plus` + `new_text2sql` + local `inmemory + deterministic + weighted`、32 条 diagnostic、195-doc corpus / hash `ce04fe4f...`、SQLite deterministic oracle、LangFuse off、代理。
- 结果：total `23/32`；automated `20/27`；manual_or_diagnostic `3/5`（review 3）。这是 M23 新合同下第一个 32 条全量基线；M22 194-doc 的 24~28/32 不可直接比较。
- 失败结构（10 条 failed_or_review）：
  - 3 条 result_contract（输出契约不保真）：`db_simple_001` 缺 ORDER BY（"前 10"含义不定，首行不匹配）、`db_simple_002` 丢 LIMIT 10（返回 6681 行 vs expected 10）、`db_simple_003` 列超量（输出 coupons 全 10 列 vs expected 3 列）。trace 确认 QueryPlan 有排序 / 限制意图，是 QueryPlan→SQL 生成保真问题，直接复现 M22 活跃坑「SQL generation 可能丢弃 order_by/limit」。
  - 6 条生成 / 计划失败（SQL 为空被拦）：`db_core_002`、`db_multi_001`、`db_trace_002`（sql_plan_contract_failed）、`db_multi_002`、`db_hard_001`、`db_join_003`（llm_generation_error）。其中 `db_core_002`、`db_join_003` 与 M23-E02 异常专项失败点重合，属稳定失败点。
  - 1 条人工待核：`db_hard_003`（SCD 窗口平均售价，SQL 已正确生成）。
- 亮点：安全 4/4 全拦（sql_guard 2 + plan_validation 2）；M23 收口口径生效（`db_core_004` 各渠道订单量 COUNT DISTINCT + 排序、`db_join_001` 渠道退款率、`db_schema_003` 宽表题均通过）；检索层零失败（schema_retrieval 32/32 success，table_hit / column_recall 全过）。
- 结论：硬失败共 9 条，其中自动失败 7 条、人工/诊断失败 2 条；failed-or-review 为 10 条，额外一条是 `db_hard_003` review-only。自动失败进一步分为 3 条结果/输出不保真、2 条生成/计划错误、2 条字符串 SQL plan contract 误拦；目标 schema 均已进入 Context，不归因 retrieval。
- 验证快照：报告 `eval/reports/m23-qwen-local-weighted-diagnostic-report.md`、triage `eval/reports/m23-qwen-local-weighted-diagnostic-triage.json`、traces `eval/traces/m23-qwen-local-weighted-diagnostic-traces.jsonl`。
- ⚠️ 注：同合同 Milvus + Qwen embedding 已补登记为上方单次诊断快照 `21/32`（自动同为 `20/27`）；它不能单次给出 embedding 结论。后续先完成 M24 合同前置关卡，再做交错重复 A/B。

### [模块任务] M23 Eval / Semantic / Database Baseline Hygiene（2026-08-05）

- 改动范围：`metrics.yaml`、订单/退款 schema descriptions、`relations.yaml`、seed 固定事实、formal / challenge cases、`result_match` 日期归一化及 focused tests；完整素材见 `docs/notes/m23-notes.md`。
- 关键记录：商品退款率统一为成交订单内“订单明细优先、整单退款回退 `refunds.product_id`”，不再用 `orders.product_id` 或 INNER JOIN 静默丢失整单退款；`order_count` 统一为 `COUNT(DISTINCT orders.id)`。状态枚举、SRC/ORD 命名空间不可 join 和退款归因边界写入运行时 field / relation schema documents。
- 评测合同：challenge 12 条与 formal 8 条自动 SQL case 均使用 `result_match` 或 `expected_value`；递归类目、SCD 价格两题保留 manual，不把 reference SQL 仅作为关键词检查的旁注。`result_match` 统一 SQL Tool 的 ISO 时间与 reference datetime 表示，避免相同结果因序列化格式误判。
- 验证：20 条 reference SQL 在当前 MySQL 与 deterministic SQLite 均可执行、逐条行数一致；focused `42 passed, 1 warning`；全量 pytest `152 passed, 1 warning`。warning 均为既有 Starlette/httpx `TestClient` deprecation。
- Milvus 复用补丁：M23 语义文本改变后发现，旧实现只校验 row_count / dimension，194 条旧向量会被错误映射为 194 条新文档。现将 `schema_docs_hash` 写入 collection schema description，复用时强制校验；随后新增 `net_refund_amount` 使当前 corpus 进一步变为 195 条 / `ce04fe4f...`，缺少标记或 hash 不同的 M20/M22 collection 必须新建或显式 reset。
- 异常专项：将异常彩蛋规则从 M22 实验卡片提升为 `eval-baselines.md` §2.5 长期章节；新增 `net_refund_amount` 指标和 `db_anomaly_001/002/003`，并由 `database-exception-suite.yaml` 引用既有 case，避免 formal / challenge / diagnostic 的重复 YAML。专项为 6 条自动 + 1 条人工素材；新增三条 reference SQL 已在 SQLite 与当前 MySQL 执行成功，相关 focused `32 passed, 1 warning`。
- 真实 LLM 快照（2026-08-06）：首次无代理运行在所有 case 的 QueryPlan 阶段报 `WinError 10013`，作为网络失败不记分；配置本地代理后，Qwen `qwen3.7-plus` + `new_text2sql` + local deterministic / weighted 完成 7 条专项，结果 `1/7`（自动 `1/6`、人工 `0/1 review`）。唯一自动通过为 `db_anomaly_001`，证明 signed completed refund reference 能进入端到端链路；其余失败分别显示成交订单缺 limit、coupon 输出列不符、退款率结果不符、退款渠道关联缺 `orders/channels`、对账输出列缺失，`db_join_003` 为 LLM generation error。单次诊断不切默认。报告/trace/triage 已随临时目录统一迁至 `.agent_work/temp/m23-exception-suite-retry-20260806_145019-*`。
- 遗留/后续：SQLite 仍是离线 oracle，MySQL 仍仅做只读审计；外部单号、负数退款和订单头/明细金额对账尚无独立自动 case。M22 真实 LLM 总分属于旧合同历史快照，下一轮 retrieval 假设必须从 M23 新合同重新建基线。

### [评测审计] M22 数据库异常彩蛋覆盖边界（2026-08-05）

- 审计范围：对照 `database-current-state.md` 的异常菜单，逐项核对 M22 challenge / diagnostic case、reference SQL 和 scorer 判定。
- 已覆盖：成交类 reference 对 `paid_at` 时间窗口和 `cancelled` / `canceled` 过滤；优惠券使用订单数的 `COUNT(DISTINCT orders.id)`；SCD 价格的 `valid_to IS NULL` 时间窗口。
- 未独立覆盖：外部单号重复 / 命名空间、负数退款、订单头与明细金额对账。`db_core_002` 当前只按 `refunds.order_item_id` 做商品退款率 reference，会排除整单退款，且未显式排除取消订单；`db_join_003` 为 manual review，不能补足自动判定。
- 影响：C0-refresh/C1/C2/C3 首轮结果仍在相同 194-doc、case/scorer、SQLite seed 下可比，但只能解释当前 eval 合同下的模型/检索波动，不能宣称异常数据鲁棒性。是否补充异常 case 或改变退款率口径属于长期评测结构选择，待用户确认；在确认前不修改 case、不重写首轮结果。
- 参考：`docs/state/database-current-state.md`「与当前 M22 eval 的关系」、`docs/state/eval-baselines.md`「M22 异常彩蛋覆盖审计」、`docs/notes/m22-notes.md`。

### [实验] M22 C0-C3 三次重复稳定性（2026-08-05）

- 在不改变当前 case/scorer、194-doc corpus、oracle、LangFuse 开关和 `new_text2sql` 的前提下，完成 C0-C3 首轮、第2次和第3次端到端 diagnostic。
- 结果：C0 `24/24/25`，C1 `27/28/28`，C2 `25/27/25`，C3 `24/26/27`（均为 32 条总分）。C2 第2次首次启动被工具 120 秒上限中断，重启后的 `r2b` 才计入有效样本。
- 结论：C1 在三次中均最高或并列最高；C2/C3 没有稳定超过 C1 的证据，因此不切换默认模型、Milvus 或 RRF。retrieval-only 的 RRF 提升不等于端到端提升。
- 所有 Milvus 复测使用独立 collection、194 rows 和同一 schema hash；本轮只说明当前评测合同下的波动与稳定性，不覆盖此前审计到的全部数据库异常彩蛋。

### [实验] M22 Qwen 3.8 追加对照（2026-08-05）

- 按用户要求执行 `qwen3.8-max + inmemory/deterministic + weighted`，固定当前 M22 32 条 diagnostic、`new_text2sql`、SQLite deterministic oracle、LangFuse disabled 和现有 case/scorer。
- 完整结果为 `22/32`；模型调用可用，故未继续备用 `qwen3.7-max`。该单次快照不改变默认模型，不能与三次重复稳定性结果混为同一组。
- 报告 `eval/reports/m22-qwen38-local-weighted-report.md`，trace `eval/traces/m22-qwen38-local-weighted-traces.jsonl`，triage `eval/reports/m22-qwen38-local-weighted-triage.json`。

### [实验] M22 Qwen 3.7 Max 追加对照（2026-08-05）

- 在相同条件下执行 `qwen3.7-max + inmemory/deterministic + weighted`，完整 diagnostic 结果为 `26/32`。
- 该结果高于 Qwen 3.8 的 `22/32`，但仍是单次追加快照，不纳入 C0-C3 三次重复矩阵，也不自动改变默认模型。
- 报告 `eval/reports/m22-qwen37max-local-weighted-report.md`，trace `eval/traces/m22-qwen37max-local-weighted-traces.jsonl`，triage `eval/reports/m22-qwen37max-local-weighted-triage.json`。

### [审计] M22 C1 本地 vs C2 embedding 逐 case 初步差异（2026-08-05）

- 三次配对通过数：`27→25`、`28→27`、`28→25`。C2 并非全面退化，首轮 `db_core_002` 由 C1 失败、C2 通过。
- C2 额外失败集中在 `db_core_004`、`db_plan_001`、`db_prompt_002`、`db_join_003`、`db_schema_003`、`db_trace_002`。其中多项 trace 显示 schema context 已包含目标表，失败发生在 SQL 生成后的别名/排序合同或输出列大小写；不能直接归因于 embedding 召回。
- 初步排查顺序：先比较同 case 的 retrieval top docs/context 表字段，再区分“上下文缺目标”与“上下文有但 SQL 未使用”，最后单独核对 QueryPlan 与候选 SQL 的 alias/order/limit 及 scorer 列名大小写。任何 AST 合同升级、别名规范化或默认 retrieval 调整都需另行确认。

### [默认配置] 主模型切换为 Qwen qwen3.7-plus（2026-08-05）

- 用户在查看 M22 三次重复结果后确认，将默认主模型切换为 Qwen `qwen3.7-plus`。
- 实际配置：`.env` 使用 `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`；`LLM_MODEL=deepseek-v4-flash` 保留为显式切回 DeepSeek provider 的备用入口。
- 检索默认不变：`inmemory + deterministic + weighted`；未切换 embedding、Milvus、RRF、case、scorer 或 oracle。
- 验证：`get_default_llm_client()` 解析为 `QwenChatClient / qwen3.7-plus`；配置与 NL2SQL 相关测试 `11 passed, 1 warning`。warning 为既有 Starlette/httpx deprecation。
- 后续影响：真实请求默认依赖 DashScope Qwen key，延迟/费用/输出格式需按新默认持续观察；DeepSeek `deepseek-v4-flash` 仍可通过显式 provider 配置使用。

### [修复] M22 契约完整性与收口证据（2026-08-04）

- 改动范围：Context scorer、plan-validation scorer/case、SQL contract trace、`db_simple_002`、M22 计划与临时产物纪律。
- 记录：补齐 Context 的 join key 硬检查，以及表数/禁表 warn；`accept_paths` 现按 `(blocked_via, issue_tag)` 成对验证，三类 M22 语义拒绝统一声明 `semantic_request_validation`。SQL Plan Contract 暂不改 AST，只在失败 trace 写候选 SQL 摘要与计划/观察到的排序、limit，先积累误拦证据。用户确认“已支付订单”case 使用“成交订单”口径并排除取消状态。
- 产物：`.agent_work/temp/m22-db-core-004-trace.jsonl` 已取消 Git 跟踪并加入 ignore；历史 commit 不重写，本地一次性文件可保留供本机排障。
- 验证：M22 专属 `14 passed, 1 warning`；相关回归 `64 passed, 1 warning`；全量 `147 passed, 2 skipped, 1 warning`，均仅有既有 Starlette/httpx warning。
- 遗留/后续：三条默认快照 SQL contract failure 的真实/误拦比例需以后续 trace 判断；是否采用 AST 比较需单独确认。真实 LLM default diagnostic 未因本次修复重跑，`25/32` 仍是修复前 C0 快照。Qwen/Milvus/RRF 新口径实验仍待用户确认，不在本修复中执行。

### [范围调整] M22 纳入 Qwen / Milvus / RRF 新口径对照（2026-08-04）

- 改动范围：`docs/notes/m22-notes.md`、state 当前路线与评测账本。
- 记录：用户确认将这组候选对照归入 M22，不另开 M23。固定 M22 的 194-doc/new case-scorer/oracle 条件；既有 C0 默认快照不重复执行，首轮只运行 C1-C3 与 retrieval-only 组各一次，结果后再由用户确认是否在同一窗口完整运行 C0-C3 三次。默认模型、embedding、Milvus、fusion 不因单次结果切换。
- 性能事实：M22 默认 32 条 diagnostic 实测总 `512.0s`，其中 QueryPlan LLM 调用占 69.4%、SQL generation LLM 调用占 30.3%；检索和 SQLite 非主耗时。

### [文档口径] State 续接仪表盘收敛（2026-08-04）

- 改动范围：`AI_CONTEXT.md`、`database-current-state.md`、`runbook.md`。
- 记录：移除仪表盘中已完成 M19/M20 的行动指令，改为 M22 后 194-doc / 新 case-scoring 基线和“先按 trace/failure subtype 定位”的当前路线；明确商品退款率默认 reference 使用订单明细归因，兼容字段不作为默认口径；将 manual/review 说明更新为 M22 通用报告语义。随后将同类 cross-state 审计固化为 `accept-module` 检查 9，验收只报告精确问题，不自动修改 state 文档。
- 边界：仅收敛文档续接口径，不改代码、数据库、默认模型/检索、安全策略或 eval 规则。

### [模块任务] M22 Eval Contract / Semantic Output Stabilization（2026-08-04）

- 改动范围：`eval/scorers/rule_scorers.py`、`eval/run_eval.py`、`engine/nl2sql/{semantic_validation,pipeline,generator,prompt}.py`、三份 eval case、`metrics.yaml`、M22 / M20 回归测试及报告；完整清单见 `docs/notes/m22-notes.md`。
- 关键记录：用户确认先校正 case/scorer 契约；商品退款率采用订单明细归因，一级类目采用规范类目树，manual/diagnostic 单列。Context Contract 改读同请求 trace 的 SchemaGraph metadata；`plan_validation_blocked` 优先评分；supplier、知识库订单归因、多步对比改为带 `blocked_via` 的语义拒绝。SQL 只检查 QueryPlan 已声明的排序/limit，不改写 SQL，危险 SQL 仍先走 SQL Guard。
- 评测事实：新增 `coupon_order_count` 使 schema docs `193→194`；最终默认 diagnostic `25/32`（automated `22/27`、manual `3/5`），与 M21 `21/32` 不可比较。报告三视图曾因插入 Score Summary 表中间而破坏 Markdown 表格，已补回归测试并在修复后重跑；`db_prompt_002` trace 已验证 SCD overlap；`db_core_004` 单 case SQLite oracle 复测 `result_match_ok`，但批量实时 LLM 仍会波动。
- 验证快照：focused `42 passed`、pipeline focused `28 passed`；最终全量 pytest `144 passed, 2 skipped`，均仅有既有 Starlette/httpx warning。
- 参考资料：无外部资料；依据 M22 plan、`m22-review-notes.md` 和项目现有 trace/scorer/pipeline。
- 遗留/后续：`db_simple_001` 暴露 SQL generation 丢失已规划排序并被结构化拦截，M22 不扩展为通用列表排序优化；M23 从 194-doc、新 case/scorer 基线重新做 retrieval 假设，默认策略不变。

### [小修] roadmap阶段编号调整（2026-08-04）

阶段三改名为阶段四，其他阶段编号依次后移；阶段三A 后补阶段三B；去掉周次 / 耗时标注。

### [小修] 产物路径收编：notes / eval 产物迁出 temp（2026-08-03）

- 改动范围：28 个 mX-notes.md → `docs/notes/`（进 git）；72 个 eval 报告（report/triage/compare）→ `eval/reports/`、40 个 traces → `eval/traces/`（jsonl 继续 gitignore）；18 份 accept 验收报告删除（不再落盘）；同步 `CLAUDE.md`、finish-module / finish-docs / accept-module skill 的 notes 路径，及 `runbook.md` eval 命令模板和 `eval-baselines.md` / `schema-retrieval-milvus-embedding.md` / `database-current-state.md` 的产物指针。
- 关键记录：notes 原在 gitignore 的 temp（跨会话收工素材有被清理风险），迁入 `docs/notes/` 后进 git，可恢复可追溯；验收报告不再保存文件（会话即存档），验收事件状态仍写入 AI_CONTEXT「当前状态」，accept-module 同模块复检改以"上次验收时的提交"界定增量；eval 产物默认归宿 = report/triage/compare → `eval/reports/`、traces → `eval/traces/`，runbook 命令矩阵产物路径已同步指向新位置。
- 遗留/后续：`.agent_work/temp/` 仍剩 176 个一次性文件（129 个 pytest basetemp 目录 + 历史 smoke 脚本/摘要——smoke 一次性产物按口径留 temp，正式 eval trace 已全部收编 `eval/traces/`），待大扫除；`db-current-smoke-traces.jsonl` 为既有悬空引用，未处理。

### [实验] M21 Qwen-plus 本地 vs Qwen embedding controlled A/B（2026-08-03）

- 目的：在不改主模型、fusion、case、oracle 和默认配置的前提下，只比较 Schema Retrieval 的 `inmemory + deterministic` 与 clean Milvus + DashScope Qwen embedding。
- 固定条件：`QWEN_MODEL=qwen3.7-plus`、`schema_fusion_strategy=weighted`、`new_text2sql`、同一 diagnostic 32 题、`LANGFUSE_ENABLED=false`、`result_match_oracle_backend=sqlite_deterministic_seed`；B 组 collection 为 `datapilot_schema_docs_m21_qwen_weighted_20260803_001`，`milvus_final_row_count=193`，schema hash 为 `7b531e...`，`schema_vector_index_reuse=run_scoped`。
- 结果：A 本地 deterministic `21/32`；B Milvus + Qwen embedding `21/32`。A 的 failure stage 为 `schema_context=6`、`schema_retrieval=2`、`sql_generation=2`、`result_match=1`、`unknown=2`；B 为 `schema_context=6`、`schema_retrieval=2`、`query_plan=1`、`result_match=1`、`sql_generation=1`、`unknown=1`。
- 失败细分类：两组 `failure_subtype` 完全一致：`output_column_contract=6`、`output_table_contract=2`、`result_contract=1`。逐 case 只有 `db_hard_001`（schema_retrieval → query_plan）、`db_join_003`（unknown → schema_retrieval）、`db_plan_004`（失败 → 通过）发生形态变化。
- 结论：本次受控端到端 A/B 没有显示 Qwen embedding 提分，也没有改变 M21 的 `schema_context` / 输出契约瓶颈判断；embedding 保持显式实验路径，不切默认。后续转向 M22 的 output contract 与 QueryPlan → SQL 稳定性。
- 产物：`.agent_work/temp/m21-qwen-plus-local-weighted-report.md`、`.agent_work/temp/m21-qwen-plus-local-weighted-triage.json`、`.agent_work/temp/m21-qwen-plus-qwenemb-weighted-report.md`、`.agent_work/temp/m21-qwen-plus-qwenemb-weighted-triage.json`、`.agent_work/temp/m21-qwen-plus-local-vs-qwenemb-triage-compare.md`、`.agent_work/temp/m21-plus-local-vs-qwenemb-notes.md`。

### [实验] Qwen qwen3.7-max M21 follow-up pilot timeout（2026-08-03）

- 配置：固定 M21 clean Milvus collection `datapilot_schema_docs_m21_qwen_weighted_20260803_001`、Qwen embedding 1024 维、`weighted`、`LANGFUSE_ENABLED=false`；先执行 32 条 diagnostic，随后缩小为 16 条 `database-upgrade-challenge` pilot。
- 结果：32 条 run 在约 15 分钟外层命令上限内未生成 report/triage；16 条 pilot 继续等待后也未生成任何产物，进程长期低 CPU 等待，已停止。没有可用的新增 Qwen 分数，也没有启动 RRF 对照，避免在端点未稳定时继续消耗长时间 eval。
- 判断：这次不能证明 Qwen 模型质量或 weighted/RRF 差异；只能说明当前环境下该 Qwen 端点在本次运行中不可稳定完成。历史 M20 的 Qwen `21/32` 仍是唯一完整基线，不改默认模型或 fusion。
- 产物：未生成有效 report/triage；本记录是超时/阻塞事实，不能作为模型优劣结论。

### [实验] Qwen qwen3.7-max health check + 32-case rerun（2026-08-03）

- 健康检查：通过项目现有配置、代理和 `get_default_llm_client()` 发起最小 JSON 请求，返回合法 JSON，耗时 `6.57s`；因此 key、模型名、网络和 DashScope 路由均可用。
- 重测配置：沿用 M21 clean Milvus collection、Qwen embedding 1024 维、`weighted`、32 条 diagnostic；产物为 `.agent_work/temp/m21-qwen-health-weighted-diagnostic-report.md`、`-triage.json`、`-traces.jsonl`。
- 结果：`11/32`。失败结构中 `query_plan=12`，多数请求耗时约 `45.4–45.5s`；客户端 `OpenAICompatibleChatClient` 当前单次请求 timeout 固定为 `45s`，这些失败应优先视为 timeout / infra，而不是模型能力结论。其余结构为 `sql_generation=2`、`schema_context=5`、`schema_retrieval=1`、`plan_validation=1`。
- 判断：Qwen 端点健康但长 prompt 生成延迟高；本次 `11/32` 不能与 M20 `21/32` 直接做能力比较。若要公平重测，需要先确认是否允许调整 timeout / 评测耗时策略；本次不改默认配置。

### [实验] Qwen qwen3.7-plus M21 weighted diagnostic（2026-08-03）

- 配置：仅通过本次命令设置 `QWEN_MODEL=qwen3.7-plus`；其余保持 clean Milvus collection、Qwen embedding 1024 维、`weighted`、32 条 diagnostic 不变，未修改默认配置。
- 健康检查：返回合法 JSON，耗时 `5.04s`。
- 结果：`21/32`；平均单 case latency `38.9s`、P50 `38s`、P95 `65.8s`。失败阶段为 `schema_context=6`、`schema_retrieval=2`、`result_match=1`、`query_plan=1`、`unknown=2`、`sql_generation=1`，只有 1 条 query_plan 和 1 条 sql_generation 的 LLM error，不再像 qwen3.7-max 重测那样有 12 条 query_plan timeout 型失败。
- 判断：plus 与历史 M20 qwen3.7-max 的 `21/32` 总分相同，但本次 plus 的端点稳定性 / 规划阶段明显更好；剩余主要问题转为 schema context / schema docs 与少量结果匹配。该单次 A/B 仍不足以直接切换默认模型。
- 产物：`.agent_work/temp/m21-qwen-plus-weighted-diagnostic-report.md`、`-triage.json`、`-traces.jsonl`。

### [实验] M21 proper A/B：qwen3.7-plus weighted vs RRF（2026-08-03）

- 固定 `qwen3.7-plus`、同一 clean Milvus collection、Qwen embedding 1024 维、32 条 diagnostic；只把 fusion 从 `weighted` 改为显式 `rrf`。
- 结果：weighted `21/32`，RRF `20/32`。triage 对比：`schema_context 6→5`、`query_plan 1→2`、`result_match 1→2`、`unknown 2→1`，`schema_retrieval=2`、`sql_generation=1` 不变。
- 判断：在同一主模型下，RRF 的离线召回优势没有转化为端到端收益，反而少 1 条通过；M21 保持 `weighted` 默认的结论得到第二个模型证据支持。
- 产物：`.agent_work/temp/m21-qwen-plus-rrf-diagnostic-report.md`、`-triage.json`、`-traces.jsonl`、`m21-qwen-plus-weighted-vs-rrf-compare.md`。

### [实验] M21 后续 Context 地基体检（2026-08-03）

- 对齐 plus weighted / RRF 的 32 条 trace、triage 和 retrieval metadata，产出 `.agent_work/temp/m21-context-audit.md`。
- 关键发现：当前 triage 的 `schema_context` 是 schema 相关失败桶；`eval/triage.py` 将 `rule:column_recall` 映射为 `schema_context`，但 scorer 检查的是最终响应 `body.columns`，不是 SchemaGraph 字段是否被召回。
- weighted 失败样本中，`expected_tables` 均已进入 `schema_context.metadata.tables`；`db_core_002`、`db_multi_001`、`db_prompt_001` 等更像 SQL 输出表 / alias / scorer 契约问题，不能直接归因 embedding 或 context assembly。`build_schema_graph()` 对已选表会补入完整 domain-schema fields。
- 结论：没有发现可被证据明确证明的“目标物理表 / 字段已召回但被 context assembly 丢掉”的 plus weighted case；M21 地基目标达到，不在 M21 临时实现未定位的 rerank / top_k / doc_type weighting，后续方法实验留给下一模块。

### [小修] M21 triage 输出契约细分类（2026-08-03）

- `eval/triage.py` 新增 `failure_subtype`，把 `rule:table_hit` / `rule:column_recall` 标成 `output_table_contract` / `output_column_contract`；保留原 `failure_stage`，避免破坏旧报告和 A/B 口径。
- 报告新增 subtype 分布；这只修正诊断解释，不改变 scorer 分数、正式 case、oracle、默认配置或 LangFuse score 数量。
- 验证：M19 triage focused `7 passed, 1 warning`；与 pipeline 相关回归 `13 passed, 1 warning`。

### [模块任务] M21 Schema Retrieval Fusion / Context Repair（2026-08-03）

- 改动范围：未提供模块起始 commit，按当前工作树检查；本模块涉及 `engine/schema_retrieval/retriever.py`、`engine/nl2sql/pipeline.py`、`app/schemas/agent.py`、`app/api/query.py`、`eval/run_schema_retrieval_benchmark.py`、`eval/run_eval.py`、两份 retrieval 测试和 `.agent_work/temp/m21-*` 验证素材。`docs/dev-log.md` 存在用户既有未提交改动，未重写其旧内容。
- 关键记录：
  - 保持默认 `weighted` merge，不改默认 embedding / Milvus、正式 case、scorer 或 oracle；新增仅显式传入的 `rrf`，并把它写入 benchmark / eval runtime metadata 和 schema retrieval trace metadata。
  - RRF 只使用线上候选 hit 的 rank；`expected_tables`、`expected_columns`、metric / relation 标注只用于离线评分，不能进入 retriever / reranker，避免评测标签泄漏。
  - 为 deterministic 和 Milvus 报告统一补齐 `schema_docs_hash` 等运行元数据，确保基线与候选可以确认使用同一份 schema 语料。
  - retrieval-only：deterministic merged `0.738→0.802`；Milvus + Qwen embedding merged `0.738→0.929`、metric `0.600→0.900`、relation `0.633→0.967`（collection `datapilot_schema_docs_m21_qwen_weighted_20260803_001`，row_count `193`，hash `7b531e...`）。
  - 同配置 DeepSeek diagnostic：weighted `21/32`，RRF `18/32`。虽然 `schema_context 5→4`，但 `plan_validation 0→3`、`query_plan 3→4`、`schema_retrieval 0→1`；RRF 不具备端到端收益，记录为否定实验，不切默认。
- 参考资料：无外部资料；依据 M21 计划、M19 triage、M20 clean Milvus 证据与既有 `SchemaHit.rrf_score` 字段，未引入 LLM / cross-encoder reranker。
- 验证快照：focused `16 passed, 1 warning`；related `22 passed, 1 warning`；全量 pytest 首次 300s 外层超时但无失败栈，使用新 basetemp 复跑为 `133 passed, 1 warning`（376.77s）。真实 retrieval-only 和 diagnostic A/B 报告均已写入 `.agent_work/temp/m21-*`；既有 Starlette/httpx deprecation warning 不影响 M21。
- 遗留/后续：若继续优化，先按 case 审查 RRF 改变后的 context 与 QueryPlan；relation/metric bundle docs、doc_type weighting、context budget / top_k、reranker 和默认 embedding / Milvus 均为需单独确认的长期选择。

### [实验] 新增 Schema Retrieval embedding-only benchmark（2026-08-02）

- 新增 `eval/cases/schema-retrieval-embedding-benchmark.yaml`、`eval/run_schema_retrieval_benchmark.py`、`tests/test_schema_retrieval_embedding_benchmark.py`，用于只评估 Schema Retrieval 召回，不调用 LLM / 不执行 SQL。
- 首轮 deterministic baseline：`.agent_work/temp/schema-retrieval-embedding-deterministic-report.md`，`avg_overall_recall=0.738`、`avg_keyword_overall_recall=0.738`、`avg_vector_overall_recall=0.787`。
- 首轮 Milvus + DashScope `qwen3.7-text-embedding`：`.agent_work/temp/schema-retrieval-embedding-qwen-milvus-report.md`，collection `datapilot_schema_retrieval_bench_qwen_20260802_223456_127f76ab`，`row_count=193`，`avg_overall_recall=0.738`、`avg_keyword_overall_recall=0.738`、`avg_vector_overall_recall=0.929`。
- 结论：Qwen embedding 的 vector-only recall 明显更好，但当前 merged recall 未提升，说明下一步更应评估 fusion / RRF / rerank / top_k，而不是直接切默认 embedding。

### [实验] M20 Qwen qwen3.7-max + clean Milvus + Qwen embedding diagnostic（2026-08-02）

- 背景：上次同配置 run 900s 超时只有 partial trace；本次用后台长时运行补上完整数据点。
- 配置：`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-max`、`SCHEMA_VECTOR_BACKEND=milvus`、`SCHEMA_EMBEDDING_PROVIDER=dashscope`、`QWEN_EMBEDDING_MODEL=qwen3.7-text-embedding`、`QWEN_EMBEDDING_DIMENSIONS=1024`、`MILVUS_COLLECTION=datapilot_schema_docs_m20_qwen37max_qwenemb_20260802_214810`、`LANGFUSE_ENABLED=false`。
- 用户要求（已落实）：Milvus 实验 collection 命名统一为日期+秒级时间戳 `<YYYYMMDD_HHMMSS>`，不再用 `_a` / `_b` 后缀；已同步到 `docs/state/schema-retrieval-milvus-embedding.md`「Milvus Collection 纪律」。
- 结果：diagnostic `21/32`；`milvus_final_row_count=193`、`schema_vector_index_reuse=run_scoped`、`schema_docs_hash=7b531e...`、oracle 仍为 `sqlite_deterministic_seed`、`milvus_dimension=1024`。
- 失败结构：`schema_context=7`、`sql_generation=2`（llm_generation_error）、`result_match=1`、`schema_retrieval=1`、`unknown=2`；needs_action `fix_schema_desc=7`、`fix_pipeline=3`、`manual_review=3`。
- 对比：同链路 clean DeepSeek `17/32` → Qwen `21/32`，提升主要来自 query_plan 5→0、plan_validation 2→0、sql_guard 1→0；代价是 schema_context 5→7、sql_generation 0→2、unknown 0→2。M19 污染 Qwen `20/32` → M20 clean `21/32`（主要来自 plan 类失败消失）。
- 结论：首次完整 clean Qwen 链路数据点；Qwen 规划/生成类失败更少，但 `schema_context` 仍是最大失败簇，优化优先级不变（先修 schema 上下文）；单次真实 LLM run 有非确定性，不切换默认模型 / embedding / Milvus。
- 产物：`.agent_work/temp/m20-qwen37max-qwenemb-diagnostic-report.md`、`-traces.jsonl`、`-triage.json`；对比 `.agent_work/temp/m20-clean-deepseek-vs-qwen37max-compare.md`、`m20-polluted-vs-clean-qwen37max-compare.md`。
- 长期数字已同步 `docs/state/eval-baselines.md`，速查结论已同步 `docs/state/schema-retrieval-milvus-embedding.md`，摘要已同步 `docs/state/AI_CONTEXT.md`。

### [小修] 新增 Schema Retrieval / Milvus / embedding 速查文档 + Milvus 实验 collection 命名规范（2026-08-02）

- 新增 `docs/state/schema-retrieval-milvus-embedding.md`，集中说明默认 `inmemory + deterministic`、Milvus 显式实验边界、M20 collection hygiene、`schema_docs_hash`、报告字段、常用命令和排查菜单。
- 文档顶部标注 `更新时间：2026-08-02`，方便后续 AI 判断速查事实的新旧。
- `docs/state/AI_CONTEXT.md`、`docs/state/runbook.md`、`docs/state/eval-baselines.md` 已加入该文档入口；本次只做文档索引与说明，不改变代码默认值或 eval 口径。
- 用户要求：唯一 collection 名不再用 `_a` / `_b` 序号后缀，统一为 `datapilot_schema_docs_m20_<model>_<embedding>_<YYYYMMDD_HHMMSS>`，防止重复 / 误复用旧 collection。
- 已同步到 `docs/state/schema-retrieval-milvus-embedding.md` 的「Milvus Collection 纪律」和「常用命令」示例；命名前先用 `date +%Y%m%d_%H%M%S` 取时间戳。

### [模块任务] M20 Schema Retrieval / Milvus Index Hygiene（2026-08-02）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `engine/schema_retrieval/*`、`engine/nl2sql/pipeline.py`、`app/api/query.py`、`eval/run_eval.py`、`scripts/audit_m20_eval_ground_truth.py`、`scripts/smoke_m20_milvus_index.py`、`tests/test_m20_schema_index_hygiene.py`、`.agent_work/temp/m20-notes.md`、`.agent_work/temp/m20-eval-ground-truth-audit.md`、`.agent_work/temp/m20-milvus-index-smoke.md` 和 M20 eval/triage artifacts。
- 关键记录：
  - 用户确认 M20 采用三条边界：Milvus 实验使用唯一 collection 名；`result_match` 本轮只做 oracle 可追溯标注和 MySQL audit，不切换到 MySQL oracle；formal case 强度、退款率题面和“已支付订单”题面只审查不改 YAML。
  - 新增 `schema_documents_hash()`，基于 `doc_id + keyword_text + vector_text` 生成 schema docs 指纹，用于报告索引版本。
  - `MilvusVectorIndex` 新增 collection hygiene：记录 `initial_row_count / inserted_document_count / final_row_count`；已有 clean collection 且维度匹配时复用不插入；已有 collection 行数或维度不匹配时拒绝复用并要求唯一 collection 或显式 reset。
  - `eval/run_eval.py` 在 `--pipeline-mode new_text2sql` 且 `SCHEMA_VECTOR_BACKEND=milvus` 时预建 run-scoped vector index，并通过 `app.state.schema_vector_index` 传入 `/api/query` -> `run_text2sql_pipeline()` -> `retrieve_schema()`，避免一个 eval run 内每个 case 重复灌入 193 条 schema docs。
  - Eval Markdown 报告新增 `Eval Runtime Metadata`，显式写出 `result_match_oracle_backend=sqlite_deterministic_seed`、`schema_docs_hash`、embedding provider/model/dimension、Milvus collection 和 row_count。
  - 新增 `scripts/audit_m20_eval_ground_truth.py` 生成 `.agent_work/temp/m20-eval-ground-truth-audit.md`，用当前 MySQL 执行 `expected_sql`，但不改变 scorer 口径。
  - 新增 `scripts/smoke_m20_milvus_index.py`，创建唯一 collection，验证 clean collection 下 `row_count == len(schema_documents)`，并输出五类典型 query 的 keyword/vector/merged hits。
- 验证快照：
  - MySQL audit：`.agent_work/temp/m20-eval-ground-truth-audit.md`；formal `10`、challenge `16`、diagnostic extra `16`，共 `42` 条且无重复 case id；14 条 `expected_sql` 在当前 MySQL 执行 `ok=14 error=0`；当前 `result_match` oracle 明确仍为 SQLite deterministic seed。
  - Focused tests：`pytest tests\test_m20_schema_index_hygiene.py tests\test_phase3a_schema_retrieval.py -q --basetemp=.agent_work\temp\pytest-m20-focused` -> `14 passed, 1 warning`。
  - Default smoke eval：`.agent_work/temp/m20-smoke-report.md` -> `passed=5/6`，报告显示 `result_match_oracle_backend=sqlite_deterministic_seed`、`schema_vector_index_reuse=not_applicable`。
  - Milvus index smoke：`.agent_work/temp/m20-milvus-index-smoke.md` -> PASS；collection `datapilot_schema_docs_m20_20260802_203949_007d1e09`，`schema_docs_count=193`、`final_row_count=193`、`schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`。
  - Clean Milvus + Qwen embedding diagnostic：DeepSeek `deepseek-v4-flash` + DashScope `qwen3.7-text-embedding`，unique collection `datapilot_schema_docs_m20_deepseek_qwenemb_20260802_a`，`.agent_work/temp/m20-deepseek-qwenemb-diagnostic-report.md` -> `passed=17/32`、`milvus_final_row_count=193`、`schema_vector_index_reuse=run_scoped`。
  - Failure distribution compare：`.agent_work/temp/m20-m19-polluted-vs-clean-deepseek-qwenemb-compare.md`；clean vs M19 polluted：`schema_retrieval 1 -> 1`、`schema_context 4 -> 5`、`query_plan 4 -> 5`、`result_match 2 -> 1`、`unknown 2 -> 0`。
  - Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic 尝试 900s 超时，只生成 21 行 partial trace，无 final report / triage；不作为结论。
  - Related regression：`pytest tests\test_phase3a_pipeline.py tests\test_m16_trace_router.py tests\test_m19_failure_triage.py tests\test_m20_schema_index_hygiene.py -q --basetemp=.agent_work\temp\pytest-m20-related` -> `27 passed, 1 warning`。
  - Full pytest：首次 300s 超时中断且无失败输出；复跑 `pytest -q --basetemp=.agent_work\temp\pytest-m20-full-2` -> `127 passed, 1 warning`。
  - `git diff --check`：仅 Windows LF/CRLF 提示，无 whitespace error。
- 结论：
  - M20 已修复 Milvus 实验链路的索引可信度问题：clean collection 可证明 193 条 schema docs，eval run 内不再重复 insert，报告能追溯 schema docs hash、collection、row_count、embedding 配置和 oracle backend。
  - Clean Milvus 后 DeepSeek + Qwen embedding diagnostic 为 `17/32`，低于 M19 污染链路 `19/32`，因此不能宣布 Qwen embedding 胜出；也不能据此自动切默认 embedding，后续仍需在 RAG / Hybrid 或单独 embedding 评估中继续看。
  - 默认配置不变：`SCHEMA_VECTOR_BACKEND=inmemory`、`SCHEMA_EMBEDDING_PROVIDER=deterministic`；Milvus / DashScope embedding 仍为显式实验路径。
- 遗留/后续：
  - `result_match` 是否切到 MySQL/current configured database 是长期 benchmark 口径决策，M20 未改。
  - Formal 多表题检查强度、`db_core_002` 退款率口径、`db_simple_002` 已支付订单题面仍需单独确认后再改 case。
  - 唯一 collection 策略会带来 collection 数量增长；后续可加显式 cleanup 工具，但 M20 不默认自动删除历史实验 collection。

### [实验/计划] M19 后续 Qwen embedding / Milvus A/B 复测与 M20 立项（2026-08-02）

- 触发原因：用户要求用 Qwen `qwen3.7-max` + Qwen embedding 再跑三类 eval，并追问 DeepSeek + Qwen embedding 效果差是否可能来自 Milvus 链路问题。
- 执行配置：
  - Qwen 主模型：`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-max`。
  - DeepSeek 主模型：`LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-v4-flash`。
  - Qwen embedding / Milvus：`SCHEMA_VECTOR_BACKEND=milvus`、`SCHEMA_EMBEDDING_PROVIDER=dashscope`、`QWEN_EMBEDDING_MODEL=qwen3.7-text-embedding`、`QWEN_EMBEDDING_DIMENSIONS=1024`、`LANGFUSE_ENABLED=false`。
- 验证快照：
  - Qwen `qwen3.7-max` + Qwen embedding：formal `8/10`、challenge `12/16`、diagnostic `20/32`；报告为 `.agent_work/temp/m19-qwen37max-qwenemb-formal-report.md`、`.agent_work/temp/m19-qwen37max-qwenemb-challenge-report.md`、`.agent_work/temp/m19-qwen37max-qwenemb-diagnostic-report.md`。
  - Qwen `qwen3.7-max` + 默认 embedding 对照为 formal `8/10`、challenge `12/16`、diagnostic `22/32`；diagnostic 对比见 `.agent_work/temp/m19-qwen37max-default-vs-qwenemb-diagnostic-compare.md`。
  - DeepSeek `deepseek-v4-flash` + Qwen embedding diagnostic 为 `19/32`；triage summary：`schema_retrieval=1`、`schema_context=4`、`query_plan=4`、`plan_validation=1`、`sql_guard=1`、`unknown=2`、`result_match=2`；报告见 `.agent_work/temp/m19-deepseek-qwenemb-diagnostic-report.md`。
- 新发现：当前 `build_schema_documents()` 生成 193 条 schema docs，但 Milvus collection `datapilot_schema_docs` 的 `row_count=19493`，约等于 `193 * 101`。排查代码发现 `MilvusVectorIndex.__init__` 每次初始化都会重新 embedding + insert 全量 schema docs，而 `retrieve_schema()` 默认会按 case 构建配置化 vector index；固定 collection 且 `MILVUS_RESET_COLLECTION=false` 时会被重复灌入。
- 结论：这轮 Qwen embedding / Milvus 结果不能直接判定 embedding 模型无效，只能说明当前 Milvus 实验链路不可信。已在 `docs/phase3b-langfuse-plan-v6.md` 新增 M20 `Schema Retrieval / Milvus Index Hygiene`，作为 M19 后续模块，先修 collection 生命周期、去重 / upsert、run 内 retriever 复用和 `schema_docs_hash`，再重新评估 embedding。
- 边界：不自动切默认模型、不自动切默认 embedding / Milvus、不改 eval case、不扩展到 RAG/Hybrid；这些长期影响选择仍需用户确认。

### [小修] AI 续接文档体系重构：state 分文档 + 必读规则（2026-08-02）

- 将 `AI_CONTEXT.md` 瘦身为续接仪表盘（当前状态 / 默认值 / 最近事实 / 路线判断 / 活跃坑，各表补日期列），并按职责拆出独立文档：`docs/state/runbook.md`（模型、embedding、LangFuse、eval 命令矩阵与运行纪律）、`docs/state/eval-baselines.md`（长期评测账本）、`docs/state/database-current-state.md`（数据库事实与 eval 排障口径，含数据异常菜单、RBAC 敏感字段优先于角色权限的表述）。
- 各文档顶部增加 Trigger 触发条件；`AI_CONTEXT.md` 将「续接阅读顺序」升级为「必读规则」：运行命令 / eval 数字 / 数据库事实 / 历史取舍等场景必须继续读对应文档，`CLAUDE.md` 同步，防止只读摘要就开工。
- 历史验证数字统一标注为历史快照并指向 eval-baselines / runbook；用户将四份文档移入 `docs/state/` 后同步入口文档和内部引用，归档目录旧引用保持原貌。

### [实验] M19 qwen3.7-max 三类 eval 对照（2026-08-02）

- 触发原因：用户确认 qwen3.8-max 当前不可用后，要求改用 `qwen3.7-max` 执行 formal / challenge / diagnostic 三类评测。
- 执行配置：`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-max`、`LANGFUSE_ENABLED=false`，保持 M19 本地 triage 输出，不改默认 `.env` / 代码兜底模型。
- 验证快照：
  - Formal：`.agent_work/temp/m19-qwen37max-formal-report.md` / `.agent_work/temp/m19-qwen37max-formal-triage.json`：`passed=8/10`；triage `schema_context=2`，动作 `fix_schema_desc=2`；失败 `p3a_multi_001` 缺 `coupon_order_count`、`p3a_multi_003` 缺 `category`。
  - Challenge：`.agent_work/temp/m19-qwen37max-challenge-report.md` / `.agent_work/temp/m19-qwen37max-challenge-triage.json`：命令行通过率 `passed=12/16`；triage summary `failed=5`（多出的 1 条是 `review_required` manual case）；stage 为 `result_match=1`、`schema_context=1`、`query_plan=1`、`schema_retrieval=1`、`unknown=1`；动作 `fix_pipeline=2`、`fix_schema_desc=1`、`manual_review=2`。
  - Diagnostic：`.agent_work/temp/m19-qwen37max-diagnostic-report.md` / `.agent_work/temp/m19-qwen37max-diagnostic-triage.json`：命令行通过率 `passed=22/32`；triage summary `failed=11`（含 1 条 manual/review case）；stage 为 `schema_context=6`、`schema_retrieval=2`、`result_match=1`、`plan_validation=1`、`unknown=1`；动作 `fix_schema_desc=6`、`fix_pipeline=2`、`manual_review=3`。
  - DeepSeek flash vs qwen3.7-max diagnostic 本地分布对比：`.agent_work/temp/m19-deepseek-vs-qwen37max-diagnostic-triage-compare.md`；qwen3.7-max 相比本轮 DeepSeek flash 少了 `query_plan`、`result_match`、`sql_generation`、`sql_guard`、`unknown` 各 1 个，但 `schema_context` 持平为 6，`schema_retrieval` 多 1 个。
- 结论：qwen3.7-max 在本轮 M19 三类 eval 上优于 `deepseek-v4-flash` 快照（8/10、12/16、22/32 vs 7/10、9/16、19/32），但 schema 上下文仍是主要失败来源，且模型默认切换属于长期基线选择；本次只记录为候选和 A/B 对照，不自动切默认。

### [模块任务] M19 Trace Failure Triage / LangFuse-driven Eval Analysis（2026-08-02）

- 改动范围：`eval/triage.py`、`eval/run_eval.py`、`tests/test_m19_failure_triage.py`、`docs/state/AI_CONTEXT.md`、`docs/state/AI_CONTEXT_CHANGELOG.md`、`docs/dev-log.md`、`.agent_work/temp/m19-notes.md`。未修改数据库、架构分层、安全策略、正式 eval case 集或 LangFuse Dataset/Experiment 编排。
- 关键记录：
  - 新增 `eval/triage.py` 作为 M19 failure triage 单一事实源，定义 `failure_stage` taxonomy、`needs_action` taxonomy、JSONL trace 读取、单 case 归因、批量摘要、triage JSON、LangFuse triage score payload 和本地 A/B failure distribution 对比。
  - `eval/run_eval.py` 的 Markdown 报告新增 `Failure Triage Summary`，包含 `failure_stage` 聚合、`needs_action` 聚合、Top cases 和 case 明细；新增 `--triage-json` 输出本地 JSON；新增 `--compare-triage-left/--compare-triage-right/--compare-triage-report` 生成本地分布对比 Markdown。
  - LangFuse 增强保持可选：只有 JSONL 中存在 `langfuse_trace_id` 且 `langfuse_write_status=ok` 的记录才回写 `triage:failed`、`triage:failure_stage`、`triage:needs_action`、`triage:confidence`。LangFuse disabled、SDK 不可用、trace id 缺失或 Cloud 写入失败时，本地 triage 不丢失，只在 score write 统计里显示 skipped/failed。
  - M19 不自动创建 Dataset、不实现 Webhook runner、不新增评测历史数据库、不改写 `eval/cases/*`；回归集候选只在 triage JSON / report 中建议，不直接落正式 benchmark。
  - 踩坑：安全类 expected block case 会有 `passed=True` 且 `error_type=sql_guard_blocked`，triage 失败状态必须跟随 eval 的 pass/skipped/review/status，而不是单看响应体 `error_type`，否则会把“正确拦截”误报成失败。
- 验证快照：
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m19_failure_triage.py tests\test_m17_scorers.py --basetemp=.agent_work\temp\pytest-m19-b`：15 passed，1 个既有 Starlette/httpx warning。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m19_failure_triage.py tests\test_m18_phase3b_smoke.py tests\test_m17_scorers.py tests\test_m16_trace_router.py --basetemp=.agent_work\temp\pytest-m19-c`：31 passed，1 warning。
  - 默认本地 smoke：`python -m eval.run_eval --cases eval\cases\smoke.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\m19-smoke-traces.jsonl --report .agent_work\temp\m19-smoke-report.md --triage-json .agent_work\temp\m19-smoke-triage.json`：`passed=6/6`，`langfuse_triage_scores=ok:0 skipped:24 failed:0`。
  - LangFuse enabled smoke（代理）：`LANGFUSE_ENABLED=true` + `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`，报告 `.agent_work/temp/m19-langfuse-smoke-report.md`：`passed=5/6`，`langfuse_scores=ok:27`，`langfuse_triage_scores=ok:24`。
  - Formal：`.agent_work/temp/m19-formal-report.md` / `.agent_work/temp/m19-formal-triage.json`：`passed=7/10`；triage `schema_context=1`、`plan_validation=1`、`query_plan=1`。
  - Challenge：`.agent_work/temp/m19-challenge-report.md` / `.agent_work/temp/m19-challenge-triage.json`：`passed=9/16`；triage `schema_context=1`、`result_match=3`、`query_plan=3`、`unknown=1`。
  - Diagnostic（challenge 16 + diagnostic extra 16）：`.agent_work/temp/m19-diagnostic-report.md` / `.agent_work/temp/m19-diagnostic-triage.json`：`passed=19/32`；triage `schema_context=6`、`schema_retrieval=1`、`result_match=2`、`plan_validation=1`、`sql_guard=1`、`unknown=2`、`query_plan=1`、`sql_generation=1`；动作聚合 `fix_schema_desc=7`、`fix_pipeline=5`、`manual_review=3`。
  - 本地分布对比：`.agent_work/temp/m19-formal-vs-challenge-triage-compare.md` 展示 formal vs challenge 的阶段差异，例如 `result_match 0 -> 3`、`query_plan 1 -> 3`。
  - 全量测试：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest --basetemp=.agent_work\temp\pytest-m19-full`：121 passed, 2 skipped, 1 warning。
- 遗留/后续：
  - 当前 triage 是启发式，不是绝对真因。`missing_columns` 第一版归为 `schema_context`，但后续可能细分为 schema 描述缺失、SQL alias、scorer strictness 或 prompt 输出列选择问题。
  - `review_required=True` 的困难 case 即使 trace 指向具体阶段，也默认保留 `manual_review`，避免把人工诊断题误标成自动修复候选。
  - M19 暴露出 deepseek-v4-flash 当前快照低于 M13 稳定基线，但真实 LLM 波动较大；这轮数字主要作为 M19 triage 验证和 Phase 3 RAG/Hybrid 前的参考，不直接作为默认模型切换结论。

### [实验] M19 重复 case 波动与 Qwen 3.8 availability probe（2026-08-02）

- 重复 case 波动：M19 formal / challenge / diagnostic 是三次独立真实 LLM eval，不是同一次 superset run 的切片。challenge 与 diagnostic 中相同 `case_id` 有 6 个结果或失败形态不同：`db_core_001`、`db_core_002`、`db_core_004`、`db_hard_001`、`db_multi_002`、`db_multi_004`。结论：读包含关系时不能把三次独立运行当作同一批结果；若要严格比较包含关系，应跑一次 superset，再按 case 集切子集统计。
- Qwen 3.8 probe：`LLM_PROVIDER=qwen; QWEN_MODEL=qwen3.8-max` 最小 DashScope chat completion 返回 HTTP 403 `access_denied`，当前账号/配置不可用；对照 `QWEN_MODEL=qwen3.7-max` 返回 `{"ok": true}`，说明 DashScope key/base URL 正常。未跑 qwen3.8-max 三类 eval。

### [小修] 主模型切换 deepseek-v4-pro → deepseek-v4-flash（2026-07-31）

- 改动范围：`.env`（新增 `LLM_PROVIDER=deepseek` / `LLM_MODEL=deepseek-v4-flash`，此前未显式设置，一直靠代码兜底）、`engine/nl2sql/generator.py` 两处兜底默认值、`.env.example`、`README.md` LLM 配置示例、`docs/state/AI_CONTEXT.md` 技术默认值快照。
- 关键记录：模型名配置本来就是"`.env` 的 `LLM_MODEL` 优先、代码 `deepseek-v4-pro` 兜底"结构（见 M12 修复），本次切换只是补上 `.env` 显式配置 + 把兜底值同步为 flash，零逻辑改动。L3 judge 独立走 `EVAL_JUDGE_MODEL`，不受影响；`scripts/run_qwen_ab_experiments.py` 的 A/B 实验模型硬编码是刻意设计，未改。
- 验证快照：
  - `get_default_llm_client()` 解析结果 `resolved model: deepseek-v4-flash`；真实 DeepSeek API 调用返回 `{"ok": true}`（HTTP 200，flash 模型名被 API 接受）。
  - `python -m pytest tests\test_m4_nl2sql.py tests\test_config.py --basetemp=.agent_work\temp\pytest-model-switch`：11 passed，1 个既有 Starlette/httpx deprecation warning。
- 遗留/后续：flash 是更快更便宜的非推理模型（archive 文档曾记为"JSON 模式失败的方案 B"），切换后未重跑 formal / challenge / diagnostic 基线，真实 LLM 效果待 Phase 3 RAG / Hybrid 评估时验证；若准确率下降再考虑按阶段分模型（规划用强模型、生成用 flash）。

### [小修] Phase 3B code review findings 修复（2026-07-30）

- 依据 `docs/phase3b-code-review-findings.md` 处理 Phase3B LangFuse / Trace / Scorer / Eval 审查问题；用户确认 P2-2 采用方案 B：危险 SQL 预检下沉到 `new_text2sql` pipeline 的统一 guard lifecycle，而不是在 API 层补临时 TraceStep。
- 修复重点：LangFuse SDK import failure 降级、只对 `langfuse_write_status=ok` 的 trace 回写 score、M18 smoke mapping 状态检查、危险 SQL blocked path 记录 `sql_guard` step、`equals` 不再做全 JSON substring、`result_match` 按列名对齐、Markdown report 输出 scorer 明细 / LangFuse score 写入结果。
- 仓库卫生：LangFuse Dataset CSV 从 git 跟踪移除并加入 ignore，保留本地文件仅作临时 UI 验证素材；正式 EvalBench dataset 仍应从 YAML case 或清洗后的 root trace 生成。

### [模块任务] M18 Smoke / Experiment / 阶段收尾（2026-07-30）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `scripts/smoke_phase3b_langfuse.py`、`tests/test_m18_phase3b_smoke.py`、`docs/state/AI_CONTEXT.md`、`docs/state/AI_CONTEXT_CHANGELOG.md`、`docs/dev-log.md`、`.agent_work/temp/m18-notes.md`、`.agent_work/temp/m18-experiment-workflow-cases.yaml`。用户导出的 LangFuse Dataset CSV 曾作为 UI 验证素材保留在项目根目录；2026-07-30 review 修复后已从 git 跟踪移除并加入 ignore。
- 关键记录：
  - 新增 `scripts/smoke_phase3b_langfuse.py`：一键验证配置摘要、真实 `/api/query`、JSONL trace 写入、DataPilot trace id 与 JSONL 匹配、LangFuse trace mapping、`rule:m18_smoke` Score 回写和 trace visibility 查询。脚本默认允许 `LANGFUSE_ENABLED=false` 时 Cloud 检查 SKIP；显式 `--require-langfuse` 时 LangFuse disabled / 缺 key / SDK 不可用 / score 或 visibility 失败均会 FAIL。
  - smoke 复用 `eval.run_eval.seeded_api_client()`，使用内存 SQLite seed + FastAPI TestClient 调真实 `/api/query`，不碰 MySQL 开发库，不绕过 API seam。
  - 脚本启动前显式 `configure_trace_router(build_trace_router(settings))`，避免 M16 模块级 router 在 import 时锁死旧环境变量。
  - Score 写入和 trace visibility 分开检查：Score 可按 `langfuse_trace_id` 直接写；trace/observation 查询可能受 ingestion 延迟或本机网络影响，脚本以独立 PASS / FAIL / PENDING / SKIP 呈现。
  - 手动 Experiment 结论：LangFuse UI 支持从 trace 创建 Dataset item；用户创建 `datapilot-m18-workflow-smoke-20260730` 并导出 5 条 ACTIVE items。`Run experiment -> via User Interface` 需要项目 LLM API key + prompt/model 配置；`via Webhook` 需要 remote experiment URL。当前 DataPilot 没有 webhook runner，因此不临时实现；后续 EvalBench 更适合通过 Webhook / SDK API 接入 dataset run。
  - 5 条 workflow smoke case 仅用于验证 Experiment 工作流，不替代 formal/challenge/diagnostic benchmark。DeepSeek 组本地 eval `passed=4/5`、`langfuse_scores=ok:25 skipped:0 failed:0`；Qwen `qwen3.7-plus` 组 `passed=3/5`、`langfuse_scores=ok:22 skipped:0 failed:0`。
  - Dataset CSV 复盘发现：1 条 item 可能从 `schema_retrieval` span/observation 生成，input/expected output 不是 root query/answer；M18 workflow smoke 可接受，但后续正式 EvalBench dataset 应从 case 定义或 root trace 统一生成样本。CSV metadata 包含 telemetry 噪音和 LangFuse public key（非 secret），后续正式数据集应清理 metadata。
- 参考资料：
  - 按 `langfuse` skill 重新读取要求；实现前用官方 LangFuse docs 确认 Scores / Datasets / Experiment 当前语义。M18 只吸收“score 与 visibility 可分离、Experiment UI/API/Webhook 边界”，未把手动 UI workflow 擅自替换成自动化 Experiment。
- 验证快照：
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m18_phase3b_smoke.py tests\test_m17_scorers.py --basetemp=.agent_work\temp\pytest-m18-final-focused`：9 passed，1 个既有 Starlette/httpx deprecation warning。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m compileall scripts\smoke_phase3b_langfuse.py tests\test_m18_phase3b_smoke.py`：通过。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_phase3b_langfuse.py --trace .agent_work\temp\m18-final-default-traces.jsonl --visibility-timeout-seconds 5`：返回 0；config snapshot PASS；`api.query` PASS；`jsonl.trace` PASS；LangFuse mapping / score / visibility 均因默认 `LANGFUSE_ENABLED=false` 正常 SKIP。
  - `$env:LANGFUSE_ENABLED='true'; $env:HTTP_PROXY='http://127.0.0.1:7897'; $env:HTTPS_PROXY='http://127.0.0.1:7897'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_phase3b_langfuse.py --trace .agent_work\temp\m18-final-langfuse-traces.jsonl --require-langfuse --visibility-timeout-seconds 45`：返回 0；trace mapping PASS，`langfuse_trace_id=8937e57d85814f74a47d25dc2f431c8e`；score PASS `ok=1`；trace visibility PASS `observations=8 waited=7s`。
  - 裸连真实 LangFuse require smoke 曾出现 `WinError 10013`：trace mapping 和 score 写入 PASS，但 visibility query FAIL；设置项目代理后复跑通过，判定为本机网络出口/权限问题。
  - DeepSeek 5-case Experiment workflow smoke eval：`passed=4/5`，`langfuse_scores=ok:25 skipped:0 failed:0`，报告 `.agent_work/temp/m18-experiment-deepseek-report.md`，trace `.agent_work/temp/m18-experiment-deepseek-traces.jsonl`。
  - Qwen `qwen3.7-plus` 5-case Experiment workflow smoke eval：`passed=3/5`，`langfuse_scores=ok:22 skipped:0 failed:0`，报告 `.agent_work/temp/m18-experiment-qwen37-plus-report.md`，trace `.agent_work/temp/m18-experiment-qwen37-plus-traces.jsonl`。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests -x --basetemp=.agent_work\temp\pytest-m18-full`：107 passed, 2 skipped, 1 warning。
- 遗留/后续：
  - 不在 M18 临时实现 remote experiment webhook。进入 Phase 3 RAG / Hybrid 或 EvalBench 时，再设计 LangFuse DatasetRun / Webhook / SDK runner 边界。
  - 正式 EvalBench dataset 应清洗 telemetry metadata，并明确从 root trace / case 定义生成 input、expected output，避免误选中间 span。
  - LangFuse Cloud 查询在当前 Windows 环境建议配置 Clash 代理；Cloud trace 只是 Phase 3B 实验记录，不作为 DataPilot 长期数据资产。

### [模块任务] M17 Scorer 分层与 Score 回写（2026-07-29）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `docs/phase3b-langfuse-plan-v6.md`、`eval/run_eval.py`、`eval/scorers/*`、`tests/test_m17_scorers.py`、`docs/state/AI_CONTEXT.md`、`.agent_work/temp/m17-notes.md`。`git diff --name-only` 只列出已跟踪文件，完整范围以 `git status --short` 为准。
- 关键记录：
  - 按用户要求先补 plan：当前执行路线改为在 `M16B` 分支继续 M17/M18，完成后整体合并回 `main`；不新增 `M17B` / `M18B` 双章节，现有 M17/M18 目标不变，只把底座调整为 M16B live lifecycle spans。
  - M17-1 调研结论：LangFuse Scores 是统一质量评估对象；Code evaluators 适合 deterministic checks，LLM-as-a-Judge 适合 semantic judgment。本模块不把规则评分迁到 LangFuse 托管 evaluator，原因是会引入 UI 配置、observation target 和 dispatcher 依赖；M17 先做本地 scorer 单一事实源 + SDK/API score 回写。
  - 新增 `eval/scorers/`：`base.py` 定义 `EvalScoreDetail` / `LangFuseScorePayload`，`rule_scorers.py` 承接 L1/L2 规则评分，`llm_judge.py` 实现显式开启的 `llm:correctness`，`langfuse_scores.py` 负责按 JSONL `langfuse_trace_id` 回写 Score，`factory.py` 提供统一 scorer 入口。
  - `eval.run_eval._score_case()` 保留旧函数名，但变为兼容薄壳；旧 Markdown pass/fail/reason 语义保持，例如 `expected_value_ok`、`blocked_as_expected` 不因 M17 迁移变成统一 `ok`。
  - `rule:latency_p95` 作为 numeric score 明细回写 LangFuse，但不参与旧 Markdown pass/fail 汇总。原因：延迟有运行环境波动，M17 的“不退化”门禁优先守住答案/安全/结果口径；性能分数用于观测趋势。
  - L3 judge 默认关闭；CLI `--judge-model` 优先于 `EVAL_JUDGE_MODEL`，两者都为空时不创建 L3 scorer。judge 失败返回 null/skipped detail，不阻断 eval。
  - Score 回写语义：只按 JSONL 里的 DataPilot `trace_id -> langfuse_trace_id` 映射构造 payload，不等待 LangFuse trace 可查询；没有有效映射时只写 Markdown / EvalResult，不回写 LangFuse。
- 参考资料：
  - 官方 LangFuse Scores / Code evaluators / LLM-as-a-Judge 文档；实现前按 `langfuse` skill 要求查阅当前文档。M17 只吸收“score 对象和 evaluator 用途边界”，不照搬托管 evaluator 流程。
- 验证快照：
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m17_scorers.py tests\test_phase3a_eval.py --basetemp=.agent_work\temp\pytest-m17-3`：27 passed，1 个既有 Starlette/httpx deprecation warning。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m compileall eval\run_eval.py eval\scorers`：通过。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --report .agent_work\temp\m17-eval-report-2.md --trace .agent_work\temp\m17-eval-traces-2.jsonl`：命令返回 0，`judge_model=<disabled>`，`langfuse_scores=ok:0 skipped:0 failed:0`，passed=3/6（当前 baseline smoke 现状）。
  - `$env:LANGFUSE_ENABLED='true'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --report .agent_work\temp\m17-langfuse-score-report.md --trace .agent_work\temp\m17-langfuse-score-traces.jsonl`：命令返回 0，`langfuse_scores=ok:16 skipped:0 failed:0`。
  - M16B live lifecycle score smoke（fake LLM + `new_text2sql` + `LANGFUSE_ENABLED=true`）：`passed=true`，`score_payload_count=6`，`score_write_result.ok=6`，JSONL `langfuse_span_mode=live` / `langfuse_write_status=ok`，`langfuse_trace_id=dbcbce212ae74e6cb998642310687dc4`。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests -x --basetemp=.agent_work\temp\pytest-m17-full`：104 passed, 2 skipped, 1 warning。
  - `git diff --check`：通过；仅 Windows CRLF warning。
- 遗留/后续：
  - M18 补正式 `scripts/smoke_phase3b_langfuse.py` 和手动 Experiment 记录；M17 的临时 live score smoke 只作为模块验证素材。
  - 真实 LangFuse smoke 中出现 SDK OTLP trace export `WinError 10013` warning / `Unexpected error occurred` 日志，但 eval 返回 0、JSONL 映射存在、Score writer 返回 ok。M18 smoke 应把 trace upload warning、score write status、trace visibility 分开显示，避免误判。

### [模块任务] M16B Trace Lifecycle 下沉预备分支（2026-07-29）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `engine/trace/lifecycle.py`、`engine/trace/recorder.py`、`engine/trace/langfuse_backend.py`、`engine/nl2sql/pipeline.py`、`engine/tools/sql_tool.py`、`app/api/query.py`、`tests/test_m16_trace_router.py`、`tests/test_phase3a_pipeline.py`、`docs/state/AI_CONTEXT.md`、`.agent_work/temp/m16b-notes.md`。
- 关键记录：
  - 用户确认重复 span 处理采用方案 1：`TraceRecord.langfuse_span_mode` 显式区分 `post_hoc` / `live`。M16 post-hoc 继续由 `LangFuseBackend.record()` 请求结束后拆 flat spans；M16B live 由 pipeline/tool lifecycle 执行中写 LangFuse spans，最终 backend 只保留 JSONL 映射字段，不再重复写 post-hoc spans。
  - 用户确认 SQL tool 分层采用方案 1：`run_sql_tool()` 增加可选 DataPilot `trace_context` 参数，在工具层内部记录 `sql_guard` / `sql_execution` spans。原因是 guard 与 DB 执行真实边界在 tool 内部；pipeline 事后补 span 改动更小，但不适合作为后续 RAG/Hybrid 底座。
  - 新增 `engine/trace/lifecycle.py`：`TraceContext` / `SpanHandle` / `TraceLifecycleSnapshot` 作为 DataPilot 自己的 lifecycle 抽象；业务 pipeline 不直接 import `langfuse`，LangFuse SDK 细节封装在内部 live writer。
  - `force_new_pipeline` 主链路迁移为 lifecycle 生成 `TraceStep`，覆盖 `schema_retrieval`、`schema_context`、`join_path`、`query_plan`、`plan_validation`、`sql_generation`、`sql_guard`、`sql_execution`、`chart_generation` 和 blocked/error path。
  - LangFuse root span 采用 live-only `datapilot-query` observation，不写入 JSONL `trace_steps`，避免打乱 eval 依赖的 step_index；JSONL 与 LangFuse step spans 保持同名。
  - M16B 统一图表步骤名为 `chart_generation`，替换旧 M11 的 `chart_decision` trace 命名。
- 参考资料：
  - 未浏览外部文档；实现依据 `docs/phase3b-langfuse-plan-v6.md` M16B 小节、M15 SDK 4.14.1 smoke 结果、M16 TraceRouter 现有实现和用户对方案 1 的确认。
- 验证快照：
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m16_trace_router.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m16b-3`：14 passed，1 个既有 Starlette/httpx deprecation warning。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests -x --basetemp=.agent_work\temp\pytest-m16b-full-2`：98 passed, 2 skipped, 1 warning；warning 为既有 Starlette/httpx deprecation。第一次 180s 全量跑到 69% 后超时，360s 复跑通过，判定为耗时波动。
  - 临时 live smoke（fake LLM + SQLite seed + `LANGFUSE_ENABLED=true` + `force_new_pipeline`）：HTTP 200，`safety_status=passed`，JSONL `langfuse_span_mode=live`、`langfuse_write_status=ok`，LangFuse trace URL：`https://jp.cloud.langfuse.com/project/traces/c1e4a46844fb49ea9cc2fb77a21b737d`。
- 遗留/后续：
  - M16B 是并行预备分支，不自动替换 M16 主线；后续按计划对比 M16A post-hoc flat spans 与 M16B lifecycle spans 的 UI 排障价值、代码侵入度和测试复杂度，再决定是否作为 RAG/Hybrid 观测底座。
  - M16B 不做 M17 scorer / score 回写，也不补 M18 正式 smoke 脚本和 Experiment workflow。

### [模块任务] M16 Trace 双写与降级（2026-07-28）

- 改动范围：`engine/trace/recorder.py`、`engine/trace/langfuse_backend.py`、`tests/test_m16_trace_router.py`；临时验证素材写入 `.agent_work/temp/m16-notes.md`、`.agent_work/temp/smoke_m16_trace_double_write.py`、`.agent_work/temp/m16-double-write-traces.jsonl`、`.agent_work/temp/m16-eval-*`。
- 关键记录：
  - 用户确认采用方案 A：TraceRouter + JSONL 主路 + LangFuse 旁路 + flat spans；不在 M16 伪造嵌套 span 和真实时间线，RAG/Hybrid 阶段 pipeline 埋点下沉后再补。
  - `append_trace(record, path=...)` 保持兼容入口，内部改为模块级 `TraceRouter`；新增 `build_trace_router(settings=None)` 和 `configure_trace_router(router)`，测试 / smoke 可在同一进程切换 LangFuse 开关。
  - `TraceRecord` 新增 `langfuse_trace_id`、`langfuse_trace_url`、`langfuse_write_status=ok/skipped/failed`，字段只进入 JSONL，不进入 `/api/query` 的 `AgentResponse`。
  - `LangFuseBackend` 使用 SDK 4.14.1 的 `start_observation(trace_context=...)` + `flush()`；成功时回填独立 32 位 hex `langfuse_trace_id`，异常由 router 捕获并标记 `failed`，JSONL 继续写入。
  - Router 顺序为 `LangFuseBackend -> JSONLBackend`：这样 LangFuse 成功/失败后的映射字段能写入同一行 JSONL；LangFuse 异常不阻断后续 JSONL。
  - Cloud payload 最小化：不上传完整 rows / docs，只上传 question、answer、安全状态、columns/tables、行数、step 摘要和 cost metadata。
- 参考资料：
  - 未浏览外部文档；实现依据 M15 本地 SDK 4.14.1 API smoke 结果和 `docs/phase3b-langfuse-plan-v6.md` 的 M16 设计。
- 验证快照：
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m16_trace_router.py --basetemp=.agent_work/temp/pytest-m16-final-related`：6 passed，1 个既有 Starlette/httpx warning。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m5_agent_response.py tests\test_config.py --basetemp=.agent_work/temp/pytest-m16-related-1`：7 passed，1 个既有 Starlette/httpx warning。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\smoke_m16_trace_double_write.py`：真实 LangFuse + JSONL 双写通过，`langfuse_trace_id=e62319e3b05944ca90d4fbc6540cb5df`，`langfuse_write_status=ok`。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\check_m15_langfuse_visibility.py e62319e3b05944ca90d4fbc6540cb5df`：`visible_after_seconds=0.7`，`score_count=0`（M16 不写 score）。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --trace .agent_work/temp/m16-eval-traces.jsonl --report .agent_work/temp/m16-eval-report.md`：passed=6/6；抽查 JSONL 首行 `langfuse_trace_id=None`、`langfuse_write_status=skipped`。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m16-full-final-2`：96 passed, 2 skipped, 1 warning；warning 为既有 Starlette/httpx deprecation。一次 300s 全量复跑超时，420s 复跑通过，判定为耗时波动。
- 遗留/后续：
  - M17 接 Scorer 分层与 Score 回写，按 `langfuse_trace_id` 写 LangFuse score；M16 只写 trace，不写 score。
  - LangFuse flat spans 暂不表达真实父子嵌套 / start-end 时间线；RAG/Hybrid 阶段补更细粒度 pipeline 埋点。

### [模块任务] M15 LangFuse Cloud 接入基线（2026-07-28）

- 改动范围：`app/core/config.py`、`.env.example`、`pyproject.toml`、`tests/test_config.py`；临时验证素材写入 `.agent_work/temp/m15-notes.md`、`.agent_work/temp/smoke_m15_langfuse_sdk.py`、`.agent_work/temp/check_m15_langfuse_visibility.py`。
- 关键记录：
  - 复跑 LangFuse Cloud JP smoke：`auth_check`、span/observation 写入、`create_score(trace_id=...)`、`flush()` 均通过，trace `a5b22262bb154b3a9b08b0b09b5f8cc5` 约 `0.6s` 可通过 SDK 查询，score_count=1。
  - 固定双 ID 策略：DataPilot 请求级 `trace_id` 继续用现有 UUID；LangFuse trace id 由 DataPilot 使用独立 `uuid4().hex` 生成。原因是 SDK 4.14.1 要求传入 trace id 为 32 位小写 hex，且这样不会让 LangFuse 接管 API / JSONL / eval 主链路 ID。
  - SDK 基线固定为 `langfuse==4.14.1`，纳入 `pyproject.toml` 的 `observability` optional extra；默认 `LANGFUSE_ENABLED=false`，未启用时原链路不要求安装该 extra。
  - `Settings` 新增 `langfuse_enabled`、`langfuse_public_key`、`langfuse_secret_key`、`langfuse_base_url`、`eval_judge_model`；删除未使用的 LangSmith 字段，`rg -n "langsmith_|LANGSMITH" app engine eval scripts tests .env.example pyproject.toml` 无命中。
  - 踩坑：SDK 4.14.1 没有旧版 `client.trace()` builder；M16 应使用 `start_observation(trace_context=...)`、`create_score(trace_id=...)`、`flush()` 这组 API。
- 参考资料：
  - 未浏览外部文档；本次以本地已安装 SDK 4.14.1 的真实签名和 smoke 结果为准。
- 验证快照：
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\smoke_m15_langfuse_sdk.py`：PASS，输出 Cloud base URL、DataPilot trace id、LangFuse trace id、trace URL、auth/observation/score/flush PASS。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\check_m15_langfuse_visibility.py a5b22262bb154b3a9b08b0b09b5f8cc5`：`visible_after_seconds=0.6`，`score_count=1`。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_config.py --basetemp=.agent_work/temp/pytest-m15-config`：4 passed。
  - `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m15-full-2`：90 passed, 2 skipped, 1 warning；warning 为既有 Starlette/httpx deprecation。
- 遗留/后续：
  - M16 才接入 Trace 双写与降级；M15 不改 `/api/query` 响应契约，不替代 JSONL。
  - DataPilot Phase 3B 不默认 self-host；EvalBench 阶段再做完整 self-host 部署 spike。

