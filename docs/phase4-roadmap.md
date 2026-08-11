# DataPilot Phase 4 Roadmap：可信多证据 Agent

> **文档定位**：本文记录已经确认的 Phase 4 路线，并将其转化为可推进、可验收的能力建设路线。它位于“阶段方向”和“模块施工计划”之间：固定能力顺序、依赖、交付物、验收语义和决策门，但不提前固定逐文件实现、具体类名、模型、chunk、top-k、阈值、循环次数或性能分数。
>
> **效力关系**：本文是 Phase 4 高层边界、核心合同、能力顺序和决策门的唯一推进事实源；`docs/phase4-reference.md` 不拥有路线决策权，但它是制定 module plan 和实施关键技术前必须按能力切片阅读的参考地图。当前运行、Eval、数据库和索引事实分别以 `docs/state/` 下对应文档为准。进入某个能力切片后，应结合本文、最新 state/失败证据和 reference 中的定点源码入口编写 module plan 与 `docs/notes/<module>-notes.md`，不能只读 roadmap 后直接施工，也不能把本文直接当成逐函数施工清单。
>
> **规划基线**：2026-08-11。当前为 M28 Text2SQL 收尾文档完成、待人工审查与 `accept-module`；Phase 4 尚未开工。

## 1. 阶段目标与完成故事

Phase 4 的目标不是“给 SQL Agent 接一个向量库”，而是把 DataPilot 从单一 Text2SQL 链路升级为一个**按证据类型工作、只在授权边界内取证、结论可回查、失败可解释、能力可评测**的数据分析 Agent。

阶段结束时，系统应能稳定演示三条主路径：

1. **SQL**：数据问题继续由现有 Text2SQL 深模块取得数据库 Evidence，保留 SQL Guard、业务口径、表格和 Trace。
2. **RAG**：政策、客服规则和指标说明由 Knowledge Tool 取得 Document Evidence；答案引用本次实际进入生成器、仍有效且有权使用的证据，证据不足或越权时正确停止。
3. **Hybrid**：LangGraph 编排 SQL 与 RAG 两条受控链路，以原始 typed Evidence 合成“数据表现 + 业务规则”结论；任一必需分支失败时，不伪造完整建议，并能保留安全、独立成立的 partial result。

系统还应具备以下 Agent 工程能力：

- Router 先判断是否需要重新取证，再判断需要 SQL、RAG、Hybrid，还是应澄清、拒绝或标记不支持；
- Tool 执行后经过 Evidence Gate，才能回答、有限恢复、澄清、部分返回或停止；
- 同一 thread 内支持澄清后恢复与基于上一轮证据的有限追问；
- State 保存可审计事实，Context Builder 只给当前节点提供最小必要上下文；
- Trace 与 Eval 能还原本轮路由、Tool、Observation、Evidence、citation、权限、出站、循环与终止原因。

一句话概括阶段故事：

> DataPilot 不只会查数或搜文档，而是知道一个结论需要什么证据，能在权限允许的范围内取得它，并能说明结论从哪里来、哪些条件不足、为什么继续或停止。

## 2. 当前起点与 Phase 4 入口门禁

### 2.1 可以直接承接的基础

| 当前基础 | Phase 4 复用方式 | 必须守住的边界 |
|---|---|---|
| Schema Retrieval → QueryPlan → SQL Guard → SQL execution | 整体封装为 Text2SQL Tool，返回 SQL Evidence 或结构化错误 | 不为画 Graph 拆成大量转发节点；SQL QueryPlan 不升级为跨能力万能计划 |
| SQL AST、RBAC、敏感字段策略 | 继续承担数据库侧只读与字段安全 | 不能代替文档 ACL；SQL 与文档安全只共享身份和审计上下文 |
| `AgentResponse`、`ToolCallTrace`、JSONL Trace | 兼容演进公开响应与运行证据 | 当前 `docs_used: list[dict]` 不是 Evidence 事实源，不能继续堆开放字段 |
| Schema Retrieval adapter、corpus hash、clean index、run-scoped 生命周期 | 复用 adapter 与索引卫生方法 | Schema corpus 与 Knowledge corpus 必须保持独立身份、索引和 Eval 合同 |
| M27 Scenario + typed assertion + ExecutionEvidence | 扩展为 RAG/Hybrid 一题一次执行、多断言共享真实证据 | 不把旧 Text2SQL assertion 名称机械套到 RAG，也不为每个指标重新执行 |
| 本地 JSONL 主路、LangFuse 可选旁路 | 继续作为 Trace 总体策略 | 未完成出站授权前，不能把文档正文、结果行或完整回答默认上传 Cloud |
| 10 条 `knowledge_docs` seed | 作为正式 corpus 的业务草稿和测试候选 | 未审查、未版本化、未建立 anchor/ACL 前，不是正式 gold corpus |

### 2.2 已确认的真实缺口

- `/api/query` 当前实际全部进入 SQL 路径，`rag/hybrid` 只是预留枚举；
- `domain_pack/kb_docs/` 仍为空；
- `knowledge_docs` 同时出现在数据库、RBAC、Schema 描述和 Schema Retrieval 中，通用 Text2SQL 目前可能看到知识正文；
- 当前响应和 Trace 没有稳定的 document revision、chunk、anchor、Evidence 与 claim-to-citation 关系；
- 当前 Eval 合同主要面向 Text2SQL，尚无 RAG/Hybrid 的 retrieval、citation、ACL、partial 与 Agent loop typed assertions；
- 项目依赖中尚未正式引入 LangGraph；具体版本与 API 应在对应 module plan 中根据当时官方文档确定，本文不固定。

### 2.3 Phase 4 开工门禁

Phase 4 实现应满足以下入口条件：

1. M28 已完成人工审查和 `accept-module`，Text2SQL 当前合同、默认配置和遗留问题已冻结为 Phase 4 输入；
2. 工作树中的既有改动已确认归属，不把其他工具或用户改动混入 Phase 4 首个模块；
3. `docs/state/AI_CONTEXT.md` 的当前阶段已切换到 Phase 4，并链接本文；
4. 第一能力切片的 notes 已建立 implementation checklist；
5. 下文 G0、G1 中会改变公开合同或知识安全边界的事项已由用户确认。

M28 的验收是阶段入口门禁，不意味着必须先补做新的真实 LLM Eval。若用户没有单独授权，Phase 4 不以重跑旧 Text2SQL Eval 作为开工前置。

### 2.4 参考分析与路线决策关系

`docs/phase4-reference.md` 保存横向分析、优先源码入口、可借鉴设计、反例和重新评估条件；本文保存经过确认后的当前路线。两者可以双向导航，但权威关系单向：若参考项目、旧分析或其采纳状态与本文冲突，以本文为准。参考结论也不是封闭候选集；进入具体模块时必须结合最新 state、失败证据和当时源码重新核对，必要时可以补充新项目或官方资料。

## 3. 总体架构与控制权

```text
API / Demo
  │  question + caller identity + thread identity
  ▼
LangGraph Agent Harness（唯一全局控制者）
  ├─ Router：是否需要重新取证、需要哪类 Evidence
  ├─ Controller：预算、允许状态迁移、澄清、停止、partial
  ├─ Evidence Gate：硬约束检查 + 结构化充分性判断
  ├─ Context Builder：按节点选择最小必要上下文
  │
  ├─ Text2SQL Tool ── SQL Guard / execution ── SQL Evidence
  │
  └─ Knowledge Tool ── ACL / retrieval / Evidence 构造
         ├─ 默认：确定性 RAG Pipeline
         └─ 实验：有界 LangGraph RAG Subgraph adapter
  │
  ▼
RetrievalOutcome + Document Evidence / SQL Evidence
  → Evidence Gate
  → Answer Composer / Hybrid Synthesizer
  → Citation Validator
  → complete / partial / clarification / insufficient / refusal
  │
  ├─ AgentResponse 安全投影
  ├─ 本地 JSONL Trace
  └─ RAG / Hybrid Eval ExecutionEvidence
```

控制权必须保持单一：

