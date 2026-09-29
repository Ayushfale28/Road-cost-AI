import os
import json
import pandas as pd
import streamlit as st

from ai_module import (
    analyze_photo,
    analyze_photos,
    chat_reply,
    generate_ssr_estimate
)

from ssr_loader import (
    load_ssr,
    match_chapters,
    search,
    get_ai_items,
    get_item_by_id,
    calculate_basic_quantity
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Road Estimator",
    page_icon="🛣️",
    layout="wide"
)

st.title("Road Cost Estimator")


# ============================================================
# SSR CHAPTER GROUPS
# ============================================================

COMMON_NEW = [
    "Road Survey and DPR",
    "Road Survey",
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
    os.path.dirname(
        os.path.abspath(__file__)
    ),
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
    "ai_estimate": [],
    "estimate_generated": False,
    "last_project_signature": None
}

for key, value in DEFAULT_STATE.items():

    if key not in st.session_state:

        if isinstance(value, list):
            st.session_state[key] = []

        elif isinstance(value, dict):
            st.session_state[key] = {}

        else:
            st.session_state[key] = value


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Project Setup")

    st.caption(
        "AI analysis and estimation are handled "
        "automatically in the backend."
    )

    st.subheader("SSR Source")

    st.caption(
        "Upload the PWD SSR you want to use for "
        "the estimate. If no file is uploaded, "
        "the default SSR will be used."
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
        ],
        help="Upload the SSR database used for rates and items."
    )

    if ssr_file:

        st.success(
            f"SSR loaded: {ssr_file.name}"
        )

    else:

        st.info(
            "Default SSR will be used."
        )


# ============================================================
# SSR LOADING
# ============================================================

