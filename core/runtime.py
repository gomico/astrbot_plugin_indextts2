"""Small AstrBot compatibility boundary; production imports use AstrBot classes."""
from __future__ import annotations

import logging

try:  # pragma: no cover - exercised inside AstrBot
    from astrbot.api import logger  # type: ignore
    from astrbot.api.event import filter  # type: ignore
    from astrbot.api.star import Context, Star, register  # type: ignore
    from astrbot.core.message.components import Plain, Record  # type: ignore
except ImportError:  # Enables unit tests without an AstrBot installation.
    logger = logging.getLogger("astrbot_plugin_indextts2")

    class _Filter:
        def _decorator(self, *_args, **_kwargs):
            return lambda func: func
        command = on_decorating_result = llm_tool = _decorator
    filter = _Filter()

    def register(*_args, **_kwargs):
        return lambda cls: cls

    class Context:  # type: ignore[no-redef]
        pass

    class Star:  # type: ignore[no-redef]
        def __init__(self, context=None): self.context = context

    class Plain:  # type: ignore[no-redef]
        def __init__(self, text=""): self.text = text

    class Record:  # type: ignore[no-redef]
        @classmethod
        def fromBase64(cls, value): return cls(value)
        @classmethod
        def fromFileSystem(cls, value): return cls(value)
        def __init__(self, value): self.value = value
