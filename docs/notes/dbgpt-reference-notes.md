# DB-GPT reference report notes

- [x] 读取 DataPilot 当前状态：Phase 3A M8.5 已验收，下一步 M9 Schema Retrieval 与 JoinPath。
- [x] 读取远期路线图：DataPilot 主线是 NL2SQL、RAG、评测闭环；Skill/MCP/复杂 Agent 后置。
- [x] 核对现有报告：`docs/reference-dbgpt-analysis.md` 缺失，`docs/AI_CONTEXT.md` 已有一条新增报告记录。
- [x] 梳理 DB-GPT 顶层包：core / app / serve / ext / client / sandbox / accelerator。
- [x] 抽样阅读关键实现：AWEL DAG、Text2SQL chat_db auto_execute、DB schema retriever、Agent Action/Skill、sandbox、evaluate。
- [x] 对照 DataPilot 当前代码：AgentResponse、/api/query、SQL Tool、SQL Guard、Trace、Phase 3A diagnostic baseline。
- [x] 写报告后回读检查章节完整性和结论是否足够明确。

关键结论素材：
- DB-GPT 是完整 AI + Data 平台，适合学习平台分层、AWEL 编排、Skill 包、沙箱、评测服务。
- DataPilot 是求职倒推的教学型业务 Agent，强在范围收敛、可解释演进、SQL Guard 硬边界和 EvalOps-lite。
- 不建议直接放弃 DataPilot 基于 DB-GPT 重开；建议把 DB-GPT 当中后期参考，按 M9/M10/M11/M12 分步吸收。
