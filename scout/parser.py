"""Language-aware parsing for card generation.

Uses regex-based extraction with a trait-like interface so tree-sitter
can be plugged in later. Covers the top languages well enough for v0.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".lua": "lua",
    ".r": "r", ".R": "r",
    ".sql": "sql",
    ".tf": "terraform", ".hcl": "terraform",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".vue": "vue", ".svelte": "svelte",
    ".zig": "zig",
    ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
    ".dart": "dart",
}


@dataclass
class ParseResult:
    language: str
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)


def detect_language(path: Path) -> str | None:
    return LANGUAGE_MAP.get(path.suffix.lower())


def parse_file(path: Path, content: str | None = None) -> ParseResult | None:
    lang = detect_language(path)
    if lang is None:
        return None

    if content is None:
        try:
            content = path.read_text(errors="replace")
        except (OSError, PermissionError):
            return None

    result = ParseResult(language=lang)

    lines = content.splitlines()
    if len(lines) > 10_000:
        lines = lines[:10_000]

    parser = _PARSERS.get(lang, _parse_generic)
    parser(lines, result)

    result.imports = result.imports[:30]
    result.exports = result.exports[:50]
    result.functions = result.functions[:50]
    result.classes = result.classes[:30]
    result.types = result.types[:30]
    result.constants = result.constants[:20]

    return result


def _parse_python(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import "):
            r.imports.append(stripped.split("#")[0].strip())
        elif stripped.startswith("from ") and "import" in stripped:
            r.imports.append(stripped.split("#")[0].strip())
        elif re.match(r"^def\s+(\w+)", stripped):
            m = re.match(r"^def\s+(\w+)\s*\(([^)]*)\)", stripped)
            if m:
                name, params = m.group(1), m.group(2)
                ret = ""
                ret_match = re.search(r"->\s*(.+?):", stripped)
                if ret_match:
                    ret = f" -> {ret_match.group(1).strip()}"
                sig = f"{name}({_truncate_params(params)}){ret}"
                r.functions.append(sig)
                if not line.startswith(" ") and not line.startswith("\t"):
                    r.exports.append(name)
        elif re.match(r"^class\s+(\w+)", stripped):
            m = re.match(r"^class\s+(\w+)(\([^)]*\))?", stripped)
            if m:
                name = m.group(1)
                bases = m.group(2) or ""
                r.classes.append(f"{name}{bases}")
                if not line.startswith(" ") and not line.startswith("\t"):
                    r.exports.append(name)
        elif re.match(r"^[A-Z_][A-Z0-9_]*\s*=", stripped) and not line.startswith(" "):
            name = stripped.split("=")[0].strip()
            r.constants.append(name)
        elif stripped.startswith("@dataclass") or stripped.startswith("@typing"):
            pass
        elif re.match(r"^(\w+):\s*TypeAlias", stripped):
            r.types.append(stripped.split("=")[0].strip())
        elif stripped.startswith("__all__"):
            match = re.search(r"\[([^\]]+)\]", stripped)
            if match:
                names = re.findall(r"['\"](\w+)['\"]", match.group(1))
                r.exports = names


def _parse_typescript(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if re.match(r"^import\s", stripped):
            r.imports.append(stripped.rstrip(";"))
        elif re.match(r"^export\s+(default\s+)?(async\s+)?function\s+(\w+)", stripped):
            m = re.match(r"^export\s+(default\s+)?(async\s+)?function\s+(\w+)\s*(\([^)]*\))?", stripped)
            if m:
                name = m.group(3)
                params = m.group(4) or "()"
                r.functions.append(f"{name}{_truncate_params(params)}")
                r.exports.append(name)
        elif re.match(r"^(async\s+)?function\s+(\w+)", stripped):
            m = re.match(r"^(async\s+)?function\s+(\w+)\s*(\([^)]*\))?", stripped)
            if m:
                r.functions.append(f"{m.group(2)}{_truncate_params(m.group(3) or '()')}")
        elif re.match(r"^export\s+(default\s+)?class\s+(\w+)", stripped):
            m = re.match(r"^export\s+(default\s+)?class\s+(\w+)(\s+extends\s+\w+)?", stripped)
            if m:
                name = m.group(2) + (m.group(3) or "")
                r.classes.append(name)
                r.exports.append(m.group(2))
        elif re.match(r"^class\s+(\w+)", stripped):
            m = re.match(r"^class\s+(\w+)(\s+extends\s+\w+)?", stripped)
            if m:
                r.classes.append(m.group(1) + (m.group(2) or ""))
        elif re.match(r"^export\s+(type|interface)\s+(\w+)", stripped):
            m = re.match(r"^export\s+(type|interface)\s+(\w+)", stripped)
            if m:
                r.types.append(m.group(2))
                r.exports.append(m.group(2))
        elif re.match(r"^(type|interface)\s+(\w+)", stripped):
            m = re.match(r"^(type|interface)\s+(\w+)", stripped)
            if m:
                r.types.append(m.group(2))
        elif re.match(r"^export\s+(const|let|var)\s+(\w+)", stripped):
            m = re.match(r"^export\s+(const|let|var)\s+(\w+)", stripped)
            if m:
                r.exports.append(m.group(2))
        elif re.match(r"^export\s*\{", stripped):
            names = re.findall(r"(\w+)(?:\s+as\s+\w+)?", stripped)
            r.exports.extend([n for n in names if n not in ("export", "as", "default")])
        elif re.match(r"^const\s+(\w+)\s*=\s*(async\s+)?\(", stripped):
            m = re.match(r"^const\s+(\w+)\s*=\s*(async\s+)?\(([^)]*)\)", stripped)
            if m:
                r.functions.append(f"{m.group(1)}({_truncate_params(m.group(3))})")


def _parse_go(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import "):
            if '"' in stripped:
                r.imports.append(stripped)
        elif stripped.startswith('"') and stripped.endswith('"'):
            r.imports.append(f"import {stripped}")
        elif re.match(r"^func\s+(\([^)]+\)\s+)?(\w+)", stripped):
            m = re.match(r"^func\s+(\([^)]+\)\s+)?(\w+)\s*(\([^)]*\))", stripped)
            if m:
                receiver = m.group(1) or ""
                name = m.group(2)
                params = m.group(3)
                sig = f"{receiver}{name}{_truncate_params(params)}"
                r.functions.append(sig)
                if name[0].isupper():
                    r.exports.append(name)
        elif re.match(r"^type\s+(\w+)\s+(struct|interface)", stripped):
            m = re.match(r"^type\s+(\w+)\s+(struct|interface)", stripped)
            if m:
                r.classes.append(f"{m.group(1)} {m.group(2)}")
                if m.group(1)[0].isupper():
                    r.exports.append(m.group(1))
        elif re.match(r"^type\s+(\w+)\s+", stripped):
            m = re.match(r"^type\s+(\w+)", stripped)
            if m:
                r.types.append(m.group(1))
        elif re.match(r"^const\s+(\w+)", stripped):
            m = re.match(r"^const\s+(\w+)", stripped)
            if m:
                r.constants.append(m.group(1))


def _parse_rust(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("use "):
            r.imports.append(stripped.rstrip(";"))
        elif re.match(r"^pub(\s*\(crate\))?\s+(async\s+)?fn\s+(\w+)", stripped):
            m = re.match(r"^pub(\s*\(crate\))?\s+(async\s+)?fn\s+(\w+)\s*(\([^)]*\))?", stripped)
            if m:
                name = m.group(3)
                params = m.group(4) or "()"
                r.functions.append(f"{name}{_truncate_params(params)}")
                r.exports.append(name)
        elif re.match(r"^(async\s+)?fn\s+(\w+)", stripped):
            m = re.match(r"^(async\s+)?fn\s+(\w+)\s*(\([^)]*\))?", stripped)
            if m:
                r.functions.append(f"{m.group(2)}{_truncate_params(m.group(3) or '()')}")
        elif re.match(r"^pub\s+(struct|enum)\s+(\w+)", stripped):
            m = re.match(r"^pub\s+(struct|enum)\s+(\w+)", stripped)
            if m:
                r.classes.append(f"{m.group(1)} {m.group(2)}")
                r.exports.append(m.group(2))
        elif re.match(r"^(struct|enum)\s+(\w+)", stripped):
            m = re.match(r"^(struct|enum)\s+(\w+)", stripped)
            if m:
                r.classes.append(f"{m.group(1)} {m.group(2)}")
        elif re.match(r"^pub\s+trait\s+(\w+)", stripped):
            m = re.match(r"^pub\s+trait\s+(\w+)", stripped)
            if m:
                r.types.append(f"trait {m.group(1)}")
                r.exports.append(m.group(1))
        elif re.match(r"^pub\s+type\s+(\w+)", stripped):
            m = re.match(r"^pub\s+type\s+(\w+)", stripped)
            if m:
                r.types.append(m.group(1))
                r.exports.append(m.group(1))


def _parse_java(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import "):
            r.imports.append(stripped.rstrip(";"))
        elif re.match(r"^(public|protected|private)?\s*(static\s+)?(abstract\s+)?class\s+(\w+)", stripped):
            m = re.match(r"^(public|protected|private)?\s*(static\s+)?(abstract\s+)?class\s+(\w+)(\s+extends\s+\w+)?", stripped)
            if m:
                r.classes.append(m.group(4) + (m.group(5) or ""))
                if m.group(1) == "public":
                    r.exports.append(m.group(4))
        elif re.match(r"^(public|protected|private)?\s*(static\s+)?(abstract\s+)?interface\s+(\w+)", stripped):
            m = re.match(r"interface\s+(\w+)", stripped)
            if m:
                r.types.append(m.group(1))
        elif re.match(r"^\s*(public|protected|private)\s+.*\w+\s*\(", stripped):
            m = re.match(r"^\s*(public|protected|private)\s+(static\s+)?(\w[\w<>\[\],\s]*?)\s+(\w+)\s*\(([^)]*)\)", stripped)
            if m:
                ret_type = m.group(3)
                name = m.group(4)
                params = m.group(5)
                r.functions.append(f"{name}({_truncate_params(params)}): {ret_type}")


def _parse_ruby(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("require ") or stripped.startswith("require_relative "):
            r.imports.append(stripped)
        elif re.match(r"^class\s+(\w+)", stripped):
            m = re.match(r"^class\s+(\w+)(\s*<\s*\w+)?", stripped)
            if m:
                r.classes.append(m.group(1) + (m.group(2) or ""))
                r.exports.append(m.group(1))
        elif re.match(r"^module\s+(\w+)", stripped):
            m = re.match(r"^module\s+(\w+)", stripped)
            if m:
                r.types.append(f"module {m.group(1)}")
        elif re.match(r"^\s*def\s+(\w+[\w?!]*)", stripped):
            m = re.match(r"^\s*def\s+(self\.)?(\w+[\w?!]*)\s*(\([^)]*\))?", stripped)
            if m:
                prefix = "self." if m.group(1) else ""
                r.functions.append(f"{prefix}{m.group(2)}{m.group(3) or ''}")


def _parse_yaml(lines: list[str], r: ParseResult) -> None:
    """Parser for YAML files. Extracts nothing.

    YAML structural keys (apiVersion, kind, metadata) appear in every
    file and add zero signal. Let the directory listing speak for itself.
    """
    pass


def _parse_terraform(lines: list[str], r: ParseResult) -> None:
    """Parser for Terraform/HCL. Extracts resource, module, variable, output."""
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        m = re.match(
            r'^(resource|module|variable|output|data)\s+"([^"]+)"', stripped
        )
        if m:
            symbol = f"{m.group(1)} {m.group(2)}"
            if symbol not in seen:
                seen.add(symbol)
                r.exports.append(symbol)
    r.exports = r.exports[:15]


def _parse_elixir(lines: list[str], r: ParseResult) -> None:
    """Parser for Elixir. Extracts modules, functions, structs, types."""
    in_doc = False
    for line in lines:
        stripped = line.strip()
        # Track heredoc strings to skip doc content
        if '"""' in stripped or "'''" in stripped:
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        if re.match(r"^defmodule\s+", stripped):
            m = re.match(r"^defmodule\s+([\w.]+)", stripped)
            if m:
                r.classes.append(m.group(1))
        elif re.match(r"^defprotocol\s+", stripped):
            m = re.match(r"^defprotocol\s+([\w.]+)", stripped)
            if m:
                r.classes.append(m.group(1))
        elif re.match(r"^\s*defstruct\b", stripped):
            r.types.append("defstruct")
        elif re.match(r"^\s*def\s+(\w+)", stripped):
            m = re.match(r"^\s*def\s+(\w+[\w?!]*)\s*(\([^)]*\))?", stripped)
            if m:
                r.functions.append(f"{m.group(1)}{_truncate_params(m.group(2) or '()')}")
        elif re.match(r"^\s*defp\s+", stripped):
            m = re.match(r"^\s*defp\s+(\w+[\w?!]*)", stripped)
            if m:
                r.functions.append(f"_{m.group(1)}")  # mark private
        elif re.match(r"^\s*@callback\s+", stripped):
            m = re.match(r"^\s*@callback\s+(\w+[\w?!]*)", stripped)
            if m:
                r.exports.append(m.group(1))
        elif re.match(r"^\s*@type\s+", stripped):
            m = re.match(r"^\s*@type\s+(\w+)", stripped)
            if m:
                r.types.append(m.group(1))
        elif re.match(r"^\s*(alias|import|require|use)\s+", stripped):
            r.imports.append(stripped)


