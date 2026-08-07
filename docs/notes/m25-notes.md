# M25 Eval Trustworthiness, Reliability & Evidence-Grounded Attribution Notes

## Implementation checklist（2026-08-07）

- [x] 读取 `AGENTS.md`、`docs/state/AI_CONTEXT.md` 及其要求的 M25 相关事实源。
- [x] 核对 M24 入口门禁：M24 已于 2026-08-07 验收，无入口阻塞。
- [x] 只读审计现有 case、scorer、triage、report、LLM client、trace 与 M24 六次有效 run。
- [x] 用户确认正式 case contract、样本分组字段、归因 module seam、timeout/retry 配置与 P2 范围。
- [x] 实施 P0：case contract、样本独立性/分母、两轴归因、LLM attempt/transport 证据。
- [x] 实施 P1：可靠性实验入口、新合同基线结构、退款率与递归类目 focused spike。
- [x] 按用户决策门执行或跳过 P2：Judge/retrieval 未触发；完成最小 counterfactual probe。
- [x] 运行 focused tests、全仓 pytest 与 `git diff --check`；未运行完整 formal/challenge/diagnostic。
- [x] 执行 `finish-module`：四遍注释扫描、验证快照与收尾素材固化。
- [x] 执行 `finish-docs`：更新 AI_CONTEXT / CHANGELOG / eval-baselines / dev-log。

## 开工前只读审计（2026-08-07）

### 当前基线与入口

- `docs/state/AI_CONTEXT.md` 已登记 M24 为“已验收（2026-08-07）”，M25 的 P0-0 入口门禁通过。
- 当前默认保持 Qwen `qwen3.7-plus` + `inmemory/deterministic + weighted`；M25 不自动修改模型、检索、embedding、fusion 或 SQLite oracle。
- 工作树开工时已有用户修改 `docs/dev-log.md`；M25 实现和收工必须保留这部分内容，不回滚、不覆盖，只在 finish-docs 阶段谨慎追加 M25 复盘。

### Case 与独立样本证据

- 当前 32 条 diagnostic（16 challenge + 16 extra）按完全相同的 question 文本统计为 **26 个唯一问题、6 个重复/linked 问题组**：
  - `db_core_001 ↔ db_trace_001`
  - `db_multi_001 ↔ db_trace_002`
  - `db_multi_003 ↔ db_plan_001`
  - `db_multi_004 ↔ db_prompt_001`
  - `db_hard_003 ↔ db_prompt_002`
  - `db_join_002 ↔ db_prompt_003`
- formal 10 条与 diagnostic 32 条合并观察时，共 42 个 raw cases、26 个唯一 question 文本、13 个重复组。仅靠 question 文本自动分组不够稳定：题面修订后文本会变化，同义改写也无法识别，因此需要显式稳定 group 字段或对现有 `linked_case_id` 作明确扩展。
- 已确认的题面/expected contract 缺口：
  - `db_simple_001` / `p3a_simple_001`：题面写“前 10 条”，未声明 expected SQL 的 `product_name ASC`。
  - `db_simple_002`：题面未声明精确三列、`paid_at ASC` 和 `LIMIT 10`。
  - `db_simple_003` / `p3a_simple_002`：“基本信息”无法唯一推出三列。
  - `db_multi_002` / `p3a_multi_003`：expected SQL 固定 2026 年 6 月，题面未声明时间范围。
- `coupon_order_count` 是当前权威 canonical metric；`coupon_usage_count` 可能被理解为桥接记录数，不能仅为追分加入 alias 白名单。
- `avg_selling_price` 当前事实源明确为 `AVG(product_price_history.price)`，但题面“平均售价”仍可能被业务读者理解为时间加权平均或成交均价；从 manual 升为自动题前需要用户确认业务定义。
- `refund_rate` 当前事实源为成交订单内 `refund_count / order_count`，但 `refund_count=COUNT(refunds.id)` 未定义是否包含 `requested/approved/rejected`。seed 四种状态轮换，若 M25 focused spike 要宣称业务能力，必须先确认退款状态口径，不能沿用歧义后只优化生成。

### Timeout 与调用证据

