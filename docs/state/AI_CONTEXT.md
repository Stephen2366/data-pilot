# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，Text2sql 和 RAG 评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，RAG / 知识库事实见 `docs/state/rag-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

## 当前状态

| 项目         | 当前值                                      |
| ------------ | ------------------------------------------- |
| 阶段路线     | `docs/phase4b-roadmap.md`                   |
| 阶段参考     | `docs/phase4-reference.md`                  |
| 当前活动模块 | M50 / DataPilot Web 工作台技术收工完成       |
| 当前 plan    | `docs/notes/m50-plan.md`                     |
| 当前 notes   | `docs/notes/m50-notes.md`                    |
| 待决事项     | M50 无阻塞；下一模块尚未立项。Pipeline 默认、Subgraph experimental、qst_0431 质量边界与 reserve sealed/not-run 均不变 |
| 更新时间     | 2026-08-28                                   |

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
- Web：M50 默认本地产品壳为 `web/` 的 Next.js 16.3.3 + React 19 + TypeScript 6。浏览器只经同源薄 BFF 调 FastAPI，Zod 只校验页面消费的公开网络边界；Python/Pydantic 仍是唯一业务 authority。BFF timeout 默认 300s，task mutation 不自动 retry；timeout/abort/合同漂移按 unknown outcome 冻结并跨刷新保留现场，可由用户显式调用 owner-scoped 只读 task status 对账后采用服务端版本。客户端不能选择 model/corpus/RAG strategy，sessionStorage 只保存最近 8 轮 validated 公开 snapshot、role、runtime family 与最小恢复投影。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- M50 演示数据库：独立可重建 `datapilot_demo`，只允许显式确认 prepare，固定 0005 + Phase 4B profile（7/8 月 120000/180000）；不修改 `.env` 或 reset/reseed `datapilot_dev`。最终 synthetic task rows 0/0。启动与 preflight 见 `runbook.md`。
- Phase 4B seed：默认仍为 legacy `sqlite_deterministic_seed`；只有显式选择 `profile_alias="phase4b"` 才加载 content-bound B0 profile，生成 7/8 月 oracle。不得把两个 profile 的 artifact 混算。
- NL2SQL：普通 API 默认走 Harness 内的 `new_text2sql` 深 Tool（Schema Retrieval → QueryPlan → SQL Guard）；显式 `force_new_pipeline=false` 只选择 adapter 内部 legacy baseline，不能绕过顶层 Harness。
- SQL dialect repair：服务端默认 `deterministic_ast`，只处理 typed MySQL month DATE_TRUNC；私有复用首次可信 QueryPlan/candidate/issue，不重新调用 QueryPlan provider，结果重走 validator、fidelity、Guard 与执行。客户端不能选策略，LLM repair 仅为非默认候选。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1；本机 `.env` 已覆盖 `LLM_TIMEOUT_SECONDS=120`（2026-08-23，Qwen 比较类 QueryPlan 实测 43~105s，45s 会误杀），config 默认仍为 45。
- Schema Retrieval 默认：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅在显式实验中开启。
- Knowledge/RAG 分账：22 条业务 release 默认 `knowledge-deterministic-lexical-v1`；EnterpriseRAG-Bench 产品 API/external Eval 默认 `knowledge-enterprise-milvus-semantic-v1`，lexical 只允许显式历史 baseline；两者与 Text2SQL Schema Retrieval 均为独立链路。
- Harness：LangGraph `>=1.1.2,<2`；SQL/RAG 单路仍为 `route → tool → controller`、各至多一个深 Tool。M38 canonical Hybrid 为 `route → hybrid_sql_tool → hybrid_rag_tool → controller`，SQL/RAG 都 required、各至多一次、总计至多两个深 Tool；Router 只签发薄计划，RAG branch 只执行 retrieval + Gate，不生成子答案。未知 Hybrid 继续保守停止；M37 follow-up 仍只覆盖 SQL/RAG。
- Thread checkpoint：方案 A，应用持有 `inprocess-bounded-thread-v2`，state `m37-thread-v2`，默认 TTL `900s`（`THREAD_CHECKPOINT_TTL_SECONDS`）。除 M36 一次结构化恢复外，成功 SQL/RAG 可在显式开启后签发一次 closed-world follow-up；owner 绑定 trusted caller + tenant/active role，同 version 原子单 claim，重启/多 worker 不恢复或共享。checkpoint 不保存旧 answer/rows/正文/citation。
- Agent task boundary：产品默认 `phase4b-mysql-task-boundary-v1`，以 MySQL checkpoint + typed event ledger 持久化已提交 TaskState v2 与 bounded Context Window/Compact；owner/tenant/active role、expected version、single-use claim token 与 TTL 共同参与数据库 CAS。state/context/event 同 claim 原子提交，active TTL 默认 900s，terminal/clear/expiry 立即 scrub，24h tombstone 后 bounded purge；claimed crash 保守停止、不自动重放 Tool。memory backend 仅允许 `APP_ENV=test` 显式使用。payload 不保存完整 rows、文档正文、Prompt、凭据、Thought 或 Graph/RAG program counter；M49 仅在 Context/Compact v2 中新增一份最近完成结果的有界摘要（最多 8 KiB、16 个 Evidence ID），用于重启后零 Tool/零模型解释既有结果。`datapilot_dev` 已于 M49 正常迁移到 0005，未 reset/reseed，默认演示 schema 前置已闭合。
- Task Context Compact：当前写入 `phase4b-task-context-window-v2` + `phase4b-task-compact-v2`，旧 v1 仍严格可读；typed Compact 继续使用 deterministic facts，不使用 LLM summary。latest result digest 是独立、有界的最近结果展示材料，不是 Evidence/ACL/业务 authority，也不保存任意 SQL、原始文档正文或无界 rows。下一个 accepted turn 前按 5 committed turns 或 candidate node Context 75% token budget 双触发；只保留最近 2 个 raw user turns、每条 2048 UTF-8 bytes，独立总 payload 上限 65536 bytes。source gap、schema/identity/索引列漂移在 Tool 前失败关闭；switch 的新 task 从独立 T1/version=1 Context lineage 起步。
- B2 Agent Loop：只有 accepted task turn 进入独立 `phase4b-agent-loop-v1`，由确定性 Controller 选择 closed-world Evidence action；父预算最多 3 次 Evidence action/deep Tool、1 次 Knowledge、每 requirement 1 次 repair、6 次 model call、24000 observed tokens。clarification/cancel/clear/pre-rejection 为零 Loop，legacy 非 task Harness 拓扑不变。
- B4 RAG acquisition：服务端保留 Pipeline/Subgraph 两个 adapter，Pipeline 仍为产品默认与显式 baseline，Subgraph 仅 server-controlled experimental；Subgraph 在一次父级 Knowledge action内执行 bounded initial retrieval → Observation → eligible rewrite/expansion/stop → Evidence merge/reauthorize，并投影独立 child ledger。external recovery 现与 Pipeline 共用 Enterprise SQLite context loader，metadata identity 水化后必须保持 key/revision/content hash/anchor、正文非空且坐标有效；缺依赖或漂移失败关闭。historical candidate `ab66f20d...2f78` 仍 no-go；rollout contract `ebb06f82...f164` 的 `quality_claim=not_established`、无自动 fallback、reserve sealed/not-run 均不变。
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
| 2026-08-28 | M50 用户实测小修：两轮月份比较因 150s BFF 先超时、服务端稍后提交及派生指标被错误下推为嵌套聚合而造成 unknown/version 分叉。现改为 300s、显式只读 task status 恢复、unknown 跨刷新，以及仅对 Agent comparison 启用 month+base metric 计划收敛；`M50-UXR-P1` 双轮真实链 4 calls/16029 tokens，通过 120000/180000/60000/50%、UI v3 与 cleanup 0/0。该 Probe 仅证明固定场景，不登记 Formal Eval。 |
| 2026-08-28 | M50 Web 工作台技术收工：Next/React/TypeScript + thin BFF 真实消费 FastAPI task/legacy 两个 family，展示 SQL/Vega/citation/Hybrid 与公开 TaskDelta/Action/Budget/Termination/Context Inspector。P1 经网络与错库修正后 120000 oracle 通过；首次 P2 的问法失败和 9/8 attempts 控制错误永久保留，用户确认 P2R 后新 lineage 6 calls/23009 tokens 完成 120000/180000/60000/50% + Document Evidence/citation；P3 两拒绝+clear 0 provider/0 deep invocation、cleanup 0/0。前端 35 unit + 12 Playwright、Python 聚焦 245、全仓 681 均通过；只证明固定本地展示链，不是 Formal Eval 或质量/生产结论。 |
| 2026-08-27 | Phase 4B 整体审计双 Probe：P1 r9 在含未提交 RAG 修复的当前工作区真实贯通 T1→T6（12 calls/52709 tokens、Compact/重启/cleanup 0/0）；P2 两负例（不存在版本→`task_version_conflict`、角色漂移→`task_unavailable`）在真实 lineage 上 0 provider 成立；P2 attempt 1 另暴露 T2 的 Qwen `sql_generation` 120s 网络超时（retry0 下安全失败关闭，非产品缺陷）。审计发现与收口建议见 `docs/notes/phase4b-audit-notes.md`（含：默认 `datapilot_dev` 仍无 Phase 4B 7/8 月种子、README 多节过期、RAG 修复未提交、tombstone purge 无 scheduler、演示链对 Qwen 延迟敏感）。 |
| 2026-08-27 | M49 收工后 RAG 重验与修复：Business happy/no-candidate、Enterprise Pipeline qst_0386 通过；external Subgraph qst_0431 首次暴露 metadata-only recovery 漏水化，修复后 R4R `context_characters=5425`、answer complete、漏斗 `3→3→3→2`，但 required `11/1/0` 仍因 cited-gold 质量失败。随后真实 Qwen/MySQL/business Subgraph Hybrid 单 turn 通过，2 calls/9696 tokens、task cleanup 0/0。campaign 总计 9 attempts / 15502 observed chat tokens；不是 Formal Eval/基线/开发期 Probe。 |
| 2026-08-27 | M49 技术收工：最终聚焦 `35 passed`、deterministic evidence `6 passed`；全仓前台收集 677 项后后台同次 `677 passed, 1 warning in 595.25s`，warning 仅既有 Starlette/httpx deprecation。compileall、rehearsal 重签、diff check、Alembic current/check 均通过。Phase 4B 固定 Demo 技术链可收口，但不外推为质量或生产能力。 |
| 2026-08-27 | M49-P2 r8 最终 `continue`：真实 Qwen + Text2SQL + SQL Guard + MySQL + business Subgraph 同一 task 完成 T1～T5；新进程恢复并在 T6 提交 Compact v2、零 Graph/Tool/provider 复用 latest result digest；安全负例在 deep runtime/provider 前统一 `task_unavailable`。总计 12 calls / 51013 observed tokens、cleanup `0/0`。deterministic evidence 6/6，Scenario v7=`9b133cdf...ed080`、assurance v2=`bc495840...e36bf` 均 completed；只证明当前固定演示链技术闭环，不外推质量或生产能力。 |
| 2026-08-27 | M49-P1 最终 `continue`：真实 Qwen/Text2SQL/MySQL T1/T2 均 complete，T2 完整重述正确替换为唯一 comparison requirement；自然出现 `DATE_TRUNC` failure 后 deterministic repair 成功，得到 120000/180000/60000/50%，4 calls / 13075 tokens，cleanup `0/0`。同次还修复了 Controller 把 failure+repair success 误判为 observation missing 的断点；离线同源复核新增 provider/DB writes=`0/0`。`datapilot_dev` 已从 0003 正常升级到 0005，业务关键计数不变。 |
| 2026-08-27 | M48/B6技术收工：真实MySQL P1/P2最终均`continue`，Agent synthetic checkpoint/event清理为`0/0`，provider/tokens=`0/0`；同源版本链`1→3→5→7→9→11`，Compact `d7a5fcf3...d098`覆盖T1..T5并跨进程续接。Scenario v6=`53dde955...beaf`、Phase 4B assurance=`4084e428...a22b`，B0～B6 technical available；全仓`662 passed, 1 warning`。Pipeline默认/Subgraph experimental、quality未声明、reserve sealed/not-run与生产边界不变。 |
| 2026-08-26 | M47/B5技术收工：真实MySQL P1/P2均`continue`且隔离库synthetic行最终清零；restart-resume `version 1→3`、多worker单胜者、旧版本/role/tenant/claimed crash/clear/expiry/purge边界闭合，provider/tokens均0。Scenario v5 6/6，identity=`c1ad1663...000af`。全仓640项为639 pass+1个旧表集合断言失败，修正后该项独立1 pass；当前640项均有通过证据，warning仅既有Starlette/httpx deprecation。 |
| 2026-08-26 | M46技术收工：注释审计23文件/257符号、缺失0；聚焦`57 passed`，兼容修复聚焦`26 passed`。全仓首次发现并修复M33/M34 Pipeline兼容回归；第二次625项通过，唯一M31临时目录`os.replace` WinError5项独立`1 passed`，故当前626项均有通过证据。M46 rollout identity=`ebb06f82...f164`，默认/experimental/reserve边界不变。 |
| 2026-08-26 | M46最后一次 historical v3 `m46-historical-paired-20260826-164511` 两臂各60 completed，value-shape `19→0`、child projection 60/60、answer-ready `12→26`；rollout评审将后续优化收敛到Evidence run identity、formation grounding和Composer structured output。用户已确认experimental rollout收口：当前candidate不晋级、不解封reserve、不再追加同类historical；Pipeline默认/Subgraph experimental，未来修复包在仓库外todo。 |
| 2026-08-25 | M45-H/P5 最终 passed：显式默认关闭的 `procedure_boundary_v1` 在 qst_0431 initial coverage 显示完整、且 SQLite authority 证明存在 forward unit 时，准入 expansion 并新增 2 条同物理文档后续 Evidence；P5 retrieval/embedding/chat/Composer=0。v4 review `949a3b03...fbb4`=`go_for_M46`，两张 action card completed，累计 provider attempts 仍为 11；全仓 `582 passed, 1 warning`。M45/B3 技术完成，但它仍是 diagnostic admission，不是产品 RAG Subgraph。 |
| 2026-08-25 | M45-P4R/v3 最终 no-go：qst_0461 用 P4 immutable proposal 离线重放后 expansion passed；qst_0431 唯一 Qwen revalidation transport 成功，但本地 coverage validator 判为 `proposal_no_unsupported_requirement`，未触发 action。runner 未 catch 异常导致 raw/token usage 丢失，故 tokens=`unobserved`，严禁估算为 0 或补发。recovered safe `6426219b...a949`，v3 review `8fb3cfad...14e4`，累计 provider attempts=`8 embedding + 3 chat = 11`；M45/B3 未完成、M46 blocked。 |
| 2026-08-25 | M45-P4 受控 A2 真实 Probe failed：qst_0431 proposal schema 因 prompt 未声明 marker 数量上限被 validator 拒绝；qst_0461 正确提出 weekly schedule 缺口，但 literal phrase matcher 未命中语义等价 sibling，expansion 未准入。2 Qwen calls / 3877 tokens，零新 retrieval/embedding/Composer；累计 provider attempts=10。safe `a374f0c0...cfac`，v2 review `ce0d7615...40af`=`review_required/no_go`；不自动重跑，M46 blocked。 |
| 2026-08-25 | M45 Live Dev Probe：P1 business rewrite passed；P2 Round 2 找到目标文档但 coverage 未闭合；P2C immediate neighbor failed；用户确认的 sibling v2 在 P2D passed；P3 的 qst_0431/qst_0461 均因 deterministic question-derived coverage 误判为完整而只允许 stop，未执行 recovery。campaign 共 8 embedding provider attempts、零 chat/model/Composer、零 observed chat tokens；review artifact `33efaf8f...9ea9`，结论 `review_required/no_go`，M46 不得开工。 |
| 2026-08-24 | `M44-PFIX-G4-1` 真实 canonical T1→T2 passed：4 calls / 15762 tokens；T2 same-source Answer/rows/Trace 给出 120000/180000/60000/50%，completion identity `41b577e...ecac9`，raw DB marker=0，数据库 rollback。初始 SQL 合法而未触发 repair，故 G3 repair real path 仍 inconclusive；不为展示 repair 重跑。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的必须删除或改写。

