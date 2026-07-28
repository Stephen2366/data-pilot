# DataPilot Phase 3B Plan v2：引入 LangFuse 可观测性与评测基座

> 阶段三B：用 LangFuse 替代当前 JSONL Trace + 规则评分体系，为阶段三 RAG/Hybrid 和独立 agent-eval-ops 项目打好可观测性基座。
>
> **核心目标**：在不改动 `/api/query` 响应契约的前提下，把 trace 存储从 JSONL 文件迁移到 LangFuse 自部署实例，并补齐 **L1 规则评分器 + L3 LLM-as-Judge** 双层评分能力，最后跑通一次最小 Experiment 验证全链路闭环。
>
> **v2 修订**：基于评审意见优化（详见文末「修订记录」）。

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

| 他的经验 | 本计划对应措施 |
|----------|--------------|
| trace 异步上传 → 评测读到空数据 | Step 2：`LangFuseBackend.record()` 末尾 `flush()` 同步等待 |
| | Step 3a：评分前 trace 就绪检查（等待 + 重试 3 次） |
| trace_id 没下传 → step 散落不同 trace | DataPilot 不受影响：所有 step 同在一个 `TraceRecord.trace_steps` 列表中 |
| LLM judge 超时/限流/抖动 | Step 3b：`timeout=30s` + `max_retries=3`，失败记 null 不阻断流程 |
| retrieval recall 的 chunk 粒度问题 | 后续衔接：Phase 3 RAG 预留 coverage 指标作为 L1 规则评分器 |
| "LangFuse 内置评估器可以直接用" | Step 3-0：先调研内置评估器，再决定复用/自研 |
| "rule 指标从 trace 埋点算，不用 LLM" | L1/L2/L3 分层框架：能用规则不用 LLM |
| Experiment 是评测闭环的关键环节 | Step 5：最小 Experiment 走通验证 |

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
| 已有配置预留 | `Settings` 中已有 LangSmith 字段（`langsmith_tracing/endpoint/api_key/project`），当前未启用 |
| LangFuse 现状 | ❌ 代码库中无任何 LangFuse 引用或配置 |
| 独立评测项目 | agent-eval-ops 尚在规划阶段，计划做成独立项目 |

### 本次对话分析结论摘要

上一轮对话对当前方案、LangFuse、LangSmith 做了详细对比，关键结论：

1. **当前自研 JSONL trace + 规则评分**：在当前 Text2SQL 阶段刚好够用，但缺乏三个关键能力——(a) LLM-as-Judge 语义评分、(b) Trace 可视化和查询、(c) 实验管理平台化
2. **LangSmith vs LangFuse**：功能相近；LangSmith 仅 SaaS（国内网络不稳定），LangFuse 开源可自部署（BSL 协议，非生产级使用免费）
3. **那个员工的方案**（业务埋点 → LangFuse trace → LLM-as-Judge + 规则计算 → Experiment）：思路完全正确，是行业主流做法，适合作为 agent-eval-ops 的参考架构
4. **对 DataPilot**：建议暂不切，先抽象 trace 接口，等 RAG/Hybrid 阶段再评估
5. **对 agent-eval-ops**：强烈建议直接基于 LangFuse 构建，省 6-8 周基建工作量

用户决定：**趁 Phase 3A 刚收口、Phase 3 未开工的窗口期，新增 Phase 3B 引入 LangFuse。** 本文档即为该阶段的执行计划。

### 关键文件索引

| 文件 | 作用 | 本阶段是否修改 |
|------|------|---------------|
| `engine/trace/recorder.py` | Trace 数据模型 + JSONL 写入 | ✅ 重构为抽象接口 + 双写 |
| `app/api/query.py` | `/api/query` 路由，`_record_trace()` 入口 | ✅ 注入 LangFuse trace |
| `app/core/config.py` | Settings 配置类 | ✅ 新增 LangFuse 字段 |
| `.env.example` | 环境变量模板 | ✅ 新增 LangFuse 配置项 |
| `eval/run_eval.py` | 评测执行器 | ✅ 增加 LLM-as-Judge 评分器 |
| `eval/scorers/` | 评分器模块（新目录）：L1 规则 + L3 LLM-as-Judge | ✅ 新建 |
| `engine/trace/langfuse_backend.py` | LangFuse 适配器（新文件）| ✅ 新建 |
| `scripts/smoke_phase3b_langfuse.py` | Phase 3B smoke 脚本（新文件）| ✅ 新建 |
| `eval/cases/` | Eval 用例（已有）| 📋 参考，不修改 |
| `domain_pack/metrics.yaml` | KPI 指标定义 | 📋 参考，不修改 |
| `docs/AI_CONTEXT.md` | 技术档案 | ✅ 更新当前状态 |
| `docs/AI_CONTEXT_CHANGELOG.md` | 变更记录 | ✅ 记录本阶段 |

