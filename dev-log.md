# DataPilot Dev Log

记录每个阶段性里程碑的交付内容、技术决策、验证结果和面试讲法。这里不是流水账，而是后续 README、简历和面试复盘的原材料。

## 2026-07-16 / Phase 2 Day 1 - 工程骨架与配置基础

### 做了什么

- 建立 FastAPI 项目骨架：`app/`、`engine/`、`domain_pack/`、`eval/`、`demo/`、`scripts/`、`.codex/temp_work/`。
- 新增 `app/main.py`，提供 `/health` 健康检查。
- 新增 `app/core/config.py`，用 Pydantic Settings 从 `.env` 读取配置。
- 新增 `pyproject.toml`，声明 FastAPI、SQLAlchemy、Alembic、sqlglot、pandas、Streamlit、Altair、PyMySQL 等阶段二依赖。
- 新增 `.env.example`，保留真实 `.env` 在本地，示例文件只放占位说明。
- 新增配置测试和健康检查测试：`tests/test_config.py`、`tests/test_health.py`。

### 技术决策

- 数据库直接切到 MySQL 开发库 `datapilot_dev`，不再把 SQLite 作为主路径。这样 Day 2/Day 3 的 SQLAlchemy 模型和 Alembic migration 会更接近真实后端项目，也更适合面试讲工程落地。
- SQLAlchemy URL 使用 `mysql+pymysql://...`，因此项目依赖显式加入 `PyMySQL`。
- `SettingsConfigDict(extra="ignore")` 保留。因为本地 `.env` 会放多个模型供应商和 LangSmith 配置，当前阶段不一定全部使用，忽略额外字段能避免配置文件一扩展服务就启动失败。
- `.env.example` 只写占位和说明，不写真实密钥；真实账号密码只放 `.env`。

### 验证结果

- 已验证 `.env` 能被 `Settings()` 读取，`DATABASE_URL` 是 MySQL URL，且指向 `datapilot_dev`。
- 已验证 `pymysql` 可导入。
- 已运行测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider
```

结果：`4 passed`。当前仅有 FastAPI / Starlette TestClient 的 deprecation warning，不影响阶段二开发。

### 面试怎么讲

DataPilot 从一开始按真实后端服务搭骨架：FastAPI 做 API 层，Pydantic Settings 管理环境配置，SQLAlchemy + Alembic 负责后续数据模型和迁移。数据库选择直接使用 MySQL 开发库，而不是长期停留在 SQLite demo，这样后续权限、索引、迁移和数据生成都更贴近生产项目。配置层允许多模型供应商密钥共存，但只把当前代码需要的字段建模，避免 `.env` 扩展导致服务启动失败。

### 遗留问题 / 下一步

- Day 2 需要定义 7 张核心表的 SQLAlchemy ORM 模型。
- Day 3 需要接入 Alembic，并用 `datapilot_dev` 实际执行 migration。
- 后续需要在 `app/db/session.py` 中基于 `settings.database_url` 创建 SQLAlchemy engine，并为 MySQL 增加连接池参数。
