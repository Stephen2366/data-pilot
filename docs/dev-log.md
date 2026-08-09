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

M20 主要解决 **Milvus 索引被重复写入，导致 embedding 实验结果不可信**的问题。最终清理了实验链路，并把 embedding、向量库和完整 Text2SQL 的效果拆开验证。

1. **先确认旧实验为什么不可信**

   M19 复测时发现，当前只有 193 条 Schema 文档，但固定 Milvus collection 中却有约 1.9 万行数据。原因是每次评测都会重复插入同一批向量。

   在这种情况下，旧实验分数无法准确反映 embedding 效果，因此不能继续拿来比较模型。

2. **给 Milvus collection 增加复用护栏**

   `MilvusVectorIndex` 不再每次启动都直接插入数据，而是先检查 collection 的**行数和向量维度**：

   - 数据一致就直接复用；
   - 行数或维度不一致就拒绝运行；
   - 实验需要重建时，使用新的 collection 或显式 reset。

   这样避免旧数据污染后续实验。

3. **让一次评测只构建一次向量索引**

   以前 32 条 diagnostic case 可能反复创建和写入索引。现在 eval 启动时预建一个 shared vector index，再由整轮请求共同使用。

   报告也新增了 collection、row count、Schema 文档 hash、向量维度和 oracle backend 等信息，让每次实验都能确认自己使用了哪一版数据。

4. **重新运行干净的端到端评测**

   clean collection smoke 确认最终只有 `193` 行。

   在干净链路下：

   - DeepSeek + Qwen embedding：`17/32`
   - Qwen `qwen3.7-max` + Qwen embedding：`21/32`

   进一步查看失败结构后发现，Qwen 的优势主要来自 QueryPlan 和 plan validation 失败减少，不能直接算作 embedding 的贡献。

5. **把 embedding 单独拿出来测试**

   为了避免 LLM 规划和 SQL 生成干扰判断，又新增了 retrieval-only benchmark，只检查 Schema 表、字段、指标和关系能否被召回。

   结果显示：

   - deterministic vector recall：`0.787`
   - Qwen embedding vector recall：`0.929`
   - 两者最终 merged recall：都是 `0.738`

   这说明 **Qwen embedding 本身有更强的语义召回能力，但现有融合排序没有把这部分优势转化成最终上下文收益**。因此没有切换默认 embedding，而是把后续重点转向 fusion 和 rerank。

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

M21 主要研究 **Qwen embedding 已经召回了更好的 Schema 信息，为什么最终 Text2SQL 仍没有明显提升**。为此新增 RRF 融合，并通过离线召回和端到端评测分别验证效果。

1. **给 Schema Retrieval 增加 RRF 融合**

   原来的 weighted 策略直接合并关键词分数和向量相似度，但两种分数的范围并不完全一致。

   M21 新增了显式 `rrf` 策略，只根据每条结果在关键词路和向量路中的排名进行融合。默认仍保持 `weighted`，只有实验时才显式开启 RRF。

   CLI、请求参数、Trace 和 Eval 报告都会记录当前 fusion strategy，保证实验可以复现。

2. **先看 RRF 能不能改善离线召回**

   在 retrieval-only benchmark 中：

   - deterministic merged recall：`0.738 → 0.802`
   - Milvus + Qwen embedding merged recall：`0.738 → 0.929`
   - metric recall：`0.600 → 0.900`
   - relation recall：`0.633 → 0.967`

   这说明 RRF 确实能把 Qwen embedding 已经召回的信息排到更合适的位置。

3. **再检查离线提升能否转化成端到端收益**

   固定 Qwen `qwen3.7-plus`、同一 clean Milvus collection、同一 embedding、同一批 case 和同一 oracle，只改变 fusion：

   - weighted：`21/32`
   - RRF：`20/32`

   RRF 虽然减少了一条 Schema Context 失败，却增加了 QueryPlan 和 Result Match 失败。因此，**离线召回提高并没有稳定转化成最终 SQL 能力**，默认策略继续使用 weighted。

4. **重新检查“Schema Context 失败”的真实含义**

   逐 case 查看 retrieval、SchemaGraph、QueryPlan 和最终 SQL 后发现，不少旧的 `schema_context` 失败并不是目标表没有被召回，而是 SQL 最终漏用了表、字段或输出列。

   因此 triage 新增了 `output_table_contract` 和 `output_column_contract` 等细分类，避免把 SQL 生成问题误判成 embedding 问题。

5. **直接对比本地检索和 Qwen embedding**

   固定 Qwen `qwen3.7-plus`、weighted、同一批 32 条 diagnostic，只改变 Schema Retrieval：

   - 本地 deterministic：`21/32`
   - clean Milvus + Qwen embedding：`21/32`

   两组总分和主要失败分布基本一致。这次实验没有证明 embedding 能带来端到端提分，但明确了后续方向：**先处理输出合同和 QueryPlan→SQL 稳定性，不再继续盲目调整 embedding 与 fusion 参数。**

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

M22 主要解决 **评测失败归因混乱、业务口径不一致，以及 QueryPlan 中的信息在生成 SQL 时丢失**的问题。最终把 Context、输出、结果和人工诊断拆开评分，并补上结构化拒绝与初步 SQL 保真检查。

1. **先把题目、业务指标和参考 SQL 放在一起核对**

   检查后发现，一些题目虽然能运行，但业务含义并不完全一致：

   - 商品退款率没有准确处理一单多商品；
   - 优惠券订单数和优惠券使用率被混为一个指标；
   - 一级类目有时绕过正式类目树；
   - 历史价格查询没有正确处理价格生效区间；
   - QueryPlan 要求的排序或 LIMIT 可能在生成 SQL 时丢失。

   这些问题会让模型即使理解正确，也可能被错误参考答案或评分规则判错。

2. **统一业务口径和参考答案**

   商品退款率改为按订单明细归因；一级类目统一走正式类目树；优惠券使用订单数增加独立指标定义。

   同时重新检查相关 reference SQL，确保题目、指标说明和标准答案表达的是同一个业务规则。

3. **把不同层次的失败拆开评分**

   评测不再用最终 SQL 的输出结果反推检索是否成功，而是分成：

   - **Context**：目标表和字段有没有进入 SchemaGraph；
   - **Output**：最终 SQL 是否使用了要求的表和列；
   - **Result**：执行结果是否符合 reference SQL；
   - **Manual**：当前无法稳定自动判断的复杂语义题。

   这样可以分清问题到底出在检索、计划、SQL 生成还是结果语义。

4. **增加结构化拒绝**

   对当前数据模型无法回答的问题，例如缺少供应商字段、知识库无法归因订单，或者需要多步查询但 pipeline 暂不支持，系统会返回明确的拒绝原因，而不是强行编造 SQL。

5. **增加 QueryPlan→SQL 初步合同**

   如果 QueryPlan 已经声明 `ORDER BY` 或 `LIMIT`，生成 SQL 不能静默丢弃。

   合同失败时，Trace 会保存计划内容、候选 SQL和实际观察结果，方便区分真正的信息丢失与检查器误判。这也为 M24 的 AST 语义保真合同提供了直接问题证据。

6. **用重复实验重新判断默认路线**

   | 组   | 配置                                                         |  首轮 | 第2次 | 第3次 | 平均通过率 |
   | ---- | ------------------------------------------------------------ | ----: | ----: | ----: | ---------- |
   | C0   | `deepseek-v4-flash` + Milvus + `qwen3.7-text-embedding` + weighted | 24/32 | 24/32 | 25/32 | 76.0%      |
   | C1   | `qwen3.7-plus` + inmemory/deterministic + weighted           | 27/32 | 28/32 | 28/32 | 86.5%      |
   | C2   | `qwen3.7-plus` + Milvus + `qwen3.7-text-embedding` + weighted | 25/32 | 27/32 | 25/32 | 80.2%      |
   | C3   | `qwen3.7-plus` + Milvus + `qwen3.7-text-embedding` + RRF     | 24/32 | 26/32 | 27/32 | 80.2%      |
   |      | `qwen3.8-max` + inmemory/deterministic + weighted            | 22/32 |       |       | 68.8%      |
   |      | `qwen3.7-max` + inmemory/deterministic + weighted            | 26/32 |       |       | 81.3%      |

   M22 不是单纯提高分数，而是让后续失败能够被正确归因，并暴露出下一步最需要解决的 **SQL 合同误拦和 QueryPlan→SQL 信息保真问题**。

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

M23 主要解决 **评测标准答案** 与 **真实数据库业务规则** 之间 **没有完全对齐** 的问题。最终统一了退款、订单去重等核心口径，把 reference SQL 真正接入自动评分，并补上异常数据专项和 Milvus 文档版本校验。

1. **统一退款率和订单量口径**

   商品退款率不再只统计带 `order_item_id` 的退款：

   - 明细退款优先按 `order_item_id` 归因；
   - 整单退款没有明细时，回退到 `refunds.product_id`；
   - 成交指标排除未支付和取消订单。

   订单量统一使用 `COUNT(DISTINCT orders.id)`，避免订单关联明细、优惠券或退款后被重复计数。

2. **让参考 SQL 真正参与自动评分**

   以前部分 case 虽然写了 reference SQL，但评分时只检查关键词、表名或输出字段。

   M23 将能确定答案的 formal 和 challenge SQL case 改为：

   - `result_match`：实际执行 reference SQL 并比较结果集；
   - `expected_value`：比较明确的固定数值。

   这样 reference SQL 不再只是给人看的说明，而是真正决定 case 是否通过。

3. **建立数据库异常专项评测**

   项目 seed 中包含一些企业数据常见异常：

   - 未支付和取消订单；
   - 一单多券导致重复计数；
   - 没有订单明细的整单退款；
   - 表示冲销的负数退款；
   - 订单头金额与明细金额不一致；
   - `SRC-*` 与 `ORD-*` 两种不能直接关联的单号。

   M23 新增了带符号净退款金额、内部外键关联渠道、订单头明细金额对账三道题，并与已有 case 组成 **6 条自动题 + 1 条人工题**的异常专项。

