# Phase 2 Reference Review（参考项目对照复盘）

> 目的：补上 Phase 2 M2-M6 开发过程中没有系统查阅外部 reference 的复盘缺口，并判断 DataPilot 当前实现是否需要调整。
>
> 结论先行：**当时不逐模块系统查 reference 是可以接受的**，因为 Phase 2 的范围已经由 `docs/phase2-plan.md`、`AGENTS.md` 和 `AI_CONTEXT.md` 明确限定，且多处涉及数据库、安全、评测结构的选择都已经先询问用户确认。但从工程复盘角度看，**M2-M6 少了一轮 reference 对照审查**，现在补查是有价值的：它不会推翻当前实现，但能形成一组后续优化候选，尤其集中在 **pipeline trace、schema selection、SQL governance 解释性、EvalOps 指标粒度、RAG ingest 结构** 这几块。

## 查阅范围

本次按 `docs/phase2-plan.md` 和 `REFERENCE_GUIDE.md` 中 Phase 2 提到的 reference 定位，重点阅读与当前模块直接相关的文件。

| Reference | plan 中对应模块 | 本次实际阅读重点 | 对 DataPilot 的主要价值 |
|---|---|---|---|
| `askdata_agent` | M1、M3、M4 | `askdata_pipeline/text2sql_pipeline.py`、`sql_generation/prompt_builder.py`、`mcp_router/sqlite_executor.py` | Text2SQL 分步骤日志、schema context 约束、执行结果结构 |
| `QueryMind` | M3、M4、M6 | `docs/zh/support/evaluation.md`、`docs/zh/use-cases/sql-governance.md`、`src/QueryMind/tools/run_sql.py`、`tests/test_evaluation_rules.py` | SQL governance 闭环、评测 runner / scorer / report 分层、issue tag 体系 |
| `GustoBot` | M4 | `application/agents/text2sql/workflow.py`、`state.py`、`sql_validation/validators.py`、`kb_ingest/.../processor.py`、`search.py` | Text2SQL workflow 状态字段、RAG ingest / search 的元数据形状 |
| `databao-agent` | M2、M5、M6 | `databao/agent/api.py`、`visualizers/vega_vis_tool.py`、`examples/benchmark_template/benchmark/metrics.py` | Agent API 装配入口、Vega-Lite 展示、DataFrame/LLM Judge 评测 |
| `langchain_data_agent` | M2 | `src/data_agent/graph.py`、`docs/VISUALIZATION.md` | graph 化 SQL→执行→可视化流程、可视化 intent 与执行沙箱边界 |
| `CoreCoder` | M5 | `corecoder-annotated/agent.py`、`context.py` | tool loop、tool result 回写、上下文压缩与 trace/cost 思路 |
| `hello-agents/ch12` | M6 | `code/chapter12/README.md`、`data_generation/运行指南.md` | 评测路径、LLM Judge / Win Rate / 人工验证、报告产物组织 |

## 总体判断

当前 DataPilot 的实现方向**没有需要推翻的地方**。尤其是以下选择，在查阅 reference 后仍然成立：

- **MySQL + SQLAlchemy + Alembic 主路径**：比 reference 中若干 demo SQLite / notebook 路线更接近后端实习项目叙事。
- **SQL Guard 使用 `sqlglot` AST**：比 `askdata_agent`、`GustoBot` 里偏 `startswith SELECT/WITH` 或关键词扫描的轻量方案更可靠，不能退回字符串检查。
- **普通 Python pipeline 先行，不提前上 LangGraph**：`GustoBot` 和 `langchain_data_agent` 的 graph 很适合复杂多节点流程，但当前 Phase 2 只有 SQL 主链路、轻量图表和 smoke eval，提前引入会增加学习和调试成本。
- **AgentResponse 字段先稳定，再扩展内部编排**：这与多个 reference 的输出契约思路一致，适合后续 RAG / Hybrid / EvalOps 继续复用。
- **M6 EvalOps-lite 做 smoke，不冒充完整评测平台**：参考 QueryMind / hello-agents 后更能确认，完整 EvalOps 应该有 dataset validation、checkpoint、issue tag、judge、report 多层结构；Phase 2 只做 6 条 smoke 是合理边界。

