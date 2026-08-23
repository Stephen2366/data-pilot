# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，Text2sql 和 RAG 评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，RAG / 知识库事实见 `docs/state/rag-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

## 当前状态

| 项目         | 当前值                                                       |
| ------------ | ------------------------------------------------------------ |
| 阶段路线     | `docs/phase4b-roadmap.md`                                    |
| 阶段参考     | `docs/phase4-reference.md`                                   |
| 当前活动模块 | M42 / Phase 4B B0 前置包已验收通过（2026-08-23）；M43/B1 尚未立项 |
| 当前 plan    | `docs/notes/m42-plan.md`；B0 冻结合同由 M43–M48 分模块消费，不得把 skeleton 当 runtime 完成 |
| 当前 notes   | `docs/notes/m42-notes.md`                                    |
| 待决事项     | 下一步为 M43/B1 独立 module plan；M46 前 60 题 decision reserve 保持 sealed，M41 的正式基线登记/held-out 授权仍是独立事项 |
| 更新时间     | 2026-08-23                                                   |

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

- 后端：FastAPI + Pydantic；`/api/query` 统一调用 M37 turn seam。普通/accepted initial、resume 或 follow-up 恰好一次 M35 Graph，thread lifecycle 前置拒绝为零次；响应、JSONL Trace 与 Eval 都从同一 turn/result/lifecycle/validity 事实投影。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- Phase 4B seed：默认仍为 legacy `sqlite_deterministic_seed`；只有显式选择 `profile_alias="phase4b"` 才加载 content-bound B0 profile，生成 7/8 月 oracle。不得把两个 profile 的 artifact 混算。
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
- Trace runtime identity：`/api/query` 的 SQL、RAG、Hybrid、澄清恢复和安全拒绝 Trace 均从同一 `AgentTurnResult` 投影 `phase4-trace-runtime-v1`。缺少安全 identity 只标 `unavailable`、不阻断业务；P7 canonical rehearsal 视其为失败。Trace 不保存 raw `thread_id` 或结构化 clarification/follow-up 参数副本，但沿用既有用户可见 `answer` 保存合同。
- 现有 Text2SQL chat/schema embedding 出站在 transport 前按 `phase4-outbound-v1` 精确登记；普通 Knowledge/RAG 与 LangFuse Cloud 继续默认拒绝。唯一例外是用户确认的 M41 显式 Eval CLI：`phase4-rag-eval-business-generation-outbound-v1` 只允许已通过 active release、caller/ACL/Gate 的政策/指标 generation context 发往 Qwen，security/未知类别网络前拒绝；该 policy 不进入普通 API。

## 最近验证事实

> 只保留会影响当前决策的最新证据，不按模块流水账累积。

