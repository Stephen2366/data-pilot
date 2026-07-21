# AskData 技术亮点取舍记录

> 日期：2026-07-21  
> 背景：对照 `D:\.Work\Practice\Python-Practice\references\askdata_agent` 后，判断哪些能力值得 DataPilot 借鉴，哪些只是面试包装或后期加分项。本文用于后续改 roadmap、写简历和准备面试追问。

## 结论

AskData 里最值得学的不是 MCP、长短期记忆或多智能体包装，而是 **Text2SQL 的 Schema 处理、SQL 可控性和可观测链路**。

DataPilot 后续最应该吸收的是：

```text
字段级 Schema 检索
  -> 局部 Schema Prompt
  -> 轻量 Join 路径约束
  -> 结构化 QueryPlanStep
  -> SQL Guard
  -> 分步骤 Trace
```

这条线能把 DataPilot 从“让 LLM 裸写 SQL”提升到“工程化 NL2SQL 系统”。它比提前做 MCP、记忆、多智能体更适合当前阶段，也更容易被面试官追问出有效内容。

## 第一梯队：真的值得做

| 技术点 | 泛用性 | 面试热度 | 工作实用性 | 判断 |
|---|---:|---:|---:|---|
| 字段级 Schema 检索 / Schema Linking | 高 | 高 | 高 | Data Agent 核心能力，优先补 |
| 局部 Schema Prompt | 高 | 高 | 高 | 比把全库 Schema 塞给模型成熟很多 |
| Join 路径约束 / 轻量 SchemaGraph | 中高 | 中高 | 高 | 多表 SQL 很常见，但不用讲成复杂图算法 |
| SQL Guard / RBAC / 敏感字段控制 | 高 | 高 | 高 | 面试官很爱问“怎么防模型乱查、删库、越权” |
| 执行日志 / Trace / 失败归因 | 高 | 高 | 高 | Agent 工程化必备，也服务 AgentEvalOps |

### 为什么这些是真泛用

- **Schema Linking** 是 Text2SQL 的核心问题：用户说“退款率”，系统必须知道它对应哪些表、哪些字段、哪些指标口径。
- **局部 Schema** 是控制上下文和幻觉的工程手段：只给模型相关表字段，减少编造字段和错误 Join。
- **Join 路径约束** 是多表查询的安全护栏：让模型优先使用已知主外键或业务关系，而不是自由猜连接条件。
- **SQL Guard 和权限控制** 是生产系统底线：prompt 不能替代 AST 校验、只读限制、敏感字段拦截和角色权限。
- **Trace** 是排障和评测入口：没有中间步骤，就很难知道错在 Schema 召回、计划、SQL 生成还是执行。

## 第二梯队：有价值，但要轻量做

| 技术点 | 判断 | DataPilot 建议 |
|---|---|---|
| RRF 融合 | 有价值，但不是第一天必须完整实现 | 先做关键词召回 + Milvus 向量召回 + 简单融合，RRF 作为 P1 |
| Rerank 精排 | 能提高相似字段区分能力，但依赖模型和评测样本 | Milvus 主链路稳定后再做 |
| 四元组计划 | 名词不是行业标准，背后的“结构化中间计划”有价值 | 改造成 `QueryPlanStep`，不要照搬 CoT 四元组 |
| SQL 自修复 / Reflection | 面试好讲，工作也有用，但工程量容易扩散 | 先做“执行失败后基于错误信息重试一次”，不要做复杂反思系统 |
| Milvus | 有工程价值，也贴近后续 RAG 和 Schema 检索 | 作为向量检索主路径，但面试重点应放在“为什么需要向量检索” |

### 对“四元组计划”的真实判断

AskData 的四元组计划可以作为灵感，但不建议 DataPilot 原样照搬。更稳的讲法是：

> 我没有直接暴露模型 CoT，而是让模型输出一个结构化查询计划 `QueryPlanStep`，里面包含表、字段、过滤条件、聚合方式、排序和输出列。这个计划先经过 Pydantic 校验，再交给 SQL prompt 使用。

这比“我用了四元组 CoT”更工程化，也更适合面试。

## 第三梯队：能讲，但不该当主线

| 技术点 | 判断 |
|---|---|
| MCP | 当前热度高，但对 DataPilot 单库/少工具场景不是核心。可以作为后期 P2，把稳定能力封装给外部 Agent 调用。 |
| 长短期记忆 | 对聊天 Agent 更常见；对 Data Agent 不是 P0。数据分析里更实用的是会话上下文和用户偏好，而不是泛泛的长期记忆。 |
| 多智能体 | 容易讲虚。除非能证明拆成多个 Agent 后准确率或可维护性提升，否则不如 Router + Tools + Trace 稳。 |
| 多数据库动态路由 | 企业里有用，但会扩大范围。当前先把 MySQL + Milvus 跑稳更划算。 |

## DataPilot 的取舍

DataPilot 不需要追 AskData 全家桶。当前更合理的路线是：

1. 阶段三A保留，但 P0 写成 **字段级 Schema 检索、局部 Schema、轻量 Join 路径约束、结构化 QueryPlanStep、分步骤 Trace**。
2. `SchemaGraph` 只作为“当前问题相关表字段和关系的轻量视图”，不要包装成复杂图数据库或通用图算法。
3. `QueryPlanStep` 取代 AskData 的“四元组 CoT”，强调结构化输出、可校验和不暴露原始思维链。
4. MCP、Skill、记忆、多智能体继续放到 P2 或扩展实现，不能挤占 NL2SQL、RAG、评测闭环。
5. Milvus 可以作为 Schema Retriever 和 RAG 的共同向量检索底座，但简历里只写实际完成的部分。

## 面试讲法

推荐主线：

> DataPilot 的 Text2SQL 不是直接把全库 Schema 塞给大模型生成 SQL，而是先做字段级 Schema 检索，用关键词召回处理精确字段和指标名，用 Milvus 向量召回处理业务语义。系统再根据召回字段构造局部 Schema 和 Join 路径，让模型输出结构化 QueryPlanStep，最后只基于局部 Schema 生成 SQL。SQL 执行前统一经过 SQL Guard、RBAC 和敏感字段拦截，每一步都会写入 Trace，方便调试和被独立 AgentEvalOps 评测。

被问到 MCP / 记忆时：

> 我了解 MCP 和长短期记忆，但在这个项目里没有把它们放到主线。DataPilot 当前最核心的问题是 Text2SQL 的正确性、安全性和可评测性。MCP 更适合作为后期对外暴露工具能力的标准接口；记忆更适合在多轮分析里保存会话上下文、默认时间范围和用户偏好，而不是一开始就做通用长期记忆。

## 是否需要修改 roadmap v2

需要小修，但不需要推翻阶段三A。

修改方向：

- 保留阶段三A，因为 Text2SQL 深化确实是 Data Agent 的核心卖点。
- 把 `SchemaGraph` 的表述改成 **轻量 SchemaGraph / Join 路径约束**，避免误解成复杂图系统。
- 把 AskData 的“四元组计划”明确降级为参考来源，DataPilot 实现 `QueryPlanStep`。
- 明确 RRF / Rerank / SQL 自修复是 P1/P2 加分项，不阻塞主线。
- 继续把 MCP、Skill、长短期记忆放在后期扩展，不作为求职主线。
