# Phase 4 Agent / RAG 能力现状、工程债与后续演进

> **用途**：面向 Phase 4 收尾后的 Agent / RAG 工程演进，统一说明当前真实能力、未兑现的 roadmap 主线、条件能力、Phase 4 后能力，以及后续推进与验收顺序。本文不替代当前事实源：运行与边界以 [`AI_CONTEXT.md`](../state/AI_CONTEXT.md) 为准，RAG 运行口径以 [`rag-current-state.md`](../state/rag-current-state.md) 为准，评测数字和可比性以 [`eval-baselines.md`](../state/eval-baselines.md) 为准，Phase 4 原始目标与决策门以 [`phase4-roadmap.md`](../phase4-roadmap.md) 为准。
>
> **一句话结论**：DataPilot 已经完成 Phase 4 的主要工程闭环，并形成了可信 Tool、ACL、typed Evidence / citation、四轴状态、Trace、Eval、Hybrid 与受控 thread 等较强地基；P4 已通过最小 bounded recovery / thread state 切片达到阶段验收基线，但通用 Context Builder 与面向未来动态 Loop 的 Action / Budget / Progress 控制仍值得继续 hardening；P6 则按既定决策门合法得到 `no_go`，因此“没有 RAG Subgraph”不是 Phase 4 未完成。M40 之后应在**路线层面并行、施工层面交错切片**推进 **RAG 质量与动作证据**、**顶层 Agent foundation**，再基于证据决定是否实现 bounded Agentic RAG，并逐步升级到任务级自然多轮。

阅读本文时，必须先区分四个容易混淆的概念：

- **当前已经存在最小的 bounded Agent recovery loop，但还没有 autonomous in-run Agent Loop**：澄清后 resume 与一次 follow-up 已形成跨 turn 的受控恢复闭环；但同一次 Graph invoke 内还不会读取 Tool Observation 后自主选择下一动作并再次调用 Tool。
- **保存了 thread，不等于有通用记忆**：当前 checkpoint 是短期任务恢复状态，不是聊天历史、用户画像或跨会话记忆库。
- **能够澄清和追问，不等于自然多轮对话**：当前多轮能力仍是模板化、closed-world、次数受限的任务恢复/追问，不具备通用自由文本 Task Delta 理解。
- **有 RAG Tool，不等于 Agentic RAG**：当前 RAG 默认仍是确定性 Pipeline；P6 已完成 go/no-go 审查，但尚无由 Observation 驱动的 query rewrite、上下文扩展、子问题检索等多步再取证 Subgraph。

---

## 1. Phase 4 应怎样判断“完成”

### 1.1 Roadmap 原始能力分层

Phase 4 roadmap 并没有要求所有设想都必须在阶段内实现，也不能把“已经按最小切片验收”与“仍值得继续泛化”混成同一种 debt。更准确的分层如下：

| 类型 | 定义 | 典型能力 | 当前判断 |
|---|---|---|---|
| **Roadmap 主线（已收口 / 最小切片）** | Phase 4 主干明确要求交付，并允许通过最小可验收切片满足 Gate | P4 clarification recovery + 短期 thread state、P5 Hybrid、P7 assurance | 已达到 Phase 4 验收口径；其中 P4 是 bounded 最小切片，不等于通用多轮或动态 Loop 已完成 |
| **P4-aligned hardening / 当前工程债** | roadmap 的控制权原则已经明确，但当前实现仍缺通用化或面向动态 Loop 的 first-class 表达；继续收口有助于后续能力，而不推翻既有验收 | 通用 node-level Context Builder；面向动态 Loop 的 Action / Budget / Progress contract | 建议优先 hardening；这是“阶段完成后的工程债/控制面补强”，不是“Phase 4 验收不合格” |
| **条件能力 / conditional capability** | 必须完成决策门或安全前置条件，但只有出现合格 Evidence / 条件满足时才实现或启用 | P6 bounded RAG Subgraph；LangFuse Cloud 显式恢复 | P6 已完成决策门且为 `no_go`；Cloud observability 继续默认关闭，满足安全条件后才可启用 |
| **Phase 4 后能力 / post-Phase-4 enhancement** | roadmap 明确不要求当前阶段完成，或应由新 Scenario 重新立项 | 跨会话长期记忆、开放 ReAct、多 Agent、复杂 context compact、生产 SSO/OAuth/JWT | 当前未实现，不应反向算作 Phase 4 debt |

因此，“Phase 4 已完成”应理解为：**既定主线已经按允许的最小切片、决策门与 P7 technical assurance 收口；后续 hardening 与能力泛化用于支撑更强 Agent，而不是重新判定 Phase 4 是否完成。**

还未正式开发 phase 4 时，对于 roadmap 的预期如下表（仅供参考）：

