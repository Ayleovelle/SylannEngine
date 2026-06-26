"""spike_ntap.py — pre-P0 anti-theater spike (Next-Tick Assessor Prediction).

Kill-or-continue gate for the BroadCore-S program. Question: does a LEARNED recurrent core add a
demonstrated, leakage-free increment over "field + reactive assessor nudge"? If not, STOP before P0.

Why naive metrics are unfair: the field already injects a_* into base every assessed tick, so it is
NOT semantics-blind; "predict a_t" is rigged. The only things a learned core can add that the
reactive, memoryless-w.r.t.-assessor nudge cannot are (1) cross-tick memory and (2) richer-than-4-
scalar message info. NTAP isolates both: from observables up to tick t, predict the NEXT assessed
tick's affect a_{t+1} (valence, arousal). a_{t+1} was injected into nothing at t -> leakage-free.
It is also exactly what Phase M needs (predict a_{t+1} => skip the next LLM call).

Baselines (steelmanned, same held-out split):
  - persistence: a_hat_{t+1} = a_t (zero-param floor under the floor).
  - field+nudge: Ridge AND GradientBoosting from the field's OWN exposed state (z_post carries the
    field's fixed recurrent memory) + a_t + surprise. The student must beat the field's own memory.

Student: the §5.1 cell (h=tanh(x·Win); u=tanh(z·Wrec+h·Wout); z=(1-α)z+α·u) + a 2-dim a_{t+1} head,
trained by truncated BPTT. Ablation across message bandwidth: V0 (no HDC) / V4 (8-float density) /
Vfull (64-float density) — a MECHANICAL probe of whether a message latent survives the HDC
bottleneck (NOT a test of real semantics; that needs real data).

HONEST CAVEAT: synthetic data. The robust headline is the memory increment; the HDC ablation only
tests the compression bottleneck on an injected latent.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DRIVEN = ["a_valence", "a_arousal"]  # graded dims for the headline


def load_sessions(path: str) -> list[dict]:
    """Group the tick corpus into per-session arrays sorted by tick; attach next-tick targets."""
    df = pd.read_parquet(path).sort_values(["session", "tick"]).reset_index(drop=True)
    sessions = []
    for sid, g in df.groupby("session"):
        n = len(g)
        if n < 3:
            continue
        rec = {
            "is_iid": bool(g.is_iid.iloc[0]),
            "a": g[["a_valence", "a_arousal", "a_wound_risk", "a_confidence"]].to_numpy(np.float32),
            "surprise": g.surprise.to_numpy(np.float32)[:, None],
            "z_post": np.array(g.z_post.tolist(), np.float32),
            "scar_mod": np.array(g.scar_mod.tolist(), np.float32),
            "hdc8": np.array(g.hdc8.tolist(), np.float32),
            "hdc64": np.array(g.hdc64.tolist(), np.float32),
            "ts": g.ts.to_numpy(np.float64),
        }
        dt = np.diff(rec["ts"], prepend=rec["ts"][0])
        rec["dt"] = np.log1p(np.clip(dt / 60.0, 0.0, 60.0)).astype(np.float32)[:, None]
        # target = next tick's (valence, arousal); valid for ticks 0..n-2
        tgt = rec["a"][1:, :2]
        rec["target"] = np.vstack([tgt, np.zeros((1, 2), np.float32)])  # last row invalid
        rec["valid"] = np.array([True] * (n - 1) + [False])
        sessions.append(rec)
    return sessions


def features(rec: dict, cond: str) -> np.ndarray:
    """x_t = a_t(4) + surprise(1) + scar_mod(8) + dt(1) [+ hdc by ablation condition]."""
    base = [rec["a"], rec["surprise"], rec["scar_mod"], rec["dt"]]
    if cond == "V4":
        base.append(rec["hdc8"])
    elif cond == "Vfull":
        base.append(rec["hdc64"])
    return np.concatenate(base, axis=1).astype(np.float32)


class BroadCoreS(torch.nn.Module):
    """§5.1 cell: structurally bounded (convex combo) recurrent core + a next-tick affect head."""

    def __init__(self, in_dim: int, h_dim: int = 24, z_dim: int = 8, out_dim: int = 2):
        super().__init__()
        self.Win = torch.nn.Linear(in_dim, h_dim)
        self.Wout = torch.nn.Linear(h_dim, z_dim, bias=False)
        self.Wrec = torch.nn.Linear(z_dim, z_dim, bias=False)
        self.alpha_raw = torch.nn.Parameter(torch.zeros(z_dim))
        self.head = torch.nn.Linear(z_dim, out_dim)
        self.z_dim = z_dim

    def forward(self, X: torch.Tensor) -> torch.Tensor:  # X: (B, T, in_dim) -> (B, T, out_dim)
        b, t, _ = X.shape
        z = torch.zeros(b, self.z_dim, device=X.device)
        alpha = torch.sigmoid(self.alpha_raw)
        outs = []
        for i in range(t):
            h = torch.tanh(self.Win(X[:, i, :]))
            u = torch.tanh(self.Wrec(z) + self.Wout(h))
            z = (1.0 - alpha) * z + alpha * u
            outs.append(self.head(z))
        return torch.stack(outs, dim=1)


def pad_batch(sessions: list[dict], cond: str) -> tuple[torch.Tensor, ...]:
    tmax = max(len(s["a"]) for s in sessions)
    feat = [features(s, cond) for s in sessions]
    fdim = feat[0].shape[1]
    b = len(sessions)
    X = np.zeros((b, tmax, fdim), np.float32)
    Y = np.zeros((b, tmax, 2), np.float32)
    M = np.zeros((b, tmax), bool)
    for i, s in enumerate(sessions):
        n = len(s["a"])
        X[i, :n] = feat[i]
        Y[i, :n] = s["target"]
        M[i, :n] = s["valid"]
    t = lambda a: torch.from_numpy(a).to(DEVICE)  # noqa: E731
    return t(X), t(Y), torch.from_numpy(M).to(DEVICE)


def train_student(train_s, test_s, cond, epochs=120, seed=0) -> dict:
    torch.manual_seed(seed)
    Xtr, Ytr, Mtr = pad_batch(train_s, cond)
    Xte, Yte, Mte = pad_batch(test_s, cond)
    model = BroadCoreS(Xtr.shape[2]).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    lossf = torch.nn.SmoothL1Loss(reduction="none")
    for _ in range(epochs):
        model.train()
        opt.zero_grad()
        pred = model(Xtr)
        loss = (lossf(pred, Ytr).mean(-1) * Mtr).sum() / Mtr.sum()
        loss.backward()
        opt.step()
        sched.step()
    model.eval()
    with torch.no_grad():
        pred = model(Xte).cpu().numpy()
    Yte_np, Mte_np = Yte.cpu().numpy(), Mte.cpu().numpy()
    return _score(pred, Yte_np, Mte_np, test_s)


def _flatten(pred, Y, M, test_s):
    """Return per-tick predictions/targets/iid-flag over valid ticks."""
    P, T, iids = [], [], []
    for i, s in enumerate(test_s):
        n = len(s["a"])
        for j in range(n):
            if M[i, j]:
                P.append(pred[i, j])
                T.append(Y[i, j])
                iids.append(s["is_iid"])
    return np.array(P), np.array(T), np.array(iids)


def _score(pred, Y, M, test_s) -> dict:
    P, T, iids = _flatten(pred, Y, M, test_s)
    err = np.abs(P - T)
    mae_all = err.mean(0)  # per-dim (valence, arousal)
    mae_ac = err[~iids].mean(0) if (~iids).any() else np.array([np.nan, np.nan])
    mae_iid = err[iids].mean(0) if iids.any() else np.array([np.nan, np.nan])
    # skippable: both dims within 0.1 of the truth (good enough to skip the LLM call)
    skippable = float((err.max(1) < 0.1).mean())
    return {
        "mae": float(mae_all.mean()),
        "mae_val": float(mae_all[0]),
        "mae_aro": float(mae_all[1]),
        "mae_ac": float(np.nanmean(mae_ac)),
        "mae_iid": float(np.nanmean(mae_iid)),
        "skippable": skippable,
        "pred": P,
        "tgt": T,
        "iid": iids,
    }


def baseline_persistence(test_s) -> dict:
    P, T, iids = [], [], []
    for s in test_s:
        n = len(s["a"])
        for j in range(n - 1):
            P.append(s["a"][j, :2])  # a_t
            T.append(s["target"][j])  # a_{t+1}
            iids.append(s["is_iid"])
    P, T, iids = np.array(P), np.array(T), np.array(iids)
    err = np.abs(P - T)
    return {
        "mae": float(err.mean()),
        "mae_val": float(err[:, 0].mean()),
        "mae_aro": float(err[:, 1].mean()),
        "mae_ac": float(err[~iids].mean()) if (~iids).any() else np.nan,
        "mae_iid": float(err[iids].mean()) if iids.any() else np.nan,
        "skippable": float((err.max(1) < 0.1).mean()),
    }


def _xy_memoryless(sessions):
    """field+nudge baseline inputs: z_post(8) + a_t(4) + surprise(1) -> a_{t+1}."""
    X, Y = [], []
    for s in sessions:
        n = len(s["a"])
        feat = np.concatenate([s["z_post"], s["a"], s["surprise"]], axis=1)
        for j in range(n - 1):
            X.append(feat[j])
            Y.append(s["target"][j])
    return np.array(X, np.float32), np.array(Y, np.float32)


def baseline_field(train_s, test_s, kind="ridge") -> dict:
    Xtr, Ytr = _xy_memoryless(train_s)
    Xte, Yte = _xy_memoryless(test_s)
    if kind == "ridge":
        m0, m1 = Ridge(alpha=1.0), Ridge(alpha=1.0)
    else:
        m0 = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05)
        m1 = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05)
    m0.fit(Xtr, Ytr[:, 0])
    m1.fit(Xtr, Ytr[:, 1])
    pred = np.stack([m0.predict(Xte), m1.predict(Xte)], axis=1)
    # iid flags aligned with _xy_memoryless ordering
    iids = []
    for s in test_s:
        iids += [s["is_iid"]] * (len(s["a"]) - 1)
    iids = np.array(iids)
    err = np.abs(pred - Yte)
    return {
        "mae": float(err.mean()),
        "mae_val": float(err[:, 0].mean()),
        "mae_aro": float(err[:, 1].mean()),
        "mae_ac": float(err[~iids].mean()) if (~iids).any() else np.nan,
        "mae_iid": float(err[iids].mean()) if iids.any() else np.nan,
        "skippable": float((err.max(1) < 0.1).mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default="training/student_core/spike_corpus.parquet")
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    sessions = load_sessions(args.corpus)
    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(sessions))
    n_test = int(len(sessions) * args.test_frac)
    test_s = [sessions[i] for i in idx[:n_test]]
    train_s = [sessions[i] for i in idx[n_test:]]
    print(f"device={DEVICE} sessions={len(sessions)} train={len(train_s)} test={len(test_s)}")

    pers = baseline_persistence(test_s)
    fr = baseline_field(train_s, test_s, "ridge")
    fg = baseline_field(train_s, test_s, "gbm")
    students = {
        c: train_student(train_s, test_s, c, args.epochs, args.seed) for c in ("V0", "V4", "Vfull")
    }

    def row(name, d):
        print(
            f"  {name:18s} MAE={d['mae']:.4f} (val={d['mae_val']:.4f} aro={d['mae_aro']:.4f}) "
            f"ac={d['mae_ac']:.4f} iid={d['mae_iid']:.4f} skippable={d['skippable'] * 100:5.1f}%"
        )

    print("\n=== NTAP results (lower MAE is better; ac=autocorrelated, iid=control) ===")
    row("persistence", pers)
    row("field+nudge ridge", fr)
    row("field+nudge gbm", fg)
    for c in ("V0", "V4", "Vfull"):
        row(f"student {c}", students[c])

    best_base = min(pers["mae"], fr["mae"], fg["mae"])
    best_base_ac = min(pers["mae_ac"], fr["mae_ac"], fg["mae_ac"])
    student = students["Vfull"]
    rel = (best_base - student["mae"]) / best_base
    rel_ac = (best_base_ac - student["mae_ac"]) / best_base_ac
    absimp = best_base - student["mae"]
    v4_over_v0 = (students["V0"]["mae"] - students["V4"]["mae"]) / students["V0"]["mae"]
    vfull_over_v4 = (students["V4"]["mae"] - students["Vfull"]["mae"]) / students["V4"]["mae"]

    print("\n=== VERDICT ===")
    print(f"  best baseline MAE={best_base:.4f}; best student (Vfull) MAE={student['mae']:.4f}")
    print(
        f"  student vs best baseline: {rel * 100:+.1f}% rel, {absimp:+.4f} abs; on autocorrelated: {rel_ac * 100:+.1f}% rel"
    )
    print(
        f"  HDC ablation: V4 over V0 = {v4_over_v0 * 100:+.1f}%; Vfull over V4 = {vfull_over_v4 * 100:+.1f}%"
    )
    passed = rel >= 0.15 and absimp >= 0.02 and rel_ac >= 0.15
    print(
        f"  memory-increment gate (>=15% rel AND >=0.02 abs, holds on autocorrelated): {'PASS' if passed else 'FAIL'}"
    )
    if students["V0"]["mae"] > 0 and (v4_over_v0 > 0.10 or vfull_over_v4 > 0.10):
        print(
            "  HDC verdict: message bandwidth HELPS -> the compression carries the latent (D-12 relevant)"
        )
    else:
        print(
            "  HDC verdict: message bandwidth adds little here -> increment (if any) is mostly cross-tick MEMORY"
        )
    print(
        f"\n  >>> SPIKE {'PASS — proceed to P0' if passed else 'FAIL — do NOT enter P0 (would be theater)'} <<<"
    )


if __name__ == "__main__":
    main()
