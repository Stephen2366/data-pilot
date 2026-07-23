# Phase 3A Plan 审查：DB-GPT 借鉴后的改动质量评估

> 审查日期：2026-07-23
> 审查范围：`docs/phase3a-plan.md` 在 `DB-GPT对比+修改plan`（commit `720bbb3`）中的改动
> 依据材料：`docs/reference-dbgpt-analysis.md`、DB-GPT 源码抽样、`docs/AI_CONTEXT.md` 当前状态

## 一、总体评价：改动质量高，边界清晰

这次 DB-GPT 对比后的 plan 修改整体质量很好。核心判断正确：**DB-GPT 作为结构参考，不做运行时底座**。

做得好的几个点：

- 每个模块的"参考资料"表给出了具体的 DB-GPT 文件路径、借鉴点和 DataPilot 独有的落地方式，不是笼统地"参考 DB-GPT"
- P0 架构底线明确写了"不引入 DB-GPT/AWEL/Skill/Sandbox 运行时"
- 风险表中新增了"DB-GPT 借鉴变成平台迁移"这一防膨胀条目
- 单一事实源中把 DB-GPT 参考项目取舍的权威出处指向 `reference-dbgpt-analysis.md`
- 每个借鉴点都有"DataPilot 怎么落地"的具体策略，不是机械照搬

一句话：**DB-GPT 的成熟结构被恰当地映射到了 DataPilot 的轻量主线上，没有喧宾夺主。**

---

## 二、Plan 里还可以完善的地方

### 2.1 M9：缺少 Schema Linking（LLM 二次筛选）的设计预留

**现状**：当前 plan M9 的链路是 `keyword + vector → merge → build SchemaGraph`，没有 LLM 对召回结果做二次过滤的步骤。M10 的 `validate_query_plan` 是事后校验（plan 生成后才检查字段合法性），不是事前过滤。

**DB-GPT 的做法**：[`SchemaLinkingOperator`](D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-ext\src\dbgpt_ext\rag\operators\schema_linking.py) 在 keyword + vector 召回之后，再用 LLM 过一次，把与当前问题无关的表和字段过滤掉，只把精简后的 schema 交给 SQL 生成。

```
DB-GPT 链路：keyword/vector recall → schema_linking_with_llm(query) → 精简 schema → SQL 生成
DataPilot 当前：keyword + vector → merge → build SchemaGraph → plan → validate
```

**为什么不直接加**：DataPilot M10 的 plan validation 已经能拦截不存在的表字段，所以二次筛选不是刚需。但 DB-GPT 的思路是**事前缩小范围**（减少 prompt 噪音），而 DataPilot 是**事后校验**（报错但不缩小），两者的设计理念不同。

**建议**：在 M9 的 `graph.py` 或 `retriever.py` 里加一个可选步骤的接口预留，比如：

```python
# engine/schema_retrieval/graph.py
class SchemaLinkingFilter:
    """可选：用 LLM 对召回结果做二次筛选（当前 Phase 3A 不做实现）。
    
    思路借鉴 DB-GPT SchemaLinkingOperator：
    - 输入：原始 merged_hits + 用户问题
    - 输出：过滤后的相关表/字段/指标子集
    - 优势：缩小 prompt、减少无关表噪音
    - 不做原因：M10 plan validation 已能事后拦截，二次筛选留后续优化
    """
```

这样 M9→M10 之间的职责更清晰：M9 负责"尽量召回"，二次筛选是可选增强，面试时有东西可讲。

---

### 2.2 M9：Embedding 模型选择没有明确提及

**现状**：Plan 里提了 `EmbeddingProvider` 协议和 `InMemoryVectorIndex`，但没有说后续用什么 embedding 模型。DataPilot 的中文业务问题（"各渠道 GMV 是多少"、"退款率最高的商品"）对 embedding 质量敏感——通用英文模型对中文业务术语的向量表示可能很差。

**建议**：在 M9 的"需用户确认的决策点"或任务清单中加一条：

> 明确测试环境的 fake embedding 策略（如 deterministic hash-based）和后续生产 embedding 候选（如 `bge-large-zh` 或 `text2vec-base-chinese`）。不需要在 M9 真接模型，但要确定方向，面试能讲清楚"为什么选这个模型"。

