"""
AI backend module for the Road Cost Estimator.

This file handles:
1. Road photo analysis
2. Road project chat assistant

IMPORTANT:
- API keys are NEVER requested from the website user.
- The API key is read only from Streamlit secrets or environment variables.
- The AI provider is intentionally hidden from the user interface.
"""

import json
import os
from pathlib import Path

from google import genai
from google.genai import types


# ============================================================
# FILE LOCATIONS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PHOTO_PROMPT_PATH = BASE_DIR / "road_photo_prompt.xml"
CHAT_PROMPT_PATH = BASE_DIR / "chat_prompt.xml"


# ============================================================
# MODEL
# ============================================================

MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


# ============================================================
# INTERNAL API KEY
# ============================================================

def get_api_key():
    """
    Get the AI API key from backend configuration.

    Priority:
    1. Streamlit secrets
    2. Environment variable

    The user never enters the key in the UI.
    """

    # --------------------------------------------------------
    # Try Streamlit Secrets
    # --------------------------------------------------------

    try:
        import streamlit as st

        key = st.secrets.get(
            "GEMINI_API_KEY",
            ""
        )

        if key:
            return str(key).strip()

    except Exception:
        pass


    # --------------------------------------------------------
    # Try Environment Variable
    # --------------------------------------------------------

    key = os.getenv(
        "GEMINI_API_KEY",
        ""
    )

    if key:
        return key.strip()


    return ""


# ============================================================
# PROMPT LOADER
# ============================================================

def load_prompt(file_path: Path) -> str:
    """
    Load an XML prompt file.
    """

    if not file_path.exists():

        raise FileNotFoundError(
            f"Required AI prompt file is missing: {file_path.name}"
        )

    return file_path.read_text(
        encoding="utf-8"
    )


# ============================================================
# JSON CLEANER
# ============================================================

def clean_json_response(text: str) -> str:
    """
    Remove accidental Markdown code fences from an AI response.
    """

    text = (text or "").strip()

    if not text:
        return ""

    if text.startswith("```json"):

        text = text[len("```json"):]

    elif text.startswith("```"):

        text = text[len("```"):]

    if text.endswith("```"):

        text = text[:-3]

    return text.strip()


# ============================================================
# PHOTO ANALYSIS
# ============================================================

def analyze_photo(
    image_bytes: bytes,
    mime_type: str,
    api_key: str | None = None,
    note: str = ""
) -> dict:
    """
    Analyze one road photograph.

    The API key argument is retained for compatibility with
    existing app.py versions, but the website should not ask
    the user for it.

    The actual key is obtained from backend configuration.
    """

    # --------------------------------------------------------
    # Use backend key
    # --------------------------------------------------------

    backend_key = get_api_key()

    if not backend_key:

        raise RuntimeError(
            "AI analysis is currently unavailable."
        )


    # --------------------------------------------------------
    # Validate image
    # --------------------------------------------------------

    if not image_bytes:

        raise ValueError(
            "No image data was provided."
        )


    # --------------------------------------------------------
    # Create client
    # --------------------------------------------------------

    client = genai.Client(
        api_key=backend_key
    )


    # --------------------------------------------------------
    # Load prompt
    # --------------------------------------------------------

    system_prompt = load_prompt(
        PHOTO_PROMPT_PATH
    )


    # --------------------------------------------------------
    # User message
    # --------------------------------------------------------

    user_text = (
        "Analyse this road/site photograph according "
        "to the instructions provided."
    )


    if note and note.strip():

        user_text += (
            "\n\nEngineer's additional note: "
            + note.strip()
        )


    # --------------------------------------------------------
    # Gemini request
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Read response
    # --------------------------------------------------------

    text = clean_json_response(
        response.text
    )


    if not text:

        raise RuntimeError(
            "AI analysis returned no result."
        )


    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            "AI analysis returned an invalid result."
        ) from error


    if not isinstance(
        result,
        dict
    ):

        raise RuntimeError(
            "AI analysis returned an unexpected format."
        )


    return result


