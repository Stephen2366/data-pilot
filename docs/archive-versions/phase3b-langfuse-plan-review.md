# Phase 3B LangFuse Plan 评审

> 评审对象：[docs/phase3b-langfuse-plan.md](phase3b-langfuse-plan.md)
> 评审日期：2026-07-27

## 一、那位员工的方案是否合理

**完全合理，是行业主流做法。** 他描述的是一套标准的 trace-based evaluation 工作流：

```
业务埋点 → Trace（含 span 详情）→ LangFuse 聚合 → Experiment 对比
                ↓                            ↓
        规则指标（recall / MRR）      LLM-as-Judge 指标（correctness / hallucination）
        直接从 trace 结构字段计算        调外部大模型做裁判
```

核心洞察有两点：

1. **并非所有指标都需要 LLM 裁判** —— recall、MRR 等可以直接从 trace 的 span metadata 中算出来，成本为零、速度极快。
2. **LangFuse 同时承担 trace 存储和评测平台两个角色** —— trace → dataset → experiment 形成同一平台内的闭环，不需要在多个系统间搬运数据。

对你两个项目的参考价值：

- **DataPilot**：当前 JSONL trace + 规则评分刚好够用，LangFuse 的价值在于后续 RAG / Hybrid 阶段的**可视化 debug**和**LLM-as-Judge 语义评分**。不需要急着切，但 Phase 3B 作为探路阶段是合理的。
- **agent-eval-ops**：那位员工的方案可以直接作为参考架构——以 LangFuse 为基座，上面搭建评测方法论（case 管理、scorer 注册、experiment 对比），省去自建 trace 存储、可视化、评分回写等 6-8 周基建工作量。

---

## 二、Plan 整体评价

**整体框架合理**，亮点：

- TraceBackend 协议抽象设计清晰，JSONL + LangFuse 双写模式兼顾稳定性和可观测性
- 降级策略务实：LangFuse 不可用时自动降级，JSONL 始终为第一优先级
- "非目标"列表明确，有效防止范围蔓延
- 分步实施节奏合理，每步有清晰的验收标准

但 plan 存在一个**核心偏差**——忽略了那位员工方案中"从 trace 字段直接计算规则指标"这条腿，过度聚焦 LLM-as-Judge。以下按优先级列出需要优化的点。

---

## 三、需要优化的点（按优先级）

### P0 — 缺失"从 trace 结构字段计算规则指标"

**问题**：那位员工说的关键点是"一部分指标调大模型，一部分直接从 trace 埋点算"。DataPilot 的 `TraceRecord` 已有丰富的结构化字段（`tables_used`、`columns`、`rows`、`safety_status`、`trace_steps`、`cost.latency_ms`），且 [eval/run_eval.py](eval/run_eval.py) 已经实现了大量规则评分逻辑（`expected_tables` 命中、`expected_value` 数值校验、`result_match` 结果对比、安全 compliance）。但 plan 的 Step 3 只设计了三个 LLM-as-Judge 评分器，完全没有提及规则评分器，相当于忽略了现有评分资产和 trace 结构化数据的价值。

**优化方案**：将 Step 3 拆为两个子步骤——

- **Step 3a：规则评分器**（从 trace 结构化字段计算，**不调 LLM**，零成本）
  - `expected_tables` 命中率 ← `tables_used`
  - `expected_columns` 召回率 ← `columns`
  - `result_match`（执行 expected_sql 对照实际 rows）← 已有逻辑
  - SQL 执行成败 ← `error_type`
  - 安全合规 ← `safety_status`
  - 延迟 ← `cost.latency_ms`
  - Schema 检索命中 ← `trace_steps[].metadata`
  - 以上结果统一通过 LangFuse Score API 写入对应 trace
- **Step 3b：LLM-as-Judge 评分器**（调外部模型，仅在 `--judge-model` 显式指定时启用）
  - Answer Correctness（语义等价判断）
  - Hallucination（事实是否超出 rows / docs）
  - Faithfulness（回答是否忠实于检索文档，RAG 预留）

---

### P0 — Experiment 完全不验证，与"探路"目标矛盾

**问题**：那位员工说的"在 langfuse 触发 experiment"是他整个工作流的核心环节。Plan 把 Experiment 列在"明确不做"并完全推到 agent-eval-ops，但 Phase 3B 的核心目标之一是"为 agent-eval-ops 探路"——如果连 Experiment 的最基本流程都没验证过，怎么知道它是否满足 agent-eval-ops 的需求？

**优化方案**：不要写"不做 Experiment"，改成"做一个最小 Experiment 验证"作为 Step 4 的子任务：

- 手动在 LangFuse Web UI 中从已收集的 trace 创建 Dataset
- 跑一次最小 A/B（如 DeepSeek vs Qwen，选 5 条 case），观察 Experiment 结果展示
- 记录：UX 体验、API 能力边界、是否满足 agent-eval-ops 预期、有无 blocking issue
- 不要求自动化，只要求"跑通 + 有结论"

---

### P1 — 评分器设计中"规则 vs LLM"的边界不清晰

