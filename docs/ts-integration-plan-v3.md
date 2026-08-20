# DataPilot TypeScript 集成方案 v3

> **文档定位**：在不改写 DataPilot Python/FastAPI Agent 核心、不扩大 Phase 4 已确认能力边界的前提下，为项目补一个适合简历与面试演示的 TypeScript 产品外壳，并保留一个可选的轻量 MCP 接入层。
>
> **核心取舍**：从 v2 的“Demo + MCP Server + Eval Dashboard 三个 TS 目标”收缩为 **一个核心 Next.js Web UI + 一个可选 MCP Adapter**。不为了技术栈展示重复实现 Agent 编排，不为了 UI 强行引入 streaming、通用多轮聊天、完整 Eval 平台或公网后端部署。
>
> 创建时间：2026-08-20  
> 来源：`docs/ts-integration-plan-v2.md` 重构  
> 当前状态基线：以 `docs/state/AI_CONTEXT.md` 为准。制定本文时 M40 P7 technical assurance 已验收通过，P6 strict no-go 保持；这不等于 Phase 4 已完成人工验收或生产认证。

---

## 0. 先说结论

### 0.1 本次最值得做什么

优先完成一个 **Next.js + TypeScript 演示界面**，真实调用现有 FastAPI `/api/query`，重点展示 DataPilot 已经具备的能力：

- SQL / RAG / Hybrid 三条主路径；
- Answer、SQL、Table、Chart；
- Citation / Document Evidence 的公开投影；
- Tool Call / Trace / runtime 状态；
- `route / execution / answer / safety` 四轴状态；
- clarification → resume；
- 成功 SQL/RAG 后的一次 bounded follow-up；
- blocked / insufficient evidence / external unavailable / partial 等失败与降级语义。

Web UI 的目标不是做一个“仿 ChatGPT 聊天站”，而是把 DataPilot 已有的可信 Agent 能力 **准确、直观、好看地展示出来**。

### 0.2 什么暂时不做

第一版明确不做：

- 不把 Python Agent 改写成 TypeScript；
- 不在前端复制 Router、Evidence Gate、Controller 或 Thread 状态机；
- 不做通用无限多轮聊天；
- 不引入 Vercel AI SDK `useChat` 作为必要依赖；
- 不为了视觉效果新增 SSE / WebSocket / token streaming；
- 不做 Redux / Zustand 等全局状态框架；
- 不做 Turborepo / npm workspace 等 monorepo 基础设施；
- 不新建完整 Eval Dashboard + SQLite + `/api/eval/*` 平台；
- 不把“部署到 Vercel 并真实调用本地 FastAPI”写成验收前置；
- 不为了 MCP 数量拆出 `search_docs`、`analyze` 等绕过顶层 Router 的重复 Tool；
- 不新增 RAG Subgraph、query rewrite、rerank 等与本 TS 集成无关的 Agent 能力。

### 0.3 优先级

```text
P0  Next.js Web UI（核心）
     ↓
P1  Web UI 与真实 /api/query 完整联调
     ↓
P2  面试展示打磨：预设场景、状态解释、截图/GIF
     ↓
P3  可选：轻量 TypeScript MCP Adapter
     ↓
P4  可选：只读 Eval Summary 页面

完整 Eval 平台、真 streaming、公网后端部署：
只有出现明确需求时再单独立项。
```

---

# 一、为什么现在做 TS，以及它不负责什么

## 1.1 当前项目已经不缺 Agent 主体能力

当前 DataPilot 的核心是 Python/FastAPI + LangGraph Harness：

```text
用户问题
  ↓
/api/query
  ↓
bounded turn seam
  ↓
Router / Harness
  ├─ SQL deep Tool
  ├─ RAG deep Tool
  ├─ Hybrid: SQL + RAG
  └─ clarify / reject / unsupported
  ↓
Evidence / Gate / Controller
  ↓
AgentResponse + Trace
```

TS 集成的价值是 **Presentation / Integration Layer**，不是再造一套 Agent。

面试时应能一句话说明：

> Python 负责 Agent engine 和可信执行合同；TypeScript 负责产品展示与协议适配。两边通过稳定 HTTP contract 解耦。

## 1.2 TS 层必须守住的职责边界

### TypeScript 可以做

- 收集用户问题和 demo role；
- 调 `/api/query`；
- 对公开 `AgentResponse` 做运行时校验；
- 根据服务端响应选择展示组件；
- 渲染 SQL、rows、chart、citations、tool calls、thread；
- 按服务端签发的 clarification/follow-up schema 生成表单；
- 展示安全阻断、证据不足、partial、provider unavailable 等状态；
- 提供演示预设问题；
- 可选地把 `/api/query` 包装成一个 MCP Tool。

### TypeScript 不可以做

