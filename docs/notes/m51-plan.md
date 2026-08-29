# M51 TypeScript MCP Adapter 开发计划

> 能力里程碑：Phase 4B 后续外部协议集成切片；把已完成的 DataPilot Agent 能力接入本地 MCP Client，不新增或改写 Phase 4B Agent 里程碑
>
> 主要问题：在不复制 Python Agent、业务合同和身份授权的前提下，让标准 MCP Client 通过一个有界 Tool 安全调用 DataPilot，并诚实处理多轮 task、失败和未知结果

> 2026-08-29 收口修订：用户确认 M51 按“本地 stdio 协议适配器基础闭环”结束。真实 SQL happy path、单 Tool、bounded result、task/version、status/clear、unknown/no-retry 与负路径属于本模块完成门；真实政策 RAG/Hybrid happy path 延后为独立 `M51R`，在其完成前不得宣称该能力完成。详细待办与重开条件保存在仓库外 `D:\.Work\Practice\Python-Practice\DevProbe-todo.md`，M52 仍只负责远程 MCP/OAuth，不吸收这项缺口。

## 1. 模块定义与范围判断

M50 已把 `/api/query` 接成第一个 TypeScript consumer，但当前入口仍只服务浏览器工作台；Claude、Cursor、MCP Inspector 或其他本地 MCP Client 还不能通过标准 Tool 调用 DataPilot。`docs/todo.md` 已把“本地 stdio + 单一 Tool + FastAPI authority + task/version + bounded result”列为候选首版边界，`docs/state/AI_CONTEXT.md` 与 M50 Handoff 也明确要求 MCP 独立立项。

M51 围绕一个问题形成闭环：**本地 MCP Client 能否通过一个标准、受限、可验证的 adapter 使用现有 DataPilot**。范围包含 MCP stdio 协议、HTTP transport、公开结果裁剪、多轮 task 对账、错误映射、客户端配置和真实纵向 Probe，适合在一个模块中学习、演示和验收。它不把公网 transport、OAuth 或生产 caller 一并塞入首版；这些能力需要另一套威胁模型和部署验收，合并会使本模块失控。

完成后用户可以演示：MCP Client 只看到一个 `data_pilot_query` Tool；用自然语言发起 SQL 分析，并携带服务端签发的 task id/version 执行继续查询或状态对账；结果包含答案、四轴状态、route、有界 SQL/rows/citations、reason、trace 和最小 task 信息；输入错误、旧版本、身份不可用、timeout 和合同漂移不会触发自动重放或泄漏内部 Trace。真实政策 RAG/Hybrid 展示不属于本次完成声明。

本模块的完成声明严格限于“**本地 stdio MCP adapter 技术闭环**”。远程 MCP/OAuth/生产多租户不是被缩水后遗留的 M51 验收项，而是独立部署与身份能力；若满足第 10 节硬触发条件，固定由 M52 另立计划，M51 不提前宣称生产 MCP 能力。

## 2. 当前事实与问题

| 当前事实 | 导致的问题 | 事实来源 |
|---|---|---|
| FastAPI `POST /api/query` 是 legacy/task 的唯一业务入口，Router、Loop、SQL/RAG/Hybrid、Evidence 与状态机均在服务端 | MCP 只能做协议 adapter；若复制路由或拆 SQL/RAG Tool，会形成安全旁路和第二业务 authority | `app/api/query.py::query`、`app/schemas/agent.py::QueryRequest/AgentResponse`、`docs/phase4b-roadmap.md` §2.1/§4.7 |
| 本地/demo/test 才注入 fixture caller；请求 `user_role` 不能自行授权，生产认证尚未建设 | MCP Tool 输入不能暴露可自由选择的 role；首版必须由本地进程配置固定 demo/test role，并限制 loopback FastAPI | `engine/harness/caller.py::build_default_caller_resolver`、`app/main.py`、`docs/state/AI_CONTEXT.md`“Caller” |
| task mutation 使用服务端 task id、expected version、CAS 和 typed rejection；timeout/abort/合同漂移是 unknown outcome，不能自动 retry | adapter 必须原样延续 last-acknowledged version，并提供 status 对账/clear；仅封装一次 POST 不足以闭合真实多轮 | `app/schemas/agent.py::TaskRequestEnvelope`、`app/api/query.py::get_query_task_status/clear_query_task`、`web/lib/data-pilot-client.ts` |
| Python/Pydantic 是唯一业务合同 authority；M50 的 Zod 只是网络漂移门 | 新 MCP consumer 若再手抄一份完整响应，会产生第三份漂移面；但 MCP 的 bounded output 又不能直接等于完整 `AgentResponse` | `web/lib/contracts.ts`、`tests/test_m50_web_contract.py`、`docs/notes/m50-plan.md::C1` |
| M50 `DataPilotClient` 绑定浏览器相对 URL和 Next BFF，不能直接由独立 stdio 子进程复用 | M51 可复用其错误语义与 fixture 方法，不能把浏览器 client 当通用 SDK | `web/lib/data-pilot-client.ts`、`web/lib/server-adapter.ts` |
| 当前响应允许 rows、动态 record 和公开 Agent 投影；MCP 候选要求 bounded structured result | 必须新增不可逆的公开 projector，限制数量、字节和字段；不能把完整 Trace、private Evidence、state/context 或无界 rows交给 Client | `app/schemas/agent.py::AgentResponse`、`docs/state/runbook.md`“Trace / LangFuse”、`docs/todo.md` |
| 当前 Node 24、TypeScript 6、Zod 4.4 已可用；MCP 官方 SDK v2 已拆分 server/client package，并以 `registerTool`、`outputSchema`、`structuredContent` 和 `serveStdio` 为当前接口 | 需要在开工前选择 v2 还是旧 v1，锁定依赖和兼容测试，不能把网上旧单包示例与新接口混用 | `web/package.json`；官方 `typescript-sdk` 的 `docs/migration/upgrade-to-v2.md`、`packages/server/src/server/mcp.ts`、`docs/serving/stdio.md` |
| 工作区已有用户修改的 `docs/ref-discussion/Agent 测评 的讨论.md` 和未跟踪 `docs/todo.md` | M51 只能新增/修改自身交付范围，不能覆盖或顺手整理这些文件 | 计划调查时 `git status --short` |

