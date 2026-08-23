# M44A EnterpriseRAG-Bench Milvus 产品运行链路开发计划

> 能力里程碑：Phase 4B 插入式基础设施修复模块；位于 M43/B1 与 M44/B2 之间，不占用 B0–B6 任一能力里程碑，也不改变 M44–M48 owner 和 M46 sealed reserve 解封绑定
>
> 主要问题：EnterpriseRAG-Bench 已有完整 Milvus semantic candidate，但普通 Uvicorn 和 external 产品 Eval 仍固定或退回 lexical，用户无法可靠地启动、验证并证明一次 RAG 请求真的经过向量数据库

## 1. 模块定义与范围判断

M44A 只闭环一个问题：把现有 EnterpriseRAG-Bench Milvus candidate 从“只供 M34 retrieval-only 脚本选择的候选”接入真实产品 RAG runtime，使本地 API、external Eval、Trace/artifact 和运行手册使用同一套解析、生命周期与身份事实。

用户已确认把本模块命名为 M44A，并确认默认方案 A：EnterpriseRAG-Bench 的产品 RAG 默认使用 Milvus semantic；lexical 只作为显式 baseline 保留。显式 semantic 配置失败时必须失败关闭，禁止自动回退 lexical。M44A 是路线插入模块，后续仍为 M44/B2、M45/B3、M46/B4、M47/B5、M48/B6；M42/M43 的版本化合同和 reserve 均不改签。

模块完成后，用户可以：

- 配置已冻结的 profile/semantic identities 后，用 `python -m uvicorn app.main:app --reload` 启动服务，并从安全运行状态看到当前是否真的加载了目标 Milvus collection；
- 通过普通 `/api/query` 执行 EnterpriseRAG-Bench RAG，链路实际为“query embedding → Milvus 候选 → SQLite 原文/坐标 → Evidence/citation → Composer”，而不是小语料 fixture 或 lexical FTS；
- 用 external Eval CLI 在不额外选择 backend 时得到同一 semantic runtime，并在 artifact/Trace 中回查 embedding、collection、manifest 和 adapter identity；需要 lexical 对照时必须显式声明；
- 在 Docker/Milvus、API key、manifest、collection 或 identity 不满足条件时得到稳定、可诊断的 unavailable/mismatch，而不是看似成功的假 RAG。

