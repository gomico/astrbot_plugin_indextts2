from __future__ import annotations

import re
from typing import Any, Mapping

_CODE_BLOCK = re.compile(r"```", re.S)
_URL = re.compile(r"https?://\S{100,}", re.I)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_PHONETIC_TAG = re.compile(r"<[^<>|]+\|[^<>]*>")

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

def apply_phonetic(text: str, language: str, entries: list[Mapping[str, Any]]) -> str:
    """按配置的注音替换条目，把目标字符替换为 IndexTTS 标注。"""
    if not entries or not text:
        return text
    lang = language.upper()

    phonetics = {
        str(entry.get("char", "")).strip(): str(entry.get("phonetic", "")).strip()
        for entry in entries
        if isinstance(entry, Mapping) and str(entry.get("language", "")).upper() == lang
        and str(entry.get("char", "")).strip() and str(entry.get("phonetic", "")).strip()
    }
    if not phonetics:
        return text

    targets = sorted(phonetics, key=len, reverse=True)
    target_re = re.compile("|".join(re.escape(char) for char in targets))

    def replace_segment(segment: str) -> str:
        return target_re.sub(lambda match: f"<{match.group(0)}|{phonetics[match.group(0)]}>", segment)

    segments = _PHONETIC_TAG.split(text)
    tags = _PHONETIC_TAG.findall(text)
    parts: list[str] = []
    for index, segment in enumerate(segments):
        parts.append(replace_segment(segment))
        if index < len(tags):
            parts.append(tags[index])
    return "".join(parts)
