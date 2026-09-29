import os
import re
from collections import Counter

import pandas as pd
import streamlit as st

from ai_module import analyze_photo, chat_reply
from ssr_loader import load_ssr, match_chapters, search


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Road Estimator - AI Assisted",
    layout="wide"
)

st.title("Road Estimator - AI Assisted Estimation")


# ============================================================
# SSR CHAPTER GROUPS
# ============================================================

COMMON_NEW = [
    "Road Survey and DPR",
    "Road Surevy",
    "Excavation",
    "Road Sub grade",
    "Road Sub Base and Base Course",
    "Cross Drainage Works",
    "Road Miscellaneous items",
    "Road Furniture",
    "Road Safety",
    "Geosynthetic"
]

CC_EXTRA = [
    "Rigid Pavement",
    "Rigid Pavement (New item)",
    "Expansion Joint"
]

BT_EXTRA = [
    "Road Surfacing Course",
    "Road work",
    "Road works",
    "Road"
]

REPAIR = [
    "Road Maintenance",
    "Bitumen and concrete road Pot Hole Reparing",
    "Road Miscellaneous items",
    "Road Furniture",
    "Road Safety",
    "Cross Drainage Works"
]


# ============================================================
# DEFAULT SSR
# ============================================================

DEFAULT_SSR_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "SSR_2022-23 (2).xlsx"
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "ai": None,
    "ai_results": [],
    "photos": [],
    "photo": None,
    "photo_mime": "image/jpeg",
    "selected": {},
    "chat": [],
    "estimate_generated": False,
    "estimate_signature": None,
    "manual_added": set(),
}

for key, value in DEFAULT_STATE.items():

    if key not in st.session_state:

        if isinstance(value, set):
            st.session_state[key] = set(value)

        elif isinstance(value, dict):
            st.session_state[key] = dict(value)

        elif isinstance(value, list):
            st.session_state[key] = list(value)

        else:
            st.session_state[key] = value


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_float(value, default=0.0):
    """
    Safely convert a value to float.
    """

    try:

        if pd.isna(value):
            return default

        return float(value)

    except Exception:

        return default


