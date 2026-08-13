# M31 可信证据与安全发布开发计划

> 状态：已确认可执行；实施推进到 G3 时等待用户最终发布确认
>
> 能力里程碑：Phase 4 P1「可信知识、Evidence 与安全地基」的第二个能力切片；承接 M30 的 staged catalog，闭环可信 caller、文档授权、outbound 裁决、typed Evidence/citation 完整性和安全发布。P1 可以由多个模块完成，M31 不进入 P2 的检索与问答链路。
>
> 主要问题：怎样让 M30 已治理的知识只有在身份可信、文档有权、用途允许、引用可验证且发布完整时，才成为可供后续 RAG 使用的 active corpus 和 typed Evidence。

## 1. 模块定义与范围判断

M30 已解决“知识从哪里来”和“Text2SQL 不能旁路读取正文”，但其结果明确停在 `staged`：没有可信 caller、正式文档授权裁决、outbound 强制门、Evidence/citation 运行合同，也没有 active 发布与旧版本保留。

M31 围绕一个可独立验收的问题形成闭环：**把 staged catalog 安全地发布成一个版本化 active corpus，并证明只有经过确定性身份、ACL、用途和 citation 校验的内容才能成为后续回答证据。** 用户完成本模块后可以理解并演示：为什么请求体角色不等于可信身份、为什么“检索到了”不等于“可以使用”、为什么 citation 不能只是文件名，以及新版本构建失败时系统怎样继续使用上一版。

本模块不再拆小，原因是 caller、ACL、outbound、Evidence 和发布共同构成 G3 的前置条件；只做其中一项会留下“已 active 但尚未证明可安全消费”的中间状态。它也不继续扩大到 P2：检索排序、Knowledge Tool、Evidence Gate、Answer Composer 和端到端 RAG 是另一条可单独演示与归因的能力闭环。

