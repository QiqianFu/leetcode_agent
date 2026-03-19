# LeetCode Agent

终端刷题助手 — 用自然语言和 AI 对话刷 LeetCode。

AI 帮你选题、给提示、讲解思路、管理复习计划，你只需要专注写代码。

![Demo](assets/demo.png)

## 功能

- **自然语言交互** — 不用记指令，直接说"帮我做第 146 题"、"给个提示"、"我做完了"
- **自动创建解题文件** — 按题目分类在当前目录创建 `.py` 文件，包含题目描述和代码模板
- **智能提示** — AI 读取你的代码，给出针对性提示，引导你思考而不是直接给答案
- **间隔复习** — 基于自评分数自动安排复习计划（1/3/7/14/30 天）
- **高频题推荐** — 接入 CodeTop 数据，按目标公司筛选高频面试题
- **刷题统计** — 跟踪做题数量、难度分布、薄弱标签

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
在编辑器中打开文件编写代码，写好后回来继续对话。

> 给个提示
  ⚙ read_solution
你现在用的是暴力双循环，想想有没有办法只遍历一次？
提示：用一个数据结构来记录"你见过的数"。

> 讲解一下
  ⚙ read_solution
这道题最优解是用哈希表...

> 我做完了，感觉还行
你觉得这道题难度如何？请给个自评分：
1=轻松搞定 2=稍有思考 3=想了一阵 4=很吃力 5=没做出来

> 2
  ⚙ submit_result
已提交！用时 15 分钟，安排了 3 次复习。

> 今天还有什么题
  ⚙ get_daily_plan
今日计划：...
```

### 快捷指令

| 指令 | 说明 |
|------|------|
| `/today` | 今日计划（复习 + 新题） |
| `/submit` | 提交当前题目 |
| `/info` | 当前做题状态 |
| `/similar` | 查找相似题目 |
| `/status` | 刷题统计 |
| `/review` | 待复习列表 |
| `/hot` | 高频面试题 |
| `/undo` | 撤回上次提交 |
| `/config` | 设置目标公司、难度、刷题模式 |
| `/help` | 显示帮助 |
| `/quit` | 退出 |

除此之外，所有操作都通过自然语言完成，AI 会自动理解你的意图。

## 解题文件结构

做题时会在当前目录按分类创建文件：

```
./
├── array/
│   └── 1_two_sum.py
├── hash_table/
│   └── 146_lru_cache.py
├── dynamic_programming/
│   └── 70_climbing_stairs.py
└── ...
```

每个文件包含题目描述（注释）和 LeetCode 官方的 Python3 代码模板。

## 复习算法

做完题自评 1-5 分，系统根据分数自动安排复习：

| 情况 | 复习间隔 |
|------|----------|
| 自评 3-5 且用了提示 | 1, 3, 7, 14, 30 天 |
| 自评 3-5 | 1, 7, 30 天 |
| 自评 1-2 | 3, 14 天 |
| 复习时评 4-5 | 额外 +1 天后复习 |
| 复习时评 1-2 | 取消后续复习 |

## 数据存储

所有数据存储在 `~/.leetcode_agent/leetcode.db`（SQLite），包括做题记录、复习计划、统计数据。

## 架构

```
src/lc/
├── cli.py           — 命令入口 & REPL 主循环
├── agent.py         — DeepSeek 对话 Agent（function calling）
├── db.py            — SQLite schema + 数据访问
├── models.py        — 数据模型（Problem / Attempt 等）
├── config.py        — 环境变量 & 配置加载
├── leetcode_api.py  — LeetCode GraphQL 客户端
├── codetop_api.py   — CodeTop 高频题 API
├── scheduler.py     — 间隔复习算法
├── planner.py       — 每日计划生成
├── display.py       — Rich 渲染
└── state.py         — 会话状态管理
```

## 技术栈

- **CLI**: prompt_toolkit + Rich
- **AI**: DeepSeek (OpenAI 兼容 API，支持 function calling)
- **数据**: SQLite
- **题目来源**: LeetCode GraphQL API + CodeTop API

## 贡献

欢迎提 Issue 和 Pull Request！无论是 bug 反馈、功能建议还是代码改进，都非常欢迎。

## License

[MIT](LICENSE)
