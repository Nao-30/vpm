"""Main VPM CLI application class."""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .config import Config
from .executor import Executor
from .lockfile import LockFile
from .manifest import ManifestApp, ManifestParser
from .models import AppRecord, AppStatus, StepStatus
from .scanner import SecurityScanner
from .style import Style
from .ui import UI


class VPM:
    """Main VPM application."""

    def __init__(self):
        self.config = Config()
        self.config.ensure_dirs()
        self.lock = LockFile(self.config)
        self.executor = Executor(self.config, self.lock)

    # ── INIT ──────────────────────────────────────────────────────────────

    def cmd_init(self, args):
        """Initialize a VPM workspace with a manifest template."""
        UI.header("Initialize VPM Workspace", UI.FOLDER)

        target = Path(args.path).resolve() if args.path else Path.cwd()
        manifest_path = target / "vpm-manifest.yaml"

        if manifest_path.exists() and not args.force:
            UI.warning(f"Manifest already exists: {manifest_path}")
            if not UI.confirm("Overwrite existing manifest?"):
                UI.info("Aborted.")
                return

        target.mkdir(parents=True, exist_ok=True)
        template = ManifestParser.generate_template()
        manifest_path.write_text(template)

        UI.success(f"Created manifest: {manifest_path}")
        UI.info("Edit the manifest file to define your apps and installation steps.")
        UI.info(f"Then run: {Style.s('vpm install --file ' + str(manifest_path), Style.BOLD)}")
        UI.dim(f"Or navigate to {target} and run: vpm install")

    # ── INSTALL ───────────────────────────────────────────────────────────

    def cmd_install(self, args):
        """Install apps from manifest file or inline definition."""
        UI.header("VPM Install", UI.ROCKET)

        apps_to_install: list[ManifestApp] = []

        # Determine source
        if args.file:
            manifest_path = Path(args.file).resolve()
            UI.info(f"Reading manifest: {manifest_path}")
            try:
                all_apps = ManifestParser.parse_file(manifest_path)
            except FileNotFoundError as e:
                UI.error(str(e))
                UI.info(f"Run '{Style.s('vpm init', Style.BOLD)}' to create a manifest template.")
                sys.exit(1)
            except Exception as e:
                UI.error(f"Failed to parse manifest: {e}")
                sys.exit(1)

            if args.apps:
                app_names = {Config._safe_name(a) for a in args.apps}
                for app in all_apps:
                    if Config._safe_name(app.name) in app_names:
                        apps_to_install.append(app)
                missing = app_names - {Config._safe_name(a.name) for a in apps_to_install}
                if missing:
                    UI.warning(f"Apps not found in manifest: {', '.join(missing)}")
                    available = [a.name for a in all_apps]
                    UI.info(f"Available: {', '.join(available)}")
            else:
                apps_to_install = all_apps
        elif args.apps:
            found = self._find_manifest()
            if found:
                UI.info(f"Using manifest: {found}")
                try:
                    all_apps = ManifestParser.parse_file(found)
                except Exception as e:
                    UI.error(f"Failed to parse manifest: {e}")
                    sys.exit(1)
                app_names = {Config._safe_name(a) for a in args.apps}
                for app in all_apps:
                    if Config._safe_name(app.name) in app_names:
                        apps_to_install.append(app)
                missing = app_names - {Config._safe_name(a.name) for a in apps_to_install}
                if missing:
                    UI.error(f"Apps not found in manifest: {', '.join(missing)}")
                    sys.exit(1)
            else:
                UI.error("No manifest file found. Specify one with --file or run 'vpm init'.")
                sys.exit(1)
        else:
            found = self._find_manifest()
            if not found:
                UI.error("No manifest file found.")
                UI.info(f"Create one with: {Style.s('vpm init', Style.BOLD)}")
                UI.info(f"Or specify one with: {Style.s('vpm install --file <path>', Style.BOLD)}")
                sys.exit(1)

            UI.info(f"Using manifest: {found}")
            try:
                apps_to_install = ManifestParser.parse_file(found)
            except Exception as e:
                UI.error(f"Failed to parse manifest: {e}")
                sys.exit(1)

        if not apps_to_install:
            UI.warning("No apps to install.")
            return

        # Resolve dependency order
        try:
            apps_to_install = self.executor.resolve_order(apps_to_install, self.lock)
        except ValueError as e:
            UI.error(f"Dependency error: {e}")
            sys.exit(1)

        # Show dependency info
        has_deps = any(a.requires for a in apps_to_install)
        if has_deps:
            UI.sub_header("Resolved installation order (based on dependencies):")
            for i, app in enumerate(apps_to_install):
                dep_info = ""
                if app.requires:
                    dep_info = Style.s(
                        f" (requires: {', '.join(app.requires)})", Style.DIM
                    )
                print(f"    {Style.s(str(i + 1), Style.CYAN)}. {app.name}{dep_info}")

        # Security scan
        if not getattr(args, "skip_security", False):
            scanner = SecurityScanner(self.config)
            findings = scanner.scan_apps(apps_to_install)
            if findings:
                scanner.display_findings(findings)
                if scanner.should_block(findings):
                    UI.error("Blocked by security scanner. Use --skip-security to override.")
                    return
                if scanner.should_warn(findings) and not args.yes:
                    if not UI.confirm("Security warnings found. Continue anyway?"):
                        return

        # Dry run
        if args.dry_run:
            self._dry_run(apps_to_install)
            return

        # Confirmation
        self._show_install_plan(apps_to_install)

        if not args.yes and not UI.confirm("Proceed with installation?", default=True):
            UI.info("Aborted.")
            return

        # Execute
        results = self._execute_install(apps_to_install, args.force)

        # Final summary
        self._show_install_summary(results)

    def _find_manifest(self) -> Path | None:
        search_paths = [
            Path.cwd() / "vpm-manifest.yaml",
            Path.cwd() / "vpm-manifest.yml",
            Path.cwd() / ".vpm-manifest.yaml",
            self.config.config_dir / "manifest.yaml",
        ]
        for p in search_paths:
            if p.exists():
                return p
        return None

    def _dry_run(self, apps: list[ManifestApp]):
        UI.sub_header("Dry Run — nothing will be executed")
        for app in apps:
            print(f"\n  {Style.s(UI.PACKAGE, Style.CYAN)} {Style.s(app.name, Style.BOLD)}"
                  f"  {Style.s(app.description, Style.DIM) if app.description else ''}")
            for i, step in enumerate(app.steps):
                status_icon = Style.s(UI.DOT, Style.GRAY)
                existing = self.lock.get_app(app.name)
                if existing:
                    for es in existing.steps:
                        if es.index == i and es.status == StepStatus.SUCCESS.value:
                            status_icon = Style.s(UI.CHECK, Style.GREEN)
                            break
                        elif es.index == i and es.status == StepStatus.FAILED.value:
                            status_icon = Style.s(UI.CROSS, Style.RED)
                            break
                print(f"    {status_icon} {step['label']}")
                UI.dim(f"  $ {step['command'][:80]}{'...' if len(step['command']) > 80 else ''}")

    def _show_install_plan(self, apps: list[ManifestApp]):
        print()
        UI.sub_header("Apps to install:")
        total_steps = 0
        for app in apps:
            existing = self.lock.get_app(app.name)
            status_text = ""
            if existing:
                if existing.status == AppStatus.COMPLETED.value:
                    status_text = Style.s(" (already installed)", Style.GREEN)
                elif existing.status in (AppStatus.PARTIAL.value, AppStatus.FAILED.value):
                    status_text = Style.s(
                        f" (resumable: {existing.completed_steps}/{existing.total_steps} done)",
                        Style.YELLOW,
                    )
            print(f"  {Style.s(UI.PACKAGE, Style.CYAN)} {Style.s(app.name, Style.BOLD)} "
                  f"— {len(app.steps)} step(s){status_text}")
            total_steps += len(app.steps)

        print()
        UI.info(f"Total: {len(apps)} app(s), {total_steps} step(s)")

    def _execute_install(self, apps: list[ManifestApp], force: bool) -> list[AppRecord]:
        results: list[AppRecord] = []
        for app in apps:
            if self.executor._interrupted:
                UI.warning("Installation interrupted. Remaining apps skipped.")
                break

            # Check that all dependencies succeeded
            dep_failed = False
            for dep in app.requires:
                dep_record = self.lock.get_app(dep)
                if not dep_record or dep_record.status != AppStatus.COMPLETED.value:
                    dep_failed = True
                    UI.error(
                        f"Skipping '{app.name}': dependency '{dep}' "
                        f"is not successfully installed."
                    )
                    break

            if dep_failed:
                record = self.lock.get_app(app.name) or AppRecord(
                    name=app.name,
                    display_name=app.name,
                    created_at=datetime.datetime.now().isoformat(),
                )
                record.status = AppStatus.FAILED.value
                record.updated_at = datetime.datetime.now().isoformat()
                self.lock.set_app(record)
                results.append(record)
                continue

            result = self.executor.execute_app(app, force=force)
            results.append(result)
        return results

    def _show_install_summary(self, results: list[AppRecord]):
        print()
        UI.header("Installation Summary", UI.SHIELD)
        headers = ["App", "Status", "Steps", "Failed", "Duration"]
        rows = []
        for r in results:
            status_display = {
                AppStatus.COMPLETED.value: Style.s("✔ Completed", Style.GREEN),
                AppStatus.PARTIAL.value: Style.s("◐ Partial", Style.YELLOW),
                AppStatus.FAILED.value: Style.s("✖ Failed", Style.RED),
                AppStatus.IN_PROGRESS.value: Style.s("… In Progress", Style.BLUE),
                AppStatus.PENDING.value: Style.s("○ Pending", Style.DIM),
            }.get(r.status, r.status)

            total_dur = sum(s.duration_seconds or 0 for s in r.steps)
            rows.append([
                r.display_name,
                status_display,
                f"{r.completed_steps}/{r.total_steps}",
                str(r.failed_steps) if r.failed_steps else Style.s("0", Style.DIM),
                f"{total_dur:.1f}s",
            ])
        UI.table(headers, rows)

    # ── STATUS ────────────────────────────────────────────────────────────

    def cmd_status(self, args):
        """Show installation status."""
        UI.header("Installation Status", UI.SHIELD)

        apps = self.lock.all_apps()
        if not apps:
            UI.info("No apps tracked yet. Run 'vpm install' to get started.")
            return

        if args.app:
            safe = Config._safe_name(args.app)
            if safe not in apps:
                UI.error(f"App '{args.app}' not found in tracking.")
                return
            record = apps[safe]
            self._show_app_detail(record)
        else:
            headers = ["App", "Status", "Progress", "Failed", "Last Updated"]
            rows = []
            for name, record in apps.items():
                status_display = {
                    AppStatus.COMPLETED.value: Style.s("✔ Completed", Style.GREEN),
                    AppStatus.PARTIAL.value: Style.s("◐ Partial", Style.YELLOW),
                    AppStatus.FAILED.value: Style.s("✖ Failed", Style.RED),
                    AppStatus.IN_PROGRESS.value: Style.s("… Running", Style.BLUE),
                    AppStatus.PENDING.value: Style.s("○ Pending", Style.DIM),
                    AppStatus.ROLLED_BACK.value: Style.s("⏪ Rolled Back", Style.MAGENTA),
                }.get(record.status, record.status)

                updated = ""
                if record.updated_at:
                    try:
                        dt = datetime.datetime.fromisoformat(record.updated_at)
                        updated = dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        updated = record.updated_at

                rows.append([
                    record.display_name,
                    status_display,
                    f"{record.completed_steps}/{record.total_steps}",
                    str(record.failed_steps) if record.failed_steps else Style.s("0", Style.DIM),
                    updated,
                ])
            UI.table(headers, rows)

    def _show_app_detail(self, record: AppRecord):
        """Show detailed status for a single app."""
        UI.sub_header(f"App: {record.display_name}")
        print(f"  Status: {record.status}")
        print(f"  Log Dir: {record.log_dir}")
        print(f"  Created: {record.created_at}")
        print(f"  Updated: {record.updated_at}")
        print()

        headers = ["#", "Step", "Status", "Exit", "Duration", "Log"]
        rows = []
        for step in record.steps:
            status_icon = {
                StepStatus.SUCCESS.value: Style.s("✔", Style.GREEN),
                StepStatus.FAILED.value: Style.s("✖", Style.RED),
                StepStatus.RUNNING.value: Style.s("…", Style.BLUE),
                StepStatus.SKIPPED.value: Style.s("⊘", Style.DIM),
                StepStatus.PENDING.value: Style.s("○", Style.DIM),
            }.get(step.status, step.status)

            dur = f"{step.duration_seconds:.1f}s" if step.duration_seconds else "-"
            exit_code = str(step.exit_code) if step.exit_code is not None else "-"
            log_ref = Path(step.log_file).name if step.log_file else "-"

            rows.append([
                str(step.index + 1),
                step.label[:40],
                status_icon,
                exit_code,
                dur,
                log_ref,
            ])
        UI.table(headers, rows)

        if record.failed_steps > 0:
            UI.info(f"Retry with: {Style.s(f'vpm retry {record.name}', Style.BOLD)}")

    # ── LIST ──────────────────────────────────────────────────────────────

    def cmd_list(self, args):
        """List all managed apps."""
        self.cmd_status(argparse.Namespace(app=None))

    # ── LOGS ──────────────────────────────────────────────────────────────

    def cmd_logs(self, args):
        """View logs for an app."""
        UI.header("Logs", UI.FILE)

        if not args.app:
            apps = self.lock.all_apps()
            if not apps:
                UI.info("No apps tracked.")
                return
            for name, record in apps.items():
                if record.log_dir:
                    log_path = Path(record.log_dir)
                    files = sorted(log_path.glob("*")) if log_path.exists() else []
                    print(
                        f"  {Style.s(UI.FOLDER, Style.CYAN)} {name}: "
                        f"{Style.s(str(log_path), Style.UNDERLINE)} "
                        f"({len(files)} files)"
                    )
            return

        Config._safe_name(args.app)
        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found.")
            return

        log_dir = Path(record.log_dir) if record.log_dir else None
        if not log_dir or not log_dir.exists():
            UI.warning("No log directory found for this app.")
            return

        if args.step is not None:
            if 0 <= args.step < len(record.steps):
                step = record.steps[args.step]
                if step.log_file and Path(step.log_file).exists():
                    UI.sub_header(f"Log: Step {args.step + 1} — {step.label}")
                    print()
                    print(Path(step.log_file).read_text())
                else:
                    UI.warning("No log file for this step.")
            else:
                UI.error(f"Step index {args.step} out of range (0-{len(record.steps) - 1}).")
            return

        if args.follow:
            summaries = sorted(log_dir.glob("summary_*.log"), reverse=True)
            if summaries:
                target = summaries[0]
                UI.info(f"Following: {target}")
                try:
                    subprocess.run(["tail", "-f", str(target)])
                except KeyboardInterrupt:
                    pass
            else:
                UI.warning("No summary logs found.")
            return

        UI.sub_header(f"Logs for: {record.display_name}")
        UI.dim(f"Directory: {log_dir}")
        print()

        files = sorted(log_dir.glob("*"), reverse=True)
        if not files:
            UI.warning("No log files found.")
            return

        for f in files:
            size = f.stat().st_size
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            size_str = self._format_size(size)
            time_str = mtime.strftime("%H:%M:%S")

            is_summary = f.name.startswith("summary_")
            icon = UI.FILE if not is_summary else "📋"
            name_style = Style.BOLD if is_summary else ""

            print(
                f"  {icon} {Style.s(f.name, name_style)} "
                f"{Style.s(f'({size_str}, {time_str})', Style.DIM)}"
            )

        if args.latest:
            summaries = sorted(log_dir.glob("summary_*.log"), reverse=True)
            if summaries:
                print(f"\n{'─' * 60}")
                UI.sub_header(f"Latest Summary: {summaries[0].name}")
                print()
                print(summaries[0].read_text())

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    # ── RETRY ─────────────────────────────────────────────────────────────

    def cmd_retry(self, args):
        """Retry failed app installation from the point of failure."""
        UI.header("Retry Installation", UI.GEAR)

        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found in tracking.")
            UI.info("Run 'vpm list' to see tracked apps.")
            return

        if record.status == AppStatus.COMPLETED.value:
            UI.success(f"'{args.app}' is already fully installed.")
            if UI.confirm("Force re-run all steps?"):
                for step in record.steps:
                    step.status = StepStatus.PENDING.value
                    step.exit_code = None
                    step.started_at = None
                    step.finished_at = None
                    step.duration_seconds = None
                    step.error_summary = None
                record.status = AppStatus.PENDING.value
                self.lock.set_app(record)
            else:
                return

        for step in record.steps:
            if step.status in (StepStatus.FAILED.value, StepStatus.SKIPPED.value):
                step.status = StepStatus.PENDING.value
                step.exit_code = None
                step.error_summary = None

        record.status = AppStatus.IN_PROGRESS.value
        self.lock.set_app(record)

        manifest_app = ManifestApp(
            name=record.name,
            steps=[{"label": s.label, "command": s.command} for s in record.steps],
            description="",
        )

        self.executor.execute_app(manifest_app, force=False)

    # ── RESET ─────────────────────────────────────────────────────────────

    def cmd_reset(self, args):
        """Reset tracking for an app."""
        UI.header("Reset App Tracking", UI.BROOM)

        if args.all:
            apps = self.lock.all_apps()
            if not apps:
                UI.info("Nothing to reset.")
                return
            UI.warning(f"This will reset tracking for {len(apps)} app(s).")
            if not UI.confirm("Are you sure?"):
                return
            for name in list(apps.keys()):
                self.lock.remove_app(name)
                UI.success(f"Reset: {name}")
            if args.clean_logs:
                shutil.rmtree(self.config.logs_dir, ignore_errors=True)
                self.config.logs_dir.mkdir(parents=True, exist_ok=True)
                UI.success("Cleaned all logs.")
            return

        if not args.app:
            UI.error("Specify an app name or use --all.")
            return

        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found.")
            return

        UI.warning(f"This will reset all tracking for '{args.app}'.")
        if args.clean_logs and record.log_dir:
            UI.warning(f"Logs will also be deleted: {record.log_dir}")

        if not UI.confirm("Proceed?"):
            return

        if args.clean_logs and record.log_dir:
            shutil.rmtree(record.log_dir, ignore_errors=True)
            UI.success("Logs cleaned.")

        self.lock.remove_app(args.app)
        UI.success(f"Reset tracking for '{args.app}'.")

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

    # ── ROLLBACK ──────────────────────────────────────────────────────────

    def cmd_rollback(self, args):
        """Rollback a previously installed app."""
        UI.header("Rollback", "⏪")

        record = self.lock.get_app(args.app)
        if not record:
            UI.error(f"App '{args.app}' not found in tracking.")
            UI.info("Run 'vpm list' to see tracked apps.")
            return

        has_rollback = any(s.rollback_command for s in record.steps)
        if not has_rollback:
            UI.error(f"No rollback commands defined for '{args.app}'.")
            UI.info("Add 'rollback:' fields to your manifest steps to enable rollback.")
            return

        succeeded_with_rb = [
            s for s in record.steps
            if s.status == StepStatus.SUCCESS.value and s.rollback_command
        ]
        succeeded_without = [
            s for s in record.steps
            if s.status == StepStatus.SUCCESS.value and not s.rollback_command
        ]

        if not succeeded_with_rb:
            UI.warning("No succeeded steps with rollback commands to undo.")
            return

        UI.info(f"Steps to rollback ({len(succeeded_with_rb)}):")
        for s in reversed(succeeded_with_rb):
            UI.dim(f"  {s.index + 1}. {s.label}")

        if succeeded_without:
            UI.warning(f"{len(succeeded_without)} succeeded step(s) have no rollback command and will be skipped.")

        if args.dry_run:
            self.executor.rollback_app(record, dry_run=True)
            return

        if not UI.confirm("Proceed with rollback?"):
            return

        self.executor.rollback_app(record)

    # ── RUN (remote manifest) ────────────────────────────────────────────

    def cmd_run(self, args):
        """Fetch and execute a remote manifest."""
        UI.header("Run Remote Manifest", "🌐")

        source = args.source

        if source.startswith(("http://", "https://")):
            url = source
        elif source.startswith("github:"):
            parts = source[7:]
            segments = parts.split("/", 2)
            if len(segments) < 2:
                UI.error("GitHub shorthand: github:user/repo or github:user/repo/path/file.yaml")
                return
            user, repo = segments[0], segments[1]
            path = segments[2] if len(segments) > 2 else "vpm-manifest.yaml"
            url = f"https://raw.githubusercontent.com/{user}/{repo}/main/{path}"
        elif Path(source).exists():
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
            UI.info("Supported: https://..., github:user/repo, ./local-file.yaml")
            return

        UI.info(f"Fetching: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vpm/1.1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404 and source.startswith("github:") and "/main/" in url:
                url = url.replace("/main/", "/master/")
                UI.dim("  main not found, trying master...")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "vpm/1.1.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        content = resp.read().decode("utf-8")
                except Exception as e2:
                    UI.error(f"Failed to fetch: {e2}")
                    return
            else:
                UI.error(f"Failed to fetch: {e}")
                return
        except Exception as e:
            UI.error(f"Failed to fetch: {e}")
            return

        UI.success(f"Fetched {len(content)} bytes")

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
                UI.error("Blocked: Critical security issues in remote manifest.")
                return
            if not getattr(args, "yes", False):
                if not UI.confirm("Security warnings found in remote manifest. Continue?"):
                    return
        else:
            UI.success("Security scan clean.")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix="vpm_remote_", delete=False
        ) as tmp:
            tmp.write(content)
            manifest_path = tmp.name

        try:
            args.file = manifest_path
            args.apps = []
            args.force = False
            args.skip_security = True  # Already scanned
            self.cmd_install(args)
        finally:
            try:
                os.unlink(manifest_path)
            except OSError:
                pass
