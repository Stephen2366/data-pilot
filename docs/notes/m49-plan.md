# M49 Phase 4B 最终联调与证据可信度优化计划

## 1. 模块定位

M49 消化 `docs/notes/m48-review.md` 中影响 Phase 4B 最终验收的确定性断点，不重做 B0～B6，也不把展示型工程扩大成生产化工程。核心目标是：修复自然多轮第二轮的 requirement 合并错误；让 Scenario/assurance 只能对真实观察到的事实签发通过；统一阶段完成门、演示环境与公开状态；最后用一条真实 Qwen + MySQL 连续链验证可演示闭环。

本模块不解封 held-out / sealed reserve，不切换 Pipeline/Subgraph 默认，不修改模型、embedding、active Knowledge release、生产认证或大规模质量 Eval。

## 2. 当前根因

1. `understand_turn()` 只在“改成/调整”等窄触发词出现时把 continue 归为 `modify_constraint`。完整显式重述“比较 7 月和 8 月……”会保留 `continue`，随后 `apply_delta()` 把新旧 comparison requirement 相加，稳定触发 `comparison_requirement_ambiguous`。
2. Scenario v6 builder 为每个 case 固定生成 `passed` assertion；budget trigger/fallback 可由常量构造，未绑定 execution evidence。Phase 4B assurance 对 B0～B5 复用 contract identity 充当 evidence identity，合同存在被误写成能力已执行。
3. Phase 4B roadmap 仍要求新 sealed reserve A/B，M46 后续经用户确认的 experimental-only 收口则保留 reserve sealed/not-run；二者没有形成单一完成门。
4. 默认 `datapilot_dev` 尚未迁移 0005，而产品 task backend 默认 MySQL；仓库能力与默认演示环境不一致。
5. runbook 的内部拒绝原因 `caller_untrusted` 与 task family 对外统一投影 `task_unavailable` 未分层说明；README/AI_CONTEXT/人工演示清单也有状态或边界漂移。

## 3. 用户决策门（2026-08-27 已确认全部采用方案 A）

### G49-1：显式完整重述的 TaskDelta 语义

- 方案 A（建议）：当 continue turn 自身给出可闭合的 metric + periods，并生成与当前任务同类、可替换的主 requirement 时，归为 `modify_constraint`；显式“补充/再查证/结合政策”等仍走 additive category。分类依据 typed intent/constraint 完整性，不只依赖“改成”字样。
- 方案 B：只增加“比较/对比/相比”等关键词为 `modify_constraint` 触发词。
- 方案 C：引入 LLM Turn Understanding，由模型输出 TaskDelta，再由确定性层校验。
- 建议 A。B 修得快但继续依赖脆弱关键词；C 会新增模型用途、出站许可、成本和失败面，超出本次展示型收口的必要范围。
- 用户决定：采用 A。方案 C 作为防遗忘能力候选写入 `AI_CONTEXT.md`，本模块不实施。

### G49-2：Scenario/assurance 版本策略

- 方案 A（建议）：保留 v1～v6 历史 artifact 只读，新增 M49 evidence-backed Scenario v7 与 assurance v2；assertion 只有绑定同源 observation/evidence locator 才能 `passed`，未观察必须为 `not_observed`，required case 含未观察时整体只能 `inconclusive`。
- 方案 B：原位加严 v6/现有 assurance validator，并重签 M48 artifact。
- 建议 A。它遵守 additive versioning，不把历史证据改签成新的含义；代价是新增一版小型 schema、builder 和报告。
- 用户决定：采用 A。

### G49-3：B4/Phase 4B 最终完成门

- 方案 A（建议）：正式修订 roadmap，记录 M46 已确认的 experimental-only 例外：Pipeline 保持默认、Subgraph 能力和 no-go 证据保留、reserve 继续 sealed/not-run；Phase 4B 最终验收不再要求当前 candidate 的新 reserve A/B。
- 方案 B：保持 roadmap 原文，M49 不宣称 Phase 4B 最终完成，后续另立质量候选并获权运行 reserve 后再验收。
- 建议 A。它符合简历展示项目边界和既有用户决定，但属于阶段完成门变更，必须再次明确确认。
- 用户决定：采用 A。

### G49-4：默认演示数据库

- 方案 A（建议）：在最终验证前，把本机 `datapilot_dev` 正常升级到 Alembic 0005；不 reset/reseed 业务数据，升级前后只读核对 revision、表和关键计数。
- 方案 B：保持 `datapilot_dev` 不动，新增显式 demo DB 启动配置与准备脚本，以隔离库作为唯一 Phase 4B 演示入口。
- 建议 A。默认 `.env` 与 README 演示路径会真正一致；但 migration 是真实数据库写入，实施前需要本门的精确授权。
- 用户决定：采用 A，并据此授权最终验证阶段对本机 `datapilot_dev` 执行正常 Alembic 0005 升级；禁止 reset/reseed。

### G49-5：安全失败原因的公开合同

- 方案 A（建议）：保持产品公开 `task_unavailable`，runbook 明确内部原因是 `caller_untrusted`、公开投影统一模糊化以防身份/资源枚举。
- 方案 B：把 task API 公开 reason 改为 `caller_untrusted`。
- 建议 A。行为不变，只修正文档和测试分层；B 会扩大公开信息并破坏 B5 的 uniform unavailable 合同。
- 用户决定：采用 A。

## 4. 实现切片

### M49-A：冻结合同和失败回归

