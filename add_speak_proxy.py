#!/usr/bin/env python3
"""Add a /speak proxy to Express so the page can play Rime audio same-origin.

    cd /workspaces/gcpc
    python add_speak_proxy.py

Without this the page has to call http://localhost:8000/speak directly, which
breaks in Codespaces (the browser is not inside the Codespace) and drags in
CORS. Proxying keeps everything on port 3000. Idempotent.
"""
import os, re, shutil, sys

PATH = "voice-console/server.js"
if not os.path.exists(PATH):
    print("run from the repo root"); sys.exit(1)

src = open(PATH).read()
shutil.copy(PATH, PATH + ".bak7")
print(f"backed up -> {PATH}.bak7")

if '"/speak"' in src or "'/speak'" in src:
    print("/speak proxy already present"); sys.exit(0)

ROUTE = '''
// Proxy TTS to the Python service so the browser stays same-origin.
// Returns raw wav bytes plus the measured TTS latency header.
app.post("/speak", async (req, res) => {
  try {
    const r = await fetch(`${LANE_B}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body || {})
    });
    if (!r.ok) {
      const t = await r.text();
      return res.status(r.status).type("application/json").send(t);
    }
    const ms = r.headers.get("x-tts-ms");
    if (ms) res.set("X-TTS-Ms", ms);
    res.set("Access-Control-Expose-Headers", "X-TTS-Ms");
    res.type("audio/wav");
    const buf = Buffer.from(await r.arrayBuffer());
    res.send(buf);
  } catch (e) {
    res.status(502).json({ error: "Lane B unreachable: " + e.message });
  }
});

'''

lines = src.split("\n")
idx = None
for i, ln in enumerate(lines):
    if re.search(r"\b\w+\.listen\s*\(", ln):
        idx = i
if idx is None:
    print("!! no .listen( found — add the route by hand"); sys.exit(2)

target = lines[idx].strip()[:50]
lines.insert(idx, ROUTE)
open(PATH, "w").write("\n".join(lines))
print(f"added POST /speak before: {target}")
print("\nrestart node, then open  <your-3000-url>/talk.html")
