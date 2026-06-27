"""Tests for the LLM assessor — the SDK's semantic organ.

Besides the coarse flags/confidence, the assessor now emits continuous affect
(valence/arousal/wound_risk) that drives the emotion core. These guard the output
contract (keys + ranges), backward-compat (old confidence/flags-only LLM output),
and the keyword fallback used when no LLM is reachable.
"""

from __future__ import annotations

import pytest

from sylanne_core.assessor import _local_fallback, _parse_response, assess_text

_AFFECT_KEYS = {"confidence", "flags", "valence", "arousal", "wound_risk"}


class TestParseResponse:
    def test_full_affect_payload_parsed(self):
        out = _parse_response(
            '{"confidence": 0.8, "flags": ["negative"], '
            '"valence": -0.7, "arousal": 0.6, "wound_risk": 0.4}'
        )
        assert set(out) >= _AFFECT_KEYS
        assert out["confidence"] == pytest.approx(0.8)
        assert out["flags"] == ["negative"]
        assert out["valence"] == pytest.approx(-0.7)
        assert out["arousal"] == pytest.approx(0.6)
        assert out["wound_risk"] == pytest.approx(0.4)

    def test_legacy_confidence_flags_only_defaults_neutral(self):
        # Older LLM that doesn't know the new fields must not break the path.
        out = _parse_response('{"confidence": 0.6, "flags": ["greeting"]}')
        assert out["valence"] == 0.0
        assert out["arousal"] == 0.0
        assert out["wound_risk"] == 0.0

    def test_out_of_range_values_clamped(self):
        out = _parse_response(
            '{"confidence": 5, "flags": [], "valence": -9, "arousal": 9, "wound_risk": 9}'
        )
        assert out["confidence"] == 1.0
        assert out["valence"] == -1.0
        assert out["arousal"] == 1.0
        assert out["wound_risk"] == 1.0

    def test_non_numeric_affect_falls_back_to_neutral(self):
        out = _parse_response('{"confidence": 0.5, "flags": [], "valence": "sad", "arousal": null}')
        assert out["valence"] == 0.0
        assert out["arousal"] == 0.0

    def test_malformed_json_returns_neutral_idle(self):
        out = _parse_response("not json at all")
        assert out["flags"] == ["idle"]
        assert set(out) >= _AFFECT_KEYS
        assert out["valence"] == 0.0

    def test_non_finite_affect_falls_back_to_neutral(self):
        # json.loads accepts the non-standard NaN / Infinity literals, so an LLM can
        # emit them. They must coerce to neutral defaults, not max out the affect.
        out = _parse_response(
            '{"confidence": 0.5, "flags": [], "wound_risk": NaN, "valence": Infinity}'
        )
        assert out["wound_risk"] == 0.0
        assert out["valence"] == 0.0

    @pytest.mark.parametrize("payload", ["[]", '"just text"', "null", "42"])
    def test_non_dict_json_returns_neutral_idle(self, payload):
        # Legal JSON that isn't an object: json.loads succeeds, but the following
        # data.get raises AttributeError. Must fall back to neutral, not propagate.
        out = _parse_response(payload)
        assert out["flags"] == ["idle"]
        assert set(out) >= _AFFECT_KEYS
        assert out["valence"] == 0.0
        assert out["confidence"] == pytest.approx(0.3)

    def test_fenced_json_unwrapped(self):
        out = _parse_response(
            '```json\n{"confidence": 0.7, "flags": ["positive"], "valence": 0.8}\n```'
        )
        assert out["flags"] == ["positive"]
        assert out["valence"] == pytest.approx(0.8)


class TestLocalFallback:
    def test_emits_all_affect_keys_in_range(self):
        out = _local_fallback("随便一句话")
        assert set(out) >= _AFFECT_KEYS
        assert -1.0 <= out["valence"] <= 1.0
        assert 0.0 <= out["arousal"] <= 1.0
        assert 0.0 <= out["wound_risk"] <= 1.0

    def test_positive_keyword_gives_positive_valence(self):
        out = _local_fallback("谢谢你，好开心")
        assert "positive" in out["flags"]
        assert out["valence"] > 0.0

    def test_negative_keyword_gives_negative_valence(self):
        out = _local_fallback("我好难过")
        assert "negative" in out["flags"]
        assert out["valence"] < 0.0

    def test_hostile_keyword_carries_wound_risk(self):
        out = _local_fallback("你滚")
        assert out["wound_risk"] > 0.0

    def test_neutral_text_is_idle_zero_affect(self):
        out = _local_fallback("嗯")
        assert out["flags"] == ["idle"]
        assert out["valence"] == 0.0
        assert out["wound_risk"] == 0.0


class TestAssessText:
    @pytest.mark.asyncio
    async def test_llm_path_returns_affect(self):
        async def fake_llm(system: str, text: str) -> str:
            return '{"confidence": 0.9, "flags": ["intimate"], "valence": 0.6, "arousal": 0.5, "wound_risk": 0.0}'

        out = await assess_text("我想你了", fake_llm)
        assert out["valence"] == pytest.approx(0.6)
        assert "_degraded" not in out

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_degraded(self):
        async def boom(system: str, text: str) -> str:
            raise RuntimeError("no llm")

        out = await assess_text("我好难过", boom)
        assert out["_degraded"] is True
        assert out["valence"] < 0.0  # fallback still produced real affect

    @pytest.mark.asyncio
    async def test_empty_text_is_neutral_idle(self):
        async def unused(system: str, text: str) -> str:  # pragma: no cover
            raise AssertionError("LLM should not be called for empty text")

        out = await assess_text("   ", unused)
        assert out["flags"] == ["idle"]
        assert out["valence"] == 0.0
