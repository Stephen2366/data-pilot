# M38 保守 Hybrid 双 Evidence 编排 — 实施素材

> 状态：技术收工完成，等待人工检查 / `accept-module`（2026-08-17）
>
> 范围以 [m38-plan.md](m38-plan.md) 为准：P5 的保守 Hybrid 纵向基线；正式本地确定性 Synthesizer，不新增 Hybrid 数据出站。

## Implementation checklist

- [x] 核对 M36/M37 的 P4 关闭口径、工作树和 Hybrid 现状；冻结实现真值表。
- [x] 扩展内部 `hybrid` route、薄 `HybridPlan` 与 fail-closed Router；保持 SQL/RAG/none 兼容。
- [x] 建立 Harness 私有的双 branch typed Evidence seam；Hybrid RAG 仅执行 retrieval + Gate，不生成 RAG 子答案。
- [x] 在既有 Harness 图中实现两支各至多一次、总计至多两次的预算、join 和唯一 controller。
- [x] 实现正式本地确定性 Hybrid Synthesizer、claim/Evidence validator、conflict 与安全 partial 合同。
- [x] 将同一运行事实投影到 API、Trace（及必要的 demo），且不泄露正文、完整 rows 或 denied branch 侧信道。
- [x] 新建独立 Hybrid sequence Eval 及聚焦/回归测试，覆盖 complete、partial、ACL、SQL safety、conflict、synth failure、预算和篡改。
- [x] 完成注释审查、验证、技术档案与 `finish-module` 收工门禁。

## 开工快照与关键决策

- 用户已确认 G-M38-1 方案 A：本地确定性结构化 Synthesizer 是正式默认和长期 fallback，不是临时替代；禁止新增 Hybrid 数据出站、远程 LLM/embedding、P6 实验或 Hybrid follow-up。
- 现有 M35–M37 Harness 对 Hybrid 保守停止；M38 必须在相同 Harness / `run_turn` / Trace seam 内加入分支与 controller，不能建立 API 旁路。
- P4 关闭口径已由 M36 + M37 共同满足；M38 承接 P5，不为第二次追问、持久 checkpoint 或长历史 compact 扩展范围。
- 参考项目定点复核：DataAgent 借鉴显式计划→执行→汇合状态迁移，不复制其大型多节点平台；GustoBot 仅作为“统一汇合但不能自动 fallback / 松散 source 拼接”的反例，不复用其降级策略。

## 过程记录

- 2026-08-17：已完整阅读 `AGENTS.md`、M38 plan、`AI_CONTEXT.md` 及其命中的 runbook、数据库、RAG、Eval、历史索引/Phase 4 记录；收工将依照 `finish-module` skill 执行注释、验证、notes 与 state/changelog 门禁。
- 2026-08-17：内部 `ToolObservation` 只新增进程内 `EvidenceLedger/raw_evidence`，API/Trace 投影不读取它们。SQL adapter 单点构造已 Guard 的 SQL Evidence；RAG 新增 `prepare_for_hybrid()`，复用 Knowledge Tool、active release 与 Shared Gate，但在 Composer 前停止，避免两个自然语言子答案被拼接。
- 2026-08-17：Graph 固定为 `route → hybrid_sql_tool → hybrid_rag_tool → controller`；两支均按 M38 required 执行各一次。SQL Guard 拦截全局停止；RAG ACL/技术失败只允许 SQL 独立 partial，且公开 branch summary 不含 RAG EvidenceRef 或真实拒绝 reason。
- 2026-08-17：方案 A 实现为正式 `DeterministicHybridSynthesizer`。跨来源 claim 必须同时绑定 SQL/Document Evidence；conflict 固定停止；adapter invalid/unavailable 时不重跑 Tool，只由独立 fallback 生成单来源 partial。
- 2026-08-17：已新增 `phase4-harness-hybrid-v1` 独立 artifact family，覆盖 complete、SQL/RAG partial、SQL safety 与 conflict；artifact validator 拒绝漏断言和重复 execution。聚焦验证已通过：Harness/Eval 9 passed；真实 API/Trace 1 passed（FastAPI TestClient 有既有 httpx deprecation warning，不影响模块合同）。

## 后台验证 checkpoint（启动前）

- 已完成改动：M38 contracts/router、私有 typed Evidence seam、Gate-only RAG branch、双分支 Graph/controller、确定性 Synthesizer/fallback、API/Trace 投影和独立 Hybrid Eval/test。
- 已完成验证：`tests/test_m38_hybrid_harness.py tests/test_m38_hybrid_eval.py tests/test_m38_hybrid_api_trace.py` 为 `9 passed, 1 warning`；`tests/test_m36_turn.py tests/test_m37_followup_turn.py tests/test_m37_followup_eval.py` 为 `12 passed`；M31–M33 RAG 组在前台超时前已显示 35 项通过，M35 API 的第三项已单独 `1 passed`。
- 已知风险/待完成：需获得全仓 deterministic pytest 的可靠终态；随后执行静态检查、注释审查和 `finish-module` 的 state/changelog 收工门禁。Streamlit 是 plan 的建议项，当前未改动，待 full regression 后审查是否需要最小兼容展示。
- 后台完成：PID `6088` 的全仓 deterministic pytest 退出码为 `0`；`439` 项收集结果为 **436 passed, 3 skipped, 1 warning in 599.87s**。warning 是 FastAPI/Starlette TestClient 依赖 `httpx` 的既有 deprecation warning，不涉及 Hybrid 合同。命令、stdout、stderr、退出码和 done 标记仍在 `.agent_work/temp/m38-full-pytest.*`，可复核。

