# DataPilot AI Context（技术档案）

> 续接任务、查 bug 读这个。记录 git 和代码里查不到的信息：为什么这么做、验证过什么、有什么坑等。硬约束见 CLAUDE.md/AGENTS.md（自动加载），任务见当前阶段计划文件（现指向见下方「当前状态」），均不在此重复。用户学习复盘见 dev-log.md。「当前状态」「已知的坑」保持最新；「模块技术档案」「补充记录」只追加不改写。

## 当前状态（唯一权威出处）

- 当前阶段计划文件：`docs/phase3a-plan.md`
- 当前模块：Phase 3A M8 回归基线冻结（已完成，待 accept-module）
- 上一模块验收：Phase 3A M8 未验收（待 accept-module）
- 阻塞项：无；旧链路 formal baseline 允许类 SQL 为 6/8，challenge baseline 为 11/16，已按用户确认作为真实 baseline 冻结
- 更新时间：2026-07-22

## 当前技术选型快照

- 后端框架：FastAPI + Pydantic Schema；`/api/query` 使用结构化 `AgentResponse`
- 数据库主路径：MySQL `datapilot_dev` + SQLAlchemy ORM + Alembic migration；SQLite 仅用于测试 / smoke
- 数据库状态速查：`docs/database-current-state.md` 记录 Phase 2.7 后 14 表清单、指标口径、固定 seed 事实和后续写 plan 注意事项
- 数据准备：`scripts/seed_data.py` 写入确定性电商 / SaaS 运营数据和固定业务事实
- NL2SQL：M3 模板 SQL 优先；M4 起模板未命中时走 DeepSeek，Schema / KPI / few-shot 从 `domain_pack/` 加载
- SQL 安全：sqlglot AST 只读检查 + 表级 RBAC + `users.email/users.phone` 敏感字段策略；安全能力不只靠 prompt
- Agent 编排：Phase 2 先用普通 Python pipeline，不上复杂 LangGraph；字段按未来 graph state 预留；后续进入多步骤 Agent / RAG 编排时，可在不改响应契约的前提下迁移到 LangGraph。
- Trace / Eval：Agent Trace 默认写 JSONL 到 `eval/traces/traces.jsonl`；M6 EvalOps-lite 已复用 AgentResponse / trace 字段跑 6 条 SQL smoke；JSONL 默认不提交；后续如需查询和聚合，可迁移到 SQLite 或独立 EvalOps 平台
- 图表：后端输出 Vega-Lite 兼容 `chart_spec`，当前仅覆盖基础 bar / line / horizontal_bar 和单指标柱图
- 演示：M6 已提供 `demo/streamlit_app.py` 最小演示控制台，通过 HTTP 调用 `/api/query` 展示 answer / SQL / table / chart / trace

## 已知的坑（活跃列表，过期即删）

- `app.db.base` 目前同时定义 `Base` 又导入所有模型来注册 Alembic metadata；如果业务代码先从 `app.models` 聚合包导入模型，可能触发循环导入。当前规避方式：API / 工具层优先沿用 `app.db.base` 暴露的模型导入路径；后续若重构，可拆 `app/db/base_class.py`（只放 Base）和 `app/db/base.py`（只汇总 metadata）
- Windows 下 `.agent_work/temp/pytest-tmp` 偶发被旧 pytest 临时目录锁住，表现为 `PermissionError` 删除 basetemp 失败；遇到时不要改业务代码，改用新的 `--basetemp=.agent_work/temp/<name>` 复跑即可。本次 M6 已用 `pytest-m6-tmp-final` 验证通过
- DB comment 在 PowerShell 离线 SQL 输出中乱码；在线迁移和建表正常，无害。如需导出 SQL文件，再统一处理输出编码或将 DB comment 改为 ASCII（M1）
- 工作树可能有用户或其他工具留下的未提交改动；动文件前先 `git status --short`，不要回滚非本次任务的改动

## 模块技术档案（新的在上）

