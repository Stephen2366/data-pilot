# DataPilot RAG / 知识库当前事实速查

> 本文是知识库的当前状态入口，作用类似 `database-current-state.md`：只记录续接开发需要立刻知道的事实、证据边界和活跃风险，不代替模块 plan、notes、Eval artifact 或历史档案。涉及知识原件、active release、外部 corpus、Knowledge Tool、RAG Eval 或 M34 状态时必须先读本文。

**更新时间：2026-08-16**

## 一句话结论

DataPilot 现在有两套彼此隔离的知识运行口径：**22 条业务知识 release** 继续作为原有回归与业务默认；EnterpriseRAG-Bench 的 **36,417 篇 Confluence / Google Drive / Jira 文档**已经通过独立 external profile 接入 KnowledgeTool → Evidence → AnswerFlow → citation 链路，并形成 60 dev + 120 held-out retrieval 和 180 题 Answer Eval 证据。external 默认保持 lexical；semantic 已完成候选构建，但两个 split 都未胜出。

## 当前两套知识基线

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

recipe 的依据是同 corpus/parser/dev lexical 对照：paragraph-2400 的 coverage@20 为 `0.810417`，高于 whole-document `0.724306`、paragraph-1200 `0.793056` 和 paragraph-2400-overlap1 `0.793750`；overlap1 增加约 19% 索引字符却没有稳定收益。这只证明当前协议下的工程折中，不代表所有 embedding、语言或生产文档的全局最优切分。

## 运行时接线与安全合同

- `engine/rag/enterprise_runtime.py` 提供 metadata-only bundle、SQLite FTS adapter、命中后正文 loader，以及 Knowledge Tool / AnswerFlow factory。
- Knowledge Tool 先用 metadata 做 pre-selection ACL；只有命中的 units 才加载正文，再执行 pre-generation authorization。
- 每个 unit 使用独立 `enterprise-unit:<unit_identity>` document key，并在 Evidence 保存 source type、logical/physical document、unit 和 normalized offsets，避免同一长文多个切片覆盖 citation map。
- M31–M33 的 trusted caller、ACL 双检、Evidence ledger、active revision、outbound policy、Answer Gate 和 Citation Validator 均保留；external adapter 不能绕过。
- 方案 B 的 `ClaimDraft` 为自然语言 `text` + 同一 Evidence 中逐字存在的 `support_text` + `evidence_id` + `anchor`。只允许 whitespace canonicalization，不做 fuzzy/semantic support 放行。
- M34 Composer identity 为 `rag-qwen-evidence-support-nonthinking-unbounded-v4`：`enable_thinking=false`，应用层不发送 `max_tokens`；provider 服务端限制仍在。该配置只属于 M34 external Answer Eval，不是业务默认 Composer。

## Retrieval Eval 当前证据

> 本节保留 RAG 续接所需的快速读数；正式长期基线、共同 identity 与后续可比性规则以 `docs/state/eval-baselines.md` 为准。

固定 @20、相同 corpus/parser/unit/split；gold 不进入 runtime，只在 Tool 返回后评分。

| Adapter / split | Coverage@20 | All-gold@20 | MRR |
|---|---:|---:|---:|
| lexical dev（60） | 0.810417 | 0.766667 | 0.645303 |
| semantic dev（60） | 0.737500 | 0.700000 | 0.621421 |
| lexical held-out（120） | 0.823125 | 0.775000 | 0.723134 |
| semantic held-out（120） | 0.773958 | 0.741667 | 0.630477 |

semantic candidate 已完成 139,214/139,214 unique unit 闭合：

