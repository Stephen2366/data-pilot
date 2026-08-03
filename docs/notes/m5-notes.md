# M5 开发随手记录

- 2026-07-20 Trace 存储方案：用户确认按建议执行 JSONL 主路径；不在 M5 引入 SQLite Trace 表或 TraceRepository 抽象。原因：phase2-plan 已把 JSONL 定为可简化但接口稳定的路径，M6 EvalOps-lite 可直接按行读取，后续迁移只换存储层。
- 2026-07-20 SQL 执行收口：`/api/query` 不再直接 `db.execute()`，改为调用 `engine/tools/sql_tool.py`；SQL Tool 内部统一完成 SQL Guard policy、tables_used 提取、数据库执行、耗时和 tool call 记录。
- 2026-07-20 图表规则：`domain_pack/chart_templates/basic.yaml` 只保存 bar / line / horizontal_bar 三类模板；`chart_tool` 用轻量规则选择图表。GMV 单指标用合成 `metric_name/value` 生成单柱图，避免 M5 smoke 无法覆盖第三类聚合结果。
- 2026-07-20 踩坑：退款率模板同时返回 `refund_count/order_count/refund_rate`，初版 chart tool 取第一个数值列导致图表画 `refund_count`；已改为按问题关键词优先选择 `refund_rate`、`gmv`、`order_count`。
- 2026-07-20 验证素材：M5 聚焦测试首次红灯缺 `docs_used/chart_spec`；补实现后 `tests/test_m5_agent_response.py` 3 passed。M5 smoke 首次失败于脚本把 GMV 单指标的 Vega-Lite `y=value` 误判为字段不匹配，已改为读取 `data.values[0].metric_name`，随后 4/4 passed 且 trace_lines=4。
