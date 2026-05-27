"""Directory tree generation (L1 summaries)."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from scout.card import Card, load_card
from scout.config import cards_dir

# Directories that get collapsed into a single summary line
_LOW_VALUE_PREFIXES = (
    "test", "tests", "spec", "specs", "__tests__",
    "docs", "doc", "documentation",
    ".github", ".circleci", ".gitlab",
    "examples", "example", "samples",
    "fixtures", "testdata", "test_data",
    "static", "public", "assets",
    "vendor", "third_party",
)


def _is_low_value_dir(dir_path: str) -> bool:
    """Check if a directory should be collapsed in the tree."""
    parts = Path(dir_path).parts
    if not parts:
        return False
    # Check if any path component is a low-value prefix
    top = parts[0].lower()
    return top in _LOW_VALUE_PREFIXES


def generate_tree(slug: str, repo_path: str) -> str:
    cdir = cards_dir(slug)
    if not cdir.exists():
        return "No cards generated yet. Run: scout warm"

    cards_by_dir: dict[str, list[Card]] = defaultdict(list)

    for card_file in cdir.rglob("*.card.json"):
        rel = os.path.relpath(card_file, cdir)
        card_rel_path = rel.removesuffix(".card.json")
        card = load_card(slug, card_rel_path)
        if card:
            dir_path = str(Path(card.rel_path).parent)
            if dir_path == ".":
                dir_path = "(root)"
            cards_by_dir[dir_path].append(card)

    if not cards_by_dir:
        return "No cards found."

    lines = ["# Repository Map\n"]

    # Surface entry points from pyproject.toml if available
    entry_points = _find_entry_points(repo_path)
    if entry_points:
        lines.append("## Entry Points")
        for ep in entry_points:
            lines.append(f"- {ep}")
        lines.append("")

    # Collapse low-value directories: group all subdirs under the
    # top-level low-value dir into one summary line
    collapsed: dict[str, dict] = {}  # top_dir -> {files, lines, subdirs}
    normal_dirs: list[str] = []

    for dir_path in sorted(cards_by_dir.keys()):
        if dir_path == "(root)":
            normal_dirs.append(dir_path)
            continue

        top = Path(dir_path).parts[0]
        if top.lower() in _LOW_VALUE_PREFIXES:
            if top not in collapsed:
                collapsed[top] = {"files": 0, "lines": 0, "subdirs": set()}
            cards = cards_by_dir[dir_path]
            collapsed[top]["files"] += len(cards)
            collapsed[top]["lines"] += sum(c.lines for c in cards)
            if dir_path != top:
                collapsed[top]["subdirs"].add(dir_path)
        else:
            normal_dirs.append(dir_path)

    # Emit normal directories with full detail
    for dir_path in normal_dirs:
        cards = cards_by_dir[dir_path]
        total_lines = sum(c.lines for c in cards)
        file_count = len(cards)

        summary = _dir_summary(cards)

        lines.append(f"## {dir_path}/ ({file_count} files, {total_lines} lines)")
        if summary:
            lines.append(summary)
        lines.append("")

    # Emit collapsed directories as single lines
    for top_dir in sorted(collapsed.keys()):
        info = collapsed[top_dir]
        subdir_count = len(info["subdirs"])
        sub_note = f", {subdir_count} subdirs" if subdir_count > 0 else ""
        lines.append(f"## {top_dir}/ ({info['files']} files, {info['lines']} lines{sub_note})")
        lines.append("")

    return "\n".join(lines)


def _dir_summary(cards: list[Card]) -> str:
    """Build a concise summary for a directory from its cards."""
    all_exports = []
    all_classes = []
    for c in cards:
        all_exports.extend(c.exports[:3])
        all_classes.extend(c.classes[:2])

    summary_parts = []
    if all_classes:
        summary_parts.append(", ".join(all_classes[:3]))
    if all_exports and not all_classes:
        summary_parts.append(", ".join(all_exports[:4]))

    if summary_parts:
        return "; ".join(summary_parts[:2])

    # Fall back to purpose keywords
    purposes = set()
    for c in cards:
        if c.purpose:
            first_word = c.purpose.split(" ")[0].rstrip("s")
            purposes.add(first_word)
    return ", ".join(sorted(purposes)[:3])


def _find_entry_points(repo_path: str) -> list[str]:
    """Extract CLI entry points from pyproject.toml or setup.cfg."""
    results = []

    # pyproject.toml
    pyproject = Path(repo_path) / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            # Parse [project.scripts] section
            in_scripts = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped == "[project.scripts]":
                    in_scripts = True
                    continue
                if in_scripts:
                    if stripped.startswith("["):
                        break
                    if "=" in stripped:
                        results.append(stripped)
        except (OSError, PermissionError):
            pass

    # package.json
    pkg_json = Path(repo_path) / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            if "main" in data:
                results.append(f"main: {data['main']}")
            if "bin" in data:
                if isinstance(data["bin"], str):
                    results.append(f"bin: {data['bin']}")
                elif isinstance(data["bin"], dict):
                    for name, path in list(data["bin"].items())[:5]:
                        results.append(f"{name} = {path}")
            scripts = data.get("scripts", {})
            for key in ("start", "dev", "build"):
                if key in scripts:
                    results.append(f"npm {key}: {scripts[key]}")
        except (OSError, json.JSONDecodeError):
            pass

    return results[:8]


def generate_dir_cards(slug: str, dir_path: str) -> str:
    cdir = cards_dir(slug)
    target = cdir / dir_path

    if not target.exists():
        return f"No cards for {dir_path}/"

    lines = [f"# Cards: {dir_path}/\n"]

    for card_file in sorted(target.rglob("*.card.json")):
        rel = os.path.relpath(card_file, cdir)
        card_rel_path = rel.removesuffix(".card.json")
        card = load_card(slug, card_rel_path)
        if card:
            lines.append(f"### {card.rel_path}")
            lines.append(f"{card.lines} lines | {card.language}")
            if card.purpose:
                lines.append(card.purpose)
            if card.exports:
                lines.append(f"Exports: {', '.join(card.exports[:5])}")
            lines.append("")

    return "\n".join(lines)
