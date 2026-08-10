# M28 Text2SQL 收尾型技术体检笔记

> 目标：判断当前 Text2SQL 是否可以收尾进入 RAG、是否仍有应优先处理的确定性工程问题，以及未来回到 Text2SQL 时的优化入口。
>
> 本轮边界：只审查、只运行不调用真实 LLM 的确定性验证；不改产品代码、Eval 合同、默认配置或 state 正式文档。

## Review checklist

- [x] 阅读 `AGENTS.md`、`AI_CONTEXT.md` 及其要求的 runbook / eval / database / schema retrieval state 文档。
- [x] 阅读 `m27-plan.md`、`m27-notes.md`，确认当前合同为 `m27-v2`，旧 v1 只读。
- [x] 盘点 Text2SQL、Schema Retrieval、Eval、Review、Trace 当前实现与测试。
- [x] 复核 Core / Stress / Database Exception 既有 artifact 和 checkpoint，不混算重叠 Scenario。
- [x] 运行不调用真实 LLM 的确定性验证；全仓测试发现非 hermetic 用例后及时终止并单独记录。
- [x] 形成“现在修 / 随 RAG 修 / 未来专项优化”三级建议。
- [x] 修正 `orders_wide` 的业务时间语义，并补宽表/星型结果对账。
- [x] 升级 `m27-v3`，分离物理字段、metric key、输出 alias，并增加 catalog 静态可满足性校验。
- [x] 恢复 Eval run-scoped Schema Vector Index 的创建、注入、身份记录与关闭生命周期。
- [x] 为全仓测试增加真实 provider fail-fast guard，并修正旧链路/新链路测试注入。
- [x] 跑完聚焦、相关与全仓确定性测试；不运行真实 LLM Eval。

## 用户确认后的实施记录（2026-08-10）

- **宽表时间**：QueryPlan guidance 与 canonical Scenario 统一按 `orders_wide.paid_at` 过滤业务月份；`snapshot_at/batch_id` 只负责快照版本。保留 seed 中宽表与星型按渠道 GMV 对账，并新增“误按 snapshot_at 过滤 6 月必为空”的回归断言。`june_channel_gmv_dashboard` 增加 Result / Output 断言，零行结果不能再只靠 Schema Context 假通过。
- **合同可满足性**：当前合同升级到 `m27-v3`。修正商品退款率、递归类目、价格历史、渠道退款率、优惠券 GMV 五条 Schema Context，把输出 alias 从 `required_columns` 移出；catalog loader 现在逐分支验证物理表/字段与 metric key，错误在执行前失败。Review 继续兼容 v1/v2 只读 artifact。
- **运行级索引**：`SQLiteRunEnvironmentFactory` 在新 pipeline 的 EvalRun 开始时构建一次 index，通过 `app.state.schema_vector_index` 供全部 Scenario 复用，并在 close 时释放。resolved runtime identity 增加 `schema_vector_index_reuse=run_scoped` 与 Milvus initial/final row count。关闭环境时只恢复本环境接管的 override/state，避免误清其他组件状态。
- **测试隔离**：新增 pytest autouse provider guard；未 mock 的新 pipeline LLM 调用立即失败。M4/M5/M16 的 legacy 合同显式传 `force_new_pipeline=false`，M18 smoke 与新 pipeline 测试显式注入 fake client。
- **验证**：M27/Review/数据库聚焦测试 `28 passed`；legacy API/Trace `22 passed`；M18 smoke `4 passed`；new pipeline `8 passed`；全仓 `223 passed, 1 warning in 464.31s`。warning 为既有 Starlette/httpx deprecation。另通过 `compileall` 和 `eval.run_eval --help`。没有运行真实 LLM Eval，也没有改变模型、检索、embedding、数据库、oracle、timeout/retry 或产品 API 默认。

## 已确认的口径

- Core `28 passed / 0 failed / 6 not_observed` 表示 17 个已完成 Scenario 的 required assertions 全过；另 2 个 Scenario 因 QueryPlan timeout 没有候选 SQL。它不是稳定性结论，也不是正式长期 baseline。
- Stress `7 passed / 14 failed / 4 not_observed` 为单轮 advisory evidence；Database Exception 复用部分 Stress Scenario，二者不能相加。
- 当前默认仍是 Qwen `qwen3.7-plus` + `inmemory/deterministic/weighted`；已有真实 M27 快照使用 Milvus + DashScope embedding 是显式实验条件，不代表默认切换。

