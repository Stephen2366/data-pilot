# DB-GPT 参考项目解读与 DataPilot 借鉴报告

> 生成日期：2026-07-23  
> 参考项目：`D:\.Work\Practice\Python-Practice\references\DB-GPT`  
> DataPilot 对照基准：`docs/AI_CONTEXT.md` 当前状态、`docs/phase3a-plan.md`、`D:\.Work\Practice\Python-Practice\LEARNING_ROADMAP_v3.md`

## 0. 结论先行

DB-GPT 是一个完整的 **Agentic AI 数据分析平台**，不是一个轻量 Text2SQL demo。它的目标是连接数据库、文件、知识库、多模型、Agent、AWEL 工作流、Skill、沙箱和 Web 产品形态，最终支撑“AI + Data 应用平台”。从工程完整度看，它明显强于当前 DataPilot；但从 **求职倒推、学习闭环、可解释演进、面试可讲性** 看，不建议放弃 DataPilot 直接基于 DB-GPT 重开。

更合理的策略是：

1. **DataPilot 继续作为主项目**：保留现有 FastAPI + MySQL + SQL Guard + EvalOps-lite + Phase 3A Text2SQL 深化路线。
2. **DB-GPT 作为中后期参考库**：重点借鉴它的 AWEL 编排表达、Schema Retriever 组织、Action/Skill 抽象、沙箱分层、评测服务化思路。
3. **不要照搬 DB-GPT 平台底座**：DB-GPT 的 package、服务、依赖、UI、Agent、多数据源能力都很重，直接重开会吞掉 DataPilot 当前最值钱的“从 v0 到 v1 到可诊断 Text2SQL 的成长线”。
4. **可以在 M9-M12 局部吸收**：DB-GPT 的 `DBSchemaAssembler/DBSchemaRetriever`、AWEL DAG、`ActionOutput`、Skill 包格式，都可以变成 DataPilot 的实现参考或面试对照材料。

一句话判断：**DB-GPT 是“成熟平台范本”，DataPilot 应该学习它的结构，不应该变成它的二次开发壳。**

## 1. 本次阅读范围

这次没有通读 DB-GPT 全仓库，而是按 DataPilot roadmap 相关性抽样阅读。重点文件包括：

| 范围 | 文件 |
|---|---|
| 项目定位 | `README.zh.md`、`README.md`、`DB-GPT-Core-Code-Design-Analysis.md`、`pyproject.toml` |
| 包分层 | `packages/dbgpt-core`、`packages/dbgpt-app`、`packages/dbgpt-serve`、`packages/dbgpt-ext`、`packages/dbgpt-client`、`packages/dbgpt-sandbox` |
| AWEL 工作流 | `packages/dbgpt-core/src/dbgpt/core/awel/dag/base.py`、`packages/dbgpt-core/src/dbgpt/core/awel/operators/base.py`、`examples/awel/simple_dag_example.py`、`examples/awel/simple_nl_schema_sql_chart_example.py` |
| 数据库问答 / Text2SQL | `packages/dbgpt-app/src/dbgpt_app/scene/chat_db/auto_execute/chat.py`、`prompt.py`、`out_parser.py`、`scene/base_chat.py` |
| Schema RAG | `packages/dbgpt-ext/src/dbgpt_ext/rag/assembler/db_schema.py`、`retriever/db_schema.py`、`operators/db_schema.py`、`operators/schema_linking.py`、`examples/rag/simple_dbschema_retriever_example.py` |
| Agent / Action / Skill | `packages/dbgpt-core/src/dbgpt/agent/core/action/base.py`、`agent/core/base_agent.py`、`agent/skill/base.py`、`agent/skill/loader.py`、`agent/skill/manage.py`、`skills/README.md` |
| 沙箱 | `packages/dbgpt-sandbox/src/dbgpt_sandbox/sandbox/main.py`、`user_layer/service.py`、`control_layer/control_layer.py`、`execution_layer/runtime_factory.py` |
| 评测 | `packages/dbgpt-serve/src/dbgpt_serve/evaluate/*`、`packages/dbgpt-client/src/dbgpt_client/evaluation.py`、`examples/client/client_evaluation.py` |

