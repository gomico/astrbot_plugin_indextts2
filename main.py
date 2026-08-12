from __future__ import annotations

import base64
import random
from pathlib import Path
from typing import Any, AsyncGenerator, Mapping

from .core.client import IndexTTSClient, TTSResult
from .core.config import LANGUAGES, PluginConfig
from .core.emotion import EmotionJudger, _get_extra, _set_extra
from .core.entry import EntryManager
from .core.local_data import LocalDataManager
from .core.runtime import Context, Record, Star, filter, logger
from .core.service import IndexTTSService
from .core.text import clean_text, plain_chain_text

_SENT_KEY = "indextts2_audio_sent"

class IndexTTSPlugin(Star):
    def __init__(self, context: Context, config: Mapping[str, Any]):
        super().__init__(context)
        data_dir = self._data_dir()
        self.cfg = PluginConfig.from_mapping(config, data_dir=data_dir)
        self.entries = EntryManager(self.cfg.emotion)
        self.client = IndexTTSClient(self.cfg.client)
        self.cache = LocalDataManager(self.cfg.cache, self.cfg.audio_dir)
        self.service = IndexTTSService(self.cfg, self.client, self.cache)
        self.judger = EmotionJudger(context, self.cfg.emotion, self.entries)

    @staticmethod
    def _data_dir() -> Path:
        try:  # pragma: no cover - requires AstrBot runtime
            from astrbot.core.star.star_tools import StarTools  # type: ignore
            return Path(StarTools.get_data_dir("astrbot_plugin_indextts2"))
        except (ImportError, AttributeError):
            return Path("data/plugins_data/astrbot_plugin_indextts2")

    async def initialize(self) -> None:
        self.cache.cleanup()
        if not self.cfg.enabled: return
        result = await self.client.health()
        if not result.ok: logger.warning("IndexTTS API 当前不可用，插件仍会加载：%s", result.error)

    async def terminate(self) -> None:
        self.cache.cleanup()
        await self.client.close()

    @staticmethod
    def _record(result: TTSResult) -> Any:
        if result.file_path:
            try: return Record.fromFileSystem(result.file_path)
            except Exception: logger.warning("缓存语音无法以文件形式发送，使用内存数据")
        if not result.data: raise ValueError("没有可发送的音频")
        return Record.fromBase64(base64.urlsafe_b64encode(result.data).decode("ascii"))

    async def _automatic_emotion(self, event: Any, text: str):
        return await self.judger.select(event, text)

    def _language_error(self, language: str) -> str:
        allowed = "/".join(sorted(LANGUAGES))
        return f"语言代码 {language or '（空）'} 无效。支持：{allowed}。"

    @staticmethod
    def _command_text(event: Any) -> str:
        value = str(getattr(event, "message_str", ""))
        return value.partition(" ")[2].strip()

    @filter.command("说", alias={"itts", "ITTS"})
    async def say(self, event: Any) -> AsyncGenerator[Any, None]:
        """说 <文本> 或 说 <语言>&&<文本>。"""
        if not self.cfg.enabled:
            yield event.plain_result("IndexTTS 插件未启用")
            return
        raw = self._command_text(event)
        parts = [part.strip() for part in raw.split("&&")]
        if len(parts) == 1:
            text = parts[0]
            language, emotion = await self.judger.select_with_language(event, text) if text else (None, None)
            language = language or self.cfg.tts.default_language
        elif len(parts) == 2:
            language, text = parts
            if language not in LANGUAGES:
                yield event.plain_result(self._language_error(language)); return
            emotion = await self._automatic_emotion(event, text) if text else None
        else:
            yield event.plain_result("用法：说 <文本> 或 说 <语言>&&<文本>"); return
        if not text:
            yield event.plain_result("用法：说 <文本> 或 说 <语言>&&<文本>"); return
        result = await self.service.synthesize(text, emotion=emotion, language=language)
        if not result: yield event.plain_result(result.error); return
        yield event.chain_result([self._record(result)])

    @filter.command("说情绪", alias={"itts_emo"})
    async def say_emotion(self, event: Any) -> AsyncGenerator[Any, None]:
        """说情绪 <情感>&&<文本> 或 说情绪 <语言>&&<情感>&&<文本>。"""
        if not self.cfg.enabled:
            yield event.plain_result("IndexTTS 插件未启用"); return
        parts = [part.strip() for part in self._command_text(event).split("&&")]
        if len(parts) == 2:
            emotion_name, text = parts
            language = None
        elif len(parts) == 3:
            language, emotion_name, text = parts
            if language not in LANGUAGES:
                yield event.plain_result(self._language_error(language)); return
        else:
            yield event.plain_result("用法：说情绪 <情感>&&<文本> 或 说情绪 <语言>&&<情感>&&<文本>"); return
        if not emotion_name or not text:
            yield event.plain_result("用法：说情绪 <情感>&&<文本> 或 说情绪 <语言>&&<情感>&&<文本>"); return
        emotion = self.entries.get_entry(emotion_name)
        if not emotion:
            yield event.plain_result(self._emotion_help("情感不存在")); return
        if language is None:
            language = await self.judger.detect_language(event, text) or self.cfg.tts.default_language
        result = await self.service.synthesize(text, emotion=emotion, language=language)
        if not result: yield event.plain_result(result.error); return
        yield event.chain_result([self._record(result)])

    @filter.command("TTS情绪")
    async def list_emotions(self, event: Any) -> AsyncGenerator[Any, None]:
        yield event.plain_result("可用情感：" + ("、".join(self.entries.get_names()) or "（未配置）"))

    @filter.command("TTS状态")
    async def status(self, event: Any) -> AsyncGenerator[Any, None]:
        result = await self.client.health()
        yield event.plain_result("IndexTTS 服务正常" if result.ok else f"IndexTTS 服务不可用：{result.error}")

    @filter.on_decorating_result(priority=14)
    async def on_decorating_result(self, event: Any) -> None:
        if not self.cfg.enabled or not self.cfg.auto.enabled or _get_extra(event, _SENT_KEY): return
        result = event.get_result() if hasattr(event, "get_result") else None
        if not result or not getattr(result, "chain", None): return
        if self.cfg.auto.only_llm_result and not result.is_llm_result(): return
        if random.random() > self.cfg.auto.tts_probability: return
        text = plain_chain_text(result.chain)
        if text is None: return
        text = clean_text(text, strip_markdown=self.cfg.auto.strip_markdown)
        if not text or len(text) > self.cfg.auto.max_text_length: return
        emotion = await self._automatic_emotion(event, text)
        synthesized = await self.service.synthesize(text, emotion=emotion, max_length=self.cfg.auto.max_text_length)
        if not synthesized: return
        # Do not mutate the original reply before a valid record exists.
        record = self._record(synthesized)
        result.chain.clear(); result.chain.append(record)
        _set_extra(event, _SENT_KEY, True)

    def _emotion_help(self, prefix: str) -> str:
        names = "、".join(self.entries.get_names()) or "（未配置）"
        return f"{prefix}。当前可用情感：{names}。请重新调用 indextts_tts，并同时提供 message 和 emotion。"

    @filter.llm_tool()
    async def indextts_list_emotions(self, event: Any) -> str:
        """
        列出可用于 indextts_tts 的 emotion 名称。
        """
        return "可用情感：" + ("、".join(self.entries.get_names()) or "（未配置）")

    @filter.llm_tool()
    async def indextts_tts(self, event: Any, message: str = "", emotion: str = "", language: str = "") -> str:
        """
        用 IndexTTS 发送一条语音。必须显式提供 message 和 emotion。

        Args:
            message(string): 需要朗读的文本，不能为空。
            emotion(string): 必填，必须是 indextts_list_emotions 返回的一个准确名称。
            language(string, optional): ZH、EN、JA、AR 或 ES；留空使用插件默认语言。
        """
        if not self.cfg.enabled or not self.cfg.tool.enabled: return "IndexTTS Tool 未启用"
        if _get_extra(event, _SENT_KEY): return "本事件已经发送过 IndexTTS 语音"
        if not (message or "").strip(): return "未指定 message。请重新调用 indextts_tts，并同时提供 message 和 emotion。"
        entry = self.entries.get_entry(emotion)
        if not entry: return self._emotion_help("未指定 emotion" if not (emotion or "").strip() else "emotion 无效")
        if language and not self.cfg.tool.allow_language_argument: return "当前配置不允许 Tool 指定 language"
        result = await self.service.synthesize(message, emotion=entry, language=language)
        if not result: return result.error
        try:
            await event.send(event.chain_result([self._record(result)]))
            _set_extra(event, _SENT_KEY, True)
            return "语音已发送"
        except Exception as exc:
            logger.warning("IndexTTS Tool 发送失败(%s)", type(exc).__name__)
            return "语音发送失败"
