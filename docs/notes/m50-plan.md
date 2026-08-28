# M50 DataPilot Web 工作台开发计划

> 能力里程碑：Phase 4B 完成后的产品展示集成；把 B0～B6 已完成的公开能力做成可操作、可解释、可复现的本地 Web Demo，不新增或改写 Agent 能力里程碑
>
> 主要问题：现有 Streamlit 页仍停留在 legacy 单轮/澄清/一次追问，无法完整展示当前 `agent_task` 多轮、Action/Evidence、预算、持久 task 与 Compact，且旧 TypeScript 方案仍以 M40 时的合同为基线

## 1. 模块定义与范围判断

M50 交付一个完整的本地真实 Web 工作台：用户可从浏览器发起 DataPilot task，连续修改任务、查看 SQL/RAG/Hybrid 结果、图表、引用和安全状态，并从公开响应中理解本轮 TaskDelta、Action、Evidence、Budget、Termination 与 Compact。页面必须真实调用现有 FastAPI `POST /api/query`，不得用静态 mock 冒充最终演示，也不得在前端复制 Router、Evidence Gate、Controller、权限或 task 状态机。

这个范围围绕“把已完成的可信 Agent 能力正确展示出来”形成一个闭环，适合作为单个模块：

- 合同对齐、交互状态机、结果可视化、真实联调和演示材料共同决定页面是否可信，拆开后任何一片都不能独立形成可验收的产品体验。
- 公网部署、生产认证、MCP、完整 Eval Dashboard、streaming 和新的 Agent/RAG 能力各自需要不同的安全与运行合同，不属于这个闭环；不把它们列成 M50 的模糊后续，也不以未实现这些能力为由降低 M50 的本地 Web 完成标准。
- M50 不是“先做一个静态页面，以后再接 API”的分阶段交付。静态 fixture 只用于开发与自动化验证；模块完成时必须具备真实 API、多轮 task、结果展示、错误/安全状态和可复现的演示环境。

用户完成本模块后应能：

1. 在同一 Web task 中演示自然语言 start/continue/switch/cancel/clear，并正确携带服务端签发的 task identity/version；
2. 展示 SQL 表格与 Vega-Lite 图表、RAG citation、Hybrid 双分支，以及 blocked/partial/unsupported/insufficient/external-unavailable/failed 等非 happy-path；
3. 用“前端只消费服务端公开事实，不替 Agent 决策”的方式解释 Presentation Layer 与 Agent Engine 的 seam；
4. 通过固定 preset 和本地启动说明重复演示，而不是依赖开发者记住隐藏环境步骤。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| `/api/query` 已有 `legacy` 与 `agent_task` 两个 runtime family；task family 支持 start/continue/switch/cancel、MySQL durable state、Action/Budget/Termination、Context/Compact | 旧前端若只展示 legacy thread，会隐藏 Phase 4B 的核心成果并把“有界一次追问”误讲成当前主多轮能力 | `app/schemas/agent.py`、`app/api/query.py`、`docs/state/AI_CONTEXT.md` |
| `AgentResponse` 同时包含四轴状态、兼容结果字段和大量 task-only 安全投影 | 页面若只判断 `answer` 是否为空，会把 blocked、partial、insufficient 或 transport failure 误展示成普通成功/普通空结果 | `app/schemas/agent.py::AgentResponse`、`tests/test_m43_task_api_trace.py`、`tests/test_m44_api_trace.py` |
| task 请求必须使用上一响应的 `task_id + task_version`，错误版本会在 Tool/provider 前拒绝；当前没有公开 task 查询/重放端点 | 浏览器不能自动重试结果未知的写请求，也不能在并发 tab 中凭本地猜测恢复最新版本；必须显式冻结 last-acknowledged 语义 | `TaskRequestEnvelope`、`runbook.md` API/task 章节、`tests/test_m43_task_api_trace.py` |
| 现有 `demo/streamlit_app.py` 只实现 legacy initial、clarification、一次 follow-up，Trace 也未展示 Phase 4B task 字段 | 它可作为旧兼容调用参考，但不能直接迁移为 M50 的交互模型 | `demo/streamlit_app.py`、`docs/notes/phase4b-audit-notes.md` |
| 旧 TS v3 方案写于 M40，仍把 clarification + bounded follow-up 当主要多轮目标，并将五类 legacy 场景作为 DoD | 方案的 Presentation/Agent 分权仍成立，但请求合同、主演示故事、组件状态和验收矩阵已过时 | `docs/ts-integration-plan-v3.md` |
| 默认 `datapilot_dev` 已迁移 0005，但没有 Phase 4B 7/8 月 profile；招牌 T1→T6 只在隔离 `datapilot_m48_test` 有冻结 oracle | 不解决演示数据入口，Web 页面虽能运行，却不能按文档稳定复现招牌故事 | `docs/state/database-current-state.md`、`docs/notes/phase4b-audit-notes.md` |
| ordinary external RAG 依赖 Milvus/embedding/profile readiness；business task Knowledge 与 external runtime 分账，Subgraph 仍是服务端 experimental | 前端必须展示 readiness/typed unavailable，不能提供 corpus/backend/strategy 开关，也不能把 Subgraph 标成质量胜出或默认能力 | `docs/state/rag-current-state.md`、`docs/state/runbook-rag.md` |
| 后端返回 Vega-Lite v5 spec；图表不是结果 authority | 图表渲染失败必须降级为表格，不能让图表异常吞掉已验证 rows 或改变 answer 状态 | `engine/tools/chart_tool.py`、`domain_pack/chart_templates/basic.yaml` |
| 仓库目前没有 JS/TS 工程，Node/npm 本机为 `v24.14.0 / 11.9.0` | M50 需新增锁文件、构建/测试命令和忽略规则；不能假设已有前端工程规范 | 根目录文件检查、`node --version`、`npm --version`（2026-08-28） |

