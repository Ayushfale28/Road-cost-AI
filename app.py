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

# Keep this file in the same GitHub folder as app.py.
DEFAULT_SSR_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "SSR_2022-23 (2).xlsx"
)


# ============================================================
# SESSION STATE
# ============================================================

if "ai" not in st.session_state:
    st.session_state.ai = None

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
        "Gemini API Key",
        value=api_key,
        type="password"
    )


    # --------------------------------------------------------
    # SSR UPLOAD
    # --------------------------------------------------------

    st.subheader("SSR Source")

    st.caption(
        "Upload your own SSR if you have one. "
        "If you do not upload an SSR, the website will "
        "automatically use the default SSR."
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
            "Supported formats: Excel, CSV, PDF, DOCX and TXT."
        )
    )


    # --------------------------------------------------------
    # SHOW SSR STATUS
    # --------------------------------------------------------

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

@st.cache_data(show_spinner="Loading SSR...")
def get_ssr(file_source):

    return load_ssr(file_source)


def load_selected_ssr():

    """
    SSR priority:

    1. User uploaded SSR
    2. Default SSR

    The selected SSR is passed to the existing
    ssr_loader.py file.
    """

    # --------------------------------------------------------
    # USER SSR
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
            "Please upload your own SSR or make sure "
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
# PHOTO ANALYSIS
# ============================================================

st.subheader("1. Site Photo")

st.caption(
    "Upload a photo of an existing road, damaged road, "
    "unpaved road or land where a new road is planned."
)

photo = st.file_uploader(
    "Upload Road Photo",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ]
)


note = st.text_input(
    "Additional Information (Optional)",
    placeholder=(
        "Example: The road has potholes "
        "and needs repair."
    )
)


if photo is not None:

    st.session_state.photo = photo.getvalue()

    st.session_state.photo_mime = photo.type

    col1, col2 = st.columns(
        [1, 2]
    )

    with col1:

        st.image(
            photo,
            width=300
        )

    with col2:

        if st.button(
            "Analyze Photo with AI"
        ):

            if not api_key:

                st.error(
                    "Please enter your Gemini API key."
                )

            else:

                try:

                    with st.spinner(
                        "AI is analyzing the photo..."
                    ):

                        st.session_state.ai = analyze_photo(
                            photo.getvalue(),
                            photo.type,
                            api_key,
                            note
                        )

                except Exception as error:

                    st.error(
                        f"Photo analysis failed: {error}"
                    )


# ============================================================
# AI RESULT
# ============================================================

ai = st.session_state.ai


if ai is not None:

    recommendation = ai.get(
        "recommended_mode",
        {}
    )

    st.info(
        f"AI Recommendation: "
        f"**{recommendation.get('value', 'unclear')}**"
        f" | Confidence: "
        f"{recommendation.get('confidence', '-')}"
    )

    if recommendation.get(
        "reason"
    ):

        st.write(
            f"**Reason:** "
            f"{recommendation.get('reason')}"
        )


    with st.expander(
        "View AI Photo Analysis"
    ):

        site_type = ai.get(
            "site_type",
            {}
        ).get(
            "value",
            "-"
        )

        road_type = ai.get(
            "road_type",
            {}
        ).get(
            "value",
            "-"
        )

        photo_quality = ai.get(
            "photo_quality",
            "-"
        )

        surface_condition = ai.get(
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


        if ai.get(
            "defects"
        ):

            st.dataframe(
                pd.DataFrame(
                    ai["defects"]
                ),
                hide_index=True,
                use_container_width=True
            )


        if ai.get(
            "limitations"
        ):

            st.write(
                f"**Limitations:** "
                f"{ai.get('limitations')}"
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
        "The assistant can explain repair versus new "
        "construction and Concrete versus Bitumen."
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

        if not api_key:

            st.error(
                "Please enter your Gemini API key."
            )

        else:

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
                    ai,
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
            "Your current ssr_loader.py must convert "
            "the uploaded SSR into the same DataFrame "
            "structure used by the existing estimator."
        )

        st.stop()


    # --------------------------------------------------------
    # CHAPTERS
    # --------------------------------------------------------

    all_chapters = list(
        df["chapter"].dropna().unique()
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


    ai_mode = (

        ai.get(
            "recommended_mode",
            {}
        ).get(
            "value"
        )

        if ai

        else None

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
        horizontal=True
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
    # SSR ITEM SEARCH
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
            "Example: excavation, concrete, bitumen, pothole"
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


    # --------------------------------------------------------
    # SHOW ITEMS
    # --------------------------------------------------------

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

        if column not in found_items.columns

    ]


    if missing_columns:

        st.error(
            "Required SSR columns are missing:"
        )

        st.write(
            missing_columns
        )

        st.stop()


    item_view = found_items[
        required_columns
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


            edited_estimate[
                "Amount"
            ] = (

                edited_estimate[
                    "Quantity"
                ]

                * edited_estimate[
                    "Rate"
                ]

            )


            final_estimate = edited_estimate[
                ~edited_estimate["Remove"]
            ].copy()


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


            # ------------------------------------------------
            # TOTALS
            # ------------------------------------------------

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
