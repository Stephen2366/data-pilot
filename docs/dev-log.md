# DataPilot 开发日志（学习复盘）

> 给"未来的我"读的：每个模块讲清楚做了什么、我该理解什么、面试怎么讲。当前进度看 `docs/state/AI_CONTEXT.md`「当前状态」；完整技术档案和历史实验看 `docs/state/AI_CONTEXT_CHANGELOG.md`，查 bug 时按需追溯。
>
> M0 ~ M19 的记录已被拆分到 `docs/dev-log(M0-M19).md`；本文件记录从 M20 开始。

## ★ ★ M20 Milvus collection 修复与 embedding 测试

（2026-08-02）

**简述**：M20 修的是 **Milvus 实验链路可信度**：先保证 schema docs 只被干净、可追溯地写入索引，再谈 embedding 模型效果。

### 先用大白话讲

M19 之后我们发现一个很典型的评测坑：看起来是在比较 **Qwen embedding** 和默认检索，但底层 Milvus collection 其实已经被同一批 schema docs 重复灌了很多次。就像你想比较两位选手跑步，结果赛道上堆了 100 层重复障碍物，最后成绩差异不能说明选手真实能力，只能说明赛道不可信。

M20 做的事就是先把赛道清干净：每次实验用**唯一 collection**，collection 里应该只有当前 193 条 schema docs；报告里写清楚 collection 名、row_count、embedding 模型、维度和 `schema_docs_hash`；eval 一个 run 内复用同一个 Milvus index，不再每个 case 重复插入。与此同时，M20 也把 eval 的标准答案来源讲清楚：当前 `result_match` 仍是 SQLite deterministic oracle，不冒然切到 MySQL。

所以本模块的核心价值是：**让后续检索/embedding A/B 的证据可信，而不是让一次分数变好看。**

### 这次做了什么

一开始的问题是：M19 复测发现 Qwen embedding 没带来稳定收益，但继续排查发现固定 collection `datapilot_schema_docs` 的行数远高于 schema docs 数量。当前 schema docs 是 193 条，历史 collection 却有约 1.9 万行，这说明它被**重复写入**了很多次。

这次先做了一个关键取舍：不顺手改默认 embedding、不把 Milvus 设成默认、不改正式 eval case，也不把 `result_match` 的 oracle 直接切 MySQL。因为这些都会改变长期基线。最终只做 M20 范围内的事：**索引卫生 + 标准答案审计 + clean run 复测**。

代码上，`MilvusVectorIndex` 不再无脑 insert。它会检查已有 **collection 的 row_count 和 vector dimension**：干净就复用，污染就直接报错，提示使用唯一 collection 或显式 reset。`eval/run_eval.py` 在 Milvus 实验时会预建一次 shared vector index，挂到 `app.state`，让 32 条 diagnostic case 共用同一个索引。报告也新增了 **Eval Runtime Metadata**，能看到 `schema_docs_hash`、collection、row_count 和 oracle backend。

验证上，Milvus smoke 证明 clean collection 下 `row_count=193`。DeepSeek + clean Milvus + Qwen embedding diagnostic 跑出 `17/32`，没有超过 M19 污染链路的 `19/32`。这个结果不是坏消息，而是一个更诚实的结论：之前污染链路不能当证据；clean 链路下 Qwen embedding 暂时没有稳定收益，但也不能因为一次 run 就盖棺定论。

`qwen3.7-max` + clean Milvus + Qwen embedding diagnostic ：diagnostic `21/32`，是 clean Qwen 链路的首个完整数据点。它高于 DeepSeek 的 `17/32`，但看失败结构会发现，提升主要来自 Qwen 让 query_plan / plan_validation 类失败消失了（5→0、2→0），`schema_context` 反而从 5 升到 7，仍是最大失败簇——也就是说 **这部分差距主要来自模型本身，不是 Qwen embedding 的功劳，schema 上下文修复依然是下一步优先级**。

所以这个实验的结论不是“Qwen embedding 已经解决 schema retrieval”，而是：**Qwen LLM 能改善规划失败，但 schema 上下文问题仍要单独修**。这也是后来新增 retrieval-only benchmark 的原因：先把 embedding 检索能力从完整 Text2SQL 链路里拆出来看，再决定下一步修 fusion / rerank。

