"""simulate_corpus.py — headless field-driven corpus for the NTAP ROI spike (pre-P0 gate).

Drives the REAL resonance field (ScarredState / VoidScarEngine / ResonanceSpine) headless over a
synthetic message -> assessor -> field pipeline, logging one row per tick. This is the data
generator for the pre-P0 anti-theater spike (and the reusable skeleton for the Tier-1 generator).

Pipeline per session (models the real path: message -> assessor a_* -> field base):

    latent mood m_t  (AR(1) + occasional regime switch)
      -> synthetic assessor a_* = f(m_t) + noise        # stands in for the remote LLM assessor
      -> message text that encodes m_t                  # so the message HDC actually carries m_t
      -> ResonanceSpine.process(text, ts, a_*)          # the REAL field consumes a_*, evolves base

Logged per tick: a_t (4), prior base z_{t-1} (8), base_pre_nudge (8, via monkey-patch), post base
z_t (8), scar-mod sensitivity (8), surprise, HDC density features at two widths (8 = "compressed",
64 = "full"), dt, and the latent mood (diagnostic only — NEVER fed to the models).

HONESTY NOTE: synthetic data tests the MECHANISM only — (a) can a learned recurrent core beat the
field's OWN fixed recurrent memory at predicting next-tick affect, and (b) can an injected message
latent survive the HDC density bottleneck. It does NOT test real assessor semantics; that needs real
labelled traffic. The robust headline of the spike is the memory increment, not the HDC ablation.
"""

from __future__ import annotations

import argparse
import os
import sys

# `python training/student_core/simulate_corpus.py` puts the SCRIPT dir at sys.path[0], which
# can shadow imports and load a different copy of a dependency. Force the repo root ahead of it
# BEFORE importing sylanne_core, so this runs identically as a script and as an imported module.
if sys.path and os.path.basename(sys.path[0]) == "student_core":
    sys.path[0] = os.getcwd()

import numpy as np
import pandas as pd

from sylanne_core.compute.hdc import HDCEncoder
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.config import build_profile

EMO = 8
N_MOOD_BINS = 8
PERSONALITY = {
    "extraversion": 0.5,
    "neuroticism": 0.5,
    "openness": 0.5,
    "conscientiousness": 0.5,
    "agreeableness": 0.5,
}
# Distinct token sets per mood bin so the message HDC carries the latent mood.
MOOD_WORDS = {b: [f"mood{b}tok{i}" for i in range(4)] for b in range(N_MOOD_BINS)}


def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


class _CaptureSpine(ResonanceSpine):
    """ResonanceSpine subclass that snapshots base_pre_nudge each tick.

    base_pre_nudge = scar_state.base right AFTER _evolve_base but BEFORE the assessment nudge.
    The base class uses __slots__ (instance attrs are read-only), so we cannot monkey-patch an
    instance; subclassing gives a __dict__ and a clean override point. We snapshot on entry to
    _apply_assessment_to_engine, then defer to the real implementation.
    """

    def _apply_assessment_to_engine(self, assessment: dict) -> None:
        # Snapshot base AFTER _evolve_base but BEFORE the assessment nudge.
        self.base_pre_nudge = list(self._engine.scar_state.base)
        super()._apply_assessment_to_engine(assessment)


def make_spine() -> _CaptureSpine:
    """Build a fresh headless capture-spine for one session."""
    spine = _CaptureSpine(build_profile("lite"))
    spine.apply_personality(PERSONALITY)
    spine.base_pre_nudge = list(spine._engine.scar_state.base)
    return spine


def density_features(h: bytearray, width: int) -> np.ndarray:
    """Per-chunk bit density of the packed HDC hypervector, mapped to ~[-1, 1]."""
    bits = np.unpackbits(np.frombuffer(bytes(h), dtype=np.uint8))
    chunks = np.array_split(bits, width)
    return np.array([c.mean() * 2.0 - 1.0 for c in chunks], dtype=np.float64)


def gen_moods(rng: np.random.Generator, length: int, rho: float) -> list[float]:
    """AR(1) latent mood in [-1, 1] with a small per-tick regime-switch probability."""
    m = float(rng.uniform(-1.0, 1.0))
    out = []
    drive = (max(1e-6, 1.0 - rho * rho)) ** 0.5
    for _ in range(length):
        if rng.random() < 0.05:
            m = float(rng.uniform(-1.0, 1.0))
        else:
            m = _clip(rho * m + drive * float(rng.normal(0.0, 0.5)), -1.0, 1.0)
        out.append(m)
    return out