- 自己判断 SQL / RAG / Hybrid；
- 自己决定“证据够不够”；
- 自己猜 clarification 缺失字段；
- 自己把 follow-up 改写为自由聊天；
- 自己决定是否能继续执行；
- 自己拼接 Hybrid 最终业务结论；
- 自己绕过 trusted caller / role / ACL；
- 把 `docs_used` 当成新的 Evidence authority；
- 把前端显示状态反向作为 Harness 的事实源。

一句话：

> **前端展示服务端事实，不创造 Agent 事实。**

---

# 二、总体架构

## 2.1 v3 推荐架构

```text
┌──────────────────────────────────────────────────────────┐
│                  Python / FastAPI                        │
│                                                          │
│  POST /api/query                                         │
│    ├─ SQL                                                │
│    ├─ RAG                                                │
│    ├─ Hybrid                                             │
│    ├─ Clarification / bounded follow-up                  │
│    ├─ Safety / Evidence Gate                             │
│    └─ Trace / AgentResponse                              │
└───────────────────────┬──────────────────────────────────┘
                        │ HTTP / JSON
              ┌─────────▼──────────┐
              │ Next.js / TS Web  │
              │                   │
              │ Presentation/BFF  │
              └─────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │ Browser Demo UI     │
             └─────────────────────┘

可选：
Claude / Cursor / MCP Client
              │
              ▼
      TypeScript MCP Adapter
              │
              └──── HTTP → POST /api/query
```

## 2.2 为什么不再做三个独立 TS 项目

v2 把 Demo、MCP、Eval Dashboard 同时列为主要交付，会带来三个问题：

1. **展示目标分散**：真正给面试官第一眼价值最高的是主 Demo；
2. **重复合同维护**：多个 TS 工程都要追 `AgentResponse` 演进；
3. **Eval Dashboard 容易反客为主**：DataPilot 当前已有 EvalOps-lite 和 assurance 体系，不需要为了“有页面”再在项目内部建立一套完整 Eval 平台。

v3 因此只把 Web UI 设为 required；MCP 和 Eval Summary 都是 optional。

---

# 三、FastAPI 合同是唯一事实源

## 3.1 不再使用 v2 的旧 `AgentResponse` 假设

当前 `/api/query` 已经不是早期“问题 → SQL → answer”的简单响应。TS 必须至少正确理解以下公开字段：

```text
route:
  sql | rag | hybrid | none

answer
sql
columns
rows
tables_used
docs_used
chart_spec

safety_status:
  passed | blocked

blocked_reason
cost
tool_calls
error_type
trace_id

execution_status:
  not_started | completed | external_unavailable | failed

answer_status:
  complete
  | partial
  | clarification_required
  | unsupported
  | insufficient_evidence
  | no_answer

citations
reason_code

turn_action:
  initial | resume | follow_up | rejected

graph_invocation_count
thread
hybrid_branches
```

请求端还要支持当前 bounded turn 合同：

```text
question
user_role
force_new_pipeline
schema_retrieval_profile
schema_fusion_strategy

thread_id
expected_version
clarification_answers

enable_bounded_follow_up
follow_up_action
follow_up_fields
```

> 具体字段、枚举和值域始终以 `app/schemas/agent.py` 和 FastAPI OpenAPI 为准，本文不建立第二份权威 schema。

## 3.2 TypeScript 类型策略

### 第一版：单工程本地类型 + Zod 校验

推荐：

```text
web/
  lib/
    agent-schema.ts
```

职责：

- 给 UI 提供 TypeScript 类型；
- 对 FastAPI 返回值做 Zod runtime validation；
- schema 只覆盖 **公开 HTTP contract**；
- 测试校验典型 SQL/RAG/Hybrid/blocked/clarification 响应。

不引入共享 npm package，也不为了两个消费者先建 workspace。

### 后续出现 MCP 时

MCP Adapter 可以选择：

- 少量复制公开 request/response type；或
- 从 Web 工程提取一个极小的 `contracts/` 包。

**只有真的出现两个以上长期维护的 TS consumer 后再提取**，不要为了“架构完整”提前上 monorepo。

### 可选优化

如果后续发现 TS contract drift 经常发生，再考虑根据 FastAPI OpenAPI 自动生成类型。

这个优化应由真实维护成本驱动，不作为第一版前置。

---

# 四、核心交付：Next.js Web UI

## 4.1 定位

替代 Streamlit 作为 **主要求职展示界面**，但 Streamlit 可以继续保留为 Python 本地调试/兜底入口，不要求立即删除。

目标不是：

> “做一个像 ChatGPT 的页面。”

而是：

> “让面试官一眼看懂 DataPilot 为什么是可信多证据 Agent，而不只是 Text2SQL。”

## 4.2 推荐技术栈