**Retrieval-only embedding benchmark：**M20 收尾后又补了一组更干净的小实验：不让 LLM 写 SQL，只让 schema retrieval 对 10 条专门设计的问题召回表、字段、指标和关系。这样可以单独看 Milvus + embedding 有没有能力，而不是被 SQL 生成、query plan、result_match 一起搅在分数里。

结果：默认 deterministic embedding 的 `vector-only recall=0.787`，Milvus + Qwen embedding 的 `vector-only recall=0.929`，说明 Qwen embedding 对 schema 语义检索确实更强；但两者 merged recall 都是 `0.738`，说明当前短板不在 Milvus 写入或 embedding 模型本身，而更像在 keyword/vector 融合、排序和 rerank 策略。换句话说，embedding “有信号”，只是现有合并策略没有把这个信号转成最终上下文收益。

### 补课：Milvus + embedding 链路原理

M20 一直在用"embedding 模型" "Milvus collection" "向量检索"这些词。如果对这些概念只有模糊印象，这里补一课，把整条链路从"一段文字"到"生成 SQL"串起来讲清楚。

**第一步：embedding —— 把文字翻译成"坐标"。**

电脑看不懂"退款率""GMV"这些词的含义，但它擅长算数。embedding 模型（比如 Qwen embedding）就是个翻译官：把一段文字翻译成一串数字（叫**向量**），相当于在 N 维空间里给这句话一个坐标点——向量有几个数字就是几维，比如项目默认本地路径是 128 维，真实 embedding 模型通常是几百上千维。

这个翻译有个关键性质：**语义相近的文本，坐标距离就近**。"退款"和"退货"意思接近，坐标就挨得近；"退款"和"发货"就离得远。于是"比较两段文字像不像"就变成了"算两个坐标点的余弦相似度"，一个纯数学问题，模型能力再强也是靠这个坐标决定检索结果。

★ 项目里还有个**默认本地路径**（`deterministic` embedding）：它不做真神经网络，只是按 token 和中文 bigram 拼出一个可重复的向量。虽然"翻译质量"不如真实模型，但完全离线、可复现，所以 pytest 和本地诊断都走它；M20/M21 实验的 Qwen embedding 走的是 DashScope 在线 API。

**第二步：向量检索 —— 找坐标最近的 top-k 条。**

有了"文字 → 坐标"的能力，检索就从"看字面"升级成"看语义"。用户问"哪个渠道卖得最好"，先把问题翻译成查询向量，再和每条 schema 文档的向量算**相似度**，按分数从高到低取**前 k 条（top_k）**。这解决了关键词匹配的硬伤：关键词只有"字面包含"才命中，换个说法就漏（比如问"成交额"匹配不到"GMV"）；向量检索能跨说法命中语义相同的文档。

**第三步：Milvus —— 专门存"坐标"的数据库。**

那 193 条 schema 文档的向量存在 Milvus。可以把它类比成一张特殊的 MySQL 表（collection）：

| MySQL 表       | Milvus collection            |
| -------------- | ---------------------------- |
| 一行是一条记录 | 一行是一个文档向量           |
| 主键           | doc_id（VARCHAR 主键）       |
| 字段值         | vector（FLOAT_VECTOR，N 维） |

查询时执行一次 `search(collection, query_vector, limit=top_k)`，Milvus 用 COSINE 索引（AUTOINDEX）快速返回"离查询向量最近的 k 行"。为什么不用 Python 手动全量算一遍余弦？数据量一大就慢；Milvus 内部用 ANN（近似最近邻）索引，"先粗筛、再精排"把速度提上去，代价只是一点点精度。这也解释了 M20 为什么死磕维度一致性：向量长度不同根本没法算距离，所以 collection 的维度必须和当前 embedding 模型严格对齐。

**第四步：整条链路串起来，全流程分两段:**

1. **灌库**（实验/启动时做一次）

   domain schema（表 / 字段 / 指标 / 关系）

     → 组装成 193 条 schema docs（document_builder）

     → embedding 模型逐条**翻译成向量**

     → insert 进 Milvus collection + flush（此时才有数据可搜）

     → 顺手算 schema_docs_hash 打版本指纹

2. **召回**（每次提问时做）

   例如用户问题"哪个渠道卖得最好"

     → 用同一个 embedding 模型翻译成**查询向量**

     → Milvus search 召回 top-k 条最相关的 schema docs（**语义路**）

     → keyword 关键词路也同步召回一份（**字面路**）

     → **两路按 weighted 融合排序**，取最终 top-k

     → 拼进 LLM prompt → LLM 生成 SQL

