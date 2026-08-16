# M34 EnterpriseRAG-Bench 真实语料接入开发记录

> 当前状态：实现与 M34-F 已完成；M34-C lexical/semantic candidate、M34-D 真实链路、M34-E 180 题 retrieval 证据、M34-F 180 题 Answer/Citation artifact 均已落地。M34-G 聚焦回归通过；全仓 pytest 因环境遗留权限/等待问题 inconclusive。当前 external 默认仍是 lexical，semantic 不胜出，Answer 质量边界已如实记录。

## Implementation checklist

### M34-A：数据审计、题集与身份基线

- [x] 复核项目外 `v1.0.0` 目录、release 资产、许可/归属说明与三来源 allowlist。
- [x] 实现 strict closed-world dataset scanner：36,417 source instances、180 questions、274 gold IDs、0 missing、3 conflict IDs。
- [x] 冻结 logical document identity 与 physical source-instance identity，禁止冲突 ID 覆盖写入。
- [x] 形成轻量 dataset manifest/inspect 输出和稳定 corpus identity；原始大文件不进入 Git。
- [x] 为路径/资产漂移、未知来源、非法编码、空 `source_types`、gold 缺失、重复题目和冲突保留编写失败关闭测试。
- [x] 调查题型/来源/文档数/长度分布并确认 split 方案：60 diagnostic/dev + 120 held-out；required contract/security 使用独立 fixtures。

### M34-B：解析、结构 profiling 与 unit 候选

- [x] 实现 Confluence、Google Drive、Jira source-aware parser/normalizer。
- [x] 对字面量 `\\n`、标题/段落、空文档、异常编码、极短/极长文档输出质量统计。
- [x] 建立 raw → normalized document → retrieval/context unit → source anchor 的稳定往返合同。
- [x] 比较少量、可解释的 chunk/unit 候选；一次只改变 unit recipe。
- [x] 记录候选的 gold coverage、context 规模、anchor 完整性和构建成本，形成 recipe 决策材料。
- [x] 用户确认 `enterprise-unit-paragraph-2400-v1`、无 overlap；允许进入 external candidate build。

### 决策门与后续切片

- [x] **G-M34-1**：用户确认独立 benchmark profile；业务 22 条 active release 保持默认且不合并。
- [x] **G-M34-2**：semantic candidate 已完成但 dev/held-out 均不胜 lexical；external 默认保持 lexical。
- [x] **G-M34-3**：embedding 已按用户确认执行；generation 仅 3 题 smoke，Judge 保持关闭。
- [x] M34-C：lexical 完整 corpus candidate/原子 profile 与 semantic candidate 均完成；semantic collection 不激活。
- [x] M34-D：Tool/Evidence/AnswerFlow 本地真实接线完成；remote Composer smoke 暴露并保留 extractive 合同边界。
- [x] M34-E：60 dev + 120 held-out retrieval artifacts 完成，semantic/lexical 对照可复算。
- [x] M34-F：180 题真实 Answer/Citation full Eval 完成；结果显示链路成立但 correctness/多文档/semantic 仍未证明提升。
- [x] M34-G：M30–M34 与 M31–M33 聚焦回归 158 passed；compileall passed；全仓 pytest 曾因项目外遗留 `\.agent_work/temp/pytest-tmp` 无权限清理并在非 M34 测试处长时间等待，已停止该进程，不能宣称全仓通过。
- [x] 完成实现后运行验证，并按 `finish-module` skill 做注释审计、验证快照和 handoff。

## finish-module 固化快照（2026-08-16）

### 阶段 1：注释查漏补缺

- 新增 M34 文件均有模块级职责说明；为 Answer Eval、remote Composer、case split、retrieval Eval、smoke/checkpoint 入口补充了缺失的函数 docstring。
- 关键概念已在代码注释解释：support_text 与最终自然回答的分离、gold 后置评分、逐题原子 checkpoint、multiset gold coverage、provider token telemetry、非思考模式和 whitespace-only canonicalization。
- 四遍扫描未改写 M31–M33 用户既有注释；剩余私有统计/解析 helper 结构短小且由命名与邻近调用自解释，未为凑数量添加噪声注释。

### 阶段 2：验证快照

- `pytest --basetemp .agent_work/temp/pytest-run-m34 ...`（M30–M34 + M31–M33 聚焦文件）：`158 passed in 4.47s`。
- `pytest tests/test_m4_nl2sql.py ...` 生成/安全聚焦套件：最终 `40 passed`；新增 Answer Eval 单测在聚焦总数内通过。
- `compileall -q engine app eval scripts tests`：`compileall passed`。
- `git diff --check`：仅 CRLF/LF warning，无 whitespace error。
- 全仓 `pytest --basetemp .agent_work/temp/pytest-run-full -q`：未形成可靠终态；进程在非 M34 测试阶段长时间无输出/无 TCP 子连接，已停止。旧 `pytest-tmp` 目录权限错误是环境遗留，不属于本模块代码；因此全仓结论为 inconclusive，不写成通过。
- 180 题 Answer Eval：`completed`、180 flow calls、180 provider requests、405,305 total tokens，artifact identity `d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f`；离线重建 identity match。

### 参考资料

- EnterpriseRAG-Bench 官方数据/题集与仓库 metadata；没有提交 raw/extracted/大索引文件。
- 阿里云百炼官方模型价格、Qwen OpenAI-compatible `enable_thinking` 和结构化输出文档；只用于确认 M34 专用出站模式和成本口径，没有照搬其应用架构。

## Handoff（下一模块交接）

### 已完成且后续可以依赖

- 独立 benchmark external profile、lexical runtime、semantic candidate、KnowledgeTool→Evidence→AnswerFlow→citation 接线。
- `enterprise-rag-retrieval-eval-v1` 60 dev + 120 held-out retrieval artifacts。
- `enterprise-rag-answer-eval-v1` 180 题 completed artifact、逐题 gold 后置评分、token/失败/延迟 telemetry 和可复算 identity。
- 方案 B Composer 合同：自然语言 text + 同 Evidence 的逐字 support_text；权限、ledger、citation、业务 22 条 release 不变。

### 下一模块建议入口

- 建议首先解决的主要问题：针对 full Eval 失败簇改善 gold document 召回和多文档 context packing，再重新做同 split 的 retrieval/Answer 对照。
- 建议从 `enterprise_retrieval_eval.py` 的 semantic/multi-document 分组、`m34-answer-eval-full-v4.json` 的 cited coverage 与 `KnowledgeTool` selected budget 开始。
- 原因：当前真实证据已证明工程链路不是主要缺口，主要缺口是 lexical top-k 漏召回和 support contract rejection。

### 未完成、未证明与当前风险

- 未完成：全仓 pytest 的可靠终态；finish-docs/accept-module 尚未执行。
- 尚未通过真实验证证明：EnterpriseRAG 语料代表生产企业噪声、semantic candidate 优于 lexical、开放式答案语义正确率、生产 connector ACL、长期成本/性能。
- 活跃风险：full Answer Eval 仅 44.44% 题目引用齐 gold 文档；multi-document all-gold 5.26%；semantic all-gold 28.85%；24/180 support contract rejected、10/180 Composer unavailable。

### 必须延续的决策与边界

