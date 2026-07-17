# DataPilot Dev Log

记录每个阶段性里程碑的交付内容、技术决策、验证结果和面试讲法。这里尽量用新手友好的语言：第一次出现的重要概念，会顺手解释一句，方便之后复盘和准备面试。

## 当前状态速览

- 当前模块：Phase 2 M2 API 与后端工程基础，待开始。
- 最近完成模块：M1 数据底座（2026-07-17）
- 下一步：建立 DB session、分页 CRUD、请求日志和统一异常响应。
- 阻塞项：无。
- 状态更新时间：2026-07-17

## ★ 2026-07-16 / Phase 2 M0 - 工程骨架与配置基础

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

**改动**

- 在 `phase2-plan.md` 增加“架构底线与可降级边界”：P0 不可降级，P1 可简化但要保留接口。
- 将简化版 AgentResponse 前置到 M3；M5 只做增量扩展。

**原因**

- 避免“先用临时方案，后面再换正式方案”造成返工。
- 数据库、迁移、SQL Guard、业务 / 引擎分层、AgentResponse、评测用例格式都属于早期要定稳的边界。

**验证与影响**

- 未运行代码测试；本次只改计划文档。
- 后续 M3 必须返回简化版 AgentResponse，SQL 执行必须先经过 SQL Guard v0。

## 2026-07-17 / Phase 2 计划补充 - 多工具协作口径校准

**改动**

- 统一临时目录为 `.agent_work/temp/`，Trace 改放 `eval/traces/`。
- 更新 `AGENTS.md`、`CLAUDE.md`、`phase2-plan.md`、`LEARNING_ROADMAP.md`、`REFERENCE_GUIDE.md` 的相关口径。
- Phase 2 smoke 统一为 6 条 SQL smoke；阶段三补齐 RAG / 混合后再扩展为 10 条 smoke。

**原因**

- 同时使用 Claude Code 和 Codex 时，临时目录不能绑定某个工具名。
- Trace 是评测和复盘数据，不是一次性临时产物。

**验证与影响**

- 未运行代码测试；本次只改文档和目录占位文件。
- 已检查项目内旧临时目录、旧 smoke 数量和旧验证结果表述已清理。
- M1 参考资料口径更新为：SQLAlchemy / Alembic 优先查官方文档，`askdata_agent` 只参考业务元数据和模拟数据组织。

## 2026-07-17 / 补充记录 - 文档口径审查与修正

**改动**

- `README.md`：删除废弃口径“当前默认数据库：SQLite”，改为 MySQL 开发库 `datapilot_dev` 主路径（SQLite 仅测试兜底）；进度标识从“Day 1 工程骨架搭建中”更新为“M0 已完成，推进 M1”。
- 默认库名统一为 `datapilot_dev`：`app/core/config.py` 默认连接串、`.env.example` 示例、`tests/test_health.py` 脱敏测试字面值三处对齐，并在 config.py 注明默认值仅作占位兜底。
- `phase2-plan.md`：M0 小节删除重复的“状态”行；“单一事实源”章节登记模块进度口径——当前进度以 `dev-log.md` 速览为准，完成状态只在“模块总览”表维护。
- 全局 `~/.claude/CLAUDE.md`（项目外）：临时目录规则加“项目 CLAUDE.md 另有约定时以项目约定为准”，避免已废弃的 `.claude/temp_work` 口径经全局规则反复复发。

**原因**

- 例行口径审查发现 README 与 phase2-plan P0“MySQL 主路径”矛盾，属于“废弃口径再次出现”，按文档维护规则清理。
- 模块状态此前在三处维护（模块总览、模块小节、dev-log 速览），容易漂移，收敛为两处并登记单一事实源。

**验证与影响**

- 全局搜索确认 `3306/datapilot?`（非 dev）、README 中 SQLite 主路径表述、“Day 1”进度标识已清零。
- 实际测试：`python -m pytest` → `5 passed`。
- 不影响 M1 计划；遗留待办（本次未处理）：dev 依赖补 `httpx`、空包目录补 `__init__.py`、`.gitkeep` 入库、`redact_database_url` 改用 `rsplit`、LEARNING_ROADMAP 两处旧口径（SQLite/MySQL 执行、Week 2 Redis 缓存表述）。

