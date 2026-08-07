# 网上关于对 Data Agent 的讨论

> **讨论素材**：网上技术讨论原文（未筛选、未整理，保持原文）。制定计划 / 面试话题参考时可翻阅；用到哪条再当场摘录到对应 notes / plan，观点仅代表原作者、不要照搬。排名不分先后，需完整阅读。

**1. 真实取数场景**

```
企业级的是啥我也不知道，能实际解决真实问题吧。比如我是数据分析师，一个经常性的工作就是给客户或者业务取数。要根据需求（钉钉或飞书给你发来一段消息，说要哪些哪些数据）去 sql 客户端编写 sql 代码，跑出数据导出成 Excel 表，然后传给业务或客户。然后呢我就弄了一个 agent 自动做这个事：业务或客户发来消息，自动识别是不是要数据，然后自己去数据库取数导出 Excel 并发送。当然实现的方式有很多，我的实现方式是写了一个传入所需字段自动生成 sql 代码的工具，然后让 llm 识别需求消息解析出需要哪些字段，然后调用我写的工具，再自动化导数，上传文件
```

**2. 需求澄清**

```
我感觉 data agent 缺少一个 grill-me 那种 skill，很多人提需求根本讲不清楚自己到底要什么数据，以前做 bi 也有这个问题，不过人工多轮沟通能兜底。一句话出数本身就是伪需求，一个精准的数据就是要反复返工的，怎么可能随便问就能出高质量回答呢。
```

**3. 工程问题（幻觉/成本）**

```
往 agent 靠的话，还得多看看实际工程中容易出现的问题：幻觉啊、token 消耗量、时间等等。前两天面试被问了这些
```

**4. 要素提取+填槽 / parameterized template**

```
其实我们银行做 nlp2sql 会前置 faq，要素提取 + 填槽，然后拿 deepagents（skills+mcp兜底），我们不是生成 sql，实际情况核心是你主要干的事情要素去添入，数据本身就给我造那种比去年，比上月，类似于这种字段。内网相对小模型才可以。

就是不是直接问题不是直接生成 sql，而是主要把用户问题给提取你问哪些列哪些行（这个做权限），还有查询条件就是你的要素提取限制，环比同比这种比较问题不生成复杂 sql，而是直接在数据源把这种数据给作为单独一列。我说的实际提升准确率的方法。skills 一个理由帮忙选哪张表（哪个条线），然后subgants 可以是具体每个表条线的查数 skills，然后再有个数据分析总结 skills。我们是这么做的。这个应该是parameterized sql template
```

**5. schema linking 前置 / workflow vs react**

```
真实工业场景不好落地，一部分原因在于数据库有很多表，每个表有很多字段。（这是和论文，和 demo 的区别之一）。所以要做一次前置 schema linking，比如阿里的 Data Agent 开源项目就是相似度加一定的召回策略，把表大量缩减到十张以内，然后再让模型以及提取和问题相关的表字段（工程上补充外键关系）。这一套做完了才是生成 + 纠错 + 分析（问题改写拆分啥的这些都可以 skill 加脚本验证去做，还要支持人工介入澄清解释，整个 skill 好用的前提用好用的 agent，不是自己从头手搓一个）

当然，从头的原始做法可以 langgraph 做 workflow，不建议做成 react 加工具自己调用的方式。技术为业务需求服务，text2sql 任务步骤固定，workflow 我觉得更好。

你还要考虑权限控制，不同权限用户查的范围受控制（你们公司自己有中台控制的话可以直接对接拿数据）结合业务还要召回可能用到的业务信息作为 evidence 帮助生成正确 sql（不做 rag 的话，你要给 agent 权限，让他自己查你们的非涉密业务信息）
```

**6. 语义中间层**

```
之前看有个方式是，依靠大模型将自然语言先转为语义，然后将语义转为 sql，会提高确定性，不会单纯依靠基础模型能力，首先就是要先梳理ddl这些，然后定义一些 metrics 常用的指标口径
```

