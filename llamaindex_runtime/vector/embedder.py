"""Hash-based deterministic embedding for testing and reproducibility.

Uses SHA-256 token hashing to produce L2-normalized vectors.
Not suitable for production semantic search -- use a real embedding model instead.
"""
from __future__ import annotations

import hashlib
import math
from typing import List


class DeterministicEmbedder:
    def __init__(self, dim: int = 16) -> None:
        if dim < 1:
            raise ValueError("dim must be >= 1")
        self.dim = dim

    def embed_text(self, text: str) -> List[float]:
        """Produce a deterministic, L2-normalized embedding vector for *text*."""
        vec = [0.0] * self.dim
        if not text:
            return vec
        for token in self._tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dim):
                vec[i] += digest[i] / 255.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def _tokenize(self, text: str) -> list[str]:
        compact = "".join(text.split())
        if not compact:
            return []
        tokens = [compact]
        tokens.extend(list(compact))
        if len(compact) > 1:
            tokens.extend(compact[i : i + 2] for i in range(len(compact) - 1))
        return tokens