- 外部 benchmark 保持独立 profile，不合并 22 条业务 active release。
- semantic collection 保持 candidate，不切 external 默认；lexical 是当前 external 默认 adapter。
- 不把 answer_status=complete 当作 gold correctness；所有质量结论必须引用 full artifact 分组数据。
- 不提交 raw/extracted/SQLite/Milvus 大文件；Judge、Router、Hybrid、UI 和通用评测平台仍不在 M34 范围。

### 待触发的决策门

- 决策门：是否投入下一模块解决召回/多文档 context packing；触发条件：需要提高 full artifact 的 gold coverage 或 multi-document all-gold。
- 触发前允许做：离线失败簇分析、retrieval recipe 对照和本地合同测试。
- 触发前禁止做：未经新计划与授权再次跑大规模 provider、切换 semantic 默认、放宽 support/citation 安全合同。

### 下一轮规划必读指针

- `docs/notes/m34-plan.md`：M34-E/M34-F 验收门、G-M34-2 和 G-M34-3 决策门。
- `docs/notes/m34-notes.md`：full Answer Eval 结果、失败簇、Handoff 与成本边界。
- `.agent_work/temp/m34-answer-eval-full-v4.json`：180 题 completed artifact 与 artifact identity。
- `engine/rag/enterprise_retrieval_eval.py`：分组 coverage/MRR 口径；`engine/rag/enterprise_answer_eval.py`：gold 后置评分和 closed-world 门。

## finish-docs 执行清单

### dev-log 交付门（必须执行）

- [x] 有“简述”和“先用大白话讲”
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] 每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、为何不选更宽松方案（如适用）、真实验证证据、尚未证明的边界。
- [x] 本模块首次出现的术语保留英文或代码名，并紧跟一句普通话解释。
- [x] “新概念”解释至少一个本模块新术语
- [x] “代码阅读路线”是按调用顺序的编号列表，不止说明“看什么”，还需要说明“为什么/解决了什么”
- [x] 有“设计要点”
- [x] “面试怎么讲”有一段可直接复述的模块叙述，说明目标、方案、验证和边界。
- [x] 至少有 1 个 `[基础追问]` 和 1 个 `[工程/深挖追问]`；架构、评测、安全等复杂模块优先增加 `[压力追问]`。
- [x] 追问基于真实实现与证据，覆盖设计取舍、失败场景或后续边界。
- [x] 不写纯定义、送分、显而易见、凑数的低价值问题。
- [x] “验证与下一步”只引用 notes.md 中真实验证快照
- [x] 有可复制命令和本地启动体验/无独立入口说明
- [x] 未把确定性测试写成真实 LLM 能力结论
- [x] 模块记录的各个小节都用 `**...**` 加粗标出“服务于扫读抓重点”的关键词或关键短语。

### 三文档交付门（必须执行）

- [x] `AI_CONTEXT_CHANGELOG.md`：本次完整模块有新的 `###` 条目，包含改动范围、关键记录、参考资料、验证快照、遗留/后续。
- [x] `AI_CONTEXT_CHANGELOG.md`：改动范围已经通过 `git status --short` 和对应 diff 命令核对，覆盖已提交、已暂存、未暂存和未跟踪的模块文件；文档中的归并范围与原始文件清单一致。
- [x] `AI_CONTEXT_CHANGELOG.md`：如果用户确认过关键方案，已经完整记录每个主要选项的做法、影响、适用条件和风险，以及 AI 的建议和用户最终选择；没有用“选择 A/B”代替决策上下文。
- [x] `AI_CONTEXT.md`：只同步影响续接的当前事实，不复制完整历史；当前模块、默认配置、最新基线和活跃边界均准确。
- [x] `AI_CONTEXT.md` 已完整审查全文，而非只检查本次新增或修改的区域。
- [x] `AI_CONTEXT.md` 中已删除或改写被新结论替代、已经完成、已经解决、重复或只具有历史价值的内容。
- [x] `AI_CONTEXT.md` 的当前状态、默认值、验证事实、路线判断和活跃坑之间不存在互相冲突的结论。
- [x] 从 `AI_CONTEXT.md` 删除的有价值历史信息，仍可在 changelog、eval-baselines 或对应专项 state 文档中追溯。
- [x] 涉及评测口径、文档入口、归档迁移、默认行为、安全边界或长期兼容边界时，已在 changelog 或当前事实摘要中留下可追溯记录。
- [x] 已检查本模块的新结论是否推翻或修正旧结论；`AI_CONTEXT_CHANGELOG.md` 中被修正的历史结论已在原位添加 `⚠️ 注`，`AI_CONTEXT.md` 中的过时当前结论已执行替换、退役或删除。
- [x] 三份文档刚写入的章节均已按照「阶段 5：收尾确认」完整回读，确认无截断、乱码、标题层级错误、事实夸大或未经 notes 支持的结论。

### finish-docs 完成记录（2026-08-16）

- 已更新 `docs/state/AI_CONTEXT.md` 的当前模块、M34 最新事实、路线判断和活跃风险；旧的 M33 当前状态已改写，历史原因保留在 changelog。
- 已在 `docs/state/AI_CONTEXT_CHANGELOG.md` 顶部新增 M34 完整条目，覆盖范围、用户决策、验证快照、参考资料和后续边界。
- 已在 `docs/dev-log.md` 追加 M34 面向学习/面试的完整章节，包含大白话、调用链、取舍、追问和真实验证命令。
- 已完整回读三份文档新增/修改章节；`git diff --check` 仅有既有 LF/CRLF 提示，无 whitespace error。
- dev-log 交付门与三文档交付门均逐项核对通过；未执行新的 pytest、Eval 或 provider 请求。

## finish-docs 二次执行清单（dev-log 重写）

### dev-log 交付门（必须执行）

- [x] 有“简述”和“先用大白话讲”
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] 每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、为何不选更宽松方案（如适用）、真实验证证据、尚未证明的边界。
- [x] 本模块首次出现的术语保留英文或代码名，并紧跟一句普通语言解释。

- [x] “新概念”解释至少一个本模块新术语
- [x] “代码阅读路线”是按调用顺序的编号列表，不止说明“看什么”，还需要说明“为什么/解决了什么”
- [x] 有“设计要点”
- [x] “面试怎么讲”有一段可直接复述的模块叙述，说明目标、方案、验证和边界。
- [x] 至少有 1 个 `[基础追问]` 和 1 个 `[工程/深挖追问]`；架构、评测、安全等复杂模块优先增加 `[压力追问]`。
- [x] 追问基于真实实现与证据，覆盖设计取舍、失败场景或后续边界。
- [x] 不写纯定义、送分、显而易见、凑数的低价值问题。
- [x] “验证与下一步”只引用 notes.md 中真实验证快照
- [x] 有可复制命令和本地启动体验/无独立入口说明
- [x] 未把确定性测试写成真实 LLM 能力结论
- [x] 模块记录的各个小节都要用 `**...**` 加粗标出“服务于扫读抓重点”的关键词或关键短句。

### 三文档交付门（必须执行）

