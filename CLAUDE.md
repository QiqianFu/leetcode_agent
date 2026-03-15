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
