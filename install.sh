#!/usr/bin/env bash
set -euo pipefail

# Scout installer - one script, fully set up.
#
# Usage:
#   bash install.sh              # install to ~/.local/bin (default)
#   bash install.sh --global     # install to /usr/local/bin (needs sudo)
#   bash install.sh --dir ~/bin  # install to a custom directory
#   bash install.sh --upgrade    # reinstall over existing installation

SCOUT_HOME="$HOME/.scout"
SCOUT_VENV="$SCOUT_HOME/env"
INSTALL_DIR="$HOME/.local/bin"
UPGRADE=false
MIN_PYTHON="3.10"

usage() {
    echo "Usage: bash install.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --global       Install to /usr/local/bin (requires sudo)"
    echo "  --dir PATH     Install to a custom directory"
    echo "  --upgrade      Reinstall over existing installation"
    echo "  -h, --help     Show this help"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --global)   INSTALL_DIR="/usr/local/bin"; shift ;;
        --dir)      INSTALL_DIR="$2"; shift 2 ;;
        --upgrade)  UPGRADE=true; shift ;;
        -h|--help)  usage ;;
        *)          echo "Unknown option: $1"; usage ;;
    esac
done

# ── Helpers ──

info()  { echo -e "\033[1;37m[scout]\033[0m $1"; }
ok()    { echo -e "\033[1;32m[scout]\033[0m $1"; }
warn()  { echo -e "\033[1;33m[scout]\033[0m $1"; }
fail()  { echo -e "\033[1;31m[scout]\033[0m $1"; exit 1; }

# ── Preflight checks ──

info "Checking Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        if [[ -n "$version" ]]; then
            major="${version%%.*}"
            minor="${version#*.}"
            req_major="${MIN_PYTHON%%.*}"
            req_minor="${MIN_PYTHON#*.}"
            if [[ "$major" -gt "$req_major" ]] || { [[ "$major" -eq "$req_major" ]] && [[ "$minor" -ge "$req_minor" ]]; }; then
                PYTHON="$cmd"
                break
            fi
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    fail "Python >= $MIN_PYTHON is required but not found."
fi

info "Found $PYTHON ($version)"

# ── Check existing installation ──

if [[ -d "$SCOUT_VENV" ]] && [[ "$UPGRADE" == false ]]; then
    if [[ -x "$INSTALL_DIR/scout" ]]; then
        current=$("$INSTALL_DIR/scout" --version 2>/dev/null || echo "unknown")
        warn "Scout is already installed ($current)"
        warn "Run with --upgrade to reinstall"
        exit 0
    fi
fi

# ── Find source directory ──

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    fail "Cannot find pyproject.toml. Run this script from the scout project directory."
fi

# ── Create scout home ──

info "Setting up ~/.scout..."
mkdir -p "$SCOUT_HOME"

# ── Create isolated venv ──

if [[ -d "$SCOUT_VENV" ]]; then
    info "Removing old venv..."
    rm -rf "$SCOUT_VENV"
fi

info "Creating venv at $SCOUT_VENV..."
"$PYTHON" -m venv "$SCOUT_VENV"

# ── Install scout into venv ──

info "Installing scout..."
"$SCOUT_VENV/bin/pip" install --quiet --upgrade pip
"$SCOUT_VENV/bin/pip" install --quiet "$SCRIPT_DIR"

# ── Verify it works ──

if ! "$SCOUT_VENV/bin/scout" --version &>/dev/null; then
    fail "Installation failed. scout binary not working."
fi

INSTALLED_VERSION=$("$SCOUT_VENV/bin/scout" --version 2>&1)

# ── Symlink to PATH ──

mkdir -p "$INSTALL_DIR"

SYMLINK="$INSTALL_DIR/scout"

if [[ "$INSTALL_DIR" == "/usr/local/bin" ]]; then
    info "Linking to $SYMLINK (requires sudo)..."
    sudo ln -sf "$SCOUT_VENV/bin/scout" "$SYMLINK"
else
    ln -sf "$SCOUT_VENV/bin/scout" "$SYMLINK"
fi

# ── Check PATH ──

if ! echo "$PATH" | tr ':' '\n' | grep -q "^${INSTALL_DIR}$"; then
    warn "$INSTALL_DIR is not on your PATH."
    echo ""
    warn "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
    echo ""
    echo "    export PATH=\"$INSTALL_DIR:\$PATH\""
    echo ""
fi

# ── Done ──

echo ""
echo -e "\033[1m  ___  ___ ___  _   _ _____"
echo -e " / __|/ __/ _ \\| | | |_   _|"
echo -e " \\__ \\ (_| (_) | |_| | | |"
echo -e " |___/\\___\\___/ \\___/  |_|\033[0m"
echo ""
ok "Installed $INSTALLED_VERSION"
ok "Binary:  $SYMLINK"
ok "Venv:    $SCOUT_VENV"
ok "Data:    $SCOUT_HOME/repos/"
echo ""
info "Get started:"
echo "    cd your-repo"
echo "    scout init"
echo "    scout warm"
echo "    scout context"
echo ""
