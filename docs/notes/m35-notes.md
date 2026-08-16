# M35 顶层 LangGraph Harness 与 SQL/RAG Router 实施素材

> 状态：开发完成，`finish-module` 与 `finish-docs` 均已完成；待用户人工检查与 `accept-module` 验收。
>
> 对应计划：[m35-plan.md](m35-plan.md)

## Implementation checklist

- [x] 复核运行/评测/RAG/数据库 state、LangGraph 当前接口与工作树，记录依赖快照。
- [x] 直接声明 LangGraph 依赖，并完成最小 import / compile 验证。
- [x] 建立单轮 Harness 的最小合同、runtime context 与 `route → tool/terminal → controller` 拓扑。
- [x] 实现可注入的 deterministic/conservative Router，覆盖 SQL、RAG、澄清、拒绝和 Hybrid 保守停止。
- [x] 将 Text2SQL 与 `RAGAnswerFlow.run()` 分别接入受控 Tool adapter；完成 SQL Evidence 与四轴失败映射。
- [x] 按 G-M35-1 方案 A 组装 local/demo/test caller resolver，接入 `/api/query` 的唯一 Harness 路径和兼容投影。
- [x] 扩展 Trace、Harness Eval 与 API/Graph/Tool 回归；确认一题只调用一次 Graph。
- [x] 运行计划验证矩阵、完成注释审计，并按 `finish-module` 固化收工素材与 handoff。

## 开工快照与已确认边界

- M35 对应 Phase 4 P3：只做单轮顶层 Harness、保守 Router、SQL/RAG 两个受控 Tool 及四轴投影；不做 P4 loop/thread/context、P5 Hybrid、P6 检索优化或 M34 external profile 接入。
- G-M35-1 已由用户于 2026-08-16 选择方案 A：明确 `local/demo/test` 的 demo/test caller resolver；其他环境没有 authenticated resolver 时失败关闭。请求 `user_role` 只能选择 resolver 已解析的 role，不能独立授权。
- `docs/state/AI_CONTEXT.md` 仍显示 M34 为活动模块/plan；这是 M34 收工文档未切换的状态滞后。M35 当前范围、合同与执行依据以已确认的 `m35-plan.md` 为准。
- 本模块使用 22 条业务 active Knowledge release 的既有 `RAGAnswerFlow.run()`；不启用或替换为 M34 EnterpriseRAG-Bench external profile。

## 开发记录