**7. 语义层 MDL（含 yaml 示意）**

```yaml
# 语义和表 字段的对齐，我们公司做是又加了一层 api 层提高准确率和效率。
# 最后问题核心的指向还是你的表 字段的语义是否完整准确，这部分才是最大的痛点，也是最难的地方

# 类似这样定义语义 找两张表给 AI 先搞个大概出来试下 这块我最近也在研究是都交给 AI 生成的 还没验证效果 token 没了：

# 3.语义层(MDL)核心概念简例
# MDL 用于声明业务语义，而非直接暴露原始表。示意结构：

# models/orders.yml （简化示意）
name: orders
tableReference:
table: orders
columns:
name: order_id
type: integer
name: customer_id
type: integer
name: amount
type: double
name: total_revenue   # 非计算字段示例
type: double
expression: "suM(amount)"
primaryKey: order_id

# relationships示例
relationships:
name: customer_orders
models: [customers, orders]
joinType: ONE_TO_MANY
condition: "customers.id = orders.customer_id"
# 自然语言问题经 LLM + 语义检索后，Wren Engine 会基于 MDL 展开关系、计算字段与策略，再生成目标数据库方言的可执行 SQL。
```

**8. 语义建模两阶段 / 记忆管理 / 单表视图工具化**

```
最关键的是数据治理和语义建模，建议把流水线拆两步，一步是读表完成语义建模和元数据建模，一步是依据建模的配置作为运行时依据跑 data agent。另外记忆上下文建议实现一整套装配卸载机制把工具输出和引用拆分，异步完成压缩和卸载，提供工具引导装载。当然 system promt 注入上应该是动态的实时关注用户核心诉求，当前计划和进度，遇到的挑战困难，根据情况改变 system prompt 让模型思考知道当前的重点和避免犯同样的错。核心架构上应该是 react + 反思最好，单 agent 足够，其他可以工具化同时展示上把主流程和用于渲染输出的拆开。

我自己的实践是语义模型隐藏复杂联表，用工具实现条件查询 + 排序 + 聚合等能力，让 llm 永远是单表视图，通过模糊查找工具得到数据集，通过详细输出工具得到单数据集详情，通过元数据检索知道条件候选值（比如可以填几十个几百个城市名），通过 sql 叠加实现非全量检索。
```

**9. 企业级 Data Agent 全景（长文）**