- 顶层 LangGraph 决定跨 Tool 路由、全局预算、澄清、Hybrid 汇合、最终状态与停止；
- Text2SQL Tool 自己决定如何完成数据库取证，SQL Guard 仍是数据库安全边界；
- Knowledge Tool 只负责文档取证，返回 RetrievalOutcome、Document Evidence、稳定 reason code 和诊断 reference；它不生成最终用户答案，也不决定最终 `answer_status`；
- Evidence Gate 判断当前 Evidence 是否足以回答；Answer Composer / Hybrid Synthesizer 只在 Gate 允许的 Evidence 上生成 claim，Citation Validator 再校验 claim-to-Evidence 绑定；
- 顶层 controller 是 route、execution、answer、safety 四轴及 `insufficient_evidence` 等最终产品状态的唯一裁决者；Tool 只报告 `no_candidate`、`no_authorized_evidence`、`stale_revision`、`retrieval_unavailable` 等更具体的取证事实；
- RAG Subgraph 只管理文档取证，不能调用 Text2SQL、生成跨来源结论、放宽 ACL 或扩大全局预算；
- 模型可以提出结构化动作，确定性 controller 只允许合同内状态迁移；模型不能自行覆盖权限、citation、必需分支或预算。

## 4. 跨里程碑不变量

以下合同从建立起贯穿 Phase 4，是跨阶段语义的单一事实源；后续里程碑只描述新增能力和验收增量。若各里程碑的局部表述与本节冲突，以第 4 节和本文最新修订记录为准；不得在模块 Plan 中另建一套核心合同。

### 4.1 知识事实源与发布不变量

- 政策、客服规则等文档型知识以 `domain_pack/kb_docs/` 中经审查的文件为权威源；
- 指标定义继续以 `domain_pack/metrics.yaml` 为权威源，RAG 可读说明只能由它生成或经过一致性校验；
- 数据库业务事实由 Text2SQL 查询，不复制到 RAG 伪装成实时事实；
- Schema 与关系继续服务 Schema Retrieval，不进入回答知识 corpus；
- 数据库目录、chunk store、关键词索引和向量索引都是可重建投影，不反向成为正文编辑入口；
- 新 corpus/index 必须在完整构建和校验成功后切换；失败时继续使用上一版完整可用版本，不暴露半成品。

### 4.2 Evidence 与 citation 不变量

Evidence 采用精简公共外壳加 typed payload：

- 公共外壳只表达本轮 Evidence 身份、类型、权威来源与 revision/content identity、允许用途、受控内容和稳定 reference；
- Document payload 表达 document/chunk 身份、标题、知识类型、anchor 与当前消费者实际可用片段；
- SQL payload 表达已通过 Guard 的 SQL、列、行数、结果 fingerprint、数据库快照身份和允许展示的结果视图；
- 授权决策、检索诊断、runtime identity 和对外安全投影是独立对象或 reference，不形成所有模块都依赖的万能 Evidence 大对象。

Evidence 流转至少区分四个阶段：

1. Tool 返回的候选 Evidence；
2. 过滤、去重或排序后选中的 Evidence；
3. 实际进入生成器的 Evidence；
4. 最终被 citation 使用的 Evidence。

Citation ID 由代码分配和校验，只能指向第 3 阶段中本轮实际可见、用途允许的 Evidence，并记录支持的 claim 或答案片段。引用存在性、身份、权限、revision 与可回查性由确定性代码裁决；开放语义支持度可由 gold、人工或 advisory judge 辅助，但不能取代真实性校验。

职责边界固定为：Tool 构造 typed Evidence，Evidence Gate 决定能否回答，Answer Composer / Hybrid Synthesizer 生成用户可见 claim，Citation Validator 校验引用，顶层 controller 投影最终状态。P2 的薄应用流程与 P3 的 LangGraph 必须复用这些组件，禁止在 Tool 内外各生成一次答案。

### 4.3 状态四轴不变量

| 状态轴 | 只回答什么 | 不应混入什么 |
|---|---|---|
| route | 选择 SQL、RAG、Hybrid 或暂不选择证据路径 | partial、blocked、外部超时 |
| execution | 工具/流程是否完成及技术 root cause | 回答是否完整、是否越权 |
| answer | 完整回答、partial、需澄清、不支持、证据不足或无答案 | provider 错误、安全裁决 |
| safety | 是否通过确定性安全裁决 | 检索不到、模型不会回答 |

Hybrid 还需保留每个分支自己的 execution 状态。`external_unavailable` 属于 execution，`insufficient_evidence` 和 `partial` 属于 answer，`blocked` 属于 safety；它们不能继续被压成 SQL Guard blocked 或单一 error 字段。

### 4.4 安全与出站不变量

- 文档使用 `public` 或显式 `allowed_roles`，不默认假设 admin 隐式全读；
- 检索前按权威目录硬过滤，检索后、进入生成器前再次复核；相似度、collection 名、前端选项都不是授权凭证；
- 未授权文档的正文、标题、存在性、命中数、citation 和错误信息都不能通过响应、Trace 或旁路泄露；
- 文档内容是不可信数据，伪系统指令、伪 citation 和诱导 Tool Call 不得改变控制流；
- outbound policy 按接收方、模型节点用途、数据类别和字段集合默认拒绝、显式放行；即使使用同一 provider，Router、Evidence 充分性判断、答案合成、Query Rewriting、Eval Judge、embedding、rerank 与 Cloud observability 也分别登记和授权；
- 每个模型节点调用前都必须取得 OutboundDecision。Router 通常不应看完整正文，Eval Judge 不继承线上 generation 的授权；未获授权的充分性判断器走确定性保守降级，不能静默发送 Document Evidence；
- 本地 JSONL 是默认运行证据事实源。当前远程 Qwen generation 只算待登记和审查的既有行为，不自动获得 Document Evidence 等新增数据类别的出站权限。

### 4.5 State 与 Context 不变量

- State 保存调用者、任务、状态迁移、Tool Observation、Evidence reference、分支结果、预算与终止事实；
- Context Builder 决定某一节点此刻能看到什么，不能把完整 State 或历史消息无差别塞入 prompt；
- SQL 节点不接收全部文档，RAG 节点不接收完整数据库结果，生成器只接收最终选中的 Evidence；
- thread 内只保留当前任务、已确认条件、必要指代、安全摘要和仍有效的 Evidence reference；
- 复用旧 Evidence 前复核调用者、权限、document revision、数据库快照和用途；失效时重新取证；
- 不保存或展示模型原始思维链，只记录结构化 Action、Observation、Gate 决策、reason code 和状态迁移。

### 4.6 Eval 不变量

- 一个 Scenario 只执行一次，同一 ExecutionEvidence 支撑 route、retrieval、citation、answer、Hybrid、safety、Trace 等多条 typed assertion；
- 离线 retrieval benchmark 与端到端 Eval 分开，召回命中不自动等于答案正确；
- `eligible = passed + failed + not_observed`，外部服务不可用和 judge 失败不能伪装成业务错误；
- 预期的 `insufficient_evidence`、澄清或安全拒绝是可观察行为，可以判为正确，不是 `not_observed`；
- 确定性安全、citation integrity、状态、Hybrid 必需分支和循环预算进入 required Gate；
- 运行时 Evidence 充分性判断器的控制合同和失败降级是 required，但其开放语义准确率先与人工 gold 对照；Eval LLM Judge 校准前保持 advisory。

Scenario 还必须按用途隔离：

- **diagnostic/dev Scenario**：用于发现失败簇、选择恢复动作和调整实现，可以迭代；
- **held-out decision Scenario**：在实验前冻结，只用于判断 Pipeline/Subgraph 或其他候选是否切默认；一旦根据其失败继续调方案，就降级为 dev，并重新准备未污染的保留集；
- **required contract/security Scenario**：持续验证 ACL、citation、预算、状态和 outbound 等确定性合同，可以反复运行，不承担开放效果估计。

默认切换必须在相同 corpus revision、runtime contract 和可比 provider 条件下使用 held-out decision Scenario；涉及模型波动时需要多轮证据，不能用单次通过切默认。具体分集数量由后续 catalog plan 决定。

## 5. 能力路线总览

| 里程碑 | 能力切片 | 主要依赖 | 关键结果 | 路线属性 |
|---|---|---|---|---|
| P0 | 阶段入口与合同冻结 | M28 验收 | 当前/目标差距、状态/API 迁移方案、首批 Scenario 与安全清单 | 主线必做 |
| P1 | 可信知识、Evidence 与安全地基 | P0 | 单一事实源、可重建发布、Text2SQL 隔离、Evidence/citation、outbound seam | 主线必做 |
| P2 | 确定性 RAG 垂直切片 | P1 | 独立 Knowledge Tool、ACL 双检、citation 闭环、RAG baseline 与首批 Eval | 主线必做 |
| P3 | 顶层 LangGraph Harness 与 Router | P2、现有 Text2SQL | SQL/RAG 路由、统一状态、受控 Tool 接入、首版 Evidence Gate | 主线必做 |
| P4 | 有界 Agent Loop、短期状态与上下文治理 | P3 | 结构化失败恢复、澄清恢复、Evidence 复用/失效、最小 Context Builder | 主线必做 |
| P5 | 保守 Hybrid | P3、P4 | 薄计划、双 Evidence 合成、partial/conflict/增强降级 | 主线必做 |
| P6 | 有界 RAG Subgraph 对照 | P2、P4 的失败证据 | 同 interface 实验 adapter、held-out A/B、默认路径决策 | 实验 adapter 必做；默认化条件引入 |
| P7 | 安全、Trace、Eval 与演示收口 | P5、P6 及全部横切合同 | required Gate、runtime identity、回归与阶段验收故事 | 主线必做 |

