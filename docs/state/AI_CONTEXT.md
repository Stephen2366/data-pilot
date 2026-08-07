# DataPilot AI Context（续接仪表盘）

> 续接任务、查 bug 先读本文。这里只保留当前状态、默认值、最近事实、路线判断和活跃坑；运行命令见 `docs/state/runbook.md`，评测账本见 `docs/state/eval-baselines.md`，数据库事实见 `docs/state/database-current-state.md`，Schema Retrieval / Milvus / embedding 速查见 `docs/state/schema-retrieval-milvus-embedding.md`，完整历史见 `docs/state/AI_CONTEXT_CHANGELOG.md`。

## 当前状态（唯一权威出处）

- 当前阶段计划文件：`docs/phase3b-langfuse-plan-v6.md`
- 当前模块：M25 Eval Trustworthiness, Reliability & Evidence-Grounded Attribution（代码与收工完成，待验收）
- 上一模块验收：M25 已验收（2026-08-07）
- 阻塞项：无
- 更新时间：2026-08-07

## 必读规则

- 开始任何开发 / 排障 / 验证前，必须先读本文。
- 只要要运行命令、切模型、开 LangFuse、跑 eval，必须读 `docs/state/runbook.md`。
- 只要涉及 eval 数字、模型 A/B、失败归因、测试集口径、通过率解读，必须读 `docs/state/eval-baselines.md`。
- 只要涉及 SQL、字段、指标、seed、expected SQL、`result_match`，必须读 `docs/state/database-current-state.md`。
- 只要涉及 Schema Retrieval、Milvus collection、embedding provider / model / dimension、`schema_docs_hash`，必须读 `docs/state/schema-retrieval-milvus-embedding.md`。
- 只要需要追溯为什么这样设计、历史实验、默认值为何不切，必须读 `docs/state/AI_CONTEXT_CHANGELOG.md`。
- `docs/dev-log.md` 面向用户学习复盘；只有写日志、解释面试讲法或用户要求时再读。
- 不允许只凭本文摘要修改默认模型、默认 embedding、正式 eval case、安全策略或数据库结构；这些长期影响选择必须先向用户说明方案 / 风险 / 后续影响并等待确认。

## 当前默认值

- 后端：FastAPI + Pydantic Schema；`/api/query` 返回结构化 `AgentResponse`。
- 数据库：MySQL `datapilot_dev` + SQLAlchemy ORM + Alembic；SQLite 仅用于测试 / smoke。
- 数据底座：Phase 2.7 后 14 张物理表，固定业务事实和指标口径以 `docs/state/database-current-state.md` 为准。
- NL2SQL：M3 模板 SQL 优先；模板未命中走 LLM + Schema Retrieval + QueryPlan + SQL Guard；LLM 生成后经 SQL Plan Fidelity AST 合同，SQL 执行后由 `output_contract` 校验展示列集合与顺序。
- 主模型默认：Qwen `qwen3.7-plus`，配置入口为 `LLM_PROVIDER=qwen` + `QWEN_MODEL=qwen3.7-plus`。
- 主 LLM 可靠性默认：`LLM_TIMEOUT_SECONDS=45`、`LLM_MAX_RETRIES=0`、`LLM_RETRY_BACKOFF_SECONDS=1`；成功/失败 attempt 均进入 trace，实验配置只在当前 shell 覆盖。
- DeepSeek 主模型：显式切换时使用 `LLM_PROVIDER=deepseek` + `LLM_MODEL=deepseek-v4-flash`；Qwen provider 不读取 `LLM_MODEL`。
- Schema Retrieval 默认：`inmemory + deterministic`；`milvus` / `siliconflow` / `dashscope(qwen3.7-text-embedding)` 只通过环境变量显式开启。
- SQL 安全：sqlglot AST 只读检查 + 表级 RBAC + 敏感字段策略；`admin` 也不能通过 Text2SQL 直出 `users.email/users.phone`。
- Trace / Eval：默认 JSONL trace；LangFuse 默认关闭，仅作为旁路观测和 score 回写增强；eval 入口和开关见 `docs/state/runbook.md`。

## 最近验证事实