- (2026-08-24) M44A 仍是 B2 前置修复、不占 B milestone。business 小 catalog 与 external 180 题继续分账，120 held-out 保持停门；external 产品默认为 semantic，但历史 lexical artifact/正式 retrieval baseline 不改签，也没有证据宣称 semantic 质量更优。
- (2026-08-25) M45/B3最终以v4 `go_for_M46`完成，rewrite、bounded sibling expansion与procedure forward continuation两张action card已闭合；M46已消费这些diagnostic contracts并完成experimental产品Subgraph。M45的Evidence gain仍不能外推为答案正确率，最终默认/质量结论以M46 historical no-go与rollout为准。
- (2026-08-27) M46/B4 external recovery 的 metadata-only 正文水化接线已修复并由同题 R4R 证明可进入 Composer/citation 完成态；business Hybrid 也已再次真实贯通。qst_0431 仍未通过 cited-gold/精确事实质量 Gate，因此只能恢复“技术链可运行”，不能声称 Subgraph 质量胜出。Pipeline 默认、Subgraph experimental、无自动 fallback、reserve sealed/not-run 均不变。
- (2026-08-26) M47/B5技术收工已完成：产品 task boundary 已从进程内实现升级为 MySQL durable 默认，B5 的 restart、多worker/CAS、TTL/clear/tombstone/typed ledger 与安全失败已闭合；M37 thread checkpoint 仍是独立的进程内 legacy family，不因 B5 自动升级。
- (2026-08-27) M49 已修复自然 T2 requirement 合并、comparison/conditional dependency、跨 turn Evidence 复用与重启解释断点；Context/Compact v2 的 latest result digest 让 T6 可零 Graph/Tool/provider 解释最近完成结果，v1 继续可读。evidence-backed Scenario v7/assurance v2 已由真实 Probe、deterministic JUnit 和历史 durable negative-path artifact 独立签发 completed。Phase 4B 展示型 technical integration 可收口；仍不包含 RAG/LLM 质量提升、生产认证、性能/HA、外部 Tool exactly-once 或 sealed reserve 结论。
- (2026-08-28) M50 已把 Phase 4B 公开合同接成可操作的本地 Web 工作台；真实 Browser→BFF→FastAPI→Qwen/MySQL/business Knowledge→Response/Trace→UI 主故事与安全负路径均闭合。前端是 presentation/transport seam，不新增 Agent 里程碑，也不改变 Pipeline/Subgraph、数据库默认世界或质量结论。下一模块未预定；公网部署/auth、streaming、MCP 或质量优化必须分别立项。

