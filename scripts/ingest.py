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