| 概念                  | 体现程度       | 当前方案中的体现                                             |
| --------------------- | -------------- | ------------------------------------------------------------ |
| Harness Engineering   | 核心主线       | LangGraph 统一管理状态、Tool 调度、预算、失败恢复、停止条件、Trace 和 Eval。 |
| Agent Loop / 循环设计 | 核心主线       | `Action → Observation → Evidence Gate → Next Action`，循环有预算、reason code 和明确终止条件。 |
| Tool Use / 工具调用   | 核心主线       | Text2SQL 和 Knowledge/RAG 作为两个独立 Tool，成功返回 typed Evidence，失败返回结构化错误。 |
| 工具调用失败处理      | 核心主线       | 区分可恢复、不可恢复、权限拒绝和外部服务不可用；对应有限重试、澄清、partial 或停止。 |
| Agent 编排            | 核心主线       | LangGraph 负责 SQL、RAG、Hybrid 路由、分支汇合、Evidence 检查和最终状态。 |
| Agentic RAG           | 中等，条件增强 | RAG 首先使用确定性 Pipeline；中后期若 Eval 证明需要，再加入有界 LangGraph RAG Subgraph。 |
| ReAct                 | 受控体现       | 采用“动作—观察—再决策”的思想，但不做开放式、无限自主研究。   |
| Memory                | 有限体现       | 主要建设同一 thread 内的任务状态和短期记忆，不建设通用记忆平台。 |
| 短期记忆机制          | 主线能力       | 保存已确认条件、指代关系、任务状态、安全摘要和有效 Evidence reference。 |
| 长期记忆机制          | Phase 4 后考虑 | 不在主线建设跨会话用户画像、偏好和长期历史召回。             |
| 长期对话记忆召回      | 暂不建设       | 需要额外处理过期、纠错、删除、权限变化和隐私问题，阶段四结束后再决定。 |
| 多轮对话              | 有限支持       | 支持澄清后恢复任务，以及基于上一轮结果的有限追问；不是通用聊天机器人。 |
| 上下文管理            | 核心主线       | State 保存运行事实，Context Builder 只向当前节点提供最小必要上下文。 |
| Context Compact       | 基础版         | 首版主要裁剪无关历史、保留条件和 Evidence reference；复杂自动摘要和多层压缩后置。 |
| 长上下文治理          | 部分体现       | 区分候选 Evidence、选中 Evidence、进入模型的 Evidence 和最终引用 Evidence；高级压缩后置。 |
| 测评效果              | 核心主线       | 使用固定 corpus、Scenario、typed assertion 和同题一次执行，分别评 route、retrieval、citation、answer、Hybrid、安全和循环。 |

总体上可以概括为：

- **重点做深**：Harness、LangGraph 编排、有界循环、Tool Use、失败恢复、Evidence、上下文管理和 Eval。
- **有限实现**：多轮对话、短期记忆、ReAct 和 Agentic RAG。
- **后续补强**：长期记忆、跨会话召回、复杂 context compact、开放式 ReAct 和多 Agent。

### 1.2 M40 结束时的概念体现程度

| 概念 | 体现程度 | 当前实现 | 明确边界 |
|---|---|---|---|
| Harness engineering | 很强 | 顶层 LangGraph Harness 已统一 SQL / RAG / Hybrid 路由、状态、终止、Trace 和 API 投影。SQL/RAG 单路各至多一个深 Tool；Hybrid 固定两支各一次。 | 当前强项是控制面、typed contract 和失败关闭，不是开放自治规划。 |
| Agent loop | **最小 bounded recovery 已形成；autonomous in-run loop 未实现** | 条件澄清可以跨 turn resume；成功 SQL/RAG 后支持一次受控 follow-up；每个 accepted turn 都重新经过 Graph、权限与生命周期检查。 | 尚无“读取本次 Tool Observation → 动态选择允许动作 → 同次运行再次调用 Tool → 按 Evidence progress 停止”的循环边。 |
| Tool use | 很强 | SQL 与 Knowledge/RAG 均作为受控 deep Tool；成功返回 typed Evidence，失败返回结构化状态；最终答案、citation 与 Trace 消费同次运行事实。 | 不提供任意 Python/Shell、写库或其他副作用 Tool。 |
| Agentic RAG | 条件能力，当前未实现 | M39 已完成 P6 入场审查，历史结论为 `no_go`。 | 没有多步 query rewrite、子问题检索、Observation-driven expansion 或 RAG Subgraph。 |
| 循环设计 | 合同较强，运行能力仍窄 | 已有 reason code、允许状态、无进展停止、Evidence 生命周期与禁止双循环等原则。 | 当前调用上限主要由固定拓扑和 follow-up 次数结构性限制，并不存在供动态 Agent 持续消费的统一 Budget Ledger。 |
| 短期任务状态 | 窄范围已实现 | 进程内 versioned checkpoint 支持 pending clarification、resume/clear、一次 follow-up，并处理 owner、TTL、版本与旧状态冲突。 | 不保存完整消息历史、旧 answer、SQL rows、文档正文或 citation；重启与多 worker 不共享。 |
| 多轮对话 | 窄范围已实现 | 支持结构化澄清恢复与一次 closed-world follow-up。 | 不支持自由连续追问、Hybrid follow-up、自然语言 Task Delta、跨 route 持续推进或跨会话连续任务。 |
| 上下文管理 | Evidence 上下文较强；对话上下文仍是初级 | 已区分候选 Evidence、授权/选择、generation-visible Evidence 与 citation；thread 侧按最小字段重建问题。 | 仍缺 roadmap 意义上的通用 node-level Context Builder、可 Eval 的节点输入投影与 token budget 治理。 |
| Context compact | 未实现 | 尚无自动摘要、滚动压缩或长历史 compact。 | 这属于长会话 Scenario 驱动的后续能力，不应为了名词提前建设。 |
| Agent 编排 | 很强，但目前是固定工作流 | 典型单路为 `route → tool → controller`，Hybrid 为双 Evidence 分支后汇合。 | Router 仍偏 closed-world；没有基于 Observation 的开放式动态计划。 |
| ReAct | 主动不采用开放式版本 | 保留结构化 Action / Observation / Evidence Gate / reason code，方便审计与 Eval。 | 不保存模型原始思维链，也不做无限 Thought → Action → Observation 研究循环。 |
| 工具失败处理 | 确定性失败关闭很强；自动恢复较弱 | `blocked`、`external_unavailable`、`no_answer`、`partial` 等状态有明确投影；权限与生命周期拒绝可在 Tool 前停止。 | 大多数失败目前是安全停止或等待下一 turn，不会自动根据失败类型执行 fallback / retry / retrieval recovery。 |

