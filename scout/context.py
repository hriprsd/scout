"""Context assembly - the main output of scout.

Produces a hierarchical context blob optimized for LLM consumption:
  L0 - Working set (cards for active files, full source only with --full)
  L1 - Repository tree (directory summaries)
  L2 - Cards for related files
"""

from __future__ import annotations

from pathlib import Path

from scout.card import load_card, render_card, cards_dir
from scout.config import repo_dir
from scout.git import get_git_state, get_diff_stat, infer_intent
from scout.tree import generate_tree


def generate_context(
    repo_path: str,
    slug: str,
    include_workset: bool = True,
    include_tree: bool = True,
    include_related: bool = False,
    max_file_lines: int = 300,
) -> str:
    sections: list[str] = []

    if include_workset:
        # Only inline full source when --full is requested
        workset = _build_workset(repo_path, slug, max_file_lines,
                                 inline_source=include_related)
        if workset:
            sections.append(workset)

    if include_tree:
        tree = generate_tree(slug, repo_path)
        sections.append(tree)

    if include_related:
        related = _build_related(repo_path, slug)
        if related:
            sections.append(related)

    return "\n---\n\n".join(sections)


def _build_workset(repo_path: str, slug: str, max_lines: int,
                   inline_source: bool = False) -> str:
    git_state = get_git_state(repo_path)
    intent = infer_intent(repo_path, git_state)

    lines = ["# Current Work"]
    lines.append(f"Branch: {git_state.branch}")
    lines.append(f"Intent: {intent}")

    all_active = list(dict.fromkeys(
        git_state.staged_files + git_state.changed_files
    ))

    if all_active:
        lines.append(f"\n## Active Files ({len(all_active)} changed)\n")
        for rel_path in all_active:
            abs_path = Path(repo_path) / rel_path
            diff = get_diff_stat(repo_path, rel_path)
            status = "staged" if rel_path in git_state.staged_files else "unstaged"
            lines.append(f"### {rel_path} ({status}, {diff})")

            card = load_card(slug, rel_path)
            if card:
                lines.append(f"*{card.purpose}*")

            if inline_source and abs_path.is_file():
                # --full mode: inline the actual source
                try:
                    content = abs_path.read_text(errors="replace")
                    file_lines = content.splitlines()
                    lines.append("")
                    if len(file_lines) <= max_lines:
                        lines.append(f"```{_ext_lang(abs_path)}")
                        lines.append(content)
                        lines.append("```\n")
                    else:
                        lines.append(f"```{_ext_lang(abs_path)}")
                        lines.append("\n".join(file_lines[:max_lines]))
                        lines.append("```")
                        lines.append(f"*... truncated ({len(file_lines)} lines total)*\n")
                except (OSError, PermissionError):
                    lines.append("*unreadable*\n")
            elif card:
                # Default mode: show the card instead of full source
                lines.append("")
                if card.functions:
                    lines.append("Functions: " + ", ".join(card.functions[:8]))
                if card.classes:
                    lines.append("Classes: " + ", ".join(card.classes[:5]))
                if card.imports:
                    lines.append("Imports: " + ", ".join(card.imports[:6]))
                lines.append("")

    if git_state.recent_files:
        recent_only = [
            f for f in git_state.recent_files
            if f not in all_active
        ][:10]
        if recent_only:
            lines.append(f"\n## Recently Committed\n")
            for rel_path in recent_only:
                card = load_card(slug, rel_path)
                if card:
                    lines.append(f"- {rel_path} - {card.purpose}")
                else:
                    lines.append(f"- {rel_path}")

    if git_state.stashed:
        lines.append(f"\n*{git_state.stashed} stash(es) available*")

    return "\n".join(lines)


def _build_related(repo_path: str, slug: str) -> str:
    git_state = get_git_state(repo_path)
    active = set(git_state.staged_files + git_state.changed_files)

    if not active:
        return ""

    active_imports: set[str] = set()
    for rel_path in active:
        card = load_card(slug, rel_path)
        if card:
            for imp in card.imports:
                parts = imp.split()
                for p in parts:
                    cleaned = p.strip("\"';,{}")
                    if "/" in cleaned or "." in cleaned:
                        active_imports.add(cleaned)

    cdir = cards_dir(slug)
    if not cdir.exists():
        return ""

    related_cards: list[str] = []
    for card_file in cdir.rglob("*.card.json"):
        import os
        rel = os.path.relpath(card_file, cdir)
        card_rel = rel.removesuffix(".card.json")
        if card_rel in active:
            continue
        card = load_card(slug, card_rel)
        if card is None:
            continue

        is_related = False
        for imp in active_imports:
            if card_rel in imp or Path(card_rel).stem in imp:
                is_related = True
                break

        for exp in card.exports:
            if any(exp in (c_imp) for c_imp in active_imports):
                is_related = True
                break

        if is_related:
            related_cards.append(render_card(card))

    if not related_cards:
        return ""

    header = f"# Related Files ({len(related_cards)} cards)\n"
    return header + "\n\n".join(related_cards[:15])


def _ext_lang(path: Path) -> str:
    mapping = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".jsx": "jsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".rb": "ruby", ".php": "php", ".sh": "bash",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
        ".sql": "sql", ".css": "css", ".html": "html", ".md": "markdown",
        ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    }
    return mapping.get(path.suffix.lower(), "")
