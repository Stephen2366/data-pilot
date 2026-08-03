# DataPilot Phase 3B Plan v6：引入 LangFuse 可观测性与评测基座

> 阶段三B：在保留当前 JSONL Trace + 规则评分主链路的前提下，优先使用 **LangFuse Cloud** 做最小接入验证，验证 trace 可视化、score 回写和手动 Experiment 是否适合作为后续 RAG/Hybrid 与独立 **EvalBench** 项目的可观测性基座。
>
> **核心目标**：在不改动 `/api/query` 响应契约、不替代 JSONL 和现有 eval 报告的前提下，新增可选 LangFuse Cloud 写入，并补齐 **L1/L2 规则评分器 + 最小 L3 LLM-as-Judge** 评分能力，最后跑通一次最小 Experiment 验证全链路闭环。LangFuse 自部署不再作为 DataPilot Phase 3B 的默认目标，改为 EvalBench 阶段重点探索。
>
> **v6 修订**：在 v5 Cloud 优先路线基础上，进一步收紧 **DataPilot trace_id 与 LangFuse trace_id 的边界**：LangFuse 不接管当前请求级 `trace_id`，只作为旁路观测系统写入并保存映射；同时把实施粒度从 6 个 step 收敛为 M15-M18 四个模块，避免 dev-log 和阶段复盘过碎。v6.2 追加 M19，把 LangFuse 从“上传本地记录”推进到“基于 trace/span/score 做失败归因、A/B 对比和改进闭环”。v6.3 追加 M20，处理 M19 后续 Qwen embedding / Milvus A/B 暴露出的 collection 重复灌入和索引可信度问题。v6.4 追加 M21，基于 clean Milvus 和 retrieval-only benchmark 结果，专门修 Schema Retrieval 的上下文融合与 rerank。

## 灵感来源：一线开发者的 LangFuse 评测实战经验

以下来自几位在业务系统中实际做 LangFuse trace-based evaluation 的开发者分享。他们在 RAG 和 Agent 评测中踩过的坑，直接影响了本计划的多项设计决策。当然，他们的方法也不一定完全正确，只是作为参考。

**A 的方案描述**：

> 我们是在业务系统埋点，然后基于 trace 评测，在langfuse触发experiment。一些指标调用外部大模型，比如 answer correctness、hallucination，还有一些rag的指标recall，mrr等等都是直接根据trace的埋点结果计算的。langfuse也有一些内置评估器可以直接用，需要自己配置外部模型。LangFuse 观测模块挺好的，评测模块内置的评估器比较少，自定义的指标需要自己写评估器，但是灵活度比较高。而且社区很活跃，项目一直在更新

**A 的踩坑实录**：

> 最近在做一些 RAG 和 agent 的评测工作。开始感觉评测就是上传数据集跑一下，看分数，结果做之后遇到各种乱七八糟的问题。 我们现在是用 Langfuse 记录 trace，再根据 trace 做评测。但实际跑起来之后，经常会遇到各种乱七八糟的问题。外部大模型做裁判，本身可能调用失败。 trace 还没上传完成，评测就已经开始了。好难找到合适的数据集。而且刚开始评测流程有问题，任务跑的巨慢。每次跑一晚上，回来发现又出错了。好像天天在忙 又没有成果。
>
> Agent eval中发现很多问题根本不是Agent的问题，而是评测本身的问题，就要一直改评估器。本意是想要通过评测发现Agent的问题，结果发现的都是我的评测的问题。踩过几个印象比较深的坑： 
>1. trace 还没上传完，评测已经开始了。trace 是异步上传的， 评测流程启动太快， 读到的 trace 还不完整，只能加等待和预获取缓存。而且还有个问题，业务系统里埋点的时候， 如果 trace id 没有连续往下传， retrieval、tool等步骤可能根本不在同一个 trace 里，需要手动获取trace向下传。
> 2. 外部llm做 judge，本身也不稳定。一些指标是直接让大模型打分，但跑起来之后发现会超时，或者需求过高，限制请求，又要加重试。其实我觉得指标打分不算复杂任务，是不是用本地部署的就可以了，但是领导觉得不够可信。 
>3. 在测 retrieval 的 recall的时候，很多开源数据集给的是参考文本， 和自己实际切片后的 chunk 并不完全一致。有时候 retrieval 召回了相关信息， 结果还是会被判 miss。后来引入了一个coverage的指标，将reference text按照句子拆分，计算recall text对reference的覆盖度。

**A 关于 LLM-as-Judge 的可信度**：

> 外部大模型做裁判，如何保证结果的可信度呢？特别是业务agent使用了专门的rag语料，或者是其他的上下文工程。这也是最近做评测感觉比较痛苦的，担心评测结果没有说服力。llm judge本身就会有偏差，只能当做一个参考吧，能通过评测发现系统问题更重要。目前我们这边llm judge是用在一些相对明确的指标上，比如答案正确性有参考答案，但同一个答案，不同模型打分也可能不一样。所以现在这么考虑的，在固定的benchmark、固定 judge模型、固定 prompt 的情况下，看系统优化后的相对变化。比如说改了检索方式之后，指标有没有提升。

**关于多轮跑分与测试集审核（A ↔ B 讨论）**：

> B：我也遇到测评的坑了，我想问一下一般测评会跑几轮？命中缓存Cache Collusion和答案泄露Leakage是怎么解决的？
>
> A：我现在是跑三轮，然后让大模型判断期望最高的答案。这个是算法说需要这么做。缓存和数据泄露还没考虑过，大模型本地部署，不联网，是不是不用考虑啊
>
> B：答案泄露不是数据，是测试prompt里面会无意间藏答案，需要审核测试集，llm太聪明了直接就能发现从而影响结果。缓存问题本地部署应该的确不用考虑。跑三轮ClaudeCode说发现不了差异，让我跑12轮。
>
> A：理解了，确实需要检查测试集。请问跑12轮是每一轮都进行评分再取平均值吗？还是选择期望最高的一轮评分啊？
>
> B：我是分两种情况，一种全跑完算完成率均值，一种是跑harness机制消融，每个机制要打分

**按能力维度设计评分策略（C 的经验）**：

> C：我设计了一个 sdk 便于部门内部的 agent 项目去收集运行 trace ，然后开发了一个评测平台，主要是针对 agent 不同的维度设计了 grade 策略层，比如 tool 调用能力， memory 检索能力，agent 安全等等，此外还有一些用例管理，回归管理等等，这些部门的设计基本和 anthropic 那篇博客一致。我目前觉得最大的难点在于， agent 不同能力维度都要单独设计评分方案，如果对中间过程评测又太严格，只基于结果进行 llm-as-judge 又太宽泛，让 llm 评测整个 trace 感觉是在套娃……我也是刚开始做没多久，目前还没有什么好的思路

**对本计划的影响**：

| 开发者经验 | 本计划对应措施 |
|----------|--------------|
| trace 异步上传 → 评测读到空数据 | M16：`LangFuseBackend.record()` 末尾 `flush()`，确保事件送达 API |
| | M17：Score 回写语义——优先直接按 `langfuse_trace_id` 写入；trace 查询只做 smoke/验证，允许 ingestion 延迟 |
| trace_id 没下传 → step 散落不同 trace | DataPilot 不受影响：所有 step 同在一个 `TraceRecord.trace_steps` 列表中；LangFuse 侧另存 `datapilot_trace_id` metadata 用于反查 |
| LLM judge 超时/限流/抖动 | M17：`timeout=30s` + `max_retries=3`，失败记 null 不阻断流程 |
| retrieval recall 的 chunk 粒度问题 | 后续衔接：Phase 3 RAG 预留 coverage 指标作为 L1 规则评分器 |
| "LangFuse 内置评估器可以直接用" | M17：先调研内置评估器，再决定复用/自研 |
| "rule 指标从 trace 埋点算，不用 LLM" | L1/L2/L3 分层框架：能用规则不用 LLM |
| Experiment 是评测闭环的关键环节 | M18：最小 Experiment 走通验证 |

## 前置状态（供新 AI 会话续接）

### 项目当前状态快照

| 维度 | 事实 |
|------|------|
| 当前阶段 | Phase 3A（M14-lite）刚收口，Phase 3 RAG/Hybrid 尚未开工 |
| 当前 trace 实现 | `engine/trace/recorder.py`：`TraceRecord` Pydantic 模型 → `append_trace()` 写 JSONL 到 `eval/traces/traces.jsonl` |
| trace 写入入口 | `app/api/query.py` 的 `_record_trace()` 函数，在 `_success_response()` / `_blocked_response()` 中调用 |
| trace 路径可覆盖 | 通过 `app.state.trace_path` 指向临时文件，测试/smoke/实验各自写入不同路径 |
| 当前评测体系 | `eval/run_eval.py`：YAML 用例 → 调 `/api/query` → 纯规则评分（contains/equals/expected_value）→ Markdown 报告 |
| A/B 实验 | `scripts/run_qwen_ab_experiments.py`：子进程运行 eval、解析 Markdown 报告 → 汇总表格 |
| 已有配置清理 | `.env` / `.env.example` 中的 LangSmith 配置已清理；`Settings` 中若仍有旧 LangSmith 字段，Phase 3B 实施时同步移除，避免与 LangFuse tracing 口径混淆 |
| LangFuse 配置现状 | `.env` 已手动写入 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL` 三项 Cloud 配置；文档和日志不得记录具体 key |
| LangFuse smoke 现状 | ✅ 本会话已用 JP LangFuse Cloud 跑通过一次临时 SDK smoke，Cloud UI 中可见 `datapilot-langfuse-cloud-smoke-20260728T083247Z` trace 和 `fake-sql-pipeline-step` span |
| LangFuse 代码现状 | ❌ 代码库中仍无任何 LangFuse 正式引用；Phase 3B 实施前只完成了临时 SDK 连通性验证 |
| 独立评测项目 | EvalBench尚在规划阶段，计划做成独立项目 |

### 本次对话分析结论摘要

上一轮对话对当前方案、LangFuse、LangSmith 做了详细对比，关键结论：

1. **当前自研 JSONL trace + 规则评分**：在当前 Text2SQL 阶段刚好够用，但缺乏三个关键能力——(a) LLM-as-Judge 语义评分、(b) Trace 可视化和查询、(c) 实验管理平台化
2. **LangSmith vs LangFuse**：功能相近；LangSmith 仅 SaaS（国内网络不稳定），LangFuse 开源可自部署（BSL 协议，非生产级使用免费）
3. **那个员工的方案**（业务埋点 → LangFuse trace → LLM-as-Judge + 规则计算 → Experiment）：思路完全正确，是行业主流做法，适合作为 EvalBench的参考架构
4. **对 DataPilot**：建议暂不切，先抽象 trace 接口，等 RAG/Hybrid 阶段再评估
5. **对 EvalBench**：强烈建议直接基于 LangFuse 构建，省 6-8 周基建工作量

用户决定：**趁 Phase 3A 刚收口、Phase 3 未开工的窗口期，新增 Phase 3B 引入 LangFuse。v6 路线进一步收敛为：DataPilot 先用 LangFuse Cloud 验证能力，自部署留给 EvalBench 阶段；当前请求级 `trace_id` 保持 DataPilot 自己管理，LangFuse 使用独立 `langfuse_trace_id` 并通过 metadata 建立映射。** 本文档即为该阶段的执行计划。

### 关键文件索引

| 文件 | 作用 | 本阶段是否修改 |
|------|------|---------------|
| `engine/trace/recorder.py` | Trace 数据模型 + JSONL 写入 | ✅ 重构为抽象接口 + 双写 |
| `app/api/query.py` | `/api/query` 路由，`_record_trace()` 入口 | ✅ 注入 LangFuse trace |
| `app/core/config.py` | Settings 配置类 | ✅ 新增 LangFuse 字段；清理未使用的 LangSmith 字段 |
| `.env.example` | 环境变量模板 | ✅ 新增 LangFuse 配置项；保持 LangSmith 配置清理后的口径 |
| `eval/run_eval.py` | 评测执行器 | ✅ 增加 LLM-as-Judge 评分器 |
| `eval/scorers/` | 评分器模块（新目录）：L1 规则 + L3 LLM-as-Judge | ✅ 新建 |
| `engine/trace/langfuse_backend.py` | LangFuse 适配器（新文件）| ✅ 新建 |
| `scripts/smoke_phase3b_langfuse.py` | Phase 3B smoke 脚本（新文件）| ✅ 新建 |
| `eval/cases/` | Eval 用例（已有）| 📋 参考，不修改 |
| `domain_pack/metrics.yaml` | KPI 指标定义 | 📋 参考，不修改 |
| `docs/state/AI_CONTEXT.md` | 技术档案 | ✅ 更新当前状态 |
| `docs/state/AI_CONTEXT_CHANGELOG.md` | 变更记录 | ✅ 记录本阶段 |

---

## 阶段三B 总目标

> ★ 本阶段定位：DataPilot 负责证明“这个业务 Agent 可被观测、可被评测”；EvalBench 负责后续把这套经验抽象成通用评测框架。Phase 3B 不追求在 DataPilot 内完成完整评测平台，也不默认自部署 LangFuse，只做 Cloud 最小接入验证和踩坑记录。

1. **LangFuse Cloud smoke / API spike**：默认使用 JP region 的 LangFuse Cloud，确认 `.env` 中 `LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL` 可用，核对 Python SDK 版本、trace/observation 创建、`flush()`、Score API 和 trace 查询延迟
2. **Cloud 优先，不默认自部署**：DataPilot Phase 3B 不强制本机 Docker 自部署；自部署只保留为资料调研和 EvalBench 后续重点。若 Cloud 网络不可用或数据安全不可接受，再临时评估 self-host / 远端部署
3. **Trace ID 边界清晰**：DataPilot 当前请求级 `trace_id` 继续服务 API 响应、响应头、JSONL 和 eval 报告；LangFuse 使用独立 `langfuse_trace_id`，并在 LangFuse metadata / JSONL 内保存 `datapilot_trace_id ↔ langfuse_trace_id` 映射
4. **Trace 后端抽象**：把 `append_trace()` 从 "只能是 JSONL" 重构为 "默认 JSONL + 可选 LangFuse" 的双写模式；保留 `append_trace(record, path=...)` 兼容入口，避免破坏测试 / eval 的临时 trace 路径覆盖
5. **带 Span 的分步 Trace**：LangFuse trace 里先用扁平 span / observation 表达 pipeline 的每一步（schema_retrieval → join_path → query_plan → sql_generation → sql_guard → sql_execution）；Phase 3B 不强行伪造精确嵌套和 start/end 时间线
6. **评分器模块**：新增 `eval/scorers/` 模块，先调研 LangFuse 内置评估器，再用“兼容迁移模式”把 `_score_case()` 中已有 L1/L2 规则评分逻辑抽成单一事实源；Markdown 报告继续走旧入口，LangFuse Score 也消费同一批 scorer 结果，避免两套评分口径并行
7. **评测链路打通**：`eval/run_eval.py` 跑完 cases 后，trace 自动提交到 LangFuse；L1/L2/L3 评分结果统一通过 LangFuse Score API 按 `langfuse_trace_id` 回写。Score 回写不等待 trace 可查询，trace 可见性检查只用于 smoke 和调试
8. **最小 Experiment 验证**：在 LangFuse Web UI 中手动从已收集的 trace 创建 Dataset，先用 5 条代表性 case 跑通 A/B workflow smoke（如 DeepSeek vs Qwen），确认 trace → dataset → experiment → score 对比这条流程可用；流程稳定后再扩展到 formal 全量 case，不把 5 条误认为完整 benchmark
9. **为 EvalBench 探路**：本阶段验证 LangFuse 的 trace/score/experiment 全链路能力，确认可以作为独立评测项目的基座；自部署、私有化、多项目接入和平台化能力留给 EvalBench
10. **LangFuse 价值闭环**：M18 证明“能上传、能看见、能回写分数”之后，还必须进入 M19，把 trace/span/score 转成失败归因、失败样本沉淀和 A/B 改进证据。否则 LangFuse 只是在网页里复刻本地 JSONL，无法带来本地 eval 之外的能力提升。

### 阶段完成标准（总览）

- [ ] LangFuse Cloud smoke 跑通：trace、observation、score 都能在 Cloud 侧看到或最终查询到
- [ ] Trace ID 边界清楚：`/api/query` 响应体和响应头继续使用 DataPilot `trace_id`；LangFuse 写入和 Score 回写使用独立 `langfuse_trace_id`；JSONL / metadata 能按 `datapilot_trace_id` 反查 LangFuse trace
- [ ] 双写架构无回归：同一次请求既能写 JSONL，也能在启用时写 LangFuse；LangFuse 失败不影响 JSONL
- [ ] L1/L2 规则评分器可用：`table_hit`、`column_recall`、`safety`、`expected_value`、`result_match`、`contains`、`equals` 等结果能进入 Markdown 报告和 LangFuse Score
- [ ] L3 最小评分器可用：`llm:correctness` 只在 `--judge-model` 或 `EVAL_JUDGE_MODEL` 明确配置时运行，失败不阻断 eval
- [ ] 手动 Experiment workflow smoke 走通：5 条代表性 case 能完成 dataset / experiment / score 对比；是否扩展 formal 全量 case 有记录
- [ ] 失败归因闭环可用：至少能从本地 eval report + JSONL trace 生成 `failure_stage / failure_reason / needs_action`，并在 LangFuse 启用时把 triage 结果回写为可筛选的 score / metadata
- [ ] 原链路兜底通过：`LANGFUSE_ENABLED=false`、key 缺失、Cloud 不可达、Score 写入失败时，`/api/query`、JSONL、规则评分和 Markdown 报告仍可用
- [ ] 文档同步完成：`docs/state/AI_CONTEXT.md`、`docs/state/AI_CONTEXT_CHANGELOG.md`、`.agent_work/temp/m15-notes.md` 至 `.agent_work/temp/m19-notes.md` 记录关键结论、验证结果和遗留风险
- [ ] Smoke 脚本一键可跑：`scripts/smoke_phase3b_langfuse.py` 输出每个检查点的 PASS / FAIL / PENDING

### 项目边界一句话

DataPilot Phase 3B 做的是 **LangFuse Cloud 接入验证**：保留 JSONL 主链路，同时可选写入 LangFuse Cloud，跑通 trace / score / 手动 experiment，记录它是否适合后续独立评测项目。EvalBench 做的是 **评测平台化**：把 case 管理、adapter、多项目接入、scorer 注册、实验对比、报告生成和 LangFuse 自部署做成可复用框架。

### 非目标（明确不做）

- ❌ 不引入 LangFuse Prompt Management（当前 prompt 仍走 `domain_pack/` 文件）
- ❌ 不做 Dataset 管理 UI（继续用 YAML cases）
- ❌ 不建设通用评测平台（跨项目 adapter、case 版本管理、评测历史、报告平台化留给 EvalBench）
- ❌ 不把 LangFuse 自部署作为 DataPilot Phase 3B 默认目标（自部署留给 EvalBench；本阶段最多调研 / 记录迁移注意事项）
- ❌ 不让 LangFuse 替代 JSONL trace、`eval/run_eval.py` 或现有 Markdown 报告
- ❌ 不把 LangFuse 作为生产强依赖（默认仍走 JSONL，LangFuse 不可用时自动降级）
- ❌ 不删除现有 JSONL 逻辑（保留作为本地兜底和轻量实验场景）
- ❌ 不做 Experiment 自动化（M18 只要求手动走通一次，不要求脚本化）
- ❌ 不在 DataPilot 内完成完整 LLM-as-Judge 稳定性系统（多轮统计、judge 对照、prompt 泄露审计等留给 EvalBench）

### 已知限制（Phase 3B 不做，后续补）

| 限制 | 原因 | 后续何时补 |
|------|------|-----------|
| `CostInfo` 是一次请求的总 token，无法按 span 拆分的 token 归因 | 当前 pipeline 是单步 Text2SQL，只有一次 LLM 调用，拆分 token 需要改 pipeline 层而非 trace 层，投入产出比低 | RAG/Hybrid 阶段 pipeline 变成多次 LLM 调用后补 |
| `TraceStep.parent_step_id` 的 DAG 化 span 嵌套 | 当前 pipeline 是线性步骤，没有父子层级，DAG 化没有实际数据支撑 | RAG/Hybrid 阶段 pipeline 出现分支/迭代后补 |
| 真实 step 起止时间 | 当前 `TraceRecord` 是请求结束后一次性写入，只保存每步 `latency_ms`，没有每步真实 `started_at / ended_at` | RAG/Hybrid 或下一轮 trace 埋点下沉到 pipeline 执行过程中再补 |
| LangFuse 完整本地部署稳定性 | 当前 LangFuse self-host 版本组件较重，本机 Docker 可能受资源限制 | DataPilot Phase 3B 不默认处理；EvalBench 阶段再做 self-host 部署 spike |

---

## 架构设计

### 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                    /api/query                             │
│  app/api/query.py                                        │
│  _record_trace() ──→ TraceRouter ──┬──→ JSONLBackend     │
│                                     │    (eval/traces/)   │
│                                     │                     │
│                                     └──→ LangFuseBackend  │
│                                          (LANGFUSE_BASE_URL)│
└──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────┐
│              LangFuse Cloud (JP region)                    │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────┐    │
│  │ Traces   │  │ Scores   │  │ Web UI (jp.cloud.     │    │
│  │ (Spans)  │  │ (评分)    │  │   langfuse.com)       │    │
│  └─────────┘  └──────────┘  └──────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────┐
│              eval/run_eval.py                             │
│  1. 跑 case → 调 /api/query → 拿到 DataPilot trace_id    │
│  2. L1 结构规则：tables/columns 命中、安全合规、         │
│     SQL 执行成败（从 trace 字段直接判定，零成本）         │
│  3. L2 结果规则：expected_value 数值校验、               │
│     result_match 行集对比（极低成本）                     │
│  4. L3 LLM 裁判：Phase 3B 先做 correctness；             │
│     hallucination/faithfulness 先占位，RAG 阶段补          │
│  5. 从 JSONL / 映射拿到 langfuse_trace_id                │
│  6. 所有评分结果写入 LangFuse Score API                  │
└──────────────────────────────────────────────────────────┘
```

