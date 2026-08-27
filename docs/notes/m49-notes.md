# M49 Notes — Phase 4B 验收阻塞项优化

## Implementation checklist

- [x] 重读 `AGENTS.md`、`docs/state/AI_CONTEXT.md` 及其必读规则指向的状态事实源。
- [x] 从 `docs/notes/m48-review.md`、Phase 4B roadmap、M42～M48 plan/notes 中提取 M49 的明确修复范围与完成门。
- [x] 复现并定位自然语言 T2 被错误合并为双重比较需求的根因，补齐最小失败测试。
- [x] 修复 TaskState / turn understanding / requirement merge 的语义，同时保持旧合同兼容、版本并发和失败关闭行为。
- [x] 审计并修正 Scenario v6 / assurance 的证据独立性，避免伪造输入获得“completed”。
- [x] 对齐 Phase 4B roadmap、M46 特批收口、M48 验收状态和安全失败原因等合同/文档冲突；涉及完成门或默认行为时先向用户提交方案。
- [x] 修复默认开发库迁移前置检查或演示入口，确保缺少 M48 migration 时明确失败，不静默形成断点；若需要改变默认库或自动迁移策略，先请求确认。
- [x] 更新 README / 状态文档的公开能力表述，正面展示已证实的工程能力，不把 deterministic 证据夸大成效果或生产结论。
- [x] 运行聚焦测试、相关 Phase 4B 回归和静态文档检查；失败后先定位、修复相关层，再扩展验证。
- [x] 按 plan 预注册并申请 Live Dev Probe：真实连续纵向 happy path、安全失败路径、重启续接与 compact 边界；未经授权不执行真实模型/Eval。
- [x] Probe 后立即记录时间、HEAD/dirty、命令、依赖、Response/Trace/usage、结果三态和 continue/revise/stop。
- [x] 完整回读变更与 notes，确认没有扩大到 held-out、sealed reserve、生产数据、默认切换或大规模 Eval。

## 开工记录

- 2026-08-27：M49 开工。范围来源暂定为 M48 审计中的最终验收阻塞项；在重读路线与历史合同前不自行改写完成门、默认行为或安全边界。
- Live Dev Probe 尚未执行、尚未获得本模块授权；先完成预注册和离线/测试验证。

## 调查与决策记录

- 2026-08-27：重读 `AGENTS.md`、`AI_CONTEXT.md`、runbook 及 Text2SQL/RAG/Eval/数据库/Milvus 专项事实源，并复核 Phase 4B roadmap、M43/M46/M48 plan/notes 与 M48 review。M49 需要独立 plan；不能直接把 M48 的技术收工结论当作真实最终联调证据。
- 确定性根因：`understand_turn()` 对 continue 的 `modify_constraint` 分类依赖“改成/调整”等窄词；完整显式比较重述仍是 `continue`。`apply_delta()` 对 continue 采用 requirement additive merge，因此稳定保留旧单月 requirement 与新双月 comparison requirement。该问题无需 provider 即可复现。
- 证据门根因：`scripts/rehearse_m48_b6.py` 为所有 case 固定写入 passed，且 budget trigger/fallback observation 可由常量构造；`eval/phase4b_assurance.py` 把 B0～B5 contract identity 同时当 evidence identity。当前 validator 能证明 artifact 形状/签名，不能证明 execution 发生。
- 合同冲突：roadmap 的 reserve A/B 最终门与 M46 经确认的 experimental-only/no-go 收口并存；默认 `datapilot_dev` migration 0003 与 task runtime 0005 前置也仍冲突。两项都不能由 M49 自行选择。
- 已建立 `docs/notes/m49-plan.md`，登记 G49-1～G49-5 与 M49-P1/P2。确认前不修改核心合同、默认数据库、安全投影或阶段完成门，不运行真实 provider。
- 2026-08-27 用户确认 G49-1～G49-5 全部采用方案 A：完整显式重述按 typed completeness 替换；新增 v7/assurance v2；roadmap 正式吸收 M46 experimental-only 例外；最终验证阶段正常迁移 `datapilot_dev` 到 0005 且不 reset/reseed；公开 `task_unavailable`、内部 `caller_untrusted` 分层保持。方案 C（LLM Turn Understanding）只进入防遗忘能力账本，本模块不实施。
- 2026-08-27 M49-A red tests：`tests/test_m43_task_runtime.py + tests/test_m48_v6_assurance.py` 得到 `2 failed, 8 passed`。失败精确命中两项审计根因：完整显式 T2 实际仍为 `continue`；缺失 budget-trigger/fallback observation 的伪 probe 仍可生成 completed v6。命令使用 `.agent_work/temp/m49/red-tests-r1`，未调用 provider、未访问数据库。决定：`revise`，进入生产修复；不通过删除断言或补假 observation 规避。
- 2026-08-27 M49-B/C 首轮实现：Turn Understanding 新增 typed completeness 规则，只在 continue 自身显式给出 metric+period 且不存在政策/原因/商品/渠道追加意图时替换主 requirement；“再查证/补充证据”仍 additive。证据层保留 v6 只读，新增 Scenario v7 与 assurance v2：三态由 required assertion 推导，passed 必须绑定 evidence locator/identity，缺失场景自动 not_observed，contract identity 禁止冒充 execution identity。
- 聚焦修复首次运行因测试误用不存在的 `EvidenceRequirement.requirement_type` 属性得到 `1 failed, 12 passed`；实现行为已正确，测试改为既有 `purpose` 字段后重跑 `13 passed`。这不是产品失败。临时目录：`.agent_work/temp/m49/focused-r1`、`focused-r2`，provider/数据库均为 0。
- 流程偏差：M49-C 的 schema/validator 草案在 P1 前已落盘并通过纯测试，早于 plan 写的“P1 continue 后进入 C”；尚未生成/冻结任何 v7/assurance v2 正式 artifact，也未用草案宣称通过。P1 仍作为正式证据投影和后续全链接线的硬门，不倒填 Probe。
- 2026-08-27 跨模块聚焦回归：前两次和一次沙箱内重跑均被 Windows `basetemp` 父目录消失/权限拒绝阻断，最多只执行到 `21 passed + 10 setup errors`，没有业务失败结论。显式建立 `.agent_work/temp/m49` 后在沙箱外用新目录 `phase4b-focused-r4-approved` 重跑同一集合，结果 `31 passed, 1 existing warning`；覆盖 M43 runtime/API、M44 Loop/API、M48 Context/v6 与 M49 v7/assurance。warning 为既有 Starlette/httpx deprecation。决定：deterministic Gate=`continue`，进入 M49-P1 授权门。
- 2026-08-27 15:42～15:44 M49-P1 attempt 1：`failed → revise`。用户已精确授权；真实 Qwen + Text2SQL + SQL Guard + MySQL `datapilot_m48_test`，retry=0。T1=`complete/answer_ready`，120000；T2 的 M49 修复已生效：category=`modify_constraint`，active requirement 只有 `sql:net_refund_amount:2026-07,2026-08`。首次 SQL 使用 MySQL 不支持的 `DATE_TRUNC`，既有 deterministic AST repair 随后零新增 provider 成功返回 120000/180000/60000/0.5；但 Controller 最终为 `partial/comparison_observation_missing`。usage=`4 calls / 15,310 tokens`，未越 `4 / 20,000` 上限；运行前/清理后 task rows=`0/0`，证据 `.agent_work/temp/m49/probe-p1/result-safe.json`。
- P1 首错根因：`_complete_comparison_if_required()` 要求同一 requirement 在 observations 中精确只有一条；bounded repair 合法保留“首次 dialect failure + repair success”两条同 requirement Observation，因此在进入 `complete_metric_comparison()` 前就被误判 missing。修复方向不扩大范围：比较完成只消费唯一的 successful、safety-passed Observation；零条继续 missing，多条成功仍失败关闭。需要补“comparison + dialect repair”回归后，按 runbook 仅申请/执行受影响 P1 最小重验。
- P1 attempt 1 修复：Controller 保留全部失败/成功 Observation 账本，但 comparison completion 只选同 requirement 唯一 `execution_status=completed + safety_status=passed` 的 Observation；不存在或多条成功仍以稳定 reason 失败关闭。新增 `RepairingComparisonSQLTool` 回归，冻结“dialect failure + repair success + comparison completion”连续行为。
- 修复聚焦：沙箱内先完成 15 项业务单测后再次被 Windows basetemp cleanup 权限阻断 API 组，无产品失败结论；沙箱外新目录重跑结果 `23 passed, 1 existing warning`。决定：代码 Gate=`continue`，等待用户对同一 P1 场景的 attempt 2 精确重验授权；不沿用 attempt 1 结果冒充通过。
- 2026-08-27 15:46～15:48 M49-P1 attempt 2：真实运行的 T1/T2 均 `complete/answer_ready`；T2=`modify_constraint`、唯一 comparison requirement，首次 `DATE_TRUNC` failure 后 deterministic repair 成功，实际 rows 为 `month + net_refund_amount + delta/rate`，数值 120000/180000/60000/0.5。usage=`4 calls / 13,075 tokens`，清理后=`0/0`。runner 末端错误地要求 M48 fake oracle 的 `period/value` 列形状，故原 `result-safe.json` 标 `revise/sql_oracle`；这是 Probe assertion 缺陷，不是产品失败。
- Probe assertion 修复：新增 projection-neutral 语义核对，同时接受真实 `month/net_refund_amount` 与 frozen oracle `period/value`，但严格核对月份、数值、差额和变化率；测试 `11 passed, 1 existing warning`。随后对 attempt 2 原始 safe artifact 做同源离线复核，新增 provider=0、DB writes=0，`verification-safe.json`=`continue`，source SHA-256=`e53ecf6b...de07`。M49-P1 最终决定=`continue`，放行后续正式 v7 evidence 投影与 M49-D；原 revise artifact 保留，不覆盖历史。
- 2026-08-27 G49-4 默认演示库升级：用户已通过“全部 A”精确授权 `datapilot_dev` 正常 migration 且禁止 reset/reseed。升级前 `alembic current=20260722_0003`，关键计数 users/orders/refunds/knowledge_docs=`200/10000/1000/11`。执行 `python -m alembic upgrade head`，只运行 0003→0004→0005 schema migration；升级后 `current=20260827_0005 (head)`、`alembic check=No new upgrade operations`，同四张业务表计数完全不变，新 task checkpoint/event=`0/0`。结论：默认 task backend 的 schema 前置已闭合，没有改写业务数据。
- 2026-08-27 M49-D 合同对齐：按用户确认修订 Phase 4B roadmap，把 B4 experimental 工程完成与未来默认晋级分开；当前 Pipeline default/Subgraph server-controlled experimental/no-auto-fallback/historical no-go/reserve sealed-not-run 可用于展示型阶段收口，未来新 candidate 切默认仍需新 sealed decision evidence。runbook 已明确内部 `caller_untrusted` / 对外 `task_unavailable` 分层；database state 与 AI_CONTEXT 已同步默认库 0005 和 M49-P1 事实；M48 人工清单已区分当前 SQL turn/guarded rows 与 durable Context/Compact 禁区。
- M49-P2 runner 已固化为 `scripts/probe_m49_phase4b_continuity.py` 并通过 compileall/diff check：真实 Qwen + Text2SQL + SQL Guard + `datapilot_m48_test` + business Subgraph，worker A T1→T5、worker B restart/T6 Compact、production-like 无 resolver 安全路径；上限 14 calls/60000 tokens/retry0，首错停止，finally 清理 0/0。v7 的 budget-trigger/fallback 另绑定实际 deterministic test log/hash，不从 P2 常量伪造。尚未执行，等待精确授权。

