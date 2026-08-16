# DataPilot AI Context Changelog — Phase 3A

> 本文件保存 Phase 3A 的完整模块档案、实验记录和历史取舍，按时间倒序排列。当前项目状态以 `docs/state/AI_CONTEXT.md` 为准；跨阶段索引见 `docs/state/CHANGELOG_INDEX.md`。
>
> 默认先按模块号、日期或关键词定位，再读取相关章节，不要无差别全文读取。新结论修正本阶段旧判断时，应在旧条目原位添加 `⚠️ 注`。

M13 之后的新增记录使用标题标签，帮助 AI 快速筛选阅读优先级：

- `[模块任务]`：功能、架构、默认行为、安全口径、评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM eval、smoke 或会影响路线判断的实验结论。
- `[验收]`：accept-module、阶段验收、明确的模块完成状态。
- `[小修]`：文档措辞、口径同步、注释补充、轻量整理；只需简写，不要求完整模板。

「变更记录」：小修可以只写一段话；较大的任务建议包含：改动范围、关键记录（比如关键决策、决策原因、实验结果、新发现、用户做出的选择等）、参考资料、验证快照、遗留/后续。

同一模块 / 同一阶段内连续的小修（中间没有被 [模块任务] / [实验] 等其他类型条目隔开时），合并到一个 [小修] 小节。

## 变更记录（新的在上）

### [小修] AI_CONTEXT 拆分为当前快照 + Changelog（2026-07-27）

- 按用户确认，将 `docs/state/AI_CONTEXT.md` 的完整历史变更记录拆到 `docs/state/AI_CONTEXT_CHANGELOG.md`；`AI_CONTEXT.md` 保留当前状态、默认配置、最新基线、重要实验结论、活跃坑和 changelog 索引，减少后续 AI 续接时默认加载的历史上下文。
- 同步更新 `AGENTS.md` / `CLAUDE.md`、`.claude/skills/finish-module/SKILL.md` 和 `docs/phase3a-plan.md` 的开发记录规则：完整模块档案、真实 LLM eval、A/B 实验和 smoke 结论写入 changelog；影响当前路线的摘要再同步到 `AI_CONTEXT.md`。
- 同轮将真实 `.env` 静默补齐 `DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` 与 `DASHSCOPE_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/api/v1`，不输出任何 API key。

### [实验] Qwen / DashScope 主模型与 Embedding Provider 临时 A/B（2026-07-27）

- 改动范围：`app/core/config.py`、`engine/nl2sql/generator.py`、`engine/schema_retrieval/embedding_provider.py`、`engine/schema_retrieval/retriever.py`、`.env.example`、`scripts/run_qwen_ab_experiments.py`、相关配置 / LLM / embedding 单元测试；同步记录本次临时实验结论，不切默认。
- 关键记录：
  - 新增 Qwen / DashScope 显式 provider 支持：`LLM_PROVIDER=qwen` 可走 DashScope OpenAI-compatible chat completion；`SCHEMA_VECTOR_BACKEND=milvus` + `SCHEMA_EMBEDDING_PROVIDER=dashscope|qwen` 可走 DashScope `qwen3.7-text-embedding`。
  - 默认保持 `LLM_PROVIDER=deepseek` 与 `SCHEMA_VECTOR_BACKEND=inmemory` / `SCHEMA_EMBEDDING_PROVIDER=deterministic`，避免 Phase 3A 收口基线被联网模型、Milvus 服务状态、费用和非确定性影响。
  - 本轮主模型第一轮 formal 初测：DeepSeek formal `9/10`；Qwen `qwen-plus` formal `7/10`。该结果不能证明 Qwen 系列整体不适合 Agent，只说明在当前 DataPilot prompt / JSON 解析 / SQL 兜底均长期按 DeepSeek 调过的前提下，`qwen-plus` 这个旧/通用入口不适合作为 Qwen 主模型代表。
  - 改测官方新代际模型 `qwen3.7-plus` 后，formal 与 DeepSeek 持平：DeepSeek `9/10`、Qwen `qwen3.7-plus` `9/10`；challenge 上 Qwen 略高：DeepSeek `12/16`、Qwen `qwen3.7-plus` `13/16`。失败形态不同：DeepSeek formal 主要卡 `p3a_multi_003` LLM 生成失败；Qwen formal 主要卡 `p3a_multi_001` 缺 `coupon_order_count`。challenge 中 Qwen 过了 DeepSeek 未过的 `db_core_003`、`db_multi_002`，但仍卡 `db_core_004` 结果口径、`db_multi_001` alias/列名和 `db_hard_001` LLM 生成。
  - diagnostic 补测后，DeepSeek `24/32`，Qwen `qwen3.7-plus` `21/32`。这组更像边界体检：DeepSeek 仍有结果口径、LLM 生成失败、plan validation 和 expected columns 严格性问题；Qwen 暴露出更多漏表/漏列和证据字段不足问题，例如 `products`、`supplier_name`、`coupon_order_count`、`doc_title`。结论调整为：Qwen `qwen3.7-plus` 可继续作为强候选和 A/B 对照，但当前 Phase 3A 主模型默认仍保留 DeepSeek。
  - `qwen3.7-max` diagnostic 追加测试为 `22/32`，略高于 `qwen3.7-plus`，但低于 DeepSeek。`qwen3.7-max` 过了 DeepSeek 未过的 `db_join_003`、`db_plan_004`，说明复杂 join / plan 题有上限优势；但独有失败包括 blocking 的 `db_core_002` LLM 生成失败、`db_multi_002` 缺 `category`、`db_plan_002` plan validation failed、`db_trace_002` 缺 `coupon_order_count`。不看分数只看错法，`qwen3.7-max` 的独有错误比 DeepSeek 更影响主线稳定性，所以仍不切默认。
  - 本轮 embedding formal 初测：`Milvus + SiliconFlow BAAI/bge-m3` formal `8/10`；`Milvus + DashScope qwen3.7-text-embedding` formal `9/10`。Qwen embedding 在 formal 上略好，值得继续跑 challenge / diagnostic；但仍未达到足以替换默认 deterministic in-memory 的证据标准。
  - 2026-07-27 20:11 补跑本地 retrieval formal baseline：DeepSeek + `inmemory + deterministic` formal `8/10`，失败为 `p3a_multi_001` 缺 `coupon_order_count`、`p3a_multi_003` 缺 `category`。和 embedding formal 组相比：本地 `8/10`、SiliconFlow BGE-M3 `8/10`、Qwen embedding `9/10`。这说明 Qwen embedding 仍略好，但差距只有 1 题，且 formal 受真实 LLM 波动影响，不能据此切默认。
  - 2026-07-27 按用户建议同步 `AI_CONTEXT.md`「最新评测基线」：保留 M13 后稳定快照 formal `10/10`、challenge `14/16`、diagnostic `23/32`；并新增 M14-lite 后临时真实 LLM 快照。M14-lite 后数字反映更严格 result_match / 安全 / trace 口径和真实 LLM 波动，不能直接当作 M13 退化结论。
  - qwen3.7-text-embedding 口径：官方文档推荐纯文本 / 代码场景使用，支持 1024 默认维度、最长 128K token、批量最多 20 条，并支持 instruct / sparse 等高级功能。本次只接 dense 1024，未启用 sparse / hybrid / rerank。
  - Milvus 启动坑：在 Docker Desktop 直接启动单个 `milvusdb/milvus:v3.0-beta` 容器会自动退出；正确本地方式是官方 Docker Compose 三容器 `milvus-standalone` + `milvus-etcd` + `milvus-minio`，端口 `19530` / `9091`。本次 compose 文件放在 `.agent_work/temp/milvus/docker-compose.yml`，属于本地实验环境，不写入 `.env`。
