# M25 规划前置上下文（2026-08-07）

> 用途：供新会话快速制定 M25 计划。本文是规划交接材料，不代表 M25 范围已经由用户最终确认，也不替代项目状态事实源。

## 0. 新会话必读顺序

1. `AGENTS.md`
2. `docs/state/AI_CONTEXT.md`，并按其中必读规则继续读取：
   - `docs/state/runbook.md`
   - `docs/state/eval-baselines.md`
   - `docs/state/schema-retrieval-milvus-embedding.md`
   - `docs/state/database-current-state.md`
   - `docs/state/AI_CONTEXT_CHANGELOG.md` 中 M23/M24 记录
3. `docs/phase3b-langfuse-plan-v6.md` 的 M24/v6.7；当前文件尚未正式定义 M25，不能把本文建议当成已批准计划。
4. `docs/notes/m24-notes.md`
5. `eval/reports/m24-ab-execution-manifest.md`

## 1. 当前状态与核心结论

- M24 **SQL Plan Contract Semantic Equivalence / Plan-to-SQL Fidelity** 已完成代码、六次受控 diagnostic 和收尾文档，尚待 `accept-module`。
- M24 focused：`70 passed, 1 warning`；全仓 pytest：`176 passed, 1 warning`。warning 为既有 Starlette/httpx deprecation。
- M24 AST fidelity 已消除历史上可确认的表别名、quoted identifier、唯一限定名省略和 SELECT alias 误拦；六次有效 run 中没有出现新的 `semantic_false_block`。
- 当前稳定问题已经从“字符串合同误拦”转向：
  1. eval 题面与 expected contract 是否一致；
  2. QueryPlan 输出投影过宽；
  3. 退款率、递归类目等真实业务语义；
  4. Qwen 固定 45 秒超时；
  5. manual case 与 LLM-as-Judge 的边界。
- 当前默认仍为：Qwen `qwen3.7-plus` + `inmemory + deterministic + weighted`。Milvus/Qwen embedding 只作显式实验路径。
- 不能把一次或少量端到端 LLM 分数直接解释成 embedding 能力。

## 2. M24 六次受控 A/B 事实

固定条件：Qwen `qwen3.7-plus`、weighted、32 条 diagnostic、195-doc corpus/hash、SQLite deterministic oracle、LangFuse disabled。

| 链路 | 三次总分 | 三次自动能力 | manual/diagnostic |
|---|---|---|---|
| Local：in-memory + deterministic | `24,24,25/32` | `21,21,22/27` | `3,3,3/5` |
| Milvus + DashScope/Qwen embedding | `25,25,25/32` | `22,22,22/27` | `3,3,3/5` |

解释边界：

- `22/27` 是 **automated capability pass rate**，不是纯 SQL 答案正确率。27 条中包含安全、Context、Plan、Trace、JoinPath 和结果题。
- 32 条 diagnostic 也不是 32 个完全独立的自然语言问题：formal/challenge 有重复或等价题，`db_multi_001` 与 `db_trace_002` 使用同一个问题但检查目标不同。
- provider timeout 当前会计入 end-to-end failure；它反映服务可靠性，但不等同 SQL 语义错误。
- manual/review 不能当稳定自动正确率。

## 3. Milvus + embedding 链路现状

### 3.1 工程健康状态

M24 collection：

```text
datapilot_schema_docs_m24_qwen_weighted_20260806_194900
```

- M1/M2/M3 最终 `row_count=195`。
- M1 插入 195 条；M2/M3 插入 0 条并复用同一 clean collection。
- Schema 文档 hash 与 1024 维 Qwen embedding 配置一致。
- M20 的重复灌入问题已由 row count/dimension 护栏解决。
- M23 又补了 `schema_docs_hash` 校验，防止“行数相同但文档内容已变化”时误用旧向量。

结论：当前 Milvus 的主要问题已经不是 collection 污染、重复写入或版本错配。

### 3.2 能力证据

历史 retrieval-only benchmark：

