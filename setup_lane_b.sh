#!/usr/bin/env bash
# Lane B setup. Run from your repo root:   bash setup_lane_b.sh
set -e
echo "creating lane B tree..."
mkdir -p contracts retrieval scripts data tests

cat > contracts/__init__.py << 'LANEB_EOF'

LANEB_EOF

cat > contracts/types.py << 'LANEB_EOF'
"""FROZEN AT H1. Changing this after H1 means telling all four people."""
from dataclasses import dataclass, field


@dataclass
class Resolution:
    code: str                 # catalog id, e.g. "c01"
    canonical: str            # exactly what the agent should say
    phoneme: str | None       # Rime brace string, e.g. "{b1i tEk s1i 1Es 1i}"
    score: float
    band: str                 # "accept" | "confirm" | "reject"
    payload: dict = field(default_factory=dict)
    alternates: list[str] = field(default_factory=list)


@dataclass
class Intent:
    name: str
    confidence: float

LANEB_EOF

cat > retrieval/__init__.py << 'LANEB_EOF'

LANEB_EOF

cat > retrieval/embed.py << 'LANEB_EOF'
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

LANEB_EOF

cat > retrieval/store.py << 'LANEB_EOF'
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

LANEB_EOF

cat > retrieval/mocks.py << 'LANEB_EOF'
"""H1:15 unblock. Push this BEFORE you build anything real.
Three people are blocked until it exists. Delete once store.py works."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contracts.types import Resolution, Intent

_M = {
    "cse": Resolution("c01", "B.Tech Computer Science and Engineering (AI & ML)",
                      "{b1i tEk s1i 1Es 1i}", 0.95, "accept",
                      {"fees_per_year": 185000, "seats": 120, "duration_years": 4,
                       "cutoffs": {"jee_main": 88.0}}),
    "jee": Resolution("jee_main", "JEE Main", "{J1i 1i 1i m1eyn}", 0.95, "accept",
                      {"score_type": "percentile", "score_min": 0, "score_max": 100}),
}

def resolve(text, kind, filters=None):
    for k, v in _M.items():
        if k in text.lower():
            return v
    return None

def route(text):
    return Intent("eligibility", 0.9) if "eligib" in text.lower() else Intent("unknown", 0.0)

def recall(phone, k=3):
    return []

LANEB_EOF

cat > scripts/ingest.py << 'LANEB_EOF'
#!/usr/bin/env python3
"""Rerunnable Qdrant loader. D will hand you three revised catalogs overnight.

    python scripts/ingest.py --wipe
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import ensure_collections, upsert_rows, client   # noqa: E402

