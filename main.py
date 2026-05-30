"""SylannEngine SDK — AstrBot 共享插件。

本插件的唯一作用：把 sylanne_core 包注册到 Python 路径中，
让同一 AstrBot 实例下的其他插件可以直接 `from sylanne_core import SylanneEngine`。

不处理消息、不注入 prompt、不注册命令。纯依赖提供者。
"""

from __future__ import annotations

import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

try:
    from astrbot.api import logger
    from astrbot.api.star import Context, Star, register
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylannengine")

    class Star:  # type: ignore
        def __init__(self, context=None):
            pass

    class Context:  # type: ignore
        pass

    def register(*args, **kwargs):
        def decorator(cls):
            return cls
        return decorator


@register(
    "astrbot_plugin_sylannengine",
    "Ayleovelle",
    "SylannEngine SDK 共享插件，提供情感计算引擎供其他插件调用",
    "0.1.0-preview",
)
class SylannEnginePlugin(Star):
    """共享 SDK 插件。不处理消息，只确保 sylanne_core 可被其他插件 import。"""

    def __init__(self, context: Context):
        super().__init__(context)
        logger.info(
            "SylannEngine SDK v%s loaded. "
            "Other plugins can now: from sylanne_core import SylanneEngine",
            self._get_version(),
        )

    @staticmethod
    def _get_version() -> str:
        try:
            from sylanne_core import __version__
            return __version__
        except ImportError:
            return "unknown"
