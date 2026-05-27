"""Card generation, caching, and management.

A card is a compact summary of a source file (~50 tokens) designed
to be concatenated directly into an LLM prompt.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from scout.config import cards_dir, repo_dir
from scout.hash import file_hash
from scout.parser import parse_file, ParseResult, detect_language


@dataclass
class Card:
    rel_path: str
    language: str
    lines: int
    source_hash: str
    generated_at: float
    purpose: str = ""
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)


def card_path(slug: str, rel_path: str) -> Path:
    return cards_dir(slug) / (rel_path + ".card.json")


def load_card(slug: str, rel_path: str) -> Card | None:
    cp = card_path(slug, rel_path)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text())
        return Card(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def save_card(slug: str, card: Card) -> None:
    cp = card_path(slug, card.rel_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(asdict(card), indent=2) + "\n")


def generate_card(repo_path: str, slug: str, rel_path: str, force: bool = False) -> Card | None:
    abs_path = Path(repo_path) / rel_path

    if not abs_path.is_file():
        return None

    lang = detect_language(abs_path)
    if lang is None:
        return None

    h = file_hash(abs_path)

    if not force:
        existing = load_card(slug, rel_path)
        if existing and existing.source_hash == h:
            return existing

    try:
        content = abs_path.read_text(errors="replace")
    except (OSError, PermissionError):
        return None

    line_count = content.count("\n") + 1
    parsed = parse_file(abs_path, content)

    if parsed is None:
        return None

    purpose = _infer_purpose(rel_path, parsed)

    card = Card(
        rel_path=rel_path,
        language=lang,
        lines=line_count,
        source_hash=h,
        generated_at=time.time(),
        purpose=purpose,
        imports=parsed.imports,
        exports=parsed.exports,
        functions=parsed.functions,
        classes=parsed.classes,
        types=parsed.types,
        constants=parsed.constants,
    )

    save_card(slug, card)
    return card


def render_card(card: Card, diff_stat: str = "") -> str:
    parts = [f"# {card.rel_path}"]
    meta = f"{card.lines} lines | {card.language}"
    if diff_stat:
        meta += f" | {diff_stat}"
    parts.append(meta)

    if card.purpose:
        parts.append(f"\n## Purpose\n{card.purpose}")

    if card.exports:
        parts.append(f"\n## Public API\n" + "\n".join(f"- {e}" for e in card.exports))

    if card.functions:
        parts.append(f"\n## Functions\n" + "\n".join(f"- {f}" for f in card.functions))

    if card.classes:
        parts.append(f"\n## Classes/Structs\n" + "\n".join(f"- {c}" for c in card.classes))

    if card.types:
        parts.append(f"\n## Types\n" + "\n".join(f"- {t}" for t in card.types))

    if card.imports:
        trimmed = card.imports[:10]
        parts.append(f"\n## Imports\n" + "\n".join(f"- {i}" for i in trimmed))
        if len(card.imports) > 10:
            parts.append(f"  ... and {len(card.imports) - 10} more")

    return "\n".join(parts)


def _infer_purpose(rel_path: str, parsed: ParseResult) -> str:
    path = Path(rel_path)
    name = path.stem.lower()
    parent = path.parent.name.lower() if path.parent.name else ""

    keywords = {
        "test": "Tests",
        "spec": "Tests",
        "mock": "Test mocks",
        "fixture": "Test fixtures",
        "config": "Configuration",
        "setting": "Settings",
        "model": "Data models",
        "schema": "Schema definitions",
        "migration": "Database migration",
        "route": "Route definitions",
        "handler": "Request handlers",
        "controller": "Controller",
        "middleware": "Middleware",
        "service": "Service layer",
        "util": "Utilities",
        "helper": "Helper functions",
        "constant": "Constants",
        "type": "Type definitions",
        "interface": "Interface definitions",
        "api": "API layer",
        "auth": "Authentication",
        "index": "Module entry point",
        "main": "Application entry point",
        "setup": "Setup/initialization",
        "init": "Initialization",
        "cli": "CLI interface",
        "command": "CLI commands",
    }

    for keyword, label in keywords.items():
        if keyword in name or keyword in parent:
            context = parent if parent and parent != keyword else name
            return f"{label} for {context}"

    top_exports = parsed.exports[:3]
    if top_exports:
        return f"Provides {', '.join(top_exports)}"

    top_classes = parsed.classes[:2]
    if top_classes:
        return f"Defines {', '.join(top_classes)}"

    top_funcs = parsed.functions[:3]
    if top_funcs:
        names = [f.split("(")[0] for f in top_funcs]
        return f"Contains {', '.join(names)}"

    return f"{parsed.language} module"


def collect_files(repo_path: str, ignore_patterns: list[str]) -> list[str]:
    result = []
    repo = Path(repo_path)

    ignore_set = set(ignore_patterns)

    for root, dirs, files in os.walk(repo):
        rel_root = os.path.relpath(root, repo)

        dirs[:] = [
            d for d in dirs
            if d not in ignore_set
            and not d.startswith(".")
            and not any(
                _matches_pattern(os.path.join(rel_root, d), p)
                for p in ignore_patterns
            )
        ]

        for f in files:
            if f.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(root, f), repo)
            if any(_matches_pattern(rel, p) for p in ignore_patterns):
                continue
            if detect_language(Path(f)) is not None:
                result.append(rel)

    return sorted(result)


def _matches_pattern(path: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        return path.endswith(pattern[1:])
    return pattern in path.split(os.sep)
