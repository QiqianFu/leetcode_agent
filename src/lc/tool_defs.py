"""Tool JSON schema definitions — passed to the LLM as the `tools` parameter."""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_problem",
            "description": "本地 DB 快速检查某题是否已在用户记忆索引中（已开始过的题）。纯本地查询，不调用 LeetCode API。返回 has_memory + 元信息（若存在）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "display_problem",
            "description": "把指定题目以 Rich panel + markdown 的形式渲染给用户看（不把题面内容回传给你）。适合'让用户看到题面但你自己不需要阅读/引用'的场景，避免 description 占 context。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_problem_detail",
            "description": "从 LeetCode 拉取指定题目的完整详情（标题、难度、标签、描述、代码模板）到你的上下文。不会创建本地 solution/memory 文件，也不渲染给用户。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号（与 title_slug 二选一）"},
                    "title_slug": {"type": "string", "description": "题目 slug（如 two-sum），与 problem_id 二选一"},
                    "include_description": {"type": "boolean", "description": "是否包含题面 markdown，默认 true"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_practiced",
            "description": "列出用户已做过的题（从 L3 记忆索引读取），支持按 tag 子串、difficulty 过滤。纯本地 DB 查询。与 list_hot_problems 互补：一个是未做的高频题，一个是已做的历史记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "标签过滤（子串匹配，大小写不敏感）"},
                    "difficulty": {"type": "string", "enum": ["Easy", "Medium", "Hard"], "description": "难度过滤（精确匹配）"},
                    "limit": {"type": "integer", "description": "返回上限，1-200，默认 30"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_solution",
            "description": "读取用户的解题代码文件。可传 file_path 或 problem_id（二选一），传 problem_id 时自动查找文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "解题文件路径"},
                    "problem_id": {"type": "integer", "description": "题目编号（与 file_path 二选一）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_problem_file",
            "description": "在当前工作区内按题号查找本地解题文件。只搜索当前 CLI 启动目录及其子目录，不查询 LeetCode 线上题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_solution",
            "description": "将参考解法追加到用户的解题文件末尾（不会覆盖用户已有代码）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "解题文件路径"},
                    "content": {"type": "string", "description": "参考解法代码"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_leetcode",
            "description": "按英文关键词搜索 LeetCode 全站题库。返回候选列表 JSON，不触发 UI、不开始做题。英文关键词only。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "英文搜索关键词，如 climbing stairs, two sum, LRU, partition subset"},
                    "limit": {"type": "integer", "description": "返回数量，1-20，默认 5"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_hot_problems",
            "description": "列出 CodeTop 高频题，自动过滤用户已做过的题。返回候选 JSON 列表，不触发 UI、不开始做题。参数未指定时 fallback 到 /config；返回的 used_filters 字段告知实际应用的筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "标签筛选（如 dp, graph, 二分查找）。不传 → 使用 /config 中的 tag"},
                    "difficulty": {"type": "string", "enum": ["Easy", "Medium", "Hard"], "description": "难度筛选。不传 → 使用 /config 中的 difficulty"},
                    "company": {"type": "string", "description": "公司筛选。不传 → 使用 /config 中的 company"},
                    "limit": {"type": "integer", "description": "返回数量，1-30，默认 10"},
                    "randomize": {"type": "boolean", "description": "是否随机排序。不传 → 使用 /config 中的 mode 设置"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "let_user_pick",
            "description": "把若干候选题目展示给用户，触发箭头选择器让用户自选。返回用户选中的 selected_id。纯 UI 工具，不做数据筛选也不开始做题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "choices": {
                        "type": "array",
                        "description": "候选题目数组，每项至少包含 id 和 title，可选 difficulty",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "title": {"type": "string"},
                                "difficulty": {"type": "string"},
                            },
                            "required": ["id", "title"],
                        },
                    },
                    "prompt": {"type": "string", "description": "展示给用户的提示文本（可选）"},
                },
                "required": ["choices"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_problem",
            "description": "开始做指定题号的 LeetCode 题。重型复合动作：拉题面 + AI 分类 + 建 solution.py 和 memory.md + 注册 DB。执行后该题进入 L3 记忆索引（视为已开始）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "读取指定题目的 L3 记忆文件原始内容（markdown）。未开始过的题会返回错误。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "写入或追加内容到某道题的 L3 记忆文件。你需要自己决定 content 的具体内容（区别于 analyze_and_memorize，那个由子 agent 自动生成）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                    "content": {"type": "string", "description": "要写入的内容（markdown 格式）"},
                    "mode": {"type": "string", "enum": ["append", "overwrite"], "description": "写入模式：append 追加，overwrite 覆盖。默认 append"},
                },
                "required": ["problem_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "通过 DuckDuckGo 搜索互联网。返回 title/url/snippet 的 JSON 结果列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（建议用英文以获得更好结果）"},
                    "max_results": {"type": "integer", "description": "返回结果数量，默认 5，最大 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_memory",
            "description": "触发子 agent 读取当前对话上下文，从中提取用户偏好（编码风格、辅导偏好、薄弱点、已掌握模式等），合并进 L2 用户偏好记忆文件。可选传 hint 给子 agent 一个额外提示。",
            "parameters": {
                "type": "object",
                "properties": {
                    "hint": {"type": "string", "description": "可选：给子 agent 的额外指引，如'重点记录用户对递归的偏好'"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_problems",
            "description": "从用户已做过的题目中找出与指定题目相似的题，返回相似题的 L3 记忆内容。子 agent 通过 LLM 基于 criteria 判断相似度（默认：算法/数据结构/解题模式）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "当前题目编号"},
                    "max_results": {"type": "integer", "description": "返回相似题数量上限，1-10，默认 3"},
                    "criteria": {"type": "string", "description": "可选：自定义相似性判断标准（如'同样是 DP 但状态设计不同'、'同样的数据结构但难度更高'）"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_memorize",
            "description": "为指定题目生成并写入 L3 做题总结。子 agent 会读取当前对话上下文（你的提示、用户代码、发现的错误等）自动生成总结内容。默认 section 为 解题思路/踩坑记录/关键收获/复杂度，可通过 sections 参数覆盖。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：自定义 section 名称列表（按顺序），如 ['核心思路', 'AC 代码要点']。不传使用默认 4 个 section",
                    },
                    "focus": {"type": "string", "description": "可选：要求子 agent 重点关注某个方面（如'详细记录状态转移推导过程'）"},
                },
                "required": ["problem_id"],
            },
        },
    },
]
