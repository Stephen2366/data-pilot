# M30 可信知识原件、Catalog Prototype 与 Text2SQL 隔离计划

> 状态：计划已完成；模块名称、范围和 staged/active 边界不再要求用户重复确认。实施到 G2 检查点时，再基于 prototype 证据请用户选择运行时投影形态。
>
> 模块名称：**M30 可信知识原件、Catalog Prototype 与 Text2SQL 隔离**。
>
> 能力里程碑：本模块对应 Phase 4 **P1「可信知识、Evidence 与安全地基」的第一个能力切片**。P1 不是一个模块的同义词；M30 只闭环“知识从哪里来、怎样形成可验证的 staged catalog、Text2SQL 怎样不能旁路读取正文”。Evidence/citation/ACL/outbound 与正式安全发布留给 P1 的后续模块。
>
> 本轮边界：本文只制定 M30 开发计划。没有修改运行代码、数据库、正式 corpus、Eval 合同、默认模型、检索配置或公开响应。

## 1. 范围判断与拆分结论

### 1.1 M30 围绕的主要问题

M30 只回答一个完整问题：

> DataPilot 如何把政策、规则和指标说明从数据库草稿整理成唯一、可审查、可重建的知识事实源，同时证明任何 Text2SQL 路径都不能再绕过未来 Knowledge Tool 直接读取知识正文？

这个问题可以独立形成闭环：权威原件有明确身份，catalog prototype 能确定性构建和失败关闭，指标说明不会形成第二事实源，Text2SQL 的 Schema、检索、prompt 和 SQL Guard 都不再暴露 `knowledge_docs`，并能用无网络测试验收。

### 1.2 为什么不把完整 P1 塞进 M30

完整 P1 还包含 typed Evidence、citation validator、文档 ACL 双检、outbound decision、Trace/AgentResponse 安全投影和 active corpus 切换。它们共同回答的是另一个问题：

> 已治理的知识怎样在授权范围内进入回答，并能被安全引用和发布？

若与 M30 合并，实施会同时改知识正文、数据库/Schema、SQL 安全、运行时回答合同、Trace、Eval 和外发策略，用户很难分辨失败来自“知识源不可信”还是“回答链路不安全”，验收和复盘也会失焦。

因此建议把 P1 至少拆成两个模块：

1. **M30（本模块）**：可信知识原件、catalog prototype、Text2SQL 隔离和 G2 决策材料；产物保持 staged，不交给生成器。
2. **后续 P1 模块**：Evidence/citation/ACL/outbound、安全投影与 active corpus 发布；通过 G3 后再交给 P2 Knowledge Tool。

这不是为了目录或类的工程拆分，而是让每个模块各自有一个用户能讲清、能演示反例、能独立验收的能力闭环。

### 1.3 为什么 M30 不应再拆小

- 只做“把 seed 改成 Markdown”无法证明新文件是事实源，也无法阻断 SQL 旁路。
- 只做 `knowledge_docs` RBAC 删除会遗漏 Domain Schema、Schema Retrieval、prompt、旧说明和测试假设。
- 只做 manifest/catalog 会保留数据库草稿与 `metrics.yaml` 双事实源。
- 原件治理、catalog identity 和 Text2SQL 隔离共同定义“知识归谁管、从哪里读、谁不能读”，拆开后中间状态既难解释也不安全。

## 2. 已复核的当前事实

### 2.1 上一模块与已确认决策

- M29“Phase 4 入口盘点与合同冻结”已于 2026-08-13 验收；当前无阻塞项，Git 最近模块提交为 `bc79ad1 M29 Phase 4 入口盘点与合同冻结`。
- G0 已确认：保留 `/api/query`，后续用增量字段和兼容投影演进；M30 不实施响应变更。
- G1 已确认：治理现有 10 条 seed；政策/规则经审查后保留或重写，metric 说明由 `metrics.yaml` 派生或校验；首批不做长文 parent/child。
- G1-O 已确认：新增 Knowledge/RAG 远端用途默认 deny，本地 deterministic 先行；M30 不调用远程 embedding、rerank、generation、judge 或 LangFuse Cloud。
- M29 handoff 明确建议先完成“可信知识原件、catalog prototype 与 Text2SQL 隔离”，再做 Evidence/citation/ACL/outbound 与安全发布。

### 2.2 当前知识与数据库事实

- `domain_pack/kb_docs/` 只有 `.gitkeep`，没有权威知识原件。
- `scripts/seed_data.py::_KB_CONTENTS` 是 10 条作者草稿；`knowledge_docs` 物理表保存完整正文，但只有单角色 `audience_role`、简单 `status` 和时间戳，没有 revision、content identity、anchor、显式多角色 ACL、data classification 或 corpus identity。
- `sensitive_data_policy` 草稿暗示 admin 可看明文敏感字段，与当前“敏感字段优先，admin 也不能经自然语言 Text2SQL 明文直出”的确定性安全事实冲突。
- GMV、优惠券和行为漏斗三条 seed 与 `domain_pack/metrics.yaml` 存在双事实源风险；指标公式的唯一 authority 必须继续是 `metrics.yaml`。
- 数据库当前仍是 14 张物理表，`knowledge_docs` 有 10 行。M30 的 Text2SQL 隔离不等于未经 G2 就删除物理表、改 Alembic 历史或宣布数据库只剩 13 表。

### 2.3 当前 Text2SQL 暴露路径

