# TODO

## 待 Tool 化的保留函数

以下函数当前无调用方，但保留作为未来 agent tool 的底层实现。

| 函数 | 文件 | 用途 | 预期 Tool |
|------|------|------|-----------|
| `show_problem(problem)` | `src/lc/display.py` | 渲染题目详情（Panel + Markdown） | 展示题目详情 |
| `fetch_problem_by_slug(title_slug)` | `src/lc/leetcode_api.py` | 按 slug 获取题目 | 内部辅助 |
| `delete_session(key)` | `src/lc/db.py` | 删除 session KV | 通用基础设施，config 管理可能用到 |
| `clear_session()` | `src/lc/db.py` | 清空所有 session KV | 重置配置等场景 |

## 架构审查发现（待逐项讨论）

### 1. 当前题状态没有真正建模，ReAct 依赖模型记忆

- `CLAUDE.md` 写了 `_build_context()` 和“动态上下文注入”，但代码里没有这个实现。
- 当前流程主要依赖模型记住 `start_problem` 返回的 `problem_id` / `attempt_id` / `file_path`。
- 同时，开始/提交/放弃后又会触发 `_pending_clear`，下一轮直接清空对话历史，进一步削弱上下文连续性。
- 结果是“继续当前题”“给提示”“提交当前题”这些动作缺少稳定、可验证的状态来源。

相关位置：
- `CLAUDE.md`
- `src/lc/agent.py`

### 2. 未完成题目的生命周期被硬编码为“全局只能有一个活跃 attempt”

- 启动应用时会关闭所有未完成 attempt。
- 开始新题时也会先关闭其他未完成 attempt。
- 如果开始新题中途失败，旧题也已经被关闭。
- `abandon_problem` 目前也不是精确放弃目标题，而是直接关闭全部未完成 attempt。

这属于隐藏的全局副作用，不利于“继续之前的题”或多题切换。

相关位置：
- `src/lc/cli.py`
- `src/lc/agent.py`
- `src/lc/db.py`

### 3. 推荐逻辑把 attempted / abandoned / in-progress / solved 混为一类

- `get_attempted_problem_ids()` 会把所有尝试过的题都排除，包括放弃题和未完成题。
- 这会导致用户只要打开过一次，题目后续就不会再作为“新题”被推荐。
- 从产品语义上，至少应该区分 `solved`、`abandoned`、`in_progress`，而不是统一视为“已做”。

相关位置：
- `src/lc/db.py`
- `src/lc/planner.py`

### 4. `max_reviews=不限` 的配置和真实执行不一致

- 配置页里“不限”会存为空字符串。
- `planner.generate_daily_plan()` 的接口也支持 `None` 表示不限。
- 但 agent 在调用时写成了 `int(get_config("max_reviews") or 3)`。
- 结果是 UI 看起来是“不限”，实际执行却是 3。

这是一个明确的硬编码 bug。

相关位置：
- `src/lc/cli.py`
- `src/lc/planner.py`
- `src/lc/agent.py`

### 5. AI 分类、文件夹分类、弱项统计三套口径没有闭合

- 文档里说 category 用于文件夹命名和薄弱项统计。
- 实际上 `tag_stats` 和弱项推荐仍然基于原生 LeetCode tags，不是基于 12 类 category。
- `_classify_problem()` 的 fallback 还可能返回 12 类之外的原始 tag，进一步破坏 category 体系的一致性。

这会导致“分类体系”在设计上分裂成多套口径。

相关位置：
- `src/lc/models.py`
- `src/lc/agent.py`
- `src/lc/db.py`
- `src/lc/planner.py`
- `CLAUDE.md`

### 6. Tool 层没有真正和 UI 分离

- 文档里强调“工具返回数据，不内嵌 UI 流程”。
- 但当前不少 tool 一边返回 JSON，一边直接做终端渲染或箭头选择。
- 这会让 tool 既承担 action，又承担 presentation，测试、复用、替换 UI 都更困难。

这不是功能错误，但会拖慢后续架构演进。

相关位置：
- `src/lc/agent.py`
- `CLAUDE.md`

### 7. 文档与实现存在明显漂移

- `CLAUDE.md` 中提到的一些函数和能力目前并不存在，或与实现不一致。
- 例如：`_build_context()`、`undo_finish_attempt()`、`get_all_tag_stats()`、`get_solved_problem_ids()`。
- 这会导致后续讨论设计时，文档和真实代码基线不一致。

后续建议先决定：以代码为准修文档，还是以文档目标为准补实现。

相关位置：
- `CLAUDE.md`
- `src/lc/db.py`
- `src/lc/agent.py`
