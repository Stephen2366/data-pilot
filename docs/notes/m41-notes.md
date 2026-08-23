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

## M41 remediation：接入 M34 external 180 题（2026-08-22）

### Implementation checklist

- [x] 将冻结的 180 题、原生 question type/source/gold 与 60 dev / 120 held-out split 接入独立 external catalog，不复制题面形成第二事实源。
- [x] 把现有 M34 completed artifact 逐题投影为 retrieval → context/Composer → citation → answer 的离线诊断 Evidence；产品 API/Router/Harness 层诚实标 `not_observed`。
- [x] 建立 eval-only `external-180` 产品 runtime：复用 M34 external profile、lexical adapter、Qwen Composer 与 public benchmark outbound policy。
- [x] 使用显式 fixed-RAG eval route 进入 Harness；报告必须声明它不评测自然 Router 分类，禁止通过改写英文题面骗过 Router。
- [x] 保留 M34 `question_type × source_signature × document_cardinality` 分层与 60/120 冻结 split，输出逐题 triage 和分组汇总。
- [x] 补充 closed-world、identity、once-only、分层分母、旧 artifact 零重跑与产品 runtime 测试。
- [x] deterministic/离线 Gate 通过后，真实运行 60 dev；不自动执行 120 held-out，不调用 Judge，不切 external lexical 或普通 API 默认。
- [x] 记录真实运行 checkpoint、usage、failure funnel 和 review 证据；更新 runbook/state/changelog 后再次执行 `finish-module`。

### 用户确认与纠偏结论

- 用户指出 5 道业务题无法形成完整 RAG 质量诊断。此前 M41 实际只完成了 EvalOps 基础设施与最小 Smoke，不能宣称完整业务质量体系；该完成判断已纠正。
- 用户确认执行两段式补救：先零费用消费 M34 180 题既有结果，再把 external 题接入产品 Harness；真实运行只先打开冻结的 60 dev，120 held-out 保持停门。
- 分账原则：external-180 负责大规模语义/多文档/检索/回答质量，business catalog 负责 ACL、版本、安全拒绝等业务合同；两者不得混成同一总分。

### 真实 60 dev 启动前 checkpoint

- 离线 importer 已升级为 `phase4-rag-m34-historical-view-v2`：合并 M34 Answer artifact、lexical dev/held-out retrieval artifacts 与冻结 split，180/180 逐题闭合；输出 `.agent_work/temp/m41-m34-180-layered-history.json` 与 `eval/reports/m41-m34-180-layered-history.md`，零 Tool/LLM。
- external catalog 直接从项目外 immutable release 加载题面/gold，完整 audit 后生成 60 dev catalog：identity `b6254651...386b`，selector identity `50a03cfe...dc5c`；不复制题面。
- 产品接线新增 eval-only fixed-RAG Router seam、external profile AnswerFlow factory、logical document funnel 和只读 SQLite 跨 TestClient 线程开关；普通 API 为 None/default，M34 direct runtime 默认线程约束不变。
- 一题 actual external profile + fake Composer 产品验证：`qst_0016` 经过 API → fixed RAG route → Harness → RAG Tool → external AnswerFlow，5 candidate / 3 selected+generation-visible / 3 cited，response/Trace 一致。首次验证暴露 SQLite thread ownership，已用显式 `allow_cross_thread=True` 的只读 eval-only 开关修正。
- 验证：M41 聚焦 `13 passed`；M31–M41 受影响回归 `228 passed, 1 warning in 64.98s`；warning 仍为 TestClient/httpx deprecation。
- 用户已授权执行真实 60 dev。冻结 run ID `m41-rag-external-dev-20260822-01`，Qwen `qwen3.7-plus`、timeout 60s、retry0、public benchmark generation policy；最多 60 次 provider，不运行 120 held-out/Judge。
- 运行输出：checkpoint `.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`，artifact `eval/reports/m41-rag-external-artifacts/<run-id>.json`，report/triage `eval/reports/<run-id>{,-triage.json}`。任何中断按同一 run 处理，不自动换 ID。

### 真实 60 dev 结果与运行后修正