## M49-P2 后台启动前 checkpoint

- 2026-08-27：用户已精确授权 M49-P2，并要求长任务按 AGENTS.md 后台执行。当前关键改动：完整显式重述替换主 requirement；comparison completion 可消费 failure history 后唯一 repair success；Scenario v7/assurance v2 独立证据门；roadmap B4 experimental-only 修订；`datapilot_dev` 0005；安全 reason 分层文档。
- 已完成验证：M49 red tests 精确命中旧缺口；聚焦 `31 passed`；P1 修复组 `23 passed`；Probe projection 组 `11 passed`；M49-P1 attempt 2 同源离线复核=`continue`，真实 usage=4 calls/13075 tokens、cleanup=0/0。
- 已知风险：T3～T6 的开放 QueryPlan、T4/T5 business Subgraph 与真实 continuous Compact 尚未在同一次真实 Qwen sequence 观察；P2 可能在任一 turn 首错停止。P2 不验证泛化率、RAG 质量胜出或生产能力。
- 待完成：后台 P2；结果三态检查；若 continue，再运行 budget-trigger/fallback deterministic evidence log、生成 v7/assurance v2、更新 README/state/history，并执行分组/全仓回归。完成标记检查前不得宣称 P2 或 M49 通过。
- M49-P2 已后台启动：PID=`27140`。launcher=`.agent_work/temp/m49/probe-p2-launcher.ps1`；stdout=`.agent_work/temp/m49/probe-p2-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2/result-safe.json`。当前状态：**运行中，待检查**；不得提前记录为通过。

## M49-P2 结果与计划外阻塞

- 2026-08-27 15:56～15:58：后台任务已完成，`exit-code=20`、decision=`revise`。T1 真实 SQL 链路 `complete/answer_ready`，usage=`2 calls / 5,667 tokens`；T2 的 M49 TaskDelta 修复仍正确生效：`modify_constraint` 且唯一 requirement 为 `sql:net_refund_amount:2026-07,2026-08`，但 QueryPlan 在 1 次真实 provider 调用后被碰库前校验拒绝，错误为 `step_1 的 ORDER BY 输出别名 month 缺少 output_expressions 绑定`。累计 usage=`3 calls / 11,490 tokens`，未越 `14 / 60,000` 上限；task rows 从运行前 `0/0` 到清理后 `0/0`。safe artifact=`.agent_work/temp/m49/probe-p2/result-safe.json`，worker A trace SHA-256=`3a9a5a26...c9303e`。
- 首个失败层的准确边界：对外 Controller 收口为 `comparison_observation_missing/no_answer`；底层 Text2SQL Observation 是 `plan_validation_failed`。没有进入 SQL generation、SQL Guard 或数据库执行，所以这次不能归因为 SQL 方言、数据错误或 Guard；也没有执行 T3～T6、重启/Compact 和 production-like 无 resolver 安全路径，不能把未执行项写成通过。首错停止纪律正常生效。
- 根因定位：`engine/nl2sql/prompt.py` 已有“ORDER BY 使用聚合输出别名时必须写 output_expressions”的通用规则，`engine/nl2sql/planner.py` 的校验也按 M24 plan-fidelity 合同正确 fail closed；Phase 4B 历史同一比较问题此前已经出现过 `month` 别名未绑定。结论不是校验器误杀，而是模型多次忽略抽象规则。弱化校验或从候选 SQL 反推绑定会破坏“计划先约束、候选 SQL 不能自证”的安全边界。
- 该问题涉及默认 QueryPlan prompt / 调用预算 / fidelity 安全合同，按用户约束先提交方案，确认前不实现、不追加 P2：
  - **方案 A（建议）**：在现有 QueryPlan prompt 中增加一个很短的正反例，明确“`month` 这类派生时间别名只要出现在输出或排序中，就必须在 `output_expressions` 绑定”；保留 validator、调用次数与预算不变。优点是改动最小、适合展示型收口；代价是 prompt 略增，且模型行为仍是概率性的，不能承诺永不再犯。
  - **方案 B**：遇到 `plan_validation_failed` 时，把精确错误反馈给模型，允许一次有界 QueryPlan 修复。成功率通常更高，但会改变默认 provider 调用次数、延迟、token 预算和 retry 语义，范围明显大于当前缺口。
  - **方案 C（不建议）**：代码自动补齐缺失的别名绑定。看似稳定，但 `month` 可能对应多种粒度/字段/函数，自动猜测会制造错误语义，也会削弱 M24 fidelity 安全合同。
  - **方案 D（不建议）**：保留现状，把 P2 记为 inconclusive。安全上仍是失败关闭，但连续可演示链路没有拿到证据，不能满足 M49 的主要收口目标。
