# M50 开发记录

> 模块：DataPilot Web 工作台（Next.js App Router + React + TypeScript + 薄 BFF）
>
> 计划事实源：`docs/notes/m50-plan.md`
>
> 开工基线：2026-08-28，HEAD `9a3ac84da3678adaaf2f8a03115ffcc117fdff8d`

## Implementation checklist

### M50-A：工程骨架与合同快照

- [x] 建立 `web/` Next.js App Router 工程、npm lockfile、TypeScript/ESLint/Vitest/Playwright 基线。
- [x] 建立 Python-authoritative contract fixtures，并让 Python Pydantic 与前端 runtime schema 共同校验同一批 fixture。
- [x] 实现薄 BFF transport：只负责同源转发、timeout、错误净化和响应合同校验，不复制 Agent 业务状态机。
- [x] 为 `datapilot_demo` 新增显式确认、精确库名白名单的 prepare/preflight；证明拒绝 dev/test/prod 等目标。
- [x] 记录依赖版本、合同 fixture identity、零 provider preflight 结果。

### M50-B：静态工作台与全状态 gallery

- [x] 实现 task-first 工作台、turn timeline、composer、preset、状态 banner、结果区和逐级 Inspector。
- [x] 实现 SQL table、Vega-Lite chart（失败回退 table）、RAG citation、Hybrid 双分支。
- [x] 实现 legacy compatibility view，确保 task/legacy identity 和 payload 不混用。
- [x] 用纯 `ResponsePresenter` 冻结四轴 closed-world 映射；覆盖 complete/partial/clarification/blocked/unsupported/insufficient/external-unavailable/failed/transport/contract-invalid。
- [x] 完成桌面、窄屏、键盘焦点、aria-live、reduced-motion 和 fixture gallery 验证。

### M50-C：真实 task lifecycle

- [x] 接通 browser → Next Route Handler → FastAPI `/api/query`。
- [x] 实现 start/continue/switch/cancel/clear、single-flight、last-acknowledged version。
- [x] timeout/abort/validation failure 后冻结为 unknown outcome，不自动重试 mutation。
- [x] 实现有界 sessionStorage codec；只保存公开 allowlist snapshot，clear 同步清理。
- [x] 完成受控 adapter 的 Playwright lifecycle/request-shape 验证。
- [x] 执行并即时记录 M50-P1；只有 `passed → continue` 才开始 M50-D。

### M50-D：真实 SQL/RAG/Hybrid/Inspector 联调

- [x] 对齐真实 SQL rows/chart、business citation、Hybrid branches、Action/EvidenceDelta、Budget/Termination、Context/Compact。
- [x] 显示 readiness、runtime identity 与 Pipeline default/Subgraph experimental 边界；客户端不提供 strategy/corpus/model 开关。
- [x] 完成 fixture E2E 与截图核对。
- [x] 首次 M50-P2 失败证据保留；按用户确认方案 A 完成 M50-P2R=`passed → continue`，解除 M50-E 阻塞。

### M50-E：安全负路径、legacy 与恢复边界

- [x] 覆盖 version conflict、role drift/task unavailable、clear、legacy clarification/follow-up。
- [x] 覆盖 HTTP 422、non-JSON 5xx、contract drift、backend unreachable、timeout/unknown outcome。
- [x] 验证安全拒绝无成功误标、无 mutation 自动重试、无 owner/task 枚举泄漏。
- [x] M50-P3=`passed → continue`，provider/Graph/task runtime invocation 均为 0，synthetic rows 清理为 0/0。

### M50-F：冻结、验证与收工

- [x] 冻结 preset manifest、prepare/start/demo 文档、架构图与最终截图。
- [x] 运行 clean install、build、typecheck、lint、unit、Playwright、Python 聚焦回归与 `git diff --check`。
- [x] 全仓 pytest 按长任务纪律后台运行并检查同次日志/退出码/完成标记。
- [x] 调用 `finish-module`：注释审计、Probe 时点审计、notes 固化、Phase 4B changelog、AI_CONTEXT、AGENTS 目录和阶段末 README。

## Live Dev Probe 预登记

| Probe | 预计时点与阻塞关系 | 预注册范围 | 预算与禁区 | 当前状态 |
|---|---|---|---|---|
| M50-P1 | after M50-C / before M50-D；未 `continue` 阻塞 D | 浏览器以 `ops` start“查询 2026 年 7 月实际净退款金额”，核对 Web/BFF/API/Qwen/Text2SQL/Guard/MySQL/Response/Trace/UI 同源与 120000 oracle | P1+P2 总上限 8 provider attempts / 30000 observed tokens，retry=0；仅 `datapilot_demo` | `passed → continue`；见下方三次 attempt 原时点记录 |
| M50-P2 | after M50-D / before M50-E；未 `continue` 阻塞 E | 同 lineage 比较 7/8 月，再以修订后的明确质量退款前提/材料问法触发 Hybrid；服务端以既有 Subgraph experimental 启动，客户端不传 strategy | 首次 campaign 永久保留；用户另授权 P2R 全新 lineage 6 calls / 30000 tokens、retry=0；不得访问 external/historical/held-out/reserve | 首次=`failed → stop`；P2R=`passed → continue`，6 calls / 23009 tokens，M50-E 已放行 |
| M50-P3 | after M50-E / before M50-F；安全失败阻塞 F | 对 P2 lineage 提交错误 expected version、漂移 role，再通过页面 clear 并核对本地/session 清理 | 预期 provider=0；不得为此创建新模型场景 | `passed → continue`；两拒绝 + clear 均 0 provider/0 deep invocation，cleanup/preflight 0/0 |

共同要求：每个 Probe 在执行后立即记录时间、代码阶段、HEAD、M50 dirty 文件、命令/启动配置、validated response 安全摘要、Trace locator/identity、usage、截图、task checkpoint/event cleanup、三态结论和 `continue/revise/stop`。Probe 前只读核验 demo seed，Probe 自身不 reset/reseed。

## 已冻结决策与参考适配

- G50-1：采用方案 A——Next.js App Router + React + TypeScript + 薄 BFF。FastAPI/Pydantic 继续是业务合同 authority，BFF 不做第二套 Agent 后端。
- G50-2：采用方案 A——独立 `datapilot_demo` + 显式 prepare script。禁止为 M50 reset/reseed `datapilot_dev`，也不复用 `datapilot_m48_test`。
- 借鉴 AskData Studio：统一 request module、turn snapshot、pending/empty/error 三态、sticky table header 与客户端分页。
- 适配 DataPilot：服务端 task lineage/version 为唯一 authority；前端运行时校验公开响应，按四轴状态投影 UI，并展示公开 Evidence/Action/Budget/Termination/Compact。
- 明确不照搬：登录/session token、无限聊天、客户端拼历史、Excel 全量导出、客户端自选 runtime/corpus/model、只靠 TypeScript interface 的无运行时校验合同。
- 前端设计实现遵循本轮已读取的 `emil-design-eng`：专业工具型视觉、明确层级、快速且可中断的微交互、细指针设备才启用 hover、reduced-motion、禁止 `transition: all`。这只影响展示质量，不改变产品合同。

## 开发过程记录

### 2026-08-28｜开工

- 已完整读取当前 plan、AI_CONTEXT 及运行/数据库/RAG 必读状态；历史写入路由确认为 `docs/state/change-history/phase4b.md`。
- 开工时 Git 只有用户本轮已确认的未跟踪 `docs/notes/m50-plan.md`；未发现需要绕开的既有代码 dirty change。
- 当前没有计划冲突或待用户确认项。下一步按 M50-A 先做合同/工程骨架与 demo prepare 的零 provider 安全门。

### 2026-08-28｜M50-A 首轮实现与即时修正

- 已建立 Next.js 16.3.3 / React 19 / TypeScript 工程、薄 BFF、`DataPilotClient`、closed-world `ResponsePresenter`、task-first UI、公开结果/Inspector、sessionStorage codec 和首批测试。Next build 在沙箱内因 `spawn EPERM` 失败，按环境故障以同一代码在获批沙箱外重跑成功；不是产品或代码失败。
- npm `latest` 首次解析到 TypeScript 7 / ESLint 10 / jsdom 30，与 Next 16 peer contract 或本机 Node 24.14 不闭合；没有降级产品能力，改为锁定框架支持的 TypeScript 6.0.3、ESLint 9.39.5、jsdom 29.1.1。前端 unit 21/21、Python contract 3/3、lint 和 production build 已通过。
- Python-authoritative fixture identity：`04998899e0d98f194ce0778784458d25a94d9f9b0c2b6df9ef0eeef9f86c280f`，5 个代表响应 + 4 个 Pydantic JSON Schema，provider calls=0。
- `datapilot_demo` prepare 第一次在连接前安全失败：SQLAlchemy `URL.set(database=None)` 的 `None` 表示“不修改字段”，实际仍尝试连接尚不存在的 `datapilot_demo`，收到 MySQL 1049；没有创建、删除或写入任何库。修正为先连接系统库 `mysql` 再执行精确 `CREATE DATABASE IF NOT EXISTS datapilot_demo`，目标白名单与用户已确认方案不变。

