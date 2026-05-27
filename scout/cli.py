"""Scout CLI - codebase context for LLMs, zero waste. Zero dependencies."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from scout import __version__
from scout.config import (
    RepoMeta, repo_slug, repo_dir, cards_dir,
    save_meta, load_meta, resolve_slug,
)
from scout.card import generate_card, collect_files, load_card, render_card
from scout.context import generate_context
from scout.git import get_git_state
from scout.tree import generate_tree, generate_dir_cards

BANNER = """\
\033[1m  ___  ___ ___  _   _ _____
 / __|/ __/ _ \\| | | |_   _|
 \\__ \\ (_| (_) | |_| | | |
 |___/\\___\\___/ \\___/  |_|\033[0m
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="scout",
        description="Scout - codebase context for LLMs, zero waste.",
    )
    parser.add_argument("--version", action="version", version=f"scout {__version__}")
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Register a repository with scout")
    p_init.add_argument("paths", nargs="*", default=["."])
    p_init.add_argument("--scan", action="store_true", help="Scan directory for all git repos underneath")
    p_init.add_argument("--warm", action="store_true", help="Also run warm after init")

    # warm
    p_warm = sub.add_parser("warm", help="Generate cards for all files")
    p_warm.add_argument("path", nargs="?", default=".")
    p_warm.add_argument("--force", action="store_true", help="Regenerate all, ignoring cache")

    # card
    p_card = sub.add_parser("card", help="Show or regenerate a card for a file")
    p_card.add_argument("file_path")
    p_card.add_argument("--path", default=".", dest="repo_path")

    # context
    p_ctx = sub.add_parser("context", help="Emit context for LLM consumption (stdout)")
    p_ctx.add_argument("path", nargs="?", default=".")
    p_ctx.add_argument("--full", action="store_true", help="Include related L2 cards")
    p_ctx.add_argument("--tree-only", action="store_true", help="Only L1 tree")
    p_ctx.add_argument("--workset-only", action="store_true", help="Only L0 workset")

    # status
    p_status = sub.add_parser("status", help="Show card coverage and staleness")
    p_status.add_argument("path", nargs="?", default=".")

    # gc
    p_gc = sub.add_parser("gc", help="Remove cards for deleted files")
    p_gc.add_argument("path", nargs="?", default=".")
    p_gc.add_argument("--dry-run", action="store_true", help="Show what would be removed")

    # ls
    p_ls = sub.add_parser("ls", help="List cards in a directory")
    p_ls.add_argument("dir_path")
    p_ls.add_argument("--path", default=".", dest="repo_path")

    # tree
    p_tree = sub.add_parser("tree", help="Show repository map (L1 directory summaries)")
    p_tree.add_argument("path", nargs="?", default=".")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "init": cmd_init,
        "warm": cmd_warm,
        "card": cmd_card,
        "context": cmd_context,
        "status": cmd_status,
        "gc": cmd_gc,
        "ls": cmd_ls,
        "tree": cmd_tree,
    }
    commands[args.command](args)


def cmd_init(args: argparse.Namespace) -> None:
    repos = _resolve_init_paths(args.paths, scan=args.scan)

    if not repos:
        _err("No git repositories found.")
        raise SystemExit(1)

    banner_shown = False
    initialized = []

    for repo_path in repos:
        slug = repo_slug(repo_path)
        existing = load_meta(slug)

        if existing:
            _err(f"Already initialized: {slug}")
            continue

        meta = RepoMeta(path=repo_path, slug=slug)
        rdir = repo_dir(slug)
        rdir.mkdir(parents=True, exist_ok=True)
        cards_dir(slug).mkdir(parents=True, exist_ok=True)
        save_meta(slug, meta)
        _install_hooks(repo_path)

        if not banner_shown:
            sys.stderr.write(BANNER + "\n")
            banner_shown = True

        _err(f"Initialized: {slug}")
        _err(f"  Repo: {repo_path}")
        _err(f"  Data: {rdir}")
        _err("")
        initialized.append(repo_path)

    if not initialized:
        return

    _err(f"{len(initialized)} repo(s) initialized.")

    if args.warm:
        _err("")
        for repo_path in initialized:
            slug, meta = resolve_slug(repo_path)
            files = collect_files(repo_path, meta.ignore_patterns)
            _err(f"Warming {Path(repo_path).name} ({len(files)} files)...")
            generated = 0
            start = time.time()
            for rel_path in files:
                card = generate_card(repo_path, slug, rel_path)
                if card and card.generated_at >= start:
                    generated += 1
            elapsed = time.time() - start
            meta.card_count = len(files)
            meta.last_warm = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_meta(slug, meta)
            _err(f"  {generated} cards in {elapsed:.1f}s")
    elif len(initialized) == 1:
        _err("Next: scout warm")
    else:
        _err("Next: scout warm <path> (for each repo)")


def _resolve_init_paths(paths: list[str], scan: bool) -> list[str]:
    repos = []
    for p in paths:
        resolved = str(Path(p).resolve())
        if (Path(resolved) / ".git").exists():
            repos.append(resolved)
        elif scan:
            for child in sorted(Path(resolved).iterdir()):
                if child.is_dir() and (child / ".git").exists():
                    repos.append(str(child))
        else:
            # single path that's not a git repo and --scan not set
            _err(f"Not a git repository: {resolved}")
            _err(f"  Use --scan to find git repos inside this directory")
    return repos


def cmd_warm(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.path).resolve())
    slug, meta = resolve_slug(repo_path)

    files = collect_files(repo_path, meta.ignore_patterns)
    total = len(files)

    if total == 0:
        _err("No supported files found.")
        return

    _err(f"Warming {total} files...")

    generated = 0
    cached = 0
    failed = 0
    start = time.time()

    for i, rel_path in enumerate(files):
        card = generate_card(repo_path, slug, rel_path, force=args.force)
        if card:
            if card.generated_at >= start:
                generated += 1
            else:
                cached += 1
        else:
            failed += 1

        if (i + 1) % 100 == 0 or i + 1 == total:
            sys.stderr.write(f"\r  [{i + 1}/{total}] {generated} new, {cached} cached, {failed} skipped")

    elapsed = time.time() - start
    sys.stderr.write("\n")
    _err(f"Done in {elapsed:.1f}s")
    _err(f"  Generated: {generated}")
    _err(f"  Cached:    {cached}")
    _err(f"  Skipped:   {failed}")

    meta.card_count = generated + cached
    meta.last_warm = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta.branch = get_git_state(repo_path).branch
    save_meta(slug, meta)