@st.cache_data(
    show_spinner="Loading SSR..."
)
def get_ssr(file_source):

    return load_ssr(
        file_source
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

        except Exception as error:

            st.error(
                "The uploaded SSR could not be read."
            )

            st.error(
                str(error)
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
            "Upload an SSR file or place "
            "'SSR_2022-23 (2).xlsx' beside app.py."
        )

        st.stop()

    try:

        return get_ssr(
            DEFAULT_SSR_FILE
        )

    except Exception as error:

        st.error(
            "The default SSR could not be loaded."
        )

        st.error(
            str(error)
        )

        st.stop()


# ============================================================
# SITE PHOTOS
# ============================================================

st.subheader("1. Site Photos")

st.caption(
    "Upload one or multiple photos of the road, "
    "damaged section, kaccha track, or proposed "
    "road location."
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


# ============================================================
# PROJECT NOTE
# ============================================================

note = st.text_input(
    "Additional Project Information",
    placeholder=(
        "Example: Existing road has severe potholes "
        "and drainage problems."
    )
)


# ============================================================
# STORE PHOTOS
# ============================================================

if photos:

    current_names = [
        photo.name
        for photo in photos
    ]

    stored_names = [
        photo["name"]
        for photo in st.session_state.photos
    ]

    if current_names != stored_names:

        st.session_state.photos = []

        for uploaded_photo in photos:

            st.session_state.photos.append(
                {
                    "name": uploaded_photo.name,
                    "bytes": uploaded_photo.getvalue(),
                    "mime": uploaded_photo.type
                }
            )

        st.session_state.photo = (
            st.session_state.photos[0]["bytes"]
        )

        st.session_state.photo_mime = (
            st.session_state.photos[0]["mime"]
        )

        # New photos = new analysis context.
        st.session_state.ai_results = []
        st.session_state.ai = None
        st.session_state.ai_estimate = []
        st.session_state.estimate_generated = False
        st.session_state.selected = {}


# ============================================================
# PHOTO PREVIEW
# ============================================================

if photos:

    st.write(
        f"**{len(photos)} photo(s) uploaded.**"
    )

    preview_columns = st.columns(
        min(
            len(photos),
            4
        )
    )

    for index, uploaded_photo in enumerate(photos):

        with preview_columns[
            index % len(preview_columns)
        ]:

            st.image(
                uploaded_photo,
                caption=uploaded_photo.name,
                use_container_width=True
            )


    # ========================================================
    # ANALYZE PHOTOS
    # ========================================================

    if st.button(
        "Analyze Site",
        type="primary",
        use_container_width=True
    ):

        st.session_state.ai_results = []
        st.session_state.ai = None
        st.session_state.ai_estimate = []
        st.session_state.estimate_generated = False
        st.session_state.selected = {}

        progress = st.progress(0)
        status = st.empty()

        try:

            results = analyze_photos(
                st.session_state.photos,
                note=note
            )

            st.session_state.ai_results = results

            progress.progress(1.0)

            status.empty()

            if results:

                st.session_state.ai = (
                    results[0]["result"]
                )

            st.success(
                f"Finished analysing {len(results)} photo(s)."
            )

        except Exception as error:

            status.empty()

            st.error(
                "Site analysis is temporarily unavailable."
            )

            print(
                "Photo analysis error:",
                repr(error)
            )


# ============================================================
# PHOTO ANALYSIS RESULTS
# ============================================================

ai_results = st.session_state.ai_results

if ai_results:

    st.subheader(
        "2. Site Analysis"
    )

    # --------------------------------------------------------
    # COMBINED ANALYSIS
    # --------------------------------------------------------

    recommended_modes = []

    road_types = []

    all_observations = []

    all_works = []

    all_parameters = []

    for entry in ai_results:

        result = entry.get(
            "result",
            {}
        )

        recommendation = result.get(
            "recommended_mode",
            {}
        )

        if isinstance(
            recommendation,
            dict
        ):

            value = recommendation.get(
                "value"
            )

            if value:
                recommended_modes.append(
                    value
                )

        road_type = result.get(
            "road_type",
            {}
        )

        if isinstance(
            road_type,
            dict
        ):

            value = road_type.get(
                "value"
            )

            if value:
                road_types.append(
                    value
                )

        observations = result.get(
            "observations",
            []
        )

        if isinstance(
            observations,
            list
        ):

            all_observations.extend(
                observations
            )

        works = result.get(
            "suggested_works",
            []
        )

        if isinstance(
            works,
            list
        ):

            all_works.extend(
                works
            )

        parameters = result.get(
            "suggested_parameters",
            []
        )

        if isinstance(
            parameters,
            list
        ):

            all_parameters.extend(
                parameters
            )


    # --------------------------------------------------------
    # DISPLAY PHOTO RESULTS
    # --------------------------------------------------------

    for index, entry in enumerate(
        ai_results
    ):

        result = entry.get(
            "result",
            {}
        )

        photo_name = entry.get(
            "name",
            f"Photo {index + 1}"
        )

        with st.expander(
            f"Photo {index + 1}: {photo_name}",
            expanded=(index == 0)
        ):

            recommendation = result.get(
                "recommended_mode",
                {}
            )

            if isinstance(
                recommendation,
                dict
            ):

                rec_value = recommendation.get(
                    "value",
                    "unclear"
                )

                rec_confidence = recommendation.get(
                    "confidence",
                    "-"
                )

                rec_reason = recommendation.get(
                    "reason",
                    ""
                )

                st.info(
                    f"**Suggested Work Type:** "
                    f"{rec_value.replace('_', ' ').title()}  \n"
                    f"**Confidence:** {rec_confidence}"
                )

                if rec_reason:
                    st.write(
                        rec_reason
                    )

            site_type = result.get(
                "site_type",
                {}
            )

            if isinstance(
                site_type,
                dict
            ):

                site_type = site_type.get(
                    "value",
                    "-"
                )

            road_type = result.get(
                "road_type",
                {}
            )

            if isinstance(
                road_type,
                dict
            ):

                road_type = road_type.get(
                    "value",
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
                    "**Detected Defects**"
                )

                try:

                    st.dataframe(
                        pd.DataFrame(defects),
                        hide_index=True,
                        use_container_width=True
                    )

                except Exception:

                    st.write(
                        defects
                    )

            limitations = result.get(
                "limitations"
            )

            if limitations:

                st.caption(
                    f"Limitations: {limitations}"
                )


# ============================================================
# LOAD SSR
# ============================================================

df = load_selected_ssr()

if not isinstance(
    df,
    pd.DataFrame
):

    st.error(
        "SSR loader did not return a DataFrame."
    )

    st.stop()


# ============================================================
# REQUIRED COLUMNS
# ============================================================

required_ssr_columns = [
    "id",
    "item_no",
    "chapter",
    "description",
    "unit",
    "rate",
    "unit_kind"
]

missing_columns = [
    column
    for column in required_ssr_columns
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
# CHAT ASSISTANT
# ============================================================

with chat_tab:

    st.subheader(
        "Road Project Assistant"
    )

    st.caption(
        "Ask questions about the road project, "
        "measurements or estimation."
    )

    for message in st.session_state.chat:

        with st.chat_message(
            message["role"]
        ):

            st.markdown(
                message["content"]
            )

    clear_chat = st.button(
        "Clear Chat"
    )

    if clear_chat:

        st.session_state.chat = []

        st.rerun()

    user_message = st.chat_input(
        "Ask about your road project..."
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
                analysis=st.session_state.ai,
                image_bytes=st.session_state.photo,
                mime_type=st.session_state.photo_mime
            )

            st.session_state.chat.append(
                {
                    "role": "assistant",
                    "content": response
                }
            )

        except Exception as error:

            st.session_state.chat.pop()

            st.error(
                "The assistant is temporarily unavailable."
            )

            print(
                "Chat error:",
                repr(error)
            )

        st.rerun()


# ============================================================
# ESTIMATE TAB
# ============================================================

with estimate_tab:

    st.subheader(
        "3. Project Type"
    )

    # --------------------------------------------------------
    # AI MODE SUGGESTION
    # --------------------------------------------------------

    ai_mode = None

    if st.session_state.ai:

        recommendation = st.session_state.ai.get(
            "recommended_mode"
        )

        if isinstance(
            recommendation,
            dict
        ):

            ai_mode = recommendation.get(
                "value"
            )


    mode_options = [
        "Repair (Existing Road)",
        "New Road Construction"
    ]

    default_index = 0

    if ai_mode == "new_construction":

        default_index = 1

    mode = st.radio(
        "Work Type",
        mode_options,
        index=default_index,
        horizontal=True
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
            "Select Road Type",
            [
                "Concrete (CC)",
                "Bitumen / Dambar"
            ],
            horizontal=True
        )


    # ========================================================
    # MEASUREMENTS
    # ========================================================

    st.subheader(
        "5. Project Measurements"
    )

    c1, c2, c3 = st.columns(3)

    length = c1.number_input(
        "Road Length (m)",
        min_value=0.0,
        value=0.0,
        step=10.0
    )

    width = c2.number_input(
        "Road Width (m)",
        min_value=0.0,
        value=0.0,
        step=0.1
    )

    thickness = c3.number_input(
        "Main Layer Thickness (mm)",
        min_value=0.0,
        value=0.0,
        step=5.0
    )


    c4, c5, c6 = st.columns(3)

    traffic_type = c4.selectbox(
        "Traffic Type",
        [
            "Not specified",
            "Light",
            "Medium",
            "Heavy"
        ]
    )

    soil_condition = c5.selectbox(
        "Sub-grade / Soil Condition",
        [
            "Not specified",
            "Good",
            "Moderate",
            "Poor",
            "Weak"
        ]
    )

    lead_distance = c6.number_input(
        "Material Lead Distance (km)",
        min_value=0.0,
        value=0.0,
        step=1.0
    )


    # ========================================================
    # ADDITIONAL PROJECT PARAMETERS
    # ========================================================

    st.subheader(
        "6. Additional Conditions"
    )

    c1, c2 = st.columns(2)

    drainage_required = c1.selectbox(
        "Drainage / Culvert Requirement",
        [
            "Not specified",
            "Not required",
            "Required"
        ]
    )

    pothole_count = c2.number_input(
        "Number of Potholes",
        min_value=0,
        value=0,
        step=1
    )


    additional_conditions = st.text_area(
        "Other Project Information",
        placeholder=(
            "Example: Road passes through a village area, "
            "existing side drain is damaged, heavy vehicles "
            "use the road."
        )
    )


    # ========================================================
    # CHAPTER FILTER
    # ========================================================

    all_chapters = sorted(
        [
            str(x)
            for x in df["chapter"]
            .dropna()
            .unique()
        ]
    )


    if mode == "New Road Construction":

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
    # AI SSR ESTIMATION
    # ========================================================

    st.subheader(
        "7. AI SSR Recommendation"
    )

    st.caption(
        "The AI will identify applicable SSR items from "
        "your uploaded SSR. Rates are taken directly "
        "from the SSR file."
    )


    measurements_complete = (
        length > 0
        and width > 0
    )


    if mode == "New Road Construction":

        measurements_complete = (
            measurements_complete
            and thickness > 0
        )


    if st.button(
        "Generate AI SSR Estimate",
        type="primary",
        disabled=not measurements_complete,
        use_container_width=True
    ):

        # ----------------------------------------------------
        # Reset previous AI estimate
        # ----------------------------------------------------

        st.session_state.ai_estimate = []
        st.session_state.selected = {}

        # ----------------------------------------------------
        # Prepare SSR items
        # ----------------------------------------------------

        ai_items = get_ai_items(
            df,
            max_items=500
        )

        # ----------------------------------------------------
        # Prepare project information
        # ----------------------------------------------------

        project_data = {

            "work_type": (
                "new_construction"
                if mode == "New Road Construction"
                else "repair"
            ),

            "road_type": (
                "concrete_cc"
                if road_kind == "Concrete (CC)"
                else (
                    "bitumen_bt"
                    if road_kind == "Bitumen / Dambar"
                    else "existing_road"
                )
            ),

            "length_m": length,

            "width_m": width,

            "thickness_mm": thickness,

            "traffic_type": traffic_type,

            "soil_condition": soil_condition,

            "lead_distance_km": lead_distance,

            "drainage_required": drainage_required,

            "pothole_count": pothole_count,

            "additional_conditions": (
                additional_conditions
            )
        }

        # ----------------------------------------------------
        # AI selection
        # ----------------------------------------------------

        with st.spinner(
            "Preparing SSR items..."
        ):

            try:

                ai_response = generate_ssr_estimate(
                    project_data=project_data,
                    ssr_items=ai_items,
                    photo_analysis=(
                        st.session_state.ai_results
                    )
                )

                if not isinstance(
                    ai_response,
                    dict
                ):

                    raise ValueError(
                        "Invalid AI estimate response."
                    )

                recommended_items = (
                    ai_response.get(
                        "selected_items",
                        []
                    )
                )

                if not recommended_items:

                    st.warning(
                        "The AI could not identify suitable SSR items. "
                        "Please search and select items manually."
                    )

                # ------------------------------------------------
                # Validate AI item IDs against real SSR
                # ------------------------------------------------

                final_ai_items = []

                for item in recommended_items:

                    if not isinstance(
                        item,
                        dict
                    ):
                        continue

                    item_id = item.get(
                        "id"
                    )

                    try:

                        item_id = int(
                            item_id
                        )

                    except Exception:

                        continue

                    real_item = get_item_by_id(
                        df,
                        item_id
                    )

                    if real_item is None:
                        continue

                    # --------------------------------------------
                    # Calculate deterministic quantity
                    # --------------------------------------------

                    calculated_quantity = (
                        calculate_basic_quantity(
                            real_item["unit_kind"],
                            length,
                            width,
                            thickness,
                            pothole_count
                        )
                    )

                    # --------------------------------------------
                    # If AI supplied a quantity but Python
                    # cannot safely calculate it, retain AI
                    # suggestion for user review.
                    # --------------------------------------------

                    ai_quantity = item.get(
                        "quantity"
                    )

                    if calculated_quantity is not None:

                        quantity = float(
                            calculated_quantity
                        )

                        calculation_method = (
                            "Calculated from project measurements"
                        )

                    elif ai_quantity is not None:

                        try:

                            quantity = float(
                                ai_quantity
                            )

                        except Exception:

                            quantity = 0.0

                        calculation_method = (
                            "AI suggested quantity - "
                            "user verification required"
                        )

                    else:

                        quantity = 0.0

                        calculation_method = (
                            "Manual quantity required"
                        )

                    final_ai_items.append(
                        {
                            "id": int(real_item["id"]),
                            "item_no": real_item["item_no"],
                            "chapter": real_item["chapter"],
                            "description": real_item["description"],
                            "unit": real_item["unit"],
                            "unit_kind": real_item["unit_kind"],
                            "rate": float(real_item["rate"]),
                            "quantity": quantity,
                            "calculation": (
                                item.get(
                                    "calculation",
                                    calculation_method
                                )
                            ),
                            "reason": item.get(
                                "reason",
                                ""
                            ),
                            "confidence": item.get(
                                "confidence",
                                "medium"
                            )
                        }
                    )

                st.session_state.ai_estimate = (
                    final_ai_items
                )

                # ------------------------------------------------
                # Add AI items to estimate
                # ------------------------------------------------

                for item in final_ai_items:

                    st.session_state.selected[
                        int(item["id"])
                    ] = float(
                        item["quantity"]
                    )

                st.session_state.estimate_generated = True

                st.success(
                    "AI SSR recommendation generated. "
                    "Please review the items before finalizing."
                )

            except Exception as error:

                print(
                    "AI SSR estimation error:",
                    repr(error)
                )

                st.error(
                    "The AI estimate could not be generated."
                )

                st.info(
                    "You can still search and select SSR items manually."
                )


    # ========================================================
    # AI RECOMMENDED ITEMS
    # ========================================================

    if st.session_state.ai_estimate:

        st.subheader(
            "AI Recommended SSR Items"
        )

        ai_display = []

        for item in st.session_state.ai_estimate:

            ai_display.append(
                {
                    "Item No": item["item_no"],
                    "Chapter": item["chapter"],
                    "Description": item["description"],
                    "Unit": item["unit"],
                    "Quantity": item["quantity"],
                    "Rate": item["rate"],
                    "Reason": item["reason"],
                    "Confidence": item["confidence"]
                }
            )

        st.dataframe(
            pd.DataFrame(ai_display),
            hide_index=True,
            use_container_width=True
        )

        st.info(
            "These are AI-recommended items. "
            "You have full control to modify, remove, "
            "or add items below."
        )


    # ========================================================
    # MANUAL SSR SEARCH
    # ========================================================

    st.subheader(
        "8. Add / Modify SSR Items"
    )

    chapters = st.multiselect(
        "SSR Chapters",
        options=all_chapters,
        default=preset_chapters
    )

    keywords_text = st.text_input(
        "Search SSR Items",
        placeholder=(
            "Example: excavation, concrete, "
            "bitumen, pothole"
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

    except Exception as error:

        st.error(
            "SSR search failed."
        )

        print(
            "SSR search error:",
            repr(error)
        )

        found_items = pd.DataFrame(
            columns=required_ssr_columns
        )


    st.caption(
        f"{len(found_items)} SSR items found."
    )


    # ========================================================
    # ITEM SELECTOR
    # ========================================================

    if not found_items.empty:

        item_view = found_items[
            required_ssr_columns
        ].copy()

        item_view.insert(
            0,
            "Select",
            False
        )

        edited_items = st.data_editor(
            item_view,
            hide_index=True,
            use_container_width=True,
            height=350,
            disabled=[
                "id",
                "item_no",
                "chapter",
                "description",
                "unit",
                "rate",
                "unit_kind"
            ],
            column_config={
                "id": None,
                "unit_kind": None
            },
            key="ssr_item_picker"
        )

        if st.button(
            "Add Selected SSR Items"
        ):

            selected_rows = edited_items[
                edited_items["Select"]
            ]

            added_count = 0

            for _, selected_row in selected_rows.iterrows():

                item_id = int(
                    selected_row["id"]
                )

                # Do not reset an existing quantity.
                if item_id not in st.session_state.selected:

                    real_item = get_item_by_id(
                        df,
                        item_id
                    )

                    if real_item:

                        calculated_quantity = (
                            calculate_basic_quantity(
                                real_item["unit_kind"],
                                length,
                                width,
                                thickness,
                                pothole_count
                            )
                        )

                        if calculated_quantity is None:
                            calculated_quantity = 0.0

                        st.session_state.selected[
                            item_id
                        ] = float(
                            calculated_quantity
                        )

                        added_count += 1

            st.success(
                f"{added_count} new SSR item(s) added."
            )

    else:

        st.info(
            "No matching SSR items found. "
            "Try changing the chapter or search keywords."
        )


    # ========================================================
    # FINAL ESTIMATE
    # ========================================================

    st.subheader(
        "9. Final Estimate"
    )

    if not st.session_state.selected:

        st.info(
            "No SSR items have been selected yet."
        )

    else:

        estimate_rows = []

        for item_id, quantity in (
            st.session_state.selected.items()
        ):

            real_item = get_item_by_id(
                df,
                item_id
            )

            if real_item is None:
                continue

            estimate_rows.append(
                {
                    "Remove": False,
                    "ID": int(real_item["id"]),
                    "Item No": real_item["item_no"],
                    "Chapter": real_item["chapter"],
                    "Description": real_item["description"],
                    "Unit": real_item["unit"],
                    "Rate": float(real_item["rate"]),
                    "Quantity": float(quantity)
                }
            )

        if estimate_rows:

            estimate_df = pd.DataFrame(
                estimate_rows
            )

            edited_estimate = st.data_editor(
                estimate_df,
                hide_index=True,
                use_container_width=True,
                disabled=[
                    "ID",
                    "Item No",
                    "Chapter",
                    "Description",
                    "Unit",
                    "Rate"
                ],
                column_config={
                    "ID": None,
                    "Quantity": st.column_config.NumberColumn(
                        "Quantity",
                        min_value=0.0,
                        step=0.01
                    )
                },
                key="final_estimate_editor"
            )

            # ------------------------------------------------
            # UPDATE QUANTITIES
            # ------------------------------------------------

            for _, row in edited_estimate.iterrows():

                item_id = int(
                    row["ID"]
                )

                try:

                    quantity = float(
                        row["Quantity"]
                    )

                except Exception:

                    quantity = 0.0

                st.session_state.selected[
                    item_id
                ] = max(
                    0.0,
                    quantity
                )


            # ------------------------------------------------
            # REMOVE ITEMS
            # ------------------------------------------------

            removed_ids = []

            for _, row in edited_estimate.iterrows():

                if bool(
                    row["Remove"]
                ):

                    removed_ids.append(
                        int(row["ID"])
                    )

            for item_id in removed_ids:

                st.session_state.selected.pop(
                    item_id,
                    None
                )

            if removed_ids:

                st.rerun()


            # ------------------------------------------------
            # RECALCULATE AMOUNTS
            # ------------------------------------------------

            final_rows = []

            for item_id, quantity in (
                st.session_state.selected.items()
            ):

                real_item = get_item_by_id(
                    df,
                    item_id
                )

                if real_item is None:
                    continue

                rate = float(
                    real_item["rate"]
                )

                amount = (
                    quantity
                    * rate
                )

                final_rows.append(
                    {
                        "Item No": real_item["item_no"],
                        "Chapter": real_item["chapter"],
                        "Description": real_item["description"],
                        "Unit": real_item["unit"],
                        "Quantity": quantity,
                        "Rate": rate,
                        "Amount": amount
                    }
                )

            final_estimate = pd.DataFrame(
                final_rows
            )


            # ------------------------------------------------
            # TOTAL
            # ------------------------------------------------

            if not final_estimate.empty:

                subtotal = float(
                    final_estimate["Amount"].sum()
                )

                gst = st.number_input(
                    "GST (%)",
                    min_value=0.0,
                    value=18.0,
                    step=1.0
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

                st.download_button(
                    "Download Estimate CSV",
                    final_estimate.to_csv(
                        index=False
                    ),
                    file_name="road_estimate.csv",
                    mime="text/csv"
                )


    # ========================================================
    # CLEAR ESTIMATE
    # ========================================================

    if st.session_state.selected:

        if st.button(
            "Clear Estimate"
        ):

            st.session_state.selected = {}
            st.session_state.ai_estimate = []
            st.session_state.estimate_generated = False

            st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Road Cost Estimator | AI-assisted site analysis "
    "and SSR-based estimation"
)