**问题**：Plan 的评分器设计表把 Answer Correctness 定义为"LLM 判断回答是否与期望一致"，但实际上 DataPilot 已有 `result_match`（执行 expected_sql 对照实际结果），这在数值/行集对比场景比 LLM 裁判更可靠、更快、更便宜。边界不清晰容易导致 LLM-as-Judge 被滥用，成本失控。

**优化方案**：在 scorer 设计中显式分层：

| 层级 | 评分方式 | 适用指标 | 成本 |
|------|---------|---------|------|
| L1 结构规则 | 从 trace 字段直接判定 | tables/columns 命中、安全合规、SQL 执行成败 | 零 |
| L2 结果规则 | expected_sql 对照（已有 `result_match`） | answer correctness（数值/行集精确对比） | 极低 |
| L3 LLM 裁判 | 调外部模型 | hallucination、faithfulness、语义等价判断 | 高 |

分层原则：能用 L1 不用 L2，能用 L2 不用 L3。L3 只在 `--judge-model` 显式开启时才执行。

---

### P1 — 未调研 LangFuse 内置评估器

**问题**：那位员工明确提到"langfuse 也有一些内置评估器可以直接用，需要自己配置外部模型"。LangFuse 内置了 hallucination、answer-relevance、context-precision 等评估器，只需配置 judge 模型即可使用。Plan 的 `eval/scorers/` 全部从零写，没提先调研已有能力。

**优化方案**：Step 3 开头加一步："先调研并跑通 LangFuse 内置评估器（至少覆盖 hallucination / answer-relevance），确认可用性和评分质量；再决定哪些直接复用、哪些需要自定义实现。"这也能和 agent-eval-ops 形成分工——通用评估器复用 LangFuse 内置 + DataPilot 自定义 scorer。

---

### P2 —  trace → span 的 `cost` 映射不应是扁平的

**问题**：Plan 的映射表把 `cost.prompt_tokens/completion_tokens` 映射到"generation.usage（如有 LLM generation span）"。但 DataPilot 的 pipeline 中有多次 LLM 调用（embedding、query_plan 生成、sql_generation），每次消耗不同。当前 `CostInfo` 是一次请求的总 token 数，无法拆分到每个 span。

**优化方案**：在 `TraceStep.metadata` 中增加每次 LLM 调用的 `prompt_tokens` 和 `completion_tokens`，LangFuseBackend 在每个 generation 类型的 span 上独立设置 usage。不必一步到位完美覆盖所有 LLM 调用点，先打基础，后续逐步补全。目标是后续能做"哪个环节最费 token"的 cost 归因。

---

### P3 — 缺少 smoke 脚本

**问题**：Phase 3A 有 `scripts/smoke_phase3a_text2sql.py` 一键验证全链路。Phase 3B plan 完全没有对应的 smoke 脚本，验收依赖手动检查，续接时其他 AI 不知道"怎么验证这阶段是跑通的"。

**优化方案**：新增 `scripts/smoke_phase3b_langfuse.py`，最小路径：

1. 检查 Docker 状态（LangFuse 是否 running）
2. 发一条 `/api/query` 请求
3. 调 LangFuse API 确认 trace 已写入
4. 调 LangFuse Score API 写入一条评分
5. 输出 PASS / FAIL

---

### P3 — AI_CONTEXT 更新范围不完整

**问题**：Phase 3B 是一个新阶段的起点（不是 Phase 3A 的子模块），`AI_CONTEXT.md` 需要更新的内容比 plan 列出的多。

**优化方案**：Step 4 的 AI_CONTEXT 更新至少覆盖：

- 「当前状态」的当前阶段指针从 `phase3a-plan.md` → `phase3b-langfuse-plan.md`
- 「当前技术选型快照」补充 LangFuse（自部署、版本、端口）
- 「最新事实快照」补充 LangFuse 默认值（`LANGFUSE_ENABLED=false`、host、降级行为）
- 「已知的坑」登记新坑：Docker 资源占用、LangFuse SDK Python 版本兼容性、数据膨胀清理策略

---

## 四、总结

| 优先级 | 问题 | 影响 |
|--------|------|------|
| 🔴 P0 | 缺失规则评分器（从 trace 字段计算），浪费已有结构化 trace 数据 | 评分体系不完整，只有 LLM 裁判一条腿 |
| 🔴 P0 | Experiment 完全不验证，与"为 agent-eval-ops 探路"的核心目标矛盾 | 探路结论缺乏最关键环节的证据 |
| 🟡 P1 | 规则 vs LLM 评分边界模糊，Answer Correctness 定位有偏差 | 容易滥用 LLM-as-Judge，成本失控 |
| 🟡 P1 | 未调研 LangFuse 内置评估器就全部自研 | 可能重复造轮子，也失去学习内置方案的机会 |
| 🟢 P2 | cost 映射是扁平的，无法按 span 做 token 归因 | 后续 cost 优化缺少数据支撑 |
| 🟢 P3 | 缺 smoke 脚本 | 验收无抓手，续接效率低 |
| 🟢 P3 | AI_CONTEXT 更新范围不完整 | 下一轮 AI 会话可能拿到过期信息 |

整体来看，plan 的架构方向正确，主要偏差在于**过度聚焦 LLM-as-Judge 而忽略了规则评分的价值**，以及**对 Experiment 的过度保守**。修正这两个 P0 点后即可进入实施。