4. **修复 Milvus 同行数复用漏洞**

   之前 collection 只检查行数和向量维度。如果 Schema 文档内容改变但数量不变，系统仍可能错误复用旧向量。

   现在会把 **Schema 文档内容 hash** 写入 collection 元数据。复用时除了检查行数和维度，还必须检查 hash；内容发生变化时必须新建或显式重建索引。

5. **用双数据库验证参考答案**

   原有 20 条和新增 3 条 reference SQL 都在 deterministic SQLite 与当前 MySQL 上执行检查，确认 SQL 可以运行，并且两端结果行数一致。

   本地代码验证为：

   - focused：`42 passed`
   - 全仓 pytest：`152 passed, 1 warning`

### 面试怎么讲

我在 DataPilot 中做过一次 **Text2SQL 评测基线治理**。

当时我发现，SQL 评测失败不一定是模型或 Schema Retrieval 的问题，也可能是**业务口径、参考 SQL、评分规则和数据库真实数据没有对齐**。例如商品退款率只统计明细退款，会漏掉整单退款；订单关联明细、优惠券或退款表后，如果直接 `COUNT(*)`，又会把同一订单重复计算。

因此，我先统一了核心业务口径：商品退款按“**明细优先、整单退款回退商品**”归因，订单量统一使用 `COUNT(DISTINCT orders.id)`，成交指标排除未支付和取消订单。随后把 formal 和 challenge 中可以确定答案的 SQL case 改为真正执行 reference SQL，并通过 `result_match` 或 `expected_value` 比较结果，而不是只检查表名、列名或关键词。

我还针对数据库中的真实异常建立了专项评测，覆盖**取消订单、一单多券、整单退款、负数退款冲销、错误外部单号关联和订单头明细金额不一致**。相关 reference SQL 同时在 deterministic SQLite 和 MySQL 上执行，确认标准答案本身可以运行且口径一致。

另外，我发现 Milvus 以前只按行数和向量维度判断 collection 能否复用。如果 Schema 文档内容变化但数量不变，就可能继续使用旧向量。因此我把 **Schema 文档 hash** 写入 collection 元数据，复用前同时校验行数、维度和内容版本。

M23 的价值不是把某次评测分数做高，而是让后续实验建立在一个**业务口径明确、标准答案可执行、异常数据有覆盖、向量索引可追溯**的基线上。这样模型失败时，才能进一步判断问题究竟出在检索、QueryPlan、SQL 生成，还是业务语义。

1. **[基础追问] 为什么 Text2SQL 评测不能只比较生成 SQL 和参考 SQL 的字符串？**

   同一个查询可以有多种正确写法，例如使用不同表别名、CTE 或等价聚合表达式。字符串不同，不代表结果错误。

   M23 对能自动判断的 case 执行 reference SQL，再比较列和结果集；复杂语义题则保留人工复核，避免用脆弱的字符串规则代替业务正确性。

2. **[工程/深挖追问] 为什么 reference SQL 还要同时在 SQLite 和 MySQL 上验证？**

   SQLite 是本地 eval 使用的确定性 oracle，MySQL 是项目真实运行数据库。如果只验证一端，可能出现 reference SQL 在评测环境通过、到真实数据库却因方言或数据行为不同而失败。

   双端验证的目标不是要求所有生成 SQL都同时兼容两种方言，而是确认**标准答案和固定业务事实本身可信**。

3. **[压力追问] 你修改了业务口径、case 和 scorer，后面的分数还能和以前比较吗？**

   不能直接比较，这也是我在文档中明确保留的边界。

   M23 改变了业务定义、参考 SQL、自动判分方式和 Schema 文档 corpus，因此它建立的是一条**新评测基线**，不是对旧分数的直接提升。旧结果只保留为历史证据；后续模型、embedding 和 fusion 实验必须在 M23 新合同下重新运行，才能进行公平比较。

## ★ ★ M24：让 SQL 真正履行 QueryPlan

（2026-08-06）

**简述**：用 **SQLGlot AST 语义保真合同**替换容易误判的字符串检查，确保 LLM 生成的 SQL 忠实保留 QueryPlan 中的**排序、LIMIT、输出投影和展示顺序**，同时通过受控 A/B 验证规则边界。

### 先用大白话讲

QueryPlan 像一张已经审核过的“点菜单”：要查哪些列、按什么排序、取前几条，都已经写清楚。LLM 生成的 SQL 则像厨房最后端出来的菜。

M24 之前，系统主要用字符串包含关系检查两者是否一致。这会产生两种麻烦：

- 同一个意思换了写法，例如 `channels.channel_name` 写成 `c.channel_name`，如果前面有 `channels AS c`，两者实际是同一个意思，系统可能误以为错了；
- 真正重要的信息，例如 QueryPlan 明明要求 `DESC`、排序先后顺序、`LIMIT 10` 或输出列，却可能在生成 SQL 时丢失。这种情况不能因为 SQL 可以执行就放行。

M24 把检查器升级成了 **AST 语义保真合同**。它先把 SQL 解析成语法树，再比较“表达式实际指向什么”，而不是比较文字长得像不像。

同时，最终 API 返回的列也必须和计划约定的集合、别名和展示顺序一致。

一句话概括：以前检查的是字面像不像，现在检查的是 SQL 有没有忠实执行计划。

### 这次做了什么

M24 主要解决一个问题：**QueryPlan 已经写对了，但生成的 SQL 不一定照着执行。**

例如，计划要求“按订单量降序，取前 10 条”，SQL 可能丢掉排序、写反方向，或者忘记 `LIMIT 10`。旧检查又只会比较字符串，导致 `channels.channel_name` 和表别名 `c.channel_name` 这种实际相同的写法也可能被误拦。

这次按下面的顺序完成了改造：

1. **先重新检查历史失败**

   逐条查看 M22、M23 的 QueryPlan、候选 SQL、执行结果和 trace，把失败分清楚：

   - SQL 语义正确，只是写法不同；
   - SQL 真的丢了排序或 LIMIT；
   - 输出列多了、少了或顺序不对；
   - QueryPlan 或 SQL 本身生成错误；
   - 历史证据不足，暂时无法判断。

   这样避免把所有失败都错误归因给模型或 embedding。

2. **把字符串检查改成 SQL 结构检查**

   新增独立的 SQL 保真检查模块 `fidelity module`，使用 SQLGlot 把 SQL 解析成 AST，再比较实际含义。

   现在可以正确识别这些等价写法：

   - 原表名和表别名；
   - 普通字段名和带反引号的字段名；
   - 单表查询中 `table.column` 和 `column`；
   - 聚合表达式和它在同一 SELECT 中的输出别名。

   同时仍会拦截真正的问题：

   - 排序方向不一致；
   - 多个排序字段的顺序被调换；
   - 缺少 `ORDER BY`；
   - `LIMIT` 丢失或数值不一致；
   - 输出列多了、少了或顺序变化。

3. **让 QueryPlan 明确说明聚合别名的含义**

   QueryPlan 新增 `output_expressions`。例如：

   ```
   {
     "output_columns": ["channel_name", "order_count"],
     "output_expressions": {
       "order_count": "COUNT(DISTINCT orders.id)"
     }
   }
   ```

   这样系统能够确认 `order_count` 到底代表什么，不能让候选 SQL 自己随便定义一个同名 alias，然后声称自己符合计划。

4. **检查数据库真正返回的列**

   SQL 执行后，pipeline 会继续检查数据库 driver 返回的 `columns`。最终采用的政策是：

   - 只能返回计划要求的列；
   - 不能添加辅助列或内部字段；
   - 允许的别名必须提前声明；
   - 返回列顺序必须与计划一致；
   - 敏感字段仍由 SQL Guard 单独拦截。

   这保证了 API 表格和图表拿到的列稳定一致。

5. **把失败原因分到正确的位置**

   输出列不匹配现在归为 `output_contract`，不再自动算成 Schema Retrieval 或 embedding 问题。

   判断检索是否失败，要看目标表和字段有没有进入 SchemaGraph；不能因为最终 SQL 没使用某张表，就反推 embedding 没有召回它。

6. **完成本地测试和真实评测**

   | 组                                                           | 总分三次      | 自动能力三次  | manual/diagnostic | Milvus 健康                                                  |
   | ------------------------------------------------------------ | ------------- | ------------- | ----------------- | ------------------------------------------------------------ |
   | `inmemory + deterministic`                                   | `24,24,25/32` | `21,21,22/27` | `3,3,3/5`         | 不适用                                                       |
   | clean Milvus collection + DashScope `qwen3.7-text-embedding`（1024 维） | `25,25,25/32` | `22,22,22/27` | `3,3,3/5`         | 三次 final row count=195；M1 insert=195，M2/M3 insert=0；hash/1024 维一致 |


### 补课：为什么 AST 比字符串更适合 SQL 合同

AST 是 **Abstract Syntax Tree（抽象语法树）**。它把 SQL 拆成 SELECT、列、函数、表、ORDER BY、LIMIT 等结构节点。

例如下面两段文字不同：

```sql
ORDER BY channels.channel_name ASC
ORDER BY c.channel_name
```

如果 `channels AS c`，两者的 AST 在做 alias 绑定后都指向同一物理列；没有显式 `DESC` 时，ASC 也是默认方向。因此它们可以被证明等价。

但 AST 不是魔法。`ORDER BY id` 在多表查询里可能同时指向多张表；跨 CTE 或 derived table 的字段还涉及不同 scope。M24 的原则是：**能唯一证明才通过，不能唯一证明就返回 indeterminate。** 这比“猜一个最可能的解释”更符合企业查询的安全要求。

### 新概念

