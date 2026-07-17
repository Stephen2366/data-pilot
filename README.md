# DataPilot

企业数据分析 Agent 系统——自然语言 → SQL/RAG → 可视化 + 分析报告。

🚧 阶段二进行中：M0 工程骨架已完成，当前推进 M1 数据底座

## 快速开始

### 环境

- Python：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe`
- 数据库：MySQL 开发库 `datapilot_dev`（SQLAlchemy + Alembic 管理建表和迁移；SQLite 仅用于测试兜底）

### 安装依赖

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pip install -e ".[dev]"
```

### 配置环境变量

```powershell
Copy-Item .env.example .env
```

### 启动 API

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m uvicorn app.main:app --reload
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回：

```json
{
  "status": "ok"
}
```

### 运行测试

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest
```

## 项目结构

```text
app/                    # FastAPI 应用层
  api/                  # REST API 路由
  core/                 # 配置、日志、异常处理
  db/                   # SQLAlchemy engine/session
  models/               # ORM 模型
  schemas/              # Pydantic 请求/响应模型
engine/                 # 通用 Agent 引擎
  nl2sql/               # 模板 SQL / NL2SQL
  sql_guard/            # SQL 安全检查
  tools/                # Agent tools
  trace/                # Trace 与成本延迟记录
domain_pack/            # 电商/SaaS 业务配置
  chart_templates/      # 图表模板
  kb_docs/              # 知识库文档
  schema_desc/          # 表结构与字段语义
  sql_examples/         # few-shot 与模板 SQL
eval/                   # EvalOps-lite
  cases/                # YAML 测试用例
  reports/              # 评测报告
demo/                   # Streamlit 演示页
scripts/                # 数据生成和维护脚本
tests/                  # 自动化测试
```
