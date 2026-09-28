import os

import pandas as pd
import streamlit as st

from ai_module import analyze_photo, chat_reply
from ssr_loader import load_ssr, match_chapters, search

st.set_page_config(page_title="Road Estimator (AI-assisted)", layout="wide")
st.title("Road Estimator: AI suggests, you decide")

# SSR chapter groups (names as in the SSR; spelling variants are matched automatically)
COMMON_NEW = ["Road Survey and DPR", "Road Surevy", "Excavation", "Road Sub grade",
              "Road Sub Base and Base Course", "Cross Drainage Works", "Road Miscellaneous items",
              "Road Furniture", "Road Safety", "Geosynthetic"]
CC_EXTRA = ["Rigid Pavement", "Rigid Pavement (New item)", "Expansion Joint"]
BT_EXTRA = ["Road Surfacing Course", "Road work", "Road works", "Road"]
REPAIR = ["Road Maintenance", "Bitumen and concrete road Pot Hole Reparing", "Road Miscellaneous items",
          "Road Furniture", "Road Safety", "Cross Drainage Works"]

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Setup")
    api_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    api_key = st.text_input("Gemini API key", value=api_key, type="password")
    ssr_file = st.file_uploader("SSR Excel file", type=["xlsx"])
    st.caption("Free key: aistudio.google.com. Confidential photos free key par mat bhejo.")


@st.cache_data(show_spinner="SSR load ho raha hai...")
def get_ssr(file):
    return load_ssr(file)


for k, v in {"ai": None, "photo": None, "photo_mime": "image/jpeg", "selected": {}, "chat": []}.items():
    st.session_state.setdefault(k, v)

# ---------- Photo (shared by both tabs) ----------
st.subheader("Site photo")
st.caption("Kahin ki bhi photo: purani road, kharab road, kaccha rasta ya khali zameen jahan road banana hai.")
photo = st.file_uploader("Upload photo", type=["jpg", "jpeg", "png", "webp"])
note = st.text_input("Kya karna hai? (optional)", placeholder="e.g. mujhe yahan road banana hai / potholes bhar dene hain")
if photo:
    st.session_state.photo, st.session_state.photo_mime = photo.getvalue(), photo.type
    c1, c2 = st.columns([1, 2])
    c1.image(photo, width=300)
    if c2.button("AI se photo padhwao"):
        if not api_key:
            st.error("API key daalo.")
        else:
            try:
                with st.spinner("AI dekh raha hai..."):
                    st.session_state.ai = analyze_photo(photo.getvalue(), photo.type, api_key, note)
            except Exception as e:
                st.error(f"AI call fail hua: {e}")

ai = st.session_state.ai
if ai:
    rec = ai.get("recommended_mode", {})
    st.info(f"AI ka suggestion: **{rec.get('value', 'unclear')}** ({rec.get('confidence', '-')}). "
            f"{rec.get('reason', '')}  Final faisla aapka.")
    with st.expander("AI ne photo me kya dekha"):
        st.markdown(f"**Site:** {ai.get('site_type', {}).get('value', '-')} | "
                    f"**Road type:** {ai.get('road_type', {}).get('value', '-')} | "
                    f"**Photo quality:** {ai.get('photo_quality', '-')}")
        st.markdown(f"**Surface:** {ai.get('surface_condition', '-')}")
        if ai.get("defects"):
            st.dataframe(pd.DataFrame(ai["defects"]), hide_index=True, use_container_width=True)
        if ai.get("new_road_notes"):
            st.json(ai["new_road_notes"])
        for p in ai.get("suggested_parameters", []):
            st.markdown(f"- Measure: {p.get('name')} ({p.get('why_needed', '')})")
        st.caption(f"Limitations: {ai.get('limitations', '-')}")

tab_est, tab_chat = st.tabs(["Estimate", "Chat assistant"])

# ================= CHAT TAB (separate feature) =================
with tab_chat:
    st.caption("Chatbot ki tarah baat karo. AI suggest karega, decision aapka. Rates sirf Estimate tab me SSR se aate hain.")
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    if st.button("Chat clear karo"):
        st.session_state.chat = []
        st.rerun()
    msg = st.chat_input("Apna sawal ya kaam likho...")
    if msg:
        if not api_key:
            st.error("API key daalo.")
        else:
            st.session_state.chat.append({"role": "user", "content": msg})
            try:
                reply = chat_reply(st.session_state.chat, api_key, ai,
                                   st.session_state.photo, st.session_state.photo_mime)
                st.session_state.chat.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.session_state.chat.pop()
                st.error(f"Chat fail hua: {e}")
            st.rerun()