### 1.3 当前最值得优先收口的 P4-aligned hardening

P6 `no_go` 不应算作技术债；M36+M37 已通过 roadmap 允许的最小恢复切片完成 P4 基线，因此下面两项 hardening **不等于 Phase 4 验收不合格**：

1. **通用 Context Builder**：当前只有围绕 clarification / follow-up 的最小模板或字段重建，还不是“按 Router、SQL、RAG、Controller、Composer 等节点投影最小必要上下文”的统一组件；也缺少对实际入模内容的系统级 Eval。
2. **面向动态 Loop 的 first-class Action / Budget / Progress contract**：当前 Tool 调用次数主要由固定 DAG 拓扑天然限制，follow-up 有局部预算，足以支撑现有 bounded flow；但未来如果引入 Observation-driven next action，仍需要统一表达 allowed action、预算消费、Evidence delta、no-progress 与 termination。具体是否实现为单一 Ledger，不在本文提前冻结。

### 1.4 主线延伸增强：重要，但不是 Phase 4 未兑现债务

以下能力值得在下一阶段建设，但更准确地说是**从已验收最小切片继续泛化**：

1. **通用 TaskState**：当前 typed thread/checkpoint 足以完成受控 resume / follow-up；后续可进一步稳定表达 task goal、confirmed constraints、pending questions、route、EvidenceRef、freshness、预算与 termination 等任务事实。
2. **更多顶层 bounded recovery**：当前 clarification recovery 已满足最小 G5；后续可从 Evidence 失效重取证、跨 Tool 补 Evidence、结构化失败后的安全 fallback 中选择真实 Scenario 做第二个切片。

---

## 2. 目前的 RAG 效果：应怎样理解

### 2.1 已经可以肯定的工程能力

- 知识发布、revision、ACL、typed Evidence、citation、AnswerFlow、Harness、Trace 与 Eval 已形成完整工程链路。
- external EnterpriseRAG-Bench 与 business release 保持隔离，不能把外部 benchmark 指标直接当成业务 Runtime 的实际效果。
- external 当前默认 lexical，而不是 semantic candidate；semantic candidate 在同一 dev / held-out 切分上没有证明净收益，因此没有为了“语义检索”标签切默认。
- M40 rehearsal 已覆盖 SQL、RAG、Hybrid、澄清恢复和安全拒绝等核心路径，主要证明 response / Trace / Evidence / citation / lifecycle 的合同一致性，而不是证明开放世界问答已经达到生产质量。

### 2.2 当前外部 benchmark 基线

下列数字只用于 external benchmark 内部比较，不与业务 22 条知识回归或 Text2SQL Eval 混算：

| 层次 | 当前结果 | 不能推出什么 |
|---|---|---|
| lexical retrieval（held-out，@20） | gold coverage `82.31%`；all-gold `77.50%`；MRR `0.723` | 召回到 gold，不等于答案正确。 |
| semantic candidate（held-out，@20） | gold coverage `77.40%`；all-gold `74.17%`；MRR `0.630` | 不能因为使用 embedding 就默认优于 lexical。 |
| Answer / Citation（180 题） | `146/180` complete；all-gold cited `80/180`（44.44%） | `complete` 只表示回答、support、citation 合同闭合，不等于自然语言答案正确。 |
| 难题切片 | multi-document all-gold `2/38`（5.26%）；semantic all-gold `15/52`（28.85%） | 当前不宜宣传为强多文档或强语义 RAG。 |

当前主要失败簇仍包括 lexical 漏召回、selected/context packing 不足、Composer 严格 support 合同拒绝等。M39 没有证明“第一次 Observation 后自动追加一个动作”可以稳定新增有效 Evidence，也缺少公平的额外预算对照，因此当时不建设 RAG Subgraph 是符合 roadmap 的决策，不是遗漏开发。

但 `no_go` 不能被扩大解释为“Agentic RAG 永远无价值”。现有历史 artifact 主要记录单次 Pipeline 结果，本来就没有系统执行过相邻上下文扩展、受控 query rewrite、独立证据需求拆分等候选动作，因此下一阶段如果要重开 P6，必须先产生新的动作级 diagnostic Evidence。

