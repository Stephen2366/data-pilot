---
name: datapilot-module-finish
description: Use when finishing any DataPilot module, before claiming module completion, before running accept-module, or when the user says 收工、模块完成、补注释、写日志、finish module、归档模块. This skill finishes a module by checking comments, running verification, updating AI_CONTEXT technical records, and writing dev-log learning notes.
---

# DataPilot Module Finish

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
datapilot-module-finish
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

注释遵循以下规则：

- 注释覆盖完整（复杂或者非直观的地方都要加注释），但是内容要求简洁不啰嗦
- 注释内容通俗易懂，适合新手自学和面试复盘适当使用类比辅助理解
- 适当使用 ★ 标记关键处
- 对于较长或者复杂的代码，需要添加分隔，大步骤用 `# 描述 =====`，小步骤用 `# 描述 -----`（描述必要时可添加序号`步骤 N：`和`步骤 N-M：`，每行总长度 100 个半角字符左右，使各行视觉对齐）

推荐注释风格：

```python
# 步骤 1：先创建父表数据 =====================================================
# ★ 订单依赖用户、商品、渠道的主键，所以必须先 flush 父表对象。
```

## 阶段 2：运行验证

根据模块类型选择验证命令。

记录要求：

- 记录命令是否成功
- 记录关键输出结论
- 有 warning 要说明是否影响本模块
- 命令失败时，不要掩盖；写明失败原因和是否阻塞

## 阶段 3：更新 AI_CONTEXT.md

模块完成时，在 `docs/AI_CONTEXT.md`「模块技术档案」头部新增一节。

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
- 阻塞项：
- 更新时间：
```

如果只是小修复，不写模块技术档案，只在「补充记录」新增 1-3 行：

```md
- YYYY-MM-DD 简短标题：改了什么；为什么；验证了什么
```

## 阶段 4：更新 dev-log.md

只有模块完成时更新 `docs/dev-log.md`，小修复则不更新。本文档给用户读，不给 AI 堆上下文，少用术语堆叠。不写没实现的能力，没记录到的过程细节就写“过程细节未记录”

模板：

```md
## ★ Mx 模块名（YYYY-MM-DD）

**简述**：一句话说明这次模块完成了什么，最好带类比。

### 这次做了什么

用故事体写：为什么要做 → 怎么做 → 得到了什么结果。
点名关键文件，但不要变成完整文件清单。

### 新概念

- **概念 1**：本模块第一次出现的概念要用新手能听懂的话解释。必要时用 Java / SpringBoot / MySQL / Redis / FastAPI / LangGraph 类比。

### 设计要点

- 关键决策 1：为什么这样选
- 关键决策 2：为什么没用临时方案
- 风险或边界：哪里后续要继续补

### 面试怎么讲

条理清晰。

### 验证与下一步

- 验证：写真实跑过的命令结论
- 下一步：下一模块入口

可复制验证命令：

```powershell
...
```