这不是索引重建或质量优化模块。现有 139,214-unit candidate 是本模块的输入；M34 @20 证据显示该 dense-only candidate 当时低于 lexical，这不阻止用户已确认的产品默认切换，但 M44A 不能把“真正用了向量库”写成“召回质量已经优于 lexical”。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
| --- | --- | --- |
| EnterpriseRAG-Bench profile 为 36,417 documents / 139,214 units，现有 semantic manifest、Milvus collection 和 unit-set identity 已闭合 | 不应因接线缺失重新建库；运行时应验证并消费既有派生索引 | `docs/state/rag-current-state.md`、`docs/state/schema-retrieval-milvus-embedding.md`、`engine/rag/enterprise_semantic.py` |
| `load_enterprise_semantic_runtime` 已把 Milvus adapter 注入同一 external bundle/context loader | 向量库只负责候选检索，SQLite 仍是正文和 Evidence 坐标权威；无需复制第二套 AnswerFlow | `engine/rag/enterprise_semantic.py::load_enterprise_semantic_runtime`、`engine/rag/enterprise_runtime.py::EnterpriseProfileRuntime` |
| `app.main.create_app` 把 `rag_tool_factory` 设为 `None`，普通 `/api/query` 因而构造仓库内小语料 `RAGToolAdapter` | 用户启动 Uvicorn 时不会进入 EnterpriseRAG-Bench，更不会访问 Milvus | `app/main.py::create_app`、`app/api/query.py` |
| `eval.run_rag_external_eval` 固定调用 `load_enterprise_profile_runtime` | external 产品 E2E 即使 Milvus 正在运行，也始终使用 SQLite lexical | `eval/run_rag_external_eval.py::main` |
| semantic adapter 启动时验证 visible unit set 并 load collection，查询时调用 DashScope embedding 后执行 Milvus search | 它具备 fail-closed 基础，但缺少应用级一次加载、跨线程适配、ready 状态和统一配置解析 | `engine/rag/enterprise_semantic.py::EnterpriseMilvusSemanticAdapter` |
| external runtime 会加载 139k metadata，并持有 SQLite/Milvus client | 若每请求创建会重复重载、泄漏连接并放大延迟；必须由 FastAPI lifespan 和 Eval context 一次持有、最终关闭 | `engine/rag/enterprise_runtime.py::EnterpriseProfileRuntime.close`、`app/main.py` |
| `RAGResolvedRuntime` 只记录 adapter/recipe 等通用字段 | semantic 与 lexical artifact 不能充分证明具体 semantic manifest、embedding 和 collection；A/B 可能被错误视为同 runtime | `eval/rag_e2e_contracts.py::RAGResolvedRuntime`、`engine/trace/runtime.py` |
| M34 @20 的 semantic retrieval 分数低于 lexical；M41 post-fix external 产品证据仍全是 lexical | 已知的是旧 dense-only retrieval 差异，不是 semantic 产品 AnswerFlow 的完整质量结论 | `docs/state/eval-baselines.md`、`docs/state/change-history/phase4.md`、`docs/state/change-history/phase4b.md` |
| 当前仓库没有负责启动 Milvus 的 compose 文件，Milvus 是外部运行前置 | 应提供明确 preflight、启动检查和错误说明，但应用不得暗中创建/启动/重建 Docker 资源 | `rg --files` 调查、`docs/state/runbook-rag.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
| --- | --- | --- | --- | --- |
| 向量索引与知识原件怎样分权 | `WrenAI/core/wren/src/wren/memory/index_backend.py::MemoryIndex.reset/LanceDBIndex.rebuild` | source 与 derived index 分离，重建索引不删除原件 | SQLite profile/正文/坐标继续是权威 source；Milvus collection 只是由 manifest 标识的 derived retrieval index | 不引入 Wren memory/watch，不把文件 fingerprint 当 corpus release，也不在 M44A 自动 rebuild/reset |
| 多后端检索怎样接入工作流 | `GustoBot/gustobot/application/agents/kg_sub_graph/agentic_rag_agents/workflows/multi_agent/multi_tool.py::create_kb_multi_tool_workflow/local_search/finalize/_collect_sources` | 检索 backend 通过稳定工作流 seam 汇入回答阶段，source 汇总需保持可追踪 | API/Eval 都向现有 Knowledge Tool/AnswerFlow 注入同一个 Enterprise runtime；Milvus 命中后仍由 SQLite materialize 并签发 DataPilot Evidence/citation | 不照搬 PostgreSQL/Milvus 自动级联、外部搜索 fallback 或字符串 sources 拼接；显式 semantic 失败绝不换 lexical |
| Milvus schema 是否足以承担 citation 权威 | `GustoBot/gustobot/infrastructure/knowledge/vector_store.py::VectorStore._create_collection` | 向量库适合保存主键和向量并做候选检索 | collection 只返回 `unit_identity`；revision、anchor、source 和 content hash 必须回查已验证 SQLite entry | 不照搬缺少 revision/anchor/source continuity 的 schema，不从 Milvus payload 直接生成 citation |
| 检索结果与 reference 怎样分层 | `DB-GPT/packages/dbgpt-core/src/dbgpt/agent/resource/knowledge.py::RetrieverResource.get_resources/_get_references` | retrieval chunks 与结构化 references 分开呈现 | 保持 RetrievalMatch → MaterializedDocumentContext → Evidence/citation 的 typed 链，新增 runtime identity 只做诊断，不代替 Evidence | 不把异常文本塞进 Tool Observation，不只拼文档名/score，也不引入 DB-GPT 平台层 |
| 索引替换失败能否视为原子发布 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java::replaceDocumentsByMetadata` | replacement 的异常清理和 metadata 过滤可作为风险提醒 | M44A 只读验证精确 semantic manifest/collection，不做在线替换；若 unit set 不匹配直接不可用 | 不把“先加后删 + best-effort cleanup”宣传为原子切换，也不扩展到增量发布服务 |

定点复核结论：参考项目支持“稳定 workflow seam + source/index 分离 + structured reference”的方向，但其 fallback、schema 和发布保证均不足以证明 DataPilot 的身份闭合。M44A 必须依赖自身 manifest hash、profile/corpus/unit-set/embedding/collection identities、pre-selection ACL、SQLite materialization 和 Trace/Eval 同源证据。