- 六次 M24 有效 diagnostic 共 192 个 case-run，发现 14 次固定约 45 秒 read timeout：
  - `db_join_003`：QueryPlan timeout `6/6`；
  - `db_core_002`：QueryPlan `3` 次、SQL generation `1` 次；
  - `db_multi_002`：QueryPlan `3` 次；
  - `db_hard_001`：QueryPlan `1` 次。
- timeout step 的 metadata 为空；没有 provider/model、prompt length、configured timeout、attempt 或稳定 transport subtype。
- 代码原因已定位：主 client 默认 `timeout=45.0`；`generate_query_plan()` / `generate_sql_from_plan_step()` 的真实网络调用发生在解析异常的 `_add_error_context()` 保护范围之外，所以 transport error 没补齐 prompt/stage 上下文。
- 当前主模型路径没有 retry；Judge 路径已有独立三次 retry，但该实现不能直接照搬，因为 Judge 的失败可降级为 skipped，而主 pipeline 的成本、总延迟和 end-to-end 语义不同。

### 现有评测/架构 seam

- `eval.run_eval.EvalResult` 保存响应与全部 `score_details`；`summarize_score_details()` 为兼容历史只把第一条失败作为 summary。
- `eval.triage` 已是 failure stage 单一事实源，但当前 `FailureTriage` 只有 stage/subtype/action，没有 root cause、伴随原因、semantic observation status 或 report views。
- `write_report()` 仍直接承担大量聚合/Markdown 逻辑；M22 automated/manual 视图只按 manual 属性拆分，尚未表达 independent groups、eligible/observed/unavailable。
- `linked_case_id` 已存在但只覆盖少量诊断题，不足以表达跨文件的稳定语义分组。
- 主 LLM `LLMClient.complete() -> str` seam 被大量 fake client 使用；若直接把返回值改为复杂对象，测试和调用方迁移面较大。更稳妥的长期方案需要把 attempt/retry/transport 分类集中到单一深 module，同时避免 stateful `last_call_metadata` 的并发隐患。

## 待用户确认的长期决策

### D1：正式 case contract 与业务口径

- 题面缺口：建议同步修订 formal/challenge 的重复题，显式声明列、时间、排序和 LIMIT；形成 M25 新合同，不回写 M24 分数。
- `avg_selling_price`：候选为价格记录算术平均（保持当前 reference）、时间加权平均、成交均价。当前建议保持并写清“价格历史记录算术平均”，再决定是否升级自动题。
- `refund_rate`：候选为全部退款记录、已完成退款、退款申请/退款订单口径。需要用户确认后才能固定 metric/reference/focused spike。

### D2：样本分组结构

- 方案 A：继续扩展一对一 `linked_case_id`。改动小，但多 case 同组、跨文件 canonical 关系和未来改题面时表达笨重。
- 方案 B：新增稳定 `semantic_group_id`，保留 `linked_case_id` 表达“该诊断 case 具体链接哪条能力 case”。字段职责清楚，支持一组多 case；需要同步 YAML/loader/report/tests。
- 当前建议：方案 B。

### D3：归因与报告的 module seam

- 方案 A：继续把 root cause / views 逻辑写进 `run_eval.write_report()`。改动最少，但会让 runner/report 更浅、更难独立测试。
- 方案 B：深化现有 `eval.triage`，新增一个小 interface 产出 run-level analysis，集中 stage、root cause、完整失败链、groups 和 report views；`write_report()` 只渲染，旧 triage interface 保持兼容。
- 方案 C：新增平行 analysis 层再调用 triage。命名清晰，但若只是转发容易形成浅 module 和两套事实源。
- 当前建议：方案 B。

### D4：LLM attempt / retry module

- 方案 A：只给异常补 metadata，并在 client 上保存 `last_call_metadata`。改动小，但成功路径证据不足，且 stateful client 在并发/复用时有串线风险，属于后续需要替换的临时设计。
- 方案 B：新增深 `LLMCallExecutor`（名称可在实现时收敛），interface 接收 client、stage、prompt、system prompt 和显式 policy，返回 content + 完整 attempt evidence；generator 继续负责业务 JSON 解析。真实 HTTP client 与 fake client 都从同一 seam 调用，不改变安全/SQL 逻辑。
- 当前建议：方案 B；不采用“先上 last_call_metadata、以后再换”的临时方案。

### D5：timeout / retry 默认策略

