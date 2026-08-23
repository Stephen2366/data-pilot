# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，Text2sql 和 RAG 评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，RAG / 知识库事实见 `docs/state/rag-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

## 当前状态

| 项目         | 当前值                                                       |
| ------------ | ------------------------------------------------------------ |
| 阶段路线     | `docs/phase4b-roadmap.md`                                    |
| 阶段参考     | `docs/phase4-reference.md`                                   |
| 当前活动模块 | M44A / EnterpriseRAG-Bench Milvus 产品运行链路已验收通过（2026-08-24） |
| 当前 plan    | `docs/notes/m44a-plan.md`；只解决 Enterprise 向量产品链，不占 B2 里程碑 |
| 当前 notes   | `docs/notes/m44a-notes.md`                                   |
| 待决事项     | 下一步仍为 M44/B2 独立 module plan；M46 前 60 题 decision reserve 保持 sealed |
| 更新时间     | 2026-08-24                                                   |

## 必读规则

- 开始开发、排障或验证前先读本文。
- 运行任何项目命令前必须先读 `docs/state/runbook.md`；涉及 Text2SQL/Schema Retrieval/SQL Eval/数据库验证时继续读 `runbook-text2sql.md`，涉及业务 RAG/M34/external 180/RAG Eval 时继续读 `runbook-rag.md`。
- 解释 eval 数字、模型 A/B、失败归因或分母时必须读 `docs/state/eval-baselines.md`。
- 涉及 SQL/字段/指标/oracle 时读 `database-current-state.md`。
- 涉及知识原件、active release、外部 corpus、Knowledge Tool、RAG Eval 或 M34 语料状态时读 `rag-current-state.md`。
- 涉及 Milvus/embedding/Schema Retrieval 时读 `schema-retrieval-milvus-embedding.md`。
- 写入 changelog、记录小修或追溯设计原因、历史实验时，先读 `docs/state/CHANGELOG_INDEX.md`，再进入索引指定的 Phase 文件。
- 前台等待超时不等于真实 Eval 已结束：按 runbook 用同一 `run_id` 检查 manifest、checkpoint、artifact；不得擅自换 ID 重跑。
- 用户明确说执行某个 eval 时，按 runbook 的“一次精确运行授权”直接执行一次；不重复询问授权，也不扩大范围或切换默认配置。
- 默认模型、embedding、正式 case、安全策略、数据库结构等长期选择，必须先说明方案并等待用户确认。

## 当前默认值

