from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_indextts2.main import IndexTTSPlugin
from astrbot_plugin_indextts2.core.client import TTSResult

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
        await collect(plugin.say_emotion(Event("/说情绪 开心&&hola")))
        self.assertEqual(context.calls, 1)
        self.assertEqual(calls[0][0], "hola")
        self.assertEqual(calls[0][1]["language"], "ES")
        self.assertEqual(calls[0][1]["emotion"].name, "开心")

    async def test_say_emotion_explicit_language_skips_llm(self):
        context = Context()
        plugin = IndexTTSPlugin(context, {})
        calls = capture_synthesis(plugin)
        await collect(plugin.say_emotion(Event("/说情绪 AR&&开心&&مرحبا")))
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
        old_syntax = await collect(plugin.say_emotion(Event("/说情绪 开心 text")))
        self.assertIn("用法", old_syntax[0])
        empty = await collect(plugin.say(Event("/说 EN&&")))
        self.assertIn("用法", empty[0])
        self.assertFalse(calls)
        self.assertEqual(context.calls, 0)

if __name__ == "__main__": unittest.main()
