# M44 Phase 4B B2 开发素材

> 本文是 M44 实施过程的事实记录。关键决策、踩坑、取舍和验证结果在发生时立即追加；最终技术收工由 `finish-module` 基于本文整理。

## 2026-08-24 M44 post-finish defect repair implementation checklist

- [x] R1：让真实 `blocked/sql_execution_error` 经安全分类后仅对精确 MySQL `DATE_TRUNC` 问题进入既有 allowlisted repair；generic DB error/timeout/Guard deny 继续零 repair。
- [x] R2：API Response、Action Observation 与 JSONL Trace 统一使用 safe SQL failure projection，移除底层 DBAPI/SQLAlchemy 异常文本。
- [x] R3：补 real-shape deterministic regression，覆盖 repair 可达、错误动作排除和 API/Trace 非泄漏。
- [x] R4：完成聚焦 deterministic tests 后执行 `M44-PFIX-1`，实际时点为 broader regression 前；canonical T1→T2 首次+一次最小重验累计预算经用户调整为≤10 calls / ≤35000 observed tokens，结果立即记录 `passed/failed/inconclusive` 与 `continue/revise/stop`。（已执行，结果 failed/revise，不代表放行）
- [x] R5：Probe 放行后完成受影响回归、必要全仓验证，并重新执行 `finish-module` 技术收工。
- [x] R6：在 closed-world 服务端 repair strategy seam 下实现候选 A（确定性 AST）与候选 B（增加 required output aliases 的 LLM repair），比较阶段保持原 `llm_minimal` 默认；G3 用户确认后才切换默认。
- [x] R7：先用 deterministic tests 验证 A 不调用 repair provider且保留 projection、B 只增加可信 alias 且不泄漏私有字段；随后 A/B 各跑一次真实 T1→T2。
- [x] R8：按授权审计两项候选并报告；runner 的 usage 因后置 Gate 漏记被判为下界，已停止调用并由用户选择缩小版 A。

### 修复开工指纹

- 执行时间：2026-08-24；代码阶段：尚未修改 repair/security 代码，正从真实 smoke 根因进入修复。
- HEAD：`5ef7c47feb2584589a1c85c11373b87b9ff3771d`。
- 开工 dirty：`docs/notes/m44-notes.md`、`docs/state/AI_CONTEXT.md`、`docs/state/change-history/phase4b.md` 及新报告/当时位于 `.codex/temp_work/` 的运行材料，均来自刚完成的真实 smoke 与状态固化；业务代码尚无本次 repair 修改。运行材料随后已迁至 `.agent_work/temp/`。
- 范围边界：只处理 M44 C9/C10 已冻结合同的真实实现缺陷，不改默认模型、budget、outbound purpose、数据库、Knowledge runtime 或 M45/B3 能力。
- Probe 预登记：`M44-PFIX-1`，after repair + focused tests / before broader regression；被阻塞切片为 R5 broader regression 与 renewed finish-module。

### 修复切片 R1～R3：首轮实现与聚焦测试

- 实现：`SQLToolResult` 增加不含 driver 原文的 closed-world `issue_code`；真实 MySQL 1305 且 candidate SQL 含 `DATE_TRUNC` 时才标 `mysql_unsupported_date_trunc`。Harness 不再要求技术失败的 `safety_status=passed`，只凭该 typed code 准入既有一次 repair；generic DB error 保持不可 repair。
- 安全：SQL Tool 的公开 `blocked_reason`、ToolCall 与 lifecycle span 改为固定安全话术，详细异常只进入受控本地日志；API projector 对 `sql_execution_error` 的 ToolCall/TraceStep 再做防御性脱敏，Response 与 Trace 共用该结果。
- 回归：新增真实 `blocked/sql_execution_error` 形状的 1305/2006 对照，以及 adapter 即使误塞 raw error 时 API/Trace 仍不外露的测试。
- 首次聚焦命令：`python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m44-pfix-focused tests/test_m44_sql_failure_bridge.py tests/test_m44_agent_loop.py tests/test_m44_api_trace.py -q`。
- 结果：9 tests passed 后，4 个依赖 `tmp_path` 的 API tests 因 pytest session 的 sandbox `WinError 5` 报错；没有 assertion failure，当前不能把这 4 项记为通过。决定：保持代码不变，在沙箱外重跑同一命令以区分环境与代码问题；`M44-PFIX-1` 仍被 focused Gate 阻塞，尚未执行真实 provider。
- 沙箱外同组重跑：`13 passed, 1 warning in 1.32s`，exit 0；warning 为既有 Starlette TestClient/httpx deprecation，不影响本修复。R1～R3 focused Gate 通过，决定放行预登记的 `M44-PFIX-1`，但 broader regression 继续被 Probe 结果阻塞。

### M44-PFIX-1 启动前 checkpoint

- 计划/实际时点：after defect code + focused deterministic tests / before broader regression，符合 plan addendum；这是重开开发期间的首个 Probe，不把此前 post-module smoke 倒填为开发证据。
- 执行时间：2026-08-24；当时代码阶段：R1～R3 已落盘且聚焦 13 tests 通过，尚未开始 broader regression 或 renewed finish-module。
- HEAD：`5ef7c47feb2584589a1c85c11373b87b9ff3771d`。
- 模块相关 dirty：`engine/tools/sql_tool.py`、`engine/harness/adapters.py`、`app/api/query.py`、`tests/test_m44_sql_failure_bridge.py`、`tests/test_m44_api_trace.py`、`docs/notes/m44-{plan,notes}.md`；另有本次 smoke 已产生的 state/history/report 修改和当时尚位于 `.codex/temp_work/` 的运行材料，现已迁至 `.agent_work/temp/`。
- 真实依赖与范围：真实 FastAPI `/api/query`、Qwen `qwen3.7-plus`、MySQL；在同一未提交事务临时 append 官方 Phase 4B seed，结束必 rollback 并核对前后快照。只跑 canonical T1→T2 首次一次，≤6 calls / ≤20000 observed tokens，不触碰 T3～T5、RAG Eval、held-out、sealed reserve，不换模型/backend 或自动重跑。
- 观察与停止：必须同时检查 T2 一次 repair、comparison oracle、invalidation、usage、Response/Trace raw DB error 缺席及数据库恢复；任何系统性失败均形成 `failed/revise` 并停止 broader regression。runner `.agent_work/temp/m44_pfix_probe.py` 已 `py_compile` 通过。
- 待启动命令：后台执行 `.agent_work/temp/run_m44_pfix_probe.ps1`；启动后补 PID、stdout/stderr、exit/done、artifact/Trace 路径，结果检查前不得标 Probe 通过或继续收工。
- 后台任务已启动：PID `66728`；launcher `.agent_work/temp/run_m44_pfix_probe.ps1`；stdout `.agent_work/temp/m44-pfix-probe-20260824-01.stdout.log`；stderr `.agent_work/temp/m44-pfix-probe-20260824-01.stderr.log`；exit `.agent_work/temp/m44-pfix-probe-20260824-01.exit.txt`；完成标记 `.agent_work/temp/m44-pfix-probe-20260824-01.done`；artifact/Trace 目录 `.agent_work/temp/m44-pfix-probe-20260824-01/`。路径为任务结束后按项目规则迁移后的最终位置。

### M44-PFIX-1 首次结果（failed → revise）

- 后台结束：exit `0`，done `2026-08-24T18:48:25.3576869+08:00`；runner 本身和数据库恢复正常。artifact `m44-live-dev-probe-v1 / M44-PFIX-1`，Trace SHA-256 `acd2353bc39bbe05880fa07d90e28f425cc069060824f19c013fd8db0fb8657b`。
- 用量：3 provider calls / 11342 observed tokens，全部 usage 可观察，未越过 6 calls / 20000 tokens；未重跑、未换模型/backend、未触碰 T3～T5/RAG/held-out/reserve。
- 已通过：T1 得到 `120000`；T2 `modify_constraint` 与 1 条旧 SQL Evidence invalidation 正常；Response/Trace 的四类 raw DB error marker 均缺席；事务 rollback 后数据库前后快照一致。
- 失败层：T2 在第一次 SQL 生成后的 fidelity Gate 以 `sql_plan_contract_failed / order_expression_or_sequence_mismatch` 停止，只发生 1 次模型调用，尚未进入数据库或 repair。QueryPlan 的月份表达式是 PostgreSQL `DATE_TRUNC('month', processed_at)`，生成器已正确改成 MySQL `DATE_FORMAT(processed_at, '%Y-%m-01')`，但 fidelity validator 把两者判为不等价。
- 三态与开发决定：`failed → revise`。这不是原 `blocked/passed` bridge 修复回归，也不能靠重跑解决；broader regression/finish-module 继续阻塞。下一步先调查 SQL fidelity 已有 narrow-equivalence seam，判断能否在不放宽通用保真/Guard 的前提下登记精确月份方言等价；若会改变安全边界，先向用户说明方案并确认。
- 目录纠正：本次误按上层通用规则使用 `.codex/temp_work/`，但项目内更具体事实源要求共享运行材料使用 `.agent_work/temp/`。后台结束后已把本轮 M44 runner/产物迁至 `.agent_work/temp/` 并修正文档指针；以后不再向 `.codex/temp_work/` 写项目运行材料。

### PFIX-G1 用户决策与 revise 方案