## 3. 参考源码定点复核

现有 `docs/phase4-reference.md` 没有 MCP server 入口；按其 §1、§3 和 Phase 4B roadmap §17.1 的开放边界，本模块补读 MCP 官方 TypeScript SDK 源码/文档，并以 DataPilot 自身 M50/Phase 4B 源码作为安全事实源。这里不把官方示例当成 DataPilot 的认证、幂等或数据边界证明。

| 本模块问题 | 参考项目与源码入口 | 借鉴内容 | DataPilot 如何适配 | 明确不照搬 |
|---|---|---|---|---|
| 单 Tool 的输入/输出合同和错误 | `modelcontextprotocol/typescript-sdk/packages/server/src/server/mcp.ts::McpServer.registerTool/validateToolOutput`；`examples/guides/servers/tools.examples.ts` | `inputSchema` 在 handler 前校验；`outputSchema` 校验 `structuredContent`；业务可读错误用 `isError` | 只注册 `data_pilot_query`；成功/typed product result 返回 text + bounded `structuredContent`，transport/contract 失败返回安全 `isError` | 不把 schema validation 当业务授权；不把 thrown stack、FastAPI detail 或完整响应直接返给模型 |
| 本地 stdio 生命周期与日志安全 | `modelcontextprotocol/typescript-sdk/docs/serving/stdio.md::serveStdio`；对应 `@modelcontextprotocol/server/stdio` 入口 | factory 创建 server；stdout 专用于 JSON-RPC，日志走 stderr；Inspector 可直接启动子进程 | 独立 Node 进程只通过 stdio 服务；启动、诊断和请求日志均结构化写 stderr，生产 Tool handler 不 `console.log` | 不在 M51 增加 Streamable HTTP、SSE、常驻公网 server 或 OAuth |
| 协议级集成测试 | `modelcontextprotocol/typescript-sdk/examples/guides/testing.examples.ts`；`docs/clients/connect.md::StdioClientTransport/InMemoryTransport` | 内存 linked pair 验证 tool list/call；spawn stdio 覆盖真实进程/管道 | 单元/模块测试走内存 transport；另有构建产物子进程测试验证 stdout 洁净、tool schema 和 call result | 不用直接调用 handler 的测试冒充 stdio 兼容；不以 Inspector 人工截图代替自动化 |
| 第二个 TypeScript consumer 的 seam | `web/lib/contracts.ts`、`web/lib/data-pilot-client.ts::decode/DataPilotClient`、`scripts/export_m50_web_contract_fixtures.py` | Python-authoritative fixture、网络 runtime gate、known rejection/unknown outcome 分层 | G51-2 选择共享网络 schema 包或独立窄 schema；无论哪案都由 Python fixture/identity 阻断漂移 | 不把 Web presenter/session 状态、相对 URL、BFF 或 UI 文案搬进 MCP；不让 TypeScript 反向定义 Pydantic |
| task/version 与 owner 安全 | `app/api/query.py::query/get_query_task_status/clear_query_task`、`engine/phase4b/task_boundary.py`、`engine/phase4b/mysql_task_boundary.py` | task id/version 由服务端签发；status 只读；错误 owner/未知 task 统一 `task_unavailable`；mutation 不重放 | 单 Tool 内用 closed-world operation 分派 POST/GET/DELETE；role 只来自本地 adapter config，task/version 只来自上一次已确认结果或显式 status | 不在 adapter 缓存/猜测 TaskState，不把 MCP client identity 冒充业务 caller，不新增 client-supplied tenant/role/runtime 字段 |

参考覆盖边界：官方 SDK 能证明 MCP schema、transport 和测试接口，不证明 Claude/Cursor 各版本 UI、DataPilot 业务正确性、FastAPI caller 安全或 exactly-once；后四项分别由兼容配置示例、真实 stdio Probe、现有服务端合同和 unknown-outcome 语义验收。

## 4. 目标、优先级与非目标

### 模块完成状态

在文档声明的本地环境中，标准 MCP Client 能启动构建后的 stdio server，列出且只列出 `data_pilot_query`，完成 start/continue/status/clear 的受控调用；每次调用都经过 FastAPI 现有安全链，返回有界公开结果或安全错误，并能用 trace/task/version 对账。Web 与后端既有合同不回归。

### 必须完成

