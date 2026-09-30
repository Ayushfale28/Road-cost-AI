import os
from collections import Counter

import pandas as pd
import streamlit as st

from ai_module import (
    ai_is_configured,
    analyze_photos,
    chat_reply,
    select_ssr_items,
)
from quantity_engine import ProjectMeasurements, calculate_quantity, quantity_note
from ssr_loader import load_ssr, match_chapters, search, ssr_health_summary
from ssr_selector import candidates_to_ai_payload, find_candidates

st.set_page_config(page_title="Road Estimator - AI Assisted", layout="wide")
st.title("Road Estimator - AI Assisted Estimation")


# ============================================================
# SSR CHAPTER GROUPS
# ============================================================

COMMON_NEW = [
    "Road Survey and DPR", "Excavation", "Road Sub grade",
    "Road Sub Base and Base Course", "Cross Drainage Works",
    "Road Miscellaneous items", "Road Furniture", "Road Safety", "Geosynthetic",
]
CC_EXTRA = ["Rigid Pavement", "Expansion Joint"]
BT_EXTRA = ["Road Surfacing Course"]
REPAIR = [
    "Road Maintenance", "Bitumen and concrete road Pot Hole Reparing",
    "Road Miscellaneous items", "Road Furniture", "Road Safety", "Cross Drainage Works",
]

DEFAULT_SSR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SSR_2022-23 (2).xlsx")

REQUIRED_COLUMNS = ["id", "item_no", "chapter", "description", "unit", "rate", "kind"]


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "ai": None,
    "ai_results": [],
    "photos": [],
    "photo": None,
    "photo_mime": "image/jpeg",
    "selected": {},          # item id -> quantity
    "chat": [],
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = list(value) if isinstance(value, list) else \
            (dict(value) if isinstance(value, dict) else value)


# ============================================================
# SMALL HELPERS
# ============================================================

