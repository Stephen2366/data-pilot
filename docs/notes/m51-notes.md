# M51 TypeScript MCP Adapter 开发记录

> 当前状态：技术收工完成
>
> 起始 HEAD：`fb77479d46771d97f948be29ffcd3ce271c3ea7f`
>
> 当前 plan：`docs/notes/m51-plan.md`

## Implementation checklist

- [x] 建立 root npm workspace、`mcp/` 工程和 Web/MCP 共用的 `@datapilot/contracts` 网络合同包。
- [x] 使用官方 MCP TypeScript SDK v2 建立本地 stdio server，只注册 `data_pilot_query` 一个 Tool。
- [x] 实现 loopback-only、固定 `ops` fixture caller、单次 HTTP、310 秒 timeout、redirect 拒绝、mutation retry=0 与安全错误映射。
- [x] 实现 query/task status/task clear、typed rejection、unknown outcome 与显式版本对账。
- [x] 实现 bounded projector：字段 allowlist、20 列 × 50 行、单 cell 2 KiB、16 citations、总 structured output 64 KiB，并返回 truncation metadata。
- [x] 完成 schema/config/HTTP/projector、SDK in-memory 与 spawned stdio 测试。
- [x] 完成 `M51-P1` SQL 纵向链与 `M51-P3` 安全/lifecycle Probe，并清理 synthetic task 行到 `0/0`。
- [x] 按用户确认，将尚未建立的真实 policy RAG/Hybrid MCP 路径移至后续 `M51R`；M51 不宣称该能力完成。
- [x] 补齐 `mcp/README.md`、AGENTS 目录结构和 runbook 入口。
- [x] 删除为已结束诊断 campaign 编写的专用 runner/assertion 源码、测试、构建产物，以及相关 Probe 失败文本/临时结果；成功证据继续保留。
- [x] 将待处理问题记录到仓库外 `D:\.Work\Practice\Python-Practice\DevProbe-todo.md`。
- [x] 完成 TypeScript clean install、typecheck、lint、unit/integration test、production build和 Python 定向回归。
- [x] 完成后台全仓 pytest、diff/path 检查和技术档案更新。
- [x] 完成 `finish-module` 技术收工。

## 冻结的实现与边界

- **SDK 与公开面**：`@modelcontextprotocol/server` / `client` 2.0.0；MCP server 只公开一个 `data_pilot_query` Tool，内部按 `query`、`task_status`、`task_clear` 分发。
- **深模块边界**：MCP 只负责协议、transport、网络合同校验和安全投影；FastAPI/Pydantic 继续负责 Router、Agent Loop、Evidence、权限、task 状态与数据库真值。
- **共享合同**：`packages/data-pilot-contracts/` 只承载 Web/MCP 共同的网络 Zod schema；Web 的 presenter/session/BFF 与 MCP projector/stdio 不进入共享包。
- **安全边界**：仅允许 `127.0.0.1`/`localhost`，固定本地 `ops` fixture caller，不允许客户端选择 role/model/corpus/RAG strategy；不包含远程 transport、OAuth/生产认证、streaming 或动态 Tool。
- **可靠性边界**：mutation 永不自动 retry；timeout/abort/合同漂移等不可判定结果映射为 unknown，调用方只能显式 status 对账。
- **能力声明**：M51 完成的是本地 stdio 基础适配器、SQL happy path、transport/lifecycle 和安全负路径。真实 policy RAG/Hybrid MCP happy path 未作为 M51 完成项，后续编号固定为 `M51R`，且不得挪给 M52。

## 模块名称与改动文件清单

- **模块**：M51 TypeScript 本地 MCP Adapter。
- **工程与依赖**：`.gitignore`、root `package.json` / `package-lock.json`、删除旧 `web/package-lock.json`、调整 `web/package.json`。
- **共享合同**：`packages/data-pilot-contracts/` 全目录；`web/lib/contracts.ts` 改为稳定 re-export 门面。
- **MCP 产品代码**：`mcp/package.json`、`tsconfig.json`、`eslint.config.js`、`README.md`，以及 `src/` 下 config/contracts/http-adapter/index/probe/probe-p3/projector/server。
- **MCP 与共享合同测试**：`mcp/test/` 5 个测试文件、`packages/data-pilot-contracts/test/contracts.test.ts`。
- **模块文档与状态**：`AGENTS.md`、`docs/notes/m51-plan.md`、本 notes、`docs/state/runbook.md`、`docs/state/AI_CONTEXT.md`、`docs/state/change-history/phase4b.md`；finish-docs 阶段将只追加 `docs/dev-log.md`。
- **排除项**：用户已有的 `docs/ref-discussion/Agent 测评 的讨论.md` 和 `docs/todo.md` 不属于 M51，未整理；仓库外 `DevProbe-todo.md` 是用户明确指定的延期问题入口。

