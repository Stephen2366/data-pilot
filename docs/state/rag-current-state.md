# DataPilot RAG / 知识库当前事实速查

> 本文是知识库的当前运行状态入口，作用类似 `database-current-state.md`：只记录续接开发需要立刻知道的语料、active identity、运行接线、当前结论和活跃风险。评测数字、分母、artifact 与可比性规则统一以 `eval-baselines.md` 为准；本文不建立第二份评测账本。涉及知识原件、active release、外部 corpus、Knowledge Tool 或 M34 运行状态时必须先读本文。

**更新时间：2026-08-23**

## 一句话结论

DataPilot 现在有两套彼此隔离的知识运行口径：**22 条业务知识 release** 继续作为业务默认，M41 的 business 小 catalog 检查 ACL/安全合同；EnterpriseRAG-Bench 的 **36,417 篇文档 / 180 题**已接入独立 external 产品链路诊断，负责大规模检索与答案质量。external 默认仍是 lexical，60 dev 已真实运行，120 held-out 未运行。

## 当前两套知识运行口径

| 项目 | 业务知识基线 | EnterpriseRAG-Bench external benchmark |
|---|---|---|
| 定位 | DataPilot 业务知识与 M30–M33 回归 | M34 大语料、长文、语义与多文档压力证据 |
| 规模 | 22 条：10 个 Markdown 文档条目 + 12 个指标投影 | 36,417 documents / 139,214 retrieval units / 180 questions |
| 权威输入 | `domain_pack/kb_docs/`、`domain_pack/metrics.yaml` | 项目外 EnterpriseRAG-Bench v1.0.0 `raw/`、`extracted/` |
| 发布/存储 | `domain_pack/kb_releases/` immutable release | 项目外 immutable SQLite external profile + benchmark 专属 pointer |
| active identity | release `7d0d0937...`；previous `4e86bdd...`；corpus `1927eb53...` | profile `e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2` |
| 默认检索 | `knowledge-deterministic-lexical-v1` | SQLite FTS5 lexical adapter，`knowledge-sqlite-fts5-unicode61-v1` |
| 回答口径 | 业务回归使用 deterministic extractive Composer | M34 Answer Eval 使用 Qwen Composer 自然改写，并受严格 `support_text` / Evidence / citation 合同约束 |
| 是否相互合并 | 否 | 否；不得修改业务 release/pointer |

`knowledge_docs` 数据库表仍只是有损 legacy projection，不是知识权威源，也不参与 Text2SQL。两套知识链路都不依赖运行时联网抓取原始文档；外部 profile 必须由显式项目外路径加载。

## EnterpriseRAG-Bench 数据与身份

外部数据根：

`D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0`

上游源码：

`D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\source`

源码固定为 tag `v1.0.0`、commit `56ba6a62cb66bf0a68ff995b1c423680980bf70a`；它只用于方法追溯，不是 DataPilot 运行依赖。正式语料以相邻 `v1.0.0/raw|extracted` 为准；checkout 方式、字段核验和构建过程见 `docs/notes/m34-notes.md`。

| 项目 | 当前事实 |
|---|---|
| 来源范围 | Confluence 5,189；Google Drive 25,108；Jira 6,120 |
| 题集 | 官方 500 题中严格筛选三来源相关的 180 题；274 unique gold IDs；0 missing |
| 冲突身份 | 3 个 logical document ID 对应多个 physical source instances；禁止覆盖写入 |
| dataset identity | `70c572328a90ec5dc380c086181af4d3706264f5aefd71c2856329f996d93cf7` |
| corpus identity | `380d0511e737a774cc3c476dcfec2e85ec52003e21270bd869d012dcdc8ec29f` |
| question-set identity | `9a21ca95995c9d2c9e962351e9e7485630233a89c280a5c928b6bc40b9cd271c` |
| split | 60 diagnostic/dev + 120 held-out；identity `f8164d3f57fe4c262f3a8f7ecd293196748d2abcbd4f387f3fbb8f50208138dd` |