用户已确认发布存储采用**版本化 immutable release bundle**：authority source 仍是唯一正文事实源；release bundle 是由 builder 生成、带完整 identity、不可手工编辑的运行时投影。候选发布失败不移动 active pointer，上一版完整 release 继续可用。该选择避免重构 M30 刚验收的 authority revision 结构，也不把仅存于进程内存的对象冒充可恢复发布。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| M30 已验收；当前 Git 为 `7f2ca21`，工作树在本轮调查时干净 | M31 可以直接消费冻结的 staged contract，不应回改 M30 结论 | `docs/state/AI_CONTEXT.md`、`git log/status` |
| staged catalog 有 11 个 usable entries，corpus identity 为 `abdc9aed...`、build identity 为 `c5e6cf17...` | 内容已验证但尚未通过 G3，不能交给生成器或称为 active corpus | `engine/rag/catalog.py`、`docs/notes/m30-notes.md` |
| `StagedCatalog` 没有 active pointer、release history 或跨重启恢复 | 新 build 失败、服务重启和显式回滚没有稳定运行合同 | `engine/rag/catalog.py` |
| 当前 11 个 entry 全部 `public=false`，分别限制为 `admin/ops/customer_service/demo_user` | 任何把请求体 `user_role` 直接用于文档 ACL 的实现都会形成越权 | `domain_pack/kb_docs/*.md`、`metric_projections.yaml` |
| `QueryRequest.user_role` 是客户端自报字符串；Streamlit 角色也是用户选择 | 只能作为 legacy SQL 声明或 demo 输入，不能证明生产身份 | `app/schemas/agent.py`、`demo/streamlit_app.py`、M29 caller inventory |
| 当前没有 `AuthorizationDecision`、`OutboundDecision`、typed Evidence 或 Citation Validator 实现 | 后续模块若各自实现，会把安全逻辑散落到 Tool、Graph、Trace 和 Eval | `rg` 当前代码、`docs/notes/m29-phase4-entry-contract-notes.md` |
| `AgentResponse.docs_used` 和 `TraceRecord.docs_used` 仍是开放 dict；JSONL 还会保存完整 question/answer/rows | 它们不能作为 Evidence/citation 事实源，Phase 4 文档正文不能直接塞入旧字段 | `app/schemas/agent.py`、`engine/trace/recorder.py` |
| 现有 Qwen/DeepSeek、Schema embedding、LangFuse 等远程入口没有统一 outbound decision seam | 新 Knowledge 数据若复用 provider 配置，可能静默扩大外发范围 | M29 outbound inventory、`engine/nl2sql/*`、`engine/trace/*` |
| 新 Knowledge/RAG 远端用途已确认默认 deny，LangFuse Cloud 继续关闭 | M31 不需要选择新 provider，但必须让缺策略或错误用途稳定失败关闭 | M29 G1-O、`docs/state/AI_CONTEXT.md` |
| M27 当前合同为 `m27-v3` 且历史 artifact 只读；Phase 4 要使用独立合同 family | 不能向 M27 artifact 塞 caller/Evidence/citation 字段或混算分母 | `docs/state/eval-baselines.md`、M29 D2 |
| 当前没有 Knowledge 向量索引；186-doc/hash 是 Text2SQL Schema corpus，不是知识 corpus | M31 不能复用旧 Schema collection，也不应为了发布 corpus 提前选择检索后端 | `docs/state/schema-retrieval-milvus-embedding.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| Evidence 不能退化为正文字符串 | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py :: RetrieverResource.get_resources / _get_references`；`DB-GPT/.../tools/knowledge_retrieve.py :: knowledge_retrieve` | 对照“chunks + structured references”和“编号正文字符串”两种 interface，确认 reference identity 必须随内容贯穿 | M31 使用公共 Evidence 外壳 + Document/SQL typed payload；授权、诊断、runtime、outbound 独立引用 | 不只保存 chunk id、文件名、score；不把异常文本或 Tool 正文直接当最终 Observation/答案 |
| citation 不能在末尾拼 sources | `GustoBot/.../workflows/multi_agent/multi_tool.py :: _collect_sources / finalize` | 把它作为身份断裂反例：最终 sources 来自多字段猜测，不能证明进入生成器或支持具体 claim | M31 建立 `generation_visible -> cited` 子集校验、代码分配 citation slot 和 claim reference | 不继承其 PostgreSQL→Milvus 级联、默认 fallback、来源字符串去重或 Tool 内生成最终答案 |
| 索引 metadata 不是授权与可回查身份 | `GustoBot/.../infrastructure/knowledge/vector_store.py :: VectorStore._create_collection` | 其 schema 缺少通用 source/revision/anchor，说明 collection 结构不能代替 Evidence/ACL 合同 | ACL 在 authority/active catalog 上确定性裁决；未来索引只是可重建投影 | 不把 collection、前端选择、相似度或 metadata filter 当授权凭据 |
| 生成时真实上下文必须可观察 | `agentic-rag-for-dummies/project/rag_agent/graph_state.py :: AgentState / append_unique`；`nodes.py :: _retrieval_contexts`（reference map 指定入口） | 保留实际进入生成器的 context，而不是从最终答案猜测 | M31 只建立四阶段 Evidence ledger 和安全投影；P2/P3 接线后直接复用 | 不保存字符串 context 作为唯一身份，不引入 Graph、history compact、强制搜索或循环 |
| 发布失败不能推进 active 状态 | `WrenAI/core/wren/src/wren/memory/watch.py :: poll_once`；`index_backend.py :: MemoryIndex.reset / LanceDBIndex.rebuild` | source/derived 分离；callback 成功后才推进观察状态；重建派生物不修改 authority | release bundle 完整生成、校验、可重载后才原子更新 active pointer；候选失败保持旧 active | 不把 path/size/mtime fingerprint 当 corpus identity，不把 rebuild 当原子发布或完整回滚证明 |
| 替换与回滚保证必须如实表达 | `DataAgent/.../AgentVectorStoreServiceImpl.java :: replaceDocumentsByMetadata` | 先形成 replacement、后删旧；异常时尝试清理新文档 | M31 在新 release 完整存在且验证成功后才切 pointer，保留上一版 bundle；cleanup 不影响旧 active | 不把 best-effort cleanup 说成事务，不引入 Java 平台结构或在线增量替换 |
| ACL/outbound 正向实现缺少完整外部范例 | `GustoBot` 与 `DB-GPT` 上述入口作为反例 | 证明正文 Tool 输出、错误文本和 collection 选择都会扩大泄露面 | 正向合同以 Phase 4 roadmap、M29 caller/outbound inventory 和 DataPilot required tests 为准 | 不以 prompt guardrail、模型自觉或“模拟数据”替代确定性授权 |