在 `vector_index.py` 中预留：

```python
class EmbeddingProvider(Protocol):
    """Embedding 服务协议。
    
    测试环境：InMemoryFakeEmbedding（deterministic hash-based，不依赖外部模型）
    生产候选：bge-large-zh / text2vec-base-chinese（中文语义匹配好，开源可私有化部署）
    不做：pymilvus 直接依赖（等阶段三 RAG 前再补 Milvus smoke）
    """
```

---

### 2.3 M9：缺少表名/字段名的中文别名策略

**现状**：用户可能说"订单表"而不是 `orders`，说"用户"而不是 `users`。DB-GPT 靠向量相似度兜底，但 DataPilot 的 keyword 召回需要能匹配这些中文别名。

`domain_pack/schema_desc/` 已经有中文表描述和字段描述（如 `orders: 订单主表`），但 `document_builder.py` 的任务清单没有明确说要把这些描述提取到 `keyword_text` 里。

**建议**：在 M9 `document_builder.py` 的任务清单中明确：

> `SchemaDocument.keyword_text` 应包含表的英文名 + schema_desc 中的中文表名/描述 + 常见业务别名。例如 `orders` 表的 keyword_text = `"orders 订单 订单主表 订单记录"`，让 keyword 召回能命中"各渠道订单量"这类中文提问。别名来源以 `domain_pack/schema_desc/*.md` 的描述段落为准，不额外维护别名文件。

---

### 2.4 M9：大表字段拆分的 chunk 策略没有涉及

**现状**：Plan 的 M9 有 `field_doc / metric_doc / relation_doc` 三类文档，但没有讨论当某张表字段很多（如 `orders_wide` 有 20+ 列）时，怎么避免局部 schema prompt 爆炸。

**DB-GPT 的做法**：[`DBSchemaRetriever._similarity_search`](D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-ext\src\dbgpt_ext\rag\retriever\db_schema.py) 把表级 chunk 和字段级 chunk 分开存储：

1. 先召回表级 chunks
2. 区分"separated"（字段太多的表，只存了表名和注释）和"not separated"（字段少的表，表+字段一起存）
3. 对 separated 表，按 `table_name` metadata 去字段向量库做字段级二次检索
4. 最后反序列化成 `CREATE TABLE` 风格的结构

**建议**：这个不需要在 M9 完整复刻，但应该在 `SchemaDocument` 的 metadata 设计里预留拆分条件：

> `SchemaDocument.metadata` 必须包含 `table_name`（字段文档归属的表），让 `retriever` 在召回相关表后，可以按 `table_name` 对字段做二次过滤。当某表字段超过阈值（如 15 列）时，字段文档和表文档分开向量化，检索时分两步走。这和 plan 已有的"局部 Schema"概念一致，只是补充了实现细节。

---

### 2.5 M10：`thoughts` 字段的取舍应写清理由

**现状**：DB-GPT 的所有 Action 输出都包含 `thought` 字段（模型的推理过程摘要）。当前 plan M10 写的是"只返回 JSON plan，不返回 CoT 原文"。这个选择本身没问题（减少 prompt 泄漏、简化解析、不暴露原始推理），但 **理由没有写进 plan**。

**建议**：在 M10 的决策点里加一句：

> `QueryPlanStep` 不包含 `thoughts`/CoT 字段，理由有三：① Phase 3A 的可校验性依赖结构化 plan 字段（表/字段/Join 来源），不依赖自由文本推理；② `purpose` 字段已能表达每步的意图摘要；③ 不暴露原始 CoT 减少了 prompt 泄漏面。如果后续发现 plan 质量不稳定需要调试依据，可以在 `PlanValidationResult` 中追加 `raw_llm_output`（只写 trace，不进 prompt）。

---

### 2.6 M11：`TraceStep` 可以加 `observations` 字段

**现状**：当前 plan 的 `TraceStep` 有 `input_summary / output_summary / error_type / metadata`。

**DB-GPT 的做法**：[`ActionOutput`](D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-core\src\dbgpt\agent\core\action\base.py) 区分了 `content`（执行结果）、`observations`（观察到什么，更偏诊断）、`thoughts`（模型的推理），三个字段各司其职。