### 2.3 多文档问题要改为 funnel 诊断，而不是直接归因给 packing

`multi-document all-gold cited = 5.26%` 是最终漏斗结果，可能同时受到 retrieval、selection/packing、generation-visible context、Composer 与 citation 的影响。不能仅凭这个数字断言“主要问题就是 packing”。

后续应增加最少一条 multi-document funnel，并明确区分 Evidence 生命周期与 Composer 诊断：

```text
retrieved all-gold
  → selected all-gold
  → generation-visible all-gold
  → [Composer / support outcome]
  → cited all-gold
```

其中 `retrieved / selected / generation-visible / cited` 仍映射既有 Evidence 生命周期；`Composer / support outcome` 是回答侧诊断层，用于记录 support pass/reject 或 supported claims，**不新增第五个 EvidenceLedger stage**，而且失败样本同样需要记录该诊断。只有这样才能回答：问题究竟死在召回、装配、生成 support，还是 citation；也才能判断应继续增强确定性 Pipeline，还是确实需要 Observation-driven recovery action。

---

## 3. 当前未实现能力：按性质分类，而不是放在一张“待办表”里

### 3.1 P4-aligned hardening：建议优先收口

| 能力 | 当前缺口 | 建议推进方式 |
|---|---|---|
| 通用 Context Builder | 目前只有受控 clarification / follow-up 最小重建，没有统一 node projection 与可直接 Eval 的入模合同 | 为 Router / SQL / RAG / Controller / Composer 定义 typed context projection；保留 Evidence identity 与高风险原始 reference |
| Dynamic-loop Action / Budget / Progress contract | 当前 bounded 调用上限主要来自固定拓扑和局部 follow-up budget；没有供未来 Observation-driven action 统一消费的 action/budget/progress 表达 | 建立 typed action、budget consumption、Evidence delta、no-progress、termination contract；是否合并为单一 Ledger 留到对应 module plan 决定 |

**主线延伸增强（不作为 Phase 4 debt）**：通用 TaskState、第二个顶层 bounded recovery Scenario。它们用于把现有最小 recovery/thread 能力升级为更自然的任务级 Agent，但不应反向否定 P4 已通过的最小验收。

### 3.2 Conditional capability：有证据才实现

| 能力 | 当前状态 | 重新进入条件 |
|---|---|---|
| 多步 Agentic RAG / RAG Subgraph | M39 决策为 `no_go`，当前未实现 | diagnostic/dev 上证明至少一种 Observation-driven recovery action 能正确触发并新增有效 Evidence；再冻结可比较 held-out 与预算 |
| query rewrite / 子问题拆分 | 尚无稳定失败簇证明其必要性 | 证明问题表达或证据需求分解是独立主因，并有动作级收益假设 |
| parent/child、相邻上下文扩展、rerank、hybrid retrieval | 均可作为确定性 Pipeline 或动作候选实验 | 每项单变量 A/B；不能一起上线后再解释收益 |
| 开放 Router / remote Synthesizer | 当前 closed-world baseline 更容易验证 | 开放问法形成稳定失败簇，并完成 outbound、held-out、预算和授权合同 |
| LangFuse Cloud 显式恢复 | 当前默认关闭，JSONL Trace 仍是本地事实源 | 仅在上传 allowlist、脱敏、data classification、旁路失败降级与 outbound security case 通过后显式启用；不得成为唯一 Trace/Eval 事实源 |

### 3.3 Phase 4 后能力：不要误当当前债务

- 自动长历史 context compact / 多层摘要；
- 跨会话长期记忆、用户画像和历史召回；
- 持久分布式 checkpoint（除非重启恢复 / 多 worker 已成为 required Scenario）；
- 开放 ReAct、研究型 Agent、多 Agent；
- 生产 SSO/OAuth/JWT、真实企业 connector；
- 任意 Python/Shell 或写操作类副作用 Tool。

这些能力必须由真实 Scenario 和安全/Eval 证据重新立项，不应为了简历关键词直接加入默认路径。

---

## 4. M40 之后的优先级：两条主线并行，而不是串行等待

原先“先 RAG 质量 → 再 Agentic RAG → 最后 TaskState / 多轮”的顺序容易导致顶层 Agent 地基过晚建设。更合理的方式是从 M41 起在**路线层面并行、施工层面交错切片**推进两条主线：A/B 都可以持续演进，但同一时间只为当前最小可验收切片建立一个 active module plan。

### P0-A：RAG 质量、失败 funnel 与动作证据

1. **建立 Answer correctness / faithfulness / support / completeness 的清晰基线**：不能继续用 `complete`、retrieval coverage 或 citation 任一指标替代自然语言回答质量。
2. **建立 multi-document funnel**：分别记录 retrieved / selected / generation-visible / supported / cited all-gold，定位真实损失层。
3. **改进 selected/context packing，但不预设它一定是全部根因**：做确定性排序、去重、文档覆盖、预算装配，并记录对 funnel 每层的影响。
4. **单变量检索增强实验**：相邻段落、parent/child、rerank、lexical + semantic 等一次只验证一个候选。
5. **动作级 diagnostic**：针对“命中但上下文不完整”“表达不匹配”“多个独立证据需求”等稳定失败簇，记录 Observation → candidate action → Evidence delta → latency/cost。