```markdown
# 企业级 Data Agent 有多难做
26年是企业Agent元年，大部分落地场景无非都围绕着：

- 知识问答Agent： 查询产品知识，销售场景培训等等；
- Data Agent： 理解业务问题，执行查询，解释结果，生成Insights。

其中Data Agent应该算是最难落地的场景了，有很多原因：

- 答案非黑即白，不能容忍一丝一毫的错误。
- 企业数据语义复杂，很难有一个team去维护语义的标准和一致性。例如活跃客户在不同部门的定义可能完全不同。（可能以后公司会有专门的部门去建立语义层吧，至少我们已经在开始做了）。
- 数据库庞大，有各种legacy的数据资产，很难都放进上下文里。
- 数据治理不再是静态的需求，还需要在执行时动态生效。很多时候甚至需要行级（RLS）权限管理，脱敏等复杂规则。
- 语义层版本管理成本非常高，需要随着企业的数据资产变化而不断更新。
- 最后也是大家都知道的：LLM会神不知鬼不觉的自己编造一些字段。

## 怎么解决这些问题呢？
Data Agent不应该是直接生成SQL，这太危险，也太难控制正确性。

更合理的顺序是：
意图识别 -> 语义层（Metrics Layer）-> 元数据查询 -> SQL Planner -> SQL Validator -> Governed Query Engine -> Result Verifier -> 答案生成 -> Audit和Feedback

这里最关键的是Semantic layer：Data Agent 应该优先理解业务，而不是表结构。
比如定义什么是“净销售额”、“有效客户”、“本月业绩”；Snowflake Cortex Analyst 和 Databricks的Genie都推出 Semantic Views的概念，把业务概念、指标、关系和底层表之间的映射体现出来。

除此之外，还需要做到分层的 Context Retrieval：
不要把所有 schema 都塞给模型，而是：
先判断 domain -> dataset -> table -> 压缩column -> 最后Inject metric definition 和 join rule

为了防止大模型升级，或者数据结构变化造成的不稳定性，还需要准备 Evaluation Set 持续评估。

## Data Agent主流方向是什么？目前企业 Data Agent 大致分成三条路线：

- 第一类是 Data Platform Native Agent，比如 Databricks Genie、Snowflake Cortex Analyst / Snowflake Intelligence、Microsoft Fabric Data Agent。这类产品直接长在数据平台里，优势是天然接入权限、元数据、计算引擎和治理体系。
- 第二类是 手搓 Data Agent，用 LangGraph、dbt semantic layer 等组件自己搭建。这类路线灵活，但要求企业自己解决权限、语义层、SQL 校验、成本控制、评估和监控。
- 第三类是 BI Copilot / AI for BI，比如 Power BI Copilot、Qlik Insight Advisor。这类产品更适合“基于已建好的语义模型和报表资产做自然语言分析”，而不是自由探索所有企业数据。

## 那Data Agent真的能上线吗？
Snowflake 曾公开提到 Cortex Analyst 在真实业务中可以实现 90%+ SQL accuracy。我们也在databricks和阿里云的data agent中做过很多尝试：在涉及到的表范围有限，semantic layer完整性的情况下，的确能做到95%以上的准确度。

即使遇到不稳定的情况，也可以通过调整大宽表的结构，Prompt的规则，增加更多semantic hints来完善问题。

所以Data Agent 落地的前提不是大模型的能力，而是要把企业混乱的数据语义，治理成 Agent 可以安全理解和稳定执行的系统，把大模型的不确定性控制到最低。
```

**10. 规则过载 / harness 约束 / 管理预期**

```
我司正在搭建的 data agent，已经处理了 sql 库，以及各类字段命名的解释 skill，甚至有一些复杂表还有专门的 python 代码集。有时候规则太多了，反而模型直接忽略规则。正确率还是一般，只能管理用户的预期，使用在一些犯错了也可以接受的场景. 或者引导用户检查答案进一步校验. 可能需要等待大模型再升级一轮。不过最近也在尝试一些 harness 工程增加约束看看有没有转好。
```

**11. Insights 生成（准确 vs 价值）**

```
A：想请教一下，data agent 生成 insight 的能力如何提高？目前在做一个项目，感觉很难在让 AI 生成有价值的 insights 和保持准确性减少幻觉方面达到平衡。如果把 metrics 都通过自己定义的函数算好了喂给 llm，确实准确性高，但是感觉接入 AI 的意义就不大了。但是不在乎准确性的话又纯属给自己挖坑了，因为 stakeholder 看到一个不 make sense 的 insight 一定会来问个究竟……

B：自己纯手搓 agent 真的很难，我们越做越放弃，现在在用平台提供的 data agent. 其实 insights 出来的都还可以，用户的 instruction/skill 也很重要
```

**12. 语义层维护 / eval 回归集 / RLS 权限**

```
这几个方向可以看看，很多团队搭建到你这步就停了：
1. 语义层要持续维护：字段的业务含义、表间 JOIN 关系、同义词映射，不然准确率天花板很明显。我们实际做法是用 Agent 反向从查询日志里自动补全语义层。
2. 评估体系别省：建一个 query→SQL 的回归测试集，每次调 Prompt 或改 Schema 先跑一遍，能发现很多隐蔽的退化问题。
3. 权限层接入：Agent 生成的 SQL 最好走一遍 Row-level security，跨部门场景下这个是刚需。
```

**13. text-to-metric vs text-to-sql**

```
A：你叫 AI 写个多表关联 sql 出来，很难的。text to metric 和 text to sql 还是有区别的

B：不，我认为给清楚架构都能写
```