DataPilot 对照文件包括：`app/schemas/agent.py`、`app/api/query.py`、`engine/tools/sql_tool.py`、`engine/sql_guard/*`、`engine/trace/recorder.py`、`eval/reports/phase3a-diagnostic-baseline.md`、`docs/phase3a-plan.md` 和 roadmap v3。

## 2. DB-GPT 项目本身解读

### 2.1 项目定位

DB-GPT 的 README 把自己定位为 **开源 Agentic AI 数据分析智能助手**。它不是只做“自然语言转 SQL”，而是覆盖：

- 多数据源：数据库、CSV、Excel、文档、知识库。
- 多模型：本地模型、OpenAI 兼容模型、国内外多个 provider。
- 数据分析 Agent：任务规划、SQL 生成、Python 代码执行、图表、报告。
- Workflow：AWEL，把分析流程写成 DAG。
- Skill：把数据分析、财报分析、CSV 分析等流程沉淀成可复用技能包。
- Sandbox：隔离执行 Python / shell / 浏览器等代码任务。
- Web 平台：提供应用、数据源、知识库、Flow、Agent、评测等管理界面。

所以 DB-GPT 更像“AI 原生数据应用平台”，而不是“一个项目里的一条 NL2SQL pipeline”。

### 2.2 包分层

DB-GPT 使用 uv workspace，顶层 `pyproject.toml` 中版本为 `0.8.1`，核心包拆成：

| 包 | 作用 | 对 DataPilot 的启发 |
|---|---|---|
| `dbgpt-core` | 核心抽象：Agent、AWEL、LLM、RAG、Datasource、Storage、Model、Util | 抽象层不要依赖具体业务 |
| `dbgpt-ext` | 具体扩展：数据库连接、向量库、RAG 实现、LLM provider、可视化 | 具体 provider 放 adapter 层 |
| `dbgpt-serve` | 服务层：Agent、Datasource、RAG、Prompt、Flow、Evaluate 等 API | 后期 EvalBench 可服务化 |
| `dbgpt-app` | 应用层：FastAPI app、业务 scene、openapi、初始化 | 业务场景和底层引擎分开 |
| `dbgpt-client` | Python SDK 和 API client | 后期可给 DataPilot 做 SDK，但不是 P0 |
| `dbgpt-sandbox` | 独立沙箱服务 | 任意代码执行必须单独隔离 |
| `dbgpt-accelerator` | 推理加速 | DataPilot 当前不需要 |

这个分层最值得学习的是 **抽象与实现分离**：core 定义协议，ext 放 provider，serve 暴露 API，app 组合业务场景。DataPilot 现在的 `engine/` 与 `domain_pack/` 其实已经在走同一类方向，只是规模更小。

## 3. 关键设计详细解读

### 3.1 AWEL：把 Agent 工作流表达成 DAG

AWEL 的核心在 `dbgpt.core.awel`。`DAG` 管理节点、上下游关系、root/leaf/trigger；`BaseOperator` 在 `DAGNode` 基础上增加执行能力；`>>` 和 `<<` 运算符用于声明依赖关系。

典型例子：

```python
with DAG("simple_dag_example") as dag:
    trigger = HttpTrigger("/examples/hello", request_body=TriggerReqBody)
    map_node = RequestHandleOperator()
    trigger >> map_node
```

`simple_nl_schema_sql_chart_example.py` 展示了更接近 DataPilot 的链路：

```text
HttpTrigger
  -> RequestHandleOperator
  -> query_operator
  -> SchemaLinkingOperator
  -> prompt_join_operator
  -> SqlGenOperator
  -> SqlExecOperator
  -> ChartDrawOperator
```

这和 DataPilot Phase 3A 的远期链路高度相似：

```text
question -> schema_retrieval -> schema_graph/join_path -> query_plan
-> local_schema_prompt -> sql_generation -> sql_guard -> sql_execution -> trace
```

