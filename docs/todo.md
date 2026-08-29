# DataPilot 候选功能存档

> 记录以后可能加入、但尚未立项的功能。本文不是 roadmap、module plan 或实施承诺；真正开工前仍需结合最新状态、失败证据和用户目标单独评审。

## 受控 Skill

### 目标

把常见分析流程封装为版本化、可复用的 Skill。Skill 只负责把用户目标编译成 DataPilot 已登记的 typed plan / Evidence requirements，实际执行继续复用现有 Agent Loop、SQL / Knowledge Tool、SQL Guard、ACL、预算、Evidence、Trace 和 Eval。

### 首版边界

- 只加载仓库内预注册、带版本与内容 identity 的 Skill；不做运行时生成、上传、热注册或动态 Tool / Connector 平台。
- 客户端不能提交 Skill 文件、Prompt、路径、Tool 名称或权限配置，只能由服务端解析并选择允许的 Skill。
- Skill manifest 至少声明适用意图、必要参数、允许动作、资源预算、权限与 outbound policy、输出结构和 Eval case。
- Skill 不得直接执行 SQL、MCP、Python / Shell 或写业务数据；所有访问必须经过现有安全链。

### 可选首批 Skill

1. `metric-comparison`：把已有指标 / 时段比较能力封装成受控分析配方，验证产品运行时 Skill 链路。
2. `domain-pack-audit`：离线检查 Schema、指标、关联关系、示例与索引的一致性，并输出缺失或漂移报告。

### 参考结论

可参考 `D:\.Work\Practice\Python-Practice\references\data-analyst-vault-template` 的数据字典模板、渐进式索引读取、Skill 触发描述和索引维护流程。但该项目只有 Markdown 指令与示例，没有可复用运行时、测试或安全合同，且未提供 LICENSE；只借鉴思想，不直接复制或作为依赖。它的 `sql-generation` 会直接编写并交给 MCP 执行 SQL，不能照搬，以免绕过 DataPilot 的 QueryPlan、SQL Guard、RBAC、Evidence 和 Trace。

### 立项前检查

- 确认真实重复分析场景及现有 pipeline 无法低成本表达的收益，避免只给 NL2SQL 套一层名称。
- 单独冻结 Skill contract、catalog identity、选择规则、失败关闭行为及 Eval / Live Dev Probe。
- 不修改 Phase 4B 已完成的 closed-world 边界；作为后续独立模块实施。

## Agent 执行时间线

### 目标与收益

把当前页面中的 Action、EvidenceDelta、Budget、Termination、Knowledge child ledger 和 Trace 摘要整理成可读时间线，让用户看懂 Agent 做了什么、获得了哪些证据、消耗了多少预算以及为何停止；提升可信度与面试展示效果。

### 实现边界

- 只消费 FastAPI 已公开并通过 Zod 校验的安全投影，不读取 JSONL 私有内容或展示模型 Thought。
- 以 turn 为边界展示 `选择动作 → Tool Observation → Evidence gain / no-progress → budget before/after → termination`，SQL、RAG、Hybrid 和安全停止使用统一视图。
- 保留原始结果卡作为业务答案，时间线是解释层，不在前端重新推断 route、Evidence validity 或成功状态。
- 优先复用现有 `action_attempts` 等合同；只有确有展示缺口时才为后端增加最小公开字段，并同步 Python authority、fixture 和合同测试。

### 难度

中低。主要是前端 presenter、组件、样式和 Vitest / Playwright；若扩展公开合同则上升为中等。

## TypeScript MCP Adapter

### 目标与收益

让 Claude、Cursor 等 MCP Client 能把 DataPilot 作为标准数据分析 Tool 调用，同时继续由 FastAPI Router 决定 SQL / RAG / Hybrid，形成可展示的外部协议集成能力。

### 首版边界

- 新建轻量 Node / TypeScript adapter，通过 HTTP 调用现有 `/api/query`；不复制 Python Agent、Router、Evidence Gate 或 task 状态机。
- 首版只暴露统一的 `data_pilot_query` Tool，不拆分 SQL、RAG、Hybrid Tool，避免外部 Client 绕过顶层路由。
- 返回 bounded structured result：Answer、四轴状态、route、必要 SQL / rows、citations、reason code、trace identity 和最小 task/version 信息；不得输出私有 Evidence、完整内部 Trace 或无界 rows。
- 优先支持本地 stdio 和 demo/test caller；远程 transport、OAuth、生产身份与多租户 ACL 另行立项，客户端不能借 `user_role` 自行授权。
- Web 成为第二个 TypeScript consumer 后，再评估抽取共享 Zod contract package；Python / Pydantic 仍是唯一业务合同 authority。
- timeout / unknown outcome 不自动重放 mutation；多轮 task 必须沿用服务端签发的 task ID、expected version 与现有对账语义。

### 难度

中等。本地单 Tool adapter 较轻，主要难点是合同复用、task/version、错误映射、结果限流和集成测试；远程认证版属于高难度。
