# M6 Implementation Notes

- [x] 用户确认 EvalOps-lite 优先通过 FastAPI `/api/query` 调用，不直接绕过 API 调本地 pipeline。
- [x] 用户确认 Streamlit 只做最小演示闭环：answer / SQL / table / chart / safety_status / trace_id。
- [x] 用户确认阶段二验收报告写 v0/v1 能力清单，但自动化评测只覆盖 6 条 smoke。
- [x] 从 `eval/cases_plan.md` 抽 6 条 SQL smoke，落地 `eval/cases/smoke.yaml`。
- [x] 实现 `eval/run_eval.py`，批量执行、评分并输出 `eval/reports/latest.md`。
- [x] 实现 `demo/streamlit_app.py`，通过 HTTP 调用真实 `/api/query`。
- [x] 更新 README 与 `eval/reports/phase2-v1-acceptance.md`。
- [x] 跑 pytest、`python -m eval.run_eval`，再执行 finish-module 收工。

## Decisions

- Eval seam：选择 `/api/query`。风险是比函数内调更慢，但能验证真实 API 契约、trace、图表字段和演示链路。
- UI scope：选择 Streamlit 最小控制台。风险是没有历史记录/筛选，但避免 M6 扩大成前端大模块。
- Report scope：选择“能力清单 + 6 条 smoke 自动化结果”。风险是全量 32 条仍需后续扩展，但阶段二收尾更稳。
- Eval runtime：默认用 FastAPI `TestClient` + 内存 SQLite seed 调 `/api/query`，不写 MySQL 主库；这仍然验证 API seam。若 simple SQL 触发 LLM 且本地缺 key，会记为 case fail / `llm_generation_error`，但 runner 本身继续产出报告。
- Smoke case 调整：`join_005` 会被现有“渠道 + 订单量”模板提前命中，导致只返回 `order_count` 不返回 `gmv`；`join_001` 又被“退款 + 原因”模板命中。改用 `join_002`，可稳定走 LLM 三表 join，并命中 `channels/orders/refunds`。
- 验证坑：首次全量 pytest 用默认 `.agent_work/temp/pytest-tmp` 时，M5 相关测试 setup 阶段因 Windows `PermissionError` 无法删除旧 basetemp；这与 M5 验收记录里的旧临时目录权限问题一致。改用新的 `--basetemp=.agent_work/temp/pytest-m6-tmp` 复跑。