### Trace Backend 抽象

```python
# engine/trace/recorder.py（重构后）

class TraceWriteResult(BaseModel):
    """一次 trace 写入后的内部结果，不进入 /api/query 响应契约。"""

    datapilot_trace_id: str
    langfuse_write_status: Literal["ok", "skipped", "failed"] = "skipped"
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None

class TraceBackend(Protocol):
    """Trace 存储后端接口。
    
    当前实现：JSONLBackend（文件）、LangFuseBackend（Web）
    调用方只依赖这个协议，不关心底层是文件还是平台。
    """
    def record(self, record: TraceRecord, *, path: Path | None = None) -> TraceWriteResult: ...
    def close(self) -> None: ...  # 优雅关闭（flush 缓冲区）

class JSONLBackend:
    """当前的 append_trace 逻辑，保持完全兼容。"""
    def record(self, record: TraceRecord, *, path: Path | None = None) -> TraceWriteResult: ...
    def close(self) -> None: ...

class LangFuseBackend:
    """把 TraceRecord 映射为 LangFuse trace + spans。"""
    def __init__(self, public_key: str, secret_key: str, base_url: str): ...
    def record(self, record: TraceRecord, *, path: Path | None = None) -> TraceWriteResult: ...
    def close(self) -> None: ...

class TraceRouter:
    """根据配置决定写哪些后端：默认只写 JSONL，配置了 LANGFUSE 则双写。"""
    def __init__(self, backends: list[TraceBackend]): ...
    def record(self, record: TraceRecord, *, path: Path | None = None) -> TraceWriteResult:
        result = TraceWriteResult(datapilot_trace_id=record.trace_id)
        for backend in self.backends:
            try:
                backend_result = backend.record(record, path=path)
                if backend_result.langfuse_trace_id:
                    result.langfuse_write_status = backend_result.langfuse_write_status
                    result.langfuse_trace_id = backend_result.langfuse_trace_id
                    result.langfuse_trace_url = backend_result.langfuse_trace_url
            except Exception:
                # LangFuse 不可用时只记日志，不影响主链路
                result.langfuse_write_status = "failed"
                logger.warning("Trace backend unavailable: %s", backend, exc_info=True)
        return result

def build_trace_router(settings: Settings | None = None) -> TraceRouter:
    """按当前 Settings 创建 router，测试可传入 fake settings 避免模块级单例锁死配置。"""
    ...

def configure_trace_router(router: TraceRouter) -> None:
    """仅供测试 / smoke 重置模块级 router；生产代码默认使用初始化时的单例。"""
    ...

def append_trace(record: TraceRecord, *, path: Path = DEFAULT_TRACE_PATH) -> TraceWriteResult:
    """兼容旧调用方的门面函数。

    ★ 测试和 eval 依赖 path 覆盖写入 `.agent_work/temp/`，所以不能直接删除这个入口。
    """
    return trace_router.record(record, path=path)
```

### TraceRecord → LangFuse Span 映射

当前 `TraceRecord.trace_steps: list[TraceStep]` 是扁平列表。映射到 LangFuse 时：

| TraceRecord 字段 | LangFuse 映射 |
|------------------|---------------|
| `trace_id` | LangFuse trace.metadata.datapilot_trace_id；不直接作为 LangFuse trace.id |
| `langfuse_trace_id` | LangFuse trace.id / Score API 的 `trace_id`；由 DataPilot 生成 32 位 hex 或由 SDK 生成后回填，M15 smoke 后固定一种 |
| `langfuse_write_status` | JSONL metadata / smoke 输出；区分 `ok`、`skipped`、`failed` |
| `question` | trace.input |
| `answer` | trace.output |
| `route` | trace.metadata |
| `user_role` | trace.user_id / trace.metadata |
| `cost.latency_ms` | trace.metadata |
| `cost.prompt_tokens` / `cost.completion_tokens` | generation.usage（如有 LLM generation span） |
| `trace_steps[i]` | span / observation（Phase 3B 先扁平挂在 trace 下） |
| `trace_steps[i].name` | span.name |
| `trace_steps[i].step_type` | span.metadata |
| `trace_steps[i].latency_ms` | span.metadata.latency_ms（暂不伪造精确 start_time / end_time） |
| `trace_steps[i].input_summary` | span.input |
| `trace_steps[i].output_summary` | span.output |
| `trace_steps[i].status` | span.level（success/error） |
| `trace_steps[i].error_type` | span.status_message |

> ★ LangFuse trace 和 span 没有"固定 schema"——除了 input/output 外，其他业务字段（sql、tables_used、safety_status 等）全部放 metadata，不丢信息。当前 `TraceRecord` 是请求结束后一次性写入，所以 Phase 3B 的 span 映射是 post-hoc 可视化，不承诺精确时间线；后续把 trace 埋点下沉到 pipeline 执行过程中，再做真正的嵌套 span。
>
> ★ ID 边界：`trace_id` 是 DataPilot 的请求级 ID，继续用于响应头、响应体、JSONL 和 Markdown 报告；`langfuse_trace_id` 是 LangFuse 专用 ID，只用于 LangFuse trace / score 关联。不要让 LangFuse 改写或接管当前 `trace_id`，也不要把上游传入的 `x-trace-id` 直接当成 LangFuse trace id。

---

## 评分分层框架（L1 → L2 → L3）

在实施评分器之前，先确定"什么时候用规则、什么时候用 LLM"的清晰边界。原则：**能用 L1 不用 L2，能用 L2 不用 L3。**

| 层级 | 评分方式 | 适用指标 | 成本 | 示例 |
|------|---------|---------|------|------|
| **L1 结构规则** | 从 trace 结构化字段直接判定 | tables/columns 命中、安全合规（safety_status）、SQL 执行成败（error_type）、延迟阈值（latency_ms）、schema 检索命中（trace_steps metadata） | 零 | `expected_tables ⊆ tables_used` → passed |
| **L2 结果规则** | expected_sql 对照实际 rows（已有 `result_match`）、数值容差校验（已有 `expected_value`） | answer correctness（数值/行集精确对比场景）、指标值校验 | 极低（执行 1 条 SQL） | `abs(actual_gmv - expected_gmv) ≤ tolerance` → passed |
| **L3 LLM 裁判** | 调外部大模型做语义判断 | hallucination（事实是否超出 rows/docs）、faithfulness（回答是否忠实于检索文档）、语义等价判断（L2 无法覆盖的开放文本场景） | 高（每次调 LLM） | "回答是否包含 rows 中不存在的数据？" |

> ★ L1/L2 始终执行（零/极低成本）；L3 仅在 `--judge-model` 显式指定时才开启。这条规则对应到代码：`_score_case()` 默认只跑 `contains`/`equals`/`expected_value`/`result_match` 等现有规则评分；`--judge-model` 传入了才创建 LLMJudge 实例并追加 L3 评分。

---

## 模块划分说明

Phase 3B 从 `M15` 开始编号。本阶段主线不再按 6 个细碎 step 写 dev-log，而是压成 4 个能独立学习、实现、验证和复盘的模块。v6 默认使用 LangFuse Cloud 做最小验证，避免被本地 self-host 的 Docker / ClickHouse / Redis / MinIO 运维细节拖偏；自部署只做资料记录和迁移风险分析，正式落地留给 EvalBench。

> 2026-07-29 补充：M16 的 post-hoc flat spans 足够验证 LangFuse 的接入、双写、降级和 Score/Experiment 关联，但不足以充分验证“排障观测体验”。因此新增 **M16B Trace Lifecycle 下沉预备分支**：它不阻塞 M17/M18 主线验收，单独作为后续 RAG/Hybrid 观测底座的架构对照实验。

模块拆分原则：

- 每个模块结束时只写一段 dev-log 复盘，避免把配置、脚手架、smoke 小步骤拆成一堆学习日志。
- M15 先钉 Cloud / SDK / ID 策略，因为 LangFuse 接入最容易踩在版本 API 和 trace id 语义上。
- M16 单独做 trace 双写，因为这是“不破坏原 JSONL 主链路”的核心风险面。
- M16B 作为并行预备分支，不替换 M16 主线：目标是把 trace lifecycle 下沉到 pipeline 执行层，验证真实层级 span / 异常路径 / 观测排障价值是否值得作为后续底座。
- 2026-07-29 执行路线补充：用户决定在 `M16B` 分支上继续完成 M17 / M18，完成后再整体合并回 `main`。因此本文后续 M17 / M18 不新增 `M17B` / `M18B` 双章节；现有 M17 / M18 目标保持不变，只把执行底座从 M16 post-hoc flat spans 调整为 M16B live lifecycle spans。M16 post-hoc 路线保留为 fallback / 对照，不再作为当前执行分支的默认前提。
- M17 合并 L1/L2/L3 scorer 和 Score 回写，因为它们共同回答“怎么评测、怎么把分数送到 LangFuse”。
- M18 合并 smoke、手动 Experiment 和文档收尾，因为这些都是阶段闭环材料，不单独拆模块。
- M19 不再继续验证“LangFuse 能不能记录”，而是专门回答“LangFuse 比本地 eval 多带来了什么”：把失败 trace 归因成可行动的问题清单，并支持后续跨模型 / 跨版本对比失败分布。
- M20 是 M19 后续的检索链路修复模块：M19 的真实 LLM + embedding A/B 发现 Qwen embedding 结果不稳定，但排查后确认 Milvus collection 存在重复灌入污染，因此先修 Schema Retrieval / Milvus 索引生命周期，再重新评估 embedding，而不是直接判定 embedding 模型无效。
- M21 承接 M20 的 clean run 证据：Qwen embedding 在 vector-only 上有明显收益，但 merged context 没吃到收益，因此下一步收敛到 schema retrieval 融合、排序、relation/metric 覆盖修复，而不是继续盲目换模型。

## 模块总览

| 模块 | 顺序 | 依赖 | 模块目标 | 关键产出 |
|------|------|------|----------|----------|
| M15 LangFuse Cloud 接入基线 | 1 | Phase 3A / M14-lite 收口 | 纳入配置、复跑 Cloud SDK smoke、固定 `datapilot_trace_id` / `langfuse_trace_id` 双 ID 策略、验证 `langfuse` 依赖可选 | Settings / `.env.example`、`.agent_work/temp/m15-notes.md`、ID 策略记录 |
| M16 Trace 双写与降级 | 2 | M15 | 保留 JSONL 主链路，新增 LangFuse 旁路写入和 payload 脱敏；LangFuse 失败不影响 `/api/query` / eval | `engine/trace/recorder.py`、`engine/trace/langfuse_backend.py`、双写 / 降级测试 |
| M16B Trace Lifecycle 下沉预备分支 | 2B（已作为当前执行底座） | M16 | 在独立 `M16B` 分支上把 trace start/end/fail lifecycle 下沉到 Text2SQL pipeline，验证是否适合作为 RAG/Hybrid 观测底座 | `engine/trace/lifecycle.py`、`engine/nl2sql/pipeline.py`、lifecycle 测试、A/B 观测对照记录 |
| M17 Scorer 分层与 Score 回写 | 3 | M16B（当前分支） | 把现有规则评分迁移为单一事实源，补最小 L3 judge，并按 `langfuse_trace_id` 写回 LangFuse Score | `eval/scorers/*`、`eval/run_eval.py`、score 回写测试 |
| M18 Smoke / Experiment / 阶段收尾 | 4 | M17（基于 M16B） | 一键 smoke、5 条代表性 case 手动 Experiment、阶段档案和学习复盘收尾 | `scripts/smoke_phase3b_langfuse.py`、Experiment 记录、`docs/state/AI_CONTEXT.md` / CHANGELOG / dev-log |
| M19 Trace Failure Triage / LangFuse-driven Eval Analysis | 5 | M18 | 把 trace/span/score 转成失败阶段、失败原因和下一步动作，形成本地报告 + 可选 LangFuse triage score 的改进闭环 | failure triage summary、triage scorer/heuristics、A/B failure distribution、`.agent_work/temp/m19-notes.md` |
| M20 Schema Retrieval / Milvus Index Hygiene | 6 | M19 | 修复 Milvus 实验链路的索引生命周期、去重和版本口径，并先校准 eval 的 MySQL ground truth，保证 Qwen embedding / Milvus A/B 结果可信 | MySQL ground truth audit、Milvus collection reset/upsert、run 内 retriever 复用、schema_docs_hash、diagnostic 复测、`.agent_work/temp/m20-notes.md` |
| M21 Schema Retrieval Fusion / Context Repair | 7 | M20 | 基于 clean Milvus、Qwen LLM diagnostic 和 retrieval-only benchmark 的证据，修复 schema_context 最大失败簇，让 vector 语义召回能进入最终上下文 | retrieval-only baseline、fusion / rerank 对比、relation/metric 覆盖增强方案、diagnostic 复测、`.agent_work/temp/m21-notes.md` |

