# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史见 `docs/state/AI_CONTEXT_CHANGELOG.md`。

## 当前状态（唯一权威出处）

- 当前阶段计划：`docs/notes/m27-plan.md`
- 当前模块：M27 Diagnostic / Eval Case 体系优化（含 Review Bundle 增补，待 `accept-module`）
- 上一模块验收：M26 已验收（2026-08-08）
- 阻塞项：无
- 更新时间：2026-08-09

## 必读规则

- 开始开发、排障或验证前先读本文。
- 运行命令、模型、LangFuse 或 eval 前必须读 `docs/state/runbook.md`。
- 解释 eval 数字、模型 A/B、失败归因或分母时必须读 `docs/state/eval-baselines.md`。
- 涉及 SQL/字段/指标/oracle 时读 `database-current-state.md`。
- 涉及 Milvus/embedding/Schema Retrieval 时读 `schema-retrieval-milvus-embedding.md`。
- 追溯设计原因、历史实验时读 `docs/state/AI_CONTEXT_CHANGELOG.md`。
- 前台等待超时不等于真实 Eval 已结束：按 runbook 用同一 `run_id` 检查 manifest、checkpoint、artifact；不得擅自换 ID 重跑。
- 用户明确说执行某个 eval 时，按 runbook 的“一次精确运行授权”直接执行一次；不重复询问授权，也不扩大范围或切换默认配置。
- 默认模型、embedding、正式 case、安全策略、数据库结构等长期选择，必须先说明方案并等待用户确认。

## 当前默认值

- 后端：FastAPI + Pydantic；`/api/query` 返回 `AgentResponse`。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- NL2SQL：模板优先，未命中走 LLM + Schema Retrieval + QueryPlan + SQL Guard + `output_contract`。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1。
- 默认检索：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅显式实验开启。
- LangFuse 默认关闭，JSONL trace 为主；SQL 安全为只读 AST + RBAC + 敏感字段策略。

## 最近验证事实

| 日期 | 事实 |
|---|---|
| 2026-08-09 | M27 有 28 个 canonical Scenario；一个 Scenario 一次执行，多条 typed assertion 共用证据。旧 formal/challenge/diagnostic 只读冻结，不能与 M27 数字比较。 |
| 2026-08-09 | 当前可比的 Core：Qwen `qwen3.7-plus` 与充值后的 `qwen3.7-max`，各自 local / Milvus 都为 **29 passed / 5 failed / 0 not_observed**、Gate failed。稳定失败是商品退款率排名（result/output/schema context）、实际金额指标映射、渠道 GMV dashboard schema context。 |
| 2026-08-09 | Milvus 实验均使用 DashScope `qwen3.7-text-embedding`、1024 dim、195-doc clean collection、hash `8a8b6626...`；当前样本不足以判断模型或 Milvus 优劣，不切默认。 |
| 2026-08-09 | Review v2 是自动评分后的旁路证据：来源 SHA-256、结构化分类、无候选 SQL 的普通题只能 `insufficient_evidence`；它不改 EvalRun、分母、Gate 或 CI。 |
| 2026-08-09 | 已有可比较 Core 快照，但尚未登记长期正式 M27 基线；长期账本见 `eval-baselines.md`。 |

## 当前路线判断

- (2026-08-09) 优先修复 M27 Core 稳定暴露的 5 条合同失败，再讨论模型或检索优化。
- (2026-08-09) 默认保持 Qwen `qwen3.7-plus` + inmemory deterministic + weighted；任何切换需要单变量重复证据与用户确认。
- (2026-08-09) M22–M26 的旧模型分数、RRF、M25/M26 合同取舍仅作历史参考，不定义当前 M27 路线。

## 已知的坑（活跃列表）

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 的模型注册可能触发循环导入 | 聚合导入模型时可能失败 | API/工具层沿用 `app.db.base` 暴露路径；重构时再拆 base class。 |
| Windows pytest 临时目录偶发被旧进程锁住 | `PermissionError` 导致假失败 | 换新的 `--basetemp=.codex/temp_work/<name>`。 |
| 工作树可能含用户/其他工具未提交改动 | 容易误回滚 | 动文件前先看 `git status --short`，不回滚非本次改动。 |
| 旧 Milvus collection `datapilot_schema_docs` 有重复灌入污染 | 历史 A/B 不可信 | 新 eval 用唯一/clean collection；校验 row count、dimension、schema docs hash。 |
| QueryPlan 可能过宽，或 SQL 与计划不一致 | contract pass 不等于答案正确 | 保持保守 AST 边界，用 output/result/trace 共同定位。 |
| Windows 宿主保留 9091 | Milvus health 检查失败 | 使用 `19091:9091` host 映射。 |

## 历史入口

- 完整变更、实验记录、旧合同取舍：`docs/state/AI_CONTEXT_CHANGELOG.md`。
- 历史 eval 数字：`docs/archive-versions/eval-baselines-old.md`；M27 以后的长期账本：`docs/state/eval-baselines.md`。