| 日期 | 事实 |
|---|---|
| 2026-08-23 | M42 完成 Phase 4B B0 前置包：B0 contract `6543883...aae6f`、seed profile `9c49407...00673`、SQL oracle `be813a8...57ef80`、Agent skeleton `b303d4d...52982`、sealed reserve `f70c5fc...e505`。首次 business retrieval 零 provider 且真实漏选 basic 政策，保留为 B3 输入；M43–M48 能力仍 unavailable。最终全仓 `487 passed, 3 skipped, 1 warning`，未改 legacy/active release/默认模型或任何长期基线。 |
| 2026-08-23 | 用户授权 external dev Smoke + Basic 各一次并 completed：Smoke 9 题 Gate `failed`（required `96/12/0`），usage `20288 tokens`，triage `4 passed / 2 selection / 2 citation / 1 retrieval`，语义 verdict `3 pass / 6 fail`；Basic 21 题 Gate `failed`（required `215/25/12`），usage `47814 tokens`，triage `12 passed / 4 retrieval / 3 product_runtime / 1 selection / 1 citation`，语义 verdict `9 pass / 9 fail / 3 insufficient_evidence`。Basic 的 3 个无答案均为 provider 有响应但 Composer 结构合同失败；两套共 30 requests / 68102 tokens，无 transport unavailable。重叠 3 题 verdict 一致，但不构成 Reliability 证明；不登记基线、不改默认，120 held-out 未运行。 |
| 2026-08-23 | 用户授权首条 v2/post-fix external dev core 真实运行 `m41-rag-external-core-20260823-151649` completed：25 题 / 25 执行，Gate `failed`（required `211 passed / 58 failed / 31 not_observed`），primary triage `9 retrieval / 7 product_runtime / 1 selection / 1 citation / 1 provider_or_support / 6 passed`，usage `53106 tokens`（24/25 provider 成功，latency p50 8.9s）。5 题 `composer_output_invalid` 被如实标记（归类修正生效）。AI reviewer 逐题语义 verdict `4 pass / 13 fail / 8 insufficient_evidence`：fail 主体为检索错文档→答偏与有引用仍拒答，4 例 pass 全部检索命中 gold；自动 Gate 通过的 6 题中 2 题 verdict 仍 fail，再次证明自动断言 ≠ 语义正确。结论强化 lexical 漏召回为首要瓶颈；不改变任何默认、不登记基线，120 held-out 未运行。 |
| 2026-08-23 | M41 RAG Eval 用户入口去歧义：business 的旧 smoke/core/diagnostic/reliability 合并为唯一 `business`（5 题各 1 次），仍可 `--scenario` 精确诊断；external 的裸 smoke/basic/core/hard/reliability/full 默认使用 `diagnostic_dev`。因此日常说“执行 core RAG Eval”即 external dev core；只有明确说 `held-out` 才触碰封存集。历史 artifact 不改签，本次零 provider 调用。 |
| 2026-08-23 | M41 补充完成 external canonical 180 catalog 与 `basic/core/hard=64/74/42`；dev suites 为 smoke `9`、basic `21`、core `25`、hard `14`、reliability `6×3`、full `60`。`phase4-rag-e2e-compare-v2` 默认 strict repeat，只有显式 runtime allowlist 才允许候选 A/B，并输出 paired/失败层/difficulty/usage/latency；不替代人工语义 review。零 provider 调用；聚焦 `19 passed`、M31–M41 回归 `234 passed`、全仓 `467 passed, 3 skipped, 1 warning`。 |
| 2026-08-23 | M41 已把 M34 冻结 180 题直接接入分层诊断：保留原生 `question_type × source_signature × document_cardinality` 和 60 dev / 120 held-out split，不复制题面。旧 180 Answer + retrieval artifacts 已零调用投影为分层历史报告。用户授权的 external 60 dev 产品链路 run `m41-rag-external-dev-20260822-01` completed：60 requests / 137299 tokens，Gate failed，primary triage 为 `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`；人工语义 verdict `18 pass / 26 fail / 16 insufficient_evidence`；120 held-out 未运行。运行暴露 5 个 Composer 坏结构被误记 Harness failure，已修正未来分类并新增 `composer_support_valid`；原 artifact 不改签、不重跑，标记 pre-fix candidate。最新 M31–M41 回归 `229 passed, 1 warning`；全仓 `462 passed, 3 skipped, 1 warning`。 |
| 2026-08-22 | 用户授权并完成 M41 首次 business RAG Qwen Smoke `m41-rag-smoke-20260822-01`：2 Scenario / 2 executions，唯一 generation 成功、另一 no-candidate 零 provider；自动 required `23 passed / 0 failed / 0 not_observed`，Gate `passed`，人工 review `2/2 pass`。Qwen `qwen3.7-plus` usage 为 prompt 660、completion 352、total 1012 tokens；artifact identity `674de0f...a461`。本次已停门，未扩大 selector、未重跑、未调用 Judge；它是当前有效实验快照，不是正式长期基线。 |
| 2026-08-22 | M41 完成 Phase 4 business RAG 产品 EvalOps 技术闭环：`phase4-rag-e2e-v1` 经 `/api/query → turn → Router → Harness → RAG Tool → AnswerFlow → API/Trace` 一题一次执行，提供 catalog/selectors、RunSpec/checkpoint/completed artifact、failure funnel、Gate、triage、SHA-256 review、strict compare 与 M34 historical importer；用户确认独立 eval-only business Qwen 出站 policy。M41 聚焦 11 passed、M27/M31–M40 受影响回归 205 passed、全仓 459 passed / 3 skipped / 1 warning。该条是开发收工时快照，当时尚未运行真实 business RAG；后续首次 Smoke 结果见上一条，Judge、remote embedding/Milvus 与 LangFuse 仍未运行。 |
| 2026-08-22 | 本模块立项前曾按一次授权执行 M27-v3 Text2SQL `smoke`，其 run ID 恰以 `m41-` 开头：`m41-real-llm-smoke-20260822-01`。4 个 Scenario 中两个 generation 因 `network_error` 为 `external_unavailable`，两个确定性拒绝通过；Gate `inconclusive`。这不是 M41 business RAG smoke，不能满足 M41 G2 或形成 RAG 质量证据；不得未经新授权重跑。artifact/report 位于 `eval/reports/m27-artifacts/`。 |
| 2026-08-22 | Phase 4B roadmap 审查确认旧 M35 `single_tool`、M36/M37 单 Graph/单深 Tool、M38 branch budget 与新 Loop 需要显式 runtime family 隔离；当前 Pydantic 请求只严格校验已知 thread/follow-up 组合，未知字段不是统一 `extra=forbid` 合同。一次本地 deterministic Knowledge retrieval 诊断使用当前 active business release、默认 budget 与 `customer_service` caller，直接点名“基础退款政策和质量问题专项规则”的 T4 问法一次选中 `refund_policy_basic`、`refund_policy_quality`、`evidence_escalation_rule`，因此该原句不能承担 RAG recovery 证明。未修改 release、retrieval、权限或任何运行默认。 |
| 2026-08-17 | M40 完成 P7 技术收口：五条 deterministic API/Trace rehearsal（SQL、RAG、Hybrid、澄清恢复、安全拒绝）验证 response/Trace 同源、四轴、Evidence/citation、Graph/lifecycle 预算、安全 runtime identity 与非泄露；P7 closed-world manifest 只允许 P1、P2 retrieval/answer、P3、P4 turn/follow-up、P5、M39 P6 verified `no_go`、P7 rehearsal 九个 family，拒绝 M27 历史与 M34 质量数字填槽。M40 聚焦 6 passed、M31–M39 回归 208 passed、全仓 deterministic pytest 447 passed / 3 skipped / 1 warning；technical Gate 不等于人工验收、生产认证或 P6 Subgraph 完成。 |
| 2026-08-17 | M39 完成 P6 只读 readiness audit：六份冻结 M34 输入须同时匹配 SHA-256、identity、split、retrieval runtime 与 Composer identity；只分类 60 dev，120 held-out 仅作闭合核验，零 provider 调用。结果为 retrieval `11`、context/packing `13`、Composer `10`、provider unavailable `2`、not classifiable `24`；“Observation 驱动新增 Evidence 动作”与“可比额外预算”均未被既有证据证明，故严格 `no_go`，external lexical 默认不变。全仓 deterministic pytest `441 passed, 3 skipped, 1 warning in 517.57s`。 |
| 2026-08-17 | M38 完成 P5 保守 Hybrid 双 Evidence 基线：本地确定性 Synthesizer、双 required branch、typed SQL/Document Evidence、safe partial/conflict/合成失败降级、API/Trace 投影和 `phase4-harness-hybrid-v1`（5 Scenario / 25 required）。全仓 deterministic pytest `436 passed, 3 skipped, 1 warning in 599.87s`，compileall/diff check 通过；未运行真实 Hybrid LLM、远程 embedding/Milvus、LangFuse Cloud 或 M34 external 大评测。 |
| 2026-08-17 | M37 完成 P4 的一次有界 follow-up + Evidence validity/重新取证切片：`phase4-harness-followup-v1` 覆盖 10 sequences / 22 turn evidence / 50 required，50/50 通过，identity `1185edf0...634b25`。全仓 deterministic pytest `427 passed, 3 skipped, 1 warning in 509.36s`，compileall/diff check 通过；未运行真实 LLM、远程 embedding/Milvus、LangFuse Cloud 或 M34 external 大评测。 |
| 2026-08-16 | M36 完成 P4/G5 首个有界恢复切片：应用持有 versioned in-process checkpoint，支持 pending→一次 resume/clear、owner+tenant/active-role、TTL/state version、原子单 claim、budget stop 和安全 Trace；`phase4-harness-turn-v1` 覆盖 8 组 sequence。全仓 deterministic pytest `416 passed, 1 warning in 594.12s`，compileall/diff check 通过；未运行真实 LLM/远程 Eval。 |
| 2026-08-16 | SQL 四轴映射按用户确认的方案 A 收口：QueryPlan output-projection mismatch 是执行前确定性合同拒绝，保持 `completed / no_answer / blocked`；LLM JSON/SQL 解析失败是 `external_unavailable / no_answer / passed`，不写 `blocked_reason`。SQL Guard、语义拒绝和 driver/pipeline 技术错误各有独立分支。 |
| 2026-08-16 | 用户已将 M34 EnterpriseRAG-Bench retrieval 与 Answer/Citation 结果登记为正式长期 RAG 基线；lexical 在 dev/held-out 均胜当前 semantic candidate，external 默认不切换。完整身份、数字、轻量证据清单与解释边界见 `eval-baselines.md`，不得与 22 条业务知识回归或 M27 Text2SQL 混算。 |
| 2026-08-10 | Text2SQL canonical contract 为 `m27-v3`，并使用 run-scoped Schema vector index；旧 v1/v2 artifact 只作历史解释，当前尚无由用户指定的 v3 真实 LLM 长期基线。完整合同、运行身份和旧实验数字见 `eval-baselines.md`。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的“下一步做……”必须删除或改写。

