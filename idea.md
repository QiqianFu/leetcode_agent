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

### 7. P0 — 提交流程跳过 AI
- **问题**: 用户说"提交"要经过 AI 问评分再调工具，两次 API 调用。
- **修复**: 新增 `/submit` 斜杠命令，直接弹箭头选择器选 1-5 评分，`submit_current_problem()` 提取为独立函数供 cli.py 和 agent 共用。从 AI 工具列表中移除了 `submit_result`。

### 8. P0 — /review 和 /hot 加箭头选择
- **问题**: 展示列表后没有后续动作，用户还得手动输入题号。
- **修复**: `/review` 和 `/hot` 展示完表格后直接接 `_arrow_select`，选中即开题。

### 9. P1 — 做题状态 prompt
- **问题**: 做题时 prompt 始终是 `> `，不知道当前在做哪题。
- **修复**: 新增 `_get_prompt()`，做题时显示 `146 LRU Cache > `，空闲时显示 `> `。

### 10. P1 — 消息截断保持完整配对
- **问题**: `messages > 40` 时简单截断 `[-30:]`，可能切断 tool_call 和 tool_result 的配对，导致 DeepSeek 收到残缺历史报错。
- **修复**: 截断时从 -30 位置向前扫描，跳过 `tool` 和带 `tool_calls` 的 `assistant` 消息，找到安全的切割点。

### 11. P2 — 放弃后不再弹选题器
- **问题**: 放弃题目后自动弹箭头选择器，体验突兀。
- **修复**: 改为只提示"输入 /today 选择下一道题"，用户自己决定。

### 12. Bug — hint/teach 计数器未调用
- **问题**: agent 给提示/讲解时没有调用 `db.increment_hints()` / `db.increment_teach()`，struggle_score 始终为 0，复习调度不准。
- **修复**: 新增 `count_hint` 和 `count_teach` 两个轻量工具，system prompt 要求 AI 在给提示/讲解前必须调用。这样计数器通过 function calling 自动触发。
- **思考**: 另一种方案是在 `read_solution` 里根据上下文自动判断是 hint 还是 teach，但语义不清晰，不如显式工具调用可靠。

### 13. Bug — LeetCode API 静默失败
- **问题**: `_graphql()` 重试耗尽后 `return {}` 导致下游 `KeyError`，用户看到的是 Python 堆栈而非友好提示。
- **修复**: 改为 `raise ConnectionError("LeetCode API 请求失败，请检查网络连接后重试。")`，会被 agent 的 `try/except` 捕获并显示给用户。

### 14. Bug — 薄弱标签排序说明
- **问题**: display.py 标题写"评分越高越薄弱"，虽然逻辑正确（自评 5=没做出来），但用户容易困惑。
- **修复**: 标题改为"薄弱标签（按难度排序）"，更直观。排序逻辑 `avg_rating DESC` 不变。

### 15. 清理 ai.py 死代码
- **问题**: `get_hint()`, `get_explanation()`, `route_command()`, `stream_response()` 等函数在 agent 重构后不再被任何地方引用。
- **修复**: 直接删除 `src/lc/ai.py`。

### 16. 新增 .env.example
- **问题**: 新用户 clone 后不知道要配什么环境变量。
- **修复**: 创建 `.env.example` 文件，包含 `DEEPSEEK_API_KEY=your_api_key_here`。

### 17. P2 — /info 命令
- **修复**: 新增 `/info` 斜杠命令，做题中途查看当前题目、难度、标签、用时、提示/讲解使用次数、文件路径。用 Rich Panel 渲染。

### 18. P2 — Ctrl+C 做题中确认
- **问题**: 做题状态下 Ctrl+C 直接退出，可能丢失进度。
- **修复**: 如果正在做题，第一次 Ctrl+C 只提示当前题目信息和可用操作（/submit、/help），不退出。再按一次才退出。
- **思考**: 进度本身不会丢（state 存在 DB 里），但突然退出体验不好，提示一下更友好。

### 19. P2 — 空输入微提示
- **修复**: 连续 2 次空输入后显示 `输入 /help 查看帮助`，轻量提示不打扰。

### 20. 实现 /similar 命令
- **问题**: CLAUDE.md 列了但代码未实现。
- **修复**: 新增 `/similar` 斜杠命令，调 `fetch_similar_problems()` 获取当前题的相似题目，用 `show_similar` 展示表格，后接箭头选择器可直接开题。新增 `fetch_problem_by_slug()` 函数支持通过 title_slug 获取完整题目信息。

### 21. 统计面板加趋势
- **问题**: `/status` 只有累计数据，缺乏激励感。
- **修复**: `get_attempt_stats()` 新增 `recent_7d`（最近 7 天做题数）和 `streak`（连续刷题天数）字段，`show_status` 面板中显示。
- **思考**: streak 的计算是从今天向前数连续有做题记录的天数。如果今天还没做题，streak 从昨天开始算。

