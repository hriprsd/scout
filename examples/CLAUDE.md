# Example: Scout integration for Claude Code

Add this to your global `~/.claude/CLAUDE.md` or project-level `CLAUDE.md`.

---

## Codebase context via Scout

**Always run `scout context` before reading any files in a repo.** This gives you the full repo structure and my active working set in ~700 tokens instead of opening files blind. Only read full files when you need to edit them.

- If `scout context` fails with a "not initialized" error, run `scout init . && scout warm` first, then retry.
- `scout context` - L0 workset (what I'm actively changing) + L1 repo map (directory summaries). Start here, every time.
- `scout context --full` - also include L2 file cards for files related to what I'm working on.
- `scout card <file>` - compact summary of a specific file. Run this before reading a file in full.
- `scout tree` - directory-level overview of the entire repo.
- Do not open files just to understand what they contain. Use scout cards instead.
