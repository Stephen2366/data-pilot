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

### 代码阅读路线

1. **应用入口**：`app/main.py`
   理解 FastAPI 应用是怎么被创建出来的。主角是 `create_app()`：它负责组装服务、注册 `/health`，也是后续所有路由挂载的入口。

2. **配置对象**：`app/core/config.py`
   理解 `.env` 配置如何变成 Python 对象。重点看 `Settings` 和 `get_settings()`，它们决定后续数据库、LLM、环境变量从哪里读。

3. **健康检查契约**：`tests/test_health.py`
   反过来理解服务最小可用标准：`/health` 必须返回 `{"status": "ok"}`。

4. **配置测试契约**：`tests/test_config.py`
   看测试如何守住配置默认值、`.env` 读取和敏感信息不外泄。

一次启动的调用关系：

`uvicorn app.main:app`
→ `create_app()`
→ `get_settings()`
→ 注册 `/health`
→ 测试用 `TestClient` 请求接口

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

### 代码阅读路线

1. **模型定义**：`app/models/`
   重点不要逐字段背表，而是先看 7 张表的角色：`User/Product/Channel` 是维表，`Order/Refund/Ticket` 是事实表，`KnowledgeDoc` 给后续 RAG 预留。每个模型里的主角是类本身和外键关系字段。

2. **metadata 汇总**：`app/db/base.py`
   理解为什么 Alembic 能“看见”所有模型。这个文件的主角是 `Base` 和模型导入：它把分散的 ORM 类汇总成一份 metadata。

3. **migration 建表**：`alembic/versions/20260717_0001_create_m1_business_tables.py`
   把它当成“数据库真实建表脚本”读。重点看 `upgrade()` 里创建了哪些表、索引和外键；`downgrade()` 则是回滚顺序。

4. **seed 造数与事实校验**：`scripts/seed_data.py`
   主角是 `seed_database()`：它按父表到子表的顺序写入数据。再看 `verify_business_facts()`，理解 4 个标准答案是怎么被 SQL 查出来的。

5. **业务语义说明**：`domain_pack/schema_desc/`
   这里不是给数据库执行的，而是给后续 NL2SQL / SQL Guard 理解业务语义的。重点看字段说明和敏感字段标记。

一次 seed 的数据流向：

`seed_database()`
→ `_build_users/products/channels/docs()`
→ `_build_orders()`
→ `_build_refunds()` / `_build_tickets()`
→ `verify_business_facts()`
→ 输出固定标准答案

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

### 代码阅读路线

1. **数据库入口**：`app/db/session.py`
   主角是 `build_engine()` 和 `get_db()`。前者创建共享 SQLAlchemy engine，后者把每次请求需要的 Session 借出去、用完再关闭。

2. **响应 Schema**：`app/schemas/common.py` 和 `app/schemas/resources.py`
   先理解接口返回什么形状。`PageResponse` 和 `ErrorResponse` 是 M2 的核心合同，资源读取模型则规定列表里每个 item 的字段。

3. **路由实现**：`app/api/resources.py`
   主角是 `_paginate()` 和 4 个列表函数：`list_products()`、`list_orders()`、`list_refunds()`、`list_tickets()`。读的时候重点看筛选条件怎么转成 SQLAlchemy `where()`，分页怎么统一收口。

4. **日志与异常**：`app/core/logging.py` 和 `app/core/exceptions.py`
   理解一次请求从进入到返回，中间如何生成 `trace_id`、记录日志，以及异常如何变成统一 JSON。

5. **测试反推契约**：`tests/test_m2_api.py`
   测试是 M2 的行为说明书：它告诉你哪些筛选组合必须可用，非法分页必须返回什么结构。

一次列表查询的调用链：

`GET /api/orders`
→ 日志中间件生成 `trace_id`
→ `get_db()` 提供 Session
→ `list_orders()` 拼筛选条件
→ `_paginate()` 统一计数和分页
→ `PageResponse`

一次非法请求的调用链：

`GET /api/products?page=0`
→ FastAPI 参数校验失败
→ 全局异常处理器接住
→ `ErrorResponse(code="validation_error")`

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

### 代码阅读路线

1. **接口契约**：`app/schemas/agent.py`
   理解 `/api/query` 的输入输出合同。主角是 `QueryRequest` 和 `AgentResponse`：前者规定用户怎么问，后者规定系统必须怎么答。

2. **SQL 从哪来**：`engine/nl2sql/templates.py`
   理解 M3 暂时不接 LLM，而是通过 `match_template()` 把自然语言问题匹配到 5 条白名单 SQL。主角是 `SQLTemplate`、`TEMPLATES` 和 `match_template()`。

3. **安全检查**：`engine/sql_guard/guard.py`
   理解 SQL 不是直接执行，而是先经过 `validate_readonly_sql()`，只允许单条 `SELECT`。主角是 `GuardResult` 和 `validate_readonly_sql()`。

4. **API 串起来**：`app/api/query.py`
   这是 M3 的主角文件。`query()` 把前面几步串成完整链路：问题 → 模板匹配 → SQL Guard → 执行 SQL → 组装 AgentResponse。辅助函数 `_blocked_response()`、`_build_answer()`、`_row_to_dict()` 分别负责拦截响应、最小答案和结果序列化。

5. **测试验证**：`tests/test_m3_query.py` 和 `scripts/smoke_v0.py`
   前者守住自动化测试契约，后者给人工验收看真实输出。读测试时重点看：哪些问题必须命中模板，哪些危险 SQL 必须被拦截。

一次正常查询的调用链：

`POST /api/query`
→ `QueryRequest`
→ `match_template(question)`
→ `validate_readonly_sql(sql)`
→ `db.execute(text(sql), parameters)`
→ `columns / rows`
→ `AgentResponse`

一次危险 SQL 的调用链：

`POST /api/query`
→ 未命中模板
→ `validate_readonly_sql(question)`
→ `safety_status=blocked`
→ 返回结构化拦截响应

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

## ★ M4 NL2SQL 最小链路与安全（2026-07-20）

**简述**：把 SQL 来源从固定模板扩展到 **DeepSeek LLM 生成**，但数据库执行前仍然必须经过同一个安全闸门。

### 这次做了什么

M3 已经跑通了 **模板 SQL 闭环**：自然语言问题命中白名单模板，SQL 过 Guard，再执行数据库查询。M4 往前走了一步：当问题没有命中模板时，系统会读取 `domain_pack/` 里的表结构、字段敏感标记、KPI 口径和 M3 few-shot 示例，构造 **NL2SQL prompt**，调用 **DeepSeek** 生成 SQL。

关键点是：M4 没有把“模型生成”当成安全保证。LLM 生成的 SQL 和模板 SQL 一样，都要进入增强版 **SQL Guard policy**：先用 sqlglot 确认是单条 `SELECT`，再提取访问的表和列，然后按角色矩阵拦截敏感字段和越权表访问。这样 SQL 从哪里来可以变化，但**执行前的安全入口不变**。

这次还补了 M4 smoke：6 条 simple SQL 真实调用 DeepSeek，其中 **5 条生成并执行正确**，满足 M4 口径；剩下一条待处理工单查询返回了 pending 数据，但模型没有把 `status` 放进 SELECT，记录为后续提示词和 EvalOps 优化素材。

### 新概念

- **Schema Loader**：把 markdown / YAML 里的业务知识加载成程序里的结构化对象。类比 SpringBoot 启动时读取配置文件，只不过这里读的是“表、字段、敏感级别、指标口径”。
- **Prompt Builder**：把可用表、字段说明、业务指标、few-shot 示例和用户问题拼成模型能理解的任务说明。它负责提高 SQL 生成质量，但不负责最终安全。
- **LLM Provider Adapter**：把 DeepSeek 的 HTTP 调用包成一个小客户端。M4 只接一个实际可用 provider，不提前做复杂多厂商抽象。
- **RBAC allowlist**：角色权限白名单。`admin` 可以看全量；`ops` 不能看敏感字段；`customer_service` 只看工单和政策；`demo_user` 只看脱敏样例表。
- **字段级安全策略**：不只判断能不能访问表，还判断 SQL 是否碰到 `users.email`、`users.phone` 这类敏感字段。`SELECT * FROM users` 也会被展开检查。

### 关键文件

- `engine/nl2sql/schema_loader.py`：读取 `domain_pack/schema_desc`、`metrics.yaml` 和 few-shot 示例。
- `engine/nl2sql/prompt.py`：构造 NL2SQL prompt。
- `engine/nl2sql/generator.py`：DeepSeek 调用、模型输出解析和 `GeneratedSQL`。
- `engine/sql_guard/rbac.py`：角色权限矩阵。
- `engine/sql_guard/policy.py`：只读检查、表级 RBAC、敏感字段拦截。
- `app/api/query.py`：模板优先、LLM 兜底、policy 校验、SQL 执行和 AgentResponse 返回。
- `scripts/smoke_m4_nl2sql.py`：M4 smoke 和 prompt 快照生成。
- `tests/test_m4_nl2sql.py`：M4 行为契约测试。

### 代码阅读路线

1. **领域知识入口**：`engine/nl2sql/schema_loader.py`
   先看 `load_domain_schema()`。它把表结构 markdown、KPI YAML 和 M3 SQL 示例合成 `DomainSchema`，后面的 prompt 和 policy 都依赖它。

2. **模型看到什么**：`engine/nl2sql/prompt.py`
   主角是 `build_sql_prompt()`。读的时候重点看 prompt 里如何写清楚单条 SELECT、敏感字段、可用表、指标口径和 few-shot。

3. **SQL 如何生成**：`engine/nl2sql/generator.py`
   主角是 `DeepSeekChatClient`、`extract_generated_sql()` 和 `generate_sql()`。重点理解：真实网络调用集中在一个地方，JSON / fenced SQL 两种输出都能解析，失败会变成可诊断错误。

4. **权限如何拦截**：`engine/sql_guard/rbac.py` 和 `engine/sql_guard/policy.py`
   先看 `ROLE_POLICIES`，再看 `validate_sql_policy()`。它先复用 M3 的只读检查，再从 AST 里提取表和字段，判断角色是否允许访问。

5. **API 如何串起来**：`app/api/query.py`
   读 `query()` 和 `_resolve_sql()`。完整链路是：先 `match_template()`，没命中才 `generate_sql()`，拿到 SQL 后统一 `validate_sql_policy()`，最后执行并返回 `AgentResponse`。

一次 LLM 查询的数据流向：

`POST /api/query`
→ `match_template()` 未命中
→ `load_domain_schema()`
→ `build_sql_prompt()`
→ `DeepSeekChatClient.complete()`
→ `extract_generated_sql()`
→ `validate_sql_policy()`
→ `db.execute()`
→ `AgentResponse`

一次安全拦截的数据流向：

`SELECT email FROM users`
→ `validate_readonly_sql()` 通过
→ `extract_sql_access()` 提取 `users.email`
→ 命中敏感字段
→ `safety_status=blocked`

### 设计要点

- **模板优先，不让 LLM 破坏稳定基线**：M3 已验证的 5 条模板问题继续走模板路径，模板未命中才走 LLM。
- **安全不靠 prompt**：prompt 会提醒模型不要写危险 SQL，但真正放行由 sqlglot AST、RBAC 和敏感字段策略决定。
- **provider 不过度抽象**：M4 只接 DeepSeek，先证明端到端能跑；SiliconFlow 等 provider 后续需要时再补。
- **业务口径仍放 domain_pack**：GMV、退款率、敏感字段都从配置读，`engine/` 不写电商硬编码。
- **边界明确**：M4 只做表级 / 字段级 allowlist；行级权限、脱敏样例数据和更细角色策略留到后续。

### 面试怎么讲

M4 可以讲成“把 **Text-to-SQL** 从规则模板升级到 **LLM 生成**，但没有把安全交给模型”。我先让模板 SQL 保持优先，保证 v0 稳定基线不被模型波动影响；未命中模板时，用 schema、指标口径和 few-shot 构造 prompt 调 DeepSeek。模型输出后，系统用 **sqlglot AST** 提取表和字段，再按 **RBAC allowlist** 和 **敏感字段策略**决定是否放行。这个设计能体现一个关键工程意识：LLM 可以负责生成候选答案，但数据库执行权必须由后端安全策略掌握喵

### 验证与下一步

- 验证：**24 个测试全过**；M4 smoke 真实调用 DeepSeek，**6 条 simple SQL 中 5 条通过**；危险 SQL、敏感字段和越权角色在自动化测试中都返回结构化拦截。
- warning：Starlette TestClient 提示 httpx 依赖迁移，不影响 M4 行为；`git diff --check` 只有 Windows CRLF 提示。
- 下一步：M5 扩展 AgentResponse、封装 SQL Tool、记录 Trace / cost / latency，并生成基础图表 spec。

可复制验证命令：

```powershell
# 跑所有自动化测试。预期：24 passed，可能有 1 个 Starlette/httpx warning。
python -m pytest -p no:cacheprovider

# 跑 M4 smoke。预期：6 条 simple SQL 里至少 5 条 passed=True；
# 当前已知 sql_005 可能因为模型没有选择 status 列而显示 missing_columns=['status']。
python scripts\smoke_m4_nl2sql.py

# 检查 ORM 模型和 MySQL 当前迁移是否一致。预期：No new upgrade operations detected.
python -m alembic check

# 查看当前数据库迁移版本。预期：20260717_0001 (head)。
python -m alembic current
```

**本地启动体验：**