- 独立、可 clean install/build/test 的 Node + TypeScript MCP 工程和 lockfile，使用用户确认的 SDK major。
- 单一 `data_pilot_query` Tool；不按 SQL/RAG/Hybrid 拆 Tool，不允许客户端选择 model、corpus、RAG strategy、tenant 或 role。
- Tool input 使用 closed-world operation：`query`、`status`、`clear`。`query` 支持 start/continue/switch/cancel 的严格 task envelope；status/clear 复用服务端 GET/DELETE seam。
- loopback-only HTTP adapter、固定 demo/test role、有限 timeout、无 mutation retry、known/unknown outcome 分层。
- 通过 output schema 的 bounded structured result 和简短 text 摘要；字段/数量/字节/总大小均可测试，私有 Evidence、完整 Trace、TaskState/Context、Prompt、raw error 永不输出。
- Python-authoritative contract drift Gate；Web + MCP 两个 TypeScript consumer 对共享网络字段的策略由 G51-2 明确冻结。
- SDK client 内存集成、真实 stdio 子进程、HTTP fake、bounded projector、task/version/negative matrix、clean build 与既有回归。
- 按切片时点执行 M51-P1～P3，留下 Response/MCP result/Trace/usage/task safe ref 与清理证据。
- Claude/Cursor/MCP Inspector 的本地配置示例、启动前置、失败排查和能力边界说明。

### 建议完成

- 为结果 schema、server/tool identity 和 Python fixture 集生成可复核 identity，便于 Client/Trace 对账。
- stderr 使用有界、无敏感内容的结构化日志，并提供 `DATAPILOT_MCP_LOG_LEVEL` 等本地运行配置。
- 在不增加第二 Tool 的前提下，为 `status`/`clear` 返回短而明确的下一步提示。

### 条件触发

- **触发条件**：G51-2 方案 A 的 spike 证明共享包可被 MCP 和 Web clean install/build，且只承载两者真实共用的网络 schema，不迫使 MCP 依赖 Next/browser。
- **允许动作**：抽取共享 TypeScript 网络合同包，迁移 Web import，并保持 Python fixture/identity 为 authority。
- **未触发时**：采用方案 B 的 MCP 窄 schema + 独立 fixture parity；不得让 MCP 直接跨目录导入 `web/lib/contracts.ts`。

### 明确非目标

- Streamable HTTP/SSE、远程 MCP hosting、公网部署、OAuth/JWT/SSO、生产 caller、多租户目录与滥用/计费控制。
- 第二个 SQL/RAG/Hybrid Tool、MCP resources/prompts、动态 Tool 注册、Tool discovery 代理或通用 connector 平台。
- 修改 Router、Agent Loop、RAG default、TaskState、Evidence Gate、SQL Guard、数据库 schema、active release、模型或 outbound policy。
- 把 MCP Client 提供的 role/tenant/task state/route/runtime 当成可信授权或业务事实。
- streaming/progress notification、后台 MCP task、自动 retry、exactly-once 承诺或跨进程本地缓存。
- 输出 chart spec、完整 action/node/Context ledger、完整 docs、完整 Trace、private Evidence、Thought、Prompt 或无界导出。
- 用 MCP 接入结果宣称 RAG/LLM 质量提高、Subgraph 胜出、生产 readiness 或通用客户端全部兼容。

## 5. 关键合同

### C1：单 Tool 与可信输入

- 输入：唯一 Tool `data_pilot_query`；closed-world `operation=query|status|clear`。`query` 接收 UTF-8 最多 4096 bytes 的 question 与严格 task action；非 start 必须同时提供服务端签发的 task id（1～128 字符）和正整数 expected version。status 只接 task id，clear 接 task id + expected version。
- 成功输出：SDK 已验证的 handler 参数；operation 被确定性映射到现有 POST/GET/DELETE，不把 Client 输入拼为其他路径或字段。
- 失败语义：shape/长度/互斥错误在 HTTP 前拒绝；不产生 provider、Graph、Tool 或 task mutation。
- 必须保持的不变量：Tool schema 不含 user role、tenant、model、corpus、RAG strategy、Evidence、route 或任意 backend URL；本地 role 和 loopback base URL只由 operator 配置；只注册一个 Tool。
- 本模块不冻结的实现细节：Zod schema 的文件名、factory 名称和内部 DTO 命名。

### C2：HTTP delegation 与 unknown outcome

- 输入：C1 的已验证 operation、adapter 固定 config、AbortSignal/timeout。
- 成功输出：一次且仅一次对应 HTTP 请求和通过网络 schema 的 FastAPI 公开响应。
- 失败语义：至少区分 `request_invalid/not_sent`、`backend_rejected/known_rejected`、`backend_unreachable`、`backend_timeout`、`backend_invalid_response`、`response_contract_invalid`；POST query 与 DELETE clear 在发送后无法证明是否提交时必须是 `outcome_unknown`，GET status 失败不能改写 task 状态。
- 必须保持的不变量：mutation retry=0；不跟随非 loopback redirect；不缓存或改写业务结果；HTTP 非成功、raw detail、stack、driver/provider error 只转为 allowlist 安全文案；unknown 后只能显式 status 对账，不能自动重发原 mutation。
- 本模块不冻结的实现细节：使用原生 fetch 还是一层很薄的 transport helper；timeout 默认值在不短于当前 Web 300s 基线的前提下由实现 spike 与 P1/P2 记录最终值。

### C3：bounded MCP result

