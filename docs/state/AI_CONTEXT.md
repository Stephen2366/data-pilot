# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，Text2sql 和 RAG 评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，RAG / 知识库事实见 `docs/state/rag-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

## 当前状态

| 项目         | 当前值                                                       |
| ------------ | ------------------------------------------------------------ |
| 阶段路线     | `docs/phase4-roadmap.md`                                     |
| 阶段参考     | `docs/phase4-reference.md`                                   |
| 当前活动模块 | M39 P6 RAG Subgraph 入场证据审计技术收工完成，待人工检查（2026-08-17） |
| 当前 plan    | `docs/notes/m39-plan.md`                                     |
| 当前 notes   | `docs/notes/m39-notes.md`                                    |
| 待决事项     | 用户已选 M39 G-M39-1 方案 A；严格 no-go 已证实，P6 不实现 Subgraph，后续另按 P7 规划 |
| 更新时间     | 2026-08-17                                                   |

## 必读规则

- 开始开发、排障或验证前先读本文。
- 运行命令、模型、LangFuse 或 eval 前必须读 `docs/state/runbook.md`。
- 解释 eval 数字、模型 A/B、失败归因或分母时必须读 `docs/state/eval-baselines.md`。
- 涉及 SQL/字段/指标/oracle 时读 `database-current-state.md`。
- 涉及知识原件、active release、外部 corpus、Knowledge Tool、RAG Eval 或 M34 语料状态时读 `rag-current-state.md`。
- 涉及 Milvus/embedding/Schema Retrieval 时读 `schema-retrieval-milvus-embedding.md`。
- 写入 changelog、记录小修或追溯设计原因、历史实验时，先读 `docs/state/CHANGELOG_INDEX.md`，再进入索引指定的 Phase 文件。
- 前台等待超时不等于真实 Eval 已结束：按 runbook 用同一 `run_id` 检查 manifest、checkpoint、artifact；不得擅自换 ID 重跑。
- 用户明确说执行某个 eval 时，按 runbook 的“一次精确运行授权”直接执行一次；不重复询问授权，也不扩大范围或切换默认配置。
- 默认模型、embedding、正式 case、安全策略、数据库结构等长期选择，必须先说明方案并等待用户确认。

## 当前默认值

- 后端：FastAPI + Pydantic；`/api/query` 统一调用 M37 turn seam。普通/accepted initial、resume 或 follow-up 恰好一次 M35 Graph，thread lifecycle 前置拒绝为零次；响应、JSONL Trace 与 Eval 都从同一 turn/result/lifecycle/validity 事实投影。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- NL2SQL：普通 API 默认走 Harness 内的 `new_text2sql` 深 Tool（Schema Retrieval → QueryPlan → SQL Guard）；显式 `force_new_pipeline=false` 只选择 adapter 内部 legacy baseline，不能绕过顶层 Harness。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1。
- Schema Retrieval 默认：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅在显式实验中开启。
- 业务 Knowledge Retrieval 默认：`knowledge-deterministic-lexical-v1`。它与 Text2SQL Schema Retrieval 是两套独立检索链路；这不代表语义最优，未来替换仍需独立候选 identity、held-out 失败证据、A/B 与用户确认。
- Harness：LangGraph `>=1.1.2,<2`；SQL/RAG 单路仍为 `route → tool → controller`、各至多一个深 Tool。M38 canonical Hybrid 为 `route → hybrid_sql_tool → hybrid_rag_tool → controller`，SQL/RAG 都 required、各至多一次、总计至多两个深 Tool；Router 只签发薄计划，RAG branch 只执行 retrieval + Gate，不生成子答案。未知 Hybrid 继续保守停止；M37 follow-up 仍只覆盖 SQL/RAG。
- Thread checkpoint：方案 A，应用持有 `inprocess-bounded-thread-v2`，state `m37-thread-v2`，默认 TTL `900s`（`THREAD_CHECKPOINT_TTL_SECONDS`）。除 M36 一次结构化恢复外，成功 SQL/RAG 可在显式开启后签发一次 closed-world follow-up；owner 绑定 trusted caller + tenant/active role，同 version 原子单 claim，重启/多 worker 不恢复或共享。checkpoint 不保存旧 answer/rows/正文/citation。
- Evidence follow-up：SQL 没有可靠业务 snapshot，永远重查；EnterpriseRAG-Bench external 永远重检索；只有业务 22-entry release 的同 requirement 解释动作可按当前 active authority/revision/content/anchor 重新加载并重新授权，随后签发新 run Evidence/ledger/citation。requirement/identity 变化重检索一次，ACL/用途拒绝零 retrieval 停止。
- Caller：`local/demo/test` 使用明确标记的 fixture resolver，请求 `user_role` 只能选择 resolver 已解析的 role；其他环境没有 authenticated resolver 时在 Tool 前失败关闭。生产认证尚未建设。
- M34 external benchmark：项目外 EnterpriseRAG-Bench v1.0.0 独立 profile；当前 external adapter 保持 `enterprise-lexical`，`enterprise-unit-paragraph-2400-v1` 无 overlap；semantic candidate 不胜 lexical，未激活。业务 22 条 active release 不变。
- LangFuse 默认关闭，JSONL trace 为主；SQL 安全为只读 AST + RBAC + 敏感字段策略。
- 现有 Text2SQL chat/schema embedding 出站在 transport 前按 `phase4-outbound-v1` 精确登记；所有新增 Knowledge/RAG 数据类别与节点用途继续默认拒绝，LangFuse Cloud 未获放行。