- [x] `AI_CONTEXT_CHANGELOG.md`：本次完整模块有新的 `###` 条目，包含改动范围、关键记录、参考资料、验证快照、遗留/后续。
- [x] `AI_CONTEXT_CHANGELOG.md`：改动范围已经通过 `git status --short` 和对应 diff 命令核对，覆盖已提交、已暂存、未暂存和未跟踪的模块文件；文档中的归并范围与原始文件清单一致。
- [x] `AI_CONTEXT_CHANGELOG.md`：如果用户确认过关键方案，已经完整记录每个主要选项的做法、影响、适用条件和风险，以及 AI 的建议和用户最终选择；没有用“选择 A/B”代替决策上下文。
- [x] `AI_CONTEXT.md`：只同步影响续接的当前事实，不复制完整历史；当前模块、默认配置、最新基线和活跃边界均准确。
- [x] `AI_CONTEXT.md` 已完整审查全文，而非只检查本次新增或修改的区域。
- [x] `AI_CONTEXT.md` 中已删除或改写被新结论替代、已经完成、已经解决、重复或只具有历史价值的内容。
- [x] `AI_CONTEXT.md` 的当前状态、默认值、验证事实、路线判断和活跃坑之间不存在互相冲突的结论。
- [x] 从 `AI_CONTEXT.md` 删除的有价值历史信息，仍可在 changelog、eval-baselines 或对应专项 state 文档中追溯。
- [x] 涉及评测口径、文档入口、归档迁移、默认行为、安全边界或长期兼容边界时，已在 changelog 或当前事实摘要中留下可追溯记录。
- [x] 已检查本模块的新结论是否推翻或修正旧结论；`AI_CONTEXT_CHANGELOG.md` 中被修正的历史结论已在原位添加 `⚠️ 注`，`AI_CONTEXT.md` 中的过时当前结论已执行替换、退役或删除。
- [x] 三份文档刚写入的章节均已按照「阶段 5：收尾确认」完整回读，确认无截断、乱码、标题层级错误、事实夸大或未经 notes 支持的结论。

### finish-docs 二次完成记录（2026-08-16）

- **二次补齐次数：1 次**。原因是用户删除了首次生成的 M34 dev-log 章节并要求由更高能力模型重新写作；本轮从 notes 单一事实源完整重建，不复用被删正文。
- 新章节完整覆盖数据身份、解析切分、external profile、lexical/semantic 对照、方案 B support 合同、180 题 Answer Eval、成本、失败结构、代码阅读路线和面试追问。
- 交付检查中发现并修正两处状态文档旧表述：退役“仅在 22 条短知识验证”的活跃坑；澄清取消 800-token 上限后确实完成一次已确认的 180 题 full Eval，但无自动 retry 或收工阶段追加重跑。
- dev-log 交付门 `15/15`、三文档交付门 `11/11`，共 `26/26` 逐项通过；三份相关区域已按顺序完整回读。
- `git diff --check` 通过；只有工作树既有 LF→CRLF warning，无 whitespace error。本轮未运行 pytest、Eval、数据库、API 或真实 provider。

### RAG 专项状态补齐（2026-08-16）

- 用户复核指出 `docs/state/rag-current-state.md` 是否需要随 M34 更新；审查确认该文件仍写着“尚未接入/尚未建立索引/M34 收工后补全”，会违反 `AI_CONTEXT.md` 的 RAG 必读事实源约定。
- 已将其完整更新为 M34 最终当前状态：业务 22 条与 external benchmark 双基线、完整 identities、parser/unit/profile/pointer、lexical/semantic 对照、Answer Eval、方案 B、成本、失败结构、WixQA 排除与活跃风险。
- 同步在 `AI_CONTEXT_CHANGELOG.md` 的 M34 条目记录此次专项事实源补齐；`AI_CONTEXT.md` 已有对应当前摘要，无需重复扩写。
- 本次只读取已有 artifact/notes 并更新文档；未运行 pytest、构建、检索、Answer Eval 或真实 provider。

## 开工快照

- 日期：2026-08-15（Asia/Shanghai）
- Git HEAD：`d94a2d563a2af76c21a943aa386ff05495687ba0`
- 开工前工作区已有改动：`CLAUDE.md`、`docs/state/AI_CONTEXT.md`；已有未跟踪文件：`docs/notes/m34-plan.md`、`docs/state/rag-current-state.md`。这些均视为用户/前序工作，实施时不覆盖或回滚。
- 当前业务 Knowledge 基线：22 条（10 个 Markdown 文档条目 + 12 个指标投影）；默认 lexical adapter 和 deterministic extractive composer 保持不变。
- 当前外部数据根：`D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0`，包含 `raw/`、`extracted/`、`derived/`。
- 本轮在决策门前禁止：修改业务 active pointer/默认 Knowledge profile、把 raw/extracted 写进仓库、任何真实 provider 出站、把 Schema collection 当 Knowledge collection、把 gold 文档直接注入运行链。

## 过程记录

### 2026-08-15：开工必读与边界复核

- 已完整阅读 `AGENTS.md`、`docs/notes/m34-plan.md`、`docs/state/AI_CONTEXT.md`。
- 按 AI_CONTEXT 必读规则，已完整阅读 `docs/state/runbook.md`、`docs/state/eval-baselines.md`、`docs/state/rag-current-state.md`、`docs/state/schema-retrieval-milvus-embedding.md`。
- 已完整阅读用户点名的 `finish-module` skill；收工时必须执行四遍注释审计、实际验证、notes 固化和 handoff。
- 当前只获准按已确认 plan 推进；plan 内三道显式决策门仍生效，不能自动视为用户已经选择推荐方案。

### 2026-08-15：M34-A closed-world scanner

- 项目内新增轻量 recipe `eval/cases/enterprise-rag-bench-v1.0.0-dataset.json`：冻结 release tag、三来源、严格题集筛选、11 个必需官方资产的 size/SHA-256、预期分母和官方仓库/许可证链接。
- `engine/rag/enterprise_dataset.py` 建立三层身份：logical benchmark document ID、不可覆盖的 physical source instance identity、由完整 source-instance 清单计算的 corpus identity；question set 与 dataset 另有独立 identity。
- `scripts/inspect_m34_enterprise_dataset.py` 是只读 inspect 入口；外部路径通过 `--dataset-root` 或 `ENTERPRISE_RAG_BENCH_ROOT` 显式提供，不把本机绝对路径写成长期默认。
- 官方 release 包内没有 README/LICENSE，`release-api.json` 的 body 只有 `Initial dataset release`。2026-08-15 只读核对官方 GitHub 仓库：仓库标记 MIT，并说明数据是模拟 Redwood Inference 的合成企业数据；recipe 保存官方 repository/license URL，但明确这是 repository-level metadata，不声称 release 压缩包内带有独立数据许可证文件。
- 新发现：`qst_0413`（`conflicting_info`）把 `dsid_6df52...` 列了两次，而该 logical ID 恰好对应两份内容不同的 Jira source instances。这不是可以静默去重的普通重复；scanner 保留 gold multiset，并验证每个重复次数都有足够物理实例支持。后续 retrieval set coverage 必须显式处理该题，不能用 `set(expected_doc_ids)` 降格。
- 全量只读扫描结果：Confluence 5,189、Google Drive 25,108、Jira 6,120，总计 36,417；严格筛选 180 题；274 unique gold；0 missing；3 conflict logical IDs。
- 稳定身份：corpus `380d0511e737a774cc3c476dcfec2e85ec52003e21270bd869d012dcdc8ec29f`；question set `9a21ca95995c9d2c9e962351e9e7485630233a89c280a5c928b6bc40b9cd271c`；dataset `70c572328a90ec5dc380c086181af4d3706264f5aefd71c2856329f996d93cf7`。
- 轻量审计输出保存在 `.agent_work/temp/m34-dataset-audit.json`，不提交 36,417 条 source 清单或原始文件。