- 验证快照：
  - 相关单元测试：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_config.py tests\test_m4_nl2sql.py tests\test_m9_2_siliconflow_embedding.py tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work\temp\pytest-qwen-final-related` -> 23 passed，1 个既有 Starlette / httpx warning。
  - 实验脚本：`scripts/run_qwen_ab_experiments.py`，报告写入 `.agent_work/temp/qwen-ab/`。
  - 已完成报告：`main-deepseek-formal.md` 最新补测 `8/10`（历史同脚本曾跑出 `9/10`，说明 formal 存在 LLM 波动）、`main-deepseek-challenge.md` `12/16`、`main-deepseek-diagnostic.md` `24/32`、`main-qwen-plus-formal.md` `7/10`、`main-qwen37-plus-formal.md` `9/10`、`main-qwen37-plus-challenge.md` `13/16`、`main-qwen37-plus-diagnostic.md` `21/32`、`main-qwen37-max-diagnostic.md` `22/32`、`embedding-siliconflow-bge-m3-formal.md` `8/10`、`embedding-qwen37-formal.md` `9/10`；主模型汇总 `summary-20260727-170319.md` / `summary-20260727-171213.md` / `summary-20260727-182431.md` / `summary-20260727-191224.md` / `summary-20260727-201144.md`，embedding 汇总 `summary-20260727-163220.md`。
- 遗留 / 后续：
  - 不再用 `qwen-plus` 代表 Qwen 主模型优劣；后续主模型对照可保留 `qwen3.7-plus` / `qwen3.7-max` 两档，但默认仍使用 DeepSeek。
  - 结构化输出不是一票否决项；DataPilot 当前更依赖“JSON object / prompt 约束 + 解析校验 + 失败拦截”的稳定性。`qwen3.7-max` 可作为上限探测模型，但 diagnostic 表明它仍不适合直接切默认。
  - Qwen embedding 继续跑 challenge / diagnostic 后，再决定是否在 Phase 3 RAG / Hybrid 中作为推荐 provider；Phase 3A 默认仍保留轻量 deterministic / in-memory。

### [模块任务] M14-lite Phase 3A 收口开发中（2026-07-27）

- 改动范围：`eval/run_eval.py`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`engine/nl2sql/generator.py`、`engine/nl2sql/pipeline.py`、`engine/sql_guard/rbac.py`、`engine/schema_retrieval/retriever.py`、`app/core/config.py`、`.env.example`、相关 Phase 3A 测试。
- 关键记录：
  - M14-lite 执行用户确认的 5 项：最小 `result_match`、LLM 失败 trace 增强、安全/diagnostic 口径清理、Schema Retrieval 后端配置开关；不做递归类目、知识库归因、完整 EvalOps、JSON mode 大实验。
  - `result_match` 只做最小结果集对比：执行 `expected_sql`，按行顺序和列值比较 API 返回 rows；不做 SQL AST 等价、历史库或平台化。当前仅给 5 条核心 challenge SQL case 启用，目的是加严结果校验，不追 diagnostic 满分。
  - 安全口径采用用户确认的方案 A：敏感字段优先于 admin 角色；`users.email/users.phone` 在 Text2SQL 路径中默认不直出，后续如需 admin 查看应走脱敏/审计/专门接口。
  - diagnostic 清理只做边界与语义等价 alias：`db_plan_003` 知识库订单金额归因标为 `manual_review + hybrid_attribution + non_blocking`，留给后续 Hybrid；未通过 prompt 硬连知识库与订单。
  - Schema Retrieval 配置开关默认仍是 `inmemory + deterministic`；`milvus` / `siliconflow` 必须通过环境变量显式开启，pytest 不依赖外部 Milvus 或联网 embedding。
  - Milvus/SiliconFlow 不切默认的关键依据：2026-07-26 临时 A/B eval 显示，Milvus + SiliconFlow 对当前 M13 end-to-end pipeline 没有收益，formal `10/10` 持平，challenge `14/16` 持平，diagnostic `23/32 -> 20/32`。因此 M14-lite 只把它登记为显式工程开关和后续 RAG 复用能力，不把它当成 Text2SQL 提分主线。
  - 注意区分两类结论：M9.1/M9.2 的 schema recall smoke 证明 Milvus adapter / SiliconFlow embedding provider 可用；M14-lite 参考的是 M13 后的真实端到端 eval，结论是“能用，但当前不该默认启用”。
- 验证快照：
  - `pytest tests\test_phase3a_eval.py::test_result_match_case_fails_when_generated_rows_do_not_match_expected_sql`：先红后绿。
  - `pytest tests\test_phase3a_pipeline.py::test_sql_generation_failure_trace_keeps_raw_preview_and_parse_context`：先红后绿。
  - `pytest tests\test_m4_nl2sql.py::test_enhanced_guard_blocks_sensitive_fields_and_role_table_access tests\test_phase3a_planner.py::test_sensitive_field_plan_is_blocked_before_sql_generation`：先红后绿。
  - `pytest tests\test_phase3a_schema_retrieval.py::test_retrieve_schema_default_backend_stays_inmemory_deterministic tests\test_phase3a_schema_retrieval.py::test_retrieve_schema_can_explicitly_select_milvus_backend_without_changing_default`：默认路径通过，显式 Milvus 分支先红后绿。
  - Milvus/SiliconFlow A/B 结论来自 M13 后续接文档与 `.agent_work/temp/milvus-eval/` 临时实验记录：formal `10/10` 持平，challenge `14/16` 持平，diagnostic `23/32 -> 20/32`，所以没有切默认，也没有把 diagnostic 下降伪装成配置收益。
- 临时记录：`.agent_work/temp/m14-lite-notes.md`。

### [模块任务] M13 第二批：alias scorer + item_gmv/转化率 prompt 修复（2026-07-26）

- 改动范围：`eval/run_eval.py`、`eval/cases/phase3a-regression.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/pipeline.py`、`tests/test_phase3a_eval.py`、`tests/test_phase3a_planner.py`、`tests/test_phase3a_pipeline.py`、`eval/reports/phase3a-*.md`、`docs/phase3a-issues-and-fixes-v5.md`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m13-notes.md`。
- 关键记录：
  - 继续按分步修复，不做 JSON mode 大改；先用 trace 证明失败位于 eval 评分、QueryPlan prompt、SQL prompt 还是数据预期。
  - `expected_value` 单指标题新增单列兜底：如果结果只有一列，即使列名是 `"2026年6月GMV"` 这类中文别名，也交给数值校验判定；多列结果仍按列名/显式 alias 检查。
  - 给 formal/challenge 补显式 alias：`usage_count`、`add_to_pay_conversion_rate`、`total_gmv`、`category_gmv`、`product_name_snapshot`、中文 `"商品名称"` / `"平均售价"` 等。原则是只放语义等价别名，不用 alias 掩盖缺表或错表。
  - QueryPlan prompt 增加商品/类目销售额约束：必须用 `item_gmv`、聚合 `order_items.line_amount`，商品/类目维度通过 `order_items.product_id = products.id` 关联，不用 `gmv` / `orders.order_amount` / `orders.product_id` 替代。
  - SQL prompt 增加转化率浮点除法约束：`add_to_pay_conversion_rate` 必须使用 `* 1.0` 或 `CAST(... AS REAL)`，避免 SQLite 整数除法把小数截成 0。
  - `一级类目销售额排名` 的固定检查值从 `数码电子` 改为 `SaaS 软件`。原因：用当前 MySQL seed 直接执行参考 SQL，Top1 实际为 `SaaS 软件`；`数码电子及其子类目` 是另一条困难诊断题，未改。
  - 参考资料：未查阅外部参考；本次按 trace 分层诊断和已有 metrics.yaml / schema_desc 口径执行修复，未引入新的参考项目。