实现时还须按 `docs/phase4-reference.md` 的要求复核所用版本的 FastAPI lifespan 与 Milvus client 官方接口；官方文档只用于确认资源初始化/释放、collection load/search/readiness API，不覆盖 DataPilot 的安全和 Eval 合同。

## 4. 目标、优先级与非目标

### 模块完成状态

M44A 完成后，项目具备一个由应用和 Eval 共用的 Enterprise RAG runtime resolver。其默认 retrieval mode 为 `semantic`，需要精确的 profile 与 semantic snapshot 选择；成功时只加载一次并明确记录 Milvus 事实，失败时不签发 RAG Evidence、不调用 Composer、不回退 lexical。`lexical` 仍可通过显式配置用于历史复现和候选对照，但绝不再是 Enterprise 产品链的隐含默认。

### 必须完成

- 冻结 `semantic | lexical` closed-world mode；API 与 external Eval 默认 `semantic`，未知值拒绝。
- 建立同一 resolver，验证 profile、semantic manifest、embedding provider/model/dimensions、collection、unit count/set 和 adapter recipe 的一致性。
- 用 FastAPI lifespan 持有唯一进程级 external runtime；请求只创建轻量 Knowledge Tool/AnswerFlow view，shutdown 关闭 SQLite、Milvus 和 provider 资源。
- 普通 API 不再用小语料 adapter 冒充 EnterpriseRAG-Bench；未配置或 runtime unavailable 时返回稳定、安全、可诊断失败。
- external Eval 改用同一 resolver；semantic 默认，lexical 仅显式 opt-in；partition/suite/held-out 授权纪律不变。
- 扩展 response-safe diagnostics、Trace、`RAGResolvedRuntime`、artifact 和 compare allowlist，使 semantic snapshot 能被直接证明和严格比较。
- 给出不泄露 API key/本机敏感路径的 liveness/readiness 或等价安全状态，以及 Uvicorn/Eval 的可复制运行说明和 preflight。
- 测试 fail-closed、一次初始化/关闭、线程使用、身份漂移、无 fallback、API/Eval 同解析；最终通过至少一次经用户精确授权的真实 Milvus semantic 验证。

### 建议完成

- 提供独立 preflight/diagnostic 入口，一次报告 profile、semantic manifest、Milvus reachability/load state 和安全 identity 摘要，不调用 Composer。
- 为 external Eval 增加精确单 Scenario 诊断选择，沿用既有一题一次执行和 artifact 合同，降低产品链 smoke 成本；它不得绕过 suite/partition 和 held-out 门禁。
- 在启动日志中输出脱敏后的 retrieval mode、adapter、collection 和 snapshot 短 identity，便于用户一眼发现仍未进入向量模式。

### 条件触发

- **触发条件**：既有 semantic manifest、collection 或 unit set 校验失败，确认不是 Docker 未启动、连接配置或依赖版本问题。
- **允许动作**：停止 M44A 完成声明，提交“恢复/重建既有 candidate”所需的精确命令、成本和身份影响，由用户另行授权；若会产生新 semantic identity，则先重开决策。
- **未触发时**：禁止重跑 139,214-unit embedding build、覆盖 collection、修改 manifest 或生成替代 candidate。

- **触发条件**：真实 semantic product smoke 能运行但暴露稳定的召回/排序质量问题。
- **允许动作**：把失败事实和 runtime identity 交给 M45/B3 campaign；M45 必须据此诊断 recovery action，M46/B4 再按 reserve 与质量证据决定 RAG Subgraph 候选。
- **未触发时**：M44A 不新增 hybrid fusion、rerank、query rewrite、parent/child 扩展或第二 embedding 模型。

### 明确非目标

- 不重建、增量更新、发布或回滚 Enterprise semantic index，不改变现有 36,417/139,214 corpus/profile。
- 不以 lexical 分数较高为由撤销用户确认的 semantic 默认，也不以 semantic 已接通为由声称质量更高。
- 不改变业务小语料 active release、Schema Retrieval 的 Milvus/embedding 默认或 Text2SQL 数据库。
- 不实现 M44/B2 Decision Loop、M45/B3 failure campaign、M46/B4 RAG Subgraph、M47/B5 durable state 或 M48/B6 Compact。
- 不解封或读取 M46 sealed reserve，不运行 held-out/all，不把真实运行授权从 smoke 自动扩大。
- 不让请求体选择 backend、semantic identity、provider、collection 或出站权限；这些只能由可信启动/Eval 配置确定。
- 不自动启动 Docker、创建 collection、下载模型或把 API key/绝对数据路径写入 Trace、响应、报告和仓库文档。

