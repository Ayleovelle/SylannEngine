from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

import experiments.brain_benchmark as benchmark_module
from experiments.brain_benchmark import (
    GIB,
    MIB,
    detect_environment,
    evaluate_gates,
    measure_engine_rss,
    measure_state_resources,
    percentile_summary,
    run_benchmark,
    write_report,
)


def _target_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "samples": 10_000,
        "warmup_samples": 128,
        "assessor": "disabled",
        "backend": "lite",
        "compute_fast_ms": {"p50": 1.0, "p95": 2.0, "p99": 10.0},
        "compute_full_ms": {"p50": 2.0, "p95": 4.0, "p99": 20.0},
        "sqlite_full_ms": {"p50": 2.0, "p95": 5.0, "p99": 10.0},
        "engine_e2e_fast_ms": {"p50": 5.0, "p95": 10.0, "p99": 30.0},
        "engine_e2e_full_ms": {"p50": 8.0, "p95": 15.0, "p99": 40.0},
        "cold_load_ms": {"p50": 1.0, "p95": 2.0, "p99": 3.0},
        "environment": {
            "platform": "test",
            "logical_cpus": 8,
            "affinity_cpus": 2,
            "cpu_quota": 2.0,
            "physical_memory_bytes": 16 * GIB,
            "available_memory_bytes": 8 * GIB,
            "memory_limit_bytes": 2 * GIB,
            "target_verified": False,
        },
        "throughput": {"producers": 2, "operations_per_second": 100.0},
        "queue": {"max_depth": 2, "wait_p99_ms": 1.0},
        "overflow": {"max_hosts": 48, "wait_count": 0},
        "memory": {
            "engine_48_host_rss_bytes": 128 * MIB,
            "b_hot_bytes": 12_000,
            "c_hot_bytes": 48_000,
            "fresh_blob_bytes": 4_000,
            "cold_blob_bytes": 24_000,
        },
    }


def test_percentiles_are_computed_from_all_retained_samples() -> None:
    assert percentile_summary([0.0, 10.0]) == {"p50": 5.0, "p95": 9.5, "p99": 9.9}
    with pytest.raises(ValueError, match="sample"):
        percentile_summary([])
    with pytest.raises(ValueError, match="finite"):
        percentile_summary([1.0, float("nan")])


def test_gate_pass_requires_actual_2c2g_evidence_and_every_budget() -> None:
    report = _target_report()

    gates = evaluate_gates(report)

    assert gates == {"target": "2c2g", "status": "pass", "failures": []}
    assert report["environment"]["target_verified"] is True  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("affinity_cpus", None),
        ("cpu_quota", None),
        ("memory_limit_bytes", None),
        ("memory_limit_bytes", 2 * GIB + 1),
    ],
)
def test_gate_is_unverified_without_complete_target_evidence(field: str, value: object) -> None:
    report = _target_report()
    report["environment"][field] = value  # type: ignore[index]

    gates = evaluate_gates(report)

    assert gates["status"] == "unverified"
    assert report["environment"]["target_verified"] is False  # type: ignore[index]


def test_gate_fails_measured_target_instead_of_hiding_slow_results() -> None:
    report = _target_report()
    report["engine_e2e_full_ms"]["p99"] = 60.001  # type: ignore[index]
    report["memory"]["engine_48_host_rss_bytes"] = 500 * MIB + 1  # type: ignore[index]

    gates = evaluate_gates(report)

    assert gates["status"] == "failed"
    assert gates["failures"] == [
        "engine_e2e_full_ms.p99 exceeds 60ms",
        "memory.engine_48_host_rss_bytes exceeds 500MiB",
    ]


def test_too_few_samples_can_never_pass() -> None:
    report = _target_report()
    report["samples"] = 9_999

    gates = evaluate_gates(report)

    assert gates["status"] == "unverified"
    assert "samples must be at least 10000" in gates["failures"]


def test_environment_report_is_complete_and_nonnegative() -> None:
    environment = detect_environment()

    assert set(environment) == {
        "platform",
        "logical_cpus",
        "affinity_cpus",
        "cpu_quota",
        "physical_memory_bytes",
        "available_memory_bytes",
        "memory_limit_bytes",
        "target_verified",
    }
    assert environment["logical_cpus"] >= 1
    assert environment["physical_memory_bytes"] >= 0
    assert environment["available_memory_bytes"] >= 0


def test_max_horizon_resource_measurement_uses_1000_owned_sessions() -> None:
    measured = measure_state_resources(session_count=1_000, horizon=32)

    assert measured["sessions"] == 1_000
    assert 0 < measured["b_hot_bytes"] < 16 * 1024
    assert 0 < measured["c_hot_bytes"] < 64 * 1024
    assert 0 < measured["fresh_blob_bytes"] <= measured["cold_blob_bytes"] < 32 * 1024
    assert measured["tracemalloc_peak_bytes"] >= measured["tracemalloc_delta_bytes"] > 0


@pytest.mark.asyncio
async def test_full_engine_rss_measurement_populates_48_real_hosts(tmp_path: Path) -> None:
    measured = await measure_engine_rss(tmp_path, host_count=48)

    assert measured["host_count"] == 48
    assert measured["engine_48_host_rss_bytes"] >= 0
    assert measured["max_hosts"] >= 48


@pytest.mark.asyncio
async def test_engine_benchmark_worker_failure_propagates_without_queue_deadlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark_module, "_last_route", lambda _engine, _session: "normal")

    with pytest.raises(RuntimeError, match="requested diagnostic route"):
        await asyncio.wait_for(
            benchmark_module._measure_engine_mode(
                tmp_path,
                route="fast",
                samples=1,
                warmup_samples=0,
                host_count=1,
                producers=1,
            ),
            timeout=2.0,
        )


def test_small_real_benchmark_has_versioned_schema_and_honest_labels(tmp_path: Path) -> None:
    report = run_benchmark(
        samples=4,
        warmup_samples=1,
        host_count=4,
        producers=2,
        data_dir=tmp_path,
    )

    assert report["schema_version"] == 1
    assert report["samples"] == 4
    assert report["assessor"] == "disabled"
    assert report["backend"] == "lite"
    for name in (
        "compute_fast_ms",
        "compute_full_ms",
        "sqlite_full_ms",
        "engine_e2e_fast_ms",
        "engine_e2e_full_ms",
        "cold_load_ms",
    ):
        assert set(report[name]) == {"p50", "p95", "p99"}
        assert all(value >= 0.0 for value in report[name].values())
    assert report["throughput"]["producers"] == 2
    assert report["gates"]["status"] == "unverified"


def test_report_writes_only_to_an_explicit_output_path(tmp_path: Path) -> None:
    report = _target_report()
    output = tmp_path / "nested" / "benchmark.json"

    with pytest.raises(ValueError, match="explicit output"):
        write_report(report, None)
    write_report(report, output)

    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_benchmark_import_does_not_load_optional_numeric_stacks() -> None:
    root = Path(__file__).resolve().parents[1]
    code = (
        f"import sys; sys.path.insert(0, {str(root)!r}); import experiments.brain_benchmark; "
        "assert not any(n == 'torch' or n.startswith('torch.') for n in sys.modules); "
        "assert not any(n == 'numpy' or n.startswith('numpy.') for n in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