- 2026-08-16：已完整阅读 `AGENTS.md`、`m35-plan.md`、`AI_CONTEXT.md`；后续涉及运行/评测、RAG 或数据库事实时，按 AI_CONTEXT 必读规则继续读取对应 state 文档。
- 2026-08-16：为保持 Harness 的深模块边界，采用“一个小 interface / 可注入 runtime adapter”的设计：Graph 只编排 route、唯一 Tool 和终止；不把 Text2SQL/RAG 内部步骤拆成浅 Graph 节点。
- 2026-08-16：LangGraph 直接依赖以当前环境已验证的 `1.1.2` 为下限，约束为 `>=1.1.2,<2`；最小 `StateGraph` / `Runtime` import 与无 checkpoint compile 已通过。没有启用 Store、checkpointer 或 interrupt。
- 2026-08-16：首轮 API 回归曾出现 `route=none`。根因是 SQL EvidenceRef 沿用了不存在的 `safe_projection()` 名称，Harness 按合同失败关闭掩盖了内部异常。改用既有 `audit_projection()` 后，legacy SQL 深链已实际构造 Evidence、ledger 和兼容响应；这不是安全语义变更。
- 2026-08-16：SQL 技术失败历史上由 `SQLToolResult` 标成 `safety_status=blocked`；M35 adapter 只把 `sql_guard_blocked` 映射为 safety blocked，`llm_generation_error` 映射 external unavailable，其余 pipeline/driver 错误映射 failed 且 safety passed，避免 `blocked_reason` 吞掉技术错误。
- 2026-08-16：为严格落实“requested role 只能选择、不能授权”，local/demo/test resolver 先给出固定 fixture caller 及完整已知 role 集，再校验 requested role 是否在该集内；不按用户提交的 role 临时创建单角色 caller。此身份仍只属于明确标记的 demo/test，不声称生产认证。
- 2026-08-16：全仓回归发现 M27 的“请求不存在供应商字段”从 `rejected` 变成 `pipeline_error`。根因是 adapter 把所有 `plan_validation_failed` 都当技术失败；但 pipeline trace 明确标注 `blocked_via=semantic_request_validation` 的分支是既有确定性 expected rejection。现已仅按该 trace 标记映射为 `completed / unsupported / blocked`；普通 QueryPlan/driver 失败仍保持 safety passed。M27 反例与新增 adapter 单测均通过。
- 2026-08-16：同一轮全仓回归还暴露 legacy raw SQL Guard 缺少 `tool_calls[0]`。根因是旧 API 原先在 response builder 补了 `sql_guard` call，收进 adapter 后漏掉。现由 Guard Observation 在没有下游 tool call 时补回同一结构化记录；M5 兼容反例与 M35 adapter 测试通过。
- 2026-08-16：最终全仓回归（396 项）有 394 通过、2 项失败，均来自旧 Phase 3 API 测试：它们要求 SQL 的 QueryPlan output-projection 拒绝和 LLM JSON/SQL 解析失败都外显为 `safety_status=blocked`。这与 M35 plan C3/C6、Phase 4 四轴不变量（`external_unavailable` 属于 execution，技术失败不借用 `blocked_reason`）存在核心合同冲突；在用户确认公开兼容策略前不自行改测试或改四轴映射。
- 2026-08-16：用户确认方案 A：将 QueryPlan output-projection mismatch 视为执行前的确定性 SQL 输出合同拒绝，保持 `completed / no_answer / blocked`；将 LLM JSON/SQL 解析失败明确为 `external_unavailable / no_answer / passed`，不写 `blocked_reason`。前者保留已有 SQL fidelity 保护，后者落实 M35 C6 的技术故障四轴语义；已补充 adapter 反例并更新旧 API 测试的过时断言。
- 2026-08-16：实际调用本地业务 `RAGAnswerFlow.run()` 验证完成：默认 22 条业务 active release 返回 `completed / complete / passed`，并生成 validated citations、docs_used、cited ledger 和安全 EvidenceRef；没有触发 M34 external profile 或远程 Composer。
- 2026-08-16：参考源码定点复核完成。ARAG 的 `StateGraph` / conditional edge 被借鉴为显式分支与终止；DataAgent 的固定编排被借鉴为深 Tool 与控制边分离；GustoBot 的“未指定 Tool 则 postgres+milvus 兜底”被明确拒绝。未复制其 loop、fan-out、checkpoint、强制检索或多后端 fallback。

## 验证快照

- 2026-08-16：最小 `langgraph 1.1.2` import / `StateGraph(..., context_schema=...)` compile 通过；项目 `pyproject.toml` 已直接声明 `langgraph>=1.1.2,<2`。
- 2026-08-16：M35 Harness / SQL adapter / Harness Eval 聚焦测试 `10 passed in 0.77s`。覆盖固定拓扑、SQL/RAG/terminal 单 Tool、Hybrid 保守停止、caller fail-closed、Guard 与技术错误四轴、SQL Evidence/ledger、fixture 环境 resolver、closed-world Eval artifact。
- 2026-08-16：M35 API/Trace 三个 TestClient case 分别通过（每项 `1 passed`，约 12–13s，均有既有 Starlette `httpx` deprecation warning）：SQL 的响应/Trace 同轮投影、RAG validated citations 无正文 Trace、unknown role Tool 前失败关闭。
- 2026-08-16：既有 API 回归 `tests/test_m3_query.py` 为 `4 passed, 1 warning in 26.82s`；M16 TraceRouter 前 11 项为 `11 passed, 1 deselected, 1 warning in 23.06s`，最后 API 契约项单独为 `1 passed, 1 warning in 12.43s`。warning 均为 FastAPI TestClient 的既有 Starlette deprecation，不影响 M35 合同。
- 2026-08-16：M31/M32/M33 required contract 聚焦套件为 `48 passed in 2.19s`；未调用真实 LLM、远程 Router、Milvus、external Composer/Judge 或 LangFuse Cloud。
- 2026-08-16：`compileall -q app engine eval demo tests` 与 `git diff --check` 通过；Git 仅报告既有 CRLF 自动转换提示，无空白错误。

## 模块名称与改动文件清单

