# Example: Scout integration for GitHub Copilot

Add this to `.github/copilot-instructions.md` in your repo.

---

## Codebase context

This project uses [scout](https://github.com/hriprsd/scout) for codebase indexing. Before exploring the codebase, run:

```bash
scout context --full
```

This gives you:
- What the developer is currently working on (from git state)
- A directory-level map of the entire repo
- Compact cards for files related to the active work

Use `scout card <file>` to get a summary of any file before reading it in full.
Use `scout tree` for a quick directory-level overview.
