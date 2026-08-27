# Phase 4B 整体审计与最终 Dev Probe（2026-08-27 后，审计轮）

> 定位：M49 收工后，对 Phase 4B（B0～B6 / M42～M49）做整体完整性审计 + 用户授权的两个真实 Dev Probe。只记录事实与决策，不修改代码。

## 审计已核实的关键发现（截至探针启动前）

1. **工作区未提交**：`engine/phase4b/rag_subgraph.py`、`rag_strategy.py`、`app/main.py`、`eval/run_rag_external_eval.py`、`tests/test_m46_b4_external_chain.py`、`tests/test_m46_rag_strategy.py` 及 4 个 state 文档有未提交改动；`docs/notes/m49-rag-postprobe.md` 未被 git 跟踪。HEAD=`7e1cec2`。
2. **默认演示断点**：`datapilot_dev`（默认 .env）已迁移 0005，但 refunds 无 2026-08 行、2026-07 合计 74866.40≠120000、无净退款口径数据；Phase 4B 招牌 T1～T6 链只能在隔离库 `datapilot_m48_test`（0005、120000/180000、合成行 0/0，已只读核实）复现。README Quick Start 与顶部演示声明不一致。
3. **README 过期**：§4 仍描述 legacy 单轮（“不宣称多轮、不跨进程共享”）；§Roadmap 仍把 persistent thread state 列为后续；§Project Structure 缺 engine/phase4b；Streamlit demo 无 task envelope。
4. **里程碑完成门审计**（三个只读子代理 + 代码审计子代理，均有 file:line）：B0/B1 完成；B2 当年完成凭证被真实链证伪、四轮返工，T3/T4/T5 真实路径后由 M49-P1/P2 补证；B3 expansion 卡 4 次重定义后 no-go→go，direct expansion 未按原定义证明；B4 experimental 收口合法但“两种动作真实 product runtime 选择”在 M46 内未端到端证明（M49 R4R/R5 部分补上，qst_0431 cited-gold 仍未过）；B5/B6 机制完成、真实 MySQL 证据扎实，M48“Phase 4B completed”过度宣称已被 M49 v7/assurance v2 修正。
5. **代码级发现**（代码审计子代理）：MySQL CAS 无自动化真库测试（全靠手工 probe）；tombstone purge 无 scheduler、event 表无限增长；`external_profile` 知识 runtime 在 NL task 链注册但不可达（understand_turn 只产 business_release）；claimed-crash 后 reason 为 task_not_active、`mysql_task_boundary.py:342` “claim 竞争失败”分支不可达；active 期间用户原文/答案摘要落 context_payload，隐私依赖 scrub。
6. **正面核对**：assurance v2 / Scenario v7 引用的 3 个执行证据文件 SHA-256 全部对账通过；P2 r8 result-safe.json 完整；worker-a Trace 无 prompt/正文/raw error/凭据；compileall + 探针模块导入通过。

## Probe 授权与登记（用户 2026-08-27 批准 P1+P2）

- 分类：`exploratory / baseline-ineligible / development-probe`，不登记基线。
- 总预算：≤20 provider attempts / ≤75,000 observed tokens，retry=0，各执行一次。
- 数据边界：只写 `datapilot_m48_test` 的 synthetic task/event 行并 finally 清理 0/0；不 reset/reseed；不碰 held-out、sealed reserve、生产数据、Milvus/external、默认切换。
- 停止条件：首个系统性失败 / 预算到顶 / 数据 identity 漂移 / 负例意外产生 provider 调用 / cleanup 失败，立即停止，不换问法/模型/backend。

## P1：纵向链最小重验（当前工作区，r9）

- 命令：`M49_P2_OUTPUT=.agent_work/temp/phase4b-audit/probe-p1-r9 python scripts/probe_m49_phase4b_continuity.py`
- 场景：仓库已提交脚本原样运行，T1→T6 + 重启 + Compact + no-resolver 安全负例。
- 预算：脚本内置 ≤14 calls / ≤60,000 tokens。
- 执行时点：P2 之前（两个 Probe 共用同一隔离库，串行）。