## 5. 关键合同

### C1：Enterprise RAG runtime 选择与默认合同

- 输入：可信配置提供的 retrieval mode、profile root/identity、semantic root/identity，以及应用/Eval 的调用场景。
- 成功输出：`semantic` 默认解析为一个已验证的 Enterprise semantic runtime；`lexical` 只有显式选择才解析为历史 adapter；API 与 Eval 得到相同 resolved identity。
- 失败语义：配置缺失、未知 mode、snapshot 不存在或 identity 不一致时返回稳定 config/runtime error；不构造小语料/lexical 替代品。
- 必须保持的不变量：请求体不能选择 runtime；external partition/suite 权限不因 mode 改变；M42/M43 与 B0–B6 owner/reserve 不变。
- 本模块不冻结的实现细节：Settings 字段和 resolver 文件的最终命名；但运行手册必须给出唯一、可复制的配置入口。

### C2：Semantic snapshot 与 fail-closed 合同

- 输入：profile manifest、semantic manifest、query embedding provider 和目标 Milvus collection。
- 成功输出：profile/corpus/unit recipe、semantic/manifest、embedding provider/model/dimensions、collection、unit count/set、adapter/recipe 全部闭合后才把 runtime 标为 ready。
- 失败语义：Milvus 不可达、collection 未 load/不存在、unit set 漂移、embedding identity 不符或 provider 不可用时 semantic unavailable；当前请求零 Evidence、零 Composer，且不回退 lexical。
- 必须保持的不变量：SQLite 是正文、revision、anchor、content hash 和 coordinates 权威；Milvus 只提供 `unit_identity` 候选；错误输出不得泄露 key、正文或不必要的本机路径。
- 本模块不冻结的实现细节：健康检查是 eager preflight 还是受控 lazy refresh；无论哪种都必须一次缓存、可观察且测试无 fallback。

### C3：应用生命周期与并发合同

- 输入：FastAPI application lifespan、已解析 runtime 和并发 RAG 请求。
- 成功输出：每个应用进程只建立一份重型 metadata/SQLite/Milvus runtime，请求共享只读能力，shutdown 恰好关闭；Eval context 同样成对 acquire/release。
- 失败语义：初始化失败不得留下半初始化 factory/client；关闭可重复安全；已不可用 runtime 不接受业务请求。
- 必须保持的不变量：不会每请求重载 139k metadata；SQLite 跨线程只读使用必须显式安全；测试 fixture 可替换深 interface，但不能改变产品默认。
- 本模块不冻结的实现细节：锁、context manager、lifespan helper 的内部类名。

### C4：产品 RAG 数据流与 Evidence 合同

- 输入：通过现有 caller/ACL 的普通 RAG query 和 ready Enterprise semantic runtime。
- 成功输出：query embedding → Milvus search → 已授权 entry 映射 → SQLite materialization → 现有 Evidence/citation → Composer；response、Trace 和 Eval 只投影这一次执行事实。
- 失败语义：embedding、retrieval、materialization 或 Evidence 校验失败沿既有安全失败语义结束；后续阶段不补跑另一 backend。
- 必须保持的不变量：pre-selection ACL、物理文档去重、citation/source continuity、outbound policy 和一题一次产品执行不削弱；不得从 Milvus payload 直接拼回答或引用。
- 本模块不冻结的实现细节：top-k 和 scan multiplier；现有值先保持，质量调参不进入 M44A。

### C5：可观测性、Eval 与比较合同

- 输入：一次 API/Eval resolved runtime 和实际执行 diagnostics。
- 成功输出：Trace/artifact 至少记录 mode、adapter/recipe、profile/release/corpus、semantic/manifest、embedding provider/model/dimensions、collection 和 unit-set identity 的安全形式；API/Eval/Trace 三方一致。
- 失败语义：命令声明与实际 runtime 不一致、semantic 字段缺失、artifact resume identity 漂移或 compare 未显式允许 runtime 差异时拒绝。
- 必须保持的不变量：API key、正文、完整本机路径不落盘；旧 lexical artifact 保持可读且原件不改签；candidate A/B 只有显式 allowlist 才可比较。
- 本模块不冻结的实现细节：旧 artifact 兼容采用 optional fields 还是 additive contract version；实施时必须用回归证明旧 M41 artifact 仍可读取。

