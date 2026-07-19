# DataPilot 开发日志（学习复盘）

> 给"未来的我"读的：每个模块讲清楚做了什么、我该理解什么、面试怎么讲。当前进度看 `AI_CONTEXT.md`「当前状态」；完整技术档案看 `AI_CONTEXT.md` 对应模块，查 bug 找那边。

## ★ M0 工程骨架与配置（2026-07-16）

**简述：**把空仓库变成一个能启动、能跑测试的 FastAPI 项目——相当于盖房子前先打好地基、通好水电。

### 这次做了什么

DataPilot 最终要做"用自然语言问数据"的 Agent 系统，但第一天**不碰 AI**，先把**工程底子打牢**。就像做 **Java / SpringBoot** 项目前先建好启动类、配置文件和健康检查一样，这一步先让 Python 后端具备最基本的工程形态。

具体做法是：搭好 **FastAPI 服务**（把 Python 函数变成对外 HTTP 接口的 Web 框架），加一个 `/health` **健康检查接口**确认服务活着；用 **Pydantic Settings** 把 `.env` 里的配置（数据库地址、API Key 等）自动读成 Python 对象，避免代码里到处手写 `os.getenv()`；再配上**第一批自动化测试**。这样后面每加一个功能，都能随时确认"服务还能起、配置还能读、测试还能过"。

### 新概念

- **FastAPI**：Python 的 Web 框架，把函数变成 HTTP 接口。类比 SpringBoot 的 `@RestController`
- **Pydantic Settings**：把 `.env` 里的配置自动读成带类型检查的 Python 对象，避免代码里到处手写 `os.getenv()`

### 关键文件：

- `app/main.py`：FastAPI 应用入口，负责创建服务和注册 `/health`。
- `app/core/config.py`：配置入口，负责读取 `.env`。
- `pyproject.toml`：项目依赖清单，类似 Java 项目的 `pom.xml` / `build.gradle`。
- `tests/test_config.py`、`tests/test_health.py`：第一批自动化测试，负责守住配置和健康检查。

### 设计要点

- **健康检查不是摆设**：一个永远回答"我还活着"的接口，CI/CD、K8s 探针、测试脚本都用它确认服务启动成功——加新功能后先看健康检查，能快速判断是谁坏了
- **配置密钥分离**：真实密钥放本地 `.env`（不提交），仓库只放 `.env.example` 模板——门锁装好，钥匙不放门口。`.env` 里允许存在暂未启用的字段，但代码只建模当前真正使用的配置，避免配置膨胀

### 面试怎么讲

DataPilot 不是只写一个脚本 demo，而是从第一天按**真实后端服务**搭骨架：**FastAPI 负责 API 层**，**Pydantic Settings 负责配置管理**，**SQLAlchemy + Alembic** 负责后续数据模型和数据库迁移。数据库直接使用 **MySQL 开发库**，后面讲表设计、权限控制、索引和迁移时更贴近真实业务项目。配置层允许 `.env` 里存在暂时没用到的字段，但代码只建模当前真正使用的配置，既方便本地开发，也避免配置混乱。

### 验证与下一步

- 验证：**5 个测试全过**，`.env` 配置能被正确读取
- 下一步：M1 建数据底座（7 张表 + 迁移 + 模拟数据）

可复制验证命令：

```powershell
python -m pytest
```

## ★ M1 数据底座（2026-07-17）

**简述**：建好 7 张业务表、数据库迁移和确定性假数据——先把"仓库和货"备齐，之后 Agent 才有东西可查。

### 这次做了什么

要让 Agent 回答"上月退款率最高的商品是什么"，前提是数据库里真的有**订单、退款这些数据**。这一步相当于先给数据分析系统准备"业务仓库"：**表结构是货架**，**seed 数据是摆上去的货**，**固定业务事实是后面验货用的标准答案**。

