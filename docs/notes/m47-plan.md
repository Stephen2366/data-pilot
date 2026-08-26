# M47 Phase 4B B5 Durable Task State 开发计划

> 能力里程碑：Phase 4B B5；本模块完整承担 durable task state，不提前实现 M48/B6 的 Context Compact
>
> 主要问题：当前 Agent Task 只保存在单进程字典中，无法在进程重启、多 worker、并发旧版本或重复请求下安全恢复

## 1. 模块定义与范围判断

M46/B4 已验收通过，M43 的 TaskState/TaskDelta/turn boundary 与 M44 的 Decision Loop turn boundary 已稳定，满足 roadmap 对 B5 的强制开工依赖。M47 完整对应 B5；模块内部按 M47-A～M47-G 形成一个可独立验收的纵向闭环，不再把 CAS、多 worker、TTL/clear 或清理留给额外模块。

本模块不是“给现有字典换一个数据库”。完成后，用户能够演示：在同一任务完成一个 turn 后停止进程，由另一个进程或 worker 从安全任务边界恢复并继续；两个 worker 同时提交同一版本时只有一个获得执行权；重复/旧版本请求不会再次调用 Tool；owner、tenant、active role、TTL、clear、不兼容 schema 和存储故障都按稳定的非泄露语义停止。系统仍不恢复 LangGraph 节点栈、RAG Subgraph program counter、模型 Thought 或未完成的中间执行。

M47 完成后可以宣称 B5 durable task state 完成，但不能宣称 B6 Context Compact 或整个 Phase 4B 完成。M48/B6 必须直接消费本模块的 durable typed event ledger 和 checkpoint identity。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| `TaskBoundary` 用进程内 `dict + RLock` 保存 `_Checkpoint`，runtime 明示 `process_local_non_durable` | 重启后 task 消失，多 worker 各有独立副本；锁内原子性不能证明数据库 CAS | `engine/phase4b/task_boundary.py::TaskBoundary` |
| `claim()` 在应用内先检查 status/TTL/version，再写 `claimed`；`commit()` 也只检查本进程对象 | 现有实现无法抵抗两个进程同时 claim，也无法用存储层受影响行数证明唯一胜者 | `engine/phase4b/task_boundary.py::claim/commit` |
| claim 成功后若进程崩溃，checkpoint 会保持 `claimed`；当前状态检查先于 TTL 检查 | 现有失败语义不完整；若简单“超时重跑”又可能重复 Tool 调用 | `engine/phase4b/task_boundary.py::_Checkpoint/claim` |
| owner hash 绑定 caller/tenant，但 checkpoint 未独立保存 tenant、active SQL role 或恢复时的授权快照 | 同一 caller 改 role 后仍可继续；无法直接证明 roadmap 要求的 owner/tenant/role 复核 | `TaskBoundary.owner_ref`、`engine/harness/caller.py::CallerResolution` |
| TaskState v2 只提供 `safe_projection()`，没有版本化反序列化/迁移入口 | JSON 落库后可能宽松接受缺字段、未知字段或不兼容 Evidence requirement，造成恢复漂移 | `engine/phase4b/task_runtime.py::TaskState/TaskEvidence` |
| `run_task_turn()` 依赖具体 `TaskBoundary` 类型，应用启动固定实例化内存实现 | durable adapter 无法在不扩散条件分支的情况下替换；测试也无法系统验证 adapter 等价 | `engine/phase4b/task_turn.py`、`app/main.py`、`app/api/query.py` |
| TaskState 保存 last action/budget/termination，但 task boundary 没有可持久消费的 typed turn/event ledger | B6 无法基于 durable ledger 生成可追溯 Compact；仅靠 Trace 不能作为恢复 authority | `TaskState.safe_projection()`、`TaskLifecycleFact`、roadmap §4.1/§12 |
| 项目已有 MySQL + SQLAlchemy + Alembic，Redis 只有未使用的 URL 配置且未声明客户端依赖 | MySQL 可复用现有事务/迁移底座；Redis 会新增服务、依赖和持久化配置，不能因有一个 URL 就视为现成能力 | `app/db/session.py`、`alembic/env.py`、`pyproject.toml`、`app/core/config.py` |
| M46 已冻结 Pipeline 默认、Subgraph experimental，且 handoff 明确只在 task boundary 恢复 | B5 不能借持久化重开 B4 质量优化，也不能保存/恢复 RAG 子图执行位置 | `docs/notes/m46-notes.md::Handoff`、`AI_CONTEXT.md` |