## 模块实施明细

## M15：LangFuse Cloud 接入基线

**目标**：复跑并正式记录本会话已经验证过的 LangFuse Cloud SDK 连通性，确认当前 `.env` key / JP region / SDK 版本仍可用，并记录 Cloud → self-host 后续迁移需要注意的边界。

> ★ 顺序说明：本会话已完成一次临时 Cloud smoke，且 `.env` 已有 `LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL`。正式实施 M15 时仍要复跑 smoke 并把结果写入 `.agent_work/temp/m15-notes.md`，但不要重复要求用户创建账号或重新生成 key。M15 后半段再把这些配置正式纳入 `Settings` 和 `.env.example`，避免把临时验证和项目配置改造混在一起。

**操作要点**：

- 当前 `.env` 已有 LangFuse Cloud 三项配置；后续 AI 只需读取变量名并复跑 smoke，不要打印、复制或写入具体 key。如果配置缺失或失效，再提示用户重新创建 JP region project / key。
- 默认使用 LangFuse Cloud JP region：`LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com`
- 从 `.env` 读取 `LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL`，不要把 key 或 Cloud URL 写死到业务代码。
- 这一步的临时 smoke 脚本不依赖 DataPilot 业务代码，只验证 optional observability 依赖里的 LangFuse SDK 能连通 Cloud；脚本放 `.agent_work/temp/` 作为一次性验证素材，不提交到项目。
- 安装/验证 Python SDK API：`Langfuse(public_key=..., secret_key=..., base_url=...)` 或 `get_client()`、trace/observation 创建、`flush()`、`create_score()`、按 `langfuse_trace_id` 查询 observations/scores。
- 固定双 ID 策略：`datapilot_trace_id` 继续使用当前请求级 UUID；`langfuse_trace_id` 使用独立 32 位 hex（优先 `uuid4().hex`，若 SDK smoke 证明必须由 SDK 生成，则记录原因并在 JSONL 回填）。
- 使用当前环境实际安装并 smoke 通过的 LangFuse SDK 版本作为基线，例如记录 `langfuse==4.14.1`；后续不盲目升级，遇到 SDK / Cloud 行为差异时先对照该版本排查。
- 依赖管理优先走 optional extra：在 `pyproject.toml [project.optional-dependencies]` 增加 `observability = ["langfuse==4.14.1"]` 或 smoke 验证过的等价固定版本；M15 notes 记录安装命令 `python -m pip install -e .[observability]`。`LANGFUSE_ENABLED=false` 时仍不得要求安装该 extra。
- 明确 `flush()` 语义：它保证事件送达 LangFuse API，不保证 trace 立即完整可查询；`langfuse_trace_id` 可用于 Score 写入并最终关联，但 spans / metadata 可能还在异步 ingestion，smoke 必须容忍 15-30s 级别的可见性延迟。
- 在 `.agent_work/temp/m15-notes.md` 记录 smoke 结果：SDK 版本、Cloud region、trace URL、trace 查询延迟、Score API 是否可写、双 ID 策略最终选择。
- 同步记录 self-host 调研结论：当前自部署组件较重，DataPilot Phase 3B 不默认执行；EvalBench 阶段再做完整部署 spike。

**验收**：
- `.agent_work/temp/m15-notes.md` 写明 LangFuse Cloud region、Python SDK 版本、关键 API 名称、双 ID 策略和 smoke trace URL
- `.agent_work/temp/m15-notes.md` 必须明确写出最终选定的 `langfuse_trace_id` 生成方式及原因；M16/M17 只能消费这个结论，不能再次分叉
- 复跑最小 SDK 脚本成功创建一条 trace/observation，并用 `create_score(trace_id=<langfuse_trace_id>)` 写入一条 score；可参考本会话已成功看到的 `datapilot-langfuse-cloud-smoke-20260728T083247Z` / `fake-sql-pipeline-step`
- 如果 trace 查询短时间不可见，记录实际延迟，不把它判为实现失败
- 不要求 `docker compose up`，不要求本机自部署 LangFuse

### M15-2：LangFuse Cloud 环境配置

**目标**：把 Cloud 配置纳入 DataPilot 的 Settings 和 `.env.example`，后续只通过配置切换 Cloud / self-host，不改业务代码。

**操作要点**：

- 在 `.env` 中新增：

```env
# LangFuse Cloud (Phase 3B)
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com
EVAL_JUDGE_MODEL=           # L3 judge 默认模型；CLI --judge-model 显式传入时优先
```

- 在 `app/core/config.py` 的 `Settings` 中新增对应字段：优先使用 `langfuse_base_url` / `LANGFUSE_BASE_URL`，如需兼容旧草稿里的 `LANGFUSE_HOST`，只作为别名或迁移注释
- 在 `Settings` 中新增 `eval_judge_model: str = Field(default="", alias="EVAL_JUDGE_MODEL")`；`--judge-model` 显式传入时优先，其次使用 `EVAL_JUDGE_MODEL`，两者都为空时不启用 L3
- 删除 `Settings` 中未使用的 LangSmith 字段：`langsmith_tracing`、`langsmith_endpoint`、`langsmith_api_key`、`langsmith_project`。DataPilot 当前不使用 LangSmith，`.env.example` 中也已无对应配置项，不存在兼容风险；如果后续需要做 LangSmith 对照实验，从 git history 恢复即可
- 删除前先运行 `rg -n "langsmith_|LANGSMITH"`，确认除 `app/core/config.py` 外没有其他业务引用；若发现引用，先汇报再处理
- 更新 `.env.example`
- 不在业务代码中写死 `https://jp.cloud.langfuse.com`、project id 或 trace URL；后续 EvalBench 自部署时只换 `.env`

**验收**：
- `python -c "from app.core.config import get_settings; print(get_settings().langfuse_base_url)"` 输出正确
- `python -c "from app.core.config import get_settings; print(get_settings().eval_judge_model)"` 能读取 `EVAL_JUDGE_MODEL`；为空且未传 `--judge-model` 时表示 L3 跳过
- `LANGFUSE_ENABLED=false` 为默认值；没有 LangFuse key 时，DataPilot 原链路照常运行
- `LANGFUSE_BASE_URL` 改成未来 self-host URL（如 `http://localhost:3000`）时，不需要改业务代码
- `rg -n "langsmith_|LANGSMITH"` 只剩历史文档或无业务引用；`Settings` 中 4 个 LangSmith 字段删除后 `config_snapshot()` 和应用启动不报错

## M16：Trace 双写与降级

**目标**：把 `engine/trace/recorder.py` 的 `append_trace()` 内部改成 TraceBackend 协议 + TraceRouter，默认行为完全不变，且保留 `path` 覆盖能力。

**改动文件**：

1. `engine/trace/recorder.py`：
   - 保留 `TraceRecord`、`TraceStep` 对现有调用方的语义不变；允许新增内部可选字段 `langfuse_trace_id` / `langfuse_trace_url`，但不得进入 `/api/query` 响应契约
   - `TraceRecord` 新增字段：

```python
langfuse_trace_id: str | None = None
langfuse_trace_url: str | None = None
langfuse_write_status: Literal["ok", "skipped", "failed"] = "skipped"
```

   - 上述字段会随 `TraceRecord.model_dump_json()` 写入 JSONL，方便后续 eval / smoke 反查；但 `AgentResponse` 不新增这些字段，保证 `/api/query` 响应契约不变
   - 新增 `TraceBackend` 协议类
   - 把现有 JSONL 写入逻辑抽成 `JSONLBackend`
   - 新增 `TraceRouter`（管理多个 backend），`record(record, path=...)` 继续支持 JSONL 临时路径
   - 模块级单例 `trace_router: TraceRouter` 按 Settings 初始化
   - 新增 `build_trace_router(settings=None)` 和 `configure_trace_router(router)`：测试 / smoke 可重置 router，避免 import 时的模块级单例锁死 `LANGFUSE_ENABLED`
   - 保留 `append_trace(record, path=...)` 作为兼容入口，内部调用 router

2. `engine/trace/langfuse_backend.py`（新文件）：
   - `LangFuseBackend` 实现 `TraceBackend` 协议
   - 依赖 `langfuse` Python SDK，但必须延迟导入：`LANGFUSE_ENABLED=false` 时，即使本地没安装 `langfuse`，DataPilot 原链路也要能运行
   - `record()` 内把 `TraceRecord` 拆成 LangFuse trace + flat spans/observations，并生成 / 回填 `langfuse_trace_id`
   - `path` 参数对 LangFuseBackend 无意义，忽略即可
   - 不可用时抛异常（由 TraceRouter catch + log）

3. `app/api/query.py`：
   - 可继续调用 `append_trace(record, path=path)`，也可调用 `trace_router.record(record, path=path)`
   - 必须保留 `_trace_path(request)` 行为：测试/smoke/eval 指定的临时 JSONL 路径仍生效

**关键设计决策**：

- ★ LangFuse SDK 默认异步批量上传 trace。`LangFuseBackend.record()` 末尾调用 `langfuse.flush()`，只保证事件已经送达 LangFuse API；`langfuse_trace_id` 可用于 Score 写入并最终关联，但服务端仍可能异步处理 spans / metadata，trace/observation 查询短时间不可见是正常现象。因此评分回写不要依赖"先查到 trace"。
- ★ 不让 LangFuse 接管 DataPilot `trace_id`：当前请求级 `trace_id` 只作为 `datapilot_trace_id` metadata 写入 LangFuse；LangFuse 专用 ID 单独生成、单独保存、单独用于 Score API。

**验收**：
- `LANGFUSE_ENABLED=false` 时：行为与当前完全一致，trace 写入 JSONL
- `LANGFUSE_ENABLED=true` 时：JSONL 和 LangFuse 同时写入，`flush()` 后 score 可按 `langfuse_trace_id` 提交；trace 查询允许延迟
- JSONL trace 行中能看到 `trace_id`（DataPilot 主 ID）以及 `langfuse_trace_id` / `langfuse_trace_url`（如 LangFuse 写入成功）
- JSONL trace 行中能看到 `langfuse_write_status`，能区分 `ok`、`skipped`、`failed`
- 未安装 `langfuse` 且 `LANGFUSE_ENABLED=false` 时，`/api/query`、JSONL trace 和 `eval/run_eval.py` 仍可运行
- 测试可通过 `configure_trace_router(build_trace_router(fake_settings))` 或等价 fixture 在同一进程内切换 LangFuse 开关，不依赖重新 import 模块
- `eval/run_eval.py --trace .agent_work/temp/<name>.jsonl` 仍写到指定路径，不污染默认 `eval/traces/traces.jsonl`
- LangFuse 挂了：JSONL 仍正常写入，API 不返回 500
- 已有测试全部通过（`pytest tests/ -x`）

## M16B：Trace Lifecycle 下沉预备分支（并行，不阻塞主线）

**定位**：M16B 是从 M16 主线切出的架构对照分支，用来验证“pipeline 执行层实时埋点”是否值得作为后续 RAG / Hybrid / Agent 观测底座。它不替代 M16，也不阻塞 M17 / M18；主线继续用 M16 的 TraceRouter + post-hoc flat spans 完成 Phase 3B trace → score → experiment 闭环。

> ★ 关键判断：如果只是验证 LangFuse Cloud 接入，M16 的 post-hoc flat spans 已经够；如果要验证 LangFuse 的排障观测价值，以及为后续 RAG/Hybrid 做底座，只挑 `force_new_pipeline` 的 3-5 个 span 不够。M16B 应该做轻量但正式的 Trace lifecycle 抽象，再让 Text2SQL pipeline 作为第一个接入方。

### M16B-0：分支与范围

**操作要点**：

- 从 M16 完成后的工作状态切独立分支：建议分支名 `M16B`（或按工具约定使用 `codex/M16B`），主线不在该分支上继续做 M17 / M18。
- M16B 只做观测底座对照，不新增 scorer / score 回写，不改 M17/M18 主线验收口径。
- M16B 完成后与 M16A 主线做 A/B 对照，记录：
  - LangFuse UI 排障体验是否明显提升
  - 代码侵入度和测试复杂度是否可接受
  - JSONL 与 LangFuse step 口径是否一致
  - 后续 RAG/Hybrid 是否值得基于 M16B 继续演进

**非目标**：

- 不把 LangFuse SDK 直接散落到 pipeline 业务代码里
- 不建设完整跨项目 tracing SDK
- 不在 DataPilot 内做 EvalBench 平台化能力
- 不要求在 M16B 中完成 RAG/Hybrid，只为后续阶段建立 lifecycle seam

### M16B-1：Trace Lifecycle 抽象

**目标**：新增 DataPilot 自己的 trace lifecycle 层，让业务 pipeline 只依赖项目内接口，而不是直接依赖 LangFuse SDK 或 JSONL 写入细节。

**拟改动文件**：

1. `engine/trace/lifecycle.py`（新文件，建议）：
   - 定义 `TraceContext` / `SpanRecorder` / `SpanHandle` 或等价轻量抽象
   - 支持：

```python
trace_context.start_span(name, step_type, input_summary="", metadata=None)
span.end(output_summary="", metadata=None)
span.fail(error_type, message, metadata=None)
```

   - 支持 context manager 用法，确保异常时 span 自动 close：

```python
with trace_context.span("sql_generation", step_type="llm") as span:
    ...
    span.end(output_summary="generated_sql")
```

   - 每个 span lifecycle 同时产出：
     - JSONL 需要的 `TraceStep`
     - LangFuse 需要的 observation/span 事件
   - LangFuse 写入失败不得影响业务执行；失败状态进入 trace metadata 或 lifecycle 状态

2. `engine/trace/recorder.py`：
   - 继续保留 M16 的 `TraceRouter` / `append_trace()` 兼容入口
   - M16B 不删除 post-hoc TraceRecord 写入，避免 eval / JSONL 主链路断开
   - 如需新增 lifecycle-aware backend，只能作为内部扩展，不改变 `/api/query` 响应契约

3. `engine/trace/langfuse_backend.py`：
   - 复用 M16 的 SDK 延迟导入、双 ID 策略、flush 语义
   - 如果 lifecycle 层需要实时 start/end span，封装在 DataPilot adapter 内，业务 pipeline 不直接 import `langfuse`

**关键设计决策**：

- ★ lifecycle 抽象是 DataPilot 的边界，不是 LangFuse 的边界。业务层只说“开始/结束一个步骤”，不关心最终写入 LangFuse、JSONL 还是 EvalBench。
- ★ JSONL 和 LangFuse 必须共用同一套 step lifecycle，避免出现两套 trace 口径：一个 step 在 JSONL 叫 `sql_generation`，LangFuse 里叫 `llm_sql_generator`。
- ★ lifecycle 层必须优先保证业务不中断：span start/end/fail 任一步失败，都不能改变 pipeline 的 SQL 生成、Guard、执行结果。

### M16B-2：完整接入 Text2SQL pipeline

**目标**：不是只补 3-5 个示意 span，而是让当前新 Text2SQL pipeline 的主要步骤都通过 lifecycle 生成 trace。

**优先接入范围**：

- pipeline root：一次 `force_new_pipeline` 请求的整体 span
- `schema_retrieval`：schema 检索、候选表/字段数量、profile、backend
- `join_path`：join path 推断结果、候选关系数
- `query_plan`：QueryPlan 生成 / 校验 / blocked 原因
- `sql_generation`：SQL 生成成功/失败、raw preview、parse error
- `sql_guard`：只读检查、RBAC、敏感字段拦截、blocked reason
- `sql_execution`：执行耗时、表名、列名、行数，不上传完整 rows
- `chart_generation`：图表 mark、x/y 字段、是否 skipped
- error / blocked path：LLM 失败、plan validation failed、SQL Guard blocked、tool error 都必须 close span

**拟改动文件**：