- timeout 可配置是 P0 证据入口；默认仍保持 45 秒，先通过 focused 受控实验比较候选值。
- retry 建议默认 `0`，只通过显式实验 policy 开启；仅对 timeout/连接类瞬时错误有限重试，4xx、parse、合同与语义错误不重试。
- 是否改变长期默认必须依赖后续 focused reliability 结果并再次形成决策，不用本次预设替代证据。

### D6：P2 范围

- 当前建议 M25 核心先不实现 Judge shadow、retrieval 复测或 multi-seed 平台；只有 P0/P1 证据触发对应门槛时再执行。
- 若未触发，在 notes/changelog 明确登记为“按条件跳过”，不算未完成。

## 用户决策记录（2026-08-07）

用户确认“按推荐方案执行”，具体含义：

1. formal/challenge 重复题同步修订为显式列、时间、排序、LIMIT；M25 建立新合同，M24 历史分数不回写。
2. `avg_selling_price` 保持价格历史记录算术平均，但题面写清业务含义后再考虑自动化。
3. `refund_rate` 采用“成交订单中 completed 退款的去重订单数 / 包含该商品的去重成交订单数”，明细优先、整单退款回退 `refunds.product_id`；同步 metric/schema/reference/审计。
4. 新增稳定 `semantic_group_id`，保留 `linked_case_id` 表达诊断 case 的具体链接。
5. 深化 `eval.triage` 作为 run analysis seam；报告只渲染，不新增平行浅 analysis 层。
6. 新增深 LLM 调用 module，集中 timeout/retry/transport 分类/attempt evidence；不采用 stateful `last_call_metadata` 临时方案。
7. timeout 先可配置且默认保持 45 秒；retry 默认 0，只在 focused 实验显式开启瞬时错误有限重试，是否切长期默认以后续证据另决策。
8. P2 Judge/retrieval/multi-seed 默认不主动实现，只有 P0/P1 证据触发才进入；未触发则明确登记条件性跳过。

## 模块名称与改动文件清单

模块：M25 Eval Trustworthiness, Reliability & Evidence-Grounded Attribution。

- 配置与运行入口：`.env.example`、`app/core/config.py`、`docs/state/runbook.md`。
- LLM 可靠性：`engine/nl2sql/llm_call.py`、`engine/nl2sql/generator.py`、`engine/nl2sql/pipeline.py`。
- Eval 结构：`eval/run_eval.py`、`eval/triage.py`、`eval/cases/m25-reliability-suite.yaml`。
- Case 合同：`eval/cases/database-upgrade-challenge.yaml`、`phase3a-regression.yaml`、`phase3a-diagnostic-benchmark.yaml`、`docs/notes/m25-case-contract-audit.md`。
- 业务事实与 seed：`domain_pack/metrics.yaml`、`domain_pack/schema_desc/refunds.md`、`docs/state/database-current-state.md`、`scripts/seed_data.py`。
- 聚焦门禁：`tests/test_m25_eval_trustworthiness.py`。

## 实施结果与关键证据

### P0

- 冻结 `case_contract_version=m25-v1`；42 raw cases 映射为 26 个独立语义组，其中 challenge + diagnostic 为 32 raw / 26 groups。
- 题面补齐列、月份、排序、LIMIT、递归子类目和 tie-break；`avg_selling_price` 明确为有效价格历史记录的算术平均，但仍保持 manual。
- `refund_rate` 固定为 completed 退款去重订单数 / 成交去重订单数；商品归因继续明细优先、整单回退 `refunds.product_id`。
- `FailureTriage` 保留 execution stage，同时新增 root cause、evidence level/chain、semantic status、error subtype 和 observability completeness。
- 报告新增六个证据视图及 raw/group/eligible/observed/unavailable 分母，综合 automated capability 不再被解释成 SQL 正确率。
- 新 `llm_call` 深 module 显式返回正文 + request-local evidence；成功/失败共用 provider/model/stage/timeout/attempt/latency/prompt length/outcome 结构，不使用并发不安全的 `last_call_metadata`。

### P1 真实小样本（只跑 4 条 reliability suite）

固定条件：Qwen `qwen3.7-plus`、`inmemory/deterministic + weighted`、LangFuse off、SQLite deterministic oracle、相同 4 条输入；只改 `LLM_MAX_RETRIES`。

