# DataPilot Changelog Index（技术历史唯一入口）

> 本文件只负责导航，不保存具体变更记录。无论用户要求“写 changelog / 记录小修 / 记录实验”，还是“查询历史 / 以前怎么做的 / 为什么这样设计”，都必须先读本文件，再进入对应 Phase 文件。
>
> 当前状态和默认配置先读 `docs/state/AI_CONTEXT.md`；设计原因、模块档案、实验过程和旧结论修正再从本索引进入历史文件。

## 路由规则

- **新增记录**：先确认当前写入目标，再把新条目写到该 Phase 文件的“变更记录”头部；不要把正文写进本索引。
- **修正旧结论**：到旧结论所在文件原位添加 `⚠️ 注`。

## 当前写入目标

- **Phase 4B**：[`change-history/phase4b.md`](change-history/phase4b.md)

所有新的模块档案、真实 LLM Eval、A/B 实验、smoke、默认行为取舍和有技术含义的小修，当前都写入该文件；Phase 4 及更早阶段的历史记录仍按下方阶段索引进入对应文件。

## 阶段索引

| 阶段 | 范围 | 文件 |
| --- | --- | --- |
| Phase 4B | M41 至当前 | [`change-history/phase4b.md`](change-history/phase4b.md) |
| Phase 4 | M29–M40 | [`change-history/phase4.md`](change-history/phase4.md) |
| Phase 3B | M15–M28 | [`change-history/phase3b.md`](change-history/phase3b.md) |
| Phase 3A | M8–M14-lite，以及 Phase 3B 开始前的过渡记录 | [`change-history/phase3a.md`](change-history/phase3a.md) |
| Phase 2 | M0–Phase 2.7.1 | [`change-history/phase2.md`](change-history/phase2.md) |

## 记录规则

- `[模块任务]`：功能、架构、默认行为、安全或评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM Eval、smoke 或影响路线判断的实验。
- `[小修]`：有技术含义的轻量修改，可用短条目；纯措辞润色不记录。
- 连续且同主题的小修合并为一个条目；完整模块条目包含改动范围、关键记录、参考资料、验证快照和遗留/后续。
