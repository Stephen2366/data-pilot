# DataPilot AI Context（技术档案）

> 续接任务、查 bug 读这个。记录 git 和代码里查不到的信息：为什么这么做、验证过什么、有什么坑等。硬约束见 CLAUDE.md/AGENTS.md（自动加载），任务见当前阶段计划文件（现指向见下方「当前状态」），均不在此重复。用户学习复盘见 dev-log.md。「当前状态」「已知的坑」保持最新；「模块技术档案」「补充记录」只追加不改写。

## 当前状态（唯一权威出处）

- 当前阶段计划文件：`docs/phase2-plan.md`
- 当前模块：Phase 2 M5 AgentResponse 扩展、Trace、Tool 与图表，待开始（任务详情 → 计划文件 M5 小节）
- 上一模块验收：M4 未验收（待 accept-module）
- 阻塞项：无
- 更新时间：2026-07-20

## 已知的坑（活跃列表，过期即删）

- `app.db.base` 目前同时定义 `Base` 又导入所有模型来注册 Alembic metadata；如果业务代码先从 `app.models` 聚合包导入模型，可能触发循环导入。当前规避方式：API / 工具层优先沿用 `app.db.base` 暴露的模型导入路径；后续若重构，可拆 `app/db/base_class.py`（只放 Base）和 `app/db/base.py`（只汇总 metadata）
- DB comment 在 PowerShell 离线 SQL 输出中乱码；在线迁移和建表正常，无害。如需导出 SQL文件，再统一处理输出编码或将 DB comment 改为 ASCII（M1）
- 工作树可能有用户或其他工具留下的未提交改动；动文件前先 `git status --short`，不要回滚非本次任务的改动
- Milvus 本地暂不可用（兼容性问题），阶段三 RAG 主路径按 ChromaDB 规划；阶段三启动时重新评估 Milvus 兼容性

## 模块技术档案（新的在上）

### M4 NL2SQL 最小链路与安全（2026-07-20）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`engine/nl2sql/schema_loader.py`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`engine/sql_guard/policy.py`、`engine/sql_guard/rbac.py`、`app/api/query.py`、`tests/test_m4_nl2sql.py`、`scripts/smoke_m4_nl2sql.py`、`domain_pack/sql_examples/error_cases.yaml`、`.env.example`、`README.md`、`.agent_work/temp/m4-notes.md`、`.agent_work/temp/prompt-snapshots.md`、`.agent_work/temp/m4-smoke.md`
- 关键决策：
  - LLM provider 采用 DeepSeek 主路径：只实现一个实际可用 provider，不做多厂商复杂抽象；API key 缺失、网络失败或返回结构异常时转成 `LLMGenerationError`，由 `/api/query` 返回结构化拦截，不降级成假 LLM
  - `/api/query` 保持模板优先：M3 已验证模板继续优先执行，模板未命中才构造 prompt 调 LLM；所有模板 SQL 和 LLM SQL 都统一进入 M4 `validate_sql_policy`
  - RBAC 先做表级 + 字段级 allowlist：`admin` 全量，`ops` 可看全表但不能看敏感字段，`customer_service` 限 `tickets / knowledge_docs`，`demo_user` 限脱敏样例表；行级权限不在 M4 扩展
  - Schema / KPI / few-shot 均从 `domain_pack/` 读取：避免把电商字段、GMV、退款率等业务口径写死在 `engine/`