### P0-B：顶层 Agent foundation / 控制面 hardening

1. **Typed TaskState**：统一表达 goal、confirmed constraints、pending questions、route、EvidenceRef、freshness/authorization、budget、termination。
2. **Typed TaskDelta**：把每个新 user turn 先解释为对当前任务的增量，而不是直接重写整张 TaskState。
3. **通用 Context Builder**：每个节点只拿当前需要的最小上下文，实际入模内容可在 Eval 中直接检查。
4. **Action / Budget / Progress Ledger**：明确 allowed action、消耗预算、Tool Observation、Evidence delta、no-progress 与停止原因。
5. **补第二个顶层 bounded recovery Scenario**：在不进入 RAG 内部策略的前提下，验证 Evidence 失效重取证或跨 Tool 补证据等全局恢复。

这两条线在路线层面可以并行、在施工层面应交错切片：A 线回答“RAG 什么情况下真的需要额外动作”，B 线回答“系统是否具备安全执行额外动作的通用控制面”。只有相关前置切片成熟，才应该进入真正的 Agentic RAG / 更自然多轮。

---

## 5. Agentic RAG：重新打开 P6 时应怎样实现

### 5.1 先冻结职责与插入点合同，避免 Subgraph 与 AnswerFlow 打架

RAG Subgraph 的职责应严格限制为**文档 Evidence acquisition**，而不是重新实现 AnswerFlow。当前对上层已经存在 Knowledge Tool 的取证合同，P6 若重新得到 `go`，首先应冻结下面这些**不变约束**，而不是提前固定新的类名或第三层抽象：

- 对调用者继续保持现有 Knowledge Tool 的请求/`RetrievalOutcome` 语义，上层不需要知道内部走 deterministic Pipeline 还是 bounded Subgraph；
- Subgraph 的插入点位于 RAG 的取证阶段，不能复制 AnswerFlow，更不能再建立第二个 Gate；
- 上层 Shared Gate、Composer、Citation Validator、Evidence schema、ACL、outbound 与 Trace/Eval 合同保持唯一事实源；
- deterministic Pipeline 必须继续作为可比较 baseline / fallback。

具体实现可以是扩展现有 retrieval adapter、在 Knowledge Tool 内增加策略选择，或其他内部形态；应由 P6 重开后的 module plan 根据当时的 action state、父子预算、ACL/outbound 和 A/B 需求决定，本文**不预先冻结 `EvidenceAcquisitionStrategy` 等具体接口或类名**。

### 5.2 最小可信 Subgraph

```text
Retrieve
  → Observation / Evidence Progress
  → Answerable：返回 RetrievalOutcome
  → Recoverable：从 allowed actions 中选择一个动作
  → Re-acquire Evidence
  → No progress / Budget exhausted / Unsafe：停止
```

“Agentic”的判定标准不是“用了 LangGraph”，而是：**系统读取第一次 Observation 后，能够在停止与至少一个受控 recovery action 之间作出选择，并通过下一次 Observation 验证是否获得新的有效 Evidence。**

### 5.3 必须保持的边界

- 顶层 Harness 负责全局 route、SQL/Hybrid、总预算和最终产品状态；RAG Subgraph 只负责文档取证。
- 顶层 Loop 与 RAG Subgraph 使用父子预算；禁止对同一个失败同时在两层重复循环。
- Subgraph 不生成最终答案、不调用 SQL、不放宽 ACL、不绕过 outbound。
- Pipeline 必须长期保留为 baseline / fallback；实现 Subgraph 不代表默认切换。
- 同 corpus、同问题集、同 AnswerFlow、同 Evidence/citation 合同、可比较预算下做 A/B。

### 5.4 Agentic RAG 必须有两套验收

**External quality acceptance**：在未污染 held-out 上证明 Evidence / answer / citation 的净收益，并报告额外 Tool calls、延迟和成本。

**DataPilot business/demo acceptance**：至少有一个实际 business/demo canonical Scenario 可以稳定展示：

```text
retrieve
→ observe insufficient Evidence
→ choose allowed recovery action
→ retrieve again
→ Evidence increases
→ answer / stop
```

只在 external benchmark 上有效、却无法进入 DataPilot 实际 Runtime 的 Subgraph，不足以成为项目核心面试亮点。

---

## 6. 多轮 Agent：TaskState 之外还需要 TaskDelta

当前“一次 clarification + 一次 signed follow-up”已经证明了跨 turn 安全恢复，但要升级到自然的任务级多轮，仅增加 TaskState 还不够。

建议形成：

```text
User Turn
  → Turn Understanding / Typed TaskDelta
  → Merge into TaskState
  → Invalidate / reuse Evidence
  → Route / Allowed Action
  → Tool / Controller
  → Updated TaskState
```

### 6.1 Typed TaskDelta 至少应区分

- **continue**：继续当前任务，不改变主要约束；
- **modify_constraint**：例如“把上个月改成本月”；
- **ask_about_existing_result**：例如“为什么？”、“第二个呢？”；
- **add_evidence_requirement**：例如“再结合公司政策看看”；
- **switch_task**：开始新的目标，不继承旧任务语义；
- **correct_previous_understanding**：例如“不对，我说的是退款率”；
- **cancel / stop**：显式终止当前任务。

