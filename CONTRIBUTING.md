# Contributing to VPM

Thanks for your interest in contributing to VPM!

## Development Setup

```bash
git clone git@github.com:Nao-30/vpm.git
cd vpm
python3 -m vpm version   # verify it runs
```

No virtual environment needed — VPM uses only the Python standard library.

## Project Structure

```
vpm/
├── __init__.py          # Version and package metadata
├── __main__.py          # python -m vpm entry point
├── style.py             # ANSI terminal styling
├── ui.py                # Terminal UI components
├── config.py            # XDG path management
├── models.py            # Data models (StepRecord, AppRecord, enums)
├── lockfile.py          # Atomic JSON state persistence
├── manifest.py          # Manifest file parser
├── scanner.py           # Security scanning and URL analysis
├── executor.py          # PTY-based command execution
├── completions.py       # Shell completion generators
├── app.py               # Core commands (install, status, logs, retry, reset, audit, rollback, run)
├── cli.py               # Entry point, arg parser, setup/doctor/version commands
```

Dependency flow (one-directional):
```
style → ui → config → models → lockfile → manifest → scanner → executor → completions → app → cli
```

## Guidelines

- **No external dependencies.** VPM must remain pure Python 3.10+ stdlib. This is a hard rule.
- **Keep the module dependency flow one-directional.** No circular imports.
- **Test on a real system.** VPM uses PTY execution — there's no way to unit test that meaningfully without a real terminal.
- **Match the existing code style.** No formatters enforced, just be consistent with what's there.

## Making Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Run tests: `pip install pytest && python -m pytest tests/ -v`
4. Test locally: `python3 -m vpm doctor` and run through the core commands
5. Commit with a clear message
6. Open a PR against `main`

## Reporting Issues

Open an issue with:
- What you expected to happen
- What actually happened
- Your OS and Python version (`vpm version` output)
- Relevant log output (`vpm logs <app> --latest`)