| 层 | 推荐 | 原因 |
|---|---|---|
| Framework | Next.js + App Router + TypeScript | 成熟、适合展示全栈能力 |
| UI | Tailwind CSS + shadcn/ui | 少写样式基础设施，快速获得专业 UI |
| HTTP | 原生 `fetch` | 当前是普通 JSON request/response，足够 |
| Runtime validation | Zod | 防止 TS 静态类型掩盖真实 API drift |
| Chart | 优先复用后端 `chart_spec` 的 Vega-Lite 渲染 | 不在前端重造图表语义 |
| State | React 本地状态 | 当前交互是 bounded turn，不需要全局状态库 |
| Tests | Vitest + Playwright | 合同/组件轻测 + 一条真实关键路径 |
| Package manager | npm | 保持工具链简单 |

### 明确不要求固定具体大版本

实施模块开工时再根据当时官方稳定版本锁定 `package.json`。

文档不再把 `Next.js 15`、`next.config.mjs` 等历史版本选择写成长期合同。

---

# 五、UI 应该长什么样

## 5.1 主界面

推荐单页工作台，而不是复杂多页面后台：

```text
┌───────────────────────────────────────────────────────┐
│ DataPilot                              Role: ops      │
│ Trusted multi-evidence data agent                     │
├───────────────────────────────────────────────────────┤
│ Demo scenarios                                        │
│ [SQL] [RAG] [Hybrid] [Clarify] [Safety]              │
│                                                       │
│ Ask DataPilot                                         │
│ ┌───────────────────────────────────────────────────┐ │
│ │ 2026 年 6 月退款率最高的商品是什么？             │ │
│ └───────────────────────────────────────────────────┘ │
│                                   [Run]              │
├───────────────────────────────────────────────────────┤
│ Status                                                │
│ route: sql  execution: completed  answer: complete   │
│ safety: passed  latency: ...  trace: ...             │
├───────────────────────────────────────────────────────┤
│ Answer                                                │
│ ...                                                   │
├───────────────────────┬───────────────────────────────┤
│ Evidence / SQL        │ Result                        │
│ SELECT ...            │ Table / Chart                 │
├───────────────────────┴───────────────────────────────┤
│ Citations / Hybrid branches                          │
├───────────────────────────────────────────────────────┤
│ ▸ Why this result / Agent Trace                      │
│   Router → Tool → Evidence → Controller              │
└───────────────────────────────────────────────────────┘
```

## 5.2 页面重点不是“消息气泡”

可以保留轻量聊天视觉，但主信息层级应该是：

1. **用户问了什么**
2. **Agent 最终回答**
3. **它走了哪条路径**
4. **依据是什么**
5. **安全/证据是否通过**
6. **如果不能回答，为什么停**
7. **如果需要用户补充，应该补什么**

这比无限 message history 更能体现当前项目设计。

---

# 六、必须展示的五类场景

Web Demo 的预设场景应直接对齐 Phase 4 项目展示目标。

## 6.1 SQL

展示：

- `route=sql`
- answer
- SQL
- rows / table
- chart（存在时）
- tables used
- tool call
- trace id
- execution / answer / safety

用户应能从答案回到 SQL Evidence 和运行 Trace。

## 6.2 RAG

展示：

- `route=rag`
- answer
- citations
- 允许公开展示的 document metadata
- tool call
- Evidence / citation 状态
- execution / answer / safety

UI 不应把 `docs_used` 的兼容投影包装成新的权威 Evidence 模型。

## 6.3 Hybrid

展示：

- `route=hybrid`
- 最终 answer
- SQL 部分的结果
- RAG citations
- `hybrid_branches`
- partial / branch failure 时的显式状态

Hybrid 的视觉重点应是：

```text
Data Evidence + Document Evidence
            ↓
        Final Answer
```

而不是“两个聊天机器人答案拼接”。

## 6.4 Clarification → Resume

当：

```text
answer_status = clarification_required
thread.status = pending
```

前端读取：

```text
thread.clarification.prompt
thread.clarification.fields
```

并按服务端给出的：

- `value_type`
- `allowed_values`
- `max_length`

动态画表单。

提交时必须带：

```text
thread_id
expected_version
clarification_answers
```

前端不能自己猜“用户应该补时间还是产品”。

## 6.5 Safety / Evidence Stop

至少展示一条：

- SQL safety blocked；
- 文档 ACL / evidence insufficient；
- unsupported；
- external provider unavailable；
- Hybrid required branch 失败导致 partial/stop；

页面必须把“没有答案”展示成 **可信行为**，而不是 UI error。

---

# 七、Bounded Follow-up 的前端设计

## 7.1 不做通用聊天历史

当前 thread 不是长期 conversation memory。

前端不应该让用户看到一个无限输入框，并暗示：

> “你可以一直基于上一轮自由追问。”

正确做法是：

当服务端返回：

