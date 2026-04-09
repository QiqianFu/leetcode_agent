"""Tool JSON schema definitions — passed to the LLM as the `tools` parameter."""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_problem",
            "description": "按题号查询题目信息。返回题目元信息和是否有记忆文件。",
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
            "name": "search_workspace_files",
            "description": "在当前工作区内按文件名关键词搜索本地题目文件。适合用户只记得题目名或部分关键词时使用。只搜索本地工作区，不查询 LeetCode 线上题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "文件名或题目关键词"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_category_problems",
            "description": "列出当前工作区内某个分类文件夹下的题目文件。适合用户只记得题型或文件夹名时使用。只查看本地工作区目录，不查询 LeetCode 线上题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "分类/文件夹名，如 dp、graph、tree、string"},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_solution",
            "description": "将参考解法追加到用户的解题文件末尾（不会覆盖用户代码）。用户要求看答案、给正确解法时使用。",
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
            "name": "pick_problem",
            "description": "从 CodeTop 高频题库推荐题目供用户选择。仅在用户没有指定题型/关键词、只是说'开始刷题''来一道题'时使用。如果用户指定了题型（如'来一道 DP 题''树的题'），应改用 search_problem 搜索更精准的结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "临时指定标签筛选，如 dp, graph, heap, 二分查找。覆盖 /config 中的 tag 设置"},
                    "difficulty": {"type": "string", "enum": ["Easy", "Medium", "Hard"], "description": "临时指定难度筛选，覆盖 /config 中的 difficulty 设置"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_problem",
            "description": "用英文关键词搜索 LeetCode 题目。返回匹配的题目列表供用户选择。当用户指定了题型或关键词（如'来一道 DP 题''二叉树的题''背包问题'）时优先使用此工具。注意：只支持英文搜索，用户说中文时你需要自行翻译成英文关键词。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "英文搜索关键词，如 climbing stairs, two sum, LRU"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_problem",
            "description": "开始做指定题号的 LeetCode 题（用户明确给了题号时使用）",
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
            "description": "读取某道题的记忆文件内容。用于回顾做题记录、判断是否需要复习等。",
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
            "description": "写入或追加内容到某道题的记忆文件。记录做题心得、难点、提示使用、总结等。",
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
            "name": "get_daily_plan",
            "description": "生成今日刷题计划（新题推荐），基于用户 /config 中的设置",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hot_problems",
            "description": "查看高频题列表（从 CodeTop 获取，按用户配置的公司/标签筛选）",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "公司名（可选，默认用 /config 中的设置）"},
                    "tag": {"type": "string", "description": "标签名（可选，默认用 /config 中的设置）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取信息。适合查找算法讲解、题目思路、数据结构知识、面试经验等。当用户问的问题超出你已有知识范围，或需要最新信息时使用。",
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
            "description": "当用户表达了编码偏好、辅导偏好、习惯等个人偏好时调用。子 agent 会根据当前对话上下文自动合并更新长期偏好记忆文件。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_problems",
            "description": "查找用户已做过的题目中与当前题目算法思路相似的题。开始做一道新题后调用，帮助用户联系过往经验。返回相似题的记忆内容供你引导用户思考方向。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "当前题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_memorize",
            "description": "将当前题目的分析写入 L3 记忆文件。当你检查了用户答案、给出了指导、或用户表示做完时调用。子 agent 根据对话上下文和用户代码自动生成总结。",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_id": {"type": "integer", "description": "题目编号"},
                },
                "required": ["problem_id"],
            },
        },
    },
]
