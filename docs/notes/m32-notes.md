# M32 确定性知识取证与 Knowledge Tool 开发素材

> 本文是 M32 开发过程事实源。实现中的决策、踩坑、验证证据和收工交接随进度即时补充，不在收工时凭记忆重建。

## Implementation checklist

- [x] 固化开工 Git、active release、corpus、旧合同与测试基线
- [x] 冻结 Knowledge Tool request/outcome、reason registry、safe diagnostics 和 retrieval adapter 合同（C1/C2）
- [x] 实现本地 deterministic retrieval baseline：稳定规范化、匹配、排序、去重、预算与结构化失败（C2）
- [x] 实现 active load → pre-selection ACL → retrieval → candidate Evidence → selected → pre-generation recheck（C1/C3）
- [x] 证明未授权 entry 不进入 adapter，公开投影不泄露其存在性、标题、revision、identity、命中数或正文（C3）
- [x] 保持 Evidence ledger 最远到 selected，不生成答案、四轴状态、claim 或 citation（C1/C3）
- [x] 建立独立版本化 RAG retrieval contract family 与一次执行共享证据（C4）
- [x] 实现 completed artifact closed-world 校验、required Gate 与 retrieval-only advisory 视图（C4）
- [x] 覆盖授权命中、no candidate、ACL 非泄露、revision/release 异常、retriever unavailable、投毒文本与确定性 case
- [x] 运行 adapter → Tool/ACL/Evidence → retrieval Eval 聚焦测试
- [x] 运行 M31/P1、API/Text2SQL/Eval 受影响回归与全仓确定性测试
- [x] 运行 compileall、`git diff --check` 并确认未调用真实 provider/Milvus/LangFuse
- [x] 按 `finish-module` 完成四轮注释审查、验证和 Handoff 素材固化
- [x] 按 `finish-docs` 更新 state/changelog/dev-log 并逐项完成两个交付门

## 开工基线与用户确认

- 日期：2026-08-13。
- Git 基线：`37d5707`（M31 模块提交）；开工时工作树只有未跟踪的 `docs/notes/m32-plan.md`，属于用户已确认的当前模块计划。
- 当前 active Knowledge release：`4e86bdddbf15ca7ce1284f27b7507fedac70a69c098f5a1952cf6e71001e95a7`，11 entries，corpus identity `abdc9aed...`，首次发布所以 `previous=null`。
- 当前 M31 `phase4-v1`：8 Scenario / 12 required，最终 artifact `197e0d62...`，只证明 P1 contract/security；M27 v3 和所有历史 artifact/report 继续只读。
- 用户确认 G-M32 **方案 A**：M32 只完成 deterministic retrieval adapter、Knowledge Tool、ACL/Evidence 和 retrieval Eval；Shared Evidence Gate、Composer、generation-visible/citation、公开 RAG API 留给后续模块。
- 方案 B 的做法与风险：同模块完成整个 P2，可更早看到用户可见 RAG，但会同时修改检索、生成、API、Trace、Eval，并提前触发远端出站和公开响应决策。计划建议 A，用户明确选择 A。
- G4 本模块不触发：M32 只形成首个已验证 adapter 候选和本地 baseline，不选择 P3 默认 adapter，不改变模型、embedding、vector backend、LangFuse 或 API 默认行为。

## 开工参考复核