## 3. 参考源码定点复核

本模块的真实问题是：如何把复杂 Agent 状态收敛到一个易学、易测的前端 interface，同时不把前端变成第二个 Agent。`docs/phase4-reference.md` 中已有项目主要覆盖 Agent/RAG 内部，不直接提供当前 Web 产品 seam；因此本次在遵守其 Evidence/安全/Trace 边界的基础上，定点复核完整 data-agent 前端 `askdata_studio`，并用官方框架文档核对 transport 选项。

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 统一 HTTP 调用、超时与可读错误 | `askdata_studio/frontend/src/api.ts::request/api.query` | 将 timeout、无法连接、HTTP 非 2xx 收敛到单一请求模块；调用方不重复 fetch 细节 | 建立小 interface、高实现深度的 `DataPilotClient` 模块；内部负责 BFF/FastAPI transport、运行时校验、错误分类、AbortSignal 和 task envelope | 不照搬 session token/login，因为 DataPilot 当前只有 local/demo fixture caller；不把任意后端 `detail` 原样透给最终用户 |
| 对话、pending 与结果卡的组合 | `askdata_studio/frontend/src/App.vue::ConversationRecord/createConversation/submit` | pending query、按 turn 保存“问题 + 结果”、完成后滚动、结果与输入同屏 | 一个前端 task 只对应一个服务端 task lineage；turn 记录保存公开 response snapshot，current task identity 只从最后成功响应推进 | 不照搬客户端自建的无限对话语义、任意 session id、workspace rows 拼入下一轮或 30 条本地长期历史 |
| 大表格的可读展示 | `askdata_studio/frontend/src/components/ResultTableCard.vue` | sticky header、分页、空/加载/错误三态、数值格式与窄屏处理 | 对当前响应内已公开 rows 做客户端分页/格式化；原始值仍可检查；图表失败保持 table 可用 | 不照搬 Excel 导出 5000 行：DataPilot 响应不是完整导出 authority，导出会制造“已取全量”的误解 |
| 类型与状态枚举 | `askdata_studio/frontend/src/types.ts::QueryResult` | 将 route/status/clarification/result shape 显式建模 | Python OpenAPI/Pydantic 继续是 authority；前端只为实际消费字段建立 runtime validator，并用跨语言 fixture 漂移测试约束 | 不照搬只有 TypeScript interface、没有运行时校验的做法；不照搬 AskData 的 route/status taxonomy |
| 同源转发 seam | `askdata_studio/frontend/vite.config.ts::server.proxy`；`https://nextjs.org/docs/app/guides/backend-for-frontend :: Route Handlers`；`https://vite.dev/config/server-options.html#server-proxy` | 浏览器使用相对 `/api`，避免页面组件知道 FastAPI 地址 | 若 G50-1 选 A，用薄 BFF 统一 POST/DELETE、超时和 runtime validation；若选 B，只把 Vite proxy 当开发适配器，并明确生产仍需同源 reverse proxy | 不把 dev proxy 当部署方案；不在 BFF 复制业务路由、task 状态机或安全决策 |
| 图表嵌入生命周期 | `https://vega.github.io/vega-embed/index.html :: embed/result.finalize` | 可直接消费 Vega/Vega-Lite object spec，卸载时释放 view/timer/listener | 只渲染服务端 `chart_spec`，关闭在线 editor/source action，失败时记录 UI error 并降级 table | 不允许图表从外部 URL 加载数据，不让前端 patch 改写业务字段/聚合 |
| Agent 控制权与公开 Trace | `docs/phase4-reference.md` 的 `Evidence、citation 与回答边界`、`Trace 与 RAG/Hybrid Eval` | 公开展示必须以实际 Tool context、Evidence/citation 与同源执行事实为准 | Inspector 只读取 `AgentResponse` 的安全投影；不读 JSONL、数据库或私有 Evidence 补页面 | 不把 Tool call 列表、引用存在或 UI 标签冒充答案正确率/质量胜出 |

参考项目实际证明了请求封装、turn UI 和表格卡可以形成清晰的 data-agent 页面，但不能证明 DataPilot 的 task/version、四轴状态、Evidence/citation 或 durable state 合同。M50 的这些语义仍以 DataPilot Pydantic、测试、state 与真实 Probe 为准。

## 4. 目标、优先级与非目标

### 模块完成状态

模块完成时，仓库包含一个可独立安装、构建和启动的 TypeScript Web 工程。页面通过真实 FastAPI 完成一条 Phase 4B task 纵向链，正确展示每轮问题、答案、SQL/rows/chart、citation/Hybrid branch、task version、TaskDelta、Action/Budget/Termination 与 Compact 安全摘要；legacy 请求仍有单独演示入口，但不会与 task payload 混用。所有关键状态均有 fixture 自动化覆盖，真实链有按切片执行的 Live Dev Probe 证据。