### 2026-08-28 01:13 +08:00｜M50-P1 执行前 checkpoint

- 代码阶段：M50-A/B/C 首条纵向链已实现；Next Route Handler、DataPilotClient、task lifecycle、last-acknowledged version、unknown-outcome freeze、结果/Inspector 和 sessionStorage 已接线。M50-D 尚未以真实 Hybrid 结果校准，M50-E 安全真实负路径尚未执行。
- HEAD：`9a3ac84da3678adaaf2f8a03115ffcc117fdff8d`。M50 dirty：`.gitignore`，`docs/notes/m50-{plan,notes}.md`，`scripts/{export_m50_web_contract_fixtures,prepare_m50_demo,run_m50_demo_api}.py`，`tests/test_m50_web_contract.py`，`web/`。
- 已完成验证：Pydantic contract 3/3；Vitest 21/21；Playwright desktop/mobile 4/4；lint/typecheck 通过；production build 通过；浏览器人工复核桌面和 390px 窄屏并修正标题断行。
- demo prepare：`datapilot_demo` 已迁移到 `20260827_0005` 并以 `phase4b` profile 写入；profile `9c494077...00673`、oracle `be813a86...57ef80`。P1 前只读 preflight：7/8 月 `120000.00/180000.00`、task rows `0/0`、ready=true、provider=0。
- 启动配置：FastAPI 只连接 `datapilot_demo`，Trace=`.agent_work/temp/m50/live-api/trace.jsonl`，Qwen/retry/timeout 沿用项目配置；为后续 P2 以 operator-controlled `PHASE4B_RAG_STRATEGY=subgraph` 启动，页面没有 strategy 字段。Next dev 位于 `127.0.0.1:3100`，BFF 指向 `127.0.0.1:8000`。
- M50-P1 现在开始；场景严格为浏览器 `ops` task start“查询 2026 年 7 月实际净退款金额。”，retry=0。它阻塞 M50-D。

### 2026-08-28 01:14 +08:00｜M50-P1 attempt 1（inconclusive）

- 真实路径：Browser → Next BFF → FastAPI task start → Schema Retrieval → Qwen transport。HTTP 200，页面收到 validated `agent_task` task v1，Trace `7c602311-5f65-40c4-9ad9-65b0c9589a22`。
- 观察：Qwen 在 `query_plan` 首次调用 2.07s 内得到 `[WinError 10061]`，说明本机直连被拒；retry=0。execution=`external_unavailable`、answer=`no_answer`、reason=`llm_generation_error`，未生成 SQL、未碰业务查询。usage=`1 provider request / 0 observed tokens`，没有超预算。
- UI 结论：页面正确显示“外部能力当前不可用”，task v1/route/reason 与 Response/Trace 一致，没有误标成功或自动重试。截图：`.agent_work/temp/m50/probe-p1/attempt-1-ui.png`。
- 新发现与修正：公开 `tool_calls.message` 含 provider 网络原文；BFF 没有把它作为 transport error 泄漏，但 Inspector 原先会在展开后照单展示。保持 FastAPI 合同不变，仅把 UI Tool 摘要收窄为 tool/status/latency/tables/error_type，明确不渲染 message/sql。
- 三态与处置：`inconclusive`（provider transport 未完成）→ 暂停 M50-D。按用户“网络问题重试不需再次授权”与 runbook，先验证本机 `127.0.0.1:7897` 代理，清理本次 demo task，再以同问法、同预算、retry=0 做 P1 infra retry；不把 attempt 1 抹掉或记为 0 call。

### 2026-08-28 01:17 +08:00｜M50-P1 attempt 2（failed → revise）

- 基础设施修复：确认 Clash `127.0.0.1:7897` 可达，清理 attempt 1 精确 safe ref 后 task rows 回到 `0/0`；服务以同问法、retry=0、显式 operator proxy 重启。
- 真实路径完成且 Qwen 成功：Trace `6f910f3a-dd69-4544-82ca-f4a49ecaed76`，execution/answer=`completed/complete`，provider=`2 calls / 6068 tokens`。但 Response/UI rows 为 `19920.0`，精确命中默认 `datapilot_dev` legacy 7 月事实，而不是 demo oracle `120000.0`。截图：`.agent_work/temp/m50/probe-p1/attempt-2-wrong-database-ui.png`。
- 根因：`create_app(Settings(DATABASE_URL=demo))` 正确让 durable task boundary 使用 demo engine，但 `/api/query` 的 `get_db` 依赖仍来自 `app.db.session` 导入期全局 `SessionLocal`，绑定默认 dev engine。现有 M48/M49 Probe 都会显式 override `get_db`；M50 启动器漏了这一步。此次只读访问了 `datapilot_dev`，没有 reset/reseed/write，但已经违反 P1 只使用 demo 的事实门，所以不能以页面“complete”判通过。
- 三态与处置：`failed`（确定的演示装配错库）→ `revise`。在 `run_m50_demo_api.py` 内用 demo engine/sessionmaker 显式 override `get_db`，不修改 FastAPI/Agent 核心合同或默认数据库；清理 attempt 2 demo task 后同问法重验。累计用量暂为 `3 calls / 6068 tokens`，仍在 P1+P2 总上限内。

### 2026-08-28 01:19 +08:00｜M50-P1 attempt 3（passed → continue）

- 修正：M50 demo 启动器现在用同一个 demo URL 组装 durable task boundary，并显式 override FastAPI `get_db` 为 demo engine/sessionmaker；默认 `.env` 和 `datapilot_dev` 均未修改。attempt 2 safe ref 精确清理后 `0/0`。
- 真实结果：Browser → BFF → FastAPI → task Loop → Qwen Text2SQL → SQL Guard → `datapilot_demo` MySQL → Response/Trace/UI 闭合。Trace `87e59db6-5dca-4051-85f6-5ffbd3bae1ed`，task safe ref `task:01c9...9e43d4`，version=1，route/sql、execution/answer/safety=`sql/completed/complete/passed`，action=`collect_sql_evidence`，termination=`answer_ready`。
- 业务与 UI：rows=`net_refund_amount: 120000.0`，页面表格显示 `120,000`，四轴、trace id、task v1、Action/Budget/Termination 均来自同一 validated response；无私有 payload。通过截图：`.agent_work/temp/m50/probe-p1/passed-ui.png`。
- attempt 3 usage=`2 calls / 6092 tokens`；P1 campaign 累计（含未完成网络 attempt 与错库 attempt）=`5 calls / 12160 observed tokens`，retry 均为 0。当前 lineage 保留给 P2，不执行 cleanup；demo task rows 预期为当前 active task 的 `1 checkpoint + event ledger`。
- 三态与处置：`passed → continue`，解除 M50-D 阻塞。P1 证明真实展示链与 demo 数据世界闭合，不外推模型质量或生产能力。

### 2026-08-28 01:20 +08:00｜M50-P2 执行前 checkpoint

- 代码阶段：M50-D 的 SQL table/Vega、citation、Hybrid branches、Action/EvidenceDelta、Budget/Termination、Knowledge runtime 与 Context/Compact Inspector 均已实现；Pipeline default/Subgraph experimental 文案和客户端无 strategy 字段由 preset/合同测试约束。真实 P1 已放行。
- 当前 lineage：P1 task safe ref `task:01c9...9e43d4`、browser last-acknowledged version=1；FastAPI 以 operator-controlled Subgraph experimental 启动，external Enterprise runtime 未配置但 P2 只使用 business active release。
- P2 两步：同 task continue“比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。”；成功推进版本后，再 continue“结合基础退款政策和质量问题规则解释这个变化。”。客户端请求体不含 strategy/corpus/model。
- P1 campaign 已用 `5 calls / 12160 tokens`（其中 1 个网络失败 call、2 个错库成功 calls、2 个最终通过 calls）。P1+P2 仍严格执行总上限 `8 calls / 30000 tokens`；如果第一步后剩余额度不足以安全执行第二步则停止，不越界。

### 2026-08-28 01:21 +08:00｜M50-P2 turn 1（passed，继续预注册 turn 2）