- `DBGPT-RESOURCE/TOOL`：借鉴 chunk 与 structured reference 同步返回的 seam；不照搬纯文本 Tool Observation、只使用第一个 resource、异常字符串进模型上下文或文件名/score 冒充 citation。
- `ARAG-TOOLS/STATE`：借鉴候选检索与上下文扩展分层，以及保存本轮 Tool 实际 context；DataPilot 改为 stable entry identity + typed Evidence/ExecutionEvidence，不引入 parent-child、Graph、rewrite、compact 或 Agent 自主多次取证。
- `DBGPT-EVAL` 与 `ARAG-EVAL`：借鉴 retrieval 指标独立于 answer、先固化实际运行输出再评分；不照搬空结果统一记零、notebook 简单均值、评分时重跑 Tool 或大型 evaluator DAG。
- `GUSTO-WORKFLOW`：把末尾从多种 metadata 猜测并拼接 sources 作为身份断裂反例；不照搬 PostgreSQL→Milvus 级联、fallback 答案或 Tool 内生成答案。
- DataPilot 适配以 roadmap/state 为准：pre-selection 前置硬过滤、pre-generation 复核、Document Evidence 只来自 active release、ledger 最远到 selected、一次 Scenario 一次 Tool、closed-world artifact、Knowledge 远端用途默认 deny。

## 过程记录

- 开工阶段尚未发现 plan 与当前代码、roadmap、state 或参考源码冲突。
- 实现参数、具体文件名和词法评分内部细节仍按 plan 保持为本模块实现细节；若发现需要改变核心合同、范围、默认或安全边界，将暂停并请求用户确认。
- **首轮聚焦测试**：`10 passed / 3 failed`。两条 no-candidate 失败来自当前算法把“平台”这类公共词造成的 `0.0074` 极低正文重合也当候选；stale case 失败来自预算允许选 2 条，quality revision 被模拟撤销后，basic refund 仍是合法 selected，所以 Tool 正确返回 `evidence_retrieved`。两者都是实现/fixture 问题，不改变 C1-C4。
- **修正判断**：deterministic baseline 增加显式最小相关性门，过滤仅有公共词的极低重合；该阈值是 M32 本地 recipe 的可观察实现身份，不是长期默认或远程检索参数。stale fixture 改成 `max_selected=1`，精确验证 gold revision 在两次 ACL 间失效时的 `stale_revision`。
- **首轮完整 M32 测试**：`26 passed / 2 failed`。失败来自 Eval 将 authorization identity 当作 document safe ref 与 gold 对账，以及 stale case 把内部 candidate ledger 误当成 Tool 已返回 Evidence；Tool 实际已正确拦截 selected。修正为从同次 active bundle 映射稳定文档引用，并以 `selected_evidence` 判断是否返回。
- **修正后 M32 聚焦门**：`28 passed in 0.65s`；同批还覆盖 adapter query/runtime identity、越预算、rank、duplicate、unknown entry 和非法 score 的失败关闭。
- **M31/P1 受影响回归**：M30 catalog + M31 release/governance/Evidence/phase4 contracts 共 `56 passed in 2.26s`。
- **API/Text2SQL/Eval 首次受影响回归**：命令在 `180.3s` 外层时限终止，终止前 `31` 项通过且无失败输出；这是未完成运行，不能计作通过，后续换新 basetemp 完整重跑。
- **API/Text2SQL/Eval 完整受影响回归**：换新 basetemp 后 `188 passed, 1 warning in 446.43s`；warning 是既有 Starlette `TestClient`/httpx 弃用提示。
- **收工安全审查发现并修复**：内部 candidate ledger 在 pre-generation revision 撤销时应继续保留审计事实，但原安全投影也带出了 candidate revision/content identity，形成存在性侧信道。现改为 `safe_projection()` 只投影最终 selected Evidence；内部 `RetrievalOutcome.ledger` 不变，并增加 stale 非泄露回归。

## 模块名称与改动文件清单

- 模块：M32「确定性知识取证与 Knowledge Tool」，对应 Phase 4 P2 的第一个安全取证能力切片，不代表 P2 整体完成。
- 计划与过程素材：`docs/notes/m32-plan.md`、`docs/notes/m32-notes.md`。
- 生产实现：`engine/rag/retrieval.py`、`engine/rag/knowledge_tool.py`。
- 独立 Eval：`eval/rag_retrieval_contracts.py`。
- 测试：`tests/test_m32_retrieval.py`、`tests/test_m32_knowledge_tool.py`、`tests/test_m32_rag_retrieval_contracts.py`。
- 起始 commit 为 `37d5707236a86953b1a0098f25d8a5443051601e`；上述 8 个文件均为 M32 新文件。既有代码、配置、历史 report/artifact 未修改。