### C6：真实验证与完成声明合同

- 输入：deterministic 聚焦测试、可用 Milvus、匹配的 semantic snapshot、DashScope embedding/Qwen 配置，以及用户对精确 external selector 的一次授权。
- 成功输出：至少一条真实请求直接证明 semantic adapter、目标 collection、query embedding、Milvus hit、SQLite Evidence/citation 和产品 AnswerFlow；Eval artifact 记录相同身份。
- 失败语义：若只完成 fake/unit tests，或 Milvus/真实 provider 验证未获授权、未运行或失败，M44A 只能标为“代码完成、真实门未闭合”，不得宣称向量数据库问题已解决。
- 必须保持的不变量：默认只允许 diagnostic_dev；held-out/all 仍需另行明确授权；失败后不自动重跑、不扩大 suite、不换 lexical 取得假绿。
- 本模块不冻结的实现细节：最终真实门采用一个显式 Scenario 还是用户明确授权的 external smoke suite；实施前按 runbook 请求精确范围。

## 6. 工作切片与执行顺序

### M44A-A：统一配置、resolver 与身份合同

- 优先级：必须完成
- 依赖：M34 verified profile/semantic candidate、用户已确认 semantic 默认。
- 实施内容：建立 closed-world mode 与可信配置；统一解析 lexical/semantic runtime；补齐 resolved identity 和稳定错误；保持请求体不可选 backend。
- 关键合同：C1、C2、C5。
- 交付物：runtime resolver/config view、identity projection、配置/漂移 contract tests。
- 验证方式：表驱动 semantic 默认、显式 lexical、未知值、缺字段、profile/manifest/embedding/collection mismatch；删除 fallback 禁令后测试必须失败。
- 完成门：API 与 Eval 不再各自拼装 runtime，且任何 semantic 失败路径都不构造 lexical/fixture adapter。

### M44A-B：FastAPI lifespan、readiness 与普通 API 接入

- 优先级：必须完成
- 依赖：M44A-A、现有 `EnterpriseProfileRuntime.close` 和 `/api/query` factory seam。
- 实施内容：应用生命周期 acquire/release Enterprise runtime；普通 RAG 请求从应用 runtime 获取 Knowledge Tool；增加安全 ready/diagnostic 状态；去除普通请求的小语料隐式兜底。
- 关键合同：C2～C4。
- 交付物：lifespan/runtime holder、API projection、liveness/readiness、生命周期和并发测试。
- 验证方式：初始化/关闭计数、并发只读请求、cross-thread、Milvus off、配置缺失、mid-init failure、shutdown；RAG unavailable 时零 Tool/Composer，SQL/系统错误边界不被伪装。
- 完成门：Uvicorn 配置正确时 semantic ready；配置错误或 Docker 未启动时用户能直接看到明确不可用，且一次请求绝不落入 lexical/小语料。

### M44A-C：external Eval 同源接入与 artifact/compare 演进

- 优先级：必须完成
- 依赖：M44A-A/B、M41 external product E2E 合同。
- 实施内容：external CLI 使用同一 resolver；默认 semantic、显式 lexical；补 runtime identity、resume/compare compatibility；保留 partition × suite 和一题一次执行。
- 关键合同：C1、C4、C5。
- 交付物：Eval CLI/runtime wiring、artifact/Trace schema 演进、旧 artifact compatibility 与 semantic/lexical compare tests。
- 验证方式：CLI parse/default、fake semantic product execution、旧 M41 lexical artifact 回读、resume mismatch、strict compare 和显式 runtime allowlist。
- 完成门：同一配置下 API 与 Eval 的 adapter/semantic/collection/embedding identities 完全一致；Eval 不再硬编码 lexical。

### M44A-D：运行体验、真实 Milvus 门与技术收口

- 优先级：必须完成
- 依赖：M44A-A～C、用户对精确真实 selector 的一次授权。
- 实施内容：补 Uvicorn、Milvus preflight、semantic/lexical Eval 命令和常见错误说明；运行聚焦/回归；执行一次获授权真实 semantic 产品链验证；记录 candidate 质量边界与 M45 handoff。
- 关键合同：C5、C6。
- 交付物：runbook/state 更新、必要 diagnostic/smoke、真实 artifact/Trace/报告、`docs/notes/m44a-notes.md` 和 finish-module 技术档案。
- 验证方式：按第 8 节执行；真实结果只记录实际 selector/调用数/identity，不自动重跑或切 lexical。
- 完成门：用户能够照 runbook 启动并判断 Milvus 是否生效；C6 闭合后才可宣称 M44A 完成，随后仍进入原定 M44/B2。

