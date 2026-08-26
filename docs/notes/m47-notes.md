# M47 Phase 4B B5 Durable Task State 开发记录

> 模块 plan：`docs/notes/m47-plan.md`
>
> 范围：完整交付 B5 的 MySQL/InnoDB durable task boundary、存储层 CAS、restart/multi-worker、TTL/clear/tombstone、typed event ledger 与 Agent Scenario v5；不提前实现 M48/B6 Context Compact。

## Implementation checklist

- [x] M47-A：冻结 additive B5 machine contract、durable runtime/schema/lifecycle identity、兼容矩阵与 Agent Scenario v5 skeleton；M42～M46 artifact 只读。
- [x] M47-B：实现 closed-world TaskState codec、payload size/禁存门、adapter-neutral boundary protocol、typed boundary event 与 in-memory parity。
- [x] M47-C：实现 Alembic/ORM checkpoint + event schema、MySQL durable adapter、CAS/fencing、原子 switch、TTL/clear/tombstone/purge 与 storage failure。
- [x] M47-P1（after M47-C / before M47-D）：在独立 `datapilot_m47_test` 上验证真实 MySQL 两 session 唯一 claim、commit/switch/TTL/clear/purge；只有 `continue` 放行 M47-D。
- [x] M47-D：接入产品 durable 默认、恢复时 caller/tenant/active role 与 Evidence validity 重核、fail-closed API/Trace；test 明示 memory adapter。
- [x] M47-E：建立 restart/multi-worker/duplicate/in-flight crash 纵向 harness。
- [x] M47-P2（after M47-E / before M47-F）：进程 A T1→退出→进程 B T2，并验证 worker 竞争、重复请求、role/tenant/clear；只有 `continue` 放行 M47-F。
- [x] M47-F：实现 additive Agent Scenario v5、零 provider rehearsal、required Gate 与 v1～v4/legacy compatibility view。
- [x] M47-G：按 `finish-module` 完成注释审计、聚焦/受影响/全仓验证、migration 检查、notes/state/changelog 与 M48 handoff。

## 开工基线与已确认决策

- 起始 commit：`db0c14548d1f3a6fd270560fd0440108e4a35493`（`db0c145 m46accept`）。创建 notes 前工作树只有未跟踪的 `docs/notes/m47-plan.md`，属于本模块已确认计划。
- G47-1 已于 2026-08-26 确认方案 A：MySQL/InnoDB snapshot + typed event ledger；产品 agent task 默认 durable，测试显式 memory；active TTL 900 秒；clear/terminal/expiry 立即 scrub payload；最小 tombstone 24 小时后 bounded purge；不新增应用层加密。
- G47-2 已于 2026-08-26 确认方案 A：真实 P1/P2 只使用独立 `datapilot_m47_test`，允许 M47 migration、synthetic checkpoint/event、计划内并发/重启验证和精确数据清理；禁止改写 `datapilot_dev`、seed/reset、业务表、active release、historical/reserve。
- G47-3 仅在 M47-B 发现当前合法 TaskState v2 无法 closed-world 无损 round-trip 时触发；未触发不得建设猜测迁移。
- M46 Pipeline 默认/Subgraph experimental/no-auto-fallback 与 reserve sealed/read0/not-run 均保持不变；B5 只恢复 committed task boundary，不恢复 Graph/RAG Subgraph program counter。

## 预注册 Live Dev Probe

| ID | 时点与阻塞关系 | 场景与真实依赖 | 额度、禁区与证据落点 |
|---|---|---|---|
| M47-P1 | after M47-C、before M47-D；仅 `continue` 放行产品组装 | 两个独立 SQLAlchemy session/adapter 竞争同一 version，随后验证 commit、switch rollback、TTL、clear/purge；真实 MySQL/InnoDB | 零 LLM/embedding/RAG/业务 SQL，provider calls=0、tokens=0；只写 `datapilot_m47_test` synthetic checkpoint/event；结果写本 notes 与 `.agent_work/temp/m47/probe-p1/` |
| M47-P2 | after M47-E、before M47-F；仅 `continue` 放行 v5 artifact 冻结 | 进程 A 经 `/api/query` 提交 T1 后退出，进程 B 从同库继续 T2；两个 worker 竞争同 version，并覆盖 duplicate/role/tenant/claimed crash/clear | deterministic SQL Tool + 既有 120000/180000/60000/0.5 oracle；provider calls=0、tokens=0；不得访问业务表/remote provider/reserve；结果写本 notes 与 `.agent_work/temp/m47/probe-p2/` |

