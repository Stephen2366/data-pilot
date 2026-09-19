## Why

当前顶层 Router 通过关键词和两个固定 Hybrid 模板裁决 SQL、RAG、Hybrid 或停止，能够稳定执行已登记场景，但不能以语义方式覆盖开放问法。用户已于 2026-09-19 明确决定：不再以“先形成稳定失败簇”作为引入条件，本 change 直接引入受控 LLM Router；这一决定修订了 `docs/state/AI_CONTEXT.md:116` 的原重开门，但不放宽既有 Tool、安全、权限和证据合同。

## What Changes

- 新增“确定性快路 + 单次结构化 LLM fallback + 确定性编译/校验”的顶层 Router；危险输入、已登记澄清和明确 canonical 场景保留本地快路，其余开放或冲突问法允许模型提出 `sql/rag/hybrid/clarify/unsupported` 候选。
- 模型候选不能直接调用 Tool、生成答案、修改权限或创造 Hybrid operator；只有通过 closed-world schema、受控 RAG requirement/Hybrid plan 编译和现有 `RouteDecision` 不变量校验后才能执行。解析失败、超时、越权字段或未登记 Hybrid 一律失败关闭。
- 为 Router 建立独立 model purpose、outbound data class、运行身份、调用/usage/降级 Trace；模型只接收当前问题和闭集路由说明，不接收 caller identity、历史、Schema、rows、文档正文或 Evidence。
- 新增版本化开放意图 decision set 与 Router Eval artifact，对 deterministic baseline 和 `llm_fallback` candidate 做同集单次配对比较；Eval 只证明路由质量，不能冒充 SQL/RAG Answer Eval。
- 服务端保留 `deterministic` 基线/回滚模式，并在 Live Dev Probe 和 Formal Router Eval 完成门全部通过后将 `llm_fallback` 设为默认；客户端不能选择 Router 模式或模型。
- 不改变 Phase 4B `understand_turn()`、TaskDelta、next-action Controller、默认 Text2SQL/RAG 模型、Knowledge release、数据库或已有 Hybrid branch 执行预算。

## Capabilities

### New Capabilities

- `llm-intent-routing`: 顶层意图 Router 的结构化模型提案、确定性校验/降级、可观察运行身份、开放问法评测及默认激活合同。

### Modified Capabilities

无。仓库当前没有已发布的 OpenSpec capability；本 change 以 additive capability 描述现有 Harness Router 的新行为。

## Impact

- 主要代码面：`engine/harness/router.py`、`engine/harness/contracts.py`、`engine/harness/graph.py`、`engine/governance.py`、`app/main.py`、`app/api/query.py` 与安全 Trace/runtime projection。
- 测试/Eval 面：M35/M38 Router、Harness、API/Trace 回归，以及新的 Router decision set、runner、validator、artifact/report。
- 运行面：复用现有 OpenAI-compatible chat transport，但新增独立 `intent_route` purpose 与 `router_prompt` data class；LLM fallback 每次路由至多一次调用，retry 仍服从服务端配置且本 change 的 Router 默认冻结为 `retry=0`。
- 兼容面：公开 `/api/query` 请求和响应结构保持兼容；`RouteDecision`/Trace 以 additive 字段记录 `model` 来源、Router identity、usage 和 fallback reason。旧 deterministic fixture 和历史 artifact 不改签。
- 依据：当前关键词/固定模板见 `engine/harness/router.py:22-134`，可注入 seam 见 `engine/harness/graph.py:68-72`，当前 source 闭集见 `engine/harness/contracts.py:239-268`；现有 Eval 仅覆盖固定场景见 `eval/harness_contracts.py:31-36`、`eval/harness_hybrid_contracts.py:23-39`。