### 必须完成

- 完成 G50-1/G50-2 并冻结工程 runtime 与演示数据入口。
- 建立单一 `DataPilotClient` interface，封装 task/legacy 请求、DELETE clear、timeout、HTTP/validation/product-status error 和 unknown-outcome 语义。
- 以 Phase 4B task 为首页主交互：start、continue、switch、cancel、clear；一轮在途时禁止同 task 并发提交。
- runtime 校验当前页面消费的 `AgentResponse`/control response；非法或漂移响应不得进入正常成功视图。
- 建立纯 `ResponsePresenter` 投影，将四轴状态和 reason 映射为互斥的 UI state，不用 `answer` 真值替代服务端裁决。
- 展示 SQL、表格、Vega-Lite 图、citation、Hybrid branch、Tool calls、TaskDelta、Action/EvidenceDelta、Budget、Termination、Context/Compact identity 的公开摘要。
- 覆盖 loading、empty、blocked、clarification、partial、unsupported、insufficient evidence、external unavailable、failed、transport unavailable、timeout、validation failure、stale version 和 unknown outcome。
- 提供明确标注依赖/runtime 的 preset；至少覆盖 SQL task 多轮、business Hybrid/citation、legacy clarification、安全/证据停止。
- 构建、类型检查、lint、单元/模块测试、Playwright 主路径与关键非 happy-path 通过。
- 形成可重复启动说明、演示脚本、架构图和最终截图；README 只在 M50 作为本展示集成模块收口时更新。

### 建议完成

- 响应式桌面/窄屏布局、键盘可操作、可见 focus、`aria-live` 状态播报和 reduced-motion 基线。
- task inspector 支持按“本轮决策 / 数据结果 / 技术细节”逐级展开，默认不把 raw JSON 倾倒给非技术观众。
- 浏览器 `sessionStorage` 保存最后已确认的 task id/version 和已公开 turn snapshot，使普通刷新可恢复 UI；任何在途请求不写成已确认版本。
- 开发模式的 fixture gallery，集中查看全部状态，不作为生产/演示默认入口。

### 条件触发

- **触发条件**：实际合同对齐发现当前公开响应不足以区分必须展示的状态，且不能从已有四轴/reason/task safe projection 无歧义得出。
- **允许动作**：只增加最小、additive、安全的公开投影及 Python contract test；先证明“缺公开投影”，再修改后端。
- **未触发时**：不改 `AgentResponse`、TaskState、Trace、Router、Loop、Knowledge runtime 或数据库 schema。

### 明确非目标

- 不做公网部署、Vercel 上线、生产 OAuth/JWT/SSO、真实 tenant 管理或滥用防护。
- 不做 SSE/WebSocket/token streaming；loading 展示不伪造节点进度。
- 不做自由无限聊天、跨 task 长期记忆、客户端自己拼 conversation history 或自动 replay。
- 不让客户端选择 Pipeline/Subgraph、corpus、backend、model、outbound policy、Evidence requirement 或 Action。
- 不做 MCP Adapter、完整 Eval Dashboard、在线触发 Eval、LangFuse 页面或读取 JSONL 的内部 Trace 浏览器。
- 不做 CSV/Excel 全量导出、数据编辑、文件上传、Schema 拖拽、保存结果作为下一轮 authority。
- 不以 M50 宣称 RAG/LLM 质量提升、Subgraph 胜出、生产 HA/性能或 exactly-once。

## 5. 关键合同

这是 M50 核心合同的单一事实源；后续章节只引用编号。

### C1：Python 合同权威与跨语言校验

- 输入：FastAPI OpenAPI/Pydantic 的 `QueryRequest`、`AgentResponse`、`TaskControlResponse`、`ThreadControlResponse`。
- 成功输出：前端得到经 runtime validator 验证的 typed response；只允许页面明确消费的开放字典保留 passthrough，核心 enum/identity/version/四轴字段严格校验。
- 失败语义：HTTP body 非 JSON、核心字段缺失、enum 漂移或 shape 不合法 → `response_contract_invalid`，展示独立合同错误，不进入 answer/result 组件。
- 必须保持的不变量：Python 是唯一业务合同 authority；fixture 携带来源/生成 identity；前端类型不能反向定义后端语义。
- 本模块不冻结的实现细节：采用手写 Zod、OpenAPI 派生或组合生成的具体工具；G50-1 确认后在 M50-A 用最小 spike 比较并锁定依赖。

### C2：Task lineage 与 last-acknowledged version

- 输入：自然语言 question、active demo role、`start/continue/switch/cancel`；非 start 必须使用最后一次成功响应的 task id/version。
- 成功输出：每轮保存 user turn + validated response；只有响应完整返回且校验成功，客户端才原子推进 active task/version。
- 失败语义：`task_version_conflict` / `task_unavailable` 不自动重试；timeout、断网或响应校验失败若发生在提交后，标记 `outcome_unknown`，冻结该 lineage 的继续提交并提示新建 task/人工处理。
- 必须保持的不变量：同 task 最多一个在途 mutation；task 与 legacy thread payload 永不混用；不得递增、猜测或回退 version；cancel/clear 后不再继续旧 task；switch 使用服务端返回的新 identity/version。
- 本模块不冻结的实现细节：状态管理使用 React 内建 reducer/context 还是等价轻量机制；禁止仅为此引入全局状态库。