原始数据是模拟 Redwood Inference 企业协作场景的**英文合成语料**。仓库级 metadata 标记 MIT，但 release 压缩包内没有独立 README/LICENSE；不能把它表述成真实企业生产数据，也不能把 repository-level license 说成压缩包内数据许可证。

## 解析、切分与 lexical profile

- parser 按 Confluence、Google Drive、Jira 显式策略恢复正文中的结构性 literal newline；不使用通用 `unicode_escape`，避免误改 JSON、代码和路径。
- parser identity：`5af364e197a26eaf6f7afc764a777454a0ea839e7dfb905844ce304a5b7f9c84`。36,417 篇全文解析完成，无空标题、空正文或 identity 漂移。
- 最终 unit recipe：`enterprise-unit-paragraph-2400-v1`，**无 overlap**；unit recipe identity `3f8eecfb09738eb3e82c16414fdd2b6ae587b1d8e35e0dbe77d8ba0c9ae1f0bd`。
- 共产生 139,214 units；每个 unit 绑定 normalized revision、content hash 和 `normalized-char:<start>-<end>` anchor，可从 Evidence 回切原文。
- lexical profile database 为 662,818,816 bytes，SHA-256 `5b88e88abaaa6ee570f10a9dc9eb57b0b4b83b28d7e62d7569c5653d728141d3`；manifest identity `546b0aeec8264c0e9d55e3093ce5a72577a2a63a594544f82cae5ad4cfb48eaf`。
- benchmark pointer identity `9908e59aa43d9fac360fbd896ec98f4e8cc935adf90c0ff126e4e2adebf2446b`；active 为上述 lexical profile，previous 为 `null`。构建物损坏时失败关闭，不自动回退未校验版本。

当前 paragraph-2400 无 overlap recipe 来自同 corpus/parser/dev 条件下的 lexical 候选对照；它在该协议下胜出，且 overlap 没有形成稳定收益。完整实验数字和历史取舍见 `docs/notes/m34-notes.md`；这仍只是当前协议下的工程折中，不代表所有 embedding、语言或生产文档的全局最优切分。

## 运行时接线与安全合同

- `engine/rag/enterprise_runtime.py` 提供 metadata-only bundle、SQLite FTS adapter、命中后正文 loader，以及 Knowledge Tool / AnswerFlow factory。
- Knowledge Tool 先用 metadata 做 pre-selection ACL；只有命中的 units 才加载正文，再执行 pre-generation authorization。
- 每个 unit 使用独立 `enterprise-unit:<unit_identity>` document key，并在 Evidence 保存 source type、logical/physical document、unit 和 normalized offsets，避免同一长文多个切片覆盖 citation map。
- M31–M33 的 trusted caller、ACL 双检、Evidence ledger、active revision、outbound policy、Answer Gate 和 Citation Validator 均保留；external adapter 不能绕过。
- 方案 B 的 `ClaimDraft` 为自然语言 `text` + 同一 Evidence 中逐字存在的 `support_text` + `evidence_id` + `anchor`。只允许 whitespace canonicalization，不做 fuzzy/semantic support 放行。
- M34 Composer identity 为 `rag-qwen-evidence-support-nonthinking-unbounded-v4`：`enable_thinking=false`，应用层不发送 `max_tokens`；provider 服务端限制仍在。该配置只属于 M34 external Answer Eval，不是业务默认 Composer。
- M37 在成功 RAG turn 外增加一次显式 opt-in follow-up。只有 22 条业务 release 的同 requirement 解释动作，才可重新加载当前 active 原件并精确核对 authority/revision/content/anchor、重新执行 ACL/用途授权后重建本轮 Evidence；identity/requirement 变化走同一 Knowledge Tool 一次。external profile 每次 follow-up 都重新检索，不进入业务 rehydrate seam。
- M38 的 Hybrid RAG branch 调用 `RAGAnswerFlow.prepare_for_hybrid()`：复用同一 Knowledge Tool、active release 与 Shared Gate，只交付本轮 `generation_visible` Document Evidence 给唯一 Hybrid Synthesizer，不运行 Composer/单路 citation validator，也不生成 RAG 子答案。
- M41 `phase4-rag-e2e-v1` 通过 eval-only app-state factory 注入 Composer，但每题仍真实经过 `/api/query → caller → turn → Router → Harness → RAG Tool → business AnswerFlow → API/Trace`；退出后恢复 app state，普通 API 继续使用 deterministic Composer。一次 execution 形成共享 Evidence，scorer/report/triage/review/compare 不重跑 retrieval 或 provider。
- 用户确认的 `phase4-rag-eval-business-generation-outbound-v1` 只允许显式 M41 CLI 把 active release 中已通过 caller/ACL/Gate、且 source class 为 `role_restricted_policy_text` / `metric_definition` 的 generation context 发给 Qwen；`security_policy`、未知类别或 identity 漂移在网络前失败关闭。它不是默认 `phase4-outbound-v1` 的扩权，也不得用于普通 API。
- M41 external `phase4-rag-external-product-v2` 直接审计完整 M34 immutable 180 question set；difficulty `basic/core/hard=64/74/42`、partition `60 dev/120 held-out` 与 suite `smoke/basic/core/hard/reliability/full` 三轴分离，不复制题面。eval-only fixed-RAG Router 只固定进入 RAG 分支，因此评测 Harness/RAG Tool/AnswerFlow，不声称验证自然语言 Router 分类。

