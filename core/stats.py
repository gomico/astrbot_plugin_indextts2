from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Callable, Literal

from .runtime import logger

EmotionOrigin = Literal["bot", "command", "auto"]
_ORIGINS: tuple[EmotionOrigin, ...] = ("bot", "command", "auto")


class EmotionStats:
    """Small, daily-persisted counter for emotion synthesis usage."""

    def __init__(self, path: Path, *, today: Callable[[], date] = date.today):
        self.path = Path(path)
        self._today = today
        self._lock = RLock()
        self._data = self._read()

    def record(self, origin: EmotionOrigin, emotion_name: str | None) -> None:
        if origin not in _ORIGINS:
            raise ValueError(f"未知情感统计来源：{origin}")
        name = (emotion_name or "none").strip() or "none"
        with self._lock:
            disk_data = self._read()
            if disk_data:
                self._data = disk_data
            counts = self._data.setdefault(self._today().isoformat(), {}).setdefault(name, {})
            counts[origin] = int(counts.get(origin, 0)) + 1
            self._write(self._data)

    def daily(self, day: str | None = None) -> dict[str, dict[str, int]]:
        with self._lock:
            disk_data = self._read()
            if disk_data:
                self._data = disk_data
            return deepcopy(self._data.get(day or self._today().isoformat(), {}))

    def totals(self) -> dict[str, dict[str, int]]:
        with self._lock:
            disk_data = self._read()
            if disk_data:
                self._data = disk_data
            result: dict[str, dict[str, int]] = {}
            for emotions in self._data.values():
                for name, counts in emotions.items():
                    target = result.setdefault(name, {})
                    for origin, count in counts.items():
                        target[origin] = target.get(origin, 0) + count
            return result

    def summary(self, day: str | None = None) -> str:
        values = self.daily(day) if day else self.totals()
        if not values:
            return "暂无情感统计"
        title = f"{day} 情感统计：" if day else "情感统计："
        lines = [title]
        for name in sorted(values):
            counts = values[name]
            total = sum(counts.values())
            sources = "、".join(f"{origin}:{counts.get(origin, 0)}" for origin in _ORIGINS)
            lines.append(f"{name}: {total}（{sources}）")
        return "\n".join(lines)

    def _read(self) -> dict[str, dict[str, dict[str, int]]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(day): {
                str(name): {
                    origin: int(count)
                    for origin, count in counts.items()
                    if origin in _ORIGINS and isinstance(count, int) and count >= 0
                }
                for name, counts in emotions.items()
                if isinstance(emotions, dict) and isinstance(counts, dict)
            }
            for day, emotions in raw.items()
            if isinstance(day, str) and isinstance(emotions, dict)
        }

    def _write(self, data: dict[str, dict[str, dict[str, int]]]) -> None:
        temporary = ""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            logger.warning("写入情感统计失败(%s)", type(exc).__name__)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
