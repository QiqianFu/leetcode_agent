# LeetCode Agent

Terminal CLI 刷题助手，智能复习 + AI 辅导。

## Tech Stack
- **CLI**: Typer + Rich
- **DB**: SQLite (~/.leetcode_agent/leetcode.db)
- **LLM**: DeepSeek V4 via OpenAI SDK
- **API**: LeetCode GraphQL

## Setup
```bash
pip install -e .
cp .env.example .env  # 填入 DEEPSEEK_API_KEY
```

## Commands
- `lc today` — 今日计划（复习 + 新题）
- `lc solve <id>` — 开始做题
- `lc hint` — AI 提示
- `lc teach` — AI 详细讲解
- `lc submit` — 提交评分
- `lc status` — 统计面板
- `lc review` — 待复习列表
- `lc similar <id>` — 相似题目
- `lc abandon` — 放弃当前题目

## Architecture
- `src/lc/cli.py` — 命令入口
- `src/lc/db.py` — SQLite schema + 数据访问
- `src/lc/leetcode_api.py` — LeetCode GraphQL 客户端
- `src/lc/ai.py` — DeepSeek 流式响应
- `src/lc/scheduler.py` — 间隔复习算法
- `src/lc/planner.py` — 每日计划生成
- `src/lc/display.py` — Rich 渲染
- `src/lc/state.py` — 会话状态管理

## Review Algorithm
做题时自评 1-5 分：
- 1-2 分且无提示 → 不复习
- struggle score >= 5 → 1, 3, 7, 14, 30 天
- score 3-5 → 1, 7, 30 天
- score < 3 → 3, 14 天

复习时：评 1-2 取消后续复习，评 4-5 加 +1 天复习

## TODO（剩余）

- **slash 命令输出风格统一** — AI 回复有 ⏺ 前缀，slash 命令输出也应有统一的视觉分隔

## 已完成

### 交互优化
- [x] 提交流程跳过 AI — `/submit` + 箭头选择器
- [x] /review、/hot 加箭头选择
- [x] 做题状态 prompt（`146 LRU Cache > `）
- [x] 消息截断保持 tool_call/tool_result 配对完整
- [x] 放弃后不弹选题，只提示 /today
- [x] /info 命令（题目、用时、提示次数）
- [x] Ctrl+C 做题中确认
- [x] 空输入微提示
- [x] /continue 恢复上次未完成的题

### Bug 修复
- [x] hint/teach 计数器（count_hint / count_teach 工具）
- [x] LeetCode API 静默失败 → raise ConnectionError
- [x] 薄弱标签标题改为"按难度排序"

### 功能补全
- [x] /similar 命令（GraphQL 查相似题 + 箭头选择）
- [x] 清理 ai.py 死代码（整个文件删除）
- [x] 新题 tag 过滤（planner 现在会 fetch 再过滤）
- [x] .env.example

### 架构优化
- [x] HTML → markdownify
- [x] DB schema 版本管理（schema_version 表 + _MIGRATIONS）
- [x] /undo 撤回提交
- [x] 统计面板趋势（最近 7 天 + 连续刷题天数）
- [x] Windows 兼容（_flush_stdin + _arrow_select_windows）