对于 DataPilot 的 SQL 执行 step，`observations` 可以记录"返回了 50 行、3 列、耗时 12ms"这类执行层面的元观察，和 `output_summary`（业务结果摘要，如"GMV=11285752.00"）区分开。

**建议**：M11 `TraceStep` 加一个可选字段：

```python
observations: Optional[str] = None
# ★ 和 output_summary 的区别：
# - output_summary: 业务结果摘要，给人看的（"各渠道 GMV 已算出"）
# - observations: 执行元信息，给诊断看的（"返回 50 行 3 列，耗时 12ms"）
# 借鉴 DB-GPT ActionOutput.observations 的思路
```

面试时能讲"我把模型的输出和工具的实际执行观察分开了"是一个好细节。

---

## 三、有没有漏掉的值得加进 plan 的方法/技术？

### 3.1 DB-GPT 的 `ai_out_schema` 模式可以更具体地落地

**DB-GPT 的做法**：`Action.ai_out_schema` 不是手写 JSON 示例，而是**用 Pydantic 字段描述自动拼接 JSON 格式说明**注入 prompt。每个 Action 子类重写 `ai_out_schema` property，把字段名和 description 转成 JSON 示例字符串。

**当前 plan 的不足**：M10 plan 里写了"由 Pydantic 模型反推 JSON 输出示例"，但任务清单里没有对应的具体实现步骤。`build_query_plan_prompt` 只说"要求 LLM 只返回 JSON plan"，没说怎么生成这个 JSON 的格式说明让 LLM 照着输出。

**建议**：在 M10 任务清单里加一条：

> `QueryPlanStep` 实现 `to_prompt_schema()` 方法：遍历 Pydantic 字段的 `Field(description=...)` ，自动生成 JSON 格式示例字符串注入 prompt。例如 `step_type: str = Field(description="步骤类型")` → prompt 中追加 `"step_type": "步骤类型（sql_query / ...）"`。这比手写 JSON 示例更工程化——字段定义即格式文档，不会出现 prompt JSON 示例和 Pydantic Schema 不同步的问题。借鉴 DB-GPT `Action.ai_out_schema` 的思路，但 DataPilot 用 Pydantic  introspection 自动生成，而不是每个子类手写。

### 3.2 DB-GPT 的 fallback 策略值得记录

**DB-GPT 的做法**：[`ToolAction.run()`](D:\.Work\Practice\Python-Practice\references\DB-GPT\packages\dbgpt-core\src\dbgpt\agent\expand\actions\tool_action.py) 如果 LLM 输出的 JSON 解析失败，会尝试几个 fallback（识别纯数字结果、从文本中提取 tool name + expression 等），最后才返回 `ActionOutput(is_exe_success=False)`。

**当前 plan**：M10 降级方案写的是"解析层兼容 fenced JSON；字段名偏差只兼容明确同义词"，没有明确 JSON 完全无法解析时的行为。

**建议**：在 M10 降级方案或验收门中加一条策略说明：

> Plan JSON 解析失败时的行为：直接返回 `PlanValidationResult(is_valid=False, issue_tags=["invalid_query_plan"])`，不降级回旧链路、不做 SQL 自修复。理由：Phase 3A 的目标是让新链路可诊断，而不是在新链路不可用时悄悄回退——后者会掩盖 plan 质量问题，让对照报告失真。旧链路的结果已经在 M8 baseline 中冻结，对照时自然能看到差异。

---

## 四、有没有不该加进 plan 的内容？

**没有。** 这次修改加的 DB-GPT 引用都很克制：

- 每个模块只引 2–5 个具体文件，不是"参考 DB-GPT 整体架构"
- 每个引用都有"怎么落地"的 DataPilot 独有适配方案，不是"照搬 DB-GPT 的 X"
- P0 架构底线第 14 条明确划清了"设计参考"和"运行时底座"的边界
- 风险表第 6 行专门防"DB-GPT 借鉴变成平台迁移"
- 没有出现为了显得全面而堆砌 AWEL、Skill、Sandbox 等 Phase 3A 不该有的概念

AWEL 的引用分寸尤其好：只在 M11 trace_steps 中借鉴其 DAG node/context 的字段设计思路，代码仍是普通 Python pipeline，不引入任何 AWEL 依赖。

---

## 五、新加进来的方法在 plan 里写得是否够完善？