- 建议选择 A：先用正反例强化模型的结构化计划输出，同时保持碰库前 fail closed；完成聚焦测试后，再单独申请一次同规格 P2 全序列重验。因为本次在 T2 首错停止，不能把后续 T3～T6 从另一段运行拼接成“同一条连续链”。
- 2026-08-27：用户确认方案 A，并精确授权一次同规格 M49-P2 全序列重验。实现只强化 QueryPlan prompt：把原“聚合输出别名”规则扩成所有非物理派生别名，并加入 `month + net_refund_amount` 的正例与漏绑 `month` 的反例；不修改 validator、不增加默认 retry/provider calls、不放宽 M24 fidelity 合同。先过离线聚焦门，才可消费本次真实重验授权。
- 2026-08-27 16:03：方案 A 离线聚焦门通过：`tests/test_phase3a_planner.py + tests/test_m49_probe_contract.py` 得到 `20 passed, 1 existing warning`，目录 `.agent_work/temp/m49/prompt-a-focused`。确认正反例进入默认 QueryPlan prompt，P2 的限额/首错停止/清理合同未改变；provider/DB 均未调用。决定=`continue`，消费用户已授权的 P2 重验。

## M49-P2 attempt 2 后台启动前 checkpoint

- 代码阶段：HEAD=`6e3cf3459088010e308a28d8361cd10b4348faba`，M49 相关 dirty 包括 `engine/nl2sql/prompt.py`、TaskDelta/Controller 修复、v7/assurance v2、Probe/测试与对应 notes/state 文档；完整 dirty 清单保留在本轮启动记录输出。
- 本次相对 attempt 1 的唯一产品修正是 QueryPlan 派生别名正反例；不改 validator、SQL Guard、数据库数据、Subgraph 策略、provider 重试或预算。仍运行 T1→T6 连续序列、worker B 重启/Compact 与 production-like 无 resolver 安全路径；上限 `14 calls / 60,000 tokens / retry=0`，首次系统性失败停止，finally 清理 synthetic task/event rows。
- 真实依赖与数据边界不变：Qwen `qwen3.7-plus`、Text2SQL、SQL Guard、MySQL `datapilot_m48_test` 既有 Phase 4B seed、business active release/Subgraph；禁止 `datapilot_dev` 业务写入、Milvus/external、held-out、sealed reserve、生产数据、迁移/reset/reseed、默认切换或 Formal Eval。
- 已知风险：正反例降低同类结构遗漏概率但不是确定性保证；任何新首错都按真实层记录为 `revise`，不在同一次授权中自行反复重跑。后台结果的 exit code、done marker、safe artifact 与必要 trace 未检查前不得宣称通过。
- M49-P2 attempt 2 已后台启动：PID=`55720`；launcher=`.agent_work/temp/m49/probe-p2-launcher.ps1`；stdout=`.agent_work/temp/m49/probe-p2-r2-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r2-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r2/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 attempt 2 结果

- 2026-08-27 16:04：后台任务 `exit-code=20`、decision=`revise`，但没有进入方案 A 所影响的 QueryPlan 输出判断。T1 第一次 Qwen 连接在约 2.05s 被本机代理端口拒绝：`network_error / WinError 10061`；因此 `external_unavailable / llm_generation_error / no_answer`，usage=`1 call / 0 observed tokens`。worker A trace SHA-256=`4e722700...4a87c7`；首错停止后 T2～T6 与安全路径均未执行；task rows 清理后=`0/0`。
- 证据边界：这是外部网络入口瞬时不可用，不能判定方案 A 有效或无效，也不能把 P2 记为通过；产品的外部失败关闭、调用记账、首错停止和 cleanup 行为符合合同。随后只读 `Test-NetConnection 127.0.0.1:7897` 已恢复为 `TcpTestSucceeded=true`，`clash-verge` / `verge-mihomo` 进程存在。
- 决定：不改代码、不改变 prompt/backend/model/retry/预算/问法。若用户追加授权，建议只做同规格 attempt 3；仍是最多 `14 calls / 60,000 tokens / retry=0`、首错停止，且本次 attempt 2 的 1 次失败调用独立留账，不合并伪装为成功运行。没有追加授权前不自行重跑。

## M49-P2 attempt 3 后台启动前 checkpoint

- 2026-08-27：用户已追加授权一次 P2 真实重验。启动前只读检查 `127.0.0.1:7897` 为 `TcpTestSucceeded=true`；HEAD 仍为 `6e3cf3459088010e308a28d8361cd10b4348faba`，attempt 2 后没有产品代码变化。
- 重验合同完全不变：Qwen `qwen3.7-plus`、同一 T1→T6 问法、MySQL `datapilot_m48_test`、business Subgraph、production-like 无 resolver 安全路径；`14 calls / 60,000 tokens / retry=0`，首错停止并 finally 清理。继续禁止 dev 业务写入、Milvus/external、held-out、sealed reserve、生产数据、迁移/reset/reseed、默认切换和 Formal Eval。
- attempt 1（QueryPlan fail）与 attempt 2（代理拒绝）原 artifact/Trace 独立保留；attempt 3 使用 `probe-p2-r3*` 新目录，不拼接跨运行结果。
- M49-P2 attempt 3 已后台启动：PID=`57056`；stdout=`.agent_work/temp/m49/probe-p2-r3-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r3-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r3/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 attempt 3 结果与执行环境纠正