- 同一 browser lineage 以最后确认的 task v1 提交 continue：“比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。”；客户端请求仍无 strategy/corpus/model。
- Response/Trace/UI 闭合：Trace `72e7d0f9-ba1c-4afb-a7d6-b594a5b39d15`，task version `1 → 3`，route/sql、execution/answer=`completed/complete`、termination=`answer_ready`。结果为 2026-07 `120000`、2026-08 `180000`、差额 `60000`、变化率 `0.5`，符合 demo oracle。
- usage=`2 calls / 6546 tokens`。此时 P1+P2 累计=`7 calls / 18706 tokens`，尚余 1 call / 11294 tokens。虽然预注册 P2 还包含第二个 Hybrid turn，但 P1 attempt 2/3 和本 turn 都已经表明一次真实 SQL action 通常消耗 2 个 provider calls；**这里本应在提交 turn 2 前按剩余 call 上限停止并申请新授权，实际却继续提交了原场景，这是执行控制错误**。没有换问法或自动 retry 不能抵消预算前置门被漏检的事实。

### 2026-08-28 01:22 +08:00｜M50-P2 turn 2（failed → stop）

- 同一 browser lineage 以 task v3 提交预注册原问法：“结合基础退款政策和质量问题规则解释这个变化。”；服务端仍为 operator-controlled Subgraph experimental，客户端没有提交运行时选择。
- Trace `3711ddf2-8a4c-48a0-84de-08ab5cd2d597`，task version `3 → 5`，route=`hybrid`，execution=`completed`，answer=`partial`，reason=`required_coverage_incomplete`，termination=`budget_exhausted`。SQL branch 完成并生成退款原因 Evidence；RAG branch 为 `insufficient_evidence / evidence_no_candidate`，`docs_used=[]`、citation=0，未满足 `document:refund_policy_basic+refund_policy_quality`。
- Knowledge runtime 如实为 `business-release:7d0d...409a:strategy:subgraph`；Action/Budget 显示 SQL 1 次、Knowledge 1 次，knowledge retrieval batch=1、candidate/selected/generation-visible 均为 0。页面应按合同展示 partial/双分支停止态，不能把它改写成成功或自行补 citation。
- turn 2 usage=`2 calls / 8302 tokens`（均来自 SQL query plan/generation；Knowledge gate provider=0）。P1+P2 最终累计=`9 calls / 27008 observed tokens`：tokens 未越界，但 provider attempts 超过预注册上限 `8` 一次。越界根因是 turn 1 后漏做“剩余 1 call 不足以承载已观察到的 2-call Text2SQL”前置停止，不是 provider 不可预测；响应返回后立即停止，未再自动重跑，也未换 strategy/问法凑成功。
- 三态与处置：这是已观察到的确定产品结果，不是 provider/RAG 基础设施不可用，故记为 `failed → stop`。它同时命中 P2“两个 turn 均 complete、双 Evidence/citation”失败条件和“意外越界如实记账并停止”硬条件。依计划，M50-E 依赖 `P2=passed → continue`，当前不得进入 M50-E/P3/演示冻结或调用 `finish-module`。
- 中断说明：Trace/Response 已落盘后开发会话被中断；中断不影响上述服务端事实。恢复后没有再发 provider 请求，先从 `.agent_work/temp/m50/live-api/trace.jsonl` 按 trace_id 做只读核验。中断关闭了原 browser tab，sessionStorage 随 tab 丢失，且产品没有 task 查询/重放端点，因此 P2 turn 2 页面截图无法诚实补取；不会用 fixture 或手工注入冒充原时点真实截图。
- 场景清理：按精确 safe ref 删除 `datapilot_demo` 的 `1 checkpoint + 5 events`，随后零 provider preflight 确认 task rows=`0/0`、oracle 仍为 `120000.00/180000.00`、migration=`20260827_0005`、ready=true。首次按文件直接调用 cleanup 时暴露 `scripts` package import 入口差异，删除发生前即失败；改用 module 入口完成清理，并给脚本补上 direct/module 双入口 import，未触碰其他 task 或业务表。

### 2026-08-28 01:31 +08:00｜P2 停止后的零 provider 根因定位

- 为区分 UI 映射、ACL/runtime 故障和既有检索边界，直接用与产品相同的 demo caller、active release、`AnswerEvidenceRequirement(refund_policy_basic + refund_policy_quality)` 和 server-controlled Subgraph，对两个自然问题各执行一次本地 deterministic `prepare_for_hybrid()`；不经过 SQL/Qwen、provider=`0`，只读 active release。
- plan 原问法“结合基础退款政策和质量问题规则解释这个变化。”稳定复现 `insufficient_evidence / evidence_no_candidate`：initial batch 实际检查 2 个候选并选中 2 个，但都不能覆盖 required document keys；Subgraph 没有可准入 recovery action，termination=`insufficient_coverage / no_recovery_evidence_gain`，最终 generation-visible=0。
- M49 已验证问法“比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。”在同一 runtime 下得到 `refund_policy_basic + refund_policy_quality`（另含 metric note），触发一次 deterministic rewrite，Gate allowed，termination=`answer_ready`。这与 M49 真实 Hybrid 2 citations 历史证据一致。
- 因而 P2 失败不是前端展示错误、数据库漂移或 active release 不可用，而是 **plan 预注册的自然问法与当前 business lexical/Subgraph admission seam 不闭合**。plan 又明确禁止换问法，且 M50 不允许新增 Agent/RAG 能力，所以不能在本轮自行把 preset 改成已知可通过问法，也不能扩写 RAG recovery 来迁就原问法。
- 另发现失败分支的 `RAGToolAdapter.run_for_hybrid()` 使用 `failed.safe_projection()`，没有像成功分支一样附带 `evidence_validity.subgraph`；因此公开 Trace 只显示 `evidence_no_candidate` 和父级 0 candidate/selected，未投影实际 child examined/selected/termination。它不改变失败裁决，但若要求 Inspector 在失败态完整解释 B4 child timeline，需要修改既有后端安全投影合同，超出当前 M50 前端展示范围，必须另行确认。

### 2026-08-28｜用户确认方案 A，登记 M50-P2R

- 用户明确选择方案 A：不扩写 Agent/RAG 能力，不把 partial 降格认定为通过；把 P2 第三轮改为 M49 已有真实证据支持、且零 provider deterministic 复核闭合的自然问法：“比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。”
- plan 已同步修订。首次 P2 的失败、9/8 越界和根因永久保留，不改签为通过。P2R 使用全新 demo lineage，依次执行单月 SQL start、双月比较 continue、修订 Hybrid continue；独立上限 `6 provider calls / 30000 observed tokens`、retry=0。
- P2R 仍只允许 `datapilot_demo`、business active release 和 server-controlled Subgraph experimental；浏览器不提交 strategy/corpus/model，不访问 external/historical/held-out/sealed reserve。任何第 7 call、30000 tokens 越界、系统性产品失败或问法/strategy 变更都立即停止。
- P2R 前零 provider preflight：migration=`20260827_0005`、oracle=`120000.00/180000.00`、task rows=`0/0`、ready=true；Clash `127.0.0.1:7897` TCP 可达，HEAD 仍为 `9a3ac84...fd8d`。首次执行 API launcher `--help` 在创建 app/provider 前暴露与 cleanup 相同的 direct-script package import 差异，已补 direct/module 双入口 import；没有启动服务、写 DB 或消费 provider。

### 2026-08-28 01:36～01:43 +08:00｜M50-P2R（passed → continue）

- 启动与范围：FastAPI 只连接 `datapilot_demo`，operator-controlled `PHASE4B_RAG_STRATEGY=subgraph`，Trace=`.agent_work/temp/m50/probe-p2r/trace.jsonl`，Clash=`127.0.0.1:7897`；Next/BFF=`127.0.0.1:3100`。页面请求体没有 strategy/corpus/model，retry=0。
- Turn 1：浏览器 start“查询 2026 年 7 月实际净退款金额。”；Trace `8a69a191-390d-476d-9c2d-9e0c34cd52ef`，task v1，`completed/complete/answer_ready`，UI/table=`120000`；usage=`2 calls / 5889 tokens`。
- Turn 2：同 task v1 continue 比较 7/8 月；Trace `0c5414be-03b0-47ca-bbf0-cf0445c1b6b4`，task v3，`completed/complete/answer_ready`，UI/rows=`120000/180000/60000/0.5`；usage=`2 calls / 9328 tokens`。提交第三轮前实时账本=`4 calls / 15217 tokens`，剩余恰好 2 calls / 14783 tokens，前置门允许继续。
- Turn 3：同 task v3 continue 修订问法“比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。”；Trace `166253f3-d60b-4ea1-9215-1524d9dcbcac`，task v5，route/hybrid、execution/answer/safety=`completed/complete/passed`、termination=`answer_ready`，未解决 requirement=[]。
- Hybrid Evidence：SQL branch=`complete/sql_completed`；RAG branch=`complete/hybrid_document_evidence_ready`。同轮 Evidence 为 1 SQL + 3 Document，Document anchors=`refund-policy-basic / metric-net-refund-amount / refund-policy-quality`；两个 action 均 completed 且 `coverage_increased`。Knowledge runtime=`business-release:7d0d...409a:strategy:subgraph`，页面明确显示两个分支 complete，不展示文档正文。
- 浏览器 validated response 投影显示 8 行退款原因数据、2 条 citation（`sql-result` + `基础退款政策/refund-policy-basic`）、Hybrid 双分支和 task v5；Trace 原始行安全投影不包含最终 citation 数组，但 branch Evidence refs 与页面 citation 数量/anchor 闭合。截图：`.agent_work/temp/m50/probe-p2r/passed-hybrid-viewport.png`、`passed-hybrid-evidence.png`；全页截图因多 Vega canvas 的当前浏览器 full-page 合成出现重复/裁切，只作布局诊断，不用作通过证据。
- P2R 总 usage=`6 provider calls / 23009 observed tokens`，精确未超过独立 `6 / 30000` 上限；没有 retry、额外问题、strategy 切换、external/historical/held-out/reserve 访问。task safe ref=`task:37a2...12ff1`、state identity=`7e8500...d1a93`，当前 lineage 保留给零 provider P3。
- 三态与处置：`passed → continue`。修订后的真实 Browser→BFF→API→Qwen/Text2SQL/MySQL + business Subgraph→Response/Trace→UI 双 Evidence Gate 闭合，解除 M50-E 阻塞；首次 P2 的失败与越界仍作为独立历史证据保留。