| candidate | logical calls | physical attempts | first/final success | timeout | 总耗时 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| 45s / retry 0 | 4 | 4 | 1/4 → 1/4 | 3 | 179.7s | 3 个 external timeout；1 个有效响应后在 plan validation 失败 |
| 45s / retry 1 | 4 | 8 | 0/4 → 0/4 | 8 attempts | 377.9s | 无恢复，调用翻倍、耗时约翻倍 |

- retry=1 本轮没有恢复任何请求，不能支持切为长期默认；默认继续 45 秒 / 0 retry。由于每个候选只有一次 4-case run，关于更广泛 provider 稳定性的结论仍标记为小样本，不外推成总体 SLA。
- 默认候选的 `db_multi_002` 在 31.68s 得到有效 QueryPlan，但模型引用不存在的 `root_category.level/name`，因此是 `plan_validation + model_capability`；同 trace 的 SchemaGraph 已包含 category tree、products/order_items/orders 和 `item_gmv`，没有触发 retrieval 问题。
- `db_core_002`、`db_hard_001`、`db_join_003` 本轮都只有 QueryPlan timeout，因此语义结论是 `not_observed`，不能算退款率/递归能力错误。
- 退款率反例覆盖：多退款记录、非 completed 状态、错误记录数分子，以及 INNER JOIN 丢失整单退款 fallback。
- 递归类目反例覆盖：漏子类目得到 20 而 reference 为 70；错误使用订单头 GMV 因明细 join 重复得到 200。正确 recursive CTE 当前 fidelity 仍保守返回 `indeterminate`，未扩大 AST scope。

### P2 条件门

- Judge shadow：未触发；当前没有本模块新建立的人工 gold/rubric，不让 Judge 改正式 pass/fail。
- Retrieval/embedding：未触发；唯一有效递归样本的所需 SchemaGraph 事实完整，问题发生在计划引用，不重跑 embedding A/B。
- Counterfactual：由退款率与递归类目高风险 grain 触发并完成最小内存 SQLite probe；没有建设 multi-seed 平台。

## 关键决策与取舍

- 选项、风险、推荐与用户选择完整记录在前文 D1-D6 和“用户决策记录”。实现严格采用推荐方案。
- 归因深化现有 `eval.triage`，避免 runner/analysis 两套事实源；代价是该 module 变大，因此对外收敛到 `triage_result()` / `analyze_eval_run()` 两个主要 interface。
- LLM evidence 采用显式返回值与 sink，避免 stateful client metadata 在并发请求间串线；保留 `complete()->str` fake-client seam，控制迁移范围。
- retry 只覆盖明确 transient 且幂等的调用；Arrearage、WinError 10013、非瞬时 4xx、parse、合同和语义失败不重试。
- 没有根据小样本把 timeout 改成新魔法数字，也没有切模型、Milvus、embedding、fusion 或 oracle。

## 阶段 1 注释小结（finish-module）

- 第 1 遍覆盖：对 6 个业务代码文件做 AST 清单扫描，共 112 个类/函数；5 个无独立 docstring 项均为纯 `__init__`、Protocol 方法或局部 callback，按技能规则豁免，0 个非豁免缺失。新测试函数名称自描述，关键反例另有 docstring/模块说明。
- 第 2 遍质量：深化了 attempt evidence、request-local result、execution stage vs root cause、semantic observed/unavailable、semantic group denominator 五个新概念；补充了为何不采用 stateful metadata、不盲目 retry、不扩大 recursive CTE AST 的理由。
- 第 3 遍可读性：检查并补足 HTTP subtype/retry 分支、LLM attempt 循环、完整失败链、证据视图聚合、退款率 seed 口径和 pipeline 成功/失败 metadata 路径。
- 第 4 遍形式：更新 `generator.py` 过时的 DeepSeek-only/M5 注释；新增注释保持中文为主并使用 ★ 标注关键边界，未为短小自解释代码堆叠分隔线。

## 阶段 2 验证快照

