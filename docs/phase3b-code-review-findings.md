# Phase 3B Code Review Findings

审查范围：Phase3B 的 LangFuse / Trace / Scorer / Eval 链路，以及新增 `docs/eval-observability-guide.md`。本次只做代码审查，不修改业务代码。

结论摘要：未发现 P0 级“必然导致数据破坏或主链路完全不可用”的问题；但发现 2 个 P1，其中一个会在 `LANGFUSE_ENABLED=true` 且未安装 SDK 时打破 `new_text2sql` 本地 eval/API 降级底线，另一个是已提交的 LangFuse Dataset CSV 含 Cloud project/trace 元数据和 public key。

## P0

无。

## P1

### P1-1：live lifecycle 的 LangFuse SDK 导入未被降级保护包住

**问题**：`build_trace_context()` 在 `LANGFUSE_ENABLED=true` 且 key 存在时，会先执行 `from langfuse import Langfuse`，再进入 `try` 构造 `_LangFuseLiveWriter`。如果环境没有安装 optional extra `langfuse`，`ImportError` 会直接冒泡，`force_new_pipeline/new_text2sql` 请求会在 pipeline 起点失败，而不是降级为只写 JSONL。

**影响**：这违反 Phase3B 的核心底线：SDK 不可用时 `/api/query`、JSONL、本地 eval 仍应可用。尤其 `eval/run_eval.py --pipeline-mode new_text2sql` 会通过 API 触发 `run_text2sql_pipeline()`，因此本地回归在“启用了 LangFuse 但没装 SDK”的机器上可能直接失败。

**证据文件与行号**：

- `engine/trace/lifecycle.py:395` 到 `engine/trace/lifecycle.py:398`：`from langfuse import Langfuse` 在 `try` 外。
- `engine/nl2sql/pipeline.py:226` 到 `engine/nl2sql/pipeline.py:228`：每次新 pipeline 都调用 `build_trace_context()`。
- `docs/phase3b-langfuse-plan-v6.md:130`、`docs/phase3b-langfuse-plan-v6.md:940`：文档要求 LangFuse/SKD 报错时 API、JSONL、规则评分和 Markdown 报告仍可用。
- `tests/test_m16_trace_router.py:294` 到 `tests/test_m16_trace_router.py:330`：live lifecycle 成功路径只通过 fake factory 测试，没有覆盖 SDK import failure。

**建议修复方向**：把 SDK import 放进 `try` 块内；ImportError 时返回 `TraceContext(initial_write_status="failed")`，继续产出本地 `trace_steps`。补一个单测：`LANGFUSE_ENABLED=true`、key 存在、`client_factory=None`、模拟 `langfuse` 不可导入时，`build_trace_context().snapshot()` 不抛异常且 `langfuse_write_status="failed"`。

### P1-2：LangFuse Dataset CSV 已被提交，包含 Cloud 元数据、public key 和 trace 数据

**问题**：根目录 `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv` 是已跟踪文件，内容包含 LangFuse `projectId`、`datasetId`、`sourceTraceId`、`htmlSourcePath`、业务问题/期望输出、`datapilot_trace_id`、`resourceAttributes`，以及 `scope.attributes.public_key`。虽然 public key 不是 secret key，但它仍是可关联 Cloud project 的真实观测元数据。

**影响**：这不适合作为普通仓库资产提交。它会泄露实验 project/dataset/trace 标识、业务 trace 样本和 telemetry 噪音，并且 CSV 第 6 行还显示一个 dataset item 来自 `schema_retrieval` observation，而不是 root query，后续如果被误当正式 benchmark 会污染评测口径。

**证据文件与行号**：

- `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv:1`：包含 `projectId`、`datasetId`、`sourceTraceId`、`sourceObservationId` 等导出字段。
- `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv:2` 到 `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv:5`：metadata 中包含 `scope.attributes.public_key`、`datapilot_trace_id` 和 Cloud trace path。
- `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv:6`：input/expected output 来自 `schema_retrieval` span 摘要，不是 root query/answer。
- `docs/AI_CONTEXT_CHANGELOG.md:26`：变更记录已承认 CSV metadata 包含 telemetry 噪音和 LangFuse public key，正式数据集应清理。
- `.gitignore:7` 到 `.gitignore:10`：只忽略 `.agent_work/temp/*` 和 `eval/traces/*.jsonl`，没有防止根目录 dataset CSV 被提交。