## 关键决策与取舍

1. **模块边界采用方案 A**：候选 A 是先闭环 adapter + Tool + ACL/Evidence + retrieval Eval；候选 B 是同模块继续完成 Gate/Composer/citation/API。B 的主要风险是把取证、生成、公开合同和远端出站同时耦合，失败难归因；计划推荐 A，用户最终确认 A。M32 因此不提供用户可见 RAG answer。
2. **先 ACL、后 adapter**：未授权 entry 连正文和 identity 都不交给检索器，避免未来远端 adapter、日志、score 或命中数量形成侧信道。选中后再做 pre-generation 检查，但 M32 只推进到 `selected`，不冒充真实入模。
3. **本地词法 baseline 是可替换 recipe，不是 P3 默认**：使用可解释的 title/key/content 2–4 gram 排序与 `0.05` 低相关门；阈值进入 `title-key-content-ngram-min005-v1` identity。它只服务离线确定性 baseline，G4 仍未触发。
4. **内部审计与安全投影分离**：内部 ledger 保留全部候选和被二次 ACL 拦截的事实；`safe_projection()` 只展示最终 selected Evidence，防止 revision/content identity 泄露。技术不可用与业务零结果保持不同内部原因，权限拒绝与知识不存在则在安全投影收敛。
5. **Eval 一题只执行一次**：required 合同与 advisory retrieval 指标只读同一 `ExecutionEvidence`，技术不可用时 coverage 为 `not_observed`；不通过重跑 Tool 或把 advisory 均值混进 required Gate 制造好看的结果。

## 阶段 1 注释小结

- 检查范围：3 个新增实现/Eval 文件全量检查；测试函数因名称自描述按 skill 规则豁免逐函数 docstring，但文件级职责和关键 fixture 已说明。
- 第 1 遍覆盖：AST 复核共 62 个类/函数，最终 62/62 有入口说明；收工阶段补写 24 处缺失 docstring，第二次扫描为 0 缺失。
- 第 2 遍深度：深化 deterministic recipe identity、中文 n-gram baseline、pre-selection/pre-generation 双检、selected 与 generation-visible 边界、closed-world artifact、`not_observed` 与业务失败分离等概念。
- 第 3 遍可读性：复核 Tool 的 active load → ACL → adapter → Evidence → recheck 多步骤控制流，以及 Eval 的 shared evidence、safe ref 映射和 Gate 投影；补充安全投影只保留 selected Evidence 的原因注释。
- 第 4 遍形式：主角类/函数保留 ★ 标记，Tool 四步骤分隔线保持一致；注释以中文为主，无 TODO/FIXME/“后续替换”式临时承诺。未发现需要继续调整的分隔线或过量 ★。

## 阶段 2 验证快照