## 最近验证事实

> 只保留会影响当前决策的最新证据，不按模块流水账累积。

| 日期 | 事实 |
|---|---|
| 2026-08-17 | M39 完成 P6 只读 readiness audit：六份冻结 M34 输入须同时匹配 SHA-256、identity、split、retrieval runtime 与 Composer identity；只分类 60 dev，120 held-out 仅作闭合核验，零 provider 调用。结果为 retrieval `11`、context/packing `13`、Composer `10`、provider unavailable `2`、not classifiable `24`；“Observation 驱动新增 Evidence 动作”与“可比额外预算”均未被既有证据证明，故严格 `no_go`，external lexical 默认不变。全仓 deterministic pytest `441 passed, 3 skipped, 1 warning in 517.57s`。 |
| 2026-08-17 | M38 完成 P5 保守 Hybrid 双 Evidence 基线：本地确定性 Synthesizer、双 required branch、typed SQL/Document Evidence、safe partial/conflict/合成失败降级、API/Trace 投影和 `phase4-harness-hybrid-v1`（5 Scenario / 25 required）。全仓 deterministic pytest `436 passed, 3 skipped, 1 warning in 599.87s`，compileall/diff check 通过；未运行真实 Hybrid LLM、远程 embedding/Milvus、LangFuse Cloud 或 M34 external 大评测。 |
| 2026-08-17 | M37 完成 P4 的一次有界 follow-up + Evidence validity/重新取证切片：`phase4-harness-followup-v1` 覆盖 10 sequences / 22 turn evidence / 50 required，50/50 通过，identity `1185edf0...634b25`。全仓 deterministic pytest `427 passed, 3 skipped, 1 warning in 509.36s`，compileall/diff check 通过；未运行真实 LLM、远程 embedding/Milvus、LangFuse Cloud 或 M34 external 大评测。 |
| 2026-08-16 | M36 完成 P4/G5 首个有界恢复切片：应用持有 versioned in-process checkpoint，支持 pending→一次 resume/clear、owner+tenant/active-role、TTL/state version、原子单 claim、budget stop 和安全 Trace；`phase4-harness-turn-v1` 覆盖 8 组 sequence。全仓 deterministic pytest `416 passed, 1 warning in 594.12s`，compileall/diff check 通过；未运行真实 LLM/远程 Eval。 |
| 2026-08-16 | SQL 四轴映射按用户确认的方案 A 收口：QueryPlan output-projection mismatch 是执行前确定性合同拒绝，保持 `completed / no_answer / blocked`；LLM JSON/SQL 解析失败是 `external_unavailable / no_answer / passed`，不写 `blocked_reason`。SQL Guard、语义拒绝和 driver/pipeline 技术错误各有独立分支。 |
| 2026-08-16 | 用户已将 M34 EnterpriseRAG-Bench retrieval 与 Answer/Citation 结果登记为正式长期 RAG 基线；lexical 在 dev/held-out 均胜当前 semantic candidate，external 默认不切换。完整身份、数字、轻量证据清单与解释边界见 `eval-baselines.md`，不得与 22 条业务知识回归或 M27 Text2SQL 混算。 |
| 2026-08-10 | Text2SQL canonical contract 为 `m27-v3`，并使用 run-scoped Schema vector index；旧 v1/v2 artifact 只作历史解释，当前尚无由用户指定的 v3 真实 LLM 长期基线。完整合同、运行身份和旧实验数字见 `eval-baselines.md`。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的“下一步做……”必须删除或改写。