## 关键决策与取舍

- **SDK major**：方案 A 是官方 TypeScript SDK v2 server/client 分包，方案 B 是兼容面更老的 v1。建议并最终选择 A，因为当前 Node 24/TypeScript 6/Zod 4 能直接消费 v2 的 schema、structured output 和测试接口；若将来目标 Client 出现官方兼容机制无法解决的可复现阻断，必须带证据重新决策，不能静默双栈。
- **网络合同 seam**：方案 A 是抽取私有共享网络 schema 包，方案 B 是 MCP 独立复制窄 schema 再靠 fixture parity。建议并最终选择 A，但只共享 Web/MCP 都消费的网络边界，不共享 UI presenter、session、BFF 或 MCP projector；这样减少漂移，又避免形成浅而大的公共包。
- **模块收口**：继续修 Web/API/MCP 共用 turn understanding 会改变既有默认行为；用户最终选择先结束 M51，将真实 policy RAG/Hybrid 问题放入仓库外 todo，并固定后续为 M51R。主要风险是能力声明被误写过宽，因此 plan、runbook、AI_CONTEXT、changelog 和 README 都明确保留未完成边界。

## Live Dev Probe 收口证据

- **时点合规**：P1 在 M51-C 后、M51-D 前执行并形成 `passed → continue`；P3 在 lifecycle 实现后执行。真实调用没有统一拖到收工阶段补造。
- **M51-P1**：真实 `MCP Client → stdio → loopback HTTP → FastAPI task → Qwen Text2SQL → SQL Guard → datapilot_demo MySQL → Response/Trace → MCP` 完成；2026-07 实际净退款金额为 `120000`，task v1，2 provider calls / 5900 observed tokens，Trace=`8e0e1fe4-70c8-46fc-a411-be3a81260c06`。
- **P1 重验成功证据**：同一固定 SQL 场景再次得到 `120000`，2 calls / 5908 tokens，Trace=`836c8d37-3bdc-466d-ae5c-0f99b07bc71e`。成功摘要保存在 `.agent_work/temp/m51/probe-campaign/p1r-success.json` 与 `success-trace.jsonl`。
- **M51-P3**：非法输入在 HTTP 前拒绝；stale version 为 `task_version_conflict` 且零 provider/deep invocation；status 返回服务端确认版本；clear 成功并按完整 safe ref 精确清理。最终 demo migration/oracle 不变，synthetic checkpoint/event=`0/0`。
- **模块实际总账**：8 provider calls / 25940 observed tokens，retry=0；全部属于 exploratory/baseline-ineligible development probe，不登记 Formal Eval 或质量基线。
- **用户收口决定**：真实 policy RAG/Hybrid 的详细待办、依据和 M51R 重开门已迁移到仓库外 `DevProbe-todo.md`。仓库内只保留上述完成边界与成功证据，不保留相关失败 Probe 文本或结果文件。

## 关键工程记录

- SDK v2 server factory 需要零参闭包；用 `() => createDataPilotServer()` 适配，没有扩大公开接口。
- 开发 Probe 的 MCP Client 默认约 60 秒等待短于 adapter 310 秒预算；通用 probe harness 已显式使用 330 秒，仅修正开发工具等待，不改变产品 Tool 合同。
- root workspace clean install 暴露 Web 的 `jsdom` 只位于 workspace 子路径、根 Vitest 无法解析；在 root 增加同版本 devDependency 后，新的 `npm ci` 和三 workspace 测试均通过。它是 workspace 安装图修正，不改变 Web 或 MCP 运行行为。
- 第一次 Python 定向回归被 Windows pytest basetemp `WinError 5` 阻断；使用同一测试集合和新的隔离 basetemp 在沙箱外复验通过，没有改实现或缩小范围。
- 用户已有的 `docs/ref-discussion/Agent 测评 的讨论.md` 与未跟踪 `docs/todo.md` 不属于 M51，未修改或整理。