- 2026-08-27 16:07：attempt 3 与 attempt 2 相同，在 T1 首次 Qwen 连接约 2.06s 后 `WinError 10061`，`1 call / 0 observed tokens`，首错停止、cleanup=`0/0`，trace SHA-256=`e55ec978...3d01e`。
- 进一步定位推翻“项目代理瞬时波动”的初判：当前沙箱进程环境把 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 强制指向 `http://127.0.0.1:9`，而启动前检查的是项目规定的 `127.0.0.1:7897`。因此 attempt 2/3 的 provider 请求被隔离环境导向拒绝端口，没有真正出站；这是 Probe launcher 执行环境错误，不是 Qwen、方案 A 或产品链路失败。
- 纠正方式只作用于 `.agent_work/temp` 下的 Probe launcher：显式设置大小写 HTTP/HTTPS/ALL proxy 为 AGENTS 规定的 `http://127.0.0.1:7897`，并在非沙箱网络权限下后台启动新目录 `probe-p2-r4*`。不改应用配置、产品代码、模型、问法、retry、预算或数据边界；attempt 2/3 继续保留为无效基础设施尝试，不删除、不拼接。
- attempt 4 尚未启动：非沙箱后台执行的权限审查认为，前一份用户授权已被 attempt 3 消费；纠正后再次向 Qwen 发送 schema/数据上下文并消耗预算需要用户明确追加授权。已停止，没有改用其他命令绕过权限门。
- 用户纠正规则：同一已授权 Probe、同场景/预算/数据边界内的基础设施纠错重试不再重复询问；只有扩大场景、预算、数据范围或改变合同才重新申请。并且禁止未经检查就立即后台运行，先前台预检，确认无问题后才可转后台。
- attempt 4 前台预检通过：launcher PowerShell parser errors=`0`；大小写 HTTP/HTTPS/ALL 六个 proxy 变量均显式绑定 `127.0.0.1:7897`；proxy TCP=`true`；通过该代理访问 DashScope 根地址返回 HTTP `404`（已到达服务端，未发送任务/schema payload）；`probe-p2-r4` 与 `probe-p2-r4-run` 启动前均不存在。决定=`continue`，可以后台启动真实 P2。
- M49-P2 attempt 4 已在预检通过后后台启动：PID=`47824`；stdout=`.agent_work/temp/m49/probe-p2-r4-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r4-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r4/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 attempt 4 结果与 T3 新阻塞

- 2026-08-27 16:10～16:15：真实出站 attempt 4 decision=`revise`。T1=`complete`（2 calls / 5,633 tokens）；T2=`complete`（2 calls / 12,248 tokens），方案 A 生效：QueryPlan 正确绑定 `month`，TaskDelta=`modify_constraint`、唯一主 comparison requirement，SQL/Guard/执行完成并返回两行。T3 首错停止，累计=`6 calls / 26,221 tokens`；T4～T6、重启/Compact 与安全负例未执行；cleanup=`0/0`。worker A trace SHA-256=`103c817f...0309`。
- T3 TaskDelta/Decision Loop 没有漏项：状态正确新增 quality driver 与 product breakdown 两个 requirements，先执行无依赖的 quality driver；底层首错是 `sql_plan_contract_indeterminate`，不是公开层显示的泛化 `comparison_observation_missing`。
- 精确根因：QueryPlan 合法绑定 `month/net_refund_amount/increment`；模型生成了语义上看似合理的派生子查询 `FROM (...) t`，外层使用无前缀 `refund_reason/month` 排序。M24 fidelity validator 按既有安全合同拒绝跨 derived scope 猜测字段来源，因此在 SQL Guard/碰库前 fail closed。现有测试也明确冻结 CTE/derived scope 无前缀字段为 `ambiguous_order_expression`，不能把它当误报直接放行。
- 这是新的默认 SQL 生成形态决策，不属于“同一 Probe 基础设施重试”；按核心合同决策纪律先给方案，确认前不改、不重跑：
  - **方案 A（建议）**：强化 SQL generation prompt：当 QueryPlan 可由单层聚合完成时，禁止为了计算派生列额外包 CTE/子查询；SELECT/GROUP BY/ORDER BY 使用计划中的物理表限定字段或显式绑定表达式。保留 fidelity validator、调用次数和预算不变。优点是改动小、继续 fail closed；缺点是仍依赖模型遵循，复杂任务未来仍可能需要 derived scope。
  - **方案 B**：扩展 fidelity validator，递归解析 derived scope 的输出 lineage，再证明外层别名与内层表达式等价。架构上更完整，但会改变 M24 安全证明边界、实现与回归范围较大，不适合本次展示型收口临时扩张。
  - **方案 C（不建议）**：确定性把模型 SQL 展平或自动改写。窗口函数、聚合粒度和别名作用域容易被改错，存在静默语义风险。
  - **方案 D**：遇到 indeterminate 再让模型修一次。可能提高成功率，但增加调用、延迟和 retry/预算合同，且没有解决 validator 能力边界。
- 建议 A；若确认，先补红/绿测试和离线聚焦门，再按用户已明确的规则做前台环境预检，正常后直接进行同规格 P2 重试，不为同边界重试重复询问。
- 2026-08-27：用户确认 T3 采用方案 A。SQL generation prompt 新增单层可完成时禁止额外 CTE/derived subquery 的规则，并加入 `refunds.refund_reason + month` 的单层正确结构及外层无前缀 derived scope 的错误结构；M24 fidelity validator、SQL Guard、默认 provider 次数、retry 和预算均不变。
- T3 方案 A 离线门：沙箱内运行前 33 项通过，后 8 项被既有 Windows basetemp 权限问题阻断，无产品断言失败；沙箱外新目录 `.agent_work/temp/m49/t3-prompt-a-focused-approved` 重跑同一集合得到 `43 passed, 1 existing warning in 91.10s`。覆盖 QueryPlan/SQL prompt、M24 fidelity 正反边界、Phase3A pipeline 与 P2 脚本合同。决定=`continue`，进入 attempt 5 前台环境预检。
- attempt 5 前台预检通过：launcher parser errors=`0`、六个 proxy 变量=`7897`、proxy TCP=`true`、DashScope HTTP=`404`、新单层 prompt 规则已加载，`probe-p2-r5*` 输出目录均不存在。没有发送任务/schema payload。决定=`continue`，允许后台运行同规格 P2。
- M49-P2 attempt 5 已在预检通过后后台启动：PID=`57304`；stdout=`.agent_work/temp/m49/probe-p2-r5-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r5-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r5/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 attempt 5 结果

- 2026-08-27 16:53～16:55：decision=`revise`。T1 complete；T2 QueryPlan success 且正确绑定 `month`，随后 SQL generation 调用被远端无响应关闭：`client_exception / Remote end closed connection without response`，该调用 observed tokens=`0`。累计=`4 calls / 10,489 observed tokens`，T3～T6/安全路径未执行，cleanup=`0/0`，trace SHA-256=`fc1ced96...e8867`。
- 判断：新 prompt 已进入并产出合法 QueryPlan；首错发生在第二次 provider 网络传输，未产生 SQL candidate，不能归因于方案 A、fidelity、SQL Guard 或数据库。按用户规则作为同规格已授权 Probe 的外部依赖中断处理，不改代码/模型/问法/retry/预算，保留 r5 证据并进入 r6 前台预检；预检正常才后台运行。
- r6 前台预检通过：launcher parser=`0`、六 proxy 变量=`7897`、proxy TCP=`true`、DashScope 连续两次 HTTP=`404/404`、r6 输出目录不存在；未发送任务/schema payload。决定=`continue`，允许后台运行。
- M49-P2 r6 已在预检通过后后台启动：PID=`34920`；stdout=`.agent_work/temp/m49/probe-p2-r6-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r6-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r6/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 r6 结果与 Controller 合同决策门

- 2026-08-27 17:16～17:20：r6 decision=`revise`。T1/T2 complete；T3 的 quality driver SQL 也 completed/safety passed，单层 SQL 返回 8 行，其中 `quality_issue` 为 2026-07=`48,000`、2026-08=`96,000`。累计=`6 calls / 25,541 tokens`，cleanup=`0/0`，trace SHA-256=`5df4a0a3...e4c6`。T3 最终 partial，T4～T6/安全路径未执行。
- 确定性根因一：dependent product requirement 使用 `depends_on=quality_increment_positive`；`_dependency_status()` 只识别同一行的 `increment/delta/change/...` 或 fake diagnostic，不会从两个月的 typed `month + refund_reason + net_refund_amount` rows 计算差额。因此虽然质量问题由 48,000 增至 96,000，依赖仍被判 false，商品拆分没有获得下一 Action。
- 确定性根因二：T2 comparison Evidence 在 T3 状态中仍 active、已经覆盖主 metric requirement，且 T3 没改变 metric/periods；但 `_complete_comparison_if_required()` 只在“本轮 observations”寻找主 comparison Observation，找不到便把 Loop 原终止覆盖为 `comparison_observation_missing`。这把跨 turn 已覆盖事实误当成本轮缺失。
- **G49-6 quality dependency 方案**：
  - **A（建议）**：Controller 从 guarded typed rows 中按显式两期与 quality reason 取值，确定性计算 `后期 - 前期 > 0`；只有恰好可识别两期且数值合法才解锁，否则仍 false/fail closed。保留 fake diagnostic 仅供测试兼容，不解析 answer 文本。优点是无需新增模型调用，语义与 `quality_increment_positive` 一致；影响是 Controller 新增一项窄域确定性派生事实。
  - B：继续靠 prompt 强制 SQL 输出 `increment`。改动小，但模型仍可能漏列，且把 Controller 可确定计算的事实交给概率输出。
  - C：无条件执行商品拆分。会浪费预算并违反 conditional requirement，不建议。
  - D：让 LLM 判断质量增量。理解更灵活，但增加成本、延迟和不确定性；本阶段不建议。
- **G49-7 cross-turn comparison 方案**：
  - **A（建议）**：若主 comparison requirement 已被 TaskState 中 active Evidence 覆盖，且本轮没有重新执行该 requirement，则 comparison completion 旁路为 `already_covered`，保留 Loop 的真实终止；本轮确实重查 comparison 时仍必须找到唯一成功 Observation 并完成数值校验。优点是符合 durable state 语义且不放宽新取证；影响是后续 turn 不重复投影旧 comparison 数值。
  - B：每个后续 SQL turn 都重新查询主 comparison。证据更新鲜但浪费调用/预算，并破坏“未改约束就复用 active Evidence”的状态设计。
  - C：从 durable EvidenceRef 反查旧 rows 后重新完成 comparison。需要扩大持久化/回读敏感结果范围，与 Context 隐私边界冲突，不建议。
- 建议 G49-6/G49-7 均选 A。确认前不改 Controller、不重跑 P2。
- 2026-08-27：用户确认 G49-6/G49-7 均采用 A。实现保持窄域：dependency 只从 requirement identity 明示的恰好两期、quality reason、guarded typed amount rows 计算后期减前期；缺期/坏值/非正增长不解锁。comparison completion 仅在“本轮无该 requirement Observation + active durable coverage 已存在”时旁路 `already_covered`；本轮重查仍执行唯一成功 Observation 与数值严格校验。
- G49-6/G49-7 聚焦回归：`tests/test_m44_agent_loop.py + test_m43_task_runtime.py + test_m49_probe_contract.py` 得到 `18 passed, 1 existing warning`，目录 `.agent_work/temp/m49/g49-6-7-focused`。覆盖真实形状两期正增量解锁、负增长/缺月失败关闭、当前 turn comparison 严格完成、跨 turn active Evidence 复用与 Probe 合同。决定=`continue`，进入 r7 前台预检。
- r7 前台预检通过：launcher parser=`0`、六 proxy 变量=`7897`、proxy TCP=`true`、DashScope=`404/404`、r7 目录不存在；未发送任务/schema payload。决定=`continue`，允许后台运行。
- M49-P2 r7 已在预检通过后后台启动：PID=`64192`；stdout=`.agent_work/temp/m49/probe-p2-r7-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r7-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r7/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 r7 结果与 T6 既有结果解释合同门