- M32 首轮 adapter/Tool 聚焦：`10 passed / 3 failed`；失败已定位并修正，未掩盖。
- M32 首轮含 Eval：`26 passed / 2 failed`；暴露 Eval safe-ref 与“returned evidence”观察口径错误，修正后通过。
- 最终 M32 聚焦：`pytest ... tests/test_m32_retrieval.py tests/test_m32_knowledge_tool.py tests/test_m32_rag_retrieval_contracts.py -q` → `28 passed in 0.71s`（安全投影修复后快照）。
- M30/M31 P1 回归：5 个 catalog/release/governance/Evidence/phase4 contract 文件 → `56 passed in 2.26s`。
- API/Text2SQL/Eval 受影响回归：第一次在 `180.3s` 外层超时，只完成 31 项且无失败，未计作成功；新 basetemp 完整重跑 → `188 passed, 1 warning in 446.43s`。
- 全仓确定性门：`python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m32-full-suite -q` → `304 passed, 3 skipped, 1 warning in 537.27s`。3 个 skip 是本机 `127.0.0.1:19530` 没有可用 Milvus 的既有条件跳过；warning 是既有 Starlette `TestClient`/httpx 弃用提示，均不影响 M32 离线合同。
- 编译门：项目 Python 执行 `python -m compileall -q engine app eval tests` 成功，无输出。
- 清洁门：新增范围尾随空白扫描无命中，`git diff --check` 成功；`git status --short` 只列出上述 8 个 M32 新文件。
- 外部边界：所有运行均未启用或调用真实 LLM、remote embedding/rerank、Milvus、LangFuse Cloud；因此不能据此宣称真实语义检索或答案质量成立。

## 参考资料

- `docs/phase4-reference.md` 指定的 DB-GPT Resource/Tool：借鉴 chunk 与 structured reference 同步返回的 seam；未照搬纯文本 Observation、首 resource 假设或异常字符串入上下文。
- ARAG Tool/State：借鉴候选检索与后续上下文消费分层、保存本轮实际 Tool 输出；未照搬 Graph、rewrite、compact、parent-child 或自主多次调用。
- DB-GPT/ARAG retrieval Eval：借鉴 retrieval 与 answer 分评、先固化执行输出再评分；未照搬空结果一律记零、notebook 简单均值或 scorer 重跑 Tool。
- Gusto workflow sources/finalize：作为 metadata 拼接 source 导致身份断裂的反例；未照搬 PostgreSQL→Milvus 级联、fallback answer 或 Tool 内生成答案。

## Handoff（下一模块交接）

### 已完成且后续可以依赖

- `RetrievalAdapter`/`RetrievalBatch`/`RetrievalBudget` 已冻结最小可替换 seam；本地 deterministic adapter 对固定 query/corpus/recipe 可复现，并对重复、越预算、非法 identity/rank/score 失败关闭。
- `KnowledgeTool.retrieve()` 已闭环 active release、pre-selection ACL、一次 adapter 调用、Document Evidence candidate/selected、pre-generation 复核和结构化失败归因。
- `RetrievalOutcome` 提供内部完整 ledger、selected Evidence、pre-generation decisions 与安全 diagnostics；安全投影不会泄露未返回候选。
- `phase4-rag-retrieval-v1` 提供 6 Scenario、20 条 required 全通过、3 条 retrieval advisory（2 passed、1 technical-unavailable not_observed）的确定性 artifact/Gate 基线。

### 下一模块建议入口

- 建议首先解决的主要问题：让已选中的 Document Evidence 真正经过共享 Evidence Gate 进入 Composer，并形成可验证 citation 的回答闭环。
- 建议从哪些现有 seam、失败簇或未闭环能力开始：从 `KnowledgeTool.retrieve()` 的 `selected_evidence`、`pre_generation_authorizations`、M31 `EvidenceLedger.transition(..., generation_visible)`、citation slot/validator 以及 M29 四轴产品状态开始。
- 为什么这是自然的下一步：M32 已把“找对/拿对/没越权”的取证失败与未来“入模/生成/引用”失败分开，下一轮可以只冻结回答与 citation 语义，不再同时调检索。

这里只提供下一轮规划输入，不提前冻结下一模块的模块号、名称、文件结构、参数或具体实现。

### 未完成、未证明与当前风险

- 未完成：Shared Evidence Gate、Composer、`generation_visible`/`cited`、用户可见 citations、公开 RAG API、Router/Graph/Hybrid 与 Trace 接线。
- 尚未通过真实验证证明：真实 LLM 答案充分性、语义 citation support、远程 embedding/rerank、Milvus 检索、长文/PDF ingestion 和 P3 端到端可靠性。
- 活跃风险或兼容边界：11 条短知识上的词法成功不能外推长文语义检索；公开层仍须把知识不存在与无权限安全收敛；未验证 caller 不能通过请求体角色声明获取文档。