- (2026-08-23) M42 已完成 B0 冻结与 rehearsal，不等于 Phase 4B Agent runtime 完成。M43/B1 必须消费独立 runtime family、TaskState 入口、最小 caller 与 Scenario catalog；M45/B3 只能用预注册动作/预算诊断首次漏选；M46/B4 前 reserve 必须 sealed，提前访问或调参即退休。M41 继续作为历史 RAG Eval/纪律来源，不被 M42 改签或替代。
- (2026-08-23) M41 是 Phase 4 RAG Eval 缺口补完，不是 Phase 4B Agent 能力实施。business 小 catalog 负责 ACL/安全合同；M34 external 180 题负责大规模检索、选择、生成可见、Composer、引用与答案诊断，两者分账。60 dev 已真实运行，120 held-out 保持停门；这不改变 M39 P6 no-go、external lexical/业务 release/普通 Composer 或 Phase 4B B0–B5 决策门。
- (2026-08-23) external 评测现以完整 180 catalog 为事实源，difficulty、partition、suite 三轴分离；候选 compare 只放行预注册 runtime 字段差异。旧 60 dev artifact 缺 difficulty 且属于 pre-fix 协议，只作历史候选；未来先经新授权建立 v2/post-fix dev baseline，再讨论模块收益或 held-out 最终裁决。
- (2026-08-22) 用户已确认 `phase4-rag-capability-status.md` 第 12 节进入正式路线，现由 `docs/phase4b-roadmap.md` 升格为 Phase 4B 推进事实源。Phase 4B 是已完成 Phase 4 之上的新能力阶段，最终硬交付包含 experimental bounded RAG Subgraph、任务级自然多轮、持久任务状态、node-level Context Builder、Context Compact 基础版和贯穿 Agent Scenario Eval；“实现 Subgraph”与“切换默认”继续分离。该路线升格不改变 M39 P6 当时冻结 Evidence 下的正确 `no_go`、当前进程内 checkpoint、external lexical 默认或任何运行配置。
- (2026-08-22) Phase 4B 新增三项施工硬边界：旧 M31–M40 fixture 显式 pin legacy runtime、新 Agent Loop 使用独立 versioned family 且两类 Gate 同时通过；B1 新建 TaskState family/in-memory adapter，并以增量 API 投影兼容旧 thread payload；B3 使用预注册候选/预算/轮次/review point 的有界 campaign，动作不足时暂停重规划，no-go 不冒充能力完成。直接点名双政策的现有 T4 问法已证明会一次取全，B0 必须冻结真实非陷阱 business recovery case。