### Phase 3A M8 回归基线冻结（2026-07-22）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/run_eval.py`、`tests/test_phase3a_eval.py`、`eval/reports/phase3a-baseline.md`、`eval/reports/phase3a-challenge-baseline.md`、`docs/phase3a-plan.md`、`docs/database-current-state.md`、`.agent_work/temp/m8-notes.md`、`.agent_work/temp/phase3a-baseline-traces.jsonl`、`.agent_work/temp/phase3a-challenge-baseline-traces.jsonl`
- 关键决策：
  - M8 只扩展 EvalOps-lite 的 case 结构和 baseline 报告，不引入新 Text2SQL pipeline、Schema Retrieval、QueryPlanStep 或 trace_steps，避免把 M9-M12 的工作提前倒灌。
  - `EvalCase` 前向兼容 `expected_metrics`、`expected_trace_steps`、`pipeline_mode`，但旧 `smoke.yaml` 默认仍是 `pipeline_mode=baseline`，旧 M6 smoke 不需要补新字段。
  - `_score_case()` 从 tuple 改为 `EvalScore`，新增最小 `issue_tags`：`missing_table`、`missing_column`、`safety_mismatch`、`unexpected_error`；补充轻量 `manual` 语义，困难诊断题无论通过或失败都可在报告中标记 `review_required`。这只服务 baseline 和后续对照报告，不扩展成完整 scorer 平台。
  - 10 条 formal 与 16 条 challenge 的最终口径：10 条 formal 是主硬门；16 条 challenge 是 superset，包含 10 条 formal question，额外 6 条用于扩展数据库复杂度诊断。后续每个模块同步跑两套报告。
  - 用户确认：baseline 首轮结果为 8/10 overall、2/2 security blocked、允许类 SQL 6/8；可选项是 ① 按真实 baseline 继续收工整理、② 调整 regression expected columns、③ 先修旧链路别名再重跑。风险分别是保留低于计划门槛的真实旧链路事实、可能弱化后续对照硬门、可能扩大 M8 到旧链路修复。我的建议是选 ①，用户最终确认选 ①。
- 参考资料：未查阅外部参考；本次按 `docs/phase3a-plan.md` M8、`docs/database-current-state.md`、`domain_pack/schema_desc/relations.yaml`、`domain_pack/metrics.yaml` 和现有 M6 eval runner 实现，没有照搬参考项目。
- 验证快照：
  - TDD 红灯：`pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8-red` 首次 1 passed / 3 failed，失败点为 `EvalCase` 缺 M8 字段、`_score_case` 仍返回 tuple、报告不能接收 issue tags，符合预期。
  - 聚焦 pytest：`pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8-final-align` 7 passed, 1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - 旧 smoke 兼容：`python -m eval.run_eval --cases eval/cases/smoke.yaml --report .agent_work/temp/m8-smoke-compat.md --trace .agent_work/temp/m8-smoke-compat-traces.jsonl` 6/6 passed。
  - M8 formal baseline：`python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-baseline.md --trace .agent_work/temp/phase3a-baseline-traces.jsonl` 8/10 passed；安全 2/2 blocked；允许类 SQL 6/8 passed。
  - M8 challenge baseline：`python -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --report eval/reports/phase3a-challenge-baseline.md --trace .agent_work/temp/phase3a-challenge-baseline-traces.jsonl` 11/16 passed；安全 2/2 blocked；`db_hard_001` / `db_hard_003` 失败且 `review_required=True`。
  - baseline 失败明细：`p3a_multi_001` 生成 `order_count`，case 期望 `coupon_order_count`；`p3a_multi_003` 生成 `category_name`，case 期望 `category`；均记录为 `missing_column`。
- 遗留：
  - M8 不修改 regression / challenge case，也不修旧链路别名；后续 M9-M12 应以 `eval/reports/phase3a-baseline.md` 和 `eval/reports/phase3a-challenge-baseline.md` 的真实失败点证明新 pipeline 的 schema / plan / prompt 改进价值。
  - `expected_trace_steps` 字段已可加载，但 trace_steps 结构仍属于 M11，不要误判为 M8 已实现。

