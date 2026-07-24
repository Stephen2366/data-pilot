# DataPilot TypeScript 集成方案 — 审查意见

> 审查文档：[ts-integration-plan.md](ts-integration-plan.md)
> 审查时间：2026-07-24
> 审查结论：方向正确，有 1 处原则性矛盾、2 处遗漏、若干技术细节需修正。建议修改后按优先级推进。

## 一、总体评价

方案质量**中上**。三个方向（Next.js Demo、MCP Server、Eval Dashboard）选得合理，技术选型基本正确，分阶段交付思路清晰，面试话术储备到位。

核心问题就一个：**方案三与文档开篇"不改 Python 后端一行代码"的原则自相矛盾**。此外缺少共享类型层和 TS 测试策略。下面逐项展开。

---

## 二、方案一：Next.js Demo 页 ✅ 最值得做

**结论：保留，小修即可。**

### 优点

- 技术栈选择准确：Next.js 15 + Vercel AI SDK + shadcn/ui + Tailwind CSS 是 2026 年 AI 应用前端的主流组合，面试含金量高
- "先 Mock 再连后端"的两阶段交付非常务实——前端 UI 开发不阻塞 Python 后端进度，也能独立验收 UI 效果
- 复用 Vega-Lite spec（零转换）的设计正确，避免了前后端图表格式不一致的老问题
- 相比 Streamlit，Next.js 可部署到公网（Vercel），招聘方点链接就能看效果，面试体验远好于"我本地跑一下"

### 需要修改的点

**1. Streaming 的前提条件没说清楚（高优先级）**

文档 1.6 把 streaming 标为"可选"，但没有说明要实现真正的流式输出，FastAPI 端 `/api/query` 需要支持 SSE（Server-Sent Events）。当前后端是一次性返回完整 `AgentResponse`，不存在流式接口。如果第一版不做 streaming，那 Vercel AI SDK `useChat` 的核心价值就打了折扣。

建议：第一版先用非 streaming 模式（`fetch` + 一次性渲染），把 `/api/chat` 代理做扎实。Streaming 放到阶段三完成后作为增量。这恰好和 1.6 的现有策略一致，但需要在文档中**明确写出 backend 依赖**，避免后续联调时才发现接口对不上。

**2. 缺少国内访问方案（中优先级）**

文档多处提到 Vercel 部署，但 Vercel 在国内访问不稳定（CDN 节点被墙或很慢）。国内招聘方的面试官可能打不开链接。

建议补充备选方案：
- Cloudflare Pages（国内可访问）
- 本地开发截图 + GIF 兜底（面试前准备好）
- 或者接受 VPN 前提——明确写在文档里，不回避

**3. `next.config.ts` 稳定性（低优先级）**

Next.js 15 的 `next.config.ts` 仍是实验性特性。建议改为 `next.config.mjs`，避免踩坑。

---

## 三、方案二：MCP Server TypeScript ⚠️ 方向对，理由需修正

**结论：值得做，但技术理由要改，建议补对比分析。**

### 优点

- MCP 是 AI Agent 生态的核心协议，作为面试话术非常加分
- 三个 Tool 设计合理：`data_pilot_query` / `data_pilot_search_docs` / `data_pilot_analyze`，覆盖项目核心能力
- 代码量小（3 个文件约 210 行），投入产出比高
- MCP Inspector 调试方案避开了 Windows stdio 的坑

### 需要修改的点

**1. 技术选型理由过时（高优先级）**

文档 6.1 节面试话术中说：

> "MCP 官方 SDK 的 TypeScript 实现最成熟"

这个说法在 2026 年 7 月已经不太成立了。Python 的 **FastMCP**（`fastmcp`）已经非常成熟，被 Anthropic 官方推荐为 Python MCP Server 的首选方案。FastMCP 代码量更少、不需要启动额外进程、可以直接调用 Python 引擎内部函数。

**真正合理的理由应该是**：
- **进程隔离**：MCP Server 作为独立 Node.js 进程运行，不污染 Python 后端进程空间
- **启动速度**：Node.js 冷启动远快于 Python（尤其是不加载 torch/pymilvus 的干净进程）
- **全栈能力展示**：简历上 Python + TypeScript 双栈比纯 Python 更有竞争力
- **协议层职责分离**：MCP 协议是"外壳"，核心引擎是 Python，两层解耦证明了架构设计能力

建议把面试话术中的理由替换为上面几点。

**2. 缺少与 Python FastMCP 的对比分析（中优先级）**

建议在文档中加一小节，明确回答"为什么不用 Python FastMCP"——这恰恰是面试官会追问的问题。技术决策的思考过程比结论本身更有说服力。

**3. 本质是一个薄 HTTP 代理（低优先级——认知问题）**

MCP Server 的业务逻辑就是转发 HTTP 请求到 FastAPI，TypeScript 代码量很少。这不代表"不值得做"，而是意味着：不要期望它单独就能证明"我精通 TypeScript"。它更多是**协议层能力**的展示，TypeScript 深度的证明需要由共享类型包和 Demo 页来提供。