### C3：Transport/BFF 错误分层

- 输入：相对路径的 query/clear 请求、AbortSignal 和只在 server/dev config 可见的 FastAPI base URL。
- 成功输出：validated product response。
- 失败语义：至少区分 client validation、FastAPI 422、typed product rejection、backend unreachable、timeout/abort、non-JSON 5xx、response contract invalid、outcome unknown。
- 必须保持的不变量：BFF/proxy 不修改 task action、role、question、状态、Evidence 或 reason；错误响应不泄漏 raw stack/driver/provider 内容；mutation 不自动 retry。
- 本模块不冻结的实现细节：具体 timeout 数值在实现时结合本机 Qwen 120s 现实与真实 Probe 冻结；UI 必须允许用户主动取消等待，但取消后的 mutation 仍按 unknown outcome 处理。

### C4：四轴状态到视图的确定性投影

- 输入：validated `runtime_family + route + execution_status + answer_status + safety_status + reason_code`，以及 task/legacy lifecycle。
- 成功输出：一个互斥主状态和若干可组合辅助面板；`complete`、`partial`、`clarification_required`、`blocked`、`unsupported`、`insufficient_evidence`、`external_unavailable`、`failed/no_answer` 均有明确文案和视觉层级。
- 失败语义：出现未登记组合 → `unrecognized_product_state`，保留安全摘要/trace id，但不自行降级为 complete。
- 必须保持的不变量：`safety_status=blocked` 永不显示成功徽标；`answer_status=partial` 永不写“全部完成”；网络失败与 Agent typed failure 分开；`complete` 不等于语义正确率或质量 Gate 通过。
- 本模块不冻结的实现细节：颜色、图标、微文案；必须满足可访问性，不能只靠颜色区分。

### C5：结果、Evidence 与 Inspector 展示

- 输入：公开 `sql/columns/rows/chart_spec/citations/hybrid_branches/tool_calls/action_attempts/agent_budget/agent_termination/task_delta/task_transition/task_context/compact_decision`。
- 成功输出：结果区优先展示业务答案与数据；Inspector 逐级解释“任务发生了什么、用了哪些公开证据、为何停止”。
- 失败语义：chart render error → table fallback；某个可选 inspector 字段缺失 → 显示“本轮未公开/未触发”，不伪造 0 或空成功；citation/branch 不闭合时按服务端状态展示。
- 必须保持的不变量：不读取 JSONL、数据库、Prompt、完整文档正文或私有 Evidence 补页面；Hybrid 不把两段子答案重新合成；rows 不进入后续 question；隐藏/展开只影响展示。
- 本模块不冻结的实现细节：卡片拆分、tab/accordion、表格分页大小和桌面布局细节。

### C6：可复现演示场景与运行依赖

- 输入：版本化 preset manifest；每个 preset 声明 runtime family、前置依赖、首轮/后续 turns、预期状态类别和不可外推结论。
- 成功输出：本地操作员按文档准备环境后，可运行 SQL task 多轮、business Hybrid/citation、legacy clarification、安全/证据停止；页面显示真实结果和 runtime identity。
- 失败语义：依赖未就绪时 preset 显式 disabled/degraded 并指向 `/health` 或 `/health/rag` 事实；不切 fallback、不改问法凑成功。
- 必须保持的不变量：前端不能选择 server-controlled RAG strategy；Phase 4B oracle 与 legacy/default 数据分账；fixture preset 与真实 preset 明确标记；不得访问 held-out/sealed reserve。
- 本模块不冻结的实现细节：preset 的最终展示标题和排序；业务问法在不改变冻结 oracle/合同的前提下可做文案润色。

### C7：Legacy 兼容展示

- 输入：无 task envelope 的普通请求，以及服务端签发的 legacy clarification/follow-up spec。
- 成功输出：单独的兼容模式可展示 initial、clarification resume 和最多一次 bounded follow-up。
- 失败语义：没有 server spec 就不出现表单/动作；budget 消耗后不再显示 follow-up。
- 必须保持的不变量：legacy 不伪装 durable、跨 worker 或 Phase 4B task；页面默认入口仍是 task workspace；两套 identity/version 字段绝不共用。
- 本模块不冻结的实现细节：兼容入口位于 preset、secondary tab 或独立 route。

### C8：数据最小化与浏览器持久化

- 输入：validated public response 与 UI 所需最小 turn snapshot。
- 成功输出：内存中完整展示当前 session；若实现 sessionStorage，只保存公开字段、last-acknowledged task identity/version 和有界 turn 数。
- 失败语义：payload 超上限、schema/version 不兼容或读取失败 → 丢弃本地副本并要求新建 task，不把旧数据提交给服务端猜恢复。
- 必须保持的不变量：不持久化凭据、Prompt、Document 正文、完整内部 Trace、任意未受限 rows 或私有 task payload；不使用 localStorage 形成长期记忆；退出/clear 提供本地清理。
- 本模块不冻结的实现细节：建议项未落地时可只使用内存；这不影响服务端 durable task 能力，但页面必须如实标注刷新恢复边界。

## 6. 工作切片与执行顺序

### M50-A：决策冻结、工程骨架与 contract snapshot

