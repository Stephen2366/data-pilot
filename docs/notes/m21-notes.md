# M21 Schema Retrieval Fusion / Context Repair Notes

## 模块名称与改动文件清单

- 模块：M21 Schema Retrieval Fusion / Context Repair。
- 本模块代码 / 测试：`engine/schema_retrieval/retriever.py`、`engine/nl2sql/pipeline.py`、`app/schemas/agent.py`、`app/api/query.py`、`eval/run_schema_retrieval_benchmark.py`、`eval/run_eval.py`、`tests/test_phase3a_schema_retrieval.py`、`tests/test_schema_retrieval_embedding_benchmark.py`。
- 本模块素材：本文件及 `.agent_work/temp/m21-*.md/json` 报告。`docs/dev-log.md` 的既有未提交改动不属于本模块，未触碰。

## 关键决策与取舍

- 保持 `weighted` 为默认 fusion，不改默认 `retrieve_schema()`、默认 embedding、Milvus 默认值、正式 case 或 scorer/oracle。理由：这些属于长期基线；M21 先证明候选收益。
- 新增显式 `rrf` 参数，贯通 retrieval benchmark、eval CLI、API request、pipeline trace metadata。它只读取 question / candidate hit 的分数或 rank，绝不读取 `expected_tables`、`expected_columns`、metric/relation 等 benchmark 标注；避免标签泄漏。
- 候选选择门槛：固定 `schema_docs_hash=7b531e073fa0b2dfaae205097b8440c44b745234305396b5f185561dcf9cc644`、Qwen embedding 1024 维、同一 clean collection `datapilot_schema_docs_m21_qwen_weighted_20260803_001`、`top_k=12` 和固定 10 条 retrieval case；先看 relation / metric recall，再做同配置 DeepSeek diagnostic。
- 用户未被要求确认长期策略：本次仅增加显式实验开关，最终结论是 RRF **不升级为默认**。

## 实验结果与失败 case 观察

- deterministic retrieval-only：weighted merged overall `0.738`、metric `0.600`、relation `0.633`；RRF 为 `0.802`、`0.700`、`0.767`。
- Milvus + Qwen embedding retrieval-only（row_count=193）：weighted merged overall `0.738`、metric `0.600`、relation `0.633`；RRF 为 `0.929`、`0.900`、`0.967`。vector-only 仍为 `0.929`，说明 RRF 能把 vector 信号带入 merged context。
- 同配置 DeepSeek diagnostic：weighted `21/32`，RRF `18/32`。triage 对比中 `schema_context 5→4`，但 `plan_validation 0→3`、`query_plan 3→4`、`schema_retrieval 0→1`；RRF 的离线 recall 收益没有稳定转化为端到端收益。
- 结论：RRF 记录为否定实验；默认 `weighted` 保持不变。下一步先逐 case 分析 RRF 改变的 context assembly / prompt 耦合，不直接调高 top_k、不新增 bundle docs、不引入 reranker。

## 阶段 1 注释小结

- 覆盖扫描：本模块新增 / 修改的业务函数、CLI 参数和测试函数均已有模块级或函数级中文说明；0 处缺失。
- 质量扫描：补充了 RRF 与 weighted 分数可比性、显式实验开关、标签泄漏边界、deterministic 基线也必须写 `schema_docs_hash` 的设计理由。
- 内部可读性：`_merge_hits()` 为融合分计算添加步骤注释；benchmark metadata 构建处增加“为什么 deterministic 也要记录 hash”的 ★ 注释。
- 形式扫描：新增注释均以中文为主，分隔线只用于融合关键步骤；无额外格式调整。

## 阶段 2 验证快照

