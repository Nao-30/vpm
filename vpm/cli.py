"""CLI entry point: argument parser, bootstrap, and main dispatch."""

import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
import textwrap
import traceback
from pathlib import Path

from . import __version__
from .app import VPM
from .completions import Completions
from .config import Config
from .style import Style
from .ui import UI


# ── Additional VPM commands (setup, doctor, completions, version) ─────────

class _VPMExtended(VPM):
    """Extends VPM with setup, doctor, completions, and version commands."""

    # ── SETUP ─────────────────────────────────────────────────────────────

    def cmd_setup(self, args):
        """Install vpm to PATH."""
        UI.header("Setup VPM", UI.LINK)

        script_path = self.config.script_path

        if args.scope == "global":
            target_dir = self.config.bin_dir_global
            needs_sudo = True
        else:
            target_dir = self.config.bin_dir_user
            needs_sudo = False

        target = target_dir / "vpm"

        UI.info(f"Script location: {script_path}")
        UI.info(f"Symlink target: {target}")

        if needs_sudo:
            UI.warning("Global installation requires sudo.")

        if target.exists() or target.is_symlink():
            current = target.resolve() if target.is_symlink() else target
            UI.warning(f"vpm already exists at {target} -> {current}")
            if not UI.confirm("Overwrite?"):
                return

        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            if needs_sudo:
                subprocess.run(
                    ["sudo", "ln", "-sf", str(script_path), str(target)],
                    check=True,
                )
                subprocess.run(
                    ["sudo", "chmod", "+x", str(target)],
                    check=True,
                )
            else:
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(script_path)
                script_path.chmod(0o755)

            UI.success(f"Installed vpm to {target}")

            # Ensure target_dir is in PATH
            if not needs_sudo:
                shell_name = self._detect_shell()
                path_dirs = os.environ.get("PATH", "").split(":")
                if str(target_dir) not in path_dirs:
                    rc_file = self._get_shell_rc(shell_name)
                    if rc_file:
                        line = f'\nexport PATH="$HOME/.local/bin:$PATH"\n'
                        rc_content = rc_file.read_text() if rc_file.exists() else ""
                        if ".local/bin" not in rc_content:
                            with open(rc_file, "a") as f:
                                f.write(line)
                            UI.success(f"Added {target_dir} to PATH in {rc_file}")
                            UI.warning(f"Restart your shell or run: source {rc_file}")
                        else:
                            UI.info(f"{target_dir} already in {rc_file}")
                    else:
                        UI.warning(
                            f"Add to your PATH manually: export PATH=\"{target_dir}:$PATH\""
                        )

        except subprocess.CalledProcessError as e:
            UI.error(f"Failed to create symlink: {e}")
            sys.exit(1)

        # Auto-install completions
        if UI.confirm("Also install shell completions?", default=True):
            self.cmd_completions(argparse.Namespace(shell=None))

    # ── DOCTOR ────────────────────────────────────────────────────────────

    def cmd_doctor(self, args):
        """Diagnose and fix VPM environment."""
        UI.header("VPM Doctor", "🩺")

        checks = [
            ("Python version", self._check_python),
            ("VPM directories", self._check_dirs),
            ("Lock file integrity", self._check_lock),
            ("Shell detection", self._check_shell),
            ("PATH configuration", self._check_path),
            ("Sudo access", self._check_sudo),
            ("Required tools", self._check_tools),
        ]

        issues = []
        for name, check_fn in checks:
            try:
                ok, msg, fix = check_fn()
                if ok:
                    UI.success(f"{name}: {msg}")
                else:
                    UI.error(f"{name}: {msg}")
                    if fix:
                        issues.append((name, msg, fix))
            except Exception as e:
                UI.error(f"{name}: Exception — {e}")

        if issues:
            print()
            UI.sub_header("Suggested Fixes")
            for name, msg, fix in issues:
                print(f"  {Style.s(UI.ARROW, Style.YELLOW)} {name}")
                UI.dim(f"  {fix}")

            if UI.confirm("\nAttempt automatic fixes?"):
                for name, msg, fix in issues:
                    UI.info(f"Fixing: {name}")
                    try:
                        subprocess.run(fix, shell=True, check=True)
                        UI.success(f"Fixed: {name}")
                    except subprocess.CalledProcessError:
                        UI.error(f"Could not fix: {name}")
        else:
            print()
            UI.success("Everything looks good! 🎉")

    def _check_python(self):
        v = sys.version_info
        if v >= (3, 12):
            return True, f"Python {v.major}.{v.minor}.{v.micro}", None
        return False, f"Python {v.major}.{v.minor}.{v.micro} (3.12+ recommended)", \
            "sudo apt-get install -y python3.12 || sudo dnf install -y python3.12"

    def _check_dirs(self):
        dirs = [self.config.config_dir, self.config.data_dir, self.config.logs_dir]
        missing = [d for d in dirs if not d.exists()]
        if not missing:
            return True, "All directories exist", None
        self.config.ensure_dirs()
        return True, "Created missing directories", None

    def _check_lock(self):
        if not self.config.lock_file.exists():
            return True, "No lock file yet (fresh install)", None
        try:
            data = json.loads(self.config.lock_file.read_text())
            app_count = len(data.get("apps", {}))
            return True, f"Valid ({app_count} app(s) tracked)", None
        except json.JSONDecodeError:
            return False, "Corrupted", f"rm {self.config.lock_file}"

    def _check_shell(self):
        shell = self._detect_shell()
        return True, f"Detected: {shell}", None

    def _check_path(self):
        user_bin = str(self.config.bin_dir_user)
        path = os.environ.get("PATH", "")
        if user_bin in path:
            return True, f"{user_bin} in PATH", None
        return False, f"{user_bin} not in PATH", \
            f'echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.{self._detect_shell()}rc'

    def _check_sudo(self):
        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return True, "Passwordless sudo available", None
            return True, "Sudo available (password required)", None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Sudo not available", None

    def _check_tools(self):
        required = ["bash", "curl", "wget", "git"]
        missing = []
        for tool in required:
            if not shutil.which(tool):
                missing.append(tool)
        if not missing:
            return True, f"All present ({', '.join(required)})", None
        return False, f"Missing: {', '.join(missing)}", \
            f"sudo apt-get install -y {' '.join(missing)}"

    # ── COMPLETIONS ───────────────────────────────────────────────────────

    def cmd_completions(self, args):
        """Generate and install shell completions."""
        UI.header("Shell Completions", UI.GEAR)

        target_shell = args.shell or self._detect_shell()
        UI.info(f"Detected shell: {target_shell}")

        generators = {
            "zsh": (Completions.zsh_completion, "_vpm"),
            "bash": (Completions.bash_completion, "vpm.bash"),
            "fish": (Completions.fish_completion, "vpm.fish"),
        }

        if target_shell not in generators:
            UI.warning(f"Unsupported shell: {target_shell}")
            UI.info(f"Supported: {', '.join(generators.keys())}")
            return

        gen_fn, filename = generators[target_shell]
        content = gen_fn()

        # Save to vpm completions dir
        comp_file = self.config.completions_dir / filename
        comp_file.write_text(content)
        comp_file.chmod(0o644)
        UI.success(f"Generated: {comp_file}")

        # Install to shell-specific location
        installed = False
        if target_shell == "zsh":
            zshrc = Path.home() / ".zshrc"
            target_dir = Path.home() / ".zsh" / "completions"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            shutil.copy2(comp_file, target)
            target.chmod(0o644)
            UI.success(f"Installed to: {target}")

            if zshrc.exists():
                rc_content = zshrc.read_text()
                if str(target_dir) not in rc_content:
                    with open(zshrc, "a") as f:
                        f.write(f"\n# VPM completions\n")
                        f.write(f"fpath=({target_dir} $fpath)\n")
                        f.write(f"autoload -Uz compinit && compinit\n")
                    UI.success(f"Added fpath to {zshrc}")
                else:
                    UI.info(f"Completion path already in {zshrc}")
            installed = True

        elif target_shell == "bash":
            bash_comp_dir = Path.home() / ".local" / "share" / "bash-completion" / "completions"
            bash_comp_dir.mkdir(parents=True, exist_ok=True)
            target = bash_comp_dir / "vpm"
            shutil.copy2(comp_file, target)
            target.chmod(0o644)
            UI.success(f"Installed to: {target}")

            bashrc = Path.home() / ".bashrc"
            if bashrc.exists():
                rc_content = bashrc.read_text()
                if str(comp_file) not in rc_content and "vpm" not in rc_content:
                    with open(bashrc, "a") as f:
                        f.write(f"\n# VPM completions\n")
                        f.write(f"[ -f {comp_file} ] && source {comp_file}\n")
                    UI.success(f"Added source to {bashrc}")
            installed = True

        elif target_shell == "fish":
            fish_comp_dir = Path.home() / ".config" / "fish" / "completions"
            fish_comp_dir.mkdir(parents=True, exist_ok=True)
            target = fish_comp_dir / "vpm.fish"
            shutil.copy2(comp_file, target)
            target.chmod(0o644)
            UI.success(f"Installed to: {target}")
            installed = True

        if installed:
            UI.info("Restart your shell or source the config to activate completions.")
        else:
            UI.info(f"Manual setup: source {comp_file}")

    # ── VERSION ───────────────────────────────────────────────────────────

    def cmd_version(self, args):
        """Show version information."""
        UI.banner()
        print()
        UI.info(f"Version:  {__version__}")
        UI.info(f"Python:   {sys.version.split()[0]}")
        UI.info(f"Platform: {__import__('platform').platform()}")
        UI.info(f"Config:   {self.config.config_dir}")
        UI.info(f"Data:     {self.config.data_dir}")
        UI.info(f"Logs:     {self.config.logs_dir}")
        UI.info(f"Lock:     {self.config.lock_file}")
        UI.info(f"Script:   {self.config.script_path}")

    # ── HELPERS ───────────────────────────────────────────────────────────

    @staticmethod
    def _detect_shell() -> str:
        """Detect the current user's shell."""
        shell_env = os.environ.get("SHELL", "")
        shell_name = Path(shell_env).name if shell_env else ""

        if shell_name in ("zsh", "bash", "fish"):
            return shell_name

        try:
            user = pwd.getpwuid(os.getuid())
            login_shell = Path(user.pw_shell).name
            if login_shell in ("zsh", "bash", "fish"):
                return login_shell
        except (KeyError, AttributeError):
            pass

        if shutil.which("zsh"):
            return "zsh"
        if shutil.which("bash"):
            return "bash"
        return "bash"

    @classmethod
    def _get_shell_rc(cls, shell: str) -> Path | None:
        """Get the RC file path for a given shell."""
        home = Path.home()
        rc_files = {
            "zsh": home / ".zshrc",
            "bash": home / ".bashrc",
            "fish": home / ".config" / "fish" / "config.fish",
        }
        return rc_files.get(shell)