- 优先级：必须完成
- 依赖：G50-1、G50-2 用户确认；当前工作树无冲突；开工时先建立 `docs/notes/m50-notes.md` checklist
- 实施内容：按 G50-1 初始化单一 `web/` 工程并锁定 npm 依赖；补 JS build/cache 忽略；建立 Python OpenAPI/fixture 导出与前端 runtime schema 的漂移检查；fixture 覆盖 task SQL、RAG/citation、Hybrid、clarification、partial、blocked、unavailable、failed、Compact、clear/rejected。
- 关键合同：C1、C3
- 交付物：可重复安装/构建的工程、lockfile、contract fixture/identity、最小 client/presenter interface
- 验证方式：Python fixture 生成/比对；前端 typecheck + runtime schema tests；篡改 enum/required field 必须失败
- Live Probe checkpoint：不适用；此切片只处理离线合同和 fixture，不调用真实 API/provider/数据库
- 完成门：页面尚可为空，但跨语言合同失败能在 CI/本地命令中稳定阻断；没有手抄整份 Pydantic 为第二权威

### M50-B：静态工作台与全状态 gallery

- 优先级：必须完成
- 依赖：M50-A
- 实施内容：实现 task workspace 基础布局、turn timeline、composer、preset、status banner、result/table/chart/citation/Hybrid 卡、Inspector 和 legacy compatibility view；使用 contract fixtures 驱动全部状态；完成桌面和窄屏最低可用布局。
- 关键合同：C4、C5、C7、C8
- 交付物：fixture gallery 与默认工作台 UI
- 验证方式：presenter table tests、模块渲染 tests、Playwright fixture matrix、键盘/focus/可访问性检查、chart failure → table fallback
- Live Probe checkpoint：不适用；仍未接真实 transport
- 完成门：所有登记状态都有确定视图；不存在 `if (answer) => success` 一类旁路；raw fixture JSON 不作为默认产品界面

### M50-C：真实 task 纵向链与 lifecycle

- 优先级：必须完成
- 依赖：M50-B；G50-2 对应 demo 环境已通过零 provider preflight
- 实施内容：接通 browser → BFF/proxy → `/api/query`；实现 start/continue/switch/cancel/clear、single-flight、last-acknowledged version、timeout/abort/unknown outcome；保留每轮 validated response snapshot。
- 关键合同：C2、C3、C4、C8
- 交付物：可操作的真实 task workspace
- 验证方式：Playwright 使用受控 FastAPI fixture adapter 验证请求形状/version；真实环境执行 M50-P1
- Live Probe checkpoint：M50-P1 / after M50-C、before M50-D；只有 `continue` 才放行真实 Evidence 展示联调
- 完成门：P1 三态和处置已记录；task 请求不携带客户端自造 state/delta/action；stale/unknown outcome 不自动重试

### M50-D：SQL、RAG、Hybrid 与 Agent Inspector 真实联调

- 优先级：必须完成
- 依赖：M50-P1=`passed → continue`
- 实施内容：对齐真实 SQL rows/chart、business citation、Hybrid branches、Action/EvidenceDelta、Budget/Termination、Knowledge runtime、Task Context/Compact；实现依赖 readiness 与 experimental runtime 的诚实标注；不新增客户端 strategy 开关。
- 关键合同：C4、C5、C6
- 交付物：招牌 task preset 与真实结果/Inspector 展示
- 验证方式：fixture E2E 覆盖所有分支；真实环境执行 M50-P2；截图人工核对 Response 与页面关键值/identity 一致
- Live Probe checkpoint：M50-P2 / after M50-D、before M50-E；未形成明确 `continue` 不得进入演示冻结
- 完成门：真实 SQL/Document 双 Evidence 能被页面区分且不会泄漏正文；图表失败不影响表格；Pipeline/Subgraph/default/experimental 文案无误

### M50-E：安全负路径、legacy 兼容与恢复边界

- 优先级：必须完成
- 依赖：M50-P2=`passed → continue`
- 实施内容：贯通 version conflict、role drift/task unavailable、clear、legacy clarification/follow-up；验证 session refresh/unknown outcome 的诚实边界；补全 HTTP 422/non-JSON/contract drift/后端不可达的 UX。
- 关键合同：C2、C3、C4、C7、C8
- 交付物：非 happy-path 产品闭环
- 验证方式：Playwright negative matrix；真实环境执行零额外 provider 的 M50-P3
- Live Probe checkpoint：M50-P3 / after M50-E、before M50-F；安全断言失败时停止演示冻结
- 完成门：安全拒绝不会出现成功/重试诱导；legacy/task payload 无混用；clear 后本地 identity 和 session snapshot 清理

### M50-F：演示冻结、全量验证与交付

- 优先级：必须完成
- 依赖：P1～P3 均有明确处置且不存在未处理 `revise/stop`
- 实施内容：冻结 preset manifest、启动/准备/演示步骤、页面架构图、截图；更新当前 state、技术历史、AGENTS 目录事实和阶段末 README；按 `finish-module` 收工。
- 关键合同：C1～C8
- 交付物：最终 Web 工程、测试、演示材料、notes/state/changelog/README
- 验证方式：clean install、build/typecheck/lint/test、Playwright、Python 聚焦回归、`git diff --check`；全仓 pytest 预计超过 2 分钟，按后台纪律执行
- Live Probe checkpoint：不新增；收工只审计 P1～P3 的原时点证据，不补跑冒充开发期 Probe
- 完成门：在文档声明的本地环境中可从零启动并完成真实主故事；所有自动化通过或有明确非产品阻断；未把本地 Demo 写成公网/生产能力