但注意边界：DataPilot 当前阶段计划明确 **Phase 3A 不引入 LangGraph / 多智能体 / 复杂 workflow**。所以 DB-GPT 的 AWEL 现在不应该直接引入，只适合在 M11/M12 写 `trace_steps` 和 README 架构图时作为“未来可 DAG 化”的参考。

具体借鉴方式：

- M11 的 `TraceStep` 字段可以参考 AWEL 的 `DAGContext` 思路，保留 `step_index / step_type / parent_step_id`。
- M12 对照报告可以画成 DAG 风格，但代码仍保持普通 Python pipeline。
- 等后续 Hybrid 阶段出现 Router + SQL + RAG + Report 多节点后，再考虑 LangGraph 或自定义 DAG，而不是在 Text2SQL 单链路阶段上 AWEL。

### 3.2 Text2SQL 场景：Scene + Prompt + Parser + Action

DB-GPT 的数据库自动执行场景在：

- `scene/chat_db/auto_execute/chat.py`
- `scene/chat_db/auto_execute/prompt.py`
- `scene/chat_db/auto_execute/out_parser.py`

它的流程大致是：

1. `ChatWithDbAutoExecute.generate_input_values()` 根据用户问题和数据库名获取 schema summary。
2. prompt 要求模型只使用给出的表结构，返回 JSON，字段包括 `thoughts`、`direct_response`、`sql`、`display_type`。
3. `DbChatOutputParser` 解析模型输出。如果是纯 SQL，兼容为 `SqlAction`；如果是 JSON，就提取 SQL 和展示类型。
4. `parse_view_response()` 执行 SQL，把结果 DataFrame 转成前端可识别的 chart-view 内容。

这个设计的价值：

- 把 prompt、解析、执行、展示分成了不同类。
- SQL 输出不是纯文本，而是结构化 JSON。
- 模型需要同时决定 SQL 和展示方式。
- schema summary 可以按问题检索，不必每次塞全量表结构。

但它也有 DataPilot 不应照搬的点：

- `parse_view_response()` 里根据模型输出直接执行 SQL，安全边界不如 DataPilot 的 `SQLTool` 明确。
- prompt 中要求“不要编造表字段”，但最终安全不应依赖 prompt。
- DB-GPT 的 scene 模式为通用平台服务，代码路径比 DataPilot 目前需要的重很多。

DataPilot 更好的落点是：保留当前 `run_sql_tool()` 的硬边界，把 DB-GPT 的 JSON 输出格式和 display_type 决策吸收到 M10/M11 的 `QueryPlanStep` 与 chart decision。

### 3.3 DBSchema RAG：表级召回 + 字段级补充

DB-GPT 的 DB schema 检索相关文件集中在 `dbgpt-ext/rag`：

- `DBSchemaAssembler` 从数据库连接构造 schema chunks，并持久化到向量库。
- `DBSchemaRetriever` 根据 query 检索表级 chunks；如果某张表字段很多，会再去字段向量库检索字段 chunks。
- `DBSchemaRetrieverOperator` 把 retriever 封装成 AWEL operator。
- `SchemaLinkingOperator` 用 LLM 对 schema 做二次筛选。

这对 DataPilot M9 非常有价值。特别是 `DBSchemaRetriever` 的两层结构：

```text
先召回 table chunk
如果 table 被拆成 separated chunk
再按 table metadata 去 field vector store 召回字段 chunk
最后反序列化成 CREATE TABLE 风格的局部 schema
```

DataPilot roadmap v3 要求 M9 做 `field_doc / metric_doc / relation_doc`。DB-GPT 的实现主要覆盖 table / field，对 metric 和 relation 没有 DataPilot 计划得那么业务化。可借鉴的不是字段命名，而是：

- `SchemaDocument` 可以有 `doc_type`，分表、字段、指标、关系。
- 表级召回和字段级召回可以分开，避免大表字段太多时 prompt 爆炸。
- 检索结果需要 metadata，可用于过滤和二次字段召回。
- retriever 入口应该和向量库解耦，测试环境可以用 memory vector index，生产再接 Milvus。

