# DataPilot AI Context Changelog — Phase 2

> 本文件保存 Phase 2 的完整模块档案、实验记录和历史取舍，按时间倒序排列。当前项目状态以 `docs/state/AI_CONTEXT.md` 为准；跨阶段索引见 `docs/state/CHANGELOG_INDEX.md`。
>
> 默认先按模块号、日期或关键词定位，再读取相关章节，不要无差别全文读取。新结论修正本阶段旧判断时，应在旧条目原位添加 `⚠️ 注`。

## 变更记录（新的在上）

### Phase 2.7.1 数据库 polish（2026-07-22）

- 背景：外部 AI 对 Phase 2.7 审查后指出若干 plan v5 与实现偏差。本轮不重开 Phase 3A M8，只处理进入 M8 前值得补齐且低扰动的数据库口径问题。
- 改动范围：`app/models/orders_wide.py`、`app/models/coupons.py`、`app/models/product_price_history.py`、`alembic/versions/20260722_0003_phase27_database_polish.py`、`scripts/seed_data.py`、`tests/test_m1_models.py`、`domain_pack/schema_desc/{orders_wide,coupons,product_price_history,user_behavior_log}.md`、`docs/state/database-current-state.md`、`.agent_work/temp/phase2.7.1-notes.md`
- 关键决策：
  - `orders_wide` 不重命名旧字段，保留 `product_name/category/user_status` 等已通过用例依赖的兼容列；仅追加 plan v5 需要的 `user_role`、`primary_product_price`、`item_count`、`refund_count`、`total_refund`、`has_refund`、`updated_at`，让宽表具备“看板预聚合 vs 星型强一致”的后续挑战价值。
  - `user_behavior_log` 不回退到 `target_type/target_id` 多态列；当前显式 `product_id/channel_id` 外键更适合参照完整性和 Text2SQL join path，偏离理由写入 schema_desc 和数据库速查。
  - `coupons` 补 `ix_valid_range(valid_from, valid_to)`，服务优惠券有效期查询；`coupon_code VARCHAR(64)` 保持不动，属于无害兼容差异。
  - `product_price_history` 追加 `change_reason`，同时保留 `price_source`。前者是业务调价原因，后者是数据来源元数据，两者不要混用。
  - seed 仍然保持确定性生成：宽表退款字段从 `order.refunds` 聚合，明细行数从 `order.order_items` 计算；没有逐行写死 10000 行数据，也不依赖自增 ID 从 1 开始。
- 参考资料：未查阅外部参考；本次按外部 AI 对 Phase 2.7 的审查意见和 `docs/database-upgrade-plan-v5.md` 口径补齐偏差，调整范围限定在 3 个 ORM 模型 + 1 条 migration + seed + 4 份 schema_desc + 数据库速查。
- 验证快照：
  - 聚焦 pytest：`tests/test_m1_models.py tests/test_database_upgrade.py` 7 passed
  - 真实 MySQL：`alembic current` 从 `20260722_0002` 升级到 `20260722_0003 (head)`；`alembic check` 输出 `No new upgrade operations detected.`
  - `python -m scripts.seed_data --reset` 成功；14 表行数保持 users 200 / orders 10000 / order_items 18000 / refunds 1000 / product_price_history 150 / orders_wide 10000 等既定数量
  - 固定事实保持不变：2026 年 6 月 GMV `11285752.00`、Aurora 退款率最高、Mobile App GMV Top、Top 退款原因 `quality_issue`、高优 pending 工单 12、金额不一致订单 5
  - 新增字段抽查：`orders_wide` 中 `has_refund=1` 的订单 1000 笔，`sum(refund_count)=1000`，`sum(total_refund)=893612.80`，`max(item_count)=3`；`product_price_history.change_reason` 分布为 current_price 48 / new_year_clearance 50 / spring_price_restore 50 / summer_price_refresh 2；MySQL `coupons` 上存在 `ix_valid_range`
  - 全量 pytest：31 passed, 1 warning（Starlette TestClient / httpx deprecation，既有警告）
