import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def extract_query(user_said: str, slot_type: str) -> str:
    system_prompt = (
        f"You extract a short search query for '{slot_type}' from what a caller said. "
        f"Reply with ONLY the extracted query, nothing else. No explanation. "
        f"If the text does not mention a specific {slot_type}, reply with exactly: NONE"
    )
    response = _client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_said},
        ],
        max_tokens=30,
        temperature=0,
    )
    result = response.choices[0].message.content.strip()
    return "" if result.upper() == "NONE" else result


if __name__ == "__main__":
    print(extract_query("mera bête ko computer science mein interest hai", "course"))
    print(extract_query("usne JEE de rakha hai", "exam"))