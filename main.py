"""SylannEngine — AstrBot 前置插件。

本插件的唯一作用：把 sylanne_core 包注册到 Python 路径中，
让同一 AstrBot 实例下的其他插件可以直接 `from sylanne_core import SylanneEngine`。

不处理消息、不注入 prompt、不注册命令、不监听事件。纯前置依赖。
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
    "SylannEngine 前置插件 — 提供情感计算引擎供其他插件 import 使用",
    "0.1.0-preview",
)
class SylannEnginePlugin(Star):
    """前置依赖插件。不做任何事，只确保 sylanne_core 可被其他插件 import。"""

    def __init__(self, context: Context):
        super().__init__(context)
        from sylanne_core import __version__
        logger.info("SylannEngine SDK v%s ready — other plugins can now: from sylanne_core import SylanneEngine", __version__)