- 输入：通过 Python-authoritative 网络 schema 的 `AgentResponse`、TaskStatusResponse 或 TaskControlResponse。
- 成功输出：text 摘要 + `structuredContent`。query 只含 `answer`、`route`、`execution_status`、`answer_status`、`safety_status`、`reason_code`、可选 SQL、columns/rows、citations、`trace_id`、`runtime_family` 和最小 `task{id,version,status,expires_at}`；status/clear 返回 operation、ok、reason/safety/message 和同等级最小 task 投影。
- 失败语义：投影或 output schema 不成立时失败关闭为安全 `isError`，不回退到完整 FastAPI JSON。
- 必须保持的不变量：answer≤16 KiB、SQL≤16 KiB、columns≤20、rows≤50、单个 cell 的 UTF-8 表示≤2 KiB、citations≤16 且只允许 `evidence_id/title/anchor`，最终 structured JSON≤64 KiB；超限按固定优先级裁剪可选 rows/citations/text并设置 `truncated` 与原始计数，永远保留四轴、reason、trace 和 task/version。不得输出 docs_used、chart_spec、tool_calls、task state/context/delta/transition、node/action/budget/termination ledger、runtime config、private Evidence 或完整 Trace。
- 本模块不冻结的实现细节：内部 byte counter、稳定 key 排序与 cell normalizer 的具体函数拆分；实现必须对 Unicode/Decimal/date/nested value 做确定性安全字符串化。

### C4：task continuity、status 与 clear

- 输入：start 的已确认 query result；后续 Client 显式回传该结果中的 task id/version；unknown 后显式 status；clear 使用最后已确认或 status 对账后的 version。
- 成功输出：start/continue/switch/cancel 沿用服务端 action；只有完整 MCP result 通过 output schema 后才把 task/version视为 acknowledged；status 不消费 claim，clear 返回服务端事实。
- 失败语义：`task_version_conflict`、`task_unavailable` 等 typed product rejection 仍返回有界 product result，不伪装成 transport 成功回答；unknown 不推进/回退 version；claimed status 提示继续等待/人工处理而不重放。
- 必须保持的不变量：adapter 不持久化 TaskState、不自增/猜测 version、不把 raw MCP session/client identity 当 owner、不跨 task 复用 id、不在 cancel/clear 后继续旧 lineage。
- 本模块不冻结的实现细节：Client 是否把返回的 task 投影放入自己的会话上下文；adapter 本身保持无业务会话状态。

### C5：MCP protocol、错误与日志

- 输入：SDK initialize/list/call/close、tool handler result、进程信号。
- 成功输出：stdio 上仅有合法 MCP JSON-RPC；tool list 稳定且只有一个 Tool；正常 product result 同时提供短 text 和 structuredContent；进程可正常关闭。
- 失败语义：协议输入由 SDK 处理；可供模型修正的 Tool 失败使用 `isError` + 安全文案；未捕获异常有顶层安全映射和 stderr 诊断，不泄漏到 Tool result。
- 必须保持的不变量：禁止 stdout 日志；annotations 明示不是只读/幂等 Tool，但 annotation 仅是提示、不是安全控制；server/tool/version identity 可复核；关闭不制造新的 HTTP 调用。
- 本模块不冻结的实现细节：stderr 日志库或原生 writer；不为日志引入平台级依赖。

### C6：跨语言 authority 与漂移门

- 输入：Pydantic/OpenAPI、Python-authoritative response fixtures、MCP input/output schema、G51-2 的共享或独立实现。
- 成功输出：fixture 先通过 Python model，再通过 TypeScript network gate 和 bounded projector；schema/fixture identity 可重签；缺 core 字段、enum 漂移和超界稳定阻断。
- 失败语义：合同漂移在测试或运行时失败关闭；不宽松接收后继续调用/展示。
- 必须保持的不变量：Python/Pydantic 唯一业务 authority；TypeScript 只定义 transport validation 与 MCP 专属 bounded projection；Web presenter/MCP output 各自保持消费侧职责。
- 本模块不冻结的实现细节：共享 package 的路径和发布名由 G51-2 后的最小 spike 决定；不发布 npm registry。

## 6. 工作切片与执行顺序

### M51-A：工程基线、SDK 与合同 seam

- 优先级：必须完成
- 依赖：G51-1、G51-2 用户确认；开工先建立 `docs/notes/m51-notes.md` checklist 并登记 P1～P3
- 实施内容：初始化独立 MCP 工程/lockfile；用最小 spike 验证 SDK Tool schema、structured output、stdio build 和 Node 24；执行 G51-2 的共享面盘点；建立 Python fixture/identity → TypeScript network gate → bounded output 的漂移链。
- 关键合同：C1、C5、C6
- 交付物：可重复安装/构建的空 server、锁定依赖、合同 fixture/identity、G51-2 实施结果
- 验证方式：clean install、typecheck、SDK 内存 list/call spike、fixture mutation tests；若方案 A，还需 Web clean typecheck/test
- Live Probe checkpoint：不适用；只处理本地协议/fixture，不调用 FastAPI、数据库或 provider
- 完成门：SDK major 与 schema 形式不混用；Python authority 清晰；MCP 不跨目录偷引 Web 私有模块；tool list 已稳定为单 Tool

### M51-B：stdio server 与单 Tool HTTP 纵向骨架

