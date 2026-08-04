# DataPilot 开发日志（学习复盘）

> 给"未来的我"读的：每个模块讲清楚做了什么、我该理解什么、面试怎么讲。当前进度看 `docs/state/AI_CONTEXT.md`「当前状态」；完整技术档案和历史实验看 `docs/state/AI_CONTEXT_CHANGELOG.md`，查 bug 时按需追溯。
>
> M0 ~ M19 的记录已被拆分到 `docs/dev-log(M0-M19).md`；本文件记录从 M20 开始。

## ★ ★ M20 Milvus 修复与 embedding 测试

（2026-08-02）

**简述**：M20 修的是 **Milvus 实验链路可信度**：先保证 schema docs 只被干净、可追溯地写入索引，再谈 embedding 模型效果。

### 先用大白话讲

M19 之后我们发现一个很典型的评测坑：看起来是在比较 **Qwen embedding** 和默认检索，但底层 Milvus collection 其实已经被同一批 schema docs 重复灌了很多次。就像你想比较两位选手跑步，结果赛道上堆了 100 层重复障碍物，最后成绩差异不能说明选手真实能力，只能说明赛道不可信。

M20 做的事就是先把赛道清干净：每次实验用**唯一 collection**，collection 里应该只有当前 193 条 schema docs；报告里写清楚 collection 名、row_count、embedding 模型、维度和 `schema_docs_hash`；eval 一个 run 内复用同一个 Milvus index，不再每个 case 重复插入。与此同时，M20 也把 eval 的标准答案来源讲清楚：当前 `result_match` 仍是 SQLite deterministic oracle，不冒然切到 MySQL。

所以本模块的核心价值是：**让后续检索/embedding A/B 的证据可信，而不是让一次分数变好看。**

### 这次做了什么

一开始的问题是：M19 复测发现 Qwen embedding 没带来稳定收益，但继续排查发现固定 collection `datapilot_schema_docs` 的行数远高于 schema docs 数量。当前 schema docs 是 193 条，历史 collection 却有约 1.9 万行，这说明它被**重复写入**了很多次。

这次先做了一个关键取舍：不顺手改默认 embedding、不把 Milvus 设成默认、不改正式 eval case，也不把 `result_match` 的 oracle 直接切 MySQL。因为这些都会改变长期基线。最终只做 M20 范围内的事：**索引卫生 + 标准答案审计 + clean run 复测**。

代码上，`MilvusVectorIndex` 不再无脑 insert。它会检查已有 collection 的 row_count 和 vector dimension：干净就复用，污染就直接报错，提示使用唯一 collection 或显式 reset。`eval/run_eval.py` 在 Milvus 实验时会预建一次 shared vector index，挂到 `app.state`，让 32 条 diagnostic case 共用同一个索引。报告也新增了 **Eval Runtime Metadata**，能看到 `schema_docs_hash`、collection、row_count 和 oracle backend。

验证上，Milvus smoke 证明 clean collection 下 `row_count=193`。DeepSeek + clean Milvus + Qwen embedding diagnostic 跑出 `17/32`，没有超过 M19 污染链路的 `19/32`。这个结果不是坏消息，而是一个更诚实的结论：之前污染链路不能当证据；clean 链路下 Qwen embedding 暂时没有稳定收益，但也不能因为一次 run 就盖棺定论。

`qwen3.7-max` + clean Milvus + Qwen embedding diagnostic ：diagnostic `21/32`，是 clean Qwen 链路的首个完整数据点。它高于 DeepSeek 的 `17/32`，但看失败结构会发现，提升主要来自 Qwen 让 query_plan / plan_validation 类失败消失了（5→0、2→0），`schema_context` 反而从 5 升到 7，仍是最大失败簇——也就是说 **这部分差距主要来自模型本身，不是 Qwen embedding 的功劳，schema 上下文修复依然是下一步优先级**。

所以这个实验的结论不是“Qwen embedding 已经解决 schema retrieval”，而是：**Qwen LLM 能改善规划失败，但 schema 上下文问题仍要单独修**。这也是后来新增 retrieval-only benchmark 的原因：先把 embedding 检索能力从完整 Text2SQL 链路里拆出来看，再决定下一步修 fusion / rerank。

