# Benchmarks

Reproducible benchmarks comparing Scout against [Repomix](https://github.com/yamadashy/repomix), the most popular open-source repo-to-prompt tool.

## Methodology

Three real-world open-source repos at different scales:

| Repo | Files | Language | Why |
|------|------:|----------|-----|
| [flask](https://github.com/pallets/flask) | 265 | Python | Small, well-structured framework |
| [express](https://github.com/expressjs/express) | 242 | JavaScript | Medium, widely-used Node.js framework |
| [fastapi](https://github.com/fastapi/fastapi) | 3,002 | Python | Large, docs-heavy project |

Each repo is shallow-cloned (`--depth 1`) to get a realistic snapshot without git history overhead.

### What we measure

| Metric | How | Why it matters |
|--------|-----|----------------|
| **Output size (bytes + tokens)** | `wc -c` on stdout/file | Tokens = cost. Fewer tokens = cheaper, faster LLM calls |
| **Generation time** | Wall clock via `time.time()` | How long you wait before the LLM gets context |
| **Incremental update time** | Touch 1 file, regenerate | Real-world workflow: you edit a file, how fast does context update? |
| **Disk usage** | `du -sh` on index dir | Persistent cost on developer's machine |

### Token estimation

We use a rough heuristic of `bytes / 4` for token count. This isn't exact (real tokenizers vary by model) but is consistent across both tools and good enough for relative comparison. The actual ratio for structured text with code tends to be ~3.5-4.5 bytes per token.

### What we compare

- **Scout** `context` (L0 working set + L1 repo map) -- the default mode
- **Scout** `context --full` (L0 + L1 + L2 file cards) -- maximum detail
- **Repomix** default -- full repo dump as structured text
- **Repomix** `--compress` -- tree-sitter compressed output (removes implementation details)

Both tools run on the same machine, same repos, same conditions. No cherry-picking.

## Running

Prerequisites: `scout` installed, `node`/`npx` available, `python3` available.

```bash
bash bench.sh
```

This will:
1. Clone the three test repos to `/tmp/scout-bench/`
2. Run Scout and Repomix on each
3. Write raw results to `/tmp/scout-bench/results.md`
4. Clean up Scout indexes for the benchmark repos

To reuse already-cloned repos:
```bash
bash bench.sh --skip-clone
```

## Results

Latest run: **2026-05-27** on Apple M4 Pro (arm64).

Raw data: [results-2026-05-27.md](results-2026-05-27.md)

### Token output comparison

| Repo | Scout | Repomix | Repomix --compress | Scout reduction vs Repomix |
|------|------:|--------:|-------------------:|---------------------------:|
| Flask | ~680 | ~296K | ~227K | **436x** |
| Express | ~686 | ~181K | ~58K | **264x** |
| FastAPI | ~1.2K | ~6.0M | ~4.8M | **~5,000x** |

### Generation time

| Repo | Scout | Repomix | Repomix --compress |
|------|------:|--------:|-------------------:|
| Flask | 0.33s | 8.00s | 1.89s |
| Express | 0.29s | 1.14s | 1.17s |
| FastAPI | 0.75s | 3.04s | 2.18s |

### Incremental updates (1 file changed)

| Repo | Scout | Repomix |
|------|------:|--------:|
| Flask | 0.32s | 1.17s |
| Express | 0.28s | 1.07s |
| FastAPI | 1.13s | 1.52s |

Scout only recomputes the card for the changed file. Repomix regenerates the entire output from scratch every time.

### Disk usage (persistent index)

| Repo | Scout | Repomix |
|------|------:|--------:|
| Flask | 476 KB | 0 |
| Express | 636 KB | 0 |
| FastAPI | 11 MB | 0 |

Scout's index is small and pays for itself immediately. A single LLM call with Repomix's full output costs far more (in tokens and money) than Scout's entire on-disk index.

## Why not other tools?

We benchmarked against Repomix because it's the closest comparable open-source tool (CLI, repo-to-prompt, no vendor lock-in). Other tools we considered:

- **Aider repo-map**: Tightly coupled to Aider's conversation loop, no standalone CLI output to measure
- **code2prompt**: Requires Rust compiler for tiktoken dependency, similar approach to Repomix (full dump)
- **Cursor/Windsurf/Continue.dev**: Proprietary or IDE-embedded, no CLI to benchmark against

## Notes

- Repomix's first run includes npx download time. We use `--yes` to avoid prompts but the cached version for subsequent runs.
- Scout's `context` and `context --full` produced identical output on these repos because there was no active git work (clean clones). In a real workflow with uncommitted changes, `--full` includes L2 cards for files related to your work, adding more tokens.
- Token counts are estimates. Use your model's tokenizer for exact numbers.