## 当前评测结论

> 完整数值、共同 identity、artifact 和可比性规则只在 `docs/state/eval-baselines.md` 维护。这里仅保留会影响运行和下一步开发的结论。

- 固定 @20、相同 corpus/parser/unit/split 的正式对照中，lexical 在 dev 和 held-out 都胜过当前 semantic candidate，因此 external 默认保持 lexical。
- gold 不进入 runtime，只在 Tool 返回后评分；retrieval gold coverage 不能冒充答案正确率。
- completed Answer/Citation Eval 证明真实 Tool → Evidence → AnswerFlow → citation 链路与账本可复现，但暴露出 lexical 漏召回、多文档 context packing 不足和 Composer support 合同拒绝三类主要缺口。
- `answer_status=complete` 只表示回答、support 和 citation 合同闭合，不等于答案正确；M34 没有启用 LLM Judge。
- M39 只读审计已将冻结 M34 的 60 dev 分为 retrieval `11`、context/packing `13`、Composer `10`、provider unavailable `2`、not classifiable `24`；120 held-out 未逐题消费。现有材料没有“首次 Observation 选择允许动作后新增 Evidence”的证据，也没有可比额外预算，因此 P6 为严格 `no_go`，不接入 RAG Subgraph、不切 external lexical 默认。可复核报告见 [`m39-p6-readiness.md`](../../eval/reports/m39-p6-readiness.md)。
- M41 首次真实 business Qwen Smoke `m41-rag-smoke-20260822-01` 已 completed：2 个 Scenario、自动 required `23/23`、Gate `passed`、人工 review `2/2 pass`。唯一 generation 调用成功并消耗 `1012` tokens，no-candidate 题零 provider；该单次窄结果不能外推 Core、多文档、Reliability 或整体业务 RAG 质量，也尚未登记正式长期基线。
- M41 external 60 dev `m41-rag-external-dev-20260822-01` 已 completed：primary triage `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`，candidate/selected/generation-visible/cited gold 为 `35/30/30/24`（分母均 60），usage `137299` tokens；人工语义 verdict `18 pass / 26 fail / 16 insufficient_evidence`。它证明 180 题可以像 Text2SQL 一样逐层定位，且自动链路通过不能代替语义正确。
- M41 首条 post-fix dev core `m41-rag-external-core-20260823-151649` 已 completed：25 题，Gate `failed`（required 211/58/31），primary triage `9 retrieval / 7 product_runtime / 1 selection / 1 citation / 1 provider_or_support / 6 passed`，usage `53106` tokens；AI reviewer verdict `4 pass / 13 fail / 8 insufficient_evidence`。5 题 Composer 坏结构被如实标记（归类修正生效）；9 题 lexical 漏召回为最大失败层；verdict fail 主体是检索错文档→答偏与有引用仍拒答，4 例 pass 全部检索命中 gold——检索命中是语义正确的关键前提。未登记正式基线，120 held-out 未运行。
- M41 post-fix dev Smoke/Basic `m41-rag-external-{smoke|basic}-20260823-154101` 已 completed：Smoke Gate `failed`（required 96/12/0）、语义 `3 pass / 6 fail`、20288 tokens；Basic Gate `failed`（215/25/12）、语义 `9 pass / 9 fail / 3 insufficient_evidence`、47814 tokens。Basic 的 3 个无答案都是 provider 有响应但 Composer 结构合同失败；30 requests 无 transport unavailable。Smoke/Basic 重叠 3 题 verdict 一致但不构成 Reliability；均未登记正式基线，held-out 未运行。
- M42 B0 用最小 `ops + customer_service` caller 对冻结 gold-first 业务题执行一次默认 deterministic retrieval：期望 `refund_policy_basic + refund_policy_quality`，实际只选中 quality，Observation identity `e6bc5fa...aab99`，零 provider。该真实漏选是 Phase 4B B3 的诊断输入，不是新质量基线；M42 没有为通过而改变 active release、ACL、budget 或 lexical 默认。

