#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════
# VPM Global Upgrade Script
# Upgrades the system-wide pipx installation of VPM
# ═══════════════════════════════════════════════════════

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPX_HOME=/opt/pipx
PIPX_BIN_DIR=/usr/local/bin

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "  ${CYAN}ℹ${RESET} $1"; }
success() { echo -e "  ${GREEN}✔${RESET} $1"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET} $1"; }
error()   { echo -e "  ${RED}✖${RESET} $1"; }
dim()     { echo -e "  ${DIM}$1${RESET}"; }

echo
echo -e "${BOLD}VPM Upgrade${RESET}"
echo -e "${DIM}───────────────────────────────────────${RESET}"

# ── Preflight checks ─────────────────────────────────

if [[ $EUID -eq 0 ]]; then
    error "Don't run this as root. It will sudo when needed."
    exit 1
fi

if ! command -v pipx &>/dev/null; then
    error "pipx not found. Install it: sudo apt install pipx"
    exit 1
fi

if ! command -v vpm &>/dev/null; then
    error "vpm is not currently installed."
    echo
    info "Install with:"
    dim "sudo PIPX_HOME=$PIPX_HOME PIPX_BIN_DIR=$PIPX_BIN_DIR pipx install $REPO_DIR"
    exit 1
fi

if [[ ! -f "$REPO_DIR/pyproject.toml" ]]; then
    error "pyproject.toml not found in $REPO_DIR"
    exit 1
fi

# ── Version comparison ────────────────────────────────

INSTALLED=$(vpm version 2>/dev/null | grep -oP 'v\K[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
SOURCE=$(grep -oP '^version\s*=\s*"\K[0-9]+\.[0-9]+\.[0-9]+' "$REPO_DIR/pyproject.toml" || echo "unknown")

echo
info "Installed : ${BOLD}v${INSTALLED}${RESET}"
info "Source    : ${BOLD}v${SOURCE}${RESET}"
info "Repo      : ${DIM}${REPO_DIR}${RESET}"
echo

if [[ "$INSTALLED" == "$SOURCE" ]]; then
    warn "Versions match. This will reinstall v${SOURCE}."
else
    success "Upgrading v${INSTALLED} → v${SOURCE}"
fi

# ── Confirm ───────────────────────────────────────────

echo
read -rp "  Proceed with upgrade? [y/N] " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo
    info "Aborted."
    exit 0
fi

# ── Upgrade ───────────────────────────────────────────

echo
info "Installing..."
echo

if sudo PIPX_HOME="$PIPX_HOME" PIPX_BIN_DIR="$PIPX_BIN_DIR" pipx install "$REPO_DIR" --force 2>&1; then
    echo
    success "Upgrade complete!"
    echo
    vpm version
else
    echo
    error "Upgrade failed. Previous version should still be intact."
    exit 1
fi