- `load_domain_schema()` 会 glob `domain_pack/schema_desc/*.md`；因此 `knowledge_docs.md` 会进入 `DomainSchema.tables`。
- Schema document builder 会为 `knowledge_docs` 生成字段文档和中文 alias；当前 Schema corpus 为 195 条，hash 为 `8a8b6626...`。
- `engine/sql_guard/rbac.py` 把 `knowledge_docs` 放入 `ALL_TABLES`；admin/ops 继承全部表，customer_service/demo_user 也显式允许它。
- 当前语义预检会把“统计每篇知识库文档带来的订单金额”稳定拒绝为 `unsupported_relation`；M27 v3 canonical Scenario 依赖这个行为。隔离不能破坏该只读合同或改写历史 artifact。
- ORM、Alembic 和 `app.db.base` 的模型注册只是物理存储事实，不应自动等同于 Text2SQL 可查询 Schema。

### 2.4 当前测试与 Eval 事实

- M27 当前合同为 `m27-v3`，历史 artifact 全部只读；尚无正式长期真实 LLM 基线。
- 当前测试把 Schema corpus count 固定为 195，并检查 resolved runtime identity 的 195/hash；M30 隔离后必须重算并同步新 identity，不能继续沿用旧数值，也不能回写旧 artifact。
- 当前 `knowledge_doc_order_attribution_rejection` 属于 Text2SQL required contract/security 回归；它验证“不能把知识正文与订单伪造出可验证归因”，不代表知识表仍应暴露给 SQL。
- 合同核心可以用 fake/deterministic adapter 验证；本模块不需要真实向量库、真实模型或完整 LLM Eval 才能完成。

## 3. 当前问题

1. **权威源缺失**：知识正文只存在于 seed 常量和数据库投影，无法审查 revision、anchor、ACL 与来源。
2. **指标双写**：metric 文本可独立编辑，可能与 `metrics.yaml` 漂移。
3. **构建身份缺失**：没有稳定 document/revision/content/corpus/build identity，无法判断索引或 manifest 对应哪版知识。
4. **失败发布语义缺失**：没有“完整校验成功才产出 staged catalog”的失败关闭合同。
5. **SQL 旁路真实存在**：知识正文同时处于 Domain Schema、Schema Retrieval 和 RBAC 可见面。
6. **物理表与能力 Schema 混淆**：当前实现容易把“数据库里存在一张表”误当成“自然语言 SQL 可以查询它”。
7. **后续安全模块缺少稳定输入**：若 M30 不先固定 authority/catalog interface，Evidence、ACL、citation 和 Eval 会各自解析原件并重复发明身份。

## 4. 模块目标

M30 完成后必须达到：

1. 现有 10 条 seed 都有明确 disposition，并落实为经审查的政策/规则原件、由 `metrics.yaml` 派生的 metric 说明，或明确淘汰/拆分项。
2. 建立一个小 interface 的 catalog builder/loader：调用者只提交权威源集合并获得“成功的 staged catalog”或结构化校验失败；正文解析、归一化、hash、manifest 和 metric 派生藏在 implementation 内。
3. staged catalog 能稳定表达 document、revision、content identity、anchor、status、用途、data classification、`public`/`allowed_roles` 与 authority reference；相同输入和 build recipe 得到可比较 identity。
4. 构建失败时不产出可被误认成完整可用的 catalog，不推进任何 active identity，也不污染既有 Schema index。
5. `knowledge_docs` 不再出现在 Text2SQL 的 Domain Schema、Schema Retrieval、prompt 或任何角色的 SQL allowlist 中；物理表若暂留，只能是隔离的 legacy/derived storage，不是 SQL 能力面。
6. M27 v3 当前合同、historical artifact 与旧报告保持只读；当前 deterministic Text2SQL/security 回归继续通过。
7. 用 prototype 形成 G2 的事实证据并由用户决定运行时投影形态；M30 不在 prototype 前偷偷把某种数据库结构写成长期默认。

## 5. 优先级、范围与非目标

### 5.1 必须完成

#### A. 权威知识原件治理

- 按 M29 disposition 审查和重写短政策/规则，放入 `domain_pack/kb_docs/` 的权威源层。
- 退款总则与质量规则消除重复或冲突并建立显式关联；物流、发票、VIP、demo scope 和安全说明分别写清适用范围。
- `sensitive_data_policy` 必须服从当前确定性安全代码和 state 事实，不保留“admin 可经 Text2SQL 直出明文”的暗示。
- VIP 文档只保存资格规则，不把某个客户是否达标写成文档事实；实时资格留给未来 SQL + RAG Hybrid。
- GMV、优惠券计数/使用率、行为漏斗说明必须从对应 metric key 生成或做严格一致性校验，不能保留可独立编辑副本。
- 每个进入 staged catalog 的条目必须有稳定 key、authority、revision、anchor、status、data class、用途、`public`/`allowed_roles` 和内容 identity。

#### B. Catalog prototype 与构建身份

- 实现确定性的 source loader、validator 和 staged catalog build interface。
- 生成或返回可审计 manifest：能从 document revision 定位其原件与派生知识单元，并记录 corpus/build identity。
- 建立 duplicate key/revision/anchor、缺 authority、非法 ACL、未知 data class、metric key 不存在、内容 hash 漂移、inactive revision 误入等失败关闭测试。
- 明确 staged 与 active：M30 只形成经验证的 staged catalog，不接入生成器、不建立正式 Knowledge index、不宣布通过 G3。
- 形成 G2 对照：现有 `knowledge_docs` 升级为 derived runtime projection，或使用其他 source-backed runtime catalog，各自的迁移成本、回滚、安全与测试影响必须有 prototype 证据。

