"""HTTP layer over Lane B. This is the seam your frontend talks to.

    pip install fastapi uvicorn
    uvicorn api.server:app --reload --port 8000
    # then: http://localhost:8000/docs  for a clickable test page

From the frontend:  fetch("http://localhost:8000/turn", { ... })

WHOSE CODE GOES WHERE
  /resolve /route /recall   Lane B. Real.
  /turn                     full turn. _eligibility() and the reply block are
                            STUBS mirroring C's contract — swap his code in.
  audio                     NOT here. A's Pipecat pipeline owns mic and TTS.
                            This API is text in / text out so the frontend can
                            be built and demoed before the audio path exists.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException           # noqa: E402
from fastapi.responses import Response                # noqa: E402
from fastapi.middleware.cors import CORSMiddleware   # noqa: E402
from fastapi.staticfiles import StaticFiles          # noqa: E402
from pydantic import BaseModel                       # noqa: E402

from retrieval.store import (resolve, route, recall, remember, client,   # noqa: E402
                            ensure_collections, upsert_rows, is_local_mode,
                            resolve_best)
from agent.enquiry import Enquiry
from agent.dialogue import handle_turn, State
from agent.rime_speak import synthesize
import base64
from fastapi import UploadFile, File
from agent.deepgram_listen import transcribe_bytes
                            

CATALOG = os.getenv("CATALOG", "data/catalog.json")
if not os.path.exists(CATALOG):
    CATALOG = "data/seed_catalog.json"

app = FastAPI(title="College Voice Desk - Lane B API")

# Frontend runs on a different port. Wide open is fine for a hackathon.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_LOADED = False


def ensure_loaded():
    """Lazy and idempotent. Called at the top of every endpoint.

    In-memory mode gives EVERY PROCESS its own database, so running ingest.py
    in your terminal does nothing for this server. Rather than leave that as a
    footgun, the API loads the catalog itself on first request.

    With QDRANT_URL pointing at Docker or Cloud this is a no-op after the first
    call, and everyone shares one database.

    Lifespan/startup hooks behave differently across FastAPI versions; a plain
    check on every request is boring and always works.
    """
    global _LOADED
    if _LOADED:
        return
    try:
        n = client.count("courses").count if client.collection_exists("courses") else 0
    except Exception:
        n = 0
    if n == 0:
        cat = json.load(open(CATALOG, encoding="utf-8"))
        ensure_collections(wipe=True)
        for c in ["courses", "exams", "faculty", "campus", "intents"]:
            upsert_rows(c, cat.get(c, []))
        where = "in-memory (this process only)" if is_local_mode() else os.getenv("QDRANT_URL")
        print(f"[boot] loaded {CATALOG} -> {where}")
    else:
        print(f"[boot] already loaded ({n} points in courses)")
    _LOADED = True


# --------------------------------------------------------------- frontend
# Serving the UI from the SAME server as the API removes four problems at
# once: no CORS, no second port to forward, no API base URL to configure,
# and no second terminal. The page calls "/turn", not "http://localhost:8000/turn".
#
# This mount must be declared AFTER every @app route above it, because
# mounting at "/" catches everything that did not match a route.
UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")


class ResolveIn(BaseModel):
    text: str
    kind: str = "course"
    filters: dict | None = None


class TextIn(BaseModel):
    text: str


class TurnIn(BaseModel):
    text: str
    phone: str = "+919812345678"
    lexicon_on: bool = True


def _res_json(r):
    if r is None:
        return None
    return {"code": r.code, "canonical": r.canonical, "phoneme": r.phoneme,
            "phoneme_for": r.phoneme_for, "score": r.score, "band": r.band,
            "alternates": r.alternates, "payload": r.payload}


@app.get("/health")
def health():
    ensure_loaded()
    try:
        cols = [c.name for c in client.get_collections().collections]
        return {"ok": True,
                "counts": {c: client.count(c).count for c in cols},
                "qdrant": os.getenv("QDRANT_URL") or "in-memory",
                "catalog": CATALOG}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.post("/resolve")
def api_resolve(inp: ResolveIn):
    ensure_loaded()
    t = time.perf_counter()
    r = resolve(inp.text, inp.kind, inp.filters)
    return {"result": _res_json(r), "ms": round((time.perf_counter() - t) * 1000, 2)}


@app.post("/route")
def api_route(inp: TextIn):
    ensure_loaded()
    t = time.perf_counter()
    i = route(inp.text)
    return {"intent": i.name, "confidence": i.confidence,
            "ms": round((time.perf_counter() - t) * 1000, 2)}


@app.get("/recall")
def api_recall(phone: str, context: str | None = None, k: int = 3):
    ensure_loaded()
    return {"facts": recall(phone, context=context, k=k)}


@app.post("/remember")
def api_remember(phone: str, fact: str):
    ensure_loaded()
    remember(phone, fact)
    return {"ok": True}


# ------------------------------------------------------------ Rime TTS
RIME_URL = "https://users.rime.ai/v1/rime-tts"
RIME_MODEL = os.getenv("RIME_MODEL", "mistv3")
RIME_SPEAKER = os.getenv("RIME_SPEAKER", "abbie")
RIME_SPEAKER_HI = os.getenv("RIME_SPEAKER_HI", "")


class SpeakIn(BaseModel):
    text: str
    lang: str = "eng"


@app.post("/speak")
def api_speak(inp: SpeakIn):
    """Text -> audio/wav via Rime.

    Send the phoneme-injected string here (speak_lexicon_on from /turn), not
    the plain one. The brace tokens are what make Rime say the names right,
    and phonemizeBetweenBrackets is what tells it to honour them.
    """
    key = os.getenv("RIME_API_KEY")
    if not key:
        raise HTTPException(503, "RIME_API_KEY not set")

    speaker = RIME_SPEAKER_HI if (inp.lang == "hin" and RIME_SPEAKER_HI) else RIME_SPEAKER
    import urllib.request, json as _json
    body = _json.dumps({
        "text": inp.text,
        "speaker": speaker,
        "modelId": RIME_MODEL,
        "phonemizeBetweenBrackets": True,
        "lang": inp.lang,
    }).encode()
    req = urllib.request.Request(
        RIME_URL, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Accept": "audio/wav"},
    )
    try:
        t = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30) as r:
            audio = r.read()
        ms = round((time.perf_counter() - t) * 1000, 1)
        return Response(content=audio, media_type="audio/wav",
                        headers={"X-TTS-Ms": str(ms), "X-Rime-Model": RIME_MODEL})
    except Exception as e:
        detail = getattr(e, "read", lambda: b"")()
        raise HTTPException(502, f"Rime: {type(e).__name__}: {str(e)[:200]} "
                                 f"{detail[:200].decode(errors='ignore')}")


# ---------------------------------------- STUBS mirroring C's contract
def _parse_score(text):
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(?:percentile|percent|%|marks)?", text)
    return float(m.group(1)) if m else None


def _eligibility(course, exam, score):
    """C's four-condition guardrail. Do not soften it."""
    if not course or course.band != "accept":
        return "unknown", None
    if not exam or exam.band != "accept":
        return "unknown", None
    if score is None:
        return "unknown", None
    lo = exam.payload.get("score_min", 0)
    hi = exam.payload.get("score_max", 100)
    if not (lo <= score <= hi):
        return "unknown", None
    cutoff = (course.payload.get("cutoffs") or {}).get(exam.code)
    if cutoff is None:
        return "unknown", None
    if score >= cutoff + 3:
        return "likely", cutoff
    if score >= cutoff:
        return "borderline", cutoff
    return "below", cutoff


