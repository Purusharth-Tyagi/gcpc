#!/usr/bin/env python3
"""Fix D's catalog: cutoff key mismatches + missing phonemes.

    cd /workspaces/gcpc
    python backfill.py

TWO SILENT FAILURES THIS FIXES

1. cutoffs keyed by a name that is not an exam id. C's eligibility check does
   payload["cutoffs"][exam.code], so a mismatch returns "unknown" for every
   caller — no error, no warning, just an agent that never answers.

2. phoneme: null on every row. The A/B lexicon toggle then produces identical
   audio on both sides, and the "Qdrant decides what you hear" claim has no
   evidence behind it.

Phonemes are applied as phoneme_for + phoneme, so only the tricky SUBSTRING is
replaced. Replacing a whole canonical with a short phoneme makes the agent say
"Ghaziabad" and silently drop "Campus, Block C".
"""
import json, os, shutil, sys

P = sys.argv[1] if len(sys.argv) > 1 else "data/catalog.json"
if not os.path.exists(P):
    print(f"{P} not found — run from the repo root"); sys.exit(1)

cat = json.load(open(P, encoding="utf-8"))
shutil.copy(P, P + ".prebackfill")

# ---------------------------------------------------------------- 1. cutoffs
exam_ids = {e["id"] for e in cat.get("exams", [])}
print("exam ids in catalog:", sorted(exam_ids))

def match_exam(key):
    k = key.lower().replace(" ", "_").replace("-", "_")
    if k in exam_ids:
        return k
    for eid in exam_ids:
        e = eid.lower()
        if e.startswith(k) or k.startswith(e) or k in e or e in k:
            return eid
    return None

fixed = dropped = 0
for c in cat.get("courses", []):
    cuts = c.get("cutoffs") or {}
    new = {}
    for k, v in cuts.items():
        m = match_exam(k)
        if m is None:
            dropped += 1
            continue
        if m != k:
            fixed += 1
        new[m] = v
    c["cutoffs"] = new
print(f"cutoff keys remapped: {fixed}, unmatched dropped: {dropped}")

nulls = [c["id"] for c in cat.get("courses", [])
         if not any(v is not None for v in (c.get("cutoffs") or {}).values())]
if nulls:
    print(f"  !! {len(nulls)} course(s) still have no usable cutoff: {nulls[:10]}")
    print("     eligibility returns 'unknown' for these until D fills numbers")

# --------------------------------------------------------------- 2. phonemes
# substring -> Rime brace phoneme. Longest match wins, so "B.Tech" is tried
# before "Tech". Acronyms first: they break worst and appear most.
# Plain English is left alone — Rime already says "Computer Science and
# Engineering" correctly, and spending the one phoneme slot on it wastes the
# slot. Only ACRONYMS, NAMES and PLACES get overrides: those are what break,
# and they are what a judge notices.
LEX = [
    ("AI & ML",   "{1ey 1ay and 1Em 1El}"),
    ("AI and ML", "{1ey 1ay and 1Em 1El}"),
    ("B.Tech",  "{b1i tEk}"),   ("BTech", "{b1i tEk}"),
    ("M.Tech",  "{1Em tEk}"),   ("MTech", "{1Em tEk}"),
    ("B.Voc",   "{b1i vok}"),
    ("CUET",    "{s1i y1u 1i t1i}"),
    ("JEE",     "{J1i 1i 1i}"),
    ("BCA",     "{b1i s1i 1ey}"),
    ("MBA",     "{1Em b1i 1ey}"),
    ("MCA",     "{1Em s1i 1ey}"),
    ("CSE",     "{s1i 1Es 1i}"),
    ("ECE",     "{1i s1i 1i}"),
    ("NAAC",    "{n1ak}"),
    ("AICTE",   "{1ey 1ay s1i t1i 1i}"),
    ("NIRF",    "{1En 1ay 1ar 1Ef}"),
    # place names
    ("Ghaziabad",   "{g1az0iyab1ad}"),
    ("Indirapuram", "{1ind0ir1apUr0am}"),
    ("Vaishali",    "{va2yS1ali}"),
    ("Meerut",      "{m1ir0Ot}"),
    ("Noida",       "{n1oyd0a}"),
    # surnames — the most emotive demo material
    ("Chaturvedi",   "{Ca2tUrv1edi}"),
    ("Mukherjee",    "{mUk1OrJ0i}"),
    ("Bhattacharya", "{b h a2 t 0 t A1 C A2 r y A0}"),
    ("Rajagopalan",  "{r1aJ0ag1op0al2an}"),
    ("Shubhangi",    "{SU2bh1angi}"),
    ("Ananya",       "{an1any0a}"),
    ("Iyer",         "{1ay0Er}"),
    ("Chaudhary",    "{C1Odh0ari}"),
    ("Upadhyay",     "{Up1adhy0ay}"),
    ("Srivastava",   "{Sr1iv0ast0av0a}"),
]
LEX.sort(key=lambda x: -len(x[0]))

applied = 0
for coll in ("courses", "exams", "faculty", "campus"):
    for r in cat.get(coll, []):
        if r.get("phoneme"):
            continue
        canon = r.get("canonical", "")
        for sub, ph in LEX:
            if sub in canon:
                r["phoneme_for"] = sub
                r["phoneme"] = ph
                applied += 1
                break

total = sum(len(cat.get(k, [])) for k in ("courses", "exams", "faculty", "campus"))
print(f"phonemes applied: {applied}/{total} rows")

missing = [(k, r["id"], r["canonical"]) for k in ("courses", "exams", "faculty", "campus")
           for r in cat.get(k, []) if not r.get("phoneme")]
if missing:
    print(f"  {len(missing)} row(s) still without a phoneme (fine if Rime says them right):")
    for k, i, c in missing[:10]:
        print(f"    {k}/{i}: {c[:52]}")

json.dump(cat, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nbacked up -> {P}.prebackfill")
print(f"wrote {P}")
print("\nnow:  python scripts/ingest.py --catalog data/catalog.json --wipe")
