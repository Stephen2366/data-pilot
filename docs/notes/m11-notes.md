# M11 新 Text2SQL Pipeline 与 Trace Steps notes

- [x] 保持 `/api/query` 默认模板优先；只有 `force_new_pipeline=true` 才进入新链路。
- [x] `QueryRequest.force_new_pipeline` 只做可选字段，不改 `AgentResponse` 必填契约。
- [x] trace_steps 只写 JSONL trace，不强塞进公开响应体。
- [x] 新 pipeline 顺序：schema_retrieval -> schema_context -> join_path -> query_plan -> plan_validation -> sql_generation -> sql_guard/sql_execution -> chart_decision。
- [x] SQL 仍统一进入 `run_sql_tool()`；SQL Guard 是最终安全门。
- [x] eval 的 `pipeline_mode=new_text2sql` 已会发送 `force_new_pipeline=true`，API 侧接住后用 trace_steps 证明实际链路。
- [x] 参考资料只借 step log / 局部 schema prompt / DAG trace 表达，不引入 AskData MCP 或 DB-GPT AWEL 运行时。

## 关键决策 / 素材

- 2026-07-24：M11 按计划采用 `force_new_pipeline` 作为 API 侧显式开关，`pipeline_mode` 仍留在 eval 侧；没有新增公开 `plan_execute` 模式，也没有改 `AgentResponse` 必填字段。
- 2026-07-24：`trace_steps` 只写入 JSONL `TraceRecord`，旧响应体不膨胀；默认旧模板路径 trace_steps 为空，强制新链路才记录分步骤。
- 2026-07-24：新 pipeline 复用 `run_sql_tool()`，因此 SQL Guard / RBAC / 敏感字段最终安全边界不变。
- 2026-07-24：TDD 红灯为 `ImportError: cannot import name 'pipeline' from 'engine.nl2sql'`；实现后补强 SQL Guard 回归，`tests/test_phase3a_pipeline.py` 4 passed，1 个既有 TestClient/httpx warning。
- 2026-07-24：计划指定组合 `tests\test_phase3a_pipeline.py tests\test_m5_agent_response.py tests\test_m4_nl2sql.py` 为 12 passed，1 个既有 TestClient/httpx warning。
- 2026-07-24：全量 pytest 为 67 passed，1 个既有 TestClient/httpx warning；`git diff --check` 无 whitespace error，仅 LF->CRLF 提示。
- 参考资料：AskData 的端到端 step log、局部 Schema prompt；DB-GPT AWEL 的 node / context / schema_linking -> sql_gen -> sql_exec -> chart 分段；未引入 AskData MCP / DB-GPT AWEL 运行时。
