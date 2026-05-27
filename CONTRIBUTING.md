# Contributing to Scout

Thanks for your interest in contributing. Here's what you need to know.

## Setup

```bash
git clone https://github.com/hriprsd/scout.git
cd scout
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Project structure

```
scout/
  cli.py        # CLI entry point (argparse)
  config.py     # Paths, slugs, ignore patterns
  card.py       # Card generation and caching
  parser.py     # Language-aware regex parsing
  context.py    # L0/L1/L2 context assembly
  git.py        # Git state and intent inference
  tree.py       # Directory tree generation
  hash.py       # Content-addressed hashing
```

About 1,400 lines of Python total.

## Rules

**Zero dependencies.** Scout uses only the Python standard library. Do not add packages to `dependencies` in `pyproject.toml`. If you need something that isn't in stdlib, find another way or discuss it in an issue first.

**Python 3.10+.** Use modern syntax (type unions with `|`, match statements are fine) but don't require 3.12+ features.

**Match the existing style.** The codebase is straightforward and minimal. No classes where a function will do. No abstractions for the sake of abstraction.

**Test your changes.** Run `scout warm` and `scout context` on a real repo before submitting. If you're adding a new language parser, test it against a well-known open source project in that language.

## Adding a new language parser

1. Add the file extension to `LANGUAGE_MAP` in `parser.py`
2. Write a `_parse_<language>()` function following the pattern of existing parsers
3. The function should extract: imports, exports, functions (with signatures), classes, types, constants
4. Don't worry about perfect parsing. "Good enough for navigation" is the bar. If a regex catches 90% of function declarations in that language, that's fine.
5. Test against a real repo. Run `scout card <file>` on several files and check the output makes sense.

## Submitting changes

1. Fork the repo
2. Create a branch (`feat/xxx` or `fix/xxx`)
3. Make your changes
4. Test on at least one real repo
5. Open a PR with a short description of what and why

Keep PRs focused. One feature or fix per PR. If you want to do multiple things, open multiple PRs.

## Reporting bugs

Open an issue with:
- What you ran
- What you expected
- What happened instead
- Your Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
