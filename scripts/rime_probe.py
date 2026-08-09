#!/usr/bin/env python3
"""Find a speaker name that actually works on your pinned Rime model.

    export RIME_API_KEY=...
    python scripts/rime_probe.py                 # probe mistv2
    python scripts/rime_probe.py --model mistv3

Voice names do NOT carry across Rime models — a speaker valid on one model
returns 400 "Speaker 'x' not found in any backend speaker map" on another.
This tries the live catalog first, then falls back to probing candidates.
"""
import argparse, json, os, sys, urllib.request, urllib.error

KEY = os.getenv("RIME_API_KEY")
if not KEY:
    print("set RIME_API_KEY first"); sys.exit(1)

CATALOG_URLS = [
    "https://docs.rime.ai/data/voices/all-v2.json",
    "https://users.rime.ai/data/voices/all-v2.json",
]

# Rime's mist-family voices are named after natural features. Probe order is a
# guess; the catalog above is authoritative when reachable.
CANDIDATES = ["marsh", "brook", "flower", "spore", "lagoon", "tide", "glacier",
              "gulch", "alpine", "delta", "narrow", "ridge", "rill", "cove",
              "abbie", "allison", "ana", "antoine", "armon", "brenda", "brittany",
              "carol", "colin", "courtney", "elena", "elliot", "eva", "geoff",
              "gerald", "helen", "hera", "jen", "joe", "joy", "juan", "lauren",
              "lena", "lisa", "lily", "madison", "marissa", "marta", "maya",
              "nicholas", "nyles", "phil", "reba", "rex", "rick", "ritu",
              "rob", "rodney", "rohan", "rosco", "samantha", "sandy", "selena",
              "seth", "sharon", "stan", "tamra", "tanya", "tibur", "tj",
              "tyler", "viv", "yadira"]


def try_catalog():
    for url in CATALOG_URLS:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return url, json.loads(r.read())
        except Exception:
            continue
    return None, None


def speak_ok(model, speaker, lang="eng"):
    body = json.dumps({"text": "test", "speaker": speaker, "modelId": model,
                       "lang": lang}).encode()
    req = urllib.request.Request(
        "https://users.rime.ai/v1/rime-tts", data=body,
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Accept": "audio/wav"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, len(r.read())
    except urllib.error.HTTPError as e:
        return False, e.read()[:120].decode(errors="ignore")
    except Exception as e:
        return False, str(e)[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mistv2")
    ap.add_argument("--stop-after", type=int, default=3)
    a = ap.parse_args()

    url, cat = try_catalog()
    if cat:
        print(f"catalog: {url}")
        try:
            names = cat.get(a.model) or cat.get("voices", {}).get(a.model)
            if names:
                print(f"  {a.model} voices from catalog: {list(names)[:20]}")
        except Exception:
            print(f"  (catalog shape unexpected — probing instead)")
    else:
        print("catalog unreachable — probing candidates")

    print(f"\nprobing {a.model} ...")
    working = []
    for s in CANDIDATES:
        ok, info = speak_ok(a.model, s)
        if ok:
            print(f"  OK   {s:12} ({info} bytes)")
            working.append(s)
            if len(working) >= a.stop_after:
                break
        elif "not found in any backend speaker map" not in str(info):
            print(f"  ??   {s:12} {info}")   # a different error is worth seeing

    print("\n=== RESULT ===")
    if working:
        print(f"  working speakers on {a.model}: {working}")
        print(f"\n  put this in .env:")
        print(f"    RIME_MODEL={a.model}")
        print(f"    RIME_SPEAKER={working[0]}")
    else:
        print(f"  no candidate worked on {a.model}.")
        print("  Check the voice list in the Rime dashboard for this model.")


if __name__ == "__main__":
    main()