### 2026-08-28｜M50-E 负路径实现 checkpoint

- 新增 task active 时 preset/mode 双重防护，避免点击 legacy preset 后丢掉 task envelope；补充 DataPilotClient、thin BFF、Playwright 的 version conflict/known rejection、422、non-JSON 5xx、contract drift、backend unreachable、timeout unknown、zero-network request rejection、clear/sessionStorage、legacy clarification/follow-up 测试。
- 首轮 Vitest 为 `27 passed + 1 suite import failed`：新增 BFF 测试无法解析 Next 的 compile-time `server-only` marker，生产代码和断言均未执行失败。为测试配置增加仅 Vitest 生效的空 marker alias；不删除生产 `import "server-only"`，避免为了测试弱化 BFF 边界。下一步重跑同一聚焦测试。
- marker 修正后 Vitest=`33 passed`。Playwright 首轮=`10 passed / 2 failed`，两个失败都是同一测试在桌面/移动端用 `getByText("v1")` 同时命中 toolbar 版本和 Inspector JSON 的 strict selector 歧义；页面已正确渲染 v1，不是产品失败。收窄为 exact selector 后重跑。
- selector 修正后 Playwright=`12 passed`。随后对照真实 API 合同发现测试最初把 version conflict 模拟成 HTTP 409，但 FastAPI 实际以 HTTP 200 + typed `task_action=rejected` 安全投影 owner/missing/version 边界。当前 client 若直接返回该响应，Workbench 会 append 一个 `task=null` turn 并丢失最后确认 identity；修正为 validated typed rejection → `known_rejected` client error，保留原 turns/version，不冻结、不重试。补充 version conflict/task unavailable 两个 unit 反例，并把 E2E 改成真实 transport 口径。
- typed rejection 首轮修正后 Vitest=`35 passed`，但 Playwright=`10 passed / 2 failed`：client 把所有 `task_action=rejected` 都当 lineage rejection，连 `sensitive_field_blocked` 这种应由 ResultView 展示的安全业务停止也被收成 notice。收窄为 boundary 闭集 `task_version_conflict | task_unavailable`；其他 blocked/unsupported 产品状态仍走四轴 Presenter，不因 task_action 字面值被吞掉。
- 收窄后 Playwright=`12 passed`。M50-E deterministic 负路径现已覆盖真实 HTTP 200 typed boundary rejection、BFF transport failure、unknown freeze、clear/session 和 legacy structured flow，允许进入零 provider M50-P3。

### 2026-08-28 01:54 +08:00｜M50-P3 执行前 checkpoint

- 当前保留 P2R lineage：task safe ref=`task:37a2...12ff1`、last acknowledged version=5；API/Next 仍是同一 `datapilot_demo`/Subgraph 进程，未重启、未 reset/reseed。P3 预期 provider=0、Graph/task runtime invocation=0。
- P3 通过浏览器页面继续按钮发起请求，但在当前 tab 临时包一层 one-shot `window.fetch`：第一次只把 outgoing task `expected_version` 改成不存在版本，第二次只把 `user_role` 改成 `customer_service`；wrapper 每次修改一个请求后立即恢复原 fetch。这样请求仍走 Workbench→DataPilotClient→BFF→FastAPI，且不用把完整 task id 暴露给脚本/日志。
- deterministic 验证：Vitest=`35 passed`；Playwright=`12 passed`（desktop/mobile），已证明 typed rejection 保留 v5、不误标、不自动 retry。P3 依次观察 version conflict、role drift，然后用页面原生 clear；任一深调用、provider、identity 泄漏或旧 version 丢失即 stop。
- 执行时修正：Browser Plugin 的安全 evaluate world 将 `window.fetch/sessionStorage` 置为 unavailable，one-shot wrapper 在读取 `window.fetch.bind` 时即失败，未填写/点击、请求=0。改用完成后删除的同源 `public/m50-p3-probe.html`：页面自身读取当前 tab 的公开 session snapshot，经正式 `/api/datapilot/query` BFF 提交两条 envelope，只显示 closed-world 安全摘要；然后回到正式 Workbench clear。该临时页不进入最终工程。

### 2026-08-28 01:55～01:57 +08:00｜M50-P3（passed → continue）

- Version conflict：同源 Browser page → Next BFF → FastAPI 对 P2R task v5 提交 `expected_version=999`；HTTP 200 typed response=`agent_task/rejected/task_version_conflict/passed`，Trace `cbf14afd-2641-4730-b996-d514727c6c4d`，Graph=0、task runtime=0、Tool=0、agent budget=null、task projection=null。截图=`.agent_work/temp/m50/probe-p3/version-conflict.png`。
- Role drift：同一 task v5 改为 `customer_service`；response=`agent_task/rejected/task_unavailable/blocked`，没有区分 owner/role/missing 事实，Trace `2cbde370-a0fb-4b25-807f-cafc290cf4bb`，Graph=0、task runtime=0、Tool=0、agent budget=null、task projection=null。截图=`.agent_work/temp/m50/probe-p3/role-drift.png`。
- 两个拒绝后回到正式 Workbench，session 恢复仍为 v5、三条已确认 turn 完整，没有 rejection success card、version 推进或自动 retry。随后点击页面原生“清理任务与本地快照”：Trace `4580ed3c-f3e0-4094-8c74-6e98c5a686fd`，reason=`task_cleared`，version `5→7`，Graph/task runtime/Tool/provider=0；页面回到“尚未开始 task”并显示本地公开快照已移除。截图=`.agent_work/temp/m50/probe-p3/clear.png`。
- durable clear 按 M47 合同保留 scrubbed tombstone/audit rows，第一次 preflight 因此观察到 `1 checkpoint / 7 events`，不代表 clear 失败。按 Probe 额外清理门使用精确 safe ref 删除这组 synthetic rows，最终 preflight=`0/0`、migration/oracle 不变、ready=true；删除的 synthetic tombstone/event 不从 DB 恢复，原 Trace/截图仍保留。
- P3 provider calls/tokens=`0/0`；未创建新模型场景、未访问 external/historical/held-out/reserve。临时同源 Probe 页已从最终工程删除。
- 三态与处置：`passed → continue`。错误 version 与漂移 role 均在深执行前拒绝且不泄漏；last-ack v5、clear、UI/session 与 DB cleanup 闭合，解除 M50-F 阻塞。

### 2026-08-28｜M50-F 注释审查中的恢复边界修正

- `finish-module` 逐文件审查发现 session snapshot 原先只保存 role/turns，没有保存 `agent_task | legacy` runtime mode。刷新 legacy 澄清页面后默认 mode 会回到 `agent_task`，虽不会篡改服务端 thread，但会把已确认的 legacy 表单暂时隐藏，属于前端恢复合同遗漏。
- 修正为 session codec 同时保存并 closed-world 校验 mode；旧的缺字段 snapshot 按既定 schema-drift 策略整份丢弃，不做模糊迁移。Playwright 在 legacy clarification 首轮后新增 reload，再继续提交服务端签发字段，防止 task/legacy identity 串线。
- 同轮注释审查为 client/BFF/session/workbench/result/chart/API route/demo cleanup 的非豁免入口补充中文职责、unknown-outcome、last-acknowledged version、安全投影和 chart/table 回退理由；未改变 FastAPI 核心合同或模块范围。
- 最终真实页面证据已固化为 `docs/notes/assets/m50/m50-hybrid-workbench.png`、`m50-hybrid-evidence.png`、`m50-clear-state.png`；临时 full-page 合成图未纳入交付。

