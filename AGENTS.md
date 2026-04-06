# AGENTS.md

## 目的

这个仓库中的 `src/` 是一个正在持续升级的刷题 agent。升级目标是参考 Claude Code 的设计与实现，对当前项目逐轮改造。

从本文件创建之后，每次用户完成一轮修改并重新唤醒 agent，agent 的职责不是重复设计方案，而是基于本轮实际改动补充一条**迭代记录**。

## 参考仓库

- 当前仓库：`/Users/austin/leetcode_agent`
- Claude Code 源码：`/Users/austin/Downloads/claude-code-main`

## 每轮工作的固定输入

每次新 session，默认使用下面两类输入：

1. 当前仓库本轮的 `git diff`
2. 用户补充说明“这一轮大概参考了 Claude Code 的哪一部分”

如果用户没有额外说明，仍然先从 `git diff` 里归纳改动；但凡涉及“参考自 Claude Code”的结论，都应尽量去 Claude Code 仓库中定位到具体文件和行号。

## 每轮记录目标

每一轮记录都必须回答下面三个问题：

1. 原本的做法是什么
2. 改造后变成什么样
3. 参考了 Claude Code 的哪个实现，具体到文件和行号

如果某一处改动没有直接对应的 Claude Code 实现，也要明确写出“未找到直接对应实现，属于本仓库自定义改造”，不要伪造映射关系。

## 执行流程

每次被唤醒后，按下面顺序执行：

1. 查看当前改动范围
   - `git status --short`
   - `git diff --stat`
   - 必要时看 `git diff`
2. 结合用户描述，拆出本轮的几个核心改造点
3. 去 Claude Code 仓库定位对应实现
   - 优先用 `rg` 搜文件、类名、函数名、关键字
   - 再用 `sed -n` 或类似方式确认上下文
   - 最终记录要落到“文件路径 + 行号”
4. 把本轮结果追加到本文件的“迭代记录”部分

## 记录约束

- 只依据当前实际 diff 记录，不凭印象补写不存在的改动。
- 如果工作区里混有多轮未提交改动，无法仅靠当前 diff 切分本轮边界，需要先让用户说明基线 commit，或者承认“本轮记录基于当前累计 diff”。
- “原本的做法”优先写改造前本仓库中的真实实现，不要把推测写成事实。
- “新的改造后”优先描述行为、结构和职责变化，不只是复述代码字面差异。
- Claude Code 参考位置尽量精确到行号；如果只能定位到一个函数或代码块，需明确说明是“近似对应”。
- 如果用户口头说参考了某模块，但当前 diff 看不出对应关系，应在记录里写明“用户说明参考了 X，但本轮 diff 中未观察到明确一一对应关系”。

## 记录模板

每次追加记录时使用下面格式：

```md
### Iteration 00N | YYYY-MM-DD

**本轮范围**
- Diff 基线：`<写明是 working tree / 某个 commit 区间 / staged diff>`
- 用户说明：`<用户提到参考了 Claude Code 的什么部分>`
- 涉及文件：`<当前仓库文件列表>`

**改造点 1：<一句话标题>**
- 原本：<改造前的做法>
- 现在：<改造后的做法>
- Claude Code 参考：`/Users/austin/Downloads/claude-code-main/<path>:<line>`
- 说明：<为什么认为这里是对应参考，或注明“近似对应 / 自定义改造”>

**改造点 2：<一句话标题>**
- 原本：...
- 现在：...
- Claude Code 参考：...
- 说明：...

**备注**
- <测试、未完成项、推断项、边界说明>
```

## 迭代记录

### Iteration 001 | 2026-04-04

**本轮范围**
- Diff 基线：`初始化本记录文件`
- 用户说明：`建立后续迭代记录规范，之后每轮根据 git diff + Claude Code 对照补充记录`
- 涉及文件：`AGENTS.md`

**改造点 1：建立统一的迭代记录协议**
- 原本：仓库中没有固定的升级记录协议，后续每轮如何总结“旧实现 / 新实现 / Claude Code 对照位置”没有统一格式。
- 现在：新增 `AGENTS.md`，固定每轮记录的输入、执行流程、约束和模板，后续直接在本文件下持续追加迭代记录。
- Claude Code 参考：`无`
- 说明：这是为当前项目定制的协作约定，不是对 Claude Code 某段源码的直接移植。

