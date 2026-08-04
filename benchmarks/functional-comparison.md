# Functional Comparison: Scout vs Repomix

Performance benchmarks show Scout uses 100-700x fewer tokens. But does the LLM actually get enough information to work with? This document answers that question.

## 1. Context window feasibility

Most LLMs have hard context limits. If your repo context doesn't fit, the tool is useless.

| Model | Context window | Flask (265 files) | Express (242 files) | FastAPI (3,002 files) |
|-------|---------------:|:------------------:|:-------------------:|:---------------------:|
| GPT-4o | 128K | | | |
| Claude Sonnet | 200K | | | |
| Gemini 2.5 Pro | 1M | | | |

**Repomix output fits?**

| Model | Flask (296K tokens) | Express (181K tokens) | FastAPI (6.0M tokens) |
|-------|:-------------------:|:---------------------:|:---------------------:|
| GPT-4o (128K) | No | No | No |
| Claude Sonnet (200K) | No | Yes | No |
| Gemini 2.5 Pro (1M) | Yes | Yes | No |

**Scout output fits?**

| Model | Flask (680 tokens) | Express (686 tokens) | FastAPI (1.2K tokens) |
|-------|:------------------:|:--------------------:|:---------------------:|
| GPT-4o (128K) | Yes | Yes | Yes |
| Claude Sonnet (200K) | Yes | Yes | Yes |
| Gemini 2.5 Pro (1M) | Yes | Yes | Yes |

Scout output fits in every model's context window, every time. Repomix output doesn't fit in GPT-4o for even a 265-file project, and can't handle FastAPI on any model.

Even Repomix `--compress` doesn't solve this -- Flask compressed is still 227K tokens (exceeds GPT-4o and Claude), and FastAPI compressed is 4.8M tokens (exceeds everything).

This isn't a nice-to-have optimization. For large repos, it's the difference between "works" and "doesn't work."

## 2. Signal density

Both tools cover the same codebase. The question is: how much of each tool's output is actually useful signal vs noise?

### What the LLM sees

Using Flask's `src/flask/helpers.py` (684 lines) as an example:

**Scout card (358 tokens):**
```
# src/flask/helpers.py
684 lines | python

## Purpose
Helper functions for flask

## Public API
- get_debug_flag
- get_load_dotenv
- make_response
- abort
- get_template_attribute
- flash
- _prepare_send_file_kwargs
- get_root_path
- _split_blueprint_path
- _CollectErrors

## Functions
- get_debug_flag(()) -> bool
- get_load_dotenv((default: bool = True)) -> bool
- make_response((*args: t.Any)) -> Response
- abort((code: int | BaseResponse, *args: t.Any, **kwargs: t.Any)) -> t.NoReturn
- flash((message: str, category: str = "message")) -> None
  ... (full signatures for all 20+ functions)

## Classes/Structs
- _CollectErrors

## Imports
- from __future__ import annotations
- import werkzeug.utils
- from .globals import current_app, request, session
  ... (all 22 imports)
```

The LLM knows: what this file does, every public function and its signature, what it imports, what classes it defines. Enough to decide if it needs the full file.

**Repomix default (6,160 tokens):**
The entire 684-line source file, including docstrings, implementation details, error handling, internal helpers, comments, and blank lines. 17x more tokens for the same navigational value.

**Repomix --compress (4,636 tokens):**
Tree-sitter compressed version. Removes some implementation but keeps docstrings, partial function bodies, and formatting. Still 13x more tokens than Scout's card.

### Per-file cost

| | Scout card | Repomix --compress | Repomix default |
|---|---:|---:|---:|
| **helpers.py** | 358 tokens | 4,636 tokens | 6,160 tokens |
| **Ratio** | 1x | 13x | 17x |

The LLM doesn't need to read every line of `helpers.py` to know that `flash()` takes a message and category. Scout gives it the index; it can request the full file if it actually needs to edit it.

### File relevance