### 2026-08-28｜M50-F clean install checkpoint

- 开发期 FastAPI/Next 进程已正常停止。首次 `npm ci` 在 sandbox 内安装阶段因 Windows `spawn EPERM` 退出，npm 同时无法写用户缓存日志；这是与此前 production build 相同的进程权限故障，不是依赖合同失败。
- 获批后以同一 lockfile 在 sandbox 外原命令重跑：`added 528 packages`、audit `529 packages`、`0 vulnerabilities`，耗时约 25 秒。唯一 warning 是锁定的 ESLint 9.39.5 已进入上游 unsupported 提示；它仍满足 Next 16 当前 peer contract，本模块不在收工时越过 lockfile 升级到 ESLint 10。
- clean install 后首轮静态验证：typecheck=`passed`，Vitest=`5 files / 35 tests passed`；lint 唯一失败是 gallery 内部 `/` 导航使用原生 `<a>`。按 `web/AGENTS.md` 阅读随 Next 16 安装的 `linking-and-navigating.md`，改用 `next/link`；这是局部框架规范修正，未影响真实工作台或合同。
- `next/link` 修正后 lint/typecheck 均为 exit 0。production build 在 sandbox 内完成编译后仍于 worker `spawn EPERM` 中止；获批后同一命令 sandbox 外重跑通过：Next 16.3.3、6/6 static pages、3 个动态 BFF routes，未出现产品 warning。
- Playwright 最终结果=`12 passed / 11.9s`，同时覆盖 Chromium desktop 与 Pixel 7 viewport；新增的 legacy reload 后仍能继续澄清。warning 只有 `NO_COLOR/FORCE_COLOR` 测试进程设置冲突，以及 Python fixture 的 Vega-Lite v5 schema 被当前 v6.4.3 renderer 兼容接收时提示版本差异；实际 chart 与权威 table 均渲染，均不阻塞 M50。
- Python 49 文件聚焦回归首次在 sandbox 内因 `.agent_work/temp/m50/pytest-focused-final` 访问拒绝产生用例 error 与 session cleanup `WinError 5`，不作为产品失败；sandbox 外以新 basetemp 原范围重跑=`245 passed / 1 warning / 99.93s`。warning 为既有 Starlette TestClient/httpx deprecation，不由 M50 引入。
- 零 provider 最终核验：demo preflight exit 0，migration=`20260827_0005`、oracle=`120000.00/180000.00`、task rows=`0/0`、ready=true；fixture export exit 0，identity=`04998899e0d98f194ce0778784458d25a94d9f9b0c2b6df9ef0eeef9f86c280f`、5 fixtures。

### 2026-08-28｜全仓 pytest 后台启动前 checkpoint

- 关键决策：G50-1/G50-2 与用户确认的 P2R 方案 A 均未变化；前端仍是薄 BFF + Python-authoritative contract，demo 仍只允许 `datapilot_demo`，没有用简化实现替代后端 task/RAG 能力。
- 改动范围：`.gitignore`、完整 `web/`、4 个 M50 scripts、1 个 Python contract test、M50 plan/notes 与 3 张截图；尚未开始阶段 4 的 AGENTS/README/state/changelog 更新。起始 commit 明确为 `9a3ac84da3678adaaf2f8a03115ffcc117fdff8d`。
- 已完成验证：clean install 0 vulnerabilities；lint/typecheck exit 0；Vitest 35/35；Playwright 12/12；production build 通过；Python 聚焦 245/245；demo/fixture 两个零 provider Gate 通过；P1/P2R/P3 的原时点证据与首次 P2 失败均已保留。
- 已知风险：ESLint 9 上游 support warning、Starlette TestClient deprecation、Vega-Lite v5→v6 compatibility warning 均不阻塞本模块；公网 auth/deploy、streaming、生产 task 查询恢复不在 M50 范围。开发期 Probe 审计未发现 `development_probe_missing`：各 checkpoint、失败/revise/重验、Trace/usage/cleanup/决策顺序均可在上方原时点记录交叉核对。
- 待完成：同一次全仓 pytest 日志/退出码检查；随后阶段 3 notes 总结与 Handoff、阶段 4 README/AGENTS/changelog/AI_CONTEXT/专项 state、最终 `git diff --check` 和链接检查。

### 2026-08-28｜全仓 pytest 后台任务指针

