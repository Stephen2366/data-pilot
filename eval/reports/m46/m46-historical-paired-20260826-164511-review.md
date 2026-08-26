# M46 historical v3 paired closed-set review

- Run：`m46-historical-paired-20260826-164511`
- Candidate：`ab66f20dc40eb8a1f1deba3fd16aad466a5a836e7543aacdb65326d182532f78`
- Review 结论：`no_go_revise_stop`
- Reserve：`sealed`，未读取逐题内容

## 来源与完整性

| 来源 | Artifact identity | 文件 SHA-256 |
|---|---|---|
| Pipeline 60 | `cd70c2a8bd12b4d09f80faca3ec90f33e186b20339d5e4d22edf9c3aa0ea8963` | `95b4de662bf88bf24f8302eac045d4d099e81d18798afa89058b8fdffe06084d` |
| Subgraph 60 | `578db71837669bcf4dd30fada21d28030d5ff7a319fba3f3c7ef24714e83ab42` | `e2ac9abcb0fd99e49d9186354ceb817d5a15622890573e861a7215bc9e446b4d` |
| Paired compare | `a9175c91373b43c0c8d13175fedf52bd659649b7ac0c92408c95d0c20f35e5a6` | `a1e6eac9dcefa8a6438c0390b1ce227754ef2f9d8da61c52eec16cb6e297a7fb` |
| Paired wrapper | `f6a5e1a291fd5e1a7d9353f9bfe1e0b536b221f7349691386183bb12c9886f4d` | `30b4c6013c4125f4998a3c168c3610247e822835a4c77766429e321e15db6330` |

两臂均为 60/60 completed，exit=0；Subgraph 的 60 条 child projection 全部 observed、response/Trace source-consistent，request count 完整。token 只包含 Composer + formation，不包含 embedding token，因此总 token 不完整。

## 闭集结果

- 自动 paired verdict：`57 insufficient / 3 tie / 0 win`。
- Gate：Pipeline `598 passed / 112 failed / 10 not_observed`；Subgraph `393 / 139 / 188`。
- 分层 passed：basic `269→141`、core `289→162`、hard `150→90`，三个层级均明显退化。
- Subgraph 最终答案闭集：`60/60 no_answer`；其中 `34 retrieval_unavailable / 23 composer_unavailable / 3 composer_output_invalid`。没有自然语言答案可供 correctness 复核，因此 60 条语义 verdict 均只能是 `insufficient_evidence`，不能把 tie 或 Gate 局部通过解释为答案正确。

## 修复收益与剩余失败

- v3 的 deterministic value-shape normalization 生效：v2 的 value-shape 失败 `19→0`。
- Eval 证据闭合：child projection `57/60→60/60`，request count 由不完整变为完整。
- `answer_ready` 从 `12→26`，26 次 context expansion 共新增 43 条 Evidence。
- 但 26 个 answer-ready 最终仍全部失败：22 个 Composer invalid cardinality、1 个 invalid citation binding、3 个 typed `composer_output_invalid`。
- 其余 34 个 child contract failure 为：19 个 `Evidence run mismatch`、7 个 question anchor 非 source span、6 个没有形成 unsupported requirement、2 个 requested aspect 非 source span。
- 已知 provider requests：Pipeline `120`；Subgraph `139`。已知 chat tokens：Pipeline `133581`；Subgraph `110622`。两臂 embedding token均不可得，不比较完整总成本。

## 决策

v3 确实修复了预期的 value-shape 与可观测性问题，但没有形成任何最终答案，且在 basic/core/hard 三层都显著落后 Pipeline。按照本次运行前约定，本候选不冻结、不进入 sealed reserve，不继续围绕相同 formation/Evidence/Composer 失败簇追加 historical 调参。Pipeline 保持默认，Subgraph 保持 experimental；下一步应由用户确认修订 M46 完成门并执行作品集轻量收口。

本结论只适用于当前 candidate/runtime/60 题 historical dev，不外推生产正确率、Reliability 或其他 corpus/model。