- focused：`39 passed, 1 warning in 78.22s`，覆盖 M25、M24 fidelity、M19 triage 和 Phase3A pipeline。
- 修订 linked source 后回归：`12 passed, 1 warning in 0.85s`。
- finish focused：`18 passed, 1 warning in 0.98s`。
- 全仓第一次完整结果：`183 passed, 3 skipped, 1 failed`；唯一失败为 `db_plan_001.question != db_multi_003.question`，定位为 source 题面修订未同步 linked case，已修复。
- 全仓最终：`184 passed, 3 skipped, 1 warning in 552.37s`。
- seed：`python -m scripts.seed_data --reset` 成功，14 表计数符合固定规模；新退款率口径下最高商品仍为 `Aurora Noise Cancelling Headphones`，GMV/宽表对账等固定事实通过。
- `git diff --check`：通过；只有 Git 的 LF→CRLF 工作区提示，无 whitespace error。
- warning：`StarletteDeprecationWarning`（FastAPI TestClient 依赖 httpx 兼容层），为既有依赖告警，不影响 M25。
- 按用户要求未运行完整 formal / challenge / diagnostic；M25 新合同的完整 baseline 数字等待用户手动执行，不能用 4 条 reliability suite 代替。

## 参考资料

- 项目内：M25 计划、M24 fidelity/output contract 代码与测试、M24 六轮 trace/report、state runbook/eval baseline/database facts、现有 M19 triage/M22 report views。
- 方法：使用 `codebase-design` 的 deep module/seam 原则，深化 `eval.triage` 并新增 `llm_call` 深 module；没有照搬 Judge 的三次 retry，因为主链路的失败语义与成本不同。
- 外部资料：无；本模块实现不依赖新的外部 API 文档。

## 遗留 / 后续

- 用户需手动执行 M25 `m25-v1` 的完整 formal/challenge/diagnostic 重复 baseline；报告现已能诚实区分 external unavailable、observed semantic 和 end-to-end。
- retry=1 小样本为明确负结果，默认保持 0；若未来评估 60 秒等 timeout 候选，应继续固定唯一变量并至少重复，不直接改 `.env`。

### 2026-08-07 当前默认 reliability 复测

- 固定 Qwen `qwen3.7-plus`、45s timeout、retry=0、本地 deterministic/weighted、LangFuse off，运行 4 条 M25 reliability suite；4/4 未通过，耗时约 253.5s。
- 失败并非全部发生在 QueryPlan：`db_multi_002`、`db_join_003` 为 QueryPlan timeout；`db_core_002` 已进入 SQL generation 后 timeout；`db_hard_001` 无 timeout，但模型输出缺少 `order_items` / `orders`，归为 model capability / output contract。
- 本轮 triage：`external_service=3`、`model_capability=1`，前三条 semantic `not_observed`。该结果进一步说明不能把 reliability suite 简化为 QueryPlan 能力分数；仍不足以外推 provider SLA。

### 2026-08-07 diagnostic baseline 尝试

- 按当前默认配置启动完整 `challenge + phase3a-diagnostic-benchmark` diagnostic；外层 1200 秒上限到达后安全终止，未生成正式 report/triage。
- 已留下 29 条 partial trace；其中可见部分请求在 21–50 秒完成，也有约 45 秒超时，说明诊断运行时间主要被外部 LLM 等待占用。
- partial trace 不作为 diagnostic baseline，不用于正式分母或能力结论；后续需拆分 case 集或采用可续跑方式完成正式诊断。

### 2026-08-07 DeepSeek diagnostic 对照

- 临时切换 `LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-v4-flash`，其余保持 45s/retry0、inmemory deterministic/weighted、LangFuse off，完整运行 32 条 M25-v1 diagnostic。
- 结果 `25/32`，总耗时约 `917.1s`（15.3 分钟），正式 report/triage 已生成。
- 失败结构：`query_plan=3`、`plan_validation=2`、`sql_guard=1`、`unknown=1`；root cause 为 `external_service=3`、`model_capability=2`、`code_issue=1`、`mixed_or_unknown=1`。该轮仍有 5 条 `not_observed`，不能把 25/32 直接解释成纯模型能力分数。
- 与 Qwen partial run 的比较只能作为运行可靠性线索：DeepSeek 本轮完整结束且耗时低于外层 1200s；Qwen 本轮没有正式 report，不能做严格分数对比，也不据此切换默认模型。

### 2026-08-07 Qwen qwen3.7-max diagnostic 对照