- 用户于 2026-08-24 选择方案 A：在 `fidelity_contract` 既有 `narrow_equivalences` seam 增加精确月份方言等价，只接受同一字段的 `DATE_TRUNC('month', column)` 与 `DATE_FORMAT(column, '%Y-%m-01')`；不同字段、粒度、格式、排序方向或其他合同差异继续拒绝。
- 明确不采用：不故意让 generator 保留错误 SQL 来强制展示 repair；不保持现状继续误杀；不把 `sql_plan_contract_failed` 加入 repair allowlist。
- Probe 标准修正：正确 MySQL SQL 能直接通过时零 repair 是正确行为；只有真实 SQL execution 形成 `mysql_unsupported_date_trunc` typed issue 时才要求一次 repair。首次失败 attempt 永久保留。
- 用户批准首次+最小重验的累计额度由 6 calls / 20000 tokens 调整为 10 calls / 35000 tokens；首次已用 3 calls / 11342 tokens。具体代码与聚焦测试落盘后，只允许额外执行 T1→T2 一次，不继续自动重跑。
- 开发决定：`revise` 进入精确 fidelity 修复；修复后的聚焦 Gate 未通过前不得重验，重验未 `passed/continue` 前不得开始 broader regression。

### PFIX-G1 首轮聚焦验证

- 实现已落盘：fidelity 只在计划侧 SQLGlot canonical month bucket 与候选侧 `DATE_FORMAT(..., '%Y-%m-01')` 指向同一解析后 base column 时登记 `month_bucket_dialect_translation:date_trunc_to_date_format`；不同字段/format/方向用例保持 failed。
- 命令：`pytest tests/test_m24_sql_plan_fidelity.py tests/test_m44_sql_failure_bridge.py tests/test_m44_agent_loop.py tests/test_m44_api_trace.py tests/test_m44_b2_contracts.py -q`（项目 Python、沙箱外 basetemp）。
- 结果：`34 passed, 1 failed, 1 warning`。唯一失败是旧 `test_m44_b2_contracts` 仍构造没有 typed `issue_code` 的 `SQLToolResult`，却期待 adapter 仅凭 SQL 字符串猜出 dialect；这与本次真实错误形状修复后的安全合同冲突，不是放宽 production classifier 的理由。
- 决定：保持 production 代码不变，把该 fixture 更新为显式 `issue_code=mysql_unsupported_date_trunc`；generic 对照继续无 code，并重跑同一聚焦集。warning 仍为既有 TestClient deprecation。
- fixture 更新后的同组重跑：`35 passed, 1 warning in 1.52s`，exit 0；精确月份等价、不同字段/format/方向拒绝、真实错误形状、repair allowlist 与 API/Trace 脱敏同时通过。warning 不阻塞。

### M44-PFIX-1 最小重验启动前 checkpoint

- 计划/实际时点：具体 PFIX-G1 修复和聚焦 tests 已落盘，仍在 broader regression 前；符合首次 `failed/revise` 后只重验受影响 T1→T2 一次的门。
- 当时代码阶段：`engine/nl2sql/fidelity_contract.py` 与对应 M24/M44 tests 已修改；R1～R3 安全修复未再变化；HEAD 仍为 `5ef7c47feb2584589a1c85c11373b87b9ff3771d`，工作树包含 notes 开头列明的本轮模块文件。
- 断言修正：SQL generator 已给出可信 MySQL 等价式时，`collect_sql_evidence → sql_completed` 且零 repair 为正确；只有首动作 Observation 为 `sql_dialect_incompatible` 时才允许并要求随后一次 `repair_sql_evidence`。不再为了展示修复强迫执行错误 SQL。
- 累计额度：用户批准 10 calls / 35000 tokens；首次 attempt 已用 3 / 11342。重验 runner 会读取 attempt-01 artifact 并在 attempt-02 同时输出本次与累计 usage，达到累计边界立即停止。
- 真实范围不变：canonical T1→T2、真实 API/Qwen/MySQL、事务内 Phase 4B seed + rollback、Response/Trace raw error scan；不触碰 T3～T5、RAG/held-out/reserve，不换模型/backend，重验后无论结果如何都不再自动运行第三次。
- runner/launcher：`.agent_work/temp/m44_pfix_probe.py`、`.agent_work/temp/run_m44_pfix_probe.ps1`；目标为 `.agent_work/temp/m44-pfix-probe-20260824-02/`。当前尚未启动、尚无重验结论。
- 后台重验已启动：PID `14232`；stdout `.agent_work/temp/m44-pfix-probe-20260824-02.stdout.log`；stderr `.agent_work/temp/m44-pfix-probe-20260824-02.stderr.log`；exit `.agent_work/temp/m44-pfix-probe-20260824-02.exit.txt`；done `.agent_work/temp/m44-pfix-probe-20260824-02.done`；artifact/Trace 目标目录 `.agent_work/temp/m44-pfix-probe-20260824-02/`。当前状态：运行中，待检查；结果检查前不得标 `passed/continue` 或开始 broader regression。

### M44-PFIX-1 最小重验结果（failed → stop pending decision）

- 后台结束：exit `0`，done `2026-08-24T20:04:14.5509633+08:00`；attempt-02 artifact/Trace 完整，Trace SHA-256 `08d10ba21ac7611dc00c2d9cad1b7959f3920f0f728384b9950d558b4171f633`，数据库 rollback 后前后快照一致。
- 本次用量：5 calls / 18089 tokens；与 attempt-01 合计 8 calls / 29431 tokens，未超过用户批准的 10 / 35000。usage 全部可观察；没有第三次运行、换模型/backend 或范围扩大。
- 已通过：T1 `120000`；T2 constraint/invalidation；真实 SQL Tool 将 MySQL 1305 + `DATE_TRUNC` 安全分类为 `mysql_unsupported_date_trunc`；Loop 动作顺序为 `collect_sql_evidence → repair_sql_evidence`，repair 恰好一次；月份窄等价登记生效；Response/Trace raw error markers 均缺席；数据库恢复。
- 最终失败：repair 模型把 candidate SQL 的 `DATE_TRUNC` 正确改为 `DATE_FORMAT`，但同时删除了 QueryPlan required output `diff` 与 `change_rate`，因此 fidelity/output projection Gate 以 `projection_set_mismatch` 正确阻断。T2 为 `unsafe/output_projection_contract_failed`，未形成答案或 SQL Evidence。
- 判断：原始 repair bridge、安全脱敏和 PFIX-G1 均已被真实链验证生效；剩余问题是 LLM repair 不能稳定遵守“只改 dialect、不改输出”的合同。不能靠放宽 projection Gate、重复调用或把 safe failure 算 passed 解决。
- 开发决定：Probe 仍为 `failed`。按已承诺边界不运行第三次；broader regression 与 finish-module 继续阻塞。下一步需要用户重开 G44-4，在“本地精确 AST dialect compiler / 扩大模型 repair context / 保持安全失败”之间选择，并对任何第三次真实验证重新精确授权和设定累计预算。

### PFIX-G2 用户授权与 A/B 实施 checkpoint

- 用户于 2026-08-24 明确同意候选 A、B 都试，并授权执行。该确认重开 G44-4 的 repair 内部实现选择，但不改变 outbound purpose、fidelity/Guard、parent budget、默认模型、知识运行时或 M45/B3 路线。
- 候选 A：本地 AST 只编译 allowlisted 月粒度 `DATE_TRUNC`；repair provider calls 固定为 0。候选 B：LLM repair 只新增来自已验证 QueryPlan 的 required output aliases；raw DB error、rows、Schema/metric/join 继续不得进入 prompt。
- 深 module 取舍：pipeline 只调用一个 closed-world repair interface，策略复杂性留在模块内部；`Text2SQLToolAdapter` 接受服务端构造参数，API 请求无此字段。原 `llm_minimal` 在比较完成和用户选择前保持 production 默认。
- 真实比较边界：A、B 各一次 canonical T1→T2；不是可登记基线的统计学 A/B，不重复抽样。既有用量 8 calls / 29431 tokens，新累计上限 18 / 65000；若 A 使剩余额度不足或运行异常，则停止 B 并如实记录。
- 当前代码阶段：尚未实现 PFIX-G2，HEAD `5ef7c47feb2584589a1c85c11373b87b9ff3771d`；broader regression 与 renewed finish-module 仍被阻塞。下一步先完成策略实现与 focused deterministic Gate，真实调用前再写当时 dirty/命令/路径 checkpoint。

### PFIX-G2 首轮实现与 focused Gate

- 实现：新增 `sql_repair` 深 module 与 `llm_minimal/deterministic_ast/llm_enriched` closed-world 策略；Adapter 只接受服务端构造参数，默认仍为 `llm_minimal`。A 用 SQLGlot AST 编译精确 month/column DATE_TRUNC，B 只把已验证 QueryPlan 的 required output aliases 加进原 repair prompt；两者返回后共用 fidelity、Guard 与执行。
- 新增 deterministic 覆盖：A 的完整四列 candidate 保留 `month/net_refund_amount/diff/change_rate` 且 repair provider 不得调用；B prompt 含可信四列顺序但不含 raw error/Schema details；未知策略失败关闭。
- 首轮命令覆盖 M44 B2、M24 fidelity、真实错误 bridge、Loop 与 API/Trace。结果先完成 `34 passed`，随后 4 个依赖 pytest temp 的 API tests 因 sandbox `WinError 5` 进入 ERROR，和此前同一环境问题一致；没有 assertion failure，但不能据此放行真实 Probe。
- 决定：不改代码，使用已经批准的项目 pytest 命令在沙箱外重跑同一 focused set；只有得到完整 exit 0 才写真实 A/B 启动 checkpoint。
- 沙箱外同组复核：`38 passed, 1 warning in 1.55s`，exit 0；warning 仍是既有 Starlette TestClient/httpx deprecation。随后 product modules 与 Probe runner `py_compile` 通过，`git diff --check` 无 whitespace error（只有 Git 的 LF→CRLF 工作区提示）。focused Gate 放行。

