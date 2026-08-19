# Phase 4 RAG 能力现状、缺口与演进候选

> **用途**：面向后续 RAG 工程演进的状态清单：解释现有能力、质量缺口、尚未实现能力及其推进条件。它不替代当前事实源：运行与边界以 [`AI_CONTEXT.md`](../state/AI_CONTEXT.md) 为准，RAG 运行口径以 [`rag-current-state.md`](../state/rag-current-state.md) 为准，评测数字和可比性以 [`eval-baselines.md`](../state/eval-baselines.md) 为准，路线选择以 [`phase4-roadmap.md`](../phase4-roadmap.md) 为准。
>
> **一句话结论**：DataPilot 已经完成了企业 RAG/Agent 最难补的“控制与证据地基”——可信 Tool、ACL、Evidence/citation、四轴状态、Trace、Eval 和受控 thread；但智能自治层仍然偏薄。目前不能把项目介绍成完整的 Agentic RAG、通用 Agent Loop 或自然多轮对话系统，M40 之后应先补真实回答质量与失败证据，再有界实现 RAG 再取证循环和任务级多轮。

阅读这份清单时，需要把四件容易混淆的事分开：

- **用了 LangGraph，不等于有 Agent Loop**：当前顶层图是固定、无环的编排图；它能安全调度 Tool，但不会在同一次运行中根据 Observation 自主决定再次行动。
- **保存了 thread，不等于有通用记忆**：当前 checkpoint 是一张短期、一次性任务卡，不是聊天历史、用户画像或跨会话记忆库。
- **能够追问一次，不等于自然多轮对话**：当前追问必须显式开启，并从服务端签发的 action/field 闭集中选择。
- **有 RAG Tool，不等于 Agentic RAG**：当前 RAG 是单次检索、Gate、回答和 citation 流程；检索失败后没有由 Observation 驱动的改写、扩展或子问题再取证。

## 1. 概念体现程度

### 1.1 还未正式开发 phase 4 时 roadmap 的预想

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

重点关注“目前实际体现程度未达到 roadmap 预想的体现程度”的概念。

| 概念 | 体现程度 | 当前实现 | 明确边界 |
|---|---|---|---|
| Harness engineering | 很强 | 顶层 LangGraph Harness 统一路由、Tool 预算、状态、终止、Trace 和 API 投影。SQL/RAG 单路各至多一个深 Tool；Hybrid 固定 SQL/RAG 两支各一次。 | 当前强项是控制面与失败关闭，不是自治规划。 |
| Agent loop | 尚未真正形成；控制地基已具备 | 当前 Graph 是无环固定拓扑；澄清 resume 和 follow-up 是用户发起的新 turn，Hybrid 双分支是顺序编排，都不是同次运行内的循环。现有 reason code、预算、Observation、状态迁移和停止语义可供后续 Loop 复用。 | 还没有“观察结果后选择下一动作并再次调用 Tool”的运行时闭环。 |
| Tool use / 工具调用 | 很强 | Knowledge Tool 返回 typed Evidence，SQL 也经深 Tool 执行；答案、引用和 Trace 都消费同次运行事实。 | 不允许任意 Python/Shell、写库或副作用 Tool。 |
| Agentic RAG | 当前不实现 | M39 已完成 P6 入场审计，严格结论为 `no_go`。 | 没有 query rewrite、多步再检索、子问题拆分或 RAG Subgraph。 |
| 循环设计 | 设计合同较强，实现尚未进入循环 | 已定义允许动作、预算、终止、无新增 Evidence 停止和禁止顶层/RAG 双循环等原则。 | 这些目前主要是后续循环的安全合同，不能当成已运行的循环能力。 |
| 短期记忆 | 窄范围已实现 | 进程内 versioned checkpoint 支持 pending clarification、一次 resume / clear 和一次 follow-up；有 owner、TTL、版本和并发旧状态拒绝。 | 本质是最小任务状态，不保存消息历史、旧 answer、rows、正文或 citation；重启或多 worker 不恢复。 |
| 长期记忆 / 长期对话召回 | 未实现 | 当前没有跨会话用户画像、偏好库或历史对话检索。 | 不能把完整聊天记录长期保存后称为“记忆”。 |
| 多轮对话 | 窄范围已实现 | 支持一次结构化澄清恢复，以及成功 SQL/RAG 后的一次显式、closed-world 追问；每个 accepted turn 都重新经过 Graph 和权限检查。 | 不是自由文本连续对话；不支持继续追问、Hybrid follow-up、跨 route 任务推进或跨会话连续对话。 |
| 上下文管理 | Evidence 上下文强；对话上下文初步 | Evidence 有候选、授权、generation-visible、citation 四阶段；thread 侧只有两类 clarification 模板和三类 follow-up 模板，按最小字段重建当前问题。 | 尚无通用的按节点 Context Builder、长历史裁剪、摘要保真或 token 预算治理。 |
| Context compact | 未实现 | 暂无自动摘要、滚动压缩或上下文裁剪组件。 | 不应把“截断历史”误称为上下文治理。 |
| 长上下文治理 | 初步具备 | 外部语料按约 2400 字符单元切分，有 revision/content identity/anchor，且有 selected budget 与 Evidence Gate。 | 无 parent/child、rerank、相邻段落扩展或自动长历史 compact；多文档 packing 仍是弱点。 |
| Agent 编排 | 很强，但属于固定工作流 | 单路固定为 `route → tool → controller`；Hybrid 为 `route → SQL branch → RAG branch → controller`，唯一 controller 负责最终回答。 | Router 只覆盖 closed-world SQL/RAG 与两类 canonical Hybrid；没有动态计划或基于 Observation 的下一步选择。 |
| ReAct | 主动不采用 | 保留结构化 Action、Observation、Gate、reason code 和状态迁移，方便审计。 | 没有自由 Thought → Action → Observation 循环，也不保存模型原始思维链。 |
| 工具失败处理 | 确定性失败处理很强；自适应恢复较弱 | 用四轴状态和保守终止表达 `blocked`、`external_unavailable`、`no_answer`、`partial` 等结果；权限/生命周期拒绝在 Tool 前停止。 | 当前通常是安全停止或用户重新发起，没有基于失败类型自动选择 fallback/retry/retrieval recovery。 |