这次用 **SQLAlchemy 定义了 7 张表**：用户、商品、渠道是"**维度**"（描述业务对象是谁），订单、退款、工单是"**事实**"（记录业务发生了什么），知识文档表给后面的 **RAG 检索**预留位置。建表不手写 SQL，而是通过 **Alembic 迁移管理**，改表历史全程可追溯。然后写了一个"**每次运行结果都一模一样**"的假数据脚本，还故意在数据里埋了 **4 个标准答案**（比如 2026 年 6 月退款率最高的商品是谁）——以后评测 Agent 时，就能自动判断它查得对不对。

### 新概念

- **SQLAlchemy**：Python 操作数据库的工具包，两层——**ORM**（类↔表，类比 JPA/Hibernate）和 **Core**（用 Python 表达式构建 SQL，防注入，类比 MyBatis）。项目里 `app/models/` 走 ORM，后面 `engine/nl2sql/` 动态拼 SQL 走 Core
- **Alembic**：数据库结构的版本控制（类比 Flyway/Liquibase）。改 Model → 自动生成迁移脚本 → `upgrade` 应用到库，可 `downgrade` 回滚，和 git 一样可追溯
- **维度表 / 事实表**：维度表回答"是谁 / 是什么"，事实表回答"发生了什么"——查询时先定位维度，再查事实，性能更好

### 关键文件：

- `app/models/`：7 张业务表的 ORM 模型，负责描述数据库长什么样。
- `app/db/base.py`：统一收集所有 ORM 表，让 Alembic 能看到完整表结构。
- `alembic/versions/20260717_0001_create_m1_business_tables.py`：第一版建表迁移，负责真正把表建到 MySQL。
- `scripts/seed_data.py`：确定性模拟数据脚本，负责写入 7 张表的数据和固定业务事实。
- `domain_pack/schema_desc/`：给后续 NL2SQL / SQL Guard 看的业务字段说明和敏感字段标记。

### 设计要点

- **seed 必须确定性**：随机假数据会让"标准答案"每天变，评测无法自动化——固定随机种子，每次生成一模一样的数据，4 个业务事实才敢拍胸脯说"这就是正确答案"
- **敏感字段从 M1 就标**：用户邮箱、手机号在建表阶段就标记为敏感——安全不是事后补文档，而是进入 schema → SQL Guard → RBAC 全链路，后面做拦截时有据可查

### 面试怎么讲

DataPilot 的数据底座不是随手建几张 demo 表，而是按真实分析系统拆成**维表和事实表**：用户、商品、渠道是维度，订单、退款、工单是运营事实，知识文档给后续 **RAG 链路**预留入口。迁移全部通过 **Alembic 管理**，seed 数据里还专门设计了**固定业务事实**，后续 **NL2SQL 和评测**可以验证"查出来的答案是否稳定正确"。**敏感字段从 M1 就标出来**，说明安全策略不是最后补文档，而是会进入 schema、RBAC 和 SQL Guard 的主链路。

### 验证与下一步

- 验证：**9 个测试全过**，MySQL 在线迁移和 seed 数据都成功，**4 个标准答案**可查
- 下一步：M2 做 API 层（数据库会话、分页查询接口、请求日志、统一异常）

可复制验证命令：

```powershell
python -m pytest -p no:cacheprovider
python -m alembic upgrade head
python -m scripts.seed_data --reset
python -m alembic current
python -m alembic check
```

## ★ M2 API 与后端工程基础（2026-07-18）

**简述**：给 M1 的数据底座装上稳定 API 出入口——像给仓库开了带登记簿的取货窗口，后续 Agent 和演示页都从这里拿数据。

### 这次做了什么

M1 已经把 **7 张表和确定性数据**准备好了，但后续 Agent、评测脚本、Streamlit 页面不能直接到处打开数据库连接。M2 做的是后端工程基础：**统一数据库会话、统一分页列表接口、统一请求日志和统一错误响应**。

这次新增了 `app/db/session.py`，让每个请求通过 `get_db()` 拿一个 **SQLAlchemy Session**，用完自动关闭；`pool_pre_ping=True` 负责在 MySQL 连接交给业务代码前先探活。然后新增 **4 个列表接口**：商品、订单、退款、工单，每个接口都支持分页和本模块计划里的基础筛选。接口返回统一 `PageResponse`，错误返回统一 `ErrorResponse`，并且每次请求都有 `trace_id`，日志里能看到 method、path、status、latency_ms 和 trace_id。