- deterministic vector-only recall：`0.787`
- Qwen embedding vector-only recall：`0.929`
- weighted merged recall：两者均为 `0.738`
- RRF 可把离线 merged recall 提高，但端到端 A/B 没有稳定收益，曾出现 `21/32 → 20/32` 或更差结果。

因此当前最稳妥的判断是：

> Qwen embedding 有更强的向量召回信号；现有 fusion/排序未稳定把它转化为端到端收益。M24 三次 Milvus 自动分高约 1 分仍不足以证明 embedding 的因果收益，也不足以切默认。

若 M25 继续研究检索，应优先隔离 retrieval evidence，不能直接继续调 embedding/RRF 后只看总分。

## 4. 当前失败 case：证据、归因与候选优化

### 4.1 自动评分 case

| Case | 六轮观察 | 当前最可能归因 | M25 候选动作 |
|---|---|---|---|
| `db_simple_001` | 六次均首行不匹配；计划只有 `LIMIT 10`，没有排序 | **题面/评测合同缺口优先**：题面只说“active 商品列表前10条”，expected SQL 隐含“商品名称升序” | 题面明确排序；不要让模型猜隐藏顺序。改合同后重建基线，不能回填旧分数 |
| `db_simple_002` | 六次均返回 7 列、6681 行；expected 要 3 列、支付时间升序、LIMIT 10 | **题面/评测合同缺口 + QueryPlan 投影过宽**：题面只说“查询6月成交订单”，没有明确列、顺序和条数 | 题面明确“仅返回哪3列、按何顺序、取多少条”；随后观察 planner 是否仍过宽 |
| `db_simple_003` | 六次均返回优惠券 10 个字段；expected 只要 3 列 | **题面/评测合同缺口优先**：“基本信息”无法唯一推出固定3列 | 明确列名，或产品上明确一套可追溯的“基本信息”默认投影；不要同时保持模糊题面和精确 scorer |
| `db_core_002` | 六次均失败：有真实退款率错误、一次真实 fidelity mismatch，也有多次 45 秒超时 | **真实业务语义 + provider reliability** | 强化“明细优先、整单退款回退” metric/plan/few-shot；修复分母绑定；把 timeout 与 semantic failure 分开 |
| `db_multi_001` / `db_trace_002` | 各 5/6；失败 run 使用正确表达式但 alias 为 `coupon_usage_count`，白名单只含 `usage_count/used_order_count` | **alias 政策缺口或 canonical name 未落实** | 二选一：显式加入 `coupon_usage_count`；或让 QueryPlan/prompt 强制 canonical `coupon_order_count`。先确认产品政策 |
| `db_multi_002` | 六次均失败；正确生成时只过滤 `level=1`，没有递归回溯；多次又在 QueryPlan 阶段超时 | **题面缺口 + 递归类目能力缺口 + timeout**：题面没写六月，expected SQL 隐含六月过滤 | 先补题面时间；再做 recursive CTE/derived scope fidelity spike，不能直接修改生成器后被 M24 合同拦下 |

重要判断：前三个 simple case 和 `db_multi_002` 暴露出 expected SQL 中存在题面未声明的约束。当前分数可能因此偏低，但不能简单把这些 case “加回通过”；应先修订题面/合同，再在新合同下重跑。

### 4.2 Manual / diagnostic case

| Case | 六轮观察 | 当前最可能归因 | M25 候选动作 |
|---|---|---|---|
| `db_hard_001` | 多数 run 使用 `orders_wide.order_amount`，而期望是类目树 + `order_items.line_amount`；另有一次 timeout | **真实语义路径错误**，但属于 manual | 递归类目树 + item_gmv focused spike；先确认 M24 fidelity 对 CTE/derived scope 的扩展边界 |
| `db_hard_003` | 多数 run 已生成与现有 reference 接近的 SCD 时间窗口 SQL，但一直 manual review | **业务定义未唯一**：“平均售价”可能是价格记录平均、时间加权平均或成交均价 | 先确认业务定义并改清题面；能唯一判定后再升级为 `result_match` |
| `db_join_003` | 六次全部在 QueryPlan 阶段约 45 秒 timeout | **稳定运行可靠性失败，不是已证明的语义失败** | 增加 timeout/retry/attempt/prompt-length 证据后再判断模型能力；不要先改 refund SQL |

