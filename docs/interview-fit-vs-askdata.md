# DataPilot 面试适配度与 AskData 对照分析

> 日期：2026-07-21  
> 目的：判断当前已完成阶段二 M0-M6 的 DataPilot v1，以及按 roadmap 完成阶段三到阶段五后的 DataPilot，作为 AI 应用开发 / Agent 开发 / 后端开发实习面试项目的竞争力；同时对照 `D:\.Work\Practice\Python-Practice\references\askdata_agent` 的技术路线和面试话术，明确相同点、差异和后续补强方向。

> 补充决策：AskData 技术亮点的取舍分层见 `docs/askdata-tech-value-decision.md`。该文档明确哪些能力是真正泛用、面试常问且工作可用，哪些能力只适合作为后期加分项。

## 结论先行

我的判断：**DataPilot 的方向是适配市场主流面试项目的，不是一个偏离招聘口味的 AI 玩具项目。**它解决的是企业数据分析 / 智能问数这个真实场景，技术上覆盖 NL2SQL、SQL 安全、RBAC、结构化输出、Trace、Eval、图表和演示页，这些都能对应 AI 应用开发、Agent 开发和后端开发面试的常见追问。

但当前阶段二 v1 还不能把它包装成“完整 Agent 项目”。它现在更像一个**工程底座扎实的 NL2SQL v1**：能查 SQL、能拦截危险 SQL、能评测 smoke、能演示图表，但还缺少 RAG、SQL+RAG 混合推理、稳定 Router、完整失败归因和独立 AgentEvalOps。也就是说，当前适合做阶段性展示，不适合作为最终简历主项目的完整版本。

如果后续在 RAG / Hybrid 前补一段 AskData 风格的 Text2SQL 深化，再完成 RAG、混合推理和阶段五包装，DataPilot 单体会进入**强 Data Agent 项目**区间。完整 AgentEvalOps 仍应作为第二个项目独立计算，不算进 DataPilot 单体分；两者组合起来，才形成“业务 Agent + 独立评测平台”的面试组合优势。

## 评分说明

以下分数不是客观行业标准，而是按实习面试视角做的工程判断。参考维度包括：

| 维度 | 权重 | 面试官实际关心的问题 |
|---|---:|---|
| 业务真实性 | 15 | 这个项目是不是解决真实问题，而不是套壳聊天？ |
| AI / Agent 技术深度 | 25 | 是否有 NL2SQL、RAG、工具调用、规划、路由、反馈闭环等核心技术？ |
| 后端工程能力 | 20 | FastAPI、数据库、迁移、接口契约、异常、日志、配置、测试是否扎实？ |
| 安全与治理 | 15 | 是否只靠 prompt，还是有 SQL Guard、RBAC、敏感字段、审计思路？ |
| 评测与可观测性 | 15 | DataPilot 单体是否有轻量回归、trace、可被独立评测平台消费的接口；完整 AgentEvalOps 不计入 DataPilot 单体。 |
| 展示与包装 | 10 | README、演示页、报告、面试话术是否清楚？ |

## DataPilot 当前 v1 面试分

**总体分：72 / 100 左右。**

| 方向 | 当前分 | 判断 |
|---|---:|---|
| AI 应用开发 | 74 | 有 NL2SQL、LLM 生成、图表、演示和业务场景，已经不像普通 Demo；但 RAG / Hybrid 尚未实现，Agent 味道还不够完整。 |
| Agent 开发 | 66 | 目前主要是普通 Python pipeline，不是多节点 Agent 编排；有 tool trace 和结构化响应，但还缺 Router、规划、反思、记忆、多步执行。 |
| 后端开发 | 82 | FastAPI、SQLAlchemy、Alembic、MySQL 主路径、Pydantic 契约、统一异常、日志、RBAC、测试都比较加分。 |

当前 v1 的强项：

- **后端底座比很多 AI Demo 扎实**：不是 notebook，也不是只调用模型接口；有 API、数据库迁移、seed、测试、演示页。
- **安全能力可讲**：SQL 不直接执行，先过 `sqlglot` AST 只读检查，再做表级 RBAC 和敏感字段拦截。
- **响应契约稳定**：`AgentResponse` 有 `route / answer / sql / rows / tables_used / docs_used / chart_spec / safety_status / cost / tool_calls / trace_id`，方便前端、评测和 trace 复用。
- **Eval 前置意识强**：阶段二就有 32 条用例计划和 6 条 SQL smoke，不是最后才想起测试。

当前 v1 的短板：