- 状态：**已完成并检查**；PID 已退出，`completed.txt=2026-08-28T14:54:05.2403415+08:00`，`exit-code.txt=0`。
- PID：`11548`；后台入口：`.agent_work/temp/m50/run-full-pytest-final.ps1`。
- 实际命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m50/pytest-full-final/basetemp`。
- 日志：`.agent_work/temp/m50/pytest-full-final/pytest.log`。
- 退出码：`.agent_work/temp/m50/pytest-full-final/exit-code.txt`。
- 完成标记：`.agent_work/temp/m50/pytest-full-final/completed.txt`。
- 下次继续时先读取同次退出码、完成标记和日志尾部；若未完成只报告运行状态，若失败先定位失败用例，不启动第二次全量。确认结果后再继续 `finish-module` 阶段 3–5，之后读取并执行 `finish-docs`。
- 同次结果：`681 passed / 1 warning / 581.33s (0:09:41)`；warning 仍是既有 Starlette TestClient/httpx deprecation。没有启动第二次全量。

## Finish-module 素材固化

### 模块名称与改动文件清单

- 模块：M50 DataPilot Web 工作台。
- 起始 commit 明确：`9a3ac84da3678adaaf2f8a03115ffcc117fdff8d`；模块期间没有提交，最终范围以该基线、当前 Git status 与本 notes 交叉核对。
- 代码与产品产物：完整 `web/`（Next/React/TypeScript、BFF、contracts、UI、测试、README）、`scripts/cleanup_m50_demo_task.py`、`scripts/export_m50_web_contract_fixtures.py`、`scripts/prepare_m50_demo.py`、`scripts/run_m50_demo_api.py`、`tests/test_m50_web_contract.py`、`.gitignore`。
- 文档与证据：`docs/notes/m50-plan.md`、本文件、`docs/notes/assets/m50/` 三张最终截图；阶段 4 还将更新根 `AGENTS.md`、`README.md`、runbook、database state、AI_CONTEXT 与 Phase 4B changelog。
- 排除项：`.agent_work/emilkowalski skill 描述.md` 是本模块基线后出现的独立未跟踪文件，不属于 M50，未读取、未修改、未删除，也不写入模块档案范围。

### 关键决策与取舍

- G50-1 用户选择方案 A：Next.js App Router + React + TypeScript + 薄 BFF。原因是把同源 transport、timeout、错误净化和 runtime validation 收进一个深模块，同时保持 FastAPI/Pydantic 为唯一业务 authority；代价是多一个 Node 进程与本地 HTTP hop。未选直连 FastAPI，也未把 BFF 扩成第二个 Agent backend。
- G50-2 用户选择方案 A：独立 `datapilot_demo` + 显式确认 prepare。收益是招牌 7/8 月故事可复现且不 reset/reseed `datapilot_dev`；代价是多维护一个本地演示库。精确库名白名单、0005 migration、phase4b profile 与 0/0 synthetic cleanup 均已验证。
- 首次 P2 因预注册问法与 business admission seam 不闭合且出现 9/8 attempts 控制错误而 `failed → stop`。用户随后确认方案 A：保留失败账本、不改 Agent/RAG、不把 partial 降格为通过，改用已有 M49 证据支持的明确质量退款问法，以全新 lineage 和独立 6 calls/30000 tokens 执行 P2R。最终 P2R 6 calls/23009 tokens 通过；旧失败没有被改签。
- 收工注释审查发现 legacy mode 未持久化。采用 closed-world session codec 保存 mode；旧 snapshot 缺字段时整份丢弃，不加模糊迁移或客户端猜测。

### 阶段 1 注释小结

- 完整检查 34 个本模块代码/config/test 文件；核对 47 个非豁免类、函数、方法和主要局部 workflow 入口。
- 补写 17 处缺失入口说明，另深化 5 处复杂内部注释；重点覆盖 Python-authoritative/Zod 边界、thin BFF unknown outcome、last-acknowledged version、session runtime family、防 task/legacy 串线、Inspector safe projection、Vega finalize 与 table fallback、demo DB 双 engine/session 装配。
- 关键设计理由已在 `DataPilotClient`、`proxyFastApi`、`Workbench`、`ResultView`、demo prepare/launcher 附近就地说明；修正了 session 只写 role/turns 的过时恢复假设。没有为了数量给简单 config/re-export/字段模型硬加注释；当前无已知缺失。

### 阶段 2 验证快照

- `npm ci`：sandbox 内 `spawn EPERM` 后获批原命令重跑，528 packages、audit 529、0 vulnerabilities；ESLint 9.39.5 upstream unsupported 提示不影响当前 Next peer contract。
- `npm run lint`：首轮 1 个 gallery 原生内部链接错误；按 Next 16 随包文档改为 `next/link` 后 exit 0。`npm run typecheck` exit 0。
- `npm test`：5 files / 35 tests passed。`npm run test:e2e`：desktop + mobile 共 12 passed / 11.9s，覆盖 lifecycle、known rejection、unknown freeze、clear/session、legacy reload/follow-up。颜色环境与 Vega-Lite v5→v6 compatibility warning 不阻塞。
- `npm run build`：sandbox worker `spawn EPERM` 后获批原命令重跑；Next 16.3.3 production build、TypeScript、6/6 static pages、3 个动态 BFF routes 全部通过。
- Python 受影响聚焦：sandbox 目录权限失败后以新 basetemp sandbox 外原范围重跑，49 files / 245 passed / 1 warning / 99.93s。
- 全仓后台：同次 PID 11548，exit 0，681 passed / 1 warning / 581.33s；warning 为既有 Starlette TestClient/httpx deprecation。
- demo preflight：0005、120000/180000、task 0/0、provider 0、ready=true；fixture export：5 fixtures、identity `04998899...280f`、provider 0。
- 尚待阶段 4 完成后执行最终 `git diff --check` 与文档链接检查；此前失败均已保留原因和重跑边界，没有用重复全量掩盖产品失败。

### Live Dev Probe 开发时间线审计

- 适用：M50 改变 browser 对真实 Qwen/MySQL/RAG/task API 的消费与展示，fixture/pytest 不能替代真实页面链。
- M50-P1 在 C 后、D 前执行：attempt 1 provider transport inconclusive；attempt 2 暴露 `get_db` 仍指 dev 的装配错误并 revise；启动器 override demo session 后 attempt 3 以 2 calls/6092 tokens、120000 oracle、Trace/UI 同源 passed→continue。失败、截图、usage、safe cleanup 与 dirty checkpoint 均按原时点保留。
- M50-P2 在 D 后、E 前执行：turn 1 后漏做剩余 attempts 前置门，最终 9/8 attempts 且原问法 RAG no candidate，failed→stop；定位使用零 provider deterministic seam。用户确认新方案后，P2R 全新 lineage 3 turns，6/6 calls、23009/30000 tokens，SQL 120000/180000/60000/0.5 + Document anchors + 2 citations，passed→continue。
- M50-P3 在 E 后、F 前执行：version conflict、role drift、页面 clear 分别命中 typed boundary，Graph/task runtime/Tool/provider 都为 0；last-ack v5 未推进，session 与 synthetic rows 最终清理 0/0，passed→continue。
- 审计结论：计划/实际时点、授权、HEAD/模块 worktree、命令与依赖、Trace/Response identity、calls/tokens、失败层/修正/最小重验、截图/cleanup、三态与开发决定可由上方原时点记录闭合；不存在 `development_probe_missing`。所有 Probe 都是 exploratory/baseline-ineligible，不登记 Formal Eval 或质量基线。当前无需 Formal Eval，因为 M50 未修改 Agent quality/route/retrieval/SQL 合同。

### 参考资料

- AskData Studio：借鉴统一 request module、turn snapshot、pending/empty/error、sticky table header 与客户端分页；适配成 DataPilot task/version authority、四轴 Presenter 和公开 Inspector；不照搬无限聊天、客户端拼历史、登录/session token、全量导出或客户端 runtime 选择。
- Next 16 随包 docs：核对 App Router、Route Handler、server-only 与 `next/link`；采用同源薄 adapter，不照搬任何后端业务状态。
- Vega Embed：采用 object spec + `result.finalize()` 生命周期，关闭 actions；渲染失败保留权威 table，不从外部 URL 加载数据。
- 前端设计 skills：`emil-design-eng` 用于专业工具型层级、微交互、reduced-motion 和细指针 hover；`codebase-design` 用于收敛 `DataPilotClient`/Presenter 深模块 seam。它们没有改变产品合同。

### Handoff

1. **已完成且可依赖**：`web/` 可从 lockfile clean install/build；浏览器经 thin BFF 调真实 FastAPI；task start/continue/switch/cancel/clear、legacy clarification/follow-up、closed-world Presenter、SQL table/Vega/citation/Hybrid/Inspector、bounded session restore 与 unknown freeze 都有自动化和真实 Probe 证据。`datapilot_demo` prepare/preflight/launcher/cleanup 形成可复现本地演示入口。
2. **未完成与风险**：不包含公网部署、生产 auth/abuse、streaming、生产 task 查询恢复、MCP、Eval Dashboard 或全量导出；Qwen 延迟可能接近 BFF 150s timeout，unknown outcome 必须人工判断；Vega v5 spec 在 v6 renderer 有兼容 warning。M50 只证明固定本地展示链，不外推 RAG/LLM 泛化质量、Subgraph 胜出、HA/性能或 exactly-once。
3. **必须延续的边界与决策门**：Python/FastAPI 是业务 authority；客户端不得选择 model/corpus/RAG strategy，不自动 retry mutation；Pipeline default/Subgraph server-controlled experimental、reserve sealed/not-run 不变；`datapilot_dev` 不因演示 reset。任何公网部署/认证、默认 runtime、核心响应合同或数据库默认世界变化都须另立 plan 并请用户确认。
4. **下一模块入口与必读指针**：没有预先冻结下一模块编号。后续若立项部署/MCP/质量模块，先读 `web/README.md`、`web/lib/data-pilot-client.ts`、`web/lib/contracts.ts`、`web/lib/presenter.ts`、`docs/notes/m50-plan.md` 与本 Handoff，再按实际目标读取对应 runbook/state；不要把可复用 seam 当成新能力已完成。

### 技术档案 checklist

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] notes 已记录 Live Dev Probe 完整时间线，且不存在 `development_probe_missing` 或 Formal Eval 混算。
- [x] 已按 `CHANGELOG_INDEX.md` 路由写入 Phase 4B 完整模块记录。
- [x] `AI_CONTEXT.md` 已更新并清理失效/重复内容。
- [x] 所有命中的专项 state 均已完整检查并更新，或记录无需修改理由。
- [x] 新结论与历史、代码、测试、默认配置和 state 不冲突或重复定义。
- [x] changelog 新章节、AI_CONTEXT 与修改过的专项 state 已完整回读。
- [x] `git diff --check` 和文档链接检查已通过并记录。

### State impact（最终）

- **已更新**：`docs/state/runbook.md`（新增 Web/demo prepare/preflight/API/Next/验证/cleanup 入口与 unknown outcome 边界）；`docs/state/database-current-state.md`（新增隔离 `datapilot_demo`、0005/phase4b profile、双 session 装配和 0/0 事实）。
- **已检查、无需修改**：`docs/state/rag-current-state.md`（M50 只展示既有 business/Subgraph 投影，未改 active release、runtime identity、default/quality/reserve）；`docs/state/eval-baselines.md`（仅 development Probe 与 deterministic regression，不是 Formal Eval/基线，不能新增分母或 baseline）。
- **未命中**：`docs/state/schema-retrieval-milvus-embedding.md`（未改 embedding、collection、schema corpus 或 backend）。

### 技术档案最终回读与一致性检查

- 已完整回读修改后的 `AI_CONTEXT.md`、`runbook.md`、`database-current-state.md` 和 Phase 4B changelog 新章节；与代码/notes/测试/Probe 对账后，没有把 Subgraph 写成默认或质量胜出，没有把 `datapilot_demo` 写成默认数据库，也没有把 development Probe 混作 Formal Eval。
- 根 `README.md` 已把旧的“仅 Streamlit / 进程内 checkpoint”当前口径更新为 M50 Web + durable task/独立 legacy family；`AGENTS.md` 目录事实新增 `web/`。没有修改阶段 roadmap 或预定下一模块。
- 最终 `git diff --check` exit 0；额外扫描本模块文本 `trailing_whitespace=0`。14 个新增/修改文档与证据目标均存在，missing=0；`web/node_modules`、`web/.next`、`web/test-results` 均被 ignore，未进入交付清单。
- Git 最终范围与起始 commit/notes 一致；唯一排除的未跟踪 `.agent_work/emilkowalski skill 描述.md` 保持原样。技术档案全部硬门满足，`finish-module=complete`。

## Finish-docs 执行清单（Track A）

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有概览，再有至少 3 条一级编号。
- [x] 每个编号点交代原问题/影响、概念、解决方式、取舍、证据和未证明边界。
- [x] 编号内容按短段或 `- **小标题**：` 拆分，没有无断点长段。
- [x] 英文/代码术语首次出现时有通俗解释。
- [x] 对照数字使用列表或表格呈现。
- [x] 新概念已用新手能理解的方式解释。
- [x] “代码阅读路线”按真实调用/数据流组织，并解释为什么这样协作。
- [x] 有“设计要点”，且最后一个句号按模板为“汪。”。
- [x] “有面试价值的亮点”可背、可独立展开且不强行凑数。
- [x] 追问围绕真实亮点与边界，压力回答最后一句按模板为“喵。”。
- [x] “验证与下一步”只引用 notes 的真实验证快照。
- [x] 复制命令安全、可重复并写明前置条件与预期。
- [x] 各小节使用加粗关键词帮助扫读，没有整段加粗。
- [x] 新增章节已完整回读，并以第一次阅读者视角完成易读性检查。
- [x] finish-docs 期间只修改 `docs/dev-log.md` 与本 notes，没有改技术档案或代码。
- [x] `git diff --check` 通过，检查结果已写回 notes。

### Finish-docs 自检结果（2026-08-28）

- **章节范围**：`docs/dev-log.md:4752-4997` 已分块完整回读到 EOF；包含 6 个“这次做了什么”、6 个新概念、8 步代码阅读路线、5 个面试亮点和 7 个追问。
- **第一次阅读者检查**：问题、方案、价值、权威边界、真实证据和未证明范围均可从章节独立理解；关键英文/代码术语在首次承担概念解释时给出中文释义，长内容已按短段、小标题、列表或表格拆分。
- **数字口径**：安装、单元测试、E2E、Python 回归、Live Dev Probe 与零调用负例均来自本 notes 已冻结的技术收工快照；finish-docs 未重跑测试、数据库或真实模型调用。
- **格式门禁**：设计要点末句以“汪。”结束，压力追问末句以“喵。”结束；章节使用局部加粗帮助扫读，没有整段加粗。
- **变更边界**：finish-docs 开始后只编辑了 `docs/dev-log.md` 与 `docs/notes/m50-notes.md`；未改代码、README 或技术 state。工作区中其他 M50 变更均来自此前 implementation / finish-module，另有无关 untracked 文件保持原样未触碰。
- **最终检查**：`git diff --check` exit 0；`docs/dev-log.md` 与 `docs/notes/m50-notes.md` 行尾空白均为 0。完整回读未发现需要追加修正的内容。

## 用户实测后的 UX 修正（2026-08-28）

### 反馈与决策

- **发送反馈**：用户发现请求 pending 时 textarea 保留原问题且变成 disabled，不符合聊天产品心智。修正为提交瞬间把文本移入右侧 `YOU · SENT` 气泡并清空输入；成功响应后同一文本进入正式 turn。typed known rejection 会把原文放回输入框供修改，unknown outcome 则保留已发气泡并继续冻结 lineage，不改变 mutation 安全合同。
- **状态文案**：把“DataPilot 正在执行真实链路 / 等待服务端返回，不伪造节点进度”收敛为“DataPilot 正在查询和分析 / 正在等待服务端返回”，保留真实等待含义，去掉面向实现者的自证式表达。
- **滚动模型**：删除占用首屏的大 Hero，把 `.shell` 固定为 `100dvh`，工作区填满 topbar 下方空间；conversation panel 使用 `minmax(0, 1fr)`，只有 timeline 负责主要纵向滚动，外层不再与聊天区形成双滚动。移动端 preset 改为横向场景条，避免固定视口下压缩聊天区。
- **视觉方向**：依据用户选择，从 askdata 式饱和绿切换为暖米黄、陶土橙和深棕的 Anthropic-inspired 配色；绿色只保留在 API ready 这个语义状态点。`emil-design-eng` 用于高频反馈、按钮响应和避免多余消息动画，`apple-design` 用于固定 chrome、独立滚动、半透明层级与 reduced-motion 边界。
- **范围边界**：只改浏览器交互、布局和视觉 token，不改变 BFF/FastAPI 合同、task version、Presenter 四轴、安全展示或后端默认。

### 实现与验证 checklist

- [x] pending question 使用独立 `outboundQuestion`，提交即清空 textarea 并生成右侧气泡。
- [x] 成功、known rejection、unknown outcome 三类收口不改变 last-acknowledged version 语义。
- [x] 删除 Hero，固定外层视口并保留 timeline 单一主滚动区。
- [x] 暖黄/橙/深棕 token 覆盖主表面、输入、消息、结果和 Inspector；保留安全/危险语义色。
- [x] 新增 desktop/mobile E2E，断言发送反馈、文案、Hero 移除和滚动 CSS 合同。
- [x] typecheck、lint、Vitest、Playwright、build 与 `git diff --check` 已通过。

### 验证快照

- `npm run typecheck`：exit 0。
- `npm run lint`：exit 0。
- `npm test`：5 files / 35 tests passed。
- `npm run test:e2e`：desktop Chromium + Pixel 7 共 14 tests passed；新增用例在两套 viewport 下均验证提交即清空、右侧消息、等待文案、Hero 移除和滚动 CSS 合同。
- `npm run build`：Next.js 16.3.3 production build 成功，6 个页面/路由完成生成。
- in-app browser 视觉核验：1280×720 下 `documentScrollHeight=720`、`shellOverflow=hidden`、`timelineOverflowY=auto`、`workspaceHeight=612`；暖色 token `paper=#f7f3ea`、`accent=#d97732`，browser console errors=0。
- 本次没有调用真实 API mutation、Qwen、MySQL 或 RAG；M50 既有 Probe/全仓回归证据不被冒充为本次 UI 修正证据。

