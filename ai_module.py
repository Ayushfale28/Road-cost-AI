"""
AI module for the Road Cost Estimator.

This file handles:
1. Road photo analysis using Gemini
2. Road Project Chat Assistant using Gemini

The AI only provides suggestions.
Final engineering decisions must be made by the user/engineer.
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
# GEMINI MODEL
# ============================================================

MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)


# ============================================================
# PROMPT LOADER
# ============================================================

def load_prompt(file_path: Path) -> str:
    """
    Load an XML prompt file from the same folder
    as this Python file.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required prompt file was not found: "
            f"{file_path.name}"
        )

    try:
        return file_path.read_text(
            encoding="utf-8"
        )

    except Exception as error:
        raise RuntimeError(
            f"Could not read prompt file "
            f"'{file_path.name}': {error}"
        ) from error


# ============================================================
# GEMINI CLIENT
# ============================================================

def create_client(api_key: str):
    """
    Create and return a Gemini client.
    """

    if not api_key or not api_key.strip():
        raise ValueError(
            "Gemini API key is missing. "
            "Please provide a valid Gemini API key."
        )

    try:
        return genai.Client(
            api_key=api_key.strip()
        )

    except Exception as error:
        raise RuntimeError(
            f"Could not create Gemini client: {error}"
        ) from error


# ============================================================
# CLEAN GEMINI JSON RESPONSE
# ============================================================

def clean_json_response(text: str) -> str:
    """
    Clean a Gemini response before JSON parsing.

    Gemini should normally return pure JSON because
    response_mime_type is set to application/json.

    This function also handles accidental markdown
    code fences.
    """

    if not text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    # Remove ```json ... ```
    if text.startswith("```json"):
        text = text[len("```json"):].strip()

    # Remove ``` ... ```
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text


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
    Analyze a road/site photo using Gemini.

    Returns a Python dictionary containing the structured
    AI analysis defined in road_photo_prompt.xml.
    """

    # --------------------------------------------------------
    # VALIDATE IMAGE
    # --------------------------------------------------------

    if not image_bytes:
        raise ValueError(
            "No image was provided."
        )

    if not mime_type:
        mime_type = "image/jpeg"

    # --------------------------------------------------------
    # CREATE CLIENT
    # --------------------------------------------------------

    client = create_client(
        api_key
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
        "Analyse this site photo according to "
        "the instructions provided."
    )

    if note and note.strip():
        user_text += (
            "\n\nEngineer's additional note:\n"
            + note.strip()
        )

    # --------------------------------------------------------
    # SEND PHOTO TO GEMINI
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

        raise RuntimeError(
            f"Gemini photo analysis failed: {error}"
        ) from error

    # --------------------------------------------------------
    # GET RESPONSE
    # --------------------------------------------------------

    response_text = getattr(
        response,
        "text",
        None
    )

    if not response_text:

        raise ValueError(
            "Gemini did not return any photo analysis."
        )

    # --------------------------------------------------------
    # CLEAN RESPONSE
    # --------------------------------------------------------

    cleaned_text = clean_json_response(
        response_text
    )

    # --------------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------------

    try:

        result = json.loads(
            cleaned_text
        )

    except json.JSONDecodeError as error:

        raise ValueError(
            "Gemini returned an invalid JSON response. "
            "Please try analyzing the photo again."
        ) from error

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    if not isinstance(result, dict):

        raise ValueError(
            "Gemini returned an unexpected response format."
        )

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
    Generate a response from the Road Project Chat Assistant.

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

    The optional photo analysis is added as context.
    """

    # --------------------------------------------------------
    # CREATE CLIENT
    # --------------------------------------------------------

    client = create_client(
        api_key
    )

    # --------------------------------------------------------
    # LOAD CHAT PROMPT
    # --------------------------------------------------------

    system_prompt = load_prompt(
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

        except Exception:

            analysis_json = str(
                analysis
            )

        system_prompt += (
            "\n\n"
            "<photo_analysis>\n"
            + analysis_json
            + "\n</photo_analysis>"
        )

    # --------------------------------------------------------
    # PREPARE CHAT HISTORY
    # --------------------------------------------------------

    contents = []

    if not history:

        raise ValueError(
            "Chat history is empty."
        )

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

        if not content:
            continue

        # ----------------------------------------------------
        # CONVERT ROLE
        # ----------------------------------------------------

        if role == "assistant":
            gemini_role = "model"

        else:
            gemini_role = "user"

        # ----------------------------------------------------
        # TEXT PART
        # ----------------------------------------------------

        parts = [

            types.Part.from_text(
                text=str(content)
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

            if not mime_type:
                mime_type = "image/jpeg"

            parts.insert(

                0,

                types.Part.from_bytes(

                    data=image_bytes,

                    mime_type=mime_type

                )

            )

        # ----------------------------------------------------
        # ADD MESSAGE TO GEMINI HISTORY
        # ----------------------------------------------------

        contents.append(

            types.Content(

                role=gemini_role,

                parts=parts

            )

        )

    # --------------------------------------------------------
    # CHECK HISTORY
    # --------------------------------------------------------

    if not contents:

        raise ValueError(
            "No valid messages were found in chat history."
        )

    # --------------------------------------------------------
    # SEND CHAT REQUEST
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

        raise RuntimeError(
            f"Gemini chat request failed: {error}"
        ) from error

    # --------------------------------------------------------
    # GET RESPONSE
    # --------------------------------------------------------

    answer = getattr(
        response,
        "text",
        None
    )

    if not answer:

        return (
            "I could not generate a response right now. "
            "Please try again."
        )

    return answer.strip()


# ============================================================
# OPTIONAL MODEL INFORMATION
# ============================================================

def get_model_name() -> str:
    """
    Return the Gemini model currently being used.
    """

    return MODEL
