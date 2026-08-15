# M33 可信 RAG 回答与 Citation 闭环开发素材

> 本文是 M33 开发过程事实源。实现中的决策、踩坑、验证证据和收工交接随进度即时补充，不在收工时凭记忆重建。

## Implementation checklist

- [x] 固化 Git、active release、M31/M32 合同与测试基线
- [x] 冻结 AnswerFlow、Gate、claim/citation、四轴结果和安全投影枚举（C1-C5）
- [x] 实现 Shared Answer Evidence Gate、最小 generation context 与稳定 context identity（C2）
- [x] 证明只有实际交给 Composer 的 selected Evidence 推进 `generation_visible`（C2）
- [x] 实现离线 deterministic Evidence-bound Composer 与有界 claim drafts（C3）
- [x] 由流程代码分配 claim/citation slot，接入现有 Citation Validator（C4）
- [x] 实现 validated answer、citation 用户视图、`docs_used` 兼容投影和四轴结果（C1/C4）
- [x] 覆盖 no candidate、semantic insufficient、ACL deny、stale、投毒、retriever/composer unavailable、citation invalid
- [x] 建立独立版本化 RAG answer/citation contract family 与一次执行共享证据（C5）
- [x] 实现 completed artifact closed-world 校验、required Gate 与 advisory 分层（C5）
- [x] 运行 Gate → Composer → citation/result → answer Eval 聚焦测试
- [x] 运行 M31/M32、API/Text2SQL/Eval 受影响回归与全仓确定性测试
- [x] 运行 compileall、`git diff --check` 并确认未调用真实 provider/Milvus/LangFuse
- [x] 整理 G4 证据并在选择默认 adapter 前请求用户确认
- [x] 按 `finish-module` 完成注释审查、验证和 Handoff 素材固化
- [x] 按 `finish-docs` 更新 state/changelog/dev-log 并完成交付门

## 开工基线与已确认边界

- 日期：2026-08-14。
- Git 基线：`895d340c0f7c2a2d616f5bf215b3e6b7d217c0fd`（`确定性知识取证与 Knowledge Tool`）。
- 开工工作树：用户/其他工具已有 `.codex/skills/finish-docs/SKILL.md`、`docs/dev-log.md` 修改；当前模块已有未跟踪 `docs/notes/m33-plan.md`。这些既有改动不回滚，M33 只在收工 skill 明确要求时基于当前内容增量更新 `docs/dev-log.md`。
- 用户已确认 G-M33 **方案 A**：M33 完成内部可信回答深 module，不接 `/api/query`、不增加 route hint、不提前实现 P3 Router/Harness。
- 开工时 active release：`4e86bdddbf15ca7ce1284f27b7507fedac70a69c098f5a1952cf6e71001e95a7`；pointer `8bf9e82a...`；`previous=null`；authorization/outbound policy 分别为 `document-authorization-v1` / `phase4-outbound-v1`。
- M32 retrieval 基线：`phase4-rag-retrieval-v1`，6 Scenario / 20 required 全通过；3 advisory 为 2 passed / 1 technical-unavailable `not_observed`。它只证明安全取证，不证明 answer/citation。
- Knowledge generation/sufficiency/judge 远端用途继续 deny；本模块不调用真实 LLM、embedding/rerank、Milvus 或 LangFuse Cloud。
- 开工时 G4 尚未选择：当时只允许完成 M33 实现、测试、Eval 和证据整理；最终决定见本文「G4 用户决定」。

## 开工参考复核

- `DBGPT-RESOURCE`：借鉴正文与 structured reference 同时越过生成 seam；DataPilot 改用 generation-visible typed Evidence 与稳定 context identity，不把 doc name/score 当 citation。
- `DBGPT-TOOL`：纯文本正文、零结果和异常混在 Tool Observation 是反例；M32 Tool 继续只取证，M33 不把异常字符串送入 Composer。
- `ARAG-STATE`：借鉴保存本轮真实 Tool context；DataPilot 固化实际 Composer 输入的 EvidenceRef/ledger stage，不引入 Graph、message reducer、loop 或 compact。
- `GUSTO-WORKFLOW`：`finalize` 后置猜 metadata 并拼 sources 是身份断裂反例；M33 改为先分配 claim slot、再确定性校验、最后公开 answer/citation。
- `codebase-design`：对 P3 只暴露一个 AnswerFlow interface；Gate/Composer/validator 是内部职责，不要求调用者手工排序拼装，也不为唯一离线 Composer 制造假 adapter seam。

## 模块名称与改动文件清单

