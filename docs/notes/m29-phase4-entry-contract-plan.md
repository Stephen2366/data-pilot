# M29 Phase 4 入口盘点与合同冻结计划

> 状态：计划草案，待用户确认 G0（公开响应迁移）、G1（首批 corpus）和初始出站政策后实施。
>
> 能力里程碑：本模块对应 Phase 4 **P0「阶段入口与合同冻结」**。P0 是能力里程碑，不等于以后所有里程碑都只用一个模块；M29 只完成进入 P1/P2 所需的现状盘点、语义合同和决策材料，不实现知识发布、RAG 检索或 LangGraph。
>
> 本轮边界：本文只制定计划，没有修改运行代码、数据库、Eval 合同、默认模型、检索配置或公开响应。

## 1. 范围判断：为什么把完整 P0 作为一个 M29

### 1.1 结论

M29 应围绕一个主要问题形成闭环：

> 在开始 RAG 施工前，DataPilot 到底把谁当可信调用者、用哪几条状态轴描述一次请求、什么算 Evidence、首批知识以谁为准、哪些数据能外发，以及未来如何评测这些行为？

这个问题需要把 API、Trace、Eval、RBAC、知识草稿和出站现状放在同一张图里判断。若再拆成多个小模块，用户会分别看到“状态枚举”“知识清单”“Eval 题目”，却难以理解它们如何共同保证一个回答可信；若把 P1 的知识发布和 P2 的 RAG 垂直切片也塞进来，又会在关键合同未确认时同时改数据库、索引、响应和模型链路，执行容易失控。

因此 M29 覆盖完整 P0，但明确停在“盘点 + 合同冻结 + 决策记录 + 后续验收蓝图”。它本身可独立验收：验收结果不是“RAG 已能回答”，而是“P1/P2 不再需要临场猜核心语义”。

### 1.2 不建议的拆法

- 不把“API inventory”“知识 inventory”“Eval Scenario 草案”分别拆成三个模块：三者共同决定 G0/G1，独立验收价值弱。
- 不在 M29 顺手实现 Evidence 类、Knowledge Tool、索引发布或 LangGraph：这些分别属于 P1、P2、P3。
- 不以“新增多少文件或枚举”为拆分依据；以用户能否形成一套完整的可信回答心智模型为准。

## 2. 已复核的当前事实

### 2.1 上一模块与阶段入口

- M28 没有独立 `*-plan.md`；其计划、调查、修复和验证材料统一保存在 `docs/notes/m28-text2sql-review-notes.md`。
- Git 当前 `HEAD` 为 `29e12f2 M28accept`，M28 已于 2026-08-12 验收；`docs/state/AI_CONTEXT.md` 已切到“待进入 Phase 4 RAG（规划中）”，无阻塞项。
- M28 最终确定性验证为全仓 `223 passed, 1 warning`，未运行新的真实 LLM Eval，未切换模型、检索、embedding、数据库或产品 API 默认。
- M28 遗留的 F5（Eval closed-world 完整性）、F6（Review 长期证据）和 F7（LangFuse question/answer 脱敏）不阻塞进入 P0，但会进入 M29 inventory；F7 在任何 RAG/Hybrid Cloud 出站前是硬前置。

### 2.2 当前产品接口和消费者

- `/api/query` 的实际控制流全部进入 SQL；`AgentResponse.route` 虽预留 `rag/hybrid`，当前没有 Router 或 RAG 实现，也没有 `none` 语义。
- `AgentResponse` 只有 `route`、单一 `safety_status`、`blocked_reason` 和 `error_type`；执行失败、回答不足、安全拦截仍可能挤在同一组字段里。
- `docs_used` 是开放的 `list[dict]`，没有 document revision、chunk、anchor、用途、授权决定或 claim-to-citation 关系，不能成为 Evidence 事实源。
- Streamlit 直接消费 `safety_status`、`blocked_reason`、SQL、rows、`docs_used` 和 `tool_calls`；README、旧 API 测试、M27 Eval adapter 也依赖当前响应形状。G0 不能只看 Pydantic model，必须覆盖这些消费者。
- 旧代码注释强调响应“只增不改”，但 Phase 4 roadmap 已把迁移选择提升为 G0 决策；两者不是同级事实源，最终以 roadmap 和 M29 consumer inventory 为准。

### 2.3 当前 caller 与权限边界

- `QueryRequest.user_role` 是客户端直接提交的字符串；API、Text2SQL planner、SQL Guard 和 Trace 都直接使用它。
- Streamlit 允许用户从下拉框自行选择 `ops/admin/customer_service/demo_user`。这可以作为 demo fixture，不能宣称为生产可信身份。
- 当前 SQL RBAC 是角色级表 allowlist + 敏感字段策略，没有认证主体、caller id、thread owner 或文档级 ACL。
- 代码和 `database-current-state.md` 都规定 admin 也不能通过自然语言 Text2SQL 明文直出敏感字段；README 中“除 admin 外不可访问”的表述已经漂移，应在后续文档同步时修正，但 M29 不改变当前安全默认。

