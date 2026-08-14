# DataPilot AI Context（续接仪表盘）

> 这里只保留当前状态、默认值、最新事实和活跃坑。运行命令见 `docs/state/runbook.md`，评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史见 `docs/state/AI_CONTEXT_CHANGELOG.md`。

## 当前状态

| 项目         | 当前值                     |
| ------------ | -------------------------- |
| 阶段路线     | `docs/phase4-roadmap.md`   |
| 阶段参考     | `docs/phase4-reference.md` |
| 当前活动模块 | M32 已开发并收工，待人工检查与验收（2026-08-13） |
| 当前 plan    | `docs/notes/m32-plan.md`   |
| 当前 notes   | `docs/notes/m32-notes.md`  |
| 待决事项     | 无                         |
| 更新时间     | 2026-08-13                 |

## 必读规则

- 开始开发、排障或验证前先读本文。
- 运行命令、模型、LangFuse 或 eval 前必须读 `docs/state/runbook.md`。
- 解释 eval 数字、模型 A/B、失败归因或分母时必须读 `docs/state/eval-baselines.md`。
- 涉及 SQL/字段/指标/oracle 时读 `database-current-state.md`。
- 涉及 Milvus/embedding/Schema Retrieval 时读 `schema-retrieval-milvus-embedding.md`。
- 追溯设计原因、历史实验时读 `docs/state/AI_CONTEXT_CHANGELOG.md`。
- 前台等待超时不等于真实 Eval 已结束：按 runbook 用同一 `run_id` 检查 manifest、checkpoint、artifact；不得擅自换 ID 重跑。
- 用户明确说执行某个 eval 时，按 runbook 的“一次精确运行授权”直接执行一次；不重复询问授权，也不扩大范围或切换默认配置。
- 默认模型、embedding、正式 case、安全策略、数据库结构等长期选择，必须先说明方案并等待用户确认。

## 当前默认值

- 后端：FastAPI + Pydantic；`/api/query` 返回 `AgentResponse`。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy/Alembic；SQLite 仅用于测试、smoke 与 M27 deterministic oracle。
- NL2SQL：普通 API 默认走 `new_text2sql`（Schema Retrieval → QueryPlan → SQL Guard）；只有显式传 `force_new_pipeline=false` 才走 legacy 模板优先 baseline。
- 默认模型：Qwen `qwen3.7-plus`（`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`）；45s、retry0、backoff1。
- Schema Retrieval 默认：inmemory + deterministic + weighted；Milvus / DashScope embedding 仅显式实验开启。M32 Knowledge deterministic adapter 只是 P2 本地 baseline，G4 尚未选择 P3 默认 adapter。
- LangFuse 默认关闭，JSONL trace 为主；SQL 安全为只读 AST + RBAC + 敏感字段策略。
- 现有 Text2SQL chat/schema embedding 出站在 transport 前按 `phase4-outbound-v1` 精确登记；所有新增 Knowledge/RAG 数据类别与节点用途继续默认拒绝，LangFuse Cloud 未获放行。

## 最近验证事实

> 只保留会影响当前决策的最新证据，不按模块流水账累积。

