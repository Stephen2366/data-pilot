# DataPilot 多重链路架构（v2）

> 面向项目使用者梳理：同一个目标为什么会有多条执行路径、默认走哪条、什么情况下才切换。本文只讲当前架构；运行命令和环境变量以 [runbook.md](state/runbook.md) 为准，评测数字以 [eval-baselines.md](state/eval-baselines.md) 为准。

## 先看关系类型

| 关系 | 含义 | 项目中的例子 |
|---|---|---|
| **互斥选择** | 一次只走一条路径 | Qwen 或 DeepSeek；InMemory 或 Milvus |
| **优先级分流** | 先尝试更快的路径，未命中再走下一条 | 模板 SQL → 旧 LLM SQL |
| **并行合并** | 同时取多路结果，再统一排序 | 关键词召回 + 向量召回 |
| **串行防线** | 同一请求依次经过多层检查 | Plan Validation → SQL Guard |
| **旁路复核** | 不改变主结果，只补充解释证据 | M27 自动评分后的 review bundle |

## 总览

| 功能 | 路径 / 组件 | 关系 | 当前默认或边界 |
|---|---|---|---|
| API 查询 | legacy baseline / `new_text2sql` | 互斥选择 | API 与 M27 Eval 默认 `new_text2sql`；baseline 仅显式兼容 |
| SQL 生成 | 模板 / 全量 Schema LLM / 局部 Schema LLM | 优先级分流 + 显式切换 | 普通 API 走新链路的局部 Schema；旧链路才模板优先 |
| 主模型 | Qwen / DeepSeek / Mock | 互斥选择 | Qwen `qwen3.7-plus` |
| 检索后端 | InMemory / Milvus | 互斥选择 | InMemory + deterministic |
| Embedding | Deterministic / SiliconFlow / DashScope-Qwen | 与后端组合 | dense embedding 仅用于 Milvus 实验 |
| Schema 召回 | 关键词 / 向量 / 融合 | 并行合并 | 两路都跑；默认 weighted 融合 |
| SQL 安全 | Plan Validation / SQL Guard | 串行防线 | 新链路两层；旧链路只有 SQL Guard |
| Eval | legacy 只读 / M27 canonical | 新旧隔离 | 新运行只走 M27 |
| 人工复核 | 自动评分 / review bundle | 旁路复核 | review 不改分母、Gate 或 CI |

---

## 1. API 查询：baseline 与新 Text2SQL

`POST /api/query` 有两条互斥路径，由请求中的 `force_new_pipeline` 决定。

| 路径 | 适用情况 | 大致流程 |
|---|---|---|
| **baseline** | 显式 `force_new_pipeline=false` 的兼容排障 | 模板匹配 → 全量 Schema LLM（模板未命中时）→ SQL Guard → SQL 执行 → 图表 |
| **new_text2sql** | 普通 API 默认；M27 Eval | Schema Retrieval → SchemaGraph → QueryPlan → Plan Validation → SQL 生成 → SQL Guard → SQL 执行 → 图表 |

可以把 baseline 理解为“老的直达路线”，把 `new_text2sql` 理解为“先做查询计划、再执行的受控路线”。

现在 API 默认路径和评测默认路径一致，都是 `new_text2sql`。如果需要回查老模板行为，调用方必须显式传 `force_new_pipeline=false`，避免“少传字段”时悄悄走错链路。

相关代码：`app/api/query.py`、`engine/nl2sql/pipeline.py`。

## 2. SQL 生成：三种来源，不是三次都调用

| 来源 | 何时使用 | 是否调用 LLM |
|---|---|---|
| **白名单模板** | baseline 且问题命中固定业务模板 | 否 |
| **全量 Schema LLM** | baseline 的模板未命中 | 是 |
| **局部 Schema LLM** | `new_text2sql`；只使用检索到的 SchemaGraph | 是 |

legacy baseline 是“模板优先、未命中才调 LLM”。当前普通 API 的新链路不是在模板后面再兜底一次，而是默认直接使用 QueryPlan 和局部 Schema 来约束生成。

相关代码：`engine/nl2sql/templates.py`、`engine/nl2sql/generator.py`。

## 3. 主模型：Qwen、DeepSeek 与 Mock

| Provider | 用途 | 切换方式 |
|---|---|---|
| **Qwen** | 当前默认主模型，默认 `qwen3.7-plus` | `LLM_PROVIDER=qwen`；`QWEN_MODEL=...` |
| **DeepSeek** | 显式 A/B 或回退对照 | `LLM_PROVIDER=deepseek`；`LLM_MODEL=...` |
| **Mock** | 测试，不发真实网络请求 | 测试注入或显式测试配置 |

三者是互斥选择：一次请求只会创建一个主模型客户端。切模型属于长期基线选择，不能把一次实验结果直接当作默认切换依据。

相关代码：`engine/nl2sql/generator.py`。

## 4. 检索后端与 Embedding：两个独立开关

检索后端决定“向量放在哪里”；embedding 决定“文本怎样变成向量”。两者要能配套使用。

| 后端 + embedding | 状态 | 用途 |
|---|---|---|
| **InMemory + Deterministic** | 当前默认 | 本地开发、pytest、稳定的轻量检索 |
| **Milvus + Deterministic** | 可显式使用 | 验证 Milvus adapter 或隔离后端因素 |
| **Milvus + SiliconFlow** | 可显式实验 | 真实 dense embedding 对照 |
| **Milvus + DashScope/Qwen** | 可显式实验 | `qwen3.7-text-embedding` 对照 |

