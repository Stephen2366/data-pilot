# M41 Phase 4 RAG 真实链路 EvalOps 与诊断体系实施素材

> 本文是 M41 开发过程事实源。关键决策、踩坑、验证证据和修正必须在发生时记录，不能在收工时凭记忆补写。

## Implementation checklist

- [x] 完整复核 M41 plan、运行/RAG/Eval state、M27 EvalOps、M31–M40 产品链路与 M34 真实 AnswerFlow Eval。
- [x] 冻结独立版本化的 Phase 4 RAG Eval contracts、Scenario catalog、selector 和 resolved runtime identity。
- [x] 建立 eval-only 真实 Composer 注入 seam；普通 API deterministic 默认保持不变。
- [x] 建立一次产品链路执行产生共享 `RAGExecutionEvidence` 的 runner；scorer/report/review 零产品重跑。
- [x] 建立 retrieval → selected → generation-visible → Composer/support → citation → answer 的 failure funnel。
- [x] 建立 required/advisory/not_observed、Gate、completed artifact、checkpoint/resume 和 Markdown report。
- [x] 建立逐题 triage、带来源 SHA-256 的 review/verify 和严格可比 compare。
- [x] 建立 M34 historical artifact 的只读兼容视图，不重跑 external Tool/LLM。
- [x] 补齐聚焦测试与 M31–M40/M27 受影响回归；按长任务规则执行全仓验证。
- [x] 更新 runbook、RAG/Eval state、AI_CONTEXT 和索引指定的技术历史。
- [x] 用户明确授权前不运行真实 Qwen RAG Eval；不调用 LLM Judge；不改默认 Composer/retrieval/release。
- [x] 调用 `finish-module` 完成注释、验证、notes 与技术档案收工。

## 开工快照

- 模块范围：只补齐 Phase 4 RAG Eval 缺口，不建设或执行 Phase 4B 能力。
- 当前核心缺口：M34 真实 Qwen Eval 直接调用 external `RAGAnswerFlow`；M35–M40 产品 Harness 的 RAG 路径只有 deterministic contract，没有真实 LLM E2E、完整 failure funnel、triage/review/compare。
- 核心设计：以“一次真实产品执行产生一份共享 Evidence”为唯一外部 interface；runtime injection、provider、scorer 等作为内部 seam，所有下游只读共享 Evidence。
- 默认边界：普通 API 保持 deterministic Composer；business 22-entry release、lexical retrieval、caller/ACL/outbound、M34 external pointer 和历史 artifact 均不改变。
- 决策门：G1 首版按 plan 的方案 A 实现 deterministic oracle 下限 + 人工 review；不调用 Judge。G2 真实运行尚未授权，本轮只实施和做 deterministic 验证。

## 参考源码复核记录

- `ARAG-EVAL`：借鉴保存实际 Agent answer/context 后再评分；不照搬 notebook 简单平均、失败样本跳过和 RAGAS 直接裁决。
- `DBGPT-EVAL`：借鉴 retrieval/answer evaluator 分层；不照搬 scorer 重跑 pipeline、空结果统一计零或单个 LLM 分数冒充正确性。
- DataPilot M27：复用一次执行、RunSpec、checkpoint、closed-world、Gate、triage、review 来源哈希的纪律；不改 M27 schema，不混算 SQL/RAG。

## 过程记录