```powershell
# 1. 确认 .env 里 DATABASE_URL 指向本地 MySQL datapilot_dev，并配置 DeepSeek key。
# 如果只想体验 M3 模板问题，DeepSeek key 不是必须；如果想体验 M4 LLM 生成问题，需要 key。

# 2. 准备数据库表结构。预期：数据库迁移到 head。
# 3. 写入确定性演示数据。预期：输出 users/products/orders/refunds/tickets 等行数和固定业务事实。
# 4. 启动 FastAPI 后端。预期：看到 Uvicorn running on http://127.0.0.1:8000。
python -m alembic upgrade head
python -m scripts.seed_data --reset
python -m uvicorn app.main:app --reload

# 服务启动后，用浏览器打开 Swagger UI `http://127.0.0.1:8000/docs`：
# `POST /api/query` → `Try it out` → 在 `Request body` 文本框里输入 JSON → `Execute` → 查看 `Response body` 里的字段。
```

M4 LLM 生成问题 —— 大致结果：`safety_status` 应该是 `passed`，`sql` 是一条查询 `products` 的 `SELECT`，`columns / rows` 会返回 active 商品列表。这个问题需要 DeepSeek key 可用，因为它不是 M3 的固定模板问题。

```json
{
  "question": "查询 active 商品列表前 10 条",
  "user_role": "ops"
}
```

M3 模板问题 —— 大致结果：`safety_status=passed`，`answer` 会提到 `Aurora Noise Cancelling Headphones`，`rows` 第一行包含 `refund_count=18`、`order_count=40`、`refund_rate=0.45`。这条会优先命中 M3 模板 SQL，所以不依赖 LLM 生成质量。

```json
{
  "question": "2026年6月退款率最高的商品是什么？",
  "user_role": "ops"
}
```

安全拦截 —— 大致结果：`safety_status=blocked`，`blocked_reason` 会提到 `users.email` 这类敏感字段，说明 M4 的字段级安全策略生效。

```json
{
  "question": "查询用户邮箱",
  "user_role": "ops"
}
```

## ★ M5 AgentResponse 扩展、Trace、Tool 与图表（2026-07-20）

**简述**：把 `/api/query` 从“能查出表格”升级成一个**可评测、可演示、可追踪**的结构化 Agent 输出。

### 这次做了什么

M5 做的是：把 M3/M4 查出来的结果，整理成后续评测和演示能直接使用的标准输出

M4 已经解决了 SQL 从哪里来、怎么安全执行的问题：模板优先，未命中时走 LLM，所有 SQL 都过 SQL Guard。M5 做的是另一件同样重要的工程收口：让这个查询结果变成后续 **EvalOps-lite** 和演示页可以直接消费的标准响应。

这次先扩展了 `AgentResponse`：除了原来的 `route / answer / sql / columns / rows / safety_status / trace_id`，新增了 **`tables_used`**、**`docs_used`**、**`chart_spec`**、**`cost`**、**`tool_calls`** 和 **`error_type`**。这些字段让前端不需要猜：用了哪些表、有没有文档证据、能不能画图、SQL 花了多久、哪个工具被调用、失败属于什么类型。

然后把 SQL 执行从 API 层抽成 **SQL Tool**。原来 `/api/query` 自己做 Guard、自己 `db.execute()`、自己转 rows；现在它把 SQL、角色和 trace_id 交给 `run_sql_tool()`，SQL Tool 统一做安全检查、表名提取、查询执行、耗时统计和 tool call 记录。API 层回到编排职责：解析问题、调用工具、拼响应、写 trace。

最后补了 **Chart Tool** 和 **JSONL Trace**。Chart Tool 根据表格形状生成基础 Vega-Lite spec：各渠道订单量是柱状图，退款率最高商品是横向柱状图，GMV 单指标是一根柱。Trace 先写 JSONL，每行保存一次完整查询过程；这是后续 M6 评测最需要的“证据链”。

### 新概念

- **AgentResponse 扩展契约**：可以理解成后端给前端和评测系统的“固定合同”。字段一旦稳定，Streamlit、EvalOps、甚至未来别的前端都能按同一份结构读取结果。
- **ToolCallTrace**：记录一次工具调用的过程，例如 `sql_query` 成功、`sql_guard` 拦截、耗时多少、访问了哪些表。类比 SpringBoot 里的调用日志，但它是结构化数据，评测程序也能读。
- **CostInfo**：记录一次查询的成本和耗时。M5 先真实记录 `latency_ms` 和 `sql_time_ms`，模型名和 token 先保留字段，后续接 LLM usage 时直接填进去。
- **JSONL Trace**：一行一个 JSON 对象。好处是追加写入简单，M6 可以按行读取，不需要现在就设计数据库表和查询接口。
- **Vega-Lite chart_spec**：一种前端可视化描述格式。后端不直接画图，而是告诉前端“用什么 mark、什么字段做 x/y 轴、数据是什么”，演示页可以直接渲染。

### 关键文件

- `app/schemas/agent.py`：M5 扩展版 AgentResponse、CostInfo、ToolCallTrace。
- `engine/tools/sql_tool.py`：SQL Tool，统一执行 Guard、SQL 查询、耗时和工具调用记录。
- `engine/tools/chart_tool.py`：Chart Tool，把聚合结果转成 Vega-Lite 兼容 spec。
- `engine/trace/recorder.py`：JSONL Trace 写入器。
- `domain_pack/chart_templates/basic.yaml`：bar / line / horizontal_bar 三类基础图表模板。
- `app/api/query.py`：查询编排层，调用 SQL Tool、Chart Tool，并写 Trace。
- `tests/test_m5_agent_response.py`：M5 响应契约、trace 和图表规则测试。
- `scripts/smoke_m5_agent_response.py`：M5 smoke，输出人工验收摘要。

### 代码阅读路线

1. **响应合同**：`app/schemas/agent.py`
   先看 `AgentResponse`、`CostInfo` 和 `ToolCallTrace`。重点理解 M5 不是改旧字段，而是新增评测和演示页需要的字段。

2. **SQL Tool**：`engine/tools/sql_tool.py`
   主角是 `run_sql_tool()`。它先调用 `validate_sql_policy()`，再用 `extract_sql_access()` 提取 `tables_used`，最后执行 SQL 并返回 `SQLToolResult`。

3. **图表生成**：`engine/tools/chart_tool.py`
   主角是 `build_chart_spec()`。读的时候重点看三类规则：类别 + 数值走 `bar`，日期 + 数值走 `line`，Top / 最高类问题走横向 `bar`。GMV 单指标用 `metric_name/value` 合成一根柱。

4. **Trace 写入**：`engine/trace/recorder.py`
   主角是 `TraceRecord` 和 `append_trace()`。它把一次 Agent 查询写成 JSONL 的一行，M6 后续按行读即可。

5. **API 编排**：`app/api/query.py`
   读 `query()`：模板 / LLM 解析 SQL 后，不再直接执行数据库，而是调用 `run_sql_tool()`；成功时再调用 `build_chart_spec()`，最后 `_record_trace()` 写 JSONL。

一次成功查询的数据流向：

`POST /api/query`
→ `QueryRequest`
→ `match_template()` / `generate_sql()`
→ `run_sql_tool()`
→ `validate_sql_policy()`
→ `db.execute()`
→ `build_chart_spec()`
→ `AgentResponse`
→ `TraceRecord JSONL`

一次拦截查询的数据流向：

`DROP TABLE orders`
→ `validate_readonly_sql()`
→ `ToolCallTrace(tool_name="sql_guard", status="blocked")`
→ `AgentResponse(error_type="sql_guard_blocked")`
→ `TraceRecord JSONL`

**模块闭环**：M3-M5 现在形成了一个可演示的 SQL Agent 闭环：M3 负责**模板 SQL 稳定基线**，M4 负责**LLM SQL 生成和安全策略**，M5 负责**结构化输出、工具调用记录、Trace 和图表**。换句话说，M5 让前面的能力从“后端能跑”变成“评测和页面能消费”。

### 设计要点

- **Trace 先 JSONL，不上数据库表**：这是用户确认后的方案。JSONL 足够支撑 M6 smoke 评测，也避免 M5 扩大到 migration / Trace 查询服务。
- **SQL Tool 固定安全边界**：任何 SQL 进入数据库前都在 Tool 内过 policy，避免后续 Agent 编排绕过 Guard。
- **AgentResponse 只增不改**：M3/M4 已有字段含义保持不变，保证旧测试和调用方继续可用。
- **图表规则轻量但可消费**：只支持基础 bar / line / horizontal_bar；无法判断时返回 `chart_spec=null`，不阻塞答案。
- **单指标 GMV 做合成柱图**：因为现有模板返回单行 `gmv`，Chart Tool 用 `metric_name/value` 生成一根柱，满足演示需要且不改 SQL 口径。

### 面试怎么讲

M5 可以讲成“我把 Text-to-SQL 的结果做成了**可观测的 Agent 输出协议**”。很多项目只返回 answer 和 SQL，但我额外记录了 **tool_calls、cost、tables_used、chart_spec、error_type 和 JSONL trace**。这样做的价值是：前端能直接展示图表，评测系统能按 trace_id 回放每次查询，安全拦截也能被归类统计。工程上，我把 SQL 执行从 API 层拆成 SQL Tool，保证安全检查、执行和耗时记录在同一个边界里，后续换成 LangGraph 或 EvalOps 时不用重写核心查询逻辑喵

### 验证与下一步

- 验证：**27 个测试全过**；M5 smoke **4/4 通过**，覆盖渠道订单量、商品退款率、GMV 和危险 SQL 拦截；Alembic check/current 正常。
- warning：Starlette TestClient 提示 httpx 依赖迁移，不影响 M5 行为；`git diff --check` 只有 Windows CRLF 提示。
- 下一步：M6 做 EvalOps-lite 和 Streamlit 演示页，直接消费 M5 的 AgentResponse、chart_spec 和 trace。

可复制验证命令：

```powershell
# 跑所有自动化测试。预期：27 passed，可能有 1 个 Starlette/httpx warning。
python -m pytest -p no:cacheprovider

# 跑 M5 smoke。预期：4/4 passed；摘要写入 .agent_work/temp/m5-smoke.md。
python scripts\smoke_m5_agent_response.py

# 检查 ORM 模型和 MySQL 当前迁移是否一致。预期：No new upgrade operations detected.
python -m alembic check

# 查看当前数据库迁移版本。预期：20260717_0001 (head)。
python -m alembic current
```

**本地启动体验：**

```powershell
# 1. 准备数据库和 seed。预期：MySQL datapilot_dev 里有 M1 的确定性数据。
# 2. 启动 FastAPI 后端。预期：看到 Uvicorn running on http://127.0.0.1:8000。
python -m alembic upgrade head
python -m scripts.seed_data --reset
python -m uvicorn app.main:app --reload

# 服务启动后，用浏览器打开 Swagger UI `http://127.0.0.1:8000/docs`：
# `POST /api/query` → `Try it out` → 输入下面 JSON → `Execute`。
```

图表查询 —— 大致结果：`safety_status=passed`，`tables_used=["channels","orders"]`，`chart_spec.mark="bar"`，`tool_calls[0].tool_name="sql_query"`，trace 会追加到 `eval/traces/traces.jsonl`。

```json
{
  "question": "各渠道订单量是多少？",
  "user_role": "ops"
}
```

安全拦截 —— 大致结果：`safety_status=blocked`，`chart_spec=null`，`tool_calls[0].tool_name="sql_guard"`，`error_type="sql_guard_blocked"`。

```json
{
  "question": "DROP TABLE orders",
  "user_role": "admin"
}
```

## ★ M6 EvalOps-lite 与演示收尾（2026-07-20）

**简述**：把阶段二的 SQL Agent 闭环收成一个**能批量评测、能本地演示、能进入阶段三**的 v1 小系统。

### 这次做了什么

M6 做的是“收口”：前面 M3-M5 已经能把自然语言变成安全 SQL、结构化响应、图表和 trace；这次把这些能力接到两个使用场景上。

第一个场景是 **EvalOps-lite**。`eval/cases/smoke.yaml` 从 32 条问题清单里抽出 6 条 smoke：2 条简单 SQL、2 条聚合、1 条多表 join、1 条安全攻击。`eval/run_eval.py` 会读取 YAML，通过 FastAPI `/api/query` 批量调用真实 API，再检查 route、表、列、安全期望和关键结果，最后写出 `eval/reports/latest.md`。这就像给 Agent 做一个很小但稳定的“单元验收台”：不是完整评测平台，但能快速回答“v1 主链路今天还通不通”。

第二个场景是 **Streamlit 演示页**。`demo/streamlit_app.py` 不复制任何 SQL 或 Agent 逻辑，只通过 HTTP 调 `/api/query`，展示 `answer`、SQL、表格、图表、`safety_status`、`trace_id` 和 tool trace。这样本地演示和后端真实链路一致：Swagger 能测，Streamlit 能看，EvalOps-lite 能批量跑。

最后补了阶段二收尾材料：README 写清 v1 能力、启动方式、评测命令和未实现边界；`eval/reports/phase2-v1-acceptance.md` 记录 v0/v1 能力清单、6 条 smoke 结果和阶段三 RAG 输入。

### 新概念

- **EvalOps-lite**：一个**轻量评测闭环**。完整 EvalOps 会有用例管理、批量运行、评分、报告、历史趋势；M6 只实现最小版：**YAML case -> 调 API -> 评分 -> Markdown 报告**。
- **API seam 评测**：评测不绕过 `/api/query` 直接调内部函数，而是走**真实 API 契约**。类比 SpringBoot 项目里用 Controller 层集成测试，不只测 Service 私有逻辑。
- **Smoke case**：少量**高价值用例**，用来快速确认主链路还活着。它不是全量回归，但适合作为每次开发后的**第一道健康检查**。
- **阶段验收报告**：把“**当前到底完成了什么、没完成什么、下一阶段接哪里**”写成持久文档，避免 README、简历和复盘时凭记忆拼。

### 关键文件

- `eval/cases/smoke.yaml`：M6 的 6 条 smoke 用例，字段沿用 `eval/cases_plan.md` 草案。
- `eval/run_eval.py`：EvalOps-lite 执行入口，负责加载 YAML、调用 `/api/query`、评分、写报告。
- `eval/reports/latest.md`：最近一次 smoke 评测报告，记录 pass/fail/error_type/trace_id。
- `eval/reports/phase2-v1-acceptance.md`：阶段二 v1 收尾记录。
- `demo/streamlit_app.py`：Streamlit 最小演示控制台。
- `README.md`：补充 M6 评测命令、演示页启动方式、v1 能力边界。

### 代码阅读路线

1. **用例入口**：`eval/cases/smoke.yaml`
   先看 `cases` 下面的 6 条用例，每条都包含 `id`、`task_type`、`question`、`expected_tables`、`expected_columns`、`security_expectation` 和 `check`。这里的关键设计是 **评测字段复用**：M6 没有重新发明一套 case 格式，而是把 M3 在 `eval/cases_plan.md` 里定好的 YAML 草案落成文件。读的时候重点看 6 条 smoke 如何覆盖简单 SQL、聚合、多表 join 和安全拦截，不用纠结每条 SQL 最终由模板还是 LLM 生成。

2. **评测执行**：`eval/run_eval.py`
   可以按“一条 case 的旅程”来读：先看 `main()`，它负责把命令行参数、用例加载、API 测试客户端、执行结果和报告输出串起来。然后看 `load_cases()`，它把 YAML 用例变成 `EvalCase`；`seeded_api_client()` 准备 **内存 SQLite 测试库**，并用 FastAPI **dependency override** 临时替换 `get_db()`；`run_cases()` 用 `TestClient` 调真实 `/api/query`；最后 `write_report()` 把结果写成 `latest.md`。重点理解：M6 评测走的是 **API seam**，不是绕过接口直接调内部函数。

3. **评分逻辑**：`eval/run_eval.py`
   主角是 `_score_case()`，它接收一条 `EvalCase` 和一次 `/api/query` 返回的 AgentResponse，然后判断这条 case 是否通过。这里的关键设计是 **smoke 级评分**：它只检查 HTTP 200、`route=sql`、安全状态、表/列命中和关键文本包含，目的是快速发现主链路断没断。不要把它理解成完整 SQL 语义评测；比如 SQL 写法是否最优、结果是否覆盖所有业务边界，都不是 M6 这层负责。

4. **演示页面**：`demo/streamlit_app.py`
   先看 `main()`，它负责页面布局：左侧放 API 地址、角色和预置问题，主区域放问题输入和执行结果。再看 `_post_query()`，它通过 HTTP 调真实 `/api/query`，说明 Streamlit 只是演示层，不复制后端 Agent 逻辑。最后看 `_render_response()`：它把 AgentResponse 拆成 **answer / SQL / table / chart / trace** 几块展示。这里的关键设计是 **前端消费统一响应契约**，也就是演示页只依赖 M5 固定下来的字段，而不是自己猜 SQL、图表或安全状态。

5. **阶段记录**：`eval/reports/phase2-v1-acceptance.md`
   这个文件不是程序入口，而是阶段二的**交付边界说明**。先看 v0 / v1 capability checklist，确认哪些能力已经有证据支撑；再看 `Boundaries`，它明确写了 RAG、Hybrid、LangGraph、MCP 还没有在阶段二实现。这里的关键设计是 **报告不夸大能力**：它既能给 README、简历和复盘提供阶段成果，也防止后续 AI 或人把“计划中的 RAG”误写成“已经完成的 RAG”。

一次 M6 评测的数据流向：

`smoke.yaml`
→ `EvalCase`
→ `TestClient POST /api/query`
→ `AgentResponse`
→ `_score_case()`
→ `EvalResult`
→ `eval/reports/latest.md`

一次 Streamlit 演示的数据流向：

`页面输入问题`
→ `HTTP POST /api/query`
→ `AgentResponse`
→ `answer / SQL / table / chart / trace` 展示

**模块闭环**：M3-M6 现在构成阶段二 v1 闭环：M3 有模板 SQL 基线，M4 有 LLM NL2SQL 与安全策略，M5 有结构化输出和图表 trace，M6 有 smoke 评测和演示入口。阶段二可以作为一个可运行、可讲述、可继续扩展的简历项目节点。

### 设计要点

- **评测走 API seam**：用户确认后选择 `/api/query`，不直接调内部 pipeline。这样慢一点，但更贴近**真实用户路径**，也能一起检查 API 契约、Trace 和图表字段。
- **默认用内存 SQLite seed**：Eval runner 通过 **FastAPI dependency override** 接内存库，不写 **MySQL 主库**；这保持评测可重复，也不污染开发数据。
- **case 选择避开模板误命中**：`join_005` 会提前命中“渠道 + 订单量”模板，缺 `gmv`；`join_001` 会提前命中“退款 + 原因”模板。M6 最终选 `join_002`，稳定走**三表 join**。
- **演示页只做最小控制台**：不做历史记录、复杂筛选和多页面，避免 **M6 范围膨胀**。
- **报告诚实写边界**：README 和验收记录只写**已完成的 SQL Agent v1**，不把 RAG、LangGraph、MCP 写成已实现。

### 面试怎么讲

M6 可以讲成“我给 Agent 项目补了一个轻量 EvalOps 和演示闭环”。我不是只做了一个 `/api/query` 接口就结束，而是把问题整理成 **YAML case**，通过真实 API 批量调用，记录 **pass/fail/error_type/trace_id**，并生成 Markdown 报告。同时用 Streamlit 做了一个最小演示台，让面试官能看到 answer、SQL、表格、图表和 trace。这个模块体现的是工程收尾能力：能把一个 AI 能力从“能跑”推进到“能测、能演示、能复盘、能继续迭代”喵

### 验证与下一步

- 验证：`py_compile` 通过；全量 pytest **27 passed, 1 warning**；`python -m eval.run_eval` **6/6 passed**；Streamlit 页面 HTTP 200，真实 API 查询返回 answer / SQL / rows / chart_spec / trace_id。
- warning：默认 `.agent_work/temp/pytest-tmp` 曾被 Windows 旧临时目录锁住，改用新的 `--basetemp=.agent_work/temp/pytest-m6-tmp-final` 后测试通过；Starlette TestClient 仍有 httpx 迁移 warning，不影响 M6。
- 下一步：用户人工检查后可运行 `accept-module` 做 M6 最终验收；通过后进入阶段三 RAG / Hybrid。

可复制验证命令：

```powershell
# 编译 M6 新增 Python 文件。预期：无输出即通过。
python -m py_compile eval\run_eval.py demo\streamlit_app.py