| 日期 | 事实 |
|---|---|
| 2026-08-07 | M25 冻结 `case_contract_version=m25-v1`：formal + challenge + diagnostic 共 42 raw cases / 26 independent semantic groups；报告新增 semantic/safety/plan/provider/manual/end-to-end 六个视图与 eligible/observed/unavailable 分母。退款率改为 completed 退款去重订单数 / 成交去重订单数，明细优先、整单回退；平均售价明确为有效价格历史记录的算术平均但仍为 manual。 |
| 2026-08-07 | M25 4-case reliability 小样本：45s/retry0 为 4 logical / 4 physical attempts、1/4 成功、3 timeout、179.7s；retry1 为 4 logical / 8 physical attempts、0/4 成功、8 timeout attempts、377.9s。该样本不支持默认开启 retry，默认保持 45s/0；timeout 归 `external_service + not_observed`，不再算模型语义错误。 |
| 2026-08-07 | M25 收尾验证：focused `39 passed, 1 warning`，最终全仓 `184 passed, 3 skipped, 1 warning`；seed reset 成功且 14 表固定规模/关键事实通过。随后已完成 4 组 M25-v1 diagnostic superset 对照；未另跑独立 formal，challenge 已包含在 diagnostic superset 中。 |
| 2026-08-07 | M25 round2 四组 diagnostic：Qwen 3.7-max+Milvus `26/32`、Qwen 3.7-plus+Milvus `21/32`、Qwen 3.7-plus+local `28/32`、Qwen 3.8-max+local `18/32`；同日单轮差异不作模型/embedding 稳定结论。Milvus 两组使用 clean 195-doc、1024 维、hash `8a8b6626...` collection。 |
| 2026-08-05 | M23 已收口非 pipeline 基线：商品退款率改为成交订单内“明细优先、整单退款回退 `refunds.product_id`”，`order_count` 统一为 `COUNT(DISTINCT orders.id)`；challenge 12 条、formal 8 条自动 SQL case 使用 `result_match` / `expected_value`，并新增 6 自动 + 1 人工的异常专项。原 20 条与新增 3 条 reference SQL 经 MySQL 与 SQLite 双端审计均可执行。当前 195 条 schema docs hash 为 `ce04fe4f...`；Milvus 复用强制校验 collection schema description 中的同一 hash。此前 focused `42 passed`、全量 pytest `152 passed, 1 warning`。 |
| 2026-08-06 | M23 新合同 local 首跑：Qwen `qwen3.7-plus` + local deterministic / weighted 为 `23/32`（自动 `20/27`、人工/诊断 `3/5`）。硬失败共 9 条，其中自动 7 条、人工/诊断 2 条；另有 `db_hard_003` 只要求人工 review，不属于第 10 条硬失败。自动失败包括 3 条结果/输出不保真、2 条生成/计划错误和 2 条字符串 SQL plan contract 误拦；目标 schema 均已进入 Context。 |
| 2026-08-06 | M23 同合同 Milvus 单次诊断已完成：Qwen `qwen3.7-plus` + clean run-scoped Milvus + DashScope `qwen3.7-text-embedding` + weighted 为 `21/32`（自动同为 `20/27`、人工/诊断 `1/5`）；195 docs、hash `ce04fe4f...`、1024 维、final row count 195。local / Milvus 各仅一次，`23→21` 不能定性为 embedding 退化，也不改变默认 retrieval。 |
| 2026-08-06 | M23 异常专项首次真实 LLM run：Qwen `qwen3.7-plus` + local deterministic / weighted 为 `1/7`（自动 `1/6`、人工 `0/1 review`）。`db_anomaly_001` 的 completed / `processed_at` / 带符号净退款金额通过；其余暴露 limit、输出列、退款率、真实外键和对账输出缺口。无代理启动的 `WinError 10013` 不计入；本次代理 run 仅为单次诊断快照，不切默认。 |
| 2026-08-06 | M24 代码完成后受控 A/B：Local `24,24,25/32`（自动 `21,21,22/27`），Milvus + DashScope/Qwen embedding `25,25,25/32`（自动稳定 `22/27`），两组 manual/diagnostic 均 `3/5`。Milvus 唯一 collection 三次均 195 rows、195-doc hash 正确，M2/M3 inserted=0。该三次样本显示合同误拦历史正例稳定通过，但不单独证明 embedding 因果收益；详见 `eval/reports/m24-ab-execution-manifest.md`。 |
| 2026-08-06 | M24 收尾验证：focused `70 passed, 1 warning`；全仓 `176 passed, 1 warning`。warning 为既有 Starlette/httpx deprecation。未重复运行外部 formal/challenge/diagnostic，未改默认 backend/embedding/fusion。 |
| 2026-08-02 | M19 failure triage 已完成：`eval/run_eval.py` 默认报告新增 `Failure Triage Summary`，支持 `--triage-json` 和 `--compare-triage-left/right/report`；LangFuse 可选回写 `triage:*` scores。 |
| 2026-08-02 | M19 代码验证：focused tests、M16-M19 focused tests、全量 pytest 均已通过；全量快照为 `121 passed, 2 skipped`。 |
| 2026-08-02 | M19 LangFuse Cloud smoke：代理下 `langfuse_triage_scores=ok:24`；说明 triage score 可写回 Cloud。 |
| 2026-08-02 | M19 DeepSeek `deepseek-v4-flash` 快照：formal `7/10`、challenge `9/16`、diagnostic `19/32`；这是 triage 验证快照，不直接等同稳定能力基线。 |
| 2026-08-02 | M19 Qwen `qwen3.7-max` 对照：formal `8/10`、challenge `12/16`、diagnostic `22/32`；分数更好，但 `schema_context` 仍为 6、`schema_retrieval` 比 DeepSeek 多 1。 |
| 2026-08-02 | M19 后续 Qwen embedding / Milvus 复测：Qwen `qwen3.7-max` + Qwen embedding 为 formal `8/10`、challenge `12/16`、diagnostic `20/32`；DeepSeek + Qwen embedding diagnostic 为 `19/32`。 |
| 2026-08-02 | Milvus `datapilot_schema_docs` 当前发现重复灌入污染：schema docs 实际 193 条，但 collection `row_count=19493`（约 `193 * 101`）；因此 Qwen embedding / Milvus A/B 结果不能直接当作 embedding 模型优劣结论。 |
| 2026-08-02 | M20 已完成索引卫生修复：Milvus eval 使用 run-scoped vector index 复用，报告写出 `schema_docs_hash` / collection / row_count / oracle backend；clean smoke `row_count=193`。 |
| 2026-08-02 | M20 DeepSeek + clean Milvus + Qwen embedding diagnostic 为 `17/32`，低于 M19 污染链路 `19/32`；说明 clean Milvus 后仍未看到 Qwen embedding 稳定收益，但不自动改默认 embedding。 |
| 2026-08-02 | M20 Qwen `qwen3.7-max` + clean Milvus + Qwen embedding diagnostic 完整跑通：`21/32`（row_count=193、run_scoped）；高于同链路 DeepSeek `17/32` 与 M19 污染 Qwen `20/32`；提升来自 query_plan/plan_validation 消失，`schema_context` 7 仍是主失败簇。 |
| 2026-08-02 | Retrieval-only benchmark 已新增：Qwen embedding vector-only recall `0.929` 高于 deterministic `0.787`，但 merged recall 均为 `0.738`；说明 embedding 有信号，当前瓶颈更像 fusion / rerank。 |
| 2026-08-03 | M21 新增显式 `rrf` fusion 实验（默认仍为 `weighted`，不读取任何 `expected_*` 标签）。retrieval-only 上，Milvus + Qwen embedding merged recall `0.738 → 0.929`、relation `0.633 → 0.967`；但同配置 DeepSeek diagnostic `21/32 → 18/32`，并新增 `plan_validation 0→3`，故 RRF 记录为否定实验且不切默认。 |
| 2026-08-02 | ⚠️ 旧结论：`qwen3.8-max` 曾因 DashScope 账号/配置返回 HTTP 403 `access_denied`。2026-08-07 新一轮已可完整运行 32 条 local diagnostic（`18/32`），旧“不可用”判断不再适用于当前运行状态；该轮 external failure 较多，能力结论仍待重复。 |
| 2026-07-30 | M18 Experiment 结论：LangFuse UI 的 trace -> Dataset item 可用；UI run 需要项目 LLM key，Webhook run 需要 remote experiment URL，DataPilot 当前不临时实现 webhook runner。 |

