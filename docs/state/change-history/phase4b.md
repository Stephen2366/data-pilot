# DataPilot AI Context Changelog — Phase 4B

> Phase 4B 的新记录写入本文件头部；阶段结束后再将本文件转为历史档案。
>
> 本文件保存 Phase 4B（M41 起，对应 `docs/phase4b-roadmap.md`）的模块档案、实验记录和技术取舍，按时间倒序排列。Phase 4（M29–M40）历史仍见 `change-history/phase4.md`。当前项目状态以 `docs/state/AI_CONTEXT.md` 为准；跨阶段索引见 `docs/state/CHANGELOG_INDEX.md`。
>
> 默认先按模块号、日期或关键词定位，再读取相关章节，不要无差别全文读取。新结论修正本阶段旧判断时，应在旧条目原位添加 `⚠️ 注`。

标题标签：

- `[模块任务]`：功能、架构、默认行为、安全口径、评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM Eval、smoke 或会影响路线判断的实验结论。
- `[验收]`：accept-module、阶段验收或明确的完成状态。
- `[小修]`：文档措辞、口径同步、注释补充、轻量整理；只需简写，不要求完整模板。

「变更记录」：小修可以只写一段话；较大的任务建议包含：改动范围、关键记录（比如关键决策、决策原因、实验结果、新发现、用户做出的选择等）、参考资料、验证快照、遗留/后续。

同一模块 / 同一阶段内连续的小修（中间没有被 [模块任务] / [实验] 等其他类型条目隔开时），合并到一个 [小修] 小节。

## 变更记录（新的在上）

### [实验] M41 首次真实 LLM smoke（2026-08-22）

- 按用户一次授权，使用当前默认 `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`、M27 v3 `smoke` selector 执行恰好一次；未扩大到 core/stress/reliability，也未重复运行。
- run：`m41-real-llm-smoke-20260822-01`；4 个逻辑 Scenario、4 个 physical attempts。`june_gmv` 与 `active_products_top10` 到达 LLM generation，但均为 `external_unavailable / network_error`；`unsafe_drop_orders` 与 `missing_product_supplier_rejection` 在确定性安全/计划合同处拒绝并通过对应 required assertion。
- 结果：run `completed`，Gate `inconclusive`（required passed=2、failed=0、not_observed=7；logical completed=2、external unavailable=2）。本次没有成功的模型输出可用于 Text2SQL 质量结论，`inconclusive` 不能当作通过或失败。
- artifact/report：`eval/reports/m27-artifacts/m41-real-llm-smoke-20260822-01.json`、`eval/reports/m41-real-llm-smoke-20260822-01.md`；run spec hash `bd3ce4aefd4ccebfad5ecd364548aeec87deb49ee931d80000c2b6139e98d07f`。
- 遗留：需另行诊断 provider/network 出站问题；未经新的明确授权不得重跑或扩大 suite。此次真实模型 smoke 与 M35–M40 deterministic contract/assurance Eval 分账，不改默认模型或路线。

### [小修] Status 文档标注路线升格（2026-08-22）

- `docs/notes/phase4-rag-capability-status.md` 头部与第 12 节标注：方案已于 2026-08-22 经用户确认升格为 `docs/phase4b-roadmap.md`，第 1–11 节转为演进记录；修订记录同步补一条。仅文档标注，不改变任何运行事实或路线内容。

### [小修] 新建 Phase 4B 历史档案并切换索引写入目标（2026-08-22）

- `docs/state/CHANGELOG_INDEX.md` 的当前写入目标由 Phase 4 切换为 Phase 4B，并新增阶段索引行：Phase 4B（M41 至当前）→ `change-history/phase4b.md`；Phase 4 行范围收口为 M29–M40。
- `change-history/phase4.md` 转为历史档案（Phase 4 收口于 M40），不再承接新条目；其中 2026-08-22 的 Phase 4B 立项相关既有条目（候选方案审查小修、Roadmap 正式立项模块任务）保留原位，不迁移。
- 本次只重组 changelog 路由，不改变任何运行配置、Eval 结果、历史结论或 `docs/phase4b-roadmap.md` 内容。