## 7. 决策门

### G50-1：Web runtime 与同源 transport seam

> 用户决定（2026-08-28）：采用方案 A，冻结为 Next.js App Router + React + TypeScript + 薄 BFF；方案 B 不实施。

#### 方案 A：Next.js App Router + 薄 BFF（建议）

- 做法：`web/` 使用 Next.js + React + TypeScript；浏览器只调用同源 Route Handler，BFF 转发 FastAPI POST/DELETE，集中做 timeout、错误净化与 runtime validation；业务状态仍原样返回。
- 影响：多一个 Node server 和一次本地 HTTP hop，但 transport/config/error 复杂度集中在一个深模块，页面不会知道 FastAPI 地址；更适合以后独立托管 Web shell，但 M50 不承诺公网部署。
- 适用条件：重视简历中的 React/Next 全栈展示、同源 seam、未来部署可迁移性，并接受 BFF 的构建/运行复杂度。
- 风险：Route Handler 可能被误写成第二后端；必须用 C3 和 contract test 限制为纯 adapter，禁止缓存 mutation 和业务改写。

#### 方案 B：React + Vite SPA + 开发代理

- 做法：浏览器直接调用相对 `/api`；开发时用 Vite proxy 转 FastAPI，部署时另需 reverse proxy 或 CORS 配置；runtime validation 在浏览器完成。
- 影响：开发产物更薄、启动更直接；但 Vite proxy 只在 dev 生效，未来部署必须重新解决同源和后端地址，transport seam 也更靠近浏览器。
- 适用条件：明确只要本地静态 SPA，不需要 BFF/SSR/同源 server adapter，也不把未来托管迁移作为当前价值。
- 风险：容易把 dev proxy 误当最终运行方案；若后来增加公网 shell，会重新设计部署 seam。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：旧 v3 路线与求职展示目标本就选择 Next.js；当前复杂度集中在 task mutation、响应校验和错误分层，BFF 能以小 interface 提供真实 leverage/locality，而不是为了“多一个框架”增加空壳。官方文档也明确 Route Handler 适合 BFF，但不是完整后端替代，这与 DataPilot 的 FastAPI authority 一致。
- 用户确认前允许推进：已完成只读调查、plan、contract fixture 清单。
- 用户确认前禁止推进：该限制已解除；仍需用户明确发起 M50 开发后才创建 JS 工程、安装依赖和冻结 lockfile。
- 需要确认的时点：已于 2026-08-28 确认，无待决项。
- 重开决策的条件：实现 spike 证明当前 Windows/Node 环境存在不可接受的 Next build/runtime 阻断，或用户明确将交付目标改为纯静态 SPA。

### G50-2：Phase 4B 招牌故事的演示数据库

> 用户决定（2026-08-28）：采用方案 A，冻结为独立 `datapilot_demo` + 显式准备脚本；禁止为 M50 reset/reseed `datapilot_dev`。

#### 方案 A：独立 `datapilot_demo` + 显式准备脚本（建议）

- 做法：新增有护栏的演示准备入口，只允许目标库精确为 `datapilot_demo`；显式执行 Alembic 到 0005 和 `profile_alias="phase4b"` deterministic seed，记录 profile/oracle identity。页面正常运行时只读业务表；task checkpoint/event 按产品合同写入并支持 clear/expiry。准备动作绝不由 Web 按钮触发。
- 影响：招牌 7/8 月故事可重复，且不触碰 `datapilot_dev`/Probe 库；用户需在首次演示前执行一次明确的建库/重建命令。
- 适用条件：要把 T1→T6 作为稳定作品演示，并愿意维护独立 demo 数据库的准备说明。
- 风险：准备脚本具有真实 DB reset/write；必须精确校验数据库名、显示将被重建的目标、获得本门确认，并在测试中证明不会指向 dev/test/prod 名称。

#### 方案 B：把默认 `datapilot_dev` 切为 Phase 4B profile

- 做法：对默认开发库执行 reset/reseed，使其直接具备 7/8 月 oracle；同步数据库 state、既有默认事实和全部受影响测试/文档。
- 影响：启动步骤少一个数据库选择，但会改写当前 1 万级开发数据及既有本机事实，把展示 profile 与日常开发默认耦合。
- 适用条件：用户明确希望 Phase 4B profile 成为整个项目的新默认数据世界，并接受现有库可恢复性与历史可比性变化。
- 风险：破坏性更高，影响范围明显超过前端模块；不能仅因演示方便采用。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：它完整解决招牌演示断点，同时保持 legacy/default、Probe 与 demo 三账隔离；没有为了少一步启动去重写长期数据库事实。
- 用户确认前允许推进：该阶段已结束，方案已冻结。
- 用户确认前禁止推进：决策限制已解除；但本轮仍只更新 plan，必须等用户明确发起 M50 开发后才创建/重建 `datapilot_demo`，且不得修改 `.env` 默认数据库或触碰 `datapilot_dev`。
- 需要确认的时点：已于 2026-08-28 确认，无待决项。
- 重开决策的条件：隔离数据库无法在现有 MySQL 权限下创建，或 seed 对 MySQL demo adapter 出现无法在本模块内安全闭合的真实缺口；届时暂停，不自动回退到 reset `datapilot_dev`。

