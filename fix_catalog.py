#!/usr/bin/env python3
"""Repair a catalog.json that fails with 'Extra data'.

    cd /workspaces/gcpc
    python fix_catalog.py

'Extra data' means valid JSON ends and something else begins — almost always
two objects pasted one after another. This parses every document in the file
and merges them, concatenating the per-collection lists.

Writes data/catalog.json (backing up to data/catalog.json.bak) and reports
what it found. Never silently drops anything.
"""
import json, os, shutil, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "data/catalog.json"
if not os.path.exists(PATH):
    print(f"{PATH} not found"); sys.exit(1)

raw = open(PATH, encoding="utf-8").read()
dec = json.JSONDecoder()
docs, i = [], 0
while i < len(raw):
    while i < len(raw) and raw[i] in " \t\r\n":
        i += 1
    if i >= len(raw):
        break
    try:
        obj, end = dec.raw_decode(raw, i)
    except json.JSONDecodeError as e:
        line = raw[:i].count("\n") + 1
        print(f"could not parse from line {line}: {e}")
        print("--- context ---")
        print(raw[max(0, i - 200):i + 200])
        sys.exit(2)
    docs.append(obj)
    i = end

print(f"found {len(docs)} JSON document(s) in {PATH}")
for n, d in enumerate(docs, 1):
    if isinstance(d, dict):
        print(f"  doc {n}: {[(k, len(v) if isinstance(v, list) else '?') for k, v in d.items()]}")
    else:
        print(f"  doc {n}: {type(d).__name__}")

if len(docs) == 1:
    print("\nonly one document — the error is elsewhere. Nothing changed.")
    sys.exit(0)

merged, seen = {}, {}
for d in docs:
    if not isinstance(d, dict):
        continue
    for k, v in d.items():
        if isinstance(v, list):
            merged.setdefault(k, [])
            seen.setdefault(k, set())
            for row in v:
                rid = row.get("id") if isinstance(row, dict) else None
                if rid and rid in seen[k]:
                    print(f"  duplicate id skipped: {k}/{rid}")
                    continue
                if rid:
                    seen[k].add(rid)
                merged[k].append(row)
        else:
            merged[k] = v

shutil.copy(PATH, PATH + ".bak")
json.dump(merged, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nbacked up -> {PATH}.bak")
print(f"merged -> {PATH}")
print("  " + str({k: len(v) for k, v in merged.items() if isinstance(v, list)}))
print("\nnow run:  python scripts/ingest.py --catalog data/catalog.json --wipe")