For a typical task like "add a new CLI command to Flask," here's what Repomix dumps:

| Category | Files | Useful for this task? |
|----------|------:|:---------------------:|
| Source code (`src/`) | 26 | Yes |
| Tests (`tests/`) | 61 | Maybe a few |
| Documentation (`docs/`) | 82 | No |
| CI/config (`.github/`) | 11 | No |
| Examples (`examples/`) | 42 | No |
| Other | 8 | No |
| **Total** | **230** | **~30 (13%)** |

Repomix dumps 230 files. For most tasks, you need maybe 30 of them. The other 200 files (87% of the output) are noise that the LLM has to read through, burning tokens and attention.

Scout maps all 230 files in its directory tree (one line each) but only expands the ones relevant to your current work. The LLM sees the full picture at directory level and can drill into specific files on demand.

## 3. Intent awareness

This is where Scout does something Repomix fundamentally can't.

### Scenario: you're editing two files

You've staged a change to `src/flask/helpers.py` and have unsaved changes in `tests/test_basic.py`.

**Scout output (with active changes):**
```
# Current Work
Branch: main
Intent: Working in src/flask (2 files touched recently)

## Active Files (2 changed)

### src/flask/helpers.py (staged, +1 -0)
*Helper functions for flask*

[full source of helpers.py - the file you're editing]

### tests/test_basic.py (unstaged, +1 -0)
*Test module*

[full source of test_basic.py - the other file you're editing]

---

# Repository Map
[one-line summary for every directory]
```

Scout tells the LLM:
- What branch you're on
- What you're probably working on (inferred from git state)
- Full source of the files you're actively changing
- A map of everything else for navigation

**Repomix output (same scenario):**
Identical to before. All 230 files, all 296K tokens. No indication of what you're working on. No prioritization. The LLM has to figure out your intent from the conversation alone.

### Why this matters

When you say "add error handling to this function," the LLM needs to know *which* function, *which* file, and *what* you're currently doing. Scout provides this context from git. Repomix provides a 1.2MB haystack and hopes the LLM finds the needle.

## 4. Progressive disclosure

Scout is designed around a hierarchy: overview first, details on demand.

```
scout context          →  L0 (active files) + L1 (directory map)     ~680 tokens
scout context --full   →  L0 + L1 + L2 (cards for related files)    ~2-8K tokens
scout card <file>      →  Single file card                           ~50-400 tokens
[read the actual file] →  Full source                                ~500-5K tokens
```

The LLM starts with the map, identifies what it needs, and drills in. This matches how a human developer navigates a codebase: you don't read every file, you look at the directory structure, check a few key files, then focus on what matters.

Repomix gives you one option: everything at once. There's no "give me just the overview" mode. You get the full dump or nothing.

## 5. Incremental updates

After you edit a single file:

| | Scout | Repomix |
|---|---|---|
| **What happens** | Recomputes 1 card (the changed file) | Regenerates entire output from scratch |
| **Time** | 0.28-1.13s | 1.07-1.52s |
| **Output change** | Only the changed file's section differs | Entire output is regenerated |

Scout's content-addressed cards mean unchanged files are never reprocessed. The SHA-256 hash of the source matches the existing card, so it's skipped. This is a fundamental architectural advantage, not just an optimization.

## Summary

| Capability | Scout | Repomix |
|---|---|---|
| Fits in any model's context window | Always (under 8K tokens) | Often doesn't fit |
| Knows what you're working on | Yes (git state) | No |
| Progressive detail levels | L0 / L1 / L2 / full source | All or nothing |
| Per-file signal density | ~358 tokens (signatures + API) | ~6,160 tokens (full source) |
| Relevant file prioritization | Active files first, rest as map | All files equal |
| Incremental cost | 1 card recomputed | Full regeneration |

Scout doesn't give the LLM less information. It gives the same structural information in fewer tokens, prioritized by what you're actually doing. The LLM can always request more detail. With Repomix, it gets everything whether it needs it or not.