但也有一个真实问题：**M2-M6 开发记录里连续写“未查阅外部参考”，长期看会降低参考项目的利用率**。建议以后每个模块至少做一次 10-20 分钟的 reference 对照，结果不一定改代码，但要在 notes 或 `AI_CONTEXT.md` 里说明“借鉴 / 不借鉴”的理由。

## 优化机会

### P1：补强 pipeline trace，而不是立刻改架构

**参考依据**：`askdata_agent` 的 Text2SQL pipeline 会记录 keyword extraction、schema retrieval、prompt context、SQL generation、execution result 等 step log；`QueryMind` 的评测也依赖 agent trace 提取 tool path、run_sql 次数和 final answer。

**当前项目**：DataPilot 已有 `AgentResponse.tool_calls` 和 JSONL trace，`/api/query` 也能记录 SQL Tool 执行结果、耗时、表、列、行数。但 trace 更偏最终产物，缺少中间决策，例如：

- 模板是否命中、命中哪个 template id；
- 未命中模板后 prompt 使用了哪些 schema / few-shot；
- LLM 原始 SQL 与清洗后的 SQL 是否不同；
- SQL Guard 拦截是语法、只读、表权限还是字段权限；
- chart_spec 为什么生成或为什么没有生成。

**建议**：后续在不改变 API 主响应的前提下，为 trace 增加 `steps` 或更细的 `tool_calls.metadata`。这比现在就重构成 LangGraph 更轻，也能直接服务 M6 后续评测和面试讲法。

**风险 / 影响**：trace 字段一旦进入 eval 报告，就会成为长期契约。建议先作为 JSONL 内部字段，不急着写入公开 API schema。

### P1：把模板 SQL 的命中解释做得更可控

**参考依据**：QueryMind 的 SQL governance 会跟踪 SQL family、row grain、repair strategy、drift、best skeleton；它的目标不是“多跑几次”，而是让 SQL 生成过程知道自己在修什么。

**当前项目**：M3/M4 的模板优先策略非常适合 v0，但 smoke 中已经暴露过一个边界：`join_005` 容易被“渠道 + 订单量”模板提前命中，导致 GMV 语义丢失。当前通过换 smoke case 规避是 M6 合理边界，但模板系统后续需要更强的解释性。

**建议**：

- 为模板补 `template_id`、`intent_tags`、`required_keywords`、`negative_keywords`、`metric_priority`；
- 在 trace 中记录 `template_candidates` 和最终选择原因；
- 对 GMV、退款率、订单量这类 KPI 建立“指标优先于泛关键词”的匹配规则。

**风险 / 影响**：这是 NL2SQL 核心行为调整，可能影响已有 M3/M6 smoke 结果。建议作为单独小模块做，先补测试再改模板匹配。

### P1：EvalOps-lite 可增加 issue tag 和 scorer 分层

**参考依据**：QueryMind 的 evaluator 把 `missing_sql`、`execution_error`、`wrong_columns`、`wrong_order_by`、`formatting_only` 等问题拆成 issue tags；databao benchmark 里也分 execution accuracy 与 LLM judge；hello-agents/ch12 强调报告、人工验证和多评价方式。

**当前项目**：`eval/run_eval.py` 已能从 YAML 读取 case，经 FastAPI `TestClient` 调 `/api/query`，最后写 Markdown。评分目前主要是 status、safety、contains/table/columns 等 smoke 检查，适合 M6，但还不够支撑“回归分析”。

**建议**：

- 拆出 `eval/scorers/`：例如 `contract_scorer.py`、`sql_surface_scorer.py`、`result_shape_scorer.py`；
- 给失败增加稳定 `issue_tags`，例如 `status_mismatch`、`safety_mismatch`、`missing_table`、`missing_column`、`answer_fragment_mismatch`、`chart_missing`；
- 报告按 route / role / metric / issue tag 聚合；
- 后续如引入 LLM Judge，先只作为可选 scorer，不替代确定性检查。

**风险 / 影响**：评测结构会成为长期维护资产。不要一次性照搬 QueryMind 的 checkpoint / resume / HTML 报告；先把 scorer 边界和 issue tag 定稳。