- 唯一真实运行 `m41-rag-external-dev-20260822-01` 已完成，60/60 checkpoint 与 Trace 闭合；未运行 120 held-out、未调用 Judge、未重试。artifact identity `ad1bcd7694d3b76b69748146a08107de7e7741c4cf7e59885bcc625251bf597b`，文件 SHA-256 `c78d2c609ad23ce57c344eafa640c1311ff254aa72a83e4f2fdee2d464ddb5bb`。
- 调用账本：60 requests / 60 provider responses，prompt `116120`、completion `21179`、total `137299` tokens；产品请求耗时 p50 `8183ms`、p95 `13731ms`、max `16598ms`。
- 自动 Gate 为 `failed`：required `524 passed / 136 failed / 0 not_observed`。按 primary triage 分层为 `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`；因此 60 题已能定位失败发生在哪一层，不再是 5 题 Smoke 的笼统结论。
- 运行结果为 `53 completed + 5 harness_contract_failure + 2 composer_unavailable`。逐层 gold 命中为：candidate `35/60`、selected `30/60`、generation-visible `30/60`、cited `24/60`。exact-fact `0/60` 只是保守字符串下限，不能解释成语义正确率为 0。
- 离线 review bundle 已生成并校验 artifact + 60 checkpoint hash；逐题人工 verdict 闭集覆盖并再次验证来源：`18 pass / 26 fail / 16 insufficient_evidence`。存在“自动链路通过但答案答偏”的案例，因此必须把语义 verdict 与自动 Gate 并列，不能用 `complete` 或 gold recalled 代替。
- 真实运行暴露误分类：`qst_0118/qst_0233/qst_0388/qst_0389/qst_0442` 的 provider 请求成功，但 Composer 输出违反结构合同；旧适配器让 `AnswerFlowContractError` 逃逸，最终被 Harness 误报为 `harness_contract_failure`。这 5 题的原始 artifact 保持不可变，不改签、不重跑。
- 代码已面向后续运行修正：RAG Tool adapter 把 Composer 合同错误记录为已观察的 Tool/Composer 失败；无 internal result 时从 Trace 恢复诊断；新增 `composer_support_valid` assertion，下游 answer/citation 在该失败后标 `not_observed`。普通 API、普通 Router、默认 Composer 均未改变。
- 因新增 assertion 与 catalog identity，当前代码协议已不同于上述 60 题完成 artifact；该 artifact 必须标为 **pre-fix candidate**。未来如获授权重跑，应使用新 run ID，并在 compare 时声明协议变化，禁止伪装为同协议复现。
- 运行后修正的 M41 聚焦测试：`14 passed, 1 warning in 1.66s`；受影响回归 `229 passed, 1 warning in 62.53s`；最新全仓 pytest 结果见下方，remediation 验证已闭合。

### remediation 完整 pytest 启动前 checkpoint

- 改动范围已冻结：external 180 catalog/CLI、旧 artifact 分层 importer、eval-only product seam、Composer 合同错误分层、测试、报告与 state/runbook/changelog；不含 120 held-out 重跑或默认行为切换。
- 已完成验证：CLI help、compileall、`git diff --check` 通过；最新 M31–M41 受影响回归 `229 passed, 1 warning in 62.53s`。
- 真实证据已闭合：60/60 checkpoint/Trace、completed artifact、report、triage，以及来源校验通过的人工 review `18 pass / 26 fail / 16 insufficient_evidence`。
- 已知风险：60 dev artifact 为运行后 Composer 误分类修正前的 pre-fix candidate；保留原件，不改签、不重跑。exact-fact 是字符串下限，不是语义正确率。
- 待完成：按长任务规则后台运行最新全仓 pytest，检查退出码/日志后更新最终验证结论；完成前不宣称 remediation 收工。

### remediation 完整 pytest 后台任务（已完成并检查）

- 启动时间：2026-08-23；PID `47452`。
- 执行脚本：`.agent_work/temp/run_m41_remediation_full_pytest_20260823.ps1`。
- stdout：`.agent_work/temp/m41-remediation-full-pytest-20260823.out`。
- stderr：`.agent_work/temp/m41-remediation-full-pytest-20260823.err`。
- 退出码：`.agent_work/temp/m41-remediation-full-pytest-20260823.exit`。
- 完成标记：`.agent_work/temp/m41-remediation-full-pytest-20260823.done`。
- 完成时间：`2026-08-23T00:21:37.1408737+08:00`；退出码 `0`。
- 最终结果：`462 passed, 3 skipped, 1 warning in 517.37s (0:08:37)`。
- warning：Starlette TestClient/httpx deprecation，与既有验证一致，不影响当前合同。
- 后续 runbook 拆分只修改 Markdown/导航，未改变代码或测试条件；不因此重复执行全仓 pytest。

### remediation 最终收工结论

