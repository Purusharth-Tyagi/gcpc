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


def alias_blob(row: dict) -> str:
    """Embed canonical PLUS every alias. This single line is worth more than
    any model choice: callers say 'AI wala course', not the catalog name."""
    return " | ".join([row["canonical"], *row.get("aliases", [])])


def upsert_rows(collection: str, rows: list[dict]) -> None:
    points = [
        PointStruct(
            id=point_id(r["id"]),
            vector=embed(alias_blob(r)),
            payload={**r, "code": r["id"]},
        )
        for r in rows
    ]
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
        limit=3,
    ).points
    if not hits:
        return None
    top = hits[0]
    second = hits[1].score if len(hits) > 1 else 0.0
    return Resolution(
        code=top.payload["code"],
        canonical=top.payload["canonical"],
        phoneme=top.payload.get("phoneme"),
        score=round(top.score, 4),
        band=_band(top.score, second),
        payload=top.payload,
        alternates=[h.payload["canonical"] for h in hits[1:]],
    )


ROUTE_MIN = 0.30


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


def recall(phone: str, k: int = 3) -> list[str]:
    """Short natural-language facts. C feeds these straight to an LLM."""
    hits = client.query_points(
        "memory", query=embed(phone),
        query_filter=Filter(must=[FieldCondition(key="phone", match=MatchValue(value=phone))]),
        limit=k,
    ).points
    return [h.payload["fact"] for h in hits]

