# Phase 2 Optimization Triage（阶段二优化机会分流）

> 背景：`docs/phase2-reference-review.md` 已补查 Phase 2 计划中提到的 reference，并整理出若干优化机会。本文回答一个更具体的问题：**阶段二刚完成、阶段三还没开始时，这些优化点应该现在实操，还是放入后续阶段？**

## 总结建议

**不建议现在把所有优化机会都实操。**

更稳的策略是：

1. **先跑 `accept-module` 验收 M6**：阶段二需要一个干净、可追溯的 baseline。否则优化改动混进 M6，会让“阶段二到底验收了什么”变模糊。
2. **验收通过后可安排一个很短的 Phase 2.5**：只做能降低阶段三风险、且不改公开 API 契约的大约 1-2 个优化。
3. **其余优化按 roadmap 放回阶段三 / 阶段四 / 阶段五**：不要把阶段四的 EvalOps 平台、阶段五的包装增强提前塞进阶段二尾巴。

我的推荐是：

- **现在只做决策和文档分流**：本文即完成这一步。
- **M6 accept 后，若有精力做 Phase 2.5**：优先做 **trace 决策粒度增强**，可选做 **Eval issue tag 最小化**。
- **阶段三开工第一件事**：先确认 **RAG 主路径和 `RetrievedDoc` 契约**，再写 RAG 代码。
- **完整 EvalOps scorer / report / checkpoint**：放到阶段四 AgentEvalOps 独立项目，不要现在做。

## 判断标准

本次分流按四个维度判断：

| 维度 | 含义 |
|---|---|
| **优先级** | 对阶段三成功、简历叙事、后续返工风险的影响 |
| **难度** | 预计改动复杂度：S 小、M 中、L 大 |
| **风险** | 是否会改变 API 契约、评测口径、SQL 行为、架构分层 |
| **roadmap 影响** | 会不会挤占阶段三 RAG / 混合推理、阶段四 AgentEvalOps、阶段五包装时间 |

## 总览表

| 优化点 | 建议去向 | 优先级 | 难度 | 风险 | Roadmap 影响 | 结论 |
|---|---|---:|---:|---:|---|---|
| trace 决策粒度增强 | Phase 2.5 可做 | 高 | M | 中 | 正向支撑阶段三 / 阶段四 | **推荐 M6 accept 后优先做** |
| Eval issue tag 最小化 | Phase 2.5 可选 | 中高 | S-M | 中 | 正向支撑阶段四，但不应扩大 | **可做最小版，不做平台版** |
| RAG `RetrievedDoc` 契约 | 阶段三开工前决策 | 高 | S-M | 高 | 直接影响阶段三架构 | **先设计确认，再实现** |
| 模板 SQL 命中解释 / 匹配优化 | 阶段三或阶段四前小修 | 中 | M | 中高 | 可能影响既有 SQL smoke | **暂缓，除非再被误命中阻塞** |
| SQL Guard blocked reason 细化 | 阶段三安全用例扩展时做 | 中 | S-M | 中 | 支撑安全评分与演示 | **随安全 eval 一起做** |
| Prompt builder schema 约束增强 | 阶段三前后均可 | 中 | S | 低中 | 降低 LLM 编造字段概率 | **可作为阶段三第一轮微调** |
| Streamlit 解释性信息增强 | 阶段三 RAG 后做 | 中 | S-M | 低 | 支撑演示，但不影响主链路 | **等 `docs_used` 有真实数据后做** |
| SQL Tool 预览 / CSV artifact | 阶段四或数据量变大后做 | 低中 | M | 中 | 暂不影响当前 seed / smoke | **暂缓** |
| 真实 token / cost 统计 | provider usage 可用后做 | 低中 | M | 中 | 支撑面试观测性，但非阶段三 P0 | **暂缓** |
| LangGraph 迁移 | 阶段三后半或阶段四后评估 | 中 | L | 高 | 可能拖慢 RAG 主线 | **不要现在做** |
| 完整 EvalOps scorer / checkpoint / HTML | 阶段四 AgentEvalOps | 高 | L | 高 | 这是独立项目主线 | **不要现在塞进 DataPilot** |