- external 180 题已形成旧证据离线分层 + 60 dev 产品链路两级诊断；120 held-out 保持未运行。
- Composer 合同错误的未来分层已修正；完成 artifact 保持 pre-fix candidate，不改签、不重跑。
- 聚焦、受影响与全仓验证全部通过，人工 review 来源校验闭合；`finish-module` 的技术档案与验证门已完成。

## finish-docs 执行清单（Track A）

### 素材与范围核对

- [x] 已完整读取本 notes，并确认最近一次技术档案 checklist 与 remediation implementation checklist 全部为 `[x]`。
- [x] 已核对模块范围、关键决策、真实验证、风险/兼容边界、遗留和 Handoff 均有记录。
- [x] 已读取 `AI_CONTEXT.md`、`CHANGELOG_INDEX.md` 及其路由的 Phase 4B M41 技术档案，并与 notes 对账一致。
- [x] 已运行 `git status --short`、`git diff --name-only`、`git diff --name-only --cached`，确认本轮 dev-log 只使用现有 M41 技术事实。

### Track A 模块记录交付门

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、重要取舍、验证证据、未证明的边界；不适用项可以省略。
- [x] 每个编号点没有挤成一个无断点大段：编号下先写一句可独立成立的结论，再用 `- **小标题**：` 或分段落拆分不同主题；任何自然段超过约 4 行、或包含 3 个以上独立主题时必须拆分。
- [x] 正文每个英文/代码术语首次出现时紧跟括号或一句通俗解释。
- [x] 需要对照的数字优先用列表或表格呈现，没有埋在长句中间。
- [x] 新概念存在时已用通俗语言解释，没有强行编造。
- [x] “代码阅读路线”按真实调用或数据流组织，说明了看什么、为什么以及文件如何协作。
- [x] 有“设计要点”，且最后一个句号按 skill 要求写成“汪。”。
- [x] “有面试价值的亮点”可背、可独立展开，只保留真正有工程价值的内容。
- [x] 面试追问优先围绕亮点，没有强行凑数；压力追问回答按 skill 要求以“喵。”收尾。
- [x] “验证与下一步”只引用 notes 中的真实验证快照，未把未实现的运行档位写成完成。
- [x] 复制命令安全、可重复，并标明真实 LLM 命令需要单独授权。
- [x] 模块记录各小节均有服务扫读的 `**关键词**` 或 `**关键短句**`。

### 收尾检查

- [x] 已完整回读 `dev-log.md` 本次新增 M41 章节，并以第一次阅读视角检查术语、段落和扫读性；据此补充了首次出现术语的解释与未实现分层边界。
- [x] 本轮未修改 `AI_CONTEXT.md`、`CHANGELOG_INDEX.md`、`change-history/`、代码或其它文档。
- [x] `git diff --check` 通过；仅有 LF→CRLF 行尾转换提示，无内容格式错误。

## M41 补充：external 难度套件与候选对比（2026-08-23）

### Implementation checklist

- [x] 为冻结 180 题增加独立 `difficulty=basic/core/hard` 元数据；难度只由题目原生类型与单/多文档属性决定，不使用当前模型答对率，避免评测泄漏。
- [x] 保持 `difficulty`、`partition=diagnostic_dev/held_out`、`suite=smoke/basic/core/hard/reliability/full` 三个维度分离；held-out 继续显式停门，不把 held-out 偷换成 hard。
- [x] 建立完整 180 题 canonical external catalog，再由 suite 与 partition 交集生成 selector；selector 只引用冻结题目 ID，不复制题面。
- [x] 提供稳定的 external `smoke/basic/core/hard/reliability/full` 运行入口；smoke/reliability 只允许 dev，held-out/all 必须显式指定 partition。
- [x] external 报告按 difficulty 输出题数、primary failure、assertion 三态和 funnel 命中，不再只展示 strata 题数。
- [x] 增加版本化候选对比合同：默认继续 strict compare；只有显式声明 allowed runtime differences 时才允许候选 A/B，且题集、协议、scorer、assertion plan 等共同条件仍必须一致。
- [x] 候选对比输出逐题 win/loss/tie、primary failure 迁移、difficulty 分层 assertion 变化、provider usage 与可用 latency 变化；不把自动结果冒充人工语义 correctness。
- [x] 补充难度计数、suite/partition 闭集、held-out 停门、compare 非法放宽、单变量候选对比与分层报告测试。
- [x] 更新 RAG runbook 与 M41 notes 素材；本次不运行真实 Qwen、不重跑 pre-fix 60 dev、不运行 120 held-out、不切换默认 lexical/Composer/model。