- 遗留：
  - 本轮 polish 是 Phase 2.7 验收后的补强，建议新会话复审时重点看 `0003` migration 与文档口径是否一致；不要求 Phase 3A trace_steps 通过。
  - `resources.py` 模块 docstring 位置仍是已知 cosmetic issue，未在本轮扩大处理。

### Phase 2.7 数据库升级（2026-07-22）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`app/models/*`、`app/db/base.py`、`app/schemas/resources.py`、`alembic/versions/20260722_0002_database_upgrade_14_tables.py`、`scripts/seed_data.py`、`domain_pack/schema_desc/*`、`domain_pack/metrics.yaml`、`domain_pack/sql_examples/basic.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-regression.yaml`、`tests/test_m1_models.py`、`tests/test_database_upgrade.py`、`tests/test_m5_agent_response.py`、`docs/phase3a-plan.md`、`.agent_work/temp/database-upgrade-notes.md`、`.agent_work/temp/database-upgrade-seed-summary.md`
- 关键决策：
  - 按 `docs/database-upgrade-plan-v5.md` 一次性将 7 表数据底座升级为 14 张物理表：新增 `product_categories`、`order_items`、`coupons`、`order_coupons`、`user_behavior_log`、`product_price_history`、`orders_wide`；旧表增补 `products.category_id`、`orders.source_order_no/external_order_no/shipping_amount/discount_amount/actual_amount`、`orders.paid_at nullable`、`refunds.source_order_no/order_item_id`
  - 兼容阶段二旧链路：保留 `orders.product_id` 和 `products.category`，让 M2 API、M3/M4 模板 SQL、M6 smoke 继续运行；新指标口径在 `metrics.yaml` / schema_desc 中声明商品维度默认走 `order_items`
  - Seed 不依赖自增 ID 从 1 开始：外键用 ORM 对象关系，固定事实用 `sku/coupon_code/channel_code/category/device_type` 等稳定业务键定位；不把 10000 行数据逐行写死
  - 数据质量彩蛋不破坏主表外键 / 唯一约束：重复源单号放在 `source_order_no/external_order_no`，弱关联退款放在 `refunds.source_order_no`，金额不一致控制为 5 条可解释样例
  - MySQL downgrade 按真实 DDL 行为修正：新表整表 drop 优先，避免外键索引逐个 drop 被拦截；回滚旧 `orders.paid_at NOT NULL` 前先回填 NULL；`coupons.coupon_code` 只保留 unique constraint，避免 Alembic metadata diff
- 参考资料：未查阅外部参考；本次按 `database-upgrade-plan-v5.md`、现有 M1-M6 ORM / seed / eval 结构和用户明确约束实现，没有启动 Phase 3A M8，也没有提前实现 `schema_retrieval` / `query_plan` / `trace_steps`
- 验证快照：
  - 真实 MySQL migration：完整 `alembic downgrade 20260717_0001` -> `alembic upgrade head` -> `python -m scripts.seed_data --reset` 通过；最终 `alembic current` = `20260722_0002 (head)`，`alembic check` 无新增操作
  - Seed 行数：users 200 / product_categories 15 / products 50 / channels 6 / orders 10000 / order_items 18000 / refunds 1000 / tickets 300 / knowledge_docs 10 / coupons 10 / order_coupons 3000 / user_behavior_log 10000 / product_price_history 150 / orders_wide 10000
  - 固定事实：GMV 11285752.00；Aurora 仍为 6 月退款率最高商品；Mobile App 仍为 6 月 GMV Top 渠道；Top 退款原因 `quality_issue`；待处理高优先级工单 12；`JUNE_FIXED_50` 在 Mobile App 使用最多；数码电子一级类目 GMV Top；Aurora 6 月历史均价 899.00；`mobile_app` 设备转化率最高；宽表与星型渠道 GMV 一致；金额不一致订单 5 条
  - 自动化：`pytest` 全量 31 passed, 1 warning；M6 smoke `python -m eval.run_eval --cases eval/cases/smoke.yaml ...` 6/6 passed；`git diff --check` 无 whitespace error，仅 Windows CRLF 提示