## P2：真实 lineage 安全负例（新场景）

- 脚本：`.agent_work/temp/phase4b-audit/probe_p2_negative.py`（临时工具，不进产品代码）。
- 场景：T1→T2 真实 chain 后插入过期 expected_version 重放（期望 task_version_conflict / 0 provider / 状态不变）与 customer_service 角色漂移（期望 task_unavailable / 0 provider / 不创建任务），最后用正确版本继续证明 lineage 未污染。
- 预算：≤6 calls / ≤15,000 tokens。
- 预期依据：M48-P2 真实负例 artifact + 代码审计确认（`mysql_task_boundary.py:340-341`、`322-323`）。

## 运行记录

### P1 启动（后台，待检查）

- 启动时间：2026-08-27（审计轮）
- 代码基线：HEAD=`7e1cec2`；工作区 dirty 文件 = 审计发现 1 列出的 10 个文件 + `docs/notes/phase4b-audit-notes.md`（本文件）+ 审计临时脚本。
- 命令（v2）：`$env:M49_P2_OUTPUT='<系统临时目录>/p4b-audit-p1-r9'; python scripts/probe_m49_phase4b_continuity.py`
- 后台 job：`pwsh-10`；产物目录：`<系统临时目录>/p4b-audit-p1-r9/`（result-safe.json / 各 turn Response / Trace / handoff / exit-code）。
- 状态：已完成，见下方"执行结果"。
- 沙箱注记：本轮会话中 pwsh/python 对 `.agent_work/temp/**` 只有读权限（连 python 自建子目录也被拒），探针产物改写到系统临时目录；审计临时脚本仍可被 python 从仓库内路径读取执行。

### P2（待串行执行）

- 命令：`$env:P4B_AUDIT_P2_OUTPUT='<系统临时目录>/p4b-audit-p2-negative'; python .agent_work/temp/phase4b-audit/probe_p2_negative.py`

## 执行结果（按时间顺序）

### P1 r9（当前工作区纵向链）—— `continue`

- 时间：2026-08-27 22:19–22:27；job `pwsh-10`，exit 0。
- 结果：同一 task T1→T6 全部 complete，版本链 `1→3→5→7→9→11`；T3 两次 Observation 驱动 SQL action；T4/T5 Hybrid + business Subgraph（`strategy:subgraph`）各 2 citations；worker B 新进程恢复，T6 Compact `triggered_and_committed`（identity=`68cae70a...`，source 1..5）、0 provider 复用 digest；no-resolver 安全负例 `task_unavailable`、0 provider、不创建 task；cleanup `0/0`。
- usage：12 calls / 52,709 observed tokens（≤14/60,000），retry 0。
- artifact：`<TEMP>/p4b-audit-p1-r9/result-safe.json`；trace 同目录 worker-a/b、safety。
- 结论：**未提交的 RAG seam 改动没有破坏整条链；当前工作区可一键复现招牌演示**。三态=passed → `continue`。

### P2 attempt 1（真实 lineage 安全负例）—— 负例未触达，`inconclusive`

- 时间：2026-08-27 22:27–22:31；job `pwsh-11`（首启 import 顺序踩 `app.db.base` 已知循环导入坑，0 provider/0 DB 写入，修正临时脚本导入顺序后 job `pwsh-12` 执行同一场景）。
- 结果：T1 正常（2 calls/5830 tokens）；T2 的 `sql_generation` 阶段 Qwen 网络调用 **120s 超时**（`The read operation timed out`），query_plan 已成功（68s/6679 tokens）。产品正确失败关闭：`llm_generation_error`→不执行 SQL→`comparison_observation_missing`/`no_answer`、safety=passed、usage 完整记账；负例 A/B 与 DB 状态断言未执行（not_observed）。
- 根因：**provider 网络抖动**（同一问法 P2 r8、P1 r9 均成功；`.env` 已把超时 45→120s，本次生成仍 >120s，retry=0）。非产品逻辑缺陷，且暴露一个真实演示风险：**T2 比较 turn 对 Qwen 延迟敏感，面试现场有概率被超时打断**。
- 结论：三态=inconclusive（依赖不可用），按 runbook 第 7/8 条不自动重跑、不换问法凑数；attempt 证据保留。DB cleanup `0/0`。
- artifact：`<TEMP>/p4b-audit-p2-negative/result-safe.json`（decision=revise，first_failure=T2 agent_result）。

