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

