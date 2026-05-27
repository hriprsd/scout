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

# Substrings that mark a top-level dir as test infrastructure
_TEST_DIR_MARKERS = {"test", "testing", "mock", "fake", "stub", "fixture", "sample"}

# Words that add no signal in summaries
_NOISE_WORDS = {
    "terraform", "python", "javascript", "typescript", "go", "rust",
    "java", "ruby", "shell", "yaml", "toml", "json", "markdown",
    "html", "css", "c", "cpp", "sql", "configuration", "module",
    "application", "service", "provide", "contain", "entry", "point",
    "for", "the", "and", "with", "from", "main", "init", "helper",
    "util", "utilitie", "implement", "definition", "file",
}

# Patterns that identify test files across languages
_TEST_FILE_PATTERNS = ("_test.go", "_test.py", "test_", "_spec.", ".spec.", ".test.")

# Files most likely to define the package's public API
_ENTRY_STEMS = {
    "__init__", "index", "main", "lib", "mod",
}
_CORE_STEMS = {
    "core", "base", "app", "engine", "types", "type",
    "model", "models", "client", "server", "api",
    "router", "context", "handler", "config",
}
_UTIL_STEMS = {
    "util", "utils", "helper", "helpers", "compat",
    "internal", "common", "misc", "tools", "version",
}
_ERROR_STEMS = {
    "error", "errors", "exception", "exceptions",
}


def _is_test_file(rel_path: str) -> bool:
    name = Path(rel_path).name
    return any(p in name for p in _TEST_FILE_PATTERNS)


def _is_test_dir(name: str) -> bool:
    """Check if a directory name indicates test infrastructure."""
    parts = {p.rstrip("s") for p in name.replace("-", "_").split("_")}
    return bool(parts & _TEST_DIR_MARKERS)