### 2026-08-15：M34-B parser 与结构 profile

- 官方 `export_data.py :: convert_to_text` 定点复核：标题和 content fields 通过真实换行拼接，但每个字段只做 `str(content)`；因此语料中的字面量换行来自上游字段本身，不是解压或 DataPilot 读取造成。
- 全量预扫描纠正了“只有 Google Drive 有字面量 `\\n`”的早期样本印象：Confluence、Drive、Jira 都存在。parser 为三来源保存显式 policy，当前均只在正文恢复 `\\r\\n` / `\\n` / `\\r`；不使用通用 `unicode_escape`，所以 `\\"`、Windows path 和其他代码反斜杠保持原样。
- parser candidate identity：`5af364e197a26eaf6f7afc764a777454a0ea839e7dfb905844ce304a5b7f9c84`。全文解析 36,417 篇无空标题/空正文/identity 漂移错误。
- 结构统计：Confluence 长度 p50/p95/max = 9,615/14,331/24,881；Drive = 7,026/9,898/22,706；Jira = 5,564/7,211/10,433。gold source instances = 688/5,768/13,088(p95)/21,745(max)。
- 换行修复：共恢复 literal LF 849,117、literal CRLF 63、literal CR 64；涉及 Confluence 1,118、Drive 7,907、Jira 396 篇。原件 hash 不变，normalized revision 把 physical identity + parser identity + normalized content hash 绑定。
- 输出 `.agent_work/temp/m34-parser-profile.json`；未生成或提交 normalized 全量副本。

### 2026-08-15：M34-B unit 候选结构对照

- 实现 whole-document 与 paragraph-pack 参数化 builder。unit anchor 是 `normalized-char:<start>-<end>`，identity 绑定 document revision、recipe、offset 和 unit content hash；测试逐 unit 回切 normalized content。
- 候选初次 full-corpus profile：whole-doc 36,417 units，长度 p50/p95/max = 6,975/10,803/24,881；paragraph-1200 为 284,867 units，文档 unit 数 p50/p95/max = 8/12/26；paragraph-2400 为 139,214 units，文档 unit 数 4/6/12；paragraph-2400 + overlap1 为 160,515 units，文档 unit 数 4/7/15。
- overlap1 相比无 overlap 的 2400 候选多 21,301 units；初次报告的 ratio 分母误用了 UTF-8 raw bytes，已改用 normalized characters 并完成重跑：whole-doc = 1.0、1200 no-overlap = 0.998119、2400 no-overlap = 0.999168、2400 overlap1 = 1.189566。no-overlap 少掉的约 0.1%–0.2% 只是段间空白；overlap1 实际增加约 19.0% 索引字符。
- 这些数字只证明索引规模/上下文局部性的工程差异，不证明召回收益；任何 candidate 都尚未成为 final build recipe。

### 2026-08-15：方案 A case split 冻结

- 用户确认 60 diagnostic/dev + 120 held-out。实现 `enterprise-rag-case-split-v1`：按 `question_type × source signature × single/multi-document` 分组，使用最大余数法分配 60 个 dev 名额，组内由 `question_set_identity + question_id` 的 SHA-256 稳定排序。
- split identity：`f8164d3f57fe4c262f3a8f7ecd293196748d2abcbd4f387f3fbb8f50208138dd`。dev：60（semantic 18、multi 12）；held-out：120（semantic 34、multi 26）。
- 两个 `google_drive+jira` case 分属两个仅 1 题的 composite strata，均按确定性最大余数结果进入 held-out。没有为追求表面均匀手工换题，避免未来出现主观重抽样。
- 项目内 `eval/cases/enterprise-rag-bench-v1.0.0-split.json` 与 `.agent_work/temp/m34-case-split.json` 完整 JSON 相等；60/120 唯一、互斥、并集精确等于 180。

### 2026-08-15：full-corpus local lexical dev 对照

- 固定变量：dataset/question/split/parser 相同；不按官方 `source_types` 过滤，不向 runtime 提供 gold；每个 candidate 对完整 corpus 建独立 SQLite FTS5 `unicode61 + OR + bm25` 索引，60 道 dev 题各执行一次查询，先取 200 units，再按 physical source identity 去重为最多 50 documents。
- comparison artifact：`.agent_work/temp/m34-lexical-dev-comparison.json`，状态 `completed`，identity `96639e47a96211b1286d5897c4fdce594d55622b75bb25bc5807c83db295a87d`，约 6.1 MB；四个临时索引都位于 `.agent_work/temp/m34-lexical-indexes-20260815-01/`。
- whole-doc：36,417 units / 115.2 MB / build 19.20s；overall coverage@20 0.724306、all-gold@20 0.683333、MRR 0.634033、query p50/p95 331/520 ms；semantic coverage@20 0.388889。
- paragraph-1200：284,867 units / 203.0 MB / build 34.15s；overall coverage@20 0.793056、all-gold@20 0.75、MRR 0.612591、p50/p95 865/1,212 ms；semantic 0.444444。
- paragraph-2400：139,214 units / 157.4 MB / build 28.28s；overall coverage@20 0.810417、all-gold@20 0.766667、MRR 0.646950、p50/p95 537/814 ms；semantic 0.555556；multi coverage@20 0.885417。
- paragraph-2400-overlap1：160,515 units / 185.2 MB / build 29.64s；overall coverage@20 0.793750、all-gold@20 0.75、MRR 0.642915、p50/p95 638/944 ms；semantic 0.5。
- paired @20：2400 相对 whole-doc 为 7 improved / 53 equal / 0 worse（semantic 3/15/0，multi 4/8/0）；相对 1200 为 4/53/3，mean coverage delta +0.017361，semantic +0.111111；相对 overlap1 为 1/59/0。说明 2400 的优势不是单纯总体均值，且 overlap 没有给当前 dev 带来净收益。
- 当前建议：冻结 `enterprise-unit-paragraph-2400-v1`，不启用 overlap。它在 lexical dev 上兼顾最佳 overall/semantic@20、最佳 MRR 与中等 index/query 成本；但必须先由用户确认，held-out 仍未打开。

### 2026-08-15：M34-C immutable external profile candidate