```text
thread.status = follow_up_ready
thread.follow_up.actions = [...]
follow_up_budget_remaining = 1
```

UI 才展示服务端签发的 follow-up action。

例如：

```text
[调整 SQL 范围]
[解释同一证据]
[询问相关证据]
```

选择 action 后，再按服务端字段画 form。

## 7.2 Thread 信息怎么展示

普通用户区域只需要：

```text
Follow-up available
expires at ...
```

调试/面试折叠面板可以展示：

```text
thread_id
checkpoint_version
state_version
status
follow_up_budget_remaining
turn_action
graph_invocation_count
```

不要把 thread 当作“聊天记忆数据库”。

---

# 八、前端数据流

## 8.1 推荐第一版：普通 fetch

```text
Browser
  ↓
POST /api/query-proxy   （可选 Next.js BFF）
  ↓
FastAPI POST /api/query
  ↓
AgentResponse JSON
  ↓
Zod validate
  ↓
render by response status
```

也可以在纯本地环境直接浏览器请求 FastAPI，只要 CORS 配置明确。

为了以后部署更灵活，默认推荐保留一个很薄的 Next.js Route Handler：

```text
Browser
  ↓
Next.js Route Handler
  ↓
DATAPILOT_API_BASE_URL
  ↓
FastAPI
```

它只负责：

- 统一 API base URL；
- 转发 request；
- 处理网络级错误；
- 不解释 Agent 业务语义。

## 8.2 为什么不使用 `useChat`

当前服务端返回的是结构化 `AgentResponse`，而不是标准聊天 message stream。

为了 `useChat` 再把：

```text
AgentResponse
→ AI SDK message
→ 前端再拆回 AgentResponse UI
```

属于没有必要的格式往返。

因此 v3 默认使用：

```typescript
const response = await fetch(...)
const body = AgentResponseSchema.parse(await response.json())
```

即可。

## 8.3 为什么第一版不做 streaming

当前 `/api/query` 的合同价值主要在：

- route；
- evidence；
- citation；
- status；
- trace；
- final answer。

不是 token-by-token 输出。

如果为了动画效果新增 `/api/query/stream`，会扩大：

- 后端接口；
- 中断/失败语义；
- Trace 对齐；
- UI 状态；
- 测试范围。

只有将来真实用户体验证据说明等待体验成为问题，再单独评估 SSE/event streaming。

---

# 九、推荐目录结构

建议项目根目录新增一个主 TS 工程：

```text
web/
  package.json
  package-lock.json
  tsconfig.json
  next.config.ts

  app/
    layout.tsx
    page.tsx
    globals.css

    api/
      query/
        route.ts              # 极薄 BFF，只转发 /api/query

  components/
    query/
      query-box.tsx
      scenario-presets.tsx
      role-selector.tsx

    response/
      response-panel.tsx
      status-strip.tsx
      answer-card.tsx
      sql-card.tsx
      result-table.tsx
      chart-card.tsx
      citations-card.tsx
      hybrid-branches.tsx
      blocked-card.tsx

    thread/
      clarification-form.tsx
      follow-up-panel.tsx

    trace/
      trace-panel.tsx
      tool-call-list.tsx

    ui/
      ... shadcn components

  lib/
    agent-schema.ts
    api-client.ts
    response-view.ts
    demo-scenarios.ts

  tests/
    agent-schema.test.ts
    response-view.test.ts

  e2e/
    query-flow.spec.ts
```

### 为什么叫 `web/`

比 `demo-next/` 更自然。

这个 TS 工程如果以后继续承担简历主页、MCP 文档或只读 assurance summary，也不需要再改名。

---

# 十、组件设计原则

## 10.1 `response-panel.tsx`

只负责按服务端状态组织视图：

```text
blocked
clarification required
unsupported
insufficient evidence
complete
partial
external unavailable
failed
```

不要只写：

```typescript
if (answer) showAnswer()
```

因为当前项目的价值恰恰在正交状态。

## 10.2 `response-view.ts`

允许存在一个纯展示映射层：

```text
AgentResponse
   ↓
ResponseViewModel
```

它只做：

- label；
- 是否显示某卡片；
- UI 文案；
- 安全的空值处理。

它不能：

- 修改 route；
- 推断 Evidence；
- 把 failed 改成 partial；
- 替 Controller 决定业务语义。

## 10.3 `trace-panel.tsx`

第一版不需要把 JSONL trace 全部重新做成复杂可视化系统。

只展示公开响应里已经有的：

- tool_calls
- tables_used
- citations / docs public projection
- reason_code
- cost
- trace_id
- turn_action
- graph_invocation_count
- thread summary
- hybrid branch summary

如果以后确实需要“完整节点级 Trace 时间线”，应先确认后端已经有适合前端读取的公开 contract，而不是前端直接读内部日志猜节点。

---

