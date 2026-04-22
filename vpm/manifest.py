"""Manifest file parser and data model."""

import re
import textwrap
from pathlib import Path


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


class ManifestParser:
    """
    Parses VPM manifest files.

    Manifest format (YAML-like but parsed manually to avoid PyYAML dependency):

    ```
    # VPM Manifest File
    # Format:
    #
    # [app_name] Optional Description
    # - label: Step Label
    #   run: command to execute
    #   run: |
    #     multiline
    #     command
    # - label: Another Step
    #   run: another command
    #
    # [another_app]
    # - run: simple command (label auto-generated)
    ```
    """

    @classmethod
    def parse_file(cls, filepath: Path) -> list[ManifestApp]:
        if not filepath.exists():
            raise FileNotFoundError(f"Manifest file not found: {filepath}")

        content = filepath.read_text()
        return cls.parse_string(content)

    @classmethod
    def parse_string(cls, content: str) -> list[ManifestApp]:
        apps: list[ManifestApp] = []
        current_app_name: str | None = None
        current_app_desc: str = ""
        current_steps: list[dict[str, str]] = []
        current_step: dict[str, str] | None = None
        current_requires: list[str] = []
        in_multiline = False
        multiline_indent = 0
        multiline_lines: list[str] = []
        multiline_target = "command"  # "command" or "rollback"

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines and comments (but not inside multiline)
            if in_multiline:
                # Check if this line is a step-level key (label/run/rollback) — ends multiline
                step_key_match = re.match(r"^\s+(label|run|rollback):\s*(.*)", line, re.IGNORECASE) if line else None
                # Check if this line is still part of the multiline block
                if step_key_match or (line and not line[0].isspace() and stripped and not stripped.startswith("#")):
                    # End of multiline
                    if current_step is not None:
                        if multiline_target == "rollback":
                            current_step["rollback"] = "\n".join(multiline_lines).strip()
                        else:
                            current_step["command"] = "\n".join(multiline_lines).strip()
                    in_multiline = False
                    multiline_lines = []
                    # Don't increment i, re-process this line
                    continue
                elif not stripped:
                    # Empty line might be part of multiline or a separator
                    # Check next non-empty line
                    multiline_lines.append("")
                    i += 1
                    continue
                else:
                    # Part of multiline content
                    # Remove common indent
                    dedented = line
                    if len(line) > multiline_indent:
                        dedented = line[multiline_indent:]
                    elif line.strip():
                        dedented = line.lstrip()
                    multiline_lines.append(dedented)
                    i += 1
                    continue

            if not stripped or stripped.startswith("#"):
                i += 1
                continue

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

            # Step definition: - label: ..., or - run: ...
            step_match = re.match(r"^-\s+(.*)", stripped)
            if step_match and current_app_name is not None:
                # Save previous step
                if current_step is not None:
                    current_steps.append(current_step)

                rest = step_match.group(1).strip()
                current_step = {"label": "", "command": ""}

                # Check for label: or run: or rollback:
                kv = re.match(r"^(label|run|rollback):\s*(.*)", rest, re.IGNORECASE)
                if kv:
                    key = kv.group(1).lower()
                    val = kv.group(2).strip()
                    if key == "label":
                        current_step["label"] = val
                    elif key == "run":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                            multiline_target = "command"
                        else:
                            current_step["command"] = val
                    elif key == "rollback":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                            multiline_target = "rollback"
                        else:
                            current_step["rollback"] = val
                else:
                    # Simple format: - command here
                    current_step["command"] = rest
                    current_step["label"] = rest[:60]

                i += 1
                continue

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

            # Continuation keys (label:, run:, or rollback:) for current step
            if current_step is not None:
                kv = re.match(r"^\s+(label|run|rollback):\s*(.*)", line)
                if kv:
                    key = kv.group(1).lower()
                    val = kv.group(2).strip()
                    if key == "label":
                        current_step["label"] = val
                    elif key == "run":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                            multiline_target = "command"
                        else:
                            current_step["command"] = val
                    elif key == "rollback":
                        if val == "|":
                            in_multiline = True
                            multiline_indent = len(line) - len(line.lstrip()) + 2
                            multiline_lines = []
                            multiline_target = "rollback"
                        else:
                            current_step["rollback"] = val
                    i += 1
                    continue

            i += 1

        # Finalize multiline if still open
        if in_multiline and current_step is not None:
            if multiline_target == "rollback":
                current_step["rollback"] = "\n".join(multiline_lines).strip()
            else:
                current_step["command"] = "\n".join(multiline_lines).strip()

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

        # Auto-label steps that have no label
        for app in apps:
            for idx, step in enumerate(app.steps):
                if not step.get("label"):
                    cmd_preview = step.get("command", "")[:50]
                    step["label"] = f"Step {idx + 1}: {cmd_preview}"

        return apps

    @classmethod
    def generate_template(cls) -> str:
        return textwrap.dedent("""\
            # ═══════════════════════════════════════════════════════════════
            # VPM Manifest File
            # ═══════════════════════════════════════════════════════════════
            #
            # This file defines apps and their installation steps.
            # VPM will execute each step in order, tracking progress
            # so that interrupted installations can be safely resumed.
            #
            # ─── FORMAT ───────────────────────────────────────────────────
            #
            # [app_name] Optional description of the app
            # - label: Human readable step name
            #   run: shell command to execute
            #
            # - label: Multi-line command example
            #   run: |
            #     first line
            #     second line
            #     third line
            #
            # - run: simple one-liner (label auto-generated)
            #
            # ─── NOTES ────────────────────────────────────────────────────
            #
            # • Commands run with the current user's shell (bash -e)
            # • Use sudo where needed (user must have sudo access)
            # • Each step is tracked independently
            # • If a step fails, subsequent steps are skipped
            # • Use `vpm retry <app>` to retry from the failed step
            # • Use `vpm reset <app>` to start fresh
            # • Environment variables are inherited from current shell
            # • Use 'requires: app1, app2' to declare dependencies
            # • Dependencies are resolved automatically — install order is computed
            # • If a dependency fails, dependent apps are skipped
            #
            # ─── EXAMPLES ─────────────────────────────────────────────────

            [essential_tools] Essential system utilities
            - label: Update package lists
              run: sudo apt-get update -y

            - label: Install core utilities
              run: sudo apt-get install -y curl wget git htop vim unzip jq tree

            - label: Install network tools
              run: sudo apt-get install -y net-tools dnsutils mtr-tiny

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

            # [node_js] Node.js via NVM
            # - label: Install NVM
            #   run: |
            #     curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
            #     export NVM_DIR="$HOME/.nvm"
            #     [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
            #
            # - label: Install Node.js LTS
            #   run: |
            #     export NVM_DIR="$HOME/.nvm"
            #     [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
            #     nvm install --lts
            #     nvm use --lts
            #     node --version && npm --version
        """)