### PFIX-G2 A/B 真实 Probe 启动前 checkpoint

- 执行时点：候选 A/B 产品代码、focused tests 和 runner 已落盘，broader regression 与 renewed finish-module 尚未开始；符合 plan 的开发切片门。
- 当时代码阶段与指纹：HEAD `5ef7c47feb2584589a1c85c11373b87b9ff3771d`。模块 dirty 包括 `engine/nl2sql/{sql_repair,generator,pipeline,fidelity_contract}.py`、`engine/harness/adapters.py`、`engine/tools/sql_tool.py`、`app/api/query.py`、M24/M44 tests、plan/notes 与前序 smoke 形成的 state/history/report；未改 production assembly 默认，仍为 `llm_minimal`。
- 执行顺序：先 A `deterministic_ast`，再 B `llm_enriched`；每个候选只运行一条新的 T1→T2 task，使用独立 TaskBoundary、Trace、临时 seed 事务和 rollback 核对。A 即便能力失败，只要 runner/数据库恢复且仍有额度，也继续 B，以便获得两个候选证据；基础设施异常或达到累计边界则停止。
- 预算与范围：既有 attempt-02 累计为 8 calls / 29431 tokens；A/B 共用总上限 18 / 65000。达到边界不启动下一个候选；已开始响应意外越界只保留 usage 后停止。不运行 T3～T5、RAG、held-out、reserve，不换 provider/model，不重复候选。
- 结果口径：分别检查两轮 oracle、repair action/strategy 是否实际触发、projection Gate、Response/Trace raw error、observed usage 与 DB 恢复。若初始 generator 已直接给出合法 MySQL SQL，则产品链可 pass，但该候选 repair 记为未实际触发，不能据此声称 repair 胜出；两次均为 exploratory/dev-probe，不登记 Formal Eval 基线。
- 后台入口：`.agent_work/temp/launch_m44_pfix_ab_probe.ps1`；总日志 `.agent_work/temp/m44-pfix-ab-probe-20260824-01.log`；exit `.agent_work/temp/m44-pfix-ab-probe-20260824-01.exit.txt`；done `.agent_work/temp/m44-pfix-ab-probe-20260824-01.done`；A/B artifact 与 Trace 分别位于 `.agent_work/temp/m44-pfix-candidate-{a,b}-20260824-01/`。当前尚未启动，不能记录结论。
- 后台任务已启动：PID `27188`。状态为“运行中，待检查”；必须等 done/exit、两份实际生成的 artifact/Trace 和日志全部复核后，才形成各候选 `passed/failed/inconclusive` 及下一步决定。若任务按额度门在 A 后停止，B 不会被伪记为已执行。

### PFIX-G2 A/B 真实 Probe 结果（两项均未放行 → stop pending contract decision）

- 后台结束：done `2026-08-24T20:33:46.7705936+08:00`、launcher exit `0`；A/B artifact 与 Trace 均生成，两次临时 seed 都 rollback，数据库前后快照一致。Response/Trace raw DB error marker 两项候选均为零；底层异常只出现在受控本地日志，符合已修复的安全边界。
- 候选 A `deterministic_ast`：本次 5 calls / 20721 reported observed tokens，连同旧 attempt 的 runner 累计为 13 / 50152。真实动作 `collect_sql_evidence → repair_sql_evidence`，AST repair 实际触发且成功，SQL 不再含 DATE_TRUNC，Gate/执行通过并返回两行 `120000/180000`；Trace SHA-256 `71265284...5dead`。
- A 的整体 Gate 仍 failed：上游本次 QueryPlan/candidate 只要求 `month/net_refund_amount`，所以确定性 repair 忠实保留两列，却没有产生 `diff/change_rate`，Response 不含应有的 `60000`。这说明 A 的 dialect compiler 本身生效，但 canonical T2 的完整比较能力没有闭合，不能把“两个数都查到”降格当作场景通过。
- 候选 B `llm_enriched`：runner 报告本次 5 calls / 21839 tokens、累计 18 / 71991，最后已开始的 T2 越过 token 上限后没有后续场景或重跑；Trace SHA-256 `2918edb5...b8f2`。初始 candidate 含四列；增强 repair 也保留 `month/net_refund_amount/diff/change_rate`，但 repair pipeline 重新生成了一份只要求两列的新 QueryPlan，fidelity 因 extra `diff/change_rate` 正确阻断。因此 B 未证明失败在 prompt 遵循，而是暴露“repair 重新规划、前后合同漂移”。
- usage 新发现：当 repair LLM 已成功返回、随后在 fidelity/output Gate 失败时，`sql_repair` error span 没有写入已收集的 `LLMCallEvidence`；action/artifact 因此漏计该真实 provider request/tokens。B 的 `strategy_exercised=false` 也是 runner 只从 success metadata 找策略导致的观测假阴性。故 `18 / 71991` 只能视为已报告下界，不能作为真实硬预算闭合证据；本轮立即停止任何 provider 调用。
- 三态与决定：A 为 `failed/revise`（dialect repair pass、产品 oracle fail）；B 为 `failed/revise`（被 repair plan drift 阻断，且 usage 不完整）；总决定 `stop pending contract decision`。production 默认仍是 `llm_minimal`，没有把 A 或 B 自动切为默认，broader regression 与 renewed finish-module 继续阻塞。
- 新核心选择门：继续修复需要决定是否把首次执行时的可信 QueryPlan/output contract 作为私有 repair snapshot 复用，并为 task comparison 建立服务端 required output contract；同时必须补齐所有 post-generation failure path 的 usage/strategy Trace。该选择会改变 repair 核心合同与 task→Text2SQL seam，不能在没有用户确认时自行落盘。

### PFIX-G3 用户确认与实施 checklist

- 用户于 2026-08-24 选择上一轮建议的“缩小版方案 A”：repair 私有复用首次可信 QueryPlan/candidate/typed issue，确定性 AST 作为服务端默认，并修复后置 Gate usage/strategy 漏记。
- [x] G3-1：定义不可变 typed repair snapshot，只保留进程内；Action/API/Trace 安全投影不得暴露完整 plan 或新增客户端字段。
- [x] G3-2：初次 dialect failure 把原已验证 plan 与 candidate 交给 Loop；repair pipeline 跳过 QueryPlan provider、复用原 plan 重新走 fidelity/Guard/执行。
- [x] G3-3：production assembly 默认改为 `deterministic_ast`，closed-world 候选仍可由服务端测试注入，未知值失败关闭。
- [x] G3-4：fidelity 等 post-generation failure span 同样写已发生的 LLM evidence、generation stage、strategy 与 issue，使 action usage 不漏账。
- [x] G3-5：补 snapshot 不外露、零 repair provider、原 plan identity/output 不漂移和 failure usage 计数测试；受影响 deterministic regression 已通过。
- 范围收敛：不硬编码 T2 四列、不新增通用 required-output contract、不让 repair 承担 planning/业务计算。真实 Probe 累计额度已耗尽且旧 usage 只知下界，本切片不运行真实 provider。

### PFIX-G3 首轮实现与 focused Gate

- 实现已落盘：`SQLRepairSnapshot` 冻结原 QueryPlanStep/candidate/typed issue；真实 dialect failure 才把 snapshot 放入进程内 ToolObservation 私有字段，Loop repair 只消费它。repair pipeline 仍重做当前 SchemaGraph 与本地 plan validator，但不再调用 QueryPlan provider；默认策略已切为 `deterministic_ast`。
- usage 修复：SQL 已生成后若 fidelity 拒绝，error span 现在同时写 `LLMCallEvidence`、generation stage、repair strategy 与 issue code；action consumption 可按实际 attempt/token 计数。新增测试证明 `llm_enriched` 返回后被 projection Gate 拦截时仍保留 1 次调用证据。
- 首轮 focused 命令覆盖 M44 B2/Loop/真实错误 bridge/API Trace 与 M24 fidelity：先完成 `36 passed`，随后 4 个 pytest temp API tests 再次因 sandbox `WinError 5` ERROR；没有 assertion failure。按既有证据保持代码不变，须在沙箱外重跑同组后才放行下一回归。
- 沙箱外同组复核：`40 passed, 1 warning in 1.66s`，exit 0；warning 为既有 TestClient/httpx deprecation。随后补充首次 dialect failure 签发原 plan snapshot、Action 安全投影不含 snapshot/candidate，以及 failure Trace 可被 B2 consumption 计为 1 call 的合同测试；单文件 `13 passed in 1.10s`。
- 受影响兼容回归：M24、M35、M42、M43、M44、M44A 共 `86 passed, 1 warning in 2.52s`，exit 0；warning 同上且不阻塞。`py_compile` 与 `git diff --check` 通过（diff check 只有 Git LF→CRLF 提示）。

### renewed finish-module 阶段 0 Probe 审计（未完成，退回开发门）

