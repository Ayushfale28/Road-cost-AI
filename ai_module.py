"""
AI backend module for the Road Cost Estimator.

Uses OpenRouter (https://openrouter.ai) over plain HTTP -- no extra SDK
dependency required.

Privacy / security:
    - The end user is NEVER asked for an API key.
    - The key is read only from Streamlit secrets or an environment
      variable, inside this module.
    - The provider name and model name are never surfaced to the user;
      error messages are always generic.

Model selection:
    "openrouter/free" is a real OpenRouter router, but it selects a
    random free model on every request. Some of those models do not
    support image input or JSON-mode responses, which made photo
    analysis succeed sometimes and fail other times with no clear
    reason. To make behaviour predictable, this module instead tries a
    short, explicit list of known vision-capable free models in order,
    and falls back to the next one if a call fails.

Three-layer responsibility split (the AI never does arithmetic):
    1. analyze_photo / analyze_photos  -> understand the site (vision)
    2. generate_project_specification  -> turn a text description into
       structured work categories
    3. select_ssr_items                -> choose from a list of SSR
       candidates that Python already found by keyword search; the AI
       can only pick ids from that list, never invent one
    Quantities and costs are always calculated in quantity_engine.py,
    never by the AI.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PHOTO_PROMPT_PATH = BASE_DIR / "road_photo_prompt.xml"
CHAT_PROMPT_PATH = BASE_DIR / "chat_prompt.xml"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Ordered list of models to try. Each one is a specific, named model
# (not the random "openrouter/free" router) that is known to accept
# image input at the time this was written. Free-tier model
# availability on OpenRouter changes over time -- if all of these stop
# working, check https://openrouter.ai/models?fmt=cards&max_price=0
# and update this list.
DEFAULT_VISION_MODELS = [
    "qwen/qwen2.5-vl-72b-instruct:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "google/gemma-3-27b-it:free",
]

# For text-only chat, any of the vision models above also work fine, so
# the same list is reused.
DEFAULT_TEXT_MODELS = DEFAULT_VISION_MODELS

_env_models = os.getenv("OPENROUTER_MODELS", "").strip()
VISION_MODELS = [m.strip() for m in _env_models.split(",") if m.strip()] or DEFAULT_VISION_MODELS

SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")
SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "Road Cost Estimator")


# ============================================================
# API KEY (never exposed to the UI)
# ============================================================

def get_api_key() -> str:
    try:
        import streamlit as st
        key = st.secrets.get("OPENROUTER_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass

    return os.getenv("OPENROUTER_API_KEY", "").strip()


def ai_is_configured() -> bool:
    return bool(get_api_key())


# ============================================================
# PROMPT LOADING
# ============================================================

def load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required AI prompt file is missing: {path.name}")
    return path.read_text(encoding="utf-8")


# ============================================================
# JSON RESPONSE CLEANING / PARSING
# ============================================================

def clean_json_response(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    first_brace = text.find("{")
    if first_brace > 0:
        text = text[first_brace:]

    return text.strip()


def parse_json_response(text: str) -> dict:
    cleaned = clean_json_response(text)
    if not cleaned:
        raise RuntimeError("AI analysis returned no result.")

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            decoder = json.JSONDecoder()
            result, _ = decoder.raw_decode(cleaned)
        except Exception as error:
            raise RuntimeError("AI analysis returned an invalid result.") from error

    if not isinstance(result, dict):
        raise RuntimeError("AI analysis returned an unexpected format.")

    return result


# ============================================================
# LOW-LEVEL OPENROUTER CALL (single model, single attempt)
# ============================================================

def _call_model(model: str, messages, system_prompt: str, temperature: float, json_mode: bool) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("AI service is not configured.")

    payload_messages = []
    if system_prompt:
        payload_messages.append({"role": "system", "content": system_prompt})
    payload_messages.extend(messages)

    payload = {"model": model, "messages": payload_messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if SITE_URL:
        headers["HTTP-Referer"] = SITE_URL
    if SITE_NAME:
        headers["X-Title"] = SITE_NAME

    request = urllib.request.Request(OPENROUTER_URL, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""
        print(f"OpenRouter HTTP error ({model}):", error.code, error_body[:800])
        raise RuntimeError("AI request failed.") from error
    except Exception as error:
        print(f"OpenRouter connection error ({model}):", repr(error))
        raise RuntimeError("AI request failed.") from error

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        print("OpenRouter returned invalid JSON:", raw[:500])
        raise RuntimeError("AI request returned an invalid response.") from error

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        print("Unexpected OpenRouter response shape:", str(data)[:800])
        raise RuntimeError("AI request returned an unexpected response.") from error

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        content = "\n".join(parts)

    return str(content).strip()


def _request_with_fallback(messages, system_prompt: str, temperature: float, json_mode: bool,
                            models=None) -> str:
    """
    Try each model in order. For each model, try with json_mode first
    (if requested) and retry once without it, since some free models
    reject the response_format parameter outright rather than ignoring
    it.
    """
    models = models or VISION_MODELS
    last_error = None

    for model in models:
        attempts = [json_mode, False] if json_mode else [False]
        for attempt_json_mode in dict.fromkeys(attempts):  # de-dupe while keeping order
            try:
                return _call_model(model, messages, system_prompt, temperature, attempt_json_mode)
            except Exception as error:
                last_error = error
                continue

    raise last_error or RuntimeError("AI request failed.")


# ============================================================
# IMAGE ENCODING
# ============================================================

def _image_to_data_url(image_bytes: bytes, mime_type: str) -> str:
    if not image_bytes:
        raise ValueError("No image data was provided.")

    safe_mime = (mime_type or "image/jpeg").lower().strip()
    if safe_mime not in {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}:
        safe_mime = "image/jpeg"

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{safe_mime};base64,{encoded}"


# ============================================================
# PHOTO ANALYSIS
# ============================================================

def analyze_photo(image_bytes: bytes, mime_type: str, note: str = "") -> dict:
    """Analyze one road/site photograph. Raises on failure (caller decides the fallback)."""
    if not image_bytes:
        raise ValueError("No image data was provided.")

    system_prompt = load_prompt(PHOTO_PROMPT_PATH)

    user_text = "Analyse this road/site photograph according to the instructions provided. Return ONLY the required JSON object."
    if note and note.strip():
        user_text += f"\n\nEngineer's additional note: {note.strip()}"

    image_url = _image_to_data_url(image_bytes, mime_type)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
    }]

    text = _request_with_fallback(messages, system_prompt, temperature=0.2, json_mode=True)
    return parse_json_response(text)


def _unavailable_result(reason: str) -> dict:
    """A result with the exact schema analyze_photo produces on success,
    so the UI never has to special-case a failure shape."""
    return {
        "photo_quality": {"value": "poor", "reason": "analysis unavailable"},
        "site_type": {"value": "unclear", "confidence": "low"},
        "recommended_mode": {"value": "unclear", "confidence": "low", "reason": reason},
        "new_road_notes": {
            "terrain": "not_visible",
            "drainage_concerns": "uncertain",
            "obstacles": [],
            "cc_vs_bt_factors": "Manual engineering assessment required.",
        },
        "road_type": {"value": "unclear", "confidence": "low"},
        "surface_condition": "Automatic analysis was unavailable.",
        "defects": [],
        "suggested_works": [],
        "suggested_parameters": [],
        "limitations": "Automatic photo analysis was unavailable. Manual site review is required.",
    }


def analyze_photos(photos: list, note: str = "") -> list:
    """
    Analyze multiple photos. Each item: {"name": str, "bytes": bytes, "mime": str}.
    Returns [{"name": str, "result": dict}, ...] -- every result dict has
    the same schema whether analysis succeeded or not.
    """
    results = []
    for photo in photos:
        name = photo.get("name", "Photo")
        try:
            result = analyze_photo(photo.get("bytes"), photo.get("mime", "image/jpeg"), note)
        except Exception as error:
            print(f"Photo analysis failed for {name}:", repr(error))
            result = _unavailable_result("Photo could not be automatically analysed.")
        results.append({"name": name, "result": result})
    return results


# ============================================================
# CHAT ASSISTANT
# ============================================================

def chat_reply(history: list, analysis: dict | None = None,
               image_bytes: bytes | None = None, mime_type: str = "image/jpeg") -> str:
    try:
        system_prompt = load_prompt(CHAT_PROMPT_PATH)
        if analysis:
            system_prompt += "\n\n<photo_analysis>\n" + json.dumps(analysis, ensure_ascii=False) + "\n</photo_analysis>"

        messages = []
        for index, message in enumerate(history or []):
            role = "assistant" if message.get("role") == "assistant" else "user"
            content = message.get("content") or "Please continue."

            if index == 0 and role == "user" and image_bytes:
                image_url = _image_to_data_url(image_bytes, mime_type)
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                })
            else:
                messages.append({"role": role, "content": content})

        if not messages:
            messages = [{"role": "user", "content": "Help me plan this road project."}]

        answer = _request_with_fallback(messages, system_prompt, temperature=0.5,
                                         json_mode=False, models=DEFAULT_TEXT_MODELS)
        return answer or "I could not generate a response. Please try again."

    except Exception as error:
        print("Chat assistant error:", repr(error))
        return "The road assistant is temporarily unavailable. Please try again later."


# ============================================================
# PROJECT SPECIFICATION (natural-language project description -> work categories)
# ============================================================

_SPEC_SYSTEM_PROMPT = """You are an AI road estimation planning assistant.

