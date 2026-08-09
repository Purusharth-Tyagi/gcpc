import os, requests
from dotenv import load_dotenv

load_dotenv()

RIME_API_KEY = os.getenv("RIME_API_KEY")


def synthesize(text: str) -> bytes | None:
    """Call Rime TTS, return raw MP3 bytes, or None on failure."""
    if not text.strip():
        return None
    try:
        response = requests.post(
            "https://users.rime.ai/v1/rime-tts",
            headers={
                "Authorization": f"Bearer {RIME_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "modelId": "mistv2",
                "speaker": "marsh",
                "lang": "eng",
            },
            timeout=10,
        )
        if response.status_code == 200:
            return response.content
        else:
            print(f"Rime error: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"Rime exception: {e}")
        return None