### P1：为 Phase 3 RAG 预留 ingest / search 的元数据契约

**参考依据**：GustoBot 的 KB ingest 会把 source table、source id、rewritten content、company/year 等 metadata 写入向量库；search 结果带 `content`、`score`、`source`、`metadata`，并支持 threshold、top_k、source filter、rerank。

**当前项目**：`domain_pack/kb_docs/` 与 `knowledge_docs` 数据表已经存在，M5 `AgentResponse.docs_used` 也已预留，但还没有 RAG ingest / retrieval 主链路。

**建议**：Phase 3 开始前先定义 RAG `DocumentChunk` / `RetrievedDoc` 契约，至少包含：

- `doc_id` / `chunk_id` / `source` / `title`；
- `content` / `score` / `metadata`；
- `route` 使用时写入 `docs_used`；
- eval case 可检查 `expected_docs` 或 `expected_sources`。

**风险 / 影响**：RAG 存储选型（ChromaDB / Milvus / SQLite FTS / in-memory）会影响数据迁移和本地环境。`AI_CONTEXT.md` 已记录 Milvus 本地暂不可用，Phase 3 不应临时降级后再假装正式方案，需要先确认主路径。

### P2：演示页增加“解释性信息”，暂不扩成复杂前端

**参考依据**：databao-agent 和 langchain_data_agent 都重视 table / chart / text 多模态展示；QueryMind 的 tool result metadata 也会带 row_count、columns、executed_sql，方便 UI 和评测消费。

**当前项目**：`demo/streamlit_app.py` 已能展示 answer / SQL / table / chart / trace，这对 M6 足够。

**建议**：后续只加小而稳的展示能力：

- SQL 面板显示 `tables_used`、`safety_status`、`error_type`；
- chart 无法生成时显示“当前结果不适合自动图表”的状态；
- 增加一次性查询历史和复制 SQL；
- RAG 后显示 `docs_used` 的标题 / 来源 / 分数。

**风险 / 影响**：前端容易吞掉后端时间。演示页应服务面试讲解，不要变成单独 UI 大项目。

### P2：SQL Tool 可以补结果保存/预览策略，但不急

**参考依据**：QueryMind 的 `run_sql` 会把 DataFrame 转 UI component、保存 CSV，并把 row_count、columns、executed_sql 放入 metadata；databao-agent 也有 rows_limit 和多 executor 配置。

**当前项目**：`engine/tools/sql_tool.py` 已返回 columns / rows / row_count / elapsed_ms / tables_used / blocked_reason，满足 Phase 2。

**建议**：数据量变大后再考虑：

- `preview_rows` 与 `total_row_count` 分离；
- 大结果写临时 CSV 或 artifact；
- API 返回 rows limit，同时 trace 记录是否 truncated。

**风险 / 影响**：这会影响 API 契约和 demo 展示。当前 seed 数据量小，不需要提前做。

### P2：上下文 / 成本统计可以细化，但不该学习 CoreCoder 的完整 agent loop

**参考依据**：CoreCoder 的 agent loop 清楚展示了 LLM tool_call、tool result 回写、max_rounds、安全中断和 context compression。它适合编码 agent，但 DataPilot 是数据分析 agent。

**当前项目**：M5 已有 `CostInfo` 字段，但真实 LLM usage 仍是 `None/0/0`；trace 也还没有 token / cost 聚合。

**建议**：等 provider 返回 usage 后，补：

- `model`、`prompt_tokens`、`completion_tokens`、`total_tokens`；
- 每步 `elapsed_ms`；
- eval report 聚合平均延迟和 token。

**风险 / 影响**：不要把 DataPilot 改造成通用工具调用 agent；只借鉴 telemetry 思路。

## 不建议现在做的事

- **不要把 SQL Guard 退回字符串前缀检查**：reference 中的轻量校验只能作为 demo guard，DataPilot 当前 AST 检查更适合项目定位。
- **不要现在引入 Neo4j / pgvector / Milvus / 多数据源**：GustoBot、askdata_agent、langchain_data_agent 的复杂依赖适合成熟系统，不适合 Phase 2 收尾。
- **不要马上上 LangGraph**：等 RAG + Hybrid + 多步 tool loop 真的让普通 Python pipeline 难维护时再迁移。
- **不要把 M6 smoke 包装成完整 benchmark**：当前 6 条 smoke 是回归哨兵，不是 QueryMind 级评测平台。
- **不要扩 UI 大范围功能**：demo 应该展示后端能力，而不是抢阶段三的研发预算。

