# Example: Scout integration for Claude Code

Add this to your global `~/.claude/CLAUDE.md` or project-level `CLAUDE.md`.

---

## Codebase context via Scout

Before exploring an unfamiliar repo or when you need to understand the project structure, run `scout context` to get a hierarchical summary of the codebase and current working set. This is cheaper than reading files individually.

- Run `scout context` to get the L0 workset (what I'm actively changing) + L1 repo map (directory summaries).
- Run `scout context --full` to also include L2 file cards for files related to what I'm working on.
- Run `scout card <file>` to get a compact summary of a specific file before reading it in full.
- Run `scout tree` for a quick directory-level overview.
- If scout is not initialized for the repo, run `scout init . && scout warm` first.
- Prefer reading scout cards over opening files just to understand what they contain. Only read the full file when you need to edit it or see implementation details.