- 2026-08-27 18:01～18:13：r7 首次真实贯通 T1～T5：T1/T2 metric、T3 quality driver + product 两个 SQL actions、T4 SQL + Business Subgraph + 2 citations、T5 correction 后 channel SQL + Business Subgraph + 2 citations 均 `complete/answer_ready`。worker B 在新进程从 MySQL 恢复 task，并成功提交 Compact，`source_turn_range=[1,5]`、compact identity=`dd5a39ba...16345`。
- T6 失败：`解释这个结果` 被分类为 `ask_about_existing_result`，但 `understand_turn()` 仍根据旧 metric/periods自动生成 `sql:net_refund_amount:2026-07,2026-08`，与 T5 当前 channel + policy 结果不一致；QueryPlan 成功后 SQL generation read timeout。总 usage=`14 calls / 59,822 tokens`，未超过但已触顶 calls，T6 no_answer；安全负例因首错停止未执行；cleanup=`0/0`。trace SHA：worker A=`1dc49c8b...21a82`，worker B=`33e15528...c68f6`。
- 根本合同矛盾：TaskState/Compact 持久化 typed constraints、requirements、EvidenceRef 和安全账本，但按 M48 隐私规则不保存 SQL rows、回答正文或政策正文。因此新进程能证明“查过什么、证据是否有效”，却没有材料重放详细数值解释。当前实现既不能诚实解释旧结果，也不该偷偷退回旧 metric 重查。
- **G49-8 既有结果解释方案**：
  - **A（建议，展示型安全概览）**：`ask_about_existing_result` 不新增 requirement、不调用 Tool/provider；基于 TaskState/Compact 的 typed goal、constraints、active requirement/evidence 状态返回确定性安全概览，例如说明“当前结果是按渠道比较 7/8 月，并结合已授权退款政策证据”，同时明确详细数值/条文未持久化，如需重显需明确要求重新查询。Response 标记为完成“上下文解释”，但不声称复述具体数值。优点是保住隐私、预算、重启演示和诚实边界；缺点是解释深度有限。
  - **B（重新取证）**：把 ask-existing 转成对当前 active channel + policy requirements 的显式重查，再生成完整答案。数据更新鲜且能展示数值，但增加 SQL/Knowledge 调用；本次 14/60k 预算已不够，需要改 Probe 预算，且“解释”会变成昂贵重算。
  - **C（持久化结果摘要）**：在 TaskState/Compact 新增有界 answer/result digest，重启后直接解释。体验最好，但改变 durable schema、隐私清理、迁移与版本兼容，范围明显超出 M49 展示型收口。
- 建议 A。它不假装保存了不存在的结果，也不扩大隐私面；T6 可真实证明 restart + Compact + typed context 可用。若确认，先冻结 `ask_about_existing_result` 的 no-Tool 合同与安全概览测试，再按同规格 P2 预检重试；不改问法、不加预算。
- 2026-08-27：用户明确项目为个人 Demo，询问 C 是否最不容易出错，并在该条件下选择 C。结论分层：按实现改动风险 A 最小；按现场 Demo 运行稳定性与解释完整度，C 最稳，因为 T6 不再依赖 provider/SQL/RAG 重查且可复述具体结果。因此采用 **G49-8 C**。
- C 的正式边界：新增版本化、有界的 latest result digest，只保存最近一次已完成回答所需的有限文本/结果类型/证据引用，不持久化 prompt、Trace、任意 SQL、原始 document body 或无限 rows；设置长度/数量上限，旧 TaskState/Compact 无 digest 时兼容降级，不用临时常量冒充结果。T6 `ask_about_existing_result` 不新增 requirement、不调用 Tool/provider，从 durable digest 生成回答；digest 缺失时明确 no-answer/需重查。该边界服务展示稳定性，不宣称生产级隐私认证。
- 实现落点采用 additive Context/Compact v2，而非修改 TaskState/数据库表：`TaskResultDigest v1` 上限 8 KiB、最多 16 个 Evidence IDs；Context v2/Compact v2 携带最新 digest，B6 v1 payload 仍可 strict decode。普通完成 turn 原子提交 digest；`ask_about_existing_result` 产生空 TaskDelta、零 Graph/Tool/provider 本地回答；digest 缺失则明确要求重查。数据库继续使用 0005 既有 JSON context 列，无 Alembic migration。
- Digest 首轮测试已执行 25 项业务断言后被 Windows basetemp 权限阻断剩余 5 项，无产品断言失败；沙箱外新目录重跑专属 Context/Task/API/Loop/Probe 组=`40 passed, 1 existing warning`。随后 B5/B6 contract、API Context、v6/v7 assurance 兼容组=`21 passed, 1 existing warning`。结论：additive v2 写入、v1 历史读取、Compact、边界原子提交和 artifact validator 未见回归；决定=`continue`，进入 P2 r8 前台预检。
- r8 前台预检通过：launcher parser=`0`、六 proxy=`7897`、proxy TCP=`true`、DashScope=`404/404`、r8 目录不存在；未发送任务/schema payload。决定=`continue`，允许后台运行。
- M49-P2 r8 已在预检通过后后台启动：PID=`53572`；stdout=`.agent_work/temp/m49/probe-p2-r8-run/stdout.log`；stderr=`.agent_work/temp/m49/probe-p2-r8-run/stderr.log`；退出码=`exit-code.txt`；完成标记=`done.txt`；safe artifact 预期=`.agent_work/temp/m49/probe-p2-r8/result-safe.json`。当前状态：**运行中，待检查**。