## 初步发现（持续补充）

### F1【已解决】：M27 新 runner 丢失 run-scoped Schema vector index（确定性工程问题，P0）

修复前证据：

- 旧 runner 的 `_build_eval_schema_vector_index()` + `seeded_api_client()` 会在一轮 run 开始时构建一次 index，并放入 `app.state.schema_vector_index` 供所有 case 复用。
- `AI_CONTEXT_CHANGELOG` 的 M20 记录明确把 `schema_vector_index_reuse=run_scoped` 作为已修复的索引卫生结论；因此这不是新功能建议，而是 M27 入口切换时产生的生命周期回归。
- 当前 M27 `main()` 直接创建 `SQLiteRunEnvironmentFactory`；`SQLiteRunEnvironment` 只设置 `trace_path`，没有创建或注入 `schema_vector_index`。
- `/api/query` 传入的 index 因而为 `None`，`retrieve_schema()` 每个 Scenario 都调用 `build_configured_vector_index()`。
- Milvus adapter 在检查 collection 是否可安全复用之前，先对全部 195 个 schema documents 执行 embedding；所以显式 Milvus Eval 会按 Scenario 重复整批 embedding/adapter 初始化。
- DashScope provider 每批最多 20 条，195 docs 约需 10 个 document embedding HTTP 请求，随后每题 query 再 1 次；新 provider 每题重建，内存 cache 也无法跨题复用。粗略计算：Core 19 题约 209 次、Stress 9 题约 99 次、Database Exception 7 题约 77 次 embedding HTTP 请求。
- 既有 raw checkpoint 的 `schema_retrieval` span 可见：Core 19 题合计约 **146.94s**（均值 7.73s/题），Stress 约 **78.31s**（8.70s/题），Database Exception 约 **61.96s**（8.85s/题）。这不是纯理论风险。
- 额外只读构造检查确认：`SQLiteRunEnvironmentFactory.create()` 后 `app.state` 没有 `schema_vector_index`，尽管 resolved runtime identity 会记录 backend。

影响：放大网络调用、耗时、费用和失败面；与 M27 计划中“RunEnvironment 初始化并复用 run-scoped vector index”的生命周期承诺不一致。默认 inmemory 路径也会重复建索引，但代价较小。

解决结果：`RunEnvironment` 现已拥有一次性 index 初始化、注入和 close；新 pipeline 的一个 EvalRun 只构建一次 index，并通过 fake index 测试验证检索与关闭次数。runtime identity 同步记录 `schema_vector_index_reuse=run_scoped` 及可用的 Milvus row count。

### F2【已解决】：`orders_wide.snapshot_at` 的提示口径与数据语义冲突（确定性产品正确性问题，P0）

修复前证据：

- `engine/nl2sql/prompt.py` 明确要求渠道 GMV 月度快照按 `orders_wide.snapshot_at` 过滤业务月份；`database-current-state.md` 也采用相同说法。
- `orders_wide.md` 与 ORM 把 `snapshot_at` 定义为“抽取/快照时间”。seed 中所有宽表行的值固定为 `2026-07-01 03:00:00`，batch 为 `orders_wide_20260701_0300`。
- Stress 的 `june_channel_gmv_ranking` 严格按提示生成 `snapshot_at >= '2026-06-01' AND < '2026-07-01'`，得到 0 行；星型 reference 返回 6 个渠道。
- 更关键的是，同一轮 Core 的 `june_channel_gmv_dashboard` 也生成相同 0 行 SQL，却因为该 Scenario 只有 `schema_context` assertion 而被记为 passed。故“Core 已完成题全部通过”不能被理解为 17 道题的最终答案都正确；其中该题没有 Result oracle。

判断：这不是模型随机答错，而是“业务月份”和“快照抽取时间”被混成同一时间字段。当前表也没有独立 `business_month` / `snapshot_period` 字段，无法自然表达“7 月 1 日抽取的 6 月快照”。

解决结果：业务月份统一按 `paid_at`，`snapshot_at/batch_id` 只选择快照版本；prompt、canonical contract 和数据库 state 已同步。seed 回归同时证明宽表与星型渠道 GMV 对账一致，并证明误按 `snapshot_at` 过滤 6 月会得到空集。dashboard 已补 Result / Output 断言，不再允许零行结果只靠 Context 假通过。

### F3【已解决】：4 条已观察 Stress + 1 条潜在 Core `schema_context` 存在合同/scorer 命名空间错位（确定性 Eval 问题，P0）