# 十一、测试策略

TS 是展示/适配层，原则继续是：

> **测合同和关键行为，不追求覆盖率数字。**

## 11.1 Required

### A. Zod contract tests

至少准备这些 fixture：

- SQL complete；
- RAG complete + citations；
- Hybrid complete；
- Hybrid partial；
- clarification required；
- bounded follow-up ready；
- safety blocked；
- external unavailable；
- unsupported / insufficient evidence。

验证：

- 合法响应能 parse；
- 缺关键字段或非法 enum 会失败；
- UI 不因 `rows=[]`、`sql=null`、`citations=[]` 崩溃。

### B. View mapping tests

验证典型状态不会展示错误组件。

例如：

```text
clarification_required
→ 有 clarification form
→ 不假装 normal complete answer

blocked
→ 显示 blocked state
→ 不把空 SQL 当 UI bug

hybrid partial
→ 显示 branch 状态
→ 不显示“全部成功”
```

### C. Playwright 一条主路径

至少：

```text
打开页面
→ 选择一个预设问题
→ Run
→ mock/真实后端返回 AgentResponse
→ Answer + Status + Evidence 区域正确出现
```

如果成本不高，再增加一条 clarification → resume。

## 11.2 不要求

- 不做视觉像素级快照；
- 不追求高覆盖率；
- 不为每个 shadcn 组件写测试；
- 不在第一版做复杂端到端真实 LLM 测试。

真实 Agent correctness 继续由 Python contract / Eval / assurance 负责。

---

# 十二、交付顺序

> 不在本文预先指定下一个模块一定叫 M41。真正开工时遵守 `AGENTS.md`：读取最新 state，并为实际模块建立独立 plan / notes。

## Step 1：合同对齐

先做：

- 读取最新 `app/schemas/agent.py`；
- 读取现有 Streamlit 对 `/api/query` 的调用；
- 固定 Web UI 只需要的公开字段；
- 建 Zod schema + fixtures。

验收：

- TS 能正确解析当前典型响应；
- 没有修改 Python Agent 行为。

## Step 2：静态 UI 骨架

使用 fixtures 做：

- 页面布局；
- 状态条；
- Answer；
- SQL；
- Table；
- Chart；
- Citation；
- Trace；
- Hybrid branches；
- blocked/partial 等状态。

验收：

- 五类演示场景的页面结构都能展示；
- UI 不依赖真实 LLM 才能开发。

## Step 3：接真实 FastAPI

实现：

```text
Next.js BFF → /api/query
```

替换 fixtures。

验收：

- 与 Streamlit 同一问题能获得相同业务结果；
- Web 不重复实现 Agent 判断；
- 网络错误和 Agent blocked 能区分。

## Step 4：Clarification + bounded follow-up

复用服务端 thread spec。

验收：

- clarification 表单完全由 server spec 生成；
- resume 正确带 version；
- follow-up 只有服务端明确签发时出现；
- UI 不形成无限多轮假象。

## Step 5：面试演示打磨

固定一组可复现 preset：

```text
SQL
RAG
Hybrid
Clarification
Safety / Evidence stop
```

补：

- 清晰状态解释；
- Loading / network error；
- 空结果；
- README 截图/GIF；
- 简短架构图。

这一阶段优先做“看得懂”，而不是继续堆依赖。

---

# 十三、公网部署策略

## 13.1 v3 不把公网部署作为 required

原因很简单：

```text
Vercel 上的 Next.js
fetch("http://localhost:8000")
```

访问的是部署容器自己的 localhost，不是用户电脑上的 FastAPI。

如果要让公开网页真实运行 DataPilot，必须同时解决：

- FastAPI 公网部署；
- 数据库；
- secrets；
- LLM provider；
- trusted caller / demo identity；
- CORS / HTTPS；
- 成本与滥用；
- 运行环境；
- 数据安全。

这已经是一个独立部署模块，不应伪装成“前端半天上线”。

## 13.2 第一目标

求职展示第一版接受：

```text
本地真实 Web Demo
+ README 高清截图
+ 30~60 秒 GIF / 视频
+ 架构图
```

这足以证明代码真实存在、交互真实存在。

## 13.3 什么时候再做公网真实 Demo

只有当出现明确收益，例如：

- 简历投递确实需要 live URL；
- 后端已有安全可控的 demo deployment；
- 可接受 provider/API 成本；
- identity / abuse boundary 有明确方案；

再单独立项。

---

# 十四、可选加分项：TypeScript MCP Adapter

## 14.1 定位

MCP 不是第二套 Agent，而是协议转换层：

```text
Claude / Cursor
      ↓ MCP
data-pilot-mcp
      ↓ HTTP
POST /api/query
      ↓
DataPilot Router 决定 SQL / RAG / Hybrid
```

## 14.2 第一版只暴露一个 Tool