CONTENT = ["courses", "exams", "faculty", "campus"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/seed_catalog.json")
    ap.add_argument("--wipe", action="store_true")
    a = ap.parse_args()

    cat = json.load(open(a.catalog))
    t0 = time.time()
    ensure_collections(wipe=a.wipe)

    for name in CONTENT:
        rows = cat.get(name, [])
        if rows:
            upsert_rows(name, rows)
            print(f"  {name:10} {len(rows):4} rows")

    intents = cat.get("intents", [])
    if intents:
        upsert_rows("intents", intents)
        print(f"  {'intents':10} {len(intents):4} rows")

    # Fail loudly if the catalog is internally inconsistent. C's whole
    # eligibility check reads cutoffs keyed by exam id.
    exam_ids = {e["id"] for e in cat.get("exams", [])}
    bad = [(c["id"], k) for c in cat.get("courses", [])
           for k in c.get("cutoffs", {}) if k not in exam_ids]
    if bad:
        print("\n  !! cutoff keys with no matching exam id:", bad)
        print("  !! tell D now — C's eligibility check will silently return 'unknown'")

    print(f"\ningested in {time.time()-t0:.2f}s")


if __name__ == "__main__":
    main()

LANEB_EOF

cat > data/seed_catalog.json << 'LANEB_EOF'
{
 "courses": [
  {
   "id": "c01",
   "canonical": "B.Tech Computer Science and Engineering (AI & ML)",
   "aliases": [
    "BTech CSE AIML",
    "CSE AI ML",
    "computer science AI",
    "AI wala course",
    "artificial intelligence branch",
    "CS with AI specialisation",
    "कंप्यूटर साइंस एआई"
   ],
   "phoneme": "{b1i tEk s1i 1Es 1i}",
   "degree": "B.Tech",
   "branch": "CSE-AIML",
   "duration_years": 4,
   "fees_per_year": 185000,
   "seats": 120,
   "intake_open": true,
   "cutoffs": {
    "jee_main": 88.0,
    "cuet": 92.0,
    "university_test": 65.0
   }
  },
  {
   "id": "c02",
   "canonical": "B.Tech Computer Science and Engineering",
   "aliases": [
    "BTech CSE",
    "computer science",
    "CS branch",
    "seeyesee",
    "plain CSE",
    "कंप्यूटर साइंस"
   ],
   "phoneme": "{b1i tEk s1i 1Es 1i}",
   "degree": "B.Tech",
   "branch": "CSE",
   "duration_years": 4,
   "fees_per_year": 165000,
   "seats": 180,
   "intake_open": true,
   "cutoffs": {
    "jee_main": 82.0,
    "cuet": 86.0,
    "university_test": 60.0
   }
  },
  {
   "id": "c03",
   "canonical": "B.Tech Information Technology",
   "aliases": [
    "BTech IT",
    "information technology",
    "IT branch",
    "आईटी"
   ],
   "phoneme": null,
   "degree": "B.Tech",
   "branch": "IT",
   "duration_years": 4,
   "fees_per_year": 155000,
   "seats": 120,
   "intake_open": true,
   "cutoffs": {
    "jee_main": 74.0,
    "cuet": 80.0,
    "university_test": 55.0
   }
  },
  {
   "id": "c04",
   "canonical": "B.Tech Mechanical Engineering",
   "aliases": [
    "BTech mechanical",
    "mechanical",
    "mech branch",
    "mechanical wala",
    "मैकेनिकल"
   ],
   "phoneme": null,
   "degree": "B.Tech",
   "branch": "MECH",
   "duration_years": 4,
   "fees_per_year": 135000,
   "seats": 90,
   "intake_open": true,
   "cutoffs": {
    "jee_main": 58.0,
    "cuet": 65.0,
    "university_test": 45.0
   }
  },
  {
   "id": "c05",
   "canonical": "B.Tech Electronics and Communication Engineering",
   "aliases": [
    "BTech ECE",
    "electronics",
    "ECE branch",
    "electronics and communication",
    "इलेक्ट्रॉनिक्स"
   ],
   "phoneme": null,
   "degree": "B.Tech",
   "branch": "ECE",
   "duration_years": 4,
   "fees_per_year": 145000,
   "seats": 120,
   "intake_open": true,
   "cutoffs": {
    "jee_main": 66.0,
    "cuet": 72.0,
    "university_test": 50.0
   }
  },
  {
   "id": "c06",
   "canonical": "B.Tech Civil Engineering",
   "aliases": [
    "BTech civil",
    "civil",
    "civil branch",
    "सिविल"
   ],
   "phoneme": null,
   "degree": "B.Tech",
   "branch": "CIVIL",
   "duration_years": 4,
   "fees_per_year": 125000,
   "seats": 60,
   "intake_open": false,
   "cutoffs": {
    "jee_main": 52.0,
    "cuet": 60.0,
    "university_test": 42.0
   }
  },
  {
   "id": "c07",
   "canonical": "Bachelor of Computer Applications",
   "aliases": [
    "BCA",
    "bee see aay",
    "computer applications",
    "बीसीए",
    "BCA karna hai",
    "bca course",
    "bca admission"
   ],
   "phoneme": "{b1i s1i 1ey}",
   "degree": "BCA",
   "branch": "BCA",
   "duration_years": 3,
   "fees_per_year": 95000,
   "seats": 120,
   "intake_open": true,
   "cutoffs": {
    "cuet": 58.0,
    "university_test": 40.0
   }
  },
  {
   "id": "c08",
   "canonical": "Master of Business Administration",
   "aliases": [
    "MBA",
    "em bee aay",
    "business administration",
    "एमबीए"
   ],
   "phoneme": "{1Em b1i 1ey}",
   "degree": "MBA",
   "branch": "MBA",
   "duration_years": 2,
   "fees_per_year": 275000,
   "seats": 60,
   "intake_open": true,
   "cutoffs": {
    "cat": 72.0,
    "university_test": 55.0
   }
  }
 ],
 "exams": [
  {
   "id": "jee_main",
   "canonical": "JEE Main",
   "aliases": [
    "mains",
    "jee mains",
    "joint entrance main",
    "जेईई मेन"
   ],
   "phoneme": "{J1i 1i 1i m1eyn}",
   "score_type": "percentile",
   "score_min": 0,
   "score_max": 100
  },
  {
   "id": "cuet",
   "canonical": "CUET UG",
   "aliases": [
    "cuet",
    "see you ee tee",
    "common university entrance test",
    "सीयूईटी"
   ],
   "phoneme": "{s1i y1u 1i t1i}",
   "score_type": "percentile",
   "score_min": 0,
   "score_max": 100
  },
  {
   "id": "cat",
   "canonical": "CAT",
   "aliases": [
    "cat exam",
    "see aay tee",
    "common admission test"
   ],
   "phoneme": "{s1i 1ey t1i}",
   "score_type": "percentile",
   "score_min": 0,
   "score_max": 100
  },
  {
   "id": "university_test",
   "canonical": "University Entrance Test",
   "aliases": [
    "college ka test",
    "university test",
    "own entrance",
    "internal test"
   ],
   "phoneme": null,
   "score_type": "marks",
   "score_min": 0,
   "score_max": 100
  }
 ],
 "faculty": [
  {
   "id": "f01",
   "canonical": "Dr. Shubhangi Chaturvedi",
   "aliases": [
    "chaturvedi maam",
    "shubhangi mam",
    "CS HOD",
    "computer science HOD"
   ],
   "phoneme": "{SU2bh1angi Ca2tUrv1edi}",
   "role": "HOD, Computer Science",
   "handles": [
    "CSE-AIML",
    "CSE"
   ]
  },
  {
   "id": "f02",
   "canonical": "Prof. Rajagopalan Iyer",
   "aliases": [
    "rajagopalan sir",
    "iyer sir",
    "mechanical HOD"
   ],
   "phoneme": "{r1aJ0ag1op0al2an 1ay0Er}",
   "role": "HOD, Mechanical",
   "handles": [
    "MECH"
   ]
  },
  {
   "id": "f03",
   "canonical": "Dr. Ananya Bhattacharya",
   "aliases": [
    "bhattacharya maam",
    "ananya mam",
    "admissions counsellor"
   ],
   "phoneme": "{b h a2 t 0 t A1 C A2 r y A0}",
   "role": "Admissions Counsellor",
   "handles": [
    "ALL"
   ]
  }
 ],
 "campus": [
  {
   "id": "cp01",
   "canonical": "Ghaziabad Campus, Block C",
   "aliases": [
    "block C",
    "main building",
    "ghaziabad campus"
   ],
   "phoneme": "{g1az0iyab1ad}",
   "nearest_metro": "Vaishali",
   "visit_slots": [
    "10:00",
    "12:00",
    "15:00"
   ]
  },
  {
   "id": "cp02",
   "canonical": "Indirapuram Annexe",
   "aliases": [
    "indirapuram",
    "annexe",
    "second campus"
   ],
   "phoneme": "{1ind0ir1apUr0am}",
   "nearest_metro": "Vaishali",
   "visit_slots": [
    "11:00",
    "14:00"
   ]
  }
 ],
 "intents": [
  {
   "id": "i01",
   "label": "eligibility",
   "canonical": "can my son get CSE",
   "aliases": [
    "am I eligible",
    "91 percentile mein admission ho jayega",
    "cutoff cross kiya kya",
    "admission mil jayega",
    "do I qualify",
    "kya mera number aayega"
   ]
  },
  {
   "id": "i02",
   "label": "fees",
   "canonical": "what is the fees",
   "aliases": [
    "kitni fees hai",
    "total cost",
    "fees per year",
    "kitna paisa lagega",
    "how much does it cost",
    "fee structure"
   ]
  },
  {
   "id": "i03",
   "label": "book_visit",
   "canonical": "book a campus visit",
   "aliases": [
    "campus dekhna hai",
    "can we visit",
    "campus tour",
    "college aana hai",
    "visit karna hai",
    "campus ghumna hai"
   ]
  },
  {
   "id": "i04",
   "label": "book_callback",
   "canonical": "book a callback with a counsellor",
   "aliases": [
    "counsellor se baat karani hai",
    "call me back",
    "koi call kare",
    "arrange a call",
    "callback chahiye",
    "baad mein call karo",
    "counsellor call kare",
    "schedule a call"
   ]
  },
  {
   "id": "i05",
   "label": "status",
   "canonical": "application status",
   "aliases": [
    "form ka status",
    "where is my application",
    "status check karna hai",
    "application kahan pahunchi"
   ]
  },
  {
   "id": "i06",
   "label": "course_info",
   "canonical": "tell me about the course",
   "aliases": [
    "what subjects are there",
    "duration kitna hai",
    "course ke bare mein batao",
    "syllabus kya hai",
    "how many years"
   ]
  },
  {
   "id": "i07",
   "label": "human",
   "canonical": "transfer me to a person now",
   "aliases": [
    "kisi se baat karao abhi",
    "connect me to a person",
    "operator",
    "real person se baat",
    "transfer kar do",
    "live agent"
   ]
  }
 ]
}
LANEB_EOF

cat > tests/test_resolve.py << 'LANEB_EOF'
#!/usr/bin/env python3
"""The 30-case test set. Run after EVERY change. Takes two seconds.
This is the only honest way to tune bands. Your pass rate goes on a slide.

    python tests/test_resolve.py
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import ensure_collections, upsert_rows, resolve, route  # noqa

# (spoken text, kind, expected canonical or None if it should be rejected)
CASES = [
    ("AI wala CS course",              "course", "c01"),
    ("btech cse ai ml",                "course", "c01"),
    ("artificial intelligence branch", "course", "c01"),
    ("plain CSE",                      "course", "c02"),
    ("bee tech seeyesee",              "course", "c02"),
    ("computer science",               "course", "c02"),
    ("information technology",         "course", "c03"),
    ("IT branch",                      "course", "c03"),
    ("mechanical branch",              "course", "c04"),
    ("mechanical wala",                "course", "c04"),
    ("electronics and communication",  "course", "c05"),
    ("ECE branch",                     "course", "c05"),
    ("bee see aay",                    "course", "c07"),
    ("BCA karna hai",                  "course", "c07"),
    ("em bee aay",                     "course", "c08"),
    ("business administration",        "course", "c08"),
    ("mains ka score",                 "exam",   "jee_main"),
    ("jee mains",                      "exam",   "jee_main"),
    ("see you ee tee",                 "exam",   "cuet"),
    ("cuet ug",                        "exam",   "cuet"),
    ("college ka test",                "exam",   "university_test"),
    ("chaturvedi maam",                "faculty","f01"),
    ("shubhangi mam",                  "faculty","f01"),
    ("computer science HOD",           "faculty","f01"),
    ("rajagopalan sir",                "faculty","f02"),
    ("bhattacharya maam",              "faculty","f03"),
    ("admissions counsellor",          "faculty","f03"),
    ("block C",                        "campus", "cp01"),
    ("indirapuram",                    "campus", "cp02"),
    ("asdfgh qwerty zxcvb",            "course", None),
]

ROUTE_CASES = [
    ("kya mera number aayega",        "eligibility"),
    ("91 percentile mein ho jayega",  "eligibility"),
    ("kitni fees hai",                "fees"),
    ("how much does it cost",         "fees"),
    ("campus dekhna hai",             "book_visit"),
    ("can we visit the campus",       "book_visit"),
    ("counsellor se baat karani hai", "book_callback"),
    ("form ka status",                "status"),
    ("kitne saal ka course hai",      "course_info"),
    ("kisi se baat karao",            "human"),
]


def setup():
    cat = json.load(open("data/seed_catalog.json"))
    ensure_collections(wipe=True)
    for n in ["courses", "exams", "faculty", "campus", "intents"]:
        upsert_rows(n, cat[n])


def main():
    setup()
    fails = []
    print("=== resolve ===")
    for text, kind, want in CASES:
        r = resolve(text, kind)
        got = r.code if (r and r.band != "reject") else None
        ok = got == want
        if not ok:
            fails.append((text, want, got))
        band = r.band if r else "-"
        sc = f"{r.score:.3f}" if r else "  -  "
        print(f"{'ok ' if ok else 'FAIL'} {text!r:34} -> {str(got):14} {sc} {band}")

    print("\n=== route ===")
    rfails = []
    for text, want in ROUTE_CASES:
        i = route(text)
        ok = i.name == want
        if not ok:
            rfails.append((text, want, i.name))
        print(f"{'ok ' if ok else 'FAIL'} {text!r:34} -> {i.name:14} {i.confidence:.3f}")

    rp = len(CASES) - len(fails)
    ip = len(ROUTE_CASES) - len(rfails)
    print(f"\nresolve {rp}/{len(CASES)}   route {ip}/{len(ROUTE_CASES)}")
    if fails or rfails:
        print("\nfailures:")
        for f in fails + rfails:
            print("  ", f)
    return 0 if not (fails or rfails) else 1


if __name__ == "__main__":
    sys.exit(main())

LANEB_EOF

cat >> .gitignore << 'LANEB_EOF'
.env
*.wav
*.mp3
logs/
*.db
*.sqlite3
__pycache__/
.venv/
LANEB_EOF

cat > .env.example << 'LANEB_EOF'
QDRANT_URL=
QDRANT_API_KEY=
RIME_API_KEY=
DEEPGRAM_API_KEY=
ANTHROPIC_API_KEY=
LANEB_EOF

echo ""
echo "installing deps..."
pip install -q qdrant-client numpy 2>/dev/null \
  || pip install -q --break-system-packages qdrant-client numpy 2>/dev/null \
  || pip install -q --user qdrant-client numpy

echo ""
echo "running tests..."
python tests/test_resolve.py