## 模块名称与改动文件清单

- **模块**：M38 保守 Hybrid 双 Evidence 编排（P5）。起始 commit 未由用户指定；本次根据开工后的 `git status --short`、`git diff --name-only` 与未跟踪文件归并，暂存区为空。
- **实现**：`engine/harness/{contracts,router,graph,adapters,hybrid}.py`、`engine/rag/answer_flow.py`、`app/{api/query,schemas/agent}.py`、`engine/trace/recorder.py`。
- **Eval / tests**：`eval/{harness_contracts,harness_hybrid_contracts}.py`、`tests/test_m35_harness.py`、`tests/test_m38_hybrid_{harness,eval,api_trace}.py`。
- **技术档案**：`docs/notes/m38-{plan,notes}.md`、`docs/state/{AI_CONTEXT,runbook,rag-current-state,eval-baselines}.md`、`docs/state/change-history/phase4.md`。

## 关键决策与取舍

- **用户最终选择**：G-M38-1 方案 A。确定性 `HybridSynthesizer` 是正式 default/fallback；不使用“先写一个临时本地版本、以后换 LLM”的方案，也不改 outbound policy。这样先证明双 Evidence 控制合同，代价是开放问法覆盖窄。
- **唯一控制权**：复用 M35–M37 Harness，以显式 `hybrid_sql_tool → hybrid_rag_tool → controller` 完成，不另建 endpoint 或 Graph。SQL/RAG 单路仍各至多一次；Hybrid 也只允许各一次，避免重试/隐藏 fallback 改写预算事实。
- **RAG branch 的边界**：新增 Gate-only seam，而不是把 `RAGAnswerFlow.run()` 的自然语言子答案交给 Synthesizer。这样完整 Document Evidence 仍受现有 Gate/ACL/revision 约束，跨来源结论由唯一 controller/validator 形成。
- **required 与失败策略**：两支都 required 才能 complete；一支失败只允许另一支事先允许、独立成立的 partial。SQL Guard 全局停止；Document ACL 拒绝不泄露 ref/title/reason；conflict 不选边；Synthesizer 失败不重跑深 Tool。

## 阶段 1 注释小结

- 完整审查 10 个本模块实现文件和 5 个新/修改的 Eval/测试文件；新增/大改的类、函数均有中文 docstring 或紧邻职责注释。
- 新增并深化的概念包括：薄 `HybridPlan`、私有 typed Evidence seam、Gate-only RAG branch、唯一 Hybrid controller、cross-source binding、Synthesizer fallback、Trace 的非披露投影。
- 重点补足了“为什么不拼两个子答案”“为什么 SQL Guard 是全局 stop”“为什么 fallback 不重跑 Tool”的注释；未发现仍需补写的非豁免注释。Streamlit 是 plan 的建议项，本模块不修改其布局，避免在没有新增交互验收价值时扩大范围。

## 阶段 2 验证快照

- `python -m pytest tests/test_m38_hybrid_harness.py tests/test_m38_hybrid_eval.py tests/test_m38_hybrid_api_trace.py -p no:cacheprovider --basetemp=.agent_work/temp/m38-focus-final`：**9 passed, 1 warning in 12.04s**；覆盖 complete、SQL/RAG partial、ACL 非披露、SQL Guard、conflict、Synthesizer failure、artifact 篡改与真实 API/Trace。warning 为既有 TestClient/httpx deprecation。
- `python -m pytest tests/test_m36_turn.py tests/test_m37_followup_turn.py tests/test_m37_followup_eval.py -p no:cacheprovider --basetemp=.agent_work/temp/m38-turn-regression`：**12 passed in 0.85s**；证明 clarification/follow-up 没有被 Hybrid 扩张。
- `python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m38-full-pytest-base`：后台可靠结束，**436 passed, 3 skipped, 1 warning in 599.87s**，退出码 0。3 skip 为既有 Milvus/远端 embedding 条件跳过；warning 不影响 M38。
- `python -m compileall app engine eval tests`：通过；`git diff --check`：通过。未运行真实 Hybrid LLM、远程 embedding/Milvus、LangFuse Cloud、M34 external 或 M27 真实 Eval，符合方案 A / runbook 边界。

## 参考资料