### 必须延续的决策与边界

- 延续用户确认的方案 A：M32 只交付安全取证；后续不能把它改写成已经完成 P2 或用户可见 RAG。
- Knowledge 远端用途继续默认 deny；不得因下一步需要 Composer 就偷偷放行 provider、改变模型/embedding/vector/LangFuse 默认。
- Evidence 只有真正交给 Composer 时才能从 selected 推进 generation-visible；只有通过 citation validator 才能成为 cited。
- M31 `phase4-v1`、M27 v3 及历史 artifact/report 继续只读；新的 answer/citation Eval 不与 retrieval-only advisory 混算。

### 待触发的决策门

- 决策门：Roadmap G4「首个 Knowledge Tool 运行时默认 adapter」。
- 触发条件：P2 回答/citation 闭环通过，且有足够闭环可靠性证据比较 adapter 候选。
- 触发前允许做什么：继续使用 M32 deterministic adapter 作为本地可替换 baseline；冻结 Gate/Composer/citation 合同并建立离线测试。
- 触发前禁止做什么：宣布该 adapter 为 P3 默认、引入远程 embedding/hybrid/rerank 或据此修改长期默认配置。

### 下一轮规划必读指针

- `docs/phase4-roadmap.md`：P2、跨里程碑不变量与 G0/G4，决定回答闭环范围和决策门。
- `docs/phase4-reference.md`：P2/Eval 能力卡及 Gusto finalize 反例，决定 Composer/source seam 的定点参考。
- `docs/notes/m32-plan.md`：第 5、8、10 节冻结的 C1-C4、验收边界和刻意遗留。
- `engine/rag/knowledge_tool.py::KnowledgeTool.retrieve`：下一层唯一应消费的 selected Evidence 与 pre-generation decision 来源。
- `engine/rag/evidence.py::EvidenceLedger.transition / allocate_citation_slot / validate_citations`：真实入模与 citation 完整性边界。
- `eval/rag_retrieval_contracts.py`：retrieval-only family 和一次执行证据口径；未来 answer Eval 必须独立分层。
- `tests/test_m32_knowledge_tool.py`、`tests/test_m32_rag_retrieval_contracts.py`：安全非泄露、一次调用、closed-world 与历史兼容回归门。

## finish-docs 执行清单

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

### finish-docs 执行结果

- 素材单一事实源：本文件的模块范围、关键决策、注释小结、验证快照、参考资料与 Handoff；关键素材完整，未退回 `finish-module`，三份文档初稿后也未发生二次补齐。
- `AI_CONTEXT.md`：替换当前模块/plan/notes 与已完成的“下一步做 retrieval”路线；改写“默认检索”以区分 Schema Retrieval 默认和未触发 G4 的 Knowledge baseline；新增 M32 事实、离线 Gate 与词法适用风险。退役/删除无；M31/M30 历史事实仍影响当前 active corpus、安全和兼容边界，继续保留。
- 旧结论复核：M32 未推翻旧安全、默认或 Eval 结论；在 M31 changelog 的已完成 retrieval 后续原位增加 `⚠️ 注`，当前 AI_CONTEXT 的过时路线已替换。
- dev-log 交付门：15/15 逐项核对通过；无二次补齐。
- 三文档交付门：11/11 逐项核对通过。
- 完整回读：已按顺序完整回读 M32 changelog 新章节、AI_CONTEXT 全文和 dev-log M32 新章节；未发现截断、乱码、标题层级错误、夸大或 notes 外结论。
- 交付检查：`git diff --check` 通过；Git 提示 tracked Markdown 将来可能由 LF 转 CRLF，属于 Windows 行尾提示，不是 diff 错误。M32 新文件另经尾随空白扫描无命中。
