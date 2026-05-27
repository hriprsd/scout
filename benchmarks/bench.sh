#!/usr/bin/env bash
set -euo pipefail

# Scout vs Repomix benchmark
# Tests: flask (small), express (medium), fastapi (large)
#
# Prerequisites:
#   - scout installed (https://github.com/hriprsd/scout)
#   - node/npx available (for repomix)
#   - python3 available
#
# Usage:
#   bash bench.sh              # run full benchmark
#   bash bench.sh --skip-clone # reuse already-cloned repos

BENCH_DIR="/tmp/scout-bench"
RESULTS="$BENCH_DIR/results.md"
SKIP_CLONE=false

for arg in "$@"; do
    case $arg in
        --skip-clone) SKIP_CLONE=true ;;
    esac
done

mkdir -p "$BENCH_DIR"

# ── Clone test repos ──
declare -A REPO_URLS=(
    [flask]="https://github.com/pallets/flask.git"
    [express]="https://github.com/expressjs/express.git"
    [fastapi]="https://github.com/fastapi/fastapi.git"
)

if [[ "$SKIP_CLONE" == false ]]; then
    for repo in flask express fastapi; do
        if [[ -d "$BENCH_DIR/$repo" ]]; then
            echo "Removing old clone: $repo"
            rm -rf "$BENCH_DIR/$repo"
        fi
        echo "Cloning $repo..."
        git clone --depth 1 --quiet "${REPO_URLS[$repo]}" "$BENCH_DIR/$repo"
    done
fi

# ── Begin benchmark ──
echo "# Benchmark Results" > "$RESULTS"
echo "" >> "$RESULTS"
echo "Date: $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$RESULTS"
echo "Machine: $(uname -m), $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'unknown')" >> "$RESULTS"
echo "" >> "$RESULTS"

repos=("flask" "express" "fastapi")