- 模块：M33「可信 RAG 回答与 Citation 闭环」。模块起始 commit 为 `895d340c0f7c2a2d616f5bf215b3e6b7d217c0fd`；由于 M33 文件尚未提交，本次按起始状态、`git status --short` 和当前工作树全量检查。
- `docs/notes/m33-plan.md`：用户已确认的 M33 计划与 G-M33/G4 决策门。
- `docs/notes/m33-notes.md`：implementation checklist、开发证据、决策、验证与 Handoff。
- `engine/rag/answer_flow.py`：AnswerFlow、Shared Gate、generation context、deterministic Composer、citation 接线、四轴结果与安全投影。
- `eval/rag_answer_contracts.py`：独立 `phase4-rag-answer-v1` Scenario catalog、单次执行 evidence、closed-world artifact、required Gate 与 advisory summary。
- `tests/test_m33_answer_flow.py`：主链、硬约束、故障注入和非泄露测试。
- `tests/test_m33_rag_answer_contracts.py`：Eval 确定性、一次执行、分母和 artifact 篡改反例。
- 开工前已存在的 `.codex/skills/finish-docs/SKILL.md`、`docs/dev-log.md` 修改不属于 M33 实现范围，未回滚；后者只会在 `finish-docs` 明确要求下基于当前内容增量更新。

## 关键决策与取舍

- **G-M33 用户选择方案 A**：先完成内部可信 AnswerFlow 深 module，P3 再接 HTTP/Router。另一选项是 M33 直接接 `/api/query`，但会迫使本模块提前引入 route hint、可信 caller 接线或 P3 控制权；风险是产生短命公开合同甚至误信请求体角色，因此当时建议并最终选择 A。
- **Composer 采用确定性 extractive baseline**：选择“从真实 generation-visible Evidence 抽取有界 claim”，而非假装已有远程模型 adapter。优点是当前离线授权边界内可复现地证明 claim/citation 身份闭环；风险是措辞不够自然，且不代表开放答案质量。未来远程 Composer 必须另过 outbound 与效果门。
- **内部审计与公开投影分离**：Composer/citation 失败时 ledger 保留真实 `generation_visible` 阶段，但公开 safe projection 清空 Evidence/context。若直接公开内部账本，会在安全拒绝路径泄露无权或投毒文档是否存在。
- **Eval 一题一次执行**：状态、stage、citation、支持度和非泄露 assertion 全部引用同一 ExecutionEvidence；不让 scorer 重跑 retrieval/Composer，也不把 advisory 混入 required Gate。
- **G4 用户选择方案 A**：将 `knowledge-deterministic-lexical-v1` 作为 P3 首个默认 baseline。备选 B 是暂停 P3、先做 embedding/hybrid 候选；当前 9 个回答闭环 Scenario 无关键失败，选择 B 缺少失败证据且会阻塞主线，因此建议并最终选择 A。该结论不等于词法检索最终最优。

## 阶段 1 注释小结

- 覆盖扫描：4 个代码/测试文件共 106 个类/函数；95 个具有 docstring，11 个为纯赋值 `__init__`、局部授权 closure 或已由 fixture 类解释的单行 override，按 skill 规则豁免；0 个未解释的非豁免项。
- 质量扫描：补强 generation context、Evidence Gate、extractive claim、四轴状态、closed-world artifact、required/advisory 分母等新概念；重点解释了“为什么只推进真实入模 Evidence”“为什么失败 ledger 内部保留但公开清空”“为什么 Eval 不重跑”。
- 可读性扫描：`RAGAnswerFlow.run()` 已按 Tool → Gate → Composer → Validator 分步；为 Eval runner 和 artifact validator 新补 7 处分步/安全注释；测试新增 18 处用例/fixture 意图说明。
- 形式扫描：为 AnswerFlow 与 Eval 主入口 docstring 增加 2 个 ★；Eval runner/validator 补齐 7 处分隔线，中文注释和关键标记密度检查通过。

## 过程记录

- 开工调查尚未发现 plan 与当前代码/state 的冲突。
- 首轮实现前继续定点核对 M31 Evidence/Citation、M32 Knowledge Tool/Eval 的真实类型与测试 seam；若需要改变核心合同、范围、安全边界或采用临时替代方案，将暂停并请求用户确认。

### 2026-08-15：AnswerFlow 主链与首轮合同测试