- 现状调查结论：旧 `ReleaseBundle` 内嵌全文且 AnswerFlow 假设一个 `(document_key, revision)` 对应单 anchor；把 139,214 units 强塞进去会制造约 262M 字符 JSON/内存放大和 citation anchor 冲突。因此新增独立 external profile lifecycle，而不是改写业务 release 或伪造大量旧 bundle entries。
- `engine/rag/enterprise_profile.py` 在项目外 immutable SQLite 同时保存 36,417 条 document catalog、139,214 条 unit metadata/context 和 contentless FTS5 index；profile meta 绑定 dataset/corpus/question/parser/unit/index/ACL/outbound identities。
- 构建纪律：先写 `.building-<identity>-<uuid>`，关闭数据库后计算 size/SHA-256，写 manifest，执行 SQLite integrity/meta/count/FTS count/hash 全校验，最后同目录原子 rename 为 profile identity。已有同 identity 时只 verify/reuse，不追加写入。
- benchmark active pointer 独立为 `enterprise-knowledge-active-pointer-v1`，支持 previous identity；单测证明 corrupt candidate 不能替换已有 active。业务 `domain_pack/kb_releases` 和其 pointer 不在模块路径范围内。
- 真实 candidate 路径：项目外 `v1.0.0/derived/enterprise_profiles/e8783fe0...75fa2/`；profile identity `e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2`；manifest identity `546b0aeec8264c0e9d55e3093ce5a72577a2a63a594544f82cae5ad4cfb48eaf`。
- 真实 build：36,417 documents / 139,214 units / 662,818,816 bytes / 33.475832s；database SHA-256 `5b88e88abaaa6ee570f10a9dc9eb57b0b4b83b28d7e62d7569c5653d728141d3`。
- 构建完成后 state 为 `active=false` / `profile_count=1`；这是刻意保持 candidate，尚未把 local lexical 设为最终 external adapter。随后通过独立新进程 `--verify-profile` reload，identity/count/hash 全部一致。
- build 摘要：`.agent_work/temp/m34-external-profile-build.json`；独立 verify：`.agent_work/temp/m34-external-profile-verify.json`。原始/派生大文件均未进入 Git。

## 模块内容清单

- `eval/cases/enterprise-rag-bench-v1.0.0-dataset.json`：v1.0.0 轻量 dataset recipe 与 hard expectations。
- `engine/rag/enterprise_dataset.py`：release/asset/source/question closed-world scanner、身份模型和摘要投影。
- `scripts/inspect_m34_enterprise_dataset.py`：显式外部 root 的只读 inspect CLI。
- `tests/test_m34_enterprise_dataset.py`：稳定重建、logical/physical 冲突、空来源排除和负向漂移测试。
- `engine/rag/enterprise_parser.py`：三来源 parser policy、显式 normalization events、normalized revision 与 full-corpus profiling。
- `engine/rag/enterprise_units.py`：参数化 whole/paragraph unit builder、stable offset anchor 与候选结构对照。
- `scripts/profile_m34_enterprise_corpus.py`：完整 corpus parser/结构 profile CLI。
- `scripts/profile_m34_unit_candidates.py`：同 parser/corpus 的 unit 候选规模对照 CLI。
- `tests/test_m34_enterprise_parser.py`、`tests/test_m34_enterprise_units.py`：三来源转义修复、原件漂移、recipe identity、offset 往返和超长段边界。
- `engine/rag/enterprise_cases.py`：用户确认的 60/120 确定性分层与 closed-world validator。
- `engine/rag/enterprise_lexical_experiment.py`：experiment-only SQLite FTS5 build/search 和 dev retrieval evidence；尚不是 Knowledge Tool adapter。
- `eval/cases/enterprise-rag-bench-v1.0.0-split.json`：冻结的 180 题 ID split manifest。
- `scripts/build_m34_case_split.py`、`scripts/run_m34_lexical_dev_experiment.py`：split 重建和 full-corpus local lexical dev 对照入口。
- `tests/test_m34_enterprise_case_split.py`、`tests/test_m34_enterprise_lexical_experiment.py`：split tamper、FTS unit search、physical dedup 和 anchor 测试。
- `engine/rag/enterprise_profile.py`：项目外 immutable profile build/verify/activate/load/inspect 与 benchmark 专属 pointer。
- `scripts/build_m34_external_profile.py`：candidate build、只读 verify/inspect 和显式 activate CLI；默认不切 pointer。
- `tests/test_m34_enterprise_profile.py`：安全复用、完整 reload、previous pointer 与 corrupt candidate 不切换测试。
- `engine/rag/enterprise_runtime.py`：独立 profile 的 metadata-only bundle、SQLite FTS adapter、命中后正文 loader，以及复用现有 Knowledge Tool / AnswerFlow 的 factory。
- `engine/rag/knowledge_tool.py`、`engine/rag/evidence.py`、`engine/rag/answer_flow.py`：新增可注入 context loader、document/unit/offset 坐标和通用 bundle view；默认业务 release 行为保持不变。
- `tests/test_m34_enterprise_runtime.py`：candidate 真实取证、未验证 caller 失败关闭、Evidence 坐标和 validated citation 闭环。
- `engine/rag/enterprise_retrieval_eval.py`、`scripts/run_m34_retrieval_eval.py`：一题一次真实 Tool 的专用 retrieval artifact、multiset scorer、分组摘要与 closed-world validator。
- `scripts/smoke_m34_external_runtime.py`：只允许冻结 dev IDs 的真实 AnswerFlow smoke；gold 只在运行返回后评分。

## 决策与取舍

### 待确认：180 题的 diagnostic/dev 与 held-out decision split

- 依据：M34 plan C6 明确最终 split 数量要在看见真实分布后冻结；用户要求影响长期 Eval 口径的选择必须先确认。当前 180 题中 semantic 52、multi-document 38，来源/题型组合不均，不能直接按 question ID 前 N 条切。
- 方案 A（建议）：60 diagnostic/dev + 120 held-out decision，按 `question_type × source signature × single/multi-document` 做确定性分层，question-set identity 作为稳定 seed；required contract/security 继续使用独立本地 fixtures，不占 180 题。
- 方案 B：45 diagnostic/dev + 135 held-out decision，同样分层。held-out 更大，但 dev 约只有 13 道 semantic、10 道 multi-document，chunk/top-k 失败簇更容易受个别题影响。
- 方案 C：不分集，180 题同时调参与裁决。实现最省事，但会把调参反馈泄露进最终选择，不能支持“held-out 证明提升”，不建议。
- 影响：确认后会提交轻量 question-ID split manifest 和 hash；只在 dev 比较 parser/unit/local lexical，held-out 在候选冻结后才打开。任何 remote run 仍由 G-M34-3 单独授权。
- 风险：分层维度过细会产生大量单元素 strata；实现会采用稳定的全局配额 + 分层优先分配，并在 manifest 中校验 60/120、全 180 唯一闭合与关键分组计数。
- 用户选择：2026-08-15 确认方案 A。后续按 60/120 冻结，不因检索分数重新抽样。

### Gold 重复项语义

- 依据：`qst_0413` 两次声明同一个 expected logical ID；语料中该 ID 有两份内容不同的 Jira 物理文件。
- 选项：A. 直接去重成 logical set；B. 保留官方列表的 multiset，并以 physical source-instance cardinality 校验。
- 做法/建议：采用 B。A 会把真实 conflicting/multi-document 题静默降格，且与 3 个冲突 ID 的身份合同矛盾。
- 影响：后续 retrieval artifact 同时记录 physical identity 与 logical ID；集合评分需支持 multiplicity 或为该题给出专门、可审计的映射规则。
- 风险：官方只有重复 logical ID，无法仅凭 ID 指定两份物理文件的先后；因此不能制造伪精确 path gold，只能验证检索结果覆盖同 ID 的两个不同 physical instances。
- 用户选择：属于已确认 C1/C6 身份不变量下暴露出的数据事实，当前只落实“不覆盖、不静默去重”；最终 scorer 细节在 M34-E 前再次复核。

### 字面量换行 normalization