主干为 `P0 → P1 → P2 → P3 → P4`；P4 之后分成 `P5 Hybrid` 与 `P6 RAG Subgraph A/B` 两条能力支线，二者都完成后进入 P7 收口。这里表示依赖而非要求并行开发：实际可以按当时失败证据先做 P5 或 P6。Eval、Trace、安全和出站不是最后才补的横切模块：P0 先定义合同，P1/P2 建首批断言，后续每个里程碑同步扩展，P7 只负责完整门禁和阶段收口。

## 6. P0：阶段入口与合同冻结

### 目标

把当前 Text2SQL 产品合同与 Phase 4 新语义之间的兼容问题前置解决，先定义可评测的正确行为，再选择实现细节。

### 参考检查点

P0 先以 DataPilot 当前代码和 `docs/state/` 为事实依据，再读取 `docs/phase4-reference.md` 的“当前基础”“Eval、运行身份与失败归因”和“路线对齐状态”。外部项目此时主要用于发现合同缺口与反例，不能替代现状 inventory；P0 module plan 必须留下首份参考复核记录，格式见第 16.1 节。

### 主要交付物

- Phase 4 能力 inventory：确认 `/api/query`、`AgentResponse`、Trace、Eval、RBAC、Schema Retrieval、`knowledge_docs` 与 seed 的当前边界；
- 状态四轴和稳定 reason code 的语义草案，覆盖 SQL/RAG/Hybrid、clarify、unsupported、insufficient evidence、partial、blocked 与 external unavailable；
- 公开响应迁移方案：内部 Evidence 与状态先稳定，再决定对外字段如何兼容投影；
- 首批 canonical Scenario 设计：至少覆盖纯 SQL 回归、纯 RAG、Hybrid、证据不足、ACL、文档投毒、外部不可用、partial 和澄清，并在 catalog 设计中区分 diagnostic/dev、held-out decision 与 required contract/security 三种用途；
- 首批知识 inventory：把 10 条 seed 逐条标为采用、重写、拆分、合并或淘汰，并为拟纳入内容指定权威来源、用途、数据分类和角色；
- 当前 Text2SQL 远程 Qwen payload inventory，以及 RAG 新增数据类别的初始 outbound policy 草案；Router、Evidence 充分性判断、答案合成、Query Rewriting 和 Eval Judge 等模型节点按用途分别登记；
- P1/P2 的 deterministic fixture 与测试边界，不要求真实 provider 才能验证核心合同。

### 验收标准

1. 同一个示例不会再用 route 同时表达执行失败、回答不完整和安全拦截；
2. 每个首批 Scenario 都能说明 authority reference、预期状态、所需 Evidence、required/advisory assertion 和 dev/held-out/contract-security 用途；
3. 知识 inventory 中不存在“数据库 seed 和 Markdown 同时是权威正文”的条目；
4. 已列出 `knowledge_docs` 从 Text2SQL 全部入口迁出的检查范围，而不只修改 RBAC；
5. 未确定的模型、索引、检索与循环参数仍保持开放；
6. G0、G1 的用户选择已记录，后续 module plan 不需要重新猜语义。

### 决策门

- **G0：公开响应迁移**。在“同一端点增量扩展并提供兼容投影”与“新版本端点/响应模型”之间确认；见第 15 节。
- **G1：首批正式 corpus 与数据分类**。确认具体文档、用途、角色 allowlist 和允许的外部接收方；没有确认的内容不得进入正式索引或远程模型。

## 7. P1：可信知识、Evidence 与安全地基

### 目标

建立 RAG、Hybrid、Trace 和 Eval 共用的事实基础，使知识原件、运行时投影、Evidence、citation、权限和出站都具备稳定语义。

### 参考检查点

重点复核 WrenAI 的 source/index 分离与成功后推进版本、Alibaba DataAgent 的替换式更新，以及 GustoBot、DB-GPT 中来源未贯穿 Tool/回答的反例。借鉴发布纪律和 interface seam，不照搬完整语义编译层、平台服务结构或新旧知识接口并存。

### 能力范围

#### 7.1 知识原件与发布

- 把已确认的 seed 草稿整理成可审查 Markdown；短政策优先保持天然知识单元，不为了向量检索强制切碎；
- 指标说明由 `metrics.yaml` 生成或校验，明确“回答证据 / 分析约束 / 生成上下文”用途；
- 建立稳定 document、revision、content identity、anchor、status、有效期、ACL、data classification 与 corpus identity；
- ingestion 输出 manifest，能够从 document revision 定位全部派生 chunk；
- 新 revision 采用构建、校验、切换的发布顺序，失败不推进 active corpus identity；
- 索引可删除重建，重建不修改权威原件。

#### 7.2 Text2SQL 与知识正文隔离

统一检查并迁移所有可能暴露 `knowledge_docs` 正文的入口：

- SQL Guard/RBAC 的可见表；
- Domain Schema 与 Schema Retrieval 文档构建；
- schema descriptions、relations、few-shot、旧 case 与测试假设；
- prompt、Trace、错误消息与 demo 展示；
- 当前事实文档与公开说明，包括 `docs/state/database-current-state.md` 的 RBAC 事实、`docs/state/AI_CONTEXT.md` 的最新安全快照、`docs/state/AI_CONTEXT_CHANGELOG.md` 的迁移记录，以及受影响的 runbook、canonical Eval catalog、当前测试和 demo 能力描述；
- 历史 artifact 只读兼容，不因迁移被改写。

首版默认不提供知识目录 SQL 查询。若以后确有目录统计需求，必须另设不含正文的安全 metadata 投影，并执行与 Knowledge Tool 等价的逐文档授权；不能因为“只查标题/数量”就绕过文档安全。

#### 7.3 Evidence、citation 与安全投影

- 建立统一 Evidence 公共外壳和 Document/SQL typed payload；
- 明确内部完整 Evidence、节点 Context、JSONL Trace、长期 Eval artifact 和 AgentResponse 的不同投影；
- citation ID、EvidenceRef、claim support 与 anchor 由代码构造和校验；
- AuthorizationDecision、RetrievalDiagnostics、RuntimeIdentity 与 OutboundDecision 独立演进；OutboundDecision 还要区分模型节点用途，不能因 provider 相同而继承授权；
- 长期 artifact 默认保存 identity、hash、摘要和白名单诊断，不保存完整敏感正文、完整结果行或密钥。

### 主要交付物

- 首批经审查知识原件与 corpus manifest；
- 可重建 ingestion/index lifecycle 与失败回滚证据；
- Evidence/citation 最小合同和各消费者安全投影；
- 文档 ACL 与 outbound policy seam；
- `knowledge_docs` Text2SQL 隔离迁移及反绕过测试；
- corpus drift、陈旧索引、未授权文档和伪指令的确定性测试 fixture。

### 验收标准

1. 任一 Document Evidence 能回到明确 document revision 和原文 anchor；
2. 删除派生索引后可从权威源重建：corpus hash 与来源 revision 一致，相同 build recipe 可识别和比较；新的物理索引具有独立 build/index identity，并通过 manifest 指回来源与构建配置；构建失败不会切换到半成品或诱导复用旧脏索引；
3. Text2SQL 的 Schema、retrieval、prompt、RBAC 和测试路径都不再暴露知识正文；
4. 未授权内容在候选、生成上下文、citation、响应和长期 Trace 中都不可见；
5. 指标说明与 `metrics.yaml` 不形成第二套可独立编辑口径；
6. outbound 默认拒绝，缺少显式策略的 adapter 或模型节点不能静默外发；同一 provider 的不同用途有独立授权与保守降级测试；
7. 合同测试不依赖真实向量库或远程模型。

### 决策门