| 日期 | 事实 |
|---|---|
| 2026-08-13 | M32 按用户确认的方案 A 完成 P2 第一切片：`load_active_release()` → pre-selection ACL → deterministic adapter → Document Evidence candidate/selected → pre-generation 复核。内部 ledger 保留审计事实，安全投影只显示最终 selected Evidence；不生成答案、citation、公开 API 或四轴状态。 |
| 2026-08-13 | 独立 `phase4-rag-retrieval-v1` 当前为 6 Scenario / 20 required，Gate `passed`；3 条 retrieval advisory 为 2 passed / 1 technical-unavailable `not_observed`。最终 M32 聚焦 `28 passed`，全仓 `304 passed, 3 skipped, 1 warning`；均为离线确定性证据，不证明真实 LLM、语义检索或 citation 支持质量。 |
| 2026-08-13 | M31 完成 Phase 4 P1 第二切片：trusted caller、文档 ACL 双检、outbound 默认拒绝、Document/SQL typed Evidence 四阶段、确定性 citation validator 和 immutable release 已落地。用户选择 G3=A；11-entry release `4e86bdd...` 已 active，corpus `abdc9aed...`，首次发布 `previous=null`。 |
| 2026-08-13 | 独立 `phase4-v1` contract/security family 当前为 8 Scenario / 12 required，最终 artifact `197e0d62...`，`12 passed / 0 failed / 0 not_observed`、Gate passed；全仓 `276 passed, 3 skipped, 1 warning`。它不证明 retrieval、答案质量或开放语义 citation support，M27 v3 保持只读。 |
| 2026-08-13 | M30 建立 source-backed staged catalog：7 个 Markdown 政策/规则原件 + 4 个从 `metrics.yaml` 派生的指标条目，共 11 entries；corpus identity `abdc9aed...`，build identity `c5e6cf17...`。M31 以它为 authority-derived candidate 完成 active 发布；legacy `knowledge_docs` 仍不是 runtime catalog。 |
| 2026-08-13 | 用户在 G2 选择方案 B：运行时 catalog 读取 authority source，`knowledge_docs` 物理表暂留为有损 legacy storage；seed 从同一 builder 派生 11 行，不再维护 `_KB_CONTENTS`。Text2SQL queryable universe 为 13 表，Schema corpus 为 186 docs/hash `6b67606d...`；14 张物理表事实不变。全仓 `231 passed, 3 skipped`，未调用真实 provider。 |
| 2026-08-12 | M29 完成 Phase 4 P0 合同冻结：后续保留 `/api/query` 并做兼容投影；内部事实拆为 route/execution/answer/safety 四轴；引入 trusted caller、typed Evidence 四阶段、citation 校验与 receiver × node purpose × data class 出站策略。M29 只产出合同/调查材料，没有修改运行代码或默认行为。 |
| 2026-08-12 | 首批知识治理覆盖现有 10 条 seed：政策/规则经审查后保留，metric 说明由 `metrics.yaml` 派生或校验，不引入长文 parent/child；所有新增 Knowledge/RAG 远端用途默认 deny。Phase 4 Eval 使用独立 family，M27 v3 全部只读；具体文件结构/版本号留给首次实现模块。 |
| 2026-08-10 | 当前 canonical contract 升为 `m27-v3`：Schema Context 的物理字段、metric key、输出 alias 分开，并在 catalog 加载时做 domain schema 可满足性校验；`orders_wide` 业务月份统一按 `paid_at`，`snapshot_at/batch_id` 只选快照版本。旧 v1/v2 artifact 继续只读，不与 v3 直接比较；本次未运行真实 LLM Eval。 |
| 2026-08-10 | M27 EvalRun 已恢复 run-scoped Schema vector index：一轮只构建/注入一次，结束时关闭，runtime identity 记录 reuse 与 Milvus row count；pytest 默认禁止未 mock 的真实 Text2SQL provider。 |
| 2026-08-10 | Qwen plus + Milvus 的 M27 Stress（9 题）与 Database Exception（7 题）各完成一次，runtime identity 完整记录 DashScope Qwen embedding / 1024 dim、clean collection、195-doc hash。Stress 为全部 assertion **7 passed / 14 failed / 4 not_observed**（7 completed / 2 external unavailable）；Database Exception 为 **4 / 4 / 11**（3 completed / 4 external unavailable）。两套 policy 的 required 均为 0、Gate 都是 `inconclusive`，不等于业务硬门失败；均为单轮 advisory 证据，未登记长期 baseline。 |
| 2026-08-09 | M27 v2 曾建立“一题一次执行、多条 typed assertion 共享证据”与 timeout `not_observed` 语义；该版本现为只读历史。 |
| 2026-08-09 | 四份 M27 v1 Core 快照都曾显示 **29 passed / 5 failed / 0 not_observed**、Gate failed；复查发现商品退款率排名的 3 条“failed”实际是 QueryPlan timeout 后的空答卷误投影。v2 已把这类情况改为 `external_unavailable → not_observed → Gate inconclusive`。 |
| 2026-08-09 | 首个 v2 Core `m27-core-20260809-qwen37plus-milvus-02`：Qwen plus + Milvus 为 **28 passed / 0 failed / 6 not_observed**、Gate `inconclusive`；两题 QueryPlan timeout，没有候选 SQL。17 题已完成的结果全部通过，但单次样本不能当成稳定性或 Milvus 因果结论。该 run 早于 runtime identity 补齐 collection / embedding / corpus 字段，不能单独充当后续严格 Milvus 对照锚点。 |
| 2026-08-09 | v2 单轮曾观察到渠道 GMV 计划使用 `orders_wide.snapshot_at`；M28 已确认这会把抽取时间误当业务时间，并在 v3 修正，旧通过结果不能沿用。 |
| 2026-08-09 | Milvus 实验均使用 DashScope `qwen3.7-text-embedding`、1024 dim、195-doc clean collection、hash `8a8b6626...`；当前样本不足以判断模型或 Milvus 优劣，不切默认。 |
| 2026-08-09 | Review v2 是自动评分后的旁路证据：来源 SHA-256、结构化分类、无候选 SQL 的普通题只能 `insufficient_evidence`；它不改 EvalRun、分母、Gate 或 CI。 |
| 2026-08-09 | 已有可比较 Core 快照，但尚未登记长期正式 M27 基线；长期账本见 `eval-baselines.md`。 |

