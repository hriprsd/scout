"""Directory tree generation (L1 summaries)."""

from __future__ import annotations

import json
import os
import re
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
    "bench", "benchmark", "benchmarks",
    "scripts", "script", "tools", "hack",
    "changelogs", "changelog",
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
    # Split on -, _, and camelCase boundaries (split BEFORE lowercasing)
    expanded = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    parts = {p.rstrip("s").lower() for p in expanded.replace("-", "_").split("_")}
    return bool(parts & _TEST_DIR_MARKERS)


_LOW_SIGNAL_PARTS = {
    "test", "tests", "spec", "specs", "__tests__",
    "examples", "example", "bench", "benchmarks", "benchmark",
    "fixtures", "testdata", "test_data", "testcases",
    "snapshots", "__snapshots__",
}


def _has_test_ancestor(rel_path: str) -> bool:
    """Check if any path component is a test/example/bench directory."""
    for part in Path(rel_path).parts[:-1]:  # skip filename
        if part.lower() in _LOW_SIGNAL_PARTS or _is_test_dir(part):
            return True
    return _is_test_file(rel_path)


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


def _collapse_depth2_children(
    child_keys: list[str],
    group_name: str,
) -> list[str]:
    """Collapse homogeneous depth-2 siblings into one line.

    Detects numbered patterns (problem_001, problem_002, ...) and
    prefix-based repetition. Returns a list of child_keys with
    collapsed groups replaced by pre-formatted "[COLLAPSED]..." entries.
    """
    if len(child_keys) <= 8:
        return child_keys

    # Extract the child name portion and find common prefixes
    prefix_groups: dict[str, list[str]] = defaultdict(list)
    for k in child_keys:
        name = Path(k).name
        # Strip trailing digits/underscores to find prefix
        prefix = re.sub(r"[\d_]+$", "", name)
        if prefix and prefix != name:
            prefix_groups[prefix].append(k)

    result: list[str] = []
    consumed: set[str] = set()
    for prefix, members in prefix_groups.items():
        if len(members) < 5:
            continue
        consumed.update(members)
        total = len(members)
        result.append(
            f"[COLLAPSED]  {prefix}*/ ({total} dirs)"
        )

    # Add non-consumed children normally
    for k in child_keys:
        if k not in consumed:
            result.append(k)

    return result