复核结论：参考项目能帮助定位 identity、context 和发布 seam，但没有项目直接提供 DataPilot 所需的 trusted caller、claim-level citation、outbound 矩阵或安全 active pointer。M31 不新增远程 Knowledge 用途，因此本模块不以 provider 宣传或默认数据政策作为放行依据；以后任何 receiver × purpose × data class 放行都必须重新核对当时官方政策并经过用户决策。

## 4. 目标、优先级与非目标

### 模块完成状态

模块完成后，系统能够从 M30 staged catalog 生成一个完整、可校验、可跨重启加载的 immutable release bundle；只有可信 caller 才能通过确定性 ACL 获得用途受限的 typed Evidence，citation 只能引用同轮 `generation_visible` Evidence。缺少 outbound policy、未授权、revision 失效、bundle 损坏或候选构建失败均失败关闭。通过 G3 后才更新 active pointer；P2 可以只依赖 active catalog/Evidence interface，不需要重新解析 Markdown、猜测角色或自行实现发布回退。

### 必须完成

- 建立 trusted caller interface，以及明确标注的 test/demo adapter；请求体 role 只能形成 `unverified_request_claim`，不得获得 Document Evidence。
- 建立文档 AuthorizationDecision，统一执行 caller trust、`public/allowed_roles`、revision、用途及可选 tenant 检查；admin 不隐式全读。
- 建立 outbound policy seam，按 receiver × node purpose × data class × fields 默认拒绝；登记现有 Text2SQL 远程用途的兼容边界，所有新 Knowledge 用途继续 deny。
- 实现 Evidence 公共外壳、Document/SQL typed payload、四阶段 ledger、EvidenceRef 与安全投影；diagnostics/runtime/authorization/outbound 不塞入万能大对象。
- 实现 Citation Validator 的确定性完整性检查；未知、未入模、越权、旧 revision、用途不允许或 anchor 不一致全部拒绝。
- 实现版本化 immutable release bundle、active pointer、启动重载、候选失败保持旧 active、显式回滚和清理保护。
- 建立独立 `phase4-v1` contract/security family 的最小确定性执行与 closed-world artifact 校验；M27 v3 保持只读。
- 在 G3 前输出 release manifest、内容/ACL/outbound 摘要和验证证据，等待用户选择是否正式发布。

### 建议完成

- 提供只读 inspect/diff 投影，能比较 staged、candidate release、active 和 previous identity，不输出无权正文。
- 为测试/debug 提供显式短期详细投影，但默认长期投影只保留 refs/hash/状态/白名单诊断；不提前固定保留天数。
- 为后续 P2 提供 deterministic candidate/selected fixture helper，避免测试绕过正式授权与 Evidence transition。

### 条件触发

- **触发条件**：用户在 G3 选择正式发布。
- **允许动作**：把已验证的 candidate bundle 固化为 approved release，复核可重载性和安全 manifest，然后更新 active pointer；记录 current/previous identity。
- **未触发时**：保留 staged/candidate 状态，不提供 active corpus，不让 P2 默认消费。

- **触发条件**：未来要求把 Document Evidence 发往某个远程 embedding、rerank、generation、judge 或 Cloud receiver。
- **允许动作**：重新核对具体 payload、官方数据政策、fallback 和测试，提交独立用户决策。
- **未触发时**：所有新 Knowledge/RAG 远端用途保持 deny，不联网验证效果。

### 明确非目标