逐项检查 DB-GPT 新增借鉴点在各模块中的完善程度：

| 借鉴点 | 所在模块 | 完善度 | 说明 |
|---|---|---|---|
| `DBSchemaAssembler` 构建→写入→检索分层 | M9 | ★★★★☆ | 分层思路已落地。缺少大表字段 chunk 拆分策略（见 2.4）和 embedding 模型选择（见 2.2） |
| `DBSchemaRetriever` 表级召回 + 字段级补充 | M9 | ★★★★☆ | 两级检索思路已映射到 `doc_type` + metadata filter。缺少中文别名策略（见 2.3） |
| `SchemaLinkingOperator` LLM 二次筛选 | M9 | ★★☆☆☆ | 已隐含在 retriever→graph 链路中，但没有显式预留接口（见 2.1） |
| `Action.ai_out_schema` Pydantic→JSON 示例 | M10 | ★★★☆☆ | 思路提到了但实现步骤不够具体，缺少 `to_prompt_schema()` 的任务条目（见 3.1） |
| `ActionOutput` 诊断字段 | M10/M11 | ★★★★☆ | `PlanValidationResult(issue_tags, errors)` 已覆盖核心诊断。`observations` 可补到 M11（见 2.6） |
| AWEL DAG context 的分段 trace | M11 | ★★★★★ | `TraceStep(step_index, step_type, parent_step_id)` 完美对齐 AWEL 的 node/context 思路，不过度设计 |
| evaluate service 的 scene/metrics/context 抽象 | M12 | ★★★★★ | 已映射到对照报告的 capability 维度。边界清楚：M12 只输出 Markdown，不做服务化 |
| `BaseChat` 分段 trace 命名和失败记录 | M11 | ★★★★☆ | 已体现在 trace_steps 的 `error_type` 和分步记录中。缺少 fallback 策略（见 3.2） |

---

## 六、改进建议汇总（按优先级）

### P0 — 建议在进入 M9 前补齐

| # | 建议 | 影响模块 | 改动量 |
|---|---|---|---|
| 1 | M9 `document_builder`：明确 `keyword_text` 包含中文别名（来自 schema_desc 的描述），不给 keyword 召回留盲区 | M9 | 1 行说明 |
| 2 | M10 `to_prompt_schema()`：在任务清单里加一条自动从 Pydantic 字段生成 JSON 格式示例，让 `ai_out_schema` 模式落地更具体 | M10 | 1 条任务 |
| 3 | M10 plan 解析 fallback：明确 JSON 解析失败时直接 blocked + issue tag，不降级回旧链路。写出理由 | M10 | 1 条降级策略 |

### P1 — 建议在对应模块开工前补齐

| # | 建议 | 影响模块 | 改动量 |
|---|---|---|---|
| 4 | M9 大表字段拆分：`SchemaDocument.metadata` 必须包含 `table_name`，为字段级二次过滤留入口 | M9 | 1 行字段说明 |
| 5 | M9 Embedding 模型：在决策点里明确后续接哪个中文 embedding 模型和测试 fake 策略 | M9 | 1 条决策点 |
| 6 | M9 Schema Linking 预留：在 `graph.py` 或 `retriever.py` 里加 `SchemaLinkingFilter` 接口注释，不做实现 | M9 | 几行注释 |

### P2 — 建议在对应模块实现时顺手补

| # | 建议 | 影响模块 | 改动量 |
|---|---|---|---|
| 7 | M10 `thoughts` 取舍理由：在决策点中说明为什么不保留 CoT 字段 | M10 | 1 段说明 |
| 8 | M11 `TraceStep.observations`：加可选字段，区分"业务结果摘要"和"执行元观察" | M11 | 1 个可选字段 |

---

## 七、结语

这次 plan 修改的核心判断和边界控制都是对的。DB-GPT 的成熟结构被恰当地映射到了 DataPilot 的轻量主线上。上述 8 条建议都是**锦上添花**，不改变 plan 的主体结构、模块边界和依赖关系。改动量最大的是加几行注释或 1 条任务条目，不涉及重新设计。

如果要挑一个最值得改的，我选 **P0-2（M10 `to_prompt_schema()`）**——它把一个抽象的"借鉴 Action 模式"变成了一条具体的、面试能讲清楚的实现步骤。
