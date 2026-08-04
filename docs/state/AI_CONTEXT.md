# DataPilot AI Context（续接仪表盘）

> 续接任务、查 bug 先读本文。这里只保留当前状态、默认值、最近事实、路线判断和活跃坑；运行命令见 `docs/state/runbook.md`，评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史见 `docs/state/AI_CONTEXT_CHANGELOG.md`。

## 当前状态（唯一权威出处）

- 当前阶段计划文件：`docs/phase3b-langfuse-plan-v6.md`
- 当前模块：M22 Eval Contract / Semantic Output Stabilization（实现完成；Qwen / Milvus / RRF 新口径首轮实验待用户确认）
- 下一模块：M23（在 M22 实验扩展完成后，再提出新的 retrieval 方法假设；不复用 M21 的 193-doc 对照）
- 当前模块验收：M22 未验收（待 accept-module）
- 上一模块验收：M21 未验收（待 `accept-module`）
- 阻塞项：无
- 更新时间：2026-08-04

## 必读规则

- 开始任何开发 / 排障 / 验证前，必须先读本文。
- 只要要运行命令、切模型、开 LangFuse、跑 eval，必须读 `docs/state/runbook.md`。
- 只要涉及 eval 数字、模型 A/B、失败归因、测试集口径、通过率解读，必须读 `docs/state/eval-baselines.md`。
- 只要涉及 SQL、字段、指标、seed、expected SQL、`result_match`，必须读 `docs/state/database-current-state.md`。
- 只要涉及 Schema Retrieval、Milvus collection、embedding provider / model / dimension、`schema_docs_hash`，必须读 `docs/state/schema-retrieval-milvus-embedding.md`。
- 只要需要追溯为什么这样设计、历史实验、默认值为何不切，必须读 `docs/state/AI_CONTEXT_CHANGELOG.md`。
- `docs/dev-log.md` 面向用户学习复盘；只有写日志、解释面试讲法或用户要求时再读。
- 不允许只凭本文摘要修改默认模型、默认 embedding、正式 eval case、安全策略或数据库结构；这些长期影响选择必须先向用户说明方案 / 风险 / 后续影响并等待确认。

## 当前默认值

- 后端：FastAPI + Pydantic Schema；`/api/query` 返回结构化 `AgentResponse`。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy ORM + Alembic；SQLite 仅用于测试 / smoke。
- 数据底座：Phase 2.7 后 14 张物理表，固定业务事实和指标口径以 `docs/state/database-current-state.md` 为准。
- NL2SQL：M3 模板 SQL 优先；模板未命中走 LLM + Schema Retrieval + QueryPlan + SQL Guard。
- 主模型默认：DeepSeek `deepseek-v4-flash`，配置入口为 `LLM_PROVIDER=deepseek` + `LLM_MODEL=deepseek-v4-flash`。
- Qwen 主模型：只作为显式候选 / A/B，对应 `LLM_PROVIDER=qwen` + `QWEN_MODEL=...`；当前不读 `LLM_MODEL`。
- Schema Retrieval 默认：`inmemory + deterministic`；`milvus` / `siliconflow` / `dashscope(qwen3.7-text-embedding)` 只通过环境变量显式开启。
- SQL 安全：sqlglot AST 只读检查 + 表级 RBAC + 敏感字段策略；`admin` 也不能通过 Text2SQL 直出 `users.email/users.phone`。
- Trace / Eval：默认 JSONL trace；LangFuse 默认关闭，仅作为旁路观测和 score 回写增强；eval 入口和开关见 `docs/state/runbook.md`。

## 最近验证事实

