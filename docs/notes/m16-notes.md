# M16 Trace 双写与降级 notes

## Implementation checklist

- [x] 读取 M16 计划、AGENTS.md、AI_CONTEXT.md、M15 notes
- [x] 用户确认方案 A：TraceRouter + JSONL 主路 + LangFuse 旁路 + flat spans
- [x] 补 TraceRouter / JSONL path override / LangFuse 降级测试
- [x] 重构 `engine/trace/recorder.py`
- [x] 新增 `engine/trace/langfuse_backend.py`
- [x] 验证 `/api/query` 响应契约不新增 LangFuse 字段
- [ ] 跑 M16 验证并调用 finish-module 收工

## 关键决策

- 采用方案 A：`append_trace()` 保持兼容入口，内部走 `TraceRouter`；默认只写 JSONL，`LANGFUSE_ENABLED=true` 时追加 LangFuse backend。
- LangFuse span 映射采用 flat spans，不伪造父子嵌套和真实 started_at / ended_at。原因：当前 TraceRecord 是请求结束后一次性生成，只有每步 `latency_ms`，没有真实时间线；强做嵌套会扩大到 pipeline 埋点架构，越过 M16 范围。
- Router 执行顺序暂定为 `LangFuseBackend -> JSONLBackend`。原因：这样 LangFuse 成功/失败后的 `langfuse_trace_id` / `langfuse_write_status` 能写进同一行 JSONL；LangFuse 异常由 router 捕获，不影响后续 JSONL 写入。
- Cloud payload 最小化：root span 只上传 question/user_role/route、answer/safety/error 摘要和 columns/tables/rows_count/docs_count/cost 等 metadata；不上传完整 rows 和 docs 内容。

## 已完成实现快照

- `engine/trace/recorder.py`
  - `TraceRecord` 新增 `langfuse_trace_id`、`langfuse_trace_url`、`langfuse_write_status`
  - 新增 `TraceBackend`、`JSONLBackend`、`TraceRouter`、`build_trace_router()`、`configure_trace_router()`
  - `append_trace(record, path=...)` 保持兼容，内部调用模块级 `trace_router`
- `engine/trace/langfuse_backend.py`
  - SDK 延迟导入，只有启用并实际写 LangFuse 时才 import `langfuse`
  - 使用 M15 固定的 SDK 4.14.1 API：`start_observation(trace_context=...)`、`flush()`
  - 成功时回填 `langfuse_trace_id/url/status=ok`，异常由 router 捕获并标记 `failed`

## 验证快照（开发中）

- 红灯：`python -m pytest tests/test_m16_trace_router.py --basetemp=.agent_work/temp/pytest-m16-red` 因 `JSONLBackend` 尚不存在收集失败，符合预期。
- 绿灯：`python -m pytest tests/test_m16_trace_router.py --basetemp=.agent_work/temp/pytest-m16-green-3` -> 6 passed，1 个既有 Starlette/httpx warning。
- 相关回归：`python -m pytest tests/test_m5_agent_response.py tests/test_config.py --basetemp=.agent_work/temp/pytest-m16-related-1` -> 7 passed，1 个既有 Starlette/httpx warning。
- 真实双写 smoke：`python .agent_work/temp/smoke_m16_trace_double_write.py` -> JSONL 写入 `.agent_work/temp/m16-double-write-traces.jsonl`，`langfuse_trace_id=e62319e3b05944ca90d4fbc6540cb5df`，`langfuse_write_status=ok`。
- Cloud 查询：`python .agent_work/temp/check_m15_langfuse_visibility.py e62319e3b05944ca90d4fbc6540cb5df` -> `visible_after_seconds=0.7`，`score_count=0`（M16 只写 trace，不写 score；score 属于 M17）。
- Eval path 覆盖：`python -m eval.run_eval --trace .agent_work/temp/m16-eval-traces.jsonl --report .agent_work/temp/m16-eval-report.md` -> passed=6/6；抽查首行 `langfuse_trace_id=None`、`langfuse_write_status=skipped`。
- 全量测试：`python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m16-full-final-2` -> 96 passed, 2 skipped, 1 warning（既有 Starlette/httpx deprecation）。
- 备注：一次全量复跑 `--basetemp=.agent_work/temp/pytest-m16-full-final` 在 300s 超时，输出停在 `tests/test_phase3a_pipeline.py` 后半段；加长到 420s 后通过，判定为耗时波动，不是业务失败。

## 后续不在 M16 做

- 不改 `/api/query` 响应 Schema，不把 `langfuse_trace_id` 暴露给 API 用户。
- 不建设 scorer / score 回写；那是 M17。
- 不做真实 span 嵌套和精确时间线；RAG/Hybrid 阶段 pipeline 埋点下沉后再补。