- focused tests：`pytest tests\\test_phase3a_schema_retrieval.py tests\\test_schema_retrieval_embedding_benchmark.py -q --basetemp=.agent_work\\temp\\pytest-m21-final-focused` → `16 passed, 1 warning`。
- related tests：`pytest tests\\test_phase3a_pipeline.py tests\\test_phase3a_schema_retrieval.py tests\\test_schema_retrieval_embedding_benchmark.py -q --basetemp=.agent_work\\temp\\pytest-m21-related` → `22 passed, 1 warning`。
- full pytest：首次 `.agent_work\\temp\\pytest-m21-full` 在 300 秒命令上限超时，只有进度点、无失败栈；使用新目录复跑 `pytest -q --basetemp=.agent_work\\temp\\pytest-m21-full-retry` → `133 passed, 1 warning`，耗时 `376.77s`。
- retrieval-only 四份报告：`.agent_work/temp/m21-baseline-deterministic-weighted.md`、`m21-candidate-deterministic-rrf.md`、`m21-baseline-qwen-milvus-weighted.md`、`m21-candidate-qwen-milvus-rrf.md`。Milvus 两份均为 collection row_count `193`、schema docs hash `7b531e...`。
- diagnostic A/B：weighted report / triage 为 `.agent_work/temp/m21-deepseek-weighted-diagnostic-report.md` / `-triage.json`，`21/32`，耗时 `845.3s`；RRF 为 `.agent_work/temp/m21-deepseek-rrf-diagnostic-report.md` / `-triage.json`，`18/32`，耗时 `672.0s`；分布对比 `.agent_work/temp/m21-deepseek-weighted-vs-rrf-triage-compare.md`。
- `git diff --check`：最终无 whitespace error；Windows LF/CRLF 提示不属于 whitespace error。
- warning：既有 Starlette/httpx `TestClient` deprecation warning，不影响 M21。

## 参考资料

- 无外部资料。设计依据是 M21 计划、M19 triage 口径、M20 clean Milvus / Qwen embedding benchmark 证据和项目现有 `SchemaHit.rrf_score` 预留字段；未引入 LLM / cross-encoder reranker。

## 遗留 / 后续

- 不把 RRF 切默认。RRF 在 retrieval-only 上有效、在一次同配置 diagnostic 上退化，真实 LLM 非确定性仍存在；若要继续，需要先审查逐 case context / QueryPlan，而不是重复刷分。
- relation / metric bundle docs、doc_type weighting、context token budget、top_k、正式 reranker 和默认 embedding / Milvus 都属于需单独确认的长期选择。

## M21 follow-up：Qwen 主模型 pilot（2026-08-03）

- 用户要求先不改默认，验证 `qwen3.7-max` 是否比 `deepseek-v4-flash` 更适合作为主模型；本次只固定 clean Milvus + Qwen embedding + fusion 参数做外部 eval。
- 32 条 diagnostic 的 Qwen weighted run 在约 15 分钟命令上限内未生成报告；缩小到 16 条 challenge-only weighted pilot 后仍长时间无产物，已停止进程。
- 没有新增有效分数，因此不启动 RRF 对照，也不改变默认模型 / fusion。历史 M20 Qwen `21/32` 仍保留为可用基线；本次只能记录端点稳定性阻塞，不能据此判断 Qwen 优劣。

## M21 follow-up：健康检查与 32 条重测结果（2026-08-03）

- 最小 JSON health check 通过，耗时 `6.57s`；key、模型名、代理和 DashScope 路由正常。
- 32 条 weighted 重测完成，结果 `11/32`。但 `query_plan` 有 12 条 `llm_generation_error`，多数请求耗时约 `45.4s`，正好撞上客户端固定的 `45s` timeout；因此该分数不能直接与 M20 `21/32` 比较。
- 产物：`.agent_work/temp/m21-qwen-health-weighted-diagnostic-report.md`、`-triage.json`、`-traces.jsonl`。
- 后续若要公平比较，应先由用户确认是否调整单请求 timeout / 总耗时策略；不在本次自行改默认配置。

## M21 follow-up：qwen3.7-plus 对照（2026-08-03）

- 只通过命令环境变量切换 `QWEN_MODEL=qwen3.7-plus`，未修改 `.env` 或默认模型；clean Milvus、Qwen embedding、weighted 和 32 条 diagnostic 保持一致。
- health check `5.04s` 通过；完整 diagnostic `21/32`，平均 latency `38.9s`、P50 `38s`、P95 `65.8s`。
- 失败主要转为 `schema_context=6`、`schema_retrieval=2`、`unknown=2`；仅 1 条 query_plan 和 1 条 sql_generation LLM error。相比 qwen3.7-max 的 `11/32`（12 条 query_plan timeout 型失败），plus 在当前客户端 timeout 下更稳定。
- 结论：plus 与 M20 max 同为 `21/32`，但 plus 更适合作为下一轮候选主模型；仍不直接切默认，后续应先确认是否要做重复 run 或调整 timeout 以降低单次 LLM 非确定性。