InMemory 只接受确定性稀疏向量，因此不能直接搭配 SiliconFlow 或 DashScope 的 dense embedding。Milvus 实验必须使用 clean collection，并校验文档数、向量维度和 schema-doc hash；这能避免旧 collection 的重复灌入污染比较结果。

默认仍是 `inmemory + deterministic`。Milvus、SiliconFlow、DashScope/Qwen 都是显式实验路径，不会因为一次运行而自动切换默认。

相关代码：`engine/schema_retrieval/vector_index.py`、`engine/schema_retrieval/embedding_provider.py`。

## 5. Schema 召回：两路并行，一种融合策略

每次 `new_text2sql` 检索都会同时运行：

1. **关键词召回**：擅长精确表名、字段名、指标名。
2. **向量召回**：擅长语义相近但措辞不同的问题。
3. **融合排序**：把两路候选合并，交给下游 SchemaGraph。

两路召回始终并行；融合策略才是可选项：

| 融合策略 | 状态 | 含义 |
|---|---|---|
| **weighted** | 当前默认 | 关键词分数加权后与向量分数合并 |
| **rrf** | 显式实验 | 只按两路名次融合，避免不同后端的原始分数尺度互相干扰 |

不要把 “关键词 + 向量” 误解为 `weighted + rrf` 同时执行：前者是两条召回路，后者是二选一的排序规则。

相关代码：`engine/schema_retrieval/retriever.py`。

## 6. 安全：新链路的前后两道门

| 防线 | 在哪里拦截 | 解决什么问题 |
|---|---|---|
| **Plan Validation** | SQL 生成前 | QueryPlan 是否引用了未召回的表、字段、指标或 Join；是否触碰敏感字段 |
| **SQL Guard** | SQL 执行前 | SQL 是否只读、是否符合角色权限和敏感字段策略 |

两道门不是替代关系。新链路两者都经过：前门防“计划本身不可信”，后门防“最终 SQL 不安全”。baseline 没有 QueryPlan，因此只经过 SQL Guard。

相关代码：`engine/nl2sql/planner.py`、`engine/sql_guard/`、`engine/tools/sql_tool.py`。

## 7. Eval：冻结旧体系，运行新体系

| 体系 | 是否还能新增运行 | 作用 |
|---|---|---|
| **legacy formal / challenge / diagnostic** | 否 | 保留旧 YAML、报告、trace、triage、audit，供历史追溯 |
| **M27 canonical eval** | 是 | 当前唯一的新评测入口 |

M27 的关键变化是：一个业务问题是一个 canonical Scenario；一次 Pipeline 执行产生的证据，可被 Result、Schema Context、Plan、Trace、Safety 等多个 typed assertion 共用。它避免了旧体系把相近问题复制成多条 case、重复调用 LLM 的问题。

Core、Stress、Manual Lab 是场景分类；Smoke、Reliability、Database Exception 是选择或执行协议，不是把题面复制成新的题库。Gate 由 suite policy 从 assertion 结果推导；`passed / failed / not_observed / unavailable` 的口径见 [eval-baselines.md](state/eval-baselines.md)。

相关代码：`eval/contracts.py`、`eval/evaluator.py`、`eval/selectors.py`、`eval/projector.py`、`eval/run_eval.py`。

## 8. 自动评分与人工复核：主线与旁路

```text
M27 EvalRun（自动执行、自动 scorer、Gate）
                 │
                 └── review bundle（只读证据）→ Codex / 人工复核
```

review bundle 从 completed EvalRun、短期 checkpoint 和 canonical contract 组装脱敏材料，并用 SHA-256 确认材料没有被替换。它可以帮助回答“自动失败到底是业务 SQL、输出合同、Schema Context，还是证据不足”，但不能：

- 改写自动评分结果；
- 改变分母、Gate 或 CI；
- 代替真实 scorer 形成第二套分数。

普通业务题没有 candidate SQL 时，复核只能是 `insufficient_evidence`；不能凭感觉判定模型对或错。

相关代码：`eval/review.py`、`eval/run_review.py`。

## 9. 日常怎么选

| 你的目标 | 应关注的路径 |
|---|---|
| 开发或启动普通 API | 默认 `new_text2sql`；只有排查旧兼容行为时显式 `force_new_pipeline=false` |
| 调试 Schema Retrieval / QueryPlan | `new_text2sql` + 默认 InMemory；Milvus 仅在明确实验时开启 |
| 做模型或检索对照 | 临时环境变量切换一个变量；阅读 runbook 与 eval-baselines 后执行 |
| 修改 Eval case / scorer / Gate | 只看 M27 canonical eval；不要使用旧 formal/challenge/diagnostic 分数作新结论 |
| 解释自动失败 | 先看 M27 artifact / report；需要业务核验再使用 review bundle |

## 进一步阅读

- 运行命令、环境变量、真实 Eval 执行纪律：[runbook.md](state/runbook.md)
- 当前评测口径、快照与人工复核边界：[eval-baselines.md](state/eval-baselines.md)
- 当前默认值、活跃坑与路线判断：[AI_CONTEXT.md](state/AI_CONTEXT.md)
- Milvus collection、embedding 与历史实验排查：[schema-retrieval-milvus-embedding.md](state/schema-retrieval-milvus-embedding.md)
