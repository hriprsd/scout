"""Configuration and path management for scout."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

SCOUT_HOME = Path.home() / ".scout"
CONFIG_FILE = SCOUT_HOME / "config.toml"


@dataclass
class RepoMeta:
    path: str
    slug: str
    last_warm: Optional[str] = None
    branch: Optional[str] = None
    card_count: int = 0
    ignore_patterns: list[str] = field(default_factory=lambda: [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", ".nuxt", "target", "vendor",
        ".scout", ".cards", "*.min.js", "*.min.css", "*.map",
        "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.svg",
        "*.woff", "*.woff2", "*.ttf", "*.eot", "*.mp3", "*.mp4",
        "*.zip", "*.tar", "*.gz", "*.pdf", "*.bin", "*.exe",
        "*.pyc", "*.pyo", "*.so", "*.dylib", "*.dll",
    ])


def repo_slug(repo_path: str) -> str:
    name = Path(repo_path).name
    short_hash = hashlib.sha256(repo_path.encode()).hexdigest()[:8]
    return f"{name}-{short_hash}"


def repo_dir(slug: str) -> Path:
    return SCOUT_HOME / "repos" / slug


def cards_dir(slug: str) -> Path:
    return repo_dir(slug) / "cards"


def load_meta(slug: str) -> Optional[RepoMeta]:
    meta_file = repo_dir(slug) / "meta.json"
    if not meta_file.exists():
        return None
    data = json.loads(meta_file.read_text())
    return RepoMeta(**data)


def save_meta(slug: str, meta: RepoMeta) -> None:
    meta_file = repo_dir(slug) / "meta.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(asdict(meta), indent=2) + "\n")


def find_repo_slug_by_path(repo_path: str) -> Optional[str]:
    repos_root = SCOUT_HOME / "repos"
    if not repos_root.exists():
        return None
    for d in repos_root.iterdir():
        if not d.is_dir():
            continue
        meta_file = d / "meta.json"
        if meta_file.exists():
            data = json.loads(meta_file.read_text())
            if data.get("path") == repo_path:
                return d.name
    return None


def resolve_slug(repo_path: Optional[str] = None) -> tuple[str, RepoMeta]:
    if repo_path is None:
        repo_path = _find_git_root()
    repo_path = str(Path(repo_path).resolve())
    slug = find_repo_slug_by_path(repo_path)
    if slug is None:
        raise SystemExit(f"Repo not initialized. Run: scout init {repo_path}")
    meta = load_meta(slug)
    if meta is None:
        raise SystemExit(f"Corrupted repo metadata for {slug}")
    return slug, meta


def _find_git_root() -> str:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists():
            return str(parent)
    raise SystemExit("Not inside a git repository. Run from a repo or pass a path.")