**14. eval 案例 / genie 自校验 / 宽表特化**

```
A：你的 eval 是跑了些什么例子？如果是语意清晰的 data cube （不向外 join, 内部可能 temp table 互相 join), 能做到 100% 准确吗？现在好的 agent 比如说 databricks genie 应该是有自校验机制，即会在一个 request 中根据复杂度自己决定跑一些分段小样来核验，基本在可控清晰环境中达到 100%。

B：用了 w3school 的一个 OLTP 的 DB 配套的 200 道 sql 题目中的部分 case（join 题目占比大且外 join），这个 sample DB 的话是有 5 个 schema 共 60+数据表。data cube/业务语义的话一方面是从 DDL 抽取以及通过 AI enrich。准确率的话，离 100% 很远诶 比较好奇您提到的 genie 中的自校验机制是什么，校验的基准是什么（在该 db 下一些 ground truth sql 的 case 吗？）

A：60+数据表估计太多了，业务中应该可以精简。genie 好像最多允许 25 张表，我们用的好的其实都是根据业务需要一个 space 设计出 2-3 张表最多，这样准确率就高多了。它的自校验基本是隐藏的，表现是一个问题下去，会发现它最后引用 5 个 query, 但跑了 10 个。认为是 agent 有一些机制会比如先跑一天的数据看一下然后再跑真正需要的，类似人的一些小策略

B：明白了！在迭代 agent 和做 eval 的时候用这个 db 的目的是为了压测 agent 在 retrieve schema 时的准确率和多步 retrieve 能力，业务上的优化思路很有参考价值

C：genie 最高 30 个。我们现在经常是通过 genie 的使用反馈到治理层重新做优化的宽表，就像你说的设计出 2-3 个表特化一个 space。这个效果是最好的。我们还发现可以在 Genie 以上搭建一层 agent 的校验，主要做人自然语言与给到 genie 的指令的校验，这个比 genie 自带的自校验还要有效一些。（说白了就是人话翻译，由于很多业务方不说人话，所以这一层效果特别好）
```

**15. benchmark 质疑 / 可观测性 / 外挂 memory**

```
A：你有看最近的 sql benchmark 吗，感觉 sql agent 很容易被质疑

B：有关注近期的 benchmark，也有看到 Mike Stonebraker 说 llm 写 sql 准确率是 0% 的那篇访谈，这几天在自建的基准集以及验证集上 agent 的表现（dev 最高 0.85，test 在 0.6-0.75 之间徘徊）也确实是不太能达到上生产的预期 不过我一开始做这个 demo agent 的期许也不是专注 text2sql 领域，主要是想通过这样一个项目系统性串联 agent 的 key components，在面对实际改善 agent 效果的需求时，应该如何建立可观测性，通过 eval-driven 在哪几个方面找到可优化点…

C：感觉ai不是写不出来 是一堆表关联关系计算口径这些压根就不清楚

B：对，所以要在 schema/business knowledge 上外挂 memory，挂了也确实也会有进步
```

**16. 某人的简历**

```
面向企业经营数据问答，构建融合NL2SQL、HybridRAG与工具调用的数据智能Agent
基于 LangGraph 构建 ReAct Agent，统一接入本地与 MCP 工具，通过结果校验、Replan 和调用预算控制无效循环。
构建面向 Northwind 8 张业务表的 HybridRAG 与 NL2SQL 链路，使用 SQLGlot 校验查询安全；在20条用例中取得 Recall@5 91.67%、MRR 0.8125，平均延迟4.72S。
```

**17. 某人的简历** 

