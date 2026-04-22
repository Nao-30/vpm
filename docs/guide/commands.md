# Commands Reference

## Commands Reference

### vpm init

Create a manifest template file with documentation and examples.

```bash
vpm init                    # Creates vpm-manifest.yaml in current directory
vpm init /path/to/project   # Creates in specified directory
vpm init --force            # Overwrite existing manifest without asking
```

**Output**: A `vpm-manifest.yaml` file pre-filled with commented examples.

### vpm install

Execute installation steps from a manifest file.

```bash
vpm install                           # Auto-discover manifest, install all apps
vpm install --file mysetup.yaml       # Use specific manifest file
vpm install docker node_js            # Install only specific apps
vpm install --file setup.yaml docker  # Specific file + specific apps
vpm install --dry-run                 # Preview without executing
vpm install --force                   # Reinstall even if already completed
vpm install --yes                     # Skip confirmation prompts
vpm install -f setup.yaml -y         # Combined short flags
```

**Manifest auto-discovery order** (when `--file` is not specified):
1. `./vpm-manifest.yaml`
2. `./vpm-manifest.yml`
3. `./.vpm-manifest.yaml`
4. `~/.config/vpm/manifest.yaml`

**Behavior**:
- Resolves dependencies and computes installation order.
- Skips already-completed steps (resume support).
- Stops remaining steps in an app if one fails.
- Skips dependent apps if their requirements failed.
- Shows real-time progress with step counters and progress bar.

### vpm status

Show installation status of tracked apps.

```bash
vpm status          # Table of all tracked apps
vpm status docker   # Detailed view for a specific app (shows each step)
```

### vpm list

Alias for `vpm status` (shows the summary table).

```bash
vpm list
```

### vpm logs

Browse and view execution logs.

```bash
vpm logs                  # List all app log directories with file counts
vpm logs docker           # List all log files for docker
vpm logs docker --latest  # Show contents of the latest summary log
vpm logs docker --step 0  # Show log for step 0 (first step)
vpm logs docker --step 2  # Show log for step 2 (third step)
vpm logs docker --follow  # Tail -f the latest summary log
```

### vpm retry

Resume a failed or partially completed installation.

```bash
vpm retry docker
```

**Behavior**:
- Resets `failed` and `skipped` steps to `pending`.
- Keeps `success` steps as-is (they won't re-run).
- Starts execution from the first non-completed step.

### vpm reset

Clear tracking state for an app, allowing fresh reinstallation.

```bash
vpm reset docker              # Reset tracking for docker
vpm reset docker --clean-logs # Also delete all log files for docker
vpm reset --all               # Reset tracking for everything
vpm reset --all --clean-logs  # Nuclear option: reset everything + delete all logs
```

**Note**: Reset does not undo any system changes made by previous commands. It only clears VPM's tracking data.

### vpm setup

Install the `vpm` command to your PATH.

```bash
vpm setup --user     # Symlink to ~/.local/bin/vpm (default, no sudo needed)
vpm setup --global   # Symlink to /usr/local/bin/vpm (requires sudo)
```

Also offers to install shell completions automatically.

### vpm doctor

Diagnose the VPM environment and suggest fixes.

```bash
vpm doctor
```

**Checks performed**:
- Python version (3.10+ required, 3.12+ recommended)
- VPM directory structure
- Lock file integrity
- Shell detection
- PATH configuration
- Sudo access
- Required system tools (bash, curl, wget, git)

Can attempt automatic fixes when issues are found.

### vpm completions

Generate and install tab-completion for your shell.

```bash
vpm completions              # Auto-detect shell and install
vpm completions --shell zsh  # Force specific shell
vpm completions --shell bash
vpm completions --shell fish
```

**Supported shells**: zsh, bash, fish

Completions include:
- All commands and subcommands
- Command-specific flags and options
- Dynamic app name completion (reads from lock file)
- File path completion where appropriate

### vpm version

Show version and environment information.

```bash
vpm version
```

---
