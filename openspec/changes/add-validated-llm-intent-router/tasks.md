## 1. 合同与失败回归

- [x] 1.1 新建本 change 的开发 notes/checklist，登记 `LLMR-P1` 时点、三题、证据、12 attempts/50,000 tokens/12 分钟整轮预算和阻塞关系；回读 notes 确认 Probe 在真实调用前已登记且没有复制 runbook 公共条款。
- [x] 1.2 先增加当前实现的行为锁定与失败回归：canonical fast path、开放改写进入 model-eligible、模型不得覆盖前置安全/澄清、未登记 Hybrid 失败关闭；运行该聚焦测试，确认新增能力测试在实现前按预期失败、历史 deterministic 测试仍通过。
- [x] 1.3 以 additive 方式实现闭集 Router candidate、Router run evidence 和 `deterministic/model/controller` decision source，并通过构造器/反例测试验证字段组合、usage 数值、未知枚举、额外字段及非法 RouteDecision 全部被拒绝。
- [x] 1.4 新增版本化 Router outbound policy identity、`intent_route × router_prompt × prompt/system_prompt/model` 精确规则和 prompt 最小投影；用 fake transport 验证合法调用可达、复用其他 purpose/增加字段/夹带 caller、Schema、rows、Document、Evidence 或 history 时网络调用数为零。

## 2. 组合 Router 核心实现

- [x] 2.1 实现固定 Router prompt、严格单 JSON 解析和纯确定性 compiler；用 fake 响应覆盖 SQL、RAG、registered Hybrid、两类 clarification、unsupported、未知 operator、越权字段、空/多 JSON 和 schema 错误，验证只有 registry 内容能形成最终计划/模板。
- [x] 2.2 实现 fast-path eligibility 与组合 Router：前置决定/canonical 零模型，model-eligible 至多一次，失败返回调用前保守决定；运行表驱动测试验证 retry0、无 catch-all 默认 Tool、SQL/RAG 单 Tool和 Hybrid 两 Tool预算不变。
- [x] 2.3 基于现有 OpenAI-compatible transport 实现 per-attempt Router client factory，沿用当前服务端 provider/model但隔离 usage；用并发 fake 测试验证两个请求的 calls/tokens/latency 不串线，缺 key、timeout、transport error 均只形成一次失败 evidence。
- [x] 2.4 增加服务端 closed-world `deterministic|llm_fallback` mode 和应用组装接线，禁止请求体/Web/MCP 选择 mode/model/operator；运行配置与 TestClient 测试验证未知值启动失败、显式 deterministic 完全保持历史行为、candidate 仅由服务端启用。
- [x] 2.5 将 Router identity/source/attempts/usage/latency/validation/fallback 安全投影到 JSONL Trace/Eval evidence，保持公开 API schema 兼容；运行 API/Trace 测试验证 adopted 与 fallback 两条路径同源，且 prompt、raw response、stack、凭据和私有上下文均不出现。
- [x] 2.6 运行 Router/contracts/governance/API/Trace 的聚焦测试集合并修复失败；记录命令和结果，后续代码未变化时不重复运行已被更广验证覆盖的同一集合。

## 3. 首条真实纵向链准备

- [x] 3.1 用 fake Router client 和真实 Harness adapters 打通 `question → model proposal → compiler → SQL/RAG/Hybrid Tool → API/Trace` 三路纵向集成测试，验证每路 route、operator、Graph steps、Tool count、四轴和 Router evidence 闭合。
- [x] 3.2 在真实调用前运行 M35/M38 Router、Harness、API/Trace 与 M31 outbound policy 的受影响回归；只有这些共享合同测试通过才允许进入 Probe，并在 notes 记录尚未被真实验证的风险。
- [x] 3.3 创建 Probe 前 checkpoint：记录当时 HEAD、change 相关 dirty files、实现范围、聚焦验证、运行身份、依赖状态和待执行命令；回读确认默认切换及其依赖任务都明确被 `LLMR-P1=continue` 阻塞。

## 4. Live Dev Probe 硬门

- [x] 4.1 按 runbook 完成 `LLMR-P1` preflight，确认 Qwen、数据库、Knowledge runtime、Trace/usage 记录和三题数据身份可用；依赖未就绪则记 `inconclusive/stop` 并停止。
- [x] 4.2 严格按 design D8 通过真实 `/api/query` 执行开放 SQL、政策 RAG、registered Hybrid 三题各一次，立即把每个 attempt 的时间、代码阶段、HEAD/dirty、命令、Response/Trace/usage、三态结果及 `continue/revise/stop` 写入 notes；验证累计不超过 12 attempts、50,000 tokens、12 分钟。
- [x] 4.3 若首次结果为可定位 `failed/revise`，只完成一次最小代码修复并只重验失败题一次；验证 notes 能串起“首次执行 → 定位 → 最小修复 → 必要重验”，若无明确修复、再次失败、预算/identity 漂移或安全泄漏则 `stop`，不得换问法或重复抽样。
- [x] 4.4 审计 `LLMR-P1` 三态、usage、Tool budget、API/Trace 同源和私有载荷；只有形成完整 `passed → continue` 证据才勾选本项并解锁第 5～6 组，Probe 结果不得登记为 Formal Eval 或质量基线。

## 5. 默认激活与最小充分回归

- [x] 5.1 在 4.4 已形成 `passed → continue` 且聚焦合同测试通过后，将服务端默认 mode 切为 `llm_fallback`，保留 `deterministic` 一键回滚；运行配置、启动和 TestClient 测试验证默认/回滚身份、零客户端控制和 provider 不可用时的保守终止。
- [x] 5.2 运行受影响回归：M35/M38/M40 Harness/API/Trace、M31 governance，以及消费同一 `/api/query` 公共合同的 M50 Web/M51 MCP schema/adapter 测试；只修复本 change 引入的失败，不运行 Router Formal Eval，也不重跑未受影响的 RAG/Text2SQL Eval。
- [x] 5.3 在实现和合同不再变化后执行唯一一次全仓 deterministic 测试、compileall、OpenSpec strict validate 与 `git diff --check`；若失败先修复并只重跑失败子集，最终代码再变化时才重建必要的完成证据。

## 6. 状态固化与完成门

- [x] 6.1 先按 `CHANGELOG_INDEX.md` 路由更新当前 Phase 技术历史，再更新 `AI_CONTEXT.md`：记录用户取消原失败簇前置门、用户确认展示型收口、最终 Router 默认/回滚身份、Probe 证据和仍然不属于本 change 的 Phase 4B 理解/action 边界；不得把 Probe 登记为 Formal Eval 或质量基线。
- [x] 6.2 按 finish-module 流程审计注释、开发期 Probe 时点证据、notes、参考来源/许可证和验证快照；若实际复制了第三方表达性代码，补齐来源 commit、许可证头与本地改动，否则明确记录为设计迁移、无直接代码复制。
- [x] 6.3 对照 spec 逐项验收：LLM Router 已真实参与 model-eligible 路由、默认与回滚成立，所有安全/预算/观测合同及最小充分验证闭合且无 required 未完成项；只有全部满足才能将 change 标记完成并进入 OpenSpec archive，任一门未闭合必须保持未完成并写明阻塞项。