- `engine/nl2sql/pipeline.py`
  - 把当前手工 append `TraceStep(...)` 的位置逐步迁移到 lifecycle
  - 保留返回 `pipeline_result.trace_steps`，确保 `/api/query`、eval 和 JSONL 消费方不变
- `app/api/query.py`
  - 如需传入 `trace_context`，只在 `force_new_pipeline` 分支接入；旧模板链路暂不强行改
  - 不新增 `AgentResponse` 字段

**验收**：

- 成功路径：LangFuse UI 能看到 root span + 主要 step spans，并且 JSONL `trace_steps` 与 LangFuse step 名称一致
- blocked 路径：SQL Guard / plan validation blocked 时 span 正常 close，JSONL 仍有完整 `error_type` / `blocked_reason`
- LLM 失败路径：span 记录 `raw_response_preview` / `parse_error` 等已有 M14-lite trace 信息，不因异常丢失后续 JSONL
- `LANGFUSE_ENABLED=false` 时，lifecycle 仍能产出 JSONL trace_steps，不要求安装或调用 LangFuse
- `LANGFUSE_ENABLED=true` 且 Cloud 不可用时，业务请求不 500，JSONL 仍写入，LangFuse failure 可诊断

### M16B-3：A/B 对照与采用决策

**目标**：用同一批 case 对比 M16A 与 M16B，不靠主观感觉决定是否把 M16B 合回后续主线。

**建议对照集**：

- 3 条成功路径：
  - 单表聚合
  - 多表 join
  - 带 chart 的聚合题
- 3 条异常 / blocked 路径：
  - 危险 SQL / prompt injection
  - 敏感字段查询
  - LLM 生成失败或 plan validation failed（可用 mock / monkeypatch 制造）

**对照维度**：

| 维度 | M16A post-hoc flat spans | M16B lifecycle spans | 结论记录 |
|------|--------------------------|----------------------|----------|
| LangFuse UI 是否能快速定位慢步骤 | 待测 | 待测 | 写入 `.agent_work/temp/m16b-notes.md` |
| blocked / error path 是否完整 | 待测 | 待测 | 写入 `.agent_work/temp/m16b-notes.md` |
| JSONL 与 LangFuse step 口径是否一致 | 待测 | 待测 | 写入 `.agent_work/temp/m16b-notes.md` |
| 代码侵入度 | 低 | 待评估 | 统计改动文件和关键函数 |
| 测试复杂度 | 低 | 待评估 | 统计新增测试和 mock 边界 |

**合入建议标准**：

- 如果 M16B 明显提升 UI 排障体验，且 lifecycle 抽象没有把 LangFuse SDK 泄漏进业务层，则可作为 RAG/Hybrid 前的推荐底座。
- 如果 M16B 只带来 UI 层轻微改善，却显著增加 pipeline 复杂度，则主线保持 M16A，等 RAG/Hybrid 真正出现多步骤分支后再做下沉。
- 无论是否合入，M16B 的实验结论都写入 `docs/state/AI_CONTEXT_CHANGELOG.md`；影响路线的摘要同步到 `docs/state/AI_CONTEXT.md`。

## M17：Scorer 分层与 Score 回写

M17 拆为三个子步骤，先调研，再迁移规则评分，最后补最小 L3 judge。

> **基于 M16B 执行的补充说明**：当前分支后续 M17 / M18 以 M16B live lifecycle trace 为底座。Score 回写语义仍然只依赖 JSONL 中的 `langfuse_trace_id`，因此不需要新增 `M17B`；但实现和测试要覆盖 `langfuse_span_mode=live` 时不会触发 post-hoc span 重放，且 scorer / score 回写只读取映射字段，不依赖 LangFuse trace 已可查询。

### M17-1：调研 LangFuse 内置评估器（先做）

**目标**：确认 LangFuse 内置了哪些评估器、评分质量如何、哪些可以直接复用，避免从零造轮子。

**操作要点**：

