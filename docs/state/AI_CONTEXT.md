# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，Text2sql 和 RAG 评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，RAG / 知识库事实见 `docs/state/rag-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史统一从 `docs/state/CHANGELOG_INDEX.md` 进入。

## 当前状态

| 项目         | 当前值                                                       |
| ------------ | ------------------------------------------------------------ |
| 阶段路线     | `docs/phase4-roadmap.md`                                     |
| 阶段参考     | `docs/phase4-reference.md`                                   |
| 当前活动模块 | M35 顶层 LangGraph Harness 与 SQL/RAG Router 已开发并完成收工文档，待人工检查与验收（2026-08-16） |
| 当前 plan    | `docs/notes/m35-plan.md`                                     |
| 当前 notes   | `docs/notes/m35-notes.md`                                    |
| 待决事项     | 下一模块规划时按 P4/G5 选择首个有界恢复切片；尚未触发远程 Router 或生产认证决策门 |
| 更新时间     | 2026-08-16                                                   |

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

- 后端：FastAPI + Pydantic；`/api/query` 每题只调用一次 M35 LangGraph Harness，再从唯一 `AgentRunResult` 投影 `AgentResponse`、JSONL Trace 与 Eval 事实。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- NL2SQL：普通 API 默认走 Harness 内的 `new_text2sql` 深 Tool（Schema Retrieval → QueryPlan → SQL Guard）；显式 `force_new_pipeline=false` 只选择 adapter 内部 legacy baseline，不能绕过顶层 Harness。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1。
- Schema Retrieval 默认：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅显式实验开启。用户已在 G4 选择 `knowledge-deterministic-lexical-v1` 作为 P3 首个 Knowledge Tool 默认 baseline；这不代表语义最优，未来替换仍需独立候选 identity、held-out 失败证据、A/B 与用户确认。
- Harness：LangGraph `>=1.1.2,<2`；固定单轮拓扑 `route → (sql_tool | rag_tool | terminal) → controller`，每轮最多一个 Tool。首版 Router 是可注入的 deterministic/conservative adapter；未知或 Hybrid 请求保守停止，不默认落到 SQL/RAG。
- Caller：`local/demo/test` 使用明确标记的 fixture resolver，请求 `user_role` 只能选择 resolver 已解析的 role；其他环境没有 authenticated resolver 时在 Tool 前失败关闭。生产认证尚未建设。
- M34 external benchmark：项目外 EnterpriseRAG-Bench v1.0.0 独立 profile；当前 external adapter 保持 `enterprise-lexical`，`enterprise-unit-paragraph-2400-v1` 无 overlap；semantic candidate 不胜 lexical，未激活。业务 22 条 active release 不变。
- LangFuse 默认关闭，JSONL trace 为主；SQL 安全为只读 AST + RBAC + 敏感字段策略。
- 现有 Text2SQL chat/schema embedding 出站在 transport 前按 `phase4-outbound-v1` 精确登记；所有新增 Knowledge/RAG 数据类别与节点用途继续默认拒绝，LangFuse Cloud 未获放行。

## 最近验证事实

> 只保留会影响当前决策的最新证据，不按模块流水账累积。

| 日期 | 事实 |
|---|---|
| 2026-08-16 | M35 完成 Phase 4 P3 顶层单轮 Harness：`/api/query`、JSONL Trace 与独立 `phase4-harness-v1` Eval 共享同一个 `AgentRunResult`；Text2SQL 与 `RAGAnswerFlow.run()` 保持完整深 Tool，Graph 不拆其内部步骤。最终全仓 deterministic pytest `397 passed, 1 warning in 555.68s`，compileall/diff check 通过。 |
| 2026-08-16 | SQL 四轴映射按用户确认的方案 A 收口：QueryPlan output-projection mismatch 是执行前确定性合同拒绝，保持 `completed / no_answer / blocked`；LLM JSON/SQL 解析失败是 `external_unavailable / no_answer / passed`，不写 `blocked_reason`。SQL Guard、语义拒绝和 driver/pipeline 技术错误各有独立分支。 |
| 2026-08-16 | 用户确认将 M34 EnterpriseRAG-Bench completed retrieval 与 Answer/Citation 结果登记为正式长期 RAG 基线；共同 dataset/question/split/profile identity、lexical/semantic @20 对照、Answer artifact 与解释边界见 `eval-baselines.md`。该基线与 22 条业务知识回归及 M27 Text2SQL 分账，不得混算。 |
| 2026-08-16 | M34 完成真实外部语料的构建、检索、回答与可复现 Eval：36,417 docs / 139,214 units / 180 questions；lexical @20 coverage/all-gold/MRR 为 dev `0.810417/0.766667/0.645303`、held-out `0.823125/0.775000/0.723134`。semantic candidate 两个 split 均落后，保持 candidate 不切默认。 |
| 2026-08-16 | M34 full Answer Eval artifact `.agent_work/temp/m34-answer-eval-full-v4.json` completed，identity `d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f`；180 flow/provider calls、405,305 tokens、answer complete `146/180`、all-gold cited `80/180`、mean gold coverage `0.493981`、multi-document all-gold `2/38`、semantic all-gold `15/52`，10 unavailable、24 support contract rejected。它证明链路和证据账本可复现，不证明答案正确率或生产质量。 |
| 2026-08-16 | 方案 B 的回答合同已落地：自然语言 `text` 可改写，但必须携带同一 Evidence 中逐字存在的 `support_text`；ACL、ledger、citation validator 不放宽。应用层不再设置 800-token 上限，provider 仍有服务端限制；已确认的 full Eval 完成一次并记录实际 token telemetry，收工阶段未追加重跑。 |
| 2026-08-10 | 当前 canonical contract 升为 `m27-v3`：Schema Context 的物理字段、metric key、输出 alias 分开，并在 catalog 加载时做 domain schema 可满足性校验；`orders_wide` 业务月份统一按 `paid_at`，`snapshot_at/batch_id` 只选快照版本。旧 v1/v2 artifact 继续只读，不与 v3 直接比较；本次未运行真实 LLM Eval。 |
| 2026-08-10 | M27 EvalRun 已恢复 run-scoped Schema vector index：一轮只构建/注入一次，结束时关闭，runtime identity 记录 reuse 与 Milvus row count；pytest 默认禁止未 mock 的真实 Text2SQL provider。 |
| 2026-08-10 | Qwen plus + Milvus 的 M27 Stress（9 题）与 Database Exception（7 题）各完成一次，runtime identity 完整记录 DashScope Qwen embedding / 1024 dim、clean collection、195-doc hash。Stress 为全部 assertion **7 passed / 14 failed / 4 not_observed**（7 completed / 2 external unavailable）；Database Exception 为 **4 / 4 / 11**（3 completed / 4 external unavailable）。两套 policy 的 required 均为 0、Gate 都是 `inconclusive`，不等于业务硬门失败；均为单轮 advisory 证据，未登记长期 baseline。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的“下一步做……”必须删除或改写。

