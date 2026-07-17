# DataPilot Dev Log

记录每个阶段性里程碑的交付内容、技术决策、验证结果和面试讲法。这里尽量用新手友好的语言：第一次出现的重要概念，会顺手解释一句，方便之后复盘和准备面试。

## 当前状态速览

- 当前模块：Phase 2 M1 数据底座，待开始。
- 下一步：定义 7 张 ORM 表，接入 Alembic migration，编写 seed 数据和固定业务事实。
- 阻塞项：无。

## 2026-07-16 / Phase 2 M0 - 工程骨架与配置基础

### 做了什么

- 建立了项目的基础目录：`app/` 放 Web 服务代码，`engine/` 放后续 Agent 通用能力，`domain_pack/` 放业务配置，`eval/` 放评测相关内容。
- 新增 `app/main.py`，创建 FastAPI 应用，并提供 `/health` 健康检查接口。FastAPI 是 Python Web 框架，用来对外提供 HTTP API。
- 新增 `app/core/config.py`，用 Pydantic Settings 从 `.env` 读取配置。Pydantic Settings 可以把环境变量自动变成 Python 对象，避免在代码里到处手写 `os.getenv()`。
- 新增 `pyproject.toml`，集中声明项目依赖。这里包含 FastAPI、SQLAlchemy、Alembic、sqlglot、pandas、Streamlit、Altair、PyMySQL 等阶段二会用到的库。
- 新增 `.env.example`，只放配置模板和占位说明；真实账号、密码、API Key 只放本地 `.env`，不提交到仓库。
- 新增配置测试和健康检查测试：`tests/test_config.py`、`tests/test_health.py`，用于确认配置能读、接口能跑。

### 技术决策

- 数据库直接使用 MySQL 开发库 `datapilot_dev`，而不是把 SQLite 当主路径。SQLite 是轻量本地数据库，适合快速 demo；MySQL 更接近真实后端项目，后续讲表结构、索引、迁移、权限会更自然。
- 后续 ORM 和迁移会围绕 MySQL 设计。ORM 是“用 Python 类表示数据库表”的写法；SQLAlchemy 是常用 ORM；Alembic 是配合 SQLAlchemy 管理建表、改表历史的迁移工具。
- SQLAlchemy 连接串使用 `mysql+pymysql://...`。`PyMySQL` 是 Python 连接 MySQL 的驱动，就像数据库和 Python 之间的插头。
- 保留 `SettingsConfigDict(extra="ignore")`。意思是 `.env` 里如果有当前代码还没用到的字段，配置加载时先忽略，不让服务因为“多写了配置”而启动失败。
- `.env.example` 保留，但只写占位和说明；真实 `.env` 可以更短，只保留你当前常用的 DeepSeek、SiliconFlow、MySQL、LangSmith 等配置。

### 参考资料

- 本次 Day 1 没有直接查 `references/` 里的项目。原因是 Day 1 主要是工程骨架、配置读取、健康检查和测试，这些属于通用 FastAPI 后端基础，不需要借鉴外部项目结构。
- 后续会参考。M1 做表结构、SQLAlchemy 模型、Alembic 迁移和模拟数据时，会优先查 `REFERENCE_GUIDE.md` 里提到的 `askdata_agent`；到 SQL 安全和评测用例时，会查 `QueryMind`。

### 验证结果

- 已验证 `.env` 能被 `Settings()` 读取，`DATABASE_URL` 是 MySQL URL，且指向 `datapilot_dev`。
- 已验证 `pymysql` 可导入，说明 Python 环境里已经有 MySQL 驱动。
- 实际测试：`python -m pytest` → `5 passed`


### 面试怎么讲

DataPilot 不是只写一个脚本 demo，而是从第一天按真实后端服务搭骨架：FastAPI 负责 API 层，Pydantic Settings 负责配置管理，SQLAlchemy + Alembic 负责后续数据模型和数据库迁移。数据库直接使用 MySQL 开发库，后面讲表设计、权限控制、索引和迁移时更贴近真实业务项目。配置层允许 `.env` 里存在暂时没用到的字段，但代码只建模当前真正使用的配置，这样既方便本地开发，也避免配置混乱。

### 遗留问题 / 下一步

- M1 需要定义 7 张核心表的 SQLAlchemy ORM 模型。
- M1 需要接入 Alembic，并用 `datapilot_dev` 实际执行 migration。
- 后续需要在 `app/db/session.py` 中基于 `settings.database_url` 创建 SQLAlchemy engine，并为 MySQL 增加连接池参数。

## 2026-07-17 / Phase 2 计划补充 - 架构底线与降级边界

### 改动

- 在 `phase2-plan.md` 增加“架构底线与可降级边界”：P0 不可降级，P1 可简化但要保留接口。
- 将简化版 AgentResponse 前置到 M3；M5 只做增量扩展。

### 原因

- 避免“先用临时方案，后面再换正式方案”造成返工。
- 数据库、迁移、SQL Guard、业务 / 引擎分层、AgentResponse、评测用例格式都属于早期要定稳的边界。

