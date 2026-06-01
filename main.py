"""SylannEngine 鈥?AstrBot 鍓嶇疆鎻掍欢銆?

鏈彃浠剁殑浣滅敤锛?
1. 鎶?sylanne_core 鍖呮敞鍐屽埌 Python 璺緞涓?
2. 鍒涘缓骞剁鐞嗗叡浜紩鎿庡疄渚嬶紝LLM 鐢辨湰鎻掍欢閫氳繃 AstrBot provider_manager 閰嶇疆
3. 涓嬫父鎻掍欢閫氳繃 `from sylanne_core import get_engine` 鑾峰彇宸查厤缃ソ鐨勫紩鎿?

涓嶅鐞嗘秷鎭€佷笉娉ㄥ叆 prompt銆佷笉娉ㄥ唽鍛戒护銆佷笉鐩戝惉浜嬩欢銆傜函鍓嶇疆渚濊禆銆?
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
    "SylannEngine 鍓嶇疆鎻掍欢 鈥?鎻愪緵鎯呮劅璁＄畻寮曟搸渚涘叾浠栨彃浠?import 浣跨敤",
    "2.0.0",
)
class SylannEnginePlugin(Star):
    """鍓嶇疆渚濊禆鎻掍欢銆傚垱寤哄叡浜紩鎿庡疄渚嬶紝LLM 鐢辨湰鎻掍欢閰嶇疆銆?""

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
            "SylannEngine SDK v%s ready 鈥?get_engine() now available",
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
