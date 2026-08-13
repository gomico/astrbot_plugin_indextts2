from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .runtime import logger

LANGUAGES = {"ZH", "EN", "JA", "AR", "ES"}
EMOTION_VECTOR_DIMENSIONS = (
    "happy", "angry", "sad", "afraid",
    "disgusted", "melancholic", "surprised", "calm",
)

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "client": {"base_url": "http://127.0.0.1:8000", "api_key": "", "connect_timeout": 10.0, "request_timeout": 300.0, "max_response_mb": 50},
    "tts": {"speaker_audio": "voices/subaru.wav", "default_language": "ZH", "default_emotion_weight": .8, "duration_factor": 1.0, "max_text_length": 200},
    "auto": {"enabled": False, "only_llm_result": True, "tts_probability": .15, "max_text_length": 100, "strip_markdown": True},
    "emotion": {
        "control_mode": "reference_audio",
        "selection_mode": "llm",
        "provider_id": "",
        "judge_timeout": 20.0,
        "fallback_to_keyword": True,
        "entries": [
            {"name": "开心", "keywords": ["开心", "哈哈", "太棒了"], "emotion_audio": "emotions/subaru_happy.wav", "emotion_weight": .8},
        ],
        "vector_entries": [
            {"name": "开心", "keywords": ["开心", "哈哈", "太棒了"], "emotion_weight": .8, "happy": .6, "angry": 0.0, "sad": 0.0, "afraid": 0.0, "disgusted": 0.0, "melancholic": 0.0, "surprised": .2, "calm": 0.0},
            {"name": "平静", "keywords": ["平静"], "emotion_weight": .8, "happy": .05, "angry": 0.0, "sad": .05, "afraid": 0.0, "disgusted": 0.0, "melancholic": .1, "surprised": 0.0, "calm": .6},
            {"name": "紧张", "keywords": ["紧张"], "emotion_weight": .8, "happy": 0.0, "angry": .35, "sad": 0.0, "afraid": .2, "disgusted": 0.0, "melancholic": 0.0, "surprised": .25, "calm": 0.0},
            {"name": "难过", "keywords": ["难过"], "emotion_weight": .8, "happy": 0.0, "angry": 0.0, "sad": .45, "afraid": 0.0, "disgusted": 0.0, "melancholic": .25, "surprised": 0.0, "calm": .1},
        ],
    },
    "cache": {"enabled": True, "expire_hours": 24, "path": "", "max_files": 500, "namespace": "v1"},
    "tool": {"enabled": True, "allow_language_argument": True},
}