DataPilot 应优先实现自己的 `domain_pack` 驱动文档构建，而不是从真实数据库 DDL 直接抽。原因是 DataPilot 的面试亮点包括业务指标口径、关系口径、宽表 vs 星型表选择，这些不是普通 DDL 能完整表达的。

### 3.4 Agent / Action：把模型输出转成可执行动作

DB-GPT 的 `Action` 抽象在 `agent/core/action/base.py`。核心对象是：

- `Action`：定义动作名、资源依赖、输出 schema、渲染协议、解析 AI JSON、执行 `run()`。
- `ActionOutput`：记录动作结果，包括 `content`、`is_exe_success`、`view`、`action_input`、`thoughts`、`observations`、`next_speakers`、`terminate`、`memory_fragments` 等。
- `ConversableAgent`：负责 Agent 间 send/receive、LLM 调用、memory、context management、resource prompt、action 执行。

这个抽象比 DataPilot 当前的 `ToolCallTrace` 丰富得多。它服务的是多 Agent 对话和通用工具执行，不只是一次 SQL 查询。

DataPilot 当前不应该搬整套 Agent 框架，但可以借鉴两点：

1. **Tool / Action 输出要统一**  
   目前 DataPilot 的 `ToolCallTrace` 有 `tool_name/status/latency/sql/tables/error_type/message`。到 Hybrid 阶段，可以扩展成更接近 `ActionOutput` 的结构，例如加入 `observation`、`artifact`、`retryable`、`next_step_hint`。

2. **模型输出 schema 应该由动作反推**  
   DB-GPT 的 `Action.ai_out_schema` 会把 Pydantic 模型转成示例 JSON，提示模型按格式输出。DataPilot M10 的 `QueryPlanStep` 也可以这么做：用 Pydantic 字段描述生成 prompt schema，而不是手写散装 JSON 示例。

### 3.5 Skill：把分析能力打包为可复用资源

DB-GPT 的 Skill 机制包含：

- `SkillMetadata`：名称、描述、版本、类型、标签。
- `Skill`：prompt_template、required_tools、required_knowledge、actions、config。
- `SkillLoader`：支持 JSON/YAML/Markdown/SKILL.md。
- `SkillManager`：注册、按名称或类型查找、获取脚本和引用文件、执行 skill script。
- `skills/` 目录：CSV 分析、财报分析、Walmart 销售分析等示例。

这和 DataPilot roadmap 中后期的 Skill 封装很贴近。但对当前阶段来说，Skill 仍然是 P2，不应该抢 M9-M12 主线。

最适合 DataPilot 的借鉴方式是：后期把 `domain_pack/` 升级成“业务分析 Skill 包”的形态，而不是引入 DB-GPT Skill Manager。比如：

```text
domain_pack/ecommerce_ops/
  skill.yaml              # 名称、适用场景、需要的 tools / docs / metrics
  metrics.yaml
  schema_desc/
  sql_examples/
  kb_docs/
  report_templates/
```

这样可以保留 DataPilot 的业务迁移故事：换行业不是改 engine，而是换一个 domain skill pack。

### 3.6 Sandbox：任意代码执行必须独立隔离

DB-GPT 的 sandbox 是独立 package，有 user layer、control layer、execution layer：

- `UserLayer` 暴露 FastAPI 接口：connect、configure、execute、manual、status、get_file。
- `ControlLayer` 管理 task、session、lock、connect/configure/execute/disconnect。
- `RuntimeFactory` 优先选择 Docker、Podman、Nerdctl，只有显式允许时才使用 local runtime。
- `SessionConfig` 里能配置工作目录、内存、CPU、环境变量、网络。

这点对 DataPilot 的启发很明确：

- SQL 执行和 Python 任意代码执行是两类安全等级。
- DataPilot 当前只需要 SQL sandbox，不需要代码 sandbox。
- 如果未来做“自动写 Python 分析代码”，必须像 DB-GPT 一样单独隔离，不能在 FastAPI 进程里直接 `exec`。

