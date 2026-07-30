# DataPilot AI Context Changelog（技术档案变更记录）

> 这里保存 `docs/AI_CONTEXT.md` 拆出的完整历史变更、实验记录和模块档案。续接任务时先读 `AI_CONTEXT.md` 的当前状态；只有需要追溯原因、验证快照或历史实验时再读本文。

M13 之后的新增记录使用标题标签，帮助 AI 快速筛选阅读优先级：

- `[模块任务]`：功能、架构、默认行为、安全口径、评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM eval、smoke 或会影响路线判断的实验结论。
- `[验收]`：accept-module、阶段验收、明确的模块完成状态。
- `[小修]`：文档措辞、口径同步、注释补充、轻量整理；只需简写，不要求完整模板。

未来新增记录优先使用这些标签；小修可以只写一段话，模块任务建议包含：改动范围、关键记录（比如关键决策、实验结果、新发现）、参考资料、验证快照、遗留/后续。

## 变更记录（新的在上）

### [模块任务] M18 Smoke / Experiment / 阶段收尾（2026-07-30）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `scripts/smoke_phase3b_langfuse.py`、`tests/test_m18_phase3b_smoke.py`、`docs/AI_CONTEXT.md`、`docs/AI_CONTEXT_CHANGELOG.md`、`docs/dev-log.md`、`.agent_work/temp/m18-notes.md`、`.agent_work/temp/m18-experiment-workflow-cases.yaml`。用户导出的 LangFuse Dataset CSV `1785405281245-lf-dataset_items-export-<REDACTED_LANGFUSE_PROJECT_ID>.csv` 保留在项目根目录作为 UI 验证素材。
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

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `docs/phase3b-langfuse-plan-v6.md`、`eval/run_eval.py`、`eval/scorers/*`、`tests/test_m17_scorers.py`、`docs/AI_CONTEXT.md`、`.agent_work/temp/m17-notes.md`。`git diff --name-only` 只列出已跟踪文件，完整范围以 `git status --short` 为准。
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

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；涉及 `engine/trace/lifecycle.py`、`engine/trace/recorder.py`、`engine/trace/langfuse_backend.py`、`engine/nl2sql/pipeline.py`、`engine/tools/sql_tool.py`、`app/api/query.py`、`tests/test_m16_trace_router.py`、`tests/test_phase3a_pipeline.py`、`docs/AI_CONTEXT.md`、`.agent_work/temp/m16b-notes.md`。
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

### [小修] AI_CONTEXT 拆分为当前快照 + Changelog（2026-07-27）

- 按用户确认，将 `docs/AI_CONTEXT.md` 的完整历史变更记录拆到 `docs/AI_CONTEXT_CHANGELOG.md`；`AI_CONTEXT.md` 保留当前状态、默认配置、最新基线、重要实验结论、活跃坑和 changelog 索引，减少后续 AI 续接时默认加载的历史上下文。
- 同步更新 `AGENTS.md` / `CLAUDE.md`、`.claude/skills/finish-module/SKILL.md` 和 `docs/phase3a-plan.md` 的开发记录规则：完整模块档案、真实 LLM eval、A/B 实验和 smoke 结论写入 changelog；影响当前路线的摘要再同步到 `AI_CONTEXT.md`。
- 同轮将真实 `.env` 静默补齐 `DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` 与 `DASHSCOPE_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/api/v1`，不输出任何 API key。

### [实验] Qwen / DashScope 主模型与 Embedding Provider 临时 A/B（2026-07-27）

- 改动范围：`app/core/config.py`、`engine/nl2sql/generator.py`、`engine/schema_retrieval/embedding_provider.py`、`engine/schema_retrieval/retriever.py`、`.env.example`、`scripts/run_qwen_ab_experiments.py`、相关配置 / LLM / embedding 单元测试；同步记录本次临时实验结论，不切默认。
- 关键记录：
  - 新增 Qwen / DashScope 显式 provider 支持：`LLM_PROVIDER=qwen` 可走 DashScope OpenAI-compatible chat completion；`SCHEMA_VECTOR_BACKEND=milvus` + `SCHEMA_EMBEDDING_PROVIDER=dashscope|qwen` 可走 DashScope `qwen3.7-text-embedding`。
  - 默认保持 `LLM_PROVIDER=deepseek` 与 `SCHEMA_VECTOR_BACKEND=inmemory` / `SCHEMA_EMBEDDING_PROVIDER=deterministic`，避免 Phase 3A 收口基线被联网模型、Milvus 服务状态、费用和非确定性影响。
  - 本轮主模型第一轮 formal 初测：DeepSeek formal `9/10`；Qwen `qwen-plus` formal `7/10`。该结果不能证明 Qwen 系列整体不适合 Agent，只说明在当前 DataPilot prompt / JSON 解析 / SQL 兜底均长期按 DeepSeek 调过的前提下，`qwen-plus` 这个旧/通用入口不适合作为 Qwen 主模型代表。
  - 改测官方新代际模型 `qwen3.7-plus` 后，formal 与 DeepSeek 持平：DeepSeek `9/10`、Qwen `qwen3.7-plus` `9/10`；challenge 上 Qwen 略高：DeepSeek `12/16`、Qwen `qwen3.7-plus` `13/16`。失败形态不同：DeepSeek formal 主要卡 `p3a_multi_003` LLM 生成失败；Qwen formal 主要卡 `p3a_multi_001` 缺 `coupon_order_count`。challenge 中 Qwen 过了 DeepSeek 未过的 `db_core_003`、`db_multi_002`，但仍卡 `db_core_004` 结果口径、`db_multi_001` alias/列名和 `db_hard_001` LLM 生成。
  - diagnostic 补测后，DeepSeek `24/32`，Qwen `qwen3.7-plus` `21/32`。这组更像边界体检：DeepSeek 仍有结果口径、LLM 生成失败、plan validation 和 expected columns 严格性问题；Qwen 暴露出更多漏表/漏列和证据字段不足问题，例如 `products`、`supplier_name`、`coupon_order_count`、`doc_title`。结论调整为：Qwen `qwen3.7-plus` 可继续作为强候选和 A/B 对照，但当前 Phase 3A 主模型默认仍保留 DeepSeek。
  - `qwen3.7-max` diagnostic 追加测试为 `22/32`，略高于 `qwen3.7-plus`，但低于 DeepSeek。`qwen3.7-max` 过了 DeepSeek 未过的 `db_join_003`、`db_plan_004`，说明复杂 join / plan 题有上限优势；但独有失败包括 blocking 的 `db_core_002` LLM 生成失败、`db_multi_002` 缺 `category`、`db_plan_002` plan validation failed、`db_trace_002` 缺 `coupon_order_count`。不看分数只看错法，`qwen3.7-max` 的独有错误比 DeepSeek 更影响主线稳定性，所以仍不切默认。
  - 本轮 embedding formal 初测：`Milvus + SiliconFlow BAAI/bge-m3` formal `8/10`；`Milvus + DashScope qwen3.7-text-embedding` formal `9/10`。Qwen embedding 在 formal 上略好，值得继续跑 challenge / diagnostic；但仍未达到足以替换默认 deterministic in-memory 的证据标准。
  - 2026-07-27 20:11 补跑本地 retrieval formal baseline：DeepSeek + `inmemory + deterministic` formal `8/10`，失败为 `p3a_multi_001` 缺 `coupon_order_count`、`p3a_multi_003` 缺 `category`。和 embedding formal 组相比：本地 `8/10`、SiliconFlow BGE-M3 `8/10`、Qwen embedding `9/10`。这说明 Qwen embedding 仍略好，但差距只有 1 题，且 formal 受真实 LLM 波动影响，不能据此切默认。
  - 2026-07-27 按用户建议同步 `AI_CONTEXT.md`「最新评测基线」：保留 M13 后稳定快照 formal `10/10`、challenge `14/16`、diagnostic `23/32`；并新增 M14-lite 后临时真实 LLM 快照。M14-lite 后数字反映更严格 result_match / 安全 / trace 口径和真实 LLM 波动，不能直接当作 M13 退化结论。
  - qwen3.7-text-embedding 口径：官方文档推荐纯文本 / 代码场景使用，支持 1024 默认维度、最长 128K token、批量最多 20 条，并支持 instruct / sparse 等高级功能。本次只接 dense 1024，未启用 sparse / hybrid / rerank。
  - Milvus 启动坑：在 Docker Desktop 直接启动单个 `milvusdb/milvus:v3.0-beta` 容器会自动退出；正确本地方式是官方 Docker Compose 三容器 `milvus-standalone` + `milvus-etcd` + `milvus-minio`，端口 `19530` / `9091`。本次 compose 文件放在 `.agent_work/temp/milvus/docker-compose.yml`，属于本地实验环境，不写入 `.env`。
- 验证快照：
  - 相关单元测试：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_config.py tests\test_m4_nl2sql.py tests\test_m9_2_siliconflow_embedding.py tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work\temp\pytest-qwen-final-related` -> 23 passed，1 个既有 Starlette / httpx warning。
  - 实验脚本：`scripts/run_qwen_ab_experiments.py`，报告写入 `.agent_work/temp/qwen-ab/`。
  - 已完成报告：`main-deepseek-formal.md` 最新补测 `8/10`（历史同脚本曾跑出 `9/10`，说明 formal 存在 LLM 波动）、`main-deepseek-challenge.md` `12/16`、`main-deepseek-diagnostic.md` `24/32`、`main-qwen-plus-formal.md` `7/10`、`main-qwen37-plus-formal.md` `9/10`、`main-qwen37-plus-challenge.md` `13/16`、`main-qwen37-plus-diagnostic.md` `21/32`、`main-qwen37-max-diagnostic.md` `22/32`、`embedding-siliconflow-bge-m3-formal.md` `8/10`、`embedding-qwen37-formal.md` `9/10`；主模型汇总 `summary-20260727-170319.md` / `summary-20260727-171213.md` / `summary-20260727-182431.md` / `summary-20260727-191224.md` / `summary-20260727-201144.md`，embedding 汇总 `summary-20260727-163220.md`。
- 遗留 / 后续：
  - 不再用 `qwen-plus` 代表 Qwen 主模型优劣；后续主模型对照可保留 `qwen3.7-plus` / `qwen3.7-max` 两档，但默认仍使用 DeepSeek。
  - 结构化输出不是一票否决项；DataPilot 当前更依赖“JSON object / prompt 约束 + 解析校验 + 失败拦截”的稳定性。`qwen3.7-max` 可作为上限探测模型，但 diagnostic 表明它仍不适合直接切默认。
  - Qwen embedding 继续跑 challenge / diagnostic 后，再决定是否在 Phase 3 RAG / Hybrid 中作为推荐 provider；Phase 3A 默认仍保留轻量 deterministic / in-memory。

### [模块任务] M14-lite Phase 3A 收口开发中（2026-07-27）

- 改动范围：`eval/run_eval.py`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`engine/nl2sql/generator.py`、`engine/nl2sql/pipeline.py`、`engine/sql_guard/rbac.py`、`engine/schema_retrieval/retriever.py`、`app/core/config.py`、`.env.example`、相关 Phase 3A 测试。
- 关键记录：
  - M14-lite 执行用户确认的 5 项：最小 `result_match`、LLM 失败 trace 增强、安全/diagnostic 口径清理、Schema Retrieval 后端配置开关；不做递归类目、知识库归因、完整 EvalOps、JSON mode 大实验。
  - `result_match` 只做最小结果集对比：执行 `expected_sql`，按行顺序和列值比较 API 返回 rows；不做 SQL AST 等价、历史库或平台化。当前仅给 5 条核心 challenge SQL case 启用，目的是加严结果校验，不追 diagnostic 满分。
  - 安全口径采用用户确认的方案 A：敏感字段优先于 admin 角色；`users.email/users.phone` 在 Text2SQL 路径中默认不直出，后续如需 admin 查看应走脱敏/审计/专门接口。
  - diagnostic 清理只做边界与语义等价 alias：`db_plan_003` 知识库订单金额归因标为 `manual_review + hybrid_attribution + non_blocking`，留给后续 Hybrid；未通过 prompt 硬连知识库与订单。
  - Schema Retrieval 配置开关默认仍是 `inmemory + deterministic`；`milvus` / `siliconflow` 必须通过环境变量显式开启，pytest 不依赖外部 Milvus 或联网 embedding。
  - Milvus/SiliconFlow 不切默认的关键依据：2026-07-26 临时 A/B eval 显示，Milvus + SiliconFlow 对当前 M13 end-to-end pipeline 没有收益，formal `10/10` 持平，challenge `14/16` 持平，diagnostic `23/32 -> 20/32`。因此 M14-lite 只把它登记为显式工程开关和后续 RAG 复用能力，不把它当成 Text2SQL 提分主线。
  - 注意区分两类结论：M9.1/M9.2 的 schema recall smoke 证明 Milvus adapter / SiliconFlow embedding provider 可用；M14-lite 参考的是 M13 后的真实端到端 eval，结论是“能用，但当前不该默认启用”。
- 验证快照：
  - `pytest tests\test_phase3a_eval.py::test_result_match_case_fails_when_generated_rows_do_not_match_expected_sql`：先红后绿。
  - `pytest tests\test_phase3a_pipeline.py::test_sql_generation_failure_trace_keeps_raw_preview_and_parse_context`：先红后绿。
  - `pytest tests\test_m4_nl2sql.py::test_enhanced_guard_blocks_sensitive_fields_and_role_table_access tests\test_phase3a_planner.py::test_sensitive_field_plan_is_blocked_before_sql_generation`：先红后绿。
  - `pytest tests\test_phase3a_schema_retrieval.py::test_retrieve_schema_default_backend_stays_inmemory_deterministic tests\test_phase3a_schema_retrieval.py::test_retrieve_schema_can_explicitly_select_milvus_backend_without_changing_default`：默认路径通过，显式 Milvus 分支先红后绿。
  - Milvus/SiliconFlow A/B 结论来自 M13 后续接文档与 `.agent_work/temp/milvus-eval/` 临时实验记录：formal `10/10` 持平，challenge `14/16` 持平，diagnostic `23/32 -> 20/32`，所以没有切默认，也没有把 diagnostic 下降伪装成配置收益。
- 临时记录：`.agent_work/temp/m14-lite-notes.md`。

### [模块任务] M13 第二批：alias scorer + item_gmv/转化率 prompt 修复（2026-07-26）

- 改动范围：`eval/run_eval.py`、`eval/cases/phase3a-regression.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/pipeline.py`、`tests/test_phase3a_eval.py`、`tests/test_phase3a_planner.py`、`tests/test_phase3a_pipeline.py`、`eval/reports/phase3a-*.md`、`docs/phase3a-issues-and-fixes-v5.md`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m13-notes.md`。
- 关键记录：
  - 继续按分步修复，不做 JSON mode 大改；先用 trace 证明失败位于 eval 评分、QueryPlan prompt、SQL prompt 还是数据预期。
  - `expected_value` 单指标题新增单列兜底：如果结果只有一列，即使列名是 `"2026年6月GMV"` 这类中文别名，也交给数值校验判定；多列结果仍按列名/显式 alias 检查。
  - 给 formal/challenge 补显式 alias：`usage_count`、`add_to_pay_conversion_rate`、`total_gmv`、`category_gmv`、`product_name_snapshot`、中文 `"商品名称"` / `"平均售价"` 等。原则是只放语义等价别名，不用 alias 掩盖缺表或错表。
  - QueryPlan prompt 增加商品/类目销售额约束：必须用 `item_gmv`、聚合 `order_items.line_amount`，商品/类目维度通过 `order_items.product_id = products.id` 关联，不用 `gmv` / `orders.order_amount` / `orders.product_id` 替代。
  - SQL prompt 增加转化率浮点除法约束：`add_to_pay_conversion_rate` 必须使用 `* 1.0` 或 `CAST(... AS REAL)`，避免 SQLite 整数除法把小数截成 0。
  - `一级类目销售额排名` 的固定检查值从 `数码电子` 改为 `SaaS 软件`。原因：用当前 MySQL seed 直接执行参考 SQL，Top1 实际为 `SaaS 软件`；`数码电子及其子类目` 是另一条困难诊断题，未改。
  - 参考资料：未查阅外部参考；本次按 trace 分层诊断和已有 metrics.yaml / schema_desc 口径执行修复，未引入新的参考项目。