# 跑全量测试。若默认 pytest-tmp 被 Windows 锁住，可使用新的 basetemp；预期：27 passed。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m6-tmp-final

# 跑 M6 EvalOps-lite。预期：passed=6/6，报告写入 eval/reports/latest.md。
python -m eval.run_eval
```

**本地启动体验：**

```powershell
# 1. 启动 FastAPI。预期：Uvicorn running on http://127.0.0.1:8000。
python -m uvicorn app.main:app --reload

# 2. 启动 Streamlit。预期：Local URL: http://localhost:8501。
python -m streamlit run demo\streamlit_app.py
```

打开 `http://localhost:8501` 后，可以点左侧预置问题，例如“各渠道订单量是多少？”。大致结果：主区域展示自然语言答案、SQL、表格、柱状图和 trace；如果点 `DROP TABLE orders`，会看到 `safety_status=blocked` 和 `sql_guard_blocked`。

## ★ Phase 2.7 数据库升级（2026-07-22）

**简述**：把阶段二的 7 表数据底座升级成 **14 张物理表 + 1 万级订单数据**，让后续 Phase 3A Text2SQL 深化面对的不是小 demo 库，而是更接近真实企业分析系统的复杂 schema。

### 这次做了什么

阶段二 M0-M6 已经跑通了 SQL Agent v1：能查库、能安全拦截、能出图表、能跑 smoke。但 7 张表的数据底座仍然偏“教学版”：订单是一单一商品，类目只是字符串，没有优惠券多对多、行为日志、价格历史、宽表和数据质量问题。这样的库可以证明链路能跑，却不够支撑 Phase 3A 要做的 **Schema Retrieval、JoinPath、QueryPlanStep 和局部 Schema Prompt**。

所以 Phase 2.7 先做了一次数据库底座升级。表结构上，从原来的用户、商品、渠道、订单、退款、工单、知识库 7 张表，扩展为 **13 张业务分析表 + 1 张桥接表**。新增内容包括：**订单明细 `order_items`**、**类目树 `product_categories`**、**优惠券 `coupons` + 桥接表 `order_coupons`**、**行为日志 `user_behavior_log`**、**价格历史 `product_price_history`** 和 **订单宽表 `orders_wide`**。旧表没有简单推倒重来，而是保留 `orders.product_id` 和 `products.category`，让阶段二 API、模板 SQL 和 M6 smoke 继续兼容。

数据上，`scripts/seed_data.py` 不写死 10000 行，而是用确定性规则生成真实感模拟业务数据：**10000 张订单、18000 条订单明细、1000 条退款、3000 条用券记录、10000 条用户行为日志**。同时保留一组固定业务事实，例如 2026 年 6 月 GMV、Aurora 耳机退款率最高、Mobile App 渠道 GMV Top、`JUNE_FIXED_50` 在 Mobile App 使用最多、数码电子类目 GMV Top、mobile_app 设备转化率最高等。这样后续 Agent 生成 SQL 时，不只要“能跑”，还可以被稳定标准答案检查。

最后补齐了领域知识和评测素材：`domain_pack/schema_desc/relations.yaml` 把外键、桥接表、递归层级、SCD 时间窗口和聚合风险结构化写出来；`metrics.yaml` 明确 GMV、商品维度 GMV、净收入、优惠券使用率、转化率和历史售价口径；`database-upgrade-challenge.yaml` 放 16 条数据库挑战用例，`phase3a-regression.yaml` 放 10 条 Phase 3A 正式回归输入。注意：这次只升级数据库和数据，不进入 Phase 3A M8，也不提前要求 trace_steps 通过。

### 新概念

- **订单头 / 订单明细**：真实电商里一笔订单可能买多个商品，所以订单头 `orders` 记录“这笔订单整体状态和总金额”，订单明细 `order_items` 记录“这一单里每个商品买了几件、多少钱”。以后问订单级 GMV 可以查 `orders.order_amount`，问商品销售额就应该走 `order_items.line_amount`。
- **桥接表**：`orders` 和 `coupons` 是多对多关系，一笔订单可能用多张券，一张券也会被多笔订单使用，所以中间需要 `order_coupons`。面试里可以把它类比成 Java 里订单和标签的关联表：统计订单数时要 `COUNT(DISTINCT orders.id)`，否则一单多券会把订单量放大。
- **类目树 / 递归 CTE**：`product_categories` 不是平铺枚举，而是父子层级。用户问“数码电子及其子类目 GMV”时，SQL 需要递归展开子类目，再关联商品和订单明细。
- **SCD Type 2 价格历史**：`products.price` 是当前价，`product_price_history` 保存历史价格窗口。问“6 月当时售价”不能直接用当前价，而要用 `valid_from / valid_to` 做时间窗口匹配。
- **宽表 `orders_wide`**：把订单、用户、商品、渠道常用字段冗余到一张表，适合看板汇总，但不适合明细追溯和强一致校验。它用来训练 Agent 判断“这题用宽表快，还是用规范化星型模型更准”。
- **数据质量彩蛋**：新 seed 故意加入少量真实业务常见问题，例如未支付订单 `paid_at IS NULL`、`canceled/cancelled` 状态拼写差异、源系统单号重复、少量金额不一致、负数退款冲销。这不是把数据库做脏，而是在不破坏主键 / 外键 / 唯一约束的前提下模拟真实数据挑战。

### 关键文件

- `app/models/`：新增和改造 ORM 模型，描述 14 张物理表。
- `alembic/versions/20260722_0002_database_upgrade_14_tables.py`：Phase 2.7 数据库迁移，负责把旧 7 表升级到 14 表。
- `scripts/seed_data.py`：确定性 seed 数据工厂，生成 1 万级订单、固定事实和 seed summary。
- `domain_pack/schema_desc/relations.yaml`：结构化关系事实源，后续 M9 生成 relation_doc / JoinPath 会优先读它。
- `domain_pack/metrics.yaml`：指标口径单一事实源，明确订单级 GMV、商品维度 GMV、净收入等默认口径。
- `eval/cases/database-upgrade-challenge.yaml`：16 条数据库挑战集，验证新库复杂度和固定事实。
- `eval/cases/phase3a-regression.yaml`：10 条 Phase 3A 正式回归输入，给 M8 baseline 使用。
- `tests/test_database_upgrade.py`：数据库升级专用测试，验证 challenge case 结构、expected SQL 基础稳定和安全拦截。

### 代码阅读路线

1. **表结构入口**：`app/models/`
   先看新增模型，不要急着背字段。重点理解每张表引入的 SQL 难题：`OrderItem` 解决一单多商品，`OrderCoupon` 解决多对多，`ProductCategory` 解决层级类目，`ProductPriceHistory` 解决历史价格，`OrderWide` 解决宽表 vs 星型模型选择。

2. **迁移脚本**：`alembic/versions/20260722_0002_database_upgrade_14_tables.py`
   把它当成“真实数据库结构变化清单”读。先看 `upgrade()` 如何按依赖顺序建新表、给旧表加列，再看 `downgrade()`。这里的阅读重点是 **MySQL DDL 不是事务性的**：外键索引不能随便先删，`paid_at` 从可空回滚到非空前也必须回填 NULL。

3. **Seed 数据工厂**：`scripts/seed_data.py`
   主角是 `seed_database()` 和 `verify_business_facts()`。前者按父表、事实表、桥接表、宽表的顺序生成数据；后者用真实 SQL 查固定事实。读的时候重点看：外键靠 ORM 对象关系，不靠自增 ID；固定事实靠 `sku/coupon_code/channel_code` 等业务键，不靠 `id=1`。

4. **业务语义层**：`domain_pack/schema_desc/` 和 `domain_pack/metrics.yaml`
   这里不是给数据库执行的，而是给后续 Text2SQL 中间层理解业务的。重点看 `orders.md`、`order_items.md`、`refunds.md` 和 `relations.yaml`：它们告诉 Agent 什么时候查订单头、什么时候查明细、什么时候要 `COUNT(DISTINCT)`。

5. **评测素材**：`eval/cases/database-upgrade-challenge.yaml` 和 `eval/cases/phase3a-regression.yaml`
   先看两者边界：challenge 是 16 条数据库复杂度素材，不替代正式硬门；regression 是 10 条 Phase 3A M8-M12 主线回归。这个拆分能避免一上来把 Phase 3A 验收压成复杂 SQL 全能力攻坚。

一次真实 seed 的数据流向：

`seed_database()`
→ `_build_product_categories/users/products/channels/coupons()`
→ `_build_orders_and_items()`
→ `_build_order_coupons()`
→ `_build_refunds/tickets/user_behavior_logs()`
→ `_build_orders_wide()`
→ `verify_business_facts()`
→ `.agent_work/temp/database-upgrade-seed-summary.md`

**模块闭环**：Phase 2.7 不是新增 Agent 智能，而是把 Phase 3A 要训练和评测的“地形”铺出来。没有这一步，Schema Retriever、JoinPath 和 QueryPlanStep 很容易只是在小库上自嗨；有了 14 表和固定事实，后续每个优化都能被真实复杂 schema 检验。

### 设计要点

- **不推倒阶段二旧契约**：保留 `orders.product_id` 和 `products.category`，让旧 API、旧模板、M6 smoke 都能继续跑；新口径通过 metrics 和 schema_desc 引导后续新链路。
- **seed 生成逻辑优先于静态数据**：不把 10000 行逐行写死，避免数据不可维护。规则化生成既能规模化，又能保证固定事实稳定。
- **固定事实用业务键定位**：MySQL 多次 reset 后自增 ID 不一定从 1 开始，所以 seed 和测试都不依赖具体 ID。这是后端项目里很重要的可迁移性习惯。
- **challenge 和 regression 分开**：16 条 challenge 证明数据库复杂度，10 条 regression 才是 Phase 3A 主线硬门。这样既有技术深度，又不会把 M8 变成过度验收。
- **脏数据不破坏工程约束**：真实业务会乱，但主业务表仍然应该守住外键和唯一约束。逻辑脏数据放进源系统字段和少量金额不一致样例里，既真实又可控。

### 面试怎么讲

Phase 2.7 可以讲成”我为了让 Text2SQL 项目从 demo 走向真实业务复杂度，专门升级了数据库底座”。原来只有 7 张表，Agent 很容易靠全量 schema prompt 硬猜；升级后有 **14 张物理表、1 万级订单、1.8 万级订单明细、多对多优惠券、递归类目、SCD 价格历史、行为漏斗和宽表快照**。我还把固定业务事实和数据质量彩蛋写进确定性 seed，并用 Alembic 管理可逆迁移。这样后续做 Schema Retriever、JoinPath 和 QueryPlanStep 时，不是凭感觉优化 prompt，而是在一套可复现的新库上验证选表、Join、指标口径和安全边界喵

**审查后 polish**：Phase 2.7 验收后，外部 AI 审查指出几处 plan v5 与实现之间的口径偏差——`orders_wide` 缺 `user_role/primary_product_price/item_count/refund_count/total_refund/has_refund/updated_at` 七个字段、`coupons` 缺 `ix_valid_range` 复合索引、`product_price_history` 缺 `change_reason`。通过独立的 `20260722_0003` migration 补齐，不改链路、不改旧字段名、不扩大范围。面试可以讲：**plan 和实现有偏差时不是默默跳过，而是用独立 migration 补齐——Alembic 历史清晰可追溯，后续接手的人看到 `0003` 就知道这是”审查后补齐的口径”，不会和 `0002` 的核心升级混在一起。**

### 验证与下一步

- 验证：真实 MySQL 完整跑过 `alembic downgrade 20260717_0001` → `alembic upgrade head` → `python -m scripts.seed_data --reset`；最终 `alembic current` 为 `20260722_0003 (head)`，`alembic check` 无新增操作。
- 自动化：全量 pytest **31 passed, 1 warning**；M6 smoke **6/6 passed**；`git diff --check` 无 whitespace error，仅 Windows CRLF 提示。
- 下一步：进入 Phase 3A M8 回归基线冻结。

可复制验证命令：

```powershell
# 查看当前数据库迁移版本。预期：20260722_0003 (head)。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current

# 检查 ORM metadata 与真实 MySQL 是否一致。预期：No new upgrade operations detected.
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check

# 重置并写入 14 表确定性 seed。预期：输出 14 张表行数和固定业务事实。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset

# 跑全量测试。预期：31 passed, 1 warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-db-upgrade-full

# 跑阶段二 M6 smoke 回归。预期：passed=6/6。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\smoke.yaml --report eval\reports\latest.md --trace .agent_work\temp\database-upgrade-m6-smoke-traces.jsonl
```

**本地启动体验：**

```powershell
# 1. 准备新库。预期：MySQL datapilot_dev 迁移到 14 表，并写入 1 万级 seed 数据。
python -m alembic upgrade head
python -m scripts.seed_data --reset

# 2. 启动 FastAPI。预期：Uvicorn running on http://127.0.0.1:8000。
python -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/docs` 后，可以继续用 `POST /api/query` 测阶段二旧问题，例如”2026年6月本月GMV是多少？”。大致结果：`safety_status=passed`，`chart_spec` 是单指标柱图，GMV 会变成新库的 **11285752.0**。如果测”各渠道订单量是多少？”，仍会返回 Mobile App 等渠道结果，说明旧链路在新库上保持兼容。

## ★ Phase 3A M8 回归基线冻结（2026-07-22）

**简述**：把阶段二旧 SQL 链路放到 Phase 3A 的 10 条 formal regression 和 16 条 challenge 上跑一遍，像做性能优化前先量一次旧机器的真实速度，后续 M9-M12 才有可信对照。

### 这次做了什么

Phase 3A 的目标不是立刻让 Text2SQL 变聪明，而是先回答一个很朴素的问题：**旧链路在 14 表新库上到底是什么水平？** 如果没有这个 baseline，后面做 Schema Retrieval、JoinPath、QueryPlanStep 时，就很容易只凭感觉说“新链路更好”，但说不清好在哪里。

这次 M8 没有改数据库、没改 `/api/query` 默认行为，也没有提前做新 pipeline。主要做了四件事：第一，检查 `eval/cases/phase3a-regression.yaml` 仍然是 **10 条正式回归**，比例为 2 条 simple、3 条 aggregation、3 条 multi_table、2 条 security；第二，确认 `eval/cases/database-upgrade-challenge.yaml` 是 **16 条 challenge superset**，包含全部 10 条 formal question，额外 6 条覆盖更多数据库复杂度；第三，把 `eval/run_eval.py` 从 M6 smoke runner 扩展成能读 Phase 3A 字段的 runner，新增 `expected_metrics / expected_trace_steps / pipeline_mode`，但旧 `smoke.yaml` 不需要补字段；第四，报告里新增 **issue_tags** 和 **review_required**，把失败原因稳定标成 `missing_column`、`missing_table`、`safety_mismatch` 或 `unexpected_error`，并让困难诊断题显式提示人工复核，避免后续对照报告靠解析自然语言字符串。

