---
name: finish-module
description: 项目模块代码完成后的收工整理。Use when the user says 收工、模块完成、补注释、写日志、写复盘、finish module.
---

# Module Finish（模块收工整理）

用于模块代码开发完成后的“收工整理”。它不是最终验收门禁；最终验收由 `accept-module` skill 负责。

## 核心原则

过程细节未记录就不编。

如果从以下来源都找不到某个决策、踩坑或命令信息：

- 当前对话
- `docs/AI_CONTEXT.md`
- `.agent_work/temp/<module>-notes.md`
- git diff
- 终端验证输出

那就在日志里写“过程细节未记录”，不要脑补合理故事。

验证快照必须来自本 skill 实际跑过的命令，或来自当前对话中明确可见的真实命令输出。不能写“预计通过”“应该通过”。

## 与 accept-module 的关系

```text
finish-module
  负责：补注释 + 跑验证 + 写技术档案 + 写学习复盘
        ↓
用户人工看一遍，可要求小修
        ↓
accept-module
  负责：最终门禁检查
```

两个 skill 独立调用，不互相嵌套。收工完成后，提示用户可以继续调用 `accept-module` 做最终验收。

## 阶段 0：确认范围和素材

1. 读取：
   - `AGENTS.md` 或 `CLAUDE.md`
   - `docs/AI_CONTEXT.md`
   - 当前阶段计划文件，例如 `docs/phase2-plan.md`
   - 当前模块小节

2. 确认模块范围：
   - 当前模块名称
   - 当前模块验收标准
   - 不属于本模块的内容不要补做

3. 收集改动范围：
   - 优先使用用户提供的模块起始 commit
   - 如果没有 commit，使用 `git status --short` 和 `git diff --stat`
   - 只处理本模块相关文件，不回滚用户改动

4. 收集过程素材：
   - 读取 `docs/AI_CONTEXT.md`「补充记录」
   - 读取 `.agent_work/temp/<module>-notes.md`，如果存在
   - 查找当前对话中已经跑过的验证命令输出
   - 如果素材缺失，后续日志中明确写“过程细节未记录”

## 阶段 1：注释查漏补缺

目标：让代码适合新手学习和面试复盘，而不是堆满废话注释。

收工时必须逐个检查本模块新增 / 大幅修改的代码文件（以 Python 为主，含测试）：

- 文件级职责是否清楚。
- 每个核心函数 / 类是否解释用途、输入、输出和设计理由。
- 是否解释了本模块第一次出现的新概念。
- 是否有“为什么这样做”的注释，而不只是“这行代码做什么”。
- 测试文件是否说明测试守住的业务 / 工程验收标准。
- 涉及某技术栈的特性和机制的地方，如果对新手不直观，检查是否有补充说明。

注释规则以 AGENTS.md / CLAUDE.md「代码风格」为单一事实源，本阶段不复述规则，只做查漏补缺。

- 除了「代码风格」的基本要求外，分隔注释的对齐线（`==========` / `----------`）如果长度较短或长短不齐，在此阶段统一补齐到每行总宽约 100 列（中文按 2 列计），使同文件内各行大致视觉对齐（目测即可，无需精确计数）。

推荐注释风格：

```python
# 步骤 1：先创建父表数据 ===========================================================================
# ★ 订单依赖用户、商品、渠道的主键，所以必须先 flush 父表对象。
```

## 阶段 2：运行验证

1. 先读当前阶段计划文件中本模块的「验证」或「验收标准」小节，确认是否有模块特定的验证步骤（如 eval 脚本、smoke 测试）。有则优先执行；没有则只跑通用命令。
   