- `M44-PFIX-1` 与 A/B Probe 确实发生在当时 focused Gate 之后、broader regression 之前，时间、HEAD/dirty、命令、artifact/Trace、usage、三态和 `revise/stop` 决定均有 contemporaneous 记录；不存在“收工时首次补跑冒充开发 Probe”。
- 但最后一次真实 A/B 之后，G3 又实质修改了 production 默认、repair 输入合同、QueryPlan provider 次数与 failure usage Trace；旧 Probe 不能反推最终代码真实有效。按 `finish-module` 阶段 0 规则必须退出收工，回到开发期做一次 plan 允许的最小真实重验。
- 当前状态：`finish-module 未完成`，R5 继续未勾选；尚未启动全仓 pytest，也未执行阶段 1–4 的最终技术档案门。
- 所需新授权建议：只运行 canonical T1→T2 一次，真实 API/Qwen/MySQL、事务 seed + rollback、同一 provider/model；本次上限 5 provider calls / 22000 observed tokens，已开始 response 意外越界则保留 usage 后停止。零重跑、零 T3～T5/RAG/held-out/reserve。重点验证 repair action 复用原 plan、repair provider calls=0、实际 usage 完整、raw error 缺席、DB 恢复；整体 oracle 仍按 plan 判定，不因只返回两个月数字而降级标准。

### PFIX-G3 最终 Live Dev Probe 启动前 checkpoint

- 用户于 2026-08-24 明确批准上述最终最小重验。本次是 G3 具体实现与 `86 passed` 受影响回归之后、全仓 regression 与 renewed finish-module 之前的开发切片门；不是收工补跑或 Formal Eval。
- 当时代码指纹：HEAD 仍为 `5ef7c47feb2584589a1c85c11373b87b9ff3771d`；模块 dirty 为本 notes/plan/state/history/report、`app/api/query.py`、`engine/{tools/sql_tool,harness/adapters,harness/contracts,nl2sql/fidelity_contract,nl2sql/generator,nl2sql/pipeline,nl2sql/sql_repair,phase4b/agent_loop}.py` 及对应 M24/M44 tests。production 默认为 `deterministic_ast`，snapshot/usage G3 代码已冻结，尚未开始全仓回归。
- 场景与额度：canonical T1→T2 恰好一次，真实 API/Qwen/MySQL、事务内官方 seed + rollback；独立本次预算 ≤5 provider calls / ≤22000 observed tokens，已开始 response 意外越界则保留后停止。禁止重跑、换模型/backend、T3～T5、RAG、held-out、reserve。
- 断言：T1 `120000`；T2 action/repair/plan reuse/usage 完整，若 repair 触发则 deterministic repair provider calls=0；整体仍要求 `120000/180000/60000`、invalidation、Response/Trace raw error 缺席和 DB 恢复。若初始 SQL 已合法而未触发 repair，产品结果可判定，但 repair 真实验证记 inconclusive；若只返回两个月金额则整体仍 failed，不降低 oracle。
- runner 已更新并通过 `py_compile`；启动前确认 artifact 目录、日志、exit 与 done 均不存在，没有复用旧结果。
- 后台任务已启动：PID `58916`；入口 `.agent_work/temp/launch_m44_pfix_g3_final_probe.ps1`；日志 `.agent_work/temp/m44-pfix-g3-final-20260824-01.log`；退出码 `.agent_work/temp/m44-pfix-g3-final-20260824-01.exit.txt`；完成标记 `.agent_work/temp/m44-pfix-g3-final-20260824-01.done`；artifact/Trace 目录 `.agent_work/temp/m44-pfix-g3-final-20260824-01/`。状态：**运行中，待检查**，不得提前记为通过。

### PFIX-G3 最终 Live Dev Probe 结果与开发决定

- 后台任务完成于 `2026-08-24T21:02:13+08:00`，exit=`0`；artifact `.agent_work/temp/m44-pfix-g3-final-20260824-01/artifact.json`，Trace `.agent_work/temp/m44-pfix-g3-final-20260824-01/trace.jsonl`，Trace SHA-256 `e59a3684...e773d`。
- 本次真实用量为 `4 provider calls / 14298 observed tokens`，低于批准的 `5 / 22000`；两轮 usage 全部可观察。Response/Trace 均无 raw DB error，事务 seed 已 rollback，数据库前后快照一致。
- T1 通过：`120000`。T2 正确使旧 SQL Evidence invalidated，取得 `2026-07=120000`、`2026-08=180000` 两行证据并 `answer_ready`；但没有计算/回答差额 `60000`，故 `t2_comparison_oracle` failed，总 Gate=`failed`，不降低 oracle。
- 本次初始 SQL 已直接使用合法 MySQL `DATE_FORMAT`，只有 `collect_sql_evidence`，未形成 allowlisted dialect error，也没有 `repair_sql_evidence`；因此真实产品结果可判定，但 G3 deterministic repair 路径为 `inconclusive`。不得为了展示 repair 故意执行无效 SQL或重复抽样；snapshot/reuse/provider=0 目前只有 deterministic tests 证明。
- 根因定位：T2 的真实 QueryPlan 只冻结 `month/net_refund_amount`，SQL 与 output projection 忠实返回两列；顶层 Loop 将 requirement coverage 当作完成，却没有独立的 comparison result contract/派生计算。因此这不是 G3 dialect repair 的继续调参点，而是已重复出现的 planning/output completion 缺口。
- 开发决定：`revise/stop-for-decision`。继续修复需要改变 PFIX-G3 已确认的“不建立通用 required-output 平台、不让 repair 补业务计算”边界；在用户确认新方案前不扩范围、不追加真实调用，也不进入 renewed finish-module。

### PFIX-G4 用户确认与 implementation checklist

- 用户于 2026-08-24 确认方案 A：新增窄范围 typed comparison completion；不降低 `60000` oracle，不把业务计算塞进 dialect repair，也不靠增强 LLM prompt 碰运气。
- [x] G4-1：定䵍已验证 SQL rows 到 Agent answer/termination 的最窄 seam，冻结最小 typed comparison input/output；只沿用 API/SQL 单路 Trace 的历史 rows 兼容投影，不新增任意 rows 通道。
- [x] G4-2：仅对可信 `metric_comparison` requirement 计算两期 absolute difference/change rate；异常形状和零基期安全停止。
- [x] G4-3：让 completion 结果参与 `answer_ready` 判定、API Answer 与 Trace same-source 投影，非 comparison/legacy 行为不变。
- [x] G4-4：补成功/失败/安全/兼容 deterministic tests，并在每个依赖切片后运行聚焦验证。
- [x] G4-5：受影响回归通过后审计是否需要新的 Live Probe 授权；不得把已结束 G3 Probe 倒填为 G4 证据。

### PFIX-G4 第一切片：typed completion 与 API/Trace seam

- 新增 `engine/phase4b/comparison_completion.py`：只认服务端 `metric_comparison` requirement、TaskState 中恰好两个 period 和同一 metric；不读 question，不调用 provider，不改 SQL/Evidence identity。两行结果按 TaskState 顺序对齐后确定性派生 `delta/rate`；行数、列、period、数值、重复 period、零基期异常均 blocked。
- Agent Loop 在 SQL-only 收口、`answer_ready` 对外生效前执行 completion。成功时只替换本轮兼容 Answer/rows 投影；失败时 termination 改为 `no_progress/<stable comparison reason>`，已有 SQL Evidence 仍保留，API 只能给 partial，不能把“查到两行”误当“完成比较”。T3/T4/T5 和单期 metric 不适用并旁路。
- 检查公开 Trace 时发现现有 `app/api/query.py::_observation_projection()` 缺 return：白名单 return 被误放进 `_safe_trace_steps()` 的不可达位置，导致 `tool_observation` 恒为 null。该问题会阻断 G4 same-source 证据，已在原 seam 恢复 return；仍沿用既有 diagnostics raw-key 过滤。
- 首轮 sandbox focused：纯完成器 3 项先通过，但 Windows pytest basetemp `WinError 5` 覆盖了集成失败摘要；按纪律只在沙箱外重跑同一集合定位。第一个真实失败为 `TaskState.constraints` 实际是 immutable tuple-of-pairs，代码误按 Mapping 调 `.get()`；已改为在 completion 边界显式 `dict(state.constraints)`，没有改变 TaskState 合同。
- 修正后同一 focused 集合：`18 passed, 1 warning in 1.45s`；warning 为既有 Starlette TestClient/httpx deprecation。该结果覆盖纯 completion、T1→T2 API/Trace、M44 Loop、T4/T5 与 raw DB error projection。
- 补上 Loop 收口硬门后，更新集合为 `19 passed, 1 warning in 1.43s`：两行正确时 `answer_ready/complete` 且产生 `60000/0.5`；只有一行时稳定为 `no_progress/comparison_row_count_mismatch` 与 partial。
- 受影响兼容回归：M24/M35/M42/M43/M44/M44A 共 `108 passed, 1 warning in 84.20s`。恢复 `tool_observation` 白名单投影没有破坏 v1/v2/v3 closed-world、legacy Harness、M44A 或 raw error 非泄漏断言。
- 静态检查：G4 相关 Python `py_compile` 通过；`git diff --check` 仅报告工作区既有 LF→CRLF 提示，无 whitespace error。`git status` 仍包含本轮 M44 defect repair 的全部已知 dirty 文件；没有覆盖或清理用户其他改动。

### PFIX-G4 后台全仓回归启动前 checkpoint