## 2. 目前的 RAG 效果：应怎样理解

### 已经可以肯定的工程能力

- 知识发布、revision、ACL、Evidence、citation、AnswerFlow、Harness、Trace 和 Eval 都已经形成链路。
- 外部 EnterpriseRAG-Bench 共有 36,417 篇文档、139,214 个 retrieval units；business release 与 external benchmark 互相隔离。
- 当前 external 默认是 lexical，而不是 semantic：后者在相同 dev / held-out split 上都没有胜出，因此没有为了“语义检索”标签而切换默认。
- M40 的 SQL、RAG、Hybrid、澄清恢复和安全拒绝五路径 rehearsal，已验证 response / Trace、Evidence/citation、预算和 lifecycle 的同源关系。

### 质量证据与限制

下列数字只是当前外部 benchmark 的可比较基线，不与 22 条业务知识回归或 Text2SQL Eval 混算：

| 层次 | 当前结果 | 不能推出什么 |
|---|---|---|
| lexical retrieval（held-out，@20） | gold coverage `82.31%`；all-gold `77.50%`；MRR `0.723` | 召回到 gold 文档，不等于最终答案正确。 |
| semantic candidate（held-out，@20） | gold coverage `77.40%`；all-gold `74.17%`；MRR `0.630` | 不能因“semantic”名称而默认替换 lexical。 |
| Answer / Citation（180 题） | `146/180` complete；all-gold cited `80/180`（44.44%） | `complete` 只表示回答、support 与 citation 合同闭合，不等于自然语言答案正确。 |
| 难题切片 | multi-document all-gold `2/38`（5.26%）；semantic all-gold `15/52`（28.85%） | 当前不宜宣传为强多文档或强语义 RAG。 |

**当前主要失败簇**：lexical 漏召回、selected budget / multi-document context packing 不足、Composer 严格 support 合同拒绝。M39 审计没有证明“第一次 Observation 后再选一个动作”能稳定新增 Evidence，也没有可比较的额外预算，因此当时不建设 RAG Subgraph 是有证据的取舍，不是遗漏开发。