2. 通用验证命令（以 CLAUDE.md 指定的项目 Python 路径为准）：

   Windows / PowerShell 常用：

   ```powershell
   $env:PYTHONDONTWRITEBYTECODE='1'
   # 测试（所有模块）
   <项目 Python> -m pytest -p no:cacheprovider

   # 数据库迁移检查（涉及 ORM / Alembic 时）
   <项目 Python> -m alembic check
   <项目 Python> -m alembic current

   # seed 数据完整性（涉及 seed 时）
   <项目 Python> -m scripts.seed_data --reset
   ```

   macOS / Linux 可用：

   ```bash
   PYTHONDONTWRITEBYTECODE=1 "<项目 Python>" -m pytest -p no:cacheprovider
   PYTHONDONTWRITEBYTECODE=1 "<项目 Python>" -m alembic check
   PYTHONDONTWRITEBYTECODE=1 "<项目 Python>" -m alembic current
   PYTHONDONTWRITEBYTECODE=1 "<项目 Python>" -m scripts.seed_data --reset
   ```

3. 记录要求：

- 记录命令是否成功
- 记录关键输出结论
- 有 warning 要说明是否影响本模块
- 命令失败时，不要掩盖；写明失败原因和是否阻塞

## 阶段 3：更新 AI_CONTEXT.md

模块完成时，在 `docs/AI_CONTEXT.md`「模块技术档案」头部新增一节，方便 AI 续接优先看到最新状态。

模板：

```md
### Mx 模块名（YYYY-MM-DD）

- 改动范围：列核心目录 / 文件，细节看 git
- 关键决策：
  - 决策 1：为什么这样做
  - 决策 2：为什么不用另一个方案
- 参考资料：
  - 查了什么
  - 借鉴了什么
  - 没照搬什么
  - 如果未查阅，写“未查阅外部参考”
- 验证快照：
  - pytest：结果
  - alembic / seed / API / eval：结果
  - warning：是否影响
- 遗留：
  - 下一模块要接什么
  - 当前还有什么风险
```

同时更新顶部「当前状态」：

```md
- 当前阶段计划文件：
- 当前模块：
- 上一模块验收：
- 阻塞项：
- 更新时间：
```

「上一模块验收」在收工时填「Mx 未验收（待 accept-module）」（Mx = 本次收工的模块）；验收通过后由 accept-module 改写，本 skill 不代填「已验收」。

如果只是小修复，不写模块技术档案，只在「补充记录」新增 1-3 行：

```md
- YYYY-MM-DD 简短标题：改了什么；为什么；验证了什么
```

## 阶段 4：更新 dev-log.md

只有模块完成时更新 `docs/dev-log.md`，小修复则不更新。本文档给用户读，不给 AI 堆上下文，少用术语堆叠。不写没实现的能力，没记录到的过程细节就写“过程细节未记录”。新的模块记录追加到文档末尾，便于用户顺序阅读。

模板：

```md
## ★ Mx 模块名（YYYY-MM-DD）

**简述**：一句话说明这次模块完成了什么，最好带类比。

### 这次做了什么

用故事体完整地写：为什么要做 → 怎么做 → 得到了什么结果。

### 新概念

- **概念 1**：本模块第一次出现的概念要用新手能听懂的话详细解释。必要时用 Java / SpringBoot / MySQL / Redis / FastAPI / LangGraph 类比。

### 关键文件

- 列出本次任务中，用户需要重点查看或理解哪些文件，并通俗详细地介绍这些文件。

### 设计要点

- 关键决策 1：为什么这样选
- 关键决策 2：为什么没用临时方案
- 风险或边界：哪里后续要继续补

### 面试怎么讲

条理清晰，必要时可分段写。

### 验证与下一步

- 验证：写真实跑过的命令结论
- 下一步：下一模块入口

可复制验证命令：

```powershell
...
```

## 阶段 5：收尾确认

写完 AI_CONTEXT.md 和 dev-log.md 后，回读各自刚写入的章节，确认格式正确、内容完整、没有截断或乱码。发现异常立即修正。

最后回复用户，列出本次收工做了什么：

- 补了哪些注释
- 跑了哪些验证及其结论
- 更新了哪些文档
- 有哪些 warning / 遗留

> 收工完成后，提示用户可以继续调用 `accept-module` 做最终验收门禁。
