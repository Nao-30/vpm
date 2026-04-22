# How It Works

## How Tracking Works

### The Lock File

All state is persisted in `~/.local/share/vpm/vpm-lock.json`. This JSON file contains:

```json
{
  "_meta": {
    "version": "1.0.0",
    "updated_at": "2024-01-15T10:30:00",
    "user": "deploy",
    "hostname": "my-vps"
  },
  "apps": {
    "docker": {
      "name": "docker",
      "display_name": "docker (Docker Engine)",
      "status": "completed",
      "requires": ["system_base"],
      "steps": [
        {
          "index": 0,
          "label": "Install prerequisites",
          "command": "sudo apt-get install -y ...",
          "status": "success",
          "exit_code": 0,
          "started_at": "2024-01-15T10:30:00",
          "finished_at": "2024-01-15T10:30:05",
          "duration_seconds": 5.2,
          "log_file": "/home/user/.local/share/vpm/logs/docker/step_000_...",
          "command_hash": "a1b2c3d4e5f6"
        }
      ],
      "total_steps": 5,
      "completed_steps": 5,
      "failed_steps": 0
    }
  }
}
```

### Step States

| State | Meaning |
|---|---|
| `pending` | Not yet executed |
| `running` | Currently executing (set before command starts) |
| `success` | Completed with exit code 0 |
| `failed` | Completed with non-zero exit code |
| `skipped` | Skipped because a previous step failed, a dependency failed, or execution was interrupted |

### App States

| State | Meaning |
|---|---|
| `pending` | No steps have been executed |
| `in_progress` | Currently being installed |
| `completed` | All steps finished successfully |
| `partial` | Some steps succeeded, some failed |
| `failed` | One or more steps failed, none succeeded (or dependency failed) |

### Crash Recovery

If VPM is interrupted (SSH disconnect, `Ctrl+C`, system crash, kill signal):

1. The lock file already has the current step marked as `running`.
2. On next `vpm install`, VPM reads the lock file.
3. Steps marked `success` are skipped.
4. The `running` step (which was interrupted) is treated as needing re-execution.
5. Execution resumes from that point.

The lock file is written atomically (write to `.tmp`, then `rename()`) so it cannot be corrupted by a crash mid-write.

### Change Detection

Each step's command is SHA-256 hashed and stored in the lock file. If you modify a command in the manifest and re-run `vpm install`:

- VPM detects the hash mismatch.
- It warns you that the manifest has changed.
- It asks whether to re-run with the updated steps.

---

## Dependency System

### How Dependencies Resolve

Given this manifest:

```
[base]
- run: apt-get update

[docker]
requires: base

[app]
requires: docker, base
```

VPM performs a topological sort:
1. `base` (no dependencies)
2. `docker` (depends on `base`)
3. `app` (depends on `docker` and `base`)

If `docker` fails, `app` is automatically skipped with a clear message:
```
✖ Skipping 'app': dependency 'docker' is not successfully installed.
```

### Cross-Manifest Dependencies

If App B in today's manifest requires App A that was installed last week from a different manifest:

- VPM checks the lock file for App A's status.
- If App A shows `completed` in the lock file, the dependency is satisfied.
- If App A is not found or not completed, VPM reports the missing dependency.

### Circular Dependency Detection

```
[a]
requires: b

[b]
requires: a
```

VPM detects this and exits with:
```
✖ Dependency error: Circular dependency detected involving: a, b
```

---

## Logging

### Directory Structure

```
~/.local/share/vpm/
├── vpm-lock.json                          # State tracking
└── logs/
    ├── system_base/
    │   ├── summary_20240115_103000.log    # Overall run summary
    │   ├── step_000_update_packages_103000.log
    │   ├── step_001_install_tools_103012.log
    │   └── step_002_set_timezone_103045.log
    ├── docker/
    │   ├── summary_20240115_103100.log
    │   ├── step_000_install_prereqs_103100.log
    │   ├── step_001_add_gpg_key_103108.log
    │   └── ...
    └── app_deployment/
        └── ...
```

### Summary Logs

Each `vpm install` run for an app creates a summary log:

```
VPM Installation Summary
============================================================
App: docker (Docker Engine)
Started: 2024-01-15T10:31:00
User: deploy
Host: my-vps
Total Steps: 5
============================================================

[OK] Step 1: Install prerequisites (exit=0, 5.2s)
[OK] Step 2: Add Docker GPG key (exit=0, 2.1s)
[OK] Step 3: Add Docker repository (exit=0, 0.8s)
[OK] Step 4: Install Docker Engine (exit=0, 45.3s)
[FAIL] Step 5: Verify installation (exit=1, 0.5s)
  Error: Cannot connect to the Docker daemon

============================================================
Finished: 2024-01-15T10:31:54
Duration: 53.9s
Status: partial
Steps: 4/5 succeeded, 1 failed
============================================================
```

### Step Logs

Each step gets its own log file with full command output:

```
VPM Step Execution Log
────────────────────────────────────────────────────────────
Step: 4 — Install Docker Engine
Started: 2024-01-15T10:31:08
Command:
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli ...
────────────────────────────────────────────────────────────

Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease
Get:2 http://archive.ubuntu.com/ubuntu jammy-updates InRelease [119 kB]
...
Setting up docker-ce (5:24.0.7-1~ubuntu.22.04~jammy) ...
Created symlink /etc/systemd/system/multi-user.target.wants/docker.service

────────────────────────────────────────────────────────────
Exit Code: 0
Duration: 45.3s
Finished: 2024-01-15T10:31:53
```

---
