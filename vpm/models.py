"""Data models for step and app tracking."""

import enum
from dataclasses import asdict, dataclass, field


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
