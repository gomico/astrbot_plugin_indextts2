from __future__ import annotations

import asyncio
import json
from typing import Any

from .config import EmotionConfig
from .entry import EntryManager, EmotionEntry
from .runtime import logger

_CACHE_KEY = "indextts2_emotion"

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
        label = await self.judge_llm(event, text)
        if label: return self.entries.get_entry(label)
        if self.cfg.fallback_to_keyword:
            logger.debug("情感模型失败，使用关键词回退")
            return self.entries.match_entry(text)
        return None

    async def judge_llm(self, event: Any, text: str) -> str | None:
        labels = self.entries.get_names()
        if not labels:
            return None
        cached = _get_extra(event, _CACHE_KEY)
        if isinstance(cached, str) and cached in labels:
            return cached
        prompt = ("选择下列唯一允许标签中最符合文本主要情绪的一个：" + json.dumps(labels, ensure_ascii=False) +
                  "。严格只返回 JSON 对象，不要 Markdown 或解释：{\"emotion\":\"标签\"}。\n文本：" + text)
        try:
            kwargs: dict[str, Any] = {"prompt": prompt}
            if self.cfg.provider_id: kwargs["provider_id"] = self.cfg.provider_id
            result = await asyncio.wait_for(self.context.llm_generate(**kwargs), timeout=self.cfg.judge_timeout)
            raw = getattr(result, "completion_text", result)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("empty response")
            parsed = json.loads(raw)
            if set(parsed) != {"emotion"} or not isinstance(parsed["emotion"], str) or parsed["emotion"] not in labels:
                raise ValueError("invalid emotion JSON")
            _set_extra(event, _CACHE_KEY, parsed["emotion"])
            return parsed["emotion"]
        except asyncio.TimeoutError:
            logger.warning("情感判断超时，%s", "将回退关键词" if self.cfg.fallback_to_keyword else "不回退")
        except Exception as exc:
            logger.warning("情感判断失败(%s)，%s", type(exc).__name__, "将回退关键词" if self.cfg.fallback_to_keyword else "不回退")
        return None