- **Schema Linking 仍然偏简单**：现在是从 `domain_pack/schema_desc` 加载全量字段描述进 prompt，还不是 AskData 那种字段级关键词召回 + 向量召回 + RRF + Rerank + SchemaGraph。
- **Agent 编排还轻**：没有正式 Router、RAG、Hybrid、LangGraph 或明确的计划执行节点。
- **评测还是 smoke 级**：当前 6/6 passed 很好，但只能证明主链路没坏，不能证明整体准确率。
- **业务真实性弱于 AskData**：DataPilot 是自建模拟业务数据，AskData 的包装来自横向项目和实际面试经验，这一点天然更有叙事优势。

## DataPilot 单体完成后的面试分

如果后续按新的路线完成 Text2SQL 深化、RAG / Hybrid 和阶段五包装，DataPilot 单体最低应达到：

- Text2SQL 深化：字段级 Schema Retriever、SchemaGraph / Join 路径、结构化 QueryPlanStep、局部 Schema SQL prompt、分步骤 Trace。
- RAG / Hybrid：来源引用、SQL/RAG/Hybrid Router、3-5 个稳定混合案例。
- DataPilot 自身评测边界：保留 smoke / regression 级轻量用例、稳定 `AgentResponse`、trace、Adapter 友好的接口；不把完整 AgentEvalOps 平台写成 DataPilot 内置能力。
- 阶段五包装：README、架构图、ER 图、演示视频、简历话术、部署说明、面试问答。

**DataPilot 单体预期分：84-86 / 100 左右。**

| 方向 | 预期分 | 判断 |
|---|---:|---|
| AI 应用开发 | 87 | 能讲“自然语言查数 + 知识库问答 + 混合分析报告 + 可视化”，非常贴近 AI 应用岗。 |
| Agent 开发 | 84 | 若补 Router、Tool Trace、多步 SQL+RAG、结构化 planner，Agent 叙事会成立；如果再引入 LangGraph，会更稳。 |
| 后端开发 | 86 | 后端底座已经不错，后续若补 Docker、缓存、部署、报告服务，会更完整。 |

完成后 DataPilot 的核心卖点应该不是“我做了一个 Text2SQL”，而是：

> 我做了一个面向企业运营数据的 Data Agent。它能根据问题选择 SQL、RAG 或 SQL+RAG 混合链路，用字段级 Schema 检索和结构化查询计划提升 NL2SQL 稳定性，用 SQL Guard 和 RBAC 保证查询安全，用结构化 AgentResponse 和 Tool Trace 支撑前端展示、调试和外部评测接入。

这个叙事比单纯“调用大模型写 SQL”更像真实工程项目。

## DataPilot + AgentEvalOps 项目组合分

如果 AgentEvalOps 作为第二个独立项目完成，且通过 Adapter 接入 DataPilot，项目组合可以达到 **88-90 / 100**。这里的加分点不属于 DataPilot 单体，而属于“两个项目形成闭环”：

- DataPilot 是被评测的业务 Agent，提供稳定 API、结构化响应、trace 和典型业务场景。
- AgentEvalOps 是独立评测平台，负责 YAML case、Adapter、SQL / RAG / Tool / 安全评分器、失败归因、SQLite 结果库和 Markdown / HTML 报告。
- 面试时应明确说“DataPilot 接入了独立的 AgentEvalOps 做回归评测”，不要说“DataPilot 内置了完整 AgentEvalOps 平台”。

## AskData 项目拆解

从 `askdata_agent` 的文档和代码看，它的核心定位是**面向私域结构化数据库的 Text2SQL Agent**。它的面试包装非常成熟，尤其强调横向项目、私有化部署、研究所/企业问数场景和量化指标。

AskData 文档中的主链路：

```text
用户 Query
  -> 关键词抽取
  -> Schema 混合检索 + RRF + Rerank
  -> SchemaGraph
  -> CoT 四元组规划
  -> SQL 生成
  -> MCP 路由执行
  -> 查询结果
```

代码中已复现的核心模块：

| 模块 | 作用 |
|---|---|
| `schema_indexing` | 定义字段级 Schema、表级 Schema、字段样例、业务描述、三级索引文本。 |
| `schema_retrieval` | BM25 关键词召回、向量召回、RRF 融合、Rerank 精排、SchemaGraph 构建。 |
| `cot_planning` | 把用户问题和 SchemaGraph 变成四元组步骤：数据库、处理对象、操作指令、输出目标。 |
| `sql_generation` | 根据 CoT 步骤和局部 Schema 生成 SQL。 |
| `mcp_router` | 按数据库名路由到 SQL 执行器，Demo 中是 SQLite 执行器。 |
| `askdata_pipeline` | 串联端到端流程，并保存每一步的执行日志。 |

