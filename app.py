"""
app.py — Hisaab AI (حساب) Frontend
Enterprise-Grade AI Bookkeeper for Pakistani Retailers & Kiryana Stores.

Features:
- Tab 1: 📷 Smart Scan (Multimodal OCR & Document Verification)
- Tab 2: 🎙️ Voice Khata (Groq Whisper-large-v3 Speech-to-Text & Gemini)
- Tab 3: 📒 Ledger (Search, Filtering, Excel/CSV Export, Quick Add, Batch Delete)
- Tab 4: 👥 Udhaar (Customer Khata Balances, WhatsApp AI Reminders, Ledger History)
- Tab 5: 📊 Dashboard (Bill Due Alerts, Plotly Charts, Financial Q&A with Gemini 3.8 Flash)
"""

import os
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import dotenv
import pandas as pd
import plotly.express as px
import streamlit as st

from db import (
    ALLOWED_TYPES,
    FIXED_CATEGORIES,
    add_transactions,
    delete_transactions,
    find_duplicates,
    get_all_transactions,
    get_customer_balances,
    get_customer_phone,
    get_unpaid_bills,
    init_db,
    mark_paid,
    reset_db,
    seed_demo_data,
    set_customer_phone,
)
from core import (
    ExtractionResult,
    ask_ledger,
    clean_model_name,
    draft_reminder,
    extract_from_image,
    extract_from_text,
    normalize_entry,
    resolve_model_name,
    transcribe_audio,
    whatsapp_link,
)

# Load environment configuration
dotenv.load_dotenv()

