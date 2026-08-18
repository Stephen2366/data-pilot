# Phase 4 RAG 能力现状、缺口与演进候选

> **用途**：面向后续 RAG 工程演进的状态清单：解释现有能力、质量缺口、尚未实现能力及其推进条件。它不替代当前事实源：运行与边界以 [`AI_CONTEXT.md`](../state/AI_CONTEXT.md) 为准，RAG 运行口径以 [`rag-current-state.md`](../state/rag-current-state.md) 为准，评测数字和可比性以 [`eval-baselines.md`](../state/eval-baselines.md) 为准，路线选择以 [`phase4-roadmap.md`](../phase4-roadmap.md) 为准。
>
> **一句话结论**：DataPilot 已具备 Harness、真实 Tool、短期状态、受控多轮、Evidence/citation、Trace 与 Eval 基线；开放式 ReAct、长期记忆、多步自治检索等能力尚未实现，但都是可按证据继续演进的候选，而不是永久排除项。

## 1. 概念体现程度

| 概念 | 体现程度 | 当前实现 | 明确边界 |
|---|---|---|---|
| Harness engineering | 很强 | 顶层 LangGraph Harness 统一路由、Tool 预算、状态、终止、Trace 和 API 投影。SQL/RAG 单路各至多一个深 Tool；Hybrid 固定 SQL/RAG 两支各一次。 | 不提供开放式计划、多 Agent 或无限循环。 |
| Agent loop | 有限 | 支持澄清后的恢复、一次显式 follow-up、Hybrid 的双 Evidence 汇合。 | 不允许模型自行反复“想—搜—再想”；RAG 内部没有循环。 |
| Tool use / 工具调用 | 很强 | Knowledge Tool 返回 typed Evidence，SQL 也经深 Tool 执行；答案、引用和 Trace 都消费同次运行事实。 | 不允许任意 Python/Shell、写库或副作用 Tool。 |
| Agentic RAG | 当前不实现 | M39 已完成 P6 入场审计，严格结论为 `no_go`。 | 没有 query rewrite、多步再检索、子问题拆分或 RAG Subgraph。 |
| 循环设计 | 有但刻意收紧 | 顶层有有界状态迁移、预算和停止语义。 | 不允许顶层与 RAG 子图对同一失败重复循环。 |
| 短期记忆 | 已实现 | 进程内 versioned checkpoint 支持 pending clarification、一次 resume / clear 和一次 follow-up；有 owner、TTL、版本和并发旧状态拒绝。 | 重启或多 worker 不恢复；不保存旧 answer、rows、正文或 citation。 |
| 长期记忆 / 长期对话召回 | 未实现 | 当前没有跨会话用户画像、偏好库或历史对话检索。 | 不能把完整聊天记录长期保存后称为“记忆”。 |
| 多轮对话 | 窄范围已实现 | 支持一次结构化澄清恢复，以及成功 SQL/RAG 后的一次显式追问。 | 不支持第二次追问、Hybrid follow-up、无限轮聊天或跨会话连续对话。 |
| 上下文管理 | 中等偏强 | Evidence 有候选、授权、generation-visible、citation 四阶段；ACL、用途、Gate 和 Citation Validator 控制哪些资料真正能进入回答。 | 还没有自动历史摘要或任意长会话的压缩。 |
| Context compact | 未实现 | 暂无自动摘要、滚动压缩或上下文裁剪组件。 | 不应把“截断历史”误称为上下文治理。 |
| 长上下文治理 | 初步具备 | 外部语料按约 2400 字符单元切分，有 revision/content identity/anchor，且有 selected budget 与 Evidence Gate。 | 无 parent/child、rerank、相邻段落扩展或自动长历史 compact；多文档 packing 仍是弱点。 |
| Agent 编排 | 很强，但非自治 | 单路固定为 `route → tool → controller`；Hybrid 为 `route → SQL branch → RAG branch → controller`，唯一 controller 负责最终回答。 | Router 只覆盖 closed-world SQL/RAG 与两类 canonical Hybrid，不是通用意图理解。 |
| ReAct | 主动不采用 | 保留结构化 Action、Observation、Gate、reason code 和状态迁移，方便审计。 | 没有自由 Thought → Action → Observation 循环，也不保存模型原始思维链。 |
| 工具失败处理 | 很强 | 用四轴状态和保守终止表达 `blocked`、`external_unavailable`、`no_answer`、`partial` 等结果；权限/生命周期拒绝在 Tool 前停止。 | 不自动无限重试；没有证据时不伪造成功答案。 |

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