- 验证快照：
  - TDD RED/GREEN 细节见 `.agent_work/temp/m13-notes.md`。
  - 相关回归最终：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-single-metric-related` -> 37 passed，1 既有 Starlette/httpx warning。
  - finish-module 注释补强后相关回归：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py tests\test_phase3a_planner.py tests\test_phase3a_pipeline.py --basetemp=.agent_work\temp\pytest-m13-finish-related` -> 37 passed，1 既有 Starlette/httpx warning。
  - 全量 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest --basetemp=.agent_work\temp\pytest-m13-final-full-2` -> 78 passed，1 既有 Starlette/httpx warning。
  - `git diff --check`：无 whitespace error，仅 Windows CRLF 提示。
  - 真实 LLM formal：10/10（最新报告 `eval/reports/phase3a-new-pipeline.md`）。
  - 真实 LLM challenge：14/16（最新报告 `eval/reports/phase3a-challenge-new-pipeline.md`）。
  - 真实 LLM diagnostic：23/32，review_required=3（最新报告 `eval/reports/phase3a-diagnostic-new-pipeline.md`）。
  - formal/challenge/diagnostic 对照报告已按最新 trace 重生成：`eval/reports/phase3a-comparison.md`、`eval/reports/phase3a-challenge-comparison.md`、`eval/reports/phase3a-diagnostic-comparison.md`。
  - finish-module 注释扫描：M13 新增/修改函数与测试均有 docstring 或开头说明；补充 `eval/run_eval.py` 单指标数值兜底、`engine/nl2sql/prompt.py` item_gmv 计划约束两处内部注释。
- 遗留：
  - challenge 仍有 2 条未过：`db_multi_002` 本轮为 LLM generation error；`db_hard_001` 是非阻塞 manual-review 递归类目题，被 SQL Guard 拦截。
  - diagnostic 仍有 9 条未过：5 条偏输出列/诊断评分严格性，2 条 plan validation/guard blocked，1 条非阻塞递归类目 SQL Guard block，1 条安全诊断 `db_sec_004` safety_mismatch。
  - Windows 下默认 `.agent_work/temp/pytest-tmp` 仍可能被锁，已改用本次专属 `--basetemp` 规避。

### [模块任务] M13 第一批：eval 固定事实校准 + metrics prompt 管道修复（2026-07-26）

- 改动范围：`eval/run_eval.py`、`eval/cases/phase3a-regression.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`tests/test_phase3a_eval.py`、`tests/test_phase3a_planner.py`、`docs/archive-dormant/phase3a-issues-and-fixes-v5.md`、`.agent_work/temp/m13-notes.md`。
- 关键记录：
  - 按 v5 执行 M13 分步修复，不一步到位。第一批先解决"测不准"和"metrics prompt 管道断裂"，暂不改 JSON mode，不直接优化 Schema Retrieval。
  - 新增 `expected_value` eval check，优先拦住 `gmv=NULL` 但 `contains: gmv` 误判通过的问题。正式 regression/challenge 中 GMV 使用固定事实 `11285752.00`，净收入按确定性 seed 查询得到 `11293058.25`。
  - `_format_plan_metrics()` 现在会把 `filter` 和 `default_time_field` 注入新 pipeline 的 QueryPlan / 局部 SQL prompt，恢复旧 M4 `_format_metrics()` 已有的结构化指标口径。
  - `DeepSeekChatClient.complete()` 支持可选 `system_prompt`；`generate_query_plan()` 和 `generate_sql_from_plan_step()` 传入各自任务角色。为保护已有 fake LLM 测试，新增兼容调用：旧 `complete(prompt=...)` fake client 仍可工作。
  - 参考资料：未查阅外部参考；本次按 v5 计划执行 M13 第一批修复，修改范围限定在 eval scorer、metrics prompt 管道和 generator system_prompt 兼容；未引入新的参考项目。
- 验证快照：
  - TDD RED/GREEN 记录见 `.agent_work/temp/m13-notes.md`。
  - `tests/test_phase3a_eval.py`：15 passed，1 既有 Starlette/httpx warning。
  - `tests/test_phase3a_planner.py`：11 passed。
  - `tests/test_phase3a_pipeline.py`：4 passed，1 既有 warning。
  - `tests/test_m4_nl2sql.py`：5 passed，1 既有 warning。
  - 相关回归：38 passed，1 既有 warning。
  - 第一批修复后全量 pytest：69 passed，2 skipped，1 既有 warning。
  - 真实 LLM formal 重跑：第一轮 6/10，补 trace 后重跑 5/10；GMV / 净收入均为 `expected_value_ok`，说明原 NULL 伪通过问题已消失。
  - 真实 LLM challenge 重跑：10/16（M12 为 8/16），GMV / 净收入均为 `expected_value_ok`。
  - 真实 LLM diagnostic 重跑：20/32（M12 为 15/32）。
  - 对照报告已重新生成：`eval/reports/phase3a-comparison.md`、`phase3a-challenge-comparison.md`、`phase3a-diagnostic-comparison.md`。
  - trace 增强后全量 pytest：71 passed，1 既有 warning。
- 遗留：
  - M13 已确认原始 `paid_at` / `unpaid` / NULL 类问题基本修复。剩余失败主要是 alias / expected table 严格匹配、SQL 生成阶段没有采用已召回表、以及少数真实 SQL 语义问题（如转化率别名/整数除法、一级类目销售额漂到 `orders_wide`/`gmv`）。下一轮不要再优先改 metrics prompt，应基于新增 trace metadata 判断是 plan prompt、SQL prompt 还是 eval 评分口径需要调整。

### [小修] Phase 3A 问题分析 v5 修订（2026-07-26）

- 改动范围：新增 `docs/archive-dormant/phase3a-issues-and-fixes-v5.md`（由 v4 复制后修订），未改源码。
- 关键记录：
  - v4 主线判断保持：M12 新 pipeline 低通过率的确定性根因优先看 `_format_plan_metrics()` 漏传 `metrics.yaml` 的 `filter/default_time_field`，以及 eval 只做列名 / contains 检查导致 GMV=NULL 也 pass。
  - v5 收紧优先级：第一批执行顺序改为先做 `expected_value` 最小 eval，让固定事实数值错误能被测出来；再修 metrics prompt 管道和 system prompt；之后重跑 formal / challenge / diagnostic。
  - JSON mode 影响从"可能根因"降级为"待验证假设"，仅保留三组对照实验（当前 / SQL 层放开 / 全部放开），不在第一批直接改。
  - `p3a_multi_002` 的 `products` 问题不再直接归因为 Schema Retrieval 没召回；当前复核显示同题 SchemaGraph 可包含 `products`，M12 formal 报告里的 `missing_tables=['products']` 更可能是 SQL 生成阶段选择 `order_items.product_name_snapshot`。后续需通过 trace 区分召回、QueryPlan、SQL 生成三层。（结论：不能凭 `missing_tables` 直接判检索漏召回，先看 trace 定位到层。）
  - `orders.md` 的 `order_status` 字段说明后续应同时补 `canceled` 和 `pending_payment`，避免模型继续幻想不存在的 `unpaid` 状态。