## 8. 验证与验收矩阵

### Live Dev Probe（开发期真实探针）

M50 会改变真实 API 多轮的消费方式，并把 Qwen/MySQL/RAG 结果映射为用户可见状态；pytest/mock 不能证明 browser → Web transport → FastAPI → Agent runtime → 页面这条真实链。因此适用 Live Dev Probe。standing authorization、计数、禁区、重验与 Formal Eval 分账统一遵守 `docs/state/runbook.md`「Live Dev Probe」。

| Probe ID / 执行时点 | 探针场景 | 真实产品链路/依赖 | 需要观察的结果与 Trace 事实 | 通过/失败/不确定标准 | 决策与停止条件 |
|---|---|---|---|---|---|
| M50-P1 / after M50-C、before M50-D | 从浏览器用 `ops` start：“查询 2026 年 7 月实际净退款金额” | Browser → Web adapter → `/api/query` task start → Qwen Text2SQL → SQL Guard → `datapilot_demo` MySQL → Response/Trace → UI | question/request shape；runtime=`agent_task`；task v1；SQL/rows/answer 四轴一致；Tool/action/budget/termination；页面 trace id/数值与 Response 一致；无私有 payload | passed：业务 oracle=120000 且 UI/Response/Trace 同源、无误标；failed：已观察到合同/UI错配；inconclusive：真实依赖不可用或 provider transport 未完成 | 首个系统性失败、数据 identity 漂移、provider/预算越界即停；passed→continue，UI mapping 错→revise 后只重验 P1，依赖不可用→保留 inconclusive 并暂停依赖 P1 的 D |
| M50-P2 / after M50-D、before M50-E | 同一 task continue 比较 7/8 月；再 continue 明确提问“比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。”；API 由操作员以既有 server-controlled `subgraph` experimental 配置启动，客户端不提交 strategy | Browser → Web adapter → task continue → Qwen/Text2SQL/MySQL + business Knowledge Subgraph → Hybrid → citation → UI | version 单调使用服务端值；120000/180000/60000/50%；SQL/Document 双 Evidence；Hybrid branches；citation；Knowledge runtime 明确标 experimental；预算/termination；UI 不展示正文 | passed：两轮均 complete，双 Evidence/citation 与页面投影闭合；failed：确定的产品链或 UI/transport/合同错；inconclusive：provider/RAG 依赖不可用或所需自然分支未触发。默认 Pipeline 的 partial/stop 另由 fixture/兼容测试覆盖，不能替代本 Probe 的真实双 Evidence Gate | 总体以“真实链完成且页面忠实展示”为 Gate，不要求借 UI 提升 RAG 质量；系统性产品失败停止，不换 strategy/问法重跑；passed→continue，UI 缺陷→revise，已知质量 no-go 保留边界不调参。2026-08-28 原问法与当前 business admission seam 不闭合且首次 P2 已 `failed → stop`；用户确认方案 A 后只允许按本行修订问法执行一次全新 lineage 的 `M50-P2R`，旧证据不得改写。 |
| M50-P3 / after M50-E、before M50-F | 对 P2 lineage 先提交不存在的 expected version，再以漂移 role 继续；通过页面执行 clear/本地清理 | Browser → Web adapter → FastAPI task boundary/MySQL；深 Tool/provider 应为 0 | `task_version_conflict` 与 `task_unavailable` 分层；task/runtime invocation=0；页面无成功/自动 retry；clear 后本地 identity/session snapshot 清空；公开错误不枚举 owner/task 事实 | passed：两个负断言精确命中且 provider=0；failed：任何深调用、泄漏、自动重试或旧 task 继续；inconclusive：原 lineage 已不可用而分支未观察 | 任一深调用或泄漏立即 stop；UI mapping 错→revise 后只重验对应负路径；不为 P3 新建模型场景 |

本模块 Probe 额外收紧：