| 日期 | 事实 |
|---|---|
| 2026-08-02 | M19 failure triage 已完成：`eval/run_eval.py` 默认报告新增 `Failure Triage Summary`，支持 `--triage-json` 和 `--compare-triage-left/right/report`；LangFuse 可选回写 `triage:*` scores。 |
| 2026-08-02 | M19 代码验证：focused tests、M16-M19 focused tests、全量 pytest 均已通过；全量快照为 `121 passed, 2 skipped`。 |
| 2026-08-02 | M19 LangFuse Cloud smoke：代理下 `langfuse_triage_scores=ok:24`；说明 triage score 可写回 Cloud。 |
| 2026-08-02 | M19 DeepSeek `deepseek-v4-flash` 快照：formal `7/10`、challenge `9/16`、diagnostic `19/32`；这是 triage 验证快照，不直接等同稳定能力基线。 |
| 2026-08-02 | M19 Qwen `qwen3.7-max` 对照：formal `8/10`、challenge `12/16`、diagnostic `22/32`；分数更好，但 `schema_context` 仍为 6、`schema_retrieval` 比 DeepSeek 多 1。 |
| 2026-08-02 | M19 后续 Qwen embedding / Milvus 复测：Qwen `qwen3.7-max` + Qwen embedding 为 formal `8/10`、challenge `12/16`、diagnostic `20/32`；DeepSeek + Qwen embedding diagnostic 为 `19/32`。 |
| 2026-08-02 | Milvus `datapilot_schema_docs` 当前发现重复灌入污染：schema docs 实际 193 条，但 collection `row_count=19493`（约 `193 * 101`）；因此 Qwen embedding / Milvus A/B 结果不能直接当作 embedding 模型优劣结论。 |
| 2026-08-02 | M20 已完成索引卫生修复：Milvus eval 使用 run-scoped vector index 复用，报告写出 `schema_docs_hash` / collection / row_count / oracle backend；clean smoke `row_count=193`。 |
| 2026-08-02 | M20 DeepSeek + clean Milvus + Qwen embedding diagnostic 为 `17/32`，低于 M19 污染链路 `19/32`；说明 clean Milvus 后仍未看到 Qwen embedding 稳定收益，但不自动改默认 embedding。 |
| 2026-08-02 | M20 Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic 完整跑通：`21/32`（row_count=193、run_scoped）；高于同链路 DeepSeek `17/32` 与 M19 污染 Qwen `20/32`；提升来自 query_plan/plan_validation 消失，`schema_context` 7 仍是主失败簇。 |
| 2026-08-02 | Retrieval-only benchmark 已新增：Qwen embedding vector-only recall `0.929` 高于 deterministic `0.787`，但 merged recall 均为 `0.738`；说明 embedding 有信号，当前瓶颈更像 fusion / rerank。 |
| 2026-08-03 | M21 新增显式 `rrf` fusion 实验（默认仍为 `weighted`，不读取任何 `expected_*` 标签）。retrieval-only 上，Milvus + Qwen embedding merged recall `0.738 → 0.929`、relation `0.633 → 0.967`；但同配置 DeepSeek diagnostic `21/32 → 18/32`，并新增 `plan_validation 0→3`，故 RRF 记录为否定实验且不切默认。 |
| 2026-08-02 | `qwen3.8-max` 当前 DashScope 账号/配置不可用，最小调用返回 HTTP 403 `access_denied`；`qwen3.7-max` 可用。 |
| 2026-07-30 | M18 Experiment 结论：LangFuse UI 的 trace -> Dataset item 可用；UI run 需要项目 LLM key，Webhook run 需要 remote experiment URL，DataPilot 当前不临时实现 webhook runner。 |

## 当前路线判断

| 日期 | 判断 |
|---|---|
| 2026-08-04 | M22 已校正 Context / Output / Result / Manual 契约：不再使用 M21 的 `schema_context` 失败数直接判断检索质量。后续先按 trace 和 failure subtype 定位，再提出单变量假设。 |
| 2026-08-04 | 用户已将 Qwen / Milvus / RRF 的新口径对照纳入 M22：C0 已有 `25/32` 默认快照，首轮只运行 C1-C3 与 retrieval-only 组各一次，用于筛选而非因果结论；结果后再确认是否在同一窗口完整跑 C0-C3 三次。仍固定 194-doc corpus、新 case/scorer 与同一 oracle；RRF、rerank、top_k、默认 embedding 或默认 fusion 均不可因旧实验或单次 run 自动切换。 |
| 2026-08-04 | 默认模型、embedding、向量库和 weighted fusion 保持不变。`db_core_004` 等 SQL plan contract 失败先作为生成链路缺口复核，不预设为 retrieval 问题。 |
| 2026-08-04 | 当前默认 diagnostic `25/32`（自动 `22/27`、人工/诊断 `3/5`）仅是 M22 新口径快照；M21 的 `21/32` 及 193-doc 实验只作历史证据。 |
| 2026-08-04 | Eval / Trace / LangFuse 的功能说明见 `docs/eval-observability-guide.md`；历史实验和取舍见 changelog / eval-baselines，不在本仪表盘重复展开。 |

