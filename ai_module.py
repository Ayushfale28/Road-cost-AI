"""
AI module for the Road Cost Estimator.

Gemini is OPTIONAL.

If a Gemini API key is available:
    - Road photos can be analyzed using Gemini.
    - Chat Assistant uses Gemini.

If no Gemini API key is available:
    - The application continues to work.
    - Photo analysis uses a safe fallback.
    - Chat Assistant uses a rule-based road-planning assistant.
"""

import json
import os
from pathlib import Path


# ============================================================
# OPTIONAL GEMINI IMPORT
# ============================================================

try:
    from google import genai
    from google.genai import types

    GEMINI_AVAILABLE = True

except ImportError:
    GEMINI_AVAILABLE = False


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

        return ""

    return file_path.read_text(
        encoding="utf-8"
    )


# ============================================================
# CHECK GEMINI
# ============================================================

def gemini_is_available(api_key=None):
    """
    Returns True only when Gemini package and API key
    are both available.
    """

    if not GEMINI_AVAILABLE:
        return False

    if api_key and api_key.strip():
        return True

    return False


# ============================================================
# ROAD PHOTO FALLBACK ANALYSIS
# ============================================================

def fallback_photo_analysis(note=""):
    """
    Safe fallback when Gemini API is not available.

    IMPORTANT:
    This does NOT pretend that an image was analyzed by AI.
    """

    observations = [
        "Photo analysis is not available because no Gemini API key was provided.",
        "The uploaded image should be reviewed by the site engineer.",
        "Do not use this result as a final engineering decision."
    ]

    if note and note.strip():

        observations.append(
            "Engineer's note: " + note.strip()
        )

    return {

        "recommended_mode": None,

        "confidence": "not_available",

        "observations": observations,

        "source": "manual_review_required",

        "message": (
            "I cannot reliably determine whether this is "
            "road repair or new construction without AI "
            "photo analysis. Please confirm the work type."
        )

    }


# ============================================================
# ANALYZE ROAD PHOTO
# ============================================================

