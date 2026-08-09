#!/usr/bin/env python3
"""H8 GATE. Runs the full path end to end and prints every stage.

    python scripts/smoke.py
    python scripts/smoke.py --catalog data/catalog.json

Lane B is real. A and C are stubbed here with the MINIMUM logic their real
code must implement. When their code lands, swap the two marked functions
and nothing else changes.

If this script is green, the H8 gate is met.
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import (ensure_collections, upsert_rows, resolve, route,  # noqa
                             remember, recall)

# ---------------------------------------------------------------- LANE A stub
def inject_phonemes(text, resolutions, lexicon_on=True):
    """A replaces this. NOTE: replaces phoneme_for, NOT canonical."""
    if not lexicon_on:
        return text
    for r in sorted([x for x in resolutions if x and x.phoneme],
                    key=lambda x: -len(x.phoneme_for or x.canonical)):
        target = r.phoneme_for or r.canonical
        text = text.replace(target, r.phoneme)
    return text


# ---------------------------------------------------------------- LANE C stub
def eligibility(course, exam, score):
    """C replaces this. The four-condition guardrail is NOT optional."""
    if not course or course.band != "accept":
        return "unknown", None
    if not exam or exam.band != "accept":
        return "unknown", None
    if score is None:
        return "unknown", None
    lo, hi = exam.payload.get("score_min", 0), exam.payload.get("score_max", 100)
    if not (lo <= score <= hi):
        return "unknown", None
    cutoff = (course.payload.get("cutoffs") or {}).get(exam.code)
    if cutoff is None:
        return "unknown", None
    if score >= cutoff + 3:
        return "likely", cutoff
    if score >= cutoff:
        return "borderline", cutoff
    return "below", cutoff


def parse_score(text):
    import re
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(?:percentile|percent|%|marks)?", text)
    return float(m.group(1)) if m else None


def turn(utterance, phone="+919812345678", lexicon_on=True):
    t0 = time.perf_counter()
    intent = route(utterance);              t_route = time.perf_counter()
    course = resolve(utterance, "course");  t_course = time.perf_counter()
    exam = resolve(utterance, "exam");      t_exam = time.perf_counter()
    score = parse_score(utterance)
    verdict, cutoff = eligibility(course, exam, score)
    facts = recall(phone, context=utterance, k=2)

    # ORDER MATTERS. Availability first: a closed course has a real answer
    # ("it's closed"), and checking eligibility first buries it under
    # "I can't answer that". C: keep this order.
    if course and course.band == "accept" and not course.payload.get("intake_open", True):
        reply = (f"{course.canonical} intake is closed this year. "
                 f"Shall I tell you about another branch?")
    elif verdict == "unknown":
        reply = ("I don't want to give you a wrong answer on that. "
                 "Let me have a counsellor confirm it. Shall I book a callback?")
    else:
        word = {"likely": "comfortably above", "borderline": "just at",
                "below": "below"}[verdict]
        reply = (f"For {course.canonical}, the {exam.canonical} cutoff is "
                 f"{cutoff}. Your score is {word} it.")

    spoken = inject_phonemes(reply, [course, exam], lexicon_on)

    print(f'\n  caller: "{utterance}"')
    print(f"    intent    {intent.name:14} {intent.confidence:.3f}   "
          f"{(t_route-t0)*1000:.1f}ms")
    print(f"    course    {(course.code if course else '-'):14} "
          f"{(course.band if course else '-'):8} {(t_course-t_route)*1000:.1f}ms  "
          f"{course.canonical if course else ''}")
    print(f"    exam      {(exam.code if exam else '-'):14} "
          f"{(exam.band if exam else '-'):8} {(t_exam-t_course)*1000:.1f}ms  "
          f"{exam.canonical if exam else ''}")
    print(f"    score     {score}")
    print(f"    verdict   {verdict} (cutoff {cutoff})")
    if facts:
        print(f"    memory    {facts}")
    print(f"    SAY       {spoken}")
    print(f"    total     {(time.perf_counter()-t0)*1000:.1f}ms (Qdrant + logic only)")
    return spoken


CASES = [
    "my son got 91 percentile in JEE Main can he get CSE AI ML",
    "mechanical branch mein 60 percentile se ho jayega",
    "civil engineering ke bare mein batao",
    "AI wala course ki fees kitni hai",
    "counsellor se baat karani hai",
    "what is the weather today",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/seed_catalog.json")
    a = ap.parse_args()

    cat = json.load(open(a.catalog))
    ensure_collections(wipe=True)
    for n in ["courses", "exams", "faculty", "campus", "intents"]:
        upsert_rows(n, cat[n])
    remember("+919812345678", "asking about B.Tech CSE AI-ML for her son Aryan")
    remember("+919812345678", "concerned about fees, asked about instalments")

    print("=" * 74)
    print("H8 GATE — full path (Lane B real, A and C stubbed)")
    print("=" * 74)
    for c in CASES:
        turn(c)

    print("\n" + "=" * 74)
    print("A/B TOGGLE — the demo moment (same sentence, lexicon off then on)")
    print("=" * 74)
    u = "campus visit at Ghaziabad with Dr. Shubhangi Chaturvedi"
    campus = resolve("ghaziabad campus block c", "campus")
    fac = resolve("chaturvedi maam", "faculty")
    line = (f"Your visit is at {campus.canonical} with {fac.canonical}.")
    print(f"\n  OFF: {inject_phonemes(line, [campus, fac], False)}")
    print(f"  ON : {inject_phonemes(line, [campus, fac], True)}")
    print("\n  ^ if these two lines are identical, phonemes are missing "
          "from the catalog and the demo does nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())

