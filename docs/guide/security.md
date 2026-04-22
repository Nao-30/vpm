# Security, Rollback & Remote Manifests

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

---

## Rollback

Steps can define optional rollback commands that undo their changes:

```yaml
- label: Install Nginx
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx
```

```bash
vpm rollback my_app            # undo succeeded steps in reverse order
vpm rollback my_app --dry-run  # preview what would be undone
```

Rollback is best-effort: if a rollback step fails, remaining rollbacks still execute.
Only steps with `rollback:` defined and `status: success` are undone.

---

## Remote Manifests

Fetch and execute manifests from URLs or GitHub:

```bash
vpm run https://example.com/setup.yaml
vpm run github:user/repo                      # fetches vpm-manifest.yaml from repo root
vpm run github:user/repo/path/manifest.yaml   # specific file
```

Security scanning is mandatory for remote manifests and cannot be skipped.

---
