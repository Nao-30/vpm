"""Tests for dependency resolution."""

import pytest
from unittest.mock import MagicMock
from vpm.executor import Executor
from vpm.manifest import ManifestApp
from vpm.config import Config
from vpm.lockfile import LockFile
from vpm.models import AppRecord, AppStatus


def make_executor():
    config = MagicMock(spec=Config)
    lock = MagicMock(spec=LockFile)
    lock.get_app.return_value = None
    return Executor(config, lock), lock


class TestResolveOrder:
    def test_no_dependencies(self):
        executor, lock = make_executor()
        apps = [
            ManifestApp("a", [{"label": "a", "command": "a"}]),
            ManifestApp("b", [{"label": "b", "command": "b"}]),
        ]
        order = executor.resolve_order(apps, lock)
        names = [a.name for a in order]
        assert set(names) == {"a", "b"}

    def test_simple_dependency(self):
        executor, lock = make_executor()
        apps = [
            ManifestApp("child", [{"label": "c", "command": "c"}], requires=["parent"]),
            ManifestApp("parent", [{"label": "p", "command": "p"}]),
        ]
        order = executor.resolve_order(apps, lock)
        names = [a.name for a in order]
        assert names.index("parent") < names.index("child")

    def test_chain_dependency(self):
        executor, lock = make_executor()
        apps = [
            ManifestApp("c", [{"label": "c", "command": "c"}], requires=["b"]),
            ManifestApp("b", [{"label": "b", "command": "b"}], requires=["a"]),
            ManifestApp("a", [{"label": "a", "command": "a"}]),
        ]
        order = executor.resolve_order(apps, lock)
        names = [a.name for a in order]
        assert names.index("a") < names.index("b") < names.index("c")

    def test_circular_dependency_raises(self):
        executor, lock = make_executor()
        apps = [
            ManifestApp("a", [{"label": "a", "command": "a"}], requires=["b"]),
            ManifestApp("b", [{"label": "b", "command": "b"}], requires=["a"]),
        ]
        with pytest.raises(ValueError, match="Circular dependency"):
            executor.resolve_order(apps, lock)

    def test_missing_dependency_raises(self):
        executor, lock = make_executor()
        apps = [
            ManifestApp("child", [{"label": "c", "command": "c"}], requires=["nonexistent"]),
        ]
        with pytest.raises(ValueError, match="not in the manifest"):
            executor.resolve_order(apps, lock)

    def test_external_dependency_satisfied(self):
        executor, lock = make_executor()
        record = MagicMock(spec=AppRecord)
        record.status = AppStatus.COMPLETED.value
        lock.get_app.return_value = record

        apps = [
            ManifestApp("child", [{"label": "c", "command": "c"}], requires=["external"]),
        ]
        order = executor.resolve_order(apps, lock)
        assert len(order) == 1
        assert order[0].name == "child"

    def test_diamond_dependency(self):
        executor, lock = make_executor()
        apps = [
            ManifestApp("d", [{"label": "d", "command": "d"}], requires=["b", "c"]),
            ManifestApp("c", [{"label": "c", "command": "c"}], requires=["a"]),
            ManifestApp("b", [{"label": "b", "command": "b"}], requires=["a"]),
            ManifestApp("a", [{"label": "a", "command": "a"}]),
        ]
        order = executor.resolve_order(apps, lock)
        names = [a.name for a in order]
        assert names.index("a") < names.index("b")
        assert names.index("a") < names.index("c")
        assert names.index("b") < names.index("d")
        assert names.index("c") < names.index("d")