## M49-P2 r8 最终结果

- 2026-08-27 18:24～18:32：后台完成标记与退出码均已检查，`exit-code=0`、decision=`continue`、`first_failure=null`。同一次真实运行中 T1～T5 全部 `complete/answer_ready`：T1 单月 SQL；T2 完整显式重述替换并完成双月比较；T3 quality driver 正增长后解锁商品拆分，两项 SQL action 均完成；T4 hybrid SQL + Business Subgraph + 2 citations；T5 correction 后 channel SQL + Business Subgraph + 2 citations。
- worker B 以新进程从 MySQL 0005 durable state 恢复，Compact v2 成功提交，`source_turn_range=[1,5]`、compact identity=`5fb26ea401dbd9733d22b78d68102a5a05ad72138d3d44362c89692ec1b5b705`。T6=`ask_about_existing_result`，从 latest result digest 本地完成：`complete/complete/passed`、reason=`existing_result_digest_ready`、actions=`[]`、provider calls/tokens=`0/0`；没有把“解释结果”错误退化为旧 metric 重查。
- production-like 无 resolver 安全路径同次通过：HTTP 200、公有 reason=`task_unavailable`、内部 blocked，`runtime_invocations=0`、provider=`0/0`、`task_created=false`。运行前与 finally cleanup 后 checkpoint/event rows 均=`0/0`；worker A/B/safety trace SHA-256 分别为 `22fa3b2b...c1bb`、`914af729...1fe4`、`0d93fbb6...4014`。
- 总 usage=`12 provider calls / 51,013 observed tokens`，低于预注册上限 `14 / 60,000`，retry=`0`；worker exit codes=`[0,0]`。safe artifact=`.agent_work/temp/m49/probe-p2-r8/result-safe.json`，stdout/stderr/exit/done 位于 `.agent_work/temp/m49/probe-p2-r8-run/`。stderr 只有既有 Starlette/httpx deprecation 与 external Enterprise RAG unavailable 后按已确认 active business release 执行的提示，没有未处理异常。
- Probe 三态最终决定=`continue`：放行 deterministic budget-trigger/fallback execution evidence、v7/assurance v2 正式 artifact、公开文档和回归收口。证据边界：这是一次受控开发期真实纵向 Probe，只证明该固定演示场景、当前依赖和当前数据快照可运行；不外推为泛化正确率、质量胜出、sealed reserve、held-out 或生产就绪。
- P2 后同源离线核验（provider/DB writes=`0`）：T6 answer 与 T5 answer 逐字一致（均 124 chars），`graph_invocation_count=0`、actions=`0`、TaskDelta requirements=`0`，Context version=`phase4b-task-context-window-v2`，result digest identity=`e1638ece...b368`。这补足 safe summary 中没有展开的“零 Graph 且确实复用最近结果”证据。
- Deterministic execution evidence：首轮/次轮因 Windows pytest basetemp 权限/父目录问题得到 `3 passed + 3 setup errors`，无产品断言失败；显式建立全新目录后沙箱外同集合得到 `6 passed in 0.73s`。覆盖 candidate budget trigger、Compact build failure 保留 uncompacted source、memory/MySQL version fencing、错误 owner 统一 unavailable + terminal scrub、Scenario v7 重签后仍拒绝 private payload。JUnit=`.agent_work/temp/m49/deterministic-evidence-r3-approved/junit.xml`，SHA-256=`9f2f9e55...65e0`。P2 safe artifact SHA-256=`881e8111...bad4`；既有 M48-P2 durable negative-path artifact SHA-256=`67ac498e...27a7`。这些定位符将作为 v7 case 的独立 execution evidence，不能用 B6 contract identity 替代。
- 正式 rehearsal 首次直接运行 `python scripts/rehearse_m49_phase4b.py` 暴露 `ModuleNotFoundError: eval`：脚本此前只有可 import 函数，没有从 `scripts/` 入口运行时的仓库根 `sys.path` seam。修复为显式仓库根引导并新增 argparse CLI；没有用临时 `python -c` 代替正式入口。随后同一 evidence package 生成并 strict validate：Scenario v7=`completed / 9b133cdf...ed080`，assurance v2=`completed / bc495840...e36bf`。正式输入/产物位于 `eval/reports/m49/`；10 个 scenario 分别绑定 M49-P2 r8、deterministic JUnit 或 M48 durable negative-path artifact，不读取 sealed reserve。
- 文档同步：AI_CONTEXT/runbook/database state/roadmap 已登记 Context/Compact v2 latest result digest 的 8 KiB/16 Evidence ID 边界与 v1 兼容；README 更新为 B0～B6 + M49 连续联调现状，并明确 fixed demo technical closure、Pipeline default/Subgraph experimental、无质量胜出/生产认证外推。正式报告 `eval/reports/m49/m49-phase4b-continuous-rehearsal.md` 采用同一边界。

## M49 全仓回归后台启动前 checkpoint

- 截至 2026-08-27，核心决策均已按用户确认落地：G49-1～G49-7 采用 A；G49-8 按个人 Demo 的现场稳定性采用 C，但收敛为 Context/Compact additive v2 bounded latest result digest，不改 TaskState/数据库表，旧 v1 继续可读。Pipeline 默认、Subgraph experimental、no auto-fallback、reserve sealed/not-run 不变。
- 关键改动范围：完整显式重述替换主 requirement；comparison repair-success/跨 turn coverage；两期 quality delta 确定性依赖；QueryPlan/SQL generation 正反例；结果 digest 与零 Graph existing-result path；Scenario v7/assurance v2 独立 execution evidence；M49 Probe/rehearsal/测试及 README/roadmap/state/report 对齐。
- 已完成验证：M49-P2 r8=`continue`（T1～T6、restart/Compact、安全负例、12 calls/51013 tokens、cleanup 0/0）；deterministic evidence=`6 passed`；最终聚焦=`35 passed, 1 existing warning`；compileall、rehearsal reproducibility、`git diff --check` 与 stale-public-wording scan 均通过。Scenario v7/assurance v2 identities=`9b133cdf...ed080 / bc495840...e36bf`。
- 已知边界/风险：真实 Probe 只证明固定演示链；result digest 增加有限回答文本的 durable privacy surface，但有 8 KiB/16 Evidence ID 上限且 terminal scrub；未运行 held-out、sealed reserve、生产数据、大规模 Eval或默认切换。既有 Windows pytest basetemp 权限问题可能再次造成环境失败，出现时先定位，不把 setup error 记成产品回归。
- 待完成：后台全仓 pytest；检查 exit/done/log 后更新 notes、Phase 4B changelog 与最终状态；再按模块技术收工流程审计注释/Probe 时点/文档和交付。后台结果未检查前不得宣称 M49 完成。
- 全仓 pytest 启动前 launcher parser errors=`0`，exit/done/log 均不存在；确认前台聚焦和静态门无问题后才转后台。后台 PID=`67096`，launcher=`.agent_work/temp/m49/pytest-full-final/launcher.ps1`，日志=`pytest.log`，退出码=`exit-code.txt`，完成标记=`done.txt`，异常日志=`launcher-error.log`，均位于同一 run 目录。当前状态：**运行中，待检查**。

## M49 全仓回归 attempt 1 launcher 失败