def _merge(default: dict[str, Any], supplied: Mapping[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(default)
    for key, value in (supplied or {}).items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result

def migrate_template_keys(config: Mapping[str, Any]) -> bool:
    """Repair legacy template-list entries in AstrBot's mutable config."""
    if not isinstance(config, dict):
        return False
    emotion = config.get("emotion")
    if not isinstance(emotion, dict):
        return False
    changed = False
    for key in ("entries", "vector_entries"):
        entries = emotion.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and not entry.get("__template_key"):
                entry["__template_key"] = entry.get("template") or "default"
                changed = True
    return changed

@dataclass(frozen=True)
class ClientConfig:
    base_url: str; api_key: str; connect_timeout: float; request_timeout: float; max_response_bytes: int

@dataclass(frozen=True)
class TTSConfig:
    speaker_audio: str; default_language: str; default_emotion_weight: float; duration_factor: float; max_text_length: int

@dataclass(frozen=True)
class AutoConfig:
    enabled: bool; only_llm_result: bool; tts_probability: float; max_text_length: int; strip_markdown: bool

@dataclass(frozen=True)
class EmotionConfig:
    selection_mode: str; provider_id: str; judge_timeout: float; fallback_to_keyword: bool; entries: list[dict[str, Any]]
    control_mode: str = "reference_audio"
    vector_entries: list[dict[str, Any]] = field(default_factory=list)

@dataclass(frozen=True)
class CacheConfig:
    enabled: bool; expire_hours: float; path: str; max_files: int; namespace: str

@dataclass(frozen=True)
class ToolConfig:
    enabled: bool; allow_language_argument: bool

@dataclass
class PluginConfig:
    enabled: bool
    client: ClientConfig
    tts: TTSConfig
    auto: AutoConfig
    emotion: EmotionConfig
    cache: CacheConfig
    tool: ToolConfig
    data_dir: Path = field(default_factory=lambda: Path("data/plugins_data/astrbot_plugin_indextts2"))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None, *, data_dir: Path | None = None) -> "PluginConfig":
        cfg = _merge(DEFAULTS, raw)
        c, t, a, e, cache, tool = (cfg[x] for x in ("client", "tts", "auto", "emotion", "cache", "tool"))
        parsed = urlparse(str(c["base_url"]).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("client.base_url 必须是 http(s) URL")
        lang = str(t["default_language"]).upper()
        if lang not in LANGUAGES: raise ValueError("tts.default_language 非法")
        if not 0 <= float(t["default_emotion_weight"]) <= 1: raise ValueError("tts.default_emotion_weight 必须在 0-1")
        if not .5 <= float(t["duration_factor"]) <= 2: raise ValueError("tts.duration_factor 必须在 0.5-2")
        if int(t["max_text_length"]) < 1: raise ValueError("tts.max_text_length 必须大于 0")
        if str(e["selection_mode"]) not in {"off", "keyword", "llm"}: raise ValueError("emotion.selection_mode 非法")
        control_mode = str(e.get("control_mode", "reference_audio"))
        if control_mode not in {"reference_audio", "vector"}: raise ValueError("emotion.control_mode 非法")
        if not 0 <= float(a["tts_probability"]) <= 1: raise ValueError("auto.tts_probability 必须在 0-1")
        if int(a["max_text_length"]) < 1: raise ValueError("auto.max_text_length 必须大于 0")
        if float(c["connect_timeout"]) <= 0 or float(c["request_timeout"]) <= 0 or int(c["max_response_mb"]) < 1: raise ValueError("client 超时或响应限制非法")
        if float(e["judge_timeout"]) <= 0 or float(cache["expire_hours"]) < 0 or int(cache["max_files"]) < 0: raise ValueError("emotion/cache 配置非法")

        def validate_entries(entries: Any, *, vector: bool) -> None:
            if not isinstance(entries, list):
                raise ValueError("情感条目必须是列表")
            names: set[str] = set()
            for entry in entries:
                if not isinstance(entry, Mapping):
                    raise ValueError("情感条目必须是对象")
                keywords = entry.get("keywords", [])
                if not isinstance(keywords, list):
                    raise ValueError("情感关键词必须是列表")
                name = str(entry.get("name", "")).strip()
                if not name or name in names: raise ValueError("情感名称必须非空且唯一")
                try:
                    weight = float(entry.get("emotion_weight", .8))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"情感 {name} 的权重非法") from exc
                if not 0 <= weight <= 1: raise ValueError(f"情感 {name} 的权重非法")
                if not vector and not str(entry.get("emotion_audio", "")).strip():
                    raise ValueError(f"情感 {name} 缺少 emotion_audio")
                if vector:
                    missing = [dimension for dimension in EMOTION_VECTOR_DIMENSIONS if dimension not in entry]
                    if missing: raise ValueError(f"情感 {name} 缺少向量维度：{','.join(missing)}")
                    for dimension in EMOTION_VECTOR_DIMENSIONS:
                        try:
                            value = float(entry[dimension])
                        except (TypeError, ValueError) as exc:
                            raise ValueError(f"情感 {name} 的向量维度 {dimension} 非法") from exc
                        if not 0 <= value <= 1:
                            raise ValueError(f"情感 {name} 的向量维度 {dimension} 必须在 0-1")
                names.add(name)

        validate_entries(e["entries"], vector=False)
        validate_entries(e["vector_entries"], vector=True)
        root = data_dir or Path("data/plugins_data/astrbot_plugin_indextts2")
        root.mkdir(parents=True, exist_ok=True)
        return cls(bool(cfg["enabled"]), ClientConfig(str(c["base_url"]).rstrip("/"), str(c["api_key"]), float(c["connect_timeout"]), float(c["request_timeout"]), int(c["max_response_mb"]) * 1024 * 1024), TTSConfig(str(t["speaker_audio"]).strip(), lang, float(t["default_emotion_weight"]), float(t["duration_factor"]), int(t["max_text_length"])), AutoConfig(bool(a["enabled"]), bool(a["only_llm_result"]), float(a["tts_probability"]), int(a["max_text_length"]), bool(a["strip_markdown"])), EmotionConfig(str(e["selection_mode"]), str(e["provider_id"]), float(e["judge_timeout"]), bool(e["fallback_to_keyword"]), list(e["entries"]), control_mode, list(e["vector_entries"])), CacheConfig(bool(cache["enabled"]), float(cache["expire_hours"]), str(cache["path"]), int(cache["max_files"]), str(cache["namespace"])), ToolConfig(bool(tool["enabled"]), bool(tool["allow_language_argument"])), root)

    @property
    def audio_dir(self) -> Path:
        path = Path(self.cache.path).expanduser() if self.cache.path.strip() else self.data_dir / "audio"
        path.mkdir(parents=True, exist_ok=True)
        return path
