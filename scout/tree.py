"""Directory tree generation (L1 summaries)."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from scout.card import Card, load_card
from scout.config import cards_dir


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

    for dir_path in sorted(cards_by_dir.keys()):
        cards = cards_by_dir[dir_path]
        total_lines = sum(c.lines for c in cards)
        file_count = len(cards)

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

        purposes = set()
        for c in cards:
            if c.purpose:
                first_word = c.purpose.split(" ")[0].rstrip("s")
                purposes.add(first_word)

        summary = "; ".join(summary_parts[:2]) if summary_parts else ", ".join(sorted(purposes)[:3])

        lines.append(f"## {dir_path}/ ({file_count} files, {total_lines} lines)")
        if summary:
            lines.append(f"{summary}")
        lines.append("")

    return "\n".join(lines)


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