- 时点：G4 typed completion、API/Trace 投影修复、focused `19 passed` 与受影响 `108 passed` 之后；新的真实 Probe 决策和 renewed `finish-module` 之前。
- 关键决定与范围：只新增两期 `metric_comparison` completion；不改 QueryPlan、SQL repair、Evidence identity、模型、数据库、RAG/runtime 或 M45 路线。异常结果禁止 `answer_ready`，单期/非 comparison 完全旁路。
- 已知风险：全仓可能存在仍假设 `tool_observation=null` 的旧 Trace fixture，或存在两期 fake 只返回一行却期待 `answer_ready`；若失败只修相关兼容合同，不降低 G4 Gate。
- 待完成：后台全仓 pytest；结果检查后再判断 Live Probe 精确授权、更新 state/history，并重新进入 `finish-module`。启动前不得把任务记为通过。
- 后台任务已启动：PID `74784`；脚本 `.agent_work/temp/run_m44_g4_full_pytest_20260824.ps1`；日志 `.agent_work/temp/m44-g4-full-pytest-20260824-01.log`；退出码 `.agent_work/temp/m44-g4-full-pytest-20260824-01.exit.txt`；完成标记 `.agent_work/temp/m44-g4-full-pytest-20260824-01.done`；basetemp `.agent_work/temp/m44-g4-full-pytest-20260824-01-temp/`。状态：**运行中，待检查**，不得提前宣称通过。

### PFIX-G4 后台全仓回归结果与 Probe 门

- 后台任务完成于 `2026-08-24T21:35:27+08:00`，exit=`0`；结果 `553 passed, 1 warning in 646.74s (0:10:46)`。warning 仍是既有 Starlette TestClient/httpx deprecation。
- 该结果覆盖 G4 新测试和全仓 legacy/Phase 3/Phase 4/Phase 4B 回归；没有触发真实 provider、RAG Eval、held-out 或 reserve。deterministic 开发决定为 `continue`，放行 G4 真实效果门。
- runbook 复核：Live Dev Probe standing authorization 以**每模块**总 calls/tokens 计数，首次与修复重验合并；M44 此前默认额度和多次用户精确扩额已经耗尽。G3 的“恰好一次、≤5/22000”也已执行结束，不能自动复用。
- 已在 plan 预登记新 Probe `M44-PFIX-G4-1`：真实 canonical T1→T2 一次，拟独立上限 ≤5 calls / ≤22000 tokens，只验证 `120000/180000/60000/0.5`、answer_ready、same-source、usage、脱敏与 rollback。状态：**等待用户确认额度，尚未执行**。

### M44-PFIX-G4-1 启动前 checkpoint

- 用户已明确批准：canonical T1→T2 恰好一次、≤5 provider calls / ≤22000 observed tokens；不执行 T3～T5/RAG/held-out/reserve，不换模型/backend，失败不自动重跑。
- 时点：G4 typed completion 代码与全仓 `553 passed` 之后、renewed `finish-module` 之前。HEAD=`5ef7c47feb2584589a1c85c11373b87b9ff3771d`；dirty 范围仍为本轮 M44 defect repair 的 API、Harness、NL2SQL、Agent Loop/completion、对应 tests/report/plan/notes/state/history，未观察到范围外新改动。
- runner `.agent_work/temp/m44_pfix_probe.py` 已扩展为显式 Probe ID，并把 `50%/0.5` 加入 G4 oracle；仍只从公开 Answer/rows 观察值，不保存 prompt/raw error。待 `py_compile` 与新路径存在性复核。
- 后台入口 `.agent_work/temp/launch_m44_pfix_g4_probe.ps1`；artifact/Trace 目录 `.agent_work/temp/m44-pfix-g4-20260824-01/`；log/exit/done 使用同名前缀。当前尚未启动、没有真实 provider call 或结果。
- 启动前 `py_compile` 与两个 PowerShell script parse 均通过，artifact/Trace 目录及 log/exit/done 均不存在，没有复用旧结果。
- 后台任务已启动：PID `66748`；launcher `.agent_work/temp/launch_m44_pfix_g4_probe.ps1`；日志 `.agent_work/temp/m44-pfix-g4-20260824-01.log`；退出码 `.agent_work/temp/m44-pfix-g4-20260824-01.exit.txt`；完成标记 `.agent_work/temp/m44-pfix-g4-20260824-01.done`；artifact/Trace 目录 `.agent_work/temp/m44-pfix-g4-20260824-01/`。状态：**运行中，待检查**，不得提前宣称通过。

### M44-PFIX-G4-1 结果与开发决定

- 后台任务完成于 `2026-08-24T21:47:51+08:00`，exit=`0`；artifact Gate=`passed`，failed assertions=`[]`。本次真实用量 `4 provider calls / 15762 observed tokens`，低于批准的 `5 / 22000`，两轮 usage 均完整可观察。
- T1：`120000`、`answer_ready`。T2：旧 SQL Evidence invalidated 后重新取证，公开 Answer 为“2026-07 120000、2026-08 180000、增加 60000、变化率 50%”；rows 第二行带 `delta=60000.0/rate=0.5`，termination=`answer_ready`。
- same-source Trace：T2 trace id `7291f4d2-0cab-4305-9980-09b1b857a1b1`；`tool_observation.diagnostics.comparison_completion.status=complete`，identity=`41b577e...ecac9`，Answer/columns/rows/termination 与 API artifact 一致。Trace SHA-256 `6e2fc4a2...a54fa`；raw DB marker hits=0。
- 初始 SQL 直接是合法 MySQL，只执行 `collect_sql_evidence`，没有 dialect error/repair；因此 G4 产品效果通过，G3 deterministic repair 的真实路径仍保持 inconclusive。按纪律不故意生成坏 SQL、不追加抽样。
- 事务内官方 Phase 4B seed 已 rollback；运行前后均为 legacy 2026-07 30 rows / `19920`、持久 Phase 4B rows=0，`database_restored=true`。
- 开发决定：`passed → continue`，G4 Probe 门放行 renewed `finish-module`。本 artifact 分类仍为 `exploratory / baseline-ineligible / live-dev-probe`，不登记 Formal Eval 或长期质量基线。

### renewed finish-module 收工记录

- **Probe 时点审计**：`M44-PFIX-G4-1` 在 G4 代码与全仓 deterministic 回归后、renewed finish 前执行；notes 按时记录了 HEAD/dirty、命令、artifact/Trace/usage、三态与 `continue` 决定。收工期没有首次补跑或倒填。
- **最终代码范围**：真实 MySQL typed dialect issue 与 raw-error 脱敏、精确 month fidelity 等价、私有 immutable repair snapshot、默认 deterministic AST repair、post-generation usage 闭合、窄 typed comparison completion 与 `tool_observation` 安全投影恢复。不改 B2 parent budget、模型、数据库、Knowledge runtime 或 M45/B3 路线。
- **最终合同决策**：收工审计发现文档声称“Trace 不保存 rows”与既有实现冲突。用户确认方案 B：SQL 单路（含 task SQL）本地 JSONL 继续保存已经 Guard/授权的 `columns/rows`；Hybrid Trace、action Observation、node Context、Scenario artifact 仍禁止完整 rows，Document/private Evidence/raw DB error/prompt/stack 禁区不变。该决定只对齐文档与既有行为，没有新增运行通道。
- **验证快照**：G4 focused `19 passed, 1 warning`；受影响 M24/M35/M42/M43/M44/M44A `108 passed, 1 warning`；后台全仓 `553 passed, 1 warning in 646.74s`，exit 0。收工期 Trace/comparison 精确复核首次因 Windows pytest basetemp `WinError 5` 未闭合，代码不变在沙箱外同组重跑 `8 passed, 1 warning in 11.86s`。warning 仍为已知 Starlette TestClient/httpx deprecation。`git diff --check` 无 whitespace error，只有 LF→CRLF 工作区提示。
- **状态影响**：`runbook.md` 与 `AI_CONTEXT.md` 已同步 Trace rows 窄例外；Phase 4B history 已固化 defect repair、Probe 证据与用户决策。数据库 schema/data 及 RAG release/index 未改；Probe 临时 seed 已 rollback。本轮 artifact baseline-ineligible，`eval-baselines.md` 不登记新基线。
- **起止指纹**：post-finish repair 起始 HEAD 与收工 HEAD 均为 `5ef7c47feb2584589a1c85c11373b87b9ff3771d`；本轮未提交、未 staged，完整 dirty 范围保留供用户检查。
- **遗留边界**：最终 deterministic repair 在真实 Probe 中因初始 SQL 已合法而未自然触发，故该真实路径仍是 `inconclusive`；有 deterministic snapshot/reuse/provider=0 证据，但不为展示故意执行坏 SQL。M45/B3、M46/B4、B5/B6 仍未开始，不宣称完整 Phase 4B 完成。

#### renewed Handoff

1. **已完成且可依赖**：M44/B2 现可依赖真实 SQL 错误的 typed/脱敏投影、精确月份方言等价、私有 repair snapshot、默认 deterministic AST 和两期 comparison completion；最终全仓回归与 G4 Live Dev Probe 已通过。
2. **未完成与风险**：最终 repair 路径尚无自然触发的真实成功证据，只有 deterministic 证据；本次 Probe 不是 Formal Eval 或长期基线。
3. **必须延续的边界与决策门**：SQL/task SQL 本地 JSONL 可保存 Guarded rows，但 Hybrid/action/Context/artifact 不得借此携带完整 rows；raw error/Document/private Evidence 禁区不变。M45 只能开始 B3 recovery action，不得把 M44 宣称为 B4–B6 或完整 Phase 4B。
4. **建议下一入口**：为 M45/B3 单独调查并制定 module plan；若要获得更强真实效果结论，由用户另行授权 Formal task Smoke，不将 Live Dev Probe 改签为基线。