- 2026-08-22：用户确认按 `m41-plan.md` 开发，并再次明确 M41 属于 Phase 4 RAG Eval 补完，不执行 Phase 4B。已完整读取 AGENTS、M41 plan、AI_CONTEXT 及命中的 runbook、RAG/Eval state、CHANGELOG_INDEX 和 Phase 4 reference；真实 provider 与 Judge 均未获授权。
- 2026-08-22：首轮聚焦 pytest 的业务错误被 Windows 临时目录清理异常遮蔽：`--basetemp=.agent_work/temp/pytest-m41-first` 在 session finish 触发 `WinError 5`。后续聚焦测试改用 `.codex/temp_work/` 下的独立目录；不改变产品或 Eval 合同。
- 2026-08-22：非沙箱聚焦测试暴露两个 oracle 对齐问题，而非产品缺陷：`quality_refund_materials` 原问法没有 Router 的 RAG hint，已在 canonical catalog 中改为包含“规则”的真实 RAG 问法；no-candidate 产品会由 Harness 输出固定安全兜底文本，故 assertion 改为验证该稳定兜底，而不是错误要求 API `answer=null`。默认 Router/Harness 均未修改。
- 2026-08-22：产品执行、catalog/selectors、RunSpec/checkpoint/completed artifact、funnel/assertions/Gate/report/triage、review 来源哈希、strict compare 与 M34 historical importer 的首轮离线实现已落地；聚焦结果 `8 passed`，全程 fake composer，零真实 provider 调用。
- 2026-08-22：发现必须停门的 C2 / 出站安全冲突。现有 `make_qwen_evidence_composer()` 与 `KNOWLEDGE_GENERATION_POLICY` 是 M34 external benchmark 专用，只允许 `public_benchmark_document`；M41 business release 使用 `role_restricted_policy_text`、`metric_definition` 等数据类别，而 `phase4-outbound-v1` 没有 business knowledge generation 规则。当前 CLI 暂时引用 M34 factory 只能算未完成接线，不能作为真实业务运行入口。未经用户确认，不新增 eval-only business outbound policy、不把业务文档发往 Qwen、不运行真实 Eval。
- 2026-08-22：用户确认出站方案 1。已新增独立 `phase4-rag-eval-business-generation-outbound-v1`，只在显式 M41 CLI 中允许已通过 active release、caller/ACL、Gate 且 source data class 属于 `role_restricted_policy_text` / `metric_definition` 的 generation context 发给 Qwen；`security_policy`、未知类别或 identity 漂移在网络前失败关闭。普通 API、默认 deterministic Composer 与 `phase4-outbound-v1` 不变。真实 Qwen smoke 仍未获本轮精确运行授权。

## 收工阶段性 checkpoint（完整 pytest 启动前）

### 模块名称与当前改动范围

- 模块：M41 Phase 4 RAG 真实产品链路 EvalOps 与诊断体系；不属于 Phase 4B 实施。
- 起始 commit：未由用户明确指定；当前 HEAD 为 `1348148`，文件范围依据本轮会话、`git status --short`、tracked diff 与 untracked M41 文件归并。
- 产品接线：`app/api/query.py`、`app/main.py`、`engine/harness/adapters.py`、`engine/rag/answer_flow.py`、`engine/rag/enterprise_generation.py`。
- Eval 合同/运行/评分：`eval/rag_e2e_{contracts,generation,runtime,runner,scoring,review}.py`、`eval/rag_m34_history.py`。
- CLI：`eval/run_rag_{eval,review,compare,m34_history}.py`。
- Catalog/selectors：`eval/cases/rag/scenarios.yaml` 与 `selectors/{smoke,core,diagnostic,reliability}.yaml`。
- 测试：`tests/test_m41_rag_e2e_runtime.py`、`tests/test_m41_rag_e2e_contracts.py`、`tests/test_m41_rag_review_history.py`。
- 文档：`docs/notes/m41-plan.md`、本文、`docs/state/runbook.md`；专项 state/changelog/AI_CONTEXT 尚待完整 pytest 结果检查后更新。

### 关键决策与风险