- **G2：运行时投影形态**。基于 P1 prototype 决定保留并升级现有 `knowledge_docs` 为目录/投影，还是采用其他运行时 catalog；无论选择什么，权威源与公开合同不变。
- **G3：正式 corpus 发布**。只有内容审查、ACL、data classification、anchor 和一致性校验全部通过后，才能成为 P2 默认 corpus。

## 8. P2：确定性 RAG 垂直切片

### 目标

先做一个可复现、可隔离测试的 RAG 基线。P2 使用 Knowledge Tool 外部的薄应用流程串起“取证 → Evidence Gate → Answer Composer → Citation Validator”，证明完整闭环；这些共享组件在 P3 由 LangGraph 直接复用，不形成第二套回答链。

### 参考检查点

重点复核 agentic-rag-for-dummies 的文档切分、Knowledge Tool 和实际 retrieval context 留存，以及 DB-GPT Resource reference 与新 Tool 返回合同的差异；GustoBot 用作“最终拼 sources 但中间身份断裂”的反例。首版只吸收稳定身份、真实上下文和 citation 闭环，不继承参考项目的 chunk、top-k、parent/child 或检索默认值。

### 能力范围

- Knowledge Tool 对外只暴露当前问题/已确认条件、调用者、证据要求、预算与既往尝试，返回 RetrievalOutcome、Document Evidence、稳定 reason code 和诊断 reference；
- Tool 内的确定性 Pipeline 依次完成权威目录过滤、候选检索、选择/去重、生成前 ACL 复核和 Evidence 构造；它不生成最终用户答案，不绑定最终 claim-to-Evidence citation，也不决定最终 `answer_status`；
- Tool 外的共享 Evidence Gate 判断证据充分性，Answer Composer 只使用被允许的 Evidence 生成 claim，Citation Validator 校验最终引用；顶层薄流程把 Tool 的具体取证事实投影成 `insufficient_evidence` 等产品状态；
- 记录四阶段 Evidence，不用单个 `docs_used` 覆盖候选、选中、入模和引用；
- 找不到适用 Evidence 时，Tool 返回 `no_candidate`、`no_authorized_evidence`、`stale_revision` 等具体取证结果；最终 controller 再决定 `insufficient_evidence`、blocked 或其他 answer/safety 状态，不依赖模型常识补公司政策；
- 文档正文按不可信数据处理，不能触发系统指令、改写授权或诱导 Tool Call；
- 首版优先建立确定性/关键词与可替换检索 seam；是否加入远程 embedding、混合检索、rerank、parent/child 或 query rewrite 留给后续实验。

这里的“确定性 RAG Pipeline”只指 Knowledge Tool 内的取证控制流、授权、Evidence 与失败语义可复现。Tool 外的 Gate/Composer 若使用远程模型，必须先通过 G1/G3 并取得对应模型节点用途的 OutboundDecision；测试仍需有不联网的 deterministic adapter 和保守降级。

### Eval 同步建设

首批 RAG Scenario 与 typed assertions 至少覆盖：

- route 与 answer status；
- gold Evidence 候选覆盖和最终上下文覆盖；
- citation integrity 与原文可回查；
- 可结构化政策事实和适用条件；
- insufficient evidence；
- public/allowed/denied ACL；
- stale index 与 inactive revision；
- indirect prompt injection、伪 citation 与诱导 Tool Call；
- Trace/runtime identity 和 outbound decision。

### 主要交付物

- 稳定 Knowledge Tool interface 与确定性 Pipeline adapter；
- Knowledge Tool 外部可被 P3 复用的 Evidence Gate、Answer Composer、Citation Validator 与第一条端到端 RAG API 路径；
- citation 用户视图与内部 claim-to-Evidence 映射；
- retrieval-only baseline 和端到端 RAG baseline，二者报告分开；
- 首批 RAG Scenario、required Gate 与失败归因视图；
- Pipeline 的调用次数、延迟、上下文规模和 provider identity 观测。

### 验收标准

1. 同一固定 corpus 和 deterministic adapter 下行为可复现；
2. 答案中的 citation 全部来自本轮实际生成上下文，伪造或越权 ID 被代码拒绝；
3. 已有知识但未召回、召回但未使用、知识本身缺失能被分别归因；
4. ACL 在检索前和生成前均有测试证明，未授权文档不产生侧信道；
5. 外部 provider 不可用时 execution 与 answer 状态正确，不被判为政策事实错误；
6. retrieval-only 提升不会自动成为端到端默认切换结论；
7. Knowledge Tool 的调用者不需要知道内部索引、embedding 或排序实现，且 Tool 内外不会各生成一次答案或各自裁决最终 `insufficient_evidence`。

### 决策门

- **G4：首个在线检索默认**。从已验证 adapter 中选择 P3 的默认 RAG Pipeline；选择依据是闭环可靠性与可解释性，不是某次单项召回最高。
- 混合检索、rerank、parent/child 和远程 embedding 此时可以进入候选实验清单，但不得仅因参考项目采用就切默认。

## 9. P3：顶层 LangGraph Harness、Router 与统一状态

### 目标

让 LangGraph 成为唯一顶层 Agent Harness，在不拆散现有深模块的前提下，完成 SQL/RAG 路由、Tool 调度、Observation 保存、Evidence Gate 和统一响应状态。

### 参考检查点

重点复核 agentic-rag-for-dummies 的 `graph.py`、`graph_state.py`、`nodes.py` 中主图/子图职责、conditional edge、state reducer 和终止路径；用 Alibaba DataAgent 的固定编排理解深模块如何接入，用 GustoBot 检查多数据面 Router 的取舍。不得复制复杂 fan-out、多层 Prompt，或把 Text2SQL 内部步骤拆成顶层浅节点。

### 能力范围

- Router 按“是否需要重新取证、需要何种 Evidence”分类；明显问题可走确定性快路径，模糊问题可走结构化模型判断；具体比例与阈值不在 roadmap 固定；
- Router 失败或不确定时保守进入澄清/暂不可执行，不默认落到 RAG，也不把路由失败说成没有业务知识；
- 现有 Text2SQL pipeline 作为一个完整 Tool 接入，成功返回 SQL Evidence，失败返回稳定错误；
- P2 Knowledge Tool 作为一个完整 Tool 接入，Graph 不解析其检索后端细节；
- Graph state 落实 route、execution、answer、safety 四轴，并保存 caller、Tool Observation、EvidenceRef、reason code、预算和终止事实；
- 直接复用 P2 已验证的 Evidence Gate、Answer Composer 和 Citation Validator：Gate 先覆盖 ACL、revision、必需 Evidence、允许动作和预算等硬约束，再调用结构化充分性判断器；Composer 只在 Gate 允许后生成 claim，Validator 最后检查 citation；
- 顶层 controller 根据 Tool 的 RetrievalOutcome、GateDecision 和生成/校验结果，唯一决定最终四轴状态以及回答、澄清、停止或允许的下一动作；
- 判断器超时、解析失败或结果不稳定时，确定性降级到澄清、证据不足或安全 partial，不追加无界循环。

### API 与兼容

- 内部新状态和 Evidence 不应全部直接暴露；AgentResponse 只提供用户和前端需要的安全投影；
- `docs_used` 可作为兼容视图，但不能继续被内部模块当事实源；
- SQL 旧成功路径在新 Harness 下应保持业务结果、SQL Guard 与可解释 Trace，不因接入 LangGraph 改写 Text2SQL 内部计划；
- clarify、unsupported、partial 和 blocked 按四轴表达，具体公开字段按 G0 方案实施。

### 主要交付物

- 顶层 LangGraph 固定状态图和稳定 Graph invocation seam；
- Router 数据集与确定性/模型 fallback 行为；
- Text2SQL/Knowledge 两个受控 Tool adapter；
- 首版 Evidence Gate、结构化 action/reason code 和保守降级；
- AgentResponse/Trace/Eval 的状态兼容迁移；
- SQL 与 RAG 代表场景的 Graph 垂直回归。

### 验收标准

1. SQL 问题只调用 Text2SQL Tool，RAG 问题只调用 Knowledge Tool，模糊/不支持问题不会伪装成某个成功 route；
2. Graph 不依赖 Text2SQL QueryPlan 或 RAG 检索实现细节；
3. Tool 失败后先形成结构化 Observation 与状态，再决定下一步，不直接让模型自由补答；
4. Evidence Gate 判断器失效时走确定性保守降级；
5. route、execution、answer、safety 在响应、Trace 与 Eval 中保持一致；
6. 旧 SQL 安全回归通过，知识正文仍无法经 Text2SQL 旁路访问；
7. Graph 中没有只转发参数、没有独立决策意义的大量浅节点。