最终 baseline 很诚实：**10 条 formal 里 8 条通过**，其中 **安全题 2/2 拦截**；但允许类 SQL 只有 **6/8 通过**，低于计划里“7/8”的理想门槛。两个失败都不是危险 SQL，而是旧链路输出列别名和 regression 期望不一致：`p3a_multi_001` 返回 `order_count`，期望 `coupon_order_count`；`p3a_multi_003` 返回 `category_name`，期望 `category`。同步跑出的 **16 条 challenge 为 11/16 通过**，其中 `db_hard_001` 和 `db_hard_003` 属于困难诊断题，失败时也会标记 `review_required=True`。我没有删 case、没有放宽门槛，也没有回头修旧链路；用户确认后，按真实旧链路状态冻结为 baseline。

### 新概念

- **Baseline（基线）**：做优化前先保存旧系统的真实表现。它不一定好看，但必须真实。类比做 Java 服务性能优化前先记录 QPS / P95 延迟；没有基线，就不知道优化到底有没有价值。
- **Regression Case（回归用例）**：一组固定问题，每次改链路都跑同一批，防止“修了一个场景，弄坏另一个场景”。Phase 3A 固定 10 条，是后续新旧链路对照的尺子。
- **Challenge Superset（挑战扩展集）**：比正式回归更大的诊断题本。当前 16 条 challenge 包含 10 条 formal question，额外 6 条用来观察旧链路和新链路在更复杂数据库问题上的变化。
- **Issue Tag**：把失败原因变成稳定标签，而不是只写一句人类描述。`missing_column` 这样的标签后续可以直接被 Markdown 对照报告、失败统计或 EvalOps 平台消费。
- **Manual Review**：困难诊断题可能不是早期硬门，但报告必须告诉读者“这里需要人工复核”。这比简单写 pass/fail 更诚实，也为 M11/M12 的 trace_steps 诊断留位置。
- **Pipeline Mode**：评测入口预留的链路选择字段。M8 默认都是 `baseline`，后续 M11/M12 才会用类似 `force_new_pipeline` 的方式强制走新 Text2SQL pipeline。

### 关键文件

- `eval/cases/phase3a-regression.yaml`：Phase 3A 10 条正式 regression 输入，M8 只校验和运行，不重选题。
- `eval/cases/database-upgrade-challenge.yaml`：Phase 3A 16 条 challenge superset，每模块同步运行，用来观察困难诊断和扩展场景。
- `eval/run_eval.py`：评测执行入口，负责加载 YAML、调用真实 `/api/query`、评分并生成 Markdown 报告。
- `tests/test_phase3a_eval.py`：M8 新增测试，守住 case 比例、新字段默认值、issue tags 和报告字段。
- `eval/reports/phase3a-baseline.md`：旧链路 baseline 报告，记录 10 条 case 的 pass/fail、SQL、trace_id 和 issue tag。
- `eval/reports/phase3a-challenge-baseline.md`：旧链路 challenge baseline 报告，记录 16 条 case 的 pass/fail、review_required、SQL、trace_id 和 issue tag。
- `.agent_work/temp/m8-notes.md`：M8 开工 checklist、TDD 红绿灯、baseline 失败明细和用户确认记录。

### 代码阅读路线

1. **正式题本**：`eval/cases/phase3a-regression.yaml`
   先看 10 条 case 的结构：每条都有 `id / task_type / question / expected_tables / expected_columns / expected_metrics / security_expectation / check`。重点理解它不是“随手问几个问题”，而是 Phase 3A 后续模块共同使用的**固定回归尺子**。

2. **扩展题本**：`eval/cases/database-upgrade-challenge.yaml`
   再看 16 条 challenge。它不是另一套独立硬门，而是 formal regression 的 **superset**：10 条正式问题都在里面，额外 6 条覆盖已支付订单、退款率最高商品、渠道订单量、渠道 GMV、递归类目和 SCD 历史售价。

3. **评测入口**：`eval/run_eval.py`
   可以按“一条 case 的旅程”来读：`load_cases()` 把 YAML 变成 `EvalCase`，其中新字段有默认值，保证旧 smoke 不坏；`seeded_api_client()` 继续用 **内存 SQLite + FastAPI dependency override** 调真实 `/api/query`；`run_cases()` 按 `pipeline_mode` 组装请求，M8 默认 baseline；`_score_case()` 返回 `EvalScore`，把 pass/fail、reason 和 issue_tags 分开；`write_report()` 生成 Markdown baseline 报告。

4. **测试反推契约**：`tests/test_phase3a_eval.py`
   这份测试最适合用来理解 M8 到底改了什么。先看比例测试，确认 10 条 formal 的组成；再看 superset 测试，确认 10 条问题都包含在 16 条 challenge 中；然后看 loader 测试，确认新字段不会绑架旧 smoke；最后看 issue tag、manual review 和 report 测试，确认失败可以被后续对照脚本稳定消费。

5. **真实 baseline 报告**：`eval/reports/phase3a-baseline.md` 和 `eval/reports/phase3a-challenge-baseline.md`
   先看顶部总览表，快速定位 formal 8/10、challenge 11/16 和关键 `missing_column` / `missing_table`；再往下看 Case Details 里的 SQL。阅读重点不是“旧链路怎么修”，而是理解旧链路在哪些多表场景已经能 join、在哪些输出契约上还不稳定。

一次 M8 baseline 的数据流向：

`phase3a-regression.yaml / database-upgrade-challenge.yaml`
→ `EvalCase`
→ `TestClient POST /api/query`
→ 旧 SQL 链路 `AgentResponse`
→ `EvalScore(issue_tags)`
→ `EvalResult`
→ `phase3a-baseline.md / phase3a-challenge-baseline.md`

**模块闭环**：M8 把 Phase 3A 从“准备做优化”推进到“已有旧链路对照样本”。后续 M9 做 Schema Retrieval、M10 做 QueryPlanStep、M11 做新 pipeline、M12 做对照报告时，都可以拿 10 条 formal baseline 和 16 条 challenge baseline 做参照。

### 设计要点

- **不美化旧链路**：允许类 SQL 只有 6/8 通过，低于计划门槛；用户确认后仍按真实 baseline 冻结。这比为了好看改 case 更有工程价值。
- **两个题本分层**：10 条 formal 是主硬门，16 条 challenge 是 superset 诊断门。这样既有稳定验收尺子，又能观察困难 SQL 的改进空间。
- **前向兼容，不破坏旧 smoke**：`expected_metrics / expected_trace_steps / pipeline_mode` 都有默认值，所以 M6 的 `smoke.yaml` 仍然 6/6 通过。
- **issue tags 只做最小集合**：M8 不扩展完整 EvalOps，不做复杂 SQL 语义判等，只先落 `missing_table / missing_column / safety_mismatch / unexpected_error`，服务后续新旧对照。
- **manual review 先轻量实现**：M8 只标记困难题需要复核，不要求 trace_steps 完整；真正 diagnostic 语义留给 M11/M12。
- **M8 不提前做新 pipeline**：`expected_trace_steps` 只是可加载字段，真正 trace_steps 结构仍在 M11；这能保持模块边界清楚。

### 面试怎么讲

M8 可以讲成“我在 Text2SQL 深化前先做了一个真实 baseline 冻结”。我没有一上来就改 prompt，而是先把 10 条 formal regression 和 16 条 challenge 跑在旧链路上，报告里记录 SQL、trace_id、安全状态、issue tag 和 manual review 标记。结果显示旧链路 formal 8/10，challenge 11/16，安全 2/2 能拦截，但 formal 允许类 SQL 只有 6/8，失败集中在多表输出列契约。这说明后续 Schema Retrieval 和 QueryPlanStep 的目标不是抽象地“更智能”，而是要针对可观测失败点提升选表、指标口径和输出结构稳定性。

### 验证与下一步

- 验证：TDD 红灯先失败于 M8 字段、结构化 score 和 manual review 缺失；实现后 `tests/test_phase3a_eval.py` **7 passed**；旧 `smoke.yaml` **6/6 passed**；Phase 3A formal baseline **8/10 passed**，安全 **2/2 blocked**，允许类 SQL **6/8 passed**；challenge baseline **11/16 passed**，安全 **2/2 blocked**。
- warning：Starlette TestClient / httpx deprecation 是既有 warning，不影响 M8；Windows CRLF 提示仍为既有换行提示。
- 下一步：用户人工检查后可运行 `accept-module` 做 M8 最终验收；通过后进入 M9 Schema Retrieval 与 JoinPath。

可复制验证命令：

```powershell
# 跑 M8 eval 契约测试。预期：7 passed，可能有既有 TestClient warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8-tmp

# 跑旧 M6 smoke 兼容验证。预期：passed=6/6。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval/cases/smoke.yaml --report .agent_work/temp/m8-smoke-compat.md --trace .agent_work/temp/m8-smoke-compat-traces.jsonl

# 生成 Phase 3A 旧链路 baseline。预期：passed=8/10；安全 2/2 blocked；允许类 SQL 6/8。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-baseline.md --trace .agent_work/temp/phase3a-baseline-traces.jsonl

# 生成 Phase 3A challenge baseline。预期：passed=11/16；安全 2/2 blocked；困难诊断失败带 review_required。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --report eval/reports/phase3a-challenge-baseline.md --trace .agent_work/temp/phase3a-challenge-baseline-traces.jsonl
```

**本地启动体验：**

本模块暂无新的交互页面；它的交互方式是评测报告。运行上面的 baseline 命令后，打开 `eval/reports/phase3a-baseline.md` 和 `eval/reports/phase3a-challenge-baseline.md`，可以看到每条 case 的 pass/fail、review_required、issue tag、trace_id 和实际 SQL。这两个报告就是后续 M12 新旧链路对照的旧链路输入。

## ★ M8.5 Diagnostic Benchmark 骨架与旧链路诊断基线（2026-07-23）

**简述**：这次把 Phase 3A 的诊断评测从 16 条 challenge 扩成 **32 条 diagnostic benchmark**，像给后续 Text2SQL 改造装了一块更细的仪表盘。

### 这次做了什么

M8 已经回答了“旧链路在 10 条 formal 和 16 条 challenge 上表现如何”，但它还不够说明“后续新链路到底在哪些能力上进步”。M8.5 做的就是补这层诊断骨架：保留 `database-upgrade-challenge.yaml` 作为 **16 条 challenge 唯一源**，新建 `phase3a-diagnostic-benchmark.yaml` 只写新增 **16 条 capability-focused case**，然后让 runner 通过 `--cases + --extra-cases` 拼成 32 条。

runner 也做了最小扩展：每条结果记录 `source_file`、`configured_pipeline_mode`、`actual_pipeline_mode`，报告里增加 **capability summary**、blocking/non-blocking 统计、skipped 和 review_required。旧链路无法验证的 plan / trace / local schema 检查不会被硬判失败，而是标成 **skipped_due_to_pipeline_mode**，这样报告既诚实，又不会把“能力还没实现”和“旧链路答错了”混成一团。

真实旧链路 diagnostic baseline 是：**32 条 total，12 passed，10 failed，10 skipped，3 review_required**。这不是为了追求好看的分数，而是给 M9-M12 留一份可对照的失败地图。

### 新概念

- **Diagnostic Benchmark**：不是普通“多问几道题”，而是按能力维度设计的评测集。它关心的是 **schema_retrieval、join_path、query_plan、local_schema_prompt、trace_steps、security_guard** 分别有没有证据。
- **source_file**：记录一条 case 来自哪个 YAML。因为 32 条不是复制到一个大文件，而是由 **challenge 16 + extra 16** 组合出来的，来源字段可以防止以后找错维护位置。
- **configured_pipeline_mode / actual_pipeline_mode**：case 自己推荐用什么链路是一回事，runner 实际用什么链路是另一回事。M8.5 用旧链路跑 baseline，所以很多 extra case 的 configured 是 `new_text2sql`，actual 是 `baseline`。
- **skipped_due_to_pipeline_mode**：旧链路没有 QueryPlan、局部 Schema 和 trace_steps，不能假装这些检查通过，也不应该把它们当失败。skip 是一种更诚实的诊断状态。

### 关键文件

- `eval/cases/phase3a-diagnostic-benchmark.yaml`：新增 16 条 extra case，只维护 proposal v5 的 capability-focused 题。
- `eval/cases/database-upgrade-challenge.yaml`：16 条 challenge 唯一源，本次只补 capability / blocking 等诊断元数据。
- `eval/run_eval.py`：支持 `--extra-cases`、pipeline mode 覆盖、skip 评分和 diagnostic Markdown 摘要。
- `tests/test_phase3a_eval.py`：守住 32 条合并、case id 唯一、linked case、多答案 case、skip 规则和报告字段。
- `eval/reports/phase3a-diagnostic-baseline.md`：旧链路跑 32 条 diagnostic 的真实 baseline。

### 代码阅读路线

1. **先看题本分层**：`eval/cases/database-upgrade-challenge.yaml` 和 `eval/cases/phase3a-diagnostic-benchmark.yaml`
   重点看两个文件的职责差异：challenge 文件继续维护前 16 条；diagnostic 文件只维护新增 16 条。新增 case 里可以重点读 `db_plan_001`、`db_schema_003`、`db_prompt_001` 和 `db_trace_001`，它们分别代表 **linked case、多答案、局部 Schema 分层和 trace step 完整性**。

2. **再看加载入口**：`eval/run_eval.py`
   从 `load_cases()` 读起。它把主文件和 extra 文件按顺序合并，并用 case id 去重。这里的关键设计是 **显式组合，而不是隐式 includes**：运行命令里能直接看见 32 条由哪两个文件拼出来，后续维护不容易迷路。

3. **然后看评分边界**：`eval/run_eval.py`
   看 `_should_skip_due_to_pipeline_mode()` 和 `_score_case()`。前者专门判断旧 baseline 无法验证的新链路检查；后者仍保留 M8 的轻量结果层评分。重点理解这里不是完整 scorer，而是给 M12 对照报告准备稳定状态。

4. **最后看报告输出**：`eval/run_eval.py` 和 `eval/reports/phase3a-diagnostic-baseline.md`
   `write_report()` 会先写总览，再写 blocking summary、capability summary 和 case summary。读报告时先看 capability summary，再看 `db_sec_003 / db_sec_004` 这类失败明细，它们说明旧链路在哪些安全意图上还不能稳定触发 SQL Guard。

32 条 diagnostic baseline 的数据流向：

`database-upgrade-challenge.yaml + phase3a-diagnostic-benchmark.yaml`
→ `EvalCase(source_file, capabilities, pipeline_mode)`
→ baseline `/api/query` 或 skip
→ `EvalScore`
→ `EvalResult(actual_pipeline_mode)`
→ `phase3a-diagnostic-baseline.md`

### 设计要点

- **不复制 challenge 16 条**：复制会制造第二份真相，后续改一个问题可能漏另一个文件。M8.5 选择多文件组合，让维护边界更干净。
- **skip 不是失败也不是通过**：QueryPlan、local schema、trace_steps 还没实现时，旧链路只能告诉我们“这类检查当前不可验证”。这比把新能力虚报成失败/通过都更稳。
- **challenge 补元数据，不改旧题**：为了让 32 条 capability summary 完整，本次给 challenge case 补了能力标签和 blocking 属性，但没有改问题、expected_sql、check，也没有重写 M8 baseline 报告。
- **报告继续是 Markdown**：M8.5 没有做 HTML、历史库或复杂 scorer。它先把最小结构跑通，完整 EvalOps 平台仍留给后续独立项目。

### 面试怎么讲

M8.5 可以讲成“我没有等新 pipeline 写完才想怎么评估，而是先把诊断基准设计落地”。我把原来的 16 条 challenge 和新增 16 条 capability case 组合成 32 条 benchmark，并在 runner 里区分 configured pipeline 和 actual pipeline。旧链路不能验证 QueryPlan、local schema、trace_steps 时，我没有把它们算失败，而是标记 skipped；同时报告按 capability 汇总，能清楚看到旧链路在 schema_retrieval、join_path、query_plan、安全边界上的真实状态。这能体现我做 Agent / Text2SQL 项目时，不只是写 prompt，而是会先设计可复现、可诊断、可对照的评测闭环喵