- 新增 `engine/rag/answer_flow.py`，对 P3 暴露单一 `RAGAnswerFlow.run()` interface；内部顺序固定为 Knowledge Tool → Shared Gate → generation context → deterministic Composer → 代码分配 claim/citation slot → 既有 Citation Validator。
- `generation_visible` 只推进实际交给 Composer 的 Evidence；Composer 故障或 citation 校验失败时，内部 ledger 保留真实停留阶段用于审计，但公开 safe projection 清空 Evidence/context，避免失败路径泄露文档存在性。
- 首版 Composer 采用确定性的 extractive claim，不是假装成远程模型 adapter；目标是冻结 Evidence/claim/citation 的可信闭环，不宣称回答语言质量已达到最终默认能力。
- 文档正文继续按不可信输入处理：明显伪系统、伪 citation、Tool 调用指令在 Gate 阻断，既不进入 Composer，也不进入公开投影。
- 首轮验证：`pytest tests/test_m33_answer_flow.py -q` 为 `10 passed`。覆盖成功、zero-hit、semantic insufficient、ACL、stale revision、prompt injection、retriever/composer unavailable、citation tamper 与 invented claim。
- 发现并修正测试假设：GMV authority 文档实际 key 为 `gmv_metric_note`、角色为 `ops`、公式为 `SUM(orders.order_amount)`；未改变生产合同。
- M31/M32 首次回归出现 `51 passed + 22 setup errors`：错误均发生在 pytest 清理历史固定 `.agent_work/temp/pytest-tmp` 时触发 Windows `PermissionError`，相关测试体未运行，不记作产品回归失败。后续验证改用新的 M33 专属 `--basetemp`，不删除或覆盖被占用目录。
- 全仓第一次运行在 `120.3s` 外层命令时限到达后被终止，终止前输出 63 个通过点且没有失败；该轮不记作全仓通过，改用新 basetemp 和更长时限完整重跑。

## 验证快照

- `pytest tests/test_m33_answer_flow.py -q`：`10 passed in 0.41s`。
- `pytest M31/M32 聚焦集合 -q` 首次运行：`51 passed, 22 errors`；22 项均为旧 basetemp 清理权限错误，待专属 basetemp 重跑确认。
- `pytest --basetemp=.agent_work/temp/pytest-m33-regression-20260815 M31/M32 聚焦集合 -q`：`73 passed in 1.44s`。
- M33 AnswerFlow + Answer Eval：`28 passed in 0.80s`。
- 全仓第一次运行：`120.3s` 命令超时，终止前 63 项通过、无失败输出；待完整重跑。
- 全仓完整重跑：`332 passed, 3 skipped, 1 warning in 444.90s`；3 项为既有条件 skip，warning 为既有 Starlette/httpx deprecation。
- 最终补强 Gate/Composer/citation failure 测试后，M33 聚焦集合：`33 passed in 0.84s`。
- M33 Eval artifact：`6b45cb45fc135858a4c6cac4dc561b57ba7442f9720f94811cbf1ec35f9bcc0a`；9 Scenario；required `60/60 passed`；advisory `3 eligible / 2 observed passed / 1 technical-unavailable not_observed`。
- `compileall app engine eval tests scripts`：通过，pycache 定向到 `.agent_work/temp/m33-pycache-20260815`；`git diff --check`：通过。
- G4 确认后的最终全仓复验：`pytest --basetemp=.agent_work/temp/pytest-m33-final-20260815 -q` 为 `337 passed, 3 skipped, 1 warning in 498.86s`。
- `finish-module` 专属全仓命令：`pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m33-finish-module-20260815 -q` 为 `337 passed, 3 skipped, 1 warning in 462.10s`。
- 3 个 skip 是既有条件跳过；唯一 warning 是既有 FastAPI `TestClient` 的 Starlette/httpx deprecation，不由 M33 引入，不影响本模块合同。
- `finish-module` 再次直接执行 M33 Eval：artifact identity 仍为 `6b45cb45fc135858a4c6cac4dc561b57ba7442f9720f94811cbf1ec35f9bcc0a`；9 Scenario；required `60 passed / 0 failed / 0 not_observed`；advisory `2 passed / 0 failed / 1 technical-unavailable not_observed`。
- 最终 `compileall -q app engine eval tests scripts` 通过，pycache 定向到 `.agent_work/temp/m33-finish-pycache-20260815`；最终 `git diff --check` 通过。

## G4 决策证据（等待用户确认）

