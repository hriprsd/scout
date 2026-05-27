"""Directory tree generation (L1 summaries)."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from scout.card import Card, load_card
from scout.config import cards_dir

# Top-level dirs that get a single collapsed line (no subdirs listed)
_COLLAPSED_DIRS = {
    "test", "tests", "spec", "specs", "__tests__",
    "docs", "doc", "documentation",
    ".github", ".circleci", ".gitlab",
    "examples", "example", "samples",
    "fixtures", "testdata", "test_data",
    "static", "public", "assets",
    "vendor", "third_party",
}

# Summary words that are noise (language names, obvious labels)
_NOISE_WORDS = {
    "terraform", "python", "javascript", "typescript", "go", "rust",
    "java", "ruby", "shell", "yaml", "toml", "json", "markdown",
    "html", "css", "c", "cpp", "sql", "configuration", "module",
    "application",
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

    # Group all dirs by their top-level parent
    groups: dict[str, list[str]] = defaultdict(list)
    for dir_path in sorted(cards_by_dir.keys()):
        if dir_path == "(root)":
            groups["(root)"].append(dir_path)
        else:
            top = Path(dir_path).parts[0]
            groups[top].append(dir_path)

    # Render each group
    for group_name in sorted(groups.keys()):
        dir_paths = groups[group_name]

        if group_name == "(root)":
            cards = cards_by_dir["(root)"]
            summary = _dir_summary(cards)
            detail = f" - {summary}" if summary else ""
            lines.append(f"./ ({len(cards)} files){detail}")
            continue

        # Aggregate stats for the whole group
        total_files = sum(len(cards_by_dir[d]) for d in dir_paths)
        total_lines = sum(
            sum(c.lines for c in cards_by_dir[d]) for d in dir_paths
        )

        # Collapsed dirs or groups with many subdirs: single line
        if (group_name.lower() in _COLLAPSED_DIRS
                or len(dir_paths) > 6):
            sub_count = len(dir_paths) - (1 if group_name in dir_paths else 0)
            sub_note = f", {sub_count} subdirs" if sub_count > 0 else ""
            # For large groups, list the subdir names compactly
            if len(dir_paths) > 6 and group_name.lower() not in _COLLAPSED_DIRS:
                child_names = []
                for d in dir_paths:
                    parts = Path(d).parts
                    if len(parts) == 2:
                        child_names.append(parts[1])
                if child_names:
                    names_str = ", ".join(child_names[:12])
                    if len(child_names) > 12:
                        names_str += f", +{len(child_names) - 12} more"
                    lines.append(
                        f"{group_name}/ ({total_files} files, "
                        f"{total_lines} lines{sub_note})"
                    )
                    lines.append(f"  [{names_str}]")
                else:
                    lines.append(
                        f"{group_name}/ ({total_files} files, "
                        f"{total_lines} lines{sub_note})"
                    )
            else:
                lines.append(
                    f"{group_name}/ ({total_files} files, "
                    f"{total_lines} lines{sub_note})"
                )
            continue

        # Small group (1-6 subdirs): show top-level with summary,
        # then subdirs indented
        if len(dir_paths) == 1:
            d = dir_paths[0]
            cards = cards_by_dir[d]
            summary = _dir_summary(cards)
            detail = f" - {summary}" if summary else ""
            lines.append(
                f"{d}/ ({len(cards)} files, "
                f"{sum(c.lines for c in cards)} lines){detail}"
            )
        else:
            # Group header
            all_cards = []
            for d in dir_paths:
                all_cards.extend(cards_by_dir[d])
            summary = _dir_summary(all_cards)
            detail = f" - {summary}" if summary else ""
            lines.append(
                f"{group_name}/ ({total_files} files, "
                f"{total_lines} lines){detail}"
            )
            # Subdirs as indented lines
            for d in dir_paths:
                if d == group_name:
                    continue
                cards = cards_by_dir[d]
                # Show relative path from group
                rel = str(Path(d).relative_to(group_name))
                sub_summary = _dir_summary(cards)
                sub_detail = f" - {sub_summary}" if sub_summary else ""
                lines.append(
                    f"  {rel}/ ({len(cards)} files){sub_detail}"
                )

    return "\n".join(lines)


def _dir_summary(cards: list[Card]) -> str:
    """Build a concise summary from cards, filtering noise."""
    all_classes = []
    all_exports = []
    for c in cards:
        all_classes.extend(c.classes[:2])
        all_exports.extend(c.exports[:3])

    # Prefer classes, then exports
    symbols = all_classes[:3] if all_classes else all_exports[:4]
    if symbols:
        return ", ".join(symbols)

    # Fall back to purpose keywords, filtering noise
    purposes = set()
    for c in cards:
        if c.purpose:
            for word in c.purpose.lower().split():
                word = word.rstrip("s").strip()
                if word and word not in _NOISE_WORDS and len(word) > 2:
                    purposes.add(word)
    filtered = sorted(purposes)[:3]
    return ", ".join(filtered) if filtered else ""


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