但 `no_go` 的含义也不能扩大：M39 只证明**已有的冻结产物不足以支持直接实现 Subgraph**，没有证明 Agentic RAG 对 DataPilot 永远无价值。现有 artifact 记录的是单次 Pipeline 结果，本来就没有执行过“相邻上下文扩展、受控改写、子问题检索”等候选动作，因此无法从中证明动作收益。若 M40 后希望补 Agentic RAG，应先用 diagnostic/dev 做新的、动作级单变量实验，形成 Observation、动作、Evidence 增量和预算证据，再重新打开 P6，而不是修改或回避 M39 的历史结论。

## 3. 当前未实现、但可继续推进的能力

这些能力不是“以后不做”，也不是自动待办。当前状态只表示：还没有足以安全切入默认路径的实现和证据。后续可以针对明确目标立模块、补合同和 Eval；表中的条件用于避免在没有可验证收益时扩大复杂度。

| 能力 | 当前缺口或风险 | 建议推进条件 |
|---|---|---|
| 多步 Agentic RAG / RAG Subgraph | 当前没有证明某个 Observation 驱动动作可以新增 Evidence；因此 M39 对“仅凭已有产物直接接入 Subgraph”给出 `no_go`。 | 在 diagnostic/dev 上补动作级实验，证明至少一种恢复动作能根据 Observation 被正确触发并新增有效 Evidence；再冻结 held-out decision set 和可比较预算，重新立项。 |
| 顶层任务级 Agent Loop | 当前 Harness 每次 invoke 都是无环图；resume/follow-up 依赖用户发起下一次请求，没有同次运行内的动态下一动作。 | 先明确值得自动恢复的失败类型，再把动作闭集、全局/子预算、进展判断、停止和失败投影做成可执行状态迁移。 |
| 更自然的任务内多轮 | 当前只有结构化澄清和一次签发式追问，无法在多轮中持续维护目标、条件、证据有效性和未决问题。 | 建立真实多轮 Scenario；用 typed TaskState 保存已确认条件、EvidenceRef 和未决项，并让每轮重新路由、授权和判断是否需要取证。 |
| query rewrite、子问题拆分 | 没有已证实“问题表达”而非 corpus/ACL/gold/外部不可用导致的稳定失败簇。 | 有可复现失败簇，并能为某一个动作写出清楚的收益假设。 |
| parent/child、相邻上下文扩展、rerank、hybrid retrieval | 都可能改善结果，但同时上会无法归因。 | 每项按单变量 A/B、相同 corpus/合同/runtime、held-out 证据独立裁决。 |
| 自动 context compact / 长历史摘要 | 当前多轮范围很窄，尚未有真实长会话的压缩质量、漂移和隐私证据。 | 长会话成为正式 Scenario 后，先压缩“已确认条件 + EvidenceRef + 未决问题”，而不是任意总结全文。 |
| 长期记忆与对话召回 | 需要解决 tenant、ACL、过期、用户删除、纠错、审计和错误记忆。 | 有明确跨会话任务需求后，先设计可删除、最小化的用户确认事实，而非长期保存完整对话。 |
| 持久化 checkpoint | 内存 checkpoint 已满足当前受控 resume / follow-up。 | 重启恢复或多 worker 会话成为 required Scenario 时。 |
| 开放 Router / 远程 Synthesizer | 当前 closed-world 路由和本地确定性 Hybrid 是已验证基线；远程能力还涉及额外数据出站。 | 真实开放问法形成稳定失败簇，并完成 outbound、held-out、预算及用户授权。 |
| 生产认证与真实 connector | 目前 caller resolver 是 demo/test seam，外部 benchmark 也不能证明企业真实 ACL、同步、删除与性能。 | 进入非本地部署、真实用户/tenant 或真实企业数据接入时。 |
| LangFuse Cloud | 默认关闭，避免 question/answer 随观测链路外发。 | 定义 allowlist、脱敏、接收方、用途和失败降级后，并得到明确授权。 |

### 3.1 目前可以怎样介绍，哪些还不能宣传

