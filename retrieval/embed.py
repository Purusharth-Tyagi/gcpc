"""Embedding for Lane B.

Default: hashed character n-grams. Zero downloads, ~50us, no GPU, no network.
For matching short noisy ASR strings against short catalog strings this is
competitive with a neural encoder and roughly 100x faster.

Swap to bge-small by setting EMBED_BACKEND=bge. Do NOT swap mid-build without
re-running the test set and re-tuning bands: the backends have different scales.
"""
import os, re, zlib
import numpy as np

DIM = 512
_BACKEND = os.getenv("EMBED_BACKEND", "ngram")
_model = None

_KEEP = re.compile(r"[^a-z0-9\u0900-\u097F ]+")
_WS = re.compile(r"\s+")
_FILLER = {"umm", "uh", "matlab", "yaani", "please", "sir", "maam", "actually",
           "basically", "haan", "toh", "na", "ji", "the", "a", "hai", "ka"}


def normalise(s: str) -> str:
    s = _KEEP.sub(" ", s.lower())
    return " ".join(t for t in _WS.sub(" ", s).strip().split() if t not in _FILLER)


def _stable_hash(g: str) -> int:
    # zlib.crc32 is stable across processes. Python's hash() is NOT (salted per
    # process unless PYTHONHASHSEED is set), which would make ingested vectors
    # silently disagree with query vectors. This bug is invisible until it isn't.
    return zlib.crc32(g.encode("utf-8"))


def _ngram_embed(text: str) -> list[float]:
    t = " " + normalise(text) + " "
    v = np.zeros(DIM, dtype=np.float32)
    for n in (3, 4, 5):
        for i in range(len(t) - n + 1):
            v[_stable_hash(t[i:i + n]) % DIM] += 1.0
    nrm = float(np.linalg.norm(v))
    return (v / nrm).tolist() if nrm else v.tolist()


def _bge_embed(text: str) -> list[float]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _model.encode(normalise(text), normalize_embeddings=True).tolist()


def embed(text: str) -> list[float]:
    return _bge_embed(text) if _BACKEND == "bge" else _ngram_embed(text)


def vector_size() -> int:
    return 384 if _BACKEND == "bge" else DIM

