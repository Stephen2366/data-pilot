# DataPilot 开发日志（学习复盘）

> 给"未来的我"读的：每个模块讲清楚做了什么、我该理解什么、面试怎么讲。当前进度看 `docs/state/AI_CONTEXT.md`「当前状态」；完整技术档案和历史实验统一从 `docs/state/CHANGELOG_INDEX.md` 进入，查 bug 时按需追溯。
>
> 本文件只包含 M0 → M28；M29 以后的记录见 `dev-log`。

## ★ M0 工程骨架与配置

（2026-07-16）

**简述：**把空仓库变成一个能启动、能跑测试的 FastAPI 项目——相当于盖房子前先打好地基、通好水电。

### 这次做了什么

DataPilot 最终要做"用自然语言问数据"的 Agent 系统，但第一天**不碰 AI**，先把**工程底子打牢**。就像做 **Java / SpringBoot** 项目前先建好启动类、配置文件和健康检查一样，这一步先让 Python 后端具备最基本的工程形态。

具体做法是：搭好 **FastAPI 服务**（把 Python 函数变成对外 HTTP 接口的 Web 框架），加一个 `/health` **健康检查接口**确认服务活着；用 **Pydantic Settings** 把 `.env` 里的配置（数据库地址、API Key 等）自动读成 Python 对象，避免代码里到处手写 `os.getenv()`；再配上**第一批自动化测试**。这样后面每加一个功能，都能随时确认"服务还能起、配置还能读、测试还能过"。

### 新概念

- **FastAPI**：Python 的 Web 框架，把函数变成 HTTP 接口。类比 SpringBoot 的 `@RestController`
- **Pydantic Settings**：把 `.env` 里的配置自动读成带类型检查的 Python 对象，避免代码里到处手写 `os.getenv()`

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

## ★ M1 数据底座

（2026-07-17）

**简述**：建好 7 张业务表、数据库迁移和确定性假数据——先把"仓库和货"备齐，之后 Agent 才有东西可查。

### 这次做了什么

要让 Agent 回答"上月退款率最高的商品是什么"，前提是数据库里真的有**订单、退款这些数据**。这一步相当于先给数据分析系统准备"业务仓库"：**表结构是货架**，**seed 数据是摆上去的货**，**固定业务事实是后面验货用的标准答案**。

这次用 **SQLAlchemy 定义了 7 张表**：用户、商品、渠道是"**维度**"（描述业务对象是谁），订单、退款、工单是"**事实**"（记录业务发生了什么），知识文档表给后面的 **RAG 检索**预留位置。建表不手写 SQL，而是通过 **Alembic 迁移管理**，改表历史全程可追溯。然后写了一个"**每次运行结果都一模一样**"的假数据脚本，还故意在数据里埋了 **4 个标准答案**（比如 2026 年 6 月退款率最高的商品是谁）——以后评测 Agent 时，就能自动判断它查得对不对。

### 新概念

- **SQLAlchemy**：Python 操作数据库的工具包，两层——**ORM**（类↔表，类比 JPA/Hibernate）和 **Core**（用 Python 表达式构建 SQL，防注入，类比 MyBatis）。项目里 `app/models/` 走 ORM，后面 `engine/nl2sql/` 动态拼 SQL 走 Core
- **Alembic**：数据库结构的版本控制（类比 Flyway/Liquibase）。改 Model → 自动生成迁移脚本 → `upgrade` 应用到库，可 `downgrade` 回滚，和 git 一样可追溯
- **维度表 / 事实表**：维度表回答"是谁 / 是什么"，事实表回答"发生了什么"——查询时先定位维度，再查事实，性能更好

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

## ★ M2 API 与后端工程基础

（2026-07-18）

**简述**：给 M1 的数据底座装上稳定 API 出入口——像给仓库开了带登记簿的取货窗口，后续 Agent 和演示页都从这里拿数据。

### 这次做了什么

M1 已经把 **7 张表和确定性数据**准备好了，但后续 Agent、评测脚本、Streamlit 页面不能直接到处打开数据库连接。M2 做的是后端工程基础：**统一数据库会话、统一分页列表接口、统一请求日志和统一错误响应**。

这次新增了 `app/db/session.py`，让每个请求通过 `get_db()` 拿一个 **SQLAlchemy Session**，用完自动关闭；`pool_pre_ping=True` 负责在 MySQL 连接交给业务代码前先探活。然后新增 **4 个列表接口**：商品、订单、退款、工单，每个接口都支持分页和本模块计划里的基础筛选。接口返回统一 `PageResponse`，错误返回统一 `ErrorResponse`，并且每次请求都有 `trace_id`，日志里能看到 method、path、status、latency_ms 和 trace_id。

### 新概念

- **请求级 Session**：每个 HTTP 请求拿一个数据库会话，请求结束就关闭。类比 SpringBoot 里一次请求进 Service / Repository 使用同一个事务上下文，不在 Controller 里到处手写连接。
- **分页响应**：列表接口不只返回数据，还返回 `total / page / page_size`。前端或评测脚本才知道总共有多少条、当前是哪一页。
- **trace_id**：一次请求的追踪编号。出错时用户拿到 trace_id，服务端也用同一个 trace_id 查日志，排查链路会快很多。

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

## ★ M3 v0 模板 SQL 闭环

（2026-07-19）

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

“M3 我先做的是一个**可控的 Text-to-SQL v0**。我没有一上来就让 LLM 自由生成 SQL，而是先用 5 条高价值模板 SQL 打通自然语言问题、SQL Guard、数据库执行和 `AgentResponse` 返回的完整闭环。这样做的价值是：系统先有一条稳定、可测、可演示的主链路；后续 M4 接 LLM、M5 扩展 trace 和图表时，只需要替换 SQL 来源，不需要重做 API、安全和响应契约。”

“安全上，M3 已经把 SQL 执行入口固定到 **SQL Guard** 后面。即使模板 SQL 是我们自己写的，也不绕过 Guard；危险输入会被 sqlglot AST 解析拦截为非 SELECT。这是后续安全能力的地基：M3 只做只读检查，M4 再在同一个入口叠加 RBAC 和敏感字段策略。”

> 现在口径：M3 的模板路径仍然是 `/api/query` 默认 baseline 的一部分；M11 之后可以通过 `force_new_pipeline=true` 强制走新 Text2SQL pipeline。SQL Guard 也已从 M3 的只读检查演进为 **只读检查 + 表级 RBAC + 敏感字段拦截**，M14-lite 后 admin 也不能通过 Text2SQL 直出 `users.email/users.phone`。

1. **面试官问“为什么不一开始就接 LLM？”**

   可以答：“因为一开始就接 LLM，会把生成质量、SQL 安全、接口契约、数据库执行混在一起排查。M3 先用模板 SQL 建立稳定 baseline，等 API、Guard、AgentResponse 都可测后，再把 LLM 作为 SQL 来源接进来。这样问题分层更清楚。”

   这段突出的是 **先稳工程闭环，再引入不确定性**。

2. **面试官问“模板 SQL 会不会太简单？”**

   可以答：“模板 SQL 不是最终智能能力，而是 v0 基线。它覆盖 GMV、退款率、渠道订单量等高价值问题，帮助项目先有可演示结果；同时模板和 LLM 共用 SQL Guard 和响应结构，所以后续升级不会推倒重来。”

   这段突出的是 **演进式架构**，不是把模板包装成智能。

3. **面试官问“M3 的安全设计有什么亮点？”**

   可以答：“M3 没有靠字符串判断 `drop`，而是用 sqlglot 把 SQL 解析成 AST，只允许单条 SELECT。虽然当时还没有 RBAC 和敏感字段，但 Guard 的入口已经固定，后续所有模板 SQL、LLM SQL、新 pipeline SQL 都复用同一个安全门。”

   这段突出的是 **安全边界前置** 和 **可扩展门禁**。

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

## ★ M4 NL2SQL 最小链路与安全

（2026-07-20）

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

“M4 我把 Text-to-SQL 从规则模板升级到 **LLM 生成 SQL**，但没有把安全交给模型。默认仍然模板优先，只有模板未命中才把 schema、指标口径和 few-shot 示例放进 prompt 调 DeepSeek。模型返回 SQL 后，系统不会直接执行，而是用 sqlglot AST 提取访问的表和字段，再按 RBAC allowlist 和敏感字段策略判断是否放行。”

“这个模块最重要的工程意识是：**LLM 只负责生成候选 SQL，数据库执行权必须掌握在后端确定性策略里**。prompt 可以提醒模型不要查敏感字段，但真正的门禁在 SQL Guard / policy 层。这样即使模型输出了危险 SQL、越权表或 `users.email`，后端也能结构化拦截，而不是把安全寄托在模型‘听话’上。”

> 现在口径：M4 当时接的是最小 DeepSeek 主路径；后续默认模型名已修到 `deepseek-v4-pro`。M14-lite 后安全策略进一步收紧为 **敏感字段优先于 admin 角色**，所以 admin 也不能在 Text2SQL 路径直接查邮箱/手机号；如果要给管理员看敏感信息，应走脱敏、审计或专门接口。

1. **面试官问“LLM 生成 SQL 怎么保证不乱查？”**

   可以答：“M4 的做法是 prompt 约束 + 后端校验双层。prompt 里给 schema、指标和 few-shot，让模型尽量生成正确 SQL；但最终放行由 SQL Guard 决定，它会解析 AST、检查是否只读、访问了哪些表字段，再套 RBAC 和敏感字段策略。”

   这段突出的是 **LLM 不掌握执行权**。

2. **面试官问“为什么模板优先？”**

   可以答：“M3 的 5 条模板已经是稳定 baseline，如果 M4 一接 LLM 就让所有问题都走模型，老能力会被模型波动影响。模板优先能保证核心 demo 稳定，模板未命中时再用 LLM 扩展覆盖面。”

   这段突出的是 **稳定基线 + 渐进扩展**。

3. **面试官问“敏感字段怎么处理？”**

   可以答：“敏感字段来自 domain pack 的 schema 描述，不靠自然语言临时判断。SQL Guard 会从 SQL AST 里提取 `table.column`，命中 `users.email/users.phone` 就拦截。现在主线里这条规则对 admin 也生效，避免 Text2SQL 成为敏感信息直出通道。”

   这段突出的是 **schema metadata 驱动安全策略**。

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

## ★ M5 AgentResponse 扩展、Trace、Tool 与图表

（2026-07-20）

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

“M5 我把 Text-to-SQL 的结果从‘返回 answer + SQL’升级成一个**可观测的 Agent 输出协议**。响应里不只包含自然语言答案和表格，还包含 `tool_calls`、`cost`、`tables_used`、`chart_spec`、`error_type` 和 `trace_id`。这样前端可以直接展示图表，评测系统可以按 trace_id 复盘一次查询，安全拦截也能被归类统计。”

“工程上，我把 SQL 执行从 API 层拆成 **SQL Tool**。这样安全检查、数据库执行、耗时记录、错误类型都收口在同一个边界里。后续不管是 Streamlit 演示、EvalOps-lite，还是 M11 新 pipeline，本质上都可以复用这个 Tool，而不是每条链路各自执行 SQL、各自处理安全。”

> 现在口径：M5 的 `tool_calls` / JSONL trace 是可观测性底座；M11 后新增了更细的 `trace_steps`，能看到 schema retrieval、query plan、sql generation、sql guard 等阶段；M14-lite 又给 LLM 失败 trace 增加 raw response preview、parse error 和 prompt length。也就是说，M5 是 trace 起点，不是最终形态。

1. **面试官问“AgentResponse 为什么要这么多字段？”**

   可以答：“因为 Agent 系统不只是给用户看一句 answer。前端需要表格和图表，评测需要 SQL、表、列和 trace_id，排查需要 tool_calls、error_type 和耗时。M5 把这些信息结构化，后续模块就不用解析一段自由文本。”

   这段突出的是 **响应契约设计**。

2. **面试官问“为什么要把 SQL 执行封装成 Tool？”**

   可以答：“Tool 是 Agent 调用外部能力的边界。SQL Tool 统一负责 Guard、执行、耗时和错误记录，避免 API、评测、新 pipeline 各自直接 `db.execute()`。这样后续迁移到 LangGraph 或多步骤 Agent 时，安全边界仍然在 Tool 里。”

   这段突出的是 **工具边界和安全复用**。

3. **面试官问“图表是怎么来的？”**

   可以答：“M5 先做轻量规则，不让图表决策拖大范围。根据 columns 和 rows 判断 bar、line、horizontal_bar 或单指标柱图，无法判断就返回 `chart_spec=null`。图表是附加展示能力，不影响 SQL 答案本身。”

   这段突出的是 **功能可用但边界克制**。

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

## ★ M6 EvalOps-lite 与演示收尾

（2026-07-20）

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

## ★ Phase 2.7 数据库升级

（2026-07-22）

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

“Phase 2.7 我把项目的数据底座从 demo 级 7 表升级到更接近真实分析场景的 **14 张物理表**。新增了订单明细、类目树、优惠券桥接表、行为日志、价格历史和订单宽表；数据规模也扩到 1 万级订单和 1.8 万级订单明细。这样后续 Text2SQL 不再是在小库上自嗨，而是要面对多表 Join、指标口径、宽表选择、递归类目、SCD 价格历史和数据质量问题。”

“这个模块的价值不只是表变多，而是把**可复现的业务事实**写进 deterministic seed。比如 2026 年 6 月 GMV、净收入、优惠券、渠道和商品销售额等，后续评测可以拿这些固定事实判断 Agent 的 SQL 结果到底对不对。数据库迁移用 Alembic 管理，审查后发现字段和索引口径偏差时，也通过独立 `0003` migration 补齐，没有把历史改乱。”

> 现在口径：Phase 2.7 提供的 14 表和固定事实，已经在 Phase 3A 被继续消费。M13 用 `expected_value` 校准 GMV / 净收入，M14-lite 又用 `result_match` 对 5 条核心 SQL case 执行参考 SQL 结果对比。递归类目和知识库归因仍然不作为当前 Text2SQL 硬门，后续应放到 SQL Guard 递归 CTE 设计或 RAG / Hybrid 阶段处理。

1. **面试官问“为什么要专门做数据库升级？”**

   可以答：“原来的 7 表足够跑 demo，但不够检验 Text2SQL 的真实问题。企业数据分析常见难点是多表 Join、指标口径、明细表和宽表选择、历史价格窗口、优惠券多对多和数据质量异常。Phase 2.7 把这些复杂度提前放进可控 seed，后续优化才有可信评测环境。”

   这段突出的是 **用真实复杂度驱动 Agent 能力设计**。

2. **面试官问“seed 数据为什么要确定性？”**

   可以答：“评测需要稳定标准答案。如果每次 seed 都随机，GMV、Top 商品、渠道排名每天变，Agent 对不对就没法自动判断。Phase 2.7 用规则化生成保证数据规模真实，同时固定关键业务事实，后续 M13/M14 才能做 expected_value 和 result_match。”

   这段突出的是 **评测可复现性**。

3. **面试官问“审查后发现表设计偏差怎么处理？”**

   可以答：“我没有直接改旧 migration，也没有口头说‘差不多’。发现 `orders_wide` 字段、优惠券有效期索引、价格历史变更原因等口径偏差后，用独立 `20260722_0003` migration 补齐。这样 Alembic 历史清楚，接手的人能看出哪些是核心升级，哪些是审查后 polish。”

   这段突出的是 **迁移历史可追溯** 和 **工程补偿方式**。

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

## ★ ★ ★ Phase 2 阶段总结：SQL Agent v1 闭环

（2026-07-31）

**简述**：Phase 2 是 DataPilot 的"从 0 到 1"：M0-M3 先跑通 **v0 模板 SQL 端到端闭环**（工程骨架 → 7 表数据底座 → API 基础 → 模板查询 + sqlglot 只读检查），M4-M6 升级成 **v1**（LLM 生成 SQL + RBAC/敏感字段安全 + 结构化输出 + Trace / Tool / 图表 + EvalOps-lite 评测 + Streamlit 演示），最后 Phase 2.7 把数据底座升级为 **14 张物理表 + 1 万级订单**。整个阶段的定位是：**先跑通、再变强、然后给它装上尺子和眼睛**——v1 交付时可投递：NL2SQL + SQL 安全 + 图表 + 演示页 + 6 条 smoke 全绿。

### 先用大白话讲

阶段二讲的是一个"**从 0 到 1 开面馆**"的故事，可以拆成四幕：

第一幕是**把店开起来**（M0-M3，v0）：先定厨房设备（工程骨架，MySQL 主路径）、备齐 7 种食材（数据底座：用户/商品/渠道/订单/退款/工单/知识库 7 张表 + 确定性假数据）、装好窗口（FastAPI + 统一日志/异常/分页）、然后只卖三样固定菜（5 条模板 SQL）。关键决策是：**先端到端跑通，不急着请大厨**——模板没命中的问题先结构化地告诉用户"我不会"。同时把"卫生检查"前置：所有 SQL 执行前必须过 **sqlglot AST 只读检查**（只允许单条 SELECT）。

第二幕是**请大厨，但卫生检查不变**（M4，v1 起点）：模板没命中时改调 **DeepSeek LLM 生成 SQL**，但模型生成的 SQL 和模板 SQL 走**同一个安全闸门**——sqlglot AST 只读 + 表级 RBAC + 字段级敏感字段拦截（`users.email / users.phone` 从建表第一天就标了敏感）。安全不是靠 prompt 求模型"别做坏事"，而是执行前的硬拦截。

第三幕是**上标准摆盘 + 记台账**（M5-M6）：把返回结果整理成 **AgentResponse 结构化契约**（答案/SQL/表格/图表/用了哪些表/工具调用/trace_id），SQL 执行统一收进 **SQL Tool**，每次查询写 **JSONL Trace** 证据链，聚合结果自动给 **Vega-Lite 图表 spec**；然后补上 **EvalOps-lite**（6 条 smoke 用例走真实 API 评测）+ **Streamlit 演示页**。至此 v1 闭环：能查、能拦、能画、能测、能演示。

第四幕是**扩充食材**（Phase 2.7）：7 表对真实企业分析太"教学版"了，一次性升级成 **14 张物理表 + 1 万级订单**（订单明细、类目树、优惠券多对多、行为日志、价格历史、宽表），数据里还**刻意埋了真实业务彩蛋**（未支付订单、canceled/cancelled 拼写差异、金额不一致、负数退款）——不是为了把库做脏，而是让 Agent 从"在干净玩具库里答对题"走向"面对真实数据挑战"。

所以 Phase 2 的核心价值是：**用最小的闭环先证明"自然语言 → 安全查库 → 结构化输出"跑得通，再一层层加上智能、可观测和真实数据复杂度**，为阶段三的 Text2SQL 深化和 RAG / Hybrid 提供可评测的 v1 底座。

### 这次做了什么

按阶段主线写，不按模块流水账：

1. **v0：先把端到端跑通**（M0-M3）——M0 搭工程骨架（FastAPI + MySQL `datapilot_dev` 主路径 + `.env` 配置），M1 建 **7 表数据底座**（Alembic 迁移 + 确定性 seed + 4 个固定业务事实 + 敏感字段从模型层标记），M2 做 API 基础（共享数据库 session、统一分页/日志/异常、Redis 只落 NullCache 骨架），M3 用 **5 条白名单模板 SQL** 跑通 `/api/query` 闭环：命中模板 → sqlglot 只读检查 → 执行 → 返回简化版 `AgentResponse`。同时先写好 `eval/cases_plan.md` 的 **32 条评测问题规划**——评测前置，不给功能写飞留空间。

2. **v1 上半场：让 LLM 来生成 SQL，但不放松安全**（M4）——模板未命中时调 **DeepSeek** 生成 SQL，prompt 里带 schema 描述、KPI 口径（GMV/退款率来自 `metrics.yaml`）和 few-shot；执行前统一过增强版 **SQL Guard**：sqlglot AST 只读 + **表级 RBAC**（admin/ops/customer_service/demo_user 四角色）+ **字段级敏感字段拦截**。API key 缺失或 LLM 失败时返回结构化拦截，**不降级成假 LLM 糊弄答案**。

3. **v1 下半场：结构化输出 + Trace + Tool + 图表**（M5）——`AgentResponse` **增量扩展**（保留旧字段含义，新增 `tables_used / docs_used / chart_spec / cost / tool_calls / error_type`）；SQL 执行从 API 层抽成 **SQL Tool** 统一入口（Guard → 表名提取 → 执行 → 耗时 → tool call 记录）；每次查询写 **JSONL Trace**；Chart Tool 按结果形状生成 Vega-Lite 兼容 spec（bar / line / horizontal_bar）。

4. **评测与演示收尾**（M6）——EvalOps-lite 用 **API seam 评测**（TestClient + 内存 SQLite 调真实 `/api/query` 路由，不绕过 API 契约、不写主库），6 条 smoke 全绿（2 简单 + 2 聚合 + 1 多表 join + 1 安全拦截）；Streamlit 演示页展示 answer / SQL / table / chart / safety / trace；产出 v1 验收报告（只写已实现能力，不把 RAG/hybrid 写成已完成）。

5. **数据库底座升级**（Phase 2.7 / 2.7.1）——7 表升级为 **14 张物理表**（新增订单明细、类目树、优惠券 + 桥接表、行为日志、价格历史、订单宽表），**1 万级确定性数据**（10000 订单 / 18000 明细 / 1000 退款 / 3000 用券 / 10000 行为日志）+ 固定业务事实（GMV `11285752.00`、Aurora 退款率最高、Mobile App 渠道 GMV Top 等）；**兼容旧链路**（保留 `orders.product_id`、`products.category`，旧 API / 模板 / smoke 照跑）；`relations.yaml` 结构化关系源 + `metrics.yaml` 指标口径就位，16 条 challenge + 10 条正式回归 case 预置给 Phase 3A 用。2.7.1 再按外部审查补宽表字段、价格历史 `change_reason`、优惠券有效期索引等 polish。

### 阶段主线图

`自然语言问题`
→ `/api/query`（M3 起：模板优先 → M4 起：未命中走 DeepSeek LLM）
→ `SQL Guard`（sqlglot AST 只读 → M4 起 + RBAC + 敏感字段拦截）
→ `SQL Tool`（M5 起统一执行入口：Guard → 执行 → 耗时 → tool call）
→ `AgentResponse`（M3 简化版 → M5 扩展版：answer / sql / rows / chart_spec / tables_used / trace_id / ...）
→ `JSONL Trace`（证据链）+ `chart_spec`（Vega-Lite）→ Streamlit 演示页

数据与评测侧：`M1 7 表确定性 seed` → `Phase 2.7 14 表 + 1 万级订单 + 固定事实 + 数据质量彩蛋` → `M6 EvalOps-lite 6 条 smoke`（API seam）→ `cases_plan 32 条规划` → `Phase 3A 三层评测基座（后续）`

### 关键知识点串联

这里不再列每个模块所有概念，而是列阶段级概念：

- **v0 → v1 的演进顺序**：先模板闭环、再加 LLM。v0 的"菜谱之外先诚实说不会"让端到端链路先稳定，v1 加 LLM 时才不会和安全、契约问题搅在一起——**先跑通，再变强**。
- **安全闸门不变原则**：SQL 从哪来可以变（模板 → LLM → 后续新 pipeline），但**执行前的安全入口永远不变**（M3 只读检查 → M4 叠加 RBAC / 敏感字段 → 后续一直在同一入口演进）。这是后面所有阶段安全讨论的地基，也是面试里最好讲的一条主线。
- **敏感字段从建表第一天就标记**：`users.email / users.phone` 在 M1 的 ORM 模型和 schema_desc 就标了敏感，M4 才有据可拦——安全是"进 schema → 全链路"的设计，不是事后补文档。
- **契约先行与增量扩展**：`AgentResponse` 从 M3 固定简化版起步，M5 只增量扩展不改变旧字段含义；`PageResponse / ErrorResponse` 从 M2 固定形状，演示页、EvalOps、Agent 错误路径全部复用——**契约稳定是前后端和评测系统协作的前提**。
- **确定性 seed + 固定业务事实**：评测标准答案的基础。seed 不依赖自增 ID，固定事实用业务键（sku / channel_code 等）定位，M3 模板和 M6 smoke 复用同一批稳定数据；这条原则一路延续到 14 表（GMV `11285752.00` 从 Phase 2.7 起成为标准答案）。
- **评测前置思想**：`eval/cases_plan.md` 的 32 条问题在 M3 就设计好，M6 才抽 6 条 smoke 落地——先想清楚"要测什么"，开发才有方向，不给"功能很多但没业务问题支撑"留空间。
- **API seam 评测**：EvalOps-lite 用 TestClient + 内存 SQLite 调真实路由，而不是直接调内部函数——同时验证 API 契约、Trace、SQL Tool 和 chart_spec，不会因为绕过路由而漏掉真实调用链问题。
- **数据库升级的兼容策略**：升级 14 表时保留旧字段（`orders.product_id`、`products.category`），旧 API / 模板 / smoke 照跑，新口径在 `metrics.yaml` 声明——**升级不破坏 v1**，这条策略让 Phase 3A 的 M8 baseline 能直接在 14 表新库上跑。
- **数据质量彩蛋**：在**不破坏主键 / 外键 / 唯一约束**的前提下刻意埋入真实业务问题（未支付 `paid_at IS NULL`、`canceled/cancelled` 拼写差异、源单号重复、金额不一致、负数退款）——让评测集从"干净玩具"走向"真实数据挑战"，也是后面 Phase 3A 修 `order_status` 口径的素材。
- **最小实现原则**：Redis 只落 `NullCache` 骨架、JSONL 而非 SQLite 存 trace、LLM 只实现 DeepSeek 一个 provider——每个都是"够用就停"，把复杂度留给真正需要它的阶段。

### 阶段设计取舍

- **先 v0 模板闭环，再 v1 LLM 化**：没有让 M3 直接接 LLM。模板未命中先"诚实说不会"，换来端到端链路、安全入口和契约先稳定；LLM 是叠加在稳定地基上的能力，而不是一开始就依赖的变数。
- **安全不靠 prompt，靠执行前硬拦截**：sqlglot AST 只读 → RBAC → 敏感字段，层层都是代码判断不是模型自觉；LLM 失败也结构化拦截、**不降级假 LLM**——"宁可不答，不答错"。
- **AgentResponse 契约增量扩展**：M5 不推倒 M3 的响应结构，旧字段含义不变、只加新字段——避免破坏已通过的模板链路和即将接入的评测、演示，也符合"公开契约只加不改"的后端习惯。
- **EvalOps-lite 选 API seam 而非直接调 pipeline**：多花一层 TestClient 成本，换来验证的是"用户真正走的路"，同时用内存 SQLite 不污染 MySQL 主库。
- **Redis 只落 NullCache 骨架**：M2 不接真实 Redis client，避免把缓存逻辑散进业务 API；这是计划允许的降级边界，接口形状留好，后续可替换实现。
- **数据底座一次升级到位（7 → 14 表）**：与其在 Phase 3A 边做边加表，不如先把"接近真实企业分析系统"的库一次建好——让后续 Schema Retrieval、JoinPath、QueryPlanStep 面对的是真实复杂度；代价是迁移和 seed 工作量大，但换来后面所有模块的高可信度评测。
- **刻意不做的事**：行级权限与脱敏样例（M4 只做表级 / 字段级）、真实 Redis 缓存、完整 32 条评测（M6 只落 6 条 smoke）、RAG / Hybrid 检索（知识库语料就位但链路未实现）、真实 LLM usage 统计（CostInfo 字段预留）——每件都明确记录"留给哪个阶段"，不为凑能力写已完成。

### 面试怎么讲

我做的是一个企业经营数据分析 Agent，目标是让运营/客服用自然语言安全查询订单、退款、渠道 GMV 等指标。Phase 2 从 0 到 1 搭建了一个 **SQL Agent v1**，核心方法是"先跑通、再变强、然后给它装上尺子和眼睛"。v0 阶段先用 5 条模板 SQL 跑通端到端闭环，并把 **sqlglot AST 只读检查**固定为所有 SQL 执行前唯一入口；v1 阶段接入 DeepSeek LLM 生成 SQL，但模型生成的 SQL 与模板 SQL 走**同一个安全闸门**——AST 只读 + 表级 RBAC + 字段级敏感字段拦截，安全不靠 prompt 靠硬拦截。随后把响应扩展成结构化 AgentResponse 契约（答案/SQL/表格/图表/工具调用/trace），SQL 执行收进统一 SQL Tool，每次查询写 JSONL Trace，并搭了 EvalOps-lite（6 条 smoke 走真实 API 评测）和 Streamlit 演示页，形成可评测、可演示的 v1 闭环。最后把数据底座从 7 张表升级为 **14 张物理表 + 1 万级确定性订单数据**，内置固定业务事实（如 GMV 11285752.00）和数据质量彩蛋，为阶段三的 Text2SQL 深化评测提供真实复杂度。

1. **[基础追问] 安全链路从 M1 到 M4 是怎么层层叠加的？**

   三层递进：M1 在**模型层标记敏感字段**（`users.email / users.phone` 建表时就标敏感，给拦截留依据）；M3 固定执行入口——所有 SQL 先过 **sqlglot AST 只读检查**，只允许单条 SELECT，DROP/DELETE 等直接 blocked；M4 叠加**表级 RBAC + 字段级敏感字段拦截**——按角色矩阵判断能否访问某表，`SELECT * FROM users` 也会被展开检查是否碰到敏感列。核心是"SQL 来源可以变（模板 → LLM → 后来的新 pipeline），执行前的安全入口不变"，这条原则从 v0 一路延续到现在。

2. **[工程/深挖追问] EvalOps-lite 为什么选 API seam（TestClient + 内存 SQLite），而不是直接调内部函数？**

   因为评测要验证的是"用户真正走的路"——**HTTP** 请求进来、经过路由、Schema 校验、编排、SQL Guard、执行、返回响应整条链路，而不只是某个函数的正确性。直接调 pipeline 会绕过路由和契约，可能漏掉真实调用链问题（比如字段没进响应、Guard 没被调用）。API seam 用 TestClient + 内存 SQLite 调真实路由，同时覆盖 AgentResponse、Trace、SQL Tool、chart_spec 和安全拦截，且不污染 MySQL 主库——成本是包装一层测试客户端，收益是评测可信。

3. **[工程/深挖追问] 为什么要把数据从 7 表升级到 14 表 + 1 万级订单？数据质量彩蛋的意义是什么？**

   7 表是"教学版"：订单一单一商品、类目只是字符串、没有优惠券多对多、价格历史、宽表。这样的库能证明链路能跑，但撑不起后续 Schema Retrieval、JoinPath、QueryPlan 的评测——问题太简单，任何方案都显得好用。14 表引入订单明细（一单多品）、桥接表（多对多）、递归类目树、SCD 价格历史、宽表 vs 星型模型选择这些**真实 SQL 难题**；1 万级数据让聚合、join、性能问题真实起来。数据质量彩蛋（未支付订单、canceled/cancelled 拼写差异、金额不一致、负数退款）是**在不破坏约束的前提下模拟真实脏数据**，让 Agent 从"在干净玩具库答对题"走向"面对真实数据挑战"——这些彩蛋后来确实成了 Phase 3A 修口径的素材。

4. **[工程/深挖追问] JSONL Trace 为什么够用？什么时候需要换？**

   M5-M6 阶段 trace 的消费者只有一个评测脚本：按行读取、判断 pass/fail、记录 error_type。JSONL"追加写入、按行读"正好满足，不需要 SQLite 表或查询接口——这是最小实现。什么时候需要换？**当 trace 需要被多路并发查询、需要按条件聚合、或者演示页/平台要在线展示时**（后来 M16 接 TraceRouter、Phase 3B 接 LangFuse 就是这两个触发点）。当时的取舍是"为现在够用的需求做最小实现，把扩展点留给真正需要的阶段"。

5. **[压力追问] 数据里埋了彩蛋（金额不一致、负数退款），评测标准答案怎么确定？会不会模型查对了但被标准答案冤枉？**

   这正是固定事实 + 确定性 seed 的意义：标准答案不是"模型输出什么就信什么"，而是**先用参考 SQL 在确定性数据上执行得到基准值**，再把它固化成语义明确的固定事实（比如 GMV = 11285752.00，Aurora 退款率最高）。彩蛋本身是数据事实，不是评测陷阱——比如金额不一致的 5 条订单是刻意设计的可解释样例，负数退款是合法的冲销记录，它们的口径都写进了 `docs/state/database-current-state.md` 和 metrics.yaml。只要问题语义和口径定义一致，标准答案不会冤枉模型；真正会冤枉的是口径定义不清（比如 `paid_at` vs `created_at`），而这类问题在 Phase 3A 修口径时被逐一暴露和校准——数据彩蛋反而帮我们把口径磨清楚了。

### 阶段成果与边界

- 完成：
  - **v0 端到端闭环**：工程骨架 + 7 表数据底座（Alembic + 确定性 seed + 固定事实）+ API 基础 + 模板 SQL 查询 + sqlglot 只读检查
  - **v1 LLM 化不放松安全**：DeepSeek 生成 SQL（模板优先、未命中才调）、RBAC 表级 + 字段级、敏感字段拦截、LLM 失败结构化拦截不降级
  - **结构化 Agent 输出**：AgentResponse 增量扩展（tables_used / docs_used / chart_spec / cost / tool_calls / error_type）、SQL Tool 统一执行入口、JSONL Trace、Chart Tool（bar / line / horizontal_bar）
  - **评测与演示**：EvalOps-lite 6 条 smoke 全绿（API seam）、Streamlit 演示页、v1 验收报告（只写已实现能力）
  - **Phase 2.7 数据库升级**：14 张物理表 + 1 万级订单 + 固定业务事实 + 数据质量彩蛋 + relations.yaml / metrics.yaml 口径 + 16 条 challenge / 10 条正式回归 case 预置，旧链路完全兼容
  - **全量 pytest 演进**：5 → 9 → 15 → 19 → 24 → 27 → **31 passed**（M0 → Phase 2.7.1）
- 没完成 / 刻意不做：
  - **真实 Redis 缓存**——只落 `NullCache` 骨架，接口形状留好
  - **行级权限与脱敏样例**——M4 只做表级 / 字段级核心边界
  - **完整 32 条评测**——M6 只落地 6 条 smoke，32 条清单在 `eval/cases_plan.md` 规划
  - **RAG / Hybrid 检索**——`knowledge_docs` 语料和 `kb_docs/` 就位，链路未实现
  - **真实 LLM usage 统计**——CostInfo 字段预留，token 先留空
  - **复杂图表推荐**——只覆盖基础 bar / line / horizontal_bar 和单指标柱图

### 口径说明（以 2026-07-31 为准）

> 早期模块记录是**时间切片**，记录的是当时状态，未回溯修改；以下为后续阶段校准后的最新口径，读早期记录时以本节为准。

- **数据库**：本总结正文中的"7 表"是 Phase 2.7 之前的状态；当前是 **14 张物理表 + 1 万级数据**，固定事实与口径速查见 [database-current-state.md](state/database-current-state.md)。
- **安全口径**：M4 记录中"`admin` 可以看全量"是当时状态；M14-lite 定案后**敏感字段优先于 admin 角色**，`users.email / users.phone` 在任何角色下都不能通过 Text2SQL 直出。
- **评测体系**：M6 的"6 条 smoke"是当时全部；M8 起扩展为三层（10 formal + 16 challenge + 32 diagnostic），M17 起 scorer 分层（L1/L2/L3）。
- **Trace**：M5 的 JSONL 是当时唯一入口；M16 起为 TraceRouter + 可选 LangFuse 双写，JSONL 仍是默认路径。
- **指标口径**：GMV / 退款率等口径在 Phase 2.7.1 和 Phase 3A 过程中实地查库校准（如 `order_status` 共 6 种状态、整单退款占 10% 需 LEFT JOIN、`refunds.source_order_no` 与 `orders.order_no` 命名空间不兼容不可 join），以 `docs/state/database-current-state.md` 为准。

### 下一阶段怎么接

- **Phase 3A Text2SQL 深化（M8-M14）**：直接基于 14 表新库跑三层评测——M8 冻结旧链路 baseline、M9-M11 建设 Schema Retrieval / QueryPlan / 新 pipeline、M13 质量修复到 formal 10/10。完整衔接见后文 **Phase 3A 阶段总结**。
- **Phase 2 的资产复用**：固定业务事实和口径是 Phase 3A 评测标准答案的底料；`relations.yaml` 是 M9 JoinPath 的单一事实源；AgentResponse 契约一路沿用（后续只增不改）。
- **独立 EvalBench 项目**：EvalOps-lite 的 6 条 smoke 和 cases_plan 的 32 条规划是平台化的起点。
- **可复用的阶段级验证命令**：阶段收口时全量 pytest 预期 **31 passed, 1 warning**；EvalOps-lite 入口 `python -m eval.run_eval --cases eval/cases/smoke.yaml`（预期 6/6 passed）；数据库迁移检查 `alembic check`（预期 No new upgrade operations detected）。

## ★ Phase 3A M8 回归基线冻结

（2026-07-22）

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

“M8 我在 Text2SQL 深化前先做了**真实 baseline 冻结**。我没有一上来就调 prompt 或重写链路，而是把 10 条 formal regression 和 16 条 challenge 跑在旧链路上，报告里记录 SQL、trace_id、安全状态、issue tag 和 manual review 标记。这样后续 M9-M12 做 Schema Retrieval、QueryPlan、新 pipeline 和对照报告时，不是凭感觉说‘更好’，而是能和同一批问题的旧链路表现对比。”

“这个模块最重要的不是分数好不好看，而是**先把测量对象固定住**。M8 发现旧链路安全题能拦截，但允许类 SQL 失败集中在多表输出列契约、别名和表选择上。这些失败点直接影响了后续设计：M9 做字段级 Schema Retrieval 和 JoinPath，M10 做 QueryPlanStep，M11 做 trace_steps，M12/M13 再用报告和 trace 继续定位质量问题。”

> 现在口径：M8 的 baseline 报告是 Phase 3A 早期“旧尺子”阶段产物。M13 后发现部分旧 eval 会把 `GMV=NULL` 这类错误结果误判通过，所以面试中引用 M8 分数要谨慎；更推荐说“先冻结旧链路 baseline，再在 M13 用 expected_value/result_match 思路修正评测可信度”。当前可包装的真实改进口径是 M13 后 formal **约 4/10 → 10/10**、challenge **约 6/16 → 14/16**、diagnostic **约 12/32 → 23/32**，这里的“约”来自旧报告曾存在误判。

1. **面试官问“为什么要先做 baseline？”**

   可以答：“如果没有 baseline，后续改 Schema Retrieval 或 prompt，很容易只凭个别样例说有效。M8 先固定同一批 formal/challenge 问题、同一套报告字段和 issue tag，后续新链路才能和旧链路同题对照。”

   这段突出的是 **先测量，再优化**。

2. **面试官问“baseline 分数不高会不会不好看？”**

   可以答：“baseline 的价值不是好看，而是真实。旧链路低分说明问题确实存在，后续优化才有目标。更重要的是，我没有为了好看删 case 或放宽期望，而是保留失败 SQL、issue tag 和 trace_id，方便后续定位。”

   这段突出的是 **不美化指标**。

3. **面试官问“M8 对后续模块有什么作用？”**

   可以答：“M8 把失败形态结构化了：是缺表、缺列、安全 mismatch，还是需要人工复核。后续 M9/M10/M11 每个模块都可以针对这些失败类型补能力，M12 再生成新旧链路对照报告。”

   这段突出的是 **评测驱动架构演进**。

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

## ★ M8.5 扩展为 32 条 diagnostic

（2026-07-23）

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

“M8.5 我把 Phase 3A 的评测从普通 pass/fail 扩展成了**按能力维度诊断的 benchmark**。原来的 16 条 challenge 继续作为唯一源，新文件只新增 16 条 capability-focused case，最终通过 `--cases + --extra-cases` 拼成 32 条。每条 case 都标注它关注 schema_retrieval、join_path、query_plan、local_schema_prompt、trace_steps 还是 security_guard，报告也按 capability 汇总。”

“这里的关键设计是：旧链路不能验证的新 pipeline 能力，不硬算失败，也不假装通过，而是标成 `skipped_due_to_pipeline_mode`。比如旧链路没有 QueryPlan、local schema 和 trace_steps，那这些检查在 baseline 下只能 skip。这样报告能区分‘能力尚不可验证’和‘SQL 真的答错’，后续 M11/M12 跑新 pipeline 时，才有公平对照。”

> 现在口径：M8.5 的 32 条 diagnostic 是诊断素材，不是正式硬门。M13 后 diagnostic 到 **23/32**，M14-lite 又清理了边界：递归类目、知识库归因、完整 EvalOps、JSON mode 大实验都不在当前 Text2SQL 收口范围内；`db_plan_003` 这类 Hybrid 归因题已标为 non_blocking/manual_review。面试时不要说“我要把 diagnostic 修满”，而要说“diagnostic 用来暴露未来能力缺口”。

1. **面试官问“diagnostic benchmark 和 regression 有什么区别？”**

   可以答：“regression 是正式回归硬尺子，关注核心问题是否稳定；diagnostic 是能力仪表盘，按 schema retrieval、join path、query plan、trace、安全等维度设计，用来发现链路哪一层弱。它不应该被当成所有 case 必须立刻满分的目标。”

   这段突出的是 **评测分层**。

2. **面试官问“为什么旧链路不支持的检查要 skipped？”**

   可以答：“因为旧链路没有 QueryPlan 和 trace_steps，把这些检查判失败是不公平，也会混淆原因。skip 表示当前 pipeline mode 无法验证这类能力。等新 pipeline 接入后，同一批 case 再变成可验证项。”

   这段突出的是 **评分口径诚实**。

3. **面试官问“为什么不把 32 条都作为硬门？”**

   可以答：“因为其中有些是未来能力探针，比如递归类目、知识库归因、复杂 Hybrid 语义。如果当前阶段为了分数硬补 prompt，很容易把未来语义层和 SQL Guard 设计塞进 Text2SQL。M8.5 的价值是发现这些边界，而不是逼当前模块全做完。”

   这段突出的是 **知道哪些失败该修，哪些该留给后续架构**。

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

## ★ M9 Schema Retrieval 与 JoinPath

（2026-07-23）

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

“我给 Text2SQL 加了一层**字段级 Schema Retrieval **和 **结构化 JoinPath**。用户问题进来后，系统不再把全库 schema 一股脑塞给 LLM，而是先从 domain pack 生成 **field_doc、metric_doc、relation_doc**，再用 keyword + vector 两路召回当前问题相关的表、字段、指标和关系。多表查询不让模型自由猜 Join，而是从 `relations.yaml` 里找结构化 **JoinPath**。”

“这一步的价值是把 Text2SQL 的第一层不确定性拆出来：到底有没有召回正确表字段、有没有找到合法 Join、指标文档有没有命中，都可以在 M9 单独测试。自动化结果证明 formal 允许类 SQL 的表召回、字段指标召回和多表 JoinPath 达到阶段目标，为后续 M10 QueryPlan 和 M11 局部 Schema SQL prompt 打了可验证基础。”

1. **面试官问“为什么不直接把全库 schema 给 LLM？”**

   可以答：“全库 schema 会让 **prompt 很长**，而且模型容易在**不相关表字段里漂移**。M9 先做 schema retrieval，只给当前问题相关的字段、指标和关系，既减少噪音，也让失败可以归因到召回层。”这段突出的是 **局部上下文** 和 **可诊断性**。

2. **面试官问“JoinPath 怎么避免模型乱连表？”**

   可以答：“Join 关系不靠模型自由发挥，而是来自 `relations.yaml`。SchemaGraph 根据召回到的表和结构化关系找 JoinPath，后续 QueryPlan 只允许引用这些 relation id。这样 Join 从自然语言猜测变成了可校验的关系事实。”这段突出的是 **关系单一事实源**。


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

## ★ M9.1 / M9.2 试验 embedding

（2026-07-23 ~ 2026-07-24）

**简述**：这两次实验已经合并进主线：DataPilot 现在 **默认仍用 in-memory 检索**，同时 **可选支持 Milvus + SiliconFlow 真实中文 embedding**。

### 这次做了什么

M9.1：验证 **Milvus 作为 Schema Retriever 的向量存储** 是否能跑通。它做的事情很单纯：把 M9 的 `VectorIndex` 接口换一个实现，默认链路不变，显式传入 `MilvusVectorIndex` 时才会连接 Docker Milvus。实验结果证明 Milvus adapter 能正常建 collection、写入 schema document 向量、flush、load、search。

M9.2：把 M9.1 里的 fake embedding 换成 **SiliconFlow 真实中文 embedding**。这次测试了 **BAAI/bge-m3** 和 **Qwen/Qwen3-Embedding-0.6B**，并把报告拆成两个视角：**merged_top30** 看当前系统最终召回效果，**vector_only_top12** 看 embedding 模型自己的排序能力。

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

“M9.1/M9.2 我把 Schema Retrieval 的向量层做成了**可插拔后端**。默认路径仍然是本地 in-memory，保证自动化测试和普通开发不依赖外部服务；真实路径支持 Milvus 向量库和 SiliconFlow embedding，并用 formal / challenge / diagnostic case 做 A/B 对比。实验里真实 embedding 的 vector-only 召回确实更强，但当时 merged recall 已经被 keyword + relations.yaml 补得比较满，所以我没有把默认链路切到联网服务。”

“这个取舍很适合面试讲：我不是为了简历技术栈强行上 Milvus，而是先把 adapter、provider、smoke 和对比报告做好，让它成为可选能力。等后续进入 RAG 或 schema 规模变大，再通过配置显式开启；平时 pytest 和本地启动仍然稳定、可重复。”

1. **面试官问“你为什么接 Milvus 但不设为默认？”**

   可以答：“因为默认链路要服务 pytest、CI、本地开发和新同学启动，不能依赖 Docker Milvus 或联网 embedding。Milvus 是生产候选能力，应该显式开启；默认路径保持 deterministic in-memory，保证工程稳定。”这段突出的是 **默认稳定，能力可选**。

2. **面试官问“真实 embedding 实验有什么结论？”**

   可以答：“Qwen3 embedding 在 vector-only 召回上优于 fake embedding，说明真实中文 embedding 有价值。但最终 merged 结果还受 keyword 和 relations.yaml 影响，当前 eval 没明显收益，所以我没有盲目切默认，而是保留为后续 RAG / 大规模 schema 的配置能力。”

3. **面试官问“可插拔设计体现在哪里？”**

   可以答：“上层 retriever 只依赖 `VectorIndex.search()` 和 `EmbeddingProvider.embed()` 这两个协议。InMemory、Milvus、Deterministic、SiliconFlow 都实现这些边界，后续换 Qdrant 或其他 embedding provider，不需要改 Schema Retrieval 主流程。”这段突出的是 **接口隔离**。


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

## ★ ★ M10 QueryPlanStep 与自检

（2026-07-24）

**简述**：M10 给 Text2SQL 加了一个 **SQL 生成前的结构化计划层**，像后端接口里的 DTO + Validator，先检查“准备查什么”是否合法，再交给后续 SQL 生成。

### 先用大白话讲

M9 已经把问题相关的表、字段、Join 召回出来了，但如果让 LLM 直接拿着这些信息写 SQL，它仍可能**编造**不存在的字段、乱连表、或者在 SQL 里偷查**敏感数据**——这在代码里叫"幻觉"，在企业里叫"事故"。M10 的做法是：在 LLM 写 SQL 之前，先让它填一张**"申请表"（QueryPlanStep）**，写明要查哪些表、用哪些字段、按什么 Join 条件、输出什么列；填完后系统逐项核对这张申请表是否都在 M9 的合法"菜单"里。整个过程相当于后端接口收到请求后先做参数校验——没通过就不往下走，通过了才交给 M11 生成 SQL。

### 这次做了什么

M10 在 Schema Retrieval 和 SQL 生成之间加入了 **QueryPlan 计划层**。模型不能再拿到几张表后直接自由写 SQL，而要先提交一份结构化“查询施工单”，系统检查通过后才能进入下一阶段。

1. **为什么要增加计划层。**

   M9 已经能召回相关表、字段、指标和 JoinPath，但“召回正确”不代表“模型一定会正确使用”。模型仍可能编造字段、遗漏关键表、使用非法 Join，或者在生成 SQL 前就计划访问敏感信息。

   如果等 SQL 生成后才发现这些问题，检索错误、规划错误和 SQL 生成错误会混在一起，很难判断应该修哪里。

2. **把查询意图变成可以校验的数据结构。**

   M10 新增 `QueryPlan` 和 `QueryPlanStep`。每个步骤需要声明：

   - 使用哪些表和字段；
   - 使用哪些业务指标；
   - 有什么过滤、聚合、分组和排序；
   - 使用哪些 Join relation id；
   - 最终准备输出哪些列。

   Prompt 中的 JSON Schema 直接从 Pydantic 模型生成，避免代码字段已经变化，而 prompt 示例仍停留在旧版本。

3. **建立 SQL 生成前的自检门。**

   `validate_query_plan()` 会将计划逐项对照 M9 产出的 `SchemaGraph` 和 `DomainSchema`：

   - 表或字段不存在：`missing_table / missing_column`
   - Join 不在允许路径中：`invalid_join_path`
   - 多个 SQL 查询步骤：`unsupported_multi_step_plan`
   - 访问敏感字段：`sensitive_field_access`
   - 指标不存在或当前上下文不可用：`invalid_query_plan`

   Join 必须引用 `relations.yaml` 中的 relation id，不接受模型自由描述一条关联关系。

4. **给未来扩展留接口，但没有提前实现多 SQL Agent。**

   `QueryPlan.steps` 使用列表，并保留 `step_id`、`step_index` 和 `depends_on`，方便未来扩展 Plan-and-Execute 或 SQL/RAG Hybrid。

   但 M10 明确只允许一个可执行 `sql_query` step。数据结构能扩展，不等于当前执行器已经支持多 SQL；越过边界的计划会被直接阻断。

5. **控制可观测信息，不保存原始推理过程。**

   QueryPlan 只保留一句话 `purpose` 说明步骤目的，不增加 `thoughts` 或原始 CoT。这样既能让 trace 看懂计划，又不会把模型的自由推理当成稳定接口。M10 只完成计划结构和自检，没有提前接入 `/api/query`；真实 pipeline 串联留给 M11。

> **M24 章节结束时补充**：M10 当时只检查“计划引用是否合法”，还不能验证“生成的 SQL 是否忠实执行计划”。到 M24，`QueryPlanStep` 增加了 `output_expressions`，pipeline 使用 SQLGlot AST 严格核对 ORDER BY、排序方向、LIMIT 和输出投影；`steps` 仍只是多步骤预留接口，真正的 Multi-SQL 仍未实现。

### 新概念

- **QueryPlanStep**：一次查询计划里的一个步骤。可以理解成 SQL 生成前的“施工单”：**写明要查哪些表、用哪些字段、按什么指标聚合、需要哪些 Join。**
- **Plan Validation**：计划自检。它不是执行 SQL，而是检查计划引用的东西是否都在可信 Schema 里，类似 SpringBoot Controller 收到请求后先做参数校验。
- **CoT 不外露**：M10 不保存 `thoughts` 或原始推理过程，只保留 `purpose` 这种一句话意图摘要。这样既能调试，又不会把模型自由推理塞进公开响应。
- **Join relation id**：Join 不靠自然语言猜，而是使用 `relations.yaml` 里的关系 ID，例如 `order_items_order`。这让“能不能这么连表”变成可校验事实。
- **unsupported_multi_step_plan**：当前阶段的边界标签。系统知道未来可能有多 SQL、多步骤分析，但 M10-M12 不执行这种计划。

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

“M10 我在 Text2SQL 里加了一层**可校验的中间表示 QueryPlanStep**。普通 NL2SQL 是直接从问题到 SQL，失败时只能看最终 SQL；M10 让模型先声明准备查哪些表、哪些字段、哪些指标、用哪些 Join relation id，再由本地 validator 检查这些对象**是否来自 M9 的局部 SchemaGraph**。这样错误可以在 SQL 生成前暴露出来。”

“这层中间表示的价值是把模型输出从自由文本变成结构化契约。评测和 trace 可以稳定打出 `missing_column`、`invalid_join_path`、`unsupported_multi_step_plan`、`sensitive_field_access` 这类 issue tag，后续排查就能知道问题发生在计划层，而不是等 SQL 执行报错后再猜。”

1. **面试官问“QueryPlanStep 和直接生成 SQL 比有什么优势？”**

   可以答：“直接 SQL 太难诊断，错了只能看一长串 SQL。QueryPlanStep 把模型意图拆成表、字段、指标、Join、过滤、聚合和输出列，本地 validator 可以逐项检查。这样错误更早暴露，也更容易告诉模型或开发者到底错在哪里。”这段突出的是 **结构化意图表达**。

2. **面试官问“为什么用 relation id 表示 Join？”**

   可以答：“Join 条件应该来自 `relations.yaml`，而不是模型现场编。M10 让 QueryPlan 引用 relation id，validator 再检查 id 是否存在于局部 SchemaGraph。这样 JoinPath 就是结构化事实，不是 prompt 里的建议。”这段突出的是 **Join 可校验**。

3. **面试官问“为什么预留多 step 但当前只允许单 SQL？”**

   可以答：“Pydantic 结构上预留 `steps`，是为了后续 Plan-and-Execute 或 Hybrid；但 Phase 3A 当前执行器只支持单 SQL。如果此时放开多个 sql_query step，会把事务、安全、结果合并和 trace 都提前复杂化。所以 M10 先把多 SQL plan 拦成 `unsupported_multi_step_plan`。”这段突出的是 **结构可扩展，执行边界收紧**。

4. **面试官问“安全为什么还要 SQL Guard 兜底？”**

   可以答：“Plan Validation 是生成 SQL 前的预检，**它能提前发现计划层访问敏感字段或编造字段**；但模型最后生成的 SQL 仍可能偏离计划，所以执行前必须再走 SQL Guard。两层分别在计划阶段和运行阶段拦截，形成纵深防御。”

   这段突出的是 **预检不替代最终门禁**。

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

## ★ ★ M11 新 Text2SQL Pipeline 与 Trace Steps

（2026-07-24）

**简述**：M11 把 M9 的 **Schema Retrieval / JoinPath**、M10 的 **QueryPlanStep 自检** 和 M5 的 **SQL Tool / Trace** 串成了一条真正能从 `/api/query` 触发的新 Text2SQL 链路。

### 先用大白话讲

评测或调试时传 `force_new_pipeline=true`，就会强制绕过模板，走 `schema_retrieval -> query_plan -> local_schema_sql -> sql_guard -> sql_execution`，并把每一步写进 JSONL 的 `trace_steps`。

可以把 M9 和 M10 理解成已经造好的几台机器：一台负责找表和字段，一台负责检查查询计划，但它们还没有接上真正的生产线。M11 做的就是把这些机器按顺序连起来，让一个自然语言问题能够从 API 进入，经过检索、计划、校验、SQL 生成、安全检查和数据库执行，最后返回结果；哪台机器出错，trace 就记录在哪一步停下。

所以 M11 的核心价值是：把前面分散的能力变成一条**真实可运行、失败可定位、旧链路不受影响**的新 Text2SQL 流水线。

### 这次做了什么

M11 把 M9 的 Schema Retrieval、M10 的 QueryPlan 和已有 SQL Tool 真正串成一条可执行的 Text2SQL pipeline，并让每一步都留下结构化 TraceStep。

1. **为什么需要单独做 pipeline 串联。**

   M9 和 M10 已经分别解决了“找哪些 Schema”和“准备怎么查”，但它们仍是独立能力，没有进入真实 API 请求。

   如果只在单元测试里验证 planner，而 `/api/query` 继续走旧模板链路，评测报告就无法证明新方案真的被执行。

2. **增加显式入口，不破坏旧链路。**

   API 请求新增可选字段 `force_new_pipeline`。默认值为 `false`，原来的模板优先路径保持不变；只有显式设置为 `true` 时，才强制进入新 Text2SQL pipeline。

   eval 侧的 `pipeline_mode=new_text2sql` 会自动发送这个开关，避免报告写着“新 pipeline”，实际请求却仍走旧链路。

3. **串起完整执行流程。**

   新链路依次完成：

   `schema_retrieval`
   → `schema_context`
   → `join_path`
   → `query_plan`
   → `plan_validation`
   → `sql_generation`
   → `sql_guard`
   → `sql_execution`
   → `chart_generation`

   SQL 生成器只能看到已经召回和验证过的局部 Schema、指标和 JoinPath，从源头减少全库 prompt 噪音。

4. **复用原有 SQL Tool，不新建第二套安全边界。**

   新 pipeline 生成的 SQL 仍交给 `run_sql_tool()`。SQL Guard、RBAC、敏感字段检查和数据库执行逻辑没有被复制到 pipeline 中。

   这样 planner 可以提前发现风险，但真正执行前仍必须经过统一 SQL Guard，形成清晰的分层防线。

5. **失败时诚实阻断，不偷偷降级。**

   Schema 没召回、QueryPlan 无法解析、自检失败或 SQL 生成失败时，pipeline 返回带 issue tag 的结构化 blocked 结果。

   它不会偷偷退回旧模板，也没有在这一阶段加入自动 SQL 修复。这样后续报告能看到新 pipeline 的真实能力，而不是被 fallback 掩盖的问题。

6. **用 TraceStep 记录每一步发生了什么。**

   每个步骤都会记录名称、顺序、类型、状态、耗时、错误类型和 metadata。Schema 表字段数量、Join relation id、计划内容和 SQL 返回行数等信息都能进入 JSONL trace，但不会塞进公开 API 响应。

   这为 M12 的新旧 pipeline 对照和后续失败归因提供了证据。

   最终 pipeline 聚焦测试 **4 passed**，相关组合测试 **12 passed**，全量测试 **67 passed**。M11 完成的是“链路真实接通并可观察”，正确率评测和质量修复分别留给 M12、M13。

> **M24 章节结束时补充**：这里描述的是 M11 初版链路。M16B 后 TraceStep 已升级为 live lifecycle；M24 又在 SQL 生成与执行之间加入 AST fidelity，并在执行后增加 `output_contract`。因此“九步 pipeline”是历史结构，不是当前完整步骤清单；当前仍坚持 SQL Guard 先于语义合同，SQL Tool 执行时再次检查安全。

### 新概念

- **force_new_pipeline**：API 侧的显式开关。默认 `False` 保持旧模板优先；设为 `True` 才强制走新 Text2SQL pipeline。它像 SpringBoot 里一个只给灰度/评测用的开关，不改变普通用户默认路径。
- **pipeline_mode**：eval 侧的配置字段。`pipeline_mode=new_text2sql` 会让 runner 自动给 `/api/query` 发送 `force_new_pipeline=true`，避免报告写“新链路”，实际却跑旧模板。
- **TraceStep**：一次请求里的分步骤日志。它比 `tool_calls` 更细：`tool_calls` 只记录工具调用，`trace_steps` 会记录 schema 检索、计划生成、自检、SQL 生成、SQL Guard、SQL 执行和图表决策。
- **局部 Schema SQL prompt**：M11 不再把全库表字段都塞给 SQL 生成器，而是只给 QueryPlanStep 和 SchemaGraph 里出现的上下文。这样可以减少 prompt 噪音，也方便失败归因。
- **结构化 blocked**：新链路失败时不偷偷回到旧模板，也不自动修 SQL，而是返回 blocked 响应和 issue tag。这样对照报告会诚实暴露新链路质量。

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

“M11 我把 Text2SQL 从一条黑盒 LLM 调用，升级成一条**可观测、可校验、可灰度的新 pipeline**。以前用户问一句话，系统直接给 SQL，失败时很难判断错在 schema 召回、查询计划、SQL 生成还是安全拦截。M11 后，请求会先走 **Schema Retrieval 和 SchemaGraph**，只把相关表字段交给模型；再让模型生成结构化 **QueryPlan**，本地**校验**表、字段、指标、Join 是否来自可信上下文；最后才基于局部 Schema 生成 SQL，并统一经过 **SQL Guard** 执行。每一步都会写成 `TraceStep`，所以后续 M12 能用报告证明新链路到底走了哪些步骤、在哪一层失败。”

1. **面试官问“你为什么要在 Text2SQL 前加 QueryPlan？”**

   可以答：“直接让 LLM 生成 SQL 太黑盒，失败时只能看到最终 SQL。QueryPlan 相当于先让模型说清楚‘准备查哪些表、用哪些字段、按什么指标和 Join 查’，再由本地 validator 校验它有没有编造表字段或越权访问。这样可以把错误提前挡在 SQL 生成前，也能把失败归因拆清楚。”这段突出的是 **结构化中间层** 和 **本地校验**，比单纯说“优化 prompt”更有工程含量。

3. **面试官问“你怎么保证 LLM 生成的 SQL 安全？”**

   可以答：“M11 不把安全押在 prompt 上。QueryPlan 阶段会预检表、字段、Join 和敏感字段，但最终 SQL 仍统一交给 `run_sql_tool()`，走 SQL Guard 的 AST 只读检查、表级 RBAC 和敏感字段策略。测试里 fake LLM 故意返回 `DELETE FROM orders`，仍会被 SQL Guard 拦住。这说明安全边界在工具层，而不是靠模型自觉。”这段突出的是 **纵深防御**：prompt / plan 可以减少错误，但最终门禁必须在确定性代码里。

4. **面试官问“TraceStep 有什么价值？”**

   可以答：“TraceStep 让一次 Text2SQL 请求从黑盒变成分步骤证据。它记录 schema retrieval、schema context、join path、query plan、plan validation、sql generation、sql guard、sql execution 等步骤，每步都有状态、耗时、错误类型和 metadata。后续做 eval 报告时，不只是知道 case 失败了，还能判断是 schema 没召回、plan 没通过，还是 SQL 执行被 guard 拦截。”这段突出的是 **Agent 可观测性** 和 **失败归因能力**。


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

## ★ M12 对新 pipeline 进行三类测评

（2026-07-25）

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

"核心结论是：新链路的局部 Schema 把 LLM 看到的内容从**全量 14 表几百字段**精简到 **4-7 表几十字段**，Join 条件来自 `relations.yaml` 而不是 LLM 自由发挥，每次请求有完整 9 步 **trace** 可以定位到底是 schema retrieval 召回不足还是 plan validation 拦截还是 SQL Guard 报错。当前瓶颈是 LLM 输出列名不稳定，约一半 case 挂在别名匹配上——但这个对照报告本身已经给出了明确的改进方向。"

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

## ★ ★ M13 pipeline 大修

（2026-07-26）

**简述**：M13 是 M12 收工后的质量修复模块。M12 已经把新旧 pipeline 的差异量出来了，但新 pipeline 通过率偏低；M13 做的不是“盲目调 prompt”，而是先修**评测尺子**，再沿着 trace 一层层定位：到底是评测误杀、指标口径没进 prompt、QueryPlan 选错口径，还是 SQL 生成时关系边用错。按“真实通过”口径重新校准后，最终 formal 新 pipeline 从 **4/10** 提升到 **10/10**，challenge 从 **6/16** 到 **14/16**，diagnostic 从 **12/32** 到 **23/32**。(40%→100%，37.5%→87.5%，37.5%→71.9%)

> ★ Ctrl + 左键 → 查看 M12 发现通过率低后制定的修复计划：[phase3a-issues-and-fixes-v5.md](archive-dormant/phase3a-issues-and-fixes-v5.md)

### 先用大白话讲

M13 像是在修一条“成绩突然很差”的生产线。最开始看报告，很容易把问题全部归咎于模型不会写 SQL；但真正拆开检查后发现，**阅卷答案有错、业务说明书没有完整送到模型手里、模型自己也确实会写错**，三种问题混在了一起。

所以 M13 没有直接堆 prompt，而是先把评测尺子修准，再查看每条 trace：Schema 有没有召回、QueryPlan 选了什么、SQL 最后又用了什么。确认问题属于哪一层后，才分别修数值校验、指标口径传递、商品销售额 Join 和转化率计算。

所以 M13 的核心价值是：建立了**先确认测得准，再根据证据修系统**的 Text2SQL 优化方法，而不是靠反复试 prompt 碰运气。

### 这次做了什么

M13 解决的不是一个单独的 prompt 问题，而是一次完整的 **Text2SQL 质量排查和修复**：先确认评测是否可信，再沿 trace 判断问题发生在指标口径、QueryPlan 还是 SQL 生成阶段。

1. **先发现“分数低”和“分数不可信”是两个问题。**

   M12 报告表面为 formal **6/10**、challenge **8/16**、diagnostic **15/32**。回看实际 SQL 后发现，有些查询虽然被判通过，却使用了错误时间字段，甚至返回 `GMV=NULL`。

   这意味着不能直接根据旧分数调 prompt。按照后来补充的固定事实口径回看，初始真实水平约为 **4/10、6/16、12/32**。

2. **第一步先修评测尺子。**

   原 scorer 对部分指标只检查响应中是否出现 `gmv` 等文本，列名正确不代表结果正确。

   M13 增加 `expected_value`：对于 seed 数据中已经确定的 GMV、净收入等指标，必须比较真实数值。单指标且只有一列时，可以接受模型生成的本地化 alias；多列结果仍严格检查，防止 alias 兜底掩盖错误投影。

3. **定位到指标定义存在，但没有完整进入 prompt。**

   `metrics.yaml` 已经声明了 GMV 的过滤条件和默认时间字段，但 `_format_plan_metrics()` 漏掉了 `filter/default_time_field`。

   结果是模型虽然知道 GMV 公式，却不知道应该按 `orders.paid_at` 统计并排除取消、未支付订单。修复后，QueryPlan 和 SQL 生成阶段都能看到完整业务口径。

4. **根据 trace 区分检索、计划和生成问题。**

   M13 给 trace 增加 `metric_doc_hits`，以及计划中的 tables、columns、metrics、joins、filters 和 output columns。

   这些信息可以判断：相关表是否被召回、QueryPlan 是否选中了它、还是计划正确但 SQL 生成阶段没有使用。由此确认部分多表失败不是 embedding 没召回，而是“销售额”在计划或生成阶段被错误解释成订单头 GMV。

5. **补充有证据支持的通用 SQL 约束。**

   根据失败 case，M13明确：

   - 商品和类目销售额使用 `item_gmv`；
   - `item_gmv` 聚合 `order_items.line_amount`；
   - 商品通过 `order_items.product_id = products.id` 关联；
   - 转化率必须使用浮点除法；
   - active 商品列表应输出名称、类目和状态；
   - QueryPlan 和 SQL generation 使用各自对应的 system prompt。

   JSON mode 和更复杂检索策略仍只保留为假设，因为现有证据不足以证明必须修改。

6. **校准语义等价 alias 和错误 seed 预期。**

   `total_gmv/category_gmv`、`usage_count/coupon_order_count` 等语义等价 alias 可以被接受，但缺表、错表不能靠 alias 放行。

   同时通过直接查询数据库确认：当前 seed 中一级类目销售额最高的是“SaaS 软件”，不是旧 case 中的“数码电子”，因此修正了过时预期。

7. **最终形成一条可解释的改进链。**

   修复后的真实 LLM 结果达到：

   - formal：**10/10**
   - challenge：**14/16**
   - diagnostic：**23/32**

   最终全量测试 **78 passed**。剩余问题被明确记录为 LLM 生成波动、递归类目被 SQL Guard 阻断、部分诊断输出列不匹配和安全诊断缺口，没有为了追求满分继续添加 case-specific 补丁。

> **M24 章节结束时补充**：M13 的 formal `10/10`、challenge `14/16`、diagnostic `23/32` 是当时模型、数据集和 scorer 合同下的历史稳定快照，不能当作当前正确率。M24 已使用 Qwen `qwen3.7-plus`、195-doc corpus 和更严格输出合同完成交错 A/B：Local 为 `24/24/25`（自动 `21/21/22`），Milvus 为 `25/25/25`（自动均 `22/27`）。两阶段口径不同，不能直接用总分判断进步或退化。

### 新概念

- **评测尺子先于修模型**：如果测试本身会把 `GMV=NULL` 判成通过，后续所有通过率都不可信。类比 SpringBoot 项目里先修单元测试断言，再修 Service 逻辑；否则你是在用坏温度计判断病人退烧。
- **固定事实检查（expected_value）**：对 seed 数据里确定的业务事实直接做数值比较，例如 GMV 必须等于 `11285752.00`。这比 `contains: gmv` 更像数据库里的精确断言：不是看列名长得像，而是看结果值对不对。
- **单指标别名兜底**：单指标题只有一列结果时，LLM 可能把列名写成 `"2026年6月GMV"`。M13 的 scorer 会先尝试期望列名和显式 alias；如果仍没命中且只有一列，就用数值判断。这不是放水，因为多列结果仍然严格要求列名。
- **口径漂移**：模型看到“销售额”可能从 `orders.order_amount` 算，也可能从 `order_items.line_amount` 算。业务上商品/类目销售额必须从订单明细算，这就是口径；口径漂了，SQL 能跑也不代表答案对。

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

“我做过一次 Text2SQL 新 pipeline 的质量修复。通过率很低，然后排查原因AI说是语义漂移。但我仔细检查了一下，先发现通过率不可信：GMV=NULL 也会被旧 **eval** 判过，所以先加**固定事实数值校验**；

然后以为是因为 `metrics.yaml` 里没有定义 GMV 的 filter 和默认时间字段导致的有问题，但实测发现：再定位到新 pipeline 重写时**漏传** `metrics.yaml` 的 filter 和默认时间字段，导致模型用 `created_at` 代替 `paid_at`；然后通过 trace 区分召回、计划和 SQL 生成问题，补了 item_gmv、商品表 join、转化率浮点除法等通用约束。按“真实通过”口径重新校准后，最终 formal 新 pipeline 从 **4/10** 提升到 **10/10**，challenge 从 **6/16** 到 **14/16**，diagnostic 从 **12/32** 到 **23/32**。（40%→100%，37.5%→87.5%，37.5%→71.9%）整个过程重点不是调 prompt，而是 eval 校准、语义口径注入、trace 分层诊断和小步验证。”

1. **面试官问“你怎么排查 Agent 效果差？”**

   “我不会先调 prompt，而是先确认评测是否可信。M12 的 Text2SQL 新 pipeline 表面 formal 是 6/10，但我复查 SQL 和执行结果后发现，有些 case 虽然通过，实际算出来是 NULL 或用了错误时间字段。于是我先修 eval，加 `expected_value` 固定事实校验，再沿 trace 看失败发生在 Schema Retrieval、QueryPlan 还是 SQL Generation。这样后面每个修复都能解释通过率为什么变化。”

   这段突出的是 **先校准测量，再修模型**。很多面试回答会停在“prompt 不好”，但企业里更关心你能不能判断指标本身是否可靠。

2. **面试官问“你修复的核心 bug 是什么？”**

   “核心 bug 是 metrics 到 prompt 的**管道断了**。`metrics.yaml` 里已经定义了 GMV 的 filter 和默认时间字段：排除取消订单、`paid_at IS NOT NULL`、默认用 `orders.paid_at`。但新 pipeline 重写 `_format_plan_metrics()` 时只输出了 name/formula/description，没有把 `filter/default_time_field` 传给 LLM。模型看到 `created_at` 和 `paid_at` 两个字段只能猜，所以经常用错时间口径。修复后，QueryPlan 和局部 SQL prompt 都能看到结构化指标口径。”

   这段突出的是 **不是靠自然语言补丁救火，而是把已有 semantic metadata 接回链路**。

3. **面试官问“你怎么避免为了通过率写死答案？”**

   “我没有把某个问题映射成固定 SQL，也没有把标准答案塞给模型。`expected_value` 只用于 eval scorer，目的是判断模型 SQL 的执行结果是否等于 seed 数据里的固定事实；生产 pipeline 不读取这些答案。prompt 侧加的也是通用规则，比如商品/类目销售额使用 `item_gmv`，通过 `order_items.product_id = products.id` 连商品表；转化率必须用浮点除法。这些规则来自业务口径和 schema 关系，不是针对单个 case 的捷径。”

   这段可以主动化解“是不是刷榜”的质疑。重点是 **eval 断言和生产推理路径隔离**。

4. **面试官问“Text2SQL 里你怎么处理业务口径？”**

   “我把业务指标看成 semantic layer 的雏形，而不是让模型自己猜。GMV、净收入、商品销售额、转化率这些指标都有明确公式、过滤条件和默认时间字段。M13 里我修了一个典型**口径漂移**：订单总 GMV 可以从 `orders.order_amount` 算，但商品/类目销售额要从 `order_items.line_amount` 聚合，否则会把订单头金额错误分摊到商品维度。这个问题 SQL 语法完全正确，但业务结果错，所以必须靠指标定义和 prompt 约束共同解决。”

   这段突出的是 **SQL 正确不等于业务正确**，很适合讲给做数据产品或 Agent 应用的面试官。

5. **面试官问“你怎么设计可观测性？”**

   “我给 pipeline trace 补了能定位责任层的信息。Schema Retrieval 记录 `metric_doc_hits`（检索（Schema Retrieval）命中的"指标文档"清单——记录这次查询召回了哪些指标定义，放进 trace 里做诊断用的），看指标文档有没有召回；SQL Generation 记录 `plan_step_tables/columns/filters/metrics/joins/output_columns`，看 QueryPlan 想做什么、SQL 最后有没有照做。这样一个失败 case 可以拆成三种：没召回、计划没写、SQL 没遵守计划。M13 后续判断 `products` 问题时，就是靠这个分层避免误判成单纯召回问题。”

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

## ★ M14-lite 小修

（2026-07-27）

**简述**：M14-lite 是进入 RAG / Hybrid 前的一次小收口，不追 diagnostic 满分，而是把 **评测更可信、失败更好查、安全边界更清楚、Schema Retrieval 可显式切换后端** 这几件基础卫生补齐。

### 这次做了什么

这次先补了最小 **result_match**：部分核心 SQL case 不再只看列名或包含文本，而是执行 `expected_sql`，把标准 SQL 的结果和模型生成 SQL 的结果做轻量对比。它不是完整 EvalOps 平台，只覆盖 5 条核心 challenge case，用来防止“SQL 能跑但结果错”继续混过去。

然后增强了 **LLM 失败 trace**。以前 `llm_generation_error` 只能看到一句“解析失败”，现在 trace 会记录 `raw_response_preview`、`parse_error`、`prompt_length` 和失败阶段，方便判断是 QueryPlan 解析坏了，还是 SQL generation 没按 JSON 返回。

安全口径采用用户确认的方案 A：敏感字段优先于 admin 角色。也就是说，`users.email / users.phone` 在 Text2SQL 路径里默认不直出；即使是 admin 查询，也会被 QueryPlan 预检和 SQL Guard 拦住。后续如果真的要给 admin 看联系方式，应该走脱敏、审计或专门接口，而不是让自然语言 SQL 直接吐敏感字段。

最后补了 **Schema Retrieval 后端配置开关**：默认仍是 `inmemory + deterministic`，pytest 和本地开发不依赖 Milvus 或联网 embedding；只有显式设置 `SCHEMA_VECTOR_BACKEND=milvus`、`SCHEMA_EMBEDDING_PROVIDER=siliconflow` 等配置时，才会走外部后端。

### 新概念

- **result_match**：把“生成 SQL 的执行结果”拿去和“参考 SQL 的执行结果”比较。它比 `contains` 更严格，但 M14-lite 只做最小版本，不做 SQL 语法等价、历史记录库或完整评测平台。
- **安全口径**：先定清“什么情况一定不能放行”。这次定的是 **敏感字段优先**，避免 admin 角色在 Text2SQL 里变成“万能通行证”。
- **显式后端开关**：工程上支持 Milvus / SiliconFlow，但默认不启用。这样 README 和面试里可以诚实讲“能力已接入，可显式开启；默认路径仍稳定可测”。

### 设计要点

- **不刷 diagnostic**：递归类目、知识库归因、完整 EvalOps、JSON mode 大实验都没有做；`db_plan_003` 被标成 non_blocking/manual_review，是因为它属于后续 Hybrid 语义层，不适合硬塞进 Text2SQL。
- **默认路径不变**：Milvus / SiliconFlow 只是显式开关，默认仍不依赖外部服务，避免测试和本地开发被环境拖住。
- **安全优先于便利**：admin 能看所有表，但不能通过 Text2SQL 直接查邮箱手机号；这更接近真实企业系统里的“敏感字段要有专门通道”。

### 面试怎么讲

“M14-lite 我没有继续追 diagnostic 满分，而是做进入下一阶段前的工程收口：给核心 SQL case 加最小 result_match，让评测不只看列名；给 LLM 失败 trace 加 raw preview 和 parse error，方便排查 JSON/生成稳定性；同时定稿敏感字段策略，admin 也不能在 Text2SQL 中直接查 email/phone。最后把 Schema Retrieval 的 Milvus / SiliconFlow 做成显式配置开关，默认仍走本地 deterministic 检索。这个模块体现的是我知道什么时候该补工程边界，什么时候不该为了分数把未来 Hybrid 能力硬塞进 Text2SQL。”

### 验证与下一步

- 验证：相关回归 **54 passed**；全量 pytest **84 passed**。
- warning：仍是既有 Starlette/httpx warning，不影响本模块。
- 下一步：用户人工检查后可调用 `accept-module` 做 M14-lite 验收；之后进入阶段三 RAG / Hybrid。

可复制验证命令：

```powershell
# 相关回归，预期 54 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_pipeline.py tests\test_phase3a_planner.py tests\test_phase3a_schema_retrieval.py tests\test_m4_nl2sql.py -q --basetemp=.agent_work\temp\pytest-m14-related

# 全量验证，预期 84 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.agent_work\temp\pytest-m14-full-2
```

**本地启动体验：**

M14-lite 没有新增 API 端点，体验入口仍是批量评测和 trace。想看变化，优先看 eval 报告里的 `result_match` case 是否更严格，再看新 pipeline trace 中 LLM 失败时的 metadata 是否包含 raw preview / parse error。

## ★ [实验] 主模型与 embedding 试用 Qwen / Milvus

（2026-07-27）

**简述**：这不是一个完整功能模块，更像进入 Phase 3 前的一次 **技术路线体检**：确认 Qwen 是否值得作为主模型候选，确认 Qwen embedding 是否比 SiliconFlow BGE-M3 更适合后续 RAG / Hybrid，并把过长的 `AI_CONTEXT.md` 拆成当前快照和历史 changelog。

### 这次做了什么

修正了 Milvus 的本地启动方式。直接在 Docker Desktop 里启动单个 `milvusdb/milvus:v3.0-beta` 容器会自动退出，因为 standalone 还需要 etcd 和 minio；正确方式是官方 docker compose 三件套。这个坑已经记录到技术档案，后续做 RAG 不会再从环境问题上绕圈。

| 主模型对比 | 链路 / 配置 | 测试范围 | 结果 | 这次怎么理解 |
|---|---|---|---|---|
| deepseek-v4-pro | DeepSeek + 本地 `inmemory + deterministic` | formal / challenge / diagnostic | `8~9/10`、`12/16`、`24/32` | 综合最稳；formal 有真实 LLM 波动，但 diagnostic 仍领先 |
| qwen3.7-plus | `qwen3.7-plus` + 本地 retrieval | formal / challenge / diagnostic | `9/10`、`13/16`、`21/32` | 常规复杂题有竞争力，边界体检不如 DeepSeek |
| qwen3.7-max | `qwen3.7-max` + 本地 retrieval | diagnostic | `22/32` | 比 plus 略好，但独有 blocking 失败更重，不适合切默认 |

| embedding对比         | 链路 / 配置                                  | 测试范围 | 结果   | 这次怎么理解                                       |
| --------------------- | -------------------------------------------- | -------- | ------ | -------------------------------------------------- |
| SiliconFlow embedding | DeepSeek + `Milvus + BAAI/bge-m3`            | formal   | `8/10` | 没明显超过本地 baseline                            |
| Qwen embedding        | DeepSeek + `Milvus + qwen3.7-text-embedding` | formal   | `9/10` | 略好 1 题，值得 Phase 3 继续测，但证据不足以切默认 |

### 新概念

- **主模型 A/B**：比较的是“谁来规划和生成 SQL”。它影响 QueryPlan、JSON 稳定性、SQL 生成风格和安全边界表现。
- **Embedding Provider A/B**：比较的是“检索时用什么向量表示文本”。它影响 Schema / 文档召回，不等于主模型能力。Qwen 主模型不一定默认更好，但 Qwen embedding 仍可能更适合后续 RAG。
- **diagnostic 体检**：formal / challenge 更像考试分数，diagnostic 更像体检报告。它不只看答对多少，还暴露失败发生在漏表、漏列、plan validation、LLM 生成失败、安全拦截还是 trace 证据不足。
- **错误严重性对比**：不只比较谁错得少，还要比较错在哪里。DeepSeek 独有错误更多在非阻塞生成失败；`qwen3.7-max` 独有错误包含 blocking 的核心生成失败、多表缺列、plan validation 和 trace 证据缺失，所以即使分数只差 2 分，也更不适合当默认。
- **Context / Changelog 拆分**：`AI_CONTEXT.md` 只保留当前快照，完整历史最初集中在 `AI_CONTEXT_CHANGELOG.md`；现在统一从 `CHANGELOG_INDEX.md` 路由到按 Phase 拆分的历史文件。这样 AI 续接时先读短上下文，需要查原因时再定点追溯，减少无关历史占用上下文。

### 设计要点

- **不因为 Qwen challenge 多 1 条或 max 稍高于 plus 就切默认**：diagnostic 补测后，Qwen 在漏表、漏列、证据字段完整性上更不稳；`qwen3.7-max` 虽然比 plus 多过 1 条，但独有失败更影响主线，所以默认仍保留 DeepSeek。
- **不把主模型和 embedding 混在一起判断**：Qwen 主模型暂不切，不代表 Qwen embedding 没价值；后者可能更适合 Phase 3 的中文文档检索。
- **按钮只是实验开关，不改变默认链路**：Streamlit 里可以切 `Milvus + Qwen embedding`，但默认请求和 pytest 仍不依赖 Milvus 或联网 API。

### 面试怎么讲

“我在 Phase 3A 收口前做了一轮模型和检索后端 A/B。没有只看单次分数，而是分成主模型和 embedding 两条线测：主模型方面，`qwen3.7-plus` formal 和 DeepSeek 持平，challenge 略高，但 diagnostic 更低；追加 `qwen3.7-max` 后 diagnostic 到 `22/32`，仍低于 DeepSeek 的 `24/32`，而且独有错误更偏 blocking 主线问题。这说明 Qwen 在常规复杂题上有竞争力，但边界稳定性还不如 DeepSeek。embedding 方面，`qwen3.7-text-embedding` formal 表现优于 SiliconFlow BGE-M3，值得后续 RAG 继续验证。最后我没有盲目换默认，而是把 Qwen 保留为显式候选，把 DeepSeek 保持为当前稳定默认，并把技术档案拆成当前快照和 changelog，降低后续 Agent 续接成本。”

### 验证与下一步

- 相关单元回归：**30 passed**，仅既有 Starlette/httpx warning。
- 主模型 A/B：formal DeepSeek `9/10`、Qwen plus `9/10`；challenge DeepSeek `12/16`、Qwen plus `13/16`；diagnostic DeepSeek `24/32`、Qwen plus `21/32`、Qwen max `22/32`。
- Embedding A/B：formal 本地 `8/10`、SiliconFlow BGE-M3 `8/10`、Qwen `qwen3.7-text-embedding` `9/10`。
- 下一步：Phase 3 进入 RAG / Hybrid 时，优先继续验证 Qwen embedding 在文档检索上的收益；主模型默认暂不从 DeepSeek 切到 Qwen。

可复制验证命令：

```powershell
# 相关回归，预期 30 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_config.py tests\test_m4_nl2sql.py tests\test_phase3a_pipeline.py tests\test_phase3a_schema_retrieval.py tests\test_m9_2_siliconflow_embedding.py -p no:cacheprovider --basetemp=.agent_work\temp\pytest-qwen37-related

# 主模型 diagnostic A/B，真实联网调用，结果本轮为 DeepSeek 24/32、Qwen plus 21/32。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\run_qwen_ab_experiments.py --group main --suite diagnostic

# Qwen max 单独 diagnostic，结果本轮为 22/32。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\run_qwen_ab_experiments.py --group main --experiment main-qwen37-max --suite diagnostic
```

## ★ ★ ★ Phase 3A 阶段总结：Text2SQL 分层推理与评测闭环

（2026-07-31）

**简述**：Phase 3A 把 DataPilot 从阶段二"模板优先 + LLM 兜底"的简单 SQL Agent，升级成 **Schema Retrieval → QueryPlan 自检 → 局部 Schema SQL 生成 → SQL Guard 收尾** 的分层 Text2SQL 新链路，并用 **10 条 formal + 16 条 challenge + 32 条 diagnostic** 三层评测基座冻结基线、度量改进、闭环修复。最终新链路 formal **10/10**、challenge **14/16**、diagnostic **23/32**，同时回答了"Milvus / 真实 embedding / Qwen 主模型值不值得切"三个技术路线问题。这个阶段的定位是：**把"会查库"升级成"能证明自己会查库"**。

### 先用大白话讲

阶段二结束时，DataPilot 查库的方式像一家**小面馆只招了一个全能厨师**：问题来了，先翻固定的几本菜谱（模板 SQL），菜谱里没有的，就让厨师凭感觉做（直接让 LLM 写 SQL）。出餐快，但问题也明显：**厨师可能用错食材**——编造不存在的字段、乱连 Join、甚至偷偷查用户手机号；而且**好不好吃没有统一标准**——之前只有 6 条 smoke 用例，没法量化"这碗面到底进步了没有"。

Phase 3A 做的事情，可以概括成两件：

1. **把单兵作战改成流水线**：先查"食材清单和仓库布局"（**Schema Retrieval**，只召回和问题相关的表、字段、指标、Join 关系），再让厨师**先填一张申请单**（**QueryPlanStep**，写明查哪些表、用什么字段、按什么条件 Join），系统逐项核对申请单是否都在合法清单里（**plan 自检**，相当于后端接口的 **DTO + Validator**），核对通过后才基于**局部菜单**（局部 Schema prompt）写 SQL，最后仍然统一过 **SQL Guard** 这道最终安全闸门。任何一步失败都**结构化地停下**，绝不悄悄退回模板或自己修 SQL——问题暴露得越诚实，才越可评测。

2. **把"感觉好吃"变成"有台账的盲评"**：先做**三层测试集**——10 条 formal（主硬门）、16 条 challenge（更复杂的 superset）、32 条 diagnostic（能力体检，带 capability 标签），在改任何东西之前先把旧链路跑出 **baseline 冻结**下来（像优化前先量旧机器速度）；每跑一次都留下**分步骤 trace_steps** 台账；M12 生成新旧链路对照报告；M13 发现通过率低后**先修评测尺子再修系统**（`expected_value` 数值校验，堵住"GMV=NULL 也算对"的伪通过），再沿着 trace 一层层定位修复。

过程中还做了几次**技术路线体检**：Milvus + SiliconFlow / Qwen 真实 embedding 能不能替掉轻量 in-memory 检索、Qwen 能不能当主模型——结论都是**"能用，但当前不切默认"**，并且留下了可复用的显式开关和 A/B 证据。

所以 Phase 3A 的核心价值是：**把 Text2SQL 从"能答对几条题"推进到"有分层推理、有评测闭环、能证明改进来源"**，为后面的 RAG / Hybrid 和独立评测平台打地基。

### 这次做了什么 ver.5.6-sol

Phase 3A 把 DataPilot 从“模板命中就执行、否则让 LLM 直接写 SQL”，升级成一条**先找 Schema、再做计划、然后生成 SQL、最后安全执行**的分层 Text2SQL pipeline。同时建立 formal、challenge、diagnostic 三层评测，让每次改进都有可比较的证据。

1. **先冻结旧链路基线，避免后面只凭感觉说新方案更好。**

   M8 建立了 10 条 formal 和 16 条 challenge 两套用例。旧链路的真实结果是：

   - formal：**8/10**
   - challenge：**11/16**
   - 安全题：**2/2 正确阻断**

   当 formal 低于原计划门槛时，没有修改 case 或修饰数字，而是保留真实结果作为后续对照。

   M8.5 又补充 16 条 diagnostic extra case，与 challenge 合成 32 条诊断集。旧 pipeline 无法验证的 QueryPlan、局部 Schema 和 trace 检查被明确标为 skipped，不算通过，也不算失败。旧链路 diagnostic 基线为 **12 passed、10 failed、10 skipped**。

2. **建立 Schema Retrieval 和可信 JoinPath。**

   M9 把表字段、业务指标和表关系整理成 `field_doc / metric_doc / relation_doc` 三类 Schema 文档，再通过 keyword、vector 和 relation 信息召回问题需要的局部上下文。

   表之间怎么连接不由 LLM 自由猜，而是统一读取 `relations.yaml`。退款相关缺失的三条结构化关系也在这一阶段补齐。由此生成的 `SchemaGraph / JoinPath` 成为后续计划校验和 SQL prompt 的可信边界。

   第一版使用 deterministic in-memory index，优先稳定召回合同，不让主线开发被 Docker、网络和外部 embedding 阻塞。

3. **用真实 Milvus 和中文 embedding 做实验，但没有因为技术更新就强行切默认。**

   M9.1 接入了可选 `MilvusVectorIndex`，证明真实 Milvus adapter 可以工作；在使用相同 deterministic embedding 时，它与内存索引的召回结果完全一致，说明**替换存储本身不会自动提升语义质量**。

   M9.2 又接入 SiliconFlow embedding，对比 BGE-M3 和 Qwen3 Embedding。最终 keyword + relation merge 的 hard recall 与 M9 持平；但在 vector-only Top12 中，Qwen3 的字段和 Join 召回更好。

   因此阶段结论不是“embedding 无效”，而是：在当时的混合召回策略下，真实 embedding 没有增加最终 hard recall，证据不足以切换默认链路。默认仍保持本地 deterministic 方案，Milvus 和真实 embedding 作为显式实验能力保留。

4. **在 SQL 生成前增加结构化 QueryPlan。**

   M10 不再让模型拿到 Schema 后直接写 SQL，而是要求它先输出 `QueryPlan(steps=[QueryPlanStep])`，明确声明表、字段、指标、过滤、Join、聚合、排序、LIMIT 和输出列。

   `validate_query_plan()` 会把计划逐项对照 `SchemaGraph`、`DomainSchema` 和角色权限。缺表、缺字段、非法 Join、敏感字段和不可用指标会在 SQL 生成前被发现。

   `steps`、`step_id` 和 `depends_on` 为未来 Plan-and-Execute 预留了接口，但 Phase 3A 明确只允许一个 `sql_query` step，多个 SQL 计划会被 `unsupported_multi_step_plan` 阻断。计划只保存一句话 `purpose`，不保存原始 CoT。

5. **把检索、计划、生成、安全和执行串成真实 pipeline。**

   M11 增加 `force_new_pipeline=true` 显式开关，将完整链路接入 `/api/query`：

   `Schema Retrieval`
   → `SchemaGraph / JoinPath`
   → `QueryPlan`
   → `Plan Validation`
   → `局部 Schema SQL 生成`
   → `SQL Guard`
   → `SQL Execution`
   → `Chart`

   SQL 生成器只接收已经召回和校验过的局部 Schema，不再默认看到全库上下文。所有 SQL 仍统一进入 `run_sql_tool()`，所以 SQL Guard、RBAC 和敏感字段策略继续作为最终安全边界。

   每一步都会写入 `TraceStep`。失败时返回结构化 blocked 结果，不偷偷回退模板 SQL，也不自动修改 SQL，从而保证评测看到的就是新 pipeline 的真实能力。

6. **用对照报告暴露问题，而不是把新架构上线等同于效果提升。**

   M12 真正运行了 formal、challenge 和 diagnostic，并生成新旧链路对照报告。新 pipeline 的初始报告为 **6/10、8/16、15/32**，说明分层架构虽然已经连通，但结果质量仍不稳定。

   更重要的是，M12 暴露了两类不同问题：一类是 QueryPlan、别名、指标口径和 SQL 生成问题；另一类是 eval 本身可能测不准。这个发现让后续优化从“继续调 prompt”转向“先检查评测尺子”。

7. **先修评测可信度，再修模型和 prompt。**

   M13 回看报告后发现，旧 scorer 可能因为响应里出现了 `gmv` 字样，就把实际结果为 `NULL` 的 SQL 判成通过。按照新增的固定事实数值口径重新审视，初始真实水平约为：

   - formal：**4/10**
   - challenge：**6/16**
   - diagnostic：**12/32**

   因此第一步不是调模型，而是增加 `expected_value`，让 GMV、净收入等 seed 已知指标必须返回正确数值。单指标只有一列时允许语义等价 alias，但多列结果仍保持严格，避免把“接受别名”变成放水。

8. **沿着 trace 修复指标口径传递和 SQL 生成问题。**

   排查发现，`metrics.yaml` 已经定义 GMV 的过滤条件和默认时间字段，但 `_format_plan_metrics()` 没有把 `filter/default_time_field` 带进新 pipeline prompt，导致模型可能用 `created_at` 代替 `paid_at`。

   修复后，指标定义能够完整进入 QueryPlan 和 SQL 生成。随后又根据 trace 补充：

   - 商品和类目销售额使用 `item_gmv`，聚合 `order_items.line_amount`；
   - 商品维度通过 `order_items.product_id = products.id` 关联；
   - 转化率使用浮点除法；
   - 不同 LLM 任务使用不同 system prompt；
   - trace 增加指标文档命中和计划字段证据；
   - 修正 seed 中一级类目销售额冠军实际为“SaaS 软件”的过时预期。

   这些修复都来自具体失败证据，没有把 JSON mode、rerank 或更复杂架构一次性混进来。

9. **最终形成稳定基线，同时保留真实边界。**

   M13 修复后的稳定快照达到：

   - formal：**10/10**
   - challenge：**14/16**
   - diagnostic：**23/32**

   M14-lite 又继续收紧 eval 可信度、LLM 失败 trace、安全措辞和 diagnostic 卫生，并明确原始邮箱、手机号等敏感字段对所有角色都应阻断。Schema Retrieval 默认仍保持 in-memory + deterministic，Milvus和外部 embedding 必须显式开启。

   阶段没有追求 diagnostic 满分，也没有把真实 LLM 单次波动包装成稳定提升。递归类目、部分输出别名、安全诊断和复杂 SQL 仍被保留为后续问题。

所以 Phase 3A 的成果不只是多了一条 NL2SQL pipeline，而是建立了：

```
评测基线`
→ `局部 Schema`
→ `结构化计划`
→ `SQL 生成`
→ `安全执行`
→ `Trace`
→ `按证据修复
```

DataPilot 从“模型生成了一条能跑的 SQL”，前进到“系统能说明 SQL 为什么这样生成、用了哪些可信上下文、在哪一步失败，以及改完以后是否真的更好”。

> **M24 章节结束时补充**：本节的 formal `10/10`、challenge `14/16`、diagnostic `23/32` 是 Phase 3A 在 M13 合同下的历史成果，不是当前基线。到 M24，模型已切为 Qwen `qwen3.7-plus`，Schema corpus 为 195 docs，case/scorer 又加入更严格的结果、输出和 SQL fidelity 合同；最新受控 diagnostic 为 Local `24/24/25`、Milvus `25/25/25`。这些数字与 M13 口径不同，只能分别说明各自阶段，不宜直接横比。

### 这次做了什么

按阶段主线写，不按模块流水账：

1. **先立评测基座，再动推理链路**（M8 / M8.5）：把 EvalOps-lite 升级成三层评测。`EvalCase` 前向兼容新增 `expected_metrics / pipeline_mode` 等字段，`_score_case()` 改为 `EvalScore` 并带最小 **issue_tags**（missing_table / missing_column / safety_mismatch / unexpected_error）和 `manual / review_required` 标记；冻结旧链路 baseline：formal **8/10**、challenge **11/16**（2/2 安全拦截全过）。M8.5 再扩出 32 条 **diagnostic benchmark**：16 条 challenge + 16 条新增 extra case 通过 `--cases + --extra-cases` 组合，每条带 **capability 标签**（schema_retrieval / join_path / query_plan / local_schema_prompt / trace_steps / security_guard）；旧链路下新能力专属 check 记为 `skipped_due_to_pipeline_mode`，**不算过也不算挂**——不伪装没实现的能力。

2. **给新链路装上"食材清单"**（M9 / M9.1 / M9.2）：M9 实现 **Schema Retrieval 与 JoinPath**——从 `domain_pack` 构建字段 / 指标 / 关系三类检索文档，`relations.yaml` 作为 **Join 唯一事实源**（补上原来缺的 refunds 三条关系），用 deterministic in-memory 向量索引完成轻量召回，recall 硬门达标（formal 15/15 表、16/18 字段指标、3/3 Join）。M9.1 / M9.2 在实验分支验证 **Milvus adapter + SiliconFlow BGE-M3 / Qwen3 真实中文 embedding**：单点召回持平、vector-only 下 Qwen 略好，但不合并主线先问用户，最终作为可选注入合回 main，默认仍走 in-memory。

3. **给 LLM 加"申请单 + 校验"**（M10 / M11）

   - **M10：先填申请单，再写 SQL。** M9 已经把问题相关的表、字段、指标和 Join 关系召回了，但如果直接把 SchemaGraph 塞给 LLM 让它写 SQL，中间仍是一个**黑盒**——模型可能编造不存在的字段、乱连 Join、甚至在计划里就打算查敏感字段。这在代码里叫"幻觉"，在企业里叫"事故"。M10 的解法是：让 LLM 写 SQL 之前，先输出一张**结构化"申请单"（QueryPlanStep）**——写明要查哪些表（`tables`）、用哪些字段（`columns`）、要哪个指标（`metrics`）、按什么条件 Join（`joins`）、怎么聚合排序（`aggregations / group_by / order_by / limit`）、最后输出什么列（`output_columns`）。填完后，系统拿这张申请单做**plan_validation 自检**，逐项核对三件事：表 / 字段是否都来自合法 SchemaGraph（模型编造的字段当场拦下）、Join 条件是否来自 `relations.yaml` 的 relation id（**不接受自由文本编造**，防止模型发明连接方式）、敏感字段是否在 SQL 生成前就预检为 `sensitive_field_access`（根本不进入生成环节）。这里的关键区分是：**SchemaGraph 是"业务里有什么"（系统检索出的客观事实，像一张地图），QueryPlanStep 是"模型想做什么"（LLM 输出的主观意图，像一条路线规划）**——地图是固定的，路线是模型现画的，自检就是核对"你画的路线是不是都在这张地图上"。整个机制相当于把"生成后检查"提前成了"生成前约束"。

   - **M11：把零件串成一条新流水线。** M9 的检索、M10 的计划、M5 的 SQL Tool / Trace，各是一台机器；M11 的 `run_text2sql_pipeline()` 把它们串成一条**真正能从 `/api/query` 触发的新 Text2SQL pipeline**，九个环节依次走：**schema_retrieval**（召回相关文档）→ **schema_context**（组装局部 Schema 上下文）→ **join_path**（在 SchemaGraph 上找表间连通路径）→ **query_plan**（LLM 填申请单）→ **plan_validation**（系统核对申请单）→ **sql_generation**（基于局部 Schema 生成 SQL）→ **sql_guard**（SQL 安全最终门）→ **sql_execution**（执行）→ **chart_decision**（决定要不要配图、配什么图）。三个设计点：① **任一步失败都结构化 blocked**——不降级回模板、不让模型自动修 SQL 重试，问题暴露得越诚实，才越可评测；② **`force_new_pipeline` 显式开关**——评测可以从 API 侧强制走新链路，但默认请求仍模板优先，旧行为、响应契约都不变；③ **每步写 `trace_steps` 到 JSONL**——记录 `step_type / status / error_type / latency_ms`，失败能精确归因到"检索、计划、校验、生成、执行"具体哪一层，这是后面 M13 分层修复的基础设施。

4. **量出差距，如实记录**（M12）：跑新链路全套报告并生成**新旧对照**（`compare_phase3a.py` 直接读 trace JSONL 而不是解析 Markdown）：formal **6/10**、challenge **8/16**、diagnostic **15/32**，安全 2/2 全拦。如实暴露瓶颈是 **LLM 输出列名不稳定**（`category` vs `category_name`、`coupon_order_count` 别名漂移）；同时顺手修掉三个真问题：DeepSeek 废弃模型名 `deepseek-chat` → `deepseek-v4-pro`、新链路绕过的危险 SQL 预检补丁、plan validation 对 `COUNT(DISTINCT ...)` 的聚合表达式误判。

5. **先修尺子，再沿 trace 修复**

   **动系统之前，先检查尺子。** M12 已经把差距量出来了（formal 6/10、challenge 8/16、diagnostic 15/32），M13 的任务是修复。但拿到差距报告直接调 prompt 是错的——第一步是先问一个问题：**"评测本身测准了吗？"** 因为"测不准的系统没法优化"：如果 GMV=NULL 的结果也能被判对，那改对改错都看不出来，任何修复都是在黑灯里装修。M13 先做的不是调模型，是**修评测尺子、补断裂的管道**，把"系统在干什么"看清楚之后再动手。

   **第一批（修尺子 + 补管道）：先让"对错"判断可靠。** 两件事：

   - ① 新增 **`expected_value` 数值校验**——GMV 这类有固定事实的指标，必须和参考 SQL 在确定性数据上执行得到的基准值 **`11285752.00`** 对得上才算过，而不是"结果里 contains `gmv` 字样就算过"。M12 报告里就出现过 GMV=NULL 仍判 pass 的伪通过，这就是尺子坏了；
   - ② 修 **metrics prompt 管道**——`_format_plan_metrics()` 漏传了 `metrics.yaml` 里的 `filter`（"GMV 用 `paid_at` 过滤"）和 `default_time_field`（默认时间字段），**口径信息根本没进新链路的 prompt**。这解释了一个之前很诡异的失败模式：模型自己编造 `unpaid` 状态、用 `created_at` 代替 `paid_at`——不是模型笨，是它压根没被告知正确口径。第一批的效果有一个反直觉的信号：**formal 重跑反而比 M12 更低（5/10）**，因为以前伪通过的现在真失败了——这正是"先修尺子"要暴露的东西，数字变难看说明尺子变准了；challenge 8/16 → **10/16**、diagnostic 15/32 → **20/32**。
   - 这里有个**反转**：M12 阶段曾把这批失败归因为"LLM 语义漂移"（列名对不上），但后续结合数据质量彩蛋重新审视后发现，**别名漂移只是症状，不是根因**——formal 允许类失败里直接由管道/彩蛋导致的占 **4/5（80%）**，纯别名漂移只有 1 条；真正的主因是 **metrics → prompt 管道断裂**，`_format_plan_metrics()` 重写时漏字段，典型 rewrite regression（重写回归：重写代码时，把原来已经正常工作的功能弄丢了，导致行为比旧代码退化），管道在最后几行代码断了。一句话教训：**看到"模型答错"，先查"信息有没有送到模型手里"再怪模型**——说明书一直在，是管道把说明书丢了。
   - 方向相反还有另一个反转：`p3a_agg_003` 转化率题，模型其实输出了 `conversion_rate`、数值也对（0.7），但 eval 的列名匹配没认出来照样判挂——以为模型错，可能是管道断（信息没送到，上面那条），也可能是评测错（尺子量错，这段的这个），最后才轮到模型自己错。

   **第二批（沿 trace 归因 + 修 alias 与 SQL 约束）：定位到层，逐类修。** 第一批之后不再盲调 prompt，而是**每个失败 case 先翻 trace_steps**——看失败落在评测评分、QueryPlan 选择、SQL 生成哪一层，再决定改哪里。两轮修复：

   - 为什么必须分层定位？具体例子：`p3a_multi_002` 报告里显示 `missing_tables=['products']`，意思是"该用的表没用到，判缺表"。第一印象是检索漏召回，但复核发现该题 SchemaGraph 里其实有 `products`（源码现跑可复现），检索没漏！——真实原因是模型生成 SQL 时，没去 join `products` 表，而是用了 `order_items` 宽表里的 `product_name_snapshot`（商品名快照）字段——宽表里已经存了一份商品名，模型觉得"我不用专门去查商品表，直接用快照就行了"。没有 trace 分层，就会误判成检索问题、白白去改检索。

   - > 相当于餐厅出菜出了问题，第一反应是"采购（检索）漏买了土豆"。一查库房，土豆在。真相是：**厨师（SQL 生成）做菜时没去库房拿土豆，直接用了冰箱里预先切好的土豆丝半成品**。菜还是做出来了，但没用上"土豆"这个进货记录——所以采购记录里看起来"缺了土豆"。

   - ① 补**语义等价 alias**（`usage_count`、`add_to_pay_conversion_rate`、`total_gmv`、`category_gmv`、中文"商品名称"等）——原则是只放语义等价的别名，**绝不用 alias 掩盖缺表或错表**；

   - ② 修 **SQL 约束**——商品/类目销售额必须用 `item_gmv`（聚合 `order_items.line_amount`），不能用 `gmv` / `orders.order_amount` 替代（口径防止串维度）；转化率必须 `* 1.0` 或 `CAST(... AS REAL)`（防 SQLite 整数除法把小数截成 0）；"一级类目销售额 Top1"的固定检查值从"数码电子"改为 **"SaaS 软件"**（用当前 seed 直接执行参考 SQL，Top1 实际就是 SaaS 软件——检查值以数据事实为准）。最终新链路 **formal 4/10 → 10/10**、challenge **6/16 → 14/16**、diagnostic **12/32 → 23/32**。

   整个过程**测试题一行没改**——改的是评测尺子（scorer 严格度）和系统（prompt 管道、SQL 约束），所以 4/10 → 10/10 的提升是"系统真的变好了"，不是"题变简单了"。

6. **收口卫生与路线体检**（M14-lite + Qwen / Milvus 实验）：M14-lite 执行用户确认的 5 项小收口——`result_match` 最小结果集对比（5 条核心 challenge 加严）、LLM 失败 trace 增强、**安全口径定案（敏感字段优先于 admin 角色，`users.email/phone` 不直出）**、Schema Retrieval 后端配置开关（milvus / siliconflow 必须显式开启）、诊断口径清理（知识库归因题标 `manual_review + hybrid_attribution` 留给后续 Hybrid）；刻意不做递归类目、知识库归因、完整 EvalOps、JSON mode 大实验。最后的 A/B 实验回答技术路线：DeepSeek vs Qwen 主模型（formal 9/10 持平，看**失败形态**——Qwen max 独有 blocking 错误更多，默认仍 DeepSeek）、in-memory vs BGE-M3 vs Qwen embedding（8/10 / 8/10 / 9/10，差 1 题且受 LLM 波动影响，Phase 3A 不切，留给 RAG 再测）。

### 阶段主线图

`自然语言问题`
→ `/api/query`（`force_new_pipeline` 显式开关）
→ `Schema Retrieval`（字段 / 指标 / 关系三类文档；in-memory 默认，Milvus + 真实 embedding 可选）
→ `SchemaGraph / JoinPath`（`relations.yaml` 单一 Join 事实源）
→ `QueryPlan` + 自检（plan_validation / 敏感字段预检）
→ `SQL 生成`（基于局部 Schema 的 prompt）
→ `SQL Guard`（危险预检 / RBAC / 敏感字段，最终安全门）
→ `SQL 执行` → `chart_decision` → `AgentResponse`

评测侧：`10 formal + 16 challenge + 32 diagnostic` → `eval/run_eval`（expected_value / result_match / safety / trace check）→ `trace_steps JSONL` → 新旧对照报告 → 下一轮修复

### 关键知识点串联

这里不再列每个模块所有概念，而是列阶段级概念：

- **三层评测基座（formal / challenge / diagnostic）**：10 条 formal 是**主硬门**，16 条 challenge 是 superset（多表、窗口、困难诊断），32 条 diagnostic 是带 capability 标签的**能力体检**。三层各有定位：硬门保验收、superset 扩复杂度、diagnostic 定位边界和下一步问题（**不追满分**）。
- **baseline 冻结与对照**：改造前先把旧链路量化成 baseline，改造后用 `compare_phase3a.py` 生成并排对照。没有基线，任何"提升了"的说法都是自说自话——这也是"先测量、后优化"的工程习惯。
- **Schema Retrieval 三类文档 + JoinPath 单一事实源**：字段 / 指标 / 关系分别来自 `schema_desc/*.md`、`metrics.yaml`、`relations.yaml`；Join 条件**只认结构化关系文件，不接受 LLM 自由编造**，防止模型"发明"连接方式。
- **deterministic in-memory vs Milvus + 真实 embedding**：两种证据层次——M9.1/M9.2 的 **recall smoke** 证明 adapter 可用；M14-lite 的**端到端 A/B eval**（formal 10/10 持平、diagnostic 23/32 → 20/32）证明不值得切默认。"能用"和"该用"是两件事。
- **QueryPlanStep = DTO + Validator**：像 Java 后端接口先接 DTO、校验、再进 service——LLM 先填结构化"申请单"，系统逐项核对来源，防幻觉从"生成后检查"提前到"生成前约束"。
- **双层安全**：plan 层敏感字段预检（生成前拦住）+ SQL Guard（执行前最终闸门，RBAC / 危险语句 / 敏感字段）。安全能力不只靠 prompt，拦截点彼此独立。
- **trace_steps 分层归因**：M13 的修复顺序证明了这个方法——先看 trace 判断失败在**评测误杀、指标口径没进 prompt、QueryPlan 选错口径、SQL 生成**哪一层，再动手，而不是盲调 prompt。
- **先修评测尺子再修系统**：`expected_value` 数值校验让"GMV=NULL 但 contains: gmv 误判通过"无处遁形。**测不准的系统没法优化**——这是 M13 的第一课。
- **失败形态分析（主模型 A/B）**：Qwen 与 DeepSeek 分数接近，但看失败形态——Qwen max 独有失败里 blocking 类更多，稳定性不如 DeepSeek，所以不切默认。**别只看总分，要看错在哪里、错得多严重**。
- **前向兼容与显式开关**：`EvalCase` 新增字段不破坏旧 smoke；`pipeline_mode`、`force_new_pipeline`、`SCHEMA_VECTOR_BACKEND` 都是显式开关，默认行为不变，评测和实验可以自由走新路径——这保证了 Phase 3A 全程旧链路可回归、pytest 不依赖外部服务。

### 阶段设计取舍

- **先冻结 baseline 再改造（M8）**：把旧链路 8/10 的真实水平如实记录，而不是修好旧链路再比。用户确认保留这份"旧机器真实速度"的基线，宁可难看也不造假。
- **轻量 in-memory 为主，Milvus / 真实 embedding 只作实验开关**：M9 不被 Docker / 网络 / 额度阻塞，pytest 不依赖外部服务；Milvus 和 SiliconFlow / Qwen embedding 作为可选注入合并回 main，但切默认必须过**端到端 A/B** 证据关。结论：能用、recall 持平、diagnostic 略降，所以不切。
- **计划层自检而不是让 LLM 直接写 SQL**：多一层 QueryPlan 的代价（结构化输出、校验代码）换来的是幻觉被提前拦住、失败可归因；同时用"失败结构化 blocked 不降级"保证问题暴露，而不是悄悄退回模板掩盖错误。
- **先修评测尺子再修系统（M13 顺序）**：如果不先加 `expected_value`，后续任何 prompt 修复都可能被"伪通过"掩盖或误判，修完也不知道有没有用。
- **主模型默认不切 Qwen**：虽然 formal 打平、challenge 略高，但诊断失败形态（漏表漏列、blocking 错误）和稳定性不占优；Qwen 保留为显式候选和 A/B 对照，后续 RAG / Hybrid 再评估。**技术选型跟随证据，不跟随新鲜感**。
- **安全口径：敏感字段优先于 admin 角色**：`users.email / users.phone` 在 Text2SQL 路径不直出，后续查看走脱敏 / 审计 / 专门接口——把"能查"和"该查"分开。
- **刻意不做的事**：递归类目题（留 manual review）、知识库归因（标 `hybrid_attribution` 留给 Phase 3）、完整 EvalOps 平台（留给独立 EvalBench 项目）、JSON mode 大实验（现有 JSON 解析 + 校验 + 拦截已够稳定，不做一票否决式改造）。

### 面试怎么讲

我的 DataPilot 项目在 Phase 3A 完成了一次 Text2SQL 的体系化升级：从"模板优先 + LLM 兜底"的简单链路，重构为**"Schema Retrieval → QueryPlan 自检 → 局部 Schema SQL 生成 → SQL Guard"**的分层推理链路。

我用 domain_pack 实现了一个轻量语义层：metrics.yaml 定义 KPI 口径（类似 dbt metrics），relations.yaml 定义 join 语义（类似 LookML joins），schema_desc 定义字段字典。engine 只消费不硬编码，换行业只换这一层。与 dbt Semantic Layer 的差异是：我们没有对外查询 API，语义只作为 LLM 的上下文和约束——相当于把语义层拆成了“知识侧”（我负责）和“执行侧”（LLM + SQL Guard 负责）。

核心方法论是**评测驱动**：先建 10/16/32 三层评测基座、冻结旧链路 baseline，再改系统；每步改进都先修评测尺子（`expected_value` 数值校验，堵住"GMV=NULL 也算对"的伪通过），再沿 `trace_steps` 判断失败发生在检索、计划、生成、执行还是 scorer。

最终新链路 formal 从 4/10 提升到 **10/10**、challenge 6/16 → **14/16**、diagnostic 12/32 → **23/32**，全程不改测试题、不过拟合。过程中用端到端 A/B 回答了三个技术路线问题：Milvus + 真实 embedding **可用但不切默认**（单点 recall 持平、端到端 diagnostic 略降）、Qwen 主模型**不切默认**（失败形态分析：独有 blocking 错误更多）、in-memory 检索保持默认但保留显式开关。安全侧把"敏感字段优先于 admin 角色"定为口径，防幻觉靠 plan 层预检 + SQL Guard 双层独立拦截，不靠 prompt 承诺。

1. **[基础追问] 旧链路有什么具体问题，值得你重构一遍？**

   旧链路的问题有三个层面：**召回层面**，LLM 直接面对全量 schema prompt，容易编造不存在的字段、乱连 Join（比如把退款表和订单表错误 join）；**安全层面**，模型可能计划查询 `users.email` 这类敏感字段，只能在 SQL 执行前靠字符串特征拦截；**评测层面**，只有 6 条 smoke 用例，无法量化"改进了没有"。Phase 3A 分别用 Schema Retrieval（只给局部 schema）、QueryPlan 自检 + SQL Guard 双层拦截、三层评测基座解决。一句话：**旧链路不可测、不可控，重构是为了让问题可归因、改进可证明**。

2. **[基础追问] 三层评测为什么这么设计？它们各自解决什么问题？**

   一层测试集的毛病是**分不清"验收没过"和"哪里不行"**。formal 10 条是主硬门，验收用；challenge 16 条是 superset，覆盖多表、窗口函数、困难诊断，测试数据库复杂度扩展能力；diagnostic 32 条是带 capability 标签的能力体检，每条标注测的是 schema_retrieval / join_path / query_plan / local_schema_prompt / trace_steps / security_guard 中哪项能力，跑完直接看 capability summary，就知道下一步该修哪块。而且 diagnostic 不追满分——它的职责是定位边界，不是刷数字。

3. **[工程/深挖追问] 为什么不直接把全量 schema 都塞给 LLM，而要做 Schema Retrieval 和局部 Schema prompt？**

   全量 schema 看起来信息更多，但对 Text2SQL 反而是**噪音**：表多、字段多、相似字段多，LLM 更容易选错表、编造字段或乱连 Join，而且失败后很难判断是 schema 没给清楚，还是模型自己生成错。Schema Retrieval 的作用是先把问题相关的表、字段、指标和关系召回成一个局部 **SchemaGraph**，再让 LLM 基于局部上下文写 QueryPlan 和 SQL。这样好处有三个：**token 更少、干扰更少、失败更可归因**。如果召回没命中，是 retrieval 问题；如果计划用了不存在字段，是 plan validation 问题；如果 SQL 写错，是 generation 问题。

4. **[工程/深挖追问] M13 从 4/10 提到 10/10，具体怎么定位问题的？怎么证明不是刷评测？**

   定位方法是**沿 trace 分层归因**：trace_steps 记录每步 input / output / status / error_type，先看失败落在 eval 评分、QueryPlan prompt、SQL prompt 还是数据预期哪一层。第一批发现的最大问题其实是**评测尺子坏了**：`gmv` 字段是 NULL 时旧检查只做 `contains: gmv` 字符串匹配，仍然判 pass，所以测不准。先加 `expected_value` 数值校验（GMV 必须等于固定事实 `11285752.00`），再修 metrics prompt 管道（`filter / default_time_field` 没注入新链路），之后才做 SQL 约束（item_gmv 口径、转化率浮点除法）。证明没刷评测的证据是：**测试题一行没改**，改的是 scorer 严格度和 prompt 管道；而且对照报告如实展示失败明细和 issue tags，剩余 2 条 challenge、9 条 diagnostic 失败原因都写得出来。

5. **[工程/深挖追问] JoinPath 为什么必须来自 relations.yaml，而不是让 LLM 自己推理？**

   因为 Join 是 SQL 正确性的地基，一旦 LLM 编造 Join 条件（比如拿订单号 join 退款单号），生成出的 SQL 要么报错要么出错误数据，而且**错误不可归因**——你不知道是模型不会还是 schema 没给全。relations.yaml 作为单一事实源，把"系统允许哪些连接方式"显式化：M9 补齐了 refunds 三条缺失关系，说明结构化的文档确实会被漏写，但漏写是**可发现、可补的**；而 LLM 自由编造是无法控制的。这个取舍像后端里"枚举值只从配置读，不接受请求体里传任意字符串"。

6. **[工程/深挖追问] plan 自检和 SQL Guard 双层安全，会不会重复？边界怎么划？**

   不重复，职责不同：**plan 自检管"计划是否合法"**——表、字段、Join 是否来自 SchemaGraph / relations.yaml，敏感字段是否在生成前就拦截（`sensitive_field_access`）；**SQL Guard 管"执行的 SQL 是否可执行"**——危险语句、表级 RBAC、敏感字段最终门。一个是生成前约束，一个是执行前兜底，任一层的绕过都拦不住另一层。而且这是**刻意设计的两道独立防线**：prompt 和计划都可能被模型不遵守，所以执行前的 SQL Guard 永远存在——安全能力不只靠 prompt，这个原则从 M4 一直贯穿到 Phase 3B。

7. **[压力追问] 你又是加数值校验、又是加 result_match，会不会只是把评测改严了，让系统显得"提升"了？**

   这个问题问得很到位，要分开看：加严评测确实会改变分数，但方向是**让分数更难通过**，而不是更宽松——M13 前 GMV=NULL 能伪通过，加 `expected_value` 后这类错误立刻暴露为失败。而且顺序是先修尺子、再修系统，formal 从 4/10 到 10/10 的提升是在更严的尺子下取得的，所以是"系统真的变好了"。另外我们保留了三个交叉验证：**测试题不改**（改动都在 scorer 和 pipeline）、**新旧对照报告**（同套 case 新旧链路并排）、**失败明细全量公开**（剩余失败都有 issue tags 和原因）。如果只为了数字好看，直接改 case 或放松校验最快，我们反而在收紧。

8. **[压力追问] 10/10 只是 10 条固定题，真实场景泛化怎么证明？**

   固定题确实不能证明泛化，这正是我们设计三层评测的原因：**formal 证明验收口径，diagnostic 证明边界**。diagnostic 23/32 的 9 条失败里，5 条是输出列 / 评分严格性问题、2 条 plan validation / guard blocked、1 条非阻塞递归类目题、1 条安全诊断 mismatch——这组数字本身就是诚实的边界声明，我们从没宣称全对。真实场景的差距主要来自 **LLM 列名不稳定**（category vs category_name 这类别名漂移），这是 M12 对照报告如实记录的瓶颈，M13 用语义等价别名缓解但没有根治。所以泛化问题是真实存在的技术债，下一阶段（RAG / Hybrid 和独立评测平台）要解决的是：更多样化的 case、文档知识补充、更稳的 schema 表示。

9. **[压力追问] 这个阶段修了很多评测和 prompt 的"内功"，但业务能力提升有限，是不是偏工程自嗨？**

   承认一部分：Phase 3A 确实没有增加新业务能力（比如知识库问答、多步骤 Agent），产出集中在**让已有能力可测、可控、可归因**。但我认为这不是自嗨，理由有三：一是**地基性质**——SQL Agent 的核心风险就是"答错但显得很自信"，不解决测不准问题，后续任何功能叠加都是空中楼阁，M13 的伪通过就是例子；二是**每个技术路线问题都给了明确结论**——Milvus / Qwen / embedding 该不该切，都有端到端证据和结论，避免团队在错误路线上投入；三是**直接服务后续阶段**——评测基座、trace_steps、安全口径现在被 Phase 3B 的 LangFuse 观测和独立 EvalBench 项目直接复用。如果面试官觉得偏工程，可以反问：一个没有评测闭环的 SQL Agent，怎么证明它"变好了"？

### 阶段成果与边界

- 完成：
  - **三层评测基座**：10 formal + 16 challenge + 32 diagnostic，`EvalScore / issue_tags / manual / review_required`，capability 标签与 `skipped_due_to_pipeline_mode` 口径
  - **Schema Retrieval 与 JoinPath**：字段 / 指标 / 关系三类文档，`relations.yaml` 单一 Join 源，deterministic in-memory 索引，recall 硬门（formal 15/15 表、16/18 项、3/3 Join）
  - **QueryPlan 自检层**：结构化计划 + 表 / 字段 / Join 来源校验 + 敏感字段预检
  - **新 Text2SQL pipeline 与 trace_steps**：`force_new_pipeline` 显式开关，失败结构化 blocked 不降级
  - **质量闭环**：formal **4/10 → 10/10**、challenge **6/16 → 14/16**、diagnostic **12/32 → 23/32**（测试题未改）
  - **技术路线结论**：Milvus + SiliconFlow / Qwen embedding 可用不切默认（保留可选注入）；Qwen 主模型不切默认（失败形态分析）；DeepSeek 模型名修复
  - **安全与收口**：敏感字段优先于 admin 角色定案；`result_match` 加严 5 条核心 challenge；LLM 失败 trace 增强；Schema Retrieval 后端显式开关
- 没完成 / 刻意不做：
  - **LLM 列名别名漂移**（`category` vs `category_name` 等）是真实瓶颈，M13 只缓解未根治，留给后续阶段
  - **递归类目题**（db_hard_001）标 `manual_review` 非阻塞处理，不强行支持
  - **知识库归因**（db_plan_003）标 `manual_review + hybrid_attribution`，留给 Phase 3 RAG / Hybrid
  - **diagnostic 不追满分**：23/32 是边界定位结果，不是失败
  - **完整 EvalOps 平台**（case 管理、历史结果库、HTML dashboard）——定位在独立项目 EvalBench
  - **JSON mode 大实验**——现有"JSON object + prompt 约束 + 解析校验 + 失败拦截"已够稳定，不做一票否决式改造

### 下一阶段怎么接

- **实际执行的下一阶段是 Phase 3B 可观测性（M15-M19）**：进入 RAG / Hybrid 之前，先把"业务 Agent 可被观测、可被评测、可被归因"补上——**评测基座和 trace_steps 正好是 Phase 3B 的输入**：eval scorer 演化为 L1/L2/L3 分层（M17）、trace_steps 演化为 LangFuse live lifecycle spans（M16B）、实验与对照报告演化为 LangFuse Dataset / Experiment 工作流（M18）、失败报告演化为 failure triage 与 A/B failure distribution（M19）。下一阶段的衔接已在 Phase 3B 上半阶段总结中完整记录。
- **Phase 3 RAG / Hybrid（计划中的下一模块）**：M14-lite 已把知识库归因题标为 `hybrid_attribution` 预埋；Schema Retrieval 的 Milvus / SiliconFlow / Qwen embedding 可选能力可直接复用（Qwen embedding formal 9/10 略好于 8/10，值得在文档检索上继续验证）；别名漂移问题在更多样化 schema 表示下继续处理。
- **独立 EvalBench 项目**：Phase 3A 的三层评测基座、对照报告和 eval 口径（expected_value / result_match / issue_tags）是平台化的基础素材。
- **可复用的阶段级验证命令**：各模块记录里都有完整验证命令；阶段收口时全量 pytest 预期 **84 passed**；真实 LLM 基线入口是 `python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-new-pipeline.md --trace .agent_work/temp/xxx.jsonl`（预期 formal 10/10，需 DeepSeek key）和 `scripts/run_qwen_ab_experiments.py`（A/B 对照）。

## ★ [Phase3B] M15 LangFuse Cloud 接入基线

（2026-07-28）

**简述**：M15 是 Phase 3B 的第一块地基：先确认 **LangFuse Cloud、Python SDK、配置入口和 trace id 边界** 都可靠，再让后续 M16 去做真正的 JSONL + LangFuse 双写。它没有改 `/api/query`，也没有替代现有 JSONL trace，而是把“能不能安全接入 LangFuse”这件事先钉牢。

### 先用大白话讲

M15 做的事情，可以理解成：在把 LangFuse 接进正式业务前，先去确认“这套外部观测平台到底能不能稳定用”。

如果一上来就把 LangFuse 接到 `/api/query`，问题会混在一起：到底是业务代码错了、SDK 用法错了、Cloud key 错了，还是 LangFuse 查询有延迟？M15 先把这些基础问题拆出来，单独验证 Cloud 写入、score 写入、flush 和查询可见性。

同时，M15 还先定好边界：DataPilot 自己的 `trace_id` 继续当主 ID，LangFuse 用自己的 trace id；LangFuse 默认关闭，SDK 放在可选依赖里。这样后面接入 LangFuse 时，它只是给系统多一双“观察的眼睛”，不会反过来改变主业务怎么运行。

所以本模块的核心价值是：先把 **外部观测平台的可用性、配置边界和 ID 边界** 验证清楚，为后续双写和 score 回写打地基。

### 这次做了什么

这次先用 `.env` 里已有的 LangFuse Cloud key 复跑了 SDK smoke：创建一条观察 span，按 LangFuse trace id 写入一条 score，调用 `flush()`，再用 SDK 查询确认 trace 和 score 已经能在 Cloud 侧读到。本轮 trace id 是 `a5b22262bb154b3a9b08b0b09b5f8cc5`，查询可见约 `0.6s`。

然后把 LangFuse 配置正式纳入 `Settings` ：默认 `LANGFUSE_ENABLED=false`，也就是说项目原来的 API、JSONL trace、eval 报告不会因为 LangFuse 没装、没开或 Cloud 不通而受影响。`langfuse==4.14.1` 被放进 `observability` optional extra，后续需要观测能力时再显式安装。

### 新概念

- **旁路观测**：LangFuse 在这里不是主链路，而是像“额外抄送一份运行记录”。主路仍是 JSONL；LangFuse 挂了，主系统继续跑。
- **optional extra**：Python 项目里的一种可选依赖分组。`pip install -e .[observability]` 才安装 LangFuse SDK，普通开发和测试不用被外部观测依赖绑住。
- **双 ID 策略**：DataPilot 自己的 `trace_id` 继续服务 API、日志、JSONL 和 eval；LangFuse 使用独立 `langfuse_trace_id`。这类似业务订单号和第三方支付流水号，两个都重要，但不能混成一个。
- **flush 语义**：`flush()` 代表 SDK 把事件送到 LangFuse API，不保证 UI 或查询立刻同步完成。所以 smoke 需要允许短暂 ingestion 延迟，而不是看到一秒内查不到就判失败。

### 代码阅读路线

1. **配置入口**：`app/core/config.py`
   先看 `Settings` 的“可观测性配置”和“Eval Judge 配置”。重点理解 `LANGFUSE_ENABLED=false` 为什么是默认值：Phase 3B 要证明 LangFuse 可用，但不能让它成为生产强依赖。

2. **依赖边界**：`pyproject.toml`
   看 `[project.optional-dependencies]` 里的 `observability`。它把 LangFuse SDK 和核心依赖分开，后续 M16 写 backend 时也要保持延迟导入，避免默认链路被可选依赖拖住。

3. **本地验证素材**：`.agent_work/temp/m15-notes.md`
   这里是 M16 最应该先读的材料：SDK 4.14.1 没有旧版 `client.trace()`，要用 `start_observation(trace_context=...)`；LangFuse trace id 要用 32 位小写 hex。

### 设计要点

- **不让 LangFuse 接管 DataPilot trace_id**：这是 M15 最重要的边界。API 响应、响应头、JSONL、eval 报告都继续用 DataPilot 自己的 trace id；LangFuse id 只服务 Cloud trace 和 score。
- **不提前做 M16 双写**：M15 只做 Cloud / SDK / Settings 基线。真正把请求 trace 写到 LangFuse，会触及 payload 脱敏、失败降级和 JSONL 兼容，留到 M16 单独做。
- **不做 self-host**：Cloud 已能验证 trace / score 能力；自部署组件较重，留给后续 EvalBench 阶段更合理。

### 面试怎么讲

“M15 我没有一上来就把 LangFuse 接进业务请求，而是先做 **observability 接入基线**：确认 **Cloud key、SDK 版本、span 写入、score 写入和 flush** 都可用；同时明确 **DataPilot 的 trace_id 不被 LangFuse 接管**，LangFuse 用独立 **32 位 hex id**，并通过 metadata 建立映射。依赖上我把 `langfuse==4.14.1` 放到 **optional extra**，默认 `LANGFUSE_ENABLED=false`，保证 **观测系统不可用时不影响主链路**。这体现的是我在引入外部平台时，会先守住 **响应契约、依赖边界和故障降级**，而不是为了可视化把核心链路绑死。”

1. **[基础追问] M15 明明还没有接入业务请求，那它到底交付了什么？**

   可以答：M15 交付的是 **“能不能安全接入 LangFuse”的基线**，而不是业务埋点本身。它验证了 **Cloud key、SDK 4.14.1、span 写入、score 写入、flush 和查询可见性**；同时把 **配置入口、依赖边界、trace id 映射规则** 先定下来。这样 M16 真正接业务请求时，不需要边查 SDK 行为边改主链路，风险会小很多。

2. **[工程/深挖追问] 为什么不直接复用 DataPilot 自己的 `trace_id` 作为 LangFuse trace id？多维护一个 ID 会不会复杂？**

   可以答：多一个 ID 确实增加一点映射成本，但它保护了 **内部契约**。DataPilot 的 `trace_id` 已经服务 **API、响应头、JSONL、日志和 eval**，是项目自己的稳定语义；LangFuse trace id 则要满足第三方 SDK 的格式和查询习惯。M15 的做法是保留 **DataPilot trace id 作为主 ID**，LangFuse 生成独立 **32 位 hex id**，再通过 metadata 和 JSONL 字段建立映射。这样以后换观测平台或调整 LangFuse 写法，不会反向污染 **业务响应和历史 trace**。

3. **[工程/深挖追问] 为什么把 LangFuse SDK 放到 optional extra，而不是直接作为默认依赖？**

   可以答：因为 LangFuse 是 **旁路观测能力**，不是 DataPilot 的核心运行依赖。默认依赖里如果强绑定 SDK，本地开发、CI 或离线 eval 都会被外部观测平台影响。放进 `observability` optional extra 后，**普通路径不用安装 LangFuse 也能跑**；只有明确要看 Cloud trace 时，才用 `pip install -e .[observability]` 开启。这种边界能避免 **“观测系统坏了，业务系统也启动不了”** 的问题。

4. **[压力追问] 你这个 M15 听起来只是连了一下第三方平台，甚至还没接业务链路，这种模块放在简历里会不会显得很水？**

   可以答：如果把 M15 单独包装成一个“业务功能”，这个质疑是成立的，它确实没有让用户多问一个问题，也没有改变 `/api/query`。但我不会把它讲成业务能力，而会讲成 **引入外部平台前的风险隔离**：先验证 SDK、Cloud、score、flush、trace id 格式和配置边界，再进入业务链路。它的价值不是炫耀接了 LangFuse，而是避免后面 M16/M17 一边改主链路一边踩 SDK 和 Cloud 行为的坑。简历里更适合把它放在 Phase 3B 的上下文里讲：**外部观测平台接入前，我先固定了依赖边界和响应契约边界**。

### 验证与下一步

- 验证：LangFuse Cloud smoke PASS；trace 查询约 `0.6s` 可见；配置单测 **4 passed**；全量 pytest **90 passed, 2 skipped**。
- warning：仍是既有 Starlette/httpx deprecation，不影响 M15。
- 下一步：M16 做 Trace 双写与降级，重点是保留 JSONL 主链路、LangFuse 失败不影响 `/api/query` / eval，并处理 Cloud payload 脱敏。

可复制验证命令：

```powershell
# LangFuse SDK smoke，预期 auth / observation / score / flush 全部 PASS。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\smoke_m15_langfuse_sdk.py

# 查询本次 smoke trace 的可见性，预期能看到 visible_after_seconds 和 score_count=1。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\check_m15_langfuse_visibility.py a5b22262bb154b3a9b08b0b09b5f8cc5

# 配置单测，预期 4 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_config.py --basetemp=.agent_work\temp\pytest-m15-config

# 全量验证，预期 90 passed, 2 skipped。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\pytest-m15-full-2
```

**本地启动体验：**

M15 暂无新的 API 端点或页面，因为它只完成 LangFuse 接入基线。可交互体验在 LangFuse Cloud UI：用 smoke 输出的 trace URL 打开后，应能看到 `datapilot-m15-cloud-smoke-20260728T144148Z` 这条 trace 和 `rule:m15_smoke` score。真正从 `/api/query` 自动写 LangFuse trace，要等 M16。

## ★ M16 Trace 双写与降级（实际使用的 M16B）

（2026-07-28）

**简述**：M16 把原来“只能写 JSONL 文件”的 trace recorder，升级成 **TraceRouter + 多后端写入**。默认仍然只写 JSONL；只有 `LANGFUSE_ENABLED=true` 时，才额外写入 LangFuse。这个模块的核心不是炫技，而是把可观测系统做成 **旁路增强**：它能帮我们看 trace，但不能绑架 `/api/query`、JSONL 和 eval。

### 先用大白话讲

M16 做的事情，可以理解成：原来 DataPilot 只会把运行记录写进本地 JSONL 文件，现在它多了一个“分发器”，可以在不改变业务入口的情况下，把同一份 trace 同时写给不同地方。

这个分发器就是 **TraceRouter**。业务代码仍然只说“我要记录一次 trace”，至于这条 trace 是写 JSONL、写 LangFuse，还是以后写 EvalBench，**都由 router 决定**。这样业务链路不用到处知道 LangFuse 的存在。

更重要的是，LangFuse 在 M16 里不是主链路。Cloud 不通、key 配错、SDK 报错，都不能让 `/api/query` 失败，也不能让本地 JSONL 丢失。LangFuse 只是**旁路增强**：能写进去当然更好，写不进去也要留下失败状态，方便排查。

所以本模块的核心价值是：把 trace 写入从 **单一 JSONL 文件** 升级成 **可扩展、可降级、保护业务契约的多后端写入机制**。

### 这次做了什么

这次先保留了老入口 `append_trace(record, path=...)`。旧代码、测试和 eval 不需要知道内部已经换成了 router；它们继续传临时 trace 路径，JSONL 仍然写到指定文件。

然后新增了 **TraceRouter**：它按顺序调用多个 backend。启用 LangFuse 时，顺序是 `LangFuseBackend -> JSONLBackend`，这样 LangFuse 成功或失败后的 `langfuse_trace_id`、`langfuse_trace_url`、`langfuse_write_status` 能一起写进 JSONL。即使 LangFuse 报错，router 也只记录 warning，并继续写 JSONL。

最后新增了 **LangFuseBackend**。它按 M15 确认的 SDK 4.14.1 API 写入 `start_observation(trace_context=...)`，每条请求生成一个独立的 32 位 hex LangFuse trace id。DataPilot 自己的 `trace_id` 继续作为主 ID，只放进 LangFuse metadata 做反查。

### 新概念

- **TraceRouter**：像一个分发器。业务代码只把 trace 交给它，它再决定写 JSONL、写 LangFuse，未来也可以写 SQLite 或 EvalBench。
- **Backend 协议**：这里用 `TraceBackend` 描述“只要有 `record()` 方法，就能接进 router”。类比 Java 里的 interface，调用方依赖接口，不依赖具体实现。
- **旁路降级**：LangFuse 是增强能力，不是主系统的生命线。Cloud 不通、key 错、SDK 出问题时，API 不能 500，JSONL 也不能丢。
- **Flat spans**：M16 只把每个 `TraceStep` 平铺到同一个 LangFuse trace 下，不做父子嵌套。因为当前 trace 是请求结束后一次性生成，没有真实 started_at / ended_at，硬做时间线会变成伪数据。

### 代码阅读路线

1. **兼容入口**：`engine/trace/recorder.py`
   从 `append_trace()` 开始读。它现在很薄，只把 record 交给模块级 `trace_router`。然后看 `build_trace_router()`：默认只加 `JSONLBackend`；如果 `settings.langfuse_enabled` 为 true，才延迟导入并追加 `LangFuseBackend`。

2. **降级逻辑**：`TraceRouter.record()`
   重点看 `try/except`。每个 backend 独立执行，一个失败不会阻断另一个。LangFuse backend 失败时会把 `langfuse_write_status` 标成 `failed`，这样 JSONL 里能看出“请求成功了，但旁路观测失败了”。

3. **Cloud 写入**：`engine/trace/langfuse_backend.py`
   先看 `record()`：生成 `uuid4().hex` 作为 LangFuse trace id，写一个 `datapilot-query` root span，再把 `trace_steps` 平铺成 step spans，最后 `flush()`。读的时候别纠结 UI 里 trace name 的细节，M16 的重点是 ID 映射和降级。

4. **测试证明**：`tests/test_m16_trace_router.py`
   可以按风险读：默认关闭时 path override 不变；LangFuse 抛异常时 JSONL 还在；缺 key 时降级；fake client 成功时能看到 flat spans；API body 不出现 LangFuse 内部字段。

核心流向：

`/api/query`
→ `_record_trace()`
→ `append_trace()`
→ `TraceRouter`
→ `LangFuseBackend（可选）`
→ `JSONLBackend`

### 设计要点

- **为什么 LangFuse 先写、JSONL 后写**：不是让 LangFuse 变主路，而是为了让 JSONL 同一行能记录 LangFuse 的成功/失败状态和 trace id。LangFuse 失败会被捕获，JSONL 仍继续写。
- **为什么不做嵌套 span**：当前没有真实时间线，只有 post-hoc trace 快照。为了 UI 好看而伪造嵌套，会让后续排障误判。
- **为什么字段只进 JSONL 不进 API**：`langfuse_trace_id` 是观测系统内部映射，不是业务响应契约。API 用户只需要 DataPilot `trace_id`。
- **Cloud payload 最小化**：不上传完整 rows / docs，只上传摘要和计数，避免 Cloud trace 变成业务数据副本。

### 面试怎么讲

“M16 我把 trace recorder 从 **单一 JSONL 写入** 重构成 **TraceRouter 架构**，但没有改变 **业务入口和 API 响应**。`append_trace(record, path=...)` 仍然兼容旧调用；默认只写 JSONL，启用 LangFuse 时才额外写入 Cloud。LangFuse 失败会被捕获并标记 `langfuse_write_status=failed`，**JSONL 仍然落盘**。为了避免第三方系统接管内部契约，我保留 **DataPilot 自己的 `trace_id`**，单独生成 LangFuse trace id，并把映射写进 JSONL。这个模块体现的是我引入可观测平台时，优先考虑 **兼容性、降级和数据边界**，而不是只追求 UI 上能看到 trace。”

1. **[基础追问] M16 里的 TraceRouter 解决的核心问题是什么？**

   可以答：它解决的是 **“业务生成 trace”和“trace 写到哪里”耦合** 在一起的问题。M16 之前，`append_trace()` 基本等价于写 JSONL 文件；M16 之后，业务仍然调用 **同一个入口**，但内部由 **TraceRouter** 决定写 JSONL、写 LangFuse，或者未来写别的 backend。这样 `/api/query`、eval 和旧测试不用理解 LangFuse，也不会因为 **观测后端变化** 而跟着改。

2. **[工程/深挖追问] 你为什么让 LangFuse 先写、JSONL 后写？这听起来像把 LangFuse 放在主链路前面了。**

   可以答：顺序上 LangFuse 先写，是为了让 JSONL 同一行能记录 `langfuse_trace_id`、`langfuse_trace_url` 和 `langfuse_write_status`；语义上它 **仍然不是主链路**。TraceRouter 会捕获 LangFuse backend 的异常，失败时只标记 `failed`，然后继续写 JSONL。所以这里的重点不是“LangFuse 优先”，而是 **“JSONL 要带上旁路写入结果”**，方便后续 eval 和排障关联 Cloud trace。

3. **[工程/深挖追问] 如果 LangFuse key 配错、Cloud 不通或者 SDK 报错，M16 怎么保证 API 和 eval 不受影响？**

   可以答：M16 把 LangFuse 放在 **backend adapter** 里，router 对每个 backend **独立 try/except**。LangFuse 失败不会向上抛到 `/api/query`，而是把状态写成 `langfuse_write_status=failed`，再继续执行 **JSONLBackend**。测试里也覆盖了 **fake client 抛异常、缺 key 降级、API 响应体不暴露 LangFuse 字段** 这些路径，证明 **主响应契约和 eval trace 文件仍然稳定**。

4. **[工程/深挖追问] M16 为什么只做 flat spans，不做嵌套 span？这样在 LangFuse UI 里的可读性是不是差一些？**

   可以答：是的，flat spans 的 UI 结构不如真实嵌套调用链漂亮，但 M16 当时只有请求结束后的 `TraceRecord` 快照，没有 **每一步真实开始和结束时间**。如果为了 UI 好看硬造父子 span 和时间线，会让观测数据看起来更精细，实际上却是 **伪时间线**。M16 的边界是先证明 **双写、降级和映射可靠**；真实 lifecycle 下沉留给 M16B 单独验证。

5. **[工程/深挖追问] 为什么 Cloud payload 只上传摘要和计数，不上传完整 SQL rows 或文档内容？这会不会降低排障能力？**

   可以答：会牺牲一部分 Cloud 侧复盘细节，但这是有意的 **安全边界**。LangFuse Cloud 是第三方观测系统，不应该默认变成 **业务数据副本**。M16 上传 **表名、列名、步骤状态、SQL 摘要、行数和错误信息**，足够判断链路走到哪一步、是否生成了合理 SQL、是否执行成功；完整 rows 和更敏感的业务内容仍留在 **本地 JSONL 或数据库侧**。后续如果要上传样本，也应该 **显式脱敏和配置化**，而不是默认全量外发。

6. **[压力追问] TraceRouter 会不会就是把一个 append 写文件包装成一堆类？为了接 LangFuse 加这么多抽象，是不是典型过度设计？**

   可以答：这个质疑需要分场景看。如果系统永远只写一个 JSONL 文件，那 TraceRouter 确实没必要。但 M16 的目标不是美化 `append_trace()`，而是把 trace 同时送到 **本地 JSONL 和外部 LangFuse**，还要满足 **path override、失败降级、SDK 延迟导入、API 响应不暴露内部字段**。这些要求如果都堆在一个函数里，短期代码少，后续排障会更乱。所以我会承认它比原来复杂，但这个复杂度对应的是明确需求：**多后端写入 + 主链路不被观测系统拖垮**。同时它仍保留旧入口，调用方没有被迫理解新抽象。

### 验证与下一步

- 验证：M16 专项 **6 passed**；M5/config 相关回归 **7 passed**；eval smoke **6/6 passed**；真实 LangFuse + JSONL 双写 smoke `langfuse_write_status=ok`；全量 pytest **96 passed, 2 skipped**。
- warning：仍是既有 Starlette/httpx deprecation，不影响 M16。
- 下一步：M17 做 Scorer 分层与 LangFuse Score 回写，按 M16 写入的 `langfuse_trace_id` 关联分数。

可复制验证命令：

```powershell
# M16 trace router 专项，预期 6 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m16_trace_router.py --basetemp=.agent_work\temp\pytest-m16-final-related

# 真实 LangFuse + JSONL 双写 smoke，预期 langfuse_write_status=ok。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe .agent_work\temp\smoke_m16_trace_double_write.py

# eval 路径覆盖，预期 passed=6/6，trace 写入指定 .agent_work/temp 文件。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --trace .agent_work\temp\m16-eval-traces.jsonl --report .agent_work\temp\m16-eval-report.md

# 全量验证，预期 96 passed, 2 skipped。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\pytest-m16-full-final-2
```

**本地启动体验：**

M16 没有新增 API 端点，体验入口仍是 `/api/query` 和 trace 文件。默认 `LANGFUSE_ENABLED=false` 时，请求只写 JSONL；如果本地 `.env` 开启 LangFuse 并配置 key，请求会额外写入 LangFuse Cloud，同时 JSONL 行里出现 `langfuse_trace_id`、`langfuse_trace_url`、`langfuse_write_status`。实际业务 API 响应体不会出现这些字段。

## ★ M16B Trace Lifecycle 下沉预备分支

（2026-07-29）

**简述**：M16B 是在独立分支上做的一次观测底座实验。M16 已经能把请求结束后的 `TraceRecord` 写成 LangFuse flat spans，但那更像“事后整理日志”。M16B 把埋点下沉到 Text2SQL pipeline 和 SQL tool 的真实执行边界，让 LangFuse 看到更接近真实运行过程的 spans，同时 JSONL / eval 仍然消费同一套 `TraceStep`。

### 先用大白话讲

M16B 做的事情，可以理解成：M16 已经能把“事后整理好的运行记录”发给 LangFuse，但 M16B 想进一步验证，能不能在程序真正运行的时候，就把每一步开始、结束和失败记录下来。

这就像看外卖订单轨迹。M16 更像订单结束后给你一张总结：“已接单、已出餐、已送达”；M16B 更像实时轨迹：“骑手什么时候到店、什么时候取餐、什么时候遇到异常”。对简单链路来说，总结够用；但后续 RAG / Hybrid 这种多步骤 Agent，一旦出问题，实时边界会更有排障价值。

为了不让业务代码直接依赖 LangFuse，M16B 新增了 DataPilot 自己的 `TraceContext / SpanHandle`。pipeline 和 SQL tool 只记录“我的步骤开始了/结束了/失败了”，具体怎么写 LangFuse 被封装在 trace 层里。SQL Guard 和 SQL Execution 也放到 tool 内部记录，因为那里才是真正发生安全检查和数据库执行的地方。

所以本模块的核心价值是：验证 **live lifecycle span** 是否适合作为后续 RAG / Hybrid 的观测底座，同时保持 JSONL、eval 和业务代码边界不被 LangFuse 绑死。

### 这次做了什么

这次先新增了 **TraceContext / SpanHandle**。pipeline 不直接 import LangFuse，而是只说“开始一个步骤、结束一个步骤、这个步骤失败了”。这有点像 SpringBoot 里业务代码依赖自己的 service interface，而不是到处直接调用第三方 SDK。

然后把 `force_new_pipeline` 主链路迁移到 lifecycle：`schema_retrieval`、`join_path`、`query_plan`、`sql_generation`、`sql_guard`、`sql_execution`、`chart_generation` 都从同一套 lifecycle 生成 trace。SQL Guard 和 SQL Execution 没有在 pipeline 里事后补，而是通过 `run_sql_tool(trace_context=...)` 在工具层内部记录，因为真正的安全检查和数据库执行边界就在 tool 里。

最后补了一个显式去重字段 **`langfuse_span_mode`**。M16 的 `post_hoc` 模式继续在请求结束后由 backend 拆 spans；M16B 的 `live` 模式说明 spans 已经在执行中写过，最终 `LangFuseBackend.record()` 不能再重放一遍，否则 Cloud UI 会出现重复步骤。

### 新概念

- **Trace lifecycle**：不是等请求结束后再回忆发生了什么，而是在每个步骤开始和结束时记录。这样排障时能更像看真实调用链。
- **Live span**：运行中写入的 span。它比 post-hoc span 更接近真实时间线，适合后续 RAG / Hybrid 这种多步骤 Agent。
- **Post-hoc 去重**：同一件事不能既 live 写一遍，又请求结束后再拆一遍。`langfuse_span_mode` 就是告诉 backend 当前 trace 属于哪种模式。

### 代码阅读路线

1. **先看 lifecycle 抽象**：`engine/trace/lifecycle.py`
   从 `TraceContext.start_span()` 和 `SpanHandle.end()` 读起。重点理解业务代码只产生 DataPilot 的 `TraceStep`，LangFuse SDK 被藏在内部 writer 里。

2. **再看 pipeline 接入**：`engine/nl2sql/pipeline.py`
   顺着 `run_text2sql_pipeline()` 看一条请求怎么穿过 schema retrieval、plan、SQL generation、SQL tool 和 chart generation。每个早退分支都会走 `_with_trace_snapshot()`，避免异常路径漏掉 flush 或 JSONL 映射字段。

3. **最后看 SQL tool 下沉**：`engine/tools/sql_tool.py`
   这里是本模块最关键的分层选择。`run_sql_tool()` 的 `trace_context` 是可选参数，只有新 pipeline 传入；旧路径不传时行为不变。

核心流向：

`/api/query force_new_pipeline`
→ `run_text2sql_pipeline()`
→ `TraceContext.start_span()`
→ `run_sql_tool(trace_context=...)`
→ `TraceLifecycleSnapshot`
→ `TraceRecord(langfuse_span_mode=live)`
→ `JSONL + LangFuse`

### 设计要点

- **为什么不用事后补 span**：SQL Guard 和 DB 执行的真实边界在 `run_sql_tool()` 里，pipeline 事后补只能猜结果，不适合作为后续底座。
- **为什么 root span 不放进 JSONL steps**：LangFuse UI 需要请求级 root span；JSONL / eval 更依赖稳定的业务 step 序号，所以 root 只作为 LangFuse live observation。
- **为什么 M16B 不直接替换主线**：这是对照实验分支。它证明 lifecycle 能跑通，但是否合回，要看它对排障体验的提升是否值得代码侵入度。

### 面试怎么讲

“我在 M16B 做了一个 **Trace lifecycle 下沉分支**。原来的 LangFuse 接入是 **post-hoc**，把请求结束后的 trace_steps 平铺上传，能看但不够像真实调用链。M16B 新增了 DataPilot 自己的 **TraceContext / SpanHandle**，pipeline 和 SQL tool **只依赖这个抽象**，不直接依赖 LangFuse。**SQL Guard 和 SQL Execution 的 span 放在 tool 内部**，因为安全检查和数据库执行的真实边界在那里。为了避免 **live spans 和 post-hoc spans 重复**，我加了 `langfuse_span_mode`，live 模式下 backend 只保留 JSONL 映射，不再重放 spans。这个分支的价值是为 **RAG / Hybrid 阶段提前验证观测底座**，而不是等复杂度叠上来以后再一起改。”

1. **[基础追问] M16 已经能写 LangFuse 了，为什么还要做 M16B？**

   可以答：M16 能证明 **“请求结束后可以把 trace 写进 LangFuse”**，但它更像事后整理日志。M16B 要验证的是另一件事：能不能在 **pipeline 和 tool 的真实执行边界记录 span**。这个差异对后续 **RAG / Hybrid** 很重要，因为多步骤 Agent 出问题时，排障不只看最终结果，还要看 **每一步到底何时开始、何时结束、在哪里失败**。

2. **[工程/深挖追问] 为什么不让 pipeline 直接调用 LangFuse SDK，而要先做 `TraceContext / SpanHandle`？**

   可以答：因为 pipeline 应该表达 **DataPilot 自己的业务生命周期**，而不是被 LangFuse SDK 污染。`TraceContext.start_span()` 表达的是“schema retrieval 开始了”、“SQL execution 结束了”这类内部事件；LangFuse 只是当前的一个 writer。这样后续如果**换**成自建观测、EvalBench，或者同时写多个后端，pipeline 不需要到处改 import 和 SDK 参数。这个分层会增加一点抽象成本，但能保护 **长期架构边界**。

3. **[工程/深挖追问] SQL Guard 和 SQL Execution 为什么要下沉到 `run_sql_tool()` 里记录，而不是在 pipeline 调用前后包一层？**

   可以答：因为 **真实边界在 tool 里**。SQL Guard 的安全检查、SQL 执行、异常捕获和返回结构都发生在 `run_sql_tool()` 内部；如果 pipeline 在外层事后补 span，只能**根据返回结果猜**发生了什么，**异常路径和安全拦截很容易失真**。M16B 把 `trace_context` 做成可选参数传进 tool，既让新 pipeline 得到 **真实 span**，又不影响旧路径。

4. **[工程/深挖追问] `langfuse_span_mode` 看起来只是一个小字段，为什么你把它当成关键设计？**

   可以答：因为它解决的是 **重复观测** 的问题。M16 的 backend 会把请求结束后的 `trace_steps` 拆成 post-hoc spans；M16B 又在执行中写 live spans。如果没有 `langfuse_span_mode`，同一个步骤会在 LangFuse 里出现两次，排障时反而更混乱。这个字段明确告诉 backend：当前 trace 是 `live` 还是 `post_hoc`，**live 模式下只保留 JSONL 映射，不再重放步骤 span**。

5. **[工程/深挖追问] M16B 的代价是什么？如果要把它作为后续底座，你最担心什么？**

   可以答：代价是 **代码侵入度和测试复杂度都变高**。M16 只改 recorder/backend，业务代码几乎无感；M16B 要把 lifecycle 参数传进 pipeline 和 tool，后续 RAG、Hybrid 接入时也要遵守同一套 span 边界。最担心的不是复杂度本身，而是 **边界不统一**：有的步骤 live 记录，有的步骤 post-hoc 补，有的错误路径漏 flush。所以下一步如果继续基于 M16B，应该把 **span 命名、错误记录、flush 时机和 JSONL snapshot 规则** 固定成约定，避免每条链路各写一套。

6. **[压力追问] 你现在还没做 RAG / Hybrid，就先把 lifecycle 下沉到 pipeline 和 tool，这是不是提前设计未来、把当前代码弄复杂了？**

   可以答：这个问题很尖锐，而且我会承认：如果只看当前 Text2SQL 的功能效果，M16B 确实不是必需品，M16 的 post-hoc trace 已经能完成最小 LangFuse 验证。所以我没有把它说成“当前主链路必须这样”，而是把它放在 **M16B 分支** 做对照实验。它的价值是用相对可控的 Text2SQL 链路提前暴露 live span 的问题：SDK 边界、span 去重、tool 内部边界、flush 时机和 JSONL snapshot。如果这些问题等 RAG / Hybrid 多步骤链路叠上来后再一起改，代价会更大。换句话说，M16B 不是为了未来瞎抽象，而是用小范围实验验证未来底座是否值得采用。

### 验证与下一步

- 验证：M16B 专项 **14 passed**；全量 pytest **98 passed, 2 skipped**；临时 live smoke 写入 LangFuse Cloud 成功，JSONL 中 `langfuse_span_mode=live`、`langfuse_write_status=ok`。
- warning：仍是既有 Starlette/httpx deprecation，不影响 M16B。
- 下一步：把 M16A post-hoc 和 M16B lifecycle 放到相同 case 下对比 UI 排障价值、代码侵入度和测试复杂度，再决定是否作为 RAG / Hybrid 底座。

可复制验证命令：

```powershell
# M16B lifecycle / LangFuse 去重 / 新 pipeline 专项，预期 14 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m16_trace_router.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m16b-3

# 全量回归，预期 98 passed, 2 skipped。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests -x --basetemp=.agent_work\temp\pytest-m16b-full-2
```

**本地启动体验：**

M16B 仍然使用 `/api/query`，没有新增端点。体验方式是在 `.env` 中启用 LangFuse 后，请求 `force_new_pipeline=true` 的问题；JSONL 会写出 `langfuse_span_mode=live`，LangFuse Cloud UI 里能看到请求级 `datapilot-query` root span 和各个 Text2SQL step spans。

## ★ ★ M17 Scorer 分层与 Score 回写

（2026-07-29）

**简述**：M17 把 DataPilot 的 eval 从“只有一个 pass/fail 结果”升级成 **多 scorer 明细 + 旧报告兼容 + LangFuse Score 回写**。

### 先用大白话讲

M17 做的事情，可以理解成给 DataPilot 的 eval 系统换了一种“阅卷方式”。

以前评测一条 case，最后只会得到一个很粗的结果：这题过了，或者没过。这个结果能告诉我们“有没有问题”，但不能清楚告诉我们“问题出在哪里”。

M17 把这件事拆细了：一条 case 不再只有一个总结果，而是会拆成多项评分，比如 **表有没有找对**、**列有没有找对**、**安全拦截是否符合预期**、**查询结果是否匹配标准答案**，以及在显式开启时让 **LLM judge** 判断回答语义是否正确。

这些小分数会先用于本地 Markdown 报告，同时也能按 `langfuse_trace_id` 写回 LangFuse。这样以后打开一条 trace，不只是看“这次请求怎么执行”，还能看到“这次请求质量怎么样”。

所以 M17 的核心价值是：让 eval 从单纯的 **pass/fail**，升级成可解释、可回写、后续能支撑 Experiment 对比的评分体系。

### 这次做了什么

M17 把 eval 从“每条 case 只有一个 pass/fail”，升级为**多项规则评分、可选语义评分和 LangFuse Score 回写**，同时保持旧报告口径不变。

1. **为什么要拆分 scorer。**

   原来的 `_score_case()` 集中了 HTTP、route、安全、表、列、SQL、固定事实和结果匹配等判断。一旦失败，报告通常只留下一个最终原因，很难从整体上统计究竟是安全问题、结构问题还是答案问题。

   如果 LangFuse 再单独维护一套评分逻辑，本地 Markdown 和 Cloud Score 还可能出现口径分裂。

2. **建立本地 scorer 单一事实源。**

   M17 新增 `eval/scorers/`，用 `EvalScoreDetail` 表达每个评分项的名称、数值、是否通过、是否跳过、原因和 metadata。

   原来的规则被迁入 `rule_scorers.py`：

   - **L1** 负责 HTTP、route、安全、表、列和 SQL 执行；
   - **L2** 负责固定事实、结果匹配和其他确定性输出检查。

   `_score_case()` 仍保留为兼容薄壳，所以旧 Markdown 的 pass/fail 和 `expected_value_ok`、`blocked_as_expected` 等 reason 不会因为内部重构而改变。

3. **保留最小 L3 LLM-as-Judge，但默认不启用。**

   M17 增加 `llm:correctness`，只在命令行传入 `--judge-model` 或配置 `EVAL_JUDGE_MODEL` 时运行。

   Judge 适合补充语义正确性，不能替代表、列、安全和固定事实等确定性检查。它有费用、延迟和模型波动，调用失败时只产生 skipped/null detail，不会阻断整轮 eval。

4. **把同一批评分写回 LangFuse。**

   Score writer 从 JSONL 读取 DataPilot `trace_id` 到 `langfuse_trace_id` 的映射，然后直接按 LangFuse trace id 写入评分。

   它不等待 Cloud trace 查询可见，因为 ingestion 存在延迟；没有有效映射时，本地报告照常生成，只跳过 Cloud 回写。

5. **把延迟作为观测指标，而不是正确率门槛。**

   `rule:latency_p95` 会作为 numeric score 写入 LangFuse，但不参与旧 Markdown pass/fail。

   原因是当前延迟容易受到网络和模型服务波动影响。M17 需要先守住答案、安全和结果口径，不能因为一次外部服务变慢就把正确答案判错。

6. **最终验证了本地与 Cloud 使用同一套评分结果。**

   聚焦测试为 **27 passed**；默认 eval 在未配置 judge 时显示 `judge_model=<disabled>`；真实 LangFuse smoke 成功回写 **16 条 score**；M16B live lifecycle 场景也成功生成并写入 **6 条 score payload**。

   M17 没有把规则评分迁到 LangFuse 托管 evaluator，因为那会额外引入 UI 配置、observation target 和调度依赖。当前结果是：**规则留在本地统一执行，LangFuse负责承载和展示同一批 score。**

> **M24 章节结束时补充**：L3 `llm:correctness` 仍是显式开启的辅助评分，当前正确率主口径不是 LLM-as-Judge。M22-M24 已继续把 Context、Output、Result 和 Manual 合同拆开，并加入精确投影、SQL AST fidelity 与 `output_contract`；因此 M17 早期的 `table_hit / column_recall / schema_context` 标签不能脱离 trace 直接解释成检索成功或失败。

### 新概念

- **Scorer 明细**：一条 case 不再只有一个总分，而是拆成多条 detail，例如 `rule:table_hit`、`rule:column_recall`、`rule:safety_compliance`。
- **L1/L2/L3 分层**：L1 看结构和安全，L2 看结果是否匹配固定事实，L3 才让 LLM 做语义判断。能用规则就不用 LLM。
- **Score 回写**：把本地评测结果写回 LangFuse trace。这样你在 Cloud UI 看某条 trace 时，不只看到它怎么跑，还能看到它每个评分项的结果。
- **兼容薄壳**：旧函数名 `_score_case()` 保留，但内部调用新 scorer。类比 SpringBoot 里旧 Controller endpoint 不变，内部 service 换了新实现。

### 代码阅读路线

1. **先看评分数据结构**：`eval/scorers/base.py`
   重点看 `EvalScoreDetail`。它是 M17 的核心：既能表达 pass/fail，也能表达 skipped/null，还能带 metadata 写回 LangFuse。

2. **再看规则评分**：`eval/scorers/rule_scorers.py`
   从 `score_case_rules()` 开始读。它按旧 `_score_case()` 的顺序执行规则：先判断 pipeline mode、HTTP/route，再看安全、表、列、SQL success、latency 和结果检查。重点理解这里是 **单一事实源**，不是和旧函数并行判断。

3. **然后看 eval 薄壳**：`eval/run_eval.py`
   看 `_score_case()` 和 `run_cases()`。`_score_case()` 负责把 detail 汇总成旧 `EvalScore`；`run_cases()` 则把 detail 保存在 `EvalResult.score_details`，给 LangFuse 回写使用。

4. **最后看 Score 回写**：`eval/scorers/langfuse_scores.py`
   重点看 `build_langfuse_score_payloads()`。它不查 Cloud trace 是否可见，只读 JSONL 里的 `langfuse_trace_id`。这和 M16/M16B 的双 ID 策略连上了。

核心流向：

`EvalCase`
→ `/api/query`
→ `AgentResponse`
→ `score_case_rules() / llm:correctness`
→ `EvalResult.score_details`
→ `Markdown summary`
→ `LangFuse create_score(trace_id=langfuse_trace_id)`

### 设计要点

- **为什么不直接用 LangFuse 托管 evaluator**：M17 要保持 Markdown、JSONL 和 LangFuse Score 同一套口径。把规则评分放到 LangFuse UI 托管执行会引入 observation target、UI 配置和调度依赖，现阶段会扩大范围。
- **为什么 L3 默认关闭**：外部 LLM judge 有费用、延迟和抖动，不能让普通 eval 默认变慢或变贵。
- **为什么 score 回写不等待 trace 可查询**：LangFuse ingestion 有延迟。M16 已经把 `langfuse_trace_id` 写到 JSONL，M17 直接按这个 ID 写 score，查询可见性留给 M18 smoke。
- **为什么 latency 不影响 pass/fail**：延迟是重要观测指标，但本地网络和 LLM 波动很大。M17 把 `rule:latency_p95` 作为可回写 score，不让它改变旧 Markdown 的正确率。

### 面试怎么讲

“我在 M17 做的是把 DataPilot 的 eval 从一个大函数里的 **pass/fail 判断**，升级成 **可解释、可复用、可回写的 scorer 分层**。原来 `_score_case()` 既负责判断表列、安全、结果，又负责产出 Markdown 需要的总结果；这样继续接 LangFuse Score 时很容易出现 **两套评分口径**。M17 把规则评分迁到 `eval/scorers/`，每条 case 先产出多条 `EvalScoreDetail`，再汇总成旧 `EvalScore`，所以 **旧报告不变**，LangFuse 也能拿到 **同一批分数**。**L3 judge 默认关闭**，只有显式传 `--judge-model` 或配置 `EVAL_JUDGE_MODEL` 才运行。Score 回写只依赖 JSONL 里的 `langfuse_trace_id` 映射，**不等待 Cloud trace 可查询**。”

1. **[基础追问] 你说 M17 把 scorer 拆出来了，那它和原来的 `_score_case()` 到底是什么关系？为什么不直接删掉旧函数？**

   可以答：直接结论是，`_score_case()` 现在是 **兼容薄壳**，真正的评分逻辑在 `eval/scorers/`。不直接删掉旧函数，是因为现有 **Markdown 报告、测试和历史 eval** 都依赖旧的 `EvalScore` 返回结构。M17 的取舍是多保留一层入口，但换来 **低风险迁移**：新 scorer 负责 **单一事实源**，旧入口只负责汇总和兼容。验证上，旧的 `test_phase3a_eval.py` 继续通过，同时新增 `test_m17_scorers.py` 覆盖 **score details 和 LangFuse payload**。

2. **[工程/深挖追问] 如果本地 Markdown 报告和 LangFuse 上的分数不一致，你会怎么定位？**

   可以答：我会先确认两边是否来自 **同一批 `EvalScoreDetail`**。M17 的设计就是让 `rule_scorers.py` 产出统一 detail；Markdown 只走 `summarize_score_details()` 汇总，LangFuse 只把同一批 detail 转成 `LangFuseScorePayload`。如果不一致，优先查两层转换：**detail 到 summary 的汇总逻辑**，或者 **detail 到 LangFuse payload 的映射逻辑**，而不是维护两套评分规则。这个设计的核心价值是把排查范围缩小到 **“转换层”**，避免评分口径漂移。

3. **[工程/深挖追问] 为什么 `rule:latency_p95` 不参与 pass/fail？如果延迟很高，难道不应该算失败吗？**

   可以答：延迟应该被观测，但不应该在 M17 改变 **旧 eval 的正确率口径**。当前 eval 的主门禁是 **答案、安全和结果是否正确**；延迟受本地网络、LLM provider、LangFuse SDK 上传状态影响很大。如果让 latency 直接决定 pass/fail，可能会把一次外部抖动误判成 **业务能力退化**。所以 M17 把 `rule:latency_p95` 作为 numeric score 回写 LangFuse，用于 **趋势观察**；真正是否设为硬门禁，应该等 M18 或后续有稳定环境和阈值后再决定。

4. **[工程/深挖追问] 为什么 M17 不直接使用 LangFuse 的托管 evaluator，而是继续在本地实现 scorer？这是不是重复造轮子？**

   可以答：不是完全不用 LangFuse evaluator，而是 M17 不把它作为 **主评分口径**。DataPilot 已经有 **YAML cases、Markdown 报告和一套历史规则评分**，如果直接迁到 LangFuse 托管 evaluator，会引入 **UI 配置、observation target 和调度依赖**，短期内容易让本地报告和 Cloud 分数各说各话。M17 的目标是先保证 **评分口径单一**：本地 scorer 产出 details，同时服务 Markdown 和 LangFuse Score。后续 M18 / EvalBench 如果验证 LangFuse evaluator workflow 足够稳定，再考虑把部分 evaluator 托管化。

5. **[压力追问] 你这个 scorer 分层会不会把评测做得很复杂，但实际模型效果没有提升？从业务结果看有什么用？**

   可以答：这个质疑合理，因为 scorer 分层本身不会让模型立刻答得更准，它不是模型优化模块。M17 的目标是解决另一个问题：当模型失败时，能不能知道失败发生在 **表选择、列召回、安全、结果匹配、语义判断** 哪一层。没有这个拆分，业务结果只有 pass/fail，后续优化很容易凭感觉改 prompt。M17 的价值是把“模型效果提升”前置成可诊断的评测基础：它不直接提升答案，但能让后续提升有依据、有定位、有 Cloud trace 证据。这个边界要讲清楚，不能把 scorer 说成模型能力本身。

### 验证与下一步

- 验证：M17 scorer/eval 专项 **27 passed**；默认 eval CLI 返回 0，judge disabled；真实 LangFuse score smoke `ok:16`；M16B live score smoke `ok:6`；全量 pytest **104 passed, 2 skipped**。
- warning：仍有既有 Starlette/httpx deprecation；真实 LangFuse smoke 中还有 SDK OTLP trace export `WinError 10013` warning，但 score writer 返回 ok，不阻断 M17。
- 下一步：M18 做正式一键 smoke、trace/score 可见性检查和手动 Experiment 记录。

可复制验证命令：

```powershell
# M17 scorer + 旧 eval 兼容测试，预期 27 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m17_scorers.py tests\test_phase3a_eval.py --basetemp=.agent_work\temp\pytest-m17-3

# 默认 eval CLI，预期 judge_model=<disabled>，命令返回 0。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --report .agent_work\temp\m17-eval-report-2.md --trace .agent_work\temp\m17-eval-traces-2.jsonl

# 全量回归，预期 104 passed, 2 skipped。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests -x --basetemp=.agent_work\temp\pytest-m17-full
```

**本地启动体验：**

M17 仍然没有新增 API 端点，体验入口是 eval CLI 和 LangFuse Cloud UI。默认运行 `python -m eval.run_eval` 会生成 Markdown 报告；如果 `.env` 中启用 LangFuse，eval 会在 JSONL 里找到 `langfuse_trace_id` 并把规则分数写回对应 trace。要体验 L3 judge，则显式加 `--judge-model <模型名>`；不加时不会调用外部裁判模型。

## ★ M18 Phase3B 收尾

（2026-07-30）

**简述**：简单说，M17 是“能打分”，M18 是“以后怎么一键确认整条链路还正常”。M18 给 Phase 3B 做收口：新增 **一键 LangFuse smoke 脚本**，复核 API / JSONL / trace mapping / score / visibility；同时手动验证 LangFuse **trace → Dataset** 工作流，明确 Experiment run 当前需要 **LLM key 或 Webhook**，不在 DataPilot 里临时补远程实验服务。

### 先用大白话讲

| 模块     | 证明了什么                                         |
| -------- | -------------------------------------------------- |
| M15      | LangFuse 云平台账号能连、能写数据（SDK/Cloud/key） |
| M16/M16B | 业务请求的 trace 能自动写到 LangFuse（还能降级）   |
| M17      | eval 评分能写回 LangFuse 的 trace 上               |

但这些都是散装的。M18 新增 `scripts/smoke_phase3b_langfuse.py`：发一个真实 `/api/query` 请求来检查一下整条链路是否正常。一条命令就能检查 **配置、API 请求、JSONL trace、LangFuse trace id、score 回写和 trace 可见性**。

同时，M18 也验证了 LangFuse Experiment 的真实 UI 边界。Dataset 可以从 trace 创建，这部分是可用的；但 `Run experiment` 不是把已有 trace 手动编成两组 run，而是要么让 LangFuse 自己用 Prompt + LLM key 执行，要么通过 Webhook 调远程服务。DataPilot 当前没有这个 webhook runner，所以 M18 不临时扩展架构。

所以本模块的核心价值是：把 Phase 3B 的 **trace → score → dataset** 能力收成可复用基线，并把 **Experiment run 需要 EvalBench 级 runner** 这件事提前验证清楚。

### 这次做了什么

简单说，M17 是“能打分”，M18 是“以后怎么一键确认整条链路还正常”。

这次先新增了 `scripts/smoke_phase3b_langfuse.py`。它不直接绕过业务函数，而是复用 eval 的 `seeded_api_client()`，用内存 SQLite seed 调真实 `/api/query`。这样既不污染 MySQL 开发库，也能验证 API 响应、JSONL trace 和 LangFuse 映射是不是连在一起。

脚本有两种模式。默认模式允许 `LANGFUSE_ENABLED=false`，这时 API 和 JSONL 必须 PASS，LangFuse 相关检查输出 SKIP。验收模式加 `--require-langfuse`，如果 LangFuse disabled、缺 key、SDK 不可用、score 写入失败或 visibility 查询失败，就会明确 FAIL。

然后跑了真实 Cloud smoke。裸连时，trace mapping 和 score 写入都成功，但 trace visibility 查询遇到 Windows `WinError 10013`；设置项目代理 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` 后，全链路 PASS，能查到 observations。

最后做了手动 Experiment workflow smoke。我们准备了 5 条临时 case，DeepSeek 跑出 `4/5`、Qwen `qwen3.7-plus` 跑出 `3/5`，两组分数都写回 LangFuse。你在 UI 中创建了 Dataset 并导出 5 条 ACTIVE items，证明 trace → Dataset item 可用。但 UI 的 run 入口要求 LLM key 或 Webhook URL，所以本阶段只记录这个边界，不临时实现远程 runner。

> Phase 3B 收口后又做了两轮严格 review，重点不是新增功能，而是把 **“能跑通”加固成“边界更可信”**。第一轮主要修了几类问题：`LANGFUSE_ENABLED=true` 但 SDK 不可用时，新 pipeline 现在会 **降级为本地 trace**，不会打断 `/api/query`；LangFuse score 只会回写到 `langfuse_write_status=ok` 的 trace，避免给未确认上传成功的 trace 写分；危险 SQL 预检下沉到 `new_text2sql` pipeline 的统一 `sql_guard` lifecycle，blocked path 也能留下 `sql_guard` step；`equals` scorer 不再把整个 JSON 做 substring，`result_match` 也改为按列名对齐比较，减少 eval 误判。
>
> 第二轮继续收边界：危险 SQL 预检现在发生在 `get_default_llm_client()` 之前，确保 **安全拦截不依赖 LLM 配置是否健康**；Markdown report 的 `Score Summary` 增加 `case_id`，多 case 报告更容易定位具体分数；M15 面试追问编号跳号已修；LangFuse Dataset CSV 从仓库跟踪中移除并移动到 `.agent_work/temp/`，保留复盘素材但不再污染根目录或提交范围。验证侧新增了对应负向测试，当前复审修复 focused 测试和全量 pytest 均已通过。

### 新概念

- **Smoke 脚本**：不是完整 benchmark，而是快速确认关键链路还活着。M18 的 smoke 关心“能不能跑通 API、写 JSONL、写 score、查 trace”，不追求模型答题满分。
- **Trace visibility**：LangFuse SDK `flush()` 和 score 写入成功，不等于 trace 立刻能被查询 API 查到。M18 把 score write 和 visibility query 拆开，避免把 ingestion 延迟误判成 score 失败。
- **Dataset item**：LangFuse 里可复用的测试样本。它通常包含 input、expected output、metadata 和 source trace。后续 EvalBench 可以把 case 管理和 Dataset 对齐。
- **Remote experiment webhook**：LangFuse UI 触发实验时调用你的服务 URL，让你的服务读取 dataset、执行系统、再把 run 结果写回 LangFuse。它更像后续 EvalBench adapter，不适合 M18 临时补。

### 代码阅读路线

1. **一键 smoke 入口**：`scripts/smoke_phase3b_langfuse.py`
   从 `main()` 和 `run_smoke()` 看。它先读取 Settings，再按 `require_langfuse` 决定 Cloud 检查是 SKIP 还是 FAIL。重点理解这里不是 eval runner，而是 Phase 3B 的健康检查器。

2. **真实 API 调用**：`scripts/smoke_phase3b_langfuse.py`
   看 `_run_api_smoke()`。它用 `seeded_api_client()` 发 `/api/query`，并检查 JSONL 最后一行的 `trace_id` 是否等于响应体 trace id。这里守住的是 **API seam**，不是内部函数单测。

3. **Score 与 visibility**：`scripts/smoke_phase3b_langfuse.py`
   看 `_write_smoke_score()` 和 `_query_trace_visibility()`。前者按 JSONL 里的 `langfuse_trace_id` 写 `rule:m18_smoke`；后者再轮询 observations。两者分开，是为了把“score 写入失败”和“trace 暂时查不到”区别开。

4. **测试门禁**：`tests/test_m18_phase3b_smoke.py`
   重点看三个测试：默认关闭时 Cloud 检查 SKIP、`--require-langfuse` 时 disabled 必须 FAIL、PENDING 不等于 FAIL。这保证 smoke 不会因为设计语义含糊而变成脆弱脚本。

核心流向：

`smoke_phase3b_langfuse.py`
→ `seeded_api_client()`
→ `/api/query`
→ `TraceRouter / JSONL / LangFuse`
→ `LangFuseScoreWriter`
→ `LangFuse observations query`

### 设计要点

- **为什么 smoke 复用 `/api/query`**：M18 要检查真实响应契约、trace path override 和 LangFuse 映射。如果直接调用内部 pipeline，会绕过 API seam。
- **为什么不自动创建 Experiment run**：计划要求验证 UI Experiment 体验。LangFuse 当前 UI run 需要 LLM key 或 Webhook；自动补一个 webhook 会扩大到 EvalBench adapter 范围。
- **为什么保留 SKIP / PENDING**：默认关闭 LangFuse 是项目正式行为，不能算失败；trace ingestion 有延迟，短时不可见也不能和 score 写入失败混在一起。
- **为什么记录 Dataset metadata 噪音**：导出的 CSV 里带 telemetry 字段和 public key。public key 不是 secret，但正式 EvalBench dataset 应该清理 metadata，避免样本变脏。

### 面试怎么讲

“我在 M18 做的是 Phase 3B 的 **可观测性收口**。前面已经有 LangFuse trace 双写和 score 回写，但还缺一个可重复的总验收入口，所以我新增了 `scripts/smoke_phase3b_langfuse.py`：它用真实 `/api/query` 跑一条请求，检查 **API 响应、JSONL trace、LangFuse trace id 映射、Score 回写和 trace visibility**。默认 `LANGFUSE_ENABLED=false` 时 Cloud 检查是 SKIP，不影响主链路；显式 `--require-langfuse` 才把 Cloud 作为硬门禁。Experiment 这部分我没有临时造 webhook，而是按 UI 真实验证：Dataset 创建可用，但 run 需要 **LLM key 或 Webhook runner**，所以后续应该放到 EvalBench 里正式设计。”

1. **[基础追问] M18 和 M17 的区别是什么？M17 不是已经能写 score 了吗？**

   可以答：M17 解决的是 **评分能力本身**：把 scorer 拆出来，并按 JSONL `langfuse_trace_id` 写回 LangFuse Score。M18 解决的是 **阶段收口和可重复验证**：用一个正式 smoke 把 API、JSONL、trace mapping、score write 和 trace visibility 串起来。简单说，M17 是“能打分”，M18 是“以后怎么一键确认整条链路还正常”。

2. **[工程/深挖追问] 为什么 smoke 默认不要求 LangFuse enabled？这样会不会降低验收强度？**

   可以答：默认不要求，是因为 DataPilot 的正式设计就是 **LangFuse 旁路增强，默认关闭**。如果默认 smoke 因 Cloud 不可用而失败，就违背了 M15-M16 定下的降级边界。但 M18 同时提供 `--require-langfuse`，在阶段验收或真实 Cloud 检查时可以把 LangFuse 变成硬门禁。也就是说，默认 smoke 验证主链路，require 模式验证 Cloud 闭环。

3. **[工程/深挖追问] 你怎么处理 trace 已经写了 score 但 UI/API 暂时查不到 trace 的情况？**

   可以答：M18 把 **score write** 和 **trace visibility** 拆成两个检查点。Score 回写只依赖 JSONL 里的 `langfuse_trace_id`，成功就说明 Score API 已接受；visibility 查询另做轮询，短时不可见可以报 PENDING。这样排障时能区分是 score 写入失败、LangFuse ingestion 延迟，还是本机网络查询失败。

4. **[压力追问] 你说 Phase 3B 收口了，但 LangFuse Experiment run 实际上没跑通，这是不是只能算半成品？**

   可以答：如果把 Phase 3B 的目标定义成“完整自动化 Experiment 平台”，那这个质疑是对的，M18 没有完成那件事。但 Phase 3B 的目标是验证 LangFuse 是否适合作为 **DataPilot 的可观测和评测前置底座**。这次已经跑通了 **API / JSONL / live trace / score 回写 / trace visibility / trace 到 Dataset item**，同时也验证出 UI run 的真实边界：它需要 LLM key 或 Webhook runner。我的结论不是“Experiment 平台完成了”，而是 **DataPilot 侧闭环到 score 和 dataset；真正的 run 编排应该进入 EvalBench 设计**。这比在 M18 临时补一个不完整 webhook 更诚实，也更有工程边界感。

### 验证与下一步

- 验证：M18 focused **9 passed**；脚本 compileall 通过；默认 smoke API / JSONL PASS、LangFuse SKIP；带代理的真实 LangFuse require smoke 全 PASS；全量 pytest **107 passed, 2 skipped**。
- warning：仍有既有 Starlette/httpx deprecation；裸连 LangFuse Cloud visibility 查询曾触发 Windows `WinError 10013`，设置 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` 后通过。
- 下一步：进入 Phase 3 RAG / Hybrid，基于 M16B live lifecycle 继续扩展多步骤链路；独立 EvalBench 阶段再设计 LangFuse Webhook / SDK Experiment runner。

可复制验证命令：

```powershell
# M18 smoke + M17 score 兼容测试，预期 9 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m18_phase3b_smoke.py tests\test_m17_scorers.py --basetemp=.agent_work\temp\pytest-m18-final-focused

# 默认 smoke：预期 API / JSONL PASS，LangFuse 因默认关闭显示 SKIP。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_phase3b_langfuse.py --trace .agent_work\temp\m18-final-default-traces.jsonl --visibility-timeout-seconds 5

# 真实 LangFuse smoke：预期全部 PASS；当前 Windows 环境建议显式设置代理。
$env:LANGFUSE_ENABLED='true'
$env:HTTP_PROXY='http://127.0.0.1:7897'
$env:HTTPS_PROXY='http://127.0.0.1:7897'
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\smoke_phase3b_langfuse.py --trace .agent_work\temp\m18-final-langfuse-traces.jsonl --require-langfuse --visibility-timeout-seconds 45

# 全量回归，预期 107 passed, 2 skipped。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests -x --basetemp=.agent_work\temp\pytest-m18-full
```

**本地启动体验：**

M18 没有新增 API 端点，体验入口是 smoke CLI 和 LangFuse Cloud UI。先运行默认 smoke，确认本地 API / JSONL 主链路；再按需开启 `LANGFUSE_ENABLED=true` 和代理运行 require smoke。LangFuse UI 侧可以打开本次 trace，查看 `datapilot-query` live spans 和 `rule:m18_smoke` score；Dataset 页面能看到 `datapilot-m18-workflow-smoke-20260730` 的 5 条 workflow items。

## ★ M19 Trace Failure Triage：把观测数据变成改进闭环

（2026-08-02）

**简述**：M19 补上 Phase 3B 最后一个关键问题：LangFuse 和 JSONL 不只是“能看见 trace”，还要能回答“失败到底更像哪一层的问题，下一步该修哪里”。这一步没有改业务查询能力，也没有改正式测试集，而是在 eval 报告里新增 **Failure Triage Summary**，把失败 case 归成 `schema_retrieval / schema_context / query_plan / plan_validation / sql_generation / sql_guard / sql_execution / result_match / scorer_issue / unknown` 等阶段，并给出 `fix_schema_desc / fix_pipeline / fix_scorer / manual_review / infra_retry` 这类下一步动作。

### 先用大白话讲

前面 M15-M18 相当于给 DataPilot 装了监控摄像头：能把一次请求的每个步骤拍下来，也能把分数贴回 LangFuse。但光有摄像头还不够，出了问题时你还要有人帮你看录像、圈出“可能是这里坏了”。

M19 做的就是这个“看录像做初步标注”的工作。它不会神奇地修好模型，也不会替你直接改测试集；它只是把失败 case 归类成更容易行动的清单：有些是 schema 上下文没给够，有些是 QueryPlan 生成失败，有些是 SQL 跑出来但结果和标准答案不一致，有些证据不够只能人工复核。

所以本模块的核心价值是：把 **trace / score / report** 从“记录事实”推进到“指导下一步怎么修”。

### 这次做了什么

M19 新增了一个本地优先的 `eval/triage.py`：它读取 eval result、score details 和 JSONL trace，对每条失败、跳过或需要人工复核的 case 生成 `failure_stage`、`failure_reason`、`needs_action`、`evidence_step` 和 `confidence`。`eval/run_eval.py` 现在会把这些信息写进 Markdown report，并可用 `--triage-json` 输出 JSON，方便后续做 A/B failure distribution 对比。

LangFuse 仍然只是增强：如果 JSONL 里有确认成功的 `langfuse_trace_id`，M19 会把 `triage:failed`、`triage:failure_stage`、`triage:needs_action`、`triage:confidence` 写成 LangFuse Scores，方便在 Cloud UI 里筛选；如果 LangFuse 关闭、网络失败或 trace id 缺失，本地报告照常生成，只把 score write 统计为 skipped / failed。

最重要的边界是：M19 **不自动改正式 case 集**。它可以输出“建议沉淀为 regression 的候选”，但不会直接写 `eval/cases/*`，因为这会影响长期基线，必须单独确认。

### 新概念

- **Failure triage**：不是只看 pass/fail，而是把失败映射到“可能的问题层”。它是排障导航，不是绝对真因。
- **Evidence-first**：归因优先看 trace step 的 `status/error_type` 和 scorer 明细，比如 `rule:table_hit` 失败更像 schema retrieval，`rule:result_match` 失败更像结果口径/SQL 输出问题。
- **本地闭环优先**：评测报告和 JSON 文件必须在 `LANGFUSE_ENABLED=false` 时也完整可用；Cloud 只是筛选和展示增强。
- **A/B failure distribution**：两个 run 不只比较总分，还要比较失败结构，比如新方案 `schema_context` 失败少了但 `result_match` 失败多了，这比一个总分更能指导下一步。

### 代码阅读路线

1. **归因核心**：`eval/triage.py`
   先看 `FailureTriage` 这个数据结构，它就是 M19 输出的一条“失败诊断卡片”。然后看 `triage_result()`：它按 **trace step → error_type → scorer detail → manual fallback** 的顺序归因。最后看 `build_triage_score_payloads()` 和 `compare_triage_files()`，前者把本地 triage 变成 LangFuse Score，后者把两个 run 的失败阶段分布做本地对比。

2. **评测入口**：`eval/run_eval.py`
   从 `main()` 开始看：正常 eval 跑完后，先写原有 rule score，再调用 `triage_results()` 生成 M19 归因，然后写 Markdown report 和可选 JSON。`_append_failure_triage_summary()` 只负责展示，不负责判断，这样报告层不会变成第二套归因逻辑。

3. **测试样例**：`tests/test_m19_failure_triage.py`
   这个文件是理解 M19 的最快入口：它用很小的假 `EvalResult` 和 JSONL trace 覆盖 SQL Guard、SQL Execution、Result Match、LangFuse mapping 降级和本地 A/B 对比。读测试能直接看到每类失败应该被归到哪里。

核心链路：

`EvalResult + JSONL Trace`
→ `FailureTriage`
→ `Markdown Failure Triage Summary`
→ `triage JSON`
→ `LangFuse triage scores（可选）`
→ `A/B failure distribution（本地）`

### 设计要点

- **不让 LangFuse 成为强依赖**：M19 第一交付是本地 Markdown / JSON。Cloud 可用时写 score，不可用时只记 skipped / failed。
- **启发式而非 LLM 自由判断**：本模块不让 LLM 读完整 trace 来“自由发挥”，因为那会引入成本、抖动和新一层误判。第一版只用确定性证据做归因。
- **建议回归候选但不改正式基线**：自动写 case 会改变评测结构和长期基线，所以 M19 只输出 candidate list，是否沉淀为 regression 要单独确认。
- **保留 unknown / manual_review**：证据不足时宁愿不判断，也不把猜测包装成真因。

### 面试怎么讲

可以这样讲：

“我在可观测性阶段最后补了一层 failure triage。之前 eval 只能告诉我这条 case 过没过，LangFuse 能告诉我每一步 trace 长什么样，但它们还没有直接告诉我下一步该修哪。M19 做的是把 eval 的 scorer 明细和 JSONL trace 结合起来：如果 schema retrieval 没召回表，就归到 schema_retrieval；如果 QueryPlan validation 挡住了，就归到 plan_validation；如果 SQL 跑通但 result_match 不一致，就归到 result_match；如果证据不足，就保留 unknown/manual_review。报告里会聚合每类失败数量和建议动作，LangFuse 可用时再把 triage 结果写成 score，方便 Cloud UI 筛选。这样 A/B 不再只看总分，而能看到失败结构有没有变好。”

压力追问可以这样答：

“这不是一个自动判案系统，它只是工程排障建议。比如 `missing_columns` 第一版会归到 schema_context，但真实原因可能是 schema 描述不足、SQL alias 不一致或 scorer 太严格，所以报告里必须保留 `failure_reason` 和 `evidence_step`，不能只给一个标签。对 `review_required` 的困难 case，我宁愿保守标成 manual_review，也不让系统过度自信。”

### 验证与下一步

- 单元测试：M19/M17 focused tests 15 passed；M16-M19 focused tests 31 passed。
- 全量测试：`121 passed, 2 skipped`。
- 默认 smoke：`passed=6/6`，LangFuse triage score 因本地模式正常 `skipped=24`。
- LangFuse enabled smoke：`passed=5/6`，`langfuse_triage_scores=ok:24`，说明四类 triage score 可回写。
- DeepSeek `deepseek-v4-flash` 当前快照：formal `7/10`，challenge `9/16`，diagnostic `19/32`。
- Diagnostic 主展示集的失败结构：`schema_context=6`、`schema_retrieval=1`、`result_match=2`、`plan_validation=1`、`sql_guard=1`、`unknown=2`、`query_plan=1`、`sql_generation=1`；下一步动作聚合是 `fix_schema_desc=7`、`fix_pipeline=5`、`manual_review=3`。
- 下一步：进入 Phase 3 RAG / Hybrid 时，复用 M16B live lifecycle 和 M19 triage 口径；如果要把候选失败样本写回正式 regression，需要单独确认。

### 这次测试怎么看

M19 的测试结果要分两层读，不能只盯着 `passed=19/32` 这个总分。

第一层是**代码能力是否实现**：看 `pytest`、smoke 和 LangFuse score 回写。这里的结论是通过的：M19 focused tests、M16-M19 focused tests、全量 pytest 都通过；本地 smoke 能在 LangFuse 关闭时生成 triage；LangFuse enabled smoke 能把 6 条 smoke case 的 24 个 triage score 写回 Cloud。这说明 **M19 这个工具本身能工作**。

第二层是**当前 Text2SQL 系统失败在哪里**：看 formal / challenge / diagnostic 的 failure distribution。这里的结论不是“系统变好了”，而是“失败结构看清楚了”。本轮 DeepSeek `deepseek-v4-flash` 快照是 formal `7/10`、challenge `9/16`、diagnostic `19/32`，低于 M13 稳定基线；但 M19 的价值是把 32 条 diagnostic 里的失败拆成了具体方向。

Diagnostic 的主结论可以这样读：

| failure_stage | 数量 | 怎么理解 | 下一步 |
|---|---:|---|---|
| `schema_context` | 6 | 表大多找到了，但传给后续步骤的字段/上下文不够，典型表现是 `missing_columns` | 优先检查 `domain_pack/schema_desc/*`、retrieval 命中文档、局部 SchemaGraph 输出列 |
| `schema_retrieval` | 1 | 需要的表没有召回，例如期望 `products` 但没进上下文 | 调 schema retrieval query / aliases / metric doc |
| `result_match` | 2 | SQL 能跑通，但结果列名、排序或数值和 expected SQL 不一致 | 查 generated SQL、expected SQL、scorer 是否过严 |
| `plan_validation` | 1 | QueryPlan 生成出来了，但自检不通过 | 查 planner / validator 的错误标签和 prompt 约束 |
| `query_plan` | 1 | 自然语言到 QueryPlan 阶段失败，多见 LLM 输出不可解析或理解偏了 | 查 QueryPlan prompt、模型输出、失败 case 是否多步/歧义 |
| `sql_generation` | 1 | plan 有了，但 SQL 生成阶段失败 | 查 SQL prompt 和局部 schema 是否足够 |
| `sql_guard` | 1 | 安全门相关失败，可能是真拦截，也可能是误拦截 | 先人工复核，不能贸然放宽安全策略 |
| `unknown` | 2 | 证据不足或人工复核 case，不该硬贴标签 | 保留 manual_review，补更细 trace 或 case 说明 |

所以这次测试暴露的最大方向不是“LangFuse 写入问题”，而是 **schema 上下文质量**：`schema_context + schema_retrieval = 7`，占 diagnostic 失败的主要部分。第二类是 **pipeline 生成/验证/结果匹配问题**：`result_match + plan_validation + query_plan + sql_generation = 5`。这就是 M19 说的闭环：不是只说“失败了 13 条”，而是告诉你下一轮更该先修 schema 上下文，再看 SQL 结果口径。

还有一个很重要的读数风险：**三类测试虽然是包含关系，但这次不是“同一次运行结果的子集统计”，而是 formal / challenge / diagnostic 三次独立 LLM eval**。所以重复 case 会因为 LLM 非确定性、请求上下文和模型输出波动出现不同结果。

本轮同 `case_id` 在 challenge 和 diagnostic 中出现结果差异的例子有 6 个：

| case_id | challenge | diagnostic | 说明 |
|---|---|---|---|
| `db_core_001` | fail：`result_match` 列名 `gmv` vs `total_gmv` | pass：`result_match_ok` | 同题重跑后 SQL alias / 输出列口径变了 |
| `db_core_002` | fail：`llm_generation_error` | fail：`missing_tables=['products']` | 都失败，但失败阶段从 query/生成类变成 schema retrieval |
| `db_core_004` | fail：渠道排序/行值不一致 | fail：仍是 result mismatch，但错在另一行 | 都失败，但输出顺序或 SQL 结果波动 |
| `db_hard_001` | fail：`llm_generation_error` | fail：`sql_guard_blocked` | 困难题失败形态变了，不能只看总分 |
| `db_multi_002` | fail：`llm_generation_error` | pass | 典型 LLM 重跑波动 |
| `db_multi_004` | pass | fail：`plan_validation_failed` | 典型 LLM 重跑波动 |

所以以后读三类测试时要记住：**同一轮内的总分可以横向参考，但如果要严格比较包含关系，最好只跑一次 superset，再从同一份结果里切 formal / challenge / diagnostic 子集**。否则“challenge 过了但 diagnostic 同题没过”不一定代表测试集定义矛盾，可能只是 LLM 重跑波动。

按你的要求又补跑了一轮 `qwen3.7-max`。`qwen3.8-max` 这次不是模型效果差，而是当前 DashScope 账号/配置直接返回 HTTP 403 `access_denied`，所以没有跑三类 eval；`qwen3.7-max` 最小调用可用，于是用它完整跑了 formal / challenge / diagnostic。

| 模型 / 运行 | formal | challenge | diagnostic | 主要失败结构 |
|---|---:|---:|---:|---|
| DeepSeek `deepseek-v4-flash`（M19 快照） | 7/10 | 9/16 | 19/32 | `schema_context=6`、`schema_retrieval=1`、`result_match=2`、`plan_validation=1`、`sql_guard=1`、`query_plan=1`、`sql_generation=1`、`unknown=2` |
| Qwen `qwen3.7-max`（追加对照） | 8/10 | 12/16 | 22/32 | `schema_context=6`、`schema_retrieval=2`、`result_match=1`、`plan_validation=1`、`unknown=1` |

这轮 qwen3.7-max 的总分更好，尤其是 challenge 从 9/16 到 12/16、diagnostic 从 19/32 到 22/32；从 triage 看，它少了一些 `query_plan / sql_generation / sql_guard` 类失败，说明生成稳定性在这批题上更顺。但它没有解决 M19 暴露的主问题：`schema_context` 仍然是 6，`schema_retrieval` 还从 1 变成 2。换句话说，**换模型能缓解一部分生成失败，但不能替代 schema 上下文修复**。

这里还有一个读数细节：qwen3.7-max 的 challenge 命令行通过率是 `12/16`，但 triage summary 里显示 `failed=5`；diagnostic 命令行通过率是 `22/32`，triage summary 是 `failed=11`。差的 1 条不是算错，而是 `review_required` 的人工复核 case：它不一定按规则分数算失败，但 M19 triage 会把它保留在待处理清单里，避免困难/歧义样本被“通过率”藏起来。

所以这轮对模型选择的结论是：`qwen3.7-max` 值得作为显式候选和后续 A/B 组，但 M19 不直接切默认模型。原因不是保守，而是模型默认会影响长期基线；如果要切，应该单独做一次“默认模型切换”决策，把成本、稳定性、三类 benchmark、失败形态和后续 RAG / Hybrid 影响一起看。

### 怎么用于改进

M19 的改进方法不是“一次性全修”，而是按 failure distribution 排优先级：

1. **先修 `fix_schema_desc=7` 的问题**
   重点看 `schema_context` 和 `schema_retrieval` 的 Top cases，例如 `db_prompt_001 / db_prompt_002 / db_prompt_003 / db_schema_003 / db_simple_002`。这些 case 多数是字段缺失或上下文不完整。下一步可以逐条打开 `.agent_work/temp/m19-diagnostic-report.md`，看 `evidence_step=score:rule:column_recall` 对应的 missing columns，再反查 `domain_pack/schema_desc/*` 和 retrieval metadata。

2. **再修 `fix_pipeline=5` 的问题**
   重点看 `result_match`、`plan_validation`、`query_plan`、`sql_generation`。这里不要先改 scorer，也不要先换模型，而是先看 trace step：失败发生在 QueryPlan，就看 plan prompt / LLM raw response；失败发生在 result_match，就对比 generated SQL 和 expected SQL。比如 `result_match` 可能只是列名 alias 不一致，也可能是真 SQL 口径错，两者修法完全不同。

3. **最后处理 `manual_review=3`**
   `unknown` 和 review_required case 不应该被自动归因。它们更像“诊断题”或“边界题”，需要人工判断：是 case 本身歧义、scorer 太严格、安全策略误拦，还是当前系统确实不支持。

4. **用 A/B failure distribution 检查改动是否真的变好**
   改完后不要只看总分从 19/32 到多少，而要比较失败结构。例如如果 `schema_context` 从 6 降到 2，但 `result_match` 从 2 升到 6，说明你可能让更多表字段进来了，但 SQL 口径更乱了；这不是纯提升。M19 的 `--compare-triage-left/right/report` 就是为了看这种变化。

一句话：M19 不是“自动修复器”，而是把下一轮优化从“凭感觉挑 case”变成 **按失败阶段排队修**。

可复制验证命令：

```powershell
# M19 focused tests：预期 5 passed
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m19_failure_triage.py --basetemp=.agent_work\temp\pytest-m19-check

# 生成带 Failure Triage Summary 的 smoke report：预期 passed=6/6，本地 LangFuse triage scores skipped=24
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --cases eval\cases\smoke.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\m19-smoke-traces.jsonl --report .agent_work\temp\m19-smoke-report.md --triage-json .agent_work\temp\m19-smoke-triage.json
```

**本地启动体验：**本模块没有新增 Web 页面或 API endpoint；它的入口是 eval CLI。用户体验方式是运行 `eval.run_eval` 后打开生成的 Markdown report，看 `Failure Triage Summary` 和 `Case Triage Details`。

## ★ ★ ★ Phase 3B 上半阶段总结：LangFuse 可观测性与评测闭环

（2026-08-02）

**简述**：Phase 3B 上半段给 DataPilot 装上了"观察自己的眼睛"和"失败归因的罗盘"——在 **不动 `/api/query` 响应契约、不替代 JSONL trace 和现有 eval** 的前提下，验证并落地 LangFuse 可观测性与评测闭环：**trace 双写、live lifecycle span、评分分层与 score 回写、一键 smoke、trace → Dataset 工作流手动验证、Failure Triage Summary、A/B failure distribution**（未实现自动 Experiment run）。这个阶段证明了一件事：**"业务 Agent 可被观测、可被评测、可被归因"**，为后续 Schema Retrieval 修复、RAG / Hybrid 和独立 EvalBench 评测项目铺好底座。

### 先用大白话讲

Phase 3B 之前，DataPilot 已经能查数据、能评测，但它只回答了两个问题："答得对不对"（eval）和"刚才那次请求做了什么"（JSONL trace）。它还没有回答第三个问题：**系统跑起来以后，到底发生了什么、质量怎么样、能不能持续观察**。

这里有个容易混的点，先分清**记录层和查看层**：M11 起 JSONL trace 里其实已经把每一步写成 **TraceStep**（记录层不缺数据，M12 对照报告就是程序读 trace 生成的）；但"记录在案"和"看得方便"是两回事——LangFuse 之前，eval 报告只给最终 pass/fail，要看单次请求的中间步骤只能自己打开 JSONL 文件翻 `trace_steps` 字段（查看层缺手段）。LangFuse 做的不是"从这一刻开始记录"，而是**把早已记录的中间过程变成可视化 span 视图**。

你可以把 DataPilot 想象成一家餐厅。Phase 3A 之前做的是：**菜品**（Text2SQL 能力）和**菜谱验收**（eval）。Phase 3B 做的是给餐厅装 **后厨监控和顾客评分系统**：每做一道菜，监控系统记下"什么时候下单、谁洗的菜、谁炒的、炒到一半有没有糊锅"；每上一道菜，评分系统记下"菜名对不对、分量够不够、安全有没有违规、味道好不好（LLM judge）"。监控和评分都不影响做菜本身——**监控系统坏了，后厨照样出餐**。

这个阶段最核心的设计思想可以总结成四个字：**旁路观测**。LangFuse 这个外部观测平台在 Phase 3B 里永远不是主链路：默认关闭、SDK 放在可选依赖里、Cloud 不通时 trace 只标记 `failed` 然后继续写本地 JSONL。项目自己的 `trace_id` 继续当主 ID，LangFuse 用独立的 32 位 hex id，两边靠 JSONL 字段建立映射——就像业务订单号和第三方支付流水号，两个都重要，但不能混成一个。

所以 Phase 3B 的核心价值是：**在不绑架主链路的前提下，验证了"外部观测平台 + 本地评测"能组成一套可用的可观测与评测闭环，并把这条链路的真实边界（哪些能做、哪些留给 EvalBench）摸清楚**。

### 这次做了什么

按阶段主线写，不按模块流水账：

1. **先钉边界，再谈接入（M15）**。先单独验证 Cloud key、SDK 4.14.1、span 写入、score 写入、flush 和查询可见性（trace 约 0.6s 可查）。同时把配置纳入 `Settings`：默认 `LANGFUSE_ENABLED=false`，SDK 放进 `observability` optional extra——**观测系统不可用时，主链路照常跑**。这一步把"能不能安全接入"钉死，后续模块不再边查 SDK 行为边改主链路。

2. **再打通双写与降级（M16）**。把 trace recorder 升级成 **TraceRouter 架构**：业务代码只把 trace 交给 router，router 按顺序调用 `LangFuseBackend -> JSONLBackend`。LangFuse 失败会被捕获、标记 `langfuse_write_status=failed`，JSONL 仍然落盘。M16 的 spans 是 **post-hoc flat spans**：请求结束后把 `trace_steps` 一次性平铺上传，不伪造父子嵌套和真实时间线。

3. **然后验证观测底座（M16B）**。在独立分支上做 **live lifecycle 下沉**：新增 DataPilot 自己的 `TraceContext / SpanHandle` 抽象，pipeline 和 SQL tool 只依赖这个抽象，不直接 import LangFuse。SQL Guard 和 SQL Execution 的 span 通过 `run_sql_tool(trace_context=...)` 在 **tool 内部**记录——因为安全检查和数据库执行的真实边界就在 tool 里，事后补 span 只能猜结果。`langfuse_span_mode=live` 显式标记，避免 live spans 和 post-hoc spans 在 Cloud UI 里重复。用户随后决定 **M17/M18 直接在 M16B 分支上继续**，M16 post-hoc 降级为 fallback 对照。

4. **之后做评分分层与回写（M17）**。把 eval 从一个大函数里的 pass/fail 拆成 **L1/L2/L3 分层 scorer**：L1 看结构和安全、L2 看结果匹配固定事实、L3 用 LLM judge 做语义判断（默认关闭）。`_score_case()` 保留为兼容薄壳，旧 Markdown 报告口径不变。评分结果按 JSONL 里的 `langfuse_trace_id` **写回 LangFuse Score**，不等待 Cloud trace 查询可见。

5. **最后收口（M18）**。新增正式一键 smoke 脚本 `scripts/smoke_phase3b_langfuse.py`：默认模式验证 API / JSONL 主链路（LangFuse 检查 SKIP），`--require-langfuse` 模式把 Cloud 作为硬门禁。真实 Cloud smoke 走代理后全链路 PASS（observations=8）。手动验证了 LangFuse **trace → Dataset** 工作流（5 条 case，DeepSeek `4/5`、Qwen `3/5`），并摸清 Experiment run 的真实边界：**UI run 需要项目 LLM key，Webhook run 需要远程实验服务**，当前不临时实现。

6. **收口后再加固两轮（Phase 3B 复审）**。把"能跑通"加固成"边界更可信"：LangFuse SDK import 失败时降级为本地 trace；score 只回写 `langfuse_write_status=ok` 的 trace；**危险 SQL 预检下沉到 `new_text2sql` pipeline 的统一 `sql_guard` lifecycle**（blocked path 也留下 trace step），且发生在 `get_default_llm_client()` 之前，让安全拦截不依赖 LLM 配置健康；`equals` 不再做全 JSON substring、`result_match` 按列名对齐；Markdown report 输出 scorer 明细和 score 写入结果；Dataset CSV 移出 git 跟踪。

7. **把观测数据变成改进闭环（M19）**。M15-M18 证明了 trace 和 score 能被写入、看见和回放，但还缺"失败后该先修哪"。M19 新增 Failure Triage：把 eval scorer 明细、JSONL trace step 和可选 LangFuse score 结合起来，给每条失败 case 标出 `schema_context / schema_retrieval / query_plan / plan_validation / sql_generation / sql_guard / sql_execution / result_match / scorer_issue / unknown` 等失败阶段，并输出 `fix_schema_desc / fix_pipeline / fix_scorer / manual_review / infra_retry` 这类下一步动作。它不自动修复，也不自动改 case，而是把下一轮优化从"凭感觉挑 case"变成"按失败分布排队修"。



Phase 3B 上半阶段完成的不是一个单独的 LangFuse 接口，而是一套从**运行记录、质量评分到失败归因**的可观测闭环。系统既能保留本地证据，也能借助 LangFuse 查看 trace 和 score；即使 LangFuse 不可用，业务查询和本地评测仍可继续运行。

1. **先确定外部观测平台不能绑架业务主链路。**

   DataPilot 原来已经有 JSONL trace，但缺少方便查看 span、关联评分和管理实验样本的平台。接入 LangFuse 前，项目先验证了 Cloud 鉴权、SDK、trace、score、flush 和查询可见性，并把 LangFuse 设计成**默认关闭的可选能力**。

   项目继续使用自己的 `trace_id`，LangFuse 使用独立的 32 位 ID，两者通过 JSONL 映射。这样无论以后更换平台，`/api/query`、本地 trace 和 eval 都不需要跟着改。

2. **把一次 trace 从单点写入改造成可扩展的双写架构。**

   原来的 `append_trace()` 被保留下来，内部增加 `TraceRouter`，把同一份记录分发给 **LangFuseBackend** 和 **JSONLBackend**。

   LangFuse 写入失败时只记录 `failed`，不会阻止 JSONL 落盘，更不会让 API 请求变成 500。Cloud 只接收问题、状态、表、列、行数和耗时等必要摘要，不上传完整查询结果和文档内容。

3. **把事后补写的 flat span，升级为真实执行过程中的 live lifecycle。**

   第一版 M16 是在请求结束后读取 `trace_steps`，再上传一组扁平 span。这足以验证双写和降级，但不能还原真正的执行时间线。

   M16B 因此增加了 DataPilot 自己的 `TraceContext / SpanHandle` 抽象，让 pipeline 在执行过程中开始和结束 span。SQL Guard 和 SQL Execution 的 span 被放进 `run_sql_tool()` 内部记录，因为安全检查和数据库执行的真实边界就在工具层。

   系统用 `langfuse_span_mode=post_hoc/live` 区分两种模式，防止同一个步骤在 LangFuse 中被重复记录。

4. **把 eval 从一个总结果拆成可解释的分层评分。**

   原来的 eval 主要给出 pass/fail，能看出“错了”，却不容易看出“错在哪一项”。M17 将评分拆成：

   - **L1**：路由、表、列、安全和 SQL 执行状态；
   - **L2**：固定事实、预期结果和输出匹配；
   - **L3**：可选的 `llm:correctness` 语义评分。

   L1/L2 由本地确定性规则负责，成为 Markdown 报告和 LangFuse Score 的**单一事实源**；L3 只有显式配置 judge model 时才启用，失败时降级为 skipped，不阻断整轮 eval。延迟也会记录成 score，但不会因为一次网络抖动改变正确率。

5. **用一键 smoke 验证整条链路确实能工作。**

   M18 新增正式 smoke 脚本，从真实 `/api/query` 出发，依次检查 API、JSONL trace、双 ID 映射、LangFuse Score 和 Cloud trace 可见性。

   默认模式下，LangFuse 未开启属于正常 SKIP；`--require-langfuse` 模式下，Cloud 则成为硬门。真实 Cloud 验证在配置代理后全链路通过，查询到 **8 个 observations**。这也确认了 Windows 裸连可能遇到 `WinError 10013`，属于网络出口问题，不应误判成业务代码失败。

6. **验证了 trace 到 Dataset 的工作流，也明确停在没有证据继续扩张的位置。**

   项目在 LangFuse UI 中建立了包含 5 条样本的 Dataset，并用 DeepSeek 和 Qwen 跑了小规模对照，结果分别为 **4/5** 和 **3/5**。

   这次验证证明了 trace 可以整理成 Dataset，但也发现：如果从中间 span 创建样本，input 和 expected output 可能不是最终用户问题和答案；正式数据集应该从 case 定义或 root trace 生成。

   LangFuse UI 的 Experiment run 还需要项目 LLM key，Webhook 模式则需要远程 runner。DataPilot 没有为了“看起来闭环”临时实现一个不完整的实验服务，而是把正式 Experiment 编排留给后续 EvalBench。

7. **通过代码复审补齐安全和评测边界。**

   阶段收口时又修正了几处容易产生假象的问题：LangFuse SDK 缺失时可以降级；只有成功写入的 trace 才回写 score；危险 SQL 预检被下沉到统一 SQL Guard lifecycle；`equals` 不再搜索整份 JSON；`result_match` 按列名对齐；Markdown 报告展示 scorer 明细和 score 写入结果。

   这些修改的重点不是增加功能数量，而是避免出现“Cloud 显示成功，但本地没有可靠证据”或“评测通过只是字符串碰巧匹配”的情况。

8. **最后把 trace 和 score 转化成可行动的失败归因。**

   M19 新增 Failure Triage，将 scorer 明细、JSONL trace step 和可选 LangFuse score 组合起来，把失败定位到 `schema_retrieval`、`schema_context`、`query_plan`、`plan_validation`、`sql_generation`、`sql_guard`、`sql_execution`、`result_match` 等阶段，并给出 `fix_schema_desc`、`fix_pipeline`、`fix_scorer`、`infra_retry` 或 `manual_review` 等建议。

   Triage 优先相信真实失败 step，其次看响应 `error_type`，最后才看 scorer。证据不足时保留 `unknown`，困难题保留 `manual_review`，不会把启发式判断伪装成绝对根因。

   M19 的真实 LLM 运行也说明：不同轮次的相同 case 会出现波动，因此 formal、challenge 和 diagnostic 的独立运行不能直接当成同一次实验的包含关系。后续严格比较必须使用**同一次 superset run 再切片统计**。

所以，这一阶段最终建立的是：

```
真实执行过程`
→ `本地 JSONL + LangFuse Trace`
→ `分层 Score`
→ `失败归因`
→ `Dataset / 后续实验
```

它让 DataPilot 不只是“能运行”，还开始具备**看得见、测得清、查得出、能继续改进**的工程能力。

> **M24 章节结束时补充**：M19 的 Failure Triage 是启发式排障导航，不是最终真因判定。M22-M24 复核发现，早期 `schema_context / schema_retrieval` 桶中可能混有最终表列、输出投影、SQL 保真或 scorer 合同问题；当前必须结合完整 trace、`output_contract` 和结果 scorer 再定性，不能只看旧桶名就归因 embedding。LangFuse 仍默认关闭，LLM judge 仍只在显式配置时启用。

### 阶段主线图

一条请求从进来到被评分、被观察的完整链路：

`/api/query`
→ `TraceContext / TraceRouter`
→ `JSONL Trace`
→ `LangFuse Trace`
→ `EvalScoreDetail`
→ `LangFuse Score`
→ `FailureTriage`
→ `Dataset`
→ `EvalBench 后续`

**通俗理解**：请求先进业务链路（第 1-2 步），同时把运行记录写给两个地方——本地 JSONL 是"家底"，LangFuse 是"云监控"（第 3-4 步）；eval 跑完把每条评分细节（第 5 步）回写到云监控里的对应 trace（第 6 步）；M19 再把失败样本做阶段归因（第 7 步）；需要做实验对比时，把样本收成 Dataset（第 8 步）；真正的 Experiment run 编排留给 EvalBench（第 9 步）。

### 关键知识点串联

阶段级概念，不只是某个模块的概念：

- **Trace / Span / Score / Dataset / Experiment**：LangFuse 世界里的五个核心对象。Trace 是一次请求的总记录，Span 是其中的一个步骤，Score 是评测结果，Dataset 是可复用的测试样本集，Experiment 是用 Dataset 跑一组对比实验。Phase 3B 把前四个都跑通了，第五个只验证到边界。
- **post-hoc vs live lifecycle**：post-hoc 是"请求结束后补写日志"——简单但不真实；live 是"执行过程中实时记录 span"——更像真实调用链，但要处理 SDK 边界、span 去重和 flush 时机。Phase 3B 先用 post-hoc 跑通闭环，再用 M16B 验证 live 是否值得作为后续底座。
- **记录层 vs 查看层**：TraceStep 写进 JSONL 是"记录"（M11 就有，M12 对照报告就是程序读 trace 生成的），LangFuse span 是"查看"（M16 起才有可视化）。"用 LangFuse 之前看不到中间 span"说的是查看层——**数据一直在，缺的是不翻文件就能看的手段**。读 M11 的记录时不要误以为它和 Phase 3B 矛盾。
- **旁路观测与降级**：观测系统永远不是主链路。默认关闭、可选依赖、失败标记 + 继续写 JSONL，这三条保证了"监控坏了，业务照跑"。
- **双 ID 策略**：DataPilot 自己的 `trace_id` 服务 API / JSONL / eval，LangFuse 用独立 32 位 hex id，JSONL 字段做映射。第三方平台不接管内部契约。
- **L1/L2/L3 评分分层**：能用规则就不用 LLM。L1 结构安全、L2 结果匹配、L3 语义判断（默认关闭，显式传 `--judge-model` 才开）。
- **Failure Triage / failure distribution**：M19 不只告诉你 case 失败了，还把失败归到阶段、给出下一步动作，并支持两个 run 的失败结构对比。它不是自动判案，而是排障导航：证据不足时保留 `unknown / manual_review`，避免把猜测当真因。
- **兼容薄壳**：旧函数名 / 旧报告口径保留，内部换成新实现。像 SpringBoot 旧 endpoint 不变、内部 service 换了实现。

### 阶段设计取舍

- **Cloud 优先，不默认 self-host**：LangFuse Cloud 够验证能力，本地自部署（Docker / ClickHouse / Redis / MinIO）组件重、容易把阶段拖进运维泥潭，留给 EvalBench 阶段做正式部署 spike。
- **旁路观测而不是"接了就绑死"**：这是整个阶段的地基。如果观测平台是强依赖，Cloud 抖动会变成业务故障；旁路化之后，观测能力是加分项而不是生命线。
- **双 ID 不接管**：多维护一个 ID 有映射成本，但保护了 API、响应头、JSONL、eval 四处的内部契约。换观测平台时不需要反向污染历史 trace。
- **post-hoc → live 渐进，不一步到位**：M16 先证明"双写 + 降级 + 映射"可靠，M16B 再验证"真实执行边界埋点"值不值得。如果一上来就做 lifecycle，SDK 边界、去重、flush 这些坑会和新抽象混在一起，不好定位。
- **SQL Guard / SQL Execution span 下沉到 tool 内部**：真实安全边界在 `run_sql_tool()` 里，pipeline 事后补只能猜结果。这是用户确认过的方案，M16B 之后成为主链路的 trace 边界。
- **本地 scorer 单一事实源，而不是 LangFuse 托管 evaluator**：托管 evaluator 会引入 UI 配置、observation target 和调度依赖，容易让本地报告和 Cloud 分数各说各话。M17 先保证同一批 `EvalScoreDetail` 同时服务 Markdown 和 LangFuse。
- **Experiment run 不临时实现 webhook**：UI 真实验证发现 run 需要 LLM key 或 Webhook runner，临时补一个不完整的 runner 会扩大成 EvalBench adapter 的活。边界先记录，正式设计留给 EvalBench。
- **失败归因用确定性证据优先**：M19 没有让 LLM 自由阅读 trace 后判断真因，而是优先使用 trace step、error_type 和 scorer detail。这样结果可复现、成本低，也不会把一个新模型判断层引入到排障基础设施里。
- **风险或边界**：Windows 裸连 LangFuse Cloud 偶发 `WinError 10013`（需要 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`）；Cloud trace 只传最小 payload，完整 rows 和 PII 不上传，也不把 Cloud trace 当长期数据资产。

### 面试怎么讲

先背/改写这一段阶段级叙述：

"我做过一个 Agent 项目的**可观测性与评测闭环阶段**。系统原来只有本地 JSONL trace 和 pass/fail 评测，我把它升级成 trace → score → triage → dataset 的闭环：第一步，先验证外部观测平台 LangFuse 的 Cloud、SDK、score 写入和 flush 都可用，并把配置做成默认关闭的可选依赖；第二步，把 trace 写入重构成 TraceRouter 架构，支持本地 JSONL + LangFuse 双写，LangFuse 失败只标记状态、不影响主链路；第三步，做一个 live lifecycle 分支，把埋点下沉到 pipeline 和 SQL tool 的真实执行边界，用 DataPilot 自己的 TraceContext 抽象隔离 LangFuse SDK；第四步，把 eval 拆成 L1/L2/L3 分层 scorer，规则评分同时服务 Markdown 报告和 LangFuse Score 回写；第五步，新增 Failure Triage，把失败 case 按 `schema_context / query_plan / sql_guard / result_match` 等阶段归因，并支持 A/B failure distribution。整个阶段守住一条底线：**观测系统永远不绑架主链路**——默认关闭、失败降级、双 ID 隔离、最小 payload。同时我也摸清了边界：Experiment run 编排和 LangFuse self-host 留给后续独立的 EvalBench 评测项目。"

1. **[基础追问] 你为什么要专门做一个阶段做可观测性？之前的 JSONL trace 不够用吗？**

   可以答：JSONL trace 够用，但它是"文件"，不是"系统"。先说清楚一点：**中间过程的数据其实一直都有**——M11 起每次请求的每一步（schema_retrieval → chart_decision）就已经以 TraceStep 形式写在 JSONL 里，M12 的对照报告就是程序读这些 trace 生成的。但"记录在案"和"看得方便"是两回事：LangFuse 之前，eval 报告只给最终 pass/fail，要看单次请求的中间步骤只能自己打开 JSONL 翻字段。JSONL 能回答"刚才那次请求发生了什么"，但很难回答"这周请求的质量趋势怎么样""失败集中在哪一步""评测分数和 trace 怎么关联"。Phase 3B 做的事情不是抛弃 JSONL，而是把 LangFuse 作为**旁路增强**：保留 JSONL 主链路，同时把 trace 可视化、score 回写、样本管理这些能力交给专门的观测平台。核心原则是**新增能力，不改契约**——`/api/query` 响应和本地 eval 完全不变。

2. **[基础追问] Trace、Span、Score、Dataset、Experiment 这几个概念在 LangFuse 里是什么关系？**

   可以答：一次请求对应一个 **Trace**，Trace 下面有多个 **Span**（每个 span 是一个步骤，比如 schema retrieval、sql generation、sql guard）；评测跑完后，按 `langfuse_trace_id` 把每个评分项写成 **Score** 挂在 trace 上；需要做实验对比时，把样本收成 **Dataset**（每条 item 包含 input、expected output 和 metadata）；用 Dataset 跑一组对比就叫 **Experiment**。Phase 3B 把前四个都跑通并有验证证据，Experiment 只验证了 UI 边界。

3. **[工程/深挖追问] 为什么保留 DataPilot 自己的 `trace_id`，而不是直接用 `langfuse_trace_id` 当全局 ID？**

   因为 LangFuse 是旁路观测平台，不应该接管 DataPilot 的内部契约。`trace_id` 服务 API、JSONL、本地 eval 和错误排查，是项目自己的主 ID；`langfuse_trace_id` 是第三方平台里的观测 ID。两者靠 JSONL 字段映射。这样即使 LangFuse 关闭、网络失败、未来换平台，DataPilot 的 trace、报告和测试都还能继续工作。这个设计类似业务订单号和第三方支付流水号：可以关联，但不能混用。

4. **[工程/深挖追问] post-hoc flat spans 和 live lifecycle spans 有什么本质区别？你为什么先做前者再做后者？**

   可以答：post-hoc 是请求结束后拿 `TraceRecord` 一次性拆 spans，**没有真实的开始/结束时间**，只有步骤顺序，所以叫 flat spans；live 是在 pipeline 执行过程中真正记录"这步开始、这步结束、这步失败了"，时间线是真实的。先做 post-hoc 是因为它能**最快验证双写、降级和 ID 映射**这些基础设施；live 涉及 SDK 边界、span 去重、flush 时机和错误路径快照，复杂度更高，单独放 M16B 分支验证。最后用 `langfuse_span_mode` 显式区分两种模式，避免同一个步骤在 Cloud UI 出现两次。

5. **[工程/深挖追问] 如果 LangFuse Cloud 完全不可用，你的系统会发生什么？**

   可以答：什么都不会发生——这正是设计的底线。LangFuse 默认关闭（`LANGFUSE_ENABLED=false`），SDK 在 optional extra 里，未启用时根本不会 import；启用后 router 对每个 backend 独立 try/except，LangFuse 失败只把 `langfuse_write_status` 标记为 `failed`，然后继续写 JSONL。M18 的 smoke 专门有一个默认模式：LangFuse 关闭时 API / JSONL 必须 PASS，Cloud 检查显示 SKIP。测试里也覆盖了 fake client 抛异常、缺 key、SDK import 失败这些路径。**观测系统是加分项，不是生命线**。

6. **[工程/深挖追问] 评分为什么要拆 L1/L2/L3？为什么不用 LangFuse 自带的 evaluator？**

   可以答：拆层是因为**成本和质量递减**：L1 看表、列、安全这些结构规则，L2 看结果是否匹配固定事实，都是确定性的、便宜的；L3 的 LLM judge 有费用、延迟和抖动，所以默认关闭、显式开启。不用 LangFuse 托管 evaluator，是因为 DataPilot 已经有 YAML cases、Markdown 报告和一套历史规则评分，托管化会引入 UI 配置和调度依赖，容易让本地报告和 Cloud 分数**两套口径**。M17 让本地 scorer 产出统一的 `EvalScoreDetail`，同时服务 Markdown 和 LangFuse，分数只有一份。

7. **[压力追问] 这个阶段没有让用户多问出一个正确答案，也没有提升模型效果，它是不是偏工程自嗨？**

   可以答：这个质疑有合理的地方——Phase 3B **确实不是模型优化模块**，它不提升通过率。但它解决的是另一类问题：**当系统变复杂以后，你怎么知道它为什么失败、怎么持续改进**。Phase 3A 的教训就是失败归因难：同一道题失败，可能是 schema 没召回、plan 没通过、SQL 生成跑偏，也可能是评测尺子本身错了。Phase 3B 把"失败发生在哪一步"变成可见的（live spans）、把"每个评分项对不对"变成可回写的（score）、把"样本怎么复用"变成可管理的（dataset）。没有这层底座，后续 RAG / Hybrid 多步骤链路一接进来，排障会直接失控。所以我会把它讲成**给后续阶段铺观测地基**，而不是包装成模型效果提升。

8. **[压力追问] LangFuse Cloud 会不会上传业务数据、SQL 结果或敏感信息？**

   Phase 3B 的原则是最小 payload。Cloud 只作为观测旁路，不作为长期数据资产；本地 JSONL 才是主记录。上传到 LangFuse 的内容应该控制在 trace 元信息、步骤摘要、状态、错误类型和评分结果，避免上传完整 rows、PII 和不必要的业务明细。这个取舍是为了证明观测链路可用，同时不把企业数据安全边界交给外部平台。

9. **[压力追问] 怎么证明 LangFuse 关闭、key 缺失、SDK 不可用或网络失败时，本地 eval 仍然可用？**

   我专门把这些当成 Phase 3B 的验收边界。默认配置下 `LANGFUSE_ENABLED=false`，SDK 在 optional extra 里，未启用时不应该影响主链路；启用后 TraceRouter 对每个 backend 独立 try/except，LangFuse 写失败只标记 `langfuse_write_status=failed`，JSONL 仍然落盘。M18 smoke 也分成默认模式和 `--require-langfuse` 模式：默认模式必须证明 API / JSONL / 本地 eval PASS，LangFuse 检查 SKIP；只有 require 模式才把 Cloud 可见性作为硬门。这样观测系统坏了，业务和本地评测仍能跑。

10. **[压力追问] 你们 Experiment 实际上没跑通——UI run 要 LLM key，Webhook 没有实现，这算阶段收口吗？**

   可以答：如果阶段目标定义成"完整自动化 Experiment 平台"，那确实没完成，我会诚实承认。但 Phase 3B 的目标是**验证 LangFuse 是否适合作为 DataPilot 的可观测与评测前置底座**，这个目标完成了：trace 双写、live spans、score 回写、trace visibility、trace → Dataset item 全部有真实 Cloud 验证证据。Experiment 的边界也摸清了：run 需要 LLM key（UI 路径）或远程实验服务（Webhook 路径）。我没有在 M18 临时补一个不完整的 webhook runner，因为那是 EvalBench adapter 的活，临时实现反而会留下半吊子架构。**结论是"DataPilot 侧闭环到 score 和 dataset，run 编排进入 EvalBench 设计"**——这比假装全通更诚实。

### 阶段成果与边界

- 完成了：
  - **Trace 双写与降级**：TraceRouter + JSONL 主链路 + LangFuse 旁路，失败只标记不阻断，全量 pytest 从 M15 的 **90 passed** 涨到 M18 的 **107 passed, 2 skipped**
  - **Live lifecycle 观测底座**：`TraceContext / SpanHandle` 抽象、`langfuse_span_mode` 去重、SQL tool 内部记录 guard / execution spans
  - **评分分层与回写**：`eval/scorers/` L1/L2 规则单一事实源 + 最小 L3 LLM judge（默认关闭），真实 LangFuse score 回写 smoke 通过（baseline 路径 `ok:16`、live 路径 `ok:6`、M18 smoke `ok=1`）
  - **一键 smoke**：`scripts/smoke_phase3b_langfuse.py`，默认模式主链路 PASS + Cloud SKIP，`--require-langfuse` + 代理下 trace mapping / score / visibility 全 PASS
  - **手动 Experiment 工作流验证**：trace → Dataset item 可用，5 条 workflow case 两组模型跑出 DeepSeek `4/5`、Qwen `3/5`，scores 全写回
  - **Failure Triage 改进闭环**：Markdown report 新增 Failure Triage Summary / Case Triage Details，支持 `--triage-json`、LangFuse triage scores 和本地 A/B failure distribution 对比；M19 快照把 diagnostic 失败主簇定位到 `schema_context + schema_retrieval`
  - **两轮复审加固**：SDK 降级、score 只回写 ok trace、危险 SQL 预检下沉 pipeline 统一 guard、equals / result_match 修正、report 加 case_id、Dataset CSV 移出 git
- 没完成 / 刻意不做：
  - **Experiment run 自动化**（Webhook runner / UI run 编排）——留给 EvalBench
  - **LangFuse self-host 部署**——组件重，EvalBench 阶段再做 spike
  - **L3 LLM judge 默认开启**——费用、延迟、抖动，显式配置才启用
  - **完整 EvalBench 平台**（case 管理、多项目 adapter、实验编排、报告生成）——这是独立项目的定位
  - **正式 Dataset 从 root trace / case 定义生成**——本次 Dataset 是临时 UI 素材，CSV 里还有 telemetry 噪音和 public key 需要清洗
  - **Cloud trace 作为长期数据资产**——它只是 Phase 3B 实验记录，不承诺数据保留和迁移

### 下一阶段怎么接

- **M20 起转入 Schema Retrieval / Milvus 修复线**：M19 的 failure distribution 已经指出最大失败簇在 `schema_context / schema_retrieval`，所以后续不急着进入 RAG / Hybrid，而是先修 Milvus collection hygiene、schema docs hash、run 内 vector index 复用和 clean embedding A/B 证据。也就是说，M20 以后是在给未来 RAG / Hybrid 补检索地基。
- **Phase 3 RAG / Hybrid（后续模块）**：等 Schema Retrieval 可信后，再基于 **M16B live lifecycle 底座**继续扩展多步骤链路，复用 `TraceContext / SpanHandle`、score 分层和 M19 failure triage 口径。
- **独立 EvalBench 项目**：吸收 Phase 3B 上半段的踩坑记录，设计 **LangFuse Webhook / SDK 方式的 DatasetRun runner**、**self-host 部署 spike**，并从 root trace / case 定义统一生成清洗过的 Dataset 样本。
- **可复用的阶段级验证命令**：M15-M19 的模块记录里都有完整验证命令；上半阶段收口时的总检查入口包括 M18 smoke、全量 pytest（M18 时为 **107 passed, 2 skipped**；M19 后为 **121 passed, 2 skipped**）和 M19 triage smoke / diagnostic report。

## ★ ★ M20 Milvus collection 修复与 embedding 测试

（2026-08-02）

**简述**：M20 修的是 **Milvus 实验链路可信度**：先保证 schema docs 只被干净、可追溯地写入索引，再谈 embedding 模型效果。

### 先用大白话讲

M19 之后我们发现一个很典型的评测坑：看起来是在比较 **Qwen embedding** 和默认检索，但底层 Milvus collection 其实已经被同一批 schema docs 重复灌了很多次。就像你想比较两位选手跑步，结果赛道上堆了 100 层重复障碍物，最后成绩差异不能说明选手真实能力，只能说明赛道不可信。

M20 做的事就是先把赛道清干净：每次实验用**唯一 collection**，collection 里应该只有当前 193 条 schema docs；报告里写清楚 collection 名、row_count、embedding 模型、维度和 `schema_docs_hash`；eval 一个 run 内复用同一个 Milvus index，不再每个 case 重复插入。与此同时，M20 也把 eval 的标准答案来源讲清楚：当前 `result_match` 仍是 SQLite deterministic oracle，不冒然切到 MySQL。

所以本模块的核心价值是：**让后续检索/embedding A/B 的证据可信，而不是让一次分数变好看。**

### 这次做了什么

M20 主要解决 **Milvus 索引被重复写入，导致 embedding 实验结果不可信**的问题。最终清理了实验链路，并把 embedding、向量库和完整 Text2SQL 的效果拆开验证。

1. **先确认旧实验为什么不可信**

   M19 复测时发现，当前只有 193 条 Schema 文档，但固定 Milvus collection 中却有约 1.9 万行数据。原因是每次评测都会重复插入同一批向量。

   在这种情况下，旧实验分数无法准确反映 embedding 效果，因此不能继续拿来比较模型。

2. **给 Milvus collection 增加复用护栏**

   `MilvusVectorIndex` 不再每次启动都直接插入数据，而是先检查 collection 的**行数和向量维度**：

   - 数据一致就直接复用；
   - 行数或维度不一致就拒绝运行；
   - 实验需要重建时，使用新的 collection 或显式 reset。

   这样避免旧数据污染后续实验。

3. **让一次评测只构建一次向量索引**

   以前 32 条 diagnostic case 可能反复创建和写入索引。现在 eval 启动时预建一个 shared vector index，再由整轮请求共同使用。

   报告也新增了 collection、row count、Schema 文档 hash、向量维度和 oracle backend 等信息，让每次实验都能确认自己使用了哪一版数据。

4. **重新运行干净的端到端评测**

   clean collection smoke 确认最终只有 `193` 行。

   在干净链路下：

   - DeepSeek + Qwen embedding：`17/32`
   - Qwen `qwen3.7-max` + Qwen embedding：`21/32`

   进一步查看失败结构后发现，Qwen 的优势主要来自 QueryPlan 和 plan validation 失败减少，不能直接算作 embedding 的贡献。

5. **把 embedding 单独拿出来测试**

   为了避免 LLM 规划和 SQL 生成干扰判断，又新增了 retrieval-only benchmark，只检查 Schema 表、字段、指标和关系能否被召回。

   结果显示：

   - deterministic vector recall：`0.787`
   - Qwen embedding vector recall：`0.929`
   - 两者最终 merged recall：都是 `0.738`

   这说明 **Qwen embedding 本身有更强的语义召回能力，但现有融合排序没有把这部分优势转化成最终上下文收益**。因此没有切换默认 embedding，而是把后续重点转向 fusion 和 rerank。

### 补课：Milvus + embedding 链路原理

M20 一直在用"embedding 模型" "Milvus collection" "向量检索"这些词。如果对这些概念只有模糊印象，这里补一课，把整条链路从"一段文字"到"生成 SQL"串起来讲清楚。

**第一步：embedding —— 把文字翻译成"坐标"。**

电脑看不懂"退款率""GMV"这些词的含义，但它擅长算数。embedding 模型（比如 Qwen embedding）就是个翻译官：把一段文字翻译成一串数字（叫**向量**），相当于在 N 维空间里给这句话一个坐标点——向量有几个数字就是几维，比如项目默认本地路径是 128 维，真实 embedding 模型通常是几百上千维。

这个翻译有个关键性质：**语义相近的文本，坐标距离就近**。"退款"和"退货"意思接近，坐标就挨得近；"退款"和"发货"就离得远。于是"比较两段文字像不像"就变成了"算两个坐标点的余弦相似度"，一个纯数学问题，模型能力再强也是靠这个坐标决定检索结果。

★ 项目里还有个**默认本地路径**（`deterministic` embedding）：它不做真神经网络，只是按 token 和中文 bigram 拼出一个可重复的向量。虽然"翻译质量"不如真实模型，但完全离线、可复现，所以 pytest 和本地诊断都走它；M20/M21 实验的 Qwen embedding 走的是 DashScope 在线 API。

**第二步：向量检索 —— 找坐标最近的 top-k 条。**

有了"文字 → 坐标"的能力，检索就从"看字面"升级成"看语义"。用户问"哪个渠道卖得最好"，先把问题翻译成查询向量，再和每条 schema 文档的向量算**相似度**，按分数从高到低取**前 k 条（top_k）**。这解决了关键词匹配的硬伤：关键词只有"字面包含"才命中，换个说法就漏（比如问"成交额"匹配不到"GMV"）；向量检索能跨说法命中语义相同的文档。

**第三步：Milvus —— 专门存"坐标"的数据库。**

那 193 条 schema 文档的向量存在 Milvus。可以把它类比成一张特殊的 MySQL 表（collection）：

| MySQL 表       | Milvus collection            |
| -------------- | ---------------------------- |
| 一行是一条记录 | 一行是一个文档向量           |
| 主键           | doc_id（VARCHAR 主键）       |
| 字段值         | vector（FLOAT_VECTOR，N 维） |

查询时执行一次 `search(collection, query_vector, limit=top_k)`，Milvus 用 COSINE 索引（AUTOINDEX）快速返回"离查询向量最近的 k 行"。为什么不用 Python 手动全量算一遍余弦？数据量一大就慢；Milvus 内部用 ANN（近似最近邻）索引，"先粗筛、再精排"把速度提上去，代价只是一点点精度。这也解释了 M20 为什么死磕维度一致性：向量长度不同根本没法算距离，所以 collection 的维度必须和当前 embedding 模型严格对齐。

**第四步：整条链路串起来，全流程分两段:**

1. **灌库**（实验/启动时做一次）

   domain schema（表 / 字段 / 指标 / 关系）

     → 组装成 193 条 schema docs（document_builder）

     → embedding 模型逐条**翻译成向量**

     → insert 进 Milvus collection + flush（此时才有数据可搜）

     → 顺手算 schema_docs_hash 打版本指纹

2. **召回**（每次提问时做）

   例如用户问题"哪个渠道卖得最好"

     → 用同一个 embedding 模型翻译成**查询向量**

     → Milvus search 召回 top-k 条最相关的 schema docs（**语义路**）

     → keyword 关键词路也同步召回一份（**字面路**）

     → **两路按 weighted 融合排序**，取最终 top-k

     → 拼进 LLM prompt → LLM 生成 SQL

为什么要"先检索再生成"，而不是把所有 schema docs 全塞给 LLM？193 条全塞进去 token 太长、噪声太大还费钱；挑最相关的 k 条，相当于给 LLM"按需翻书"，只递给它当前问题相关的几页。

**这和 M20 修的东西有什么关系？**

一句话：**这条链路里，Milvus collection 是"坐标仓库"，仓库脏了，召回就乱。** M20 发现的污染，就是同一批 193 条文档被反复 insert，仓库里攒了约 1.9 万行重复数据——查询时一堆重复坐标干扰相似度排序，embedding A/B 的分数就不可信了。所以 M20 给仓库装护栏：检查 row_count 是不是 193、维度对不对，脏了直接报错，改用唯一 collection 重建；再靠 `schema_docs_hash` 让每份报告都能追溯"这次搜的是哪版坐标"。仓库干净了，后面 M21 的 weighted / RRF 融合实验才有说服力。

> ⚠️ 注（M22 后更新）：文中"193 条"是 M20 时的 schema docs 数量。M22 新增 `coupon_order_count` 指标后，schema docs 变为 **194 条**；后续检索 / 融合实验都基于新 corpus，分数与 M21 的 `21/32` 不再直接可比。

### 新概念

- **Index Hygiene**：索引卫生。意思是向量库里的数据版本、数量、embedding 模型和维度都要可追溯。如果 collection 里混进旧文档、重复文档或不同维度的向量，检索结果就像 MySQL 表里有重复脏数据一样，后面的模型再强也会被误导。
- **schema_docs_hash**：Schema 文档指纹。M20 用 `doc_id + keyword_text + vector_text` 算一个 hash，类似后端里给配置文件或 migration 打版本号。以后看到报告里的 hash，就知道这次向量索引用的是哪一版 schema docs。
- **run-scoped vector index**：一次 eval run 内共享的向量索引。以前每个 case 都重新建 Milvus index，相当于每次请求都重新建表并插入全量数据；M20 改成 run 开始时建一次，后面每条 case 只 search。
- **oracle backend**：评测标准答案的执行来源。当前 `result_match` 的 expected SQL 是在 SQLite seed 上执行，不是直接查 MySQL。M20 先把这个事实写进报告，避免读报告的人误以为它一定代表当前 MySQL 真相。

### 代码阅读路线

1. **Schema 文档版本**：`engine/schema_retrieval/document_builder.py`
   先看 `build_schema_documents()`，它把字段、指标、关系整理成 193 条可检索文档；再看 `schema_documents_hash()`，它给这批文档打版本指纹。重点理解：hash 不参与召回，只服务实验复现和报告追溯。

2. **Milvus 护栏**：`engine/schema_retrieval/vector_index.py`
   主角是 `MilvusVectorIndex.__init__()`。读的时候按顺序看：连接 Milvus，检查 collection 是否存在，检查 row_count 和 vector dimension，决定是插入、复用还是拒绝。这里的关键不是“怎么调 Milvus API”，而是 **不允许污染 collection 静默进入实验**。

3. **run 内复用入口**：`engine/schema_retrieval/retriever.py`
   看 `build_configured_schema_vector_index()`，它一次性构建 documents、vector index 和 hash，交给 eval runner 复用。`retrieve_schema()` 仍然按每个问题计算 keyword hits 和 merged hits，只是 vector search 复用同一个 index。

4. **API / Pipeline 传递**：`app/api/query.py` 和 `engine/nl2sql/pipeline.py`
   API 层从 `request.app.state.schema_vector_index` 取共享索引，传给 `run_text2sql_pipeline()`；pipeline 再传给 `retrieve_schema()`。这条链路很轻，只是多传一个可选对象，不改变 `/api/query` 的响应契约。

5. **Eval 报告与审计**：`eval/run_eval.py`
   看 `_build_eval_schema_vector_index()` 和 `write_report()`。前者只在 `new_text2sql + milvus` 时预建 index，后者把 runtime metadata 写进 Markdown。这样报告不只告诉你过了几条，还告诉你这次用的是哪一个 collection 和哪一个 oracle。

6. **验证脚本**：`scripts/audit_m20_eval_ground_truth.py` 和 `scripts/smoke_m20_milvus_index.py`
   audit 脚本用当前 MySQL 执行 expected SQL，但不改变 scorer；smoke 脚本创建唯一 Milvus collection，检查 `row_count == 193`。这两个脚本是 M20 的证据来源。

核心链路：

`eval.run_eval`
→ `build_configured_schema_vector_index`
→ `MilvusVectorIndex`
→ `app.state.schema_vector_index`
→ `/api/query`
→ `run_text2sql_pipeline`
→ `retrieve_schema`
→ `Eval Runtime Metadata`

### 设计要点

- **唯一 collection 优先**：M20 选了每次实验唯一 collection，而不是固定 collection 反复 reset。这样最隔离、最好复现，也不容易误删别的实验数据。
- **拒绝污染而不是自动猜修复**：如果已有 collection 行数或维度不匹配，代码直接报错。这里没有临时 upsert，因为 upsert 是更接近长期服务形态的方案，需要单独验证 Milvus API 一致性。
- **不改 benchmark 口径**：MySQL audit 证明 expected SQL 当前可执行，但 `result_match` 仍保留 SQLite oracle。这样避免 M20 同时改变索引和评分标准，导致结果无法解释。

### 面试怎么讲

“我在做 Text2SQL 的 schema retrieval A/B 时发现一个评测基础设施问题：Milvus collection 被**重复灌入**，同一批 193 条 schema docs 累积到上万行，导致 embedding A/B 的**检索结果不可信**。我没有直接换模型或改 prompt，而是先做 index hygiene：每次实验使用**唯一 collection**，Milvus adapter 检查 row_count 和向量维度，不匹配就拒绝复用；eval runner 在一个 run 内预建并复用同一个 **vector index**，避免每个 case 重新 insert；报告里写出 schema_docs_hash、collection、row_count 和 oracle backend。最后 clean collection smoke 证明 row_count 回到 193，并用 clean Milvus 重新跑 diagnostic。结果没有提分，但这个结论更可信，也说明不应该自动切默认 embedding。”

“我没有直接根据 Text2SQL 总分判断 embedding 好坏，而是加了一个 retrieval-only benchmark，把检索从生成链路里拆出来。这个实验发现 Qwen embedding 的向量召回明显更好，但最终 merged recall 没变，因此下一步优化方向应该是 fusion / rerank，而不是盲目继续换 embedding 或把 Milvus 切默认。

1. **[基础追问] 为什么 M20 没有提分也算完成？**

   因为 M20 的目标不是优化 Text2SQL 正确率，而是修复评测和索引可信度。污染 collection 下的分数无论高低都不能直接解释 embedding 好坏；clean collection 后即使分数下降，也说明我们拿到了更干净的证据。工程里有时先修仪表盘和数据地基，比直接刷指标更重要。

2. **[工程/深挖追问] 为什么不用 upsert 直接覆盖旧 doc_id？**

   upsert 更像长期在线服务方案，但要确认 Milvus 当前版本对主键、delete/upsert、一致性和索引刷新行为的具体语义。M20 是实验链路卫生修复，优先选唯一 collection，隔离性更强、风险更小。后续如果 Milvus 要成为正式服务路径，再单独实现 upsert / delete-by-doc-id。

3. **[压力追问] 你这次 clean run 只有 17/32，比污染链路还低，那是不是说明修坏了？**

   这个质疑合理，但要先区分目标。M20 改的是索引生命周期和报告可追溯，不是 prompt 或 schema doc 内容；clean run 的 row_count 是 193，说明索引污染被清掉了。分数低不能证明代码修坏了，它更可能说明之前污染链路的结果本来就不可解释，或者 Qwen embedding 对当前 schema doc 粒度没有稳定收益。后续要提升能力，应继续看 schema_context、query_plan 和 result_match 的失败结构，而不是回到污染 collection。

### 验证与下一步

- 验证：focused tests `14 passed`；相关回归 `27 passed`；全量 pytest `127 passed`；Milvus smoke `row_count=193`；DeepSeek + clean Milvus + Qwen embedding diagnostic `17/32`；Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic `21/32`（时间戳命名 collection，`row_count=193`、run_scoped）。
- Warning：只有既有 Starlette/httpx warning 和 Windows LF/CRLF 提示，不影响 M20。
- 下一步：M20 待 `accept-module`；之后进入 Phase 3 RAG / Hybrid 前置规划，或单独确认是否调整 `result_match` oracle / eval case 口径。

可复制验证命令：

```powershell
# M20 focused tests：预期 14 passed
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m20_schema_index_hygiene.py tests\test_phase3a_schema_retrieval.py -q --basetemp=.agent_work\temp\pytest-m20-focused

# Milvus clean collection smoke：预期 PASS，final_row_count=193
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.smoke_m20_milvus_index --output .agent_work\temp\m20-milvus-index-smoke.md
```

## ★ M21 weighted VS RRF / 本地 vs embedding

（2026-08-03）

**简述**：M21 验证了“检索召回更高”不等于“Text2SQL 更准”：RRF 把更多 relation / metric 文档放进上下文，却在同配置真实 diagnostic 上从 `21/32` 降到 `18/32`，因此保持默认 weighted，不为漂亮的离线指标切策略。

### 先用大白话讲

M20 证明 Qwen embedding 像一支更灵敏的雷达，能看到更多相关的 schema 文档；但旧的合并方式没有把信号送到驾驶舱。M21 试了 **RRF（Reciprocal Rank Fusion）**：不比较两台雷达分数谁大，而是按各自的名次投票。它在 retrieval-only 测试上确实把 relation recall 从 `0.633` 拉到 `0.967`，但真正让 LLM 写 SQL 时，更多上下文也会改变 QueryPlan 的选择，反而新增了 plan validation 失败。

所以本模块的核心价值是：**把“检索指标变好”与“端到端能力变好”分开验证，并用否定实验保护默认基线。**

### 这次做了什么

M21 主要研究 **Qwen embedding 已经召回了更好的 Schema 信息，为什么最终 Text2SQL 仍没有明显提升**。为此新增 RRF 融合，并通过离线召回和端到端评测分别验证效果。

1. **给 Schema Retrieval 增加 RRF 融合**

   原来的 weighted 策略直接合并关键词分数和向量相似度，但两种分数的范围并不完全一致。

   M21 新增了显式 `rrf` 策略，只根据每条结果在关键词路和向量路中的排名进行融合。默认仍保持 `weighted`，只有实验时才显式开启 RRF。

   CLI、请求参数、Trace 和 Eval 报告都会记录当前 fusion strategy，保证实验可以复现。

2. **先看 RRF 能不能改善离线召回**

   在 retrieval-only benchmark 中：

   - deterministic merged recall：`0.738 → 0.802`
   - Milvus + Qwen embedding merged recall：`0.738 → 0.929`
   - metric recall：`0.600 → 0.900`
   - relation recall：`0.633 → 0.967`

   这说明 RRF 确实能把 Qwen embedding 已经召回的信息排到更合适的位置。

3. **再检查离线提升能否转化成端到端收益**

   固定 Qwen `qwen3.7-plus`、同一 clean Milvus collection、同一 embedding、同一批 case 和同一 oracle，只改变 fusion：

   - weighted：`21/32`
   - RRF：`20/32`

   RRF 虽然减少了一条 Schema Context 失败，却增加了 QueryPlan 和 Result Match 失败。因此，**离线召回提高并没有稳定转化成最终 SQL 能力**，默认策略继续使用 weighted。

4. **重新检查“Schema Context 失败”的真实含义**

   逐 case 查看 retrieval、SchemaGraph、QueryPlan 和最终 SQL 后发现，不少旧的 `schema_context` 失败并不是目标表没有被召回，而是 SQL 最终漏用了表、字段或输出列。

   因此 triage 新增了 `output_table_contract` 和 `output_column_contract` 等细分类，避免把 SQL 生成问题误判成 embedding 问题。

5. **直接对比本地检索和 Qwen embedding**

   固定 Qwen `qwen3.7-plus`、weighted、同一批 32 条 diagnostic，只改变 Schema Retrieval：

   - 本地 deterministic：`21/32`
   - clean Milvus + Qwen embedding：`21/32`

   两组总分和主要失败分布基本一致。这次实验没有证明 embedding 能带来端到端提分，但明确了后续方向：**先处理输出合同和 QueryPlan→SQL 稳定性，不再继续盲目调整 embedding 与 fusion 参数。**

### 补课：fusion 原理

接 M20 补课里的那张"召回"流程图：每次提问，keyword 路和 vector 路**各排出自己的一份候选名单**。fusion（融合）回答一个问题——**这两份名单怎么合并成最终的一份 top-k**，决定到底把哪几条 schema 文档塞给 LLM。

**问题：两路分数不可比。**

keyword 分是**字面命中计数**：问题切词后逐词去文档里找，命中一个加 0.2~2 分（词越长越高），表名 / 列名 / 指标名精确命中再各 +2，分数 0~几十；vector 分是**余弦相似度**：问题和文档各被翻译成坐标，算两个坐标的夹角余弦 `cos = (A·B) / (|A| × |B|)`，只关心方向一不一致，范围固定 -1~1（通常 0 ~ 1）。一个是"数量"（出现几个词），一个是"比例"（方向多像），量纲完全不同，直接相加不公平——就像把考试成绩（0~100）和体温（36~37）加起来。

**策略一：weighted —— 比总分（默认）。**

keyword 分 × 1.2 + vector 分，按总和排序。思路是"相信两路分数的绝对值，加起来比"。1.2 是给字面命中一点倾斜（更信任精确匹配）。这是 M9 以来的老行为，M21 保留它当默认基线。

**策略二：RRF —— 比名次（实验）。**

完全不看分数大小，只看**名次**：某条文档在名单里排第 r 名，就投 `1/(60+r)` 票。分母加常数 60 是为了把票数压在一个平滑的小范围，避免第一名垄断投票。

|          | weighted                 | RRF                                    |
| -------- | ------------------------ | -------------------------------------- |
| 比什么   | 两路分数的**绝对值相加** | 两路名次**各投一票**                   |
| 最大优点 | 沿用旧行为，稳定可解释   | 绕开"分数不可比"的难题                 |
| 典型后果 | 某一路分数特别高也能进   | 两路都命中的文档天然靠前，带进更多文档 |

RRF 的隐藏副作用：因为"两路都上榜"的文档能拿两份票，它更容易把 relation / metric 等不同类型的文档带进 top-k——这既是它离线 recall 大胜的原因，也是端到端翻车的伏笔（见下）。

**结果：离线大胜，端到端翻车。**

- 离线 retrieval-only：merged recall `0.738 → 0.929`，relation recall `0.633 → 0.967`，全面碾压；
- 端到端同配置 diagnostic：`21/32 → 18/32`（同模型复测 `20/32`），反而下降，新增失败集中在 plan_validation。

**为什么"召回变好"却没换来"端到端变好"？**

recall 只问"该召回的召回了没"，RRF 把更多文档塞进上下文，这个指标自然好看；但**上下文更全 ≠ 对 LLM 更好**——prompt 变长、文档变多，LLM 的 QueryPlan 选择会被改变，反而更容易选错关系路径，卡在 plan validation。就像地图信息更全了，司机反而看花眼选错路。

所以 M21 的核心教训是：**离线检索指标和端到端能力是两层东西，必须分别验证**；不能因为离线分数漂亮就切默认策略。

> ★ 安全底线：RRF 排序只允许用"问题 + 候选文档的分数/名次"，**绝不允许**用 benchmark 的 expected 表/字段标签参与排序——否则就像考试时把答案塞给判卷人，分数虚高，真实用户请求里根本没有这些信息（标签泄漏）。

**结论。**

RRF 被记录为**否定实验**：保持默认 weighted，不改 top_k、schema docs 或评测口径。fusion 只是排序层，真正瓶颈在 schema_context / 输出契约，交给 M22 处理。

> ⚠️ 注（M22 后更新）：M22 确实按新口径处理了这块——拆出 Context / Output / Result / Manual 契约评分，默认 diagnostic `25/32`（新 case + scorer + 194-doc），是"新口径快照"而非对 `21/32` 的提分；默认 **weighted 未切换**，本节结论仍有效。M23 若再研究 RRF / rerank，需在 194-doc 新基线上重做单变量 A/B，不能复用 M21 的总分结论。

### 新概念

- **RRF**：一种 rank-based fusion。它像两份“推荐名单”按名次累积投票，避免 keyword 分数和 vector 相似度的数值尺度不同，直接相加不公平。
- **标签泄漏**：把评测集的 expected 表、字段等正确答案交给线上排序逻辑。这样分数会虚高，真实用户请求却没有这些信息；M21 明确禁止这种做法。
- **否定实验**：结果没有被采用也不是白做。M21 用同配置 A/B 证明 RRF 目前不能稳定改善 Text2SQL，这比把一次离线高分误切为默认更有工程价值。

### 代码阅读路线

1. **融合核心**：`engine/schema_retrieval/retriever.py`
   从 `_merge_hits()` 看 weighted 如何保持旧行为、RRF 如何只按 rank 计分；再看 `retrieve_schema()` 的显式参数，理解默认请求为何不会变化。
2. **实验入口**：`eval/run_schema_retrieval_benchmark.py` 与 `eval/run_eval.py`
   前者只测 schema graph 召回，后者通过 API 跑真实 Text2SQL；两者都把 fusion strategy 和 schema docs metadata 写入报告，保证 A/B 可追溯。
3. **请求与 trace 传递**：`app/schemas/agent.py`、`app/api/query.py`、`engine/nl2sql/pipeline.py`
   `schema_fusion_strategy` 从显式请求传到 retrieval，并进入 trace metadata；它是实验开关，不改变响应体契约。

### 设计要点

- **默认不动**：`weighted` 是已有稳定基线，RRF 必须显式选择；避免一次实验影响所有 API / eval。
- **先离线、后端到端**：retrieval-only 先证明候选值得继续看，再用同配置 diagnostic 检查是否把失败迁移到别的 pipeline 阶段。
- **当前边界**：不靠增大 top_k、bundle docs 或 reranker 掩盖问题；这些会改变上下文结构或长期路线，需要单独决定。

### 面试怎么讲

“我做过一次 schema retrieval fusion 实验。Qwen embedding 的 vector recall 明显高，但 merged recall 没提升，所以我加了一个显式 RRF 对照，并严格避免用 benchmark 的 expected 标签参与排序。RRF 在 retrieval-only 上把 Milvus + Qwen 的 merged recall 从 0.738 提到 0.929，relation recall 到 0.967；但同配置的 32 条真实 Text2SQL diagnostic 从 21/32 降到 18/32，plan validation 失败增加。我的结论不是强行把 RRF 切默认，而是保留 weighted、记录否定实验，并把下一步定位到 context assembly 和 QueryPlan 的耦合。”

1. **[压力追问] 你离线 recall 提升这么多却没有收益，是不是 benchmark 没意义？**

   benchmark 仍有意义：它证明向量信号与 fusion 排序本身确实发生了变化。但它不能替代端到端评测，因为 LLM 还会受 prompt 长度、文档顺序和 QueryPlan 约束影响。正确做法是两层都保留：用 retrieval-only 定位检索问题，用 diagnostic 检查系统结果，不能拿其中一层代替另一层。

### 验证与下一步

- 验证：focused `16 passed`、related `22 passed`、全量 `133 passed`；Milvus collection row_count `193`；weighted/RRF diagnostic `21/32 → 18/32`。既有 Starlette/httpx deprecation warning 不影响模块。
- 下一步：先逐 case 分析 RRF 改变的 context 与 QueryPlan；如需 doc_type weighting、bundle docs、context budget、reranker 或默认策略切换，先单独做长期决策。

**本地启动体验：**本模块没有独立页面；可运行 `python -m eval.run_schema_retrieval_benchmark --top-k 12 --fusion-strategy weighted`，再把策略改为 `rrf` 对比 `.agent_work/temp` 中的报告。

## ★ ★ M22 评测契约与 QueryPlan 输出稳定性

（2026-08-04）

**简述**：M22 先把“Agent 做错了”和“评测题判错了”分开，再用 QueryPlan 合同防止排序等已规划要求在 SQL 生成时悄悄丢失。

### 先用大白话讲

以前系统有一种“冤案”。

我们想检查的是：“模型写 SQL 前，有没有拿到正确的表和字段？”
但旧评测看的却是：“最后返回的结果里，有没有出现这些字段？”

这就像检查学生有没有看懂题目，老师却只盯着最后答题卡上写了什么。学生做题时可能确实查过资料、用了中间变量，但最终答案本来就不需要把所有过程写出来。于是，系统明明拿到了正确的 Schema，却可能被误判成“检索没召回”。

M22 做的第一件事，就是把这几件事拆开看：

- Context：模型写 SQL 前，实际拿到了哪些表和字段；
- Output：最终 SQL 返回了哪些列；
- Result：返回的数据值、排序和条数对不对；
- Manual：太复杂、暂时不能稳定自动判分的题，明确交给人工复核。

同时，系统遇到“查供应商”“知识库文档带来多少订单金额”“先查两个指标再比较”这类当前能力做不了的问题，不再硬让模型猜一个 SQL，也不再把网络报错伪装成业务结论，而是诚实地说明：当前为什么做不了。

一句话：M22 不是单纯让分数变高，而是先把“模型真做错了”和“尺子量错了”分开。

### 这次做了什么

M22 主要解决 **评测失败归因混乱、业务口径不一致，以及 QueryPlan 中的信息在生成 SQL 时丢失**的问题。最终把 Context、输出、结果和人工诊断拆开评分，并补上结构化拒绝与初步 SQL 保真检查。

1. **先把题目、业务指标和参考 SQL 放在一起核对**

   检查后发现，一些题目虽然能运行，但业务含义并不完全一致：

   - 商品退款率没有准确处理一单多商品；
   - 优惠券订单数和优惠券使用率被混为一个指标；
   - 一级类目有时绕过正式类目树；
   - 历史价格查询没有正确处理价格生效区间；
   - QueryPlan 要求的排序或 LIMIT 可能在生成 SQL 时丢失。

   这些问题会让模型即使理解正确，也可能被错误参考答案或评分规则判错。

2. **统一业务口径和参考答案**

   商品退款率改为按订单明细归因；一级类目统一走正式类目树；优惠券使用订单数增加独立指标定义。

   同时重新检查相关 reference SQL，确保题目、指标说明和标准答案表达的是同一个业务规则。

3. **把不同层次的失败拆开评分**

   评测不再用最终 SQL 的输出结果反推检索是否成功，而是分成：

   - **Context**：目标表和字段有没有进入 SchemaGraph；
   - **Output**：最终 SQL 是否使用了要求的表和列；
   - **Result**：执行结果是否符合 reference SQL；
   - **Manual**：当前无法稳定自动判断的复杂语义题。

   这样可以分清问题到底出在检索、计划、SQL 生成还是结果语义。

4. **增加结构化拒绝**

   对当前数据模型无法回答的问题，例如缺少供应商字段、知识库无法归因订单，或者需要多步查询但 pipeline 暂不支持，系统会返回明确的拒绝原因，而不是强行编造 SQL。

5. **增加 QueryPlan→SQL 初步合同**

   如果 QueryPlan 已经声明 `ORDER BY` 或 `LIMIT`，生成 SQL 不能静默丢弃。

   合同失败时，Trace 会保存计划内容、候选 SQL和实际观察结果，方便区分真正的信息丢失与检查器误判。这也为 M24 的 AST 语义保真合同提供了直接问题证据。

6. **用重复实验重新判断默认路线**

   | 组   | 配置                                                         |  首轮 | 第2次 | 第3次 | 平均通过率 |
   | ---- | ------------------------------------------------------------ | ----: | ----: | ----: | ---------- |
   | C0   | `deepseek-v4-flash` + Milvus + `qwen3.7-text-embedding` + weighted | 24/32 | 24/32 | 25/32 | 76.0%      |
   | C1   | `qwen3.7-plus` + inmemory/deterministic + weighted           | 27/32 | 28/32 | 28/32 | 86.5%      |
   | C2   | `qwen3.7-plus` + Milvus + `qwen3.7-text-embedding` + weighted | 25/32 | 27/32 | 25/32 | 80.2%      |
   | C3   | `qwen3.7-plus` + Milvus + `qwen3.7-text-embedding` + RRF     | 24/32 | 26/32 | 27/32 | 80.2%      |
   |      | `qwen3.8-max` + inmemory/deterministic + weighted            | 22/32 |       |       | 68.8%      |
   |      | `qwen3.7-max` + inmemory/deterministic + weighted            | 26/32 |       |       | 81.3%      |

   M22 不是单纯提高分数，而是让后续失败能够被正确归因，并暴露出下一步最需要解决的 **SQL 合同误拦和 QueryPlan→SQL 信息保真问题**。

### 新概念

- **Contract（契约）**：像 Java DTO/接口约定，先明确“这一层必须交付什么证据”。Context Contract 看内部 SchemaGraph，Output Contract 看 SELECT 返回列，Result Contract 看结果值和顺序，不能混用。
- **Semantic rejection（语义拒绝）**：不是权限安全拦截，也不是模型超时；它表示“当前产品能力没有可靠的业务关系或字段支撑”，并且把原因写进 trace。

### 代码阅读路线

1. **评测证据分流**：`eval/scorers/rule_scorers.py` 与 `eval/run_eval.py`。先看 trace 如何只作为 scorer 私有证据，再看专属 contract 为何优先于最终列检查。
2. **能力边界与 SQL 合同**：`engine/nl2sql/semantic_validation.py`、`engine/nl2sql/pipeline.py`、`engine/nl2sql/generator.py`。理解语义拒绝、SQL Guard、QueryPlan contract 三者各守哪一道门。
3. **业务事实源**：`domain_pack/metrics.yaml` 与 `eval/cases/`。对照商品退款率、优惠券订单数、类目树的 case 改动，理解“题面—指标—reference SQL”必须说同一种业务语言。

### 设计要点

- **先改尺子再量分数**：M22 不把口径校正包装成模型能力提升。
- **窄合同而非泛化 SQL 解析**：只验证计划中已经声明的排序/limit，不用正则替代 SQL AST 或重写合法 SQL。
- **M22 实验期间默认策略不动**：实验固定使用声明的模型、检索链路、weighted、Milvus 选择与 seed；M22 收口后，用户另行确认将默认主模型切换为 Qwen `qwen3.7-plus`。

### 面试怎么讲

“我在做 Text2SQL 评测时发现，低分不一定全是模型或检索的问题：有些 case 把内部检索上下文、SQL 输出列和最终结果混在一起评分，导致检索明明正确，仍被判失败。

所以我先做了一轮评测契约治理，把评测拆成 Context、Output、Result 和 Manual 四层：Context 直接读取同一次请求 trace 里的 SchemaGraph，Output 检查 SQL 返回列，Result 用确定性 SQL 对照结果，复杂语义题则明确进入人工复核。

同时我统一了退款率、优惠券订单数和一级类目等业务口径，并补了两类工程护栏：一类是 semantic rejection，遇到当前 Schema 根本不支持的需求时结构化拒绝；另一类是 QueryPlan 到 SQL 的合同检查，防止计划里已经声明的排序或 limit 在 SQL 生成时丢失。

最终我没有把口径调整包装成模型提分，而是把它记录为新的评测合同。这样后续无论优化 retrieval、prompt 还是模型，都能更准确地区分：到底是模型生成问题、检索问题，还是评测本身的问题。”

1. **[压力追问] 你把 case 和 scorer 都改了，25/32 有什么意义？**

它不表示模型从 21/32 提升到 25/32。M22 同时改变了 case、scorer 和 schema docs corpus，所以我把它记录为新口径诊断快照，并在报告中单列自动、人工和契约重分类。复审后又明确了“成交订单”的取消订单排除口径，因此 `25/32` 也不能直接充当修复后的严格 C0；真正可比的 retrieval 实验要先刷新一次默认 C0，再在 194-doc、新 case/scorer、同模型条件下重新做。

### 验证与下一步

- 验证：复审后 M22 专属 `14 passed, 1 warning`，相关回归 `64 passed, 1 warning`，全量 pytest `147 passed, 2 skipped, 1 warning`；`25/32` 是修复前 C0 快照，尚未重跑真实 LLM diagnostic。
- 下一步：M22 的 C0-C3 重复和 Qwen `qwen3.8-max` / `qwen3.7-max` 追加对照已完成；正式收工后，下一模块优先检查 SQL Contract 的别名/等价表达误拦，再区分 QueryPlan→SQL 生成缺口与 Schema Retrieval 缺口。M23 若研究 retrieval / rerank，要从 194-doc 基线重新做单变量 A/B，不能复用 M21 的总分结论。

## ★ M23：把题目和数据校准

### 先用大白话讲

之前看到一条 SQL 答错，第一反应很容易是：“模型不行”“检索没找到表”。

但这次发现，问题也可能出在更前面的地方：

- 参考答案本身没把真实业务规则写完整；
- 数据库里故意放了取消订单、整单退款、负数退款、错误单号等真实企业常见情况；
- 一道题虽然写了参考 SQL，却可能没有真正用结果来评分；
- 向量库里的文档数量一样，不代表文档内容还是同一版。

如果这些基础没校准，后面再怎么换模型、换 embedding、调 RRF，分数也不一定可信。

M23 做的事，就是先把“考卷、标准答案、数据口径、评分规则”整理好。这样以后模型通过，才是真的通过；模型失败，也更容易知道它到底错在理解、关联、SQL，还是业务口径。

### 这次做了什么

M23 主要解决 **评测标准答案** 与 **真实数据库业务规则** 之间 **没有完全对齐** 的问题。最终统一了退款、订单去重等核心口径，把 reference SQL 真正接入自动评分，并补上异常数据专项和 Milvus 文档版本校验。

1. **统一退款率和订单量口径**

   商品退款率不再只统计带 `order_item_id` 的退款：

   - 明细退款优先按 `order_item_id` 归因；
   - 整单退款没有明细时，回退到 `refunds.product_id`；
   - 成交指标排除未支付和取消订单。

   订单量统一使用 `COUNT(DISTINCT orders.id)`，避免订单关联明细、优惠券或退款后被重复计数。

2. **让参考 SQL 真正参与自动评分**

   以前部分 case 虽然写了 reference SQL，但评分时只检查关键词、表名或输出字段。

   M23 将能确定答案的 formal 和 challenge SQL case 改为：

   - `result_match`：实际执行 reference SQL 并比较结果集；
   - `expected_value`：比较明确的固定数值。

   这样 reference SQL 不再只是给人看的说明，而是真正决定 case 是否通过。

3. **建立数据库异常专项评测**

   项目 seed 中包含一些企业数据常见异常：

   - 未支付和取消订单；
   - 一单多券导致重复计数；
   - 没有订单明细的整单退款；
   - 表示冲销的负数退款；
   - 订单头金额与明细金额不一致；
   - `SRC-*` 与 `ORD-*` 两种不能直接关联的单号。

   M23 新增了带符号净退款金额、内部外键关联渠道、订单头明细金额对账三道题，并与已有 case 组成 **6 条自动题 + 1 条人工题**的异常专项。

4. **修复 Milvus 同行数复用漏洞**

   之前 collection 只检查行数和向量维度。如果 Schema 文档内容改变但数量不变，系统仍可能错误复用旧向量。

   现在会把 **Schema 文档内容 hash** 写入 collection 元数据。复用时除了检查行数和维度，还必须检查 hash；内容发生变化时必须新建或显式重建索引。

5. **用双数据库验证参考答案**

   原有 20 条和新增 3 条 reference SQL 都在 deterministic SQLite 与当前 MySQL 上执行检查，确认 SQL 可以运行，并且两端结果行数一致。

   本地代码验证为：

   - focused：`42 passed`
   - 全仓 pytest：`152 passed, 1 warning`

### 面试怎么讲

我在 DataPilot 中做过一次 **Text2SQL 评测基线治理**。

当时我发现，SQL 评测失败不一定是模型或 Schema Retrieval 的问题，也可能是**业务口径、参考 SQL、评分规则和数据库真实数据没有对齐**。例如商品退款率只统计明细退款，会漏掉整单退款；订单关联明细、优惠券或退款表后，如果直接 `COUNT(*)`，又会把同一订单重复计算。

因此，我先统一了核心业务口径：商品退款按“**明细优先、整单退款回退商品**”归因，订单量统一使用 `COUNT(DISTINCT orders.id)`，成交指标排除未支付和取消订单。随后把 formal 和 challenge 中可以确定答案的 SQL case 改为真正执行 reference SQL，并通过 `result_match` 或 `expected_value` 比较结果，而不是只检查表名、列名或关键词。

我还针对数据库中的真实异常建立了专项评测，覆盖**取消订单、一单多券、整单退款、负数退款冲销、错误外部单号关联和订单头明细金额不一致**。相关 reference SQL 同时在 deterministic SQLite 和 MySQL 上执行，确认标准答案本身可以运行且口径一致。

另外，我发现 Milvus 以前只按行数和向量维度判断 collection 能否复用。如果 Schema 文档内容变化但数量不变，就可能继续使用旧向量。因此我把 **Schema 文档 hash** 写入 collection 元数据，复用前同时校验行数、维度和内容版本。

M23 的价值不是把某次评测分数做高，而是让后续实验建立在一个**业务口径明确、标准答案可执行、异常数据有覆盖、向量索引可追溯**的基线上。这样模型失败时，才能进一步判断问题究竟出在检索、QueryPlan、SQL 生成，还是业务语义。

1. **[基础追问] 为什么 Text2SQL 评测不能只比较生成 SQL 和参考 SQL 的字符串？**

   同一个查询可以有多种正确写法，例如使用不同表别名、CTE 或等价聚合表达式。字符串不同，不代表结果错误。

   M23 对能自动判断的 case 执行 reference SQL，再比较列和结果集；复杂语义题则保留人工复核，避免用脆弱的字符串规则代替业务正确性。

2. **[工程/深挖追问] 为什么 reference SQL 还要同时在 SQLite 和 MySQL 上验证？**

   SQLite 是本地 eval 使用的确定性 oracle，MySQL 是项目真实运行数据库。如果只验证一端，可能出现 reference SQL 在评测环境通过、到真实数据库却因方言或数据行为不同而失败。

   双端验证的目标不是要求所有生成 SQL都同时兼容两种方言，而是确认**标准答案和固定业务事实本身可信**。

3. **[压力追问] 你修改了业务口径、case 和 scorer，后面的分数还能和以前比较吗？**

   不能直接比较，这也是我在文档中明确保留的边界。

   M23 改变了业务定义、参考 SQL、自动判分方式和 Schema 文档 corpus，因此它建立的是一条**新评测基线**，不是对旧分数的直接提升。旧结果只保留为历史证据；后续模型、embedding 和 fusion 实验必须在 M23 新合同下重新运行，才能进行公平比较。

## ★ ★ M24：让 SQL 真正履行 QueryPlan

（2026-08-06）

**简述**：用 **SQLGlot AST 语义保真合同**替换容易误判的字符串检查，确保 LLM 生成的 SQL 忠实保留 QueryPlan 中的**排序、LIMIT、输出投影和展示顺序**，同时通过受控 A/B 验证规则边界。

### 先用大白话讲

QueryPlan 像一张已经审核过的“点菜单”：要查哪些列、按什么排序、取前几条，都已经写清楚。LLM 生成的 SQL 则像厨房最后端出来的菜。

M24 之前，系统主要用字符串包含关系检查两者是否一致。这会产生两种麻烦：

- 同一个意思换了写法，例如 `channels.channel_name` 写成 `c.channel_name`，如果前面有 `channels AS c`，两者实际是同一个意思，系统可能误以为错了；
- 真正重要的信息，例如 QueryPlan 明明要求 `DESC`、排序先后顺序、`LIMIT 10` 或输出列，却可能在生成 SQL 时丢失。这种情况不能因为 SQL 可以执行就放行。

M24 把检查器升级成了 **AST 语义保真合同**。它先把 SQL 解析成语法树，再比较“表达式实际指向什么”，而不是比较文字长得像不像。

同时，最终 API 返回的列也必须和计划约定的集合、别名和展示顺序一致。

一句话概括：以前检查的是字面像不像，现在检查的是 SQL 有没有忠实执行计划。

### 这次做了什么

M24 主要解决一个问题：**QueryPlan 已经写对了，但生成的 SQL 不一定照着执行。**

例如，计划要求“按订单量降序，取前 10 条”，SQL 可能丢掉排序、写反方向，或者忘记 `LIMIT 10`。旧检查又只会比较字符串，导致 `channels.channel_name` 和表别名 `c.channel_name` 这种实际相同的写法也可能被误拦。

这次按下面的顺序完成了改造：

1. **先重新检查历史失败**

   逐条查看 M22、M23 的 QueryPlan、候选 SQL、执行结果和 trace，把失败分清楚：

   - SQL 语义正确，只是写法不同；
   - SQL 真的丢了排序或 LIMIT；
   - 输出列多了、少了或顺序不对；
   - QueryPlan 或 SQL 本身生成错误；
   - 历史证据不足，暂时无法判断。

   这样避免把所有失败都错误归因给模型或 embedding。

2. **把字符串检查改成 SQL 结构检查**

   新增独立的 SQL 保真检查模块 `fidelity module`，使用 SQLGlot 把 SQL 解析成 AST，再比较实际含义。

   现在可以正确识别这些等价写法：

   - 原表名和表别名；
   - 普通字段名和带反引号的字段名；
   - 单表查询中 `table.column` 和 `column`；
   - 聚合表达式和它在同一 SELECT 中的输出别名。

   同时仍会拦截真正的问题：

   - 排序方向不一致；
   - 多个排序字段的顺序被调换；
   - 缺少 `ORDER BY`；
   - `LIMIT` 丢失或数值不一致；
   - 输出列多了、少了或顺序变化。

3. **让 QueryPlan 明确说明聚合别名的含义**

   QueryPlan 新增 `output_expressions`。例如：

   ```
   {
     "output_columns": ["channel_name", "order_count"],
     "output_expressions": {
       "order_count": "COUNT(DISTINCT orders.id)"
     }
   }
   ```

   这样系统能够确认 `order_count` 到底代表什么，不能让候选 SQL 自己随便定义一个同名 alias，然后声称自己符合计划。

4. **检查数据库真正返回的列**

   SQL 执行后，pipeline 会继续检查数据库 driver 返回的 `columns`。最终采用的政策是：

   - 只能返回计划要求的列；
   - 不能添加辅助列或内部字段；
   - 允许的别名必须提前声明；
   - 返回列顺序必须与计划一致；
   - 敏感字段仍由 SQL Guard 单独拦截。

   这保证了 API 表格和图表拿到的列稳定一致。

5. **把失败原因分到正确的位置**

   输出列不匹配现在归为 `output_contract`，不再自动算成 Schema Retrieval 或 embedding 问题。

   判断检索是否失败，要看目标表和字段有没有进入 SchemaGraph；不能因为最终 SQL 没使用某张表，就反推 embedding 没有召回它。

6. **完成本地测试和真实评测**

   | 组                                                           | 总分三次      | 自动能力三次  | manual/diagnostic | Milvus 健康                                                  |
   | ------------------------------------------------------------ | ------------- | ------------- | ----------------- | ------------------------------------------------------------ |
   | `inmemory + deterministic`                                   | `24,24,25/32` | `21,21,22/27` | `3,3,3/5`         | 不适用                                                       |
   | clean Milvus collection + DashScope `qwen3.7-text-embedding`（1024 维） | `25,25,25/32` | `22,22,22/27` | `3,3,3/5`         | 三次 final row count=195；M1 insert=195，M2/M3 insert=0；hash/1024 维一致 |


### 补课：为什么 AST 比字符串更适合 SQL 合同

AST 是 **Abstract Syntax Tree（抽象语法树）**。它把 SQL 拆成 SELECT、列、函数、表、ORDER BY、LIMIT 等结构节点。

例如下面两段文字不同：

```sql
ORDER BY channels.channel_name ASC
ORDER BY c.channel_name
```

如果 `channels AS c`，两者的 AST 在做 alias 绑定后都指向同一物理列；没有显式 `DESC` 时，ASC 也是默认方向。因此它们可以被证明等价。

但 AST 不是魔法。`ORDER BY id` 在多表查询里可能同时指向多张表；跨 CTE 或 derived table 的字段还涉及不同 scope。M24 的原则是：**能唯一证明才通过，不能唯一证明就返回 indeterminate。** 这比“猜一个最可能的解释”更符合企业查询的安全要求。

### 新概念

- **AST（Abstract Syntax Tree，抽象语法树）**：把 SQL 从一段字符串拆成 SELECT、表、字段、函数、ORDER BY、LIMIT 等结构节点。可以类比 Java 编译器解析源码：`a + b` 不再只是五个字符，而是一个加法节点和两个变量节点。
- **Semantic fidelity（语义保真）**：生成物是否忠实保留计划中已经确定的语义约束。
- **Scope（作用域）**：一个 SELECT 内名字可以解析到哪些表、列和 alias 的边界。
- **Indeterminate（无法确定）**：不是通过，也不是已证明错误；表示现有规则无法安全证明，应保守阻断。
- **Projection contract（投影合同）**：SQL 最终输出哪些列、使用什么受允许的别名、以什么顺序展示。
- **Defense in depth（纵深防御）**：pipeline 先做 SQL policy 预检，SQL Tool 执行前再做一次 Guard；语义合同不能替代安全合同。

### 代码阅读路线

1. **从计划数据结构开始**：`engine/nl2sql/planner.py`

   先看 `QueryPlanStep` 中的 **`output_columns`** 和 **`output_expressions`**。前者定义最终 API 展示列的精确集合与顺序，后者定义聚合 alias 的可信表达式。然后看 `_check_output_bindings()`：它会拒绝空输出声明、绑定了不存在输出列的 alias，以及 ORDER BY 使用了聚合 alias 却没有表达式绑定的计划。这一层解决的是：**SQL 生成前，QueryPlan 自己是否足够明确、可验证。**

2. **阅读本模块的主角接口**：`engine/nl2sql/fidelity_contract.py`

   从 `evaluate_sql_plan_fidelity()` 开始。它接收 QueryPlanStep、candidate SQL、DomainSchema 和 dialect，返回 `SQLPlanFidelityResult`。建议按三个大步骤阅读：

   - **ORDER BY**：比较排序项数量、位置、规范化表达式和方向；
   - **LIMIT**：比较整数字面量限制；
   - **projection**：比较输出列的集合和展示顺序。

   接着看 `_scope_sources()`、`_normalize_expression()` 和 `_parse_plan_alias_bindings()`，理解表 alias、唯一字段和输出 alias 如何解析到可信表达式。`_projection_issues()` 使用 tuple 保留顺序，使用 Counter 区分“纯顺序变化”和“集合变化”。这里不应改成 set，因为 set 会丢失重复列和展示顺序。SQLGlot 的所有节点类型不需要死记，重点理解 **“能唯一证明才通过”** 的边界。

3. **看 SQL 生成层如何消费合同**：`engine/nl2sql/generator.py`

   主角是 `validate_sql_plan_contract()` 和 `SQLPlanContractError`。

   `validate_sql_plan_contract()` 把 deep module 的三态结果转换成当前 pipeline 已经使用的异常式控制流；这样旧 caller 不需要一次性重写。

   `SQLPlanContractError` 会根据结果区分：普通 fidelity failure / `indeterminate` / 纯 projection failure

   阅读重点是：**复杂比较只存在于 fidelity module，generator 只负责适配调用方式。**

4. **沿真实请求执行顺序阅读**：`engine/nl2sql/pipeline.py`

   从 `run_text2sql_pipeline()` 的 SQL generation 部分开始，按以下顺序阅读：

   `QueryPlan 已验证`
   → `生成候选 SQL`
   → `SQL policy 预检`
   → `validate_sql_plan_contract()`
   → `SQL Tool 执行`
   → `output_projection span`
   → `chart generation`

   重点看 fidelity 失败时如何写入：完整 QueryPlanStep、candidate SQL 与 hash、planned/observed order、planned/observed limit、planned/observed projection、reason code、evidence level。然后看执行后的 `output_contract`：它检查的是 **数据库 driver 实际返回的列**，不是再次猜测 SQL 文本。

5. **看 prompt 如何把合同传给 LLM**：`engine/nl2sql/prompt.py`

   先看 `build_query_plan_prompt()` 如何告诉规划模型：`output_columns` 是精确合同；不得添加辅助列；聚合 alias 必须写入 `output_expressions`。

   再看 `build_local_schema_sql_prompt()` 如何告诉 SQL 生成模型：排序项、方向和先后顺序不能丢；LIMIT 不能静默改写；SELECT 必须严格按计划输出；MySQL 是生成方言，SQLite 只是本地结果核对工具。

   这里解决的是**减少模型犯错**；真正的硬保证仍由后面的 AST contract 提供。

6. **看自动评测如何检查真实输出**：`eval/scorers/rule_scorers.py`

   主角是 `_score_result_match()`。它先读取 `body.columns`，用 `_canonicalize_column_aliases()` 处理 case 明示的同义 alias，然后严格比较 `expected_columns`。alias 白名单只解决“同义列名”，不会放宽：多列、少列、错列、顺序变化。投影通过后，才执行 reference SQL 并比较行值。这样失败原因不会全部压成模糊的 `result_mismatch`。

7. **看失败如何进入正确归因桶**：`eval/triage.py`

   M24 新增 **`output_contract` failure stage**。最终 table、column 或 projection 不匹配不再自动归到 `schema_retrieval` 或 `schema_context`。只有 trace 证明目标 Schema 没进入 Context，才能讨论 retrieval 问题。这里是 M24 很重要的评测治理：**最终 SQL 没使用某张表，不等于 embedding 没召回这张表。**

8. **最后用测试理解边界**：`tests/test_m24_sql_plan_fidelity.py`

   先看历史正例：表 alias；quoted identifier；唯一限定名省略；SELECT alias

   再看真实反例：；ASC/DESC 不一致；排序项顺序变化；缺 ORDER BY；LIMIT 不一致；projection missing/extra/reordered；候选 SQL alias 自证漏洞

   最后看 `indeterminate`：；derived scope；歧义字段；ordinal ORDER BY；非字面量或 offset LIMIT

   这些测试比直接读 SQLGlot API 更容易建立完整心智模型。

核心调用链：

```
POST /api/query`
→ `QueryPlan generation`
→ `validate_query_plan()`
→ `SQL generation`
→ `SQL policy precheck`
→ `evaluate_sql_plan_fidelity()`
→ `SQL Tool + second Guard`
→ `output_contract`
→ `AgentResponse.columns / rows / chart_spec`
→ `result_match scorer`
→ `failure triage
```

**模块闭环**：M10 建立 QueryPlan，M11 把计划接入 Text2SQL pipeline，M22/M23 校正评测和业务口径，M24 最终补上 **QueryPlan→SQL→API 输出**之间的可执行合同。至此，系统不仅会生成 SQL，还能解释 SQL 是否忠实履行了上游计划。

### 设计要点

- **使用 AST，而不是继续补字符串规则**：历史证据已经出现表 alias、反引号、限定名省略和 SELECT alias。继续堆正则会让规则互相影响，也无法可靠处理作用域。
- **合同只验证，不自动改写 SQL**：自动补 ORDER BY 或 LIMIT 会让验证器膨胀成 SQL 重写器，可能掩盖模型退化，也会扩大安全责任。当前选择阻断并保留证据。
- **安全检查先于语义合同**：危险 SQL 不应该为了收集 fidelity 信息而继续深度解析。SQL policy 先拦截，SQL Tool 执行前再检查一次。
- **QueryPlan alias 必须显式绑定**：候选 SQL 是被检查对象，不能同时担任解释计划的可信来源。`output_expressions` 把 alias 语义固定在计划侧。
- **精确投影包含展示顺序**：数据库行值可以按列名对齐，但 API 表格和 chart 输入依赖稳定顺序。允许任意 extra 会同时放过合理辅助列和大量无关列，因此没有采用。
- **保留 `indeterminate`，坚持 fail closed**：首版不支持的 SQL 结构不会被误标成通过。只有真实业务样本出现，并且补齐正反例后才扩展规则。
- **MySQL 与 SQLite 职责分离**：MySQL 是生成与 AST 解析合同；SQLite 是离线 deterministic result oracle。不要求同一 SQL 同时成为两种数据库方言的标准答案。
- **不把端到端总分直接解释为 embedding 能力**：三次 Milvus 自动分均高约一分，但它仍混入 LLM 计划和生成波动，因此保持默认 `inmemory + deterministic + weighted`。
- **当前风险**：合同能判断 SQL 是否忠实于 QueryPlan，却不能保证 QueryPlan 自己理解正确。六轮评测中部分额外投影正是计划先声明过宽，随后 SQL 忠实执行了错误计划。

### 面试怎么讲

我在 DataPilot 的 Text2SQL pipeline 中实现了一套 **QueryPlan→SQL 语义保真合同**。

原来的合同通过**字符串包含关系**检查 SQL 是否保留了计划中的 `ORDER BY` 和 `LIMIT`。但真实 Trace 表明，表别名、反引号、限定名省略和 SELECT alias 等等价写法会被误拦；与此同时，排序方向写反、`LIMIT` 丢失、输出列不一致等真实错误又必须严格阻断。

因此，我没有继续堆叠正则，而是先对 M22/M23 的历史失败进行**逐 case 定性**，再通过离线 spike 验证 AST 规则的适用边界。最终基于 SQLGlot 封装了独立的**保真检查模块**，统一返回 `passed / failed / indeterminate` 和结构化证据。

这套合同会逐项比较 `ORDER BY` 的表达式、方向和先后顺序，并精确检查 `LIMIT` 与输出投影。对于 derived scope、歧义字段、ordinal ORDER BY 等暂时无法可靠证明的情况，系统会返回 `indeterminate` 并**保守阻断**。为了防止候选 SQL 用**自己的 alias 定义“自证正确”**，我还为 QueryPlan 增加了 `output_expressions`，由计划侧显式声明聚合 alias 对应的可信表达式。

在执行链路上，我保持 **SQL Guard 先于语义合同**，并由 SQL Tool 在执行前再次检查安全；SQL 执行后，再核对数据库实际返回的列集合和展示顺序。同时，Eval 和 Triage 将输出合同失败从 Retrieval 归因中独立出来，避免仅凭最终 SQL 使用了哪些表，就错误推断 embedding 是否召回成功。

这项工作的价值不只是增加一个 SQL 检查器，而是打通了 **计划、生成、安全、执行、输出与评测**之间一致、可验证、可追踪的合同与证据链。

1. **[基础追问] 这个合同通过以后，为什么还不能说明答案一定正确？**

   **fidelity contract** 检查的是 **SQL 是否忠实于 QueryPlan**，不是 QueryPlan 是否正确理解了用户问题。

   如果 QueryPlan 本身把商品退款率的分母写错，SQL 完全照着执行，fidelity 仍然会通过。因此系统还需要 QueryPlan validation、SQL Guard、SQL execution、output contract 和 result scorer。

   **类比后端 DTO 校验**：请求格式合法，不表示业务逻辑一定正确。每层合同只负责自己的边界。

2. **[基础追问] 为什么需要 `passed / failed / indeterminate` 三种状态，布尔值不够吗？**

   `failed` 表示已经找到确定不一致，例如 DESC 变成 ASC、LIMIT 10 变成没有 LIMIT。

   `indeterminate` 表示当前规则无法唯一证明，例如多表查询里的无前缀 `id`、跨 derived scope 的 alias 或 `ORDER BY 1`。

   如果只有布尔值，就会被迫把“未知”混入“错误”或“通过”。安全场景下，更合理的做法是保留未知状态并 fail closed，同时用 reason code 指导后续扩展。

3. **[工程/深挖追问] 为什么不让 LLM judge 判断 QueryPlan 和 SQL 是否语义一致？**

   LLM judge 可以辅助复杂人工语义题，但不适合代替硬合同。

   ORDER BY、LIMIT 和投影是可以确定性判断的结构约束。AST 规则成本更低、结果可复现、reason code 稳定，也能在没有网络和模型额度时工作。

   LLM judge 还可能受 prompt、模型版本和随机波动影响。对安全和执行边界，确定性规则应优先。

4. **[工程/深挖追问] `output_expressions` 会不会增加 QueryPlan 生成难度，导致更多计划失败？**

   会，这是该设计的真实代价。

   但如果不要求显式绑定，候选 SQL 就能用自己的错误表达式解释 alias，合同失去可信根基。M24 只要求非物理聚合 alias 在被 ORDER BY 使用时提供绑定，普通物理字段不需要重复声明，已经尽量控制了负担。

   后续应该根据稳定失败优化 QueryPlan prompt 或结构化生成，而不是删除可信绑定。

5. **[工程/深挖追问] 为什么把输出列顺序也设成硬合同？SQL 结果按列名读取不就行了吗？**

   行值比较确实可以按列名对齐，但 DataPilot 的输出还会被 API 表格和 chart 消费。

   如果列顺序不稳定，同一个问题可能一轮返回“渠道、订单量”，下一轮返回“订单量、渠道”，前端表格和图表维度选择都会波动。

   因此 M24 把“行值语义”和“展示顺序”分开：行值按列名比较，`body.columns` 作为独立展示合同严格检查。

6. **[压力追问] 你做了这么复杂的 AST 合同，最终总分没有明显大涨，这是不是工程自嗨？**

   这个质疑有合理部分：M24 没有把端到端总分提升包装成主要成果，稳定失败仍然存在。

   但 M24 的目标不是直接提高模型能力，而是消除错误门禁和建立可信归因。六轮诊断证明历史 alias/限定名正例没有再被误拦，同时真实表达式错误、额外投影和结果语义失败仍能被区分。

   如果没有这层治理，后续换 prompt、模型或 embedding 时，分数变化仍会混入合同误拦，实验结论不可解释。

   下一阶段的价值点也更明确：不再继续扩 AST，而是针对 QueryPlan 过宽投影和真实生成错误逐 case 修复。

7. **[压力追问] 你现在不支持 CTE、子查询和 `ORDER BY 1`，那这套合同是不是只能处理玩具 SQL？**

   这是当前边界，不应该回避。

   M24 首版是根据历史失败证据设计的，目标是修复现有单步 Text2SQL pipeline 中已经出现的问题，而不是一次性实现通用 SQL 等价证明器。

   CTE 和 derived scope 会引入跨 scope lineage，`ORDER BY 1` 依赖 SELECT 位置，扩展后需要新的可信正反例和作用域测试。当前返回 `indeterminate` 并保守阻断，比未经验证地放行更可靠。

   如果后续真实业务频繁出现这些结构，再扩展 scope lineage，而不是提前把模块做成一个难以验证的 SQL optimizer。

### 验证与下一步

- M24 focused：`70 passed, 1 warning`。
- 全仓 pytest：`176 passed, 1 warning`。
- 真实 diagnostic：Local `24/24/25`，Milvus `25/25/25`；自动分别为 `21/21/22` 与 `22/22/22`（分母 27），人工/诊断均为 `3/5`。
- 历史 alias/限定名正例六轮稳定通过，没有新的 semantic false block；稳定问题转为 QueryPlan 过宽投影、真实生成保真和结果语义错误。
- 下一步先执行 `accept-module` 验收。后续若继续优化，应针对稳定失败逐 case 修 QueryPlan/prompt；没有真实正反例前，不扩展 CTE/derived scope 等 AST 边界，也不切默认 embedding。

本地回归命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\m24-finish-full
```

读完可以试着回答：**如果 QueryPlan 写 `ORDER BY order_count DESC`，为什么合同不能直接使用候选 SQL 的 `COUNT(order_items.id) AS order_count` 来证明它正确？**

## ★ M25 治理评测可信度

（2026-08-07）

**简述**：M25 没有继续靠调 Prompt 冲总分，而是让评测能区分 **试卷问题、代码问题、模型能力、检索缺失和外部服务故障**，并用真实 attempt 证据验证 retry 是否值得开启。

### 先用大白话讲

以前看到一题失败，报告往往只告诉我们“在 QueryPlan 阶段挂了”。但这像医院只记录“病人在急诊停下”，没有回答他为什么停下：可能是模型真的不会，也可能是网络 45 秒超时，甚至可能是试题没有写清排序和列，却拿隐藏答案扣分。

M25 给评测加了三张互不替代的标签：

- **execution stage** 说失败发生在哪里，
- **root cause** 说当前证据支持该修谁，
- **report view** 说这条证据应该进入哪一种分母。

外部 timeout 仍然算端到端失败，但语义状态是 **not observed**，不能包装成“模型答错”。

同时，M25 把 LLM 的一次逻辑调用拆成可观察的 physical attempts。每次 attempt 都有 provider、模型、timeout、延迟、错误 subtype 和 outcome；这样 retry 是否有效不再靠感觉。真实 4 题小样本显示：retry 从 0 调到 1 后，请求数和总时长约翻倍，却没有救回任何一题，所以默认继续保持 **45 秒、0 retry**。

### 这次做了什么

M25 主要解决的不是“怎样让模型多答对几题”，而是“怎样让评测结果值得相信”。

以前看到某个 case 失败，我们通常只能知道它停在 QueryPlan、SQL generation 或 result scorer，却不一定知道真正原因。模型可能确实不会，也可能只是网络超时；还可能是题目没写清楚，但参考答案偷偷要求特定排序、列或时间范围。如果这些情况混在一起，总分就很难指导后续优化。

这次主要完成了以下六项工作。

1. **先把评测试题和参考答案对齐**

   我们审计了 formal、challenge、diagnostic 三套评测中的 42 个 raw cases，逐项检查题目有没有明确说明：

   - 要查询哪些字段；使用哪个时间范围；应排除哪些业务状态；按什么顺序排序；是否限制返回条数；并列时如何决定先后；参考 SQL 使用的业务指标是否已经有权威定义。

   审计发现，一些题目只写了“前 10 条”“基本信息”或“一级类目销售额排名”，但参考 SQL 还**额外**要求了固定列、2026 年 6 月、特定排序等条件。这相当于考试题没有写要求，阅卷时却按隐藏要求扣分。M25 把这些隐藏条件补回了题目，使模型看到的要求与自动评分要求一致。

   同时，为这轮新题面和新业务口径登记了 **`case_contract_version=m25-v1`**。这样 M25 的新分数不会与 M24 的旧题面分数直接混算，也不会反向修改历史实验结论。

2. **把“检查次数”和“独立问题数”分开**

   42 个 case 并不等于 42 个独立问题。例如，同一个“2026 年 6 月 GMV”问题，可能分别有：

   - 一条 case 检查最终结果；
   - 一条 case 检查 QueryPlan；
   - 一条 case 检查 Trace 步骤是否完整。

   这些 case 检查的是同一个业务问题的不同侧面。如果直接把它们当成三个独立问题，总分就会重复放大某些问题的权重。

   因此 M25 新增了稳定的 **`semantic_group_id`**，把语义相同或等价的问题放进同一组：

   - 42 个 raw cases：表示实际执行了多少项检查；
   - 26 个 independent semantic groups：表示大约有多少个独立业务问题。

   这类似于数据库分析中必须同时区分“订单明细行数”和“去重订单数”：两者都是真实数字，但回答的问题不同。

3. **重新定义业务含义**

   原来的退款率只写成 `refund_count / order_count`，但没有明确：

   - requested、approved、rejected、completed 哪些状态算退款；
   - 一笔订单有多条退款记录时算几次；
   - 整单退款没有 `order_item_id` 时如何归属商品。

   M25 将商品退款率明确为：**已完成退款的去重订单数 ÷ 包含该商品的去重成交订单数**

   `avg_selling_price` 也明确为：取与查询时间范围相交的有效价格历史记录，对 `price` 按记录条数计算算术平均，而不是按有效天数加权，也不是成交均价。不过，题意写清不等于评分已经足够可靠。因此平均售价题仍保持 manual，没有直接升级成自动硬门。

4. **把“失败在哪里”和“为什么失败”拆成两套信息**

   M19 已经能通过 `failure_stage` 告诉我们失败发生在哪一步，例如：

   - `schema_retrieval`
   - `query_plan`
   - `plan_validation`
   - `sql_generation`
   - `result_match`

   但“失败发生在 QueryPlan”并不等于“模型不会做 QueryPlan”。如果 QueryPlan 请求等待 45 秒后超时，执行位置确实是 QueryPlan，真正原因却是外部服务没有按时返回。

   因此 M25 增加了第二条轴线——**root cause**：

   - `code_issue`：确定性的代码、状态传播、parser 或安全逻辑问题；
   - `model_capability`：provider 正常返回，但计划、SQL 或业务语义不符合已确认合同；
   - `retrieval_issue`：Trace 证明回答所需的表、字段、指标或关系没有进入 SchemaGraph；
   - `external_service`：timeout、网络、限流、欠费或外部服务不可用；
   - `eval_contract`：题面、reference、scorer 或业务口径不一致；
   - `mixed_or_unknown`：证据不足，或者多个因素混在一起。

   例如本轮 `db_multi_002`：

   - LLM 在约 31.68 秒后正常返回 QueryPlan；
   - SchemaGraph 已包含类目树、商品、订单明细、订单和 `item_gmv`；
   - 但 QueryPlan 虚构了不存在的 `root_category.level` 和 `root_category.name`。

   所以它的执行阶段是 `plan_validation`，当前根因是 `model_capability`，而不是 retrieval。

5. **把“模型答错”和“根本没观察到答案”分开**

   M25 又新增了 **semantic status**：

   - `observed_correct`：拿到了答案，并且确定性评分通过；
   - `observed_wrong`：拿到了答案，并且确定性证据证明它不符合合同；
   - `not_observed`：因为 timeout 或前置阻断，最终答案根本没有出现；
   - `not_applicable`：这条 case 本来就不负责检查最终语义答案。

   例如 QueryPlan timeout：

   - 在 end-to-end 视角下，它仍然是一次失败，因为用户没有拿到结果；
   - 在 provider reliability 视角下，它是 unavailable；
   - 在 semantic answer 视角下，它是 `not_observed`，不能算成“模型已经答错”。

   报告因此拆成六个视图：`semantic answer；safety；plan/trace；provider reliability；manual/Judge；end-to-end`。

   每个视图分别报告 eligible、observed、passed 和 unavailable，避免再把综合自动评测分数直接叫作“SQL 正确率”。

6. **记录每次 LLM 请求，并用真实实验判断 retry 是否值得开启**

   以前主模型超时时，Trace 往往只剩一句网络错误，缺少：

   - 使用了哪个 provider 和模型；
   - 配置的 timeout 是多少；
   - 实际请求了几次；
   - 每次等了多久；
   - 是否发生 retry；
   - 最终是成功、timeout、HTTP 错误还是解析失败。

   M25 新增了统一的 LLM 调用模块。每次逻辑调用都会记录完整的 **attempt evidence**，成功和失败使用同一种结构。

   随后用四条历史超时题做了一个小型受控实验，固定模型、检索、题目和 oracle，只改变 retry：

   - 45 秒、retry 0：发送 4 次实际请求，1/4 获得有效响应，总耗时 179.7 秒；
   - 45 秒、retry 1：发送 8 次实际请求，0/4 获得有效响应，总耗时 377.9 秒。

   retry=1 没有救回任何一题，却让调用次数和总耗时大约翻倍。因此本轮没有证据支持默认开启 retry，默认继续保持：

   - `LLM_TIMEOUT_SECONDS=45`
   - `LLM_MAX_RETRIES=0`

   这只是四题小样本，不能解释成 provider 的总体 SLA，也不能证明 retry 永远无效。它只支持一个保守结论：**当前没有足够证据值得让所有请求默认承担重试成本。**

7. **用反例证明业务 SQL 不能“碰巧答对”**

   为退款率和递归类目建立了最小反事实数据：

   - 退款率中，正确 SQL能区分一单多退款、非 completed 状态和整单退款；旧记录数口径会得到错误结果。
   - 递归类目中，正确 item grain 得到 70；漏掉子类目只得到 20；错误使用订单头金额会因一单多明细被重复累计成 200。

   这些反例证明了不同 SQL 的业务含义确实不同，而不是只看当前 seed 上是否碰巧返回同一个答案。

   对 recursive CTE，现有 SQL fidelity 仍然返回保守的 `indeterminate`。M25 没有为了让某一题通过，就临时把 AST 检查范围扩大成未经验证的通用 CTE 等价判断。

### 新概念

- **Execution stage vs root cause**：stage 像异常堆栈告诉你在哪一层抛错；root cause 像事故复盘告诉你为什么发生。`query_plan + timeout` 的 stage 是 query_plan，根因却是 external service。
- **Observed / unavailable**：`observed_wrong` 表示系统真的拿到答案并证明它错；`not_observed` 表示外部故障或前置阻断使答案根本没有出现。二者都可算端到端失败，但不能进入同一个模型能力分子。
- **Semantic group denominator**：一个问题可以同时有结果、Plan、Trace 三个 case。raw case 是检查次数，semantic group 才接近独立问题数，类似数据库里明细行数与 `COUNT(DISTINCT order_id)` 的区别。
- **Logical call / physical attempt**：一次业务调用可能因 retry 发送两次 HTTP 请求。成本和延迟必须按 physical attempt 统计，最终成功率则按 logical call 统计。
- **Counterfactual probe**：构造一小份能让正确 SQL 和常见错误 SQL 得出不同结果的数据。它像单元测试里的边界用例，防止错误 SQL 在单一 seed 上“碰巧答对”。

### 代码阅读路线

1. **先看调用可靠性 seam**：`engine/nl2sql/llm_call.py`

   从 `execute_llm_call()` 开始。它接收 client、prompt、stage 和策略，返回 `LLMCallResult`；重点看 `LLMAttemptEvidence` 与 `LLMCallEvidence` 如何避免保存敏感 prompt 正文。retry 分支只相信异常上的 `retryable`，不要先陷入 backoff 的小细节。

2. **再看 provider 如何分类错误**：`engine/nl2sql/generator.py`

   `OpenAICompatibleChatClient.complete()` 把 timeout、Arrearage、WinError 10013、429/5xx 和响应结构错误变成稳定 subtype；`_complete_with_evidence()` 把可靠性 module 接回 QueryPlan/SQL parser。这里的关键边界是 **transport 不负责业务解析**。

3. **看证据怎样进入一次请求的 Trace**：`engine/nl2sql/pipeline.py`

   QueryPlan 与 SQL generation 各自收集 request-local evidence。成功 span 和失败 span 使用同一种 `llm_call` metadata，所以报告不会只看见失败样本。

4. **看两轴归因与报告分母**：`eval/triage.py`

   先读 `triage_result()` 的最早硬失败规则，再读 `_root_cause()` 和 `_semantic_status()`；最后读 `analyze_eval_run()` 如何从相同 triage 构建六个视图。重点理解它深化了已有 module，没有再造第二套归因事实源。

5. **看 case 和 report 的入口**：`eval/run_eval.py`、`eval/cases/*.yaml`

   `EvalCase.semantic_group_id` 默认回退 case id，旧 case 不需要一次性迁移；`CASE_CONTRACT_VERSION="m25-v1"` 防止新旧合同混算。`write_report()` 只渲染 `analyze_eval_run()` 的结果。

6. **最后看业务反例**：`tests/test_m25_eval_trustworthiness.py`

   这里最值得复盘的是退款率和递归类目的内存 SQLite 反例，以及 retry/非 retry、external/model/retrieval/eval/code root cause 的正反例。

核心链路：

`EvalCase + semantic_group_id`
→ `pipeline QueryPlan / SQL generation`
→ `execute_llm_call + attempt evidence`
→ `TraceStep metadata`
→ `triage_result(stage + root cause + semantic status)`
→ `analyze_eval_run(report views)`

### 设计要点

- **不使用 stateful metadata**：显式返回 evidence，再用 request-local sink 写 Trace，避免复用 client 时把 A 请求的调用证据写到 B 请求。
- **retry 默认关闭**：只有 timeout、连接错误、429、5xx 等明确 transient 错误可重试；欠费、权限、普通 4xx、parse、合同和语义错误不重试。
- **历史分数冻结**：M25-v1 改了题面、退款率与分母，不能反向重算 M24 历史结果。
- **不扩大 AST scope**：recursive CTE 当前不能被安全证明时返回 indeterminate；能力反例与 result oracle 先证明业务差异，AST 扩展留给后续独立决策。
- **真实边界**：可靠性候选各只有一次 4-case run，足以否定本轮默认 retry，但不足以描述 provider 总体 SLA，也没有完整 M25-v1 baseline。

### 面试怎么讲

我在 DataPilot 的 M25 没继续通过调 Prompt 追总分，而是治理评测可信度。首先审计 42 个 raw cases，把隐藏的时间、列、排序和 LIMIT 写回题面，并用 semantic group 得到 26 个独立问题。然后把失败拆成 execution stage、root cause 和 semantic status：例如 QueryPlan timeout 仍算端到端失败，但属于 external service 且答案 not observed，不能算模型答错。工程上我做了一个 LLM call executor，成功和失败都记录 provider、模型、timeout、每次 attempt 延迟和稳定错误 subtype。最后用 4 条历史超时题做单变量实验，retry=1 把调用数从 4 增到 8、耗时从约 180 秒增到 378 秒，却没有恢复请求，因此默认保持 45 秒、0 retry。模块最终通过 184 个测试，且没有切模型、检索或 oracle。

1. **[基础追问] 为什么 raw case 数不能直接当独立问题数？**

   同一个自然语言问题可能分别检查结果、QueryPlan 和 Trace。如果把三条都当独立问题，某类能力会被重复加权。M25 保留 raw case 作为检查次数，同时用 stable semantic group 报独立问题数；这与订单明细行数和去重订单数必须分开统计是同一个道理。

2. **[工程/深挖追问] 你怎么保证 timeout 不被归因成模型能力不足？**

   不能靠错误文案猜。我在 transport 层生成稳定 subtype，并把每次 attempt 的 stage、timeout、latency、provider/model 和 outcome 写入 Trace。triage 先保留执行 stage，再依据 transport evidence 判 root cause；external failure 的 semantic status 固定为 not observed，但仍进入 end-to-end failure 和 provider unavailable。

3. **[工程/深挖追问] 为什么不默认 retry 一次，反正请求是幂等的？**

   幂等只说明不会产生重复副作用，不代表成本可接受。真实小实验中 retry=1 没救回任何一题，物理调用和总耗时约翻倍。并且 retry 还会放大额度、排队和尾延迟。所以默认策略必须看恢复率与成本，而不是只看“技术上能重试”。

4. **[压力追问] 4 条题各跑一次，就敢说 retry 没用吗？**

   不能说总体没用，这个质疑成立。我的结论严格限定为“本轮没有证据支持把 retry 切成默认”，不是 provider SLA。M24 六轮已显示部分题有稳定 45 秒 timeout，M25 本轮又观察到 retry 无恢复和成本翻倍；因此保持原默认是保守决策。如果要选择新 timeout 或 SLA，需要预注册候选并重复运行。

5. **[压力追问] 做了这么多评测工程，业务正确率还是没给出来，是不是绕开了真正问题？**

   M25 确实没有交付完整新基线，因为用户明确保留 formal/challenge/diagnostic 手动执行；我没有用 4 题小样本冒充业务正确率。但这不是回避：模块已经让后续基线能区分 external unavailable、observed semantic wrong、safety 和 plan/trace，并用退款率与递归反例固定了业务口径。完整运行完成后，分数才有可解释性。

### 验证与下一步

- 聚焦回归：**39 passed, 1 warning**。
- 全仓最终：**184 passed, 3 skipped, 1 warning**。
- seed reset：14 表固定规模与关键事实通过，新退款率口径下最高商品仍是 Aurora 耳机。
- warning 是既有 Starlette/httpx deprecation，不影响 M25。
- 下一步：用户手动运行 M25-v1 的完整 formal/challenge/diagnostic，再进行人工检查和 `accept-module`；若递归 CTE 需要扩大 fidelity scope，必须单独做设计决策。

可复制验证命令：

```powershell
# 聚焦门禁：预计 39 passed
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m25_eval_trustworthiness.py tests\test_m24_sql_plan_fidelity.py tests\test_m19_failure_triage.py tests\test_phase3a_pipeline.py -q --basetemp=.agent_work\temp\pytest-m25-focused

# 全仓回归：本次结果 184 passed, 3 skipped
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.agent_work\temp\pytest-m25-full

# 4 条可靠性专项；实验时只在当前 shell 临时覆盖 timeout/retry
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --case-set eval\cases\m25-reliability-suite.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\m25-reliability-traces.jsonl --report .agent_work\temp\m25-reliability-report.md --triage-json .agent_work\temp\m25-reliability-triage.json
```

**本地启动体验：** M25 没有新增独立页面。可按既有 runbook 启动 FastAPI，在 Swagger 调 `/api/query`；本模块的新增价值主要从 JSONL trace 的 `llm_call`、triage JSON 的 `primary_root_cause/semantic_status` 和 Markdown 的 `M25 Evidence Views` 查看。

## ★ M26 继续治理评测可信度

（2026-08-07）

M26 的目标不是再跑一次大模型、再看一个总分，而是先回答一个更基础的问题：**上一轮评测里显示的失败，哪些真是模型错了，哪些是评测和代码把正确路径误判了？**

### 先用大白话理解

一次评测报告像期末成绩单，但成绩单本身也可能有阅卷规则错误。M26 先把已经跑完的 M25 round2 冻结为审计输入，再让人工按同一份 trace、SQL、结果和 triage 证据逐项复核。这样后续修改不会把历史证据“洗白”，也不会因为重新调用不稳定的模型而得到另一份无法比较的答案。

审计结果是：32 条 raw case 实际对应 26 个独立语义问题；人工复核后有 26 条一致、1 条是假阳性、4 条是状态不一致、1 条证据不足。这里最有价值的不是“找到了几个 bug”，而是把每种不一致都连回可复现的代码和测试。

### 这次做了什么

这次先做一次 **评测结果审计（evaluation audit）**：确认 diagnostic 中每个“通过”或“失败”到底是否可信。否则很容易把 **评分器 bug、SQL Guard 误拦、网络超时** 错当成模型能力不足，后续优化方向就会跑偏。具体做了下面几件事：

1. **冻结并整理上一轮 diagnostic 的原始证据**

   我们没有重新调用 LLM，而是固定使用 M25 round2 已经产生的：

   - Trace：模型在哪一步执行、生成了什么 QueryPlan、是否生成 SQL；
   - 候选 SQL：模型实际给出的 SQL；
   - 执行结果与评分结果；
   - triage：原来系统对失败阶段和原因的判断。

   这样做的意义是：**先判断“当时这次运行发生了什么”，而不是重新跑一次后得到另一份受网络和模型波动影响的结果。**

   最终把 32 个检查项整理为 26 个独立业务问题，并为每一项保留可回看的审计记录。

2. **逐项检查上一轮生成 SQL 是否真的符合业务合同**

   这次确实检查了上一轮的 SQL，但检查方式是基于冻结的 SQL、执行结果和业务合同做审计，**不是重新执行全部候选 SQL 或重新生成 SQL**。

   最典型的是 `db_core_002`：自动评分显示它通过了，但审计发现候选 SQL 少了整单退款的归因回退：

   ```
   COALESCE(order_items.product_id, refunds.product_id)
   ```

   如果退款没有关联到具体订单明细，正确逻辑应回退使用 `refunds.product_id`。原 SQL 漏掉这部分，但现有 seed 数据恰好没有让它暴露错误，所以结果“碰巧正确”。

   因此这次新增了一个 **反事实测试**：专门构造能让正确 SQL 与错误 SQL 得到不同结果的数据。这样以后不会再因为当前数据太巧合，让错误 SQL 被自动判为正确。

3. **修复合法 CTE 被 SQL 安全层误拦的问题**

   递归 SQL 常用 CTE，例如：

   ```
   WITH RECURSIVE category_tree AS (...)
   ```

   `category_tree` 只是本次查询内部创建的临时名字，不是真实数据库表。旧 SQL Guard 没有区分两者，会把它也当成物理表做 RBAC 权限校验，导致合法递归查询被拒绝。

   现在改为按 SQL 的 **scope（作用域）** 判断：

   - CTE 临时名可以被后续 SQL 引用；
   - CTE 内真正访问的物理表仍做 RBAC 检查；
   - 即使经过 CTE，也不能读取 `users.email` 之类敏感字段。

   所以这不是“放宽安全规则”，而是让安全规则识别正确的 SQL 结构。

4. **修复 SQL Fidelity 对 `\* 1.0` 的误判，但严格控制范围**

   有些 SQL 会写成：

   ```
   refund_count * 1.0 / NULLIF(order_count, 0)
   ```

   这里的 `* 1.0` 通常只是为了避免整数除法，让结果保留小数；它不改变退款率的业务含义。但旧 Fidelity 会把它视为“SQL 与 QueryPlan 表达式不同”，从而阻断执行。

   这次没有实现宽松的“数学等价判断”，因为通用代数变形会碰到空值、类型、聚合粒度、Join 重复和数据库方言等风险。

   只增加了一个 **可证明安全的窄规则**：

   - 分母仍是相同的 `NULLIF(..., 0)`；
   - 分子不变；
   - 唯一变化只是额外乘以 `1.0`。

   只在满足这些条件时才视为等价；换分子、换分母、乘其他数字等情况仍然会被拒绝。

5. **让 SchemaGraph alternatives 和人工复核状态真正生效**

   评测 case 中原本已经可以写“满足方案 A 或方案 B 都算 SchemaGraph 正确”，但评分器没有真正使用这条规则，导致有些 Context 检查表面通过、实际没有验证到目标内容。

   现在评分器会从同一次请求的 SchemaGraph 中检查：

   - 找到了哪些表；
   - 找到了哪些字段；
   - 找到了哪些指标；
   - 是否完整满足任意一种允许的替代方案。

   同时，把两种以前容易混淆的状态拆开：

   - **`execution_failed`**：自动链路已经确定失败；
   - **`review_pending`**：缺少确定性 oracle，需要人工判断。

   例如模型超时、根本没有生成 SQL，不能叫“模型 SQL 答错”；它应是外部不可用或未观察到结果。`db_hard_003` 这种 SCD 时间边界题则仍是人工复核，不伪装成自动失败。

最终，这次工作把“上一轮的分数”拆成了更可信的事实：哪些是 **真实 SQL 语义错误**，哪些是 **代码或 scorer 的确定性缺陷**，哪些只是 **外部超时导致没有观察到结果**。这样下一次完整 diagnostic 跑出的 M26-v1 基线，才有可解释性。

模块完成后又补跑了 **两轮、四种模型/检索组合的完整 diagnostic**，共 256 次 raw case 执行；各组合都落在相近区间，现有证据不足以证明 Qwen Max 或 Milvus 有稳定优势。随后由 Codex 对第二轮 Qwen Plus 的 local / Milvus 两组各 32 条逐题审查，除了区分 **SQL 确实错误** 与 **超时导致无 SQL**，还发现 3 条自动通过但业务语义有误的 SQL，说明只看 runner 总分仍会漏掉 false positive。

复查也暴露了当前评测结构的历史包袱：formal、challenge、diagnostic 存在重复业务问题，manual、expected-block 和能力诊断题又混在同一总分里。后续建议改为 **一个业务场景只执行一次、多个 assertion 共享同一份 Trace**，suite 只负责选择场景，diagnostic 改为多维报告视图；这仍是待确认的下一步方向，M26 没有擅自改动现有 case 或正式口径。

### 新概念

- **Frozen audit evidence**：先把一次运行的输入、trace、报告和 triage 固定下来再复核。像财务审计先封存凭证，避免后续系统变化改变被审计的事实。
- **SQL scope**：CTE、子查询和外层查询各有自己的名字空间。判断一个标识符是不是物理表，不能只扫描全局名称，必须看它所在 scope。
- **Narrow semantic equivalence**：只接受能够用明确 AST 结构证明的一个小等价规则，而不是“看起来差不多就通过”。它宁可保守，也不把真实业务 SQL 改错放过去。
- **Execution failed vs review pending**：前者说明自动链路已确定失败，后者表示还没有足够证据下结论；两者都可能尚未通过，但不能混成一个失败原因。

### 代码阅读路线

1. 先看 `eval/audit.py` 和 `eval/run_audit.py`，理解冻结证据如何生成 audit record、如何写入人工 verdict，以及为什么 audit 不重跑模型。
2. 再看 `engine/sql_guard/policy.py` 的 `extract_sql_access()`，重点理解 sqlglot `Scope` 如何让 CTE 名称不冒充物理表。
3. 看 `engine/nl2sql/fidelity_contract.py` 的 ratio helper，观察“仅加 `* 1.0`”如何被限制为可证明的窄模式。
4. 看 `eval/scorers/rule_scorers.py`、`eval/triage.py` 与 `eval/run_eval.py`，理解 SchemaGraph alternatives、正交 triage 状态和报告如何共享同一份事实。
5. 最后读 `tests/test_m26_targeted_contracts.py`；其中 CTE/RBAC、ratio 正反例、SchemaGraph alternatives、triage 和退款率反事实覆盖了本模块最重要的边界。

### 设计要点

- **冻结审计证据不回写**：审计只消费同一轮 run 的 case / trace / report / triage，人工 verdict 不与正式 `passed`、LangFuse score 或历史报告混写。原因和财务审计封存凭证一样——先固定事实，再谈修复；否则每次系统变化都会悄悄改变被审计的结论。
- **窄等价宁可保守**：fidelity 只接受"同一分母 + 分子仅多乘 `* 1.0`"这一种可证明的类型提升。不做通用代数化简，因为 NULL、类型、聚合粒度、Join 重复和方言差异都可能在"看起来一样"的变形中被忽略。
- **schema_context 直接消费 SchemaGraph**：`expected_tables_alternatives` 由同请求的 tables / fields / metrics 判定，绝不拿最终输出列冒充上下文证据。这样"检索对了但 SQL 生成错了"保持为两条独立证据，也不会让最终响应反向篡改 Context 结论。
- **failed 兼容 + 正交状态**：保留旧 `failed` 字段供历史脚本使用，另加 `execution_failed`（自动链路已确定失败）与 `review_pending`（缺确定性 oracle，待人工），消除"待人工看"被误读成"执行失败"的歧义。
- **CTE 修复是名称解析修正，不是安全放宽**：只把 CTE 临时名从 RBAC 表集合中剔除，CTE 内部访问的物理表和敏感字段仍逐 scope 严格检查；安全边界是"修正识别，不降低约束"。

### 面试怎么讲

我在 DataPilot 的 M26 做的不是直接调 Prompt 或追求更高的 diagnostic 总分，而是先治理评测结果的可信度。M25 的 diagnostic 已经暴露出递归 SQL、退款率、SchemaGraph 和人工题状态上的异常，但“失败”不一定等于模型答错：它也可能来自 SQL Guard 误拦、评分器没有消费 case 合同、当前 seed 恰好掩盖错误 SQL，或者外部超时导致根本没有生成 SQL。

因此我先冻结上一轮的 trace、候选 SQL、执行结果、评分报告和 triage，避免重新调用 LLM 后被网络和模型波动干扰。32 个检查项归并为 26 个独立语义问题后，我发现了一次自动评分假阳性：退款率 SQL 漏掉整单退款的 `COALESCE(order_items.product_id, refunds.product_id)` 回退逻辑，却因为现有 seed 数据碰巧通过。随后我用 SQLite 反事实数据证明，缺少回退时会把正确答案从 `Beta, 1.0` 错算成 `Alpha, 0.0`。

修复时我刻意控制范围：SQL Guard 仅在 AST scope 内识别 CTE 临时名，真实物理表和敏感字段继续走 RBAC；SQL fidelity 仅接受相同分母和分子、只多出 `* 1.0` 的 ratio 类型提升；SchemaGraph scorer 开始真正消费 alternatives；自动执行失败与等待人工复核拆成正交状态。最终 focused 62 个、全仓 194 个测试通过。但我没有把这些确定性修复说成模型能力提升：M26 尚未跑新的完整 LLM diagnostic，新的 M26-v1 端到端基线仍需用固定配置独立建立。

1. **[基础追问] 你这个模块到底是在修模型、修 SQL 安全，还是修评测？为什么这些事情会放在同一个模块？**

   M26 的主目标是修 **评测归因的可信度**，但审计证明有些“评测失败”来自确定性代码边界，因此不能只改报告。比如递归 SQL 被拒绝时，表面上看是模型没有完成任务，实际是 SQL Guard 把 CTE 临时名误认为物理表；`schema_context_match` 表面通过，实际没有验证 alternatives。  

   所以这个模块不是把模型、安全和评测混在一起，而是沿着同一条证据链处理：**冻结运行证据 → 判断失败来源 → 只修已经证实的确定性缺陷 → 用测试证明边界没有被放宽**。模型是否真的进步，仍要由后续完整 diagnostic 回答。

2. **[工程/深挖追问] 你让 CTE alias 绕过了表级 RBAC。攻击者能不能把敏感表藏进 CTE，借此绕过权限检查？**

   不能，因为放行的不是 CTE 内的数据访问，而只是 **查询内部临时名字的引用**。例如 `category_tree` 是 CTE alias，不是数据库里的物理表；后续 `SELECT * FROM category_tree` 不应再把它当作一张真实表检查。  

   但 SQL Guard 会继续进入这个 CTE 对应的 scope，提取其中真正访问的物理表和字段。因此 CTE 内查询禁用表仍会被拦截，访问 `users.email` 这类敏感字段也仍会被拦截。M26 的回归测试同时覆盖了合法递归 CTE、CTE 内越权表、CTE 内敏感字段和 CTE 名遮蔽物理表四种情况。这里的安全边界是：**修正名称解析，不降低数据访问约束。**

3. **[工程/深挖追问] 你如何证明 `db_core_002` 是自动评分假阳性，而不是你主观认为那条 SQL “写得不够标准”？**

   我没有只根据 SQL 写法下结论，而是把业务合同变成了能区分正确与错误的反事实数据。合同规定商品退款率需要优先按订单明细归因，整单退款缺少 `order_item_id` 时再回退到 `refunds.product_id`。  

   原候选 SQL 缺少这个回退，在原 seed 上仍然通过 Top1 结果比较；但在新构造的最小 SQLite 数据里，正确 SQL 得到 `Beta, 1.0`，缺少回退的 SQL 得到 `Alpha, 0.0`。因此它不是“风格不同”，而是在存在整单退款时计算了错误的业务语义。  

   这也是 M26 的一个原则：**当现有数据无法区分两种 SQL 时，不能仅凭一次 result_match 就宣称它们业务等价。**

4. **[压力追问] 你的审计还要从历史 Markdown 报告里提取 Score Summary。既然源数据不完整，凭什么相信这次审计结论？**

   不能把这部分证据说得比它实际更强。历史 M25 run 没有单独保存逐 case 的结构化 `score_details`，因此 M26 的 legacy adapter 只读取冻结 Markdown 中已有的 Score Summary，并在审计记录里明确标注来源和报告 hash。  

   关键是它没有重新执行 scorer，也没有从别的 run 补数据；trace、候选 SQL、triage 和报告必须来自同一冻结运行，缺任何一项就失败。这样至少保证审计不把另一轮运行的证据拼进来。  

   这条限制也已经转化为后续改进项：新的 runner 应保存结构化 score artifact，让报告只是给人阅读的展示层，而不是审计时反向恢复事实的长期数据源。

### 验证与下一步

- 聚焦回归：**62 passed, 1 warning**。
- 全仓回归：**194 passed, 1 warning**。
- warning 为既有 Starlette/httpx deprecation，不影响 M26。
- 本模块未运行新的完整真实 LLM diagnostic，也没有切换模型、embedding、Milvus、LangFuse 或数据库默认值；因此不能把确定性修复表述为新的端到端能力基线。
- 下一步：用户人工查看 audit artifact 后执行 `accept-module`；若要得到 M26-v1 的新真实 LLM 基线，应另行授权完整运行。

可复制的审计命令（用于已保留的冻结输入）：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_audit --trace <frozen-trace.jsonl> --report <frozen-report.md> --triage <frozen-triage.json> --output-prefix eval\reports\m26-audit
```

**本地启动体验：** M26 没有新增 Web 页面。阅读 [审计 Markdown](eval/reports/m26-qwen37plus-local-round2-audit.md) 或运行上述 CLI 即可查看逐 case 证据；API 启动方式仍以 `docs/state/runbook.md` 为准。

## ★ ★ M27 Eval 体系优化

（2026-08-09）

**简述**：把旧评测里“同一道业务题为了多检查几项就多调用几次模型”的结构，改成 **一题一次执行、多条断言共用同一份证据** 的 `m27-v1` 体系；确定性验证已完成，但 **尚未运行新的真实 LLM 基线**。

### 先用大白话讲

旧 diagnostic 像是让同一个学生为数学、语文和实验课分别重新答一遍同一道题：不仅浪费调用，还会因为每次 LLM 输出不同，让“这次 SQL 错了”与“这次 Trace 少了一步”混成两张不同答卷的结论。M27 改成一张答卷交给多位老师：**Result、SchemaContext、QueryPlan、Trace、安全和拒绝路径**分别评分，但都看同一次 API 执行、同一份 SQLite snapshot 和同一个 trace。

把它类比成你熟悉的后端接口测试会更直观：不能为了验证响应字段、数据库写入和日志各发一次 HTTP 请求；应该先完成**一次请求**，再围绕这次请求留下的事实写多条断言。M27 的价值正是让“模型这次答得怎样”先变成一份可追溯的答卷，再讨论不同维度的成绩。

### 这次做了什么

这一节的主线是：先把“题目是什么”和“怎样检查答案”拆开，再把一次运行留下的事实保存好，最后才计算不同视图的分母和 Gate。这样评测报告不再只是一个总分，而能回答：**哪道业务题出了问题、问题发生在哪一层、这次是否有足够证据下结论。**

- **先消除重复答题和“空检查”**：旧 formal、challenge、diagnostic 的 **42 条 raw case** 实际只有 **26 个旧语义组**，同一业务问题会因检查结果、计划或 Trace 而被重复调用模型。更危险的是，部分旧 check（例如 metric mapping、JoinPath、Plan、Trace）没有真实 scorer，会落入默认 `ok`。M27 先做 inventory 和迁移矩阵，再把它们整理成 **28 个 canonical Scenario**：这里的 Scenario 就是“一道唯一的业务题”，而不是“一种检查方法”。

- **让一次答题接受多项检查**：每个 Scenario 可以挂多个 **typed assertion**。assertion 可以理解为“有明确规则的判卷项”：例如六月 GMV 这道题，既可检查结果行，又可检查返回列、Schema Context、QueryPlan 和 Trace。`Evaluator.evaluate()` 保证同一个 `(run, scenario, replicate)` 最多调用一次 Pipeline；候选 SQL 和 reference SQL 也共用同一 SQLite snapshot。于是多个 scorer 是在检查**同一张答卷**，不会发生“结果来自第一次模型输出、计划来自第二次模型输出”的归因混乱。

- **把分数改成可解释的视图**：`EvalRun` 保存每次执行和 assertion 的结构化明细，`Projector` 再从明细计算 `eligible / observed / passed / failed / not_observed`。其中 `not_observed` 的意思不是答错，而是这次没有足够证据自动评分，例如外部服务不可用；Reliability 的多次 replicate 也会归约为一个逻辑 Scenario，不能靠重复请求扩大分母。Core、Stress、Manual Lab 说明题目职责；Smoke、Reliability、Database Exception 是“从题库选题”的 selector；Gate 则单独决定哪些 assertion 必须通过。

- **用反事实守住业务合同**：只在当前 seed 上对比结果，错误 SQL 可能碰巧通过。因此 SCD、退款率和递归分类都有最小 SQLite 反事实：缺少 `valid_to IS NULL`、把 rejected refund 算进分子、漏掉子类时，坏 SQL 必须得到不同结果。这证明的是 **case 合同和 scorer 能区分对错**，不是模型能力已经提升。

- **明确本模块没有做什么**：M27 保存的是脱敏的结构化 artifact（例如行数、fingerprint、Trace 摘要），不默认保存完整结果行、prompt 或凭证；旧 M26 报告也不重算。后续虽已获授权运行 Core，但它只是有限次数的真实快照，不能据此宣称模型稳定能力、成本优势或检索因果。

**后续补记**：M27 主体完成后，又围绕“人工怎么看结果”和“真实 Core 怎么读”做了三项小收口。

1. **补人工复查功能**：新增独立 review bundle，让 Codex/人工能查看脱敏 SQL、有限结果样本和 Trace 摘要；它只帮助解释自动结果，**不改 Gate 和分数**。

2. **吸收 M26 审查教训**：给复查材料加来源 SHA-256、错误分类，并规定普通题没有候选 SQL 时只能写“证据不足”，避免把外部调用失败误说成模型答错。

3. **运行两轮 Core 对照**：`qwen3.7-plus` 与充值后 `qwen3.7-max` 的本地/Milvus Core 都出现 **29 passed / 5 failed / 0 not_observed**；这说明当前稳定暴露的是同一批合同缺口，不足以证明 Milvus 或模型谁更好。

### 新概念

- **Scenario + assertion**：Scenario 是唯一业务问题；assertion 是对同一份执行证据的一个可裁决检查。可以把它类比成一次 SpringBoot 接口调用后的多层测试：业务返回、字段契约、日志和安全策略各自断言，但不会为了每条断言再发一次请求。
- **Snapshot oracle**：候选 SQL 与 reference SQL 在同一个数据库快照上执行。像单元测试里的同一事务，避免 scorer 各自重新 seed 数据导致“标准答案”和“实际答案”看见不同数据。
- **Projector**：结构化明细的只读视图。它类似 SQL 的聚合查询：Markdown 和 LangFuse payload 都消费同一个投影，不再让 Markdown 反过来成为评分事实源。

### 代码阅读路线

1. **先看合同**：`eval/contracts.py` 与 `eval/catalog.py` 定义 `m27-v1` Scenario、typed assertion、四类 hash 和严格 YAML loader；重点理解为什么未知 kind 会在执行前失败。
2. **再看执行闭环**：`eval/evaluator.py`、`eval/environment.py`、`eval/ports.py` 展示一次 Pipeline 调用、同 snapshot Oracle、checkpoint 与 interrupted/abandoned 边界如何协作。
3. **看怎么评分**：`eval/assertions.py` 和 `engine/nl2sql/pipeline.py`。后者把安全的 `plan_steps` 写入 trace，前者用它评分 Plan、Join 和 Metric，而不再默认通过。
4. **最后看消费层**：`eval/selectors.py`、`eval/projectors.py`、`eval/reporting.py` 和 `eval/run_eval.py`。这里能看到 selector 不复制题面、replicate 不扩大分母，以及 CLI 只把 gate 转成退出码。

核心调用链是：

`canonical scenarios.yaml`
→ `catalog / selector`
→ `Evaluator.evaluate()`
→ `RunEnvironment（API + 同 snapshot Oracle）`
→ `ExecutionEvidence`
→ `typed assertions`
→ `EvalRun artifact`
→ `projector`
→ `Markdown / LangFuse payload / CLI gate`

### 设计要点

- **新旧合同隔离**：旧 formal/challenge/diagnostic 报告仍是历史证据，不能被 M27 重新计分；新结果也不能与旧 `25/32`、`26/32` 直接比较。
- **安全 artifact 优先**：完成的 JSON 只保存 allowlist trace 摘要、行数和稳定 fingerprint，不保存完整 rows、prompt、answer 或凭证。代价是不能恢复原始业务行，换来清理 raw trace 后仍能核验评分身份且不泄露 PII。
- **不擅自改变运行默认值**：本模块没有切模型、检索、embedding、数据库、oracle、timeout 或 retry；真实 LLM 基线仍需要单独授权。

### 面试怎么讲

我把 DataPilot 的评测从“case 列表加总分”改成了更像工程测试平台的合同体系。先盘点发现 42 条 raw case 只有 26 个旧语义问题，同题被不同诊断维度重复调用，而且部分 Join/Plan/Trace check 实际会默认通过。于是我设计了 `Scenario + typed assertion + Evaluator`：每个业务问题只执行一次，结果、上下文、计划和安全断言共享同一份 trace 与数据库 snapshot；再用 versioned projector 推导分母和 gate。为了避免原 seed 掩盖 SQL 语义错误，我还为 SCD、退款和递归分类补了反事实 SQLite 测试。全仓 208 个测试通过，但我没有把它包装成模型能力提升，因为真实 M27 基线尚未运行。

1. **[基础追问] M27 为什么要把 Scenario 和 assertion 分开？这和普通测试用例有什么不同？**

   **Scenario** 表示一个唯一的业务问题，例如“六月各渠道 GMV 排名”；**assertion** 表示围绕同一答案要检查的某个维度，例如结果是否正确、输出列是否正确、计划是否真的用了 `channels -> orders` 的 Join。普通测试也可以有多个断言，但旧评测的数据结构把“一个 check”当成“一道题”，导致同一业务问题要重新调用多次模型。M27 把业务题与评分维度拆开，才能保证多条断言看到的是**同一张答卷**，也才能明确一个问题到底是 SQL 语义错、Context 不足，还是 Trace 证据缺失。

2. **[工程/深挖追问] 为什么不继续在旧 runner 上补几个 scorer？**

   因为旧 runner 的基本单位是单个 check，对同一业务题会重复调用模型；即使补齐 scorer，Result 和 Plan 也可能来自不同 LLM 输出，归因仍不可信。M27 把复杂性集中到 `Evaluator.evaluate()`，先固定“一题一次执行”的证据边界，再让多个纯 scorer 读取同一份 evidence。

3. **[压力追问] 你保存 hash 不保存完整结果行，出了争议怎么复核？**

   这个质疑成立：hash 不能替代原始业务数据。M27 的目标是长期、安全地保存可重算的自动评分身份和结构化差异，不是建设审计数据仓库；raw trace 仍可短期保留用于排障。若未来需要人工仲裁或长期保留完整 rows，应新建受控的权限、保留期和脱敏策略，而不是把敏感数据默认塞进 eval report。

### 验证与下一步

- 验证：M27 focused/counterfactual **`14 passed, 1 warning`**，证明一次调用、多断言、artifact、selector/gate 与 SCD/退款/递归反事实；legacy Eval 回归 **`37 passed, 1 warning`**，证明历史读取链未被破坏；pipeline 相关 **`21 passed, 1 warning`**，证明新增 QueryPlan trace 摘要没有回归；全仓 **`208 passed, 1 warning`**。warning 始终是既有 Starlette/httpx deprecation，不影响本模块结论。
- 下一步：先由用户人工检查，再运行 `accept-module`。如要建立 `m27-v1` 真实 LLM 基线，需要单独确认 selector、调用数、成本和运行窗口；新结果从零开始解释，不与 M26 历史单一总分做升降比较。

可复制的确定性验证命令：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.agent_work/temp/pytest-m27-full
```

**本地启动体验：** M27 没有新增 Web 页面；它的入口是评测 CLI。先可无副作用查看新入口：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --help
```

你会看到 `--selector`、`--suite`、`--scenario`、`--replicate-count` 和 gate 相关参数。真实执行会调用当前配置的模型，因此在未获得新基线授权前，不要以“试一下”为由运行该 CLI；模型、检索与默认配置仍以 `docs/state/runbook.md` 为准。

## ★ M28 Text2SQL 收尾型技术体检

（2026-08-10）

**简述**：没有继续追模型分数，而是对 Text2SQL 做了一次**确定性工程收尾**：修正宽表时间语义、Eval 合同、运行级索引生命周期和测试网络隔离，确认模块可以暂时告一段落并进入 RAG。

### 先用大白话讲

这次工作像项目交付前的“查漏补缺”。功能表面上能跑，并不代表可以放心离开：可能存在一条提示把业务日期说错、一个评分规则永远无法通过、一次评测重复初始化昂贵资源，或者普通单元测试偷偷访问真实模型。

M28 没有尝试让模型再多答对几题，而是把这些**可确定证明、可本地修复**的问题清理掉。最终 Text2SQL 仍有递归查询、两阶段聚合等能力上限，但它们已经属于未来专项优化，不再阻塞 RAG 阶段。

### 这次做了什么

本模块的核心矛盾是：已有 Core/Stress 数字能提供线索，但其中混有**业务口径错误、评测假失败和运行基础设施回归**，不能直接拿失败数去调模型。于是先审计证据，再只处理确定性问题，最后用完全不访问真实 provider 的测试闭环验证。

1. **修正宽表的业务时间语义**

   原来的 QueryPlan 提示要求按 `orders_wide.snapshot_at` 过滤 6 月 GMV，但该字段实际是**抽取快照的时间**；seed 中所有记录都在 7 月 1 日抽取，因此正确照做反而会返回空结果。M28 将业务月份统一到 `paid_at`，把 `snapshot_at/batch_id` 限定为选择快照版本，并为渠道 GMV dashboard 增加 Result/Output 断言。

   这里没有新增一个看似方便的 `business_month` 字段，因为当前数据只有单批快照，贸然扩表会制造没有真实数据生命周期支撑的概念。确定性测试证明宽表与星型表的渠道 GMV 一致，也证明误用 `snapshot_at` 会得到空集；但它**没有证明真实 LLM 每次都会选对字段**。

2. **让 Eval 合同在执行前就可满足**

   旧 Schema Context 把 `refund_rate`、`avg_price` 等输出 alias 当成物理字段检查，造成 SQL 和结果正确也必然失败。M28 将合同升级为 **`m27-v3`**，明确区分物理字段、metric key 和输出 alias，并让 catalog loader 在调用 LLM 前校验表、字段、metric 是否真实存在。

   没有选择放宽 scorer、让“字段或 metric 任意命中都算过”，因为那会把错误合同变成宽松判分，继续掩盖问题。旧 v1/v2 artifact 保持只读，不能与 v3 数字直接比较；本模块也没有运行新的真实 LLM Eval，所以**尚未建立 v3 能力基线**。

3. **恢复 EvalRun 级索引生命周期**

   M27 新 runner 曾丢失 run-scoped index，一轮评测中的每道题都会重新构建 Schema vector index；在 Milvus + 在线 embedding 下，这会重复对整批 Schema 文档做 embedding，放大耗时、费用和失败面。现在由 `SQLiteRunEnvironmentFactory` 在一轮开始时构建一次，通过 FastAPI `app.state` 注入所有 Scenario，并在环境关闭时释放。

   这个设计类似 Spring 容器里的 **singleton bean 生命周期**：资源属于整轮运行，而不是某次请求。关闭时只恢复本环境接管的 override/state，不再粗暴清空全局状态。fake index 测试验证了初始化、检索和关闭边界；这证明生命周期正确，但不等于已经重新测量真实 Milvus 的性能收益。

4. **恢复全仓测试的确定性边界**

   API 默认切到新 Text2SQL 后，部分旧测试没有显式选择 legacy 路径，普通 pytest 可能意外访问 Qwen。M28 增加 autouse **provider fail-fast guard**：未显式注入 fake 的新 pipeline 调用会立即失败；旧合同测试显式 `force_new_pipeline=false`，新 pipeline 与 smoke 测试显式提供 fake client。

   最终全仓 **223 passed, 1 warning**，证明本地测试不再依赖网络、凭证和模型可用性。这个数字只能证明确定性工程回归通过，不能被包装成 Text2SQL 端到端准确率提升。

### 新概念

- **Contract satisfiability（合同可满足性）**：一条评测规则必须先能被系统的数据模型满足。例如要求“物理字段中必须出现 `avg_price`”，但数据库根本没有这个字段，这条规则就永远无法通过。M28 把这种错误提前到 catalog 加载阶段。
- **Run-scoped lifecycle（运行级生命周期）**：资源在一整轮任务开始时创建、供多次请求共享、结束时统一释放。它介于“全局永久单例”和“每次请求重建”之间，适合 Eval 的数据库快照、向量索引和 Trace 文件。
- **Hermetic test（封闭测试）**：测试结果只依赖仓库内的 fixture/fake，不依赖网络、云服务、真实密钥或模型状态。它像给单元测试拉了一条隔离带，任何意外外连都会快速暴露。

### 代码阅读路线

1. **先看业务口径入口**：`engine/nl2sql/prompt.py` 与 `docs/state/database-current-state.md`
   先理解 `paid_at` 和 `snapshot_at` 的职责差异，再看 QueryPlan 提示如何把这条规则告诉模型；阅读重点是**业务时间与数据抽取时间不能混用**。

2. **再看版本化评测合同**：`eval/contracts.py`、`eval/cases/catalog/scenarios.yaml`、`eval/catalog.py`
   `CONTRACT_VERSION` 定义当前 `m27-v3` 身份，Scenario 声明各类 assertion，loader 则在执行前做可满足性校验。这三处共同保证“合同改变就换版本、错误合同不进入运行期”。

3. **接着看资源生命周期**：`eval/environment.py`
   从 `SQLiteRunEnvironmentFactory.create()` 开始，依次看 index 构建、runtime identity、`app.state.schema_vector_index` 注入和 `close()` 恢复。重点理解为什么资源所有权放在 RunEnvironment，而不是散落在每个 Scenario 中。

4. **最后看测试隔离**：`tests/conftest.py` 与 M4/M5/M16/M18/M27 相关测试
   autouse fixture 默认禁止真实 provider；需要新 pipeline 行为的测试自行覆盖 fake，legacy 测试明确传 `force_new_pipeline=false`。这形成了“默认安全、按需显式开放”的测试边界。

核心协作链路是：

`m27-v3 catalog`
→ `静态可满足性校验`
→ `RunEnvironment 初始化一次 index`
→ `多个 Scenario 共享`
→ `typed assertions 判分`
→ `环境关闭并恢复状态`

### 设计要点

- **先修确定性问题，不继续无边界调分**：业务口径、合同和生命周期错误都能用本地证据证明，应先清理；模型能力缺口则留给未来专项实验。
- **升级合同而不是重写历史**：`m27-v3` 改变了判分语义，旧 v1/v2 artifact 继续只读，避免把不可比数字拼成趋势。
- **默认禁止测试外连**：测试需要模型行为时必须显式注入 fake，避免网络、费用和偶发超时污染日常回归。
- **边界**：Projector 完整性、Review 长期证据和 LangFuse Cloud 脱敏仍在 backlog；其中 Cloud 脱敏必须在 RAG/Hybrid 重新启用上传前完成。

### 面试怎么讲

我在 Text2SQL 阶段结束前做了一次技术体检，没有继续盲目调模型，而是从真实 Eval artifact、checkpoint、Trace 和代码路径中定位确定性问题。最终修了四类缺陷：宽表把快照时间误当业务时间、Schema Context 合同混淆物理字段和输出 alias、Eval runner 丢失运行级向量索引复用、pytest 可能意外访问真实模型。我把合同升级到 `m27-v3`，让 loader 提前检查可满足性，由 RunEnvironment 统一管理索引生命周期，并用 fail-fast guard 隔离 provider。全仓 223 个确定性测试通过，但我明确没有把它说成模型准确率提升，因为尚未运行 v3 真实 LLM 基线。

1. **[基础追问] 你怎么判断一个失败应该修合同，而不是调模型？**

   先看失败是否具有**确定性反例**。例如 `avg_price` 根本不是物理字段，但合同要求它出现在 physical fields 中，那么无论模型多强都无法通过；优惠券 GMV 的 SQL、结果和输出都正确，只因该字段检查失败，也说明问题在合同。只有排除业务口径、scorer 和运行基础设施问题后，剩余失败才适合归因到模型或计划能力。

2. **[工程/深挖追问] 为什么把向量索引放进 RunEnvironment，而不是做全局单例？**

   Eval 需要记录每轮明确的 embedding、collection、语料 hash 和 row count，全局单例容易跨 run 污染身份，也难以保证关闭时机；每题重建又成本过高。RunEnvironment 正好拥有一轮运行的开始和结束，因此能够做到**一轮一次、身份可记录、结束可释放**。

3. **[压力追问] 你做了不少工程修复，但没有新的真实模型分数，这是不是无法证明有价值？**

   这个质疑对“模型能力提升”成立，所以我没有声称准确率提高。M28 的目标是让后续分数值得相信：错误时间口径会产生空结果，错误合同会制造假失败，重复 index 会放大费用和超时，测试外连会让回归不可复现。**223 个本地测试证明的是这些确定性边界已修复**。如果未来需要发布级能力声明，再在相同 `m27-v3` 合同和完整 runtime identity 下做受控真实复测。

### 验证与下一步

- **验证**：聚焦 M27/Review/数据库 `28 passed`；legacy API/Trace `22 passed`；M18 smoke `4 passed`；new pipeline `8 passed`；全仓 **`223 passed, 1 warning in 464.31s`**。
- **Warning**：既有 Starlette/httpx deprecation，不影响 M28 结论。
- **边界**：没有运行真实 LLM Eval，没有切换模型、检索、embedding、数据库、oracle、timeout/retry 或产品 API 默认。
- **下一步**：M28 已验收（2026-08-12）；Text2SQL 可以暂时告一段落，进入 RAG。重新启用 LangFuse Cloud 前先处理 question/answer 脱敏。

可复制的确定性验证命令：

```powershell
# 全仓回归；预计看到 223 passed 和 1 条既有 deprecation warning。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.agent_work\temp\pytest-m28-full

# 只查看当前 Eval CLI 参数，不调用真实 LLM。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --help
```

**本地启动体验：** M28 没有新增独立页面，它修的是现有 Text2SQL/Eval 的正确性和工程边界。API 的启动与 Swagger 体验仍按 `docs/state/runbook.md` 执行；不要把 `eval.run_eval` 的真实运行当成本模块演示，因为它会调用当前配置的模型，必须另行明确授权。

## ★ ★ ★ Phase 3B 下半阶段总结：M20–M28

（2026-08-10）

**简述**：这一阶段没有只追求 Text2SQL 多答对几题，而是把一条“能运行但证据不够可信”的链路，逐步建设成了**索引可追溯、业务口径明确、SQL 合同可裁决、失败可归因、评测可复核**的工程系统，并在 M28 完成确定性收尾，为进入 RAG 阶段腾出了空间。

### 先用大白话讲

M20 开始时，DataPilot 已经能把自然语言转成 SQL，也有几十道 Eval 题，但当时最危险的问题不是“分数低”，而是**分数可能解释错**：Milvus collection 被重复灌入，换 embedding 后的提升可能来自脏索引；同一个业务问题在不同 case 中重复请求模型，得到的不是同一张答卷；有些规则检查的是字符串或输出列，却被报告成检索失败；模型超时后没有 SQL，仍可能被记成业务答案错误。

这就像体检仪器没有校准：继续比较药物效果，数字越多反而越容易误判。因此本阶段先校准实验环境，再统一数据库与业务事实，然后把 QueryPlan、SQL、结果、Trace 和人工复核放进同一条证据链。最终系统不仅会说“通过或失败”，还会回答：**执行到哪一步、拿到了什么证据、哪条合同没满足、是业务错误还是外部不可用、这个数字能不能与历史比较**。

阶段结束时，Text2SQL 并没有被包装成“已经完美”。递归类目、两阶段聚合、最小投影、稳定排序和复杂 Join 仍有真实能力缺口；但索引污染、时间口径、合同命名空间、资源生命周期和测试外连等确定性问题已经清理，继续无边界调分的边际收益已经不高，因而可以**暂时收尾并进入 RAG**。

### 这次做了什么

这一阶段的核心工作，可以概括为：先让实验数据可信，再让业务答案可判，最后让整个评测过程可追溯、可复核。它不是九个孤立模块的堆叠，而是一条逐层收紧“证据可信度”的主线。

1. **先修实验地基：证明实际用了什么索引、语料和 embedding**

   阶段初期发现，固定 Milvus collection 曾把约 193 份 Schema 文档重复写到约 1.9 万行。这样的 A/B 即使分数变化，也无法区分是 embedding、融合算法还是脏数据造成的。于是建立了 **collection hygiene**：实验使用唯一 collection，运行前后检查 row count、维度和 Schema 文档 hash，同一 EvalRun 复用一次索引，并把 oracle、backend、embedding、collection 与 corpus identity 写进报告。

   在 clean collection 上，retrieval-only benchmark 观察到 Qwen embedding 的 vector recall 为 **0.929**，高于 deterministic 的 **0.787**；RRF 还把 Qwen 路径的 merged recall 从 **0.738 提到 0.929**。但端到端并没有同步受益：固定 `qwen3.7-plus` 时 weighted 为 **21/32**，RRF 为 **20/32**；DeepSeek 对照中 weighted 为 **21/32**，RRF 首轮为 **18/32**。这证明了一个关键工程结论：**离线召回提升不等于最终 Text2SQL 提升**，所以默认仍保持 `inmemory + deterministic + weighted`，Milvus/Qwen embedding 只作为显式实验路径。

   没有因为某个离线指标更好就直接切默认，是因为 Text2SQL 的后半程还包含 SchemaGraph 组装、QueryPlan、SQL 生成、安全检查和结果合同。召回更多内容也可能增加噪声，把选择压力转移给模型。这个阶段真正得到的不是“某个 embedding 获胜”，而是一套以后做 RAG 检索实验也能复用的**单变量、可追溯实验纪律**。

2. **再校准业务与数据库事实：让标准答案先站得住**

   Eval 可信不只取决于模型，还取决于题面、指标、Schema 描述、reference SQL 和数据库数据是否说的是同一件事。本阶段把 MySQL 与 SQLite deterministic oracle 对齐到同一套 **14 表业务底座**，并通过确定性 seed 固化取消订单、未支付订单、一单多券、整单退款、负退款、订单头与明细金额不一致、SCD 时间重叠等反例。

   退款率、GMV、净退款额等口径被明确到可执行规则。例如商品退款率使用 completed 退款、按订单去重，并通过 `COALESCE(order_items.product_id, refunds.product_id)` 兼容整单退款；多表 Join 后统计订单必须 `COUNT(DISTINCT order_id)`；SCD 采用半开时间区间；`SRC-*` 与 `ORD-*` 属于不同编号空间，不能直接关联。reference SQL 不再只是文档示例，而是会在确定性 oracle 上真实执行并与候选结果比较。

   这一步也暴露出“标准答案自身会出错”：后来 M28 发现 `orders_wide.snapshot_at` 是抽取时间，不是业务发生时间。按旧提示查询 6 月数据会得到空集，因此最终统一为业务月份按 `paid_at`，`snapshot_at/batch_id` 只负责选择快照版本。这个修正说明，**业务语义优先于模型分数**；如果标准答案或提示错了，让模型迎合它只会把错误固化。

3. **把 QueryPlan 到 SQL 的约束从字符串升级为可解释合同**

   早期 Eval 容易把不同问题混在一起：Context 是否召回、计划是否正确、SQL 是否忠于计划、最终列是否满足 API、结果是否正确。M22 先拆出 Context、Output、Result 和 Manual 等维度，并对超出 Schema 能力的问题增加语义拒绝；M24 再用 **SQLGlot AST** 替代字符串包含检查，比较投影表达式、alias 绑定、排序方向、排序优先级和 LIMIT。

   AST 合同采用 `passed / failed / indeterminate` 三态。只有已证明安全的同一顶层 SELECT、唯一列绑定和显式 alias 才自动裁决；CTE、derived table、歧义字段或未支持语法会保守阻断，而不是猜测等价。SQL Guard 仍先做只读、RBAC 和敏感字段检查，fidelity 只证明“SQL 是否忠于已验证计划”，不能替代业务结果验证。

   受控的 Local/Milvus 六轮交错实验中，Local 为 **24/24/25**，Milvus 为 **25/25/25**；一分差不足以证明 embedding 因果收益。更有价值的发现是：历史 alias/限定名误拦被压住后，剩余问题集中到 QueryPlan 投影过宽、生成表达式不忠实和真实结果语义。这让优化方向从“继续放宽 scorer”转向了更准确的计划表达与结果合同。

4. **把失败归因从“猜原因”升级为“沿证据链定位”**

   M25 将旧 42 条 raw case 审计为 **26 个独立语义组**，避免把同一问题重复计入分母；同时把状态拆成三条正交轴：执行停在哪个 stage、root cause 属于代码/模型/检索/外部服务/Eval 合同中的哪类、业务语义是 `observed_correct`、`observed_wrong` 还是 `not_observed`。QueryPlan 和 SQL generation 的每次物理调用都记录 provider、实际模型、timeout、attempt、latency、稳定错误 subtype 和 outcome。

   一个很重要的否定实验是 retry：固定 4 条历史超时题，retry0 为 **4 次物理调用、1/4 得到有效响应、179.7 秒**；retry1 为 **8 次物理调用、0/4 有效、377.9 秒**。样本很小，不能外推整体 SLA，但足以说明“超时就默认重试一次”在当前链路中没有证据支持，因此保持 **45s、retry0**。

   M26 随后冻结历史 run 做人工 SQL 审计，而不是重新调用模型。多轮自动结果看起来接近，但人工复核发现了 **3 条自动通过、业务语义实际错误**的 SQL，例如漏 completed 退款过滤、错误处理 SCD 的 `NULL` 开放区间、漏掉 6 月 30 日生效记录。这一结果直接证明：**自动通过数不是业务正确率的同义词**，Result oracle、反事实数据和人工旁证必须共同存在。

5. **重构 Eval 的基本单位：一题一次执行，多条 typed assertion 共享证据**

   M27 将旧 formal/challenge/diagnostic 的 42 条输入、26 个旧语义组，重新整理为 **28 个 canonical Scenario**。Scenario 是唯一业务问题；Result、Output、Schema Context、QueryPlan、Trace、Safety、Expected Rejection、JoinPath、Metric Mapping 等是围绕同一张答卷的 **typed assertion**。一个 `(run, scenario, replicate)` 只调用一次 Pipeline，候选 SQL 与 reference SQL 共享同一 SQLite snapshot，所有 scorer 都读取同一份结构化 evidence。

   `Evaluator` 还引入了版本化 catalog/selector/policy/run identity、原子 checkpoint、completed artifact、`interrupted/abandoned` 生命周期和 Gate projector。Reliability 的 replicate 会先归约成一个逻辑结果，不会扩大题目或断言分母；Stress 与 Database Exception 即使复用 Scenario，也不能把数字直接相加。人工 Review bundle 是自动评分后的**旁路证据**，有来源 SHA-256、受限分类和 `insufficient_evidence` 规则，但绝不反写 EvalRun、分母或 Gate。

   M27 v1 曾把 QueryPlan timeout 后的空答卷投影成多条业务失败；v2 修正为 `external_unavailable → not_observed → Gate inconclusive`。单轮 v2 Core 观察到 required assertion **28 passed / 0 failed / 6 not_observed**，其中 17 个 Scenario 完成、2 个 QueryPlan timeout；Stress 为 **7 passed / 14 failed / 4 not_observed**，Database Exception 为 **4 / 4 / 11**。这些都是历史单轮证据，不是稳定长期基线，而且 selector 有重叠，不能相加。

6. **最后做收尾体检：只修确定性问题，不再无边界调分**

   M28 没有运行新的真实 LLM Eval，而是从 artifact、checkpoint、Trace、合同和测试路径中找出四个确定性问题：宽表业务时间误用 `snapshot_at`；Schema Context 把 metric/output alias 当物理字段；M27 新 runner 丢失 run-scoped vector index；pytest 可能意外访问真实 Qwen。四项都已修复。

   当前合同升级为 **`m27-v3`**：物理字段、metric key 与输出 alias 分开，catalog 加载时先检查合同是否能被 domain schema 满足；RunEnvironment 一轮只构建和关闭一次索引；测试默认用 provider fail-fast guard 阻止未 mock 的真实调用。最终全仓 **223 passed, 1 warning**，且没有调用真实 provider。

   这份验证证明的是工程边界已经收紧，不是模型准确率提升。当前还没有 `m27-v3` 真实 LLM 基线；旧 v1/v2 artifact 只读保留，不能与 v3 直接比较。除非要做发布级能力声明，否则没有必要为了进入 RAG 立即补跑。

### 阶段主线图

`自然语言问题`
→ `Schema Retrieval（clean corpus / hash / runtime identity）`
→ `SchemaGraph（字段、指标与 JoinPath）`
→ `QueryPlan（结构化计划）`
→ `SQL Guard（只读 / RBAC / 敏感字段）`
→ `Plan-to-SQL Fidelity（AST 保真）`
→ `SQLite/MySQL 业务事实与 Result Oracle`
→ `Scenario 的多条 typed assertion`
→ `EvalRun artifact / checkpoint`
→ `Projector / Gate / Markdown / Review bundle`
→ `证据驱动的失败归因与下一轮决策`

从实验治理角度看，则是：

`唯一 collection + corpus hash`
→ `retrieval-only 指标`
→ `端到端单变量 A/B`
→ `失败 stage / root cause / semantic status`
→ `人工审计与反事实`
→ `是否切默认或暂不采用`

### 关键知识点串联

- **Offline retrieval vs end-to-end quality**：离线召回只回答“相关 Schema 是否被找到”，端到端还取决于上下文噪声、计划、生成、安全和结果语义。M21 的 RRF 就是典型例子：召回显著提高，但最终 SQL 没有提高。
- **Scenario / assertion / evidence**：Scenario 是唯一业务题，assertion 是不同评分维度，evidence 是同一次执行留下的答卷。三者分离后，才能避免同题重复调用和跨答卷归因。
- **Oracle / counterfactual**：Oracle 是可执行的标准答案；counterfactual 是专门让错误 SQL 与正确 SQL 产生不同结果的反例数据。没有反事实，错误逻辑可能在巧合数据上通过。
- **Execution status / semantic status / Gate**：执行不可用不等于答案错误；`not_observed` 表示没有足够证据判业务能力；Gate `inconclusive` 也不等于 failed。状态正交能避免把网络超时算进模型错误。
- **Runtime identity / reproducibility**：模型名只是身份的一部分，还要记录 timeout/retry、oracle snapshot、embedding、collection、corpus hash、融合策略和索引复用方式，才知道两轮是否真的可比。
- **AST contract / conservative validation**：SQLGlot AST 能看懂表达式结构，但不应被扩成通用 SQL 证明器。对未知 scope 返回 `indeterminate`，比宽松放过一个可能错误的 SQL 更符合安全与评测可信度。
- **Hermetic test / external Eval**：单元测试必须封闭、快速、无费用；真实 LLM Eval 则天然有网络和采样波动。两者分开，才能既保证日常回归稳定，又诚实记录线上能力证据。

### 阶段设计取舍

- **不因单次高分切默认**：Qwen、Milvus、RRF 和不同 embedding 都出现过局部优势，但样本少、LLM 非确定、合同还在演进。默认只在同合同、多轮、单变量证据下讨论切换。
- **不把检索标签泄漏进线上链路**：`expected_tables`、`expected_columns`、metric/relation 标注只用于离线评分，不能参与 retriever/reranker，否则得到的是“看过答案的高分”。
- **不重写历史分数**：合同版本改变时升级版本，旧 report/artifact 只读保留。历史数字用于解释演进，不能伪装成同一排行榜。
- **不让 scorer 猜业务等价**：AST 只实现有正反例支持的窄等价；结果、输出、计划和 Context 各自裁决，避免一个宽松规则同时掩盖多类错误。
- **不把人工复核变成自动 Gate**：Review bundle 提供旁证和错因分类，但自动评测与人工意见保持独立，防止人工结论悄悄改变 CI 分母。
- **不为进入 RAG 强行补 v3 分数**：M28 的确定性问题已闭环；没有 v3 真实基线是“尚未复测”，不是“代码没收尾”。需要发布级声明时再按新合同受控运行。

### 面试怎么讲

我负责了 DataPilot Phase 3B 下半阶段的 Text2SQL 工程化与评测可信度建设。项目最初已经能生成 SQL，但实验存在 Milvus 重复灌库、业务口径不统一、同题重复调用、字符串 scorer 误判、超时被当成业务失败等问题。我先治理向量索引和 runtime identity，再把 14 表数据库事实、退款/SCD/金额口径与 deterministic oracle 对齐；随后用 SQLGlot AST 建立 QueryPlan-to-SQL 保真合同，并把 42 条旧 case 重构为 28 个 canonical Scenario，每题只执行一次，由 Result、Output、Context、Plan、Trace、Safety 等 typed assertion 共享同一份证据和数据库 snapshot。评测运行支持 checkpoint、版本化 artifact、Gate 和独立人工 Review，还通过反事实数据发现了自动通过但业务错误的 SQL。最终 M28 修复宽表时间、合同可满足性、运行级索引复用和测试外连，完成 223 个确定性测试。整个阶段最重要的成果不是把某个单轮分数调高，而是让后续每个分数都能解释、复现和审计，并据此判断 Text2SQL 可以暂时收尾、进入 RAG。

可用于简历的一句话是：

> **围绕企业 Text2SQL 构建可追溯 EvalOps-lite：治理 Milvus 索引污染与运行身份，统一 14 表业务 oracle，以 SQLGlot AST 和 28 个 canonical Scenario/typed assertions 实现一题一次执行、共享快照评分、失败归因、checkpoint 与人工旁路复核，完成 223 项确定性回归。**

1. **[基础追问] 这一阶段为什么没有把“准确率提升”作为唯一目标？**

   因为当实验地基、业务口径和评分合同不可信时，准确率变化没有明确含义。重复灌库可能制造检索假提升，错误 reference SQL 会奖励错误答案，timeout 误投影会把外部不可用算成模型失败。本阶段先保证数字能被解释，再决定是否调模型；这比追一个无法复现的高分更有工程价值。

2. **[基础追问] 你怎么判断 Text2SQL 已经可以暂时收尾？**

   我看三类条件：第一，已发现的确定性 P0 问题是否关闭，包括业务时间、合同可满足性、索引生命周期和测试隔离；第二，剩余失败是否已经能归类，而不是仍混着工具 bug；第三，继续优化是否有明确、高价值入口。M28 后前两项已满足，剩余递归、两阶段聚合、输出稳定性等问题也有清晰切入口，但不阻塞系统进入 RAG，因此适合阶段性收尾。

3. **[工程/深挖追问] 离线检索 recall 提升到 0.929，为什么仍不切 Qwen embedding 和 RRF？**

   recall 只证明目标 Schema 文档更容易进入候选集，不证明模型能从更多上下文中做出更好的计划。受控端到端实验里，RRF 在 Qwen plus 下反而从 21/32 变成 20/32；Local/Milvus 的多轮差异也只有约一题，无法隔离 LLM 波动。因此我保留它们为显式实验路径，默认选择成本低、可复现的 deterministic/weighted，等未来有同合同、多轮、单变量证据再切换。

4. **[工程/深挖追问] 为什么 M27 要重构成 Scenario + typed assertion，而不是继续补旧 scorer？**

   旧结构把一个 check 当成一道题，同一个业务问题为了检查 Result、Plan 和 Trace 会重复调用模型；不同 scorer 看到的可能是不同 SQL，归因天然不可信。新结构让 Scenario 只执行一次，多条纯 scorer 读取同一 evidence 和 snapshot；selector 只选择题，不复制题；replicate 只衡量可靠性，不扩大逻辑分母。这样复杂度集中在一个清晰的 `Evaluator` seam 中，而不是继续散落补丁。

5. **[工程/深挖追问] 你如何避免 Eval 自己“测错了还很自信”？**

   我用了四层防线：合同加载时检查字段和 metric 可满足；reference SQL 在 deterministic oracle 上真实执行；关键业务规则用 counterfactual fixture 区分正确与错误 SQL；最后用 Review bundle 对高风险自动通过样本做人工旁证。M26 人工审查找出的 3 条 false pass，正说明任何单层 scorer 都不够。

6. **[压力追问] 你做了大量评测基础设施，但最终没有正式 v3 基线，这是不是过度设计？**

   这个质疑对“已经证明模型更强”是成立的，我没有做这种声明。但本阶段发现的都是会直接扭曲结论的问题：脏 collection、错误时间字段、不可满足合同、超时假失败和测试真实外连。如果不解决，跑更多基线只是在扩大错误证据。当前 v3 没有真实基线是明确边界；当需要发布级能力声明时，可以在可信合同和完整 runtime identity 下直接运行，而不用再次重建评测地基。

7. **[压力追问] 223 个测试通过，为什么不能说 Text2SQL 已经稳定？**

   因为这 223 个是 deterministic regression，证明代码、合同、fixture、生命周期和测试隔离稳定；它们不包含真实 LLM 的采样、网络、端点延迟和长提示行为。真实 v2 Core 仍有两题 QueryPlan timeout，Stress 也暴露递归和两阶段聚合能力缺口。工程稳定性与模型能力稳定性必须分别报告。

8. **[压力追问] 既然 Stress 还有 14 条 failed，为什么不继续修完再做 RAG？**

   首先，14 条 assertion failed 不等于 14 道独立业务题失败，其中有输出 alias、tie-break、投影和同一 Scenario 的多维断言；Database Exception 还与 Stress 复用 Scenario，不能相加。其次，M28 已把确定性假失败清理并将真实缺口定位到递归计划、嵌套聚合和输出合同。这些适合未来专项优化，但项目目标还包括文档问答和混合推理；继续只优化 SQL 会推迟更关键的系统闭环，因此现在进入 RAG 是范围和收益上的主动取舍。

### 阶段成果与边界

- **完成了实验可信度治理**：clean/unique Milvus collection、row count/dimension/hash 校验、run-scoped index 与完整 runtime identity。
- **完成了业务事实对齐**：14 表数据库、确定性 seed、退款/SCD/金额/时间/Join 规则与可执行 oracle。
- **完成了计划与 SQL 合同化**：QueryPlan 结构化证据、SQLGlot AST fidelity、Output/Result/Context/Safety 等分层裁决。
- **完成了失败证据链**：调用 attempt、稳定错误 subtype、execution/root-cause/semantic 三轴归因，以及 external unavailable 的 `not_observed` 语义。
- **完成了新 Eval 架构**：28 个 canonical Scenario、一题一次执行、多 typed assertion、共享 snapshot、selector、projector、Gate、checkpoint、artifact 与 Review 旁路。
- **完成了确定性收尾**：`m27-v3` 合同、宽表时间修复、索引生命周期恢复、provider fail-fast guard；全仓 **223 passed, 1 warning**。
- **没有完成、也没有假装完成**：当前没有正式长期 Text2SQL baseline，也没有 `m27-v3` 真实 LLM run；旧 v1/v2 数字只作历史解释。
- **刻意没有切换**：默认模型仍为 Qwen `qwen3.7-plus`，默认检索仍为 `inmemory + deterministic + weighted`，timeout/retry 仍为 45s/0；单轮 A/B 不触发默认变更。
- **仍有能力边界**：递归类目、两阶段聚合、最小投影、稳定 tie-break、复杂 JoinPath 和 QueryPlan 延迟，留作未来 Text2SQL 专项。
- **仍有基础设施 backlog**：Projector closed-world 完整性、Review 长期证据保留、catalog provenance 与 LangFuse Cloud 脱敏；其中 Cloud 脱敏应在重新启用上传前处理。

### 下一阶段怎么接

下一阶段进入 **RAG** 时，可以直接复用这一阶段形成的方法，而不是从“调 embedding 参数”重新开始：

1. **先定义 RAG 的业务合同**：哪些问题只查文档、哪些必须引用证据、哪些允许 SQL+文档混合；把 unsupported request 和安全边界写清楚。
2. **建立可追溯语料身份**：记录文档版本、chunk 策略、embedding、collection 与 corpus hash，延续 M20 的 clean index 纪律。
3. **分开离线与端到端指标**：离线评 retrieval recall，端到端评 answer correctness、citation/faithfulness 和拒答；不把召回提升直接当答案提升。
4. **沿用 Scenario + typed assertion**：一个知识问题执行一次，由 retrieval、citation、faithfulness、output 和 safety assertion 共享证据，避免重复调用和分母膨胀。
5. **最后再接 Router / Hybrid**：先分别把 Text2SQL 与 RAG 的能力、证据和失败状态说清楚，再评 SQL、RAG、Hybrid 路由是否选对；不要用一个总分掩盖不同链路。
6. **重新启用 LangFuse Cloud 前先做脱敏**：本地 JSONL 可以保留调试材料，但上传 question/answer/document chunk 前要建立统一 allowlist/redaction，避免把业务内容直接送入云端。

这意味着 Phase 3B 下半阶段留下的不只是一个 Text2SQL 模块，而是一套可以继续支撑 **RAG、Hybrid Agent 与后续 EvalOps** 的工程方法：先保证事实与证据可信，再讨论模型和策略优化。