## 5. Qwen 超时事实与可观测性缺口

M24 多个复杂 case 出现固定约 45 秒的：

```text
Qwen 网络调用失败：The read operation timed out
```

受影响 case 包括 `db_join_003`（6/6）、`db_core_002`、`db_multi_002`、`db_hard_001`。当前 trace 能看到 stage 和 latency，但部分网络异常路径没有保存 prompt length、attempt count 等上下文。

M25 应先回答：

- 45 秒是否只是客户端默认值过短？
- 超时是否与 Schema Context/prompt 长度相关？
- 是否集中在 QueryPlan，还是 SQL generation 也存在？
- provider 是超时前无响应，还是响应体生成过慢？
- 有限 retry 后成功率与额外延迟/成本如何？

建议增加：可配置 timeout、只对幂等 LLM 请求执行有限 retry/backoff、attempt count、每次 attempt latency、prompt length、provider/model 和稳定 error subtype。不能仅调大 timeout 后隐藏问题。

## 6. Eval 当前完成度与仍需审计的风险

### 6.1 已经比较完整的能力

- Context / Output / Result / Manual 分层
- SQL Guard、安全题与结构化拒绝
- SchemaGraph trace 评分
- reference SQL 的 `result_match` / `expected_value`
- 精确输出投影与显式 alias 白名单
- M24 QueryPlan→SQL AST fidelity
- failure stage/subtype/needs_action
- JSONL trace、Markdown report、triage JSON
- SQLite deterministic oracle
- M23 reference SQL 的 SQLite/MySQL 双端可执行审计
- Milvus row count/dimension/hash 审计
- automated 与 manual/diagnostic 分开展示

### 6.2 不能宣称“Eval 已完全无误”的原因

1. **题面与 expected contract 不一致**：部分题目隐藏了排序、LIMIT、时间范围或精确列。
2. **总分含义混杂**：`22/27` 同时包含答案、安全、Context、Plan 和 Trace，不应称为纯 SQL 正确率。
3. **重复/等价题**：32 条不是 32 个独立语义样本。
4. **timeout 混入能力失败**：应区分 semantic accuracy、provider availability 和 end-to-end pass rate。
5. **alias 白名单可能不完整**：`coupon_usage_count` 是已出现的实际例子。
6. **固定 seed 的局限**：错误 SQL 可能在单一 seed 上碰巧得到相同结果；题面模糊时合理 SQL 也可能被 reference 误杀。
7. **reference SQL 双端可执行不等于业务定义必然正确**：可执行审计降低方言风险，但业务口径仍需人工确认。
8. **manual case 仍未形成稳定自动结论**：部分 manual case 会先被 table/column 规则标记失败，诊断有用，但不能当确定的语义错误。
9. **早返回/首失败归因**：报告主要展示第一个失败，可能掩盖同一 case 的次级错误；逐 case 优化时仍需看完整 trace/score details。

建议把后续报告拆成至少五个视图：

- `semantic_answer`
- `safety`
- `plan_and_trace`
- `provider_reliability`
- `manual_or_judge`

同时明确 independent question count、重复/linked case group、timeout count 和 parse error count。

## 7. 当前检查器与 LLM-as-Judge

### 7.1 当前默认不是 LLM-as-Judge

主链路是确定性分层检查：

1. L1：HTTP/route、安全、table/column、Schema Context、Plan/Trace 结构；
2. L2：`expected_value`、`result_match`、SQLite reference result、精确 projection；
3. M24 AST fidelity：ORDER BY 表达式/方向/顺序、LIMIT、projection、alias/scope。

项目已有可选 `llm:correctness`，通过 `--judge-model` 或 `EVAL_JUDGE_MODEL` 显式开启；M24 六次 A/B 中 Judge 关闭。

### 7.2 建议方向

不建议把安全、结构、固定结果和 AST 合同整体改成 Judge。确定性问题用 LLM 会增加成本、延迟、波动和同模型偏差。

建议只做 **Judge shadow pilot**：

