# VPM — AI Agent Reference

> Concise reference for AI agents generating VPM manifests or using the CLI.
> Full docs: [README.md](README.md)

## What is VPM?

VPM (Virtual Package Manager) is a Python CLI that orchestrates shell commands with tracking, resume, dependency resolution, and full logging. Install via `pip install vpmx`, CLI command is `vpm`.

## Installation

```bash
pip install vpmx    # or: pipx install vpmx
vpm doctor          # verify environment
vpm version         # check version
```

Requires Python 3.10+. No external dependencies.

## Manifest Format

File: `vpm-manifest.yaml` (custom format, NOT standard YAML)

```yaml
# Comments start with #

[app_name] Optional description
requires: dependency1, dependency2

- label: What this step does
  run: shell command here

- label: Multi-line command
  run: |
    line one
    line two
    line three

- label: With rollback
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx

- run: shorthand without explicit label
```

### Rules

1. App names: `snake_case` only. `[docker_engine]` not `[Docker Engine]`
2. Every step MUST have a descriptive `label:`
3. Steps should be idempotent: `apt-get install -y`, `mkdir -p`, `ln -sf`
4. Group related commands into logical steps (not one per command, not 50 in one step)
5. Never use `cd` as a separate step — use within multi-line block
6. Use `sudo` explicitly where needed
7. Do NOT set `DEBIAN_FRONTEND=noninteractive` unless user asks
8. Use `$HOME` not `~` in commands
9. Always include a verification step as last step per app
10. Use `requires:` for dependencies between apps
11. Handle already-done states gracefully (check before creating)
12. For services: combine enable + start + status in one step
13. Add `rollback:` for reversible steps when possible

### Common Patterns

**Repository + Package:**
```yaml
[custom_repo]
- label: Add GPG key
  run: |
    curl -fsSL https://example.com/gpg.key | \
      sudo gpg --dearmor -o /etc/apt/keyrings/example.gpg --yes

- label: Add repository
  run: |
    echo "deb [signed-by=/etc/apt/keyrings/example.gpg] \
      https://packages.example.com/deb stable main" | \
      sudo tee /etc/apt/sources.list.d/example.list > /dev/null

- label: Install
  run: sudo apt-get update -y && sudo apt-get install -y example-package

- label: Verify
  run: example-package --version
```

**Docker Compose App:**
```yaml
[my_app]
requires: docker

- label: Create app directory
  run: mkdir -p $HOME/apps/myapp

- label: Start services
  run: |
    cd $HOME/apps/myapp
    docker compose up -d

- label: Verify
  run: docker compose -f $HOME/apps/myapp/docker-compose.yml ps
```

### Anti-Patterns

- DON'T: Separate steps for trivially related commands (one apt-get per package)
- DON'T: Assume environment persists between steps (export in step 1 is lost in step 2)
- DON'T: Use `cd` as standalone step (runs in subshell, no effect on next step)
- DON'T: Suppress errors silently (`|| true`) — handle explicitly with `if/then`
- DON'T: Hardcode user paths (`/home/deploy/`) — use `$HOME`

## CLI Reference

```bash
vpm init [path] [--force]              # Create manifest template
vpm install [apps...] [--file F]       # Execute manifest
  [--force] [--dry-run] [--yes] [--skip-security]
vpm audit [--file F]                   # Security scan without executing
vpm run <source> [--yes] [--dry-run]   # Fetch + scan + execute remote manifest
vpm rollback <app> [--dry-run]         # Undo using rollback: commands
vpm status [app]                       # Show installation status
vpm list                               # Alias for status
vpm logs <app> [--latest] [--step N] [--follow]
vpm retry <app>                        # Resume from failure point
vpm reset <app|--all> [--clean-logs]   # Clear tracking state
vpm setup [--user|--global]            # Install to PATH
vpm doctor                             # Diagnose environment
vpm completions [--shell S]            # Install shell completions
vpm version                            # Show version info
```

## Template for AI Agents

When asked to create a VPM manifest, use this structure:

```yaml
# ═══════════════════════════════════════════════════════
# VPM Manifest: [Brief description]
# Target OS: [Ubuntu 22.04 / Debian 12 / etc.]
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file this-file.yaml
#
# Prerequisites:
#   - [List any manual prerequisites]
#

[first_app] Description
- label: Descriptive step name
  run: command
  rollback: undo command

[second_app] Description
requires: first_app
- label: Descriptive step name
  run: |
    multi-line
    command

- label: Verify installation
  run: command --version
```

Always include: header comments, dependency declarations, verification steps, descriptive labels, rollback commands where possible.
