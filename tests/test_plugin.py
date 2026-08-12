from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_indextts2.main import IndexTTSPlugin

class Context:
    async def llm_generate(self, **kwargs): return '{"emotion":"开心"}'

class Event:
    def __init__(self): self.extra = {}; self.sent = []
    def get_extra(self, key): return self.extra.get(key)
    def set_extra(self, key, value): self.extra[key] = value
    def chain_result(self, chain): return chain
    async def send(self, value): self.sent.append(value)

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

if __name__ == "__main__": unittest.main()