## 当前路线判断

| 日期 | 判断 |
|---|---|
| 2026-08-07 | M25 后路线：先用 execution stage + root cause + semantic status 区分代码、模型、检索、外部服务与 Eval 契约。4-case retry=1 没有恢复且成本翻倍，不切默认；递归题的 SchemaGraph 事实完整但计划引用虚构字段，当前证据指向 plan/model，不触发 embedding A/B；八轮复核另确认部分递归失败是 SQL Guard 把 CTE 临时名当物理表误拦（code_issue），修复前不继续用整套分数验证，先补 CTE/RBAC、`* 1.0` 等价、alternatives 的确定性单测。 |
| 2026-08-04 | M22 已校正 Context / Output / Result / Manual 契约：不再使用 M21 的 `schema_context` 失败数直接判断检索质量。后续先按 trace 和 failure subtype 定位，再提出单变量假设。 |
| 2026-08-05 | M22 C0-refresh/C1/C2/C3 首轮分别为 `24/32`、`27/32`、`25/32`、`24/32`；retrieval-only local weighted `0.738`、Milvus weighted `0.738`、Milvus RRF `0.929`。这些只用于同一 194-doc 的 M22 旧合同筛选。M23 已补退款率成交过滤与整单退款回退，并新增外部关联、负数冲销和金额对账专项；因 `net_refund_amount` 新增，后续检索实验必须以 195-doc corpus 重建基线。 |
| 2026-08-05 | M22 C0-C3 三次重复完成：C0 `24/24/25`、C1 `27/28/28`、C2 `25/27/25`、C3 `24/26/27`（32 条总分）。C1 三次均最高或并列最高；C2/C3 无稳定端到端收益，不切默认。C2 第2次有效结果使用 `r2b` 文件名，首次启动中断未计入。 |
| 2026-08-05 | Qwen `qwen3.8-max` + 本地 deterministic + weighted 追加快照为 `22/32`；模型可用，未执行备用 `qwen3.7-max`，不改变默认模型。 |
| 2026-08-05 | Qwen `qwen3.7-max` + 本地 deterministic + weighted 追加快照为 `26/32`；高于同条件 Qwen 3.8 的 `22/32`，但仍是单次证据，不改变默认模型。 |
| 2026-08-05 | 用户确认将默认主模型切换为 Qwen `qwen3.7-plus`；检索仍为 `inmemory + deterministic + weighted`，不切 embedding、Milvus 或 RRF。 |
| 2026-08-05 | 默认切换后的路线：优先观察 Qwen `qwen3.7-plus` 在 SQL Contract 别名/等价表达、QueryPlan→SQL 信息保真和延迟上的表现；DeepSeek `deepseek-v4-flash` 保留为显式回退对照。 |
| 2026-08-06 | M24 A/B 后路线：AST SQL 合同没有出现新的 semantic false block；稳定失败转为 QueryPlan 输出投影、真实生成/计划表达式和结果语义问题。Milvus 自动能力三次均为 `22/27`，Local 为 `21–22/27`，差距不足以单独切换默认 embedding；默认仍保持 `inmemory + deterministic + weighted`。 |
| 2026-08-04 | 默认模型、embedding、向量库和 weighted fusion 保持不变。`db_core_004` 等 SQL plan contract 失败先作为生成链路缺口复核，不预设为 retrieval 问题。 |
| 2026-08-04 | 当前默认 diagnostic `25/32`（自动 `22/27`、人工/诊断 `3/5`）仅是 M22 新口径快照；M21 的 `21/32` 及 193-doc 实验只作历史证据。 |
| 2026-08-04 | Eval / Trace / LangFuse 的功能说明见 `docs/eval-observability-guide.md`；历史实验和取舍见 changelog / eval-baselines，不在本仪表盘重复展开。 |