def normalize_text(value):
    """
    Convert text to lowercase searchable text.
    """

    if value is None:
        return ""

    text = str(value).lower()

    text = re.sub(
        r"[^a-z0-9\s]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_dataframe(df):
    """
    Make the SSR DataFrame safe for estimation.

    Required columns:

    id
    item_no
    chapter
    description
    unit
    rate
    """

    if not isinstance(df, pd.DataFrame):

        raise ValueError(
            "SSR loader did not return a DataFrame."
        )

    df = df.copy()

    required = [
        "id",
        "item_no",
        "chapter",
        "description",
        "unit",
        "rate"
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "SSR is missing required columns: "
            + ", ".join(missing)
        )

    # Keep ID numeric where possible.
    df["id"] = pd.to_numeric(
        df["id"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["id"]
    )

    df["id"] = df["id"].astype(int)

    df["rate"] = pd.to_numeric(
        df["rate"],
        errors="coerce"
    ).fillna(0.0)

    for column in [
        "item_no",
        "chapter",
        "description",
        "unit"
    ]:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
        )

    # Ensure ID is the DataFrame index.
    df = df.drop_duplicates(
        subset=["id"],
        keep="first"
    )

    df = df.set_index(
        "id",
        drop=False
    )

    return df


def get_ai_value(value, default=None):
    """
    Extract the value from an AI field that may be either:

    {"value": "...", ...}

    or

    "..."
    """

    if isinstance(value, dict):

        return value.get(
            "value",
            default
        )

    if value is None:

        return default

    return value


def get_ai_confidence(value):
    """
    Extract confidence from an AI field.
    """

    if isinstance(value, dict):

        return value.get(
            "confidence",
            "low"
        )

    return "low"


def combine_ai_results(results):
    """
    Combine multiple photo-analysis results.

    We do NOT simply use photo 1.

    The combined result uses:

    - majority recommended mode
    - majority road type
    - combined defects
    - combined suggested works
    - combined parameters
    """

    if not results:

        return None

    valid_results = []

    for entry in results:

        result = entry.get(
            "result",
            {}
        )

        if isinstance(result, dict):

            valid_results.append(
                result
            )

    if not valid_results:

        return None

    # --------------------------------------------------------
    # MODE
    # --------------------------------------------------------

    modes = []

    for result in valid_results:

        mode = get_ai_value(
            result.get(
                "recommended_mode"
            )
        )

        if mode in [
            "repair",
            "new_construction"
        ]:

            modes.append(mode)

    if modes:

        mode_value = Counter(
            modes
        ).most_common(1)[0][0]

    else:

        mode_value = "unclear"

    # --------------------------------------------------------
    # ROAD TYPE
    # --------------------------------------------------------

    road_types = []

    for result in valid_results:

        road_type = get_ai_value(
            result.get(
                "road_type"
            )
        )

        if road_type:

            road_types.append(
                str(road_type)
            )

    if road_types:

        road_type_value = Counter(
            road_types
        ).most_common(1)[0][0]

    else:

        road_type_value = "unclear"

    # --------------------------------------------------------
    # DEFECTS
    # --------------------------------------------------------

    defects = []

    for result in valid_results:

        result_defects = result.get(
            "defects",
            []
        )

        if isinstance(
            result_defects,
            list
        ):

            defects.extend(
                result_defects
            )

    # Remove duplicate defect types.
    unique_defects = []

    seen_defects = set()

    for defect in defects:

        if not isinstance(
            defect,
            dict
        ):

            continue

        defect_type = normalize_text(
            defect.get(
                "type",
                ""
            )
        )

        if defect_type and defect_type not in seen_defects:

            unique_defects.append(
                defect
            )

            seen_defects.add(
                defect_type
            )

    # --------------------------------------------------------
    # SUGGESTED WORKS
    # --------------------------------------------------------

    suggested_works = []

    seen_works = set()

    for result in valid_results:

        works = result.get(
            "suggested_works",
            []
        )

        if not isinstance(
            works,
            list
        ):

            continue

        for work in works:

            if not isinstance(
                work,
                dict
            ):

                continue

            work_name = normalize_text(
                work.get(
                    "work",
                    ""
                )
            )

            if work_name and work_name not in seen_works:

                suggested_works.append(
                    work
                )

                seen_works.add(
                    work_name
                )

    # --------------------------------------------------------
    # PARAMETERS
    # --------------------------------------------------------

    parameters = []

    seen_parameters = set()

    for result in valid_results:

        result_parameters = result.get(
            "suggested_parameters",
            []
        )

        if not isinstance(
            result_parameters,
            list
        ):

            continue

        for parameter in result_parameters:

            if not isinstance(
                parameter,
                dict
            ):

                continue

            name = normalize_text(
                parameter.get(
                    "name",
                    ""
                )
            )

            if name and name not in seen_parameters:

                parameters.append(
                    parameter
                )

                seen_parameters.add(
                    name
                )

    # --------------------------------------------------------
    # PHOTO QUALITY
    # --------------------------------------------------------

    qualities = []

    for result in valid_results:

        quality = result.get(
            "photo_quality"
        )

        if quality:

            qualities.append(
                str(quality)
            )

    # --------------------------------------------------------
    # SITE TYPES
    # --------------------------------------------------------

    site_types = []

    for result in valid_results:

        site_type = get_ai_value(
            result.get(
                "site_type"
            )
        )

        if site_type:

            site_types.append(
                str(site_type)
            )

    if site_types:

        site_type_value = Counter(
            site_types
        ).most_common(1)[0][0]

    else:

        site_type_value = "unclear"

    return {
        "photo_quality": (
            "; ".join(qualities)
            if qualities
            else "unclear"
        ),

        "site_type": {
            "value": site_type_value,
            "confidence": "medium"
        },

        "recommended_mode": {
            "value": mode_value,
            "confidence": "medium",
            "reason": (
                "Recommendation combined "
                "from uploaded site photographs."
            )
        },

        "road_type": {
            "value": road_type_value,
            "confidence": "medium"
        },

        "surface_condition": (
            " ".join(
                str(
                    result.get(
                        "surface_condition",
                        ""
                    )
                )
                for result in valid_results
                if result.get(
                    "surface_condition"
                )
            )
        ),

        "defects": unique_defects,

        "suggested_works": suggested_works,

        "suggested_parameters": parameters,

        "limitations": (
            "Photo analysis is visual guidance only. "
            "Final engineering measurements and "
            "site decisions must be verified."
        )
    }


# ============================================================
# UNIT CLASSIFICATION
# ============================================================

def classify_unit(unit):
    """
    Convert SSR units into a quantity category.

    Examples:

    sqm -> area
    cum -> volume
    m -> length
    km -> km
    nos -> nos
    kg -> weight
    tonne -> weight
    """

    text = normalize_text(
        unit
    )

    if not text:

        return "unknown"

    # --------------------------------------------------------
    # AREA
    # --------------------------------------------------------

    if any(
        token in text
        for token in [
            "sqm",
            "sq m",
            "m2",
            "square metre",
            "square meter",
            "square metre"
        ]
    ):

        return "area"

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if any(
        token in text
        for token in [
            "cum",
            "cu m",
            "m3",
            "cubic metre",
            "cubic meter"
        ]
    ):

        return "volume"

    # --------------------------------------------------------
    # LENGTH
    # --------------------------------------------------------

    if (
        text == "m"
        or text.startswith("m ")
        or "metre" in text
        or "meter" in text
        or "running metre" in text
    ):

        return "length"

    # --------------------------------------------------------
    # KILOMETRE
    # --------------------------------------------------------

    if (
        "km" in text
        or "kilometre" in text
        or "kilometer" in text
    ):

        return "km"

    # --------------------------------------------------------
    # NUMBER
    # --------------------------------------------------------

    if any(
        token in text
        for token in [
            "nos",
            "no.",
            "number",
            "each",
            "item"
        ]
    ):

        return "nos"

    # --------------------------------------------------------
    # WEIGHT
    # --------------------------------------------------------

    if any(
        token in text
        for token in [
            "kg",
            "kgs",
            "kilogram",
            "ton",
            "tonne",
            "metric ton"
        ]
    ):

        return "weight"

    return "unknown"


# ============================================================
# QUANTITY ENGINE
# ============================================================

def calculate_quantity(
    row,
    length_m,
    width_m,
    thickness_mm,
    pothole_area_m2=0.0,
    drainage_length_m=0.0,
    pothole_count=0
):
    """
    Calculate an estimated quantity using:

    - SSR unit
    - project length
    - project width
    - project thickness
    - defect information

    Important:
    This is an estimation engine, not a substitute for
    detailed engineering measurement.
    """

    unit_kind = classify_unit(
        row.get(
            "unit",
            ""
        )
    )

    description = normalize_text(
        row.get(
            "description",
            ""
        )
    )

    chapter = normalize_text(
        row.get(
            "chapter",
            ""
        )
    )

    # --------------------------------------------------------
    # AREA
    # --------------------------------------------------------

    if unit_kind == "area":

        # For pothole repair use measured damaged area
        # when available.
        if (
            pothole_area_m2 > 0
            and (
                "pothole" in description
                or "patch" in description
                or "repair" in chapter
                or "maintenance" in chapter
            )
        ):

            return round(
                pothole_area_m2,
                3
            )

        return round(
            length_m * width_m,
            3
        )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if unit_kind == "volume":

        thickness_m = (
            thickness_mm / 1000
        )

        if thickness_m <= 0:

            return round(
                length_m * width_m,
                3
            )

        return round(
            length_m
            * width_m
            * thickness_m,
            3
        )

    # --------------------------------------------------------
    # LENGTH
    # --------------------------------------------------------

    if unit_kind == "length":

        if (
            drainage_length_m > 0
            and (
                "drain" in description
                or "kerb" in description
                or "curb" in description
            )
        ):

            return round(
                drainage_length_m,
                3
            )

        return round(
            length_m,
            3
        )

    # --------------------------------------------------------
    # KILOMETRE
    # --------------------------------------------------------

    if unit_kind == "km":

        return round(
            length_m / 1000,
            3
        )

    # --------------------------------------------------------
    # NUMBER
    # --------------------------------------------------------

    if unit_kind == "nos":

        if pothole_count > 0 and "pothole" in description:

            return float(
                pothole_count
            )

        return 1.0

    # --------------------------------------------------------
    # WEIGHT
    # --------------------------------------------------------

    if unit_kind == "weight":

        # Do not invent density or conversion factors.
        # Weight-based SSR items need project-specific
        # material calculations.
        return 0.0

    # --------------------------------------------------------
    # UNKNOWN UNIT
    # --------------------------------------------------------

    return 0.0


# ============================================================
# SSR ITEM SCORING
# ============================================================

def score_ssr_item(
    row,
    mode,
    road_kind,
    ai_analysis
):
    """
    Score an SSR row against the project.

    The actual SSR file remains the source of:

    - item number
    - description
    - unit
    - rate

    We only use the description/chapter to find relevant
    construction activities.
    """

    description = normalize_text(
        row.get(
            "description",
            ""
        )
    )

    chapter = normalize_text(
        row.get(
            "chapter",
            ""
        )
    )

    combined = (
        description
        + " "
        + chapter
    )

    score = 0

    matched_rules = []

    # ========================================================
    # NEW ROAD
    # ========================================================

    if mode == "New Road Construction":

        # ----------------------------------------------------
        # SITE CLEANING / CLEARING
        # ----------------------------------------------------

        if any(
            word in combined
            for word in [
                "clearing",
                "cleaning",
                "grubbing",
                "removal of vegetation"
            ]
        ):

            score += 12

            matched_rules.append(
                "site preparation"
            )

        # ----------------------------------------------------
        # EXCAVATION
        # ----------------------------------------------------

        if (
            "excavat" in combined
            or "earthwork" in combined
            or "cutting" in combined
        ):

            score += 12

            matched_rules.append(
                "excavation"
            )

        # ----------------------------------------------------
        # SUBGRADE
        # ----------------------------------------------------

        if (
            "sub grade" in combined
            or "subgrade" in combined
        ):

            score += 15

            matched_rules.append(
                "subgrade"
            )

        # ----------------------------------------------------
        # SUBBASE / BASE
        # ----------------------------------------------------

        if (
            "sub base" in combined
            or "subbase" in combined
        ):

            score += 15

            matched_rules.append(
                "subbase"
            )

        if (
            "base course" in combined
            or "basecourse" in combined
            or "base course" in chapter
        ):

            score += 15

            matched_rules.append(
                "base course"
            )

        # ----------------------------------------------------
        # CC
        # ----------------------------------------------------

        if road_kind == "Concrete (CC)":

            if (
                "rigid pavement" in combined
                or "cement concrete" in combined
                or "concrete pavement" in combined
                or "cc pavement" in combined
                or "concrete road" in combined
            ):

                score += 30

                matched_rules.append(
                    "concrete pavement"
                )

            if "expansion joint" in combined:

                score += 20

                matched_rules.append(
                    "expansion joint"
                )

            if "joint" in combined:

                score += 8

                matched_rules.append(
                    "concrete joint"
                )

        # ----------------------------------------------------
        # BITUMEN
        # ----------------------------------------------------

        if road_kind == "Bitumen / Dambar":

            if (
                "bitumen" in combined
                or "bituminous" in combined
                or "asphalt" in combined
                or "surface dressing" in combined
                or "premix" in combined
                or "dense bituminous" in combined
                or "dbm" in combined
                or "bc " in combined
            ):

                score += 30

                matched_rules.append(
                    "bituminous surfacing"
                )

            if (
                "prime coat" in combined
                or "prime" in combined
            ):

                score += 18

                matched_rules.append(
                    "prime coat"
                )

            if (
                "tack coat" in combined
                or "tack" in combined
            ):

                score += 18

                matched_rules.append(
                    "tack coat"
                )

    # ========================================================
    # REPAIR
    # ========================================================

    if mode == "Repair (Existing Road)":

        if (
            "maintenance" in combined
            or "repair" in combined
        ):

            score += 15

            matched_rules.append(
                "road maintenance"
            )

        if "pothole" in combined:

            score += 30

            matched_rules.append(
                "pothole repair"
            )

        if "patch" in combined:

            score += 22

            matched_rules.append(
                "patch repair"
            )

        if "crack" in combined:

            score += 18

            matched_rules.append(
                "crack repair"
            )

        if "ravel" in combined:

            score += 15

            matched_rules.append(
                "raveling repair"
            )

        if "edge" in combined and "break" in combined:

            score += 15

            matched_rules.append(
                "edge repair"
            )

    # ========================================================
    # AI DEFECT CONTEXT
    # ========================================================

    if ai_analysis:

        defects = ai_analysis.get(
            "defects",
            []
        )

        if isinstance(
            defects,
            list
        ):

            for defect in defects:

                if not isinstance(
                    defect,
                    dict
                ):

                    continue

                defect_type = normalize_text(
                    defect.get(
                        "type",
                        ""
                    )
                )

                if defect_type and defect_type in combined:

                    score += 12

                    matched_rules.append(
                        "AI defect: "
                        + defect_type
                    )

        works = ai_analysis.get(
            "suggested_works",
            []
        )

        if isinstance(
            works,
            list
        ):

            for work in works:

                if not isinstance(
                    work,
                    dict
                ):

                    continue

                work_name = normalize_text(
                    work.get(
                        "work",
                        ""
                    )
                )

                keywords = work.get(
                    "search_keywords",
                    []
                )

                if work_name:

                    if work_name in combined:

                        score += 15

                        matched_rules.append(
                            "AI suggested work"
                        )

                if isinstance(
                    keywords,
                    list
                ):

                    for keyword in keywords:

                        keyword_text = normalize_text(
                            keyword
                        )

                        if (
                            keyword_text
                            and keyword_text in combined
                        ):

                            score += 6

    # ========================================================
    # CHAPTER BONUS
    # ========================================================

    if mode == "New Road Construction":

        if road_kind == "Concrete (CC)":

            if "rigid pavement" in chapter:

                score += 12

        if road_kind == "Bitumen / Dambar":

            if "surfacing" in chapter:

                score += 12

    else:

        if (
            "maintenance" in chapter
            or "pothole" in chapter
        ):

            score += 12

    return score, matched_rules


# ============================================================
# AUTOMATIC SSR ESTIMATE GENERATOR
# ============================================================

def generate_ssr_estimate(
    ssr_df,
    mode,
    road_kind,
    length_m,
    width_m,
    thickness_mm,
    ai_analysis=None,
    pothole_area_m2=0.0,
    drainage_length_m=0.0,
    pothole_count=0
):
    """
    Automatically select relevant SSR items and calculate
    starting quantities.

    IMPORTANT:

    The SSR file supplies the official item/rate data.

    The AI/estimation engine does NOT invent:

    - SSR item numbers
    - SSR rates

    It only maps project requirements to the uploaded SSR.
    """

    df = normalize_dataframe(
        ssr_df
    )

    if length_m <= 0:

        return []

    if width_m <= 0:

        return []

    # --------------------------------------------------------
    # SCORE EVERY SSR ITEM
    # --------------------------------------------------------

    candidates = []

    for item_id, row in df.iterrows():

        score, rules = score_ssr_item(
            row,
            mode,
            road_kind,
            ai_analysis
        )

        if score <= 0:

            continue

        candidates.append(
            {
                "id": int(item_id),
                "score": score,
                "rules": rules,
                "description": row[
                    "description"
                ],
                "chapter": row[
                    "chapter"
                ]
            }
        )

    if not candidates:

        return []

    candidates = sorted(
        candidates,
        key=lambda x: (
            x["score"],
            x["id"]
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # CATEGORY LIMITING
    #
    # Prevent the engine from selecting dozens of duplicate
    # SSR rows that represent alternative specifications.
    # --------------------------------------------------------

    selected_candidates = []

    category_counts = {}

    for candidate in candidates:

        description = normalize_text(
            candidate["description"]
        )

        chapter = normalize_text(
            candidate["chapter"]
        )

        # Determine broad category.
        if "excavat" in description:

            category = "excavation"

        elif (
            "sub grade" in description
            or "subgrade" in description
            or "sub grade" in chapter
        ):

            category = "subgrade"

        elif (
            "sub base" in description
            or "subbase" in description
        ):

            category = "subbase"

        elif (
            "base course" in description
            or "base course" in chapter
        ):

            category = "base"

        elif (
            "rigid pavement" in description
            or "concrete pavement" in description
            or "cement concrete" in description
        ):

            category = "concrete"

        elif (
            "expansion joint" in description
        ):

            category = "expansion_joint"

        elif (
            "prime coat" in description
            or "prime" in description
        ):

            category = "prime"

        elif (
            "tack coat" in description
            or "tack" in description
        ):

            category = "tack"

        elif (
            "bitumen" in description
            or "bituminous" in description
            or "asphalt" in description
            or "surface dressing" in description
        ):

            category = "bituminous_surface"

        elif (
            "pothole" in description
        ):

            category = "pothole"

        elif (
            "patch" in description
        ):

            category = "patch"

        elif (
            "maintenance" in chapter
            or "maintenance" in description
        ):

            category = "maintenance"

        elif (
            "drain" in description
            or "drainage" in description
        ):

            category = "drainage"

        elif (
            "clean" in description
            or "grubb" in description
            or "clear" in description
        ):

            category = "site_preparation"

        else:

            category = "other"

        current_count = category_counts.get(
            category,
            0
        )

        # Keep only the strongest item for most categories.
        # For "other", do not automatically select.
        if category == "other":

            continue

        if current_count >= 1:

            continue

        category_counts[
            category
        ] = current_count + 1

        selected_candidates.append(
            candidate
        )

    # --------------------------------------------------------
    # CALCULATE QUANTITIES
    # --------------------------------------------------------

    estimate = []

    for candidate in selected_candidates:

        item_id = candidate["id"]

        row = df.loc[
            item_id
        ]

        quantity = calculate_quantity(
            row=row,
            length_m=length_m,
            width_m=width_m,
            thickness_mm=thickness_mm,
            pothole_area_m2=pothole_area_m2,
            drainage_length_m=drainage_length_m,
            pothole_count=pothole_count
        )

        # ----------------------------------------------------
        # Avoid automatically adding weight-based rows because
        # there is no reliable conversion without material
        # density/specification.
        # ----------------------------------------------------

        if classify_unit(
            row["unit"]
        ) == "weight":

            continue

        # Unknown units are not safe to calculate.
        if classify_unit(
            row["unit"]
        ) == "unknown":

            continue

        # ----------------------------------------------------
        # Only add rows that actually have a quantity.
        # ----------------------------------------------------

        if quantity <= 0:

            continue

        rate = safe_float(
            row["rate"]
        )

        amount = (
            quantity
            * rate
        )

        estimate.append(
            {
                "id": item_id,
                "item_no": row[
                    "item_no"
                ],
                "chapter": row[
                    "chapter"
                ],
                "description": row[
                    "description"
                ],
                "unit": row[
                    "unit"
                ],
                "rate": rate,
                "quantity": round(
                    quantity,
                    3
                ),
                "amount": round(
                    amount,
                    2
                ),
                "selection_reason": (
                    "; ".join(
                        candidate[
                            "rules"
                        ]
                    )
                )
            }
        )

    return estimate


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "Project Setup"
    )

    # --------------------------------------------------------
    # API KEY IS COMPLETELY HIDDEN
    # --------------------------------------------------------

    st.caption(
        "AI services are configured automatically "
        "by the application."
    )

    # Compatibility variable only.
    # ai_module.py reads the real secret itself.
    api_key = ""

    # --------------------------------------------------------
    # SSR SOURCE
    # --------------------------------------------------------

    st.subheader(
        "SSR Source"
    )

    st.caption(
        "Upload an SSR if you want to use a different "
        "schedule. Otherwise the default SSR will be used."
    )

    ssr_file = st.file_uploader(
        "Upload SSR",
        type=[
            "xlsx",
            "xls",
            "csv",
            "pdf",
            "docx",
            "txt"
        ]
    )

    if ssr_file is not None:

        st.success(
            f"Using uploaded SSR: {ssr_file.name}"
        )

    else:

        st.info(
            "Default SSR will be used."
        )

        st.caption(
            "SSR_2022-23 (2).xlsx"
        )


# ============================================================
# SSR LOADING
# ============================================================

@st.cache_data(
    show_spinner="Loading SSR..."
)
def get_ssr(file_source):

    return normalize_dataframe(
        load_ssr(
            file_source
        )
    )


def load_selected_ssr():

    # --------------------------------------------------------
    # USER SSR
    # --------------------------------------------------------

    if ssr_file is not None:

        try:

            return get_ssr(
                ssr_file
            )

        except Exception:

            st.error(
                "The uploaded SSR could not be read."
            )

            st.info(
                "Please check the SSR file format and "
                "required columns."
            )

            st.stop()

    # --------------------------------------------------------
    # DEFAULT SSR
    # --------------------------------------------------------

    if not os.path.exists(
        DEFAULT_SSR_FILE
    ):

        st.error(
            "Default SSR file was not found."
        )

        st.warning(
            "Place SSR_2022-23 (2).xlsx beside app.py "
            "or upload an SSR file."
        )

        st.stop()

    try:

        return get_ssr(
            DEFAULT_SSR_FILE
        )

    except Exception:

        st.error(
            "The default SSR could not be loaded."
        )

        st.stop()


# ============================================================
# SITE PHOTOS
# ============================================================

st.subheader(
    "1. Site Photos"
)

st.caption(
    "Upload one or multiple photos of the road/site."
)

photos = st.file_uploader(
    "Upload Road Photos",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ],
    accept_multiple_files=True
)

note = st.text_input(
    "Additional Information (Optional)",
    placeholder=(
        "Example: New 2 km concrete road is required."
    )
)


# ============================================================
# STORE PHOTOS
# ============================================================

if photos:

    st.session_state.photos = []

    for uploaded_photo in photos:

        st.session_state.photos.append(
            {
                "name": uploaded_photo.name,
                "bytes": uploaded_photo.getvalue(),
                "mime": uploaded_photo.type
            }
        )

    # First image remains available to chat.
    st.session_state.photo = (
        st.session_state.photos[0]["bytes"]
    )

    st.session_state.photo_mime = (
        st.session_state.photos[0]["mime"]
    )


# ============================================================
# DISPLAY PHOTOS
# ============================================================

if photos:

    st.write(
        f"**{len(photos)} photo(s) uploaded.**"
    )

    columns = st.columns(
        min(
            len(photos),
            4
        )
    )

    for index, uploaded_photo in enumerate(
        photos
    ):

        with columns[
            index % len(columns)
        ]:

            st.image(
                uploaded_photo,
                caption=uploaded_photo.name,
                use_container_width=True
            )

    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    if st.button(
        "Analyze Site",
        type="primary"
    ):

        st.session_state.ai_results = []
        st.session_state.ai = None

        # New analysis = new project.
        st.session_state.selected = {}

        st.session_state.estimate_generated = False
        st.session_state.estimate_signature = None

        progress = st.progress(
            0
        )

        status = st.empty()

        for index, uploaded_photo in enumerate(
            photos
        ):

            status.write(
                f"Analyzing photo {index + 1} "
                f"of {len(photos)}..."
            )

            try:

                result = analyze_photo(
                    uploaded_photo.getvalue(),
                    uploaded_photo.type,
                    "",
                    note
                )

            except Exception:

                result = {
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
                            "Automatic analysis "
                            "was unavailable."
                        )
                    },
                    "road_type": {
                        "value": "unclear",
                        "confidence": "low"
                    },
                    "surface_condition": (
                        "Automatic analysis unavailable."
                    ),
                    "defects": [],
                    "suggested_works": [],
                    "suggested_parameters": [],
                    "limitations": (
                        "Manual engineering review required."
                    )
                }

            st.session_state.ai_results.append(
                {
                    "name": uploaded_photo.name,
                    "result": result
                }
            )

            progress.progress(
                (index + 1)
                / len(photos)
            )

        status.empty()

        # ----------------------------------------------------
        # COMBINE ALL PHOTOS
        # ----------------------------------------------------

        st.session_state.ai = combine_ai_results(
            st.session_state.ai_results
        )

        st.success(
            "Site analysis completed."
        )


