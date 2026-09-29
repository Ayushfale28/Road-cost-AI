"""
AI backend module for the Road Cost Estimator.

This version uses OpenRouter instead of the Gemini SDK.

IMPORTANT:
- API keys are NEVER requested from the website user.
- The OpenRouter API key is read only from Streamlit Secrets or
  environment variables.
- The AI provider is intentionally hidden from the website UI.
- The default model is OpenRouter's free router, which can select
  a currently available free model that supports the request.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


# ============================================================
# FILE LOCATIONS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PHOTO_PROMPT_PATH = BASE_DIR / "road_photo_prompt.xml"
CHAT_PROMPT_PATH = BASE_DIR / "chat_prompt.xml"


# ============================================================
# OPENROUTER SETTINGS
# ============================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Can be overridden in Streamlit Secrets:
# OPENROUTER_MODEL = "some-model-slug"
#
# openrouter/free automatically selects a currently available
# free model and supports text/image requests.
MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)

SITE_URL = os.getenv(
    "OPENROUTER_SITE_URL",
    ""
)

SITE_NAME = os.getenv(
    "OPENROUTER_SITE_NAME",
    "Road Cost Estimator"
)


# ============================================================
# INTERNAL API KEY
# ============================================================

def get_api_key():
    """
    Get the OpenRouter API key from backend configuration.

    Priority:
    1. Streamlit Secrets
    2. Environment variable

    The user never enters the key in the UI.
    """

    # --------------------------------------------------------
    # Streamlit Secrets
    # --------------------------------------------------------

    try:
        import streamlit as st

        key = st.secrets.get(
            "OPENROUTER_API_KEY",
            ""
        )

        if key:
            return str(key).strip()

    except Exception:
        pass

    # --------------------------------------------------------
    # Environment variable
    # --------------------------------------------------------

    key = os.getenv(
        "OPENROUTER_API_KEY",
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
    Clean common formatting mistakes from an AI JSON response.
    """

    text = (text or "").strip()

    if not text:
        return ""

    # Remove Markdown fences.
    if text.startswith("```json"):
        text = text[len("```json"):].strip()

    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    # Some models occasionally add text before the JSON object.
    # Find the first JSON object and parse it from there.
    first_brace = text.find("{")

    if first_brace > 0:
        text = text[first_brace:]

    return text.strip()


def parse_json_response(text: str) -> dict:
    """
    Parse a JSON object robustly.

    This handles:
    - normal JSON
    - Markdown fenced JSON
    - accidental text after the JSON object
    """

    cleaned = clean_json_response(text)

    if not cleaned:
        raise RuntimeError(
            "AI analysis returned no result."
        )

    try:
        result = json.loads(cleaned)

    except json.JSONDecodeError:
        # Try JSONDecoder.raw_decode so trailing text does not
        # break an otherwise valid JSON object.
        try:
            decoder = json.JSONDecoder()
            result, _ = decoder.raw_decode(cleaned)

        except Exception as error:
            raise RuntimeError(
                "AI analysis returned an invalid result."
            ) from error

    if not isinstance(result, dict):
        raise RuntimeError(
            "AI analysis returned an unexpected format."
        )

    return result


# ============================================================
# OPENROUTER REQUEST
# ============================================================

