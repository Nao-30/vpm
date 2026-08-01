# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.3] - 2026-08-01

### Changed
- Reuse one PTY and terminal session for the entire VPM command while keeping each manifest step in an isolated shell
- Restore PTY state between steps and close the shared session cleanly when the command finishes

### Fixed
- Repeated sudo password prompts between steps when sudo uses its default per-terminal credential cache
- Existing Pyright error in file-size formatting
- Stale version metadata in remote request headers and troubleshooting documentation
- CI lint behavior drifting when Ruff changes its implicit default rule set
- Release tags publishing without first re-running lint and tests

## [1.2.2] - 2026-04-22

### Fixed
- Show a success message when an audit has findings below the configured display threshold

## [1.2.1] - 2026-04-22

### Fixed
- Use an absolute README logo URL so the image renders correctly on PyPI

## [1.2.0] - 2026-04-22

### Added
- `additional_allowed_domains` config key — extend default allowlist without replacing it
- `vpm run --audit-only` flag — security scan remote manifests without executing
- Integration tests (install, audit, rollback, status, doctor, version)
- `py.typed` marker for PEP 561 type checker support

### Changed
- `upgrade.sh` rewritten for `pip install vpmx` (replaces old pipx flow)

### Fixed
- Stale single-file architecture references in troubleshooting docs

## [1.1.0] - 2026-04-22

### Added
- Security scanner with static pattern detection (`vpm audit`)
- Auto-scan before `vpm install` with configurable severity levels
- Rollback system with `rollback:` manifest field and `vpm rollback` command
- Remote manifest execution (`vpm run <url>`)
- GitHub shorthand for remote manifests (`vpm run github:user/repo`)
- AI agent context files (`AGENTS.md`, `llms.txt`)
- Example manifests for common server setups
- CI/CD with GitHub Actions
- Unit tests for parser, models, scanner, and dependency resolver

### Changed
- PyPI package renamed from `vpm` to `vpmx` (CLI command unchanged)
- Expanded pyproject.toml metadata (keywords, classifiers, URLs)

## [1.0.0] - 2026-03-17

### Added
- Initial release
- Custom manifest format parser (no YAML dependency)
- PTY-based interactive command execution
- Dependency resolution with topological sort and cycle detection
- Crash recovery via atomic lock file with write-then-rename
- Change detection via SHA-256 command hashing
- Shell completions for zsh, bash, and fish
- Self-diagnostics with `vpm doctor`
- Full logging with per-step and summary log files
- Resume support — interrupted installs pick up where they left off
- `vpm init` manifest template generator
- `vpm setup` for PATH installation (user and global)

[Unreleased]: https://github.com/Nao-30/vpm/compare/v1.2.3...HEAD
[1.2.3]: https://github.com/Nao-30/vpm/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/Nao-30/vpm/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/Nao-30/vpm/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Nao-30/vpm/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Nao-30/vpm/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Nao-30/vpm/releases/tag/v1.0.0