**建议修复方向**：从 git 跟踪中移除该 CSV，若需要保留复盘素材，移到 `.agent_work/temp/` 或清洗后放文档附录；补 `.gitignore` 规则覆盖 `*-dataset_items-export-*.csv` / `*-lf-dataset_items-export-*.csv`；正式 EvalBench dataset 只从 YAML case 或清洗后的 root trace 生成。

## P2

### P2-1：Score 回写只看 `langfuse_trace_id`，不校验 `langfuse_write_status`

**问题**：`build_langfuse_score_payloads()` 只要 JSONL 中存在 `langfuse_trace_id` 就构造 score payload，没有检查 `langfuse_write_status` 是否为 `ok`。而 live lifecycle 在 flush 失败时仍会返回 `_live_writer.trace_id` 和 `langfuse_write_status="failed"`。M18 smoke 的 mapping 检查也只要 enabled + 有 trace id 就 PASS，即使 detail 里显示 status failed。

**影响**：网络/flush 失败时，eval 可能继续尝试给一个未确认写入成功的 trace 回写分数，造成 `langfuse_scores=ok` 与 trace 实际可见性不一致，甚至产生孤儿 score 或误导排障。JSONL/Markdown 主链路仍可用，但 LangFuse 旁路的健康状态会被高估。

**证据文件与行号**：

- `engine/trace/lifecycle.py:218` 到 `engine/trace/lifecycle.py:236`：flush 异常时状态置为 `failed`，但 snapshot 仍返回 `langfuse_trace_id`。
- `eval/scorers/langfuse_scores.py:116` 到 `eval/scorers/langfuse_scores.py:119`：映射只读取 `trace_id` 和 `langfuse_trace_id`。
- `eval/scorers/langfuse_scores.py:93` 到 `eval/scorers/langfuse_scores.py:99`：只要映射存在就生成 payload。
- `scripts/smoke_phase3b_langfuse.py:125` 到 `scripts/smoke_phase3b_langfuse.py:131`：`jsonl.langfuse_mapping` 有 id 即 PASS，未把 `langfuse_write_status!="ok"` 判为 FAIL/PENDING。

**建议修复方向**：`_load_langfuse_trace_id_map()` 只纳入 `langfuse_write_status=="ok"` 的记录；或在 payload metadata 中保留 status 但默认不回写 failed trace。M18 smoke 的 `jsonl.langfuse_mapping` 在 `--require-langfuse` 下应要求 `langfuse_write_status=="ok"`。

### P2-2：API 层危险 SQL 预检绕过 lifecycle，导致 blocked path 缺少 `sql_guard` step

**问题**：`force_new_pipeline` 分支在调用 `run_text2sql_pipeline()` 前先用 `_looks_like_dangerous_sql()` 和 `validate_readonly_sql()` 拦截危险输入。这个分支没有创建 `TraceContext`，也没有传入 `trace_steps`，因此 JSONL 中只会有 root/post-hoc trace，没有 `sql_guard` step；CSV 中的 DROP TABLE 样本也显示 `trace_step_count=0`。

**影响**：安全拦截类 case 是生产排障和 eval 的关键路径，但最直观的恶意 SQL 输入缺少 `sql_guard` span/step，和 Phase3B “blocked path 也应覆盖 SQL Guard”的观测目标不一致。后续失败归因器会很难区分“API 预检拦截”和“SQL Tool Guard 拦截”。

**证据文件与行号**：

- `app/api/query.py:279` 到 `app/api/query.py:294`：危险 SQL 在 pipeline 前直接返回 `_blocked_response()`。
- `app/api/query.py:126` 到 `app/api/query.py:130`：`_blocked_response()` 默认 `trace_steps=None`、`langfuse_write_status="skipped"`、`langfuse_span_mode="post_hoc"`。
- `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv:3`：DROP TABLE case 的 metadata 中 `trace_step_count=0`。
- `docs/phase3b-langfuse-plan-v6.md:545`：计划要求 blocked 路径 SQL Guard / plan validation blocked 时 span 正常 close。

**建议修复方向**：把危险 SQL 预检也纳入 `TraceContext`，至少记录一个 `sql_guard` step，或把预检逻辑下沉到 pipeline/tool 的统一 guard 边界。注意保持旧模板链路行为不变。

### P2-3：`equals` scorer 实际是 contains，可能误判通过

**问题**：`_score_output_check()` 中 `contains` 和 `equals` 都用 `case.check_value not in text` 判断。也就是说 `equals` 并没有做等值比较，只要期望值出现在整个 JSON body 文本中就通过。

