from __future__ import annotations

from dataclasses import dataclass

from .config import EmotionConfig
from .runtime import logger

@dataclass(frozen=True)
class EmotionEntry:
    name: str
    keywords: tuple[str, ...]
    emotion_audio: str
    emotion_weight: float

    def to_params(self) -> dict[str, object]:
        return {"emotion_audio": self.emotion_audio, "emotion_weight": self.emotion_weight}

class EntryManager:
    """Configured entries; configuration order wins when keywords overlap."""
    def __init__(self, cfg: EmotionConfig):
        self.entries = [EmotionEntry(str(x["name"]).strip(), tuple(str(k).strip() for k in x.get("keywords", []) if str(k).strip()), str(x["emotion_audio"]).strip(), float(x.get("emotion_weight", 1))) for x in cfg.entries]
        self._by_name = {entry.name: entry for entry in self.entries}

    def get_names(self) -> list[str]: return [entry.name for entry in self.entries]
    def get_entry(self, name: str | None) -> EmotionEntry | None: return self._by_name.get((name or "").strip())

    def match_entry(self, text: str) -> EmotionEntry | None:
        folded = text.casefold()
        for entry in self.entries:
            if any(keyword.casefold() in folded for keyword in entry.keywords):
                logger.debug("关键词情感命中: %s", entry.name)
                return entry
        return None