---

## 阶段三B 总目标

1. **LangFuse 自部署**：在本机 Docker 上搭建 LangFuse 实例（PostgreSQL + LangFuse Server），可通过 `http://localhost:3000` 访问 Web UI
2. **Trace 后端抽象**：把 `append_trace()` 从 "只能是 JSONL" 重构为 "默认 JSONL + 可选 LangFuse" 的双写模式，调用方代码不改
3. **带 Span 的分步 Trace**：LangFuse trace 里用嵌套 span 表达 pipeline 的每一步（schema_retrieval → join_path → query_plan → sql_generation → sql_guard → sql_execution），替代当前扁平的 `TraceStep` 列表
4. **评分器模块**：新增 `eval/scorers/` 模块，先调研 LangFuse 内置评估器，再实现 L1 规则评分器（从 trace 结构字段直接计算，零成本）+ L3 LLM-as-Judge 评分器（answer correctness、hallucination、faithfulness，仅在 `--judge-model` 显式指定时启用）
5. **评测链路打通**：`eval/run_eval.py` 跑完 cases 后，trace 自动出现在 LangFuse；L1 + L3 评分结果统一通过 LangFuse Score API 回写到对应 trace
6. **最小 Experiment 验证**：在 LangFuse Web UI 中手动从已收集的 trace 创建 Dataset，跑一次 A/B（如 DeepSeek vs Qwen，5 条 case），记录 UX 体验和 API 能力边界，确认是否满足 agent-eval-ops 需求
7. **为 agent-eval-ops 探路**：本阶段验证 LangFuse 的 trace/score/experiment 全链路能力，确认可以作为独立评测项目的基座

### 非目标（明确不做）

- ❌ 不引入 LangFuse Prompt Management（当前 prompt 仍走 `domain_pack/` 文件）
- ❌ 不做 Dataset 管理 UI（继续用 YAML cases）
- ❌ 不把 LangFuse 作为生产强依赖（默认仍走 JSONL，LangFuse 不可用时自动降级）
- ❌ 不删除现有 JSONL 逻辑（保留作为本地兜底和轻量实验场景）
- ❌ 不做 Experiment 自动化（Step 5 只要求手动走通一次，不要求脚本化）

### 已知限制（Phase 3B 不做，后续补）

| 限制 | 原因 | 后续何时补 |
|------|------|-----------|
| `CostInfo` 是一次请求的总 token，无法按 span 拆分的 token 归因 | 当前 pipeline 是单步 Text2SQL，只有一次 LLM 调用，拆分 token 需要改 pipeline 层而非 trace 层，投入产出比低 | RAG/Hybrid 阶段 pipeline 变成多次 LLM 调用后补 |
| `TraceStep.parent_step_id` 的 DAG 化 span 嵌套 | 当前 pipeline 是线性步骤，没有父子层级，DAG 化没有实际数据支撑 | RAG/Hybrid 阶段 pipeline 出现分支/迭代后补 |

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
│                                          (localhost:3000)  │
└──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────┐
│              LangFuse Server (Docker)                     │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────┐    │
│  │ Traces   │  │ Scores   │  │ Web UI (localhost:    │    │
│  │ (Spans)  │  │ (评分)    │  │   3000)               │    │
│  └─────────┘  └──────────┘  └──────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────┐
│              eval/run_eval.py                             │
│  1. 跑 case → 调 /api/query → 拿到 trace_id              │
│  2. L1 结构规则：tables/columns 命中、安全合规、         │
│     SQL 执行成败（从 trace 字段直接判定，零成本）         │
│  3. L2 结果规则：expected_value 数值校验、               │
│     result_match 行集对比（极低成本）                     │
│  4. L3 LLM 裁判：correctness/hallucination/              │
│     faithfulness（仅 --judge-model 显式开启）             │
│  5. 所有评分结果写入 LangFuse Score API                  │
└──────────────────────────────────────────────────────────┘
```

### Trace Backend 抽象

```python
# engine/trace/recorder.py（重构后）

