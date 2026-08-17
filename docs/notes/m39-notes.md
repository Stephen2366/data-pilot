# M39 P6 RAG Subgraph 入场证据审计 — 实施素材

> 状态：技术收工完成，待人工检查 / `accept-module`（2026-08-17）
>
> 范围以 [m39-plan.md](m39-plan.md) 为准：只读 M34 证据审计与严格 P6 no-go 判断；不实现 RAG Subgraph、不运行 provider、不改变默认路径。

## Implementation checklist

- [x] 核对 M34 artifact、60/120 split、external runtime 与现有 RAG/Harness 合同，冻结模块输入和只读边界。
- [x] 建立 C1 的 closed-world readiness 输入校验与零执行证明。
- [x] 建立 C2 的 dev-only Evidence stage / failure taxonomy，并拒绝 held-out 逐题消费。
- [x] 建立 C3 的 P6 入场真值表、no-go 决策报告与重开条件。
- [x] 添加专项合同测试和受影响 RAG/Harness 回归；不调用真实 provider。
- [x] 完成注释审查、验证、notes 素材、state/changelog 与 `finish-module` 收工门禁。

## 开工快照与关键决策

- 用户于 2026-08-17 确认 G-M39-1 方案 A：严格证据优先。M39 审计任一 P6 入场条件缺失时记录 no-go，保持 `enterprise-lexical` 默认；本轮不实现 Subgraph。
- M34 已登记五份 completed artifact；回答层的 complete/citation 覆盖、Composer 拒绝与 provider unavailable 不能直接归因为“需要多轮检索”。
- held-out 只能作冻结 identity 与既有 aggregate baseline 核验；不可读取逐题 execution 来选择恢复动作、Prompt 或参数。
- 本模块没有新增 receiver / node purpose / data class 的 outbound 授权；不得运行新的真实 LLM、embedding、Milvus、LangFuse Cloud 或 M34 大评测。

## 过程记录

- 2026-08-17：已读取 `AGENTS.md`、M39 plan、`AI_CONTEXT.md`，并按必读规则读取 runbook、RAG/Eval state、CHANGELOG_INDEX 和 Phase 4 历史入口；`finish-module` 将在代码与验证完成后执行。
- 2026-08-17：新增 `eval/subgraph_readiness.py`、`scripts/audit_m39_p6_readiness.py` 与专项测试。输入必须同时命中六份冻结 M34 文件的 SHA-256、split/profile/dataset/question-set identity，并核对 lexical / semantic 各自 dev 与 held-out 的 adapter+recipe 运行身份、AnswerFlow 的 Composer 身份；任一项不闭合即抛出 `ReadinessAuditError`，不把不可比输入写成 no-go。
- 2026-08-17：初次直接执行 CLI 时发现 `scripts/` 直接执行不会自动把仓库根加入 `sys.path`，导致 `ModuleNotFoundError: eval`。已按现有 smoke 脚本惯例添加纯导入路径 shim；它不读写 RAG runtime，也不改变输入。
- 2026-08-17：真实 M34 artifact 只读审计通过，最终 audit identity 为 `324ec7f8f4c7d4edf81bc73dc638905000d08d22861b079d26ebbaabc4b726c6`，零 provider 调用。dev 主层计数为 retrieval `11`、context/packing `13`、Composer `10`、provider unavailable `2`、not classifiable `24`。四项 P6 条件中“可复现非 provider cohort”与“dev/held-out 隔离”满足；“Observation 驱动的新 Evidence 动作”和“可比额外预算”没有既有证据，故严格结论为 `no_go`。
- 2026-08-17：默认 pytest 临时目录 `.agent_work/temp/pytest-tmp` 被 Windows 锁占用，首次 M31–M38 回归显示 `155 passed` 后有 `48` 个 setup 清理错误；未修改项目默认配置。改用独立 `.agent_work/temp/m39-focused-regression-2` 后，相关 M31–M38 回归 `203 passed, 1 warning in 58.09s`。专项 M39 tests 当前为 `5 passed in 0.43s`。

## 验证 checkpoint 与最终结果

- 关键决策：保持方案 A 的严格 no-go；不实现 Subgraph，不改 `enterprise-lexical` 默认。
- 改动范围：仅新增 M39 审计模块、只读 CLI、专项测试、JSON/Markdown 审计报告与本 notes；未触及 Knowledge Tool、AnswerFlow、Harness、Hybrid、ACL、profile 或历史 M34 artifact。
- 已完成验证：真实只读 CLI、M39 专项五项测试、M31–M38 相关回归 203 项；无 provider 调用。
- 已知风险：完整 pytest 仍需使用独立 `--basetemp`，避免历史 `.agent_work/temp/pytest-tmp` Windows 锁。
- 最终结果：后台任务已完成，退出码 `0`；完整 deterministic pytest `441 passed, 3 skipped, 1 warning in 517.57s`。三个 skip 是既有 Milvus/远端 embedding 条件用例；唯一 warning 是既有 Starlette `TestClient` / `httpx` 弃用提示，均不阻塞 M39。

### 后台任务：已完成并核对

- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m39-full-pytest-base`
- runner PID：`19060`（PowerShell 7 后台进程）
- 日志：`.agent_work/temp/m39-full-pytest.out` 与 `.agent_work/temp/m39-full-pytest.err`
- 退出码：`.agent_work/temp/m39-full-pytest.exitcode`
- 完成标记：`.agent_work/temp/m39-full-pytest.done`
- 检查结果：已读取 `.agent_work/temp/m39-full-pytest.done`、退出码和 stdout/stderr 尾部，确认完成标记存在、退出码为 `0`，stdout 终态为 `441 passed, 3 skipped, 1 warning in 517.57s`。

## 注释审查

- 检查范围：完整阅读 3 个新增代码文件（`eval/subgraph_readiness.py`、`scripts/audit_m39_p6_readiness.py`、`tests/test_m39_subgraph_readiness.py`），共 26 个类/函数/测试入口；数据类字段和简单 helper 不单独重复注释。
- 结论：新增模块、数据类、所有非豁免函数和测试场景均有中文 docstring 或紧邻的说明；重点复核了 SHA-256 closed-world、ledger 阶段累积、Composer/provider 优先归因、held-out 隔离和 CLI `sys.path` shim。复杂分层已用步骤注释与 ★ 标记解释“不把失败硬凑成 Subgraph 依据”的原因。
- 补写：0 处。现有注释已覆盖新概念、关键取舍与阅读分段；无过时注释或仍缺失项。

## 模块名称与改动文件清单

**M39 P6 RAG Subgraph 入场证据审计**。用户未提供模块起始 commit；当前 `HEAD` 为 `5f80c8b M38 保守 Hybrid 双 Evidence 编排`。本模块以收工时 `git status --short`、`git diff --name-only` 与 `git diff --name-only --cached` 归并：暂存区为空；新增 M39 plan/notes、审计实现/CLI/测试、JSON/Markdown 报告；修改 `AI_CONTEXT`、Phase 4 changelog、RAG/Eval state 和 runbook。没有发现可归属 M39 之外的用户改动。

- 新增：`docs/notes/m39-{plan,notes}.md`、`eval/subgraph_readiness.py`、`scripts/audit_m39_p6_readiness.py`、`tests/test_m39_subgraph_readiness.py`、`eval/reports/m39-p6-readiness.{json,md}`。
- 修改：`docs/state/{AI_CONTEXT,rag-current-state,eval-baselines,runbook}.md`、`docs/state/change-history/phase4.md`。

## 关键决策与取舍

- **方案与用户选择**：G-M39-1 的方案 A（严格证据优先）由用户在 2026-08-17 确认。做法是复盘冻结 M34 证据，任一 P6 入场条件缺失即 `no_go`；方案 B 只会在四项条件全部满足后，为独立 M40 打开实验门。A 的影响是暂不展示 Agentic RAG，换来不因“有失败”而扩大循环、延迟、出站和调试面；主要风险是未来需求出现时需要重新准备受控 dev 证据。推荐 A，用户最终选择 A。
- **失败归因**：候选召回、固定 context/packing、Composer support 和 provider unavailable 必须拆开；`complete` 或低 citation coverage 不可直接推出多步检索有收益。缺阶段事实宁可 `not_classifiable`，不从 gold/最终文本猜测运行时没有看到的 Evidence。
- **分集与默认保护**：只分类 60 dev；120 held-out 仅验证身份/闭合，不读取逐题失败来选动作、Prompt 或参数。无 Observation→允许动作→新 Evidence 的实证，且无可比额外预算，故结果严格 `no_go`；保持 `enterprise-lexical` 默认，不实现或预置 Subgraph。

## 阶段 2 验证快照

- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q -p no:cacheprovider tests\test_m39_subgraph_readiness.py`：`5 passed in 0.43s`；覆盖 dev-only taxonomy、provider 不误归 retrieval、split/runtime/hash 不闭合即失败关闭。
- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\audit_m39_p6_readiness.py ...`：真实六份 M34 artifact 的只读审计成功，`recommendation=no_go`，audit identity `324ec7f8f4c7d4edf81bc73dc638905000d08d22861b079d26ebbaabc4b726c6`，无 provider 调用；产物为 `eval/reports/m39-p6-readiness.{json,md}`。
- M31–M38 受影响确定性回归：首次使用项目默认 `pytest-tmp` 时，已有 `155 passed` 后被 Windows 临时目录锁导致 48 个 setup 清理错误；未改默认配置，改用独立 `--basetemp=.agent_work/temp/m39-focused-regression-2` 后为 `203 passed, 1 warning in 58.09s`。warning 是既有 Starlette TestClient/httpx 弃用提示，不影响模块。
- `python -m compileall -q eval\subgraph_readiness.py scripts\audit_m39_p6_readiness.py tests\test_m39_subgraph_readiness.py`：退出 `0`。
- 后台完整 pytest：退出 `0`，`441 passed, 3 skipped, 1 warning in 517.57s`；三个 skip 是既有 Milvus/远端 embedding 条件项，warning 同上，不阻塞。
- `git diff --check`：退出 `0`。Git 提示五份改写 state 文件未来会由 LF 转为 CRLF，是工作树换行提示而非 whitespace error。

## 参考资料

- `docs/phase4-reference.md` 与 agentic-rag-for-dummies 的 `graph.py::create_agent_graph`、`graph_state.py::AgentState`、`nodes.py` 的 context/stop 逻辑、`tools.py` 的 child search/parent retrieval。
- 借鉴：真正有界子图必须有状态、Observation、条件停止、已执行动作与预算；搜索命中和上下文扩展是不同动作。
- 不照搬：强制首搜、LLM rewrite/summary、字符串 Observation、全历史、InMemorySaver、默认 parent 扩展、fallback answer、开放 loop 或其向量库/参数；这些都不能替代 DataPilot 的 Tool/Evidence/ACL/outbound/held-out 合同。

## Handoff

- **已完成且可依赖**：`audit_paths()` 对六份指定 M34 JSON 执行 hash/identity/split/runtime closed-world 检查；`build_p6_readiness_audit()` 只对 dev 输出互斥主层；`render_readiness_markdown()` 只输出安全聚合。报告的 P6 结论为 strict `no_go`，保持 external lexical 默认。
- **未完成与风险**：没有实现、测试或声称 RAG Subgraph、query rewrite、parent/child、rerank、hybrid retrieval、context 参数调优、Composer 合同变更、LLM Judge、远程节点或默认切换；`not_classifiable` 不可被解释成任一种缺口。M34 的 complete 仍不等于答案正确。
- **必须延续的边界与决策门**：用户已确认方案 A。Subgraph 重开前，未污染 dev 必须证明一种由首次 Observation 选择的允许动作确实新增有效 Evidence，并冻结 held-out decision protocol、父子/额外预算和可比成本；满足后仍须用户确认并另立 M40。单变量 Pipeline 候选也不能借 P6 no-go 自动开工。
- **下一模块入口与必读指针**：先读 `docs/phase4-roadmap.md` 的 P7、`docs/notes/m39-{plan,notes}.md`、`eval/reports/m39-p6-readiness.md`、`docs/state/{AI_CONTEXT,rag-current-state,eval-baselines}.md` 与 `tests/test_m39_subgraph_readiness.py`；据路线另行制定 P7 plan，不提前冻结实现。

## 技术档案交付清单（已完成）

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] 已读取 `CHANGELOG_INDEX.md`，并按索引写入完整模块记录。
- [x] `AI_CONTEXT.md` 已更新并清理失效、重复或仅具历史价值的内容。
- [x] 所有命中的专项 state 均已完整检查，并已更新或记录“无需修改”的理由。
- [x] 新结论与历史条目、代码、测试、Eval、默认配置和各 state 之间不存在冲突或重复权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md` 和所有修改过的专项 state 已完整回读。
- [x] `git diff --check` 及本轮涉及的文档链接检查已通过，结果已写回 notes。