- 临时切换 `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-max`，其余保持 45s/retry0、inmemory deterministic/weighted、LangFuse off，完整运行 32 条 M25-v1 diagnostic。
- 结果 `27/32`，总耗时约 `1152.4s`（19.2 分钟），正式 report/triage 已生成。
- 失败结构：`query_plan=2`、`output_contract=2`、`unknown=1`、`plan_validation=1`；root cause 为 `external_service=2`、`model_capability=3`、`mixed_or_unknown=1`。语义状态 `not_observed=3`。
- 与 DeepSeek `25/32`（917.1s）相比，本轮 qwen3.7-max 得分更高但耗时更长，且失败结构不同；两次都是单轮不同模型运行，不能把分数差直接解释为稳定模型优劣，也不据此切默认。

### 2026-08-07 Qwen qwen3.7-plus diagnostic 复测

- 临时切换 `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`，其余保持 45s/retry0、inmemory deterministic/weighted、LangFuse off，完整运行 32 条 M25-v1 diagnostic；外层等待上限提高到 30 分钟以避免批量截断。
- 结果 `26/32`，总耗时约 `1208.6s`（20.1 分钟），正式 report/triage 已生成。
- 失败结构：`query_plan=4`、`sql_generation=1`、`output_contract=1`、`unknown=1`；root cause 为 `external_service=5`、`model_capability=1`、`mixed_or_unknown=1`。语义状态 `not_observed=5`。
- 与同日 qwen3.7-max `27/32`（1152.4s）相比，plus 本轮低 1 分且更慢、外部服务失败更多；仍只能说明本轮运行状态，不能据单轮结果决定默认模型。

### 2026-08-07 Qwen qwen3.7-plus + Milvus/Qwen embedding diagnostic

- Docker/Milvus 恢复后，临时使用 `qwen3.7-plus` + `SCHEMA_VECTOR_BACKEND=milvus` + DashScope/Qwen `qwen3.7-text-embedding`（1024 维），新建唯一 collection `datapilot_schema_docs_m25_qwen37plus_qwenemb_20260807_192300`，完整运行 32 条 M25-v1 diagnostic。
- 索引校验通过：`schema_docs_count=195`、`schema_docs_hash=8a8b6626...`、`milvus_inserted_document_count=195`、`milvus_final_row_count=195`、`milvus_dimension=1024`，确认本轮实际走 Milvus 且没有复用旧污染 collection。
- 结果 `25/32`，总耗时约 `1280.6s`（21.3 分钟）；失败 root cause 为 `external_service=6`、`model_capability=1`，失败阶段 `query_plan=4`、`sql_generation=2`、`output_contract=1`。
- 与同日 qwen3.7-plus + local deterministic 的 `26/32`、`1208.6s`相比，本轮少 1 条且更慢约 72 秒；单轮受 LLM 波动影响，不能据此判定 embedding 退化或切换默认检索。

### 2026-08-07 Round 2 四组 diagnostic

- 为降低单次 LLM 波动影响，按相同 32 条 M25-v1、45s/retry0、weighted、SQLite oracle、LangFuse off 顺序完成四组：`qwen3.7-max + Milvus/Qwen embedding`、`qwen3.7-plus + Milvus/Qwen embedding`、`qwen3.7-plus + local deterministic`、`qwen3.8-max + local deterministic`。
- 结果分别为 `26/32`（1263.2s）、`21/32`（1242.3s）、`28/32`（1222.7s）、`18/32`（1273.6s）。Milvus 两组复用已校验 clean collection `...192300`（195 docs、1024 维、hash 一致）。
- triage root causes 分别为：max+Milvus `model_capability=4, external_service=1, code_issue=1, mixed=1`；plus+Milvus `model_capability=6, external_service=5, mixed=1`；plus+local `external_service=3, model_capability=1, mixed=1`；3.8-max+local `external_service=11, model_capability=3`。
- 同一 qwen3.7-plus 的 Milvus/local 差距为 `21→28`，但两次外部失败结构也不同，仍不能单轮归因于 embedding；qwen3.8-max 本轮出现大量外部服务失败，不能直接解释为模型能力低。
- recursive CTE fidelity 仍是 `indeterminate`；是否扩展 derived scope 是后续独立设计决策，本模块不临时放宽。
- `contributing_causes` 结构已预留，当前只有证据支持唯一主因时保持空；未来出现真实 mixed trace 再增加保守映射。
- 完整 baseline 若暴露稳定 SchemaGraph 缺失，才重新打开 retrieval/embedding 门；否则不因最终 SQL 漏表反推检索失败。