为什么要"先检索再生成"，而不是把所有 schema docs 全塞给 LLM？193 条全塞进去 token 太长、噪声太大还费钱；挑最相关的 k 条，相当于给 LLM"按需翻书"，只递给它当前问题相关的几页。

**这和 M20 修的东西有什么关系？**

一句话：**这条链路里，Milvus collection 是"坐标仓库"，仓库脏了，召回就乱。** M20 发现的污染，就是同一批 193 条文档被反复 insert，仓库里攒了约 1.9 万行重复数据——查询时一堆重复坐标干扰相似度排序，embedding A/B 的分数就不可信了。所以 M20 给仓库装护栏：检查 row_count 是不是 193、维度对不对，脏了直接报错，改用唯一 collection 重建；再靠 `schema_docs_hash` 让每份报告都能追溯"这次搜的是哪版坐标"。仓库干净了，后面 M21 的 weighted / RRF 融合实验才有说服力。

> ⚠️ 注（M22 后更新）：文中"193 条"是 M20 时的 schema docs 数量。M22 新增 `coupon_order_count` 指标后，schema docs 变为 **194 条**；后续检索 / 融合实验都基于新 corpus，分数与 M21 的 `21/32` 不再直接可比。

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

## ★ M21 weighted VS RRF / 本地 vs embedding

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

### 补课：fusion 原理

接 M20 补课里的那张"召回"流程图：每次提问，keyword 路和 vector 路**各排出自己的一份候选名单**。fusion（融合）回答一个问题——**这两份名单怎么合并成最终的一份 top-k**，决定到底把哪几条 schema 文档塞给 LLM。

**问题：两路分数不可比。**

keyword 分是**字面命中计数**：问题切词后逐词去文档里找，命中一个加 0.2~2 分（词越长越高），表名 / 列名 / 指标名精确命中再各 +2，分数 0~几十；vector 分是**余弦相似度**：问题和文档各被翻译成坐标，算两个坐标的夹角余弦 `cos = (A·B) / (|A| × |B|)`，只关心方向一不一致，范围固定 -1~1（通常 0 ~ 1）。一个是"数量"（出现几个词），一个是"比例"（方向多像），量纲完全不同，直接相加不公平——就像把考试成绩（0~100）和体温（36~37）加起来。

**策略一：weighted —— 比总分（默认）。**

keyword 分 × 1.2 + vector 分，按总和排序。思路是"相信两路分数的绝对值，加起来比"。1.2 是给字面命中一点倾斜（更信任精确匹配）。这是 M9 以来的老行为，M21 保留它当默认基线。

**策略二：RRF —— 比名次（实验）。**

完全不看分数大小，只看**名次**：某条文档在名单里排第 r 名，就投 `1/(60+r)` 票。分母加常数 60 是为了把票数压在一个平滑的小范围，避免第一名垄断投票。

| | weighted | RRF |
|---|---|---|
| 比什么 | 两路分数的**绝对值相加** | 两路名次**各投一票** |
| 最大优点 | 沿用旧行为，稳定可解释 | 绕开"分数不可比"的难题 |
| 典型后果 | 某一路分数特别高也能进 | 两路都命中的文档天然靠前，带进更多文档 |

RRF 的隐藏副作用：因为"两路都上榜"的文档能拿两份票，它更容易把 relation / metric 等不同类型的文档带进 top-k——这既是它离线 recall 大胜的原因，也是端到端翻车的伏笔（见下）。

**结果：离线大胜，端到端翻车。**

- 离线 retrieval-only：merged recall `0.738 → 0.929`，relation recall `0.633 → 0.967`，全面碾压；
- 端到端同配置 diagnostic：`21/32 → 18/32`（同模型复测 `20/32`），反而下降，新增失败集中在 plan_validation。

**为什么"召回变好"却没换来"端到端变好"？**

recall 只问"该召回的召回了没"，RRF 把更多文档塞进上下文，这个指标自然好看；但**上下文更全 ≠ 对 LLM 更好**——prompt 变长、文档变多，LLM 的 QueryPlan 选择会被改变，反而更容易选错关系路径，卡在 plan validation。就像地图信息更全了，司机反而看花眼选错路。