### 设计素材与边界

- 冻结 180 题的推荐难度规则：`basic` 为单文档 `basic`；`hard` 为多文档，或题型属于 `completeness/conflicting_info/intra_document_reasoning/project_related`；其余单文档题为 `core`。按当前 immutable question set 计数为 basic `64`、core `74`、hard `42`；dev 为 `21/25/14`，held-out 为 `43/49/28`。
- `source_types` 只用于 smoke 分层抽样和报告观察，不参与难度判定；Confluence/Jira/Google Drive 是来源差异，不天然代表难度。
- candidate compare 的核心不是“忽略 runtime 不同”，而是把允许变化的字段写进实验合同。未声明的任何 runtime 漂移继续失败关闭；多变量虽可诚实比较总体候选，但不能宣称单一组件因果。
- 已完成的 `m41-rag-external-dev-20260822-01` 是 pre-fix candidate，不能自动升级为当前协议 baseline。本补充只提供以后建立 post-fix baseline 与模块 A/B 的工具，不在没有新授权时创建真实基线。

### 实施结果与验证素材

- external catalog 升级为 `phase4-rag-external-product-v2`：catalog identity 绑定完整 180 题、split 与 `enterprise-rag-difficulty-v1`；partition/suite 只改变 selector，不再产生不同题库。
- 固定 dev suites：Smoke `9×1`；Basic `21×1`；Core `25×1`；Hard `14×1`；Reliability `6×3=18`；Full `60×1`。Smoke 覆盖三种难度和三类单来源，并包含跨来源冲突、completeness 与 intra-document reasoning。
- report 只统计 RunSpec 真正选中的题，按 difficulty/partition/type/cardinality/source 输出 execution 数、primary diagnosis、required 三态与 retrieved/selected/visible/cited gold；避免 canonical 180 catalog 把未运行题混进分母。
- compare 升级为 `phase4-rag-e2e-compare-v2`：无声明时仍 strict repeat；候选模式只放行 `--allow-runtime-difference` 明确列出的 `RAGResolvedRuntime` 字段。输出 paired `win/loss/tie/mixed/insufficient`、首失败层迁移、difficulty assertion、usage 和 AnswerFlow latency；人工 correctness 仍独立。
- 真实 immutable dataset 只读核验：catalog `180`，difficulty `64/74/42`；dev suites 数量与上方冻结值一致。旧 60 dev artifact 自比较通过 compare-v2，结果 `60 tie`、usage/latency delta 为零；旧 artifact 没有 difficulty 字段，因此诚实归入 `not_applicable`，未改签历史证据。
- 聚焦验证：`19 passed, 1 warning in 1.68s`。M31–M41 受影响回归：`234 passed, 1 warning in 61.56s`。warning 均为既有 Starlette TestClient/httpx deprecation。
- CLI help、旧 artifact 离线 self-compare 与 immutable catalog/suite 只读检查通过；全程零 Tool/LLM provider 调用，没有真实 Eval 授权扩张。

### 全仓 pytest 启动前 checkpoint

- 关键决策：难度、partition、suite 三轴分离；候选 compare 使用显式 allowlist，而不是无条件忽略 runtime 漂移；旧 pre-fix artifact 保持不可变。
- 改动范围：RAG Scenario/RunSpec metadata、external canonical catalog/selectors/CLI、分层报告、compare-v2/CLI、M41 tests 与 RAG runbook；普通 API、Router、retrieval、Composer、active release 和 external profile 均未修改。
- 已完成验证：M41 聚焦 `19 passed`；M31–M41 受影响回归 `234 passed`；真实 180 metadata 与 suite 数量只读闭合；CLI/self-compare/diff check 通过。
- 已知风险：尚无当前 v2/post-fix 真实 external dev baseline；未来建立 baseline 仍需用户单独授权。自动 paired verdict 不代表自然语言 correctness，仍须并列人工 review。
- 待完成：后台全仓 pytest；完成并检查退出码后，更新最终验证结论和当前 Phase 技术档案。后台任务完成前不宣称本补充最终完成。

### 全仓 pytest 后台任务（已完成并检查）

