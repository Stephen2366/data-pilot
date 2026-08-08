# M26 Diagnostic Case 体系整理笔记

> 用途：记录当前 formal / challenge / diagnostic case 体系的特点、历史遗留问题和候选重构方向，供后续会话制定实施计划。
>
> 当前只做分析与方案整理；**尚未批准修改 case、scorer、runner、数据库 fixture 或正式评测口径**。后续可以建立全新的评测合同，不要求与旧基线数字兼容。

## 当前三类评测的结构

当前三层不是三套独立题目，而是逐层包含：

```text
formal 10
  ↓ 语义上被包含
challenge 16 = formal 的 10 个语义问题 + 额外复杂题
  ↓ 文件级合并
diagnostic 32 = challenge 16 + diagnostic extra 16
```

### Formal：10 条基础回归题

特点：

- 覆盖简单查询、GMV、净收入、商品 Top 5、优惠券渠道和基础安全阻断。
- 主要使用 `expected_value`、`result_match` 和 `sql_guard_block`，自动判定程度较高。
- 原定位是少量主线硬门，便于快速发现基础能力回归。

当前问题：

- 这 10 条在 challenge 中大多已有语义等价版本，只是 case ID 不同。
- 例如 `p3a_agg_001` 与 `db_core_001` 都测试六月 GMV；`p3a_multi_001` 与 `db_multi_001` 都测试优惠券使用最多渠道；`p3a_sec_001` 与 `db_sec_001` 都测试 DROP 阻断。
- formal 与 challenge 分开执行时，同一个业务问题会重复调用 LLM。由于真实 LLM 非确定，两次结果不同并不一定代表某项能力退化。

### Challenge：16 条复杂业务题

特点：

- 包含 formal 的主要语义问题，并增加复杂 Join、退款率、整单退款归因、递归类目、SCD 价格历史和安全边界。
- 更接近真实数据库业务口径，适合暴露“SQL 能运行但业务上算错”的问题。

当前问题：

- 混入 `db_hard_001`、`db_hard_003` 等 manual case。
- 这些题会真实运行 pipeline，但自动 scorer 不负责最终语义判定，只进入人工复核队列。
- 随着 DataPilot 的数据库事实源、业务指标和 counterfactual 越来越完整，部分题的合同已经明确，不应继续长期停留在 manual 状态。

### Diagnostic：32 条能力诊断题

当前 diagnostic 是 challenge 16 与 diagnostic extra 16 的合并。

新增的 16 条主要从不同阶段检查系统：

- Schema Retrieval / Schema Context；
- Join Path；
- QueryPlan；
- Local Schema Prompt；
- Trace Steps；
- Security Guard。

问题是：很多 diagnostic extra 并不是新的业务问题，而是对 challenge 中相同业务问题换一个检查角度。例如：

- 六月 GMV：结果题 + trace 题；
- 渠道 GMV：结果题 + plan 题；
- 商品 Top 5：结果题 + schema prompt 题；
- 优惠券使用最多渠道：结果题 + trace 题；
- 价格历史：manual 题 + schema context 题。

当前 runner 会把这些当成独立 case，再次调用 LLM。因此结果题通过、trace 题超时，并不能直接证明 trace 能力更差，也可能只是第二次外部调用发生了波动。

## 当前人工题混合了不同含义

现有 `manual_review` / `review_required` 大致包含三类完全不同的情况：

1. **业务合同确实尚未确定**
   - 需要产品或业务确认采用哪一种口径。
   - 这种题适合保留在人工实验区。

2. **业务合同已经明确，但自动 scorer / oracle 尚未实现**
   - 例如递归类目、SCD 半开区间、商品退款归因。
   - 这类题应逐步补 deterministic oracle 或 counterfactual，不应永久作为 manual case。

3. **系统明确不支持，预期行为就是阻断**
   - 例如不存在的知识库到订单归因关系、当前不支持的多步查询。
   - 这类应当是自动 `expected-block`，而不是人工判断题。

把三者统一显示为 `review_required`，会让人工题数量、系统失败数、业务语义错误和未来能力素材混在一起。

## 推荐方案：唯一场景 + 多断言 + Suite 选择器

不建议只在现有三个 YAML 中删除一些重复题。根本原因是当前一个 `EvalCase` 主要突出一个 `check_type`，为了分别检查 Result、Plan、Context 和 Trace，只能复制同一个业务问题。

建议建立新的 canonical scenario 结构：

```yaml
scenario_id: june_channel_gmv
question: 2026 年 6 月各渠道 GMV 排名
assertions:
  - result_match
  - output_contract
  - schema_context
  - query_plan
  - trace_complete
```

同一个业务问题只执行一次 LLM 请求，然后让多种 assertion 共同消费这一份 Trace、SchemaGraph、QueryPlan、SQL 和执行结果。

主要收益：