### 新概念

- **请求级 Session**：每个 HTTP 请求拿一个数据库会话，请求结束就关闭。类比 SpringBoot 里一次请求进 Service / Repository 使用同一个事务上下文，不在 Controller 里到处手写连接。
- **分页响应**：列表接口不只返回数据，还返回 `total / page / page_size`。前端或评测脚本才知道总共有多少条、当前是哪一页。
- **trace_id**：一次请求的追踪编号。出错时用户拿到 trace_id，服务端也用同一个 trace_id 查日志，排查链路会快很多。

### 关键文件：

- `app/db/session.py`：数据库 engine 和请求级 Session 依赖。
- `app/api/resources.py`：4 类资源列表接口。
- `app/schemas/common.py`、`app/schemas/resources.py`：分页响应、错误响应和资源读取模型。
- `app/core/logging.py`、`app/core/exceptions.py`：请求日志中间件和全局异常处理。
- `app/core/cache.py`：Redis wrapper 骨架，目前是 `NullCache`，不宣传为真实缓存能力。

### 设计要点

- **DB 入口只保留一套**：API 不自己创建连接，而是统一依赖 `get_db()`。后续 SQL Tool 和 `/api/query` 也可以沿用这套入口，避免多个模块各连各的库。
- **响应结构提前稳定**：`PageResponse` 和 `ErrorResponse` 从 M2 固定下来，后面 EvalOps、演示页、Agent 错误路径都能复用。
- **Redis 不拖主线**：M2 只放 `NullCache` 骨架，不接真实 Redis。这样保留未来替换点，又不把缓存环境问题带进 v0 主链路。
- **导入顺序要小心**：这次全量测试暴露过一次循环导入，原因是资源路由先从 `app.models` 聚合包拿模型，和 `app.db.base` 的 metadata 注册顺序撞上；最后沿用 M1 的 `app.db.base` 导入路径解决。

### 面试怎么讲

M2 体现的是**后端工程能力**，不只是“写几个 GET 接口”。我把数据库访问统一收口到**请求级 Session**，MySQL engine 开启**连接探活**；列表接口统一**分页、筛选和响应结构**；异常统一成 `code / message / trace_id / details`，请求日志统一记录关键字段。这样后续做 Agent 查询、评测和演示页时，不需要重新设计基础工程能力，只要复用这套 **API 和响应契约**。

### 验证与下一步

- 验证：**15 个测试全过**；**4 类接口各 2 个筛选组合** smoke 成功；非法分页返回统一错误；Alembic check/current 和 seed 都通过
- warning：Starlette TestClient 提示 httpx 依赖迁移，不影响 M2 行为
- 下一步：M3 做 v0 模板 SQL 闭环，新增 `/api/query`、SQL Guard v0 和简化版 AgentResponse