| 面试亮点 | 当前可以如实说明 | 还缺什么才能升级说法 |
|---|---|---|
| 企业级 Agent Harness | 已用 LangGraph 统一 SQL/RAG/Hybrid Tool、四轴状态、预算、Trace 和安全停止。 | 若要说“动态 Agent”，还需 Observation 驱动的下一动作与真实循环边。 |
| Agentic RAG | 可以说已经完成入场审计、失败分层和 Subgraph 安全接口设计。 | 必须实际实现有界 RAG Subgraph，并用同 corpus 的 Pipeline/Subgraph A/B 证明 Evidence 或答案收益。 |
| Agent Loop | 可以说已有 typed Action/Observation、reason code、预算和停止合同。 | 必须有至少一条运行路径能观察 Tool 结果、选择允许动作、再次执行并按进展停止。 |
| 多轮对话 | 可以说支持安全的一次澄清恢复和一次 closed-world follow-up。 | 需要连续任务轮次、自然 delta 理解、状态压缩/保真、Evidence 失效与跨轮 Eval。 |
| Memory / context engineering | 可以说有 owner/version/TTL checkpoint、EvidenceRef 和最小任务模板。 | 短期任务记忆要能跨多个 turn 稳定工作；context compact 和长期记忆目前都不能宣传为已完成。 |

## 4. 最值得优先补的能力

### 第一优先级：先让质量问题“量得准、改得动”

1. **答案正确性评测**：增加人工复核或明确的 gold answer/support 规则。现有 retrieval、`complete` 和 citation 指标分别有价值，但都不能单独代表回答正确。
2. **多文档 Context Packing**：为 selected Evidence 做确定性排序、去重、文档覆盖和预算装配。这直接针对 multi-document all-gold 只有 5.26% 的真实短板，也能为后续判断“需要改 packing 还是需要循环”提供基线。
3. **单变量检索增强实验**：从相邻段落扩展、parent/child、rerank、lexical + semantic 融合中按失败簇一次只验证一个候选，固定 corpus、合同、split 和预算。

### 第二优先级：重新建立 Agentic RAG 的入场证据

4. **动作级 diagnostic 实验**：对“命中但上下文不全”“查询表达不匹配”“问题确实包含多个独立证据需求”等失败分别验证候选动作，记录动作前后 Evidence 增量、重复率、延迟和成本。
5. **有界 RAG Subgraph**：只有动作实验成立后，才实现 `retrieve → assess progress → choose allowed action/stop → retrieve`。它必须是真正读取 Observation 决定下一步的子图，不能只是把现有 Pipeline 拆成 LangGraph 节点。
6. **Pipeline/Subgraph held-out A/B**：相同 Knowledge Tool interface、ACL、Evidence/citation 和预算口径下比较；有稳定净收益才切默认，否则 Subgraph 保持实验 adapter，Pipeline 继续作为 fallback。

### 第三优先级：把“单次追问”升级为任务级多轮

7. **Typed TaskState 与通用 Context Builder**：把目标、已确认条件、未决问题、EvidenceRef、预算和终止事实从固定字符串模板提升为可验证的任务状态；每个节点只看最小必要投影。
8. **有界多轮 Agent Loop**：允许同一任务在若干 turn 中澄清、重新路由、重新取证或安全停止，并持续验证 Evidence 的权限、revision 和用途；仍不建设无限聊天或开放动作空间。
9. **持久化与 compact 按 Scenario 引入**：先证明重启/多 worker 恢复或长历史确实成为 required 场景，再选择持久 checkpoint 和 typed compact；长期记忆继续独立评估，不与短期任务状态捆绑。

开放问法 Router Eval 可以和上述主线并行准备，但不宜先于 RAG 质量与任务状态成为大改造：否则路由范围变宽，只会让更多问题进入当前仍偏弱的回答链路。

## 5. 工具调用失败时的现有与未来策略

### 现有策略

- 无可信 caller、权限拒绝、thread owner/version/TTL 不符：**Tool 前失败关闭**，不让调用进入业务链路。
- 检索无证据、Evidence Gate 不允许回答、citation/support 不成立：返回 `no_answer` 或保守说明，不拼凑答案。
- 外部 provider、运行时或依赖不可用：返回 `external_unavailable`，不将技术故障伪装成业务拒绝。
- Hybrid 某支不足：仅在合同允许时保留单支 `partial`；涉及“数据表现 + 业务政策”的 claim 默认要求两支 Evidence。
- 不自动无限重试：当前默认 retry 为 0，避免重复调用、成本失控和失败被掩盖。

