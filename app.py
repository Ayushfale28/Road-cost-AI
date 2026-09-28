import os
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

if "ai" not in st.session_state:
    st.session_state.ai = None

if "ai_results" not in st.session_state:
    st.session_state.ai_results = []

if "photos" not in st.session_state:
    st.session_state.photos = []

if "photo" not in st.session_state:
    st.session_state.photo = None

if "photo_mime" not in st.session_state:
    st.session_state.photo_mime = "image/jpeg"

if "selected" not in st.session_state:
    st.session_state.selected = {}

if "chat" not in st.session_state:
    st.session_state.chat = []


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Project Setup")

    # --------------------------------------------------------
    # GEMINI API KEY
    # --------------------------------------------------------

    try:
        secret_key = st.secrets.get(
            "GEMINI_API_KEY",
            ""
        )
    except Exception:
        secret_key = ""

    api_key = secret_key or os.getenv(
        "GEMINI_API_KEY",
        ""
    )

    api_key = st.text_input(
        "Gemini API Key (Optional)",
        value=api_key,
        type="password",
        help=(
            "Gemini is optional. The application can still "
            "work without an API key."
        )
    )

    if api_key:
        st.success("Gemini API key available.")
    else:
        st.info(
            "No Gemini API key. "
            "The built-in road assistant will be used."
        )


    # --------------------------------------------------------
    # SSR SOURCE
    # --------------------------------------------------------

    st.subheader("SSR Source")

    st.caption(
        "Upload your SSR if you have one. "
        "If you do not upload an SSR, the default SSR "
        "will be used automatically."
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
        help=(
            "Upload the SSR file to be used for "
            "the estimate."
        )
    )

    if ssr_file is not None:

        st.success(
            f"Using uploaded SSR: {ssr_file.name}"
        )

    else:

        st.info(
            "No SSR uploaded. "
            "The default SSR will be used."
        )

        st.caption(
            "Default SSR: SSR_2022-23 (2).xlsx"
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
    # USER UPLOADED SSR
    # --------------------------------------------------------

    if ssr_file is not None:

        try:

            df = get_ssr(
                ssr_file
            )

            return df

        except Exception as error:

            st.error(
                "The uploaded SSR could not be read."
            )

            st.error(
                f"Error details: {error}"
            )

            st.info(
                "Please check that the SSR contains "
                "the required item, description, unit, "
                "rate and chapter information."
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
            "Please upload your SSR or make sure "
            "'SSR_2022-23 (2).xlsx' exists in the "
            "same folder as app.py."
        )

        st.stop()


    try:

        df = get_ssr(
            DEFAULT_SSR_FILE
        )

        return df

    except Exception as error:

        st.error(
            "The default SSR could not be loaded."
        )

        st.error(
            f"Error details: {error}"
        )

        st.stop()


# ============================================================
# SITE PHOTOS
# ============================================================

st.subheader("1. Site Photos")

st.caption(
    "You can upload one or multiple photos of the "
    "existing road, damaged road, unpaved road, "
    "or land where a new road is planned."
)


# ============================================================
# MULTIPLE PHOTO UPLOAD
# ============================================================

photos = st.file_uploader(

    "Upload Road Photos",

    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ],

    accept_multiple_files=True,

    help=(
        "You can select multiple road photos at once."
    )
)


# ============================================================
# ADDITIONAL NOTE
# ============================================================

note = st.text_input(

    "Additional Information (Optional)",

    placeholder=(
        "Example: The road has potholes and needs repair."
    )
)


# ============================================================
# STORE UPLOADED PHOTOS
# ============================================================

if photos:

    st.session_state.photos = []

    for uploaded_photo in photos:

        photo_data = {
            "name": uploaded_photo.name,
            "bytes": uploaded_photo.getvalue(),
            "mime": uploaded_photo.type
        }

        st.session_state.photos.append(
            photo_data
        )

    # Keep first photo for chat compatibility
    st.session_state.photo = (
        st.session_state.photos[0]["bytes"]
    )

    st.session_state.photo_mime = (
        st.session_state.photos[0]["mime"]
    )


# ============================================================
# DISPLAY UPLOADED PHOTOS
# ============================================================

