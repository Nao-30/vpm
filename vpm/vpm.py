#!/usr/bin/env python3
"""
VPM - Virtual Package Manager
A robust, interactive package/script orchestrator for VPS environments.
Manages execution of arbitrary installation scripts with full tracking,
logging, and recovery support.

Requires: Python 3.12+
"""

__version__ = "1.0.0"
__app_name__ = "vpm"

import argparse
import datetime
import enum
import errno
import hashlib
import json
import os
import platform
import pty
import pwd
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# ANSI Color & Style Helpers
# ─────────────────────────────────────────────────────────────────────────────

class Style:
    """Terminal styling with automatic detection of color support."""

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


# ─────────────────────────────────────────────────────────────────────────────
# UI Components
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Paths
# ─────────────────────────────────────────────────────────────────────────────

class Config:
    """Manages VPM paths and configuration following XDG conventions."""

    def __init__(self):
        xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

        self.config_dir = Path(xdg_config) / __app_name__
        self.data_dir = Path(xdg_data) / __app_name__
        self.logs_dir = self.data_dir / "logs"
        self.lock_file = self.data_dir / "vpm-lock.json"
        self.config_file = self.config_dir / "config.json"
        self.completions_dir = self.config_dir / "completions"
        self.bin_dir_user = Path.home() / ".local" / "bin"
        self.bin_dir_global = Path("/usr/local/bin")
        self.script_path = Path(os.path.abspath(__file__))

    def ensure_dirs(self):
        """Create all necessary directories."""
        for d in [self.config_dir, self.data_dir, self.logs_dir, self.completions_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_app_log_dir(self, app_name: str) -> Path:
        """Get or create log directory for a specific app."""
        safe_name = self._safe_name(app_name)
        d = self.logs_dir / safe_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r"[^\w\-.]", "_", name.strip().lower())

    def load_config(self) -> dict:
        if self.config_file.exists():
            try:
                return json.loads(self.config_file.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save_config(self, data: dict):
        self.ensure_dirs()
        self.config_file.write_text(json.dumps(data, indent=2) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Lock File (State Tracking)
# ─────────────────────────────────────────────────────────────────────────────

class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AppStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class StepRecord:
    index: int
    label: str
    command: str
    status: str = StepStatus.PENDING.value
    exit_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    log_file: str | None = None
    error_summary: str | None = None
    command_hash: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict) -> "StepRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AppRecord:
    name: str
    display_name: str
    status: str = AppStatus.PENDING.value
    steps: list[StepRecord] = field(default_factory=list)
    log_dir: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    manifest_source: str | None = None
    requires: list[str] = field(default_factory=list)
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AppRecord":
        steps_data = d.pop("steps", [])
        filtered = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        record = cls(**filtered)
        record.steps = [StepRecord.from_dict(s) for s in steps_data]
        return record

    def recalculate(self):
        self.total_steps = len(self.steps)
        self.completed_steps = sum(
            1 for s in self.steps if s.status == StepStatus.SUCCESS.value
        )
        self.failed_steps = sum(
            1 for s in self.steps if s.status == StepStatus.FAILED.value
        )
        if self.failed_steps > 0 and self.completed_steps > 0:
            self.status = AppStatus.PARTIAL.value
        elif self.failed_steps > 0:
            self.status = AppStatus.FAILED.value
        elif self.completed_steps == self.total_steps and self.total_steps > 0:
            self.status = AppStatus.COMPLETED.value
        elif self.completed_steps > 0:
            self.status = AppStatus.IN_PROGRESS.value
        else:
            self.status = AppStatus.PENDING.value


class LockFile:
    """Thread-safe lock file manager for tracking installation state."""

    def __init__(self, config: Config):
        self.config = config
        self.path = config.lock_file
        self._data: dict[str, AppRecord] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                meta = raw.get("_meta", {})
                apps = raw.get("apps", {})
                self._data = {}
                for key, val in apps.items():
                    self._data[key] = AppRecord.from_dict(val)
            except (json.JSONDecodeError, OSError, TypeError) as e:
                UI.warning(f"Lock file corrupted, backing up and starting fresh: {e}")
                if self.path.exists():
                    backup = self.path.with_suffix(
                        f".backup.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.json"
                    )
                    shutil.copy2(self.path, backup)
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        self.config.ensure_dirs()
        out = {
            "_meta": {
                "version": __version__,
                "updated_at": datetime.datetime.now().isoformat(),
                "user": os.environ.get("USER", "unknown"),
                "hostname": platform.node(),
            },
            "apps": {k: v.to_dict() for k, v in self._data.items()},
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2, default=str) + "\n")
        tmp.replace(self.path)

    def get_app(self, name: str) -> AppRecord | None:
        safe = Config._safe_name(name)
        return self._data.get(safe)

    def set_app(self, record: AppRecord):
        safe = Config._safe_name(record.name)
        record.updated_at = datetime.datetime.now().isoformat()
        record.recalculate()
        self._data[safe] = record
        self._save()

    def remove_app(self, name: str):
        safe = Config._safe_name(name)
        if safe in self._data:
            del self._data[safe]
            self._save()

    def all_apps(self) -> dict[str, AppRecord]:
        return dict(self._data)

    def has_app(self, name: str) -> bool:
        return Config._safe_name(name) in self._data


# ─────────────────────────────────────────────────────────────────────────────
# Manifest Parser
# ─────────────────────────────────────────────────────────────────────────────

class ManifestApp:
    """Represents an app parsed from the manifest file."""

    def __init__(
        self,
        name: str,
        steps: list[dict[str, str]],
        description: str = "",
        requires: list[str] | None = None,
    ):
        self.name = name
        self.steps = steps  # [{"label": "...", "command": "..."}, ...]
        self.description = description
        self.requires = requires or []  # list of app names this depends on


