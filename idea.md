# LeetCode Agent — Ideas & Bug Notes

## 已修复

### 1. 文件夹分类用数据结构标签而非算法标签
- **问题**: `_create_solution_file` 取 `tags[0]` 作为文件夹名，LeetCode 返回的第一个标签通常是数据结构类（Array、Hash Table），导致分类不准。例如第 200 题 Number of Islands 归到 `array` 而不是 `depth_first_search`，第 70 题 Climbing Stairs 归到 `math` 而不是 `dynamic_programming`。
- **修复**: 新增 `_pick_category()`，定义了数据结构标签集合（array, string, hash table, linked list 等），优先选算法类标签，全是数据结构标签时才 fallback 到第一个。

### 2. 文件夹名连字符不统一
- **问题**: `_slugify` 保留了连字符，导致 `Depth-First Search` 变成 `depth-first_search`，风格不一致。
- **修复**: 修改 `_slugify` 的正则，将 `[\s]+` 改为 `[\s-]+`，连字符和空格统一替换为下划线。

### 3. Agent 对明确指令做多余的 double check
- **问题**: 用户说"放弃吧"，DeepSeek 会反复确认"你确定要放弃吗？"，体验很差。
- **修复**: 在 system prompt 中明确加入"用户意图明确时直接执行，不要反复确认"的指令。

### 4. 放弃/查看计划后还要多轮对话才能开始下一题
- **问题**: 放弃题目后 AI 会问"你想做新题还是查看其他内容？"，用户还要再输入一轮才能开始。查看每日计划也是，AI 展示完列表后还要用户手动输入题号。整个流程太慢。
- **修复**:
  - 放弃后直接弹出箭头选择器，列出推荐题目，↑↓ 选择 Enter 确认，一步到位开始下一题。
  - 查看每日计划同理，Rich 表格展示完后直接弹出选择器，不再经过 AI 对话。
  - 用 prompt_toolkit 的 Application 实现了 `_arrow_select()` 组件，支持 ↑↓/j/k 选择、Enter 确认、Esc 跳过。

### 5. Agent 回复文本没有视觉区分，与工具输出混在一起
- **问题**: DeepSeek 的回复文本直接顶格显示，和工具调用行（`⚙ tool_name`）风格不统一，不好区分哪些是 AI 说的话。而且流式渲染时 `console.print("⏺")` 和 `Live` 分开渲染，导致先蹦出几个字然后内容跳到下一行。
- **修复**: 用 Rich 的 `Table`（无边框）将 `⏺` 和 Markdown 内容作为一个整体渲染，⏺ 占左侧 2 字符宽的列，内容在右侧列自动对齐。整个作为一个 Live renderable，不会出现跳行问题。

### 6. 箭头选择器无法交互 & 残留文本
- **问题**: `_arrow_select` 使用 prompt_toolkit 的 `Application(full_screen=False)`，和外层 PromptSession 冲突，导致完全无法选择。后来改为 raw terminal input (`tty.setraw` + `termios`) 后可以选择了，但 raw mode 下 `\n` 只换行不回车，导致每行文本向右偏移，选择时残留文本堆叠。
- **修复**: 渲染输出改用 `\r\n`（回车+换行），清屏时先 `\r` 回到行首再上移清除。

---

## 待观察 / 未来可能的改进

### 每日计划加载慢
- **现象**: `get_daily_plan` 调用 `fetch_all_hot`，之前最多请求 CodeTop API 5 页，每页一个 HTTP 请求，网慢时体验很差。已改为 1 页（20 题足够挑 3 道新题），但网络本身慢的话还是会有等待。
- **可能方向**: 加本地缓存（比如 CodeTop 结果缓存 24 小时）、加 loading spinner 提示。

### 每日新题数量
- 已从 5 道改为 3 道（`MAX_NEW_PROBLEMS_PER_DAY`），减少信息量，更聚焦。如果用户觉得太少可以再调。

### 标签分类的准确性
- 当前算法标签优先的逻辑依赖于一个手动维护的数据结构标签集合 `_DATA_STRUCTURE_TAGS`。如果 LeetCode 新增标签，可能需要更新。目前覆盖了常见的：array, string, hash table, linked list, stack, queue, tree, binary tree, binary search tree, graph, matrix, doubly-linked list, heap (priority queue)。