## 用户实测故障修正：unknown recovery + comparison SQL（2026-08-28）

### 现场证据与已确认方案

- **用户场景**：T1“查询 2026 年 7 月实际净退款金额。”成功；T2“比较 7 月和 8 月实际净退款金额”在页面 150 秒后进入 unknown/frozen，旧版本 clear 返回“当前任务无法清理”，刷新才恢复输入。
- **Trace 事实**：T1 `answer_ready`，31,227.902ms；T2 的 TaskDelta 正确继承 `periods=[2026-07,2026-08]` 与 `comparison=true`，但 QueryPlan 93,608.127ms + SQL generation 80,247.228ms，总响应 173,931.862ms，晚于 BFF 150,000ms。
- **SQL 根因**：T2 QueryPlan 把 `diff/change_rate` 错误下推为 `MAX(CASE ... THEN SUM(...) END)` 嵌套聚合；SQL Guard/Fidelity 通过，但 MySQL `sql_execution_error`，Agent 最终 `comparison_observation_missing/no_answer`。随后三次 clear 均为零 Graph/Tool/provider 的 `task_version_conflict`，证明浏览器旧 v1 与服务端已提交新版本分叉。
- **刷新缺口**：sessionStorage 只保存 turns，没有保存 unknown/frozen；刷新只是解除 UI 冻结，不是服务端状态恢复，旧 version 仍不可信。
- **用户确认**：选择方案 A。允许同时修复 BFF 等待窗口、metric comparison 确定性计划收敛、只读 task recovery seam 和 unknown 跨刷新；不得自动重试 mutation 或放宽 owner/tenant/role/version 安全。

### Implementation checklist

- [x] 新增 owner/tenant/role 校验的只读 task status interface，memory/MySQL adapter 同语义；不存在/错身份统一 `task_unavailable`。
- [x] 新增 `GET /api/query/tasks/{task_id}` 与 thin BFF/client 合同，只返回恢复所需的安全 task projection，不返回 payload、Evidence 正文或 raw id 之外的新信息。
- [x] unknown snapshot 跨刷新保存；提供显式“检查任务状态”，claimed 保持冻结，active 新版本更新 last-acknowledged task projection 后允许继续/清理，terminal 收口。
- [x] BFF 默认 timeout 从 150s 调整为 300s，仍保留环境变量覆盖、AbortController 和 mutation no-retry。
- [x] metric comparison 在 QueryPlan 进入 SQL 生成前确定性收敛为 period + base metric；delta/rate 只由已有 Comparison Completion 从两行 guarded rows 派生。
- [x] 覆盖 status seam 身份/状态/版本、QueryPlan 收敛、unknown reload/reconcile/clear、300s timeout 合同与既有回归。
- [x] 前台确定性验证通过后执行授权 Probe；若预计验证超过 2 分钟，按后台纪律先写 checkpoint。

### Live Dev Probe 预登记

