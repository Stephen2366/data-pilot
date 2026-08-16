# DataPilot RAG / 知识库当前事实速查

> 本文是知识库的当前运行状态入口，作用类似 `database-current-state.md`：只记录续接开发需要立刻知道的语料、active identity、运行接线、当前结论和活跃风险。评测数字、分母、artifact 与可比性规则统一以 `eval-baselines.md` 为准；本文不建立第二份评测账本。涉及知识原件、active release、外部 corpus、Knowledge Tool 或 M34 运行状态时必须先读本文。

**更新时间：2026-08-16**

## 一句话结论

DataPilot 现在有两套彼此隔离的知识运行口径：**22 条业务知识 release** 继续作为原有回归与业务默认；EnterpriseRAG-Bench 的 **36,417 篇 Confluence / Google Drive / Jira 文档**已经通过独立 external profile 接入 KnowledgeTool → Evidence → AnswerFlow → citation 链路，并形成 60 dev + 120 held-out retrieval 和 180 题 Answer Eval 证据。external 默认保持 lexical；semantic 已完成候选构建，但两个 split 都未胜出。

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

源码固定为 tag `v1.0.0`、commit `56ba6a62cb66bf0a68ff995b1c423680980bf70a`，保留 `.git`。为避免与 Release 语料重复占用空间，当前采用 blobless sparse checkout，只取 `src/`、`answer_evaluation/` 和仓库根目录的方法说明；已核验数据导出、向量索引、向量检索及回答评测等关键源码齐全，足够用于追溯官方字段、导出逻辑和评测方法，无需再下载完整仓库 ZIP。该源码目录仅作外部方法参考，不是 DataPilot 的运行依赖；未 checkout `generated_data/`，正式语料仍以相邻 `v1.0.0/raw|extracted` 为准。

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

## 当前评测结论

> 完整数值、共同 identity、artifact 和可比性规则只在 `docs/state/eval-baselines.md` 维护。这里仅保留会影响运行和下一步开发的结论。

- 固定 @20、相同 corpus/parser/unit/split 的正式对照中，lexical 在 dev 和 held-out 都胜过当前 semantic candidate，因此 external 默认保持 lexical。
- gold 不进入 runtime，只在 Tool 返回后评分；retrieval gold coverage 不能冒充答案正确率。
- completed Answer/Citation Eval 证明真实 Tool → Evidence → AnswerFlow → citation 链路与账本可复现，但暴露出 lexical 漏召回、多文档 context packing 不足和 Composer support 合同拒绝三类主要缺口。
- `answer_status=complete` 只表示回答、support 和 citation 合同闭合，不等于答案正确；M34 没有启用 LLM Judge。

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

## 暂不纳入 M34 的候选语料

WixQA 位于：

`D:\.Work\Practice\AI-Project\data-pilot-datasets\wixqa\2024-12-02`

当前保留 6,221 篇 Wix Help Center 文档，以及 ExpertWritten 200 题、Simulated 200 题、Synthetic 6,221 题，共约 57.5 MiB。它可用于后续客服场景或交叉基准，但不属于 M34 active corpus，尚未接入、索引或评测。

## 活跃风险与后续边界

- **召回和多文档质量**：主要缺口仍是 lexical 漏召回、selected budget 和 context packing；下一步按上方 Answer Eval 失败结构分层定位。
- **support 合同**：Composer 仍有输出被严格合同拒绝。不得通过 fuzzy/semantic 字符串放行换取表面 complete rate；若引入语义支持判断，需要独立合同和证据。
- **生产真实性**：合成语料属性见“数据与身份”；当前仍未证明真实 connector ACL、权限继承、增量同步、删除传播、企业脏数据或生产性能。
- **能力范围**：M35 已接入 `/api/query` 顶层单轮 Harness 与 SQL/RAG Router；Hybrid、生产认证、UI 专项接线和通用评测平台仍未完成，LangFuse Cloud 仍关闭。
- **成本**：取消 800-token 应用上限后没有固定人工费用上界；后续真实运行必须记录 provider usage，未经新计划和费用确认不得重跑大规模 generation。
- **数据纪律**：raw、extracted、SQLite profile、Milvus collection 和大 artifact 不提交 Git；项目内只保存 recipe、轻量 split、代码与必要状态文档。
- **默认切换**：semantic candidate、Hybrid、rerank 或新 recipe 必须产生新 identity，并以同 split 的单变量 A/B 和 held-out 证据经用户确认后才能切换。

完整评测数字与 artifact 见 `docs/state/eval-baselines.md`；历史决策、实验过程、欠费/TLS EOF/checkpoint 修正见 `docs/notes/m34-notes.md`，并从 `docs/state/CHANGELOG_INDEX.md` 进入对应 Phase 历史。