# ============================================================
# MULTI-PHOTO ANALYSIS
# ============================================================

def analyze_photos(
    photos: list,
    note: str = ""
) -> list:
    """
    Analyze multiple uploaded photos.

    Expected photo format:

    {
        "name": "...",
        "bytes": b"...",
        "mime": "image/jpeg"
    }

    Returns:

    [
        {
            "name": "...",
            "result": {...}
        }
    ]
    """

    results = []


    for photo in photos:

        name = photo.get(
            "name",
            "Photo"
        )

        image_bytes = photo.get(
            "bytes"
        )

        mime_type = photo.get(
            "mime",
            "image/jpeg"
        )


        try:

            result = analyze_photo(

                image_bytes=image_bytes,

                mime_type=mime_type,

                note=note

            )

            results.append(

                {
                    "name": name,
                    "result": result
                }

            )


        except Exception:

            # Do not expose provider/API details
            # to the website user.

            results.append(

                {
                    "name": name,

                    "result": {

                        "photo_quality": (
                            "poor - analysis unavailable"
                        ),

                        "site_type": {

                            "value": "unclear",

                            "confidence": "low"

                        },

                        "recommended_mode": {

                            "value": "unclear",

                            "confidence": "low",

                            "reason": (
                                "Photo could not be "
                                "automatically analysed."
                            )

                        },

                        "road_type": {

                            "value": "unclear",

                            "confidence": "low"

                        },

                        "surface_condition": (
                            "Manual site review required."
                        ),

                        "defects": [],

                        "suggested_works": [],

                        "suggested_parameters": [],

                        "limitations": (
                            "Automatic photo analysis "
                            "was unavailable."
                        )

                    }

                }

            )


    return results


# ============================================================
# CHAT ASSISTANT
# ============================================================

def chat_reply(
    history: list,
    api_key: str | None = None,
    analysis: dict | None = None,
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg"
) -> str:
    """
    Generate a response from the road project assistant.

    API key is obtained internally.
    """

    # --------------------------------------------------------
    # Backend API key
    # --------------------------------------------------------

    backend_key = get_api_key()

    if not backend_key:

        return (
            "The road assistant is temporarily unavailable. "
            "Please try again later."
        )


    # --------------------------------------------------------
    # Create client
    # --------------------------------------------------------

    client = genai.Client(
        api_key=backend_key
    )


    # --------------------------------------------------------
    # Load chat prompt
    # --------------------------------------------------------

    system_prompt = load_prompt(
        CHAT_PROMPT_PATH
    )


    # --------------------------------------------------------
    # Add photo analysis
    # --------------------------------------------------------

    if analysis:

        system_prompt += (
            "\n\n<photo_analysis>\n"
            + json.dumps(
                analysis,
                ensure_ascii=False
            )
            + "\n</photo_analysis>"
        )


    # --------------------------------------------------------
    # Prepare history
    # --------------------------------------------------------

    contents = []


    for index, message in enumerate(
        history
    ):

        role = message.get(
            "role",
            "user"
        )

        content = message.get(
            "content",
            ""
        )


        if not content:

            content = "Please continue."


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

                    mime_type=mime_type

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
    # Prevent empty conversation
    # --------------------------------------------------------

    if not contents:

        contents = [

            types.Content(

                role="user",

                parts=[

                    types.Part.from_text(
                        text=(
                            "Help me plan this road project."
                        )
                    )

                ]

            )

        ]


    # --------------------------------------------------------
    # Send request
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

    except Exception:

        # Never expose API/provider error details.

        return (
            "The road assistant is temporarily "
            "unavailable. Please try again later."
        )


    # --------------------------------------------------------
    # Return response
    # --------------------------------------------------------

    answer = (
        response.text or ""
    ).strip()


    if not answer:

        return (
            "I could not generate a response. "
            "Please try again."
        )


    return answer