## 参考资料

- **官方 MCP TypeScript SDK**：定点核对 v2 server/client 分包、stdio server、Tool registration、structured output、client transport 和 Inspector 用法；借鉴标准协议与测试 seam，没有照搬远程 transport、认证或动态 Tool。
- **Claude / Cursor 本地 MCP 文档**：核对本地 stdio command/args/env 配置和 Claude Code 的 `mcp add` 入口；README 只给本地配置示例，不承诺所有客户端版本 UI 一致。
- **项目现有实现**：复用 M50 demo launcher/preflight/status/cleanup、Python-authoritative 网络 fixture 和 Phase 4B task/version authority；没有把 Web BFF、前端 session 或服务端业务状态机复制进 MCP。

## Handoff

1. **已完成且可依赖**：root npm workspace、共享网络合同包、单 Tool stdio server factory、loopback HTTP adapter、bounded projector、query/status/clear 与 unknown reconciliation 均已通过自动化和真实 SQL 链验证；`mcp/README.md` 可直接作为本地客户端入口。
2. **未完成与风险**：真实 policy RAG/Hybrid MCP happy path 未证明；当前也不包含远程 transport、生产认证、多租户、streaming、性能/HA 或 exactly-once。MCP SDK/客户端快速演进、stdio 工作目录/env 差异与 Qwen 长延迟仍是使用风险。
3. **必须延续的边界与决策门**：Python/Pydantic 永远是业务 authority；客户端不可选 role/model/corpus/RAG strategy；mutation retry0、unknown 显式 status 对账、Pipeline 默认/Subgraph experimental 不变。M51R 与 M52 都必须满足 plan 中各自的强制开工条件，不能因为演示方便合并或降门。
4. **下一模块入口与必读指针**：若优先补本地真实政策链，先读仓库外 `DevProbe-todo.md`、`docs/notes/m51-plan.md` 第 10 节、`engine/phase4b/task_runtime.py`、`engine/phase4b/agent_loop.py` 和 RAG state，另立 M51R plan；若未来做远程 MCP，则先从 `mcp/src/server.ts`、`http-adapter.ts`、projector 测试和 M52 threat/auth 门开始。

## 注释审计

- 完整回读 10 个生产 TypeScript 文件（MCP 8、共享合同 1、Web 合同门面 1）和 6 个相关测试文件。
- 审计 22 个非豁免函数/类/构造器；文件职责、关键 seam、限额、失败关闭和新手易混点均已有中文注释，缺失为 0。
- 删除的 campaign/assertion 是临时诊断专用代码，不属于最终产品模块；通用 `probe.ts` 与 `probe-p3.ts` 保留作为可复现成功/安全链路工具。

## 收工验证快照

- `npm ci`：added 532 packages，audit 536，0 vulnerabilities。首次执行因遗留 Next Node 进程占用 SWC 文件而 EPERM；精确停止 3 个旧项目 Node 进程后 clean install 成功。
- `npm run typecheck`：contracts/MCP/Web 全部 exit 0。
- `npm run lint`：MCP/Web 全部 exit 0。
- `npm test`：contracts `2 passed`，MCP `39 passed`，Web `36 passed`。补齐 root `jsdom` 后从失败点重跑并通过。
- `npm run build`：contracts、MCP TypeScript build 和 Next production build 全部 exit 0；Next 6 个页面完成，3 个 BFF route 为动态路由。
- Python 定向回归：M42/M43/M47/M48/M50 六个文件，`38 passed, 1 existing Starlette/httpx warning`。
- 全仓 pytest：后台同次 `684 passed, 1 existing Starlette/httpx warning in 577.38s`，exit=`0`、done 存在。

## State impact

- `AGENTS.md`：已加入 `mcp/` 与 `packages/data-pilot-contracts/` 目录事实。
- `docs/state/runbook.md`：已加入 M51 本地 MCP 构建、配置、超时、对账、投影和能力边界。
- `docs/state/AI_CONTEXT.md`：已写 M51 当前状态、默认值、验证事实、M51R 重开门。
- `docs/state/change-history/phase4b.md`：已按索引新增 M51 模块档案。
- `database-current-state.md`：已检查；无 schema/seed/default DB 变化，最终 synthetic 行 `0/0`，无需更新。
- `rag-current-state.md`：已检查；无 active release、retrieval runtime、Milvus/index 或默认策略变化，需在 AI_CONTEXT/历史中保留能力边界即可。
- `eval-baselines.md`：已检查；本模块只有 baseline-ineligible Live Dev Probe，没有 Formal Eval 或新基线，无需更新。

