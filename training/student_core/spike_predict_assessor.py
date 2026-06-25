"""spike_predict_assessor.py — complementary probe to NTAP: the Phase-M payoff test.

NTAP (predict a_{t+1}) conflates the increment with future-message unpredictability. This probe
asks the question that actually decides the program's value: can a fast learned core predict the
ASSESSOR'S CURRENT read a_t from the MESSAGE (+ state), WITHOUT calling the LLM — i.e. could it
skip the call? The student gets the message HDC + prior state + scar-mod (NOT a_t). Baselines:
  - field-blind: the field's own pre-nudge base (semantic-blind — it never read the message) as a
    guess of a_t. This is what "the field alone, no assessor" knows.
  - persistence: a_{t-1}.
If the student (reading HDC) beats the field-blind baseline, the MECHANISM works: a cheap core can
extract message->affect that the field cannot. (Synthetic caveat: the message encodes the latent
mood by construction; whether REAL messages' affect survives a cheap HDC is the open D-12 question
that only real data answers. This probe proves capability, not real-world sufficiency.)
"""

from __future__ import annotations

import argparse
import os
import sys

if sys.path and os.path.basename(sys.path[0]) == "student_core":
    sys.path[0] = os.getcwd()

import importlib.util

import numpy as np
import torch

_spec = importlib.util.spec_from_file_location("sp", "training/student_core/spike_ntap.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)


def feats_msg(rec, cond):
    """Inputs for predicting a_t: message HDC + prior base + scar-mod + surprise + dt. NO a_t."""
    parts = [rec["z_prev_full"], rec["scar_mod"], rec["surprise"], rec["dt"]]
    if cond == "V4":
        parts.append(rec["hdc8"])
    elif cond == "Vfull":
        parts.append(rec["hdc64"])
    return np.concatenate(parts, axis=1).astype(np.float32)


def build(sessions, cond):
    """Per-session (X, Y=a_t, mask) with target = the assessor's CURRENT read (all ticks valid)."""
    out = []
    for s in sessions:
        n = len(s["a"])
        X = feats_msg(s, cond)
        Y = s["a"][:, :2]  # a_t valence, arousal
        out.append((X, Y, np.ones(n, bool), s["is_iid"]))
    return out


def to_pad(items):
    tmax = max(x.shape[0] for x, _, _, _ in items)
    fdim = items[0][0].shape[1]
    b = len(items)
    X = np.zeros((b, tmax, fdim), np.float32)
    Y = np.zeros((b, tmax, 2), np.float32)
    M = np.zeros((b, tmax), bool)
    for i, (x, y, m, _) in enumerate(items):
        X[i, : len(m)] = x
        Y[i, : len(m)] = y
        M[i, : len(m)] = m
    dev = sp.DEVICE
    return (
        torch.from_numpy(X).to(dev),
        torch.from_numpy(Y).to(dev),
        torch.from_numpy(M).to(dev),
    )


def train(train_items, test_items, in_dim, epochs, seed):
    torch.manual_seed(seed)
    Xtr, Ytr, Mtr = to_pad(train_items)
    Xte, Yte, Mte = to_pad(test_items)
    model = sp.BroadCoreS(in_dim).to(sp.DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    lf = torch.nn.SmoothL1Loss(reduction="none")
    for _ in range(epochs):
        opt.zero_grad()
        pred = model(Xtr)
        loss = (lf(pred, Ytr).mean(-1) * Mtr).sum() / Mtr.sum()
        loss.backward()
        opt.step()
        sched.step()
    with torch.no_grad():
        pred = model(Xte).cpu().numpy()
    return score(pred, Yte.cpu().numpy(), Mte.cpu().numpy(), test_items)


def score(pred, Y, M, items):
    P, T, iids = [], [], []
    for i, (_, _, m, iid) in enumerate(items):
        for j in range(len(m)):
            if M[i, j]:
                P.append(pred[i, j])
                T.append(Y[i, j])
                iids.append(iid)
    P, T, iids = np.array(P), np.array(T), np.array(iids)
    err = np.abs(P - T)
    return {
        "mae": float(err.mean()),
        "mae_ac": float(err[~iids].mean()) if (~iids).any() else float("nan"),
        "skippable": float((err.max(1) < 0.1).mean()),
    }



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="training/student_core/spike_corpus.parquet")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    sessions = sp.load_sessions(args.corpus)
    # attach full prior base (z_prev) per tick for the message-only feature set
    import pandas as pd

    df = pd.read_parquet(args.corpus).sort_values(["session", "tick"])
    # load_sessions drops <3 tick sessions and reorders; re-derive aligned per session
    sessions = []
    for sid, g in df.groupby("session"):
        n = len(g)
        if n < 3:
            continue
        sessions.append(
            {
                "is_iid": bool(g.is_iid.iloc[0]),
                "a": g[["a_valence", "a_arousal", "a_wound_risk", "a_confidence"]].to_numpy(np.float32),
                "surprise": g.surprise.to_numpy(np.float32)[:, None],
                "z_prev_full": np.array(g.z_prev.tolist(), np.float32),
                "base_pre_nudge": np.array(g.base_pre_nudge.tolist(), np.float32),
                "scar_mod": np.array(g.scar_mod.tolist(), np.float32),
                "hdc8": np.array(g.hdc8.tolist(), np.float32),
                "hdc64": np.array(g.hdc64.tolist(), np.float32),
                "dt": np.log1p(
                    np.clip(np.diff(g.ts.to_numpy(np.float64), prepend=g.ts.iloc[0]) / 60.0, 0, 60)
                ).astype(np.float32)[:, None],
            }
        )

    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(sessions))
    nt = int(len(sessions) * 0.2)
    test = [sessions[i] for i in idx[:nt]]
    train_s = [sessions[i] for i in idx[nt:]]
    print(f"device={sp.DEVICE} sessions={len(sessions)} train={len(train_s)} test={len(test)}")

    # field-blind baseline: pre-nudge base (idx2=valence, idx1=arousal) vs a_t
    P, T, iids = [], [], []
    for s in test:
        P.append(s["base_pre_nudge"][:, [2, 1]])
        T.append(s["a"][:, :2])
        iids.append(np.full(len(s["a"]), s["is_iid"]))
    P, T, iids = np.vstack(P), np.vstack(T), np.concatenate(iids)
    eb = np.abs(P - T)
    print("\n=== Predict-assessor (a_t from message+state, NO a_t input); lower MAE better ===")
    print(
        f"  field-blind (pre-nudge base) MAE={eb.mean():.4f} ac={eb[~iids].mean():.4f} "
        f"skippable={(eb.max(1) < 0.1).mean()*100:.1f}%"
    )
    # persistence a_{t-1}
    P, T, iids = [], [], []
    for s in test:
        P.append(s["a"][:-1, :2])
        T.append(s["a"][1:, :2])
        iids.append(np.full(len(s["a"]) - 1, s["is_iid"]))
    P, T, iids = np.vstack(P), np.vstack(T), np.concatenate(iids)
    ep = np.abs(P - T)
    print(f"  persistence a_(t-1)          MAE={ep.mean():.4f} ac={ep[~iids].mean():.4f}")

    for cond in ("V0", "V4", "Vfull"):
        items_tr = build(train_s, cond)
        items_te = build(test, cond)
        in_dim = items_tr[0][0].shape[1]
        r = train(items_tr, items_te, in_dim, args.epochs, args.seed)
        print(
            f"  student {cond:5s} (reads msg)    MAE={r['mae']:.4f} ac={r['mae_ac']:.4f} "
            f"skippable={r['skippable']*100:.1f}%"
        )

    print("\n  Read: if student Vfull/V4 << field-blind, a learned core can predict the assessor's")
    print("  read from the message (Phase-M call-skipping is mechanically possible). HDC width gap")
    print("  (Vfull vs V4) sizes the D-12 question. Synthetic caveat: real-message sufficiency unproven.")


if __name__ == "__main__":
    main()
