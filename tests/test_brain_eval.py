from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from experiments.brain_eval import (
    ADAPTER_NAMES,
    CORPUS_SCHEMA_VERSION,
    FIXED_SPLIT_SEEDS,
    NumericRecord,
    adapter_registry,
    bootstrap_ci,
    evaluate_corpus,
    load_corpus,
    paired_session_differences,
    promotion_decision,
    run_evaluation,
    session_block_splits,
    synthetic_sanity,
    write_report,
)

ZERO8 = (0.0,) * 8


def _record(session: str, tick: int, *, target: float = 0.0) -> NumericRecord:
    return NumericRecord(
        schema_version=CORPUS_SCHEMA_VERSION,
        session_id=session,
        tick_id=tick,
        features=(target / 2.0,) + ZERO8[1:],
        target=(target,) + ZERO8[1:],
        feedback_target_tick=max(0, tick - 1),
        feedback_value=max(-1.0, min(1.0, target)),
    )


def test_versioned_jsonl_loader_accepts_only_finite_numeric_records(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    document = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "session_id": "s1",
        "tick_id": 1,
        "features": [0.0] * 8,
        "target": [0.25] * 8,
        "feedback_target_tick": 0,
        "feedback_value": 0.5,
    }
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")

    assert load_corpus(path) == [
        NumericRecord(
            schema_version=CORPUS_SCHEMA_VERSION,
            session_id="s1",
            tick_id=1,
            features=ZERO8,
            target=(0.25,) * 8,
            feedback_target_tick=0,
            feedback_value=0.5,
        )
    ]

    document["target"][0] = math.nan
    path.write_text(json.dumps(document, allow_nan=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite"):
        load_corpus(path)


def test_loader_rejects_unknown_version_duplicate_tick_and_tick_splits(tmp_path: Path) -> None:
    base = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "session_id": "s1",
        "tick_id": 1,
        "features": [0.0] * 8,
        "target": [0.0] * 8,
        "feedback_target_tick": 0,
        "feedback_value": 0.0,
    }
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join((json.dumps(base), json.dumps(base))) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_corpus(path)

    base["schema_version"] = CORPUS_SCHEMA_VERSION + 1
    path.write_text(json.dumps(base) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_corpus(path)


def test_session_block_splits_are_deterministic_disjoint_and_use_five_seeds() -> None:
    records = [_record(f"s{session}", tick) for session in range(10) for tick in range(1, 4)]

    first = session_block_splits(records)
    second = session_block_splits(list(reversed(records)))

    assert first == second
    assert tuple(split.seed for split in first) == FIXED_SPLIT_SEEDS
    for split in first:
        assert set(split.train_sessions).isdisjoint(split.test_sessions)
        assert set(split.train_sessions) | set(split.test_sessions) == {
            f"s{session}" for session in range(10)
        }


def test_paired_session_differences_require_the_same_sessions() -> None:
    assert paired_session_differences(
        {"a": 0.4, "b": 0.3},
        {"a": 0.1, "b": 0.35},
    ) == pytest.approx((0.3, -0.05))
    with pytest.raises(ValueError, match="same sessions"):
        paired_session_differences({"a": 0.4}, {"b": 0.1})


def test_bootstrap_ci_is_seeded_and_uses_requested_10000_resamples() -> None:
    first = bootstrap_ci((0.1, 0.1, 0.1), resamples=10_000, seed=2718)
    second = bootstrap_ci((0.1, 0.1, 0.1), resamples=10_000, seed=2718)

    assert first == second == pytest.approx((0.1, 0.1))
    with pytest.raises(ValueError, match="resamples"):
        bootstrap_ci((0.1,), resamples=9_999, seed=2718)


@pytest.mark.parametrize(
    ("baseline", "candidate", "ci", "expected"),
    [
        (0.40, 0.35, (0.03, 0.07), "pass"),
        (0.40, 0.37, (0.019, 0.04), "refused"),
        (0.40, 0.37, (0.0201, 0.04), "pass"),
        (0.20, 0.17, (0.0101, 0.04), "refused"),
    ],
)
def test_promotion_requires_both_absolute_and_relative_lower_bounds(
    baseline: float,
    candidate: float,
    ci: tuple[float, float],
    expected: str,
) -> None:
    decision = promotion_decision(
        baseline_mae=baseline,
        candidate_mae=candidate,
        improvement_ci=ci,
        sessions=30,
        target_ticks=1_000,
    )

    assert decision["status"] == expected


def test_minimum_real_corpus_gate_refuses_metrics_and_promotion() -> None:
    too_few_sessions = [_record(f"s{i}", tick) for i in range(29) for tick in range(1, 36)]
    too_few_ticks = [_record(f"s{i}", tick) for i in range(30) for tick in range(1, 34)]

    for records in (too_few_sessions, too_few_ticks):
        report = evaluate_corpus(records, tuning_budget=2, bootstrap_resamples=10_000)
        assert report["status"] == "insufficient_data"
        assert report["models"] == {}
        assert report["promotion"]["status"] == "refused"


def test_adapter_registry_has_every_required_ablation_with_equal_budget() -> None:
    registry = adapter_registry(tuning_budget=2)

    assert tuple(registry) == ADAPTER_NAMES
    assert set(ADAPTER_NAMES) == {
        "current_v26",
        "ema_arx",
        "pel",
        "b_only",
        "b_plus_c",
        "feedback_shuffled",
        "eligibility_disabled",
        "matched_compute_continuous",
    }
    assert {model["tuning_budget"] for model in registry.values()} == {2}
    assert {len(model["candidate_parameters"]) for model in registry.values()} == {2}


def test_synthetic_target_advantage_beats_within_session_shuffle() -> None:
    first = synthetic_sanity(seed=42)
    second = synthetic_sanity(seed=42)

    assert first == second
    assert first["status"] == "pass"
    assert first["target_mae"] + 0.02 < first["shuffled_mae"]
    assert first["shuffle_scope"] == "within_session"


def test_synthetic_cli_report_never_claims_real_corpus_promotion(tmp_path: Path) -> None:
    output = tmp_path / "synthetic.json"

    report = run_evaluation(corpus_path=None, synthetic=True, tuning_budget=2)
    write_report(report, output)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    assert loaded["synthetic_sanity"]["status"] == "pass"
    assert loaded["real_corpus"]["status"] == "insufficient_data"
    assert loaded["promotion"]["status"] == "refused"


def test_evaluation_report_requires_an_explicit_output_path() -> None:
    with pytest.raises(ValueError, match="explicit output"):
        write_report({"schema_version": 1}, None)