- 一题一次产品请求产生共享 `RAGExecutionEvidence`；scorer/report/triage/review/compare 不重跑 retrieval 或 provider。
- G1 采用 deterministic oracle 下限 + 人工 review，未引入 LLM Judge；自然语言正确性不能由 `complete`、gold recalled 或 citation valid 代替。
- 用户确认 eval-only business Qwen 出站方案；风险是模拟业务但元数据标记为非公开的文档会在真实 Eval 时发往 Qwen，因此只允许显式 CLI、窄类别、独立 policy identity，普通 runtime 不继承。
- provider transport/配额/出站不可用使下游语义 assertions 为 `not_observed`、Gate `inconclusive`；模型返回坏结构/support 是已观察合同失败，Gate `failed`。
- interrupted/failed run 必须显式 `--resume`，且 checkpoint 必须是 RunSpec 的连续合法前缀；Trace 已落盘但 checkpoint 未提交时失败关闭，禁止自动重复付费执行。
- 当前未运行真实 RAG Qwen smoke，不能登记业务 RAG 质量基线；M34 只读视图仍是 external direct AnswerFlow 历史证据。

### 阶段 1 注释小结

- 完整检查当前 M41 范围内 19 个 Python 文件；正则盘点包含 158 个 class/function 声明（含既有大文件中的原声明）。
- 补强/新增了 8 处 docstring 或复杂流程注释，重点解释 eval-only 出站预检、RunSpec/checkpoint 连续前缀、一次执行共享证据、strict compare 和 CLI 边界。
- 关键设计注释已说明为什么不复用 M34 public benchmark policy、为什么 scorer 零重跑、为什么 unavailable 与 observed bad output 分账。
- 未发现仍缺失的关键注释；既有注释中没有因 M41 接线而失效的默认行为描述。

### 已完成验证快照

- M41 聚焦 pytest 最终：`11 passed, 1 warning in 1.53s`；warning 为 Starlette TestClient/httpx deprecation，不影响当前合同。
- 受影响 M27、M31–M40 + M41 回归：`205 passed, 1 warning in 73.67s`；同一 deprecation warning，不阻塞。
- 四个 CLI `--help` 均 exit 0：run / review / compare / M34 history 参数与 runbook 对账。
- 真实 M34 180 题 artifact 离线 importer exit 0：source SHA-256 `75592af...99fa`、artifact identity `d9fa2b...b41f`、180/180 AnswerFlow calls、10 unavailable；明确标记非产品 Harness E2E，零 Tool/LLM。
- `git diff --check` 无 whitespace error，仅 Windows LF→CRLF 提示；`compileall` exit 0。
- 初次 pytest 两次在沙箱临时目录收尾遇到 `WinError 5`，改为获准的非沙箱 pytest 后获得真实结果；属于执行环境问题，不是产品失败。

### 已知风险与待完成（后台启动时快照）

- 待运行并检查完整仓库 pytest；完成前不宣称 module 完成。
- 完整结果确认后，按 `CHANGELOG_INDEX` 更新当前 Phase history、`AI_CONTEXT.md`、`rag-current-state.md`、`eval-baselines.md`，完整回读并完成技术档案 checklist。
- 未运行真实 Qwen、LLM Judge、remote embedding/Milvus、LangFuse Cloud、Hybrid LLM 或 M34 重跑；这些均不在当前授权范围。

### 完整 pytest 后台任务（已完成并检查）

