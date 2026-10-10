"""
core.py — AI Logic Layer for Hisaab AI
Handles image pre-processing, Gemini multimodal extraction, Pydantic schemas,
rule-based normalization of dates and currencies, voice transcription (Groq),
and text generation helpers.
(Strictly decoupled from Streamlit UI code).
"""

import io
import re
import time
import urllib.parse
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from db import ALLOWED_TYPES, FIXED_CATEGORIES

# ==============================================================================
# 1. Pydantic Schemas (Structured Output for Vision & Voice)
# ==============================================================================


class LineItem(BaseModel):
    description: str
    qty: Optional[float] = None
    amount: Optional[float] = None


class TransactionEntry(BaseModel):
    txn_date: Optional[str] = Field(None, description="YYYY-MM-DD, or null if no date is visible")
    party: str = Field(description="Customer, supplier or biller name in Roman Urdu/English")
    type: str = Field(description="expense | udhaar_given | payment_received | cash_sale")
    amount: Optional[float] = Field(None, description="PKR. Null if unreadable. NEVER guess.")
    category: str
    status: str = Field(description="paid | unpaid | n/a")
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD for bills, else null")
    note: str = ""


class ExtractionResult(BaseModel):
    doc_type: str = Field(description="receipt | invoice | utility_bill | khata_page | other")
    summary: str
    document_date: Optional[str] = None
    confidence: float = Field(description="0.0 to 1.0, overall reading confidence")
    line_items: List[LineItem] = []
    entries: List[TransactionEntry]
    warnings: List[str] = []


# ==============================================================================
# 2. Image Preparation (EXIF orientation fix + Downscaling)
# ==============================================================================


def prepare_image(raw_bytes: bytes) -> Image.Image:
    """
    Opens raw image bytes, applies EXIF transpose to fix mobile orientation,
    converts to RGB, and downscales if the longest side exceeds 1800 px.
    """
    img = Image.open(io.BytesIO(raw_bytes))
    # Correct orientation metadata from phone cameras
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    max_dim = 1800
    width, height = img.size
    longest = max(width, height)
    if longest > max_dim:
        scale = max_dim / float(longest)
        new_width = int(round(width * scale))
        new_height = int(round(height * scale))
        resample_mode = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize((new_width, new_height), resample=resample_mode)

    return img


# ==============================================================================
# 3. Currency and Date Normalization
# ==============================================================================

# Urdu & Arabic-Indic digit translation tables
URDU_DIGITS = {
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
}

ARABIC_INDIC_DIGITS = {
    "٠": "0",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
}


def to_amount(val: Any) -> Optional[float]:
    """
    Parses numbers or strings representing currency.
    Converts Urdu and Arabic digits, strips 'Rs', commas, '/-', and returns a float.
    Returns None if empty, unparseable, NaN, or <= 0.
    """
    if val is None:
        return None

    if isinstance(val, (int, float)):
        if pd.isna(val) or val <= 0:
            return None
        return float(val)

    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None

    # Replace Urdu and Arabic-Indic numerals
    for u_char, d_char in URDU_DIGITS.items():
        s = s.replace(u_char, d_char)
    for a_char, d_char in ARABIC_INDIC_DIGITS.items():
        s = s.replace(a_char, d_char)

    # Remove common Pakistani currency prefixes & suffixes: Rs, /-, PKR, etc.
    s = re.sub(r"(?i)rs\.?|pkr|/-|=|/|\brup(ay|ee|ees)\b", "", s)
    # Remove commas and whitespaces
    s = s.replace(",", "").strip()

    # Extract digits with optional decimal point
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if not match:
        return None

    try:
        amt = float(match.group(0))
        return amt if amt > 0 else None
    except (ValueError, TypeError):
        return None