两项 Probe 均为 `exploratory / baseline-ineligible` 开发证据，不是 Formal Eval。执行前必须在本 notes 追加当时代码阶段、HEAD/dirty、精确连接目标（不含凭据）、命令、前后行数/清理断言和停止条件；执行后立即记录三态与 `continue/revise/stop`，不得在 M47-G 首次补跑。

## 开发过程记录

### 2026-08-26：启动

- 已完整读取 `finish-module` skill、M47 plan、`AI_CONTEXT.md` 与 `runbook.md`；此前计划调查已完整读取 `AGENTS.md`、Phase 4B roadmap/reference、数据库 state、Phase 4B changelog、M43/M46 notes 及相关 DataPilot/参考项目源码。
- 初步 State impact：必然命中 `runbook.md`（task durable 默认、Probe/maintenance 入口）、`database-current-state.md`（ORM/Alembic 与物理表数量）、`eval-baselines.md`（Scenario v5 deterministic artifact，非质量基线）；RAG state 只继承 Evidence/ACL 与 M46 rollout，预计检查后无需修改；Schema Retrieval/Milvus/embedding 不命中。

### 2026-08-26：切片 A–C 完成，等待 P1

- 新增内容绑定 B5 合同、严格 TaskState v2 codec、checkpoint/event ORM 与 Alembic `20260826_0004`、MySQL/SQLAlchemy CAS adapter；确定性聚焦测试 `5 passed`。
- codec 不复用面向 API 的 `safe_projection()`，因为后者有意省略 `owner_ref` 与 EvidenceRequirement 的可执行 `query`；改用独立 closed-world payload，并对任意嵌套对象递归拒绝 forbidden key。当前合法 TaskState v2 可严格 round-trip，G47-3 条件未触发。
- 踩坑与修正：最初在 claim 数据库事务内完成过期擦除后立即抛 `task_expired`，异常会使事务回滚。现改为事务提交擦除与 event 后再向调用方抛稳定错误；回归测试已覆盖。
- 验证：`pytest tests/test_m47_b5_contracts.py -q`，证据目录 `.agent_work/temp/m47/pytest-abc-r4-approved/`，结果 `5 passed in 0.62s`。
- P1 放行前状态：切片 C 已完成，D 尚未开始；下一步只在独立 `datapilot_m47_test` 验证真实 MySQL migration、跨 adapter resume/CAS、清理与错误映射。

### M47-P1 执行前登记（2026-08-26）

