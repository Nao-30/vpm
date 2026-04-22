"""Integration tests — run real VPM commands against test manifests."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = str(Path(__file__).resolve().parent.parent)
VPM = [sys.executable, "-m", "vpm"]


def _env(tmp_path):
    """Build env with XDG dirs pointing to tmp and PYTHONPATH set."""
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["PYTHONPATH"] = REPO_ROOT
    env["NO_COLOR"] = "1"
    return env


def run_vpm(*args, env=None, cwd=None):
    """Run vpm. Uses pipe for stdout but allows PTY to fall back to non-PTY."""
    result = subprocess.run(
        [*VPM, "--no-color", *args],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=30, env=env, cwd=cwd,
    )
    return result.returncode, result.stdout


@pytest.fixture
def workspace(tmp_path):
    """Create a temp workspace with a simple manifest."""
    marker = tmp_path / "marker.txt"
    manifest = tmp_path / "vpm-manifest.yaml"
    manifest.write_text(
        f"[test_app] Integration test\n"
        f"- label: Create marker file\n"
        f"  run: touch {marker}\n"
        f"  rollback: rm -f {marker}\n"
        f"\n"
        f"- label: Verify\n"
        f"  run: test -f {marker}\n"
    )
    return tmp_path, _env(tmp_path)


class TestInstall:
    def test_install_creates_lock_file(self, workspace):
        ws, env = workspace
        rc, out = run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        assert rc == 0, f"Install failed:\n{out}"
        lock = ws / "data" / "vpm" / "vpm-lock.json"
        assert lock.exists(), f"Lock file not created. Output:\n{out}"
        data = json.loads(lock.read_text())
        assert "test_app" in data["apps"]

    def test_install_runs_commands(self, workspace):
        ws, env = workspace
        rc, out = run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        assert rc == 0, f"Install failed:\n{out}"
        assert (ws / "marker.txt").exists(), "marker.txt not created"

    def test_install_tracks_step_status(self, workspace):
        ws, env = workspace
        run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        lock = ws / "data" / "vpm" / "vpm-lock.json"
        data = json.loads(lock.read_text())
        app = data["apps"]["test_app"]
        assert app["status"] == "completed"
        for step in app["steps"]:
            assert step["status"] == "success"
            assert step["exit_code"] == 0

    def test_install_dry_run_no_side_effects(self, workspace):
        ws, env = workspace
        rc, out = run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--dry-run", "--skip-security", env=env, cwd=str(ws))
        assert rc == 0, f"Dry run failed:\n{out}"
        assert not (ws / "marker.txt").exists()

    def test_install_resumes(self, workspace):
        ws, env = workspace
        run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        rc, out = run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        assert rc == 0, f"Resume failed:\n{out}"


class TestAudit:
    def test_audit_clean_manifest(self, workspace):
        ws, env = workspace
        rc, out = run_vpm("audit", "--file", str(ws / "vpm-manifest.yaml"), env=env)
        assert rc == 0

    def test_audit_detects_risky_commands(self, tmp_path):
        manifest = tmp_path / "risky.yaml"
        manifest.write_text(
            "[risky] Risky app\n"
            "- label: Danger\n"
            "  run: rm -rf /\n"
        )
        env = _env(tmp_path)
        rc, out = run_vpm("audit", "--file", str(manifest), env=env)
        assert rc != 0, f"Should have blocked critical finding:\n{out}"
        assert "CRITICAL" in out


class TestRollback:
    def test_rollback_dry_run(self, workspace):
        ws, env = workspace
        rc, out = run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        assert rc == 0, f"Install failed:\n{out}"
        rc, out = run_vpm("rollback", "test_app", "--dry-run", env=env, cwd=str(ws))
        assert rc == 0, f"Rollback dry-run failed:\n{out}"
        assert "ROLLBACK" in out
        assert (ws / "marker.txt").exists(), "Dry run should not delete files"


class TestStatus:
    def test_status_after_install(self, workspace):
        ws, env = workspace
        run_vpm("install", "--file", str(ws / "vpm-manifest.yaml"), "--yes", "--skip-security", env=env, cwd=str(ws))
        rc, out = run_vpm("status", env=env)
        assert rc == 0
        assert "test_app" in out

    def test_status_empty(self, tmp_path):
        env = _env(tmp_path)
        rc, out = run_vpm("status", env=env)
        assert rc == 0


class TestDoctor:
    def test_doctor_runs(self):
        rc, out = run_vpm("doctor")
        assert rc == 0


class TestVersion:
    def test_version_output(self):
        rc, out = run_vpm("version")
        assert rc == 0
        assert "1.1.0" in out
