# DataPilot TypeScript 集成方案 v2

> 三个独立 TypeScript 外壳项目，通过 HTTP 调 FastAPI。Demo 和 MCP Server 复用现有 `/api/query` 接口，不新增 Python 业务代码。Dashboard 所需的 eval 查询接口属于阶段四 AgentEvalOps 后端计划内，不视为 TS 项目引入的额外负担。AI 全量生成代码，用户只验收 UI 效果。
>
> 创建时间：2026-07-24 | 修订：2026-07-24（v2，根据审查意见修订）

## 前置条件

- Node.js 已安装（用户环境已有，v24.14.0）
- FastAPI 后端正常运行在 `http://localhost:8000`
- 三个 TS 项目均为独立进程，与 Python 后端零耦合
- **开始 TS 开发前，必须先通过 M11 accept-module 验收 + 完成 M12 阶段收尾**（项目 CLAUDE.md 工作约定：上一模块未验收不得进入下一模块）

## 总体架构

```
                    ┌─────────────────────────────────┐
                    │   FastAPI :8000（业务接口不改）     │
                    │                                  │
                    │   /api/query      NL2SQL 查询     │
                    │   /api/rag/*      RAG 检索（阶段三）│
                    │   /api/eval/*     评测接口（阶段四） │
                    └──────┬──────────────────────────┘
                           │ HTTP (localhost)
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     ┌──────────┐  ┌───────────┐  ┌──────────────┐
     │ 1. Demo  │  │2. MCP     │  │3. Eval       │
     │ Next.js  │  │ Server    │  │ Dashboard    │
     │ :3000    │  │ (stdio)   │  │ :3000/eval   │
     └──────────┘  └───────────┘  └──────────────┘
```

---

## 第零项：类型管理与测试策略

### 0.1 类型共享方案

三个 TS 项目中，只有 Demo 和 MCP Server 共享 `AgentResponse` / `QueryRequest` 两个类型（约 40 行 Zod schema）。Dashboard 使用完全独立的 eval 类型。

**当前阶段方案：Demo 项目作为类型源，MCP Server 直接复制类型定义。** 理由：

- 共享面积极小（两个 schema），引入 npm workspaces / turborepo 的复杂度不划算
- 项目维护期约 2 个月，AgentResponse 字段自 M5 起已稳定，类型 drift 风险很低
- Python 端有 Pydantic Schema，TS 端有 Zod Schema——"两端独立维护、契约对齐"本身就是面试 talking point

**面试话术**："当前阶段通过项目结构管理类型复用。如果扩展到更多 TS 项目，迁移路径是将 `lib/types.ts` 提取为独立 npm workspace 包，三个项目通过 `workspace:*` 引用。"

### 0.2 测试策略

Python 端每个模块有测试是因为承载核心业务逻辑。TS 端三个项目都是"外壳"——**测逻辑不测渲染**。

| 项目 | 测试工具 | 最低覆盖 |
|------|---------|---------|
| 类型定义 | Vitest | Zod schema 解析/拒绝快照 |
| Demo 页 | Playwright | 1 条关键路径：输入问题 → 渲染回复卡片 |
| MCP Server | Vitest | Tool 参数校验 + Mock HTTP 响应 |
| Dashboard | — | 无自动化测试（静态数据渲染，目测验收） |

**原则**：每个 TS 项目至少跑通一条自动化验证，不是为了覆盖率数字，而是确保 CI 里 `npm test` 不会空跑。

---

## 一、Next.js Demo 页替代 Streamlit

### 1.1 定位

替换 `demo/streamlit_app.py`，从"Python 数据工具界面"升级为"专业 AI 聊天产品"。

### 1.2 功能清单

| 功能 | 现状 (Streamlit) | 升级后 (Next.js) |
|------|-----------------|-----------------|
| 问题输入 | 文本框 + 预设按钮 | 聊天框，支持多轮对话历史 |
| 角色选择 | 下拉框 | 顶部切换，默认 ops |
| 结果展示 | 逐段 JSON 渲染 | 结构化卡片：Answer / SQL / Table / Chart / Trace |
| 输出方式 | 等 3 秒一次全出 | 流式逐字输出（AI SDK streaming） |
| Tool Call | 不展示 | 折叠面板，点击展开每一步 tool 调用 |
| Trace | 只显示 trace_id | 底部时间线，展示 schema_retrieval → query_plan → sql_generation → sql_execution |
| 部署 | `streamlit run` | Vercel 一键部署，公网可访问 |

