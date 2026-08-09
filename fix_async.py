#!/usr/bin/env python3
"""Make every function that awaits generateTurn() async.

    python fix_async.py

Finds each `await generateTurn(...)`, walks backwards to the nearest enclosing
function or arrow, and adds `async` if missing. Idempotent.
"""
import os, re, shutil, sys

PATH = "voice-console/server.js"
if not os.path.exists(PATH):
    print("run from the repo root"); sys.exit(1)

lines = open(PATH).read().split("\n")
shutil.copy(PATH, PATH + ".bak3")
print(f"backed up -> {PATH}.bak3")

# add await where it's missing on a generateTurn call
for i, ln in enumerate(lines):
    if ("generateTurn(" in ln and "function generateTurn" not in ln
            and "await" not in ln):
        lines[i] = ln.replace("generateTurn(", "await generateTurn(")
        print(f"  line {i+1}: added await")

# patterns that OPEN a function scope
OPENERS = [
    (re.compile(r"^(\s*)(function\s+\w+\s*\()"),           r"\1async \2"),
    (re.compile(r"^(\s*)(\w+\s*:\s*)(function\s*\()"),     r"\1\2async \3"),
    (re.compile(r"^(\s*)(const|let|var)(\s+\w+\s*=\s*)(function\s*\()"),
                                                           r"\1\2\3async \4"),
    (re.compile(r"^(\s*)(const|let|var)(\s+\w+\s*=\s*)(\([^)]*\)\s*=>)"),
                                                           r"\1\2\3async \4"),
    (re.compile(r"(\(\s*)(\([^)]*\)\s*=>\s*\{)"),          r"\1async \2"),
    (re.compile(r"(,\s*)(\([^)]*\)\s*=>\s*\{)"),           r"\1async \2"),
    (re.compile(r"^(\s*)(\([^)]*\)\s*=>\s*\{)"),           r"\1async \2"),
]

fixed = 0
for i, ln in enumerate(lines):
    if "await generateTurn(" not in ln:
        continue
    # walk backwards for the nearest scope opener that isn't already async
    for j in range(i, max(-1, i - 40), -1):
        cand = lines[j]
        if "async" in cand and ("=>" in cand or "function" in cand):
            break                       # already async, nothing to do
        hit = False
        for pat, rep in OPENERS:
            if pat.search(cand):
                lines[j] = pat.sub(rep, cand, count=1)
                print(f"  line {j+1}: made async  ->  {lines[j].strip()[:66]}")
                fixed += 1
                hit = True
                break
        if hit:
            break
    else:
        print(f"  !! line {i+1}: could not find an enclosing function — fix by hand")

open(PATH, "w").write("\n".join(lines))
print(f"\nmade {fixed} function(s) async")
print("now run:  node --check voice-console/server.js")