```typescript
data_pilot_query({
  question: string,
  user_role?: string,
  enable_bounded_follow_up?: boolean
})
```

MCP Server 不额外提供：

```text
data_pilot_search_docs
data_pilot_analyze
```

除非以后出现真实外部调用方需要强制指定能力，而当前 `/api/query` 自己已经承担顶层路由。

否则拆三个 Tool 会：

- 重复 Router 能力；
- 扩大合同；
- 增加参数与错误处理；
- 弱化“统一 Agent 入口”的设计。

## 14.3 MCP 返回内容

优先返回简洁 structured result：

```text
answer
route
execution_status
answer_status
safety_status
sql
rows（必要时限制）
citations
reason_code
trace_id
```

不要默认把内部 Trace、大量 rows、私有 Evidence 全量塞给 MCP Client。

## 14.4 为什么可以用 TypeScript

正确的理由不是：

> “Python MCP 不成熟，所以必须 TS。”

而是：

> 当前 MCP 只是一个独立协议 adapter，不需要直接调用 Python engine 内部对象。项目本来就新增了 TS presentation/integration layer，因此用 Node/TS 做一个轻量 HTTP→MCP 适配器很自然，也能保持 Agent engine 与外部协议解耦。

如果未来 MCP 需要深入 Python engine 内部、减少 HTTP 跳转或共享对象生命周期，再重新比较 Python 方案。

## 14.5 MCP 是否 required

不是。

优先顺序始终是：

```text
Web UI 完整、真实、可演示
        >
MCP “为了简历多一个关键词”
```

只有 Web UI 收好后再做。

---

# 十五、可选加分项：只读 Eval / Assurance Summary

## 15.1 不再建设完整 Eval Dashboard

v2 设想：

```text
/api/eval/summary
/api/eval/cases
/api/eval/cases/{id}
SQLite
Recharts dashboard
```

v3 默认全部取消。

理由：

- 当前 DataPilot 已有 `eval/`、reports、traces、assurance；
- Phase 4 明确不应在 DataPilot 内扩成独立完整 Eval 平台；
- 为了页面再增加一套数据服务和 SQLite authority，收益不足；
- 容易让展示层反过来拖动核心评测合同。

## 15.2 如果确实想展示 Eval

最多做一个只读 `/assurance` 页面。

数据源优先是 **预先生成的静态 summary JSON**，例如：

```json
{
  "generated_at": "...",
  "contract_run": "...",
  "deterministic_tests": {
    "passed": 447,
    "skipped": 3
  },
  "families": [
    "sql",
    "rag",
    "hybrid",
    "thread",
    "safety"
  ]
}
```

UI 只展示：

- 最新 assurance identity；
- 几个 contract family；
- deterministic test snapshot；
- P6 go/no-go 结论入口；
- 指向已有 Markdown report 的链接。

### 重要

数字必须来自真实、当前、明确分母的 artifact。

不能把历史不同运行结果拼成“实时 dashboard”。

---

# 十六、开发约定

## 16.1 继续遵守项目工作流

真正开始 TS 开发前：

1. 读 `AGENTS.md`；
2. 读最新 `docs/state/AI_CONTEXT.md`；
3. 按其中必读规则补相关 state；
4. 读取当前阶段 roadmap；
5. 建实际模块的 `<module>-plan.md` / `<module>-notes.md`；
6. 再开始代码修改。

本文是专项方案，不取代 module plan。

## 16.2 Python 默认行为不因 TS 自动改变

以下任何改变都不能因为“前端方便”直接做：

- 默认模型；
- retrieval；
- RAG corpus；
- safety；
- trusted caller；
- thread TTL；
- Graph 路径；
- Eval case；
- 出站策略；
- API 的核心业务语义。

如果前端发现合同不够用，应先判断：

> 这是缺少“公开投影”，还是缺少“核心能力”？

仅前者才适合做小的 API 增量。

## 16.3 TS 注释

继续遵守项目注释风格：

- 新手友好；
- 中文为主；
- 解释“为什么”；
- 关键处说明职责边界；
- 避免给普通 JSX 每一行写无意义注释。

## 16.4 npm

默认使用 npm，锁定依赖。

不要在没有收益证据时切 pnpm/yarn，也不要为了工程感额外引入 workspace。

---

# 十七、风险与缓解