- 验证快照：
  - 已确认正确 `paid_at` 口径 2026 年 6 月 GMV = `11285752.00`；M12 报告中 `created_at` + `unpaid/cancelled` 口径会得到 NULL，但旧 eval 仍可因 `contains: gmv` 判 pass。
  - 当前源码现跑"2026 年 6 月商品销售额 Top 5"时，SchemaGraph 包含 `products`，支持 v5 的归因修正。

### [小修] AI_CONTEXT M9.1/M9.2 合并状态修正（2026-07-25）

- 改动范围：`docs/state/AI_CONTEXT.md`（仅文档）
- 关键决策：M9.1/M9.2 的遗留说明"未合并回 main"已过时——`9fa9368` 已将 Milvus 和 SiliconFlow embedding 可选支持合入 main。默认检索路径仍为 `InMemoryVectorIndex`，不影响 M12 结果（和 Milvus 没启动无关）。修正 M9.1 遗留第 3 条、M9.2 遗留第 2 条。

### [小修] 数据库状态文档补充 + Phase 3A 问题分析 v3 修订（2026-07-25）

- 改动范围：`docs/state/database-current-state.md`、`docs/phase3a-issues-and-fixes-v3.md`（仅文档，无代码改动）
- 关键决策：
  - **实地查库验证 Phase 2.7 数据质量彩蛋**：连接 MySQL `datapilot_dev` 逐项核实 7 个彩蛋的实际数据。确认全部存在，但文档描述有 3 处不够精确：`order_status` 漏了 `pending_payment` 状态（20 条）、`refunds.source_order_no` 格式与 `orders.order_no` 完全不同（SRC-xxx vs ORD-xxx，不能 join）、整单退款（100 条 `order_item_id IS NULL`，10%）未被列为独立彩蛋。
  - **`database-current-state.md` 4 处修正**：① `order_status` 行补完整 6 种状态及行数；② `source_order_no` 行补格式差异和"不能 join"警告；③ refunds 表行量化整单退款比例（10%，必须 LEFT JOIN）；④ "数据质量设计"节全部 7 条量化到具体数字，原"弱关联退款"改为"命名空间不兼容"，新增整单退款条目。
  - **`phase3a-issues-and-fixes-v3.md` 多轮修订**：① 精度修正——明确 bug 是 rewrite regression（旧 `_format_metrics()` 正确，新 `_format_plan_metrics()` 漏字段）；② system prompt 优先级从 ★★ 下调为 ★（user prompt 已部分补偿）；③ 实验设计补旧链路对照组；④ 优先级表合并 Step 4+5；⑤ 新增"问题八"（`numerator`/`denominator` 静默丢弃）和"问题九"（`orders.md` 缺 `canceled` 拼写）；⑥ 彩蛋表重写为 4 列（实际数据 + LLM 易犯错误），补数据库速查行；⑦ 文档末尾新增修订记录节。
  - **v3 方案评估结论**：修复方案和优先级靠谱。最高优先仍是修 `_format_plan_metrics()`（~8 行），数据库验证加强了这一判断——LLM 失败模式可精确描述为"用 `created_at` 代替 `paid_at` + 自编不存在的 `order_status = 'unpaid'` + 不知双拼写"，而 `metrics.yaml` 的 `filter` 和 `default_time_field` 恰好提供这三个缺失信息。
- 参考资料：直接查询 MySQL 数据库；对比 `database-current-state.md`、`domain_pack/schema_desc/orders.md`、`domain_pack/metrics.yaml` 和实际数据。
- 验证快照：
  - orders 总量 10000，`paid_at IS NULL` 20 条，状态均为 `pending_payment`
  - `cancelled` 421 条 + `canceled` 8 条 = 429 条取消
  - `refunds.source_order_no` 格式 `SRC-2026-XXXXX`，与 `order_no`（`ORD-2026-XXXXX`）**0 匹配**
  - 1000 条退款中 `order_item_id IS NULL` 100 条（10%）
  - 金额不一致 5 条、负数退款 3 条 `-20.00`、`source_order_no` 重复 20 条——均与文档一致
  - 14 表行数全部与文档一致
  - 2026 年 6 月 GMV（`paid_at` 口径+filter）= `11285752.00`，与固定事实一致
- 遗留：`orders.md` schema_desc 的 `order_status` 字段行仍未补 `pending_payment` 和 `canceled`，属于问题九的范围，等主线修复完成后处理。

### [模块任务] Phase 3A M12 对照报告与阶段收尾（2026-07-25）

- 改动范围：新增 `eval/compare_phase3a.py`、`scripts/smoke_phase3a_text2sql.py`；修改 `engine/nl2sql/generator.py`、`engine/nl2sql/planner.py`、`app/api/query.py`、`README.md`、`docs/state/AI_CONTEXT.md`
- 关键决策：
  - M12 负责跑新 pipeline 10 条 formal / 16 条 challenge / 32 条 diagnostic 报告，生成新旧链路对照报告，提供一键 smoke 脚本，更新 README 能力边界。
  - **DeepSeek 模型名修复**：API 已废弃 `deepseek-chat`，修改 `generator.py` 两处默认值为 `deepseek-v4-pro`；同步更新 README LLM_MODEL 示例。
  - **新 pipeline 安全预检补丁**：新链路 `force_new_pipeline=true` 绕过了旧链路的 `_looks_like_dangerous_sql` 预检，导致 DROP/DELETE 等危险问题被 LLM 转写成 SELECT 从而绕过安全用例。修复：在 `app/api/query.py` 的 `force_new_pipeline` 分支前增加相同预检。
  - **plan validation 聚合表达式误判修复**：`_check_table_and_column_scope()` 把 `COUNT(DISTINCT orders.id)` 当作普通列名检查导致误判。修复：拆分 `step.columns` 为纯 `table.column` 和表达式引用，表达式通过 `_qualified_refs()` 提取内部引用。
  - **对照报告生成策略**：选择读取 trace JSONL（结构化）而非解析 Markdown 报告。`compare_phase3a.py` 按 question 文本匹配 case，生成并排对比表（通过率、Schema 精简度、JoinPath、Trace Steps、Issue Tags）。
  - **LLM 通过率现状**：新 pipeline 允许类 SQL 约 50-60% 通过率，低于计划目标 7/8。主要瓶颈是 LLM 输出列名不稳定（别名漂移），与 baseline 遇到的同源。对照报告如实呈现，issue tags 记录具体失败原因。后续 P0 schema/plan/prompt 优化可提升。
  - 用户确认：本模块按 `docs/phase3a-plan.md` M12 默认方案执行，未出现需要偏离计划的新方案选择。
- 参考资料：未查阅外部参考；本次按 `docs/phase3a-plan.md` M12、M8-M11 已有 baseline 和新 pipeline 代码实现。
- 验证快照：
  - 新 pipeline formal 10：6/10 passed（安全 2/2 blocked）
  - 新 pipeline challenge 16：8/16 passed（安全 2/2 blocked）
  - 新 pipeline diagnostic 32：15/32 passed
  - 对照报告 formal/challenge/diagnostic 三份均生成
  - pytest：65 passed, 2 skipped, 1 warning（既有 Starlette/httpx）
  - `git diff --check`：无 whitespace error，仅 Windows CRLF 提示
