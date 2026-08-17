# M37 开发素材：一次有界 Follow-up 与窄范围 Document Evidence 重取证

> 本文件只记录 M37 实施过程中的清单、关键判断、踩坑和验证证据；模块合同以 `m37-plan.md` 为准。

## Implementation checklist

- [x] 复核 M36 turn/thread、M35 Harness、RAG Evidence/AnswerFlow、API/Trace 与 Eval 的实际接口。
- [x] 实现默认关闭、显式开启的一次 follow-up thread；保持旧请求 `thread=None`。
- [x] 实现服务端签发的 closed-world follow-up action/spec 与严格字段校验。
- [x] 实现 SQL follow-up 每次重新执行 Text2SQL，禁止复用旧 SQL/rows/Evidence。
- [x] 实现 22-entry 业务知识 release 的窄 B：同一规则解释/改述可按 active identity 重水化并重新过 Gate；需求或 identity 变化时同一 RAG Tool 最多重检索一次。
- [x] 保持 EnterpriseRAG-Bench external profile 每次重新检索，禁止跨 runtime 通用 rehydrate。
- [x] 实现 follow-up owner/version/TTL/concurrency/budget stop 与安全失败投影。
- [x] 扩展 `/api/query`、响应投影与 Trace；不记录 raw thread id、answer/rows/body 或旧 citation id。
- [x] 新增 `phase4-harness-followup-v1` sequence Eval 与 M37 专项测试。
- [x] 跑聚焦测试、受影响回归、静态检查和全仓验证。
- [x] 按 `finish-module` 完成注释审查、技术档案、state/changelog 更新和交付核对。

## 开工基线（2026-08-17）

- M36 已由用户验收；工作区已有 `docs/state/AI_CONTEXT.md` 的“已验收通过”修改，M37 保留并在收工时基于它更新当前模块状态。
- `tests/test_m36_turn.py` 仅有文件末尾空行差异，视为上一模块/用户现有修改，不据此扩大 M37 范围。
- `docs/notes/m37-plan.md` 为当前已确认 plan；用户决策为 G-M37-1 方案 A，以及 G-M37-2“窄 B”。
- 窄 B 不是临时简化：业务 release 的等价 Evidence 重水化、变化后单次重检索、SQL/external 强制重取证都必须在本模块形成正式合同和测试。
- 本轮不运行真实 LLM、远程 embedding、Milvus 或 EnterpriseRAG-Bench 大评测；M37 sequence Eval 使用确定性运行证据，与现有 M27/M31–M36/M34 artifact 分账。

## 关键决策与过程记录

- 代码核验确认业务 `EvidenceRef` 的 `authority_identity + revision + content_identity + anchor` 可在当前 active bundle 直接对照 `CatalogEntry`，且既有 `authorize_document(pre_selection/pre_generation)`、Answer Gate、ledger 与 citation validator 均可复用；因此计划的条件降级门未触发。
- Thread 状态升级为 `m37-thread-v2`，clarification 与 follow-up 继续共用同一个 manager/owner/version/TTL/clear 容器；没有在 API 建第二份字典。
- 服务端动作冻结为 SQL `adjust_sql_scope`，RAG `explain_same_evidence` / `ask_related_evidence`。只有第二者中的同 Evidence 解释动作由代码声明 requirement 等价，客户端字段不能自行开启复用。
- RAG 窄复用在 `RAGAnswerFlow` 内完成：业务 active identity 唯一且重新授权通过时构造新 run Evidence；identity 变化或 requirement 不等价时调用 Knowledge Tool 一次；授权拒绝直接停止。SQL adapter 不读旧结果，external runtime kind 固定走 retrieval。
- API 半截 follow-up 测试暴露既有统一校验处理器会把 Pydantic v2 `ctx.error=ValueError` 原样交给 JSON，导致本应为 422 的请求在序列化时抛异常。修正为先经 `jsonable_encoder`，这是闭合 M37 请求合同所需，不改变合法请求或业务四轴。
- 按 `phase4-reference.md` 重新定点复核 ARAG `graph_state.py`、`edges.py`、`graph.py`、`nodes.py`：借鉴显式 Tool/iteration budget、任务/澄清分离、去重记录已执行 context/action；DataPilot 将其收敛为一次 follow-up budget、typed task/Evidence snapshot 和 safe validity fact。不照搬 `MessagesState` 全历史、LLM rewrite/summary、正文 `retrieved_contexts` 跨轮累计、强制搜索、fallback answer、`InMemorySaver + interrupt` 或开放 Tool loop。