TaskDelta 应是对 TaskState 的受控修改，不允许模型一次自由重写全部状态。

**实现约束**：TaskDelta contract 本身不绑定 LLM。若 `Turn Understanding` 使用任何模型节点，则必须把它作为新的独立 node purpose / data class / fields 完成 outbound 用途登记，并在每次调用前取得 `OutboundDecision`；不得继承 `query_plan`、`sql_generation` 或其他既有节点的出站授权。同时必须提供未授权、provider 不可用或解析不确定时的确定性保守降级。

### 6.2 多轮 Eval 必须覆盖的真实行为

- 连续 clarification；
- 指代与省略；
- 条件修改；
- 基于旧 Evidence 的解释；
- Evidence revision / ACL 变化后的失效；
- route 从 SQL → Hybrid 或 RAG → Hybrid 的任务推进；
- Tool 失败后的安全恢复；
- 重复请求、版本冲突、TTL 过期、无进展停止。

完成后才能把项目升级表述为“**bounded task-oriented multi-turn Agent**”；仍不能宣传为开放聊天机器人或长期记忆系统。

---

## 7. Eval：不仅评答案，还要评“循环是否值得”

### 7.1 Answer / RAG 质量指标

建议至少分开记录：

- retrieval coverage / all-gold；
- selected / generation-visible coverage；
- answer correctness；
- faithfulness / support；
- completeness；
- citation coverage / citation correctness；
- multi-document funnel。

### 7.2 Agent Loop / Agentic RAG 指标

新增 Loop 后至少记录：

- recovery trigger precision：是否在真正可恢复时才触发动作；
- recovery success rate：额外动作后是否从失败变成可回答；
- Evidence gain per extra call；
- duplicate / no-progress rate；
- average / p95 Tool calls；
- budget exhaustion rate；
- latency delta；
- provider / token cost delta；
- unsafe recovery prevention：权限、outbound、revision 等是否仍然 fail closed。

这样才能证明“Agentic”带来的不是简单多查一次，而是 Observation-driven 的额外动作在可控成本下产生稳定净收益。

### 7.3 Deterministic Gate 与真实模型 E2E 分离

M40 technical assurance 主要证明 deterministic contract 与运行身份一致性。新增 Agentic RAG / 多轮后，应继续保持 deterministic required Gate，同时增加少量真实 provider E2E showcase 验证真实交互质量。两者分别记录，不允许真实 provider 抖动覆盖 deterministic 安全失败，也不允许 deterministic case 冒充真实问答质量。

---

## 8. 工具调用失败：现有与未来策略

### 8.1 现有策略

- 无可信 caller、权限拒绝、thread owner/version/TTL 不符：**Tool 前失败关闭**。
- 检索无证据、Evidence Gate 不允许回答、citation/support 不成立：返回 `no_answer` 或保守说明，不拼凑答案。
- 外部 provider、运行时或依赖不可用：返回 `external_unavailable`，不伪装成业务拒绝。
- Hybrid 某支不足：仅在合同允许时保留单支 `partial`；同时声称数据表现和业务政策时默认要求两类 Evidence。
- 不自动无限 retry：当前优先保留失败事实和可观察性，不通过静默重复调用掩盖问题。

### 8.2 后续增强原则

未来允许有限 retry、fallback、重新检索或跨 Tool 补证据时，每个动作都必须拥有：

```text
trigger reason
allowed action
budget cost
expected Evidence delta
actual Observation
progress / no-progress
termination reason
```

恢复动作不能绕过 caller、ACL、outbound、revision 或 Trace/Eval 合同。

---

## 9. 后续演进必须保持的工程原则

1. **不要把 P6 `no_go` 当成失败，也不要把它当成永久否决。** 历史结论只说明当时 Evidence 不足以证明多步 Subgraph 值得增加复杂度。
2. **先补关键 P4-aligned hardening，再扩大自治边界。** 通用 Context Builder 与面向动态 Loop 的 Action/Budget/Progress contract 是未来 Agent Loop 的地基；TaskState 泛化和第二个 recovery 则属于主线延伸增强，不应反向解释为 P4 未完成。
3. **一次只验证一个主要改变。** packing、rerank、query rewrite、parent expansion、Subgraph 不应同时上线后再解释收益。
4. **循环必须有可证明的进展。** 没有新增 Evidence、状态改善或用户新信息就应停止。
5. **顶层 Loop 与 RAG 内部 Loop 必须职责分离。** 顶层表达“还缺什么 Evidence”，RAG Subgraph 才决定文档内部如何再取证。
6. **State 不等于 Context。** State 保存事实；Context Builder 决定当前节点能看什么；完整 State 不应无差别灌入 prompt。
7. **TaskDelta 不应自由覆盖 TaskState。** 新 turn 只允许以 typed delta 修改必要字段，并明确触发旧 Evidence 的复用或失效。
8. **记忆必须先有数据生命周期。** 长期记忆至少需要 tenant/ACL、TTL、删除、纠错、审计与过期事实治理。
9. **上下文治理优先保留可追溯事实。** 优先保存 confirmed constraints、EvidenceRef、revision、未决问题与高风险原始 reference，不用不可验证摘要替代关键事实。
10. **安全与预算优先于恢复成功率。** 不能为了“Agent 能自动恢复”而放宽权限、扩大外发或无限增加调用。