## 可现在做的范围

### A. 先做：M6 验收 baseline

**建议**：先调用 `accept-module` 完成 M6 验收。

原因：

- M6 已经 `finish-module`，且 `AI_CONTEXT.md` 当前状态仍是 **M6 未验收**。
- 如果现在直接改代码，M6 的验收对象会从“阶段二原始交付”变成“阶段二 + 临时优化混合物”。
- roadmap 需要一个清楚的里程碑：Phase 2 v1 到底在哪个点通过。

**影响**：不增加功能，但能让后续 Phase 2.5 / Phase 3 的变更边界更清楚。

### B. 可做：Phase 2.5 轻量硬化

Phase 2.5 不是新阶段，也不是功能扩张。它只应该服务两个目标：

- **减少阶段三 RAG / Hybrid 接入时的调试成本**；
- **让阶段四 AgentEvalOps 更容易接 DataPilot trace**。

建议最多做两个小任务：

1. **Trace 决策粒度增强**
   - 增加内部 trace step，例如 `template_match`、`llm_generation`、`sql_guard`、`sql_execution`、`chart_decision`。
   - 先写入 JSONL trace，不急着放进公开 `AgentResponse`。
   - 价值：阶段三混合链路一旦出错，可以快速判断是 router、SQL、RAG、guard 还是 answer 组合问题。

2. **Eval issue tag 最小化**
   - 在 M6 `eval/run_eval.py` 现有评分基础上，为失败原因加稳定标签。
   - 不拆完整 scorer 平台，不做 checkpoint，不做 HTML。
   - 价值：失败时从“failed: xxx”变成 `missing_table`、`safety_mismatch`、`answer_fragment_mismatch` 这类可聚合信号。

**不建议 Phase 2.5 做的事**：

- 不引入 SQLite eval result store；
- 不做 LLM-as-Judge；
- 不做完整 `eval/scorers/` 架构；
- 不改 API 响应字段含义；
- 不迁移 LangGraph；
- 不改 RAG 存储选型。

## 应放到阶段三的优化

### RAG 元数据契约

**优先级：高**  
**难度：S-M**  
**风险：高，因为会影响后续 RAG、Hybrid、Eval 和演示页。**

阶段三开始前必须先确认这些接口形状：

- `DocumentChunk`：原始文档如何切块、如何保存来源；
- `RetrievedDoc`：检索返回给 AgentResponse / eval / demo 的最小字段；
- `docs_used`：现在是预留字段，阶段三要决定它是 `list[str]` 还是结构化对象；
- eval 中的 `expected_docs` / `expected_sources`：RAG 用例怎么验收命中文档。

**建议**：阶段三第一个模块先写 RAG 契约和最小 ingest，而不是直接堆 retrieval 代码。

### Prompt builder schema 约束增强

**优先级：中**  
**难度：S**  
**风险：低中。**

可以借鉴 `askdata_agent` 的 prompt 约束，把这些规则写得更明确：

- 只能使用 schema context 中列出的表、字段、关系；
- 不得编造字段；
- 输出 SQL 不带 markdown fence；
- 当问题超出 schema 范围时返回可诊断错误。

这类优化可以放在阶段三早期，因为 RAG / Hybrid 会增加上下文，prompt 约束更重要。

### SQL Guard blocked reason 细化

**优先级：中**  
**难度：S-M**  
**风险：中。**

建议随着阶段三安全用例补齐一起做。原因是 blocked reason 会被：

- Eval 安全评分消费；
- demo 页面展示；
- dev-log / 面试讲法引用。

不要单独为了“文案更好看”改安全层；等安全用例扩展时一起收口。

## 应放到阶段四的优化

### 完整 EvalOps scorer 分层

**优先级：高**  
**难度：L**  
**风险：高。**

它很重要，但它属于 roadmap 中的 **AgentEvalOps 独立项目**，不应该塞回 DataPilot 阶段二尾巴。