# ============================================================
# PHOTO RESULTS
# ============================================================

if st.session_state.ai_results:

    st.subheader(
        "Photo Analysis Results"
    )

    for index, entry in enumerate(
        st.session_state.ai_results
    ):

        result = entry[
            "result"
        ]

        with st.expander(
            f"Photo {index + 1}: "
            f"{entry['name']}",
            expanded=index == 0
        ):

            recommendation = result.get(
                "recommended_mode",
                {}
            )

            mode_value = get_ai_value(
                recommendation,
                "unclear"
            )

            confidence = get_ai_confidence(
                recommendation
            )

            reason = ""

            if isinstance(
                recommendation,
                dict
            ):

                reason = recommendation.get(
                    "reason",
                    ""
                )

            st.info(
                f"**Suggested Work:** "
                f"{mode_value}  \n"
                f"**Confidence:** {confidence}"
            )

            if reason:

                st.write(
                    f"**Reason:** {reason}"
                )

            site_type = get_ai_value(
                result.get(
                    "site_type"
                ),
                "-"
            )

            road_type = get_ai_value(
                result.get(
                    "road_type"
                ),
                "-"
            )

            st.write(
                f"**Site Type:** {site_type}"
            )

            st.write(
                f"**Road Type:** {road_type}"
            )

            st.write(
                f"**Photo Quality:** "
                f"{result.get('photo_quality', '-')}"
            )

            st.write(
                f"**Surface Condition:** "
                f"{result.get('surface_condition', '-')}"
            )

            defects = result.get(
                "defects",
                []
            )

            if defects:

                st.markdown(
                    "**Detected Defects:**"
                )

                st.dataframe(
                    pd.DataFrame(
                        defects
                    ),
                    hide_index=True,
                    use_container_width=True
                )

            suggested_works = result.get(
                "suggested_works",
                []
            )

            if suggested_works:

                st.markdown(
                    "**Suggested Works:**"
                )

                for work in suggested_works:

                    if isinstance(
                        work,
                        dict
                    ):

                        st.write(
                            "- "
                            + str(
                                work.get(
                                    "work",
                                    ""
                                )
                            )
                        )

            limitations = result.get(
                "limitations"
            )

            if limitations:

                st.caption(
                    "Limitations: "
                    + str(
                        limitations
                    )
                )


