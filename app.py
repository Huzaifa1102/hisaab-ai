"""
app.py — Hisaab AI (حساب) Frontend
Enterprise-Grade AI Bookkeeper for Pakistani Retailers & Kiryana Stores.

Features:
- Tab 1: 📷 Smart Scan (Multimodal OCR & Document Verification)
- Tab 2: 🎙️ Voice Khata (Groq Whisper-large-v3 Speech-to-Text & Gemini)
- Tab 3: 📒 Ledger (Search, Filtering, Excel/CSV Export, Quick Add, Batch Delete)
- Tab 4: 👥 Udhaar (Customer Khata Balances, WhatsApp AI Reminders, Ledger History)
- Tab 5: 📊 Dashboard (Bill Due Alerts, Plotly Charts, Financial Q&A with the sidebar's Gemini model)
"""

import html
import json
import os
import sys
import uuid
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
    add_or_update_stock,
    add_transactions,
    create_or_get_shop,
    deduct_stock,
    delete_transactions,
    find_duplicates,
    get_all_shops,
    get_all_transactions,
    get_customer_balances,
    get_customer_phone,
    get_galla_history,
    get_inventory,
    get_today_cash_summary,
    get_unpaid_bills,
    init_db,
    mark_paid,
    reset_db,
    save_galla_reconciliation,
    seed_demo_data,
    set_customer_phone,
    update_inventory_from_line_items,
    update_shop_pin,
    verify_shop_pin,
)
from core import (
    AIServiceError,
    ExtractionResult,
    ask_ledger,
    cache_json,
    clean_model_name,
    draft_reminder,
    extract_from_image,
    extract_from_pdf,
    extract_from_text,
    extract_unseen_image_offline,
    get_gemini_key_pool,
    normalize_entry,
    offline_parse_document,
    resolve_model_name,
    send_whatsapp_api,
    transcribe_audio,
    whatsapp_link,
)

# UI Localization Dictionary
UI_TRANSLATIONS = {
    "en": {
        "app_title": "Hisaab AI",
        "app_subtitle": "Digital khata for kiryana stores",
        "tab_scan": "📷 Smart Scan",
        "tab_voice": "🎙️ Voice Khata",
        "tab_ledger": "📒 Ledger",
        "tab_udhaar": "👥 Udhaar",
        "tab_inventory": "📦 Inventory",
        "tab_dashboard": "📊 Dashboard",
        "scan_header": "📷 Smart Document Scanner",
        "scan_desc": "Upload photos or PDF copies of receipts, wholesaler invoices, utility bills, or khata pages.",
        "upload_label": "Upload Document (JPG, PNG, WebP, PDF)",
        "extract_btn": "🚀 Extract with AI",
        "save_to_ledger": "💾 Save to Ledger",
        "discard": "🗑️ Discard",
        "inventory_update_cb": "📦 Update inventory stock with extracted line items",
        "spending_month": "Expenses this month (incl. unpaid bills)",
        "outstanding_udhaar": "Outstanding udhaar",
        "unpaid_bills": "Unpaid bills",
        "cash_sales_month": "Recorded cash sales this month",
        "galla_title": "💵 Galla Hisaab (Cash Drawer Reconciliation)",
        "galla_opening": "Opening Cash (Rs)",
        "galla_counted": "Counted Physical Cash in Drawer (Rs)",
        "galla_save": "💾 Save Today's Galla Reconciliation",
        "galla_balanced": "✅ Galla Balanced! Physical cash matches recorded transactions perfectly.",
        "galla_surplus": "📈 Cash Surplus: Physical cash is more than recorded transactions.",
        "galla_shortage": "⚠️ Cash Shortage: Physical cash is less than recorded transactions.",
        "low_stock_warning": "⚠️ Low Stock Alert: The following items are below minimum safety levels!",
        "add_stock_header": "➕ Add or Restock Item",
        "shop_security": "🛡️ Shopkeeper Security PIN",
        "pin_prompt": "Enter 4-digit PIN to perform sensitive action:",
        "pin_locked": "🔒 Security Locked",
        "pin_unlocked": "🔓 Security Unlocked",
        "whatsapp_api_btn": "⚡ Send WhatsApp (Direct API)",
        "whatsapp_web_btn": "📲 Open in WhatsApp Web",
    },
    "ur": {
        "app_title": "حساب اے آئی",
        "app_subtitle": "کریانہ اور ریٹیل اسٹورز کے لیے ڈیجیٹل کھاتہ",
        "tab_scan": "📷 اسمارٹ اسکین",
        "tab_voice": "🎙️ آواز کھاتہ",
        "tab_ledger": "📒 ڈیجیٹل لیجر",
        "tab_udhaar": "👥 ادھار کھاتہ",
        "tab_inventory": "📦 گودام و اسٹاک",
        "tab_dashboard": "📊 ڈیش بورڈ",
        "scan_header": "📷 اسمارٹ دستاویز اسکینر",
        "scan_desc": "بلز، رسیدیں، ہول سیل انوائسز یا کھاتہ رجسٹر کے صفحات کی تصاویر یا پی ڈی ایف اپلوڈ کریں۔",
        "upload_label": "دستاویز اپلوڈ کریں (تصویر یا پی ڈی ایف)",
        "extract_btn": "🚀 اے آئی سے اسکین کریں",
        "save_to_ledger": "💾 کھاتے میں محفوظ کریں",
        "discard": "🗑️ منسوخ کریں",
        "inventory_update_cb": "📦 مال کی اشیاء گودام و اسٹاک میں شامل کریں",
        "spending_month": "ماہانہ کل اخراجات",
        "outstanding_udhaar": "واجب الادا ادھار",
        "unpaid_bills": "غیر ادا شدہ بلز",
        "cash_sales_month": "کاؤنٹر نقد فروخت",
        "galla_title": "💵 گلہ حساب (کیش ڈراور بیلنسنگ)",
        "galla_opening": "شروع کیش / صبح کا گلہ (روپے)",
        "galla_counted": "گن کر درج شدہ کیش (روپے)",
        "galla_save": "💾 یومیہ گلہ ریکارڈ محفوظ کریں",
        "galla_balanced": "✅ گلہ بالکل درست ہے! کاؤنٹر کیش اور کھاتہ برابر ہے۔",
        "galla_surplus": "📈 کیش اضافی ہے: گلے میں رقم کھاتے سے زیادہ ہے۔",
        "galla_shortage": "⚠️ کیش کم ہے: گلے میں رقم کھاتے سے کم ہے۔",
        "low_stock_warning": "⚠️ اسٹاک میں کمی کا الرٹ: درج ذیل اشیاء کم سے کم حد سے کم ہیں!",
        "add_stock_header": "➕ اسٹاک شامل / تبدیل کریں",
        "shop_security": "🛡️ دکاندار سیکورٹی پن کوڈ",
        "pin_prompt": "کارروائی کے لیے 4 ہندسوں کا پن کوڈ درج کریں:",
        "pin_locked": "🔒 سیکورٹی مقفل",
        "pin_unlocked": "🔓 سیکورٹی فعال",
        "whatsapp_api_btn": "⚡ فوری اے پی آئی ارسال",
        "whatsapp_web_btn": "📲 واٹس ایپ پر بھیجیں",
    },
}

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
if "scan_errors" not in st.session_state:
    st.session_state.scan_errors = []