## 10. P4：有界 Agent Loop、短期状态与上下文治理

### 目标

在顶层 Harness 内形成真正受控的 `Action → Observation → Evidence Gate → Next Action`，同时支持同一 thread 的澄清恢复与有限追问，而不进入开放 ReAct 或长期记忆平台。

### 参考检查点

重点复核 agentic-rag-for-dummies 的预算、状态 reducer、澄清/恢复、fallback 与停止路径；DB-GPT 的 ReAct、长上下文压缩和通用工具体系主要作为复杂度与权限面反例。只借鉴有界状态迁移和最小上下文方法，不继承开放动作空间、默认长历史压缩或平台化 memory。

### 能力范围

#### 10.1 有界恢复

- 只为明确可恢复的 reason code 提供下一动作；知识缺失、权限拒绝和不可恢复外部故障不能靠循环解决；
- 每次动作记录原因、已消费预算、前后 Evidence 变化和终止依据；
- 重复动作没有新增 Evidence 时应停止，不通过“换一种说法再试”掩盖失败；
- P4 的顶层 Loop 只负责全局恢复：用户澄清后恢复、决定是否允许重新调用 Tool、跨 Tool 补齐另一类 Evidence、Evidence 失效后的重新取证、partial、全局预算与停止；
- 顶层再次调用 Knowledge Tool 时只表达“仍缺少哪类 Evidence”和新的已确认条件，不直接指定 query rewrite、parent expansion、rerank 或其他内部检索策略；
- P4 至少跑通一种顶层恢复切片，优先选择用户澄清后恢复或结构化 Tool 失败后的保守处理；RAG 内部改写和上下文扩展统一留给 P6 Subgraph。

#### 10.2 澄清与 thread 内状态

- 缺少月份、对象、范围或其他必要条件时暂停并返回结构化澄清；
- 用户补充条件后从同一 thread 恢复，复用仍有效的任务状态，不重新生成一张无关答卷；
- 支持基于上一轮结果的有限追问，但必须重新判断旧 Evidence 是否支持新 claim；
- 采用 LangGraph thread state 或轻量 checkpoint 形成暂停/恢复能力；不在此阶段建设跨会话画像、长期偏好或通用记忆检索。

#### 10.3 Context Builder

- 根据当前节点选择问题、已确认条件、必要历史和最终 Evidence；
- Tool 长结果使用安全结构化摘要、fingerprint 和 EvidenceRef，Trace 可以保留更完整诊断，但不原样回灌模型；
- 对话增长时先裁剪无关历史，保留政策例外、时间条件、适用角色和 SQL 口径等高风险事实的原始 reference；
- 摘要和压缩不能替代 Evidence identity，复杂多层 compact 留到长会话 Eval 证明需要之后。

### Eval 同步建设

- 正确 Tool 和下一动作选择；
- 无意义重复调用与停止正确性；
- 运行时 Evidence Gate 的结构化输出、失败降级和允许状态迁移；
- 澄清后恢复、指代解析、Evidence 复用与 revision/权限变化后的失效；
- Context Builder 实际入模内容和裁剪后关键条件保真；
- 顶层重新调用 Knowledge Tool 时只传递缺失 Evidence requirement 和已确认条件，不能越权干预 adapter 内部检索动作。

### 主要交付物

- 有界 controller、预算与终止 reason code；
- 澄清/恢复和有限多轮的 thread state；
- Context Builder 与 Evidence reuse/invalidation；
- 至少一个顶层澄清或结构化 Tool 失败恢复切片；
- 顶层 loop typed assertions、全局预算与调用成本观测。

### 验收标准

1. 每条路径都存在可枚举终止状态，不依赖模型自觉停止；
2. 不可恢复错误不会触发重复 Tool Call；
3. 恢复动作必须产生可观察的新 Evidence 或正确停止；
4. 澄清后恢复保留用户已确认条件，且不绕过权限与 revision 复核；
5. 旧 Evidence 失效时重新取证，不能把历史答案当永久事实；
6. Trace 不保存模型原始思维链，但能解释 Action、Observation、Gate 与 Next Action；
7. Context Builder 的输入可以被 Eval 直接检查，不靠最终答案反推模型看见了什么；
8. 顶层 Loop 不直接改写检索 query 或执行 parent/context expansion，也不会与 P6 Subgraph 对同一失败各循环一次。

### 决策门

- **G5：首个顶层恢复切片**。在条件澄清恢复、Evidence 失效后重调 Tool、跨 Tool 补证据或结构化失败后的安全 partial/停止中选择一个最有真实价值的切片；query rewrite 和上下文扩展不在此门决定。

## 11. P5：保守 Hybrid

### 目标

把数据库事实与业务规则组合成有出处的分析结论，同时让分支失败、冲突和展示增强失败都具备清楚边界。

### 参考检查点

重点复核 Alibaba DataAgent 的业务 Evidence 贯穿问题增强、计划和报告的固定链，以及 GustoBot 的多数据面路由与 sources 汇合。借鉴跨能力只保留薄计划、核心结果优先的思想，不消费两个自然语言子答案，不照搬完整 Plan 模型或“任一后端命中即可合成”的假设。

### 能力范围

- 顶层只使用很薄的跨能力计划，表达子任务类型、依赖、期望 Evidence、required/optional 和失败后允许保留的结果；
- SQL 与 RAG 分支各自保留内部计划，向上只返回 typed Evidence 和结构化状态；
- 合成器消费原始 SQL/Document Evidence，不消费两个自然语言子答案；
- 同时声称“数据表现如何”和“按规则应如何处理”的 claim，默认要求 SQL 与 RAG 两支都可用；
- SQL 可用、RAG 不足时只保留数据结果并说明缺少政策依据；RAG 可用、SQL 不足时只说明一般政策，不声称已针对实际数据成立；
- 两支证据冲突时展示冲突和来源，返回证据不足或需人工确认，不自动选择更像真的一方；
- 一支被权限拦截时不得泄露其标题、命中或存在性；另一支是否可返回由确定性安全合同决定；
- 合成、图表或长报告失败时不重跑已成功分支，优先保留表格、citation 和解释清楚的 partial result。

### 主要交付物

- 薄 Hybrid plan 与 required Evidence 合同；
- SQL/RAG 分支、汇合、冲突与 partial 状态；
- 双来源 claim/citation 视图；
- 代表性业务演示 Scenario，例如数据异常结合政策解释，但正式题面以 P0 canonical catalog 为准；
- Hybrid branch use、partial、安全与增强降级 typed assertions。

### 验收标准

1. 完整 Hybrid claim 能同时回到 SQL Evidence 和 Document Evidence；
2. 缺任一必需分支时不生成跨来源结论；
3. partial 明确说明已有结果、缺失证据和不能下的结论；
4. 合成失败不产生第二次 SQL/RAG 执行，也不丢失已完成 Evidence；
5. 分支冲突不会由模型静默消解；
6. SQL 与文档安全分别生效，共享身份但不共享一套 allowlist 实现；
7. 图表/报告增强失败不拖垮核心结果。

### 决策门

- **G6：optional 分支放宽**。只有 Eval 证明某类分支确实只是增强项，且不会造成误导或侧信道，才允许从 required 调整为 optional；不先用 best-effort 提高表面完成率。

## 12. P6：有界 LangGraph RAG Subgraph 实验

### 目标

在不改变 Knowledge Tool、Evidence、ACL、Router、Hybrid、Trace 和 Eval 合同的前提下，完成一个小型、有界的 RAG Subgraph adapter，并用同 corpus A/B 回答“Agentic RAG 是否值得成为默认路径”。

### 参考检查点

重点复核 agentic-rag-for-dummies 的 `graph.py`、`nodes.py`、`graph_state.py` 和 `tools.py`，核对主图/研究子图边界、Tool loop、context accumulation、fallback 与终止。参考的目的，是设计一个同合同的实验 adapter；不默认采用其 fan-out、强制搜索、parent/child、query rewrite 或 history compact，恢复动作仍必须来自 DataPilot 的 dev 失败簇。

### 实验约束