# ─────────────────────────────────────────────────────────────────────────────
# Self-Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def self_bootstrap():
    """Check Python version and dependencies, offer to fix if needed."""
    v = sys.version_info
    if v < (3, 10):
        print(f"\n⚠  VPM requires Python 3.10+ (you have {v.major}.{v.minor}.{v.micro})")
        print()
        print("To install Python 3.12:")
        print()

        if shutil.which("apt-get"):
            print("  sudo apt-get update && sudo apt-get install -y python3.12")
        elif shutil.which("dnf"):
            print("  sudo dnf install -y python3.12")
        elif shutil.which("yum"):
            print("  sudo yum install -y python3.12")
        elif shutil.which("pacman"):
            print("  sudo pacman -S python")
        elif shutil.which("brew"):
            print("  brew install python@3.12")
        else:
            print("  Please install Python 3.12+ from https://www.python.org/downloads/")

        print()
        print("Then re-run this script with: python3.12 " + " ".join(sys.argv))
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Argument Parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all commands and options."""
    parser = argparse.ArgumentParser(
        prog="vpm",
        description=Style.s(
            "VPM — Virtual Package Manager\n"
            "Robust script orchestration for your VPS",
            Style.BOLD
        ) if Style.enabled() else "VPM — Virtual Package Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              vpm init                          Create manifest template in current directory
              vpm init /path/to/project         Create manifest in specific directory
              vpm install                       Install all apps from manifest
              vpm install --file manifest.yaml  Use specific manifest file
              vpm install docker node_js        Install specific apps only
              vpm install --dry-run             Preview what would be executed
              vpm status                        Show all tracked installations
              vpm status docker                 Show detailed status for docker
              vpm logs docker                   List log files for docker
              vpm logs docker --latest          Show latest summary log
              vpm retry docker                  Retry from failed step
              vpm reset docker                  Reset tracking (allows fresh install)
              vpm reset --all                   Reset everything
              vpm setup --user                  Install vpm to ~/.local/bin
              vpm setup --global                Install vpm to /usr/local/bin (sudo)
              vpm doctor                        Check environment and fix issues
              vpm completions                   Install shell completions
              vpm completions --shell zsh       Install for specific shell
        """),
    )

    parser.add_argument(
        "--no-color", action="store_true",
        help="Disable colored output",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # init
    p_init = subparsers.add_parser(
        "init",
        help="Initialize a new VPM workspace with manifest template",
        description="Create a vpm-manifest.yaml template file with examples and documentation.",
    )
    p_init.add_argument(
        "path", nargs="?", default=None,
        help="Directory to create the manifest in (default: current directory)",
    )
    p_init.add_argument(
        "--force", "-f", action="store_true",
        help="Overwrite existing manifest without prompting",
    )

    # install
    p_install = subparsers.add_parser(
        "install",
        help="Install apps from manifest file",
        description="Execute installation steps for apps defined in a manifest file. "
                     "Tracks progress and supports resume on failure.",
    )
    p_install.add_argument(
        "apps", nargs="*", metavar="APP",
        help="Specific app name(s) to install (default: all)",
    )
    p_install.add_argument(
        "--file", "-f", metavar="FILE",
        help="Path to manifest file (default: auto-discover)",
    )
    p_install.add_argument(
        "--force", action="store_true",
        help="Force reinstallation even if already completed",
    )
    p_install.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be done without executing anything",
    )
    p_install.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip confirmation prompts",
    )

    # status
    p_status = subparsers.add_parser(
        "status",
        help="Show installation status of tracked apps",
    )
    p_status.add_argument(
        "app", nargs="?",
        help="Show detailed status for a specific app",
    )

    # list
    subparsers.add_parser(
        "list",
        help="List all managed apps (alias for status)",
    )

    # logs
    p_logs = subparsers.add_parser(
        "logs",
        help="View logs for an app",
        description="Browse and view execution logs.",
    )
    p_logs.add_argument("app", nargs="?", help="App name")
    p_logs.add_argument(
        "--step", "-s", type=int, metavar="N",
        help="Show log for specific step (0-indexed)",
    )
    p_logs.add_argument(
        "--follow", "-f", action="store_true",
        help="Follow the latest log file (like tail -f)",
    )
    p_logs.add_argument(
        "--latest", "-l", action="store_true",
        help="Display content of the latest summary log",
    )

    # retry
    p_retry = subparsers.add_parser(
        "retry",
        help="Retry failed app installation from point of failure",
    )
    p_retry.add_argument("app", help="App name to retry")

    # reset
    p_reset = subparsers.add_parser(
        "reset",
        help="Reset tracking for an app (allows fresh reinstallation)",
    )
    p_reset.add_argument("app", nargs="?", help="App name to reset")
    p_reset.add_argument(
        "--all", action="store_true",
        help="Reset tracking for all apps",
    )
    p_reset.add_argument(
        "--clean-logs", action="store_true",
        help="Also delete log files",
    )

    # setup
    p_setup = subparsers.add_parser(
        "setup",
        help="Install vpm to PATH for global access",
    )
    scope = p_setup.add_mutually_exclusive_group()
    scope.add_argument(
        "--global", dest="scope", action="store_const", const="global",
        help="Install to /usr/local/bin (requires sudo)",
    )
    scope.add_argument(
        "--user", dest="scope", action="store_const", const="user",
        help="Install to ~/.local/bin (default)",
    )
    p_setup.set_defaults(scope="user")

    # doctor
    subparsers.add_parser(
        "doctor",
        help="Self-diagnose dependencies and fix issues",
    )

    # completions
    p_comp = subparsers.add_parser(
        "completions",
        help="Generate and install shell completions",
    )
    p_comp.add_argument(
        "--shell", choices=["zsh", "bash", "fish"],
        help="Target shell (default: auto-detect)",
    )

    # version
    subparsers.add_parser(
        "version",
        help="Show version and environment information",
    )

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main entry point for VPM."""
    self_bootstrap()

    parser = build_parser()
    args = parser.parse_args()

    if args.no_color:
        Style._force_no_color = True

    if not args.command:
        UI.banner()
        print()
        parser.print_help()
        sys.exit(0)

    try:
        vpm = _VPMExtended()

        dispatch = {
            "init": vpm.cmd_init,
            "install": vpm.cmd_install,
            "status": vpm.cmd_status,
            "list": vpm.cmd_list,
            "logs": vpm.cmd_logs,
            "retry": vpm.cmd_retry,
            "reset": vpm.cmd_reset,
            "setup": vpm.cmd_setup,
            "doctor": vpm.cmd_doctor,
            "completions": vpm.cmd_completions,
            "version": vpm.cmd_version,
        }

        handler = dispatch.get(args.command)
        if handler:
            handler(args)
        else:
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        print()
        UI.warning("Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print()
        UI.error(f"Unexpected error: {e}")
        UI.dim(traceback.format_exc())
        UI.info("Run 'vpm doctor' to diagnose issues.")
        sys.exit(1)