## renewed finish-module 技术档案交付清单

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] notes 已记录 Live Dev Probe 的切片级计划/实际时点、真实 calls/tokens/Response/Trace/三态和开发决定时间线；不存在 `development_probe_missing`、收工补跑或 Formal Eval 混算。
- [x] 已完整读取 `CHANGELOG_INDEX.md`，并按索引更新 Phase 4B 模块历史与旧结论注记。
- [x] `AI_CONTEXT.md` 已更新，并删除被 G4 通过结论取代的等待/失败流水摘要。
- [x] 命中的 `runbook.md` 已完整检查并同步 Trace rows 方案 B；`eval-baselines.md`、`database-current-state.md`、`rag-current-state.md` 无需修改，原因分别是本 Probe 不登记基线、DB 已 rollback 且 schema/data 未改、RAG runtime/release/index 未改。
- [x] 新结论已与历史条目、代码、测试、Eval、默认配置和各 state 核对；Trace rows 冲突已按用户确认的方案 B 消解。
- [x] Phase 4B changelog 新注记、`AI_CONTEXT.md` 和修改过的 `runbook.md` 已完整回读。
- [x] `git diff --check` 无 whitespace error（仅 LF→CRLF 提示）；本轮文档链接未新增无效目标。

## renewed finish-docs 执行清单

> 用户限定：只把 post-finish defect repair 精简补入 M44 章的“这次做了什么”、“有面试价值的亮点”和“面试官追问”，不改写其他小节。

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号。
- [x] “这次做了什么”的每个编号点都交代原问题/影响、概念、解法、取舍、证据与未证明边界（不适用项可省略）。
- [x] 每个编号点结构易读，无超过约 4 行或混合 3 个以上主题的大段。
- [x] 英文/代码术语首次出现时有就地解释。
- [x] 需要对照的数字优先用列表或表格。
- [x] 新概念已通俗解释，没有强行编造。
- [x] “代码阅读路线”按真实调用/数据流组织，说明为什么。
- [x] 有“设计要点”。
- [x] “有面试价值的亮点”有可背、可独立展开的高价值内容，不强行凑数。
- [x] 追问优先围绕亮点，无低价值凑数。
- [x] “验证与下一步”只引用 notes 中的真实验证快照。
- [x] 复制命令安全、可重复并标明前置条件。
- [x] 各小节使用适量加粗帮助扫读。

- 回读结果：按用户限定只改动上述三个小节；自检时修正了旧“repair 依赖模型 prompt”表述，对齐为最终 deterministic AST + private snapshot，并明确真实 repair 路径仍 inconclusive。
- 范围核对：finish-docs 阶段只修改 `docs/dev-log.md` 与本 notes，没有再改代码、state 或 history。`git diff --check` 无 whitespace error，仅有 Git LF→CRLF 提示。

## 2026-08-24 post-module exploratory E2E smoke（已结束，Gate failed）

- 身份边界：用户明确授权在 M44 收工后执行一条 T1→T5 真实产品链；本次标记为 `exploratory / baseline-ineligible / not-development-probe`，不倒填为开发期 Probe，也不是 Formal RAG suite。
- 运行范围：真实 FastAPI `/api/query` task、Qwen `qwen3.7-plus`、MySQL、business release、Response/JSONL Trace；只跑一个 canonical sequence，每 turn 首次一次，不碰 held-out、M46 sealed reserve、external full RAG Eval，不换模型/backend 或自动重跑。
- 运行预算：总 provider calls≤8、observed tokens≤30000；达到上限立即停止后续 turn，并保留已经发生的结果。
- 只读 preflight：`APP_ENV=local`、Qwen key 已配置、timeout 120s、22-entry business release `7d0d0937...409a` 可用。当前 `datapilot_dev` 只有 2026-07 completed refund `19920`，没有 8 月，不能直接验证 Phase 4B oracle，也未获得数据库 reset 授权。
- 数据适配：runner 在同一 MySQL 未提交事务中调用官方 phase4b profile append，API 五轮复用该 Session；无论成功失败都在 `finally` rollback，再用新连接比较运行前后数据库快照。它不 commit、不 reset、不修改默认配置；若恢复核对失败则单独以 exit 2 报警。
- 启动前验证：一次性 runner `.agent_work/temp/m44_post_module_smoke.py` 已通过 `py_compile`；当前尚未发生真实 provider 调用。
- 后台任务：PID `35020`；launcher `.agent_work/temp/run_m44_post_module_smoke.ps1`；stdout `.agent_work/temp/m44-post-module-smoke-20260824-01.stdout.log`；stderr `.agent_work/temp/m44-post-module-smoke-20260824-01.stderr.log`；exit `0`；完成标记与 artifact/Trace 均已生成。以上为任务结束后迁移的最终路径；Trace SHA-256 为 `05fa65b919033040a4d03ab60066e031f369c97196a857d54b3789f4928e6e59`。
- 最终用量：T1～T3 共 `8 provider calls / 32674 observed tokens`，所有 usage 可观察。最后一个已开始的 T3 response 使累计 token 越过 30000，按“保留已发生响应后停止”纪律未执行 T4/T5，也没有自动重跑。
- T1 pass：真实 API/Qwen/MySQL 返回 7 月 `120000`，`answer_ready`，2 calls / 5724 tokens。
- T2 fail：constraint delta 与旧 SQL Evidence invalidation 正常，但 Qwen 生成 MySQL 不支持的 `DATE_TRUNC`；真实 SQL Tool 将数据库错误记为 `safety_status=blocked/sql_execution_error`，而 Harness 方言分类只接受 `safety_status=passed`，所以没有进入已实现的 allowlisted repair，最终 `unrecoverable/sql_execution_error`。
- T3 fail：Controller 按预期选择两次有界 SQL Evidence action，但两次都被同类方言错误阻断；4 calls / 18582 tokens。T4 business Knowledge 与 T5 correction 没有形成真实证据，不能宣称通过或失败。
- 安全发现：真实 Trace 的 `tool_calls.message` 保存了底层数据库异常文本；API Response 代码路径投影同一未脱敏 `tool_calls`。这推翻了本 notes 早先仅基于 deterministic fixture 写下的“Action Observation 与 task Trace 已去除 raw DB error”判断，当前真实路径不满足 M44 C10/既有 Trace 合同。
- 数据库恢复：runner `finally` rollback 后，新连接复核运行前后均为 2026-07 30 rows / `19920`、Phase 4B 临时 refund rows=0，`database_restored=true`。
- 决策：本次结论为 `failed`，不是 inconclusive，也不倒填为开发期 Probe或登记正式基线。建议 M45 前另行授权聚焦修复真实错误分类/repair bridge 与 API/Trace 脱敏，再只重验受影响的 T2/T3。稳定报告见 `eval/reports/m44/m44-post-module-e2e-smoke-20260824-01.md`。

## Implementation checklist

- [x] M44-A：新增 additive B2 contract/identity、TaskState v2 与 closed-world Knowledge Runtime Resolver。
- [x] M44-B：实现 typed Requirement/Action/Budget/Consumption/EvidenceDelta/Progress/Termination 深合同。
- [x] M44-C：实现唯一 `run_agent_loop(...)` interface、确定性回边、实际 node Context 和稳定停止。
- [x] M44-D：实现 T3 Observation 驱动的原因→商品 SQL 动作链，以及 allowlisted 单次 SQL dialect repair。
- [x] M44-E：实现 T4 SQL→business Document Hybrid 与 T5 correction/invalidation/reauthorization。
- [x] M44-F：实现安全 Response/Trace 投影、Agent Scenario v3 和零 provider rehearsal。
- [x] M44-G：完成聚焦、前序兼容、legacy 与全仓 deterministic 验证，更新运行说明并技术收工。

## 已冻结实施边界

- G44-1～G44-4 均按用户确认的方案 A：服务端 runtime resolver、确定性 Controller、三次 Evidence action 父预算、独立最小 `sql_repair` purpose。
- M44 只完成 B2 顶层 Loop；不准入 B3 recovery action，不实现 B4 RAG Subgraph，不触碰 sealed reserve。
- 普通非 task RAG 保持 M44A Enterprise semantic 默认；task Document requirement 只能由服务端 typed scope 选择 business/external runtime。
- 本轮不自动运行真实 provider、RAG Eval、held-out/all 或 sealed reserve；设计确认不等于运行授权。

## 开工检查（2026-08-24）

- 已完整回读 `AGENTS.md`、`docs/state/runbook.md`、`docs/state/AI_CONTEXT.md` 和 `docs/notes/m44-plan.md` 至 EOF。
- 已读取 `codebase-design` skill：外部 seam 保持一个 `run_agent_loop` interface，复杂 Action/预算/进展/停止逻辑收进深 module；生产与 fake adapter 共用同一 seam。
- 工作区已有用户文档修改：`docs/state/AI_CONTEXT.md` 与未跟踪的 `docs/notes/m44-plan.md`；实施时保留且不覆盖。

## 过程记录

### 2026-08-24：开始实施

- 当前阶段：M44-A 调查与 contract/schema 设计。
- 待补读：Phase 4B roadmap/reference、Text2SQL/RAG 专项 runbook 与状态、Eval 基线、Phase 4B 历史索引和当前代码/测试。

### 2026-08-24：M44-A/B 首批合同落点