## 已知的坑（活跃列表）

| 日期 | 坑 | 影响 | 当前处理 |
|---|---|---|---|
| 2026-07-18 起，2026-08-02 仍有效 | `app.db.base` 同时定义 `Base` 又导入所有模型注册 Alembic metadata | 业务代码若先从 `app.models` 聚合包导入模型，可能触发循环导入 | API / 工具层优先沿用 `app.db.base` 暴露的模型导入路径；后续若重构，可拆 `app/db/base_class.py` 和 `app/db/base.py` |
| 2026-07-24 起，2026-08-02 仍有效 | Windows 下 `.agent_work/temp/pytest-tmp` 偶发被旧 pytest 临时目录锁住 | 测试可能因 `PermissionError` 删除 basetemp 失败而假失败 | 不改业务代码，换新的 `--basetemp=.agent_work/temp/<name>` 复跑 |
| 2026-07-22 起，2026-08-02 仍有效 | DB comment 在 PowerShell 离线 SQL 输出中乱码 | 影响离线 SQL 文件可读性；在线迁移和建表正常 | 暂不改业务；如需导出 SQL 文件，再统一处理输出编码或将 DB comment 改为 ASCII |
| 2026-07-18 起，2026-08-02 仍有效 | 工作树可能有用户或其他工具留下的未提交改动 | 容易误回滚非本次任务修改 | 动文件前看 `git status --short`，不回滚非本次任务改动 |
| 2026-07-29 起，2026-08-02 仍有效 | LangFuse SDK 4.14.1 已无旧版 `client.trace()` builder | 按旧博客 / 旧草稿写 smoke 或 M16 backend 会直接 `AttributeError` | 使用 `start_observation(trace_context={"trace_id": uuid4().hex})` / `create_score(trace_id=...)` / `flush()`；细节见 `docs/notes/m15-notes.md` |
| 2026-07-29 起，2026-08-02 仍有效 | Windows 裸连 LangFuse Cloud 偶发 `WinError 10013` | trace visibility 查询 / OTLP export 可能失败，但 score 写入和 JSONL 主链路可正常 | 真实 Cloud smoke 建议显式设置 `HTTP_PROXY` / `HTTPS_PROXY` 为 `http://127.0.0.1:7897`；脚本将 score write 和 trace visibility 分开显示 |
| 2026-08-02 起，M20 已加护栏 | 旧固定 Milvus collection `datapilot_schema_docs` 已被历史重复灌入污染 | 旧 collection 的历史 A/B 结果不能直接作为 embedding 优劣结论 | 新 eval/smoke 使用唯一 collection 或 clean collection；`MilvusVectorIndex` 会拒绝行数/维度不匹配的已有 collection |
| 2026-08-04 起 | SQL generation 可能丢弃 QueryPlan 已明确的 `order_by/limit` | `db_simple_001`、`db_simple_002`、`db_core_004` 已被结构化拦截；需区分真实漏排序与等价表达误拦 | 窄 SQL plan contract 失败 trace 记录候选 SQL 摘要、计划/观察到的排序和 limit；不自动扩大为 AST 或通用列表排序策略 |

## 变更记录索引

- 完整历史变更、实验记录和模块档案写入 `docs/state/AI_CONTEXT_CHANGELOG.md`。
- 真实 LLM eval、A/B、smoke、默认值调整、不采用某方案 / 不切默认等路线判断，必须同步 changelog；影响当前路线的摘要再同步到本文。
- 长期评测数字、报告路径、失败结构和典型错因写入 `docs/state/eval-baselines.md`，本文只保留续接摘要。
- 运行命令、模型/embedding/LangFuse 开关和 eval 命令矩阵写入 `docs/state/runbook.md`。
- Schema Retrieval / Milvus / embedding 的默认值、collection 纪律、报告字段和排查菜单写入 `docs/state/schema-retrieval-milvus-embedding.md`。
