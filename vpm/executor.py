"""PTY-based command executor with full logging and tracking."""

import datetime
import errno
import hashlib
import os
import platform
import pty
import re
import select
import signal
import sys
from pathlib import Path

from .config import Config
from .lockfile import LockFile
from .manifest import ManifestApp
from .models import AppRecord, AppStatus, StepRecord, StepStatus
from .style import Style
from .ui import UI


class Executor:
    """Executes shell commands with full logging and tracking."""

    def __init__(self, config: Config, lock: LockFile):
        self.config = config
        self.lock = lock
        self._interrupted = False
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        self._interrupted = True
        print()
        UI.warning("Interrupt received. Finishing current step gracefully...")

    def compute_command_hash(self, command: str) -> str:
        return hashlib.sha256(command.encode()).hexdigest()[:12]

    def resolve_order(
        self, apps: list[ManifestApp], lock: LockFile
    ) -> list[ManifestApp]:
        """
        Topologically sort apps based on their 'requires' field.
        Raises an error on circular dependencies.
        """
        by_name: dict[str, ManifestApp] = {}
        for app in apps:
            safe = Config._safe_name(app.name)
            by_name[safe] = app

        # Build adjacency list
        graph: dict[str, list[str]] = {Config._safe_name(a.name): [] for a in apps}
        for app in apps:
            safe = Config._safe_name(app.name)
            for dep in app.requires:
                dep_safe = Config._safe_name(dep)
                if dep_safe not in by_name:
                    # Dependency not in this manifest — check if already installed
                    existing = lock.get_app(dep)
                    if existing and existing.status == AppStatus.COMPLETED.value:
                        UI.dim(
                            f"Dependency '{dep}' for '{app.name}' "
                            f"already satisfied (installed previously)"
                        )
                        continue
                    else:
                        raise ValueError(
                            f"App '{app.name}' requires '{dep}', but it is "
                            f"not in the manifest and not previously installed. "
                            f"Add '{dep}' to your manifest or install it first."
                        )
                graph[safe].append(dep_safe)

        # Kahn's algorithm for topological sort
        in_degree: dict[str, int] = {n: 0 for n in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] = in_degree.get(dep, 0)  # ensure exists
                    # node depends on dep, so dep must come first
                    # we track the reverse: in_degree counts how many depend on you
                    pass

        # Actually build it properly: edge from dep -> node (dep must come before node)
        reverse_graph: dict[str, list[str]] = {n: [] for n in graph}
        in_degree = {n: 0 for n in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in reverse_graph:
                    reverse_graph[dep].append(node)
                    in_degree[node] += 1

        queue = [n for n in in_degree if in_degree[n] == 0]
        order: list[str] = []

        while queue:
            queue.sort()  # deterministic order
            node = queue.pop(0)
            order.append(node)
            for neighbor in reverse_graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(graph):
            remaining = set(graph.keys()) - set(order)
            raise ValueError(
                f"Circular dependency detected involving: {', '.join(remaining)}"
            )

        return [by_name[name] for name in order if name in by_name]

    def execute_app(self, app: ManifestApp, force: bool = False) -> AppRecord:
        """Execute all steps for an app, with skip/resume logic."""
        now = datetime.datetime.now()
        app_log_dir = self.config.get_app_log_dir(app.name)

        # Check existing record
        record = self.lock.get_app(app.name)
        is_resume = False

        if record and not force:
            if record.status == AppStatus.COMPLETED.value:
                # Check if steps changed
                existing_hashes = {s.command_hash for s in record.steps}
                new_hashes = {
                    self.compute_command_hash(s["command"]) for s in app.steps
                }
                if existing_hashes == new_hashes:
                    UI.success(f"'{app.name}' is already fully installed. Use --force to reinstall.")
                    return record
                else:
                    UI.warning(f"'{app.name}' manifest has changed since last install.")
                    if not UI.confirm("Re-run with updated steps?"):
                        return record
                    force = True

            elif record.status in (
                AppStatus.PARTIAL.value,
                AppStatus.FAILED.value,
                AppStatus.IN_PROGRESS.value,
            ):
                UI.warning(f"'{app.name}' has a previous incomplete/failed installation.")
                is_resume = True

        if force or not record:
            # Build fresh record
            steps = []
            for idx, step_def in enumerate(app.steps):
                steps.append(
                    StepRecord(
                        index=idx,
                        label=step_def["label"],
                        command=step_def["command"],
                        command_hash=self.compute_command_hash(step_def["command"]),
                        rollback_command=step_def.get("rollback"),
                    )
                )
            record = AppRecord(
                name=app.name,
                display_name=app.name,
                steps=steps,
                log_dir=str(app_log_dir),
                created_at=now.isoformat(),
                requires=app.requires,
            )
            if app.description:
                record.display_name = f"{app.name} ({app.description})"

        record.status = AppStatus.IN_PROGRESS.value
        self.lock.set_app(record)

        UI.header(f"Installing: {record.display_name}", UI.PACKAGE)
        UI.info(f"Log directory: {Style.s(str(app_log_dir), Style.UNDERLINE)}")
        total = len(record.steps)

        # Summary log for the app
        summary_log = app_log_dir / f"summary_{now.strftime('%Y%m%d_%H%M%S')}.log"

        with open(summary_log, "w") as summary_f:
            summary_f.write("VPM Installation Summary\n")
            summary_f.write(f"{'=' * 60}\n")
            summary_f.write(f"App: {record.display_name}\n")
            summary_f.write(f"Started: {now.isoformat()}\n")
            summary_f.write(f"User: {os.environ.get('USER', 'unknown')}\n")
            summary_f.write(f"Host: {platform.node()}\n")
            summary_f.write(f"Total Steps: {total}\n")
            summary_f.write(f"{'=' * 60}\n\n")

            for step in record.steps:
                if self._interrupted:
                    UI.warning("Skipping remaining steps due to interrupt.")
                    step.status = StepStatus.SKIPPED.value
                    summary_f.write(f"[SKIPPED] Step {step.index + 1}: {step.label} (interrupted)\n")
                    continue

                # Skip already completed steps (resume mode)
                if is_resume and step.status == StepStatus.SUCCESS.value:
                    UI.step(step.index + 1, total, f"{step.label}")
                    UI.success("Already completed — skipping")
                    summary_f.write(f"[SKIPPED/OK] Step {step.index + 1}: {step.label}\n")
                    continue

                UI.step(step.index + 1, total, step.label)
                UI.dim(f"$ {step.command[:100]}{'...' if len(step.command) > 100 else ''}")

                success = self._run_step(step, app_log_dir, summary_f)
                if not success:
                    # Skip remaining steps
                    for remaining in record.steps[step.index + 1:]:
                        if remaining.status != StepStatus.SUCCESS.value:
                            remaining.status = StepStatus.SKIPPED.value
                            summary_f.write(
                                f"[SKIPPED] Step {remaining.index + 1}: {remaining.label} "
                                f"(previous step failed)\n"
                            )
                    break

                UI.progress_bar(step.index + 1, total)

            # Final status
            end_time = datetime.datetime.now()
            record.recalculate()

            summary_f.write(f"\n{'=' * 60}\n")
            summary_f.write(f"Finished: {end_time.isoformat()}\n")
            summary_f.write(f"Duration: {(end_time - now).total_seconds():.1f}s\n")
            summary_f.write(f"Status: {record.status}\n")
            summary_f.write(
                f"Steps: {record.completed_steps}/{record.total_steps} succeeded, "
                f"{record.failed_steps} failed\n"
            )
            summary_f.write(f"{'=' * 60}\n")

        self.lock.set_app(record)

        print()
        if record.status == AppStatus.COMPLETED.value:
            UI.success(
                f"All {record.total_steps} steps completed successfully! "
                f"({(end_time - now).total_seconds():.1f}s)"
            )
        elif record.status == AppStatus.PARTIAL.value:
            UI.warning(
                f"{record.completed_steps}/{record.total_steps} steps succeeded, "
                f"{record.failed_steps} failed. Use 'vpm retry {app.name}' to retry."
            )
        elif record.status == AppStatus.FAILED.value:
            UI.error(
                f"Installation failed. {record.failed_steps} step(s) failed. "
                f"Check logs: {summary_log}"
            )
        UI.dim(f"Summary: {summary_log}")

        return record

    def _run_step(
        self, step: StepRecord, log_dir: Path, summary_f
    ) -> bool:
        """Run a single step command with full logging using PTY for interactive support."""
        now = datetime.datetime.now()
        step.status = StepStatus.RUNNING.value
        step.started_at = now.isoformat()

        # Create log file for this step
        safe_label = re.sub(r"[^\w\-.]", "_", step.label)[:50]
        log_file = log_dir / f"step_{step.index:03d}_{safe_label}_{now.strftime('%H%M%S')}.log"
        step.log_file = str(log_file)

        try:
            with open(log_file, "w") as lf:
                lf.write("VPM Step Execution Log\n")
                lf.write(f"{'─' * 60}\n")
                lf.write(f"Step: {step.index + 1} — {step.label}\n")
                lf.write(f"Started: {now.isoformat()}\n")
                lf.write(f"Command:\n{step.command}\n")
                lf.write(f"{'─' * 60}\n\n")
                lf.flush()

                shell = os.environ.get("SHELL", "/bin/bash")
                if "bash" not in shell and "zsh" not in shell:
                    shell = "/bin/bash"

                env = os.environ.copy()

                exit_code = self._pty_exec(
                    shell_path=shell,
                    command=step.command,
                    env=env,
                    log_fh=lf,
                )

                end_time = datetime.datetime.now()
                step.exit_code = exit_code
                step.finished_at = end_time.isoformat()
                step.duration_seconds = (end_time - now).total_seconds()

                lf.write(f"\n{'─' * 60}\n")
                lf.write(f"Exit Code: {exit_code}\n")
                lf.write(f"Duration: {step.duration_seconds:.1f}s\n")
                lf.write(f"Finished: {end_time.isoformat()}\n")

                if exit_code == 0:
                    step.status = StepStatus.SUCCESS.value
                    UI.success(f"Done ({step.duration_seconds:.1f}s)")
                    summary_f.write(
                        f"[OK] Step {step.index + 1}: {step.label} "
                        f"(exit={exit_code}, {step.duration_seconds:.1f}s)\n"
                    )
                    return True
                else:
                    step.status = StepStatus.FAILED.value
                    # Read last few lines of log for error summary
                    try:
                        log_content = Path(step.log_file).read_text()
                        last_lines = log_content.strip().split("\n")[-5:]
                        step.error_summary = "\n".join(last_lines)[-500:]
                    except OSError:
                        step.error_summary = f"Exit code {exit_code}"

                    UI.error(
                        f"Failed (exit code {exit_code}, {step.duration_seconds:.1f}s)"
                    )
                    UI.dim(f"Log: {log_file}")
                    if step.error_summary:
                        for err_line in step.error_summary.split("\n")[-3:]:
                            cleaned = Style.strip_ansi(err_line.strip())
                            if cleaned:
                                UI.dim(f"  {cleaned}")
                    summary_f.write(
                        f"[FAIL] Step {step.index + 1}: {step.label} "
                        f"(exit={exit_code}, {step.duration_seconds:.1f}s)\n"
                    )
                    if step.error_summary:
                        summary_f.write(
                            f"  Error: {Style.strip_ansi(step.error_summary[:200])}\n"
                        )
                    return False

        except OSError as e:
            step.status = StepStatus.FAILED.value
            step.error_summary = str(e)
            step.finished_at = datetime.datetime.now().isoformat()
            UI.error(f"Execution error: {e}")
            summary_f.write(
                f"[ERROR] Step {step.index + 1}: {step.label} — {e}\n"
            )
            return False

    def rollback_app(self, record: AppRecord, dry_run: bool = False) -> AppRecord:
        """Run rollback commands in reverse order for succeeded steps."""
        now = datetime.datetime.now()
        app_log_dir = self.config.get_app_log_dir(record.name)

        rollback_steps = [
            s for s in reversed(record.steps)
            if s.status == StepStatus.SUCCESS.value and s.rollback_command
        ]

        if not rollback_steps:
            UI.warning("No steps to rollback (no succeeded steps with rollback commands).")
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
            summary_f.write(f"VPM Rollback Summary\n{'=' * 60}\n")
            summary_f.write(f"App: {record.display_name}\nStarted: {now.isoformat()}\n")
            summary_f.write(f"Steps to rollback: {len(rollback_steps)}\n{'=' * 60}\n\n")

            for i, step in enumerate(rollback_steps):
                UI.step(i + 1, len(rollback_steps), f"[ROLLBACK] {step.label}")
                UI.dim(f"  $ {step.rollback_command[:100]}")

                step.rollback_status = StepStatus.RUNNING.value
                self.lock.set_app(record)

                safe_label = re.sub(r"[^\w\-.]", "_", step.label)[:50]
                rb_log = app_log_dir / f"rollback_{step.index:03d}_{safe_label}_{now.strftime('%H%M%S')}.log"
                step.rollback_log_file = str(rb_log)

                try:
                    with open(rb_log, "w") as lf:
                        lf.write(f"VPM Rollback Step Log\n{'─' * 60}\n")
                        lf.write(f"Step: {step.index + 1} — {step.label}\n")
                        lf.write(f"Rollback command:\n{step.rollback_command}\n{'─' * 60}\n\n")
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
                            UI.success("Rolled back")
                            summary_f.write(f"[OK] Rollback step {step.index + 1}: {step.label}\n")
                        else:
                            step.rollback_status = StepStatus.FAILED.value
                            UI.error(f"Rollback failed (exit {exit_code})")
                            summary_f.write(f"[FAIL] Rollback step {step.index + 1}: {step.label} (exit={exit_code})\n")

                except OSError as e:
                    step.rollback_status = StepStatus.FAILED.value
                    UI.error(f"Rollback error: {e}")
                    summary_f.write(f"[ERROR] Rollback step {step.index + 1}: {step.label} — {e}\n")

                self.lock.set_app(record)

            end_time = datetime.datetime.now()
            summary_f.write(f"\n{'=' * 60}\nFinished: {end_time.isoformat()}\n")
            summary_f.write(f"Duration: {(end_time - now).total_seconds():.1f}s\n{'=' * 60}\n")

        record.status = AppStatus.ROLLED_BACK.value
        self.lock.set_app(record)

        rb_ok = sum(1 for s in rollback_steps if s.rollback_status == StepStatus.SUCCESS.value)
        rb_fail = sum(1 for s in rollback_steps if s.rollback_status == StepStatus.FAILED.value)

        print()
        if rb_fail == 0:
            UI.success(f"Rollback complete: {rb_ok}/{len(rollback_steps)} steps rolled back.")
        else:
            UI.warning(f"Rollback partial: {rb_ok} succeeded, {rb_fail} failed.")
        UI.dim(f"Log: {summary_log}")

        return record

    def _pty_exec(
        self,
        shell_path: str,
        command: str,
        env: dict[str, str],
        log_fh,
    ) -> int:
        """
        Execute a command inside a PTY so interactive programs (debconf,
        ncurses config screens, sudo password prompts, etc.) work correctly.

        stdin/stdout of the real terminal are wired through to the child.
        All output is also tee'd into log_fh.
        """
        # Create PTY pair
        master_fd, slave_fd = pty.openpty()

        pid = os.fork()
        if pid == 0:
            # ── CHILD ────────────────────────────────────────────────
            os.close(master_fd)
            # Create a new session and set the slave as controlling terminal
            os.setsid()
            import fcntl
            import termios
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            # Redirect stdin/stdout/stderr to the slave PTY
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            os.execve(
                shell_path,
                [shell_path, "-e", "-c", command],
                env,
            )
            # execve never returns on success
            os._exit(127)

        # ── PARENT ────────────────────────────────────────────────────
        os.close(slave_fd)

        # If our stdin is a TTY, put it in raw mode so keystrokes
        # (arrow keys, tab, etc.) reach the child unmodified.
        stdin_fd = sys.stdin.fileno()
        stdin_is_tty = os.isatty(stdin_fd)
        old_tattr = None

        if stdin_is_tty:
            import termios
            import tty
            try:
                old_tattr = termios.tcgetattr(stdin_fd)
                tty.setraw(stdin_fd)
            except termios.error:
                old_tattr = None

        try:
            self._pty_copy_loop(master_fd, stdin_fd, stdin_is_tty, log_fh)
        finally:
            # Restore terminal no matter what
            if old_tattr is not None:
                import termios
                try:
                    termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, old_tattr)
                except termios.error:
                    pass
            os.close(master_fd)

        # Reap child
        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        return 1

    def _pty_copy_loop(
        self,
        master_fd: int,
        stdin_fd: int,
        stdin_is_tty: bool,
        log_fh,
    ):
        """
        Bidirectional copy between the real terminal and the PTY master.
        Also writes child output to the log file.
        """
        fds = [master_fd]
        if stdin_is_tty:
            fds.append(stdin_fd)

        while True:
            try:
                rfds, _, _ = select.select(fds, [], [], 0.1)
            except (select.error, ValueError):
                break

            if master_fd in rfds:
                try:
                    data = os.read(master_fd, 4096)
                except OSError as e:
                    if e.errno == errno.EIO:
                        # Child closed its side — normal at exit
                        break
                    raise
                if not data:
                    break
                # Write to real stdout (user sees interactive output)
                try:
                    os.write(sys.stdout.fileno(), data)
                except OSError:
                    pass
                # Tee to log file (strip ANSI later if needed, but keep raw for now)
                try:
                    log_fh.write(data.decode("utf-8", errors="replace"))
                    log_fh.flush()
                except (OSError, ValueError):
                    pass

            if stdin_is_tty and stdin_fd in rfds:
                try:
                    data = os.read(stdin_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                try:
                    os.write(master_fd, data)
                except OSError:
                    break
