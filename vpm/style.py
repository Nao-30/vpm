"""Terminal styling with automatic detection of color support."""

import os
import re
import sys


class Style:
    """ANSI color and style helpers."""

    _force_no_color = os.environ.get("NO_COLOR") is not None
    _is_tty = sys.stdout.isatty()

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    STRIKE = "\033[9m"

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Bright foreground
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"

    @classmethod
    def enabled(cls) -> bool:
        return cls._is_tty and not cls._force_no_color

    @classmethod
    def s(cls, text: str, *styles: str) -> str:
        if not cls.enabled():
            return text
        prefix = "".join(styles)
        return f"{prefix}{text}{cls.RESET}"

    @classmethod
    def strip_ansi(cls, text: str) -> str:
        return re.sub(r"\033\[[0-9;]*m", "", text)