- 启动时间：2026-08-23；PID `50660`。
- 执行脚本：`.agent_work/temp/run_m41_supplement_full_pytest_20260823.ps1`。
- stdout：`.agent_work/temp/m41-supplement-full-pytest-20260823.out`。
- stderr：`.agent_work/temp/m41-supplement-full-pytest-20260823.err`。
- 退出码：`.agent_work/temp/m41-supplement-full-pytest-20260823.exit`。
- 完成标记：`.agent_work/temp/m41-supplement-full-pytest-20260823.done`。
- 完成时间：`2026-08-23T01:22:51.9579888+08:00`；进程已退出，退出码 `0`。
- 最终结果：`467 passed, 3 skipped, 1 warning in 492.31s (0:08:12)`。
- warning：既有 Starlette TestClient/httpx deprecation，不影响本次合同。

### M41 补充最终结论

- external 180 题已经具备稳定、互斥的 basic/core/hard 难度字段，以及与 partition 正交的 smoke/basic/core/hard/reliability/full 运行套件。
- 后续模块可以在相同题集/协议/scorer 下，通过显式 runtime allowlist 比较候选；未声明漂移继续失败关闭。自动 paired 结果仍须与人工语义 review 并列。
- 聚焦、M31–M41 受影响回归和全仓验证全部通过；本补充没有创建真实 post-fix baseline，没有运行 120 held-out，也没有改变任何产品默认。

## M41 补充：RAG Eval 用户入口去歧义（2026-08-23）

### Implementation checklist

- [x] 将 business RAG 的 smoke/core/diagnostic/reliability 四个用户套件合并为唯一 `business` 套件，覆盖现有 5 个业务合同场景、每题执行 1 次。
- [x] 保留 `--scenario` 精确诊断入口，但删除旧 business selector，避免 `core` 同时指 business 与 external。
- [x] 将 external 的 `diagnostic_dev` 设为 CLI 安全默认值；裸 `smoke/basic/core/hard/reliability/full` 统一解释为 external dev 套件。
- [x] 在 RAG runbook 写清自然语言授权映射，以及 dev（练习诊断集）与 held-out（封存终考集）的区别和使用纪律。
- [x] 更新 M41 聚焦测试与长期状态文档；只运行本次改动直接相关的测试，不重复执行全仓 pytest，不运行真实 Tool/LLM Eval。

### 设计判断

- business catalog 只有 5 个场景，重点是 release、ACL、安全拒绝和业务合同，不需要再向用户暴露四档套件。合并后仍可用 `--scenario` 定位单题，诊断能力没有丢失。
- `basic/core/hard` 是 external 180 题的难度；`smoke/reliability/full` 是 external 的运行规模或重复协议。它们都不再与 business 共用名称。
- external 默认使用 `diagnostic_dev`，因此用户日常只说“执行 core RAG Eval”即可；只有准备进行最终封存验证时，才需要明确说 `held-out`。

### 实施与验证结果

- `eval.run_rag_eval` 现在只接受 `--suite business` 或精确 `--scenario`；不传 suite 时也默认 business。旧四个 selector 文件已删除，新增 `rag-business` 统一 selector。
- `eval.run_rag_external_eval --partition` 不再 required，安全默认值为 `diagnostic_dev`；`held_out/all` 仍必须显式传入。
- 两个 CLI help 检查通过；M41 business lifecycle、review/compare 和 external suite 聚焦测试为 `13 passed, 1 warning in 1.75s`。warning 是既有 Starlette TestClient/httpx deprecation。
- 第一次 pytest 因项目既有共享 `.agent_work/temp/pytest-tmp` 被 Windows 锁定，9 项停在 fixture setup、4 项通过；改用新的专用 `--basetemp` 后 13 项全部通过。该问题不是代码测试失败，未删除或修改被锁目录。
- `git diff --check` 通过，仅有既有 LF→CRLF 提示；本轮没有调用 Tool/LLM，没有真实 Eval 成本，也没有重复跑全仓测试。

## M41 补充：RAG Runbook 分层重组（2026-08-23）

### Implementation checklist

- [x] 将自然语言授权映射与执行闭环移到文档前部，使入门级 AI 先确定“跑什么、跑多少、不能扩大什么”。
- [x] 补齐项目 Python、external dataset/profile root、profile identity、唯一 run ID 规则和可直接复制的 Business/External PowerShell 命令。
- [x] 补齐前台超时/后台运行后的同 run 检查顺序，以及完成后必须汇报的 Gate、usage、失败层、artifact identity 与 review 状态。
- [x] 保留并重新组织 fixed-RAG route、三轴分离、held-out 停门、artifact 生命周期、失败分层、人工 review、严格/候选 compare 和可比性边界。
- [x] 只删除重复表达；历史旧结果与一次性维护命令不丢失，降到后部“历史回看与数据维护”区域并继续保留路由。
- [x] 回读完整 RAG Runbook，检查命令与当前 CLI 一致，运行 CLI help 和 `git diff --check`；不执行真实 Tool/LLM Eval，不重复运行 pytest。