Your job is to understand a road construction or repair project and
identify the types of work that may be required.

RULES:
1. Never invent SSR item numbers.
2. Never invent SSR rates.
3. Never invent quantities.
4. Do not provide a final cost.
5. Measurements supplied by the user must be preserved exactly, never changed.
6. Only recommend work categories reasonably supported by the given information.
7. Return ONLY valid JSON, matching the schema you are given.
"""


def generate_project_specification(mode, road_type, length_m, width_m, thickness_mm,
                                    soil_condition="", traffic_type="", drainage_required="",
                                    lead_distance_km=0.0, additional_prompt="",
                                    photo_analysis=None) -> dict:
    project_info = {
        "mode": mode,
        "road_type": road_type,
        "length_m": length_m,
        "width_m": width_m,
        "thickness_mm": thickness_mm,
        "soil_condition": soil_condition,
        "traffic_type": traffic_type,
        "drainage_required": drainage_required,
        "lead_distance_km": lead_distance_km,
        "additional_prompt": additional_prompt,
    }
    if photo_analysis:
        project_info["photo_analysis"] = photo_analysis

    user_prompt = f"""Analyse this road project and identify relevant work categories
(for example: site preparation, excavation, subgrade, sub-base, base
course, concrete pavement, bituminous pavement, joints, drainage, road
furniture, road safety, maintenance, pothole repair). Only recommend
categories reasonably supported by the information below -- do not
assume every category applies.