## 2026-07-17 / 补充记录 - 跨文档重复收敛与文档分工登记

**改动**

- `LEARNING_ROADMAP.md`（项目外）顶部新增「文档定位」声明：路线图只做总览，与具体开发计划（如 `phase2-plan.md`）不一致时以计划为准，AI 发现较大不一致先向用户汇报。
- 32 条评测用例的类型构成明细收敛为唯一出处 `phase2-plan.md` M3：阶段二总目标处改为引用，路线图 Week 2 任务行删去括号明细（路线图「基础 32 条」总览表按定位声明保留）。
- 目录结构分工：项目 `CLAUDE.md` 目录树标注为「权威地图 / 单一事实源」，路线图中的结构示例标注为「仅示意」；README 项目结构章节保持现状，与 CLAUDE.md 同步维护（用户决定）。
- `phase2-plan.md` 规范类复述收敛：全局约束中日志 / 注释两条、模块推进原则中的日志字段清单，均改为引用 CLAUDE.md「开发记录要求」「代码风格」章节。

**原因**

- 例行交叉审查发现四份文档存在多处字面值重复（用例构成 4 处、目录结构 4 处、规范复述 3 处），多处维护易漂移；按「一处定义、他处引用」原则收敛，并用路线图顶部声明兜底所有未逐一标注的历史重复。

**验证与影响**

- 全局搜索确认：用例构成明细在 phase2-plan 内仅剩 M3 一处，路线图 Week 2 行内明细已移除，规范复述已清理。
- 仅文档改动，未涉及代码，无需重跑测试。
- 不影响 M1 计划；遗留（低优先级，未处理）：路线图内部 `agent-eval-ops/` 目录树重复两次、顶部两个「目标」引用块重复。

## 2026-07-17 / 补充记录 - Phase 2 验收口径收敛

**改动**

- `phase2-plan.md` 新增单一事实源口径：M4 简单 SQL 正确性、YAML case 字段、阶段二验收记录落位。
- M4 / v1 的简单 SQL 标准统一为“6 条简单 SQL 中至少 5 条生成并执行正确”，并明确“正确”包含通过 SQL Guard、可执行、返回字段和关键结果符合用例预期。
- M6 不再重复维护 YAML 字段清单，改为引用 `eval/cases_plan.md` 中的字段草案。
- 阶段二验收记录从 `.agent_work/temp/phase2-v1-acceptance.md` 改为 `eval/reports/phase2-v1-acceptance.md`。
- v0 验收补充 M2 落点：4 类列表接口分页 / 筛选、请求日志和统一异常响应。

**原因**

- 计划文档中同一验收项曾出现“可解析 / 执行成功 / 执行正确”三种口径，后续验收容易产生歧义。
- 阶段验收记录会被 README、简历和复盘消费，不适合放在临时目录。
- YAML 字段、Trace 字段、安全拦截清单这类字面值重复越多，越容易漂移。

**验证与影响**

- 仅文档改动，未涉及代码，无需重跑测试。
- 后续执行 M4 时按 v1 验收标准判断简单 SQL，不再用“只要可解析”作为完成标准。
- 后续执行 M6 时，`smoke.yaml` 必须遵循 `eval/cases_plan.md` 的字段草案。

## ★ 2026-07-17 / Phase 2 M1 - 数据底座

### 做了什么

- 新增 7 张 SQLAlchemy ORM 模型：`users`、`products`、`channels`、`orders`、`refunds`、`tickets`、`knowledge_docs`，覆盖主键、外键、索引、状态字段、创建 / 更新时间字段。
- 新增 `app/db/base.py`，统一导入所有模型，保证 Alembic 能读取完整 `Base.metadata`。`metadata` 可以理解成 ORM 对数据库结构的总目录。
- 新增 Alembic 配置和首个 migration：`alembic.ini`、`alembic/env.py`、`alembic/versions/20260717_0001_create_m1_business_tables.py`。
- 新增 `scripts/seed_data.py`，确定性写入用户 50、商品 30、渠道 6、订单 500、退款 80、工单 120、知识文档 8。
- 新增 4 个固定业务事实锚点：2026-06 退款率最高商品、2026-06 GMV 最高渠道、Top 退款原因、待处理高优先级工单数量。
- 新增 `domain_pack/schema_desc/*.md`，为 7 张表补业务描述、字段语义和敏感字段标记。
- 更新 README，加入 M1 ER 图草稿、迁移命令、seed 命令、数据量和固定事实说明。
- 新增 M1 自动化测试：`tests/test_m1_models.py`、`tests/test_m1_alembic_config.py`。

