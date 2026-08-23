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

### [模块任务] M42 Phase 4B B0 前置包与 sealed Agent Eval 决策集（2026-08-23）

- **改动范围**：起始 commit 明确为 `f3cc1912a2ab1e9b87fbc3f57d4adb1cdf03df40`。新增 `engine/phase4b/`、`domain_pack/phase4b/`、Agent Scenario/reserve Eval 合同、安全 manifest、M42 rehearsal 报告、两个构建/复核脚本和 6 组测试；兼容性修改仅涉及 caller fixture 的可选 tenant、seed 的显式 profile 入口和 `AGENTS.md` 目录树。项目外另创建 `phase4b-agent-eval/v1.0.0` immutable asset；仓库不保存题面/gold/绝对路径。
- **关键记录与用户决策**：用户确认 G1–G6 均采用方案 A：独立 additive seed profile、最小 `ops + customer_service` caller、gold-first 单次默认 business retrieval、新建 Hybrid operator 合同且不改 legacy、60 题双审 sealed reserve、项目外 versioned immutable store。这样比升级 canonical seed、扩角色、挑必过题、改写 M38、复用已看题或把 gold 入库更能保持历史可比性、授权边界和 decision set 未污染。M41 的一次执行、closed-world、三态、review hash 与安全投影纪律继续沿用，但 artifact/基线不原位修改；M42 新建 `phase4b-agent-scenario-v1`。
- **实现与新发现**：`phase4b-b0-contracts-v1` identity 为 `6543883...aae6f`；显式 seed profile identity `9c49407...00673`，7/8 月真实 SQL 净退款为 `120000.00 / 180000.00`，oracle `be813a8...57ef80`，星型/宽表一致且保留 2 条负数冲销。首次构建发现 legacy 6 月 refund `processed_at` 尾巴会使 7 月多 `19920`；没有用 `REF-P4B-*` 过滤伪造产品口径，而只在新 profile 隔离副本内 retime 103 条 spillover，legacy 默认不变。business gold-first Observation `e6bc5fa...aab99` 如实记录默认 lexical 只取回 quality、漏掉 basic；零 provider、零参数/语料/ACL/release 修改。
- **Eval 与 reserve**：Agent skeleton identity `b303d4d...52982`，能力矩阵把 M43–M48 均标 unavailable。60 题 reserve identity `f70c5fc...e505`，分布 `20/20/20`，core 8 道、hard 20 道多文档；首次解封 owner 为 M46，M34/M41 historical 只作排除/回归，不作 candidate。逐文件 hash 与 source pool 已只读复验；没有运行真实 LLM、remote embedding/Milvus、held-out 或 reserve candidate，因此没有新质量基线。
- **参考资料**：按 `phase4-reference.md` 定点复核 Wren/DataAgent 的 source/index/state seam、ARAG 的 Graph/state/tools/Eval skeleton、GustoBot multi-tool/finalize 和 DB-GPT Tool/Resource/Eval 分层。借鉴内容身份、状态/执行闭集和一次执行后评分；不照搬 watcher 充当原子发布、参考项目 TaskState 字段、开放循环、notebook 简单平均或模型输出作为安全事实。具体 reference ID 与适配表见 `docs/notes/m42-plan.md`。
- **验证快照**：M42 全聚焦 `19 passed`，注释修正合同子集 `12 passed`；M1/M27/M31–M34 `179 passed, 1 warning`，M35–M41 `82 passed, 1 warning`；最终沙箱外全仓 `487 passed, 3 skipped, 1 warning in 566.30s`。首次全仓在 sandbox basetemp 因 `WinError 5` exit 1，保留为环境故障并以同命令/新 basetemp 重跑，不改实现或缩范围。warning 是既有 Starlette/httpx deprecation；compileall、diff check 与 trailing-whitespace 检查通过。
- **遗留/后续**：M42 只完成 B0，不实现 TaskState、Loop、Hybrid runtime、RAG Subgraph、durable state 或 Context Compact。M43/B1 应直接消费本模块合同/fixture；M45/B3 从真实漏选 Observation 开始且只能用预注册动作/预算；M46/B4 才能按污染账本解封 reserve。active business release、默认 lexical/Composer/model、legacy runtime 与 M34/M41 baseline 均未切换。