### Agent 多次调用工具的问题
- 从用户反馈看，有时 AI 会先调 `get_daily_plan` 再调 `get_status`，做了不必要的额外请求。可以考虑在 system prompt 中进一步约束：查看计划时不需要额外获取统计数据。

---

## 架构演进记录

### 第一版：硬编码指令匹配
- `parse_and_run()` 里用 `if text in (...)` 逐个匹配关键词，映射到固定的 handler 函数。
- 问题：用户只能输入精确的关键词（"提示"、"/hint"），稍有变化就报错"不认识这个指令"。

### 第二版：AI 路由器
- 在硬匹配失败后，把用户输入 + 所有指令列表发给 DeepSeek，让它返回 JSON 判断匹配哪个指令。
- 问题：AI 被当成一个"分类器"用，只输出 `{"match": true, "command": "hint"}`，对话能力完全浪费。本质上还是指令驱动的架构，AI 只是一个更智能的 `if-else`。

### 第三版（当前）：Agent + Function Calling
- 彻底反转架构：AI 是核心对话者，用户的所有输入直接进入 Agent 对话循环。
- AI 通过 DeepSeek 的 function calling 机制自主决定何时调用工具（read_solution、start_problem、submit_result 等）。
- 提示、讲解不再是独立的"指令"，而是 AI 自然对话的一部分 — AI 先调 `read_solution` 读代码，然后根据代码状态自由回复。
- CLI 只保留 `/config`（交互式设置）、`/help`、`/quit` 三个直接命令，其余全部交给 Agent。

**关键设计决策：**
- 工具尽量少、粒度尽量粗。只有 9 个工具（read/write 文件、start/submit/abandon 题目、4 个查询）。没有单独的 "hint" 或 "teach" 工具 — 这些只是 AI 读完代码后自然产生的不同回复风格。
- System prompt 每轮动态重建，包含当前题目信息（标题、描述、标签、文件路径），这样 AI 始终知道上下文。
- 对话历史保留最近 30-40 条消息，避免 token 爆炸。
- 工具执行结果返回 JSON 字符串，AI 自己决定怎么向用户展示。

---

## 已修复的 Bug（架构重构时发现）

### 6. `clear_session()` 会清除公司/难度设置
- **问题**: `state.clear_current()` 调用 `db.clear_session()`，后者执行 `DELETE FROM session`，会把 `cfg_company`、`cfg_difficulty` 等配置也一起删掉。用户每次提交/放弃题目后，之前设置的目标公司和难度偏好都丢了。
- **修复**: 新增 `db.delete_session(key)` 方法，`clear_current()` 改为只删除 `current_problem_id`、`current_attempt_id`、`current_file_path` 三个键，不影响 `cfg_*` 配置。

### 7. 题目缺少代码模板
- **问题**: 从 LeetCode API 获取题目时没有拉取 `codeSnippets` 字段，创建的解题文件只有一个空的 `class Solution: pass`，用户还得自己去 LeetCode 网站复制函数签名。
- **修复**:
  - GraphQL 查询新增 `codeSnippets { lang langSlug code }` 字段
  - 提取 Python3 的代码模板存入 `Problem.code_snippet`
  - DB schema 新增 `code_snippet` 列（含自动迁移）
  - 解题文件自动包含 LeetCode 官方的函数签名

---

## 待考虑

### 对话上下文管理
- 当前简单截断（保留最近 30-40 条消息），可能丢失重要的早期上下文。未来可以考虑摘要机制：当历史超长时让 AI 先总结之前的对话，再继续。

### DeepSeek function calling 的稳定性
- DeepSeek 的 tool_calls 支持是 OpenAI 兼容的，但实际表现可能不如 GPT-4。需要观察：
  - 是否会幻觉不存在的工具名
  - 参数格式是否稳定（JSON parse 失败的情况）
  - 多工具并行调用是否正常
- 当前已加 `try/except` 和 `max_iterations=8` 防护。

### 用户代码的隐私
- `read_solution` 会把用户写的代码完整发给 DeepSeek API。对于个人刷题无所谓，但如果未来要支持企业场景需要考虑。

### 离线模式
- 当前所有 AI 功能依赖网络。如果 API 挂了，整个 CLI 除了 `/config`、`/help`、`/quit` 什么都做不了。可以考虑加一个 fallback：API 不可用时退回到第一版的指令匹配模式。