- 阅读 LangFuse 文档中的 [Built-in Evaluators](https://langfuse.com/docs/scores/model-based-evals) 列表
- 在跑内置评估器前，先用当前 judge provider / model 做一条最小连通性检查；若外部 LLM key、额度或限流不可用，本子步骤记录 blocked / skipped 原因，不阻塞 M17-2 的 L1/L2 主线
- 至少跑通 `hallucination` 和 `answer-relevance` 两个内置评估器（只需配置 judge 模型 API key）
- 对比内置评估器的 prompt 模板与我们自己的需求（DataPilot 的业务场景是否适用通用模板）
- 得出结论：哪些直接用内置、哪些需要自定义实现

**验收**：
- 在 LangFuse Web UI 或 Python SDK 中成功执行至少 1 个内置评估器并看到 score；如果 judge 连通性失败，则 `.agent_work/temp/m17-notes.md` 必须记录失败原因、是否限流/额度/key 问题，以及不阻塞 L1/L2 的处理结论
- `.agent_work/temp/m17-notes.md` 中记录调研结论（内置评估器列表、复用/自定义判断）

### M17-2：L1 + L2 规则评分器（兼容迁移，零/极低成本）

**目标**：把 `eval/run_eval.py` 中已有的规则评分逻辑结构化注册到 `eval/scorers/`，让 Markdown 报告和 LangFuse Score 共享同一套 scorer 结果。

**与现有 `_score_case()` 的关系**：

采用 **方式 A：薄壳迁移模式**，不是并行实现第二套评分逻辑。`_score_case()` 保留函数名和旧返回结构，但内部只负责调用 `eval/scorers/rule_scorers.py`，再把多条 scorer 明细汇总成旧 Markdown 需要的 `EvalScore`。

```text
旧行为保留：
  eval/run_eval.py
    ↓
  _score_case() 仍作为兼容入口，但变成薄壳
    ↓
  Markdown 报告结构不变

内部迁移：
  table/column/safety/expected_value/result_match/contains/equals
    ↓
  eval/scorers/rule_scorers.py
    ↓
  同一批 scorer 结果
    ├─ 汇总为 EvalScore，供 _score_case() 返回
    └─ 转成 LangFuseScorePayload，供 LangFuse Score API 回写
```

实现时不要让 `_score_case()` 和 `rule_scorers.py` 各自独立判断同一个规则。评分口径只能有一个单一事实源；允许保留旧函数名和旧报告输出，是为了兼容现有 eval 链路。已有 `_score_expected_value()` / `_score_result_match()` 可以迁入或由 `rule_scorers.py` 调用，但最终只能由 `rule_scorers.py` 对外暴露规则评分入口。

建议的数据结构：

```python
class EvalScoreDetail(BaseModel):
    name: str                    # rule:table_hit / llm:correctness / builtin:answer_relevance
    value: float | None
    passed: bool | None = None
    skipped: bool = False
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

def score_case_rules(case: EvalCase, body: dict[str, Any], status_code: int, actual_pipeline_mode: str) -> list[EvalScoreDetail]:
    ...

def summarize_score_details(details: list[EvalScoreDetail]) -> EvalScore:
    ...
```

**评分数据流**：

评分器运行在 eval 上下文里，不是只从 trace 里取数据：

```text
EvalCase (YAML)
  └─ expected_tables / expected_columns / expected_sql / expected_value / check
       ↓
EvalResult.response_body / AgentResponse
  └─ actual tables_used / columns / rows / safety_status / error_type / trace_id
       ↓
TraceRecord / LangFuse trace
  └─ datapilot_trace_id / langfuse_trace_id / trace_steps / metadata，提供可观测证据
       ↓
Scorer.score(case, result)
  ├─ EvalScore：继续服务 Markdown 报告
  └─ LangFuseScorePayload：name + value + langfuse_trace_id + comment/metadata
```

**Score 回写语义**：

- ★ 评分器优先直接调用 LangFuse Score API / SDK，按 `langfuse_trace_id` 写入 score；不要因为 trace 暂时查不到就跳过 score。
- LangFuse 官方语义允许 score 先于 trace 可查询而写入，后续 trace ingestion 完成后再自动关联。
- 只有 Score API / SDK 调用本身失败时才降级：评分继续写入 EvalResult / Markdown 报告，但不回写 LangFuse。
- `pipeline_mode` 下如果没有有效的 `langfuse_trace_id`（因为没走 `/api/query` → `_record_trace()`，或 LangFuse backend 关闭 / 失败），L1/L2 评分结果只写入 EvalResult / Markdown 报告，不回写 LangFuse Score。后续如果需要 pipeline_mode 也写入 LangFuse，可以在 pipeline 内部显式创建 trace。
- trace 存在性查询只用于 smoke、debug 和"数据是否最终可见"验证，不作为评分流程的硬前置。

**新建目录结构**：

```
eval/scorers/
  __init__.py           # 导出 scorer 注册表
  base.py               # Scorer 协议基类
  rule_scorers.py       # L1 结构规则 + L2 结果规则评分器集合
  llm_judge.py          # L3 LLM-as-Judge 评分器
  factory.py            # 根据配置创建 scorer 实例列表
```

**L1 规则评分器（expected 来自 EvalCase，actual 来自 EvalResult / response_body）**：

| 评分器 | expected 来源 | actual 来源 | 评分逻辑 |
|--------|---------------|-------------|---------|
| `table_hit` | `EvalCase.expected_tables` | `response_body.tables_used` / `TraceRecord.tables_used` | expected_tables 全部命中 → 1.0，否则按命中比例计分 |
| `column_recall` | `EvalCase.expected_columns` | `response_body.columns` / `TraceRecord.columns` | expected_columns 召回率 |
| `safety_compliance` | `EvalCase.security_expectation` | `response_body.safety_status` | allow/block 与期望一致 → 1.0，否则 0.0 |
| `sql_success` | case 类型 / 安全期望 | `response_body.error_type` | 仅在 `safety_status="passed"` 后评分；正常 allow case 被误 block 统一由 `safety_compliance` 记 fail，`sql_success` 返回 skipped，避免一条安全失败被重复扣分 |
| `latency_p95` | 固定阈值或 scorer 配置 | `response_body.cost.latency_ms` | 低于阈值 → 1.0，超阈值按比例降分 |

**L2 结果规则评分器（复用已有逻辑）**：

| 评分器 | 对应现有逻辑 | 评分逻辑 |
|--------|------------|---------|
| `expected_value` | `_score_expected_value()` | 数值容差比较（已有） |
| `result_match` | `_score_result_match()` | expected_sql 对照实际 rows（已有） |
| `contains`/`equals` | `_score_case()` 中的检查 | 文本包含/等值检查（已有） |

> ★ L1/L2 评分器的核心原则：不调 LLM，不新增外部依赖，复用现有 eval 数据结构和评分函数；迁移完成后，`_score_case()` 不再自己维护另一套规则判断。

**Score name 命名规范**：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `rule:` | L1/L2 规则评分 | `rule:table_hit`、`rule:expected_value` |
| `llm:` | DataPilot 自研 L3 judge | `llm:correctness` |
| `builtin:` | LangFuse 内置评估器结果 | `builtin:answer_relevance`、`builtin:hallucination` |

### M17-3：L3 LLM-as-Judge 评分器（仅在显式配置 judge model 时启用）

**目标**：实现调外部大模型的语义评分器，作为 L1/L2 规则无法覆盖时的补充。

| 评分器 | 输入 | 输出 | 评分逻辑 | Phase 3B 交付范围 |
|--------|------|------|---------|------------------|
| Answer Correctness | question + answer + expected_answer | 0-1 分 + reason | LLM 判断回答是否与期望语义等价（数值场景走 L2 的 expected_value） | ✅ 最小实现 `llm:correctness` |
| Hallucination | question + answer + rows | 0-1 分 + reason | 判断回答中是否有不存在于 rows 中的事实 | 接口占位 + 内置评估器调研；RAG 阶段实现 |
| Faithfulness | question + answer + docs_used | 0-1 分 + reason | LLM 判断回答是否忠实于检索到的文档 | 接口占位 + 内置评估器调研；RAG 阶段实现 |

**关键设计决策**：

- ★ L3 默认不启用（太贵 + 太慢）：CLI `--judge-model` 显式传入时优先；未传 CLI 但 `EVAL_JUDGE_MODEL` 非空时，用它作为默认 judge model 并启用 L3；两者都为空时跳过 L3
- ★ L3 judge 调用必须带 `timeout=30s` + `max_retries=3`（指数退避 1s/2s/4s），失败时 score 记为 `null` 并打出 warning，不阻断整个 eval 流程。外部 LLM 做裁判本身不稳定——超时、限流、服务抖动都很常见，不能因为一次 judge 失败就丢整条 case 的结果
- Judge provider 默认复用 Settings 中的主 LLM provider；模型选择优先级为 `--judge-model` > `EVAL_JUDGE_MODEL` > 空（跳过 L3）
- 优先复用 LangFuse 内置评估器（M17-1 调研结论），仅在内置不满足需求时才自定义 prompt
- 评分结果写入 LangFuse 作为 trace score（如果 LangFuse 可用），同时写入 EvalResult 的 issue_tags
- 第一批最小交付只强制实现 `llm:correctness`；`llm:hallucination` 和 `llm:faithfulness` 允许先完成调研、接口占位和 RAG 预留，不阻塞 Phase 3B 主验收

**M17 验收**：
- `python -m eval.run_eval --cases ...` 默认不调 LLM，L1/L2 评分正常
- `python -m eval.run_eval --cases ... --judge-model deepseek-v3` 追加 `llm:correctness` 评分
- 未传 `--judge-model` 但 `.env` 中 `EVAL_JUDGE_MODEL` 非空时，追加 `llm:correctness`；两者都为空时不创建 L3 scorer
- 所有评分结果（L1/L2 + 已启用的 L3）统一通过 LangFuse Score API 写入；Web UI 最终可查，但允许 ingestion 延迟
- 规则评分、L3 judge、LangFuse 内置评估器分别使用 `rule:`、`llm:`、`builtin:` 前缀
- LangFuse 不可用时评分仍正常，只是不回写 score
- 已有 eval cases 通过率不退化

## M18：Smoke / Experiment / 阶段收尾

**目标**：更新技术档案 + 编写一键验证脚本，确保下一轮 AI 会话能正确继承。

**改动文件**：

1. `docs/state/AI_CONTEXT.md`：
   - 「当前状态」section：
     - 当前阶段指针从 `phase3a-plan.md` → `phase3b-langfuse-plan-v6.md`
     - 当前模块更新为 M18 / Phase 3B 收尾（执行中按 M15-M18 滚动更新）
     - 下一模块更新为 Phase 3 RAG/Hybrid
   - 「当前技术选型快照」section：Trace/Eval 条目补充 LangFuse Cloud（JP region、SDK 版本、Cloud base URL、可选写入）、评分分层（L1/L2/L3）、Experiment 最小验证结论
   - 「最新事实快照」section：
     - 新增 LangFuse 默认值：`LANGFUSE_ENABLED=false`、`LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com`、降级行为（不可用时自动跳过，不影响 JSONL）
     - 新增 L3 judge 配置：`EVAL_JUDGE_MODEL=""` 表示复用主 LLM 配置；只有显式指定 `--judge-model` 或配置 judge model 时才启用 L3
   - 「已知的坑」section：新增
     - Cloud region / 网络访问不稳定时可能影响 trace 上传，但不能影响主链路
     - LangFuse SDK / Cloud server 版本兼容性
     - Cloud trace 只是实验记录，不作为 DataPilot 长期数据资产；EvalBench 自部署时可重新采集
     - LangSmith 旧配置已从 `.env` / `.env.example` 清理；`Settings` 中的 `langsmith_tracing`、`langsmith_endpoint`、`langsmith_api_key`、`langsmith_project` 本阶段同步删除

2. `docs/state/AI_CONTEXT_CHANGELOG.md`：
   - 记录本阶段的改动范围、关键决策、验收结果

3. `.agent_work/temp/m15-notes.md`、`.agent_work/temp/m16-notes.md`、`.agent_work/temp/m17-notes.md`、`.agent_work/temp/m18-notes.md`（开发中记录）：
   - Cloud smoke trace URL、SDK 版本、Cloud region、Score API 结果、内置评估器调研结论、Cloud → self-host 迁移注意事项等

4. `scripts/smoke_phase3b_langfuse.py`（新文件）：
   - 检查 LangFuse Cloud 配置是否存在（不打印 secret）
   - 默认读取当前 `.env`；若 `LANGFUSE_ENABLED=false`，JSONL / API 检查照常执行，LangFuse trace / score / query 检查输出 `SKIP (langfuse disabled)` 而不是 FAIL
   - 若用户显式传入 `--require-langfuse`，则 `LANGFUSE_ENABLED=false`、key 缺失或 SDK 未安装都应输出 FAIL，用于 M18 最终验收
   - 发一条 `/api/query` 请求
   - 检查 JSONL trace 文件新增一行，且该行的 `trace_id` 等于本次 `/api/query` 响应里的 DataPilot trace id；如 LangFuse 启用成功，该行还应包含可用于 Score 回写的 `langfuse_trace_id` / `langfuse_trace_url`
   - 调 LangFuse Score API 写入一条评分
   - 调 LangFuse API 轮询确认 trace/observation 最终可查（最多 30-60s，指数退避；短时不可见单独报 `PENDING`，不和 score 写入失败混淆）
   - 输出 PASS / FAIL / PENDING / SKIP（每个检查点一行）

### M18-2：最小 Experiment 走通（手动，不要求自动化）

**目标**：在 LangFuse Web UI 中手动跑通一次完整的 Experiment 流程（trace → dataset → experiment run → 结果对比），记录 UX 体验、API 能力边界和是否满足 EvalBench 需求。

> ★ 这里的 5 条 case 是 **Experiment workflow smoke**，不是完整 A/B benchmark。通俗说：先拿 5 道不同类型的题确认“考试系统能不能正常阅卷和对比”，确认没问题后，再跑 formal 全量用例。

**操作要点**：

- 从 M16-M18 前半段已收集的 LangFuse trace 中手动创建 Dataset，先选 5 条代表性 formal case：
  - 1 条 `table_hit` / 表选择用例：验证模型有没有找对表
  - 1 条 `expected_value` / 数值精确用例：验证 GMV、订单数等指标值是否正确
  - 1 条 `result_match` / SQL 结果一致性用例：验证实际 rows 是否和 expected_sql 对齐
  - 1 条 safety / blocking 用例：验证危险 SQL 或越权请求是否被拦截
  - 1 条复杂或边界用例：验证多表、多条件、空结果、异常路径等更贴近真实问题的场景
- 切换 LLM 配置（如 DeepSeek → Qwen），重新跑这 5 条 case，产出一批新 trace；优先复用 `scripts/run_qwen_ab_experiments.py` 的子进程 env override 思路，不建议手工反复改 `.env`
- 在 LangFuse Web UI 中创建 Experiment，对比两组 run 的 score
- 如果 5 条 workflow smoke 顺利，再扩展跑 formal 全量 case；challenge / diagnostic 等更大规模用例可作为 Phase 3B 后续或 EvalBench 阶段任务
- 记录：UX 体验、Experiment 粒度是否满足 EvalBench 需求、有无 blocking issue、API 能力边界

**验收**：
- LangFuse Web UI 中能看到一次 Experiment，包含两组 run 的 score 对比
- 5 条代表性 case 的选择原因记录清楚，并明确它们只用于 workflow smoke
- 若扩展跑了 formal 全量 case，记录全量 A/B 结果；若本阶段未全量跑，记录原因和后续触发条件
- `.agent_work/temp/m18-notes.md` 中记录 Experiment 走通结论，至少覆盖：
  - Experiment UX 评价（好用/能用/不好用）
  - 是否满足 EvalBench 需求（是/否/部分，为什么）
  - A/B 使用的模型切换方式（env override / 临时 `.env` / 其他），优先记录完整命令
  - 发现的能力边界或坑

---

## M19：Trace Failure Triage / LangFuse-driven Eval Analysis

**目标**：把 M15-M18 已经接好的 trace / span / score 变成真正能推动 DataPilot 改进的评测分析能力。M19 不再证明“LangFuse 能不能上传记录”，而是要回答：某条 case 失败了，到底更像是 schema retrieval、query plan、SQL 生成、安全拦截、SQL 执行、结果比对，还是 scorer 本身的问题；下一步应该改代码、改 case、改 scorer，还是只标记人工复核。

> ★ 关键定位：LangFuse 的价值不能停在“网页里能看 trace”。真正有用的是：失败 case 能按阶段聚合，A/B 实验能看出“新 pipeline 主要减少了哪类失败 / 又新增了哪类失败”，后续 RAG/Hybrid 能把失败样本沉淀成回归集。M19 就是补这条价值闭环。

### M19-1：Failure Stage Taxonomy（失败阶段分类）

先定义一套稳定、可复用、不过度复杂的失败阶段枚举。它不要求 100% 判断真因，但必须比单纯 pass/fail 更能指导下一步。

建议第一版分类：

| failure_stage | 含义 | 常见证据 |
|----------------|------|----------|
| `schema_retrieval` | 没召回该问题需要的表 / 字段 / 指标 | trace 中 schema retrieval 命中为空、缺 expected_tables / expected_columns |
| `schema_context` | schema 召回到了，但传给后续步骤的上下文不够或结构不清 | retrieval 有结果，但 query_plan / sql_generation 仍找错字段 |
| `query_plan` | 自然语言到结构化 QueryPlan 的理解错了 | QueryPlan 缺表、缺筛选条件、指标或时间范围错 |
| `plan_validation` | QueryPlan 校验发现非法或不完整 | plan validator 报 required field / invalid metric / invalid table |
| `sql_generation` | QueryPlan 到 SQL 的生成错了 | SQL 语法错、字段错、join 错、where 条件错 |
| `sql_guard` | 安全策略拦截相关问题 | 危险 SQL、越权、误拦截、应拦未拦 |
| `sql_execution` | SQL 执行层失败 | database error、timeout、no such column/table、类型转换错误 |
| `result_match` | SQL 跑通但结果不符合 expected_sql / expected_value | rows 对不上、数值超 tolerance、排序/列名问题 |
| `answer_synthesis` | 结构化结果正确，但最终自然语言回答错误 | rows 正确，answer 漏报、误报、解释错 |
| `scorer_issue` | 被测链路可能没错，评分器或测试用例有问题 | scorer 规则过窄、expected 写错、case 本身歧义 |
| `judge_unavailable` | LLM-as-Judge 自身不可用 | judge timeout、限流、provider 配置错误 |
| `unknown` | 证据不足，不能安全判断 | trace 缺关键步骤或多个阶段同时异常 |

### M19-2：本地 Failure Triage 输出

M19 的第一交付必须先在本地闭环，避免把 LangFuse 变成强依赖：

- 读取 `eval/run_eval.py` 已有的 case result、score details、issue_tags、HTTP 状态、response body 和 JSONL trace。
- 为每个 failed / skipped / errored case 生成：
  - `failure_stage`：上面的枚举之一
  - `failure_reason`：一句可读解释，说明为什么判断为这个阶段
  - `needs_action`：建议动作，如 `fix_pipeline`、`fix_schema_desc`、`fix_scorer`、`fix_case`、`manual_review`、`infra_retry`
  - `evidence_step`：关联到 trace step 名称、score 名称或 error_type，方便回看证据
- 在 Markdown report 增加 `Failure Triage Summary`：
  - 按 `failure_stage` 聚合数量
  - 按 `needs_action` 聚合数量
  - 列出最值得优先修的 Top cases
- 输出仍兼容 `LANGFUSE_ENABLED=false`，不要求网页 UI、Dataset 或 Experiment。

### M19-3：LangFuse Triage Score / Metadata 回写

LangFuse 启用且 JSONL 里存在有效 `langfuse_trace_id` 时，M19 再把 triage 结果写回 LangFuse，形成 UI 可筛选、可对比的记录。

建议 score / metadata 口径：

- `triage:failed`：BOOLEAN 或 NUMERIC，标记该 case 是否失败
- `triage:failure_stage`：CATEGORICAL / TEXT，值来自 failure stage taxonomy
- `triage:needs_action`：CATEGORICAL / TEXT，值来自 action taxonomy
- `triage:confidence`：NUMERIC，可选，第一版可只用 `1.0 / 0.5 / 0.0` 表示规则证据强弱

注意：LangFuse score 回写失败不能影响本地 report；如果 `langfuse_write_status != "ok"`，M19 只能写本地 triage，不得把 score 写到缺失或失败的 trace id 上。

### M19-4：A/B Failure Distribution（失败分布对比）

M19 要把 A/B 从“整体分数谁高”推进到“失败结构哪里变了”：

- 比较两个 eval run 的 `failure_stage` 分布，例如：
  - 新 pipeline 的 `schema_retrieval` 失败减少，但 `sql_generation` 失败增加
  - 新 judge prompt 的 `scorer_issue` 减少，但 `judge_unavailable` 增加
  - 安全策略调整后 `sql_guard` 误拦截下降
- 报告中输出 A/B 对比摘要，优先用表格而不是长篇解释。
- 这一步只做本地 Markdown / JSON 汇总即可；是否自动创建 LangFuse Dataset / Experiment 不在 M19 默认范围内。

### M19-5：失败样本沉淀边界

M19 可以生成“建议沉淀为回归集”的 candidate list，但不要默认自动改写正式 case 集：

- 输出 candidate：case_id、question、failure_stage、needs_action、是否适合加入 regression。
- 如果要自动创建 LangFuse Dataset、自动导入 eval/cases、或调整正式 benchmark，需要单独确认，因为这会影响评测结构和长期基线。

### M19 非目标

- ❌ 不实现 LangFuse Webhook / remote experiment runner
- ❌ 不要求用户在网页 UI 中手动 Run Experiment
- ❌ 不新增平台级数据库或评测历史表
- ❌ 不默认引入 LLM-as-Judge 来读完整 trace 并“自由发挥判断真因”
- ❌ 不把 heuristic triage 当成绝对真相；它只是工程排障建议，必须保留 `unknown` 和 `manual_review`
- ❌ 不自动修改 formal / challenge / diagnostic case 集

### M19 验收

- 本地 eval report 增加 `Failure Triage Summary`，至少包含 `failure_stage` 聚合、`needs_action` 聚合和 case 明细
- 至少覆盖 3 类可验证失败：SQL guard / SQL execution / result_match 或 scorer_issue
- `LANGFUSE_ENABLED=false` 时完整可运行，报告仍有 triage
- `LANGFUSE_ENABLED=true` 且 trace 写入成功时，能把 triage score / metadata 回写到对应 LangFuse trace
- LangFuse 写入失败、SDK 未安装、trace id 缺失时，triage 不丢失，只记录 score-write skipped / failed
- `.agent_work/temp/m19-notes.md` 记录 taxonomy 取舍、验证命令、样例报告路径、LangFuse 回写结果和已知误判边界
- M19 最终验证不只跑最小 case，还要跑 `formal + challenge + diagnostic`，其中 diagnostic 是 failure triage 的主展示集。验证完后给用户报告说明切换 deepseek-v4-flash 后的效果以及 M19 的效果。

## M20：Schema Retrieval / Milvus Index Hygiene

**目标**：修复 M19 后续 A/B 暴露出的 Milvus 实验链路污染问题，并在复测前校准 eval 的 MySQL ground truth，让 `Milvus + Qwen embedding` / `Milvus + SiliconFlow embedding` 的 eval 结果具备基本可信度。M20 不追求提升 Text2SQL 正确率本身，而是先保证“标准答案可信 + 检索索引可信”。

### M20 背景事实（2026-08-02）

M19 完成后，用户要求追加真实模型 / embedding 对照：

| 配置 | formal | challenge | diagnostic | 备注 |
|---|---:|---:|---:|---|
| DeepSeek `deepseek-v4-flash` + 默认 `inmemory/deterministic` | 7/10 | 9/16 | 19/32 | M19 默认模型快照 |
| Qwen `qwen3.7-max` + 默认 `inmemory/deterministic` | 8/10 | 12/16 | 22/32 | M19 Qwen 主模型对照 |
| Qwen `qwen3.7-max` + Milvus + Qwen embedding | 8/10 | 12/16 | 20/32 | formal/challenge 持平，diagnostic 下降 |
| DeepSeek `deepseek-v4-flash` + Milvus + Qwen embedding | 未跑 | 未跑 | 19/32 | 总分持平，但 failure 分布变化 |

追加排查发现：

- 当前 `build_schema_documents()` 生成 `193` 条 schema documents：`170` 个 field doc、`13` 个 relation doc、`10` 个 metric doc。
- 当前 Milvus collection `datapilot_schema_docs` 的 `row_count=19493`，约等于 `193 * 101`。
- `MilvusVectorIndex` 每次初始化都会 embed 全部 schema docs 并 `insert` 到同一个 collection；`MILVUS_RESET_COLLECTION` 默认是 `false`。
- `retrieve_schema()` 每个 case 都会重新 `_build_configured_vector_index()`；真实 eval 跑多次后，同一批 `doc_id` 被重复插入，Milvus top_k 可能被重复项挤占。
- 因此这批 Qwen embedding 结果只能说明“当前 Milvus 实验链路下没有稳定收益”，不能作为 Qwen embedding 真实能力的最终结论。

### M20 Eval 自身审查事实（2026-08-02）

用户追问“三类 eval 本身是否有问题”后，已结合本地 MySQL `datapilot_dev` 做过一次人工 + 脚本审查，结论如下：

- 三类 case 共 `42` 条：formal `10`、challenge `16`、diagnostic extra `16`；`case_id` 无重复。
- challenge 中所有 `expected_sql` 都能在当前 MySQL 上执行；GMV `11285752.00`、净收入 `11293058.25`、订单 / 明细 / 退款行数和 `docs/state/database-current-state.md` 一致。
- challenge 的 `expected_sql` 在 MySQL 与 eval 当前 SQLite seed 上的业务结果一致，差异主要是 Decimal / float、datetime 字符串格式。
- 但 `result_match` scorer 当前通过 `_prepare_sqlite_seed()` 临时 seed 内存 SQLite 后执行 `expected_sql`，并不是直接用本地 MySQL 作为 ground truth。如果 MySQL seed / migration / 数据异常菜单继续演进，eval 可能变成“SQLite 标准答案”而不是“当前 MySQL 真相”。
- formal 里部分重复主硬门 case 检查过弱，例如 `p3a_multi_002` 只检查 `item_gmv` 字符串，`p3a_multi_003` 只检查 `SaaS 软件` 字符串；SQL 结果、排序或 TopN 错误时仍可能通过。
- `db_core_002` 退款率 case 当前用 `orders.product_id + refunds.order_id` 的主商品口径；而指标文档写的是商品维度优先 `refunds.order_item_id -> order_items.product_id`。当前两种口径 Top1 都是 `Aurora Noise Cancelling Headphones`，所以 contains 可过，但没有真正验证订单明细归因口径。
- `db_simple_002` “已支付订单”使用 `paid_at` 判断，会包含已支付后取消的订单；若题意是“发生过支付”则合理，若题意是“成交订单”则需改题面或 SQL。

结论：M20 不能只修 Milvus 后立刻复测 embedding；必须先做 eval ground truth hygiene，否则 clean Milvus 复测仍可能被 scorer / case 口径干扰。

### M20 关键决策点

这是会影响后续 RAG / Hybrid 检索底座的设计，不允许临时糊一层绕过。执行前若发现需要改变以下口径，必须先向用户说明方案 / 风险 / 后续影响 / 建议，并等待确认：

- 是否把 Milvus 从实验 adapter 升级为正式默认路径。
- 是否改变默认 `SCHEMA_VECTOR_BACKEND=inmemory`。
- 是否更换正式 embedding 模型或 embedding 维度。
- 是否调整 formal / challenge / diagnostic case 集。
- 是否把 `result_match` 标准答案来源从临时 SQLite 改为当前 MySQL / 当前 configured database，或保留 SQLite 但显式标注为离线 deterministic oracle。
- 是否增强 formal 中重复多表题的检查强度，例如从 `contains` 升级为 `result_match` / `expected_value`。
- 是否重写退款率和“已支付订单”的业务题面 / expected SQL 口径。
- 是否把 table-level / metric bundle / relation bundle 新文档加入正式检索语料。

### M20 推荐方案

推荐先做“eval 标准答案卫生 + 索引卫生 + 复测”，不要直接做复杂 rerank 或新检索语料。

0. **MySQL Ground Truth / Eval Case Hygiene**
   - M20 开工后先固化 `.agent_work/temp/m20-eval-ground-truth-audit.md`：记录三类 case 数量、重复题关系、每条 `expected_sql` 在 MySQL 上的执行状态、关键固定事实快照。
   - 优先修 `result_match` 标准答案来源：建议让 scorer 使用当前配置数据库执行 `expected_sql`，或至少新增显式配置 / 报告字段说明 oracle backend 是 MySQL 还是 SQLite。
   - 对 formal 中明显过弱的多表题列出升级方案：哪些改成 `result_match`，哪些保持 `contains`，以及会如何影响历史基线。
   - 对 `db_core_002` 退款率、`db_simple_002` 已支付订单这类业务语义题，先写方案 / 风险 / 后续影响 / 建议，等用户确认后再改 case。
   - 这一步不追通过率，只保证“eval 标准答案和当前 MySQL 事实对齐”。

1. **collection 生命周期修复**
   - 明确实验运行前 collection 必须干净。
   - 支持 `MILVUS_RESET_COLLECTION=true` 时先 drop 再 create。
   - 更推荐 eval 实验使用唯一 collection 名，例如 `datapilot_schema_docs_qwen_20260802_<run_id>`，避免历史 volume 污染。
   - 如果保留固定 collection 名，必须实现 upsert / delete-by-doc-id 语义，不能裸 insert 累积。

2. **run 内 retriever / vector index 复用**
   - 当前每个 case 重建 Milvus index，导致慢、贵、重复写入。
   - M20 应在 eval run 级别复用同一个 vector index / retriever，至少保证一个 run 内只灌入一次 193 条 schema docs。
   - 如果改动 eval runner 侵入较大，先新增显式实验脚本实现 run 级缓存，但要记录这是过渡验证工具，不是最终架构。

3. **schema_docs_hash / embedding 版本标记**
   - 计算 schema docs 内容 hash，至少基于 `doc_id + keyword_text + vector_text`。
   - collection metadata 或本地实验报告记录：`schema_docs_hash`、`embedding_provider`、`embedding_model`、`dimension`、`collection_name`、`row_count`。
   - 如果发现 collection 维度 / 模型 / hash 与当前配置不一致，应拒绝复用或强制 reset。

4. **Milvus 健康检查与验收 smoke**
   - 新增或增强 smoke：创建临时 collection，写入 193 条 schema docs，确认 `row_count == len(documents)`。
   - 对典型 query 输出 `keyword_hits / vector_hits / merged_hits`，至少覆盖 GMV、优惠券、类目、退款、历史价格五类问题。
   - smoke 输出写 `.agent_work/temp/m20-milvus-index-smoke.md`。

5. **复测策略**
   - 先跑 diagnostic，优先比较失败结构，不只看总分。
   - 复测至少包含：
     - DeepSeek + 默认 embedding diagnostic（可引用 M19 结果，不必重跑，除非用户要求）
     - DeepSeek + clean Milvus + Qwen embedding diagnostic
     - Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic
   - 如果 clean Milvus 后 diagnostic 仍无收益，再判断 Qwen embedding 当前不适合这套 schema doc 粒度。

### M20 可选方案对比

| 方案 | 做法 | 优点 | 风险 / 后续影响 | 建议 |
|---|---|---|---|---|
| A. 每次 eval 前 `MILVUS_RESET_COLLECTION=true` | 固定 collection，跑前清空重建 | 最快验证污染问题 | 容易误删同名实验 collection；并发 eval 不安全 | 可作为一次性验证，不建议长期默认 |
| B. 每次实验唯一 collection | collection 名带 run id，跑完可保留或清理 | 最隔离、最利于复现 | collection 数量会膨胀，需要清理策略 | M20 推荐 |
| C. 实现 upsert / delete-by-doc-id | 固定 collection，按 doc_id 覆盖 | 更接近长期服务形态 | 需要确认 pymilvus 3.0 API 行为和一致性 | M20 可做，但先 smoke 证明 |
| D. 只改 eval 脚本缓存，不动 index 语义 | 一个 run 内只建一次 index | 改动小，立刻降成本 | 旧 collection 污染仍存在，跨 run 不可信 | 只能作为过渡 |
| E. 直接换 embedding / rerank | 不修索引，改模型或融合策略 | 看似能提分 | 会把数据污染和模型效果混在一起 | 不建议 |

### M20 非目标

- ❌ 不切默认模型或默认 embedding。
- ❌ 不把 Milvus 设为默认 `SCHEMA_VECTOR_BACKEND`。
- ❌ 不为提升分数随意改正式 eval case 集；case 语义、检查强度或 oracle backend 的长期口径变化必须先说明并确认。
- ❌ 不新增 RAG 文档切片、RAG 语料库或 Hybrid Agent。
- ❌ 不把 diagnostic 提分作为硬目标；M20 的硬目标是索引可信。
- ❌ 不因一次 clean run 结果好看就自动宣布 Qwen embedding 胜出。

### M20 验收

- `.agent_work/temp/m20-notes.md` 记录索引污染证据、设计选择、执行命令和复测结论。
- `.agent_work/temp/m20-eval-ground-truth-audit.md` 记录三类 eval 与当前 MySQL 的审查结果；若改动 scorer / case，需说明前后口径和历史基线影响。
- `result_match` 的 oracle backend 在代码或报告里可追溯，不再让读报告的人误以为一定是当前 MySQL。
- Milvus smoke 能证明 clean collection 下 `row_count == len(schema_documents)`，并记录 collection 名、维度、embedding 模型、schema_docs_hash。
- eval run 内不再对同一个固定 collection 重复插入同一批 schema docs。
- 至少跑一轮 clean Milvus + Qwen embedding diagnostic，并生成 report / triage JSON / failure distribution compare。
- 复测结果同步到 `docs/state/eval-baselines.md`；若结论影响当前路线，再摘要同步到 `docs/state/AI_CONTEXT.md`。
- 如果发现需要正式调整 schema doc 粒度、embedding 默认值、Milvus 默认值或 eval case 结构，先暂停并向用户说明方案 / 风险 / 后续影响 / 建议。

---

## M21：Schema Retrieval Fusion / Context Repair

**目标**：在 M20 已经修好 Milvus index hygiene 之后，专门处理 diagnostic 中最大的 `schema_context` 失败簇。M21 不再问“Milvus collection 是否可信”，而是问：**已经召回到的 vector 语义信号，为什么没有稳定进入最终 schema context，以及如何让关系、指标、字段证据更稳定地喂给 Text2SQL。**

### M21 前置实验事实（2026-08-02）

当前证据来自四组实验，不要只看单个总分：

| 实验 | 结果 | 主要结论 |
|---|---:|---|
| M19 DeepSeek + 默认检索 diagnostic | `19/32` | 默认链路的失败主要集中在 `schema_context`、`query_plan`、`result_match` 等阶段。 |
| M20 DeepSeek + clean Milvus + Qwen embedding diagnostic | `17/32` | clean Milvus 后没有带来 Text2SQL 总分提升，说明“修索引污染”本身不是提分手段。 |
| M20 Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic | `21/32` | Qwen LLM 让 `query_plan` / `plan_validation` 类失败消失，但 `schema_context=7` 仍是最大失败簇；提升主要来自模型，不是 embedding 直接兑现。 |
| Retrieval-only benchmark：deterministic vs Milvus + Qwen embedding | vector-only `0.787` → `0.929`，merged `0.738` → `0.738` | Qwen embedding 本身有更强语义召回，但当前 keyword/vector merge 没把收益转化为最终上下文收益。 |

初步判断：**M21 的优先级应放在 fusion / rerank / context assembly，而不是继续换 embedding 或把 Milvus 设默认。**

### M21 关键决策点

以下选择会影响后续 RAG / Hybrid 的检索底座，执行前如果需要落地为默认策略，必须先向用户说明方案 / 风险 / 后续影响 / 建议，并等待确认：

- 是否改变 `retrieve_schema()` 的 keyword/vector merge 排序规则。
- 是否新增 reranker，尤其是需要外部 LLM / embedding API 的 reranker。
- 是否新增 table-level / metric bundle / relation bundle 等正式 schema docs。
- 是否调整 `top_k`、context token budget、prompt schema section 结构。
- 是否把 Milvus + Qwen embedding 从实验配置提升为默认配置。
- 是否调整正式 eval case 的 `expected_tables` / `expected_columns` / `result_match` 检查强度。

### M21 推荐执行顺序

0. **固化 retrieval-only baseline**
   - 使用 `eval/cases/schema-retrieval-embedding-benchmark.yaml` 固定 10 条 schema retrieval 用例。
   - 每次改 fusion / rerank 前后都跑 deterministic 与 Milvus + Qwen embedding 两组。
   - 报告至少保留 keyword-only、vector-only、merged 三个 recall，避免只看最终 Text2SQL 总分。
   - 同一轮候选对比必须固定 `schema_docs_hash`、embedding provider/model/dimension、collection / row_count、`top_k`、context token budget 和 case 文件版本；这些运行元数据写入报告，避免把索引、语料或上下文容量变化误判为 fusion 收益。

1. **先做无外部依赖的 fusion 对比**
   - 对比当前 merge、RRF（Reciprocal Rank Fusion）、加权分数融合、按 doc_type 加权等策略。
   - 重点观察 relation / metric recall，因为 diagnostic 的 schema_context 失败常常不是表没召回，而是字段、指标口径或 join 关系不完整。
   - 先用实验参数或显式 benchmark runner 对比，不直接改默认 pipeline。

2. **修 context assembly，而不是只堆 top_k**
   - 分析失败 case 的 top docs：确认是 vector 已召回但 merge 丢掉，还是根本没召回。
   - 如果 vector 已召回但最终 context 缺失，优先改 merge / 去重 / 截断策略。
   - 如果 relation 或 metric 本身召回弱，再考虑补 schema docs 粒度，例如 relation bundle、metric bundle、table summary。
   - `schema_context` 是 M19 基于 `missing_columns` 等证据给出的启发式归因，不是绝对真因。每个目标 case 都要记录它属于“已召回但 merge/context 丢失”“未召回”还是“schema 描述、SQL alias、scorer strictness 等非检索问题”，不能只按 triage 标签直接改 fusion。

3. **再考虑 reranker**
   - 先实现本地轻量 rerank：只根据问题文本、可用的 QueryPlan（如已有）、候选文档 metadata、表关系邻近度、指标关键词、字段别名等在线可得信息重排。
   - `expected_tables`、`expected_columns`、expected relation / metric 或任何 benchmark 标注只能用于离线评分和错误分析，绝不能作为 `retrieve_schema()` / reranker 的线上输入，避免评测标签泄漏。
   - LLM reranker / cross-encoder reranker 属于长期策略，成本、延迟和可复现性风险更高，不能作为 M21 的默认第一步。

4. **最后回到 diagnostic 复测**
   - retrieval-only benchmark 有收益后，再跑 DeepSeek / Qwen diagnostic。
   - 候选与基线 diagnostic 必须固定模型、embedding、schema docs hash、`top_k`、context budget、case 集和 triage 版本；先做同配置 A/B，再决定是否额外跑另一模型。
   - 复测优先看 `schema_context` 失败数是否下降，再看总分；同时检查是否把失败迁移到 `schema_retrieval`、`result_match` 或其他阶段。总分可能被 SQL 生成和 scorer 波动影响。

### M21 可选方案对比

| 方案 | 做法 | 优点 | 风险 / 后续影响 | 建议 |
|---|---|---|---|---|
| A. RRF / 加权 fusion | 用 rank 或归一化分数融合 keyword/vector hits | 无外部依赖，最能验证“vector 信号被 merge 吃掉”这个判断 | 需要小心不同 backend 分数不可比 | M21 首选实验方向 |
| B. doc_type 加权 | 对 relation / metric / column / table 文档设不同权重 | 针对 schema_context 失败簇，容易解释 | 权重可能过拟合 10 条 benchmark | 可做，但必须配 diagnostic 复测 |
| C. 补 relation / metric bundle docs | 新增更粗粒度语义文档，例如“退款率商品归因链路” | 能解决单字段召回不足的问题 | 改变 schema docs hash 和长期检索语料，需要重新建基线 | 先列方案，确认后再实施 |
| D. 直接增大 top_k | 让更多文档进上下文 | 快速、实现简单 | 容易污染 prompt，让 LLM 更困惑，也增加 token | 只作为对照，不建议作为主修复 |
| E. LLM / cross-encoder reranker | 对候选 schema docs 二次排序 | 理论效果强 | 成本、延迟、非确定性和依赖复杂度高 | M21 不作为默认，除非用户确认 |

### M21 非目标

- ❌ 不把 Milvus 或 Qwen embedding 切成默认。
- ❌ 不新增 RAG 文档语料或 Hybrid Agent。
- ❌ 不改正式 Text2SQL scorer / oracle backend。
- ❌ 不为了单次 diagnostic 提分改 case。
- ❌ 不用 LLM reranker 作为未经确认的临时替代方案。

### M21 验收

- `.agent_work/temp/m21-notes.md` 记录 fusion / rerank 对比、失败 case 观察和最终建议。
- retrieval-only benchmark 至少跑 deterministic 与 Milvus + Qwen embedding 两组，并保存包含运行元数据、keyword/vector/merged 总体与 table/column/metric/relation 分项 recall、逐 case top docs 的报告。
- 候选 fusion 只有在 merged relation / metric recall 不低于同配置基线、逐 case 结果能解释，且收益不是仅靠增大 `top_k` / context budget 获得时，才能进入 diagnostic 复测；若未满足，记录为否定实验，不改默认 pipeline。
- 如果修改 `retrieve_schema()` 或 context assembly，需要新增/更新 focused tests，覆盖 keyword-only、vector-only、merged 召回顺序。
- 至少跑一组同配置 baseline-vs-candidate diagnostic，报告 `schema_context`、`schema_retrieval`、`result_match` 等 failure distribution 和总分变化；若总分不涨但 schema_context 降低，也要逐 case 记录原因。
- 结果同步到 `docs/state/schema-retrieval-milvus-embedding.md`、`docs/state/eval-baselines.md`；若影响当前路线，再摘要同步到 `docs/state/AI_CONTEXT.md`。

### M21 后续执行计划（已执行收口）

M21 已完成 fusion 候选验证、Context 地基体检、triage 细分类和一次受控 embedding A/B。此次受用户明确要求，额外执行了“Qwen-plus 本地 vs Qwen embedding”对照；这只是单变量实验，不代表切换默认配置。

#### 已执行内容

1. 对齐 qwen3.7-plus weighted / RRF trace、retrieval-only 报告和 SchemaGraph，确认没有证据完整的“目标表/字段已召回但被 context assembly 丢失”主要案例。
2. 将 `schema_context` 中的最终输出契约问题细分为 `output_table_contract`、`output_column_contract`、`result_contract` 和 `scorer_contract`；保留旧 `failure_stage` 兼容性。
3. 固定 `qwen3.7-plus`、weighted、同一 32 条 diagnostic、同一 oracle、同一 schema hash，只改变 Schema Retrieval：
   - A：`inmemory + deterministic`，`21/32`
   - B：clean Milvus + Qwen `qwen3.7-text-embedding`（1024 维），`21/32`
4. 对照结果：两组 `schema_context=6`，`failure_subtype` 分布完全一致；只有 3 个 case 的失败阶段发生转移，没有可归因的 embedding 端到端提分。

#### M21 收口边界

- 默认模型、默认 embedding、默认 Milvus、默认 weighted fusion、正式 case、scorer 和 oracle 均未改变。
- retrieval-only 的 `0.787 → 0.929` vector-only 提升仍保留为有效事实，但不能替代端到端结论。
- RRF 仍是显式候选，不切默认；不继续在 M21 堆 embedding provider、top_k、context budget、bundle docs 或 reranker 参数。

#### 后续衔接

- M22：先处理 `output_table_contract / output_column_contract`，再处理 `QueryPlan → SQL` 的漏表、alias 和生成稳定性。
- M23：待 M22 基础事实稳定后，再逐项尝试 RRF、rerank 或其他 retrieval 方法；每次只改变一个变量，并同时保留 retrieval-only 与端到端指标。

---

## 与独立评测项目（EvalBench）的关系

Phase 3B 是 EvalBench 的**前置探路阶段**，但不是 EvalBench 本身。最通俗的分工：

| 项目 | 角色 | 本阶段边界 |
|------|------|------------|
| DataPilot | 一个真实业务 Agent，也是第一个被测对象 | 只做 LangFuse Cloud 最小接入验证，证明业务 Agent 可以被观测、被评分、被实验对比 |
| EvalBench | 独立评测框架 / 平台 | 后续负责跨项目 adapter、case 管理、scorer 注册、实验编排、历史趋势、报告平台化和 LangFuse self-host |

EvalBench 未来不会“自动进入”DataPilot，而是通过 adapter 调用被测项目：

```text
eval cases
  ↓
EvalBench runner
  ↓
Adapter 调用被测项目
  - HTTP API adapter：POST DataPilot /api/query
  - Python function adapter：调用 run_agent(question)
  - CLI adapter：执行命令并读取 JSON 输出
  - LangFuse adapter：读取已有 traces / scores
  ↓
收集 response / trace / latency / error
  ↓
规则评分 + LLM-as-Judge + 实验对比
  ↓
报告 / dashboard / LangFuse scores
```

所以 Phase 3B 和 EvalBench 的关系不是“抢亮点”，而是“先在真实业务 Agent 上验证工具链，再把经验抽象成通用框架”。DataPilot 里接一次 LangFuse Cloud，亮点是可观测性、降级设计和评测意识；EvalBench 的亮点仍然是通用化、平台化、多项目测评和私有化部署。

### LangFuse 的使用边界

本阶段采用的是“DataPilot 最小接入 + 后续评测项目复用”的组合路线：

```text
DataPilot Phase 3B：
  JSONL 保留为主链路
  LangFuse Cloud 作为可选增强层
  跑通 trace / score / 手动 experiment
  记录 Cloud region、SDK、Score、Experiment、Cloud → self-host 迁移风险

EvalBench：
  吸收 Phase 3B 的经验
  自己管理 cases / runs / scorers / reports
  通过 adapter 测 DataPilot 和其他 Agent 项目
  使用 LangFuse self-host 或 Cloud 作为 trace / score / experiment 后端
```

这相当于把两种思路结合起来：DataPilot 先用 Cloud 验证 LangFuse 能不能用、好不好用；EvalBench 后续再把 LangFuse（含 self-host）和自研评测方法论组合成独立框架。Phase 3B 不越界到通用评测平台，EvalBench 仍有完整项目空间。

本阶段验证的核心问题：

| 问题 | 本阶段如何验证 |
|------|---------------|
| LangFuse API 是否稳定？ | 从 DataPilot 写入 trace + score，观察延迟和丢失率 |
| Cloud 能否支撑最小验证？ | 记录 Cloud region、trace/score 写入延迟、UI 体验和 API 可用性 |
| Cloud → self-host 迁移风险多高？ | 记录哪些配置不能写死、哪些数据无需迁移、哪些能力需要 EvalBench 阶段重新 smoke |
| L1 规则评分是否完整？ | 对照 eval/run_eval.py 现有评分类型，确认全部映射到 scorer |
| LLM-as-Judge 评分质量如何？ | 人工抽查 10-20 条 L3 judge 结果，统计与人工判断的一致性 |
| LangFuse SDK 是否好用？ | 实际写代码体验 `langfuse` Python SDK 的 API 设计和文档质量 |
| LangFuse 内置评估器是否够用？ | M17-1 调研结论直接回答 |
| Experiment 功能是否满足需求？ | M18 手动跑通一次完整闭环，记录 UX 和能力边界 |

本阶段验证通过后，EvalBench 可以直接复用以下资产：
- LangFuse Cloud 接入配置口径（base URL + keys + project）
- `engine/trace/langfuse_backend.py` 的 TraceRecord → LangFuse 映射逻辑
- `eval/scorers/` 的评分器实现
- `.env` 配置模板
- Phase 3B 记录的部署 / SDK / trace 查询延迟 / Score API / Experiment UX 结论

EvalBench 不应该直接照搬 DataPilot 内部业务代码，而应复用本阶段沉淀出的接口思想和验证结论：

- 被测项目只要能通过 HTTP / Python / CLI 返回结构化结果，就可以接入
- JSONL / LangFuse / 数据库都只是 trace 后端选择，不应该绑死某一个业务项目
- scorer 要按能力维度注册，例如 SQL 正确性、工具调用、安全、RAG faithfulness、延迟、成本
- 报告和实验对比属于 EvalBench 的主能力，不在 DataPilot Phase 3B 里展开
- self-host 的部署、数据保留、备份和私有化能力属于 EvalBench 的工程亮点，不在 DataPilot Phase 3B 里强行完成

---

## 风险与降级策略

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| LangFuse Cloud 国内网络偶发不稳定 | 中 | trace/score 上传失败或 UI 访问慢 | LangFuse 全部可选；失败只 warning，不影响 JSONL / eval；必要时走代理或切 self-host 到 EvalBench 阶段 |
| Cloud region / key 配置错 | 中 | auth_check 失败，trace 不出现 | smoke 脚本先验证 `auth_check`；`.env.example` 写清 `LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com` |
| Cloud server 与 SDK 版本差异 | 中 | API 行为或 UI 体验变化 | 固定并记录 `langfuse` SDK 版本；正式实现前复跑 smoke；不从博客旧代码照搬 |
| `flush()` 后 trace 短时不可查询 | 高 | smoke / score 回查误判失败 | `langfuse_trace_id` 可先用于 Score 写入并最终关联；trace 查询做 30-60s 轮询并允许 PENDING |
| LLM-as-Judge 评分太慢/太贵 | 高 | 影响 M17-3 实用性 | 默认不启用；只在少数 diagnostic case 上用；judge 用便宜的模型（如 DeepSeek-V3）而非旗舰模型；优先复用 LangFuse 内置评估器 |
| Cloud trace 含敏感信息 | 中 | 业务数据 / SQL / prompt 泄露到第三方 Cloud | Phase 3B 只传最小必要字段；敏感字段、完整 rows、真实用户 PII 不写入 Cloud trace；后续 EvalBench self-host 再考虑更完整 trace |
| 后续迁移 self-host 有配置差异 | 中 | EvalBench 阶段需要重新验证 | 不写死 Cloud URL、project id、trace URL；所有连接信息只走 `.env`；self-host 时复用同一 smoke |
| LangFuse 服务挂了 | 低 | trace 丢失 | JSONL 始终作为第一优先级写入；LangFuse 是“追加”不是“替代” |

### Cloud → Self-host 迁移风险（v5 起保留，v6 补充 ID 边界）

先用 Cloud、后续 EvalBench 再 self-host 是可行的，但需要提前守住几条边界，避免把 DataPilot 写成 JP Cloud 专用：

| 风险 | 通俗解释 | Phase 3B 防法 |
|------|----------|---------------|
| URL 写死 | 代码里如果写死 `https://jp.cloud.langfuse.com`，以后换成 `http://localhost:3000` 就要改代码 | 只从 `LANGFUSE_BASE_URL` 读取 |
| Project / trace URL 写死 | Cloud project id 是临时实验项目，self-host 会换 | 代码只保存 `datapilot_trace_id` / `langfuse_trace_id` 映射；URL 仅用于日志 / smoke 输出 |
| SDK / server 版本不同 | Cloud 更新快，self-host 版本可能不同 | 记录 SDK 版本；self-host 前先跑同一 smoke |
| Cloud 数据迁移 | Phase 3B 的 trace 是实验记录，不一定值得搬到 self-host | 不把 Cloud trace 当长期资产；EvalBench 可重新采集 |
| 安全边界不同 | Cloud 不适合存完整业务敏感数据，self-host 可以更完整 | DataPilot Cloud 阶段只写最小 trace；完整 prompt/rows/docs 留给 self-host 评估 |

结论：DataPilot Phase 3B 可以先用 Cloud 验证能力；只要所有 LangFuse 连接信息都通过配置读取，并且原 JSONL 主链路保留，后续 EvalBench 切 self-host 的主要工作是部署和重新 smoke，不是大改业务代码。

---

## 单一事实源

- 阶段三B 执行计划：以 `docs/phase3b-langfuse-plan-v6.md` 为准
- 阶段三B 上一版（v5）：以 `docs/archive-versions/phase3b-langfuse-plan-v5.md` 为对照
- 阶段三B v4：以 `docs/archive-versions/phase3b-langfuse-plan-v4.md` 为对照
- 阶段三B v3：以 `docs/phase3b-langfuse-plan-v3.md` 为对照
- 阶段三B v2：以 `docs/phase3b-langfuse-plan-v2.md` 为对照
- 阶段三B 原始版本（v1）：以 `docs/archive-versions/phase3b-langfuse-plan-v1.md` 为存档
- 阶段三A 执行计划：以 `docs/phase3a-plan.md` 为参考（已完成）
- 数据库当前事实：以 `docs/state/database-current-state.md` 为准
- 项目技术档案：以 `docs/state/AI_CONTEXT.md` 为准
- LangFuse 官方文档：https://langfuse.com/docs
- LangFuse Cloud / Docs：https://langfuse.com/docs
- LangFuse 自部署指南（EvalBench 阶段重点参考）：https://langfuse.com/docs/deployment/self-host

---

## 架构底线

> ★ 原链路是主路，LangFuse 是增强。`LANGFUSE_ENABLED=false`、LangFuse Cloud 网络不可用、SDK 报错、Score API 写入失败时，`/api/query`、JSONL trace、规则评分和 Markdown 报告都必须继续可用。

### P0：不可降级

| 约束 | 验证方式 |
|------|---------|
| `/api/query` 响应契约不变 | `tests/` 全部通过，AgentResponse 字段不增不减 |
| JSONL + `eval/run_eval.py` 仍是主验收链路 | `python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --trace .agent_work/temp/<name>.jsonl --report .agent_work/temp/<name>.md` 不依赖 LangFuse 也能完成 |
| JSONL trace 始终可写，不因 LangFuse 挂了而丢 trace | 配错 `LANGFUSE_BASE_URL` 或临时关闭网络 → 调 API → 检查 `eval/traces/traces.jsonl` 有新行 |
| DataPilot trace_id 不被 LangFuse 接管 | `/api/query` 响应体 / 响应头仍是当前 `trace_id`；JSONL 中可看到 `datapilot_trace_id` 和 `langfuse_trace_id` 的映射；LangFuse metadata 可按 `datapilot_trace_id` 反查 |
| LangFuse Cloud 只通过配置启用 | 代码中不出现硬编码 `https://jp.cloud.langfuse.com`、project id 或 secret；全部从 Settings / `.env` 读取 |
| `append_trace(record, path=...)` 兼容入口保留 | `eval/run_eval.py --trace .agent_work/temp/<name>.jsonl` 能写入指定路径；现有 `_record_trace()` 不丢 path override |
| 现有规则评分 (contains/equals/expected_value/result_match) 行为不退化 | `python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml` 通过率不退化 |
| L1/L2 评分器默认启用，不因未传 `--judge-model` 而跳过 | `python -m eval.run_eval --cases ...` 跑完后 trace 上能看到 `rule:table_hit`、`rule:expected_value` 等 L1/L2 score |
| 不因本阶段引入新的必须依赖 | `pip install langfuse` 是可选的（`LANGFUSE_ENABLED=false` 时不需要，但 `LANGFUSE_ENABLED=true` 时是运行时依赖） |
| smoke 脚本可一键验证全链路 | `python scripts/smoke_phase3b_langfuse.py` 输出关键检查点 PASS；trace 查询短时不可见时输出 PENDING 并说明等待窗口 |
| Phase 3B 不越界成完整评测平台 | 代码中不新增跨项目 adapter 框架、评测历史库、报告 Web 平台或自动化 Experiment 编排；这些能力记录给 EvalBench |
| Phase 3B 不强制 self-host | 不要求 `docker compose up` 作为 DataPilot 验收；self-host 只作为 EvalBench 后续计划记录 |

### P1：可简化，接口保留

| 简化方案 | 预留接口/字段 | 后续何时补 |
|----------|-------------|-----------|
| LangFuse Span 先不完美映射 TraceStep 的嵌套关系 | `TraceStep.parent_step_id` 保留；M16B 可在分支验证 Trace lifecycle 下沉 | M16B 对照通过后作为 RAG/Hybrid 前底座；否则 RAG/Hybrid 阶段再补 DAG 化 span |
| LangFuse Span 先不伪造精确 start/end 时间 | `TraceStep.latency_ms` 放 metadata；M16B 可验证真实 start/end lifecycle | M16B 对照通过后合入后续底座；否则后续 pipeline 埋点下沉时再补真实时间线 |
| L3 Hallucination/Faithfulness 可能直接复用 LangFuse 内置评估器 | 自定义 prompt 模板作为 fallback | M17-1 调研后决定 |
| 评分结果回写 LangFuse Score 先走同步调用 | 预留 `async_score()` 方法签名 | 如果评分数量上到 50+ 条且延迟显著，再补异步批量写入 |
| Experiment 只做手动验证，不做 API 自动化 | 实验结论记录在 m18-notes.md | EvalBench 项目启动后补 Experiment SDK 自动化 |

---

## 后续衔接

Phase 3B 完成后，后续阶段的受益：

- **M19 Trace Failure Triage（Phase 3B 价值闭环）**：在 M18 证明 trace / score / smoke 可用之后，优先补 failure triage，把本地 eval + LangFuse trace 变成失败阶段分布、下一步动作和 A/B 改进证据。它比继续手动点 Web UI 更直接服务项目进步，也能为后续 RAG/Hybrid 建立可复用的失败归因口径。
- **M20 Schema Retrieval / Milvus Index Hygiene（M19 后续检索可信度修复）**：在进入 RAG/Hybrid 前，先修复 Milvus collection 重复灌入、索引版本和 run 内复用问题，避免把 embedding 模型效果和索引污染混在一起。
- **M21 Schema Retrieval Fusion / Context Repair（M20 后续上下文修复）**：在 clean Milvus 和 retrieval-only benchmark 证明 Qwen embedding 有 vector 召回信号后，优先修 keyword/vector 融合、relation/metric 覆盖和 context assembly，让 schema_context 失败簇下降，再考虑是否进入 RAG/Hybrid。
- **Phase 3B.1 工具调用容错与重试（可选轻量阶段）**：基于 Phase 3B 的 LangFuse trace 数据，分析当前工具调用失败模式，实现或整理 `ToolResult` 统一结构（status 分类、error_type、是否可重试、重试次数、降级原因），成为面试中回答“工具调用失败怎么办”的直接素材。它不是 Phase 3B 主验收项，只在 trace 暴露出足够失败样本时执行。
- **M16B Trace Lifecycle 下沉预备分支（并行对照）**：如果用户要验证 LangFuse 的真实排障观测价值，先在独立 M16B 分支做 lifecycle 下沉，而不是等 RAG/Hybrid 一口气叠加检索、生成、工具、judge 等复杂度。M16B 不阻塞 M17/M18 主线；它的产出用于决定后续 RAG/Hybrid 是否采用 lifecycle 底座。
- **Phase 3 RAG（检索增强生成）**：LangFuse 上看 retrieval span → generation span 的全链路；L1/L2/L3 评分器已就绪，RAG 专用评分器（faithfulness、context_relevancy）可直接启用。⚠️ 同行踩坑预警：retrieval recall 评测时，开源数据集的 reference text 和自己切片后的 chunk 粒度不一致，容易误判 miss。Phase 3 RAG 应设计 **coverage 指标**（将 reference 按句子拆分，计算 chunk 对 reference 的覆盖度）作为 L1 规则评分器，不做 LLM judge
- **Phase 3 Hybrid（混合推理）**：多步 Agent 的每一步都是独立 span，debug 时不用翻 JSONL
- **EvalBench（独立评测平台）**：吸收 LangFuse Cloud 接入经验、Trace Backend 抽象、Scorer 模块、Experiment 结论和后续 self-host 部署经验，但重新设计成通用框架：adapter 接入多个 Agent、统一 case / run / scorer / report / experiment 管理，从"只测 DataPilot"升级为"可测多个 Agent 项目"

---

## 修订记录

### v6.5（2026-08-03）—— M21 收口与 Qwen-plus embedding controlled A/B

依据：用户确认在 M21 内补做一次固定 Qwen-plus 的本地 deterministic vs clean Milvus/Qwen embedding 对照，以排除 embedding 链路的基本隐患后再进入 M22。

| 改动 | 说明 |
|------|------|
| 固定单变量 A/B | 两组均使用 `qwen3.7-plus`、weighted、同一 32 条 diagnostic、同一 oracle 和 schema hash；只改变 Schema Retrieval backend / embedding |
| 固化结果 | 本地 `21/32`，Milvus + Qwen embedding `21/32`；`schema_context` 和 `failure_subtype` 分布相同，没有端到端 embedding 提分证据 |
| 收口路线 | M21 embedding 线不再继续堆参数；M22 先处理 output contract 与 QueryPlan → SQL，M23 再尝试 rerank 等 retrieval 方法 |
| 保持边界 | 不切默认模型、embedding、Milvus 或 fusion，不修改正式 case、scorer、oracle |

### v6.4（2026-08-02）—— M21 Schema Retrieval Fusion / Context Repair

依据：M20 clean Milvus 复测后，DeepSeek + Qwen embedding diagnostic 仍为 `17/32`；Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic 为 `21/32`，提升主要来自 Qwen LLM 消除 `query_plan` / `plan_validation` 失败，而 `schema_context=7` 仍是最大失败簇。进一步 retrieval-only benchmark 显示 Milvus + Qwen embedding 的 vector-only recall 从 deterministic 的 `0.787` 提升到 `0.929`，但 merged recall 同为 `0.738`，说明 vector 语义信号没有被当前融合策略兑现。

| 改动 | 说明 |
|------|------|
| 新增 M21 模块 | `Schema Retrieval Fusion / Context Repair`，目标是修复 schema_context 最大失败簇，让 vector 语义召回进入最终上下文 |
| 固化实验事实 | 记录 M19/M20 diagnostic、Qwen clean run 和 retrieval-only benchmark 的关键数字，避免把 LLM 提升误判成 embedding 提升 |
| 明确优先方向 | 优先做 RRF / 加权 fusion、doc_type 加权、context assembly 分析；先证明 fusion 有收益，再回到 diagnostic |
| 收紧边界 | 不默认切 Milvus / Qwen embedding，不直接上 LLM reranker，不改 scorer / oracle / case 口径 |
| 补充验收 | M21 必须保存 retrieval-only 双基线、focused tests、diagnostic 复测和 state 文档更新 |
| 吸收审查修正 | M19 默认链路基线修正为 `19/32`；禁止把 benchmark expected 标注输入 reranker；补齐固定运行元数据、逐 case 归因和同配置 A/B 验收门槛 |

### v6.3（2026-08-02）—— M20 Schema Retrieval / Milvus Index Hygiene

依据：M19 后续 Qwen `qwen3.7-max` + Qwen embedding、DeepSeek + Qwen embedding diagnostic 复测显示 Qwen embedding 未带来稳定收益；进一步排查发现 Milvus `datapilot_schema_docs` `row_count=19493`，而当前 schema docs 只有 193 条，说明固定 collection 被每 case / 每 run 重复灌入，A/B 结果受索引污染影响。

| 改动 | 说明 |
|------|------|
| 新增 M20 模块 | `Schema Retrieval / Milvus Index Hygiene`，目标是修复 eval MySQL ground truth、Milvus collection 生命周期、重复写入、版本口径和 run 内复用 |
| 明确 M20 前置事实 | 记录 `193` schema docs vs `19493` Milvus rows、Qwen embedding 复测结果和不能直接判定 embedding 模型无效的原因 |
| 补充 eval 自身审查 | 记录三类 case 与本地 MySQL 对照结论：`expected_sql` 可执行且固定事实一致，但 `result_match` 当前用 SQLite oracle、formal 部分检查偏弱、退款率 / 已支付订单题面有口径歧义 |
| 收紧决策边界 | 默认模型、默认 embedding、Milvus 默认值、eval case、schema doc 粒度变更都需先确认 |
| 固定推荐方案 | 优先做 MySQL ground truth audit、clean collection、唯一 collection 或 upsert、`schema_docs_hash`、run 内 retriever 复用和 diagnostic 复测 |
| 收紧非目标 | 不切默认、不做 RAG/Hybrid、不追 diagnostic 提分，不为提分随意改 case；只保证标准答案可信和索引可信 |

### v6.2（2026-08-02）—— LangFuse 价值闭环补充：M19 Failure Triage

依据：M15-M18 已经证明 DataPilot 可以把流程 trace、score 和 smoke 结果写到 LangFuse，但如果 LangFuse 只是把本地 JSONL 换个网页展示，对项目改进帮助有限。Phase 3B 需要补一层“基于 trace 的失败归因和 A/B 失败分布分析”，让 LangFuse 观察数据真正服务评测闭环。

| 改动 | 说明 |
|------|------|
| 新增 M19 模块 | `Trace Failure Triage / LangFuse-driven Eval Analysis`，目标是把 trace/span/score 转成 `failure_stage`、`failure_reason`、`needs_action` |
| 新增 failure stage taxonomy | 覆盖 `schema_retrieval`、`query_plan`、`sql_generation`、`sql_guard`、`sql_execution`、`result_match`、`scorer_issue`、`unknown` 等阶段 |
| 明确本地优先 | M19 必须在 `LANGFUSE_ENABLED=false` 时也能输出本地 failure triage report，LangFuse 只做增强回写和筛选对比 |
| 补充 LangFuse triage score 口径 | 规划 `triage:failed`、`triage:failure_stage`、`triage:needs_action`、`triage:confidence` 等可筛选 score / metadata |
| 补充 A/B failure distribution | A/B 不只比较总分，还要比较失败结构变化，例如 schema 失败减少但 SQL 生成失败增加 |
| 收紧边界 | 不默认实现 Webhook runner、不自动创建 Dataset、不自动改正式 case 集、不把启发式归因当作绝对真因 |

### v6.1（2026-07-29）—— M16B Trace Lifecycle 下沉预备分支

依据：M16 的 post-hoc flat spans 足以验证 LangFuse 接入、双写、降级、Score/Experiment 关联，但不足以充分验证“LangFuse 作为排障观测底座”的价值。若等到 RAG/Hybrid 再首次下沉埋点，会把 trace lifecycle 设计问题和 RAG 本身复杂度混在一起。

| 改动 | 说明 |
|------|------|
| 新增 M16B 并行分支 | M16B 不阻塞 M17/M18 主线，作为 Trace lifecycle 下沉和观测体验对照实验 |
| M16B 目标从“3-5 个 span spike”升级为底座验证 | 明确只挑少数 span 不足以服务后续 RAG/Hybrid；应新增 DataPilot 自己的 `TraceContext/SpanRecorder` 抽象 |
| 规定 SDK 边界 | pipeline 业务代码不得直接 import `langfuse`；只依赖 DataPilot trace lifecycle 接口 |
| 规定完整 Text2SQL 接入范围 | 覆盖 pipeline root、schema_retrieval、join_path、query_plan、sql_generation、sql_guard、sql_execution、chart_generation 和 error/blocked path |
| 规定 A/B 采用标准 | 对比 M16A post-hoc flat spans 与 M16B lifecycle spans 的 UI 排障价值、口径一致性、代码侵入度和测试复杂度 |
| 更新 P1 和后续衔接 | 把真实嵌套 span / start-end 时间线从“只等 RAG/Hybrid 后补”调整为“可先由 M16B 分支验证，验证通过再作为后续底座” |

### v6（2026-07-28）—— 双 ID 边界与模块粒度收敛

依据：审查 v5 后发现当前 DataPilot 请求级 `trace_id` 是 API / 日志 / JSONL / eval 的主链路 ID，若直接让 LangFuse 复用或接管，可能引入格式、上游传入 ID、Score 关联和排障语义混淆风险；同时原 6 个 step 粒度过细，写入 dev-log 后会显得碎。

| 改动 | 说明 |
|------|------|
| 标题升级为 v6 | 当前执行计划改为 `docs/phase3b-langfuse-plan-v6.md`；v5 移入 `docs/archive-versions/` |
| 明确双 ID 策略 | `trace_id` 继续作为 DataPilot 请求级 ID；`langfuse_trace_id` 独立生成 / 回填，只用于 LangFuse trace 和 Score API |
| 修正 TraceRecord → LangFuse 映射 | DataPilot `trace_id` 写入 LangFuse metadata 的 `datapilot_trace_id`，不直接作为 LangFuse trace.id |
| 修正 Score 回写语义 | L1/L2/L3 分数按 `langfuse_trace_id` 写入 LangFuse Score；没有该 ID 时只写 Markdown / EvalResult |
| 补充可选依赖底线 | `langfuse` 必须延迟导入；`LANGFUSE_ENABLED=false` 时未安装 SDK 也不能影响原链路 |
| 模块压缩为 M15-M18 | M15 Cloud / SDK / ID 基线，M16 trace 双写，M17 scorer + score，M18 smoke / Experiment / 收尾 |
| 调整临时 notes 文件 | 从单个 `phase3b-notes.md` 改为 `.agent_work/temp/m15-notes.md` 至 `m18-notes.md`，和模块复盘粒度一致 |
| 更新单一事实源 | v6 成为当前执行计划；v5 作为上一版归档对照 |
| 吸收二次审查补丁 | 补齐 M15 ID 策略收口验收、LangSmith 删除前 grep、`EVAL_JUDGE_MODEL` / `--judge-model` 优先级、`_score_case()` 薄壳迁移方案、TraceRouter 测试重置、score 前缀规范、smoke disabled 语义和 optional dependency 管理 |
| 扩展 TraceWriteResult | 新增 `langfuse_write_status=ok/skipped/failed`，区分未启用、成功和失败，方便 smoke / eval 调试 |
| 明确 TraceRecord 内部字段 | 新增 `langfuse_trace_id`、`langfuse_trace_url`、`langfuse_write_status` 写入 JSONL，但不进入 `/api/query` 响应体 |

### v5（2026-07-28）—— Cloud 优先与 self-host 后置

依据：已在 JP LangFuse Cloud 成功看到 smoke trace，并确认 DataPilot Phase 3B 更适合先用 Cloud 验证能力，自部署 LangFuse 留给 EvalBench 阶段。

| 改动 | 说明 |
|------|------|
| 默认路线改为 LangFuse Cloud | Phase 3B 不再默认本机 self-host；优先使用 `https://jp.cloud.langfuse.com` 做最小验证 |
| Step 0 改为 Cloud / SDK smoke | 记录 Cloud region、SDK 版本、trace URL、Score API、trace 查询延迟和迁移注意事项 |
| Step 1 改为 Cloud 环境配置 | `.env.example` 以 `LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com` 为默认示例；self-host 只需换 `.env` |
| 新增 Cloud → Self-host 迁移风险 | 明确 URL / project id 不写死、Cloud trace 不当长期资产、self-host 前重跑 smoke |
| EvalBench 口径收敛 | 文档主体使用 EvalBench，并把 self-host、私有化、多项目平台化留给 EvalBench |
| 风险表改为 Cloud 风险优先 | 重点处理 Cloud 网络、region/key 配置、敏感数据、SDK/server 版本差异，而不是 DataPilot 阶段 Docker 运维 |
| 细节对齐补丁 | Step 0/1 顺序说明、架构图 Cloud URL 残留、`flush()` 与 Score 关联语义、L3 评分器交付范围、开发者经验表述和可选 Phase 3B.1 衔接 |
| 明确 scorer 兼容迁移模式 | `_score_case()` 保留为旧 eval / Markdown 入口，但内部规则评分迁移到 `eval/scorers/` 作为单一事实源，LangFuse Score 复用同一批 scorer 结果 |
| 同步 LangSmith 清理口径 | `.env` / `.env.example` 已清理 LangSmith；若 `Settings` 中仍有旧字段，Phase 3B 实施时同步移除，避免 tracing 配置混淆 |
| 澄清 Step 5 的 5 条 case 定位 | 5 条代表性 case 只用于 Experiment workflow smoke；流程稳定后再扩展 formal 全量 case，避免把 smoke 当完整 benchmark |
| 新增阶段完成标准总览 | 用 checklist 汇总 Cloud smoke、JSONL + LangFuse 双写、L1/L2/L3、Experiment、原链路兜底和文档同步，方便新 AI 会话按清单验收 |
| 补充 Step 0 新手执行指引 | 明确 `.env` 缺 LangFuse 配置时先临时写三行 key / base URL；没有账号时先建 JP region project，Step 1 再正式纳入 Settings |
| 补充 smoke 双写验证 | `scripts/smoke_phase3b_langfuse.py` 必须检查 JSONL trace 新增行和 LangFuse trace_id 对齐，证明原 JSONL 主链路没有被 LangFuse 替代 |
| 补齐 L3 judge 配置口径 | Step 1 新增 `EVAL_JUDGE_MODEL` 和 `Settings.eval_judge_model`；为空时复用主 LLM 配置，避免 Step 3b 执行时缺配置 |
| 补充 pipeline_mode 的 Score 降级规则 | 不走 `/api/query` 且没有有效 LangFuse `trace_id` 时，只写 EvalResult / Markdown，不回写 LangFuse Score |
| 收紧 LangSmith 字段删除方案 | 明确删除 `Settings` 中 4 个旧 LangSmith 字段，而不是只写 deprecated，防止 tracing 配置混淆 |
| 收紧 smoke 与 SDK 基线说明 | Step 0 的临时 smoke 不依赖 DataPilot，放 `.agent_work/temp/`；以已 smoke 通过的 `langfuse==4.14.1` 作为排查基线 |
| 修正伪代码和评分器边界 | TraceRouter 捕获异常时记录 warning；安全类 case 由 `safety_compliance` 评分，`sql_success` 返回 skipped |
| 清理失效链接 | v2.1 修订记录中的空锚点链接改为纯文本 |
| 登记本会话已完成的 Cloud smoke 事实 | 前置状态写明 `.env` 已有三项 LangFuse Cloud 配置，且已在 JP Cloud UI 看到 `datapilot-langfuse-cloud-smoke-20260728T083247Z` / `fake-sql-pipeline-step`；Step 0 改为复跑并正式记录，不重复要求用户生成 key |

### v4（2026-07-28）—— 项目边界收紧

依据：新手视角追问 Phase 3B 难度、面试价值、原链路兜底，以及 EvalBench 作为独立评测框架如何接入 DataPilot。

| 改动 | 说明 |
|------|------|
| 顶部定位从“替代 / 迁移”改为“保留主链路 + 最小接入验证” | 明确 JSONL trace、`eval/run_eval.py` 和 Markdown 报告仍是主验收链路，LangFuse 是增强 |
| 新增“项目边界一句话” | DataPilot 证明业务 Agent 可观测 / 可评测；EvalBench 后续做通用评测框架 |
| 非目标新增“不建设通用评测平台” | 跨项目 adapter、case 版本、评测历史、报告平台化、自动化 Experiment 留给 EvalBench |
| 重写与 EvalBench 的关系 | 说明 EvalBench 通过 HTTP / Python / CLI / LangFuse adapter 调用被测项目，DataPilot 是第一个真实被测对象 |
| 明确 LangFuse 使用边界 | DataPilot Phase 3B 只验证 trace / score / 手动 experiment；EvalBench 后续也可使用 LangFuse 作为后端 |
| 架构底线新增原链路兜底 | LangFuse 关闭、Docker 未启动、SDK 报错、Score 写入失败时，`/api/query`、JSONL、规则评分和 Markdown 报告必须可用 |
| 架构底线新增“不越界”验收 | Phase 3B 不新增跨项目 adapter 框架、评测历史库、报告 Web 平台或自动化 Experiment 编排 |

### v3（2026-07-28）—— 执行细节收紧

依据：对 `phase3b-langfuse-plan-v2.md` 的二次审查，重点处理当前 LangFuse 官方版本和 SDK 行为带来的执行风险。

| 改动 | 说明 |
|------|------|
| 新增 Step 0：LangFuse 版本 / API / 部署 spike | 先钉 server/SDK 版本、自部署组件、资源占用和关键 API，避免基于过期的 Postgres-only 假设实施 |
| 自部署描述改为当前组件拓扑 | 本机部署不再默认写成 LangFuse + PostgreSQL，而是要求核对 Web / Worker / PostgreSQL / ClickHouse / Redis / Blob Storage 等实际组件 |
| 配置名改为 `LANGFUSE_BASE_URL` | 对齐当前 Python SDK 的 `base_url` 口径，`LANGFUSE_HOST` 只作为旧草稿兼容说明 |
| 修正 `flush()` 语义 | `flush()` 只保证事件送达 API，不保证 trace 立即可查询；smoke 允许 PENDING 并做 30-60s 轮询 |
| Score 回写不再等待 trace 可查询 | 优先按 `trace_id` 直接写入 Score API，查询存在性只用于 smoke/debug |
| 保留 `append_trace(record, path=...)` 兼容入口 | 防止破坏 `eval/run_eval.py --trace ...` 和测试里的 `app.state.trace_path` 临时 JSONL 路径覆盖 |
| Span 映射降级为 post-hoc flat spans/observations | Phase 3B 不伪造精确 start/end 时间线，真实嵌套 span 留给后续 pipeline 内埋点 |
| L3 第一批收口为 `llm:correctness` | Hallucination/Faithfulness 先允许调研和接口占位，避免评分器范围过大 |

### v2.1（2026-07-28）—— 同行踩坑补丁

依据：该员工的第二段评论（trace 异步上传、LLM judge 不稳定、retrieval recall chunk 不匹配）

| 改动 | 位置 | 说明 |
|------|------|------|
| `LangFuseBackend.record()` 末尾加 `flush()` | Step 2 设计决策 | 防止 trace 异步上传未完成、评测就读到空数据 |
| 评分前 trace 就绪检查（等待 + 重试 3 次） | Step 3a 前置 | `flush()` 后的极端兜底，降级时不回写 Score 也不阻断流程 |
| L3 judge 调用带 `timeout=30s` + `max_retries=3` | Step 3b 设计决策 | 外部 LLM 做裁判本身不稳定，失败记 null 不阻断 eval |
| Phase 3 RAG 预留 coverage 指标备忘 | 后续衔接 | chunk 粒度 recall 应作为 L1 规则评分器，不做 LLM judge |

### v2（2026-07-27）—— 评审优化

依据：[docs/phase3b-langfuse-plan-review.md](phase3b-langfuse-plan-review.md)

| 改动 | 说明 |
|------|------|
| 总目标扩展为「L1 规则评分器 + L3 LLM-as-Judge」双层评分体系 | 原计划只覆盖 LLM-as-Judge，忽略了从 trace 字段直接计算规则指标这条腿 |
| 新增 L1/L2/L3 评分分层框架 | 明确"能用规则不用 LLM"的优先级，防止成本失控 |
| Step 3 拆为 3-0（调研内置评估器）+ 3a（L1+L2 规则）+ 3b（L3 LLM judge） | 先调研 LangFuse 内置能力再决定复用/自研 |
| 新增 Step 5：最小 Experiment 走通（手动 A/B） | 不再把 Experiment 完全推到 EvalBench |
| 实施步骤从 4 步扩展为 5 步 | — |
| 新增 smoke 脚本（`scripts/smoke_phase3b_langfuse.py`） | 一键验证全链路 |
| 扩充 AI_CONTEXT 更新清单 | 当前阶段指针、LangFuse 默认值、新坑登记 |
| 新增「已知限制」章节 | cost 扁平映射等暂不实现项 |

### v1（2026-07-27）—— 初版

依据：上轮对话中对自研方案 vs LangFuse vs LangSmith 的对比分析结论，以及用户决定新增 Phase 3B。

原始文件：[docs/archive-versions/phase3b-langfuse-plan-v1.md]
