"""Atomic JSON lock file for tracking installation state."""

import datetime
import json
import os
import platform
import shutil

from . import __version__
from .config import Config
from .models import AppRecord
from .ui import UI


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