- 参考资料：未查阅外部参考；本次按 phase2-plan M4 范围、M1 schema_desc / metrics、M3 模板 SQL 和用户确认的 DeepSeek / RBAC 边界实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m4_nl2sql.py -p no:cacheprovider` 首次失败于缺 `engine.nl2sql.schema_loader`、`engine.nl2sql.prompt`、`engine.nl2sql.generator`、`engine.sql_guard.policy`，以及 `/api/query` 尚未接 LLM 路径
  - M4 聚焦测试：`5 passed, 1 warning`（Starlette/httpx TestClient 提示，不影响本模块）
  - 全量 pytest：`24 passed, 1 warning`（同上）
  - M4 smoke：`scripts\smoke_m4_nl2sql.py` 真实调用 DeepSeek，6 条 simple SQL 中 5 条通过；prompt 快照写入 `.agent_work/temp/prompt-snapshots.md`，摘要写入 `.agent_work/temp/m4-smoke.md`
  - smoke 已知偏差：`sql_005` 查询待处理工单返回 `pending` 数据且 `safety=passed`，但模型 SQL 未把 `status` 放进 SELECT，导致 expected_columns 缺 `status`；M4 5/6 验收口径仍通过，后续可在 M5/M6 通过提示词或 eval 反馈收紧列选择
  - 安全覆盖：自动化测试验证 DDL/DML 拦截、`users.email` 敏感字段拦截、`customer_service` 越权访问 `orders` 拦截，均返回结构化 `AgentResponse`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - `git diff --check`：仅 `.env.example`、`README.md`、`app/api/query.py` 的 CRLF 提示，无 whitespace error
- 遗留：
  - M5 接 AgentResponse 扩展、SQL Tool、Trace、成本延迟和图表；当前 M4 仍沿用 M3 简化版响应字段
  - 行级权限、脱敏样例数据和更细角色策略未做；M4 只完成表级 / 字段级核心安全边界
  - LLM 生成列选择仍可能波动，`sql_005` 已记录为提示词 / EvalOps 后续优化素材

### M3 v0 模板 SQL 闭环（2026-07-19）

- 改动范围：`engine/nl2sql/*`、`engine/sql_guard/*`、`app/schemas/agent.py`、`app/api/query.py`、`domain_pack/metrics.yaml`、`domain_pack/sql_examples/basic.yaml`、`eval/cases_plan.md`、`scripts/smoke_v0.py`、`tests/test_m3_query.py`、`README.md`（细节看 git）
- 关键决策：
  - v0 严格使用白名单模板 SQL，不接 LLM、不做自由 SQL 生成；未命中模板时返回结构化拦截说明，避免 M3 范围膨胀
  - SQL 执行入口统一先过 `engine/sql_guard/guard.py`，用 sqlglot AST 只允许单条 `SELECT`；`DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE` 等危险 SQL 返回 `safety_status=blocked`
  - `AgentResponse` 从 M3 固定简化字段：`route`、`answer`、`sql`、`columns`、`rows`、`safety_status`、`blocked_reason`、`trace_id`；M5 后续只增量扩展，不改变含义
  - 模板 SQL 使用 MySQL / SQLite 都支持的基础语法；MySQL 仍是主路径，SQLite 仅服务自动化测试和 smoke
  - `eval/cases_plan.md` 同步落地 32 条问题和 YAML 字段草案，M6 只从该文件抽取 smoke 用例，不另起一套字段口径
- 参考资料：未查阅外部参考；M3 按阶段计划、M1 固定业务事实和 M2 FastAPI / SQLAlchemy 结构实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m3_query.py -p no:cacheprovider` 首次失败于缺 `engine.nl2sql.templates`、缺 `engine.sql_guard.guard`、`/api/query` 返回 404
  - M3 聚焦测试：`4 passed, 1 warning`（Starlette/httpx TestClient 依赖提示，不影响本模块）
  - 全量 pytest：`19 passed, 1 warning`（同上）
  - v0 smoke：5 条模板问题均返回 `status=200` + `safety=passed`，关键结果包括 `Aurora Noise Cancelling Headphones`、`Mobile App`、`gmv=160247.0`、`quality_issue`、`pending_high_priority_tickets=12`；`DROP TABLE orders` 返回 `safety=blocked`；摘要写入 `.agent_work/temp/v0-smoke.md`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - `git diff --check`：仅 README / app/main.py / app/api/__init__.py 的 CRLF 提示，无 whitespace error
- 遗留：
  - M4 接 schema loader、prompt、LLM SQL 生成、敏感字段策略和 RBAC；M3 的 `user_role` 目前仅在请求 Schema 中保留
  - RAG / hybrid 用例只在 `eval/cases_plan.md` 中规划，尚未实现检索链路

### M2 API 与后端工程基础（2026-07-18）

- 改动范围：`app/db/session.py`、`app/api/*`、`app/schemas/*`、`app/core/logging.py`、`app/core/exceptions.py`、`app/core/cache.py`、`app/main.py`、`tests/test_m2_api.py`、`README.md`（细节看 git）
- 关键决策：
  - DB session 走正式共享 SQLAlchemy engine + 请求级 `get_db()`，并启用 `pool_pre_ping=True`；不在接口里临时创建连接，避免后续 SQL Tool / API 出现多套数据库入口
  - 4 类资源只做 M2 计划要求的列表查询、分页和基础筛选；不扩展详情、新增、修改、删除，避免 M2 范围膨胀
  - `PageResponse[T]` 和 `ErrorResponse` 从 M2 固定响应形状，后续演示页、EvalOps 和 Agent 错误路径可以复用，不返回散装 dict
  - Redis 只落 `NullCache` wrapper 骨架，不接真实 Redis client，也不把缓存逻辑散进业务 API；这是计划允许的降级边界，后续可替换实现
  - 修复一次导入顺序坑：资源路由不能先从 `app.models` 聚合包导入模型，否则会和 `app.db.base` 的 metadata 注册形成循环导入；改为沿用 M1 的 `app.db.base` 导入路径
- 参考资料：未查阅外部参考；M2 API 形态按阶段计划和项目现有 FastAPI / SQLAlchemy 风格实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m2_api.py -p no:cacheprovider` 首次失败于 `ModuleNotFoundError: No module named 'app.db.session'`
  - M2 聚焦测试：`6 passed, 1 warning`（Starlette/httpx TestClient 依赖提示，不影响本模块）
  - 全量 pytest：`15 passed, 1 warning`（同上）
  - API smoke：4 类接口各 2 个筛选组合均返回 200 且有 `trace_id`；非法分页返回 422 + `validation_error`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - seed：users 50 / products 30 / channels 6 / orders 500 / refunds 80 / tickets 120 / knowledge_docs 8；4 个固定业务事实保持稳定
  - `git diff --check`：仅 README / app/main.py / docs 文件的 CRLF 提示，无 whitespace error
- 遗留：
  - M3 接 `/api/query`、模板 SQL、SQL Guard v0 和简化版 AgentResponse
  - Redis 仍是空实现骨架，不作为已完成缓存能力宣传

### M1 数据底座（2026-07-17）

- 改动范围：`app/models/*`、`app/db/base.py`、`alembic/*`、`scripts/seed_data.py`、`domain_pack/schema_desc/*`、`tests/test_m1_*`（细节看 git）
- 关键决策（git 里看不到的"为什么"）：
  - 状态 / 角色字段用字符串列 + 索引而非 DB 原生 Enum：取值后续可能扩展，合法值由seed / schema_desc / 后续 Pydantic 与 RBAC 层约束
  - seed 脚本不调用 `create_all()`：建表只走 Alembic；SQLite 仅测试用内存库
  - 4 个固定业务事实埋进确定性 seed（而非测试时临时拼数据）：供 M3 模板 SQL 和 M6 smoke 评测复用同一批稳定数据
  - `users.email` / `users.phone` 从模型、schema_desc 到 seed 全程标记敏感：给 M4 SQL Guard 敏感字段策略留入口
  - alembic.ini 用 ASCII 注释：避开 Windows 默认 GBK 读取配置时的 UnicodeDecodeError
- 参考资料：查了 `askdata_agent` 的 `askdata_pipeline/demo_data.py`（业务元数据与演示数据集中组织）和 `schema_indexing/objects.py`（字段描述含 description / aliases / semantic_role / samples / business_usage）；没照搬其 SQLite 建库脚本、Milvus 向量依赖和交易 / 利率业务域
- 验证快照：pytest 9 passed, 1 warning（httpx 依赖提示，无害）；alembic current = `20260717_0001 (head)`；alembic check 无新增操作；seed 行数 users 50 / products 30 / channels 6 / orders 500 / refunds 80 / tickets 120 / knowledge_docs 8（可复制命令 → README）
- 遗留：M2 建 `app/db/session.py`（`pool_pre_ping=True` 等 MySQL 连接参数）、4 类列表接口、请求日志中间件、统一异常响应

### M0 工程骨架与配置（2026-07-16）

- 改动范围：`pyproject.toml`、`app/main.py`、`app/core/config.py`、`.env.example`、`tests/test_config.py`、`tests/test_health.py`
- 关键决策：
  - 数据库主路径选 MySQL 开发库 `datapilot_dev` 而非 SQLite：贴近真实后端项目，后续讲表结构 / 索引 / 迁移 / 权限更自然
  - 连接串用 `mysql+pymysql://`：PyMySQL 作为 MySQL 驱动
  - `SettingsConfigDict(extra="ignore")`：`.env` 里多写暂未用到的字段不会导致启动失败
  - `.env.example` 只放占位和说明；真实密钥只在本地 `.env`，不入库
- 参考资料：未查阅外部参考（通用 FastAPI 骨架，无需借鉴项目结构）
- 验证快照：pytest 5 passed；`Settings()` 能读 `.env` 且 `DATABASE_URL` 指向 `datapilot_dev`；`pymysql` 可导入
- 遗留：已由 M1 完成（ORM、Alembic、seed）

## 补充记录（小修补，新的在上）

- 2026-07-20 M3 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 19 passed），报告 `accept-M3-20260720.md`
- 2026-07-19 dev-log 代码阅读路线版式调整：按用户确认，将 M0-M3 `### 代码阅读路线` 的顶部“按 X 顺序读”句式删除，改为编号项直接承载职责标题与文件路径（如 `**接口契约**：app/schemas/agent.py`），减少“先看/再看”冗余。验证：人工回读 M0-M3 阅读路线

- 2026-07-19 dev-log 代码阅读路线补强：按用户确认的标准版，为 `docs/dev-log.md` M0-M3 的「关键文件」后新增 `### 代码阅读路线`，覆盖阅读顺序、主角文件/函数、调用关系和数据流向；`finish-module` skill 暂未修改，待用户选择模板版本。验证：人工回读 M0-M3 阅读路线

- 2026-07-19 dev-log 前序章节与 finish-module 写作规则优化：为 `docs/dev-log.md` M0-M2 补充扫读重点加粗；在 `.claude/skills/finish-module/SKILL.md` 阶段 4 增加 dev-log 加粗写作要求，要求突出关键词、核心决策、类比锚点、量化成果和面试 talking point。验证：人工回读 M0-M3 与 skill 阶段 4

- 2026-07-19 M3 dev-log 可读性微调：按用户反馈为 `docs/dev-log.md` 的 M3 复盘补充重点加粗，突出模板 SQL、SQL Guard、AgentResponse、评测清单和验证结论；仅文档样式调整，未改代码。验证：人工回读 M3 小节

- 2026-07-19 dev-log.md 加粗优化：为"面试怎么讲"段落提取关键 talking point 加粗、Java→Python 类比标记加粗、关键数字锚点（X 个测试 / X 张表 / X 条 SQL 等）加粗、设计要点结论句补漏。原则：加粗服务于扫读，让新手不用逐字读就能定位到"这个概念对应 Java 的什么、面试能讲哪几个点、量化成果是什么"。

- 2026-07-19 全项目注释风格合规整改：按 CLAUDE.md「代码风格」扫描全部 36 个 .py 文件，修复合规项 47 处（A 英文→中文 docstring 14 / B 缺文件头 11 / C 缺函数 docstring 15 / D 注释简略 3 / E 空 __init__.py 4）。发现 agent 修改的两个常见问题：① docstring 可能被错放在 import 之后（Python 模块 docstring 应为首个语句，PEP 257）；② Unicode 弯引号 "" 会替代 """ 导致语法非法，prompt 应显式禁止。验证：20/20 文件 ast.parse 通过；pytest 5/5 passed
    - 2026-07-19 验收状态入「当前状态」：新增「上一模块验收」字段（现值 M2 已验收），防止未跑 accept-module 就开工下一模块。维护闭环：finish-module 收工置「Mx 未验收（待 accept-module）」→ accept-module 通过后改「已验收」（有 ❌ 记「验收未通过」）；CLAUDE.md「开发记录要求」新增任务开始核对规则（下一模块开发前上一模块未验收 → 先提醒用户）；accept-module 检查 3 把该字段纳入核对项。验证：rg「上一模块验收」命中 CLAUDE.md / AI_CONTEXT 当前状态 / 两个 skill 共 6 处预期位置

- 2026-07-19 Codex wrapper 残余口径修正（M3 前口径巡检收尾）：`.codex/skills/` 两个 wrapper 的 canonical 引用路径原为 `../../.claude/...`，自 wrapper 所在目录少跳一级、会解析到不存在的 `.codex/.claude/`，改为自项目根目录起算的 `.claude/skills/<skill>/SKILL.md`；description 同步 07-19「skill description 收敛」口径（accept-module 删流程摘要、finish-module 补「写复盘」触发词）。同轮巡检其余均干净：finish-module canonical 无硬编码 smoke 路径（验证步骤现读计划文件）、phase2-plan M2-M5 命令均指 `scripts/`、README 无 smoke 引用、全库旧路径仅本文件历史记录命中。验证：两个 canonical 路径 `test -f` 存在；废弃口径扫描（--hidden，覆盖 .codex）无命中 exit 1

- 2026-07-19 验收工作流优化（据 M2 验收复盘）：① accept-module 检查 3 改为 AI_CONTEXT 唯一权威口径（总览已无状态列）；② 检查 5 增加计数口径（docstring 或开头注释均算解释、pytest / 常量子类 / 纯字段模型豁免规则、≤10 文件必须全读列清单）；③ 检查 5 增加同模块复检的增量范围规则；④ 验收报告增加"落点两动作"（结论进补充记录、⚠️ 项登记已知的坑或下模块任务）；⑤ M2 smoke 脚本从 `.agent_work/temp/phase2/` 迁入 `scripts/smoke_m2_api.py`（★ 修正 `parents[3]`→`parents[1]` 并补中文注释），phase2-plan M2-M5 验证命令与 dev-log 引用同步改为 scripts/ 路径，CLAUDE.md「工作约定」明确 smoke 脚本落位并在 phase2-plan「单一事实源」登记，deprecated-terms 新增 temp 下 smoke .py 路径守卫正则；.gitattributes 换行统一经用户决定暂不做。验证：`python scripts/smoke_m2_api.py` 输出 9 行符合预期（8×200 + 1×422 validation_error）；废弃口径扫描含新守卫无命中（exit 1）；pytest 15 passed, 1 warning

- 2026-07-19 M2 代码注释补强：按 CLAUDE.md「代码风格」为 M2 的 7 个文件（core/logging、core/exceptions、core/cache、db/session、api/resources、schemas/resources、tests/test_m2_api）补充中文 docstring 和关键点注释（trace_id 透传与回传、三层异常兜底、Null Object 缓存骨架、分页稳定排序与 order_by(None) 计数、左闭右开时间范围、pytest 依赖覆盖），消除 accept-M2-recheck-20260719 检查 5 的 ⚠️；未改任何业务行为。验证：pytest 15 passed, 1 warning；git diff --check 仅 CRLF 提示

- 2026-07-19 skill description 收敛：finish-module / accept-module 的 description 删流程摘要、只留定位与触发词，避免与正文形成第二份口径；finish-module 触发词补「写复盘」。验证：会话内 skill 列表已刷新为新 description
- 2026-07-19 注释规则单一事实源收敛：CLAUDE.md「代码风格」定为注释规则唯一权威（补语言边界、分隔线规则及“目测即可、不进验收”说明）；finish-module / accept-module 改为引用不复述；accept-module 检查 5 更名「注释合规」、判定去 ORM 化并修 typo；deprecated-terms.txt 登记「注释合规抽查」。验证：rg 全库旧口径仅登记处命中
- 2026-07-18 模块工作流口径优化：phase2-plan 取消模块总览状态列，进度只看 AI_CONTEXT；各模块补“模块验证命令”；finish-module 明确 AI_CONTEXT 新的在上、dev-log 追加到末尾。验证：rg / diff check
- 2026-07-18 模块收工 workflow 固化：新增 `finish-module` skill（Claude canonical + Codex wrapper），把”补注释 + 跑验证 + 写 AI_CONTEXT + 写 dev-log”固定为模块完成后的收工整理；`accept-module` 增加注释合规轻量必检，并更新 AGENTS / CLAUDE / phase2-plan 的调用顺序。验证：rg / diff check
- 2026-07-18 M1 代码注释补强：按 AGENTS.md「代码风格」为 M1 模型、seed、Alembic env、M1 测试补充新手友好的中文注释和关键步骤说明；未改业务行为。验证：pytest 9 passed, 1 warning；alembic check 无新增操作；git diff --check 仅 Windows 换行提示
- 2026-07-18 完善 dev-log 学习复盘：按新版 AGENTS.md 要求，为 M0/M1 补充更清晰的故事体说明、关键文件速览和可复制验证命令。验证：rg / diff check
- 2026-07-17 日志分家（方案 A）：dev-log 改为学习复盘、本文件改为技术档案，删除与 CLAUDE.md / phase2-plan / README 重复的段落；同步改写 CLAUDE.md「开发记录要求」、phase2-plan 相关引用和 accept-module skill。验证：rg 扫描「当前状态速览」无活跃引用
- 2026-07-17 日志拆分 v1（已被上一条取代）：曾新增复制式 AI_CONTEXT.md，因重复定义问题重构
- 2026-07-17 Phase 2 验收口径收敛：M4 简单 SQL 正确性、YAML case 字段、验收记录落位（`eval/reports/phase2-v1-acceptance.md`）登记进 phase2-plan「单一事实源」。仅文档，未跑测试
- 2026-07-17 跨文档重复收敛：32 条用例构成唯一出处定为 phase2-plan M3；目录结构权威定为 CLAUDE.md；phase2-plan 规范复述改引用。仅文档，未跑测试
- 2026-07-17 文档口径审查：README 删 SQLite 主路径旧口径；库名统一 `datapilot_dev`（config 默认值 / .env.example / test 字面值三处）。pytest 5 passed。遗留低优先级待办：dev 依赖补 httpx、空包目录补 `__init__.py`、`.gitkeep` 入库、`redact_database_url`
  改 `rsplit`、LEARNING_ROADMAP 两处旧口径
- 2026-07-17 多工具协作口径校准：临时目录统一 `.agent_work/temp/`、Trace 归`eval/traces/`、Phase 2 smoke 定为 6 条。仅文档与目录占位，未跑测试
- 2026-07-17 架构底线与降级边界：phase2-plan 新增 P0（不可降级）/ P1（可简化）边界；简化版 AgentResponse 前置到 M3。仅文档，未跑测试