- 当前 deterministic lexical adapter 已在 M32 retrieval Gate（6 Scenario / 20 required）和 M33 完整 answer/citation Gate（9 Scenario / 60 required）中全绿；质量退款和 GMV 两条代表性正常链路均完成 `selected → generation_visible → cited`。
- 安全/失败簇已覆盖 zero-hit、结构化语义不足、ACL 非泄露、revision 失效、文档 prompt injection、retriever unavailable 和 citation invalid；失败路径不会公开未验证答案。
- 适用边界仍很明确：追加后 corpus 有 22 条短知识，检索仍是词法 baseline；未证明长文、同义改写、跨文档复杂问题和开放措辞质量，也未运行 embedding/rerank/真实 LLM。
- 方案 A：把当前 deterministic adapter 记录为 **P3 首个初始默认 baseline**。优点是 P3 可立即开发唯一 Router/Harness，链路离线、稳定、可解释；含义仅是“首个工程默认”，不表示语义最优，后续候选仍需独立 A/B 后才能替换。
- 方案 B：暂不选默认，先新增检索候选模块。优点是先补语义效果；代价是 P3 主线暂停，而且当前没有关键闭环 Scenario 失败来证明必须先换检索器。
- 建议：选择 **G4 方案 A**。依据是当前 adapter 已足以支撑 P3 的首个可信端到端基线，而把“是否值得换 embedding/hybrid”留给有 held-out 失败证据的后续模块更清楚。

### 2026-08-15：G4 用户决定

- 用户确认 **G4 方案 A**：将 M32 `knowledge-deterministic-lexical-v1` 记录为 P3 首个默认 Knowledge Tool adapter baseline。
- 该决定的含义是 P3 可以直接以离线、稳定、可解释的链路开发 Router/Harness；不宣称词法检索语义最优，也不授权本模块修改配置、接 HTTP、提前开发 P3 或静默替换未来候选。
- 后续若要切换 embedding/hybrid/rerank，仍需用独立候选 identity、held-out 失败证据和 A/B 结果重新过门。

## Handoff（下一模块交接）

### 已完成且后续可以依赖

- `RAGAnswerFlow.run()` 已形成 P3 可直接调用的内部深 interface：输入问题、`TrustedCaller`、run/purpose、受控 Evidence requirement 与预算，输出不可变四轴结果、validated claims/citations、ledger 和安全投影。
- Shared Gate 已确定性检查同轮/stage/purpose、当前 active revision、pre-generation authorization、结构化充分性和文档指令安全；只有实际传给 Composer 的 Evidence 进入 `generation_visible`。
- deterministic extractive Composer、代码分配 claim/citation slot、M31 Citation Validator 和 `cited` ledger 已闭环；`docs_used` 只从 validated citations 派生。
- `phase4-rag-answer-v1` 已冻结 9 Scenario / 60 required 的本地基线，artifact identity 为 `6b45cb45fc135858a4c6cac4dc561b57ba7442f9720f94811cbf1ec35f9bcc0a`；M31/M32 历史 family 未改写。

### 下一模块建议入口

- 建议首先解决的主要问题：进入 Phase 4 P3，由唯一顶层 Router/Harness 决定 SQL/RAG，并把可信 caller 与两条深 module 结果投影到同一 `/api/query` 合同。
- 建议从哪些现有 seam、失败簇或未闭环能力开始：从 `RAGAnswerFlow.run()`、现有 Text2SQL pipeline、`TrustedCaller` adapter seam、M29 G0 四轴响应合同和 P3 Scenario blueprint 开始；先冻结 controller 所有权与 route truth，再设计 Graph state/node。
- 为什么这是自然的下一步：P2 的内部可信 RAG 回答已经闭环，但普通 HTTP 用户仍不可达；G4=A 又已允许 P3 直接采用确定性 adapter baseline，无需先插入检索候选模块。

这里只提供下一轮规划输入，不提前冻结下一模块的模块号、名称、文件结构、参数或具体实现。

### 未完成、未证明与当前风险

- 未完成：没有修改 `/api/query`、`AgentResponse`、Router、LangGraph、Hybrid SQL+RAG、全局 Trace 或生产认证 provider。
- 尚未通过真实验证证明：没有运行真实 LLM Composer、remote sufficiency/judge、embedding/rerank、Milvus、LangFuse Cloud，也没有证明长文、同义改写、跨文档复杂问题和自然措辞质量。
- 活跃风险或兼容边界：当前 corpus 为 22 条短知识；词法检索和 extractive Composer 适合首个确定性 baseline，但效果上限有限；P3 接 HTTP 时仍需同时守住可信 caller、旧客户端兼容响应和安全 Trace。

### 必须延续的决策与边界

