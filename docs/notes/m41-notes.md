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