### 验证与下一步

- 验证：`tests/test_phase3a_eval.py` **13 passed**；旧 smoke 兼容 **6/6 passed**；全量 pytest **44 passed**；diagnostic baseline **12/32 passed、10 failed、10 skipped、3 review_required**。
- warning：Starlette TestClient / httpx deprecation 是既有 warning；`git diff --check` 只有 Windows LF→CRLF 提示。
- 下一步：用户人工检查后可调用 `accept-module` 验收 M8.5；通过后进入 M9 Schema Retrieval 与 JoinPath。

可复制验证命令：

```powershell
# 跑 M8.5 eval 契约测试。预期：13 passed，可能有既有 TestClient warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-tmp

# 生成 32 条 diagnostic 旧链路 baseline。预期：total=32，passed=12，failed=10，skipped=10。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode baseline --cases eval/cases/database-upgrade-challenge.yaml --extra-cases eval/cases/phase3a-diagnostic-benchmark.yaml --report eval/reports/phase3a-diagnostic-baseline.md --trace .agent_work/temp/phase3a-diagnostic-baseline-traces.jsonl

# 跑全量回归。预期：44 passed，可能有既有 TestClient warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-full
```

**本地启动体验：**

本模块暂无新的 Swagger 或前端页面；它的交互入口是评测报告。运行 diagnostic baseline 命令后，打开 `eval/reports/phase3a-diagnostic-baseline.md`，先看顶部 total / passed / failed / skipped，再看 **Capability Summary**，最后挑几条 Case Details 看实际 SQL 和 issue tag。这个报告就是后续 M12 新旧链路对照的旧链路诊断输入。

## ★ M9 Schema Retrieval 与 JoinPath（2026-07-23）

**简述**：这次给 Text2SQL 新链路加上 **Schema Retrieval**，让系统先查“数据字典和关系图”，再进入后续 QueryPlan / SQL 生成。

### 这次做了什么

M8/M8.5 已经冻结了旧链路 baseline，M9 开始真正搭 Text2SQL 中间层的第一块：把 `domain_pack/` 里的表字段、指标口径和表关系整理成可检索文档。现在系统能生成三类 Schema 文档：**字段文档 field_doc** 说明字段（用户问的'渠道名'对应哪个表的哪个列？），**指标文档 metric_doc** 说明 GMV / 退款率 / 净收入等指标（用户说'销售额'指的是 `gmv` 还是 `item_gmv`？公式是什么？），**关系文档 relation_doc** 说明表之间怎么 join（要查订单和渠道，两张表该怎么 JOIN？有没有桥表）。

检索链路分两路：一条是 **keyword retrieval**，用中文业务词、英文表字段名和指标别名做关键词命中；另一条是 **deterministic in-memory vector index**，用不联网的确定性稀疏向量模拟向量召回接口。用户已确认 M9 先不接真实 Milvus，所以本模块只保留 Milvus adapter 边界，不新增 Docker 或 `pymilvus` 依赖。

最后，M9 会把召回结果整理成 **SchemaGraph**：包含当前问题相关的表、字段、指标和 **JoinPath**（**通俗：**从全量 Schema 中剪裁出当前问题相关的部分）。JoinPath 严格来自 `relations.yaml`，不让模型临时猜 join 条件。本次还补齐了退款相关的结构化关系：`refunds_order`、`refunds_product`、`refunds_user`，它们原本已经写在 `refunds.md`，只是没有进入集中关系 YAML。

真实结果是：8 条 formal allow case 的 expected_tables **15/15 命中**，字段/指标 **16/18 命中**，3 个 formal 多表 case 的 JoinPath **3/3 生成**；32 条 diagnostic 中 schema/join 相关 24 条的 expected_tables **54/54 命中**，JoinPath **14/14 生成**。

### 新概念

- **Schema Retrieval**：可以理解为 Text2SQL 之前先查一遍“数据字典”。用户问“渠道 GMV”，系统先召回 `orders`、`channels`、`gmv`、`orders_channel` 这些上下文，后续 LLM 才不用面对全库所有表字段。
- **field_doc / metric_doc / relation_doc**：三类文档分别回答“有什么字段”“指标怎么算”“表怎么连”。这比把所有 schema 塞进 prompt 更可控，也方便评测哪一类知识没召回。
- **VectorIndex 协议**：M9 先用内存索引跑通接口，后续真实 Milvus 只要实现同样的 `search()` 契约即可。它类似 Java 里先定义 interface，再换不同实现。
- **SchemaGraph**：当前问题的小型 Schema 视图。它不是全局图数据库，只是把本次问题需要的表、字段、指标和关系收在一起。
- **JoinPath**：从一张表走到另一张表的连接路径。例如优惠券渠道题需要 `orders -> order_coupons -> coupons` 和 `orders -> channels`。M9 的原则是 **Join 条件只能来自 relations.yaml**。

### 关键文件

- `engine/schema_retrieval/objects.py`：定义 `SchemaDocument`、`SchemaHit`、`SchemaGraph`、`JoinPath` 等核心结构。
- `engine/schema_retrieval/document_builder.py`：把 `DomainSchema`、`metrics.yaml`、`relations.yaml` 构造成三类检索文档。
- `engine/schema_retrieval/vector_index.py`：提供 `EmbeddingProvider`、deterministic in-memory vector index 和 Milvus adapter 占位。
- `engine/schema_retrieval/retriever.py`：实现 keyword + vector 两路召回和简单融合。
- `engine/schema_retrieval/graph.py`：把命中文档转成局部 SchemaGraph，并从 relations 图里找 JoinPath。
- `tests/test_phase3a_schema_retrieval.py`：M9 的验收测试，覆盖文档类型、召回结构、formal 命中率和 diagnostic JoinPath。
- `domain_pack/schema_desc/relations.yaml`：集中关系源，本次补齐退款相关关系。

### 代码阅读路线

1. **先看结构定义**：`engine/schema_retrieval/objects.py`
   重点看 `SchemaDocument` 和 `SchemaHit`。前者是“被检索的知识块”，后者是“某个问题命中了哪个知识块、分数多少、来自 keyword 还是 vector”。再看 `SchemaGraph` 和 `JoinPath`，理解 M9 给后续模块交付的不是 SQL，而是 **局部上下文**。

   **通俗：**流程就是：`build_schema_documents()` 造一堆书 → 写入 Milvus → 用户提问 → Milvus 返回一摞带了分数的 `SchemaHit` → `build_schema_graph()` 把这些 hit 拼成 `SchemaGraph`。

2. **再看文档构建**：`engine/schema_retrieval/document_builder.py`
   从 `build_schema_documents()` 读起。它先遍历表字段生成 field_doc，再遍历 `metrics.yaml` 生成 metric_doc，最后读取 `relations.yaml` 生成 relation_doc。阅读重点是 **领域知识仍来自 domain_pack**，代码只负责整理和轻量别名扩写。

3. **然后看召回执行**：`engine/schema_retrieval/retriever.py` 和 `engine/schema_retrieval/vector_index.py`
   `retrieve_schema()` 会先跑关键词召回，再跑内存向量召回，最后 `_merge_hits()` 做简单融合。这里不用深抠向量数学，重点理解当前 in-memory index 是 **测试替身和接口占位**，不是宣称生产级 Milvus 已完成。

4. **最后看关系成图**：`engine/schema_retrieval/graph.py`
   `build_schema_graph()` 会从命中结果收集表、指标和 relation，然后在 `relations.yaml` 构成的无向图里找最短路径。重点理解这里的安全边界：**没有登记过的关系不会被编出来**，缺关系就补 YAML，而不是放给 LLM 猜。

5. **用测试反推验收门**：`tests/test_phase3a_schema_retrieval.py`
   这份测试最适合确认 M9 做到什么程度。先看三类文档测试，再看 keyword/vector 返回结构，最后看 formal 8 条和 diagnostic 24 条的命中统计。它能帮你分清 M9 的职责是 **召回上下文**，不是生成 QueryPlan 或 SQL。

M9 的数据流向：

`schema_desc/*.md + metrics.yaml + relations.yaml`
→ `SchemaDocument`
→ `keyword_hits + vector_hits`
→ `merged_hits`
→ `SchemaGraph`
→ `JoinPath`
→ M10 `QueryPlanStep`

### 设计要点

- **Milvus 先保边界，不接真实服务**：这是用户确认后的方案 A。M9 不新增依赖、不启动 Docker，避免环境问题阻塞核心结构；后续接 Milvus 时复用 `EmbeddingProvider` / `InMemoryVectorIndex` 的接口。
- **关系单一事实源收敛到 relations.yaml**：Markdown 可以解释关系，但 JoinPath 的结构化判断只读 `relations.yaml`。这让后续 plan validation 能稳定判断 join 是否合法。
- **不伪造派生列**：`coupon_order_count`、`conversion_rate`、`avg_price` 这类是 SQL 输出别名，不是物理字段。M9 不把它们硬塞进 schema，后续 M10/M11 通过 QueryPlan 和 SQL alias 处理。
- **M9 先保证 recall，M11 再精简 prompt**：当前 `SchemaGraph` 会补齐命中表的字段，目的是让 expected_columns 命中率先达标；局部 Schema prompt 的噪音控制留给 M11。

### 面试怎么讲

M9 可以讲成“我给 Text2SQL 增加了字段级 Schema Retrieval 和结构化 JoinPath”。用户问题进来后，系统不会直接把全库 schema 塞给 LLM，而是先从 domain pack 生成 field_doc、metric_doc、relation_doc，再用 keyword + vector 两路召回当前问题相关的表、字段、指标和关系。多表查询不让模型自由猜 join，而是从 relations.yaml 找 JoinPath；如果关系缺失，就补结构化关系源。自动化结果是 formal 允许类 SQL 的表召回 15/15，字段指标 16/18，多表 JoinPath 3/3，为后续 QueryPlanStep 和局部 Schema SQL prompt 打了一个可验证的基础喵

### 验证与下一步

- 验证：M9 聚焦测试 **6 passed**；相关 eval + schema 测试 **19 passed**；全量 pytest **50 passed**；`git diff --check` 无 whitespace error。
- warning：Starlette TestClient / httpx deprecation 是既有 warning；`relations.yaml` 有 Windows LF→CRLF 提示，不影响本模块。
- 下一步：用户人工检查后可调用 `accept-module` 验收 M9；通过后进入 M10 QueryPlanStep 与自检。

可复制验证命令：

```powershell
# 跑 M9 聚焦测试。预期：6 passed，可能有既有 TestClient warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-tmp

# 跑相关 eval 回归。预期：19 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-related

# 跑全量测试。预期：50 passed，耗时约 3 分钟。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-full-rerun

# 检查 whitespace。预期：无 whitespace error，可能出现 Windows LF->CRLF 提示。
git diff --check
```

**本地启动体验：**

本模块暂无新的 Swagger 或前端页面；它是后端 Text2SQL 中间层能力。学习时可以先跑上面的 M9 测试，再打开 `tests/test_phase3a_schema_retrieval.py` 看每个断言：它会告诉你哪些中文问题召回了哪些表、字段、指标和 JoinPath。后续 M10/M11 会把这块能力接到 QueryPlan 和新 pipeline 里。

## ★ M9.1 / M9.2 可选 Milvus + SiliconFlow Embedding（2026-07-23 ~ 2026-07-24）

**简述**：这两次实验已经合并进主线：DataPilot 现在 **默认仍用 in-memory 检索**，同时 **可选支持 Milvus + SiliconFlow 真实中文 embedding**。

### 这次做了什么

M9 验收后，我们先做了 M9.1：验证 **Milvus 作为 Schema Retriever 的向量存储** 是否能跑通。它做的事情很单纯：把 M9 的 `VectorIndex` 接口换一个实现，默认链路不变，显式传入 `MilvusVectorIndex` 时才会连接 Docker Milvus。实验结果证明 Milvus adapter 能正常建 collection、写入 schema document 向量、flush、load、search。

随后做 M9.2：把 M9.1 里的 fake embedding 换成 **SiliconFlow 真实中文 embedding**。这次测试了 **BAAI/bge-m3** 和 **Qwen/Qwen3-Embedding-0.6B**，并把报告拆成两个视角：**merged_top30** 看当前系统最终召回效果，**vector_only_top12** 看 embedding 模型自己的排序能力。

最后用户确认把这套能力合入主线，但合入方式是 **optional capability**：主线代码里有 Milvus adapter、SiliconFlow provider 和 smoke 脚本；默认 `retrieve_schema()` 仍然走 in-memory，不要求 Docker Milvus、不要求联网 API、不消耗余额。

合并后的口径是：

- **默认开发 / pytest / M10 主线**：继续用 in-memory，稳定、离线、可复现。
- **需要验证真实向量检索或 RAG 前准备**：显式运行 Milvus / SiliconFlow smoke。
- **不要把每个模块都跑两遍**：只有改到 schema retrieval、embedding、Milvus adapter、召回融合时，才需要同时跑默认路径和 Milvus 路径。

### 实验结论

M9.1 的结论是：**Milvus adapter 可用，但只换存储不提升召回质量**。在 deterministic fake embedding 下，Milvus 与 in-memory 的召回数字完全一致：formal 表命中 **15/15**、字段/指标 **16/18**、JoinPath **3/3**；diagnostic schema/join 表命中 **54/54**、字段/指标 **54/62**、JoinPath **14/14**。

M9.2 的结论更有价值：**真实 embedding 的向量排序能力更好，但当前最终 hard recall 没提升**。在 `merged_top30` 下，BGE-M3 和 Qwen3 都与 M9 持平，说明 M9 的 keyword + relations.yaml 已经把当前硬门补满；在 `vector_only_top12` 下，Qwen3-0.6B 明显更强，diagnostic item recall 从 fake 的 **47/62** 提到 **55/62**，JoinPath 从 **13/14** 提到 **14/14**。

所以这不是“Milvus / embedding 没用”，而是：**当前 Text2SQL 的 M10/M11 瓶颈不在向量库，而在 QueryPlan、派生列 alias 和 SQL 生成约束**。Milvus + Qwen3 更适合后续 RAG、文档量变大、schema 变复杂、或需要更强语义检索时启用。

### 新概念

- **Milvus**：专门存储和检索向量的数据库，可以理解成“给 embedding 用的检索库”。它成熟、适合生产，但本地开发要多一个 Docker 服务。
- **联网 embedding**：把文本发给外部模型 API，让模型返回一串语义向量。它和 DeepSeek API 一样都是外部服务，只是 DeepSeek 用来生成 SQL，embedding API 用来做检索。
- **Optional capability**：能力已经在主线代码里，但默认不开。这样既能支持真实 Milvus / embedding，又不会让普通 pytest、M10 开发、离线环境被外部服务绑定。
- **merged_top30**：当前 M9 的实际主策略，综合 keyword、vector 和 relation。它代表“最终给后续模块看的上下文”。
- **vector_only_top12**：只看向量召回能力。它更适合判断 embedding 模型本身强不强。
- **Dense Vector**：Milvus 的 `FLOAT_VECTOR` 需要固定长度数字数组。fake embedding 会用 SHA1 稳定 hash 映射成 dense vector；真实 embedding 则直接返回 dense vector。

### 关键文件

- `engine/schema_retrieval/vector_index.py`：定义 `VectorIndex` 协议、in-memory index、Milvus adapter 和 dense vector 处理。
- `engine/schema_retrieval/embedding_provider.py`：SiliconFlow embedding provider，支持 batch、cache、Qwen3 `dimensions`。
- `engine/schema_retrieval/retriever.py`：`retrieve_schema()` 支持显式注入 vector index；不注入时默认 in-memory。
- `tests/test_m9_1_milvus_schema_retrieval.py`：Milvus 可用时验证 adapter 和 retriever 集成。
- `tests/test_m9_2_siliconflow_embedding.py`：用 fake transport 测 provider，不联网、不消耗 API 额度。
- `scripts/smoke_m9_1_milvus.py`：in-memory vs Milvus fake embedding 对比。
- `scripts/smoke_m9_2_real_embedding.py`：in-memory / Milvus fake / Milvus SiliconFlow 对比。

### 代码阅读路线

