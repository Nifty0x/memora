"""Projections: derived, disposable recall structures rebuilt from the ledger.

Two reference Projections: a lexical index (BM25-style) and a vector index
with a deterministic hashing embedder. Both support full replay: rebuilding
from the ledger yields a bit-identical state hash.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict

from .core import Ledger, canonical_hash

TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list:
    return TOKEN.findall(text.lower())


class HashingEmbedder:
    """Deterministic 256-dim hashing embedder. Pluggable: any embedder with
    embed(text) -> list[float] fits, including neural ones."""

    id = "embedder.hashing.sha1"
    version = "1.0"
    dim = 256

    def embed(self, text: str) -> dict:
        """Sparse representation: {dim_index: weight}. At most one nonzero
        dim per distinct token, so dot products cost O(query tokens)."""
        v = {}
        for tok, cnt in Counter(tokenize(text)).items():
            h = int(hashlib.sha1(tok.encode()).hexdigest(), 16)
            d = h % self.dim
            v[d] = v.get(d, 0.0) + float(cnt) * (1.0 if (h >> 130) % 2 else -1.0)
        n = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {d: x / n for d, x in v.items()}


class LexicalProjection:
    """BM25-style inverted index over active Memory Events."""

    id = "projection.lexical.bm25"
    version = "1.0"

    def __init__(self):
        self.docs = {}
        self.df = Counter()
        self.doclen = {}
        self.avglen = 0.0

    def build(self, ledger: Ledger, scope=None) -> str:
        self.docs.clear(); self.df.clear(); self.doclen.clear()
        for ev in ledger.events(scope=scope):
            toks = tokenize(ev.payload or "")
            self.docs[ev.id] = Counter(toks)
            self.doclen[ev.id] = len(toks)
            for t in set(toks):
                self.df[t] += 1
        self.avglen = (sum(self.doclen.values()) / len(self.doclen)) if self.doclen else 0.0
        return self.state_hash()

    def query(self, text: str, k: int = 5, k1: float = 1.5, b: float = 0.75) -> list:
        n = len(self.docs)
        scores = defaultdict(float)
        for t in tokenize(text):
            if self.df[t] == 0:
                continue
            idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            for doc, tf_map in self.docs.items():
                tf = tf_map.get(t, 0)
                if tf:
                    dl = self.doclen[doc] / (self.avglen or 1.0)
                    scores[doc] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl))
        return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:k]

    def state_hash(self) -> str:
        return canonical_hash({d: sorted(c.items()) for d, c in self.docs.items()})


class VectorProjection:
    """Cosine-similarity index over event embeddings."""

    id = "projection.vector.cosine"
    version = "1.0"

    def __init__(self, embedder=None):
        self.embedder = embedder or HashingEmbedder()
        self.vecs = {}
        self.inv = {}

    def build(self, ledger: Ledger, scope=None) -> str:
        self.vecs = {ev.id: self.embedder.embed(ev.payload or "")
                     for ev in ledger.events(scope=scope)}
        self.inv = {}
        for doc, v in self.vecs.items():
            for d, w in v.items():
                self.inv.setdefault(d, []).append((doc, w))
        return self.state_hash()

    def query(self, text: str, k: int = 5) -> list:
        q = self.embedder.embed(text)
        # inverted index over dims: dim -> [(doc, weight)]
        scored = {}
        for d, qw in q.items():
            for doc, w in self.inv.get(d, ()):
                scored[doc] = scored.get(doc, 0.0) + qw * w
        return sorted(scored.items(), key=lambda x: (-x[1], x[0]))[:k]

    def state_hash(self) -> str:
        return canonical_hash({doc: sorted((d, round(x, 10)) for d, x in v.items())
                               for doc, v in self.vecs.items()})