- 等待 G49-1～G49-5 确认。
- 为审计中的自然 T2 增加纯状态机和 API 失败回归，先证明旧实现失败。
- 为“无 Trace/无 DB 也能 completed”增加 assurance 反例。
- 完成门：测试能稳定捕获两个已知缺口，且没有运行真实 provider。

### M49-B：TaskDelta / requirement merge 修复

- 按 G49-1 实现确定性分类与替换语义。
- 覆盖 canonical“改成”、显式完整重述、additive policy/evidence、原因/商品/渠道、correction/switch/cancel、旧 Evidence 失效与 legacy compatibility。
- 完成门：一个 task 内任何时点最多只有一个当前主 comparison requirement；additive requirement 不被误删；M43/M44/M48 相关回归通过。
- Live Probe checkpoint：M49-P1，只有 `continue` 才进入 M49-C。

### M49-C：Evidence-backed Scenario / assurance

- 按 G49-2 新增 additive artifact family；不改签 v1～v6。
- assertion 显式区分 `passed / failed / not_observed`，绑定 source execution、evidence locator/identity 和 required/optional；整体状态由闭集规则确定，builder 不得硬编码未执行场景为 passed。
- B0～B6 capability matrix 分开记录 contract identity 与 evidence identity；历史能力可以引用已有可信 artifact，不能用 manifest identity 自证执行。
- 完成门：伪造 probe、缺 case、缺 locator、identity 不一致均不能得到 completed；真实 P1/P2 来源可以生成可验证 artifact。

### M49-D：完成门、演示环境与公开文档统一

- 按 G49-3 对齐 roadmap/M46；按 G49-5 对齐安全原因分层。
- 按 G49-4 处理默认演示数据库，或落实经确认的隔离 demo 入口。
- 更新 README、AI_CONTEXT、人工演示清单和必要状态事实源；正面描述架构能力与工程取舍，不把实验能力写成质量胜出或生产就绪。
- 完成门：路线、状态、README、runbook、实际默认环境没有互相矛盾的当前表述。

### M49-E：真实连续链、回归与交付

- 执行 M49-P2：同一 task T1→T5，触发 Compact 后由新进程继续 T6；核对 Response/Trace、TaskState、Action/Evidence、父子预算和 cleanup。
- 运行 Phase 4B 聚焦/legacy 回归；完整仓库预计超过 2 分钟，按后台纪律执行。
- 固化 notes、技术历史和状态文档；最终验收仍遵守人工检查与 `accept-module` 流程。

## 5. Live Dev Probe 预注册

以下均为 `exploratory / baseline-ineligible`，不登记质量基线。执行前仍需用户对真实运行给出精确授权。

### M49-P1：受影响 T1→T2 最小真实重验

- 时点：M49-B 后、M49-C 前。
- 场景：真实 Qwen + Text2SQL + SQL Guard + 隔离 MySQL；T1 查询 2026-07，T2 用审计中失败的完整显式重述比较 2026-07/08。
- 依赖/数据：只用 `datapilot_m48_test` 的 Phase 4B deterministic business seed；不 reset/reseed，不访问 `datapilot_dev`、Milvus、external、historical、held-out/reserve。
- 预算：最多 4 provider attempts、20,000 observed tokens，retry=0。
- 停止条件：首个系统性失败、预算到顶、数据 identity 漂移或任何越界即停止；不换措辞掩盖失败。
- 完成门：T1/T2 同一 lineage；T2 只有一个 comparison requirement，重新取证并得到 120000/180000/60000/50%；TaskState/Response/Trace 一致；synthetic task rows 清理为 0/0。

### M49-P2：最终连续演示链

- 时点：M49-C/D 后、最终 artifact 冻结前；仅 P1=`continue` 才执行。
- 场景：同一 task 真实执行 T1→T5，使用 server-controlled experimental business Subgraph 完成政策 turn；新进程执行触发 Compact 的 T6 continuation；附一个 production-like 无 resolver 的 pre-Tool 安全失败路径。`COMPACT_BUDGET_TRIGGER` 与 `COMPACT_FALLBACK` 不伪装成该真实 sequence 已发生，而是绑定 M49 同代码下实际执行的 deterministic assertion 日志及其 hash；两项缺日志或断言失败时 v7 保持 inconclusive。
- 依赖/数据：真实 Qwen、Text2SQL、SQL Guard、经 G49-4 确认的演示 MySQL、business active release；不访问 Enterprise Milvus/external/historical/held-out/reserve。
- 预算：最多 14 provider attempts、60,000 observed tokens，retry=0。
- 停止条件：首个系统性失败、预算到顶、身份/权限/数据 identity 漂移、出现未预注册 Tool 或 cleanup 失败即停止；不切换模型/backend/问法继续凑成功。
- 完成门：T1→T6 连续 lineage、SQL/Document Evidence、父子预算、Compact、restart、Response/Trace/Eval 同源；安全负例 provider/runtime 均为 0；synthetic task rows 清理闭合。未观察的 required assertion 必须让 artifact 保持 inconclusive。

## 6. 验证矩阵

- 聚焦：M43 TaskDelta/TaskState、M44 Loop/API、M48 Context/assurance、M49 新测试。
- 兼容：M31～M41 legacy family；M42～M48 additive family；Pipeline default/Subgraph experimental/no-auto-fallback；reserve sealed/read0/not-run。
- 静态：artifact identity/closed-world/private payload、Alembic current/check、README/state/roadmap 交叉核对、`git diff --check`。
- 不外推：单次真实 Probe 不证明自然语言泛化率、RAG 质量提升、生产认证、性能/HA 或外部 Tool exactly-once。