1. **先看默认仍不变**：`engine/schema_retrieval/retriever.py`
   `retrieve_schema()` 只有在调用方显式传入 `vector_index` 时才会走 Milvus。没传时仍创建 `InMemoryVectorIndex`。这是合并后的核心安全边界：**主线支持 Milvus，但默认不依赖 Milvus**。

2. **再看向量索引接口**：`engine/schema_retrieval/vector_index.py`
   从 `VectorIndex` 协议看起，再看 `InMemoryVectorIndex` 和 `MilvusVectorIndex`。重点理解它们对外都是 `search(query, top_k)`，所以后续换 Milvus、Qdrant 或别的向量库时，不需要重写上层 retriever。

3. **然后看真实 embedding provider**：`engine/schema_retrieval/embedding_provider.py`
   `SiliconFlowEmbeddingProvider.embed_texts()` 会组装 `/embeddings` 请求、按 index 还原向量顺序，并用 `_cache` 避免一次 smoke 中重复扣费。这里要记住：它是 **显式 smoke / 后续 RAG 用的 provider**，不是默认 pytest 入口。

4. **最后看两个 smoke**：`scripts/smoke_m9_1_milvus.py` 和 `scripts/smoke_m9_2_real_embedding.py`
   第一个回答“Milvus adapter 能不能跑”，第二个回答“真实 embedding 是否让召回更好”。读报告时重点看 `merged_top30` 和 `vector_only_top12` 的差异。

合并后的两条使用路径：

`默认路径`
→ `retrieve_schema()`
→ `InMemoryVectorIndex`
→ `SchemaGraph / JoinPath`
→ M10/M11

`可选真实向量路径`
→ `SiliconFlowEmbeddingProvider`
→ `MilvusVectorIndex`
→ `retrieve_schema(vector_index=real_index)`
→ smoke 对比 / 后续 RAG

### 设计要点

- **合入能力，不切默认**：Milvus 和 SiliconFlow 都在主线可用，但默认路径仍离线可跑。这能兼顾简历技术栈和工程稳定性。
- **不要每个模块都双跑**：M10 QueryPlan 只消费 `SchemaGraph / JoinPath`，不需要关心它来自 in-memory 还是 Milvus。只有改检索层时才双跑。
- **Qwen3 优先级高于 BGE-M3**：在当前测试里，Qwen3-0.6B 的 vector-only 结果更好；后续如果继续做真实语义检索，优先试 Qwen3。
- **派生列不是 embedding 问题**：`coupon_order_count`、`conversion_rate`、`avg_price` 是 SQL 输出别名或计划层概念，应该在 M10 QueryPlan 和 M11 SQL prompt 里解决。

### 面试怎么讲

M9.1/M9.2 可以合起来讲成“我把 Schema Retrieval 做成了可插拔向量检索架构”。默认路径用 in-memory 保证测试稳定，真实路径支持 Milvus + SiliconFlow embedding，并用 formal / challenge / diagnostic case 做效果对比。实验发现 Qwen3 embedding 在向量单路召回上明显优于 fake embedding，但当前最终 merged recall 已经被 keyword + relations.yaml 补满，所以我没有盲目把默认链路切到联网服务，而是把它作为 optional capability 合入主线，等 RAG 或更大规模 schema 检索时启用喵

### 验证与下一步

- 验证：M9.1/M9.2 合并后全量 pytest **54 passed**；`git diff --check` 无 whitespace error。
- 真实 smoke：BGE-M3 和 Qwen3-0.6B 均调用成功；首次联网 smoke 在沙箱中遇到 `WinError 10013`，提权后正常。
- warning：Starlette TestClient / httpx deprecation 是既有 warning；运行 Milvus / embedding smoke 建议设置 `OPENBLAS_NUM_THREADS=1`。
- 下一步：主线直接进入 M10 QueryPlanStep；M10 默认使用 in-memory 召回结果即可。

可复制验证命令：

```powershell
# 默认主线验证。预期：全量通过，不联网，不要求 SiliconFlow。
$env:OPENBLAS_NUM_THREADS='1'
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9_2-merged-full

# 只验证 Milvus adapter。需要 Docker Milvus 已启动。
$env:OPENBLAS_NUM_THREADS='1'
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_m9_1_milvus.py

# 验证真实 embedding + Milvus。需要 Docker Milvus 和 SILICONFLOW_API_KEY。
$env:OPENBLAS_NUM_THREADS='1'
$env:SILICONFLOW_EMBEDDING_MODEL='Qwen/Qwen3-Embedding-0.6B'
$env:SILICONFLOW_EMBEDDING_DIMENSIONS='1024'
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_m9_2_real_embedding.py
```

**本地启动体验：**

本章节没有 Swagger 页面；它的体验方式是对比报告。日常开发不需要启动 Milvus，也不需要调用 SiliconFlow。只有想验证真实向量检索时，才启动 Docker Milvus，并运行 `scripts/smoke_m9_2_real_embedding.py`。报告会写到 `.agent_work/temp/`，重点看 `merged_top30` 判断当前系统是否受益，看 `vector_only_top12` 判断 embedding 模型本身是否更强。

## ★ M10 QueryPlanStep 与自检（2026-07-24）

**简述**：M10 给 Text2SQL 加了一个 **SQL 生成前的结构化计划层**，像后端接口里的 DTO + Validator，先检查“准备查什么”是否合法，再交给后续 SQL 生成。M9 已经把问题相关的表、字段、Join 召回出来了，但如果让 LLM 直接拿着这些信息写 SQL，它仍可能编造不存在的字段、乱连表、或者在 SQL 里偷查敏感数据——这在代码里叫"幻觉"，在企业里叫"事故"。M10 的做法是：在 LLM 写 SQL 之前，先让它填一张"申请表"（QueryPlanStep），写明要查哪些表、用哪些字段、按什么 Join 条件、输出什么列；填完后系统逐项核对这张申请表是否都在 M9 的合法"菜单"里。整个过程相当于后端接口收到请求后先做参数校验——没通过就不往下走，通过了才交给 M11 生成 SQL。

### 这次做了什么

M9 已经能把问题相关的表、字段、指标和 JoinPath 召回出来，但如果直接让模型拿这些上下文生成 SQL，中间仍有一个黑盒风险：模型可能编造不存在字段、乱连 Join、或者在 SQL 生成前就计划查询敏感字段。

M10 做的就是在这个位置加一道 **QueryPlan 自检门**。模型后续会先输出 `QueryPlan(steps=[QueryPlanStep])`，每个 step 必须写清楚要用哪些表、字段、指标、过滤条件、Join relation id 和输出列。`validate_query_plan()` 会把这些内容逐项对照 M9 的 `SchemaGraph` 和 `DomainSchema`：不存在的表字段会被打 `missing_table / missing_column`，非法 Join 会被打 `invalid_join_path`，多个可执行 SQL step 会被打 `unsupported_multi_step_plan`，普通角色查询 `users.email` 这类敏感字段会提前打 `sensitive_field_access`。

这层还刻意保留了未来扩展空间：`QueryPlan.steps` 是列表，`step_id / step_index / depends_on` 可以接后续 Plan-and-Execute；但 **Phase 3A 只允许一个 `sql_query` step**。也就是说，结构可以长远，执行边界仍然收紧。

### 新概念

- **QueryPlanStep**：一次查询计划里的一个步骤。可以理解成 SQL 生成前的“施工单”：写明要查哪些表、用哪些字段、按什么指标聚合、需要哪些 Join。
- **Plan Validation**：计划自检。它不是执行 SQL，而是检查计划引用的东西是否都在可信 Schema 里，类似 SpringBoot Controller 收到请求后先做参数校验。
- **CoT 不外露**：M10 不保存 `thoughts` 或原始推理过程，只保留 `purpose` 这种一句话意图摘要。这样既能调试，又不会把模型自由推理塞进公开响应。
- **Join relation id**：Join 不靠自然语言猜，而是使用 `relations.yaml` 里的关系 ID，例如 `order_items_order`。这让“能不能这么连表”变成可校验事实。
- **unsupported_multi_step_plan**：当前阶段的边界标签。系统知道未来可能有多 SQL、多步骤分析，但 M10-M12 不执行这种计划。

### 关键文件

- `engine/nl2sql/planner.py`：M10 主角文件，定义 `QueryPlanStep`、`QueryPlan`、`PlanValidationResult` 和 `validate_query_plan()`。
- `engine/nl2sql/prompt.py`：新增 `build_query_plan_prompt()`，把局部 Schema、指标、JoinPath 和 Pydantic JSON Schema 组装给 LLM。
- `engine/nl2sql/generator.py`：新增 `extract_query_plan()`，从 LLM 原始输出中解析 JSON / fenced JSON。
- `tests/test_phase3a_planner.py`：M10 的行为规格，覆盖合法计划、缺表缺字段、非法 Join、敏感字段和多 SQL step。

### 代码阅读路线

1. **计划结构**：`engine/nl2sql/planner.py`
   先看 `QueryPlanStep` 的字段。重点理解它不是 SQL AST，而是 **业务层可读的查询意图结构**：表、字段、指标、过滤、Join、聚合和输出列都拆成列表，方便校验和 trace。`QueryPlan.steps` 是列表，但 validator 会限制 Phase 3A 只能有一个可执行 SQL step。**通俗：**`QueryPlanStep` 就是一个**步骤的结构体**——把一个查询步骤"长什么样"用字段定死了：

2. **自检入口**：`engine/nl2sql/planner.py`
   然后看 `validate_query_plan()`。它先检查多 SQL step，再调用 `_check_table_and_column_scope()`、`_check_metric_scope()`、`_check_join_scope()` 和 `_check_sensitive_fields()`。阅读重点是：**planner 只做 SQL 前诊断，不替代 SQL Guard**。

3. **Prompt 生成**：`engine/nl2sql/prompt.py`
   看 `build_query_plan_prompt()`。它用 `query_plan_prompt_schema()` 把 Pydantic Schema 自动变成 JSON 格式说明，再拼上 M9 的局部表字段、局部指标和 JoinPath。这样后续改字段时，不需要手写两份示例。

4. **LLM 输出解析**：`engine/nl2sql/generator.py`
   看 `extract_query_plan()` 和 `_extract_json_object()`。它只兼容 JSON、fenced JSON 和前后有短解释的 JSON；完全不可解析就抛 `QueryPlanExtractionError(issue_tag="invalid_query_plan")`，不降级回自由文本 SQL。

数据流可以这样记：

`SchemaGraph / JoinPath`
→ `build_query_plan_prompt()`
→ `extract_query_plan()`
→ `validate_query_plan()`
→ M11 SQL 生成 / trace_steps

### 设计要点

- **结构预留，执行收紧**：`steps` 支持未来多步骤，但当前多个 `sql_query` step 直接拦截，避免 M10 偷偷变成多 SQL Agent。
- **不用 CoT 当契约**：计划校验依赖表、字段、指标、Join 这些结构化字段，而不是模型的自由推理文本。
- **Join 来自关系事实源**：`joins` 使用 relation id，和 M9 的 `relations.yaml` 对齐，不让模型自己发明连接条件。
- **敏感字段提前诊断**：planner 可以提前发现 `users.email`，但最终安全仍交给 SQL Guard，安全边界没有被 prompt 或 planner 替代。

### 面试怎么讲

M10 可以讲成“我在 Text2SQL 里加了一层可校验的中间表示”。普通 NL2SQL 是直接从问题到 SQL，失败时很难知道是 schema 召回错了、Join 错了，还是 SQL 生成错了；我把中间层拆成 `QueryPlanStep`，让模型先声明表、字段、指标和 Join，再用本地 validator 检查。这样后续 eval 可以打出 `missing_column / invalid_join_path / sensitive_field_access` 这类 issue tag，问题定位会比只看 SQL 错误清楚很多喵

### 验证与下一步

- 验证：M10 指定测试 **9 passed**；相关回归 **11 passed**；全量 pytest **63 passed**。
- warning：只有既有 Starlette TestClient / httpx deprecation warning，不影响 M10。
- 下一步：M11 把 QueryPlan 接进新 Text2SQL pipeline，补 `force_new_pipeline` 和 `trace_steps`。

可复制验证命令：

```powershell
# M10 指定验证。预期：9 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-tmp

# 相关回归。预期：M4 SQL 生成和 M9 Schema Retrieval 不被破坏。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m4_nl2sql.py tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-related

# 全量验证。预期：63 passed，可能出现既有 Starlette/httpx warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-full

# 检查 whitespace。预期：无 whitespace error，可能出现 Windows LF->CRLF 提示。
git diff --check
```

**本地启动体验：**

本模块暂无独立 Swagger 或页面入口，因为 M10 还没有接入 `/api/query`。学习体验建议直接读 `tests/test_phase3a_planner.py`：它就是一组可运行的小样例，展示合法计划如何通过，以及缺字段、非法 Join、敏感字段、多 SQL step 会怎样被拦截。M11 接入 pipeline 后，才会出现通过 API 强制走新 Text2SQL 链路的体验流程。

## ★ M11 新 Text2SQL Pipeline 与 Trace Steps（2026-07-24）

**简述**：M11 把 M9 的 **Schema Retrieval / JoinPath**、M10 的 **QueryPlanStep 自检** 和 M5 的 **SQL Tool / Trace** 串成了一条真正能从 `/api/query` 触发的新 Text2SQL 链路。

旧接口默认仍走模板优先，保证 M5/M6 演示不被破坏；评测或调试时传 `force_new_pipeline=true`，就会强制绕过模板，走 `schema_retrieval -> query_plan -> local_schema_sql -> sql_guard -> sql_execution`，并把每一步写进 JSONL 的 `trace_steps`。这一步的价值是让系统第一次具备“能证明自己走了新链路”的证据，而不只是报告里写了新链路。

### 这次做了什么

M10 做完后，DataPilot 已经能把“准备查什么”变成 QueryPlan，但还没有接到真实请求里。M11 做的就是把这条中间层真正串起来：API 收到请求后，如果 `force_new_pipeline=false`，旧模板链路照常工作；如果 `force_new_pipeline=true`，就进入 `run_text2sql_pipeline()`。

新 pipeline 会先召回**局部 Schema**，再构建 `SchemaGraph / JoinPath`，然后让 LLM 生成 **`QueryPlan`**，通过本地 validator 后再用局部 Schema prompt 生成 SQL。生成出来的 SQL 不会直接执行，而是统一交给 `run_sql_tool()`，继续经过 SQL Guard、RBAC 和敏感字段策略。执行成功后，结果会尝试生成图表；无图表也不影响 SQL 答案。

最重要的是：这条链路会把每一步写成 **`TraceStep`**，包括步骤名、顺序、类型、状态、耗时、错误类型和 metadata。后续 M12 做对照报告时，就能从 trace 里看见“到底走了哪些步骤、在哪一步失败、局部 Schema 有多少表字段、SQL 执行返回了几行”。

### 新概念

- **force_new_pipeline**：API 侧的显式开关。默认 `False` 保持旧模板优先；设为 `True` 才强制走新 Text2SQL pipeline。它像 SpringBoot 里一个只给灰度/评测用的开关，不改变普通用户默认路径。
- **pipeline_mode**：eval 侧的配置字段。`pipeline_mode=new_text2sql` 会让 runner 自动给 `/api/query` 发送 `force_new_pipeline=true`，避免报告写“新链路”，实际却跑旧模板。
- **TraceStep**：一次请求里的分步骤日志。它比 `tool_calls` 更细：`tool_calls` 只记录工具调用，`trace_steps` 会记录 schema 检索、计划生成、自检、SQL 生成、SQL Guard、SQL 执行和图表决策。
- **局部 Schema SQL prompt**：M11 不再把全库表字段都塞给 SQL 生成器，而是只给 QueryPlanStep 和 SchemaGraph 里出现的上下文。这样可以减少 prompt 噪音，也方便失败归因。
- **结构化 blocked**：新链路失败时不偷偷回到旧模板，也不自动修 SQL，而是返回 blocked 响应和 issue tag。这样对照报告会诚实暴露新链路质量。

### 关键文件