## M21 proper A/B：qwen3.7-plus weighted vs RRF（2026-08-03）

- 固定 qwen3.7-plus、同一 clean Milvus、Qwen embedding、32 条 diagnostic，只改变 fusion。
- weighted `21/32`；RRF `20/32`。triage：schema_context `6→5`，但 query_plan `1→2`、result_match `1→2`；schema_retrieval `2→2`、sql_generation `1→1`。
- 结论：RRF 在 plus 端到端 diagnostic 上仍未带来收益，weighted 默认结论得到同模型 A/B 支持。
- 产物：`.agent_work/temp/m21-qwen-plus-rrf-diagnostic-report.md`、`-triage.json`、`-traces.jsonl`、`m21-qwen-plus-weighted-vs-rrf-compare.md`。

## M21 后续：逐 case Context 地基体检（2026-08-03）

- 对齐 plus weighted / RRF 的 32 条 trace、triage 和 retrieval metadata，生成 `.agent_work/temp/m21-context-audit.md`。
- 关键发现：当前 `schema_context` 是 triage 的 schema 相关失败桶，不等于“上下文丢字段”。`eval/triage.py` 把 `rule:column_recall` 映射到 `schema_context`，但 scorer 实际检查的是最终响应 `body.columns`；pipeline trace 只记录 SchemaGraph 的表名、字段总数和指标名。
- weighted 失败样本中，`expected_tables` 均已进入 `schema_context.metadata.tables`；`db_core_002`、`db_multi_001`、`db_prompt_001` 等更像 SQL 输出表 / alias / scorer 契约问题，不能直接归因 embedding 或 retrieval。
- RRF 确实改变了 context 组成，部分 case 引入额外表 / metric，但 plus 端到端仍从 `21/32` 降为 `20/32`；当前没有证明 RRF 修复了真实 context 丢失。
- 本轮只做离线诊断，没有改代码、默认配置、正式 case、scorer 或 oracle；下一道门是补齐 `expected_tables / SchemaGraph.tables / body.tables_used / body.columns` 对齐，再决定是否需要诊断字段增强或进入 M22 方法实验。
- 进一步核对 `engine/schema_retrieval/graph.py:145-150` 后确认：选中物理表后会把该表完整 domain-schema fields 放入 SchemaGraph；当前没有证据证明 plus weighted 存在“目标字段在 graph 中被截断”的 case。
- M21 地基门禁结论：不再在 M21 临时实现未定位的 rerank / top_k / doc_type weighting；基础链路事实和 triage 归因缺口已记录，后续可在 M22 固定基线下大胆尝试方法。

## M21 follow-up：triage 诊断修正（2026-08-03）

- `eval/triage.py` 保留既有 `failure_stage`，新增 `failure_subtype`：`output_table_contract`、`output_column_contract`、`result_contract`、`scorer_contract`。
- `rule:table_hit` / `rule:column_recall` 仍保留原 stage 供旧报告兼容，但新增 subtype 并将下一步动作标为 `manual_review`；这样最终 SQL 输出表 / 列名不再被直接当成 embedding / Schema Retrieval 失败。
- Markdown triage report 和 A/B compare report 会额外展示 subtype 分布；不改变 scorer 分数、正式 case、oracle、默认配置或 LangFuse score 数量。
- 验证：`pytest tests\\test_m19_failure_triage.py -q --basetemp=.agent_work\\temp\\pytest-m21-triage-subtype-final` → `7 passed, 1 warning`；相关回归 `tests\\test_m19_failure_triage.py tests\\test_phase3a_pipeline.py` → `13 passed, 1 warning`。

## M21 finish-module follow-up 收工快照（2026-08-03）

### 模块范围

- 本次 follow-up 相关文件：`eval/triage.py`、`eval/run_eval.py`、`tests/test_m19_failure_triage.py`、`docs/phase3b-langfuse-plan-v6.md`、`docs/state/eval-baselines.md`、`docs/state/AI_CONTEXT.md`、`docs/state/AI_CONTEXT_CHANGELOG.md`、`docs/state/schema-retrieval-milvus-embedding.md`、`docs/dev-log.md`。
- 未修改默认模型、默认 embedding、默认 Milvus、默认 fusion、正式 eval case、scorer 或 oracle。