# ============================================================
# COMBINED AI SUMMARY
# ============================================================

ai = st.session_state.ai

if ai:

    st.subheader(
        "Combined Site Assessment"
    )

    combined_mode = get_ai_value(
        ai.get(
            "recommended_mode"
        ),
        "unclear"
    )

    combined_road_type = get_ai_value(
        ai.get(
            "road_type"
        ),
        "unclear"
    )

    c1, c2 = st.columns(2)

    c1.metric(
        "Suggested Work",
        str(
            combined_mode
        )
    )

    c2.metric(
        "Detected Road Type",
        str(
            combined_road_type
        )
    )


# ============================================================
# TABS
# ============================================================

estimate_tab, chat_tab = st.tabs(
    [
        "Estimate",
        "Chat Assistant"
    ]
)


# ============================================================
# CHAT
# ============================================================

with chat_tab:

    st.subheader(
        "Road Project Chat Assistant"
    )

    st.caption(
        "Ask questions about your road project."
    )

    for message in st.session_state.chat:

        with st.chat_message(
            message["role"]
        ):

            st.markdown(
                message["content"]
            )

    if st.button(
        "Clear Chat"
    ):

        st.session_state.chat = []

        st.rerun()

    user_message = st.chat_input(
        "Ask a question..."
    )

    if user_message:

        st.session_state.chat.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        try:

            response = chat_reply(
                st.session_state.chat,
                "",
                st.session_state.ai,
                st.session_state.photo,
                st.session_state.photo_mime
            )

        except Exception:

            response = (
                "The road assistant is temporarily "
                "unavailable. Please try again later."
            )

        st.session_state.chat.append(
            {
                "role": "assistant",
                "content": response
            }
        )

        st.rerun()


