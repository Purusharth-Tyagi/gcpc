#!/usr/bin/env python3
"""Pull phonemes from Qdrant, synthesise each term with and without the
override, write wav pairs to listen to.

This is three things at once:
  1. A's go/no-go spike, but against OUR real catalog terms
  2. D's pronunciation bench for triaging which terms need work
  3. The exact mechanism behind the A/B demo toggle

    export RIME_API_KEY=...
    python scripts/phoneme_bench.py --model mistv3 --speaker <voice>
    python scripts/phoneme_bench.py --all-models        # which model honours overrides

Outputs to bench/off_*.wav and bench/on_*.wav. Listen to the pairs.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from retrieval.store import client, COLLECTIONS  # noqa: E402

RIME_URL = "https://users.rime.ai/v1/rime-tts"
CONTENT = ["courses", "exams", "faculty", "campus"]

# Sentences that put the term where it actually lands in the demo.
FRAMES = {
    "courses":  "You asked about {}. Shall I check eligibility?",
    "exams":    "I have your {} score. Let me check the cutoff.",
    "faculty":  "{} will call you back this evening.",
    "campus":   "The visit is at {}. Does that work?",
}


def terms_with_phonemes(limit_per_collection=20):
    """Read straight from Qdrant, deduped by row code."""
    out = []
    for coll in CONTENT:
        seen = set()
        points, _ = client.scroll(coll, limit=500, with_payload=True)
        for p in points:
            pl = p.payload
            code = pl.get("code")
            if code in seen or not pl.get("phoneme"):
                continue
            seen.add(code)
            out.append({"collection": coll, "code": code,
                        "canonical": pl["canonical"], "phoneme": pl["phoneme"]})
            if len(seen) >= limit_per_collection:
                break
    return out


def synth(text, model, speaker, out_path, lang="eng"):
    r = requests.post(
        RIME_URL,
        headers={"Authorization": f"Bearer {os.environ['RIME_API_KEY']}",
                 "Accept": "audio/wav"},
        json={"text": text, "speaker": speaker, "modelId": model,
              "phonemizeBetweenBrackets": True, "lang": lang},
        timeout=30,
    )
    r.raise_for_status()
    open(out_path, "wb").write(r.content)
    return len(r.content)


def run(model, speaker, terms, outdir):
    os.makedirs(outdir, exist_ok=True)
    same = 0
    for t in terms:
        frame = FRAMES[t["collection"]]
        base = f"{outdir}/{t['collection']}_{t['code']}"
        n_off = synth(frame.format(t["canonical"]), model, speaker, base + "_OFF.wav")
        n_on = synth(frame.format(t["phoneme"]), model, speaker, base + "_ON.wav")
        # identical byte length is a strong hint the override was ignored
        flag = "  <-- IDENTICAL SIZE, override likely ignored" if n_off == n_on else ""
        if n_off == n_on:
            same += 1
        print(f"  {t['code']:14} {t['canonical'][:44]:46} {n_off:>8} / {n_on:>8}{flag}")
    print(f"\n  {model}: {len(terms)-same}/{len(terms)} terms changed when phonemes applied")
    return same < len(terms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mistv3")
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--all-models", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    a = ap.parse_args()

    terms = terms_with_phonemes(a.limit)
    if not terms:
        print("No phonemes in Qdrant. Run ingest.py first, and check D has "
              "filled the phoneme field — nulls everywhere means no A/B demo.")
        return 1
    print(f"{len(terms)} terms with phonemes\n")

    models = ["mistv3", "mistv2", "coda"] if a.all_models else [a.model]
    results = {}
    for m in models:
        print(f"=== {m} ===")
        try:
            results[m] = run(m, a.speaker, terms, f"bench/{m}")
        except Exception as e:
            print(f"  {m} failed: {type(e).__name__}: {str(e)[:120]}")
            results[m] = False
        print()

    print("=== VERDICT ===")
    for m, ok in results.items():
        print(f"  {m:8} {'honours phoneme overrides' if ok else 'IGNORES or failed'}")
    working = [m for m, ok in results.items() if ok]
    if working:
        print(f"\n  PIN THIS MODEL: {working[0]}")
    else:
        print("\n  No model honoured overrides. Team pivots to Plan B NOW.")
    print("\n  Byte-size differences are only a hint. LISTEN to a few pairs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
