# M3 临时过程记录

- 2026-07-19：M3 严格按 v0 范围实现，不接 LLM、不做 RBAC / 敏感字段策略；模板 SQL 和用户直接输入 SQL 都先经过 `engine/sql_guard/guard.py` 的 sqlglot 只读检查。
- 2026-07-19：模板 SQL 使用 MySQL / SQLite 都支持的基础语法，保证 MySQL 主路径和 SQLite 自动化测试路径共享同一批 SQL；6 月时间窗口参数统一为 `2026-06-01 00:00:00` 到 `2026-07-01 00:00:00`。