#### C. Text2SQL 全路径隔离

- 把 Text2SQL 的“可查询业务表集合”与 SQLAlchemy/Alembic 的“物理表集合”明确分开。
- 从 Domain Schema、Schema Retrieval field docs/table alias、prompt context 和所有角色 SQL policy 中移除 `knowledge_docs`。
- SQL Guard 对 admin、ops、customer_service、demo_user 直接查询 `knowledge_docs` 都必须拒绝；未知或手工构造的 planner 输出也不能绕过。
- 反向扫描 schema_desc、relations、few-shot、当前 catalog、测试、demo、Trace/error projection 和活跃文档；每个命中要么迁移、要么证明只是物理模型/只读历史。
- 保留 `knowledge_doc_order_attribution_rejection` 的确定性 `unsupported_relation` 产品语义；不能通过修改只读 M27 v3 Scenario 来掩盖回归。
- 重算 Schema corpus count/hash 和 runtime identity，更新当前事实；预计单纯移除 9 个 `knowledge_docs` 字段文档会使 195 下降到 186，但验收以实现后实际 builder 输出和 hash 为准，不在计划阶段冻结新 hash。

#### D. 验证、素材与状态同步

- 开工时建立 `docs/notes/m30-notes.md` implementation checklist，并持续记录内容取舍、G2 prototype、失败反例和验证快照。
- 增加 catalog contract、metric authority、构建失败关闭和 Text2SQL 反绕过测试。
- 运行聚焦测试、当前 M27 catalog 静态校验、确定性 Text2SQL/security 回归和全仓 pytest；不调用真实 provider。
- 收工按 `finish-module → finish-docs → 用户人工检查 → accept-module` 执行，并同步 AI_CONTEXT、CHANGELOG、database-current-state、schema-retrieval state 和必要 runbook 事实。

### 5.2 建议完成

- 为 catalog build 提供一个薄的只读检查入口或测试 helper，能输出 document/revision/count/hash/错误摘要，方便用户人工验收；是否做 CLI 由 implementation 的真实调用需求决定，不预先固定命令名。
- 生成便于 diff 的确定性 manifest 投影，使同一输入不会因文件遍历顺序或序列化顺序产生假漂移。
- 为 M29 首批 Scenario blueprint 建最小 authority fixture 映射，但不在 M30 提前实现完整 Phase 4 Eval runner/scorer。
- 在 notes 中保存一张“旧 seed → 新 authority/revision → staged catalog entry”的追踪表，方便后续学习复盘。

建议项不能替代必须项，也不能因为做了漂亮的报告就放宽 Text2SQL 隔离或构建失败关闭门禁。

### 5.3 条件触发

- **数据库 migration / ORM 大改**：只有 G2 选择升级 `knowledge_docs` 为正式 derived runtime projection，且 prototype 证明现有字段不足时才进入；执行前必须再次列明 migration、seed、回滚和兼容影响并获得用户确认。
- **物理删除 `knowledge_docs`**：只有 G2 明确选择不保留该投影、确认没有兼容消费者且回滚方案完整时才考虑；默认不在 M30 删除表或改写历史 migration。
- **active corpus 切换**：只有后续模块完成 ACL/outbound/Evidence/citation 安全合同并通过 G3 后触发；M30 禁止把 staged 伪装成 active。
- **长文切分、parent/child、向量索引、embedding、rerank**：只有真实 corpus 或 P2 dev failures 形成对应失败簇后再评估；首批短文不提前引入。
- **Phase 4 可运行 Eval family**：若 M30 的 catalog contract 已有必须机器验证的 closed-world identity，可增加最小静态 fixture/validator；完整 Scenario runner、retrieval/citation scorer 留给相应后续模块。

### 5.4 明确非目标

- 不实现 Knowledge Tool、retriever、Answer Composer、Evidence Gate、Citation Validator、Router、LangGraph、Hybrid 或 thread state。
- 不修改 `AgentResponse`、`docs_used` 或公开 `/api/query` 形状。
- 不让 staged catalog 进入任何生成器上下文。
- 不启用或选择 Knowledge 向量库、embedding、top-k、chunk 大小、reranker、模型、阈值或循环次数。
- 不启用 LangFuse Cloud，不发送 Document Evidence，不运行真实 Qwen/embedding/Eval Judge。
- 不修改 M27 v3 canonical Scenario、旧 artifact、旧报告或历史基线来制造通过。
- 不顺手修 M28/M29 之外的 Text2SQL 能力问题，不更新 README。

## 6. 本模块冻结的关键 interface 与不变量

这里冻结的是调用者和测试必须知道的语义，不提前固定类名、目录层级或每个文件的 schema。

### 6.1 Authority source interface

调用者必须能区分三类来源：

| 来源类型 | 唯一 authority | M30 处理 |
|---|---|---|
| 政策/客服规则/安全说明 | 经审查的 `domain_pack/kb_docs/` 原件 | 直接加载、校验、形成 revision/content identity |
| 指标说明 | `domain_pack/metrics.yaml` 的指定 metric key | 确定性派生或严格校验；禁止独立编辑公式/口径 |
| 实时业务事实 | 数据库 + Text2SQL Evidence | 不进入知识原件，不复制客户/订单/退款结果 |

