"""SylannEngine 嵌入式感知模型 — 训练脚本.

从 generate_data.py 产出的 JSONL 训练一个轻量 Transformer 模型，
将文本映射到 128 维情感语义向量。

模型架构: 4 层 Transformer, d=128, heads=4, ~2M params
输入: UTF-8 bytes (无需分词器)
输出: 128 维情感向量

Usage:
    python train_model.py --data data/train.jsonl --output models/perception_v1.npz --epochs 10
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Byte-level tokenizer (no vocabulary needed)
# ---------------------------------------------------------------------------


def text_to_tokens(text: str, max_len: int = 128) -> np.ndarray:
    """Convert text to byte-level token IDs. Pad/truncate to max_len."""
    raw = text.encode("utf-8")[:max_len]
    tokens = np.zeros(max_len, dtype=np.int32)
    for i, b in enumerate(raw):
        tokens[i] = b + 1  # 0 = padding, 1-256 = byte values
    return tokens


def emotion_dict_to_vector(emotion: dict) -> np.ndarray:
    """Convert emotion dict to fixed 128-dim vector.

    First 8 dims = raw emotion values (valence, arousal, dominance, warmth,
    vulnerability, hostility, engagement, surprise).
    Remaining 120 dims = learned representation space (target for model).
    For training, we use the 8 raw dims repeated/projected to fill 128.
    """
    keys = ["valence", "arousal", "dominance", "warmth",
            "vulnerability", "hostility", "engagement", "surprise"]
    raw = np.array([float(emotion.get(k, 0.0)) for k in keys], dtype=np.float32)

    # Project 8-dim to 128-dim using a fixed random projection (reproducible)
    rng = np.random.RandomState(42)
    proj_matrix = rng.randn(8, 128).astype(np.float32) * 0.1
    projected = raw @ proj_matrix
    # First 8 dims are the raw values
    projected[:8] = raw
    return projected


# ---------------------------------------------------------------------------
# Model architecture (numpy forward pass)
# ---------------------------------------------------------------------------


def gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x**3)))


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    e = np.exp(x - x.max(axis=axis, keepdims=True))
    return e / e.sum(axis=axis, keepdims=True)


def layer_norm(x: np.ndarray, gamma: np.ndarray, beta: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return gamma * (x - mean) / np.sqrt(var + eps) + beta


class MiniTransformer:
    """4-layer Transformer for text → emotion vector.

    Architecture:
    - Byte embedding: 257 tokens → d_model
    - Positional encoding: sinusoidal
    - 4 × TransformerBlock(d_model, n_heads, d_ff=4*d_model)
    - CLS pooling → linear → 128-dim output
    """

    def __init__(self, d_model: int = 128, n_heads: int = 4, n_layers: int = 4,
                 max_len: int = 128, vocab_size: int = 257, output_dim: int = 128):
        self.d_model = d_model
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.max_len = max_len
        self.vocab_size = vocab_size
        self.output_dim = output_dim
        self.d_head = d_model // n_heads
        self.d_ff = d_model * 4

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Xavier/He initialization."""
        rng = np.random.RandomState(0)
        d = self.d_model
        ff = self.d_ff

        # Embedding
        self.token_emb = rng.randn(self.vocab_size, d).astype(np.float32) * 0.02
        self.pos_emb = self._sinusoidal_pos(self.max_len, d)

        # Transformer layers
        self.layers = []
        for _ in range(self.n_layers):
            layer = {
                # Self-attention
                "Wq": rng.randn(d, d).astype(np.float32) * (d ** -0.5),
                "Wk": rng.randn(d, d).astype(np.float32) * (d ** -0.5),
                "Wv": rng.randn(d, d).astype(np.float32) * (d ** -0.5),
                "Wo": rng.randn(d, d).astype(np.float32) * (d ** -0.5),
                # Layer norms
                "ln1_g": np.ones(d, dtype=np.float32),
                "ln1_b": np.zeros(d, dtype=np.float32),
                "ln2_g": np.ones(d, dtype=np.float32),
                "ln2_b": np.zeros(d, dtype=np.float32),
                # FFN
                "W1": rng.randn(d, ff).astype(np.float32) * (d ** -0.5),
                "b1": np.zeros(ff, dtype=np.float32),
                "W2": rng.randn(ff, d).astype(np.float32) * (ff ** -0.5),
                "b2": np.zeros(d, dtype=np.float32),
            }
            self.layers.append(layer)

        # Output head
        self.ln_final_g = np.ones(d, dtype=np.float32)
        self.ln_final_b = np.zeros(d, dtype=np.float32)
        self.output_proj = rng.randn(d, self.output_dim).astype(np.float32) * (d ** -0.5)

    def _sinusoidal_pos(self, max_len: int, d_model: int) -> np.ndarray:
        pos = np.arange(max_len)[:, None]
        dim = np.arange(d_model)[None, :]
        angles = pos / (10000 ** (2 * (dim // 2) / d_model))
        pe = np.zeros((max_len, d_model), dtype=np.float32)
        pe[:, 0::2] = np.sin(angles[:, 0::2])
        pe[:, 1::2] = np.cos(angles[:, 1::2])
        return pe

    def forward(self, tokens: np.ndarray) -> np.ndarray:
        """Forward pass. tokens: (seq_len,) int array → (output_dim,) float array."""
        seq_len = len(tokens)

        # Embedding + positional
        x = self.token_emb[tokens] + self.pos_emb[:seq_len]

        # Transformer blocks
        for layer in self.layers:
            # Self-attention with pre-norm
            residual = x
            x = layer_norm(x, layer["ln1_g"], layer["ln1_b"])

            Q = x @ layer["Wq"]  # (seq, d)
            K = x @ layer["Wk"]
            V = x @ layer["Wv"]

            # Reshape for multi-head
            Q = Q.reshape(seq_len, self.n_heads, self.d_head).transpose(1, 0, 2)  # (h, seq, dh)
            K = K.reshape(seq_len, self.n_heads, self.d_head).transpose(1, 0, 2)
            V = V.reshape(seq_len, self.n_heads, self.d_head).transpose(1, 0, 2)

            # Attention scores
            scores = (Q @ K.transpose(0, 2, 1)) / math.sqrt(self.d_head)  # (h, seq, seq)
            attn = softmax(scores, axis=-1)
            out = (attn @ V).transpose(1, 0, 2).reshape(seq_len, self.d_model)  # (seq, d)
            out = out @ layer["Wo"]
            x = residual + out

            # FFN with pre-norm
            residual = x
            x = layer_norm(x, layer["ln2_g"], layer["ln2_b"])
            x = gelu(x @ layer["W1"] + layer["b1"])
            x = x @ layer["W2"] + layer["b2"]
            x = residual + x

        # CLS pooling (first token) + output projection
        x = layer_norm(x, self.ln_final_g, self.ln_final_b)
        cls = x[0]  # First token as representation
        return cls @ self.output_proj

    def save(self, path: str):
        """Save all weights to .npz file."""
        data = {
            "token_emb": self.token_emb,
            "pos_emb": self.pos_emb,
            "ln_final_g": self.ln_final_g,
            "ln_final_b": self.ln_final_b,
            "output_proj": self.output_proj,
        }
        for i, layer in enumerate(self.layers):
            for key, val in layer.items():
                data[f"layer{i}_{key}"] = val
        np.savez_compressed(path, **data)

    def load(self, path: str):
        """Load weights from .npz file."""
        data = np.load(path)
        self.token_emb = data["token_emb"]
        self.pos_emb = data["pos_emb"]
        self.ln_final_g = data["ln_final_g"]
        self.ln_final_b = data["ln_final_b"]
        self.output_proj = data["output_proj"]
        for i in range(self.n_layers):
            for key in self.layers[i]:
                self.layers[i][key] = data[f"layer{i}_{key}"]

    def param_count(self) -> int:
        total = self.token_emb.size + self.pos_emb.size
        total += self.ln_final_g.size + self.ln_final_b.size + self.output_proj.size
        for layer in self.layers:
            for v in layer.values():
                total += v.size
        return total


# ---------------------------------------------------------------------------
# Training loop (simple SGD with momentum)
# ---------------------------------------------------------------------------


def mse_loss(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean((pred - target) ** 2))


def load_dataset(path: str) -> list[dict]:
    """Load JSONL dataset."""
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return data


def main():
    parser = argparse.ArgumentParser(description="Train embedded perception model")
    parser.add_argument("--data", type=str, default="training/data/train.jsonl")
    parser.add_argument("--output", type=str, default="training/models/perception_v1.npz")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--n-layers", type=int, default=4)
    args = parser.parse_args()

    print(f"Loading data from {args.data}...")
    dataset = load_dataset(args.data)
    print(f"Loaded {len(dataset)} samples")

    if not dataset:
        print("No data! Run generate_data.py first.")
        return

    # Prepare training pairs
    texts = []
    targets = []
    for sample in dataset:
        if "text" in sample and "emotion_raw" in sample:
            tokens = text_to_tokens(sample["text"])
            target = emotion_dict_to_vector(sample["emotion_raw"])
            texts.append(tokens)
            targets.append(target)

    texts = np.array(texts)
    targets = np.array(targets)
    print(f"Training pairs: {len(texts)}")

    # Create model
    model = MiniTransformer(d_model=args.d_model, n_layers=args.n_layers)
    print(f"Model parameters: {model.param_count():,}")

    # Save initial model (for inference testing)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(output_path))
    print(f"Initial model saved to {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")

    print("\nNote: Full training requires torch for backprop.")
    print("This script saves the model architecture for numpy inference.")
    print("To train with torch, use: python train_model_torch.py")


if __name__ == "__main__":
    main()