| 风险 | 影响 | v3 缓解 |
|---|---|---|
| 前端把 bounded thread 做成无限聊天 | 错误展示系统能力 | 只渲染服务端签发的 clarification/follow-up |
| TS schema 与 Pydantic 漂移 | 联调失败或状态误读 | Python/OpenAPI 为 authority，Zod contract test |
| UI 只看 `answer` 不看四轴状态 | blocked/partial 被误展示为成功 | 建统一 `response-view` 映射 |
| 为 streaming 修改后端 | 扩大主线与测试范围 | 第一版普通 fetch |
| 为公网 Demo 顺带部署整套后端 | 时间/安全/成本失控 | 公网部署改为独立可选模块 |
| MCP 拆太多 Tool | 绕开 Router，合同重复 | 第一版统一 `data_pilot_query` |
| Eval 页面另建 authority | 评测数字不可信 | 默认不做；若做只读静态 summary |
| 图表渲染兼容问题 | 页面 crash | chart_spec 有则渲染，失败降级为 table |
| 大 rows 卡 UI | 演示体验差 | UI 限制首屏行数，保留结果统计 |
| 前端暴露内部 Evidence/敏感数据 | 安全边界变差 | 只消费现有公开 API 投影 |
| 用户 role 被误当真实认证 | 面试表述失真 | UI 明确是 demo/test active role selector |
| 为“全栈”加入大量库 | 工程噪音超过项目主线 | 每个依赖必须对应明确 UI/合同价值 |

---

# 十八、Definition of Done

## 18.1 Required：Web UI

满足以下条件才算 v3 核心目标完成：

- [ ] Next.js + TypeScript 工程可独立启动；
- [ ] 真实调用 FastAPI `/api/query`；
- [ ] Zod 对公开响应做 runtime validation；
- [ ] SQL 场景正确展示 Answer / SQL / Table / Chart / Trace；
- [ ] RAG 场景正确展示 Citations；
- [ ] Hybrid 场景正确展示双分支公开状态；
- [ ] clarification 能按 server spec 填写并 resume；
- [ ] bounded follow-up 只在服务端允许时出现，并最多消费服务端签发预算；
- [ ] blocked / partial / unsupported / insufficient evidence / external unavailable 不会被误展示为普通成功；
- [ ] role selector 明确是 demo/test active role，不宣称生产认证；
- [ ] 至少一组 Zod contract tests；
- [ ] 至少一条 Playwright 主路径；
- [ ] 页面有 5 个代表性预设场景；
- [ ] README/项目展示有架构图和 Web Demo 截图或 GIF；
- [ ] 不为了 Web UI 改写 Agent 核心路径。

## 18.2 Optional：MCP

- [ ] 一个 `data_pilot_query` Tool；
- [ ] 参数 runtime validation；
- [ ] HTTP 错误与 Agent blocked 能区分；
- [ ] MCP Inspector 能调用；
- [ ] 一条自动化测试；
- [ ] 简短配置说明。

## 18.3 Optional：Assurance Summary

- [ ] 只读；
- [ ] 数据来自明确 artifact；
- [ ] 不混淆不同 run；
- [ ] 不引入新的 Eval authority；
- [ ] 不提供 Web 触发长时间 Eval。

---

# 十九、明确的 Non-goals

这部分用于防止后续实施时范围再次膨胀。

本方案 **不以以下事项作为成功条件**：

```text
× TS 重写 Agent
× 无限聊天
× 长期记忆
× Streaming
× WebSocket
× Vercel AI SDK
× Redux / Zustand
× monorepo
× 三个 MCP Tool
× MCP 深度接管 Agent
× 完整 Eval Dashboard
× 新 Eval SQLite
× 在线启动真实 LLM Eval
× 公网生产部署
× OAuth / SSO
× 新 RAG Subgraph
× query rewrite
× rerank
× GraphRAG
× 多 Agent
```

如果以后确实需要其中某项，必须回到最新 state + 失败证据重新立项，而不是因为本文曾经提过 TS 就顺带加入。

---

# 二十、简历与面试怎么讲

## 20.1 推荐简历表述

> **全栈 Agent 产品化**：在 Python/FastAPI + LangGraph 数据分析 Agent 外构建 Next.js/TypeScript 演示层，通过统一 `/api/query` contract 展示 SQL、RAG、Hybrid、Citation、Safety、Trace 及有界 clarification/follow-up；前端只消费服务端 Evidence/状态投影，不复制 Agent 编排与安全决策，保持 engine 与 presentation layer 解耦。

如果后续真的完成 MCP，再补：

> 使用 TypeScript MCP SDK 将统一 Agent API 包装为轻量 MCP Tool，使外部 AI Client 可通过标准协议调用 DataPilot，同时保留服务端 Router、Evidence Gate 与安全边界。

不要在没实现前提前写入简历。

## 20.2 面试追问：为什么不用 Streamlit 就够了？

回答重点：

> Streamlit 很适合早期验证和内部调试，但项目进入求职展示阶段后，我希望把 SQL/RAG/Hybrid、Citation、Trace、clarification 和失败状态做成更明确的产品 UI。核心 Agent 没有迁移，Next.js 只是消费稳定 HTTP contract，因此不会让展示层污染 Python 引擎。

## 20.3 为什么不做 streaming？

