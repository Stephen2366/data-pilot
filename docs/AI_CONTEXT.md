# DataPilot AI Context（技术档案）

> 续接任务、查 bug 读这个。记录 git 和代码里查不到的信息：为什么这么做、验证过什么、有什么坑等。硬约束见 CLAUDE.md/AGENTS.md（自动加载），任务见当前阶段计划文件（现指向见下方「当前状态」）。「当前状态」「已知的坑」「最新事实快照」「当前技术选型快照」保持最新；「变更记录」已移至 `AI_CONTEXT_CHANGELOG.md`。

## 当前状态（唯一权威出处）

- 当前阶段计划文件：`docs/phase3a-plan.md`
- 当前模块：M14-lite Phase 3A 收口（开发中）
- 下一模块：阶段三 RAG / Hybrid（待定）
- 上一模块验收：M13 已验收（2026-07-26，报告 accept-M13-20260726.md）
- 阻塞项：无
- 更新时间：2026-07-27

## 当前技术选型快照

- 后端框架：FastAPI + Pydantic Schema；`/api/query` 使用结构化 `AgentResponse`
- 数据库主路径：MySQL `datapilot_dev` + SQLAlchemy ORM + Alembic migration；SQLite 仅用于测试 / smoke
- 数据库状态速查：`docs/database-current-state.md` 记录 Phase 2.7 后 14 表清单、指标口径、固定 seed 事实和后续写 plan 注意事项
- 数据准备：`scripts/seed_data.py` 写入确定性电商 / SaaS 运营数据和固定业务事实
- NL2SQL：M3 模板 SQL 优先；M4 起模板未命中时走 DeepSeek，Schema / KPI / few-shot 从 `domain_pack/` 加载
- SQL 安全：sqlglot AST 只读检查 + 表级 RBAC + `users.email/users.phone` 敏感字段策略；安全能力不只靠 prompt
- Agent 编排：先用普通 Python pipeline，不上复杂 LangGraph；字段按未来 graph state 预留；后续进入多步骤 Agent / RAG 编排时，可在不改响应契约的前提下迁移到 LangGraph。
- Trace / Eval：Agent Trace 默认写 JSONL 到 `eval/traces/traces.jsonl`；M6 EvalOps-lite 已复用 AgentResponse / trace 字段跑 6 条 SQL smoke；JSONL 默认不提交；后续如需查询和聚合，可迁移到 SQLite 或独立 EvalBench 平台
- 图表：后端输出 Vega-Lite 兼容 `chart_spec`，当前仅覆盖基础 bar / line / horizontal_bar 和单指标柱图
- 演示：M6 已提供 `demo/streamlit_app.py` 最小演示控制台，通过 HTTP 调用 `/api/query` 展示 answer / SQL / table / chart / trace

## 最新事实快照

### 技术默认值

- Schema Retrieval 默认：`inmemory + deterministic`；`milvus` / `siliconflow` / `dashscope(qwen3.7-text-embedding)` 只通过环境变量显式开启，不作为当前 Text2SQL 主线默认值。
- SQL 安全默认：敏感字段优先于角色权限；`admin` 也不能通过 Text2SQL 直出 `users.email/users.phone`，后续如需查看应走脱敏 / 审计 / 专门接口。
- Trace 默认：Agent Trace 写入 `eval/traces/traces.jsonl`；测试、smoke 和临时实验可改写到 `.agent_work/temp/`。
- Eval 默认：formal / challenge 用于主线验收和回归对照；diagnostic 用于定位边界和下一步问题，不追满分。

### 最新评测基线