修复前证据：

- 非 alternatives 路径的 scorer 分别计算 `required_columns - physical_fields` 与 `required_metrics - metrics`；它不会把 metric/output alias 当 column。
- catalog 却把下列派生输出写入 `required_columns`：`root_category/item_gmv`、`avg_price`、`refund_rate`、`gmv`。
- 已有 Stress artifact 因此分别报告缺这些“字段”。其中 `june_coupon_type_gmv` 的 candidate SQL、列和结果都与 oracle 匹配，唯一 failed 就是该 Schema Context 断言。
- 静态扫描还发现 Core 的 `june_product_refund_rate_ranking` 同时声明 `required_columns: [product_name, refund_rate]` 与 `required_metrics: [refund_rate]`。`refund_rate` 不是物理字段，因此只要未来该题成功走到 Schema Context 评分，当前 scorer 就会稳定报 `schema_context_missing`。本次 Core 因 QueryPlan timeout 把它记为 not_observed，暂时遮住了这个必现失败。

影响：Stress 的 14 failed 至少有 4 条不能解释为 Text2SQL 业务失败；更重要的是，当前 Core 合同存在一条成功执行后仍无法通过的潜在断言，未来很难得到可信的 `Gate passed`。

解决结果：合同已显式升级为 `m27-v3`，旧 v1/v2 artifact 只读保留。`required_columns` 只表达物理字段，metric key 与输出 alias 分别交给自己的 assertion；5 条错位合同已修正，catalog loader 会在执行前静态验证表、字段和 metric 对当前 domain schema 可满足。

### F4：部分 Stress 失败是合同可裁决性/分类问题，不宜直接拿来调模型（候选 P1/P2）

- `june_channel_refund_rate_ranking`：候选数值与 oracle 相同；差异只在 5 个退款率为 0 的渠道顺序。reference 要求 `channel_name ASC`，题面只说“按退款率从高到低”，未声明 tie-break。当前 `result_match` 顺序敏感，因此记 1 条 failed。
- `june_avg_price_history`：50 个商品的业务数值与时间 overlap 口径正确，但多输出 `product_id`，导致 Result + Output 两条 failed；这是输出合同问题，不是 SCD 计算错误。
- `order_item_amount_reconciliation`：候选按订单分组返回 5 行 `1`，而合同要单行总数 `5`，且 alias 为 `mismatched_order_count`/`mismatch_order_count` 不同；这里同时有真实聚合粒度问题和表面列名问题，当前 scorer 在 projection mismatch 处提前结束，未显式呈现更深层语义错误。
- `digital_electronics_recursive_item_gmv`：候选只覆盖直接子类并按子类输出 3 行，未做完整递归、未归约到一级类目；属于真实能力缺口。
- `channel_net_refund_amount`：QueryPlan 已生成但缺 `orders_channel`，随后 SQL generation timeout；JoinPath failed 是对已观察计划的真实裁决，不应误改成 timeout 假失败。

### F4a【部分改善、非阻塞】：Core 的 assertion 覆盖不是“每题端到端结果门”（解释边界）

修复前 19 个 Core Scenario 中，`june_actual_amount_sum` 只有 `metric_mapping`，`june_channel_gmv_dashboard` 只有 `schema_context`。M28 已为 dashboard 补齐 Result/Output，消除已确认的零行假通过；`june_actual_amount_sum` 仍是一条“指标绑定能力”合同，不应被解释为完整端到端答案门。

这不表示 M27 统计公式错误，而是合同覆盖层级不同。收尾判断应表述为“Core required contract 在已观察证据上全过”，不能表述为“所有 Core 最终答案均已验证正确”。未来若把 Core 当发布硬门，至少应为这类部分能力题补端到端 oracle，或明确移出业务答案硬门。

### F5：M27 projector 的完整性防御偏弱（候选 P1）

`project_eval_run()` 会过滤 policy 选中的 Scenario，但不会验证：policy 与 run 的 suite identity 是否一致、所有 selected Scenario/replicate/assertion 是否完整存在、是否有额外/重复 identity。正常 `Evaluator` 内存对象满足这些不变量，但被读取/构造的“completed”对象可能在缺题时仍产生看似 passed 的 Gate。

初步建议：补 artifact loader/validator 或在 projector 前做 closed-world identity 校验；它是 Eval 信任链问题，不需要真实 LLM。

### F6：Review bundle 的长期可追溯性仍依赖短期 checkpoint（候选 P2）

