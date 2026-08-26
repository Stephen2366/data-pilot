# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，Text2sql 和 RAG 评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，RAG / 知识库事实见 `docs/state/rag-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

## 当前状态

| 项目         | 当前值                                                       |
| ------------ | ------------------------------------------------------------ |
| 阶段路线     | `docs/phase4b-roadmap.md`                                    |
| 阶段参考     | `docs/phase4-reference.md`                                   |
| 当前活动模块 | M46/B4 技术收工已完成；等待finish-docs与后续人工检查 |
| 当前 plan    | `docs/notes/m46-plan.md`                                    |
| 当前 notes   | `docs/notes/m46-notes.md`                                   |
| 待决事项     | 无产品策略待决；完成M46学习复盘，reserve继续sealed/not-run |
| 更新时间     | 2026-08-26                                                   |

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

- 后端：FastAPI + Pydantic；`/api/query` 无 `task` 时保持 M37 legacy turn seam；只有严格 nested task envelope 才进入 Phase 4B agent task family。accepted task turn 为零或一次 B2 深 Loop Graph invoke，内部可按预算执行多个 closed-world Evidence action；clarification/cancel/clear/pre-rejection 为零次。响应、JSONL Trace 与 Eval 从同一 delta/state transition/Evidence validity/lifecycle/Loop 事实投影。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- Phase 4B seed：默认仍为 legacy `sqlite_deterministic_seed`；只有显式选择 `profile_alias="phase4b"` 才加载 content-bound B0 profile，生成 7/8 月 oracle。不得把两个 profile 的 artifact 混算。
- NL2SQL：普通 API 默认走 Harness 内的 `new_text2sql` 深 Tool（Schema Retrieval → QueryPlan → SQL Guard）；显式 `force_new_pipeline=false` 只选择 adapter 内部 legacy baseline，不能绕过顶层 Harness。
- SQL dialect repair：服务端默认 `deterministic_ast`，只处理 typed MySQL month DATE_TRUNC；私有复用首次可信 QueryPlan/candidate/issue，不重新调用 QueryPlan provider，结果重走 validator、fidelity、Guard 与执行。客户端不能选策略，LLM repair 仅为非默认候选。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1；本机 `.env` 已覆盖 `LLM_TIMEOUT_SECONDS=120`（2026-08-23，Qwen 比较类 QueryPlan 实测 43~105s，45s 会误杀），config 默认仍为 45。
- Schema Retrieval 默认：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅在显式实验中开启。
- Knowledge/RAG 分账：22 条业务 release 默认 `knowledge-deterministic-lexical-v1`；EnterpriseRAG-Bench 产品 API/external Eval 默认 `knowledge-enterprise-milvus-semantic-v1`，lexical 只允许显式历史 baseline；两者与 Text2SQL Schema Retrieval 均为独立链路。
- Harness：LangGraph `>=1.1.2,<2`；SQL/RAG 单路仍为 `route → tool → controller`、各至多一个深 Tool。M38 canonical Hybrid 为 `route → hybrid_sql_tool → hybrid_rag_tool → controller`，SQL/RAG 都 required、各至多一次、总计至多两个深 Tool；Router 只签发薄计划，RAG branch 只执行 retrieval + Gate，不生成子答案。未知 Hybrid 继续保守停止；M37 follow-up 仍只覆盖 SQL/RAG。
- Thread checkpoint：方案 A，应用持有 `inprocess-bounded-thread-v2`，state `m37-thread-v2`，默认 TTL `900s`（`THREAD_CHECKPOINT_TTL_SECONDS`）。除 M36 一次结构化恢复外，成功 SQL/RAG 可在显式开启后签发一次 closed-world follow-up；owner 绑定 trusted caller + tenant/active role，同 version 原子单 claim，重启/多 worker 不恢复或共享。checkpoint 不保存旧 answer/rows/正文/citation。
- Agent task boundary：应用另持有 `phase4b-in-memory-task-boundary-v1`，复用默认 TTL 900s，但与 thread checkpoint/state family 分离。它绑定 trusted caller+tenant、执行 version/TTL/原子 claim/commit/switch/cancel/clear；错 owner 与未知 task 统一失败。只保存通用 TaskState v2 与安全 EvidenceRef validity，不保存 rows/正文/完整历史答案；明确为 process-local non-durable，B5 前不得宣称跨进程恢复。
- B2 Agent Loop：只有 accepted task turn 进入独立 `phase4b-agent-loop-v1`，由确定性 Controller 选择 closed-world Evidence action；父预算最多 3 次 Evidence action/deep Tool、1 次 Knowledge、每 requirement 1 次 repair、6 次 model call、24000 observed tokens。clarification/cancel/clear/pre-rejection 为零 Loop，legacy 非 task Harness 拓扑不变。
- B4 RAG acquisition：服务端保留 Pipeline/Subgraph 两个 adapter，Pipeline 仍为产品默认与显式 baseline，Subgraph 仅 server-controlled experimental；Subgraph 在一次父级 Knowledge action内执行 bounded initial retrieval → Observation → eligible rewrite/expansion/stop → Evidence merge/reauthorize，并投影独立 child ledger。historical candidate `ab66f20d...2f78` 已完成最后一次60×2且no-go；当前内容绑定rollout contract `ebb06f82...f164`明确`quality_claim=not_established`、无自动跨策略fallback、reserve sealed/not-run。
- Task Knowledge runtime：服务端 requirement scope 只允许 `business_release/external_profile`，请求不能选择 corpus/backend。business 使用 22 条 active release lexical，external 与普通非 task RAG 使用 Enterprise semantic；SQLite profile 是正文 authority，Milvus/identity/ACL/readiness 缺失时失败关闭且不跨账 fallback。完整 runtime identity 与 preflight 见 RAG/Milvus 专项 state。
- Evidence follow-up：SQL 没有可靠业务 snapshot，永远重查；EnterpriseRAG-Bench external 永远重检索；只有业务 22-entry release 的同 requirement 解释动作可按当前 active authority/revision/content/anchor 重新加载并重新授权，随后签发新 run Evidence/ledger/citation。requirement/identity 变化重检索一次，ACL/用途拒绝零 retrieval 停止。
- Caller：`local/demo/test` 使用明确标记的 fixture resolver，请求 `user_role` 只能选择 resolver 已解析的 role；其他环境没有 authenticated resolver 时在 Tool 前失败关闭。生产认证尚未建设。
- LangFuse 默认关闭，JSONL trace 为主；SQL 安全为只读 AST + RBAC + 敏感字段策略。
- Trace runtime identity：legacy family 投影 `phase4-trace-runtime-v1`，task family 投影 `phase4b-agent-task-runtime-v1`，并安全描述 B2 Loop/action/budget/termination/knowledge runtime；缺少安全 identity 只标 `unavailable`。SQL 单路 JSONL 沿用 Guarded `columns/rows` 兼容合同，Hybrid、action、Context 和 artifact 不携带完整 rows；其余安全禁区见 runbook。
- 现有 Text2SQL chat/schema embedding 出站在 transport 前按 `phase4-outbound-v1` 精确登记；普通 Knowledge/RAG 与 LangFuse Cloud 继续默认拒绝。唯一例外是用户确认的 M41 显式 Eval CLI：`phase4-rag-eval-business-generation-outbound-v1` 只允许已通过 active release、caller/ACL/Gate 的政策/指标 generation context 发往 Qwen，security/未知类别网络前拒绝；该 policy 不进入普通 API。
- 开发期真实验证：Live Dev Probe 是已获 standing authorization 的开发期真实验证；额度、计数口径、禁区、重验与 Formal Eval 分账见 `docs/state/runbook.md`。Probe 必须嵌入开发切片；`finish-module` 只审计时点证据，缺失时以 `development_probe_missing` 退回开发。