**Retrieval-only embedding benchmark：**M20 收尾后又补了一组更干净的小实验：不让 LLM 写 SQL，只让 schema retrieval 对 10 条专门设计的问题召回表、字段、指标和关系。这样可以单独看 Milvus + embedding 有没有能力，而不是被 SQL 生成、query plan、result_match 一起搅在分数里。

结果：默认 deterministic embedding 的 `vector-only recall=0.787`，Milvus + Qwen embedding 的 `vector-only recall=0.929`，说明 Qwen embedding 对 schema 语义检索确实更强；但两者 merged recall 都是 `0.738`，说明当前短板不在 Milvus 写入或 embedding 模型本身，而更像在 keyword/vector 融合、排序和 rerank 策略。换句话说，embedding “有信号”，只是现有合并策略没有把这个信号转成最终上下文收益。

### 新概念

- **Index Hygiene**：索引卫生。意思是向量库里的数据版本、数量、embedding 模型和维度都要可追溯。如果 collection 里混进旧文档、重复文档或不同维度的向量，检索结果就像 MySQL 表里有重复脏数据一样，后面的模型再强也会被误导。
- **schema_docs_hash**：Schema 文档指纹。M20 用 `doc_id + keyword_text + vector_text` 算一个 hash，类似后端里给配置文件或 migration 打版本号。以后看到报告里的 hash，就知道这次向量索引用的是哪一版 schema docs。
- **run-scoped vector index**：一次 eval run 内共享的向量索引。以前每个 case 都重新建 Milvus index，相当于每次请求都重新建表并插入全量数据；M20 改成 run 开始时建一次，后面每条 case 只 search。
- **oracle backend**：评测标准答案的执行来源。当前 `result_match` 的 expected SQL 是在 SQLite seed 上执行，不是直接查 MySQL。M20 先把这个事实写进报告，避免读报告的人误以为它一定代表当前 MySQL 真相。

### 代码阅读路线

1. **Schema 文档版本**：`engine/schema_retrieval/document_builder.py`
   先看 `build_schema_documents()`，它把字段、指标、关系整理成 193 条可检索文档；再看 `schema_documents_hash()`，它给这批文档打版本指纹。重点理解：hash 不参与召回，只服务实验复现和报告追溯。

2. **Milvus 护栏**：`engine/schema_retrieval/vector_index.py`
   主角是 `MilvusVectorIndex.__init__()`。读的时候按顺序看：连接 Milvus，检查 collection 是否存在，检查 row_count 和 vector dimension，决定是插入、复用还是拒绝。这里的关键不是“怎么调 Milvus API”，而是 **不允许污染 collection 静默进入实验**。

3. **run 内复用入口**：`engine/schema_retrieval/retriever.py`
   看 `build_configured_schema_vector_index()`，它一次性构建 documents、vector index 和 hash，交给 eval runner 复用。`retrieve_schema()` 仍然按每个问题计算 keyword hits 和 merged hits，只是 vector search 复用同一个 index。

4. **API / Pipeline 传递**：`app/api/query.py` 和 `engine/nl2sql/pipeline.py`
   API 层从 `request.app.state.schema_vector_index` 取共享索引，传给 `run_text2sql_pipeline()`；pipeline 再传给 `retrieve_schema()`。这条链路很轻，只是多传一个可选对象，不改变 `/api/query` 的响应契约。

5. **Eval 报告与审计**：`eval/run_eval.py`
   看 `_build_eval_schema_vector_index()` 和 `write_report()`。前者只在 `new_text2sql + milvus` 时预建 index，后者把 runtime metadata 写进 Markdown。这样报告不只告诉你过了几条，还告诉你这次用的是哪一个 collection 和哪一个 oracle。

6. **验证脚本**：`scripts/audit_m20_eval_ground_truth.py` 和 `scripts/smoke_m20_milvus_index.py`
   audit 脚本用当前 MySQL 执行 expected SQL，但不改变 scorer；smoke 脚本创建唯一 Milvus collection，检查 `row_count == 193`。这两个脚本是 M20 的证据来源。

核心链路：

`eval.run_eval`
→ `build_configured_schema_vector_index`
→ `MilvusVectorIndex`
→ `app.state.schema_vector_index`
→ `/api/query`
→ `run_text2sql_pipeline`
→ `retrieve_schema`
→ `Eval Runtime Metadata`

