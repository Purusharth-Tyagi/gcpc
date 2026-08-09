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