if photos:

    st.write(
        f"**{len(photos)} photo(s) uploaded.**"
    )

    # Create columns for photo preview
    preview_columns = st.columns(
        min(len(photos), 4)
    )

    for index, uploaded_photo in enumerate(photos):

        column = preview_columns[
            index % len(preview_columns)
        ]

        with column:

            st.image(
                uploaded_photo,
                caption=uploaded_photo.name,
                use_container_width=True
            )


    # ========================================================
    # ANALYZE ALL PHOTOS
    # ========================================================

    if st.button(
        "Analyze All Photos",
        type="primary"
    ):

        st.session_state.ai_results = []
        st.session_state.ai = None

        progress = st.progress(
            0
        )

        status = st.empty()

        for index, uploaded_photo in enumerate(
            photos
        ):

            status.write(
                f"Analyzing photo {index + 1} "
                f"of {len(photos)}: "
                f"{uploaded_photo.name}"
            )

            try:

                result = analyze_photo(

                    uploaded_photo.getvalue(),

                    uploaded_photo.type,

                    api_key,

                    note

                )

                st.session_state.ai_results.append(

                    {
                        "name": uploaded_photo.name,
                        "result": result
                    }

                )

            except Exception as error:

                st.session_state.ai_results.append(

                    {
                        "name": uploaded_photo.name,

                        "result": {

                            "recommended_mode": None,

                            "confidence": "not_available",

                            "observations": [
                                "Photo analysis failed.",
                                "Please review this photo manually."
                            ],

                            "source": "error",

                            "error": str(error)

                        }

                    }

                )

            progress.progress(
                (index + 1) / len(photos)
            )

        status.empty()

        # ----------------------------------------------------
        # USE FIRST RESULT FOR EXISTING ESTIMATE LOGIC
        # ----------------------------------------------------

        if st.session_state.ai_results:

            st.session_state.ai = (
                st.session_state.ai_results[0]["result"]
            )

        st.success(
            f"Finished processing {len(photos)} photo(s)."
        )


# ============================================================
# PHOTO ANALYSIS RESULTS
# ============================================================

ai_results = st.session_state.ai_results