def _openrouter_request(
    messages,
    system_prompt="",
    temperature=0.2,
    json_mode=False
):
    """
    Send a request to OpenRouter.

    Uses Python's standard library so no additional HTTP
    package is required.
    """

    api_key = get_api_key()

    if not api_key:
        raise RuntimeError(
            "AI service is not configured."
        )

    payload_messages = []

    if system_prompt:
        payload_messages.append(
            {
                "role": "system",
                "content": system_prompt
            }
        )

    payload_messages.extend(messages)

    payload = {
        "model": MODEL,
        "messages": payload_messages,
        "temperature": temperature
    }

    # Ask the model/router for JSON when the photo-analysis
    # prompt requires JSON.
    if json_mode:
        payload["response_format"] = {
            "type": "json_object"
        }

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Optional OpenRouter attribution headers.
    if SITE_URL:
        headers["HTTP-Referer"] = SITE_URL

    if SITE_NAME:
        headers["X-Title"] = SITE_NAME

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=120
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="replace"
            )

    except urllib.error.HTTPError as error:

        # Do not expose provider/API details to the user.
        # Keep details available internally for debugging logs.
        try:
            error_body = error.read().decode(
                "utf-8",
                errors="replace"
            )
        except Exception:
            error_body = ""

        print(
            "OpenRouter HTTP error:",
            error.code,
            error_body[:1000]
        )

        raise RuntimeError(
            "AI request failed."
        ) from error

    except Exception as error:

        print(
            "OpenRouter connection error:",
            repr(error)
        )

        raise RuntimeError(
            "AI request failed."
        ) from error

    try:
        data = json.loads(raw)

    except json.JSONDecodeError as error:

        print(
            "OpenRouter returned invalid JSON:",
            raw[:1000]
        )

        raise RuntimeError(
            "AI request returned an invalid response."
        ) from error

    # OpenRouter normally returns:
    # choices[0].message.content
    try:
        content = data["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError) as error:

        print(
            "Unexpected OpenRouter response:",
            str(data)[:1500]
        )

        raise RuntimeError(
            "AI request returned an unexpected response."
        ) from error

    # Some providers can return structured content in a list.
    if isinstance(content, list):

        text_parts = []

        for part in content:

            if isinstance(part, dict):

                if part.get("type") == "text":
                    text_parts.append(
                        str(part.get("text", ""))
                    )

                elif "text" in part:
                    text_parts.append(
                        str(part["text"])
                    )

            elif isinstance(part, str):
                text_parts.append(part)

        content = "\n".join(
            text_parts
        )

    if not isinstance(content, str):
        content = str(content)

    return content.strip()


# ============================================================
# IMAGE DATA URL
# ============================================================

def _image_to_data_url(
    image_bytes: bytes,
    mime_type: str
) -> str:
    """
    Convert uploaded image bytes to a base64 data URL.

    OpenRouter accepts base64 image data in image_url content.
    """

    if not image_bytes:
        raise ValueError(
            "No image data was provided."
        )

    safe_mime = (
        mime_type
        or "image/jpeg"
    ).lower().strip()

    # Keep only known image MIME types.
    allowed = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif"
    }

    if safe_mime not in allowed:
        safe_mime = "image/jpeg"

    encoded = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    return (
        f"data:{safe_mime};base64,{encoded}"
    )


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

    The api_key argument is retained only for compatibility
    with existing app.py versions. It is intentionally ignored.

    The actual key always comes from Streamlit Secrets or
    the server environment.
    """

    if not image_bytes:
        raise ValueError(
            "No image data was provided."
        )

    # --------------------------------------------------------
    # Load prompt
    # --------------------------------------------------------

    system_prompt = load_prompt(
        PHOTO_PROMPT_PATH
    )

    # --------------------------------------------------------
    # User instruction
    # --------------------------------------------------------

    user_text = (
        "Analyse this road/site photograph according "
        "to the instructions provided. "
        "Return ONLY the required JSON object."
    )

    if note and note.strip():
        user_text += (
            "\n\nEngineer's additional note: "
            + note.strip()
        )

    # --------------------------------------------------------
    # Image message
    # --------------------------------------------------------

    image_url = _image_to_data_url(
        image_bytes,
        mime_type
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_text
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url
                    }
                }
            ]
        }
    ]

    # --------------------------------------------------------
    # OpenRouter request
    # --------------------------------------------------------

    text = _openrouter_request(
        messages=messages,
        system_prompt=system_prompt,
        temperature=0.2,
        json_mode=True
    )

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    return parse_json_response(
        text
    )


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

        except Exception as error:

            # Keep provider/API details out of the website.
            print(
                f"Photo analysis failed for {name}:",
                repr(error)
            )

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
                        "new_road_notes": {
                            "terrain": "not visible",
                            "drainage_concerns": "uncertain",
                            "obstacles": "uncertain",
                            "cc_vs_bt_factors": (
                                "Manual engineering assessment required."
                            )
                        },
                        "road_type": {
                            "value": "unclear",
                            "confidence": "low"
                        },
                        "surface_condition": (
                            "Automatic analysis was unavailable."
                        ),
                        "defects": [],
                        "suggested_works": [],
                        "suggested_parameters": [],
                        "limitations": (
                            "Automatic photo analysis "
                            "was unavailable. Manual site "
                            "review is required."
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

    The api_key argument is retained for compatibility with
    existing app.py versions but is intentionally ignored.

    The actual key always comes from backend configuration.
    """

    try:

        # ----------------------------------------------------
        # Load chat prompt
        # ----------------------------------------------------

        system_prompt = load_prompt(
            CHAT_PROMPT_PATH
        )

        # ----------------------------------------------------
        # Add photo analysis context
        # ----------------------------------------------------

        if analysis:

            system_prompt += (
                "\n\n<photo_analysis>\n"
                + json.dumps(
                    analysis,
                    ensure_ascii=False
                )
                + "\n</photo_analysis>"
            )

        # ----------------------------------------------------
        # Prepare conversation history
        # ----------------------------------------------------

        messages = []

        for index, message in enumerate(
            history or []
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

            # Streamlit uses "assistant"; OpenRouter expects
            # "assistant" as well.
            openrouter_role = (
                "assistant"
                if role == "assistant"
                else "user"
            )

            # ------------------------------------------------
            # Attach image only to the first user message
            # ------------------------------------------------

            if (
                index == 0
                and openrouter_role == "user"
                and image_bytes
            ):

                image_url = _image_to_data_url(
                    image_bytes,
                    mime_type
                )

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": content
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                )

            else:

                messages.append(
                    {
                        "role": openrouter_role,
                        "content": content
                    }
                )

        # ----------------------------------------------------
        # Prevent empty conversation
        # ----------------------------------------------------

        if not messages:

            if image_bytes:

                image_url = _image_to_data_url(
                    image_bytes,
                    mime_type
                )

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Help me plan this "
                                    "road project."
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ]

            else:

                messages = [
                    {
                        "role": "user",
                        "content": (
                            "Help me plan this "
                            "road project."
                        )
                    }
                ]

        # ----------------------------------------------------
        # Send request
        # ----------------------------------------------------

        answer = _openrouter_request(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.5,
            json_mode=False
        )

        if not answer:

            return (
                "I could not generate a response. "
                "Please try again."
            )

        return answer

    except Exception as error:

        # Never expose API/provider details to the user.
        print(
            "Chat assistant error:",
            repr(error)
        )

        return (
            "The road assistant is temporarily "
            "unavailable. Please try again later."
        )