所以 M21 的核心教训是：**离线检索指标和端到端能力是两层东西，必须分别验证**；不能因为离线分数漂亮就切默认策略。

> ★ 安全底线：RRF 排序只允许用"问题 + 候选文档的分数/名次"，**绝不允许**用 benchmark 的 expected 表/字段标签参与排序——否则就像考试时把答案塞给判卷人，分数虚高，真实用户请求里根本没有这些信息（标签泄漏）。

**结论。**

RRF 被记录为**否定实验**：保持默认 weighted，不改 top_k、schema docs 或评测口径。fusion 只是排序层，真正瓶颈在 schema_context / 输出契约，交给 M22 处理。

> ⚠️ 注（M22 后更新）：M22 确实按新口径处理了这块——拆出 Context / Output / Result / Manual 契约评分，默认 diagnostic `25/32`（新 case + scorer + 194-doc），是"新口径快照"而非对 `21/32` 的提分；默认 **weighted 未切换**，本节结论仍有效。M23 若再研究 RRF / rerank，需在 194-doc 新基线上重做单变量 A/B，不能复用 M21 的总分结论。

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

## ★ ★ M22 评测契约与 QueryPlan 输出稳定性

（2026-08-04）

**简述**：M22 先把“Agent 做错了”和“评测题判错了”分开，再用 QueryPlan 合同防止排序等已规划要求在 SQL 生成时悄悄丢失。

### 先用大白话讲

以前系统有一种“冤案”。

我们想检查的是：“模型写 SQL 前，有没有拿到正确的表和字段？”
但旧评测看的却是：“最后返回的结果里，有没有出现这些字段？”

这就像检查学生有没有看懂题目，老师却只盯着最后答题卡上写了什么。学生做题时可能确实查过资料、用了中间变量，但最终答案本来就不需要把所有过程写出来。于是，系统明明拿到了正确的 Schema，却可能被误判成“检索没召回”。

M22 做的第一件事，就是把这几件事拆开看：

- Context：模型写 SQL 前，实际拿到了哪些表和字段；
- Output：最终 SQL 返回了哪些列；
- Result：返回的数据值、排序和条数对不对；
- Manual：太复杂、暂时不能稳定自动判分的题，明确交给人工复核。

同时，系统遇到“查供应商”“知识库文档带来多少订单金额”“先查两个指标再比较”这类当前能力做不了的问题，不再硬让模型猜一个 SQL，也不再把网络报错伪装成业务结论，而是诚实地说明：当前为什么做不了。

一句话：M22 不是单纯让分数变高，而是先把“模型真做错了”和“尺子量错了”分开。

### 这次做了什么

我们把现有题目、参考 SQL、固定 seed 数据和评分规则放在一起检查，确认数据库本身没有坏、参考 SQL 也能正常运行；但发现有些题目、指标定义和评分规则没有完全说同一种业务语言。例如：

- 商品退款率原来可能把退款算到订单的“主商品”上，不能准确处理一单多商品；
- 优惠券“使用订单数”和“优惠券使用率”被混成了一个概念；
- “一级类目”有时绕过正式类目树，直接使用旧的兼容字段；
- 系统原来把最终 SQL 的输出列，当成模型检索到的上下文证据；
- 有些真正的 SQL 问题也被发现了，比如计划里要求排序，生成 SQL 时却漏掉排序；查历史价格时，时间范围没有按价格生效区间正确重叠。

针对这些问题，M22 做了四类修复：

1. 统一题目、指标和参考答案的业务口径：退款率按订单明细归因，一级类目走正式类目树，优惠券订单数有独立指标名。
2. 重做评分分工：上下文、最终输出、结果值和人工诊断分开评分，避免一个地方出错被误判成另一个地方的问题。
3. 给系统补上“诚实拒绝”的能力：没有供应商字段、知识库和订单没有归因关系、当前不支持多步比较时，返回结构化原因，而不是胡乱生成 SQL。
4. 给 QueryPlan 和 SQL 加了一条检查线：计划里已经明确要求的排序、条数限制，SQL 不能悄悄丢掉；如果丢了，trace 会保留计划和实际 SQL 的证据，方便定位。

**实验补测结果：**

