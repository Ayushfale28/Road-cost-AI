"""AI part only. To switch model/provider later, change only this file."""
import json
import os
from pathlib import Path

from google import genai
from google.genai import types

PROMPT_PATH = Path(__file__).parent / "prompts" / "road_photo_prompt.xml"
# Free-tier Flash model. If Google renames/retires it, change here or set GEMINI_MODEL.
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def analyze_photo(image_bytes: bytes, mime_type: str, api_key: str, note: str = "") -> dict:
    """Send the road photo to Gemini, get back a dict of suggestions."""
    client = genai.Client(api_key=api_key)
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_text = "Analyse this road photo as per your instructions."
    if note.strip():
        user_text += f"\nEngineer's note: {note.strip()}"

    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), user_text],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    text = (resp.text or "").strip()
    text = text.removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)


CHAT_PROMPT_PATH = Path(__file__).parent / "prompts" / "chat_prompt.xml"


def chat_reply(history: list, api_key: str, analysis: dict | None = None,
               image_bytes: bytes | None = None, mime_type: str = "image/jpeg") -> str:
    """history = [{'role': 'user'|'assistant', 'content': str}, ...] (last one is the new user message)."""
    client = genai.Client(api_key=api_key)
    system = CHAT_PROMPT_PATH.read_text(encoding="utf-8")
    if analysis:
        system += "\n<photo_analysis>\n" + json.dumps(analysis, ensure_ascii=False) + "\n</photo_analysis>"

    contents = []
    for i, m in enumerate(history):
        parts = [types.Part.from_text(text=m["content"])]
        if i == 0 and m["role"] == "user" and image_bytes:
            parts.insert(0, types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        contents.append(types.Content(role="user" if m["role"] == "user" else "model", parts=parts))

    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.5),
    )
    return (resp.text or "").strip()
