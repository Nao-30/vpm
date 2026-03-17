"""XDG-compliant path management and configuration."""

import json
import os
import re
from pathlib import Path

from . import __app_name__


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