- 优先级：必须完成
- 依赖：M51-A
- 实施内容：注册 `data_pilot_query`；实现 loopback config、固定 role、operation dispatcher、POST/GET/DELETE HTTP adapter、timeout/abort、无 retry、stderr logging 和安全错误映射；先贯通 fake FastAPI。
- 关键合同：C1、C2、C5
- 交付物：可由 SDK client/Inspector 启动的 stdio server 和可替换测试 transport
- 验证方式：HTTP fake 断言请求 path/body/role/次数；redirect/timeout/non-JSON/422/5xx/abort matrix；stdout 污染测试
- Live Probe checkpoint：不适用；此切片只用本地 fake，不调用真实产品链
- 完成门：每次 operation 至多一次 HTTP；Client 无法提交 role/backend/runtime；错误无 raw detail；server 可初始化、list、close

### M51-C：bounded projector 与 task happy path

- 优先级：必须完成
- 依赖：M51-B
- 实施内容：实现 C3 projector、output schema、text summary；贯通 start/continue 的 task envelope 与 last-acknowledged 语义；覆盖 SQL/RAG/Hybrid/partial/blocked/unavailable fixture。
- 关键合同：C3、C4、C6
- 交付物：稳定的 MCP input/output contract 和 task-aware handler
- 验证方式：byte/count/Unicode/nested cell/property tests；fixture snapshot；SDK client 验证 structuredContent 与 advertised output schema；真实环境执行 M51-P1
- Live Probe checkpoint：M51-P1 / after M51-C、before M51-D；只有 `continue` 才放行 unknown/status/negative 收口
- 完成门：P1 已形成三态和处置；SQL happy path 经真实 stdio → HTTP → Agent 完成；MCP 结果与 Response/Trace/task version 同源且不越界

### M51-D：unknown 对账、安全负路径与 lifecycle

- 优先级：必须完成
- 依赖：M51-P1=`passed → continue`
- 实施内容：闭合 status/clear、stale version、task unavailable、claimed/terminal、timeout/contract drift unknown；确保 product rejection 与 transport error 不混淆；补真实 stdio child-process integration。
- 关键合同：C2、C4、C5
- 交付物：可恢复但不重放的 task lifecycle 和完整 negative matrix
- 验证方式：SDK spawn 测试；fake/integration 覆盖 status/clear 与 0 retry；真实环境依次执行 M51-P2、M51-P3
- Live Probe checkpoint：M51-P2、P3 / after M51-D、before M51-E；P2 验证同 lineage Hybrid，P3 验证输入/旧版本/status/clear 且阻塞文档与收工冻结
- 完成门：P3 有明确处置；旧版本和错误输入不产生额外 provider/deep invocation；unknown 不自动重放；精确 task 清理完成。原 P2 的真实政策 RAG/Hybrid oracle 经用户确认移交 M51R，不再阻塞 M51-E，也不得被记为通过。

### M51-E：客户端接入、回归与技术收工准备

- 优先级：必须完成
- 依赖：P1 的 SQL happy path与 P3 lifecycle/negative 已闭合；adapter 自身不存在未处理的 `revise/stop`；真实政策 RAG/Hybrid 已明确移交 M51R
- 实施内容：补 Claude/Cursor/Inspector 配置示例、启动/preflight/排障/能力边界；完成 clean install/build/test、Web 回归、Python 聚焦与全仓验证；冻结 notes、state/changelog/runbook/AGENTS 目录入口，随后按用户命令进入 `finish-module`。
- 关键合同：C1～C6
- 交付物：最终 MCP 工程、自动化测试、配置示例、运行说明和开发证据
- 验证方式：从构建产物启动的 SDK stdio acceptance；Inspector 人工 smoke 只作补充；Node 全套、Web 受影响回归、Python 聚焦、后台全仓 pytest、`git diff --check`
- Live Probe checkpoint：不新增；只审计 P1～P3 原时点证据，禁止在收工首次补跑冒充开发期 Probe
- 完成门：新环境能按文档连接本地 Client；所有自动化通过或有明确非产品阻断；文档只声明本地 stdio 技术闭环

## 7. 决策门

### G51-1：MCP TypeScript SDK major

#### 方案 A：官方 v2 server/client 分包（建议）

- 做法：使用当前 `@modelcontextprotocol/server`/`client` v2 major、Zod 4 object schema、`registerTool`、`outputSchema`、`serveStdio`；由 lockfile 固定实施时版本，并用 legacy negotiation/真实 stdio 测试覆盖常见 2025-era Client。
- 影响：与当前官方接口、Zod 4 和结构化输出方向一致，未来少一次 v1→v2 迁移；server/client 测试依赖更清晰。
- 适用条件：本机 Node 24 clean build 通过，Claude/Cursor/Inspector 至少通过标准 stdio 协议验收，v2 的兼容层满足首版客户端。
- 风险：v2 在当前官方 release notes 中仍带首个 beta/新协议迁移背景；生态旧示例多，Client 兼容需要实际验证。

#### 方案 B：旧 `@modelcontextprotocol/sdk` v1 stable

- 做法：使用 v1 单包、旧 stdio transport 与对应 raw-shape registration 形式；严禁混用 v2 object schema 示例。
- 影响：短期跟随既有客户端/教程更保守，但会新增已知迁移债务，structured output/schema 测试写法也与当前官方主线不同。
- 适用条件：v2 spike 在目标 Claude/Cursor/Inspector 上出现可复现的协议阻断，且官方 legacy negotiation 不能解决。
- 风险：为首版兼容选择旧接口，后续升级会改 package、registration、transport 和测试；不能把“教程更多”当长期优势。

