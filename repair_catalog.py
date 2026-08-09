#!/usr/bin/env python3
"""Repair a catalog.json whose top-level object was closed too early.

    cd /workspaces/gcpc
    python repair_catalog.py

Symptom:  json.decoder.JSONDecodeError: Extra data
Cause:    each section was generated separately and joined, so the file reads
            ...  ]
            }              <- closes the root object
              "exams": [   <- but the file keeps going
Fix:      turn each of those `] }` boundaries into `],` and close once at the end.

Also reports rows with null cutoffs, because a null cutoff makes the eligibility
check return "unknown" for that course no matter what the caller says.
"""
import json, os, re, shutil, sys

P = sys.argv[1] if len(sys.argv) > 1 else "data/catalog.json"
if not os.path.exists(P):
    print(f"{P} not found — run from the repo root"); sys.exit(1)

raw = open(P, encoding="utf-8").read()

try:
    json.loads(raw)
    print("already valid JSON — nothing to repair")
    sys.exit(0)
except json.JSONDecodeError as e:
    print(f"before: {e}")

# `]` then `}` then a new "key": [   ->   `],` then the key
fixed, n = re.subn(r'\]\s*\}\s*(?=("[\w_]+"\s*:\s*\[))', '],\n  ', raw)
print(f"repaired {n} premature closing brace(s)")

fixed = fixed.rstrip()
# balance the braces: one root object open, so close exactly once
opens, closes = fixed.count("{"), fixed.count("}")
if opens > closes:
    fixed += "\n" + "}" * (opens - closes)
    print(f"appended {opens - closes} closing brace(s)")

try:
    cat = json.loads(fixed)
except json.JSONDecodeError as e:
    print(f"\nSTILL BROKEN: {e}")
    ln = fixed[:e.pos].count("\n") + 1
    print(f"--- around line {ln} ---")
    print("\n".join(fixed.split("\n")[max(0, ln - 6):ln + 6]))
    sys.exit(2)

shutil.copy(P, P + ".bak")
json.dump(cat, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nbacked up -> {P}.bak")
print("repaired ->", {k: len(v) if isinstance(v, list) else "?" for k, v in cat.items()})

# quality warnings — these fail silently at runtime, so surface them now
null_cut = [c["id"] for c in cat.get("courses", [])
            if not any((c.get("cutoffs") or {}).values())]
if null_cut:
    print(f"\n  !! {len(null_cut)} course(s) have all-null cutoffs: {null_cut[:8]}")
    print("     eligibility returns 'unknown' for these — tell D to fill real numbers")

with_ph = sum(1 for k in ("courses", "exams", "faculty", "campus")
              for r in cat.get(k, []) if r.get("phoneme"))
total = sum(len(cat.get(k, [])) for k in ("courses", "exams", "faculty", "campus"))
print(f"  phonemes: {with_ph}/{total} rows")
if with_ph == 0:
    print("  !! NO PHONEMES — the A/B lexicon demo will do nothing")

print("\nnow run:  python scripts/ingest.py --catalog data/catalog.json --wipe")
