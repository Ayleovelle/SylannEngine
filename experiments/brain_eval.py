"""Deterministic offline evaluation for the v26 brain-compute path.

The harness consumes opt-in numeric JSONL only. It never reads dialogue text and
never substitutes synthetic measurements for a real-corpus promotion result.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Iterable, Mapping, Sequence

CORPUS_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
N_AXES = 8
MIN_SESSIONS = 30
MIN_TARGET_TICKS = 1_000
DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
FIXED_SPLIT_SEEDS = (2718, 31415, 16180, 57721, 14142)
ADAPTER_NAMES = (
    "current_v26",
    "ema_arx",
    "pel",
    "b_only",
    "b_plus_c",
    "feedback_shuffled",
    "eligibility_disabled",
    "matched_compute_continuous",
)
_CORPUS_FIELDS = frozenset(
    {
        "schema_version",
        "session_id",
        "tick_id",
        "features",
        "target",
        "feedback_target_tick",
        "feedback_value",
    }
)
_ZERO8 = (0.0,) * N_AXES


@dataclass(frozen=True, slots=True)
class NumericRecord:
    schema_version: int
    session_id: str
    tick_id: int
    features: tuple[float, ...]
    target: tuple[float, ...]
    feedback_target_tick: int
    feedback_value: float

    def __post_init__(self) -> None:
        if self.schema_version != CORPUS_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {CORPUS_SCHEMA_VERSION}")
        _identifier(self.session_id)
        _positive_int("tick_id", self.tick_id)
        _axes("features", self.features)
        _axes("target", self.target)
        if (
            isinstance(self.feedback_target_tick, bool)
            or not isinstance(self.feedback_target_tick, int)
            or not 0 <= self.feedback_target_tick <= self.tick_id
        ):
            raise ValueError("feedback_target_tick must be an integer in [0,tick_id]")
        _bounded_float("feedback_value", self.feedback_value)


@dataclass(frozen=True, slots=True)
class SessionSplit:
    seed: int
    train_sessions: tuple[str, ...]
    test_sessions: tuple[str, ...]


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise ValueError("session_id must be nonempty UTF-8 capped at 256 bytes")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("session_id must not contain control characters")
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bounded_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    if not -1.0 <= converted <= 1.0:
        raise ValueError(f"{name} must be in [-1,1]")
    return converted


def _axes(name: str, values: object) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) != N_AXES:
        raise ValueError(f"{name} must contain exactly {N_AXES} numeric axes")
    return tuple(_bounded_float(f"{name}[{index}]", value) for index, value in enumerate(values))


def _json_constant(value: str) -> None:
    raise ValueError(f"JSON numeric value {value} must be finite")


def _record_from_document(document: object, *, line_number: int) -> NumericRecord:
    if not isinstance(document, dict) or set(document) != _CORPUS_FIELDS:
        raise ValueError(f"line {line_number}: record fields do not match schema v1")
    version = document["schema_version"]
    tick = document["tick_id"]
    feedback_tick = document["feedback_target_tick"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"line {line_number}: schema_version must be an integer")
    return NumericRecord(
        schema_version=version,
        session_id=_identifier(document["session_id"]),
        tick_id=_positive_int("tick_id", tick),
        features=_axes("features", document["features"]),
        target=_axes("target", document["target"]),
        feedback_target_tick=(
            feedback_tick
            if isinstance(feedback_tick, int) and not isinstance(feedback_tick, bool)
            else -1
        ),
        feedback_value=_bounded_float("feedback_value", document["feedback_value"]),
    )


def load_corpus(path: str | Path) -> list[NumericRecord]:
    corpus_path = Path(path)
    records: list[NumericRecord] = []
    seen: set[tuple[str, int]] = set()
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                document = json.loads(raw_line, parse_constant=_json_constant)
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"line {line_number}: invalid finite JSON: {error}") from error
            record = _record_from_document(document, line_number=line_number)
            key = (record.session_id, record.tick_id)
            if key in seen:
                raise ValueError(f"line {line_number}: duplicate session/tick")
            seen.add(key)
            records.append(record)
    return sorted(records, key=lambda item: (item.session_id, item.tick_id))


def session_block_splits(
    records: Sequence[NumericRecord] | Iterable[NumericRecord],
    *,
    seeds: Sequence[int] = FIXED_SPLIT_SEEDS,
    test_fraction: float = 0.2,
) -> tuple[SessionSplit, ...]:
    materialized = tuple(records)
    sessions = sorted({record.session_id for record in materialized})
    if len(sessions) < 2:
        raise ValueError("session-blocked splitting requires at least two sessions")
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be in (0,1)")
    test_count = max(1, min(len(sessions) - 1, round(len(sessions) * test_fraction)))
    splits: list[SessionSplit] = []
    for seed in seeds:
        shuffled = list(sessions)
        random.Random(seed).shuffle(shuffled)
        test = tuple(sorted(shuffled[:test_count]))
        train = tuple(sorted(shuffled[test_count:]))
        splits.append(SessionSplit(seed=int(seed), train_sessions=train, test_sessions=test))
    return tuple(splits)


def paired_session_differences(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
) -> tuple[float, ...]:
    if set(baseline) != set(candidate):
        raise ValueError("paired MAE requires the same sessions")
    return tuple(float(baseline[key]) - float(candidate[key]) for key in sorted(baseline))


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires values")
    rank = (len(ordered) - 1) * quantile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def bootstrap_ci(
    differences: Sequence[float] | Iterable[float],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = 2718,
) -> tuple[float, float]:
    values = tuple(float(value) for value in differences)
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("bootstrap differences must be nonempty and finite")
    if resamples < DEFAULT_BOOTSTRAP_RESAMPLES:
        raise ValueError("resamples must be at least 10000")
    generator = random.Random(seed)
    size = len(values)
    means = [
        fmean(values[generator.randrange(size)] for _ in range(size)) for _ in range(resamples)
    ]
    return (_percentile(means, 0.025), _percentile(means, 0.975))


def promotion_decision(
    *,
    baseline_mae: float,
    candidate_mae: float,
    improvement_ci: tuple[float, float],
    sessions: int,
    target_ticks: int,
) -> dict[str, object]:
    if sessions < MIN_SESSIONS or target_ticks < MIN_TARGET_TICKS:
        return {
            "status": "refused",
            "reason": "insufficient_data",
            "absolute_lower_bound": None,
            "relative_lower_bound": None,
        }
    values = (baseline_mae, candidate_mae, *improvement_ci)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        return {
            "status": "refused",
            "reason": "invalid_metrics",
            "absolute_lower_bound": None,
            "relative_lower_bound": None,
        }
    lower = improvement_ci[0]
    relative = lower / baseline_mae if baseline_mae > 0.0 else 0.0
    passed = candidate_mae < baseline_mae and lower > 0.02 and relative > 0.05
    return {
        "status": "pass" if passed else "refused",
        "reason": "thresholds_met" if passed else "promotion_threshold_not_met",
        "absolute_lower_bound": lower,
        "relative_lower_bound": relative,
    }


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _surprise(features: Sequence[float], previous: Sequence[float]) -> float:
    return min(1.0, fmean(abs(features[index] - previous[index]) for index in range(N_AXES)))


def _group_records(records: Iterable[NumericRecord]) -> dict[str, list[NumericRecord]]:
    grouped: dict[str, list[NumericRecord]] = defaultdict(list)
    for record in records:
        grouped[record.session_id].append(record)
    for session_records in grouped.values():
        session_records.sort(key=lambda item: item.tick_id)
    return dict(grouped)


def _shuffled_feedback(records: Sequence[NumericRecord], seed: int) -> list[float]:
    values = [record.feedback_value for record in records]
    random.Random(seed).shuffle(values)
    if len(values) > 1 and values == [record.feedback_value for record in records]:
        values = values[1:] + values[:1]
    return values


def _predict_session(
    records: Sequence[NumericRecord],
    *,
    model_name: str,
    parameter: float,
    seed: int,
) -> list[tuple[float, ...]]:
    predictions: list[tuple[float, ...]] = []
    previous = [0.0] * N_AXES
    previous_features = [0.0] * N_AXES
    continuous = [0.0] * N_AXES
    shuffled = _shuffled_feedback(records, seed)
    pel = None
    brain = None
    c_state = None

    if model_name == "pel":
        from sylanne_core.compute.pel_core import PELCore

        pel = PELCore.from_personality({})
    if model_name in {"b_only", "b_plus_c", "feedback_shuffled", "eligibility_disabled"}:
        from sylanne_core.compute.brain_compute import BrainComputeCore

        lineage = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sylanne-eval:{records[0].session_id}"))
        brain = BrainComputeCore.fresh(lineage_id=lineage, feedback_horizon=32)
        if model_name != "b_only":
            from sylanne_core.compute.brain_c_lite import CLiteState

            c_state = CLiteState.fresh(feedback_horizon=32)

    for index, record in enumerate(records):
        feedback = record.feedback_value
        if model_name == "feedback_shuffled":
            feedback = shuffled[index]
        elif model_name in {"b_only", "eligibility_disabled"}:
            feedback = 0.0

        if model_name == "current_v26":
            predicted = tuple(record.features)
        elif model_name == "ema_arx":
            alpha = 0.1 + 0.8 * parameter
            trend = 0.25 * parameter
            predicted = tuple(
                _clip(
                    alpha * record.features[axis]
                    + (1.0 - alpha) * previous[axis]
                    + trend * (record.features[axis] - previous_features[axis])
                )
                for axis in range(N_AXES)
            )
        elif model_name == "pel":
            assert pel is not None
            output, _free_energy = pel.step(
                list(record.features),
                _surprise(record.features, previous),
                a_vec=list(record.features),
                confidence=parameter,
            )
            predicted = tuple(_clip(value) for value in output)
        elif model_name in {
            "b_only",
            "b_plus_c",
            "feedback_shuffled",
            "eligibility_disabled",
        }:
            from sylanne_core.compute.brain_compute import BrainEvent
            from sylanne_core.compute.brain_state import EventAllocation

            assert brain is not None
            state = brain.state
            appraisal = tuple(
                _clip(record.features[axis] + (0.2 * parameter * feedback if axis == 0 else 0.0))
                for axis in range(N_AXES)
            )
            proposal = _ZERO8
            if c_state is not None:
                from sylanne_core.compute.brain_c_lite import evolve_c_event

                c_candidate = evolve_c_event(
                    c_state,
                    appraisal,
                    route="full",
                    tick_id=state.tick_id + 1,
                    created_at=float(state.tick_id + 1),
                    delta_t=1.0,
                )
                c_state = c_candidate.state
                proposal = c_candidate.proposal
            event = BrainEvent(
                event_id=f"{record.session_id}:{record.tick_id}",
                assessment=appraisal,
                hdc=appraisal,
                wound_sum=_ZERO8,
                surprise=_surprise(appraisal, state.e),
                perception_acuity=1.0,
                proposal_c=proposal,
            )
            allocation = EventAllocation(
                generation=state.generation,
                lineage_id=state.lineage_id,
                tick_id=state.tick_id + 1,
                history_epoch=state.history_epoch + 1,
                mutation_seq=state.mutation_seq + 1,
            )
            candidate = brain.prepare_event(
                event,
                allocation=allocation,
                trusted_now=float(state.tick_id + 1),
                alpha_c=(0.0 if model_name == "b_only" else min(0.1, 0.1 * parameter)),
            )
            committed = brain.commit(candidate)
            predicted = tuple(committed.e)
        elif model_name == "matched_compute_continuous":
            drive = [
                _clip(record.features[axis] + (0.2 * parameter * feedback if axis == 0 else 0.0))
                for axis in range(N_AXES)
            ]
            for _ in range(4):
                continuous = [
                    _clip(0.75 * continuous[axis] + 0.25 * drive[axis]) for axis in range(N_AXES)
                ]
            predicted = tuple(continuous)
        else:
            raise ValueError(f"unknown evaluator adapter {model_name!r}")

        predictions.append(predicted)
        previous = list(predicted)
        previous_features = list(record.features)
    return predictions


def _session_mae(
    grouped: Mapping[str, Sequence[NumericRecord]],
    *,
    model_name: str,
    parameter: float,
    seed: int,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for session_id in sorted(grouped):
        records = grouped[session_id]
        predictions = _predict_session(
            records,
            model_name=model_name,
            parameter=parameter,
            seed=seed,
        )
        errors = [
            abs(prediction[axis] - record.target[axis])
            for record, prediction in zip(records, predictions, strict=True)
            for axis in range(N_AXES)
        ]
        result[session_id] = fmean(errors)
    return result


def _candidate_parameters(budget: int) -> tuple[float, ...]:
    _positive_int("tuning_budget", budget)
    return tuple((index + 1) / (budget + 1) for index in range(budget))


def adapter_registry(*, tuning_budget: int) -> dict[str, dict[str, object]]:
    """Describe every preregistered adapter without executing an evaluation."""
    candidates = list(_candidate_parameters(tuning_budget))
    actual_core = {"pel", "b_only", "b_plus_c", "feedback_shuffled", "eligibility_disabled"}
    return {
        name: {
            "tuning_budget": tuning_budget,
            "candidate_parameters": list(candidates),
            "adapter_kind": "repository_core" if name in actual_core else "offline_numeric",
        }
        for name in ADAPTER_NAMES
    }


def _best_parameter(
    records: Sequence[NumericRecord],
    sessions: Sequence[str],
    *,
    model_name: str,
    budget: int,
    seed: int,
) -> float:
    selected = set(sessions)
    grouped = _group_records(record for record in records if record.session_id in selected)
    ranked: list[tuple[float, float]] = []
    for parameter in _candidate_parameters(budget):
        scores = _session_mae(grouped, model_name=model_name, parameter=parameter, seed=seed)
        ranked.append((fmean(scores.values()), parameter))
    return min(ranked)[1]


def evaluate_corpus(
    records: Sequence[NumericRecord] | Iterable[NumericRecord],
    *,
    tuning_budget: int = 8,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
) -> dict[str, object]:
    materialized = sorted(tuple(records), key=lambda item: (item.session_id, item.tick_id))
    session_count = len({record.session_id for record in materialized})
    target_ticks = len(materialized)
    if session_count < MIN_SESSIONS or target_ticks < MIN_TARGET_TICKS:
        return {
            "status": "insufficient_data",
            "sessions": session_count,
            "target_ticks": target_ticks,
            "minimum_sessions": MIN_SESSIONS,
            "minimum_target_ticks": MIN_TARGET_TICKS,
            "models": {},
            "promotion": {
                "status": "refused",
                "reason": "insufficient_data",
                "absolute_lower_bound": None,
                "relative_lower_bound": None,
            },
        }

    splits = session_block_splits(materialized)
    per_model_observations: dict[str, dict[str, list[float]]] = {
        name: defaultdict(list) for name in ADAPTER_NAMES
    }
    chosen_parameters: dict[str, list[float]] = {name: [] for name in ADAPTER_NAMES}
    for split in splits:
        test_set = set(split.test_sessions)
        test_grouped = _group_records(
            record for record in materialized if record.session_id in test_set
        )
        for name in ADAPTER_NAMES:
            parameter = _best_parameter(
                materialized,
                split.train_sessions,
                model_name=name,
                budget=tuning_budget,
                seed=split.seed,
            )
            chosen_parameters[name].append(parameter)
            scores = _session_mae(
                test_grouped,
                model_name=name,
                parameter=parameter,
                seed=split.seed,
            )
            for session_id, score in scores.items():
                per_model_observations[name][session_id].append(score)

    models: dict[str, dict[str, object]] = {}
    averaged: dict[str, dict[str, float]] = {}
    registry = adapter_registry(tuning_budget=tuning_budget)
    for name in ADAPTER_NAMES:
        session_scores = {
            session_id: fmean(values)
            for session_id, values in sorted(per_model_observations[name].items())
        }
        averaged[name] = session_scores
        models[name] = {
            "mae": fmean(session_scores.values()),
            "per_session_mae": session_scores,
            "tuning_budget": tuning_budget,
            "selected_parameters": chosen_parameters[name],
            "adapter_kind": registry[name]["adapter_kind"],
        }

    continuous_names = (
        "current_v26",
        "ema_arx",
        "pel",
        "b_only",
        "matched_compute_continuous",
    )
    strongest = min(continuous_names, key=lambda name: float(models[name]["mae"]))
    differences = paired_session_differences(averaged[strongest], averaged["b_plus_c"])
    interval = bootstrap_ci(
        differences,
        resamples=bootstrap_resamples,
        seed=FIXED_SPLIT_SEEDS[0],
    )
    decision = promotion_decision(
        baseline_mae=float(models[strongest]["mae"]),
        candidate_mae=float(models["b_plus_c"]["mae"]),
        improvement_ci=interval,
        sessions=session_count,
        target_ticks=target_ticks,
    )
    decision.update(
        {
            "baseline": strongest,
            "candidate": "b_plus_c",
            "improvement_ci95": list(interval),
        }
    )
    return {
        "status": "evaluated",
        "sessions": session_count,
        "target_ticks": target_ticks,
        "split_seeds": list(FIXED_SPLIT_SEEDS),
        "split_unit": "session",
        "tuning_scope": "training_sessions_only",
        "models": models,
        "promotion": decision,
    }


def synthetic_corpus(
    *,
    session_count: int = MIN_SESSIONS,
    ticks_per_session: int = 34,
    seed: int = 2718,
) -> list[NumericRecord]:
    _positive_int("session_count", session_count)
    _positive_int("ticks_per_session", ticks_per_session)
    generator = random.Random(seed)
    records: list[NumericRecord] = []
    for session in range(session_count):
        previous = [0.0] * N_AXES
        for tick in range(1, ticks_per_session + 1):
            feedback = generator.uniform(-0.9, 0.9)
            features = tuple(
                _clip(0.8 * previous[axis] + generator.uniform(-0.05, 0.05))
                for axis in range(N_AXES)
            )
            target = tuple(
                _clip(0.65 * features[axis] + 0.35 * feedback * (1.0 if axis % 2 == 0 else -1.0))
                for axis in range(N_AXES)
            )
            records.append(
                NumericRecord(
                    schema_version=CORPUS_SCHEMA_VERSION,
                    session_id=f"synthetic-{session:03d}",
                    tick_id=tick,
                    features=features,
                    target=target,
                    feedback_target_tick=tick - 1,
                    feedback_value=feedback,
                )
            )
            previous = list(target)
    return records


def synthetic_sanity(*, seed: int = 2718) -> dict[str, object]:
    records = synthetic_corpus(session_count=30, ticks_per_session=34, seed=seed)
    grouped = _group_records(records)
    target_errors: list[float] = []
    shuffled_errors: list[float] = []
    for index, session_id in enumerate(sorted(grouped)):
        session_records = grouped[session_id]
        shuffled = _shuffled_feedback(session_records, seed + index)
        for record, shuffled_value in zip(session_records, shuffled, strict=True):
            target_errors.append(abs(record.feedback_value - record.feedback_value))
            shuffled_errors.append(abs(shuffled_value - record.feedback_value))
    target_mae = fmean(target_errors)
    shuffled_mae = fmean(shuffled_errors)
    advantage = shuffled_mae - target_mae
    return {
        "status": "pass" if advantage > 0.02 else "failed",
        "target_mae": target_mae,
        "shuffled_mae": shuffled_mae,
        "absolute_advantage": advantage,
        "shuffle_scope": "within_session",
        "sessions": len(grouped),
        "target_ticks": len(records),
        "seed": seed,
    }


def run_evaluation(
    *,
    corpus_path: str | Path | None,
    synthetic: bool,
    tuning_budget: int = 8,
) -> dict[str, object]:
    if corpus_path is None:
        real: dict[str, object] = {
            "status": "insufficient_data",
            "sessions": 0,
            "target_ticks": 0,
            "models": {},
            "promotion": {"status": "refused", "reason": "insufficient_data"},
        }
    else:
        real = evaluate_corpus(load_corpus(corpus_path), tuning_budget=tuning_budget)
    sanity: dict[str, object] | None = synthetic_sanity() if synthetic else None
    promotion = dict(real.get("promotion", {"status": "refused", "reason": "no_evaluation"}))
    if sanity is not None and sanity["status"] != "pass":
        promotion = {"status": "refused", "reason": "synthetic_sanity_failed"}
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "corpus_schema_version": CORPUS_SCHEMA_VERSION,
        "synthetic_sanity": sanity,
        "real_corpus": real,
        "promotion": promotion,
    }


def write_report(report: Mapping[str, object], output_path: str | Path | None) -> None:
    if output_path is None:
        raise ValueError("an explicit output path is required")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        dict(report),
        ensure_ascii=True,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.write("\n")
        handle.flush()
    temporary.replace(target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--synthetic-sanity", action="store_true")
    parser.add_argument("--tuning-budget", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_evaluation(
        corpus_path=arguments.corpus,
        synthetic=arguments.synthetic_sanity,
        tuning_budget=arguments.tuning_budget,
    )
    write_report(report, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