- (2026-08-17) M37 单独不等于 P4，但 M36 + M37 已共同完成 roadmap 定义的 P4 最小可验收基线；不宣称通用多轮。第二次追问、长历史 compact 和持久 checkpoint 不是当前 P4 硬门；跨 route/跨 Tool 补证据由 M38 的 P5 Hybrid 正式承接。M37“窄 B”仍是正式边界，不得退化为直接复用旧答案或默认扩到 external。
- (2026-08-17) M38 已按 P5 口径完成保守 Hybrid 纵向基线：方案 A 的本地确定性 Synthesizer 是正式默认与长期 fallback；SQL/RAG 默认 required，不触发 G6 optional 放宽，不新增 Hybrid 数据出站。P5 不等于开放式跨来源研究 Agent。
- (2026-08-17) M39 已按用户确认的方案 A 完成 P6 入场审计并严格 no-go；M40 已完成 P7 的技术收口，安全 Trace runtime identity 和 nine-family assurance 可供人工检查。二者均不改变 external lexical 默认，也不实现 Subgraph；P7 technical Gate 不等于整个 Phase 4 已验收。若未来重开 Subgraph，须有未污染 dev 对具体允许动作的新增 Evidence 证据、冻结的 held-out decision protocol 与可比额外预算，并另立计划。
- (2026-08-10) Text2SQL 的确定性收尾问题已修复；若未来重跑 Text2SQL，必须使用 `m27-v3` 新序列，并完整记录 collection、embedding、corpus 与 run-scoped index identity。现有 v1/v2 数字只作历史解释。
- (2026-08-09) 默认保持 Qwen `qwen3.7-plus` + inmemory deterministic + weighted；任何切换需要单变量重复证据与用户确认。

