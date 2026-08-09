import os
from dotenv import load_dotenv
from deepgram import DeepgramClient

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


def transcribe_bytes(audio_bytes: bytes) -> str:
    """Transcribe raw audio bytes to text using Deepgram."""
    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    response = client.listen.v1.media.transcribe_file(
        request=audio_bytes,
        model="nova-2",
    )

    transcript = response.results.channels[0].alternatives[0].transcript
    return transcript