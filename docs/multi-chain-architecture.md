# DataPilot 多重链路架构

> 梳理项目中所有"同一功能存在多条执行路径"的模式，说明各链路的关系、默认行为和切换机制。

---

## 1. API 请求处理链路 —— 旧 vs 新

收到 `/api/query` 请求后，根据 `force_new_pipeline` 字段分叉。

| | 旧链路 (baseline) | 新链路 (new_text2sql) |
|---|---|---|
| **触发条件** | 默认 `force_new_pipeline=False` | `force_new_pipeline=True` |
| **处理流程** | 模板匹配 → LLM 全量 schema 生成 SQL → SQL Tool | Schema Retrieval → SchemaGraph → QueryPlan → Plan Validation → SQL 生成 → SQL Guard → SQL 执行 → Chart |
| **入口代码** | [app/api/query.py:229](app/api/query.py#L229) 主分支 | [app/api/query.py:245](app/api/query.py#L245) 分支 |
| **核心代码** | `match_template()` → `generate_sql()` → `run_sql_tool()` | [engine/nl2sql/pipeline.py:194](engine/nl2sql/pipeline.py#L194) `run_text2sql_pipeline()` |

**默认**：旧链路。

**切换**：API 请求体 `{"force_new_pipeline": true}`。评测脚本通过 `--pipeline-mode new_text2sql` 传参。

**新链路步骤详解**（7 步，各步失败均结构化拦截，不降级）：

| 步骤 | 名称 | 职责 |
|------|------|------|
| 1 | Schema Retrieval | 关键词 + 向量双路召回局部 schema 文档 |
| 2 | SchemaGraph | 构建问题相关的表/字段/Join 子图 |
| 3 | QueryPlan | LLM 生成结构化查询计划 |
| 4 | Plan Validation | 校验表/字段/指标/Join 均来自可信上下文 |
| 5 | SQL Generation | 基于局部 Schema 生成 SQL |
| 6 | SQL Guard + Execution | AST 只读检查 + RBAC + 执行 |
| 7 | Chart | 自动判断图表类型并生成 chart_spec |

---

## 2. NL2SQL SQL 生成 —— 三条路径

旧链路内部存在两层 fallback，新链路有自己独立的生成方式。

| 路径 | 触发条件 | 说明 | 代码 |
|------|----------|------|------|
| **模板匹配** | 关键词命中 5 个白名单模板 | 不调 LLM，直接返回预写参数化 SQL | [engine/nl2sql/templates.py:136](engine/nl2sql/templates.py#L136) |
| **LLM 全量 schema** | 模板未命中 | 把全部表结构塞进 prompt，DeepSeek 生成 SQL | [engine/nl2sql/generator.py:184](engine/nl2sql/generator.py#L184) |
| **LLM 局部 schema** | 新链路专属 | 基于 QueryPlan + 局部 SchemaGraph 生成 SQL | [engine/nl2sql/generator.py:219](engine/nl2sql/generator.py#L219) |

**5 个白名单模板**：退款率最高商品、各渠道订单量、GMV、Top 退款原因、待处理高优先级工单。

**默认**：模板优先 → 未命中则 LLM 全量 schema → `force_new_pipeline` 时走局部 schema。

---

## 3. Schema Retrieval 向量索引 —— In-Memory vs Milvus

| | InMemoryVectorIndex | MilvusVectorIndex |
|---|---|---|
| **存储** | 进程内 Python dict | 外部 Milvus 向量数据库 |
| **依赖** | 无 | 需启动 Milvus 服务 + `MILVUS_URI` 环境变量 |
| **用途** | pytest / 本地诊断 / 默认路径 | 生产候选 |
| **代码** | [engine/schema_retrieval/vector_index.py:67](engine/schema_retrieval/vector_index.py#L67) | [engine/schema_retrieval/vector_index.py:105](engine/schema_retrieval/vector_index.py#L105) |

**默认**：InMemory。两者实现同一个 `VectorIndex` Protocol（`search(query, top_k) → list[SchemaHit]`）。

**切换**：`retrieve_schema(vector_index=None)` → InMemory；传入 `MilvusVectorIndex` 实例 → Milvus。

---

## 4. Embedding Provider —— Deterministic vs SiliconFlow

| | DeterministicEmbeddingProvider | SiliconFlowEmbeddingProvider |
|---|---|---|
| **向量类型** | 稀疏 (token 计数 + 中文 bigram) | 稠密 (BAAI/bge-m3) |
| **联网** | 否，纯本地，结果可重复 | 是，调 SiliconFlow OpenAI-like API |
| **用途** | pytest / 本地诊断 | M9.2 实验验证真实中文 embedding 效果 |
| **代码** | [engine/schema_retrieval/vector_index.py:39](engine/schema_retrieval/vector_index.py#L39) | [engine/schema_retrieval/embedding_provider.py:29](engine/schema_retrieval/embedding_provider.py#L29) |

两者实现同一个 `EmbeddingProvider` Protocol（`embed(text) → EmbeddingVector`）。

---

### 3+4 组合：检索方案矩阵

VectorIndex × EmbeddingProvider = 4 种理论组合：

| 组合 | 验证状态 | 用途 |
|------|----------|------|
| **InMemory + Deterministic** | ✅ 默认 | pytest、本地诊断、CI |
| InMemory + SiliconFlow | ❌ 未验证 | 理论可行但无使用场景 |
| Milvus + Deterministic | ✅ M9.1 smoke | 验证 Milvus adapter 正确性 |
| **Milvus + SiliconFlow** | ✅ M9.2 smoke | 生产候选方案 |

---

## 5. Schema Retrieval 搜索方法 —— 关键词 + 向量双路融合

`retrieve_schema()` 内部每次同时跑两路，然后融合输出。

| 路 | 方法 | 权重 | 代码 |
|----|------|------|------|
| **关键词搜索** | token 分词 + 表名/字段名/指标名精确命中加权 | 融合时 ×1.2 | [engine/schema_retrieval/retriever.py:52](engine/schema_retrieval/retriever.py#L52) |
| **向量搜索** | cosine 相似度（走 InMemory 或 Milvus） | 融合时 ×1.0 | 由 VectorIndex 实现 |
| **融合** | 加权分 + RRF 分数 → `merged_hits` | — | [engine/schema_retrieval/retriever.py:70](engine/schema_retrieval/retriever.py#L70) |

**默认**：两路始终并行跑，融合结果作为下游输入。这是一种"不切换、始终多路并行"的模式。

输出结构 `SchemaRetrievalResult` 保留了三段数据（[engine/schema_retrieval/objects.py:50](engine/schema_retrieval/objects.py#L50)）：

```python
keyword_hits   # 关键词召回
vector_hits    # 向量召回
merged_hits    # 融合结果（下游消费）
```

---

## 6. SQL Guard 安全层级 —— 双层纵深防御

两层串行执行，不可绕过。

| 层 | 职责 | 实现方式 | 代码 |
|----|------|----------|------|
| **只读检查** | AST 解析，只允许单条 SELECT | sqlglot 解析 SQL | [engine/sql_guard/guard.py:26](engine/sql_guard/guard.py#L26) |
| **策略校验** | 表级 RBAC + 敏感字段拦截 | 内部调用只读检查 → role_policy → AST 提取访问对象 | [engine/sql_guard/policy.py:84](engine/sql_guard/policy.py#L84) |

策略校验内部先调 `validate_readonly_sql()`，再逐层检查。

**RBAC 角色策略矩阵**（[engine/sql_guard/rbac.py:37](engine/sql_guard/rbac.py#L37)）：

| 角色 | 可访问表 | 敏感字段 |
|------|----------|----------|
| `admin` | 全部 14 张表 | ✅ 允许 |
| `ops` | 全部 14 张表 | ❌ 禁止 |
| `customer_service` | tickets, knowledge_docs | ❌ 禁止 |
| `demo_user` | products, channels, knowledge_docs, product_categories, orders_wide | ❌ 禁止 |

**默认**：两层始终串行启用，所有 SQL 来源（模板/LLM 全量/LLM 局部）统一经过 `run_sql_tool()` 内的 `validate_sql_policy()`。

---

## 7. 安全检查双重机制 —— Plan 预检 + Runtime 门禁

新链路独有的"belt-and-suspenders"模式：生成 SQL 前先校验，执行前再校验。

| 阶段 | 做什么 | 拦截级别 | 代码 |
|------|--------|----------|------|
| **Plan Validation** | 检查 QueryPlan 的表/字段/指标/Join 是否来自局部 SchemaGraph | 生成 SQL 前拦截 | [engine/nl2sql/planner.py:190](engine/nl2sql/planner.py#L190) |
| **SQL Guard** | AST 级只读 + RBAC + 敏感字段最终检查 | 执行前拦截（所有链路都走） | [engine/tools/sql_tool.py:77](engine/tools/sql_tool.py#L77) |

Plan Validation 的 5 项子检查：

| 检查项 | issue_tag |
|--------|-----------|
| 表是否在局部 SchemaGraph 内 | `missing_table` |
| 字段是否在局部 SchemaGraph 内 | `missing_column` |
| 指标是否被召回 | `invalid_query_plan` |
| Join relation_id 是否合法 | `invalid_join_path` |
| 非 admin 角色是否访问了敏感字段 | `sensitive_field_access` |

**默认**：新链路两层都走；旧链路只走 SQL Guard。两者不是切换关系，是互补的纵深防御。

---

## 8. LLM Provider —— DeepSeek vs Mock

| | DeepSeekChatClient | Mock |
|---|---|---|
| **模型** | deepseek-v4-pro | 无，测试用 |
| **代码** | [engine/nl2sql/generator.py:50](engine/nl2sql/generator.py#L50) | [engine/nl2sql/generator.py:103](engine/nl2sql/generator.py#L103) `get_default_llm_client()` |

两者实现同一个 `LLMClient` Protocol（`complete(prompt) → str`）。

**默认**：DeepSeek。

**切换**：`.env` 中 `LLM_PROVIDER` 环境变量。`get_default_llm_client()` 按配置决定。

---

## 总结对照表

| # | 维度 | 链路 A (默认) | 链路 B | 链路 C | 关系 | 切换方式 |
|---|------|--------------|--------|--------|------|----------|
| 1 | API 请求处理 | baseline | new_text2sql | — | **互斥** | `force_new_pipeline` flag |
| 2 | SQL 生成 | 模板匹配 | LLM 全量 schema | LLM 局部 schema | **优先级 fallback** | 模板命中→A，未命中→B；force→C |
| 3 | 向量索引 | InMemory | Milvus | — | **互斥** | `vector_index` 参数 |
| 4 | Embedding | Deterministic | SiliconFlow | — | **互斥** | `embedding_provider` 参数 |
| 5 | 搜索方法 | 关键词 + 向量 → 融合 | — | — | **始终并行** | 不可切换 |
| 6 | SQL 安全层 | 只读检查 → 策略校验 | — | — | **始终串行** | 不可切换 |
| 7 | 安全检查 | Plan Validation | SQL Guard | — | **互补纵深** | 新链路两者都走，旧链路只走 Guard |
| 8 | LLM Provider | DeepSeek | Mock | — | **互斥** | `LLM_PROVIDER` env |

**关系类型说明**：

- **互斥**：同一时刻只走一条
- **优先级 fallback**：按顺序尝试，命中即停
- **始终并行**：每次同时跑多路，融合输出
- **始终串行**：每次依次经过多层，不可绕过
- **互补纵深**：两层检查不同阶段，共同提升安全性

---

## 关键代码位置速查

| 文件 | 职责 |
|------|------|
| [app/api/query.py](app/api/query.py) | `/api/query` 入口，新旧链路分叉点 |
| [engine/nl2sql/pipeline.py](engine/nl2sql/pipeline.py) | 新 Text2SQL pipeline（7 步） |
| [engine/nl2sql/templates.py](engine/nl2sql/templates.py) | 模板匹配（5 个白名单） |
| [engine/nl2sql/generator.py](engine/nl2sql/generator.py) | LLM SQL 生成 ×3（全量/局部/QueryPlan） |
| [engine/nl2sql/planner.py](engine/nl2sql/planner.py) | QueryPlan 定义 + 自检 |
| [engine/nl2sql/schema_loader.py](engine/nl2sql/schema_loader.py) | 全量 DomainSchema 加载 |
| [engine/schema_retrieval/retriever.py](engine/schema_retrieval/retriever.py) | 关键词 + 向量双路检索入口 |
| [engine/schema_retrieval/vector_index.py](engine/schema_retrieval/vector_index.py) | InMemory / Milvus 向量索引 |
| [engine/schema_retrieval/embedding_provider.py](engine/schema_retrieval/embedding_provider.py) | SiliconFlow embedding |
| [engine/schema_retrieval/graph.py](engine/schema_retrieval/graph.py) | 局部 SchemaGraph 构建 + JoinPath BFS |
| [engine/schema_retrieval/objects.py](engine/schema_retrieval/objects.py) | SchemaDocument / SchemaHit / SchemaGraph 数据结构 |
| [engine/sql_guard/guard.py](engine/sql_guard/guard.py) | 只读检查 |
| [engine/sql_guard/policy.py](engine/sql_guard/policy.py) | 表级 RBAC + 敏感字段检查 |
| [engine/sql_guard/rbac.py](engine/sql_guard/rbac.py) | 4 角色权限矩阵 |
| [engine/tools/sql_tool.py](engine/tools/sql_tool.py) | SQL 执行 + SQL Guard 统一入口 |
| [engine/tools/chart_tool.py](engine/tools/chart_tool.py) | 自动图表决策 |