## 最近验证事实

> 只保留会影响当前决策的最新证据，不按模块流水账累积。

| 日期 | 事实 |
|---|---|
| 2026-08-26 | M46技术收工：注释审计23文件/257符号、缺失0；聚焦`57 passed`，兼容修复聚焦`26 passed`。全仓首次发现并修复M33/M34 Pipeline兼容回归；第二次625项通过，唯一M31临时目录`os.replace` WinError5项独立`1 passed`，故当前626项均有通过证据。M46 rollout identity=`ebb06f82...f164`，默认/experimental/reserve边界不变。 |
| 2026-08-26 | M46最后一次 historical v3 `m46-historical-paired-20260826-164511` 两臂各60 completed，Gate `598/112/10 → 393/139/188`，paired `57 insufficient / 3 tie`。value-shape `19→0`、child projection 60/60、answer-ready `12→26`，但26题全部被Composer合同拒绝，另有Evidence run mismatch19，最终Subgraph仍`60/60 no_answer`。用户已确认`no_go_revise_stop`后的轻量收口：不冻结candidate、不解封reserve、不再追加同类historical；Pipeline默认/Subgraph experimental，未来修复包在仓库外todo。 |
| 2026-08-25 | M45-H/P5 最终 passed：显式默认关闭的 `procedure_boundary_v1` 在 qst_0431 initial coverage 显示完整、且 SQLite authority 证明存在 forward unit 时，准入 expansion 并新增 2 条同物理文档后续 Evidence；P5 retrieval/embedding/chat/Composer=0。v4 review `949a3b03...fbb4`=`go_for_M46`，两张 action card completed，累计 provider attempts 仍为 11；全仓 `582 passed, 1 warning`。M45/B3 技术完成，但它仍是 diagnostic admission，不是产品 RAG Subgraph。 |
| 2026-08-25 | M45-P4R/v3 最终 no-go：qst_0461 用 P4 immutable proposal 离线重放后 expansion passed；qst_0431 唯一 Qwen revalidation transport 成功，但本地 coverage validator 判为 `proposal_no_unsupported_requirement`，未触发 action。runner 未 catch 异常导致 raw/token usage 丢失，故 tokens=`unobserved`，严禁估算为 0 或补发。recovered safe `6426219b...a949`，v3 review `8fb3cfad...14e4`，累计 provider attempts=`8 embedding + 3 chat = 11`；M45/B3 未完成、M46 blocked。 |
| 2026-08-25 | M45-P4 受控 A2 真实 Probe failed：qst_0431 proposal schema 因 prompt 未声明 marker 数量上限被 validator 拒绝；qst_0461 正确提出 weekly schedule 缺口，但 literal phrase matcher 未命中语义等价 sibling，expansion 未准入。2 Qwen calls / 3877 tokens，零新 retrieval/embedding/Composer；累计 provider attempts=10。safe `a374f0c0...cfac`，v2 review `ce0d7615...40af`=`review_required/no_go`；不自动重跑，M46 blocked。 |
| 2026-08-25 | M45 Live Dev Probe：P1 business rewrite passed；P2 Round 2 找到目标文档但 coverage 未闭合；P2C immediate neighbor failed；用户确认的 sibling v2 在 P2D passed；P3 的 qst_0431/qst_0461 均因 deterministic question-derived coverage 误判为完整而只允许 stop，未执行 recovery。campaign 共 8 embedding provider attempts、零 chat/model/Composer、零 observed chat tokens；review artifact `33efaf8f...9ea9`，结论 `review_required/no_go`，M46 不得开工。 |
| 2026-08-24 | `M44-PFIX-G4-1` 真实 canonical T1→T2 passed：4 calls / 15762 tokens；T2 same-source Answer/rows/Trace 给出 120000/180000/60000/50%，completion identity `41b577e...ecac9`，raw DB marker=0，数据库 rollback。初始 SQL 合法而未触发 repair，故 G3 repair real path 仍 inconclusive；不为展示 repair 重跑。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的必须删除或改写。