### 22. 新题 tag 过滤修复
- **问题**: `planner.py` 的 `_pick_from_codetop()` 在题目不在本地 DB 时直接跳过 tag 过滤，注释写 "trust CodeTop ordering"，实际上完全忽略了用户的 tag 偏好。
- **修复**: 题目不在 DB 时先调 `fetch_problem()` 从 LeetCode API 获取并缓存到本地 DB，然后再做 tag 过滤。fetch 失败的题目直接跳过。

### 23. HTML 转文本用 markdownify
- **问题**: `leetcode_api.py` 用十几行正则解析 HTML 题目描述，对嵌套标签、表格等复杂结构处理不好。
- **修复**: 替换为 `markdownify` 库，3 行代码搞定，支持所有 HTML 标签的正确转换。添加到 pyproject.toml 依赖。

### 24. DB schema 版本管理
- **问题**: 用 `PRAGMA table_info` 手动检查列做迁移，新增字段时要加 ad-hoc 代码，容易遗漏。
- **修复**: 新增 `schema_version` 表和 `_MIGRATIONS` 列表，每个版本对应一组 SQL 语句。`init_db()` 自动检测当前版本并运行 pending 迁移。兼容已有数据库（自动检测 pre-versioning 的 DB 版本）。
- **思考**: 当前两个版本：v1 = 初始 schema，v2 = 添加 code_snippet 列。新增字段只需在 `_MIGRATIONS` 追加条目并递增 `SCHEMA_VERSION`。

### 25. 提交评分撤回 /undo
- **问题**: 自评分提交后无法撤回，手滑评错分会影响整个复习计划。
- **修复**: 提交时将 `{problem_id, attempt_id, rating, file_path}` 存入 session 的 `last_submit` key。`/undo` 命令还原 attempt（清除 rating 和 finished_at）、删除关联的 reviews、恢复做题状态，让用户可以重新 `/submit`。
- **限制**: 只能撤回最近一次提交。重新 `/submit` 后 undo 信息被覆盖。

### 27. 输入区域上下分隔线
- **问题**: 用户输入行只有左边一个 `>` 箭头，没有视觉边界，不像 Claude Code / Codex 那样用上下两条线把输入区域框起来。
- **修复**:
  - 上边线：每次进入输入前用 Rich 打印一条全宽 `─` 线。
  - 下边线：修改 prompt_toolkit 的 layout，在 FloatContainer 内部的 HSplit 中，紧跟 input Window 后面插入一个 `height=1` 的分隔线 Window。
  - 补全菜单空间：在分隔线下方加一个 ConditionalContainer，仅在 `complete_while_typing` 或有 `complete_state` 时才撑开 `Dimension(min=N)` 的预留空间，避免平时有空隙。
  - 菜单下移：给 FloatContainer 的每个 Float 内容外包一层 `HSplit([Window(height=1), original])`,让补全菜单整体下移 1 行，不遮挡分隔线。
  - `reserve_space_for_menu=0`：关闭 input Window 自身的膨胀，预留空间由独立的 ConditionalContainer 控制。
- **思考**: prompt_toolkit 的 `bottom_toolbar` 方案不可行——它和 `reserve_space_for_menu` 绑定，要么紧贴但补全菜单消失，要么补全正常但有大段空隙。最终方案是直接操作 layout 树。

### 26. Windows 兼容
- **问题**: `_flush_stdin()` 用 `select.select`，`_arrow_select()` 用 `tty`/`termios`，都是 Unix-only。
- **修复**:
  - `_flush_stdin()`: Windows 下用 `msvcrt.kbhit()` + `msvcrt.getch()` 替代。
  - `_arrow_select()`: Windows 下 fallback 到编号选择（`输入编号 (q 跳过)`），不用 raw terminal。
- **思考**: Windows 上的箭头选择体验不如 Unix，但至少不会崩溃。未来可以考虑用 `prompt_toolkit` 的跨平台方案（如果能解决之前和外层 PromptSession 冲突的问题）。

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

### /continue 恢复未完成题目
- **需求**: 启动时不再自动恢复上次未完成的题目，而是把状态挂起（suspend）。用户需要主动输入 `/continue` 才能恢复。
- **实现**:
  - `state.py` 增加 `suspend_current()` 和 `resume_current()`，通过 session 表的 `suspended_*` 键暂存状态。
  - `show_welcome()` 检测到有未完成题目时，调用 `suspend_current()` 并提示用 `/continue` 恢复，而非自动恢复。
  - `handle_continue()` 调用 `resume_current()` 恢复状态，并显示题目信息和文件路径。
  - `clear_current()` 同时清理 `suspended_*` 键，避免残留。

### 离线模式
- 当前所有 AI 功能依赖网络。如果 API 挂了，整个 CLI 除了 `/config`、`/help`、`/quit` 什么都做不了。可以考虑加一个 fallback：API 不可用时退回到第一版的指令匹配模式。