class TraceBackend(Protocol):
    """Trace 存储后端接口。
    
    当前实现：JSONLBackend（文件）、LangFuseBackend（Web）
    调用方只依赖这个协议，不关心底层是文件还是平台。
    """
    def record(self, record: TraceRecord) -> None: ...
    def close(self) -> None: ...  # 优雅关闭（flush 缓冲区）

class JSONLBackend:
    """当前的 append_trace 逻辑，保持完全兼容。"""
    def record(self, record: TraceRecord) -> None: ...
    def close(self, record: TraceRecord) -> None: ...

class LangFuseBackend:
    """把 TraceRecord 映射为 LangFuse trace + spans。"""
    def __init__(self, public_key: str, secret_key: str, host: str): ...
    def record(self, record: TraceRecord) -> None: ...
    def close(self, record: TraceRecord) -> None: ...

class TraceRouter:
    """根据配置决定写哪些后端：默认只写 JSONL，配置了 LANGFUSE 则双写。"""
    def __init__(self, backends: list[TraceBackend]): ...
    def record(self, record: TraceRecord) -> None:
        for backend in self.backends:
            try:
                backend.record(record)
            except Exception:
                # LangFuse 不可用时只记日志，不影响主链路
                pass
```

### TraceRecord → LangFuse Span 映射

当前 `TraceRecord.trace_steps: list[TraceStep]` 是扁平列表。映射到 LangFuse 时：

| TraceRecord 字段 | LangFuse 映射 |
|------------------|---------------|
| `trace_id` | trace.id（外部 ID） |
| `question` | trace.input |
| `answer` | trace.output |
| `route` | trace.metadata |
| `user_role` | trace.user_id / trace.metadata |
| `cost.latency_ms` | trace.metadata |
| `cost.prompt_tokens` / `cost.completion_tokens` | generation.usage（如有 LLM generation span） |
| `trace_steps[i]` | span（嵌套在 trace 下） |
| `trace_steps[i].name` | span.name |
| `trace_steps[i].step_type` | span.metadata |
| `trace_steps[i].latency_ms` | span 的 start_time / end_time |
| `trace_steps[i].input_summary` | span.input |
| `trace_steps[i].output_summary` | span.output |
| `trace_steps[i].status` | span.level（success/error） |
| `trace_steps[i].error_type` | span.status_message |

> ★ LangFuse trace 和 span 没有"固定 schema"——除了 input/output 外，其他业务字段（sql、tables_used、safety_status 等）全部放 metadata，不丢信息。

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

## 实施步骤

本阶段分 5 个 step，预计工作量约 1-2 天（碎片时间）。

### Step 1：LangFuse 自部署 + 环境配置

**目标**：在本地 Docker 上跑起 LangFuse，能打开 Web UI。

**操作要点**：

- 使用 LangFuse 官方 `docker-compose.yml`（含 PostgreSQL）
- 暴露端口 `3000`（Web UI）、`3030`（API，可选）
- 在 `.env` 中新增：

```env
# LangFuse self-hosted (Phase 3B)
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

- 在 `app/core/config.py` 的 `Settings` 中新增对应字段
- 更新 `.env.example`

**验收**：
- `docker compose up -d` 后 `http://localhost:3000` 能看到 LangFuse 登录/注册页
- `python -c "from app.core.config import get_settings; print(get_settings().langfuse_host)"` 输出正确

### Step 2：重构 trace 后端为可插拔架构

**目标**：把 `engine/trace/recorder.py` 的 `append_trace()` 变成 TraceBackend 协议 + TraceRouter，默认行为完全不变。

**改动文件**：

1. `engine/trace/recorder.py`：
   - 保留 `TraceRecord`、`TraceStep` 数据模型不动
   - 新增 `TraceBackend` 协议类
   - 把现有 JSONL 写入逻辑抽成 `JSONLBackend`
   - 新增 `TraceRouter`（管理多个 backend）
   - 模块级单例 `trace_router: TraceRouter` 按 Settings 初始化

2. `engine/trace/langfuse_backend.py`（新文件）：
   - `LangFuseBackend` 实现 `TraceBackend` 协议
   - 依赖 `langfuse` Python SDK（`pip install langfuse`）
   - `record()` 内把 `TraceRecord` 拆成 LangFuse trace + spans
   - 不可用时抛异常（由 TraceRouter catch + log）