AskData 的强项：

- **Text2SQL 技术深度强**：字段级 Schema、三级索引、RRF、Rerank、SchemaGraph、局部 Schema、四元组 CoT 都是能打的面试点。
- **面试话术成熟**：它提前准备了“为谁做、为什么做、Agent 范式、Schema 是什么、为什么三级索引”等高频追问。
- **业务叙事更真实**：研究所 / 私域 / 内网 / 横向项目 / 交付，这种故事天然比纯模拟数据更像真实项目。
- **量化指标强**：文档中写了字段召回率、准确率、校验回溯提升幅度等数字，面试很有杀伤力。

AskData 的弱项或注意点：

- **公开代码是复现 Demo，不是完整原始系统**：文档提到校验回溯、动态路由、长短记忆、部署和准确率，但可见代码的 pipeline 注释明确说暂不包含结果校验与回调修正。
- **后端工程展示不如 DataPilot 当前仓库扎实**：可见代码更偏算法链路 demo，缺少 DataPilot 这种 FastAPI、Alembic、统一响应、评测报告和演示页闭环。
- **SQL 安全实现偏轻**：Demo 的 SQLite executor 主要用正则判断 `SELECT / WITH`，不如 DataPilot 当前 `sqlglot` AST + RBAC + 敏感字段策略强。
- **评测平台不是代码主线**：AskData 文档有指标，但可见代码没有像 AgentEvalOps 这种可复用评测平台结构。

## DataPilot 与 AskData 的相同点

| 维度 | 相同点 |
|---|---|
| 项目本质 | 都是企业智能问数 / Text2SQL / 数据分析 Agent。 |
| 用户价值 | 都降低业务人员写 SQL 的门槛，让自然语言变成数据库查询。 |
| Schema 重要性 | 都认为表、字段、业务描述、指标口径是 SQL 生成的关键上下文。 |
| SQL 执行 | 都不是只生成文本，而是要把 SQL 交给工具或执行器运行。 |
| 可解释性 | 都保留 SQL、涉及表字段、执行结果，方便解释“为什么这么查”。 |
| 面试方向 | 都适合 AI 应用开发 / Agent 开发 / 后端开发交叉岗位。 |

## DataPilot 与 AskData 的关键差异

| 维度 | AskData | DataPilot 当前 v1 | DataPilot 完成 roadmap 后 |
|---|---|---|---|
| 业务叙事 | 横向项目 / 研究所 / 私域数据 / 交付包装 | 电商/SaaS 模拟业务，真实性较弱 | 仍是模拟业务，但可通过演示、评测和包装增强可信度 |
| Text2SQL 核心深度 | 字段级三级索引、混合检索、RRF、Rerank、SchemaGraph、四元组 CoT | 模板优先 + 全量 domain schema prompt + DeepSeek SQL | 若不额外补 Schema Retriever，仍会弱于 AskData 的 Text2SQL 深度 |
| Agent 编排 | Plan-and-Execute + Reflection 叙事，代码复现了 CoT plan + execute | 普通 Python pipeline，Agent 节点感较弱 | RAG/Hybrid 后可形成 Router + SQL Tool + RAG Tool + Report Tool |
| SQL 安全 | 文档提治理，Demo 执行器主要只读判断 | `sqlglot` AST + 表级 RBAC + 敏感字段拦截 | 可进一步加入超时、limit、审计、RAG 注入和 Tool 参数绕过安全评测 |
| 后端工程 | 可见代码偏 demo pipeline | FastAPI、Pydantic、SQLAlchemy、Alembic、统一异常、日志、测试 | 若补 Docker/README/API docs，会明显强于 AskData demo |
| 评测闭环 | 文档有准确率指标，但可见代码不突出评测平台 | 6 条 smoke + 32 条计划 | DataPilot 单体保留轻量回归；完整评分器和失败归因属于独立 AgentEvalOps 的组合优势 |
| 展示体验 | 文档和话术强，代码展示较轻 | Streamlit 最小演示页已完成 | 阶段五包装后会更适合投递 |
| 多数据源 / MCP | 有 MCP 路由执行叙事，Demo 可按 database route | 当前单 MySQL 主路径，SQLite 测试 | MCP 是后期加分项，不宜提前硬做 |
| 记忆机制 | 文档话术包含短期/长期记忆 | 当前没有 | roadmap 中 Skill/记忆不是 P0，可作为扩展而非主线 |

