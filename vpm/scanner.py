"""Security scanner for VPM manifest commands."""

import json
import re
import urllib.request
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

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
        re.compile(
            r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?-[a-zA-Z]*r[a-zA-Z]*\s+/\s*$"
            r"|rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?-[a-zA-Z]*f[a-zA-Z]*\s+/\s*$"
            r"|rm\s+-rf\s+/\*",
            re.MULTILINE,
        ),
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
        re.compile(r"chmod\s+(-R\s+)?777\s+/\s*$", re.MULTILINE),
        "global-permission-nuke",
        "Setting 777 permissions on root filesystem",
        "This makes every file world-writable. Never do this.",
    ),
]

HIGH_RULES: list[_RuleType] = [
    (
        re.compile(
            r"curl\s+[^|]*\|\s*(sudo\s+)?(ba)?sh\b"
            r"|wget\s+[^|]*\|\s*(sudo\s+)?(ba)?sh\b"
            r"|curl\s+[^|]*\|\s*(sudo\s+)?python"
        ),
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
        re.compile(
            r">\s*/etc/(passwd|shadow|sudoers)\b"
            r"|tee\s+/etc/(passwd|shadow|sudoers)\b"
        ),
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
        re.compile(
            r"(curl|wget)\s+.*-o\s+\S+.*&&.*chmod\s+\+x"
            r"|curl\s+.*>\s*\S+.*&&.*chmod\s+\+x"
        ),
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

URL_PATTERN = re.compile(r'https?://[^\s\'"<>]+')

SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".buzz", ".click", ".loan",
    ".work", ".gq", ".ml", ".tk", ".cf", ".ga",
}
URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl",
    "is.gd", "v.gd", "ow.ly", "buff.ly",
}


class SecurityScanner:
    """Scans manifest commands for security risks."""

    def __init__(self, config: Config):
        self.config = config
        cfg = config.load_config()
        sec = cfg.get("security", {})
        self.level = sec.get("level", "warn")
        self.check_urls = sec.get("check_urls", False)
        self.vt_api_key = sec.get("virustotal_api_key")
        default_domains = {
            "github.com", "raw.githubusercontent.com",
            "download.docker.com", "deb.nodesource.com",
            "packages.microsoft.com", "dl.google.com",
            "archive.ubuntu.com", "deb.debian.org",
            "pypi.org", "files.pythonhosted.org",
            "registry.npmjs.org", "rubygems.org",
        }
        self.allowed_domains = set(sec.get("allowed_domains", default_domains))
        self.allowed_domains.update(sec.get("additional_allowed_domains", []))

    def scan_apps(self, apps: list) -> list[SecurityFinding]:
        """Scan a list of ManifestApp objects. Returns all findings."""
        findings: list[SecurityFinding] = []
        for app in apps:
            for idx, step in enumerate(app.steps):
                command = step.get("command", "")
                label = step.get("label", f"Step {idx + 1}")
                findings.extend(self._scan_command(command, app.name, idx, label))
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

        urls = URL_PATTERN.findall(command)
        for url in urls:
            findings.extend(self._check_url(url, app_name, step_index, step_label))

        return findings

    def _check_url(
        self, url: str, app_name: str, step_index: int, step_label: str
    ) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        try:
            parsed = urlparse(url)
            domain = parsed.hostname or ""
        except Exception:
            return findings

        if any(domain == d or domain.endswith("." + d) for d in self.allowed_domains):
            return findings

        if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain):
            findings.append(SecurityFinding(
                severity=Severity.MEDIUM.value,
                app_name=app_name, step_index=step_index, step_label=step_label,
                pattern_name="ip-only-url",
                description=f"URL uses IP address instead of domain: {domain}",
                matched_text=url[:120],
                suggestion="Use a domain name. IP-only URLs are harder to verify.",
            ))

        for tld in SUSPICIOUS_TLDS:
            if domain.endswith(tld):
                findings.append(SecurityFinding(
                    severity=Severity.MEDIUM.value,
                    app_name=app_name, step_index=step_index, step_label=step_label,
                    pattern_name="suspicious-tld",
                    description=f"URL uses suspicious TLD: {tld}",
                    matched_text=url[:120],
                    suggestion="Verify this domain is legitimate.",
                ))
                break

        if domain in URL_SHORTENERS:
            findings.append(SecurityFinding(
                severity=Severity.HIGH.value,
                app_name=app_name, step_index=step_index, step_label=step_label,
                pattern_name="url-shortener",
                description=f"URL shortener hides the real destination: {domain}",
                matched_text=url[:120],
                suggestion="Use the full, direct URL instead of a shortener.",
            ))

        if url.startswith("http://"):
            findings.append(SecurityFinding(
                severity=Severity.MEDIUM.value,
                app_name=app_name, step_index=step_index, step_label=step_label,
                pattern_name="non-https",
                description="URL uses HTTP instead of HTTPS — traffic is unencrypted",
                matched_text=url[:120],
                suggestion="Use HTTPS to prevent man-in-the-middle attacks.",
            ))

        if self.check_urls and self.vt_api_key:
            findings.extend(self._check_virustotal(url, app_name, step_index, step_label))

        return findings

    def _check_virustotal(
        self, url: str, app_name: str, step_index: int, step_label: str
    ) -> list[SecurityFinding]:
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
                        app_name=app_name, step_index=step_index, step_label=step_label,
                        pattern_name="virustotal-flagged",
                        description=f"VirusTotal: {malicious} malicious, {suspicious} suspicious detections",
                        matched_text=url[:120],
                        suggestion="This URL has been flagged by security vendors. Do not use.",
                    ))
        except Exception:
            pass
        return findings

    def should_block(self, findings: list[SecurityFinding]) -> bool:
        if self.level == "off":
            return False
        for f in findings:
            if f.severity == Severity.CRITICAL.value:
                return True
            if self.level == "strict" and f.severity == Severity.HIGH.value:
                return True
        return False

    def should_warn(self, findings: list[SecurityFinding]) -> bool:
        if self.level == "off":
            return False
        for f in findings:
            if f.severity in (Severity.CRITICAL.value, Severity.HIGH.value):
                return True
            if self.level in ("warn", "strict") and f.severity == Severity.MEDIUM.value:
                return True
        return False

    def filter_display(self, findings: list[SecurityFinding]) -> list[SecurityFinding]:
        if self.level == "off":
            return []
        if self.level == "permissive":
            return [f for f in findings if f.severity in (Severity.CRITICAL.value, Severity.HIGH.value)]
        if self.level == "warn":
            return [f for f in findings if f.severity != Severity.LOW.value]
        return findings  # strict: show everything

    def display_findings(self, findings: list[SecurityFinding]):
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

        counts: dict[str, int] = {}
        for f in displayed:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts = []
        for sev in [Severity.CRITICAL.value, Severity.HIGH.value, Severity.MEDIUM.value, Severity.LOW.value]:
            if sev in counts:
                parts.append(f"{counts[sev]} {sev}")
        UI.info(f"Summary: {', '.join(parts)}")