可复制验证命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_m2_api.py
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset
```

## ★ M3 v0 模板 SQL 闭环（2026-07-19）

**简述**：让 DataPilot 第一次能“听懂问题并查数据库”——先不用 LLM，靠 5 条稳定模板 SQL 跑通自然语言到表格答案的闭环。

### 这次做了什么

M1 准备了数据，M2 准备了 API 出入口。M3 做的是 DataPilot v0 的核心体验：用户问一句业务问题，系统**匹配一条预设 SQL**，先过**安全检查**，再执行查询，最后返回统一的 **AgentResponse**。

这次**没有提前接 LLM**。原因很简单：如果一开始就让模型自由生成 SQL，问题会同时变成“**生成准不准、SQL 安不安全、接口结构稳不稳、数据能不能查**”四件事混在一起。M3 先把**可控链路**跑通：5 个高价值问题覆盖退款率、渠道订单量、GMV、退款原因和工单优先级；**SQL Guard** 用 sqlglot 只允许单条 `SELECT`；`/api/query` 返回 `route / answer / sql / columns / rows / safety_status / blocked_reason / trace_id`。这样 M4 再接 LLM 时，只需要替换“SQL 从哪里来”，不用重做**执行、安全和响应结构**。

同时，M3 还写了 `eval/cases_plan.md`，把阶段二 **32 条评测问题**先固定下来，包括简单 SQL、聚合、多表、RAG、混合和安全攻击，并同步定义后续 **YAML 字段草案**。它会成为 M6 smoke 用例的题库来源。

### 新概念

- **模板 SQL**：把常见自然语言问题映射到预先写好的 SQL。它不像 LLM 那样灵活，但稳定、可测、可解释，非常适合 v0 先打通链路。
- **SQL Guard**：SQL 执行前的安全门。M3 使用 sqlglot 把 SQL 解析成 AST，再判断它是不是单条 `SELECT`。这比只靠字符串里有没有 `drop` 更可靠。
- **AgentResponse**：Agent **对外输出**的结构化合同。前端、评测脚本、演示页都按这份合同读取答案、SQL、表格、安全状态和 trace_id。
- **few-shot 示例**：M3 的模板 SQL 同步沉淀到 `domain_pack/sql_examples/basic.yaml`，后续 M4 给 LLM 看这些“标准问法 + 标准 SQL”，帮助它按项目口径生成 SQL。

### 关键文件

- `engine/nl2sql/templates.py`：5 条 v0 模板 SQL 和自然语言关键词匹配逻辑。
- `engine/sql_guard/guard.py`：sqlglot 只读检查，只允许单条 `SELECT`。
- `app/schemas/agent.py`：M3 简化版 `QueryRequest` 和 `AgentResponse`。
- `app/api/query.py`：`POST /api/query` 主链路：模板匹配 → Guard → 执行 SQL → 组装响应。
- `domain_pack/metrics.yaml`：退款率、GMV、订单量、退款量、待处理高优先级工单数的业务口径。
- `domain_pack/sql_examples/basic.yaml`：模板 SQL 沉淀为 M4 few-shot 示例。
- `eval/cases_plan.md`：32 条评测问题和 YAML 字段草案。
- `scripts/smoke_v0.py`：M3 smoke 脚本，输出摘要到 `.agent_work/temp/v0-smoke.md`。

### 设计要点

- **先稳闭环，再上 LLM**：M3 不做自由生成，避免把生成质量和工程链路混在一起排查。
- **安全入口前置**：模板 SQL 也必须过 SQL Guard，不因为“SQL 是我们写的”就绕过安全层。后续 LLM SQL 能复用同一个入口。
- **接口结构不推倒重来**：M3 先定简化版 `AgentResponse`，M5 只加字段，不改已有字段含义。
- **业务口径放 domain_pack**：GMV、退款率这些电商含义不写死在 `engine/` 里，后续换行业时优先替换 domain pack。
- **边界清楚**：M3 只做模板 SQL 和只读检查；敏感字段、RBAC、LLM prompt、RAG / hybrid 执行链路留给 M4 以后。

### 面试怎么讲

M3 可以讲成“先做一个**可控的 Text-to-SQL v0**”。我没有一上来接 LLM，而是用**模板 SQL 建立稳定基线**：自然语言问题命中模板，SQL 进入 Guard，只允许只读查询，然后通过统一数据库 Session 执行，最后返回结构化 AgentResponse。这样做的好处是**可测试、可验收**，也为后续 LLM 接入留好工程接口。

安全上，我没有只靠 **prompt** 或**字符串过滤**，而是用 **sqlglot 解析 SQL AST**，拦截 **DDL / DML**。虽然 M3 还没做敏感字段和角色权限，但 **SQL Guard 的入口已经固定**，M4 可以在同一个层继续加 RBAC 和字段策略。

### 验证与下一步

- 验证：**19 个测试全过**；v0 smoke 中 **5 条模板查询**返回 `safety=passed`，危险 `DROP TABLE orders` 返回 `safety=blocked`；Alembic check/current 正常。
- warning：Starlette TestClient 提示 httpx 依赖迁移，不影响 M3 行为。
- 下一步：M4 做 schema loader、prompt、LLM SQL 生成、敏感字段策略和 RBAC。

可复制验证命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_v0.py
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check
$env:PYTHONDONTWRITEBYTECODE='1'; D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current
```