- 验证快照：
  - TDD RED/GREEN 细节见 `.agent_work/temp/m13-notes.md`。
  - 相关回归最终：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-single-metric-related` -> 37 passed，1 既有 Starlette/httpx warning。
  - finish-module 注释补强后相关回归：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-finish-related` -> 37 passed，1 既有 Starlette/httpx warning。
  - 全量 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest --basetemp=.agent_work\temp\pytest-m13-final-full-2` -> 78 passed，1 既有 Starlette/httpx warning。
  - `git diff --check`：无 whitespace error，仅 Windows CRLF 提示。
  - 真实 LLM formal：10/10（最新报告 `eval/reports/phase3a-new-pipeline.md`）。
  - 真实 LLM challenge：14/16（最新报告 `eval/reports/phase3a-challenge-new-pipeline.md`）。
  - 真实 LLM diagnostic：23/32，review_required=3（最新报告 `eval/reports/phase3a-diagnostic-new-pipeline.md`）。
  - formal/challenge/diagnostic 对照报告已按最新 trace 重生成：`eval/reports/phase3a-comparison.md`、`eval/reports/phase3a-challenge-comparison.md`、`eval/reports/phase3a-diagnostic-comparison.md`。
  - finish-module 注释扫描：M13 新增/修改函数与测试均有 docstring 或开头说明；补充 `eval/run_eval.py` 单指标数值兜底、`engine/nl2sql/prompt.py` item_gmv 计划约束两处内部注释。
- 遗留：
  - challenge 仍有 2 条未过：`db_multi_002` 本轮为 LLM generation error；`db_hard_001` 是非阻塞 manual-review 递归类目题，被 SQL Guard 拦截。
  - diagnostic 仍有 9 条未过：5 条偏输出列/诊断评分严格性，2 条 plan validation/guard blocked，1 条非阻塞递归类目 SQL Guard block，1 条安全诊断 `db_sec_004` safety_mismatch。
  - Windows 下默认 `.agent_work/temp/pytest-tmp` 仍可能被锁，已改用本次专属 `--basetemp` 规避。

### [模块任务] M13 第一批：eval 固定事实校准 + metrics prompt 管道修复（2026-07-26）

- 改动范围：`eval/run_eval.py`、`eval/cases/phase3a-regression.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`tests/test_phase3a_eval.py`、`tests/test_phase3a_planner.py`、`docs/archive-dormant/phase3a-issues-and-fixes-v5.md`、`.agent_work/temp/m13-notes.md`。
- 关键记录：
  - 按 v5 执行 M13 分步修复，不一步到位。第一批先解决"测不准"和"metrics prompt 管道断裂"，暂不改 JSON mode，不直接优化 Schema Retrieval。
  - 新增 `expected_value` eval check，优先拦住 `gmv=NULL` 但 `contains: gmv` 误判通过的问题。正式 regression/challenge 中 GMV 使用固定事实 `11285752.00`，净收入按确定性 seed 查询得到 `11293058.25`。
  - `_format_plan_metrics()` 现在会把 `filter` 和 `default_time_field` 注入新 pipeline 的 QueryPlan / 局部 SQL prompt，恢复旧 M4 `_format_metrics()` 已有的结构化指标口径。
  - `DeepSeekChatClient.complete()` 支持可选 `system_prompt`；`generate_query_plan()` 和 `generate_sql_from_plan_step()` 传入各自任务角色。为保护已有 fake LLM 测试，新增兼容调用：旧 `complete(prompt=...)` fake client 仍可工作。
  - 参考资料：未查阅外部参考；本次按 v5 计划执行 M13 第一批修复，修改范围限定在 eval scorer、metrics prompt 管道和 generator system_prompt 兼容；未引入新的参考项目。
- 验证快照：
  - TDD RED/GREEN 记录见 `.agent_work/temp/m13-notes.md`。
  - `tests/test_phase3a_eval.py`：15 passed，1 既有 Starlette/httpx warning。
  - `tests/test_phase3a_planner.py`：11 passed。
  - `tests/test_phase3a_pipeline.py`：4 passed，1 既有 warning。
  - `tests/test_m4_nl2sql.py`：5 passed，1 既有 warning。
  - 相关回归：38 passed，1 既有 warning。
  - 第一批修复后全量 pytest：69 passed，2 skipped，1 既有 warning。
  - 真实 LLM formal 重跑：第一轮 6/10，补 trace 后重跑 5/10；GMV / 净收入均为 `expected_value_ok`，说明原 NULL 伪通过问题已消失。
  - 真实 LLM challenge 重跑：10/16（M12 为 8/16），GMV / 净收入均为 `expected_value_ok`。
  - 真实 LLM diagnostic 重跑：20/32（M12 为 15/32）。
  - 对照报告已重新生成：`eval/reports/phase3a-comparison.md`、`phase3a-challenge-comparison.md`、`phase3a-diagnostic-comparison.md`。
  - trace 增强后全量 pytest：71 passed，1 既有 warning。
- 遗留：
  - M13 已确认原始 `paid_at` / `unpaid` / NULL 类问题基本修复。剩余失败主要是 alias / expected table 严格匹配、SQL 生成阶段没有采用已召回表、以及少数真实 SQL 语义问题（如转化率别名/整数除法、一级类目销售额漂到 `orders_wide`/`gmv`）。下一轮不要再优先改 metrics prompt，应基于新增 trace metadata 判断是 plan prompt、SQL prompt 还是 eval 评分口径需要调整。

### [小修] Phase 3A 问题分析 v5 修订（2026-07-26）

- 改动范围：新增 `docs/archive-dormant/phase3a-issues-and-fixes-v5.md`（由 v4 复制后修订），未改源码。
- 关键记录：
  - v4 主线判断保持：M12 新 pipeline 低通过率的确定性根因优先看 `_format_plan_metrics()` 漏传 `metrics.yaml` 的 `filter/default_time_field`，以及 eval 只做列名 / contains 检查导致 GMV=NULL 也 pass。
  - v5 收紧优先级：第一批执行顺序改为先做 `expected_value` 最小 eval，让固定事实数值错误能被测出来；再修 metrics prompt 管道和 system prompt；之后重跑 formal / challenge / diagnostic。
  - JSON mode 影响从"可能根因"降级为"待验证假设"，仅保留三组对照实验（当前 / SQL 层放开 / 全部放开），不在第一批直接改。
  - `p3a_multi_002` 的 `products` 问题不再直接归因为 Schema Retrieval 没召回；当前复核显示同题 SchemaGraph 可包含 `products`，M12 formal 报告里的 `missing_tables=['products']` 更可能是 SQL 生成阶段选择 `order_items.product_name_snapshot`。后续需通过 trace 区分召回、QueryPlan、SQL 生成三层。
  - `orders.md` 的 `order_status` 字段说明后续应同时补 `canceled` 和 `pending_payment`，避免模型继续幻想不存在的 `unpaid` 状态。
- 验证快照：
  - 已确认正确 `paid_at` 口径 2026 年 6 月 GMV = `11285752.00`；M12 报告中 `created_at` + `unpaid/cancelled` 口径会得到 NULL，但旧 eval 仍可因 `contains: gmv` 判 pass。
  - 当前源码现跑"2026 年 6 月商品销售额 Top 5"时，SchemaGraph 包含 `products`，支持 v5 的归因修正。

### AI_CONTEXT M9.1/M9.2 合并状态修正（2026-07-25）

- 改动范围：`docs/AI_CONTEXT.md`（仅文档）
- 关键决策：M9.1/M9.2 的遗留说明"未合并回 main"已过时——`9fa9368` 已将 Milvus 和 SiliconFlow embedding 可选支持合入 main。默认检索路径仍为 `InMemoryVectorIndex`，不影响 M12 结果（和 Milvus 没启动无关）。修正 M9.1 遗留第 3 条、M9.2 遗留第 2 条。

### 数据库状态文档补充 + Phase 3A 问题分析 v3 修订（2026-07-25）

- 改动范围：`docs/database-current-state.md`、`docs/phase3a-issues-and-fixes-v3.md`（仅文档，无代码改动）
- 关键决策：
  - **实地查库验证 Phase 2.7 数据质量彩蛋**：连接 MySQL `datapilot_dev` 逐项核实 7 个彩蛋的实际数据。确认全部存在，但文档描述有 3 处不够精确：`order_status` 漏了 `pending_payment` 状态（20 条）、`refunds.source_order_no` 格式与 `orders.order_no` 完全不同（SRC-xxx vs ORD-xxx，不能 join）、整单退款（100 条 `order_item_id IS NULL`，10%）未被列为独立彩蛋。
  - **`database-current-state.md` 4 处修正**：① `order_status` 行补完整 6 种状态及行数；② `source_order_no` 行补格式差异和"不能 join"警告；③ refunds 表行量化整单退款比例（10%，必须 LEFT JOIN）；④ "数据质量设计"节全部 7 条量化到具体数字，原"弱关联退款"改为"命名空间不兼容"，新增整单退款条目。
  - **`phase3a-issues-and-fixes-v3.md` 多轮修订**：① 精度修正——明确 bug 是 rewrite regression（旧 `_format_metrics()` 正确，新 `_format_plan_metrics()` 漏字段）；② system prompt 优先级从 ★★ 下调为 ★（user prompt 已部分补偿）；③ 实验设计补旧链路对照组；④ 优先级表合并 Step 4+5；⑤ 新增"问题八"（`numerator`/`denominator` 静默丢弃）和"问题九"（`orders.md` 缺 `canceled` 拼写）；⑥ 彩蛋表重写为 4 列（实际数据 + LLM 易犯错误），补数据库速查行；⑦ 文档末尾新增修订记录节。
  - **v3 方案评估结论**：修复方案和优先级靠谱。最高优先仍是修 `_format_plan_metrics()`（~8 行），数据库验证加强了这一判断——LLM 失败模式可精确描述为"用 `created_at` 代替 `paid_at` + 自编不存在的 `order_status = 'unpaid'` + 不知双拼写"，而 `metrics.yaml` 的 `filter` 和 `default_time_field` 恰好提供这三个缺失信息。
- 参考资料：直接查询 MySQL 数据库；对比 `database-current-state.md`、`domain_pack/schema_desc/orders.md`、`domain_pack/metrics.yaml` 和实际数据。
- 验证快照：
  - orders 总量 10000，`paid_at IS NULL` 20 条，状态均为 `pending_payment`
  - `cancelled` 421 条 + `canceled` 8 条 = 429 条取消
  - `refunds.source_order_no` 格式 `SRC-2026-XXXXX`，与 `order_no`（`ORD-2026-XXXXX`）**0 匹配**
  - 1000 条退款中 `order_item_id IS NULL` 100 条（10%）
  - 金额不一致 5 条、负数退款 3 条 `-20.00`、`source_order_no` 重复 20 条——均与文档一致
  - 14 表行数全部与文档一致
  - 2026 年 6 月 GMV（`paid_at` 口径+filter）= `11285752.00`，与固定事实一致
- 遗留：`orders.md` schema_desc 的 `order_status` 字段行仍未补 `pending_payment` 和 `canceled`，属于问题九的范围，等主线修复完成后处理。

### Phase 3A M12 对照报告与阶段收尾（2026-07-25）

- 改动范围：新增 `eval/compare_phase3a.py`、`scripts/smoke_phase3a_text2sql.py`；修改 `engine/nl2sql/generator.py`、`engine/nl2sql/planner.py`、`app/api/query.py`、`README.md`、`docs/AI_CONTEXT.md`
- 关键决策：
  - M12 负责跑新 pipeline 10 条 formal / 16 条 challenge / 32 条 diagnostic 报告，生成新旧链路对照报告，提供一键 smoke 脚本，更新 README 能力边界。
  - **DeepSeek 模型名修复**：API 已废弃 `deepseek-chat`，修改 `generator.py` 两处默认值为 `deepseek-v4-pro`；同步更新 README LLM_MODEL 示例。
  - **新 pipeline 安全预检补丁**：新链路 `force_new_pipeline=true` 绕过了旧链路的 `_looks_like_dangerous_sql` 预检，导致 DROP/DELETE 等危险问题被 LLM 转写成 SELECT 从而绕过安全用例。修复：在 `app/api/query.py` 的 `force_new_pipeline` 分支前增加相同预检。
  - **plan validation 聚合表达式误判修复**：`_check_table_and_column_scope()` 把 `COUNT(DISTINCT orders.id)` 当作普通列名检查导致误判。修复：拆分 `step.columns` 为纯 `table.column` 和表达式引用，表达式通过 `_qualified_refs()` 提取内部引用。
  - **对照报告生成策略**：选择读取 trace JSONL（结构化）而非解析 Markdown 报告。`compare_phase3a.py` 按 question 文本匹配 case，生成并排对比表（通过率、Schema 精简度、JoinPath、Trace Steps、Issue Tags）。
  - **LLM 通过率现状**：新 pipeline 允许类 SQL 约 50-60% 通过率，低于计划目标 7/8。主要瓶颈是 LLM 输出列名不稳定（别名漂移），与 baseline 遇到的同源。对照报告如实呈现，issue tags 记录具体失败原因。后续 P0 schema/plan/prompt 优化可提升。
  - 用户确认：本模块按 `docs/phase3a-plan.md` M12 默认方案执行，未出现需要偏离计划的新方案选择。
- 参考资料：未查阅外部参考；本次按 `docs/phase3a-plan.md` M12、M8-M11 已有 baseline 和新 pipeline 代码实现。
- 验证快照：
  - 新 pipeline formal 10：6/10 passed（安全 2/2 blocked）
  - 新 pipeline challenge 16：8/16 passed（安全 2/2 blocked）
  - 新 pipeline diagnostic 32：15/32 passed
  - 对照报告 formal/challenge/diagnostic 三份均生成
  - pytest：65 passed, 2 skipped, 1 warning（既有 Starlette/httpx）
  - `git diff --check`：无 whitespace error，仅 Windows CRLF 提示
- 遗留：
  - M12 未解决 LLM 列名别名漂移问题（category/category_name、coupon_order_count 等），属于 P0 schema/plan/prompt 优化范畴，留给后续阶段。
  - 阶段三A 全部 5 个模块（M8-M12）代码已就绪；M12 收工整理后等待人工检查和 accept-module。

### Phase 3A M11 新 Text2SQL Pipeline 与 Trace Steps（2026-07-24）