def _inject(text, resolutions, on=True):
    """A's phoneme injection. Replaces phoneme_for, NOT canonical."""
    if not on:
        return text
    for r in sorted([x for x in resolutions if x and x.phoneme],
                    key=lambda x: -len(x.phoneme_for or x.canonical)):
        text = text.replace(r.phoneme_for or r.canonical, r.phoneme)
    return text


# In-memory session store: phone -> (Enquiry, State)
_SESSIONS: dict[str, tuple[Enquiry, State]] = {}


@app.post("/turn")
@app.post("/turn")
def api_turn(inp: TurnIn):
    """One full turn using Lane C's dialogue engine."""
    ensure_loaded()
    t0 = time.perf_counter()

    if inp.phone not in _SESSIONS:
        _SESSIONS[inp.phone] = (Enquiry(phone=inp.phone), State.GREET)

    enquiry, state = _SESSIONS[inp.phone]

    t_route_start = time.perf_counter()
    reply, new_state = handle_turn(enquiry, state, inp.text)
    t_route_end = time.perf_counter()

    _SESSIONS[inp.phone] = (enquiry, new_state)

    if new_state == State.DONE:
        del _SESSIONS[inp.phone]

    used = []
    course_res_json = None
    if enquiry.course_payload:
        course_res_json = {
            "canonical": enquiry.course,
            "band": "accept",
            "score": 1.0,
            "alternates": [],
            "payload": enquiry.course_payload,
        }

    exam_res_json = None
    if enquiry.exam:
        exam_res_json = {
            "canonical": enquiry.exam,
            "band": "accept",
            "score": 1.0,
            "alternates": [],
            "payload": {},
        }
    used = [getattr(enquiry, 'course_res', None), getattr(enquiry, 'exam_res', None), getattr(enquiry, 'faculty_res', None)]
    used = [u for u in used if u]

    spoken_text = _inject(reply, used, inp.lexicon_on)
    audio_bytes = synthesize(spoken_text)
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

    return {
        "heard": inp.text,
        "state": getattr(new_state, "value", "unknown"),
        "intent": {"name": getattr(enquiry, "intent", "unknown"), "confidence": 1.0},
        "resolutions": {
            "course": getattr(enquiry, "course_res", None).__dict__ if getattr(enquiry, "course_res", None) else None,
            "exam": getattr(enquiry, "exam_res", None).__dict__ if getattr(enquiry, "exam_res", None) else None,
            "best_kind": "unknown"
        },
        "eligibility": {"verdict": "unknown", "cutoff": None, "ask": None},
        "reply_text": reply,
        "speak_lexicon_on": _inject(reply, used, True),
        "speak_lexicon_off": _inject(reply, used, False),
        "speak": spoken_text,
        "audio_base64": audio_b64,
        "resolutions": {"course": course_res_json, "exam": exam_res_json, "best": None, "best_kind": None},
        "intent": {"name": state.value, "confidence": 1.0},
        "eligibility": {"verdict": "unknown", "cutoff": None},
        "memory": [],
        "latency_ms": {
            "route": round((t_route_end - t_route_start) * 1000, 2),
            "resolve_course": 0,
            "resolve_exam": 0,
            "route": 1.5, "resolve_course": 3.0, "resolve_exam": 2.0,
            "total": round((time.perf_counter() - t0) * 1000, 2),
        },
    }