### 2.4 当前知识事实源与 Text2SQL 暴露面

- `domain_pack/kb_docs/` 只有 `.gitkeep`，还没有经审查的权威知识原件。
- `scripts/seed_data.py` 内嵌 10 条知识草稿，数据库 `knowledge_docs` 保存完整正文；其中政策、客服规则、安全说明和指标说明混在同一个运行时表中。
- `knowledge_docs` 出现在 ORM、Alembic、`app.db.base` 模型注册、schema description、Schema Retrieval alias、SQL RBAC allowlist、seed/数据库验证、旧 case、测试和文档说明中。
- `admin/ops` 当前可访问全部 14 表，`customer_service/demo_user` 的 SQL allowlist 也包含 `knowledge_docs`；因此“从 Text2SQL 隔离知识正文”不能只删一条 RBAC 配置。
- 三条指标类 seed 与 `metrics.yaml` 存在双事实源风险：GMV、优惠券、行为漏斗口径应由 `metrics.yaml` 生成或校验，不能复制成可独立编辑正文。
- Schema Retrieval 当前 corpus 为 195 条、hash 为 `8a8b6626...`；P1 将 `knowledge_docs` 从 Schema corpus 迁出后必须形成新的 count/hash 和 runtime identity，但 M29 不执行迁移。

### 2.5 当前 Trace、Cloud 与 Eval

- JSONL `TraceRecord` 默认保存完整 question、answer、SQL、columns、rows 和 `docs_used`。这适合当前本地调试，但不能无条件沿用为 RAG 长期留存策略。
- LangFuse 默认关闭；当前 post-hoc backend 不上传 rows/docs 正文，却会上传完整 question 和 answer。RAG/Hybrid 不能因为“LangFuse 已接入”就默认获得 Document Evidence 出站权限。
- 当前模型调用集中在 Text2SQL QueryPlan/SQL generation；未来 Router、Evidence 充分性、答案合成、rewrite、rerank、Eval Judge 等用途尚不存在，也没有各自的 OutboundDecision。
- M27 `m27-v3` 只面向 Text2SQL，必须只读冻结。当前 Scenario 只有 `core/stress/manual_lab`，assertion 只覆盖 Result、Output、Schema Context、QueryPlan、Trace、Safety、Join 和 Metric。
- `project_eval_run()` 只过滤选中的 Scenario，没有核对 selected Scenario、replicate、assertion、policy/hash 是否恰好完整；缺项 artifact 仍可能投影出看似可信的 Gate，这是 M29 必须为 Phase 4 Eval 设计明确的 closed-world 合同。
- 旧 `eval/cases_plan.md` 有 5 条 RAG、3 条 Hybrid 题目，但它们把 `knowledge_docs` 当 SQL 表、只做 `contains` 检查，属于历史候选素材，不是 Phase 4 canonical contract。

## 3. 当前问题

M29 要解决的不是“RAG 用哪个向量库”，而是以下前置问题：

1. **状态不正交**：route、execution、answer、safety 尚未形成独立、可组合、可评测的语义。
2. **caller 不可信**：请求体角色既承担 demo 选择又被当作权限事实，无法支撑文档 ACL 和 thread owner。
3. **知识双事实源**：数据库 seed 正文、未来 Markdown 和 `metrics.yaml` 之间尚无唯一 authority 与发布方向。
4. **Evidence/citation 只有占位字段**：`docs_used` 无法证明答案实际看过、仍有效且有权使用哪段文档。
5. **出站用途未分层**：当前 Qwen 与 LangFuse 行为不能自动授权 RAG 新数据类别和新模型节点。
6. **Eval 仍是 Text2SQL 合同**：没有 RAG/Hybrid/ACL/citation/partial/clarification 的 Scenario 语义，也缺 completed run 的 closed-world 校验计划。
7. **后续模块容易抢控制权**：如果不先冻结 seam，Knowledge Tool、顶层 Graph、Answer Composer 和 Eval 都可能各自发明状态、答案或 citation。

## 4. 模块目标

M29 完成后应达到：

1. 形成一份可追溯的 Phase 4 capability inventory，覆盖 API/consumer、Trace、Eval、caller/RBAC、Schema Retrieval、knowledge seed 和 outbound payload。
2. 冻结内部四轴状态语义、稳定 reason code 规则和代表场景真值表；不再用一个字段表达多个问题。
3. 冻结最小 trusted caller interface：明确客户端声明、demo/test adapter 和未来生产认证来源的区别。
4. 给出 G0 公开响应迁移的完整影响面和最终选择；本模块只记录选择，不实施响应变更。
5. 对 10 条 seed 逐条给出采用、重写、拆分、合并或淘汰结论，并明确 authority、用途、data classification、ACL 与候选外部接收方。
6. 冻结 Phase 4 Eval 与 `m27-v3` 的隔离边界、Scenario 最小字段、三种用途分集和 closed-world identity 规则。
7. 产出 P1/P2 可直接消费的 deterministic fixture、测试边界和任务拆分，不提前固定其文件结构、top-k、chunk、模型、存储或循环参数。