每个 staged document 至少表达：稳定 document key、revision、authority reference、内容 identity、标题、知识类型、status/有效性、稳定 anchor、data classification、用途，以及 `public` 或显式 `allowed_roles`。缺任一必需事实必须失败关闭。

M30 不冻结“一 key 一文件”；短文可以按天然业务单元组织，只要 manifest 能稳定映射 document/revision/anchor。

### 6.2 Catalog build interface

外部 seam 应保持小而深：

- 输入：权威 source set 与可识别的 build recipe/config identity。
- 成功输出：一个完整、不可变语义的 staged catalog，加 corpus/build identity 和结构化摘要。
- 失败输出：有限、机器可判的 validation/build reason；不得返回“部分成功但看似可用”的 catalog。

implementation 内负责：文件发现、解析、归一化、metric 派生、anchor 构造、ACL/data class 校验、排序、hash、manifest 和诊断汇总。调用者不应分别编排这些步骤。

关键不变量：

- 同一规范化 authority 输入 + 同一 build recipe → 同一 content/corpus identity。
- 正文或影响语义的 metadata 变化 → identity 必须变化。
- 文件 mtime、遍历顺序、JSON/YAML 键顺序等非语义噪声不应单独改变 identity。
- duplicate identity、缺失 authority、未知 enum/role/purpose、metric 漂移、inactive 误入必须失败关闭。
- staged identity 与 active identity 分开；M30 没有 active 切换权。

### 6.3 Text2SQL schema seam

Text2SQL 的调用者只应看到“允许用于自然语言 SQL 的分析 Schema”，而不是数据库 metadata 的机械全集。

必须满足：

- `knowledge_docs` 物理表是否存在，不影响 Text2SQL schema 是否暴露它。
- planner、Schema Retrieval、prompt 和 SQL Guard 消费同一语义上的 queryable table universe，不能各维护一套相互漂移的名单。
- 防线至少包含 prompt 前不可见与 SQL Guard 最终拒绝；不能只靠 LLM“不去用”。
- 所有角色都不能通过 Text2SQL 查询知识正文；文档权限以后只走 Knowledge Tool 的 trusted caller + ACL seam。
- 旧历史 artifact 仍能按旧 runtime identity 解释；新运行记录新的 Schema corpus identity。

实现时应优先深化现有 DomainSchema/SQL policy seam；不要为每个消费者新增一层只转发名单的浅 module。

### 6.4 G2 prototype interface

G2 比较的不是文件名，而是三种落地方案：数据库 derived projection；source-backed catalog 并暂留 legacy 表；source-backed catalog 并立即退役 legacy 表。三者的完整做法、影响、适用条件和建议统一见第 11 节，避免在两处维护不一致的决策说明。

当前建议 **方案 B：source-backed catalog 并暂留隔离 legacy 表**。首批 corpus 很小、本地 deterministic 优先，这一方案能以更少 interface 先证明 authority、identity 和隔离，也避免为了尚未存在的检索调用者提前做数据库 migration。代价是未来多实例、增量发布或运营后台出现后可能需要重新评估持久化投影。

G2 必须在 prototype 证据和影响矩阵完成后由用户确认；确认前不得把建议写成 active runtime 默认。

## 7. 主要工作切片与执行顺序

### M30-A：建立实施 notes 与反向影响清单（必须先完成）

1. 创建 `docs/notes/m30-notes.md`，记录 implementation checklist、起始 commit/status 和本模块文件归属。
2. 反向扫描 seed、ORM/Alembic、schema_desc、DomainSchema、Schema Retrieval、RBAC、prompt、Trace/error、demo、当前 M27 catalog、测试和活跃 state 文档。
3. 每个 `knowledge_docs` 命中分类为：authority 草稿、physical/legacy projection、Text2SQL 暴露、当前消费者、测试合同、只读历史。
4. 将当前 195/hash、14 表/10 行、各角色 allowlist 和 canonical rejection 记录为迁移前快照。

完成门：没有未归类的当前可执行入口；历史报告噪声不被误当作运行时消费者。

### M30-B：治理权威原件与 metric 派生（必须完成）

1. 按 M29 disposition 重写政策/规则，处理冲突、重复、实时事实混入和安全口径漂移。
2. 为每个原件建立稳定 revision/anchor/authority/ACL/data class/use metadata。
3. 从 `metrics.yaml` 派生 GMV、coupon order count/usage rate、add-to-pay conversion 的可读说明；用反例证明改 seed 文本不能改变 metric authority。
4. 建立旧 seed → 新 authority 的可追踪映射；被淘汰的独立 metric 正文不得继续作为编辑入口。

完成门：所有 10 条 seed disposition 均已落实或有明确不纳入理由；不存在两个可独立编辑的同义 authority。

### M30-C：实现 catalog prototype 与失败关闭（必须完成）

1. 先写红灯合同测试，再实现最小 loader/builder/validator。
2. 构造稳定 document/revision/content/corpus/build identity 和 manifest 投影。
3. 覆盖成功、重复、缺字段、非法 ACL/data class、metric drift、inactive、内容变化、遍历顺序变化和中断/异常路径。
4. 确保失败时没有 partial catalog 被标为成功，也没有 active 切换或真实索引副作用。
5. 输出 G2 三方案的 prototype/影响证据；在需要改变数据库 runtime projection 前暂停并请求用户确认。

完成门：调用者通过一个小 interface 获得完整 catalog 或结构化失败；测试不需要知道内部解析步骤。

### M30-D：完成 Text2SQL 隔离迁移（必须完成）