- 后端：FastAPI + Pydantic；`/api/query` 无 `task` 时保持 M37 legacy turn seam；只有严格 nested task envelope 才进入 M43 agent task family。accepted task turn 为零或一次 M35 深 Graph，clarification/cancel/clear/pre-rejection 为零次；响应、JSONL Trace 与 Eval 从同一 delta/state transition/Evidence validity/lifecycle 事实投影。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- Phase 4B seed：默认仍为 legacy `sqlite_deterministic_seed`；只有显式选择 `profile_alias="phase4b"` 才加载 content-bound B0 profile，生成 7/8 月 oracle。不得把两个 profile 的 artifact 混算。
- NL2SQL：普通 API 默认走 Harness 内的 `new_text2sql` 深 Tool（Schema Retrieval → QueryPlan → SQL Guard）；显式 `force_new_pipeline=false` 只选择 adapter 内部 legacy baseline，不能绕过顶层 Harness。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1；本机 `.env` 已覆盖 `LLM_TIMEOUT_SECONDS=120`（2026-08-23，Qwen 比较类 QueryPlan 实测 43~105s，45s 会误杀），config 默认仍为 45。
- Schema Retrieval 默认：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅在显式实验中开启。
- Knowledge Retrieval 分账：22 条业务 release 仍默认 `knowledge-deterministic-lexical-v1`；EnterpriseRAG-Bench 产品 API/external Eval 默认 `knowledge-enterprise-milvus-semantic-v1`，lexical 只允许显式历史 baseline。两者与 Text2SQL Schema Retrieval 均为独立链路。
- Harness：LangGraph `>=1.1.2,<2`；SQL/RAG 单路仍为 `route → tool → controller`、各至多一个深 Tool。M38 canonical Hybrid 为 `route → hybrid_sql_tool → hybrid_rag_tool → controller`，SQL/RAG 都 required、各至多一次、总计至多两个深 Tool；Router 只签发薄计划，RAG branch 只执行 retrieval + Gate，不生成子答案。未知 Hybrid 继续保守停止；M37 follow-up 仍只覆盖 SQL/RAG。
- Thread checkpoint：方案 A，应用持有 `inprocess-bounded-thread-v2`，state `m37-thread-v2`，默认 TTL `900s`（`THREAD_CHECKPOINT_TTL_SECONDS`）。除 M36 一次结构化恢复外，成功 SQL/RAG 可在显式开启后签发一次 closed-world follow-up；owner 绑定 trusted caller + tenant/active role，同 version 原子单 claim，重启/多 worker 不恢复或共享。checkpoint 不保存旧 answer/rows/正文/citation。
- Agent task boundary：应用另持有 `phase4b-in-memory-task-boundary-v1`，复用默认 TTL 900s，但与 thread checkpoint/state family 分离。它绑定 trusted caller+tenant、执行 version/TTL/原子 claim/commit/switch/cancel/clear；错 owner 与未知 task 统一失败。只保存通用 TaskState 与安全 EvidenceRef validity，不保存 rows/正文/完整历史答案；明确为 process-local non-durable，B5 前不得宣称跨进程恢复。
- Evidence follow-up：SQL 没有可靠业务 snapshot，永远重查；EnterpriseRAG-Bench external 永远重检索；只有业务 22-entry release 的同 requirement 解释动作可按当前 active authority/revision/content/anchor 重新加载并重新授权，随后签发新 run Evidence/ledger/citation。requirement/identity 变化重检索一次，ACL/用途拒绝零 retrieval 停止。
- Caller：`local/demo/test` 使用明确标记的 fixture resolver，请求 `user_role` 只能选择 resolver 已解析的 role；其他环境没有 authenticated resolver 时在 Tool 前失败关闭。生产认证尚未建设。
- M44A Enterprise 产品链：项目外 EnterpriseRAG-Bench v1.0.0 SQLite profile 是正文/Evidence authority；Milvus semantic snapshot `9aec12...e20` 是默认候选索引，collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`。应用不代管 Docker/Milvus；配置或索引不可用时 `/health/rag` 503、RAG 零 Evidence/Composer，不回退 lexical 或业务小语料，SQL 与 `/health` 仍可用。
- LangFuse 默认关闭，JSONL trace 为主；SQL 安全为只读 AST + RBAC + 敏感字段策略。
- Trace runtime identity：legacy SQL/RAG/Hybrid/澄清恢复/安全拒绝继续投影 `phase4-trace-runtime-v1`；task family 外层投影 `phase4b-agent-task-runtime-v1` 并内嵌深 Harness identity。缺少安全 identity 只标 `unavailable`、不阻断业务。Trace 不保存 raw `thread_id`/raw `task_id`、结构化控制参数副本、rows 或文档正文，但沿用既有用户可见 `answer` 保存合同。
- 现有 Text2SQL chat/schema embedding 出站在 transport 前按 `phase4-outbound-v1` 精确登记；普通 Knowledge/RAG 与 LangFuse Cloud 继续默认拒绝。唯一例外是用户确认的 M41 显式 Eval CLI：`phase4-rag-eval-business-generation-outbound-v1` 只允许已通过 active release、caller/ACL/Gate 的政策/指标 generation context 发往 Qwen，security/未知类别网络前拒绝；该 policy 不进入普通 API。

## 最近验证事实

> 只保留会影响当前决策的最新证据，不按模块流水账累积。

| 日期 | 事实 |
|---|---|
| 2026-08-24 | M44A semantic external dev Smoke 9 题一次 completed：artifact `4bfff9d...5346d`，Gate failed、required `92/16/0`，triage `5 passed / 4 retrieval`，9 provider responses / 19033 tokens；哈希复核后的人工 verdict `2 pass / 7 fail`。相对历史 lexical smoke，自动 candidate compare `1 win / 5 tie / 3 loss`，人工 `3/6→2/7`。两侧均单次 generation，不能归因成稳定 backend 因果或 Reliability；不登记长期基线、不触碰 held-out，semantic 产品默认不变。 |
| 2026-08-24 | M44A 将 Enterprise 产品 API/external Eval 切为同源 semantic 默认，并补齐 lifespan、`/health/rag`、Milvus load/identity/unit-set 门和 fail-closed。全仓 `517 passed, 1 warning`。用户授权的 `qst_0386` 恰好一次真实 C6 completed：artifact `0a5bc40...c9647`，required `12/0/0`，semantic 漏斗 `5→3→3→1`，Qwen 2054 tokens，人工语义 pass；只证明单题产品链，不是 semantic 质量基线。 |
| 2026-08-23 | M43 完成 B1：B1 contract `383fbf5...e9d32`、Scenario v2 artifact `cc9f696...b27c92`，deterministic rehearsal 8/8、external calls=0；canonical T2 会使旧 SQL Evidence invalidated 后重查，得到 7 月 120000、8 月 180000、差额 60000、增幅 50%。最终全仓 `500 passed, 3 skipped, 1 warning`。legacy/M42 v1、模型、RAG release、数据库 schema 均未改变。 |
| 2026-08-23 | M42 完成 Phase 4B B0 前置包：B0 contract `6543883...aae6f`、seed profile `9c49407...00673`、SQL oracle `be813a8...57ef80`、Agent skeleton `b303d4d...52982`、sealed reserve `f70c5fc...e505`。首次 business retrieval 零 provider 且真实漏选 basic 政策，保留为 B3 输入；M43–M48 能力仍 unavailable。最终全仓 `487 passed, 3 skipped, 1 warning`，未改 legacy/active release/默认模型或任何长期基线。 |
| 2026-08-23 | M41 post-fix external dev Smoke / Basic / Core 均已 completed，但 Gate 和人工语义 review 显示 lexical 漏召回仍是主要瓶颈；这些快照未登记正式基线，120 held-out 未运行。business 与 external 分账、一次精确授权、三态 Gate、review hash 和安全出站纪律继续生效；完整运行身份、数字与失败分层只在 `eval-baselines.md` 保存。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的必须删除或改写。

- (2026-08-23) M43 已完成 B1 的独立 task runtime、自然多轮 v1、Evidence invalidation 和 node Context，但每个 turn 仍最多一次既有深 Harness，不等于 B2 Agent Loop 或完整 Phase 4B Agent。M44/B2 必须另立 plan 冻结 Decision Loop/多动作预算；M45/B3 只能用预注册动作诊断首次漏选；M46/B4 前 reserve 必须 sealed，提前访问或调参即退休。
- (2026-08-24) M44A 是 B2 前置修复，不占 B milestone。business 小 catalog 与 external 180 题继续分账，120 held-out 保持停门；external 产品默认现为 semantic，但历史 lexical artifact/正式 retrieval baseline 不改签，也没有证据宣称 semantic 质量更优。下一步仍是 M44/B2，M46 reserve 继续 sealed。

## 防遗忘能力账本

> 记录已经存在、但容易被“当前窄实现已完成”掩盖的能力缺口和重开门。优先级表示防遗忘/复核顺序，不自动决定下一模块；下一模块仍须按 roadmap、最新失败证据和独立 plan 裁决。原方案字母只在对应 module plan 内有效，禁止脱离具体方案写“以后从 A 升级 B”。

下表为 M29–M40 的能力缺口相关记录，M41 及以后的需要新建一个表格来记录。

| 优先级 | 能力缺口 | 当前结论与硬性重开门 | 路线归属 |
|---|---|---|---|
| P0 | M34 已证实 lexical 漏召回、selected budget / multi-document context packing 和 Composer support 拒绝会严重限制答案质量 | M44A 按用户确认把现有 semantic snapshot 接为 Enterprise 产品默认，但单题 C6 不构成质量胜出证据；M39 的 B3/B4 action-level Evidence 与 review-point 门不变，不能借默认切换跳过 diagnostic campaign | Phase 4B B3/B4 |
| P1 | M38 方案 A 只冻结正式本地确定性 Hybrid Synthesizer；远程方案 B 与双 adapter 方案 C 未实施 | B 的重开门：受控 operators 对真实开放 Hybrid 问法形成稳定失败簇，且用户明确批准 receiver、`hybrid_synthesis` 用途、question/conditions、SQL safe result、Document Evidence/identity 的数据类别与字段，并提供真实 provider 精确运行授权。C 的重开门：除上述授权外，还需有未污染 Hybrid held-out、多轮可比预算和明确 A/B 决策价值；禁止仅为“代码里有两个 adapter”扩大 M38。无稳定净收益时 A 继续作为默认与 fallback | P5 后续质量/出站条件项 |
| P1 | 当前只有 demo/test caller resolver，生产认证尚未建设 | 出现非本地部署、真实用户/tenant、JWT/OAuth/SSO 或企业目录需求时，必须在现有 `CallerResolver` seam 接正式认证 adapter；“所有环境手工注入 resolver”不等于生产认证 | Phase 4 后续部署门 |
| P2 | M35/M38 deterministic Router 只覆盖 closed-world SQL/RAG 和两类 canonical Hybrid operator | 先建立开放问法/混合意图 decision set 并形成稳定失败簇，再比较规则扩充、受控模型 fallback 或远程 Router；不得以“LLM 更完善”为由无 Eval 切换 | P3/P5 后续质量 |
| P1 | M37 checkpoint 仍为进程内，重启/多 worker 不恢复且 tombstone 不清扫 | Phase 4B 已把 durable task state 提升为最终硬交付；须在 TaskState/turn-boundary 稳定后建立新 state family、真正持久 adapter 与存储层条件更新，并覆盖 TTL/clear/多 worker/版本冲突。LangGraph `InMemorySaver` 仍是内存态，不能冒充持久化升级 | Phase 4B B5 |

## 已知的坑（活跃列表）

> 只允许活跃问题；已经解决的内容移入 changelog。

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 的模型注册可能触发循环导入 | 聚合导入模型时可能失败 | API/工具层沿用 `app.db.base` 暴露路径；重构时再拆 base class。 |
| 旧 Milvus collection `datapilot_schema_docs` 有重复灌入污染 | 历史 A/B 不可信 | 新 eval 用唯一/clean collection；校验 row count、dimension、schema docs hash。 |
| QueryPlan 可能过宽，或 SQL 与计划不一致 | contract pass 不等于答案正确 | 保持保守 AST 边界，用 output/result/trace 共同定位。 |
| `knowledge_docs` 物理表仍存在且是有损 legacy 投影 | 新调用者若绕过 source-backed catalog 读取旧表，会丢失 revision/authority/identity/完整 ACL，并重新制造旁路 | Text2SQL 已从 Schema/prompt/RBAC 双重隔离；seed 只从 staged catalog 派生，旧表不得作为 authority/runtime catalog。 |
| Active Knowledge release 损坏时不会自动 fallback；当前虽有 previous，但旧 11-entry release 已不等于当前 authority | 自动复活旧正文可能绕过撤销/ACL，或丢失新增内容 | 启动失败关闭；显式 rollback 仍必须重新通过当前 authority/revision/policy 校验。 |
| LangFuse Cloud 重新启用前需统一 question/answer 脱敏（M28 F7） | RAG/Hybrid 若启用 Cloud 会外传完整问答 | LangFuse 默认关闭且 M31 outbound 未放行 Cloud；重新启用前先做 allowlist/redaction 策略和用户决策。 |
| Qwen `qwen3.7-plus` 对双月比较类 QueryPlan 生成不稳定 | 真实运行 4 次 3 种失败（2×45s 超时、1×PostgreSQL 方言 `DATE_TRUNC` 执行报错、1×计划结构非法被自检拦截）；成功耗时 43~105s | 本机超时已调 120s；方言自检/修复与失败重试属于 Text2SQL 质量课题和 M44/B2，未在 M43 处理 |
| Enterprise semantic 依赖项目外 profile、DashScope embedding 与 Milvus | Docker 未启动、snapshot identity 漂移或 provider 不可用时 RAG 会明确 unavailable；启动加载/核验约 10 秒，当前单锁优先保证共享 client 安全而非吞吐 | 启动前按 `runbook-rag.md` 执行 preflight；应用不自动启动 Docker、不降级 lexical；用 `/health/rag` 判断 readiness，性能优化须另立候选与证据 |