## 5. 范围与非目标

### 5.1 本模块范围

- 只读盘点当前代码、文档、测试、Eval artifact/schema 与外部出站点。
- 在 M29 notes 中建立 inventory、决策记录、四轴真值表、reason code registry 草案、知识清单、outbound matrix 和首批 Scenario 蓝图。
- 确认 G0、G1、初始出站政策，并记录选择、理由、影响和以后重新打开的条件。
- 确认 Phase 4 Eval 采用独立新合同 family 还是版本化扩展；推荐独立 family，最终结论需写出兼容理由。
- 定义 P1/P2 必须满足的 interface 与验收，不实现这些 interface。
- 用确定性检查证明 inventory 没漏掉当前已知入口，并确认本模块没有改变运行行为。

### 5.2 非目标

- 不创建、重写或发布正式 Markdown corpus，不改数据库 seed，不做 migration。
- 不从 SQL RBAC 删除 `knowledge_docs`，不重建 Schema corpus，不写 Knowledge catalog/ingestion/index。
- 不新增 Evidence/Authorization/Outbound 的运行时代码，不改 `AgentResponse`。
- 不实现 Knowledge Tool、retriever、answer composer、citation validator、Router、LangGraph 或 thread 状态。
- 不安装 LangGraph，不选择向量库、embedding、reranker、LLM、chunk、top-k、阈值、超时或循环次数。
- 不启用 LangFuse Cloud，不调用真实 Qwen/embedding/Eval Judge，不运行真实 LLM Eval。
- 不修复 M28 已登记的 Text2SQL 能力缺口，不把 M29 变成新一轮 SQL 调分。
- 不更新 README；按项目约定留到阶段结束统一整理。README 漂移只登记为后续同步项。

## 6. 本模块要冻结的关键合同

这里冻结的是后续模块必须遵守的**语义 interface**，不是提前决定实现类名或目录。

### 6.1 四轴状态 interface

M29 必须用代表场景真值表冻结以下四轴，具体枚举名可在实施时微调，但含义不得交叉：

| 轴 | 最小候选值 | 唯一回答的问题 | 典型禁区 |
|---|---|---|---|
| route | `sql / rag / hybrid / none` | 本轮选择哪类 Evidence 路径？ | 不表达 timeout、partial 或越权 |
| execution | `not_started / completed / external_unavailable / failed`，Hybrid 另保留分支状态 | 计划中的 Tool/流程是否完成，技术根因是什么？ | 不表达答案是否充分或安全是否通过 |
| answer | `complete / partial / clarification_required / unsupported / insufficient_evidence / no_answer` | 最终能向用户交付什么程度的答案？ | 不承载 provider 错误或 ACL 判决 |
| safety | `passed / blocked` | 确定性安全检查是否允许继续/展示？ | 不把“没搜到”或“模型不会”记为 blocked |

实施时至少用以下反例校验：

- Router 无法判断需求且需要补充条件：`route=none`、`execution=not_started`、`answer=clarification_required`、`safety=passed`。
- RAG 检索正常但没有足够证据：`route=rag`、`execution=completed`、`answer=insufficient_evidence`、`safety=passed`。
- 远程 provider 超时且没有可用答案：`execution=external_unavailable`，不能自动改成业务 `failed` 或安全 `blocked`。
- 文档存在但 caller 无权访问：对外只允许安全投影；不得通过 reason、标题、命中数或 citation 泄露其存在。
- Hybrid 的 SQL 分支完成、必需 RAG 分支不可用：保留两分支 execution；只有独立成立且安全的 SQL 结论才允许 `answer=partial`。
- 文档含伪系统指令：route 不被正文改变；确定性策略阻断危险动作，正文只作为不可信 Evidence 内容处理。

### 6.2 reason code interface

reason code 必须满足：稳定、有限、机器可判、与四轴正交；用户文案与内部错误堆栈不能充当 code。M29 至少覆盖下列语义族：

- 路由/产品：需要澄清、不支持能力、不需要重新取证；
- 取证：无候选、无授权 Evidence、revision 失效、检索不可用、provider 不可用；
- 安全：caller 不可信、ACL 拒绝、outbound 拒绝、SQL Guard 拒绝、citation 无效；
- 回答：Evidence 不足、Hybrid 必需分支缺失、仅允许 partial；
- 运行：预算耗尽、合同不兼容、状态版本不兼容。

M29 不提前穷举未来所有 code；只冻结首批 Scenario 和 P1/P2 所需集合，以及“未知 code 必须在加载/投影时失败”的扩展纪律。

### 6.3 trusted caller interface

后续运行时 seam 至少要能表达：

