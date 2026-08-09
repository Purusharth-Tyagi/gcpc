"""Lane B core. resolve() / route() / recall() over Qdrant."""
import os, sys, zlib
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contracts.types import Resolution, Intent          # noqa: E402
from retrieval.embed import embed, vector_size          # noqa: E402

COLLECTIONS = ["courses", "exams", "faculty", "campus", "intents", "memory"]

# NEVER do kind + "s". "faculty" -> "facultys" and you lose 20 minutes at 2am.
KIND_TO_COLLECTION = {
    "course": "courses", "exam": "exams",
    "faculty": "faculty", "campus": "campus",
}

# Bands are calibrated for the ngram backend. Re-tune if you switch to bge.
# MARGIN matters as much as the absolute score: a 0.40 top with a 0.38 runner-up
# is a coin flip, a 0.40 top with a 0.15 runner-up is certain.
ACCEPT_MIN, CONFIRM_MIN, MARGIN_MIN = 0.42, 0.26, 0.08


def _client() -> QdrantClient:
    url = os.getenv("QDRANT_URL")
    if not url or url == ":memory:":
        return QdrantClient(":memory:")
    return QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"))


client = _client()


def point_id(code: str) -> int:
    """Qdrant point ids must be unsigned ints or UUIDs. Arbitrary strings like
    'c01' are REJECTED. Derive a stable int, keep the human code in payload."""
    return zlib.crc32(code.encode("utf-8"))


def ensure_collections(wipe: bool = False) -> None:
    size = vector_size()
    for name in COLLECTIONS:
        if wipe and client.collection_exists(name):
            client.delete_collection(name)
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
            )


def surface_forms(row: dict) -> list[str]:
    """Every string a caller might say for this row."""
    return [row["canonical"], *row.get("aliases", [])]


def upsert_rows(collection: str, rows: list[dict]) -> None:
    """ONE POINT PER SURFACE FORM, not one per row.

    A single blended vector per row fails two ways:
      - short queries ("CSE") drown in a long blob and match the wrong row
      - Devanagari aliases are a tiny fraction of a Latin-dominated blob,
        so a pure-Devanagari query matches almost nothing
    Giving each alias its own vector fixes both. Rows are ~100 and aliases
    ~7 each, so this is under a thousand points. Free.

    resolve() dedupes back to one hit per row by payload["code"].
    """
    points = []
    for r in rows:
        for i, form in enumerate(surface_forms(r)):
            points.append(PointStruct(
                id=point_id(f"{r['id']}#{i}"),
                vector=embed(form),
                payload={**r, "code": r["id"], "matched_form": form},
            ))
    client.upsert(collection_name=collection, points=points)


def _band(top: float, second: float) -> str:
    if top >= ACCEPT_MIN and (top - second) >= MARGIN_MIN:
        return "accept"
    if top >= CONFIRM_MIN:
        return "confirm"
    return "reject"


def resolve(text: str, kind: str, filters: dict | None = None) -> Resolution | None:
    """kind in {course, exam, faculty, campus}. Returns None on no hit at all."""
    qfilter = None
    if filters:
        qfilter = Filter(must=[
            FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
        ])
    collection = KIND_TO_COLLECTION.get(kind)
    if collection is None:
        raise ValueError(f"unknown kind {kind!r}, expected one of {list(KIND_TO_COLLECTION)}")
    hits = client.query_points(
        collection_name=collection,
        query=embed(text),
        query_filter=qfilter,      # filter DURING search, never after
        limit=15,                  # over-fetch: several points share one code
    ).points
    if not hits:
        return None

    # collapse surface-form hits down to one per row, keeping the best
    best: dict[str, object] = {}
    for h in hits:
        code = h.payload["code"]
        if code not in best:
            best[code] = h
    ranked = list(best.values())

    top = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else 0.0
    return Resolution(
        code=top.payload["code"],
        canonical=top.payload["canonical"],
        phoneme=top.payload.get("phoneme"),
        score=round(top.score, 4),
        band=_band(top.score, second),
        payload=top.payload,
        alternates=[h.payload["canonical"] for h in ranked[1:3]],
    )


# Measured, not guessed. With one point per surface form:
#   legitimate intents  min 0.805
#   off-topic input     max 0.510
# 0.65 sits in the gap. Re-measure if you change the embedder or add intents.
ROUTE_MIN = 0.65


def route(text: str) -> Intent:
    hits = client.query_points("intents", query=embed(text), limit=1).points
    if not hits or hits[0].score < ROUTE_MIN:
        return Intent("unknown", 0.0)     # C falls through to the LLM
    return Intent(hits[0].payload["label"], round(hits[0].score, 4))


def remember(phone: str, fact: str, kind: str = "note") -> None:
    client.upsert("memory", points=[PointStruct(
        id=point_id(f"{phone}:{fact}"), vector=embed(fact),
        payload={"phone": phone, "fact": fact, "kind": kind},
    )])


def recall(phone: str, context: str | None = None, k: int = 3) -> list[str]:
    """Short natural-language facts for this caller. C feeds these to an LLM.

    Pass `context` (what the caller just said) to rank by relevance instead of
    returning an arbitrary slice. Without it this is a key-value lookup and the
    vector DB earns nothing; with it, a caller asking about fees gets their fee
    history surfaced, not their visit preference.

    The phone filter runs DURING search, so relevance ranking never leaks facts
    across callers.
    """
    hits = client.query_points(
        "memory",
        query=embed(context if context else phone),
        query_filter=Filter(must=[
            FieldCondition(key="phone", match=MatchValue(value=phone))
        ]),
        limit=k,
    ).points
    return [h.payload["fact"] for h in hits]