- `engine/nl2sql/pipeline.py`：M11 主角文件，负责编排新 Text2SQL pipeline 和生成 trace_steps。
- `engine/trace/recorder.py`：新增 `TraceStep`，并让 `TraceRecord` 支持 `trace_steps`。
- `app/schemas/agent.py`：给 `QueryRequest` 增加 `force_new_pipeline`。
- `app/api/query.py`：接入新 pipeline，同时保留默认模板优先旧路径。
- `engine/nl2sql/prompt.py`：新增 `build_local_schema_sql_prompt()`。
- `engine/nl2sql/generator.py`：新增 QueryPlan 生成和基于计划的 SQL 生成入口。
- `tests/test_phase3a_pipeline.py`：M11 的 API seam / trace seam / SQL Guard 回归测试。

### 代码阅读路线

1. **API 开关**：`app/schemas/agent.py` 和 `app/api/query.py`
   先看 `QueryRequest.force_new_pipeline`，再看 `query()` 里最前面的 M11 分支。重点理解：**旧请求完全不变**，只有显式传 true 才绕过模板。这样 M11 能给评测一个强制入口，又不会让 M5/M6 既有 demo 忽然变成依赖 LLM 的路径。

2. **Pipeline 编排**：`engine/nl2sql/pipeline.py`
   按 `run_text2sql_pipeline()` 的步骤注释读：Schema Retrieval、SchemaGraph、JoinPath、QueryPlan、Plan Validation、SQL Generation、SQL Guard、SQL Execution、Chart Decision。不要先抠每个 metadata 字段，先抓住主线：**每个业务阶段都对应一条 TraceStep**。

3. **局部 SQL prompt**：`engine/nl2sql/prompt.py`
   看 `build_local_schema_sql_prompt()`。它把 `QueryPlanStep`、局部表字段、局部指标和允许的 JoinPath 放在同一个 prompt 里，明确禁止编造表字段。这里的关键设计是：SQL 生成只消费已经检索和自检过的上下文。

4. **LLM 入口复用**：`engine/nl2sql/generator.py`
   看 `generate_query_plan()` 和 `generate_sql_from_plan_step()`。两个函数都复用同一个 `LLMClient` 协议，所以测试能用 fake client 替换真实 DeepSeek；真实运行时仍走已有配置。

5. **Trace 结构**：`engine/trace/recorder.py`
   看 `TraceStep` 的字段。`metadata` 放行数、列数、表数量、join relation id 等机器可读信息；`output_summary` 放人能快速读懂的摘要。这个分工很重要，避免把诊断字段写成一大段自由文本。

数据流可以这样记：

`/api/query(force_new_pipeline=true)`
→ `run_text2sql_pipeline()`
→ `retrieve_schema()`
→ `build_schema_graph()`
→ `generate_query_plan()`
→ `validate_query_plan()`
→ `generate_sql_from_plan_step()`
→ `run_sql_tool()`
→ `TraceRecord.trace_steps`

### 设计要点

- **默认不破坏旧链路**：模板优先仍是生产默认路径；新 pipeline 只在显式开关下触发。
- **证据写进 trace，不塞进响应体**：`trace_steps` 只进入 JSONL，避免公开 `AgentResponse` 变重，也不影响 demo 页面。
- **安全边界不前移成 prompt**：QueryPlan 和 prompt 可以减少错误，但 SQL Guard 才是最终门。测试里 fake LLM 返回 `DELETE FROM orders`，仍被 `sql_guard_blocked` 拦住。
- **失败不降级**：如果 schema 不足、plan 不合法、LLM 输出异常，新链路直接 blocked；这样 M12 对照报告不会被旧模板能力“兜底污染”。
- **结构预留多步骤，但当前只执行单 SQL**：`TraceStep.parent_step_id` 和 `step_type` 为未来 Plan-and-Execute 留口子，M11 不新增公开多步骤 Agent。

### 面试怎么讲

M11 可以讲成“我把 Text2SQL 从一条黑盒调用升级成可观测 pipeline”。以前用户问一句话，系统直接给 SQL，失败时很难知道错在 schema、计划、SQL 生成还是安全拦截；现在我把请求拆成 schema retrieval、schema context、join path、query plan、plan validation、sql generation、sql guard、sql execution 等步骤，并把每一步写进 trace。这样评测报告能基于证据定位问题，而不是只看最终 SQL 对不对。更重要的是，我没有为了新 pipeline 破坏旧接口，而是用 `force_new_pipeline` 做显式灰度开关，安全仍由 SQL Guard 兜底喵

### 验证与下一步

- 验证：M11 聚焦测试 **4 passed**；计划指定组合 **12 passed**；全量 pytest **67 passed**。
- warning：只有既有 Starlette TestClient / httpx deprecation warning，不影响 M11。
- 下一步：M12 跑 formal / challenge / diagnostic 新链路报告，生成新旧链路对照报告和 smoke 脚本。

可复制验证命令：

```powershell
# M11 聚焦验证。预期：4 passed，覆盖强制新链路、默认旧链路、eval 联动和 SQL Guard 拦截。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-tmp-3

# M11 计划指定验证。预期：12 passed，确认 M5 响应契约和 M4 NL2SQL 旧能力不破。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py tests\test_m5_agent_response.py tests\test_m4_nl2sql.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-related-2

# 全量验证。预期：67 passed，可能出现既有 Starlette/httpx warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-full-2

# 检查 whitespace。预期：无 whitespace error，可能出现 Windows LF->CRLF 提示。
git diff --check
```

**本地启动体验：**

M11 已经有 Swagger 体验入口，但强制新 pipeline 会调用真实 LLM，所以需要先配置 DeepSeek key。未配置 key 时，建议先用上面的 pytest fake LLM 测结构。

```powershell
# 启动 FastAPI。环境未激活时使用 AGENTS.md 里的完整 Python 路径。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/docs`，找到 `POST /api/query`，点 **Try it out**，填：

```json
{
  "question": "各渠道订单量是多少？",
  "user_role": "ops",
  "force_new_pipeline": true
}
```

点 Execute 后，响应体仍是原来的 `AgentResponse` 形状；分步骤证据写在 JSONL trace 里。真实 LLM 的 SQL 质量留到 M12 用批量报告评估，不建议只凭一次 Swagger 结果判断新链路效果。

## ★ M12 对照报告与阶段收尾（2026-07-25）

**简述**：M12 是阶段三A（Text2SQL 深化）的收尾模块，把 M8 冻结的**旧链路 baseline** 和 M11 实现的**新 Text2SQL pipeline** 并排对比，用数据证明新链路在 Schema 精简度、Trace 可观测性和 Issue Tag 归因方面的改进——同时如实记录 LLM 列名不稳定的真实瓶颈。不写新能力，**只做测量和收口**。

### 这次做了什么

阶段三A 的理想目标是：新 pipeline 换了 Schema Retrieval + QueryPlan + 局部 Schema Prompt 后，SQL 质量应该**不低于**旧链路的全量 schema prompt。M12 的职责就是**用同一批 10+16+32=58 条评测用例跑新旧两套链路**，把差异量化成 Markdown 对照报告。

实际执行时，发现三个需要在 M12 修复的 bug：

1. **DeepSeek 模型名过期**：DeepSeek API 把 `deepseek-chat` 改成了 `deepseek-v4-pro`，不修的话新 pipeline 所有 LLM 调用都 400 报错。这是环境依赖变化，不是 M11 代码错误。
2. **新 pipeline 安全预检缺失**：旧链路在模板未命中时会检查用户输入是否包含 `DROP`/`DELETE` 关键词并提前拦截；新链路的 `force_new_pipeline` 分支绕过了这个检查，导致"DROP TABLE orders"被 LLM 转写成"SELECT * FROM orders"后放行。补了一个预检，新旧行为一致。
3. **plan validation 误判聚合表达式**：`COUNT(DISTINCT orders.id)` 被当成了普通列名去数据库 schema 里查，当然找不到。修了校验逻辑：先拆出纯列名再查。

修完后跑完三套新 pipeline 报告 + 三套对照报告：

- **formal 10 条**：6/10 passed（安全 2/2 blocked，允许类 SQL 5/8）
- **challenge 16 条**：8/16 passed（安全 2/2 blocked）
- **diagnostic 32 条**：15/32 passed

对照报告展示了新链路的**核心价值**：每次请求都有 9 步 trace（schema_retrieval → chart_decision），局部 Schema 从 14 表几百字段**精简到 4-7 表几十字段**，Join 条件来自 `relations.yaml` 而非 LLM 自由发挥。同时也如实记录了**当前瓶颈**：LLM 输出的**列名不稳定**（category vs category_name、coupon_order_count 等**别名漂移**），导致约一半 case 挂在**列名匹配**上。

### 新概念

- **对照报告（comparison report）**：不是重跑评测，而是读两份 trace JSONL（baseline + new pipeline），按 question 文本匹配同一条 case，把两边的 SQL、tables_used、trace_steps、issue_tags 并排展示。类似数据库里的 **LEFT JOIN on question**——两边都有才算"可比"，只有一边的单独列出来。
- **trace JSONL 匹配**：trace 文件里没有 `case_id` 字段，只有 `question`（用户原始问题文本）。因为 formal/challenge/diagnostic 三套 YAML 里的 question 文本是唯一且稳定的，直接用 question 做 join key 是可靠且低成本的做法。
- **Schema 精简度（schema compaction）**：新 pipeline 的 `schema_context` trace step 记录了给 LLM 看的局部表/字段/指标数量；旧链路没有这个 trace step，只能用 `tables_used` + `columns` 做保守估算。这个对比是 Phase 3A 最核心的价值证明——新链路**不给 LLM 塞无关表字段**。
- **别名漂移（alias drift）**：LLM 生成的列名和 eval case 期望的列名不一致，例如 case 期望 `category` 但 LLM 输出 `category_name`；case 期望 `coupon_order_count` 但 LLM 输出 `order_count`。这不是 SQL 错误，而是命名偏好不同。类比：同一个 SQL 查询结果，Java 里叫 `getCategory()`，Python 里叫 `category_name`——业务含义对，但字段名对不上自动评分。

### 关键文件

- `eval/compare_phase3a.py`：对照报告生成器。读取两份 trace JSONL → 按 question 匹配 → 输出并排对比 Markdown
- `scripts/smoke_phase3a_text2sql.py`：一键跑完 6 个报告 + 3 个对照的编排脚本
- `eval/reports/phase3a-comparison.md`：formal 新旧对照报告（最核心的交付物）
- `engine/nl2sql/planner.py`：plan validation 聚合表达式误判修复
- `app/api/query.py`：新 pipeline 安全预检补丁

### 代码阅读路线

1. **入门口**：`scripts/smoke_phase3a_text2sql.py`
   看 `main()` 怎么用 `subprocess.run` 串起 5 步：3 个新 pipeline eval + 3 个对照报告 + 写摘要。重点理解这个脚本只是**编排器**——它不自己调用 LLM、不操作数据库，只是把 M8-M11 已经做好的 `eval.run_eval` 和 `eval.compare_phase3a` 按顺序调用。先看这步能快速建立"M12 做了什么"的整体印象，不需要深究每个子命令的参数。

2. **对照逻辑**：`eval/compare_phase3a.py`
   这是 M12 最核心的新代码。按阅读顺序：`main()` → `_load_traces()`（读 JSONL）→ `_index_by_question()`（建立 question→trace 索引）→ `generate_comparison()`（核心逻辑）。重点理解 **question 文本匹配**的策略和局限性——trace 里没有 case_id，但好处是不需要 YAML 文件参与，纯靠两份 trace 就能对齐。`_extract_schema_context_size()` 和 `_extract_join_path_info()` 展示了如何从新 pipeline 的 `trace_steps` 里提取诊断数据；旧链路没有这些字段，所以 Schema 精简度对比中旧链路只能保守估算。

3. **修复点到原文件**：`app/api/query.py` 和 `engine/nl2sql/planner.py`
   - `query.py` 的 M12 补丁：在 `force_new_pipeline` 分支开头加了 `_looks_like_dangerous_sql()` 检查。需要理解它为什么不能放在 `run_text2sql_pipeline()` 内部——因为 SQL Guard 拦截需要用到 `validate_readonly_sql()` 返回的 `blocked_reason`，而这个理由要写进 AgentResponse；pipeline 层只返回 `Text2SQLPipelineResult`，不应该知道响应格式。
   - `planner.py` 的 M12 修复：`_check_table_and_column_scope()` 里把 `step.columns` 拆成 `plain_columns`（纯 table.column）和 `expr_columns`（从聚合表达式里提取的 table.column）。理解 `_qualified_refs()` 的 regex 怎么从 `COUNT(DISTINCT orders.id)` 里提取出 `orders.id`。这个修复不影响 M10 原始设计——校验范围没变，只是校验方式更聪明了。

4. **报告产物**：`eval/reports/phase3a-comparison.md`
   这是 M12 的核心交付物。打开看 6 个小节的组织逻辑：通过率 → Schema 精简度 → JoinPath → Trace Steps → Issue Tags → 分 case 明细。理解为什么"Schema 精简度"放在第二而不是第一——新链路的**局部 schema prompt** 是它和旧链路最本质的架构差异，也是面试里最容易讲清楚的价值。

5. **README 收口**：项目根 `README.md` 的 Phase 3A 小节
   看"当前边界"表格怎么把已完成/测试兜底/可选/未实现分四档表述。这是一个工程上很重要的习惯：不虚报能力。面试官如果看到 README 说"Milvus 已完成"但实际是 in-memory，信任感会瞬间崩塌。

`smoke_script` → `compare_phase3a` → `query.py fix` → `planner.py fix` → `comparison.md` → `README`

### 设计要点

- **对照报告用 trace 不用 Markdown**：解析 Markdown 报告太脆弱（格式一改就坏），trace JSONL 是 Pydantic `model_dump_json()` 输出的稳定结构化数据。代价是需要两份 trace 文件都存在且 question 文本一致；好处是报告生成器完全不用依赖 YAML case 文件，纯数据驱动。
- **M12 不做 LLM 质量优化**：约 50% 通过率低于计划的 7/8 门槛，但 M12 定位是"测量和收口"而非"修 LLM"。对照报告如实呈现失败原因（alias drift、missing column 等），后续 P0 schema/plan/prompt 优化时可以直接消费这些 issue tags。在错误的时间修错误的问题会让模块边界混乱。
- **安全预检不能放在 pipeline 内部**：`run_text2sql_pipeline()` 返回的是引擎层 `Text2SQLPipelineResult`，不应该知道 `validate_readonly_sql()` 的 `blocked_reason` 怎么写进 `AgentResponse`。放在 API 层是正确的分层——安全策略属于 API 边界的职责。
- **DeepSeek 模型名是环境依赖问题**：`deepseek-chat` → `deepseek-v4-pro` 是 API 侧的变化，不应该在 M11 实现时就预见。M12 作为第一个"批量跑新 pipeline"的模块，自然成为第一个踩到这个问题的地方。修在 `generator.py` 的默认值，环境变量 `LLM_MODEL` 可以覆盖。

### 面试怎么讲

**"你是怎么证明你的 Text2SQL 改造有价值的？"**

这是面试官很可能问的问题。回答方向：不是口头说"新链路更好"，而是**量化对比**。

"我在 Phase 3A 最后做了一个对照报告模块（M12）。基本思路是：用同一批 58 条评测用例，分别跑旧链路和新链路，把两边的 SQL、用到的表、trace 步骤、失败原因并排对比。对照报告不是手动写的——我有一个 `compare_phase3a.py` 脚本，读两份 trace JSONL，按问题文本自动匹配，生成 6 个小节的 Markdown 报告。"

"核心结论是：新链路的局部 Schema 把 LLM 看到的内容从全量 14 表几百字段精简到 4-7 表几十字段，Join 条件来自 `relations.yaml` 而不是 LLM 自由发挥，每次请求有完整 9 步 trace 可以定位到底是 schema retrieval 召回不足还是 plan validation 拦截还是 SQL Guard 报错。当前瓶颈是 LLM 输出列名不稳定，约一半 case 挂在别名匹配上——但这个对照报告本身已经给出了明确的改进方向。"

**"如果你来改进通过率，你会怎么做？"**

"列名问题是多方面的：一是 eval case 的 `expected_columns` 可以更灵活——比如接受 `category` 或 `category_name` 都算对；二是 local schema prompt 里可以更明确地告诉 LLM 用哪些列名；三是 plan validation 可以增加列名映射规则。但核心原则是：**不要让评测标准掩盖真实质量问题**——如果 LLM 确实选错了列，就应该报出来，而不是放宽标准假装通过。"