### Phase 2.7.1 数据库 polish（2026-07-22）

- 背景：外部 AI 对 Phase 2.7 审查后指出若干 plan v5 与实现偏差。本轮不重开 Phase 3A M8，只处理进入 M8 前值得补齐且低扰动的数据库口径问题。
- 改动范围：`app/models/orders_wide.py`、`app/models/coupons.py`、`app/models/product_price_history.py`、`alembic/versions/20260722_0003_phase27_database_polish.py`、`scripts/seed_data.py`、`tests/test_m1_models.py`、`domain_pack/schema_desc/{orders_wide,coupons,product_price_history,user_behavior_log}.md`、`docs/database-current-state.md`、`.agent_work/temp/phase2.7.1-notes.md`
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

## 补充记录（小修补，新的在上）

- 2026-07-22 Phase 2.7.1 验收完成、plan v5 归档、切入 Phase 3A M8：① 将 `docs/database-upgrade-plan-v5.md` 归档至 `docs/archive/`；② 补全 AI_CONTEXT Phase 2.7.1 模块档案的「参考资料」小节；③ 当前阶段计划文件切换为 `docs/phase3a-plan.md`，当前模块改为 Phase 3A M8；④ 上一模块验收更新为 Phase 2.7.1 已验收。
- 2026-07-22 Phase 2.7.1 验收未通过（accept-Phase2.7.1-20260722.md）：7 项检查中 2 项 ❌。检查 3 进度状态不一致（plan v5 已移至 archive 但 AI_CONTEXT 仍指向原路径；dev-log Phase 2.7 下一步指针过时未指向 2.7.1）；检查 4 最新日志不完整（AI_CONTEXT 2.7.1 模块档案缺「参考资料」小节；dev-log 无 2.7.1 条目）。其余 5 项 ✅（废弃口径清零、目录地图一致、注释合规、单一事实源抽查 4 项一致、pytest 31 passed）。待用户修复 ❌ 项后复检。
- 2026-07-22 seed 用户姓名真实感小修：按用户反馈，`scripts/seed_data.py` 不再用 50 个基础姓名追加 `02/03/04` 后缀生成 200 用户，改为固定 200 个姓名池，包含二字名、三字名和少量英文名；保留邮箱 / 手机号唯一性和角色分布。执行 `seed --reset` 时发现 MySQL 自引用类目树会拦截 `DELETE FROM product_categories`，已在 reset 前先断开 `ProductCategory.parent_id` 再删除。验证：`python -m scripts.seed_data --reset` 成功，14 表行数和固定事实全部匹配；数据库前 12 个用户已为新姓名 + `user001...` 邮箱；`pytest tests/test_database_upgrade.py tests/test_m1_models.py` 7 passed。
- 2026-07-22 Phase 3A 计划对齐 Phase 2.7 已验收状态：按用户确认修改 `docs/phase3a-plan.md`，将顶部「数据库升级先行」改为「Phase 2.7 数据库升级已完成」，补入 `docs/database-current-state.md` 为单一事实源入口；M8 从“新建 regression / 从 32 条候选抽样”改为“校验现有 10 条新库 regression 并冻结 baseline”；目录规划把 `eval/cases/phase3a-regression.yaml` 标为已有/校验；M9 JoinPath 验收 case 改为 `p3a_multi_001/002/003`。仅文档口径同步，未进入 M8 实现。
- 2026-07-22 新增数据库状态速查：按用户要求新增 `docs/database-current-state.md`，作为后续 AI 快速获取 Phase 2.7 后 14 表数据库现状、seed 固定事实、指标口径、RBAC、安全边界和后续写 plan 注意事项的入口；同步在「当前技术选型快照」挂入口链接。仅文档整理，未改代码。
- 2026-07-22 Phase 2.7 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 31 passed），报告 `accept-Phase2.7-20260722.md`。阶段二数据库底座升级验收完成，后续可进入 Phase 3A M8 baseline。
- 2026-07-22 补 Phase 2.7 dev-log：按用户要求在 `docs/dev-log.md` 末尾追加「Phase 2.7 数据库升级」学习复盘，覆盖 14 表升级、确定性 seed、固定业务事实、challenge / regression 分层、代码阅读路线和面试讲法。该记录仅说明本次文档补写；Phase 2.7 大改主体仍保留在「模块技术档案（新的在上）」。
- 2026-07-22 Phase 3A 计划补数据库升级前置说明：按用户确认，在 `docs/phase3a-plan.md` 顶部新增「开工前置说明：数据库升级先行」。明确 Phase 3A 正式 M8 前先执行 Phase 2.7 数据库升级，执行规格以 `docs/database-upgrade-plan-v5.md` 为准；升级后 M8 baseline 直接在新库上跑旧链路，不做旧库 vs 新库对照；16 条 `database-upgrade-challenge.yaml` 只作为数据库升级验收和困难诊断素材，不替代 10 条 `phase3a-regression.yaml` 正式硬门；M9 relation_doc / JoinPath 优先来自 `domain_pack/schema_desc/relations.yaml`；数据库升级阶段不要求完整 `schema_retrieval` / `query_plan` / trace_steps，仍留到 Phase 3A M11/M12 验收。后续数据库升级完成后，需要小修本文档的单一事实源、当前差异清单、目录规划、M8 和阶段三A验收标准。
- 2026-07-22 生成数据库升级计划 v5：按用户要求复制 `docs/database-upgrade-plan-v4.md` 为 `docs/database-upgrade-plan-v5.md`，并落入上一轮评审的 P0/P1 修正。① 明确 seed reset 与自增 ID 策略：MySQL 多次 reset 后 ID 不从 1 开始是正常现象，后续 seed 不依赖硬编码 ID，固定事实用 `sku` / `coupon_code` / `channel_name` / `category.name` / `device_type` 等业务键定位，并输出 seed_summary。② 修复 `orders_wide` DDL：`ix_category` 改为索引 `primary_category`，并把 `snapshot_at` / `batch_id` / `source_updated_at` 写入正式字段。③ 明确退款粒度：新增 `refunds.order_item_id` 可空外键，商品退款率优先按订单明细归因，同时兼容整单退款和旧 `product_id` 冗余字段。④ 拆分验收门：数据库升级阶段只验结构、seed、固定事实、基础 challenge 和安全；Phase 3A M11/M12 再验 `schema_retrieval` / `join_path` / `query_plan` 等 trace_steps。⑤ 扩展 `relations.yaml` 规格，补 `relation_type` / `grain` / bridge / recursive / temporal / aggregation_warning，覆盖 order_coupons、多级类目、SCD 时间窗口和聚合放大风险。⑥ 补影响文件清单：`app/db/base.py`、`app/models/__init__.py`、`app/schemas/resources.py`、`eval/run_eval.py`、`engine/nl2sql/schema_loader.py` 等。
- 2026-07-22 生成数据库升级计划 v4：按用户要求复制 `docs/database-upgrade-plan-v3.md` 为 `docs/database-upgrade-plan-v4.md`，并执行评审 P0/P1 修改。① 新增 `order_items` 订单明细表，数据库升级目标改为 13 张业务分析表 + 1 张桥接表，即 14 张物理表；`orders.product_id` 保留为 primary product 兼容字段，商品维度 GMV / 销量默认走 `order_items`。② 评测口径拆成两层：16 条 `database-upgrade-challenge.yaml` 证明新库复杂度和困难诊断素材，10 条 `phase3a-regression.yaml` 继续作为 Phase 3A 新旧链路对照硬门。③ 新增 `domain_pack/schema_desc/relations.yaml` 作为结构化关系事实源，M9 relation_doc / JoinPath 直接从这里生成。④ 修复 `paid_at IS NULL` 与 `orders_wide` 全量同步冲突，要求 `orders.paid_at` / `orders_wide.paid_at` 可空且 GMV 默认排除未支付订单。⑤ 为逻辑脏数据明确新增 `orders.source_order_no` / `orders.external_order_no` / `refunds.source_order_no`，不破坏主表外键和唯一约束。⑥ 补 P1 口径：SCD 改为 50 商品 × 平均 3 版本约 150 行；免运费券通过 `orders.shipping_amount` 实现且不抵扣商品 GMV；施工时间估算调整为约 1.5~2 天。
- 2026-07-22 生成数据库升级计划 v3：按用户要求复制 `docs/database-upgrade-plan-v2.md` 为 `docs/database-upgrade-plan-v3.md`，并吸收评审后的确认项。① 表数量口径修正为 12 张业务分析表 + 1 张桥接表，即 13 张物理表。② 数据量改为 `orders=10000`、`orders_wide=10000`、`refunds≈1000`、`order_coupons≈3000`、`user_behavior_log=10000`，不上 20000，兼顾面试中的一万级数据量讲法和本地 seed / pytest 成本。③ Phase 3A 验收改为 16 条分层用例：简单 3、核心指标 4、中等多表 4、困难诊断 3、安全 2；硬门为安全 2/2、简单 3/3、核心+中等 6/8、困难 1/3 正确且 3/3 可诊断。④ 脏数据策略改为不破坏主表外键/唯一约束，用 `source_order_no` / 外部单号等逻辑脏数据模拟重复和弱关联；强脏数据后续可放 raw_import 表。⑤ 新增固定业务事实和指标默认口径章节，明确 GMV、净收入、优惠金额、退款总额、当前价格、历史售价和宽表使用策略。⑥ 施工时间从约 4h 修正为约 1~1.5 天。
- 2026-07-22 生成阶段三A施工计划：按用户要求新增 `docs/phase3a-plan.md`，以 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`「阶段三A」、`docs/phaseX-plan-template.md`、`docs/AI_CONTEXT.md` 当前状态 / 技术选型 / 已知坑和 `references/askdata_agent` 指定文件为依据。结论：未发现 ROADMAP、AI_CONTEXT、模板之间需要停工确认的主线矛盾；小差异包括 `phase3a-plan.md` 原占位未实际存在、现有 M6 smoke 为 6 条而阶段三A需新增 10 条、现有 `QueryRequest` 尚无 `force_new_pipeline`、Trace 尚无 `trace_steps`、Milvus client 依赖尚未落入项目。计划将模块拆为 M8-M12：M8 冻结 10 条 baseline，M9 Schema Retrieval + JoinPath，M10 QueryPlanStep + 自检，M11 新 pipeline + trace_steps，M12 新旧链路对照报告与收尾；文档更新、测试、smoke 跟随对应模块，不单独拆模块。备注：当前工作树已有用户文档归档改动（`docs/archive/*` 与原 docs 文件删除），本次未回滚。
- 2026-07-21 阶段三A路线收敛二次确认：按用户确认，执行阶段三A优化建议中的 1~3 和 5，调整 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`：① 阶段三A改为“Text2SQL 可校验中间层改造”，强调先用 10 条 SQL 回归冻结 v1 baseline，再改造 Schema Retriever / Join Path / QueryPlanStep / trace_steps；生产链路保留模板优先，但评测链路需支持强制走新 Text2SQL pipeline。② 主线优先级表补充 10 条回归基线、局部 Schema Prompt、新旧链路对照报告，并明确阶段三A目标不是新增更多查询能力，而是让 SQL 生成过程可检索、可计划、可校验、可追踪。③ 量化验收新增阶段三A最低标准：10 条回归（2 简单 / 3 聚合 / 3 多表 / 2 安全）、安全 2/2 拦截、允许类 8 条至少 7 条正确、expected_tables 命中 100%、expected_columns / expected_metrics 命中 ≥80%、QueryPlanStep 通过 Pydantic 和局部 Schema 校验、trace_steps 完整、产出对照报告。④ P1 只作为不阻塞增强：`user_role` 预过滤、Join Path 可解释展示、RRF / Rerank、SQL 错误样例库结构化都不抢 P0。另新增 `docs/phase3a-plan.md`，按用户要求只放结构框架和待补充占位，不写具体施工内容。
- 2026-07-21 seed 数据真实化升级：按用户要求将 `scripts/seed_data.py` 的演示数据从占位名改为真实感数据。① 用户名：`Demo User 01` → `陈米娅` 等 50 个中文姓名，邮箱同步改为拼音 `miya.chen@datapilot.example`。② 商品名：`DataPilot Demo Product xx` → `真无线降噪耳机 Pro`、`CRM 入门版（月付）` 等 29 个中文商品/SaaS 名；锚点商品 `Aurora Noise Cancelling Headphones` 保持不变。③ 工单标题：`Demo support ticket 001` → 按 ticket_type 配 5 组共 35 条真实客服标题词库；描述从统一占位文改为 `用户 {姓名} 提交工单：{标题}`。④ 知识库正文：8 篇 `knowledge_docs.content` 从"阶段二 M1 的知识库草稿"改为 2-5 段完整政策文档正文。⑤ 同时将类目从英文改为中文（`Electronics`→`数码电子`、`Home`→`家居生活` 等），`ticket_type` 从 5 种各 24 条均匀分布改为加权分布（refund 30/shipping 28/invoice 22/account 20/product_quality 20），且 `product` 改名为 `product_quality`，`order_status` 从 4×125 均匀分布改为 delivered 200/shipped 150/paid 100/cancelled 50。固定事实（Aurora 退款率最高/Mobile App GMV 最高/quality_issue Top1/12 pending high tickets）和行数全部保持。协同更新：tests/test_m2_api.py（category + order_status 断言值）、tests/test_m5_agent_response.py（GMV 硬编码值）、scripts/smoke_m2_api.py / smoke_m4_nl2sql.py（category 筛选值）、eval/cases_plan.md（评测用例类目名）。验证：pytest 27/27 passed；seed --reset 输出 counts + facts 全部匹配。备注：users.id 从 301、products.id 从 181 开始是因为 DELETE 不重置 MySQL 自增 ID，不影响业务但截图前可顺手增强 reset 逻辑。按用户确认将 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md` 复制为 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`，只优化学习路线大方向，不生成具体执行 plan。v3 保留阶段三A，但收敛为可校验 Text2SQL 中间层改造：确定默认主链路 `question -> schema_retrieval -> schema_graph/join_path -> query_plan -> local_schema_prompt -> sql_generation -> sql_guard -> sql_execution -> trace`；将 QueryPlanStep 自检提升为 P0；先定 `trace_steps` 结构；Schema 检索文档扩展为 `field_doc / metric_doc / relation_doc`；Milvus 保持主路径并轻提 ChromaDB / 内存向量检索备选；RRF / Rerank 只做接口预留；阶段三A结束要求产出新旧链路对照报告；阶段三A不引入 LangGraph、MCP、Skill、多智能体、SQL 自修复或 EXPLAIN 风险检查。
- 2026-07-21 Phase 2.5 M7 并入阶段三A：按用户确认执行排期收敛，`docs/phase2-plan.md` 中 M7 不再作为独立模块执行，阶段二 M0-M6 作为 v1 baseline 冻结；原 M7 的合理内容并入 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md` 阶段三A，包括新 Text2SQL 链路的 `trace_steps`（schema_retrieval / schema_context / join_path / query_plan / sql_generation / sql_guard / sql_execution / chart_decision）和最小 Eval issue tags（missing_table / missing_column / safety_mismatch / unexpected_error）。完整 scorer 分层、历史结果库、HTML 报告和失败归因平台仍归阶段四独立 AgentEvalOps，不借 M7 名义提前实现。
- 2026-07-21 AskData 技术亮点取舍沉淀：新增 `docs/askdata-tech-value-decision.md`，把 AskData 亮点按“真泛用且面试常问”“有价值但轻量做”“能讲但不做主线”分层；结论是 DataPilot 应优先借鉴字段级 Schema 检索、局部 Schema、轻量 Join 路径约束、结构化 QueryPlanStep、SQL Guard 和分步骤 Trace，MCP / Skill / 长短期记忆 / 多智能体继续作为后期扩展。同步小修 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md`：保留阶段三A，但澄清 SchemaGraph 只是当前 Query 的轻量关系视图，四元组计划只作为 AskData 参考，DataPilot 落地为可校验的 QueryPlanStep；RRF / Rerank / SQL 自修复仍为 P1/P2，不阻塞主线。
- 2026-07-21 面试适配报告修正与 roadmap v2：按用户反馈修正 `docs/interview-fit-vs-askdata.md`，将 DataPilot 单体评分与 “DataPilot + 独立 AgentEvalOps” 项目组合评分拆开，避免把完整版 AgentEvalOps 算作 DataPilot 内置能力；DataPilot 单体完成 Text2SQL 深化 + RAG/Hybrid + 包装后预期约 84-86/100，项目组合约 88-90/100。另在 `D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v2.md` 生成 roadmap v2，在 RAG/Hybrid 前新增阶段三A「Text2SQL 深化」，覆盖字段级 Schema Retriever、Milvus 向量召回、SchemaGraph/Join 路径、QueryPlanStep、局部 Schema SQL prompt、分步骤 Trace、加分项优先级与 AskData 参考位置；同步调整时间表、README 周计划、技术栈和兜底策略。备注：用户提醒后续准备使用 Milvus，本次仅在 roadmap v2 中按主路径体现，未改当前项目运行状态口径。
- 2026-07-21 面试适配度与 AskData 对照分析：按用户担心“AI 从 0 到 1开发的 DataPilot 是否偏离市场面试项目”新增 `docs/interview-fit-vs-askdata.md`，对照当前 M0-M6 DataPilot v1、roadmap 阶段三到阶段五最终形态，以及 `references/askdata_agent` 的文档和可见代码。结论：DataPilot 当前 v1 是工程底座扎实的 NL2SQL v1，面试分约 72/100；完成 RAG/Hybrid、独立 AgentEvalOps、包装后可达强面试项目区间约 88/100。后续最值得借鉴 AskData 的是字段级 Schema Retriever、结构化 QueryPlanStep、SchemaGraph/Join 约束和分步骤 Trace；不建议盲目提前做多库 MCP、长短记忆或完整 Reflection。
- 2026-07-21 M6 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 27 passed），报告 `accept-M6-20260721.md`。阶段二 v1 全部模块 M0-M6 验收完成，可进入阶段三 RAG/Hybrid 或可选 M7 Phase 2.5 硬化
- 2026-07-21 M7 plan 补入 phase2-plan：用户确认采用“方案 B：小做 Phase 2.5”后，将 M7「Phase 2.5 Trace 与 Eval 最小硬化」加入 `docs/phase2-plan.md`。关键边界：M7 仅在 M6 accept 后执行，不属于 v1 验收标准；只做 trace 决策步骤和 Eval issue tag 最小化，不引入完整 EvalOps、数据库、LangGraph 或 RAG 存储选型变化。验证：人工回读；`git diff --check` 仅 Windows LF→CRLF 提示
- 2026-07-21 Phase 2 优化机会分流：按用户阅读 `phase2-reference-review.md` 后的问题，新增 `docs/phase2-optimization-triage.md`，把 trace 增强、Eval issue tag、RAG 契约、模板匹配、SQL Guard reason、Streamlit 增强、LangGraph 迁移等优化点按优先级/难度/风险/roadmap 影响分流。结论：先 accept M6 锁定 baseline；可选做限时 Phase 2.5（trace 决策粒度 + Eval issue tag 最小化）；完整 EvalOps 和 LangGraph 迁移后置。验证：人工回读；`git diff --check` 仅 Windows LF→CRLF 提示
- 2026-07-20 Phase 2 reference 对照复盘：按用户要求补查 phase2-plan 提到的 `askdata_agent`、`QueryMind`、`GustoBot`、`databao-agent`、`langchain_data_agent`、`CoreCoder`、`hello-agents/ch12` 相关文件，并新增 `docs/phase2-reference-review.md`。结论：M2-M6 当时未系统查 reference 在范围受控前提下可接受；当前实现无需返工，后续优先补 trace 粒度、EvalOps issue tags/scorer 分层、Phase 3 RAG 元数据契约。验证：人工回读报告；`git diff --check` 仅 Windows LF→CRLF 提示
- 2026-07-20 M6 dev-log 加粗与 finish-module 规则补强：按用户反馈，为 M6「新概念」「设计要点」解释句补充必要加粗锚点；`finish-module` 阶段 4 新增加粗自检，要求「新概念」「设计要点」不能只加粗条目名，也要加粗关键作用、核心取舍、量化结果和边界风险。验证：人工回读修改段落
- 2026-07-20 M6 dev-log 代码阅读路线二次优化：按用户反馈，将「读者需要重点理解哪个设计点」改进为“点名关键设计，并解释它解决什么问题、为什么这样放”；同步扩充 M6 阅读路线的 `smoke.yaml`、`_score_case()`、Streamlit 页面和阶段验收报告说明。验证：人工回读修改段落
- 2026-07-20 M6 dev-log 阅读路线补强：按用户反馈，将 `docs/dev-log.md` M6「代码阅读路线」中 `eval/run_eval.py` 的说明从函数名罗列扩展为入口、YAML 加载、TestClient + SQLite dependency override、API 调用、评分、报告输出的逐步阅读导航。验证：人工回读修改段落
- 2026-07-20 M5 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 27 passed），报告 `accept-M5-20260720.md`。备注：pytest 旧临时目录 `pytest-of-Stephen` 有权限问题需手动清理；`_elapsed_ms()` 在 query.py 和 sql_tool.py 各有一份相同实现，轻微重复
- 2026-07-20 模块工作流小优化：AGENTS 工作约定新增模块开工极短 checklist、README 阶段末统一整理口径；finish-module 新增“用户确认过的关键取舍”记录要求；phase2-plan M6 新增需用户确认的决策点；AI_CONTEXT 新增当前技术选型快照。验证：人工回读修改段落
- 2026-07-20 M4 验收通过：accept-module 全 7 项检查通过（废弃口径清零/目录地图一致/进度状态一致/最新日志完整/注释合规/单一事实源/测试 24 passed），报告 `accept-M4-20260720.md`
- 2026-07-20 M4 本地启动体验改为 Swagger 优先：按用户实际验证路径，将 `docs/dev-log.md` M4「本地启动体验」改为“启动 FastAPI → 打开 `/docs` Swagger UI → Try it out → 填 JSON → Execute → 看 Response body”，PowerShell 只作为复现和验收留证；同步微调 `finish-module` 模板，后续模块本地体验优先写 Swagger / 浏览器接口文档。验证：人工回读 M4 小节
- 2026-07-20 M4 dev-log 验证体验补强：按用户反馈，`docs/dev-log.md` M4「验证与下一步」从单纯命令列表扩展为自动化验证预期、本地 FastAPI 启动体验、可复制 `/api/query` 输入和大致返回结果；同步更新 `finish-module` skill 模板，要求后续模块写“命令说明 + 预期结果 + 本地启动体验”。验证：人工回读 M4 小节和 skill 阶段 4
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
