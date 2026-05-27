"""Directory tree generation (L1 summaries)."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from scout.card import Card, load_card
from scout.config import cards_dir

# Top-level dirs that get a single collapsed line
_COLLAPSED_DIRS = {
    "test", "tests", "spec", "specs", "__tests__",
    "docs", "doc", "documentation",
    ".github", ".circleci", ".gitlab",
    "examples", "example", "samples",
    "fixtures", "testdata", "test_data",
    "static", "public", "assets",
    "vendor", "third_party",
}

# Words that add no signal in summaries
_NOISE_WORDS = {
    "terraform", "python", "javascript", "typescript", "go", "rust",
    "java", "ruby", "shell", "yaml", "toml", "json", "markdown",
    "html", "css", "c", "cpp", "sql", "configuration", "module",
    "application", "service", "provide", "contain", "entry", "point",
    "for", "the", "and", "with", "from", "main", "init", "helper",
    "util", "utilitie", "implement", "definition", "file",
}


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

    # Entry points
    entry_points = _find_entry_points(repo_path)
    if entry_points:
        for ep in entry_points:
            lines.append(f"Entry: {ep}")
        lines.append("")

    # Group dirs by top-level parent
    groups: dict[str, list[str]] = defaultdict(list)
    for dir_path in sorted(cards_by_dir.keys()):
        if dir_path == "(root)":
            groups["(root)"].append(dir_path)
        else:
            top = Path(dir_path).parts[0]
            groups[top].append(dir_path)

    for group_name in sorted(groups.keys()):
        dir_paths = groups[group_name]

        # Root files
        if group_name == "(root)":
            cards = cards_by_dir["(root)"]
            summary = _dir_summary(cards)
            detail = f" - {summary}" if summary else ""
            lines.append(f"./ ({len(cards)} files){detail}")
            continue

        # Aggregate stats
        total_files = sum(len(cards_by_dir[d]) for d in dir_paths)
        total_lines = sum(
            sum(c.lines for c in cards_by_dir[d]) for d in dir_paths
        )

        # Collapsed dirs: single line, no children
        if group_name.lower() in _COLLAPSED_DIRS:
            lines.append(f"{group_name}/ ({total_files} files, {total_lines} lines)")
            continue

        # Single directory, no subdirs
        if len(dir_paths) == 1 and dir_paths[0] == group_name:
            cards = cards_by_dir[group_name]
            summary = _dir_summary(cards, dir_name=group_name)
            detail = f" - {summary}" if summary else ""
            lines.append(f"{group_name}/ ({len(cards)} files, {total_lines} lines){detail}")
            continue

        # Group with subdirs: header + indented children
        all_cards = []
        for d in dir_paths:
            all_cards.extend(cards_by_dir[d])
        summary = _dir_summary(all_cards, dir_name=group_name)
        detail = f" - {summary}" if summary else ""
        lines.append(f"{group_name}/ ({total_files} files, {total_lines} lines){detail}")

        # Show depth-2 directories as indented lines.
        # Deeper dirs get folded into their depth-2 parent.
        depth2: dict[str, list[Card]] = defaultdict(list)
        for d in dir_paths:
            parts = Path(d).parts
            if len(parts) >= 2:
                key = str(Path(parts[0]) / parts[1])
            else:
                key = d
            depth2[key].extend(cards_by_dir[d])

        for child_key in sorted(depth2.keys()):
            if child_key == group_name:
                continue
            child_cards = depth2[child_key]
            child_name = str(Path(child_key).relative_to(group_name))
            child_summary = _dir_summary(child_cards, dir_name=child_name)
            child_detail = f" - {child_summary}" if child_summary else ""
            lines.append(f"  {child_name}/ ({len(child_cards)} files){child_detail}")

    return "\n".join(lines)


def _dir_summary(cards: list[Card], dir_name: str = "") -> str:
    """Build a concise summary from cards, filtering noise."""
    # Words from the directory name itself are redundant
    dir_words = set()
    if dir_name:
        for part in dir_name.replace("-", "_").split("_"):
            part = part.lower().rstrip("s").strip()
            if part:
                dir_words.add(part)

    all_classes = []
    all_exports = []
    all_functions = []
    for c in cards:
        all_classes.extend(c.classes[:2])
        all_exports.extend(c.exports[:3])
        all_functions.extend(c.functions[:2])

    # Prefer classes, then exports, then top functions
    if all_classes:
        return ", ".join(all_classes[:3])
    if all_exports:
        return ", ".join(all_exports[:4])
    if all_functions:
        names = []
        for f in all_functions[:4]:
            name = f.split("(")[0].strip()
            if name:
                names.append(name)
        if names:
            return ", ".join(names)

    # No structural symbols found. Don't fall back to purpose keywords
    # because they're usually noise ("Application entry point for X").
    # The directory name and file count are enough.
    return ""


def _find_entry_points(repo_path: str) -> list[str]:
    """Extract CLI entry points from pyproject.toml or package.json."""
    results = []

    pyproject = Path(repo_path) / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
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