**备注**
- 从下一轮开始，默认需要先看当前 `git diff`，再结合用户给出的 Claude Code 参考方向，补写新的 iteration 记录。
- 如果某一轮不是基于干净边界开始，应先在记录中注明 diff 基线的限制。

### Iteration 002 | 2026-04-05

**本轮范围**
- Diff 基线：`working tree（基于当前累计 diff 记录）`
- 用户说明：`本轮新增记忆功能；本次对话未额外说明具体参考 Claude Code 的哪一部分`
- 涉及文件：`README.md`、`TASK.md`、`src/lc/agent.py`、`src/lc/cli.py`、`src/lc/config.py`、`src/lc/leetcode_api.py`、`src/lc/tools.py`

**改造点 1：把工作区指令和用户偏好记忆注入到 system prompt**
- 原本：agent 使用固定 `SYSTEM_PROMPT`，不会在每轮对话前额外读取工作区里的用户指令文件，也没有加载跨会话的用户偏好记忆。
- 现在：`Agent.chat()` 改为动态构建 system prompt，在基础提示词后追加工作区根目录下的 `LeetCode.md`（L1）和 `~/.leetcode_agent/user_memory.md`（L2），让后续每轮推理都能带上用户自定义指令和长期偏好。
- Claude Code 参考：`/Users/austin/Downloads/claude-code-main/src/screens/REPL.tsx:3797-3811`
- 说明：对应点在于 Claude Code 启动时会加载 `CLAUDE.md` / rules 文件并注入上下文；本仓库把这一思路简化成对 `LeetCode.md` 和用户偏好记忆文件的拼接加载，属于近似对应。

**改造点 2：把“记什么、什么时候记”显式写进记忆系统规则**
- 原本：仓库只有每题一个 markdown 记忆文件，agent 通过 `read_memory` / `write_memory` 直接读写，但没有把“用户偏好记忆”和“题目过程记忆”的边界、触发时机写成明确规则。
- 现在：system prompt 与工具定义中引入 L1/L2/L3 三层记忆，并新增 `update_user_memory`、`find_similar_problems`、`analyze_and_memorize` 三个工具，把“用户表达偏好时更新长期记忆”“做题中/做题后自动整理题目总结”等触发条件前移到 agent 的显式执行规则里。
- Claude Code 参考：`/Users/austin/Downloads/claude-code-main/src/memdir/memoryTypes.ts:120-154`
- 说明：Claude Code 在 memory types 中明确区分 user / feedback / project 等记忆类型及其保存时机；本仓库借鉴的是这种“先定义记忆类型与触发规则，再让 agent 按规则写记忆”的设计方式，但三层结构和具体题目工具是按刷题场景自定义的。

**改造点 3：用子 agent 生成用户偏好和题目总结，并按已做题目做相似题召回**
- 原本：记忆写入主要依赖主 agent 直接调用 `write_memory` 追加文本；没有自动从上下文提炼用户偏好，也没有“开题后找相似已做题”或“根据对话与代码自动生成题目总结”的流程。
- 现在：`tools.py` 新增 `_sub_agent_call()` 复用主对话前缀，分别驱动 `update_user_memory` 和 `analyze_and_memorize` 自动改写记忆文件；同时新增 `find_similar_problems`，从已做题记录中召回相似题，供新题开场时联想历史经验。
- Claude Code 参考：`未找到直接对应实现，属于本仓库自定义改造`
- 说明：Claude Code 确实有“选择相关记忆再注入”的流程，但没有看到与“LeetCode 题目级相似题召回 + 每题总结文件回写”一一对应的实现，因此这里不强行建立源码映射。

**备注**
- 本轮 review 发现了并发执行相关风险：当前 agent 会把非交互工具并行执行，而 `start_problem` 与 `find_similar_problems`、`update_user_memory` 与其他写记忆工具之间存在先后依赖，后续需要单独修正。
- 本轮 review 还发现题目记忆路径仍存相对路径到全局 DB，跨工作区时 `find_similar_problems` 可能读不到旧记忆文件；这是记忆功能接入后暴露出的边界问题。
- `TASK.md` 中删除了旧的 `fetch_similar_problems` 规划项，说明本轮相似题能力最终没有采用 LeetCode 原生 similarQuestions 接口，而是转为基于本地已做题记忆的自定义实现。