**影响**：使用 `check.type: equals` 的 case 可能被错误放行。例如期望答案为 `"10"`，实际 body 里 SQL、trace、rows 任意位置出现 `"10"` 都可能通过。这会让 Markdown pass/fail 和 LangFuse `rule:equals` score 同时带着错误口径。

**证据文件与行号**：

- `eval/scorers/rule_scorers.py:250` 到 `eval/scorers/rule_scorers.py:253`：`contains` 和 `equals` 都是 substring check。
- `docs/eval-observability-guide.md:121` 到 `docs/eval-observability-guide.md:123`：文档把 `contains` / `equals` 作为 L2 结果评分列出，使用者会自然理解为两种不同语义。

**建议修复方向**：明确 `equals` 的目标字段。最小修法是对 `answer` 做严格等值；更稳的是在 YAML check 中增加 `field`，如 `answer` / `rows[0].field` / `body_json`，并给 `equals` 增加反例测试。

### P2-4：`result_match` 按行列位置比较值，不校验列名或排序语义

**问题**：`_rows_match()` 只比较行数、列数和 `actual_row.values()` 与 `expected_row.values()` 的位置值，没有按列名对齐，也没有处理无序结果集。两个结果集列名不同但值顺序相同会误判通过；列顺序不同但语义相同会误判失败；未显式 `ORDER BY` 的 expected_sql / generated SQL 也会有顺序波动。

**影响**：`result_match` 是当前 L2 结果正确性的核心规则，比 LLM judge 更应该可靠。当前位置比较会让一些 SQL 等价变体被误杀，也会让别名/列语义错误被漏判，进而污染 Markdown pass/fail 与 LangFuse `rule:result_match` score。

**证据文件与行号**：

- `eval/scorers/rule_scorers.py:330` 到 `eval/scorers/rule_scorers.py:334`：expected SQL 执行结果直接转 dict。
- `eval/scorers/rule_scorers.py:385` 到 `eval/scorers/rule_scorers.py:405`：比较逻辑只看行数、列数和值位置，不看列名。

**建议修复方向**：先按列名对齐比较；对明确无序的聚合列表 case，在 YAML check 中增加 `order_insensitive: true` 或要求 expected_sql/generated SQL 都含稳定排序。补“列名错但值同”“列顺序不同但语义同”“行顺序不同”的 scorer 单测。

### P2-5：`parent_step_id` 混用了 QueryPlan step id 和 TraceStep 父子关系语义

**问题**：`TraceStep` 只有 `step_index/name/step_type/.../parent_step_id`，没有自己的 `step_id` 字段；但 pipeline 把 `plan_step.step_id` 填进 `sql_generation`、`sql_guard`、`sql_execution` 的 `parent_step_id`。这不是一个可解析到某条 TraceStep 的父节点 id，而是 QueryPlan 内部 step id。

**影响**：短期 LangFuse 只是 flat spans，问题不致命；但一旦后续根据 `parent_step_id` 构建 DAG/span tree，会出现父节点找不到或把 QueryPlan step 当 TraceStep 的 ID 混用。对使用者来说，字段名会暗示“这是 trace 父子关系”，实际却是 plan-step 引用。

**证据文件与行号**：

- `engine/trace/recorder.py:34` 到 `engine/trace/recorder.py:43`：`TraceStep` 没有 step id，只有 `parent_step_id`。
- `engine/nl2sql/pipeline.py:367` 到 `engine/nl2sql/pipeline.py:368`：`sql_generation` 的 parent 使用 `plan_step.step_id`。
- `engine/nl2sql/pipeline.py:411` 到 `engine/nl2sql/pipeline.py:420`：`sql_guard/sql_execution` 的 parent 也使用 `plan_step.step_id`。
- `engine/trace/lifecycle.py:320` 到 `engine/trace/lifecycle.py:323`：LangFuse span metadata 继续写出 `parent_step_id`。

**建议修复方向**：拆字段语义：保留 `plan_step_id` 表达计划引用；若要表达 trace 父子关系，给 TraceStep 增加稳定 `step_id`，并让 `parent_step_id` 只引用 TraceStep 的 `step_id`。在此之前，文档里应说明当前不是可解析的 span tree。

## P3

### P3-1：Markdown report 不展示 scorer 明细和 LangFuse score 回写结果，排查口径不够闭环

