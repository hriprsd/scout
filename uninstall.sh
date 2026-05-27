#!/usr/bin/env bash
set -euo pipefail

# Scout uninstaller - clean removal.
#
# Usage:
#   bash uninstall.sh              # remove scout, keep indexed data
#   bash uninstall.sh --purge      # remove scout AND all indexed data
#   bash uninstall.sh --dry-run    # show what would be removed

SCOUT_HOME="$HOME/.scout"
SCOUT_VENV="$SCOUT_HOME/env"
PURGE=false
DRY_RUN=false

usage() {
    echo "Usage: bash uninstall.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --purge      Also remove all indexed data (~/.scout/repos/)"
    echo "  --dry-run    Show what would be removed without doing it"
    echo "  -h, --help   Show this help"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge)    PURGE=true; shift ;;
        --dry-run)  DRY_RUN=true; shift ;;
        -h|--help)  usage ;;
        *)          echo "Unknown option: $1"; usage ;;
    esac
done

# ── Helpers ──

info()  { echo -e "\033[1;37m[scout]\033[0m $1"; }
ok()    { echo -e "\033[1;32m[scout]\033[0m $1"; }
warn()  { echo -e "\033[1;33m[scout]\033[0m $1"; }

remove() {
    local target="$1"
    local label="$2"
    if [[ -e "$target" ]] || [[ -L "$target" ]]; then
        if [[ "$DRY_RUN" == true ]]; then
            info "Would remove: $target ($label)"
        else
            rm -rf "$target"
            ok "Removed: $target ($label)"
        fi
    fi
}

# ── Find symlink ──

SYMLINK=""
for dir in "$HOME/.local/bin" "/usr/local/bin" "$HOME/bin"; do
    if [[ -L "$dir/scout" ]]; then
        link_target=$(readlink "$dir/scout" 2>/dev/null || true)
        if [[ "$link_target" == *".scout/env"* ]]; then
            SYMLINK="$dir/scout"
            break
        fi
    fi
done

# ── Show what we found ──

echo ""
info "Scout uninstaller"
echo ""

found=false

if [[ -n "$SYMLINK" ]]; then
    info "Found symlink: $SYMLINK"
    found=true
fi

if [[ -d "$SCOUT_VENV" ]]; then
    venv_size=$(du -sh "$SCOUT_VENV" 2>/dev/null | cut -f1)
    info "Found venv: $SCOUT_VENV ($venv_size)"
    found=true
fi

if [[ -d "$SCOUT_HOME/repos" ]]; then
    data_size=$(du -sh "$SCOUT_HOME/repos" 2>/dev/null | cut -f1)
    repo_count=$(ls -1d "$SCOUT_HOME/repos"/*/ 2>/dev/null | wc -l | tr -d ' ')
    info "Found indexed data: $SCOUT_HOME/repos/ ($data_size, $repo_count repo(s))"
    found=true
fi

if [[ "$found" == false ]]; then
    info "Nothing to uninstall. Scout is not installed."
    exit 0
fi

echo ""

# ── Confirm unless dry-run ──

if [[ "$DRY_RUN" == false ]]; then
    if [[ "$PURGE" == true ]]; then
        warn "This will remove scout AND all indexed data."
    else
        info "This will remove scout but keep your indexed data."
        info "Use --purge to also remove indexed data."
    fi
    echo ""
    read -p "Continue? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        info "Cancelled."
        exit 0
    fi
    echo ""
fi

# ── Remove symlink ──

if [[ -n "$SYMLINK" ]]; then
    if [[ "$SYMLINK" == "/usr/local/bin/scout" ]]; then
        if [[ "$DRY_RUN" == true ]]; then
            info "Would remove: $SYMLINK (requires sudo)"
        else
            sudo rm -f "$SYMLINK"
            ok "Removed: $SYMLINK (symlink)"
        fi
    else
        remove "$SYMLINK" "symlink"
    fi
fi

# ── Remove venv ──

remove "$SCOUT_VENV" "venv"

# ── Remove git hooks ──

if [[ -d "$SCOUT_HOME/repos" ]]; then
    for meta in "$SCOUT_HOME/repos"/*/meta.json; do
        [[ -f "$meta" ]] || continue
        # extract repo path from meta.json
        repo_path=$(python3 -c "import json; print(json.load(open('$meta'))['path'])" 2>/dev/null || true)
        if [[ -n "$repo_path" ]] && [[ -d "$repo_path/.git/hooks" ]]; then
            for hook in post-commit post-checkout post-merge; do
                hook_file="$repo_path/.git/hooks/$hook"
                if [[ -f "$hook_file" ]] && grep -q "scout" "$hook_file" 2>/dev/null; then
                    if [[ "$DRY_RUN" == true ]]; then
                        info "Would clean scout hook from: $hook_file"
                    else
                        # remove scout block from hook
                        tmp=$(mktemp)
                        sed '/# scout:/,/^fi$/d' "$hook_file" > "$tmp"
                        # if only shebang remains, remove the hook
                        non_empty=$(grep -cv '^#!\|^$' "$tmp" 2>/dev/null || echo "0")
                        if [[ "$non_empty" -eq 0 ]]; then
                            rm -f "$hook_file" "$tmp"
                            ok "Removed hook: $hook_file"
                        else
                            mv "$tmp" "$hook_file"
                            chmod +x "$hook_file"
                            ok "Cleaned scout from: $hook_file"
                        fi
                    fi
                fi
            done
        fi
    done
fi

# ── Remove data (if --purge) ──

if [[ "$PURGE" == true ]]; then
    remove "$SCOUT_HOME/repos" "indexed data"
    remove "$SCOUT_HOME/config.toml" "config"
    # remove ~/.scout if empty
    if [[ -d "$SCOUT_HOME" ]]; then
        remaining=$(find "$SCOUT_HOME" -mindepth 1 2>/dev/null | head -1)
        if [[ -z "$remaining" ]]; then
            remove "$SCOUT_HOME" "scout home"
        fi
    fi
else
    if [[ "$DRY_RUN" == false ]]; then
        echo ""
        info "Kept indexed data at $SCOUT_HOME/repos/"
        info "Run with --purge to remove it too."
    fi
fi

# ── Done ──

echo ""
if [[ "$DRY_RUN" == true ]]; then
    info "Dry run complete. No changes made."
else
    ok "Scout uninstalled."
fi
echo ""