- M13 后真实 LLM 基线（2026-07-26，阶段三A上一轮稳定快照）：formal `10/10`（`eval/reports/phase3a-new-pipeline.md`）、challenge `14/16`（`eval/reports/phase3a-challenge-new-pipeline.md`）、diagnostic `23/32`，`review_required=3`（`eval/reports/phase3a-diagnostic-new-pipeline.md`）。
- M14-lite 后 DeepSeek / 本地 retrieval 临时快照（2026-07-27，真实 LLM 有波动）：formal 曾跑出 `9/10`，最新补测为 `8/10`；challenge `12/16`；diagnostic `24/32`。本轮 result_match / 安全 / trace 口径更严格，不能直接当作 M13 退化结论。
- M14-lite 后 Qwen 主模型对照（2026-07-27）：`qwen3.7-plus` formal `9/10`、challenge `13/16`、diagnostic `21/32`；`qwen3.7-max` diagnostic `22/32`。结论：Qwen 可保留为显式候选，但默认仍不切。
- M14-lite 后 embedding formal 对照（2026-07-27，固定主模型 DeepSeek）：本地 `inmemory + deterministic` 最新补测 `8/10`，`Milvus + SiliconFlow BAAI/bge-m3` `8/10`，`Milvus + qwen3.7-text-embedding` `9/10`。差距仅 1 题，后续进入 RAG / Hybrid 再测 challenge / diagnostic。

### 重要实验结论

- Milvus/SiliconFlow：2026-07-26 临时 A/B 显示 formal `10/10` 持平、challenge `14/16` 持平、diagnostic `23/32 -> 20/32`，所以不切默认。
- M9.1/M9.2 结论：Milvus adapter / SiliconFlow embedding provider 可用，但当前 Text2SQL 主线默认仍保留轻量 deterministic / in-memory。
- Qwen/DashScope：2026-07-27 主模型 formal：DeepSeek `9/10`、Qwen `qwen3.7-plus` `9/10`；challenge：DeepSeek `12/16`、Qwen `qwen3.7-plus` `13/16`；diagnostic：DeepSeek `24/32`、Qwen `qwen3.7-plus` `21/32`、Qwen `qwen3.7-max` `22/32`。`qwen3.7-max` 比 plus 略好，但独有失败里 blocking case 更多，稳定性仍不如 DeepSeek。Embedding 侧 formal：本地 `inmemory + deterministic` 补测 `8/10`，`Milvus + SiliconFlow BAAI/bge-m3` `8/10`，`Milvus + qwen3.7-text-embedding` `9/10`。结论：Qwen embedding 值得继续测，效果好但差距只有 1 题且受 LLM 波动影响，Phase 3A 默认不切。

## 已知的坑（活跃列表，过期即删）

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 同时定义 `Base` 又导入所有模型注册 Alembic metadata | 业务代码若先从 `app.models` 聚合包导入模型，可能触发循环导入 | API / 工具层优先沿用 `app.db.base` 暴露的模型导入路径；后续若重构，可拆 `app/db/base_class.py` 和 `app/db/base.py` |
| Windows 下 `.agent_work/temp/pytest-tmp` 偶发被旧 pytest 临时目录锁住 | 测试可能因 `PermissionError` 删除 basetemp 失败而假失败 | 不改业务代码，换新的 `--basetemp=.agent_work/temp/<name>` 复跑 |
| DB comment 在 PowerShell 离线 SQL 输出中乱码 | 影响离线 SQL 文件可读性；在线迁移和建表正常 | 暂不改业务；如需导出 SQL 文件，再统一处理输出编码或将 DB comment 改为 ASCII |
| 工作树可能有用户或其他工具留下的未提交改动 | 容易误回滚非本次任务修改 | 动文件前看 `git status --short`，不回滚非本次任务改动 |

## 变更记录索引

- 完整历史变更、实验记录和模块档案已拆到 `docs/AI_CONTEXT_CHANGELOG.md`。
- `AI_CONTEXT.md` 只维护当前状态、当前默认值、最新基线、重要实验结论和活跃坑，避免续接时默认加载过长历史。
- 新增模块档案、真实 LLM eval、A/B 实验、smoke 结论和”不切默认”等路线判断，写入 `docs/AI_CONTEXT_CHANGELOG.md`；必要的最新结论同步摘要到本文件「最新事实快照」。
- 2026-07-28：第二个项目已由 AgentEvalOps / agent-eval-ops 改名为 **EvalBench / eval-bench**。文档中旧名已批量替换，历史存档（archive-dormant / archive-versions、phase3b-langfuse-plan v1-v3、phase3b-langfuse-plan-review.md）保留原名不改。

