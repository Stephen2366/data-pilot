# M46 historical v3 paired closed-set review

- Run：`m46-historical-paired-20260826-164511`
- Candidate：`ab66f20dc40eb8a1f1deba3fd16aad466a5a836e7543aacdb65326d182532f78`
- Rollout 结论：candidate 保持 `experimental`，不晋级 sealed reserve
- Reserve：`sealed`，未读取逐题内容

## 来源与完整性

| 来源 | Artifact identity | 文件 SHA-256 |
|---|---|---|
| Pipeline 60 | `cd70c2a8bd12b4d09f80faca3ec90f33e186b20339d5e4d22edf9c3aa0ea8963` | `95b4de662bf88bf24f8302eac045d4d099e81d18798afa89058b8fdffe06084d` |
| Subgraph 60 | `578db71837669bcf4dd30fada21d28030d5ff7a319fba3f3c7ef24714e83ab42` | `e2ac9abcb0fd99e49d9186354ceb817d5a15622890573e861a7215bc9e446b4d` |
| Paired compare | `a9175c91373b43c0c8d13175fedf52bd659649b7ac0c92408c95d0c20f35e5a6` | `a1e6eac9dcefa8a6438c0390b1ce227754ef2f9d8da61c52eec16cb6e297a7fb` |
| Paired wrapper | `f6a5e1a291fd5e1a7d9353f9bfe1e0b536b221f7349691386183bb12c9886f4d` | `30b4c6013c4125f4998a3c168c3610247e822835a4c77766429e321e15db6330` |

两臂均为 60/60 completed，exit=0；Subgraph 的 60 条 child projection 全部 observed、response/Trace source-consistent，request count 完整。token 只包含 Composer + formation，不包含 embedding token，因此总 token 不完整。

## 闭集结果与rollout判断

- 两臂均完成60题，paired manifest、Gate和逐题结果均已闭合；原始数字保存在同run的`compare.json`、`paired.json`及两臂artifact中。
- Subgraph child projection达到`60/60 observed/source-consistent`，证明Response、Trace与Eval同源账本可以稳定对账。
- 当前candidate没有达到预注册晋级标准，因此不进入sealed reserve；该结论只控制rollout，不否定已完成的Subgraph工程能力。

## 本轮工程收益与下一轮优化边界

- v3 的 deterministic value-shape normalization 生效：v2 的 value-shape 失败 `19→0`。
- Eval 证据闭合：child projection `57/60→60/60`，request count 由不完整变为完整。
- `answer_ready` 从 `12→26`，26 次 context expansion 共新增 43 条 Evidence。
- closed-set诊断将下一轮工作收敛到三个接口边界：Evidence run identity、requirement formation grounding和Composer structured output；详细计数保留在同run的triage与artifact中。
- 已知 provider requests：Pipeline `120`；Subgraph `139`。已知 chat tokens：Pipeline `133581`；Subgraph `110622`。两臂 embedding token均不可得，不比较完整总成本。

## 决策

v3 完成了预期的value-shape与可观测性修复，并证明bounded Subgraph可以在真实产品链上产生、合并和投影Evidence。按照预注册rollout门，当前candidate保持experimental，不进入sealed reserve，也不围绕同一诊断簇继续追加调参。Pipeline保持默认；后续从上述三个接口边界形成新candidate，再按相同流程评审。

本结论只适用于当前 candidate/runtime/60 题 historical dev，不外推生产正确率、Reliability 或其他 corpus/model。