> 当前 DataPilot 的核心合同是一次查询产生可审计的 route、Evidence、status、citation 和 Trace，而不是 token stream。为了视觉效果新增 SSE 会扩大后端终止、错误和 Trace 对齐语义，所以第一版选择普通 request/response；出现真实 UX 瓶颈再加。

## 20.4 为什么不是自由多轮聊天？

> 当前系统刻意实现 bounded clarification 和一次 closed-world follow-up，避免旧 Evidence、权限变化和上下文漂移造成不可信回答。前端忠实展示这个合同，而不是为了像 ChatGPT 就伪装成无限对话。

## 20.5 为什么 MCP 只做一个 Tool？

> DataPilot 顶层 Router 本来就负责 SQL/RAG/Hybrid 决策。如果 MCP 再拆三个 Tool，相当于让外部 Client 绕过 Router 并重复路由合同。统一 `data_pilot_query` 更符合现有架构。

## 20.6 为什么不做 Eval Dashboard？

> 项目已经有 EvalOps-lite、reports、traces 和 assurance。完整 Dashboard 需要额外数据 API、存储和版本语义，容易把项目扩成评测平台。对求职展示来说，主 Demo 和可回查的真实 assurance artifact 收益更高，因此只保留可选只读 summary。

---

# 二十一、从 v2 到 v3 的主要变化

| v2 | v3 |
|---|---|
| 三个 TS 目标并列 | 一个 required Web UI + 两个 optional 加分项 |
| 以 M11/M12、Phase 3/4 未来计划为时间轴 | 以 M40 后当前状态为基线 |
| Demo 偏通用聊天产品 | Demo 偏可信 Agent 工作台 |
| 多轮 conversation history | bounded clarification + 一次服务端签发 follow-up |
| `useChat` / AI SDK | 普通 fetch + Zod |
| streaming 作为自然增量 | 默认不做，需真实 UX 证据再立项 |
| 固定 Next.js 15 / `.mjs` | 实施时选当前稳定版本 |
| 旧 `AgentResponse` | 对齐当前四轴状态、thread、citations、hybrid branches |
| Vercel 公网访问作为验收项 | 本地真实 Demo required；公网部署 optional |
| MCP 3 Tools | MCP 1 个统一 `data_pilot_query` Tool |
| TS 优势建立在“Python MCP 落后”上 | 以 protocol adapter / integration layer 的架构边界解释 |
| 完整 Eval Dashboard + SQLite + API | 默认取消；最多只读 assurance summary |
| 三个项目各自维护类型 | 先单 Web 工程本地合同，真正多 consumer 后再提取 |
| UI 是“加一个前端” | UI 明确服务 SQL/RAG/Hybrid/Evidence/Safety/Trace 展示 |
| 目标是补更多技术关键词 | 目标是提高项目可理解性与面试展示质量 |

## 修订记录

- **v3（2026-08-20）**：基于当前 M40 / Phase 4 状态重构 v2。将原“Next.js Demo + MCP Server + Eval Dashboard”三线并行方案收缩为“**Next.js Web UI 为核心交付，轻量 MCP Adapter 与只读 Assurance Summary 为可选项**”。
- 删除或降级已不适合当前项目的设计：通用多轮聊天、`useChat` / Vercel AI SDK、默认 Streaming/SSE、完整 Eval Dashboard + SQLite + `/api/eval/*`、强制公网部署、MCP 多 Tool 拆分等。
- 前端合同全面对齐当前 `/api/query`：补充 SQL/RAG/Hybrid、四轴状态、Citation、Hybrid branches、clarification、bounded follow-up、thread/version 等现有能力。
- 明确架构边界：**Python/FastAPI 是 Agent 与合同事实源，TypeScript 只承担 Presentation/BFF/MCP Adapter，不复制 Router、Evidence Gate、Controller 或线程状态机。**
- 调整实施顺序与验收标准，优先保证本地真实 Demo、五类代表性场景、合同校验和面试展示质量，再根据实际需求决定 MCP、公网部署或 Eval 展示。

---

# 二十二、最终建议

v3 的实施原则可以压成一句话：

> **先把 DataPilot 已经有的能力展示好，再考虑增加新的集成能力。**

当前项目最值得展示的不是“用了多少框架”，而是：

```text
Natural Language
      ↓
Router
      ↓
SQL / RAG / Hybrid
      ↓
Typed Evidence
      ↓
Citation / Safety / Gate
      ↓
Bounded interaction
      ↓
Trace / Eval / Assurance
```

因此 TypeScript 的正确角色是：

> **给这条可信 Agent 链路一张足够专业、足够容易讲清楚的脸。**

只要核心 Web UI 做扎实，即使 MCP、Eval Summary、公网部署都暂时不做，这个 TS 集成也已经达到对简历和面试最有价值的目标。
