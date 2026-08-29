# 网上关于对 Agent 测评 的讨论

> **讨论素材**：网上技术讨论原文（未筛选、未整理，保持原文）。制定计划 / 面试话题参考时可翻阅；用到哪条再当场摘录到对应 notes / plan，观点仅代表原作者、不要照搬。排名不分先后，需完整阅读。

**1. **

```
现在Agent前沿在往持续学习和self improve的角度发展，我觉得核心方向就是在loop里面加入可以被清晰定义和量化的评测方法和标准，最终评测和观测会成为基础设施的一层，但是本质来讲跟业务还是强关联的，个人认为未来会越来越重要。但是可能那种纯dirty work跟标注差不多且离agent核心架构太遥远的就不太适用哈哈哈
```

**2. **

```
大模型评测岗，别去！今天刷到 git 上 jeinlee/chinese-llm-benchmark 项目，里面总结 star 最高的 top10 评测，仅 2 个出自国内。top50 评测，仅 9 个出自国内。这就很说明问题。 所以，我为什么不推荐大模型评测？基本没有成长性，都是在做数据；在整个大模型相关岗位中属于倒数第二，仅优于数据标注；模型组取得好的成果，老板会归功于算法创新的好、训练数据质量高，而不是你 benchmark 评测集做的好； 建议同学们在有选择的情况下，慎入评测岗。中厂大模型算法组和大厂评测组让我选，我一定坚定不移的选择中厂算法。如果没有选择，评测组是唯一加入大模型牌桌的机会，在工作中就需要牢记两点：1、以发论文为导向。2、尽量将做的 benchmark 公开（如 github），为自己积累声量。归根结底，虽然好的 benchmark 评测集是大模型成功的一半，但是也确实在国内不受重视，没有资源倾斜也没用功劳分成。跳槽时竞争力远小于做 RL，继续预训练，预训练的算法组同学。
```

**3. 某人的简历**

```markdown
AegisEvo | Agent Harness Evolution Platform

项目链接：https://github.com/ETOLucy/AegisEvo

- Rust 高性能决策内核： 7-Crate 模块化架构(Domain / Protocol / Control / Storage / API / Worker / CLI)，基于 Rust + Axum 实现强类型、低延迟的受控演化引擎； JSON Schema (aegisevo-protocol)与Python 评估器(Pydantic 严格模型)双向跨语言契约统一,保证演化决策的确定性与可审计性；内置有界遥测白名单，杜绝敏感信息外泄。
- 受限基因组与 Quality-Diversity 归档： Content-addressed 候选基因组+Allowlist 受限变异/交叉算子，不可变 Lineage DAG 保证血缘可追溯；4病理位点Niche归档+安全 Veto 解耦，精确区分“因安全拒”与“因证据不足拒”，防止演化产出越界配置。
- 统计&安全双门控机制： Pairwise 统计比较(10,000 次 Bootstrap 重采样，95%CI，n<30输出小样本警告)，PairwiseDecision 将统计显著性与安全门禁拆分为正交布尔量；EvidenceChainV1 哈希证据链绑定 search 证据、报告、门禁与晋升记录，驱动 Evaluated → Challenger → Canary → Active → RolledBack 生命周期，确保晋升有统计证据支撑。
- 高并发与分布式持久化： PostgreSQL 租户隔离(全仓 141 处 tenant_id 约束)、等命令、Fenced Local Workers ( FOR UPDATE SKIP LOCKED 原子抢任务+fencing token 递增防脑裂+租约到期自动回收）与事务性 Outbox，实现可重启恢复的 Durable 控制平面，断电重启不丢任务、不重复执行。
- 跨语言联动与评测对齐： Content-addressed Target Pack (repoaegis-target-pack/v2)与RepoAegis 运行时联动，跨语言 Digest校验+联合治理流水线：392-task SWE-bench Verified 生成战役（166/392=42.3%生成率，官方判定待进行，按OpenAI 弃用 Verified指引定位为方向性工程证据、正迁移SWE-bench Pro);生成≠解决，仅官方 verifier 报告可建立 resolved.
```

**4.**

```
项目直接封装成 tool 和 skill，适配到 hermes 或者 claude code 这种，比你自己整个 react 框架有说服力
```