- 依据：官方 exporter 对字段只做 `str()`；三来源共至少 849,244 个 literal newline tokens。完全不修复会让标题/段落结构和检索上下文失真。
- 选项：A. 不修复；B. 只修复结构性 newline tokens；C. 对全文做通用 escape decode。
- 做法/建议：parser candidate 采用 B。C 会改变 JSON/代码/path 的其他转义，风险过高；A 会保留已证实的上游结构编码。
- 影响：parser identity 随 policy 变化；所有修复计数进入 profile。raw bytes/source identity 始终不改。
- 风险：极少数正文可能真的想表达字面量 `\\n`；当前官方 exporter 没有 field boundary metadata 可精确区分。后续 dev 失败样本若证明误修复，再以新 parser recipe 比较，不能静默改 v1。
- 用户选择：当前只作为 M34-B candidate 实现，最终 build recipe 尚待检索证据确认。

### 待确认：final unit recipe

- 依据：同一 full corpus / parser / 60 dev / lexical protocol 的 structural + retrieval paired 证据见上。
- 方案 A（建议）：paragraph-2400，无 overlap。139,214 units；当前 dev overall/semantic/MRR 最佳，paired 相对 whole-doc 无退步题。
- 方案 B：paragraph-1200，无 overlap。长文局部性更细，但 units/索引/延迟明显更高，MRR 更低，@20 也未胜过 2400。
- 方案 C：whole-document。工程最轻、查询最快，但长上下文和 semantic/multi coverage 明显落后，不能满足 M34 的长文目标。
- 方案 D：paragraph-2400 + overlap1。增加约 19% 字符和 21,301 units，当前 paired 对照没有稳定收益，不建议。
- 影响：确认后 recipe identity 将进入 M34-C build/index/profile；修改参数必须产生新 identity 和新可比实验，不能原地改 v1。
- 用户选择：2026-08-15 确认方案 A，`paragraph-2400`、无 overlap。

### 待确认：G-M34-1 external profile 共存方式

- 方案 A（计划与当前证据均推荐）：独立 benchmark profile，复用 Knowledge Tool / AnswerFlow interface，但 release/index pointer、corpus identity 与 22 条业务 active release 分离。
- 方案 B：合并进 22 条业务 active release。会耦合 authority、ACL、回滚与默认检索，不符合当前 benchmark 定位。
- 用户选择：2026-08-15 确认方案 A，独立 benchmark profile；禁止修改业务 active release。

## 验证快照

### M34-A 聚焦测试

- 首次命令：项目 Python + `pytest tests/test_m34_enterprise_dataset.py -q`。
- 结果：6 个 case 均在 pytest fixture setup 前因共享 `.agent_work/temp/pytest-tmp` 删除权限 `WinError 5` 报错；没有执行 M34 业务代码。未删除该目录，改用新的唯一 basetemp。
- 修正后命令：`python -m pytest tests/test_m34_enterprise_dataset.py -q --basetemp=.agent_work/temp/pytest-m34-a-20260815-03`。
- 结果：`6 passed in 0.60s`。

### M34-A 真实全量扫描

- 命令：项目 Python 执行 `scripts/inspect_m34_enterprise_dataset.py`，显式传入项目外 v1.0.0 root，输出到 `.agent_work/temp/m34-dataset-audit.json`。
- 结果：36,417 / 180 / 274 / 0 missing / 3 conflicts 全部闭合；输出三层 identity，未联网、未写项目外数据。

### M34-B parser / unit 聚焦测试

- 命令：项目 Python + `pytest` 运行三个 M34 test 文件，使用 fresh basetemp `.agent_work/temp/pytest-m34-b-units-20260815-01`。
- 结果：`14 passed in 0.60s`。
- parser profile：项目 Python 执行 `scripts/profile_m34_enterprise_corpus.py`，输出 `.agent_work/temp/m34-parser-profile.json`；36,417 篇全部完成。
- unit profile：项目 Python 执行 `scripts/profile_m34_unit_candidates.py`，输出 `.agent_work/temp/m34-unit-candidates.json`；首次投影发现 ratio 分母概念错误，改为 normalized character denominator 后以同一命令重跑完成。

### 决策门前干净验证

- 命令：项目 Python + 三个 M34 test 文件，fresh basetemp `.agent_work/temp/pytest-m34-decision-gate-20260815-01`；随后 `compileall` 新增模块/脚本和 `git diff --check`。
- 结果：`14 passed in 0.61s`；compileall 通过；diff check 无 M34 空白错误。仅显示开工前已有 `CLAUDE.md`、`AI_CONTEXT.md` 的 LF→CRLF 工作区提示，未修改或格式化这两个文件。

### 方案 A split / lexical candidate 验证

- split + scanner/parser/unit/FTS 聚焦测试：fresh basetemp 下 `20 passed in 0.74s`；修复 direct-script namespace seam 后 split+FTS 复跑 `6 passed in 0.49s`。
- 第一次启动 lexical CLI 在 import 阶段因 `eval` namespace 对直接脚本不可见而失败，尚未创建索引；将 case/lexical candidate 模块移到明确的 `engine.rag` package seam 后，沿用首次空 work-dir 只执行一次真实构建。
- full-corpus dev comparison 完成；四个索引合计约 660.8 MB，artifact 为 completed。未读取 held-out query、未联网、未修改项目外数据或业务 active pointer。

### M34-C profile 验证

- 聚焦测试：六个 M34 test 文件，fresh basetemp `.agent_work/temp/pytest-m34-profile-20260815-02`，`22 passed in 0.77s`；CLI help 正常。
- 真实 candidate build 经 sandbox approval 仅写明确的项目外 `derived/enterprise_profiles`；未带 `--activate`。构建内校验通过后，另一个只读进程以 profile identity 再次 verify，36,417/139,214/database SHA 完全一致。

### M34-D runtime 接线进行中

- 取舍：不把 139,214 段正文强塞进为 22 条短知识设计的 `ReleaseBundle`。external bundle 只常驻 metadata；Knowledge Tool 完成 pre-selection ACL 和 adapter match 后才加载命中 unit 正文，再执行 pre-generation ACL、Gate 与 citation validator。
- 身份：每个 unit 使用独立 `enterprise-unit:<unit_identity>` document key，避免同一长文多个切片在现有 `(document_key, revision)` citation map 中互相覆盖；Evidence 另携带 source type、logical/physical document、unit 与 normalized offsets。
- 安全：公开 benchmark 条目仍要求 caller 来自可信 adapter；请求体自报 admin 的 unverified caller 得到空授权集合，adapter 固定调用一次但不读取正文。
- 首轮回归：M32/M33 的 23 个无 `tmp_path` 测试已通过；5 个依赖 `tmp_path` 的 profile/runtime 测试在 fixture setup 前被共享 `.agent_work/temp/pytest-tmp` 的历史 Windows 权限锁阻断，尚未执行断言。按 M34-A 已知处理方式改用 fresh basetemp 复跑，不删除受锁目录。
- fresh basetemp 复跑：首次只有新增测试把 claim ref 错当 Evidence ref 的断言错误；修正测试后 profile/runtime + M32/M33 合计 `28 passed in 0.78s`。这是测试表达错误，运行链实际已完成到 cited ledger。
- 真实 candidate smoke：profile `e8783fe...fa2`，3 道固定 dev（semantic / multi / basic）均 `answer_status=complete`、`safety=passed`、有 validated citation；单题约 1.97–1.99s。运行后 gold 对账分别为 1.0、0.5、0.0，证明链路已接通，但也明确显示 lexical 漏召回时 extractive Composer 会给出“有引用但答非所问”的完整状态；不能把 smoke complete 当答案正确。
- smoke artifact：`.agent_work/temp/m34-external-runtime-smoke.json`；candidate 未 activate、未打开 held-out、未联网。