### [小修] Phase 4B 参考项目里程碑下沉与反走马观花门（2026-08-23）

- 重读 `docs/phase4-reference.md`，并回到 WrenAI source/index/watch、DataAgent Graph/checkpointer/replacement、ARAG Graph/state/tools/chunk/compact、GustoBot multi-tool/finalize 与 DB-GPT Tool/Resource/Eval 实际源码核对输入、状态、输出、停止及保证边界。
- `docs/phase4b-roadmap.md` 的 B0–B6 每个里程碑现都有就地参考项目小结，将 Eval 骨架、TaskState/Context、顶层 Loop、RAG 失败诊断、Subgraph、durable checkpoint 与 Compact 分别对应到精确 reference ID、借鉴 seam 和不照搬边界。
- 新增适度的源码阅读门：不强制通读整仓或固定文件数，但禁止只看 README/analysis/搜索片段；module plan/notes 必须能复核当前问题、真实调用/状态通路、规模与代表性差异、保证边界、DataPilot 适配与验证方式。特别固化 M29–M33 虽逐模块读过参考源码，仍因 11/22 条短知识无法诊断大 corpus 问题、最终需 M34 补底座的教训。
- 本次仅更新路线与历史文档，未修改代码、Eval 合同、运行默认、reference ID 定义或任何 active identity；未运行 Tool/LLM/embedding/Eval。

### [实验] M41 external dev Smoke + Basic post-fix 真实运行（2026-08-23）