**当前主要失败簇**：lexical 漏召回、selected budget / multi-document context packing 不足、Composer 严格 support 合同拒绝。M39 审计没有证明“第一次 Observation 后再选一个动作”能稳定新增 Evidence，也没有可比较的额外预算，因此不建设 RAG Subgraph 是有证据的取舍，不是遗漏开发。

## 3. 当前未实现、但可继续推进的能力

这些能力不是“以后不做”，也不是自动待办。当前状态只表示：还没有足以安全切入默认路径的实现和证据。后续可以针对明确目标立模块、补合同和 Eval；表中的条件用于避免在没有可验证收益时扩大复杂度。

| 能力 | 当前缺口或风险 | 建议推进条件 |
|---|---|---|
| 多步 Agentic RAG / RAG Subgraph | 当前没有证明某个 Observation 驱动动作可以新增 Evidence；因此 M39 对“现在直接接入 Subgraph”给出 `no_go`。 | 未污染 dev 先证明具体动作有效，冻结 held-out decision set，并固定可比较额外预算；满足后可重新立项实现。 |
| query rewrite、子问题拆分 | 没有已证实“问题表达”而非 corpus/ACL/gold/外部不可用导致的稳定失败簇。 | 有可复现失败簇，并能为某一个动作写出清楚的收益假设。 |
| parent/child、相邻上下文扩展、rerank、hybrid retrieval | 都可能改善结果，但同时上会无法归因。 | 每项按单变量 A/B、相同 corpus/合同/runtime、held-out 证据独立裁决。 |
| 自动 context compact / 长历史摘要 | 当前多轮范围很窄，尚未有真实长会话的压缩质量、漂移和隐私证据。 | 长会话成为正式 Scenario 后，先压缩“已确认条件 + EvidenceRef + 未决问题”，而不是任意总结全文。 |
| 长期记忆与对话召回 | 需要解决 tenant、ACL、过期、用户删除、纠错、审计和错误记忆。 | 有明确跨会话任务需求后，先设计可删除、最小化的用户确认事实，而非长期保存完整对话。 |
| 持久化 checkpoint | 内存 checkpoint 已满足当前受控 resume / follow-up。 | 重启恢复或多 worker 会话成为 required Scenario 时。 |
| 开放 Router / 远程 Synthesizer | 当前 closed-world 路由和本地确定性 Hybrid 是已验证基线；远程能力还涉及额外数据出站。 | 真实开放问法形成稳定失败簇，并完成 outbound、held-out、预算及用户授权。 |
| 生产认证与真实 connector | 目前 caller resolver 是 demo/test seam，外部 benchmark 也不能证明企业真实 ACL、同步、删除与性能。 | 进入非本地部署、真实用户/tenant 或真实企业数据接入时。 |
| LangFuse Cloud | 默认关闭，避免 question/answer 随观测链路外发。 | 定义 allowlist、脱敏、接收方、用途和失败降级后，并得到明确授权。 |

## 4. 最值得优先补的能力

### 第一优先级：先提升“回答质量”

1. **多文档 Context Packing**：为 selected Evidence 做确定性排序、去重、按文档配额和预算装配。这直接针对多文档 all-gold 只有 5.26% 的问题。
2. **单变量检索增强实验**：从相邻段落扩展、parent/child、rerank、lexical + semantic 融合中一次只选一个候选，做同条件 dev / held-out 对照。
3. **人工正确性评测**：建立抽样人工复核或明确的 gold answer 规则。否则只能讲“引用和合同闭合”，不能讲“RAG 回答准确”。

### 第二优先级：证明后再增加“恢复能力”

4. **窄范围失败后再取证动作**：例如“已命中相关文档，但 Evidence 不足时扩展同文档相邻片段”。它必须先证明会新增 Evidence，才可能成为 P6 的入口。
5. **开放问法 Router Eval**：先收集并评测现有 Router 的真实失败，再决定扩规则、受控模型 fallback 或远程 Router。

### 第三优先级：真实需求出现后再补“会话能力”

6. **持久化短期状态**：让 resume / follow-up 可以跨重启或多 worker。
7. **最小长期记忆**：只保存用户明确确认的偏好或任务事实，并带 tenant、TTL、删除和审计。
8. **长历史 compact**：把历史收敛为受控状态，而非把旧聊天全文不断塞给模型。

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
