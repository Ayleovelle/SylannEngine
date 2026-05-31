"""SylannEngine — AstrBot 前置插件。

本插件的作用：
1. 把 sylanne_core 包注册到 Python 路径中
2. 创建并管理共享引擎实例，LLM 由本插件通过 AstrBot provider_manager 配置
3. 下游插件通过 `from sylanne_core import get_engine` 获取已配置好的引擎

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
    "1.0.0rc3",
)
class SylannEnginePlugin(Star):
    """前置依赖插件。创建共享引擎实例，LLM 由本插件配置。"""

    def __init__(self, context: Context):
        super().__init__(context)
        self._context = context

    async def initialize(self):
        import sylanne_core
        from sylanne_core import SylanneConfig, SylanneEngine

        if sylanne_core._shared_engine is not None:
            await sylanne_core._shared_engine.shutdown()
            sylanne_core._shared_engine = None

        engine = SylanneEngine(
            data_dir="./data/sylannengine",
            llm=self._llm_call,
            config=SylanneConfig(),
        )
        await engine.start()

        sylanne_core._shared_engine = engine
        self._engine = engine
        logger.info(
            "SylannEngine SDK v%s ready — get_engine() now available",
            sylanne_core.__version__,
        )

    async def terminate(self):
        """Plugin cleanup on unload / hot-reload."""
        import sylanne_core

        if hasattr(self, "_engine") and self._engine is not None:
            await self._engine.shutdown()
            self._engine = None
        sylanne_core._shared_engine = None
        logger.info("SylannEngine shutdown complete")

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._context.provider_manager.text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        return response.completion_text
