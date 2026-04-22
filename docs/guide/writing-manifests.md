# Writing Manifests — Best Practices

## Writing Manifests — Guidelines for AI Agents

This section is specifically for AI assistants generating VPM manifest files. Follow these rules precisely.

### Rules

1. **Format**: Use the VPM manifest format (described above), NOT standard YAML.
   - App headers use `[square_brackets]`
   - Steps start with `- `
   - Multi-line commands use `run: |` followed by indented lines
   - No YAML anchors, no YAML lists with `- key: value` nesting beyond what's described

2. **App names**: Use `snake_case` identifiers. No spaces, no special characters.
   - Good: `[docker_engine]`, `[node_js]`, `[my_web_app]`
   - Bad: `[Docker Engine]`, `[my-web-app]`, `[MyWebApp]`

3. **Every step must have a descriptive `label`**. Do not rely on auto-generated labels.

4. **Each step should be idempotent when possible**. If a step runs twice, it should not break things.
   - Use `apt-get install -y` (the `-y` and the fact that apt skips already-installed packages makes it idempotent)
   - Use `mkdir -p` instead of `mkdir`
   - Use `gpg --dearmor -o ... --yes` to overwrite existing files
   - Use `ln -sf` instead of `ln -s`
   - Check before creating: `id -u username &>/dev/null || useradd username`

5. **Group related commands into logical steps**. Don't make every single command its own step, but don't put 50 commands in one step either.
   - Good: "Install Docker prerequisites" (one step with 3 apt packages)
   - Bad: Separate steps for each `apt-get install` of related packages
   - Bad: One giant step that does everything

6. **Use `requires:` for dependencies between apps**. If App B needs something App A installs, declare it.

7. **Never use `cd` as a separate step**. It runs in a subshell and won't persist. Use it within a multi-line block:
   ```
   - label: Build the project
     run: |
       cd /path/to/project
       make build
       make install
   ```

8. **Use `sudo` explicitly** where needed. VPM runs as the current user.

9. **Do not set `DEBIAN_FRONTEND=noninteractive`** unless the user specifically asks for unattended installation. VPM supports interactive `debconf` screens.

10. **If a command might already be done** (like adding a repo that might exist), handle it gracefully:
    ```
    run: |
      if ! grep -q "some-repo" /etc/apt/sources.list.d/*; then
        sudo add-apt-repository -y ppa:some/repo
      fi
    ```

11. **Always include a verification step** as the last step of each app when possible:
    ```
    - label: Verify Docker installation
      run: docker --version && docker compose version
    ```

12. **Use absolute paths or `$HOME`** instead of `~` in commands (tilde expansion is unreliable in non-interactive shells):
    ```
    # Good
    run: mkdir -p $HOME/apps

    # Avoid
    run: mkdir -p ~/apps
    ```

13. **For services that need to be enabled/started**, combine into one step:
    ```
    - label: Enable and start Nginx
      run: |
        sudo systemctl enable nginx
        sudo systemctl start nginx
        sudo systemctl status nginx --no-pager
    ```

### Best Practices

#### Ordering Apps by Dependency

Always declare dependencies explicitly rather than relying on file order:

```
[system_updates]
- label: Update system
  run: sudo apt-get update -y && sudo apt-get upgrade -y

[build_tools]
requires: system_updates
- label: Install build essentials
  run: sudo apt-get install -y build-essential gcc g++ make

[node_js]
requires: build_tools
- label: Install Node.js via NVM
  run: |
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm install --lts
```

#### Sourcing Profile in Multi-Step Installs

When installing something that modifies `PATH` or shell environment (like NVM, RVM, cargo), you must re-source it in subsequent steps because each step runs in a fresh shell:

```
[rust]
- label: Install Rustup
  run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

- label: Verify Rust installation
  run: |
    source $HOME/.cargo/env
    rustc --version
    cargo --version
```

#### Handling Services That Need Restart

```
[nginx_config]
requires: nginx

- label: Copy configuration
  run: sudo cp /path/to/nginx.conf /etc/nginx/nginx.conf

- label: Test configuration
  run: sudo nginx -t

- label: Reload Nginx
  run: sudo systemctl reload nginx
```

#### Creating Users and Setting Permissions

```
[app_user]
- label: Create application user
  run: |
    id -u appuser &>/dev/null || sudo useradd -m -s /bin/bash appuser
    sudo mkdir -p /opt/myapp
    sudo chown appuser:appuser /opt/myapp
```

### Common Patterns

#### Pattern: Repository + Package Install

```
[custom_repo_app]
- label: Add GPG key
  run: |
    curl -fsSL https://example.com/gpg.key | \
      sudo gpg --dearmor -o /etc/apt/keyrings/example.gpg --yes

- label: Add repository
  run: |
    echo "deb [signed-by=/etc/apt/keyrings/example.gpg] \
      https://packages.example.com/deb stable main" | \
      sudo tee /etc/apt/sources.list.d/example.list > /dev/null

- label: Install package
  run: |
    sudo apt-get update -y
    sudo apt-get install -y example-package

- label: Verify
  run: example-package --version
```