- 改动范围：未提供模块起始 commit，本次按 `git status --short`、`git diff --name-only` 和未跟踪文件检查；`engine/nl2sql/pipeline.py`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`engine/trace/recorder.py`、`app/schemas/agent.py`、`app/api/query.py`、`tests/test_phase3a_pipeline.py`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m11-notes.md`
- 关键决策：
  - `QueryRequest.force_new_pipeline: bool = False` 作为 API 侧显式评测开关，默认旧请求仍模板优先；没有修改 `AgentResponse` 必填字段，也没有暴露 `plan_execute` / 多 SQL Agent 模式。
  - `trace_steps` 只写入 JSONL `TraceRecord`，不放进公开响应体；每步包含 `step_index/step_type/status/input_summary/output_summary/latency_ms/error_type/metadata/parent_step_id`，SQL 执行 step 的 `step_type=sql_query`，执行元信息放 `metadata`。
  - 新增 `run_text2sql_pipeline()` 串起 `schema_retrieval -> schema_context -> join_path -> query_plan -> plan_validation -> sql_generation -> sql_guard -> sql_execution -> chart_decision`；任何一步失败都结构化 blocked，不降级到模板、全量 schema prompt 或 SQL 自动修复。
  - 新 pipeline 生成 SQL 后仍统一进入 `run_sql_tool()`，SQL Guard / RBAC / 敏感字段策略仍是最终安全门；测试中 fake LLM 返回 `DELETE FROM orders` 已被 `sql_guard_blocked` 拦截。
  - `eval.run_eval` 的 `pipeline_mode=new_text2sql` 到 `force_new_pipeline=true` 映射已在 M8.5 落地，本模块未重复改动；M11 通过 API 侧接入和 trace_steps 证明实际链路。
  - 用户确认：M11 采用计划默认方案，没有出现需要偏离计划的新方案；未引入 LangGraph、MCP、DB-GPT AWEL、AskData MCP、多智能体或 SQL 自修复。
- 参考资料：
  - 查阅 `references/askdata_agent/askdata_pipeline/text2sql_pipeline.py`：借鉴端到端 step log 和 Schema Retrieval -> Plan -> SQL -> Execute 的串联位置；没有引入 MCP Router。
  - 查阅 `references/askdata_agent/sql_generation/prompt_builder.py`：借鉴“当前计划 + 局部 Schema”生成 SQL 的 prompt 边界；DataPilot 保留 JSON 结构化输出。
  - 查阅 `references/DB-GPT/examples/awel/simple_nl_schema_sql_chart_example.py`：借鉴 `schema_linking -> prompt_join -> sql_gen -> sql_exec -> chart` 的阶段覆盖，用于校验 trace_steps 命名完整。
  - 查阅 `references/DB-GPT/packages/dbgpt-core/src/dbgpt/core/awel/dag/base.py` 和 `references/DB-GPT/packages/dbgpt-app/src/dbgpt_app/scene/base_chat.py`：只借 node/context/trace 分段思想；没有新增 `dbgpt-*` 依赖或运行时框架。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-red` 失败于 `ImportError: cannot import name 'pipeline' from 'engine.nl2sql'`，符合 M11 缺口。
  - M11 聚焦：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-tmp-3` 4 passed，1 warning。
  - M11 指定验证：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py tests\test_m5_agent_response.py tests\test_m4_nl2sql.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-related-2` 12 passed，1 warning。
  - 全量 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-full-2` 67 passed，1 warning（既有 Starlette TestClient / httpx deprecation，不影响 M11）。
  - `git diff --check`：无 whitespace error，仅 `app/api/query.py`、`app/schemas/agent.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/prompt.py`、`engine/trace/recorder.py` 的 Windows LF→CRLF 提示。
- 遗留：
  - M11 只完成新 pipeline 接入和 trace_steps；M12 负责跑 formal / challenge / diagnostic 新链路报告、生成对照报告、smoke 脚本和 README 阶段收尾。
  - 当前测试用 fake LLM 固定 QueryPlan / SQL 验证链路结构；真实 LLM 质量、通过率和 issue tags 需要 M12 批量报告如实呈现。
  - `trace_steps` 已写 JSONL，但公开 API 响应暂不展示；后续若 demo 需要展示 trace，可在不改 JSONL 顶层结构的前提下增量做。

## 历史档案（2026-07-24 冻结）

### Phase 3A M10 QueryPlanStep 与自检（2026-07-24）

- 改动范围：未提供模块起始 commit，本次按 `git status --short`、`git diff --name-only` 和未跟踪文件检查；`engine/nl2sql/planner.py`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`tests/test_phase3a_planner.py`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m10-notes.md`
- 关键决策：
  - 新增 `QueryPlanStep` / `QueryPlan`，字段覆盖 `step_id/step_index/step_type/purpose/depends_on/task_type/tables/columns/metrics/filters/joins/aggregations/group_by/order_by/limit/output_columns`；`QueryPlan.steps` 保留未来多步骤扩展，但 M10 校验阶段把多个可执行 `sql_query` step 映射为 `unsupported_multi_step_plan`。
  - `QueryPlanStep` 不包含 `thoughts` / CoT，也不把 `display_type` 作为执行字段；只用 `purpose` 表达意图摘要，展示策略留给 M11 `chart_decision`。
  - Join 自检使用 M9 `SchemaGraph.join_paths` / `relations.yaml` 的 relation id，不接受自由文本编造 Join；表、字段、指标也必须来自局部 SchemaGraph 和 DomainSchema。
  - 敏感字段在 SQL 生成前预检为 `sensitive_field_access`，但 SQL Guard 仍是最终安全门；本模块没有改变 RBAC / SQL Guard 策略。
  - `build_query_plan_prompt()` 通过 `QueryPlan.model_json_schema()` 生成 JSON 格式说明，减少 Pydantic 字段和 prompt 示例漂移；`extract_query_plan()` 只兼容 JSON / fenced JSON / 前后短解释中的 JSON，不做字段名猜测式放宽。
  - 用户确认：本模块没有出现需要偏离计划的新方案；沿用 `docs/phase3a-plan.md` M10 默认边界。
- 参考资料：
  - 查阅 `D:\.Work\Practice\Python-Practice\references\askdata_agent\cot_planning\cot_planner.py`：借鉴“Schema Retrieval 与 SQL 生成之间先有可解析中间计划”的位置，但没有照搬四元组计划，也没有暴露原始 CoT。
  - 查阅 `D:\.Work\Practice\Python-Practice\references\askdata_agent\sql_generation\prompt_builder.py`：借鉴 SQL prompt 只能使用局部 Schema 的约束，M10 先落到 QueryPlan prompt。
  - 查阅 `D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-core\src\dbgpt\agent\core\action\base.py`：借鉴 Pydantic 输出结构生成 JSON 格式说明的思路，没有引入 DB-GPT Action 框架。
  - 查阅 `D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-app\src\dbgpt_app\scene\chat_db\auto_execute\prompt.py`：只借鉴结构化输出约束；没有让模型直接决定执行或绕过 SQL Tool。
  - 查阅本地 `engine/sql_guard/policy.py` / `engine/sql_guard/rbac.py`：确认敏感字段和角色策略口径。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-red` 失败于 `ImportError: cannot import name 'QueryPlanExtractionError'`，符合 M10 缺口。
  - M10 指定验证：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-tmp` 9 passed。
  - 相关回归：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m4_nl2sql.py tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-related-2` 11 passed，1 warning。
  - 全量 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-full` 63 passed，1 warning（既有 Starlette TestClient / httpx deprecation，不影响 M10）。
  - `git diff --check`：无 whitespace error，仅 `engine/nl2sql/generator.py`、`engine/nl2sql/prompt.py` 的 Windows LF→CRLF 提示。
- 遗留：
  - M10 只定义和验证 QueryPlan，不把它接入 `/api/query` 或 eval runner；M11 负责 `force_new_pipeline`、new Text2SQL pipeline 和 `trace_steps`。
  - 聚合函数 × 字段类型校验属于计划 P2/可选增强，本模块未提前做；后续若 schema metadata 有稳定 data_type 再补。
  - 当前 `extract_query_plan()` 不做同义字段名兼容，真实 LLM 若输出严重偏离 JSON Schema，会按 `invalid_query_plan` 暴露，留给 M11/M12 报告真实失败。

### Phase 3A M9.2 真实中文 Embedding + Milvus 效果测试（2026-07-24）

- 改动范围：未提供模块起始 commit，本次按当前实验分支工作树变更检查；`engine/schema_retrieval/embedding_provider.py`、`engine/schema_retrieval/vector_index.py`、`scripts/smoke_m9_2_real_embedding.py`、`tests/test_m9_2_siliconflow_embedding.py`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m9.2-notes.md`、`.agent_work/temp/m9_2-real-embedding-smoke-bge-m3.md`、`.agent_work/temp/m9_2-real-embedding-smoke-qwen3-0.6b.md`
- 关键决策：
  - M9.2 从 M9.1 实验状态切出 `codex-m9.2-real-embedding-experiment`，继续遵守“不合并前先询问用户”。M10 主线仍建议基于已验收 M9 / main，而不是实验分支。
  - 新增 `SiliconFlowEmbeddingProvider`，默认模型 `BAAI/bge-m3`；通过环境变量可切换 `SILICONFLOW_EMBEDDING_MODEL` 和 `SILICONFLOW_EMBEDDING_DIMENSIONS`。真实 API 调用只放 smoke，pytest 用 fake transport，不消耗额度、不依赖网络。
  - `MilvusVectorIndex` 支持 provider 返回 dense vector，并先批量 embedding 文档、推断真实维度，再创建 Milvus collection；否则真实 embedding 维度与默认 128 维不一致会导致 Milvus schema 错误。
  - Provider 增加内存缓存，避免同一文档 / query 在一次 smoke 中重复请求 SiliconFlow。
  - Smoke 同时输出 `merged_top30` 和 `vector_only_top12`：前者模拟 M9 当前主召回策略，后者观察真实 embedding 自身排序能力。
- 参考资料：
  - 查阅 SiliconFlow 官方 embeddings API，确认 `POST /v1/embeddings`、Bearer token、`BAAI/bge-m3`、`Qwen/Qwen3-Embedding-0.6B` 与 Qwen3 `dimensions` 参数。
  - 本次未查外部 benchmark，只用项目 M9 formal/challenge/diagnostic case 做本地效果对比。
- 验证快照：
  - TDD 红灯：`pytest tests\test_m9_2_siliconflow_embedding.py ... --basetemp=.agent_work/temp/pytest-m9_2-red` 失败于 `ModuleNotFoundError: No module named 'engine.schema_retrieval.embedding_provider'`。
  - 单元/集成绿灯：`pytest tests\test_m9_2_siliconflow_embedding.py tests\test_m9_1_milvus_schema_retrieval.py tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9_2-related` 10 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - 真实 API：首次 `scripts\smoke_m9_2_real_embedding.py` 因沙箱网络权限失败，`WinError 10013`；提权后成功调用 SiliconFlow。运行时设置 `OPENBLAS_NUM_THREADS=1`，避免 Windows 下 OpenBLAS 偶发线程/内存分配问题。
  - BGE-M3：`BAAI/bge-m3` + Milvus + `merged_top30` 与 M9 持平：formal 15/15 tables、16/18 items、3/3 join；challenge 29/29、29/33、6/6；diagnostic 54/54、54/62、14/14。`vector_only_top12` 下 challenge 27/29、28/33、5/6；diagnostic 51/54、50/62、12/14。
  - Qwen3-0.6B：`Qwen/Qwen3-Embedding-0.6B` + `dimensions=1024` + Milvus + `merged_top30` 与 M9 持平：formal 15/15、16/18、3/3；challenge 29/29、29/33、6/6；diagnostic 54/54、54/62、14/14。`vector_only_top12` 下 challenge 28/29、29/33、6/6；diagnostic 51/54、55/62、14/14。
- 遗留：
  - 当前 M9 的 keyword + relation merge 已经覆盖硬门，真实 embedding 对最终 merged_top30 没有提升；派生 SQL alias（如 `coupon_order_count`、`conversion_rate`、`avg_price`）仍不是 embedding 能直接解决的问题，留给 M10/M11。
  - Qwen3-0.6B 在 vector-only_top12 比 fake / BGE-M3 更好，说明后续如果做真正语义检索，优先试 Qwen3；但主线不宜默认联网 embedding。
  - 已合并回 main（`9fa9368`），合并后默认 retriever 保持 `InMemoryVectorIndex`，Milvus/SiliconFlow 作为可选注入。

### Phase 3A M9.1 Milvus Adapter 实验（2026-07-23）

- 改动范围：未提供模块起始 commit，本次按当前实验分支工作树变更检查；`engine/schema_retrieval/vector_index.py`、`engine/schema_retrieval/retriever.py`、`tests/test_m9_1_milvus_schema_retrieval.py`、`scripts/smoke_m9_1_milvus.py`、`pyproject.toml`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m9.1-notes.md`、`.agent_work/temp/m9_1-milvus-smoke.md`
- 关键决策：
  - 从已验收 M9 后的 `main` 切出实验分支 `codex-m9.1-milvus-experiment`，不在实验完成后自动合并；用户明确要求“如果要合并先询问”。
  - 使用 `pymilvus 3.0.0` 的 `MilvusClient` 新 API，不使用会触发 deprecation warning 的 ORM API。`pyproject.toml` 登记 `pymilvus>=3.0.0`，避免实验分支依赖只存在于本机环境而没有项目声明。
  - `retrieve_schema()` 默认仍使用 M9 的 in-memory vector index；只有显式注入 `MilvusVectorIndex` 时才走方案 B，避免普通 pytest 和主线开发被 Docker / Milvus 服务绑定。
  - Milvus collection 使用显式 schema：`doc_id VARCHAR(max_length=512)` 作为主键，`vector FLOAT_VECTOR(dim=128)`，索引用 `AUTOINDEX + COSINE`；插入后 `flush + load_collection`，保证 smoke 立即可查。
  - M9 的 deterministic sparse embedding 通过 SHA1 稳定 hash 映射到 dense vector。这里刻意不用 Python 内置 `hash()`，因为内置 hash 有进程级随机盐，会导致 Milvus 召回排序不可复现。
- 参考资料：
  - 查阅本机 `pymilvus.MilvusClient` 签名，并用临时 collection 探测 `create_collection / insert / flush / load / search / drop_collection` 行为。
  - 未查阅外部文档；本次只基于本机 PyMilvus 3.0 API 和 M9 已有接口实现。
- 验证快照：
  - 分支：`git switch -c codex-m9.1-milvus-experiment` 初次因沙箱 `.git` 写权限失败，提权后创建成功；当前工作在实验分支。
  - 环境探测：`pymilvus 3.0.0` 可 import；`http://127.0.0.1:19530` 可连接，初始 collections 为空。
  - TDD 红灯：`pytest tests\test_m9_1_milvus_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9_1-red` 2 failed，失败于 `MilvusVectorIndex` 仍抛 `NotImplementedError`。
  - 聚焦绿灯：`$env:OPENBLAS_NUM_THREADS='1'; pytest tests\test_m9_1_milvus_schema_retrieval.py tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9_1-related` 8 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - Smoke：`$env:OPENBLAS_NUM_THREADS='1'; python scripts\smoke_m9_1_milvus.py` 成功生成 `.agent_work/temp/m9_1-milvus-smoke.md`；运行中出现既有 TestClient/httpx warning。
  - Smoke 对比：in-memory 与 Milvus 在当前 deterministic embedding 下数字完全一致：formal 15/15 tables、16/18 items、3/3 join；challenge 29/29 tables、29/33 items、6/6 join；diagnostic 54/54 tables、54/62 items、14/14 join。
- 遗留：
  - 当前 Milvus 只替换向量存储，不替换 embedding 模型；因此质量没有优于 in-memory。若要评估“Milvus 主路径是否值得合入”，建议下一步接真实中文 embedding（BGE / text2vec）后复测。
  - 由于 M9.1 真实测试依赖 Docker Milvus，默认 M9 测试仍不应强制依赖外部服务；若未来合并，建议把 Milvus 测试保留为显式 smoke 或可 skip 集成测试。
  - 已合并回 main（`9fa9368 Merge optional Milvus and SiliconFlow embedding support`）。合并后默认检索路径仍为 `InMemoryVectorIndex`，`MilvusVectorIndex` 为可选注入。

### Phase 3A M9 Schema Retrieval 与 JoinPath（2026-07-23）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`engine/schema_retrieval/*`、`tests/test_phase3a_schema_retrieval.py`、`domain_pack/schema_desc/relations.yaml`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m9-notes.md`、`.agent_work/temp/m9-recall-summary.md`
- 关键决策：
  - 用户确认选择 M9 选项 A：按 ROADMAP 保留 Milvus 主路径边界，但本模块只实现 deterministic in-memory vector index 与 `EmbeddingProvider` / `InMemoryVectorIndex` 协议，不新增 `pymilvus`、Docker 启动脚本或网络下载依赖。主要风险是真实语义召回质量仍需后续 Milvus / BGE adapter smoke 验证；好处是 M9 不被环境集成阻塞，P0 的文档结构、召回契约和 JoinPath 可先稳定。
  - Schema 文档只分 `field_doc`、`metric_doc`、`relation_doc` 三类；没有新增独立 alias 文件。字段文档复用 `schema_desc/*.md`，指标文档复用 `metrics.yaml` 并做轻量中文业务说法扩写，关系文档优先来自 `relations.yaml`。
  - JoinPath 严格从 `domain_pack/schema_desc/relations.yaml` 构造，不从 Markdown 自然语言关系或 LLM 输出猜 Join。M9 暴露并补齐了 `relations.yaml` 原缺的 `refunds_order`、`refunds_product`、`refunds_user` 三条关系；这些关系已存在于 `refunds.md`，本次只是补齐结构化单一关系源。
  - `SchemaGraph` 当前按命中表补齐该表字段，优先保证 M9 recall 硬门；更严格的局部 Schema prompt 精简留给 M11。派生列别名如 `coupon_order_count`、`conversion_rate`、`avg_price` 不在 M9 强行伪造成物理字段，后续由 M10/M11 的 QueryPlan / SQL alias 层处理。