def cmd_card(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.repo_path).resolve())
    slug, meta = resolve_slug(repo_path)
    file_path = args.file_path

    abs_file = Path(repo_path) / file_path
    if not abs_file.exists():
        abs_file = Path(file_path).resolve()
        try:
            file_path = str(abs_file.relative_to(repo_path))
        except ValueError:
            _err(f"File not in repo: {file_path}")
            raise SystemExit(1)

    c = generate_card(repo_path, slug, file_path, force=True)
    if c:
        print(render_card(c))
    else:
        _err(f"Could not generate card for: {file_path}")
        raise SystemExit(1)


def cmd_context(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.path).resolve())
    slug, _meta = resolve_slug(repo_path)

    output = generate_context(
        repo_path=repo_path,
        slug=slug,
        include_workset=not args.tree_only,
        include_tree=not args.workset_only,
        include_related=args.full,
    )
    print(output)


def cmd_status(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.path).resolve())
    slug, meta = resolve_slug(repo_path)

    files = collect_files(repo_path, meta.ignore_patterns)
    total_files = len(files)

    cdir = cards_dir(slug)
    total_cards = len(list(cdir.rglob("*.card.json"))) if cdir.exists() else 0

    stale = 0
    fresh = 0
    from scout.hash import file_hash
    for rel_path in files:
        c = load_card(slug, rel_path)
        if c is None:
            stale += 1
        elif c.source_hash != file_hash(Path(repo_path) / rel_path):
            stale += 1
        else:
            fresh += 1

    git_state = get_git_state(repo_path)
    coverage = f"{fresh / total_files * 100:.0f}%" if total_files else "N/A"

    w = 18
    print(f"\n  {'scout status':^50}")
    print(f"  {'─' * 50}")
    print(f"  {'Repository':<{w}} {meta.path}")
    print(f"  {'Branch':<{w}} {git_state.branch}")
    print(f"  {'Source files':<{w}} {total_files}")
    print(f"  {'Cards (total)':<{w}} {total_cards}")
    print(f"  {'Cards (fresh)':<{w}} {fresh}")
    print(f"  {'Cards (stale)':<{w}} {stale}")
    print(f"  {'Coverage':<{w}} {coverage}")
    print(f"  {'Last warm':<{w}} {meta.last_warm or 'never'}")
    print(f"  {'Changed files':<{w}} {len(git_state.changed_files)}")
    print(f"  {'Staged files':<{w}} {len(git_state.staged_files)}")
    print(f"  {'Data dir':<{w}} {repo_dir(slug)}")
    print()


def cmd_gc(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.path).resolve())
    slug, meta = resolve_slug(repo_path)

    cdir = cards_dir(slug)
    if not cdir.exists():
        _err("No cards directory found.")
        return

    removed = 0
    for card_file in cdir.rglob("*.card.json"):
        rel = os.path.relpath(card_file, cdir)
        source_rel = rel.removesuffix(".card.json")
        source_abs = Path(repo_path) / source_rel

        if not source_abs.exists():
            if args.dry_run:
                _err(f"  Would remove: {source_rel}")
            else:
                card_file.unlink()
            removed += 1

    if removed:
        action = "Would remove" if args.dry_run else "Removed"
        _err(f"{action} {removed} stale card(s)")
    else:
        _err("No stale cards found.")

    if not args.dry_run:
        for dirpath, dirnames, filenames in os.walk(cdir, topdown=False):
            if not filenames and not dirnames:
                try:
                    Path(dirpath).rmdir()
                except OSError:
                    pass


def cmd_ls(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.repo_path).resolve())
    slug, _meta = resolve_slug(repo_path)
    print(generate_dir_cards(slug, args.dir_path))


def cmd_tree(args: argparse.Namespace) -> None:
    repo_path = str(Path(args.path).resolve())
    slug, _meta = resolve_slug(repo_path)
    print(generate_tree(slug, repo_path))


def _install_hooks(repo_path: str) -> None:
    hooks_dir = Path(repo_path) / ".git" / "hooks"
    if not hooks_dir.exists():
        return

    hook_script = """#!/usr/bin/env bash
# scout: refresh cards for changed files
if command -v scout &> /dev/null; then
    changed=$(git diff --name-only HEAD~1 HEAD 2>/dev/null)
    if [ -n "$changed" ]; then
        for f in $changed; do
            scout card "$f" --path "$(git rev-parse --show-toplevel)" > /dev/null 2>&1 &
        done
    fi
fi
"""
    for hook_name in ["post-commit", "post-checkout", "post-merge"]:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text()
            if "scout" in content:
                continue
            content += f"\n{hook_script}"
            hook_path.write_text(content)
        else:
            hook_path.write_text(hook_script)
            hook_path.chmod(0o755)


def _err(msg: str) -> None:
    sys.stderr.write(msg + "\n")


if __name__ == "__main__":
    main()