def _collapse_sibling_groups(
    groups: dict[str, list[str]],
    cards_by_dir: dict[str, list[Card]],
) -> dict[str, list[str]]:
    """Merge groups that share a prefix into one collapsed entry.

    Detects patterns like pages.ar/, pages.bg/, ... and merges them
    into a single pages.{ar,bg,...}/ group. Triggers when 5+ groups
    share the same prefix (split on '.', '-', '_').
    """
    # Find prefixes shared by many groups
    prefix_members: dict[str, list[str]] = defaultdict(list)
    for name in groups:
        if name == "(root)":
            continue
        # Try splitting on common delimiters
        for sep in (".", "-", "_"):
            if sep in name:
                prefix = name.split(sep, 1)[0]
                prefix_members[f"{prefix}{sep}"].append(name)
                break

    result = dict(groups)
    for prefix, members in prefix_members.items():
        if len(members) < 5:
            continue
        # Only collapse if members have similar internal structure.
        # Compare depth-2 child dir names across members.
        child_sets = []
        for m in members:
            children = set()
            for d in groups[m]:
                parts = Path(d).parts
                if len(parts) >= 2:
                    children.add(parts[1])
            child_sets.append(children)
        # Check structural similarity: >50% of members share the same
        # child dir names (e.g. all have common/, linux/, osx/)
        if child_sets:
            reference = child_sets[0]
            similar = sum(
                1 for cs in child_sets[1:]
                if reference and cs and len(cs & reference) / max(len(reference), 1) > 0.5
            )
            if similar < len(members) * 0.5:
                continue  # structurally diverse, don't collapse

        merged_dirs: list[str] = []
        suffixes = []
        for m in sorted(members):
            merged_dirs.extend(groups[m])
            suffix = m[len(prefix):]
            suffixes.append(suffix)
            del result[m]
        shown = sorted(suffixes)[:6]
        suffix_str = ",".join(shown)
        if len(suffixes) > 6:
            suffix_str += f",+{len(suffixes) - 6}"
        collapsed_name = f"{prefix}{{{suffix_str}}}"
        result[collapsed_name] = merged_dirs
    return result


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

    # Collapse homogeneous sibling groups that share a prefix
    # (e.g. pages.ar/, pages.bg/, ... → pages.{ar,bg,...}/)
    groups = _collapse_sibling_groups(groups, cards_by_dir)

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
        # Synthetic collapsed groups from sibling merging
        if "{" in group_name:
            lines.append(f"{group_name}/ ({total_files} files, {total_lines} lines)")
            continue
        if lower in _COLLAPSED_DIRS or _is_test_dir(group_name):
            lines.append(f"{group_name}/ ({total_files} files, {total_lines} lines)")
            continue

        # Single directory, no subdirs
        if len(dir_paths) == 1 and dir_paths[0] == group_name:
            cards = cards_by_dir[group_name]
            summary = _dir_summary(cards, dir_name=group_name)
            detail = f" - {summary}" if summary else ""
            lines.append(f"{group_name}/ ({len(cards)} files, {total_lines} lines){detail}")
            continue

        # Group with subdirs: prefer root-level cards for header,
        # but fall back to all cards if root only has functions
        # (catches Ruby/Go where init file has methods, not classes)
        root_cards = cards_by_dir.get(group_name, [])
        summary = _dir_summary(root_cards, dir_name=group_name)
        if summary and not any(c.classes for c in root_cards):
            # Root summary is function-only; check if children have classes
            all_group_cards = [c for d in dir_paths for c in cards_by_dir[d]]
            class_summary = _dir_summary(all_group_cards, dir_name=group_name)
            if class_summary != summary:
                summary = class_summary
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

        # Structural dirs (src/, lib/, pkg/, main/) just mirror
        # the parent. Fold their content into the group header.
        _STRUCTURAL = {"src", "lib", "pkg", "main"}
        _SKIP_SUBS = _STRUCTURAL | {"test", "tests"}
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
        if structural and not non_structural:
            # Collect source-only cards (skip test paths)
            src_cards_list = [
                c for sk in structural for c in depth2[sk]
                if not _has_test_ancestor(c.rel_path)
            ]
            if src_cards_list and not summary:
                summary = _dir_summary(src_cards_list, dir_name=group_name)
                detail = f" - {summary}" if summary else ""
                lines[-1] = f"{group_name}/ ({total_files} files, {total_lines} lines){detail}"
            # Promote depth-3 children, skipping structural and test dirs
            visible_subs: list[tuple[str, str, list[Card]]] = []
            for sk in sorted(structural):
                for sub in sorted(depth3_names.get(sk, set())):
                    if sub.lower() in _SKIP_SUBS or _is_test_dir(sub):
                        continue
                    sub_prefix = str(Path(sk) / sub)
                    sub_cards = [
                        c for d in dir_paths
                        if d.startswith(sub_prefix)
                        for c in cards_by_dir[d]
                    ]
                    if sub_cards:
                        visible_subs.append((sub, sub_prefix, sub_cards))
            # Only show sub-lines if there's real variety
            if len(visible_subs) > 1:
                for sub, _, sub_cards in visible_subs:
                    sub_summary = _dir_summary(sub_cards, dir_name=sub)
                    sub_detail = f" - {sub_summary}" if sub_summary else ""
                    lines.append(f"  {sub}/ ({len(sub_cards)} files){sub_detail}")
            continue

        # Detect homogeneous depth-2 children (problem_001..problem_800)
        child_keys = [k for k in sorted(depth2.keys()) if k != group_name]
        if non_structural:
            child_keys = [
                k for k in child_keys
                if Path(k).name.lower() not in _STRUCTURAL or not non_structural
            ]
        collapsed_children = _collapse_depth2_children(child_keys, group_name)

        # Track symbols across siblings to dedupe codegen scaffolding
        sibling_symbol_count: dict[str, int] = defaultdict(int)
        for ck in child_keys:
            for c in depth2.get(ck, []):
                for cls in c.classes[:2]:
                    sibling_symbol_count[cls.split("(")[0].strip()] += 1
        # Symbols appearing in 5+ siblings are likely auto-generated
        codegen_symbols = {s for s, n in sibling_symbol_count.items() if n >= 5}

        for child_entry in collapsed_children:
            if child_entry.startswith("[COLLAPSED]"):
                # Pre-formatted collapsed line
                lines.append(child_entry.removeprefix("[COLLAPSED]"))
                continue
            child_key = child_entry
            child_cards = depth2[child_key]
            child_name = str(Path(child_key).relative_to(group_name))
            sub_packages = depth3_names.get(child_key, set())
            # Filter out structural and test dirs from sub-package names
            visible_pkgs = {
                s for s in sub_packages
                if s.lower() not in _SKIP_SUBS and not _is_test_dir(s)
            }
            # If many sub-packages folded in, show their names
            # instead of symbols from one arbitrary sub-package
            if len(visible_pkgs) > 6:
                names = sorted(visible_pkgs)[:8]
                names_str = ", ".join(names)
                if len(visible_pkgs) > 8:
                    names_str += f", +{len(visible_pkgs) - 8} more"
                lines.append(
                    f"  {child_name}/ ({len(child_cards)} files)"
                    f" [{names_str}]"
                )
            elif len(visible_pkgs) > 3:
                # Medium count: expand each sub-package with symbols
                lines.append(f"  {child_name}/ ({len(child_cards)} files)")
                for pkg in sorted(visible_pkgs):
                    pkg_prefix = str(Path(child_key) / pkg)
                    pkg_cards = [
                        c for d in dir_paths
                        if d.startswith(pkg_prefix)
                        for c in cards_by_dir[d]
                    ]
                    if pkg_cards:
                        pkg_summary = _dir_summary(pkg_cards, dir_name=pkg,
                                                    exclude=codegen_symbols)
                        pkg_detail = f" - {pkg_summary}" if pkg_summary else ""
                        lines.append(f"    {pkg}/ ({len(pkg_cards)} files){pkg_detail}")
            else:
                child_summary = _dir_summary(child_cards, dir_name=child_name,
                                              exclude=codegen_symbols)
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

