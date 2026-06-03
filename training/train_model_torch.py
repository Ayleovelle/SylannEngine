"""SylannEngine 嵌入式感知模型 — PyTorch 训练脚本.

用 torch 训练，导出 numpy 权重供推理使用。

Usage:
    python train_model_torch.py --data data/train.jsonl --output models/perception_v1.npz --epochs 20
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

EMOTION_KEYS = ["valence", "arousal", "dominance", "warmth",
                "vulnerability", "hostility", "engagement", "surprise"]


class EmotionDataset(Dataset):
    def __init__(self, path: str, max_len: int = 128):
        self.samples = []
        self.max_len = max_len
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "text" in obj and "emotion_raw" in obj:
                        self.samples.append(obj)
                except json.JSONDecodeError:
                    continue

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        # Byte-level tokenization
        raw = sample["text"].encode("utf-8")[:self.max_len]
        tokens = torch.zeros(self.max_len, dtype=torch.long)
        for i, b in enumerate(raw):
            tokens[i] = b + 1  # 0=pad, 1-256=bytes

        # Emotion target (8-dim)
        emotion = sample["emotion_raw"]
        target = torch.tensor(
            [float(emotion.get(k, 0.0)) for k in EMOTION_KEYS],
            dtype=torch.float32,
        )
        return tokens, target


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class PerceptionTransformer(nn.Module):
    """Lightweight Transformer: text bytes → emotion vector."""

    def __init__(self, d_model=128, n_heads=4, n_layers=4,
                 max_len=128, vocab_size=257, output_dim=128):
        super().__init__()
        self.d_model = d_model
        self.max_len = max_len

        self.token_emb = nn.Embedding(vocab_size, d_model)
        self.pos_emb = nn.Parameter(self._sinusoidal_pos(max_len, d_model), requires_grad=False)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=0.1,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.ln_final = nn.LayerNorm(d_model)
        self.output_proj = nn.Linear(d_model, output_dim)

        self._init_weights()

    def _sinusoidal_pos(self, max_len, d_model):
        pos = torch.arange(max_len).unsqueeze(1).float()
        dim = torch.arange(d_model).unsqueeze(0).float()
        angles = pos / (10000 ** (2 * (dim // 2) / d_model))
        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(angles[:, 0::2])
        pe[:, 1::2] = torch.cos(angles[:, 1::2])
        return pe

    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        """tokens: (batch, seq_len) → (batch, output_dim)"""
        seq_len = tokens.size(1)
        # Padding mask
        pad_mask = tokens == 0  # True where padded

        x = self.token_emb(tokens) + self.pos_emb[:seq_len]
        x = self.encoder(x, src_key_padding_mask=pad_mask)
        x = self.ln_final(x)

        # CLS pooling (first non-pad token, or mean pool)
        # Use mean of non-padded positions
        mask = (~pad_mask).unsqueeze(-1).float()
        x = (x * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)

        return self.output_proj(x)

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Data
    dataset = EmotionDataset(args.data, max_len=128)
    print(f"Dataset: {len(dataset)} samples")
    if len(dataset) == 0:
        print("No data! Run generate_data.py first.")
        return

    # Split train/val
    val_size = min(1000, len(dataset) // 10)
    train_size = len(dataset) - val_size
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # Model
    model = PerceptionTransformer(
        d_model=args.d_model,
        n_heads=4,
        n_layers=args.n_layers,
        output_dim=128,
    ).to(device)
    print(f"Parameters: {model.param_count():,}")

    # Optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # Target projection (8-dim emotion → 128-dim target)
    # Use a fixed random projection so the model learns a rich representation
    rng = np.random.RandomState(42)
    proj_matrix = torch.tensor(
        rng.randn(8, 128).astype(np.float32) * 0.1, device=device
    )

    best_val_loss = float("inf")

    for epoch in range(args.epochs):
        # Train
        model.train()
        train_loss = 0.0
        n_batches = 0
        for tokens, targets in train_loader:
            tokens = tokens.to(device)
            targets = targets.to(device)

            # Project 8-dim target to 128-dim
            targets_128 = targets @ proj_matrix
            targets_128[:, :8] = targets  # First 8 dims are raw

            pred = model(tokens)
            loss = F.mse_loss(pred, targets_128)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            train_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_train = train_loss / max(n_batches, 1)

        # Validate
        model.eval()
        val_loss = 0.0
        n_val = 0
        with torch.no_grad():
            for tokens, targets in val_loader:
                tokens = tokens.to(device)
                targets = targets.to(device)
                targets_128 = targets @ proj_matrix
                targets_128[:, :8] = targets
                pred = model(tokens)
                val_loss += F.mse_loss(pred, targets_128).item()
                n_val += 1

        avg_val = val_loss / max(n_val, 1)
        lr = scheduler.get_last_lr()[0]
        print(f"  Epoch {epoch+1}/{args.epochs} | train={avg_train:.4f} val={avg_val:.4f} lr={lr:.6f}")

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            # Export to numpy format
            export_to_numpy(model, args.output)
            print(f"    → Best model saved ({best_val_loss:.4f})")

    print(f"\nTraining complete. Best val loss: {best_val_loss:.4f}")
    print(f"Model saved to: {args.output}")


def export_to_numpy(model: PerceptionTransformer, path: str):
    """Export PyTorch model weights to numpy .npz for inference without torch."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    state = model.state_dict()
    np_state = {}
    for key, tensor in state.items():
        np_state[key] = tensor.cpu().numpy()

    np.savez_compressed(str(output_path), **np_state)


def main():
    parser = argparse.ArgumentParser(description="Train perception model with PyTorch")
    parser.add_argument("--data", type=str, default="training/data/train.jsonl")
    parser.add_argument("--output", type=str, default="training/models/perception_v1.npz")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--n-layers", type=int, default=4)
    args = parser.parse_args()

    train(args)


if __name__ == "__main__":
    main()
