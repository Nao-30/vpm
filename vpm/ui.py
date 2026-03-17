"""Rich terminal UI components."""

import shutil

from . import __version__
from .style import Style


class UI:
    """Rich terminal UI components."""

    LOGO = r"""
 ╦  ╦╔═╗╔╦╗
 ╚╗╔╝╠═╝║║║
  ╚╝ ╩  ╩ ╩
"""

    BOX_CHARS = {
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
        "h": "─", "v": "│", "t_down": "┬", "t_up": "┴",
        "t_right": "├", "t_left": "┤", "cross": "┼",
    }

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    CHECK = "✔"
    CROSS = "✖"
    ARROW = "➜"
    DOT = "●"
    WARN = "⚠"
    INFO = "ℹ"
    PACKAGE = "📦"
    GEAR = "⚙"
    ROCKET = "🚀"
    FOLDER = "📂"
    FILE = "📄"
    CLOCK = "🕐"
    LINK = "🔗"
    SHIELD = "🛡"
    BROOM = "🧹"

    @staticmethod
    def width() -> int:
        return shutil.get_terminal_size((80, 24)).columns

    @classmethod
    def header(cls, text: str, icon: str = ""):
        w = cls.width()
        prefix = f" {icon} " if icon else " "
        content = f"{prefix}{text} "
        padding = w - len(Style.strip_ansi(content)) - 2
        if padding < 0:
            padding = 0
        line = cls.BOX_CHARS["h"] * padding
        print()
        print(Style.s(f"{cls.BOX_CHARS['tl']}{cls.BOX_CHARS['h'] * (w - 2)}{cls.BOX_CHARS['tr']}", Style.CYAN))
        print(Style.s(cls.BOX_CHARS["v"], Style.CYAN) +
              Style.s(content, Style.BOLD, Style.BRIGHT_WHITE) +
              Style.s(line, Style.DIM, Style.CYAN) +
              Style.s(cls.BOX_CHARS["v"], Style.CYAN))
        print(Style.s(f"{cls.BOX_CHARS['bl']}{cls.BOX_CHARS['h'] * (w - 2)}{cls.BOX_CHARS['br']}", Style.CYAN))

    @classmethod
    def sub_header(cls, text: str):
        print(f"\n  {Style.s(cls.ARROW, Style.CYAN)} {Style.s(text, Style.BOLD)}")

    @classmethod
    def success(cls, text: str):
        print(f"  {Style.s(cls.CHECK, Style.GREEN)} {Style.s(text, Style.GREEN)}")

    @classmethod
    def error(cls, text: str):
        print(f"  {Style.s(cls.CROSS, Style.RED)} {Style.s(text, Style.RED)}")

    @classmethod
    def warning(cls, text: str):
        print(f"  {Style.s(cls.WARN, Style.YELLOW)} {Style.s(text, Style.YELLOW)}")

    @classmethod
    def info(cls, text: str):
        print(f"  {Style.s(cls.INFO, Style.BLUE)} {text}")

    @classmethod
    def dim(cls, text: str):
        print(f"    {Style.s(text, Style.DIM)}")

    @classmethod
    def step(cls, current: int, total: int, text: str):
        counter = Style.s(f"[{current}/{total}]", Style.CYAN, Style.BOLD)
        print(f"\n  {counter} {Style.s(text, Style.BOLD)}")

    @classmethod
    def progress_bar(cls, current: int, total: int, width: int = 40, label: str = ""):
        if total == 0:
            ratio = 1.0
        else:
            ratio = current / total
        filled = int(width * ratio)
        empty = width - filled
        bar = Style.s("█" * filled, Style.GREEN) + Style.s("░" * empty, Style.DIM)
        pct = Style.s(f"{ratio * 100:5.1f}%", Style.BOLD)
        suffix = f" {label}" if label else ""
        print(f"\r  {bar} {pct}{suffix}", end="", flush=True)
        if current == total:
            print()

    @classmethod
    def table(cls, headers: list[str], rows: list[list[str]], max_col_width: int = 40):
        if not rows:
            cls.dim("(no data)")
            return

        col_count = len(headers)
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                plain = Style.strip_ansi(str(cell))
                col_widths[i] = min(max(col_widths[i], len(plain)), max_col_width)

        def fmt_row(cells, style_fn=None):
            parts = []
            for i, cell in enumerate(cells):
                plain = Style.strip_ansi(str(cell))
                pad = col_widths[i] - len(plain)
                padded = str(cell) + " " * max(pad, 0)
                parts.append(padded)
            line = " │ ".join(parts)
            return f"  {line}"

        header_line = fmt_row(
            [Style.s(h, Style.BOLD, Style.UNDERLINE) for h in headers]
        )
        sep = "─┼─".join("─" * w for w in col_widths)
        print(f"\n{header_line}")
        print(f"  {Style.s(sep, Style.DIM)}")
        for row in rows:
            print(fmt_row(row))
        print()

    @classmethod
    def confirm(cls, prompt: str, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        try:
            answer = input(
                f"  {Style.s('?', Style.MAGENTA)} {prompt} {Style.s(suffix, Style.DIM)} "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if not answer:
            return default
        return answer in ("y", "yes")

    @classmethod
    def prompt(cls, text: str, default: str = "") -> str:
        default_hint = f" {Style.s(f'({default})', Style.DIM)}" if default else ""
        try:
            answer = input(
                f"  {Style.s('?', Style.MAGENTA)} {text}{default_hint}: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        return answer or default

    @classmethod
    def select(cls, text: str, options: list[str], default: int = 0) -> int:
        print(f"\n  {Style.s('?', Style.MAGENTA)} {text}")
        for i, opt in enumerate(options):
            marker = Style.s("❯", Style.CYAN) if i == default else " "
            print(f"    {marker} {Style.s(str(i + 1), Style.CYAN)}. {opt}")
        while True:
            try:
                choice = input(f"  {Style.s('Enter choice', Style.DIM)} [{default + 1}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return default
            if not choice:
                return default
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return idx
            except ValueError:
                pass
            cls.error(f"Invalid choice. Enter 1-{len(options)}")

    @classmethod
    def banner(cls):
        if Style.enabled():
            for line in cls.LOGO.strip().split("\n"):
                print(f"  {Style.s(line, Style.CYAN, Style.BOLD)}")
            print(f"  {Style.s(f'Virtual Package Manager v{__version__}', Style.DIM)}")
            print(f"  {Style.s('Robust script orchestration for your VPS', Style.DIM)}")
        else:
            print(f"VPM - Virtual Package Manager v{__version__}")