def _parse_generic(lines: list[str], r: ParseResult) -> None:
    for line in lines:
        stripped = line.strip()
        if re.match(r"^(import|require|use|include|from)\s", stripped):
            r.imports.append(stripped.split("#")[0].split("//")[0].strip().rstrip(";"))
        elif re.match(r"^(def|fn|func|function|sub)\s+(\w+)", stripped):
            m = re.match(r"^(def|fn|func|function|sub)\s+(\w+)\s*(\([^)]*\))?", stripped)
            if m:
                r.functions.append(f"{m.group(2)}{_truncate_params(m.group(3) or '()')}")
        elif re.match(r"^(class|struct|enum|interface|type|trait|module)\s+(\w+)", stripped):
            m = re.match(r"^(class|struct|enum|interface|type|trait|module)\s+(\w+)", stripped)
            if m:
                r.classes.append(f"{m.group(1)} {m.group(2)}")
        elif re.match(r"^export\s", stripped):
            m = re.match(r"^export\s+(?:default\s+)?(?:function|class|const|let|var|type|interface)\s+(\w+)", stripped)
            if m:
                r.exports.append(m.group(1))


def _truncate_params(params: str) -> str:
    if not params:
        return "()"
    params = params.strip()
    if not params.startswith("("):
        params = f"({params})"
    if len(params) > 80:
        return params[:77] + "...)"
    return params


_PARSERS: dict[str, callable] = {
    "python": _parse_python,
    "typescript": _parse_typescript,
    "javascript": _parse_typescript,
    "vue": _parse_typescript,
    "svelte": _parse_typescript,
    "go": _parse_go,
    "rust": _parse_rust,
    "java": _parse_java,
    "kotlin": _parse_java,
    "ruby": _parse_ruby,
    "yaml": _parse_yaml,
    "toml": _parse_yaml,
    "json": _parse_yaml,
    "terraform": _parse_terraform,
    "elixir": _parse_elixir,
    "erlang": _parse_elixir,
}
