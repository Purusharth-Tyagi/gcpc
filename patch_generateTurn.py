#!/usr/bin/env python3
"""Replace the mock generateTurn() in voice-console/server.js with a real call
to the Python Lane B service. Preserves the exact return contract, so the
websocket broadcast, logs/turns.jsonl, and the frontend all keep working.

    python patch2.py
"""
import os, re, shutil, sys

PATH = "voice-console/server.js"
if not os.path.exists(PATH):
    print("run from the repo root (expected voice-console/server.js)"); sys.exit(1)

src = open(PATH).read()
shutil.copy(PATH, PATH + ".bak2")
print(f"backed up -> {PATH}.bak2")

if "process.env.LANE_B_URL" not in src:
    lines = src.split("\n")
    last = max((i for i, l in enumerate(lines[:60])
                if (l.strip().startswith("const ") and "require(" in l)
                or l.strip().startswith("import ")), default=-1)
    lines.insert(last + 1,
                 '\n// Lane B — the Python retrieval service (resolve / route / recall).\n'
                 'const LANE_B = process.env.LANE_B_URL || "http://localhost:8000";')
    src = "\n".join(lines)
    print(f"inserted LANE_B at line {last + 2}")
else:
    print("LANE_B already present")

m = re.search(r"(async\s+)?function\s+generateTurn\s*\(([^)]*)\)\s*\{", src)
if not m:
    print("!! could not find generateTurn(...)"); sys.exit(2)

start, bo = m.start(), src.index("{", m.end() - 1)
depth, i, q = 0, bo, None
while i < len(src):
    c = src[i]
    if q:
        if c == "\\": i += 2; continue
        if c == q: q = None
    elif c in "\"'`": q = c
    elif c == "{": depth += 1
    elif c == "}":
        depth -= 1
        if depth == 0: break
    i += 1
end = i + 1
print(f"replacing generateTurn ({src[start:end].count(chr(10))} lines)")

NEW = '''async function generateTurn(lexiconOn, text) {
  // REAL. Calls the Python Lane B service. Nothing below is invented.
  // Fabricated latency on screen is the one thing a technical judge does not
  // forgive, and we do not need it: our measured numbers are better than the
  // mock's guesses.
  //
  // Same return contract as the mock, so the websocket broadcast,
  // logs/turns.jsonl and the frontend are all untouched.
  const term = text ? { heard: text } : pick(DEMO_TERMS);
  const t0 = Date.now();

  const r = await fetch(`${LANE_B}/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: term.heard, lexicon_on: lexiconOn })
  });
  if (!r.ok) throw new Error("Lane B returned " + r.status);
  const d = await r.json();

  const course = d.resolutions.course;

  const stages = {
    // 0 means NOT WIRED YET. An honest zero beats a plausible fake.
    asr_ms: 0,                                  // A's ASR
    route_ms: d.latency_ms.route,               // measured
    resolve_ms: d.latency_ms.resolve_course + d.latency_ms.resolve_exam,
    llm_ms: 0,                                  // C's agent
    tts_ms: 0                                   // A's Rime
  };
  const total_ms = Date.now() - t0;

  // With the lexicon off we deliberately do NOT canonicalise: the raw ASR
  // string goes downstream. That contrast is the demo.
  const resolution = {
    heard: d.heard,
    resolved: lexiconOn && course ? course.canonical : null,
    similarity: course ? course.score : 0,
    band: course ? course.band : "reject",
    alternates: course ? course.alternates : [],
    ok: false
  };
  resolution.ok =
    resolution.resolved !== null && resolution.similarity >= SIMILARITY_THRESHOLD;

  return {
    type: 'turn',
    turn_id: ++turnCounter,
    ts: new Date().toISOString(),
    lexicon_enabled: lexiconOn,
    stages,
    total_ms,
    resolution,
    intent: d.intent,
    eligibility: d.eligibility,
    memory: d.memory,
    speak: lexiconOn ? d.speak_lexicon_on : d.speak_lexicon_off,
    speak_lexicon_on: d.speak_lexicon_on,
    speak_lexicon_off: d.speak_lexicon_off
  };
}'''

src = src[:start] + NEW + src[end:]
open(PATH, "w").write(src)
print(f"patched {PATH}\n")

# generateTurn is now async — every call site needs `await`, and the enclosing
# arrow/function needs to be async. Patch the common shapes automatically.
fixed = 0
out = []
for ln in src.split("\n"):
    if "generateTurn(" in ln and "function generateTurn" not in ln and "await" not in ln:
        new = ln.replace("generateTurn(", "await generateTurn(")
        # make the enclosing arrow/function async
        new = re.sub(r"\((req,\s*res)\)\s*=>", r"async (\1) =>", new)
        new = re.sub(r"\(\)\s*=>\s*\{", "async () => {", new)
        new = re.sub(r"\((ws|msg|data)\)\s*=>\s*\{", r"async (\1) => {", new)
        out.append(new)
        fixed += 1
    else:
        out.append(ln)
src = "\n".join(out)
open(PATH, "w").write(src)
print(f"auto-added await to {fixed} call site(s)")

print("\ncall sites now:")
for n, ln in enumerate(src.split("\n"), 1):
    if "generateTurn(" in ln and "function generateTurn" not in ln:
        ok = "await" in ln and "async" in ln
        print(f"  line {n}: {'ok  ' if ok else 'CHECK'} {ln.strip()[:76]}")
print("\n  ^ any CHECK line: the enclosing function must be `async`. Fix by hand.")

left = [(n, l.strip()[:70]) for n, l in enumerate(src.split("\n"), 1)
        if re.search(r"randInt\(|randFloat\(|Math\.random", l)
        and "function rand" not in l]
print("\nremaining random-number lines (check none feed the UI):")
for n, l in left or [(0, "none")]:
    print(f"  line {n}: {l}" if n else "  none")
