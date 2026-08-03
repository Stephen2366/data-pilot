# M16B Trace Lifecycle 下沉 notes

## Implementation checklist

- [x] 从 M16 提交切出 `M16B` 分支
- [x] 读取 M16B 计划、AGENTS.md、AI_CONTEXT.md、M16 notes
- [x] 用户确认重复 span 处理采用方案 1：`TraceRecord.langfuse_span_mode`
- [x] 补 lifecycle 抽象和 post_hoc/live 去重测试
- [x] 接入 `force_new_pipeline` Text2SQL pipeline 主链路
- [x] 跑 LangFuse + JSONL live smoke 和 eval 对照
- [x] 调用 finish-module 收工整理

## 关键决策

- M16B 采用 `langfuse_span_mode: Literal["post_hoc", "live"] = "post_hoc"` 区分观测写入模式。
- `post_hoc`：沿用 M16，TraceRecord 请求结束后由 `LangFuseBackend.record()` 统一拆成 flat spans。
- `live`：pipeline lifecycle 执行过程中已经写 LangFuse spans，最终 `LangFuseBackend.record()` 不再重复写 post-hoc spans，只保留 JSONL 映射字段。
- 选择原因：比动态移除 backend 更显式，M17 仍只按 `langfuse_trace_id` score 回写，后续若放弃 M16A 也可把默认模式切成 `live`。
- SQL tool 分层采用方案 1：`run_sql_tool()` 增加可选 `trace_context` 参数，在工具层内部记录 `sql_guard` / `sql_execution` spans。
- 选择原因：guard 和数据库执行的真实边界在 tool 内部，事后由 pipeline 补 span 虽然改动小，但不适合作为后续 M16B 底座。
- M16B 计划中的图表 span 名称采用 `chart_generation`；旧实现里的 `chart_decision` 是 M11 遗留命名，M16B 统一到计划口径。

## 验证记录

- 2026-07-29：`pytest tests\test_m16_trace_router.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m16b-3` 通过，14 passed。
- 2026-07-29：`pytest tests -x --basetemp=.agent_work\temp\pytest-m16b-full-2` 通过，98 passed / 2 skipped / 1 warning。
- 2026-07-29：临时 live smoke（fake LLM + SQLite seed + `LANGFUSE_ENABLED=true` + `force_new_pipeline`）通过，JSONL trace 为 `langfuse_span_mode=live` / `langfuse_write_status=ok`，LangFuse trace URL：`https://jp.cloud.langfuse.com/project/traces/c1e4a46844fb49ea9cc2fb77a21b737d`。
- smoke step_names：`schema_retrieval`、`schema_context`、`join_path`、`query_plan`、`plan_validation`、`sql_generation`、`sql_guard`、`sql_execution`、`chart_generation`。