### 修改原则

- “入门友好”只改变阅读顺序和复制成本，不降低评测合同。快速入口负责执行，后续章节负责解释为什么安全、怎样诊断和什么结论不能说。
- Runbook 保存稳定操作步骤；当前运行身份和历史数字仍分别由 `rag-current-state.md`、`eval-baselines.md` 维护，但日常命令必需的当前 external 路径/identity 在 Runbook 提供一份明确快照，并要求运行前与状态文档核对。

### 实施与验证结果

- RAG Runbook 改为“快速映射 → 完整闭环 → 固定参数/完整命令 → 生命周期与汇报 → 技术边界 → Review → Compare → 历史维护”的分层结构；不是删成简版操作卡。
- 保留旧文档的产品链路、出站权限、fixed-RAG route、三轴、held-out、artifact、失败漏斗、人工复核、严格/候选 compare、历史 M34 回看和数据维护边界；只合并了重复的授权/dev/held-out 表述。
- 新增 self-contained PowerShell 命令，避免 AI 在不同 shell 之间丢失变量；明确当前 dataset root、profile root、profile identity、唯一时间戳 run ID、manifest 检查和结果汇报字段。
- 当前 Python/dataset/profile 路径检查通过，Settings 只输出 `DASHSCOPE_API_KEY=configured`、未输出密钥。Business/External/Review/Compare CLI help 与文档一致。
- immutable catalog 只读核验：dev basic/core/hard/full 为 `21/25/14/60`，held-out 为 `43/49/28/120`；与 Runbook 表格一致。一次初始只读核验误用了不存在的 `execution_keys()` 辅助方法，未触发 Eval；改为 selector 字段后核验通过。
- Markdown fence 闭合，`git diff --check` 通过；没有运行真实 Tool/LLM Eval，没有 provider 消耗，也没有因纯文档重组重复运行 pytest。

## M41 真实运行：external dev Smoke + Basic（2026-08-23）

### 后台任务启动前 checkpoint

- 用户授权范围：external `diagnostic_dev` 的 `smoke` 与 `basic` 各运行一次；Smoke 为 9 题/9 executions，Basic 为 21 题/21 executions。两个 suite 使用独立 run ID；不运行 held-out、core、hard、reliability、full/all，不自动重跑。
- run IDs：`m41-rag-external-smoke-20260823-154101`、`m41-rag-external-basic-20260823-154101`。
- resolved input：项目 Python `fastapi0614`；dataset root `D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0`；active profile `e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2`；Qwen `qwen3.7-plus`；external dev 默认 partition。
- 启动前检查：Python、dataset、profile root/profile JSON 均存在，active pointer 与 profile identity 一致，DashScope API Key 已配置且未输出密钥；两个 run ID 均无 artifact/checkpoint/report 冲突。
- 已知现场：系统中存在两个 2026-08-22 启动的旧 Python 进程；当前权限无法读取其命令行，但本次使用全新 run ID 和独立 checkpoint/artifact。未对旧进程做任何操作。
- 执行方式：按顺序在一个隐藏后台 PowerShell 中先 Smoke、后 Basic；分别保存 stdout、stderr、exit code，并写 overall exit 与 done marker。当前状态为“待启动”，不得提前记为 completed 或通过。
- 风险与停门：任何 provider unavailable、合同失败和质量失败均保留原证据，不换 ID 重跑；完成后必须读取两个 manifest/artifact/report/triage、usage 与失败层，再判断结果。旧 pre-fix 60 dev 不是当前协议兼容基线，本次单次绝对结果不能直接宣称模块变好。

### 后台任务（已完成；启动记录保留，结果见下）

