from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_indextts2.core.client import TTSResult
from astrbot_plugin_indextts2.core.config import DEFAULTS, EMOTION_VECTOR_DIMENSIONS, PluginConfig, migrate_template_keys
from astrbot_plugin_indextts2.core.emotion import EmotionJudger
from astrbot_plugin_indextts2.core.entry import EntryManager
from astrbot_plugin_indextts2.core.local_data import LocalDataManager
from astrbot_plugin_indextts2.core.service import IndexTTSService
from astrbot_plugin_indextts2.core.stats import EmotionStats
from astrbot_plugin_indextts2.core.text import clean_text, plain_chain_text

def config(data_dir: Path) -> PluginConfig:
    return PluginConfig.from_mapping({"tts": {"speaker_audio": "voices/neutral.wav"}, "emotion": {"entries": [
        {"name": "开心", "keywords": ["开心", "哈哈"], "emotion_audio": "emotions/happy.wav", "emotion_weight": .8},
        {"name": "悲伤", "keywords": ["难过"], "emotion_audio": "emotions/sad.wav", "emotion_weight": .7},
    ]}}, data_dir=data_dir)

class Event:
    def __init__(self): self.extra = {}
    def get_extra(self, key): return self.extra.get(key)
    def set_extra(self, key, value): self.extra[key] = value

class Context:
    def __init__(self, result): self.result, self.calls = result, 0
    async def llm_generate(self, **kwargs): self.calls += 1; return self.result

class Result:
    def __init__(self, text): self.completion_text = text

class Client:
    def __init__(self): self.payloads = []
    async def tts(self, payload): self.payloads.append(payload); return TTSResult(True, b"RIFFxxxxWAVE")