## 7. 决策门

### G44A-1：模块编号与 Phase 4B 映射（已确认）

#### 已确认方案：插入 M44A

- 做法：向量产品链单独命名 M44A；M44–M48 继续对应 B2–B6。
- 影响：本模块可独立验收，既有 capability owner、M46 reserve 和历史 artifact identity 不变。
- 适用条件：修复是 Phase 4B 施工前置，但不冒充 B2 能力。
- 风险：文档若把 M44A 写成新 B milestone 会再次形成双路线；由 C1 和 roadmap/state 收口控制。

#### 建议与确认时点

- 建议：已确认方案。
- 建议理由：既解决向量链路，又不迁移 sealed reserve 和后续模块号。
- 用户确认前允许推进：只读调查。
- 用户确认前禁止推进：写入 plan 或改 B2–B6 owner。
- 需要确认的时点：本计划定稿前；用户已于 2026-08-24 确认。
- 重开决策的条件：后续要求 M44A 承担 B2 或改变 reserve 首次解封模块。

### G44A-2：Enterprise 产品 retrieval 默认（已确认）

#### 已确认方案：semantic 默认、lexical 显式、失败关闭

- 做法：API 与 external Eval 的 Enterprise runtime 默认 semantic；lexical 仅显式 baseline；semantic 故障不 fallback。
- 影响：正常产品体验能证明使用向量数据库；Docker/Milvus 未启动时会明确不可用，不能靠 lexical 获得表面成功。
- 适用条件：用户把真正的向量检索视为 RAG 产品链的必要条件，同时仍需保留历史 lexical 可复现性。
- 风险：现有 semantic @20 质量低于 lexical，且运行依赖 Milvus 与 query embedding provider；本模块通过身份、readiness 和可比 Eval 暴露风险，不篡改默认选择。

#### 未选择方案

- lexical 默认、semantic 显式：无法解决普通体验实际不走向量库。
- semantic 默认、失败自动 lexical：会掩盖基础设施故障并污染 Eval runtime identity。

#### 建议与确认时点

- 建议：已确认方案。
- 建议理由：它让产品行为与用户对 RAG 的定义一致，并使失败和评测口径都可观察。
- 用户确认前允许推进：只读现状与参考调查。
- 用户确认前禁止推进：固定默认、fallback 或公开运行合同。
- 需要确认的时点：本计划定稿前；用户已于 2026-08-24 确认。
- 重开决策的条件：只有用户明确改变产品默认，或真实证据要求设计新的 semantic candidate；不能由开发便利或测试通过率触发。

本模块当前无其他用户决策门。真实 Eval selector 的一次性授权属于运行门，不是架构方案；实施到 C6 前按 runbook 精确请求。

## 8. 验证与验收矩阵

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
| --- | --- | --- | --- |
| C1 默认与同源 resolver | config/CLI/API 表驱动测试 | semantic 为 Enterprise 默认；lexical 只有显式选择；API/Eval resolved identity 相同 | 必须完成 |
| C2 snapshot/fail-closed | fake client + manifest/collection/provider mismatch 测试 | 任一身份或连接失败均不可用，零 lexical fallback、零 Evidence/Composer | 必须完成 |
| C3 生命周期 | lifespan/context/concurrency 测试 | 每进程一次加载、请求复用、shutdown 关闭；失败无半初始化资源 | 必须完成 |
| C4 产品数据流 | deterministic adapter integration + 真实 semantic smoke | 实际顺序包含 embedding/Milvus/SQLite/Evidence/Composer，citation 坐标可回查 | 必须完成 |
| C5 Trace/Eval/artifact | schema、旧 artifact、resume、compare 测试 | semantic identities 完整且三方一致；旧 lexical artifact 可读、原件不变 | 必须完成 |
| C6 真实完成门 | 用户授权的 exact Scenario 或 diagnostic_dev smoke | 真实 artifact/Trace 证明目标 collection 命中且产品回答完成；不触碰 held-out | 必须完成 |
| 运行体验 | runbook 命令回读 + Docker off/on 人工检查 | 未启动时明确 unavailable；启动且配置匹配后 ready，用户无需改代码选择 semantic | 必须完成 |
| Phase 4B 不回退 | M42/M43、reserve 和 roadmap contract 回归 | M44/B2、M46 reserve、历史 identity 均未被 M44A 改签 | 必须完成 |

