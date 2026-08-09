// Voice loop: mic -> text -> /turn -> Rime audio.
//
// ASR uses the browser's Web Speech API. Chrome only, needs no key, no server,
// no install. It is not as good as Deepgram on Hinglish, but it works tonight
// and swaps out for A's pipeline later without touching anything else.
//
// TTS goes through Rime via POST /speak on the Python API. That is a track
// requirement, not a choice: the brief says voice generation must be Rime.

const API = window.LANE_B_URL || "";   // same-origin by default

let recognition = null;
let listening = false;

export function initASR({ lang = "en-IN", onText, onPartial, onError } = {}) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    onError && onError("Web Speech API unavailable — use Chrome, or type instead");
    return null;
  }
  recognition = new SR();
  recognition.lang = lang;              // en-IN handles Hinglish better than en-US
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onresult = (e) => {
    let finalText = "", partial = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t;
      else partial += t;
    }
    if (partial) onPartial && onPartial(partial);
    if (finalText) onText && onText(finalText.trim());
  };
  recognition.onerror = (e) => onError && onError(e.error);
  recognition.onend = () => { listening = false; };
  return recognition;
}

export function startListening() {
  if (!recognition || listening) return;
  listening = true;
  recognition.start();
}

export function stopListening() {
  if (recognition && listening) recognition.stop();
}

// --------------------------------------------------------------- speaking
let currentAudio = null;

export function stopSpeaking() {
  // Barge-in: kill playback the instant the user starts talking.
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
}

export async function speak(text, lang = "eng") {
  stopSpeaking();
  const res = await fetch(`${API}/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error("TTS failed: " + (err.detail || res.status));
  }
  const ttsMs = res.headers.get("X-TTS-Ms");
  const blob = await res.blob();
  currentAudio = new Audio(URL.createObjectURL(blob));
  await currentAudio.play();
  return { ttsMs: Number(ttsMs) || null };
}

// ------------------------------------------------------------ full turn
export async function voiceTurn(text, { lexiconOn = true, onStage } = {}) {
  const t0 = performance.now();

  const r = await fetch(`${API}/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lexicon_on: lexiconOn }),
  });
  const d = await r.json();
  onStage && onStage("logic", d.latency_ms);

  // IMPORTANT: send the phoneme-injected string, not the plain one.
  // speak_lexicon_on carries the brace tokens Rime needs.
  const toSpeak = lexiconOn ? d.speak_lexicon_on : d.speak_lexicon_off;
  const { ttsMs } = await speak(toSpeak);

  d.latency_ms.tts = ttsMs;
  d.latency_ms.end_to_end = Math.round(performance.now() - t0);
  onStage && onStage("done", d.latency_ms);
  return d;
}
