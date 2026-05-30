"""SylanneEngine — the public entry point for Sylanne-Core SDK."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import SylanneConfig
from .types import Surface


class SylanneEngine:
    """情感计算引擎。

    Usage:
        engine = SylanneEngine(data_dir="./data", llm=my_llm_fn)
        await engine.start()
        surface = await engine.process("session_1", "你好")
        await engine.shutdown()
    """

    def __init__(
        self,
        data_dir: str | Path,
        llm: Callable[[str, str], Awaitable[str]],
        embedding: Callable[[str], Awaitable[list[float]]] | None = None,
        config: SylanneConfig | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._llm = llm
        self._embedding = embedding
        self._config = config or SylanneConfig()
        self._status: str = "init"
        self._hosts: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: list[Callable[[str, Surface], Any]] = []

    @property
    def status(self) -> str:
        return self._status

    async def start(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._status = "running"

    def on(self, listener: Callable[[str, Surface], Any]) -> None:
        """注册推送监听器。每次 process() 完成后，listener(session_id, surface) 会被调用。"""
        self._listeners.append(listener)

    def off(self, listener: Callable[[str, Surface], Any]) -> None:
        """移除推送监听器。"""
        self._listeners = [fn for fn in self._listeners if fn is not listener]

    def health(self) -> dict[str, Any]:
        """引擎健康检查，开发者用于判断计算模块是否正常。"""
        return {
            "status": self._status,
            "active_sessions": len(self._hosts),
            "data_dir_exists": self._data_dir.exists(),
            "llm_configured": self._llm is not None,
            "embedding_configured": self._embedding is not None,
        }

    async def shutdown(self) -> None:
        for host in self._hosts.values():
            host.flush()
        self._hosts.clear()
        self._locks.clear()
        self._status = "closed"

    async def process(
        self,
        session_id: str,
        text: str,
        *,
        confidence: float = 0.0,
        flags: list[str] | None = None,
        now: float | None = None,
        values: dict[str, float] | None = None,
    ) -> Surface:
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            assessment = (
                await self._assess(text) if self._config.assessor_enabled else None
            )
            event = {
                "text": text,
                "confidence": confidence or (assessment or {}).get("confidence", 0.0),
                "flags": flags or (assessment or {}).get("flags", []),
                "now": now or time.time(),
                "values": values or {},
            }
            result = host.on_request(event, assessment=assessment)
            surface = self._to_surface(session_id, host, result)
            await self._notify(session_id, surface)
            return surface

    async def tick(
        self,
        session_id: str,
        flags: list[str] | None = None,
    ) -> Surface:
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            event = {
                "text": "",
                "confidence": 0.0,
                "flags": flags or ["idle"],
                "now": time.time(),
                "values": {},
            }
            result = host.on_request(event)
            return self._to_surface(session_id, host, result)

    def state(self, session_id: str) -> Surface:
        host = self._get_or_create_host(session_id)
        surface = host.diagnostics()
        return self._to_surface(session_id, host, surface)

    def reset(self, session_id: str) -> None:
        if session_id in self._hosts:
            del self._hosts[session_id]
        safe_name = "".join(
            ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in session_id
        )[:128]
        for suffix in (".alpha.json", ".json"):
            state_file = self._data_dir / f"{safe_name}{suffix}"
            if state_file.exists():
                state_file.unlink()

    def destroy(self, session_id: str) -> None:
        self.reset(session_id)
        if session_id in self._locks:
            del self._locks[session_id]

    # --- internal ---

    async def _notify(self, session_id: str, surface: Surface) -> None:
        for listener in self._listeners:
            try:
                ret = listener(session_id, surface)
                if asyncio.iscoroutine(ret) or asyncio.isfuture(ret):
                    await ret
            except Exception:
                pass

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def _get_or_create_host(self, session_id: str) -> Any:
        if session_id not in self._hosts:
            from .compute import SylanneHost

            self._hosts[session_id] = SylanneHost(
                root=self._data_dir,
                session_key=session_id,
            )
        return self._hosts[session_id]

    async def _assess(self, text: str) -> dict[str, Any] | None:
        if not text.strip():
            return None
        try:
            from .assessor import assess_text

            result = await assess_text(text, self._llm)
            if result and result.pop("_degraded", False):
                if self._status == "running":
                    self._status = "degraded"
            return result
        except Exception:
            if self._status == "running":
                self._status = "degraded"
            return None

    def _to_surface(self, session_id: str, host: Any, raw: dict[str, Any]) -> Surface:
        from .adapter import to_surface

        return to_surface(session_id, host, raw, diagnostics=self._config.diagnostics)
