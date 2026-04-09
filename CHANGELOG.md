# Changelog

## v0.5.0 (2026-04-09)

### New Features

- **双语 README + 架构图** — 重写 README，英文/中文双语，Mermaid agent loop 和 memory system 架构图，`demo.tape` VHS 录制脚本供生成演示 GIF
- **Unit tests** — 36 个单元测试，覆盖工具 dispatcher（registry 完整性、JSON 错误处理、异常捕获）、L3 记忆读写（append/overwrite/边界）、AI 分类（`pick_category_heuristic` 所有路径）；`pytest tests/` 一键运行

### Improvements

- **tools.py 拆分** — 869 行的 `tools.py` 重构为三层：`tool_defs.py`（17 个工具 JSON schema）、`tool_impl/`（按功能分组：workspace / problems / memory / subagents）、`tools.py`（薄层 dispatcher，99 行）；`agent.py` 的 `from lc.tools import TOOLS, execute_tool` 接口不变
- **pyproject.toml** — 新增 `[project.optional-dependencies] dev`（pytest、mypy）、`[tool.pytest.ini_options]`（pythonpath 配置）、`[tool.mypy]`（practical 严格度：`warn_return_any`、`check_untyped_defs`、`ignore_missing_imports`）
- **display.py 循环依赖修复** — `CodetopProblem` 改用 `TYPE_CHECKING` guard 导入，消除循环依赖风险

## v0.4.0 (2026-04-03)

### Breaking Changes

- **DB schema 简化** — 删除旧的 problems/attempts/reviews/tag_stats/schema_version 表，只保留 `problem_memories` 和 `session` 两张表。`init_db()` 自动 DROP 旧表
- **删除旧模块** — 移除 `scheduler.py`、`state.py` 等不再使用的模块

### Improvements

- **AI 分类 fallback 闭合** — `_pick_category_heuristic()` 改用 `_TAG_TO_CATEGORY` 映射表，保证 fallback 路径也只返回 12 个 CATEGORIES 之一，不再泄漏原始 LeetCode tag 到文件夹名
- **全局 console 单例** — theme 定义统一到 `display.py`，`agent.py` 和 `cli.py` 共用同一个 Console 实例
- **LLM client 单例** — `_get_llm_client()` 模块级单例，Agent 和 `_classify_problem()` 共用，避免重复创建连接
- **workspace 边界检查** — `read_solution` 和 `append_solution` 增加路径校验，防止读写工作区外文件
- **start_problem 去重复输出** — 移除函数内的直接 console.print，由模型基于返回的 JSON 自行回复
- **ReAct 循环上限提示** — 16 步达到上限时给用户可见提示，不再静默退出
- **CLAUDE.md 同步** — 文档与代码对齐：修正 db.py 描述、删除不存在的函数引用、更新架构描述

## v0.3.0 (2026-03-31)

### Breaking Changes

- **ReAct Agent 架构** — Agent 从固定流程的 tool calling 重构为 ReAct 循环（think → act → observe → repeat），模型自主推理决策，不再由 system prompt 硬编码"用户说X → 调Y"的规则
- **工具与 UI 分离** — `search_problem` 和 `pick_problem` 不再内部执行 `start_problem`，而是返回用户选择结果，由 agent 自行决定下一步

### New Features

- **调试模式** — `DEBUG=1 leetcode` 启用，日志写入 `~/.leetcode_agent/agent.log`，记录模型调用耗时、token 用量（含 KV cache 命中）、工具执行耗时和结果、完整 messages dump

### Improvements

- **KV cache 优化** — system prompt 改为静态常量，历史消息 append-only，最大化 API 调用的 KV cache 命中率
- **ReAct 循环上限提升至 16 步** — 支持更复杂的多步推理链

## v0.2.0 (2026-03-23)

### New Features

- **刷题计划 `/plan`** — 输入题目名称列表创建刷题计划，支持中文题目名自动翻译匹配，按顺序逐题推进，自动跳过已做题目。`/plan exit` 退出计划模式
- **输入历史** — 上下键恢复之前输入的命令和对话，跨会话保留
- **每日复习题数设置** — `/config` 中可设置每日复习题数（0/1/2/不限），控制 `/today` 中推荐的复习题数量

### Improvements

- `/config` 新增标签过滤和复习题数选项

## v0.1.0

Initial release.