# ================= ESTIMATE TAB =================
with tab_est:
    if not ssr_file:
        st.warning("Sidebar me SSR Excel upload karo.")
        st.stop()
    df = get_ssr(ssr_file)
    all_chapters = list(df["chapter"].unique())

    st.subheader("1. Kaam ka type (aap chuno)")
    modes = ["Repair (existing road)", "New road construction"]
    default_i = 1 if ai and ai.get("recommended_mode", {}).get("value") == "new_construction" else 0
    mode = st.radio("Mode", modes, index=default_i, horizontal=True,
                    help="AI ka suggestion default me select hota hai, aap badal sakte ho.")
    road_kind = None
    if mode == modes[1]:
        road_kind = st.radio("Road ka type", ["Concrete (CC) road", "Dambar (bitumen) road"], horizontal=True)
        wanted = COMMON_NEW + (CC_EXTRA if road_kind.startswith("Concrete") else BT_EXTRA)
    else:
        wanted = REPAIR
    preset = match_chapters(all_chapters, wanted)

    st.subheader("2. Measurements (aap daalo)")
    m1, m2, m3, m4 = st.columns(4)
    length = m1.number_input("Length (m)", min_value=0.0, value=0.0, step=1.0)
    width = m2.number_input("Width (m)", min_value=0.0, value=0.0, step=0.1)
    thick_mm = m3.number_input("Thickness (mm)", min_value=0.0, value=0.0, step=5.0)
    gst = m4.number_input("GST %", min_value=0.0, value=18.0, step=1.0,
                          help="SSR rates GST ke bina hain. Apne project ke hisaab se set karo.")

    st.subheader("3. SSR items chuno")
    default_kw = []
    if ai and ai.get("suggested_works"):
        sugg = ai["suggested_works"]
        labels = [f"{s.get('work')} ({s.get('confidence', '-')})" for s in sugg]
        pick = st.selectbox("AI ka suggested work (keywords ke liye)", ["(none)"] + labels)
        if pick != "(none)":
            s = sugg[labels.index(pick)]
            st.caption(f"Reason: {s.get('reason', '')}")
            default_kw = s.get("search_keywords", [])
    chapters = st.multiselect("Chapter (mode ke hisaab se pre-selected, badal sakte ho)",
                              sorted(all_chapters), default=preset, key=f"chap_{mode}_{road_kind}")
    kw_text = st.text_input("Keywords (comma separated)", value=", ".join(default_kw))
    kws = [k for k in kw_text.split(",") if k.strip()]

    found = search(df, chapters, kws)
    st.caption(f"{len(found)} items mile")
    view = found[["id", "item_no", "chapter", "description", "unit", "rate"]].copy()
    view.insert(0, "add", False)
    edited = st.data_editor(view, hide_index=True, use_container_width=True, height=300,
                            disabled=["id", "item_no", "chapter", "description", "unit", "rate"],
                            column_config={"id": None}, key="picker")
    if st.button("Selected items estimate me jodo"):
        for i in edited[edited["add"]]["id"]:
            st.session_state.selected.setdefault(int(i), 0.0)

    st.subheader("4. Estimate")

    def default_qty(kind):
        return {"area": length * width, "volume": length * width * thick_mm / 1000,
                "length": length, "km": length / 1000}.get(kind, 0.0)

    if not st.session_state.selected:
        st.write("Abhi koi item nahi chuna.")
    else:
        rows = []
        for i, q in st.session_state.selected.items():
            r = df.loc[i]
            rows.append({"remove": False, "item_no": r["item_no"], "description": r["description"][:120],
                         "unit": r["unit"], "rate": r["rate"],
                         "qty": q if q else round(default_qty(r["kind"]), 3)})
        est = st.data_editor(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                             disabled=["item_no", "description", "unit", "rate"], key="est")
        est["amount"] = est["qty"] * est["rate"]
        keep = est[~est["remove"]].drop(columns=["remove"])
        sub = keep["amount"].sum()
        a, b, c = st.columns(3)
        a.metric("Subtotal (excl. GST)", f"Rs {sub:,.0f}")
        b.metric(f"GST {gst:.0f}%", f"Rs {sub * gst / 100:,.0f}")
        c.metric("Total", f"Rs {sub * (1 + gst / 100):,.0f}")
        st.download_button("Estimate CSV download", keep.to_csv(index=False), "estimate.csv", "text/csv")
        if st.button("Selection clear karo"):
            st.session_state.selected = {}
            st.rerun()
        st.caption("Qty default length x width (x thickness) se aati hai, edit kar sakte ho. "
                   "Lead, area-wise percentage (corporation etc.) aur General Notes alag se check karo.")