### 1.3 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | Next.js 15 + App Router | `npx create-next-app` 一键脚手架，配置文件使用 `next.config.mjs`（避免 `next.config.ts` 实验性特性） |
| AI SDK | `@ai-sdk/react` `useChat` | 30 行搞定多轮对话 + 状态管理；第一版使用非 streaming 模式（`fetch` + 一次性渲染），真 streaming 需要 FastAPI 新增 SSE 端点，放到阶段三完成后做增量 |
| 样式 | Tailwind CSS + shadcn/ui | 组件复制粘贴，不写 CSS |
| 图表 | Vega-Lite (CDN 直接加载，不打入 npm bundle) | 与后端 chart_spec 零转换；CDN 方式避免 Next.js bundle 膨胀 |
| 部署 | Vercel (免费套餐) | 面试给链接直接打开；备选 Cloudflare Pages（国内可访问）；兜底：本地截图 + GIF |

### 1.4 目录结构

```
demo-next/
  package.json
  next.config.mjs            # 使用 .mjs 避免 TS 配置文件实验性风险
  tsconfig.json
  tailwind.config.ts
  app/
    layout.tsx              # 根布局（标题、角色切换）
    page.tsx                # 聊天主界面（~150 行）
    globals.css             # Tailwind 导入 + shadcn 主题变量
    api/
      chat/
        route.ts            # Next.js → FastAPI 代理转发（~40 行）
  components/
    chat/
      message-list.tsx       # 消息列表容器
      user-message.tsx       # 用户消息气泡
      agent-message.tsx      # Agent 回复卡片（路由到各子组件）
    cards/
      answer-card.tsx        # 自然语言答案（支持 markdown）
      sql-card.tsx           # SQL 代码块 + 复制按钮
      table-card.tsx         # 数据表格
      chart-card.tsx         # Vega-Lite 图表渲染
      docs-card.tsx          # RAG 引用文档列表（阶段三补）
    trace/
      trace-panel.tsx        # 折叠 trace 时间线
      trace-step-item.tsx    # 单步 trace 详情
  lib/
    types.ts                 # AgentResponse Zod schema
    api-client.ts            # FastAPI HTTP 调用封装
    utils.ts                 # 工具函数
```

### 1.5 核心数据流

```
用户输入问题
  → useChat 发 POST 到 /api/chat（第一版非 streaming 模式）
    → Next.js API Route 转成 FastAPI 请求格式
      → fetch("http://localhost:8000/api/query", { question, user_role })
        → FastAPI 执行 Agent pipeline
      ← AgentResponse JSON（一次性返回）
    → API Route 返回 AI SDK DataMessage 格式
  ← useChat 收到 → 渲染 message 列表
```

> **streaming 前提条件**：真 streaming 需要 FastAPI `/api/query` 支持 SSE（Server-Sent Events），当前后端是一次性返回完整 `AgentResponse`。第一版使用非 streaming 模式，此时 `useChat` 等价于封装好的 `fetch` + 状态管理，功能完整。Streaming 放到阶段三完成后作为增量，届时若需要，在 FastAPI 新增一个 `/api/query/stream` SSE 端点。

### 1.6 两阶段交付

**第一波（即刻，2-3 天）——静态 Mock 版**：

- 不连 FastAPI，用假 `AgentResponse` 数据渲染完整 UI
- 确认消息列表、SQL 卡片、表格、图表、Trace 面板都正常显示
- 这个阶段不依赖后端，可以独立验收 UI 效果

**第二波（连后端，半天）**：

- 实现 `/api/chat` 代理转发
- 接真实 `/api/query`，替换假数据
- 开 streaming（可选，第一版可以先不开）

**后续增量（各半天）**：

- 阶段三完成 RAG：补 `docs-card.tsx` 展示引用文档
- 阶段三完成 Hybrid：补混合推理的多步骤展示
- MCP Server 完成后：在 demo 页加"在 Claude Desktop 中打开"按钮

### 1.7 验收标准

- 输入预设问题 → 返回和 Streamlit 版一致的结果
- SQL 代码块语法高亮 + 一键复制
- 表格正常渲染（支持大数据量滚动）
- Vega-Lite 图表正常显示
- Trace 面板折叠/展开正常
- 角色切换后查询结果相应变化
- 部署到 Vercel 后公网可访问

---

## 二、MCP Server TypeScript 版

### 2.1 定位

