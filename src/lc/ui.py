from __future__ import annotations

import sys

from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text


def flush_stdin():
    """Flush any pending terminal responses (e.g. CPR) from stdin."""
    if sys.platform == "win32":
        try:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
        except Exception:
            pass
    else:
        import select
        try:
            while select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
        except Exception:
            pass


def agent_renderable(content: str):
    """Render agent response with ⏺ prefix, content indented."""
    t = Table(show_header=False, show_edge=False, box=None, padding=0, expand=True)
    t.add_column(width=2, no_wrap=True)
    t.add_column()
    t.add_row(Text("⏺", style="blue"), Markdown(content))
    return t


def arrow_select(choices: list[tuple[str, any]], load_more=None) -> any | None:
    """Arrow-key selector using raw terminal input. Returns selected value or None.

    If *load_more* is a callable, pressing 'n' will call it to get more
    choices (list of (label, value) tuples) which are appended to the list.
    """
    if sys.platform == "win32":
        return _arrow_select_windows(choices, load_more=load_more)
    import tty
    import termios

    flush_stdin()

    selected = 0
    has_more = load_more is not None
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def _render():
        lines = []
        for i, (label, _) in enumerate(choices):
            if i == selected:
                lines.append(f"  \033[1;34m❯\033[0m \033[1m{label}\033[0m")
            else:
                lines.append(f"    \033[2m{label}\033[0m")
        lines.append("")
        hint = "  \033[2m↑↓ 选择  Enter 确认"
        if has_more:
            hint += "  n 换一批"
        hint += "  q 跳过\033[0m"
        lines.append(hint)
        return "\r\n".join(lines)

    def _clear():
        """Restore cursor to saved position and clear to end of screen."""
        sys.stdout.write("\033[u\033[J")

    try:
        tty.setraw(fd)
        sys.stdout.flush()
        sys.stdout.write("\033[s")
        sys.stdout.write(_render())
        sys.stdout.flush()

        while True:
            ch = sys.stdin.read(1)

            if ch == "\r" or ch == "\n":  # Enter
                _clear()
                sys.stdout.flush()
                return choices[selected][1]

            if ch == "q" or ch == "\x1b":
                if ch == "\x1b":
                    next1 = sys.stdin.read(1)
                    if next1 == "[":
                        next2 = sys.stdin.read(1)
                        if next2 == "A":  # Up
                            selected = max(0, selected - 1)
                        elif next2 == "B":  # Down
                            selected = min(len(choices) - 1, selected + 1)
                        else:
                            pass
                    else:
                        # Plain Escape
                        _clear()
                        sys.stdout.flush()
                        return None
                else:
                    # 'q'
                    _clear()
                    sys.stdout.flush()
                    return None

            elif ch == "n" and has_more:
                new_choices = load_more()
                if new_choices:
                    selected = len(choices)  # jump to first new item
                    choices.extend(new_choices)
                else:
                    has_more = False

            elif ch == "k":
                selected = max(0, selected - 1)
            elif ch == "j":
                selected = min(len(choices) - 1, selected + 1)

            # Re-render
            _clear()
            sys.stdout.write(_render())
            sys.stdout.flush()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _arrow_select_windows(choices: list[tuple[str, any]], load_more=None) -> any | None:
    """Windows fallback: numbered prompt instead of arrow keys."""
    while True:
        for i, (label, _) in enumerate(choices):
            print(f"  {i + 1}. {label}")
        print()
        hint = "  输入编号"
        if load_more:
            hint += " / n 换一批"
        hint += " (q 跳过): "
        try:
            raw = input(hint).strip()
            if raw.lower() == "q" or not raw:
                return None
            if raw.lower() == "n" and load_more:
                new_choices = load_more()
                if new_choices:
                    choices.extend(new_choices)
                else:
                    load_more = None
                continue
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx][1]
        except (ValueError, EOFError):
            pass
        return None