## 防遗忘能力账本（M29–M40）

> 记录已经存在、但容易被“当前窄实现已完成”掩盖的能力缺口和重开门。优先级表示防遗忘/复核顺序，不自动决定下一模块；下一模块仍须按 roadmap、最新失败证据和独立 plan 裁决。原方案字母只在对应 module plan 内有效，禁止脱离具体方案写“以后从 A 升级 B”。

| 优先级 | 能力缺口 | 当前结论与硬性重开门 | 路线归属 |
|---|---|---|---|
| P0 | M34 已证实 lexical 漏召回、selected budget / multi-document context packing 和 Composer support 拒绝会严重限制答案质量 | M39 已以冻结 M34 证据完成当时 P6 strict no-go：没有 Observation 驱动新增 Evidence 的允许动作和可比额外预算。Phase 4B B3 只能通过新的有界 diagnostic campaign 补齐 action-level Evidence，达到 review point 后必须停止；两种动作合格才进入 B4，动作不足则暂停重规划。semantic candidate 仍禁止直接切换 | Phase 4B B3/B4 |
| P1 | M38 方案 A 只冻结正式本地确定性 Hybrid Synthesizer；远程方案 B 与双 adapter 方案 C 未实施 | B 的重开门：受控 operators 对真实开放 Hybrid 问法形成稳定失败簇，且用户明确批准 receiver、`hybrid_synthesis` 用途、question/conditions、SQL safe result、Document Evidence/identity 的数据类别与字段，并提供真实 provider 精确运行授权。C 的重开门：除上述授权外，还需有未污染 Hybrid held-out、多轮可比预算和明确 A/B 决策价值；禁止仅为“代码里有两个 adapter”扩大 M38。无稳定净收益时 A 继续作为默认与 fallback | P5 后续质量/出站条件项 |
| P1 | 当前只有 demo/test caller resolver，生产认证尚未建设 | 出现非本地部署、真实用户/tenant、JWT/OAuth/SSO 或企业目录需求时，必须在现有 `CallerResolver` seam 接正式认证 adapter；“所有环境手工注入 resolver”不等于生产认证 | Phase 4 后续部署门 |
| P2 | M35/M38 deterministic Router 只覆盖 closed-world SQL/RAG 和两类 canonical Hybrid operator | 先建立开放问法/混合意图 decision set 并形成稳定失败簇，再比较规则扩充、受控模型 fallback 或远程 Router；不得以“LLM 更完善”为由无 Eval 切换 | P3/P5 后续质量 |
| P3 | `knowledge_docs` 有损 legacy 表仍保留 | 出现新 runtime consumer、知识后台/多实例发布、从旧表恢复授权/catalog，或双事实源风险时，必须正式设计数据库 projection 或删除 legacy 表；禁止继续追加字段把它伪装成 authority | 数据治理条件项 |
| P1 | M37 checkpoint 仍为进程内，重启/多 worker 不恢复且 tombstone 不清扫 | Phase 4B 已把 durable task state 提升为最终硬交付；须在 TaskState/turn-boundary 稳定后建立新 state family、真正持久 adapter 与存储层条件更新，并覆盖 TTL/clear/多 worker/版本冲突。LangGraph `InMemorySaver` 仍是内存态，不能冒充持久化升级 | Phase 4B B5 |