- Pipeline 与 Subgraph 通过同一 Knowledge Tool interface；调用者不知道内部 adapter；
- Subgraph 必须体现 `Action → Observation → Evidence Gate → Next Action`，不能把固定 Pipeline 机械拆成节点；
- 只选择一种由真实失败簇驱动的再取证动作，例如受控改写、上下文扩展或独立证据需求拆分；
- Subgraph 无权调用 SQL、放宽 ACL、自行合成 Hybrid、决定最终用户答案、扩大顶层预算或绕过 outbound policy；
- 顶层 controller 为一次 Knowledge Tool 调用分配子预算；Subgraph 的模型调用、检索动作和上下文扩展全部计入顶层总预算，只能消费分配给它的剩余预算；
- 顶层只向 Knowledge Tool 表达 Evidence requirement 与已确认条件，Subgraph 自己管理 query rewrite、parent/context expansion 或文档子问题检索，禁止两层对同一取证失败分别循环；
- 知识缺失、权限拒绝和外部服务不可用必须保守停止；
- 恢复动作只根据 diagnostic/dev Scenario 的失败簇设计和调试；是否切默认只读取实验前冻结、未被用于调参的 held-out decision Scenario；ACL、citation、预算等 required contract/security case 持续回归；
- A/B 使用相同 corpus revision、Evidence/citation 合同、runtime contract 和可比较 provider 条件；涉及模型时取得多轮证据，具体参数与分集数量由实验计划固定，roadmap 不提前给默认值。

### 对照维度

- gold Evidence 候选与最终上下文覆盖；
- answer/business correctness 与 citation support；
- insufficient evidence、停止和恢复正确性；
- 无意义 Tool Call 和重复 Evidence；
- 延迟、调用次数、上下文规模和可获得的成本；
- ACL、outbound 和 prompt injection 行为是否与 Pipeline 等价；
- 调试复杂度与失败可归因性。

### 主要交付物

- 有界 RAG Subgraph adapter；
- Pipeline/Subgraph 的 dev 诊断报告、held-out 默认决策报告和 contract/security 回归视图；
- 恢复动作的收益、失败结构、成本和适用范围说明；
- 默认 adapter 与 fallback 的决策记录。

### 验收标准

1. 两种 adapter 的 Knowledge Tool 调用合同与返回 Evidence 语义一致；
2. Subgraph 没有第二个全局控制权，ACL、出站和父子预算测试无法被子图绕过；
3. 顶层 controller 与 Subgraph 不会对同一文档取证失败形成嵌套重复循环；
4. A/B 能区分真正新增 Evidence、只增加调用和偶然模型波动；
5. held-out decision Scenario 在默认决策前未参与恢复动作、Prompt 或参数调整；若被用于调试则有明确污染记录并退出保留集；
6. 无论是否切默认，都保留可复盘的实验证据；若没有多轮稳定净收益，Pipeline 继续作为默认和回退路径，不把“已实现 Subgraph”写成效果提升。

### 决策门

- **G7：RAG Subgraph 是否默认化**。只有证据覆盖、答案质量或停止/恢复正确性的稳定收益能够抵偿额外调用、延迟与调试成本时才切默认；否则保留实验 adapter 和面试复盘价值。
- **G8：检索增强是否进入默认**。parent/child、hybrid retrieval、rerank、query rewrite 等各自按单变量证据决定，不能打包成不可归因的“高级 RAG”。

## 13. P7：安全、Trace、Eval 与演示收口

### 目标

把前面逐步建立的能力收成一条企业化、可解释、可评测、可展示的 Phase 4 基线；P7 不再新增大能力。

### 参考检查点

P7 以 DataPilot 的 M27 Scenario/typed assertion、JSONL Trace 和最新 Phase 4 运行证据为主；外部项目只用于复查 citation 断裂、路径能力不一致、成功样本均值和平台复杂度等反例。不得用外部项目自带 notebook、总分或 demo 代替本项目 required Gate 与 held-out 决策证据。

### Trace 收口

每次运行至少能通过 trace id 关联：

- caller/thread identity 的安全摘要；
- route 决策和是否需要重新取证；
- Tool Call、Observation、分支状态和稳定 root cause；
- 循环动作、次数、预算和终止原因；
- 四阶段 Evidence 的安全投影与 citation 映射；
- corpus/document revision、index、retrieval/adapter、model/provider 等 resolved runtime identity；
- ACL、outbound decision、被删除或摘要化的数据类别；
- Tool 延迟、调用次数、上下文规模和可获得的 cache hit/miss；
- 用户反馈与 Eval assertion 对本次运行的引用。

JSONL 继续作为本地主事实。LangFuse Cloud 只有在上传 allowlist、脱敏、data classification 和旁路失败降级通过安全 case 后才能由用户明确恢复；即使恢复也不能成为业务或 Eval 唯一依赖。

### Eval 收口

Phase 4 canonical catalog 按第 4.6 节同时维护 diagnostic/dev、held-out decision 和 required contract/security 三种用途，并形成以下分层能力视图：

| 维度 | required 主门 | advisory / 趋势 |
|---|---|---|
| Route / 四轴状态 | 明确题面与确定性状态合同 | 模糊边界的人工分析 |
| Retrieval | 封闭语料核心题的 gold coverage | Recall/MRR 等离线趋势 |
| Citation | identity、入模关系、权限、anchor 可回查 | 开放表达的支持度/覆盖度 judge |
| Answer / Faithfulness | 可结构化事实、适用条件、确定性越界 | 开放语义完整性与表达质量 |
| Hybrid | 必需分支、原始 Evidence、partial/conflict | 长报告质量 |
| Agent Loop | 允许动作、预算、停止、无重复调用 | 恢复收益与成本趋势 |
| State / Context | 澄清恢复、Evidence 失效、关键条件保真 | 更长对话体验 |
| Safety / Outbound | ACL、投毒、旁路、出站默认拒绝 | 供应商成本和保留策略观察 |
| Trace / Runtime | 证据链和 resolved identity 完整 | 延迟、token、上下文规模趋势 |

最终基线仍遵守同合同、同 corpus、同 runtime identity 的可比性纪律。任何默认模型、embedding、检索策略或 Subgraph 切换都必须使用未污染的 held-out decision Scenario，并有单变量、多轮证据和用户确认；dev 结果用于诊断，不单独承担默认切换结论。真实 LLM Eval 仍按 runbook 的一次精确授权执行。

### 项目展示与面试交付

- 一个 SQL、一个 RAG、一个 Hybrid、一个澄清恢复、一个安全拒绝/证据不足的可复现实例；
- 每个实例都能从用户答案回到 citation/Evidence，再回到 Tool Observation 和 Trace；
- Pipeline vs RAG Subgraph 的真实 A/B 故事，能够解释为什么采用或不采用更复杂 Agentic RAG；
- 文档 ACL 与 Text2SQL 隔离的反绕过案例；
- 外部 provider 失败时仍能展示状态正交、partial 或保守停止；
- 一份 Phase 4 capability matrix，区分已完成、实验保留、未进入范围。

### 阶段总验收

Phase 4 只有在以下条件全部满足后才进入收工：

1. 第 4 节全部跨阶段不变量通过 required contract/security case；
2. 权威知识、可重建发布、Text2SQL 正文隔离、文档 ACL 与侧信道防护形成闭环；
3. Knowledge Tool 只负责取证，Gate/Composer/Validator 与顶层 controller 的职责唯一，RAG citation 可回查且缺证据不乱答；
4. 顶层 LangGraph、有界全局 Loop、短期状态和 Context Builder 可观察、可终止，不与 RAG Subgraph 形成双循环；
5. Hybrid 的必需分支、partial、conflict 和增强降级语义通过验收；
6. Pipeline 与 RAG Subgraph 完成未污染 held-out、多轮、同合同 A/B，并留下明确默认/fallback 决策；
7. outbound policy 覆盖实际接收方、模型节点用途和数据类别，未授权节点保守降级，Cloud 未授权时保持关闭；
8. Trace 与 Eval 使用同次运行真实 Evidence，状态、分母、runtime identity 和 `not_observed` 语义可信；
9. Text2SQL 核心回归通过，并完成 `finish-module → finish-docs → 用户人工检查 → accept-module`。

## 14. 条件引入与 Phase 4 后能力

### 14.1 达到证据条件后才引入