聚焦验证顺序：resolver/config → semantic adapter/lifecycle → API → external Eval/artifact/compare → M31–M43 受影响 RAG/Harness/API 回归 → 全仓 deterministic pytest、compileall、`git diff --check` → 获授权真实 semantic 门。失败后先修复聚焦用例，不自动重复真实调用。

真实验证边界：M44A 不运行 held-out/all，不解封 reserve，不自动重建 collection。若用户只授权一个 exact Scenario，就只能把它记录为产品链 smoke，不能外推为 180 题质量基线；若授权 diagnostic_dev smoke，则只登记该 suite 的实际质量证据。历史 M34/M41 artifacts 全部只读，新的 semantic artifact 使用新 resolved runtime identity。

## 9. 依赖与交付物

### 依赖

- M31–M34 的 Knowledge Tool、Evidence/citation、external profile 和 semantic candidate。
- M41 external product E2E catalog/selector/artifact/compare 合同。
- 当前项目外 EnterpriseRAG-Bench dataset/profile/semantic manifests，以及与 manifest 匹配的 Milvus collection。
- 本地可达 Milvus、`pymilvus`、DashScope query embedding；真实 AnswerFlow 还需 Qwen Composer 配置。
- `docs/state/runbook.md`、`runbook-rag.md`、`rag-current-state.md`、`schema-retrieval-milvus-embedding.md` 的运行和身份纪律。

### 交付物

- API/Eval 共用的 Enterprise runtime resolver、semantic 默认和显式 lexical baseline。
- FastAPI lifespan runtime holder、fail-closed readiness/diagnostics 与资源关闭。
- semantic-aware Trace、resolved runtime、artifact/resume/compare 合同及兼容测试。
- Uvicorn、Milvus preflight、external Eval 的可复制运行说明。
- 聚焦/回归/真实 smoke 证据，以及 M44A notes、Phase 4B changelog 和命中 state 文档更新。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：semantic candidate 的召回优化、rerank/hybrid、索引重建/发布、业务小语料迁移、Schema Retrieval backend，以及任何 B2–B6 Agent 能力。
- 下一模块可直接消费的产物：M44/B2 可依赖一个可观察、fail-closed、API/Eval 同源的 Enterprise semantic RAG Tool；M45/B3 可消费 M44A 真实 semantic 失败层和 runtime identity 开展 campaign。
- 后续需要根据真实失败重新规划的内容：若 M44A 证实 dense-only 稳定漏召回，M45/B3 必须把具体失败簇、恢复动作和完成门写入 plan；若需要新索引/embedding/fusion，则必须形成独立版本化 candidate、显式 A/B 和准入标准，不能原位替换现有 identity。
- 可能存在的风险：139k unit-set 强校验和 metadata 常驻会增加启动时间/内存；SQLite 跨线程共享需严格只读；semantic manifest 中的 Milvus URI 可能与本机容器变化；旧 candidate 质量低于 lexical；真实 provider/network 可能使完成门暂时未闭合。以上风险只能显式诊断，不能用自动 fallback 消失。
- 最终目标与完成边界：M44A 的最终目标是普通 API 和 external Eval 默认、可证明地走真实 Milvus 产品链。只写完配置/测试、只跑 fake、或仅证明 collection 存在，都不算完成；必须满足 C6。完成 M44A 也不代表 RAG 质量优化完成，更不代表 B2/B3/B4 完成。

## 11. 开工条件

- 开工前无需确认：模块名 M44A；不改变 M44–M48 映射/M46 reserve；semantic 默认、lexical 显式且无 fallback；复用既有 candidate；不重建索引、不触碰 held-out。
- 实施中需要确认：执行 C6 前，按 runbook 请用户精确授权一个 external Scenario 或 `diagnostic_dev smoke` 恰好一次；若 candidate 身份损坏且需要重建/替换，重开 G44A 决策。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支；不得为方便开发自行恢复 lexical 默认、引入自动 fallback、缩小最终目标或改动 Phase 4B owner/reserve。