def safe_float(value, default=0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except Exception:
        return default


def ai_value(field, default="-"):
    """
    Read a field from an AI result that may be either {"value": "...", ...}
    or a plain string (or missing). This one helper is used everywhere the
    AI result is displayed, so a schema difference never leaks a raw
    Python dict onto the screen.
    """
    if isinstance(field, dict):
        return field.get("value", default)
    if field is None:
        return default
    return field


def ai_confidence(field, default="-"):
    if isinstance(field, dict):
        return field.get("confidence", default)
    return default


def ai_text(field, default="-"):
    """Like ai_value, but always returns a plain string (for free-text fields
    such as photo_quality, which some prompt versions return as a dict with
    a 'reason', and others may return as a plain string)."""
    if isinstance(field, dict):
        value = field.get("value", "")
        reason = field.get("reason", "")
        return f"{value} - {reason}" if reason else (value or default)
    if field is None:
        return default
    return str(field)


def combine_ai_results(results: list) -> dict | None:
    """
    Merge multiple photo-analysis results into one project-level summary:
    majority vote for mode/road type/site type, and the union of defects,
    suggested works and suggested parameters (deduplicated).
    """
    valid = [r.get("result", {}) for r in results if isinstance(r.get("result"), dict)]
    if not valid:
        return None

    def majority(values):
        values = [v for v in values if v]
        return Counter(values).most_common(1)[0][0] if values else "unclear"

    modes = [ai_value(r.get("recommended_mode")) for r in valid]
    modes = [m for m in modes if m in ("repair", "new_construction")]
    road_types = [ai_value(r.get("road_type")) for r in valid]
    site_types = [ai_value(r.get("site_type")) for r in valid]

    def dedupe(items, key_fn):
        seen, out = set(), []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = key_fn(item)
            if key and key not in seen:
                seen.add(key)
                out.append(item)
        return out

    defects = dedupe(
        [d for r in valid for d in (r.get("defects") or [])],
        lambda d: str(d.get("type", "")).lower(),
    )
    works = dedupe(
        [w for r in valid for w in (r.get("suggested_works") or [])],
        lambda w: str(w.get("work", "")).lower(),
    )
    parameters = dedupe(
        [p for r in valid for p in (r.get("suggested_parameters") or [])],
        lambda p: str(p.get("name", "")).lower(),
    )

    return {
        "photo_quality": {"value": "combined", "reason": f"from {len(valid)} photo(s)"},
        "site_type": {"value": majority(site_types), "confidence": "medium"},
        "recommended_mode": {
            "value": majority(modes) if modes else "unclear",
            "confidence": "medium",
            "reason": "Combined recommendation from all uploaded photographs.",
        },
        "road_type": {"value": majority(road_types), "confidence": "medium"},
        "surface_condition": " ".join(
            str(r.get("surface_condition", "")) for r in valid if r.get("surface_condition")
        ),
        "defects": defects,
        "suggested_works": works,
        "suggested_parameters": parameters,
        "limitations": "Photo analysis is visual guidance only. Final engineering "
                       "measurements and site decisions must be verified.",
    }


def normalize_ssr_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("SSR is missing required columns: " + ", ".join(missing))
    df["rate"] = pd.to_numeric(df["rate"], errors="coerce").fillna(0.0)
    df = df.set_index("id", drop=False)
    return df


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Project Setup")
    st.caption("AI features are configured automatically by the application.")
    if not ai_is_configured():
        st.info("AI analysis is currently unavailable. You can still build an "
                "estimate manually using SSR search below.")

    st.subheader("SSR Source")
    st.caption("Upload an SSR (Excel or CSV) if you want to use a different "
               "schedule. Otherwise the default SSR is used.")
    # Only formats the loader can actually read are offered here -- PDF/DOCX/
    # TXT are not accepted because there is no real parser for them yet, and
    # advertising a format that silently fails is worse than not offering it.
    ssr_file = st.file_uploader("Upload SSR", type=["xlsx", "xls", "csv"])

    if ssr_file is not None:
        st.success(f"Using uploaded SSR: {ssr_file.name}")
    else:
        st.info("Default SSR will be used.")


@st.cache_data(show_spinner="Loading SSR...")
def get_ssr(file_source):
    return normalize_ssr_dataframe(load_ssr(file_source))


def load_selected_ssr():
    if ssr_file is not None:
        try:
            return get_ssr(ssr_file)
        except Exception as error:
            st.error("The uploaded SSR could not be read.")
            st.caption(str(error))
            st.stop()

    if not os.path.exists(DEFAULT_SSR_FILE):
        st.error("Default SSR file was not found.")
        st.warning("Place the default SSR file beside app.py, or upload an SSR file.")
        st.stop()

    try:
        return get_ssr(DEFAULT_SSR_FILE)
    except Exception as error:
        st.error("The default SSR could not be loaded.")
        st.caption(str(error))
        st.stop()


# ============================================================
# 1. SITE PHOTOS
# ============================================================

st.subheader("1. Site Photos")
st.caption("Upload one or more photos of the road/site -- an existing road, "
           "a damaged road, a kaccha track, or open land where a road is planned.")

photos = st.file_uploader(
    "Upload Road Photos", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
)
note = st.text_input(
    "Additional information (optional)",
    placeholder="Example: New 2 km concrete road is required.",
)

if photos:
    st.session_state.photos = [
        {"name": p.name, "bytes": p.getvalue(), "mime": p.type} for p in photos
    ]
    st.session_state.photo = st.session_state.photos[0]["bytes"]
    st.session_state.photo_mime = st.session_state.photos[0]["mime"]

    st.write(f"**{len(photos)} photo(s) uploaded.**")
    columns = st.columns(min(len(photos), 4))
    for index, p in enumerate(photos):
        with columns[index % len(columns)]:
            st.image(p, caption=p.name, use_container_width=True)

    if st.button("Analyze Site", type="primary", disabled=not ai_is_configured()):
        with st.spinner("Analyzing photo(s)..."):
            st.session_state.ai_results = analyze_photos(st.session_state.photos, note)
        st.session_state.ai = combine_ai_results(st.session_state.ai_results)
        st.session_state.selected = {}  # a new site analysis starts a fresh estimate
        st.success("Site analysis completed.")

if st.session_state.ai_results:
    st.subheader("Photo Analysis Results")
    for index, entry in enumerate(st.session_state.ai_results):
        result = entry["result"]
        with st.expander(f"Photo {index + 1}: {entry['name']}", expanded=(index == 0)):
            recommendation = result.get("recommended_mode", {})
            st.info(f"**Suggested Work:** {ai_value(recommendation)}  \n"
                    f"**Confidence:** {ai_confidence(recommendation)}")
            reason = recommendation.get("reason", "") if isinstance(recommendation, dict) else ""
            if reason:
                st.write(f"**Reason:** {reason}")

            st.write(f"**Site Type:** {ai_value(result.get('site_type'))}")
            st.write(f"**Road Type:** {ai_value(result.get('road_type'))}")
            st.write(f"**Photo Quality:** {ai_text(result.get('photo_quality'))}")
            st.write(f"**Surface Condition:** {result.get('surface_condition', '-')}")

            defects = result.get("defects") or []
            if defects:
                st.markdown("**Detected Defects:**")
                st.dataframe(pd.DataFrame(defects), hide_index=True, use_container_width=True)

            works = result.get("suggested_works") or []
            if works:
                st.markdown("**Suggested Works:**")
                for w in works:
                    if isinstance(w, dict):
                        st.write(f"- {w.get('work', '')}")

            limitations = result.get("limitations")
            if limitations:
                st.caption(f"Limitations: {limitations}")

ai = st.session_state.ai
if ai:
    st.subheader("Combined Site Assessment")
    c1, c2 = st.columns(2)
    c1.metric("Suggested Work", str(ai_value(ai.get("recommended_mode"))))
    c2.metric("Detected Road Type", str(ai_value(ai.get("road_type"))))


# ============================================================
# TABS
# ============================================================

estimate_tab, chat_tab = st.tabs(["Estimate", "Chat Assistant"])


# ============================================================
# CHAT TAB
# ============================================================

with chat_tab:
    st.subheader("Road Project Chat Assistant")
    st.caption("Ask questions about your road project. The assistant does not "
               "invent measurements, SSR items or rates.")

    for message in st.session_state.chat:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if st.button("Clear Chat"):
        st.session_state.chat = []
        st.rerun()

    user_message = st.chat_input(
        "Ask a question..." if ai_is_configured() else "AI chat is currently unavailable.",
        disabled=not ai_is_configured(),
    )
    if user_message:
        st.session_state.chat.append({"role": "user", "content": user_message})
        response = chat_reply(
            st.session_state.chat, st.session_state.ai,
            st.session_state.photo, st.session_state.photo_mime,
        )
        st.session_state.chat.append({"role": "assistant", "content": response})
        st.rerun()


# ============================================================
# ESTIMATE TAB
# ============================================================

with estimate_tab:
    df = load_selected_ssr()

    with st.expander("SSR file summary", expanded=False):
        st.json(ssr_health_summary(df))

    all_chapters = sorted(c for c in df["chapter"].unique() if c)

    # -------------------- Work type --------------------
    st.subheader("2. Select Work Type")
    modes = ["Repair (Existing Road)", "New Road Construction"]
    ai_mode = ai_value(ai.get("recommended_mode"), None) if ai else None
    default_index = 1 if ai_mode == "new_construction" else 0

    mode = st.radio(
        "Work Type", modes, index=default_index, horizontal=True,
        help="The photo analysis is only a suggestion. Confirm the correct work type yourself.",
    )

    road_kind = None
    if mode == "New Road Construction":
        st.subheader("3. Select Road Type")
        road_kind = st.radio("Road Type", ["Concrete (CC)", "Bitumen / Dambar"], horizontal=True)
        wanted_chapters = COMMON_NEW + (CC_EXTRA if road_kind == "Concrete (CC)" else BT_EXTRA)
    else:
        wanted_chapters = REPAIR

    preset_chapters = match_chapters(all_chapters, wanted_chapters)

    # -------------------- Measurements --------------------
    st.subheader("4. Project Measurements")
    m1, m2, m3, m4 = st.columns(4)
    length = m1.number_input("Length (m)", min_value=0.0, value=0.0, step=1.0)
    width = m2.number_input("Width (m)", min_value=0.0, value=0.0, step=0.1)
    thickness = m3.number_input("Thickness (mm)", min_value=0.0, value=0.0, step=5.0)
    gst = m4.number_input("GST (%)", min_value=0.0, value=18.0, step=1.0)

    # These extra fields only matter for repair-type work, so they are
    # shown only in that mode rather than always cluttering the form.
    pothole_count = pothole_len = pothole_wid = pothole_depth = 0.0
    drainage_length = 0.0
    if mode == "Repair (Existing Road)":
        st.markdown("**Pothole details (optional -- fill in if potholes are being repaired)**")
        p1, p2, p3, p4 = st.columns(4)
        pothole_count = p1.number_input("Number of potholes", min_value=0, value=0, step=1)
        pothole_len = p2.number_input("Avg. pothole length (m)", min_value=0.0, value=0.0, step=0.1)
        pothole_wid = p3.number_input("Avg. pothole width (m)", min_value=0.0, value=0.0, step=0.1)
        pothole_depth = p4.number_input("Avg. pothole depth (m)", min_value=0.0, value=0.0, step=0.01)

    drainage_length = st.number_input(
        "Drain / kerb length (m) -- optional", min_value=0.0, value=0.0, step=1.0,
    )

    with st.expander("Additional project context (optional, informational only)"):
        lead_distance = st.number_input("Lead distance for materials (km)", min_value=0.0, value=0.0, step=1.0)
        traffic_type = st.selectbox("Traffic type", ["", "Light", "Medium", "Heavy"])
        soil_condition = st.text_input("Soil / sub-grade condition")

    measurements = ProjectMeasurements(
        length_m=length, width_m=width, thickness_mm=thickness,
        pothole_count=int(pothole_count), pothole_avg_length_m=pothole_len,
        pothole_avg_width_m=pothole_wid, pothole_avg_depth_m=pothole_depth,
        drain_length_m=drainage_length, lead_distance_km=lead_distance,
        traffic_type=traffic_type, soil_condition=soil_condition,
    )

    # -------------------- Automatic estimation --------------------
    st.subheader("5. Automatic SSR Estimation")
    st.caption("The system searches the real SSR file for relevant items, then "
               "(if AI is available) asks it to pick the relevant subset. The "
               "AI can only choose from items that genuinely exist in the SSR.")

    can_generate = length > 0 and width > 0 and (mode == "Repair (Existing Road)" or road_kind)

    if not can_generate:
        st.info("Enter at least length and width to generate the automatic estimate.")

    if st.button("Generate SSR Estimate", type="primary", disabled=not can_generate):
        with st.spinner("Finding relevant SSR items..."):
            candidates = find_candidates(
                df, mode, road_kind, ai_analysis=ai,
                allowed_chapters=preset_chapters, max_per_category=3, max_total=40,
            )

        if candidates.empty:
            st.warning("No matching SSR items could be automatically identified. "
                       "Use the manual SSR search below.")
        else:
            selected_ids = list(candidates["id"])
            selection_reasons = {}

            if ai_is_configured():
                try:
                    spec = {
                        "mode": mode, "road_type": road_kind,
                        "length_m": length, "width_m": width, "thickness_mm": thickness,
                    }
                    payload = candidates_to_ai_payload(candidates)
                    ai_pick = select_ssr_items(spec, payload)
                    if ai_pick["selected_ids"]:
                        selected_ids = ai_pick["selected_ids"]
                        selection_reasons = ai_pick["reasons"]
                except Exception:
                    # AI refinement failed -- fall back to the top keyword
                    # candidates found above, so the feature still works.
                    pass

            st.session_state.selected = {}
            for item_id in selected_ids:
                row = df.loc[item_id]
                qty = calculate_quantity(row["kind"], row["description"], row["chapter"], measurements)
                st.session_state.selected[int(item_id)] = qty

            st.success(f"{len(selected_ids)} SSR item(s) were proposed. Review them below "
                       f"-- items showing 0 quantity need a manual value.")

    # -------------------- Manual SSR search (always available) --------------------
    st.subheader("6. Add Additional SSR Items Manually")
    chapters = st.multiselect(
        "SSR Chapters", all_chapters, default=preset_chapters,
        key=f"manual_chapters_{mode}_{road_kind}",  # changes when mode/road type changes
    )
    keywords_text = st.text_input(
        "Search SSR items", placeholder="Example: excavation, concrete, bitumen, pothole, drain",
    )
    keywords = [w.strip() for w in keywords_text.split(",") if w.strip()]

    found_items = search(df, chapters, keywords)
    st.caption(f"{len(found_items)} SSR item(s) found.")

    if not found_items.empty:
        item_view = found_items[["id", "item_no", "chapter", "description", "unit", "rate"]].copy()
        item_view.insert(0, "Add", False)
        edited = st.data_editor(
            item_view, hide_index=True, use_container_width=True, height=300,
            disabled=["id", "item_no", "chapter", "description", "unit", "rate"],
            column_config={"id": None}, key="manual_ssr_picker",
        )
        if st.button("Add Selected SSR Items"):
            added = 0
            for item_id in edited[edited["Add"]]["id"]:
                item_id = int(item_id)
                if item_id not in st.session_state.selected:
                    row = df.loc[item_id]
                    qty = calculate_quantity(row["kind"], row["description"], row["chapter"], measurements)
                    st.session_state.selected[item_id] = qty
                    added += 1
            st.success(f"{added} item(s) added." if added else "No new items were added.")

    # -------------------- Cost estimate --------------------
    st.subheader("7. Cost Estimate")

    if not st.session_state.selected:
        st.info("No SSR items are currently in the estimate.")
    else:
        rows = []
        for item_id, qty in st.session_state.selected.items():
            if item_id not in df.index:
                continue
            row = df.loc[item_id]
            rate = safe_float(row["rate"])
            qty = safe_float(qty)
            rows.append({
                "Remove": False, "ID": int(item_id), "Item No": row["item_no"],
                "Chapter": row["chapter"], "Description": row["description"],
                "Unit": row["unit"], "Rate": rate, "Quantity": qty,
                "Amount": qty * rate, "Note": quantity_note(row["kind"], qty),
            })

        estimate_df = pd.DataFrame(rows)
        edited_estimate = st.data_editor(
            estimate_df, hide_index=True, use_container_width=True, height=450,
            disabled=["ID", "Item No", "Chapter", "Description", "Unit", "Rate", "Amount", "Note"],
            column_config={
                "ID": None,
                "Quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, step=0.001),
                "Rate": st.column_config.NumberColumn("Rate", format="%.2f"),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            },
            key="final_estimate_editor",
        )

        for _, r in edited_estimate.iterrows():
            item_id = int(r["ID"])
            if bool(r["Remove"]):
                st.session_state.selected.pop(item_id, None)
            else:
                st.session_state.selected[item_id] = safe_float(r["Quantity"])

        final_rows = []
        for item_id, qty in st.session_state.selected.items():
            if item_id not in df.index:
                continue
            row = df.loc[item_id]
            rate = safe_float(row["rate"])
            final_rows.append({
                "Item No": row["item_no"], "Chapter": row["chapter"],
                "Description": row["description"], "Unit": row["unit"],
                "Rate": rate, "Quantity": qty, "Amount": qty * rate,
            })

        if final_rows:
            final_df = pd.DataFrame(final_rows)
            subtotal = final_df["Amount"].sum()
            gst_amount = subtotal * gst / 100
            total = subtotal + gst_amount

            c1, c2, c3 = st.columns(3)
            c1.metric("Subtotal", f"Rs {subtotal:,.2f}")
            c2.metric(f"GST ({gst:.0f}%)", f"Rs {gst_amount:,.2f}")
            c3.metric("Total Estimate", f"Rs {total:,.2f}")

            download_df = final_df.copy()
            download_df["GST Amount"] = download_df["Amount"] * gst / 100
            download_df["Amount Including GST"] = download_df["Amount"] + download_df["GST Amount"]
            st.download_button(
                "Download Estimate CSV", download_df.to_csv(index=False),
                file_name="road_estimate.csv", mime="text/csv",
            )

    if st.button("Clear Estimate"):
        st.session_state.selected = {}
        st.rerun()


st.divider()
st.caption("Road Cost Estimator | AI-assisted road analysis and SSR-based estimation")
