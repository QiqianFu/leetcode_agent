# Bug Tracking — 2026-04-25 审计

按 Tier 分级,每条记录:位置 / 现象 / 修复策略 / 状态。

状态: `[ ]` 待修, `[~]` 修中, `[x]` 已修+测试.

---

## Tier 1 — 数据/正确性 bug

### [x] #1 — `cli.handle_config` 网络故障误清除 tag
**位置**: `src/lc/cli.py:99`
**现象**: `fetch_tags()` 返回 `[]`(网络失败) 时,用户输入新 tag 进入 `else` 分支,沉默清除原有 `cfg_tag`。
**修复**: 把 "用户输入空 = 清除/跳过" 与 "网络失败 = 不变更" 分离成两条路径。
**测试**: 添加单元测试 `test_handle_config_preserves_tag_on_network_failure`。

### [x] #2 — `_call_model` 非 retryable 异常导致消息历史 corrupt
**位置**: `src/lc/agent.py:166-171`
**现象**: `BadRequestError` / `APIError` / `AuthenticationError` 等非 retryable 错误抛出后,user msg + 部分 assistant tool_call 已写入 `self.messages`,但缺 tool 响应配对 → 下次对话 400。
**修复**: 在 retryable except 之后加 `except Exception` 兜底回滚 + 友好提示。
**测试**: 已有 `TestReactLoopRollback` 覆盖 retryable;添加 non-retryable 用例。

### [x] #3 — `_summarize_session_context` 漏算多种持久化工具
**位置**: `src/lc/agent.py:284-296`
**现象**: 仅检查 `write_memory`。`analyze_and_memorize` / `update_user_memory` / `append_solution` 都写盘,但用户达上限时不会显示 "你的记忆已保存" 提示。
**修复**: 扩成 `_PERSISTENT_TOOLS` 集合,任何一个出现都返 True。

### [x] #4 — `arrow_select` 单按 Esc 永久阻塞
**位置**: `src/lc/ui.py:96`
**现象**: TTY raw 模式下 `read(1)` 是阻塞的,Esc 后没第二字符时 UI 卡死。
**修复**: 用 `select.select(..., timeout=0.05)` 探测有无后续字符;无 → Plain Esc → 退出。

### [x] #5 — `arrow_select` Windows fallback 输入错误后立即返回 None
**位置**: `src/lc/ui.py:138-164`
**现象**: `while True` 中 `return None` 在 try/except 之后无条件执行,任何笔误/越界数字都直接退出而非重新提示。
**修复**: 把 try/except 缩到只包 `int(raw)` 解析,无效输入 `continue` 回到循环顶,EOFError 单独处理。

### [x] #6 — `Agent` warning_threshold 严格 == 比较容易跳过
**位置**: `src/lc/agent.py:144-150`
**现象**: 每轮通常加 2~5 条消息,跨过 threshold 时未必恰等于,所以警告永远不弹。
**修复**: 改用 `>=` + 一个 `_history_warned` flag,且当 msg_count 回落到阈值之下时重置 flag(用于 /clear 后重新预警)。

### [x] #7 — `_find_tag_id` 空白/单字符 tag 滥匹配
**位置**: `src/lc/codetop_api.py:174-178`
**现象**: `" "` 通过 substring 匹配命中任何带空格的 tag(如 `"Hash Table"`)。
**修复**: 入口加 `if not tag_lower or len(tag_lower) < 2: return None`。

### [x] #8 — shrinkage check `after_bytes` 与实际写入字节数不匹配
**位置**: `src/lc/tool_impl/subagents.py:124-145, 318-340`
**现象**: 用 `proposed = result.strip()` 算 size,但 `write_text(result)` 写的是未 strip 版本。
**修复**: 写入也用 `proposed`(strip 过的),保持 size 与磁盘一致。

---

## Tier 2 — 描述/实现不一致

### [x] #9 — SYSTEM_PROMPT 说 `update_user_memory` 零参数,实际有 hint
**位置**: `src/lc/agent.py:79` vs `tool_defs.py:227`
**修复**: 把 prompt 改为 `update_user_memory(hint?)`。

### [x] #10 — `tool_read_solution` 返回原始字符串,与其他工具风格不一致
**位置**: `src/lc/tool_impl/workspace.py:102-117`
**修复**: 改为 JSON 包装 (`status`, `file_path`, `bytes`, `content`)。同时更新 schema 描述。

### [x] #11 — `tool_web_search` 错误返回纯字符串,正常返回 JSON
**位置**: `src/lc/tool_impl/subagents.py:66-87`
**修复**: 把空 query 错误改为 JSON。

