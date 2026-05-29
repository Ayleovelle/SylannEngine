"""SylannEngine — AstrBot 情感计算引擎插件。

本插件为其他 AstrBot 插件提供情感计算能力。
其他插件通过 context.get_registered_star("astrbot_plugin_sylannengine") 获取引擎实例。

Usage (其他插件中):
    engine_star = context.get_registered_star("astrbot_plugin_sylannengine")
    if engine_star:
        surface = await engine_star.star_instance.process("session_id", "你好")
"""

from astrbot.api import logger
from astrbot.api.star import Context, Star

from sylanne_core import SylanneConfig, SylanneEngine


class SylannEngineStar(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._engine: SylanneEngine | None = None

    async def initialize(self):
        config = self.context.config or {}
        data_dir = config.get("sylannengine_data_dir", "./data/sylannengine")
        diagnostics = config.get("sylannengine_diagnostics", False)

        self._engine = SylanneEngine(
            data_dir=data_dir,
            llm=self._llm_call,
            embedding=self._embedding_call,
            config=SylanneConfig(
                diagnostics=diagnostics,
                locale=config.get("sylannengine_locale", "zh"),
            ),
        )
        await self._engine.start()
        logger.info("SylannEngine started.")

    async def process(self, session_id: str, text: str, **ctx) -> dict:
        """供其他插件调用的主入口。"""
        if not self._engine:
            return {"ok": False, "error": {"code": "E_ENGINE_NOT_INITIALIZED"}}
        return await self._engine.process(session_id, text, **ctx)

    async def tick(self, session_id: str, flags: list[str] | None = None) -> dict:
        """无文本的状态推进。"""
        if not self._engine:
            return {"ok": False, "error": {"code": "E_ENGINE_NOT_INITIALIZED"}}
        return await self._engine.tick(session_id, flags)

    def state(self, session_id: str) -> dict:
        """查询当前状态。"""
        if not self._engine:
            return {"ok": False, "error": {"code": "E_ENGINE_NOT_INITIALIZED"}}
        return self._engine.state(session_id)

    def health(self) -> dict:
        """引擎健康检查。"""
        if not self._engine:
            return {"status": "not_initialized"}
        return self._engine.health()

    def reset(self, session_id: str) -> None:
        """重置会话。"""
        if self._engine:
            self._engine.reset(session_id)

    async def terminate(self):
        if self._engine:
            await self._engine.shutdown()
            logger.info("SylannEngine shut down.")

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        """通过 AstrBot 的 LLM 能力调用模型。"""
        from astrbot.core.provider.manager import ProviderManager

        provider_manager: ProviderManager = self.context.provider_manager
        response = await provider_manager.text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        return response.completion_text

    async def _embedding_call(self, text: str) -> list[float]:
        """通过 AstrBot 的 Embedding 能力调用模型（如果可用）。"""
        from astrbot.core.provider.manager import ProviderManager

        provider_manager: ProviderManager = self.context.provider_manager
        if hasattr(provider_manager, "embedding"):
            return await provider_manager.embedding(text)
        raise NotImplementedError("Embedding not available")
