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


class TestIntentDirectOutput:
    """v26 A.1：assessor 直出 intent——门在 takeover 上，关闭态逐字节不变。"""

    def test_prompt_unchanged_when_off(self):
        from sylanne_core.assessor import _SYSTEM_PROMPT, _SYSTEM_PROMPT_WITH_INTENT

        assert "intent" not in _SYSTEM_PROMPT           # 旧 prompt 一字未动
        assert '"intent"' in _SYSTEM_PROMPT_WITH_INTENT  # 替换真的生效（防静默 no-op）
        assert "撒娇(亲昵求关注)" in _SYSTEM_PROMPT_WITH_INTENT

    def test_parse_no_intent_key_when_off(self):
        out = _parse_response('{"confidence": 0.8, "flags": [], "intent": "生气"}')
        assert "intent" not in out                      # 关闭态键集与旧版逐字相同

    def test_parse_intent_sanitized_when_on(self):
        good = _parse_response('{"confidence": 0.8, "flags": [], "intent": "生气"}',
                               want_intent=True)
        assert good["intent"] == "生气"
        # 首尾引号/标点可剥（LLM 常见毛边）
        quoted = _parse_response('{"confidence": 0.8, "flags": [], "intent": "撒娇。"}',
                                 want_intent=True)
        assert quoted["intent"] == "撒娇"
        # 红队修订：精确匹配——否定/转述/混排一律归空，不再被子串匹配骗过。
        for raw in ('"无"', '"完全无关的话"', "null", "42", f'"{"x" * 99}"',
                    '"不生气"', '"别生气"', '"没有施压"', '"是生气不是撒娇"'):
            out = _parse_response(
                f'{{"confidence": 0.5, "flags": [], "intent": {raw}}}', want_intent=True
            )
            assert out["intent"] == "", raw             # 词表外一律归空（=今日生产语义）

    def test_fallback_never_classifies_intent(self):
        # 红队修订：兜底不对用户原文做意图分类（"你生气了吗"会被误判成生气）——
        # LLM 不在场就诚实给空。
        assert _local_fallback("对不起嘛别气了", want_intent=True)["intent"] == ""
        assert _local_fallback("你生气了吗", want_intent=True)["intent"] == ""
        assert _local_fallback("我没有生气", want_intent=True)["intent"] == ""
        assert "intent" not in _local_fallback("对不起嘛")   # off：无键

    @pytest.mark.asyncio
    async def test_assess_text_threads_want_intent(self):
        prompts: list[str] = []

        async def spy_llm(system: str, user: str) -> str:
            prompts.append(system)
            return '{"confidence": 0.9, "flags": [], "intent": "撒娇"}'

        off = await assess_text("抱抱我嘛", spy_llm)
        on = await assess_text("抱抱我嘛", spy_llm, want_intent=True)
        assert "intent" not in off and on["intent"] == "撒娇"
        assert "intent" not in prompts[0] and '"intent"' in prompts[1]