- 遗留：
  - M12 未解决 LLM 列名别名漂移问题（category/category_name、coupon_order_count 等），属于 P0 schema/plan/prompt 优化范畴，留给后续阶段。
  - 阶段三A 全部 5 个模块（M8-M12）代码已就绪；M12 收工整理后等待人工检查和 accept-module。
  - ⚠️ 注：本条「主要瓶颈是 LLM 输出列名不稳定（别名漂移）」的判断后经 M13 复核推翻——主因是 metrics → prompt 管道断裂（`_format_plan_metrics()` 漏字段）+ 数据质量彩蛋，别名漂移只是症状；部分「失败」还是 eval 误判（假漂移）。详见下方 M13 第一批条目。

### [模块任务] Phase 3A M11 新 Text2SQL Pipeline 与 Trace Steps（2026-07-24）

- 改动范围：未提供模块起始 commit，本次按 `git status --short`、`git diff --name-only` 和未跟踪文件检查；`engine/nl2sql/pipeline.py`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`engine/trace/recorder.py`、`app/schemas/agent.py`、`app/api/query.py`、`tests/test_phase3a_pipeline.py`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m11-notes.md`
- 关键决策：
  - `QueryRequest.force_new_pipeline: bool = False` 作为 API 侧显式评测开关，默认旧请求仍模板优先；没有修改 `AgentResponse` 必填字段，也没有暴露 `plan_execute` / 多 SQL Agent 模式。
  - `trace_steps` 只写入 JSONL `TraceRecord`，不放进公开响应体；每步包含 `step_index/step_type/status/input_summary/output_summary/latency_ms/error_type/metadata/parent_step_id`，SQL 执行 step 的 `step_type=sql_query`，执行元信息放 `metadata`。
  - 新增 `run_text2sql_pipeline()` 串起 `schema_retrieval -> schema_context -> join_path -> query_plan -> plan_validation -> sql_generation -> sql_guard -> sql_execution -> chart_decision`；任何一步失败都结构化 blocked，不降级到模板、全量 schema prompt 或 SQL 自动修复。
  - 新 pipeline 生成 SQL 后仍统一进入 `run_sql_tool()`，SQL Guard / RBAC / 敏感字段策略仍是最终安全门；测试中 fake LLM 返回 `DELETE FROM orders` 已被 `sql_guard_blocked` 拦截。
  - `eval.run_eval` 的 `pipeline_mode=new_text2sql` 到 `force_new_pipeline=true` 映射已在 M8.5 落地，本模块未重复改动；M11 通过 API 侧接入和 trace_steps 证明实际链路。
  - 用户确认：M11 采用计划默认方案，没有出现需要偏离计划的新方案；未引入 LangGraph、MCP、DB-GPT AWEL、AskData MCP、多智能体或 SQL 自修复。
- 参考资料：
  - 查阅 `references/askdata_agent/askdata_pipeline/text2sql_pipeline.py`：借鉴端到端 step log 和 Schema Retrieval -> Plan -> SQL -> Execute 的串联位置；没有引入 MCP Router。
  - 查阅 `references/askdata_agent/sql_generation/prompt_builder.py`：借鉴“当前计划 + 局部 Schema”生成 SQL 的 prompt 边界；DataPilot 保留 JSON 结构化输出。
  - 查阅 `references/DB-GPT/examples/awel/simple_nl_schema_sql_chart_example.py`：借鉴 `schema_linking -> prompt_join -> sql_gen -> sql_exec -> chart` 的阶段覆盖，用于校验 trace_steps 命名完整。
  - 查阅 `references/DB-GPT/packages/dbgpt-core/src/dbgpt/core/awel/dag/base.py` 和 `references/DB-GPT/packages/dbgpt-app/src/dbgpt_app/scene/base_chat.py`：只借 node/context/trace 分段思想；没有新增 `dbgpt-*` 依赖或运行时框架。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-red` 失败于 `ImportError: cannot import name 'pipeline' from 'engine.nl2sql'`，符合 M11 缺口。
  - M11 聚焦：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-tmp-3` 4 passed，1 warning。
  - M11 指定验证：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_pipeline.py tests\test_m5_agent_response.py tests\test_m4_nl2sql.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-related-2` 12 passed，1 warning。
  - 全量 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m11-full-2` 67 passed，1 warning（既有 Starlette TestClient / httpx deprecation，不影响 M11）。
  - `git diff --check`：无 whitespace error，仅 `app/api/query.py`、`app/schemas/agent.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/prompt.py`、`engine/trace/recorder.py` 的 Windows LF→CRLF 提示。
- 遗留：
  - M11 只完成新 pipeline 接入和 trace_steps；M12 负责跑 formal / challenge / diagnostic 新链路报告、生成对照报告、smoke 脚本和 README 阶段收尾。
  - 当前测试用 fake LLM 固定 QueryPlan / SQL 验证链路结构；真实 LLM 质量、通过率和 issue tags 需要 M12 批量报告如实呈现。
  - `trace_steps` 已写 JSONL，但公开 API 响应暂不展示；后续若 demo 需要展示 trace，可在不改 JSONL 顶层结构的前提下增量做。

### Phase 3A M10 QueryPlanStep 与自检（2026-07-24）

- 改动范围：未提供模块起始 commit，本次按 `git status --short`、`git diff --name-only` 和未跟踪文件检查；`engine/nl2sql/planner.py`、`engine/nl2sql/prompt.py`、`engine/nl2sql/generator.py`、`tests/test_phase3a_planner.py`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m10-notes.md`
- 关键决策：
  - 新增 `QueryPlanStep` / `QueryPlan`，字段覆盖 `step_id/step_index/step_type/purpose/depends_on/task_type/tables/columns/metrics/filters/joins/aggregations/group_by/order_by/limit/output_columns`；`QueryPlan.steps` 保留未来多步骤扩展，但 M10 校验阶段把多个可执行 `sql_query` step 映射为 `unsupported_multi_step_plan`。
  - `QueryPlanStep` 不包含 `thoughts` / CoT，也不把 `display_type` 作为执行字段；只用 `purpose` 表达意图摘要，展示策略留给 M11 `chart_decision`。
  - Join 自检使用 M9 `SchemaGraph.join_paths` / `relations.yaml` 的 relation id，不接受自由文本编造 Join；表、字段、指标也必须来自局部 SchemaGraph 和 DomainSchema。
  - 敏感字段在 SQL 生成前预检为 `sensitive_field_access`，但 SQL Guard 仍是最终安全门；本模块没有改变 RBAC / SQL Guard 策略。
  - `build_query_plan_prompt()` 通过 `QueryPlan.model_json_schema()` 生成 JSON 格式说明，减少 Pydantic 字段和 prompt 示例漂移；`extract_query_plan()` 只兼容 JSON / fenced JSON / 前后短解释中的 JSON，不做字段名猜测式放宽。
  - 用户确认：本模块没有出现需要偏离计划的新方案；沿用 `docs/phase3a-plan.md` M10 默认边界。