- 稳定 caller identity；
- 已解析角色/权限声明；
- identity 来源与 trust level；
- tenant/thread owner 所需的最小绑定信息；
- 当前入口是 test、demo 还是真实认证 adapter；
- 审计 reference，而不是认证密钥本身。

不变量：`QueryRequest.user_role` 只能是未验证声明或 demo 输入，不能直接构造生产 trusted caller。P1/P2 测试可以注入 deterministic caller fixture；JWT/OAuth、用户目录和登录系统不进入 M29/Phase 4 主线。

### 6.4 Evidence/citation 交接合同

M29 不实现 Evidence，但必须冻结 P1 的最小约束：

- Evidence 公共外壳与 Document/SQL typed payload 分离；授权、检索诊断、runtime identity、outbound decision 不塞进万能对象。
- 必须区分候选、选中、实际进入生成器、最终 citation 使用四个阶段。
- citation 只能指向本轮生成器实际可见、当前有效、用途允许的 Evidence；ID 由代码分配和校验。
- `docs_used` 只允许作为未来兼容投影，不能反向成为内部事实源。
- Tool 只返回 RetrievalOutcome/Evidence；Gate、Composer、Citation Validator、顶层 controller 各自只有一个责任所有者。

### 6.5 Phase 4 Eval interface

推荐把 Phase 4 建成独立合同 family，而不是原地扩写 `m27-v3`：两者的 route、Evidence、citation、ACL、Hybrid 和状态空间差异已经超出“小版本加字段”。M29 实施时需用 inventory 最终确认，并记录：

- `m27-v3` catalog/artifact/projector/review 全部只读；
- 新 Scenario 至少包含 `scenario_id`、question、caller fixture、authority refs、所需 Evidence、预期四轴状态/reason、typed assertions、用途分集和 contract identity；
- 一个 Scenario 一次执行，多条 route/retrieval/citation/answer/safety/trace assertion 共享同一份 ExecutionEvidence；
- diagnostic/dev、held-out decision、required contract/security 三类用途必须显式区分；使用 held-out 结果继续调参后，该题降级为 dev；
- completed run 进入报告/Gate 前，selected Scenario、replicate、assertion、policy、contract 和 runtime identity 必须恰好匹配；缺失、额外、重复都失败关闭；
- retrieval benchmark 与端到端 answer Eval 分开；judge 失败为 `not_observed` 或 advisory，不伪装成业务错误。

## 7. 首批知识 inventory 的处理原则

M29 要逐条审查当前 10 条 seed，不能整包复制。初始判断如下，最终结论在 G1 后冻结：

| seed | 初始处理方向 | 原因/待核对 |
|---|---|---|
| 基础退款政策 | 重写，可能与质量问题规则建立明确关系 | 当前一句话混合多类退款，缺 authority/revision/anchor |
| 质量问题退款规则 | 保留并重写 | 可形成首批 RAG gold，但需避免与基础政策互相矛盾 |
| 物流延迟处理规则 | 保留并重写 | 可形成纯 RAG 与 Evidence 不足对照 |
| 发票开具规则 | 保留并重写 | 可形成纯 RAG；需核对规则完整性和角色 |
| 高价值客户服务规则 | 条件保留 | “近 12 个月消费”是数据库事实条件，规则与实时判断必须分开，适合后续 Hybrid 而非纯 RAG 自证 |
| 敏感字段访问规范 | 条件保留并重写 | 适合安全说明，但不能让文档正文取代确定性安全策略 |
| 演示账号数据范围 | 条件保留并重写 | demo policy 可作为回答知识，实际权限仍由代码策略裁决 |
| GMV 指标口径说明 | 不作为独立可编辑事实源 | 应由 `metrics.yaml` 生成或一致性校验 |
| 优惠券核销规则 | 不直接照抄 | 先映射 `coupon_order_count/coupon_usage_rate`，由 `metrics.yaml` 生成或校验；避免把分析约束混成政策 |
| 行为漏斗口径说明 | 不作为独立可编辑事实源 | 应由 `metrics.yaml` 的 `add_to_pay_conversion_rate` 生成或校验 |

每条最终记录至少包含：stable document key、authority reference、知识类型、回答/约束/上下文用途、data classification、`public` 或显式 allowed roles、是否允许 embedding/rerank/generation/judge/Cloud、候选 canonical Scenario、处理结论和理由。

## 8. 首批 Scenario 蓝图

M29 不写可运行 scorer，但必须把以下行为变成可实施的 canonical blueprint；每条都要写 authority、caller、预期四轴、Evidence、reason、assertion effect 和用途分集：

