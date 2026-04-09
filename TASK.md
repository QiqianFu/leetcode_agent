# TASK

## 待 Tool 化的保留函数

以下函数当前无 agent 调用方，但保留作为未来 tool 的底层实现。

| 函数 | 文件 | 预期用途 |
|------|------|----------|
| `show_problem(problem)` | `src/lc/display.py` | 展示完整题面 tool |
| `fetch_problem_by_slug(title_slug)` | `src/lc/leetcode_api.py` | 内部辅助 |
| `delete_session(key)` / `clear_session()` | `src/lc/db.py` | 重置配置场景 |

---

## 功能 Backlog

### P1 — 影响核心体验

- **题目详情展示 tool** — 把 `display.show_problem()` 包装为 `show_problem` tool，让 agent 能主动展示完整题面
- **工具并行执行** — 模型返回多个 tool call 时当前逐个执行，应用 `ThreadPoolExecutor` 并行；需注意 arrow_select 等 UI 操作不能并行

### P2 — 体验优化

- **slash 命令输出风格统一** — AI 回复有 `⏺` 前缀，slash 命令输出应有对等的视觉分隔
- **工具结果截断** — `read_solution` 读大文件时整个内容进消息历史；应加 token 估算 + 截断提示
- **context 压缩** — 消息历史达到上限时只能 `/clear`；应实现摘要旧消息/丢弃旧 tool results，使 `/clear` 不等于完全失忆

### P3 — 架构演进

- **复习流程** — `DailyPlan` 目前只有 `new_problems`；需要 review queue、间隔复习优先级、`get_daily_plan` 返回复习题
- **跨工作区记忆隔离** — DB 全局，记忆文件工作区局部；同一道题在不同目录会互相覆盖 DB 索引；需要 workspace 维度的隔离字段
- **工作区全量题目发现** — 本地搜索依赖固定 12 个分类目录；非标准目录（旧结构/手动创建）的文件不会被纳入索引

---

## 已完成（归档）

| 项目 | 完成版本 |
|------|----------|
| Memory 三层架构（L1/L2/L3） | v0.4.0 |
| LLM 调用重试（指数退避） | v0.4.0 |
| 分类 fallback 闭合（默认 design） | v0.4.0 |
| display.py 循环依赖修复（TYPE_CHECKING） | v0.5.0 |
| tools.py 拆分（tool_defs + tool_impl + dispatcher） | v0.5.0 |
| Unit tests（36 tests，dispatch/memory/classification） | v0.5.0 |
| mypy 配置（pyproject.toml） | v0.5.0 |
| 双语 README + Mermaid 架构图 + demo.tape | v0.5.0 |