| 组   | 配置                                                         |  首轮 | 第2次 | 第3次 | 平均通过率 |
| ---- | ------------------------------------------------------------ | ----: | ----: | ----: | ---------- |
| C0   | `deepseek-v4-flash` + Milvus + `qwen3.7-text-embedding` + weighted | 24/32 | 24/32 | 25/32 | 76.0%      |
| C1   | `qwen3.7-plus` + inmemory/deterministic + weighted           | 27/32 | 28/32 | 28/32 | 86.5%      |
| C2   | `qwen3.7-plus` + Milvus + `qwen3.7-text-embedding` + weighted | 25/32 | 27/32 | 25/32 | 80.2%      |
| C3   | `qwen3.7-plus` + Milvus + `qwen3.7-text-embedding` + RRF     | 24/32 | 26/32 | 27/32 | 80.2%      |
|      | `qwen3.8-max` + inmemory/deterministic + weighted            | 22/32 |       |       | 68.8%      |
|      | `qwen3.7-max` + inmemory/deterministic + weighted            | 26/32 |       |       | 81.3%      |

### 新概念

- **Contract（契约）**：像 Java DTO/接口约定，先明确“这一层必须交付什么证据”。Context Contract 看内部 SchemaGraph，Output Contract 看 SELECT 返回列，Result Contract 看结果值和顺序，不能混用。
- **Semantic rejection（语义拒绝）**：不是权限安全拦截，也不是模型超时；它表示“当前产品能力没有可靠的业务关系或字段支撑”，并且把原因写进 trace。

### 代码阅读路线

1. **评测证据分流**：`eval/scorers/rule_scorers.py` 与 `eval/run_eval.py`。先看 trace 如何只作为 scorer 私有证据，再看专属 contract 为何优先于最终列检查。
2. **能力边界与 SQL 合同**：`engine/nl2sql/semantic_validation.py`、`engine/nl2sql/pipeline.py`、`engine/nl2sql/generator.py`。理解语义拒绝、SQL Guard、QueryPlan contract 三者各守哪一道门。
3. **业务事实源**：`domain_pack/metrics.yaml` 与 `eval/cases/`。对照商品退款率、优惠券订单数、类目树的 case 改动，理解“题面—指标—reference SQL”必须说同一种业务语言。

### 设计要点

- **先改尺子再量分数**：M22 不把口径校正包装成模型能力提升。
- **窄合同而非泛化 SQL 解析**：只验证计划中已经声明的排序/limit，不用正则替代 SQL AST 或重写合法 SQL。
- **M22 实验期间默认策略不动**：实验固定使用声明的模型、检索链路、weighted、Milvus 选择与 seed；M22 收口后，用户另行确认将默认主模型切换为 Qwen `qwen3.7-plus`。

### 面试怎么讲

“我在做 Text2SQL 评测时发现，低分不一定全是模型或检索的问题：有些 case 把内部检索上下文、SQL 输出列和最终结果混在一起评分，导致检索明明正确，仍被判失败。

所以我先做了一轮评测契约治理，把评测拆成 Context、Output、Result 和 Manual 四层：Context 直接读取同一次请求 trace 里的 SchemaGraph，Output 检查 SQL 返回列，Result 用确定性 SQL 对照结果，复杂语义题则明确进入人工复核。

同时我统一了退款率、优惠券订单数和一级类目等业务口径，并补了两类工程护栏：一类是 semantic rejection，遇到当前 Schema 根本不支持的需求时结构化拒绝；另一类是 QueryPlan 到 SQL 的合同检查，防止计划里已经声明的排序或 limit 在 SQL 生成时丢失。

最终我没有把口径调整包装成模型提分，而是把它记录为新的评测合同。这样后续无论优化 retrieval、prompt 还是模型，都能更准确地区分：到底是模型生成问题、检索问题，还是评测本身的问题。”

1. **[压力追问] 你把 case 和 scorer 都改了，25/32 有什么意义？**

它不表示模型从 21/32 提升到 25/32。M22 同时改变了 case、scorer 和 schema docs corpus，所以我把它记录为新口径诊断快照，并在报告中单列自动、人工和契约重分类。复审后又明确了“成交订单”的取消订单排除口径，因此 `25/32` 也不能直接充当修复后的严格 C0；真正可比的 retrieval 实验要先刷新一次默认 C0，再在 194-doc、新 case/scorer、同模型条件下重新做。

### 验证与下一步

