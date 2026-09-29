"""
AI module for the Road Cost Estimator.

This file handles:
1. Road photo analysis
2. Road Project Chat Assistant

IMPORTANT:
- API keys are NOT entered by website users.
- The API key is read from the server environment / Streamlit secrets.
- The AI provider is hidden from the application UI.
- The rest of the application only calls analyze_photo()
  and chat_reply().
"""

import json
import os
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types


# ============================================================
# FILE LOCATIONS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PHOTO_PROMPT_PATH = BASE_DIR / "road_photo_prompt.xml"
CHAT_PROMPT_PATH = BASE_DIR / "chat_prompt.xml"


# ============================================================
# MODEL CONFIGURATION
# ============================================================

# This can be changed on the server without changing the code.
#
# Example environment variable:
# GEMINI_MODEL=gemini-2.5-flash
#
# Users never see this value.
MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def _get_api_key(api_key: Optional[str] = None) -> str:
    """
    Get the AI API key.

    Priority:
    1. Explicit server-side value passed by the application.
    2. GEMINI_API_KEY environment variable.

    There is intentionally NO user-facing API-key handling here.
    """

    if api_key and str(api_key).strip():
        return str(api_key).strip()

    environment_key = os.getenv(
        "GEMINI_API_KEY",
        ""
    ).strip()

    if environment_key:
        return environment_key

    raise RuntimeError(
        "AI service is not configured."
    )