- 模块：M35「顶层 LangGraph Harness 与 SQL/RAG Router」（Phase 4 P3）。未提供模块起始 commit，本次按当前工作树中与 M35 范围一致的改动检查；未触碰开始前已存在的 `.codex/skills/finish-module/SKILL.md` 用户改动。
- 新增 Harness：`engine/harness/__init__.py`、`contracts.py`、`router.py`、`caller.py`、`adapters.py`、`graph.py`。
- 新增 Eval/测试：`eval/harness_contracts.py`、`tests/test_m35_api_trace.py`、`tests/test_m35_harness.py`、`tests/test_m35_harness_eval.py`、`tests/test_m35_sql_adapter.py`。
- 集成与兼容投影：`app/main.py`、`app/api/query.py`、`app/schemas/agent.py`、`engine/trace/recorder.py`、`demo/streamlit_app.py`、`pyproject.toml`、`tests/test_phase3a_pipeline.py`。
- 开发素材：`docs/notes/m35-plan.md`、本文件。

## 关键决策与取舍

### G-M35-1：demo/test caller 组装

- 决策内容：`local/demo/test` 注入显式 fixture caller resolver；其他环境无 authenticated resolver 时，在 Tool 前以 `caller_untrusted` 失败关闭。
- 当时选项：A 是显式 local/demo/test resolver、请求 `user_role` 只能选择已解析角色；B 是所有环境均需外部手工注入 resolver。
- 主要风险：A 若环境标识不清可能被误当生产认证；B 会中断当前默认本地/demo 启动体验，并诱发未来在 API 内偷加请求体角色直信旁路。
- 推荐与用户选择：推荐 A；用户于 2026-08-16 确认 A。实现中 fixture caller 保有固定完整 role 集，请求 role 只选 active role，不能自行创建/提升身份。

### SQL 失败的四轴映射

- 决策内容：SQL Guard 仍为 safety blocked；QueryPlan output-projection mismatch 是执行前确定性输出合同拒绝，映射为 `completed / no_answer / blocked`；LLM JSON/SQL 解析失败映射为 `external_unavailable / no_answer / passed`，不写 `blocked_reason`；其余 driver/pipeline 技术错误为 `failed / no_answer / passed`。
- 当时选项：A 区分确定性输出合同与 provider 解析失败；B 将两者都视作技术失败；C 沿用旧 API，把两者都写成 blocked。
- 主要风险：A 会让旧客户端看到 LLM 解析失败不再是 blocked；B 弱化输出投影合同的执行前保护语义；C 违反 Phase 4 四轴和 M35 C6。
- 推荐与用户选择：推荐 A；用户于 2026-08-16 确认 A。旧 Phase 3 测试仅更新 LLM 解析失败的过时断言，并为 projection 拒绝新增 adapter 反例。

### 深 Tool 与保守路由

- 决策内容：Graph 只控制 `START → route → (sql_tool | rag_tool | terminal) → controller → END`；Text2SQL pipeline 和 `RAGAnswerFlow.run()` 保持完整深 Tool。Router 只使用可注入 deterministic 规则，未知/Hybrid 不默认执行 Tool。
- 取舍原因：避免 Graph 取得 SQL/RAG 内部双控制权、避免未指定 Tool 时的隐式双后端 fallback；也不提前建设 P4 loop、P5 Hybrid 或远程 Router。

## 阶段 1 注释小结

- 覆盖扫描：按当前工作树的 M35 文件范围审计 113 个类、函数、方法和有行为的测试辅助点；此前发现并补齐 8 处缺失说明（caller resolver、Eval fake run、API 内部闭包/递归安全投影、测试 fake Tool/Router 等），最终 `113/113` 覆盖，0 缺失。
- 质量扫描：复核并保留了 Harness runtime context、显式 reducer/conditional edge、深 Tool seam、fixture caller 与四轴映射的中文 docstring；这些注释已说明为什么不把 SQL/RAG 拆成 Graph 节点、为什么请求角色不能授权、为什么技术失败不复用安全文案。
- 可读性扫描：`app/api/query.py` 的 resolver→runtime→单向 response/Trace 投影，`engine/harness/graph.py` 的 route/tool/controller 分权，`engine/harness/adapters.py` 的 Guard/语义/投影/provider 分支均有步骤或 ★ 注释；未发现连续核心逻辑无解释。
- 形式扫描：新增/修改注释以中文为主，步骤分隔线与 ★ 标记只用于关键控制点；无需再补格式修改。