- 用户发现 `done.txt` 不到一分钟出现后立即检查：PID `67096` 已退出，`exit-code=4`，done=`2026-08-27T19:27:51.9968301+08:00`，日志仅 203 bytes。pytest 在 collection 前拒绝：`--basetemp: basetemp must not be empty, the current working directory or any parent directory of it`；没有执行任何测试，不能形成产品回归结论。
- 根因是 launcher 把 PowerShell 表达式直接写成 `--basetemp=(Join-Path ...)`，native argument binding 没有把计算结果作为一个路径值传给 pytest。修复方式不改变测试范围：先把 `$baseTemp` 求值为绝对路径，再用独立参数 `--basetemp $baseTemp`；使用新目录 `pytest-full-final-r2`，保留 attempt 1 的 launcher/log/exit/done，不覆盖。
- 按用户纪律不立即后台重跑：r2 必须先完成 launcher parser、目标目录/marker 和同一 basetemp 参数的全仓 `--collect-only` 前台预检；只有预检正常才可后台运行。
- r2 前台预检通过：launcher parser errors=`0`；绝对 basetemp 位于 `.agent_work/temp/m49/pytest-full-final-r2/preflight-basetemp` 且不是 cwd/父目录；exit/done marker 均不存在。使用与 launcher 相同的 `--basetemp $baseTemp` 参数形态做全仓 `--collect-only`，结果 `677 tests collected in 3.16s`、exit 0、仅既有 Starlette/httpx warning。决定=`continue`，现在才允许转后台执行完整 677 项。
- r2 已在预检通过后后台启动：PID=`65756`；目录=`.agent_work/temp/m49/pytest-full-final-r2/`；launcher=`launcher.ps1`、日志=`pytest.log`、退出码=`exit-code.txt`、完成标记=`done.txt`、异常日志=`launcher-error.log`。当前状态：**运行中，待检查**，未宣称全仓通过。

## M49 全仓回归最终结果

- r2 完成标记=`2026-08-27T19:41:34.1120905+08:00`，PID 已退出，`exit-code=0`，无 launcher-error。全仓结果=`677 passed, 1 warning in 595.25s (0:09:55)`；warning 仅为既有 Starlette TestClient/httpx deprecation。M1～M49、legacy/Phase 4/Phase 4B、Context v1/v2、Scenario v1～v7 与 assurance v1/v2 均在同一次当前代码运行中通过。
- 与 attempt 1 分账：attempt 1 是 collection 前的 launcher 参数失败，零测试执行；r2 在 full `--collect-only` 前台门后才后台执行，不能把两次拼成同一运行。最终可信全仓证据只引用 `.agent_work/temp/m49/pytest-full-final-r2/{pytest.log,exit-code.txt,done.txt}`。
- 回归决定=`continue`：未发现需要修复的产品回归，进入 `finish-module` 技术收工审计；不重复运行全仓，不追加真实 Probe/Eval。

## 模块名称与改动文件清单

- 模块：M49 — Phase 4B 最终联调与证据可信度优化。
- 基线 HEAD：`6e3cf3459088010e308a28d8361cd10b4348faba`；模块期间无提交、无 staged 文件。
- 核心运行时：`engine/phase4b/{task_turn,task_runtime,task_context,agent_loop}.py`、`engine/nl2sql/prompt.py`。
- 合同、Probe 与 rehearsal：`eval/agent_scenario_v7_contracts.py`、`eval/phase4b_assurance_v2.py`、`scripts/probe_m49_t1_t2.py`、`scripts/probe_m49_phase4b_continuity.py`、`scripts/rehearse_m49_phase4b.py`、`eval/reports/m49/*`。
- 测试：`tests/test_m43_task_{runtime,api_trace}.py`、`tests/test_m44_agent_loop.py`、`tests/test_m48_task_context.py`、`tests/test_phase3a_planner.py`、`tests/test_m49_{probe_contract,v7_assurance}.py`。
- 文档：`README.md`、`docs/phase4b-roadmap.md`、`docs/notes/m48-review.md`、`docs/notes/m49-{plan,notes}.md`、`docs/state/{AI_CONTEXT,database-current-state,runbook,eval-baselines}.md`、`docs/state/change-history/phase4b.md`、`eval/reports/m48/m48-continuous-rehearsal.md`。

## 关键决策与取舍

- G49-1～G49-5 均按用户确认采用 A：typed completeness 替换完整重述、additive v7/assurance v2、B4 experimental-only 正式收口、默认开发库正常迁移 0005、内部/公开安全 reason 分层。
- QueryPlan 与 SQL fidelity 均采用 prompt 正反例，不弱化 validator，也不让候选 SQL 反过来自证计划正确。
- G49-6/G49-7 均采用 A：从 guarded typed rows 确定性计算两期质量增量；已有 active Evidence 且本轮未重查时允许跨 turn comparison coverage 复用。
- G49-8 按个人 Demo 的现场稳定性采用 C，但收敛成 Context/Compact additive v2 的有界 latest result digest，而不是扩大 TaskState 或数据库 schema。这样 T6 可零 Graph/Tool/provider 解释最近结果，同时 v1 可读、terminal scrub 和隐私上限不变。
- LLM Turn Understanding 方案 C 未实施，只写入 `AI_CONTEXT.md` 防遗忘账本；没有用临时模型判断替代确定性 TaskDelta 合同。

## 阶段 1 注释小结

- 审查 17 个本轮新增或实质修改的 Python/测试文件，共扫描 247 个 AST symbol；重点覆盖 Turn Understanding、Controller 派生事实、Context v2/result digest、v7/assurance、Probe/rehearsal 与新增回归。
- 补充或修正 31 处模块/类/函数 docstring 与关键注释，包括 safe projection 不等于 Evidence、v2 写入/v1 读取、跨进程 digest、Probe 数据隔离与真实依赖。
- 剩余自动扫描命中均为既有简单 fixture、dataclass dunder、property 或一行投影，按注释规则豁免；M49 新增/实质修改代码没有非豁免注释缺口。

## 阶段 2 验证快照

- 最终聚焦：`35 passed, 1 existing warning`；deterministic execution evidence：`6 passed in 0.73s`，JUnit SHA-256=`9f2f9e55...65e0`。
- 全仓：前台 `--collect-only` 收集 677 项后后台执行，`677 passed, 1 warning in 595.25s`；可信证据为 `.agent_work/temp/m49/pytest-full-final-r2/{pytest.log,exit-code.txt,done.txt}`。attempt 1 只是 collection 前 launcher 参数错误，零测试执行，未混入通过结论。
- 静态/数据库：compileall 通过；`alembic current=20260827_0005 (head)`；`alembic check=No new upgrade operations detected`；rehearsal 重签 identity 稳定；`git diff --check` 通过（仅 Git 行尾提示）。
- 正式产物：Scenario v7=`9b133cdf0bd1c071a0f10f79d03e86a0cdc00a4a75258a5d0e878a78e8ced080`；assurance v2=`bc4958405eb777b9be3a0ee1e392a9592181792d3563e0b1be33db53312e36bf`，均为 completed。

## Live Dev Probe 开发时间线

- 审计结论：M49-P1/P2 均为开发切片期间执行，不是收工时补跑；原始失败、修复、重验、usage、Trace hash、数据清理和三态决定已在上文按时记录。P1 虽在 v7 schema 草案之后执行，但正式 artifact/claim 尚未生成，P1 `continue` 仍阻塞了正式证据投影；该流程偏差已如实保留，不构成 `development_probe_missing`。
- P1 最终 `continue`：真实 Qwen + Text2SQL + Guard + MySQL 完成 T1/T2，4 calls / 13,075 tokens，得到 120000/180000/60000/50%，并自然覆盖一次 `DATE_TRUNC` failure → deterministic repair success；cleanup=`0/0`。原 runner assertion 缺陷与同源零调用复核分账保存。
- P2 r8 最终 `continue`：同一 task 真实贯通 T1～T5，worker B 新进程恢复、Compact v2 与 T6 digest 复用通过；安全负例在 deep runtime/provider 前关闭。总计 12 calls / 51,013 observed tokens、retry=0、cleanup=`0/0`，低于 14/60,000 上限。
- P2 r1～r7 的首错层均保留：QueryPlan alias、代理/网络、derived SQL scope、Controller dependency/cross-turn coverage、T6 既有结果合同。没有把不同运行拼成一次通过，也没有覆盖旧 artifact。
- 数据边界始终为隔离 MySQL task/seed、当前 business active release 与服务端 experimental Subgraph；未读取 held-out/sealed reserve，未接生产数据、Milvus/external、大规模 Eval、默认策略切换或 reset/reseed。
- 证据边界：只证明当前固定 Demo 场景与依赖快照可连续运行；不能外推为开放问法泛化、RAG/LLM 质量胜出、生产认证、性能/HA 或外部 Tool exactly-once。