把 DataPilot 的查询能力包装为标准 MCP tools，让 Claude Desktop、Cursor、VS Code Copilot 等 AI 工具能直接调用。

### 2.2 暴露的 Tools

```typescript
// Tool 1：NL2SQL 查询（现在就能用）
data_pilot_query({
  question: string,          // 自然语言问题
  user_role?: "admin" | "ops" | "customer_service" | "demo_user",
  force_new_pipeline?: boolean,
})

// Tool 2：RAG 知识库检索（阶段三完成后可用）
data_pilot_search_docs({
  question: string,          // 要在知识库中搜索的问题
  top_k?: number,            // 返回文档数，默认 5
})

// Tool 3：混合分析（阶段三完成后可用）
data_pilot_analyze({
  question: string,          // 需要 SQL+RAG 混合分析的问题
  user_role?: string,
})
```

### 2.3 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| MCP SDK | `@modelcontextprotocol/sdk` | 官方 SDK，`McpServer` + `server.tool()` |
| HTTP 客户端 | Node.js 内置 `fetch` | 零依赖 |
| 类型校验 | Zod | Tool 参数 Schema，类型定义复制自 Demo 项目（见 0.1） |
| 调试 | `@modelcontextprotocol/inspector` | Web UI 可视化调试，绕过 Windows stdio 问题 |

### 2.3.1 为什么用 TypeScript 而不是 Python FastMCP

Python 的 **FastMCP**（`fastmcp`）已被 Anthropic 官方推荐，也很成熟。选择多开一个 Node.js 进程的真实理由：

| 理由 | 说明 |
|------|------|
| **协议演进** | MCP 协议本身是 TypeScript-first 设计的，官方 SDK 的 spec 覆盖度和更新速度仍然领先。FastMCP 在追赶但滞后于协议新特性 |
| **进程隔离** | MCP Server 作为独立 Node.js 进程运行，不污染 Python 后端进程空间；Python 进程加载了 torch/pymilvus/sqlalchemy 等重量级依赖，不应因为 MCP 调用而常驻 |
| **启动速度** | Node.js 冷启动远快于加载了 ML 依赖的 Python 进程 |
| **全栈能力展示** | 简历上 Python + TypeScript 双栈比纯 Python 更有竞争力，且 MCP 作为"协议层"独立于"引擎层"，证明了架构分层能力 |

> 如果未来 Python 引擎需要深度集成 MCP（而不是通过 HTTP 转一层），FastMCP 是更好的选择——可以直接调用引擎内部函数，省去 HTTP 序列化开销。当前阶段 DataPilot 的 MCP 需求只是"把 HTTP API 翻译成 MCP 协议"，Node.js 进程的薄代理模式更合适。

### 2.4 目录结构

```
data-pilot-mcp/
  package.json
  tsconfig.json
  src/
    index.ts                  # MCP Server 入口，注册 3 个 tool（~100 行）
    datapilot-client.ts       # FastAPI HTTP 调用封装（~60 行）
    types.ts                  # Zod schema + 响应类型（~50 行）
  README.md                   # 单独 README（第二面试项目加分项）
```

### 2.5 核心数据流

```
Claude Desktop / Cursor
  │
  ├─ 用户问："上个月退款率最高的商品是什么？"
  ├─ AI 决定调用 data_pilot_query tool
  │
  └─ MCP Protocol (stdio)
       └─ data-pilot-mcp (Node.js 进程)
            └─ POST http://localhost:8000/api/query
                 └─ { question, user_role }
            ← AgentResponse JSON
       ← MCP Tool Result (结构化 answer + sql + rows)
  │
  └─ AI 基于结果生成回复
```

### 2.6 接入方式

