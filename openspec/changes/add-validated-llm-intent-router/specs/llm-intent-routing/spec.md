## Purpose

为 DataPilot 顶层 Harness 提供受控的语义意图路由，使开放问法能够在 SQL、RAG、已登记 Hybrid、澄清和不支持之间得到可验证、可观测且失败关闭的选择。

## ADDED Requirements

### Requirement: 分层意图裁决

系统 SHALL 使用“确定性前置裁决与快路、至多一次 LLM fallback、确定性结果编译”的分层 Router。确定性安全拒绝、已登记澄清以及明确 canonical 问法 SHALL 不依赖模型；开放、未知、词义重叠或现有规则判为未支持的问法 SHALL 能进入 LLM fallback。LLM fallback SHALL 只影响顶层 SQL/RAG/Hybrid/终止选择，不得改变下游 Tool 的安全与证据合同。

#### Scenario: canonical 问法命中快路

- **WHEN** 请求与已登记的无歧义 SQL、RAG 或 Hybrid canonical 场景匹配
- **THEN** 系统返回合法路由决定且 Router 模型调用数为零

#### Scenario: 开放问法进入模型 fallback

- **WHEN** 当前问题完整但无法由确定性快路可靠裁决，或同时呈现多个取证意图
- **THEN** 系统至多调用一次 Router 模型并将其候选交给确定性编译器

#### Scenario: 前置安全决定不能被模型覆盖

- **WHEN** 输入触发已登记的安全、caller 或 closed-world 澄清前置决定
- **THEN** 系统不调用 Router 模型，且模型不能把该请求改成可执行 Tool 路径

### Requirement: 闭集模型提案与确定性编译

Router 模型 SHALL 只提出结构化候选：`intent` 必须属于 `sql/rag/hybrid/clarify/unsupported`；只有 `hybrid` 可以携带服务端已登记的 operator 标识，只有 `clarify` 可以携带服务端已登记的澄清类型。模型不得提供 SQL、Tool 名称、文档内容、权限、任意分支问题或最终答案。系统 SHALL 在执行前校验字段闭集、字段组合和服务端 registry，并由服务端构造最终 RAG requirement、Hybrid plan 或澄清模板。

#### Scenario: 合法 SQL 或 RAG 候选

- **WHEN** 模型返回 schema 合法的 `sql` 或 `rag` 候选且没有额外控制字段
- **THEN** 系统分别编译为需要 SQL Evidence 或受控 Document Evidence 的合法路由决定

#### Scenario: 合法已登记 Hybrid 候选

- **WHEN** 模型返回 `hybrid` 且 operator 存在于当前服务端 registry
- **THEN** 系统只使用 registry 中的固定计划构造 Hybrid 路由，保持两分支各至多一次的既有预算

#### Scenario: 未登记 Hybrid 或越权字段

- **WHEN** 模型返回未知 operator、任意分支问题、SQL、Tool 名称、答案或与 intent 不相容的字段
- **THEN** 系统拒绝该候选并失败关闭，不调用任何未由确定性合同授权的 Tool

#### Scenario: 模型请求澄清

- **WHEN** 模型返回 `clarify` 和已登记澄清类型
- **THEN** 系统使用对应的服务端澄清模板，而不是直接显示模型生成的自由文本

### Requirement: 最小化且独立授权的模型出站

Router 模型调用 SHALL 使用独立的 receiver、`intent_route` purpose、`router_prompt` data class 和版本化 policy identity。允许字段 SHALL 仅为模型 transport 所需的 `prompt/system_prompt/model`；prompt 内容 SHALL 只包含当前问题、闭集 intent 说明和已登记 operator/澄清类型目录，不得包含 caller identity、role、tenant、对话历史、Schema、SQL rows、文档正文、Evidence、凭据或下游 Tool 输出。

#### Scenario: 合法 Router 出站

- **WHEN** 服务端配置的 receiver、purpose、data class 和字段与 Router policy 完全匹配
- **THEN** 调用可在记录安全运行身份后发出

#### Scenario: 继承其他模型用途的授权

- **WHEN** Router 尝试复用 `query_plan`、`sql_generation`、`answer_composer` 或其他用途的出站许可
- **THEN** 系统在网络调用前拒绝请求并进入 Router 失败关闭路径

#### Scenario: prompt 含未授权上下文

