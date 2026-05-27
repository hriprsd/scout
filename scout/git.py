"""Git operations for intent inference and working set detection."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitState:
    branch: str
    changed_files: list[str]
    staged_files: list[str]
    recent_files: list[str]
    stashed: int


def run_git(repo_path: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def get_git_state(repo_path: str) -> GitState:
    branch = run_git(repo_path, "branch", "--show-current") or "detached"

    diff_unstaged = run_git(repo_path, "diff", "--name-only")
    changed = [f for f in diff_unstaged.splitlines() if f.strip()]

    diff_staged = run_git(repo_path, "diff", "--cached", "--name-only")
    staged = [f for f in diff_staged.splitlines() if f.strip()]

    log_recent = run_git(
        repo_path, "log", "--since=8 hours ago", "--name-only",
        "--pretty=format:", "--diff-filter=ACMR",
    )
    seen = set()
    recent = []
    for f in log_recent.splitlines():
        f = f.strip()
        if f and f not in seen:
            seen.add(f)
            recent.append(f)

    stash_list = run_git(repo_path, "stash", "list")
    stash_count = len([l for l in stash_list.splitlines() if l.strip()])

    return GitState(
        branch=branch,
        changed_files=changed,
        staged_files=staged,
        recent_files=recent[:30],
        stashed=stash_count,
    )


def get_diff_stat(repo_path: str, file_path: str) -> str:
    stat = run_git(repo_path, "diff", "--numstat", "--", file_path)
    if not stat.strip():
        stat = run_git(repo_path, "diff", "--cached", "--numstat", "--", file_path)
    if not stat.strip():
        return ""
    parts = stat.split()
    if len(parts) >= 2:
        return f"+{parts[0]} -{parts[1]}"
    return ""


def is_tracked(repo_path: str, file_path: str) -> bool:
    result = run_git(repo_path, "ls-files", "--error-unmatch", file_path)
    return bool(result)


def infer_intent(repo_path: str, git_state: GitState) -> str:
    all_files = list(dict.fromkeys(
        git_state.staged_files + git_state.changed_files + git_state.recent_files
    ))
    if not all_files:
        return "No recent activity detected"

    dirs: dict[str, int] = {}
    for f in all_files:
        parts = Path(f).parts
        if len(parts) > 1:
            key = "/".join(parts[:2])
        else:
            key = parts[0] if parts else "root"
        dirs[key] = dirs.get(key, 0) + 1

    top_dir = max(dirs, key=dirs.get) if dirs else "unknown"

    branch = git_state.branch
    if "/" in branch:
        branch_type, branch_desc = branch.split("/", 1)
        desc = branch_desc.replace("-", " ").replace("_", " ")
        return f"{branch_type}: {desc} (focused on {top_dir})"

    return f"Working in {top_dir} ({len(all_files)} files touched recently)"
