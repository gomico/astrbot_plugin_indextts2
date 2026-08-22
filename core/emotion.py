from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from .config import LANGUAGES, EmotionConfig
from .entry import EntryManager, EmotionEntry
from .runtime import logger

_CACHE_KEY = "indextts2_classification"


@dataclass(frozen=True)
class Classification:
    language: str | None = None
    emotion: str | None = None

def _get_extra(event: Any, key: str) -> Any:
    if hasattr(event, "get_extra"): return event.get_extra(key)
    return getattr(event, "extra", {}).get(key)
def _set_extra(event: Any, key: str, value: Any) -> None:
    if hasattr(event, "set_extra"): event.set_extra(key, value); return
    if not hasattr(event, "extra"): event.extra = {}
    event.extra[key] = value

class EmotionJudger:
    def __init__(self, context: Any, cfg: EmotionConfig, entries: EntryManager):
        self.context, self.cfg, self.entries = context, cfg, entries

    async def select(self, event: Any, text: str) -> EmotionEntry | None:
        if self.cfg.selection_mode == "off": return None
        if self.cfg.selection_mode == "keyword": return self.entries.match_entry(text)
        label = (await self.classify(event, text, need_emotion=True)).emotion
        if label: return self.entries.get_entry(label)
        if self.cfg.fallback_to_keyword:
            logger.debug("情感模型失败，使用关键词回退")
            return self.entries.match_entry(text)
        return None

    async def select_with_language(self, event: Any, text: str) -> tuple[str | None, EmotionEntry | None]:
        need_emotion = self.cfg.selection_mode == "llm"
        result = await self.classify(event, text, need_language=True, need_emotion=need_emotion)
        entry = self.entries.get_entry(result.emotion) if result.emotion else None
        if self.cfg.selection_mode == "keyword" or (need_emotion and entry is None and self.cfg.fallback_to_keyword):
            entry = self.entries.match_entry(text)
        return result.language, entry

    async def detect_language(self, event: Any, text: str) -> str | None:
        return (await self.classify(event, text, need_language=True)).language

    async def classify(
        self,
        event: Any,
        text: str,
        *,
        need_language: bool = False,
        need_emotion: bool = False,
    ) -> Classification:
        labels = self.entries.get_names()
        need_emotion = need_emotion and bool(labels)
        if not need_language and not need_emotion:
            return Classification()

        cached = _get_extra(event, _CACHE_KEY)
        cached_for_text = cached.get(text, {}) if isinstance(cached, dict) else {}
        cached_language = cached_for_text.get("language")
        cached_emotion = cached_for_text.get("emotion")
        ask_language = need_language and cached_language not in LANGUAGES
        ask_emotion = need_emotion and cached_emotion not in labels
        if not ask_language and not ask_emotion:
            return Classification(cached_language if need_language else None, cached_emotion if need_emotion else None)

        requirements: list[str] = []
        example: dict[str, str] = {}
        if ask_language:
            requirements.append("language 必须是 ZH、EN、JA、AR、ES 中最符合文本语言的一个")
            example["language"] = "ZH"
        if ask_emotion:
            requirements.append("emotion 必须是以下唯一允许标签中的一个：" + json.dumps(labels, ensure_ascii=False))
            example["emotion"] = labels[0]
        prompt = (
            "分析文本并严格只返回一个 JSON 对象，不要 Markdown 或解释。"
            + "；".join(requirements)
            + "。返回示例："
            + json.dumps(example, ensure_ascii=False, separators=(",", ":"))
            + "。\n文本："
            + text
        )
        try:
            kwargs: dict[str, Any] = {"prompt": prompt, "chat_provider_id": self.cfg.provider_id}
            result = await asyncio.wait_for(self.context.llm_generate(**kwargs), timeout=self.cfg.judge_timeout)
            raw = getattr(result, "completion_text", result)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("empty response")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("response is not an object")

            language = parsed.get("language") if ask_language else cached_language
            emotion = parsed.get("emotion") if ask_emotion else cached_emotion
            if ask_language and language not in LANGUAGES:
                logger.warning("语言判断返回无效标签，将使用默认语言")
                language = None
            if ask_emotion and emotion not in labels:
                logger.warning("情感判断返回无效标签，%s", "将回退关键词" if self.cfg.fallback_to_keyword else "不回退")
                emotion = None

            successful = dict(cached_for_text)
            if language in LANGUAGES: successful["language"] = language
            if emotion in labels: successful["emotion"] = emotion
            if successful:
                all_cached = dict(cached) if isinstance(cached, dict) else {}
                all_cached[text] = successful
                _set_extra(event, _CACHE_KEY, all_cached)
            return Classification(language if need_language else None, emotion if need_emotion else None)
        except asyncio.TimeoutError:
            logger.warning("语言/情感判断超时，将使用配置的回退行为")
        except Exception as exc:
            logger.warning("语言/情感判断失败(%s)，将使用配置的回退行为", type(exc).__name__)
        return Classification(
            cached_language if need_language and cached_language in LANGUAGES else None,
            cached_emotion if need_emotion and cached_emotion in labels else None,
        )
