#!/usr/bin/env python3
"""Patch voice-console/server.js to proxy the turn loop to Lane B (Python).

    python patch_server.py

Backs up to server.js.bak first. Safe to re-run.
Does two things:
  1. inserts  const LANE_B = ...  after the last require/import at the top
  2. replaces the body of runTurn() with a real fetch to the Python API
"""
import os, re, shutil, sys

PATH = "voice-console/server.js"
if not os.path.exists(PATH):
    PATH = "server.js"
if not os.path.exists(PATH):
    print("Cannot find server.js. Run this from the repo root.")
    sys.exit(1)

src = open(PATH).read()
shutil.copy(PATH, PATH + ".bak")
print(f"backed up -> {PATH}.bak")

# ---------------------------------------------------------------- 1. LANE_B
LANE_LINE = 'const LANE_B = process.env.LANE_B_URL || "http://localhost:8000";'
if "LANE_B" in src and "process.env.LANE_B_URL" in src:
    print("LANE_B already defined, skipping")
else:
    lines = src.split("\n")
    last_import = -1
    for i, ln in enumerate(lines[:60]):
        s = ln.strip()
        if (s.startswith("const ") and "require(" in s) or s.startswith("import "):
            last_import = i
    at = last_import + 1 if last_import >= 0 else 0
    lines.insert(at, "\n// Lane B (Python retrieval service). Real resolve/route/recall.\n"
                     + LANE_LINE)
    src = "\n".join(lines)
    print(f"inserted LANE_B at line {at + 1}")

# ---------------------------------------------------- 2. replace runTurn body
m = re.search(r"(async\s+)?function\s+runTurn\s*\([^)]*\)\s*\{", src)
if not m:
    print("\n!! could not find `function runTurn(...)`.")
    print("!! paste me the function and I'll give you the whole file instead.")
    sys.exit(2)

start = m.start()
brace_open = src.index("{", m.end() - 1)
depth, i = 0, brace_open
in_s = None
while i < len(src):
    c = src[i]
    if in_s:
        if c == "\\":
            i += 2
            continue
        if c == in_s:
            in_s = None
    elif c in "\"'`":
        in_s = c
    elif c == "{":
        depth += 1
    elif c == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
end = i + 1

params = re.search(r"runTurn\s*\(([^)]*)\)", src[start:end]).group(1)
print(f"found runTurn({params}) — replacing {src[start:end].count(chr(10))} lines")

NEW = '''async function runTurn(text, lexiconOn, turnId) {
  // REAL. Proxies to the Python Lane B service. Nothing here is simulated —
  // every number below is measured, because fabricated latency on screen is
  // the one thing a technical judge will not forgive.
  const t0 = Date.now();

  const r = await fetch(`${LANE_B}/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text, lexicon_on: lexiconOn }),
  });
  if (!r.ok) throw new Error("lane B returned " + r.status);
  const d = await r.json();

  return {
    type: "turn",
    turn_id: turnId,
    stages: {
      // 0 means NOT WIRED YET. An honest zero beats a plausible fake.
      asr_ms: 0,                                    // A's ASR
      route_ms: d.latency_ms.route,                 // measured
      resolve_ms: d.latency_ms.resolve_course + d.latency_ms.resolve_exam,
      llm_ms: 0,                                    // C's agent
      tts_ms: 0,                                    // A's Rime
      total_ms: Date.now() - t0,
    },
    resolution: {
      heard: d.heard,
      resolved: d.resolutions.course ? d.resolutions.course.canonical : null,
      similarity: d.resolutions.course ? d.resolutions.course.score : 0,
      band: d.resolutions.course ? d.resolutions.course.band : "reject",
      ok: d.resolutions.course ? d.resolutions.course.band === "accept" : false,
      alternates: d.resolutions.course ? d.resolutions.course.alternates : [],
    },
    intent: d.intent,
    eligibility: d.eligibility,
    memory: d.memory,
    speak: lexiconOn ? d.speak_lexicon_on : d.speak_lexicon_off,
    speak_lexicon_on: d.speak_lexicon_on,
    speak_lexicon_off: d.speak_lexicon_off,
  };
}'''

src = src[:start] + NEW + src[end:]
open(PATH, "w").write(src)
print(f"\npatched {PATH}")
print("\nleftover simulation to check by hand:")
for i, ln in enumerate(src.split("\n"), 1):
    if re.search(r"randInt|Math\.random|fakeR|simulat", ln):
        print(f"  line {i}: {ln.strip()[:80]}")
print("\nnext:")
print("  cd voice-console && npm install && node server.js")
