# Execution Model & Configuration

## Execution Model

### PTY-Based Execution

VPM uses pseudo-terminal (PTY) execution rather than simple `subprocess.PIPE`. This means:

- The child process sees a real terminal (as if you typed the command yourself).
- Interactive programs work: `debconf` configuration screens, `ncurses` dialogs, `sudo` password prompts, `less`/`more` pagers, progress bars, colored output.
- Your keystrokes (arrows, tab, enter) are forwarded to the child process.
- All output is simultaneously displayed in your terminal AND written to the log file.

### Interactive Programs

These all work correctly during VPM execution:

- `sudo` password prompts
- `dpkg-reconfigure` dialogs
- `debconf` package configuration screens (e.g., postfix, tzdata)
- `ncurses`-based installers
- `mysql_secure_installation`
- Any program that needs a TTY

### Environment Variables

- VPM inherits the current user's full environment.
- `DEBIAN_FRONTEND` is **not** forced — interactive package configuration works. If you want unattended mode, set it yourself: `export DEBIAN_FRONTEND=noninteractive` before running vpm, or include it in your step command.
- `SHELL` is detected from the environment.
- `$USER`, `$HOME`, `$PATH` — all available as normal.

### Shell Selection

Commands are executed with:
```
$SHELL -e -c "your command here"
```

- If `$SHELL` is `bash` or `zsh`, it's used directly.
- Otherwise, falls back to `/bin/bash`.
- The `-e` flag means **exit on first error** — in a multi-line command block, if any line returns non-zero, the entire step fails immediately.

### Error Handling

- **Non-zero exit code**: Step is marked `failed`, remaining steps in that app are `skipped`.
- **OS error** (command not found, permission denied): Step is marked `failed` with the error message captured.
- **SIGINT (Ctrl+C)**: Current step is allowed to finish, then remaining steps are marked `skipped`. Terminal is restored.
- **SIGTERM**: Same as SIGINT.
- **SSH disconnect**: The `running` step in the lock file will be re-executed on next run.

---

## File Locations

| Path | Purpose |
|---|---|
| `~/.config/vpm/` | Configuration directory (XDG_CONFIG_HOME) |
| `~/.config/vpm/config.json` | User configuration (future use) |
| `~/.config/vpm/completions/` | Generated shell completion files |
| `~/.local/share/vpm/` | Data directory (XDG_DATA_HOME) |
| `~/.local/share/vpm/vpm-lock.json` | Installation state tracking |
| `~/.local/share/vpm/logs/` | All execution logs |
| `~/.local/share/vpm/logs/<app>/` | Per-app log directory |
| `~/.local/bin/vpm` | User-scoped symlink (after `vpm setup --user`) |
| `/usr/local/bin/vpm` | Global symlink (after `vpm setup --global`) |

All paths respect `XDG_CONFIG_HOME` and `XDG_DATA_HOME` environment variables if set.

---

## Shell Completions

### Supported Shells

| Shell | Completion File | Install Location |
|---|---|---|
| **zsh** | `_vpm` | `~/.zsh/completions/_vpm` + fpath in `.zshrc` |
| **bash** | `vpm.bash` | `~/.local/share/bash-completion/completions/vpm` + source in `.bashrc` |
| **fish** | `vpm.fish` | `~/.config/fish/completions/vpm.fish` |

### What Gets Completed

- All commands: `init`, `install`, `status`, `list`, `logs`, `retry`, `reset`, `setup`, `doctor`, `completions`, `version`, `help`
- Command-specific flags: `--file`, `--force`, `--dry-run`, `--yes`, `--global`, `--user`, `--shell`, `--all`, `--clean-logs`, `--step`, `--follow`, `--latest`
- **Dynamic app names**: For `logs`, `retry`, `reset`, `status` — reads from the lock file to suggest installed app names.
- File paths for `--file` flag.
- Directory paths for `init` command.

---
