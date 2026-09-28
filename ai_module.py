"""
AI module for the Road Cost Estimator.

This file handles:
1. Road photo analysis using Gemini
2. Chat Assistant using Gemini
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

# Your XML files are currently in the SAME folder as ai_module.py
PHOTO_PROMPT_PATH = BASE_DIR / "road_photo_prompt.xml"
CHAT_PROMPT_PATH = BASE_DIR / "chat_prompt.xml"


# ============================================================
# GEMINI MODEL
# ============================================================

MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


# ============================================================
# LOAD PROMPT FILE
# ============================================================

def load_prompt(file_path):
    """
    Read an XML prompt file.
    """

    if not file_path.exists():

        raise FileNotFoundError(
            f"Prompt file not found: {file_path.name}"
        )

    return file_path.read_text(
        encoding="utf-8"
    )


# ============================================================
# ANALYZE ROAD PHOTO
# ============================================================

def analyze_photo(
    image_bytes: bytes,
    mime_type: str,
    api_key: str,
    note: str = ""
) -> dict:

    """
    Send a road photo to Gemini and receive
    structured JSON analysis.
    """

    if not api_key:
        raise ValueError(
            "Gemini API key is missing."
        )


    # --------------------------------------------------------
    # CREATE GEMINI CLIENT
    # --------------------------------------------------------

    client = genai.Client(
        api_key=api_key
    )


    # --------------------------------------------------------
    # LOAD PHOTO PROMPT
    # --------------------------------------------------------

    system_prompt = load_prompt(
        PHOTO_PROMPT_PATH
    )


    # --------------------------------------------------------
    # USER MESSAGE
    # --------------------------------------------------------

    user_text = (
        "Analyse this road photo according "
        "to the instructions provided."
    )


    if note and note.strip():

        user_text += (
            "\n\nEngineer's additional note: "
            + note.strip()
        )


    # --------------------------------------------------------
    # SEND REQUEST TO GEMINI
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
    # GET RESPONSE TEXT
    # --------------------------------------------------------

    text = (
        response.text or ""
    ).strip()


    if not text:

        raise ValueError(
            "Gemini returned an empty response."
        )


    # --------------------------------------------------------
    # REMOVE MARKDOWN CODE BLOCK IF PRESENT
    # --------------------------------------------------------

    if text.startswith("```json"):

        text = text[
            len("```json"):
        ]

    elif text.startswith("```"):

        text = text[
            len("```"):
        ]


    if text.endswith("```"):

        text = text[
            :-len("```")
        ]


    text = text.strip()


    # --------------------------------------------------------
    # CONVERT JSON TEXT TO PYTHON DICTIONARY
    # --------------------------------------------------------

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError as error:

        raise ValueError(
            "Gemini returned invalid JSON."
        ) from error


    return result


# ============================================================
# CHAT ASSISTANT
# ============================================================

def chat_reply(
    history: list,
    api_key: str,
    analysis: dict | None = None,
    image_bytes: bytes | None = None,
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
    """

    if not api_key:

        raise ValueError(
            "Gemini API key is missing."
        )


    # --------------------------------------------------------
    # CREATE GEMINI CLIENT
    # --------------------------------------------------------

    client = genai.Client(
        api_key=api_key
    )


    # --------------------------------------------------------
    # LOAD CHAT PROMPT
    # --------------------------------------------------------

    system_prompt = load_prompt(
        CHAT_PROMPT_PATH
    )


    # --------------------------------------------------------
    # ADD PHOTO ANALYSIS TO CHAT CONTEXT
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
    # PREPARE CHAT HISTORY
    # --------------------------------------------------------

    contents = []


    for index, message in enumerate(history):

        role = message.get(
            "role",
            "user"
        )

        content = message.get(
            "content",
            ""
        )


        parts = [

            types.Part.from_text(
                text=content
            )

        ]


        # ----------------------------------------------------
        # ATTACH PHOTO TO FIRST USER MESSAGE
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


        # ----------------------------------------------------
        # GEMINI ROLE
        # ----------------------------------------------------

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
    # SEND CHAT REQUEST
    # --------------------------------------------------------

    response = client.models.generate_content(

        model=MODEL,

        contents=contents,

        config=types.GenerateContentConfig(

            system_instruction=system_prompt,

            temperature=0.5

        )

    )


    # --------------------------------------------------------
    # RETURN RESPONSE
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
