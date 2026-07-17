# DataPilot AI Context（技术档案）

> 续接任务、查 bug 读这个。只记 git 和代码里查不到的信息：为什么这么做、
> 验证过什么、有什么坑。硬约束见 CLAUDE.md（自动加载），任务见 phase2-plan.md，
> 均不在此重复。用户学习复盘见 dev-log.md。
> 「当前状态」「已知的坑」保持最新；「模块技术档案」「补充记录」只追加不改写。

## 当前状态（唯一权威出处）

- 当前模块：Phase 2 M2 API 与后端工程基础，待开始（任务详情 → phase2-plan.md M2 小节）
- 阻塞项：无
- 更新时间：2026-07-17

## 已知的坑（活跃列表，过期即删）

- DB comment 在 PowerShell 离线 SQL 输出中乱码；在线迁移和建表正常，无害。如需导出 SQL
  文件，再统一处理输出编码或将 DB comment 改为 ASCII（M1）
- 工作树可能有用户或其他工具留下的未提交改动；动文件前先 `git status --short`，
  不要回滚非本次任务的改动

## 模块技术档案（新的在上）

### M1 数据底座（2026-07-17）

- 改动范围：`app/models/*`、`app/db/base.py`、`alembic/*`、`scripts/seed_data.py`、
  `domain_pack/schema_desc/*`、`tests/test_m1_*`（细节看 git）
- 关键决策（git 里看不到的"为什么"）：
  - 状态 / 角色字段用字符串列 + 索引而非 DB 原生 Enum：取值后续可能扩展，合法值由
    seed / schema_desc / 后续 Pydantic 与 RBAC 层约束
  - seed 脚本不调用 `create_all()`：建表只走 Alembic；SQLite 仅测试用内存库
  - 4 个固定业务事实埋进确定性 seed（而非测试时临时拼数据）：供 M3 模板 SQL 和
    M6 smoke 评测复用同一批稳定数据
  - `users.email` / `users.phone` 从模型、schema_desc 到 seed 全程标记敏感：
    给 M4 SQL Guard 敏感字段策略留入口
  - alembic.ini 用 ASCII 注释：避开 Windows 默认 GBK 读取配置时的 UnicodeDecodeError
- 参考资料：查了 `askdata_agent` 的 `askdata_pipeline/demo_data.py`（业务元数据与演示
  数据集中组织）和 `schema_indexing/objects.py`（字段描述含 description / aliases /
  semantic_role / samples / business_usage）；没照搬其 SQLite 建库脚本、Milvus 向量
  依赖和交易 / 利率业务域
- 验证快照：pytest 9 passed, 1 warning（httpx 依赖提示，无害）；alembic current =
  `20260717_0001 (head)`；alembic check 无新增操作；seed 行数 users 50 / products 30 /
  channels 6 / orders 500 / refunds 80 / tickets 120 / knowledge_docs 8
  （可复制命令 → README）
- 遗留：M2 建 `app/db/session.py`（`pool_pre_ping=True` 等 MySQL 连接参数）、
  4 类列表接口、请求日志中间件、统一异常响应

### M0 工程骨架与配置（2026-07-16）

- 改动范围：`pyproject.toml`、`app/main.py`、`app/core/config.py`、`.env.example`、
  `tests/test_config.py`、`tests/test_health.py`
- 关键决策：
  - 数据库主路径选 MySQL 开发库 `datapilot_dev` 而非 SQLite：贴近真实后端项目，
    后续讲表结构 / 索引 / 迁移 / 权限更自然
  - 连接串用 `mysql+pymysql://`：PyMySQL 作为 MySQL 驱动
  - `SettingsConfigDict(extra="ignore")`：`.env` 里多写暂未用到的字段不会导致启动失败
  - `.env.example` 只放占位和说明；真实密钥只在本地 `.env`，不入库
- 参考资料：未查阅外部参考（通用 FastAPI 骨架，无需借鉴项目结构）
- 验证快照：pytest 5 passed；`Settings()` 能读 `.env` 且 `DATABASE_URL` 指向
  `datapilot_dev`；`pymysql` 可导入
- 遗留：已由 M1 完成（ORM、Alembic、seed）

## 补充记录（小修补，新的在上，每条 1-3 行）

- 2026-07-17 日志分家（方案 A）：dev-log 改为学习复盘、本文件改为技术档案，删除与
  CLAUDE.md / phase2-plan / README 重复的段落；同步改写 CLAUDE.md「开发记录要求」、
  phase2-plan 相关引用和 accept-module skill。验证：rg 扫描「当前状态速览」无活跃引用
- 2026-07-17 日志拆分 v1（已被上一条取代）：曾新增复制式 AI_CONTEXT.md，因重复定义问题重构
- 2026-07-17 Phase 2 验收口径收敛：M4 简单 SQL 正确性、YAML case 字段、验收记录落位
  （`eval/reports/phase2-v1-acceptance.md`）登记进 phase2-plan「单一事实源」。仅文档，未跑测试
- 2026-07-17 跨文档重复收敛：32 条用例构成唯一出处定为 phase2-plan M3；目录结构权威
  定为 CLAUDE.md；phase2-plan 规范复述改引用。仅文档，未跑测试
- 2026-07-17 文档口径审查：README 删 SQLite 主路径旧口径；库名统一 `datapilot_dev`
  （config 默认值 / .env.example / test 字面值三处）。pytest 5 passed。遗留低优先级待办：
  dev 依赖补 httpx、空包目录补 `__init__.py`、`.gitkeep` 入库、`redact_database_url`
  改 `rsplit`、LEARNING_ROADMAP 两处旧口径
- 2026-07-17 多工具协作口径校准：临时目录统一 `.agent_work/temp/`、Trace 归
  `eval/traces/`、Phase 2 smoke 定为 6 条。仅文档与目录占位，未跑测试
- 2026-07-17 架构底线与降级边界：phase2-plan 新增 P0（不可降级）/ P1（可简化）边界；
  简化版 AgentResponse 前置到 M3。仅文档，未跑测试