for repo in "${repos[@]}"; do
    repo_path="$BENCH_DIR/$repo"
    echo "=== Benchmarking $repo ==="
    echo "" >> "$RESULTS"
    echo "## $repo" >> "$RESULTS"
    echo "" >> "$RESULTS"

    total_files=$(find "$repo_path" -type f | wc -l | tr -d ' ')
    echo "Total files: $total_files" >> "$RESULTS"
    echo "" >> "$RESULTS"

    # ── Scout ──
    echo "  Scout init+warm..."
    scout init "$repo_path" > /dev/null 2>&1 || true

    warm_start=$(python3 -c "import time; print(time.time())")
    scout warm "$repo_path" > /dev/null 2>&1
    warm_end=$(python3 -c "import time; print(time.time())")
    warm_time=$(python3 -c "print(f'{$warm_end - $warm_start:.2f}')")

    # Scout context output (write to file to avoid SIGPIPE on large repos)
    ctx_start=$(python3 -c "import time; print(time.time())")
    scout context "$repo_path" > "$BENCH_DIR/scout-ctx-${repo}.txt" 2>/dev/null
    ctx_end=$(python3 -c "import time; print(time.time())")
    ctx_time=$(python3 -c "print(f'{$ctx_end - $ctx_start:.2f}')")
    scout_ctx_bytes=$(wc -c < "$BENCH_DIR/scout-ctx-${repo}.txt" | tr -d ' ')
    scout_ctx_tokens=$((scout_ctx_bytes * 10 / 40))

    # Scout context --full
    scout context --full "$repo_path" > "$BENCH_DIR/scout-full-${repo}.txt" 2>/dev/null
    scout_full_bytes=$(wc -c < "$BENCH_DIR/scout-full-${repo}.txt" | tr -d ' ')
    scout_full_tokens=$((scout_full_bytes * 10 / 40))

    # Scout disk usage
    slug=$(ls ~/.scout/repos/ | grep "^${repo}-" | head -1)
    scout_disk=$(du -sh ~/.scout/repos/$slug 2>/dev/null | cut -f1)

    # Incremental: touch one file, re-warm
    first_file=$(find "$repo_path" -name "*.py" -o -name "*.js" -o -name "*.ts" | head -1)
    if [[ -n "$first_file" ]]; then
        touch "$first_file"
        incr_start=$(python3 -c "import time; print(time.time())")
        scout warm "$repo_path" > /dev/null 2>&1
        incr_end=$(python3 -c "import time; print(time.time())")
        incr_time=$(python3 -c "print(f'{$incr_end - $incr_start:.2f}')")
    else
        incr_time="N/A"
    fi

    echo "### Scout" >> "$RESULTS"
    echo "| Metric | Value |" >> "$RESULTS"
    echo "|--------|-------|" >> "$RESULTS"
    echo "| Warm time (full) | ${warm_time}s |" >> "$RESULTS"
    echo "| Warm time (incremental, 1 file changed) | ${incr_time}s |" >> "$RESULTS"
    echo "| Context output (L0+L1) | ${scout_ctx_bytes} bytes (~${scout_ctx_tokens} tokens) |" >> "$RESULTS"
    echo "| Context output (--full, L0+L1+L2) | ${scout_full_bytes} bytes (~${scout_full_tokens} tokens) |" >> "$RESULTS"
    echo "| Context generation time | ${ctx_time}s |" >> "$RESULTS"
    echo "| Disk usage | ${scout_disk} |" >> "$RESULTS"
    echo "" >> "$RESULTS"

    # ── Repomix ──
    echo "  Repomix default..."
    repomix_start=$(python3 -c "import time; print(time.time())")
    npx --yes repomix@latest --output "$BENCH_DIR/repomix-${repo}.txt" "$repo_path" > /dev/null 2>&1
    repomix_end=$(python3 -c "import time; print(time.time())")
    repomix_time=$(python3 -c "print(f'{$repomix_end - $repomix_start:.2f}')")
    repomix_bytes=$(wc -c < "$BENCH_DIR/repomix-${repo}.txt" | tr -d ' ')
    repomix_tokens=$((repomix_bytes * 10 / 40))

    echo "  Repomix --compress..."
    compress_start=$(python3 -c "import time; print(time.time())")
    npx repomix@latest --compress --output "$BENCH_DIR/repomix-${repo}-compressed.txt" "$repo_path" > /dev/null 2>&1
    compress_end=$(python3 -c "import time; print(time.time())")
    compress_time=$(python3 -c "print(f'{$compress_end - $compress_start:.2f}')")
    compress_bytes=$(wc -c < "$BENCH_DIR/repomix-${repo}-compressed.txt" | tr -d ' ')
    compress_tokens=$((compress_bytes * 10 / 40))

    # Repomix incremental (regenerates from scratch every time)
    repomix_incr_start=$(python3 -c "import time; print(time.time())")
    npx repomix@latest --output "$BENCH_DIR/repomix-${repo}-incr.txt" "$repo_path" > /dev/null 2>&1
    repomix_incr_end=$(python3 -c "import time; print(time.time())")
    repomix_incr_time=$(python3 -c "print(f'{$repomix_incr_end - $repomix_incr_start:.2f}')")

    echo "### Repomix" >> "$RESULTS"
    echo "| Metric | Value |" >> "$RESULTS"
    echo "|--------|-------|" >> "$RESULTS"
    echo "| Generation time (default) | ${repomix_time}s |" >> "$RESULTS"
    echo "| Generation time (--compress) | ${compress_time}s |" >> "$RESULTS"
    echo "| Regeneration time (1 file changed) | ${repomix_incr_time}s |" >> "$RESULTS"
    echo "| Output size (default) | ${repomix_bytes} bytes (~${repomix_tokens} tokens) |" >> "$RESULTS"
    echo "| Output size (--compress) | ${compress_bytes} bytes (~${compress_tokens} tokens) |" >> "$RESULTS"
    echo "| Disk usage | 0 (no persistent index) |" >> "$RESULTS"
    echo "" >> "$RESULTS"

    # Cleanup temp output files
    rm -f "$BENCH_DIR/repomix-${repo}"*.txt
    rm -f "$BENCH_DIR/scout-ctx-${repo}.txt" "$BENCH_DIR/scout-full-${repo}.txt"
done

# Cleanup scout indexes for benchmark repos
for repo in "${repos[@]}"; do
    slug=$(ls ~/.scout/repos/ 2>/dev/null | grep "^${repo}-" | head -1)
    if [[ -n "$slug" ]]; then
        rm -rf ~/.scout/repos/$slug
    fi
done

echo ""
echo "Done. Results at $RESULTS"
echo "Benchmark repo indexes cleaned from ~/.scout/repos/"