- **AST（Abstract Syntax Tree，抽象语法树）**：把 SQL 从一段字符串拆成 SELECT、表、字段、函数、ORDER BY、LIMIT 等结构节点。可以类比 Java 编译器解析源码：`a + b` 不再只是五个字符，而是一个加法节点和两个变量节点。
- **Semantic fidelity（语义保真）**：生成物是否忠实保留计划中已经确定的语义约束。
- **Scope（作用域）**：一个 SELECT 内名字可以解析到哪些表、列和 alias 的边界。
- **Indeterminate（无法确定）**：不是通过，也不是已证明错误；表示现有规则无法安全证明，应保守阻断。
- **Projection contract（投影合同）**：SQL 最终输出哪些列、使用什么受允许的别名、以什么顺序展示。
- **Defense in depth（纵深防御）**：pipeline 先做 SQL policy 预检，SQL Tool 执行前再做一次 Guard；语义合同不能替代安全合同。

### 代码阅读路线

1. **从计划数据结构开始**：`engine/nl2sql/planner.py`

   先看 `QueryPlanStep` 中的 **`output_columns`** 和 **`output_expressions`**。前者定义最终 API 展示列的精确集合与顺序，后者定义聚合 alias 的可信表达式。然后看 `_check_output_bindings()`：它会拒绝空输出声明、绑定了不存在输出列的 alias，以及 ORDER BY 使用了聚合 alias 却没有表达式绑定的计划。这一层解决的是：**SQL 生成前，QueryPlan 自己是否足够明确、可验证。**

2. **阅读本模块的主角接口**：`engine/nl2sql/fidelity_contract.py`

   从 `evaluate_sql_plan_fidelity()` 开始。它接收 QueryPlanStep、candidate SQL、DomainSchema 和 dialect，返回 `SQLPlanFidelityResult`。建议按三个大步骤阅读：

   - **ORDER BY**：比较排序项数量、位置、规范化表达式和方向；
   - **LIMIT**：比较整数字面量限制；
   - **projection**：比较输出列的集合和展示顺序。

   接着看 `_scope_sources()`、`_normalize_expression()` 和 `_parse_plan_alias_bindings()`，理解表 alias、唯一字段和输出 alias 如何解析到可信表达式。`_projection_issues()` 使用 tuple 保留顺序，使用 Counter 区分“纯顺序变化”和“集合变化”。这里不应改成 set，因为 set 会丢失重复列和展示顺序。SQLGlot 的所有节点类型不需要死记，重点理解 **“能唯一证明才通过”** 的边界。

3. **看 SQL 生成层如何消费合同**：`engine/nl2sql/generator.py`

   主角是 `validate_sql_plan_contract()` 和 `SQLPlanContractError`。

   `validate_sql_plan_contract()` 把 deep module 的三态结果转换成当前 pipeline 已经使用的异常式控制流；这样旧 caller 不需要一次性重写。

   `SQLPlanContractError` 会根据结果区分：普通 fidelity failure / `indeterminate` / 纯 projection failure

   阅读重点是：**复杂比较只存在于 fidelity module，generator 只负责适配调用方式。**

4. **沿真实请求执行顺序阅读**：`engine/nl2sql/pipeline.py`

   从 `run_text2sql_pipeline()` 的 SQL generation 部分开始，按以下顺序阅读：

   `QueryPlan 已验证`
   → `生成候选 SQL`
   → `SQL policy 预检`
   → `validate_sql_plan_contract()`
   → `SQL Tool 执行`
   → `output_projection span`
   → `chart generation`

   重点看 fidelity 失败时如何写入：完整 QueryPlanStep、candidate SQL 与 hash、planned/observed order、planned/observed limit、planned/observed projection、reason code、evidence level。然后看执行后的 `output_contract`：它检查的是 **数据库 driver 实际返回的列**，不是再次猜测 SQL 文本。

5. **看 prompt 如何把合同传给 LLM**：`engine/nl2sql/prompt.py`

   先看 `build_query_plan_prompt()` 如何告诉规划模型：`output_columns` 是精确合同；不得添加辅助列；聚合 alias 必须写入 `output_expressions`。

   再看 `build_local_schema_sql_prompt()` 如何告诉 SQL 生成模型：排序项、方向和先后顺序不能丢；LIMIT 不能静默改写；SELECT 必须严格按计划输出；MySQL 是生成方言，SQLite 只是本地结果核对工具。

   这里解决的是**减少模型犯错**；真正的硬保证仍由后面的 AST contract 提供。

6. **看自动评测如何检查真实输出**：`eval/scorers/rule_scorers.py`

   主角是 `_score_result_match()`。它先读取 `body.columns`，用 `_canonicalize_column_aliases()` 处理 case 明示的同义 alias，然后严格比较 `expected_columns`。alias 白名单只解决“同义列名”，不会放宽：多列、少列、错列、顺序变化。投影通过后，才执行 reference SQL 并比较行值。这样失败原因不会全部压成模糊的 `result_mismatch`。

7. **看失败如何进入正确归因桶**：`eval/triage.py`

   M24 新增 **`output_contract` failure stage**。最终 table、column 或 projection 不匹配不再自动归到 `schema_retrieval` 或 `schema_context`。只有 trace 证明目标 Schema 没进入 Context，才能讨论 retrieval 问题。这里是 M24 很重要的评测治理：**最终 SQL 没使用某张表，不等于 embedding 没召回这张表。**

8. **最后用测试理解边界**：`tests/test_m24_sql_plan_fidelity.py`

   先看历史正例：表 alias；quoted identifier；唯一限定名省略；SELECT alias

   再看真实反例：；ASC/DESC 不一致；排序项顺序变化；缺 ORDER BY；LIMIT 不一致；projection missing/extra/reordered；候选 SQL alias 自证漏洞

   最后看 `indeterminate`：；derived scope；歧义字段；ordinal ORDER BY；非字面量或 offset LIMIT

   这些测试比直接读 SQLGlot API 更容易建立完整心智模型。

核心调用链：

```
POST /api/query`
→ `QueryPlan generation`
→ `validate_query_plan()`
→ `SQL generation`
→ `SQL policy precheck`
→ `evaluate_sql_plan_fidelity()`
→ `SQL Tool + second Guard`
→ `output_contract`
→ `AgentResponse.columns / rows / chart_spec`
→ `result_match scorer`
→ `failure triage
```

**模块闭环**：M10 建立 QueryPlan，M11 把计划接入 Text2SQL pipeline，M22/M23 校正评测和业务口径，M24 最终补上 **QueryPlan→SQL→API 输出**之间的可执行合同。至此，系统不仅会生成 SQL，还能解释 SQL 是否忠实履行了上游计划。

### 设计要点

- **使用 AST，而不是继续补字符串规则**：历史证据已经出现表 alias、反引号、限定名省略和 SELECT alias。继续堆正则会让规则互相影响，也无法可靠处理作用域。
- **合同只验证，不自动改写 SQL**：自动补 ORDER BY 或 LIMIT 会让验证器膨胀成 SQL 重写器，可能掩盖模型退化，也会扩大安全责任。当前选择阻断并保留证据。
- **安全检查先于语义合同**：危险 SQL 不应该为了收集 fidelity 信息而继续深度解析。SQL policy 先拦截，SQL Tool 执行前再检查一次。
- **QueryPlan alias 必须显式绑定**：候选 SQL 是被检查对象，不能同时担任解释计划的可信来源。`output_expressions` 把 alias 语义固定在计划侧。
- **精确投影包含展示顺序**：数据库行值可以按列名对齐，但 API 表格和 chart 输入依赖稳定顺序。允许任意 extra 会同时放过合理辅助列和大量无关列，因此没有采用。
- **保留 `indeterminate`，坚持 fail closed**：首版不支持的 SQL 结构不会被误标成通过。只有真实业务样本出现，并且补齐正反例后才扩展规则。
- **MySQL 与 SQLite 职责分离**：MySQL 是生成与 AST 解析合同；SQLite 是离线 deterministic result oracle。不要求同一 SQL 同时成为两种数据库方言的标准答案。
- **不把端到端总分直接解释为 embedding 能力**：三次 Milvus 自动分均高约一分，但它仍混入 LLM 计划和生成波动，因此保持默认 `inmemory + deterministic + weighted`。
- **当前风险**：合同能判断 SQL 是否忠实于 QueryPlan，却不能保证 QueryPlan 自己理解正确。六轮评测中部分额外投影正是计划先声明过宽，随后 SQL 忠实执行了错误计划。

### 面试怎么讲

我在 DataPilot 的 Text2SQL pipeline 中实现了一套 **QueryPlan→SQL 语义保真合同**。

原来的合同通过**字符串包含关系**检查 SQL 是否保留了计划中的 `ORDER BY` 和 `LIMIT`。但真实 Trace 表明，表别名、反引号、限定名省略和 SELECT alias 等等价写法会被误拦；与此同时，排序方向写反、`LIMIT` 丢失、输出列不一致等真实错误又必须严格阻断。

因此，我没有继续堆叠正则，而是先对 M22/M23 的历史失败进行**逐 case 定性**，再通过离线 spike 验证 AST 规则的适用边界。最终基于 SQLGlot 封装了独立的**保真检查模块**，统一返回 `passed / failed / indeterminate` 和结构化证据。

这套合同会逐项比较 `ORDER BY` 的表达式、方向和先后顺序，并精确检查 `LIMIT` 与输出投影。对于 derived scope、歧义字段、ordinal ORDER BY 等暂时无法可靠证明的情况，系统会返回 `indeterminate` 并**保守阻断**。为了防止候选 SQL 用**自己的 alias 定义“自证正确”**，我还为 QueryPlan 增加了 `output_expressions`，由计划侧显式声明聚合 alias 对应的可信表达式。

在执行链路上，我保持 **SQL Guard 先于语义合同**，并由 SQL Tool 在执行前再次检查安全；SQL 执行后，再核对数据库实际返回的列集合和展示顺序。同时，Eval 和 Triage 将输出合同失败从 Retrieval 归因中独立出来，避免仅凭最终 SQL 使用了哪些表，就错误推断 embedding 是否召回成功。

这项工作的价值不只是增加一个 SQL 检查器，而是打通了 **计划、生成、安全、执行、输出与评测**之间一致、可验证、可追踪的合同与证据链。