- (2026-08-16) M35 已完成 P3 唯一顶层 Router/Harness，并复用 `RAGAnswerFlow.run()` 与完整 Text2SQL pipeline。下一轮先基于 Harness Trace/Eval 的真实失败簇规划 P4/G5 首个有界恢复切片；不得把恢复逻辑偷塞进 Router/Tool，也不提前做 P5 Hybrid。M34 lexical 漏召回和 multi-document context packing 仍是后续独立候选，不自动并入 P4。
- (2026-08-10) Text2SQL 的确定性收尾问题已修复；若未来重跑 Text2SQL，必须使用 `m27-v3` 新序列，并完整记录 collection、embedding、corpus 与 run-scoped index identity。现有 v1/v2 数字只作历史解释。
- (2026-08-09) 默认保持 Qwen `qwen3.7-plus` + inmemory deterministic + weighted；任何切换需要单变量重复证据与用户确认。

## 已知的坑（活跃列表）

> 只允许活跃问题；已经解决的内容移入 changelog。

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 的模型注册可能触发循环导入 | 聚合导入模型时可能失败 | API/工具层沿用 `app.db.base` 暴露路径；重构时再拆 base class。 |
| Windows pytest 临时目录偶发被旧进程锁住 | `PermissionError` 导致假失败 | 换新的 `--basetemp=.agent_work/temp/<name>`。 |
| 工作树可能含用户/其他工具未提交改动 | 容易误回滚 | 动文件前先看 `git status --short`，不回滚非本次改动。 |
| 旧 Milvus collection `datapilot_schema_docs` 有重复灌入污染 | 历史 A/B 不可信 | 新 eval 用唯一/clean collection；校验 row count、dimension、schema docs hash。 |
| QueryPlan 可能过宽，或 SQL 与计划不一致 | contract pass 不等于答案正确 | 保持保守 AST 边界，用 output/result/trace 共同定位。 |
| 生产认证尚未建设；请求体 `user_role` 仍是客户端自报字符串 | 不能作为文档 ACL、生产身份或 thread owner 的独立信任来源 | M35 已让 `/api/query` 在 local/demo/test 通过显式 fixture resolver 解析 caller，role 只能选择 resolved role；其他环境缺 authenticated resolver 时 Tool 前失败关闭。 |
| M35 deterministic Router 对开放问法较窄 | 未知或 Hybrid 问题会保守停止，不能代表已具备通用意图理解 | 保持可注入 seam；只有真实失败簇、受控 Eval 和出站决策成立后，才规划远程 Router 或 fallback。 |
| `knowledge_docs` 物理表仍存在且是有损 legacy 投影 | 新调用者若绕过 source-backed catalog 读取旧表，会丢失 revision/authority/identity/完整 ACL，并重新制造旁路 | Text2SQL 已从 Schema/prompt/RBAC 双重隔离；seed 只从 staged catalog 派生，旧表不得作为 authority/runtime catalog。 |
| M34 full Answer Eval 的 complete 不等于正确 | lexical 漏召回、semantic 与多文档题会产生“有 citation 但答非所问”；全题 all-gold cited 仅 44.44%，multi-document 5.26%，semantic 28.85% | 后续先按失败簇改善 gold coverage/context packing；不得用 complete rate 代替 correctness，也不得未经新计划重跑大规模 provider。 |
| Active Knowledge release 损坏时不会自动 fallback；当前虽有 previous，但旧 11-entry release 已不等于当前 authority | 自动复活旧正文可能绕过撤销/ACL，或丢失新增内容 | 启动失败关闭；显式 rollback 仍必须重新通过当前 authority/revision/policy 校验。 |
| LangFuse Cloud 重新启用前需统一 question/answer 脱敏（M28 F7） | RAG/Hybrid 若启用 Cloud 会外传完整问答 | LangFuse 默认关闭且 M31 outbound 未放行 Cloud；重新启用前先做 allowlist/redaction 策略和用户决策。 |
| 有时会出现 Windows 宿主保留 9091 | Milvus health 检查失败 | 使用 `19091:9091` host 映射。 |

## 历史入口

- 完整改动、实验记录、旧合同取舍入口：`docs/state/CHANGELOG_INDEX.md`。
- 历史 eval 数字：`docs/archive-versions/eval-baselines-old.md`；M27 以后的长期账本：`docs/state/eval-baselines.md`。