- G-M33=A：M33 只提供内部 AnswerFlow；P3 必须复用它，不能重新实现 Gate/Composer/Validator，也不能新增临时公开 route hint。
- G4=A：`knowledge-deterministic-lexical-v1` 是 P3 首个默认 baseline；未来替换必须使用独立候选 identity、held-out 失败证据和 A/B，不得把“默认”误写成“语义最优”。
- 请求体 `user_role` 仍是不可信声明；文档授权只能消费明确来源的 `TrustedCaller`。Knowledge 远端 generation/sufficiency/judge 仍默认 deny。
- M27、M31 `phase4-v1`、M32 `phase4-rag-retrieval-v1`、M33 `phase4-rag-answer-v1` 必须分层保存，不回填、不混算、不改写历史 artifact。

### 待触发的决策门

- 决策门：P3 顶层 Harness/Router 的具体范围与公开接线方案。
- 触发条件：下一模块调查 roadmap、当前 `/api/query`/`AgentResponse`、Text2SQL pipeline、`RAGAnswerFlow` 和可信 caller seam 后形成具体计划。
- 触发前允许做什么：只读调查代码、测试、P3 Scenario 和参考项目的 orchestrator/state seam。
- 触发前禁止做什么：提前改 HTTP 合同、信任请求体角色、引入第二个顶层 controller、打开远程 Knowledge 出站或静默更换 G4 baseline。

### 下一轮规划必读指针

- `docs/state/AI_CONTEXT.md`「当前状态 / 最新事实快照 / 必读规则」：续接入口与最新默认事实。
- `docs/phase4-roadmap.md`「P3 Agent Harness」及跨里程碑不变量：决定下一能力切片与不得破坏的合同。
- `docs/notes/m33-plan.md`「关键合同 C1-C5、G4、Handoff」：M33 对 P3 已交付和未交付的精确边界。
- `docs/notes/m33-notes.md`「关键决策与取舍、验证快照、Handoff」：真实证据、风险与 G4 用户决定。
- `engine/rag/answer_flow.py::RAGAnswerFlow.run`、`tests/test_m33_answer_flow.py`：P3 应调用的 interface 和安全失败真值。
- `eval/rag_answer_contracts.py::SCENARIOS`、`tests/test_m33_rag_answer_contracts.py`：RAG-only 基线及不得混入 Router Eval 的证据口径。
- `app/api/query.py::query`、`app/schemas/agent.py::QueryRequest / AgentResponse`、`engine/governance.py::TrustedCaller`：公开入口、兼容响应与可信身份之间尚未闭环的 seam。

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

## finish-docs 执行结果

- 素材来源：本文件的模块范围、关键决策、注释小结、验证快照、参考复核和 Handoff；辅以 Git 范围核对与三份既有文档全文/近期章节。
- 关键素材检查一次通过，未退回 `finish-module`；三份文档初稿完成后未发生 dev-log 二次补齐。完整回读时只发现 `AI_CONTEXT.md` 仍残留一处“下一阶段建议进入 RAG”的旧路线措辞，已执行 1 次状态文档清理后复核。
- dev-log 交付门：15/15 逐项通过。
- 三文档交付门：11/11 逐项通过；M32 的“G4 未触发”历史结论已在 changelog 原位添加 `⚠️ 注` 指向 M33 新决定。
- 完整回读：已按顺序回读 M33 changelog 新章节、AI_CONTEXT 全文关键状态/默认/事实/路线/活跃坑、dev-log M33 完整章节；无截断、乱码、标题层级错误或能力夸大。
- `git diff --check`：通过；仅出现 Git 的 LF→CRLF 工作区提示，不是 whitespace error，不影响交付。

## 2026-08-15 知识库内容追加（方案 A）

- 本次是 M33 的内容补充，不是新模块：新增 8 条 `metrics.yaml` 指标 projection 和 3 份不新增业务承诺的边界文档，catalog 由 11 条增至 22 条。
- candidate 首轮 `14 passed / 1 failed / 1 deselected`；失败来自新增测试问法与正文词面重合不足。只把测试问题改得更明确，没有调整检索阈值、旧 gold 或生产正文；重跑为 `15 passed / 1 deselected`。
- 新 active release 为 `7d0d0937...`，previous 为旧 `4e86bdd...`，corpus `1927eb53...`，build `fd1a8c52...`，pointer `7e41ef20...`；ACL/outbound policy identity 不变。
- 新 corpus 上 `phase4-v1` 为 12/12、retrieval 为 20/20、answer 为 60/60 required；全仓为 `342 passed, 3 skipped, 1 warning`，`compileall` 与 `git diff --check` 通过。
- 能力边界不变：这些仍是短知识和词法 baseline，不证明长文、同义改写、真实 LLM 或开放语义质量。
