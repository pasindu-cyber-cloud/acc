"""Minimal YAML loader with PyYAML fallback.

If PyYAML is installed it is used (full spec). Otherwise a small indentation
based parser handles the subset of YAML used by AccuScan's own config files:
mappings, nested mappings, block sequences (``- item``), inline flow lists
(``[a, b, c]``), comments, and scalars (int/float incl. ``1e-9``/bool/null/str).

This keeps the project fully runnable with zero third-party dependencies.
"""

from __future__ import annotations

from typing import Any


def load_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _parse(text)


def _scalar(token: str) -> Any:
    t = token.strip()
    if t == "" or t in ("null", "~"):
        return None
    if t.lower() == "true":
        return True
    if t.lower() == "false":
        return False
    if (t[0] == t[-1]) and t[0] in ("'", '"') and len(t) >= 2:
        return t[1:-1]
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in _split_flow(inner)]
    # numbers
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def _split_flow(inner: str) -> list[str]:
    """Split a flow list body on commas, respecting quotes."""
    parts: list[str] = []
    buf = []
    quote = None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in (p.strip() for p in parts) if p != ""]


def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#":
            return line[:i]
    return line


class _Line:
    __slots__ = ("indent", "content")

    def __init__(self, indent: int, content: str) -> None:
        self.indent = indent
        self.content = content


def _tokenize(text: str) -> list[_Line]:
    out: list[_Line] = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        out.append(_Line(indent, stripped.strip()))
    return out


def _parse(text: str) -> dict[str, Any]:
    lines = _tokenize(text)
    pos = 0

    def parse_block(min_indent: int) -> Any:
        nonlocal pos
        if pos >= len(lines):
            return {}
        indent = lines[pos].indent
        is_seq = lines[pos].content.startswith("- ")
        container: Any = [] if is_seq else {}

        while pos < len(lines) and lines[pos].indent >= indent:
            line = lines[pos]
            if line.indent > indent:
                # Should be consumed by a deeper recursive call.
                break
            content = line.content

            if content.startswith("- "):
                pos += 1
                item_text = content[2:].strip()
                if ":" in item_text and not item_text.startswith("["):
                    # inline mapping inside a sequence item -> rare; treat as map
                    k, _, v = item_text.partition(":")
                    container.append({k.strip(): _scalar(v)})
                else:
                    container.append(_scalar(item_text))
                continue

            key, sep, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            pos += 1
            if val == "":
                # Nested block (map or sequence) on following deeper lines.
                if pos < len(lines) and lines[pos].indent > indent:
                    container[key] = parse_block(lines[pos].indent)
                else:
                    container[key] = {}
            else:
                container[key] = _scalar(val)
        return container

    result = parse_block(lines[0].indent) if lines else {}
    return result if isinstance(result, dict) else {"_": result}
