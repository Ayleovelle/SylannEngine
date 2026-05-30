"""Sylanne-Core: Affective computation engine SDK.

面向 AstrBot 插件开发者的情感计算引擎。
文本输入，结构化数据输出。
"""

from __future__ import annotations

from .config import SylanneConfig
from .engine import SylanneEngine
from .types import EngineStatus, HealthStatus, Surface

__all__ = [
    "SylanneEngine",
    "SylanneConfig",
    "Surface",
    "EngineStatus",
    "HealthStatus",
    "get_engine",
]
__version__ = "1.0.0rc1"

_shared_engine: SylanneEngine | None = None


def get_engine() -> SylanneEngine:
    """获取插件版共享引擎实例。

    插件版由 SylannEngine 前置插件创建并配置 LLM，
    下游插件直接调用此函数获取即可，无需自行配置。
    SDK 版用户请自行实例化 SylanneEngine。
    """
    if _shared_engine is None:
        raise RuntimeError(
            "SylannEngine 尚未初始化。请确认前置插件已安装并正常启动。\n"
            "AstrBot WebUI → 插件 → 从 Git 仓库安装 → "
            "https://github.com/Ayleovelle/SylannEngine.git"
        )
    return _shared_engine