- 参考资料：
  - 查阅 `docs/phase3a-plan.md` M9、`domain_pack/schema_desc/relations.yaml`、`domain_pack/metrics.yaml`、`eval/cases/phase3a-regression.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`engine/nl2sql/schema_loader.py` 和 `eval/run_eval.py`。
  - 借鉴计划中 AskData / DB-GPT 的分层思想：文档构建、检索、图构建分开；没有引入 DB-GPT / AWEL / Milvus runtime 依赖，也没有提前实现 RRF / rerank 主链路。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-red` 失败于 `ModuleNotFoundError: No module named 'engine.schema_retrieval'`，符合预期。
  - 聚焦 pytest：`pytest tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9-tmp` 6 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - 相关回归：`pytest tests\test_phase3a_eval.py tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9-related` 19 passed，1 warning（既有警告）。
  - 全量 pytest：首次 120 秒超时停在 `tests/test_m3_query.py` 中途，未判定失败；改用 300 秒后 `pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-full-rerun` 50 passed，1 warning（既有警告）。
  - `git diff --check`：无 whitespace error，仅 `domain_pack/schema_desc/relations.yaml` 的 Windows LF→CRLF 提示。
  - 召回诊断：formal allow 8 条 expected_tables 15/15、expected_columns+expected_metrics 16/18、multi_table JoinPath 3/3；challenge schema/join 14 条 expected_tables 29/29、items 29/33、JoinPath 6/6；diagnostic schema/join 24 条 expected_tables 54/54、items 54/62、JoinPath 14/14。
- 遗留：
  - M9 未接真实 Milvus / embedding 模型，`MilvusVectorIndex` 只作为明确报错的 adapter 占位；后续阶段三 RAG 或 M12 README/smoke 需如实说明实际状态。
  - 派生输出列别名未全部召回为字段：formal miss 为 `conversion_rate`、`coupon_order_count`；challenge / diagnostic 还包括 `root_category`、`avg_price`、`doc_title` 等。这些属于 QueryPlan/SQL alias 或不支持关系诊断范畴，留给 M10/M11/M12 处理。
  - `SchemaGraph` 为保证 M9 recall 目前会补齐命中表全字段；M11 做 local schema prompt 时应再按 QueryPlanStep 做字段裁剪，避免 prompt 噪音。

### Phase 3A M8.5 Diagnostic Benchmark 骨架与旧链路诊断基线（2026-07-23）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/cases/phase3a-diagnostic-benchmark.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/run_eval.py`、`tests/test_phase3a_eval.py`、`eval/reports/phase3a-diagnostic-baseline.md`、`docs/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m8.5-notes.md`、`.agent_work/temp/phase3a-diagnostic-baseline-traces.jsonl`、`.agent_work/temp/m8_5-smoke-compat.md`、`.agent_work/temp/m8_5-smoke-compat-traces.jsonl`
- 关键决策：
  - M8.5 按 proposal v5 采用显式 `--cases + --extra-cases` 多文件组合：`database-upgrade-challenge.yaml` 仍是 16 条 challenge 唯一源，`phase3a-diagnostic-benchmark.yaml` 只维护新增 16 条 extra case；没有复制 challenge，也没有实现完整 `includes`。
  - `eval/run_eval.py` 只扩展多文件合并、case id 全局唯一校验、`source_file`、`configured_pipeline_mode` / `actual_pipeline_mode` 和 Markdown 摘要，不引入历史结果库、HTML dashboard 或复杂 scorer。
  - 旧链路 baseline 下，`metric_mapping_match` / `join_path_match` / `manual` 仍跑旧链路结果层；`plan_structure_match`、`plan_validation_blocked`、`schema_context_*`、`trace_steps_complete` 这类新 pipeline 专属 check 标记 `skipped_due_to_pipeline_mode`，不算 pass，也不算 fail。
  - 16 条 challenge 只补 `phase3a_capabilities`、`phase3a_blocking`、`case_properties`、`security_subtype` 诊断元数据，不改问题、expected_sql、check 或 M8 已冻结 baseline 报告；这样 32 条 diagnostic report 的 capability summary 才能覆盖完整 32 条。
  - local schema prompt extra case 使用 block / warn 分层数据结构：缺关键表字段仍是 block；`max_tables` 超标和无关表噪音先作为 warn 素材，避免 M8.5 把 prompt 精简度膨胀成硬门。
  - 用户确认：本模块没有新增需用户二次确认的方案选择；按 `docs/phase3a-plan.md` M8.5 与 `docs/phase3a-diagnostic-benchmark-proposal-v5.md` 已定方案执行。
- 参考资料：
  - 查阅 `docs/phase3a-plan.md` M8.5、`docs/phase3a-diagnostic-benchmark-proposal-v5.md`、`eval/cases/database-upgrade-challenge.yaml`、`eval/run_eval.py`、`tests/test_phase3a_eval.py`。
  - 借鉴 proposal v5 的 32 条结构、capability 标签、check 类型、pipeline mode 和 skipped 口径。
  - 没有照搬外部项目；未查阅外部参考。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-red` 为 6 failed / 6 passed，失败点集中在 diagnostic YAML 缺失、`extra_cases` 参数缺失、`skipped_due_to_pipeline_mode` 字段缺失。
  - capability 元数据红灯：`pytest tests\test_phase3a_eval.py::test_challenge_cases_carry_diagnostic_capability_metadata ... pytest-m8_5-red-cap` 失败于 challenge case 缺 `phase3a_capabilities`，随后只补元数据。
  - 聚焦 pytest：`pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-final` 13 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - Diagnostic baseline：`python -m eval.run_eval --pipeline-mode baseline --cases eval/cases/database-upgrade-challenge.yaml --extra-cases eval/cases/phase3a-diagnostic-benchmark.yaml --report eval/reports/phase3a-diagnostic-baseline.md --trace .agent_work/temp/phase3a-diagnostic-baseline-traces.jsonl` 输出 total=32、passed=12、failed=10、skipped_due_to_pipeline_mode=10、review_required=3；trace JSONL 22 行，skipped case 不写 trace。
  - Capability summary：schema_retrieval 14 覆盖、join_path 13、query_plan 15、local_schema_prompt 7、trace_steps 6、security_guard 4；旧链路下 local schema / plan / trace 专属 case 按预期 skipped。
  - 旧 smoke 兼容：`python -m eval.run_eval --cases eval/cases/smoke.yaml --report .agent_work/temp/m8_5-smoke-compat.md --trace .agent_work/temp/m8_5-smoke-compat-traces.jsonl` 6/6 passed，skipped=0。
  - 全量 pytest：`pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-full-final` 44 passed，1 warning（既有 Starlette/httpx）。
  - `git diff --check`：无 whitespace error，仅 Windows LF→CRLF 提示。
- 遗留：
  - `db_sec_003` / `db_sec_004` 在旧链路 diagnostic baseline 下是 `safety_mismatch`，说明当前旧 pipeline 未稳定把“查用户邮箱手机号 / 管理员联系方式”转成 SQL Guard 可拦截的敏感字段 SQL；先作为 baseline 事实保留，不在 M8.5 修安全策略。
  - 10 条 skipped case 等 M9-M11 提供 Schema Retrieval、QueryPlan、local schema prompt 和 trace_steps 后再真正评分；M8.5 不伪装这些能力已实现。
  - M9 应优先消费 `eval/reports/phase3a-diagnostic-baseline.md` 的 capability summary 和失败明细，证明 schema / join / plan 改造具体改善哪些能力。

### Phase 3A M8 回归基线冻结（2026-07-22）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/run_eval.py`、`tests/test_phase3a_eval.py`、`eval/reports/phase3a-baseline.md`、`eval/reports/phase3a-challenge-baseline.md`、`docs/phase3a-plan.md`、`docs/database-current-state.md`、`.agent_work/temp/m8-notes.md`、`.agent_work/temp/phase3a-baseline-traces.jsonl`、`.agent_work/temp/phase3a-challenge-baseline-traces.jsonl`
- 关键决策：
  - M8 只扩展 EvalOps-lite 的 case 结构和 baseline 报告，不引入新 Text2SQL pipeline、Schema Retrieval、QueryPlanStep 或 trace_steps，避免把 M9-M12 的工作提前倒灌。
  - `EvalCase` 前向兼容 `expected_metrics`、`expected_trace_steps`、`pipeline_mode`，但旧 `smoke.yaml` 默认仍是 `pipeline_mode=baseline`，旧 M6 smoke 不需要补新字段。
  - `_score_case()` 从 tuple 改为 `EvalScore`，新增最小 `issue_tags`：`missing_table`、`missing_column`、`safety_mismatch`、`unexpected_error`；补充轻量 `manual` 语义，困难诊断题无论通过或失败都可在报告中标记 `review_required`。这只服务 baseline 和后续对照报告，不扩展成完整 scorer 平台。
  - 10 条 formal 与 16 条 challenge 的最终口径：10 条 formal 是主硬门；16 条 challenge 是 superset，包含 10 条 formal question，额外 6 条用于扩展数据库复杂度诊断。后续每个模块同步跑两套报告。
  - 用户确认：baseline 首轮结果为 8/10 overall、2/2 security blocked、允许类 SQL 6/8；可选项是 ① 按真实 baseline 继续收工整理、② 调整 regression expected columns、③ 先修旧链路别名再重跑。风险分别是保留低于计划门槛的真实旧链路事实、可能弱化后续对照硬门、可能扩大 M8 到旧链路修复。我的建议是选 ①，用户最终确认选 ①。
- 参考资料：未查阅外部参考；本次按 `docs/phase3a-plan.md` M8、`docs/database-current-state.md`、`domain_pack/schema_desc/relations.yaml`、`domain_pack/metrics.yaml` 和现有 M6 eval runner 实现，没有照搬参考项目。
- 验证快照：
  - TDD 红灯：`pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8-red` 首次 1 passed / 3 failed，失败点为 `EvalCase` 缺 M8 字段、`_score_case` 仍返回 tuple、报告不能接收 issue tags，符合预期。
  - 聚焦 pytest：`pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8-final-align` 7 passed, 1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - 旧 smoke 兼容：`python -m eval.run_eval --cases eval/cases/smoke.yaml --report .agent_work/temp/m8-smoke-compat.md --trace .agent_work/temp/m8-smoke-compat-traces.jsonl` 6/6 passed。
  - M8 formal baseline：`python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-baseline.md --trace .agent_work/temp/phase3a-baseline-traces.jsonl` 8/10 passed；安全 2/2 blocked；允许类 SQL 6/8 passed。
  - M8 challenge baseline：`python -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --report eval/reports/phase3a-challenge-baseline.md --trace .agent_work/temp/phase3a-challenge-baseline-traces.jsonl` 11/16 passed；安全 2/2 blocked；`db_hard_001` / `db_hard_003` 失败且 `review_required=True`。
  - baseline 失败明细：`p3a_multi_001` 生成 `order_count`，case 期望 `coupon_order_count`；`p3a_multi_003` 生成 `category_name`，case 期望 `category`；均记录为 `missing_column`。
- 遗留：
  - M8 不修改 regression / challenge case，也不修旧链路别名；后续 M9-M12 应以 `eval/reports/phase3a-baseline.md` 和 `eval/reports/phase3a-challenge-baseline.md` 的真实失败点证明新 pipeline 的 schema / plan / prompt 改进价值。
  - `expected_trace_steps` 字段已可加载，但 trace_steps 结构仍属于 M11，不要误判为 M8 已实现。

### Phase 2.7.1 数据库 polish（2026-07-22）

- 背景：外部 AI 对 Phase 2.7 审查后指出若干 plan v5 与实现偏差。本轮不重开 Phase 3A M8，只处理进入 M8 前值得补齐且低扰动的数据库口径问题。
- 改动范围：`app/models/orders_wide.py`、`app/models/coupons.py`、`app/models/product_price_history.py`、`alembic/versions/20260722_0003_phase27_database_polish.py`、`scripts/seed_data.py`、`tests/test_m1_models.py`、`domain_pack/schema_desc/{orders_wide,coupons,product_price_history,user_behavior_log}.md`、`docs/database-current-state.md`、`.agent_work/temp/phase2.7.1-notes.md`
- 关键决策：
  - `orders_wide` 不重命名旧字段，保留 `product_name/category/user_status` 等已通过用例依赖的兼容列；仅追加 plan v5 需要的 `user_role`、`primary_product_price`、`item_count`、`refund_count`、`total_refund`、`has_refund`、`updated_at`，让宽表具备“看板预聚合 vs 星型强一致”的后续挑战价值。
  - `user_behavior_log` 不回退到 `target_type/target_id` 多态列；当前显式 `product_id/channel_id` 外键更适合参照完整性和 Text2SQL join path，偏离理由写入 schema_desc 和数据库速查。
  - `coupons` 补 `ix_valid_range(valid_from, valid_to)`，服务优惠券有效期查询；`coupon_code VARCHAR(64)` 保持不动，属于无害兼容差异。
  - `product_price_history` 追加 `change_reason`，同时保留 `price_source`。前者是业务调价原因，后者是数据来源元数据，两者不要混用。
  - seed 仍然保持确定性生成：宽表退款字段从 `order.refunds` 聚合，明细行数从 `order.order_items` 计算；没有逐行写死 10000 行数据，也不依赖自增 ID 从 1 开始。
- 参考资料：未查阅外部参考；本次按外部 AI 对 Phase 2.7 的审查意见和 `docs/database-upgrade-plan-v5.md` 口径补齐偏差，调整范围限定在 3 个 ORM 模型 + 1 条 migration + seed + 4 份 schema_desc + 数据库速查。
- 验证快照：
  - 聚焦 pytest：`tests/test_m1_models.py tests/test_database_upgrade.py` 7 passed
  - 真实 MySQL：`alembic current` 从 `20260722_0002` 升级到 `20260722_0003 (head)`；`alembic check` 输出 `No new upgrade operations detected.`
  - `python -m scripts.seed_data --reset` 成功；14 表行数保持 users 200 / orders 10000 / order_items 18000 / refunds 1000 / product_price_history 150 / orders_wide 10000 等既定数量
  - 固定事实保持不变：2026 年 6 月 GMV `11285752.00`、Aurora 退款率最高、Mobile App GMV Top、Top 退款原因 `quality_issue`、高优 pending 工单 12、金额不一致订单 5
  - 新增字段抽查：`orders_wide` 中 `has_refund=1` 的订单 1000 笔，`sum(refund_count)=1000`，`sum(total_refund)=893612.80`，`max(item_count)=3`；`product_price_history.change_reason` 分布为 current_price 48 / new_year_clearance 50 / spring_price_restore 50 / summer_price_refresh 2；MySQL `coupons` 上存在 `ix_valid_range`
  - 全量 pytest：31 passed, 1 warning（Starlette TestClient / httpx deprecation，既有警告）
- 遗留：
  - 本轮 polish 是 Phase 2.7 验收后的补强，建议新会话复审时重点看 `0003` migration 与文档口径是否一致；不要求 Phase 3A trace_steps 通过。
  - `resources.py` 模块 docstring 位置仍是已知 cosmetic issue，未在本轮扩大处理。