- 用户授权“执行一次 rag eval smoke、basic”，按 runbook 唯一映射为 external `diagnostic_dev` Smoke 9 题与 Basic 21 题各一次；两个独立 run 均 exit 0、manifest/artifact completed，无 resume/重跑，未运行 held-out/core/hard/reliability/full/all。
- Smoke `m41-rag-external-smoke-20260823-154101`：Gate `failed`，required `96/12/0`；triage `4 passed / 2 selection / 2 citation / 1 retrieval`；9 provider responses / `20288 tokens`。来源哈希复验后的 AI reviewer verdict `3 pass / 6 fail`，其中自动 triage passed 的 qst_0318 仍因上线日期错误判 fail。
- Basic `m41-rag-external-basic-20260823-154101`：Gate `failed`，required `215/25/12`；triage `12 passed / 4 retrieval / 3 product_runtime / 1 selection / 1 citation`；21 provider responses / `47814 tokens`。AI reviewer verdict `9 pass / 9 fail / 3 insufficient_evidence`；3 个无答案均为 provider 有响应但 Composer 结构合同失败，不是 transport unavailable。
- 两套共 30 requests / `68102 tokens`，重叠 qst_0016/0019/0047 的 verdict 均一致（fail/pass/fail），但 3 题单次重叠不能冒充 Reliability。结果继续显示自动链路通过不等于语义正确，错材料/漏召回和 Composer 严格结构合同仍是主要缺口。
- artifact/report/triage/review/verdict/reviewed 证据位于 `eval/reports/m41-rag-external-{smoke|basic}-20260823-154101*`，30 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/`。两条均不自动登记正式长期基线，不改变默认 lexical/Composer/model，120 held-out 保持锁定。

### [实验] M41 external dev core 首条 post-fix 真实运行（2026-08-23）

- 用户授权“执行一次 rag eval core”，唯一映射为 external dev core：25 题 / 25 执行、`diagnostic_dev`、Qwen `qwen3.7-plus`、60s/retry0、public benchmark policy。run ID `m41-rag-external-core-20260823-151649`，artifact identity `fe498be7c4a4beff01e76fef2baed27651cc3ddefe4ca831e16bd1b3f3338fe8`，manifest/artifact/report/triage/checkpoint 全部闭合。
- 结果：Gate `failed`，required `211 passed / 58 failed / 31 not_observed`；usage `53106 tokens`（25 requests / 24 provider 成功）；AnswerFlow latency p50 `8852ms` / p95 `11973ms`；primary triage `9 retrieval / 7 product_runtime / 1 selection / 1 citation / 1 provider_or_support / 6 passed`。
- 失败明细：5 题 `composer_output_invalid`（Composer 坏结构，运行后修正的分类如实生效，下游 funnel/answer 标 `not_observed`）；3 题 `composer_unavailable`；9 题 retrieval 主因（gold 四层全缺但 `answer_present` 通过，漏召回后仍完成回答）。
- 逐题语义 verdict（AI reviewer，闭集覆盖 + 来源哈希校验，与自动 Gate 并列）：`4 pass / 13 fail / 8 insufficient_evidence`。fail 主体是“检索错文档→答偏”（qst_0199/0200/0268/0282/0289 等）和“已引用 gold 仍拒答”（qst_0198/0279）；8 例 insufficient 全部是无答案的 Composer/provider 坏结构题；4 例 pass（qst_0386/0457/0461/0462）全部检索命中 gold。自动 Gate 通过的 6 题中有 2 题 verdict 仍 fail，再次证明自动断言不能代替语义正确性。
- 结论：首条 post-fix dev core 快照再次确认 lexical 漏召回是首要质量瓶颈，且 Composer support/坏结构拒绝造成 8/25 无答案；不改变 M39 P6 `no_go`、默认 lexical/Composer/model，不自动登记正式长期基线，120 held-out 未运行。
- 执行环境插曲：首次后台启动时 PowerShell 日志重定向被沙箱拒绝（零 provider 调用、无任何 run 状态），获准 `danger-full-access` 后同 run ID 重试成功；不属于换 ID 重跑。
- 证据：artifact/report/triage/review/reviewed/verdicts 位于 `eval/reports/m41-rag-external-core-20260823-151649*`；25 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`。

### [小修] M41 RAG Eval 用户入口去歧义（2026-08-23）

- business catalog 只有 5 个业务合同场景，故将旧 smoke/core/diagnostic/reliability selectors 合并为唯一 `business`（5 题各 1 次）；保留 `--scenario` 单题入口和场景内部诊断分类，历史 Smoke artifact 不改名、不改签。
- external `diagnostic_dev` 改为 CLI 安全默认。runbook 约定裸 smoke/basic/core/hard/reliability/full 均表示 external dev；只有明确说 `held-out` 才触碰 120 题封存集，从而消除 business core 与 external core 的歧义。
- 本次只改评测入口、selector、测试与状态文档，未运行真实 Tool/LLM Eval，也未改变产品 RAG runtime、题目、评分器或既有基线。
- 验证：两个 CLI help 通过；M41 聚焦 `13 passed, 1 warning in 1.75s`，warning 为既有 TestClient/httpx deprecation；未重复执行全仓 pytest。
- 后续按用户确认将 RAG Runbook 分层重组，而非删成入门简版：前部新增自然语言映射、完整执行闭环、当前固定路径/identity 与 self-contained PowerShell 命令；中后部完整保留生命周期、fixed-route 边界、失败分层、语义 Review、strict/candidate Compare、历史回看和数据维护路由。补齐 held-out 分层题数、同 run 超时/恢复检查和完成后汇报合同。
- 文档重组零 provider 调用；四个 CLI help、当前路径/API Key 脱敏检查、immutable dev/held-out suite 数量和 Markdown/diff check 均通过，未重复运行 pytest。

### [模块任务] M41 补充：external 难度套件与候选 A/B compare（2026-08-23）