1. 明确 queryable schema 与 physical metadata 的 seam，移除 `knowledge_docs` 的 Text2SQL Schema 描述/alias。
2. 收紧所有角色 SQL policy，并增加手工 SQL、planner 输出和常见角色的反绕过测试。
3. 证明 Schema Retrieval corpus、prompt context 和 Trace 中不出现知识表字段/正文。
4. 保留 canonical `unsupported_relation` 预检行为，执行 catalog 静态校验。
5. 重算并记录新的 Schema docs count/hash/runtime identity；不复用旧脏 Milvus collection，不运行真实 Milvus。

完成门：任何角色和任何 Text2SQL 路径都无法查询 `knowledge_docs`；物理表存在也不能绕过。

### M30-E：验证、G2 决策与收工（必须最后完成）

1. 运行聚焦 catalog/isolation/security/M27 deterministic 测试。
2. 运行全仓 pytest 与 `git diff --check`；按 Windows 规则使用新的 `.agent_work/temp/<name>` basetemp。
3. 做删除测试：删除 catalog module 后复杂度会重新散落到 source、metric、manifest 和后续消费者，证明它有深度；删除纯转发层不应影响能力，说明不应保留浅层。
4. 向用户提交 G2 证据、推荐和影响，记录最终选择；若选择触发 migration，按条件分支实施并补齐验证。
5. 按项目流程完成 notes、state、changelog/dev-log 和最终验收准备。

完成门：必须项全绿、G2 有用户选择、staged/active 没有混淆、后续安全发布模块无需重新猜 authority/catalog 语义。

## 8. 依赖与计划交付物

### 8.1 依赖

- M29 已验收及其 G0/G1/G1-O 决策。
- `docs/phase4-roadmap.md` 第 4 节不变量与 P1 边界。
- `domain_pack/metrics.yaml`、当前政策 seed、SQL Guard、DomainSchema、Schema Retrieval 和 M27 v3 只读合同。
- 用户在 G2 prototype 后对运行时投影形态的确认。
- 若条件触发数据库 migration，还依赖当前 Alembic head、MySQL/SQLite 兼容和明确回滚检查。

### 8.2 计划交付物

- `docs/notes/m30-plan.md`：本计划。
- `docs/notes/m30-notes.md`：实施清单、内容 disposition、G2 证据、验证快照与收工素材。
- 经审查的知识原件与 metric-derived staged entries；具体文件组织由实现时按天然业务单元决定。
- 一个确定性的 catalog loader/builder/validator 深 module 和 manifest/identity 投影；不提前冻结包名或类名。
- Text2SQL Schema/RBAC/Schema Retrieval 隔离改动及反绕过测试。
- 新 Schema corpus count/hash 和相关 runtime/state 同步。
- G2 决策记录及 P1 后续模块 handoff。
- 收工阶段对 `docs/state/AI_CONTEXT.md`、`AI_CONTEXT_CHANGELOG.md`、`database-current-state.md`、`schema-retrieval-milvus-embedding.md`、必要 runbook 与 `docs/dev-log.md` 的事实更新。

## 9. 验证方式

### 9.1 Catalog 合同测试（必须）

- 相同 authority 输入、不同遍历/序列化顺序得到相同 identity。
- 正文、revision、anchor、ACL、data class 或 metric authority 变化会改变相应 identity。
- duplicate key/revision/anchor、缺 authority、非法 status/role/data class/use、未知 metric key、metric drift 均失败关闭。
- inactive/revoked revision 不进入 staged usable set，但保留必要 identity/audit reference。
- build 中途异常不返回 partial success，不推进 active identity。
- metric entry 的 formula/filter/default time field 可追溯到 `metrics.yaml`，不存在独立可编辑副本。

### 9.2 Text2SQL 隔离测试（必须）

- `load_domain_schema()` 的 queryable tables 不含 `knowledge_docs`。
- `build_schema_documents()` 不再产生 `field:knowledge_docs.*`，关键词/向量文本也不含其正文能力描述。
- admin、ops、customer_service、demo_user 查询 `knowledge_docs` 均被 SQL Guard 拒绝。
- planner 或测试直接提交 `SELECT title, content FROM knowledge_docs` 不能绕过。
- prompt/Schema Context/Trace 的允许投影不出现该表字段或正文。
- “统计每篇知识库文档带来的订单金额”仍稳定得到 `unsupported_relation`，不是由 LLM 偶然拒绝。

### 9.3 Identity 与兼容验证（必须）

- 记录迁移后 Schema docs count/hash，并证明 resolved runtime identity 使用新值。
- 当前 M27 v3 catalog 加载与静态 domain-schema validation 通过；不修改 Scenario/hash 来适配实现。
- 历史 M27 artifact/review 仍只读可解析，不回填新字段、不重算旧结果。
- 若保留数据库 legacy projection，验证它不进入 Text2SQL queryable universe；若 G2 触发 migration，再补 Alembic upgrade/downgrade/check 和 seed 验证。

### 9.4 回归层级（必须按顺序）

1. catalog/authority unit tests；
2. SQL Guard、DomainSchema、Schema Retrieval、M27 foundation/catalog 聚焦测试；
3. legacy API/Text2SQL deterministic 测试；
4. 全仓 pytest；
5. `git diff --check` 和反向 `rg` 清单复核。

精确测试文件和 basetemp 名在实施时根据实际改动确定，并记录到 M30 notes。真实 LLM Eval、Milvus、embedding 和 LangFuse Cloud 不属于 M30 自动验收；用户若另行明确授权，只能按 runbook 精确执行一次，不扩大范围。