## 阶段 2 验证快照

- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\m35-contract-recheck tests\test_m35_sql_adapter.py tests\test_phase3a_pipeline.py::test_pipeline_blocks_extra_projection_before_sql_execution tests\test_phase3a_pipeline.py::test_sql_generation_failure_trace_keeps_raw_preview_and_parse_context`：`7 passed, 1 warning in 23.00s`。验证方案 A 的 projection/LLM 解析失败映射及新增 adapter 反例。
- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\m35-full-pytest-approved`：`397 passed, 1 warning in 555.68s (9:15)`。该 warning 是 FastAPI TestClient 使用的既有 Starlette `httpx` deprecation，不影响 M35 合同。此前一次全仓回归的 `394 passed / 2 failed` 已定位为上述旧 Phase 3 断言与新四轴合同冲突，用户确认方案 A 后重跑全绿。
- `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m compileall -q app engine eval demo tests`：通过，无语法错误。
- `git diff --check`：通过，无空白错误；Git 报告的 LF→CRLF 是工作树自动转换提示，不是 diff 问题。
- 未运行：真实 LLM Router/Text2SQL Eval、Milvus/embedding、M34 external Answer Eval、远程 Composer/Judge、LangFuse Cloud；它们均不属于 M35 计划验证范围，不能据本模块测试宣称已证明。

## 参考资料

- `docs/phase4-reference.md`：按 P3 定点复核。借鉴 ARAG 的显式 `StateGraph`/conditional edge 和 state reducer 表达；借鉴 DataAgent 固定编排中控制边与深执行模块分离的思路。
- `D:\.Work\Practice\Python-Practice\references` 下 ARAG 的 `graph.py`、`graph_state.py` 与 DataAgent 的 `DataAgentConfiguration.java`：只借鉴上述局部结构，不复制其 loop、fan-out、checkpoint 或多轮状态。
- GustoBot router 实现：作为反例复核；未照搬其未指定 Tool 时 postgres+milvus 的默认兜底，M35 对未知/Hybrid 保守停止。
- 项目本地 LangGraph `1.1.2`：实际验证 `StateGraph`、`Runtime` import 和无 checkpoint compile；依赖固定为 `langgraph>=1.1.2,<2`。

## Handoff（下一模块交接）

### 已完成且后续可以依赖

- `engine.harness.graph.run_harness()` 是唯一单轮 Graph invocation seam，编译拓扑固定为 route → 至多一个 Tool/terminal → controller；`AgentRunResult` 是 API、Trace、Eval 的唯一出站事实。
- `HarnessRequest`、`RouteDecision`、`ToolObservation`、四轴状态、终止原因、caller safe ref 与 EvidenceRef 安全投影已闭合；`/api/query` 没有默认绕过 Harness 的 SQL/RAG 路径。
- Text2SQL adapter 可复用现有 new/legacy pipeline：成功 SQL 生成 fingerprint/Evidence/ledger；Guard、确定性 projection、语义拒绝和技术不可用有稳定分支。RAG adapter 每轮只调用一次既有 `RAGAnswerFlow.run()`。
- local/demo/test fixture caller resolver 已落实；请求体 role 不可单独授权。`eval/harness_contracts.py` 提供独立的 `phase4-harness-v1` closed-world 合同 Eval。

### 下一模块建议入口

- 建议首先解决的主要问题：根据真实失败簇规划 P4 的首个有界恢复切片（G5），而不是直接扩展 Router 规则或建设 Hybrid。
- 建议从哪些现有 seam、失败簇或未闭环能力开始：`AgentRunResult.reason_code`、`execution_status`、`termination_action`、Harness Eval Scenario 与 Trace 中的 route/tool 事实，先界定哪些 `external_unavailable`、澄清或证据不足值得允许一次恢复动作。
- 为什么这是自然的下一步：P3 已完成一次受控执行和可观测终止；P4 才负责预算、停止和恢复，能避免把失败处理偷偷塞回 Router 或 Tool。

### 未完成、未证明与当前风险

