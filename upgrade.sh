#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════
# VPM Upgrade Script
# Upgrades vpmx from PyPI or local source
# ═══════════════════════════════════════════════════════

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

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

echo
echo -e "${BOLD}VPM Upgrade${RESET}"
echo -e "${DIM}───────────────────────────────────────${RESET}"

# ── Detect install method ─────────────────────────────

INSTALLED=$(vpm version 2>/dev/null | grep -oP 'v\K[0-9]+\.[0-9]+\.[0-9]+' || echo "not installed")
SOURCE=$(grep -oP '^version\s*=\s*"\K[0-9]+\.[0-9]+\.[0-9]+' "$REPO_DIR/pyproject.toml" || echo "unknown")

echo
info "Installed : ${BOLD}v${INSTALLED}${RESET}"
info "Source    : ${BOLD}v${SOURCE}${RESET}"
echo

if [[ "$INSTALLED" == "not installed" ]]; then
    warn "VPM is not installed. Installing from PyPI..."
    pip install vpmx
    success "Installed vpmx v${SOURCE}"
    exit 0
fi

# ── Upgrade options ───────────────────────────────────

echo "  Upgrade method:"
echo "    1) PyPI (recommended): pip install --upgrade vpmx"
echo "    2) Local source: pip install --upgrade $REPO_DIR"
echo
read -rp "  Choose [1/2]: " choice

case "${choice:-1}" in
    1)
        info "Upgrading from PyPI..."
        pip install --upgrade vpmx
        ;;
    2)
        info "Upgrading from local source..."
        pip install --upgrade "$REPO_DIR"
        ;;
    *)
        error "Invalid choice."
        exit 1
        ;;
esac

echo
success "Upgrade complete!"
vpm version