## 最重要的判断：DataPilot 不需要完全模仿 AskData

AskData 最强的是**Text2SQL 算法链路包装**，DataPilot 更适合走**AI 数据分析后端工程项目**路线。两者不是谁替代谁，而是两个不同强项：

- 如果只拼 Text2SQL 深度，AskData 的字段级 Schema 检索和四元组计划更强。
- 如果拼后端工程、安全边界、结构化输出和可演示系统，DataPilot 的路线更完整；如果再加独立 AgentEvalOps，则形成组合级评测优势。

因此，DataPilot 后续不应该盲目照搬 AskData 的全部机制，比如一年级别的多库、多智能体、长短记忆和完整回调修正。更好的策略是：**只吸收 AskData 对面试价值最高、并且能和当前架构自然融合的部分。**

## DataPilot 最该借鉴 AskData 的 5 个点

### 1. 字段级 Schema Retriever

当前 DataPilot 的 `schema_loader` 已经有表字段描述、KPI 和 SQL examples，但缺少“从用户问题动态召回相关字段”的模块。阶段三或阶段四前，可以做一个轻量版：

```text
用户问题
  -> 关键词抽取或规则分词
  -> BM25 / 简单向量召回字段描述
  -> 召回相关表、字段、关系
  -> 只把局部 Schema 放进 SQL prompt
```

这不一定一开始就要 Milvus / Rerank。先用本地 BM25 或 ChromaDB 做到“局部 Schema”即可，面试上就能说清楚为什么不把全量 Schema 塞给模型。

### 2. 结构化查询计划

AskData 的四元组 CoT 很适合面试，因为它把模糊问题拆成可验证结构。DataPilot 可以避免暴露原始 CoT，改成更工程化的 `QueryPlanStep`：

```yaml
step_type: sql | rag | answer
data_sources: [orders, refunds]
objects: [products.product_name, refunds.refund_reason]
operation: 按商品统计退款率
output: refund_rate_top_products
```

这样既有 Plan-and-Execute 的味道，又避免“展示模型思维链”的问题。

### 3. SchemaGraph / Join 路径约束

DataPilot 现在有 `domain_pack/schema_desc` 的关联关系，但 SQL 生成时还没有显式的 Join 路径搜索。多表问题增加后，应让模型优先使用已知关系，而不是自由猜 Join：

```text
orders.product_id -> products.id
refunds.order_id -> orders.id
tickets.order_id -> orders.id
```

这能直接提升多表查询的面试说服力。

### 4. 分步骤 Trace

AskData 的 pipeline result 会记录关键词、Schema context、CoT 输出、每步 SQL 和执行结果。DataPilot 当前 trace 更偏最终响应，应按 M7 计划补：

- `template_match`
- `schema_context`
- `llm_generation`
- `sql_guard`
- `sql_execution`
- `rag_retrieval`
- `hybrid_answer`
- `chart_decision`

这会成为阶段四 AgentEvalOps 失败归因的输入。

### 5. 面试话术的结构

AskData 的话术最值得学的不是具体句子，而是回答结构：

```text
给谁做 -> 痛点是什么 -> 为什么传统方案不够 -> 技术路线 -> 量化结果 -> 面试官可追问的细节
```

DataPilot 也应该按这个结构组织，而不是一上来报技术栈。

## DataPilot 不建议现在借鉴的点

| AskData 点 | 不建议原因 |
|---|---|
| 多库 MCP 路由 | 当前单库业务足够，提前做多库会稀释主线。 |
| 长短期记忆 | 对当前“数据分析 + RAG + Eval”主线不是 P0，容易讲得虚。 |
| 完整 Reflection 回调修正 | 很有价值，但工程量大；阶段四可先用失败归因和 SQL 错误样例库替代。 |
| 大规模 Milvus / Rerank 依赖 | Milvus Standalone 已通过 Docker Desktop 部署可用（2026-07-21），阶段三直接走 Milvus，不需要 ChromaDB。 |
| 直接照搬金融/研究所话术 | 你的项目业务域是电商/SaaS 运营，应该讲自己的业务闭环，不能冒充横向交付。 |

## 面试适配风险

### 风险 1：AI 协作开发导致“讲不清”

面试官不一定介意你用了 AI，但会介意你讲不清：