短期可借鉴的是安全思维，不是功能本身。DataPilot 当前的 `SQL Guard + SQLTool` 已经是必要边界；后续若做 Python 分析 Agent，再单独设计 sandbox。

### 3.7 Evaluation：评测服务化与多指标

DB-GPT 的 evaluate 服务支持：

- `EvaluateServeRequest`：scene_key、scene_value、datasets、evaluate_metrics、context、parallel_num 等。
- scene 类型：`recall`、`app`、`dataset`。
- RAG recall 评测：HitRate、MRR、Similarity。
- App answer 评测：AnswerRelevancy 等。
- DAO 持久化 evaluate task。
- client SDK 通过 `/evaluate/evaluation` 触发评测。

这比 DataPilot 当前的 EvalOps-lite 更平台化，但 DataPilot 的路线是先在主项目里轻量跑通，再拆独立 EvalBench。两者不冲突。

DataPilot 可借鉴：

- 评测请求结构里保留 `scene_key / scene_value / context / metrics / datasets`。
- EvalBench 独立项目后，可以把 target 抽象成 `scene_key=datapilot_api` 或 adapter。
- RAG 阶段可以补 HitRate/MRR/Similarity，不要只靠人工判断。

暂时不要借鉴：

- 数据库持久化 evaluate task。
- Web 管理评测任务。
- 多模型 benchmark 文件体系。

这些都属于阶段四或更后面。

## 4. DB-GPT 与 DataPilot 的核心差异

| 维度 | DB-GPT | DataPilot 当前 / roadmap |
|---|---|---|
| 项目定位 | 通用 AI + Data 平台 | 求职倒推的企业数据分析 Agent |
| 规模 | 多 package、多服务、多 UI、多 provider | 单业务域，FastAPI + engine + domain_pack |
| 主线 | 多数据源 + Agent + Workflow + Skill + Sandbox | NL2SQL + RAG + Hybrid + EvalOps |
| Text2SQL | scene/prompt/parser/action + schema summary | 模板优先，LLM 兜底，Phase 3A 加 schema_retrieval/query_plan/trace |
| SQL 安全 | 有隐私/沙箱/连接器治理思路，但抽样路径中 SQL 执行安全边界不如 DataPilot 明确 | `SQLTool` 强制先 Guard，再执行；RBAC 与敏感字段策略已实现 |
| Schema 检索 | DB schema assembler/retriever，表级和字段级向量检索 | 计划做 field_doc / metric_doc / relation_doc，更贴业务口径 |
| Workflow | AWEL DAG，可视化 workflow | Phase 3A 暂不用 LangGraph/DAG，后续 Hybrid 再上 |
| Agent | 通用 multi-agent + memory + action + resource | 当前是单 pipeline，后续再封装 tools/skills |
| Skill | 完整 Skill Manager + loader + scripts | roadmap P2，加分项 |
| 沙箱 | 独立代码执行服务 | 当前只做 SQL sandbox |
| 评测 | evaluate service + metrics + DAO | EvalOps-lite 已有 YAML/Markdown/Trace，后续独立 EvalBench |
| 面试叙事 | “参与/二开一个大平台” | “从 0 到 1 搭业务 Agent，并用评测驱动迭代” |

关键判断：DB-GPT 更全，DataPilot 更聚焦。对你找实习而言，**聚焦和可讲清楚比平台大而全更重要**。

## 5. DataPilot 可以借鉴什么

### 5.1 M9 Schema Retrieval 与 JoinPath

借鉴 DB-GPT：

- `DBSchemaAssembler` 的“从连接器构建 schema chunks，再持久化到向量库”。
- `DBSchemaRetriever` 的“表级召回 + 字段级补充”。
- metadata filter 思路：按表名、doc_type、part 做二次检索。

DataPilot 落地方式：

