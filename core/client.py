from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

try:
    import aiohttp
except ImportError:  # pragma: no cover - only useful for source-only test environments
    aiohttp = None  # type: ignore[assignment]

from .config import ClientConfig
from .runtime import logger

@dataclass
class TTSResult:
    ok: bool
    data: bytes | None = None
    error: str = ""
    error_code: str = ""
    status: int | None = None
    request_id: str = ""
    file_path: str = ""
    text: str = ""
    def __bool__(self) -> bool: return self.ok and bool(self.data or self.file_path)

class IndexTTSClient:
    def __init__(self, cfg: ClientConfig, session: aiohttp.ClientSession | None = None):
        self.cfg, self.session, self._owned_session = cfg, session, session is None

    async def open(self) -> None:
        if aiohttp is None:
            raise RuntimeError("aiohttp 未安装，无法调用 IndexTTS API")
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.cfg.request_timeout, connect=self.cfg.connect_timeout))
            self._owned_session = True

    async def close(self) -> None:
        if self.session and self._owned_session and not self.session.closed: await self.session.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}

    async def health(self) -> TTSResult:
        if aiohttp is None:
            return TTSResult(False, error="aiohttp 未安装", error_code="dependency")
        await self.open()
        assert self.session
        try:
            async with self.session.get(f"{self.cfg.base_url}/health", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=min(self.cfg.connect_timeout + 5, 15))) as response:
                if response.status != 200: return await self._error(response)
                # Health body is not used; never buffer an unexpectedly huge body.
                await response.content.read(64 * 1024)
                return TTSResult(True, status=response.status, request_id=response.headers.get("X-Request-ID", ""))
        except asyncio.TimeoutError: return TTSResult(False, error="服务健康检查超时", error_code="timeout")
        except aiohttp.ClientError as exc:
            logger.warning("IndexTTS 健康检查连接失败(%s)", type(exc).__name__)
            return TTSResult(False, error="TTS 服务不可用", error_code="connection")

    async def tts(self, payload: dict[str, Any]) -> TTSResult:
        if aiohttp is None:
            return TTSResult(False, error="aiohttp 未安装", error_code="dependency")
        await self.open()
        assert self.session
        try:
            async with self.session.post(f"{self.cfg.base_url}/v1/tts", json=payload, headers=self._headers()) as response:
                if response.status != 200: return await self._error(response)
                request_id = response.headers.get("X-Request-ID", "")
                length = response.content_length
                if length is not None and (length <= 0 or length > self.cfg.max_response_bytes):
                    return TTSResult(False, error="TTS 响应大小异常", error_code="response_size", status=response.status, request_id=request_id)
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "audio/wav":
                    return TTSResult(False, error="TTS 服务返回了非 WAV 数据", error_code="content_type", status=response.status, request_id=request_id)
                data = await self._read_limited(response, self.cfg.max_response_bytes)
                if not data or len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                    return TTSResult(False, error="TTS 服务返回了无效 WAV 数据", error_code="invalid_wav", status=response.status, request_id=request_id)
                return TTSResult(True, data=data, status=response.status, request_id=request_id)
        except asyncio.TimeoutError: return TTSResult(False, error="语音合成超时", error_code="timeout")
        except aiohttp.ClientPayloadError:
            return TTSResult(False, error="TTS 响应超过大小限制", error_code="response_size")
        except aiohttp.ClientError as exc:
            logger.warning("IndexTTS 请求连接失败(%s)", type(exc).__name__)
            return TTSResult(False, error="TTS 服务不可用", error_code="connection")

    async def _read_limited(self, response: Any, limit: int) -> bytes:
        chunks: list[bytes] = []; size = 0
        while True:
            chunk = await response.content.read(min(64 * 1024, limit + 1 - size))
            if not chunk: return b"".join(chunks)
            size += len(chunk)
            if size > limit: raise aiohttp.ClientPayloadError("response too large")
            chunks.append(chunk)

    async def _error(self, response: Any) -> TTSResult:
        request_id = response.headers.get("X-Request-ID", "")
        body = await self._read_limited(response, min(self.cfg.max_response_bytes, 64 * 1024))
        code = "http_error"; message = {401: "认证失败，请检查 API 密钥", 404: "参考音频不存在，请检查 API 服务端 reference-dir 与配置路径", 429: "TTS 服务繁忙", 503: "TTS 服务尚未就绪"}.get(response.status, "TTS 服务请求失败")
        try:
            error = json.loads(body.decode("utf-8", "replace")).get("error", {})
            code = str(error.get("code") or code)
            if response.status not in {401, 404, 429, 503} and error.get("message"): message = "TTS 请求参数或服务错误"
        except (ValueError, UnicodeError): pass
        logger.warning("IndexTTS API 返回 HTTP %s (%s)", response.status, code)
        return TTSResult(False, error=message, error_code=code, status=response.status, request_id=request_id)