---

## 10. M40 之后的大致路线

下面是能力顺序建议，不是新的冻结 roadmap。仍应按项目现有方式：每次只为最小可验收切片写 module plan，完成验证与 state 更新后，再决定下一切片。

### Track A：RAG quality & recovery evidence

**目标**：知道 RAG 真正失败在哪里，并证明是否存在值得循环的动作。

建议顺序：

1. Answer correctness / support / completeness 基线；
2. multi-document funnel；
3. packing 单变量增强；
4. retrieval 单变量候选实验；
5. action-level diagnostic；
6. 重新执行 P6 go/no-go 审查。

**完成标志**：至少有一个稳定失败簇只能在看到第一次 Observation 后合理决定下一动作，并且该动作有明确 Evidence 增量与成本证据。

### Track B：top-level Agent foundation / control-plane hardening

**目标**：在不推翻 P4 已验收最小切片的前提下，继续 harden 通用控制面，并把 thread recovery 泛化为未来动态 Loop / 多轮可复用的 Agent foundation。

建议顺序：

1. typed TaskState；
2. typed TaskDelta（contract 不绑定 LLM；若使用模型理解，先完成独立 outbound purpose 登记与确定性降级）；
3. node-level Context Builder；
4. Action / Budget / Progress Ledger；
5. 第二个顶层 bounded recovery Scenario；
6. 对实际入模 Context、Evidence reuse/invalidation、budget/stop 做 required Eval。

**完成标志**：不依赖固定字符串模板也能表达任务状态；任一允许恢复动作都能说明“为什么执行、消耗多少预算、得到什么新 Observation、是否产生进展、为什么停止”。

### Track C：bounded Agentic RAG（条件主线）

只有 Track A 形成 `go` Evidence 后才进入：

1. 冻结 Subgraph 取证插入点与不变合同（Knowledge Tool 对上层语义、唯一 Gate/Composer/Citation、ACL/outbound、Trace/Eval、父子预算）；
2. 保留 deterministic Pipeline 作为 baseline / fallback；
3. 由当时 module plan 决定最小内部实现 seam，不提前固定类名；
4. 实现 Observation-driven bounded RAG Subgraph；
5. Pipeline/Subgraph held-out A/B；
6. business/demo canonical Scenario；
7. default / experimental / fallback 决策。

如果 A/B 没有稳定净收益，Subgraph 可以保留实验实现但不切默认；这仍然是有效工程结论。

### Track D：bounded task-oriented multi-turn Agent

Track B 基线完成后即可逐步推进，不必机械等待 Track C 全部结束：

1. TaskDelta understanding（优先 deterministic / closed-world 起步；若使用模型节点，先完成独立 outbound purpose 登记与保守降级）；
2. 连续任务状态合并；
3. Evidence reuse / invalidation；
4. route 变化与跨 Tool 补 Evidence；
5. bounded multi-turn Scenario；
6. Hybrid follow-up；
7. 必要时再引入持久 checkpoint / compact。

**Evidence 复用基线不得重新发明**：Track D 必须继承 M37 narrow-B 合同——SQL follow-up 默认重查；external Document Evidence 默认重检索；business same-requirement 的 explain/reuse 只能在重新核对 active identity、revision、content/anchor 与 ACL 后重水化。TaskDelta 只描述用户意图变化，**不自动赋予旧 Evidence 复用权**；任何放宽都需要新的 Scenario、合同与决策记录。

**完成标志**：用户可以通过自然语言在同一任务内连续修改条件、追问、补充证据要求或纠正理解；系统每轮都重新判断权限、Evidence 有效性和下一动作，并存在明确停止条件。

### Track E：条件补强

只有真实 Scenario 出现后再建设：

- typed context compact / 长历史摘要；
- 持久/分布式 checkpoint；
- 最小长期记忆；
- 生产认证与企业 connector；
- 更开放 Router；
- Cloud observability；
- 开放研究型 Agent / 多 Agent。

### 建议模块节奏（仅作排期参考）

| 大致位置 | 能力切片 | 属性 |
|---|---|---|
| M41 起 A/B 交错切片 | A：correctness / multi-doc funnel / 单变量实验；B：TaskState / TaskDelta / Context Builder / Action-Budget-Progress | 路线层面并行；施工层面同一时间只立一个 active module plan |
| A 线证据成熟后 | action diagnostic + P6 re-open go/no-go | 决策门 |
| `go` 后 | bounded RAG Subgraph + Pipeline/Subgraph A/B + business demo | 条件主线 / 核心亮点 |
| B 线相关地基稳定后 | 自然多轮 Task Loop、Evidence invalidation、跨 Tool bounded recovery | 主线；继续按交错最小切片推进 |
| 真实部署/长会话需要后 | persistent checkpoint、compact、长期记忆、认证/connector | 条件补强 |

如果求职时间有限，最值得优先形成的项目故事是：