- 遗留：
  - Phase 2.7 当前为“已完成（未验收）”，等待用户人工检查后可调用 `accept-module`
  - Phase 3A M8 后续直接基于升级后的 14 表新库跑 baseline；`eval/cases/database-upgrade-challenge.yaml` 只作为数据库升级挑战集和困难诊断素材，不替代 `phase3a-regression.yaml` 的 10 条正式回归
  - `app.db.base` / `app.models` 循环导入规避方式仍沿用既有约定；本次 seed 命令行入口通过先导入 `app.db.base` 避坑，后续若重构可拆 `base_class.py`

### M6 EvalOps-lite 与演示收尾（2026-07-20）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/cases/smoke.yaml`、`eval/run_eval.py`、`eval/reports/latest.md`、`eval/reports/phase2-v1-acceptance.md`、`demo/streamlit_app.py`、`README.md`、`.agent_work/temp/m6-notes.md`、`.agent_work/temp/m6-eval-traces.jsonl`
- 关键决策：
  - 用户确认 Eval 执行方式选择 FastAPI `/api/query`：可选方案是直接调用本地 pipeline，风险是绕过 API 契约；最终选择 API seam，默认用 `TestClient` + 内存 SQLite seed 调真实路由，避免写 MySQL 主库，同时验证 AgentResponse、trace、SQL Tool 和 chart_spec
  - 用户确认 Streamlit 只做最小演示闭环：可选方案是增加复杂筛选和历史记录，风险是 M6 扩大成 UI 大模块；最终只展示 answer / SQL / table / chart / safety_status / trace_id / tool trace
  - 用户确认阶段二验收报告写 v0/v1 能力清单，但自动化评测只覆盖 6 条 smoke：可选方案是只写 smoke 或拉全量 32 条，最终选择“能力清单 + 6 条自动化 smoke”，不把 RAG/hybrid 尚未实现能力写成已完成
  - smoke multi-table 用例从 `join_005` 调整到 `join_002`：`join_005` 会被现有“渠道 + 订单量”模板提前命中，缺 `gmv`；`join_001` 会被“退款 + 原因”模板命中。`join_002` 能稳定走 LLM 三表 join，命中 `channels/orders/refunds`
- 参考资料：未查阅外部参考；本次按 phase2-plan M6、`eval/cases_plan.md` YAML 字段草案、M5 AgentResponse / Trace 契约实现；没有照搬 `QueryMind`、`hello-agents/ch12` 或 `databao-agent`
- 验证快照：
  - `py_compile`：`eval/run_eval.py`、`demo/streamlit_app.py` 编译通过
  - pytest：首次使用默认 `.agent_work/temp/pytest-tmp` 时，旧 basetemp 删除失败触发 Windows `PermissionError`；改用 `--basetemp=.agent_work/temp/pytest-m6-tmp-final` 后 `27 passed, 1 warning`
  - EvalOps-lite：`python -m eval.run_eval` 通过，`6/6 passed`；覆盖 `sql_001/sql_006/agg_001/agg_002/join_002/sec_001`，报告写入 `eval/reports/latest.md`，临时 trace 写入 `.agent_work/temp/m6-eval-traces.jsonl`
  - Streamlit/API smoke：现有 FastAPI `http://127.0.0.1:8000/health` 返回 `ok`；`streamlit run demo/streamlit_app.py --server.port 8501` 页面 HTTP 200；通过真实 API 查询“各渠道订单量是多少？”返回 answer、SQL、rows、chart_spec、tool_calls、trace_id
  - `git diff --check`：仅 README 的 LF→CRLF 提示，无 whitespace error