## 3. 参考源码定点复核

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 如何把 saver 作为可替换依赖接入运行时 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java::mysqlCheckpointSaver/memoryCheckpointSaver/nl2sqlGraphCompileConfig` | MySQL/Memory saver 通过同一编译依赖注入；serializer 与 graph state 对齐 | 抽出 adapter-neutral task boundary protocol，由应用组装 durable/in-memory adapter；serializer 绑定 DataPilot TaskState schema identity | Java/Spring 结构、自动建 saver 表、完整 Graph state serialization、看到 MySQL saver 就宣称 owner/TTL/CAS 已闭合 |
| saver 在恢复与清理通路中实际保证什么 | `DataAgent/data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/GraphServiceImpl.java::handleHumanFeedback/isAwaitingHumanFeedback/releaseCheckpoint` | 恢复通过同一 thread config 读取 checkpoint，非等待态会 release | DataPilot 只从已提交 task boundary 重进 Decision Loop；clear/expiry/purge 使用独立生命周期合同 | 恢复任意节点栈、把 raw thread id 当 owner、best-effort `release()` 警告后继续冒充清理成功 |
| “可暂停”为什么不等于 durable | `agentic-rag-for-dummies/project/rag_agent/graph.py::create_agent_graph` | `InMemorySaver + interrupt_before` 展示 checkpointer/interrupt 接线位置 | 作为反例保留：M47 durable 由数据库 task boundary 提供，不使用 LangGraph saver 承担 B5 | 进程内 saver、MessagesState 全历史、clarification 节点栈恢复、LLM 自由 summary |
| 如何让多进程竞争由存储层决定 | MySQL 官方文档 [InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)、[Locks Set by Different SQL Statements](https://dev.mysql.com/doc/refman/8.4/en/innodb-locks-set.html)；SQLAlchemy 2.0 [Transactions and Connection Management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)、[Getting Affected Row Count from UPDATE/DELETE](https://docs.sqlalchemy.org/en/20/tutorial/data_update.html#getting-affected-row-count-from-update-delete) | 短事务、唯一索引、条件 `UPDATE`/锁定读、`rowcount == 1` 可形成 CAS 证据；死锁仍需作为明确故障处理 | claim/commit/clear 使用单条条件更新或同事务锁定更新；switch 固定锁顺序并原子退休旧 task/创建新 task；不在应用里先读后写模拟 CAS | 长事务包住 LLM/Tool、表锁、`SKIP LOCKED` 的不一致视图、把 ORM 内存 version 当跨 worker 证明、无界自动重试死锁 |
| JSON checkpoint 如何保持 schema 边界 | MySQL 官方文档 [The JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)、[JSON Schema Validation Functions](https://dev.mysql.com/doc/refman/8.4/en/json-validation-functions.html) | 数据库可保证 JSON 形状合法，应用仍需版本化 schema validator | 持久 payload 先经过 closed-world codec；恢复时核对 schema family/version、canonical identity 和必需字段 | 把任意 dict 原样存取、依赖数据库 JSON 合法性替代业务 schema、在 JSON 中保存 rows/正文/answer/Thought |

定点复核结论：DataAgent 证明了 saver 可作为接线 seam，却没有 owner、tenant、active role、TTL、CAS、重复提交、隐私和清理的正向保证；ARAG 只证明进程内 interrupt。M47 的 durability 证据必须来自 DataPilot 自身的存储层条件更新、两个独立 adapter/session、真实重启链路和安全 Scenario，不能由参考项目名称代替。

规模与代表性边界：B5 的核心规模不是 corpus 文档数，而是 checkpoint 状态大小、并发竞争和生命周期。测试至少覆盖最小状态、带 SQL/Document EvidenceRef、B4 child termination 安全摘要、连续多 turn ledger 和 schema 不兼容；不需要重跑 M46 external 60 题或解封 reserve来证明持久化。

## 4. 目标、优先级与非目标

### 模块完成状态

M47 完成后，agent task family 具有内容绑定的 durable runtime identity、版本化 TaskState codec、最小持久 checkpoint 与 typed event ledger、存储层 CAS claim/commit/switch/clear/expiry、重启和多 worker 恢复、保守故障降级、清理/审计策略，以及 additive Agent Scenario v5。in-memory adapter 继续服务快速测试并通过同一语义套件，但明确不具备 durable 身份。

### 必须完成

- M47 完整交付 B5；restart、multi-worker、CAS、duplicate/version、TTL、clear、incompatible schema 和 storage unavailable 均是硬门。
- 抽出稳定 task boundary protocol；业务 turn/API 不按后端分叉。
- 建立 closed-world TaskState codec；未知/缺失/不兼容 schema fail closed，不做在线猜测迁移。
- durable checkpoint 只保存恢复必需的 TaskState、安全 EvidenceRef/validity、last budget/termination、active role/tenant binding 和必要 typed event；不保存 rows、Document 正文、完整答案、Prompt、凭据或 program counter。
- claim/commit/clear/switch/expiry 必须由存储层条件更新/事务保证；同版本只有一个 claim 成功。
- 已提交边界可跨进程恢复；in-flight 崩溃不自动重放 Tool，不伪装 exactly-once 外部副作用。
- 恢复前重新验证 caller/tenant/active role，并在执行/Composer 前沿用现有 Evidence freshness/revision/purpose/ACL 重核。
- API、Trace、Eval 从同一 checkpoint lifecycle/state/event 事实投影；raw task id 和存储 payload 不进入 Trace。
- 新增 Alembic upgrade/downgrade、ORM metadata、SQLite deterministic contract 测试和真实 MySQL Probe。
- M42 v1、M43 v2、M44 v3、M46 v4 artifact/validator 保持只读；legacy `m37-thread-v2` 不迁移。

### 建议完成

- 提供受限 maintenance 入口，报告 active/claimed/expired/tombstone 数量并执行 bounded purge；不暴露 task 内容。
- 对 checkpoint/event payload 大小设置显式上限和拒绝 reason，避免 durable state 退化为长期大对象。

### 条件触发

- **触发条件**：真实 MySQL 证明单行条件更新无法满足 switch 原子性或出现稳定死锁失败簇。
- **允许动作**：在同一 MySQL 方案内改为短 `SELECT ... FOR UPDATE` 事务、固定锁顺序，并增加一次最小受影响 Probe。
- **未触发时**：不引入分布式锁、Redis Lua、消息队列或自动死锁重试平台。

- **触发条件**：发现现有 TaskState v2 的合法历史值无法由 closed-world codec 无损恢复。
- **允许动作**：新增显式、单向、离线可验证的 schema upgrader，并进入 G47-3 用户决策门。
- **未触发时**：v2 直接作为首个 durable state schema；不为未来版本预造通用 migration framework。

### 明确非目标

- 不恢复 LangGraph/RAG Subgraph program counter、节点栈、Tool 中间态或未提交 turn。
- 不承诺任意外部 Tool 的 exactly-once；本模块通过 claim fencing 和拒绝自动重放避免重复执行。
- 不建设跨任务长期记忆、用户画像、永久聊天历史或生产 SSO/OAuth/JWT。
- 不实现 M48/B6 Compact builder、compact trigger 或 compact 行为等价；只保存其所需的最小 durable ledger/compact reference seam。
- 不重开 M46 Subgraph 质量、默认化、reserve 或 historical Eval；Pipeline/Subgraph rollout 保持不变。
- 不改变默认模型、embedding、Knowledge release、RAG backend、SQL 指标、seed/oracle 或业务表结构。

## 5. 关键合同

### C1：Adapter-neutral Task Boundary 合同

- 输入：可信 caller context、active role、task id/expected version、typed TaskState 和 typed boundary event。
- 成功输出：TaskProjection、TaskLifecycleFact、runtime identity；in-memory/durable 公开语义等价。
- 失败语义：`task_unavailable`、`task_not_active`、`task_version_conflict`、`task_expired`、`task_schema_incompatible`、`task_storage_unavailable` 等稳定 closed-world reason；拒绝路径零深 Tool。
- 必须保持的不变量：endpoint 不访问后端表/dict；raw task id 仅合法 owner 响应可见；legacy manager 独立；runtime 明示 backend/durability/schema/lifecycle identity。
- 本模块不冻结的实现细节：protocol/adapter 的最终类名和文件拆分。

### C2：Durable Schema 与最小数据合同

- 输入：TaskState v2、安全 EvidenceRef/validity、owner/tenant/active role binding、version/status/TTL、last budget/termination、typed event 和未来 compact reference 空 seam。
- 成功输出：可 canonical round-trip、带 schema identity/fingerprint 的 checkpoint snapshot 与按 task/version 有序的最小 event ledger。
- 失败语义：缺字段、未知字段、identity 不符、payload 超限或不兼容 version 均拒绝恢复；不宽松补默认。
- 必须保持的不变量：不保存完整 rows、Document 正文、answer、Prompt、凭据、raw error、Thought 或无限原文历史；terminal/clear 立即剥离 state payload，只留最小防重放 tombstone。
- 本模块不冻结的实现细节：JSON 列的物理命名、索引名和内部 codec 函数名；由 G47-1 冻结后落入 migration。

### C3：存储层 CAS、Fencing 与原子 Switch 合同

- 输入：task key、owner/tenant/role binding、expected version、当前 status、claim token/fencing identity。
- 成功输出：恰好一个 claim 把 `active@v` 变为 `claimed@v+1`；仅匹配 claim token/version 的 commit 可变为 `active/terminal@v+2`；switch 在一笔事务内退休旧 task 并创建新 task。
- 失败语义：条件更新影响行数不是 1 即冲突/不可用；死锁或连接失败回滚并投影 storage unavailable，不进入 Tool 或自动扩大重试。
- 必须保持的不变量：数据库事务不跨越 LLM/SQL/RAG Tool 执行；旧 worker 的 fencing token 不能覆盖新状态；重复/旧版本请求零额外 Tool。
- 本模块不冻结的实现细节：使用单条条件 `UPDATE` 还是短 locking-read 事务；以真实 MySQL 竞争测试选择最小正确实现。

### C4：Restart、In-flight Crash 与恢复授权合同

- 输入：已提交 active checkpoint，或崩溃遗留 claimed checkpoint；新进程重新解析的 trusted caller/tenant/active role 和当前授权环境。
- 成功输出：只有已提交 active boundary 可重进 Decision Loop；TaskState/requirements/Evidence validity/route/budget/termination 不漂移。
- 失败语义：claimed 中间态不恢复节点栈、不自动重放 Tool；在确认结果缺失时保守停止并等待 TTL/clear，不宣称 exactly-once。存储不可用不创建同 id 新任务、不降级到内存。
- 必须保持的不变量：恢复后再次执行现有 Evidence freshness/revision/purpose/ACL/outbound 门；role/tenant 不再满足时零 Tool 停止。
- 本模块不冻结的实现细节：用户可见错误文案；稳定 reason code 与安全状态必须冻结。

### C5：TTL、Clear、Tombstone 与清理合同

- 输入：expires_at、status/version、显式 clear 或 bounded maintenance sweep。
- 成功输出：成功 commit 续期 active TTL；clear/expiry/terminal 将 payload 和 event 内容按策略剥离，保留短期最小 tombstone 防止 task id 重放；到保留期后物理删除。
- 失败语义：清理失败不复活 task；clear 只有 CAS 成功才返回成功；wrong owner/missing 保持不可区分。
- 必须保持的不变量：TTL/clear/claim/version 都在存储条件中校验；清理任务不读取或输出业务 payload；历史 Trace/artifact 不被回写。
- 本模块不冻结的实现细节：保留时长和 sweep 触发方式由 G47-1 确认。

### C6：同源 Trace、API 与 Agent Scenario v5 合同

- 输入：一次真实 task boundary 操作及同次 runtime facts。
- 成功输出：API/Trace/Eval 安全投影共享 backend identity、schema identity、checkpoint safe ref、version before/after、claim/commit/clear/expiry、resume source 与 storage outcome；Agent Scenario v5 additive 评分。
- 失败语义：缺 checkpoint execution、额外执行、重复 assertion、身份漂移或伪 durable runtime 使 completed artifact closed-world 校验失败。
- 必须保持的不变量：v1～v4 artifact 不补字段、不改签；raw task id、owner compare value、JSON payload、rows/正文不进入 Trace/Eval。
- 本模块不冻结的实现细节：v5 artifact 内部字段排列和 report 样式。

## 6. 工作切片与执行顺序

### M47-A：B5 additive contract、兼容矩阵与决策冻结

- 优先级：必须完成
- 依赖：M43 TaskState/turn boundary、M44 Loop boundary、M46 handoff、G47-1/G47-2。
- 实施内容：冻结 durable runtime/state/event/lifecycle identity、reason code、数据分类、API/Trace/Eval compatibility matrix、v5 Scenario schema 与持久化禁区；M42～M46 只读。
- 关键合同：C1～C6
- 交付物：机器可读 B5 contract、schema/lifecycle 表、v5 catalog skeleton、决策记录。
- 验证方式：identity/content-binding/closed-world/tamper tests；旧 contract hash 不变。
- Live Probe checkpoint：不适用；本切片没有真实存储实现。
- 完成门：G47-1/G47-2 已确认，所有后续切片都能引用唯一合同而不自行发明存储语义。

### M47-B：TaskState codec、boundary protocol 与内存等价基线

- 优先级：必须完成
- 依赖：M47-A。
- 实施内容：实现 closed-world canonical serializer/deserializer、payload size gate、adapter protocol、typed boundary event；让现有 in-memory adapter 通过统一 contract suite，并补 active role/tenant 恢复输入。
- 关键合同：C1、C2、C4
- 交付物：versioned codec、boundary protocol、in-memory compatibility adapter、contract tests。
- 验证方式：复杂 TaskState round-trip、未知/缺失/篡改/schema mismatch、禁存字段与 adapter parity tests。
- Live Probe checkpoint：不适用；纯 deterministic codec/内存 seam，不能证明 durability。
- 完成门：当前 M43/M44/M46 task 行为不变；codec 对所有可持久字段无损且对不兼容输入失败关闭。

### M47-C：MySQL schema 与 durable adapter

- 优先级：必须完成
- 依赖：M47-A/B、已确认 G47-1。
- 实施内容：新增 Alembic/ORM schema，实现 snapshot + typed event ledger、CAS claim/commit、原子 switch、TTL/clear/tombstone/purge、fencing、故障回滚与 safe runtime identity；SQLite 只承担 migration/contract fixture，durability 结论只来自 MySQL。
- 关键合同：C1～C5
- 交付物：migration、ORM/storage adapter、maintenance seam、durable contract tests。
- 验证方式：SQLite 结构/upgrade/downgrade；MySQL 两独立 session 的 CAS、switch rollback、TTL/clear、payload scrub、schema mismatch 和 storage fault tests。
- Live Probe checkpoint：`M47-P1` / after M47-C、before M47-D；只有 `continue` 才允许产品组装。
- 完成门：P1 证明真实 MySQL 的唯一 claim、原子状态变化和清理语义；不存在应用层伪 CAS。

### M47-D：应用组装、恢复授权与 fail-closed API/Trace

- 优先级：必须完成
- 依赖：M47-C、M47-P1=`continue`。
- 实施内容：由配置/工厂组装 durable 或显式 test-memory adapter；agent task 产品路径使用已确认 durable 默认；恢复时重核 caller/tenant/active role 与 Evidence validity；存储不可用零 Tool；API/Trace 投影 checkpoint lifecycle，不改变 legacy endpoint/payload。
- 关键合同：C1、C4、C6
- 交付物：应用 wiring、配置校验、API/Trace runtime identity、failure projection tests。
- 验证方式：同一 API 的 start/continue/switch/cancel/clear、role/tenant mismatch、storage unavailable、legacy compatibility 和零重复 Tool tests。
- Live Probe checkpoint：不在本切片结束立即单独运行；与 M47-E 的真实 restart/multi-worker 纵向链合并为 `M47-P2`，避免重复写 checkpoint。
- 完成门：durable 是 task family 的真实产品组装而非测试旁路；内存模式只能显式用于 test，runtime 不得伪报 durable。

### M47-E：Restart、Multi-worker 与重复请求纵向链

- 优先级：必须完成
- 依赖：M47-D。
- 实施内容：建立两个独立进程/adapter 实例共享同一隔离 MySQL 的 harness；跑北极星已提交边界 restart continuation、同版本 worker 竞争、重复请求、in-flight crash、TTL/clear 和不兼容版本。
- 关键合同：C3～C6
- 交付物：可重复的 dev harness、Probe 安全摘要、并发/恢复 tests。
- 验证方式：进程 A 提交 T1 后退出，进程 B 继续 T2；并发请求只有一条进入 deterministic Tool；旧 worker/旧 version/cleared/expired 都零 Tool。
- Live Probe checkpoint：`M47-P2` / after M47-E、before M47-F；只有 `continue` 才允许冻结 Scenario v5 completed artifact。
- 完成门：P2 对 restart、multi-worker、duplicate 和安全恢复给出明确三态与 `continue`；测试数据恢复断言通过。

### M47-F：Agent Scenario v5、rehearsal 与兼容回归

- 优先级：必须完成
- 依赖：M47-P2=`continue`。
- 实施内容：从同一次 sequence execution 投影 durable assertions；覆盖 north-star restart variant 和 required non-happy paths；提供零 provider deterministic rehearsal；v1～v4 validator/artifact 只读。
- 关键合同：C2～C6
- 交付物：Scenario v5 validator/artifact/report、rehearsal、capability matrix 更新。
- 验证方式：closed-world completeness、checkpoint/runtime identity、state/event lineage、CAS winner、no duplicate Tool、TTL/clear/schema/storage failures；删除 durable adapter 或条件更新后测试必须失败。
- Live Probe checkpoint：不新增；消费 P1/P2 真实证据，不把 rehearsal 冒充 MySQL durability。
- 完成门：v5 required Gate 全过，v1～v4 与 legacy runtime 原合同同时通过；B5 标 available、B6 仍 unavailable。

### M47-G：验证、技术收工与 B6 handoff

- 优先级：必须完成
- 依赖：M47-A～F。
- 实施内容：按 `finish-module` 审计注释、Probe 时点、migration/数据清理、notes/state/changelog；更新 runbook 的 durable task 运行/清理入口和数据库 state；形成 B6 handoff。
- 关键合同：C1～C6
- 交付物：完整验证快照、技术档案、状态文档与 M48 强制开工输入。
- 验证方式：聚焦→受影响回归→全仓 pytest、migration upgrade/downgrade/check、compileall、`git diff --check`；长任务按 AGENTS 后台纪律执行。
- Live Probe checkpoint：审计 P1/P2；不得在收工阶段首次补跑来掩盖缺失时点。
- 完成门：第 8 节所有必须项闭合，无未处理 `revise/stop/development_probe_missing`；没有把 B6 或生产认证标为完成。

## 7. 决策门

### G47-1：Durable 后端、默认组装与数据生命周期（已确认方案 A）

#### 方案 A：MySQL/InnoDB snapshot + typed event ledger（推荐）

- 做法：复用项目 `DATABASE_URL`、SQLAlchemy 和 Alembic，新增 checkpoint/event 表；agent task 产品路径默认使用 MySQL durable adapter，测试显式注入 in-memory adapter。active TTL 沿用 900 秒 sliding TTL；clear/terminal/expiry 立即剥离 payload，最小 tombstone 保留 24 小时后 bounded hard purge。状态只保存安全 typed facts，不新增应用层加密；访问控制复用专用数据库账号/最小表权限，部署层 TLS/磁盘或 tablespace encryption 必须按环境另行启用，M47 不虚构其已开启。
- 影响：最少新增依赖，可用 InnoDB 事务/条件更新直接证明 CAS；新增两张项目基础设施表、migration、数据库写入和运行维护入口。
- 适用条件：DataPilot 继续以 MySQL 为主运行数据库，B5 目标是同一部署内跨进程/多 worker 的有 TTL task。
- 风险：checkpoint 与业务库共享故障域；JSON payload 需要严格 codec/上限；若数据库账号权限过宽会扩大读取面；必须验证实际 MySQL 版本和事务行为。

#### 方案 B：Redis durable adapter

- 做法：新增 Redis 客户端依赖，以 Hash/JSON + Lua/transaction 实现 CAS、switch、TTL 与 event ledger；必须额外冻结 AOF/RDB、主从故障和清理策略。
- 影响：TTL/原子脚本自然，但项目当前没有 Redis 客户端依赖或已验证持久配置；会新增运行服务、部署和故障模式。
- 适用条件：用户明确希望任务状态与业务库隔离，并愿意把 Redis 持久化、备份和可用性纳入本模块。
- 风险：仅有 `REDIS_URL` 不代表 durable；未开启可靠 persistence 时仍可能重启丢失；Lua/多 key switch 和测试复杂度更高。

#### 建议与确认时点

- 建议：选择方案 A，并确认“900 秒 active TTL + payload 立即 scrub + 24 小时最小 tombstone + bounded purge；不新增应用层加密，明确只保存低敏安全投影”的生命周期。
- 建议理由：它复用当前真实主路径，能用最少新系统闭合事务/CAS/migration/清理；Redis 当前只是未使用配置，不具备现成 durability 证据。
- 用户确认：2026-08-26 选择方案 A。M47 使用 MySQL/InnoDB snapshot + typed event ledger；agent task 产品路径以 durable adapter 为默认，测试显式注入 in-memory adapter；active TTL 为 900 秒 sliding TTL，clear/terminal/expiry 立即 scrub payload，最小 tombstone 保留 24 小时后 bounded purge；不新增应用层加密，也不宣称部署层 TLS/tablespace encryption 已启用。
- 已允许推进：M47-A～G 中属于方案 A 的合同、codec、Alembic/ORM、MySQL adapter、产品组装、测试和文档工作。
- 仍禁止推进：Redis 依赖/服务、超出上述生命周期的数据保留、业务表/seed/release/default model 等非 B5 变更，以及未获 G47-2 精确边界覆盖的真实 MySQL Probe 写入。
- 需要确认的时点：已于 M47-A 开工前闭合；实施不得自行切换为方案 B。
- 重开决策的条件：真实 MySQL 无法提供所需事务/CAS，或部署明确要求状态与业务库隔离且已有可验证 Redis persistence。

### G47-2：真实 MySQL Live Probe 隔离方式（已确认方案 A）

#### 方案 A：独立 `datapilot_m47_test` 数据库（推荐）

- 做法：在独立测试库应用 M47 migration，只写 synthetic task/checkpoint/event；P1/P2 后核对并清空测试 task 数据，保留 migration schema供复验或按用户指示删除。业务 seed、active release、reserve 均不触碰。
- 影响：隔离最清楚，可真实跨进程提交和重启；需要一次建库/授权及持久测试写入许可。
- 适用条件：本机 MySQL 可创建独立库或用户可预先提供测试库。
- 风险：需要额外连接串和清理核对；建库/删库不属于 standing authorization，必须精确授权。

#### 方案 B：现有 `datapilot_dev` 中的唯一 Probe namespace

- 做法：在正式 M47 表中写唯一 synthetic task namespace，P1/P2 后硬删除本次 checkpoint/event并验证零残留；不修改 14 张业务表。
- 影响：无需新数据库，但 Probe 与开发 task 共表，清理失败会留下测试 tombstone。
- 适用条件：无法提供独立测试库，且用户接受在 dev 基础设施表中短暂写入。
- 风险：隔离较弱；错误连接或 cleanup bug 的影响更大。

#### 建议与确认时点

- 建议：选择方案 A；确认后只授权 plan 中 P1/P2 的 checkpoint/event 写入、migration 和精确清理，不授权 seed reset、业务表写入、索引重建或任何 reserve 访问。
- 建议理由：B5 的真实证据必须跨事务/进程提交，无法用单事务 rollback 伪造；独立测试库能把必要持久写入与业务数据隔开。
- 用户确认：2026-08-26 选择方案 A。真实 P1/P2 使用独立 `datapilot_m47_test` 数据库，只允许 M47 migration、synthetic checkpoint/event、并发/重启验证和精确清理；不触碰业务 seed、14 张既有业务/分析表、active release、historical 或 reserve。
- 已允许推进：为 P1/P2 准备独立测试库连接配置、应用 M47 migration、执行计划内持久写入并按前后断言清理测试 task 数据。
- 仍禁止推进：把 Probe 静默改到 `datapilot_dev`、执行 seed/reset、写业务表、重建索引、删除测试数据库本身，或扩大到计划外真实场景。若环境中测试库尚不存在，实际建库命令及目标仍须按工具权限取得执行批准，不能把方案选择冒充任意数据库管理授权。
- 需要确认的时点：隔离方案已于 M47-A 前闭合；实际执行前必须在 notes 记录精确连接目标、命令、数据前后断言、清理范围和完成标记。
- 重开决策的条件：测试库不可用时，重新选择 B；不得静默改写现有 dev 库。

### G47-3：历史 durable schema 迁移（条件触发）

#### 方案 A：首版只接受当前 v2，其他版本 fail closed（推荐默认）

- 做法：M47 从现有 TaskState v2 开始持久化；内存时代没有在线 durable 数据，因此不做 `m37-thread-v2` 或旧 process-local checkpoint 迁移。
- 影响：合同最小清楚，不伪造不存在的在线迁移。
- 适用条件：调查和 codec fixture 证明所有合法当前状态均可无损 round-trip。
- 风险：未来 schema 升级仍需新增显式 upgrader。

#### 方案 B：本模块增加 v2→新 schema 的显式 upgrader

- 做法：仅在真实合法状态无法无损落入 v2 durable schema 时，冻结单向 migration、identity 和失败回滚。
- 影响：扩大合同、测试和 migration 面，但解决已证实的兼容缺口。
- 适用条件：M47-B 出现确定性反例，而非“以后可能需要”。
- 风险：过早建设通用框架，或把宽松补默认变成静默语义漂移。

#### 建议与确认时点

- 建议：默认 A；只有 M47-B 出现真实反例才暂停并提交 B 的精确字段差异。
- 建议理由：当前没有 durable 历史数据，roadmap 也明确禁止迁移 `m37-thread-v2`。
- 用户确认前允许推进：v2 codec 和 fail-closed tests。
- 用户确认前禁止推进：自动/在线 schema 猜测迁移。
- 需要确认的时点：仅在 M47-B 触发。
- 重开决策的条件：当前合法 TaskState 无法通过 C2 round-trip。

## 8. 验证与验收矩阵

### Live Dev Probe（开发期真实探针）

M47 修改真实 MySQL、API 多轮、重启和多 worker 行为，pytest/SQLite/fake 无法独立证明 durability，因此适用 Live Dev Probe。standing authorization、计数、三态、重验和 Formal Eval 分账统一引用 `docs/state/runbook.md`；由于 Probe 必须产生跨事务持久写，本模块额外受 G47-2 精确授权约束。

| Probe ID / 执行时点 | 探针场景 | 真实产品链路/依赖 | 需要观察的结果与 Trace 事实 | 通过/失败/不确定标准 | 决策与停止条件 |
|---|---|---|---|---|---|
| M47-P1 / after M47-C、before M47-D | 两个独立 SQLAlchemy session/adapter 同时 claim 同一 `active@v`；随后验证 commit、switch rollback、TTL、clear/purge | Durable adapter → real MySQL/InnoDB；零 LLM/embedding/RAG/业务 SQL | 条件更新受影响行数、唯一 claim token/version、事务 rollback、payload scrub、event order、runtime/schema identity、测试库零业务表变化 | `passed`：每个竞争仅一胜者且生命周期/清理全符合；`failed`：双 claim、半 switch、payload 残留或错误续期；`inconclusive`：MySQL/权限不可用 | passed→继续 M47-D；failed→revise 且只重验受影响操作；inconclusive→暂停真实 durable 分支，不以 SQLite 覆盖 |
| M47-P2 / after M47-E、before M47-F | 进程 A 通过 API 提交 canonical T1 后停止；进程 B 从同库继续 T2；两个 worker 再竞争同版本；另测 role/tenant 变化、重复请求、claimed crash、clear | `/api/query` → fixture caller → durable task boundary → deterministic SQL Tool → Response/Trace；real MySQL，零 remote provider | 120000/180000/60000/0.5 oracle、state identity/route/Evidence invalidation、resume source、CAS winner、Tool call count、role/tenant/TTL/clear/schema/storage failure、Trace 无 raw id/payload | `passed`：重启后语义不漂移、竞争只一次 Tool、所有拒绝零 Tool且数据清理闭合；`failed`：状态漂移、重复 Tool、权限绕过、内存 fallback或残留；`inconclusive`：进程/DB依赖不可用 | passed→继续 M47-F；failed→revise/stop，不自动重跑；inconclusive→不得宣称 B5 complete |

Probe 数据固定为 synthetic task state 与既有 Phase 4B 只读 oracle；不执行 seed/reset，不改业务表，不调用真实 LLM/Milvus，不访问 historical/reserve。若使用独立测试库，migration 和数据清理目标在 notes 中记录绝对数据库名、前后表/行数与完成标记；若清理失败，整体 `stop`。

模块完成后建议用户执行的 Formal Eval：当前无需正式质量 Eval。M47 required Gate 由 deterministic Agent Scenario v5 + 真实 MySQL P1/P2 承担；RAG historical/reserve、LLM Reliability 和质量默认决策均不属于本模块。

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 adapter-neutral boundary | 同一 contract suite 跑 memory/MySQL adapter；API wiring tests | 公开语义等价，runtime durability 不混报，endpoint 无后端分支 | 必须完成 |
| C2 codec/minimal schema | round-trip、tamper、payload size、禁存字段、migration tests | 合法状态无损；不兼容 fail closed；无 rows/正文/answer/Thought | 必须完成 |
| C3 CAS/fencing/switch | SQLite deterministic + real MySQL P1 并发/事务 tests | 同版本恰一 claim；旧 token 不可 commit；switch 无半状态 | 必须完成 |
| C4 restart/authorization | process restart、multi-worker、role/tenant/ACL/freshness tests + P2 | 仅 committed boundary 恢复；in-flight 不重放；拒绝零 Tool | 必须完成 |
| C5 TTL/clear/cleanup | clock tests、real MySQL lifecycle、maintenance tests | storage 条件执行 TTL/clear；payload 及时 scrub；到期 purge且不复活 | 必须完成 |
| C6 API/Trace/Eval v5 | response/JSONL/artifact 同源、closed-world/tamper tests | identity/version/lifecycle 一致；v1～v4只读且无敏感投影 | 必须完成 |
| legacy compatibility | M35–M38 thread/follow-up、M43/M44 task、M46 B4、全仓 pytest | `m37-thread-v2` 不迁移；旧 assertion 未放宽；Pipeline/Subgraph rollout不变 | 必须完成 |

聚焦测试顺序：codec/protocol → in-memory parity → migration/schema → durable CAS/lifecycle → API/Trace → Scenario v5。真实 P1/P2 只在对应切片时点执行一次；失败后先修复并按 runbook 最小重验。

全量回归范围：M1 migration/database、M35–M38 legacy thread/Harness、M42 B0 identity/reserve、M43 task runtime/boundary/API、M44 Loop/API/Scenario v3、M46 B4 runtime/Scenario v4，以及最终全仓 deterministic pytest。预计超过 2 分钟的完整验证按 AGENTS 写 notes checkpoint 后后台运行。

不属于本模块的真实验证：Qwen/embedding/Milvus、RAG historical/reserve、Subgraph 质量、生产认证、跨机器分布式数据库故障、性能/吞吐、备份恢复、MySQL tablespace encryption 运维和 B6 compact equivalence。

历史 artifact/合同只读：M27/M31–M46 completed artifact 不补字段、不改签、不重跑制造 M47 分数；M42 v1、M43 v2、M44 v3、M46 v4 保留原 validator，M47 新建 additive v5；reserve 保持 sealed/read0/not-run。

## 9. 依赖与交付物

### 依赖

- 已验收的 M43 TaskState/TaskDelta/task boundary、M44 Decision Loop turn boundary、M46 B4 termination/child ledger 与 rollout 合同。
- 当前 MySQL/SQLAlchemy/Alembic 底座、trusted caller/tenant/active role seam、Evidence validity/ACL/outbound 合同。
- 用户已于 2026-08-26 确认 G47-1/G47-2 均采用方案 A；真实 Probe 使用独立 `datapilot_m47_test`，执行前仍须按已确认边界登记精确目标、命令和清理断言。
- `docs/state/runbook.md` 的 Live Dev Probe、长任务和数据库安全纪律。

### 交付物

- additive B5 machine contract、TaskState codec、adapter-neutral task boundary 与 memory compatibility adapter。
- durable checkpoint/event schema、Alembic migration、MySQL adapter、CAS/fencing/switch/TTL/clear/tombstone/purge。
- 产品组装、配置校验、恢复授权、fail-closed API/Trace 投影。
- restart/multi-worker/duplicate harness、真实 MySQL P1/P2 证据。
- Agent Scenario v5、deterministic rehearsal、required Gate 与旧 family compatibility view。
- M47 notes、runbook/database/eval/state/changelog 更新和 M48/B6 handoff。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：B6 deterministic typed Compact、production auth、跨地域 HA/灾备、性能调优、应用层字段加密、任意外部副作用 Tool exactly-once。
- 下一模块可直接消费的产物：durable ordered event ledger、checkpoint/compact reference seam、node Context/state identity、restart/multi-worker Scenario v5 和生命周期/清理合同。
- M48/B6 强制开工条件：M47 C1～C6 required Gate 与 P1/P2 均已闭合，durable ledger 的字段/顺序/保留策略稳定；届时实现 typed Compact、recent raw turn 窗口和 compact 前后行为等价，不能把本模块 event ledger 冒充 Compact。
- 后续需要根据真实失败重新规划的内容：只有出现真实 CAS死锁、payload 上限、恢复授权或 schema evolution 失败簇，才另立最小修复候选；不得模糊写“以后优化持久化”。
- 可能存在的风险：共享 MySQL 故障域、task payload 增长、claimed crash 导致任务保守不可继续、清理失败、测试环境与真实 MySQL版本差异；这些都必须显式投影，不能回退内存或自动重放。
- 最终目标没有缩水：M47 必须完整达到 B5 completion；M48/B6 完成前不得宣称 Phase 4B 六项最终能力全部交付。

## 11. 开工条件

- 开工前无需确认：M47 完整对应 B5；只恢复 committed task boundary；不恢复 Graph/Subgraph program counter；legacy `m37-thread-v2` 不迁移；v1～v4 artifact 只读；M46 rollout/default/reserve 不变；B6 Compact 不提前实现。
- 已确认：G47-1 采用 MySQL/InnoDB durable adapter、900 秒 active TTL、立即 payload scrub、24 小时最小 tombstone、bounded purge、不新增应用层加密；G47-2 采用独立 `datapilot_m47_test`，只授权计划内 migration、synthetic checkpoint/event、P1/P2 和精确数据清理。
- 实施中条件确认：只有 M47-B 发现真实 schema round-trip 冲突时进入 G47-3；没有则保持方案 A。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支。