## 模块级复盘

### M2 API 与后端工程基础

M2 没查 `databao-agent` / `langchain_data_agent` 可以理解，因为当时目标是 FastAPI 资源接口、分页、异常和 DB session，参考项目的价值有限。补查后得到的主要启发是：API 层应尽量提供稳定入口和配置装配方式，DataPilot 目前的 `app/api/resources.py`、`app/db/session.py`、统一响应结构方向没问题。

可优化点：后续如果数据源变多，可以参考 `databao-agent` 的 `agent(domain, executor, visualizer, cache, rows_limit)` 装配思路，但当前不需要抽象 executor 工厂。

### M3 v0 模板 SQL 闭环

M3 没查 `askdata_agent` / `QueryMind` 的影响更明显。当前模板白名单路线是安全且适合 v0 的，但 reference 显示：Text2SQL 系统最好把 schema context、SQL family、执行结果和修复信号显式记录下来。

可优化点：优先补模板命中解释和 trace，而不是扩大 SQL 生成能力。

### M4 NL2SQL 最小链路与安全

M4 的 DeepSeek provider、domain schema、few-shot、RBAC 和 SQL Guard 主方向正确。查阅后反而确认：DataPilot 当前安全层比若干 reference 的字符串校验更强，不能为了简单而降级。

可优化点：prompt_builder 可借鉴 `askdata_agent` 的硬约束表达，把“只能使用 schema 中给出的表 / 字段 / 关系，不得编造字段”写得更显式；SQL Guard 的 blocked reason 可以更适合用户和 eval 消费。

### M5 AgentResponse、Trace、Tool 与图表

M5 没查 `databao-agent` / `CoreCoder` 仍然可接受，因为当前实现已经覆盖 AgentResponse、SQL Tool、chart_spec、trace。但 reference 表明，tool metadata 和 telemetry 后续很有价值。

可优化点：增强 trace step 与 chart 生成原因；真实 usage 出来后补成本统计。

### M6 EvalOps-lite 与演示收尾

M6 没查 `QueryMind` / `hello-agents/ch12` / `databao-agent` 是最值得补的一块。当前 smoke runner 范围是对的，但参考项目说明：长期 EvalOps 需要 scorer 分层、issue tag、报告聚合、可恢复运行和人工检查入口。

可优化点：下一轮 EvalOps 扩展先做 issue tags + scorer modules + report grouping，不要一口气做完整平台。

## 建议行动顺序

1. **短期文档动作**：在 `AI_CONTEXT.md` 或后续计划中记录“Phase 2 已补查 reference，本报告为依据”，避免之后误以为 M2-M6 完全没有参考依据。
2. **Phase 3 开工前决策**：确认 RAG 主路径（ChromaDB / 其他）和 `RetrievedDoc` 契约；这是会影响架构和评测结构的选择，应先让用户确认。
3. **优先做轻量 trace 增强**：记录 template id、prompt schema scope、guard decision、chart decision，服务调试和 eval。
4. **再做 EvalOps scorer 分层**：把 M6 smoke 从“字符串判断”升级为“稳定 issue tag + 聚合报告”。
5. **最后考虑架构迁移**：当 SQL + RAG + Hybrid 的步骤复杂到普通函数难读时，再评估 LangGraph。

## 最终结论

**当前项目没有需要立即返工的设计错误**。此前 M2-M6 没有逐模块查 reference，在“严格按当前模块计划交付”的前提下是合理的；但从长期质量看，reference 应该成为每个模块的轻量复盘动作。

本次查阅后，最值得进入后续计划的不是“大换架构”，而是三类小而关键的增强：**trace 更细、eval 更可诊断、RAG 契约先定稳**。这些改动能让 DataPilot 更像一个可面试、可解释、可回归的 AI 数据分析后端项目。