#### 建议与确认时点

- 建议：方案 A。
- 建议理由：当前项目已是 Zod 4/TypeScript 6/Node 24，v2 能直接用标准 schema + output validation；首版又需要 structuredContent、真实 stdio 和未来可维护性。兼容风险应由 spike 和 spawn test 证明，而不是先永久停在旧 major。
- 用户确认前允许推进：本计划、只读源码调查、fixture/合同清单。
- 用户确认前禁止推进：创建 MCP package、安装/锁定 SDK、编写依赖特定 registration/transport 代码。
- 需要确认的时点：M51 开工前。
- 重开决策的条件：目标 Client 出现可复现的 v2 stdio/negotiation 阻断，且官方文档/兼容配置无法修复；此时先提交证据，再决定降到 B，不能静默双栈。

### G51-2：第二个 TypeScript consumer 的网络合同 seam

#### 方案 A：抽取共享网络校验包（建议）

- 做法：把 Web 与 MCP 真正共同消费的 QueryRequest/AgentResponse/task status/control Zod 网络 schema 抽成仓库内私有 package；Python exporter/fixture identity 继续签发 authority。Web presenter/session/BFF 和 MCP bounded output 各留在自身工程。
- 影响：两 consumer 只维护一份网络漂移门，后端字段/enum 变化能统一阻断；需要调整 Web 安装/import/lockfile 并增加 workspace/package 构建纪律。
- 适用条件：M51-A spike 证明 package 不依赖 Next/browser/server-only，Web 与 MCP 均可 clean install/build，且抽取后 interface 明显小于两个实现的重复复杂度。
- 风险：如果把 UI presenter、MCP result 或整份 OpenAPI 都塞入包，会变成浅“大合同包”；workspace 改造也可能扩大 M51 回归面。

#### 方案 B：MCP 独立窄 schema + Python fixture parity

- 做法：Web 保持现状；MCP 只定义自己真正消费的 FastAPI core 字段和 bounded result，并用同一 Python fixture/export identity 做跨语言漂移测试。
- 影响：改动范围更窄，但核心 route/四轴/task 字段会存在两份消费侧 schema，需要靠 fixture Gate 防止分叉。
- 适用条件：共享包 spike 会迫使 MCP 依赖 Next/browser、破坏 Web clean install，或两者真实重合面不足以形成深 module。
- 风险：未来第三个 TypeScript consumer 会继续放大重复；维护者容易只更新一侧。

#### 建议与确认时点

- 建议：方案 A，并以“只共享网络 schema、绝不共享 UI/MCP projector”为硬边界；若 M51-A 的 clean spike 不满足适用条件，带证据退回 B。
- 建议理由：`docs/todo.md` 的重评触发条件已经满足——M50 Web 存在，M51 将成为第二个 TypeScript consumer；QueryRequest/AgentResponse/status/control 是真实共同 seam，Python fixture 又已有成熟 authority。现在抽取比复制后再迁移更容易保持 locality。
- 用户确认前允许推进：本计划和只读重合面盘点。
- 用户确认前禁止推进：移动 `web/lib/contracts.ts`、建立 root workspace/共享 package、修改 Web lockfile/import。
- 需要确认的时点：M51 开工前，与 G51-1 一并确认。
- 重开决策的条件：spike 证明方案 A 破坏 clean install、产生 Next/browser 依赖或共享 interface 比重复实现更复杂；记录证据后采用 B，不降低 C6 漂移门。

## 8. 验证与验收矩阵

### Live Dev Probe（开发期真实探针）

M51 新增真实 MCP 外部 runtime，改变 `/api/query` 多轮的消费方式，并必须证明 stdio、HTTP、Qwen/MySQL/Knowledge、MCP output 与 task/version 能真实贯通；fake/pytest 无法证明，因此适用 Live Dev Probe。standing authorization、计数、禁区、重验与 Formal Eval 分账统一遵守 `docs/state/runbook.md`“Live Dev Probe”。