def _load_prompt(path: Path) -> str:
    """
    Load an XML prompt from the application folder.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Required AI prompt file is missing: {path.name}"
        )

    text = path.read_text(
        encoding="utf-8"
    ).strip()

    if not text:
        raise ValueError(
            f"AI prompt file is empty: {path.name}"
        )

    return text


def _clean_json_response(text: str) -> str:
    """
    Remove accidental Markdown code fences from an AI response.
    """

    text = (text or "").strip()

    if not text:
        raise ValueError(
            "AI returned an empty response."
        )

    # Handle ```json ... ```
    if text.startswith("```json"):
        text = text[len("```json"):].strip()

    # Handle ``` ... ```
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def _parse_json_response(text: str) -> dict:
    """
    Convert AI JSON response into a Python dictionary.
    """

    cleaned = _clean_json_response(
        text
    )

    try:
        result = json.loads(
            cleaned
        )

    except json.JSONDecodeError as error:

        raise ValueError(
            "AI returned an invalid structured response."
        ) from error

    if not isinstance(result, dict):

        raise ValueError(
            "AI response was not a JSON object."
        )

    return result


def _create_client(api_key: Optional[str] = None):
    """
    Create the AI client using the server-side API key.
    """

    key = _get_api_key(
        api_key
    )

    return genai.Client(
        api_key=key
    )


# ============================================================
# PHOTO ANALYSIS
# ============================================================

def analyze_photo(
    image_bytes: bytes,
    mime_type: str,
    api_key: Optional[str] = None,
    note: str = ""
) -> dict:
    """
    Analyze one road/site photograph.

    Parameters
    ----------
    image_bytes:
        Raw image bytes.

    mime_type:
        Example:
        image/jpeg
        image/png
        image/webp

    api_key:
        Optional server-side key.
        Normally the application should leave this as None.

    note:
        Optional engineer/site note.

    Returns
    -------
    dict
        Structured road analysis.
    """

    if not image_bytes:
        raise ValueError(
            "No image was provided."
        )

    if not mime_type:
        mime_type = "image/jpeg"

    # --------------------------------------------------------
    # CREATE CLIENT
    # --------------------------------------------------------

    client = _create_client(
        api_key
    )

    # --------------------------------------------------------
    # LOAD PHOTO PROMPT
    # --------------------------------------------------------

    system_prompt = _load_prompt(
        PHOTO_PROMPT_PATH
    )

    # --------------------------------------------------------
    # USER MESSAGE
    # --------------------------------------------------------

    user_text = (
        "Analyse this road/site photo according "
        "to the provided instructions."
    )

    if note and note.strip():

        user_text += (
            "\n\nEngineer's site note: "
            + note.strip()
        )

    # --------------------------------------------------------
    # GENERATE RESPONSE
    # --------------------------------------------------------

    try:

        response = client.models.generate_content(

            model=MODEL,

            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                ),
                user_text
            ],

            config=types.GenerateContentConfig(

                system_instruction=system_prompt,

                response_mime_type="application/json",

                temperature=0.2
            )
        )

    except Exception as error:

        # Do NOT expose provider/API details to the user.
        raise RuntimeError(
            "AI photo analysis is temporarily unavailable."
        ) from error

    # --------------------------------------------------------
    # READ RESPONSE
    # --------------------------------------------------------

    text = (
        response.text or ""
    ).strip()

    if not text:

        raise RuntimeError(
            "AI photo analysis returned no result."
        )

    # --------------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------------

    return _parse_json_response(
        text
    )


# ============================================================
# CHAT ASSISTANT
# ============================================================

def chat_reply(
    history: list,
    api_key: Optional[str] = None,
    analysis: Optional[dict] = None,
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg"
) -> str:
    """
    Generate a response for the Road Project Chat Assistant.

    history format:

    [
        {
            "role": "user",
            "content": "..."
        },
        {
            "role": "assistant",
            "content": "..."
        }
    ]

    The function remains compatible with the existing app.py.
    """

    if not history:
        return (
            "Please enter your road project question."
        )

    # --------------------------------------------------------
    # CREATE CLIENT
    # --------------------------------------------------------

    client = _create_client(
        api_key
    )

    # --------------------------------------------------------
    # LOAD CHAT PROMPT
    # --------------------------------------------------------

    system_prompt = _load_prompt(
        CHAT_PROMPT_PATH
    )

    # --------------------------------------------------------
    # ADD PHOTO ANALYSIS
    # --------------------------------------------------------

    if analysis:

        try:

            analysis_json = json.dumps(
                analysis,
                ensure_ascii=False
            )

        except (TypeError, ValueError):

            analysis_json = "{}"

        system_prompt += (
            "\n\n"
            "<photo_analysis>\n"
            + analysis_json
            + "\n</photo_analysis>"
        )

    # --------------------------------------------------------
    # PREPARE HISTORY
    # --------------------------------------------------------

    contents = []

    for index, message in enumerate(history):

        if not isinstance(
            message,
            dict
        ):
            continue

        role = message.get(
            "role",
            "user"
        )

        content = message.get(
            "content",
            ""
        )

        if content is None:
            content = ""

        content = str(
            content
        ).strip()

        if not content:
            continue

        parts = [

            types.Part.from_text(
                text=content
            )

        ]

        # ----------------------------------------------------
        # Attach image only to first user message
        # ----------------------------------------------------

        if (
            index == 0
            and role == "user"
            and image_bytes
        ):

            parts.insert(

                0,

                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type or "image/jpeg"
                )

            )

        gemini_role = (
            "user"
            if role == "user"
            else "model"
        )

        contents.append(

            types.Content(
                role=gemini_role,
                parts=parts
            )

        )

    # --------------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------------

    if not contents:

        return (
            "Please enter a road project question."
        )

    # --------------------------------------------------------
    # GENERATE CHAT RESPONSE
    # --------------------------------------------------------

    try:

        response = client.models.generate_content(

            model=MODEL,

            contents=contents,

            config=types.GenerateContentConfig(

                system_instruction=system_prompt,

                temperature=0.5

            )

        )

    except Exception as error:

        # Keep technical/provider information hidden.
        raise RuntimeError(
            "The road assistant is temporarily unavailable."
        ) from error

    # --------------------------------------------------------
    # RETURN ANSWER
    # --------------------------------------------------------

    answer = (
        response.text or ""
    ).strip()

    if not answer:

        return (
            "I could not generate a response right now. "
            "Please try again."
        )

    return answer