def _card_file_priority(rel_path: str, dir_name: str = "") -> int:
    """Lower = more likely to contain core API symbols."""
    stem = Path(rel_path).stem.lower()
    # File matches its containing directory (e.g. gin.go in gin/)
    if dir_name and stem == dir_name.lower().rstrip("s"):
        return 0
    if stem in _ENTRY_STEMS:
        return 0
    if stem in _CORE_STEMS:
        return 1
    if stem in _ERROR_STEMS:
        return 4
    if stem in _UTIL_STEMS:
        return 3
    # Internal modules: _compat.py, _utils.py
    if Path(rel_path).name.startswith("_") and stem.lstrip("_") not in _ENTRY_STEMS:
        return 3
    return 2


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
        lower = group_name.lower()
        if lower in _COLLAPSED_DIRS or _is_test_dir(lower):
            lines.append(f"{group_name}/ ({total_files} files, {total_lines} lines)")
            continue

        # Single directory, no subdirs
        if len(dir_paths) == 1 and dir_paths[0] == group_name:
            cards = cards_by_dir[group_name]
            summary = _dir_summary(cards, dir_name=group_name)
            detail = f" - {summary}" if summary else ""
            lines.append(f"{group_name}/ ({len(cards)} files, {total_lines} lines){detail}")
            continue

        # Group with subdirs: header uses only root-level cards
        # (not children) to avoid bubbling up child symbols
        root_cards = cards_by_dir.get(group_name, [])
        summary = _dir_summary(root_cards, dir_name=group_name)
        detail = f" - {summary}" if summary else ""
        lines.append(f"{group_name}/ ({total_files} files, {total_lines} lines){detail}")

        # Show depth-2 directories as indented lines.
        # Deeper dirs get folded into their depth-2 parent.
        depth2: dict[str, list[Card]] = defaultdict(list)
        depth3_names: dict[str, set[str]] = defaultdict(set)
        for d in dir_paths:
            parts = Path(d).parts
            if len(parts) >= 2:
                key = str(Path(parts[0]) / parts[1])
                if len(parts) >= 3:
                    depth3_names[key].add(parts[2])
            else:
                key = d
            depth2[key].extend(cards_by_dir[d])

        # Skip structural-only dirs (src/, lib/, pkg/) that just
        # mirror the parent. Fold their symbols into the group header.
        _STRUCTURAL = {"src", "lib", "pkg", "main"}
        non_structural = {
            k for k in depth2
            if k != group_name
            and Path(k).name.lower() not in _STRUCTURAL
        }
        structural = {
            k for k in depth2
            if k != group_name
            and Path(k).name.lower() in _STRUCTURAL
        }
        # If ONLY structural children, promote their content
        if structural and not non_structural:
            all_struct_cards = []
            for sk in structural:
                all_struct_cards.extend(depth2[sk])
            if all_struct_cards and not summary:
                summary = _dir_summary(all_struct_cards, dir_name=group_name)
                detail = f" - {summary}" if summary else ""
                lines[-1] = f"{group_name}/ ({total_files} files, {total_lines} lines){detail}"
            # Show depth-3 sub-packages of the structural dirs
            for sk in sorted(structural):
                sk_subs = depth3_names.get(sk, set())
                if sk_subs:
                    for sub in sorted(sk_subs):
                        sub_key_prefix = str(Path(sk) / sub)
                        sub_cards = [
                            c for d in dir_paths
                            if d.startswith(sub_key_prefix)
                            for c in cards_by_dir[d]
                        ]
                        if sub_cards:
                            sub_summary = _dir_summary(sub_cards, dir_name=sub)
                            sub_detail = f" - {sub_summary}" if sub_summary else ""
                            lines.append(f"  {sub}/ ({len(sub_cards)} files){sub_detail}")
            continue

        for child_key in sorted(depth2.keys()):
            if child_key == group_name:
                continue
            # Skip structural dirs when non-structural siblings exist
            if Path(child_key).name.lower() in _STRUCTURAL and non_structural:
                continue
            child_cards = depth2[child_key]
            child_name = str(Path(child_key).relative_to(group_name))
            sub_packages = depth3_names.get(child_key, set())
            # If many sub-packages folded in, show their names
            # instead of symbols from one arbitrary sub-package
            if len(sub_packages) > 3:
                names = sorted(sub_packages)[:8]
                names_str = ", ".join(names)
                if len(sub_packages) > 8:
                    names_str += f", +{len(sub_packages) - 8} more"
                lines.append(
                    f"  {child_name}/ ({len(child_cards)} files)"
                    f" [{names_str}]"
                )
            else:
                child_summary = _dir_summary(child_cards, dir_name=child_name)
                child_detail = f" - {child_summary}" if child_summary else ""
                lines.append(f"  {child_name}/ ({len(child_cards)} files){child_detail}")

    return "\n".join(lines)


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate while preserving order."""
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


_NOISE_SUFFIXES = ("Warning", "Error", "Exception", "Mixin")


def _symbol_rank(name: str) -> int:
    """Lower rank = more likely to be public API. Used for sorting."""
    bare = name.split("(")[0].strip()
    paren = name[len(bare):] if "(" in name else ""
    # Noise suffixes (warnings, errors, mixins) -- least interesting
    if bare.endswith(_NOISE_SUFFIXES):
        return 5
    # Underscore-prefixed -- private/internal
    if bare.startswith("_"):
        return 4
    # Exception subclasses: BadParameter(UsageError), HTTPError(Exception)
    if paren and any(x in paren for x in ("Error", "Exception")):
        return 3
    # Go unexported: lowercase initial letter, no underscore
    if bare[0:1].islower():
        return 2
    # Test-prefixed functions
    if bare.startswith("Test"):
        return 1
    # Public, exported, capitalized -- best
    return 0


def _rank_symbols(items: list[str]) -> list[str]:
    """Deduplicate and sort symbols by public-API likelihood."""
    deduped = _dedup(items)
    deduped.sort(key=_symbol_rank)
    return deduped


def _rank_functions(items: list[str]) -> list[str]:
    """Deduplicate functions by name, rank by public-API likelihood."""
    seen: set[str] = set()
    unique = []
    for f in items:
        name = f.split("(")[0].strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    unique.sort(key=_symbol_rank)
    return unique


def _dir_summary(cards: list[Card], dir_name: str = "") -> str:
    """Build a concise summary from cards, filtering noise."""
    # Words from the directory name itself are redundant
    dir_words = set()
    if dir_name:
        for part in dir_name.replace("-", "_").split("_"):
            part = part.lower().rstrip("s").strip()
            if part:
                dir_words.add(part)

    all_classes: list[str] = []
    all_exports: list[str] = []
    all_functions: list[str] = []

    # Sort: entry/core files first, test/error/util files last
    src_cards = [c for c in cards if not _is_test_file(c.rel_path)]
    test_cards = [c for c in cards if _is_test_file(c.rel_path)]
    src_cards.sort(key=lambda c: _card_file_priority(c.rel_path, dir_name))
    for c in src_cards + test_cards:
        all_classes.extend(c.classes[:3])
        all_exports.extend(c.exports[:3])
        all_functions.extend(c.functions[:4])

    all_classes = _rank_symbols(all_classes)
    all_exports = _dedup(all_exports)
    all_functions = _rank_functions(all_functions)

    # Prefer classes, then exports, then top functions
    if all_classes:
        return ", ".join(all_classes[:3])
    if all_exports:
        return ", ".join(all_exports[:4])
    if all_functions:
        return ", ".join(all_functions[:4])

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