### M34-E lexical Tool dev artifact

- 专用 runner 固定 `max_candidates=max_selected=20`，每题恰好一次 Knowledge Tool / adapter 调用；gold IDs 和 answer facts 不进入 runtime，只有 Tool 返回后才用 Evidence 的 logical/physical/unit 坐标评分。
- 首次长任务因桌面终端 session 交接消失，未生成 artifact、无残留进程；同命令在受控轮询会话重跑并取得明确 exit 0。不能把首次消失记成失败 case 或 completed run。
- completed dev artifact：`.agent_work/temp/m34-lexical-tool-dev-retrieval.json`，60/60 closed-world，identity `7b444240067f990dc1bc11d45b5010e0e8306a5100f29cd9d6d3a4da6188d182`。
- overall @20 coverage 0.810417、all-gold 0.766667、MRR 0.645303、no-result 0；semantic 18 题 coverage/all-gold 0.555556、MRR 0.259259；multi 12 题 coverage 0.885417、all-gold 0.666667；long raw-byte 7 题 @20 coverage/all-gold 1.0。
- Tool runtime p50/p95 = 1832/2150ms，明显高于 experiment-only FTS 的 537/814ms；代价来自每题 139,214 metadata ACL 扫描、授权集合校验、20 个正文加载与二次授权。它证明真实链路规模可用，但也形成后续性能边界，不能用离线 index latency 代替生产 Tool latency。
- semantic 仍是最大失败簇：14 道 @20 非 all-gold 中 semantic 8、completeness 3、basic 2、constrained 1。按 G-M34-2 已满足“比较 semantic candidate”的触发证据；held-out 仍未打开。

### 2026-08-15：G-M34-3 远程用途确认