- 不实现 Knowledge Tool、关键词/向量检索、chunk/parent-child、embedding、rerank、query rewrite 或检索参数。
- 不实现 Shared Evidence Gate 的开放语义充分性判断、Answer Composer 或真正的自然语言答案生成。
- 不把 citation fixture 通过表述为端到端回答正确或 citation support 已解决；开放语义支持仍留给 P2 gold/人工/advisory judge。
- 不修改 `/api/query` 公开形状，不把 `docs_used` 升级成内部事实源，不接 RAG route。
- 不引入 LangGraph、Router、Hybrid、thread state 或生产 JWT/OAuth/SSO。
- 不创建 Knowledge Milvus collection，不复用 186-doc Schema corpus/历史 collection，不切换模型、embedding、检索或 LangFuse 默认。
- 不改写 M27 v3 Scenario、artifact、review、报告或历史基线，不更新 README。
- 不承诺发布包永久保留全部撤销正文；撤销、删除与审计 identity 的长期保留策略按后续真实要求演进。

## 5. 关键合同

这是 M31 核心合同的单一事实源；工作切片和验收矩阵只引用合同编号。

### C1：可信 caller 合同

- 输入：受控入口类型、稳定 caller fixture/auth 结果、resolved roles、identity source，以及可选 tenant/audit ref。
- 成功输出：不可变 trusted caller，至少包含 `caller_id`、`resolved_roles`、`trust_level`、`identity_source`、可选 `tenant_id/thread_owner_ref` 和安全 `audit_ref`。
- 失败语义：未知来源、空 identity、非法角色或客户端自报 role 只能形成 `unverified_request_claim` 或 `caller_untrusted`，不能静默提升信任。
- 必须保持的不变量：业务 module 不读取 token/cookie/原始 role；只有 production authenticated、demo fixture、test fixture 可成为文档授权主体；M31 没有生产认证 adapter 时必须如实标注。
- 本模块不冻结的实现细节：类名、依赖注入框架、未来 JWT/OAuth provider 和 thread owner 实现。

### C2：文档授权合同

- 输入：trusted caller、catalog/release entry 或 EvidenceRef、请求用途和当前 revision/tenant facts。
- 成功输出：结构化 AuthorizationDecision，记录 allow、稳定 reason、policy identity、caller/evidence safe ref 和允许用途。
- 失败语义：untrusted、role 不匹配、tenant 不匹配、inactive/revoked、用途不允许均 deny；对外统一安全投影，不暴露标题、document id、revision、命中数或存在性。
- 必须保持的不变量：`public` 或显式 `allowed_roles`，admin 不隐式全读；候选进入 selected 前检查，进入 generation-visible 前再次检查；策略缺失失败关闭。
- 本模块不冻结的实现细节：复杂 ABAC、组织目录、行级策略语言和多租户管理平台。

### C3：出站裁决合同

- 输入：receiver、node purpose、data class、字段集合、caller/evidence safe refs 和 fallback 能力。
- 成功输出：OutboundDecision，明确 allow/deny、policy identity、允许字段和安全 reason。
- 失败语义：策略缺失、用途或字段未登记、caller/ACL 不满足时 deny；有确定性 fallback 时记录节点级 deny 并继续，无 fallback 且节点必需时返回 `outbound_denied`。
- 必须保持的不变量：provider 相同不共享用途授权，purpose 相同不共享 data class；当前 Text2SQL 既有行为只按登记兼容，不自动扩展到 Document Evidence；所有新 Knowledge 用途 deny。
- 本模块不冻结的实现细节：未来 provider、模型、区域、费用、远程重试和任何 Knowledge 放行规则。

### C4：typed Evidence 与阶段合同

- 输入：本轮 authority/runtime fact、受控 content view、用途、authorization/runtime refs，以及代码分配的运行 identity。
- 成功输出：公共 Evidence 外壳加 Document/SQL typed payload；Document 能回到 release/document/revision/anchor，SQL 能回到已 Guard 的 SQL/result/runtime fact。
- 失败语义：authority、identity、revision、anchor、allowed uses 或必要 payload 不完整时拒绝构造；未知 evidence type/阶段失败关闭。
- 必须保持的不变量：`candidate → selected → generation_visible → cited` 只能正向、同轮、可审计迁移；cited 必须是 generation-visible 子集；完整 Evidence、长期审计和公开响应使用不同投影。
- 本模块不冻结的实现细节：P2 的检索分数、排序、chunk 大小，P3 的 Graph state，公开 AgentResponse 字段。

### C5：citation 完整性合同

