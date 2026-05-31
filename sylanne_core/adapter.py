"""Surface adapter — maps internal kernel output to SPEC-compliant Surface dict."""

from __future__ import annotations

import time
from typing import Any

from .types import Dynamics, Surface

_SCHEMA_VERSION = "sylanne.core.v1"


def to_surface(
    session_id: str,
    host: Any,
    raw: dict[str, Any],
    *,
    diagnostics: bool = False,
) -> Surface:
    kernel = host.kernel
    body = raw.get("body") or kernel.body.to_dict()
    decision = raw.get("decision") or kernel.last_decision or {}
    guard = raw.get("guard") or kernel.last_guard or {}

    return {
        "schema_version": _SCHEMA_VERSION,
        "session_id": session_id,
        "turns": kernel.turns,
        "timestamp": time.time(),
        "state": _map_state(body),  # type: ignore[typeddict-item]
        "personality": _map_personality(kernel),  # type: ignore[typeddict-item]
        "decision": _map_decision(decision),  # type: ignore[typeddict-item]
        "guard": _map_guard(guard),  # type: ignore[typeddict-item]
        "pipeline": _map_pipeline(kernel) if diagnostics else {},
        "dynamics": _map_dynamics(kernel),
        "debug": _map_debug(kernel, raw) if diagnostics else None,
    }


def _map_state(body: dict[str, Any]) -> dict[str, Any]:
    pulse = body.get("pulse", {})
    bloodflow = body.get("bloodflow", {})
    nerve = body.get("nerve", {})
    muscle = body.get("muscle", {})
    temperature = body.get("temperature", {})
    wound = body.get("wound", {})
    immunity = body.get("immunity", {})
    mortality = body.get("mortality", {})
    needs = body.get("needs", {})

    return {
        "rhythm": {
            "beat": pulse.get("beat", 0.0),
            "stability": pulse.get("rhythm", 0.5),
            "strain": pulse.get("strain", 0.0),
        },
        "connection": {
            "warmth": bloodflow.get("warmth", 0.4),
            "circulation": bloodflow.get("circulation", 0.0),
            "memory_flow": bloodflow.get("memory_flow", 0.0),
        },
        "adaptation": {
            "plasticity": nerve.get("plasticity", 0.0),
            "sensitivity": nerve.get("sensitivity", 0.0),
            "repetition": nerve.get("repetition", 0),
            "threshold_drift": nerve.get("threshold_drift", 0.0),
        },
        "responsiveness": {
            "readiness": muscle.get("readiness", 0.2),
            "fatigue": muscle.get("fatigue", 0.0),
            "trained_reach": muscle.get("trained_reach", 0.0),
        },
        "valence": {
            "warmth": temperature.get("warmth", 0.45),
            "volatility": temperature.get("volatility", 0.0),
            "recovery_heat": temperature.get("repair_heat", 0.0),
        },
        "damage": {
            "open": wound.get("open", 0.0),
            "accumulated": wound.get("scar", 0.0),
            "sensitivity": wound.get("sensitivity", 0.0),
            "recovery": wound.get("repair", 0.0),
        },
        "boundary": {
            "pressure": immunity.get("boundary_pressure", 0.0),
            "autonomy": immunity.get("sovereignty", 1.0),
            "interruption_budget": immunity.get("interruption_budget", 1.0),
            "cooldown": immunity.get("cooldown", 0.0),
            "paused": immunity.get("paused", False),
        },
        "capacity": {
            "load": mortality.get("load", 0.0),
            "exhaustion": mortality.get("exhaustion", 0.0),
            "recovery_debt": mortality.get("recovery_debt", 0.0),
        },
        "needs": {
            "expression": needs.get("need_expression", 0.0),
            "quiet": needs.get("need_quiet", 0.0),
            "recovery": needs.get("need_repair", 0.0),
            "contact": needs.get("need_contact", 0.0),
        },
    }


