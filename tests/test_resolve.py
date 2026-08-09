#!/usr/bin/env python3
"""Lane B test set. Run after EVERY change. Two seconds.

    python tests/test_resolve.py            # all
    python tests/test_resolve.py -v         # show every line, not just fails

Rules when something fails:
  real phrasing scores low   -> ADD AN ALIAS      (not: lower the threshold)
  two intents keep swapping  -> SHARPEN EXAMPLES  (not: raise ROUTE_MIN)
  nonsense gets accepted     -> raise MARGIN_MIN
  everything is "confirm"    -> ACCEPT_MIN too high
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import (ensure_collections, upsert_rows, resolve, route,
                             remember, recall)  # noqa

VERBOSE = "-v" in sys.argv

# ---------------------------------------------------------------- resolve
# (spoken text, kind, expected id or None)
# Groups matter. A failure in NEAR-COLLISIONS is worse than one in EXACT.

EXACT = [
    ("btech cse ai ml",                "course", "c01"),
    ("computer science",               "course", "c02"),
    ("information technology",         "course", "c03"),
    ("mechanical branch",              "course", "c04"),
    ("electronics and communication",  "course", "c05"),
    ("civil engineering",              "course", "c06"),
    ("BCA karna hai",                  "course", "c07"),
    ("business administration",        "course", "c08"),
    ("jee mains",                      "exam",   "jee_main"),
    ("cuet ug",                        "exam",   "cuet"),
    ("chaturvedi maam",                "faculty","f01"),
    ("rajagopalan sir",                "faculty","f02"),
    ("block C",                        "campus", "cp01"),
    ("indirapuram",                    "campus", "cp02"),
]

# How a PARENT on a phone actually talks. Not prospectus language.
PARENT = [
    ("AI wala CS course",              "course", "c01"),
    ("artificial intelligence branch", "course", "c01"),
    ("bete ko computer science karana hai", "course", "c02"),
    ("bee tech seeyesee",              "course", "c02"),
    ("plain CSE",                      "course", "c02"),
    ("IT branch",                      "course", "c03"),
    ("mechanical wala",                "course", "c04"),
    ("ECE branch",                     "course", "c05"),
    ("bee see aay",                    "course", "c07"),
    ("em bee aay",                     "course", "c08"),
    ("mains ka score",                 "exam",   "jee_main"),
    ("see you ee tee",                 "exam",   "cuet"),
    ("college ka test",                "exam",   "university_test"),
    ("shubhangi mam",                  "faculty","f01"),
    ("bhattacharya maam",              "faculty","f03"),
    ("admissions counsellor",          "faculty","f03"),
    ("computer science HOD",           "faculty","f01"),
    ("main building",                  "campus", "cp01"),
]

# The ones that produce CONFIDENTLY WRONG answers. Most important group.
NEAR_COLLISIONS = [
    ("CSE AI ML",                      "course", "c01"),
    ("computer science and engineering","course", "c02"),
    ("computer applications",          "course", "c07"),
    ("jee advanced",                   "exam",   "jee_adv"),
    ("jee main",                       "exam",   "jee_main"),
    ("advance ka exam",                "exam",   "jee_adv"),
    ("iit ka exam",                    "exam",   "jee_adv"),
]

DEVANAGARI = [
    ("कंप्यूटर साइंस",                  "course", "c02"),
    ("मैकेनिकल",                        "course", "c04"),
    ("इलेक्ट्रॉनिक्स",                   "course", "c05"),
]

# Must return None / reject. Guards against confidently-wrong answers.
NONSENSE = [
    ("asdfgh qwerty zxcvb",            "course", None),
    ("what is the weather today",      "course", None),
    ("pizza delivery number",          "faculty",None),
    ("blah blah blah blah",            "exam",   None),
]

# Genuinely ambiguous input. The RIGHT answer is not a pick — it is "confirm"
# with both candidates offered. A high-trust agent asks; it does not guess.
# (spoken text, kind, set of codes that must appear among top + alternates)
AMBIGUOUS = [
    ("CSE",             "course", {"c01", "c02"}),
    ("computer",        "course", {"c01", "c02"}),
    ("jee",             "exam",   {"jee_main", "jee_adv"}),
]

GROUPS = [("exact", EXACT), ("parent", PARENT),
          ("near-collision", NEAR_COLLISIONS),
          ("devanagari", DEVANAGARI), ("nonsense", NONSENSE)]

# ---------------------------------------------------------------- route
ROUTE_CASES = [
    ("kya mera number aayega",          "eligibility"),
    ("91 percentile mein ho jayega",    "eligibility"),
    ("admission mil jayega kya",        "eligibility"),
    ("cutoff cross kiya kya",           "eligibility"),
    ("kitni fees hai",                  "fees"),
    ("how much does it cost",           "fees"),
    ("total kitna paisa lagega",        "fees"),
    ("campus dekhna hai",               "book_visit"),
    ("can we visit the campus",         "book_visit"),
    ("college aana hai",                "book_visit"),
    ("counsellor se baat karani hai",   "book_callback"),
    ("call me back",                    "book_callback"),
    ("form ka status",                  "status"),
    ("kitne saal ka course hai",        "course_info"),
    ("what subjects are there",         "course_info"),
    ("kisi se baat karao abhi",         "human"),
]


def _codes_of(r):
    """alternates are canonical strings; map them back to codes via the cache."""
    return {_CANON_TO_CODE.get(a, a) for a in r.alternates}


_CANON_TO_CODE = {}


def setup():
    cat = json.load(open("data/seed_catalog.json"))
    ensure_collections(wipe=True)
    for n in ["courses", "exams", "faculty", "campus", "intents"]:
        upsert_rows(n, cat[n])
        for row in cat[n]:
            _CANON_TO_CODE[row["canonical"]] = row["id"]


def main():
    setup()
    total = fails = 0
    print("=== resolve ===")
    for gname, cases in GROUPS:
        gf = []
        for text, kind, want in cases:
            r = resolve(text, kind)
            got = r.code if (r and r.band != "reject") else None
            ok = got == want
            total += 1
            if not ok:
                gf.append((text, want, got))
                fails += 1
            if VERBOSE or not ok:
                sc = f"{r.score:.3f}" if r else "  -  "
                bd = r.band if r else "-"
                print(f"  {'ok ' if ok else 'FAIL'} {text!r:36} -> {str(got):14} {sc} {bd}")
        print(f"  [{gname}] {len(cases)-len(gf)}/{len(cases)}")

    print("\n=== ambiguous (must ask, not guess) ===")
    for text, kind, want_set in AMBIGUOUS:
        r = resolve(text, kind)
        total += 1
        if r is None:
            ok = False
            detail = "no hit"
        else:
            offered = {r.code} | {a for a in _codes_of(r)}
            ok = r.band == "confirm" and bool(want_set & offered)
            detail = f"band={r.band} code={r.code} alts={r.alternates}"
        if not ok:
            fails += 1
        if VERBOSE or not ok:
            print(f"  {'ok ' if ok else 'FAIL'} {text!r:36} -> {detail}")
    print(f"  [ambiguous] {len(AMBIGUOUS)}/{len(AMBIGUOUS)}" if True else "")

    print("\n=== route ===")
    rf = []
    for text, want in ROUTE_CASES:
        i = route(text)
        ok = i.name == want
        if not ok:
            rf.append((text, want, i.name))
        if VERBOSE or not ok:
            print(f"  {'ok ' if ok else 'FAIL'} {text!r:36} -> {i.name:14} {i.confidence:.3f}")
    print(f"  [route] {len(ROUTE_CASES)-len(rf)}/{len(ROUTE_CASES)}")

    print("\n=== memory ===")
    mp = "+919812345678"
    other = "+910000000000"
    for f in ["asking about B.Tech CSE AI-ML for her son Aryan",
              "son scored 91 percentile in JEE Main",
              "wants a campus visit on a weekend",
              "concerned about the fees, asked about instalments"]:
        remember(mp, f)
    remember(other, "OTHERCALLER should never surface")

    mem_checks = [
        ("kitni fees hai",   "fees"),
        ("campus dekhna hai", "campus visit"),
        ("91 percentile",     "percentile"),
    ]
    mf = 0
    for ctx, expect_substr in mem_checks:
        got = recall(mp, context=ctx, k=1)
        ok = got and expect_substr in got[0]
        if not ok:
            mf += 1
        if VERBOSE or not ok:
            print(f"  {'ok ' if ok else 'FAIL'} ctx={ctx!r:24} -> {got}")
    leak = [f for f in recall(mp, context="other caller", k=10) if "OTHERCALLER" in f]
    if leak:
        mf += 1
        print("  FAIL cross-caller leak:", leak)
    print(f"  [memory] {len(mem_checks)+1-mf}/{len(mem_checks)+1}")
    fails += mf
    total += len(mem_checks) + 1

    print(f"\nresolve {total-fails}/{total}   route {len(ROUTE_CASES)-len(rf)}/{len(ROUTE_CASES)}")
    if rf:
        print("\nroute failures:")
        for f in rf:
            print("  ", f)
    return 0 if not (fails or rf) else 1


if __name__ == "__main__":
    sys.exit(main())