| Probe ID / 执行时点 | 探针场景 | 真实产品链路/依赖 | 需要观察的结果与 Trace 事实 | 通过/失败/不确定标准 | 决策与停止条件 |
|---|---|---|---|---|---|
| M51-P1 / after M51-C、before M51-D | SDK `StdioClientTransport` 启动构建产物，list Tool 后以固定 ops 发起 start：“查询 2026 年 7 月实际净退款金额。” | MCP Client → stdio server → loopback HTTP → `/api/query` task start → Qwen Text2SQL → SQL Guard → `datapilot_demo` MySQL → Response/Trace → bounded result | tool list 只有 `data_pilot_query`；input/output schema；oracle=120000；route/四轴/reason/trace 一致；task v1；SQL/rows 在 C3 限制内；provider usage；无私有字段/stdout 日志 | passed：业务 oracle、协议、Response/Trace/result/task 均闭合；failed：已观察到协议、投影、请求或安全错误；inconclusive：SDK/client/provider/数据库依赖不可用且产品失败关闭 | 首个系统性失败、非 loopback、数据漂移、预算越界即停；passed→continue；实现缺陷→revise 后只重验 P1；依赖不可用→stop/report，阻塞 D |
| M51-P2 / after M51-D、before M51-E | 沿 P1 服务端 task id/version continue：“比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。”；使用产品默认 Pipeline，不由 Client 选 strategy | 同一 MCP lineage → task continue → Qwen/Text2SQL/MySQL + business Knowledge Pipeline → Hybrid/citation → MCP result | version 单调；120000/180000/60000/50%；SQL + Document Evidence 的公开结果；citation≤16；route/四轴/reason/trace；bounded/truncated 计数；Client 输入无 runtime/role | passed：同 lineage Hybrid complete/partial 与服务端事实一致且 task/version 推进；failed：确定的协议/产品投影/安全错误；inconclusive：真实 provider/Knowledge 不可用或自然分支未触发 | 不换 strategy/问法/default 重跑；产品质量 partial 可按真实四轴通过“忠实投影”子门，但总体场景是否通过须按预登记 expected truth；实现错→revise，系统依赖错→stop |
| M51-P3 / after M51-D、before M51-E | 同一进程执行三段负路径：缺 question/非法 operation；用已知旧 version continue；再用当前 task id 做 status 并以确认 version clear | SDK input validation →（零 HTTP）；MCP → FastAPI task pre-rejection/status/clear → Trace | 非法输入 HTTP/provider/Graph=0；stale=`task_version_conflict` 且 provider/deep invocation=0；status 不消费 claim；clear 精确 owner/version；mutation retry=0；最终使用 P1 safe ref 执行 demo cleanup 后 synthetic rows 0/0 | passed：所有 required negative 与清理断言可观察；failed：发生越权、重放、错误 version 推进、泄漏或清理残留；inconclusive：状态依赖不可观察 | 任一额外 provider/deep invocation、错误 owner 泄漏、模糊清理或恢复失败=`stop`；只允许对已修复最小负例重验，不新建替代 lineage |

- P1/P2 共用一条 lineage 以证明 task continuity；P1 后若不能 `continue`，按其三态立即安全清理并停止，不为 P2 另起“更容易通过”的 lineage。P3 的非法输入与 stale/status/clear 为零 provider 场景，不扩大默认 calls/tokens。
- 真实数据固定使用已准备且 preflight 通过的 `datapilot_demo`；Probe 本身只读业务表。task checkpoint/event 属产品必要写入，结束后先走公开 clear，再以已记录的精确 safe ref 使用 M50 cleanup seam，断言 migration/oracle 不变、synthetic rows 0/0；禁止 reset/reseed 或模糊删除。
- 业务语义 oracle：P1=120000；P2 的 SQL 比较值=120000/180000/60000/50%，政策部分以现有 active business release 与四轴/required coverage 的真实结果为准，不能把 partial 强改 complete。安全负断言：Client 不提交 role/runtime/corpus/model，reserved/private 字段为 0，retry=0，stdout 仅协议。
- 总体默认预算沿用 runbook：P1/P2/P3 累计 provider calls≤8、observed tokens≤30000；若实现前依据当前 Qwen 延迟/usage 预计会越界，必须在执行前提交精确扩额决策，不得自行缩短场景或事后补跑。
- 自然允许未触发：SQL dialect repair、provider retry、unknown timeout；它们未自然发生时记对应子能力 `inconclusive/not_exercised`，由 deterministic fault test 覆盖，不能人为制造坏 SQL/网络故障冒充 Probe。P3 登记的 input/stale/status/clear 必须触发。
- Probe evidence 落在 `.agent_work/temp/m51/<probe-id>/`，并在 `m51-notes.md` 立即记录；不写 Formal Eval 分母，不访问 held-out/sealed reserve，不切 active/default。
- 模块完成后建议用户执行的 Formal Eval：当前无需正式 Eval。M51 验证协议忠实性，不提出新的 SQL/RAG 质量候选；P1/P2 不能登记质量基线。

| 能力/合同 | 验证方式 | 通过标准 | 优先级 |
|---|---|---|---|
| C1 | Zod/SDK input mutation + tool list | 只有一个 Tool；互斥/长度/隐藏字段 HTTP 前拒绝；role/runtime 不在 schema | 必须完成 |
| C2 | fake HTTP call counter + timeout/redirect/response matrix | 每 operation 至多一次请求；loopback-only；错误/outcome 正确；raw detail=0 | 必须完成 |
| C3 | property/boundary tests + Python fixture + P1/P2 | 所有字节/数量/总大小硬门成立；核心状态/identity 不被裁掉；private 字段=0 | 必须完成 |
| C4 | task lifecycle integration + P1～P3 | 只采用服务端 id/version；unknown 不推进或重放；status/clear 与 typed rejection 正确 | 必须完成 |
| C5 | SDK in-memory + spawned stdio build + Inspector smoke | initialize/list/call/close 通过；stdout 仅协议；isError/structured result 符合 SDK | 必须完成 |
| C6 | Python exporter/fixture identity + TS drift mutation；方案 A 时 Web 回归 | Pydantic 先验通过；core drift 稳定阻断；Web/MCP 不形成第二业务 authority | 必须完成 |
| 后端兼容 | M43/M47～M50 API/task/contract 聚焦；全仓 pytest | 原 task/version/caller/Trace 断言不放宽；无 M51 引入回归 | 必须完成 |
| 客户端说明 | 构建产物按 Claude/Cursor/Inspector 配置人工核对 | 命令、cwd、env、stdio、前置和边界可按文档复现；不含生产承诺 | 必须完成 |