## 验证记录

- 首轮 M36/M33/M35 兼容：`32 passed in 0.86s`。
- M37 首批 turn/rehydrate 合同：`7 passed in 0.78s`；API 初跑发现统一 422 序列化问题，修正后 `2 passed, 1 warning in 1.28s`。
- M37 sequence Eval：首轮 completed validator 正确拒绝了一条错误 assertion（ACL deny 没有新 Evidence，不应被要求伪造新 ref）；修正 assertion 为“成功必须新 run Evidence，安全拒绝必须无旧 id 注入”后 `2 passed in 0.72s`。
- M37 + M36/M35/M33 聚焦：`47 passed, 1 warning in 1.52s`。
- M31–M37 受影响安全/RAG/Harness/API/Eval 回归：`162 passed, 1 warning in 39.19s`。
- API/配置兼容回归：`19 passed, 1 warning in 92.14s`；同一命令中的 `compileall -q app engine eval tests demo` 与 `git diff --check` 通过。
- `phase4-harness-followup-v1` 确定性执行：10 sequences / 22 turn evidence / 50 required assertions，`50 passed`，artifact identity `1185edf04c42439dedf5e3dc051be13060a462bd05e79c48d3b975fdce634b25`。
- warning 为既有 Starlette TestClient/httpx 弃用提示；上述命令均未调用真实 LLM、远程 embedding、Milvus、LangFuse Cloud 或外部 profile 大数据。

## 后台全仓验证前 checkpoint（2026-08-17）

- 关键决策：G-M37-1 方案 A 与 G-M37-2 窄 B 均按正式合同实现；没有临时替代、默认行为扩大或跨 runtime 通用复用。
- 改动范围：Harness contracts/thread/turn/graph/adapters，RAG AnswerFlow，API schema/projector/Trace、统一 422 序列化、Streamlit 最小表单，新 follow-up Eval 与四个 M37 测试文件；未改数据库、模型/embedding/LangFuse 默认、M27/M31–M36 旧 artifact、M34 profile 或 Hybrid。
- 已完成验证：M37 专项 14 passed；M31–M37 受影响回归 162 passed；API/配置 19 passed；compileall 与 diff check 通过；follow-up Eval 50/50 required passed。
- 已知风险：checkpoint 仍为进程内且 tombstone 不清扫；follow-up action 只覆盖三个闭集模板；生产认证仍未建设；external profile 复用刻意禁止；Starlette/httpx 既有弃用 warning 尚在。
- 待完成：检查后台全仓 pytest 终态；若通过，再完成注释/文件全量核对、更新 plan/state/runbook/RAG state/Phase 4 changelog，并最终回读 notes 与 diff。

### 后台任务（已完成并检查）

- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q -p no:cacheprovider --basetemp=.agent_work\temp\m37-full-basetemp`
- wrapper：`.agent_work/temp/run_m37_full_pytest.ps1`
- PID：`37824`
- stdout：`.agent_work/temp/m37-full-pytest.out`
- stderr：`.agent_work/temp/m37-full-pytest.err`
- 退出码：`.agent_work/temp/m37-full-pytest.exit`
- 完成标记：`.agent_work/temp/m37-full-pytest.done`
- 完成时间：`2026-08-17T16:32:08.2416562+08:00`；退出码 `0`。
- 最终结论：`427 passed, 3 skipped, 1 warning in 509.36s`；stderr 为空。3 个 skip 为既有条件型远程/Milvus 用例，warning 为既有 Starlette TestClient/httpx 弃用提示，均不阻塞 M37。

## 模块名称与改动文件清单

- 模块：M37 受控有限追问与 Document Evidence 窄复用。
- 起始 commit：用户未指定；以开工时记录、`git status --short`、未暂存/暂存/未跟踪清单交叉归并。暂存区为空。
- Harness/RAG：`engine/harness/{__init__,contracts,graph,adapters,thread,turn}.py`、`engine/rag/answer_flow.py`、`engine/trace/recorder.py`。
- API/demo：`app/api/query.py`、`app/core/exceptions.py`、`app/schemas/agent.py`、`demo/streamlit_app.py`。
- Eval/tests：`eval/harness_followup_contracts.py`、`tests/test_m37_{api_trace,followup_eval,followup_turn,rag_rehydration}.py`。
- 文档：`AGENTS.md`、`docs/notes/m37-{plan,notes}.md`、`docs/state/{AI_CONTEXT,runbook,rag-current-state}.md`、`docs/state/change-history/phase4.md`。
- 排除：`tests/test_m36_turn.py` 只有开工前已有的末尾空行差异，不属于 M37；`.agent_work/temp/m37-full-pytest.*` 与 wrapper 只是一轮验证中间证据，不是交付文件。

## 阶段 1 注释小结

- 完整复核 17 个 M37 Python 文件，共扫描到 243 个类/函数/方法；其中 28 个无 docstring 项均为简单 `__init__`、测试 fixture/局部 fake 或既有简单闭包，按 skill 豁免，非豁免缺失为 0。
- 本次补写/深化 14 处注释或 docstring：重点解释 closed-world Eval artifact、真实 sequence/并发 claim、业务 rehydrate 前重新授权、Knowledge Tool 重新取证原因、Router 隔离旧 Evidence，以及 Pydantic v2 422 编码。
- 更新了 Harness、adapter、AnswerFlow、Trace 和 `AGENTS.md` 中过时的 M35/M36 单轮描述；复杂安全分支仍保留步骤注释与 ★ 边界，没有用注释重复逐行代码。

## 阶段 2 验证快照

- 兼容/聚焦：M36/M33/M35 首轮 `32 passed`；M37 专项最终 `14 passed, 1 warning`；M37 + M36/M35/M33 `47 passed, 1 warning`。
- 受影响回归：M31–M37 `162 passed, 1 warning in 39.19s`；API/配置 `19 passed, 1 warning in 92.14s`。
- M37 Eval：10 sequences / 22 turn evidence / 50 required assertions，`50 passed`；artifact identity `1185edf04c42439dedf5e3dc051be13060a462bd05e79c48d3b975fdce634b25`。
- 静态与全仓：`compileall -q app engine eval tests demo`、`git diff --check` 通过；后台全仓 pytest 退出码 `0`，`427 passed, 3 skipped, 1 warning in 509.36s`。
- 已修复的中途失败：API 半截 follow-up 的 Pydantic v2 `ValueError` 无法 JSON 序列化，修复后稳定返回 422；Eval completed validator 的 ACL deny 断言从“必须伪造新 ref”修正为“成功才必须新 run ref，拒绝必须零旧 id 注入”。两者均已回归，不阻塞。
- 未运行：真实 LLM、远程 embedding、Milvus、LangFuse Cloud、M27 真实 Text2SQL Eval、M34 external 大评测；因此不能从本轮推出这些外部链路的质量或性能结论。

## 参考资料

- 按 `docs/phase4-reference.md` 定点复核 ARAG `graph_state.py`、`edges.py`、`graph.py`、`nodes.py`。
- 借鉴：任务/澄清分离、显式 Tool/iteration budget、记录已经执行的 context/action 作为停止依据。
- 不照搬：`MessagesState` 全历史、LLM rewrite/summary、ToolMessage 正文跨轮累计、开放 Tool loop、fallback answer、`InMemorySaver + interrupt`。ARAG 没有 DataPilot 的 revision/ACL/freshness 合同，Evidence validity 仍由本项目现有 authority 与 Gate 决定。

## Handoff

### 1. 已完成且可依赖

- 旧请求默认不建 thread；显式 `enable_bounded_follow_up=true` 的成功 SQL/RAG turn 才签发一次 follow-up-ready spec。
- SQL 追问永远重新执行；external RAG 永远重新检索；业务 release 只有同 requirement 解释动作可按当前 active identity 重新加载、重新授权并签发新 run Evidence/ledger/citation。
- requirement/identity 变化只允许同 RAG Tool 重检索一次；ACL/用途拒绝在零 retrieval 时停止。accepted follow-up 恰好一次 Graph、至多一个深 Tool，budget/owner/version/TTL/concurrency 失败均在 Graph 前结束。
- `phase4-harness-followup-v1`、HTTP/Trace 投影和四个专项测试可作为下一模块的回归入口。

### 2. 未完成与风险

- 仍不是自由对话或完整 P4：没有第二次追问、跨 route/Hybrid、长历史 compact、Tool retry、持久 checkpoint、生产认证或多 worker 共享。
- external profile 没有窄复用；业务 rehydrate 只证明当前 22-entry source-backed release。全仓 deterministic 通过不等于真实 LLM/大语料质量通过。
- 进程内 tombstone 仍不清扫；开放问法仍受 deterministic Router 与三个服务端 action 限制。

### 3. 必须延续的边界与决策门

- “窄 B”是正式合同，不是以后可能忘记升级的临时 A：必须持续保留业务同 Evidence 重水化、变化后重检索、SQL/external 强制重取证三条分支。
- 若要扩到 external 复用、第二次追问、跨 route、多 Tool、完整历史、持久化或生产认证，必须重新给出依据/选项/影响并由用户确认；不得在修 bug 时顺手扩大。
- raw thread id、旧 answer/rows/body/citation 和客户端自报 requirement equivalence 继续禁止成为授权或新答案事实。

### 4. 下一模块入口与必读指针

- 下一次规划先从 `docs/phase4-roadmap.md` 的 P4 剩余能力与本文件限制判断：是继续扩展受控 Context Builder/第二类 follow-up，还是进入 P4 的其他未闭环能力；不能把 M37 宣称为完成整个 P4。
- 代码入口：`engine/harness/thread.py` 的 follow-up spec/lifecycle、`engine/harness/turn.py` 的 claim/单 Graph、`engine/rag/answer_flow.py::_obtain_evidence`；证据入口：四个 `tests/test_m37_*.py` 与 `eval/harness_followup_contracts.py`。

## State impact

- **已更新**：`docs/state/runbook.md`（M37 API/turn/thread/Trace 接线）、`docs/state/rag-current-state.md`（Evidence validity 与新 contract）、`docs/state/AI_CONTEXT.md`（当前模块、默认 seam、验证与路线）、`docs/state/change-history/phase4.md`（完整模块档案）。
- **已检查、无需修改**：`docs/state/eval-baselines.md`，本轮只有确定性 contract family，没有登记新真实长期基线或改评分分母；`docs/state/database-current-state.md`，未改数据库、seed、指标、SQL snapshot 或 RBAC 固定事实。
- **未命中**：`docs/state/schema-retrieval-milvus-embedding.md`，未改 embedding/vector/collection 或 Schema Retrieval 默认。

## 技术档案 checklist

- [x] 最终文件范围已与 Git 状态、开工记录、暂存和未跟踪清单核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] 已读取 `CHANGELOG_INDEX.md` 并按索引更新 Phase 4 历史。
- [x] `AI_CONTEXT.md` 已替换 M36 的失效当前状态并保留必要边界。
- [x] 命中的 runbook/RAG state 已更新；Eval/数据库 state 已检查并记录无需修改。
- [x] 新结论已与代码、测试、Eval、默认配置和历史条目核对，无第二份详细权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md`、runbook、RAG state 已完整回读。
- [x] 最终 `git diff --check` 与本轮新增/修改文档路径检查通过。

