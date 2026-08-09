import os
from dotenv import load_dotenv
from deepgram import DeepgramClient

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


def transcribe_file(filepath: str) -> str:
    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    with open(filepath, "rb") as audio_file:
        response = client.listen.v1.media.transcribe_file(
            request=audio_file.read(),
            model="nova-2",
        )

    transcript = response.results.channels[0].alternatives[0].transcript
    return transcript


if __name__ == "__main__":
    text = transcribe_file("test_output.mp3")
    print("Transcribed:", text)