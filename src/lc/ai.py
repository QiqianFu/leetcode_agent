from __future__ import annotations

from openai import OpenAI

from lc.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from lc.models import Problem

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

console = Console()

HINT_SYSTEM_PROMPT = """\
你是一个 LeetCode 导师。用户正在做一道题但卡住了。
给出一个简短的概念性提示，引导他们找到正确的思路。
不要写任何代码。不要透露完整的算法。
用中文回答。如果这不是用户第一次请求提示，可以更具体一些。
如果用户提供了他们当前的代码，根据代码中的思路给出针对性的提示。"""

TEACH_SYSTEM_PROMPT = """\
你是一个 LeetCode 导师。详细讲解这道题：
1. 这道题属于什么类型/类别
2. 2-3 种可能的解法，按效率排序
3. 每种解法的时间和空间复杂度
4. 最优解法的伪代码
用中文回答，清晰易懂。
如果用户提供了他们当前的代码，先评价他们的思路，再给出讲解。"""


def _get_client() -> OpenAI:
    if not DEEPSEEK_API_KEY:
        console.print("[red]错误: 请在 .env 文件中设置 DEEPSEEK_API_KEY[/red]")
        raise SystemExit(1)
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def _build_problem_context(problem: Problem, hints_used: int = 0, user_code: str = "") -> str:
    parts = [
        f"题目: {problem.id}. {problem.title}",
        f"难度: {problem.difficulty}",
        f"标签: {', '.join(problem.tags)}",
        "",
        problem.description or "(无题目描述)",
    ]
    if hints_used > 0:
        parts.append(f"\n用户已经请求了 {hints_used} 次提示，请给出更具体的提示。")
    if user_code:
        parts.append(f"\n用户当前的代码:\n```python\n{user_code}\n```")
    return "\n".join(parts)


def stream_response(system_prompt: str, user_content: str) -> str:
    """Stream a response from DeepSeek and render it live as markdown."""
    client = _get_client()
    stream = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=True,
        max_tokens=2048,
        temperature=0.3,
    )

    full_text = ""
    with Live(Markdown(""), console=console, refresh_per_second=8) as live:
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_text += delta
                live.update(Markdown(full_text))
    return full_text


def get_hint(problem: Problem, hints_used: int = 0, user_code: str = "") -> str:
    context = _build_problem_context(problem, hints_used, user_code=user_code)
    return stream_response(HINT_SYSTEM_PROMPT, context)


def get_explanation(problem: Problem, user_code: str = "") -> str:
    context = _build_problem_context(problem, user_code=user_code)
    return stream_response(TEACH_SYSTEM_PROMPT, context)


ROUTE_SYSTEM_PROMPT = """\
你是一个 LeetCode 刷题 CLI 助手的指令路由器。
用户输入了一段文本，请判断用户的意图最接近以下哪个指令：

可用指令：
- 设置 (/config): 设置公司和难度偏好
- 开始 (/start): 开始今日练习，显示今日计划
- 下一题 (/next): 自动选下一道题
- 做 <题号> (/solve <id>): 做指定题目，如 "做 146"
- 提示 (/hint): 获取当前题的提示
- 讲解 (/teach): 获取当前题的详细讲解
- 提交 (/submit): 提交当前题目并评分
- 放弃 (/abandon): 放弃当前题目
- 高频 (/hot): 查看高频面试题
- 统计 (/status): 查看刷题统计
- 复习 (/review): 查看待复习题目
- 帮助 (/help): 显示帮助
- 退出 (/quit): 退出程序

请只回复一个 JSON 对象，格式如下：
- 如果匹配到指令: {"match": true, "command": "指令名", "args": "参数或null"}
  - command 必须是以下之一: config, start, next, solve, hint, teach, submit, abandon, hot, status, review, help, quit
  - 如果是 solve 指令，args 填题号
- 如果没有匹配的指令: {"match": false, "message": "友好的提示信息，告诉用户没有这个功能，并建议可用的指令"}

只返回 JSON，不要其他内容。"""


def route_command(user_input: str) -> dict:
    """Use AI to determine which command the user intended."""
    import json
    client = _get_client()
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
        max_tokens=256,
        temperature=0.1,
    )
    text = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"match": False, "message": "抱歉，我没有理解你的意思。输入 /help 查看可用指令。"}