## 防遗忘能力账本

> 记录已经存在、但容易被“当前窄实现已完成”掩盖的能力缺口和重开门。优先级表示防遗忘/复核顺序，不自动决定下一模块；下一模块仍须按 roadmap、最新失败证据和独立 plan 裁决。原方案字母只在对应 module plan 内有效，禁止脱离具体方案写“以后从 A 升级 B”。

M41 及以后的能力缺口：

| 优先级 | 能力缺口                                                     | 当前结论与硬性重开门                                         | 路线归属              |
| ------ | ------------------------------------------------------------ | ------------------------------------------------------------ | --------------------- |
| P2     | M44 G44-2 未选方案 B：由结构化模型提出 next Action、再由确定性 Controller 审核 | M44 已确认方案 A，首版 next-action 完全确定性，decision model calls/tokens 固定为 0；这不代表永久排除模型 proposal。只有 required paraphrase 集形成稳定且不可接受的 deterministic clarification 失败簇，才能另立 module plan 评估结构化 proposal adapter；届时必须保留 closed-world Action allowlist、deterministic validator、Budget/ACL/outbound/duplicate/no-progress 硬门，并重新取得 decision purpose、数据类别和真实 E2E 的用户授权。不得仅因模型看起来更灵活就重开，也不得把它算作 M44 未完成项 | Phase 4B 后续质量候选 |
| P2     | M49 G49-1 未选方案 C：让大模型判断自然语言 turn 并提出结构化 TaskDelta | 方案 C 的潜在收益是理解力更强，但会增加成本、延迟和不确定性。M49 已确认方案 A，以 typed intent/constraint 完整性做确定性替换判断；只有代表性 paraphrase 回归与真实 Probe 形成稳定、不可接受且缺乏明确确定性修复方向的理解失败簇，才能另立 module plan 评估 LLM Turn Understanding。届时必须新增独立 model purpose/outbound 授权，并保留 TaskDelta closed-world schema、确定性 validator、权限/预算/失败关闭和真实 E2E Gate；不得把模型输出直接写入 TaskState | Phase 4B 后续质量候选 |
| P2     | G4 typed comparison completion 是“只消费服务端 metric_comparison requirement + 已验证 SQL rows”的窄合同 | 不扩成任意公式/required-output 平台：多期趋势、任意公式、自然语言自由计算、通用 required-output DSL 均不在授权内；只有用户确认新合同并另立 plan 才能扩展 | Phase 4B 后续质量候选 |
| P2     | `procedure_boundary_v1`只证明forward context值得补取，不证明后续正文一定改善最终答案 | M46已在experimental Subgraph中保留trigger identity、ACL/同文档/budget/stop，并用historical paired review发现总体no-go；未来重开仍不得全局开启或把Evidence gain当answer correctness，必须形成新candidate与可比证据 | Phase 4B 后续质量候选 |