#### Pattern: Download + Extract + Install Binary

```
[binary_tool]
- label: Download latest release
  run: |
    LATEST=$(curl -s https://api.github.com/repos/org/tool/releases/latest | jq -r .tag_name)
    curl -fsSL "https://github.com/org/tool/releases/download/${LATEST}/tool-linux-amd64.tar.gz" \
      -o /tmp/tool.tar.gz

- label: Extract and install
  run: |
    tar xzf /tmp/tool.tar.gz -C /tmp/
    sudo mv /tmp/tool /usr/local/bin/tool
    sudo chmod +x /usr/local/bin/tool
    rm /tmp/tool.tar.gz

- label: Verify
  run: tool version
```

#### Pattern: Clone + Build from Source

```
[from_source]
requires: build_tools

- label: Clone repository
  run: |
    rm -rf /tmp/project-build
    git clone --depth 1 https://github.com/org/project.git /tmp/project-build

- label: Build
  run: |
    cd /tmp/project-build
    ./configure --prefix=/usr/local
    make -j$(nproc)

- label: Install
  run: |
    cd /tmp/project-build
    sudo make install

- label: Clean up build files
  run: rm -rf /tmp/project-build

- label: Verify
  run: project --version
```

#### Pattern: Docker Compose Application

```
[my_app]
requires: docker

- label: Create app directory
  run: mkdir -p $HOME/apps/myapp

- label: Create docker-compose.yml
  run: |
    cat > $HOME/apps/myapp/docker-compose.yml << 'EOF'
    version: "3.8"
    services:
      web:
        image: nginx:alpine
        ports:
          - "80:80"
        restart: unless-stopped
      db:
        image: postgres:16-alpine
        environment:
          POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
        volumes:
          - pgdata:/var/lib/postgresql/data
        restart: unless-stopped
    volumes:
      pgdata:
    EOF

- label: Start services
  run: |
    cd $HOME/apps/myapp
    docker compose up -d

- label: Verify services
  run: |
    cd $HOME/apps/myapp
    docker compose ps
    sleep 3
    curl -sf http://localhost:80 > /dev/null && echo "Web server responding"
```

### Anti-Patterns

**DON'T: Use separate steps for trivially related commands**
```
# Bad — too granular
- run: sudo apt-get update
- run: sudo apt-get install -y curl
- run: sudo apt-get install -y wget
- run: sudo apt-get install -y git
```
```
# Good — logical grouping
- label: Update and install base tools
  run: |
    sudo apt-get update -y
    sudo apt-get install -y curl wget git
```

**DON'T: Assume environment persists between steps**
```
# Bad — variable set in step 1 is lost in step 2
- run: export MY_VAR="hello"
- run: echo $MY_VAR   # This will be empty!
```
```
# Good — use within same step
- label: Configure and use variable
  run: |
    export MY_VAR="hello"
    echo $MY_VAR
```

**DON'T: Use `cd` as a standalone step**
```
# Bad — cd has no effect on the next step
- run: cd /opt/myapp
- run: make build    # Runs in $HOME, not /opt/myapp!
```
```
# Good — cd within the same step
- label: Build project
  run: |
    cd /opt/myapp
    make build
```

**DON'T: Ignore potential failures silently**
```
# Bad — hides errors
- run: some-command || true
```
```
# Good — handle explicitly
- label: Run optional command
  run: |
    if command -v some-command &>/dev/null; then
      some-command
    else
      echo "some-command not found, skipping"
    fi
```

**DON'T: Hardcode user-specific paths**
```
# Bad
- run: cp file /home/deploy/apps/
```
```
# Good
- run: cp file $HOME/apps/
```

### Template for AI Agents

When asked to create a VPM manifest, use this template structure:

```
# ═══════════════════════════════════════════════════════
# VPM Manifest: [Brief description of what this sets up]
# Generated for: [User's described use case]
# Target OS: [Ubuntu 22.04 / Debian 12 / etc.]
# ═══════════════════════════════════════════════════════
#
# Usage:
#   vpm install --file this-file.yaml
#
# Prerequisites:
#   - [List any manual prerequisites]
#
# After installation:
#   - [List any manual post-install steps]
#

[first_app] Description
- label: Descriptive step name
  run: command

[second_app] Description
requires: first_app
- label: Descriptive step name
  run: |
    multi-line
    command
```

Always include:
1. A header comment block explaining the manifest's purpose
2. Usage instructions in comments
3. Prerequisites and post-install notes
4. Proper dependency declarations
5. Verification steps for each app
6. Descriptive labels for every step

---