- 用户确认按建议执行，并说明 Docker/Milvus 已启动。
- 精确授权范围：DashScope `qwen3.7-text-embedding` / 1024 维用于完整 139,214 个公开合成 benchmark units 的 Knowledge embedding 与查询 embedding；独立 Knowledge Milvus collection，不复用 Schema collection、不修改 `.env` 默认。
- generation 只先批准小规模 Qwen smoke：字段限 question、经现有 ACL/Gate 选择的 context 与模型/受控 prompt；全量 180 题 generation 仍需在 smoke/成本证据后按计划推进。Judge 未授权、LangFuse Cloud 保持关闭。
- 规模预估：unit 正文共 262,130,017 characters；现有 DashScope provider batch 上限 20，理论约 6,961 个 document embedding batches，属于长运行，必须流式写入、可恢复且不能把全部 Python vectors 常驻内存。
- 环境核对：`milvus-standalone`、`milvus-minio`、`milvus-etcd` 均 healthy；standalone 暴露 19530。首次 sandbox 内 Docker 查询因用户级 Docker config/pipe 权限失败，按工具规则只读提权后确认健康。
- 20-unit 真实 provider smoke 成功：semantic identity `9aec12c8...e20`，独立 collection 行数 20/20，状态只为 `building`，没有伪造 candidate manifest。
- 首次全量续跑到 checkpoint 1,080 后遇到 `SSL: UNEXPECTED_EOF_WHILE_READING`；未完成 batch 没有写入，candidate manifest 不存在。原实现没有长运行 transport retry，现补充只针对 URL/timeout/connection 和 408/429/5xx 的最多 6 次指数退避；401/403、治理 deny、响应合同和向量错误不重试。
- 为缩短预计 5–6 小时的单路构建，增加最多 4 路、每路仍为 20 条的有界并发；80-unit smoke 的 embedding/upsert 完成，但暴露 Milvus `upsert` 后 `get_collection_stats().row_count` 会包含旧版本/tombstone：checkpoint 4,120 时物理 row count 6,520。此前把 row count 当恢复游标/最终唯一数是错误的。
- 修正：恢复位置只信任同 identity 原子 checkpoint；非空 collection 丢 checkpoint 时失败关闭，不能从物理行数猜进度。物理 row count 只做 telemetry；最终 candidate 还必须增加 unit 主键集合闭合校验后才允许生成 manifest。当前 collection 仍是 building，无 candidate。
- 4 路恢复后推进到 checkpoint `76,680 / 139,214`，随后 DashScope 返回 HTTP 400。用户确认根因是账户欠费，不是语料、向量维度、Milvus 或并发合同错误；因此不继续发送请求、不把 provider 不可用记成 retrieval 业务失败。
- 充值后按 1,000 条校准和 5,000 条分段继续；`82,800`、`87,800`、`92,800`、`97,800`、`102,800` checkpoints 均成功，最近稳定段每 250 requests 约 2.4M tokens。用户要求不再逐段弹窗，沿用已批准范围执行。
- `102,800` 后一次响应体发生 `http.client.IncompleteRead`；此前 retry 只覆盖 URLError/timeout/connection，现补入 IncompleteRead，下一批从 checkpoint 重放。
- semantic candidate 最终完成：139,214/139,214 unique unit 主键集合闭合；manifest `22c57375...be97b`，unit set identity `17d5af0b...3905`，Milvus collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`，仍保持 candidate、不切默认。
- semantic diagnostic/dev artifact `.agent_work/temp/m34-semantic-tool-dev-retrieval.json`：60/60 completed，@20 coverage `0.737500`、all-gold `0.700000`、MRR `0.621421`；相对 lexical dev 6 better / 42 equal / 12 worse，平均 coverage delta `-0.072917`。semantic 子组 coverage `0.444444`，multi `0.770833`，long `0.928571`。
- semantic held-out artifact `.agent_work/temp/m34-semantic-tool-heldout-retrieval.json`：120/120 completed，@20 coverage `0.773958`、all-gold `0.741667`、MRR `0.630477`。
- lexical held-out 对照 `.agent_work/temp/m34-lexical-tool-heldout-retrieval.json`：@20 coverage `0.823125`、all-gold `0.775000`、MRR `0.723134`。因此 held-out 仍由 lexical 胜出；semantic candidate 不切 external 默认，也不宣称 semantic 提升。semantic query TLS EOF 已通过统一 retry 修复后完成。
- lexical external profile 已切换独立 benchmark pointer：active profile `e8783fe...fa2`，pointer `9908e59a...2446`；业务 22 条 active release/pointer 未改变。
- 3 题 Qwen remote AnswerFlow smoke 未形成 completed artifact：模型返回 paraphrase claim，M33 `_validate_claim_drafts` 的 extractive support contract 安全阻断（`composer_output_invalid`）。这是现有可信回答合同的真实边界，不放宽 validator、不把失败改记为 answer success；Judge 未调用。
- 用户确认采用方案 B：允许 Composer 输出自然语言 `text`，但每条 claim 必须同时返回逐字可回查的 `support_text`、`evidence_id` 和 `anchor`。代码只确定性证明 support 原文存在、Evidence/citation 身份合法和每条 claim 引用完整；不把“support 必然蕴含 paraphrase”伪装成可由字符串校验证明。M31–M33 的权限门、Evidence ledger、citation validator 与发布合同保持不变。
- 方案 B 的付费边界：先完成本地合同测试，再仅重跑 3 道 Qwen smoke；不自动启动 180 题 Answer Eval，不调用 Judge。
- 方案 B 本地合同验证：`tests/test_m33_answer_flow.py + tests/test_m34_enterprise_generation.py` 共 17 passed。自然语言 `text` + Evidence 内逐字 `support_text` 可通过完整 citation 链；伪造 support 在 citation validator 前 fail closed。
- 3 题 Qwen smoke v2：固定调用 3 次、Judge 关闭；artifact `.agent_work/temp/m34-remote-answer-smoke-v2.json`。1/3 completed（basic `qst_0016`，自然改写 + validated citation + cited ledger 全链成功）；2/3 在 Composer 阶段失败并安全投影为 `processing_not_available`（semantic `qst_0181` 约 47.1s、multi `qst_0341` 约 62.5s），未进入 validator、未公开 claim/citation。当前 transport/Composer 把 timeout、provider 错误和结构解析错误统一收敛，artifact 无法继续离线区分两次失败根因；不得把 1/3 smoke 宣称为 Answer Eval 完成，也不自动重跑付费调用。
- 针对上述可观测性缺口，已在 provider client 增加只含数字的 request/success/token telemetry，在 remote Composer 增加不含正文的 attempt status/error subtype/elapsed/usage delta；smoke 脚本升级为 v2 原子逐题 checkpoint，并支持显式 question allowlist 与 timeout。默认 LLM provider 行为、回答安全投影和业务 runtime 未切换。聚焦验证 35 passed。
- 用户确认只复测前述 2 道失败题，每题一次、无自动 retry、Judge 关闭。`qst_0181` provider 成功返回：4,028 tokens（prompt 1,793 / completion 2,235）、约 39.0s，但 Composer response contract 不合格而安全拒绝。执行 `qst_0341` 后进程在 AnswerFlow 严格 support 合同异常处退出，暴露 smoke checkpoint 只处理四轴 result、未处理 `AnswerFlowContractError` 的缺口；本次不重跑，第二题用量无法从退出后的进程内 telemetry 恢复，artifact 必须保持 `in_progress`，不能伪造 completed。脚本随后补为合同拒绝也逐题落盘，并细分不含正文的 response error subtype。
- 官方百炼文档复核：`qwen3.7-plus` 是默认开启思考的混合思考模型，直接 HTTP 请求可把 `enable_thinking=false` 放在 body 顶层；当前中国内地 0–256K 原价为输入 2 元/百万 token、输出 8 元/百万 token（活动价以控制台为准）。用户确认 M34 Composer 专用模式关闭思考并限制 `max_tokens=800`；通用 Qwen/Text2SQL client 缺省继续不发送这两个参数。Composer identity 升级为 `rag-qwen-evidence-support-nonthinking-800-v3`。
- 非思考 v3 固定 3 题 smoke 完成：3 requests，prompt/completion/total = 5,578/1,056/6,634 tokens；单题约 3.3–12.2s。`qst_0181` 与 `qst_0016` 完整通过 support/citation/ledger 合同，`qst_0341` provider 返回成功但 support 不是 Evidence 逐字子串，被 `composer_output_invalid` 拒绝。离线 gold 对账进一步证明“合同 complete ≠ 答案正确”：两道 completed 题引用的 logical docs 都不是 gold，回答也未覆盖 gold facts；multi 题 lexical top-3 只含 1/2 gold（另一 gold 在 top-20 第 11 位）。因此此 smoke 只证明真实回答链可运行，不能证明回答质量提升。
- 为减少 JSON 复制换行造成的假拒绝，Composer 只增加 whitespace-only canonicalization：标点/字母/数字必须完全相同，代码把仅空白不同的 support 还原成 Evidence 内真实连续切片，再交给 AnswerFlow 严格校验；不做 fuzzy 或语义近似匹配。
- M34 专用 180 题 Answer Eval runner 已准备：一题一次真实 AnswerFlow；gold answer/facts/docs 只在返回或合同拒绝后加入 scorer；逐题原子 checkpoint、合法前缀 resume、completed closed-world identity、provider usage/attempt、overall/type/source/cardinality 分组、cited-gold multiset coverage 与保守 exact-fact coverage。没有 Router/Hybrid/UI/通用平台，也没有 Judge。
- 按 v3 smoke 实测 3 题共 5,578 input + 1,056 output tokens，官方原价折算约 0.0196 元；线性期望 180 题约 1.18 元。考虑题目/上下文波动，并按每题最多 3,000 input + 已冻结 800 output 估算，provider 费用保守上界约 2.23 元（活动价/控制台结算可能不同）；预计串行耗时约 20–35 分钟。全量运行仍需单独确认，且结果很可能量化出“引用合同通过但 gold correctness 较低”，不能预设提升。
- 用户明确要求取消 Composer 应用层 800-token 上限并继续。已保持 `enable_thinking=false`，移除 `max_tokens` 请求字段；Qwen 服务端自身限制仍在。Composer identity 升级为 `rag-qwen-evidence-support-nonthinking-unbounded-v4`。费用不再有 800-token 人工上界，full Eval 以 provider usage telemetry 和逐题 checkpoint 为准。
- 180 题 full Answer Eval 已完成：artifact `.agent_work/temp/m34-answer-eval-full-v4.json`，identity `d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f`；180 次 AnswerFlow/180 次 provider request、无 retry，405,305 total tokens（342,656 input / 62,649 completion），179 次 provider response 成功、10 次 Composer unavailable（其中 1 次 network_error），24 次 Composer output contract rejected。146/180 `answer_status=complete`（81.11%），p50/p95/max flow latency = 8.428/13.823/16.931s。
- Full Eval 关键质量边界：gold document all-cited 80/180（44.44%），mean gold-document coverage 49.3981%；multi-document 38 题 all-gold 仅 2/38（5.2632%），mean coverage 28.7281%；semantic 52 题 all-gold 15/52（28.8462%），answer complete 71.1538%；exact-fact scorer 只有 1/180 全量命中（0.6944%），这是保守字符串检查下限，不是开放语义正确率。结果证明真实 build→retrieve→answer→cite→score 链成立，但不能宣称回答质量或 semantic/multi-document 提升；主要短板仍是 lexical top-k gold 漏召回和 Composer support 合同拒绝。
- 当前可恢复状态：semantic identity `9aec12c8...e20`，building collection 保留；没有 semantic candidate manifest、没有打开 held-out、没有运行 generation smoke。充值后可用同 identity/同命令从 checkpoint 重放；重放使用 PK upsert，最终仍须通过 139,214 个唯一 unit 主键集合 hash 闭合。

## 参考资料与借鉴边界

> M34-B 开始前按需补充 `docs/phase4-reference.md` 与定点源码复核结果。

## Handoff

### 已完成

- 已建立 implementation checklist 与开工边界。

### 关键改动

- 待补充。

### 验证结果

- 待补充。

### 遗留问题

- final unit recipe 与 G-M34-1 已确认；G-M34-2 的 semantic candidate / 最终 adapter 与 G-M34-3 出站仍在后续确认。

### 下一步

- 实现 M34-C 独立 external profile / local lexical lifecycle；不打开 held-out、不远程出站。