3. `app/api/query.py`：
   - 把 `append_trace(record)` 替换为 `trace_router.record(record)`
   - 签名和行为完全不变

**关键设计决策**：

- ★ LangFuse SDK 默认异步批量上传 trace（~5s 间隔）。为避免 trace 还没上传完、评测就开始读不到数据，`LangFuseBackend.record()` 末尾必须调用 `langfuse.flush()`，确保同步等待上传完成。这是从 [同行经验](#修订记录) 中得到的教训。

**验收**：
- `LANGFUSE_ENABLED=false` 时：行为与当前完全一致，trace 写入 JSONL
- `LANGFUSE_ENABLED=true` 时：JSONL 和 LangFuse 同时写入，`flush()` 确保 trace 立即可查
- LangFuse 挂了：JSONL 仍正常写入，API 不返回 500
- 已有测试全部通过（`pytest tests/ -x`）

### Step 3：新增评分器模块

Step 3 拆为两个子步骤，先调研，再实现。

#### Step 3-0：调研 LangFuse 内置评估器（先做）

**目标**：确认 LangFuse 内置了哪些评估器、评分质量如何、哪些可以直接复用，避免从零造轮子。

**操作要点**：

- 阅读 LangFuse 文档中的 [Built-in Evaluators](https://langfuse.com/docs/scores/model-based-evals) 列表
- 至少跑通 `hallucination` 和 `answer-relevance` 两个内置评估器（只需配置 judge 模型 API key）
- 对比内置评估器的 prompt 模板与我们自己的需求（DataPilot 的业务场景是否适用通用模板）
- 得出结论：哪些直接用内置、哪些需要自定义实现

**验收**：
- 在 LangFuse Web UI 或 Python SDK 中成功执行至少 1 个内置评估器并看到 score
- `.agent_work/temp/phase3b-notes.md` 中记录调研结论（内置评估器列表、复用/自定义判断）

#### Step 3a：L1 + L2 规则评分器（从 trace 字段计算，零/极低成本）

**目标**：把 `eval/run_eval.py` 中已有的规则评分逻辑结构化注册到 `eval/scorers/`，评分结果统一写入 LangFuse Score。

**前置：确认 trace 已落地**（来自同行踩坑经验）：

- ★ 评分前必须通过 LangFuse API 确认 trace 存在；若未找到 trace，等待 2s 重试，最多 3 次，最后一次仍失败则降级——评分继续执行但仅写入 EvalResult，不回写 LangFuse Score
- 这是防御 `flush()` 完成但 LangFuse 服务端仍在写入的极端情况，正常情况下 `flush()` 后再查询应立刻命中

**新建目录结构**：

```
eval/scorers/
  __init__.py           # 导出 scorer 注册表
  base.py               # Scorer 协议基类
  rule_scorers.py       # L1 结构规则 + L2 结果规则评分器集合
  llm_judge.py          # L3 LLM-as-Judge 评分器
  factory.py            # 根据配置创建 scorer 实例列表
```

**L1 规则评分器（从 trace 结构化字段直接判定）**：

| 评分器 | 输入字段 | 评分逻辑 |
|--------|---------|---------|
| `table_hit` | `tables_used` vs `expected_tables` | expected_tables 全部命中 → 1.0，否则按命中比例计分 |
| `column_recall` | `columns` vs `expected_columns` | expected_columns 召回率 |
| `safety_compliance` | `safety_status` | passed → 1.0，blocked → 1.0（安全 case）/ 0.0（正常 case） |
| `sql_success` | `error_type` | 无 error → 1.0，有 error → 0.0 |
| `latency_p95` | `cost.latency_ms` | 低于阈值 → 1.0，超阈值按比例降分 |

**L2 结果规则评分器（复用已有逻辑）**：

| 评分器 | 对应现有逻辑 | 评分逻辑 |
|--------|------------|---------|
| `expected_value` | `_score_expected_value()` | 数值容差比较（已有） |
| `result_match` | `_score_result_match()` | expected_sql 对照实际 rows（已有） |
| `contains`/`equals` | `_score_case()` 中的检查 | 文本包含/等值检查（已有） |

> ★ L1/L2 评分器的核心原则：不调 LLM，不新增外部依赖，从 `TraceRecord` / `EvalResult` 的已有字段直接判定。

#### Step 3b：L3 LLM-as-Judge 评分器（仅在 `--judge-model` 显式指定时启用）

**目标**：实现调外部大模型的语义评分器，作为 L1/L2 规则无法覆盖时的补充。

| 评分器 | 输入 | 输出 | 评分逻辑 | 是否复用 LangFuse 内置 |
|--------|------|------|---------|---------------------|
| Hallucination | question + answer + rows | 0-1 分 + reason | 判断回答中是否有不存在于 rows 中的事实 | 优先复用内置（调研后确认） |
| Answer Correctness | question + answer + expected_answer | 0-1 分 + reason | LLM 判断回答是否与期望语义等价（数值场景走 L2 的 expected_value） | 自定义（内置 answer-relevance 侧重相关性而非正确性） |
| Faithfulness | question + answer + docs_used | 0-1 分 + reason | LLM 判断回答是否忠实于检索到的文档 | 优先复用内置（RAG 预留） |

**关键设计决策**：

- ★ L3 默认不启用（太贵 + 太慢），只在 `--judge-model deepseek-v3` 显式传入时才创建 L3 scorer
- ★ L3 judge 调用必须带 `timeout=30s` + `max_retries=3`（指数退避 1s/2s/4s），失败时 score 记为 `null` 并打出 warning，不阻断整个 eval 流程。外部 LLM 做裁判本身不稳定——超时、限流、服务抖动都很常见，不能因为一次 judge 失败就丢整条 case 的结果
- Judge 模型复用 Settings 中的 LLM 配置（默认 `LLM_PROVIDER`），也可单独指定 `EVAL_JUDGE_MODEL`
- 优先复用 LangFuse 内置评估器（Step 3-0 调研结论），仅在内置不满足需求时才自定义 prompt
- 评分结果写入 LangFuse 作为 trace score（如果 LangFuse 可用），同时写入 EvalResult 的 issue_tags

**Step 3 验收**：
- `python -m eval.run_eval --cases ...` 默认不调 LLM，L1/L2 评分正常
- `python -m eval.run_eval --cases ... --judge-model deepseek-v3` 追加 L3 评分
- 所有评分结果（L1 + L2 + L3）统一通过 LangFuse Score API 写入，在 Web UI 可查
- 规则评分结果也作为 score 写入（`rule:table_hit`、`rule:expected_value` 等），与 L3 的 `llm:correctness` 区分 name 前缀
- LangFuse 不可用时评分仍正常，只是不回写 score
- 已有 eval cases 通过率不退化

### Step 4：文档收尾 + smoke 脚本 + AI_CONTEXT 更新

**目标**：更新技术档案 + 编写一键验证脚本，确保下一轮 AI 会话能正确继承。

**改动文件**：

1. `docs/AI_CONTEXT.md`：
   - 「当前状态」section：
     - 当前阶段指针从 `phase3a-plan.md` → `phase3b-langfuse-plan-v2.md`
     - 当前模块更新为 Phase 3B
     - 下一模块更新为 Phase 3 RAG/Hybrid
   - 「当前技术选型快照」section：Trace/Eval 条目补充 LangFuse（自部署、版本、端口 3000）、评分分层（L1/L2/L3）、Experiment 最小验证结论
   - 「最新事实快照」section：
     - 新增 LangFuse 默认值：`LANGFUSE_ENABLED=false`、`LANGFUSE_HOST=http://localhost:3000`、降级行为（不可用时自动跳过，不影响 JSONL）
   - 「已知的坑」section：新增
     - Docker 资源占用（LangFuse + PostgreSQL ~1-2GB 内存）
     - LangFuse SDK Python 版本兼容性
     - PostgreSQL 数据膨胀清理策略（30 天自动清理配置）

2. `docs/AI_CONTEXT_CHANGELOG.md`：
   - 记录本阶段的改动范围、关键决策、验收结果

3. `.agent_work/temp/phase3b-notes.md`（开发中记录）：
   - Docker 启动命令、初始账号密码、内置评估器调研结论、常见问题等

4. `scripts/smoke_phase3b_langfuse.py`（新文件）：
   - 检查 Docker 状态（LangFuse + PostgreSQL 容器是否 running）
   - 发一条 `/api/query` 请求
   - 调 LangFuse API 确认 trace 已写入
   - 调 LangFuse Score API 写入一条评分
   - 输出 PASS / FAIL（每个检查点一行）

### Step 5：最小 Experiment 走通（手动，不要求自动化）

**目标**：在 LangFuse Web UI 中手动跑通一次完整的 Experiment 流程（trace → dataset → experiment run → 结果对比），记录 UX 体验、API 能力边界和是否满足 agent-eval-ops 需求。

**操作要点**：

- 从 Step 2-4 已收集的 LangFuse trace 中手动创建 Dataset（选 5 条 formal case 的 trace）
- 切换 LLM 配置（如 DeepSeek → Qwen），重新跑这 5 条 case，产出一批新 trace
- 在 LangFuse Web UI 中创建 Experiment，对比两组 run 的 score
- 记录：UX 体验、Experiment 粒度是否满足需求、有无 blocking issue、API 能力边界

**验收**：
- LangFuse Web UI 中能看到一次 Experiment，包含两组 run 的 score 对比
- `.agent_work/temp/phase3b-notes.md` 中记录 Experiment 走通结论，至少覆盖：
  - Experiment UX 评价（好用/能用/不好用）
  - 是否满足 agent-eval-ops 需求（是/否/部分，为什么）
  - 发现的能力边界或坑

---

## 与独立评测项目（agent-eval-ops）的关系

Phase 3B 是 agent-eval-ops 的**前置探路阶段**。验证的核心问题：

| 问题 | 本阶段如何验证 |
|------|---------------|
| LangFuse API 是否稳定？ | 从 DataPilot 写入 trace + score，观察延迟和丢失率 |
| 自部署运维成本多高？ | 记录 Docker 资源占用、数据增长速率、备份需求 |
| L1 规则评分是否完整？ | 对照 eval/run_eval.py 现有评分类型，确认全部映射到 scorer |
| LLM-as-Judge 评分质量如何？ | 人工抽查 10-20 条 L3 judge 结果，统计与人工判断的一致性 |
| LangFuse SDK 是否好用？ | 实际写代码体验 `langfuse` Python SDK 的 API 设计和文档质量 |
| LangFuse 内置评估器是否够用？ | Step 3-0 调研结论直接回答 |
| Experiment 功能是否满足需求？ | Step 5 手动跑通一次完整闭环，记录 UX 和能力边界 |

本阶段验证通过后，agent-eval-ops 可以直接复用以下资产：
- LangFuse Docker 部署方案（docker-compose.yml）
- `engine/trace/langfuse_backend.py` 的 TraceRecord → LangFuse 映射逻辑
- `eval/scorers/` 的评分器实现
- `.env` 配置模板

---

## 风险与降级策略

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Docker 在本机不可用或性能差 | 低 | 阻塞 Step 1 | 用 LangFuse Cloud 免费层临时替代（但需考虑国内网络）；或先只做代码抽象，Docker 部署留到 agent-eval-ops |
| LangFuse SDK 与旧 Python 版本不兼容 | 中 | 阻塞 Step 2 | 确认 Python 3.10+ 兼容性后再 `pip install`；不兼容则降级为仅抽象接口，暂不接入真实 LangFuse |
| LLM-as-Judge 评分太慢/太贵 | 高 | 影响 Step 3b 实用性 | 默认不启用；只在少数 diagnostic case 上用；judge 用便宜的模型（如 DeepSeek-V3）而非旗舰模型；优先复用 LangFuse 内置评估器 |
| LangFuse 数据库膨胀 | 中 | 长期运行后磁盘满 | 设置 PostgreSQL 数据保留策略；trace 数据 30 天自动清理 |
| LangFuse 服务挂了 | 低 | trace 丢失 | JSONL 始终作为第一优先级写入；LangFuse 是"追加"不是"替代" |

---

## 单一事实源

- 阶段三B 执行计划：以 `docs/phase3b-langfuse-plan-v2.md` 为准
- 阶段三B 原始版本（v1）：以 `docs/archive-versions/phase3b-langfuse-plan-v1.md` 为存档
- 阶段三A 执行计划：以 `docs/phase3a-plan.md` 为参考（已完成）
- 数据库当前事实：以 `docs/database-current-state.md` 为准
- 项目技术档案：以 `docs/AI_CONTEXT.md` 为准
- LangFuse 官方文档：https://langfuse.com/docs
- LangFuse 自部署指南：https://langfuse.com/docs/deployment/self-host

---

## 架构底线

### P0：不可降级

| 约束 | 验证方式 |
|------|---------|
| `/api/query` 响应契约不变 | `tests/` 全部通过，AgentResponse 字段不增不减 |
| JSONL trace 始终可写，不因 LangFuse 挂了而丢 trace | 手动停掉 Docker → 调 API → 检查 `eval/traces/traces.jsonl` 有新行 |
| `append_trace()` / `_record_trace()` 调用方代码不改 | `rg "append_trace\(" app/` 只出现在 recorder.py 内部，外部调用方已切换到 `trace_router.record()` |
| 现有规则评分 (contains/equals/expected_value/result_match) 行为不退化 | `python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml` 通过率不退化 |
| L1/L2 评分器默认启用，不因未传 `--judge-model` 而跳过 | `python -m eval.run_eval --cases ...` 跑完后 trace 上能看到 `rule:table_hit`、`rule:expected_value` 等 L1/L2 score |
| 不因本阶段引入新的必须依赖 | `pip install langfuse` 是可选的（`LANGFUSE_ENABLED=false` 时不需要，但 `LANGFUSE_ENABLED=true` 时是运行时依赖） |
| smoke 脚本可一键验证全链路 | `python scripts/smoke_phase3b_langfuse.py` 输出 5 行 PASS

### P1：可简化，接口保留

| 简化方案 | 预留接口/字段 | 后续何时补 |
|----------|-------------|-----------|
| LangFuse Span 先不完美映射 TraceStep 的嵌套关系 | `TraceStep.parent_step_id` 保留 | RAG/Hybrid 阶段 pipeline 变复杂后补 DAG 化 span |
| L3 Hallucination/Faithfulness 可能直接复用 LangFuse 内置评估器 | 自定义 prompt 模板作为 fallback | Step 3-0 调研后决定 |
| 评分结果回写 LangFuse Score 先走同步调用 | 预留 `async_score()` 方法签名 | 如果评分数量上到 50+ 条且延迟显著，再补异步批量写入 |
| Experiment 只做手动验证，不做 API 自动化 | 实验结论记录在 phase3b-notes.md | agent-eval-ops 项目启动后补 Experiment SDK 自动化 |

---

## 后续衔接

Phase 3B 完成后，后续阶段的受益：

- **Phase 3 RAG（检索增强生成）**：LangFuse 上看 retrieval span → generation span 的全链路；L1/L2/L3 评分器已就绪，RAG 专用评分器（faithfulness、context_relevancy）可直接启用。⚠️ 同行踩坑预警：retrieval recall 评测时，开源数据集的 reference text 和自己切片后的 chunk 粒度不一致，容易误判 miss。Phase 3 RAG 应设计 **coverage 指标**（将 reference 按句子拆分，计算 chunk 对 reference 的覆盖度）作为 L1 规则评分器，不做 LLM judge
- **Phase 3 Hybrid（混合推理）**：多步 Agent 的每一步都是独立 span，debug 时不用翻 JSONL
- **agent-eval-ops（独立评测平台）**：直接复用 LangFuse 部署 + Trace Backend 抽象 + Scorer 模块 + Experiment 结论，从"搭建基础设施"变成"构建评测方法论"

---

## 修订记录

### v2.1（2026-07-28）—— 同行踩坑补丁

依据：[该员工的第二段评论](#)（trace 异步上传、LLM judge 不稳定、retrieval recall chunk 不匹配）

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
| 新增 Step 5：最小 Experiment 走通（手动 A/B） | 不再把 Experiment 完全推到 agent-eval-ops |
| 实施步骤从 4 步扩展为 5 步 | — |
| 新增 smoke 脚本（`scripts/smoke_phase3b_langfuse.py`） | 一键验证全链路 |
| 扩充 AI_CONTEXT 更新清单 | 当前阶段指针、LangFuse 默认值、新坑登记 |
| 新增「已知限制」章节 | cost 扁平映射等暂不实现项 |

### v1（2026-07-27）—— 初版

依据：上轮对话中对自研方案 vs LangFuse vs LangSmith 的对比分析结论，以及用户决定新增 Phase 3B。

原始文件：[docs/archive-versions/phase3b-langfuse-plan-v1.md]