阶段四再做更合适：

- `evalops/scorers/sql_result_scorer.py`
- `evalops/scorers/rag_citation_scorer.py`
- `evalops/scorers/safety_scorer.py`
- `evalops/reports/`
- SQLite run store
- version comparison
- HTML / Markdown 报告

DataPilot 现在只需要保留一个能跑 smoke 的轻量 eval 入口，作为未来 Adapter 的样例。

### SQL Tool result artifact

**优先级：低中**  
**难度：M**  
**风险：中。**

当结果集变大或评测需要对比完整 DataFrame 时，再考虑：

- `preview_rows` 与 `total_row_count` 分离；
- 大结果写 CSV；
- trace 记录 artifact path；
- eval 读取 artifact 做结果集比较。

当前 seed 数据量小，直接返回 rows 足够。

## 应放到阶段五或更后面的优化

### LangGraph 迁移

**优先级：中**  
**难度：L**  
**风险：高。**

LangGraph 对阶段三混合推理有价值，但不应在阶段二刚结束时为了“架构更像 reference”强行迁移。

建议触发条件：

- SQL / RAG / Hybrid 分支多到普通函数开始难读；
- trace 需要天然记录节点级状态；
- retry / fallback / conditional edge 明显增多；
- 当前 pipeline 的测试开始难写。

否则继续用普通 Python pipeline，保持主线速度。

### Streamlit 复杂交互

**优先级：低中**  
**难度：M**  
**风险：低中。**

阶段三完成 RAG 后，可以补：

- `docs_used` 展示；
- 查询历史；
- 复制 SQL；
- error_type / safety reason 面板；
- demo presets 分组。

但不要在现在扩 UI，因为它不会提高阶段三 RAG 主线完成概率。

### 真实 token / cost 统计

**优先级：低中**  
**难度：M**  
**风险：中。**

等 LLM provider 适配层能稳定拿到 usage 后再做。现在 M5 的 `CostInfo` 字段已经预留，足够支撑后续扩展。

## 推荐行动方案

### 方案 A：最稳，直接进入阶段三

步骤：

1. 运行 `accept-module` 验收 M6。
2. 保留 `docs/phase2-reference-review.md` 和本文作为阶段三输入。
3. 阶段三开工时先确认 RAG 主路径和 `RetrievedDoc` 契约。

**适合情况**：你想保持 roadmap 节奏，不想被优化项拖慢。

**我的评价**：最符合求职倒推。

### 方案 B：小做 Phase 2.5

步骤：

1. 运行 `accept-module` 验收 M6。
2. 用 0.5-1 天做 trace 决策粒度增强。
3. 还有余力，再用 0.5 天做 Eval issue tag 最小化。
4. 不做其它优化，马上进入阶段三。

**适合情况**：你希望阶段三 RAG / Hybrid 调试更顺，也想让阶段四 EvalOps 有更好的 trace 输入。

**我的评价**：可选，但必须限时。

### 方案 C：现在全面优化

内容：

- trace step；
- scorer 分层；
- template matching；
- SQL Guard reason；
- Streamlit 增强；
- LangGraph 迁移。

**我的评价**：不建议。它会把阶段二尾巴变成一个没有清晰验收边界的小泥潭，挤占阶段三 RAG 主线。

## 我的最终建议

选择 **方案 B 的克制版**：

1. **先 accept M6**，锁定阶段二 baseline。
2. 如果你愿意多花一点时间，做一个 **Phase 2.5：Trace + Eval 最小硬化**。
3. Phase 2.5 严格限时，最多两个任务：
   - trace 决策粒度增强；
   - Eval issue tag 最小化。
4. 然后进入阶段三，第一件事确认 **RAG 主路径 + `RetrievedDoc` 契约**。

这样安排的好处是：既不会浪费刚查完 reference 的收益，也不会让优化项吞掉 roadmap 主线。阶段二收得住，阶段三接得上，阶段四 AgentEvalOps 也有更好的输入。