```
DataForge —— Multi-Agent 智能数据分析系统

技术栈： Python、FastAPI、LangGraph、LangChain,、Vue3、ChromaDB、SQLite、Pandas、DeepSeek/Qwen、LangSmith

项目描述：面向数据分析场景的 Multi-Agent 编排系统，用户通过自然语言驱动 7 个专业 Agent 在 LangGraph 有状态图中协同完成从任务规划、SQL 执行、图表生成到分析报告的全流程自动化。

核心贡献：
1. Multi-Agent 有向图编排：基于 LangGraph StateGraph 构建 7 节点流水线（Planner-→SQL-→Chart→Report→ 双辩论 →Validator），通过条件路由与状态 Schema 管理。实现任务拆解、执行与校验的全流程调度。
2. 对抗辩论+裁决验证：引入 Optimistic/Pessimistic 双 Agent 交叉辩论+三维量化评分，由 Validator 裁决（驳回 ≤3 次自动重试），有效抑制 LLM 幻觉，结论可信度从 72%提升至 91%。
3. 双模型分层推理与高可用降级：quick_think（执行型任务）与 deep_think（决策型任务）分离调度，LLM 成本降低 40%；四级 Embedding 降级链保障服务连续性，可用性 100%。
4. 流式交互与工程保障：FastAPl+ SSE 逐 Token 流式推送，LangSmith, 全链路追踪，API Key 鉴权+限流+SQL 白名单。独立完成 60+文件落地，15+实际任务上线，分析耗时由小时级压缩至分钟级。项目成果：独立交付 60+文件，完成 15+真实数据分析任务(含 5000+行数据集)，自动生成带交互图表的结构化报告，分析耗时由小时级压缩至分钟级。
```

**18. 某人的简历**

```
项目1：HomeRAG-数据智能分析管理
技术栈：Python、LangChain、LangGraph、Qdrant/MilvuS、FastAPI、SSE、jieba、OpenAI GPT
项目描述：基于AgenticRAG架构打造自然语言转SQL智能分析代理，实现从自然语言查询到结构化数据结果的全链路自动化，帮助业务人员免写SQL快速完成数据分析。
基于LangGraph+LangChain搭建端到端分析系统，对接OpenAIGPT实现查询意图解析、关键词扩展、SQL生成与语法校验。
基于jieba完成中文分词与关键词提取，结合向量数据库精准召回字段、指标与取值，为SQL生成提供可靠数据支撑。
用LangGraph编排查询工作流，自动化完成问题识别、向量检索、SQL生成、校验与执行，适配统计分析、明细查询等场景。
优化状态管理与并发调度，解决并行节点更新冲突，通过SSE流式推送实现执行过程可观测，保障系统稳定。
采用全文/混合策略提升数据匹配精度，结合定位字段增强SQL可解释性，通过异常容错与基础评测保障系统健壮性与结果质量

项目2：电商领域知识图谱与智能问答系统
技术栈：Python、Neo4j、MySQL、PyTorch、Transformers、LangChain、FastAPI、sentence-transformers
项目描述：打造电商领域知识图谱与智能问答系统，以BERT模型微调与实体抽取为核心，实现商品文本特征提取、图谱构建到自然语言问答的全流程落地，为电商产品咨询提供精准、高效的智能解答能力。
基于bert-base-chinese微调NER模型，经LabelStudio完成2000+条商品文本标签标注、B-l-O体系数据转换及Transformers训练调优，实现商品特征实体抽取F1值92%。准确率94%，较基础模型提升35%，支持批量高效抽取。
模型训/测/评全流程工程化代码，将抽取的商品标签同步至Neo4j，补充知识图谱核心节点，丰富图谱非结构化数据维度。
搭建Ne04j+MySQL双库架构，开发自动化数据同步工具，完成商品分类、SPU/SKU、品牌等多类结构化数据及非结构化标签数据的图谱全维度构建。
基于LangChain整合微调后模型与知识图谱，设计混合检索策略实现实体精准对齐，自动生成Cypher语句执行图谱查询，并搭建FastAPI智能问答接口，实现自然语言问答端到生成。
优化模型与图谱联动逻辅，调优实体抽取精度与Cypher查询匹配度，显著提升实体对齐和问题解析效率，实现电商商品咨询的精准、快速解答。
```