## 当前路线判断

> 只保留仍然生效的路线和限制；已经完成的“下一步做……”必须删除或改写。

- (2026-08-13) M32 已完成 P2 的安全取证子闭环。下一轮应从 selected Document Evidence 接薄 Shared Evidence Gate/Composer/Citation 回答闭环，只在真实入模时推进 `generation_visible`，通过 validator 后才推进 `cited`；不重做 retrieval，不预选 Milvus/embedding，不接 Graph/Router/Hybrid。
- (2026-08-10) Text2SQL 的确定性收尾问题已修复，下一阶段建议进入 RAG；若未来重跑 Text2SQL，必须使用 `m27-v3` 新序列，并完整记录 collection、embedding、corpus 与 run-scoped index identity。现有 v1/v2 数字只作历史解释。
- (2026-08-09) 默认保持 Qwen `qwen3.7-plus` + inmemory deterministic + weighted；任何切换需要单变量重复证据与用户确认。
- (2026-08-09) M22–M26 的旧模型分数、RRF、M25/M26 合同取舍仅作历史参考，不定义当前 M27 路线。

## 已知的坑（活跃列表）

> 只允许活跃问题；已经解决的内容移入 changelog。

| 坑 | 影响 | 当前处理 |
|---|---|---|
| `app.db.base` 的模型注册可能触发循环导入 | 聚合导入模型时可能失败 | API/工具层沿用 `app.db.base` 暴露路径；重构时再拆 base class。 |
| Windows pytest 临时目录偶发被旧进程锁住 | `PermissionError` 导致假失败 | 换新的 `--basetemp=.agent_work/temp/<name>`。 |
| 工作树可能含用户/其他工具未提交改动 | 容易误回滚 | 动文件前先看 `git status --short`，不回滚非本次改动。 |
| 旧 Milvus collection `datapilot_schema_docs` 有重复灌入污染 | 历史 A/B 不可信 | 新 eval 用唯一/clean collection；校验 row count、dimension、schema docs hash。 |
| QueryPlan 可能过宽，或 SQL 与计划不一致 | contract pass 不等于答案正确 | 保持保守 AST 边界，用 output/result/trace 共同定位。 |
| M27 v1 将 QueryPlan timeout 投影成业务 failed | 旧 Core 的失败数混入外部不可用 | v2 统一为 `external_unavailable / not_observed`；v1 artifact 只读追溯，不再作 v2 基线。 |
| 请求体 `user_role` 仍是客户端自报字符串，生产认证尚未建设 | 不能作为文档 ACL、生产身份或 thread owner 的信任来源 | M31 已让该输入只形成 `unverified_request_claim` 且无 resolved roles；仅 authenticated/demo/test adapter 可授权文档。当前 `/api/query` 尚未接 RAG caller。 |
| `knowledge_docs` 物理表仍存在且是有损 legacy 投影 | 新调用者若绕过 source-backed catalog 读取旧表，会丢失 revision/authority/identity/完整 ACL，并重新制造旁路 | Text2SQL 已从 Schema/prompt/RBAC 双重隔离；seed 只从 staged catalog 派生，旧表不得作为 authority/runtime catalog。 |
| Active Knowledge release 首次发布没有 previous；active 损坏时不会自动 fallback | 自动复活旧正文可能绕过撤销/ACL，当前也没有可回滚版本 | 启动失败关闭；只有未来第二版且 previous 重新通过 authority/revision/policy 校验时才允许显式 rollback。 |
| M32 词法 adapter 只在 11 条短知识和冻结 Scenario 上验证 | 不能外推长文、同义改写或真实语义检索效果，也不能据此触发 G4 | 保持它为本地可替换 baseline；先完成回答/citation 闭环，再用失败簇和单变量证据决定是否实验 embedding/hybrid/rerank。 |
| LangFuse Cloud 重新启用前需统一 question/answer 脱敏（M28 F7） | RAG/Hybrid 若启用 Cloud 会外传完整问答 | LangFuse 默认关闭且 M31 outbound 未放行 Cloud；重新启用前先做 allowlist/redaction 策略和用户决策。 |
| 有时会出现 Windows 宿主保留 9091 | Milvus health 检查失败 | 使用 `19091:9091` host 映射。 |

## 历史入口

- 完整变更、实验记录、旧合同取舍：`docs/state/AI_CONTEXT_CHANGELOG.md`。
- 历史 eval 数字：`docs/archive-versions/eval-baselines-old.md`；M27 以后的长期账本：`docs/state/eval-baselines.md`。