for _confirm_key in ("confirm_demo", "confirm_reset"):
    if _confirm_key not in st.session_state:
        st.session_state[_confirm_key] = False

# Demo cache directory
CACHE_DIR = Path(__file__).parent / "demo_cache"
CACHE_DIR.mkdir(exist_ok=True)


def new_pending_doc(res: ExtractionResult, entries: List[Dict[str, Any]], img_bytes: Optional[bytes],
                    filename: str, is_offline: bool) -> Dict[str, Any]:
    """Builds a review-queue item. 'uid' keeps widget keys stable when other items are removed."""
    return {
        "uid": uuid.uuid4().hex,
        "result": res,
        "entries": entries,
        "img_bytes": img_bytes,
        "filename": filename,
        "doc_type": res.doc_type,
        "is_offline": is_offline,
    }


def remove_pending_doc(doc_item: Dict[str, Any]) -> None:
    st.session_state.pending_docs = [d for d in st.session_state.pending_docs if d is not doc_item]


def load_cached_doc(cache_file: Path, img_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Loads a saved demo_cache result as an offline review-queue item (raises if the file is invalid)."""
    raw = json.loads(cache_file.read_text(encoding="utf-8"))
    res = ExtractionResult.model_validate(raw)
    entries = [normalize_entry(e, fallback_date=res.document_date) for e in res.entries]
    doc = new_pending_doc(res, [e for e in entries if e], img_bytes, filename, is_offline=True)
    doc["cache_provenance"] = raw.get("provenance", "unknown")
    doc["cache_model"] = raw.get("model")
    return doc


def add_scan_error(filename: str, message: str, cache_file: Optional[Path] = None,
                   img_bytes: Optional[bytes] = None) -> None:
    st.session_state.scan_errors.append({
        "id": uuid.uuid4().hex,
        "filename": filename,
        "message": message,
        "cache_file": str(cache_file) if cache_file else None,
        "img_bytes": img_bytes,
    })


def api_key_input(label: str, env_var: str, help_text: str) -> str:
    """
    Returns the API key to use. A key from .env is never put into a widget, because
    password fields still send their value to the browser (and have a 'show' button).
    The user can optionally type a different key, which overrides the .env one.
    """
    env_key = os.getenv(env_var, "").strip()
    if env_key and not env_key.startswith("your_"):
        st.caption(f"🔑 {label}: loaded from .env (hidden)")
        override = st.text_input(
            f"Use a different {label} (optional)",
            value="",
            type="password",
            placeholder="Leave empty to use the .env key",
            help=help_text,
        )
        return override.strip() or env_key
    return st.text_input(label, value="", type="password", help=help_text).strip()


def ui_error_message(err: Exception) -> str:
    """UI-safe text for an exception: AIServiceError messages are already friendly; others are hidden."""
    if isinstance(err, AIServiceError):
        return str(err)
    print(f"[hisaab-ai] unexpected error ({type(err).__name__}): {err}", file=sys.stderr)
    return f"Something went wrong ({type(err).__name__}). Please try again."

# ==============================================================================
# VISUAL IDENTITY: the khata register
# The header is the cloth-bound cover of a "lal khata" (maroon binding, gold foil
# frame, Nastaliq title). Everything else stays quiet: ruled ledger rows for the
# key numbers, ink-blue actions, tabular figures for every rupee amount.
# Fonts fall back to system faces when offline.
# ==============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Mukta:wght@400;500;600;700&family=Noto+Nastaliq+Urdu:wght@500;700&display=swap');

    :root {
        --khata-binding: #6E1423;
        --khata-binding-deep: #4A0D18;
        --khata-foil: #D4AF37;
        --khata-foil-soft: rgba(212, 175, 55, 0.45);
        --khata-cover-text: #F8EBD0;
        --ink: #1E3A8A;
        --margin-rule: #C8323C;
        --paper-rule: #E9EEF5;
        --text: #111827;
        --muted: #5B6472;
        --line: #E3E6EA;
    }

    .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea,
    .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5 {
        font-family: 'Mukta', 'Segoe UI', system-ui, -apple-system, sans-serif;
    }

    /* Header: the register cover */
    .khata-cover {
        position: relative;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 16px;
        margin-bottom: 24px;
        padding: 22px 28px 22px 46px;
        border-radius: 6px;
        color: var(--khata-cover-text);
        background-color: var(--khata-binding);
        /* faint cloth weave */
        background-image:
            repeating-linear-gradient(45deg, rgba(255, 255, 255, 0.025) 0 2px, transparent 2px 5px),
            repeating-linear-gradient(-45deg, rgba(0, 0, 0, 0.05) 0 2px, transparent 2px 5px);
    }
    /* spine with gold stitching */
    .khata-cover::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 22px;
        border-radius: 6px 0 0 6px;
        background: var(--khata-binding-deep);
        border-right: 2px dashed var(--khata-foil-soft);
    }
    /* gold foil frame */
    .khata-cover::after {
        content: "";
        position: absolute;
        inset: 8px 8px 8px 30px;
        border: 1px solid var(--khata-foil-soft);
        border-radius: 3px;
        pointer-events: none;
    }
    .khata-brand {
        display: flex;
        align-items: center;
        gap: 20px;
        position: relative;
        z-index: 1;
    }
    .khata-urdu {
        font-family: 'Noto Nastaliq Urdu', 'Urdu Typesetting', 'Jameel Noori Nastaleeq', serif;
        font-size: 2.5rem;
        font-weight: 700;
        line-height: 1.7;
        color: var(--khata-foil);
    }
    .khata-brandname {
        font-size: 0.95rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        color: var(--khata-foil);
    }
    .hisaab-title {
        font-size: 1.6rem;
        font-weight: 700;
        line-height: 1.2;
        color: #FFF8E7;
    }
    .hisaab-subtitle {
        font-size: 0.95rem;
        color: var(--khata-cover-text);
        opacity: 0.85;
        margin-top: 2px;
    }
    .hisaab-status-pill {
        position: relative;
        z-index: 1;
        padding: 5px 14px;
        border: 1px solid var(--khata-foil-soft);
        border-radius: 9999px;
        background: rgba(0, 0, 0, 0.2);
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--khata-cover-text);
    }

    /* Key numbers: rows on ruled khata paper with a red double margin rule */
    .kpi-container {
        background-color: #FFFFFF;
        background-image: repeating-linear-gradient(to bottom, transparent 0 27px, var(--paper-rule) 27px 28px);
        border: 1px solid var(--line);
        border-left: 5px double var(--margin-rule);
        border-radius: 4px;
        padding: 12px 16px 12px 18px;
    }
    .kpi-label {
        color: var(--muted);
        font-size: 0.9rem;
        font-weight: 600;
        line-height: 1.3;
        margin-bottom: 2px;
    }
    .kpi-value {
        font-size: 1.65rem;
        font-weight: 700;
        line-height: 1.25;
        font-variant-numeric: tabular-nums;
        color: var(--text);
    }

    /* Tabs: register index, not pills */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid var(--line);
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 14px;
        font-weight: 600;
        font-size: 1rem;
        color: var(--muted);
    }
    .stTabs [aria-selected="true"] {
        color: var(--ink) !important;
    }

    @media (max-width: 768px) {
        .khata-cover { padding: 18px 18px 18px 40px; }
        .khata-urdu { font-size: 2rem; }
        .hisaab-title { font-size: 1.3rem; }
        .kpi-value { font-size: 1.35rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# SIDEBAR: Configuration & Offline Mode
# ==============================================================================
with st.sidebar:
    st.markdown("### 📒 **Hisaab AI (حساب)**")
    st.caption("AI-Powered Bookkeeper for Pakistani Kiryana Stores.")
    
    # 1. 100% Urdu Localization Toggle
    lang_choice = st.radio(
        "🌐 Language / زبان",
        ["🇬🇧 English", "🇵🇰 اردو"],
        horizontal=True,
        index=1 if st.session_state.get("app_lang") == "ur" else 0,
    )
    st.session_state.app_lang = "ur" if "اردو" in lang_choice else "en"
    is_urdu = st.session_state.app_lang == "ur"

    def t(key: str, default: str = "") -> str:
        lang = st.session_state.get("app_lang", "en")
        return UI_TRANSLATIONS.get(lang, {}).get(key, default or key)

    st.divider()

    # 2. Multi-Shop Profile Switcher
    st.subheader(f"🏪 {t('shop_profile', 'Shop Profile')}")
    all_shops = get_all_shops()
    shop_dict = {s["shop_name"]: s["shop_id"] for s in all_shops}
    shop_names = list(shop_dict.keys()) + ["➕ Add New Shop Profile"]
    curr_shop_name = next((k for k, v in shop_dict.items() if v == st.session_state.get("current_shop_id")), "Madina General Store")
    curr_idx = shop_names.index(curr_shop_name) if curr_shop_name in shop_names else 0

    selected_shop_name = st.selectbox("Active Shop", shop_names, index=curr_idx)
    if selected_shop_name == "➕ Add New Shop Profile":
        new_s_name = st.text_input("New Shop Name", placeholder="e.g. Bismillah Kiryana")
        new_s_pin = st.text_input("Security PIN (4 digits)", value="1234", max_chars=4, type="password")
        if st.button("Create & Switch Shop"):
            if new_s_name:
                new_profile = create_or_get_shop(new_s_name.lower().replace(" ", "_"), new_s_name, new_s_pin)
                st.session_state.current_shop_id = new_profile["shop_id"]
                st.toast(f"Switched to {new_s_name}!", icon="🏪")
                st.rerun()
        current_shop_id = st.session_state.get("current_shop_id", "madina_store")
        shop_name = curr_shop_name
    else:
        st.session_state.current_shop_id = shop_dict[selected_shop_name]
        current_shop_id = st.session_state.current_shop_id
        shop_name = selected_shop_name

    # 3. Shopkeeper Security PIN Lock
    pin_lock_active = st.toggle("🔒 Shopkeeper PIN Protection", value=False)
    if pin_lock_active:
        if not st.session_state.get("pin_unlocked"):
            pin_try = st.text_input("Enter 4-digit PIN for Admin Actions:", type="password", max_chars=4)
            if st.button("Unlock Security"):
                if verify_shop_pin(current_shop_id, pin_try):
                    st.session_state.pin_unlocked = True
                    st.toast("Admin Security Unlocked!", icon="🔓")
                    st.rerun()
                else:
                    st.error("Incorrect PIN! (Default is 1234)")
        else:
            st.success("🔓 Admin Mode Unlocked")
            if st.button("Lock Security"):
                st.session_state.pin_unlocked = False
                st.rerun()

    st.divider()

    st.subheader("⚙️ Settings & API Keys")
    default_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    raw_model_input = st.text_input(
        "Gemini Model",
        value=default_model,
        help="Default: gemini-3.8-flash (Model actually used will match this field).",
    )
    model_name = clean_model_name(raw_model_input)

    api_key = api_key_input(
        "Primary Gemini API Key", "GEMINI_API_KEY",
        help_text="Paste your Google AI Studio API key.",
    )

    # 4. Backup Gemini Key for Automatic Quota Failover
    backup_gemini_key = api_key_input(
        "Backup Gemini API Key (Failover)", "GEMINI_API_KEY_BACKUP_1",
        help_text="Automatic failover key if primary key quota is exhausted.",
    )
    key_pool = get_gemini_key_pool(api_key)
    if len(key_pool) > 1:
        st.caption(f"🛡️ **Multi-Key Failover Active:** {len(key_pool)} keys ready.")

    groq_key = api_key_input(
        "Groq API Key (Voice)", "GROQ_API_KEY",
        help_text="Optional: Free key from console.groq.com for Whisper speech-to-text.",
    )

    show_voice_tab = st.checkbox(
        "Show Voice Khata tab",
        value=True,
        help="Toggle to show/hide the Voice Khata tab during demo.",
    )

    st.divider()
    st.subheader("🧪 Demo Utilities")

    def _load_demo_ledger():
        st.session_state.sidebar_toast = (f"Demo ledger loaded with {seed_demo_data()} transactions.", "✅")
        st.session_state.confirm_demo = False

    def _reset_ledger():
        reset_db()
        st.session_state.sidebar_toast = ("Ledger reset. All entries were deleted.", "🗑️")
        st.session_state.confirm_reset = False

    st.checkbox("Replace current ledger with demo data", key="confirm_demo")
    st.button(
        t("load_demo", "📥 Load Demo Ledger"),
        type="secondary",
        disabled=not st.session_state.confirm_demo,
        on_click=_load_demo_ledger,
    )

    # Offline demo mode toggle
    offline_mode = st.toggle("Offline demo mode (use saved results)", value=False)
    if offline_mode:
        st.caption("📂 Offline mode active: extractions will run on-device and load pre-cached results.")

    # Reset ledger expander (with PIN protection if active)
    with st.expander("⚠️ Reset Database"):
        reset_allowed = not pin_lock_active or st.session_state.get("pin_unlocked")
        if not reset_allowed:
            st.warning("Admin PIN required to reset database.")
        st.checkbox("I understand this deletes everything", key="confirm_reset", disabled=not reset_allowed)
        st.button(
            "Reset Ledger",
            type="primary",
            disabled=(not st.session_state.confirm_reset) or (not reset_allowed),
            on_click=_reset_ledger,
        )

    if "sidebar_toast" in st.session_state:
        toast_msg, toast_icon = st.session_state.pop("sidebar_toast")
        st.toast(toast_msg, icon=toast_icon)

# ==============================================================================
# TOP APP HEADER BANNER (with Urdu RTL Support)
# ==============================================================================
today_str = date.today().strftime("%d %B %Y")
status_label = "⚡ " + t("offline_mode_label") if offline_mode else f"🟢 Live AI Engine ({html.escape(model_name)})"

rtl_css = ""
if is_urdu:
    rtl_css = """
    <style>
    .khata-brand { flex-direction: row-reverse !important; }
    .khata-brandname, .hisaab-title, .hisaab-subtitle { text-align: right !important; }
    .stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3 {
        font-family: 'Noto Nastaliq Urdu', 'Mukta', sans-serif !important;
    }
    </style>
    """

st.markdown(
    f"""
    {rtl_css}
    <div class="khata-cover" role="banner">
        <div class="khata-brand">
            <span class="khata-urdu" lang="ur" dir="rtl">حساب</span>
            <div>
                <div class="khata-brandname">{t('app_title')}</div>
                <div class="hisaab-title">{html.escape(shop_name)}</div>
                <div class="hisaab-subtitle">{t('app_subtitle')} — {today_str}</div>
            </div>
        </div>
        <div class="hisaab-status-pill">{status_label}</div>
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
    uid: str = doc_item.get("uid") or f"{doc_idx}_{filename}"

    st.markdown(f"### 📋 Review: **{filename}**")

    if is_offline:
        provenance = doc_item.get("cache_provenance")
        if provenance == "live_scan":
            model_note = f" with {doc_item['cache_model']}" if doc_item.get("cache_model") else ""
            st.warning(f"⚡ **Offline demo mode:** showing a saved result from an earlier live AI scan{model_note}.")
        elif provenance == "sample":
            st.warning("⚡ **Offline demo mode:** showing a hand-made sample result for this image, not a live AI scan.")
        else:
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
            key=f"editor_{uid}",
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

        # Line items expander & inventory update checkbox
        update_inv = False
        if raw_result.line_items:
            with st.expander(f"📦 View Line Items ({len(raw_result.line_items)} detected)"):
                li_df = pd.DataFrame([li.model_dump() for li in raw_result.line_items])
                st.dataframe(li_df)
                update_inv = st.checkbox(
                    t("inventory_update_cb", "📦 Update Inventory Stock with extracted line items"),
                    value=(doc_type == "invoice"),
                    key=f"inv_chk_{uid}",
                )

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("💾 Save to Ledger", key=f"save_{uid}", type="primary"):
                edited_rows = edited_df.to_dict(orient="records")
                valid_rows = []
                for r in edited_rows:
                    norm = normalize_entry(r, fallback_date=raw_result.document_date)
                    if norm:
                        valid_rows.append(norm)
                skipped = len(edited_rows) - len(valid_rows)

                if not valid_rows:
                    st.warning(
                        "Nothing saved: no row has a valid amount above 0. "
                        "Fix the amounts in the table, or click 'Discard'."
                    )
                else:
                    try:
                        active_shop = st.session_state.get("current_shop_id", "madina_store")
                        added_count = add_transactions(
                            valid_rows,
                            source=filename,
                            doc_type=doc_type,
                        )
                        if update_inv and raw_result.line_items:
                            inv_cnt = update_inventory_from_line_items(
                                [li.model_dump() for li in raw_result.line_items],
                                shop_id=active_shop,
                            )
                            if inv_cnt:
                                st.toast(f"Updated {inv_cnt} inventory items in stock!", icon="📦")
                    except Exception as save_err:
                        st.error(f"Could not save to the ledger: {ui_error_message(save_err)}")
                    else:
                        msg = f"Successfully saved {added_count} entries to ledger!"
                        if skipped:
                            msg += f" ({skipped} row(s) skipped: amount empty or 0)"
                        st.toast(msg, icon="✅")
                        remove_pending_doc(doc_item)
                        st.rerun()

        with col_btn2:
            if st.button("🗑️ Discard", key=f"discard_{uid}", type="secondary"):
                remove_pending_doc(doc_item)
                st.toast(f"Discarded {filename}.", icon="ℹ️")
                st.rerun()

    st.divider()

# ==============================================================================
# MAIN TABS INTERFACE
# ==============================================================================
tab_titles = [t("tab_scan", "📷 Smart Scan")]
if show_voice_tab:
    tab_titles.append(t("tab_voice", "🎙️ Voice Khata"))
tab_titles.extend([
    t("tab_ledger", "📒 Ledger"),
    t("tab_udhaar", "👥 Udhaar"),
    t("tab_inventory", "📦 Inventory"),
    t("tab_dashboard", "📊 Dashboard"),
])
tabs = st.tabs(tab_titles)

tab_scan = tabs[0]
if show_voice_tab:
    tab_voice = tabs[1]
    tab_ledger = tabs[2]
    tab_udhaar = tabs[3]
    tab_inventory = tabs[4]
    tab_dashboard = tabs[5]
else:
    tab_voice = None
    tab_ledger = tabs[1]
    tab_udhaar = tabs[2]
    tab_inventory = tabs[3]
    tab_dashboard = tabs[4]

# ------------------------------------------------------------------------------
# TAB 1: SMART SCAN
# ------------------------------------------------------------------------------
with tab_scan:
    st.subheader(t("scan_header", "📷 Smart Document Scanner"))
    st.caption(t("scan_desc", "Upload photos or PDF copies of receipts, wholesaler invoices, utility bills, or khata pages."))

    col_up1, col_up2 = st.columns([2, 1])
    with col_up1:
        uploaded_files = st.file_uploader(
            t("upload_label", "Upload Document (JPG, PNG, WebP, PDF)"),
            type=["jpg", "jpeg", "png", "webp", "pdf"],
            accept_multiple_files=True,
            key=f"doc_uploader_{st.session_state.uploader_key}",
        )
    with col_up2:
        camera_pic = None
        if st.toggle("📸 Use device camera", key="use_camera",
                     help="The browser asks for camera permission when you turn this on."):
            camera_pic = st.camera_input("Take a photo of bill / receipt")
            if camera_pic is not None:
                if uploaded_files is None:
                    uploaded_files = []
                uploaded_files.append(camera_pic)

    has_files = bool(uploaded_files)
    if st.button(t("extract_btn", "🚀 Extract with AI"), disabled=not has_files, type="primary"):
        st.session_state.scan_errors = []
        for f in uploaded_files:
            file_bytes = f.getvalue()
            is_camera = f is camera_pic
            filename = f"Camera photo ({datetime.now().strftime('%H:%M:%S')})" if is_camera else f.name
            base_name = Path(f.name).stem
            is_pdf_file = f.name.lower().endswith(".pdf")
            cache_file = None if (is_camera or is_pdf_file) else CACHE_DIR / f"{base_name}.json"

            if is_pdf_file:
                if offline_mode:
                    res, normalized_list = extract_from_pdf(
                        file_bytes,
                        filename,
                        api_key=api_key,
                        model_name=model_name,
                        offline_only=True,
                    )
                    doc_item = new_pending_doc(res, normalized_list, None, filename, is_offline=True)
                    doc_item["is_pdf"] = True
                    st.session_state.pending_docs.append(doc_item)
                else:
                    with st.spinner(f"Extracting digital PDF '{filename}'..."):
                        try:
                            res, normalized_list = extract_from_pdf(
                                file_bytes,
                                filename,
                                api_key=api_key,
                                model_name=model_name,
                                offline_only=False,
                            )
                            doc_item = new_pending_doc(res, normalized_list, None, filename, is_offline=False)
                            doc_item["is_pdf"] = True
                            st.session_state.pending_docs.append(doc_item)
                        except Exception as pdf_err:
                            add_scan_error(
                                filename,
                                f"Extraction failed: {ui_error_message(pdf_err)}",
                                img_bytes=file_bytes,
                            )
            elif offline_mode:
                if cache_file is None:
                    add_scan_error(filename, "Offline demo mode has no saved results for camera photos. "
                                             "Upload a saved test image, or turn off offline mode.")
                elif cache_file.exists():
                    try:
                        st.session_state.pending_docs.append(load_cached_doc(cache_file, file_bytes, filename))
                    except Exception as parse_err:
                        add_scan_error(filename, f"The saved result `demo_cache/{base_name}.json` could not be read "
                                                 f"({type(parse_err).__name__}).")
                else:
                    add_scan_error(
                        filename,
                        f"Offline demo mode: no saved result for '{filename}' (expected `demo_cache/{base_name}.json`). "
                        "Turn off offline mode to scan it live.",
                        img_bytes=file_bytes,
                    )
            else:
                with st.spinner(f"Reading and analyzing '{filename}' with {model_name}..."):
                    try:
                        res, normalized_list = extract_from_image(
                            file_bytes,
                            api_key=api_key,
                            model_name=model_name,
                        )
                        if cache_file is not None:
                            try:
                                cache_file.write_text(cache_json(res, model_name), encoding="utf-8")
                            except Exception:
                                pass

                        st.session_state.pending_docs.append(new_pending_doc(
                            res, normalized_list, file_bytes, filename, is_offline=False,
                        ))
                    except Exception as err:
                        add_scan_error(
                            filename,
                            f"Extraction failed: {ui_error_message(err)}",
                            cache_file=cache_file if cache_file is not None and cache_file.exists() else None,
                            img_bytes=file_bytes,
                        )

        st.session_state.uploader_key += 1
        st.rerun()

    # Scan errors (shown until dismissed or the next extraction)
    for scan_err in list(st.session_state.scan_errors):
        st.error(f"**{scan_err['filename']}** — {scan_err['message']}")
        col_e1, col_e2, _ = st.columns([1.4, 0.6, 2])
        if scan_err.get("cache_file"):
            with col_e1:
                if st.button(f"Use saved result for {scan_err['filename']}", key=f"use_cache_{scan_err['id']}"):
                    try:
                        st.session_state.pending_docs.append(
                            load_cached_doc(Path(scan_err["cache_file"]), scan_err["img_bytes"], scan_err["filename"])
                        )
                    except Exception as cache_err:
                        scan_err["message"] = f"The saved result could not be read ({type(cache_err).__name__})."
                        scan_err["cache_file"] = None
                    else:
                        st.session_state.scan_errors.remove(scan_err)
                    st.rerun()
        elif scan_err.get("img_bytes"):
            with col_e1:
                if st.button(f"Process with On-Device Engine for {scan_err['filename']}", key=f"use_ondevice_{scan_err['id']}"):
                    res, norm_list = extract_unseen_image_offline(scan_err["img_bytes"], scan_err["filename"])
                    doc_item = new_pending_doc(res, norm_list, scan_err["img_bytes"], scan_err["filename"], is_offline=True)
                    doc_item["cache_provenance"] = "on_device_heuristic"
                    st.session_state.pending_docs.append(doc_item)
                    st.session_state.scan_errors.remove(scan_err)
                    st.rerun()
        with col_e2:
            if st.button("Dismiss", key=f"dismiss_err_{scan_err['id']}"):
                st.session_state.scan_errors.remove(scan_err)
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
                                st.error(f"Transcription failed: {ui_error_message(e)}")

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
                        voice_doc = new_pending_doc(
                            res, norm_entries, None,
                            f"Voice Note ({datetime.now().strftime('%H:%M:%S')})", is_offline=False,
                        )
                        voice_doc.update(transcript=edited_transcript, doc_type="voice")
                        st.session_state.pending_docs.append(voice_doc)
                        st.session_state.voice_transcript = ""
                        st.toast("Voice transaction extracted! Review it below or in Smart Scan.", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Voice extraction error: {ui_error_message(e)}")

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
                        reminder_msg, draft_source, draft_notice = draft_reminder(
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
                            "notice": draft_notice,
                        }

            with col_u2:
                saved_draft = st.session_state.drafted_reminders.get(selected_customer)
                draft_notice = None
                if isinstance(saved_draft, dict):
                    current_draft = saved_draft.get("text", "")
                    draft_source = saved_draft.get("source", "Template message (AI unavailable)")
                    draft_notice = saved_draft.get("notice")
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
                    if draft_notice:
                        st.caption(f"Reason: {draft_notice}")

                edited_msg = st.text_area(
                    "Editable Reminder Message:",
                    value=current_draft,
                    height=130,
                )

                wa_url = whatsapp_link(new_phone, edited_msg)
                wa_btn1, wa_btn2 = st.columns([1, 1])
                with wa_btn1:
                    if wa_url:
                        st.link_button(
                            t("whatsapp_web_btn", "📲 Open in WhatsApp"),
                            url=wa_url,
                            type="primary",
                        )
                    else:
                        st.info("ℹ️ Enter and save a valid phone number (e.g. 03001234567).")
                with wa_btn2:
                    if st.button(t("whatsapp_api_btn", "⚡ Send via WhatsApp API"), key=f"wa_api_{selected_customer}"):
                        if not new_phone:
                            st.warning("Please save customer phone number first.")
                        else:
                            with st.spinner("Dispatching WhatsApp message in background..."):
                                ok, res_msg = send_whatsapp_api(new_phone, edited_msg)
                                if ok:
                                    st.success(res_msg)
                                else:
                                    st.info(f"ℹ️ {res_msg}")

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
# TAB 5: INVENTORY (گودام و اسٹاک)
# ------------------------------------------------------------------------------
with tab_inventory:
    st.subheader(t("tab_inventory", "📦 Inventory (گودام و اسٹاک)"))
    st.caption("Track kiryana stock quantities, cost rates, retail valuations, and reorder warnings.")

    active_shop = st.session_state.get("current_shop_id", "madina_store")
    inv_df = get_inventory(shop_id=active_shop)

    if inv_df.empty:
        st.info("No inventory items found. Add items below or click 'Load Demo Ledger'.")
    else:
        total_items = len(inv_df)
        total_cost_val = float(inv_df["total_cost_value"].sum())
        total_retail_val = float(inv_df["total_sale_value"].sum())
        low_stock_items = inv_df[inv_df["quantity"] <= inv_df["min_stock"]]

        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1:
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-label">{t('items', 'Total Commodities')}</div>
                    <div class="kpi-value" style="color: #0F172A;">{total_items} items</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with ic2:
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-label">{t('total_stock_value', 'Stock Cost Valuation')}</div>
                    <div class="kpi-value" style="color: #1E3A8A;">Rs {total_cost_val:,.0f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with ic3:
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-label">{t('potential_retail_value', 'Potential Retail Value')}</div>
                    <div class="kpi-value" style="color: #047857;">Rs {total_retail_val:,.0f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with ic4:
            low_color = "#DC2626" if len(low_stock_items) > 0 else "#047857"
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-label">{t('low_stock_alert', 'Low Stock Items')}</div>
                    <div class="kpi-value" style="color: {low_color};">{len(low_stock_items)} items</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if not low_stock_items.empty:
            for _, ls in low_stock_items.iterrows():
                st.error(
                    f"⚠️ **Low Stock Alert:** {ls['item_name']} — Only **{ls['quantity']:.1f} {ls['unit']}** remaining "
                    f"(Minimum safety level: {ls['min_stock']:.1f} {ls['unit']})!"
                )

        st.divider()
        st.markdown("#### 📦 Current Stock Register")
        disp_inv = inv_df.copy()
        disp_inv["cost_price"] = disp_inv["cost_price"].apply(lambda x: f"Rs {x:,.0f}")
        disp_inv["sale_price"] = disp_inv["sale_price"].apply(lambda x: f"Rs {x:,.0f}")
        disp_inv["total_cost_value"] = disp_inv["total_cost_value"].apply(lambda x: f"Rs {x:,.0f}")
        disp_inv["total_sale_value"] = disp_inv["total_sale_value"].apply(lambda x: f"Rs {x:,.0f}")

        st.dataframe(
            disp_inv[["item_name", "category", "quantity", "unit", "cost_price", "sale_price", "total_cost_value", "total_sale_value", "min_stock"]],
            hide_index=True,
            column_config={
                "item_name": st.column_config.TextColumn("Item Name / جنس"),
                "category": st.column_config.TextColumn("Category"),
                "quantity": st.column_config.NumberColumn("Current Stock", format="%.1f"),
                "unit": st.column_config.TextColumn("Unit"),
                "cost_price": st.column_config.TextColumn("Cost Price (PKR)"),
                "sale_price": st.column_config.TextColumn("Sale Price (PKR)"),
                "total_cost_value": st.column_config.TextColumn("Total Cost Value"),
                "total_sale_value": st.column_config.TextColumn("Retail Value"),
                "min_stock": st.column_config.NumberColumn("Reorder Level"),
            },
        )

    with st.expander(t("add_stock_header", "➕ Add or Restock Item")):
        c1, c2, c3 = st.columns(3)
        with c1:
            item_name_inp = st.text_input("Item Name (e.g. Atta 20kg)")
            item_cat_inp = st.selectbox("Category", FIXED_CATEGORIES, index=0)
        with c2:
            item_qty_inp = st.number_input("Quantity", min_value=0.0, value=10.0, step=1.0)
            item_unit_inp = st.selectbox(
                "Unit",
                ["kg", "bag (20kg)", "bag (50kg)", "tin (5L)", "carton", "pack", "litre", "piece"],
                index=0,
            )
        with c3:
            item_cost_inp = st.number_input("Cost Price (PKR)", min_value=0.0, value=500.0, step=50.0)
            item_sale_inp = st.number_input("Sale Price (PKR)", min_value=0.0, value=550.0, step=50.0)
        item_min_inp = st.number_input("Minimum Reorder Level", min_value=1.0, value=5.0)

        if st.button("Save Item to Stock"):
                if item_name_inp:
                    add_or_update_stock(
                        item_name=item_name_inp,
                        quantity=item_qty_inp,
                        unit=item_unit_inp,
                        cost_price=item_cost_inp,
                        sale_price=item_sale_inp,
                        min_stock=item_min_inp,
                        category=item_cat_inp,
                        shop_id=active_shop,
                    )
                    st.toast("Stock updated successfully!", icon="✅")
                    st.rerun()

# ------------------------------------------------------------------------------
# TAB 6: DASHBOARD (FINANCIAL ANALYTICS & GALLA HISAAB)
# ------------------------------------------------------------------------------
with tab_dashboard:
    st.subheader(t("tab_dashboard", "📊 Financial Dashboard & Analytics"))

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
            <div class="kpi-container">
                <div class="kpi-label">{t('spending_month')}</div>
                <div class="kpi-value" style="color: #991B1B;">Rs {month_expenses:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with mc2:
        st.markdown(
            f"""
            <div class="kpi-container">
                <div class="kpi-label">{t('outstanding_udhaar')}</div>
                <div class="kpi-value" style="color: #B45309;">Rs {total_udhaar:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with mc3:
        st.markdown(
            f"""
            <div class="kpi-container">
                <div class="kpi-label">{t('unpaid_bills')}</div>
                <div class="kpi-value" style="color: #7F1D1D;">Rs {unpaid_bills_total:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with mc4:
        st.markdown(
            f"""
            <div class="kpi-container">
                <div class="kpi-label">{t('cash_sales_month')}</div>
                <div class="kpi-value" style="color: #047857;">Rs {month_cash_sales:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # 3. GALLA HISAAB (CASH DRAWER RECONCILIATION)
    st.markdown(f"### {t('galla_title')}")
    st.caption("Verify that physical cash in the shop drawer matches recorded cash sales, customer repayments, and expenses.")

    cash_summary = get_today_cash_summary(shop_id=active_shop)
    c_s1, c_s2, c_s3, c_s4 = st.columns(4)
    with c_s1:
        opening_cash_val = st.number_input(
            t("galla_opening", "Opening Cash (Rs)"),
            min_value=0.0,
            value=5000.0,
            step=500.0,
            key="galla_open_inp",
        )
    with c_s2:
        st.metric("Recorded Cash Sales (+)", f"Rs {cash_summary['cash_sales']:,.0f}")
    with c_s3:
        st.metric("Cash Repayments Received (+)", f"Rs {cash_summary['cash_repayments']:,.0f}")
    with c_s4:
        st.metric("Cash Expenses Paid (-)", f"Rs {cash_summary['cash_expenses']:,.0f}")

    expected_galla = opening_cash_val + cash_summary["cash_sales"] + cash_summary["cash_repayments"] - cash_summary["cash_expenses"]
    st.markdown(f"#### **{t('expected_cash', 'Expected Cash in Drawer')}:** `Rs {expected_galla:,.0f}`")

    with st.expander("🧮 Cash Denominations Counter (روپے کے نوٹ گننے کا کیلکولیٹر)"):
        d_c1, d_c2, d_c3, d_c4 = st.columns(4)
        with d_c1:
            n_5000 = st.number_input("Rs 5,000 Notes", min_value=0, value=0, key="n5000")
            n_1000 = st.number_input("Rs 1,000 Notes", min_value=0, value=0, key="n1000")
        with d_c2:
            n_500 = st.number_input("Rs 500 Notes", min_value=0, value=0, key="n500")
            n_100 = st.number_input("Rs 100 Notes", min_value=0, value=0, key="n100")
        with d_c3:
            n_50 = st.number_input("Rs 50 Notes", min_value=0, value=0, key="n50")
            n_20 = st.number_input("Rs 20 Notes", min_value=0, value=0, key="n20")
        with d_c4:
            n_10 = st.number_input("Rs 10 Notes", min_value=0, value=0, key="n10")
            n_coins = st.number_input("Coins / سکّے (Rs)", min_value=0, value=0, key="ncoins")
        counted_denom_total = (
            (n_5000 * 5000)
            + (n_1000 * 1000)
            + (n_500 * 500)
            + (n_100 * 100)
            + (n_50 * 50)
            + (n_20 * 20)
            + (n_10 * 10)
            + n_coins
        )
        st.info(f"Total from note calculator: **Rs {counted_denom_total:,.0f}**")

    counted_actual = st.number_input(
        t("galla_counted", "Counted Physical Cash in Drawer (Rs)"),
        min_value=0.0,
        value=float(counted_denom_total) if counted_denom_total > 0 else float(expected_galla),
        step=100.0,
        key="galla_actual_inp",
    )

    diff_galla = counted_actual - expected_galla
    if abs(diff_galla) < 1.0:
        st.success(t("galla_balanced"))
    elif diff_galla > 0:
        st.info(f"{t('galla_surplus')} (+Rs {diff_galla:,.0f})")
    else:
        st.warning(f"{t('galla_shortage')} (-Rs {abs(diff_galla):,.0f})")

    g_note = st.text_input("Galla Reconciliation Note (optional):", placeholder="e.g. Closing cash drawer counted at 9 PM")
    if st.button(t("galla_save"), type="primary"):
        save_galla_reconciliation(
            {
                "recon_date": today.isoformat(),
                "opening_cash": opening_cash_val,
                "cash_sales": cash_summary["cash_sales"],
                "cash_repayments": cash_summary["cash_repayments"],
                "cash_expenses": cash_summary["cash_expenses"],
                "expected_cash": expected_galla,
                "actual_cash": counted_actual,
                "difference": diff_galla,
                "notes": g_note,
            },
            shop_id=active_shop,
        )
        st.toast("Galla reconciliation saved!", icon="✅")
        st.rerun()

    galla_hist_df = get_galla_history(shop_id=active_shop)
    if not galla_hist_df.empty:
        with st.expander("📜 View Past Galla Reconciliation Records"):
            st.dataframe(galla_hist_df, hide_index=True)

    st.divider()

    # 4. Plotly Charts
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
            monthly_exp["month"] = pd.to_datetime(monthly_exp["month"] + "-01", errors="coerce").dt.strftime("%b %Y")
            monthly_exp = monthly_exp.dropna(subset=["month"])
            fig_mo = px.bar(
                monthly_exp,
                x="month",
                y="amount",
                title="Expenses by Month (PKR)",
                labels={"amount": "Total PKR", "month": "Month"},
                color_discrete_sequence=["#047857"],
            )
            fig_mo.update_layout(plot_bgcolor="rgba(0,0,0,0)")
            fig_mo.update_xaxes(type="category")
            st.plotly_chart(fig_mo)
        else:
            st.info("No monthly expense data available.")

    # 4.1 Cash Sales Trend (Last 30 days)
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

    # 5. Unpaid Bills Management Table
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

    # 6. Natural Language Financial Q&A: Ask Your Hisaab
    st.markdown(f"#### 💬 Ask Your Hisaab ({model_name})")
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

    user_query = (user_query or "").strip()
    if ask_clicked and not user_query:
        st.warning("Type a question first, for example: Who owes me the most?")
    elif ask_clicked:
        with st.spinner(f"Analyzing your ledger records with {model_name}..."):
            ans_text, ans_source, ans_notice = ask_ledger(
                question=user_query,
                ledger_df=df_all,
                api_key=api_key,
                model_name=model_name,
            )
            if ans_source == "AI answer":
                st.success(f"🤖 **AI answer:**\n\n{ans_text}")
            elif ans_source == "Calculated from your ledger (offline, not AI)":
                st.info(f"📊 **Calculated from your ledger (offline, not AI):**\n\n{ans_text}")
                if ans_notice:
                    st.caption(f"AI not used: {ans_notice}")
            elif ans_source == "Error":
                st.error(f"❌ {ans_text}")
            else:
                st.warning(f"ℹ️ {ans_text}")