### 验证与影响

- 未运行代码测试；本次只改计划文档。
- 后续 M3 必须返回简化版 AgentResponse，SQL 执行必须先经过 SQL Guard v0。

## 2026-07-17 / Phase 2 计划补充 - 多工具协作口径校准

### 改动

- 统一临时目录为 `.agent_work/temp/`，Trace 改放 `eval/traces/`。
- 更新 `AGENTS.md`、`CLAUDE.md`、`phase2-plan.md`、`LEARNING_ROADMAP.md`、`REFERENCE_GUIDE.md` 的相关口径。
- Phase 2 smoke 统一为 6 条 SQL smoke；阶段三补齐 RAG / 混合后再扩展为 10 条 smoke。

### 原因

- 同时使用 Claude Code 和 Codex 时，临时目录不能绑定某个工具名。
- Trace 是评测和复盘数据，不是一次性临时产物。

### 验证与影响

- 未运行代码测试；本次只改文档和目录占位文件。
- 已检查项目内旧临时目录、旧 smoke 数量和旧验证结果表述已清理。
- M1 参考资料口径更新为：SQLAlchemy / Alembic 优先查官方文档，`askdata_agent` 只参考业务元数据和模拟数据组织。

## 2026-07-17 / 补充记录 - 文档口径审查与修正

### 改动

- `README.md`：删除废弃口径“当前默认数据库：SQLite”，改为 MySQL 开发库 `datapilot_dev` 主路径（SQLite 仅测试兜底）；进度标识从“Day 1 工程骨架搭建中”更新为“M0 已完成，推进 M1”。
- 默认库名统一为 `datapilot_dev`：`app/core/config.py` 默认连接串、`.env.example` 示例、`tests/test_health.py` 脱敏测试字面值三处对齐，并在 config.py 注明默认值仅作占位兜底。
- `phase2-plan.md`：M0 小节删除重复的“状态”行；“单一事实源”章节登记模块进度口径——当前进度以 `dev-log.md` 速览为准，完成状态只在“模块总览”表维护。
- 全局 `~/.claude/CLAUDE.md`（项目外）：临时目录规则加“项目 CLAUDE.md 另有约定时以项目约定为准”，避免已废弃的 `.claude/temp_work` 口径经全局规则反复复发。

### 原因

- 例行口径审查发现 README 与 phase2-plan P0“MySQL 主路径”矛盾，属于“废弃口径再次出现”，按文档维护规则清理。
- 模块状态此前在三处维护（模块总览、模块小节、dev-log 速览），容易漂移，收敛为两处并登记单一事实源。

### 验证与影响

- 全局搜索确认 `3306/datapilot?`（非 dev）、README 中 SQLite 主路径表述、“Day 1”进度标识已清零。
- 实际测试：`python -m pytest` → `5 passed`。
- 不影响 M1 计划；遗留待办（本次未处理）：dev 依赖补 `httpx`、空包目录补 `__init__.py`、`.gitkeep` 入库、`redact_database_url` 改用 `rsplit`、LEARNING_ROADMAP 两处旧口径（SQLite/MySQL 执行、Week 2 Redis 缓存表述）。

## 2026-07-17 / 补充记录 - 跨文档重复收敛与文档分工登记

### 改动

- `LEARNING_ROADMAP.md`（项目外）顶部新增「文档定位」声明：路线图只做总览，与具体开发计划（如 `phase2-plan.md`）不一致时以计划为准，AI 发现较大不一致先向用户汇报。
- 32 条评测用例的类型构成明细收敛为唯一出处 `phase2-plan.md` M3：阶段二总目标处改为引用，路线图 Week 2 任务行删去括号明细（路线图「基础 32 条」总览表按定位声明保留）。
- 目录结构分工：项目 `CLAUDE.md` 目录树标注为「权威地图 / 单一事实源」，路线图中的结构示例标注为「仅示意」；README 项目结构章节保持现状，与 CLAUDE.md 同步维护（用户决定）。
- `phase2-plan.md` 规范类复述收敛：全局约束中日志 / 注释两条、模块推进原则中的日志字段清单，均改为引用 CLAUDE.md「开发记录要求」「代码风格」章节。

### 原因

- 例行交叉审查发现四份文档存在多处字面值重复（用例构成 4 处、目录结构 4 处、规范复述 3 处），多处维护易漂移；按「一处定义、他处引用」原则收敛，并用路线图顶部声明兜底所有未逐一标注的历史重复。

### 验证与影响

- 全局搜索确认：用例构成明细在 phase2-plan 内仅剩 M3 一处，路线图 Week 2 行内明细已移除，规范复述已清理。
- 仅文档改动，未涉及代码，无需重跑测试。
- 不影响 M1 计划；遗留（低优先级，未处理）：路线图内部 `agent-eval-ops/` 目录树重复两次、顶部两个「目标」引用块重复。