聚焦测试顺序：pure schema/projector → HTTP fake → SDK in-memory → spawned stdio → Python fixture parity → Web 受影响测试 → P1 → lifecycle/negative → P2/P3 → clean install/build → Python 聚焦 → 后台全仓。真实 Probe 不能替代 deterministic timeout/oversize/contract drift 测试，Inspector 人工成功也不能替代 SDK 自动化。

不可外推：P1/P2 只证明固定本地 Client/场景和当前依赖；不证明所有 Claude/Cursor 版本、远程 transport、并发/性能、生产认证、exactly-once 或回答泛化。历史 M50 fixture/Probe、Phase 4B artifact 和 sealed reserve 全部只读，不得重签为 M51 证据。

## 9. 依赖与交付物

### 依赖

- 已完成的 M43～M49 task/version/durable boundary、M50 Web 网络合同与 demo prepare/preflight/status/cleanup seam。
- `app/schemas/agent.py`、`app/api/query.py`、Python contract fixture/export 与相关 task/caller tests。
- 用户对 G51-1/G51-2 的选择；Node 24/npm；用户确认方案对应的 MCP SDK lockfile。
- P1/P2 执行时本地 `datapilot_demo`、FastAPI、Qwen transport、business Knowledge runtime；依赖不可用按 Probe 三态，不用 fallback 掩盖。

### 交付物

- 独立 TypeScript MCP stdio 工程、lockfile、单 Tool server factory、HTTP adapter、bounded projector 与安全 config/logging。
- G51-2 方案对应的共享网络合同包，或 MCP 独立窄 schema + Python parity；两案均有漂移 identity/test。
- SDK 内存/stdio、HTTP fake、projector/property、task lifecycle、客户端兼容与受影响 Web/Python 自动化。
- Claude/Cursor/MCP Inspector 本地配置和运行/排障文档。
- `docs/notes/m51-notes.md`、Probe 证据、必要的 AGENTS/runbook/AI_CONTEXT/Phase 4B changelog 更新；实现完成后按独立命令执行 `finish-module`。

## 10. 遗留与后续

- 本模块完成但刻意不处理的内容：远程 transport、OAuth/JWT/SSO、生产 caller/tenant、滥用与计费、streaming/progress、MCP resources/prompts、动态 Tool/Connector、exactly-once、性能/HA。
- 下一模块可直接消费的产物：M52 可消费 server factory、bounded result、HTTP port、协议/fixture tests 和 local-client evidence，但不得把 demo role/loopback config 直接升级为生产认证。
- M52 强制开工条件：用户提出非本地/公网 MCP 的明确场景；选定 receiver、部署拓扑和 authenticated caller 来源；完成 threat model、OAuth/JWT/tenant/secret/abuse/cost/observability 方案；提供不依赖请求体 role 的身份绑定；获得新增 outbound/公网暴露和真实 E2E 授权。未同时满足不得开工。
- M52 最终验收标准：远程标准 transport 通过目标 Client E2E；认证 principal 确定性映射 caller/tenant/active role；错身份/跨 tenant/重放/过期 token/限流均 Tool 前失败关闭；secret 不进日志/result；task CAS/unknown reconciliation 保持；有部署、撤销、审计、滥用/成本和回滚证据。达到前不得宣称“生产 MCP”“多租户 MCP”或“公网可用”。
- M51R 强制开工条件：用户重新授权处理 Web/API/MCP 共用的 Phase 4B turn-understanding 与 Knowledge query formation；先建立独立 plan，读取 Phase 4B roadmap、RAG state 和历史，并给出不放宽 Evidence/ACL/Gate 的修复方案与独立 Probe 预算。
- M51R 最终验收标准：同一 MCP lineage 得到 7/8 月 `120000/180000/60000/50%`，同时返回 active business release 支持的全额退款前提/材料和政策 citation；四轴、reason、Trace、task version、bounded projection 与 cleanup `0/0` 同源闭合。达到前不得宣称 MCP 真实政策 RAG/Hybrid happy path 完成。
- 后续需要根据真实失败重新规划的内容：只有目标 Client 形成可复现协议兼容失败，才评估 compatibility shim；只有 C3 的有界结果在真实使用中形成稳定且不可接受的信息不足簇，才另立 result contract 模块，不能临时放大 rows/Trace。
- 可能存在的风险：SDK v2/客户端协议版本快速演进；stdio 进程工作目录/env 配置差异；Qwen 长延迟触发 unknown；完整 FastAPI response 虽公开但仍大于 MCP 所需面；共享 package 若失控会耦合 Web/MCP。分别由 G51-1、C2/C3/C6 和真实 spawn/Probe 控制。

## 11. 开工条件

- 开工前无需确认：M51 只做本地 stdio、单 `data_pilot_query` Tool、FastAPI/Pydantic authority、loopback + demo/test caller、客户端不可选 role/model/corpus/RAG strategy、bounded result、mutation no-retry、Pipeline default、Subgraph experimental/reserve sealed 边界均已由 todo/state/既有合同确定。
- 实施中需要确认：开工前确认 G51-1 与 G51-2；若预计 P1/P2 超过 standing calls/tokens、需要新增数据出站/非 loopback/持久写入/reset/default 切换，或出现计划外真实 Probe，按对应规则单独确认。
- 发现新冲突时：按“依据、选项、做法、影响、适用条件、风险、建议、确认时点”暂停对应分支。尤其是 SDK/Client 兼容要求迫使双协议栈、共享 package 反向定义 Python、Client 要求自带 role/token、或远程 transport 混入 M51 时，不得以实现便利直接扩权。