- 启动时间：2026-08-23 15:41；后台 PID `46184`，启动后 `HasExited=False`。
- 执行脚本：`.agent_work/temp/run_m41_rag_smoke_basic_20260823_154101.ps1`；PowerShell parser 语法检查通过。
- Runner stdout/stderr：`.agent_work/temp/m41-rag-smoke-basic-20260823-154101-runner.out`、`.agent_work/temp/m41-rag-smoke-basic-20260823-154101-runner.err`。
- Smoke stdout/stderr/exit：`.agent_work/temp/m41-rag-external-smoke-20260823-154101.out`、`.err`、`.exit`。
- Basic stdout/stderr/exit：`.agent_work/temp/m41-rag-external-basic-20260823-154101.out`、`.err`、`.exit`。
- Overall exit/done：`.agent_work/temp/m41-rag-smoke-basic-20260823-154101.exit`、`.done`。
- Smoke manifest/artifact：`.agent_work/temp/m41-rag-external-checkpoints/m41-rag-external-smoke-20260823-154101/manifest.json`、`eval/reports/m41-rag-external-artifacts/m41-rag-external-smoke-20260823-154101.json`。
- Basic manifest/artifact：`.agent_work/temp/m41-rag-external-checkpoints/m41-rag-external-basic-20260823-154101/manifest.json`、`eval/reports/m41-rag-external-artifacts/m41-rag-external-basic-20260823-154101.json`。
- 当前结论：任务已成功启动，按顺序先 Smoke 后 Basic；结果仍是“运行中，待检查”，不得提前宣称 completed、通过或失败。用户后续要求继续时，先读 overall done/exit、两个 suite exit、manifest、artifact 和必要日志，再更新最终结论。

### 运行结果（completed，2026-08-23）