- 遗留：
  - M6 未调用 accept-module，等待用户人工检查后再跑最终验收门
  - 阶段三接 RAG / Hybrid：以 `domain_pack/kb_docs/` 和 `knowledge_docs` 为语料入口，新增 RAG/hybrid YAML 后继续复用 AgentResponse 字段
  - EvalOps-lite 当前只做 smoke 级检查；完整 32 条评测、RAG 指标和历史聚合留到后续 EvalOps 扩展

### M5 AgentResponse 扩展、Trace、Tool 与图表（2026-07-20）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`app/schemas/agent.py`、`app/api/query.py`、`engine/tools/*`、`engine/trace/*`、`domain_pack/chart_templates/basic.yaml`、`tests/test_m5_agent_response.py`、`scripts/smoke_m5_agent_response.py`、`README.md`、`.agent_work/temp/m5-notes.md`、`.agent_work/temp/m5-smoke.md`、`.agent_work/temp/m5-traces.jsonl`
- 关键决策：
  - Trace 存储按用户确认走 JSONL 主路径：`eval/traces/traces.jsonl` 是正式 trace 默认位置，测试 / smoke 可通过 `app.state.trace_path` 指到临时文件；M5 不引入 SQLite Trace 表或 repository 抽象，避免扩大数据库和评测结构范围
  - SQL 执行迁入 `engine/tools/sql_tool.py`：`/api/query` 不再直接 `db.execute()`，而是通过 SQL Tool 统一做 SQL Guard policy、`tables_used` 提取、数据库执行、耗时统计和 `tool_calls` 记录
  - AgentResponse 只增量扩展旧契约：保留 M3/M4 的 `route/answer/sql/columns/rows/safety_status/blocked_reason/trace_id` 含义，新增 `CostInfo`、`ToolCallTrace`、`tables_used`、`docs_used`、`chart_spec`、`error_type`
  - 图表只做轻量规则：`domain_pack/chart_templates/basic.yaml` 保存 bar / line / horizontal_bar 模板；`chart_tool` 根据结果形状和问题关键词生成 Vega-Lite 兼容 spec，无法判断时返回 `None`，不影响主答案
- 参考资料：未查阅外部参考；本次按 phase2-plan M5 范围、M4 安全链路、用户确认的 JSONL Trace 方案和既有模板 SQL 聚合结果实现
- 验证快照：
  - TDD 红灯：`pytest tests\test_m5_agent_response.py -p no:cacheprovider` 首次失败于响应缺 `docs_used/chart_spec`，符合 M5 契约缺口预期；后续新增图表测试先失败于退款率问题误选 `refund_count`，已改为按问题关键词优先选择 `refund_rate`
  - M5 聚焦测试：`3 passed, 1 warning`（Starlette/httpx TestClient 提示，不影响本模块）
  - M3/M4 回归：`9 passed, 1 warning`
  - 全量 pytest：`27 passed, 1 warning`
  - M5 smoke：`scripts\smoke_m5_agent_response.py` 4/4 通过；覆盖渠道订单量 `bar/order_count`、商品退款率横向 `bar/refund_rate`、GMV 单指标 `bar/gmv`、危险 SQL 拦截；摘要写入 `.agent_work/temp/m5-smoke.md`，临时 trace 写入 `.agent_work/temp/m5-traces.jsonl` 且 `trace_lines=4`
  - Alembic：`alembic check` 无新增操作；`alembic current` = `20260717_0001 (head)`
  - `git diff --check`：仅 README / app/api/query.py / app/schemas/agent.py 的 CRLF 提示，无 whitespace error
- 遗留：
  - M6 接 EvalOps-lite：从 `eval/cases_plan.md` 抽 smoke YAML，用 M5 AgentResponse / trace 字段记录 pass-fail / error_type
  - `CostInfo.model/prompt_tokens/completion_tokens` 当前仍为 `None/0/0`；后续若需要真实 LLM usage，需要扩展 provider 返回 usage，但不改变响应字段
  - 图表规则只覆盖基础 bar / line / horizontal_bar 和 GMV 单指标，不做复杂图表推荐；复杂可视化留到演示页或后续阶段

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

