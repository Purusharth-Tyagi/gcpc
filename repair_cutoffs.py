#!/usr/bin/env python3
"""Restore cutoffs that were dropped, and add the exams they referenced.

    cd /workspaces/gcpc
    python repair_cutoffs.py

The courses referenced exams that are not in the exams list (e.g. "cuet"), so
the earlier pass dropped those cutoffs. That was the wrong call: the courses
are right and the exams list is incomplete. This reads the pre-backfill copy,
restores every cutoff, and CREATES any exam that was referenced but missing.

Also fills phonemes for the degree and exam acronyms the first pass skipped.
"""
import json, os, shutil, sys

P = "data/catalog.json"
PRE = P + ".prebackfill"
if not os.path.exists(P):
    print("run from the repo root"); sys.exit(1)

cat = json.load(open(P, encoding="utf-8"))
orig = json.load(open(PRE, encoding="utf-8")) if os.path.exists(PRE) else None
if orig is None:
    print(f"{PRE} not found — cannot recover the original cutoffs"); sys.exit(1)

# ------------------------------------------------- 1. restore + create exams
KNOWN = {
    "cuet":     ("CUET UG", ["cuet", "see you ee tee", "common university entrance test", "सीयूईटी"],
                 "{s1i y1u 1i t1i}", "CUET", "percentile", 0, 100),
    "cuet_ug":  ("CUET UG", ["cuet", "see you ee tee", "common university entrance test"],
                 "{s1i y1u 1i t1i}", "CUET", "percentile", 0, 100),
    "jee_adv":  ("JEE Advanced", ["advanced", "jee advance", "iit ka exam"],
                 "{J1i 1i 1i}", "JEE", "rank", 1, 250000),
    "neet":     ("NEET UG", ["neet", "medical entrance"],
                 "{n1it}", "NEET", "percentile", 0, 100),
    "cet":      ("State CET", ["state cet", "cet"], None, None, "percentile", 0, 100),
}

exam_ids = {e["id"] for e in cat.get("exams", [])}
orig_courses = {c["id"]: c for c in orig.get("courses", [])}

restored = 0
needed = {}
for c in cat.get("courses", []):
    o = orig_courses.get(c["id"])
    if not o:
        continue
    for k, v in (o.get("cutoffs") or {}).items():
        if k in exam_ids:
            c.setdefault("cutoffs", {})[k] = v
        else:
            needed.setdefault(k, []).append(c["id"])
            c.setdefault("cutoffs", {})[k] = v
            restored += 1

print("exams already present:", sorted(exam_ids))
print("cutoff keys with no exam row:", {k: len(v) for k, v in needed.items()})

created = 0
for k in needed:
    if k in exam_ids:
        continue
    if k in KNOWN:
        canon, al, ph, phf, st, lo, hi = KNOWN[k]
    else:
        canon, al, ph, phf, st, lo, hi = k.replace("_", " ").upper(), [k], None, None, "percentile", 0, 100
    row = {"id": k, "canonical": canon, "aliases": al,
           "score_type": st, "score_min": lo, "score_max": hi}
    if ph:
        row["phoneme"], row["phoneme_for"] = ph, phf
    cat.setdefault("exams", []).append(row)
    exam_ids.add(k)
    created += 1
    print(f"  created exam: {k} -> {canon}")

print(f"restored {restored} cutoff value(s), created {created} exam row(s)")

usable = [c["id"] for c in cat.get("courses", [])
          if any(v is not None for v in (c.get("cutoffs") or {}).values())]
print(f"courses with a usable cutoff: {len(usable)}/{len(cat.get('courses', []))}")

# ------------------------------------------------------ 2. remaining phonemes
LEX = [
    ("Master of Computer Applications", "{1Em s1i 1ey}"),
    ("Bachelor of Computer Applications", "{b1i s1i 1ey}"),
    ("Master of Business Administration", "{1Em b1i 1ey}"),
    ("Environmental Science", "{1Em 1Es s1i}"),
    ("Geoinformatics", "{J1i0o0inf0Orm1at0iks}"),
    ("B.Pharm", "{b1i farm}"), ("D.Pharm", "{d1i farm}"), ("M.Pharm", "{1Em farm}"),
    ("M.Sc.", "{1Em 1Es s1i}"), ("B.Sc.", "{b1i 1Es s1i}"),
    ("Ph.D.", "{p1i 1eyC d1i}"), ("PhD", "{p1i 1eyC d1i}"),
    ("BBA", "{b1i b1i 1ey}"), ("MCA", "{1Em s1i 1ey}"),
    ("CMAT", "{s1i 1Em 1ey t1i}"), ("GMAT", "{J1i 1Em 1ey t1i}"),
    ("XAT", "{1Eks 1ey t1i}"), ("CAT", "{s1i 1ey t1i}"), ("MAT", "{1Em 1ey t1i}"),
]
LEX.sort(key=lambda x: -len(x[0]))

added = 0
for coll in ("courses", "exams", "faculty", "campus"):
    for r in cat.get(coll, []):
        if r.get("phoneme"):
            continue
        for sub, ph in LEX:
            if sub in r.get("canonical", ""):
                r["phoneme_for"], r["phoneme"] = sub, ph
                added += 1
                break
print(f"phonemes added this pass: {added}")

total = sum(len(cat.get(k, [])) for k in ("courses", "exams", "faculty", "campus"))
have = sum(1 for k in ("courses", "exams", "faculty", "campus")
           for r in cat.get(k, []) if r.get("phoneme"))
print(f"phonemes now: {have}/{total}")

shutil.copy(P, P + ".prerepair")
json.dump(cat, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nwrote {P}")
print("now:  python scripts/ingest.py --catalog data/catalog.json --wipe")