- (2026-08-17) M37 单独不等于 P4，但 M36 + M37 已共同完成 roadmap 定义的 P4 最小可验收基线；不宣称通用多轮。第二次追问、长历史 compact 和持久 checkpoint 不是当前 P4 硬门；跨 route/跨 Tool 补证据由 M38 的 P5 Hybrid 正式承接。M37“窄 B”仍是正式边界，不得退化为直接复用旧答案或默认扩到 external。
- (2026-08-17) M38 已按 P5 口径完成保守 Hybrid 纵向基线：方案 A 的本地确定性 Synthesizer 是正式默认与长期 fallback；SQL/RAG 默认 required，不触发 G6 optional 放宽，不新增 Hybrid 数据出站。P5 不等于开放式跨来源研究 Agent。
- (2026-08-17) M39 已按用户确认的方案 A 完成 P6 入场审计并严格 no-go：固定 Pipeline 的 retrieval/context/Composer/provider 失败不能替代“Observation → 允许动作 → 新 Evidence”的实证，且没有父子预算可比较。P6 因审计闭环完成，不实现 RAG Subgraph、不切 lexical 默认；若将来重开，须有未污染 dev 对具体允许动作的新增 Evidence 证据、冻结的 held-out decision protocol 与可比额外预算，随后另立 M40。下一能力入口按 roadmap 的 P7 收口另行规划。
- (2026-08-10) Text2SQL 的确定性收尾问题已修复；若未来重跑 Text2SQL，必须使用 `m27-v3` 新序列，并完整记录 collection、embedding、corpus 与 run-scoped index identity。现有 v1/v2 数字只作历史解释。
- (2026-08-09) 默认保持 Qwen `qwen3.7-plus` + inmemory deterministic + weighted；任何切换需要单变量重复证据与用户确认。

## 防遗忘能力账本（M29–M38）

> 记录已经存在、但容易被“当前窄实现已完成”掩盖的能力缺口和重开门。优先级表示防遗忘/复核顺序，不自动决定下一模块；下一模块仍须按 roadmap、最新失败证据和独立 plan 裁决。原方案字母只在对应 module plan 内有效，禁止脱离具体方案写“以后从 A 升级 B”。

| 优先级 | 能力缺口 | 当前结论与硬性重开门 | 路线归属 |
|---|---|---|---|
| P0 | M34 已证实 lexical 漏召回、selected budget / multi-document context packing 和 Composer support 拒绝会严重限制答案质量 | M39 已以冻结 M34 证据完成 P6 strict no-go：没有 Observation 驱动新增 Evidence 的允许动作和可比额外预算。semantic candidate 已在同 split 输给 lexical，禁止直接切换；单变量 Pipeline 候选须独立计划，Subgraph 只有满足新 dev/held-out/budget 重开门后才可进入 M40 | P6 已闭环；质量候选 / P7 后续 |
| P1 | M38 方案 A 只冻结正式本地确定性 Hybrid Synthesizer；远程方案 B 与双 adapter 方案 C 未实施 | B 的重开门：受控 operators 对真实开放 Hybrid 问法形成稳定失败簇，且用户明确批准 receiver、`hybrid_synthesis` 用途、question/conditions、SQL safe result、Document Evidence/identity 的数据类别与字段，并提供真实 provider 精确运行授权。C 的重开门：除上述授权外，还需有未污染 Hybrid held-out、多轮可比预算和明确 A/B 决策价值；禁止仅为“代码里有两个 adapter”扩大 M38。无稳定净收益时 A 继续作为默认与 fallback | P5 后续质量/出站条件项 |
| P1 | 当前只有 demo/test caller resolver，生产认证尚未建设 | 出现非本地部署、真实用户/tenant、JWT/OAuth/SSO 或企业目录需求时，必须在现有 `CallerResolver` seam 接正式认证 adapter；“所有环境手工注入 resolver”不等于生产认证 | Phase 4 后续部署门 |
| P2 | M35/M38 deterministic Router 只覆盖 closed-world SQL/RAG 和两类 canonical Hybrid operator | 先建立开放问法/混合意图 decision set 并形成稳定失败簇，再比较规则扩充、受控模型 fallback 或远程 Router；不得以“LLM 更完善”为由无 Eval 切换 | P3/P5 后续质量 |
| P3 | `knowledge_docs` 有损 legacy 表仍保留 | 出现新 runtime consumer、知识后台/多实例发布、从旧表恢复授权/catalog，或双事实源风险时，必须正式设计数据库 projection 或删除 legacy 表；禁止继续追加字段把它伪装成 authority | 数据治理条件项 |
| 条件项 | M37 checkpoint 仍为进程内，重启/多 worker 不恢复且 tombstone 不清扫 | 只有重启恢复或多 worker 会话成为 required Scenario 时才设计持久 checkpoint；LangGraph `InMemorySaver` 仍是内存态，不得把更换框架内存实现冒充持久化升级。清扫策略按容量证据单独触发 | P4/部署条件项 |