class CoreTests(unittest.IsolatedAsyncioTestCase):
    def test_migrate_legacy_template_keys(self):
        config = {"emotion": {"entries": [{"name": "开心"}], "vector_entries": [{"name": "平静"}, {"__template_key": "default"}]}}
        self.assertTrue(migrate_template_keys(config))
        self.assertEqual(config["emotion"]["entries"][0]["__template_key"], "default")
        self.assertEqual(config["emotion"]["vector_entries"][0]["__template_key"], "default")
        self.assertFalse(migrate_template_keys(config))

    async def test_default_subaru_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = PluginConfig.from_mapping(None, data_dir=Path(tmp))
            self.assertEqual(cfg.tts.speaker_audio, "voices/subaru.wav")
            self.assertEqual(cfg.auto.min_text_length, 5)
            self.assertEqual(cfg.tts.default_emotion_weight, .8)
            self.assertEqual(cfg.emotion.control_mode, "reference_audio")
            entry = EntryManager(cfg.emotion).get_entry("开心")
            self.assertIsNotNone(entry)
            self.assertEqual(entry.emotion_audio, "emotions/subaru_happy.wav")
            self.assertEqual(entry.emotion_weight, .8)

    async def test_default_vector_presets_keep_names_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = PluginConfig.from_mapping(None, data_dir=Path(tmp))
            vector_cfg = replace(cfg.emotion, control_mode="vector")
            entries = EntryManager(vector_cfg)
            self.assertEqual(entries.get_names(), ["开心", "平静", "紧张", "难过"])
            self.assertEqual(entries.get_entry("开心").to_params()["emotion_vector"], [.6, 0, 0, 0, 0, 0, .2, 0])
            self.assertEqual(entries.get_entry("平静").to_params()["emotion_vector"], [.05, 0, .05, 0, 0, .1, 0, .6])
            self.assertEqual(entries.get_entry("紧张").to_params()["emotion_vector"], [0, .35, 0, .2, 0, 0, .25, 0])
            self.assertEqual(entries.get_entry("难过").to_params()["emotion_vector"], [0, 0, .45, 0, 0, .25, 0, .1])
            self.assertEqual(tuple(EMOTION_VECTOR_DIMENSIONS), ("happy", "angry", "sad", "afraid", "disgusted", "melancholic", "surprised", "calm"))

    def test_default_vector_presets_match_schema(self):
        schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        core_entries = DEFAULTS["emotion"]["vector_entries"]
        schema_entries = schema["emotion"]["items"]["vector_entries"]["default"]
        self.assertEqual([entry["name"] for entry in core_entries], [entry["name"] for entry in schema_entries])
        for core_entry, schema_entry in zip(core_entries, schema_entries):
            self.assertEqual(core_entry["emotion_weight"], schema_entry["emotion_weight"])
            self.assertEqual(
                [core_entry[dimension] for dimension in EMOTION_VECTOR_DIMENSIONS],
                [schema_entry[dimension] for dimension in EMOTION_VECTOR_DIMENSIONS],
            )

    async def test_llm_json_and_event_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); entries = EntryManager(cfg.emotion); ctx = Context(Result('{"emotion":"开心"}'))
            judger = EmotionJudger(ctx, cfg.emotion, entries); event = Event()
            self.assertEqual((await judger.select(event, "任意文本")).name, "开心")
            self.assertEqual((await judger.select(event, "任意文本")).name, "开心")
            self.assertEqual(ctx.calls, 1)

    async def test_llm_invalid_falls_back_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); entries = EntryManager(cfg.emotion); ctx = Context(Result("not-json"))
            selected = await EmotionJudger(ctx, cfg.emotion, entries).select(Event(), "真开心")
            self.assertEqual(selected.name, "开心")

    async def test_combined_language_emotion_partial_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); entries = EntryManager(cfg.emotion)
            language_ok = EmotionJudger(Context(Result('{"language":"EN","emotion":"不存在"}')), cfg.emotion, entries)
            language, emotion = await language_ok.select_with_language(Event(), "真开心")
            self.assertEqual(language, "EN")
            self.assertEqual(emotion.name, "开心")

            emotion_ok = EmotionJudger(Context(Result('{"language":"KO","emotion":"悲伤"}')), cfg.emotion, entries)
            language, emotion = await emotion_ok.select_with_language(Event(), "任意文本")
            self.assertIsNone(language)
            self.assertEqual(emotion.name, "悲伤")

    async def test_keyword_and_off_modes_only_ask_llm_for_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); entries = EntryManager(cfg.emotion)
            for mode, expected_emotion in (("keyword", "开心"), ("off", None)):
                with self.subTest(mode=mode):
                    context = Context(Result('{"language":"EN"}'))
                    judger = EmotionJudger(context, replace(cfg.emotion, selection_mode=mode), entries)
                    language, emotion = await judger.select_with_language(Event(), "真开心")
                    self.assertEqual(language, "EN")
                    self.assertEqual(emotion.name if emotion else None, expected_emotion)
                    self.assertEqual(context.calls, 1)

    async def test_llm_timeout_and_disabled_fallback(self):
        class SlowContext:
            async def llm_generate(self, **kwargs):
                await asyncio.sleep(.05)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); entries = EntryManager(cfg.emotion)
            timeout_cfg = replace(cfg.emotion, judge_timeout=.001)
            self.assertEqual((await EmotionJudger(SlowContext(), timeout_cfg, entries).select(Event(), "真开心")).name, "开心")
            no_fallback = replace(timeout_cfg, fallback_to_keyword=False)
            self.assertIsNone(await EmotionJudger(SlowContext(), no_fallback, entries).select(Event(), "真开心"))

    async def test_service_cache_and_no_emotion_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); client = Client(); cache = LocalDataManager(cfg.cache, cfg.audio_dir)
            service = IndexTTSService(cfg, client, cache)
            self.assertTrue(await service.synthesize("你好"))
            self.assertTrue(await service.synthesize("你好"))
            self.assertEqual(len(client.payloads), 1)
            self.assertNotIn("emotion_audio", client.payloads[0])
            self.assertEqual((await service.synthesize("x", language="BAD")).error_code, "invalid_language")

    async def test_vector_mode_payload_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = PluginConfig.from_mapping({"emotion": {"control_mode": "vector", "vector_entries": [{
                "name": "开心", "keywords": ["开心"], "emotion_weight": .8,
                "happy": .8, "angry": 0, "sad": 0, "afraid": 0,
                "disgusted": 0, "melancholic": 0, "surprised": 0, "calm": 0,
            }]}}, data_dir=Path(tmp))
            entry = EntryManager(cfg.emotion).get_entry("开心")
            self.assertEqual(entry.to_params(), {"emotion_vector": [.8, 0, 0, 0, 0, 0, 0, 0], "emotion_weight": .8})
            client = Client(); service = IndexTTSService(cfg, client, LocalDataManager(cfg.cache, cfg.audio_dir))
            self.assertTrue(await service.synthesize("你好", emotion=entry))
            self.assertTrue(await service.synthesize("你好", emotion=entry))
            self.assertEqual(len(client.payloads), 1)
            self.assertNotIn("emotion_audio", client.payloads[0])
            self.assertEqual(client.payloads[0]["emotion_vector"], [.8, 0, 0, 0, 0, 0, 0, 0])

    async def test_cache_namespace_and_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); cache = LocalDataManager(cfg.cache, cfg.audio_dir); payload = {"text": "x"}
            saved = cache.save(payload, b"RIFFxxxxWAVE"); self.assertIsNotNone(saved)
            self.assertIsNotNone(cache.get(payload)); saved.write_bytes(b"")
            self.assertIsNone(cache.get(payload))

    def test_cleanup_removes_empty_expired_and_excess_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp))
            cache = LocalDataManager(replace(cfg.cache, expire_hours=1, max_files=1), cfg.audio_dir)
            empty = cache.audio_dir / "indextts_empty.wav"; empty.write_bytes(b"")
            expired = cache.audio_dir / "indextts_expired.wav"; expired.write_bytes(b"RIFFxxxxWAVE")
            os.utime(expired, (time.time() - 7200, time.time() - 7200))
            older = cache.audio_dir / "indextts_older.wav"; older.write_bytes(b"RIFFxxxxWAVE")
            os.utime(older, (time.time() - 10, time.time() - 10))
            newer = cache.audio_dir / "indextts_newer.wav"; newer.write_bytes(b"RIFFxxxxWAVE")
            cache.cleanup()
            self.assertFalse(empty.exists())
            self.assertFalse(expired.exists())
            self.assertFalse(older.exists())
            self.assertTrue(newer.exists())

    def test_invalid_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                PluginConfig.from_mapping({"client": {"base_url": "not a url"}}, data_dir=Path(tmp))
            with self.assertRaises(ValueError):
                PluginConfig.from_mapping({"tts": {"default_language": "KO"}}, data_dir=Path(tmp))
            with self.assertRaises(ValueError):
                PluginConfig.from_mapping({"emotion": {"control_mode": "bad"}}, data_dir=Path(tmp))
            with self.assertRaises(ValueError):
                PluginConfig.from_mapping({"emotion": {"vector_entries": [{"name": "坏", "happy": 2}]}}, data_dir=Path(tmp))

    async def test_tool_emotion_contract(self):
        # Covered by service-level short circuit: invalid tool emotion must not call it.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(Path(tmp)); self.assertIsNone(EntryManager(cfg.emotion).get_entry("不存在"))


