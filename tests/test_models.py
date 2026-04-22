"""Tests for data models."""

from vpm.models import StepRecord, AppRecord, StepStatus, AppStatus


class TestStepRecord:
    def test_default_status(self):
        s = StepRecord(index=0, label="test", command="echo hi")
        assert s.status == StepStatus.PENDING.value

    def test_to_dict_roundtrip(self):
        s = StepRecord(
            index=0, label="test", command="echo hi",
            status=StepStatus.SUCCESS.value, exit_code=0,
            rollback_command="echo undo",
        )
        d = s.to_dict()
        s2 = StepRecord.from_dict(d)
        assert s2.label == "test"
        assert s2.status == StepStatus.SUCCESS.value
        assert s2.rollback_command == "echo undo"

    def test_rollback_fields_default_none(self):
        s = StepRecord(index=0, label="test", command="echo hi")
        assert s.rollback_command is None
        assert s.rollback_status is None
        assert s.rollback_log_file is None


class TestAppRecord:
    def test_recalculate_completed(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.SUCCESS.value),
            StepRecord(index=1, label="b", command="b", status=StepStatus.SUCCESS.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.COMPLETED.value
        assert r.completed_steps == 2
        assert r.failed_steps == 0

    def test_recalculate_partial(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.SUCCESS.value),
            StepRecord(index=1, label="b", command="b", status=StepStatus.FAILED.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.PARTIAL.value

    def test_recalculate_failed(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.FAILED.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.FAILED.value

    def test_recalculate_pending(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.PENDING.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.PENDING.value

    def test_to_dict_roundtrip(self):
        steps = [StepRecord(index=0, label="a", command="a")]
        r = AppRecord(name="test", display_name="test (Test)", steps=steps, requires=["dep"])
        d = r.to_dict()
        r2 = AppRecord.from_dict(d)
        assert r2.name == "test"
        assert r2.requires == ["dep"]
        assert len(r2.steps) == 1

    def test_rolled_back_status_exists(self):
        assert AppStatus.ROLLED_BACK.value == "rolled_back"