**问题**：`EvalResult` 已保存 `score_details`，CLI 也会打印 `langfuse_scores=ok/skipped/failed`，但 `write_report()` 只输出汇总 reason / issue_tags / trace_id，没有列出每条 `rule:*` / `llm:*` detail 的 value、skipped、reason，也没有记录 LangFuse score 写入计数。

**影响**：Markdown 是主链路报告，但现在无法从报告本身确认“哪些 score 被计算、哪些被跳过、哪些回写到 LangFuse”。当 stdout 丢失或只分享 report 时，排查者只能重新读 JSONL 或重跑 eval。

**证据文件与行号**：

- `eval/run_eval.py:352` 到 `eval/run_eval.py:471`：`write_report()` 未输出 `score_details`。
- `eval/run_eval.py:490` 到 `eval/run_eval.py:502`：score payload 构造和写入发生在 report 写完之后，只打印到 stdout。
- `docs/eval-observability-guide.md:182` 到 `docs/eval-observability-guide.md:189`：文档要求用户看命令输出里的 `langfuse_scores`，但没有提醒 report 不包含该信息。

**建议修复方向**：在 Markdown 增加 `Score Summary` 和每 case 的 compact `score_details` 表；或至少在报告头写入 LangFuse score write result。这样 JSONL、Markdown、LangFuse 三个口径更容易对账。

### P3-2：`eval-observability-guide.md` 对 JSONL 覆盖范围略有夸大

**问题**：文档说“每次请求都会写一行 JSONL trace”，又把 `trace_steps` 描述成最重要过程信息。但实际 eval 中因 pipeline mode 不支持而 skipped 的 case 不会调用 API，也就不会有 trace；旧 baseline/template 链路也可能没有 `trace_steps` 或只有 post-hoc root。

**影响**：这会误导使用者以为 report 里的每个 case 都一定能在 JSONL 找到一行、且每行都有完整 `trace_steps`。排查 skipped/baseline case 时容易白找。

**证据文件与行号**：

- `docs/eval-observability-guide.md:11` 到 `docs/eval-observability-guide.md:13`：表述为“每次请求都会写一行 JSONL trace”。
- `docs/eval-observability-guide.md:71` 到 `docs/eval-observability-guide.md:83`：列出完整 `trace_steps`，但未说明只主要覆盖 `new_text2sql`。
- `eval/run_eval.py:283` 到 `eval/run_eval.py:311`：pipeline mode skipped case 直接 append `EvalResult` 并 continue，不发 API 请求。
- `docs/eval-observability-guide.md:435` 到 `docs/eval-observability-guide.md:437`：文档后面才说明当前 span 主要覆盖 `new_text2sql`，但前文主链路部分没有同等提醒。

**建议修复方向**：补一句边界：JSONL 是“每个实际进入 `/api/query` 的请求一行”；`trace_steps` 完整覆盖主要指 `new_text2sql/force_new_pipeline`，baseline/skipped case 可能没有对应步骤。

### P3-3：测试还不足以证明 Phase3B 降级和评分口径可靠

**问题**：现有测试覆盖了 post-hoc router、fake live writer、基础 scorer 和 smoke 状态，但缺少几类容易踩坑的负向场景。

**影响**：测试通过不能证明生产级可靠性。尤其是 SDK import failure、failed trace 不回写 score、安全 blocked span、`equals` 反例和 `result_match` 列/行顺序问题，都能在现有测试下漏掉。

**证据文件与行号**：

- `tests/test_m16_trace_router.py:186` 到 `tests/test_m16_trace_router.py:217`：只测 post-hoc backend 失败和缺 key 降级。
- `tests/test_m16_trace_router.py:294` 到 `tests/test_m16_trace_router.py:330`：live lifecycle 只测 fake SDK 成功路径。
- `tests/test_m17_scorers.py:54` 到 `tests/test_m17_scorers.py:74`：只覆盖 happy path summary。
- `tests/test_m17_scorers.py:110` 到 `tests/test_m17_scorers.py:150`：score payload mapping 测试没有覆盖 `langfuse_write_status="failed"`。
- `tests/test_m18_phase3b_smoke.py:15` 到 `tests/test_m18_phase3b_smoke.py:49`：smoke 测试覆盖 disabled/require disabled，但没有覆盖 enabled + trace status failed。

**建议修复方向**：补最小测试矩阵：SDK import failure、LangFuse enabled + live writer flush failure、JSONL failed status 不生成 score payload、force_new_pipeline 危险 SQL 仍有 `sql_guard` step、`equals` 反例、`result_match` 列名/列顺序/行顺序反例。