- 新增 B2 additive contract/manifest，content identity `a808b321...d485b`，predecessor 精确绑定 M43 B1 `383fbf51...e9d32`；Action、termination、双 knowledge scope 和 G44-3 方案 A exact budget 均 closed-world。
- 新增 `loop_contracts` 纯 typed 事实：EvidenceRequirement、BudgetProfile/Ledger、ResourceConsumption、EvidenceDelta、ProgressDecision、ActionAttempt、TerminationFact。Controller 后续只消费这些 interface，不逐个解析 SQL/RAG 私有实现。
- 新增 `knowledge_runtime` seam：registry 只接受 `business_release/external_profile`，resolver 只读取服务端 requirement scope；factory 异常或 scope 缺失直接 unavailable，不 fallback。
- 设计取舍：TaskState v2 将保留旧 `requirements` 字符串投影用于 M43 兼容，同时新增 typed `evidence_requirements` 作为 M44 authority；不改写 M42 v1/M43 v2 artifact。

### 2026-08-24：M44-C/D Loop 与 repair seam

- 独立 LangGraph Decision Loop 已落盘并通过语法编译；一次节点只执行一个 Evidence action，回边前由 typed requirement、依赖事实、duplicate key 与父预算重新裁决。
- SQL repair 新增独立 `sql_repair` outbound purpose；只接受稳定 issue code `mysql_unsupported_date_trunc` 和 candidate SQL，不传 raw DB error、rows 或 stack。repair 重新经过 QueryPlan validation、SQL fidelity、Guard、执行和 Evidence 构造。
- 真实 OpenAI-compatible client 的 token/request counter 以单次调用 delta 写入 Trace；没有 counter 的 fake 明确为 `observed=false`，避免把未知 token 当作 0。
- 阶段验证：相关模块 `py_compile` 通过；M31 governance + M25 Eval trustworthiness 共 22 tests passed。

### 2026-08-24：M44-E/F 纵向路径、同源投影与 v3

- task envelope 已改接独立 B2 Loop；legacy 非 task Harness 拓扑不变。API、JSONL Trace 与 Agent Scenario v3 均从同一 `TaskTurnResult/AgentLoopResult` 投影 action、budget、EvidenceDelta、progress、termination 和 runtime identity。
- T3 踩坑 1：原 period parser 对“2026 年 7 月和 8 月”只识别 7 月；现改为同句后续月份继承最近显式年份，并补齐“净退款增长”到已冻结指标。
- T3 踩坑 2：跨 turn 初始 coverage 原先忽略 TaskState 中 active Evidence，会重复执行 T2 的旧 requirement；现只把 active Evidence 所属旧 requirement 视为已覆盖，T3 当前 run 仍按 reason Observation 决定 product action。
- Budget 踩坑：最初把 SQL ledger stage 误计入 RAG candidate/selected/context 配额，导致 T4 文档动作执行前被阻断；现这些维度只由 RAG Observation 消费。Tool 实际超额时保留已发生 action/consumption 后立即 `budget_exhausted`，不从审计账本抹掉调用。
- Partial 踩坑：只找到 quality 政策时已有 EvidenceDelta，但 required basic key 未闭合；现明确 `budget_exhausted/required_coverage_incomplete`，且不重复同一 Knowledge query。
- 安全投影：Action Observation/node Context/Scenario artifact 去除 raw DB error/technical message、rows、正文、Prompt、stack、Thought；Hybrid Trace 清空完整 SQL rows。SQL 单路（含 task SQL）Trace 按用户确认的方案 B 沿用已有 Guarded rows 兼容投影；Document typed payload 只在同进程 Gate/Synthesizer 私有边界。
- Agent Scenario v3 对 run/contract/seed/caller/knowledge/policy identity、turn/action 顺序、duplicate key、EvidenceDelta、逐步 budget 守恒、termination、三态 assertion 与 private payload 做 closed-world 校验；M42 v1/M43 v2 validator 未改。
- 零 provider rehearsal：`python -m scripts.rehearse_m44_b2` 通过，external calls=0；Context v2 固化后的最终 artifact 为 `63c9483c8d55b958b48925085d99c9bb14164c1120a7d364c0b1c611dabac700`，T3/T4/T5、repair once、negative skip 共 6 checks passed。
- 聚焦验证：M44 + M43 task + v1/v2 artifact compatibility 共 34 tests passed；随后扩展聚焦集共 34 tests passed（最终完整矩阵见收工记录）。

## 模块名称与改动文件清单

- 模块：M44 / Phase 4B B2 顶层 Evidence-driven Bounded Decision Loop。
- 起始 commit：本轮没有单独创建或记录 module base commit；范围以开工时工作区事实、当前 `git status --short`、`git diff --name-only` 与未跟踪文件归并。开工前已有用户确认的 `docs/notes/m44-plan.md` 和 `AI_CONTEXT.md` 防遗忘账本修改，均保留并纳入 M44 文档范围。
- 组装/API/Trace：`AGENTS.md`、`app/api/query.py`、`app/main.py`、`app/schemas/agent.py`、`engine/trace/recorder.py`。
- B2/Task runtime：`engine/phase4b/{b2_contracts,loop_contracts,knowledge_runtime,agent_loop,task_runtime,task_turn}.py`、`domain_pack/phase4b/b2_contracts{,.manifest}.json`。
- Text2SQL/既有 Harness：`engine/governance.py`、`engine/harness/{adapters,contracts}.py`、`engine/nl2sql/{generator,llm_call,pipeline}.py`。
- Eval/rehearsal/tests：`eval/agent_scenario_v3_contracts.py`、`eval/reports/m44/*`、`scripts/rehearse_m44_b2.py`、`tests/test_m44_{b2_contracts,agent_loop,agent_scenario_v3,api_trace}.py`。
- 文档/状态：`docs/notes/m44-{plan,notes}.md`、`docs/state/{runbook,AI_CONTEXT,eval-baselines,rag-current-state}.md`、`docs/state/change-history/phase4b.md`。

## 关键决策与取舍

- G44-1：用户选 A。普通 API 保持 M44A Enterprise semantic；task requirement 由服务端 closed-world resolver 在 business/external 中选择。风险是双 runtime identity/ACL 必须闭合；缺失时失败关闭，不 fallback。
- G44-2：用户选 A。首版 next Action 完全确定性，decision model calls/tokens=0。未选的结构化模型 proposal 方案 B 已按用户要求写入 `AI_CONTEXT` 防遗忘账本，只有稳定 paraphrase 失败簇和重新授权才能重开。
- G44-3：用户选 A。最多 3 Evidence actions / 3 deep Tools、1 Knowledge action、每 requirement 1 repair、6 model calls、24000 observed tokens。风险是复杂链保守停止；不为尚不存在的动作扩大预算。
- G44-4：用户选 A。新增独立最小 `sql_repair` outbound purpose；prompt 仅含当前 question、MySQL、稳定 issue code、safe candidate SQL 和输出格式，不外发 Schema/metric/join、raw DB error、rows 或 stack。repair 仍重走 QueryPlan validation、SQL fidelity、Guard 和执行。
- 深 module 取舍：外部仍只有一次 task turn / 一次 `run_agent_loop` invoke；Controller、Action、Budget、Progress 与 termination 收进内部。借鉴参考项目的 conditional edge/dispatcher/去重思想，不照搬 LLM 自由 tool call、字符串 Observation、平台级 PlanExecutor 或框架 recursion limit 预算。

## 阶段 1 注释小结

- 完整审查 18 个本模块 Python 代码文件，共扫描 285 个 class/function 符号；AST 初检列出 34 个无 docstring 的 public 名称，补写 12 处后剩 22 处，均为简单 `safe_projection`/property、Protocol method、局部 lifespan closure 或本轮未改的既有简单治理方法，符合豁免条件。
- 深化内容：确定性 Controller 为什么独占 next action、token usage 为什么区分 observed/unknown、实际消费超额为什么仍保留账本、SQL repair 为什么不携带 Schema/raw error、Context v2 为什么同时冻结 allowlist/field/token budget。
- 修正过时注释：task turn 从“固定一次 Harness”改为“一次 agent Loop”；clarification/cancel 只投影实际执行的 understanding/controller Context，不再预生成 route/SQL Context。
- 仍缺失：无非豁免缺失；未为简单投影函数机械堆叠注释。

## 阶段 2 验证快照（后台全仓前 checkpoint）

- `py_compile` / `compileall -q`：B2、Text2SQL repair、API/Trace、Eval/rehearsal 模块通过；无语法错误。
- `pytest ... test_m31_governance.py test_m25_eval_trustworthiness.py -q`：22 passed，验证新增 outbound rule 未放宽既有 exact-match deny。
- 多轮 M44 聚焦修复后，代码冻结命令覆盖 M44 合同/Loop/v3/API、M42 v1、M43 v2/task、M44A API、M31 governance、M35 SQL adapter：57 passed，1 个既有 Starlette `httpx` deprecation warning；warning 不影响本模块。
- `python -m scripts.rehearse_m44_b2`：passed=true、6/6 checks、external_calls=0，artifact `63c9483...ac700`。
- `git diff --check` 与 `compileall -q` 在代码冻结点通过；技术档案写入后已再次通过，路径存在性检查也全部为 true。
- 一次扩大 Text2SQL/Phase 回归前台运行耗时超出预期，因工具未返回完整 exit/summary而不计为验证通过；为严格避免无法证明的 provider 边界，曾预防性停止其中一条 pytest 进程。随后定点检查测试源码确认相关用例使用 fake client，没有证据表明发生真实 provider 调用。最终完整回归将按 AGENTS 后台规则记录日志/exit/done。

