from __future__ import annotations

import re
from typing import Any

_CODE_BLOCK = re.compile(r"```", re.S)
_URL = re.compile(r"https?://\S{100,}", re.I)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")

def plain_chain_text(chain: list[Any] | tuple[Any, ...]) -> str | None:
    """Return all Plain text only; non-Plain chain components are deliberately skipped."""
    if not chain: return None
    parts: list[str] = []
    for item in chain:
        if item.__class__.__name__ != "Plain" or not isinstance(getattr(item, "text", None), str): return None
        parts.append(item.text)
    return "\n".join(parts)

def clean_text(text: str, *, strip_markdown: bool = True) -> str | None:
    text = text.strip()
    if not text or _CODE_BLOCK.search(text) or _URL.search(text): return None
    if strip_markdown:
        text = _LINK.sub(r"\1", text)
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
        text = re.sub(r"([*_~`])\1*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None
