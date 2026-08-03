# M17 Scorer 分层与 Score 回写 notes

## Implementation checklist

- [x] 补充 plan：M17/M18 在 `M16B` 分支继续执行，不新增 `M17B` / `M18B`
- [x] 调研 LangFuse 内置评估器并记录结论
- [x] 迁移 L1/L2 规则评分为 `eval/scorers/` 单一事实源
- [x] 补最小 `llm:correctness` judge（显式配置才启用）
- [x] 按 `langfuse_trace_id` 回写 LangFuse Score，失败降级不阻断 eval
- [x] 运行验证命令
- [x] 调用 finish-module 收工整理

## 关键决策

- 当前执行路线：在 M16B live lifecycle 底座上继续 M17/M18；M17 不另建 `M17B` 章节，score 仍只依赖 JSONL 的 `langfuse_trace_id` 映射字段。
- `rule:latency_p95` 作为 numeric score 明细回写 LangFuse，但不参与旧 Markdown pass/fail 汇总。原因：延迟有运行环境波动，M17 的“不退化”门禁应优先守住答案/安全/结果口径；性能分数用于观测趋势。

## M17-1 LangFuse 内置评估器调研

- 官方 Scores 文档：Score 是 trace / observation / session / dataset run 上的通用质量评估对象，支持 LLM-as-a-Judge、Code evaluators、UI、Annotation Queue 和 API/SDK 写入。
- 官方 Code evaluators 文档：更适合 deterministic checks，例如 exact match、schema validation、keyword checks、tool-call checks 和业务规则；生产推荐观察 observation 或 experiment，不要求 DataPilot 本地迁移规则评分到 LangFuse 托管执行器。
- 官方 LLM-as-a-Judge 文档：适合 semantic judgment、rubric reasoning、helpfulness / relevance / correctness 等主观判断。
- M17 结论：DataPilot 本模块先做本地 `eval/scorers/` 单一事实源 + SDK/API score 回写；LangFuse 内置/托管 evaluator 作为 M18 UI/Experiment smoke 和 EvalBench 后续候选，不作为 M17 代码硬依赖。
- 原因：计划要求 M17 保持 Markdown / JSONL / LangFuse Score 同口径；把规则评分迁到 LangFuse 托管 Code evaluator 会引入 UI 配置、observation target 和 dispatcher 依赖，超出当前模块范围。

## 验证记录

- 2026-07-29：`pytest tests\test_m17_scorers.py tests\test_phase3a_eval.py --basetemp=.agent_work\temp\pytest-m17-3` 通过，27 passed / 1 warning。
- 2026-07-29：`python -m compileall eval\run_eval.py eval\scorers` 通过。
- 2026-07-29：默认 eval CLI：`python -m eval.run_eval --report .agent_work\temp\m17-eval-report-2.md --trace .agent_work\temp\m17-eval-traces-2.jsonl` 通过，`judge_model=<disabled>`，`langfuse_scores=ok:0 skipped:0 failed:0`，passed=3/6（与当前 baseline smoke 现状一致）。
- 2026-07-29：真实 LangFuse score 回写 smoke：`LANGFUSE_ENABLED=true python -m eval.run_eval --report .agent_work\temp\m17-langfuse-score-report.md --trace .agent_work\temp\m17-langfuse-score-traces.jsonl` 通过，`langfuse_scores=ok:16 skipped:0 failed:0`。
- 2026-07-29：M16B live lifecycle score smoke（fake LLM + `new_text2sql` + `LANGFUSE_ENABLED=true`）通过，`score_payload_count=6`，`score_write_result.ok=6`，JSONL `langfuse_span_mode=live` / `langfuse_write_status=ok`，`langfuse_trace_id=dbcbce212ae74e6cb998642310687dc4`。
- 真实 LangFuse smoke 中出现 SDK OTLP trace export `WinError 10013` warning / `Unexpected error occurred` 日志，但 eval 命令返回 0，JSONL 映射存在，Score writer 返回 ok。记录为 Cloud/SDK 网络层 warning，不阻断 M17。