- 当前 review v2 的 SHA-256 能证明 bundle 生成后 source 文件未被替换，这是有效加固。
- 但 completed artifact 不保存 candidate SQL/有限反例，review 必须读取 `.agent_work/temp` checkpoint；清理 checkpoint 后无法重建 review。
- `build_review_bundle()` 允许用当前 catalog 解释 v1 artifact，但没有核对当前 catalog/selected contract hash 与 artifact 是否对应；它只对齐 scenario/replicate 及 assertion 的 id/kind/status。

初步建议：不阻塞进入 RAG。未来做“证据保留/可恢复 Eval”时一起解决：completed artifact 保存足够脱敏的 SQL/有限 diff，或把 review bundle 作为明确的长期派生产物；同时收紧 catalog provenance。

### F7：Trace / LangFuse 的隐私边界需要在重新启用 Cloud 前复核（候选 P2）

JSONL trace 本地会保存完整 question/answer/rows，符合当前短期调试定位；但 LangFuse post-hoc adapter 会上传完整 question 和 answer，未经过 M27 assertion payload 的严格 allowlist/redaction。LangFuse 默认关闭，因此不阻塞当前收尾；RAG/Hybrid 若重新启用 Cloud，应先统一脱敏策略。

### F8【已解决】：全仓 pytest 已不再是 hermetic deterministic suite（确定性工程问题，P0）

修复前证据：

- `/api/query` 已在 M27 改为默认 `force_new_pipeline=True`。
- 多组旧 API 测试仍按模板/旧链路结果断言，却没有显式传 `force_new_pipeline=False`，包括 `tests/test_m5_agent_response.py` 的普通查询/图表测试、`tests/test_m4_nl2sql.py` 的 legacy LLM 测试；后者注释明确说“显式 false”，请求体实际没有该字段，而且 monkeypatch 的是 generator module，不是 pipeline 已导入的引用。
- `tests/test_m18_phase3b_smoke.py` 声称不访问真实 LangFuse Cloud，但其 disabled smoke 仍会通过默认新 Text2SQL 调用真实主模型。
- 本轮尝试全仓 pytest 时，这些测试实际进入 Qwen QueryPlan 调用；网络被沙箱/Windows 拒绝并在 trace 中记录 `network_permission_denied`，没有成功外发，也没有生成新 EvalRun，但测试出现失败。为遵守本轮边界，已主动终止全仓进程。

影响：全仓测试会受网络、凭证、模型可用性和费用影响；“208 passed 且未调用真实 LLM”的既有说明与当前默认路由组合不再可靠。开发者可能在普通回归中意外发模型请求。

解决结果：旧 M3/M4/M5 合同测试显式使用 legacy 路径，新 pipeline 与 smoke 显式注入 fake client；pytest autouse guard 默认禁止未 mock 的真实 provider。全仓确定性测试最终 `223 passed, 1 warning`，没有真实 provider 调用。

## 最终收尾判断

- **Text2SQL 可以暂时告一段落并进入 RAG。** 本轮识别的四项进入 RAG 前确定性问题 F1/F2/F3/F8 均已解决，全仓确定性测试通过。
- F5/F6/F7 属于 Eval 信任链、长期证据保留和 Cloud 隐私加固，不阻塞当前阶段切换；其中 F7 应在 RAG/Hybrid 重新启用 LangFuse Cloud 前处理。
- Stress 中仍有递归类目、两阶段金额对账、最小投影、稳定排序和 JoinPath 等真实能力缺口，但它们适合作为未来 Text2SQL 专项优化入口，不值得现在继续无边界调分。
- 当前没有 `m27-v3` 真实 LLM 基线；这是“尚未复测”，不是代码未收尾。除非需要发布级能力声明，否则不必为了进入 RAG 立即补跑。

## 收尾建议分级（最终状态）

### 已完成：窄的确定性收尾包

1. **宽表时间语义（F2）**：已统一为业务时间用 `paid_at`，`snapshot_at/batch_id` 只选择快照版本；已补宽表与星型结果对账。
2. **Schema Context 合同可满足性（F3）**：已分开物理字段、metric key、输出 alias，修正 5 条合同并增加静态可满足性校验；合同升级为 `m27-v3`，旧 v1/v2 artifact 只读保留。
3. **run-scoped vector index（F1）**：已恢复整轮复用语义，由 `RunEnvironment` 一次初始化、注入、关闭，并用 fake index 验证生命周期。
4. **测试隔离（F8）**：已修复旧 API/Smoke 的 pipeline 选择和 fake 注入，增加真实 provider fail-fast guard，全仓 pytest 恢复确定性。

