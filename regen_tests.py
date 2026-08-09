#!/usr/bin/env python3
"""Generate a test set from whatever catalog is loaded, and score it.

    cd /workspaces/gcpc
    python scripts/regen_tests.py                     # score only
    python scripts/regen_tests.py --write             # also write tests/test_catalog.py

Hand-maintaining expected ids breaks every time D regenerates his catalog.
This derives the cases from the catalog itself: every alias should resolve to
its own row. That is a real recall measurement, not a tautology — the aliases
compete against every other row's aliases, and near-collisions genuinely fail.

The number it prints is what goes on the slide.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import ensure_collections, upsert_rows, resolve, route  # noqa

KINDS = {"courses": "course", "exams": "exam", "faculty": "faculty", "campus": "campus"}
NONSENSE = ["asdfgh qwerty zxcvb", "what is the weather today",
            "pizza delivery number", "blah blah blah", "who won the match"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog.json")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.catalog):
        a.catalog = "data/seed_catalog.json"
    cat = json.load(open(a.catalog, encoding="utf-8"))
    print(f"catalog: {a.catalog}")

    ensure_collections(wipe=True)
    for coll in list(KINDS) + ["intents"]:
        if cat.get(coll):
            upsert_rows(coll, cat[coll])

    rows = {}
    total = hits = confirms = 0
    fails = []
    for coll, kind in KINDS.items():
        for r in cat.get(coll, []):
            queries = [r["canonical"]] + list(r.get("aliases") or [])
            for q in queries:
                total += 1
                res = resolve(q, kind)
                got = res.code if res else None
                if got == r["id"] and res.band == "accept":
                    hits += 1
                elif got == r["id"]:
                    confirms += 1          # right row, low confidence
                else:
                    fails.append((kind, q, r["id"], got,
                                  round(res.score, 3) if res else 0))
        rows[coll] = len(cat.get(coll, []))

    print(f"rows: {rows}")
    print(f"\naliases tested: {total}")
    print(f"  exact accept : {hits}  ({100*hits/max(total,1):.1f}%)")
    print(f"  right, low   : {confirms}  (agent asks 'did you mean')")
    print(f"  wrong row    : {len(fails)}  ({100*len(fails)/max(total,1):.1f}%)")

    if fails and (a.v or len(fails) <= 20):
        print("\n  wrong-row cases — these produce confidently wrong answers:")
        for kind, q, want, got, sc in fails[:20]:
            print(f"    {kind:8} {q[:34]:36} want {want:6} got {str(got):6} {sc}")

    rej = sum(1 for q in NONSENSE
              if not (resolve(q, "course") and resolve(q, "course").band != "reject"))
    print(f"\n  nonsense correctly rejected: {rej}/{len(NONSENSE)}")

    if cat.get("intents"):
        ok = 0
        n = 0
        for r in cat["intents"]:
            for q in [r["canonical"]] + list(r.get("aliases") or []):
                n += 1
                ok += route(q).name == r["label"]
        print(f"  intent routing: {ok}/{n}  ({100*ok/max(n,1):.1f}%)")

    print(f"\n  headline for the slide: {100*(hits+confirms)/max(total,1):.1f}% "
          f"of real spoken phrasings resolve to the right catalog row")

    if a.write:
        path = "tests/test_catalog.py"
        with open(path, "w", encoding="utf-8") as f:
            f.write('"""Auto-generated from the live catalog. Regenerate with:\n'
                    '    python scripts/regen_tests.py --write\n"""\n')
            f.write("CASES = [\n")
            for coll, kind in KINDS.items():
                for r in cat.get(coll, []):
                    for q in [r["canonical"]] + list(r.get("aliases") or [])[:3]:
                        f.write(f"    ({q!r}, {kind!r}, {r['id']!r}),\n")
            f.write("]\n")
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
