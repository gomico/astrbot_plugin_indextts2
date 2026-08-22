from __future__ import annotations

from .client import IndexTTSClient, TTSResult
from .config import LANGUAGES, PluginConfig
from .entry import EmotionEntry
from .local_data import LocalDataManager
from .text import apply_phonetic

class IndexTTSService:
    def __init__(self, cfg: PluginConfig, client: IndexTTSClient, cache: LocalDataManager):
        self.cfg, self.client, self.cache = cfg, client, cache

    async def synthesize(self, text: str, *, emotion: EmotionEntry | None = None, language: str = "", max_length: int | None = None) -> TTSResult:
        text = (text or "").strip()
        limit = max_length or self.cfg.tts.max_text_length
        if not text: return TTSResult(False, error="TTS 文本不能为空", error_code="empty_text")
        if len(text) > limit: return TTSResult(False, error=f"文本过长（最多 {limit} 字）", error_code="text_too_long")
        if not self.cfg.tts.speaker_audio: return TTSResult(False, error="未配置 speaker_audio", error_code="configuration")
        language = (language or self.cfg.tts.default_language).upper()
        if language not in LANGUAGES: return TTSResult(False, error="语言必须为 ZH/EN/JA/AR/ES", error_code="invalid_language")
        text = apply_phonetic(text, language, self.cfg.phonetic.entries)
        payload: dict[str, object] = {"text": text, "speaker_audio": self.cfg.tts.speaker_audio, "language": language, "duration_factor": self.cfg.tts.duration_factor, "emotion_weight": self.cfg.tts.default_emotion_weight}
        if emotion:
            payload.update(emotion.to_params())
        cached = self.cache.get(payload)
        if cached:
            path, data = cached
            return TTSResult(True, data=data, file_path=str(path))
        result = await self.client.tts(payload)
        if result.ok and result.data:
            path = self.cache.save(payload, result.data)
            if path: result.file_path = str(path)
        return result