最终硬门复核：注释与档案更新后再次运行 `compileall`、四个 M37 测试文件和 `git diff --check`，结果分别为退出码 `0`、`14 passed, 1 warning in 1.20s`、退出码 `0`；14 个关键文档/代码路径全部存在。最终 Git 清单与上方范围一致，唯一排除项仍是用户已有的 `tests/test_m36_turn.py` 末尾空行差异。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有概览，再有至少 3 条一级编号。
- [x] 每个编号点说明原问题/影响、概念、解决方式、重要取舍、证据与未证明边界。
- [x] 新概念已用新手能理解的语言解释，没有为凑数编造概念。
- [x] “代码阅读路线”按真实调用/数据流组织，并解释各层为什么这样分工。
- [x] 有“设计要点”，且最后一句按 skill 要求以“喵。”收尾。
- [x] “面试怎么讲”包含可直接复述的目标、方案、验证和边界。
- [x] 追问基于真实实现与证据，覆盖设计取舍、失败场景和能力边界，没有送分题。
- [x] “验证与下一步”只引用本 notes 的真实验证快照。
- [x] 复制命令安全、可重复，并标明前置条件与预期结果。
- [x] 各小节已用加粗关键词提供扫读锚点。
- [x] 已完整回读 M37 新章节，并与 notes/技术档案逐项核对。
- [x] 本轮除 `docs/dev-log.md` 与本 notes 外未修改其它文件。
- [x] `git diff --check` 已通过。

执行结果：完整回读后补正了两处中英文黏连；逐项核对确认章节包含 4 个“这次做了什么”一级工作点、6 步代码阅读路线、5 个真实面试追问、真实验证边界和 Swagger 两次请求体验。本轮未运行模块测试/Eval，也未修改 `AI_CONTEXT.md`、`CHANGELOG_INDEX.md`、`change-history/`、代码或其它文档。