### 后续可能的增强

若外部调用变多、失败模式变得稳定，可再规划有限的指数退避、熔断、用户可见重试建议或异步恢复。但每一种恢复都要有明确预算、可观测失败分类和 Eval，不能把“自动重试”变成隐形 Agent loop。

## 6. 后续演进时必须保持的工程原则

1. **不把 P6 `no_go` 当成 RAG 停止优化。** 它只否定“在当前证据下直接加入多步 Subgraph”；检索、packing、rerank、相邻上下文扩展、回答质量和会话能力仍可以分别推进。
2. **一次只验证一个改变。** 例如先只改 packing，或只加 rerank；固定 corpus、question split、runtime、Evidence/citation 合同和预算，才能知道是否真的有效。
3. **先把质量指标补全，再讨论默认切换。** retrieval coverage、`complete`、citation 合同、人工答案正确性分别记录；不能让任一数字代替其他数字。
4. **循环必须有可证明的进展。** 新增 Agent loop / ReAct-like action 前，应定义 Observation、允许动作、期待新增的 Evidence、最多调用次数、停止条件和失败投影。
5. **记忆必须先有数据生命周期。** 长期记忆至少需要 tenant/ACL、TTL、用户删除、修正、审计和过期事实处理；没有这些不应长期保存完整聊天。
6. **上下文治理优先保留可追溯事实。** 无论是 packing、compact 还是长记忆，都应优先保存已确认条件、EvidenceRef、revision 和未决问题；不要只保留不可验证的自然语言摘要。
7. **工具恢复不能绕过安全与预算。** 重试、fallback、重新检索和新增 Tool 都要经过 caller、ACL、outbound、预算和 Trace/Eval 合同；不能因为“恢复失败”而放宽权限或静默扩大外发。

## 7. M40 以后的大致路线

下面是基于当前代码和证据给出的**能力顺序建议**，不是已经确认的阶段 roadmap，也不提前冻结具体模块数量、参数或实现文件。后续仍应按项目约定：每次只为当前最小可验收切片写 module plan，完成验证和 state 更新后，再决定下一切片。

总体路线建议为：

> **先补真实质量与动作证据 → 再做有界 Agentic RAG → 再升级任务级多轮 Agent Loop → 最后按真实部署需要补持久化和长期能力。**

### 路线 A：RAG 质量与 Eval 地基（建议下一主线）

**目标**：先回答“现有 RAG 为什么答不好”，并建立后续 Pipeline/Subgraph 都必须共用的正确性基线。

主要包括：

- 建立 answer correctness / support 的人工复核或可验证 gold，避免继续用 `complete` 代替正确率；
- 先修多文档 selected/context packing，并按失败簇做单变量检索候选实验；
- 把失败稳定分为 corpus/gold、召回、排序/packing、Composer、provider、ACL 和 query 表达等类型；
- 保留 diagnostic/dev 用于开发，重新冻结未污染 held-out 用于默认切换。

**完成标志**：能明确指出哪些问题只需确定性 Pipeline 增强，哪些问题必须在看到首次 Observation 后才能选择下一动作；至少形成一个可验证的 Agentic recovery 假设。

### 路线 B：有界 LangGraph RAG Subgraph（核心面试亮点）

**目标**：重新打开 P6，但这次先补 M39 缺少的动作证据，再实现一个真正有循环语义的 RAG 子图。

最小可信形态是：

```text
Retrieve
  → Observation / Evidence Progress
  → Answerable：返回 Evidence
  → Recoverable：选择一个允许动作并再次取证
  → No progress / Budget exhausted / Unsafe：停止
```

这里“Agentic”的关键不是使用 LangGraph，而是子图能够根据当前 Observation 在“停止”和“采用某个已获准的恢复动作”之间做选择，并验证新一轮是否真的增加了有效 Evidence。恢复动作由路线 A 的失败证据决定，可以是受控上下文扩展、query rewrite 或独立证据需求拆分，但不在本状态报告中提前指定默认方案。

必须继续守住：

