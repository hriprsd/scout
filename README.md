<p align="center">
  <img src="assets/logo.png" alt="Scout" width="200">
  <br>
  <em>A German Shorthaired Pointer. They find things.</em>
</p>

<h1 align="center">Scout</h1>
<p align="center">Codebase context for LLMs, zero waste.</p>

<p align="center">
  <strong>Zero dependencies. Pure Python. Works with any tool.</strong>
</p>

---

- [The problem](#the-problem)
- [How Scout works](#how-scout-works)
- [Why Scout over existing tools](#why-scout-over-existing-tools)
- [Install](#install)
- [Command reference](#command-reference)
- [How it works internally](#how-it-works-internally)
- [Supported languages](#supported-languages)
- [Integration examples](#integration-examples)
- [Benchmarks](#benchmarks)
- [Blog posts](#blog-posts)
- [Roadmap](#roadmap)

---

Scout builds a lightweight, hierarchical index of your codebase that any AI coding tool can consume. It gives the LLM just enough context to understand your repo and what you're working on, without dumping thousands of files into the prompt.

```
scout init .
scout warm
scout context | pbcopy   # paste into any LLM
```

## The problem

Every AI coding tool burns tokens on context. Most approaches either dump the entire repo (millions of tokens, slow, expensive) or use embeddings and vector databases (heavy infrastructure, stale indexes, locked to one tool).

You shouldn't need a vector database to tell an LLM where your auth middleware lives.

## How Scout works

Scout generates a **card** for every source file: a compact summary (~50 tokens) containing the file's purpose, public API, function signatures, imports, and types. Cards are content-addressed (keyed by SHA-256 of the source). If the file hasn't changed, the card is valid forever. No recomputation.

Context is served in three tiers:

| Tier | What | Token cost |
|------|------|-----------|
| **L0 - Working set** | Full content of files you're actively changing, inferred from git | 1-10K |
| **L1 - Repo map** | One-line summary per directory | 0.5-2K |
| **L2 - File cards** | Per-file cards with signatures and exports | ~50 per file |

For a 29-file repo, `scout context` produces ~84 tokens. The raw files are ~9M tokens. On Django (7,048 files), `scout context` produces 34 lines that show the full module hierarchy, key types (`AppConfig`, `Signal`, `Atomic`, `cached_property`), and the entry point. The ratio gets better as repos grow because most files are cold and only the L1 directory line exists in the output.

## Why Scout over existing tools

| | Scout | Cursor / Windsurf | Continue.dev | Aider repo-map | Repomix / code2prompt |
|---|---|---|---|---|---|
| **Dependencies** | Zero | Proprietary IDE | LanceDB, transformers.js, embedding model | In-process, pip install | CLI, npm |
| **Infrastructure** | None. Flat files on disk | Cloud vector DB | Local vector DB | SQLite | None |
| **Platform lock** | None. Any tool reads the output | Cursor only | VS Code / JetBrains | Aider only | Any (but no persistence) |
| **Persistence** | Content-addressed cards, survives anything | Cloud-synced | Local DB, rebuilds on corruption | SQLite cache | Regenerated from scratch every time |
| **Token efficiency** | Hierarchical: L0 + L1 + L2 on demand | Top-k chunk retrieval | Top-k chunk retrieval | Flat ranked list, 1K budget | Full repo dump |
| **Intent awareness** | Git-native: branch, diff, log, mtime | Editor state (requires IDE) | Current file + query | Conversation context | None |
| **Privacy** | Fully local, nothing leaves your machine | Embeddings sent to cloud | Local (unless using cloud embeddings) | Local | Local |
| **Per-developer** | Yes, stored in ~/.scout/ per user | Cloud account | Local per-machine | In-process | No |
| **Offline** | Yes | No | Depends on embedding provider | Yes | Yes |

### What this means in practice

**Tool-agnostic by design.** Scout outputs markdown. Claude Code, Cursor, Copilot, Vim, Emacs, whatever you use next year. If it can read a file, it works with Scout.

**Intent from git, not editor plugins.** Scout reads `git diff`, `git log`, and `git branch` to figure out what you're working on. Switch editors, switch tools, the context stays accurate. No plugin required.

**Content-addressed, not time-based.** Cursor re-syncs every 3-10 minutes. Continue reindexes in background. Scout checks the file hash. Unchanged file = valid card. Zero wasted compute.

**Hierarchical, not all-or-nothing.** Other tools either give you everything (Repomix) or a flat top-k ranking (embedding tools). Scout gives the LLM a table of contents first (L1), then details on demand (L2), then full source only for files being edited (L0). The LLM decides what depth it needs.

## Install

```bash
git clone https://github.com/hriprsd/scout.git
cd scout
bash install.sh
```

That's it. The script:
- Checks for Python >= 3.10
- Creates an isolated venv at `~/.scout/env/` (doesn't touch your system Python)
- Installs scout into the venv
- Symlinks the `scout` binary to `~/.local/bin/`

Options:
```bash
bash install.sh              # default: symlink to ~/.local/bin
bash install.sh --global     # symlink to /usr/local/bin (needs sudo)
bash install.sh --dir ~/bin  # symlink to a custom directory
bash install.sh --upgrade    # reinstall over existing installation
```

Requires Python 3.10+. Zero external dependencies.

## Command reference

### `scout init`

Register repositories with scout.

```bash
scout init                                # current directory
scout init path/to/repo                   # single repo
scout init repo1 repo2 repo3              # multiple repos at once
scout init ~/projects --scan              # discover all git repos under a directory
scout init ~/projects --scan --warm       # discover + immediately generate cards
```

| Flag | What it does |
|------|-------------|
| `--scan` | Instead of treating the path as a repo, scan it for child directories that contain `.git`. Useful for indexing all repos under a parent folder in one shot. |
| `--warm` | Run `scout warm` on each repo immediately after init. Without this, repos are registered but cards aren't generated until you run `scout warm` separately. |

Installs lightweight git hooks (post-commit, post-checkout, post-merge) that keep cards fresh automatically. Hooks are local to `.git/hooks/` and don't affect other developers.

### `scout warm`

Generate or refresh cards for all files in a repo. This is the indexing step.

```bash
scout warm                # current repo
scout warm path/to/repo   # specific repo
scout warm --force        # regenerate all cards, ignoring cache
```

**How warm works:** Scout walks every supported source file in the repo, computes its SHA-256 hash, and checks if a card already exists with that hash. If so, the card is skipped (cache hit). If not, it parses the file, extracts structure (imports, exports, functions, classes, types), and writes a `.card.json`. This makes warm fully incremental. Only changed files are re-processed.

| Flag | What it does |
|------|-------------|
| `--force` | Ignore the content hash cache and regenerate every card. Useful if you change scout versions or want a clean slate. |

**When to warm:**
- After `scout init` (first time)
- After pulling a large update (`git pull` with many changed files)
- You generally don't need to warm manually after that. Git hooks refresh cards on commit/checkout/merge automatically.

Typical performance: **200 files in ~0.2 seconds**.

### `scout context`

Emit context for LLM consumption. This is the main command.

```bash
scout context                # L0 workset + L1 tree (default)
scout context --full         # also include L2 cards for related files
scout context --tree-only    # just the repo map
scout context --workset-only # just the working set
scout context | pbcopy       # copy to clipboard
```

Output goes to stdout. Status messages go to stderr. Safe to pipe.

### `scout card`

Show or regenerate a card for a specific file.

```bash
scout card src/auth/middleware.ts
scout card src/api/routes.py --path /other/repo
```

Example output:
```
# src/auth/middleware.ts
142 lines | typescript

## Purpose
Middleware for auth

## Public API
- validateToken
- requireRole
- refreshSession

## Functions
- validateToken(req, res, next)
- requireRole(...roles: string[]): Middleware
- refreshSession(req): Promise<Session>

## Imports
- import { verify } from "jsonwebtoken"
- import { findUser } from "../db/users"
```

### `scout tree`

Show the repository map (L1 directory summaries).

```bash
scout tree
scout tree path/to/repo
```

### `scout ls`

List all cards in a specific directory.

```bash
scout ls src/auth
scout ls tests --path /other/repo
```

### `scout status`

Show card coverage, staleness, and repo info.

```bash
scout status
scout status path/to/repo
```

### `scout gc`

Remove cards for files that no longer exist.

```bash
scout gc                # prune stale cards
scout gc --dry-run      # preview what would be removed
```

## How it works internally

1. **Parsing**: Regex-based extraction of imports, exports, function signatures, class definitions, and types. Covers Python, TypeScript/JavaScript, Go, Rust, Java, Ruby, and 20+ other languages. Tree-sitter integration planned.

2. **Card generation**: Each file gets a `.card.json` stored in `~/.scout/repos/<slug>/cards/`, mirroring the repo's directory structure. Cards contain structured metadata, not prose.

3. **Content addressing**: Each card records the SHA-256 hash of its source file. On `scout warm`, unchanged files are skipped instantly. On `scout context`, stale cards are noted but still usable.

4. **Intent inference**: `scout context` reads git state (staged changes, unstaged changes, recent commits, branch name) to determine what you're working on and includes full source for active files.

5. **Git hooks**: `scout init` installs lightweight post-commit/checkout/merge hooks that refresh cards for changed files in the background.

## Storage

Everything lives in `~/.scout/`:

```
~/.scout/
  env/                        # isolated venv (created by install.sh)
  repos/
    my-app-a1b2c3/
      meta.json               # repo path, last warm, branch
      cards/
        src/
          auth/
            middleware.ts.card.json
            session.ts.card.json
          api/
            routes.ts.card.json
```

Cards for a 29-file repo: **124KB**. That's 0.03% of the repo size. For a 1000-file repo, expect ~4MB.

## Supported languages

Python, TypeScript, JavaScript, JSX, TSX, Go, Rust, Java, Kotlin, Ruby, PHP, C, C++, C#, Swift, Scala, Shell, Lua, R, SQL, Terraform/HCL, YAML, TOML, JSON, HTML, CSS, SCSS, Vue, Svelte, Zig, Elixir, Erlang, Clojure, Dart, Markdown.

The regex parser extracts meaningful structure from all of these. Languages not in this list are skipped (binary files, images, lock files, etc. are always ignored).

## Integration examples

Ready-to-use config files are in the [`examples/`](examples/) directory.

### Claude Code

Copy `examples/CLAUDE.md` to your global `~/.claude/CLAUDE.md` (append it) or to your project root. This tells Claude to use scout for codebase navigation instead of reading files blindly.

Key instruction it adds:
> Run `scout context` to get the L0 workset + L1 repo map. Run `scout card <file>` before reading a file in full. Prefer scout cards over opening files just to understand what they contain.

### Cursor

Copy `examples/scout.mdc` to `~/.cursor/rules/scout.mdc` (global) or `.cursor/rules/scout.mdc` (project-level). This applies to all conversations and tells Cursor to use scout before exploring files.

### GitHub Copilot

Copy `examples/copilot-instructions.md` to `.github/copilot-instructions.md` in your repo.

### Any LLM chat

```bash
scout context | pbcopy
# paste into ChatGPT, Claude, Gemini, whatever
```

## Uninstall

```bash
bash uninstall.sh              # remove scout, keep your indexed data
bash uninstall.sh --purge      # remove scout AND all indexed data
bash uninstall.sh --dry-run    # preview what would be removed
```

This removes the venv, the symlink, and cleans scout hooks from any registered repos. Your indexed cards in `~/.scout/repos/` are kept unless you pass `--purge`.

## Benchmarks

Measured on Apple M4 Pro. Scout vs [Repomix](https://github.com/yamadashy/repomix), the most popular repo-to-prompt tool.

### Flask (265 files)

| Metric | Scout | Repomix | Repomix --compress |
|--------|------:|--------:|-------------------:|
| **Output size** | 2.7 KB (~680 tokens) | 1.2 MB (~296K tokens) | 907 KB (~227K tokens) |
| **Generation time** | 0.33s | 8.00s | 1.89s |
| **Token reduction** | **1x (baseline)** | **436x larger** | **334x larger** |

### Express (242 files)

| Metric | Scout | Repomix | Repomix --compress |
|--------|------:|--------:|-------------------:|
| **Output size** | 2.7 KB (~686 tokens) | 723 KB (~181K tokens) | 231 KB (~58K tokens) |
| **Generation time** | 0.29s | 1.14s | 1.17s |
| **Token reduction** | **1x (baseline)** | **264x larger** | **84x larger** |

### FastAPI (3,002 files)

| Metric | Scout | Repomix | Repomix --compress |
|--------|------:|--------:|-------------------:|
| **Output size** | 4.7 KB (~1.2K tokens) | 23.9 MB (~6.0M tokens) | 19.2 MB (~4.8M tokens) |
| **Generation time** | 0.75s | 3.04s | 2.18s |
| **Token reduction** | **1x (baseline)** | **~5,000x larger** | **~4,000x larger** |

### Incremental updates (1 file changed)

| Repo | Scout | Repomix |
|------|------:|--------:|
| Flask | 0.32s | 1.17s |
| Express | 0.28s | 1.07s |
| FastAPI | 1.13s | 1.52s |

### Disk usage (persistent index)

| Repo | Scout | Repomix |
|------|------:|--------:|
| Flask | 476 KB | 0 (no index) |
| Express | 636 KB | 0 (no index) |
| FastAPI | 11 MB | 0 (no index) |

Scout trades a small amount of disk space for dramatically fewer tokens and faster incremental updates. The index pays for itself immediately -- even one LLM call with Repomix's output costs more than Scout's entire index on disk.

### Beyond tokens: functional comparison

Fewer tokens doesn't mean less useful. Scout's context is structurally complete -- the LLM gets the same navigational information in a fraction of the space.

**Context window limits.** Repomix output for Flask (296K tokens) doesn't fit in GPT-4o (128K) or Claude (200K). FastAPI at ~6M tokens doesn't fit in any model. Scout output is always under 8K tokens -- fits everywhere.

**Intent awareness.** Scout reads your git state and tells the LLM what you're working on. Active files get full source. Everything else gets a one-line directory summary. Repomix dumps all files equally regardless of what you're doing.

**Signal density.** For a single file like Flask's `helpers.py` (684 lines): Scout's card is 358 tokens (signatures, imports, exports). Repomix default is 6,160 tokens (full source). 17x more tokens for the same navigational value. The LLM doesn't need to read every line to know what `flash()` does.

**Progressive disclosure.** Scout gives the LLM a table of contents first, details on demand. Repomix gives everything at once. For a typical Flask task, Repomix dumps 230 files when you probably need 30.

Detailed analysis with examples in [`benchmarks/functional-comparison.md`](benchmarks/functional-comparison.md). Full methodology and reproduction steps in [`benchmarks/`](benchmarks/).

## Blog posts

- [I Built a Codebase Indexer That Uses 700x Fewer Tokens Than Dumping Your Repo](https://medium.com/@hriprsd/i-built-a-codebase-indexer-that-uses-700x-fewer-tokens-than-dumping-your-repo-9c8314f86a23)
- [Building Scout Part 2: Regex Parsers, Content Addressing, and Zero Dependencies](https://medium.com/@hriprsd/building-scout-part-2-regex-parsers-content-addressing-and-zero-dependencies-cc976eaac339)

## Roadmap

- [ ] `scout watch` - filesystem watcher for real-time card updates
- [ ] `scout mcp` - MCP server for direct tool integration
- [ ] Tree-sitter parsing (replace regex for better accuracy)
- [ ] Reverse dependency tracking (who imports this file)
- [ ] `scout diff` - show what changed in context since last session
- [ ] Configurable card format (customize what fields to include)

## License

MIT