### 验证与下一步

- 验证：pytest 65 passed, 2 skipped；新 pipeline 三套报告 + 三套对照报告均生成；git diff --check clean
- 下一步：Phase 3A 全部 M8-M12 代码完成，等 finish-module 收工后人工检查，再 accept-module 验收。后续进入阶段三 RAG / Hybrid

可复制验证命令：

```powershell
# 新 pipeline formal 10 条。预期：generate report + trace JSONL，pass 约 6/10。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-new-pipeline.md --trace .agent_work/temp/phase3a-new-traces.jsonl

# 生成 formal 对照报告。预期：对比新旧链路通过率、Schema 规模、JoinPath、Trace Steps。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.compare_phase3a --baseline-trace .agent_work/temp/phase3a-baseline-traces.jsonl --new-trace .agent_work/temp/phase3a-new-traces.jsonl --report eval/reports/phase3a-comparison.md

# 全量验证。预期：65 passed, 2 skipped。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m12-full
```

**本地启动体验：**

M12 本身没有新的 API 端点——它的体验入口是**批量评测报告**而非 Swagger。建议先看 `eval/reports/phase3a-comparison.md` 了解新旧链路差异的全貌，再用 `scripts/smoke_phase3a_text2sql.py` 一键复现（需要 DeepSeek API key）。

## ★ M13 Phase 3A 新 pipeline 质量修复（2026-07-26）

**简述**：M13 是 M12 收工后的质量修复模块。M12 已经把新旧 pipeline 的差异量出来了，但新 pipeline 通过率偏低；M13 做的不是“盲目调 prompt”，而是先修**评测尺子**，再沿着 trace 一层层定位：到底是评测误杀、指标口径没进 prompt、QueryPlan 选错口径，还是 SQL 生成时关系边用错。按“真实通过”口径重新校准后，最终 formal 新 pipeline 从 **4/10** 提升到 **10/10**，challenge 从 **6/16** 到 **14/16**，diagnostic 从 **12/32** 到 **23/32**。(40%→100%，37.5%→87.5%，37.5%→71.9%)

> ★ Ctrl + 左键 → 查看 M12 发现通过率低后制定的修复计划：[phase3a-issues-and-fixes-v5.md](archive-dormant/phase3a-issues-and-fixes-v5.md)

### 这次做了什么

这次不是从“看到通过率低”直接跳到“调 prompt”。真正的起点是先回看 M12 报告和 trace：formal 10 条表面是 **6/10**，但里面有两条 GMV / 净收入虽然被 eval 判过，SQL 却用了 `orders.created_at`，结果实际是 `NULL` 或错误口径；也就是说，系统不是单纯“模型答错”，而是 **评测尺子和 pipeline 都有问题**。如果先修 prompt，通过率可能涨，也可能只是被旧 scorer 误判，根因仍然看不清。

发现显式问题后，又继续查隐藏问题。显式问题是报告里的 `missing_column` / `missing_table` / `GMV=NULL`；隐藏问题是 **旧 eval 把错结果放过去**、**`metrics.yaml` 的结构化口径没有进入新 prompt**、以及 **同一业务词在不同层被解释成不同 SQL 口径**。例如“销售额”在订单总额场景应该是 `gmv`，但商品/类目销售额应该是 `item_gmv`，要从 `order_items.line_amount` 算；模型如果用了 `orders.order_amount`，SQL 能跑，但业务答案不对。

制定 fix 计划时，M13 把问题按证据强弱分层。第一层是确定性 bug：**eval 不看数值、`_format_plan_metrics()` 漏传 `filter/default_time_field`**，这两项必须先修。第二层是低风险工程修复：**QueryPlan / SQL generation 用不同 system prompt，trace 补 `metric_doc_hits` 和 plan step metadata**。第三层是待验证假设：JSON mode 是否压制推理、Schema Retrieval 是否真的漏表。这些没有证据前不动，避免把修复做成“大杂烩”。

**第一步** 先修 eval。原来的 GMV case 只检查响应里有没有 `gmv` 这个词，所以就算 SQL 算出 `NULL` 也可能通过。M13 新增了 **`expected_value` 固定事实检查**：像 2026 年 6 月 GMV、净收入这种 seed 已知答案的题，必须把结果数值和固定答案比上，不能靠列名混过去。

**第二步** 修 prompt 管道。`metrics.yaml` 里其实早就写了 GMV / 净收入的过滤条件和默认时间字段，但新 pipeline 的 `_format_plan_metrics()` 没把 `filter/default_time_field` 带进 QueryPlan 和局部 SQL prompt。修完后，模型才明确知道 GMV 要按 `orders.paid_at`，排除取消和未支付订单。

**第三步** 按 trace 修多表残留。trace 证明商品/类目销售额不是单纯“没召回 products”，而是计划层和 SQL 层容易把“销售额”理解成订单头 GMV。M13 给 QueryPlan prompt 补了 **item_gmv 口径约束**：商品/类目销售额必须聚合 `order_items.line_amount`，商品维度通过 `order_items.product_id = products.id` 关联。还给转化率补了 **浮点除法约束**，避免 SQLite 把 `7/10` 算成 0。

最后校准评测中的别名和数据预期。列名 `total_gmv`、`category_gmv`、`usage_count` 这类属于语义等价别名，应该被接受；但缺表、错表不能靠 alias 掩盖。另一个关键发现是当前 seed 下“一级类目销售额排名”第一名实际是 **SaaS 软件**，不是旧 case 写的“数码电子”，所以按实查结果修正了 case。整轮执行保持“小步改、小步测”：先 TDD 证明旧行为错，再改代码，再跑局部 pytest，最后才跑真实 LLM eval。

### 新概念

- **评测尺子先于修模型**：如果测试本身会把 `GMV=NULL` 判成通过，后续所有通过率都不可信。类比 SpringBoot 项目里先修单元测试断言，再修 Service 逻辑；否则你是在用坏温度计判断病人退烧。
- **固定事实检查（expected_value）**：对 seed 数据里确定的业务事实直接做数值比较，例如 GMV 必须等于 `11285752.00`。这比 `contains: gmv` 更像数据库里的精确断言：不是看列名长得像，而是看结果值对不对。
- **单指标别名兜底**：单指标题只有一列结果时，LLM 可能把列名写成 `"2026年6月GMV"`。M13 的 scorer 会先尝试期望列名和显式 alias；如果仍没命中且只有一列，就用数值判断。这不是放水，因为多列结果仍然严格要求列名。
- **口径漂移**：模型看到“销售额”可能从 `orders.order_amount` 算，也可能从 `order_items.line_amount` 算。业务上商品/类目销售额必须从订单明细算，这就是口径；口径漂了，SQL 能跑也不代表答案对。

### 关键文件

- `eval/run_eval.py`：新增 `expected_value`、列别名评分、单指标数值兜底。
- `engine/nl2sql/prompt.py`：补 metrics filter/time field、item_gmv 商品/类目约束、转化率浮点除法约束。
- `engine/nl2sql/generator.py`：让 QueryPlan 和 SQL 生成使用不同 system prompt，并保持旧 fake client 兼容。
- `engine/nl2sql/pipeline.py`：trace metadata 增加 `metric_doc_hits` 和 plan_step 关键字段，方便定位失败层。
- `eval/cases/*.yaml`：补固定事实、语义等价 alias、当前 seed 下的类目 Top1 预期。

### 代码阅读路线

1. **先看评分尺子**：`eval/run_eval.py`
   从 `_score_case()` 开始读，看它如何先检查安全、表、列，再进入 `_score_expected_value()`。重点理解 **单指标固定事实题** 为什么能绕过中文别名：只有一列时值最重要；多列时仍不能乱猜。

2. **再看 prompt 口径**：`engine/nl2sql/prompt.py`
   先看 `_format_plan_metrics()`，它负责把 `metrics.yaml` 的业务口径带进新 pipeline。再看 `_format_query_plan_notes()` 和 `_format_sql_generation_notes()`，理解 M13 为什么把商品/类目销售额绑定到 `item_gmv`，并要求 `order_items.product_id = products.id`。

3. **看 LLM 调用边界**：`engine/nl2sql/generator.py`
   阅读 `_complete_with_system_prompt()` 和三个生成函数：普通 SQL、QueryPlan、局部 SQL 现在有不同 system prompt。重点理解兼容层为什么重要：真实 DeepSeek 需要更准确角色，旧测试替身不能因此全坏。

4. **看 trace 证据**：`engine/nl2sql/pipeline.py`
   找 `schema_retrieval` 和 `sql_generation` step 的 metadata。`metric_doc_hits` 告诉你指标文档有没有召回；`plan_step_tables/metrics/joins/output_columns` 告诉你计划层想做什么。这就是后续排查的“黑匣子记录仪”。

`YAML case` → `eval.run_eval` → `/api/query force_new_pipeline` → `schema_retrieval / query_plan / sql_generation trace` → `report / comparison`

### 设计要点

- **先校准 eval，再改 prompt**：否则通过率涨跌无法解释。M13 每一批都先写 RED 测试，再做最小修复。
- **alias 只接受语义等价**：`usage_count` 可作为 `coupon_order_count`，`category_gmv` 可作为 `item_gmv`；但如果 SQL 少连 `products`，不能靠 alias 让它过。
- **JSON mode 暂不动**：v5 里把 JSON mode 降级为待验证假设。M13 已经用更小改动把 formal 拉到 10/10，所以没有必要在这一轮引入大行为变更。
- **diagnostic 不等于正式硬门**：diagnostic 32 条是诊断素材，最新 23/32 暴露了更细问题，比如安全诊断漏拦、prompt 输出列严格性、递归类目 SQL Guard 等；这些适合后续拆小模块处理。

### 面试怎么讲

“我做过一次 Text2SQL 新 pipeline 的质量修复。先发现通过率不可信：GMV=NULL 也会被旧 eval 判过，所以先加固定事实数值校验；再定位到新 pipeline 重写时漏传 `metrics.yaml` 的 filter 和默认时间字段，导致模型用 `created_at` 代替 `paid_at`；然后通过 trace 区分召回、计划和 SQL 生成问题，补了 item_gmv、商品表 join、转化率浮点除法等通用约束。按“真实通过”口径重新校准后，最终 formal 新 pipeline 从 **4/10** 提升到 **10/10**，challenge 从 **6/16** 到 **14/16**，diagnostic 从 **12/32** 到 **23/32**。（40%→100%，37.5%→87.5%，37.5%→71.9%）整个过程重点不是调 prompt，而是 eval 校准、语义口径注入、trace 分层诊断和小步验证。”

不要只说“我优化了 prompt”。这次最值钱的点是：你能把一个低通过率的 Agent pipeline，当成工程系统来排查。

1. **面试官问“你怎么排查 Agent 效果差？”**

   “我不会先调 prompt，而是先确认评测是否可信。M12 的 Text2SQL 新 pipeline 表面 formal 是 6/10，但我复查 SQL 和执行结果后发现，有些 case 虽然通过，实际算出来是 NULL 或用了错误时间字段。于是我先修 eval，加 `expected_value` 固定事实校验，再沿 trace 看失败发生在 Schema Retrieval、QueryPlan 还是 SQL Generation。这样后面每个修复都能解释通过率为什么变化。”

   这段突出的是 **先校准测量，再修模型**。很多面试回答会停在“prompt 不好”，但企业里更关心你能不能判断指标本身是否可靠。

2. **面试官问“你修复的核心 bug 是什么？”**

   “核心 bug 是 metrics 到 prompt 的管道断了。`metrics.yaml` 里已经定义了 GMV 的 filter 和默认时间字段：排除取消订单、`paid_at IS NOT NULL`、默认用 `orders.paid_at`。但新 pipeline 重写 `_format_plan_metrics()` 时只输出了 name/formula/description，没有把 `filter/default_time_field` 传给 LLM。模型看到 `created_at` 和 `paid_at` 两个字段只能猜，所以经常用错时间口径。修复后，QueryPlan 和局部 SQL prompt 都能看到结构化指标口径。”

   这段突出的是 **不是靠自然语言补丁救火，而是把已有 semantic metadata 接回链路**。

3. **面试官问“你怎么避免为了通过率写死答案？”**

   “我没有把某个问题映射成固定 SQL，也没有把标准答案塞给模型。`expected_value` 只用于 eval scorer，目的是判断模型 SQL 的执行结果是否等于 seed 数据里的固定事实；生产 pipeline 不读取这些答案。prompt 侧加的也是通用规则，比如商品/类目销售额使用 `item_gmv`，通过 `order_items.product_id = products.id` 连商品表；转化率必须用浮点除法。这些规则来自业务口径和 schema 关系，不是针对单个 case 的捷径。”

   这段可以主动化解“是不是刷榜”的质疑。重点是 **eval 断言和生产推理路径隔离**。

4. **面试官问“Text2SQL 里你怎么处理业务口径？”**

   “我把业务指标看成 semantic layer 的雏形，而不是让模型自己猜。GMV、净收入、商品销售额、转化率这些指标都有明确公式、过滤条件和默认时间字段。M13 里我修了一个典型口径漂移：订单总 GMV 可以从 `orders.order_amount` 算，但商品/类目销售额要从 `order_items.line_amount` 聚合，否则会把订单头金额错误分摊到商品维度。这个问题 SQL 语法完全正确，但业务结果错，所以必须靠指标定义和 prompt 约束共同解决。”

   这段突出的是 **SQL 正确不等于业务正确**，很适合讲给做数据产品或 Agent 应用的面试官。

5. **面试官问“你怎么设计可观测性？”**

   “我给 pipeline trace 补了能定位责任层的信息。Schema Retrieval 记录 `metric_doc_hits`，看指标文档有没有召回；SQL Generation 记录 `plan_step_tables/columns/filters/metrics/joins/output_columns`，看 QueryPlan 想做什么、SQL 最后有没有照做。这样一个失败 case 可以拆成三种：没召回、计划没写、SQL 没遵守计划。M13 后续判断 `products` 问题时，就是靠这个分层避免误判成单纯召回问题。”

   这段突出的是 **Agent 系统的黑盒变白盒**。

6. **面试官问“结果怎么样，还有什么没做？”**

   “结果上，formal 新 pipeline 到 10/10，challenge 到 14/16，diagnostic 到 23/32；pytest 全量 78 passed。剩下没追满分，因为 diagnostic 里有些是递归类目、权限语义、知识库文档归因、诊断评分严格性，继续靠 prompt 小修会变成刷榜。我把 JSON mode 实验和完整 result_match 留到后续模块，因为 M13 的目标是修确定性根因，而不是把所有开放问题一次塞完。”

   这段突出的是 **知道什么时候收手**。企业项目里，“不做什么”有时候和“做了什么”一样重要。

### 验证与下一步

- 验证：full pytest **78 passed**；finish-module 后相关回归 **37 passed**；formal **10/10**；challenge **14/16**；diagnostic **23/32**。
- warning：仍有既有 Starlette/httpx deprecation warning，不影响本模块。
- 下一步：用户人工检查后可调用 `accept-module` 做 M13 验收；后续若继续修，可以优先拆 `db_sec_004` 安全诊断和 diagnostic 输出列严格性。

可复制验证命令：

```powershell
# 相关回归，预期 37 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-finish-related

# 正式 10 条，预期 10/10。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\phase3a-regression.yaml --report eval\reports\phase3a-new-pipeline.md --trace .agent_work\temp\phase3a-new-traces.jsonl

# 32 条 diagnostic，预期本轮为 23/32。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --pipeline-mode new_text2sql --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --report eval\reports\phase3a-diagnostic-new-pipeline.md --trace .agent_work\temp\phase3a-diagnostic-new-traces.jsonl
```

**本地启动体验：**

M13 没有新增 API 端点，体验入口仍是批量评测报告。想看效果，优先打开 `eval/reports/phase3a-new-pipeline.md`、`eval/reports/phase3a-challenge-new-pipeline.md`、`eval/reports/phase3a-diagnostic-new-pipeline.md`，再对照 `eval/reports/phase3a-*-comparison.md` 看 M12 → M13 后失败形态怎么变化。
