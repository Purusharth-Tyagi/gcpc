# Sarthi AI — Voice-Based Admissions Helpline

StarForge 2026 · Track: VoxForge

Sarthi AI is a voice-first admissions and counselling assistant for colleges. A caller — parent or student — speaks naturally in Hinglish, and the system checks their real eligibility against live cutoffs and responds with a natural voice reply, all in under a second — before they ever have to step onto campus.

## Problem

Every admission season, parents and students travel to campus hoping to enroll — only to find out in person that they don't meet the eligibility cutoff for the course they wanted. That's a wasted trip, wasted hope, and a disappointed family standing at the admissions desk. Colleges also lose staff time explaining "you don't qualify" over and over, in person, one family at a time.

## Approach

Sarthi AI is a voice-first helpline that tells parents and students **before they visit** whether it's worth coming in at all. A caller speaks naturally in Hinglish, shares their child's course interest, exam, and score, and Sarthi checks it against real, live cutoffs — giving an honest "likely eligible / borderline / not likely" answer over a phone call, from home.

No wasted trips. No false hope. If they're a strong fit, Sarthi can help them book a campus visit right there. If not, it can point them toward alternatives or connect them to a counsellor — instead of finding out the hard way after showing up.

## Architecture
Caller speaks (browser mic)
│
▼
Deepgram STT ──────────► transcribed text
│
▼
Dialogue Engine (state machine)
greet → identify → enquire → eligibility → offer → collect → confirm → book → done
│
▼
Retrieval Layer (Qdrant) ── resolves course / exam / faculty names, fuzzy + semantic
│
▼
Eligibility Guardrail ── compares score to real cutoffs, never fabricates a verdict
│
▼
Rime TTS ──────────────► spoken reply (phoneme-corrected pronunciation)
│
▼
Caller hears the answer

## Tech Stack

| Layer | Tech |
|---|---|
| Speech-to-Text | Deepgram (nova-2) |
| Language Understanding | Groq (Llama 3.1) |
| Retrieval / Course Catalog | Qdrant (vector search) |
| Text-to-Speech | Rime AI |
| Backend | FastAPI |
| Frontend | HTML/JS (browser mic → live voice UI) |

##  Running Locally

```bash
# 1. Clone and set up
git clone https://github.com/Purusharth-Tyagi/gcpc.git
cd gcpc
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt

# 2. Add your API keys to a .env file
RIME_API_KEY=...
DEEPGRAM_API_KEY=...
GROQ_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...

# 3. Run the server
uvicorn api.server:app --reload --port 8000

# 4. Open in browser
http://localhost:8000
```

## Key Features

- Real-time voice conversation, under 1s response latency
- Fuzzy/semantic matching for misheard course & exam names
- Strict eligibility guardrail — no hallucinated "yes, you're eligible"
- Natural pronunciation of names and courses via phoneme injection
- Hindi/English mixed speech support

## Team
Built for StarForge 2026, VoxForge track.
| Name | Lane |
|---|---|
| [Abhinav Jha] | Lane A — Audio Pipeline |
| [Yug Goel] | Lane B — Retrieval (Qdrant) |
| [Purusharth Tyagi] | Lane C — Dialogue Agent |
| [Moulik Dheer] | Lane D — Demo Console |