- 未完成：P4 loop/thread/context builder、P5 Hybrid、P6 retrieval recipe A/B、生产认证、远程 Router、M34 external profile 接入。
- 尚未通过真实验证证明：真实 LLM/远程服务、Milvus、external Composer/Judge、LangFuse Cloud 都未运行；本地 RAG 仅验证当前 22 条业务 active release 的既有 AnswerFlow。
- 活跃风险或兼容边界：deterministic Router 对开放问法较窄；旧客户端若只读取 `safety_status`，需适配新增 execution/answer/reason 字段以区分 LLM 不可用；demo fixture caller 不得被描述为生产认证。

### 必须延续的决策与边界

- G-M35-1 方案 A：local/demo/test 才允许 fixture resolver，其他环境缺 authenticated resolver 必须 fail closed；请求 role 只能选择已解析 role。
- 四轴边界：技术不可用属于 execution，`blocked_reason` 只服务安全文案；QueryPlan projection mismatch 是执行前确定性输出合同拒绝，LLM 解析失败不是安全 blocked。
- 继续复用完整 Text2SQL pipeline 与 `RAGAnswerFlow.run()` 深 Tool；不在 Graph 外再生成答案，不让 `force_new_pipeline=false` 绕过 Harness。
- M35 不做 P4/P5/P6/M34 检索优化或远程 Router；历史 M27/M31–M34 artifact 不改写、不混算。

### 待触发的决策门

- 决策门：是否允许真实/远程 Router，或改变默认的本地 demo caller 组装。
- 触发条件：准备启用外部模型路由、生产部署/认证 provider、修改 role/tenant 模型，或 P4 需要新的安全/出站边界。
- 触发前允许做什么：读取 Trace/Eval、设计 deterministic Scenario、调查失败簇和规划 P4。
- 触发前禁止做什么：静默出站、信任请求体 role、引入无界 loop/默认双 Tool fallback，或把 M34 external profile 偷接进默认 RAG。

### 下一轮规划必读指针

- `docs/phase4-roadmap.md`：P4/G5、四轴不变量和 Agent Loop 的预算/停止约束，决定恢复切片是否可行。
- `docs/notes/m35-plan.md`：C1–C6、验证矩阵和“遗留与后续”，避免下一模块重开 P3 已冻结合同。
- `docs/notes/m35-notes.md`：本模块的四轴映射、用户确认的两个决策和验证基线。
- `engine/harness/contracts.py`、`engine/harness/graph.py`、`eval/harness_contracts.py`：下一模块必须消费的 seam、状态事实和独立 Eval family。
- `docs/state/rag-current-state.md` 与 `docs/state/eval-baselines.md`：若后续涉及 RAG 失败或评测，必须先确认 M34 external 边界和现有账本。

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

- 素材来源：本文件的模块范围、两项用户决策、验证快照、参考资料、风险与 Handoff；并以当前会话、`git status --short`、`git diff --name-only`、`git diff --cached --name-only` 交叉核对。没有运行新的 pytest、Eval、API、数据库或真实 LLM。
- 二次补齐：发生 1 次。完整回读首稿后，补齐 changelog 中 SQL 方案 A/B/C 各自的适用条件与风险；同时从 AI_CONTEXT 退役 1 条 M27 v2 历史验证、1 条 M22–M26 历史路线判断和 1 条 M27 v1 已解决坑。未发生第 2 次补齐。
- dev-log 交付门：15/15 已逐项核对并勾选。
- 三文档交付门：11/11 已逐项核对并勾选。
- 完整回读：已按顺序完整回读 changelog 的 M35 新章节、AI_CONTEXT 当前状态/默认值/验证事实/路线/活跃坑，以及 dev-log 的 M35 完整章节；确认无截断、乱码、层级错误、事实夸大或 notes 外推。
- 历史结论修正：在 changelog 的 M34、M33 原条目处分别添加 2026-08-16 `⚠️ 注`，说明 M35 已完成 P3，但没有修复 M34 召回质量，也没有完成生产认证、Hybrid 或远程能力。
- `git diff --check`：通过；仅有工作树 LF→CRLF 自动转换 warning，不属于空白错误，不影响交付。
- 未证明与遗留：真实 LLM Router/Text2SQL Eval、Milvus/embedding、M34 external Answer Eval、远程 Composer/Judge、LangFuse Cloud 均未在 M35 运行；P4 恢复、P5 Hybrid、生产认证、远程 Router 和 M34 召回/context packing 仍属后续。
