#!/usr/bin/env python3
"""Rerunnable Qdrant loader. D will hand you three revised catalogs overnight.

    python scripts/ingest.py --wipe
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import (ensure_collections, upsert_rows, client,
                             verify_indexes)   # noqa: E402

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
    # phoneme_for must be a substring of canonical, or A's injection is a no-op
    # (silent) or eats the rest of the name (worse, and only audible on stage).
    ph_bad = []
    for coll in CONTENT:
        for r in cat.get(coll, []):
            if r.get("phoneme"):
                target = r.get("phoneme_for") or r["canonical"]
                if target not in r["canonical"]:
                    ph_bad.append((r["id"], target, r["canonical"]))
    if ph_bad:
        print("\n  !! phoneme_for is not a substring of canonical:")
        for i, t, c_ in ph_bad:
            print(f"       {i}: {t!r} not in {c_!r}")
        print("  !! tell D — the phoneme will not be applied")

    with_ph = sum(1 for coll in CONTENT for r in cat.get(coll, []) if r.get("phoneme"))
    total_rows = sum(len(cat.get(coll, [])) for coll in CONTENT)
    print(f"\n  phonemes: {with_ph}/{total_rows} rows")
    if with_ph == 0:
        print("  !! NO PHONEMES AT ALL — the A/B demo toggle will do nothing")

    exam_ids = {e["id"] for e in cat.get("exams", [])}
    bad = [(c["id"], k) for c in cat.get("courses", [])
           for k in c.get("cutoffs", {}) if k not in exam_ids]
    if bad:
        print("\n  !! cutoff keys with no matching exam id:", bad)
        print("  !! tell D now — C's eligibility check will silently return 'unknown'")

    from retrieval.store import is_local_mode
    missing = verify_indexes()
    if is_local_mode():
        print("\n  payload indexes: skipped (in-memory mode does not enforce them)")
    elif missing:
        print("\n  !! MISSING PAYLOAD INDEXES:", ", ".join(missing))
        print("  !! filtered searches and recall() will fail with 400 on a real server")
    else:
        print("\n  payload indexes: ok")

    print(f"\ningested in {time.time()-t0:.2f}s")


if __name__ == "__main__":
    main()