def normalize_date(val: Any, fallback_date: Optional[str] = None) -> Optional[str]:
    """
    Normalizes a date input to 'YYYY-MM-DD'.
    Accepts:
    - YYYY-MM-DD
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - DD/MM/YY
    - English named dates: '08 Oct 2026', '8 October 2026', etc.
    - Python date/datetime objects.
    Falls back to fallback_date or today's date if unparseable.
    """
    today_iso = date.today().isoformat()
    if val is None or str(val).strip().lower() in ("none", "null", "nan", ""):
        return fallback_date if fallback_date else today_iso

    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")

    s = str(val).strip()

    # Direct match for YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # Parse common date formats
    date_formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(s, fmt)
            # Handle 2-digit years if needed
            if dt.year < 2000:
                dt = dt.replace(year=dt.year + 100)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Try dateutil parser if available as secondary fallback
    try:
        from dateutil import parser as dt_parser

        dt = dt_parser.parse(s, dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return fallback_date if fallback_date else today_iso


def normalize_entry(entry: Any, fallback_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Normalizes an entry dictionary or TransactionEntry instance according to Hisaab AI rules.
    - Drops the entry if amount is null or <= 0 (returns None).
    - Ensures party casing preserves acronyms (e.g., 'IESCO' stays uppercase).
    - Enforces fixed categories and valid transaction types.
    - Sets correct status rules (expenses get 'paid'/'unpaid'; all others get 'n/a').
    """
    if hasattr(entry, "model_dump"):
        data = entry.model_dump()
    elif isinstance(entry, dict):
        data = dict(entry)
    else:
        return None

    # Amount validation: drop entry if unreadable/zero
    amount = to_amount(data.get("amount"))
    if amount is None or amount <= 0:
        return None

    # Party normalization
    party = str(data.get("party") or "").strip()
    if not party:
        party = "Unknown"
    elif party.islower():
        party = party.title()

    # Type validation
    txn_type = str(data.get("type") or "expense").strip().lower()
    if txn_type not in ALLOWED_TYPES:
        txn_type = "expense"

    # Category normalization
    category = str(data.get("category") or "").strip()
    if category not in FIXED_CATEGORIES:
        if txn_type in ("udhaar_given", "payment_received"):
            category = "Customer Credit"
        elif txn_type == "cash_sale":
            category = "Sales"
        else:
            category = "Other"

    # Status normalization
    raw_status = str(data.get("status") or "").strip().lower()
    if txn_type == "expense":
        status = "unpaid" if raw_status == "unpaid" else "paid"
    else:
        status = "n/a"

    # Date normalization
    txn_date = normalize_date(data.get("txn_date"), fallback_date=fallback_date)

    # Due date normalization for unpaid expenses
    due_date = None
    if txn_type == "expense" and status == "unpaid":
        raw_due = data.get("due_date")
        if raw_due:
            due_date = normalize_date(raw_due, fallback_date=None)

    note = str(data.get("note") or "").strip()

    return {
        "txn_date": txn_date,
        "party": party,
        "type": txn_type,
        "amount": amount,
        "category": category,
        "status": status,
        "due_date": due_date,
        "note": note,
    }


# ==============================================================================
# 4. Prompt Generation
# ==============================================================================


def get_image_extraction_prompt() -> str:
    """Builds the system prompt with current dates and allowed categories."""
    today = date.today().isoformat()
    year = date.today().year
    categories_str = ", ".join(FIXED_CATEGORIES)

    return f"""You are an expert bookkeeper for small shops (kiryana stores) in Pakistan.
Read the image and extract ledger entries.

The image can be:
- receipt / invoice: printed or handwritten purchase receipt or supplier invoice (English or Urdu)
- utility_bill: IESCO, LESCO, K-Electric or other DISCO, SNGPL, SSGC, PTCL/internet, water bill
- khata_page: handwritten udhaar register page (Urdu, Roman Urdu or English; may use Urdu digits ۰۱۲۳۴۵۶۷۸۹)
- other

Rules:
1. Amounts are PKR plain numbers. Convert Urdu digits to English digits. Remove "Rs", commas, "/-".
2. receipt/invoice: ONE "expense" entry for the grand total; party = vendor/supplier; status "paid";
   best category (goods for resale = "Stock / Inventory"). List products in line_items, translating
   Urdu/Roman Urdu item names to English (cheeni → Sugar, chawal → Rice, ghee → Cooking Oil/Ghee).
3. utility_bill: ONE "expense" entry; amount = payable within due date; set due_date;
   category Electricity / Gas / Water / Internet & Phone; status "unpaid" unless a PAID stamp or
   payment proof is visible; party = company name (e.g. "IESCO").
4. khata_page: one entry per customer line.
   - took goods/money on credit (udhaar, liye, le gaya, baqi, ادھار, لیے) → "udhaar_given"
   - paid back (jama, wapis, wasool, ada, diye, جمع, ادا) → "payment_received"
   - category "Customer Credit", status "n/a", party = customer name in Roman Urdu/English.
   - Skip lines that are only running totals or balances and mention them in warnings.
   - If a line records a cash sale (naqd, cash), use "cash_sale" with category "Sales".
5. Dates are written DD/MM/YYYY in Pakistan. If the year is missing assume {year}. Today is {today}.
   Use null if no date is visible.
6. NEVER invent or guess an amount. If unreadable, set amount to null and add a warning.
7. Allowed categories: {categories_str}
"""


# ==============================================================================
# 5. Multimodal Extraction via Google GenAI SDK
# ==============================================================================


def clean_model_name(model_name: Optional[str]) -> str:
    """
    Trims whitespace and strips any leading 'models/' prefix without rewriting the name.
    Strictly respects the user's chosen model in the sidebar.
    """
    if not model_name:
        return "gemini-3.8-flash"
    m = str(model_name).strip()
    if m.startswith("models/"):
        m = m[7:]
    return m or "gemini-3.8-flash"

# Backwards compatibility alias
resolve_model_name = clean_model_name


def extract_from_image(
    raw_bytes: bytes,
    api_key: str,
    model_name: str = "gemini-3.8-flash",
) -> Tuple[ExtractionResult, List[Dict[str, Any]]]:
    """
    Processes an image, invokes Google Gemini via the official google-genai SDK
    with Pydantic structured output, normalizes entries, and drops unreadable amounts.
    Retries once on failure before raising a friendly human-readable exception.
    """
    model_name = clean_model_name(model_name)
    clean_key = (api_key or "").strip()
    if not clean_key or clean_key.startswith("your_"):
        raise ValueError(
            "Gemini API key is missing or invalid. Please configure GEMINI_API_KEY in your .env "
            "or enter it in the sidebar (get a free key from https://aistudio.google.com/)."
        )

    from google import genai
    from google.genai import types

    pil_img = prepare_image(raw_bytes)
    prompt_text = get_image_extraction_prompt()

    # Configure client with 45-second timeout as required for complex handwriting
    client = genai.Client(api_key=clean_key, http_options=types.HttpOptions(timeout=45_000))

    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[pil_img, prompt_text],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=ExtractionResult,
                ),
            )

            # Check parsed Pydantic object, fallback to json validation if needed
            result: Optional[ExtractionResult] = resp.parsed
            if result is None and getattr(resp, "text", None):
                result = ExtractionResult.model_validate_json(resp.text)

            if not result:
                raise ValueError("Model returned an empty response. Please retry with a clearer photo.")

            # Normalization phase
            normalized_entries: List[Dict[str, Any]] = []
            for entry in result.entries:
                norm = normalize_entry(entry, fallback_date=result.document_date)
                if norm is not None:
                    normalized_entries.append(norm)
                else:
                    party_label = entry.party or "unnamed party"
                    warning_msg = f"Entry for '{party_label}' skipped: amount unreadable"
                    if warning_msg not in result.warnings:
                        result.warnings.append(warning_msg)

            return result, normalized_entries

        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(1.5)  # brief pause before retry

    # Human-readable error translation
    err_str = str(last_error)
    if "API_KEY_INVALID" in err_str or "API key not valid" in err_str or "401" in err_str:
        raise ValueError("Invalid Gemini API Key. Please verify your key on Google AI Studio.")
    elif "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
        raise ValueError("Gemini API rate limit exceeded. Please wait a few moments or switch to offline demo mode.")
    elif "NOT_FOUND" in err_str or "404" in err_str or "not found" in err_str.lower():
        raise ValueError(
            f"Model '{model_name}' was not found. Please change the model name in the sidebar (e.g. gemini-3.8-flash). API Error details: {err_str}"
        )
    elif "timeout" in err_str.lower() or "deadline" in err_str.lower():
        raise ValueError("Gemini request timed out after 45s. Please check your network connection or try a smaller image.")
    else:
        raise RuntimeError(f"AI Extraction failed: {err_str}")


# ==============================================================================
# 6. Text AI Helpers (WhatsApp Reminder & Ask Your Hisaab)
# ==============================================================================


def draft_reminder(
    shop_name: str,
    customer: str,
    amount: float,
    language: str,
    api_key: str,
    model_name: str = "gemini-3.8-flash",
) -> Tuple[str, str]:
    """
    Generates a polite, respectful WhatsApp payment reminder.
    Returns (reminder_text, source_label).
    Source label is either 'AI answer' or 'Template message (AI unavailable)'.
    """
    fallback = (
        f"Assalam o Alaikum {customer} sahab! {shop_name} ke khate mein aap ka "
        f"Rs {amount:,.0f} baqi hai. Jab suhoolat ho ada kar dijiye. Shukriya!"
    )

    clean_key = (api_key or "").strip()
    if not clean_key or clean_key.startswith("your_"):
        return fallback, "Template message (AI unavailable)"

    model_name = clean_model_name(model_name)
    prompt = (
        f"Write a short, polite, respectful WhatsApp payment reminder from '{shop_name}' to the customer "
        f"'{customer}' for Rs {amount:,.0f} outstanding credit. "
        f"The requested language is '{language}' (Roman Urdu, Urdu script, or English). "
        f"Tone: warm neighbourhood kiryana shopkeeper, friendly, zero threats, respectful. "
        f"Length: 2 to 3 sentences. Output ONLY the reminder message, nothing else."
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=clean_key, http_options=types.HttpOptions(timeout=15_000))
        resp = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.4,
            ),
        )
        if resp and resp.text:
            return resp.text.strip(), "AI answer"
    except Exception:
        pass

    return fallback, "Template message (AI unavailable)"


def local_hisaab_answer(question: str, ledger_df: pd.DataFrame) -> Optional[str]:
    """
    Zero-cost local query answering engine without API calls.
    Directly computes answers for customer debts, expenses, utilities, and sales.
    """
    if ledger_df.empty:
        return "Aap ka ledger khali hai. Pehle transactions darj karein ya demo data load karein."

    q = question.lower().strip()

    # Query 1: Top debtor / Who owes me the most
    if any(k in q for k in ["who owes", "owes me", "most", "sab se zyada udhaar", "zyada baqi", "top debtor", "highest balance", "udhaar kiska"]):
        cust_df = ledger_df[ledger_df["type"].isin(["udhaar_given", "payment_received"])]
        if cust_df.empty:
            return "Khate mein filhal kisi customer ka udhaar darj nahi hai."

        balances: Dict[str, float] = {}
        display_names: Dict[str, str] = {}
        for _, row in cust_df.iterrows():
            party = str(row.get("party") or "Unknown").strip()
            p_key = party.lower()
            display_names[p_key] = party
            amt = float(row.get("amount") or 0.0)
            if row.get("type") == "udhaar_given":
                balances[p_key] = balances.get(p_key, 0.0) + amt
            elif row.get("type") == "payment_received":
                balances[p_key] = balances.get(p_key, 0.0) - amt

        positive_bals = {k: v for k, v in balances.items() if v > 0}
        if not positive_bals:
            return "Tamam customers ka hisaab clear hai! Kisi par udhaar baqi nahi hai."

        top_key = max(positive_bals, key=positive_bals.get)
        top_name = display_names[top_key]
        top_amt = positive_bals[top_key]
        total_outstanding = sum(positive_bals.values())
        return (
            f"Sab se zyada udhaar **{top_name}** ka hai: **Rs {top_amt:,.0f}**.\n\n"
            f"(Kul {len(positive_bals)} customers par kul **Rs {total_outstanding:,.0f}** udhaar baqi hai)."
        )

    # Query 2: Electricity / Utilities spending
    if any(k in q for k in ["bijli", "electricity", "iesco"]):
        elec_df = ledger_df[(ledger_df["type"] == "expense") & (ledger_df["category"].str.contains("Electricity", case=False, na=False))]
        total = elec_df["amount"].sum()
        return f"Bijli (Electricity / IESCO) par kul kharcha **Rs {total:,.0f}** record hua hai."

    # Query 3: Total Expenses
    if any(k in q for k in ["kharcha", "spending", "total expense", "expenses", "total kharch"]):
        exp_df = ledger_df[ledger_df["type"] == "expense"]
        total = exp_df["amount"].sum()
        return f"Aap ke total record shuda ikhrajat (expenses) **Rs {total:,.0f}** hain."

    # Query 4: Cash sales
    if any(k in q for k in ["cash sale", "naqd", "kamai", "sales", "bikri"]):
        sales_df = ledger_df[ledger_df["type"] == "cash_sale"]
        total = sales_df["amount"].sum()
        return f"Aap ki record shuda counter cash sales **Rs {total:,.0f}** hain."

    return None


def ask_ledger(
    question: str,
    ledger_df: pd.DataFrame,
    api_key: str,
    model_name: str = "gemini-3.8-flash",
) -> Tuple[str, str]:
    """
    Answers natural language queries about the shopkeeper's books using the recent ledger data.
    Returns (answer_text, source_label).
    Source label is either 'AI answer' or 'Calculated from your ledger (offline, not AI)'.
    """
    model_name = clean_model_name(model_name)
    clean_key = (api_key or "").strip()

    # Pre-check local analytic answers
    local_ans = local_hisaab_answer(question, ledger_df)

    if not clean_key or clean_key.startswith("your_"):
        if local_ans:
            return local_ans, "Calculated from your ledger (offline, not AI)"
        return (
            "Please enter a valid Gemini API key in the sidebar to use 'Ask your hisaab'.",
            "Notice",
        )

    if ledger_df.empty:
        return "Your ledger is currently empty. Add transactions or load demo data first.", "Notice"

    # Take recent 300 rows and convert to concise CSV
    recent_slice = ledger_df.head(300)[
        ["txn_date", "party", "type", "amount", "category", "status", "due_date", "note"]
    ]
    csv_data = recent_slice.to_csv(index=False)

    prompt = f"""You are the intelligent financial assistant for a Pakistani kiryana store.
The shopkeeper is asking: "{question}"

Here are the latest ledger entries in CSV format:
{csv_data}

Rules:
1. For customer credit, balance = sum(udhaar_given) - sum(payment_received).
2. Answer strictly based on the provided ledger data. Show key numbers and amounts in PKR.
3. If the data does not contain the answer, politely say so.
4. Reply in the exact same language/script the user asked in (Urdu, Roman Urdu, or English).
5. Keep your answer concise (2-4 sentences max).
"""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=clean_key, http_options=types.HttpOptions(timeout=20_000))
        resp = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )
        if resp and resp.text:
            return resp.text.strip(), "AI answer"
        if local_ans:
            return local_ans, "Calculated from your ledger (offline, not AI)"
        return "No answer could be generated. Please rephrase your question.", "Notice"
    except Exception as e:
        # Fall back gracefully to local analysis rather than displaying raw API error
        if local_ans:
            return local_ans, "Calculated from your ledger (offline, not AI)"
        err_msg = str(e)
        if "NOT_FOUND" in err_msg or "404" in err_msg or "not found" in err_msg.lower():
            return (
                f"Model '{model_name}' was not found. Please change the model name in the sidebar (e.g. gemini-3.8-flash). API Error details: {err_msg}",
                "Model Error",
            )
        return f"Could not answer hisaab query via AI: {err_msg}", "Error"


def whatsapp_link(phone: Optional[str], message: str) -> Optional[str]:
    """
    Converts a Pakistani phone number (e.g., 03001234567) into an international WhatsApp link:
    https://wa.me/923XXXXXXXXX?text=...
    Returns None if no valid phone number is supplied.
    """
    if not phone:
        return None

    digits = re.sub(r"\D", "", str(phone))
    if not digits:
        return None

    # Handle standard Pakistani prefixes
    if digits.startswith("03") and len(digits) == 11:
        digits = "92" + digits[1:]
    elif digits.startswith("3") and len(digits) == 10:
        digits = "92" + digits
    elif digits.startswith("92") and len(digits) == 12:
        pass
    else:
        # Check if length is plausible international
        if len(digits) < 10:
            return None

    encoded_msg = urllib.parse.quote(message)
    return f"https://wa.me/{digits}?text={encoded_msg}"


# ==============================================================================
# 7. Phase 2 Voice Khata Logic (Groq Whisper + Text Extraction)
# ==============================================================================


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    groq_key: str,
) -> str:
    """
    Transcribes Urdu / Roman Urdu speech using Groq's high-speed Whisper-large-v3 API.
    """
    clean_key = (groq_key or "").strip()
    if not clean_key or clean_key.startswith("your_"):
        raise ValueError(
            "Groq API key is missing. Please add GROQ_API_KEY to your .env or enter it in the sidebar. "
            "(Free keys available at https://console.groq.com/)."
        )

    from groq import Groq

    client = Groq(api_key=clean_key)
    try:
        tr = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3",
            prompt="Kiryana store khata: udhaar, wasool, jama, wapis, chawal, cheeni, atta, ghee, IESCO, SNGPL, rupay",
            temperature=0.0,
        )
        return tr.text.strip()
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg or "invalid_api_key" in err_msg:
            raise ValueError("Invalid Groq API Key. Please verify your key on console.groq.com.")
        raise RuntimeError(f"Voice transcription failed: {err_msg}")


def extract_from_text(
    transcript: str,
    api_key: str,
    model_name: str = "gemini-3.8-flash",
) -> Tuple[ExtractionResult, List[Dict[str, Any]]]:
    """
    Converts transcribed shopkeeper speech into structured ledger entries using Gemini.
    Normalizes amounts, dates, and types identically to image extractions.
    """
    model_name = resolve_model_name(model_name)
    clean_key = (api_key or "").strip()
    if not clean_key or clean_key.startswith("your_"):
        raise ValueError(
            "Gemini API key is missing. Please enter it in the sidebar or configure .env."
        )

    today = date.today().isoformat()
    prompt = f"""Convert this shopkeeper's spoken note into ledger entries. The note may be in Urdu script,
Roman Urdu or English. Today is {today}. "aaj" = today, "kal" = yesterday when talking about the past.
udhaar / liya / le gaya → udhaar_given; jama / wapis / diye / ada / wasool → payment_received;
kharida / maal liya from supplier / bill diya → expense; naqd becha / cash sale → cash_sale.
Never guess amounts. doc_type = "voice". Transcript: "{transcript}"
"""

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=clean_key, http_options=types.HttpOptions(timeout=30_000))
    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            ),
        )

        result: Optional[ExtractionResult] = resp.parsed
        if result is None and getattr(resp, "text", None):
            result = ExtractionResult.model_validate_json(resp.text)

        if not result:
            raise ValueError("Model could not parse any transactions from the voice note.")

        normalized_entries: List[Dict[str, Any]] = []
        for entry in result.entries:
            norm = normalize_entry(entry, fallback_date=today)
            if norm is not None:
                normalized_entries.append(norm)
            else:
                party_label = entry.party or "unnamed party"
                warning_msg = f"Voice entry for '{party_label}' skipped: amount unreadable"
                if warning_msg not in result.warnings:
                    result.warnings.append(warning_msg)

        return result, normalized_entries
    except Exception as e:
        err_msg = str(e)
        if "API_KEY_INVALID" in err_msg or "401" in err_msg:
            raise ValueError("Invalid Gemini API Key. Please verify your key on Google AI Studio.")
        elif "NOT_FOUND" in err_msg or "404" in err_msg or "not found" in err_msg.lower():
            raise ValueError(
                f"Model '{model_name}' was not found. Please change the model name in the sidebar (e.g. gemini-3.8-flash). API Error details: {err_msg}"
            )
        raise RuntimeError(f"Voice extraction failed: {err_msg}")
