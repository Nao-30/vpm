These are significant changes concentrated in a few areas. I'll give you surgical replacements:

## Change 1: Add PTY-based execution (replaces the `_run_step` method entirely)

Add this import at the top of the file with the other imports:

```python
import pty
import select
import errno
```

Now replace the **entire `_run_step` method** in the `Executor` class with this:

```python
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
                lf.write(f"VPM Step Execution Log\n")
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
                # DO NOT force noninteractive — let debconf/ncurses work
                # Only set if user hasn't explicitly set it
                # env.setdefault("DEBIAN_FRONTEND", "noninteractive")

                # Use PTY so that interactive programs (debconf, ncurses menus,
                # passwd prompts, etc.) work correctly.  We sit in the middle:
                # the child thinks it has a real terminal, we copy bytes between
                # the real stdin/stdout and the child, AND tee everything to the
                # log file.

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
```

## Change 2: Add dependency support to the manifest parser

Replace the **`ManifestApp` class** with:

```python
class ManifestApp:
    """Represents an app parsed from the manifest file."""

    def __init__(
        self,
        name: str,
        steps: list[dict[str, str]],
        description: str = "",
        requires: list[str] | None = None,
    ):
        self.name = name
        self.steps = steps  # [{"label": "...", "command": "..."}, ...]
        self.description = description
        self.requires = requires or []  # list of app names this depends on
```

Now in the **`ManifestParser.parse_string` classmethod**, find this block:

```python
            # App header: [app_name] optional description
            app_match = re.match(r"^\[([^\]]+)\]\s*(.*)?$", stripped)
            if app_match:
                # Save previous app
                if current_app_name is not None:
                    if current_step is not None:
                        current_steps.append(current_step)
                    if current_steps:
                        apps.append(
                            ManifestApp(current_app_name, current_steps, current_app_desc)
                        )

                current_app_name = app_match.group(1).strip()
                current_app_desc = (app_match.group(2) or "").strip()
                current_steps = []
                current_step = None
                i += 1
                continue
```

**Replace it with:**

```python
            # App header: [app_name] optional description
            app_match = re.match(r"^\[([^\]]+)\]\s*(.*)?$", stripped)
            if app_match:
                # Save previous app
                if current_app_name is not None:
                    if current_step is not None:
                        current_steps.append(current_step)
                    if current_steps:
                        apps.append(
                            ManifestApp(
                                current_app_name,
                                current_steps,
                                current_app_desc,
                                current_requires,
                            )
                        )

                current_app_name = app_match.group(1).strip()
                current_app_desc = (app_match.group(2) or "").strip()
                current_steps = []
                current_step = None
                current_requires = []
                i += 1
                continue
```

Now find this block (the continuation keys handling):

```python
            # Continuation keys (label: or run:) for current step
            if current_step is not None:
                kv = re.match(r"^\s+(label|run):\s*(.*)", line)
```

**Replace it with:**

```python
            # Top-level app directive: requires
            if current_app_name is not None and current_step is None:
                req_match = re.match(r"^\s*requires:\s*(.*)", stripped, re.IGNORECASE)
                if req_match:
                    deps = [
                        d.strip()
                        for d in req_match.group(1).split(",")
                        if d.strip()
                    ]
                    current_requires.extend(deps)
                    i += 1
                    continue

            # Continuation keys (label: or run:) for current step
            if current_step is not None:
                kv = re.match(r"^\s+(label|run):\s*(.*)", line)
```

Now find the end-of-method finalization block:

```python
        # Save last step and app
        if current_step is not None:
            current_steps.append(current_step)
        if current_app_name is not None and current_steps:
            apps.append(ManifestApp(current_app_name, current_steps, current_app_desc))
```

**Replace with:**

```python
        # Save last step and app
        if current_step is not None:
            current_steps.append(current_step)
        if current_app_name is not None and current_steps:
            apps.append(
                ManifestApp(
                    current_app_name,
                    current_steps,
                    current_app_desc,
                    current_requires if 'current_requires' in dir() else [],
                )
            )
```

Now add this initialization near the top of `parse_string`, right after `current_step: dict[str, str] | None = None`:

```python
        current_requires: list[str] = []
```

## Change 3: Dependency resolution in the executor

Add this **new method to the `Executor` class**, right before `execute_app`:

```python
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
```

## Change 4: Wire dependency resolution into `cmd_install`

In the **`cmd_install` method**, find this block (it's right before the dry run check):

```python
        if not apps_to_install:
            UI.warning("No apps to install.")
            return

        # Dry run
        if args.dry_run:
```

**Replace with:**

```python
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

        # Dry run
        if args.dry_run:
```

Now find the execution loop in `cmd_install`:

```python
        # Execute
        results: list[AppRecord] = []
        for i, app in enumerate(apps_to_install):
            if self.executor._interrupted:
                UI.warning("Installation interrupted. Remaining apps skipped.")
                break
            result = self.executor.execute_app(app, force=args.force)
            results.append(result)
```

**Replace with:**

```python
        # Execute with dependency checks
        results: list[AppRecord] = []
        skipped_due_to_dep: list[str] = []
        for i, app in enumerate(apps_to_install):
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
                    skipped_due_to_dep.append(app.name)
                    break

            if dep_failed:
                # Create a record marking it as failed due to deps
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

            result = self.executor.execute_app(app, force=args.force)
            results.append(result)
```

## Change 5: Update the manifest template

In **`ManifestParser.generate_template`**, find the `[docker]` section and **replace it with:**

```python
            [docker] Docker Engine & Compose
            requires: essential_tools

            - label: Install prerequisites
              run: sudo apt-get install -y ca-certificates curl gnupg lsb-release

            - label: Add Docker GPG key
              run: |
                sudo install -m 0755 -d /etc/apt/keyrings
                curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \\
                  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
                sudo chmod a+r /etc/apt/keyrings/docker.gpg

            - label: Add Docker repository
              run: |
                echo "deb [arch=$(dpkg --print-architecture) \\
                  signed-by=/etc/apt/keyrings/docker.gpg] \\
                  https://download.docker.com/linux/ubuntu \\
                  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \\
                  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

            - label: Install Docker Engine
              run: |
                sudo apt-get update -y
                sudo apt-get install -y docker-ce docker-ce-cli \\
                  containerd.io docker-buildx-plugin docker-compose-plugin

            - label: Add current user to docker group
              run: sudo usermod -aG docker $USER

            - label: Verify Docker installation
              run: docker --version && docker compose version
```

And add this to the comments section at the top of the template, after the `# • Environment variables are inherited from current shell` line:

```python
            # • Use 'requires: app1, app2' to declare dependencies
            # • Dependencies are resolved automatically — install order is computed
            # • If a dependency fails, dependent apps are skipped
```

## Change 6: Store requires in the lock file

In the **`AppRecord` dataclass**, add this field after `manifest_source`:

```python
    requires: list[str] = field(default_factory=list)
```

Then in the **`execute_app` method** of `Executor`, find where the fresh record is built:

```python
            record = AppRecord(
                name=app.name,
                display_name=app.name,
                steps=steps,
                log_dir=str(app_log_dir),
                created_at=now.isoformat(),
            )
            if app.description:
                record.display_name = f"{app.name} ({app.description})"
```

**Replace with:**

```python
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
```
