"""Sylanne-Core: Affective computation engine SDK.

面向 AstrBot 插件开发者的情感计算引擎。
文本输入，结构化数据输出。
"""

from __future__ import annotations

from .engine import SylanneEngine
from .config import SylanneConfig
from .types import Surface

__all__ = ["SylanneEngine", "SylanneConfig", "Surface"]
__version__ = "0.1.0"