- `document_builder.py` 从 `domain_pack/schema_desc/`、`metrics.yaml`、`relations.yaml` 构建 `SchemaDocument`。
- `doc_type` 至少包括 `field_doc / metric_doc / relation_doc`，不要只做 DB-GPT 的 table/field。
- `retriever.py` 保留 keyword + vector 两路，测试用 in-memory vector index，生产预留 Milvus adapter。
- `graph.py` 根据命中 docs 生成局部 `SchemaGraph` 和 `JoinPath`。

### 5.2 M10 QueryPlanStep

借鉴 DB-GPT：

- `Action.ai_out_schema` 自动生成 JSON 输出格式的思路。
- `ActionOutput` 中 `observations / action_reason / is_exe_success` 这类诊断字段。

DataPilot 落地方式：

- `QueryPlanStep` 用 Pydantic 定义字段，prompt 中直接引用 schema 示例。
- plan validation 输出 `PlanValidationResult(is_valid, issue_tags, errors)`。
- 不暴露原始 CoT，只保存 `reason_summary` 或 `purpose`。
- 多步骤 plan 结构预留，但 Phase 3A 只允许一个可执行 SQL step。

### 5.3 M11 Trace Steps

借鉴 DB-GPT：

- AWEL 的 DAG node、DAG context、task output 思路。
- BaseChat / root_tracer 的分段 trace 思路。

DataPilot 落地方式：

- `TraceStep(name, step_index, step_type, status, input_summary, output_summary, latency_ms, error_type, metadata, parent_step_id)`。
- 每步 trace 写 JSONL，不先塞进公开 API 响应。
- 失败时记录是 schema_retrieval、plan_validation、sql_generation、sql_guard 还是 sql_execution 出错。

### 5.4 M12 对照报告

借鉴 DB-GPT：

- evaluate service 的 `scene_key / datasets / metrics / context` 抽象。
- RAG metrics 中 HitRate、MRR、Similarity 的分层。

DataPilot 落地方式：

- Phase 3A 仍输出 Markdown，不做服务化。
- 报告里按 capability 汇总：schema_retrieval、join_path、query_plan、local_schema_prompt、trace_steps、security_guard。
- 后续 EvalBench 独立项目再把 DataPilot eval runner 包成 adapter。

### 5.5 后期 RAG / Hybrid / Skill

借鉴 DB-GPT：

- Skill 包目录：`SKILL.md + references + scripts + templates`。
- 沙箱的 user/control/execution 三层。
- Agent `Action` 和 `Resource` 分离。

DataPilot 落地方式：

- RAG 阶段先实现企业知识库来源引用，不做完整 Skill。
- Hybrid 阶段再考虑把 SQL/RAG/Report 封装成 action 或 tool。
- Skill 阶段把 `domain_pack` 升级成可迁移业务包。
- 如果未来允许 Python 代码分析，必须先独立 sandbox，不进 FastAPI 主进程。

## 6. 不建议照搬什么

1. **不照搬 monorepo 分包**  
   DB-GPT 的 workspace 分包适合平台团队。DataPilot 现在照搬会造成认知负担，也不利于面试讲“我自己实现了什么”。

2. **不提前引入 AWEL / Workflow UI**  
   Phase 3A 是 single-step Text2SQL pipeline。此时上 DAG 会把主线复杂化。

3. **不提前做多数据源**  
   DataPilot 当前电商/SaaS MySQL 数据域已经足够支撑 Text2SQL 深化。多源连接会稀释主线。

4. **不提前做任意代码 sandbox**  
   代码执行安全成本很高。没有 Python 分析 Agent 需求前，不做。

5. **不把 Skill 写成主线能力**  
   Skill 是包装和复用层，不是 NL2SQL 正确率提升的核心。

6. **不弱化 SQL Guard**  
   DB-GPT prompt 中强调只用给定 schema，但 DataPilot 必须继续保持 sqlglot AST + RBAC + 敏感字段拦截的硬门。

## 7. 有没有必要放弃 DataPilot，直接基于 DB-GPT 重开？

结论：**没有必要，也不建议。**

理由如下。

### 7.1 DataPilot 的简历价值来自“从 0 到 1 的工程闭环”

