#!/usr/bin/env python3
"""ONE SCRIPT. Wires voice-console/server.js to the Python Lane B service.

    cd /workspaces/gcpc
    python fix_voice_console.py

Idempotent and self-resetting: if a .bak from an earlier attempt exists it
starts from that, so a half-patched file is not a problem.

What it does
  1. restores the cleanest available backup
  2. inserts  const LANE_B = ...
  3. replaces the body of generateTurn() with a real fetch to :8000
  4. adds `await` at REAL call sites only (comments and strings are skipped)
  5. makes the enclosing function of each await `async`
  6. reverts `async` on any function that does not actually await
  7. runs node --check and reports

Undo everything:
    cp voice-console/server.js.ORIGINAL voice-console/server.js
"""
import os
import re
import shutil
import subprocess
import sys

PATH = "voice-console/server.js"


def fail(msg):
    print(f"\n!! {msg}")
    sys.exit(1)


if not os.path.exists(PATH):
    fail(f"{PATH} not found — run this from the repo root (/workspaces/gcpc)")

# ---------------------------------------------------------------- 1. reset
ORIGINAL = PATH + ".ORIGINAL"
if not os.path.exists(ORIGINAL):
    # first run: whichever backup is oldest is closest to pristine
    for cand in [PATH + ".bak", PATH + ".bak2", PATH + ".bak3", PATH + ".bak4"]:
        if os.path.exists(cand):
            shutil.copy(cand, ORIGINAL)
            print(f"saved pristine copy from {cand} -> {ORIGINAL}")
            break
    else:
        shutil.copy(PATH, ORIGINAL)
        print(f"saved pristine copy -> {ORIGINAL}")

shutil.copy(ORIGINAL, PATH)
print(f"reset {PATH} from {ORIGINAL}")

src = open(PATH).read()
lines = src.split("\n")


# ------------------------------------------------------- comment detection
def comment_mask(all_lines):
    """True for lines that are comments — these are NOT call sites.

    Treating a comment as a call site is exactly what broke the earlier
    attempts: the SWAP POINT block mentions generateTurn() several times.
    """
    mask, in_block = [], False
    for ln in all_lines:
        s = ln.strip()
        starts_block = "/*" in s and "*/" not in s.split("/*", 1)[1]
        is_comment = in_block or s.startswith("//") or s.startswith("*")
        mask.append(is_comment)
        if starts_block:
            in_block = True
        if "*/" in s:
            in_block = False
    return mask


# ------------------------------------------------------------- 2. LANE_B
if "process.env.LANE_B_URL" in src:
    print("LANE_B already present")
else:
    last = -1
    for i, ln in enumerate(lines[:80]):
        s = ln.strip()
        if (s.startswith("const ") and "require(" in s) or s.startswith("import "):
            last = i
    at = last + 1 if last >= 0 else 0
    lines.insert(at, "\n// Lane B — the Python retrieval service (resolve / route / recall).\n"
                     'const LANE_B = process.env.LANE_B_URL || "http://localhost:8000";')
    print(f"inserted LANE_B at line {at + 1}")

src = "\n".join(lines)

# ------------------------------------------------- 3. replace generateTurn
m = re.search(r"(async\s+)?function\s+generateTurn\s*\(([^)]*)\)\s*\{", src)
if not m:
    fail("could not find `function generateTurn(...)` — paste it to me instead")

start = m.start()
bo = src.index("{", m.end() - 1)
depth, i, q = 0, bo, None
while i < len(src):
    c = src[i]
    if q:
        if c == "\\":
            i += 2
            continue
        if c == q:
            q = None
    elif c in "\"'`":
        q = c
    elif c == "{":
        depth += 1
    elif c == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
end = i + 1
print(f"replacing generateTurn ({src[start:end].count(chr(10))} lines)")