# Page Configuration
st.set_page_config(
    page_title="Hisaab AI — Kiryana Ledger",
    page_icon="📒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Database once
@st.cache_resource
def setup_database():
    init_db()
    return True

setup_database()

# Session State Initialization
if "pending_docs" not in st.session_state:
    st.session_state.pending_docs = []
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "drafted_reminders" not in st.session_state:
    st.session_state.drafted_reminders = {}
if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = ""

# Demo cache directory
CACHE_DIR = Path(__file__).parent / "demo_cache"
CACHE_DIR.mkdir(exist_ok=True)

# ==============================================================================
# PROFESSIONAL FINTECH DESIGN SYSTEM (CSS)
# ==============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Noto+Nastaliq+Urdu:wght@400;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Top App Header Banner */
    .hisaab-banner {
        background: linear-gradient(135deg, #064E3B 0%, #047857 50%, #059669 100%);
        border-radius: 12px;
        padding: 20px 24px;
        color: #FFFFFF;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(4, 120, 87, 0.15);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }
    .hisaab-title {
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin: 0;
        color: #FFFFFF;
    }
    .hisaab-subtitle {
        font-size: 0.92rem;
        color: #A7F3D0;
        margin-top: 4px;
    }
    .hisaab-status-pill {
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.25);
        padding: 6px 14px;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }

    /* Card Containers */
    .hisaab-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        margin-bottom: 16px;
    }
    .hisaab-card:hover {
        box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.08);
    }

    /* KPI Metric Cards */
    .kpi-container {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 4px rgba(15, 23, 42, 0.03);
        border-top: 4px solid #059669;
    }
    .kpi-label {
        color: #64748B;
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .kpi-value {
        color: #0F172A;
        font-size: 1.55rem;
        font-weight: 800;
        letter-spacing: -0.5px;
    }

    /* Transaction Type Badges */
    .badge-udhaar {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .badge-jama {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .badge-expense {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .badge-cash {
        background-color: #DBEAFE;
        color: #1E40AF;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #F1F5F9;
        padding: 6px;
        border-radius: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 18px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.95rem;
        color: #475569;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #047857 !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
    }

    /* Responsive Mobile Adjustments */
    @media (max-width: 768px) {
        .hisaab-banner {
            flex-direction: column;
            align-items: flex-start;
        }
        .kpi-value {
            font-size: 1.3rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# SIDEBAR: Configuration & Offline Mode
# ==============================================================================
with st.sidebar:
    st.markdown("### 📒 **Hisaab AI**")
    st.caption("AI-Powered Bookkeeper for Pakistani Kiryana Stores.")
    st.divider()

    st.subheader("⚙️ Settings")
    default_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    raw_model_input = st.text_input(
        "Gemini Model",
        value=default_model,
        help="Default: gemini-3.8-flash (Model actually used will match this field).",
    )
    model_name = clean_model_name(raw_model_input)

    env_gemini_key = os.getenv("GEMINI_API_KEY", "")
    api_key = st.text_input(
        "Gemini API Key",
        value=env_gemini_key,
        type="password",
        help="Paste your Google AI Studio API key.",
    )
    if not api_key:
        st.info("💡 Need a free key? Get one at [Google AI Studio](https://aistudio.google.com/).")

    env_groq_key = os.getenv("GROQ_API_KEY", "")
    groq_key = st.text_input(
        "Groq API Key (Voice)",
        value=env_groq_key,
        type="password",
        help="Optional: Free key from console.groq.com for Whisper speech-to-text.",
    )

    shop_name = st.text_input("Shop Name", value="Madina General Store")

    show_voice_tab = st.checkbox(
        "Show Voice Khata tab",
        value=True,
        help="Toggle to show/hide the Voice Khata tab during demo.",
    )

    st.divider()
    st.subheader("🧪 Demo Utilities")

    # Load Demo Ledger button
    if st.button("📥 Load Demo Ledger", type="secondary"):
        count = seed_demo_data()
        st.toast(f"Demo ledger seeded with {count} realistic transactions!", icon="✅")
        st.rerun()

    # Offline demo mode toggle
    offline_mode = st.toggle("Offline demo mode (use saved results)", value=False)
    if offline_mode:
        st.caption("📂 Offline mode active: extractions will load pre-cached results from `demo_cache/`.")

    # Reset ledger expander
    with st.expander("⚠️ Reset Database"):
        confirm_reset = st.checkbox("I understand this deletes everything")
        if st.button("Reset Ledger", type="primary", disabled=not confirm_reset):
            reset_db()
            st.toast("Database has been completely cleared.", icon="🗑️")
            st.rerun()

# ==============================================================================
# TOP APP HEADER BANNER
# ==============================================================================
today_str = date.today().strftime("%d %B %Y")
status_label = "⚡ Offline Demo Mode" if offline_mode else "🟢 Live AI Engine (Gemini 3.8 Flash)"

st.markdown(
    f"""
    <div class="hisaab-banner">
        <div>
            <div class="hisaab-title">📒 Hisaab AI — {shop_name}</div>
            <div class="hisaab-subtitle">Digital Khata & Automatic Bookkeeper • {today_str}</div>
        </div>
        <div class="hisaab-status-pill">
            {status_label}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# SHARED REVIEW PANEL COMPONENT (Smart Scan & Voice Khata)
# ==============================================================================
def render_review_panel(doc_idx: int, doc_item: Dict[str, Any]):
    """Renders the standard two-column review panel for extracted transactions."""
    raw_result: ExtractionResult = doc_item["result"]
    entries_list: List[Dict[str, Any]] = doc_item["entries"]
    img_bytes: Optional[bytes] = doc_item.get("img_bytes")
    filename: str = doc_item.get("filename", "Document")
    doc_type: str = doc_item.get("doc_type", "receipt")
    is_offline: bool = doc_item.get("is_offline", False)

    st.markdown(f"### 📋 Review: **{filename}**")

    if is_offline:
        st.warning("⚡ **Offline demo mode:** showing a saved result for this image.")

    col_preview, col_editor = st.columns([1, 1.4], gap="medium")

    with col_preview:
        if img_bytes:
            st.image(img_bytes, caption=f"Original: {filename}")
        else:
            st.info(f"🎙️ **Spoken Voice Transcript:**\n\n_{doc_item.get('transcript', '')}_")

    with col_editor:
        # Document Summary & Confidence
        conf_pct = int(raw_result.confidence * 100) if raw_result.confidence else 92
        st.write(f"**Detected Type:** `{doc_type}` | **Confidence:** `{conf_pct}%`")
        st.info(f"**Summary:** {raw_result.summary}")

        if doc_type == "other":
            st.warning("⚠️ **Non-financial image detected.** No business or ledger transactions were identified in this photo.")

        if not entries_list:
            st.info("ℹ️ No financial entries were found in this document.")

        # AI Warnings
        if raw_result.warnings:
            for w in raw_result.warnings:
                st.warning(f"⚠️ {w}")

        # Duplicate Check
        dups = find_duplicates(entries_list)
        if dups:
            for d in dups:
                st.warning(
                    f"⚠️ **Potential Duplicate Detected:** Found existing record for **{d['party']}** "
                    f"(Rs {d['amount']:,.0f} on {d['txn_date']})."
                )

        # Editable Data Editor
        st.markdown("**Verify / Edit Ledger Entries:**")
        df_entries = pd.DataFrame(entries_list)
        if df_entries.empty:
            df_entries = pd.DataFrame(
                columns=["txn_date", "party", "type", "amount", "category", "status", "due_date", "note"]
            )

        edited_df = st.data_editor(
            df_entries,
            key=f"editor_{doc_idx}_{filename}",
            num_rows="dynamic",
            column_config={
                "type": st.column_config.SelectboxColumn("Type", options=ALLOWED_TYPES, required=True),
                "category": st.column_config.SelectboxColumn("Category", options=FIXED_CATEGORIES, required=True),
                "status": st.column_config.SelectboxColumn("Status", options=["paid", "unpaid", "n/a"], required=True),
                "amount": st.column_config.NumberColumn("Amount (PKR)", min_value=0.0, format="Rs %.2f", required=True),
                "txn_date": st.column_config.TextColumn("Date", help="Format: YYYY-MM-DD"),
                "due_date": st.column_config.TextColumn("Due Date", help="Format: YYYY-MM-DD for bills"),
                "party": st.column_config.TextColumn("Party / Person", required=True),
                "note": st.column_config.TextColumn("Note"),
            },
        )

        # Line items expander
        if raw_result.line_items:
            with st.expander(f"📦 View Line Items ({len(raw_result.line_items)} detected)"):
                li_df = pd.DataFrame([li.model_dump() for li in raw_result.line_items])
                st.dataframe(li_df)

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("💾 Save to Ledger", key=f"save_{doc_idx}_{filename}", type="primary"):
                edited_rows = edited_df.to_dict(orient="records")
                valid_rows = []
                for r in edited_rows:
                    norm = normalize_entry(r, fallback_date=raw_result.document_date)
                    if norm:
                        valid_rows.append(norm)

                if valid_rows:
                    added_count = add_transactions(
                        valid_rows,
                        source=filename,
                        doc_type=doc_type,
                    )
                    st.toast(f"Successfully saved {added_count} entries to ledger!", icon="✅")
                else:
                    st.toast("No valid rows to save (all amounts were 0 or unreadable).", icon="⚠️")

                st.session_state.pending_docs.pop(doc_idx)
                st.rerun()

        with col_btn2:
            if st.button("🗑️ Discard", key=f"discard_{doc_idx}_{filename}", type="secondary"):
                st.session_state.pending_docs.pop(doc_idx)
                st.toast(f"Discarded {filename}.", icon="ℹ️")
                st.rerun()

    st.divider()

# ==============================================================================
# MAIN TABS INTERFACE
# ==============================================================================
tab_titles = ["📷 Smart Scan"]
if show_voice_tab:
    tab_titles.append("🎙️ Voice Khata")
tab_titles.extend(["📒 Ledger", "👥 Udhaar", "📊 Dashboard"])
tabs = st.tabs(tab_titles)

tab_scan = tabs[0]
if show_voice_tab:
    tab_voice = tabs[1]
    tab_ledger = tabs[2]
    tab_udhaar = tabs[3]
    tab_dashboard = tabs[4]
else:
    tab_voice = None
    tab_ledger = tabs[1]
    tab_udhaar = tabs[2]
    tab_dashboard = tabs[3]

# ------------------------------------------------------------------------------
# TAB 1: SMART SCAN
# ------------------------------------------------------------------------------
with tab_scan:
    st.subheader("📷 Smart Document Scanner")
    st.caption("Upload photos of receipts, wholesaler invoices, utility bills (IESCO/SNGPL/PTCL), or handwritten khata pages.")

    col_up1, col_up2 = st.columns([2, 1])
    with col_up1:
        uploaded_files = st.file_uploader(
            "Upload Document Photos (JPG, PNG, WebP)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key=f"doc_uploader_{st.session_state.uploader_key}",
        )
    with col_up2:
        with st.expander("📸 Or Use Device Camera"):
            camera_pic = st.camera_input("Take a photo of bill / receipt")
            if camera_pic is not None:
                if uploaded_files is None:
                    uploaded_files = []
                uploaded_files.append(camera_pic)

    has_files = bool(uploaded_files)
    if st.button("🚀 Extract with AI", disabled=not has_files, type="primary"):
        for f in uploaded_files:
            file_bytes = f.getvalue()
            filename = f.name
            base_name = Path(filename).stem
            cache_file = CACHE_DIR / f"{base_name}.json"

            if offline_mode:
                if cache_file.exists():
                    try:
                        raw_json = cache_file.read_text(encoding="utf-8")
                        res = ExtractionResult.model_validate_json(raw_json)
                        normalized_list = []
                        for entry in res.entries:
                            n = normalize_entry(entry, fallback_date=res.document_date)
                            if n:
                                normalized_list.append(n)
                        st.session_state.pending_docs.append({
                            "result": res,
                            "entries": normalized_list,
                            "img_bytes": file_bytes,
                            "filename": filename,
                            "doc_type": res.doc_type,
                            "is_offline": True,
                        })
                    except Exception as parse_err:
                        st.error(f"Failed parsing saved offline cache for '{filename}': {parse_err}")
                else:
                    st.error(
                        f"Offline cache not found for '{filename}'. Expected file at `demo_cache/{base_name}.json`. "
                        "Turn off offline mode or ensure the cache file exists."
                    )
            else:
                with st.spinner(f"Reading and analyzing '{filename}' with {model_name}..."):
                    try:
                        res, normalized_list = extract_from_image(
                            file_bytes,
                            api_key=api_key,
                            model_name=model_name,
                        )
                        try:
                            cache_file.write_text(res.model_dump_json(indent=2), encoding="utf-8")
                        except Exception:
                            pass

                        st.session_state.pending_docs.append({
                            "result": res,
                            "entries": normalized_list,
                            "img_bytes": file_bytes,
                            "filename": filename,
                            "doc_type": res.doc_type,
                            "is_offline": False,
                        })
                    except Exception as err:
                        st.error(f"Extraction failed for '{filename}': {err}")
                        if cache_file.exists():
                            st.info(f"A saved offline extraction is available for '{filename}'.")
                            if st.button(f"Use saved result for {filename}", key=f"use_cache_{filename}"):
                                raw_json = cache_file.read_text(encoding="utf-8")
                                res = ExtractionResult.model_validate_json(raw_json)
                                normalized_list = [
                                    normalize_entry(e, fallback_date=res.document_date) for e in res.entries
                                ]
                                normalized_list = [e for e in normalized_list if e]
                                st.session_state.pending_docs.append({
                                    "result": res,
                                    "entries": normalized_list,
                                    "img_bytes": file_bytes,
                                    "filename": filename,
                                    "doc_type": res.doc_type,
                                    "is_offline": True,
                                })
                                st.rerun()

        st.session_state.uploader_key += 1
        st.rerun()

    # Pending Review Queue
    if st.session_state.pending_docs:
        st.divider()
        st.subheader(f"📑 Scanned Documents Awaiting Review ({len(st.session_state.pending_docs)})")
        st.caption("Review extracted entries, correct any numbers, and click 'Save to Ledger'.")
        for idx, doc_item in enumerate(list(st.session_state.pending_docs)):
            render_review_panel(idx, doc_item)

# ------------------------------------------------------------------------------
# TAB 2: VOICE KHATA (PHASE 2)
# ------------------------------------------------------------------------------
if show_voice_tab and tab_voice is not None:
    with tab_voice:
        st.subheader("🎙️ Voice Khata (Audio Khata Entry)")
        st.caption("Speak transaction details in Urdu or Roman Urdu (e.g., 'Ahmed ne 500 rupay ka atta udhaar liya').")

        if offline_mode:
            st.info("💡 Note: Voice transcription requires online Groq / Whisper API. Offline mode does not apply to speech.")

        voice_audio = st.audio_input("Record a transaction voice note:")

        if voice_audio:
            audio_bytes = voice_audio.getvalue()

            col_v1, col_v2 = st.columns([1, 1])
            with col_v1:
                if st.button("🎧 Transcribe Speech (Groq Whisper)", type="primary"):
                    if not groq_key:
                        st.error(
                            "Groq API key is missing. Please enter your GROQ_API_KEY in the sidebar "
                            "(get a free key from https://console.groq.com/)."
                        )
                    else:
                        with st.spinner("Transcribing speech with Whisper-large-v3..."):
                            try:
                                transcript = transcribe_audio(audio_bytes, "voice_khata.wav", groq_key)
                                st.session_state.voice_transcript = transcript
                                st.success("Transcribed successfully!")
                            except Exception as e:
                                st.error(f"Transcription failed: {e}")

        # Editable transcript area
        if st.session_state.voice_transcript:
            st.markdown("**Transcript (Edit if needed before extracting):**")
            edited_transcript = st.text_area(
                "Spoken Transcript",
                value=st.session_state.voice_transcript,
                height=90,
                label_visibility="collapsed",
            )

            if st.button("✨ Extract Ledger Entries from Voice Note", type="primary"):
                with st.spinner("Converting spoken note into structured transactions with Gemini..."):
                    try:
                        res, norm_entries = extract_from_text(
                            edited_transcript,
                            api_key=api_key,
                            model_name=model_name,
                        )
                        st.session_state.pending_docs.append({
                            "result": res,
                            "entries": norm_entries,
                            "img_bytes": None,
                            "transcript": edited_transcript,
                            "filename": f"Voice Note ({datetime.now().strftime('%H:%M:%S')})",
                            "doc_type": "voice",
                            "is_offline": False,
                        })
                        st.session_state.voice_transcript = ""
                        st.toast("Voice transaction extracted! Review it below or in Smart Scan.", icon="✅")
                        st.rerun()
                    except Exception as e:
                        err_str = str(e)
                        if "not found" in err_str.lower():
                            st.error(
                                f"❌ Model selection error: {err_str}\n\n"
                                "Please check the 'Gemini Model' field in the sidebar (e.g. `gemini-3.8-flash`)."
                            )
                        else:
                            st.error(f"Voice extraction error: {e}")

# ------------------------------------------------------------------------------
# TAB 3: LEDGER
# ------------------------------------------------------------------------------
with tab_ledger:
    st.subheader("📒 Digital Ledger")
    df_all = get_all_transactions()

    # Quick Add Manual Entry Expander
    with st.expander("➕ Quick Add Manual Entry (No Camera / Voice Required)"):
        col_m1, col_m2, col_m3, col_m4 = st.columns([1.5, 1.2, 1.2, 1.5])
        with col_m1:
            m_party = st.text_input("Party / Customer Name:", placeholder="e.g. Ahmed Raza")
        with col_m2:
            m_type = st.selectbox("Type:", options=ALLOWED_TYPES)
        with col_m3:
            m_amount = st.number_input("Amount (PKR):", min_value=1.0, value=500.0, step=50.0)
        with col_m4:
            m_cat = st.selectbox("Category:", options=FIXED_CATEGORIES)

        col_m5, col_m6 = st.columns([2, 1])
        with col_m5:
            m_note = st.text_input("Optional Note:", placeholder="e.g. 5kg sugar")
        with col_m6:
            st.write("")
            st.write("")
            if st.button("Save Entry", type="primary"):
                if not m_party.strip():
                    st.warning("Please provide a party name.")
                else:
                    manual_row = {
                        "txn_date": date.today().isoformat(),
                        "party": m_party.strip(),
                        "type": m_type,
                        "amount": m_amount,
                        "category": m_cat,
                        "status": "unpaid" if (m_type == "expense" and "Bill" in m_cat) else "paid",
                        "due_date": None,
                        "note": m_note.strip(),
                    }
                    norm_row = normalize_entry(manual_row)
                    if norm_row:
                        add_transactions([norm_row], source="manual", doc_type="manual")
                        st.toast("Manual transaction recorded!", icon="✅")
                        st.rerun()

    if df_all.empty:
        st.info("The ledger is currently empty. Scan a receipt or click 'Load Demo Ledger' in the sidebar to populate data.")
    else:
        # Filtering Controls
        col_f1, col_f2 = st.columns([1.5, 2])
        with col_f1:
            type_filter = st.multiselect(
                "Filter by Transaction Type:",
                options=ALLOWED_TYPES,
                default=[],
                help="Leave empty to show all types.",
            )
        with col_f2:
            search_party = st.text_input("🔍 Search Party / Supplier / Customer:", value="").strip()

        filtered_df = df_all.copy()
        if type_filter:
            filtered_df = filtered_df[filtered_df["type"].isin(type_filter)]
        if search_party:
            filtered_df = filtered_df[filtered_df["party"].str.contains(search_party, case=False, na=False)]

        # Display Dataframe with formatted currency
        display_df = filtered_df.copy()
        display_df["amount_formatted"] = display_df["amount"].apply(lambda x: f"Rs {x:,.2f}")

        cols_to_show = [
            "id",
            "txn_date",
            "party",
            "type",
            "amount_formatted",
            "category",
            "status",
            "due_date",
            "note",
            "source",
            "doc_type",
        ]
        st.dataframe(
            display_df[cols_to_show],
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "txn_date": st.column_config.TextColumn("Date", width="medium"),
                "party": st.column_config.TextColumn("Party / Name", width="large"),
                "type": st.column_config.TextColumn("Type", width="medium"),
                "amount_formatted": st.column_config.TextColumn("Amount", width="medium"),
                "category": st.column_config.TextColumn("Category", width="medium"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "due_date": st.column_config.TextColumn("Due Date", width="medium"),
                "note": st.column_config.TextColumn("Note", width="large"),
                "source": st.column_config.TextColumn("Source", width="medium"),
                "doc_type": st.column_config.TextColumn("Doc Type", width="small"),
            },
        )

        st.caption(f"Showing {len(filtered_df)} of {len(df_all)} transactions.")

        # Download Exports: Excel and CSV
        col_d1, col_d2, _ = st.columns([1, 1, 2])
        with col_d1:
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                filtered_df.to_excel(writer, index=False, sheet_name="Ledger")
            excel_bytes = excel_buffer.getvalue()
            st.download_button(
                label="📥 Download Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"hisaab_ledger_{date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col_d2:
            csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download CSV",
                data=csv_bytes,
                file_name=f"hisaab_ledger_{date.today().isoformat()}.csv",
                mime="text/csv",
            )

        # Batch delete expander
        with st.expander("🗑️ Delete Entries"):
            del_options = [f"#{row['id']} — {row['party']} (Rs {row['amount']:,.0f} on {row['txn_date']})" for _, row in filtered_df.iterrows()]
            del_selection = st.multiselect("Select transactions to delete:", options=del_options)
            if st.button("Delete Selected", type="primary", disabled=not del_selection):
                ids_to_del = [int(item.split(" ")[0].replace("#", "")) for item in del_selection]
                deleted_count = delete_transactions(ids_to_del)
                st.toast(f"Deleted {deleted_count} transactions.", icon="🗑️")
                st.rerun()

# ------------------------------------------------------------------------------
# TAB 4: UDHAAR (CUSTOMER KHATA & WHATSAPP)
# ------------------------------------------------------------------------------
with tab_udhaar:
    st.subheader("👥 Udhaar (Customer Khata)")
    st.caption("Track who owes money, view individual khata history, and send polite WhatsApp payment reminders.")

    df_balances = get_customer_balances()

    if df_balances.empty:
        st.info("No customer udhaar records found. Load demo data or scan khata pages.")
    else:
        owing_df = df_balances[df_balances["balance"] > 0]
        total_outstanding = owing_df["balance"].sum()
        num_debtors = len(owing_df)

        m1, m2 = st.columns(2)
        with m1:
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-label">Total Outstanding Udhaar</div>
                    <div class="kpi-value" style="color: #B45309;">Rs {total_outstanding:,.0f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-label">Customers Who Owe Money</div>
                    <div class="kpi-value" style="color: #0F172A;">{num_debtors} customers</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()

        st.markdown("#### 📋 Customer Credit Balances")
        df_disp_balances = df_balances.copy()
        df_disp_balances["udhaar_given"] = df_disp_balances["udhaar_given"].apply(lambda x: f"Rs {x:,.0f}")
        df_disp_balances["payment_received"] = df_disp_balances["payment_received"].apply(lambda x: f"Rs {x:,.0f}")
        df_disp_balances["balance_formatted"] = df_disp_balances["balance"].apply(lambda x: f"Rs {x:,.0f}")

        st.dataframe(
            df_disp_balances[["party", "udhaar_given", "payment_received", "balance_formatted", "last_activity", "phone"]],
            hide_index=True,
            column_config={
                "party": st.column_config.TextColumn("Customer Name"),
                "udhaar_given": st.column_config.TextColumn("Total Udhaar Given"),
                "payment_received": st.column_config.TextColumn("Total Repaid"),
                "balance_formatted": st.column_config.TextColumn("Net Balance (Owed)"),
                "last_activity": st.column_config.TextColumn("Last Transaction"),
                "phone": st.column_config.TextColumn("Phone Number"),
            },
        )

        st.divider()

        # WhatsApp Reminder Drawer & Customer History
        st.markdown("#### 💬 Send WhatsApp Khata Reminder")
        debtor_names = owing_df["party"].tolist()

        if not debtor_names:
            st.success("All customer accounts are clear! No outstanding balances.")
        else:
            col_u1, col_u2 = st.columns([1, 1.2], gap="large")

            with col_u1:
                selected_customer = st.selectbox("Select Customer:", options=debtor_names)
                cust_row = owing_df[owing_df["party"] == selected_customer].iloc[0]
                cust_balance = float(cust_row["balance"])

                st.write(f"**Outstanding Balance:** `Rs {cust_balance:,.0f}`")
                current_phone = cust_row["phone"] or ""
                new_phone = st.text_input("Customer Phone (03XX1234567):", value=current_phone)
                if st.button("Save Phone Number"):
                    set_customer_phone(selected_customer, new_phone)
                    st.toast("Phone number saved!", icon="💾")
                    st.rerun()

                lang_choice = st.radio(
                    "Reminder Language:",
                    options=["Roman Urdu", "Urdu Script", "English"],
                    horizontal=True,
                )

                if st.button("✍️ Draft AI Reminder", type="primary"):
                    with st.spinner(f"Drafting respectful payment reminder with {model_name}..."):
                        reminder_msg, draft_source = draft_reminder(
                            shop_name=shop_name,
                            customer=selected_customer,
                            amount=cust_balance,
                            language=lang_choice,
                            api_key=api_key,
                            model_name=model_name,
                        )
                        st.session_state.drafted_reminders[selected_customer] = {
                            "text": reminder_msg,
                            "source": draft_source,
                        }

            with col_u2:
                saved_draft = st.session_state.drafted_reminders.get(selected_customer)
                if isinstance(saved_draft, dict):
                    current_draft = saved_draft.get("text", "")
                    draft_source = saved_draft.get("source", "Template message (AI unavailable)")
                elif isinstance(saved_draft, str):
                    current_draft = saved_draft
                    draft_source = "Template message (AI unavailable)"
                else:
                    current_draft = (
                        f"Assalam o Alaikum {selected_customer} sahab! {shop_name} ke khate mein aap ka "
                        f"Rs {cust_balance:,.0f} baqi hai. Jab suhoolat ho ada kar dijiye. Shukriya!"
                    )
                    draft_source = "Template message (AI unavailable)"

                if draft_source == "AI answer":
                    st.caption("✨ **AI answer**")
                else:
                    st.caption("⚠️ **Template message (AI unavailable)**")

                edited_msg = st.text_area(
                    "Editable Reminder Message:",
                    value=current_draft,
                    height=130,
                )

                wa_url = whatsapp_link(new_phone, edited_msg)
                if wa_url:
                    st.link_button(
                        "📲 Open in WhatsApp",
                        url=wa_url,
                        type="primary",
                    )
                else:
                    st.info("ℹ️ Enter and save a valid Pakistani phone number (e.g. 03001234567) to open WhatsApp directly.")

            # Individual Customer Transaction History Drilldown
            with st.expander(f"📜 View Full Khata History for {selected_customer}"):
                df_all_tx = get_all_transactions()
                if not df_all_tx.empty:
                    cust_tx = df_all_tx[df_all_tx["party"].str.lower() == selected_customer.lower()]
                    if cust_tx.empty:
                        st.caption("No individual transactions found.")
                    else:
                        cust_tx_disp = cust_tx.copy()
                        cust_tx_disp["amount_formatted"] = cust_tx_disp["amount"].apply(lambda x: f"Rs {x:,.0f}")
                        st.dataframe(
                            cust_tx_disp[["txn_date", "type", "amount_formatted", "note", "source"]],
                            hide_index=True,
                        )

# ------------------------------------------------------------------------------
# TAB 5: DASHBOARD
# ------------------------------------------------------------------------------
with tab_dashboard:
    st.subheader("📊 Financial Dashboard & Analytics")

    today = date.today()
    df_all = get_all_transactions()
    unpaid_bills_df = get_unpaid_bills()

    # 1. Unpaid Bills Alerts
    if not unpaid_bills_df.empty:
        for _, bill in unpaid_bills_df.iterrows():
            due_str = bill.get("due_date")
            b_amount = float(bill.get("amount") or 0.0)
            b_party = bill.get("party") or "Biller"

            if due_str:
                try:
                    due_d = datetime.strptime(due_str, "%Y-%m-%d").date()
                    delta = (due_d - today).days
                    if delta < 0:
                        st.error(
                            f"🚨 **{b_party}** bill of **Rs {b_amount:,.0f}** is **overdue by {abs(delta)} day(s)**! (Due: {due_str})"
                        )
                    elif delta <= 3:
                        st.error(
                            f"⚠️ **{b_party}** bill of **Rs {b_amount:,.0f}** is **due in {delta} day(s)** (Due: {due_str})!"
                        )
                except ValueError:
                    pass

    # 2. Key Metrics Row
    curr_month_str = today.strftime("%Y-%m")
    if not df_all.empty:
        df_all["txn_month"] = df_all["txn_date"].str.slice(0, 7)
        month_expenses = df_all[(df_all["type"] == "expense") & (df_all["txn_month"] == curr_month_str)]["amount"].sum()
        month_cash_sales = df_all[(df_all["type"] == "cash_sale") & (df_all["txn_month"] == curr_month_str)]["amount"].sum()
    else:
        month_expenses = 0.0
        month_cash_sales = 0.0

    df_bals = get_customer_balances()
    total_udhaar = df_bals[df_bals["balance"] > 0]["balance"].sum() if not df_bals.empty else 0.0
    unpaid_bills_total = unpaid_bills_df["amount"].sum() if not unpaid_bills_df.empty else 0.0

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.markdown(
            f"""
            <div class="kpi-container" style="border-top-color: #DC2626;">
                <div class="kpi-label">Spending this month</div>
                <div class="kpi-value" style="color: #991B1B;">Rs {month_expenses:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with mc2:
        st.markdown(
            f"""
            <div class="kpi-container" style="border-top-color: #D97706;">
                <div class="kpi-label">Outstanding udhaar</div>
                <div class="kpi-value" style="color: #B45309;">Rs {total_udhaar:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with mc3:
        st.markdown(
            f"""
            <div class="kpi-container" style="border-top-color: #EF4444;">
                <div class="kpi-label">Unpaid bills</div>
                <div class="kpi-value" style="color: #7F1D1D;">Rs {unpaid_bills_total:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with mc4:
        # Strictly labeled as specified
        st.markdown(
            f"""
            <div class="kpi-container" style="border-top-color: #059669;">
                <div class="kpi-label">Recorded cash sales this month</div>
                <div class="kpi-value" style="color: #047857;">Rs {month_cash_sales:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # 3. Plotly Charts
    col_ch1, col_ch2 = st.columns(2)

    with col_ch1:
        exp_df = df_all[df_all["type"] == "expense"] if not df_all.empty else pd.DataFrame()
        if not exp_df.empty:
            cat_totals = exp_df.groupby("category", as_index=False)["amount"].sum()
            fig_cat = px.bar(
                cat_totals,
                x="category",
                y="amount",
                title="Expenses by Category (PKR)",
                color="category",
                color_discrete_sequence=px.colors.qualitative.Prism,
                labels={"amount": "Total PKR", "category": "Category"},
            )
            fig_cat.update_layout(showlegend=False, xaxis_tickangle=-45, plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_cat)
        else:
            st.info("No expense data available to plot categories.")

    with col_ch2:
        if not exp_df.empty:
            exp_copy = exp_df.copy()
            exp_copy["month"] = exp_copy["txn_date"].str.slice(0, 7)
            monthly_exp = exp_copy.groupby("month", as_index=False)["amount"].sum().sort_values("month")
            fig_mo = px.bar(
                monthly_exp,
                x="month",
                y="amount",
                title="Expenses by Month (PKR)",
                labels={"amount": "Total PKR", "month": "Month"},
                color_discrete_sequence=["#047857"],
            )
            fig_mo.update_layout(plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_mo)
        else:
            st.info("No monthly expense data available.")

    # 3.1 Cash Sales Trend (Last 30 days)
    st.markdown("#### 📈 Recorded Cash Sales (Last 30 Days)")
    thirty_days_ago = (today - timedelta(days=30)).isoformat()
    cash_sales_df = (
        df_all[(df_all["type"] == "cash_sale") & (df_all["txn_date"] >= thirty_days_ago)]
        if not df_all.empty
        else pd.DataFrame()
    )

    if not cash_sales_df.empty:
        daily_sales = cash_sales_df.groupby("txn_date", as_index=False)["amount"].sum().sort_values("txn_date")
        fig_sales = px.line(
            daily_sales,
            x="txn_date",
            y="amount",
            markers=True,
            title="Daily Recorded Cash Sales",
            labels={"amount": "Cash Sales (PKR)", "txn_date": "Date"},
            line_shape="spline",
            color_discrete_sequence=["#059669"],
        )
        fig_sales.update_layout(plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_sales)
    else:
        st.info("No recorded cash sales in the last 30 days.")

    st.divider()

    # 4. Unpaid Bills Management Table
    st.markdown("#### ⚡ Unpaid Bills List")
    if unpaid_bills_df.empty:
        st.success("All utility and vendor bills have been marked paid!")
    else:
        for _, ub in unpaid_bills_df.iterrows():
            bill_id = int(ub["id"])
            b_party = ub["party"]
            b_amt = float(ub["amount"])
            b_due = ub["due_date"] or "No due date"

            col_b1, col_b2, col_b3, col_b4 = st.columns([2, 1.2, 1.5, 1])
            with col_b1:
                st.write(f"**{b_party}** — Rs {b_amt:,.0f}")
            with col_b2:
                st.caption(f"Category: {ub.get('category')}")
            with col_b3:
                if ub.get("due_date"):
                    try:
                        due_dt = datetime.strptime(ub["due_date"], "%Y-%m-%d").date()
                        rem = (due_dt - today).days
                        due_label = f"Overdue by {abs(rem)}d" if rem < 0 else f"Due in {rem}d ({ub['due_date']})"
                    except ValueError:
                        due_label = ub["due_date"]
                else:
                    due_label = "No due date"
                st.write(f"📅 `{due_label}`")
            with col_b4:
                if st.button("Mark Paid", key=f"paid_{bill_id}"):
                    mark_paid(bill_id)
                    st.toast(f"Marked {b_party} bill as paid!", icon="✅")
                    st.rerun()

    st.divider()

    # 5. Natural Language Financial Q&A: Ask Your Hisaab
    st.markdown("#### 💬 Ask Your Hisaab (Gemini 3.8 Flash)")
    st.caption("Ask financial questions in Urdu, Roman Urdu, or English about your shop expenses and ledger.")

    col_q1, col_q2 = st.columns([3, 1])
    with col_q1:
        user_query = st.text_input(
            "Question",
            placeholder="Is mahine bijli pe kitna kharcha hua? / Who owes me the most?",
            label_visibility="collapsed",
        )
    with col_q2:
        ask_clicked = st.button("🔍 Ask AI", type="primary")

    if ask_clicked and user_query:
        with st.spinner(f"Analyzing your ledger records with {model_name}..."):
            ans_text, ans_source = ask_ledger(
                question=user_query,
                ledger_df=df_all,
                api_key=api_key,
                model_name=model_name,
            )
            if ans_source == "AI answer":
                st.success(f"🤖 **AI answer:**\n\n{ans_text}")
            elif ans_source == "Calculated from your ledger (offline, not AI)":
                st.info(f"📊 **Calculated from your ledger (offline, not AI):**\n\n{ans_text}")
            elif ans_source == "Model Error":
                st.error(f"❌ **Model Error:**\n\n{ans_text}")
            else:
                st.warning(f"ℹ️ {ans_text}")