- semantic identity `9aec12c8d05db192cf041b89d04f880267a7c1200f5130caf4915c436b9a0e20`
- Milvus collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`
- unit-set identity `17d5af0b197ab3e4a069703d2095813f4727f1315a1e12bc06e631a9b793905f`
- manifest identity `22c573755257c47c6264218ba1bbe2e1182ccc7ad91a15bc889e3e8da56be97b`

semantic 在 dev 和 held-out 都未胜 lexical，因此保持 candidate，不切 external 默认。该结果只约束当前 embedding、recipe 和检索协议，不证明 semantic、Hybrid 或 rerank 永久无价值。

## Answer / Citation Eval 当前证据

> 本节保留当前结果与失败结构速查；正式基线登记和严格对照边界见 `docs/state/eval-baselines.md`。

full artifact：`.agent_work/temp/m34-answer-eval-full-v4.json`

artifact identity：`d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f`

| 项目 | 结果 |
|---|---:|
| AnswerFlow / provider requests | 180 / 180 |
| 自动 retry | 0 |
| provider tokens | 405,305（342,656 input + 62,649 completion） |
| `answer_status=complete` | 146/180（81.11%） |
| Composer unavailable | 10/180，其中 1 次 network error |
| Composer output contract rejected | 24/180 |
| gold document all-cited | 80/180（44.44%） |
| mean gold-document coverage | 49.3981% |
| multi-document all-gold | 2/38（5.2632%） |
| semantic questions all-gold | 15/52（28.8462%） |
| exact-fact 全量命中 | 1/180（0.6944%） |
| flow latency p50 / p95 / max | 8.428s / 13.823s / 16.931s |

`answer_status=complete` 只证明回答、support 和 citation 合同完整走完，**不等于答案正确**。exact-fact 是保守逐字检查下限，也不能反向解释为开放语义正确率只有 0.69%；M34 没有启用 LLM Judge。当前主要失败结构是 lexical top-k 漏掉 gold 文档、多文档 context packing 不足，以及 Composer 输出未满足严格 support 合同。

## 旧业务合同与回归证据

- M31 `phase4-v1`：8 Scenario / 12 required，证明既有合同与安全边界。
- M32 `phase4-rag-retrieval-v1`：6 Scenario / 20 required，证明 22 条业务语料上的确定性检索合同。
- M33 `phase4-rag-answer-v1`：9 Scenario / 60 required，证明确定性抽取式回答与 citation 闭环。
- M34 聚焦回归：M30–M34 相关套件 `158 passed`；`compileall` 通过。
- 全仓 pytest 未形成可靠终态，在非 M34 测试阶段长时间等待后停止；当前结论是 `inconclusive`，不能写成全仓通过。

## 暂不纳入 M34 的候选语料

WixQA 位于：

`D:\.Work\Practice\AI-Project\data-pilot-datasets\wixqa\2024-12-02`

当前保留 6,221 篇 Wix Help Center 文档，以及 ExpertWritten 200 题、Simulated 200 题、Synthetic 6,221 题，共约 57.5 MiB。它可用于后续客服场景或交叉基准，但不属于 M34 active corpus，尚未接入、索引或评测。

## 活跃风险与后续边界

- **召回和多文档质量**：主要缺口仍是 lexical 漏召回、selected budget 和 context packing；下一步按上方 Answer Eval 失败结构分层定位。
- **support 合同**：Composer 仍有输出被严格合同拒绝。不得通过 fuzzy/semantic 字符串放行换取表面 complete rate；若引入语义支持判断，需要独立合同和证据。
- **生产真实性**：合成语料属性见“数据与身份”；当前仍未证明真实 connector ACL、权限继承、增量同步、删除传播、企业脏数据或生产性能。
- **能力范围**：未接 `/api/query`、Router、Hybrid、UI 或通用评测平台；LangFuse Cloud 仍关闭。
- **成本**：取消 800-token 应用上限后没有固定人工费用上界；后续真实运行必须记录 provider usage，未经新计划和费用确认不得重跑大规模 generation。
- **数据纪律**：raw、extracted、SQLite profile、Milvus collection 和大 artifact 不提交 Git；项目内只保存 recipe、轻量 split、代码与必要状态文档。
- **默认切换**：semantic candidate、Hybrid、rerank 或新 recipe 必须产生新 identity，并以同 split 的单变量 A/B 和 held-out 证据经用户确认后才能切换。

历史决策、实验过程、欠费/TLS EOF/checkpoint 修正和完整 artifact 路径见 `docs/notes/m34-notes.md`，并从 `docs/state/CHANGELOG_INDEX.md` 进入对应 Phase 历史。