### Phase 2.7 数据库升级（2026-07-22）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`app/models/*`、`app/db/base.py`、`app/schemas/resources.py`、`alembic/versions/20260722_0002_database_upgrade_14_tables.py`、`scripts/seed_data.py`、`domain_pack/schema_desc/*`、`domain_pack/metrics.yaml`、`domain_pack/sql_examples/basic.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-regression.yaml`、`tests/test_m1_models.py`、`tests/test_database_upgrade.py`、`tests/test_m5_agent_response.py`、`docs/phase3a-plan.md`、`.agent_work/temp/database-upgrade-notes.md`、`.agent_work/temp/database-upgrade-seed-summary.md`
- 关键决策：
  - 按 `docs/database-upgrade-plan-v5.md` 一次性将 7 表数据底座升级为 14 张物理表：新增 `product_categories`、`order_items`、`coupons`、`order_coupons`、`user_behavior_log`、`product_price_history`、`orders_wide`；旧表增补 `products.category_id`、`orders.source_order_no/external_order_no/shipping_amount/discount_amount/actual_amount`、`orders.paid_at nullable`、`refunds.source_order_no/order_item_id`
  - 兼容阶段二旧链路：保留 `orders.product_id` 和 `products.category`，让 M2 API、M3/M4 模板 SQL、M6 smoke 继续运行；新指标口径在 `metrics.yaml` / schema_desc 中声明商品维度默认走 `order_items`
  - Seed 不依赖自增 ID 从 1 开始：外键用 ORM 对象关系，固定事实用 `sku/coupon_code/channel_code/category/device_type` 等稳定业务键定位；不把 10000 行数据逐行写死
  - 数据质量彩蛋不破坏主表外键 / 唯一约束：重复源单号放在 `source_order_no/external_order_no`，弱关联退款放在 `refunds.source_order_no`，金额不一致控制为 5 条可解释样例
  - MySQL downgrade 按真实 DDL 行为修正：新表整表 drop 优先，避免外键索引逐个 drop 被拦截；回滚旧 `orders.paid_at NOT NULL` 前先回填 NULL；`coupons.coupon_code` 只保留 unique constraint，避免 Alembic metadata diff
- 参考资料：未查阅外部参考；本次按 `database-upgrade-plan-v5.md`、现有 M1-M6 ORM / seed / eval 结构和用户明确约束实现，没有启动 Phase 3A M8，也没有提前实现 `schema_retrieval` / `query_plan` / `trace_steps`
- 验证快照：
  - 真实 MySQL migration：完整 `alembic downgrade 20260717_0001` -> `alembic upgrade head` -> `python -m scripts.seed_data --reset` 通过；最终 `alembic current` = `20260722_0002 (head)`，`alembic check` 无新增操作
  - Seed 行数：users 200 / product_categories 15 / products 50 / channels 6 / orders 10000 / order_items 18000 / refunds 1000 / tickets 300 / knowledge_docs 10 / coupons 10 / order_coupons 3000 / user_behavior_log 10000 / product_price_history 150 / orders_wide 10000
  - 固定事实：GMV 11285752.00；Aurora 仍为 6 月退款率最高商品；Mobile App 仍为 6 月 GMV Top 渠道；Top 退款原因 `quality_issue`；待处理高优先级工单 12；`JUNE_FIXED_50` 在 Mobile App 使用最多；数码电子一级类目 GMV Top；Aurora 6 月历史均价 899.00；`mobile_app` 设备转化率最高；宽表与星型渠道 GMV 一致；金额不一致订单 5 条
  - 自动化：`pytest` 全量 31 passed, 1 warning；M6 smoke `python -m eval.run_eval --cases eval/cases/smoke.yaml ...` 6/6 passed；`git diff --check` 无 whitespace error，仅 Windows CRLF 提示
- 遗留：
  - Phase 2.7 当前为“已完成（未验收）”，等待用户人工检查后可调用 `accept-module`
  - Phase 3A M8 后续直接基于升级后的 14 表新库跑 baseline；`eval/cases/database-upgrade-challenge.yaml` 只作为数据库升级挑战集和困难诊断素材，不替代 `phase3a-regression.yaml` 的 10 条正式回归
  - `app.db.base` / `app.models` 循环导入规避方式仍沿用既有约定；本次 seed 命令行入口通过先导入 `app.db.base` 避坑，后续若重构可拆 `base_class.py`

### M6 EvalOps-lite 与演示收尾（2026-07-20）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/cases/smoke.yaml`、`eval/run_eval.py`、`eval/reports/latest.md`、`eval/reports/phase2-v1-acceptance.md`、`demo/streamlit_app.py`、`README.md`、`.agent_work/temp/m6-notes.md`、`.agent_work/temp/m6-eval-traces.jsonl`
- 关键决策：
  - 用户确认 Eval 执行方式选择 FastAPI `/api/query`：可选方案是直接调用本地 pipeline，风险是绕过 API 契约；最终选择 API seam，默认用 `TestClient` + 内存 SQLite seed 调真实路由，避免写 MySQL 主库，同时验证 AgentResponse、trace、SQL Tool 和 chart_spec
  - 用户确认 Streamlit 只做最小演示闭环：可选方案是增加复杂筛选和历史记录，风险是 M6 扩大成 UI 大模块；最终只展示 answer / SQL / table / chart / safety_status / trace_id / tool trace
  - 用户确认阶段二验收报告写 v0/v1 能力清单，但自动化评测只覆盖 6 条 smoke：可选方案是只写 smoke 或拉全量 32 条，最终选择“能力清单 + 6 条自动化 smoke”，不把 RAG/hybrid 尚未实现能力写成已完成
  - smoke multi-table 用例从 `join_005` 调整到 `join_002`：`join_005` 会被现有“渠道 + 订单量”模板提前命中，缺 `gmv`；`join_001` 会被“退款 + 原因”模板命中。`join_002` 能稳定走 LLM 三表 join，命中 `channels/orders/refunds`
- 参考资料：未查阅外部参考；本次按 phase2-plan M6、`eval/cases_plan.md` YAML 字段草案、M5 AgentResponse / Trace 契约实现；没有照搬 `QueryMind`、`hello-agents/ch12` 或 `databao-agent`
- 验证快照：
  - `py_compile`：`eval/run_eval.py`、`demo/streamlit_app.py` 编译通过
  - pytest：首次使用默认 `.agent_work/temp/pytest-tmp` 时，旧 basetemp 删除失败触发 Windows `PermissionError`；改用 `--basetemp=.agent_work/temp/pytest-m6-tmp-final` 后 `27 passed, 1 warning`
  - EvalOps-lite：`python -m eval.run_eval` 通过，`6/6 passed`；覆盖 `sql_001/sql_006/agg_001/agg_002/join_002/sec_001`，报告写入 `eval/reports/latest.md`，临时 trace 写入 `.agent_work/temp/m6-eval-traces.jsonl`
  - Streamlit/API smoke：现有 FastAPI `http://127.0.0.1:8000/health` 返回 `ok`；`streamlit run demo/streamlit_app.py --server.port 8501` 页面 HTTP 200；通过真实 API 查询“各渠道订单量是多少？”返回 answer、SQL、rows、chart_spec、tool_calls、trace_id
  - `git diff --check`：仅 README 的 LF→CRLF 提示，无 whitespace error
- 遗留：
  - M6 未调用 accept-module，等待用户人工检查后再跑最终验收门
  - 阶段三接 RAG / Hybrid：以 `domain_pack/kb_docs/` 和 `knowledge_docs` 为语料入口，新增 RAG/hybrid YAML 后继续复用 AgentResponse 字段
  - EvalOps-lite 当前只做 smoke 级检查；完整 32 条评测、RAG 指标和历史聚合留到后续 EvalOps 扩展

### M5 AgentResponse 扩展、Trace、Tool 与图表（2026-07-20）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`app/schemas/agent.py`、`app/api/query.py`、`engine/tools/*`、`engine/trace/*`、`domain_pack/chart_templates/basic.yaml`、`tests/test_m5_agent_response.py`、`scripts/smoke_m5_agent_response.py`、`README.md`、`.agent_work/temp/m5-notes.md`、`.agent_work/temp/m5-smoke.md`、`.agent_work/temp/m5-traces.jsonl`
- 关键决策：
  - Trace 存储按用户确认走 JSONL 主路径：`eval/traces/traces.jsonl` 是正式 trace 默认位置，测试 / smoke 可通过 `app.state.trace_path` 指到临时文件；M5 不引入 SQLite Trace 表或 repository 抽象，避免扩大数据库和评测结构范围
  - SQL 执行迁入 `engine/tools/sql_tool.py`：`/api/query` 不再直接 `db.execute()`，而是通过 SQL Tool 统一做 SQL Guard policy、`tables_used` 提取、数据库执行、耗时统计和 `tool_calls` 记录
  - AgentResponse 只增量扩展旧契约：保留 M3/M4 的 `route/answer/sql/columns/rows/safety_status/blocked_reason/trace_id` 含义，新增 `CostInfo`、`ToolCallTrace`、`tables_used`、`docs_used`、`chart_spec`、`error_type`
  - 图表只做轻量规则：`domain_pack/chart_templates/basic.yaml` 保存 bar / line / horizontal_bar 模板；`chart_tool` 根据结果形状和问题关键词生成 Vega-Lite 兼容 spec，无法判断时返回 `None`，不影响主答案
- 参考资料：未查阅外部参考；本次按 phase2-plan M5 范围、M4 安全链路、用户确认的 JSONL Trace 方案和既有模板 SQL 聚合结果实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m5_agent_response.py -p no:cacheprovider` 首次失败于响应缺 `docs_used/chart_spec`，符合 M5 契约缺口预期；后续新增图表测试先失败于退款率问题误选 `refund_count`，已改为按问题关键词优先选择 `refund_rate`
  - M5 聚焦测试：`3 passed, 1 warning`（Starlette/httpx TestClient 提示，不影响本模块）
  - M3/M4 回归：`9 passed, 1 warning`
  - 全量 pytest：`27 passed, 1 warning`
  - M5 smoke：`scripts\smoke_m5_agent_response.py` 4/4 通过；覆盖渠道订单量 `bar/order_count`、商品退款率横向 `bar/refund_rate`、GMV 单指标 `bar/gmv`、危险 SQL 拦截；摘要写入 `.agent_work/temp/m5-smoke.md`，临时 trace 写入 `.agent_work/temp/m5-traces.jsonl` 且 `trace_lines=4`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - `git diff --check`：仅 README / app/api/query.py / app/schemas/agent.py 的 CRLF 提示，无 whitespace error
- 遗留：
  - M6 接 EvalOps-lite：从 `eval/cases_plan.md` 抽 smoke YAML，用 M5 AgentResponse / trace 字段记录 pass-fail / error_type
  - `CostInfo.model/prompt_tokens/completion_tokens` 当前仍为 `None/0/0`；后续若需要真实 LLM usage，需要扩展 provider 返回 usage，但不改变响应字段
  - 图表规则只覆盖基础 bar / line / horizontal_bar 和 GMV 单指标，不做复杂图表推荐；复杂可视化留到演示页或后续阶段

### M4 NL2SQL 最小链路与安全（2026-07-20）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`engine/nl2sql/schema_loader.py`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`engine/sql_guard/policy.py`、`engine/sql_guard/rbac.py`、`app/api/query.py`、`tests/test_m4_nl2sql.py`、`scripts/smoke_m4_nl2sql.py`、`domain_pack/sql_examples/error_cases.yaml`、`.env.example`、`README.md`、`.agent_work/temp/m4-notes.md`、`.agent_work/temp/prompt-snapshots.md`、`.agent_work/temp/m4-smoke.md`
- 关键决策：
  - LLM provider 采用 DeepSeek 主路径：只实现一个实际可用 provider，不做多厂商复杂抽象；API key 缺失、网络失败或返回结构异常时转成 `LLMGenerationError`，由 `/api/query` 返回结构化拦截，不降级成假 LLM
  - `/api/query` 保持模板优先：M3 已验证模板继续优先执行，模板未命中才构造 prompt 调 LLM；所有模板 SQL 和 LLM SQL 都统一进入 M4 `validate_sql_policy`
  - RBAC 先做表级 + 字段级 allowlist：`admin` 全量，`ops` 可看全表但不能看敏感字段，`customer_service` 限 `tickets / knowledge_docs`，`demo_user` 限脱敏样例表；行级权限不在 M4 扩展
  - Schema / KPI / few-shot 均从 `domain_pack/` 读取：避免把电商字段、GMV、退款率等业务口径写死在 `engine/`
- 参考资料：未查阅外部参考；本次按 phase2-plan M4 范围、M1 schema_desc / metrics、M3 模板 SQL 和用户确认的 DeepSeek / RBAC 边界实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m4_nl2sql.py -p no:cacheprovider` 首次失败于缺 `engine.nl2sql.schema_loader`、`engine.nl2sql.prompt`、`engine.nl2sql.generator`、`engine.sql_guard.policy`，以及 `/api/query` 尚未接 LLM 路径
  - M4 聚焦测试：`5 passed, 1 warning`（Starlette/httpx TestClient 提示，不影响本模块）
  - 全量 pytest：`24 passed, 1 warning`（同上）
  - M4 smoke：`scripts\smoke_m4_nl2sql.py` 真实调用 DeepSeek，6 条 simple SQL 中 5 条通过；prompt 快照写入 `.agent_work/temp/prompt-snapshots.md`，摘要写入 `.agent_work/temp/m4-smoke.md`
  - smoke 已知偏差：`sql_005` 查询待处理工单返回 `pending` 数据且 `safety=passed`，但模型 SQL 未把 `status` 放进 SELECT，导致 expected_columns 缺 `status`；M4 5/6 验收口径仍通过，后续可在 M5/M6 通过提示词或 eval 反馈收紧列选择
  - 安全覆盖：自动化测试验证 DDL/DML 拦截、`users.email` 敏感字段拦截、`customer_service` 越权访问 `orders` 拦截，均返回结构化 `AgentResponse`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - `git diff --check`：仅 `.env.example`、`README.md`、`app/api/query.py` 的 CRLF 提示，无 whitespace error
- 遗留：
  - M5 接 AgentResponse 扩展、SQL Tool、Trace、成本延迟和图表；当前 M4 仍沿用 M3 简化版响应字段
  - 行级权限、脱敏样例数据和更细角色策略未做；M4 只完成表级 / 字段级核心安全边界
  - LLM 生成列选择仍可能波动，`sql_005` 已记录为提示词 / EvalOps 后续优化素材

### M3 v0 模板 SQL 闭环（2026-07-19）

- 改动范围：`engine/nl2sql/*`、`engine/sql_guard/*`、`app/schemas/agent.py`、`app/api/query.py`、`domain_pack/metrics.yaml`、`domain_pack/sql_examples/basic.yaml`、`eval/cases_plan.md`、`scripts/smoke_v0.py`、`tests/test_m3_query.py`、`README.md`（细节看 git）
- 关键决策：
  - v0 严格使用白名单模板 SQL，不接 LLM、不做自由 SQL 生成；未命中模板时返回结构化拦截说明，避免 M3 范围膨胀
  - SQL 执行入口统一先过 `engine/sql_guard/guard.py`，用 sqlglot AST 只允许单条 `SELECT`；`DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE` 等危险 SQL 返回 `safety_status=blocked`
  - `AgentResponse` 从 M3 固定简化字段：`route`、`answer`、`sql`、`columns`、`rows`、`safety_status`、`blocked_reason`、`trace_id`；M5 后续只增量扩展，不改变含义
  - 模板 SQL 使用 MySQL / SQLite 都支持的基础语法；MySQL 仍是主路径，SQLite 仅服务自动化测试和 smoke
  - `eval/cases_plan.md` 同步落地 32 条问题和 YAML 字段草案，M6 只从该文件抽取 smoke 用例，不另起一套字段口径
