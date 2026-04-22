# Manifest Format

## The Manifest File

The manifest file (`vpm-manifest.yaml`) is where you define what to install and how. It uses a simple, human-readable format that does **not** require a YAML parser — VPM parses it with its own lightweight parser.

### Structure Overview

```
# Comments start with #

[app_name] Optional human-readable description
requires: dependency1, dependency2

- label: What this step does
  run: shell command to execute

- label: Another step
  run: |
    multi-line
    shell command

- run: simple command without explicit label
```

### App Header

An app is defined by a header line enclosed in square brackets:

```
[my_app] This is my application
```

- `my_app` — The app identifier. Used in commands like `vpm install my_app`, `vpm retry my_app`, etc.
- Everything after `]` is an optional description shown in status output.
- App names are normalized internally: lowercased, special characters replaced with `_`.
- App names must be unique within a manifest.

### Dependencies

Declared on a line after the app header, before any steps:

```
[web_server] Nginx + Certbot
requires: base_packages, firewall_setup
```

- Comma-separated list of app names.
- Dependencies must either be defined in the same manifest or already successfully installed from a previous run.
- VPM topologically sorts apps so dependencies always execute first.
- If a dependency fails, all apps that depend on it are automatically skipped.

### Steps

Each step is a shell command to execute:

```
- label: Install Nginx
  run: sudo apt-get install -y nginx
```

- `label` — Human-readable name shown in terminal output and logs. If omitted, auto-generated from the command.
- `run` — The shell command to execute. Runs with `bash -e` (exits on first error).
- Steps execute in order within an app.
- If a step fails (non-zero exit code), all subsequent steps in that app are skipped.
- On re-run, successfully completed steps are skipped automatically.

#### Shorthand (no label)

```
- sudo apt-get install -y nginx
```

When only a command is provided without `label:` or `run:` keys, VPM treats the entire line after `- ` as the command and auto-generates a label from it.

### Multi-line Commands

Use the pipe `|` character after `run:` to start a multi-line block:

```
- label: Configure firewall
  run: |
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw allow http
    sudo ufw allow https
    sudo ufw --force enable
```

- All indented lines following `run: |` are joined with newlines.
- The block ends when a line at the same or lesser indentation level appears (or at end of file).
- The entire block runs as a single `bash -e` invocation — if any line fails, execution stops.

#### Line Continuation

For long single commands, use backslash continuation inside multi-line blocks:

```
- label: Add Docker repository
  run: |
    echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### Comments

Lines starting with `#` are ignored everywhere:

```
# This entire app is disabled for now
# [experimental_stuff]
# - run: something risky

[active_app]
# This step is temporarily skipped
# - run: do something optional
- run: do something important
```

### Complete Manifest Example

```
# ═══════════════════════════════════════════════════════
# Server Setup Manifest
# ═══════════════════════════════════════════════════════

[system_base] Core system packages and configuration
- label: Update package lists
  run: sudo apt-get update -y

- label: Upgrade existing packages
  run: sudo apt-get upgrade -y

- label: Install essential tools
  run: |
    sudo apt-get install -y \
      curl wget git htop vim unzip jq tree \
      net-tools dnsutils mtr-tiny \
      build-essential software-properties-common

- label: Set timezone
  run: sudo timedatectl set-timezone UTC

- label: Configure automatic security updates
  run: |
    sudo apt-get install -y unattended-upgrades
    sudo dpkg-reconfigure -plow unattended-upgrades

[firewall] UFW Firewall Configuration
requires: system_base

- label: Install UFW
  run: sudo apt-get install -y ufw

- label: Configure firewall rules
  run: |
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw --force enable

- label: Verify firewall status
  run: sudo ufw status verbose

[docker] Docker Engine
requires: system_base

- label: Install prerequisites
  run: sudo apt-get install -y ca-certificates curl gnupg lsb-release

- label: Add Docker GPG key and repository
  run: |
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

- label: Install Docker Engine
  run: |
    sudo apt-get update -y
    sudo apt-get install -y \
      docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin

- label: Add current user to docker group
  run: sudo usermod -aG docker $USER

- label: Verify installation
  run: sudo docker run --rm hello-world

[app_deployment] Deploy Application Stack
requires: docker, firewall

- label: Create application directory
  run: mkdir -p ~/apps/myapp

- label: Clone repository
  run: git clone https://github.com/example/myapp.git ~/apps/myapp

- label: Start services
  run: |
    cd ~/apps/myapp
    docker compose up -d

- label: Verify services are running
  run: docker compose -f ~/apps/myapp/docker-compose.yml ps
```

---