class EmotionStatsTests(unittest.TestCase):
    def test_record_merges_and_aggregates_by_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            current_day = [date(2026, 8, 22)]
            path = Path(tmp) / "emotion_stats.json"
            stats = EmotionStats(path, today=lambda: current_day[0])
            stats.record("bot", "开心")
            stats.record("bot", "开心")
            stats.record("auto", None)
            current_day[0] = date(2026, 8, 23)
            stats.record("command", "开心")

            self.assertEqual(stats.daily("2026-08-22"), {"开心": {"bot": 2}, "none": {"auto": 1}})
            self.assertEqual(stats.totals(), {"开心": {"bot": 2, "command": 1}, "none": {"auto": 1}})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {
                "2026-08-22": {"开心": {"bot": 2}, "none": {"auto": 1}},
                "2026-08-23": {"开心": {"command": 1}},
            })

            reopened = EmotionStats(path, today=lambda: date(2026, 8, 23))
            reopened.record("command", "开心")
            self.assertEqual(reopened.totals()["开心"], {"bot": 2, "command": 2})
            self.assertEqual(reopened.path, path)

class TextTests(unittest.TestCase):
    def test_plain_and_markdown(self):
        Plain = type("Plain", (), {"__init__": lambda self, text: setattr(self, "text", text)})
        self.assertEqual(plain_chain_text([Plain("a"), Plain("b")]), "a\nb")
        self.assertIsNone(plain_chain_text([Plain("a"), object()]))
        self.assertEqual(clean_text("# [标题](https://x.test) **好**"), "标题 好")
        self.assertIsNone(clean_text("```code```"))

if __name__ == "__main__": unittest.main()
