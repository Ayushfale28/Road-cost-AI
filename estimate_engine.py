import re
import math
import pandas as pd


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    """Convert any value to clean lowercase text."""
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    return str(value).strip().lower()


def safe_float(value, default=0.0):
    """Safely convert a value to float."""
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace(",", "").strip()

        return float(value)

    except (ValueError, TypeError):
        return default


# ============================================================
# UNIT CLASSIFICATION
# ============================================================

def classify_unit(unit):
    """
    Identify the general quantity type from SSR unit.
    """

    unit_text = clean_text(unit)

    # Volume
    if any(x in unit_text for x in [
        "cum",
        "cu.m",
        "m3",
        "m³",
        "cubic metre",
        "cubic meter"
    ]):
        return "volume"

    # Area
    if any(x in unit_text for x in [
        "sqm",
        "sq.m",
        "m2",
        "m²",
        "square metre",
        "square meter"
    ]):
        return "area"

    # Length
    if unit_text in [
        "m",
        "metre",
        "meter",
        "metres",
        "meters"
    ]:
        return "length"

    # Kilometre
    if any(x in unit_text for x in [
        "km",
        "kilometre",
        "kilometer"
    ]):
        return "km"

    # Number
    if any(x in unit_text for x in [
        "no",
        "nos",
        "number",
        "each",
        "each no"
    ]):
        return "number"

    # Weight
    if any(x in unit_text for x in [
        "kg",
        "kgs",
        "ton",
        "tonne",
        "mt"
    ]):
        return "weight"

    return "unknown"


# ============================================================
# ROAD TYPE KEYWORDS
# ============================================================

CC_KEYWORDS = [
    "concrete",
    "cement concrete",
    "rigid pavement",
    "cc pavement",
    "pcc",
    "rigid"
]

BT_KEYWORDS = [
    "bitumen",
    "bituminous",
    "dambar",
    "asphalt",
    "surface dressing",
    "tack coat",
    "prime coat",
    "premix"
]

REPAIR_KEYWORDS = [
    "repair",
    "maintenance",
    "pothole",
    "patch",
    "reinstatement",
    "damaged"
]

NEW_ROAD_KEYWORDS = [
    "construction",
    "new road",
    "new construction",
    "formation",
    "subgrade",
    "sub base",
    "base course"
]


# ============================================================
# PROJECT TEXT
# ============================================================

def build_project_text(
    mode,
    road_type,
    length_m,
    width_m,
    thickness_mm,
    drainage_required=False,
    soil_condition="",
    traffic_type="",
    lead_distance_km=0.0,
    additional_prompt=""
):
    """
    Build a searchable project description.
    """

    return " ".join([
        clean_text(mode),
        clean_text(road_type),
        clean_text(soil_condition),
        clean_text(traffic_type),
        clean_text(additional_prompt)
    ])


# ============================================================
# KEYWORD MATCHING
# ============================================================

def keyword_score(text, keywords):
    """
    Count how many keywords are present in text.
    """

    score = 0

    for keyword in keywords:

        if keyword in text:
            score += 1

    return score


# ============================================================
# SSR ITEM SCORING
# ============================================================

def score_ssr_item(
    row,
    mode,
    road_type,
    additional_prompt=""
):
    """
    Score an SSR item according to project requirements.

    This does NOT invent SSR items.
    It only scores items that actually exist
    in the uploaded SSR.
    """

    description = clean_text(
        row.get("description", "")
    )

    chapter = clean_text(
        row.get("chapter", "")
    )

    item_text = f"{description} {chapter}"

    score = 0

    mode_text = clean_text(mode)
    road_text = clean_text(road_type)

    # --------------------------------------------------------
    # NEW ROAD
    # --------------------------------------------------------

    if "new" in mode_text or "construction" in mode_text:

        score += keyword_score(
            item_text,
            NEW_ROAD_KEYWORDS
        )

    # --------------------------------------------------------
    # REPAIR
    # --------------------------------------------------------

    if "repair" in mode_text or "maintenance" in mode_text:

        score += keyword_score(
            item_text,
            REPAIR_KEYWORDS
        )

    # --------------------------------------------------------
    # CONCRETE
    # --------------------------------------------------------

    if "concrete" in road_text or "cc" in road_text:

        score += keyword_score(
            item_text,
            CC_KEYWORDS
        )

    # --------------------------------------------------------
    # BITUMEN
    # --------------------------------------------------------

    if "bitumen" in road_text or "dambar" in road_text:

        score += keyword_score(
            item_text,
            BT_KEYWORDS
        )

    # --------------------------------------------------------
    # ADDITIONAL USER REQUIREMENT
    # --------------------------------------------------------

    extra_text = clean_text(
        additional_prompt
    )

    if extra_text:

        words = re.findall(
            r"[a-zA-Z]+",
            extra_text
        )

        for word in words:

            if len(word) >= 4 and word in item_text:
                score += 1

    return score


