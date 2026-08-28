# DataPilot 求职版发布收尾清单

> 状态：A 已于 2026-08-28 完成；B 待用户授权。本文只冻结两个收尾任务，不扩大产品能力，也不包含“陌生机器式”安装检查。

## A. 整理仓库发布状态

- [x] 审查 `git status`，逐项区分应提交的源码/文档、运行产物和无关个人文件；删除前必须确认精确目标。
- [x] 检查 `.gitignore`、`.env.example`、API Key、数据库连接串、本机绝对路径和个人信息，确保公开仓库不泄密。
- [x] 检查截图是否放入 `docs/assets/`。
- [x] 复核 README 内部链接、演示命令、项目结构、公开边界与证据数字；不重新执行全套安装验证。
- [x] 用户人工演示通过后提交最终变更，并创建 `v1.0.0-portfolio` tag；是否添加 License 由用户在公开前决定。

执行摘要：严格密钥格式扫描未发现真实 API Key、私钥或 Git token；`.env.example` 只含空值/占位符。5 张演示截图已改为稳定文件名并接入 README，所有本地链接存在。删除了误提交的 AI 调研草稿，并收紧 `.agent_work/` 忽略规则；该文件仍可从 Git 历史恢复。本轮不添加 License、不执行安装检查或全仓测试。

完成标准：工作区范围清楚、公开内容无敏感信息、README 图片和链接有效、最终提交与 tag 可定位。

## B. 有限 Text2SQL 正确率收口

- [ ] 执行前由用户明确授权一次当前 `m27-v3` **Core selector**；不自动扩大到 Reliability、Stress、full、RAG 180、held-out 或大规模数据压测。
- [ ] 使用冻结 catalog、当前默认 runtime 和现有 oracle，只创建一个 run ID；首次结果无论通过、失败或外部不可用都停止，不靠换模型、重跑或改题覆盖。
- [ ] 记录 completed artifact、resolved runtime、实际 provider calls/tokens、Gate，以及 QueryPlan/SQL/执行结果/安全拒绝/provider failure 的分层结果。
- [ ] 对失败题做一次人工分类，明确“模型质量、合同拒绝、数据库执行、外部不可用”的区别；不把固定 Demo 三题冒充总体正确率。
- [ ] 用户根据结果决定是否登记为 Text2SQL 正式长期基线；未确认前只作为 release candidate evidence。

完成标准：得到一条可复核、边界明确的当前版本 Core 快照；无论分数高低，都能诚实说明分母、失败结构和未覆盖范围。

## 明确不做

- 不为制造“规模感”扩充海量业务行；数据量主要验证性能，不等于 Text2SQL 正确率。
- 不重跑完整 RAG 180 或 sealed reserve，不切换 Pipeline/Subgraph 默认，不新增模型、Router、认证、部署或 streaming 能力。
- 不因为 README、截图或发布整理再次机械运行全仓测试；验证范围必须与实际代码改动匹配。

执行时以 [`docs/state/runbook.md`](state/runbook.md)、[`docs/state/eval-baselines.md`](state/eval-baselines.md) 和 [`docs/state/AI_CONTEXT.md`](state/AI_CONTEXT.md) 的当前口径为准。