- 参考资料：未查阅外部参考；M3 按阶段计划、M1 固定业务事实和 M2 FastAPI / SQLAlchemy 结构实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m3_query.py -p no:cacheprovider` 首次失败于缺 `engine.nl2sql.templates`、缺 `engine.sql_guard.guard`、`/api/query` 返回 404
  - M3 聚焦测试：`4 passed, 1 warning`（Starlette/httpx TestClient 依赖提示，不影响本模块）
  - 全量 pytest：`19 passed, 1 warning`（同上）
  - v0 smoke：5 条模板问题均返回 `status=200` + `safety=passed`，关键结果包括 `Aurora Noise Cancelling Headphones`、`Mobile App`、`gmv=160247.0`、`quality_issue`、`pending_high_priority_tickets=12`；`DROP TABLE orders` 返回 `safety=blocked`；摘要写入 `.agent_work/temp/v0-smoke.md`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - `git diff --check`：仅 README / app/main.py / app/api/__init__.py 的 CRLF 提示，无 whitespace error
- 遗留：
  - M4 接 schema loader、prompt、LLM SQL 生成、敏感字段策略和 RBAC；M3 的 `user_role` 目前仅在请求 Schema 中保留
  - RAG / hybrid 用例只在 `eval/cases_plan.md` 中规划，尚未实现检索链路

### M2 API 与后端工程基础（2026-07-18）

- 改动范围：`app/db/session.py`、`app/api/*`、`app/schemas/*`、`app/core/logging.py`、`app/core/exceptions.py`、`app/core/cache.py`、`app/main.py`、`tests/test_m2_api.py`、`README.md`（细节看 git）
- 关键决策：
  - DB session 走正式共享 SQLAlchemy engine + 请求级 `get_db()`，并启用 `pool_pre_ping=True`；不在接口里临时创建连接，避免后续 SQL Tool / API 出现多套数据库入口
  - 4 类资源只做 M2 计划要求的列表查询、分页和基础筛选；不扩展详情、新增、修改、删除，避免 M2 范围膨胀
  - `PageResponse[T]` 和 `ErrorResponse` 从 M2 固定响应形状，后续演示页、EvalOps 和 Agent 错误路径可以复用，不返回散装 dict
  - Redis 只落 `NullCache` wrapper 骨架，不接真实 Redis client，也不把缓存逻辑散进业务 API；这是计划允许的降级边界，后续可替换实现
  - 修复一次导入顺序坑：资源路由不能先从 `app.models` 聚合包导入模型，否则会和 `app.db.base` 的 metadata 注册形成循环导入；改为沿用 M1 的 `app.db.base` 导入路径
- 参考资料：未查阅外部参考；M2 API 形态按阶段计划和项目现有 FastAPI / SQLAlchemy 风格实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m2_api.py -p no:cacheprovider` 首次失败于 `ModuleNotFoundError: No module named 'app.db.session'`
  - M2 聚焦测试：`6 passed, 1 warning`（Starlette/httpx TestClient 依赖提示，不影响本模块）
  - 全量 pytest：`15 passed, 1 warning`（同上）
  - API smoke：4 类接口各 2 个筛选组合均返回 200 且有 `trace_id`；非法分页返回 422 + `validation_error`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - seed：users 50 / products 30 / channels 6 / orders 500 / refunds 80 / tickets 120 / knowledge_docs 8；4 个固定业务事实保持稳定
  - `git diff --check`：仅 README / app/main.py / docs 文件的 CRLF 提示，无 whitespace error
- 遗留：
  - M3 接 `/api/query`、模板 SQL、SQL Guard v0 和简化版 AgentResponse
  - Redis 仍是空实现骨架，不作为已完成缓存能力宣传

### M1 数据底座（2026-07-17）

- 改动范围：`app/models/*`、`app/db/base.py`、`alembic/*`、`scripts/seed_data.py`、`domain_pack/schema_desc/*`、`tests/test_m1_*`（细节看 git）
- 关键决策（git 里看不到的"为什么"）：
  - 状态 / 角色字段用字符串列 + 索引而非 DB 原生 Enum：取值后续可能扩展，合法值由seed / schema_desc / 后续 Pydantic 与 RBAC 层约束
  - seed 脚本不调用 `create_all()`：建表只走 Alembic；SQLite 仅测试用内存库
  - 4 个固定业务事实埋进确定性 seed（而非测试时临时拼数据）：供 M3 模板 SQL 和 M6 smoke 评测复用同一批稳定数据
  - `users.email` / `users.phone` 从模型、schema_desc 到 seed 全程标记敏感：给 M4 SQL Guard 敏感字段策略留入口
  - alembic.ini 用 ASCII 注释：避开 Windows 默认 GBK 读取配置时的 UnicodeDecodeError
- 参考资料：查了 `askdata_agent` 的 `askdata_pipeline/demo_data.py`（业务元数据与演示数据集中组织）和 `schema_indexing/objects.py`（字段描述含 description / aliases / semantic_role / samples / business_usage）；没照搬其 SQLite 建库脚本、Milvus 向量依赖和交易 / 利率业务域
- 验证快照：pytest 9 passed, 1 warning（httpx 依赖提示，无害）；alembic current = `20260717_0001 (head)`；alembic check 无新增操作；seed 行数 users 50 / products 30 / channels 6 / orders 500 / refunds 80 / tickets 120 / knowledge_docs 8（可复制命令 → README）
- 遗留：M2 建 `app/db/session.py`（`pool_pre_ping=True` 等 MySQL 连接参数）、4 类列表接口、请求日志中间件、统一异常响应

### M0 工程骨架与配置（2026-07-16）

- 改动范围：`pyproject.toml`、`app/main.py`、`app/core/config.py`、`.env.example`、`tests/test_config.py`、`tests/test_health.py`
- 关键决策：
  - 数据库主路径选 MySQL 开发库 `datapilot_dev` 而非 SQLite：贴近真实后端项目，后续讲表结构 / 索引 / 迁移 / 权限更自然
  - 连接串用 `mysql+pymysql://`：PyMySQL 作为 MySQL 驱动
  - `SettingsConfigDict(extra="ignore")`：`.env` 里多写暂未用到的字段不会导致启动失败
  - `.env.example` 只放占位和说明；真实密钥只在本地 `.env`，不入库
- 参考资料：未查阅外部参考（通用 FastAPI 骨架，无需借鉴项目结构）
- 验证快照：pytest 5 passed；`Settings()` 能读 `.env` 且 `DATABASE_URL` 指向 `datapilot_dev`；`pymysql` 可导入
- 遗留：已由 M1 完成（ORM、Alembic、seed）

## 历史补充（2026-07-24 冻结）

- 2026-07-24 dev-log M9.1/M9.2 章节合并：按用户要求将两个实验复盘合并为一个”可选 Milvus + SiliconFlow Embedding”章节，补充合并后主线口径（默认 in-memory，不强制 Milvus/联网 API）、使用时机和注意事项；未改代码。
- 2026-07-23 M9 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 50 passed），报告 `accept-M9-20260723.md`。后续可进入 M10 QueryPlanStep 与自检。

- 2026-07-23 Phase 3A plan P2 增强取舍：按用户补充建议更新 `docs/phase3a-plan.md`，把聚合函数 × 列类型校验登记为 M10 P2 可选增强，`SchemaDocument.metadata` 可选保留 `data_type`；增加 `QueryPlan.to_human_explanation()` 作为 trace/report/dev-log 可读解释预留；暂不把 `display_type` 放入 QueryPlanStep 执行字段，最终展示仍归 M11 `chart_decision`。仅文档，未跑测试

- 2026-07-23 Phase 3A plan DB-GPT 改动审查：新增 `docs/phase3a-plan-dbgpt-review.md`，审查 `DB-GPT对比+修改plan` 提交中 plan 的改动质量。总体评价改动质量高、边界清晰；列出 8 条改进建议（P0 3 条、P1 3 条、P2 2 条），覆盖 M9 中文别名/embedding 选型/大表拆分/Schema Linking 预留、M10 `to_prompt_schema()`/fallback 策略/thoughts 取舍理由、M11 `observations` 字段。建议在进入 M9 前由用户审查此文档。仅文档，未跑测试

- 2026-07-23 Phase 3A plan 吸收 DB-GPT 审查意见：按 `docs/phase3a-plan-dbgpt-review.md` 补强 M9 中文 `keyword_text`、metadata/table_name、大表字段拆分预留、fake embedding 与中文 embedding 候选方向；M10 补 `to_prompt_schema()`、不保留 CoT 理由和 plan JSON 失败不回退策略；M11 只把 SQL 执行观察放入 TraceStep metadata，不新增自由文本 observations 顶层字段。仅文档，未跑测试

- 2026-07-23 Phase 3A plan 二次审查补强：按用户提供的补充审查意见继续更新 `docs/phase3a-plan.md`，明确 `pipeline_mode=new_text2sql` 在 eval 中必须映射为 `force_new_pipeline=true` API 请求，Schema Retrieval 命中不足时返回 `insufficient_schema_context` blocked 且不降级全量 schema prompt，并在 M9 增加 `relations.yaml` 对 formal/challenge/diagnostic 多表 case 的 JoinPath 覆盖度校验。仅文档，未跑测试

- 2026-07-23 Phase 3A plan 同步 DB-GPT 报告：更新 `docs/phase3a-plan.md`，把 DB-GPT 明确登记为 M9-M12 的结构参考，新增 Schema Retriever、Action schema、AWEL trace、evaluate 抽象的具体借鉴入口，同时强化不引入 DB-GPT/AWEL/Skill/Sandbox 运行时、不基于 DB-GPT 重开的边界。仅文档，未跑测试

- 2026-07-23 DB-GPT 参考项目解读：新增 `docs/reference-dbgpt-analysis.md`，分析其 AWEL/Agent/Skill/沙箱架构，提炼 DataPilot 可借鉴点（Action 抽象、Skill 统一 domain_pack、DAG 编排预留、上下文管理）。仅文档，未跑测试

- 2026-07-23 M8.5 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 44 passed），报告 `accept-M8.5-20260723.md`。后续可进入 M9 Schema Retrieval 与 JoinPath。

- 2026-07-23 Phase 3A plan 口径小修：按用户要求执行 M9 diagnostic 消费与安全统计澄清。`docs/phase3a-plan.md` 新增 M9-M11 分阶段消费 32 条 diagnostic capability 标签的要求；M9 任务清单和验收门明确要对带 `schema_retrieval` / `join_path` capability 的 diagnostic case 输出召回诊断摘要，但不提前要求 QueryPlan / local schema prompt / trace_steps 专属 check 通过；M12 安全验收拆成 formal 2/2 主硬门 + diagnostic security 4 条单独统计，避免 `db_sec_003/db_sec_004` 这类诊断安全失败被 2/2 口径掩盖。`D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md` 只补全程总览可能过时、以项目计划为准、不要混淆 Phase 3A diagnostic 32 与 AgentEvalOps 基础 32 的说明。

- 2026-07-23 Phase 3A plan 增补 M8.5：按用户确认将 `docs/phase3a-diagnostic-benchmark-proposal-v5.md` 的落地任务写入 `docs/phase3a-plan.md`，新增 M8.5「Diagnostic Benchmark 骨架与旧链路诊断基线」。边界：只新建 16 条 extra diagnostic case、扩展 eval runner 的 `--extra-cases` / `--pipeline-mode` / `skipped_due_to_pipeline_mode` / `source_file` 报告字段，并生成旧链路 32 条 diagnostic baseline；不提前实现 M9 Schema Retrieval、M10 QueryPlanStep 或 M11 trace_steps。当前下一模块已改为 M8.5。

- 2026-07-23 Phase 3A M8 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 38 passed），报告 `accept-M8-20260723.md`。当时后续可进入 M9 Schema Retrieval 与 JoinPath；现已按上方 M8.5 补充记录调整为先进入 M8.5。

- 2026-07-23 Phase 3A 32 条诊断 benchmark proposal v5：按用户要求生成 `docs/phase3a-diagnostic-benchmark-proposal-v5.md`，在 v4 基础上吸收 review-v4 中有效意见。v5 保持 32 条结构，但改为 `database-upgrade-challenge.yaml` 作为 16 条 challenge 唯一源，`phase3a-diagnostic-benchmark.yaml` 只维护新增 16 条，并由 runner `--cases + --extra-cases` 合并；明确 `pipeline_mode` 推荐值 / runner 覆盖 / 实际模式记录，旧链路无法验证的新 check 标 `skipped_due_to_pipeline_mode`；重算 capability 覆盖总数和自动门分母；补 `metric_mapping_match`、local_schema_prompt block/warn 分层、pipeline robustness 单测边界、`quality_reasons` 和 golden path 调整。当前仍未落 benchmark YAML、未改 M8 baseline。

- 2026-07-23 Phase 3A 32 条诊断 benchmark proposal v4 审查：新增 `docs/phase3a-diagnostic-benchmark-review-v4.md`，按 AI_CONTEXT 和 phase3a-plan.md 口径审查 v4 proposal。总体评价 v4 质量高、主体结构无需大改；列出 P0 级 3 点（16 条 challenge 重复维护 drift、能力覆盖矩阵数字不一致、pipeline_mode 语义歧义）、P1 级 3 点（db_hard_002 blocking 矛盾、local_schema_prompt 评分缺分层、chart_decision 覆盖不足）、P2 级 3 点（缺 pipeline 错误路径 case、quality_win 主观、golden path 选择），并给出调整方案：runner 参数组合替代物理复制、能力通过率计算规则、pipeline_mode 三级优先级、local_schema_prompt block/warn 分层。当前仍未落 benchmark YAML、未改 M8 baseline。

- 2026-07-23 Phase 3A 32 条诊断 benchmark proposal v4：按用户要求生成 `docs/phase3a-diagnostic-benchmark-proposal-v4.md`，吸收 `docs/phase3a-diagnostic-benchmark-review-v3.md` 的审查意见。v4 保持 `10 formal / 16 challenge / 32 diagnostic` 三层结构和 32 条总数；用 `db_prompt_003` 替换低价值 `db_schema_001`；补 `pipeline_mode`、`source_case_file`、`expected_tables_alternatives.required_columns`、`optional_steps.chart_decision`、golden path、improvement 计算伪代码和 manual 统计口径；明确短期采用 `source_case_id + 独立 YAML + --check-consistency`，`includes` 留后续。当前仍未落 benchmark YAML、未改 M8 baseline。

- 2026-07-23 Phase 3A 32 条诊断 benchmark proposal v3：按用户要求复制 `docs/phase3a-diagnostic-benchmark-proposal-v2.md` 为 `docs/phase3a-diagnostic-benchmark-proposal-v3.md`，并吸收 `docs/phase3a-diagnostic-benchmark-review-v2.md` 的落地性审查。v3 明确 `difficult_diagnosis` 是 `case_properties` 而非 capability；补 `expected_tables_alternatives`、`accept_paths`、完整 `expected_plan`、`expected_schema_context`、`expected_trace_steps` 和 security YAML 示例；规定单表查询 `join_path` trace 记为 `skipped`；M12 示例数字标注为格式示例。当前仍未落 benchmark YAML、未改 M8 baseline。

- 2026-07-23 Phase 3A 32 条诊断 benchmark proposal v2：阅读 `docs/phase3a-diagnostic-benchmark-review.md` 后新增 `docs/phase3a-diagnostic-benchmark-proposal-v2.md`。v2 保留 `10/16/32` 三层结构，但按 Phase 3A 能力维度重排，新增 `phase3a_capabilities`、`improvement` 分类、`plan_diagnosis`、`local_schema_prompt`、`trace_steps` 检查建议；将 dirty data / edge case 移出主 benchmark，作为后续 robustness 候选。当前仍未落 YAML、未改 M8 baseline。

- 2026-07-23 Phase 3A 32 条诊断 benchmark proposal：按用户要求新增 `docs/phase3a-diagnostic-benchmark-proposal.md`，用于新会话审查方案；内容建议三层评测结构 `10 formal / 16 challenge / 32 diagnostic benchmark`，并列出 32 条候选 case、分层、审查问题和落地步骤。当前仅为 proposal，尚未新增 `eval/cases/phase3a-diagnostic-benchmark.yaml`，也未改变 M8 已冻结 baseline。

- 2026-07-22 Phase 3A 多 SQL Agent 边界预留：按用户确认小修 `docs/phase3a-plan.md`，明确 Phase 3A 仍是 single-step Text2SQL pipeline，不实现多 SQL Agent / SQL+RAG 迭代分析；但 `QueryPlan.steps`、`QueryPlanStep.step_type/depends_on`、`TraceStep.step_index/step_type/parent_step_id`、`EvalCase.pipeline_mode/expected_trace_steps` 需避免写死为单 SQL。本阶段多 `sql_query` step 映射 `unsupported_multi_step_plan`，复杂 Plan-and-Execute 留后续 Hybrid / Data Analysis Agent。

- 2026-07-22 Phase 2.7.1 验收完成、plan v5 归档、切入 Phase 3A M8：① 将 `docs/database-upgrade-plan-v5.md` 归档至 `docs/archive/`；② 补全 AI_CONTEXT Phase 2.7.1 模块档案的「参考资料」小节；③ 当前阶段计划文件切换为 `docs/phase3a-plan.md`，当前模块改为 Phase 3A M8；④ 上一模块验收更新为 Phase 2.7.1 已验收。

- 2026-07-22 Phase 2.7.1 验收未通过（accept-Phase2.7.1-20260722.md）：7 项检查中 2 项 ❌。检查 3 进度状态不一致（plan v5 已移至 archive 但 AI_CONTEXT 仍指向原路径；dev-log Phase 2.7 下一步指针过时未指向 2.7.1）；检查 4 最新日志不完整（AI_CONTEXT 2.7.1 模块档案缺「参考资料」小节；dev-log 无 2.7.1 条目）。其余 5 项 ✅（废弃口径清零、目录地图一致、注释合规、单一事实源抽查 4 项一致、pytest 31 passed）。待用户修复 ❌ 项后复检。

- 2026-07-22 seed 用户姓名真实感小修：按用户反馈，`scripts/seed_data.py` 不再用 50 个基础姓名追加 `02/03/04` 后缀生成 200 用户，改为固定 200 个姓名池，包含二字名、三字名和少量英文名；保留邮箱 / 手机号唯一性和角色分布。执行 `seed --reset` 时发现 MySQL 自引用类目树会拦截 `DELETE FROM product_categories`，已在 reset 前先断开 `ProductCategory.parent_id` 再删除。验证：`python -m scripts.seed_data --reset` 成功，14 表行数和固定事实全部匹配；数据库前 12 个用户已为新姓名 + `user001...` 邮箱；`pytest tests/test_database_upgrade.py tests/test_m1_models.py` 7 passed。

- 2026-07-22 Phase 3A 计划对齐 Phase 2.7 已验收状态：按用户确认修改 `docs/phase3a-plan.md`，将顶部「数据库升级先行」改为「Phase 2.7 数据库升级已完成」，补入 `docs/database-current-state.md` 为单一事实源入口；M8 从“新建 regression / 从 32 条候选抽样”改为“校验现有 10 条新库 regression 并冻结 baseline”；目录规划把 `eval/cases/phase3a-regression.yaml` 标为已有/校验；M9 JoinPath 验收 case 改为 `p3a_multi_001/002/003`。仅文档口径同步，未进入 M8 实现。

- 2026-07-22 新增数据库状态速查：按用户要求新增 `docs/database-current-state.md`，作为后续 AI 快速获取 Phase 2.7 后 14 表数据库现状、seed 固定事实、指标口径、RBAC、安全边界和后续写 plan 注意事项的入口；同步在「当前技术选型快照」挂入口链接。仅文档整理，未改代码。

- 2026-07-22 Phase 2.7 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 31 passed），报告 `accept-Phase2.7-20260722.md`。阶段二数据库底座升级验收完成，后续可进入 Phase 3A M8 baseline。

- 2026-07-22 补 Phase 2.7 dev-log：按用户要求在 `docs/dev-log.md` 末尾追加「Phase 2.7 数据库升级」学习复盘，覆盖 14 表升级、确定性 seed、固定业务事实、challenge / regression 分层、代码阅读路线和面试讲法。该记录仅说明本次文档补写；Phase 2.7 大改主体仍保留在「模块技术档案（新的在上）」。

- 2026-07-22 Phase 3A 计划补数据库升级前置说明：按用户确认，在 `docs/phase3a-plan.md` 顶部新增「开工前置说明：数据库升级先行」。明确 Phase 3A 正式 M8 前先执行 Phase 2.7 数据库升级，执行规格以 `docs/database-upgrade-plan-v5.md` 为准；升级后 M8 baseline 直接在新库上跑旧链路，不做旧库 vs 新库对照；16 条 `database-upgrade-challenge.yaml` 只作为数据库升级验收和困难诊断素材，不替代 10 条 `phase3a-regression.yaml` 正式硬门；M9 relation_doc / JoinPath 优先来自 `domain_pack/schema_desc/relations.yaml`；数据库升级阶段不要求完整 `schema_retrieval` / `query_plan` / trace_steps，仍留到 Phase 3A M11/M12 验收。后续数据库升级完成后，需要小修本文档的单一事实源、当前差异清单、目录规划、M8 和阶段三A验收标准。

- 2026-07-22 生成数据库升级计划 v5：按用户要求复制 `docs/database-upgrade-plan-v4.md` 为 `docs/database-upgrade-plan-v5.md`，并落入上一轮评审的 P0/P1 修正。① 明确 seed reset 与自增 ID 策略：MySQL 多次 reset 后 ID 不从 1 开始是正常现象，后续 seed 不依赖硬编码 ID，固定事实用 `sku` / `coupon_code` / `channel_name` / `category.name` / `device_type` 等业务键定位，并输出 seed_summary。② 修复 `orders_wide` DDL：`ix_category` 改为索引 `primary_category`，并把 `snapshot_at` / `batch_id` / `source_updated_at` 写入正式字段。③ 明确退款粒度：新增 `refunds.order_item_id` 可空外键，商品退款率优先按订单明细归因，同时兼容整单退款和旧 `product_id` 冗余字段。④ 拆分验收门：数据库升级阶段只验结构、seed、固定事实、基础 challenge 和安全；Phase 3A M11/M12 再验 `schema_retrieval` / `join_path` / `query_plan` 等 trace_steps。⑤ 扩展 `relations.yaml` 规格，补 `relation_type` / `grain` / bridge / recursive / temporal / aggregation_warning，覆盖 order_coupons、多级类目、SCD 时间窗口和聚合放大风险。⑥ 补影响文件清单：`app/db/base.py`、`app/models/__init__.py`、`app/schemas/resources.py`、`eval/run_eval.py`、`engine/nl2sql/schema_loader.py` 等。

- 2026-07-22 生成数据库升级计划 v4：按用户要求复制 `docs/database-upgrade-plan-v3.md` 为 `docs/database-upgrade-plan-v4.md`，并执行评审 P0/P1 修改。① 新增 `order_items` 订单明细表，数据库升级目标改为 13 张业务分析表 + 1 张桥接表，即 14 张物理表；`orders.product_id` 保留为 primary product 兼容字段，商品维度 GMV / 销量默认走 `order_items`。② 评测口径拆成两层：16 条 `database-upgrade-challenge.yaml` 证明新库复杂度和困难诊断素材，10 条 `phase3a-regression.yaml` 继续作为 Phase 3A 新旧链路对照硬门。③ 新增 `domain_pack/schema_desc/relations.yaml` 作为结构化关系事实源，M9 relation_doc / JoinPath 直接从这里生成。④ 修复 `paid_at IS NULL` 与 `orders_wide` 全量同步冲突，要求 `orders.paid_at` / `orders_wide.paid_at` 可空且 GMV 默认排除未支付订单。⑤ 为逻辑脏数据明确新增 `orders.source_order_no` / `orders.external_order_no` / `refunds.source_order_no`，不破坏主表外键和唯一约束。⑥ 补 P1 口径：SCD 改为 50 商品 × 平均 3 版本约 150 行；免运费券通过 `orders.shipping_amount` 实现且不抵扣商品 GMV；施工时间估算调整为约 1.5~2 天。

- 2026-07-22 生成数据库升级计划 v3：按用户要求复制 `docs/database-upgrade-plan-v2.md` 为 `docs/database-upgrade-plan-v3.md`，并吸收评审后的确认项。① 表数量口径修正为 12 张业务分析表 + 1 张桥接表，即 13 张物理表。② 数据量改为 `orders=10000`、`orders_wide=10000`、`refunds≈1000`、`order_coupons≈3000`、`user_behavior_log=10000`，不上 20000，兼顾面试中的一万级数据量讲法和本地 seed / pytest 成本。③ Phase 3A 验收改为 16 条分层用例：简单 3、核心指标 4、中等多表 4、困难诊断 3、安全 2；硬门为安全 2/2、简单 3/3、核心+中等 6/8、困难 1/3 正确且 3/3 可诊断。④ 脏数据策略改为不破坏主表外键/唯一约束，用 `source_order_no` / 外部单号等逻辑脏数据模拟重复和弱关联；强脏数据后续可放 raw_import 表。⑤ 新增固定业务事实和指标默认口径章节，明确 GMV、净收入、优惠金额、退款总额、当前价格、历史售价和宽表使用策略。⑥ 施工时间从约 4h 修正为约 1~1.5 天。

- 2026-07-22 生成阶段三A施工计划：按用户要求新增 `docs/phase3a-plan.md`，以 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`「阶段三A」、`docs/phaseX-plan-template.md`、`docs/AI_CONTEXT.md` 当前状态 / 技术选型 / 已知坑和 `references/askdata_agent` 指定文件为依据。结论：未发现 ROADMAP、AI_CONTEXT、模板之间需要停工确认的主线矛盾；小差异包括 `phase3a-plan.md` 原占位未实际存在、现有 M6 smoke 为 6 条而阶段三A需新增 10 条、现有 `QueryRequest` 尚无 `force_new_pipeline`、Trace 尚无 `trace_steps`、Milvus client 依赖尚未落入项目。计划将模块拆为 M8-M12：M8 冻结 10 条 baseline，M9 Schema Retrieval + JoinPath，M10 QueryPlanStep + 自检，M11 新 pipeline + trace_steps，M12 新旧链路对照报告与收尾；文档更新、测试、smoke 跟随对应模块，不单独拆模块。备注：当前工作树已有用户文档归档改动（`docs/archive/*` 与原 docs 文件删除），本次未回滚。

- 2026-07-21 阶段三A路线收敛二次确认：按用户确认，执行阶段三A优化建议中的 1~3 和 5，调整 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`：① 阶段三A改为“Text2SQL 可校验中间层改造”，强调先用 10 条 SQL 回归冻结 v1 baseline，再改造 Schema Retriever / Join Path / QueryPlanStep / trace_steps；生产链路保留模板优先，但评测链路需支持强制走新 Text2SQL pipeline。② 主线优先级表补充 10 条回归基线、局部 Schema Prompt、新旧链路对照报告，并明确阶段三A目标不是新增更多查询能力，而是让 SQL 生成过程可检索、可计划、可校验、可追踪。③ 量化验收新增阶段三A最低标准：10 条回归（2 简单 / 3 聚合 / 3 多表 / 2 安全）、安全 2/2 拦截、允许类 8 条至少 7 条正确、expected_tables 命中 100%、expected_columns / expected_metrics 命中 ≥80%、QueryPlanStep 通过 Pydantic 和局部 Schema 校验、trace_steps 完整、产出对照报告。④ P1 只作为不阻塞增强：`user_role` 预过滤、Join Path 可解释展示、RRF / Rerank、SQL 错误样例库结构化都不抢 P0。另新增 `docs/phase3a-plan.md`，按用户要求只放结构框架和待补充占位，不写具体施工内容。

- 2026-07-21 seed 数据真实化升级：按用户要求将 `scripts/seed_data.py` 的演示数据从占位名改为真实感数据。① 用户名：`Demo User 01` → `陈米娅` 等 50 个中文姓名，邮箱同步改为拼音 `miya.chen@datapilot.example`。② 商品名：`DataPilot Demo Product xx` → `真无线降噪耳机 Pro`、`CRM 入门版（月付）` 等 29 个中文商品/SaaS 名；锚点商品 `Aurora Noise Cancelling Headphones` 保持不变。③ 工单标题：`Demo support ticket 001` → 按 ticket_type 配 5 组共 35 条真实客服标题词库；描述从统一占位文改为 `用户 {姓名} 提交工单：{标题}`。④ 知识库正文：8 篇 `knowledge_docs.content` 从"阶段二 M1 的知识库草稿"改为 2-5 段完整政策文档正文。⑤ 同时将类目从英文改为中文（`Electronics`→`数码电子`、`Home`→`家居生活` 等），`ticket_type` 从 5 种各 24 条均匀分布改为加权分布（refund 30/shipping 28/invoice 22/account 20/product_quality 20），且 `product` 改名为 `product_quality`，`order_status` 从 4×125 均匀分布改为 delivered 200/shipped 150/paid 100/cancelled 50。固定事实（Aurora 退款率最高/Mobile App GMV 最高/quality_issue Top1/12 pending high tickets）和行数全部保持。协同更新：tests/test_m2_api.py（category + order_status 断言值）、tests/test_m5_agent_response.py（GMV 硬编码值）、scripts/smoke_m2_api.py / smoke_m4_nl2sql.py（category 筛选值）、eval/cases_plan.md（评测用例类目名）。验证：pytest 27/27 passed；seed --reset 输出 counts + facts 全部匹配。备注：users.id 从 301、products.id 从 181 开始是因为 DELETE 不重置 MySQL 自增 ID，不影响业务但截图前可顺手增强 reset 逻辑。按用户确认将 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md` 复制为 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`，只优化学习路线大方向，不生成具体执行 plan。v3 保留阶段三A，但收敛为可校验 Text2SQL 中间层改造：确定默认主链路 `question -> schema_retrieval -> schema_graph/join_path -> query_plan -> local_schema_prompt -> sql_generation -> sql_guard -> sql_execution -> trace`；将 QueryPlanStep 自检提升为 P0；先定 `trace_steps` 结构；Schema 检索文档扩展为 `field_doc / metric_doc / relation_doc`；Milvus 保持主路径并轻提 ChromaDB / 内存向量检索备选；RRF / Rerank 只做接口预留；阶段三A结束要求产出新旧链路对照报告；阶段三A不引入 LangGraph、MCP、Skill、多智能体、SQL 自修复或 EXPLAIN 风险检查。

- 2026-07-21 Phase 2.5 M7 并入阶段三A：按用户确认执行排期收敛，`docs/phase2-plan.md` 中 M7 不再作为独立模块执行，阶段二 M0-M6 作为 v1 baseline 冻结；原 M7 的合理内容并入 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md` 阶段三A，包括新 Text2SQL 链路的 `trace_steps`（schema_retrieval / schema_context / join_path / query_plan / sql_generation / sql_guard / sql_execution / chart_decision）和最小 Eval issue tags（missing_table / missing_column / safety_mismatch / unexpected_error）。完整 scorer 分层、历史结果库、HTML 报告和失败归因平台仍归阶段四独立 AgentEvalOps，不借 M7 名义提前实现。

- 2026-07-21 AskData 技术亮点取舍沉淀：新增 `docs/askdata-tech-value-decision.md`，把 AskData 亮点按“真泛用且面试常问”“有价值但轻量做”“能讲但不做主线”分层；结论是 DataPilot 应优先借鉴字段级 Schema 检索、局部 Schema、轻量 Join 路径约束、结构化 QueryPlanStep、SQL Guard 和分步骤 Trace，MCP / Skill / 长短期记忆 / 多智能体继续作为后期扩展。同步小修 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md`：保留阶段三A，但澄清 SchemaGraph 只是当前 Query 的轻量关系视图，四元组计划只作为 AskData 参考，DataPilot 落地为可校验的 QueryPlanStep；RRF / Rerank / SQL 自修复仍为 P1/P2，不阻塞主线。

- 2026-07-21 面试适配报告修正与 roadmap v2：按用户反馈修正 `docs/interview-fit-vs-askdata.md`，将 DataPilot 单体评分与 “DataPilot + 独立 AgentEvalOps” 项目组合评分拆开，避免把完整版 AgentEvalOps 算作 DataPilot 内置能力；DataPilot 单体完成 Text2SQL 深化 + RAG/Hybrid + 包装后预期约 84-86/100，项目组合约 88-90/100。另在 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md` 生成 roadmap v2，在 RAG/Hybrid 前新增阶段三A「Text2SQL 深化」，覆盖字段级 Schema Retriever、Milvus 向量召回、SchemaGraph/Join 路径、QueryPlanStep、局部 Schema SQL prompt、分步骤 Trace、加分项优先级与 AskData 参考位置；同步调整时间表、README 周计划、技术栈和兜底策略。备注：用户提醒后续准备使用 Milvus，本次仅在 roadmap v2 中按主路径体现，未改当前项目运行状态口径。

- 2026-07-21 面试适配度与 AskData 对照分析：按用户担心“AI 从 0 到 1开发的 DataPilot 是否偏离市场面试项目”新增 `docs/interview-fit-vs-askdata.md`，对照当前 M0-M6 DataPilot v1、roadmap 阶段三到阶段五最终形态，以及 `references/askdata_agent` 的文档和可见代码。结论：DataPilot 当前 v1 是工程底座扎实的 NL2SQL v1，面试分约 72/100；完成 RAG/Hybrid、独立 AgentEvalOps、包装后可达强面试项目区间约 88/100。后续最值得借鉴 AskData 的是字段级 Schema Retriever、结构化 QueryPlanStep、SchemaGraph/Join 约束和分步骤 Trace；不建议盲目提前做多库 MCP、长短记忆或完整 Reflection。

- 2026-07-21 M6 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 27 passed），报告 `accept-M6-20260721.md`。阶段二 v1 全部模块 M0-M6 验收完成，可进入阶段三 RAG/Hybrid 或可选 M7 Phase 2.5 硬化

- 2026-07-21 M7 plan 补入 phase2-plan：用户确认采用“方案 B：小做 Phase 2.5”后，将 M7「Phase 2.5 Trace 与 Eval 最小硬化」加入 `docs/phase2-plan.md`。关键边界：M7 仅在 M6 accept 后执行，不属于 v1 验收标准；只做 trace 决策步骤和 Eval issue tag 最小化，不引入完整 EvalOps、数据库、LangGraph 或 RAG 存储选型变化。验证：人工回读；`git diff --check` 仅 Windows LF→CRLF 提示

- 2026-07-21 Phase 2 优化机会分流：按用户阅读 `phase2-reference-review.md` 后的问题，新增 `docs/phase2-optimization-triage.md`，把 trace 增强、Eval issue tag、RAG 契约、模板匹配、SQL Guard reason、Streamlit 增强、LangGraph 迁移等优化点按优先级/难度/风险/roadmap 影响分流。结论：先 accept M6 锁定 baseline；可选做限时 Phase 2.5（trace 决策粒度 + Eval issue tag 最小化）；完整 EvalOps 和 LangGraph 迁移后置。验证：人工回读；`git diff --check` 仅 Windows LF→CRLF 提示

- 2026-07-20 Phase 2 reference 对照复盘：按用户要求补查 phase2-plan 提到的 `askdata_agent`、`QueryMind`、`GustoBot`、`databao-agent`、`langchain_data_agent`、`CoreCoder`、`hello-agents/ch12` 相关文件，并新增 `docs/phase2-reference-review.md`。结论：M2-M6 当时未系统查 reference 在范围受控前提下可接受；当前实现无需返工，后续优先补 trace 粒度、EvalOps issue tags/scorer 分层、Phase 3 RAG 元数据契约。验证：人工回读报告；`git diff --check` 仅 Windows LF→CRLF 提示

- 2026-07-20 M6 dev-log 加粗与 finish-module 规则补强：按用户反馈，为 M6「新概念」「设计要点」解释句补充必要加粗锚点；`finish-module` 阶段 4 新增加粗自检，要求「新概念」「设计要点」不能只加粗条目名，也要加粗关键作用、核心取舍、量化结果和边界风险。验证：人工回读修改段落

- 2026-07-20 M6 dev-log 代码阅读路线二次优化：按用户反馈，将「读者需要重点理解哪个设计点」改进为“点名关键设计，并解释它解决什么问题、为什么这样放”；同步扩充 M6 阅读路线的 `smoke.yaml`、`_score_case()`、Streamlit 页面和阶段验收报告说明。验证：人工回读修改段落

- 2026-07-20 M6 dev-log 阅读路线补强：按用户反馈，将 `docs/dev-log.md` M6「代码阅读路线」中 `eval/run_eval.py` 的说明从函数名罗列扩展为入口、YAML 加载、TestClient + SQLite dependency override、API 调用、评分、报告输出的逐步阅读导航。验证：人工回读修改段落

- 2026-07-20 M5 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 27 passed），报告 `accept-M5-20260720.md`。备注：pytest 旧临时目录 `pytest-of-Stephen` 有权限问题需手动清理；`_elapsed_ms()` 在 query.py 和 sql_tool.py 各有一份相同实现，轻微重复

- 2026-07-20 模块工作流小优化：AGENTS 工作约定新增模块开工极短 checklist、README 阶段末统一整理口径；finish-module 新增“用户确认过的关键取舍”记录要求；phase2-plan M6 新增需用户确认的决策点；AI_CONTEXT 新增当前技术选型快照。验证：人工回读修改段落

- 2026-07-20 M4 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 24 passed），报告 `accept-M4-20260720.md`

- 2026-07-20 M4 本地启动体验改为 Swagger 优先：按用户实际验证路径，将 `docs/dev-log.md` M4「本地启动体验」改为“启动 FastAPI → 打开 `/docs` Swagger UI → Try it out → 填 JSON → Execute → 看 Response body”，PowerShell 只作为复现和验收留证；同步微调 `finish-module` 模板，后续模块本地体验优先写 Swagger / 浏览器接口文档。验证：人工回读 M4 小节

- 2026-07-20 M4 dev-log 验证体验补强：按用户反馈，`docs/dev-log.md` M4「验证与下一步」从单纯命令列表扩展为自动化验证预期、本地 FastAPI 启动体验、可复制 `/api/query` 输入和大致返回结果；同步更新 `finish-module` skill 模板，要求后续模块写“命令说明 + 预期结果 + 本地启动体验”。验证：人工回读 M4 小节和 skill 阶段 4

- 2026-07-20 M3 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 19 passed），报告 `accept-M3-20260720.md`

- 2026-07-19 dev-log 代码阅读路线版式调整：按用户确认，将 M0-M3 `### 代码阅读路线` 的顶部“按 X 顺序读”句式删除，改为编号项直接承载职责标题与文件路径（如 `**接口契约**：app/schemas/agent.py`），减少“先看/再看”冗余。验证：人工回读 M0-M3 阅读路线

- 2026-07-19 dev-log 代码阅读路线补强：按用户确认的标准版，为 `docs/dev-log.md` M0-M3 的「关键文件」后新增 `### 代码阅读路线`，覆盖阅读顺序、主角文件/函数、调用关系和数据流向；`finish-module` skill 暂未修改，待用户选择模板版本。验证：人工回读 M0-M3 阅读路线

- 2026-07-19 dev-log 前序章节与 finish-module 写作规则优化：为 `docs/dev-log.md` M0-M2 补充扫读重点加粗；在 `.claude/skills/finish-module/SKILL.md` 阶段 4 增加 dev-log 加粗写作要求，要求突出关键词、核心决策、类比锚点、量化成果和面试 talking point。验证：人工回读 M0-M3 与 skill 阶段 4

- 2026-07-19 M3 dev-log 可读性微调：按用户反馈为 `docs/dev-log.md` 的 M3 复盘补充重点加粗，突出模板 SQL、SQL Guard、AgentResponse、评测清单和验证结论；仅文档样式调整，未改代码。验证：人工回读 M3 小节

- 2026-07-19 dev-log.md 加粗优化：为"面试怎么讲"段落提取关键 talking point 加粗、Java→Python 类比标记加粗、关键数字锚点（X 个测试 / X 张表 / X 条 SQL 等）加粗、设计要点结论句补漏。原则：加粗服务于扫读，让新手不用逐字读就能定位到"这个概念对应 Java 的什么、面试能讲哪几个点、量化成果是什么"。

- 2026-07-19 全项目注释风格合规整改：按 CLAUDE.md「代码风格」扫描全部 36 个 .py 文件，修复合规项 47 处（A 英文→中文 docstring 14 / B 缺文件头 11 / C 缺函数 docstring 15 / D 注释简略 3 / E 空 __init__.py 4）。发现 agent 修改的两个常见问题：① docstring 可能被错放在 import 之后（Python 模块 docstring 应为首个语句，PEP 257）；② Unicode 弯引号 "" 会替代 """ 导致语法非法，prompt 应显式禁止。验证：20/20 文件 ast.parse 通过；pytest 5/5 passed
    - 2026-07-19 验收状态入「当前状态」：新增「上一模块验收」字段（现值 M2 已验收），防止未跑 accept-module 就开工下一模块。维护闭环：finish-module 收工置「Mx 未验收（待 accept-module）」→ accept-module 通过后改「已验收」（有 ❌ 记「验收未通过」）；CLAUDE.md「开发记录要求」新增任务开始核对规则（下一模块开发前上一模块未验收 → 先提醒用户）；accept-module 检查 3 把该字段纳入核对项。验证：rg「上一模块验收」命中 CLAUDE.md / AI_CONTEXT 当前状态 / 两个 skill 共 6 处预期位置

- 2026-07-19 Codex wrapper 残余口径修正（M3 前口径巡检收尾）：`.codex/skills/` 两个 wrapper 的 canonical 引用路径原为 `../../.claude/...`，自 wrapper 所在目录少跳一级、会解析到不存在的 `.codex/.claude/`，改为自项目根目录起算的 `.claude/skills/<skill>/SKILL.md`；description 同步 07-19「skill description 收敛」口径（accept-module 删流程摘要、finish-module 补「写复盘」触发词）。同轮巡检其余均干净：finish-module canonical 无硬编码 smoke 路径（验证步骤现读计划文件）、phase2-plan M2-M5 命令均指 `scripts/`、README 无 smoke 引用、全库旧路径仅本文件历史记录命中。验证：两个 canonical 路径 `test -f` 存在；废弃口径扫描（--hidden，覆盖 .codex）无命中 exit 1

- 2026-07-19 验收工作流优化（据 M2 验收复盘）：① accept-module 检查 3 改为 AI_CONTEXT 唯一权威口径（总览已无状态列）；② 检查 5 增加计数口径（docstring 或开头注释均算解释、pytest / 常量子类 / 纯字段模型豁免规则、≤10 文件必须全读列清单）；③ 检查 5 增加同模块复检的增量范围规则；④ 验收报告增加"落点两动作"（结论进补充记录、⚠️ 项登记已知的坑或下模块任务）；⑤ M2 smoke 脚本从 `.agent_work/temp/phase2/` 迁入 `scripts/smoke_m2_api.py`（★ 修正 `parents[3]`→`parents[1]` 并补中文注释），phase2-plan M2-M5 验证命令与 dev-log 引用同步改为 scripts/ 路径，CLAUDE.md「工作约定」明确 smoke 脚本落位并在 phase2-plan「单一事实源」登记，deprecated-terms 新增 temp 下 smoke .py 路径守卫正则；.gitattributes 换行统一经用户决定暂不做。验证：`python scripts/smoke_m2_api.py` 输出 9 行符合预期（8×200 + 1×422 validation_error）；废弃口径扫描含新守卫无命中（exit 1）；pytest 15 passed, 1 warning

- 2026-07-19 M2 代码注释补强：按 CLAUDE.md「代码风格」为 M2 的 7 个文件（core/logging、core/exceptions、core/cache、db/session、api/resources、schemas/resources、tests/test_m2_api）补充中文 docstring 和关键点注释（trace_id 透传与回传、三层异常兜底、Null Object 缓存骨架、分页稳定排序与 order_by(None) 计数、左闭右开时间范围、pytest 依赖覆盖），消除 accept-M2-recheck-20260719 检查 5 的 ⚠️；未改任何业务行为。验证：pytest 15 passed, 1 warning；git diff --check 仅 CRLF 提示

- 2026-07-19 skill description 收敛：finish-module / accept-module 的 description 删流程摘要、只留定位与触发词，避免与正文形成第二份口径；finish-module 触发词补「写复盘」。验证：会话内 skill 列表已刷新为新 description

- 2026-07-19 注释规则单一事实源收敛：CLAUDE.md「代码风格」定为注释规则唯一权威（补语言边界、分隔线规则及“目测即可、不进验收”说明）；finish-module / accept-module 改为引用不复述；accept-module 检查 5 更名「注释合规」、判定去 ORM 化并修 typo；deprecated-terms.txt 登记「注释合规抽查」。验证：rg 全库旧口径仅登记处命中

- 2026-07-18 模块工作流口径优化：phase2-plan 取消模块总览状态列，进度只看 AI_CONTEXT；各模块补“模块验证命令”；finish-module 明确 AI_CONTEXT 新的在上、dev-log 追加到末尾。验证：rg / diff check

- 2026-07-18 模块收工 workflow 固化：新增 `finish-module` skill（Claude canonical + Codex wrapper），把”补注释 + 跑验证 + 写 AI_CONTEXT + 写 dev-log”固定为模块完成后的收工整理；`accept-module` 增加注释合规轻量必检，并更新 AGENTS / CLAUDE / phase2-plan 的调用顺序。验证：rg / diff check

- 2026-07-18 M1 代码注释补强：按 AGENTS.md「代码风格」为 M1 模型、seed、Alembic env、M1 测试补充新手友好的中文注释和关键步骤说明；未改业务行为。验证：pytest 9 passed, 1 warning；alembic check 无新增操作；git diff --check 仅 Windows 换行提示

- 2026-07-18 完善 dev-log 学习复盘：按新版 AGENTS.md 要求，为 M0/M1 补充更清晰的故事体说明、关键文件速览和可复制验证命令。验证：rg / diff check

- 2026-07-17 日志分家（方案 A）：dev-log 改为学习复盘、本文件改为技术档案，删除与 CLAUDE.md / phase2-plan / README 重复的段落；同步改写 CLAUDE.md「开发记录要求」、phase2-plan 相关引用和 accept-module skill。验证：rg 扫描「当前状态速览」无活跃引用

- 2026-07-17 日志拆分 v1（已被上一条取代）：曾新增复制式 AI_CONTEXT.md，因重复定义问题重构

- 2026-07-17 Phase 2 验收口径收敛：M4 简单 SQL 正确性、YAML case 字段、验收记录落位（`eval/reports/phase2-v1-acceptance.md`）登记进 phase2-plan「单一事实源」。仅文档，未跑测试

- 2026-07-17 跨文档重复收敛：32 条用例构成唯一出处定为 phase2-plan M3；目录结构权威定为 CLAUDE.md；phase2-plan 规范复述改引用。仅文档，未跑测试

- 2026-07-17 文档口径审查：README 删 SQLite 主路径旧口径；库名统一 `datapilot_dev`（config 默认值 / .env.example / test 字面值三处）。pytest 5 passed。遗留低优先级待办：dev 依赖补 httpx、空包目录补 `__init__.py`、`.gitkeep` 入库、`redact_database_url`
  改 `rsplit`、LEARNING_ROADMAP 两处旧口径
  
- 2026-07-17 多工具协作口径校准：临时目录统一 `.agent_work/temp/`、Trace 归`eval/traces/`、Phase 2 smoke 定为 6 条。仅文档与目录占位，未跑测试

- 2026-07-17 架构底线与降级边界：phase2-plan 新增 P0（不可降级）/ P1（可简化）边界；简化版 AgentResponse 前置到 M3。仅文档，未跑测试

    