## 已知的坑（活跃列表）

> 只允许活跃问题；已经解决的内容移入 changelog。

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 的模型注册可能触发循环导入 | 聚合导入模型时可能失败 | API/工具层沿用 `app.db.base` 暴露路径；重构时再拆 base class。 |
| 旧 Milvus collection `datapilot_schema_docs` 有重复灌入污染 | 历史 A/B 不可信 | 新 eval 用唯一/clean collection；校验 row count、dimension、schema docs hash。 |
| QueryPlan 可能过宽，或 SQL 与计划不一致 | contract pass 不等于答案正确 | 保持保守 AST 边界，用 output/result/trace 共同定位。 |
| 生产认证尚未建设；请求体 `user_role` 仍是客户端自报字符串 | 不能作为文档 ACL、生产身份或 thread owner 的独立信任来源 | M35–M37 让 `/api/query` 在 local/demo/test 通过显式 fixture resolver 解析 caller，role 只能选择 resolved role；thread 再绑定 owner+tenant/active role，其他环境缺 authenticated resolver 时 Tool 前失败关闭。 |
| M37 checkpoint 仅在单进程内存，resolved/cleared tombstone 暂不清扫 | 重启或多 worker 时 pending/follow-up-ready 不可恢复；长时间大量创建 thread 会增长进程内容器 | 当前仍明确返回 `conversation_unavailable`，不伪装持久会话；Phase 4B 已把 restart/multi-worker 提升为 required Scenario，B1 先建独立 TaskState family，B5 再完成 durable adapter、TTL/clear/tombstone/清扫与 CAS。 |
| M35/M38 deterministic Router 对开放问法较窄 | 未登记 Hybrid、开放问法会保守停止；当前只证明两类 canonical operator，不代表通用意图理解 | 保持可注入 seam；只有真实失败簇、受控 Eval 和出站决策成立后，才规划规则扩张、远程 Router 或 Synthesizer。 |
| `knowledge_docs` 物理表仍存在且是有损 legacy 投影 | 新调用者若绕过 source-backed catalog 读取旧表，会丢失 revision/authority/identity/完整 ACL，并重新制造旁路 | Text2SQL 已从 Schema/prompt/RBAC 双重隔离；seed 只从 staged catalog 派生，旧表不得作为 authority/runtime catalog。 |
| M34 full Answer Eval 的 complete 不等于正确 | lexical 漏召回、semantic 与多文档题会产生“有 citation 但答非所问”；全题 all-gold cited 仅 44.44%，multi-document 5.26%，semantic 28.85% | 后续先按失败簇改善 gold coverage/context packing；不得用 complete rate 代替 correctness，也不得未经新计划重跑大规模 provider。 |
| Active Knowledge release 损坏时不会自动 fallback；当前虽有 previous，但旧 11-entry release 已不等于当前 authority | 自动复活旧正文可能绕过撤销/ACL，或丢失新增内容 | 启动失败关闭；显式 rollback 仍必须重新通过当前 authority/revision/policy 校验。 |
| LangFuse Cloud 重新启用前需统一 question/answer 脱敏（M28 F7） | RAG/Hybrid 若启用 Cloud 会外传完整问答 | LangFuse 默认关闭且 M31 outbound 未放行 Cloud；重新启用前先做 allowlist/redaction 策略和用户决策。 |