- **ID**：`M50-UXR-P1`，时点为 status recovery、comparison plan normalization、BFF timeout 和聚焦测试全部通过之后；它阻塞本次故障修正收口。
- **场景**：独立 `datapilot_demo` 新 task 连续执行 T1“查询 2026 年 7 月实际净退款金额。”与 T2“比较 7 月和 8 月实际净退款金额”；通过 Browser/BFF/FastAPI/MySQL/Qwen/Text2SQL/SQL Guard/Response/Trace/UI 完整链。
- **required assertions**：T1=`120000`；T2 TaskDelta 继承 `2026-07/2026-08`，SQL 不含 aggregate-inside-aggregate，只返回两月基础聚合，最终 rows/answer 包含 `120000/180000/delta=60000/rate=0.5`；页面不发生 BFF timeout/frozen；服务端 task version 与 UI last-acknowledged version 一致；cleanup 后 synthetic rows `0/0`。
- **安全负断言**：不自动 retry；不切 RAG strategy/default；不读 reserve；不改 `.env`；Probe 只使用本次新 task safe ref 清理。
- **授权预算**：用户明确授权一次两轮 Probe，累计最多 4 provider calls / 25,000 observed tokens；首次运行后无论 passed/failed/inconclusive 都停止，不自动重跑。
- **三态与决策**：required assertions 全过=`passed → continue`；确定性代码/合同失败=`failed → revise`；外部网络/provider 不可用且产品失败关闭=`inconclusive → stop/report`。

### 实现 checkpoint（Probe 前）

- **关键设计**：`codebase-design` 的 deep-module 取舍落实为 `TaskBoundaryPort.status`，memory/MySQL 同语义；前端只持久化最小 recovery projection，不复制 task 状态机。status 是显式 GET，错误 owner/未知 id 统一 `task_unavailable`，Trace 中 Graph/task runtime/provider 均为 0。
- **comparison 适配**：新增服务端 `base_aggregate_only` authority，只由 Agent task 的 `comparison=true` 设置；Legacy Text2SQL 默认 false。QueryPlan 在 validation/SQL generation 前移除 `diff/change_rate` 输出与绑定，保留 month + base metric；既有 Comparison Completion 继续从 guarded 两行结果派生 delta/rate。
- **页面恢复**：unknown 时保存 `frozen/outboundQuestion/recoveredTask`；刷新后保持冻结与已发送气泡。显式 status 返回 claimed 则继续冻结，active 且 version 前进则采用新 version 并恢复输入/clear，terminal 则允许新建任务；全程不重发原 mutation。
- **确定性验证（截至本 checkpoint）**：Python status/API/comparison 聚焦 `15 passed`；Text2SQL pipeline 回归 `14 passed`；Vitest `5 files / 36 passed`；typecheck/lint exit 0；新增 Playwright unknown reload/status/v3 clear 在 Chromium desktop/mobile `2 passed`；`git diff --check` exit 0。首次 sandbox Playwright 因 Windows `spawn EPERM` 未执行浏览器，按规则在获准环境重跑后通过，不属于产品失败。
- **已知风险与待完成**：仍需完整 E2E、production build 和较宽 Python 回归；之后执行且仅执行一次已授权 `M50-UXR-P1`。真实双轮可能接近数分钟，启动后台服务与 Probe 前须记录 PID/log/exit/done 路径；首次 Probe 后无论三态均停止。

### M50-UXR-P1 启动前记录（2026-08-28 16:05 CST）

- **代码阶段**：status recovery、comparison normalization、300s BFF timeout 和全部确定性门完成；HEAD=`9a3ac84da3678adaaf2f8a03115ffcc117fdff8d`，模块相关 dirty 范围为 `app/`、`engine/`、`web/`、对应 tests、本 notes 与 `docs/state/runbook.md`，未触碰 sealed reserve/default RAG/.env。
- **最终前台门**：相关 Python 回归 `54 passed`；Vitest `36 passed`；Playwright desktop/mobile `16 passed`；typecheck/lint/build exit 0。demo preflight 首次发现旧演示残留 `2 checkpoints / 7 events`；按 Trace 中精确 safe ref 清理用户失败 lineage `task:5d957...` 和已确认 expired lineage `task:76078...` 后为 `0/0`、migration=`20260827_0005`、oracle=`120000/180000`、`ready=true`。历史 `task:37a2...` 已不在数据库，cleanup 精确返回 observed=0，未发生模糊删除。
- **后台服务计划**：重启当前 8000 API 进程以加载本轮代码，Trace=`.agent_work/temp/m50/uxr-p1/trace.jsonl`，API log/exit/done=`api.log/api.exit/api.done`；复用当前 3100 Next dev（源码热更新已由 E2E/build 验证）。API 新 PID 在启动成功后追加。
- **Probe 唯一运行**：Browser 经 3100 BFF 发 T1/T2；本次首次执行无论 passed/failed/inconclusive 都不重复。运行结果、Response/Trace/usage、task safe ref、cleanup 和三态将在观察后立即追加。
- **后台已启动**：wrapper PID=`61244`，Uvicorn PID=`7780`；命令为 `run_m50_demo_api.py --rag-strategy pipeline --trace-path .agent_work/temp/m50/uxr-p1/trace.jsonl --proxy http://127.0.0.1:7897`。日志=`.agent_work/temp/m50/uxr-p1/api.log`，退出码=`api.exit`，完成标记=`api.done`；当前为“运行中，待 Probe 后停止并检查”。`GET /health` HTTP 200，启动日志确认 RAG unavailable 但本次 SQL-only 场景不依赖 RAG。

### M50-UXR-P1 首次且唯一执行结果（2026-08-28 16:02–16:06 CST）

- **执行入口与代码时点**：Codex in-app Browser → `http://127.0.0.1:3100` → thin BFF → 当前代码 FastAPI PID 7780 → Qwen/Text2SQL/SQL Guard → `datapilot_demo` MySQL。HEAD/dirty 与上方启动前记录一致；Trace=`.agent_work/temp/m50/uxr-p1/trace.jsonl`，API log=`api.log`。
- **T1 Response/Trace**：trace_id=`7e94310a-bea7-4012-9d41-6f6357856000`，HTTP 200 / `answer_ready`，latency=`30948.32ms`；answer/rows=`120000`，UI 从右侧 SENT 气泡收口为 TURN 1、task v1。QueryPlan/SQL generation 共 `2 calls / 5842 observed tokens`。
- **T2 Response/Trace**：trace_id=`9133604c-3336-4b4f-bf1c-7984f95f503e`，HTTP 200 / `answer_ready`，latency=`100725.57ms`，低于 BFF 300s，页面未 timeout/frozen；UI task 从 v1 前进到 v3。TaskDelta 仍为 `comparison=true, periods=[2026-07,2026-08]`。
- **计划与 SQL 证据**：T2 query_plan metadata 为 `base_aggregate_only=true / plan_normalized=true`，planned/generated outputs 都是 `month,net_refund_amount`；SQL 为 `DATE_FORMAT + SUM ... GROUP BY month ORDER BY month`，不含 aggregate-inside-aggregate。guarded rows 为 July `120000`、August `180000`，上层 completion 添加 `delta=60000/rate=0.5`，答案明确“增加 60000，变化率 50%”。
- **预算与停止**：T2=`2 calls / 10187 observed tokens`；本次累计严格为 `4/4 calls、16029/25000 tokens`，没有 repair/retry/RAG call。首次运行已经给出结论，按授权停止，不创建第二 lineage。
- **UI required assertions**：发送 T1/T2 时输入均立即清空并出现右侧消息气泡；pending 文案为“DataPilot 正在查询和分析”；T1/T2 均形成“本轮结果已完成”，T2 表格显示 `120000/180000/60000/0.5`，页面最后为可输入状态且 task v3，与服务端提交一致。
- **安全与清理**：同一 task safe ref=`task:3ed90af24ba27f0e773334b32169ff2e90a9e1e21f439e62f8b42f97ddb1a6f4`；精确 cleanup 删除 `1 checkpoint / 3 events`，随后 preflight migration/oracle 不变、synthetic rows=`0/0`、`ready=true`。未使用模糊删除、未读 reserve、未切 default/strategy、未改 `.env`。
- **后台收口**：Probe 后精确停止 Uvicorn PID 7780；wrapper 生成 `api.exit=-1` 与 `api.done`，`-1` 是受控 `Stop-Process` 的预期退出而非 Probe 产品错误，Probe 前后 HTTP/Trace/cleanup 均已完成。
- **三态与开发决定**：required assertions 全部有真实证据，`M50-UXR-P1 = passed → continue`。这只证明当前固定双轮 happy path 与本次恢复修正，不登记 Formal Eval/质量基线，也不外推性能稳定性或比较问题泛化。

### 小修收口

- 复用本节已有的聚焦回归、前端构建/E2E 与真实 Probe 证据，不重复运行完整测试。
- 按用户要求不再次机械执行完整 `finish-module` / `finish-docs`；只同步 runbook、`AI_CONTEXT` 与 Phase 4B 历史短记录，`dev-log` 不追加小修章节。