### P2 attempt 2（用户裁决：最小重验）—— 负例通过，state 直查 not_observed

- 时间：2026-08-27 22:34–22:35；job `pwsh-13`，主流程 exit 20（见下）。
- 结果：T1 正常（2 calls/5,783 tokens，v1）→ **负例 A（不存在的 expected_version=2）**：`task_version_conflict`、safety=passed、runtime_invocations=0、provider=0、不投影 task（7.5ms）→ **负例 B（customer_service 角色漂移）**：`task_unavailable`、safety=blocked、invocations=0、provider=0、不投影 task（5.2ms）。两条负例与预注册预期完全一致。
- 插曲：审计 runner 的 DB 直查用了不存在的列名 `task_id`（真实主键是 sha256(task_id) 的 `task_key`，raw id 不落库）导致最后一步崩溃；finally 已清理 0/0。负例响应均已落盘，由后处理脚本固化 `result-safe.json`：`state_intact_direct_check=not_observed`（间接证据：两负例 invocations=0 + 无 task 投影 + M48-P2 真实边界 artifact `67ac498e...`）。未为此重新烧 provider 调用。
- 三态结论：负例场景=passed；state 直查=not_observed（工具缺陷，非产品问题）；整体 `continue`（附 caveat）。
- artifact：`<TEMP>/p4b-audit-p2-negative-attempt2/result-safe.json`。

### Probe 预算总账（用户授权 ≤20 calls / ≤75,000 tokens）

- P1 r9：12 calls / 52,709 tokens。
- P2 attempt 1：4 calls / 12,509 tokens（含 T2 超时那次，usage 完整记账）。
- P2 attempt 2：2 calls / 5,783 tokens。
- 合计：18 calls / 71,001 tokens，retry 0，未越界。分类均为 `exploratory / baseline-ineligible / development-probe`。

## 最终审计结论（摘要，详细版见对话报告）

1. **链路真实性：通过**。当前工作区（含未提交 RAG 水化修复）真实 Qwen/MySQL/business Subgraph 下 T1→T6 一次贯通（P1 r9），重启/Compact/零调用解释/清理/无 resolver 失败关闭全部按合同工作；两个版本并发/权限隔离负例在真实 lineage 上 0 provider 成立。
2. **收口前必须处理（按影响排序）**：① 默认演示断点——`datapilot_dev` 无 Phase 4B 7/8 月种子，README 默认路径跑不出招牌链，演示只能在 `datapilot_m48_test`（要么补正式演示数据方案，要么 README 明说）；② 未提交的 RAG 修复 + untracked notes（验收/复现依赖工作区，不在 git 历史里）；③ README §4/§Roadmap/§Structure 过期与自相矛盾、Streamlit 无 task envelope；④ tombstone purge 无 scheduler、event 表无界增长（README/runbook 已声明"部署方周期调用"，但没有任何调度器/运维入口文档化）；⑤ 演示链对 Qwen 延迟敏感（T2 生成 >120s 超时，retry0，P2 attempt 1 实证）——面试演示前应准备话术或等待网络好的时段。
3. **不必修、但要会讲（面试边界）**：B2 当年完成门曾被真实链证伪后返工、B3 expansion 卡四次重定义、B4 真实 runtime 两动作未在 M46 内端到端证明（M49 补上）、qst_0431 cited-gold 质量门未过、M42/M43/M44 无 accept-module 记录、external 知识 runtime 在 NL task 链注册但不可达、claimed-crash 报错码无法区分"已结束"、MySQL CAS 无自动化真库测试。这些都有文档可查，属于"展示型工程收口"的既有边界，不是本轮新引入的缺陷。
