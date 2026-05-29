"""Async utility helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("sylanne_core")


def safe_ensure_future(
    coro: Any, name: str = "task", task_list: list | None = None
) -> "asyncio.Task[Any]":
    loop = asyncio.get_running_loop()
    task = loop.create_task(coro)
    if task_list is not None:
        task_list.append(task)

    def _done(t: "asyncio.Task[Any]") -> None:
        if task_list is not None:
            try:
                task_list.remove(t)
            except ValueError:
                pass
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning(f"Sylanne background task [{name}] failed: {exc}")

    task.add_done_callback(_done)
    return task