- **WHEN** Router prompt 投影包含 caller、Schema、rows、文档正文、Evidence 或历史字段
- **THEN** 确定性投影/策略校验失败，真实网络调用数保持为零

### Requirement: 有界调用与失败关闭

单次顶层路由 SHALL 至多发生一次 Router 模型调用，Router retry SHALL 固定为零；该调用不扩大 SQL/RAG/Hybrid 深 Tool 预算。模型未配置、出站拒绝、超时、transport 失败、空响应、JSON/schema 错误或编译失败时，系统 SHALL 返回调用前已经形成的保守确定性结果，或已登记澄清/不支持终止，不得默认 SQL、RAG 或同时调用多个 Tool。

#### Scenario: 模型超时或不可用

- **WHEN** Router 模型超时、缺少凭据或 provider 不可用
- **THEN** 系统不重试模型，保留一次 attempt 事实，并返回保守结果而不是猜测可执行 route

#### Scenario: 响应不可解析

- **WHEN** 模型响应不是唯一合法 JSON 对象或不满足闭集 schema
- **THEN** 系统记录稳定 fallback reason，且深 Tool 调用数不超过保守决定允许的数量

#### Scenario: Hybrid Tool 预算保持不变

- **WHEN** 合法模型候选被编译为 Hybrid
- **THEN** SQL 和 RAG 分支仍各至多执行一次，总深 Tool 数仍至多为二

### Requirement: Router 决定可审计

每次顶层路由 SHALL 形成安全的 Router 运行投影，至少包含 Router mode、版本化 identity、决定来源、是否尝试模型、attempt 数、prompt/completion/total token 数、latency、候选校验结果和 fallback reason。Trace SHALL 不保存 prompt、原始模型响应、思维链、凭据或未授权业务上下文。公开 API 请求/响应 SHALL 保持向后兼容。

#### Scenario: 模型候选被采用

- **WHEN** 合法模型候选通过确定性编译并成为最终路由决定
- **THEN** Trace 将决定来源记录为 model，并记录一次调用的安全 usage 与 Router identity

#### Scenario: 模型候选降级

- **WHEN** 模型调用发生但候选未被采用
- **THEN** Trace 同时记录模型 attempt、校验/失败原因和最终 deterministic fallback 来源

#### Scenario: 敏感诊断不进入 Trace

- **WHEN** provider 返回原始错误、响应文本或内部异常
- **THEN** Trace 只保存 allowlisted 分类和数值 usage，不保存原始文本、stack、prompt 或 response

### Requirement: 版本化 Router 评测与默认激活

系统 SHALL 提供一个预注册、版本化的 40 题 Router decision set，固定包含 10 个 SQL、10 个 RAG、10 个已登记 Hybrid、5 个 clarification、5 个 unsupported 场景，其中 20 题标记为 deterministic fast-path、20 题标记为 model-eligible，并覆盖 canonical、改写、词义重叠和控制指令干扰。Formal Router Eval SHALL 在同一 decision set 上分别执行 deterministic baseline 和 `llm_fallback` candidate；每个 arm 的每个场景只执行一次 Graph，多个断言共享同一 ExecutionEvidence，且使用 fake 深 Tool 隔离答案质量。`llm_fallback` 只有同时满足质量、控制、安全、观测和 Live Dev Probe 完成门后才能成为服务端默认。

#### Scenario: Formal Eval 通过

- **WHEN** candidate 总体 route accuracy 不低于 90%、每类不低于 80%、canonical slice 无回归、model-eligible slice 相对 deterministic baseline 提升至少 10 个百分点，且所有 schema、安全、Tool 预算、usage 完整性断言 100% 通过
- **THEN** candidate 满足默认激活的 Router Eval 门

#### Scenario: Formal Eval 未通过

- **WHEN** 任一 required 质量阈值、安全/预算断言或 evidence completeness 不满足
- **THEN** artifact 必须为 failed 或 inconclusive，服务端默认保持 deterministic，change 不得声明完成

#### Scenario: Eval 与 Answer 质量分账

- **WHEN** Router Eval 使用 fake SQL/RAG Tool 完成场景
- **THEN** 报告只能声明意图/Tool 选择质量，不得声明 SQL 正确率、RAG 引用质量或最终回答质量

#### Scenario: 客户端尝试选择 Router

- **WHEN** API 或 MCP 客户端提交 Router mode、模型或 operator 配置
- **THEN** 服务端忽略或拒绝该控制输入，Router mode 只由服务端配置决定
