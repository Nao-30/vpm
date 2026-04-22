# Troubleshooting & Architecture

## Troubleshooting

### "App already installed" but something is wrong

```bash
# Reset tracking and reinstall
vpm reset my_app
vpm install my_app
```

### SSH disconnected during install

```bash
# Just run install again — it resumes automatically
vpm install
```

### Want to see what failed

```bash
# Quick status
vpm status my_app

# View the latest summary
vpm logs my_app --latest

# View a specific step's full output
vpm logs my_app --step 3
```

### Terminal is garbled after interrupted command

This shouldn't happen (VPM restores terminal settings), but if it does:

```bash
reset
# or
stty sane
```

### Lock file corrupted

VPM auto-detects corruption, creates a backup, and starts fresh. You can also:

```bash
# Nuclear reset
vpm reset --all --clean-logs
```

### Need completely unattended installation

Set `DEBIAN_FRONTEND` in your manifest steps:

```
- label: Install package non-interactively
  run: |
    export DEBIAN_FRONTEND=noninteractive
    sudo apt-get install -y postfix
```

Or set it globally before running VPM:
```bash
export DEBIAN_FRONTEND=noninteractive
vpm install --yes
```

---

## Architecture

```
vpm/                    — Python package
├── style.py           — ANSI color/formatting with terminal detection
├── ui.py              — Rich terminal components (headers, tables, progress bars, prompts)
├── config.py          — XDG-compliant path management
├── models.py          — StepRecord, AppRecord, StepStatus, AppStatus dataclasses
├── lockfile.py        — Atomic JSON state persistence
├── manifest.py        — Custom format parser (no YAML dependency) + ManifestApp
├── scanner.py         — Security scanning: static analysis and URL checking
├── executor.py        — PTY-based command execution with logging + rollback
├── completions.py     — Shell completion generators (zsh, bash, fish)
├── app.py             — Main application with all command handlers
└── cli.py             — Argument parsing, dispatch, and bootstrap
```

**Key design decisions**:

| Decision | Rationale |
|---|---|
| Modular package | Clean separation of concerns, testable components |
| No pip dependencies | Nothing to install, no virtual environment needed |
| Custom manifest format | Avoids PyYAML dependency while being human-readable |
| PTY execution | Full interactive support (debconf, ncurses, sudo prompts) |
| Atomic lock file writes | Write to `.tmp` + `rename()` prevents corruption |
| XDG Base Directory spec | Config in `~/.config/vpm/`, data in `~/.local/share/vpm/` |
| SHA-256 command hashing | Detects manifest changes without re-executing |
| Topological sort | Dependency resolution with cycle detection |
| Per-step tracking | Granular resume — skip only what succeeded |

---

*VPM v1.1.0 — Built for humans who manage servers, and the AI agents who help them.*