## 已知的坑（活跃列表）

> 只允许活跃问题；已经解决的内容移入 changelog。

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 的模型注册可能触发循环导入 | 聚合导入模型时可能失败 | API/工具层沿用 `app.db.base` 暴露路径；重构时再拆 base class。 |
| 旧 Milvus collection `datapilot_schema_docs` 有重复灌入污染 | 历史 A/B 不可信 | 新 eval 用唯一/clean collection；校验 row count、dimension、schema docs hash。 |
| QueryPlan 可能过宽，或 SQL 与计划不一致 | contract pass 不等于答案正确 | 保持保守 AST 边界，用 output/result/trace 共同定位。 |
| 生产认证尚未建设；请求体 `user_role` 仍是客户端自报字符串 | 不能作为文档 ACL、生产身份或 thread owner 的独立信任来源 | M35–M37 让 `/api/query` 在 local/demo/test 通过显式 fixture resolver 解析 caller，role 只能选择 resolved role；thread 再绑定 owner+tenant/active role，其他环境缺 authenticated resolver 时 Tool 前失败关闭。 |
| M37 checkpoint 仅在单进程内存，resolved/cleared tombstone 暂不清扫 | 重启或多 worker 时 pending/follow-up-ready 不可恢复；长时间大量创建 thread 会增长进程内容器 | 当前明确返回 `conversation_unavailable`，不伪装持久会话；只有重启恢复成为 required Scenario 才重开存储决策，清扫策略按真实容量证据另行规划。 |
| M35/M38 deterministic Router 对开放问法较窄 | 未登记 Hybrid、开放问法会保守停止；当前只证明两类 canonical operator，不代表通用意图理解 | 保持可注入 seam；只有真实失败簇、受控 Eval 和出站决策成立后，才规划规则扩张、远程 Router 或 Synthesizer。 |
| `knowledge_docs` 物理表仍存在且是有损 legacy 投影 | 新调用者若绕过 source-backed catalog 读取旧表，会丢失 revision/authority/identity/完整 ACL，并重新制造旁路 | Text2SQL 已从 Schema/prompt/RBAC 双重隔离；seed 只从 staged catalog 派生，旧表不得作为 authority/runtime catalog。 |
| M34 full Answer Eval 的 complete 不等于正确 | lexical 漏召回、semantic 与多文档题会产生“有 citation 但答非所问”；全题 all-gold cited 仅 44.44%，multi-document 5.26%，semantic 28.85% | 后续先按失败簇改善 gold coverage/context packing；不得用 complete rate 代替 correctness，也不得未经新计划重跑大规模 provider。 |
| Active Knowledge release 损坏时不会自动 fallback；当前虽有 previous，但旧 11-entry release 已不等于当前 authority | 自动复活旧正文可能绕过撤销/ACL，或丢失新增内容 | 启动失败关闭；显式 rollback 仍必须重新通过当前 authority/revision/policy 校验。 |
| LangFuse Cloud 重新启用前需统一 question/answer 脱敏（M28 F7） | RAG/Hybrid 若启用 Cloud 会外传完整问答 | LangFuse 默认关闭且 M31 outbound 未放行 Cloud；重新启用前先做 allowlist/redaction 策略和用户决策。 |

## 历史入口

- 完整改动、实验记录、旧合同取舍入口：`docs/state/CHANGELOG_INDEX.md`。
- 历史 eval 数字：`docs/archive-versions/eval-baselines-old.md`；M27 以后的长期账本：`docs/state/eval-baselines.md`。
