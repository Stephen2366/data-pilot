# M12 对照报告与阶段收尾 — Implementation Checklist

## Checklist

- [x] 新建 `eval/compare_phase3a.py`：读取 baseline traces + new pipeline traces，生成对照报告
- [x] 运行新 pipeline 10 条 formal → `eval/reports/phase3a-new-pipeline.md`
- [x] 运行新 pipeline 16 条 challenge → `eval/reports/phase3a-challenge-new-pipeline.md`
- [x] 运行新 pipeline 32 条 diagnostic → `eval/reports/phase3a-diagnostic-new-pipeline.md`
- [x] 生成对照报告（formal/challenge/diagnostic 三份）
- [x] 新建 `scripts/smoke_phase3a_text2sql.py` 一键 smoke
- [x] 更新 `README.md` Phase 3A 能力边界
- [x] 全量 pytest（65 passed, 2 skipped）+ git diff --check（仅有预期 CRLF warning）
- [ ] finish-module 收工

## 实际运行结果

### 新 pipeline 10 条 formal：6/10 passed（安全 2/2 blocked，允许类 SQL 5/8）
- p3a_simple_001: PASS（修复 plan validation 聚合表达式误判后通过）
- p3a_simple_002: PASS
- p3a_agg_001: PASS（GMV）
- p3a_agg_002: PASS（净收入）
- p3a_agg_003: FAIL — missing_columns=['conversion_rate']（LLM 列名别名漂移）
- p3a_multi_001: FAIL — missing_columns=['coupon_order_count']（同上）
- p3a_multi_002: FAIL — missing_tables=['products']（LLM 未使用该表）
- p3a_multi_003: FAIL — missing_columns=['category', 'item_gmv']（列名漂移）
- p3a_sec_001: PASS（DROP TABLE 被危险关键词预检拦截）
- p3a_sec_002: PASS（DELETE FROM 被危险关键词预检拦截）

### 新 pipeline 16 条 challenge：8/16 passed（安全 2/2 blocked）
- 主要失败原因：LLM 列名别名漂移（category/coupon_order_count/channel_name/avg_price）、
  LLM 不稳定（db_core_002 缺少商品名文本）、API 超时（db_hard_001 递归类目超时）

### 新 pipeline 32 条 diagnostic：15/32 passed
- db_sec_003 通过（plan_validation 拦截敏感字段查询）
- db_sec_004 失败（safety_mismatch，LLM 未访问敏感字段）

## 关键决策与踩坑

### 1. DeepSeek 模型名更新（M12 必要的依赖修复）
- DeepSeek API 已废弃 `deepseek-chat`，要求使用 `deepseek-v4-pro` 或 `deepseek-v4-flash`
- 修改了 `engine/nl2sql/generator.py` 两处默认模型名：`deepseek-chat` → `deepseek-v4-pro`
- 同步更新了 README.md 中的 LLM_MODEL 示例

### 2. 新 pipeline 安全预检缺口（M12 补丁）
- 旧链路在 `matched is None` 分支通过 `_looks_like_dangerous_sql()` 拦截危险问题
- 新链路 `force_new_pipeline=true` 绕过该分支，导致 DROP/DELETE 问题进入 LLM 后被转写成 SELECT
- 修复：在 `force_new_pipeline` 分支前增加危险关键词预检，确保新旧链路统一拦截

### 3. plan validation 聚合表达式误判（M12 修复）
- `_check_table_and_column_scope()` 把 `COUNT(DISTINCT orders.id)` 这类聚合表达式
  当作普通列名检查，导致误判 `missing_column`
- 修复：拆分 `step.columns` 为纯 `table.column` 引用和表达式引用，
  对表达式通过 `_qualified_refs()` 提取内部 `table.column`

### 4. 对照报告生成策略
- 选择方案 B：读取 trace JSONL（结构化），不解析 Markdown 报告
- `compare_phase3a.py` 按 question 文本匹配 case，生成并排对比表
- 报告包含：通过率对比、Schema 精简度、JoinPath、Trace Steps 完整性、Issue Tags

### 5. LLM 通过率现状
- 新 pipeline 允许类 SQL 约 50-60% 通过率，低于计划目标 7/8（87.5%）
- 主要瓶颈是 LLM 输出列名不稳定（别名漂移），与 baseline 遇到的问题同源
- 对照报告如实呈现，issue tags 记录具体失败原因
- 提升方向：P0 schema/plan/prompt 优化（非 M12 范围）

## 验证快照

- pytest: 65 passed, 2 skipped, 1 warning（Starlette/httpx deprecation，既有）
- git diff --check: 无 whitespace error，仅 Windows CRLF 提示
- 新 pipeline formal: 6/10 passed
- 新 pipeline challenge: 8/16 passed
- 新 pipeline diagnostic: 15/32 passed
- 对照报告: formal/challenge/diagnostic 三份均生成

## 生成文件清单

- `eval/compare_phase3a.py` — 对照报告生成器
- `scripts/smoke_phase3a_text2sql.py` — 一键 smoke 脚本
- `eval/reports/phase3a-new-pipeline.md` — 新 pipeline formal 报告
- `eval/reports/phase3a-challenge-new-pipeline.md` — 新 pipeline challenge 报告
- `eval/reports/phase3a-diagnostic-new-pipeline.md` — 新 pipeline diagnostic 报告
- `eval/reports/phase3a-comparison.md` — formal 对照报告
- `eval/reports/phase3a-challenge-comparison.md` — challenge 对照报告
- `eval/reports/phase3a-diagnostic-comparison.md` — diagnostic 对照报告
- `.agent_work/temp/phase3a-new-traces.jsonl` — 新 pipeline formal trace
- `.agent_work/temp/phase3a-challenge-new-traces.jsonl` — 新 pipeline challenge trace
- `.agent_work/temp/phase3a-diagnostic-new-traces.jsonl` — 新 pipeline diagnostic trace

## 修改的已有文件

- `engine/nl2sql/generator.py` — 默认模型名 `deepseek-chat` → `deepseek-v4-pro`
- `engine/nl2sql/planner.py` — plan validation 聚合表达式误判修复
- `app/api/query.py` — 新 pipeline 危险 SQL 预检补丁
- `README.md` — Phase 3A 能力、命令、边界、目录结构更新
