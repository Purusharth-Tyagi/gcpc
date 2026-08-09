#!/usr/bin/env python3
"""Two changes to voice-console/server.js:

  1. add POST /turn  so the frontend can send REAL typed input
  2. gate the autoplay timer behind DEMO_AUTOPLAY=1

Run from the repo root:   python patch_console.py
Then restart node.
"""
import os, re, shutil, sys

PATH = "voice-console/server.js"
if not os.path.exists(PATH):
    print("run from the repo root (/workspaces/gcpc)"); sys.exit(1)

src = open(PATH).read()
shutil.copy(PATH, PATH + ".bak5")
print(f"backed up -> {PATH}.bak5")

# ---------------------------------------------------------- 1. POST /turn
ROUTE = '''
// Real typed input from the frontend. The websocket broadcast still works;
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

if re.search(r'app\.post\(\s*["\']/turn["\']', src):
    print("POST /turn already present")
else:
    m = re.search(r"^(const\s+\w+\s*=\s*)?app\.listen\(", src, re.M)
    if not m:
        print("!! could not find app.listen(...) — add the route by hand"); sys.exit(2)
    src = src[:m.start()] + ROUTE + "\n" + src[m.start():]
    print("added POST /turn before app.listen")

# ------------------------------------------------------- 2. gate autoplay
lines = src.split("\n")
gated = False
# Match the TOP-LEVEL kickoff only: zero indentation. The recursive call
# inside setTimeout is indented, and gating that one would stop the loop
# after the first tick instead of never starting it. Scan from the end.
for i in range(len(lines) - 1, -1, -1):
    ln = lines[i]
    if re.match(r"^scheduleNext\(\);\s*$", ln):
        lines[i] = ('// Autoplay fires a turn every 1.5-2.6s. Every tick now hits Lane B for\n'
                    '// real, so leaving it on pollutes p50 with synthetic traffic.\n'
                    '//   node server.js                  -> quiet, real input only\n'
                    '//   DEMO_AUTOPLAY=1 node server.js   -> background chatter\n'
                    'if (process.env.DEMO_AUTOPLAY === "1") scheduleNext();')
        print(f"gated autoplay at line {i+1}")
        gated = True
        break
if not gated:
    if "DEMO_AUTOPLAY" in src:
        print("autoplay already gated")
    else:
        print("!! no bare `scheduleNext();` found — check by hand")

open(PATH, "w").write("\n".join(lines))
print(f"\nwrote {PATH}")
print("""
next, in TERMINAL 2 (the one running node):
    Ctrl+C
    node server.js

then in TERMINAL 3:
    curl -s -X POST localhost:3000/turn -H 'Content-Type: application/json' \\
      -d '{"lexicon_on": true, "text": "AI wala CS course"}'
""")