配置到 Claude Desktop 的 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "data-pilot": {
      "command": "node",
      "args": ["D:/path/to/data-pilot-mcp/dist/index.js"]
    }
  }
}
```

### 2.7 两阶段交付

**第一波（阶段三期间，1 天）——Query Tool 骨架**：

- 只实现 `data_pilot_query`（现在就能用）
- 其余两个 tool 写占位，返回"RAG/混合分析能力将在阶段三完成后上线"
- 用 MCP Inspector 验证 `data_pilot_query` 能正常调用

**第二波（阶段三完成后，半天）**：

- 补全 `data_pilot_search_docs` 和 `data_pilot_analyze`
- 更新 README
- 录一段"用 Claude Desktop 调 MCP Server 查数据"的演示 GIF

### 2.8 验收标准

- `data_pilot_query` 在 MCP Inspector 中能正常调用并返回正确结果
- 参数校验生效（传非法 user_role 返回错误提示）
- SQL 安全拦截被正确透传（危险 SQL 返回 blocked 状态）
- 配置到 Claude Desktop 后能正常使用
- README 含架构图 + 配置说明 + 演示 GIF

---

## 三、AgentEvalOps 评测仪表盘

### 3.1 定位

替换阶段四原计划的简版 HTML 报告，做成可交互的单页面 Web 仪表盘。和 Demo 共享同一个 Next.js 项目，通过 Route Groups 隔离：`app/(demo)/` 和 `app/(eval)/`。

**v2 范围降级**：原计划 4 个页面（仪表盘 + 用例列表 + 用例详情 + 版本对比）过重。降级为 **1 个页面 + 2 个 Tab**：

| 保留 | 砍掉 | 理由 |
|------|------|------|
| 首页仪表盘（统计卡片 + 图表） | — | 核心展示，面试第一眼 |
| 用例列表（表格 + 筛选，合并到首页 Tab 2） | — | 展示 CRUD 能力，代码量小 |
| — | 用例详情页 | 单 case 详情用 `run_eval.py` CLI 输出替代 |
| — | 版本对比页 | 版本对比用现有 Markdown 报告替代 |

### 3.2 功能清单

**首页仪表盘（Tab 1：概览）**：

- 总通过率环形图
- 各类型通过率柱状图（SQL / 聚合 / 多表 / RAG / 混合 / 安全）
- 安全拦截率（100% 时绿色强调）
- 平均延迟 / 平均 Token 消耗
- 失败原因 Top 5 饼图
- 最近一次运行时间和 commit hash

**用例列表（Tab 2：用例）**：

- 按类型/状态筛选
- 每条用例：ID、问题摘要、通过/失败/跳过标签
- 失败用例标红，点击展开显示 SQL、实际结果和 issue tags（不跳转独立页）

### 3.3 技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | Next.js（复用 demo-next，Route Groups 隔离） | `app/(demo)/` vs `app/(eval)/` |
| 图表 | Recharts + `dynamic(() => import(...), { ssr: false })` | 动态导入隔离，不影响 Demo 页首屏加载 |
| 组件 | shadcn/ui（Card, Table, Badge, Tabs, Progress, Select） | 和 Demo 共享组件库 |
| 数据源 | FastAPI `/api/eval/*` + SQLite | 阶段四 AgentEvalOps 后端计划内新增 3 个查询接口 |
| 部署 | 和 Demo 同 Vercel 项目，`/eval` 路径 | 同一域名 |

### 3.4 目录结构（在 demo-next 内扩展，Route Groups 隔离）

```
demo-next/
  app/
    (demo)/                   # Route Group：Demo 页
      page.tsx                # 聊天主界面
      layout.tsx              # Demo 布局
    (eval)/                   # Route Group：Dashboard（零耦合）
      page.tsx                # 仪表盘首页（~150 行，含 2 个 Tab）
      layout.tsx              # Eval 布局
    api/
      chat/
        route.ts              # Demo API Route
      eval/                   # Eval API Proxy（可选，也可前端直调 FastAPI）
        summary/route.ts
        cases/route.ts
  components/
    eval/
      stat-card.tsx           # 统计卡片（~30 行）
      pass-rate-donut.tsx     # 通过率环形图（~50 行）
      category-bar-chart.tsx  # 各类型柱状图（~50 行）
      failure-pie-chart.tsx   # 失败原因饼图（~50 行）
      case-table.tsx          # 用例列表表格（~60 行）
      run-eval-trigger.tsx    # 一键跑评测按钮 + 进度（~50 行）
  lib/
    eval-types.ts             # 评测 Zod schema（独立于 Demo 类型）
```

### 3.5 FastAPI 新增接口（阶段四 AgentEvalOps 计划内）

Dashboard 需要 FastAPI 新增 3 个查询接口（约 80 行 Python），这些接口属于阶段四 AgentEvalOps 的后端开发计划，不是 TS 项目引入的额外负担：

```python
# GET  /api/eval/summary          → 返回仪表盘聚合数据
# GET  /api/eval/cases            → 返回用例列表（支持筛选/分页）
# GET  /api/eval/cases/{case_id}  → 返回单 case 结果 + trace（供详情展开使用）
```

> `POST /api/eval/runs`（触发评测运行）砍掉——评测触发仍通过 CLI `run_eval.py`，避免 Web 端管理长时间运行任务的复杂度。

### 3.6 核心数据流

```
浏览器 /eval 页面（Tab 1：概览）
  → fetch("/api/eval/summary")
    → FastAPI 读 SQLite → 聚合查询
    ← { total, passed, failed, by_category: {...}, avg_latency, top_failures }
  → Recharts 渲染图表

浏览器 /eval 页面（Tab 2：用例列表）
  → fetch("/api/eval/cases?category=sql&status=failed")
    → FastAPI 读 SQLite
    ← { cases: [...], total: 32 }
  → shadcn/ui Table 渲染
  → 点击某行失败用例 → 内联展开显示 SQL 和 issue tags
```

### 3.7 两阶段交付

**第一波（阶段四开始，1 天）——骨架 + 假数据**：

- 和 FastAPI eval 接口契约先定好
- 前端用假数据渲染仪表盘首页（2 个 Tab）
- 不依赖真实评测数据

**第二波（阶段四评测引擎跑通后，半天）——接真实数据**：

- 连 FastAPI 真实接口，替换假数据
- 确保仪表盘数据与 `run_eval.py` 命令行输出一致

### 3.8 验收标准

- 仪表盘首页 Tab 1：4 个统计卡片 + 3 张图表正常渲染
- Tab 2：用例列表可筛选，失败用例点击展开显示详情
- 仪表盘数据与 `run_eval.py` 命令行输出一致

---

## 四、执行计划总览

```
现在（7/24）
│
├─ ★ accept-module M11 验收（先跑，0.5 天）          ← 前置门禁
├─ M12 阶段收尾（1-2 天）
│
├─ Demo 页静态 Mock 版（2-3 天）                     ← 1️⃣ 第一波
│     └─ 目标：能看到漂亮的聊天界面 + 假数据渲染
│
阶段三 RAG + Hybrid（约 2 周，7/28 - 8/8）
│
├─ Demo 页连 FastAPI 后端（半天）                    ← 1️⃣ 第二波
├─ Demo 页补 RAG/Docs 渲染（半天）                   ← 1️⃣ 增量
├─ MCP Server Query Tool 骨架（1 天）                 ← 2️⃣ 第一波
│
阶段四 AgentEvalOps（约 2 周，8/9 - 8/22）
│
├─ FastAPI eval 接口（在阶段四内实现）                 ← Python
├─ 评测仪表盘骨架 + 假数据（1 天）                    ← 3️⃣ 第一波
├─ 评测仪表盘接真实数据（半天）                        ← 3️⃣ 第二波
├─ MCP Server 补全 RAG + 混合 Tool（半天）            ← 2️⃣ 第二波
│
阶段五 求职包装（8/23 - 9/5）
│
├─ Demo 页样式打磨 + 部署 Vercel
├─ MCP Server README + 演示 GIF
├─ 评测仪表盘样式打磨 + 截图放进简历
└─ 三个 TS 项目的面试话术准备
```

### 4.1 进一步扩展（有余力再做）

| 扩展项 | 工作量 | 价值 | 说明 |
|--------|--------|------|------|
| CLI 工具 `datapilot` | 100 行 TS | 中 | 终端直接查询：`npx datapilot query "上个月退款率最高的商品" --role ops`；可发布到 npm（简历加分）。当前阶段不优先，3 个核心 TS 项目做完再说 |
| Dashboard 用例详情页 | 100 行 TS | 低 | 单 case 详情 + trace 时间线独立页，CLI 输出已覆盖 |
| Dashboard 版本对比 | 80 行 TS | 低 | 两次运行对比，Markdown 报告已覆盖 |

## 五、风险与缓解

### 5.1 全局风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| AI 生成的 TS 代码有 bug，用户看不懂无法自己修 | 中 | 阻塞该模块 | 每次只让 AI 改一个小模块；出 bug 时把报错原样贴回对话让 AI 修；不做"自己排查 TS 代码"的事 |
| 三个 TS 项目同时推进，上下文切换频繁 | 中 | 哪个都做不完 | 严格按执行计划顺序；一次只 focus 一个 TS 项目 |
| npm 依赖安装失败（Windows 兼容） | 低 | 耽误 1-2h | Next.js / MCP SDK / Recharts / shadcn 全部跨平台纯 JS，无 native 模块 |
| Vercel AI SDK 版本更新 break API | 低 | 修复 1-2h | `package.json` 锁定版本号，不追 latest |
| Vercel 国内访问不稳定 | 中 | 面试官打不开链接 | 备选 Cloudflare Pages；兜底：本地截图 + GIF 提前准备好 |

### 5.2 各项目特有风险

| 项目 | 风险 | 缓解 |
|------|------|------|
| Demo | Next.js `/api/chat` 代理转发写错 → 前端收不到数据 | 先做非 streaming 模式；用 curl 单独测 FastAPI → Next.js → 浏览器每一跳 |
| MCP Server | Windows stdio 通信偶发编码问题 | 开发和调试阶段全程用 MCP Inspector (WebSocket 模式)，最后再切 stdio |
| Dashboard | FastAPI eval 接口和前端契约不一致 → 联调返工 | 前后端先对着同一份 OpenAPI Schema 开发；接口定好再写前端代码 |
| Dashboard | Recharts SSR 报错 | `'use client'` + `dynamic(() => import(...), { ssr: false })` |

### 5.3 时间风险

- 如果阶段三/四开发比预期慢，**Dashboard 可以降级**——阶段四原计划的 Markdown 报告 + 1 张截图放进 README 仍然能讲"评测闭环"
- **Demo 页和 MCP Server 不建议降级**——Demo 是招聘方第一眼，MCP Server 是面试核心话术
- 最坏情况：9 月上旬只完成 Demo 页 + MCP Server，Dashboard 用阶段四原计划 Markdown 报告替代

## 六、简历话术

三个 TS 项目完成后，简历中可以在 Python 技术栈之外，加一段 TypeScript/全栈能力相关的描述：

> **全栈工程化**：用 Next.js + Vercel AI SDK 构建 DataPilot 演示应用，支持多轮对话、结构化结果渲染（SQL/表格/图表/Trace）和 Tool Call 可视化；用 MCP SDK (TypeScript) 将 NL2SQL/RAG/混合分析封装为标准 MCP Server，支持 Claude Desktop、Cursor 等 AI 工具直接调用；用 Recharts + shadcn/ui 搭建 AgentEvalOps 评测仪表盘，可视化通过率、失败归因分布和用例详情。

面试追问应对：
- "为什么 MCP Server 用 TypeScript 而不是 Python FastMCP？" → 四个理由：① MCP 协议是 TypeScript-first 设计的，官方 SDK 的 spec 覆盖度和更新速度领先；② 进程隔离——MCP 调用不应拖起加载了 torch/pymilvus 的 Python 进程；③ Node.js 冷启动远快于 Python；④ 全栈能力展示，且 MCP 作为协议层独立于引擎层，证明了架构分层能力。如果未来需要深度集成（直接调用引擎内部函数而非 HTTP 转一层），FastMCP 更合适
- "前后端怎么通信？" → HTTP 协议，后端 FastAPI 不改业务代码；引擎和外壳解耦，各自用最合适的语言
- "你一个人写 Python 又写 TypeScript？" → 核心 Agent 引擎用 Python（LLM/向量检索/DataFrame 生态最成熟），产品外壳和工具协议用 TypeScript（前端框架和 MCP 协议最成熟），这是工业界 AI 应用的主流技术栈分工

## 七、开发约定

1. **三个 TS 项目放在项目根目录**：`demo-next/`、`data-pilot-mcp/`，和 `demo/`、`engine/` 并列
2. **AI 全量生成代码**：用户不需要手写 TS，只负责验收 UI 效果和数据正确性
3. **每个 TS 模块独立开发、独立验收**：不互相依赖，一个出问题不影响另一个
4. **出 bug 时**：把终端报错 + 浏览器控制台报错原样贴给 AI，让 AI 自己修
5. **npm 包管理**：用 `npm`（不用 `pnpm`/`yarn`），减少工具链复杂度
6. **代码注释**：TS 代码同样遵循项目中文注释规范（CLAUDE.md「代码风格」）
7. **TS 测试**：每个 TS 项目至少跑通一条自动化验证——类型定义测 Zod schema 解析/拒绝；Demo 页测 1 条关键路径；MCP Server 测 Tool 参数校验。不追求覆盖率数字，但 `npm test` 不能空跑
8. **图表库隔离**：Demo 页 Vega-Lite 通过 CDN 加载（不打入 npm bundle）；Dashboard Recharts 通过 `dynamic(() => import(...), { ssr: false })` 动态导入。同一 Next.js 项目中不出现两个图表库的 npm 依赖冲突