- 输入：结构化 claim/draft、代码预分配 citation slot、citation 引用、同轮 generation-visible Evidence 和相关 decision refs。
- 成功输出：validated citations 及 cited-stage 记录，可供后续 Composer/controller 投影。
- 失败语义：unknown id、candidate/selected-only、跨轮、越权、inactive/old revision、用途不允许、anchor 不一致或模型自造 slot，统一 `citation_invalid`；未经验证的 claim/citation 不得展示为可信答案。
- 必须保持的不变量：确定性代码裁决存在性、阶段、ACL、revision、用途和可回查性；开放语义支持度不得覆盖确定性失败。
- 本模块不冻结的实现细节：自然语言 span 算法、LLM support judge、最终引用 UI 和答案文案。

### C6：immutable release 与 active 切换合同

- 输入：完整 StagedCatalog、release recipe/policy identity、C1-C5 合同版本、可选 G3 approval record 和当前 active identity。
- 成功输出：没有 approval 时只产生内容与 manifest 完整、hash 可复算、可独立重载的 candidate bundle；取得 approval 后才能固化 approved release，并由原子切换后的 active pointer 记录 current 和可回滚 previous identity。
- 失败语义：构建、序列化、hash、closed-world、ACL/outbound、重载或 pointer 切换任一步失败，candidate 不成为 active，旧 active 不变；启动时 active bundle 校验失败则保守不可用，不自动复活可能已撤销的旧正文。
- 必须保持的不变量：authority 仍是原件；release bundle 只能由 builder 生成且不得反向编辑原件；active pointer 只指向完整 bundle；显式回滚前必须重新校验 revision、ACL、撤销状态和 policy，不能仅因文件存在就恢复。
- 本模块不冻结的实现细节：精确目录/文件名、永久保留数量、对象存储/数据库、多实例锁和在线无停机发布。

### C7：Phase 4 contract/security Eval 合同

- 输入：版本化 `phase4-v1` Scenario/fixture、一次确定性执行产生的 ExecutionEvidence、policy 与 runtime identity。
- 成功输出：caller、ACL、outbound、Evidence stage、citation、publish/fallback 等 typed assertions 共享同一执行证据，并形成 closed-world artifact/Gate 投影。
- 失败语义：缺失、额外或重复 Scenario/replicate/assertion，contract/policy/caller/corpus/release identity 不匹配时 completed artifact 整体拒绝；预期 deny/insufficient 是可观察结果，不记为 `not_observed`。
- 必须保持的不变量：M27 v3 全部只读；required 确定性失败不能被 advisory 平均分覆盖；本模块不运行真实 provider。
- 本模块不冻结的实现细节：P2 retrieval/answer assertion 全集、held-out 数量、真实模型 baseline 和长期报告 UI。

## 6. 工作切片与执行顺序

### M31-A：建立 notes、基线与反向清单

- 优先级：必须完成
- 依赖：M30 已验收；用户已选择 immutable release bundle。
- 实施内容：创建 `m31-notes.md` checklist；记录 Git/status、11-entry staged identity、当前远程 call-site、旧 Trace/API consumer 和 release 存储约束；把当前入口分类为 legacy SQL、Phase 4 新路径、远程 receiver、长期/短期投影或历史只读。
- 关键合同：C1-C7
- 交付物：实施清单、consumer/outbound/release exposure matrix、迁移前快照。
- 验证方式：反向 `rg` 与当前代码路径逐项对账。
- 完成门：没有未归类的 active caller、provider、Trace、catalog consumer 或 artifact 写入点。

### M31-B：可信 caller、AuthorizationDecision 与 OutboundDecision

- 优先级：必须完成
- 依赖：M31-A、M29 caller/outbound inventory。
- 实施内容：先写 unverified role 篡改、角色交叉、admin 非全读、inactive、用途错误、policy missing、receiver/purpose/data class/field 组合的红灯测试；实现统一 caller/authorization/outbound 深 module；在集中远程调用 seam 登记并约束现有 Text2SQL 行为，保证新 Knowledge payload 无法绕过。
- 关键合同：C1、C2、C3
- 交付物：trusted caller adapters、authorization/outbound policy identity、结构化 decisions 和安全公开 reason 投影。
- 验证方式：table-driven 正反例、fake remote adapter、payload capture；网络调用为零。
- 完成门：请求体改成 admin 不能获得文档 Evidence；每个远程调用类别都有 allow/deny/missing-policy 结果，新 Knowledge 全部 deny。