---

## 四、方案三：AgentEvalOps Dashboard ❌ 有原则性矛盾

**结论：方向有价值，但与文档核心原则矛盾，建议缩小范围或重新定位。**

### 致命问题：违反"不改 Python 后端一行代码"

文档开篇（第 2 行）声明：

> 三个独立 TypeScript 外壳项目，通过 HTTP 调 FastAPI，不改 Python 后端一行代码。

但 3.5 节明确要新增 3-4 个 FastAPI 接口：

```python
# GET  /api/eval/summary          → 返回仪表盘聚合数据
# GET  /api/eval/cases            → 返回用例列表（支持筛选/分页）
# GET  /api/eval/cases/{case_id}  → 返回单 case 详情 + trace
# POST /api/eval/runs             → 触发一次评测运行（可选）
```

这是**自相矛盾**。要么：
- **方案 A（推荐）**：承认 Dashboard 需要新增 Python 接口，把它归入阶段四 AgentEvalOps 的 Python 开发任务，不再声称"不改 Python 后端"
- **方案 B（降级）**：Dashboard 纯前端 Mock，数据写死在 JSON 文件中，只展示 UI 效果，不连后端

### 其他问题

**1. 时间估算过于乐观**

"1-2 天骨架 + 1 天接真实数据"的前提是 FastAPI eval 接口已经就绪。但按照执行计划，这些接口是阶段四才实现的——前端和后端的时间线是耦合的。联调阶段一旦后端接口和前端契约不一致（文档自己也在 5.2 承认这是风险），返工成本不低。

**2. 两个图表库混用**

Demo 页用 Vega-Lite，Dashboard 用 Recharts——在同一个 Next.js 项目中同时引入两个图表库会导致 bundle 膨胀。建议：
- 统一为一个图表库，或者
- Dashboard 用动态导入 (`dynamic(() => import(...), { ssr: false })`) 隔离 Recharts，不影响 Demo 页加载

**3. 功能范围可能 over-engineer**

4 个页面（首页仪表盘 + 用例列表 + 用例详情 + 版本对比）+ 多种图表 + 筛选，对于一个求职项目来说可能过重。文档自己也说可以降级（5.3 节），建议**直接降级为轻量方案**：

| 原计划 | 建议降级为 |
|--------|-----------|
| 首页仪表盘（4 统计卡片 + 3 图表） | 保留，这是核心展示 |
| 用例列表页（筛选/分页/跳转） | 砍掉，仪表盘上的失败率图表已经能讲 |
| 用例详情页（trace 时间线 + 历史对比） | 砍掉，单 case 详情用 Python `run_eval.py` 命令行输出替代 |
| 版本对比页（两次运行对比） | 砍掉，版本对比用 Markdown 报告就够了 |

**4. 和 Demo 共享项目的耦合风险**

Dashboard（eval API）和 Demo（query API）数据源完全不同，没有共享的业务逻辑，只有 UI 组件可能复用。合在一起会增加 Next.js 项目的复杂度。建议：如果做 Dashboard，要么保持独立项目，要么在共享项目中用清晰的目录边界（`app/(demo)/` 和 `app/(eval)/` route groups）隔离。

---

## 五、文档遗漏的重要方案

### 遗漏 1：共享 TypeScript 类型包 🔴 强烈建议加入

三个 TS 项目各自在 `lib/types.ts` 中定义 Zod schema，互相不共享。这会导致：
- AgentResponse 类型在 Demo 和 MCP Server 中各写一份，维护 drift
- 面试时被问"类型怎么管理的"没有好答案

建议新增**第零个 TS 项目**：`packages/datapilot-types/`

```
packages/datapilot-types/
  package.json
  tsconfig.json
  src/
    index.ts                  # 统一导出
    agent-response.ts         # AgentResponse Zod schema（Python Pydantic 的 TS 镜像）
    query-request.ts          # QueryRequest 类型
    eval-types.ts             # EvalCase / EvalReport 类型
    mcp-tool-types.ts         # MCP Tool 参数/返回值类型
  README.md
```

好处：
- **真正展示 TypeScript 类型设计能力**：泛型、Zod schema、类型推导——比一个薄 HTTP 代理有说服力得多
- **三个方案共享一份类型定义**，契约对齐
- **体现工程化思维**：Python 端有 Pydantic Schema，TS 端有 Zod Schema——"两端类型同步"是很好的面试 talking point
- **代码量小，优先级高**：~100 行，半天搞定，三个方案都能受益

### 遗漏 2：轻量 CLI 工具（可选加入）

一个 `datapilot` 命令行工具，终端直接查询：

```bash
npx datapilot query "上个月退款率最高的商品是什么？" --role ops
npx datapilot eval --report          # 跑评测看结果
```

