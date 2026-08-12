from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import CacheConfig
from .runtime import logger

class LocalDataManager:
    def __init__(self, cfg: CacheConfig, audio_dir: Path):
        self.cfg, self.audio_dir = cfg, audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, payload: dict[str, Any]) -> Path:
        canonical = json.dumps({"namespace": self.cfg.namespace, **payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self.audio_dir / f"indextts_{hashlib.sha256(canonical.encode()).hexdigest()}.wav"

    def get(self, payload: dict[str, Any]) -> tuple[Path, bytes] | None:
        if not self.cfg.enabled: return None
        try:
            path = self._path(payload)
            if not path.exists(): return None
            if path.stat().st_size == 0 or (self.cfg.expire_hours and time.time() - path.stat().st_mtime > self.cfg.expire_hours * 3600):
                path.unlink(missing_ok=True); return None
            data = path.read_bytes()
            if not data: path.unlink(missing_ok=True); return None
            return path, data
        except OSError as exc:
            logger.warning("读取语音缓存失败(%s)", type(exc).__name__); return None

    def save(self, payload: dict[str, Any], data: bytes) -> Path | None:
        if not self.cfg.enabled or not data: return None
        try:
            target = self._path(payload)
            fd, tmp = tempfile.mkstemp(prefix=".indextts_", suffix=".tmp", dir=self.audio_dir)
            try:
                with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
            self.cleanup()
            return target
        except OSError as exc:
            logger.warning("写入语音缓存失败(%s)", type(exc).__name__); return None

    def cleanup(self) -> None:
        """Remove invalid/expired cache entries, then enforce the file budget."""
        if not self.cfg.enabled: return
        try:
            remaining: list[Path] = []
            now = time.time()
            for path in self.audio_dir.glob("indextts_*.wav"):
                try:
                    stat = path.stat()
                    expired = bool(self.cfg.expire_hours and now - stat.st_mtime > self.cfg.expire_hours * 3600)
                    if stat.st_size == 0 or expired:
                        path.unlink(missing_ok=True)
                    else:
                        remaining.append(path)
                except OSError:
                    # A concurrent cache reader/writer may have removed it.
                    continue
            if self.cfg.max_files:
                remaining.sort(key=lambda p: p.stat().st_mtime)
                for path in remaining[:-self.cfg.max_files]:
                    path.unlink(missing_ok=True)
        except OSError as exc: logger.warning("清理语音缓存失败(%s)", type(exc).__name__)
