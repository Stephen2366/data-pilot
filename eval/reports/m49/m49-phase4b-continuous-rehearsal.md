# M49 Phase 4B evidence-backed continuous rehearsal

- Scenario v7: `9b133cdf0bd1c071a0f10f79d03e86a0cdc00a4a75258a5d0e878a78e8ced080`
- Phase 4B assurance v2: `bc4958405eb777b9be3a0ee1e392a9592181792d3563e0b1be33db53312e36bf`
- Technical status: `B0–B6 available / evidence gated`
- Rollout: `Pipeline default / Subgraph server-controlled experimental / no auto-fallback`
- Claims: `fixed demo chain verified / no quality-win or production claim / reserve sealed`

## Continuous demo evidence

1. T1 单月 SQL，T2 完整显式重述替换为双月比较。
2. T3 根据两期 guarded rows 确定性判断质量问题增长，再解锁商品拆分。
3. T4/T5 串起 SQL、business RAG Subgraph、Document Evidence、Citation 与 correction。
4. 新进程从 MySQL 恢复 task，提交覆盖 T1～T5 的 Compact v2；T6 从 latest result digest 零 Graph/Tool/provider 解释最近结果。
5. production-like 无 resolver 路径在 deep runtime/provider 前统一失败关闭，且没有创建 task。

M49-P2 r8 使用真实 Qwen、Text2SQL、SQL Guard、隔离 MySQL 与 active business release：`12 provider calls / 51,013 observed tokens / retry 0`，synthetic checkpoint/event 最终 `0/0`。safe source SHA-256 为 `881e8111...bad4`。

## Evidence gate

- budget trigger、Compact fallback、version fencing、owner isolation 和 private payload rejection 来自实际 JUnit `6 passed`，SHA-256=`9f2f9e55...65e0`。
- durable role/version negative paths 引用 M48-P2 真实 adapter artifact，SHA-256=`67ac498e...27a7`。
- v7 的 passed case 必须携带 execution locator/identity；缺失 observation 自动变为 `not_observed`，整体只能 `inconclusive`。
- assurance v2 分开保存 contract identity 与 execution evidence identity，禁止合同自证执行。

## Demo boundary

这份报告证明固定场景下的架构、状态流、安全边界、重启与证据投影可以连续运行。它不证明开放问法泛化率、RAG/LLM 质量优于基线、生产认证、性能/HA、外部 Tool exactly-once 或 sealed reserve 结果。

大白话：这条准备给面试展示的完整链已经真实跑通，而且每张“通过票”都能找到执行证据；但不能据此说所有问题都答得准，也不能说已经能直接上线。
