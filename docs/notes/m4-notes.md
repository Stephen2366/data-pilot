# M4 开发过程素材

- 2026-07-20 方案确认：M4 采用 DeepSeek 作为主 LLM provider；只实现一个实际可用 provider，不做多厂商复杂抽象。API key 缺失或调用失败时返回可诊断的结构化错误，不降级成假 LLM。
- 2026-07-20 RBAC 边界确认：M4 先做表级 + 字段级 allowlist，覆盖 `users.email`、`users.phone` 敏感字段拦截；行级权限明确作为后续风险/遗留，不在 M4 扩大范围。
- 2026-07-20 TDD 红灯：`pytest tests\test_m4_nl2sql.py -p no:cacheprovider` 失败于缺 `engine.nl2sql.schema_loader`、`engine.nl2sql.prompt`、`engine.nl2sql.generator`、`engine.sql_guard.policy`，以及 `/api/query` 尚未接 LLM 路径。
- 2026-07-20 TDD 绿灯：`pytest tests\test_m4_nl2sql.py -p no:cacheprovider` = 5 passed；全量 pytest = 24 passed。warning 仍是既有 Starlette/httpx TestClient 提示。
- 2026-07-20 M4 smoke：`scripts\smoke_m4_nl2sql.py` 真实调用 DeepSeek，6 条 simple SQL 中 5 条通过，摘要 `.agent_work/temp/m4-smoke.md`，prompt 快照 `.agent_work/temp/prompt-snapshots.md`。`sql_005` 模型返回 pending 工单但缺 `status` 列，未达该条 expected_columns；总体验收口径仍满足 5/6。
- 2026-07-20 Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`。