| 候选能力 | 引入条件 | 默认不做的原因 |
|---|---|---|
| parent/child | 长文 gold Evidence 经常只命中碎片，补 parent 稳定改善 citation support | 当前短政策本身是天然知识单元，双层存储会增加一致性和引用复杂度 |
| hybrid retrieval | 单路检索在术语/编号与自然语言问题上呈现稳定互补 | 单次召回提升不证明端到端收益 |
| rerank | gold 已进入候选但持续排不到最终 Context，额外成本和出站可接受 | 增加远程数据面、延迟和不可解释波动 |
| query rewrite | 首轮失败主要来自 query 表达，而不是 corpus、ACL 或 gold 错误 | 改写容易偏离用户条件并制造无意义循环 |
| 更宽松 Hybrid partial | 某分支被证明只是 optional，且不会误导或造成侧信道 | 首版优先防止“有数据没政策也给建议” |
| 轻量持久 checkpoint | 暂停/恢复和服务重启场景证明仅内存 thread state 不足 | 持久化引入过期、清理、权限变化与隐私语义 |
| PDF / 长文档 | 正式 Scenario 需要且 Markdown 不能代表原始来源 | OCR、多格式与复杂 anchor 会扩大阶段范围 |
| LLM Judge required | 与人工 gold 稳定对齐，失败语义、成本和可用性可接受 | Judge 失败不能影响确定性安全门 |
| LangFuse Cloud 恢复 | 上传 allowlist、脱敏、分类与失败降级通过安全 case | 外部观测不是主事实源 |

### 14.2 Phase 4 结束后再评估

- 跨会话长期记忆、用户画像、过期/纠错/删除治理；
- 多层 context compact、自动摘要与超长会话管理；
- 更开放的 ReAct/研究循环、并行 fan-out 和通用研究 Agent；
- 多 Agent 协作；
- GraphRAG、Neo4j、LightRAG 或另一套知识体系；
- 任意 Python/Shell 执行、自动写库、发消息等有副作用 Tool；
- 动态 Skills/Connector、多模型 Worker、通用知识管理/多租户平台；
- OCR、多格式全覆盖和大规模增量同步；
- WrenAI 级别的完整语义编译层；
- 在 DataPilot 内扩张成独立完整 Eval 平台。

这些能力不是“以后一定做”，而是只有出现能证明净收益的任务和 Eval 证据后才重新立项。

## 15. 需要用户确认的问题

以下事项不阻塞本文作为 roadmap 成立，但会改变 P0/P1 的具体 module plan；在进入对应实现前需要用户确认，本文暂不替用户固定。

### 15.1 公开响应如何迁移四轴状态

| 方案 | 优点 | 风险 / 后续影响 |
|---|---|---|
| A. 同一 `/api/query` 增量增加 execution/answer 状态和结构化 citations，保留 `docs_used` 等兼容投影 | 迁移成本低，适合当前单体项目与 demo；内部合同可先做深 | 现有严格 typed client 仍需适配；`route=none` 等新值要明确兼容策略 |
| B. 新建版本化响应/端点，旧端点保留 SQL 兼容 | 边界最清楚，不会让旧消费者误解新状态 | 维护两套投影和测试，项目规模下可能形成重复路径 |

**建议**：优先 A。内部先使用四轴状态和 typed Evidence，对外采用增量字段与兼容投影；若 P0 inventory 发现已有不可控严格客户端，再转 B。

### 15.2 首批正式 corpus 的具体范围

| 方案 | 优点 | 风险 / 后续影响 |
|---|---|---|
| A. 以 10 条 seed 为草稿，重写为政策/客服/安全规则；补由 `metrics.yaml` 生成的指标说明，只纳入有 canonical Scenario 的内容 | 范围可控、容易形成 gold Evidence、ACL 和 Hybrid 闭环 | 文档形态偏短，暂时不能证明长文检索能力 |
| B. 同时扩充产品说明和长政策文档 | 展示面更广，可较早验证结构切分 | corpus 审查、anchor、切分和 Eval 工作量显著增加，容易提前引入 parent/child |

**建议**：先 A；只有目标 Scenario 明确需要时，再在 Phase 4 中追加少量长文作为条件实验，不以文档数量作为完成标准。

### 15.3 Phase 4 的初始出站政策

| 方案 | 优点 | 风险 / 后续影响 |
|---|---|---|
| A. 先审计现有 Qwen payload；本地/deterministic 完成检索与测试基线，仅对明确标记允许外发的数据开放指定模型节点用途，LangFuse Cloud 继续关闭 | 与当前运行现实兼容，也保留确定性安全边界 | 需要维护细分授权矩阵，部分受限文档或模型节点可能只能走本地/保守降级 |
| B. Phase 4 全部本地处理 | 边界最简单 | 当前没有已确认的本地生成主链路，可能扩大模型部署范围并拖慢主线 |
| C. 模拟 corpus 默认允许远程 embedding/rerank/generation/Cloud | 实验方便 | 把“是模拟数据”误当成正式授权，无法展示企业出站治理，也扩大泄漏和供应商依赖面 |

**建议**：采用 A。最终允许哪些文档、query、SQL rows 和答案发送给哪个 provider、哪个模型节点用途，必须在 G1 逐类确认；不能从当前 Qwen 已在用推导 Router、充分性判断、答案合成或 Eval Judge 自动获批。

## 16. 参考项目使用合同与导航

外部项目参考是 Phase 4 的必需输入，但不是路线事实源。参考顺序固定为“当前 roadmap 合同 → 最新 state 与失败证据 → `docs/phase4-reference.md` 对应分析 → 外部项目定点源码”；没有任何项目同时覆盖 Evidence、ACL、出站、Hybrid 与 Eval，因此只能按问题借鉴局部设计或反例。

### 16.1 Module plan 的参考复核门禁

每个 Phase 4 module plan 定稿前必须完成一次与该能力切片相称的参考复核，并在 plan 或 `docs/notes/<module>-notes.md` 留下精简记录：

| 必填项 | 要回答的问题 |
|---|---|
| 当前问题与证据 | 当前代码缺口或 Eval 失败簇是什么，为什么需要这项设计？ |
| 优先参考与源码入口 | 参考哪个项目、哪份 analysis、哪些直接相关源码？ |
| 借鉴内容 | 借鉴 interface、控制权、状态、失败处理还是评测方法？ |
| DataPilot 适配 | 现有 Text2SQL、安全、Trace、Eval 和规模约束要求怎样调整？ |
| 明确不照搬 | 哪些平台能力、参数、Prompt、类结构或默认行为不进入本模块？ |
| 验证方式 | 用什么合同测试、Scenario、A/B 或安全 case 判断是否真正有收益？ |

执行时还要遵守以下纪律：

1. 不能只引用 analysis 摘要；影响 interface、控制权、安全或默认路径的结论，必须在开工时重新定点查看源码；
2. 不因参考项目采用某能力就继承其模型、Prompt、chunk、top-k、阈值、循环次数、存储组合或默认参数；
3. 当前项目的合同与失败证据优先。参考做法若不适配，可以明确不采用，也可以补充新项目、论文或官方文档；当前清单不是封闭候选集；
4. 新外部资料只能提供候选设计，默认路径切换仍由 DataPilot 自己的 required Gate、未污染 held-out 和可比运行证据决定；
5. 不为纯机械修改强行绑定参考项目。只有形成可复用设计结论、修正旧分析或新增重要入口时，才更新 `phase4-reference.md`。

### 16.2 里程碑与参考重点

| 里程碑 | 优先参考方向 | 主要使用方式 |
|---|---|---|
| P0 | DataPilot state、M27 Eval；reference 的现状与 Eval 章节 | 识别合同缺口和外部反例，不让外部架构替代当前事实 |
| P1 | WrenAI、Alibaba DataAgent、GustoBot、DB-GPT | 知识发布、替换式更新、Evidence/citation seam 与断裂反例 |
| P2 | agentic-rag-for-dummies、DB-GPT、GustoBot | 检索单元、真实 Tool context、结构化 reference 与 citation 闭环 |
| P3 | agentic-rag-for-dummies、Alibaba DataAgent、GustoBot | 顶层 Graph/state、固定编排、Router 与深 Tool 边界 |
| P4 | agentic-rag-for-dummies；DB-GPT 作为边界反例 | 有界状态迁移、预算、澄清恢复、停止和最小 Context |
| P5 | Alibaba DataAgent、GustoBot | 薄 Hybrid plan、原始 Evidence 汇合、核心结果与增强降级 |
| P6 | agentic-rag-for-dummies | 同 Tool 合同的 RAG Subgraph、内部循环与 fallback 对照 |
| P7 | DataPilot M27/Phase 4 证据优先；五项目反例 | Trace/Eval 收口、citation/路径一致性与复杂度复查 |

### 16.3 优先源码入口