1. **[基础追问] 这个合同通过以后，为什么还不能说明答案一定正确？**

   **fidelity contract** 检查的是 **SQL 是否忠实于 QueryPlan**，不是 QueryPlan 是否正确理解了用户问题。

   如果 QueryPlan 本身把商品退款率的分母写错，SQL 完全照着执行，fidelity 仍然会通过。因此系统还需要 QueryPlan validation、SQL Guard、SQL execution、output contract 和 result scorer。

   **类比后端 DTO 校验**：请求格式合法，不表示业务逻辑一定正确。每层合同只负责自己的边界。

2. **[基础追问] 为什么需要 `passed / failed / indeterminate` 三种状态，布尔值不够吗？**

   `failed` 表示已经找到确定不一致，例如 DESC 变成 ASC、LIMIT 10 变成没有 LIMIT。

   `indeterminate` 表示当前规则无法唯一证明，例如多表查询里的无前缀 `id`、跨 derived scope 的 alias 或 `ORDER BY 1`。

   如果只有布尔值，就会被迫把“未知”混入“错误”或“通过”。安全场景下，更合理的做法是保留未知状态并 fail closed，同时用 reason code 指导后续扩展。

4. **[工程/深挖追问] 为什么不让 LLM judge 判断 QueryPlan 和 SQL 是否语义一致？**

   LLM judge 可以辅助复杂人工语义题，但不适合代替硬合同。

   ORDER BY、LIMIT 和投影是可以确定性判断的结构约束。AST 规则成本更低、结果可复现、reason code 稳定，也能在没有网络和模型额度时工作。

   LLM judge 还可能受 prompt、模型版本和随机波动影响。对安全和执行边界，确定性规则应优先。

5. **[工程/深挖追问] `output_expressions` 会不会增加 QueryPlan 生成难度，导致更多计划失败？**

   会，这是该设计的真实代价。

   但如果不要求显式绑定，候选 SQL 就能用自己的错误表达式解释 alias，合同失去可信根基。M24 只要求非物理聚合 alias 在被 ORDER BY 使用时提供绑定，普通物理字段不需要重复声明，已经尽量控制了负担。

   后续应该根据稳定失败优化 QueryPlan prompt 或结构化生成，而不是删除可信绑定。

6. **[工程/深挖追问] 为什么把输出列顺序也设成硬合同？SQL 结果按列名读取不就行了吗？**

   行值比较确实可以按列名对齐，但 DataPilot 的输出还会被 API 表格和 chart 消费。

   如果列顺序不稳定，同一个问题可能一轮返回“渠道、订单量”，下一轮返回“订单量、渠道”，前端表格和图表维度选择都会波动。

   因此 M24 把“行值语义”和“展示顺序”分开：行值按列名比较，`body.columns` 作为独立展示合同严格检查。

7. **[压力追问] 你做了这么复杂的 AST 合同，最终总分没有明显大涨，这是不是工程自嗨？**

   这个质疑有合理部分：M24 没有把端到端总分提升包装成主要成果，稳定失败仍然存在。

   但 M24 的目标不是直接提高模型能力，而是消除错误门禁和建立可信归因。六轮诊断证明历史 alias/限定名正例没有再被误拦，同时真实表达式错误、额外投影和结果语义失败仍能被区分。

   如果没有这层治理，后续换 prompt、模型或 embedding 时，分数变化仍会混入合同误拦，实验结论不可解释。

   下一阶段的价值点也更明确：不再继续扩 AST，而是针对 QueryPlan 过宽投影和真实生成错误逐 case 修复。

8. **[压力追问] 你现在不支持 CTE、子查询和 `ORDER BY 1`，那这套合同是不是只能处理玩具 SQL？**

   这是当前边界，不应该回避。

   M24 首版是根据历史失败证据设计的，目标是修复现有单步 Text2SQL pipeline 中已经出现的问题，而不是一次性实现通用 SQL 等价证明器。

   CTE 和 derived scope 会引入跨 scope lineage，`ORDER BY 1` 依赖 SELECT 位置，扩展后需要新的可信正反例和作用域测试。当前返回 `indeterminate` 并保守阻断，比未经验证地放行更可靠。

   如果后续真实业务频繁出现这些结构，再扩展 scope lineage，而不是提前把模块做成一个难以验证的 SQL optimizer。

### 验证与下一步

- M24 focused：`70 passed, 1 warning`。
- 全仓 pytest：`176 passed, 1 warning`。
- 真实 diagnostic：Local `24/24/25`，Milvus `25/25/25`；自动分别为 `21/21/22` 与 `22/22/22`（分母 27），人工/诊断均为 `3/5`。
- 历史 alias/限定名正例六轮稳定通过，没有新的 semantic false block；稳定问题转为 QueryPlan 过宽投影、真实生成保真和结果语义错误。
- 下一步先执行 `accept-module` 验收。后续若继续优化，应针对稳定失败逐 case 修 QueryPlan/prompt；没有真实正反例前，不扩展 CTE/derived scope 等 AST 边界，也不切默认 embedding。