- 当时代码阶段：A–C 完成，D 未开始；HEAD `db0c14548d1f3a6fd270560fd0440108e4a35493`。dirty 仅含 M47 plan/notes、B5 contract/codec/boundary/model/migration/probe/test 与 `app/db/base.py`。
- 连接目标：`mysql+pymysql://root@127.0.0.1:3306/datapilot_m47_test`（凭据不记入证据）；明确不连接 `datapilot_dev`。
- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\probe_m47_mysql_boundary.py`。
- 数据边界：若空库则仅 stamp 到 `20260722_0003` 后执行 M47 `20260826_0004`，允许表只有 `alembic_version`、`agent_task_checkpoints`、`agent_task_events`；运行前后清空两张 M47 表，禁止创建或访问 14 张业务表。
- 代码快照：B5 contract 36 行，Probe 113 行。停止条件：目标库名不匹配、出现额外表、并发非唯一胜者、switch 非原子、payload 未擦除、bounded purge 异常或 storage error 未 fail-closed 时一律 `revise/stop`，不得进入 D。

### M47-P1 结果（2026-08-26）

- 首次启动在 import 阶段失败：既有 `app.models.__init__` 集中导入模式要求先加载 `app.db.base`，直接导入新 model 触发 partial-init circular import；没有连接或写入数据库。已修正 durable adapter/Probe 的导入顺序后原命令重跑。
- 三态结果：`continue`。真实 MySQL/InnoDB 只出现 `alembic_version`、`agent_task_checkpoints`、`agent_task_events`；双 adapter 同 version 竞争结果为唯一 `won` + `task_not_active`；跨 adapter commit、switch 故障回滚、expiry scrub、clear scrub、24h 后 bounded purge 全部通过。
- 行数与清理：清理前 synthetic checkpoint/event 为 `4/6`，清理后 `0/0`；provider calls=`0`、tokens=`0`。结构保留在独立 `datapilot_m47_test` 供 P2，未触碰业务库/业务表/release/reserve。
- 证据：`.agent_work/temp/m47/probe-p1/result.json`。P1 已按时点放行 M47-D。

### 2026-08-26：切片 D–E 完成，等待 P2

- 产品组装默认切换为 `MySQLTaskBoundary`；新增独立 task TTL/retention/max-bytes 配置。memory backend 仅允许 `APP_ENV=test` 显式选择，既有测试仍可直接注入 memory seam。
- `run_task_turn` 现在把 resolver 的 active role 传入每次 lifecycle 操作，并写入不含 question/answer/rows 的 typed event 摘要；API/Trace 从同一个 boundary runtime/lifecycle fact 投影，storage/schema 失败保持稳定 fail-closed reason。
- 建立跨 app SQLite 确定性 restart 测试与真实 MySQL 跨进程 rehearsal 脚本。受影响聚焦回归先发现两处测试断言误把 Trace-only 字段当作 Response 字段，修正为读取 JSONL Trace；最近复验 `5 passed`。更早整组结果除该测试断言外为 `26 passed`，实现链无失败。

### M47-P2 执行前登记（2026-08-26）

- 当时代码阶段：A–E 完成，F 未开始；HEAD `db0c14548d1f3a6fd270560fd0440108e4a35493`。dirty 为 M47 实现/测试/文档及受影响的 config/main/query/task turn、M43 expiry parity 测试，没有无关用户改动。
- 连接目标：`mysql+pymysql://root@127.0.0.1:3306/datapilot_m47_test`（不记录凭据）；P1 已确认该库只有 Alembic/M47 两张表。
- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe scripts\rehearse_m47_b5.py full`；rehearsal 脚本 147 行。
- 场景：process A T1 写盘并退出；process B T2 恢复；两个独立 app/engine 竞争同 version；重复旧 version、role/tenant 错配、claimed crash、clear scrub；固定 SQL oracle 120000/180000/60000/0.5。
- 停止条件：跨进程未恢复、超过一个 worker 深执行、错误 owner 可枚举、claimed 被自动重放、clear 未擦除、出现 provider/业务 SQL 调用或清理后 synthetic 行非零则 `revise/stop`，不得进入 F。

### M47-P2 迭代记录（2026-08-26）

- 首轮判定：`revise`（不是实现失败）。process A/B restart-resume 成功，worker 竞争也实际产生一个 `task_not_active`；但脚本把胜者 reason 错误冻结为 `sql_completed`。由于 T2 已有 active comparison Evidence，胜者合法地由 controller 以 `comparison_observation_missing` 收敛且不再调用 Tool。
- 修正：并发门改为核对“恰好一个非拒绝胜者 + 两份 Trace 的 `task_runtime_invocation_count` 合计为 1”，不把重复 SQL 调用误写成 durable boundary 合同。首轮在断言处退出，未执行后半控制场景与最终清理；重跑开头会先精确清空 M47 两张表，再完整执行，F 仍未开始。
- 第二轮仍为 `revise`：CAS loser 的稳定安全结果受调度影响——若在胜者 commit 前观察到 `claimed` 则为 `task_not_active`，若在 commit 后观察到更高 active version 则为 `task_version_conflict`；两者都满足 closed-world 单胜者语义。另发现 worker Trace 文件跨轮追加会污染次数统计。脚本现接受这两个合法 loser reason，并在每轮并发前删除本轮 worker Trace；实现合同未改。
- 第三轮在已通过 restart/worker 后停于 role fixture：脚本误用了项目 closed-world catalog 不存在的 `finance`，在构造 caller 时即安全拒绝；改为已注册的第二角色 `admin`。这属于 Probe fixture 修正，未改变 active-role 绑定合同；下一轮仍会先清空前轮 synthetic 行。

### M47-P2 结果（2026-08-26）

- 第四轮三态结果：`continue`。process A version 1 写盘退出，process B 从同库恢复并提交 version 3；两个独立 app/engine 竞争只产生一个 runtime 胜者，loser 为 `task_not_active`；重复旧 version 为 `task_version_conflict`。
- role/tenant 错配统一 `task_unavailable`；claimed crash 经新 adapter 访问保守停在 `task_not_active`，未自动重放；clear payload scrub 通过。provider calls=`0`、tokens=`0`。
- 行数与清理：最终轮清理前 checkpoint/event=`4/7`，清理后 `0/0`。证据 `.agent_work/temp/m47/probe-p2/result.json` 及同目录 process/worker/controls Trace。P2 已按时点放行 M47-F。

### 2026-08-26：切片 F 完成

- 新增 additive Agent Scenario v5，完整覆盖 `RESTART_RESUME / MULTIWORKER_CONFLICT / WRONG_OWNER / EXPIRED / CLEAR / SWITCH`，并明确 v1–v4 `unchanged_readable`；artifact 递归拒绝 raw task id、state payload、question/answer/rows/prompt/token/credential/secret。
- Scenario v5 + B5/runtime 聚焦 Gate：`12 passed`；零 provider rehearsal identity `7132ce661301fdfee84a823bccadde1c2fcfe7f9f4309bb5860a003389dd2e55`，6 cases，报告 `eval/reports/m47/m47-agent-scenario-v5-rehearsal.json`。
- rehearsal 首次因 `eval/` 是 namespace package 且直接脚本启动未把项目根加入 `sys.path` 而失败；补齐与既有 smoke 脚本相同的项目根 bootstrap 后通过，不涉及 artifact/runtime 合同变化。

### 2026-08-26：收工前 lifecycle 审计补强

- 注释/边界审计发现 claimed crash 虽会立即安全停止，但若之后无人访问，原实现不会自动转成可 purge tombstone；这会让敏感 state payload 超过 TTL 留存。补充 bounded `expire_stale()`：active/claimed 到期均条件更新为 expired、立即 scrub、按原 expires_at 计算 24h purge，并写 typed event。
- 为让 maintenance event 与 API/Trace 使用同一不可逆引用，checkpoint 新增 `task_safe_ref`；claim 胜者也写 `task_claimed` event。B5 合同/identity 相应更新，顶层 task Trace 改为 B5 identity，父 Loop 的 B2/B4 identity 继续保留在 `agent_loop`。
- 这是已确认 TTL/typed ledger 核心合同的完整实现，不改变 plan 范围或用户决策。由于发生在 P1/P2 后，将在进入最终验证前重跑真实 P1/P2；独立测试库的未发布 0004 会先 downgrade 到 0003 再按最终 migration 重建，仅影响 M47 两张空测试表。

### 2026-08-26：最终验证前 checkpoint

- 最终关键设计：MySQL product default；memory 仅 test 显式；owner/tenant/active-role + version + single-use claim token + TTL 共同参与数据库 CAS；terminal/expiry 立即 scrub；24h tombstone 后 bounded purge；claim/commit/switch/expiry 均写 typed event；in-flight 不自动重放。
- 最终改动范围：B5 machine contract/strict codec/protocol；checkpoint/event ORM 与 0004 migration；MySQL adapter/maintenance；产品组装、API active-role 与 Trace B5 identity；restart/multi-worker harness；Scenario v5/Gate/report；M43/M46 additive compatibility assertion。未改业务表/seed/RAG rollout/reserve/M48 Context Compact。
- 最终 Probe：P1=`continue`，加入 expired claim commit fencing 后 checkpoint/event 清理前 `5/13`、清理后 `0/0`；P2=`continue`，A/B version `1→3`、单 worker winner、loser `task_version_conflict`、清理前 `4/11`、清理后 `0/0`；两者 provider/tokens 均 `0/0`。
- 已完成验证：最终 lifecycle 聚焦 `27 passed`；TTL fencing 聚焦 `12 passed`；Phase 4B 受影响集合已无失败；Scenario v5 6 cases、identity `c1ad1663...000af`；`compileall`、`git diff --check` 通过；临时 SQLite metadata 的 Alembic `current=20260826_0004(head)`、`check=No new upgrade operations detected`。
- 注释审计：M47 12 个主要 Python 文件、112 个 class/function symbol；8 个无 docstring 项均为 `TaskBoundaryPort` Protocol 声明，其余缺失 0。新增/大改实现均有中文职责、关键安全边界和必要 ★/步骤说明。
- 已知风险：`datapilot_dev` 按用户禁区未执行 0004，部署前必须正常运行 migration；现有 Starlette/httpx deprecation warning 非 M47 引入。待完成：后台全仓 pytest、最终 notes/state/changelog 固化与 handoff。
- 后台全仓 pytest 已启动，PID=`33904`；命令为项目 Python `-m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m47/pytest-full-final/pytest-temp`。日志 `.agent_work/temp/m47/pytest-full-final/pytest.log`，退出码 `.agent_work/temp/m47/pytest-full-final/exit-code.txt`，完成标记 `.agent_work/temp/m47/pytest-full-final/done.marker`。当前状态：**运行中，待检查**；未提前记录为验证通过或模块完成。
- 后台首轮包装失败：exit=`4`，pytest 报 `basetemp must not be empty, current working directory or parent`，确认是 PowerShell 把 `--basetemp=(Join-Path ...)` 错误传参；尚未收集/执行任何测试，不属于代码失败。已改为先解析绝对 `$baseTemp`，再以单个 `--basetemp=<absolute>` 参数传入，并在新运行前删除旧 exit/done marker。
- 修正后后台全仓 pytest 已重新启动，PID=`18276`；日志/退出码/完成标记路径不变。当前状态仍为**运行中，待检查**，finish-module 与 finish-docs 均未完成。

## 关键决策与取舍

- 用户在计划阶段对全部决策门选择方案 A：产品默认使用 MySQL/InnoDB snapshot + typed event ledger，测试必须显式选择 memory；active TTL 900 秒，terminal/clear/expiry 立即 scrub，最小 tombstone 保留 24 小时后 bounded purge，不新增应用层加密。原因是它复用项目既有数据库底座，同时能用数据库受影响行数形成跨 worker CAS 证据；风险是部署前必须执行 0004 migration，MySQL 不可用时产品 task API 会失败关闭。未采用 Redis/分布式锁、LangGraph saver 或应用内伪 CAS，因为它们分别扩大基础设施、恢复了错误层级的状态，或不能证明跨进程唯一胜者。
- 用户确认真实 Probe 只使用隔离库 `datapilot_m47_test`；禁止改写 `datapilot_dev`、业务表、seed/release/reserve。该选择牺牲了对本机开发库已迁移的证明，换取对业务数据零扰动；因此 `datapilot_dev` 仍需在后续实际部署/启动前按 runbook 正常升级到 0004。
- G47-3 未触发：当前合法 TaskState v2 可由 closed-world codec 无损 round-trip，所以没有建设猜测迁移框架。in-flight crash 采用保守停止、不自动重放 Tool；这是避免把外部副作用误称 exactly-once 的安全选择。

## 参考资料

- 计划调查已定点复核 DataAgent saver/GraphService 接线、ARAG `InMemorySaver + interrupt_before` 反例，以及 MySQL InnoDB locking/SQLAlchemy transaction 与 rowcount 官方文档。借鉴 adapter seam、短事务、存储层条件更新和显式 release；不照搬 Graph program counter、应用层伪 CAS、长事务、`SKIP LOCKED` 或 saver 存在即宣称安全持久化。

## Handoff

- **已完成且可依赖**：B5 durable task state 已形成完整纵向链。产品默认 `MySQLTaskBoundary`；TaskState v2 有 closed-world codec；checkpoint/event 表、0004 migration、owner/tenant/active-role/version/single-use claim token/TTL CAS、原子 switch、即时 payload scrub、24h tombstone 与 bounded expiry/purge 已实现。API 与 Trace 共用 B5 runtime/lifecycle identity；Agent Scenario v5 六类安全场景可离线复演。M42～M46 artifact 继续可读，M46 Pipeline 默认/Subgraph experimental/reserve sealed 不变。
- **未完成与风险**：没有证明任意外部 Tool exactly-once、生产认证、吞吐/压测或跨地域容灾；claimed 崩溃故意不自动重放。`datapilot_dev` 按用户禁区没有执行 0004，真实产品启动前必须迁移。M47 的 deterministic Scenario/Probe 是控制与安全证据，不是 Agent 答案质量 Formal Eval；本轮不建议为 B5 追加付费 Formal Eval。
- **必须延续的边界与决策门**：禁止把 rows、Document 正文、答案、Prompt、凭据、Thought 或 Graph/RAG program counter 写入 durable payload；memory 只能在 `APP_ENV=test` 明示使用；owner/tenant/active role、Evidence validity 和 schema identity 继续失败关闭。若未来要自动重放 claimed turn、更换 Redis/分布式锁、改变 TTL/保留、增加应用层加密或迁移历史 state family，必须另立计划并经用户确认。
- **下一模块入口与必读指针**：M48/B6 应先从 `docs/phase4b-roadmap.md` 的 B6、`docs/notes/m47-plan.md` C2/C6、`engine/phase4b/task_state_codec.py`、`engine/phase4b/mysql_task_boundary.py`、`eval/agent_scenario_v5_contracts.py` 与 `tests/test_m47_b5_contracts.py` 开始；只消费 durable typed event/checkpoint identity，不能恢复子图 program counter，也不能把无界聊天历史塞回 checkpoint。

## 模块名称与改动文件清单

- 模块：M47 Phase 4B B5 Durable Task State。起始 commit 明确为 `db0c14548d1f3a6fd270560fd0440108e4a35493`，期间无模块提交；最终范围由起始 commit、工作树状态与未跟踪文件归并。
- 合同与 runtime：`domain_pack/phase4b/b5_contracts.json`、`domain_pack/phase4b/b5_contracts.manifest.json`、`engine/phase4b/b5_contracts.py`、`engine/phase4b/task_state_codec.py`、`engine/phase4b/mysql_task_boundary.py`、`engine/phase4b/task_boundary.py`、`engine/phase4b/task_turn.py`。
- 数据库与应用接线：`alembic/versions/20260826_0004_m47_durable_task_state.py`、`app/models/agent_task_checkpoint.py`、`app/db/base.py`、`app/core/config.py`、`app/main.py`、`app/api/query.py`。
- Eval、脚本与报告：`eval/agent_scenario_v5_contracts.py`、`eval/reports/m47/m47-agent-scenario-v5-rehearsal.json`、`scripts/probe_m47_mysql_boundary.py`、`scripts/rehearse_m47_b5.py`、`scripts/rehearse_m47_agent_scenario_v5.py`。
- 测试与兼容：`tests/test_m47_b5_contracts.py`、`tests/test_m47_api_runtime.py`、`tests/test_m47_agent_scenario_v5.py`、`tests/test_m1_models.py`、`tests/test_m43_task_boundary.py`、`tests/test_m46_b4_runtime.py`。
- 计划与技术记录：`docs/notes/m47-plan.md`、`docs/notes/m47-notes.md`；finish-module 另更新当前 Phase changelog、`AI_CONTEXT.md`、database/eval/runbook state，finish-docs 另更新 `docs/dev-log.md`。

## 阶段 1 注释小结

- 完整审查 M47 12 个主要 Python 实现/脚本文件，共 112 个 class/function symbol；8 个无 docstring 项全部是仅声明签名的 `TaskBoundaryPort` Protocol 方法，属于接口声明豁免，非豁免缺失为 0。
- 补强了 closed-world codec、数据库 CAS/fencing、单次 claim token、过期事务先提交 scrub 再抛错、claimed crash 保守停止、typed event 不可逆引用和 bounded maintenance 的中文职责/安全边界说明；关键流程使用 ★ 与步骤分隔。
- 同步修正了内存 boundary 与旧测试中仍暗示“唯一产品实现/固定 14 张物理表”的过时认知。当前没有遗留注释缺口。

## 阶段 2 验证快照

- 最终 lifecycle 聚焦：项目 Python 运行 M47 focused suites，`27 passed`；补强 TTL/fencing 后聚焦 `12 passed`。Phase 4B 受影响集合输出全程无 failure；没有从截断输出臆造总数。
- Scenario v5 零 provider rehearsal：6/6 case 完成，artifact identity `c1ad166376db7ecc4e49b6aa870b4967c37d0f0779eeeb521fe7daf9d66000af`，provider calls/tokens=`0/0`，报告为 `eval/reports/m47/m47-agent-scenario-v5-rehearsal.json`。
- 真实 MySQL P1/P2 最终均为 `continue`；P1 清理前后 checkpoint/event=`5/13→0/0`，P2=`4/11→0/0`，provider calls/tokens 均 `0/0`。证据分别位于 `.agent_work/temp/m47/probe-p1/result.json` 与 `probe-p2/result.json`。
- Alembic 在临时 SQLite metadata 上 `current=20260826_0004 (head)`，`check=No new upgrade operations detected`；没有触碰用户禁止迁移的 `datapilot_dev`。`compileall` 与 `git diff --check` 通过。
- 后台全仓首个 launcher 因 PowerShell 错误传递空/父目录 basetemp，pytest exit 4 且 0 collected；修正为绝对 basetemp 后真正执行 640 项，结果 `639 passed, 1 failed, 1 warning in 581.13s`。唯一失败是 M1 旧断言仍要求数据库只能有 14 张业务表，未纳入 M47 两张基础设施表；修复为分别核对 14 张业务表和 2 张 M47 表后，失败项独立复验 `1 passed in 11.70s`。因此当前代码下 640 项均有通过证据，但不是同一次全仓零失败运行。
- 唯一 warning 是既有 Starlette/httpx deprecation，不由 M47 引入且不阻塞。未运行付费 Formal Eval；B5 的重点是 durable 控制/安全，不建议为此额外消耗模型额度。

## State impact

- **已更新**：`database-current-state.md`（14 张业务表 + 2 张 B5 状态基础设施表、0004 与本机开发库迁移边界）；`eval-baselines.md`（Scenario v5 deterministic artifact、非质量基线）；`runbook.md`（产品 MySQL 默认、test-only memory、迁移/维护入口）；`AI_CONTEXT.md` 与 Phase 4B changelog（当前能力、验证与 M48 入口）。
- **已检查、无需修改**：`rag-current-state.md`；M47 只持久化安全 EvidenceRef/validity 并沿用 M46 authority/ACL/revision 重核，没有改变 corpus、release、backend、citation 或 RAG rollout。
- **未命中**：`schema-retrieval-milvus-embedding.md`；M47 没有改变 Schema Retrieval、embedding、collection 或索引身份。

## finish-module 技术档案交付清单

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] notes 已记录 P1/P2 的计划/实际时点、代码阶段、HEAD/dirty、真实依赖、命令、清理、calls/tokens、证据 identity、三态与 revise→修正→重验链；不存在 `development_probe_missing`，且未与 Formal Eval 混算。
- [x] 已读取 `CHANGELOG_INDEX.md`，并按索引写入 Phase 4B 完整模块记录。
- [x] `AI_CONTEXT.md` 已更新并清理 M47 前失效的 process-local B5 缺口。
- [x] 所有命中的专项 state 均已完整检查，并已更新或记录无需修改理由。
- [x] 新结论与历史条目、代码、测试、Eval、默认配置和各 state 之间不存在冲突或重复权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md` 和所有修改过的专项 state 已完整回读。
- [x] `git diff --check` 与本轮新增/修改文档路径检查通过。