1. 纯 SQL 正常回归：证明 Phase 4 合同不会破坏现有 Text2SQL。
2. 纯 RAG 政策回答：命中当前有效、已授权文档并形成合法 citation。
3. 指标说明 RAG：证明内容来自 `metrics.yaml` 派生/校验，而非数据库正文副本。
4. Evidence 不足：检索完成但资料无法支持用户问题，应保守停止。
5. 未授权文档：响应、Trace、citation 和诊断都不得泄露存在性。
6. 文档投毒：正文中的伪系统指令/伪 citation 不能改变控制流。
7. 文档 revision 失效：旧 revision 不得服务新回答，但审计 identity 可追溯。
8. 外部不可用：execution 与 answer/safety 分开，不能投影为业务失败。
9. 完整 Hybrid：SQL Evidence + Document Evidence 都是必需分支。
10. Hybrid partial：一个分支失败时，只保留独立成立且安全的结论。
11. 澄清：不取证或停止继续取证，等待用户补齐条件。
12. 不支持能力：与安全拒绝、Evidence 不足明确区分。
13. caller trust 反例：篡改请求体 role 不得升级为生产可信 caller。
14. citation 完整性反例：引用不存在、未进入生成器、越权或 revision 不匹配时 required assertion 失败。

不要求 M29 冻结每类的最终数量，也不为凑题量扩大 corpus。P1/P2 只实现与已确认 corpus 和能力直接相关的首批集合。

## 9. 主要工作切片

### M29-A：建立 inventory 与证据索引

1. 在 `docs/notes/m29-phase4-entry-contract-notes.md` 建 implementation checklist。
2. 建 API/consumer matrix：请求、响应、Streamlit、测试、Eval adapter、Trace、README/runbook 的读取/写入关系。
3. 建 caller trust matrix：角色从哪里进入、哪些模块消费、当前能证明什么、不能证明什么。
4. 建 `knowledge_docs` 暴露矩阵：ORM/Alembic/seed/schema_desc/Schema Retrieval/RBAC/prompt/Trace/Eval/test/docs 全入口。
5. 建 outbound payload matrix：当前与未来节点按 receiver、用途、数据类别、字段、默认决定、降级行为登记。
6. 建 Eval migration matrix：M27 可复用纪律、不可复用字段、F5/F6/F7 处置位置。

完成门：所有结论能指回具体代码/state/历史 artifact；没有只靠 roadmap 猜测的“当前事实”。

### M29-B：用户决策门与语义冻结

1. 基于 M29-A inventory 向用户提交 G0、G1 和初始出站政策的最终选项、影响与推荐。
2. 记录用户选择，不把未确认倾向写成既定事实。
3. 冻结四轴真值表、首批 reason code、trusted caller interface 和公开投影原则。
4. 明确哪些兼容字段只读投影、哪些内部字段永不直接公开。

完成门：任一代表场景都能唯一解释 route/execution/answer/safety；G0/G1 不再留给 P1/P2 猜。

### M29-C：知识与出站合同冻结

1. 逐条完成 10 条 seed disposition。
2. 明确 `metrics.yaml` 派生说明与政策 Markdown 的不同发布路径。
3. 冻结首批 data classification、ACL 和外部接收方/模型节点用途。
4. 指定未获授权时的 deterministic fallback；默认拒绝不能退化为静默外发。
5. 列出 P1 `knowledge_docs` 隔离的全量检查范围和更新顺序，但不执行迁移。

完成门：不存在数据库 seed 与 Markdown 同时作为权威正文；每种出站用途都有 allow/deny/fallback。

### M29-D：Scenario、Eval 与 P1/P2 handoff

1. 将第 8 节蓝图收敛为首批 canonical Scenario matrix。
2. 冻结新 Eval family 的 identity、用途分集、一题一次执行与 closed-world 完整性规则。
3. 为 P1/P2 给出 deterministic fixture 和 required/advisory assertion 边界。
4. 把 P1 拆成可执行但不预先固定文件名的候选能力切片；把 P2 依赖写清，不提前规划 P3 细节。
5. 形成 M29 验收包和用户可读讲解。

完成门：P1/P2 能直接依据 M29 合同写各自 module plan，不需要重新定义 caller、Evidence、状态、corpus 或出站语义。

## 10. 关键 seam 与模块深度要求

M29 的设计应让后续形成少量深 module，而不是把每个字段拆成浅层转发对象：

- **可信 caller seam**：生产 adapter 与 test/demo adapter 是两个真实 adapter；业务模块只消费已解析的 trusted caller interface。
- **Knowledge authority/publish seam**：权威原件与派生 catalog/chunk/index 分离；发布复杂度藏在实现内，调用方只看 active corpus identity。
- **Knowledge Tool seam**：调用方提交问题、trusted caller、用途和预算，获得 typed RetrievalOutcome/Evidence；ACL、检索、去重、revision 校验在内部。
- **Shared Answer Evidence Gate seam**：SQL/RAG/Hybrid 复用同一充分性与硬约束裁决，不在每条路径复制状态逻辑。
- **Outbound policy seam**：所有远程 adapter 调用前消费同一决策 interface；provider 相同不代表用途授权相同。
- **Eval seam**：Scenario 只执行一次，多个 scorer 只读同一 ExecutionEvidence；报告与 Gate 是投影，不反写运行事实。

