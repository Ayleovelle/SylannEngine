"""Tests for SylanneEngine.submit() — engine-instance-level single-fire dedup.

Covers the dual-index (msg_id / text-hash) join rules, the detached-task +
shield architecture (cancellation-safety, failure eviction), the lazy
prune/cap window, submit_stats()/participants() diagnostics, and the
loop-rebind regression (KS3) — see the sylanne-core 2.4.0 master spec.
"""

from __future__ import annotations

import asyncio
import gc
import hashlib
import logging
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core.config import SylanneConfig


def _llm() -> AsyncMock:
    return AsyncMock(return_value="ok")


def _hash_key(session_id: str, text: str) -> tuple[str, str]:
    return (session_id, "h:" + hashlib.blake2b(text.encode()).hexdigest()[:32])


class TestConcurrentJoin:
    @pytest.mark.asyncio
    async def test_concurrent_submits_same_msg_id_one_compute(self, tmp_path: Path):
        llm = _llm()
        engine = SylanneEngine(tmp_path, llm=llm)
        await engine.start()
        results = await asyncio.gather(
            *(engine.submit("s1", "hello", msg_id="m1") for _ in range(20))
        )
        assert all(r is results[0] for r in results)
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_submits_same_text_no_msg_id_one_compute(self, tmp_path: Path):
        llm = _llm()
        engine = SylanneEngine(tmp_path, llm=llm)
        await engine.start()
        results = await asyncio.gather(*(engine.submit("s1", "identical text") for _ in range(15)))
        assert all(r is results[0] for r in results)
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_all_awaiters_get_the_same_surface_object(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        results = await asyncio.gather(*(engine.submit("s1", "hi", msg_id="m1") for _ in range(5)))
        first_id = id(results[0])
        assert all(id(r) == first_id for r in results)


class TestDualIndexJoinRules:
    """The dual-index join-rule quadrants (msg_id x hash, hit/miss)."""

    @pytest.mark.asyncio
    async def test_no_msgid_then_no_msgid_joins_via_hash(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        r1 = await engine.submit("s1", "same text")
        r2 = await engine.submit("s1", "same text")
        assert r2 is r1

    @pytest.mark.asyncio
    async def test_no_msgid_then_msgid_upgrades_hash_entry_and_joins(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        r1 = await engine.submit("s1", "same text")  # hash-only entry
        r2 = await engine.submit("s1", "same text", msg_id="m1")  # upgrades it
        assert r2 is r1
        # A later lookup by msg_id alone must now hit directly too.
        r3 = await engine.submit("s1", "same text", msg_id="m1")
        assert r3 is r1

    @pytest.mark.asyncio
    async def test_msgid_then_no_msgid_joins_via_hash(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        r1 = await engine.submit("s1", "same text", msg_id="m1")
        r2 = await engine.submit("s1", "same text")
        assert r2 is r1

    @pytest.mark.asyncio
    async def test_msgid_direct_hit_joins(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        r1 = await engine.submit("s1", "hello", msg_id="m1")
        r2 = await engine.submit("s1", "hello", msg_id="m1")
        assert r2 is r1

    @pytest.mark.asyncio
    async def test_different_msgid_same_text_is_genuine_repeat_computes_fresh(self, tmp_path: Path):
        llm = _llm()
        engine = SylanneEngine(tmp_path, llm=llm)
        await engine.start()
        r1 = await engine.submit("s1", "same text", msg_id="m1")
        r2 = await engine.submit("s1", "same text", msg_id="m2")
        assert r2 is not r1
        assert llm.call_count == 2
        stats = engine.submit_stats()
        assert stats["computed"] == 2
        assert stats["joined"] == 0

    @pytest.mark.asyncio
    async def test_different_session_same_text_never_joins(self, tmp_path: Path):
        llm = _llm()
        engine = SylanneEngine(tmp_path, llm=llm)
        await engine.start()
        r1 = await engine.submit("s1", "same text")
        r2 = await engine.submit("s2", "same text")
        assert r1 is not r2
        assert llm.call_count == 2


class TestTextDivergenceWarning:
    @pytest.mark.asyncio
    async def test_msgid_join_different_text_joins_anyway_and_warns_once(
        self, tmp_path: Path, caplog
    ):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        r1 = await engine.submit("s1", "hello", msg_id="m1")
        with caplog.at_level("WARNING", logger="sylanne_core"):
            r2 = await engine.submit("s1", "goodbye", msg_id="m1")
        # msg_id is authoritative: joins the FIRST submission's result anyway.
        assert r2 is r1
        assert any("DIFFERENT text" in r.message for r in caplog.records)

        caplog.clear()
        with caplog.at_level("WARNING", logger="sylanne_core"):
            r3 = await engine.submit("s1", "yet another text", msg_id="m1")
        assert r3 is r1
        # Warned once per key — not again on the second divergence.
        assert not any("DIFFERENT text" in r.message for r in caplog.records)


class TestCtxDivergence:
    @pytest.mark.asyncio
    async def test_ctx_divergence_logs_debug_once_first_submitter_wins(
        self, tmp_path: Path, caplog
    ):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        r1 = await engine.submit("s1", "hi", msg_id="m1", confidence=0.9)
        with caplog.at_level("DEBUG", logger="sylanne_core"):
            r2 = await engine.submit("s1", "hi", msg_id="m1", confidence=0.1)
        assert r2 is r1
        assert any("differ from this call" in r.message for r in caplog.records)


class TestWindowAndEviction:
    @pytest.mark.asyncio
    async def test_join_within_window(self, tmp_path: Path):
        cfg = SylanneConfig(submit_window_seconds=5.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        await engine.submit("s1", "hi", msg_id="m1")
        before = engine.submit_stats()
        await engine.submit("s1", "hi", msg_id="m1")
        after = engine.submit_stats()
        assert after["joined"] == before["joined"] + 1
        assert after["computed"] == before["computed"]

    @pytest.mark.asyncio
    async def test_recompute_after_window(self, tmp_path: Path):
        cfg = SylanneConfig(submit_window_seconds=0.05)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        await engine.submit("s1", "hi", msg_id="m1")
        await asyncio.sleep(0.15)
        before = engine.submit_stats()
        await engine.submit("s1", "hi", msg_id="m1")
        after = engine.submit_stats()
        assert after["recomputed_after_window"] == before["recomputed_after_window"] + 1

    @pytest.mark.asyncio
    async def test_cap_eviction_never_evicts_inflight(self, tmp_path: Path):
        cfg = SylanneConfig(submit_max_entries=1, submit_window_seconds=100.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()

        started = asyncio.Event()
        gate = asyncio.Event()
        slow_calls = 0
        orig_process = engine.process

        async def maybe_slow(session_id: str, text: str, **kw: object) -> object:
            nonlocal slow_calls
            if session_id == "slow":
                slow_calls += 1
                started.set()
                await gate.wait()
            return await orig_process(session_id, text, **kw)  # type: ignore[arg-type]

        engine.process = maybe_slow  # type: ignore[method-assign]

        inflight = asyncio.ensure_future(engine.submit("slow", "hold text", msg_id="hold-id"))
        await started.wait()

        # Drive several OTHER submissions to completion — well past the
        # submit_max_entries=1 completed-entry cap, triggering prune every call.
        for i in range(5):
            await engine.submit(f"other{i}", f"text{i}", msg_id=f"id{i}")

        # A second submitter for the SAME still-in-flight key must still JOIN —
        # proof the cap never touched the in-flight entry.
        joiner_task = asyncio.ensure_future(engine.submit("slow", "hold text", msg_id="hold-id"))
        await asyncio.sleep(0)  # let it register/join synchronously
        gate.set()
        result, joiner = await asyncio.gather(inflight, joiner_task)
        assert joiner is result
        assert slow_calls == 1

    @pytest.mark.asyncio
    async def test_cap_eviction_evicts_oldest_completed(self, tmp_path: Path):
        cfg = SylanneConfig(submit_max_entries=2, submit_window_seconds=100.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()

        await engine.submit("s0", "text0", msg_id="id0")  # oldest completed
        await engine.submit("s1", "text1", msg_id="id1")
        await engine.submit("s2", "text2", msg_id="id2")  # now 3 completed > cap 2

        before = engine.submit_stats()
        # Prune is lazy (runs at the TOP of submit()): the NEXT submit() call
        # is what actually evicts the now-overflowing oldest entry (id0), so
        # resubmitting it recomputes (tracked as recomputed_after_window, since
        # the key is found in the recent-evicted LRU) rather than joins.
        await engine.submit("s0", "text0", msg_id="id0")
        after = engine.submit_stats()
        assert after["recomputed_after_window"] == before["recomputed_after_window"] + 1
        assert after["joined"] == before["joined"]

        # That single eviction step must only have touched the OLDEST entry —
        # the two more-recent ones (id1, id2) survive it untouched.
        assert ("s1", "id1") in engine._submissions
        assert ("s2", "id2") in engine._submissions


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_failed_compute_evicts_immediately_and_retry_recomputes(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        calls = {"n": 0}
        orig_process = engine.process

        async def flaky(*a: object, **kw: object) -> object:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return await orig_process(*a, **kw)  # type: ignore[arg-type]

        engine.process = flaky  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="boom"):
            await engine.submit("s1", "hello", msg_id="m1")

        # Retrying immediately (well within submit_window_seconds) must
        # recompute, not rejoin the poisoned entry.
        surface = await engine.submit("s1", "hello", msg_id="m1")
        assert surface["session_id"] == "s1"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_first_awaiter_cancellation_does_not_kill_shared_task(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        started = asyncio.Event()
        orig_process = engine.process

        async def slow_process(*a: object, **kw: object) -> object:
            started.set()
            await asyncio.sleep(0.1)
            return await orig_process(*a, **kw)  # type: ignore[arg-type]

        engine.process = slow_process  # type: ignore[method-assign]

        first = asyncio.ensure_future(engine.submit("s1", "hello", msg_id="m1"))
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        # A second submitter for the SAME key must still get the real result —
        # the underlying compute was not killed by the first awaiter's cancel
        # (that's what asyncio.shield is for).
        second = await engine.submit("s1", "hello", msg_id="m1")
        assert second["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_zero_awaiter_exception_is_consumed_no_warning(self, tmp_path: Path, caplog):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()

        async def failing_process(*a: object, **kw: object) -> object:
            await asyncio.sleep(0.01)
            raise RuntimeError("boom")

        engine.process = failing_process  # type: ignore[method-assign]

        outer = asyncio.ensure_future(engine.submit("s1", "hello", msg_id="m1"))
        await asyncio.sleep(0)  # let it register the entry and start awaiting shield
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await outer

        # Let the underlying compute task actually finish (and fail) with
        # nobody left watching it.
        await asyncio.sleep(0.05)
        with caplog.at_level(logging.ERROR):
            gc.collect()
            await asyncio.sleep(0)
        assert not any("never retrieved" in r.message for r in caplog.records)


class TestLoopRebind:
    """KS3 regression: a submission bound to a now-dead loop must never wedge
    the next submit() on the rebound engine."""

    @pytest.mark.asyncio
    async def test_rebind_mid_flight_next_submit_recomputes_not_hang(self, tmp_path: Path):
        m = _llm()

        def first_loop() -> None:
            async def run() -> None:
                engine = await SylanneEngine.shared(tmp_path, llm=m)
                # Fire-and-forget: still (loop-bound) alive when this loop tears
                # down at the end of asyncio.run().
                asyncio.ensure_future(engine.submit("s1", "hello", msg_id="m1"))
                await asyncio.sleep(0)  # let it start and register the entry

            asyncio.run(run())

        t = threading.Thread(target=first_loop)
        t.start()
        t.join()

        # Re-acquire on the current loop: triggers the rebind branch.
        engine = await SylanneEngine.shared(tmp_path, llm=m)
        assert engine._submissions == {}  # dedup table cleared by the rebind fix

        # The next submit for the SAME key must recompute rather than hang or
        # raise trying to join a Task bound to the dead loop.
        surface = await asyncio.wait_for(engine.submit("s1", "hello", msg_id="m1"), timeout=5.0)
        assert surface["session_id"] == "s1"


class TestSubmitStats:
    @pytest.mark.asyncio
    async def test_stats_counts_computed_joined_recomputed(self, tmp_path: Path):
        cfg = SylanneConfig(submit_window_seconds=0.05)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        await engine.submit("s1", "a", msg_id="1")  # computed
        await engine.submit("s1", "a", msg_id="1")  # joined
        await asyncio.sleep(0.15)
        await engine.submit("s1", "a", msg_id="1")  # recomputed_after_window
        stats = engine.submit_stats()
        assert stats["computed"] == 1
        assert stats["joined"] == 1
        assert stats["recomputed_after_window"] == 1

    @pytest.mark.asyncio
    async def test_stats_omit_by_plugin_when_no_plugin_tags_used(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        await engine.submit("s1", "hello", msg_id="m1")
        stats = engine.submit_stats()
        assert "by_plugin" not in stats


class TestParticipants:
    @pytest.mark.asyncio
    async def test_plugin_attach_via_shared_logs_and_registers(self, tmp_path: Path, caplog):
        with caplog.at_level("INFO", logger="sylanne_core"):
            engine = await SylanneEngine.shared(tmp_path, llm=_llm(), plugin="alpha")
        assert any("plugin alpha attached" in r.message for r in caplog.records)
        parts = engine.participants()
        assert len(parts) == 1
        assert parts[0]["plugin"] == "alpha"
        assert parts[0]["submits"] == 0
        assert parts[0]["joins"] == 0

    @pytest.mark.asyncio
    async def test_submit_increments_submits_and_joins_per_plugin(self, tmp_path: Path):
        engine = await SylanneEngine.shared(tmp_path, llm=_llm())
        await engine.submit("s1", "hello", msg_id="m1", plugin="alpha")
        await engine.submit("s1", "hello", msg_id="m1", plugin="beta")
        parts = {p["plugin"]: p for p in engine.participants()}
        assert parts["alpha"]["submits"] == 1
        assert parts["alpha"]["joins"] == 0
        assert parts["beta"]["submits"] == 0
        assert parts["beta"]["joins"] == 1

    @pytest.mark.asyncio
    async def test_participants_snapshot_sorted_by_first_seen(self, tmp_path: Path):
        engine = await SylanneEngine.shared(tmp_path, llm=_llm())
        await engine.submit("s1", "a", msg_id="1", plugin="zzz")
        await asyncio.sleep(0.01)
        await engine.submit("s1", "b", msg_id="2", plugin="aaa")
        names = [p["plugin"] for p in engine.participants()]
        assert names == ["zzz", "aaa"]

    @pytest.mark.asyncio
    async def test_submit_stats_by_plugin_breakdown(self, tmp_path: Path):
        engine = await SylanneEngine.shared(tmp_path, llm=_llm())
        await engine.submit("s1", "hello", msg_id="m1", plugin="alpha")
        await engine.submit("s1", "hello", msg_id="m1", plugin="beta")
        stats = engine.submit_stats()
        assert stats["by_plugin"]["alpha"] == {"submits": 1, "joins": 0}
        assert stats["by_plugin"]["beta"] == {"submits": 0, "joins": 1}

    @pytest.mark.asyncio
    async def test_participants_never_gates_dedup_behavior(self, tmp_path: Path):
        # Same message, DIFFERENT plugin tags: identity must not create separate
        # compute streams — dedup keys purely on (session, msg_id/text-hash).
        llm = _llm()
        engine = SylanneEngine(tmp_path, llm=llm)
        await engine.start()
        r1 = await engine.submit("s1", "hello", msg_id="m1", plugin="alpha")
        r2 = await engine.submit("s1", "hello", msg_id="m1", plugin="totally_different_plugin")
        assert r1 is r2
        assert llm.call_count == 1


class TestDedupBypass:
    @pytest.mark.asyncio
    async def test_dedup_false_is_plain_process_always_recomputes(self, tmp_path: Path):
        llm = _llm()
        engine = SylanneEngine(tmp_path, llm=llm)
        await engine.start()
        r1 = await engine.submit("s1", "hello", msg_id="m1", dedup=False)
        r2 = await engine.submit("s1", "hello", msg_id="m1", dedup=False)
        assert r1 is not r2
        assert llm.call_count == 2
        # dedup=False never touches the submit() dedup table/stats at all.
        assert engine.submit_stats() == {
            "computed": 0,
            "joined": 0,
            "recomputed_after_window": 0,
        }


class TestSharedInstallRepro:
    @pytest.mark.asyncio
    async def test_two_call_sites_same_module_same_message_one_process(self, tmp_path: Path):
        # The shared-install repro, inverted: instead of two plugins each
        # process()-ing independently (2x LLM, the 2.4.0 failure mode), two
        # call sites submit() the SAME platform event and converge to 1x.
        llm = _llm()
        engine = await SylanneEngine.shared(tmp_path, llm=llm)

        async def call_site_a() -> object:
            return await engine.submit("s1", "same platform event", msg_id="evt-1", plugin="a")

        async def call_site_b() -> object:
            return await engine.submit("s1", "same platform event", msg_id="evt-1", plugin="b")

        ra, rb = await asyncio.gather(call_site_a(), call_site_b())
        assert ra is rb
        assert llm.call_count == 1
        stats = engine.submit_stats()
        assert stats["computed"] == 1
        assert stats["joined"] == 1


class TestSubmitInternals:
    """Sanity checks tying the dual-index keys to the documented scheme, so a
    future refactor that silently changes the key shape gets caught here."""

    @pytest.mark.asyncio
    async def test_hash_key_present_after_no_msgid_submit(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        await engine.submit("s1", "hello")
        assert _hash_key("s1", "hello") in engine._submissions

    @pytest.mark.asyncio
    async def test_created_timestamp_is_monotonic_recent(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        before = time.time()
        await engine.submit("s1", "hello", msg_id="m1")
        entry = engine._submissions[("s1", "m1")]
        assert before <= entry.created <= time.time() + 1