- 启动时间：2026-08-22；PID `48860`。
- 执行脚本：`.agent_work/temp/run_m41_full_pytest_20260822.ps1`。
- 实际 pytest：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\pytest-m41-full-20260822`。
- stdout：`.agent_work/temp/m41-full-pytest-20260822.out`。
- stderr：`.agent_work/temp/m41-full-pytest-20260822.err`。
- 退出码：`.agent_work/temp/m41-full-pytest-20260822.exit`。
- 完成标记：`.agent_work/temp/m41-full-pytest-20260822.done`。
- 完成时间：`2026-08-22T23:08:44.3842504+08:00`；退出码 `0`。
- 最终结果：`459 passed, 3 skipped, 1 warning in 508.88s (0:08:28)`。
- warning：Starlette TestClient/httpx deprecation；与聚焦/受影响回归相同，不影响 M41 合同，后续依赖升级时处理。

## Handoff

### 已完成且可依赖

- `phase4-rag-e2e-v1` 已提供 business RAG 产品链路的 canonical catalog/selectors、RunSpec/resolved runtime、一次执行 Evidence、closed-world artifact、typed assertions、Gate、funnel report 与 triage。
- `RAGProductExecutor` 真实经过 `/api/query`、caller、turn、Router、Harness、RAG Tool、AnswerFlow、API/Trace；app-state 注入退出后恢复，普通 API 仍使用 deterministic Composer。
- 用户确认的 eval-only Qwen 出站 guard 已冻结：只允许 active release 中经过 ACL/Gate 的政策/指标 generation context；security/未知类别网络前拒绝，policy identity 写入 runtime/attempt。
- review/verify、strict compare、M34 historical importer 均为离线只读消费者；人工 verdict 不修改自动 Gate，M34 明示为 external direct AnswerFlow。
- 确定性实现通过 M41 聚焦、M27/M31–M40 受影响回归和完整仓库 pytest。

### 未完成与风险

- 未获得真实 business RAG Qwen selector/suite 精确运行授权，因此没有 M41 产品 E2E 真实质量 artifact、人工 verdict 或长期基线；fake provider 通过不证明 Qwen 输出质量、网络可用性或费用。
- deterministic required terms 只是 correctness/completeness 下限；自然语言语义仍需人工 review。未引入 LLM Judge。
- 业务 lexical、22-entry active release、默认 Router/Composer、M34 external pointer 均未改变；本模块也没有实现任何 Phase 4B Agent Loop/Subgraph/TaskState 能力。

### 必须延续的边界与决策门

- 真实首次运行只能在用户明确指定 selector、run ID、题数/调用数后执行一次；建议 smoke 后停门，不能自动扩大 core/reliability 或因 unavailable 换 ID 重跑。
- `phase4-rag-eval-business-generation-outbound-v1` 只能用于显式 Eval CLI；增加 data class、receiver、用途或把它接入普通 API，必须重新向用户确认。
- LLM Judge 仍是条件项；若未来启用，只能是独立 advisory adapter，并冻结 judge model/prompt/rubric identity，不得进入 required truth。

### 下一模块入口与必读指针

- 若继续 M41 条件项：先读本文、`docs/state/runbook.md` 的 M41 章节、`rag-current-state.md` 与 `eval-baselines.md`，再提交精确 smoke 授权参数；运行后必须生成 review bundle 并逐题复核。
- 若回到 Phase 4B：先读 `docs/phase4b-roadmap.md` 与当前 `AI_CONTEXT.md`；M41 只提供新的 RAG EvalOps consumer，不改变 B0/B1 的 runtime family、TaskState 或兼容矩阵决策。

## 技术档案 checklist（已完成）

- [x] 最终 Git 文件范围已与 notes 核对。
- [x] `CHANGELOG_INDEX.md` 已读取，并按当前目标更新完整模块记录。
- [x] `AI_CONTEXT.md` 已更新，失效的“M41 尚未立项”已清理。
- [x] `rag-current-state.md` 已更新 M41 产品 Eval 接线与出站边界。
- [x] `eval-baselines.md` 已更新 M41 合同、分账、review 与可比性，且未伪造真实基线。
- [x] `runbook.md` M41 命令与 CLI help 已对账。
- [x] 修改后的 state/changelog 已完整回读并与代码/测试一致。
- [x] 最终 `git diff --check` 与文档路径检查通过。

## State impact（最终）

- **已更新并回读**：`AI_CONTEXT.md`（当前模块/默认出站例外/最新验证）、`rag-current-state.md`（产品 RAG Eval 与安全边界）、`eval-baselines.md`（新合同/分账/可比性/无真实基线）、`runbook.md`（选择、运行、等待、Gate、review、compare、M34 history 和授权）、索引路由的 `change-history/phase4b.md`（完整模块历史）。
- **历史消歧**：更早的 M27 Text2SQL smoke 因 run ID 以 `m41-` 开头而被写成“M41 首次真实 LLM smoke”；已在原条目增加 `⚠️ 注`，明确它不是本模块 business RAG smoke，不能满足 M41 G2。
- **未命中**：`database-current-state.md`、`schema-retrieval-milvus-embedding.md`；没有数据库、seed、ORM、指标、Schema Retrieval、Milvus、embedding 或 collection 改动。

## 最终收工门禁

- `finish-module` 要求的注释检查、聚焦/受影响/全仓验证、notes 固化、CHANGELOG 路由写入、state 更新与完整回读均已完成。
- 18 个关键 plan/notes/state/catalog/CLI 路径存在性检查：`MISSING_COUNT=0`；最终 `git diff --check` 无 whitespace error，仅 Windows LF→CRLF 提示。
- `git status` 对早期测试残留 `.codex/temp_work/pytest-m41-second/` 报 `Permission denied`；该目录不在交付源码/文档范围，最终获准 pytest 使用 `.agent_work/temp/pytest-m41-full-20260822` 并已 exit 0，不影响验证结论。
- 收工时仍未执行真实 business RAG Qwen、LLM Judge、remote embedding/Milvus、LangFuse Cloud、真实 Hybrid LLM 或 M34 重跑；没有伪造或登记 M41 质量基线。

## G2 首次真实 business RAG Smoke（2026-08-22）

- 用户明确授权“执行 smoke”。本次精确解释为 M41 `smoke` selector：2 个 Scenario、最多 1 次 Qwen generation；不扩大到 Core、Diagnostic、Reliability、LLM Judge 或其他远程链路。
- 唯一 run ID：`m41-rag-smoke-20260822-01`；启动前已确认 checkpoint、artifact、report、triage 四个目标均不存在，不覆盖或恢复旧 run。
- 冻结参数：默认 Qwen `qwen3.7-plus`、`phase4-rag-e2e-v1`、`phase4-rag-eval-business-generation-outbound-v1`、timeout `60s`；report `eval/reports/m41-rag-smoke-20260822-01.md`，triage 使用同名默认路径。
- 运行纪律：只执行一次前台 CLI；若外部不可用则保留 `not_observed/inconclusive` 证据，不自动换 run ID 重跑。运行完成后先检查 manifest/artifact/report/triage，再做离线 review bundle；任何正式基线登记仍需用户决定。
- 实际运行 exit `0`，manifest/artifact 均为 `completed`；2 个 Scenario 各执行一次产品请求，唯一 generation 题成功调用 Qwen 一次，no-candidate 题 provider 调用为 0。自动 Gate `passed`：required `23 passed / 0 failed / 0 not_observed`。
- 质量退款题产品耗时约 `6.89s`；provider usage 为 prompt `660`、completion `352`、total `1012` tokens。答案覆盖订单号、照片、照片不足时补必要视频，三条 citation 均闭合到 `refund_policy_quality@2026-08-13-r1`。
- 五年整机保修题检索候选为 0，返回 `insufficient_evidence / evidence_no_candidate` 和安全兜底文本；Qwen/Composer/validator 调用均为 0，证明 no-candidate 不花 generation 费用。
- artifact identity `674de0f...a461`，文件 SHA-256 `5fd72b...ba64`；两份 checkpoint 均生成。review bundle、逐题 verdict 与 verify 已离线完成，人工结果 `2 pass / 0 fail / 0 insufficient_evidence`，来源 artifact + checkpoint 哈希校验通过。
- 解释边界：这次只证明 Smoke 两个窄场景和当前一次 provider 样本；不证明 Core、多文档、稳定性或整体业务 RAG 质量，也不自动成为正式长期基线。未重跑、未扩大 selector、未调用 Judge。