### M31-C：typed Evidence、四阶段 ledger 与 Citation Validator

- 优先级：必须完成
- 依赖：M31-B。
- 实施内容：建立小而稳定的 Evidence interface、Document/SQL constructors、阶段 transition 和各消费者安全投影；通过合法/unknown/candidate-only/selected-only/跨轮/旧 revision/错误 anchor/越权 citation fixture 实现 validator；禁止开放 dict 反向构造内部事实。
- 关键合同：C2、C4、C5
- 交付物：typed Evidence、EvidenceRef、stage ledger、validated citation、安全审计/公开投影。
- 验证方式：构造/序列化/round-trip/篡改/阶段反例测试；删除测试验证 caller 只依赖小 interface。
- 完成门：所有合法 citation 都来自同轮 generation-visible Evidence；任何篡改确定性失败且无正文/身份侧信道。

### M31-D：immutable release bundle、active pointer 与回滚

- 优先级：必须完成
- 依赖：M31-B、M31-C、M30 staged builder。
- 实施内容：定义 canonical release serialization 与 identity；实现 candidate build、完整校验、独立重载、pointer 原子切换、current/previous 保护、启动恢复和显式 rollback；用写入中断、hash 篡改、pointer 切换失败、active 损坏、旧 revision 被撤销等反例明确边界。
- 关键合同：C2-C6
- 交付物：版本化 release bundle、active registry/pointer、inspect/diff、安全 rollback 结果。
- 验证方式：临时目录文件系统测试、fault injection、重启重载模拟、candidate/active identity 对账；临时产物统一放 `.agent_work/temp/`。
- 完成门：candidate 任一步失败都不改变旧 active；成功 release 可跨进程重载；显式 rollback 不能复活已撤销或当前无权内容。

### M31-E：`phase4-v1` contract/security family

- 优先级：必须完成
- 依赖：M31-B-D。
- 实施内容：建立首个独立 Phase 4 deterministic contract family，覆盖 caller tamper、ACL non-disclosure、outbound missing/deny、Evidence stage、citation invalid、candidate publish failure、startup load、rollback safety 和 closed-world artifact 反例；一次执行产生共享 ExecutionEvidence。
- 关键合同：C1-C7
- 交付物：最小 Scenario/fixture、executor/projector、typed assertions、artifact identity 和 required Gate。
- 验证方式：正例 completed artifact；缺失/额外/重复/hash/policy/caller/release mismatch 全部失败关闭；M27 loader/review 回归。
- 完成门：required Gate 能准确区分合同通过、真实失败和不可观察；不调用 API/LLM 伪造端到端 RAG 分数。

### M31-F：G3 证据审查、条件发布与收工

- 优先级：必须完成
- 依赖：M31-A-E 全绿。
- 实施内容：向用户提交 11-entry release manifest 摘要、ACL/outbound 矩阵、bundle/current/previous identity、失败注入证据和未证明边界；取得 G3 选择；若发布则执行一次受控 activation 并验证重载，若不发布则保持 staged；随后运行完整回归并按项目流程收工。
- 关键合同：C1-C7
- 交付物：G3 决策记录、active 或 staged 状态、验证快照、M32/P2 handoff。
- 验证方式：第 8 节矩阵、全仓 pytest、`compileall`、`git diff --check`、反向泄露扫描。
- 完成门：状态与用户选择一致，没有把 candidate/staged 写成 active；state/runbook/changelog/dev-log 准确同步。

## 7. 决策门

### G3：首批正式 corpus 发布

#### 方案 A：批准 11-entry release 并切换 active（当前建议）