- 只使用 G50-2 确认的 `datapilot_demo`；不访问 `datapilot_dev`、`datapilot_m48_test`、Enterprise external、historical、held-out 或 sealed reserve。
- demo business seed 在 P1/P2 前只读核验；Probe 不 reset/reseed。task checkpoint/event 在场景后 clear，并核对合成 task 状态恢复到 0；恢复失败为独立 `stop`。
- 首次 P1+P2 campaign 的 provider attempts 上限 8、observed tokens 上限 30000、retry=0；实际证据与一次 9/8 越界永久保留。2026-08-28 用户确认方案 A，另行授权一次 `M50-P2R` 全新 lineage：从 P1 SQL start、比较 continue 到修订后的明确 Hybrid continue，独立上限 6 provider attempts / 30000 observed tokens、retry=0；不得再追加重试、换 strategy/问法或与首次账本混算。P3 预期 0 provider。
- P2 的 Subgraph 若启用，必须是启动时 server-controlled experimental 配置，页面只读 runtime identity；这不构成默认切换或质量胜出。
- 每个 Probe 保存浏览器截图、validated response 安全摘要、trace locator/identity 与 usage；截图只证明展示，不替代 Response/Trace 业务事实。
- 当前无需 Formal Eval：M50 不修改 Agent quality/route/retrieval/SQL 合同，正式 Text2SQL/RAG suite 不因前端展示重复运行。若条件触发修改后端业务合同，必须重新评估并单独取得对应 selector 授权。

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 | Python contract fixture + runtime schema mutation tests | 当前 fixture 全部通过；核心字段缺失/enum 漂移稳定拒绝；OpenAPI/fixture identity 漂移会阻断 | 必须完成 |
| C2 | client module tests + Playwright lifecycle + P1/P3 | 请求 shape/version 正确；single-flight；success 才推进版本；stale/unknown 不自动 retry | 必须完成 |
| C3 | transport adapter fake + BFF integration | 422/product/timeout/unreachable/non-JSON/contract-invalid 分层且不泄漏 raw error | 必须完成 |
| C4 | presenter closed-world table tests | 每个已登记组合唯一主状态；未知组合 fail closed；blocked/partial 不误标 | 必须完成 |
| C5 | render tests + chart fault injection + P2 | SQL/table/chart/citation/Hybrid/Inspector 与公开 response 一致；chart 可降级；无私有旁路 | 必须完成 |
| C6 | preset manifest validator + demo preflight + P1/P2 | 每个 preset 有依赖、runtime、turn、预期类别、边界；招牌故事可重复 | 必须完成 |
| C7 | legacy request/response fixture + Playwright | clarification/follow-up 仅由 server spec 出现且预算最多一次；不混 task | 必须完成 |
| C8 | storage codec tests + clear/refresh E2E | 仅保存 allowlist、有界、last-acknowledged 数据；不兼容即丢弃；clear 同步清理 | 建议完成；若不做持久化则必须明确内存边界 |
| 工程质量 | clean install、build、typecheck、lint、unit、Playwright | 全部 exit 0，lockfile 可复现，无 node_modules/build 产物入库 | 必须完成 |
| 后端兼容 | M5/M35–M38/M43–M49 受影响聚焦；全仓 pytest 后台 | 旧 legacy 与 agent_task 原断言不放宽；全仓无 M50 引入回归 | 必须完成 |

验证顺序：contract/presenter 单元 → 模块渲染 → BFF/client integration → Playwright fixture → P1 → P2 → negative/legacy → P3 → build/clean install → Python 聚焦 → 后台全仓。真实 Probe 不能替代 deterministic 测试，fixture 通过也不能替代真实链。

## 9. 依赖与交付物

### 依赖

- 已完成的 M43～M49 task、Loop、B4、durable boundary、Context/Compact 与 evidence-backed assurance。
- `app/schemas/agent.py` / FastAPI OpenAPI 的公开合同，`app/api/query.py` 的唯一投影，`/health` 与 `/health/rag`。
- G50-1 选择的 Node/TypeScript runtime；npm 锁文件。
- G50-2 选择的演示数据库、MySQL 0005、Phase 4B seed profile；真实 P2 还依赖 Qwen 和 business active release。
- `docs/state/runbook.md`、Text2SQL/RAG runbook、数据库/RAG state 与现有安全/Probe 纪律。

### 交付物

- `web/` 单一前端工程及锁文件；深 `DataPilotClient` 与纯 `ResponsePresenter` 两个主要 module interface。
- task workspace、结果/图表/citation/Hybrid/Inspector、legacy compatibility、全状态 gallery。
- Python-authoritative contract fixtures、frontend unit/module/Playwright tests、必要的 Python compatibility tests。
- G50-2 方案 A 时的受保护 demo prepare/preflight 入口与版本化 preset manifest。
- `docs/notes/m50-notes.md`、启动/演示说明、架构图、截图；收工时更新 AGENTS 目录、AI_CONTEXT、Phase 4B 后续技术历史和阶段末 README。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：公网 deployment/auth/abuse boundary、streaming、MCP、Eval Dashboard、全量数据导出、生产 task 查询/恢复端点。这些不是 M50 最终目标的一部分，因此 M50 不以“以后优化”承诺它们，也不宣称相应能力完成。
- 下一模块可直接消费的产物：没有预先指定下一模块编号。`DataPilotClient` interface 与 validated response/presenter 可被将来经独立立项的部署或 MCP adapter 复用，但复用可能性不是 M50 验收项。
- 后续需要根据真实失败重新规划的内容：只有 P1/P2 证明普通 request/response 等待体验不可接受，才可另立有编号模块评估 SSE/event streaming；只有真实公网求职需求成立且后端认证/成本/滥用边界有方案，才可另立部署模块。未满足重开门时不启动。
- 可能存在的风险：Qwen 比较 turn 已实测可超过 120s；BFF/browser timeout 与 unknown outcome UX 需要真实 Probe 校准。external RAG readiness 约需额外启动时间；M50 默认 preset 不用 external，避免把 Milvus 依赖伪装成所有页面的硬前置。

## 11. 开工条件

- 开工前无需再次确认：G50-1/G50-2 已于 2026-08-28 选择方案 A；Phase 4B task 作为主展示、legacy 作为兼容；Python/FastAPI 为 Agent authority；不做 streaming/public deploy/MCP/Eval Dashboard；前端不得选择 RAG strategy/corpus/model；采用 npm 并提交 lockfile。
- 实施中需要确认：无。只有触发重开条件、计划外真实 Probe、扩大 provider/token 预算、新数据出站、默认切换或越出 `datapilot_demo` 的数据库写入时，才按对应规则重新确认。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支。尤其是任何默认数据库/reset、公开响应新增字段、server-controlled runtime 切换或新数据出站，都不能由前端实现便利自动获得授权。
