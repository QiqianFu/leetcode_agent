# LeetCode Agent

终端刷题助手 — 用自然语言和 AI 对话刷 LeetCode。

AI 帮你选题、给提示、讲解思路、记录做题记忆，你只需要专注写代码。

![Demo](assets/demo.png)

## 功能

- **ReAct Agent** — AI 自主推理决策，多步思考后执行操作，不是简单的指令映射
- **自然语言交互** — 不用记指令，直接说"帮我做第 146 题"、"给个提示"
- **自动创建解题文件** — 按题目分类在当前目录创建 `.py` 文件，包含题目描述和代码模板
- **智能提示** — AI 读取你的代码，给出针对性提示，引导你思考而不是直接给答案
- **记忆系统** — 每道题一个 markdown 记忆文件，记录做题过程、心得、难点
- **高频题推荐** — 接入 CodeTop 数据，按目标公司筛选高频面试题
- **输入历史** — 上下键恢复之前的输入，跨会话保留

## 安装

需要 Python 3.11+。

```bash
git clone https://github.com/你的用户名/leetcode-agent.git
cd leetcode-agent
pip install -e .
```

## 配置

创建 `.env` 文件，填入 DeepSeek API Key（[申请地址](https://platform.deepseek.com/)）：

```bash
echo "DEEPSEEK_API_KEY=你的key" > .env
```

## 使用

```bash
leetcode
```

启动后直接用自然语言对话：

```
> 帮我做第 1 题
  ⚙ start_problem
已开始 1. Two Sum (Easy)
解题文件: array/1_two_sum.py
记忆文件: .memories/1_two_sum.md

> 给个提示
  ⚙ read_solution
你现在用的是暴力双循环，想想有没有办法只遍历一次？
提示：用一个数据结构来记录"你见过的数"。

> 讲解一下
  ⚙ read_solution
这道题最优解是用哈希表...

> 今天还有什么题
  ⚙ get_daily_plan
推荐题目：...
```

### 快捷指令

| 指令 | 说明 |
|------|------|
| `/config` | 设置公司、难度、排序、标签 |
| `/clear` | 清屏 + 清除对话历史 |
| `/help` | 显示帮助 |
| `/quit` | 退出 |

除此之外，所有操作都通过自然语言完成，AI 会自动理解你的意图。

## 记忆系统

LeetCode Agent 有三层记忆，帮你积累刷题经验：

### LeetCode.md — 你的自定义指令

在工作区根目录创建 `LeetCode.md`，写入你的偏好和指令，Agent 每次对话都会读取并遵守。

```bash
touch LeetCode.md
```

示例内容：

```markdown
# 我的刷题偏好

- 我用 Python，偏好迭代写法，不喜欢递归
- 给提示时先给小提示，不要直接给答案
- 每道题做完后帮我总结时间复杂度和空间复杂度
- 我在准备 Google 面试，重点关注 Medium 难度
```

### 用户偏好记忆 — AI 自动维护

Agent 会在对话过程中观察你的编码习惯、薄弱点、偏好等，自动记录到 `~/.leetcode_agent/user_memory.md`。这些信息跨会话持久保存，不会因 `/clear` 丢失。

你也可以主动让 Agent 记住某些偏好："记住我喜欢用 defaultdict"。

### 题目记忆 — 每题一个

每道做过的题都有一个 `.memories/{id}_{title}.md` 记忆文件，记录做题过程、心得、难点、错误思路。做完题时 Agent 会自动写入总结。

## 解题文件结构

做题时会在当前目录按 AI 分类创建文件（12 个固定分类：dp, greedy, binary_search, two_pointers, dfs_bfs, sorting, stack_queue, tree, graph, design, math_bit, string）：

```
./
├── dp/
│   └── 70_climbing_stairs.py
├── two_pointers/
│   └── 1_two_sum.py
├── design/
│   └── 146_lru_cache.py
├── .memories/
│   ├── 1_two_sum.md
│   ├── 146_lru_cache.md
│   └── 70_climbing_stairs.md
└── ...
```

每个 `.py` 文件包含题目描述（注释）和 LeetCode 官方的 Python3 代码模板。每个 `.md` 记忆文件记录做题过程和心得。

## 调试模式

```bash
DEBUG=1 leetcode
```

日志写入 `~/.leetcode_agent/agent.log`，记录模型调用耗时、token 用量、工具执行详情和完整对话链。实时查看：

```bash
tail -f ~/.leetcode_agent/agent.log
```

## 数据存储

- `~/.leetcode_agent/leetcode.db`（SQLite）— 记忆文件索引和配置
- `.memories/`（当前工作区）— 每道题的 markdown 记忆文件

## 架构

```
src/lc/
├── cli.py           — 命令入口 & REPL 主循环
├── agent.py         — ReAct Agent 核心（chat loop, streaming, LLM client）
├── tools.py         — 13 个工具定义 + 实现 + dispatcher
├── workspace.py     — 文件/分类 helpers（解题文件创建, AI 分类, start_problem）
├── ui.py            — 终端交互（箭头选择器, 渲染 helpers）
├── db.py            — SQLite 数据访问（记忆索引 + 配置）
├── models.py        — 数据模型（Problem）
├── config.py        — 环境变量 & 配置加载
├── leetcode_api.py  — LeetCode GraphQL 客户端
├── codetop_api.py   — CodeTop 高频题 API
├── planner.py       — 每日计划生成
└── display.py       — Rich 渲染
```

## 技术栈

- **CLI**: prompt_toolkit + Rich
- **AI**: DeepSeek (OpenAI 兼容 API，ReAct agent + tool calling)
- **数据**: SQLite + Markdown 记忆文件
- **题目来源**: LeetCode GraphQL API + CodeTop API

## 贡献

欢迎提 Issue 和 Pull Request！无论是 bug 反馈、功能建议还是代码改进，都非常欢迎。

## License

[MIT](LICENSE)