### [x] #12 — `tool_check_problem` 不验证 memory_file 是否存在于磁盘
**位置**: `src/lc/tool_impl/workspace.py:15-33`
**修复**: 加 `memory_file_exists` bool 字段,与 `read_memory` / `find_similar_problems` 保持一致。

### [x] #13 — `let_user_pick` schema 要求 title,实现不强制
**位置**: `src/lc/tool_defs.py:142-162` vs `src/lc/tool_impl/problems.py:194-199`
**修复**: 实现侧检查 `title.strip()` 非空,否则跳过该项;若全部跳过则返回格式错误。

### [x] #14 — 产品规则引用的字符串与实际消息不完全对照
**位置**: `src/lc/agent.py:88` vs `subagents.py:171, 240-243`
**修复**: prompt 改为基于 `similar_problems` 数组是否为空判断,避免字符串脆性。同时把 `subagent_hallucinated` 也囊括。

### [x] #15 — `classify_problem` substring 匹配漏掉空格/连字符形式
**位置**: `src/lc/workspace.py:130-156`
**现象**: AI 回 `"two pointers"` 不匹配 category `"two_pointers"`(下划线)。
**修复**: 把 answer 的 `[\s-]+` 规范成 `_` 后再 substring。

---

## Tier 3 — 边界/冲突未处理

### [x] #16 — `start_problem` 跨工作区无条件 upsert 覆盖 DB
**位置**: `src/lc/workspace.py:273`
**修复**: 检测 existing memory_file 与新 rel_memory 不一致 → 在 flags 里加 `cross_workspace_db_overwrite: True`。schema/prompt 注明该字段含义。

### [x] #17 — `_pick_from_codetop` 静默丢弃无法识别的 tag
**位置**: `src/lc/planner.py:46`
**修复**: stats 里加 `tag_resolved: bool` 和 `tag_requested`;`tool_list_hot_problems` 在 `used_filters` 里也透出。

### [x] #18 — `find_similar_problems` 单次 hallucination 沉默吞掉
**位置**: `src/lc/tool_impl/subagents.py:234-246`
**修复**: `hallucination_count == 1` 时仍透出 `dropped_hallucinations` 字段,但不否决整个结果。

### [x] #19 — `leetcode_api.fetch_problem` 通过 `searchKeywords` 找 ID 不可靠
**位置**: `src/lc/leetcode_api.py:137-154`
**修复**: limit=5 失败时降级到 limit=25 重试一次再放弃。

### [x] #20 — codetop_api 缓存永不失效
**位置**: `src/lc/codetop_api.py:51-78`
**修复**: 加 1 小时 TTL。

### [x] #21 — `_sanitize_messages` 不处理 tool_calls.arguments
**位置**: `src/lc/agent.py:298-312`
**修复**: 同时清洗 `tool_calls[].function.arguments`。

### [x] #22 — `_pick_from_codetop` randomize 未达 target 时不告诉调用方
**位置**: `src/lc/planner.py:102-110`
**修复**: stats 里加 `target_unmet: bool`。

### [x] #23 — `tool_find_problem_file` 多文件命中只返第一个
**位置**: `src/lc/tool_impl/workspace.py:120-134`
**修复**: 加 `total_matches` + `all_files`(>1 时)。

### [x] #24 — cli.py 旧 `mode="tag"` 残留只在 UI 默认值层迁移,DB 未清写
**位置**: `src/lc/cli.py:78-79`
**修复**: 在 `init_db()` 或 `show_welcome` 启动时检测并 `set_config("mode", "default")` 持久化迁移。

### [x] #25 — `cli.py` 引入未使用的 `DIFFICULTY_COLORS`
**位置**: `src/lc/cli.py:8`
**修复**: 删除 import。

### [x] #26 — `let_user_pick` 不区分 "用户取消" vs "内部错误"
**位置**: `src/lc/tool_impl/problems.py:208-213`
**修复**: 文本上澄清(已是 cancelled);考虑后续 arrow_select 加返回元信息(本次先不动 UI 层)。

### [x] #27 — `tool_append_solution` 不校验目标是不是解题文件
**位置**: `src/lc/tool_impl/workspace.py:137-179`
**修复**: 校验 `p.suffix == ".py"`,否则返 status=error。

---

## 验证策略
每修一项跑一次 `pytest tests/ -x`。为新行为新增的回归测试加在 `tests/test_atomicity_fixes.py` 或新建 `tests/test_audit_fixes.py`。