class ManifestParser:
    """
    Parses VPM manifest files.

    Manifest format (YAML-like but parsed manually to avoid PyYAML dependency):

    ```
    # VPM Manifest File
    # Format:
    #
    # [app_name] Optional Description
    # - label: Step Label
    #   run: command to execute
    #   run: |
    #     multiline
    #     command
    # - label: Another Step
    #   run: another command
    #
    # [another_app]
    # - run: simple command (label auto-generated)
    ```
    """

    @classmethod
    def parse_file(cls, filepath: Path) -> list[ManifestApp]:
        if not filepath.exists():
            raise FileNotFoundError(f"Manifest file not found: {filepath}")

        content = filepath.read_text()
        return cls.parse_string(content)

    @classmethod
    def parse_string(cls, content: str) -> list[ManifestApp]:
        apps: list[ManifestApp] = []
        current_app_name: str | None = None
        current_app_desc: str = ""
        current_steps: list[dict[str, str]] = []
        current_step: dict[str, str] | None = None
        current_requires: list[str] = []
        in_multiline = False
        multiline_indent = 0
        multiline_lines: list[str] = []

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines and comments (but not inside multiline)
            if in_multiline:
                # Check if this line is still part of the multiline block
                if line and not line[0].isspace() and stripped and not stripped.startswith("#"):
                    # End of multiline
                    if current_step is not None:
                        current_step["command"] = "\n".join(multiline_lines).strip()
                    in_multiline = False
                    multiline_lines = []
                    # Don't increment i, re-process this line
                    continue
                elif not stripped:
                    # Empty line might be part of multiline or a separator
                    # Check next non-empty line
                    multiline_lines.append("")
                    i += 1
                    continue
                else:
                    # Part of multiline content
                    # Remove common indent
                    dedented = line
                    if len(line) > multiline_indent:
                        dedented = line[multiline_indent:]
                    elif line.strip():
                        dedented = line.lstrip()
                    multiline_lines.append(dedented)
                    i += 1
                    continue

            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            # App header: [app_name] optional description
            app_match = re.match(r"^\[([^\]]+)\]\s*(.*)?$", stripped)
            if app_match:
                # Save previous app
                if current_app_name is not None:
                    if current_step is not None:
                        current_steps.append(current_step)
                    if current_steps:
                        apps.append(
                            ManifestApp(
                                current_app_name,
                                current_steps,
                                current_app_desc,
                                current_requires,
                            )
                        )

                current_app_name = app_match.group(1).strip()
                current_app_desc = (app_match.group(2) or "").strip()
                current_steps = []
                current_step = None
                current_requires = []
                i += 1
                continue

            # Step definition: - label: ..., or - run: ...
            step_match = re.match(r"^-\s+(.*)", stripped)
            if step_match and current_app_name is not None:
                # Save previous step
                if current_step is not None:
                    current_steps.append(current_step)

                rest = step_match.group(1).strip()
                current_step = {"label": "", "command": ""}

                # Check for label: or run:
                kv = re.match(r"^(label|run):\s*(.*)", rest, re.IGNORECASE)
                if kv:
                    key = kv.group(1).lower()
                    val = kv.group(2).strip()
                    if key == "label":
                        current_step["label"] = val
                    elif key == "run":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                        else:
                            current_step["command"] = val
                else:
                    # Simple format: - command here
                    current_step["command"] = rest
                    current_step["label"] = rest[:60]

                i += 1
                continue

            # Top-level app directive: requires
            if current_app_name is not None and current_step is None:
                req_match = re.match(r"^\s*requires:\s*(.*)", stripped, re.IGNORECASE)
                if req_match:
                    deps = [
                        d.strip()
                        for d in req_match.group(1).split(",")
                        if d.strip()
                    ]
                    current_requires.extend(deps)
                    i += 1
                    continue

            # Continuation keys (label: or run:) for current step
            if current_step is not None:
                kv = re.match(r"^\s+(label|run):\s*(.*)", line)
                if kv:
                    key = kv.group(1).lower()
                    val = kv.group(2).strip()
                    if key == "label":
                        current_step["label"] = val
                    elif key == "run":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                        else:
                            current_step["command"] = val
                    i += 1
                    continue

            i += 1

        # Finalize multiline if still open
        if in_multiline and current_step is not None:
            current_step["command"] = "\n".join(multiline_lines).strip()

        # Save last step and app
        if current_step is not None:
            current_steps.append(current_step)
        if current_app_name is not None and current_steps:
            apps.append(
                ManifestApp(
                    current_app_name,
                    current_steps,
                    current_app_desc,
                    current_requires if 'current_requires' in dir() else [],
                )
            )

        # Auto-label steps that have no label
        for app in apps:
            for idx, step in enumerate(app.steps):
                if not step.get("label"):
                    cmd_preview = step.get("command", "")[:50]
                    step["label"] = f"Step {idx + 1}: {cmd_preview}"

        return apps

    @classmethod
    def generate_template(cls) -> str:
        return textwrap.dedent("""\
            # ═══════════════════════════════════════════════════════════════
            # VPM Manifest File
            # ═══════════════════════════════════════════════════════════════
            #
            # This file defines apps and their installation steps.
            # VPM will execute each step in order, tracking progress
            # so that interrupted installations can be safely resumed.
            #
            # ─── FORMAT ───────────────────────────────────────────────────
            #
            # [app_name] Optional description of the app
            # - label: Human readable step name
            #   run: shell command to execute
            #
            # - label: Multi-line command example
            #   run: |
            #     first line
            #     second line
            #     third line
            #
            # - run: simple one-liner (label auto-generated)
            #
            # ─── NOTES ────────────────────────────────────────────────────
            #
            # • Commands run with the current user's shell (bash -e)
            # • Use sudo where needed (user must have sudo access)
            # • Each step is tracked independently
            # • If a step fails, subsequent steps are skipped
            # • Use `vpm retry <app>` to retry from the failed step
            # • Use `vpm reset <app>` to start fresh
            # • Environment variables are inherited from current shell
            # • Use 'requires: app1, app2' to declare dependencies
            # • Dependencies are resolved automatically — install order is computed
            # • If a dependency fails, dependent apps are skipped
            #
            # ─── EXAMPLES ─────────────────────────────────────────────────

            [essential_tools] Essential system utilities
            - label: Update package lists
              run: sudo apt-get update -y

            - label: Install core utilities
              run: sudo apt-get install -y curl wget git htop vim unzip jq tree

            - label: Install network tools
              run: sudo apt-get install -y net-tools dnsutils mtr-tiny

            [docker] Docker Engine & Compose
            requires: essential_tools

            - label: Install prerequisites
              run: sudo apt-get install -y ca-certificates curl gnupg lsb-release

            - label: Add Docker GPG key
              run: |
                sudo install -m 0755 -d /etc/apt/keyrings
                curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \\
                  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
                sudo chmod a+r /etc/apt/keyrings/docker.gpg

            - label: Add Docker repository
              run: |
                echo "deb [arch=$(dpkg --print-architecture) \\
                  signed-by=/etc/apt/keyrings/docker.gpg] \\
                  https://download.docker.com/linux/ubuntu \\
                  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \\
                  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

            - label: Install Docker Engine
              run: |
                sudo apt-get update -y
                sudo apt-get install -y docker-ce docker-ce-cli \\
                  containerd.io docker-buildx-plugin docker-compose-plugin

            - label: Add current user to docker group
              run: sudo usermod -aG docker $USER

            - label: Verify Docker installation
              run: docker --version && docker compose version

            # [node_js] Node.js via NVM
            # - label: Install NVM
            #   run: |
            #     curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
            #     export NVM_DIR="$HOME/.nvm"
            #     [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
            #
            # - label: Install Node.js LTS
            #   run: |
            #     export NVM_DIR="$HOME/.nvm"
            #     [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
            #     nvm install --lts
            #     nvm use --lts
            #     node --version && npm --version
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Command Executor
# ─────────────────────────────────────────────────────────────────────────────

class Executor:
    """Executes shell commands with full logging and tracking."""

    def __init__(self, config: Config, lock: LockFile):
        self.config = config
        self.lock = lock
        self._interrupted = False
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        self._interrupted = True
        print()
        UI.warning("Interrupt received. Finishing current step gracefully...")

    def compute_command_hash(self, command: str) -> str:
        return hashlib.sha256(command.encode()).hexdigest()[:12]

    def resolve_order(
        self, apps: list[ManifestApp], lock: LockFile
    ) -> list[ManifestApp]:
        """
        Topologically sort apps based on their 'requires' field.
        Raises an error on circular dependencies.
        """
        by_name: dict[str, ManifestApp] = {}
        for app in apps:
            safe = Config._safe_name(app.name)
            by_name[safe] = app

        # Build adjacency list
        graph: dict[str, list[str]] = {Config._safe_name(a.name): [] for a in apps}
        for app in apps:
            safe = Config._safe_name(app.name)
            for dep in app.requires:
                dep_safe = Config._safe_name(dep)
                if dep_safe not in by_name:
                    # Dependency not in this manifest — check if already installed
                    existing = lock.get_app(dep)
                    if existing and existing.status == AppStatus.COMPLETED.value:
                        UI.dim(
                            f"Dependency '{dep}' for '{app.name}' "
                            f"already satisfied (installed previously)"
                        )
                        continue
                    else:
                        raise ValueError(
                            f"App '{app.name}' requires '{dep}', but it is "
                            f"not in the manifest and not previously installed. "
                            f"Add '{dep}' to your manifest or install it first."
                        )
                graph[safe].append(dep_safe)

        # Kahn's algorithm for topological sort
        in_degree: dict[str, int] = {n: 0 for n in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] = in_degree.get(dep, 0)  # ensure exists
                    # node depends on dep, so dep must come first
                    # we track the reverse: in_degree counts how many depend on you
                    pass

        # Actually build it properly: edge from dep -> node (dep must come before node)
        reverse_graph: dict[str, list[str]] = {n: [] for n in graph}
        in_degree = {n: 0 for n in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in reverse_graph:
                    reverse_graph[dep].append(node)
                    in_degree[node] += 1

        queue = [n for n in in_degree if in_degree[n] == 0]
        order: list[str] = []

        while queue:
            queue.sort()  # deterministic order
            node = queue.pop(0)
            order.append(node)
            for neighbor in reverse_graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(graph):
            remaining = set(graph.keys()) - set(order)
            raise ValueError(
                f"Circular dependency detected involving: {', '.join(remaining)}"
            )

        return [by_name[name] for name in order if name in by_name]

    def execute_app(self, app: ManifestApp, force: bool = False) -> AppRecord:
        """Execute all steps for an app, with skip/resume logic."""
        now = datetime.datetime.now()
        app_log_dir = self.config.get_app_log_dir(app.name)

        # Check existing record
        record = self.lock.get_app(app.name)
        is_resume = False

        if record and not force:
            if record.status == AppStatus.COMPLETED.value:
                # Check if steps changed
                existing_hashes = {s.command_hash for s in record.steps}
                new_hashes = {
                    self.compute_command_hash(s["command"]) for s in app.steps
                }
                if existing_hashes == new_hashes:
                    UI.success(f"'{app.name}' is already fully installed. Use --force to reinstall.")
                    return record
                else:
                    UI.warning(f"'{app.name}' manifest has changed since last install.")
                    if not UI.confirm("Re-run with updated steps?"):
                        return record
                    force = True

            elif record.status in (
                AppStatus.PARTIAL.value,
                AppStatus.FAILED.value,
                AppStatus.IN_PROGRESS.value,
            ):
                UI.warning(f"'{app.name}' has a previous incomplete/failed installation.")
                is_resume = True

        if force or not record:
            # Build fresh record
            steps = []
            for idx, step_def in enumerate(app.steps):
                steps.append(
                    StepRecord(
                        index=idx,
                        label=step_def["label"],
                        command=step_def["command"],
                        command_hash=self.compute_command_hash(step_def["command"]),
                    )
                )
            record = AppRecord(
                name=app.name,
                display_name=app.name,
                steps=steps,
                log_dir=str(app_log_dir),
                created_at=now.isoformat(),
                requires=app.requires,
            )
            if app.description:
                record.display_name = f"{app.name} ({app.description})"

        record.status = AppStatus.IN_PROGRESS.value
        self.lock.set_app(record)

        UI.header(f"Installing: {record.display_name}", UI.PACKAGE)
        UI.info(f"Log directory: {Style.s(str(app_log_dir), Style.UNDERLINE)}")
        total = len(record.steps)

        # Summary log for the app
        summary_log = app_log_dir / f"summary_{now.strftime('%Y%m%d_%H%M%S')}.log"

        with open(summary_log, "w") as summary_f:
            summary_f.write(f"VPM Installation Summary\n")
            summary_f.write(f"{'=' * 60}\n")
            summary_f.write(f"App: {record.display_name}\n")
            summary_f.write(f"Started: {now.isoformat()}\n")
            summary_f.write(f"User: {os.environ.get('USER', 'unknown')}\n")
            summary_f.write(f"Host: {platform.node()}\n")
            summary_f.write(f"Total Steps: {total}\n")
            summary_f.write(f"{'=' * 60}\n\n")

            all_success = True
            for step in record.steps:
                if self._interrupted:
                    UI.warning("Skipping remaining steps due to interrupt.")
                    step.status = StepStatus.SKIPPED.value
                    summary_f.write(f"[SKIPPED] Step {step.index + 1}: {step.label} (interrupted)\n")
                    continue

                # Skip already completed steps (resume mode)
                if is_resume and step.status == StepStatus.SUCCESS.value:
                    UI.step(step.index + 1, total, f"{step.label}")
                    UI.success(f"Already completed — skipping")
                    summary_f.write(f"[SKIPPED/OK] Step {step.index + 1}: {step.label}\n")
                    continue

                UI.step(step.index + 1, total, step.label)
                UI.dim(f"$ {step.command[:100]}{'...' if len(step.command) > 100 else ''}")

                success = self._run_step(step, app_log_dir, summary_f)
                if not success:
                    all_success = False
                    # Skip remaining steps
                    for remaining in record.steps[step.index + 1:]:
                        if remaining.status != StepStatus.SUCCESS.value:
                            remaining.status = StepStatus.SKIPPED.value
                            summary_f.write(
                                f"[SKIPPED] Step {remaining.index + 1}: {remaining.label} "
                                f"(previous step failed)\n"
                            )
                    break

                UI.progress_bar(step.index + 1, total)

            # Final status
            end_time = datetime.datetime.now()
            record.recalculate()

            summary_f.write(f"\n{'=' * 60}\n")
            summary_f.write(f"Finished: {end_time.isoformat()}\n")
            summary_f.write(f"Duration: {(end_time - now).total_seconds():.1f}s\n")
            summary_f.write(f"Status: {record.status}\n")
            summary_f.write(
                f"Steps: {record.completed_steps}/{record.total_steps} succeeded, "
                f"{record.failed_steps} failed\n"
            )
            summary_f.write(f"{'=' * 60}\n")

        self.lock.set_app(record)

        print()
        if record.status == AppStatus.COMPLETED.value:
            UI.success(
                f"All {record.total_steps} steps completed successfully! "
                f"({(end_time - now).total_seconds():.1f}s)"
            )
        elif record.status == AppStatus.PARTIAL.value:
            UI.warning(
                f"{record.completed_steps}/{record.total_steps} steps succeeded, "
                f"{record.failed_steps} failed. Use 'vpm retry {app.name}' to retry."
            )
        elif record.status == AppStatus.FAILED.value:
            UI.error(
                f"Installation failed. {record.failed_steps} step(s) failed. "
                f"Check logs: {summary_log}"
            )
        UI.dim(f"Summary: {summary_log}")

        return record

    def _run_step(
        self, step: StepRecord, log_dir: Path, summary_f
    ) -> bool:
        """Run a single step command with full logging using PTY for interactive support."""
        now = datetime.datetime.now()
        step.status = StepStatus.RUNNING.value
        step.started_at = now.isoformat()

        # Create log file for this step
        safe_label = re.sub(r"[^\w\-.]", "_", step.label)[:50]
        log_file = log_dir / f"step_{step.index:03d}_{safe_label}_{now.strftime('%H%M%S')}.log"
        step.log_file = str(log_file)

        try:
            with open(log_file, "w") as lf:
                lf.write(f"VPM Step Execution Log\n")
                lf.write(f"{'─' * 60}\n")
                lf.write(f"Step: {step.index + 1} — {step.label}\n")
                lf.write(f"Started: {now.isoformat()}\n")
                lf.write(f"Command:\n{step.command}\n")
                lf.write(f"{'─' * 60}\n\n")
                lf.flush()

                shell = os.environ.get("SHELL", "/bin/bash")
                if "bash" not in shell and "zsh" not in shell:
                    shell = "/bin/bash"

                env = os.environ.copy()
                # DO NOT force noninteractive — let debconf/ncurses work
                # Only set if user hasn't explicitly set it
                # env.setdefault("DEBIAN_FRONTEND", "noninteractive")

                # Use PTY so that interactive programs (debconf, ncurses menus,
                # passwd prompts, etc.) work correctly.  We sit in the middle:
                # the child thinks it has a real terminal, we copy bytes between
                # the real stdin/stdout and the child, AND tee everything to the
                # log file.

                exit_code = self._pty_exec(
                    shell_path=shell,
                    command=step.command,
                    env=env,
                    log_fh=lf,
                )

                end_time = datetime.datetime.now()
                step.exit_code = exit_code
                step.finished_at = end_time.isoformat()
                step.duration_seconds = (end_time - now).total_seconds()

                lf.write(f"\n{'─' * 60}\n")
                lf.write(f"Exit Code: {exit_code}\n")
                lf.write(f"Duration: {step.duration_seconds:.1f}s\n")
                lf.write(f"Finished: {end_time.isoformat()}\n")

                if exit_code == 0:
                    step.status = StepStatus.SUCCESS.value
                    UI.success(f"Done ({step.duration_seconds:.1f}s)")
                    summary_f.write(
                        f"[OK] Step {step.index + 1}: {step.label} "
                        f"(exit={exit_code}, {step.duration_seconds:.1f}s)\n"
                    )
                    return True
                else:
                    step.status = StepStatus.FAILED.value
                    # Read last few lines of log for error summary
                    try:
                        log_content = Path(step.log_file).read_text()
                        last_lines = log_content.strip().split("\n")[-5:]
                        step.error_summary = "\n".join(last_lines)[-500:]
                    except OSError:
                        step.error_summary = f"Exit code {exit_code}"

                    UI.error(
                        f"Failed (exit code {exit_code}, {step.duration_seconds:.1f}s)"
                    )
                    UI.dim(f"Log: {log_file}")
                    if step.error_summary:
                        for err_line in step.error_summary.split("\n")[-3:]:
                            cleaned = Style.strip_ansi(err_line.strip())
                            if cleaned:
                                UI.dim(f"  {cleaned}")
                    summary_f.write(
                        f"[FAIL] Step {step.index + 1}: {step.label} "
                        f"(exit={exit_code}, {step.duration_seconds:.1f}s)\n"
                    )
                    if step.error_summary:
                        summary_f.write(
                            f"  Error: {Style.strip_ansi(step.error_summary[:200])}\n"
                        )
                    return False

        except OSError as e:
            step.status = StepStatus.FAILED.value
            step.error_summary = str(e)
            step.finished_at = datetime.datetime.now().isoformat()
            UI.error(f"Execution error: {e}")
            summary_f.write(
                f"[ERROR] Step {step.index + 1}: {step.label} — {e}\n"
            )
            return False

    def _pty_exec(
        self,
        shell_path: str,
        command: str,
        env: dict[str, str],
        log_fh,
    ) -> int:
        """
        Execute a command inside a PTY so interactive programs (debconf,
        ncurses config screens, sudo password prompts, etc.) work correctly.

        stdin/stdout of the real terminal are wired through to the child.
        All output is also tee'd into log_fh.
        """
        # Create PTY pair
        master_fd, slave_fd = pty.openpty()

        pid = os.fork()
        if pid == 0:
            # ── CHILD ────────────────────────────────────────────────
            os.close(master_fd)
            # Create a new session and set the slave as controlling terminal
            os.setsid()
            import fcntl
            import termios
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            # Redirect stdin/stdout/stderr to the slave PTY
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            os.execve(
                shell_path,
                [shell_path, "-e", "-c", command],
                env,
            )
            # execve never returns on success
            os._exit(127)

        # ── PARENT ────────────────────────────────────────────────────
        os.close(slave_fd)

        # If our stdin is a TTY, put it in raw mode so keystrokes
        # (arrow keys, tab, etc.) reach the child unmodified.
        stdin_fd = sys.stdin.fileno()
        stdin_is_tty = os.isatty(stdin_fd)
        old_tattr = None

        if stdin_is_tty:
            import termios
            import tty
            try:
                old_tattr = termios.tcgetattr(stdin_fd)
                tty.setraw(stdin_fd)
            except termios.error:
                old_tattr = None

        try:
            self._pty_copy_loop(master_fd, stdin_fd, stdin_is_tty, log_fh)
        finally:
            # Restore terminal no matter what
            if old_tattr is not None:
                import termios
                try:
                    termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, old_tattr)
                except termios.error:
                    pass
            os.close(master_fd)

        # Reap child
        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        return 1

    def _pty_copy_loop(
        self,
        master_fd: int,
        stdin_fd: int,
        stdin_is_tty: bool,
        log_fh,
    ):
        """
        Bidirectional copy between the real terminal and the PTY master.
        Also writes child output to the log file.
        """
        fds = [master_fd]
        if stdin_is_tty:
            fds.append(stdin_fd)

        while True:
            try:
                rfds, _, _ = select.select(fds, [], [], 0.1)
            except (select.error, ValueError):
                break

            if master_fd in rfds:
                try:
                    data = os.read(master_fd, 4096)
                except OSError as e:
                    if e.errno == errno.EIO:
                        # Child closed its side — normal at exit
                        break
                    raise
                if not data:
                    break
                # Write to real stdout (user sees interactive output)
                try:
                    os.write(sys.stdout.fileno(), data)
                except OSError:
                    pass
                # Tee to log file (strip ANSI later if needed, but keep raw for now)
                try:
                    log_fh.write(data.decode("utf-8", errors="replace"))
                    log_fh.flush()
                except (OSError, ValueError):
                    pass

            if stdin_is_tty and stdin_fd in rfds:
                try:
                    data = os.read(stdin_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                try:
                    os.write(master_fd, data)
                except OSError:
                    break


# ─────────────────────────────────────────────────────────────────────────────
# Shell Completions Generator
# ─────────────────────────────────────────────────────────────────────────────

class Completions:
    """Generate shell completions for bash, zsh, and fish."""

    COMMANDS = [
        "init", "install", "status", "list", "logs", "retry",
        "reset", "setup", "doctor", "completions", "version", "help"
    ]

    @classmethod
    def zsh_completion(cls) -> str:
        cmds = " ".join(cls.COMMANDS)
        return textwrap.dedent(f"""\
            #compdef vpm
            # VPM - Virtual Package Manager completion for Zsh
            # Auto-generated by vpm v{__version__}

            _vpm() {{
                local -a commands
                commands=(
                    'init:Initialize a new VPM workspace with manifest template'
                    'install:Install apps from manifest file or CLI'
                    'status:Show installation status of all tracked apps'
                    'list:List all managed apps and their states'
                    'logs:View or tail logs for an app'
                    'retry:Retry failed installations from the failed step'
                    'reset:Reset tracking for an app (allows reinstallation)'
                    'setup:Install vpm to PATH for global access'
                    'doctor:Self-diagnose dependencies and fix issues'
                    'completions:Generate and install shell completions'
                    'version:Show version information'
                    'help:Show help information'
                )

                _arguments -C \\
                    '1:command:->command' \\
                    '*::arg:->args'

                case "$state" in
                    command)
                        _describe -t commands 'vpm command' commands
                        ;;
                    args)
                        case $words[1] in
                            install)
                                _arguments \\
                                    '--file[Manifest file to use]:file:_files' \\
                                    '--force[Force reinstallation]' \\
                                    '--dry-run[Show what would be done without executing]' \\
                                    '*:app name:'
                                ;;
                            init)
                                _arguments \\
                                    '1:directory:_directories'
                                ;;
                            logs|retry|reset|status)
                                local -a apps
                                if [[ -f "$HOME/.local/share/vpm/vpm-lock.json" ]]; then
                                    apps=(${{(f)"$(python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.local/share/vpm/vpm-lock.json'
if p.exists():
    d = json.loads(p.read_text())
    for k in d.get('apps', {{}}):
        print(k)
" 2>/dev/null)"}})
                                fi
                                _describe -t apps 'installed app' apps
                                ;;
                            setup)
                                _arguments \\
                                    '--global[Install to /usr/local/bin (requires sudo)]' \\
                                    '--user[Install to ~/.local/bin (default)]'
                                ;;
                            completions)
                                _arguments \\
                                    '--shell[Target shell]:shell:(zsh bash fish)'
                                ;;
                        esac
                        ;;
                esac
            }}

            _vpm "$@"
        """)

    @classmethod
    def bash_completion(cls) -> str:
        cmds = " ".join(cls.COMMANDS)
        return textwrap.dedent(f"""\
            # VPM - Virtual Package Manager completion for Bash
            # Auto-generated by vpm v{__version__}

            _vpm_completions() {{
                local cur prev commands
                COMPREPLY=()
                cur="${{COMP_WORDS[COMP_CWORD]}}"
                prev="${{COMP_WORDS[COMP_CWORD-1]}}"

                commands="{cmds}"

                if [[ $COMP_CWORD -eq 1 ]]; then
                    COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
                    return 0
                fi

                case "${{COMP_WORDS[1]}}" in
                    install)
                        if [[ "$cur" == -* ]]; then
                            COMPREPLY=( $(compgen -W "--file --force --dry-run" -- "$cur") )
                        elif [[ "$prev" == "--file" ]]; then
                            COMPREPLY=( $(compgen -f -- "$cur") )
                        fi
                        ;;
                    init)
                        COMPREPLY=( $(compgen -d -- "$cur") )
                        ;;
                    logs|retry|reset|status)
                        local apps
                        if [[ -f "$HOME/.local/share/vpm/vpm-lock.json" ]]; then
                            apps=$(python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.local/share/vpm/vpm-lock.json'
if p.exists():
    d = json.loads(p.read_text())
    print(' '.join(d.get('apps', {{}}).keys()))
" 2>/dev/null)
                        fi
                        COMPREPLY=( $(compgen -W "$apps" -- "$cur") )
                        ;;
                    setup)
                        COMPREPLY=( $(compgen -W "--global --user" -- "$cur") )
                        ;;
                    completions)
                        if [[ "$prev" == "--shell" ]]; then
                            COMPREPLY=( $(compgen -W "zsh bash fish" -- "$cur") )
                        else
                            COMPREPLY=( $(compgen -W "--shell" -- "$cur") )
                        fi
                        ;;
                esac
            }}

            complete -F _vpm_completions vpm
        """)

    @classmethod
    def fish_completion(cls) -> str:
        lines = [
            f"# VPM - Virtual Package Manager completion for Fish",
            f"# Auto-generated by vpm v{__version__}",
            "",
            "# Disable file completions by default",
            "complete -c vpm -f",
            "",
        ]
        descs = {
            "init": "Initialize a new VPM workspace",
            "install": "Install apps from manifest",
            "status": "Show installation status",
            "list": "List all managed apps",
            "logs": "View logs for an app",
            "retry": "Retry failed installations",
            "reset": "Reset tracking for an app",
            "setup": "Install vpm to PATH",
            "doctor": "Self-diagnose and fix issues",
            "completions": "Generate shell completions",
            "version": "Show version information",
            "help": "Show help",
        }
        for cmd, desc in descs.items():
            lines.append(
                f"complete -c vpm -n '__fish_use_subcommand' -a '{cmd}' -d '{desc}'"
            )
        lines.extend([
            "",
            "# install subcommand options",
            "complete -c vpm -n '__fish_seen_subcommand_from install' -l file -d 'Manifest file' -rF",
            "complete -c vpm -n '__fish_seen_subcommand_from install' -l force -d 'Force reinstall'",
            "complete -c vpm -n '__fish_seen_subcommand_from install' -l dry-run -d 'Dry run'",
            "",
            "# setup subcommand options",
            "complete -c vpm -n '__fish_seen_subcommand_from setup' -l global -d 'Install globally'",
            "complete -c vpm -n '__fish_seen_subcommand_from setup' -l user -d 'Install for user'",
        ])
        return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# CLI Application
# ─────────────────────────────────────────────────────────────────────────────

class VPM:
    """Main VPM application."""

    def __init__(self):
        self.config = Config()
        self.config.ensure_dirs()
        self.lock = LockFile(self.config)
        self.executor = Executor(self.config, self.lock)

    # ── INIT ──────────────────────────────────────────────────────────────

    def cmd_init(self, args):
        """Initialize a VPM workspace with a manifest template."""
        UI.header("Initialize VPM Workspace", UI.FOLDER)

        target = Path(args.path).resolve() if args.path else Path.cwd()
        manifest_path = target / "vpm-manifest.yaml"

        if manifest_path.exists() and not args.force:
            UI.warning(f"Manifest already exists: {manifest_path}")
            if not UI.confirm("Overwrite existing manifest?"):
                UI.info("Aborted.")
                return

        target.mkdir(parents=True, exist_ok=True)
        template = ManifestParser.generate_template()
        manifest_path.write_text(template)

        UI.success(f"Created manifest: {manifest_path}")
        UI.info("Edit the manifest file to define your apps and installation steps.")
        UI.info(f"Then run: {Style.s('vpm install --file ' + str(manifest_path), Style.BOLD)}")
        UI.dim(f"Or navigate to {target} and run: vpm install")

    # ── INSTALL ───────────────────────────────────────────────────────────

    def cmd_install(self, args):
        """Install apps from manifest file or inline definition."""
        UI.header("VPM Install", UI.ROCKET)

        apps_to_install: list[ManifestApp] = []

        # Determine source
        if args.file:
            manifest_path = Path(args.file).resolve()
            UI.info(f"Reading manifest: {manifest_path}")
            try:
                all_apps = ManifestParser.parse_file(manifest_path)
            except FileNotFoundError as e:
                UI.error(str(e))
                UI.info(f"Run '{Style.s('vpm init', Style.BOLD)}' to create a manifest template.")
                sys.exit(1)
            except Exception as e:
                UI.error(f"Failed to parse manifest: {e}")
                sys.exit(1)

            if args.apps:
                # Filter to specified apps
                app_names = {Config._safe_name(a) for a in args.apps}
                for app in all_apps:
                    if Config._safe_name(app.name) in app_names:
                        apps_to_install.append(app)
                missing = app_names - {Config._safe_name(a.name) for a in apps_to_install}
                if missing:
                    UI.warning(f"Apps not found in manifest: {', '.join(missing)}")
                    available = [a.name for a in all_apps]
                    UI.info(f"Available: {', '.join(available)}")
            else:
                apps_to_install = all_apps
        elif args.apps:
            # Try to find default manifest
            search_paths = [
                Path.cwd() / "vpm-manifest.yaml",
                Path.cwd() / "vpm-manifest.yml",
                Path.cwd() / ".vpm-manifest.yaml",
                self.config.config_dir / "manifest.yaml",
            ]
            found = None
            for p in search_paths:
                if p.exists():
                    found = p
                    break

            if found:
                UI.info(f"Using manifest: {found}")
                try:
                    all_apps = ManifestParser.parse_file(found)
                except Exception as e:
                    UI.error(f"Failed to parse manifest: {e}")
                    sys.exit(1)
                app_names = {Config._safe_name(a) for a in args.apps}
                for app in all_apps:
                    if Config._safe_name(app.name) in app_names:
                        apps_to_install.append(app)
                missing = app_names - {Config._safe_name(a.name) for a in apps_to_install}
                if missing:
                    UI.error(f"Apps not found in manifest: {', '.join(missing)}")
                    sys.exit(1)
            else:
                UI.error("No manifest file found. Specify one with --file or run 'vpm init'.")
                sys.exit(1)
        else:
            # Auto-discover manifest
            search_paths = [
                Path.cwd() / "vpm-manifest.yaml",
                Path.cwd() / "vpm-manifest.yml",
                Path.cwd() / ".vpm-manifest.yaml",
                self.config.config_dir / "manifest.yaml",
            ]
            found = None
            for p in search_paths:
                if p.exists():
                    found = p
                    break

            if not found:
                UI.error("No manifest file found.")
                UI.info(f"Create one with: {Style.s('vpm init', Style.BOLD)}")
                UI.info(f"Or specify one with: {Style.s('vpm install --file <path>', Style.BOLD)}")
                sys.exit(1)

            UI.info(f"Using manifest: {found}")
            try:
                apps_to_install = ManifestParser.parse_file(found)
            except Exception as e:
                UI.error(f"Failed to parse manifest: {e}")
                sys.exit(1)

        if not apps_to_install:
            UI.warning("No apps to install.")
            return

        # Resolve dependency order
        try:
            apps_to_install = self.executor.resolve_order(apps_to_install, self.lock)
        except ValueError as e:
            UI.error(f"Dependency error: {e}")
            sys.exit(1)

        # Show dependency info
        has_deps = any(a.requires for a in apps_to_install)
        if has_deps:
            UI.sub_header("Resolved installation order (based on dependencies):")
            for i, app in enumerate(apps_to_install):
                dep_info = ""
                if app.requires:
                    dep_info = Style.s(
                        f" (requires: {', '.join(app.requires)})", Style.DIM
                    )
                print(f"    {Style.s(str(i + 1), Style.CYAN)}. {app.name}{dep_info}")

        # Dry run
        if args.dry_run:
            UI.sub_header("Dry Run — nothing will be executed")
            for app in apps_to_install:
                print(f"\n  {Style.s(UI.PACKAGE, Style.CYAN)} {Style.s(app.name, Style.BOLD)}"
                      f"  {Style.s(app.description, Style.DIM) if app.description else ''}")
                for i, step in enumerate(app.steps):
                    status_icon = Style.s(UI.DOT, Style.GRAY)
                    existing = self.lock.get_app(app.name)
                    if existing:
                        for es in existing.steps:
                            if es.index == i and es.status == StepStatus.SUCCESS.value:
                                status_icon = Style.s(UI.CHECK, Style.GREEN)
                                break
                            elif es.index == i and es.status == StepStatus.FAILED.value:
                                status_icon = Style.s(UI.CROSS, Style.RED)
                                break
                    print(f"    {status_icon} {step['label']}")
                    UI.dim(f"  $ {step['command'][:80]}{'...' if len(step['command']) > 80 else ''}")
            return

        # Confirmation
        print()
        UI.sub_header("Apps to install:")
        total_steps = 0
        for app in apps_to_install:
            existing = self.lock.get_app(app.name)
            status_text = ""
            if existing:
                if existing.status == AppStatus.COMPLETED.value:
                    status_text = Style.s(" (already installed)", Style.GREEN)
                elif existing.status in (AppStatus.PARTIAL.value, AppStatus.FAILED.value):
                    status_text = Style.s(
                        f" (resumable: {existing.completed_steps}/{existing.total_steps} done)",
                        Style.YELLOW,
                    )
            print(f"  {Style.s(UI.PACKAGE, Style.CYAN)} {Style.s(app.name, Style.BOLD)} "
                  f"— {len(app.steps)} step(s){status_text}")
            total_steps += len(app.steps)

        print()
        UI.info(f"Total: {len(apps_to_install)} app(s), {total_steps} step(s)")

        if not args.yes and not UI.confirm("Proceed with installation?", default=True):
            UI.info("Aborted.")
            return

        # Execute with dependency checks
        results: list[AppRecord] = []
        skipped_due_to_dep: list[str] = []
        for i, app in enumerate(apps_to_install):
            if self.executor._interrupted:
                UI.warning("Installation interrupted. Remaining apps skipped.")
                break

            # Check that all dependencies succeeded
            dep_failed = False
            for dep in app.requires:
                dep_record = self.lock.get_app(dep)
                if not dep_record or dep_record.status != AppStatus.COMPLETED.value:
                    dep_failed = True
                    UI.error(
                        f"Skipping '{app.name}': dependency '{dep}' "
                        f"is not successfully installed."
                    )
                    skipped_due_to_dep.append(app.name)
                    break

            if dep_failed:
                # Create a record marking it as failed due to deps
                record = self.lock.get_app(app.name) or AppRecord(
                    name=app.name,
                    display_name=app.name,
                    created_at=datetime.datetime.now().isoformat(),
                )
                record.status = AppStatus.FAILED.value
                record.updated_at = datetime.datetime.now().isoformat()
                self.lock.set_app(record)
                results.append(record)
                continue

            result = self.executor.execute_app(app, force=args.force)
            results.append(result)

        # Final summary
        print()
        UI.header("Installation Summary", UI.SHIELD)
        headers = ["App", "Status", "Steps", "Failed", "Duration"]
        rows = []
        for r in results:
            status_display = {
                AppStatus.COMPLETED.value: Style.s("✔ Completed", Style.GREEN),
                AppStatus.PARTIAL.value: Style.s("◐ Partial", Style.YELLOW),
                AppStatus.FAILED.value: Style.s("✖ Failed", Style.RED),
                AppStatus.IN_PROGRESS.value: Style.s("… In Progress", Style.BLUE),
                AppStatus.PENDING.value: Style.s("○ Pending", Style.DIM),
            }.get(r.status, r.status)

            total_dur = sum(
                s.duration_seconds or 0 for s in r.steps
            )
            rows.append([
                r.display_name,
                status_display,
                f"{r.completed_steps}/{r.total_steps}",
                str(r.failed_steps) if r.failed_steps else Style.s("0", Style.DIM),
                f"{total_dur:.1f}s",
            ])
        UI.table(headers, rows)

    # ── STATUS ────────────────────────────────────────────────────────────

    def cmd_status(self, args):
        """Show installation status."""
        UI.header("Installation Status", UI.SHIELD)

        apps = self.lock.all_apps()
        if not apps:
            UI.info("No apps tracked yet. Run 'vpm install' to get started.")
            return

        if args.app:
            safe = Config._safe_name(args.app)
            if safe not in apps:
                UI.error(f"App '{args.app}' not found in tracking.")
                return
            record = apps[safe]
            self._show_app_detail(record)
        else:
            headers = ["App", "Status", "Progress", "Failed", "Last Updated"]
            rows = []
            for name, record in apps.items():
                status_display = {
                    AppStatus.COMPLETED.value: Style.s("✔ Completed", Style.GREEN),
                    AppStatus.PARTIAL.value: Style.s("◐ Partial", Style.YELLOW),
                    AppStatus.FAILED.value: Style.s("✖ Failed", Style.RED),
                    AppStatus.IN_PROGRESS.value: Style.s("… Running", Style.BLUE),
                    AppStatus.PENDING.value: Style.s("○ Pending", Style.DIM),
                }.get(record.status, record.status)

                updated = ""
                if record.updated_at:
                    try:
                        dt = datetime.datetime.fromisoformat(record.updated_at)
                        updated = dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        updated = record.updated_at

                rows.append([
                    record.display_name,
                    status_display,
                    f"{record.completed_steps}/{record.total_steps}",
                    str(record.failed_steps) if record.failed_steps else Style.s("0", Style.DIM),
                    updated,
                ])
            UI.table(headers, rows)

    def _show_app_detail(self, record: AppRecord):
        """Show detailed status for a single app."""
        UI.sub_header(f"App: {record.display_name}")
        print(f"  Status: {record.status}")
        print(f"  Log Dir: {record.log_dir}")
        print(f"  Created: {record.created_at}")
        print(f"  Updated: {record.updated_at}")
        print()

        headers = ["#", "Step", "Status", "Exit", "Duration", "Log"]
        rows = []
        for step in record.steps:
            status_icon = {
                StepStatus.SUCCESS.value: Style.s("✔", Style.GREEN),
                StepStatus.FAILED.value: Style.s("✖", Style.RED),
                StepStatus.RUNNING.value: Style.s("…", Style.BLUE),
                StepStatus.SKIPPED.value: Style.s("⊘", Style.DIM),
                StepStatus.PENDING.value: Style.s("○", Style.DIM),
            }.get(step.status, step.status)

            dur = f"{step.duration_seconds:.1f}s" if step.duration_seconds else "-"
            exit_code = str(step.exit_code) if step.exit_code is not None else "-"
            log_ref = Path(step.log_file).name if step.log_file else "-"

            rows.append([
                str(step.index + 1),
                step.label[:40],
                status_icon,
                exit_code,
                dur,
                log_ref,
            ])
        UI.table(headers, rows)

        if record.failed_steps > 0:
            UI.info(f"Retry with: {Style.s(f'vpm retry {record.name}', Style.BOLD)}")

    # ── LIST ──────────────────────────────────────────────────────────────

    def cmd_list(self, args):
        """List all managed apps."""
        self.cmd_status(argparse.Namespace(app=None))

    # ── LOGS ──────────────────────────────────────────────────────────────

    def cmd_logs(self, args):
        """View logs for an app."""
        UI.header("Logs", UI.FILE)

        if not args.app:
            # List all app log directories
            apps = self.lock.all_apps()
            if not apps:
                UI.info("No apps tracked.")
                return
            for name, record in apps.items():
                if record.log_dir:
                    log_path = Path(record.log_dir)
                    files = sorted(log_path.glob("*")) if log_path.exists() else []
                    print(
                        f"  {Style.s(UI.FOLDER, Style.CYAN)} {name}: "
                        f"{Style.s(str(log_path), Style.UNDERLINE)} "
                        f"({len(files)} files)"
                    )
            return

        safe = Config._safe_name(args.app)
        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found.")
            return

        log_dir = Path(record.log_dir) if record.log_dir else None
        if not log_dir or not log_dir.exists():
            UI.warning("No log directory found for this app.")
            return

        if args.step is not None:
            # Show specific step log
            if 0 <= args.step < len(record.steps):
                step = record.steps[args.step]
                if step.log_file and Path(step.log_file).exists():
                    UI.sub_header(f"Log: Step {args.step + 1} — {step.label}")
                    print()
                    content = Path(step.log_file).read_text()
                    print(content)
                else:
                    UI.warning("No log file for this step.")
            else:
                UI.error(f"Step index {args.step} out of range (0-{len(record.steps) - 1}).")
            return

        if args.follow:
            # Show latest summary log and follow
            summaries = sorted(log_dir.glob("summary_*.log"), reverse=True)
            if summaries:
                target = summaries[0]
                UI.info(f"Following: {target}")
                try:
                    subprocess.run(["tail", "-f", str(target)])
                except KeyboardInterrupt:
                    pass
            else:
                UI.warning("No summary logs found.")
            return

        # List all log files for this app
        UI.sub_header(f"Logs for: {record.display_name}")
        UI.dim(f"Directory: {log_dir}")
        print()

        files = sorted(log_dir.glob("*"), reverse=True)
        if not files:
            UI.warning("No log files found.")
            return

        for f in files:
            size = f.stat().st_size
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            size_str = self._format_size(size)

            # 1. Format the time string here to avoid complex nesting
            time_str = mtime.strftime("%H:%M:%S")

            is_summary = f.name.startswith("summary_")
            icon = UI.FILE if not is_summary else "📋"
            name_style = Style.BOLD if is_summary else ""

            # 2. Use the simple variable inside the f-string
            print(
                f"  {icon} {Style.s(f.name, name_style)} "
                f"{Style.s(f'({size_str}, {time_str})', Style.DIM)}"
            )

        if args.latest:
            summaries = sorted(log_dir.glob("summary_*.log"), reverse=True)
            if summaries:
                print(f"\n{'─' * 60}")
                UI.sub_header(f"Latest Summary: {summaries[0].name}")
                print()
                print(summaries[0].read_text())

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    # ── RETRY ─────────────────────────────────────────────────────────────

    def cmd_retry(self, args):
        """Retry failed app installation from the point of failure."""
        UI.header("Retry Installation", UI.GEAR)

        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found in tracking.")
            UI.info("Run 'vpm list' to see tracked apps.")
            return

        if record.status == AppStatus.COMPLETED.value:
            UI.success(f"'{args.app}' is already fully installed.")
            if UI.confirm("Force re-run all steps?"):
                # Reset failed/skipped steps
                for step in record.steps:
                    step.status = StepStatus.PENDING.value
                    step.exit_code = None
                    step.started_at = None
                    step.finished_at = None
                    step.duration_seconds = None
                    step.error_summary = None
                record.status = AppStatus.PENDING.value
                self.lock.set_app(record)
            else:
                return

        # Reset failed and skipped steps to pending
        for step in record.steps:
            if step.status in (StepStatus.FAILED.value, StepStatus.SKIPPED.value):
                step.status = StepStatus.PENDING.value
                step.exit_code = None
                step.error_summary = None

        record.status = AppStatus.IN_PROGRESS.value
        self.lock.set_app(record)

        # Reconstruct ManifestApp from record
        manifest_app = ManifestApp(
            name=record.name,
            steps=[{"label": s.label, "command": s.command} for s in record.steps],
            description="",
        )

        self.executor.execute_app(manifest_app, force=False)

    # ── RESET ─────────────────────────────────────────────────────────────

    def cmd_reset(self, args):
        """Reset tracking for an app."""
        UI.header("Reset App Tracking", UI.BROOM)

        if args.all:
            apps = self.lock.all_apps()
            if not apps:
                UI.info("Nothing to reset.")
                return
            UI.warning(f"This will reset tracking for {len(apps)} app(s).")
            if not UI.confirm("Are you sure?"):
                return
            for name in list(apps.keys()):
                self.lock.remove_app(name)
                UI.success(f"Reset: {name}")
            if args.clean_logs:
                shutil.rmtree(self.config.logs_dir, ignore_errors=True)
                self.config.logs_dir.mkdir(parents=True, exist_ok=True)
                UI.success("Cleaned all logs.")
            return

        if not args.app:
            UI.error("Specify an app name or use --all.")
            return

        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found.")
            return

        UI.warning(f"This will reset all tracking for '{args.app}'.")
        if args.clean_logs and record.log_dir:
            UI.warning(f"Logs will also be deleted: {record.log_dir}")

        if not UI.confirm("Proceed?"):
            return

        if args.clean_logs and record.log_dir:
            shutil.rmtree(record.log_dir, ignore_errors=True)
            UI.success("Logs cleaned.")

        self.lock.remove_app(args.app)
        UI.success(f"Reset tracking for '{args.app}'.")

    # ── SETUP ─────────────────────────────────────────────────────────────

    def cmd_setup(self, args):
        """Install vpm to PATH."""
        UI.header("Setup VPM", UI.LINK)

        script_path = self.config.script_path

        if args.scope == "global":
            target_dir = self.config.bin_dir_global
            needs_sudo = True
        else:
            target_dir = self.config.bin_dir_user
            needs_sudo = False

        target = target_dir / "vpm"

        UI.info(f"Script location: {script_path}")
        UI.info(f"Symlink target: {target}")

        if needs_sudo:
            UI.warning("Global installation requires sudo.")

        if target.exists() or target.is_symlink():
            current = target.resolve() if target.is_symlink() else target
            UI.warning(f"vpm already exists at {target} -> {current}")
            if not UI.confirm("Overwrite?"):
                return

        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            if needs_sudo:
                subprocess.run(
                    ["sudo", "ln", "-sf", str(script_path), str(target)],
                    check=True,
                )
                subprocess.run(
                    ["sudo", "chmod", "+x", str(target)],
                    check=True,
                )
            else:
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(script_path)
                script_path.chmod(0o755)

            UI.success(f"Installed vpm to {target}")

            # Ensure target_dir is in PATH
            if not needs_sudo:
                shell_name = self._detect_shell()
                path_dirs = os.environ.get("PATH", "").split(":")
                if str(target_dir) not in path_dirs:
                    rc_file = self._get_shell_rc(shell_name)
                    if rc_file:
                        line = f'\nexport PATH="$HOME/.local/bin:$PATH"\n'
                        rc_content = rc_file.read_text() if rc_file.exists() else ""
                        if ".local/bin" not in rc_content:
                            with open(rc_file, "a") as f:
                                f.write(line)
                            UI.success(f"Added {target_dir} to PATH in {rc_file}")
                            UI.warning(f"Restart your shell or run: source {rc_file}")
                        else:
                            UI.info(f"{target_dir} already in {rc_file}")
                    else:
                        UI.warning(
                            f"Add to your PATH manually: export PATH=\"{target_dir}:$PATH\""
                        )

        except subprocess.CalledProcessError as e:
            UI.error(f"Failed to create symlink: {e}")
            sys.exit(1)

        # Auto-install completions
        if UI.confirm("Also install shell completions?", default=True):
            self.cmd_completions(argparse.Namespace(shell=None))

    # ── DOCTOR ────────────────────────────────────────────────────────────

    def cmd_doctor(self, args):
        """Diagnose and fix VPM environment."""
        UI.header("VPM Doctor", "🩺")

        checks = [
            ("Python version", self._check_python),
            ("VPM directories", self._check_dirs),
            ("Lock file integrity", self._check_lock),
            ("Shell detection", self._check_shell),
            ("PATH configuration", self._check_path),
            ("Sudo access", self._check_sudo),
            ("Required tools", self._check_tools),
        ]

        issues = []
        for name, check_fn in checks:
            try:
                ok, msg, fix = check_fn()
                if ok:
                    UI.success(f"{name}: {msg}")
                else:
                    UI.error(f"{name}: {msg}")
                    if fix:
                        issues.append((name, msg, fix))
            except Exception as e:
                UI.error(f"{name}: Exception — {e}")

        if issues:
            print()
            UI.sub_header("Suggested Fixes")
            for name, msg, fix in issues:
                print(f"  {Style.s(UI.ARROW, Style.YELLOW)} {name}")
                UI.dim(f"  {fix}")

            if UI.confirm("\nAttempt automatic fixes?"):
                for name, msg, fix in issues:
                    UI.info(f"Fixing: {name}")
                    try:
                        subprocess.run(fix, shell=True, check=True)
                        UI.success(f"Fixed: {name}")
                    except subprocess.CalledProcessError:
                        UI.error(f"Could not fix: {name}")
        else:
            print()
            UI.success("Everything looks good! 🎉")

    def _check_python(self):
        v = sys.version_info
        if v >= (3, 12):
            return True, f"Python {v.major}.{v.minor}.{v.micro}", None
        return False, f"Python {v.major}.{v.minor}.{v.micro} (3.12+ recommended)", \
            "sudo apt-get install -y python3.12 || sudo dnf install -y python3.12"

    def _check_dirs(self):
        dirs = [self.config.config_dir, self.config.data_dir, self.config.logs_dir]
        missing = [d for d in dirs if not d.exists()]
        if not missing:
            return True, "All directories exist", None
        self.config.ensure_dirs()
        return True, "Created missing directories", None

    def _check_lock(self):
        if not self.config.lock_file.exists():
            return True, "No lock file yet (fresh install)", None
        try:
            data = json.loads(self.config.lock_file.read_text())
            app_count = len(data.get("apps", {}))
            return True, f"Valid ({app_count} app(s) tracked)", None
        except json.JSONDecodeError:
            return False, "Corrupted", f"rm {self.config.lock_file}"

    def _check_shell(self):
        shell = self._detect_shell()
        return True, f"Detected: {shell}", None

    def _check_path(self):
        user_bin = str(self.config.bin_dir_user)
        path = os.environ.get("PATH", "")
        if user_bin in path:
            return True, f"{user_bin} in PATH", None
        return False, f"{user_bin} not in PATH", \
            f'echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.{self._detect_shell()}rc'

    def _check_sudo(self):
        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return True, "Passwordless sudo available", None
            return True, "Sudo available (password required)", None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Sudo not available", None

    def _check_tools(self):
        required = ["bash", "curl", "wget", "git"]
        missing = []
        for tool in required:
            if not shutil.which(tool):
                missing.append(tool)
        if not missing:
            return True, f"All present ({', '.join(required)})", None
        return False, f"Missing: {', '.join(missing)}", \
            f"sudo apt-get install -y {' '.join(missing)}"

    # ── COMPLETIONS ───────────────────────────────────────────────────────

    def cmd_completions(self, args):
        """Generate and install shell completions."""
        UI.header("Shell Completions", UI.GEAR)

        target_shell = args.shell or self._detect_shell()
        UI.info(f"Detected shell: {target_shell}")

        generators = {
            "zsh": (Completions.zsh_completion, "_vpm"),
            "bash": (Completions.bash_completion, "vpm.bash"),
            "fish": (Completions.fish_completion, "vpm.fish"),
        }

        if target_shell not in generators:
            UI.warning(f"Unsupported shell: {target_shell}")
            UI.info(f"Supported: {', '.join(generators.keys())}")
            return

        gen_fn, filename = generators[target_shell]
        content = gen_fn()

        # Save to vpm completions dir
        comp_file = self.config.completions_dir / filename
        comp_file.write_text(content)
        comp_file.chmod(0o644)
        UI.success(f"Generated: {comp_file}")

        # Install to shell-specific location
        installed = False
        if target_shell == "zsh":
            # Try multiple approaches for zsh completions
            zsh_dirs = [
                Path.home() / ".zsh" / "completions",
                Path.home() / ".zfunc",
            ]
            # Also try to source from .zshrc
            zshrc = Path.home() / ".zshrc"

            target_dir = zsh_dirs[0]
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            shutil.copy2(comp_file, target)
            target.chmod(0o644)
            UI.success(f"Installed to: {target}")

            # Ensure .zshrc sources it
            if zshrc.exists():
                rc_content = zshrc.read_text()
                fpath_line = f'fpath=({target_dir} $fpath)'
                if str(target_dir) not in rc_content:
                    with open(zshrc, "a") as f:
                        f.write(f"\n# VPM completions\n")
                        f.write(f"{fpath_line}\n")
                        f.write(f"autoload -Uz compinit && compinit\n")
                    UI.success(f"Added fpath to {zshrc}")
                else:
                    UI.info(f"Completion path already in {zshrc}")
            installed = True

        elif target_shell == "bash":
            bash_comp_dir = Path.home() / ".local" / "share" / "bash-completion" / "completions"
            bash_comp_dir.mkdir(parents=True, exist_ok=True)
            target = bash_comp_dir / "vpm"
            shutil.copy2(comp_file, target)
            target.chmod(0o644)
            UI.success(f"Installed to: {target}")

            # Also try system dir if possible
            bashrc = Path.home() / ".bashrc"
            if bashrc.exists():
                rc_content = bashrc.read_text()
                source_line = f"source {comp_file}"
                if str(comp_file) not in rc_content and "vpm" not in rc_content:
                    with open(bashrc, "a") as f:
                        f.write(f"\n# VPM completions\n")
                        f.write(f"[ -f {comp_file} ] && source {comp_file}\n")
                    UI.success(f"Added source to {bashrc}")
            installed = True

        elif target_shell == "fish":
            fish_comp_dir = Path.home() / ".config" / "fish" / "completions"
            fish_comp_dir.mkdir(parents=True, exist_ok=True)
            target = fish_comp_dir / "vpm.fish"
            shutil.copy2(comp_file, target)
            target.chmod(0o644)
            UI.success(f"Installed to: {target}")
            installed = True

        if installed:
            UI.info("Restart your shell or source the config to activate completions.")
        else:
            UI.info(f"Manual setup: source {comp_file}")

    # ── VERSION ───────────────────────────────────────────────────────────

    def cmd_version(self, args):
        """Show version information."""
        UI.banner()
        print()
        UI.info(f"Version:  {__version__}")
        UI.info(f"Python:   {sys.version.split()[0]}")
        UI.info(f"Platform: {platform.platform()}")
        UI.info(f"Config:   {self.config.config_dir}")
        UI.info(f"Data:     {self.config.data_dir}")
        UI.info(f"Logs:     {self.config.logs_dir}")
        UI.info(f"Lock:     {self.config.lock_file}")
        UI.info(f"Script:   {self.config.script_path}")

    # ── HELPERS ───────────────────────────────────────────────────────────

    @staticmethod
    def _detect_shell() -> str:
        """Detect the current user's shell."""
        shell_env = os.environ.get("SHELL", "")
        shell_name = Path(shell_env).name if shell_env else ""

        if shell_name in ("zsh", "bash", "fish"):
            return shell_name

        # Try to detect from /etc/passwd
        try:
            user = pwd.getpwuid(os.getuid())
            login_shell = Path(user.pw_shell).name
            if login_shell in ("zsh", "bash", "fish"):
                return login_shell
        except (KeyError, AttributeError):
            pass

        # Check if zsh or bash is available
        if shutil.which("zsh"):
            return "zsh"
        if shutil.which("bash"):
            return "bash"
        return "bash"

    @classmethod
    def _get_shell_rc(cls, shell: str) -> Path | None:
        """Get the RC file path for a given shell."""
        home = Path.home()
        rc_files = {
            "zsh": home / ".zshrc",
            "bash": home / ".bashrc",
            "fish": home / ".config" / "fish" / "config.fish",
        }
        return rc_files.get(shell)


