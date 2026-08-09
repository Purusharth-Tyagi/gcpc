#!/usr/bin/env python3
"""Two changes to voice-console/server.js:

  1. add POST /turn  so the frontend can send REAL typed input
  2. gate the autoplay timer behind DEMO_AUTOPLAY=1

    cd /workspaces/gcpc
    python patch_console2.py

Then restart node. Idempotent.
"""
import os, re, shutil, sys

PATH = "voice-console/server.js"
if not os.path.exists(PATH):
    print("run from the repo root (/workspaces/gcpc)"); sys.exit(1)

src = open(PATH).read()
shutil.copy(PATH, PATH + ".bak6")
print(f"backed up -> {PATH}.bak6")

ROUTE = '''
// Real typed input from the frontend. The websocket broadcast still works —
// this just gives the UI a way to SEND something instead of only receiving
// timer-driven demo phrases.
app.post("/turn", async (req, res) => {
  try {
    const turn = await generateTurn(
      req.body.lexicon_on !== undefined ? req.body.lexicon_on : lexiconEnabled,
      req.body.text
    );
    broadcast(turn);
    res.json(turn);
  } catch (e) {
    res.status(502).json({ error: "Lane B unreachable: " + e.message });
  }
});

'''

# ---------------------------------------------------------- 1. POST /turn
if re.search(r'app\.post\(\s*["\']/turn["\']', src):
    print("POST /turn already present")
else:
    lines = src.split("\n")
    # any listen call: app.listen / server.listen / httpServer.listen, and
    # forms like `const server = app.listen(`. Take the LAST one.
    idx = None
    for i, ln in enumerate(lines):
        if re.search(r"\b\w+\.listen\s*\(", ln):
            idx = i
    if idx is None:
        print("!! no `.listen(` anywhere. These lines mention listen/createServer:")
        for i, ln in enumerate(lines):
            if "listen" in ln or "createServer" in ln:
                print(f"   line {i+1}: {ln.strip()[:70]}")
        sys.exit(2)
    target = lines[idx].strip()[:56]
    lines.insert(idx, ROUTE)
    src = "\n".join(lines)
    print(f"added POST /turn before: {target}")

# ------------------------------------------------------- 2. gate autoplay
lines = src.split("\n")
if "DEMO_AUTOPLAY" in src:
    print("autoplay already gated")
else:
    gated = False
    # TOP-LEVEL kickoff only (zero indent). The recursive call inside
    # setTimeout is indented — gating that would stop the loop after one tick.
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"^scheduleNext\(\);\s*$", lines[i]):
            lines[i] = ('// Autoplay fires a turn every 1.5-2.6s. Every tick now hits Lane B for\n'
                        '// real, so leaving it on pollutes p50 with synthetic traffic.\n'
                        '//   node server.js                 -> quiet, real input only\n'
                        '//   DEMO_AUTOPLAY=1 node server.js  -> background chatter\n'
                        'if (process.env.DEMO_AUTOPLAY === "1") scheduleNext();')
            print(f"gated autoplay at line {i+1}")
            gated = True
            break
    if not gated:
        print("!! no top-level `scheduleNext();` found — leaving autoplay as is")

open(PATH, "w").write("\n".join(lines))
print(f"\nwrote {PATH}")
print("""
next:
  TERMINAL running node:   Ctrl+C   then   node server.js
  a DIFFERENT terminal:
     curl -s -X POST localhost:3000/turn -H 'Content-Type: application/json' \\
       -d '{"lexicon_on": true, "text": "AI wala CS course"}'
""")