- 后台于 `2026-08-23T15:46:50+08:00` 完成；Smoke、Basic 和 overall exit 均为 `0`，两个 manifest/artifact 均为 `completed`，未发生 resume 或重跑。held-out/core/hard/reliability/full/all 均未运行。
- Smoke `m41-rag-external-smoke-20260823-154101`：9/9 executions 均 completed/complete，artifact identity `9e31fab3faf836b8509e227000261da89023df074d8aa50322f71b95a4a3b7f4`。Gate `failed`，required `96 passed / 12 failed / 0 not_observed`；triage `4 passed / 2 selection / 2 citation / 1 retrieval`。9 requests 全部 provider response 成功，prompt `17364` + completion `2924` = `20288 tokens`；provider-attempt latency p50 `6285ms` / p95 `15019ms`。
- Smoke 逐题语义 review 闭集覆盖并通过 artifact + 9 checkpoint 哈希复验：`3 pass / 6 fail / 0 insufficient_evidence`。通过为 qst_0019/0386/0461；主要错误包括 30 天规则答反、prefix cache 权衡答偏、遗漏 30–120 秒 jitter、缺失 GiB 费率、rollback 不完整和 rollout 日期错误。自动 triage passed 的 qst_0318 仍因日期错误被人工判 fail。
- Basic `m41-rag-external-basic-20260823-154101`：21 executions 中 `18 completed / 3 failed`，artifact identity `10836eef6c459606dde95a3c299f7233d389ded68fb8df2f29ef6a1f96799c28`。Gate `failed`，required `215 passed / 25 failed / 12 not_observed`；triage `12 passed / 4 retrieval / 3 product_runtime / 1 selection / 1 citation`。21 requests 均收到 provider response，prompt `41367` + completion `6447` = `47814 tokens`；provider-attempt latency p50 `6090ms` / p95 `10433ms`。
- Basic 三个 product runtime failure：qst_0086、qst_0118 为 `composer_output_invalid`，qst_0091 为 `composer_response_invalid_cardinality` 投影的 `composer_unavailable`；均是 provider 有响应但结构合同失败，不是网络 unavailable。
- Basic 逐题语义 review 闭集覆盖并通过 artifact + 21 checkpoint 哈希复验：`9 pass / 9 fail / 3 insufficient_evidence`。3 个 insufficient 正是上述无答案 Composer 失败；fail 集中在漏召回/错材料后答偏或拒答，以及自动链路通过但关键事实缺失。Smoke 与 Basic 重叠的 qst_0016/0019/0047 在两次运行中的人工 verdict 一致（fail/pass/fail），但 3 题一致性不等于 Reliability 证明。
- 两套合计 30 requests / `68102 tokens`，没有 transport external unavailable。两个 Gate 均 failed，说明 CLI/产品链路成功完成不等于质量通过；自动断言也再次不能替代语义 review。
- 证据：artifact/report/triage 位于 `eval/reports/m41-rag-external-{smoke|basic}-20260823-154101*`；review/verdict/reviewed/reviewed-verified 同前缀；30 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`。当前均是 post-fix dev 快照，不自动登记正式长期基线，也不能与旧 pre-fix 60 dev 假装严格可比。

## M41 授权运行 external dev core（2026-08-23）

- 用户授权原话："执行一次 rag eval core"。按 runbook-rag「AI 快速执行入口」唯一映射为 external dev core：25 题 / 25 次执行，partition 默认 `diagnostic_dev`；Qwen `qwen3.7-plus`、timeout 60s、retry0、public benchmark generation policy。不运行 held-out、不调用 Judge、不扩大 suite。
- 冻结 run ID：`m41-rag-external-core-20260823-151649`（时间戳唯一；artifact/checkpoint 目标均不存在，无覆盖、无恢复旧 run）。
- 运行预检：Python / DatasetRoot / ProfileRoot 三个 `True`，`DASHSCOPE_API_KEY=configured`。
- 运行命令：`python -m eval.run_rag_external_eval --dataset-root <dataset-root> --profile-root <profile-root> --profile-identity e8783fe0... --suite core --run-id m41-rag-external-core-20260823-151649 --report eval/reports/m41-rag-external-core-20260823-151649.md`
- 后台脚本：`.agent_work/temp/run_m41_external_core_20260823-151649.ps1`；stdout `.agent_work/temp/m41-rag-external-core-20260823-151649.out`；stderr `.agent_work/temp/m41-rag-external-core-20260823-151649.err`；退出码 `...exit`；完成标记 `...done`。
- 状态：**运行中，待检查**。中断按同一 run 处理（同 RunSpec + `--resume` 合法前缀），不得换 ID 重跑。
- 预期产物：checkpoint/Trace 在 `.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`，completed artifact 在 `eval/reports/m41-rag-external-artifacts/<run-id>.json`，triage 自动生成 `eval/reports/<run-id>-triage.json`。完成后离线生成 review bundle 与 verdict；是否登记基线由用户决定。
- 执行环境插曲：第一次后台启动（`pwsh-1`）在 PowerShell 重定向日志文件时被沙箱拒绝（`...out is denied`，workspace-write 模式），未进入 Python、零 provider 调用、无 manifest/checkpoint/artifact 残留；确认无部分状态后按沙箱规则以 `danger-full-access` 重试同一脚本同一 run ID（`pwsh-2`）。run 从未开始，这不属于换 ID 重跑。

### 运行结果（completed，2026-08-23）

- exit 0、manifest/artifact `completed`；artifact identity `fe498be7c4a4beff01e76fef2baed27651cc3ddefe4ca831e16bd1b3f3338fe8`，文件 `eval/reports/m41-rag-external-artifacts/m41-rag-external-core-20260823-151649.json`。
- Gate `failed`：required `211 passed / 58 failed / 31 not_observed`（共 300）；advisory `34 passed / 31 failed / 10 not_observed`（75）。
- usage：25 requests / 24 successful responses；prompt `45139` + completion `7967` = **53106 tokens**。
- latency（AnswerFlow，20 样本）：p50 `8852ms`、p95 `11973ms`。
- 状态分布：execution `17 completed / 8 failed`；answer `17 complete / 8 no_answer`。
- primary triage：`9 retrieval / 7 product_runtime / 1 selection / 1 citation / 1 provider_or_support / 6 passed`。
- 失败明细：5 题 `composer_output_invalid`（qst_0181/0215/0233/0236/0389，Composer 坏结构，本次已如实标记、下游 funnel/answer 全部 `not_observed`）；3 题 `composer_unavailable`（qst_0248/0252/0387，其中 0248/0252 的 retrieved/selected/visible gold 仍 observed failed）；9 题 retrieval 主因（gold 四层全缺但 `answer_present` 通过，即漏召回后仍完成回答）；qst_0200 主因 selection、qst_0211 主因 citation。
- review bundle 已生成并校验（artifact + 25 checkpoint 哈希）；逐题语义 verdict 由 AI reviewer 完成、闭集覆盖并合并（`eval/reports/m41-rag-external-core-20260823-151649-reviewed.json`，来源再校验通过）：**pass 4 / fail 13 / insufficient_evidence 8**。fail 主体是"检索错文档→答偏"（qst_0199/0200/0268/0282/0289 等）与"已引用 gold 仍拒答"（qst_0198/0279）；8 例 insufficient 全部是无答案的 Composer/provider 坏结构题；4 例 pass（qst_0386/0457/0461/0462）全部检索命中 gold。自动 Gate 通过的 6 题中有 2 题 verdict 仍 fail（qst_0198/0388），再次证明自动断言 ≠ 语义正确。自动 Gate 与 verdict 并列，互不改写。
- 该 run 是当前 v2/post-fix 协议（difficulty 三轴 + `composer_support_valid`）下第一条 external dev core 快照；不自动成为正式长期基线，登记与否由用户决定；120 held-out 未运行。