- (2026-08-24) M44A 仍是 B2 前置修复、不占 B milestone。business 小 catalog 与 external 180 题继续分账，120 held-out 保持停门；external 产品默认为 semantic，但历史 lexical artifact/正式 retrieval baseline 不改签，也没有证据宣称 semantic 质量更优。
- (2026-08-25) M45/B3最终以v4 `go_for_M46`完成，rewrite、bounded sibling expansion与procedure forward continuation两张action card已闭合；M46已消费这些diagnostic contracts并完成experimental产品Subgraph。M45的Evidence gain仍不能外推为答案正确率，最终默认/质量结论以M46 historical no-go与rollout为准。
- (2026-08-26) M46/B4技术收工已完成：完整experimental Subgraph、父子预算和同源Eval child ledger可复用；最后一次historical v3仍60题无答案并三档退化。Pipeline默认、Subgraph server-controlled experimental、无自动fallback、quality claim未建立；candidate不冻结，reserve sealed/not-run。后续质量修复须以新假设/新candidate/新授权另立计划；Phase 4B主线下一技术入口为M47/B5 durable task state。

## 防遗忘能力账本

> 记录已经存在、但容易被“当前窄实现已完成”掩盖的能力缺口和重开门。优先级表示防遗忘/复核顺序，不自动决定下一模块；下一模块仍须按 roadmap、最新失败证据和独立 plan 裁决。原方案字母只在对应 module plan 内有效，禁止脱离具体方案写“以后从 A 升级 B”。