删除测试：如果删掉这些 seam，复杂度会重新散落到 API、Tool、Graph、Trace 和 Eval 多个调用方，说明它们能提供真实 locality；反之，只有一个实现且没有测试 adapter 的假接口不应在 M29 中提前设计。

## 11. 依赖与交付物

### 11.1 依赖

- M28 已验收，工作树干净。
- `docs/phase4-roadmap.md` 第 4、6、15、16、17 节。
- `docs/state/AI_CONTEXT.md` 及 runbook、eval-baselines、database-current-state、schema-retrieval state、changelog 中的当前事实。
- 当前 API/schema、Trace/LangFuse、RBAC、Schema Retrieval、knowledge seed、M27 Eval/projector 和 Streamlit consumer。
- 用户对 G0、G1、初始出站政策的确认。

### 11.2 计划交付物

- 本计划：`docs/notes/m29-phase4-entry-contract-plan.md`。
- 实施 notes：`docs/notes/m29-phase4-entry-contract-notes.md`，承载 checklist、inventory、决策记录、真值表、Scenario matrix、参考复核和验证快照。
- M29 完成后的 state/changelog/dev-log 更新，按 `finish-module` → `finish-docs` 流程进行。
- 若 inventory 证明需要机器可读 artifact，再由 M29 决策是否增加最小数据文件；本计划不提前固定路径或 schema。
- P1/P2 handoff 清单；不提前创建空目录、占位类或无调用者的 adapter。

## 12. 验证方式

### 12.1 Inventory 完整性

- 用 `rg` 对 `AgentResponse`、`docs_used`、`safety_status`、`blocked_reason`、`user_role`、`knowledge_docs`、LangFuse/model provider、M27 contract/projector 做反向搜索。
- inventory 每个入口记录“当前行为、Phase 4 风险、后续 owner、验证方式”；未归类入口为验收失败。
- 对 10 条 seed 做数量与 key 对账；对 `metrics.yaml` 中相关 metric 做 authority 对账。

### 12.2 合同一致性

- 用代表场景真值表检查四轴无交叉；同一事实不得在两个轴出现相互矛盾的值。
- reason code 做唯一性、所属轴、对外可见性和信息泄露检查。
- G0 迁移矩阵覆盖 Pydantic、API handler、Streamlit、现有测试、Trace、Eval adapter 和文档消费者。
- 新 Eval 设计逐项对照 M27 的一题一次、`not_observed`、Gate、runtime identity 和 closed-world 缺口。

### 12.3 安全与出站桌面推演

- 对未授权文档、标题枚举、命中数侧信道、伪指令、stale revision、citation 越权、caller role 篡改逐项推演响应/Trace/Eval 投影。
- 对每个远程用途检查 receiver、payload 字段、data class、decision、fallback；缺一项即默认 deny。
- 明确 LangFuse disabled 时本地 JSONL 仍是主路；不得以 Cloud 不启用为理由忽略本地最小化。

### 12.4 确定性回归