- 做法：在 C1-C7 全部 required 验证通过且用户复核 candidate manifest 后，将同一份已验证 bundle 固化为 approved release，再次校验可重载性，最后更新 active pointer。
- 影响：P1 安全地基形成闭环，P2 可以消费 active catalog；运行时会保留至少 current/previous 完整发布包，正文投影需受访问和清理规则保护。
- 适用条件：内容、ACL、classification、purpose、outbound deny、citation/publish 合同均与用户预期一致。
- 风险：发布包保存派生正文；若未来出现真实敏感内容、撤销或法定删除要求，需要补更具体的 retention/删除流程。

#### 方案 B：继续保持 staged，不切换 active

- 做法：保留代码、测试和 candidate release 证据，但不更新 active pointer。
- 影响：M31 的安全 module 可验收，G3/P1 发布状态未完成；P2 只能继续使用 fixture，不能把当前 corpus 当默认运行知识。
- 适用条件：用户对某条内容、ACL、数据分类、用途或发布包保存方式仍有疑问。
- 风险：后续 RAG 主线暂停，需修订 authority/policy 后重新生成 candidate 并复核。

#### 建议与确认时点

- 建议：满足第 8 节 required 标准后选择方案 A。
- 建议理由：首批 11 条都是已治理的本地短文，所有新远程 Knowledge 用途保持 deny；immutable bundle 又提供完整校验、跨重启加载和失败不切换，具备最小安全发布条件。
- 用户确认前允许推进：C1-C7 代码、deterministic fixture、candidate release、manifest/inspect 和全部无网络测试。
- 用户确认前禁止推进：更新 active pointer、让 P2 默认读取、建立正式 Knowledge index、向任何远程节点发送正文。
- 需要确认的时点：M31-A-E 完成，candidate manifest 与 required 验证证据可供检查后。
- 重开决策的条件：authority/ACL/data class/purpose 变化，新增远程 receiver，release format/retention 改变，或 required Gate 出现失败。

### D31-1：发布存储形态（已确认）

用户已选择“版本化 immutable release bundle”。不再比较 authority 多 revision 重构或仅进程内 snapshot；若实现调查证明该方案无法满足 C6，按第 11 节冲突规则重新暂停，而不是静默降级。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 caller | role 篡改、空 identity、test/demo/production/unverified table tests | 只有明确可信 adapter 可获文档授权；请求体 admin 仍为 unverified | 必须完成 |
| C2 ACL | 11 entries × caller roles × purposes；pre-selection/pre-generation 双检 | allowlist 精确匹配，admin 不全读；deny 响应/Trace 不泄露存在性 | 必须完成 |
| C3 outbound | receiver × purpose × data class × fields × fallback 参数化测试和 fake payload capture | 缺策略默认 deny；新 Knowledge 无远程调用；现有 Text2SQL 行为不被静默扩大 | 必须完成 |
| C4 Evidence | constructors、stage transition、cross-run/unknown type/缺字段反例、projection snapshot | 只允许正向同轮迁移；长期/公开投影无正文和内部 policy 细节 | 必须完成 |
| C5 citation | legal、unknown、candidate-only、selected-only、old revision、wrong anchor、ACL deny、model-forged slot | 只有 generation-visible 合法 Evidence 可 cited；失败不展示未验证 claim | 必须完成 |
| C6 bundle build | deterministic serialization、semantic change、order noise、partial write、hash tamper | 同输入同 identity；语义变化必变；半成品永不 active | 必须完成 |
| C6 activation | pointer failure、candidate reload failure、restart reload、old active preservation | 切换前全部校验；任何候选失败旧 active 不变；成功版本可重载 | 必须完成 |
| C6 rollback | previous missing/corrupt、revision revoked、ACL/policy changed | 只有重新验证仍合格的 previous 可显式恢复；否则失败关闭 | 必须完成 |
| C7 Eval | 一题一次、共享证据、required assertions、closed-world 缺/多/重/hash mismatch | completed artifact 恰好匹配 contract/policy/caller/corpus/release identity | 必须完成 |
| G3 | candidate manifest + 人工选择 + activation/reload 证据 | 选择 A 才 active；选择 B 时系统明确保持 staged | 条件触发 |
| P2 handoff | fake caller 通过 active catalog 构造 authorized Document Evidence | 调用者不解析 Markdown、不读取 legacy 表、不知道 release 存储细节 | 建议完成 |