# ============================================================
# ESTIMATE TAB
# ============================================================

with estimate_tab:

    st.subheader(
        "2. Road Work Selection"
    )

    # --------------------------------------------------------
    # LOAD SSR
    # --------------------------------------------------------

    df = load_selected_ssr()

    required_columns = [
        "id",
        "item_no",
        "chapter",
        "description",
        "unit",
        "rate"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        st.error(
            "Required SSR columns are missing."
        )

        st.write(
            missing_columns
        )

        st.stop()

    all_chapters = sorted(
        [
            str(chapter)
            for chapter in df[
                "chapter"
            ].dropna().unique()
        ]
    )

    # ========================================================
    # WORK TYPE
    # ========================================================

    st.subheader(
        "3. Select Work Type"
    )

    modes = [
        "Repair (Existing Road)",
        "New Road Construction"
    ]

    ai_mode = get_ai_value(
        ai.get(
            "recommended_mode"
        )
        if ai
        else None,
        None
    )

    default_mode_index = (
        1
        if ai_mode == "new_construction"
        else 0
    )

    mode = st.radio(
        "Work Type",
        modes,
        index=default_mode_index,
        horizontal=True,
        help=(
            "AI provides a recommendation. "
            "You have the final decision."
        )
    )

    # ========================================================
    # ROAD TYPE
    # ========================================================

    road_kind = None

    if mode == "New Road Construction":

        st.subheader(
            "4. Road Type"
        )

        road_kind = st.radio(
            "Road Type",
            [
                "Concrete (CC)",
                "Bitumen / Dambar"
            ],
            horizontal=True
        )

        if road_kind == "Concrete (CC)":

            wanted_chapters = (
                COMMON_NEW
                + CC_EXTRA
            )

        else:

            wanted_chapters = (
                COMMON_NEW
                + BT_EXTRA
            )

    else:

        wanted_chapters = REPAIR

    preset_chapters = match_chapters(
        all_chapters,
        wanted_chapters
    )

    # ========================================================
    # PROJECT MEASUREMENTS
    # ========================================================

    st.subheader(
        "5. Project Measurements"
    )

    m1, m2, m3, m4 = st.columns(4)

    length = m1.number_input(
        "Length (m)",
        min_value=0.0,
        value=0.0,
        step=1.0
    )

    width = m2.number_input(
        "Width (m)",
        min_value=0.0,
        value=0.0,
        step=0.1
    )

    thickness = m3.number_input(
        "Thickness (mm)",
        min_value=0.0,
        value=0.0,
        step=5.0
    )

    gst = m4.number_input(
        "GST (%)",
        min_value=0.0,
        value=18.0,
        step=1.0
    )

    # --------------------------------------------------------
    # EXTRA MEASUREMENTS
    # --------------------------------------------------------

    e1, e2 = st.columns(2)

    pothole_area = e1.number_input(
        "Damaged / Pothole Area (m²)",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help=(
            "Optional. Useful for repair estimates."
        )
    )

    drainage_length = e2.number_input(
        "Drain / Kerb Length (m)",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help=(
            "Optional."
        )
    )

    pothole_count = st.number_input(
        "Number of Potholes",
        min_value=0,
        value=0,
        step=1
    )

    # ========================================================
    # AUTOMATIC AI SSR ESTIMATION
    # ========================================================

    st.subheader(
        "6. Automatic SSR Estimation"
    )

    st.caption(
        "The system will use the project type, road type, "
        "measurements, site analysis and the actual SSR "
        "file to propose relevant SSR items and quantities."
    )

    can_generate = (
        length > 0
        and width > 0
        and (
            mode == "Repair (Existing Road)"
            or (
                mode == "New Road Construction"
                and road_kind is not None
            )
        )
    )

    if not can_generate:

        st.info(
            "Enter at least length and width "
            "to generate the automatic estimate."
        )

    if st.button(
        "Generate SSR Estimate Automatically",
        type="primary",
        disabled=not can_generate
    ):

        with st.spinner(
            "Selecting SSR items and calculating quantities..."
        ):

            generated = generate_ssr_estimate(
                ssr_df=df,
                mode=mode,
                road_kind=road_kind,
                length_m=length,
                width_m=width,
                thickness_mm=thickness,
                ai_analysis=ai,
                pothole_area_m2=pothole_area,
                drainage_length_m=drainage_length,
                pothole_count=pothole_count
            )

        # Clear previous automatic selection.
        st.session_state.selected = {}

        for item in generated:

            item_id = int(
                item["id"]
            )

            st.session_state.selected[
                item_id
            ] = float(
                item["quantity"]
            )

        st.session_state.estimate_generated = True

        st.session_state.estimate_signature = (
            mode,
            road_kind,
            float(length),
            float(width),
            float(thickness),
            float(pothole_area),
            float(drainage_length),
            int(pothole_count)
        )

        if generated:

            st.success(
                f"{len(generated)} SSR item(s) "
                "were automatically proposed."
            )

        else:

            st.warning(
                "No matching SSR items could be "
                "automatically identified. "
                "Use the manual SSR search below."
            )

    # ========================================================
    # AUTOMATIC ESTIMATE REVIEW
    # ========================================================

    if st.session_state.estimate_generated:

        st.subheader(
            "7. AI-Generated SSR Items"
        )

        st.info(
            "Review these items before using the estimate. "
            "You can change quantities, remove items, "
            "or add additional SSR items below."
        )

    # ========================================================
    # MANUAL SSR SEARCH
    # ========================================================

    st.subheader(
        "8. Add Additional SSR Items"
    )

    chapters = st.multiselect(
        "SSR Chapters",
        all_chapters,
        default=preset_chapters,
        key="manual_chapters"
    )

    keywords_text = st.text_input(
        "Search SSR Items",
        placeholder=(
            "Example: excavation, concrete, "
            "bitumen, pothole, drain"
        )
    )

    keywords = [
        word.strip()
        for word in keywords_text.split(",")
        if word.strip()
    ]

    try:

        found_items = search(
            df,
            chapters,
            keywords
        )

    except Exception:

        found_items = pd.DataFrame(
            columns=required_columns
        )

    st.caption(
        f"{len(found_items)} SSR items found."
    )

    if not found_items.empty:

        item_view = found_items[
            required_columns
        ].copy()

        item_view.insert(
            0,
            "Add",
            False
        )

        edited_items = st.data_editor(
            item_view,
            hide_index=True,
            use_container_width=True,
            height=300,
            disabled=[
                "id",
                "item_no",
                "chapter",
                "description",
                "unit",
                "rate"
            ],
            column_config={
                "id": None
            },
            key="manual_ssr_picker"
        )

        if st.button(
            "Add Selected SSR Items"
        ):

            selected_rows = edited_items[
                edited_items["Add"]
            ]

            added_count = 0

            for item_id in selected_rows[
                "id"
            ]:

                item_id = int(
                    item_id
                )

                if item_id not in st.session_state.selected:

                    row = df.loc[
                        item_id
                    ]

                    quantity = calculate_quantity(
                        row=row,
                        length_m=length,
                        width_m=width,
                        thickness_mm=thickness,
                        pothole_area_m2=pothole_area,
                        drainage_length_m=drainage_length,
                        pothole_count=pothole_count
                    )

                    st.session_state.selected[
                        item_id
                    ] = quantity

                    added_count += 1

            if added_count:

                st.success(
                    f"{added_count} item(s) added."
                )

            else:

                st.info(
                    "No new items were added."
                )

    # ========================================================
    # COST ESTIMATE
    # ========================================================

    st.subheader(
        "9. Cost Estimate"
    )

    if not st.session_state.selected:

        st.info(
            "No SSR items are currently in the estimate."
        )

    else:

        rows = []

        for item_id, quantity in list(
            st.session_state.selected.items()
        ):

            if item_id not in df.index:

                continue

            row = df.loc[
                item_id
            ]

            rate = safe_float(
                row["rate"]
            )

            quantity = safe_float(
                quantity
            )

            rows.append(
                {
                    "Remove": False,
                    "ID": int(item_id),
                    "Item No": row[
                        "item_no"
                    ],
                    "Chapter": row[
                        "chapter"
                    ],
                    "Description": row[
                        "description"
                    ],
                    "Unit": row[
                        "unit"
                    ],
                    "Rate": rate,
                    "Quantity": quantity,
                    "Amount": (
                        quantity
                        * rate
                    )
                }
            )

        if rows:

            estimate_df = pd.DataFrame(
                rows
            )

            edited_estimate = st.data_editor(
                estimate_df,
                hide_index=True,
                use_container_width=True,
                height=450,
                disabled=[
                    "ID",
                    "Item No",
                    "Chapter",
                    "Description",
                    "Unit",
                    "Rate",
                    "Amount"
                ],
                column_config={
                    "ID": None,
                    "Quantity": st.column_config.NumberColumn(
                        "Quantity",
                        min_value=0.0,
                        step=0.001
                    ),
                    "Rate": st.column_config.NumberColumn(
                        "Rate",
                        format="%.2f"
                    ),
                    "Amount": st.column_config.NumberColumn(
                        "Amount",
                        format="%.2f"
                    )
                },
                key="final_estimate_editor"
            )

            # ------------------------------------------------
            # SAVE USER-EDITED QUANTITIES
            # ------------------------------------------------

            current_ids = set()

            for _, estimate_row in edited_estimate.iterrows():

                item_id = int(
                    estimate_row["ID"]
                )

                current_ids.add(
                    item_id
                )

                new_quantity = safe_float(
                    estimate_row["Quantity"]
                )

                if bool(
                    estimate_row["Remove"]
                ):

                    if item_id in st.session_state.selected:

                        del st.session_state.selected[
                            item_id
                        ]

                else:

                    st.session_state.selected[
                        item_id
                    ] = new_quantity

            # ------------------------------------------------
            # REBUILD AMOUNTS AFTER EDIT
            # ------------------------------------------------

            final_rows = []

            for item_id, quantity in (
                st.session_state.selected.items()
            ):

                if item_id not in df.index:

                    continue

                row = df.loc[
                    item_id
                ]

                rate = safe_float(
                    row["rate"]
                )

                amount = (
                    quantity
                    * rate
                )

                final_rows.append(
                    {
                        "Item No": row[
                            "item_no"
                        ],
                        "Chapter": row[
                            "chapter"
                        ],
                        "Description": row[
                            "description"
                        ],
                        "Unit": row[
                            "unit"
                        ],
                        "Rate": rate,
                        "Quantity": quantity,
                        "Amount": amount
                    }
                )

            final_estimate = pd.DataFrame(
                final_rows
            )

            if not final_estimate.empty:

                subtotal = safe_float(
                    final_estimate[
                        "Amount"
                    ].sum()
                )

                gst_amount = (
                    subtotal
                    * gst
                    / 100
                )

                total = (
                    subtotal
                    + gst_amount
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Subtotal",
                    f"Rs {subtotal:,.2f}"
                )

                c2.metric(
                    f"GST ({gst:.0f}%)",
                    f"Rs {gst_amount:,.2f}"
                )

                c3.metric(
                    "Total Estimate",
                    f"Rs {total:,.2f}"
                )

                # ------------------------------------------------
                # DOWNLOAD
                # ------------------------------------------------

                download_df = final_estimate.copy()

                download_df[
                    "GST Amount"
                ] = (
                    download_df[
                        "Amount"
                    ]
                    * gst
                    / 100
                )

                download_df[
                    "Amount Including GST"
                ] = (
                    download_df[
                        "Amount"
                    ]
                    + download_df[
                        "GST Amount"
                    ]
                )

                st.download_button(
                    "Download Estimate CSV",
                    download_df.to_csv(
                        index=False
                    ),
                    file_name=(
                        "road_estimate.csv"
                    ),
                    mime="text/csv"
                )

    # ========================================================
    # CLEAR ESTIMATE
    # ========================================================

    if st.button(
        "Clear Estimate"
    ):

        st.session_state.selected = {}

        st.session_state.estimate_generated = False

        st.session_state.estimate_signature = None

        st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Road Cost Estimator | AI-assisted road analysis "
    "and SSR-based estimation"
)