## 参考资料

- 复用 `docs/phase4-reference.md` 的版本化 artifact、父子预算、Evidence/Context 分权与失败关闭 seam，并结合 M42～M48 plan/notes、Phase 4B changelog 和当前源码合同定点核对。
- 借鉴并落地：additive schema/version、closed-world identity、服务端受控策略、执行证据与合同 identity 分离、bounded context。
- 明确未照搬：LLM 自由摘要/自由 TaskDelta、自动 SQL 语义改写、弱化 plan fidelity validator、Graph program counter 持久化、将 deterministic artifact 冒充质量 Eval。
- 本模块未新增外部网页/论文研究，也未运行 sealed reserve 或正式质量基线。

## Handoff

- Phase 4B 展示型技术链已具备可重复的固定 Demo：T1～T6、SQL/Knowledge/Subgraph、Evidence/预算、MySQL durable state、Compact/restart、Response/Trace 与 evidence-backed v7。
- 当前不建议无失败簇继续扩功能。若后续代表性 paraphrase 出现稳定 Turn Understanding 失败，可另立编号模块评估账本中的 LLM structured TaskDelta；必须保留确定性 validator、closed-world Action、预算/ACL/outbound 与失败关闭。
- 长期保留边界：Pipeline 默认、Subgraph experimental、reserve sealed/not-run；latest result digest 是 Demo 稳定性材料，不是 Evidence/ACL/业务 authority。

## 技术档案 checklist

- [x] Phase 4B changelog 已新增 M49 模块档案，并在 M48 旧结论原位追加修正注。
- [x] `AI_CONTEXT.md` 已改为 M49 技术收工完成状态，并登记全仓 677 项证据与能力边界。
- [x] `runbook.md`、`database-current-state.md`、`eval-baselines.md` 已逐项检查并更新受影响事实。
- [x] `rag-current-state.md` 已检查；因 corpus、release、runtime、策略与质量结论均未改变，确认无需更新。
- [x] 完整回读 notes/changelog/state/README/roadmap，执行 diff、链接和 stale wording 检查。

## State impact

- `AI_CONTEXT.md`：已更新当前模块状态、全仓验证与交接结论。
- `runbook.md`：已更新 Context/Compact v2 与 evidence-backed rehearsal 入口。
- `database-current-state.md`：已更新默认库 0005、表计数不变和 digest 持久化边界。
- `eval-baselines.md`：已把当前 Phase 4B deterministic artifact 更新为 v7/assurance v2，并明确其 baseline-ineligible/非质量结论。
- `rag-current-state.md`：已检查，无更新；M49 未改变 RAG corpus、active release、Pipeline/Subgraph rollout、Milvus identity、Eval 质量或 reserve 状态。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代原问题/影响、关键概念、解决方式、取舍、验证证据与未证明边界；不适用项已省略。
- [x] 每个编号点均用一句结论开头，并通过 `- **小标题**：` 或短段拆分，无超过约 4 行的连续大段。
- [x] 正文英文/代码术语首次出现时有括号或通俗解释。
- [x] 对照数字优先使用列表或表格，没有埋入长句。
- [x] 新概念已用通俗语言解释，没有强行编造概念。
- [x] “代码阅读路线”按真实调用/数据流组织，并说明每步为什么存在、解决什么问题。
- [x] 有“设计要点”，且最后一个句号按技能要求写为“汪。”。
- [x] “有面试价值的亮点”可背、可独立展开，只保留拿得出手的内容。
- [x] 面试追问围绕亮点，分层真实，没有低价值凑数；压力回答按技能要求以“喵。”结束。
- [x] “验证与下一步”只引用 M49 notes 已记录的真实验证快照。
- [x] 复制命令安全、可重复，并标明前置条件和预计结果。
- [x] 各小节均使用适量 `**...**` 加粗扫读锚点，没有整段加粗。
- [x] 已完整回读 M49 新增章节，以首次读者视角检查术语和段落长度。
- [x] 已确认本轮只修改 `docs/dev-log.md` 与 `docs/notes/m49-notes.md`，未修改技术状态或代码。
- [x] `git diff --check` 通过。

执行结果：Track A 模块记录交付门全部通过。自检时补写了开头与代码路线中的术语解释，明确了 CTE、Graph、worker、provider、FastAPI/Swagger 等首次出现含义，并把 P1/P2、T6 零调用、artifact identity、迁移计数和 677 项全仓证据整理为表格；没有新增或重跑模块验证。A1 的初始 `git status` 已包含 M49 技术收工留下的 state/code dirty 文件，本轮新增修改仅为 `docs/dev-log.md` 与本 notes。

## finish-docs 阶段总结执行清单（Track B）

- [x] 章节开头有日期、“简述”和“先用大白话讲”。
- [x] “这次做了什么”有概览段，并分编号按阶段主线组织，不按模块逐篇缩写。
- [x] 每个编号点：有可独立成立的结论句，用 `- **小标题**：` 或分段落拆分，无超过约 4 行的连续大段。
- [x] 术语扫描通过：正文每个英文/代码术语首次出现时都有括号或一句话解释，旧模块术语同样处理。
- [x] 数字对账完成：B1 第 5 步的每一项数字均与 state 文档核对一致，分歧已在会话中报告。
- [x] 边界口径一致：“已完成 / 未完成”与 AI_CONTEXT 当前路线判断和防遗忘账本一致。
- [x] “阶段主线图”真实反映区间内模块的链路，没有编造不存在的路径。
- [x] “关键知识点串联”为阶段级概念，通俗解释充分。
- [x] “阶段设计取舍”覆盖本阶段主要取舍，且与 changelog 中的决策记录一致。
- [x] “有面试价值的亮点”有可背、可独立展开的亮点。
- [x] “有面试价值的亮点”只讲能在面试中拿得出手的、能让面试官认可能力的，禁止强行凑数。
- [x] 追问优先围绕亮点展开，没有强行凑数的低价值问题和回答。
- [x] “阶段成果与边界”用清晰 bullets 区分完成与未完成，未完成项没有写成已完成。
- [x] “下一阶段怎么接”只写有证据支持的方向，不机械按模块号递增。
- [x] 全文关键句、结论、数字适当加粗，无整段加粗。

执行结果：Track B 阶段总结交付门全部通过。范围按 B0～B6 / M42～M48 + 插入的 M44A + 最终联调 M49，M41 仅作 Phase 4 RAG Eval 前置背景。数字已在 M42～M49 notes、M49 收工后 RAG notes、Phase 4B 整体审计 notes、`AI_CONTEXT`、`eval-baselines`、数据库/RAG/Milvus state 与 Phase 4B changelog 间逐项核对，本次未发现互相冲突的数字；特别区分了 M49 冻结点全仓 `677 passed` 与收工后水化修复受影响回归 `84 passed`，没有把不同运行混算。

完整回读后补写了阶段范围口径、术语首次出现解释和关键证据对照表，并明确默认演示数据入口、RAG cited-gold、scheduler/生产边界等不能写成已完成。最终 Git 核对还发现审计 notes 中“RAG 修复尚未提交”只是当时状态：当前 `git log` 已有 `32ed649 m49-post-Probe`，`git status --short` 仅包含本轮 `docs/dev-log.md` 与本 notes，因此已从阶段总结删除该失效缺口。最终新增章节共 209 行，9 个三级小节，无残留插入标记或超过 420 字符的单行大段。本轮未修改 `AI_CONTEXT.md`、`CHANGELOG_INDEX.md`、change-history、代码或其它文档。`git diff --check` 通过，仅有 Git 的 LF→CRLF 行尾提示。