你当前的 DataPilot 已经有：

- FastAPI 后端。
- MySQL + SQLAlchemy + Alembic。
- 14 表数据底座。
- 模板 SQL + LLM SQL。
- SQL Guard：只读、RBAC、敏感字段。
- AgentResponse Pydantic 结构化输出。
- SQL Tool、chart_spec、JSONL Trace。
- EvalOps-lite、32 条 diagnostic benchmark、Phase 3A baseline。

这条演进线很适合面试讲：为什么先模板、为什么加 Guard、为什么做 trace、为什么冻结 baseline、为什么再做 schema retrieval 和 query plan。直接换 DB-GPT 会把这条学习与工程取舍链切断。

### 7.2 基于 DB-GPT 重开会让“你的实现”变模糊

如果直接二开 DB-GPT，面试官很容易追问：

- 哪些是你写的？
- DB-GPT 原本就有 Agent、Skill、AWEL、Sandbox，你改了什么？
- 你理解它这么大的架构吗？
- 为什么不用它原生的数据源、评测、Skill？

这会把面试从“你做了一个可解释业务 Agent”变成“你能不能驾驭一个大平台二开”。对实习求职不划算。

### 7.3 DB-GPT 的平台复杂度会拖慢 8 月底核心交付

roadmap 的硬目标是 8 月底完成核心项目，9 月上包装，9 月中下开始集中投递。DB-GPT 的依赖、Web、服务、模型、向量库、沙箱、Skill 都很重。即使能跑起来，也很容易把时间花在配置和理解平台上，而不是打磨 DataPilot 的主线能力。

### 7.4 DataPilot 与 DB-GPT 的目标不同

DataPilot 的目标不是做“开源通用平台”，而是做一个可演示、可评测、可解释失败归因的企业数据分析 Agent。它只需要覆盖一个业务域，但要把关键链路讲深。

除非目标变成“我要参与 DB-GPT 生态二开，做一个 DB-GPT app/plugin 并投相关岗位”，否则不应该重开。

## 8. 什么时候可以考虑基于 DB-GPT 做支线？

可以，但只建议作为支线或后期加分项：

1. **阶段五包装之后**  
   DataPilot 主线完成、README/视频/简历都稳定后，可以做一个“DB-GPT 对照 demo”。

2. **作为参考项目复盘**  
   在面试问“有没有看过成熟数据 Agent 项目”时，可以讲：我读过 DB-GPT，借鉴了它的 schema retriever、workflow、skill、sandbox，但 DataPilot 因为求职主线选择了轻量自研。

3. **作为 EvalBench adapter 的外部目标**  
   如果后续想证明 EvalBench 可评测多个 Agent，可以写一个 DB-GPT adapter，但这属于阶段四/五之后。

4. **作为 Skill/MCP 后期原型**  
   DataPilot 自己的 Skill 设计可以参考 DB-GPT 的 `SkillMetadata + required_tools + references/scripts/templates`。

## 9. 推荐的具体借鉴路线

### 近期：M9

- 参考 `DBSchemaAssembler` 和 `DBSchemaRetriever`。
- 实现 DataPilot 自己的 `SchemaDocument`、`SchemaHit`、`SchemaGraph`、`JoinPath`。
- 保留 `field_doc / metric_doc / relation_doc`，这是 DataPilot 比 DB-GPT 更贴业务的一点。

### 近期：M10

- 参考 `Action.ai_out_schema`。
- 用 Pydantic Schema 自动生成 QueryPlan JSON 示例。
- validation 失败必须产生 issue tag，不进入 SQL 生成。

### 近期：M11

- 参考 AWEL 的 step/DAG context 思路。
- 增加 `trace_steps`，但不引入 AWEL 或 LangGraph。
- `force_new_pipeline=true` 只影响评测链路，默认生产链路继续模板优先。

### 近期：M12

- 参考 evaluate service 的 metrics/context 结构。
- 继续输出 Markdown 对照报告。
- 报告重点放在“局部 schema prompt 缩小多少、哪些 join path 被识别、哪些 issue tag 改善”。

