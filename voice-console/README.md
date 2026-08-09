# Voice Assistant — Demo Console (Lane D)

Three-panel demo console: **A/B lexicon toggle**, **latency panel**, **resolution panel**.
Runs entirely on mock data — no pipeline needed yet.

## Run

```bash
npm install && node server.js
```

Then open http://localhost:3000

Port override: `PORT=4000 node server.js`

## What it does

- A background loop emits one turn every ~1.5–2.6s (irregular, conversation-like).
- Every turn is broadcast to all websocket clients **and** appended to `logs/turns.jsonl`.
- `logs/turns.jsonl` is truncated on every server start (fresh demo run).

### The toggle

Flips `lexicon_enabled` live, no restart, synced to every connected client.

| | lexicon ON | lexicon OFF |
|---|---|---|
| similarity | 0.85–0.95 | 0.00–0.35 |
| `resolve_ms` | 25–70 | **0** (no vector lookup happens) |
| resolution | canonical catalog entry | `null` — nothing canonicalized |
| indicator | ✓ | ✗ |

Threshold for ✓/✗ is `similarity >= 0.75` (`SIMILARITY_THRESHOLD` in `server.js`).

## Message / log-line shape

The websocket `turn` message and each line of `logs/turns.jsonl` are the **same object**:

```json
{
  "type": "turn",
  "turn_id": 7,
  "ts": "2026-08-09T10:15:22.481Z",
  "lexicon_enabled": true,
  "stages": { "asr_ms": 248, "route_ms": 31, "resolve_ms": 52, "llm_ms": 401, "tts_ms": 178 },
  "total_ms": 910,
  "p50_ms": 894,
  "resolution": {
    "heard": "AI wala CS course",
    "resolved": "B.Tech in CSE (AI & ML)",
    "similarity": 0.907,
    "ok": true
  }
}
```

`resolution.resolved` is `null` when nothing canonicalized. `similarity` is 0–1.
This shape is a contract with the log-tailing lane — don't reshape it silently.

Other websocket messages:

- server → client: `{"type":"state","lexicon_enabled":bool}`, `{"type":"history","turns":[...]}` (last 12, sent on connect)
- client → server: `{"type":"toggle","lexicon_enabled":bool}`

## Swapping in the real pipeline

Everything fake lives in **one function**: `generateTurn(lexiconOn)` in `server.js`,
between the `SWAP POINT` / `END SWAP POINT` comment banners. Replace its body with
real pipeline output and nothing else changes — not the broadcast, not the log
format, not a single line of frontend code.

Demo terms live in `data/demo_terms.json` (`heard` / `resolved` / `kind`).

## Files

```
server.js               express + ws, turn loop, jsonl writer
public/index.html       three panels
public/app.js           websocket client, rendering
public/style.css        dark, functional only
data/demo_terms.json    17 fuzzy → canonical pairs
logs/turns.jsonl        one JSON line per turn (reset each start)
```