## 已知的坑（活跃列表）

| 日期 | 坑 | 影响 | 当前处理 |
|---|---|---|---|
| 2026-07-18 起，2026-08-02 仍有效 | `app.db.base` 同时定义 `Base` 又导入所有模型注册 Alembic metadata | 业务代码若先从 `app.models` 聚合包导入模型，可能触发循环导入 | API / 工具层优先沿用 `app.db.base` 暴露的模型导入路径；后续若重构，可拆 `app/db/base_class.py` 和 `app/db/base.py` |
| 2026-07-24 起，2026-08-02 仍有效 | Windows 下 `.agent_work/temp/pytest-tmp` 偶发被旧 pytest 临时目录锁住 | 测试可能因 `PermissionError` 删除 basetemp 失败而假失败 | 不改业务代码，换新的 `--basetemp=.agent_work/temp/<name>` 复跑 |
| 2026-07-22 起，2026-08-02 仍有效 | DB comment 在 PowerShell 离线 SQL 输出中乱码 | 影响离线 SQL 文件可读性；在线迁移和建表正常 | 暂不改业务；如需导出 SQL 文件，再统一处理输出编码或将 DB comment 改为 ASCII |
| 2026-07-18 起，2026-08-02 仍有效 | 工作树可能有用户或其他工具留下的未提交改动 | 容易误回滚非本次任务修改 | 动文件前看 `git status --short`，不回滚非本次任务改动 |
| 2026-07-29 起，2026-08-02 仍有效 | LangFuse SDK 4.14.1 已无旧版 `client.trace()` builder | 按旧博客 / 旧草稿写 smoke 或 M16 backend 会直接 `AttributeError` | 使用 `start_observation(trace_context={"trace_id": uuid4().hex})` / `create_score(trace_id=...)` / `flush()`；细节见 `docs/notes/m15-notes.md` |
| 2026-07-29 起，2026-08-02 仍有效 | Windows 裸连 LangFuse Cloud 偶发 `WinError 10013` | trace visibility 查询 / OTLP export 可能失败，但 score 写入和 JSONL 主链路可正常 | 真实 Cloud smoke 建议显式设置 `HTTP_PROXY` / `HTTPS_PROXY` 为 `http://127.0.0.1:7897`；脚本将 score write 和 trace visibility 分开显示 |
| 2026-08-02 起，M20/M23 已加护栏 | 旧固定 Milvus collection `datapilot_schema_docs` 已被历史重复灌入污染；M23 还发现同数量但不同语义文本可绕过旧行数检查 | 旧 collection 的历史 A/B 结果不能直接作为 embedding 优劣结论 | 新 eval/smoke 使用唯一 collection 或 clean collection；`MilvusVectorIndex` 会拒绝行数、维度或 schema docs hash 不匹配（含缺少 hash 标记）的已有 collection |
| 2026-08-04 起，M24 已升级护栏 | QueryPlan 仍可能把输出投影声明过宽，或 SQL generation 生成与计划不一致的真实表达式 | AST fidelity 已消除历史表 alias/quoted identifier/唯一限定名省略/SELECT alias 误拦，并严格检查 order/limit/projection；但合同不能修正错误 QueryPlan，也不能把 contract pass 当答案正确 | 保持同一顶层 SELECT 的保守 AST 边界；依靠 `output_contract`、result scorer 和完整 trace 区分计划过宽、真实保真失败与结果语义错误，不为追分放宽 CTE/derived scope 等未知情况 |
| 2026-08-05 起 | M23 自动 eval 仍未全覆盖数据库异常彩蛋 | 新退款率 case 已覆盖成交过滤和整单退款回退，但外部单号、负数退款、金额对账仍不能由当前自动分数证明 | 事实菜单保留在 `database-current-state.md`；后续新增异常 case 前先明确业务题面与自动判定方式 |
| 2026-08-07 起 | M25 reliability 候选每组只有一次 4-case 小样本，且 provider 波动明显 | 不能把 retry0 的 1/4 与 retry1 的 0/4 外推为总体 SLA，也不能据此选新的 timeout 魔法数字 | 当前只支持“retry=1 本轮无恢复且成本翻倍，因此不切默认”；后续候选必须固定唯一变量并重复 |
| 2026-08-07 起 | M25 八轮 diagnostic 复核已确认确定性缺陷：SQL Guard 将 CTE 临时名（category_tree/cat_tree 等）当物理表 RBAC 误拦；fidelity 将 ratio `* 1.0` 类型提升判为表达式 mismatch；`schema_context_match` 未消费 `expected_tables_alternatives`；manual-review 与 triage.failed 混读；`db_hard_001` 题面 GMV 与严格 `item_gmv` 期望不完全对齐 | 递归 / ratio / Context / manual 相关结论会被假阴性和误拦污染；修复前继续用更多整套分数验证会重复污染归因 | 修复方案待 M26 中间确认门逐项决策（见计划文件 M26 P1-3 决策卡）；先分别补 CTE/RBAC、alternatives、`* 1.0` 等价表达式的确定性单测 |

## 变更记录索引

- 完整历史变更、实验记录和模块档案写入 `docs/state/AI_CONTEXT_CHANGELOG.md`。
- 真实 LLM eval、A/B、smoke、默认值调整、不采用某方案 / 不切默认等路线判断，必须同步 changelog；影响当前路线的摘要再同步到本文。
- 长期评测数字、报告路径、失败结构和典型错因写入 `docs/state/eval-baselines.md`，本文只保留续接摘要。
- 运行命令、模型/embedding/LangFuse 开关和 eval 命令矩阵写入 `docs/state/runbook.md`。
- Schema Retrieval / Milvus / embedding 的默认值、collection 纪律、报告字段和排查菜单写入 `docs/state/schema-retrieval-milvus-embedding.md`。