# ============================================================
# AUTOMATIC SSR ITEM SELECTION
# ============================================================

def select_ssr_items(
    df,
    mode,
    road_type,
    additional_prompt="",
    max_items=30
):
    """
    Automatically select relevant SSR items.

    IMPORTANT:
    Only existing SSR rows are returned.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    scored_rows = []

    for index, row in df.iterrows():

        score = score_ssr_item(
            row,
            mode,
            road_type,
            additional_prompt
        )

        if score > 0:

            row_copy = row.copy()

            row_copy["_ai_score"] = score
            row_copy["_source_index"] = index

            scored_rows.append(
                row_copy
            )

    if not scored_rows:
        return pd.DataFrame()

    result = pd.DataFrame(
        scored_rows
    )

    result = result.sort_values(
        "_ai_score",
        ascending=False
    )

    result = result.head(
        max_items
    )

    return result


# ============================================================
# QUANTITY CALCULATION
# ============================================================

def calculate_quantity(
    unit,
    length_m,
    width_m,
    thickness_mm=0.0,
    default_number=1.0
):
    """
    Calculate quantity from project measurements.

    The formula depends on the SSR unit.
    """

    unit_kind = classify_unit(
        unit
    )

    length_m = safe_float(
        length_m
    )

    width_m = safe_float(
        width_m
    )

    thickness_mm = safe_float(
        thickness_mm
    )

    # --------------------------------------------------------
    # AREA
    # --------------------------------------------------------

    if unit_kind == "area":

        return length_m * width_m


    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if unit_kind == "volume":

        thickness_m = (
            thickness_mm / 1000
        )

        if thickness_m <= 0:
            return 0.0

        return (
            length_m
            * width_m
            * thickness_m
        )


    # --------------------------------------------------------
    # LENGTH
    # --------------------------------------------------------

    if unit_kind == "length":

        return length_m


    # --------------------------------------------------------
    # KM
    # --------------------------------------------------------

    if unit_kind == "km":

        return length_m / 1000


    # --------------------------------------------------------
    # NUMBER
    # --------------------------------------------------------

    if unit_kind == "number":

        return default_number


    # --------------------------------------------------------
    # UNKNOWN
    # --------------------------------------------------------

    return 0.0


# ============================================================
# BUILD AUTOMATIC ESTIMATE
# ============================================================

def build_ai_estimate(
    df,
    mode,
    road_type,
    length_m,
    width_m,
    thickness_mm,
    gst_percent=18.0,
    additional_prompt="",
    max_items=30
):
    """
    Main automatic estimation function.

    Flow:

    Project
       ↓
    SSR matching
       ↓
    Quantity calculation
       ↓
    Amount calculation
    """

    selected = select_ssr_items(
        df=df,
        mode=mode,
        road_type=road_type,
        additional_prompt=additional_prompt,
        max_items=max_items
    )

    if selected.empty:

        return {
            "items": [],
            "subtotal": 0.0,
            "gst": 0.0,
            "total": 0.0,
            "message": (
                "No sufficiently matching SSR items "
                "were found automatically."
            )
        }


    estimate_rows = []

    for _, row in selected.iterrows():

        unit = row.get(
            "unit",
            ""
        )

        rate = safe_float(
            row.get(
                "rate",
                0
            )
        )

        quantity = calculate_quantity(
            unit=unit,
            length_m=length_m,
            width_m=width_m,
            thickness_mm=thickness_mm
        )

        amount = (
            quantity * rate
        )

        estimate_rows.append({

            "Select": True,

            "Item No":
                row.get(
                    "item_no",
                    ""
                ),

            "Chapter":
                row.get(
                    "chapter",
                    ""
                ),

            "Description":
                row.get(
                    "description",
                    ""
                ),

            "Unit":
                unit,

            "Rate":
                rate,

            "Quantity":
                round(
                    quantity,
                    4
                ),

            "Amount":
                round(
                    amount,
                    2
                ),

            "AI Score":
                row.get(
                    "_ai_score",
                    0
                ),

            "SSR ID":
                row.get(
                    "id",
                    row.get(
                        "_source_index",
                        ""
                    )
                )
        })


    estimate_df = pd.DataFrame(
        estimate_rows
    )

    subtotal = estimate_df[
        "Amount"
    ].sum()

    gst_percent = safe_float(
        gst_percent,
        18.0
    )

    gst_amount = (
        subtotal
        * gst_percent
        / 100
    )

    total = (
        subtotal
        + gst_amount
    )

    return {

        "items":
            estimate_df,

        "subtotal":
            round(
                subtotal,
                2
            ),

        "gst":
            round(
                gst_amount,
                2
            ),

        "total":
            round(
                total,
                2
            ),

        "message":
            (
                "SSR items were automatically "
                "selected from the available SSR "
                "and quantities were calculated "
                "from the project measurements."
            )
    }