- 验证：复审后 M22 专属 `14 passed, 1 warning`，相关回归 `64 passed, 1 warning`，全量 pytest `147 passed, 2 skipped, 1 warning`；`25/32` 是修复前 C0 快照，尚未重跑真实 LLM diagnostic。
- 下一步：M22 的 C0-C3 重复和 Qwen `qwen3.8-max` / `qwen3.7-max` 追加对照已完成；正式收工后，下一模块优先检查 SQL Contract 的别名/等价表达误拦，再区分 QueryPlan→SQL 生成缺口与 Schema Retrieval 缺口。M23 若研究 retrieval / rerank，要从 194-doc 基线重新做单变量 A/B，不能复用 M21 的总分结论。

## ★ M23：把题目和数据校准

### 先用大白话讲

之前看到一条 SQL 答错，第一反应很容易是：“模型不行”“检索没找到表”。

但这次发现，问题也可能出在更前面的地方：

- 参考答案本身没把真实业务规则写完整；
- 数据库里故意放了取消订单、整单退款、负数退款、错误单号等真实企业常见情况；
- 一道题虽然写了参考 SQL，却可能没有真正用结果来评分；
- 向量库里的文档数量一样，不代表文档内容还是同一版。

如果这些基础没校准，后面再怎么换模型、换 embedding、调 RRF，分数也不一定可信。

M23 做的事，就是先把“考卷、标准答案、数据口径、评分规则”整理好。这样以后模型通过，才是真的通过；模型失败，也更容易知道它到底错在理解、关联、SQL，还是业务口径。

### 这次做了什么

1. 统一了关键业务口径。

   商品退款率不再只统计有订单明细的退款。正常明细退款优先按 `order_item_id` 归因；整单退款没有明细时，回退到 `refunds.product_id`，不能因为 `INNER JOIN` 被静默丢掉。

   订单量统一使用 `COUNT(DISTINCT orders.id)`，避免订单和明细、退款、优惠券表关联后被重复计数。

2. 把参考答案真正变成自动评分依据。

   formal 和 challenge 中能确定答案的 SQL 题，都改为结果集或固定数值校验。参考 SQL 不再只是给人看的说明，而是会实际执行、和模型结果对比。

3. 建立异常数据专项评测。

   数据库里的“彩蛋”不是都该过滤掉：

   - 未支付、取消订单：成交指标应排除；
   - 一单多券：订单数应去重；
   - 整单退款：应保留并按规则归因；
   - 负数退款：代表冲销，金额必须保留负号；
   - 订单头金额和明细金额不一致：应该被查出来，而不是偷偷改平；
   - `SRC-*` 单号和 `ORD-*` 单号：不能拿来直接关联。

   新增了三道专项题：已完成退款的带符号净金额、退款按内部外键关联渠道、订单头与明细金额对账。再加上已有题，专项共 6 条自动题和 1 条人工归因素材。

4. 修复 Milvus 复用漏洞。

   以前只要 collection 行数相同，就可能复用旧向量。现在 collection 会保存 Schema 文档内容 hash；文档内容变了，即使还是同样多条，也必须新建或显式重建索引。

### 这次最重要的收获

评测不是“拿几个问题跑一下模型”。

一个可信的 AI 评测，至少要同时保证：

- 题目问得清楚；
- 业务口径有唯一答案；
- 参考答案真的参与评分；
- 数据异常有明确处理原则；
- 实验使用的是同一版语料和索引；
- 分数变化能说清楚是哪里变了。

否则，分数看起来在涨，实际上可能只是标准答案、数据范围或索引版本变了。

### 面试怎么讲

我在项目里做过一次 Text2SQL 评测基线治理。

一开始我发现，模型评测失败不一定是模型或 pipeline 的问题，也可能是参考 SQL 没真正参与判分、业务指标口径不一致，或者数据库里的真实异常数据没有被覆盖。

所以我先把退款率、订单去重和整单退款归因这些语义收口；再把可自动比较的参考 SQL 改成结果集校验；随后针对取消订单、桥接表重复计数、负数退款冲销、错误外部单号关联、订单头明细不一致等场景建立异常专项评测。

另外，我发现 Milvus 以前只按行数判断能否复用 collection，文档内容变了但数量没变时会误用旧向量。我把 Schema 文档 hash 写入 collection 元数据，复用前强制校验内容版本。

这次工作的核心不是提升某一次分数，而是让后续模型、检索和 prompt 的实验建立在可信、可复现的基线上。