## 10. 验收标准

M30 只有同时满足以下条件才算完成：

1. **必须完成**：10 条 seed disposition 全部落实；政策/规则 authority 与 metric authority 单一且可追溯。
2. **必须完成**：每个 staged document/revision 都具备稳定 identity、anchor、status、ACL/data class/use 和 authority reference；非法或不完整输入失败关闭。
3. **必须完成**：相同输入/build recipe 可重现 catalog identity；语义内容变化可检测；非语义顺序噪声不造成假漂移。
4. **必须完成**：M30 产物明确是 staged，不进入生成器、不建立 active Knowledge index、不宣称 G3 已通过。
5. **必须完成**：所有角色的 Text2SQL Schema、Schema Retrieval、prompt 和 SQL Guard 都不再暴露 `knowledge_docs`；手工 SQL 与 planner 输出反绕过测试通过。
6. **必须完成**：M27 v3 的 `unsupported_relation` 确定性拒绝、catalog 静态校验及核心 deterministic 回归通过；历史 artifact 未改写。
7. **必须完成**：新的 Schema docs count/hash/runtime identity 已记录并同步当前 state；旧 195/hash 明确变成迁移前事实，不被静默复用。
8. **必须完成**：G2 prototype 对比、推荐、用户选择和影响记录完整；未确认的数据库/运行时默认没有被偷偷固定。
9. **必须完成**：核心合同测试不依赖真实向量库、远程模型或 Cloud；全仓测试无新增失败。
10. **建议完成**：提供便于用户人工查看的 catalog 摘要/diff 入口；若未做，notes 说明没有真实调用需求的理由。
11. **条件触发**：若 G2 引入 migration/seed 变化，Alembic、MySQL/SQLite seed、回滚、数据库事实和相关测试必须额外通过；否则该条件不进入 M30 分母。
12. **条件触发**：若实现意外需要 active 发布、Evidence/citation 或远程调用，必须暂停并重新评估模块范围，不能用追加测试掩盖越界。

## 11. 决策门

### G2：运行时投影形态（M30 内必须决策）

G2 只决定“后续运行时从哪里读取已验证 catalog”，不改变以下共同前提：权威正文仍在 domain pack；`metrics.yaml` 仍是指标 authority；`knowledge_docs` 不得进入 Text2SQL；M30 仍只产出 staged catalog，不通过 G3。

#### 方案 A：升级数据库 `knowledge_docs` 为正式 derived runtime projection

做法：权威原件经 builder 校验后写入升级后的数据库表，后续 Knowledge Tool 从数据库 catalog 读取；数据库只接受构建流程写入，不允许人工编辑成第二 authority。

影响：

- 必须新增 Alembic migration，补 revision、content identity、anchor、ACL、data class、用途和 corpus/build identity 等能力。
- seed、ORM、SQLite/MySQL fixture、数据库 state、回滚和发布顺序都要同步修改，M30 的条件验证明显增加。
- 更容易支持未来的多实例共享、后台查询和运营工具，但必须额外证明数据库投影不会被手工改写或被 Text2SQL 绕过。
- 当前只有很小的本地短文 corpus，现阶段会先承担较多持久化和迁移复杂度，尚无真实调用者证明这些成本必要。

适用条件：近期明确需要多实例共享 catalog、数据库运营查询或在线编辑/发布工作流。

#### 方案 B：source-backed runtime catalog，暂留隔离的 legacy 物理表（推荐）

做法：运行时通过同一个 builder/loader 从权威原件和 manifest 得到只读 immutable catalog；`knowledge_docs` 物理表暂时保留，但不再是 authority、runtime catalog 或 Text2SQL 表，也不新增字段。

影响：

- 不需要在 M30 做数据库 migration，能先集中验证 authority、identity、失败关闭和 SQL 隔离。
- 未来 Knowledge Tool、测试和 catalog inspect 都复用同一个小 interface，首批本地 corpus 的心智模型最简单。
- 仓库中会暂时保留一张 legacy 表；必须在 state、注释和测试中明确其隔离状态，避免后来的人误以为它仍是知识入口。
- 将来出现多实例、在线编辑或大规模增量发布需求时，可能需要再引入数据库/对象存储投影；届时仍可在同一 catalog interface 下新增 adapter。

适用条件：当前 Phase 4 的本地 deterministic 首版、短 corpus、尚无运营后台和多实例一致性需求。

#### 方案 C：source-backed runtime catalog，并在 M30 立即退役物理表

做法：采用与方案 B 相同的 source-backed catalog，但同时新增 migration 删除 `knowledge_docs`，移除 ORM、seed 和所有数据库兼容入口。

影响：

- 事实模型最干净，不再保留容易误解的 legacy 表，也彻底消除数据库正文副本。
- 会扩大 M30 的数据库改动范围，需要 upgrade/downgrade、seed、14 表事实、历史兼容和所有相关测试一起迁移。
- 物理删除的回滚成本高于“先隔离、后退役”；当前没有证据证明保留一张不可查询的 legacy 表会阻塞 P1/P2。
- 可能让用户把本模块重点从“可信知识和隔离”转移到数据库清理，学习与验收收益偏低。

适用条件：prototype 发现 legacy 表即使隔离后仍会被活跃消费者使用或造成无法接受的双事实源风险。

#### 建议、确认时点与默认处理

