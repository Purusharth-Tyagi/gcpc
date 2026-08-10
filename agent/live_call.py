import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sounddevice as sd
from scipy.io.wavfile import write

from agent.enquiry import Enquiry
from agent.dialogue import handle_turn, State
from agent.deepgram_listen import transcribe_bytes
from agent.rime_speak import synthesize

SAMPLE_RATE = 16000


import numpy as np

def record_audio(seconds=6) -> bytes:
    print(f"\n🎤 Taiyar ho jao...")
    import time
    time.sleep(1)
    print("3...")
    time.sleep(1)
    print("2...")
    time.sleep(1)
    print("1...")
    time.sleep(1)
    print("🔴 SAY NOW!")

    recording = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    print("Recording khatam.")

    volume = np.abs(recording).mean()
    print(f"(Volume level: {volume:.1f} — agar ye 50 se kam hai, mic sun nahi raha)")

    write("temp_recording.wav", SAMPLE_RATE, recording)
    with open("temp_recording.wav", "rb") as f:
        return f.read()


def play_audio(mp3_bytes: bytes):
    temp_path = "temp_reply.mp3"
    with open(temp_path, "wb") as f:
        f.write(mp3_bytes)
    os.system(f"start {temp_path}")


def run_live_call():
    enquiry = Enquiry()
    state = State.GREET
    user_said = ""

    print("=" * 50)
    print("Call start. Ctrl+C dabake band karo.")
    print("=" * 50)

    while True:
        reply, state = handle_turn(enquiry, state, user_said)

        if reply:
            print(f"\nAgent: {reply}")
            audio = synthesize(reply)
            if audio:
                play_audio(audio)

        if state == State.DONE:
            print("\n[Call khatam]")
            break

        input("\n(Press enter when you start talking)")
        audio_bytes = record_audio(seconds=5)
        user_said = transcribe_bytes(audio_bytes)
        print(f"You said: {user_said}")


if __name__ == "__main__":
    run_live_call()