### 阶段 1 注释查漏小结

- 覆盖扫描：本次 diff 中的新增 triage 细分类、报告渲染和测试逻辑均已有中文注释 / docstring；未发现需要补写的缺失项。
- 质量扫描：已解释 `failure_stage` 与 `failure_subtype` 的兼容关系、输出契约为何不能直接等同 retrieval 失败、以及 controlled A/B 为何只改变 retrieval 链路。
- 可读性 / 形式扫描：新增逻辑保持现有命名和报告生成结构；未引入新的复杂分支注释缺口。

### 阶段 2 验证快照

- Qwen-plus 本地 deterministic + weighted diagnostic：`21/32`；报告 `.agent_work/temp/m21-qwen-plus-local-weighted-report.md`。
- Qwen-plus clean Milvus + Qwen embedding + weighted diagnostic：`21/32`；collection row_count `193`、run-scoped；报告 `.agent_work/temp/m21-qwen-plus-qwenemb-weighted-report.md`。
- triage 对比：`.agent_work/temp/m21-qwen-plus-local-vs-qwenemb-triage-compare.md`；两组 `schema_context` 和 subtype 分布相同，只有 3 个 case 失败形态变化。
- 轻量回归：`pytest tests\\test_m19_failure_triage.py tests\\test_phase3a_pipeline.py -q --basetemp=.agent_work\\temp\\pytest-m21-plus-embedding-audit` → `13 passed, 1 warning`。
- 文档检查：`git diff --check` 无 whitespace error；仅有 Windows LF/CRLF 转换提示。唯一 pytest warning 为既有 Starlette/httpx `TestClient` deprecation，不影响本次结论。

### 遗留 / 后续

- M21 embedding 线收口，不能据此宣布 Qwen embedding 端到端胜出；下一模块 M22 先处理 output contract 与 QueryPlan → SQL 稳定性。
- M23 再逐项评估 RRF / rerank 等 retrieval 方法；每次只改变一个变量，保留 retrieval-only 与端到端两层指标。

## M21 follow-up：Qwen-plus 本地 vs Qwen embedding controlled A/B（2026-08-03）

- 用户确认执行一次严格单变量对照：固定 `QWEN_MODEL=qwen3.7-plus`、weighted、`new_text2sql`、同一 diagnostic 32 题、同一 SQLite deterministic oracle、LangFuse disabled；A 为 `inmemory + deterministic`，B 为 clean Milvus + Qwen `qwen3.7-text-embedding` 1024 维。
- A 组 `21/32`：`schema_context=6`、`schema_retrieval=2`、`sql_generation=2`、`result_match=1`、`unknown=2`；subtype `output_column_contract=6`、`output_table_contract=2`、`result_contract=1`。
- B 组 `21/32`：`schema_context=6`、`schema_retrieval=2`、`query_plan=1`、`result_match=1`、`sql_generation=1`、`unknown=1`；subtype 与 A 完全相同。B collection `datapilot_schema_docs_m21_qwen_weighted_20260803_001`，row_count=193、run_scoped、schema hash 一致。
- 逐 case 只有 3 个失败形态变化：`db_hard_001`（schema_retrieval → query_plan）、`db_join_003`（unknown → schema_retrieval）、`db_plan_004`（失败 → 通过）。
- 结论：本次没有观察到可归因于 Qwen embedding 的端到端提分或 subtype 改善；M21 embedding 线收口，M22 先处理 output contract 与 QueryPlan → SQL，M23 再尝试 retrieval 方法。
- 产物：`.agent_work/temp/m21-qwen-plus-local-weighted-report.md`、`m21-qwen-plus-local-weighted-triage.json`、`m21-qwen-plus-qwenemb-weighted-report.md`、`m21-qwen-plus-qwenemb-weighted-triage.json`、`m21-qwen-plus-local-vs-qwenemb-triage-compare.md`、`.agent_work/temp/m21-plus-local-vs-qwenemb-notes.md`。