- **我的建议：方案 B。** 它先用最少 interface 和最少迁移完成本模块的核心学习闭环，也保留以后在同一 seam 下新增数据库 adapter 的空间。
- **为什么不建议 A**：当前没有多实例、后台或在线发布需求，先做数据库 catalog 会让 implementation 比真实能力更复杂。
- **为什么不建议 C**：隔离已经能关闭 SQL 旁路，立即删表带来的迁移风险大于当前收益。
- **确认时点**：完成 source-backed prototype、legacy consumer matrix 和 Text2SQL 隔离测试后，执行任何数据库 migration/删除前。
- **用户确认前的默认处理**：只推进三种方案共有的原件治理、catalog interface 和 Text2SQL 隔离；不升级也不删除物理表。
- **重开条件**：多实例一致性、在线编辑、增量发布、运营查询、回滚历史或 corpus 规模证明方案 B 不够。

### G3：正式 corpus 发布（M30 不通过）

M30 只准备 G3 输入。必须等后续模块实现 ACL/outbound/Evidence/citation、安全投影和 active 切换，并完成内容最终人工审查后，才能将 staged catalog 设为 P2 默认 corpus。

### D30-1：Schema identity 迁移

- 新 count/hash 由实现后真实 builder 输出产生，不在 plan 中硬编码。
- 当前运行和 state 改用新 identity；旧 M27 artifact 继续保留旧 identity。
- 任何复用 Milvus collection 的想法都必须因 corpus hash 变化而失败；M30 不创建替代 collection。

## 12. 风险与控制

| 风险 | 影响 | 控制 |
|---|---|---|
| 只把 seed 复制成 Markdown | 形成第三份正文，authority 更乱 | 删除独立编辑入口；用追踪表和 content identity 证明单向派生 |
| 把 manifest 当成权威正文 | 派生物反客为主 | manifest 只指回 authority/revision/anchor，可删除重建 |
| catalog prototype 过度平台化 | M30 被 watcher、后台、增量发布拖大 | 只做显式 build/validate；不做常驻 watch、管理后台或多租户平台 |
| 只删 RBAC 一处 | Schema/prompt 仍泄露正文 | queryable schema + prompt invisibility + SQL Guard deny + 反向扫描多层验证 |
| 删除 schema_desc 后误伤 M27 拒绝题 | required contract 回归 | 保留确定性 semantic precheck，并定点测试 canonical Scenario |
| 把物理 14 表改写成 13 表事实 | ORM/Alembic 与文档失真 | 区分 physical tables 与 Text2SQL queryable tables；G2 前不删除物理表 |
| 新 hash 仍复用旧 Milvus collection | 新 schema 映射旧向量 | 记录新 identity；hash mismatch 必须拒绝，M30 不跑真实 Milvus |
| metric 说明手工润色改变公式 | 指标双事实源复发 | 公式/filter/time field 从 `metrics.yaml` 派生并测试；可读模板不拥有口径 |
| staged 被误当 active | 未完成 ACL/outbound 就进入回答 | 类型/状态/文档明确区分；M30 不提供生成器 adapter |
| G2 被实现细节偷偷决定 | 后续迁移成本失控 | prototype 后显式提交选项、证据、影响并等用户确认 |
| 为未来调用者预建大量 adapter | interface 变浅、维护面扩大 | 一项变化一个真实 seam；没有第二 adapter/调用者就不抽象 |

## 13. 参考源码定点复核记录

### 13.1 本模块问题与证据

- DataPilot 当前缺的是权威原件、稳定 catalog identity、失败关闭和 Text2SQL 隔离，不是检索算法。
- 需要借鉴“source 与 derived index 分离”“成功后才推进观察状态”“替换失败边界”，但不能把参考实现的局部保证夸大成原子发布。

### 13.2 已复核入口

- `WREN-INDEX`：`WrenAI/core/wren/src/wren/memory/index_backend.py :: MemoryIndex.reset / LanceDBIndex.rebuild`
- `WREN-WATCH`：`WrenAI/core/wren/src/wren/memory/watch.py :: compute_fingerprint / poll_once`
- `DATAAGENT-REPLACE`：`DataAgent/.../AgentVectorStoreServiceImpl.java :: replaceDocumentsByMetadata`

### 13.3 借鉴内容

- WrenAI 明确 Markdown 是 source、LanceDB 是 derived index；`reset()` 删除派生索引而不动原件。这支持 M30 的 authority/catalog 分离。
- WrenAI `poll_once()` 只在 reindex callback 成功后推进 watcher fingerprint。这支持“失败不推进已观察状态”的纪律。
- DataAgent replacement 先增加 replacement documents，再删除旧文档；异常时尝试清理新文档。这提供替换顺序和 cleanup 的局部反例/参考。

### 13.4 DataPilot 适配

- 使用内容参与的稳定 SHA-256 identity，而不是只依赖 path/size/mtime；mtime fingerprint 只能用于发现变化，不能成为 corpus identity。
- M30 使用显式、可测试的 build/validate，不引入常驻 watcher。
- staged catalog build 必须整体校验成功；active switch 留给通过 G3 的后续模块。
- Text2SQL 隔离是 DataPilot 自身的安全合同，不能从参考项目的 collection/filter 设计推导。

### 13.5 明确不照搬

