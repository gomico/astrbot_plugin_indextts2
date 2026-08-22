from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_indextts2.main import IndexTTSPlugin
from astrbot_plugin_indextts2.core.client import TTSResult
from astrbot_plugin_indextts2.core.runtime import Plain

class Context:
    def __init__(self, response='{"emotion":"开心"}'):
        self.response = response
        self.calls = 0
    async def llm_generate(self, **kwargs):
        self.calls += 1
        return self.response

class Event:
    def __init__(self, message_str=""): self.extra = {}; self.sent = []; self.message_str = message_str
    def get_extra(self, key): return self.extra.get(key)
    def set_extra(self, key, value): self.extra[key] = value
    def chain_result(self, chain): return chain
    def plain_result(self, text): return text
    async def send(self, value): self.sent.append(value)

class DecoratingResult:
    def __init__(self, text): self.chain = [Plain(text)]
    def is_llm_result(self): return True

class DecoratingEvent(Event):
    def __init__(self, result): super().__init__(); self.result = result
    def get_result(self): return self.result

async def collect(generator):
    return [item async for item in generator]

def capture_synthesis(plugin):
    calls = []
    async def synthesize(text, **kwargs):
        calls.append((text, kwargs))
        return TTSResult(True, b"RIFFxxxxWAVE")
    plugin.service.synthesize = synthesize
    return calls

class PluginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._data_dir = tempfile.TemporaryDirectory()
        self._data_dir_patch = patch.object(IndexTTSPlugin, "_data_dir", return_value=Path(self._data_dir.name))
        self._data_dir_patch.start()

    def tearDown(self):
        self._data_dir_patch.stop()
        self._data_dir.cleanup()

    def test_record_attaches_spoken_text_to_fallback_record(self):
        record = IndexTTSPlugin._record(TTSResult(True, b"RIFFxxxxWAVE", text="  朗读文本  "))
        self.assertEqual(record._private_companion_tts_source_text, "朗读文本")
        self.assertEqual(record._private_companion_tts_spoken_text, "朗读文本")

    async def test_manual_commands_and_tool_ignore_auto_minimum(self):
        context = Context('{"emotion":"开心"}')
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)

        await collect(plugin.say(Event("/说 好")))
        await collect(plugin.say_emotion(Event("/说情感 EN&&开心&&hi")))
        self.assertEqual([call[0] for call in calls], ["好", "hi"])

        tool_result = await plugin.indextts_tts(Event(), "hi", "开心")
        self.assertEqual(tool_result, "语音已发送")
        self.assertEqual([call[0] for call in calls], ["好", "hi", "hi"])
        self.assertEqual(plugin.emotion_stats.totals()["开心"], {"auto": 1, "command": 1, "bot": 1})
        stats = await collect(plugin.emotion_stats_command(Event("/TTS统计")))
        self.assertIn("开心: 3", stats[0])

    async def test_auto_tts_skips_text_shorter_than_minimum(self):
        context = Context()
        plugin = IndexTTSPlugin(context, {"auto": {"enabled": True, "tts_probability": 1, "min_text_length": 3}})
        calls = capture_synthesis(plugin)
        event = DecoratingEvent(DecoratingResult("两字"))
        await plugin.on_decorating_result(event)
        self.assertFalse(calls)
        self.assertEqual(context.calls, 0)
        self.assertEqual(event.result.chain[0].text, "两字")

    async def test_tool_rejects_missing_or_unknown_emotion_without_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = IndexTTSPlugin(Context(), {"tts": {"speaker_audio": "voices/n.wav"}, "emotion": {"entries": [{"name": "开心", "emotion_audio": "emotions/h.wav"}]}})
            called = False
            async def fail(_payload):
                nonlocal called; called = True
                raise AssertionError("API must not be called")
            plugin.client.tts = fail
            event = Event()
            self.assertIn("未指定 emotion", await plugin.indextts_tts(event, "你好"))
            self.assertIn("emotion 无效", await plugin.indextts_tts(event, "你好", "错误"))
            self.assertFalse(called)

    async def test_say_combines_language_and_emotion_judgment(self):
        context = Context('{"language":"JA","emotion":"开心"}')
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        result = await collect(plugin.say(Event("/说 こんにちは")))
        self.assertEqual(len(result), 1)
        self.assertEqual(context.calls, 1)
        self.assertEqual(calls[0][0], "こんにちは")
        self.assertEqual(calls[0][1]["language"], "JA")
        self.assertEqual(calls[0][1]["emotion"].name, "开心")

    async def test_say_llm_failure_falls_back_language_and_keyword(self):
        context = Context("not-json")
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        await collect(plugin.say(Event("/说 今天真开心")))
        self.assertEqual(context.calls, 1)
        self.assertEqual(calls[0][1]["language"], "ZH")
        self.assertEqual(calls[0][1]["emotion"].name, "开心")

    async def test_say_explicit_language_only_judges_emotion(self):
        context = Context('{"emotion":"开心"}')
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        await collect(plugin.say(Event("/说 EN&&hello")))
        self.assertEqual(context.calls, 1)
        self.assertEqual(calls[0][0], "hello")
        self.assertEqual(calls[0][1]["language"], "EN")

    async def test_say_emotion_detects_language(self):
        context = Context('{"language":"ES"}')
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        await collect(plugin.say_emotion(Event("/说情感 开心&&hola")))
        self.assertEqual(context.calls, 1)
        self.assertEqual(calls[0][0], "hola")
        self.assertEqual(calls[0][1]["language"], "ES")
        self.assertEqual(calls[0][1]["emotion"].name, "开心")

    async def test_say_emotion_explicit_language_skips_llm(self):
        context = Context()
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        await collect(plugin.say_emotion(Event("/说情感 AR&&开心&&مرحبا")))
        self.assertEqual(context.calls, 0)
        self.assertEqual(calls[0][0], "مرحبا")
        self.assertEqual(calls[0][1]["language"], "AR")

    async def test_all_explicit_languages_and_invalid_arguments(self):
        for language in ("ZH", "EN", "JA", "AR", "ES"):
            with self.subTest(language=language):
                context = Context('{"emotion":"开心"}')
                plugin = IndexTTSPlugin(context, {})
                calls = capture_synthesis(plugin)
                await collect(plugin.say(Event(f"/说 {language}&&text")))
                self.assertEqual(calls[0][1]["language"], language)

        context = Context()
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        invalid = await collect(plugin.say(Event("/说 KO&&text")))
        self.assertIn("语言代码 KO 无效", invalid[0])
        old_syntax = await collect(plugin.say_emotion(Event("/说情感 开心 text")))
        self.assertIn("用法", old_syntax[0])
        empty = await collect(plugin.say(Event("/说 EN&&")))
        self.assertIn("用法", empty[0])
        self.assertFalse(calls)
        self.assertEqual(context.calls, 0)

if __name__ == "__main__": unittest.main()