## 参考资料

- `docs/phase4-reference.md` 与 roadmap reference 要求；定点复核 ARAG `graph.py/edges.py/graph_state.py/nodes.py` 的 conditional edge、计数与去重，DataAgent `DataAgentConfiguration.java/PlanExecutorDispatcher` 的显式 dispatcher/repair 回边，以及 LangGraph Graph API 的 `Runtime` context、conditional edge、recursion limit。
- 借鉴：typed state 驱动回边、固定 dispatcher、执行 key 去重、实际 Context 留痕。
- 不照搬：LLM 自由 action/tool call、字符串 Tool output、压缩/fallback answer、Java 平台大状态、人审/Python executor、把 recursion limit 当业务预算。

## Handoff

### 已完成且可依赖

- B2 contract identity `a808b321...d485b`、TaskState v2、typed requirement/action/budget/progress/termination、Knowledge Runtime Resolver 和独立 agent-family LangGraph Loop。
- T3 reason Observation→product action、T4 business SQL→Document Hybrid、T5 correction/invalidation/reauthorization、allowlisted DATE_TRUNC repair once，以及 no-progress/budget/unsafe/unavailable/unrecoverable/contract failure 停止语义。
- API/Trace/v3 同源安全投影、actual-node Context v2、零 provider v3 rehearsal；M42 v1/M43 v2 validator 与 legacy Harness 未改写。

### 未完成与风险

- M44 未实现 B3 recovery action admission、B4 RAG Subgraph、B5 durable state 或 B6 Compact；不能宣称 Agentic RAG/B4/Phase 4B 完成。
- 未运行真实 SQL repair showcase、真实 RAG Eval、held-out/all 或 sealed reserve；deterministic fake/fixture 证明控制合同，不证明真实模型或 36,417 文档质量。
- 业务首次检索漏 basic 的真实失败仍保留；B2 只会正确 partial/budget stop，不做 rewrite/parent expansion。

### 必须延续的边界与决策门

- G44-1～G44-4 方案 A 与 M46 reserve sealed 继续生效；任何模型 decision proposal、父预算放宽、新 repair 字段/用途、runtime fallback 或真实 provider 运行都需满足 plan 重开门并重新取得对应授权。
- 普通非 task Enterprise semantic 与 task business/external resolver 必须继续分账；不能用自然语言、请求字段或“开发方便”选择 corpus/backend。

### 下一模块入口与必读指针

- 下一模块建议 M45/B3 从 `engine/phase4b/agent_loop.py` 的 document Observation/termination、`engine/phase4b/loop_contracts.py` 的 parent budget/EvidenceDelta，以及 M42 business 漏选与 M44A external semantic retrieval failures 开始。
- 必读：`docs/phase4b-roadmap.md` B3、`docs/phase4-reference.md` action-level Evidence/review point、`docs/state/{AI_CONTEXT,rag-current-state,eval-baselines}.md`、M44 plan/notes 与 `eval/reports/m44/`。M45 只诊断并准入 action card，不提前实现 B4 子图。

## State impact（阶段 4 最终）

- 已更新：`docs/state/runbook.md`（B2 task/repair/rehearsal/Trace 入口）、`AI_CONTEXT.md`（当前模块、默认 Loop/runtime、验证、路线与活跃坑）、索引指定的 Phase 4B changelog、`eval-baselines.md`（v3 deterministic artifact，不登记质量基线）、`rag-current-state.md`（task resolver 与普通 Enterprise 默认分账）。
- 已完整复核且无需修改：`database-current-state.md`（只消费既有 Phase 4B oracle，未改 schema/seed/指标）；已检查且未命中：`schema-retrieval-milvus-embedding.md`（未改 embedding/Milvus/Schema Retrieval 默认）。

## 后台完整回归启动前 checkpoint

- 关键决策与代码范围：已冻结，见上文；没有待用户确认的合同变化。
- 已完成验证：最终聚焦 57 passed；rehearsal 6/6、external calls=0；compile/diff 静态检查已阶段通过。
- 已知风险：完整回归预计超过 2 分钟；尚未获得带 exit code 的最终全仓结果，M44-G 和 finish-module 均不得标完成。
- 待完成：按后台规则运行全仓 deterministic pytest，检查 log/exit/done；随后完成 state/changelog 更新、完整回读、最终 diff/link 检查。

### 后台任务指针

- 状态：已结束并复核通过。
- 命令脚本：`.agent_work/temp/run_m44_full_pytest.ps1`。
- PID：`63628`。
- pytest 日志：`.agent_work/temp/m44-full-pytest.log`。
- 退出码：`.agent_work/temp/m44-full-pytest.exit`（任务结束后生成）。
- 完成标记：`.agent_work/temp/m44-full-pytest.done`（任务结束后生成）。
- 检查方法：确认 done/exit 均存在且 exit 为 `0`，再读取日志末尾的 passed/skipped/warning 摘要；失败时先定位失败用例，不直接重跑全仓。

### 后台完整回归结果（2026-08-24）

- done：`2026-08-24T04:44:28.5699683+08:00`；exit：`0`。
- 结果：`539 passed, 1 warning in 599.47s (0:09:59)`；warning 为既有 Starlette TestClient/httpx deprecation，不阻塞 M44。
- 本结果覆盖 legacy、M42/M43/M44A、M44 B2 与既有 Phase 3/4 回归；未触发真实 provider、RAG Eval、held-out 或 sealed reserve。

## finish-module 技术档案交付清单

- [x] 注释审查与豁免说明已记录。
- [x] 聚焦、兼容、rehearsal、全仓验证证据已记录。
- [x] `CHANGELOG_INDEX.md` 已先读，M44 模块档案已写入其指定的 Phase 4B 历史文件。
- [x] `AI_CONTEXT.md`、`eval-baselines.md`、`rag-current-state.md` 已同步；数据库专项状态已复核为无需修改。
- [x] M44 最终能力边界、遗留项、下一模块入口和必读指针已写入 Handoff。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代原问题/影响、概念解释、解决方式、取舍、验证证据和未证明边界中的适用项。
- [x] 每个编号点用独立结论句和短段或 `- **小标题**：` 拆分，没有无断点大段。
- [x] 正文英文/代码术语首次出现时有括号或就地解释。
- [x] 需要对照的数字使用列表或表格呈现。
- [x] 新概念已用通俗语言解释，没有强行编造。
- [x] “代码阅读路线”按真实调用或数据流组织，并解释为什么这样协作。
- [x] 有“设计要点”。
- [x] “有面试价值的亮点”可背、可独立展开且没有强行凑数。
- [x] 追问优先围绕亮点，包含真实工程压力且没有低价值问题。
- [x] “验证与下一步”只引用 notes 的真实验证快照。
- [x] 复制命令安全、可重复并标明前置条件。
- [x] 各小节使用适量加粗帮助扫读，没有整段加粗。
- [x] 已完整回读 M44 新增章节，并以第一次阅读者视角复核可读性。
- [x] 本阶段只修改 `docs/dev-log.md` 和 `docs/notes/m44-notes.md`，未改技术档案或代码。
- [x] `git diff --check` 通过。

### finish-docs 检查结果

- Track A 模块记录交付门全部通过；新增章节为 `★ M44 Phase 4B B2：让 Agent 根据证据连续行动，但始终有预算和刹车`。
- 第一次完整回读后补写了两类缺口：给 API/RAG/Harness 等首次出现术语增加就地解释；为多动作、预算、runtime resolver 和 SQL repair 四个核心编号补上对应验证锚点。
- 数字只取自本 notes 和已完成技术档案：57 passed、rehearsal 6/6 且 external calls=0、全仓 539 passed / 1 warning / 599.47 秒；没有在 finish-docs 阶段新跑模块验证。
- finish-docs 阶段只编辑 `docs/dev-log.md` 与本 notes；`AI_CONTEXT.md` 和 Phase 4B changelog 的现有修改均来自先行完成的 finish-module，没有在本阶段继续改写。

## finish-module 技术档案交付清单（renewed 最终索引）

- [x] post-finish repair 的最终范围、关键决策、注释审计、验证快照、Probe 时间线、参考资料、State impact 与 renewed Handoff 已固化。
- [x] `CHANGELOG_INDEX.md` 路由、Phase 4B history、`AI_CONTEXT.md` 与命中的 `runbook.md` 已完整核对；方案 B 已消解 Trace rows 文档/代码冲突。
- [x] 全仓 `553 passed, 1 warning`、G4 Probe `4 calls / 15762 tokens` passed、收工精确复核 `8 passed, 1 warning`；`git diff --check` 无 whitespace error。
- [x] 无 `development_probe_missing`，无 Formal Eval/基线混算，数据库已 rollback，RAG/runtime 默认未改。

## finish-docs 执行清单（renewed 最终索引）

- [x] 仅在 M44 章“这次做了什么”、“有面试价值的亮点”和“面试官追问”精简补充后续修复，符合用户限定。
- [x] 已完整回读修改区间并通过 Track A 交付门；数字、能力边界、未证明 repair 路径均与 renewed notes/state 一致。
- [x] finish-docs 阶段只修改 `docs/dev-log.md` 与本 notes；没有新跑模块验证或改写 state/history。
- [x] `git diff --check` 无 whitespace error（仅 LF→CRLF 提示）。