### 中期：RAG / Hybrid

- 参考 DB-GPT RAG 的 assembler/retriever/operator 分层。
- RAG 入库和检索仍先做 DataPilot 业务文档，不做多源文件平台。
- Hybrid 出现多节点后，再考虑 LangGraph 或自定义 graph。

### 后期：Skill / Sandbox

- 把 `domain_pack` 包装成业务 Skill。
- 如要执行 Python 分析脚本，参考 DB-GPT sandbox 单独服务化。
- 不在主 API 进程里执行任意代码。

## 10. 面试讲法

可以这样讲 DB-GPT 对 DataPilot 的影响：

> 我读过 DB-GPT 这类成熟 AI + Data 平台，它的核心启发是：数据 Agent 不能只是一段 prompt，要有 schema retrieval、workflow、tool/action、sandbox 和 evaluation。DataPilot 没有直接基于 DB-GPT 重开，因为我的目标是做一个求职可讲清楚的业务 Agent，所以我保留了轻量自研主线。但我借鉴了它的表级/字段级 schema retrieval、DAG 化 trace、Skill 包结构和沙箱分层，并把这些能力按阶段吸收到 DataPilot 的 M9-M12 和后续 Hybrid/RAG 中。

如果面试官追问“为什么不用 DB-GPT 现成的”，可以回答：

> DB-GPT 是平台级项目，能力很全，但也会让项目边界和个人贡献变模糊。DataPilot 的价值在于从数据建模、SQL Guard、结构化响应、trace、eval 到新旧链路对照都是自己实现和验证的，能讲清楚每一步为什么做、怎么测、失败怎么归因。DB-GPT 更适合作为架构参考，而不是直接当底座。

## 11. 后续阅读清单

如果后续具体模块要查 DB-GPT，建议按下面读，不要全仓库通读。

| DataPilot 阶段 | 优先读 DB-GPT 文件 |
|---|---|
| M9 Schema Retrieval | `dbgpt_ext/rag/assembler/db_schema.py`、`retriever/db_schema.py`、`operators/db_schema.py`、`examples/rag/simple_dbschema_retriever_example.py` |
| M10 QueryPlanStep | `agent/core/action/base.py`、`scene/chat_db/auto_execute/prompt.py`、`out_parser.py` |
| M11 Trace Steps | `core/awel/dag/base.py`、`core/awel/operators/base.py`、`examples/awel/simple_nl_schema_sql_chart_example.py` |
| RAG 阶段 | `dbgpt_ext/rag/knowledge/*`、`retriever/*`、`operators/*` |
| Hybrid / Workflow | `examples/awel/*`、`agent/core/plan/*` |
| Skill 后期 | `agent/skill/*`、`skills/README.md`、`skills/*/SKILL.md` |
| Python 分析沙箱 | `packages/dbgpt-sandbox/src/dbgpt_sandbox/sandbox/*` |
| EvalBench 独立化 | `dbgpt_serve/evaluate/*`、`dbgpt_client/evaluation.py`、`examples/client/client_evaluation.py` |

## 12. 最终建议

DataPilot 不需要推倒重来。继续按当前 roadmap 做 M9-M12，DB-GPT 作为高质量参考项目挂在旁边即可。

优先级建议：

1. **马上借鉴**：Schema Retriever 的表级/字段级召回结构、Action schema 生成 prompt、trace DAG 化表达。
2. **阶段三之后借鉴**：RAG assembler/retriever/operator 分层、evaluate service 的 metric/context 抽象。
3. **阶段五或有余力再借鉴**：Skill 包、MCP/外部应用、代码沙箱、多 Agent planning。
4. **不要借鉴**：大平台分包、多数据源泛化、Workflow UI、完整沙箱服务、过早 Skill 化。

保持 DataPilot 的轻量主线，吸收 DB-GPT 的成熟结构。这个组合最适合当前目标：**既能做出可投递项目，又能在面试里证明你读过大项目、会筛选、会取舍，而不是只会堆功能。**