# ─────────────────────────────────────────────────────────────────────────────
# Self-Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def self_bootstrap():
    """Check Python version and dependencies, offer to fix if needed."""
    v = sys.version_info
    if v < (3, 10):
        print(f"\n⚠  VPM requires Python 3.10+ (you have {v.major}.{v.minor}.{v.micro})")
        print()
        print("To install Python 3.12:")
        print()

        # Detect package manager
        if shutil.which("apt-get"):
            print("  sudo apt-get update && sudo apt-get install -y python3.12")
        elif shutil.which("dnf"):
            print("  sudo dnf install -y python3.12")
        elif shutil.which("yum"):
            print("  sudo yum install -y python3.12")
        elif shutil.which("pacman"):
            print("  sudo pacman -S python")
        elif shutil.which("brew"):
            print("  brew install python@3.12")
        else:
            print("  Please install Python 3.12+ from https://www.python.org/downloads/")

        print()
        print("Then re-run this script with: python3.12 " + " ".join(sys.argv))
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Argument Parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all commands and options."""
    parser = argparse.ArgumentParser(
        prog="vpm",
        description=Style.s(
            "VPM — Virtual Package Manager\n"
            "Robust script orchestration for your VPS",
            Style.BOLD
        ) if Style.enabled() else "VPM — Virtual Package Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              vpm init                          Create manifest template in current directory
              vpm init /path/to/project         Create manifest in specific directory
              vpm install                       Install all apps from manifest
              vpm install --file manifest.yaml  Use specific manifest file
              vpm install docker node_js        Install specific apps only
              vpm install --dry-run             Preview what would be executed
              vpm status                        Show all tracked installations
              vpm status docker                 Show detailed status for docker
              vpm logs docker                   List log files for docker
              vpm logs docker --latest          Show latest summary log
              vpm retry docker                  Retry from failed step
              vpm reset docker                  Reset tracking (allows fresh install)
              vpm reset --all                   Reset everything
              vpm setup --user                  Install vpm to ~/.local/bin
              vpm setup --global                Install vpm to /usr/local/bin (sudo)
              vpm doctor                        Check environment and fix issues
              vpm completions                   Install shell completions
              vpm completions --shell zsh       Install for specific shell
        """),
    )

    parser.add_argument(
        "--no-color", action="store_true",
        help="Disable colored output",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # init
    p_init = subparsers.add_parser(
        "init",
        help="Initialize a new VPM workspace with manifest template",
        description="Create a vpm-manifest.yaml template file with examples and documentation.",
    )
    p_init.add_argument(
        "path", nargs="?", default=None,
        help="Directory to create the manifest in (default: current directory)",
    )
    p_init.add_argument(
        "--force", "-f", action="store_true",
        help="Overwrite existing manifest without prompting",
    )

    # install
    p_install = subparsers.add_parser(
        "install",
        help="Install apps from manifest file",
        description="Execute installation steps for apps defined in a manifest file. "
                     "Tracks progress and supports resume on failure.",
    )
    p_install.add_argument(
        "apps", nargs="*", metavar="APP",
        help="Specific app name(s) to install (default: all)",
    )
    p_install.add_argument(
        "--file", "-f", metavar="FILE",
        help="Path to manifest file (default: auto-discover)",
    )
    p_install.add_argument(
        "--force", action="store_true",
        help="Force reinstallation even if already completed",
    )
    p_install.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be done without executing anything",
    )
    p_install.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip confirmation prompts",
    )

    # status
    p_status = subparsers.add_parser(
        "status",
        help="Show installation status of tracked apps",
    )
    p_status.add_argument(
        "app", nargs="?",
        help="Show detailed status for a specific app",
    )

    # list
    subparsers.add_parser(
        "list",
        help="List all managed apps (alias for status)",
    )

    # logs
    p_logs = subparsers.add_parser(
        "logs",
        help="View logs for an app",
        description="Browse and view execution logs.",
    )
    p_logs.add_argument("app", nargs="?", help="App name")
    p_logs.add_argument(
        "--step", "-s", type=int, metavar="N",
        help="Show log for specific step (0-indexed)",
    )
    p_logs.add_argument(
        "--follow", "-f", action="store_true",
        help="Follow the latest log file (like tail -f)",
    )
    p_logs.add_argument(
        "--latest", "-l", action="store_true",
        help="Display content of the latest summary log",
    )

    # retry
    p_retry = subparsers.add_parser(
        "retry",
        help="Retry failed app installation from point of failure",
    )
    p_retry.add_argument("app", help="App name to retry")

    # reset
    p_reset = subparsers.add_parser(
        "reset",
        help="Reset tracking for an app (allows fresh reinstallation)",
    )
    p_reset.add_argument("app", nargs="?", help="App name to reset")
    p_reset.add_argument(
        "--all", action="store_true",
        help="Reset tracking for all apps",
    )
    p_reset.add_argument(
        "--clean-logs", action="store_true",
        help="Also delete log files",
    )

    # setup
    p_setup = subparsers.add_parser(
        "setup",
        help="Install vpm to PATH for global access",
    )
    scope = p_setup.add_mutually_exclusive_group()
    scope.add_argument(
        "--global", dest="scope", action="store_const", const="global",
        help="Install to /usr/local/bin (requires sudo)",
    )
    scope.add_argument(
        "--user", dest="scope", action="store_const", const="user",
        help="Install to ~/.local/bin (default)",
    )
    p_setup.set_defaults(scope="user")

    # doctor
    subparsers.add_parser(
        "doctor",
        help="Self-diagnose dependencies and fix issues",
    )

    # completions
    p_comp = subparsers.add_parser(
        "completions",
        help="Generate and install shell completions",
    )
    p_comp.add_argument(
        "--shell", choices=["zsh", "bash", "fish"],
        help="Target shell (default: auto-detect)",
    )

    # version
    subparsers.add_parser(
        "version",
        help="Show version and environment information",
    )

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main entry point for VPM."""
    self_bootstrap()

    parser = build_parser()
    args = parser.parse_args()

    if args.no_color:
        Style._force_no_color = True

    if not args.command:
        UI.banner()
        print()
        parser.print_help()
        sys.exit(0)

    try:
        vpm = VPM()

        dispatch = {
            "init": vpm.cmd_init,
            "install": vpm.cmd_install,
            "status": vpm.cmd_status,
            "list": vpm.cmd_list,
            "logs": vpm.cmd_logs,
            "retry": vpm.cmd_retry,
            "reset": vpm.cmd_reset,
            "setup": vpm.cmd_setup,
            "doctor": vpm.cmd_doctor,
            "completions": vpm.cmd_completions,
            "version": vpm.cmd_version,
        }

        handler = dispatch.get(args.command)
        if handler:
            handler(args)
        else:
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        print()
        UI.warning("Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print()
        UI.error(f"Unexpected error: {e}")
        UI.dim(traceback.format_exc())
        UI.info("Run 'vpm doctor' to diagnose issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()