- 参考资料：
  - 查阅 `D:\.Work\Practice\Python-Practice\references\askdata_agent\cot_planning\cot_planner.py`：借鉴“Schema Retrieval 与 SQL 生成之间先有可解析中间计划”的位置，但没有照搬四元组计划，也没有暴露原始 CoT。
  - 查阅 `D:\.Work\Practice\Python-Practice\references\askdata_agent\sql_generation\prompt_builder.py`：借鉴 SQL prompt 只能使用局部 Schema 的约束，M10 先落到 QueryPlan prompt。
  - 查阅 `D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-core\src\dbgpt\agent\core\action\base.py`：借鉴 Pydantic 输出结构生成 JSON 格式说明的思路，没有引入 DB-GPT Action 框架。
  - 查阅 `D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-app\src\dbgpt_app\scene\chat_db\auto_execute\prompt.py`：只借鉴结构化输出约束；没有让模型直接决定执行或绕过 SQL Tool。
  - 查阅本地 `engine/sql_guard/policy.py` / `engine/sql_guard/rbac.py`：确认敏感字段和角色策略口径。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-red` 失败于 `ImportError: cannot import name 'QueryPlanExtractionError'`，符合 M10 缺口。
  - M10 指定验证：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_planner.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-tmp` 9 passed。
  - 相关回归：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m4_nl2sql.py tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-related-2` 11 passed，1 warning。
  - 全量 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m10-full` 63 passed，1 warning（既有 Starlette TestClient / httpx deprecation，不影响 M10）。
  - `git diff --check`：无 whitespace error，仅 `engine/nl2sql/generator.py`、`engine/nl2sql/prompt.py` 的 Windows LF→CRLF 提示。
- 遗留：
  - M10 只定义和验证 QueryPlan，不把它接入 `/api/query` 或 eval runner；M11 负责 `force_new_pipeline`、new Text2SQL pipeline 和 `trace_steps`。
  - 聚合函数 × 字段类型校验属于计划 P2/可选增强，本模块未提前做；后续若 schema metadata 有稳定 data_type 再补。
  - 当前 `extract_query_plan()` 不做同义字段名兼容，真实 LLM 若输出严重偏离 JSON Schema，会按 `invalid_query_plan` 暴露，留给 M11/M12 报告真实失败。

### Phase 3A M9.2 真实中文 Embedding + Milvus 效果测试（2026-07-24）

- 改动范围：未提供模块起始 commit，本次按当前实验分支工作树变更检查；`engine/schema_retrieval/embedding_provider.py`、`engine/schema_retrieval/vector_index.py`、`scripts/smoke_m9_2_real_embedding.py`、`tests/test_m9_2_siliconflow_embedding.py`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m9.2-notes.md`、`.agent_work/temp/m9_2-real-embedding-smoke-bge-m3.md`、`.agent_work/temp/m9_2-real-embedding-smoke-qwen3-0.6b.md`
- 关键决策：
  - M9.2 从 M9.1 实验状态切出 `codex-m9.2-real-embedding-experiment`，继续遵守“不合并前先询问用户”。M10 主线仍建议基于已验收 M9 / main，而不是实验分支。
  - 新增 `SiliconFlowEmbeddingProvider`，默认模型 `BAAI/bge-m3`；通过环境变量可切换 `SILICONFLOW_EMBEDDING_MODEL` 和 `SILICONFLOW_EMBEDDING_DIMENSIONS`。真实 API 调用只放 smoke，pytest 用 fake transport，不消耗额度、不依赖网络。
  - `MilvusVectorIndex` 支持 provider 返回 dense vector，并先批量 embedding 文档、推断真实维度，再创建 Milvus collection；否则真实 embedding 维度与默认 128 维不一致会导致 Milvus schema 错误。
  - Provider 增加内存缓存，避免同一文档 / query 在一次 smoke 中重复请求 SiliconFlow。
  - Smoke 同时输出 `merged_top30` 和 `vector_only_top12`：前者模拟 M9 当前主召回策略，后者观察真实 embedding 自身排序能力。
- 参考资料：
  - 查阅 SiliconFlow 官方 embeddings API，确认 `POST /v1/embeddings`、Bearer token、`BAAI/bge-m3`、`Qwen/Qwen3-Embedding-0.6B` 与 Qwen3 `dimensions` 参数。
  - 本次未查外部 benchmark，只用项目 M9 formal/challenge/diagnostic case 做本地效果对比。
- 验证快照：
  - TDD 红灯：`pytest tests\test_m9_2_siliconflow_embedding.py ... --basetemp=.agent_work/temp/pytest-m9_2-red` 失败于 `ModuleNotFoundError: No module named 'engine.schema_retrieval.embedding_provider'`。
  - 单元/集成绿灯：`pytest tests\test_m9_2_siliconflow_embedding.py tests\test_m9_1_milvus_schema_retrieval.py tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9_2-related` 10 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - 真实 API：首次 `scripts\smoke_m9_2_real_embedding.py` 因沙箱网络权限失败，`WinError 10013`；提权后成功调用 SiliconFlow。运行时设置 `OPENBLAS_NUM_THREADS=1`，避免 Windows 下 OpenBLAS 偶发线程/内存分配问题。
  - BGE-M3：`BAAI/bge-m3` + Milvus + `merged_top30` 与 M9 持平：formal 15/15 tables、16/18 items、3/3 join；challenge 29/29、29/33、6/6；diagnostic 54/54、54/62、14/14。`vector_only_top12` 下 challenge 27/29、28/33、5/6；diagnostic 51/54、50/62、12/14。
  - Qwen3-0.6B：`Qwen/Qwen3-Embedding-0.6B` + `dimensions=1024` + Milvus + `merged_top30` 与 M9 持平：formal 15/15、16/18、3/3；challenge 29/29、29/33、6/6；diagnostic 54/54、54/62、14/14。`vector_only_top12` 下 challenge 28/29、29/33、6/6；diagnostic 51/54、55/62、14/14。
- 遗留：
  - 当前 M9 的 keyword + relation merge 已经覆盖硬门，真实 embedding 对最终 merged_top30 没有提升；派生 SQL alias（如 `coupon_order_count`、`conversion_rate`、`avg_price`）仍不是 embedding 能直接解决的问题，留给 M10/M11。
  - Qwen3-0.6B 在 vector-only_top12 比 fake / BGE-M3 更好，说明后续如果做真正语义检索，优先试 Qwen3；但主线不宜默认联网 embedding。
  - 已合并回 main（`9fa9368`），合并后默认 retriever 保持 `InMemoryVectorIndex`，Milvus/SiliconFlow 作为可选注入。

### Phase 3A M9.1 Milvus Adapter 实验（2026-07-23）

- 改动范围：未提供模块起始 commit，本次按当前实验分支工作树变更检查；`engine/schema_retrieval/vector_index.py`、`engine/schema_retrieval/retriever.py`、`tests/test_m9_1_milvus_schema_retrieval.py`、`scripts/smoke_m9_1_milvus.py`、`pyproject.toml`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m9.1-notes.md`、`.agent_work/temp/m9_1-milvus-smoke.md`
- 关键决策：
  - 从已验收 M9 后的 `main` 切出实验分支 `codex-m9.1-milvus-experiment`，不在实验完成后自动合并；用户明确要求“如果要合并先询问”。
  - 使用 `pymilvus 3.0.0` 的 `MilvusClient` 新 API，不使用会触发 deprecation warning 的 ORM API。`pyproject.toml` 登记 `pymilvus>=3.0.0`，避免实验分支依赖只存在于本机环境而没有项目声明。
  - `retrieve_schema()` 默认仍使用 M9 的 in-memory vector index；只有显式注入 `MilvusVectorIndex` 时才走方案 B，避免普通 pytest 和主线开发被 Docker / Milvus 服务绑定。
  - Milvus collection 使用显式 schema：`doc_id VARCHAR(max_length=512)` 作为主键，`vector FLOAT_VECTOR(dim=128)`，索引用 `AUTOINDEX + COSINE`；插入后 `flush + load_collection`，保证 smoke 立即可查。
  - M9 的 deterministic sparse embedding 通过 SHA1 稳定 hash 映射到 dense vector。这里刻意不用 Python 内置 `hash()`，因为内置 hash 有进程级随机盐，会导致 Milvus 召回排序不可复现。