- 先覆盖 `db_hard_001`、`db_hard_003`、`db_join_003` 等 manual case；
- Judge 结果单独报告，不改变正式 automated pass/fail；
- 使用人工标注校准阈值和误判率；
- 给 Judge reference result/业务 rubric，而不只是截断的 reference SQL 和前三行结果；
- 尽量使用与生成模型不同的 Judge，降低相关偏差；
- Judge 不得覆盖安全规则和确定性失败。

现有 Judge 在正式使用前的风险：reference 主要是 SQL 文本、rows preview 只有前三行、阈值 `0.8` 尚未针对本项目人工校准、同 provider 可能产生相关偏差。

## 8. 推荐的 M25 方向（待用户确认）

建议候选名称：

> **M25 Eval Trustworthiness & Failure Attribution Closure**

### 阶段 A：case contract 审计

- 优先审计 `db_simple_001/002/003`、`db_multi_002`。
- expected SQL 中影响结果的列、时间、排序和 LIMIT 必须出现在题面或权威业务默认中。
- 审计 `coupon_usage_count` alias 政策。
- 修订后建立新 baseline；旧 M24 六轮保留为旧合同历史，不回写改分。

### 阶段 B：评分视图与样本独立性

- 拆分 semantic/safety/plan/reliability/manual 五个视图。
- 单列 timeout、parse error、judge unavailable。
- 标识 linked/duplicate/equivalent case，不把它们解释成独立样本。
- 明确 total、automated capability 和纯 answer accuracy 的不同分母。

### 阶段 C：timeout 与 LLM 调用证据

- 可配置 timeout；有限 retry/backoff。
- Trace 增加 attempt count、attempt latency、prompt length、provider/model、error subtype。
- 对复杂 case 做 prompt/context 体积对照，避免只把 45 秒改成更大的魔法数字。

### 阶段 D：两个 focused capability spike

1. `db_core_002`：退款率 metric、整单退款回退、分母和 join path。
2. `db_multi_002` / `db_hard_001`：recursive category tree、CTE/derived scope fidelity 边界。

先做离线正反例和合同 spike，再决定是否进入 pipeline 实现。

### 阶段 E：LLM-as-Judge shadow pilot

- 只评 manual case。
- 与人工标签比较，不影响正式分数。
- 评估不同 Judge、重复判定一致性、成本和延迟。

## 9. 推荐完成门禁

M25 完成时至少应能回答：

1. 每个自动 case 的题面是否完整声明 expected contract？
2. 纯 SQL/答案正确率的独立分母是多少？
3. timeout 与 semantic failure 是否完全分开？
4. duplicate/linked case 是否不再被当成独立能力样本？
5. `db_core_002`、`db_multi_002` 的失败分别位于 metric、plan、fidelity 还是 generation？
6. recursive CTE 进入 pipeline 后，M24 fidelity 是否有可信正反例？
7. Judge 对 manual case 与人工标签的一致性如何，是否值得推广？
8. 在新合同下，Local/Milvus 是否仍有稳定、可归因差异？

## 10. 建议顺序与暂不做事项

建议顺序：

```text
accept M24
→ M25 case/eval 可信度审计
→ timeout/可观测性修复
→ refund + recursive category focused spike
→ Judge shadow pilot
→ 新合同下重建基线
→ 再决定后续优化 QueryPlan、embedding 或 rerank
```

M25 规划前不建议直接做：

- 不直接切默认 Milvus/Qwen embedding/RRF。
- 不把当前 `22/27` 描述成纯 SQL 正确率。
- 不用一次 LLM run 决定 embedding 优劣。
- 不直接扩大 AST 到所有 CTE/derived scope；先做正反例 spike。
- 不让 LLM Judge 覆盖安全、结果和 AST 硬规则。
- 不根据修订后的 case 反向篡改 M24 历史分数。

## 11. 工作区提醒

创建本文时工作区仍有 M24 收尾文档、少量注释和评测报告未提交；另有用户修改过的 `.claude/skills/finish-docs/SKILL.md`。新会话开始时必须先运行 `git status --short`，不得覆盖或回滚这些现有改动。