代码量约 100 行，但：
- 可以发布到 npm（简历上有 npm 包链接是大加分）
- 展示 Node.js CLI 开发能力（`commander` + `chalk` + `ora`）
- 面试官可以跑，终端体验比网页更快

### 遗漏 3：没有 TS 测试策略 🔴 必须补

Python 端每个模块都有完善的 pytest（当前 67 passed），但整个 TS 方案文档**没有提到任何测试工具或测试策略**。这在技术方案的完整性上是明显的缺口，面试时被问到"前端怎么测的"会丢分。

建议至少：

| 项目 | 测试工具 | 最低覆盖 |
|------|---------|---------|
| `datapilot-types` | Vitest | Zod schema 解析/拒绝快照测试 |
| Demo 页 | Vitest + Playwright | 1 条关键路径（输入问题 → 渲染回复卡片） |
| MCP Server | Vitest | Tool 参数校验 + Mock HTTP 响应 |
| Dashboard | Vitest | 组件渲染快照 |

在"开发约定"中补一条：

> **TS 测试要求**：每个 TS 项目至少覆盖关键路径测试，Mock 阶段可只写组件渲染测试，连接后端后补 E2E smoke。

### 遗漏 4：Monorepo 工具（随共享类型包自然引入）

如果加入共享类型包，三个 TS 项目就自然需要一个轻量 monorepo 工具来管理依赖和构建。推荐 **npm workspaces**（零额外依赖）或 **Turborepo**。

---

## 六、执行计划层面的建议

### 6.1 M11 验收必须先完成

当前 `AI_CONTEXT.md` 显示 M11 是"已收工，待验收"。按照项目工作约定，必须先 `accept-module` 通过才能进入下一模块。执行计划中"立即开始 Demo 页"的排期建议先插入：

```
现在（7/24）
├─ ★ 先跑 accept-module M11  ← 插入这一步
├─ M12 收尾（1-2 天）
├─ 再开始 Demo 页静态 Mock 版
```

### 6.2 阶段三 RAG/Hybrid 依赖前置

Demo 页的 `docs-card.tsx` 和混合推理展示依赖阶段三完成。建议 Demo 页第一波 Mock 阶段先做好所有 UI 组件的架子（包括 RAG 和 Hybrid 卡片），用假数据渲染，等后端能力就绪后只需替换数据源。

### 6.3 优先级建议

从求职 ROI 角度，建议优先级排序：

```
1. datapilot-types（共享类型包）    ← 半天，全部方案的基础
2. Demo 页                           ← 面试第一眼，最重要
3. MCP Server                        ← 面试核心话术
4. Dashboard（降级版）               ← 能做就做，不能做用 Markdown 报告兜底
5. CLI 工具                          ← 有余力再做
```

---

## 七、修改清单汇总

| # | 位置 | 问题 | 建议操作 |
|---|------|------|----------|
| 1 | 全文 | 声明"不改 Python 后端"但方案三要加接口 | 方案三改为承认需要新增 API，或降级为纯前端 Mock |
| 2 | 二/6.1 | MCP 选型理由"SDK 最成熟"已过时 | 改为"进程隔离 + 轻量启动 + 全栈能力展示" |
| 3 | 新增 | 缺共享 TS 类型包 | 新增 `packages/datapilot-types/`，三个方案依赖它 |
| 4 | 新增 | 缺 TS 测试策略 | 开发约定补测试工具和最低覆盖要求 |
| 5 | 一/1.6 | Streaming 前提条件未说明 | 明确写"第一版不做 streaming，后端需支持 SSE 才能开启" |
| 6 | 一/1.3 | Vercel 国内不可访问 | 补充备选部署方案（Cloudflare Pages / 截图兜底） |
| 7 | 一/1.4 | `next.config.ts` 实验性 | 改为 `next.config.mjs` |
| 8 | 三/3.3 | Vega-Lite + Recharts 混用 | 统一或动态导入隔离 |
| 9 | 三/整体 | 功能范围过重（4 页面 + 多图表） | 缩为单页面首页仪表盘 |
| 10 | 三/3.1 | 和 Demo 共享项目有耦合风险 | 使用 Next.js Route Groups 隔离 |
| 11 | 四 | 执行计划跳过 M11 验收 | 先跑 accept-module M11 |
| 12 | 新增 | 缺备选方案：CLI 工具 | 可选加入，提升简历竞争力 |
| 13 | 二/2.2 | 缺与 Python FastMCP 对比 | 加一小节说明为什么选多开一个 Node.js 进程 |

---

## 八、审查结论

**方案方向正确，建议修改后推进。** 核心要改三件事：

1. **解决原则性矛盾**：方案三不再声称"不改 Python 后端"
2. **补共享类型层**：这是三个方案的基础设施，也是 TypeScript 能力的真正证明
3. **补测试策略**：和 Python 端的工程纪律保持一致

修改后按优先级顺序推进：共享类型 → Demo 页 → MCP Server → Dashboard（降级版）。