- 为什么这样分层？
- 为什么先模板 SQL 再 LLM？
- 为什么 SQL Guard 不能只靠 prompt？
- 为什么 Eval 不直接用 LLM-as-Judge？
- 为什么当前没上 LangGraph？

解决办法不是隐藏 AI，而是把关键设计决策、验证命令、失败样本和取舍讲熟。DataPilot 目前 `AI_CONTEXT.md` 和 `dev-log.md` 已经在补这件事，这是优势。

### 风险 2：最终项目功能多但主线不清

roadmap 里有 RAG、EvalOps、Skill、MCP、Docker、视频、八股。真正面试时不能讲成“我什么都做了”。主线应该压成三句话：

1. **DataPilot 解决企业运营数据的自然语言分析问题。**
2. **系统通过 SQL / RAG / Hybrid 三条链路生成结构化答案和图表，并用 SQL Guard + RBAC 保证安全。**
3. **我用 AgentEvalOps 做回归评测和失败归因，证明每次 prompt / schema / retrieval 改动是否真的变好。**

### 风险 3：缺少真实业务交付

AskData 的横向项目背景很强，DataPilot 是自建模拟项目。这是客观短板。补救方式是：

- 数据和问题要像真实运营场景，不要太玩具。
- README 展示 3-5 个完整业务案例，而不是只展示 API。
- 评测报告给出真实数字，例如 SQL 简单查询正确率、RAG 命中率、安全拦截率。
- 面试中诚实说“这是我为求职倒推设计和实现的企业数据分析 Agent 项目”，不要包装成真实交付。

### 风险 4：Text2SQL 深度不如 AskData

如果面试官深挖 Text2SQL，当前 DataPilot 在 Schema 检索、Rerank、Join path、计划生成上确实不如 AskData。后续至少要补一个轻量 Schema Retriever 或结构化 Query Plan，否则这个点会弱。

## 推荐后续优先级

### P0：必须做

1. **Text2SQL 深化阶段**：字段级 Schema Retriever、SchemaGraph / Join 路径、结构化 QueryPlanStep、局部 Schema prompt。
2. **阶段三 RAG + Hybrid 主链路**：让项目从 NL2SQL 扩展成 Data Agent。
3. **RAG `RetrievedDoc` 契约**：`doc_id / chunk_id / title / source / content / score / metadata`。
4. **Router**：能判断 `sql / rag / hybrid`。
5. **DataPilot Adapter 友好接口**：保留稳定 `AgentResponse`、trace、error_type，方便独立 AgentEvalOps 接入。

### P1：强烈建议

1. **轻量字段级 Schema Retriever**：先 BM25 / ChromaDB，不急着上复杂 Rerank。
2. **结构化 QueryPlanStep**：作为 AskData 四元组 CoT 的工程化版本。
3. **Trace steps**：把每个决策步骤写进 JSONL。
4. **DataPilot 轻量 issue tags**：只做 smoke / regression 级标签；完整 scorer 和失败归因放到独立 AgentEvalOps。
5. **README 面试版案例**：至少 3 个 SQL、2 个 RAG、2 个 Hybrid、2 个安全拦截案例。

### P2：有余力再做

1. LangGraph 迁移。
2. MCP Server。
3. Skill 封装。
4. 62 条扩展评测。
5. 消融实验和 HTML 仪表盘。
6. Docker Compose 一键部署。

## 最终建议

当前 DataPilot v1 已经值得继续，不需要推倒重来。你的担心有一半是对的：**如果只停在阶段二，它确实还不像市场上更强的 Agent 面试项目。**但另一半不必焦虑：**先补 Text2SQL 深化，再做 RAG / Hybrid 和包装后，它会比普通 AI Demo 强很多；再配合独立 AgentEvalOps，项目组合会形成 AskData 没有完全覆盖的工程化 + 评测平台优势。**

最关键的路线不是“复制 AskData”，而是：

```text
DataPilot 当前工程底座
  + AskData 的 Schema 检索 / 结构化计划思想
  + roadmap 的 RAG / Hybrid
  + 阶段五的包装材料
= 一个对 AI 应用、Agent、后端三类岗位都能讲得通的强 DataPilot 单体项目

DataPilot 单体
  + 独立 AgentEvalOps
= 一个业务 Agent + 评测平台的强项目组合
```

如果后续只能再补一个 AskData 风格能力，我建议优先补：**字段级 Schema Retriever + 结构化 QueryPlanStep + 分步骤 Trace**。这三个点组合起来，能明显提高 Text2SQL 深度，又不会把项目拖进多库、记忆、MCP 的大坑。