- 顶层 Harness 管全局 route、SQL/Hybrid、总预算和最终产品状态；RAG Subgraph 只管文档取证；
- Pipeline 与 Subgraph 使用同一个 Knowledge Tool interface，复用 ACL、outbound、Evidence/citation 和 Trace 合同；
- 子图不生成最终答案、不调用 SQL、不放宽权限，也不与顶层对同一失败形成双循环；
- 用相同 corpus、held-out、预算和回答合同做 A/B。实现成功不等于默认切换，只有稳定净收益才能切换；确定性 Pipeline 始终保留为 fallback。

**完成标志**：代码中存在真实的 Observation 驱动循环边；Eval 能证明动作选择、Evidence 增量、无增量停止、预算、ACL 等价和 Pipeline/Subgraph 差异。到这一步，DataPilot 才能有底气把“有界 Agentic RAG”作为已实现的面试亮点。

### 路线 C：任务级 Agent Loop 与自然多轮

**目标**：把当前“一次澄清/一次签发式追问”升级为同一任务内可持续推进、但仍有预算和终止条件的多轮 Agent。

建议先做短期任务能力，而不是直接做长期用户记忆：

- 用 typed TaskState 保存任务目标、已确认条件、未决问题、route、EvidenceRef、预算和终止事实；
- 每个新 turn 先理解用户对当前任务的增量，再决定复用、失效、重新取证、换 Tool、澄清或停止；
- 建立通用 Context Builder，让 Router、SQL、RAG、Subgraph 和 Composer 只看到各自需要的最小上下文；
- 先覆盖连续澄清、相关追问、Evidence 变化和 Tool 失败后的安全恢复；Hybrid follow-up 只有建立自己的双 Evidence 合同后再开放；
- 对多轮中的 owner、版本冲突、重复请求、过期、权限变化和无进展停止继续做 required Eval。

**完成标志**：不再依赖两个 clarification 模板和三种 follow-up 模板才能继续任务；多轮状态、实际入模上下文和每次 Tool/Graph 调用都可观察、可回放、可终止。此时可以宣传“有界多轮 Agent Loop”，但仍不能宣传开放 ReAct 或长期记忆。

### 路线 D：上下文压缩、持久状态与长期记忆（条件补强）

这条路线不应为了堆名词立即开工：

- 只有多轮 Eval 出现真实 token/历史增长问题，才实现 typed context compact，优先压缩已确认条件、未决项和 EvidenceRef，不总结替代高风险原始事实；
- 只有重启恢复或多 worker 成为 required Scenario，才把进程内 checkpoint 换成持久 adapter，并处理 TTL、迁移、删除、并发和权限变化；
- 只有出现明确跨会话任务，才设计长期记忆。首版只保存用户明确确认、可删除、可纠错、可过期的事实，不长期保存完整聊天；
- 生产认证、真实 connector、LangFuse Cloud 和更开放 Router 仍按各自安全/出站门独立推进，不能因 Agentic RAG 已实现而自动放行。

### 建议的模块节奏（仅作排期参考）

| 大致位置 | 能力切片 | 路线属性 |
|---|---|---|
| M41 起第一组 | 回答正确性基线、失败分层、多文档 packing 与单变量候选 | 主线必做 |
| 后续一组 | 动作级 diagnostic 实验与 P6 重开审查 | 主线必做；重新决定 go/no-go |
| 条件满足后 | 有界 RAG Subgraph、Pipeline/Subgraph A/B 与默认/fallback 决策 | 为形成 Agentic RAG 亮点重点争取，但不能跳过证据门 |
| Subgraph 基线稳定后 | Typed TaskState、通用 Context Builder、有界自然多轮 Agent Loop | 建议主线 |
| 有真实 Scenario 后 | context compact、持久 checkpoint、最小长期记忆、生产认证/connector | 条件补强 |

如果求职时间有限，最值得优先形成的完整故事不是一次铺开所有热点，而是：**企业级 Evidence/ACL/Trace 地基 + 一个有真实循环和 A/B 证据的 Agentic RAG Subgraph + 一个可连续推进且能安全停止的任务级多轮案例**。长期记忆、多 Agent 和开放 ReAct 可以明确列为后续方向，不必为了名词覆盖牺牲已有工程可信度。