### State impact（最终）

- **已更新**：`AI_CONTEXT.md`（当前模块、P6 strict no-go、P0 能力账本和最新全仓验证）；`rag-current-state.md`（M39 分层、默认保护和 Subgraph 重开门）；`eval-baselines.md`（M39 只读 audit 不是新质量基线）；`runbook.md`（可复现的只读 audit 命令）；`change-history/phase4.md`（完整 M39 模块档案）。
- **已检查、无需修改**：`database-current-state.md`，本模块未改数据库、seed、ORM、Alembic、指标或 SQL 事实；`schema-retrieval-milvus-embedding.md`，未运行或改动 Schema Retrieval/Milvus/embedding。
- **回读与一致性**：已完整回读 `AI_CONTEXT.md`、`rag-current-state.md`、`eval-baselines.md`、`runbook.md` 及 Phase 4 changelog 新章节；它们均表述为“不新增质量基线、P6 no-go、lexical 默认不变”，与代码、报告和验证一致。新增路径均经 `Test-Path` 存在性检查。

## finish-docs 执行清单（已完成）

- [x] 已完整读取本 notes，并确认最近一次 finish-module 技术档案交付清单全部为 `[x]`。
- [x] dev-log M39 章节含简述与大白话说明，准确描述问题、方案、价值和边界。
- [x] “这次做了什么”含概览与至少 3 条一级编号，逐项覆盖问题、机制、取舍、验证和未证明边界。
- [x] 新概念、真实代码阅读路线、设计要点、可复述的面试讲法和有压力的追问均已完成。
- [x] 验证与下一步只引用 notes 的真实快照，命令可复制且写明 M34 artifact 前置条件。
- [x] 已完整回读 dev-log 新章节，核对本轮只改 dev-log/notes，且 `git diff --check` 通过。

- **回读结果**：M39 dev-log 已逐节核对并未补写缺项；本轮 finish-docs 只新增 `docs/dev-log.md` 的 M39 学习复盘和本 checklist，没有改动技术档案或代码。`git diff --check` 退出 `0`；Git 的 LF→CRLF 提示是工作树换行提示，非 whitespace error。