> **可信 Evidence/ACL/Trace Harness + 可证明终止的 bounded Agent control plane + 一个由 Eval 证明有净收益的 Observation-driven Agentic RAG 场景 + 一个自然语言可连续推进的任务级多轮场景。**

长期记忆、多 Agent、开放 ReAct 不需要为了关键词覆盖强行加入。

---

## 11. 当前面试表述边界

| 亮点 | 当前可以如实说明 | 升级后的说法需要什么 |
|---|---|---|
| 企业 Data Agent Harness | LangGraph 已统一 SQL/RAG/Hybrid、typed Evidence、Trace、ACL 与安全停止 | 若要说“动态 Agent controller”，需 first-class Action/Budget/Progress 与运行中的 Observation-driven action |
| Agent Loop | 已实现 bounded clarification recovery 与一次受控 follow-up，可称“最小跨-turn bounded recovery loop” | 至少一个同次 run 或通用状态机路径能够 Observation → Next Action → Tool → Progress/Stop |
| Agentic RAG | 已完成 P6 readiness audit；当前历史结论为 `no_go`，未来 Subgraph 的控制权、安全与父子预算约束已由 Phase 4 roadmap 冻结 | 实现真实 bounded RAG Subgraph，并用 held-out + business Scenario 证明净收益 |
| 多轮对话 | 已支持一次结构化澄清恢复和一次 closed-world follow-up | Typed TaskDelta、连续 TaskState、Evidence 失效/复用、跨 route Eval |
| Memory / context engineering | 有短期 versioned checkpoint、TTL/owner、EvidenceRef 与最小上下文重建 | 通用 Context Builder 后可升级“task context engineering”；长期记忆需独立生命周期治理 |

---

## 12. 修订记录

### 2026-08-19：Phase 4 完成后能力边界与后续路线校准

- 将“Agent Loop 尚未真正形成”修正为：**已实现最小跨-turn bounded recovery loop，但尚无同次 invoke 内 Observation-driven autonomous loop**，避免否定 roadmap G5 已允许的 clarification recovery 切片。
- 初步引入能力分层，明确 P6 `no_go` 是合法阶段结果、不等同于 Phase 4 未完成；本轮进一步把“已收口主线 / P4-aligned hardening / conditional capability / post-Phase-4 enhancement”边界拆清。
- 将 **通用 Context Builder、Typed TaskState / TaskDelta、Action / Budget / Progress contract** 提升到 Agentic RAG 之前/并行建设；其中 Context Builder 与动态 Loop 控制面属于优先 hardening，TaskState / TaskDelta 属于主线延伸增强。
- 将后续路线由单线“RAG → Subgraph → 多轮”调整为 **RAG quality & recovery evidence** 与 **top-level Agent foundation** 两条并行主线。
- 补充 RAG **multi-document funnel**，避免把最终 all-gold cited 低分直接归因于 packing。
- 为 Agentic RAG 明确取证职责、父子预算/禁止双循环约束，以及 **external held-out + business/demo Scenario** 双重验收；具体内部 seam 留待 P6 重开后的 module plan 决定。
- 为自然多轮增加 **Typed TaskDelta → merge TaskState → Evidence reuse/invalidation → route/action** 的明确演进模型。
- 补充 Agent Loop / Agentic RAG 的质量指标，包括 recovery success、Evidence gain、no-progress、Tool call、budget exhaustion、latency/cost 等，要求证明循环的净收益而不是仅证明“多调用了一次”。


### 2026-08-19：第二轮审查后的合同与分类收口

- 将“Roadmap 主线必做 / roadmap debt”拆开：P4 最小 recovery/thread、P5 Hybrid、P7 assurance 明确归入**已收口/最小切片**；通用 TaskState 和第二个 recovery 降级为**主线延伸增强**，不再反向解释为 Phase 4 未完成。
- 将 `EvidenceAcquisitionStrategy`、`DeterministicPipelineAcquirer` 等具体类设计从路线文档移除，改为只冻结 **Knowledge Tool 对上层语义、Subgraph 取证插入点、唯一 Gate/Composer/Citation、ACL/outbound 与 Trace/Eval** 等不变合同。
- 为 TaskDelta / Turn Understanding 增加 outbound 前提：contract 不绑定 LLM；若引入模型节点，必须独立登记 node purpose / data class / fields、取得 `OutboundDecision`，并提供确定性保守降级。
- 修正 P6 面试表述为“**已完成 readiness audit；后续安全/控制边界由 roadmap 冻结**”，不再声称已经完成 Subgraph 安全设计。
- 将 A/B 双主线明确为**路线层面并行、施工层面交错最小切片**，同一时间只维护一个 active module plan。
- 将 multi-document funnel 中的 support 明确为 **Composer/Answer 诊断层**，不新增第五个 EvidenceLedger stage。
- Track D 明确继承 M37 narrow-B Evidence 复用/失效合同，TaskDelta 不自动赋予旧 Evidence 复用权。
- 将 LangFuse Cloud 从“Phase 4 后能力”移入 **conditional capability**：满足 allowlist、脱敏、classification、失败降级与 outbound security case 后才可显式恢复，且不作为唯一 Trace/Eval 事实源。