- 参考资料：
  - 查阅本机 `pymilvus.MilvusClient` 签名，并用临时 collection 探测 `create_collection / insert / flush / load / search / drop_collection` 行为。
  - 未查阅外部文档；本次只基于本机 PyMilvus 3.0 API 和 M9 已有接口实现。
- 验证快照：
  - 分支：`git switch -c codex-m9.1-milvus-experiment` 初次因沙箱 `.git` 写权限失败，提权后创建成功；当前工作在实验分支。
  - 环境探测：`pymilvus 3.0.0` 可 import；`http://127.0.0.1:19530` 可连接，初始 collections 为空。
  - TDD 红灯：`pytest tests\test_m9_1_milvus_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9_1-red` 2 failed，失败于 `MilvusVectorIndex` 仍抛 `NotImplementedError`。
  - 聚焦绿灯：`$env:OPENBLAS_NUM_THREADS='1'; pytest tests\test_m9_1_milvus_schema_retrieval.py tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9_1-related` 8 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - Smoke：`$env:OPENBLAS_NUM_THREADS='1'; python scripts\smoke_m9_1_milvus.py` 成功生成 `.agent_work/temp/m9_1-milvus-smoke.md`；运行中出现既有 TestClient/httpx warning。
  - Smoke 对比：in-memory 与 Milvus 在当前 deterministic embedding 下数字完全一致：formal 15/15 tables、16/18 items、3/3 join；challenge 29/29 tables、29/33 items、6/6 join；diagnostic 54/54 tables、54/62 items、14/14 join。
- 遗留：
  - 当前 Milvus 只替换向量存储，不替换 embedding 模型；因此质量没有优于 in-memory。若要评估“Milvus 主路径是否值得合入”，建议下一步接真实中文 embedding（BGE / text2vec）后复测。
  - 由于 M9.1 真实测试依赖 Docker Milvus，默认 M9 测试仍不应强制依赖外部服务；若未来合并，建议把 Milvus 测试保留为显式 smoke 或可 skip 集成测试。
  - 已合并回 main（`9fa9368 Merge optional Milvus and SiliconFlow embedding support`）。合并后默认检索路径仍为 `InMemoryVectorIndex`，`MilvusVectorIndex` 为可选注入。

### Phase 3A M9 Schema Retrieval 与 JoinPath（2026-07-23）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`engine/schema_retrieval/*`、`tests/test_phase3a_schema_retrieval.py`、`domain_pack/schema_desc/relations.yaml`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m9-notes.md`、`.agent_work/temp/m9-recall-summary.md`
- 关键决策：
  - 用户确认选择 M9 选项 A：按 ROADMAP 保留 Milvus 主路径边界，但本模块只实现 deterministic in-memory vector index 与 `EmbeddingProvider` / `InMemoryVectorIndex` 协议，不新增 `pymilvus`、Docker 启动脚本或网络下载依赖。主要风险是真实语义召回质量仍需后续 Milvus / BGE adapter smoke 验证；好处是 M9 不被环境集成阻塞，P0 的文档结构、召回契约和 JoinPath 可先稳定。
  - Schema 文档只分 `field_doc`、`metric_doc`、`relation_doc` 三类；没有新增独立 alias 文件。字段文档复用 `schema_desc/*.md`，指标文档复用 `metrics.yaml` 并做轻量中文业务说法扩写，关系文档优先来自 `relations.yaml`。
  - JoinPath 严格从 `domain_pack/schema_desc/relations.yaml` 构造，不从 Markdown 自然语言关系或 LLM 输出猜 Join。M9 暴露并补齐了 `relations.yaml` 原缺的 `refunds_order`、`refunds_product`、`refunds_user` 三条关系；这些关系已存在于 `refunds.md`，本次只是补齐结构化单一关系源。
  - `SchemaGraph` 当前按命中表补齐该表字段，优先保证 M9 recall 硬门；更严格的局部 Schema prompt 精简留给 M11。派生列别名如 `coupon_order_count`、`conversion_rate`、`avg_price` 不在 M9 强行伪造成物理字段，后续由 M10/M11 的 QueryPlan / SQL alias 层处理。
- 参考资料：
  - 查阅 `docs/phase3a-plan.md` M9、`domain_pack/schema_desc/relations.yaml`、`domain_pack/metrics.yaml`、`eval/cases/phase3a-regression.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/cases/phase3a-diagnostic-benchmark.yaml`、`engine/nl2sql/schema_loader.py` 和 `eval/run_eval.py`。
  - 借鉴计划中 AskData / DB-GPT 的分层思想：文档构建、检索、图构建分开；没有引入 DB-GPT / AWEL / Milvus runtime 依赖，也没有提前实现 RRF / rerank 主链路。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_schema_retrieval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-red` 失败于 `ModuleNotFoundError: No module named 'engine.schema_retrieval'`，符合预期。
  - 聚焦 pytest：`pytest tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9-tmp` 6 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - 相关回归：`pytest tests\test_phase3a_eval.py tests\test_phase3a_schema_retrieval.py ... --basetemp=.agent_work/temp/pytest-m9-related` 19 passed，1 warning（既有警告）。
  - 全量 pytest：首次 120 秒超时停在 `tests/test_m3_query.py` 中途，未判定失败；改用 300 秒后 `pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m9-full-rerun` 50 passed，1 warning（既有警告）。
  - `git diff --check`：无 whitespace error，仅 `domain_pack/schema_desc/relations.yaml` 的 Windows LF→CRLF 提示。
  - 召回诊断：formal allow 8 条 expected_tables 15/15、expected_columns+expected_metrics 16/18、multi_table JoinPath 3/3；challenge schema/join 14 条 expected_tables 29/29、items 29/33、JoinPath 6/6；diagnostic schema/join 24 条 expected_tables 54/54、items 54/62、JoinPath 14/14。
- 遗留：
  - M9 未接真实 Milvus / embedding 模型，`MilvusVectorIndex` 只作为明确报错的 adapter 占位；后续阶段三 RAG 或 M12 README/smoke 需如实说明实际状态。
  - 派生输出列别名未全部召回为字段：formal miss 为 `conversion_rate`、`coupon_order_count`；challenge / diagnostic 还包括 `root_category`、`avg_price`、`doc_title` 等。这些属于 QueryPlan/SQL alias 或不支持关系诊断范畴，留给 M10/M11/M12 处理。
  - `SchemaGraph` 为保证 M9 recall 目前会补齐命中表全字段；M11 做 local schema prompt 时应再按 QueryPlanStep 做字段裁剪，避免 prompt 噪音。

### Phase 3A M8.5 Diagnostic Benchmark 骨架与旧链路诊断基线（2026-07-23）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/cases/phase3a-diagnostic-benchmark.yaml`、`eval/cases/database-upgrade-challenge.yaml`、`eval/run_eval.py`、`tests/test_phase3a_eval.py`、`eval/reports/phase3a-diagnostic-baseline.md`、`docs/state/AI_CONTEXT.md`、`docs/dev-log.md`、`.agent_work/temp/m8.5-notes.md`、`.agent_work/temp/phase3a-diagnostic-baseline-traces.jsonl`、`.agent_work/temp/m8_5-smoke-compat.md`、`.agent_work/temp/m8_5-smoke-compat-traces.jsonl`
- 关键决策：
  - M8.5 按 proposal v5 采用显式 `--cases + --extra-cases` 多文件组合：`database-upgrade-challenge.yaml` 仍是 16 条 challenge 唯一源，`phase3a-diagnostic-benchmark.yaml` 只维护新增 16 条 extra case；没有复制 challenge，也没有实现完整 `includes`。
  - `eval/run_eval.py` 只扩展多文件合并、case id 全局唯一校验、`source_file`、`configured_pipeline_mode` / `actual_pipeline_mode` 和 Markdown 摘要，不引入历史结果库、HTML dashboard 或复杂 scorer。
  - 旧链路 baseline 下，`metric_mapping_match` / `join_path_match` / `manual` 仍跑旧链路结果层；`plan_structure_match`、`plan_validation_blocked`、`schema_context_*`、`trace_steps_complete` 这类新 pipeline 专属 check 标记 `skipped_due_to_pipeline_mode`，不算 pass，也不算 fail。
  - 16 条 challenge 只补 `phase3a_capabilities`、`phase3a_blocking`、`case_properties`、`security_subtype` 诊断元数据，不改问题、expected_sql、check 或 M8 已冻结 baseline 报告；这样 32 条 diagnostic report 的 capability summary 才能覆盖完整 32 条。
  - local schema prompt extra case 使用 block / warn 分层数据结构：缺关键表字段仍是 block；`max_tables` 超标和无关表噪音先作为 warn 素材，避免 M8.5 把 prompt 精简度膨胀成硬门。
  - 用户确认：本模块没有新增需用户二次确认的方案选择；按 `docs/phase3a-plan.md` M8.5 与 `docs/phase3a-diagnostic-benchmark-proposal-v5.md` 已定方案执行。