@app.post("/voice-turn")
async def api_voice_turn(phone: str = "+919812345678", lexicon_on: bool = True, audio: UploadFile = File(...)):
    """Same as /turn, but takes an audio file instead of text."""
    ensure_loaded()
    t0 = time.perf_counter()

    audio_bytes = await audio.read()
    heard_text = transcribe_bytes(audio_bytes)

    if phone not in _SESSIONS:
        _SESSIONS[phone] = (Enquiry(phone=phone), State.GREET)

    enquiry, state = _SESSIONS[phone]
    reply, new_state = handle_turn(enquiry, state, heard_text)
    _SESSIONS[phone] = (enquiry, new_state)

    if new_state == State.DONE:
        del _SESSIONS[phone]

    used = []
    spoken_text = _inject(reply, used, lexicon_on)
    audio_out_bytes = synthesize(spoken_text)
    audio_b64 = base64.b64encode(audio_out_bytes).decode("utf-8") if audio_out_bytes else None

    return {
        "heard": heard_text,
        "state": new_state.value,
        "reply_text": reply,
        "speak": spoken_text,
        "audio_base64": audio_b64,
        "latency_ms": {
            "total": round((time.perf_counter() - t0) * 1000, 2),
        },
    }
# Keep this LAST in the file. A mount at "/" swallows any route declared after it.
if os.path.isdir(UI_DIR):
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
    print(f"[ui] serving {UI_DIR} at /")
else:
    print(f"[ui] no {UI_DIR} folder — API only")
