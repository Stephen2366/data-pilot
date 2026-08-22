# DataPilot AI Context Changelog — Phase 4B

> Phase 4B 的新记录写入本文件头部；阶段结束后再将本文件转为历史档案。
>
> 本文件保存 Phase 4B（M41 起，对应 `docs/phase4b-roadmap.md`）的模块档案、实验记录和技术取舍，按时间倒序排列。Phase 4（M29–M40）历史仍见 `change-history/phase4.md`。当前项目状态以 `docs/state/AI_CONTEXT.md` 为准；跨阶段索引见 `docs/state/CHANGELOG_INDEX.md`。
>
> 默认先按模块号、日期或关键词定位，再读取相关章节，不要无差别全文读取。新结论修正本阶段旧判断时，应在旧条目原位添加 `⚠️ 注`。

标题标签：

- `[模块任务]`：功能、架构、默认行为、安全口径、评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM Eval、smoke 或会影响路线判断的实验结论。
- `[验收]`：accept-module、阶段验收或明确的完成状态。
- `[小修]`：文档措辞、口径同步、注释补充、轻量整理；只需简写，不要求完整模板。

「变更记录」：小修可以只写一段话；较大的任务建议包含：改动范围、关键记录（比如关键决策、决策原因、实验结果、新发现、用户做出的选择等）、参考资料、验证快照、遗留/后续。

同一模块 / 同一阶段内连续的小修（中间没有被 [模块任务] / [实验] 等其他类型条目隔开时），合并到一个 [小修] 小节。

## 变更记录（新的在上）

### [实验] M41 business RAG 首次真实 Qwen Smoke（2026-08-22）

- 用户明确授权 `smoke` 后只执行一次 `m41-rag-smoke-20260822-01`：2 个 Scenario / 2 次产品请求，最多 1 次 Qwen generation；未扩大 Core/Diagnostic/Reliability，未重跑、未调用 LLM Judge。
- resolved runtime：`phase4-rag-e2e-v1`，business release `7d0d0937...409a`、corpus `1927eb53...7857`、`knowledge-deterministic-lexical-v1`、Qwen `qwen3.7-plus`、60s/retry0、`phase4-rag-eval-business-generation-outbound-v1`。两题均完整经过产品 Harness；普通 API 默认未改变。
- 结果：run `completed`，自动 required `23 passed / 0 failed / 0 not_observed`，Gate `passed`。质量退款题唯一 provider attempt 成功，prompt 660 + completion 352 = 1012 tokens；答案逐项符合 `refund_policy_quality@2026-08-13-r1`。五年保修题 candidate 为 0，安全兜底且 provider 调用为 0。离线 review 来源哈希验证通过，人工 verdict `2 pass / 0 fail / 0 insufficient_evidence`。
- artifact identity `674de0f...a461`，artifact SHA-256 `5fd72b...ba64`；report、triage、review/verdict/reviewed 文件位于 `eval/reports/`，两份 checkpoint/安全 Trace 位于 `.agent_work/temp/m41-rag-checkpoints/m41-rag-smoke-20260822-01/`。
- 解释边界：登记为当前有效首次 Smoke 快照，不自动升为正式长期基线；单次两题不能证明 Core、多文档、Reliability 或整体业务质量。下一步是否登记基线或扩大运行由用户决定。

### [模块任务] M41 Phase 4 RAG 真实产品链路 EvalOps 与诊断体系（2026-08-22）

> ⚠️ 注（后续 G2）：本条“未运行真实 Smoke”是技术开发收工时状态；随后用户已授权并完成上方 `m41-rag-smoke-20260822-01`，其窄结果不改变本条模块范围与默认行为边界。