def synth_assessor(m: float, rng: np.random.Generator) -> dict[str, float]:
    """Synthetic assessor: a_* derived from the latent mood (+ noise). Stands in for the LLM."""
    return {
        "valence": _clip(m + float(rng.normal(0.0, 0.1)), -1.0, 1.0),
        "arousal": _clip(0.5 + 0.4 * abs(m) + float(rng.normal(0.0, 0.1)), 0.0, 1.0),
        "wound_risk": _clip(max(0.0, -m) * 0.7 + float(rng.normal(0.0, 0.05)), 0.0, 1.0),
        "confidence": _clip(0.75 + float(rng.normal(0.0, 0.1)), 0.0, 1.0),
    }


def mood_message(m: float, rng: np.random.Generator) -> str:
    """A message whose tokens encode the mood bin (so its HDC carries m), plus random filler."""
    b = int(round((m + 1.0) / 2.0 * (N_MOOD_BINS - 1)))
    toks = list(rng.choice(MOOD_WORDS[b], size=2, replace=True))
    filler = [f"flr{int(rng.integers(0, 64))}" for _ in range(3)]
    return " ".join(toks + filler)


def run(n_sessions: int, len_lo: int, len_hi: int, iid_frac: float, seed: int, out_path: str) -> None:
    rng = np.random.default_rng(seed)
    enc = HDCEncoder(build_profile("lite").hdc_dim)
    n_iid = int(n_sessions * iid_frac)
    rows: list[dict] = []

    for s in range(n_sessions):
        rho = 0.0 if s >= (n_sessions - n_iid) else 0.85  # last iid_frac sessions are near-iid controls
        is_iid = rho == 0.0
        length = int(rng.integers(len_lo, len_hi + 1))
        moods = gen_moods(rng, length, rho)
        spine = make_spine()
        ts = 1_000_000.0 + float(rng.uniform(0, 1e5))

        for t, m in enumerate(moods):
            a = synth_assessor(m, rng)
            msg = mood_message(m, rng)
            z_prev = list(spine._engine.scar_state.base)
            scar_mod = [float(spine._engine.scar_state.modifier(d)) for d in range(EMO)]
            h = enc.encode_text(msg)
            hdc8 = density_features(h, 8)
            hdc64 = density_features(h, 64)
            ts += float(rng.uniform(30.0, 600.0))
            result = spine.process(msg, timestamp=ts, assessment=a)
            z_post = list(spine._engine.scar_state.base)
            base_pre = list(spine.base_pre_nudge)
            surprise = float(result.get("surprise", 0.0) or 0.0)

            rows.append(
                {
                    "session": s,
                    "is_iid": is_iid,
                    "tick": t,
                    "ts": ts,
                    "mood": m,  # diagnostic ONLY — never a model input
                    "a_valence": a["valence"],
                    "a_arousal": a["arousal"],
                    "a_wound_risk": a["wound_risk"],
                    "a_confidence": a["confidence"],
                    "surprise": surprise,
                    "z_prev": [float(x) for x in z_prev],
                    "base_pre_nudge": [float(x) for x in base_pre],
                    "z_post": [float(x) for x in z_post],
                    "scar_mod": scar_mod,
                    "hdc8": [float(x) for x in hdc8],
                    "hdc64": [float(x) for x in hdc64],
                }
            )

    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    print(
        f"wrote {len(df)} ticks from {n_sessions} sessions "
        f"({n_iid} near-iid controls) -> {out_path}"
    )
    print(
        "  a_valence[min/mean/max] = "
        f"{df.a_valence.min():.3f}/{df.a_valence.mean():.3f}/{df.a_valence.max():.3f}; "
        f"mean session len = {len(df) / n_sessions:.1f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=int, default=2000)
    ap.add_argument("--len-lo", type=int, default=16)
    ap.add_argument("--len-hi", type=int, default=48)
    ap.add_argument("--iid-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default="training/student_core/spike_corpus.parquet")
    args = ap.parse_args()
    run(args.sessions, args.len_lo, args.len_hi, args.iid_frac, args.seed, args.out)


if __name__ == "__main__":
    main()