if ai_results:

    st.subheader(
        "Photo Analysis Results"
    )


    # ========================================================
    # DISPLAY EACH PHOTO RESULT
    # ========================================================

    for index, analysis_entry in enumerate(
        ai_results
    ):

        photo_name = analysis_entry[
            "name"
        ]

        result = analysis_entry[
            "result"
        ]

        with st.expander(
            f"Photo {index + 1}: {photo_name}",
            expanded=(index == 0)
        ):

            # ------------------------------------------------
            # RECOMMENDATION
            # ------------------------------------------------

            recommendation = result.get(
                "recommended_mode"
            )

            if isinstance(
                recommendation,
                dict
            ):

                recommendation_value = (
                    recommendation.get(
                        "value",
                        "unclear"
                    )
                )

                confidence = (
                    recommendation.get(
                        "confidence",
                        "-"
                    )
                )

                reason = (
                    recommendation.get(
                        "reason",
                        ""
                    )
                )

            else:

                recommendation_value = (
                    "Not available"
                )

                confidence = (
                    result.get(
                        "confidence",
                        "-"
                    )
                )

                reason = (
                    result.get(
                        "message",
                        ""
                    )
                )


            st.info(

                f"**Suggested Work Type:** "
                f"{recommendation_value}  \n"
                f"**Confidence:** {confidence}"

            )


            if reason:

                st.write(
                    f"**Note:** {reason}"
                )


            # ------------------------------------------------
            # OBSERVATIONS
            # ------------------------------------------------

            observations = result.get(
                "observations"
            )

            if observations:

                st.markdown(
                    "**Observations:**"
                )

                if isinstance(
                    observations,
                    list
                ):

                    for observation in observations:

                        st.write(
                            f"- {observation}"
                        )

                else:

                    st.write(
                        observations
                    )


            # ------------------------------------------------
            # SITE TYPE
            # ------------------------------------------------

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


            # ------------------------------------------------
            # ROAD TYPE
            # ------------------------------------------------

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


            # ------------------------------------------------
            # PHOTO QUALITY
            # ------------------------------------------------

            photo_quality = result.get(
                "photo_quality",
                "-"
            )


            # ------------------------------------------------
            # SURFACE CONDITION
            # ------------------------------------------------

            surface_condition = result.get(
                "surface_condition",
                "-"
            )


            st.write(
                f"**Site Type:** {site_type}"
            )

            st.write(
                f"**Road Type:** {road_type}"
            )

            st.write(
                f"**Photo Quality:** {photo_quality}"
            )

            st.write(
                f"**Surface Condition:** "
                f"{surface_condition}"
            )


            # ------------------------------------------------
            # DEFECTS
            # ------------------------------------------------

            defects = result.get(
                "defects"
            )

            if defects:

                st.markdown(
                    "**Detected / Reported Defects:**"
                )

                try:

                    st.dataframe(
                        pd.DataFrame(
                            defects
                        ),
                        hide_index=True,
                        use_container_width=True
                    )

                except Exception:

                    st.write(
                        defects
                    )


            # ------------------------------------------------
            # NEW ROAD NOTES
            # ------------------------------------------------

            new_road_notes = result.get(
                "new_road_notes"
            )

            if new_road_notes:

                st.markdown(
                    "**New Road Notes:**"
                )

                st.json(
                    new_road_notes
                )


            # ------------------------------------------------
            # SUGGESTED PARAMETERS
            # ------------------------------------------------

            suggested_parameters = result.get(
                "suggested_parameters",
                []
            )

            if suggested_parameters:

                st.markdown(
                    "**Measurements / Decisions "
                    "to Confirm:**"
                )

                for parameter in suggested_parameters:

                    if isinstance(
                        parameter,
                        dict
                    ):

                        parameter_name = parameter.get(
                            "name",
                            "-"
                        )

                        why_needed = parameter.get(
                            "why_needed",
                            ""
                        )

                        st.write(
                            f"- **{parameter_name}** "
                            f"{'— ' + why_needed if why_needed else ''}"
                        )


            # ------------------------------------------------
            # LIMITATIONS
            # ------------------------------------------------

            limitations = result.get(
                "limitations"
            )

            if limitations:

                st.caption(
                    f"Limitations: {limitations}"
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
# CHAT ASSISTANT
# ============================================================

with chat_tab:

    st.subheader(
        "Road Project Chat Assistant"
    )

    st.caption(
        "Ask questions about your road project. "
        "The assistant helps you collect project "
        "information and understand the estimation process."
    )


    # --------------------------------------------------------
    # DISPLAY CHAT HISTORY
    # --------------------------------------------------------

    for message in st.session_state.chat:

        with st.chat_message(
            message["role"]
        ):

            st.markdown(
                message["content"]
            )


    # --------------------------------------------------------
    # CLEAR CHAT
    # --------------------------------------------------------

    if st.button(
        "Clear Chat"
    ):

        st.session_state.chat = []

        st.rerun()


    # --------------------------------------------------------
    # CHAT INPUT
    # --------------------------------------------------------

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

                api_key,

                st.session_state.ai,

                st.session_state.photo,

                st.session_state.photo_mime

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
                f"Chat failed: {error}"
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


    # --------------------------------------------------------
    # CHECK SSR DATA
    # --------------------------------------------------------

    if not isinstance(
        df,
        pd.DataFrame
    ):

        st.error(
            "The SSR loader did not return a DataFrame."
        )

        st.warning(
            "Please check ssr_loader.py."
        )

        st.stop()


    # --------------------------------------------------------
    # CHECK REQUIRED SSR COLUMNS
    # --------------------------------------------------------

    required_ssr_columns = [
        "id",
        "item_no",
        "chapter",
        "description",
        "unit",
        "rate"
    ]

    missing_ssr_columns = [

        column

        for column in required_ssr_columns

        if column not in df.columns

    ]

    if missing_ssr_columns:

        st.error(
            "Required SSR columns are missing."
        )

        st.write(
            missing_ssr_columns
        )

        st.stop()


    # --------------------------------------------------------
    # CHAPTERS
    # --------------------------------------------------------

    all_chapters = list(

        df[
            "chapter"
        ]
        .dropna()
        .unique()

    )


    # ========================================================
    # WORK MODE
    # ========================================================

    st.subheader(
        "3. Select Work Type"
    )

    modes = [

        "Repair (Existing Road)",

        "New Road Construction"

    ]


    # --------------------------------------------------------
    # READ AI RECOMMENDATION SAFELY
    # --------------------------------------------------------

    ai_mode = None

    if st.session_state.ai:

        recommendation = (
            st.session_state.ai.get(
                "recommended_mode"
            )
        )

        if isinstance(
            recommendation,
            dict
        ):

            ai_mode = recommendation.get(
                "value"
            )


    # --------------------------------------------------------
    # DEFAULT SELECTION
    # --------------------------------------------------------

    default_mode_index = 0

    if ai_mode == "new_construction":

        default_mode_index = 1


    mode = st.radio(

        "Work Type",

        modes,

        index=default_mode_index,

        horizontal=True,

        help=(
            "The photo analysis is only a suggestion. "
            "Confirm the correct work type yourself."
        )

    )


    # ========================================================
    # ROAD TYPE
    # ========================================================

    road_kind = None


    if mode == "New Road Construction":

        st.subheader(
            "4. Select Road Type"
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


    # ========================================================
    # CHAPTER MATCHING
    # ========================================================

    preset_chapters = match_chapters(

        all_chapters,

        wanted_chapters

    )


    # ========================================================
    # MEASUREMENTS
    # ========================================================

    st.subheader(
        "5. Project Measurements"
    )


    col1, col2, col3, col4 = st.columns(4)


    length = col1.number_input(

        "Length (m)",

        min_value=0.0,

        value=0.0,

        step=1.0

    )


    width = col2.number_input(

        "Width (m)",

        min_value=0.0,

        value=0.0,

        step=0.1

    )


    thickness = col3.number_input(

        "Thickness (mm)",

        min_value=0.0,

        value=0.0,

        step=5.0

    )


    gst = col4.number_input(

        "GST (%)",

        min_value=0.0,

        value=18.0,

        step=1.0

    )


    # ========================================================
    # SSR ITEMS
    # ========================================================

    st.subheader(
        "6. Select SSR Items"
    )


    chapters = st.multiselect(

        "SSR Chapters",

        sorted(
            all_chapters
        ),

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


    # --------------------------------------------------------
    # SEARCH SSR
    # --------------------------------------------------------

    try:

        found_items = search(

            df,

            chapters,

            keywords

        )

    except Exception as error:

        st.error(
            f"SSR search failed: {error}"
        )

        st.stop()


    st.caption(
        f"{len(found_items)} SSR items found."
    )


    # ========================================================
    # SHOW ITEMS
    # ========================================================

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
            "rate"
        ],

        column_config={

            "id": None

        },

        key="ssr_item_picker"

    )


    # ========================================================
    # ADD ITEMS
    # ========================================================

    if st.button(
        "Add Selected Items"
    ):

        selected_rows = edited_items[
            edited_items["Select"]
        ]


        for item_id in selected_rows[
            "id"
        ]:

            st.session_state.selected[
                int(item_id)
            ] = 0.0


        st.success(
            "Selected items added to the estimate."
        )


    # ========================================================
    # COST ESTIMATE
    # ========================================================

    st.subheader(
        "7. Cost Estimate"
    )


    if not st.session_state.selected:

        st.info(
            "No SSR items selected yet."
        )


    else:

        estimate_rows = []


        for item_id, quantity in (

            st.session_state.selected.items()

        ):

            if item_id not in df.index:

                continue


            row = df.loc[
                item_id
            ]


            estimate_rows.append(

                {

                    "Remove": False,

                    "Item No":
                        row["item_no"],

                    "Description":
                        row["description"],

                    "Unit":
                        row["unit"],

                    "Rate":
                        row["rate"],

                    "Quantity":
                        quantity

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
                    "Item No",
                    "Description",
                    "Unit",
                    "Rate"
                ],

                key="estimate_editor"

            )


            # ------------------------------------------------
            # AMOUNT
            # ------------------------------------------------

            edited_estimate[
                "Amount"
            ] = (

                edited_estimate[
                    "Quantity"
                ]

                *

                edited_estimate[
                    "Rate"
                ]

            )


            # ------------------------------------------------
            # REMOVE ITEMS
            # ------------------------------------------------

            final_estimate = edited_estimate[

                ~edited_estimate[
                    "Remove"
                ]

            ].copy()


            # ------------------------------------------------
            # TOTALS
            # ------------------------------------------------

            subtotal = final_estimate[
                "Amount"
            ].sum()


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


        # ----------------------------------------------------
        # CLEAR ITEMS
        # ----------------------------------------------------

        if st.button(
            "Clear Selected Items"
        ):

            st.session_state.selected = {}

            st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Road Cost Estimator | AI-assisted road analysis "
    "and SSR-based estimation"
)