- 消除 formal / challenge / diagnostic 中的重复 LLM 调用；
- 同一次执行的 Result、Plan、Context、Trace 可以直接对齐；
- 避免把两次请求的随机波动误解释成能力差异；
- 一道题只有一个题面、业务合同和 reference，降低长期漂移；
- 人工审查也只需审一份完整证据。

## Suite 改成选择器，不再复制题目

建议的新评测入口：

### Smoke

- 从 canonical scenarios 中选择少量便宜、稳定的题。
- 只确认 API、Trace、SQL Guard、执行和报告链路是否正常。
- 不代表完整业务能力。

### Core

- 生产主链路必须稳定通过的自动题。
- 只收录业务合同明确、可用 deterministic oracle 或结构化安全合同判定的场景。
- 作为主要回归与模型 A/B 的统一入口。

### Stress

- 复杂 SQL、数据库异常、递归、SCD、退款归因和多表放大等困难场景。
- 尽量自动判定，但不要求和 Core 使用同一个通过门槛。
- 用于观察复杂能力，而不是复制 Core 的简单题。

### Manual Lab

- 只保留业务合同确实未确定、没有可信 oracle 或用于探索未来能力的题。
- 单列人工 verdict 和审查队列，不进入自动 pass rate。

### Reliability

- 选择历史慢题或容易发生 provider failure 的场景。
- 专门统计成功率、阶段耗时、timeout、retry 和成本。
- 不与 SQL 语义正确率混成同一个分数。

`database-exception-suite` 等专项也应变成标签或场景 ID 选择器，复用 canonical scenario，而不是复制 case 定义。

## Diagnostic 应变成报告视图

Diagnostic 不必继续作为“再运行一套额外题”的入口，而应当是对同一次 Core / Stress 执行的多维分析视图。

建议同时报告：

- 业务答案正确率；
- SQL 生成成功率；
- provider availability；
- Schema Context 合同通过率；
- QueryPlan 合同通过率；
- Output Contract 通过率；
- SQL Guard 安全通过率；
- Trace 完整率；
- manual pending 队列。

这些指标使用各自明确的分母，不再压缩成一个含义混乱的 diagnostic 总分。

## 当前人工题的初步去向建议

- `db_hard_001`：递归类目与 `item_gmv` 合同已经明确，建议转成自动结果 oracle。
- `db_hard_003`：SCD 半开区间和排序已经明确，建议补 NULL / 月末边界 fixture 后自动化。
- `db_join_003`：商品退款归因合同已经明确，建议复用 `db_core_002` 的整单退款 counterfactual 自动验证。
- `db_plan_003`：若知识库文档与订单没有受支持的归因关系，应改成自动 expected-block。
- `db_plan_004`：当前明确不支持 multi-step，应保持自动 expected-block。
- `db_prompt_002`：不能只检查 SchemaContext；应与价格历史 canonical scenario 合并，同时检查 Context 和最终结果。
- 真正进入 Manual Lab 的题，只应是业务合同尚未确定或暂时不存在可信 oracle 的场景。

## 推荐的最终结构

```text
canonical scenarios
├── core              自动、稳定、生产主链路
├── stress            自动、复杂、数据库边界与异常
├── manual-lab        真正无法自动裁决的探索题
├── smoke view        从 canonical scenarios 选少量题
├── reliability view  选择外部调用压力题
└── diagnostic report 对同一次执行按能力维度切片
```

## 候选实施顺序

1. 盘点当前所有 case，按 `semantic_group_id` 合并成唯一业务场景，并人工确认每个场景的权威题面和合同。
2. 将现有单一 `check_type` 设计为 `assertions[]`，明确 assertion 的依赖证据和独立分母。
3. 建立 Core / Stress / Manual Lab 分类；Smoke、Reliability、异常专项改为 selector。
4. runner 对每个 canonical scenario 只调用一次 pipeline，并让多个 assertion 共享同一份证据。
5. 重写报告，使 semantic、availability、plan、context、trace、安全和 manual 队列分开统计。
6. 更新 M26 audit pack，使人工审查以 scenario 为单位，并能逐 assertion 对账。
7. 将旧 formal / challenge / diagnostic YAML 和旧报告作为历史档案保留，但不承担新系统兼容责任。
8. 建立新的 case contract version，从干净的新基线开始，不与旧 formal/challenge/diagnostic 通过率强行比较。

## 当前建议

建议采用“**唯一场景 + 多断言 + suite 选择器 + diagnostic 报告视图**”的正式重构方案。

现在 DataPilot 已具备更完整的数据库事实源、指标合同、Trace、Plan、Context scorer、SQL Guard、counterfactual 和人工审计能力。继续维护旧三层包含结构，会让重复请求、随机波动和混合分母越来越难解释。既然不再要求兼容旧基线，当前正适合建立一个干净的新评测合同。