以上四项均已用 fake/SQLite/静态测试完成验证；没有运行新的真实 LLM Eval，也没有切默认模型、检索、embedding、数据库、oracle、timeout/retry。

### 可随下一次 Eval 基础设施改动处理，不阻塞 RAG

- Projector/artifact closed-world 完整性校验（F5）：selected Scenario、replicate、assertion identity 必须恰好完整，policy/hash 必须与 run 对账。
- `oracle_fixture_identity` 目前由调用方原样写入 resolved identity，factory 没有验证它确实对应当前 SQLite seed；未来应只接受已注册 fixture。
- selector loader 对 `pipeline_mode` / `fusion_strategy` 主要依赖类型注释，非法字符串不会在 YAML 加载期严格失败；可与严格 loader 加固一起修。
- `eval.ports` 的 Protocol 注解使用了未导入的 `EvalRunSpec` / `ResolvedRuntimeIdentity`；`from __future__ import annotations` 让运行不报错，但静态类型工具会报未定义名称。属于低风险、顺手修复项。
- Review bundle 的证据保留与 catalog provenance（F6），以及 LangFuse Cloud 的 question/answer 脱敏（F7）。

### 未来回到 Text2SQL 时的高价值切入口

1. **SchemaGraph 精简，而非先换 embedding**：本轮 Stress 的局部图常达 6–10 张表、72–128 个字段、多个无关 metric。当前 `build_schema_graph()` 为保证 recall 会给命中表补齐全字段，并以排序后的 anchor 补最短 JoinPath；这提高召回但也把选择压力推给 QueryPlan。未来可做“命中字段 + metric 依赖 + join key”的最小上下文，再单独验证 retrieval recall 与端到端收益。
2. **为递归和两阶段聚合增加计划表达力**：递归类目失败不是简单漏一句 prompt；当前 QueryPlan 没有 hierarchy/recursive intent。金额对账则需要“先按订单聚合，再统计不一致订单数”的嵌套聚合。优先增强结构化计划/验证 seam，而不是堆 few-shot 文案。
3. **把输出正确性拆细**：稳定 tie-break、允许/不允许附加列、alias、排序敏感性、业务数值应分层裁决。当前 projection mismatch 会掩盖更深的行粒度错误；未来报告应同时呈现最主要根因和次级差异。
4. **可靠性与成本证据**：保留 QueryPlan/SQL generation 分阶段 latency、真实 physical attempts 和 timeout stage；先消除 index 生命周期放大，再讨论 timeout/retry 或模型切换。
5. **只在确定性问题修完后做受控真实复测**：如果未来要比较模型/检索/embedding，应使用相同新合同、完整 runtime identity 和多轮单变量证据；不从当前单轮 Stress / Database Exception 推导默认切换。

## 验证快照（持续补充）

- 相关确定性回归：`tests/test_m27_*`、Phase 3A Pipeline/Planner/Schema Retrieval、M24 Fidelity、M25/M26 trustworthiness 共 **94 passed, 1 warning**，108.93s。warning 为既有 Starlette/httpx deprecation。
- M28 修复后：M27/Review/数据库聚焦测试 **28 passed**；legacy API/Trace **22 passed**；M18 smoke **4 passed**；new pipeline **8 passed**；全仓确定性 pytest **223 passed, 1 warning in 464.31s**。warning 仍为既有 Starlette/httpx deprecation；全程未调用真实 provider。
- 修复前全仓 pytest 证据（F8，已解决）：运行至约 65% 时发现旧测试未隔离默认新 pipeline，trace 证实发生真实 Qwen transport 尝试并被系统以 `network_permission_denied` 阻止；没有 completed 真实 LLM Eval、没有新 Eval artifact。
- 修复前静态环境检查（F1，已解决）：M27 `SQLiteRunEnvironment` 构造后没有注入 `app.state.schema_vector_index`。
- 修复前 catalog 静态扫描（F3，已解决）：5 个 Schema Context Scenario 把非物理派生名放入 `required_columns`；其中 4 个已在 Stress 观察为 failed，1 个 Core 被 timeout 遮住。
- `git diff --check` 当前通过；工作树另有用户/其他工具修改的 `docs/ref-discussion/RAG 的讨论.md`，本轮不触碰。
