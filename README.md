# VPM — Virtual Package Manager

> Robust script orchestration for VPS environments.
> Track, execute, resume, and manage multi-step installation workflows with full logging and dependency resolution.

---

## Table of Contents

- [What is VPM?](#what-is-vpm)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [The Manifest File](#the-manifest-file)
  - [Structure Overview](#structure-overview)
  - [App Header](#app-header)
  - [Dependencies](#dependencies)
  - [Steps](#steps)
  - [Multi-line Commands](#multi-line-commands)
  - [Comments](#comments)
  - [Complete Manifest Example](#complete-manifest-example)
- [Commands Reference](#commands-reference)
  - [vpm init](#vpm-init)
  - [vpm install](#vpm-install)
  - [vpm status](#vpm-status)
  - [vpm list](#vpm-list)
  - [vpm logs](#vpm-logs)
  - [vpm retry](#vpm-retry)
  - [vpm reset](#vpm-reset)
  - [vpm setup](#vpm-setup)
  - [vpm doctor](#vpm-doctor)
  - [vpm completions](#vpm-completions)
  - [vpm version](#vpm-version)
- [How Tracking Works](#how-tracking-works)
  - [The Lock File](#the-lock-file)
  - [Step States](#step-states)
  - [App States](#app-states)
  - [Crash Recovery](#crash-recovery)
  - [Change Detection](#change-detection)
- [Dependency System](#dependency-system)
  - [How Dependencies Resolve](#how-dependencies-resolve)
  - [Cross-Manifest Dependencies](#cross-manifest-dependencies)
  - [Circular Dependency Detection](#circular-dependency-detection)
- [Logging](#logging)
  - [Directory Structure](#directory-structure)
  - [Summary Logs](#summary-logs)
  - [Step Logs](#step-logs)
- [Execution Model](#execution-model)
  - [PTY-Based Execution](#pty-based-execution)
  - [Interactive Programs](#interactive-programs)
  - [Environment Variables](#environment-variables)
  - [Shell Selection](#shell-selection)
  - [Error Handling](#error-handling)
- [File Locations](#file-locations)
- [Shell Completions](#shell-completions)
- [Writing Manifests — Guidelines for AI Agents](#writing-manifests--guidelines-for-ai-agents)
  - [Rules](#rules)
  - [Best Practices](#best-practices)
  - [Common Patterns](#common-patterns)
  - [Anti-Patterns](#anti-patterns)
  - [Template for AI Agents](#template-for-ai-agents)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)

---

## What is VPM?

VPM is a single-file Python script that acts as an orchestrator for shell commands on a VPS. Think of it as a declarative way to define "install app X by running commands 1, 2, 3" with:

- **Tracking**: Every step is recorded. If your SSH drops mid-install, reconnect and run `vpm install` again — it picks up where it left off.
- **Dependencies**: App B can declare it requires App A. VPM resolves the order and skips dependent apps if their requirements failed.
- **Full Logging**: Every command's stdout/stderr is captured to timestamped log files while still showing output in your terminal.
- **Interactive Support**: Uses PTY execution so `debconf`, `ncurses` menus, `sudo` password prompts, and any interactive program works normally.
- **No External Dependencies**: Pure Python 3.10+ standard library. No pip packages required.

VPM does **not** replace apt, dnf, or any package manager. It orchestrates arbitrary shell commands and tracks their success/failure state.

---

## Quick Start

```bash
# Save vpm.py somewhere permanent
mkdir -p ~/.local/share/vpm
cp vpm.py ~/.local/share/vpm/vpm.py
chmod +x ~/.local/share/vpm/vpm.py

# Install to PATH
python3 ~/.local/share/vpm/vpm.py setup --user

# Restart shell or source profile
source ~/.zshrc  # or ~/.bashrc

# Create a project
mkdir ~/server-setup && cd ~/server-setup
vpm init

# Edit the manifest
nano vpm-manifest.yaml

# Preview what will run
vpm install --dry-run

# Execute
vpm install

# Check status anytime
vpm status
```

---

## Installation

### Requirements

- Python 3.10 or higher (3.12+ recommended)
- Linux or macOS (PTY support required)
- `bash` or `zsh` available on the system

### Install Steps

```bash
# 1. Download or copy vpm.py to a permanent location
mkdir -p ~/.local/share/vpm
cp vpm.py ~/.local/share/vpm/vpm.py

# 2. Install the `vpm` command (symlinks to ~/.local/bin/vpm)
python3 ~/.local/share/vpm/vpm.py setup --user

# 3. Install shell completions (auto-detects your shell)
vpm completions

# 4. Verify
vpm doctor
vpm version
```

#### Global Installation (all users)

```bash
sudo python3 vpm.py setup --global
# Installs to /usr/local/bin/vpm
```

#### If Python 3.10+ Is Not Available

```bash
# Run vpm — it will detect the issue and suggest the right command:
python3 vpm.py doctor

# Typical fix for Ubuntu/Debian:
sudo apt-get update && sudo apt-get install -y python3.12

# For RHEL/CentOS/Fedora:
sudo dnf install -y python3.12
```

---

## The Manifest File

The manifest file (`vpm-manifest.yaml`) is where you define what to install and how. It uses a simple, human-readable format that does **not** require a YAML parser — VPM parses it with its own lightweight parser.

### Structure Overview

```
# Comments start with #

[app_name] Optional human-readable description
requires: dependency1, dependency2

- label: What this step does
  run: shell command to execute

- label: Another step
  run: |
    multi-line
    shell command

- run: simple command without explicit label
```

### App Header

An app is defined by a header line enclosed in square brackets:

```
[my_app] This is my application
```

- `my_app` — The app identifier. Used in commands like `vpm install my_app`, `vpm retry my_app`, etc.
- Everything after `]` is an optional description shown in status output.
- App names are normalized internally: lowercased, special characters replaced with `_`.
- App names must be unique within a manifest.

### Dependencies

Declared on a line after the app header, before any steps:

```
[web_server] Nginx + Certbot
requires: base_packages, firewall_setup
```

- Comma-separated list of app names.
- Dependencies must either be defined in the same manifest or already successfully installed from a previous run.
- VPM topologically sorts apps so dependencies always execute first.
- If a dependency fails, all apps that depend on it are automatically skipped.

### Steps

Each step is a shell command to execute:

```
- label: Install Nginx
  run: sudo apt-get install -y nginx
```

- `label` — Human-readable name shown in terminal output and logs. If omitted, auto-generated from the command.
- `run` — The shell command to execute. Runs with `bash -e` (exits on first error).
- Steps execute in order within an app.
- If a step fails (non-zero exit code), all subsequent steps in that app are skipped.
- On re-run, successfully completed steps are skipped automatically.

#### Shorthand (no label)

```
- sudo apt-get install -y nginx
```

When only a command is provided without `label:` or `run:` keys, VPM treats the entire line after `- ` as the command and auto-generates a label from it.

### Multi-line Commands

Use the pipe `|` character after `run:` to start a multi-line block:

```
- label: Configure firewall
  run: |
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw allow http
    sudo ufw allow https
    sudo ufw --force enable
```

- All indented lines following `run: |` are joined with newlines.
- The block ends when a line at the same or lesser indentation level appears (or at end of file).
- The entire block runs as a single `bash -e` invocation — if any line fails, execution stops.

#### Line Continuation

For long single commands, use backslash continuation inside multi-line blocks:

```
- label: Add Docker repository
  run: |
    echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### Comments

Lines starting with `#` are ignored everywhere:

```
# This entire app is disabled for now
# [experimental_stuff]
# - run: something risky

[active_app]
# This step is temporarily skipped
# - run: do something optional
- run: do something important
```

### Complete Manifest Example

```
# ═══════════════════════════════════════════════════════
# Server Setup Manifest
# ═══════════════════════════════════════════════════════

[system_base] Core system packages and configuration
- label: Update package lists
  run: sudo apt-get update -y

- label: Upgrade existing packages
  run: sudo apt-get upgrade -y

- label: Install essential tools
  run: |
    sudo apt-get install -y \
      curl wget git htop vim unzip jq tree \
      net-tools dnsutils mtr-tiny \
      build-essential software-properties-common

- label: Set timezone
  run: sudo timedatectl set-timezone UTC

- label: Configure automatic security updates
  run: |
    sudo apt-get install -y unattended-upgrades
    sudo dpkg-reconfigure -plow unattended-upgrades

[firewall] UFW Firewall Configuration
requires: system_base

- label: Install UFW
  run: sudo apt-get install -y ufw

- label: Configure firewall rules
  run: |
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw --force enable

- label: Verify firewall status
  run: sudo ufw status verbose

[docker] Docker Engine
requires: system_base

- label: Install prerequisites
  run: sudo apt-get install -y ca-certificates curl gnupg lsb-release

- label: Add Docker GPG key and repository
  run: |
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

- label: Install Docker Engine
  run: |
    sudo apt-get update -y
    sudo apt-get install -y \
      docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin

- label: Add current user to docker group
  run: sudo usermod -aG docker $USER

- label: Verify installation
  run: sudo docker run --rm hello-world

[app_deployment] Deploy Application Stack
requires: docker, firewall

- label: Create application directory
  run: mkdir -p ~/apps/myapp

- label: Clone repository
  run: git clone https://github.com/example/myapp.git ~/apps/myapp

- label: Start services
  run: |
    cd ~/apps/myapp
    docker compose up -d

- label: Verify services are running
  run: docker compose -f ~/apps/myapp/docker-compose.yml ps
```

---

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

## Writing Manifests — Guidelines for AI Agents

This section is specifically for AI assistants generating VPM manifest files. Follow these rules precisely.

### Rules

1. **Format**: Use the VPM manifest format (described above), NOT standard YAML.
   - App headers use `[square_brackets]`
   - Steps start with `- `
   - Multi-line commands use `run: |` followed by indented lines
   - No YAML anchors, no YAML lists with `- key: value` nesting beyond what's described

2. **App names**: Use `snake_case` identifiers. No spaces, no special characters.
   - Good: `[docker_engine]`, `[node_js]`, `[my_web_app]`
   - Bad: `[Docker Engine]`, `[my-web-app]`, `[MyWebApp]`

3. **Every step must have a descriptive `label`**. Do not rely on auto-generated labels.

4. **Each step should be idempotent when possible**. If a step runs twice, it should not break things.
   - Use `apt-get install -y` (the `-y` and the fact that apt skips already-installed packages makes it idempotent)
   - Use `mkdir -p` instead of `mkdir`
   - Use `gpg --dearmor -o ... --yes` to overwrite existing files
   - Use `ln -sf` instead of `ln -s`
   - Check before creating: `id -u username &>/dev/null || useradd username`

5. **Group related commands into logical steps**. Don't make every single command its own step, but don't put 50 commands in one step either.
   - Good: "Install Docker prerequisites" (one step with 3 apt packages)
   - Bad: Separate steps for each `apt-get install` of related packages
   - Bad: One giant step that does everything

6. **Use `requires:` for dependencies between apps**. If App B needs something App A installs, declare it.

7. **Never use `cd` as a separate step**. It runs in a subshell and won't persist. Use it within a multi-line block:
   ```
   - label: Build the project
     run: |
       cd /path/to/project
       make build
       make install
   ```

8. **Use `sudo` explicitly** where needed. VPM runs as the current user.

9. **Do not set `DEBIAN_FRONTEND=noninteractive`** unless the user specifically asks for unattended installation. VPM supports interactive `debconf` screens.

10. **If a command might already be done** (like adding a repo that might exist), handle it gracefully:
    ```
    run: |
      if ! grep -q "some-repo" /etc/apt/sources.list.d/*; then
        sudo add-apt-repository -y ppa:some/repo
      fi
    ```

11. **Always include a verification step** as the last step of each app when possible:
    ```
    - label: Verify Docker installation
      run: docker --version && docker compose version
    ```

12. **Use absolute paths or `$HOME`** instead of `~` in commands (tilde expansion is unreliable in non-interactive shells):
    ```
    # Good
    run: mkdir -p $HOME/apps

    # Avoid
    run: mkdir -p ~/apps
    ```

13. **For services that need to be enabled/started**, combine into one step:
    ```
    - label: Enable and start Nginx
      run: |
        sudo systemctl enable nginx
        sudo systemctl start nginx
        sudo systemctl status nginx --no-pager
    ```

### Best Practices

#### Ordering Apps by Dependency

Always declare dependencies explicitly rather than relying on file order:

```
[system_updates]
- label: Update system
  run: sudo apt-get update -y && sudo apt-get upgrade -y

[build_tools]
requires: system_updates
- label: Install build essentials
  run: sudo apt-get install -y build-essential gcc g++ make

[node_js]
requires: build_tools
- label: Install Node.js via NVM
  run: |
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm install --lts
```

#### Sourcing Profile in Multi-Step Installs

When installing something that modifies `PATH` or shell environment (like NVM, RVM, cargo), you must re-source it in subsequent steps because each step runs in a fresh shell:

```
[rust]
- label: Install Rustup
  run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

- label: Verify Rust installation
  run: |
    source $HOME/.cargo/env
    rustc --version
    cargo --version
```

#### Handling Services That Need Restart

```
[nginx_config]
requires: nginx

- label: Copy configuration
  run: sudo cp /path/to/nginx.conf /etc/nginx/nginx.conf

- label: Test configuration
  run: sudo nginx -t

- label: Reload Nginx
  run: sudo systemctl reload nginx
```

#### Creating Users and Setting Permissions

```
[app_user]
- label: Create application user
  run: |
    id -u appuser &>/dev/null || sudo useradd -m -s /bin/bash appuser
    sudo mkdir -p /opt/myapp
    sudo chown appuser:appuser /opt/myapp
```

### Common Patterns

#### Pattern: Repository + Package Install

```
[custom_repo_app]
- label: Add GPG key
  run: |
    curl -fsSL https://example.com/gpg.key | \
      sudo gpg --dearmor -o /etc/apt/keyrings/example.gpg --yes

- label: Add repository
  run: |
    echo "deb [signed-by=/etc/apt/keyrings/example.gpg] \
      https://packages.example.com/deb stable main" | \
      sudo tee /etc/apt/sources.list.d/example.list > /dev/null

- label: Install package
  run: |
    sudo apt-get update -y
    sudo apt-get install -y example-package

- label: Verify
  run: example-package --version
```

#### Pattern: Download + Extract + Install Binary

```
[binary_tool]
- label: Download latest release
  run: |
    LATEST=$(curl -s https://api.github.com/repos/org/tool/releases/latest | jq -r .tag_name)
    curl -fsSL "https://github.com/org/tool/releases/download/${LATEST}/tool-linux-amd64.tar.gz" \
      -o /tmp/tool.tar.gz

- label: Extract and install
  run: |
    tar xzf /tmp/tool.tar.gz -C /tmp/
    sudo mv /tmp/tool /usr/local/bin/tool
    sudo chmod +x /usr/local/bin/tool
    rm /tmp/tool.tar.gz

- label: Verify
  run: tool version
```

#### Pattern: Clone + Build from Source

```
[from_source]
requires: build_tools

- label: Clone repository
  run: |
    rm -rf /tmp/project-build
    git clone --depth 1 https://github.com/org/project.git /tmp/project-build

- label: Build
  run: |
    cd /tmp/project-build
    ./configure --prefix=/usr/local
    make -j$(nproc)

- label: Install
  run: |
    cd /tmp/project-build
    sudo make install

- label: Clean up build files
  run: rm -rf /tmp/project-build

- label: Verify
  run: project --version
```

#### Pattern: Docker Compose Application

```
[my_app]
requires: docker

- label: Create app directory
  run: mkdir -p $HOME/apps/myapp

- label: Create docker-compose.yml
  run: |
    cat > $HOME/apps/myapp/docker-compose.yml << 'EOF'
    version: "3.8"
    services:
      web:
        image: nginx:alpine
        ports:
          - "80:80"
        restart: unless-stopped
      db:
        image: postgres:16-alpine
        environment:
          POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
        volumes:
          - pgdata:/var/lib/postgresql/data
        restart: unless-stopped
    volumes:
      pgdata:
    EOF

- label: Start services
  run: |
    cd $HOME/apps/myapp
    docker compose up -d

- label: Verify services
  run: |
    cd $HOME/apps/myapp
    docker compose ps
    sleep 3
    curl -sf http://localhost:80 > /dev/null && echo "Web server responding"
```

### Anti-Patterns

**DON'T: Use separate steps for trivially related commands**
```
# Bad — too granular
- run: sudo apt-get update
- run: sudo apt-get install -y curl
- run: sudo apt-get install -y wget
- run: sudo apt-get install -y git
```
```
# Good — logical grouping
- label: Update and install base tools
  run: |
    sudo apt-get update -y
    sudo apt-get install -y curl wget git
```

**DON'T: Assume environment persists between steps**
```
# Bad — variable set in step 1 is lost in step 2
- run: export MY_VAR="hello"
- run: echo $MY_VAR   # This will be empty!
```
```
# Good — use within same step
- label: Configure and use variable
  run: |
    export MY_VAR="hello"
    echo $MY_VAR
```

**DON'T: Use `cd` as a standalone step**
```
# Bad — cd has no effect on the next step
- run: cd /opt/myapp
- run: make build    # Runs in $HOME, not /opt/myapp!
```
```
# Good — cd within the same step
- label: Build project
  run: |
    cd /opt/myapp
    make build
```

**DON'T: Ignore potential failures silently**
```
# Bad — hides errors
- run: some-command || true
```
```
# Good — handle explicitly
- label: Run optional command
  run: |
    if command -v some-command &>/dev/null; then
      some-command
    else
      echo "some-command not found, skipping"
    fi
```

**DON'T: Hardcode user-specific paths**
```
# Bad
- run: cp file /home/deploy/apps/
```
```
# Good
- run: cp file $HOME/apps/
```

### Template for AI Agents

When asked to create a VPM manifest, use this template structure:

```
# ═══════════════════════════════════════════════════════
# VPM Manifest: [Brief description of what this sets up]
# Generated for: [User's described use case]
# Target OS: [Ubuntu 22.04 / Debian 12 / etc.]
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file this-file.yaml
#
# Prerequisites:
#   - [List any manual prerequisites]
#
# After installation:
#   - [List any manual post-install steps]
#

[first_app] Description
- label: Descriptive step name
  run: command

[second_app] Description
requires: first_app
- label: Descriptive step name
  run: |
    multi-line
    command
```

Always include:
1. A header comment block explaining the manifest's purpose
2. Usage instructions in comments
3. Prerequisites and post-install notes
4. Proper dependency declarations
5. Verification steps for each app
6. Descriptive labels for every step

---

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
vpm.py (single file, ~1500 lines)
├── Style          — ANSI color/formatting with terminal detection
├── UI             — Rich terminal components (headers, tables, progress bars, prompts)
├── Config         — XDG-compliant path management
├── LockFile       — Atomic JSON state persistence
├── StepRecord     — Per-step tracking dataclass
├── AppRecord      — Per-app tracking dataclass
├── ManifestParser — Custom format parser (no YAML dependency)
├── ManifestApp    — Parsed app representation with dependencies
├── Executor       — PTY-based command execution with logging
├── Completions    — Shell completion generators (zsh, bash, fish)
├── VPM            — Main CLI application with all command handlers
└── main()         — Argument parsing and dispatch
```

**Key design decisions**:

| Decision | Rationale |
|---|---|
| Single file | Easy to deploy to any VPS — just copy one file |
| No pip dependencies | Nothing to install, no virtual environment needed |
| Custom manifest format | Avoids PyYAML dependency while being human-readable |
| PTY execution | Full interactive support (debconf, ncurses, sudo prompts) |
| Atomic lock file writes | Write to `.tmp` + `rename()` prevents corruption |
| XDG Base Directory spec | Config in `~/.config/vpm/`, data in `~/.local/share/vpm/` |
| SHA-256 command hashing | Detects manifest changes without re-executing |
| Topological sort | Dependency resolution with cycle detection |
| Per-step tracking | Granular resume — skip only what succeeded |

---

*VPM v1.0.0 — Built for humans who manage servers, and the AI agents who help them.*
