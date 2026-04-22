# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Nao-30/vpm/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Nao-30/vpm/releases/tag/v1.0.0