## 2026-08-29 后台全仓回归启动前 checkpoint

- 关键决策与实现已经冻结：M51 按用户确认以本地 stdio 基础适配器收口；真实 policy RAG/Hybrid 移至 M51R，不改变 M52；没有临时替代方案冒充最终能力。
- 前台验证已全部通过：clean install、typecheck、lint、77 项 TypeScript 测试、production build、38 项 Python 定向回归。
- 已知风险只剩全仓兼容性与文档一致性；没有未检查的产品代码分支。完整 pytest 预计超过 2 分钟，按 AGENTS/runbook 转后台。
- 待完成：读取后台 exit/done/log，更新最终验证结论；随后写 Phase 4B changelog 与 AI_CONTEXT，执行 diff/path/完整回读，勾完 `finish-module`；之后才能进入 `finish-docs`。

## finish-module 技术档案交付清单

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] notes 已记录 Live Dev Probe 的适用理由和开发时点；P1/P3 证据不是收工补跑，也未与 Formal Eval 混算。
- [x] 已完整读取 `CHANGELOG_INDEX.md`，并按索引写入 Phase 4B 完整模块记录。
- [x] `AI_CONTEXT.md` 已更新当前模块、默认值、最新验证与路线边界。
- [x] 命中的 runbook 已更新；database/RAG/eval 三份专项 state 已完整检查并记录无需修改理由。
- [x] 新结论与历史条目、代码、测试、默认配置和各 state 之间不存在冲突或重复权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md`、runbook 与 notes 已完整回读。
- [x] `git diff --check`、本轮文档路径与 root lock/workspace 依赖检查均通过。

### 后台任务登记

- 状态：**已完成并检查**；exit=`0`，done 存在，结果=`684 passed, 1 warning in 577.38s`。
- wrapper PID：`73068`。
- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m51/pytest-full-final/basetemp -q`。
- 日志：`.agent_work/temp/m51/pytest-full-final/pytest.log`。
- 退出码：`.agent_work/temp/m51/pytest-full-final/pytest.exit`。
- 完成标记：`.agent_work/temp/m51/pytest-full-final/pytest.done`。
- 已按 notes、exit、done 和日志尾部交叉核验，未仅按进程消失判断结果。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、重要取舍、验证证据、未证明的边界；不适用项可以省略。
- [x] 每个编号点没有挤成一个无断点大段：编号下先写一句可独立成立的结论，再用 `- **小标题**：` 或分段落拆分不同主题；任何自然段超过约 4 行、或包含 3 个以上独立主题时必须拆分。
- [x] 正文每个英文/代码术语首次出现时紧跟括号或一句通俗解释（如 `checkpoint（任务检查点）`）。
- [x] 需要对照的数字（A/B 结果、覆盖率、pass 数）优先用列表或表格呈现，不埋在长句中间。
- [x] 新概念存在时已用通俗语言解释；没有新增概念时不强行编造。
- [x] “代码阅读路线”是按真实调用或数据流组织，不止说明“看什么”，还需要说明“为什么/解决了什么”
- [x] 有“设计要点”
- [x] “有面试价值的亮点”有可背、可独立展开的亮点。
- [x] “有面试价值的亮点”只讲能在面试中拿得出手的、能让面试官认可能力的，禁止强行凑数。
- [x] 追问优先围绕亮点展开，没有强行凑数的低价值问题和回答。
- [x] “验证与下一步”只引用 notes 中的真实验证快照。
- [x] 复制命令安全、可重复，并标明必要前置条件。
- [x] 模块记录的各个小节的文本都要用 `**...**` 加粗标出“服务于扫读抓重点”的关键词或关键短句。

**自检结果**：完整回读 M51 新章节后，确认包含 6 个拆分清晰的一级工作点、6 个新概念、真实调用顺序的代码阅读路线、设计要点、5 个可背亮点、5 个分层追问、验证表和本地 Inspector 体验。数字与 notes/AI_CONTEXT/Phase 4B changelog 一致；设计末句为“汪。”、压力回答末句为“喵。”；本阶段未修改技术档案或产品代码。