M41 及以后的能力缺口：

| 优先级 | 能力缺口                                                     | 当前结论与硬性重开门                                         | 路线归属              |
| ------ | ------------------------------------------------------------ | ------------------------------------------------------------ | --------------------- |
| P2     | M44 G44-2 未选方案 B：由结构化模型提出 next Action、再由确定性 Controller 审核 | M44 已确认方案 A，首版 next-action 完全确定性，decision model calls/tokens 固定为 0；这不代表永久排除模型 proposal。只有 required paraphrase 集形成稳定且不可接受的 deterministic clarification 失败簇，才能另立 module plan 评估结构化 proposal adapter；届时必须保留 closed-world Action allowlist、deterministic validator、Budget/ACL/outbound/duplicate/no-progress 硬门，并重新取得 decision purpose、数据类别和真实 E2E 的用户授权。不得仅因模型看起来更灵活就重开，也不得把它算作 M44 未完成项 | Phase 4B 后续质量候选 |
| P2     | G4 typed comparison completion 是“只消费服务端 metric_comparison requirement + 已验证 SQL rows”的窄合同 | 不扩成任意公式/required-output 平台：多期趋势、任意公式、自然语言自由计算、通用 required-output DSL 均不在授权内；只有用户确认新合同并另立 plan 才能扩展 | Phase 4B 后续质量候选 |
| P2     | `procedure_boundary_v1`只证明forward context值得补取，不证明后续正文一定改善最终答案 | M46已在experimental Subgraph中保留trigger identity、ACL/同文档/budget/stop，并用historical paired review发现总体no-go；未来重开仍不得全局开启或把Evidence gain当answer correctness，必须形成新candidate与可比证据 | Phase 4B 后续质量候选 |

M29–M40 的能力缺口：

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
| 最终 deterministic repair 真实路径仍未触发 | 最终 Probe 的初始 SQL 已是合法 MySQL，故没有 repair action；这不证明 repair 失败，也不能充当真实成功证据 | 保留 deterministic snapshot/reuse/provider=0 tests；禁止故意制造无效 SQL。只有以后自然出现 typed dialect failure 时才能补真实证据，不以此单独重复调用。 |
| Enterprise semantic 依赖项目外 profile、DashScope embedding 与 Milvus | Docker 未启动、snapshot identity 漂移或 provider 不可用时 RAG 会明确 unavailable；启动加载/核验约 10 秒，当前单锁优先保证共享 client 安全而非吞吐 | 启动前按 `runbook-rag.md` 执行 preflight；应用不自动启动 Docker、不降级 lexical；用 `/health/rag` 判断 readiness，性能优化须另立候选与证据 |
| M46 Subgraph historical 泛化仍 no-go | v3虽清除value-shape失败并使26题answer-ready，但Evidence run mismatch与严格Composer输出合同仍使60题全部no-answer | 用户已确认轻量收口：Pipeline默认、Subgraph experimental、reserve sealed/not-run；未获新计划/候选/授权不得重跑。重开顺序与证据入口见仓库外`DevProbe-todo.md` |