PROJECT INFORMATION:
{json.dumps(project_info, ensure_ascii=False, indent=2)}

Return exactly this JSON shape:
{{
  "project_type": "",
  "road_type": "",
  "work_categories": [
    {{"category": "", "reason": "", "search_keywords": []}}
  ],
  "additional_requirements": [],
  "missing_information": []
}}"""

    text = _request_with_fallback(
        [{"role": "user", "content": user_prompt}],
        system_prompt=_SPEC_SYSTEM_PROMPT,
        temperature=0.1,
        json_mode=True,
    )
    return parse_json_response(text)


# ============================================================
# SSR CANDIDATE SELECTION (AI picks from a list Python already found)
# ============================================================

_SELECTOR_SYSTEM_PROMPT = """You are an SSR item selection assistant for a road estimation application.

You will receive a project specification and a list of SSR items that
were already retrieved from the application's real SSR database.

STRICT RULES:
- You may ONLY select ids from the supplied candidate list.
- Never invent an item, an item number, a rate, or a description.
- Do not calculate quantities or costs.
- Select only items reasonably required for this project; if uncertain
  about an item, leave it out.
- Return ONLY valid JSON, matching the schema you are given.
"""


def select_ssr_items(project_specification: dict, candidate_items: list) -> dict:
    """
    Ask the AI to pick the relevant subset of `candidate_items` (a list
    of small dicts, e.g. from ssr_selector.candidates_to_ai_payload).

    Returns {"selected_ids": [...], "reasons": {id: reason}}. Raises on
    failure -- the caller should fall back to using the candidates
    directly (e.g. the top-scored ones) when this is unavailable.
    """
    if not candidate_items:
        return {"selected_ids": [], "reasons": {}}

    user_prompt = f"""PROJECT SPECIFICATION:
{json.dumps(project_specification, ensure_ascii=False, indent=2)}

CANDIDATE SSR ITEMS (only these may be selected):
{json.dumps(candidate_items, ensure_ascii=False, indent=2)}

Return exactly this JSON shape:
{{
  "selected_items": [
    {{"id": 0, "reason": "", "confidence": "low | medium | high"}}
  ]
}}"""

    text = _request_with_fallback(
        [{"role": "user", "content": user_prompt}],
        system_prompt=_SELECTOR_SYSTEM_PROMPT,
        temperature=0.1,
        json_mode=True,
    )
    result = parse_json_response(text)

    valid_ids = {c["id"] for c in candidate_items}
    selected_ids = []
    reasons = {}
    for item in result.get("selected_items", []) or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            continue
        if item_id in valid_ids:
            selected_ids.append(item_id)
            reasons[item_id] = item.get("reason", "")

    return {"selected_ids": selected_ids, "reasons": reasons}