### 设计要点

- **唯一 collection 优先**：M20 选了每次实验唯一 collection，而不是固定 collection 反复 reset。这样最隔离、最好复现，也不容易误删别的实验数据。
- **拒绝污染而不是自动猜修复**：如果已有 collection 行数或维度不匹配，代码直接报错。这里没有临时 upsert，因为 upsert 是更接近长期服务形态的方案，需要单独验证 Milvus API 一致性。
- **不改 benchmark 口径**：MySQL audit 证明 expected SQL 当前可执行，但 `result_match` 仍保留 SQLite oracle。这样避免 M20 同时改变索引和评分标准，导致结果无法解释。

### 面试怎么讲

“我在做 Text2SQL 的 schema retrieval A/B 时发现一个评测基础设施问题：Milvus collection 被**重复灌入**，同一批 193 条 schema docs 累积到上万行，导致 embedding A/B 的**检索结果不可信**。我没有直接换模型或改 prompt，而是先做 index hygiene：每次实验使用**唯一 collection**，Milvus adapter 检查 row_count 和向量维度，不匹配就拒绝复用；eval runner 在一个 run 内预建并复用同一个 **vector index**，避免每个 case 重新 insert；报告里写出 schema_docs_hash、collection、row_count 和 oracle backend。最后 clean collection smoke 证明 row_count 回到 193，并用 clean Milvus 重新跑 diagnostic。结果没有提分，但这个结论更可信，也说明不应该自动切默认 embedding。”

“我没有直接根据 Text2SQL 总分判断 embedding 好坏，而是加了一个 retrieval-only benchmark，把检索从生成链路里拆出来。这个实验发现 Qwen embedding 的向量召回明显更好，但最终 merged recall 没变，因此下一步优化方向应该是 fusion / rerank，而不是盲目继续换 embedding 或把 Milvus 切默认。

1. **[基础追问] 为什么 M20 没有提分也算完成？**

   因为 M20 的目标不是优化 Text2SQL 正确率，而是修复评测和索引可信度。污染 collection 下的分数无论高低都不能直接解释 embedding 好坏；clean collection 后即使分数下降，也说明我们拿到了更干净的证据。工程里有时先修仪表盘和数据地基，比直接刷指标更重要。

2. **[工程/深挖追问] 为什么不用 upsert 直接覆盖旧 doc_id？**

   upsert 更像长期在线服务方案，但要确认 Milvus 当前版本对主键、delete/upsert、一致性和索引刷新行为的具体语义。M20 是实验链路卫生修复，优先选唯一 collection，隔离性更强、风险更小。后续如果 Milvus 要成为正式服务路径，再单独实现 upsert / delete-by-doc-id。

3. **[压力追问] 你这次 clean run 只有 17/32，比污染链路还低，那是不是说明修坏了？**

   这个质疑合理，但要先区分目标。M20 改的是索引生命周期和报告可追溯，不是 prompt 或 schema doc 内容；clean run 的 row_count 是 193，说明索引污染被清掉了。分数低不能证明代码修坏了，它更可能说明之前污染链路的结果本来就不可解释，或者 Qwen embedding 对当前 schema doc 粒度没有稳定收益。后续要提升能力，应继续看 schema_context、query_plan 和 result_match 的失败结构，而不是回到污染 collection。

### 验证与下一步

- 验证：focused tests `14 passed`；相关回归 `27 passed`；全量 pytest `127 passed`；Milvus smoke `row_count=193`；DeepSeek + clean Milvus + Qwen embedding diagnostic `17/32`；Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic `21/32`（时间戳命名 collection，`row_count=193`、run_scoped）。
- Warning：只有既有 Starlette/httpx warning 和 Windows LF/CRLF 提示，不影响 M20。
- 下一步：M20 待 `accept-module`；之后进入 Phase 3 RAG / Hybrid 前置规划，或单独确认是否调整 `result_match` oracle / eval case 口径。

可复制验证命令：

```powershell
# M20 focused tests：预期 14 passed
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m20_schema_index_hygiene.py tests\test_phase3a_schema_retrieval.py -q --basetemp=.agent_work\temp\pytest-m20-focused

# Milvus clean collection smoke：预期 PASS，final_row_count=193
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.smoke_m20_milvus_index --output .agent_work\temp\m20-milvus-index-smoke.md
```