- **范围说明**：本条按当前索引写入 Phase 4B 历史文件，但模块语义是 Phase 4 RAG Eval 缺口补完，不执行 Phase 4B Agent Loop、TaskState、RAG Subgraph、durable checkpoint 或 Context Compact。起始 commit 未由用户指定；开工时 HEAD 为 `1348148`。改动覆盖 API/RAG Tool 的 eval-only Composer seam、独立 RAG Eval contracts/catalog/selectors/runner/scorer、artifact/report/triage/review/compare、M34 historical importer、聚焦测试和 runbook/state 文档。
- **核心合同**：每个 Scenario/replicate 恰好一次 `/api/query → caller → turn → Router → Harness → RAG Tool → business AnswerFlow → API/Trace` 产品请求，形成共享 `RAGExecutionEvidence`；所有 scorer/report/triage/review/compare 零产品重跑。`phase4-rag-e2e-v1` 冻结 RunSpec、release/corpus/retrieval/Composer/model/policy/caller identity、连续 checkpoint 前缀、closed-world assertion plan 和 Gate；transport unavailable 下游为 `not_observed/inconclusive`，模型坏结构/support 为 observed failure。
- **用户决策**：G1 采用 deterministic oracle 下限 + 强制人工 review，不引入 LLM Judge。实施中发现 M34 Composer 只允许 `public_benchmark_document`，不能用于非公开 business Knowledge；给出“独立 eval-only policy”与“不允许业务文档出站、只保留 fake”两案，建议前者。用户确认方案 1，遂新增 `phase4-rag-eval-business-generation-outbound-v1`：只允许 active release 中经过 caller/ACL/Gate 的 `role_restricted_policy_text` / `metric_definition` generation context，security/未知类别网络前失败关闭；普通 API、`phase4-outbound-v1` 和 deterministic Composer 不变。
- **诊断闭环**：catalog 单一事实源提供 smoke/core/diagnostic/reliability；runner 支持显式 `--resume` 且只接受合法 checkpoint 连续前缀；funnel 覆盖 product runtime、retrieved、selected、generation-visible、provider/support、cited、answer 自动下限。review 对 artifact/checkpoint 绑定 SHA-256，verdict 不改自动 Gate；strict compare 拒绝 runtime/protocol 漂移；M34 importer 验证原 artifact identity 后明示为 external direct AnswerFlow historical，不冒充产品 E2E。
- **参考资料**：借鉴 ARAG-EVAL“先保存实际 answer/context 再评分”和 DB-GPT retriever/answer evaluator 分层；未照搬 notebook 简单平均、失败样本跳过、scorer 重跑 pipeline、空结果统一计零、RAGAS/单一 LLM 分数裁决。EvalOps 生命周期纪律来自 DataPilot M27，但 SQL/RAG artifact 与业务语义保持分家。
- **验证**：M41 聚焦 `11 passed, 1 warning in 1.53s`；M27、M31–M40 与 M41 受影响回归 `205 passed, 1 warning in 73.67s`；全仓后台 pytest exit `0`，`459 passed, 3 skipped, 1 warning in 508.88s`。warning 均为 Starlette TestClient/httpx deprecation，不阻塞。四个 CLI help、compileall、diff check 通过；现存 M34 180 题 artifact 离线导入匹配 SHA-256 `75592af...99fa` / identity `d9fa2b...b41f`，180 calls、10 unavailable，零 Tool/LLM。
- **遗留/边界**：未运行真实 business RAG Qwen smoke、LLM Judge、remote embedding/Milvus、LangFuse Cloud、真实 Hybrid LLM 或 M34 重跑，因此没有 M41 质量基线。真实首次运行仍需用户精确授权 selector、run ID 与调用范围，建议 smoke 后停门；unavailable 不得自动换 ID 重跑。若回到 Phase 4B，仍须按 roadmap 另立 B0 module plan，不能把 M41 诊断体系冒充 Agent 能力完成。

### [实验] M41 首次真实 LLM smoke（2026-08-22）

> ⚠️ 注（M41 RAG Eval 补完）：该条是更早的 **M27 Text2SQL** smoke，只有 run ID/当时任务编号使用 `m41`；它不是 `phase4-rag-e2e-v1` business RAG smoke，不能满足本模块 G2。真正的 M41 business RAG Smoke 后续已以上方 `m41-rag-smoke-20260822-01` 独立完成，两者不得混算。

- 按用户一次授权，使用当前默认 `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`、M27 v3 `smoke` selector 执行恰好一次；未扩大到 core/stress/reliability，也未重复运行。
- run：`m41-real-llm-smoke-20260822-01`；4 个逻辑 Scenario、4 个 physical attempts。`june_gmv` 与 `active_products_top10` 到达 LLM generation，但均为 `external_unavailable / network_error`；`unsafe_drop_orders` 与 `missing_product_supplier_rejection` 在确定性安全/计划合同处拒绝并通过对应 required assertion。
- 结果：run `completed`，Gate `inconclusive`（required passed=2、failed=0、not_observed=7；logical completed=2、external unavailable=2）。本次没有成功的模型输出可用于 Text2SQL 质量结论，`inconclusive` 不能当作通过或失败。
- artifact/report：`eval/reports/m27-artifacts/m41-real-llm-smoke-20260822-01.json`、`eval/reports/m41-real-llm-smoke-20260822-01.md`；run spec hash `bd3ce4aefd4ccebfad5ecd364548aeec87deb49ee931d80000c2b6139e98d07f`。
- 遗留：需另行诊断 provider/network 出站问题；未经新的明确授权不得重跑或扩大 suite。此次真实模型 smoke 与 M35–M40 deterministic contract/assurance Eval 分账，不改默认模型或路线。

### [小修] Status 文档标注路线升格（2026-08-22）

- `docs/notes/phase4-rag-capability-status.md` 头部与第 12 节标注：方案已于 2026-08-22 经用户确认升格为 `docs/phase4b-roadmap.md`，第 1–11 节转为演进记录；修订记录同步补一条。仅文档标注，不改变任何运行事实或路线内容。

### [小修] 新建 Phase 4B 历史档案并切换索引写入目标（2026-08-22）

- `docs/state/CHANGELOG_INDEX.md` 的当前写入目标由 Phase 4 切换为 Phase 4B，并新增阶段索引行：Phase 4B（M41 至当前）→ `change-history/phase4b.md`；Phase 4 行范围收口为 M29–M40。
- `change-history/phase4.md` 转为历史档案（Phase 4 收口于 M40），不再承接新条目；其中 2026-08-22 的 Phase 4B 立项相关既有条目（候选方案审查小修、Roadmap 正式立项模块任务）保留原位，不迁移。
- 本次只重组 changelog 路由，不改变任何运行配置、Eval 结果、历史结论或 `docs/phase4b-roadmap.md` 内容。