- **Alibaba DataAgent**：定点阅读 `DataAgentConfiguration.java::nl2sqlGraph` 的 planner / executor / execution-report conditional edges；借鉴显式状态迁移和 dispatcher 边界，不复制大型平台、repair loop、Python/report/human review/checkpoint。
- **GustoBot**：定点阅读 multi-tool workflow 的 `create_kb_multi_tool_workflow`、`local_search`、`finalize` 与 source collection；借鉴分开保存结果、末端统一汇合，不照搬自动 fallback、截断 Prompt 拼接或末尾 `sources`。

## Handoff

- **已完成且可依赖**：`hybrid` route、两类 canonical `HybridPlan`、同一 Harness 双分支预算、私有 SQL/Document typed Evidence、正式确定性 Synthesizer、双引用 validator、safe partial/conflict/synth fallback、API/Trace branch 投影、`phase4-harness-hybrid-v1`。
- **未完成与风险**：只覆盖两类 closed-world operator；没有开放 Hybrid、远程 Synthesizer、Hybrid follow-up、optional branch、真实质量 benchmark 或生产认证。P5 的 deterministic contract 不能外推为自然语言综合能力或真实 RAG 质量提升。
- **必须延续的边界与决策门**：方案 A 继续默认；B/C 的重开必须满足 `AI_CONTEXT` 防遗忘账本中的稳定失败、精确 outbound 许可、真实运行授权与 held-out/可比预算条件。不得将完整 Evidence 写入 API/Trace，不得把两份子答案拼接，不能让缺 required branch 的结果变 complete。
- **下一模块入口与必读指针**：按 roadmap 先做 P6 go/no-go。先读 `docs/state/AI_CONTEXT.md` 的账本、M34 RAG state/Eval baseline、本文和 `engine/harness/{contracts,graph,hybrid}.py`、`eval/harness_hybrid_contracts.py`；以 M34 已知 lexical/context packing/support 失败簇制定单变量候选或有证据的 no-go，而不是顺手放宽 M38 Router 或接远程。

## State impact 与 finish-module 技术档案交付清单

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] 已读取 `CHANGELOG_INDEX.md`，并按索引写入完整模块记录。
- [x] `AI_CONTEXT.md` 已更新并清理失效、重复或仅具历史价值的内容。
- [x] 所有命中的专项 state 均已完整检查，并已更新或记录“无需修改”的理由。
- [x] 新结论与历史条目、代码、测试、Eval、默认配置和各 state 之间不存在冲突或重复权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md` 和所有修改过的专项 state 已完整回读。
- [x] `git diff --check` 及本轮涉及的文档链接检查已通过，结果已写回 notes。

### 收工回读结果

- 已回读 M38 changelog 新章节、更新后的 `AI_CONTEXT.md`、runbook、RAG state 与 Eval baseline；它们均指向同一事实：P5 完成保守 deterministic Hybrid，不新增 outbound，也不宣称开放 Hybrid/P6 已完成。
- 文档/代码路径存在性检查通过；最终 `git diff --check` 通过。`finish-module` 技术档案交付清单全部完成。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号。
- [x] 每个编号点交代原问题、概念、解决、取舍、验证与未证明边界。
- [x] 新概念已用通俗语言解释。
- [x] “代码阅读路线”按真实调用/数据流组织，并解释职责与原因。
- [x] 有“设计要点”。
- [x] “面试怎么讲”有可复述叙述和真实追问。
- [x] “验证与下一步”只引用真实验证快照。
- [x] 复制命令安全、可重复，并标明必要前置条件。
- [x] 模块记录各小节使用了服务于扫读的加粗关键词。

### finish-docs 回读结果

- 已完整回读 `docs/dev-log.md` 的 M38 新章节；基于本 notes、`AI_CONTEXT.md`、CHANGELOG_INDEX 路由的 Phase 4 档案与 Git 范围写作，没有编造未记录的过程或验证。
- finish-docs 期间仅修改 `docs/dev-log.md` 与本 notes；未修改代码、`AI_CONTEXT.md`、CHANGELOG_INDEX 或 change-history。
- `git diff --check` 通过；dev-log 交付门全部完成。为满足交付门，写作时补齐了可运行体验、四条有压力的面试追问，以及“确定性控制合同不等于开放质量”的边界说明。

### State impact

- **已更新**：`AI_CONTEXT.md`（当前模块/Harness/P5 状态/验证与路线）；`runbook.md`（Hybrid API/Trace 接线）；`rag-current-state.md`（Gate-only branch 与 contract）；`eval-baselines.md`（独立 deterministic Hybrid artifact 的非混算边界）；`change-history/phase4.md`（完整 M38 技术档案）。
- **已检查、无需修改**：`database-current-state.md`（未改数据库、seed、指标或 oracle）；`schema-retrieval-milvus-embedding.md`（未改向量后端、embedding、collection）；`AGENTS.md`（本轮不改全局约定）。
- **未命中**：其余专项 state。