def _map_personality(kernel: Any) -> dict[str, Any]:
    p = kernel.personality or {}
    traits = p.get("traits", p)
    return {
        "schema_version": "sylanne.core.personality.v1",
        "deep": {
            "expression_drive": traits.get("expression_drive_trait", 0.5),
            "perception_acuity": traits.get("perception_acuity", 0.5),
            "boundary_permeability": traits.get("boundary_permeability", 0.5),
            "inner_coherence": traits.get("inner_order", 0.5),
            "relational_gravity": traits.get("relational_gravity", 0.5),
        },
        "surface": {
            "warmth_bias": traits.get("warmth_bias", 0.5),
            "directness": traits.get("edge", 0.5),
            "curiosity": traits.get("curiosity", 0.5),
            "patience": traits.get("patience", 0.5),
            "intimacy_pull": traits.get("intimacy_gravity", 0.5),
            "autonomy_guard": traits.get("sovereignty_guard", 0.5),
        },
    }


_ACTION_MAP = {
    "repair": "recover",
    "reach_out": "reach_out",
    "express": "express",
    "withdraw": "withdraw",
    "explore": "explore",
    "hold": "hold",
    "guard": "guard",
    "wait": "hold",
    "observe": "hold",
}


def _map_decision(d: dict[str, Any]) -> dict[str, Any]:
    action = d.get("action", "hold")
    return {
        "action": _ACTION_MAP.get(action, action),
        "reason": d.get("reason", ""),
        "reason_code": d.get("reason_code", ""),
        "confidence": d.get("confidence", 0.5),
        "urgency": d.get("urgency", 0.0),
    }


def _map_guard(g: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed": g.get("allowed", True),
        "reason": g.get("reason", ""),
        "risk_score": g.get("risk_score", 0.0),
        "constraints": g.get("flags", g.get("constraints", [])),
    }


def _map_pipeline(kernel: Any) -> dict[str, Any]:
    cr = kernel._last_computation_result or {}
    return {
        "L1_encoding": cr.get("L1", {}),
        "L2_gate": cr.get("L2", {}),
        "L3_absence_impact": cr.get("L3", {}),
        "L4_relational": cr.get("L4", {}),
        "L5_fusion": cr.get("L5", {}),
        "L6_boundary": cr.get("L6", {}),
        "L7_expression": cr.get("L7", {}),
    }


def _map_dynamics(kernel: Any) -> Dynamics:
    body = kernel.body.to_dict()
    needs = body.get("needs", {})
    moral = kernel.moral_repair or {}
    fallibility = kernel.fallibility or {}
    rt = kernel.relational_time or {}

    return {
        "affect": {
            "recovery_drive": needs.get("need_repair", 0.0),
            "expression_drive": needs.get("need_expression", 0.0),
            "quiet_drive": needs.get("need_quiet", 0.0),
        },
        "moral_state": {
            "state": moral.get("state", "stable"),
            "events": moral.get("events", 0),
        },
        "uncertainty": {
            "claim_caution": fallibility.get("claim_caution", 0.0),
            "events": fallibility.get("events", 0),
        },
        "relational_time": {
            "interval_seconds": rt.get("interval_seconds", 0.0),
            "total_duration": rt.get("total_duration", 0.0),
            "phase": rt.get("phase", "active"),
        },
    }


def _map_debug(kernel: Any, raw: dict[str, Any]) -> dict[str, Any]:
    spine = kernel.computation
    breakers = {}
    if hasattr(spine, "_circuit_breakers"):
        for name, cb in spine._circuit_breakers.items():
            breakers[name] = {
                "open": cb.is_open(),
                "failures": cb._failures,
            }

    timing = {}
    if hasattr(spine, "_timings"):
        for name, deq in spine._timings.items():
            if deq:
                avg_ms = sum(deq) / len(deq) / 1_000_000
                timing[name] = round(avg_ms, 2)

    return {
        "healthy": not any(b["open"] for b in breakers.values()),
        "circuit_breakers": breakers,
        "layer_avg_ms": timing,
        "computation_cache_size": len(spine._result_cache)
        if hasattr(spine, "_result_cache")
        else 0,
        "kernel_schema_version": raw.get("schema_version", "unknown"),
    }