# Test fixture / placeholder names that add zero signal
_FIXTURE_NAMES = {
    "foo", "bar", "baz", "qux", "quux", "corge", "grault",
    "myclass", "mytest", "myapp", "mymodule", "mytype",
    "someclass", "sometype", "example", "sample", "demo",
    "testclass", "testtype", "testcase",
    "main",  # every binary has one, not distinctive
}


def _symbol_rank(name: str) -> int:
    """Lower rank = more likely to be public API. Used for sorting."""
    bare = name.split("(")[0].strip()
    paren = name[len(bare):] if "(" in name else ""
    # Single-letter names (X, F, I, C, U) -- test placeholders
    if len(bare) <= 2 and bare.isalpha():
        return 6
    # Known fixture/placeholder names
    if bare.lower().rstrip("0123456789") in _FIXTURE_NAMES:
        return 6
    # Noise suffixes (warnings, errors, mixins) -- least interesting
    if bare.endswith(_NOISE_SUFFIXES):
        return 5
    # Underscore-prefixed -- private/internal
    if bare.startswith("_"):
        return 4
    # Exception subclasses: BadParameter(UsageError), HTTPError(Exception)
    if paren and any(x in paren for x in ("Error", "Exception")):
        return 3
    # Enum and TypedDict types are supporting, not primary API
    if paren and any(x in paren for x in ("enum.", "Enum", "IntEnum", "TypedDict")):
        return 2
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


def _dir_summary(cards: list[Card], dir_name: str = "",
                  exclude: set[str] | None = None) -> str:
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

    # Collect from source files only. Test/example/fixture symbols
    # are omitted entirely -- they contain placeholders (Foo, X, etc.)
    # that displace real API types.
    src_cards = [c for c in cards if not _has_test_ancestor(c.rel_path)]
    src_cards.sort(key=lambda c: _card_file_priority(c.rel_path, dir_name))
    for c in src_cards:
        all_classes.extend(c.classes[:3])
        all_exports.extend(c.exports[:3])
        all_functions.extend(c.functions[:4])

    all_classes = _rank_symbols(all_classes)
    all_exports = _dedup(all_exports)
    all_functions = _rank_functions(all_functions)

    # Filter out codegen/duplicate symbols from parent
    if exclude:
        all_classes = [c for c in all_classes
                       if c.split("(")[0].strip() not in exclude]
        all_exports = [e for e in all_exports if e not in exclude]
        all_functions = [f for f in all_functions if f not in exclude]

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