M42 另创建 60 题 Phase 4B decision reserve，identity `f70c5fc...e505`，使用 external corpus/profile 的 20 份未进入既有 180 gold 的冻结文档；分布 basic/core/hard `20/20/20`，core 8、hard 20 道多文档。逐题材料在项目外 immutable store，仓库只保存安全 manifest。它在 M46 前保持 sealed，未运行 candidate，也不改变 M34/M41 基线或 external lexical 默认。

semantic candidate 已完成全部 139,214 个 unique unit，保留为未激活候选：

- semantic identity `9aec12c8d05db192cf041b89d04f880267a7c1200f5130caf4915c436b9a0e20`
- Milvus collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`
- unit-set identity `17d5af0b197ab3e4a069703d2095813f4727f1315a1e12bc06e631a9b793905f`
- manifest identity `22c573755257c47c6264218ba1bbe2e1182ccc7ad91a15bc889e3e8da56be97b`

该候选结论只约束当前 embedding、recipe 和检索协议，不证明 semantic、Hybrid 或 rerank 永久无价值。

## 当前相关合同

- M31 `phase4-v1`：8 Scenario / 12 required，证明既有合同与安全边界。
- M32 `phase4-rag-retrieval-v1`：6 Scenario / 20 required，证明 22 条业务语料上的确定性检索合同。
- M33 `phase4-rag-answer-v1`：9 Scenario / 60 required，证明确定性抽取式回答与 citation 闭环。
- M35 `phase4-harness-v1`：5 Scenario / 全 required，证明顶层单轮 Harness 的唯一路由、至多一个 Tool、保守终止与 Caller 失败关闭合同。
- M36 `phase4-harness-turn-v1`：8 组 sequence，证明 initial pending → 一次 resume/clear、owner/version/TTL/concurrency/budget stop 和安全 Trace；Graph 本身仍无 checkpoint。
- M37 `phase4-harness-followup-v1`：10 组 sequence / 22 turn evidence / 50 required，证明 SQL 强制重查、业务 Evidence 重水化或变化后重检索、external 强制重检索、ACL 零 retrieval 拒绝，以及 owner/delta/budget/concurrency 的 pre-Graph stop。该确定性 contract 不属于长期真实 RAG 质量基线。
- M38 `phase4-harness-hybrid-v1`：5 Scenario / 25 required，证明 canonical Hybrid 的两支 required、各一次预算、complete 的 SQL/Document 双绑定、单支 partial、SQL Guard stop 与 conflict；同样只是确定性控制/安全合同，不是开放 Hybrid 或真实 RAG 质量基线。
- M41 `phase4-rag-e2e-v1`：canonical business RAG catalog 对外只保留唯一 `business` selector（5 题各 1 次）；场景内部分类只用于诊断。冻结 product runtime、release/corpus/retrieval/Composer/policy/caller identity，建立 retrieved→selected→generation-visible→provider/support→cited→answer funnel、closed-world artifact、Gate、triage、review。external 的裸 smoke/basic/core/hard/reliability/full 默认指向 dev；`phase4-rag-e2e-compare-v2` 默认 strict repeat，只有显式声明允许变化的 runtime 字段才进入候选 A/B。
- M41 external-180：完整 180 catalog 复用同一 Evidence/Gate/review 框架，以 partition × suite 选择运行范围；dev 为 smoke 9、basic 21、core 25、hard 14、reliability 6×3、full 60。业务题与 external 题不得混成同一分数。
- M42 `phase4b-agent-scenario-v1`：sequence/turn/execution/assertion closed-world skeleton，安全投影只保存 evidence kind/ref 和三态结果；B0 capability matrix 明示 M43–M48 unavailable。它不替代 M41 单题 RAG Eval，也不证明 Agent runtime 或 RAG Subgraph 已可执行。

## 活跃风险与后续边界

- **召回和多文档质量**：主要缺口仍是 lexical 漏召回、selected budget 和 context packing；M39 已完成 P6 分层审计，但没有证据授权多步子图。单变量 Pipeline 候选须独立计划；Subgraph 重开必须先在未污染 dev 证明 Observation 驱动动作新增 Evidence，并冻结 held-out 协议和可比预算。
- **support 合同**：Composer 仍有输出被严格合同拒绝。不得通过 fuzzy/semantic 字符串放行换取表面 complete rate；若引入语义支持判断，需要独立合同和证据。
- **生产真实性**：合成语料属性见“数据与身份”；当前仍未证明真实 connector ACL、权限继承、增量同步、删除传播、企业脏数据或生产性能。
- **能力范围**：M38 已把两类 canonical SQL + Document Hybrid 接入同一 Harness，但不是自由多轮或开放跨来源研究。第二次追问、Hybrid follow-up、optional branch、生产认证、长历史、持久 checkpoint 和通用评测平台仍未完成，LangFuse Cloud 仍关闭。
- **成本**：取消 800-token 应用上限后没有固定人工费用上界；后续真实运行必须记录 provider usage，未经新计划和费用确认不得重跑大规模 generation。
- **M41 后续真实运行门**：历史 business Smoke 与旧 external 60 dev 均已按用户授权完成；当前 business 入口已合并为 5 题全量。external 默认 dev，120 held-out/all 仍须明确说出；任何真实运行都只授权一次，不得自动重跑或扩大 suite。旧 external dev artifact 是 Composer 误分类修正前、且缺 difficulty 的 pre-fix candidate；原件不得改签，未来 v2/post-fix run 不得伪装成直接复现。
- **数据纪律**：raw、extracted、SQLite profile、Milvus collection 和大 artifact 不提交 Git；项目内只保存 recipe、轻量 split、代码与必要状态文档。
- **Phase 4B reserve 污染门**：M46 前不得读取逐题 gold、运行 candidate 或用 reserve 调参；发生提前访问/调参时必须按访问状态机标记 retired，不能继续充当 decision set。M34/M41 现有 180 题只作 historical regression，不与该 60 题 reserve 合并。
- **默认切换**：semantic candidate、Hybrid、rerank 或新 recipe 必须产生新 identity，并以同 split 的单变量 A/B 和 held-out 证据经用户确认后才能切换。
- **未接入候选**：WixQA 仍只是项目外候选，未索引、未评测、也不属于 active corpus；后续若重新考虑，需另开 corpus 调查和接入计划。

完整评测数字与 artifact 见 `docs/state/eval-baselines.md`；历史决策、实验过程、欠费/TLS EOF/checkpoint 修正见 `docs/notes/m34-notes.md`，并从 `docs/state/CHANGELOG_INDEX.md` 进入对应 Phase 历史。