- 参考资料：
  - 查阅 `docs/phase3a-plan.md` M8.5、`docs/phase3a-diagnostic-benchmark-proposal-v5.md`、`eval/cases/database-upgrade-challenge.yaml`、`eval/run_eval.py`、`tests/test_phase3a_eval.py`。
  - 借鉴 proposal v5 的 32 条结构、capability 标签、check 类型、pipeline mode 和 skipped 口径。
  - 没有照搬外部项目；未查阅外部参考。
- 验证快照：
  - TDD 红灯：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-red` 为 6 failed / 6 passed，失败点集中在 diagnostic YAML 缺失、`extra_cases` 参数缺失、`skipped_due_to_pipeline_mode` 字段缺失。
  - capability 元数据红灯：`pytest tests\test_phase3a_eval.py::test_challenge_cases_carry_diagnostic_capability_metadata ... pytest-m8_5-red-cap` 失败于 challenge case 缺 `phase3a_capabilities`，随后只补元数据。
  - 聚焦 pytest：`pytest tests\test_phase3a_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-final` 13 passed，1 warning（Starlette TestClient / httpx deprecation，既有警告）。
  - Diagnostic baseline：`python -m eval.run_eval --pipeline-mode baseline --cases eval/cases/database-upgrade-challenge.yaml --extra-cases eval/cases/phase3a-diagnostic-benchmark.yaml --report eval/reports/phase3a-diagnostic-baseline.md --trace .agent_work/temp/phase3a-diagnostic-baseline-traces.jsonl` 输出 total=32、passed=12、failed=10、skipped_due_to_pipeline_mode=10、review_required=3；trace JSONL 22 行，skipped case 不写 trace。
  - Capability summary：schema_retrieval 14 覆盖、join_path 13、query_plan 15、local_schema_prompt 7、trace_steps 6、security_guard 4；旧链路下 local schema / plan / trace 专属 case 按预期 skipped。
  - 旧 smoke 兼容：`python -m eval.run_eval --cases eval/cases/smoke.yaml --report .agent_work/temp/m8_5-smoke-compat.md --trace .agent_work/temp/m8_5-smoke-compat-traces.jsonl` 6/6 passed，skipped=0。
  - 全量 pytest：`pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m8_5-full-final` 44 passed，1 warning（既有 Starlette/httpx）。
  - `git diff --check`：无 whitespace error，仅 Windows LF→CRLF 提示。
- 遗留：
  - `db_sec_003` / `db_sec_004` 在旧链路 diagnostic baseline 下是 `safety_mismatch`，说明当前旧 pipeline 未稳定把“查用户邮箱手机号 / 管理员联系方式”转成 SQL Guard 可拦截的敏感字段 SQL；先作为 baseline 事实保留，不在 M8.5 修安全策略。
  - 10 条 skipped case 等 M9-M11 提供 Schema Retrieval、QueryPlan、local schema prompt 和 trace_steps 后再真正评分；M8.5 不伪装这些能力已实现。
  - M9 应优先消费 `eval/reports/phase3a-diagnostic-baseline.md` 的 capability summary 和失败明细，证明 schema / join / plan 改造具体改善哪些能力。

### Phase 3A M8 回归基线冻结（2026-07-22）

- 改动范围：未提供模块起始 commit，本次按当前工作树变更检查；`eval/run_eval.py`、`tests/test_phase3a_eval.py`、`eval/reports/phase3a-baseline.md`、`eval/reports/phase3a-challenge-baseline.md`、`docs/phase3a-plan.md`、`docs/state/database-current-state.md`、`.agent_work/temp/m8-notes.md`、`.agent_work/temp/phase3a-baseline-traces.jsonl`、`.agent_work/temp/phase3a-challenge-baseline-traces.jsonl`
- 关键决策：
  - M8 只扩展 EvalOps-lite 的 case 结构和 baseline 报告，不引入新 Text2SQL pipeline、Schema Retrieval、QueryPlanStep 或 trace_steps，避免把 M9-M12 的工作提前倒灌。
  - `EvalCase` 前向兼容 `expected_metrics`、`expected_trace_steps`、`pipeline_mode`，但旧 `smoke.yaml` 默认仍是 `pipeline_mode=baseline`，旧 M6 smoke 不需要补新字段。
  - `_score_case()` 从 tuple 改为 `EvalScore`，新增最小 `issue_tags`：`missing_table`、`missing_column`、`safety_mismatch`、`unexpected_error`；补充轻量 `manual` 语义，困难诊断题无论通过或失败都可在报告中标记 `review_required`。这只服务 baseline 和后续对照报告，不扩展成完整 scorer 平台。
  - 10 条 formal 与 16 条 challenge 的最终口径：10 条 formal 是主硬门；16 条 challenge 是 superset，包含 10 条 formal question，额外 6 条用于扩展数据库复杂度诊断。后续每个模块同步跑两套报告。
  - 用户确认：baseline 首轮结果为 8/10 overall、2/2 security blocked、允许类 SQL 6/8；可选项是 ① 按真实 baseline 继续收工整理、② 调整 regression expected columns、③ 先修旧链路别名再重跑。风险分别是保留低于计划门槛的真实旧链路事实、可能弱化后续对照硬门、可能扩大 M8 到旧链路修复。我的建议是选 ①，用户最终确认选 ①。
- 参考资料：未查阅外部参考；本次按 `docs/phase3a-plan.md` M8、`docs/state/database-current-state.md`、`domain_pack/schema_desc/relations.yaml`、`domain_pack/metrics.yaml` 和现有 M6 eval runner 实现，没有照搬参考项目。
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

