import os, requests
from dotenv import load_dotenv

load_dotenv()

RIME_API_KEY = os.getenv("RIME_API_KEY")

def speak(text: str, out_file: str = "test_output.mp3"):
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
    )
    if response.status_code == 200:
        with open(out_file, "wb") as f:
            f.write(response.content)
        print(f"Saved audio to {out_file}")
    else:
        print(f"Error: {response.status_code}", response.text)

if __name__ == "__main__":
    speak("Namaste, this is the admissions helpline.")