M29–M40 的能力缺口：

| 优先级 | 能力缺口 | 当前结论与硬性重开门 | 路线归属 |
|---|---|---|---|
| P0 | M34 已证实 lexical 漏召回、selected budget / multi-document context packing 和 Composer support 拒绝会严重限制答案质量 | M44A 按用户确认把现有 semantic snapshot 接为 Enterprise 产品默认，但单题 C6 不构成质量胜出证据；M39 的 B3/B4 action-level Evidence 与 review-point 门不变，不能借默认切换跳过 diagnostic campaign | Phase 4B B3/B4 |
| P1 | M38 方案 A 只冻结正式本地确定性 Hybrid Synthesizer；远程方案 B 与双 adapter 方案 C 未实施 | B 的重开门：受控 operators 对真实开放 Hybrid 问法形成稳定失败簇，且用户明确批准 receiver、`hybrid_synthesis` 用途、question/conditions、SQL safe result、Document Evidence/identity 的数据类别与字段，并提供真实 provider 精确运行授权。C 的重开门：除上述授权外，还需有未污染 Hybrid held-out、多轮可比预算和明确 A/B 决策价值；禁止仅为“代码里有两个 adapter”扩大 M38。无稳定净收益时 A 继续作为默认与 fallback | P5 后续质量/出站条件项 |
| P1 | 当前只有 demo/test caller resolver，生产认证尚未建设 | 出现非本地部署、真实用户/tenant、JWT/OAuth/SSO 或企业目录需求时，必须在现有 `CallerResolver` seam 接正式认证 adapter；“所有环境手工注入 resolver”不等于生产认证 | Phase 4 后续部署门 |
| P2 | M35/M38 deterministic Router 只覆盖 closed-world SQL/RAG 和两类 canonical Hybrid operator | 先建立开放问法/混合意图 decision set 并形成稳定失败簇，再比较规则扩充、受控模型 fallback 或远程 Router；不得以“LLM 更完善”为由无 Eval 切换 | P3/P5 后续质量 |

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
| M46 Subgraph candidate未达到rollout晋级门 | v3已清除value-shape问题并使26题answer-ready；后续优化边界已定位到Evidence run identity、formation grounding与Composer structured output | 用户已确认experimental rollout收口：Pipeline默认、Subgraph experimental、reserve sealed/not-run；未获新计划/候选/授权不得重跑。重开顺序与证据入口见仓库外`DevProbe-todo.md` |