## ★ ★ M21 weighted VS RRF / 本地 vs embedding

（2026-08-03）

**简述**：M21 验证了“检索召回更高”不等于“Text2SQL 更准”：RRF 把更多 relation / metric 文档放进上下文，却在同配置真实 diagnostic 上从 `21/32` 降到 `18/32`，因此保持默认 weighted，不为漂亮的离线指标切策略。

### 先用大白话讲

M20 证明 Qwen embedding 像一支更灵敏的雷达，能看到更多相关的 schema 文档；但旧的合并方式没有把信号送到驾驶舱。M21 试了 **RRF（Reciprocal Rank Fusion）**：不比较两台雷达分数谁大，而是按各自的名次投票。它在 retrieval-only 测试上确实把 relation recall 从 `0.633` 拉到 `0.967`，但真正让 LLM 写 SQL 时，更多上下文也会改变 QueryPlan 的选择，反而新增了 plan validation 失败。

所以本模块的核心价值是：**把“检索指标变好”与“端到端能力变好”分开验证，并用否定实验保护默认基线。**

### 这次做了什么

代码为 `retrieve_schema()` 增加了默认不变的 `weighted` 与显式 `rrf` 两种 fusion；CLI、eval request 和 trace metadata 都会记录本轮策略。RRF 只使用问题和候选 hit 的分数 / rank，**绝不使用** benchmark 的 `expected_tables` 或 `expected_columns`，否则就像考试时把答案塞给排序器。

离线测试中，deterministic merged recall `0.738 → 0.802`；Milvus + Qwen embedding 则 `0.738 → 0.929`，metric `0.600 → 0.900`、relation `0.633 → 0.967`。但固定同一个 clean collection、embedding、模型和 32 条 diagnostic 后，weighted 是 `21/32`，RRF 是 `18/32`；triage 显示 `schema_context` 少 1 条，却多了 3 条 `plan_validation`。因此 RRF 被记录为**否定实验**，没有改默认策略、top_k、schema docs 或评测口径。

**补充1：测试**

- `qwen3.7-max` 通过率仅 `11/32`，因为其中 12 条 `query_plan` 请求撞上客户端固定的 `45s timeout`。
- `qwen3.7-plus` diagnostic 为 `21/32`；失败主要转移到 **schema_context / schema_retrieval**，LLM timeout 型失败明显减少。说明：plus 在当前评测链路下更稳定，但总分仍不足以单独触发默认模型切换；后续还要结合重复 run、延迟成本和 schema context 修复一起判断。

**补充2：fusion → weighted VS RRF**

固定 `qwen3.7-plus`、同一 clean Milvus、同一 embedding 和 32 条 case，**只改变 fusion**：`weighted=21/32`，`RRF=20/32`。RRF 虽让 `schema_context` 失败少 1 条，却让 `query_plan` 和 `result_match` 各多 1 条，因此 **离线召回提升没有转化为端到端收益**，`weighted` 默认结论得到同模型 A/B 支持。

**补充3：地基体检**

固定 `qwen3.7-plus` 做了两件事：一是 weighted `21/32` 与 RRF `20/32` 的同模型对照；二是逐 case 检查 retrieval、SchemaGraph 和最终 SQL。结果显示，Qwen embedding 的 vector recall 更高，但没有发现明确的“目标表已召回、却被 context assembly 丢掉”的主要失败；不少 `schema_context` 实际是 SQL 漏表、alias 或输出契约问题。

因此补充修正了 triage：保留旧 failure stage，同时增加 `output_table_contract` / `output_column_contract` 等细分类，避免把 SQL 生成问题误判成 embedding 问题。路线收敛为：先处理输出契约和 QueryPlan → SQL 稳定性，再尝试 rerank 等 retrieval 方法。

**补充4：本地检索 VS embedding**

为了回答“Qwen embedding 是否真的比本地检索更好”，最后固定 `qwen3.7-plus`、weighted、同一 32 条 diagnostic、同一 oracle，只改变 Schema Retrieval：

