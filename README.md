# DataPilot

企业数据分析 Agent 系统——自然语言 → SQL/RAG → 可视化 + 分析报告。

🚧 阶段二进行中：M4 NL2SQL 最小链路与安全已完成，下一步推进 M5 AgentResponse 扩展、Trace、Tool 与图表

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

M2 已提供 4 类基础列表接口，供后续 Agent、评测和演示页读取业务数据：

| 接口 | 主要筛选条件 |
|---|---|
| `GET /api/products` | `category`、`status`、`page`、`page_size` |
| `GET /api/orders` | `paid_from`、`paid_to`、`channel_id`、`order_status`、`page`、`page_size` |
| `GET /api/refunds` | `requested_from`、`requested_to`、`refund_status`、`refund_reason`、`page`、`page_size` |
| `GET /api/tickets` | `status`、`priority`、`ticket_type`、`page`、`page_size` |

分页响应统一为：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "trace_id": "..."
}
```

异常响应统一为：

```json
{
  "code": "validation_error",
  "message": "Request validation failed.",
  "trace_id": "...",
  "details": []
}
```

每次请求都会生成或透传 `X-Trace-Id`，服务端日志记录 `method / path / status / latency_ms / trace_id`。
Redis 在 M2 只保留 `NullCache` wrapper 骨架，暂未接入真实缓存能力。

### v0 模板 SQL 查询

M3 提供 `POST /api/query`：自然语言问题先匹配白名单模板 SQL，再经过 sqlglot SQL Guard
只读检查，最后执行数据库查询并返回简化版 AgentResponse。M4 之后仍然保持“模板优先”，
这些高价值问题不会被 LLM 波动影响。

请求示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/query `
  -ContentType 'application/json' `
  -Body '{"question":"2026年6月退款率最高的商品是什么？","user_role":"ops"}'
```

当前 5 个模板问题：

| 问题 | 关键结果 |
|---|---|
| `2026年6月退款率最高的商品是什么？` | `Aurora Noise Cancelling Headphones` |
| `各渠道订单量是多少？` | 返回各渠道 `order_count` |
| `2026年6月本月GMV是多少？` | 返回 `gmv` |
| `Top退款原因是什么？` | `quality_issue` |
| `待处理高优先级工单有多少？` | `12` |

简化版 AgentResponse：

```json
{
  "route": "sql",
  "answer": "2026-06 退款率最高商品：product_name=Aurora Noise Cancelling Headphones...",
  "sql": "SELECT ...",
  "columns": ["product_name", "refund_count", "order_count", "refund_rate"],
  "rows": [],
  "safety_status": "passed",
  "blocked_reason": null,
  "trace_id": "..."
}
```

危险 DDL / DML 会被结构化拦截：

```json
{
  "route": "sql",
  "answer": "SQL Guard 已拦截该请求。",
  "sql": "DROP TABLE orders",
  "columns": [],
  "rows": [],
  "safety_status": "blocked",
  "blocked_reason": "只允许 SELECT 只读查询...",
  "trace_id": "..."
}
```

v0 smoke：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_v0.py
```

输出摘要会写入 `.agent_work/temp/v0-smoke.md`。

### v1 NL2SQL 最小链路与安全

M4 在模板未命中时接入 DeepSeek NL2SQL：`schema_desc`、`metrics.yaml` 和 M3 模板 SQL
few-shot 会被组装进 prompt，模型输出 SQL 后仍必须经过增强 SQL Guard：

- 只允许单条 `SELECT`。
- 拦截 `DROP / DELETE / UPDATE / INSERT / ALTER / TRUNCATE`。
- 拦截 `users.email`、`users.phone` 等敏感字段，除 `admin` 外不可访问。
- 按角色做表级 allowlist：`customer_service` 当前只允许 `tickets` 和 `knowledge_docs`。

LLM 配置示例：

```powershell
$env:LLM_PROVIDER='deepseek'
$env:LLM_MODEL='deepseek-chat'
$env:DEEPSEEK_API_KEY='<your_key>'
$env:DEEPSEEK_BASE_URL='https://api.deepseek.com'
```

M4 smoke：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_m4_nl2sql.py
```

脚本会为 6 条 simple SQL 生成 prompt 快照到 `.agent_work/temp/prompt-snapshots.md`，
并把实际执行摘要写入 `.agent_work/temp/m4-smoke.md`。

### 运行测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider
```

### 数据库迁移与 Seed

建表主路径使用 Alembic，目标库是 MySQL 开发库 `datapilot_dev`：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic upgrade head
```

写入确定性模拟数据：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset
```

M1 seed 固定写入以下数据量：用户 50、商品 30、渠道 6、订单 500、退款 80、工单 120、知识文档 8。

固定业务事实锚点：

- 2026-06 退款率最高商品：`Aurora Noise Cancelling Headphones`
- 2026-06 GMV 最高渠道：`Mobile App`
- 全量退款 Top 原因：`quality_issue`
- 待处理高优先级工单数量：`12`

## M1 ER 图草稿

```mermaid
erDiagram
  users ||--o{ orders : places
  users ||--o{ refunds : requests
  users ||--o{ tickets : opens
  users ||--o{ tickets : assigned_to
  products ||--o{ orders : sold_as
  products ||--o{ refunds : refunded_as
  channels ||--o{ orders : receives
  orders ||--o{ refunds : may_have
  orders ||--o{ tickets : may_have

  users {
    int id PK
    string user_name
    string role
    string email "sensitive"
    string phone "sensitive"
    string status
    datetime created_at
    datetime updated_at
  }

  products {
    int id PK
    string sku
    string product_name
    string category
    string status
    decimal price
    datetime launched_at
  }

  channels {
    int id PK
    string channel_code
    string channel_name
    string channel_type
    string status
  }

  orders {
    int id PK
    string order_no
    int user_id FK
    int product_id FK
    int channel_id FK
    string order_status
    decimal order_amount
    int quantity
    datetime paid_at
  }

  refunds {
    int id PK
    string refund_no
    int order_id FK
    int user_id FK
    int product_id FK
    string refund_status
    string refund_reason
    decimal refund_amount
    datetime requested_at
    datetime processed_at
  }

  tickets {
    int id PK
    string ticket_no
    int user_id FK
    int order_id FK
    int assigned_user_id FK
    string ticket_type
    string priority
    string status
  }

  knowledge_docs {
    int id PK
    string doc_key
    string title
    string doc_type
    string audience_role
    string status
  }
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
  metrics.yaml          # KPI 口径
  schema_desc/          # 表结构与字段语义
  sql_examples/         # few-shot 与模板 SQL
eval/                   # EvalOps-lite
  cases/                # YAML 测试用例
  cases_plan.md         # 32 条评测问题清单和 YAML 字段草案
  reports/              # 评测报告
demo/                   # Streamlit 演示页
scripts/                # 数据生成和维护脚本
tests/                  # 自动化测试
```