- external catalog 升级为 `phase4-rag-external-product-v2`：完整 180 题共享一个 identity，新增只由原生题型与单/多文档决定的 difficulty `basic/core/hard=64/74/42`；difficulty、60/120 partition 与 suite 三轴分离，题面/gold 仍只读 immutable dataset。
- 冻结 dev suites：smoke `9`、basic `21`、core `25`、hard `14`、reliability `6×3`、full `60`。Smoke/Reliability 只允许 dev；held-out/all 必须显式选择且真实运行仍需独立授权。报告只统计 RunSpec 选中题，并按 difficulty/partition/type/cardinality/source 输出失败层、assertion 三态和 funnel gold。
- compare 升级为 `phase4-rag-e2e-compare-v2`：默认 runtime 完全一致的 strict repeat；候选模式只允许 CLI 显式登记的 runtime 字段变化，其他协议/题集/scorer/metadata 漂移继续失败关闭。输出逐 execution `win/loss/tie/mixed/insufficient`、首失败层迁移、difficulty assertion、provider usage 和 AnswerFlow latency；自动结果不替代人工 correctness。
- 旧 `m41-rag-external-dev-20260822-01` 保持不可变、仍为 pre-fix candidate，未补造 difficulty 或升级为基线。本次零 provider 调用，未运行 120 held-out、未切 lexical/Composer/model/普通 API 默认。
- 验证：真实 immutable catalog/suite 只读闭合；旧 artifact compare-v2 self-check 为 `60 tie`；聚焦 `19 passed, 1 warning`，M31–M41 回归 `234 passed, 1 warning`，全仓 `467 passed, 3 skipped, 1 warning in 492.31s`。warning 为既有 TestClient/httpx deprecation。

### [实验] M41 external 180 题分层接入与 60 dev 真实产品链路（2026-08-23）

- 直接复用 M34 immutable 180 question set、gold、原生 `question_type × source_signature × document_cardinality` 与冻结 60 dev / 120 held-out split；不复制题面。旧 Answer + lexical retrieval artifacts 已零 Tool/LLM 投影为逐题分层历史报告，旧证据未保存的产品层与 selected/generation-visible 明示 `not_observed`。
- 新增 external catalog、eval-only fixed-RAG Router、M34 profile AnswerFlow factory 和产品 E2E CLI；每题经过 `/api/query → Harness → RAG Tool → external AnswerFlow → Qwen`。fixed route 不评测自然 Router，business 与 external 结果分账，普通 API/Router/Composer、业务 release、external lexical 默认均未改变。
- 用户授权后只运行冻结 dev 60：`m41-rag-external-dev-20260822-01` completed，60 requests / 137299 tokens；required `524 passed / 136 failed / 0 not_observed`，Gate `failed`；primary triage `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`。candidate/selected/generation-visible/cited gold 为 `35/30/30/24`。未运行 120 held-out、Judge 或重试。
- 运行暴露 5 个 provider-success Composer 坏结构被适配器误记 `harness_contract_failure`。完成 artifact 保持不可变并标记 pre-fix candidate；后续代码已将其归为 Tool/Composer observed failure、新增 `composer_support_valid`，下游按证据标 `not_observed`。因协议 identity 已变化，禁止把未来 run 与本 run 伪装成严格同协议比较。
- 验证：运行后修正 M41 聚焦 `14 passed, 1 warning`；M31–M41 受影响回归 `229 passed, 1 warning in 62.53s`；全仓 pytest exit `0`，`462 passed, 3 skipped, 1 warning in 517.37s`。warning 为既有 TestClient/httpx deprecation。
- 证据：artifact/report/triage/review 位于 `eval/reports/m41-rag-external-*`，60 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/`；闭集人工语义 verdict 已完成并通过 artifact + 60 checkpoint 哈希复验，结果 `18 pass / 26 fail / 16 insufficient_evidence`。自动分层结果与人工语义结果并列，互不改写。

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