NEW = '''async function generateTurn(lexiconOn, text) {
  // REAL. Calls the Python Lane B service. Nothing below is invented.
  //
  // The mock used randInt() for every stage and randFloat() for similarity.
  // Fabricated latency on a screen is the one thing a technical judge will
  // not forgive, and we do not need it: the measured numbers are better than
  // the mock's guesses.
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

  // Lexicon off: we deliberately do NOT canonicalize. The raw ASR string goes
  // downstream untouched. That contrast is the demo.
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
lines = src.split("\n")

# --------------------------------------------- 4. await at real call sites
mask = comment_mask(lines)
call_lines = []
for i, ln in enumerate(lines):
    if mask[i]:
        continue
    if "generateTurn(" not in ln or "function generateTurn" in ln:
        continue
    if "await" not in ln:
        lines[i] = ln.replace("generateTurn(", "await generateTurn(")
        print(f"  line {i+1}: added await")
    call_lines.append(i)

if not call_lines:
    print("  (no call sites found — check by hand)")

# ------------------------------------------ 5. make enclosing funcs async
OPENERS = [
    (re.compile(r"^(\s*)(function\s+\w+\s*\()"),                        r"\1async \2"),
    (re.compile(r"^(\s*)(const|let|var)(\s+\w+\s*=\s*)(function\s*\()"), r"\1\2\3async \4"),
    (re.compile(r"^(\s*)(const|let|var)(\s+\w+\s*=\s*)(\([^)]*\)\s*=>)"), r"\1\2\3async \4"),
    (re.compile(r"(\(\s*)(\([^)]*\)\s*=>\s*\{)"),                       r"\1async \2"),
    (re.compile(r"(,\s*)(\([^)]*\)\s*=>\s*\{)"),                        r"\1async \2"),
    (re.compile(r"^(\s*)(\([^)]*\)\s*=>\s*\{)"),                        r"\1async \2"),
]


def make_enclosing_async(idx):
    mask_now = comment_mask(lines)
    for j in range(idx, max(-1, idx - 60), -1):
        if mask_now[j]:
            continue
        cand = lines[j]
        if "async" in cand and ("=>" in cand or "function" in cand):
            return True                       # already async
        for pat, rep in OPENERS:
            if pat.search(cand):
                lines[j] = pat.sub(rep, cand, count=1)
                print(f"  line {j+1}: made async -> {lines[j].strip()[:62]}")
                return True
    return False


for idx in call_lines:
    if not make_enclosing_async(idx):
        print(f"  !! line {idx+1}: no enclosing function found — fix by hand")

# --------------------------------- 6. revert async on non-awaiting funcs
def block_end(start_line):
    depth, i, q = 0, start_line, None
    while i < len(lines):
        for c in lines[i]:
            if q:
                if c == q:
                    q = None
            elif c in "\"'`":
                q = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(lines) - 1


mask = comment_mask(lines)
for i, ln in enumerate(lines):
    if mask[i] or "async" not in ln or "{" not in ln:
        continue
    body = "\n".join(lines[i:block_end(i) + 1])
    inner = body[body.find("{") + 1:]
    if "await " not in inner:
        new = re.sub(r"\basync\s+", "", ln, count=1)
        if new != ln:
            lines[i] = new
            print(f"  line {i+1}: reverted async, no await inside -> {new.strip()[:56]}")

# ------------------------- 6b. don't let a Lane B outage crash the server
# generateTurn can now throw (fetch failure, non-200). Timer callbacks call
# emitTurn() without awaiting, so a rejection would be unhandled — and modern
# Node exits the process on that. Losing the server mid-demo because Qdrant
# blinked is not a trade worth making.
GUARD = ('process.on("unhandledRejection", (e) => '
         'console.error("[unhandled]", e && e.message));')
if "unhandledRejection" not in "\n".join(lines):
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(const|let|var)\s+\w+\s*=\s*require\(", ln):
            continue
        if ln.strip().startswith("const app"):
            lines.insert(i, "\n// A Lane B outage should log, not kill the process.\n" + GUARD + "\n")
            print(f"  line {i+1}: added unhandledRejection guard")
            break
    else:
        lines.insert(0, GUARD)
        print("  added unhandledRejection guard at top")

open(PATH, "w").write("\n".join(lines))
print(f"\nwrote {PATH}")

# -------------------------------------------------------- 7. verify
print("\n--- node --check ---")
try:
    r = subprocess.run(["node", "--check", PATH], capture_output=True, text=True)
    if r.returncode == 0:
        print("  syntax OK")
    else:
        print("  FAILED:\n" + r.stderr[:600])
        print(f"\n  undo with:  cp {ORIGINAL} {PATH}")
        sys.exit(1)
except FileNotFoundError:
    print("  node not on PATH — run `node --check " + PATH + "` yourself")

print("\n--- remaining random-number lines (none should feed the UI) ---")
mask = comment_mask(lines)
found = False
for i, ln in enumerate(lines):
    if mask[i] or "function rand" in ln or "function pick" in ln:
        continue
    if re.search(r"randInt\(|randFloat\(|Math\.random", ln):
        print(f"  line {i+1}: {ln.strip()[:72]}")
        found = True
if not found:
    print("  none")

print("""
--- next ---
  terminal 1:  cd /workspaces/gcpc && uvicorn api.server:app --port 8000
  terminal 2:  cd /workspaces/gcpc/voice-console && node server.js
  terminal 3:  curl -s -X POST localhost:3000/turn \\
                 -H 'Content-Type: application/json' \\
                 -d '{"lexicon_on": true, "text": "AI wala CS course"}'

THEN STOP uvicorn AND RUN THAT CURL AGAIN. It must fail.
If it still returns numbers, something is still simulated.
""")
