# Sarthi — AI Voice-Based Admissions Helpline

**StarForge 2026 · Track: VoxForge**

Sarthi is a voice-first admissions and counselling assistant for colleges. A caller — parent or student — speaks naturally in Hinglish, and the system understands their query, checks eligibility against real cutoffs, and responds with a natural voice reply, all in under a second.

## Problem

Admissions helplines are overwhelmed during peak season. Callers repeat the same questions — "which courses am I eligible for", "what's the cutoff", "how do I apply" — and staff can't scale to handle every call live. Text-based bots don't work well for many callers who are more comfortable speaking, especially in Hinglish.

## Approach

Sarthi replaces a human on the first line of contact with a real-time voice agent that:
- Listens and transcribes Hinglish speech (Deepgram)
- Understands intent and extracts course/exam/score via LLM (Groq)
- Resolves fuzzy, misheard, or code-mixed course/exam names against a real catalog (Qdrant vector search)
- Applies a strict eligibility guardrail — never guesses, only says "likely / borderline / below / unknown"
- Speaks the answer back naturally, with correct pronunciation of names, courses, and numbers (Rime TTS)

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
## ⚙️ Tech Stack

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

##  Team

Built for StarForge 2026, VoxForge track.

| Name | Lane |
|---|---|
| [Abhinav Jha] | Lane A — Audio Pipeline |
| [Yug Goel] | Lane B — Retrieval (Qdrant) |
| [Purusharth Tyagi] | Lane C — Dialogue Agent |
| [Moulik Dheer] | Lane D — Demo Console |

