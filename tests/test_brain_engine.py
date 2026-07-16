"""Public Engine contracts for durable brain events and targeted feedback."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core.compute.brain_backend_coordinator import BrainBackendCoordinator
from sylanne_core.compute.brain_errors import BrainNotificationBackpressureError
from sylanne_core.compute.brain_store import BrainStateStore, SessionLoaded, session_digest
from sylanne_core.compute.host import SylanneAlphaHost
from sylanne_core.config import BrainComputeConfig, SylanneConfig
from sylanne_core.types import FeedbackReceipt, Surface


def _config(*, assessor_enabled: bool = False, c_enabled: bool = False) -> SylanneConfig:
    return SylanneConfig(
        assessor_enabled=assessor_enabled,
        brain_compute=BrainComputeConfig(enabled=True, c_enabled=c_enabled),
    )


@pytest.fixture
async def brain_engine(tmp_path: Path) -> AsyncIterator[SylanneEngine]:
    engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=_config(),
    )
    await engine.start()
    try:
        yield engine
    finally:
        await engine.shutdown()


def _brain_event(surface: Surface) -> dict[str, Any]:
    event = surface["pipeline"].get("brain_event")
    assert isinstance(event, dict)
    return cast(dict[str, Any], event)


async def _wait_for_durable_tick(
    engine: SylanneEngine,
    session_id: str,
    tick_id: int,
    *,
    timeout: float = 5.0,
) -> None:
    store = engine._brain_store
    assert store is not None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        loaded = await asyncio.to_thread(store.load, session_digest(session_id))
        if isinstance(loaded, SessionLoaded) and loaded.bundle.b.tick_id >= tick_id:
            return
        if loop.time() >= deadline:
            raise TimeoutError(f"durable tick did not reach {tick_id}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_start_creates_one_store_shared_by_every_brain_host(
    brain_engine: SylanneEngine,
) -> None:
    store = brain_engine._brain_store
    assert isinstance(store, BrainStateStore)

    await brain_engine.process("a", "one", event_id="a-1")
    await brain_engine.process("b", "two", event_id="b-1")

    assert brain_engine._hosts["a"].brain_store is store
    assert brain_engine._hosts["b"].brain_store is store


@pytest.mark.asyncio
async def test_process_propagates_explicit_event_id_exactly(
    brain_engine: SylanneEngine,
) -> None:
    surface = await brain_engine.process(
        "session",
        "that hurt",
        event_id="platform-message-17",
        confidence=0.9,
        flags=["hurt", "boundary"],
    )

    assert _brain_event(surface) == {
        "status": "applied",
        "event_id": "platform-message-17",
        "generation": 0,
        "tick_id": 1,
        "history_epoch": 1,
        "mutation_seq": 1,
    }


@pytest.mark.asyncio
async def test_process_without_event_id_reports_the_generated_uuid(
    brain_engine: SylanneEngine,
) -> None:
    surface = await brain_engine.process("session", "ordinary event")

    event_id = _brain_event(surface)["event_id"]
    assert isinstance(event_id, str)
    assert str(uuid.UUID(event_id)) == event_id


@pytest.mark.asyncio
async def test_submit_passes_msg_id_as_canonical_event_id(
    brain_engine: SylanneEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    expected = cast(Surface, {"session_id": "session"})

    async def process(session_id: str, text: str, **kwargs: Any) -> Surface:
        captured.update(session_id=session_id, text=text, **kwargs)
        return expected

    monkeypatch.setattr(brain_engine, "process", process)

    actual = await brain_engine.submit("session", "payload", msg_id="message-42")

    assert actual is expected
    assert captured["event_id"] == "message-42"


@pytest.mark.asyncio
async def test_brain_submit_without_msg_id_does_not_merge_equal_text(
    brain_engine: SylanneEngine,
) -> None:
    first = await brain_engine.submit("session", "same text")
    second = await brain_engine.submit("session", "same text")

    first_event = _brain_event(first)
    second_event = _brain_event(second)
    assert first_event["event_id"] != second_event["event_id"]
    assert (first_event["tick_id"], second_event["tick_id"]) == (1, 2)


@pytest.mark.asyncio
async def test_brain_submit_sequential_same_msg_id_uses_durable_duplicate(
    brain_engine: SylanneEngine,
) -> None:
    first = await brain_engine.submit("session", "first", msg_id="message-1")
    duplicate = await brain_engine.submit("session", "retry", msg_id="message-1")

    assert _brain_event(first)["status"] == "applied"
    assert _brain_event(duplicate)["status"] == "duplicate"
    assert _brain_event(duplicate)["event_id"] == "message-1"


@pytest.mark.asyncio
async def test_concurrent_process_calls_with_same_event_id_join_one_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=_config(assessor_enabled=True),
    )
    assessor_calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def assess(_text: str) -> dict[str, Any]:
        nonlocal assessor_calls
        assessor_calls += 1
        entered.set()
        await release.wait()
        return {
            "confidence": 0.9,
            "flags": ["hurt"],
            "valence": -0.8,
            "arousal": 0.7,
            "wound_risk": 0.9,
        }

    monkeypatch.setattr(engine, "_assess", assess)
    await engine.start()
    try:
        first = asyncio.create_task(engine.process("session", "first", event_id="same-id"))
        await asyncio.wait_for(entered.wait(), timeout=2.0)
        second = asyncio.create_task(engine.process("session", "second", event_id="same-id"))
        await asyncio.sleep(0)
        release.set()
        first_surface, second_surface = await asyncio.gather(first, second)

        assert assessor_calls == 1
        assert _brain_event(first_surface)["tick_id"] == 1
        assert _brain_event(second_surface)["tick_id"] == 1
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_formal_allocation_occurs_after_assessment_from_latest_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=_config(assessor_enabled=True),
    )
    slow_entered = asyncio.Event()
    release_slow = asyncio.Event()

    async def assess(text: str) -> dict[str, Any]:
        if text == "slow":
            slow_entered.set()
            await release_slow.wait()
        return {"confidence": 0.9, "flags": ["hurt"]}

    monkeypatch.setattr(engine, "_assess", assess)
    await engine.start()
    try:
        slow = asyncio.create_task(engine.process("session", "slow", event_id="slow-id"))
        await asyncio.wait_for(slow_entered.wait(), timeout=2.0)
        fast = await engine.process("session", "fast", event_id="fast-id")
        release_slow.set()
        slow_surface = await slow

        assert _brain_event(fast)["tick_id"] == 1
        assert _brain_event(slow_surface)["tick_id"] == 2
    finally:
        release_slow.set()
        await engine.shutdown()


@pytest.mark.asyncio
async def test_durable_duplicate_after_restart_skips_assessor_and_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=_config(),
    )
    await first.start()
    await first.process("session", "original", event_id="durable-id", flags=["hurt"])
    await first.shutdown()

    second = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=_config(assessor_enabled=True),
    )

    async def forbidden_assessment(_text: str) -> dict[str, Any]:
        raise AssertionError("durable duplicate must skip assessment")

    def forbidden_pipeline(self: SylanneAlphaHost, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("durable duplicate must skip the complete pipeline")

    monkeypatch.setattr(second, "_assess", forbidden_assessment)
    monkeypatch.setattr(SylanneAlphaHost, "on_request", forbidden_pipeline)
    await second.start()
    try:
        surface = await second.process("session", "retry text may differ", event_id="durable-id")
        receipt = _brain_event(surface)
        assert receipt["status"] == "duplicate"
        assert receipt["event_id"] == "durable-id"
        assert receipt["tick_id"] == 1
    finally:
        await second.shutdown()


@pytest.mark.asyncio
async def test_blank_text_is_still_an_accepted_brain_event(
    brain_engine: SylanneEngine,
) -> None:
    surface = await brain_engine.process("session", "", event_id="blank-1")

    receipt = _brain_event(surface)
    assert receipt["status"] == "applied"
    assert receipt["tick_id"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_id",
    ["", "line\nbreak", "zero\u200bwidth", "x" * 257, "\ud800"],
)
async def test_process_rejects_invalid_explicit_event_id(
    brain_engine: SylanneEngine,
    event_id: str,
) -> None:
    with pytest.raises(ValueError, match="event_id"):
        await brain_engine.process("session", "event", event_id=event_id)


@pytest.mark.asyncio
async def test_public_feedback_returns_typed_targeted_receipt_and_dedups(
    brain_engine: SylanneEngine,
) -> None:
    await brain_engine.process(
        "session",
        "that hurt",
        event_id="event-1",
        confidence=1.0,
        flags=["hurt", "boundary"],
    )

    applied = await brain_engine.feedback(
        "session",
        target_tick=1,
        value=1.0,
        confidence=1.0,
        source="astrbot.plugin",
        feedback_id="feedback-1",
    )
    duplicate = await brain_engine.feedback(
        "session",
        target_tick=1,
        value=1.0,
        confidence=1.0,
        source="astrbot.plugin",
        feedback_id="feedback-1",
    )

    assert isinstance(applied, FeedbackReceipt)
    assert applied.status == "applied"
    assert applied.session_id == "session"
    assert applied.target_tick == 1
    assert applied.feedback_id == "feedback-1"
    assert applied.applied_dimensions
    assert applied.applied_synapses == 0
    assert applied.mutation_seq == 2
    assert duplicate == FeedbackReceipt(
        status="duplicate",
        session_id="session",
        target_tick=1,
        feedback_id="feedback-1",
        applied_dimensions=applied.applied_dimensions,
        applied_synapses=applied.applied_synapses,
        mutation_seq=2,
    )


@pytest.mark.asyncio
async def test_feedback_rejects_future_tick_before_persisting_a_miss(
    brain_engine: SylanneEngine,
) -> None:
    await brain_engine.process("session", "event", event_id="event-1")

    with pytest.raises(ValueError, match="target_tick"):
        await brain_engine.feedback(
            "session",
            target_tick=2,
            value=1.0,
            confidence=1.0,
            source="plugin",
            feedback_id="future-feedback",
        )


@pytest.mark.asyncio
async def test_feedback_zero_signal_is_durable_no_effect(
    brain_engine: SylanneEngine,
) -> None:
    await brain_engine.process("session", "event", event_id="event-1")

    first = await brain_engine.feedback(
        "session",
        target_tick=1,
        value=-0.0,
        confidence=1.0,
        source="plugin",
    )
    second = await brain_engine.feedback(
        "session",
        target_tick=1,
        value=0.0,
        confidence=1.0,
        source="plugin",
    )

    assert first.status == "no_effect"
    assert first.mutation_seq == 1
    assert second.feedback_id == first.feedback_id
    assert second.status == "duplicate"
    assert second.mutation_seq == 1


@pytest.mark.asyncio
async def test_feedback_ttl_uses_trusted_clock_and_persists_missed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sylanne_core.compute.void_scar_engine as void_scar_module

    clock = [100.0]
    monkeypatch.setattr(void_scar_module.time, "time", lambda: clock[0])
    config = SylanneConfig(
        assessor_enabled=False,
        brain_compute=BrainComputeConfig(enabled=True, feedback_ttl_seconds=1.0),
    )
    engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=config,
    )
    await engine.start()
    try:
        await engine.process("session", "event", event_id="event-1")
        clock[0] = 102.0
        first = await engine.feedback(
            "session",
            target_tick=1,
            value=1.0,
            confidence=1.0,
            source="plugin",
            feedback_id="expired-1",
        )
        duplicate = await engine.feedback(
            "session",
            target_tick=1,
            value=1.0,
            confidence=1.0,
            source="plugin",
            feedback_id="expired-1",
        )

        assert first.status == "missed"
        assert first.mutation_seq == 1
        assert duplicate.status == "duplicate"
        assert duplicate.mutation_seq == 1
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_feedback_disabled_returns_canonical_receipt_without_creating_host(
    tmp_path: Path,
) -> None:
    engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=SylanneConfig(assessor_enabled=False),
    )
    await engine.start()
    try:
        receipt = await engine.feedback(
            "session",
            target_tick=0,
            value=1.0,
            confidence=1.0,
            source="plugin",
        )

        assert receipt.status == "disabled"
        assert len(receipt.feedback_id) == 64
        assert engine._hosts == {}
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_tick", True, "target_tick"),
        ("target_tick", -1, "target_tick"),
        ("value", float("nan"), "value"),
        ("value", float("inf"), "value"),
        ("confidence", -0.1, "confidence"),
        ("confidence", 1.1, "confidence"),
        ("confidence", float("nan"), "confidence"),
    ],
)
async def test_feedback_rejects_invalid_numeric_boundary(
    brain_engine: SylanneEngine,
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs: dict[str, object] = {
        "target_tick": 0,
        "value": 0.0,
        "confidence": 1.0,
        "source": "plugin",
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=message):
        await brain_engine.feedback("session", **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_c_applied_synapse_count_survives_restart_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(c_enabled=True)
    first_engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=config,
    )
    await first_engine.start()
    try:
        await first_engine.process(
            "session",
            "strong event",
            event_id="event-1",
            confidence=1.0,
            flags=["hurt", "boundary"],
        )
        original = BrainBackendCoordinator.prepare_feedback

        def report_seven_synapses(self: BrainBackendCoordinator, *args: Any, **kwargs: Any) -> Any:
            candidate = replace(original(self, *args, **kwargs), applied_synapses=7)
            self._pending = candidate
            return candidate

        monkeypatch.setattr(BrainBackendCoordinator, "prepare_feedback", report_seven_synapses)
        first = await first_engine.feedback(
            "session",
            target_tick=1,
            value=1.0,
            confidence=1.0,
            source="plugin",
            feedback_id="feedback-1",
        )
        assert first.applied_synapses == 7
    finally:
        await first_engine.shutdown()

    second_engine = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=config,
    )
    await second_engine.start()
    try:
        duplicate = await second_engine.feedback(
            "session",
            target_tick=1,
            value=1.0,
            confidence=1.0,
            source="plugin",
            feedback_id="feedback-1",
        )
        assert duplicate.status == "duplicate"
        assert duplicate.applied_synapses == first.applied_synapses
    finally:
        await second_engine.shutdown()


@pytest.mark.asyncio
async def test_listener_same_session_reentry_does_not_deadlock(
    brain_engine: SylanneEngine,
) -> None:
    seen: list[int] = []

    async def listener(_session_id: str, surface: Surface) -> None:
        seen.append(int(_brain_event(surface)["tick_id"]))
        if len(seen) == 1:
            await brain_engine.process("session", "nested", event_id="nested")

    brain_engine.on(listener)
    await asyncio.wait_for(
        brain_engine.process("session", "outer", event_id="outer"),
        timeout=2.0,
    )
    await brain_engine.drain_notifications(timeout=2.0)

    assert seen == [1, 2]


@pytest.mark.asyncio
async def test_cross_session_listener_cycle_does_not_deadlock(
    brain_engine: SylanneEngine,
) -> None:
    seen: list[tuple[str, str]] = []

    async def listener(session_id: str, surface: Surface) -> None:
        event_id = str(_brain_event(surface)["event_id"])
        seen.append((session_id, event_id))
        if event_id == "outer-a":
            await brain_engine.process("b", "nested from a", event_id="nested-b")
        elif event_id == "outer-b":
            await brain_engine.process("a", "nested from b", event_id="nested-a")

    brain_engine.on(listener)
    await asyncio.wait_for(
        asyncio.gather(
            brain_engine.process("a", "outer", event_id="outer-a"),
            brain_engine.process("b", "outer", event_id="outer-b"),
        ),
        timeout=2.0,
    )
    await brain_engine.drain_notifications(timeout=2.0)

    assert set(seen) == {
        ("a", "outer-a"),
        ("b", "outer-b"),
        ("a", "nested-a"),
        ("b", "nested-b"),
    }


@pytest.mark.asyncio
async def test_cancelling_process_waiter_does_not_cancel_notification_delivery(
    brain_engine: SylanneEngine,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    delivered: list[str] = []

    async def listener(_session_id: str, surface: Surface) -> None:
        entered.set()
        await release.wait()
        delivered.append(str(_brain_event(surface)["event_id"]))

    brain_engine.on(listener)
    process = asyncio.create_task(
        brain_engine.process("session", "event", event_id="cancelled-waiter")
    )
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    process.cancel()
    with pytest.raises(asyncio.CancelledError):
        await process

    release.set()
    await brain_engine.drain_notifications(timeout=2.0)
    duplicate = await brain_engine.process("session", "retry", event_id="cancelled-waiter")

    assert delivered == ["cancelled-waiter"]
    assert _brain_event(duplicate)["status"] == "duplicate"


@pytest.mark.asyncio
async def test_full_notification_capacity_rejects_listener_reentry_before_mutation(
    brain_engine: SylanneEngine,
) -> None:
    first_listener_entered = asyncio.Event()
    try_nested = asyncio.Event()
    nested_outcome: asyncio.Future[BaseException | None] = (
        asyncio.get_running_loop().create_future()
    )
    seen: list[int] = []

    async def listener(_session_id: str, surface: Surface) -> None:
        tick = int(_brain_event(surface)["tick_id"])
        seen.append(tick)
        if tick != 1:
            return
        first_listener_entered.set()
        await try_nested.wait()
        try:
            await brain_engine.process("session", "nested", event_id="listener-overflow")
        except BaseException as error:
            nested_outcome.set_result(error)
        else:
            nested_outcome.set_result(None)

    brain_engine.on(listener)
    accepted = [
        asyncio.create_task(
            brain_engine.process("session", f"event {tick}", event_id=f"event-{tick}")
        )
        for tick in range(1, 65)
    ]
    await asyncio.wait_for(first_listener_entered.wait(), timeout=5.0)
    await _wait_for_durable_tick(brain_engine, "session", 64)

    top_level_waiter = asyncio.create_task(
        brain_engine.process("session", "top-level waiter", event_id="event-65")
    )
    await asyncio.sleep(0)
    assert not top_level_waiter.done()
    try_nested.set()

    error = await asyncio.wait_for(nested_outcome, timeout=2.0)
    assert isinstance(error, BrainNotificationBackpressureError)
    loaded = await asyncio.to_thread(
        cast(BrainStateStore, brain_engine._brain_store).load,
        session_digest("session"),
    )
    assert isinstance(loaded, SessionLoaded)
    assert loaded.bundle.b.tick_id == 64

    await asyncio.gather(*accepted, top_level_waiter)
    await brain_engine.drain_notifications(timeout=5.0)
    assert seen == list(range(1, 66))


@pytest.mark.asyncio
async def test_async_listener_timeout_continues_to_next_listener(
    brain_engine: SylanneEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sylanne_core.engine as engine_module

    never = asyncio.Event()
    seen: list[str] = []

    async def blocking_listener(_session_id: str, _surface: Surface) -> None:
        seen.append("blocking")
        await never.wait()

    def following_listener(_session_id: str, _surface: Surface) -> None:
        seen.append("following")

    monkeypatch.setattr(engine_module, "_LISTENER_TIMEOUT_SECONDS", 0.01)
    brain_engine.on(blocking_listener)
    brain_engine.on(following_listener)

    await asyncio.wait_for(
        brain_engine.process("session", "event", event_id="timeout-event"),
        timeout=2.0,
    )

    assert seen == ["blocking", "following"]


@pytest.mark.asyncio
async def test_listener_that_suppresses_cancellation_cannot_extend_timeout(
    brain_engine: SylanneEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sylanne_core.engine as engine_module

    cancelled = asyncio.Event()
    release = asyncio.Event()
    following = asyncio.Event()

    async def stubborn_listener(_session_id: str, _surface: Surface) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()

    def following_listener(_session_id: str, _surface: Surface) -> None:
        following.set()

    monkeypatch.setattr(engine_module, "_LISTENER_TIMEOUT_SECONDS", 0.01)
    brain_engine.on(stubborn_listener)
    brain_engine.on(following_listener)
    process = asyncio.create_task(
        brain_engine.process("session", "event", event_id="stubborn-listener")
    )
    try:
        await asyncio.wait_for(cancelled.wait(), timeout=2.0)
        await asyncio.sleep(0.05)
        assert following.is_set()
    finally:
        release.set()
        await asyncio.wait_for(process, timeout=2.0)


@pytest.mark.asyncio
async def test_reset_from_listener_stops_current_and_queued_old_generation_callbacks(
    brain_engine: SylanneEngine,
) -> None:
    first_entered = asyncio.Event()
    allow_reset = asyncio.Event()
    listener_a: list[str] = []
    listener_b: list[str] = []

    async def reset_listener(_session_id: str, surface: Surface) -> None:
        event_id = str(_brain_event(surface)["event_id"])
        listener_a.append(event_id)
        if event_id == "outer":
            first_entered.set()
            await allow_reset.wait()
            await brain_engine.reset("session")

    def later_listener(_session_id: str, surface: Surface) -> None:
        listener_b.append(str(_brain_event(surface)["event_id"]))

    brain_engine.on(reset_listener)
    brain_engine.on(later_listener)
    outer = asyncio.create_task(brain_engine.process("session", "outer", event_id="outer"))
    await asyncio.wait_for(first_entered.wait(), timeout=2.0)
    queued_old = asyncio.create_task(
        brain_engine.process("session", "queued old", event_id="queued-old")
    )
    await _wait_for_durable_tick(brain_engine, "session", 2)
    allow_reset.set()

    await asyncio.wait_for(asyncio.gather(outer, queued_old), timeout=2.0)
    after = await brain_engine.process("session", "after reset", event_id="after-reset")
    await brain_engine.drain_notifications(timeout=2.0)

    assert listener_a == ["outer", "after-reset"]
    assert listener_b == ["after-reset"]
    assert _brain_event(after)["generation"] == 1
    assert _brain_event(after)["tick_id"] == 1


@pytest.mark.asyncio
async def test_shutdown_drains_notifications_and_releases_store_lease(
    tmp_path: Path,
) -> None:
    config = _config()
    first = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=config,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    delivered = asyncio.Event()

    async def listener(_session_id: str, _surface: Surface) -> None:
        entered.set()
        await release.wait()
        delivered.set()

    first.on(listener)
    await first.start()
    process = asyncio.create_task(first.process("session", "event", event_id="event-1"))
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    shutdown = asyncio.create_task(first.shutdown())
    await asyncio.sleep(0)
    assert not shutdown.done()
    release.set()
    await asyncio.wait_for(asyncio.gather(process, shutdown), timeout=2.0)

    assert delivered.is_set()
    assert first.status == "closed"
    assert first._brain_store is None

    second = SylanneEngine(
        data_dir=tmp_path,
        llm=AsyncMock(return_value="unused"),
        config=config,
    )
    await second.start()
    try:
        duplicate = await second.process("session", "retry", event_id="event-1")
        assert _brain_event(duplicate)["status"] == "duplicate"
    finally:
        await second.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["", " space", "bad/source", "x" * 65])
async def test_feedback_rejects_invalid_source(
    brain_engine: SylanneEngine,
    source: str,
) -> None:
    with pytest.raises(ValueError, match="source"):
        await brain_engine.feedback(
            "session",
            target_tick=0,
            value=0.0,
            confidence=1.0,
            source=source,
        )