def analyze_photo(
    image_bytes: bytes,
    mime_type: str,
    api_key: str = "",
    note: str = ""
) -> dict:

    """
    Analyze road photo.

    If Gemini API key exists:
        Use Gemini.

    If Gemini API key does not exist:
        Return safe fallback.
    """

    # --------------------------------------------------------
    # NO GEMINI KEY
    # --------------------------------------------------------

    if not gemini_is_available(api_key):

        return fallback_photo_analysis(
            note=note
        )


    # --------------------------------------------------------
    # CREATE GEMINI CLIENT
    # --------------------------------------------------------

    try:

        client = genai.Client(
            api_key=api_key.strip()
        )

    except Exception:

        return fallback_photo_analysis(
            note=note
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

        return {

            "recommended_mode": None,

            "confidence": "not_available",

            "observations": [
                "Gemini photo analysis could not be completed.",
                "Please review the uploaded photo manually.",
                "Site engineer confirmation is required."
            ],

            "source": "gemini_error",

            "error": str(error)

        }


    # --------------------------------------------------------
    # GET RESPONSE TEXT
    # --------------------------------------------------------

    text = (
        response.text or ""
    ).strip()


    if not text:

        return fallback_photo_analysis(
            note=note
        )


    # --------------------------------------------------------
    # REMOVE MARKDOWN CODE BLOCK
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
    # CONVERT JSON
    # --------------------------------------------------------

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError:

        return {

            "recommended_mode": None,

            "confidence": "not_available",

            "observations": [
                "The AI response could not be interpreted safely.",
                "Please review the photo manually."
            ],

            "source": "invalid_ai_response"

        }


    # --------------------------------------------------------
    # SAFETY DEFAULTS
    # --------------------------------------------------------

    if not isinstance(result, dict):

        return fallback_photo_analysis(
            note=note
        )


    result.setdefault(
        "recommended_mode",
        None
    )

    result.setdefault(
        "confidence",
        "unknown"
    )

    result.setdefault(
        "observations",
        []
    )

    result.setdefault(
        "source",
        "gemini"
    )


    return result


# ============================================================
# RULE-BASED CHAT ASSISTANT
# ============================================================

def fallback_chat_reply(
    history,
    analysis=None
):
    """
    Road-planning assistant that works without Gemini.

    It does not calculate quantities, rates or costs.
    """

    if not history:

        return (
            "Namaste! I can help you plan the road work. "
            "First, is this repair of an existing road "
            "or construction of a new road?"
        )


    last_message = history[-1]

    user_text = str(
        last_message.get(
            "content",
            ""
        )
    ).strip()


    text = user_text.lower()


    # ========================================================
    # WORK TYPE
    # ========================================================

    repair_words = [
        "repair",
        "maintenance",
        "existing road",
        "damaged road",
        "road damage",
        "pothole",
        "patch"
    ]

    new_words = [
        "new road",
        "new construction",
        "construct",
        "construction",
        "build road"
    ]


    if any(word in text for word in repair_words):

        return (
            "Okay, we will consider this as repair/maintenance "
            "of an existing road. What is the approximate "
            "road length?"
        )


    if any(word in text for word in new_words):

        return (
            "Okay, we will consider this as a new road. "
            "Do you want a CC (concrete) road or a dambar "
            "(bitumen) road?"
        )


    # ========================================================
    # CC / BITUMEN
    # ========================================================

    if (
        "cc" in text
        or "concrete" in text
    ):

        return (
            "Got it — CC road. What is the approximate "
            "road length?"
        )


    if (
        "bitumen" in text
        or "dambar" in text
        or "asphalt" in text
    ):

        return (
            "Got it — bitumen/dambar road. What is the "
            "approximate road length?"
        )


    # ========================================================
    # LENGTH
    # ========================================================

    if (
        "km" in text
        or "meter" in text
        or "metre" in text
        or "length" in text
    ):

        return (
            "Thank you. Now, what is the approximate "
            "road width?"
        )


    # ========================================================
    # WIDTH
    # ========================================================

    if "width" in text:

        return (
            "Thank you. What layer thickness has been "
            "specified or proposed by the site engineer?"
        )


    # ========================================================
    # THICKNESS
    # ========================================================

    if (
        "thickness" in text
        or "mm" in text
        or "cm" in text
    ):

        return (
            "Noted. What type of traffic is expected on "
            "this road — light, medium, or heavy?"
        )


    # ========================================================
    # TRAFFIC
    # ========================================================

    if (
        "traffic" in text
        or "heavy" in text
        or "medium" in text
        or "light" in text
    ):

        return (
            "Okay. What is the soil or sub-grade condition "
            "at the site?"
        )


    # ========================================================
    # SOIL
    # ========================================================

    if (
        "soil" in text
        or "subgrade" in text
        or "sub-grade" in text
        or "black soil" in text
        or "clay" in text
        or "murum" in text
    ):

        return (
            "Understood. Is any drainage work or culvert "
            "required at the site?"
        )


    # ========================================================
    # DRAINAGE
    # ========================================================

    if (
        "drainage" in text
        or "culvert" in text
        or "cross drainage" in text
        or "cd work" in text
    ):

        return (
            "Noted. What is the approximate lead distance "
            "for bringing construction materials to the site?"
        )


    # ========================================================
    # LEAD
    # ========================================================

    if (
        "lead" in text
        or "distance" in text
        or "transport" in text
    ):

        return (
            "Thank you. For the estimate, you can now select "
            "the relevant items in the Estimate tab. "
            "Check the applicable SSR chapters such as Road "
            "Sub grade, Road Sub Base and Base Course, "
            "Rigid Pavement, Road Surfacing Course, Road "
            "Maintenance, or Cross Drainage Works."
        )


    # ========================================================
    # SSR QUESTIONS
    # ========================================================

    if (
        "ssr" in text
        or "rate" in text
        or "cost" in text
        or "item number" in text
    ):

        return (
            "Please select the required item from the SSR "
            "file in the Estimate tab. I will not invent "
            "SSR item numbers, rates, quantities, or costs."
        )


    # ========================================================
    # ESTIMATE QUESTIONS
    # ========================================================

    if (
        "estimate" in text
        or "quantity" in text
    ):

        return (
            "The Estimate tab should be used for selecting "
            "the applicable SSR items and rates. Please verify "
            "the engineering measurements with the site engineer."
        )


    # ========================================================
    # PHOTO ANALYSIS
    # ========================================================

    if (
        "photo" in text
        or "image" in text
    ):

        return (
            "The photo can provide a helpful indication, but "
            "it should not replace the site engineer's judgment. "
            "Please confirm whether the work is repair or "
            "new construction."
        )


    # ========================================================
    # DEFAULT
    # ========================================================

    return (
        "I can help you collect the road-planning information. "
        "First, is this repair of an existing road or "
        "construction of a new road?"
    )


# ============================================================
# CHAT ASSISTANT
# ============================================================

def chat_reply(
    history: list,
    api_key: str = "",
    analysis: dict | None = None,
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg"
) -> str:

    """
    Generate a response for the Road Project Chat Assistant.

    Gemini is optional.

    Without Gemini:
        Uses fallback road-planning assistant.
    """

    # ========================================================
    # NO GEMINI
    # ========================================================

    if not gemini_is_available(api_key):

        return fallback_chat_reply(
            history=history,
            analysis=analysis
        )


    # ========================================================
    # CREATE GEMINI CLIENT
    # ========================================================

    try:

        client = genai.Client(
            api_key=api_key.strip()
        )

    except Exception:

        return fallback_chat_reply(
            history=history,
            analysis=analysis
        )


    # ========================================================
    # LOAD CHAT PROMPT
    # ========================================================

    system_prompt = load_prompt(
        CHAT_PROMPT_PATH
    )


    # ========================================================
    # ADD PHOTO ANALYSIS
    # ========================================================

    if analysis:

        system_prompt += (
            "\n\n<photo_analysis>\n"
            + json.dumps(
                analysis,
                ensure_ascii=False
            )
            + "\n</photo_analysis>"
        )


    # ========================================================
    # PREPARE CHAT HISTORY
    # ========================================================

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


    # ========================================================
    # SEND CHAT REQUEST
    # ========================================================

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

        return fallback_chat_reply(
            history=history,
            analysis=analysis
        )


    # ========================================================
    # RETURN RESPONSE
    # ========================================================

    answer = (
        response.text or ""
    ).strip()


    if not answer:

        return fallback_chat_reply(
            history=history,
            analysis=analysis
        )


    return answer