聚焦测试顺序：caller/ACL/outbound → Evidence/citation → release/fault injection → `phase4-v1` contract family → M30 catalog/Text2SQL isolation → legacy API/Trace/M27 → 全仓 pytest。

全量回归必须覆盖 M30 11-entry identity、13 表 Text2SQL queryable universe、186-doc Schema corpus identity、M27 canonical loader/review 和现有 API/SQL 安全行为。测试使用新的 `.agent_work/temp/<m31-name>` basetemp，避免 Windows 旧目录锁。

本模块不运行真实 LLM、远程 embedding、Milvus、LangFuse Cloud、真实 RAG Eval 或人工答案质量评分。发布内容人工审查只发生在 G3，不把用户未确认等同测试失败。历史 M27 artifact/report/review 和旧 195-doc collection 全部只读，不补字段、不重算、不混入 `phase4-v1`。

## 9. 依赖与交付物

### 依赖

- M30 已验收的 authority source、staged catalog、G2=B 和 Text2SQL 隔离。
- M29 已确认的 G0=A、G1=A、G1-O=A、trusted caller/Evidence/citation handoff 与独立 Eval family 决策。
- Phase 4 roadmap 第 4 节不变量、P1/G3 边界和 reference 使用合同。
- 用户本轮确认的 immutable release bundle 方案。
- 当前本地文件系统；多实例数据库/object storage 发布不作为 M31 前置。

### 交付物

- `docs/notes/m31-plan.md`：本计划。
- `docs/notes/m31-notes.md`：implementation checklist、决策/踩坑、release/G3 证据和验证快照。
- trusted caller、文档 authorization 和 outbound policy 深 module，以及 fake/test/demo adapters。
- Evidence 公共外壳、Document/SQL typed payload、EvidenceRef、四阶段 ledger、Citation Validator 和安全投影。
- immutable release builder/loader、versioned bundle、active pointer、inspect/diff 与显式 rollback 能力。
- `phase4-v1` 最小 contract/security Scenario、ExecutionEvidence、typed assertions、closed-world artifact/Gate。
- caller/ACL/outbound/citation/release/fault injection 测试，以及 M30/M27/legacy 回归。
- G3 决策记录；若批准则包含 active/previous release identity，若不批准则明确 staged 状态。
- 收工阶段按项目流程更新 notes、state/changelog/dev-log 和必要 runbook；README 不更新。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：真正检索、Knowledge Tool、Gate/Composer、RAG API、公开四轴响应、Graph、Hybrid、thread、真实模型和向量索引。
- 下一模块可直接消费的产物：active catalog loader、trusted caller、Authorization/OutboundDecision、Document Evidence/Citation Validator、`phase4-v1` security contract。
- 下一步最合适的里程碑：若 G3=A，进入 P2 确定性 RAG 垂直切片；先做可替换的本地 deterministic retrieval 和 Knowledge Tool，不预设 Milvus/embedding。
- 后续需要根据真实失败重新规划的内容：keyword/vector/hybrid retrieval、chunk/parent-child、rerank、query rewrite、远程 generation 和 held-out decision set。
- 可能存在的风险：release bundle 保存派生正文；旧 SQL Trace 仍有历史完整 question/rows 语义；M31 只保证新 Phase 4 Evidence 投影不沿用旧 `docs_used`/Trace 事实源，P2/P3/P7 接线时仍需完成公开响应与全局 Trace 迁移。
- 撤销/删除边界：inactive/revoked revision 不进入新 Evidence；历史审计默认保留不可逆 identity、anchor identity 和授权事件。是否保留已撤销正文以及保留多久，不在没有真实合规要求时提前固定。

## 11. 开工条件

- 开工前无需确认：M31 模块号与范围；immutable release bundle；G0/G1/G1-O；新 Knowledge 远端用途全部 deny；M27 v3 只读；不引入检索/Graph/API 变更。
- 实施中需要确认：第 7 节 G3。只有 M31-A-E 全绿并展示 candidate manifest/required 证据后，用户选择正式 active 或继续 staged。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支。尤其不得将仅进程内 fallback、best-effort 文件写入、provider 默认配置或旧 `docs_used` 兼容字段偷换成 C2-C6 的安全保证。