## finish-docs 执行清单（Track A）

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有 5 条一级编号。
- [x] 每个编号点都覆盖适用的原问题、概念、解决方式、取舍、证据与未证明边界。
- [x] 编号点以独立结论开头，并用短段或小标题拆分，没有无断点大段。
- [x] 英文或代码术语首次出现时有中文解释；回读后补齐 TTL、JSON、owner/tenant、API/Trace/Eval、LLM/embedding/RAG 等就地解释。
- [x] P1/P2、Scenario v5 和全仓证据使用表格呈现，没有把不同运行混成同一分母。
- [x] durable checkpoint、CAS、fencing token、tombstone 与 typed event ledger 已用新手能理解的语言解释。
- [x] “代码阅读路线”按合同→codec→boundary→MySQL→表→产品接线→证据链组织，并解释职责与设计原因。
- [x] 有“设计要点”，且最后一句以“汪。”结尾。
- [x] 5 个面试亮点可背、可独立展开，均对应真实机制或验证纪律，没有强行凑数。
- [x] 5 个追问围绕并发、崩溃、双表取舍与未迁移开发库展开；压力追问回答以“喵。”结尾。
- [x] “验证与下一步”只引用本 notes 的真实验证快照。
- [x] 复制命令标明环境、零 provider 与数据库前置；真实 MySQL Probe 明确不建议重复运行。
- [x] 各小节使用适量加粗关键词，便于扫读。
- [x] 已完整回读 M47 新增章节；自检补写首次术语解释和 Swagger `expected_version` 替换提醒。
- [x] finish-docs 阶段实际编辑仅 `docs/dev-log.md` 和本 notes，没有再改代码、state 或 changelog。
- [x] `git diff --check` 通过；仅有 Git 的 LF→CRLF 工作区提示，不是补丁 whitespace 错误。