### 技术决策

- 坚持 MySQL + Alembic 作为主路径，seed 脚本不调用 `create_all()` 建表；测试里才使用 SQLite 内存库做快速校验，符合“SQLite 只作为测试或兜底”的阶段约束。
- 状态和角色字段使用字符串列加索引，而不是数据库原生 Enum。原因是角色、订单状态、退款状态、工单状态后续可能扩展，用字符串更适合阶段二迭代；合法值先在 seed、schema_desc 和后续 Pydantic / RBAC 层约束。
- `users.email`、`users.phone` 在模型、schema_desc 和 seed 中都作为敏感字段出现，给 M4 SQL Guard 的敏感字段策略留好入口。
- 固定业务事实直接写进确定性 seed，而不是测试时临时拼数据。这样 M3 模板 SQL 和 M6 smoke 评测可以复用同一批稳定数据。
- Alembic ini 保持 ASCII 注释，避免 Windows 默认 GBK 读取配置时出现 `UnicodeDecodeError`。

### 参考资料

- 阅读了 `REFERENCE_GUIDE.md` 对 M1 的说明：SQLAlchemy / Alembic 没有强参考项目，`askdata_agent` 只参考业务元数据和模拟数据组织。
- 查阅了 `askdata_agent/askdata_pipeline/demo_data.py`：借鉴其“把业务元数据和演示数据集中组织”的思路。
- 查阅了 `askdata_agent/schema_indexing/objects.py`：借鉴字段描述中 `description / aliases / semantic_role / samples / business_usage` 这类信息组织方式。
- 没有照搬 `askdata_agent` 的 SQLite 建库脚本、Milvus / 向量索引依赖，也没有沿用它的交易 / 利率业务域。

### 验证结果

- 已验证 M1 metadata、外键、索引、seed 行数、4 类角色、4 个固定业务事实。
- 已验证 Alembic offline SQL 能用 MySQL dialect 生成。
- 已验证 MySQL 在线迁移成功，当前版本为 `20260717_0001 (head)`。
- 已验证 `alembic check` 无新增 upgrade operations，说明 ORM metadata 与 migration 当前一致。
- 已验证 MySQL seed 成功，输出行数为：用户 50、商品 30、渠道 6、订单 500、退款 80、工单 120、知识文档 8。
- 实际测试：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider` → `9 passed, 1 warning`。warning 来自 FastAPI / Starlette TestClient 对 `httpx` 的依赖提示，不影响 M1。

可复制验证命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic upgrade head
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check
```

### 面试怎么讲

DataPilot 的数据底座不是随手建几张 demo 表，而是按真实分析系统拆成维表和事实表：用户、商品、渠道是维度，订单、退款、工单是运营事实，知识文档给后续 RAG 链路预留入口。迁移全部通过 Alembic 管理，seed 数据里还专门设计了固定业务事实，后续 NL2SQL 和评测可以验证“查出来的答案是否稳定正确”。敏感字段从 M1 就标出来，说明安全策略不是最后补文档，而是会进入 schema、RBAC 和 SQL Guard 的主链路。

### 遗留问题 / 下一步

- M2 需要基于 `settings.database_url` 建 `app/db/session.py`，并使用 `pool_pre_ping=True` 等 MySQL 连接参数。
- M2 需要实现 products / orders / refunds / tickets 至少 4 类列表接口，支持分页和基础筛选。
- M2 需要补请求日志中间件、统一异常响应和基础 Pydantic Schema。
- 当前数据库 comment 在 PowerShell 离线 SQL 输出中会显示为乱码，但 Alembic 配置读取、在线 migration 和表结构创建均已成功；后续如需要导出 SQL 文件，可再统一处理输出编码或将 DB comment 改为 ASCII。