| 能力 | 优先项目与源码入口 | 借鉴什么 | 明确不照搬什么 |
|---|---|---|---|
| 知识源与索引生命周期 | WrenAI：`references/WrenAI/core/wren/src/wren/memory/index_backend.py`、`references/WrenAI/core/wren/src/wren/memory/watch.py` | Markdown/source 与派生 index 分离；fingerprint 变化触发重建；成功后才推进版本 | 完整语义编译层、watch daemon 和其默认 backend |
| 替换式索引更新 | Alibaba DataAgent：`references/DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java` | 先形成新版本、失败清理、避免先删后写造成知识全失 | Java 类结构、平台服务层和在线管理体系 |
| 业务 Evidence 贯穿分析链 | Alibaba DataAgent：`references/DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java` | Evidence → 问题增强 → Schema/Plan → 分析/报告的固定控制思路；核心结果与展示增强分离 | 复制其完整计划模型、Prompt 串联方式或让知识覆盖数据库事实 |
| LangGraph state、主图/子图与实际 retrieval context | agentic-rag-for-dummies：`references/agentic-rag-for-dummies/project/rag_agent/graph.py`、`references/agentic-rag-for-dummies/project/rag_agent/graph_state.py`、`references/agentic-rag-for-dummies/project/rag_agent/nodes.py` | 主图/子图职责、conditional edge、Tool loop、state reducer、fallback/终止，以及实际工具结果留给回答与 Eval | 复杂 fan-out、开放研究循环、强制搜索、默认 parent/child 和复杂 history compact |
| 文档切分与上下文扩展 | agentic-rag-for-dummies：`references/agentic-rag-for-dummies/project/document_chunker.py`、`references/agentic-rag-for-dummies/project/rag_agent/tools.py` | Markdown 结构切分、child 命中后按需取 parent 的思想 | 直接继承其 chunk 参数、稳定 ID 方式或默认让所有短政策走 parent/child |
| Router 与多数据面 | GustoBot：`references/GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py` | 按数据形态和证据需求区分 SQL/知识等路径；观察 fallback 与 sources 汇合方式 | 多 Agent、多层 prompt、多存储包装和“某后端命中就天然正确”的级联假设 |
| 来源字段反例 | GustoBot：`references/GustoBot/gustobot/infrastructure/knowledge/vector_store.py` | 检查 source/url/anchor 是否真的贯穿索引和最终回答 | 只在最终响应拼 `sources` 就宣称 citation 闭环 |
| Knowledge Tool seam 与 reference 差异 | DB-GPT：`references/DB-GPT/packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/knowledge_retrieve.py`、`references/DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py` | 比较“只返回编号正文”的新 Tool 与“结构化 references”的 Resource，识别 interface 漂移 | 通用 Resource 平台、新旧接口并存、动态工具生态与整套 Agent 平台 |

以上路径均相对于 `D:/.Work/Practice/Python-Practice/`。优先入口的完整分析、适用条件和路线对齐状态见 `docs/phase4-reference.md`。

### 16.4 参考漂移与更新规则

出现以下任一情况时，module plan 必须重新核对相关源码，必要时同步更新 `docs/phase4-reference.md`：

- 准备引入此前仅为条件项或 Phase 4 后能力的设计；
- 参考项目版本、目录或关键行为变化，旧入口已无法证明原结论；
- DataPilot Eval 出现旧分析未覆盖的新失败簇；
- 新设计会改变全局控制权、Evidence、ACL、出站、状态或默认路径；
- 发现更合适的新项目、官方文档或研究证据。

更新 reference 时应记录“新证据修正了什么结论”，而不是删除历史语境后写成一直如此；若只是某个模块的一次性实现细节，留在 module notes，不膨胀公共参考地图。

## 17. 风险与控制

| 风险 | 早期信号 | 控制方式 |
|---|---|---|
| Evidence 变成万能大对象 | Router、前端、Eval 都依赖检索和授权内部字段 | 保持稳定外壳 + typed payload；诊断、授权、runtime 分离 |
| Tool 与顶层重复生成/裁决 | Knowledge Tool 和 Graph 各有答案、citation 或 `insufficient_evidence` | Tool 只返回 RetrievalOutcome/Evidence；Gate、Composer、Validator 与 controller 各自唯一负责 |
| Graph 变成浅节点集合 | 节点只转发参数，业务逻辑散落在边上 | 只有独立状态迁移/失败语义才成为节点；深模块保留内部控制 |
| 双事实源 | Markdown 与数据库正文可分别修改 | 单向发布、content identity 校验、投影漂移即失败 |
| ACL 只在向量 filter | 未授权候选已进入 prompt 或 Trace | 检索前过滤 + 生成前复核 + 侧信道测试 |
| Text2SQL 旁路 | Schema Retrieval 仍召回 `knowledge_docs.content` | 跨 RBAC/Schema/prompt/few-shot/case 的迁移清单与反绕过测试 |
| citation 只有文件名 | 引用无法定位 revision/anchor 或不是入模证据 | 代码分配 ID、四阶段 Evidence、claim-to-Evidence 校验 |
| Agent loop 掩盖知识缺失 | 重复搜索但 Evidence 没变化 | reason code allowlist、预算、无增量停止、调用冗余 assertion |
| 顶层与 RAG 子图双循环 | 同一取证失败被两层分别改写和重搜 | 顶层只管 Evidence requirement/全局恢复；子图只管文档内部动作；父预算覆盖子预算 |
| Eval 只看最终答案 | 不能区分没召回、没使用、引用错或合成错 | 一题一次执行、多 typed assertion、实际 context 进入 evidence |
| Agentic RAG 对照过拟合 | 用同一批题发现失败、调方案并证明收益 | dev/held-out/contract-security 分集；污染的 holdout 退出默认决策集 |
| 检索实验不可比较 | corpus、provider、参数和 case 同时变化 | resolved runtime identity、同 corpus/合同、单变量、多轮证据 |
| 远程能力静默扩大出站 | 新 adapter 直接发送 query/chunk/rows | outbound seam 默认拒绝，接收方/用途/数据类别逐项授权 |
| 短期状态变长期隐私仓库 | 完整历史和原文无限保存 | thread scope、最小状态、失效/清理语义、安全摘要与 reference |
| 项目展示压过主线 | 为 UI 同时引入长报告、多 Agent、GraphRAG | 演示围绕 SQL/RAG/Hybrid/Evidence/失败闭环，增强项可降级 |

## 18. Phase 4 推进原则

1. **先合同、再能力、后参数**：先定义正确行为和证据，再通过 Eval 选择检索、模型与循环细节。
2. **纵向切片优先**：每个里程碑都形成可运行、可追踪、可测试的闭环，不积累到最后一次集成。
3. **安全与 Eval 同步进入**：ACL、outbound、Trace 和 assertions 是每条能力的组成部分，不是收尾补丁。
4. **默认路径只靠证据切换**：参考项目、技术热度或单轮分数都不能直接改变默认模型、向量库、检索或 Subgraph。
5. **失败也是产品输出**：澄清、证据不足、partial、blocked 与 external unavailable 都要有稳定、可验收语义。
6. **复杂度必须有删除测试**：如果移除某层不会降低合同、可测试性或真实能力，就不应为了展示保留它。
7. **收工按项目流程执行**：每个完整模块结束时先固化 notes 和验证，再更新 state/dev-log，最后人工检查与 `accept-module`；README 只在阶段结束统一整理。

## 19. 修订记录

2. **2026-08-11 参考联动优化**：

   - 明确 `phase4-reference.md` 是无路线决策权但按能力切片必读的技术参考地图，并建立 roadmap → reference → 外部源码的读取顺序；

   - 为 P0–P7 增加参考检查点，将参考复核纳入 module plan 门禁，补充不机械照搬、允许新增参考和默认切换仍由本项目 Eval 决定的规则；

   - 第 16 节扩展为参考使用合同、里程碑映射、源码导航与漂移更新规则，避免参考项目只停留在阶段末尾的一张孤立表格。

1. **2026-08-11 审查修订**：

   - 明确 Knowledge Tool 只负责取证，最终 Evidence 充分性、答案、claim/citation 和产品状态分别由共享 Gate、Composer、Validator 与顶层 controller 负责；P2/P3 复用同一组件。

   - 分离顶层全局 Loop 与 RAG Subgraph 内部再取证，补父子预算和禁止双循环约束；P5/P6 改为 P4 后两条支线、P7 汇合。

   - Agentic RAG Eval 增加 dev、held-out decision、contract/security 分集；补 corpus/build recipe/physical index identity、按模型节点用途的 outbound 授权、状态文档迁移清单和 `graph.py` 参考入口。

   - 第 4 节固定为跨阶段合同事实源，各阶段与总验收收敛为能力和验收增量；Phase 4 总方向与三个待确认选择不变。