本地回归命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\m24-finish-full
```

读完可以试着回答：**如果 QueryPlan 写 `ORDER BY order_count DESC`，为什么合同不能直接使用候选 SQL 的 `COUNT(order_items.id) AS order_count` 来证明它正确？**

## ★ ★ M25 Eval Trustworthiness, Reliability & Evidence-Grounded Attribution

（2026-08-07）

**简述**：M25 没有继续靠调 Prompt 冲总分，而是让评测能区分 **试卷问题、代码问题、模型能力、检索缺失和外部服务故障**，并用真实 attempt 证据验证 retry 是否值得开启。

### 先用大白话讲

以前看到一题失败，报告往往只告诉我们“在 QueryPlan 阶段挂了”。但这像医院只记录“病人在急诊停下”，没有回答他为什么停下：可能是模型真的不会，也可能是网络 45 秒超时，甚至可能是试题没有写清排序和列，却拿隐藏答案扣分。

M25 给评测加了三张互不替代的标签：

- **execution stage** 说失败发生在哪里，
- **root cause** 说当前证据支持该修谁，
- **report view** 说这条证据应该进入哪一种分母。

外部 timeout 仍然算端到端失败，但语义状态是 **not observed**，不能包装成“模型答错”。

同时，M25 把 LLM 的一次逻辑调用拆成可观察的 physical attempts。每次 attempt 都有 provider、模型、timeout、延迟、错误 subtype 和 outcome；这样 retry 是否有效不再靠感觉。真实 4 题小样本显示：retry 从 0 调到 1 后，请求数和总时长约翻倍，却没有救回任何一题，所以默认继续保持 **45 秒、0 retry**。

### 这次做了什么

M25 主要解决的不是“怎样让模型多答对几题”，而是“怎样让评测结果值得相信”。

以前看到某个 case 失败，我们通常只能知道它停在 QueryPlan、SQL generation 或 result scorer，却不一定知道真正原因。模型可能确实不会，也可能只是网络超时；还可能是题目没写清楚，但参考答案偷偷要求特定排序、列或时间范围。如果这些情况混在一起，总分就很难指导后续优化。

这次主要完成了以下六项工作。

1. **先把评测试题和参考答案对齐**

   我们审计了 formal、challenge、diagnostic 三套评测中的 42 个 raw cases，逐项检查题目有没有明确说明：

   - 要查询哪些字段；使用哪个时间范围；应排除哪些业务状态；按什么顺序排序；是否限制返回条数；并列时如何决定先后；参考 SQL 使用的业务指标是否已经有权威定义。

   审计发现，一些题目只写了“前 10 条”“基本信息”或“一级类目销售额排名”，但参考 SQL 还**额外**要求了固定列、2026 年 6 月、特定排序等条件。这相当于考试题没有写要求，阅卷时却按隐藏要求扣分。M25 把这些隐藏条件补回了题目，使模型看到的要求与自动评分要求一致。

   同时，为这轮新题面和新业务口径登记了 **`case_contract_version=m25-v1`**。这样 M25 的新分数不会与 M24 的旧题面分数直接混算，也不会反向修改历史实验结论。

2. **把“检查次数”和“独立问题数”分开**

   42 个 case 并不等于 42 个独立问题。例如，同一个“2026 年 6 月 GMV”问题，可能分别有：

   - 一条 case 检查最终结果；
   - 一条 case 检查 QueryPlan；
   - 一条 case 检查 Trace 步骤是否完整。

   这些 case 检查的是同一个业务问题的不同侧面。如果直接把它们当成三个独立问题，总分就会重复放大某些问题的权重。

   因此 M25 新增了稳定的 **`semantic_group_id`**，把语义相同或等价的问题放进同一组：

   - 42 个 raw cases：表示实际执行了多少项检查；
   - 26 个 independent semantic groups：表示大约有多少个独立业务问题。

   这类似于数据库分析中必须同时区分“订单明细行数”和“去重订单数”：两者都是真实数字，但回答的问题不同。

3. **重新定义业务含义**

   原来的退款率只写成 `refund_count / order_count`，但没有明确：

   - requested、approved、rejected、completed 哪些状态算退款；
   - 一笔订单有多条退款记录时算几次；
   - 整单退款没有 `order_item_id` 时如何归属商品。

   M25 将商品退款率明确为：**已完成退款的去重订单数 ÷ 包含该商品的去重成交订单数**

   `avg_selling_price` 也明确为：取与查询时间范围相交的有效价格历史记录，对 `price` 按记录条数计算算术平均，而不是按有效天数加权，也不是成交均价。不过，题意写清不等于评分已经足够可靠。因此平均售价题仍保持 manual，没有直接升级成自动硬门。

4. **把“失败在哪里”和“为什么失败”拆成两套信息**

   M19 已经能通过 `failure_stage` 告诉我们失败发生在哪一步，例如：

   - `schema_retrieval`
   - `query_plan`
   - `plan_validation`
   - `sql_generation`
   - `result_match`

   但“失败发生在 QueryPlan”并不等于“模型不会做 QueryPlan”。如果 QueryPlan 请求等待 45 秒后超时，执行位置确实是 QueryPlan，真正原因却是外部服务没有按时返回。

   因此 M25 增加了第二条轴线——**root cause**：

   - `code_issue`：确定性的代码、状态传播、parser 或安全逻辑问题；
   - `model_capability`：provider 正常返回，但计划、SQL 或业务语义不符合已确认合同；
   - `retrieval_issue`：Trace 证明回答所需的表、字段、指标或关系没有进入 SchemaGraph；
   - `external_service`：timeout、网络、限流、欠费或外部服务不可用；
   - `eval_contract`：题面、reference、scorer 或业务口径不一致；
   - `mixed_or_unknown`：证据不足，或者多个因素混在一起。

   例如本轮 `db_multi_002`：

   - LLM 在约 31.68 秒后正常返回 QueryPlan；
   - SchemaGraph 已包含类目树、商品、订单明细、订单和 `item_gmv`；
   - 但 QueryPlan 虚构了不存在的 `root_category.level` 和 `root_category.name`。

   所以它的执行阶段是 `plan_validation`，当前根因是 `model_capability`，而不是 retrieval。

5. **把“模型答错”和“根本没观察到答案”分开**

   M25 又新增了 **semantic status**：

   - `observed_correct`：拿到了答案，并且确定性评分通过；
   - `observed_wrong`：拿到了答案，并且确定性证据证明它不符合合同；
   - `not_observed`：因为 timeout 或前置阻断，最终答案根本没有出现；
   - `not_applicable`：这条 case 本来就不负责检查最终语义答案。

   例如 QueryPlan timeout：

   - 在 end-to-end 视角下，它仍然是一次失败，因为用户没有拿到结果；
   - 在 provider reliability 视角下，它是 unavailable；
   - 在 semantic answer 视角下，它是 `not_observed`，不能算成“模型已经答错”。

   报告因此拆成六个视图：`semantic answer；safety；plan/trace；provider reliability；manual/Judge；end-to-end`。

   每个视图分别报告 eligible、observed、passed 和 unavailable，避免再把综合自动评测分数直接叫作“SQL 正确率”。

6. **记录每次 LLM 请求，并用真实实验判断 retry 是否值得开启**

   以前主模型超时时，Trace 往往只剩一句网络错误，缺少：

   - 使用了哪个 provider 和模型；
   - 配置的 timeout 是多少；
   - 实际请求了几次；
   - 每次等了多久；
   - 是否发生 retry；
   - 最终是成功、timeout、HTTP 错误还是解析失败。

   M25 新增了统一的 LLM 调用模块。每次逻辑调用都会记录完整的 **attempt evidence**，成功和失败使用同一种结构。

   随后用四条历史超时题做了一个小型受控实验，固定模型、检索、题目和 oracle，只改变 retry：

   - 45 秒、retry 0：发送 4 次实际请求，1/4 获得有效响应，总耗时 179.7 秒；
   - 45 秒、retry 1：发送 8 次实际请求，0/4 获得有效响应，总耗时 377.9 秒。

   retry=1 没有救回任何一题，却让调用次数和总耗时大约翻倍。因此本轮没有证据支持默认开启 retry，默认继续保持：

   - `LLM_TIMEOUT_SECONDS=45`
   - `LLM_MAX_RETRIES=0`

   这只是四题小样本，不能解释成 provider 的总体 SLA，也不能证明 retry 永远无效。它只支持一个保守结论：**当前没有足够证据值得让所有请求默认承担重试成本。**

7. **用反例证明业务 SQL 不能“碰巧答对”**

   为退款率和递归类目建立了最小反事实数据：

   - 退款率中，正确 SQL能区分一单多退款、非 completed 状态和整单退款；旧记录数口径会得到错误结果。
   - 递归类目中，正确 item grain 得到 70；漏掉子类目只得到 20；错误使用订单头金额会因一单多明细被重复累计成 200。

   这些反例证明了不同 SQL 的业务含义确实不同，而不是只看当前 seed 上是否碰巧返回同一个答案。

   对 recursive CTE，现有 SQL fidelity 仍然返回保守的 `indeterminate`。M25 没有为了让某一题通过，就临时把 AST 检查范围扩大成未经验证的通用 CTE 等价判断。

### 新概念

- **Execution stage vs root cause**：stage 像异常堆栈告诉你在哪一层抛错；root cause 像事故复盘告诉你为什么发生。`query_plan + timeout` 的 stage 是 query_plan，根因却是 external service。
- **Observed / unavailable**：`observed_wrong` 表示系统真的拿到答案并证明它错；`not_observed` 表示外部故障或前置阻断使答案根本没有出现。二者都可算端到端失败，但不能进入同一个模型能力分子。
- **Semantic group denominator**：一个问题可以同时有结果、Plan、Trace 三个 case。raw case 是检查次数，semantic group 才接近独立问题数，类似数据库里明细行数与 `COUNT(DISTINCT order_id)` 的区别。
- **Logical call / physical attempt**：一次业务调用可能因 retry 发送两次 HTTP 请求。成本和延迟必须按 physical attempt 统计，最终成功率则按 logical call 统计。
- **Counterfactual probe**：构造一小份能让正确 SQL 和常见错误 SQL 得出不同结果的数据。它像单元测试里的边界用例，防止错误 SQL 在单一 seed 上“碰巧答对”。

### 代码阅读路线

1. **先看调用可靠性 seam**：`engine/nl2sql/llm_call.py`

   从 `execute_llm_call()` 开始。它接收 client、prompt、stage 和策略，返回 `LLMCallResult`；重点看 `LLMAttemptEvidence` 与 `LLMCallEvidence` 如何避免保存敏感 prompt 正文。retry 分支只相信异常上的 `retryable`，不要先陷入 backoff 的小细节。

2. **再看 provider 如何分类错误**：`engine/nl2sql/generator.py`

   `OpenAICompatibleChatClient.complete()` 把 timeout、Arrearage、WinError 10013、429/5xx 和响应结构错误变成稳定 subtype；`_complete_with_evidence()` 把可靠性 module 接回 QueryPlan/SQL parser。这里的关键边界是 **transport 不负责业务解析**。

3. **看证据怎样进入一次请求的 Trace**：`engine/nl2sql/pipeline.py`

   QueryPlan 与 SQL generation 各自收集 request-local evidence。成功 span 和失败 span 使用同一种 `llm_call` metadata，所以报告不会只看见失败样本。

4. **看两轴归因与报告分母**：`eval/triage.py`

   先读 `triage_result()` 的最早硬失败规则，再读 `_root_cause()` 和 `_semantic_status()`；最后读 `analyze_eval_run()` 如何从相同 triage 构建六个视图。重点理解它深化了已有 module，没有再造第二套归因事实源。

5. **看 case 和 report 的入口**：`eval/run_eval.py`、`eval/cases/*.yaml`

   `EvalCase.semantic_group_id` 默认回退 case id，旧 case 不需要一次性迁移；`CASE_CONTRACT_VERSION="m25-v1"` 防止新旧合同混算。`write_report()` 只渲染 `analyze_eval_run()` 的结果。

6. **最后看业务反例**：`tests/test_m25_eval_trustworthiness.py`

   这里最值得复盘的是退款率和递归类目的内存 SQLite 反例，以及 retry/非 retry、external/model/retrieval/eval/code root cause 的正反例。

核心链路：

`EvalCase + semantic_group_id`
→ `pipeline QueryPlan / SQL generation`
→ `execute_llm_call + attempt evidence`
→ `TraceStep metadata`
→ `triage_result(stage + root cause + semantic status)`
→ `analyze_eval_run(report views)`

### 设计要点

- **不使用 stateful metadata**：显式返回 evidence，再用 request-local sink 写 Trace，避免复用 client 时把 A 请求的调用证据写到 B 请求。
- **retry 默认关闭**：只有 timeout、连接错误、429、5xx 等明确 transient 错误可重试；欠费、权限、普通 4xx、parse、合同和语义错误不重试。
- **历史分数冻结**：M25-v1 改了题面、退款率与分母，不能反向重算 M24 历史结果。
- **不扩大 AST scope**：recursive CTE 当前不能被安全证明时返回 indeterminate；能力反例与 result oracle 先证明业务差异，AST 扩展留给后续独立决策。
- **真实边界**：可靠性候选各只有一次 4-case run，足以否定本轮默认 retry，但不足以描述 provider 总体 SLA，也没有完整 M25-v1 baseline。

### 面试怎么讲

我在 DataPilot 的 M25 没继续通过调 Prompt 追总分，而是治理评测可信度。首先审计 42 个 raw cases，把隐藏的时间、列、排序和 LIMIT 写回题面，并用 semantic group 得到 26 个独立问题。然后把失败拆成 execution stage、root cause 和 semantic status：例如 QueryPlan timeout 仍算端到端失败，但属于 external service 且答案 not observed，不能算模型答错。工程上我做了一个 LLM call executor，成功和失败都记录 provider、模型、timeout、每次 attempt 延迟和稳定错误 subtype。最后用 4 条历史超时题做单变量实验，retry=1 把调用数从 4 增到 8、耗时从约 180 秒增到 378 秒，却没有恢复请求，因此默认保持 45 秒、0 retry。模块最终通过 184 个测试，且没有切模型、检索或 oracle。

1. **[基础追问] 为什么 raw case 数不能直接当独立问题数？**

   同一个自然语言问题可能分别检查结果、QueryPlan 和 Trace。如果把三条都当独立问题，某类能力会被重复加权。M25 保留 raw case 作为检查次数，同时用 stable semantic group 报独立问题数；这与订单明细行数和去重订单数必须分开统计是同一个道理。

2. **[工程/深挖追问] 你怎么保证 timeout 不被归因成模型能力不足？**

   不能靠错误文案猜。我在 transport 层生成稳定 subtype，并把每次 attempt 的 stage、timeout、latency、provider/model 和 outcome 写入 Trace。triage 先保留执行 stage，再依据 transport evidence 判 root cause；external failure 的 semantic status 固定为 not observed，但仍进入 end-to-end failure 和 provider unavailable。

3. **[工程/深挖追问] 为什么不默认 retry 一次，反正请求是幂等的？**

   幂等只说明不会产生重复副作用，不代表成本可接受。真实小实验中 retry=1 没救回任何一题，物理调用和总耗时约翻倍。并且 retry 还会放大额度、排队和尾延迟。所以默认策略必须看恢复率与成本，而不是只看“技术上能重试”。

4. **[压力追问] 4 条题各跑一次，就敢说 retry 没用吗？**

   不能说总体没用，这个质疑成立。我的结论严格限定为“本轮没有证据支持把 retry 切成默认”，不是 provider SLA。M24 六轮已显示部分题有稳定 45 秒 timeout，M25 本轮又观察到 retry 无恢复和成本翻倍；因此保持原默认是保守决策。如果要选择新 timeout 或 SLA，需要预注册候选并重复运行。

5. **[压力追问] 做了这么多评测工程，业务正确率还是没给出来，是不是绕开了真正问题？**

   M25 确实没有交付完整新基线，因为用户明确保留 formal/challenge/diagnostic 手动执行；我没有用 4 题小样本冒充业务正确率。但这不是回避：模块已经让后续基线能区分 external unavailable、observed semantic wrong、safety 和 plan/trace，并用退款率与递归反例固定了业务口径。完整运行完成后，分数才有可解释性。

### 验证与下一步

- 聚焦回归：**39 passed, 1 warning**。
- 全仓最终：**184 passed, 3 skipped, 1 warning**。
- seed reset：14 表固定规模与关键事实通过，新退款率口径下最高商品仍是 Aurora 耳机。
- warning 是既有 Starlette/httpx deprecation，不影响 M25。
- 下一步：用户手动运行 M25-v1 的完整 formal/challenge/diagnostic，再进行人工检查和 `accept-module`；若递归 CTE 需要扩大 fidelity scope，必须单独做设计决策。

可复制验证命令：

```powershell
# 聚焦门禁：预计 39 passed
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_m25_eval_trustworthiness.py tests\test_m24_sql_plan_fidelity.py tests\test_m19_failure_triage.py tests\test_phase3a_pipeline.py -q --basetemp=.agent_work\temp\pytest-m25-focused

# 全仓回归：本次结果 184 passed, 3 skipped
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.agent_work\temp\pytest-m25-full

# 4 条可靠性专项；实验时只在当前 shell 临时覆盖 timeout/retry
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --case-set eval\cases\m25-reliability-suite.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\m25-reliability-traces.jsonl --report .agent_work\temp\m25-reliability-report.md --triage-json .agent_work\temp\m25-reliability-triage.json
```

**本地启动体验：** M25 没有新增独立页面。可按既有 runbook 启动 FastAPI，在 Swagger 调 `/api/query`；本模块的新增价值主要从 JSONL trace 的 `llm_call`、triage JSON 的 `primary_root_cause/semantic_status` 和 Markdown 的 `M25 Evidence Views` 查看。

## ★ ★ M26 Diagnostic Human Audit / Eval Reconciliation

（2026-08-07）

M26 的目标不是再跑一次大模型、再看一个总分，而是先回答一个更基础的问题：**上一轮评测里显示的失败，哪些真是模型错了，哪些是评测和代码把正确路径误判了？**

### 先用大白话理解

一次评测报告像期末成绩单，但成绩单本身也可能有阅卷规则错误。M26 先把已经跑完的 M25 round2 冻结为审计输入，再让人工按同一份 trace、SQL、结果和 triage 证据逐项复核。这样后续修改不会把历史证据“洗白”，也不会因为重新调用不稳定的模型而得到另一份无法比较的答案。

审计结果是：32 条 raw case 实际对应 26 个独立语义问题；人工复核后有 26 条一致、1 条是假阳性、4 条是状态不一致、1 条证据不足。这里最有价值的不是“找到了几个 bug”，而是把每种不一致都连回可复现的代码和测试。

### 这次做了什么

这次先做一次 **评测结果审计（evaluation audit）**：确认 diagnostic 中每个“通过”或“失败”到底是否可信。否则很容易把 **评分器 bug、SQL Guard 误拦、网络超时** 错当成模型能力不足，后续优化方向就会跑偏。具体做了下面几件事：

1. **冻结并整理上一轮 diagnostic 的原始证据**

   我们没有重新调用 LLM，而是固定使用 M25 round2 已经产生的：

   - Trace：模型在哪一步执行、生成了什么 QueryPlan、是否生成 SQL；
   - 候选 SQL：模型实际给出的 SQL；
   - 执行结果与评分结果；
   - triage：原来系统对失败阶段和原因的判断。

   这样做的意义是：**先判断“当时这次运行发生了什么”，而不是重新跑一次后得到另一份受网络和模型波动影响的结果。**

   最终把 32 个检查项整理为 26 个独立业务问题，并为每一项保留可回看的审计记录。

2. **逐项检查上一轮生成 SQL 是否真的符合业务合同**

   这次确实检查了上一轮的 SQL，但检查方式是基于冻结的 SQL、执行结果和业务合同做审计，**不是重新执行全部候选 SQL 或重新生成 SQL**。

   最典型的是 `db_core_002`：自动评分显示它通过了，但审计发现候选 SQL 少了整单退款的归因回退：

   ```
   COALESCE(order_items.product_id, refunds.product_id)
   ```

   如果退款没有关联到具体订单明细，正确逻辑应回退使用 `refunds.product_id`。原 SQL 漏掉这部分，但现有 seed 数据恰好没有让它暴露错误，所以结果“碰巧正确”。

   因此这次新增了一个 **反事实测试**：专门构造能让正确 SQL 与错误 SQL 得到不同结果的数据。这样以后不会再因为当前数据太巧合，让错误 SQL 被自动判为正确。

3. **修复合法 CTE 被 SQL 安全层误拦的问题**

   递归 SQL 常用 CTE，例如：

   ```
   WITH RECURSIVE category_tree AS (...)
   ```

   `category_tree` 只是本次查询内部创建的临时名字，不是真实数据库表。旧 SQL Guard 没有区分两者，会把它也当成物理表做 RBAC 权限校验，导致合法递归查询被拒绝。

   现在改为按 SQL 的 **scope（作用域）** 判断：

   - CTE 临时名可以被后续 SQL 引用；
   - CTE 内真正访问的物理表仍做 RBAC 检查；
   - 即使经过 CTE，也不能读取 `users.email` 之类敏感字段。

   所以这不是“放宽安全规则”，而是让安全规则识别正确的 SQL 结构。

4. **修复 SQL Fidelity 对 `\* 1.0` 的误判，但严格控制范围**

   有些 SQL 会写成：

   ```
   refund_count * 1.0 / NULLIF(order_count, 0)
   ```

   这里的 `* 1.0` 通常只是为了避免整数除法，让结果保留小数；它不改变退款率的业务含义。但旧 Fidelity 会把它视为“SQL 与 QueryPlan 表达式不同”，从而阻断执行。

   这次没有实现宽松的“数学等价判断”，因为通用代数变形会碰到空值、类型、聚合粒度、Join 重复和数据库方言等风险。

   只增加了一个 **可证明安全的窄规则**：

   - 分母仍是相同的 `NULLIF(..., 0)`；
   - 分子不变；
   - 唯一变化只是额外乘以 `1.0`。

   只在满足这些条件时才视为等价；换分子、换分母、乘其他数字等情况仍然会被拒绝。

5. **让 SchemaGraph alternatives 和人工复核状态真正生效**

   评测 case 中原本已经可以写“满足方案 A 或方案 B 都算 SchemaGraph 正确”，但评分器没有真正使用这条规则，导致有些 Context 检查表面通过、实际没有验证到目标内容。

   现在评分器会从同一次请求的 SchemaGraph 中检查：

   - 找到了哪些表；
   - 找到了哪些字段；
   - 找到了哪些指标；
   - 是否完整满足任意一种允许的替代方案。

   同时，把两种以前容易混淆的状态拆开：

   - **`execution_failed`**：自动链路已经确定失败；
   - **`review_pending`**：缺少确定性 oracle，需要人工判断。

   例如模型超时、根本没有生成 SQL，不能叫“模型 SQL 答错”；它应是外部不可用或未观察到结果。`db_hard_003` 这种 SCD 时间边界题则仍是人工复核，不伪装成自动失败。

最终，这次工作把“上一轮的分数”拆成了更可信的事实：哪些是 **真实 SQL 语义错误**，哪些是 **代码或 scorer 的确定性缺陷**，哪些只是 **外部超时导致没有观察到结果**。这样下一次完整 diagnostic 跑出的 M26-v1 基线，才有可解释性。

模块完成后又补跑了 **两轮、四种模型/检索组合的完整 diagnostic**，共 256 次 raw case 执行；各组合都落在相近区间，现有证据不足以证明 Qwen Max 或 Milvus 有稳定优势。随后由 Codex 对第二轮 Qwen Plus 的 local / Milvus 两组各 32 条逐题审查，除了区分 **SQL 确实错误** 与 **超时导致无 SQL**，还发现 3 条自动通过但业务语义有误的 SQL，说明只看 runner 总分仍会漏掉 false positive。

复查也暴露了当前评测结构的历史包袱：formal、challenge、diagnostic 存在重复业务问题，manual、expected-block 和能力诊断题又混在同一总分里。后续建议改为 **一个业务场景只执行一次、多个 assertion 共享同一份 Trace**，suite 只负责选择场景，diagnostic 改为多维报告视图；这仍是待确认的下一步方向，M26 没有擅自改动现有 case 或正式口径。

### 新概念

- **Frozen audit evidence**：先把一次运行的输入、trace、报告和 triage 固定下来再复核。像财务审计先封存凭证，避免后续系统变化改变被审计的事实。
- **SQL scope**：CTE、子查询和外层查询各有自己的名字空间。判断一个标识符是不是物理表，不能只扫描全局名称，必须看它所在 scope。
- **Narrow semantic equivalence**：只接受能够用明确 AST 结构证明的一个小等价规则，而不是“看起来差不多就通过”。它宁可保守，也不把真实业务 SQL 改错放过去。
- **Execution failed vs review pending**：前者说明自动链路已确定失败，后者表示还没有足够证据下结论；两者都可能尚未通过，但不能混成一个失败原因。

### 代码阅读路线

1. 先看 `eval/audit.py` 和 `eval/run_audit.py`，理解冻结证据如何生成 audit record、如何写入人工 verdict，以及为什么 audit 不重跑模型。
2. 再看 `engine/sql_guard/policy.py` 的 `extract_sql_access()`，重点理解 sqlglot `Scope` 如何让 CTE 名称不冒充物理表。
3. 看 `engine/nl2sql/fidelity_contract.py` 的 ratio helper，观察“仅加 `* 1.0`”如何被限制为可证明的窄模式。
4. 看 `eval/scorers/rule_scorers.py`、`eval/triage.py` 与 `eval/run_eval.py`，理解 SchemaGraph alternatives、正交 triage 状态和报告如何共享同一份事实。
5. 最后读 `tests/test_m26_targeted_contracts.py`；其中 CTE/RBAC、ratio 正反例、SchemaGraph alternatives、triage 和退款率反事实覆盖了本模块最重要的边界。

### 设计要点

- **冻结审计证据不回写**：审计只消费同一轮 run 的 case / trace / report / triage，人工 verdict 不与正式 `passed`、LangFuse score 或历史报告混写。原因和财务审计封存凭证一样——先固定事实，再谈修复；否则每次系统变化都会悄悄改变被审计的结论。
- **窄等价宁可保守**：fidelity 只接受"同一分母 + 分子仅多乘 `* 1.0`"这一种可证明的类型提升。不做通用代数化简，因为 NULL、类型、聚合粒度、Join 重复和方言差异都可能在"看起来一样"的变形中被忽略。
- **schema_context 直接消费 SchemaGraph**：`expected_tables_alternatives` 由同请求的 tables / fields / metrics 判定，绝不拿最终输出列冒充上下文证据。这样"检索对了但 SQL 生成错了"保持为两条独立证据，也不会让最终响应反向篡改 Context 结论。
- **failed 兼容 + 正交状态**：保留旧 `failed` 字段供历史脚本使用，另加 `execution_failed`（自动链路已确定失败）与 `review_pending`（缺确定性 oracle，待人工），消除"待人工看"被误读成"执行失败"的歧义。
- **CTE 修复是名称解析修正，不是安全放宽**：只把 CTE 临时名从 RBAC 表集合中剔除，CTE 内部访问的物理表和敏感字段仍逐 scope 严格检查；安全边界是"修正识别，不降低约束"。

### 面试怎么讲

我在 DataPilot 的 M26 做的不是直接调 Prompt 或追求更高的 diagnostic 总分，而是先治理评测结果的可信度。M25 的 diagnostic 已经暴露出递归 SQL、退款率、SchemaGraph 和人工题状态上的异常，但“失败”不一定等于模型答错：它也可能来自 SQL Guard 误拦、评分器没有消费 case 合同、当前 seed 恰好掩盖错误 SQL，或者外部超时导致根本没有生成 SQL。

因此我先冻结上一轮的 trace、候选 SQL、执行结果、评分报告和 triage，避免重新调用 LLM 后被网络和模型波动干扰。32 个检查项归并为 26 个独立语义问题后，我发现了一次自动评分假阳性：退款率 SQL 漏掉整单退款的 `COALESCE(order_items.product_id, refunds.product_id)` 回退逻辑，却因为现有 seed 数据碰巧通过。随后我用 SQLite 反事实数据证明，缺少回退时会把正确答案从 `Beta, 1.0` 错算成 `Alpha, 0.0`。

修复时我刻意控制范围：SQL Guard 仅在 AST scope 内识别 CTE 临时名，真实物理表和敏感字段继续走 RBAC；SQL fidelity 仅接受相同分母和分子、只多出 `* 1.0` 的 ratio 类型提升；SchemaGraph scorer 开始真正消费 alternatives；自动执行失败与等待人工复核拆成正交状态。最终 focused 62 个、全仓 194 个测试通过。但我没有把这些确定性修复说成模型能力提升：M26 尚未跑新的完整 LLM diagnostic，新的 M26-v1 端到端基线仍需用固定配置独立建立。

1. **[基础追问] 你这个模块到底是在修模型、修 SQL 安全，还是修评测？为什么这些事情会放在同一个模块？**

   M26 的主目标是修 **评测归因的可信度**，但审计证明有些“评测失败”来自确定性代码边界，因此不能只改报告。比如递归 SQL 被拒绝时，表面上看是模型没有完成任务，实际是 SQL Guard 把 CTE 临时名误认为物理表；`schema_context_match` 表面通过，实际没有验证 alternatives。  

   所以这个模块不是把模型、安全和评测混在一起，而是沿着同一条证据链处理：**冻结运行证据 → 判断失败来源 → 只修已经证实的确定性缺陷 → 用测试证明边界没有被放宽**。模型是否真的进步，仍要由后续完整 diagnostic 回答。

2. **[工程/深挖追问] 你让 CTE alias 绕过了表级 RBAC。攻击者能不能把敏感表藏进 CTE，借此绕过权限检查？**

   不能，因为放行的不是 CTE 内的数据访问，而只是 **查询内部临时名字的引用**。例如 `category_tree` 是 CTE alias，不是数据库里的物理表；后续 `SELECT * FROM category_tree` 不应再把它当作一张真实表检查。  

   但 SQL Guard 会继续进入这个 CTE 对应的 scope，提取其中真正访问的物理表和字段。因此 CTE 内查询禁用表仍会被拦截，访问 `users.email` 这类敏感字段也仍会被拦截。M26 的回归测试同时覆盖了合法递归 CTE、CTE 内越权表、CTE 内敏感字段和 CTE 名遮蔽物理表四种情况。这里的安全边界是：**修正名称解析，不降低数据访问约束。**

3. **[工程/深挖追问] 你如何证明 `db_core_002` 是自动评分假阳性，而不是你主观认为那条 SQL “写得不够标准”？**

   我没有只根据 SQL 写法下结论，而是把业务合同变成了能区分正确与错误的反事实数据。合同规定商品退款率需要优先按订单明细归因，整单退款缺少 `order_item_id` 时再回退到 `refunds.product_id`。  

   原候选 SQL 缺少这个回退，在原 seed 上仍然通过 Top1 结果比较；但在新构造的最小 SQLite 数据里，正确 SQL 得到 `Beta, 1.0`，缺少回退的 SQL 得到 `Alpha, 0.0`。因此它不是“风格不同”，而是在存在整单退款时计算了错误的业务语义。  

   这也是 M26 的一个原则：**当现有数据无法区分两种 SQL 时，不能仅凭一次 result_match 就宣称它们业务等价。**

4. **[压力追问] 你的审计还要从历史 Markdown 报告里提取 Score Summary。既然源数据不完整，凭什么相信这次审计结论？**

   不能把这部分证据说得比它实际更强。历史 M25 run 没有单独保存逐 case 的结构化 `score_details`，因此 M26 的 legacy adapter 只读取冻结 Markdown 中已有的 Score Summary，并在审计记录里明确标注来源和报告 hash。  

   关键是它没有重新执行 scorer，也没有从别的 run 补数据；trace、候选 SQL、triage 和报告必须来自同一冻结运行，缺任何一项就失败。这样至少保证审计不把另一轮运行的证据拼进来。  

   这条限制也已经转化为后续改进项：新的 runner 应保存结构化 score artifact，让报告只是给人阅读的展示层，而不是审计时反向恢复事实的长期数据源。

### 验证与下一步

- 聚焦回归：**62 passed, 1 warning**。
- 全仓回归：**194 passed, 1 warning**。
- warning 为既有 Starlette/httpx deprecation，不影响 M26。
- 本模块未运行新的完整真实 LLM diagnostic，也没有切换模型、embedding、Milvus、LangFuse 或数据库默认值；因此不能把确定性修复表述为新的端到端能力基线。
- 下一步：用户人工查看 audit artifact 后执行 `accept-module`；若要得到 M26-v1 的新真实 LLM 基线，应另行授权完整运行。

可复制的审计命令（用于已保留的冻结输入）：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_audit --trace <frozen-trace.jsonl> --report <frozen-report.md> --triage <frozen-triage.json> --output-prefix eval\reports\m26-audit
```

**本地启动体验：** M26 没有新增 Web 页面。阅读 [审计 Markdown](eval/reports/m26-qwen37plus-local-round2-audit.md) 或运行上述 CLI 即可查看逐 case 证据；API 启动方式仍以 `docs/state/runbook.md` 为准。

## ★ ★ M27 Diagnostic / Eval Case 体系优化

（2026-08-09）

**简述**：把旧评测里“同一道业务题为了多检查几项就多调用几次模型”的结构，改成 **一题一次执行、多条断言共用同一份证据** 的 `m27-v1` 体系；确定性验证已完成，但 **尚未运行新的真实 LLM 基线**。

### 先用大白话讲

旧 diagnostic 像是让同一个学生为数学、语文和实验课分别重新答一遍同一道题：不仅浪费调用，还会因为每次 LLM 输出不同，让“这次 SQL 错了”与“这次 Trace 少了一步”混成两张不同答卷的结论。M27 改成一张答卷交给多位老师：**Result、SchemaContext、QueryPlan、Trace、安全和拒绝路径**分别评分，但都看同一次 API 执行、同一份 SQLite snapshot 和同一个 trace。

把它类比成你熟悉的后端接口测试会更直观：不能为了验证响应字段、数据库写入和日志各发一次 HTTP 请求；应该先完成**一次请求**，再围绕这次请求留下的事实写多条断言。M27 的价值正是让“模型这次答得怎样”先变成一份可追溯的答卷，再讨论不同维度的成绩。

### 这次做了什么

这一节的主线是：先把“题目是什么”和“怎样检查答案”拆开，再把一次运行留下的事实保存好，最后才计算不同视图的分母和 Gate。这样评测报告不再只是一个总分，而能回答：**哪道业务题出了问题、问题发生在哪一层、这次是否有足够证据下结论。**

- **先消除重复答题和“空检查”**：旧 formal、challenge、diagnostic 的 **42 条 raw case** 实际只有 **26 个旧语义组**，同一业务问题会因检查结果、计划或 Trace 而被重复调用模型。更危险的是，部分旧 check（例如 metric mapping、JoinPath、Plan、Trace）没有真实 scorer，会落入默认 `ok`。M27 先做 inventory 和迁移矩阵，再把它们整理成 **28 个 canonical Scenario**：这里的 Scenario 就是“一道唯一的业务题”，而不是“一种检查方法”。

- **让一次答题接受多项检查**：每个 Scenario 可以挂多个 **typed assertion**。assertion 可以理解为“有明确规则的判卷项”：例如六月 GMV 这道题，既可检查结果行，又可检查返回列、Schema Context、QueryPlan 和 Trace。`Evaluator.evaluate()` 保证同一个 `(run, scenario, replicate)` 最多调用一次 Pipeline；候选 SQL 和 reference SQL 也共用同一 SQLite snapshot。于是多个 scorer 是在检查**同一张答卷**，不会发生“结果来自第一次模型输出、计划来自第二次模型输出”的归因混乱。

- **把分数改成可解释的视图**：`EvalRun` 保存每次执行和 assertion 的结构化明细，`Projector` 再从明细计算 `eligible / observed / passed / failed / not_observed`。其中 `not_observed` 的意思不是答错，而是这次没有足够证据自动评分，例如外部服务不可用；Reliability 的多次 replicate 也会归约为一个逻辑 Scenario，不能靠重复请求扩大分母。Core、Stress、Manual Lab 说明题目职责；Smoke、Reliability、Database Exception 是“从题库选题”的 selector；Gate 则单独决定哪些 assertion 必须通过。

- **用反事实守住业务合同**：只在当前 seed 上对比结果，错误 SQL 可能碰巧通过。因此 SCD、退款率和递归分类都有最小 SQLite 反事实：缺少 `valid_to IS NULL`、把 rejected refund 算进分子、漏掉子类时，坏 SQL 必须得到不同结果。这证明的是 **case 合同和 scorer 能区分对错**，不是模型能力已经提升。

- **明确本模块没有做什么**：M27 保存的是脱敏的结构化 artifact（例如行数、fingerprint、Trace 摘要），不默认保存完整结果行、prompt 或凭证；旧 M26 报告也不重算。后续虽已获授权运行 Core，但它只是有限次数的真实快照，不能据此宣称模型稳定能力、成本优势或检索因果。

**后续补记**：M27 主体完成后，又围绕“人工怎么看结果”和“真实 Core 怎么读”做了三项小收口。

1. **补人工复查功能**：新增独立 review bundle，让 Codex/人工能查看脱敏 SQL、有限结果样本和 Trace 摘要；它只帮助解释自动结果，**不改 Gate 和分数**。

2. **吸收 M26 审查教训**：给复查材料加来源 SHA-256、错误分类，并规定普通题没有候选 SQL 时只能写“证据不足”，避免把外部调用失败误说成模型答错。

3. **运行两轮 Core 对照**：`qwen3.7-plus` 与充值后 `qwen3.7-max` 的本地/Milvus Core 都出现 **29 passed / 5 failed / 0 not_observed**；这说明当前稳定暴露的是同一批合同缺口，不足以证明 Milvus 或模型谁更好。

### 新概念

- **Scenario + assertion**：Scenario 是唯一业务问题；assertion 是对同一份执行证据的一个可裁决检查。可以把它类比成一次 SpringBoot 接口调用后的多层测试：业务返回、字段契约、日志和安全策略各自断言，但不会为了每条断言再发一次请求。
- **Snapshot oracle**：候选 SQL 与 reference SQL 在同一个数据库快照上执行。像单元测试里的同一事务，避免 scorer 各自重新 seed 数据导致“标准答案”和“实际答案”看见不同数据。
- **Projector**：结构化明细的只读视图。它类似 SQL 的聚合查询：Markdown 和 LangFuse payload 都消费同一个投影，不再让 Markdown 反过来成为评分事实源。

### 代码阅读路线

1. **先看合同**：`eval/contracts.py` 与 `eval/catalog.py` 定义 `m27-v1` Scenario、typed assertion、四类 hash 和严格 YAML loader；重点理解为什么未知 kind 会在执行前失败。
2. **再看执行闭环**：`eval/evaluator.py`、`eval/environment.py`、`eval/ports.py` 展示一次 Pipeline 调用、同 snapshot Oracle、checkpoint 与 interrupted/abandoned 边界如何协作。
3. **看怎么评分**：`eval/assertions.py` 和 `engine/nl2sql/pipeline.py`。后者把安全的 `plan_steps` 写入 trace，前者用它评分 Plan、Join 和 Metric，而不再默认通过。
4. **最后看消费层**：`eval/selectors.py`、`eval/projectors.py`、`eval/reporting.py` 和 `eval/run_eval.py`。这里能看到 selector 不复制题面、replicate 不扩大分母，以及 CLI 只把 gate 转成退出码。

核心调用链是：

`canonical scenarios.yaml`
→ `catalog / selector`
→ `Evaluator.evaluate()`
→ `RunEnvironment（API + 同 snapshot Oracle）`
→ `ExecutionEvidence`
→ `typed assertions`
→ `EvalRun artifact`
→ `projector`
→ `Markdown / LangFuse payload / CLI gate`

### 设计要点

- **新旧合同隔离**：旧 formal/challenge/diagnostic 报告仍是历史证据，不能被 M27 重新计分；新结果也不能与旧 `25/32`、`26/32` 直接比较。
- **安全 artifact 优先**：完成的 JSON 只保存 allowlist trace 摘要、行数和稳定 fingerprint，不保存完整 rows、prompt、answer 或凭证。代价是不能恢复原始业务行，换来清理 raw trace 后仍能核验评分身份且不泄露 PII。
- **不擅自改变运行默认值**：本模块没有切模型、检索、embedding、数据库、oracle、timeout 或 retry；真实 LLM 基线仍需要单独授权。

### 面试怎么讲

我把 DataPilot 的评测从“case 列表加总分”改成了更像工程测试平台的合同体系。先盘点发现 42 条 raw case 只有 26 个旧语义问题，同题被不同诊断维度重复调用，而且部分 Join/Plan/Trace check 实际会默认通过。于是我设计了 `Scenario + typed assertion + Evaluator`：每个业务问题只执行一次，结果、上下文、计划和安全断言共享同一份 trace 与数据库 snapshot；再用 versioned projector 推导分母和 gate。为了避免原 seed 掩盖 SQL 语义错误，我还为 SCD、退款和递归分类补了反事实 SQLite 测试。全仓 208 个测试通过，但我没有把它包装成模型能力提升，因为真实 M27 基线尚未运行。

1. **[基础追问] M27 为什么要把 Scenario 和 assertion 分开？这和普通测试用例有什么不同？**

   **Scenario** 表示一个唯一的业务问题，例如“六月各渠道 GMV 排名”；**assertion** 表示围绕同一答案要检查的某个维度，例如结果是否正确、输出列是否正确、计划是否真的用了 `channels -> orders` 的 Join。普通测试也可以有多个断言，但旧评测的数据结构把“一个 check”当成“一道题”，导致同一业务问题要重新调用多次模型。M27 把业务题与评分维度拆开，才能保证多条断言看到的是**同一张答卷**，也才能明确一个问题到底是 SQL 语义错、Context 不足，还是 Trace 证据缺失。

2. **[工程/深挖追问] 为什么不继续在旧 runner 上补几个 scorer？**

   因为旧 runner 的基本单位是单个 check，对同一业务题会重复调用模型；即使补齐 scorer，Result 和 Plan 也可能来自不同 LLM 输出，归因仍不可信。M27 把复杂性集中到 `Evaluator.evaluate()`，先固定“一题一次执行”的证据边界，再让多个纯 scorer 读取同一份 evidence。

3. **[压力追问] 你保存 hash 不保存完整结果行，出了争议怎么复核？**

   这个质疑成立：hash 不能替代原始业务数据。M27 的目标是长期、安全地保存可重算的自动评分身份和结构化差异，不是建设审计数据仓库；raw trace 仍可短期保留用于排障。若未来需要人工仲裁或长期保留完整 rows，应新建受控的权限、保留期和脱敏策略，而不是把敏感数据默认塞进 eval report。

### 验证与下一步

- 验证：M27 focused/counterfactual **`14 passed, 1 warning`**，证明一次调用、多断言、artifact、selector/gate 与 SCD/退款/递归反事实；legacy Eval 回归 **`37 passed, 1 warning`**，证明历史读取链未被破坏；pipeline 相关 **`21 passed, 1 warning`**，证明新增 QueryPlan trace 摘要没有回归；全仓 **`208 passed, 1 warning`**。warning 始终是既有 Starlette/httpx deprecation，不影响本模块结论。
- 下一步：先由用户人工检查，再运行 `accept-module`。如要建立 `m27-v1` 真实 LLM 基线，需要单独确认 selector、调用数、成本和运行窗口；新结果从零开始解释，不与 M26 历史单一总分做升降比较。

可复制的确定性验证命令：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q --basetemp=.codex/temp_work/pytest-m27-full
```

**本地启动体验：** M27 没有新增 Web 页面；它的入口是评测 CLI。先可无副作用查看新入口：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m eval.run_eval --help
```

你会看到 `--selector`、`--suite`、`--scenario`、`--replicate-count` 和 gate 相关参数。真实执行会调用当前配置的模型，因此在未获得新基线授权前，不要以“试一下”为由运行该 CLI；模型、检索与默认配置仍以 `docs/state/runbook.md` 为准。