- 不把 WrenAI 的 mtime fingerprint 当内容版本、revision 或原子切换保证。
- 不把 LanceDB upsert/rebuild 当成删除旧条目、完整回滚或 active corpus 切换的证明。
- 不把 DataAgent 的“先加后删 + best-effort cleanup”描述成事务式替换；新旧并存窗口、删除失败和 cleanup 失败都必须在 DataPilot 设计中如实说明。
- 不引入 WrenAI 完整 memory backend、watch 服务或 DataAgent 的 Java/Spring 平台结构。
- 不在 M30 照搬任何向量库参数、threshold、chunk 或 metadata schema。

### 13.6 验证方式

- 用 deterministic fake 重现 build success、validation failure、中途异常和 identity drift。
- 用 deletion/rebuild 测试证明派生 manifest/catalog 可从 authority 重建且不修改原件。
- 用明确的 staged/active assertion 证明 M30 没有把局部 replacement 误当安全发布。
- 用 Text2SQL 反绕过测试补足参考项目没有覆盖的 DataPilot 安全 seam。

## 14. 遗留与后续

- P1 后续模块实现 typed Evidence、AuthorizationDecision、OutboundDecision、Citation Validator、Trace/AgentResponse 安全投影和 active corpus 切换，并完成 G3。
- P2 在 P1/G3 后实现确定性 Knowledge Tool 与薄 RAG 垂直切片；检索策略由 M30 corpus 和 P2 dev failures 决定。
- Phase 4 可运行 Eval family、RAG retrieval/citation/answer assertions 由首次真正消费 staged catalog 的模块滚动冻结；M30 只提供 authority/catalog deterministic fixture。
- 长文 parent/child、向量索引、rerank、远程 generation、Agentic RAG Subgraph 都没有获得 M30 入场证据。
- 物理 `knowledge_docs` 的最终迁移/删除、运营后台、多实例发布和在线增量同步由 G2 及未来真实需求决定。

## 15. 用户决策说明

### 15.1 开工前无需再次确认

以下事项已由 roadmap、最新 state 和 M29 决策确定，不再询问用户：

- 模块号、模块名称和本模块范围；
- M30 只形成 staged catalog，不接入生成器、不通过 G3；
- Evidence/citation/ACL/outbound 与 active 发布属于后续 P1 模块；
- 按 M29 disposition 治理现有 10 条 seed，metric 说明由 `metrics.yaml` 派生或校验；
- 新 Knowledge/RAG 远端用途继续默认 deny；
- 新政策正文可以在 M30 形成 staged revision，但正式进入 active corpus 前仍需在 G3 做最终人工内容审查。

### 15.2 实施中需要用户确认：G2

实施完成 source-backed prototype 和影响矩阵后，向用户提交第 11 节的三项完整选项：

1. 方案 A：升级数据库表为正式 derived runtime projection；
2. 方案 B：使用 source-backed runtime catalog，暂留隔离 legacy 表；
3. 方案 C：使用 source-backed runtime catalog，并立即 migration 删除 legacy 表。

提交时必须附上当时的真实代码影响、测试结果、migration 范围和未解决风险，不能只问“选 A 还是 B”。当前建议为方案 B；在用户确认前不做数据库升级或删除。

### 15.3 新冲突的处理

若实施调查发现会改变 authority、catalog interface、Text2SQL 隔离语义或 P1/P2 路线的新冲突，必须按“依据 → 选项 → 每项影响 → 建议 → 需要确认的时点”向用户说明并暂停对应分支；普通 implementation 细节由模块自行决定，不转嫁给用户。

## 16. Implementation Checklist（实施时使用）

### 开工

- [ ] 重新读取最新 AI_CONTEXT 及必读 state，确认 M29 仍已验收且无新增冲突。
- [ ] 检查 `git status --short`，记录起始 commit 和既有改动归属。
- [ ] 创建 `docs/notes/m30-notes.md`，写 implementation checklist。
- [ ] 复核 G1/G1-O 决策；模块名称和范围无需用户重复确认。

### 必须完成

- [ ] 建立完整 exposure/consumer matrix 和迁移前 identity 快照。
- [ ] 治理政策/规则原件，落实 10 条 seed disposition。
- [ ] 实现 metric-derived 说明和 authority 一致性测试。
- [ ] 先写 catalog contract 红灯测试，再实现 loader/builder/validator。
- [ ] 覆盖 identity、manifest、失败关闭与 staged/active 分离。
- [ ] 完成 Text2SQL DomainSchema/Schema Retrieval/RBAC/prompt 全路径隔离。
- [ ] 保留 canonical `unsupported_relation` 拒绝语义。
- [ ] 重算 Schema count/hash/runtime identity 并同步当前事实。
- [ ] 形成 G2 prototype 对照并取得用户最终确认。

### 建议完成

- [ ] 提供最小 catalog inspect/diff 入口或说明不需要的理由。
- [ ] 保存旧 seed → authority/revision → staged entry 追踪表。

### 条件触发

- [ ] 若 G2 选择数据库 projection，先确认 migration/seed/回滚范围，再实施并验证。
- [ ] 若发现必须接入生成器、Evidence/citation 或远程节点，暂停并重新规划，不扩大 M30。

### 验证与收工

- [ ] catalog/authority 聚焦测试通过。
- [ ] SQL Guard/DomainSchema/Schema Retrieval/M27 deterministic 回归通过。
- [ ] 全仓 pytest 通过，无真实 provider 调用。
- [ ] `git diff --check` 与反向清单复核通过。
- [ ] 使用 `finish-module` 固化 notes 和验证快照。
- [ ] 使用 `finish-docs` 更新 state/changelog/dev-log。
- [ ] 用户人工检查后运行 `accept-module`。