- 本地 `inmemory + deterministic`：`21/32`
- clean Milvus + Qwen `qwen3.7-text-embedding`：`21/32`

两组 `schema_context=6`，输出表/列契约和结果契约的 subtype 分布也完全相同；只有 3 个 case 的失败阶段发生转移。因此这次没有证明 embedding 能带来端到端提分，但证明了对照条件下的瓶颈仍在输出契约、QueryPlan/SQL 生成和少量 retrieval 失败。下一步把地基交给 M22，不再继续无目的堆 embedding 参数。

### 新概念

- **RRF**：一种 rank-based fusion。它像两份“推荐名单”按名次累积投票，避免 keyword 分数和 vector 相似度的数值尺度不同，直接相加不公平。
- **标签泄漏**：把评测集的 expected 表、字段等正确答案交给线上排序逻辑。这样分数会虚高，真实用户请求却没有这些信息；M21 明确禁止这种做法。
- **否定实验**：结果没有被采用也不是白做。M21 用同配置 A/B 证明 RRF 目前不能稳定改善 Text2SQL，这比把一次离线高分误切为默认更有工程价值。

### 代码阅读路线

1. **融合核心**：`engine/schema_retrieval/retriever.py`
   从 `_merge_hits()` 看 weighted 如何保持旧行为、RRF 如何只按 rank 计分；再看 `retrieve_schema()` 的显式参数，理解默认请求为何不会变化。
2. **实验入口**：`eval/run_schema_retrieval_benchmark.py` 与 `eval/run_eval.py`
   前者只测 schema graph 召回，后者通过 API 跑真实 Text2SQL；两者都把 fusion strategy 和 schema docs metadata 写入报告，保证 A/B 可追溯。
3. **请求与 trace 传递**：`app/schemas/agent.py`、`app/api/query.py`、`engine/nl2sql/pipeline.py`
   `schema_fusion_strategy` 从显式请求传到 retrieval，并进入 trace metadata；它是实验开关，不改变响应体契约。

### 设计要点

- **默认不动**：`weighted` 是已有稳定基线，RRF 必须显式选择；避免一次实验影响所有 API / eval。
- **先离线、后端到端**：retrieval-only 先证明候选值得继续看，再用同配置 diagnostic 检查是否把失败迁移到别的 pipeline 阶段。
- **当前边界**：不靠增大 top_k、bundle docs 或 reranker 掩盖问题；这些会改变上下文结构或长期路线，需要单独决定。

### 面试怎么讲

“我做过一次 schema retrieval fusion 实验。Qwen embedding 的 vector recall 明显高，但 merged recall 没提升，所以我加了一个显式 RRF 对照，并严格避免用 benchmark 的 expected 标签参与排序。RRF 在 retrieval-only 上把 Milvus + Qwen 的 merged recall 从 0.738 提到 0.929，relation recall 到 0.967；但同配置的 32 条真实 Text2SQL diagnostic 从 21/32 降到 18/32，plan validation 失败增加。我的结论不是强行把 RRF 切默认，而是保留 weighted、记录否定实验，并把下一步定位到 context assembly 和 QueryPlan 的耦合。”

1. **[压力追问] 你离线 recall 提升这么多却没有收益，是不是 benchmark 没意义？**

   benchmark 仍有意义：它证明向量信号与 fusion 排序本身确实发生了变化。但它不能替代端到端评测，因为 LLM 还会受 prompt 长度、文档顺序和 QueryPlan 约束影响。正确做法是两层都保留：用 retrieval-only 定位检索问题，用 diagnostic 检查系统结果，不能拿其中一层代替另一层。

### 验证与下一步

- 验证：focused `16 passed`、related `22 passed`、全量 `133 passed`；Milvus collection row_count `193`；weighted/RRF diagnostic `21/32 → 18/32`。既有 Starlette/httpx deprecation warning 不影响模块。
- 下一步：先逐 case 分析 RRF 改变的 context 与 QueryPlan；如需 doc_type weighting、bundle docs、context budget、reranker 或默认策略切换，先单独做长期决策。

**本地启动体验：**本模块没有独立页面；可运行 `python -m eval.run_schema_retrieval_benchmark --top-k 12 --fusion-strategy weighted`，再把策略改为 `rrf` 对比 `.agent_work/temp` 中的报告。
