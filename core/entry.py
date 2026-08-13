from __future__ import annotations

from dataclasses import dataclass

from .config import EMOTION_VECTOR_DIMENSIONS, EmotionConfig
from .runtime import logger

@dataclass(frozen=True)
class EmotionEntry:
    name: str
    keywords: tuple[str, ...]
    emotion_audio: str
    emotion_weight: float
    emotion_vector: tuple[float, ...] = ()

    def to_params(self) -> dict[str, object]:
        if self.emotion_vector:
            return {"emotion_vector": list(self.emotion_vector), "emotion_weight": self.emotion_weight}
        return {"emotion_audio": self.emotion_audio, "emotion_weight": self.emotion_weight}

class EntryManager:
    """Configured entries; configuration order wins when keywords overlap."""
    def __init__(self, cfg: EmotionConfig):
        source = cfg.vector_entries if cfg.control_mode == "vector" else cfg.entries
        self.entries = [EmotionEntry(
            str(x["name"]).strip(),
            tuple(str(k).strip() for k in x.get("keywords", []) if str(k).strip()),
            str(x.get("emotion_audio", "")).strip(),
            float(x.get("emotion_weight", .8)),
            tuple(float(x[dimension]) for dimension in EMOTION_VECTOR_DIMENSIONS) if cfg.control_mode == "vector" else (),
        ) for x in source]
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