M29 预期不改运行代码，因此只运行与 inventory 事实直接相关的无网络回归，并在 notes 记录精确结果：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q tests/test_m5_agent_response.py tests/test_m16_trace_router.py tests/test_m27_foundation.py tests/test_database_upgrade.py --basetemp=.agent_work/temp/pytest-m29-contract
git diff --check
```

若实施中意外需要改运行代码，应暂停并重新评估范围；不能用扩大 pytest 清单掩盖模块越界。M29 不运行真实 LLM Eval、Milvus、embedding 或 LangFuse Cloud smoke。

## 13. 验收标准

M29 只有同时满足以下条件才算完成：

1. API/consumer、caller、knowledge exposure、outbound、Trace、Eval 五类 inventory 均有代码证据和 owner。
2. G0、G1、初始出站政策已有用户明确选择和影响记录；未确认项没有被写成默认行为。
3. 四轴状态能无歧义覆盖 SQL、RAG、Hybrid、clarification、unsupported、insufficient evidence、partial、blocked 和 external unavailable。
4. 首批 reason code 有稳定语义、所属轴和安全投影；未知 code 不能静默通过。
5. 10 条 seed 全部有 disposition、authority、用途、classification、ACL 和 outbound 结论；不存在双事实源。
6. `knowledge_docs` 从 Text2SQL 隔离的检查范围覆盖 RBAC、schema_desc、Schema Retrieval、prompt/Trace、case/test、state/runbook，而不只是一处表 allowlist。
7. 首批 Scenario 覆盖 roadmap 要求，并明确 authority、caller、预期状态、Evidence、assertion effect 和用途分集。
8. `m27-v3` 保持只读；Phase 4 Eval 的 identity、一次执行、多断言、closed-world 和 `not_observed` 规则明确。
9. P1/P2 deterministic fixture 和测试边界明确，不依赖真实模型或向量库验证核心合同。
10. 没有提前冻结模型、chunk、top-k、阈值、循环次数、LangGraph 文件结构或正式索引实现。
11. 聚焦确定性回归和 `git diff --check` 通过；没有真实 provider 调用、数据库 mutation 或默认配置切换。
12. 用户能用大白话说明：为什么请求体 role 不可信、为什么 route 不等于执行状态、为什么 `docs_used` 不等于 citation、为什么数据库 seed 不能当知识权威原件、为什么 retrieval 分数不等于答案正确。

## 14. 决策门

### G0：公开响应迁移

- **方案 A（推荐）**：保留 `/api/query`，内部先建立四轴状态和 typed Evidence，公开响应增量增加结构化状态/citations，并为 `docs_used` 等旧字段提供兼容投影。
- **方案 B**：新增版本化端点/响应，旧端点继续只承担 SQL 兼容。
- **当前依据**：项目只有单体 API、Streamlit 和仓内测试这些可控消费者，方案 A 的迁移成本更低；若 M29 inventory 发现仓外严格 typed client，再转 B。
- **生效时间**：P1/P2 任何公开响应实现前。

### G1：首批正式 corpus

- **方案 A（推荐）**：以 10 条 seed 为草稿逐条治理；只发布有 canonical Scenario 的政策/客服/安全规则，并由 `metrics.yaml` 生成或校验指标说明。
- **方案 B**：同时扩入长政策和产品说明，提前验证 parent/child。
- **当前依据**：当前文档很短、`kb_docs` 为空，首要风险是 authority/ACL/citation，不是长文召回；方案 B 会把切分实验提前混入安全地基。
- **生效时间**：P1 发布正式 corpus、构建正式索引前。

### G1-O：初始出站政策

- **方案 A（推荐）**：审计当前 Qwen payload；本地/deterministic 完成检索与合同测试，只对明确 data class + receiver + node purpose 放行，LangFuse Cloud 继续关闭。
- **方案 B**：Phase 4 全本地处理。
- **方案 C**：模拟 corpus 默认允许远程 embedding/rerank/generation/Cloud。
- **当前依据**：A 既不虚构当前已有本地生成链路，也不把“模拟数据”误当通用授权；未获授权的节点必须 deterministic deny/fallback。
- **生效时间**：任何 Document Evidence、SQL rows、完整 answer 或新增 query 类别外发前。

### D2：Phase 4 Eval 合同 family（模块内设计决策）

- **推荐**：新建独立 Phase 4 family，复用 M27 的评测纪律，不继承其仅 SQL 的状态和 artifact schema。
- **替代**：版本化扩展 M27 artifact family。
- **选择标准**：能否在不制造大量 optional 字段和兼容分支的情况下表达 route、typed Evidence、citation、ACL、Hybrid 分支和四轴状态。若删除新 family 后复杂度会扩散进 M27 loader/projector/review，说明独立 seam 更深。

## 15. 风险与控制

| 风险 | 早期信号 | 控制 |
|---|---|---|
| M29 变成纯文档摘抄 | inventory 没有代码位置、consumer 或验证方式 | 每条结论绑定当前入口和后续 owner |
| M29 偷跑 P1/P2 | 开始写 Evidence 类、Markdown corpus、index 或 AgentResponse | 暂停并另建下一模块 plan |
| 状态枚举过度设计 | 为尚不存在的循环/多 Agent 预留大量值 | 只冻结首批 Scenario 必需值，未知值严格失败 |
| Evidence 变万能对象 | caller、ACL、diagnostics、runtime、outbound 全塞入同一结构 | 公共外壳 + typed payload，其他决定独立引用 |
| G0 只看 Pydantic | Streamlit、Trace、Eval/测试在实施时才破裂 | consumer matrix 是 G0 前置证据 |
| corpus 继续双写 | seed、Markdown、数据库都能编辑正文 | authority 单向发布；数据库/索引只作可重建投影 |
| ACL 泄露存在性 | 未授权标题/命中数进入错误或 Trace | 安全投影桌面推演 + required Scenario |
| “模拟数据”放宽出站 | 新节点默认复用 Qwen/LangFuse | receiver × purpose × data class 显式矩阵，缺省 deny |
| Eval 新旧混算 | Phase 4 分数沿用 `m27-v3` 分母/基线 | 独立 identity/family；旧 artifact 只读 |
| held-out 被调参污染 | 根据失败反复改实现仍称 decision set | 立即降级 dev，并准备新的未污染保留集 |
| 参考项目主导路线 | 复制其强制搜索、平均分、平台结构 | 只借鉴局部 seam，以 DataPilot required Gate 和安全合同裁决 |

## 16. 参考源码定点复核记录

### 16.1 当前问题与证据

- DataPilot Trace 未保存“实际进入生成器的 Document Evidence”这一独立阶段，`docs_used` 也没有稳定 reference identity。
- M27 Eval 有一题一次与 typed assertion 的强基础，但 Phase 4 需要 retrieval/citation/ACL/Hybrid 状态，且当前 projector 有 closed-world 缺口。

### 16.2 优先参考与源码入口

- `ARAG-STATE`：`agentic-rag-for-dummies/project/rag_agent/graph_state.py` 与 `nodes.py`。
- `ARAG-EVAL`：`agentic-rag-for-dummies/notebooks/evaluation.ipynb` 中 `query_rag`、`assert_saved_outputs_match_dataset`、`score_answer`。
- `DBGPT-EVAL`：DB-GPT 的 `rag/evaluation/retriever.py` 与 `answer.py`。

### 16.3 借鉴内容

- 借鉴 ARAG 把真实 Tool retrieval context 随运行结果保存、Tool call/iteration 单独计数、回答与 retrieval context 一起固化后再评分。
- 借鉴其保存结果与数据集 identity 对账的意识，补强 DataPilot completed artifact 的 closed-world 校验设计。
- 借鉴 DB-GPT 把 retrieval similarity/MRR/Hit Rate 与 answer relevancy 分成不同 evaluator，避免一个总分掩盖失败位置。

### 16.4 DataPilot 适配

- Context 不能只保存正文字符串，要保存 EvidenceRef、revision、anchor、授权决定和“实际进入生成器”的阶段身份。
- retrieval 与 answer 分开评估后，仍统一挂在同一 Scenario ExecutionEvidence 下；不能为每个 metric 重跑 Agent。
- 外部 unavailable/judge failure 使用 DataPilot 的 `not_observed` 和 Gate 纪律；安全/citation/状态 required assertion 不由平均分替代。

### 16.5 明确不照搬

- 不照搬 ARAG 首步强制搜索、开放 rewrite/压缩、字符串 Tool context、顺序/迭代默认值或多层 Graph。
- 不照搬 notebook 简单平均 RAGAS 分数、把 pipeline failure 只跳过后继续报均值，或把数据行匹配当完整 closed-world Gate。
- 不照搬 DB-GPT 在空 prediction/context 时直接记 `0.0` 的统一语义；DataPilot 必须区分业务错误、预期不足和不可观察。
- 不引入 DB-GPT 的平台 DAG/operator 体系，也不在 P0 选具体 evaluator 模型。

### 16.6 验证方式

- 用首批 Scenario 检查同一次运行能同时投影 retrieval、citation、answer、safety 和 Trace assertion。
- 用缺 Scenario、额外 assertion、重复 replicate、policy/hash 不匹配的反例验证 completed run 必须失败关闭。
- 用 pipeline unavailable 与 judge unavailable 反例验证不污染业务 failed 分母。

## 17. 需要用户在实施前确认的问题

1. 是否确认 G0 采用方案 A：同一 `/api/query` 后续增量扩展，保留兼容投影？
2. 是否确认 G1 采用方案 A：先治理 10 条 seed，只发布有 canonical Scenario 的短政策/规则，指标说明由 `metrics.yaml` 生成或校验，暂不引入长文 parent/child？
3. 是否确认初始出站采用方案 A：本地/deterministic 先行，按 receiver × node purpose × data class 显式放行，LangFuse Cloud 继续关闭？

这三个确认不会让 M29 立即修改 API、发布 corpus 或外发数据；它们只是让 M29 能把 P1/P2 的合同和验收边界固定下来。具体允许哪些文档发给哪个远程节点，仍需在 M29 的逐条 inventory 中形成明细并由用户最终确认。

## 18. Implementation Checklist

### 开工

- [x] 新建 `docs/notes/m29-phase4-entry-contract-notes.md`，记录本计划链接和 checklist。
- [x] 确认 `git status --short`，记录既有改动归属。
- [x] 重新读取最新 state；若用户已修改 G0/G1/outbound 选择，以最新确认覆盖本计划草案。

### Inventory

- [x] API/consumer matrix 完成。
- [x] caller trust/RBAC matrix 完成。
- [x] `knowledge_docs` 全入口 exposure matrix 完成。
- [x] Trace/local retention/LangFuse payload matrix 完成。
- [x] 模型节点 outbound matrix 完成。
- [x] M27 → Phase 4 Eval migration matrix 完成。

### 合同与决策

- [x] G0/G1/G1-O 用户选择写入 notes。
- [x] 四轴真值表与 reason code registry 冻结。
- [x] trusted caller、Evidence/citation handoff、公开投影原则冻结。
- [x] 10 条 seed disposition 与 authority/ACL/outbound 冻结。
- [x] 首批 canonical Scenario matrix 与用途分集冻结。
- [x] D2 Eval family 决策和 closed-world 合同冻结。

### 验证与收工

- [x] 反向 `rg` 复查没有漏掉 consumer/exposure/outbound 入口。
- [x] 安全、状态、Eval 反例桌面推演通过。
- [x] 聚焦确定性 pytest 通过且无真实 provider 调用。
- [x] `git diff --check` 通过。
- [x] 按 `finish-module` 固化验证与决策素材。
- [x] 按 `finish-docs` 更新 state/changelog/dev-log。
- [ ] 用户人工检查后再执行 `accept-module`。
