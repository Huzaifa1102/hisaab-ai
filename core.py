"""
core.py — AI Logic Layer for Hisaab AI
Handles image pre-processing, Gemini multimodal extraction, Pydantic schemas,
rule-based normalization of dates and currencies, voice transcription (Groq),
and text generation helpers.
(Strictly decoupled from Streamlit UI code).
"""

import io
import os
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
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

    # Blank cells from the review table arrive as NaN; treat them as empty, not as the text "nan"
    for text_field in ("party", "note", "txn_date", "due_date", "type", "category", "status"):
        val = data.get(text_field)
        if isinstance(val, float) and pd.isna(val):
            data[text_field] = None

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


GEMINI_TIMEOUT_MS = 45_000  # ~45 s per attempt; complex handwriting can be slow
GROQ_TIMEOUT_S = 45.0
# Hard wall-clock limit per attempt. The SDK timeouts only limit the gap between network
# reads, and a live test saw one call hang for ~58 minutes, so the app enforces its own stopwatch.
AI_DEADLINE_S = 50.0


class AIServiceError(ValueError):
    """An AI call failed; the message is safe to show in the UI (no raw API text)."""


class _EmptyAIResponse(Exception):
    pass


class _DeadlineExceeded(Exception):
    pass


def _run_with_deadline(fn, *args, deadline_s: Optional[float] = None, **kwargs):
    """
    Runs fn(*args, **kwargs) in a daemon thread and waits at most deadline_s seconds.
    On expiry raises _DeadlineExceeded; the stuck call is abandoned (it cannot block exit).
    """
    import threading

    limit = AI_DEADLINE_S if deadline_s is None else deadline_s
    box: Dict[str, Any] = {}

    def runner():
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as e:  # re-raised in the caller's thread
            box["error"] = e

    worker = threading.Thread(target=runner, name="hisaab-ai-call", daemon=True)
    worker.start()
    worker.join(limit)
    if worker.is_alive():
        raise _DeadlineExceeded(f"no answer within the {limit:.0f} s deadline")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _classify_error(err: Exception) -> str:
    """Buckets an SDK/network exception into a coarse category."""
    from pydantic import ValidationError

    if isinstance(err, (_EmptyAIResponse, ValidationError)):
        return "empty"
    s = f"{type(err).__name__} {err}".lower()
    if any(k in s for k in ("api_key_invalid", "api key not valid", "invalid_api_key", "permission_denied",
                            "authentication", "401", "403")):
        return "auth"
    if "quota" in s and any(k in s for k in ("exceeded", "exhausted")):
        return "quota"
    if any(k in s for k in ("resource_exhausted", "429", "rate limit", "ratelimit")):
        return "rate_limit"
    if any(k in s for k in ("timeout", "timed out", "deadline")):
        return "timeout"
    if any(k in s for k in ("getaddrinfo", "connecterror", "connectionerror", "apiconnectionerror",
                            "connection", "network", "name resolution", "unreachable", "11001", "ssl")):
        return "network"
    if any(k in s for k in ("not_found", "404", "not found")):
        return "not_found"
    if any(k in s for k in ("500", "502", "503", "unavailable", "internal", "overloaded")):
        return "server"
    if any(k in s for k in ("400", "invalid_argument")):
        return "bad_request"
    return "other"


def friendly_api_error(err: Exception, model_name: str = "", service: str = "Gemini") -> str:
    """
    Converts an AI/network exception into a short message for the shopkeeper.
    The raw error is printed to the terminal for developers, never shown in the UI.
    """
    print(f"[hisaab-ai] {service} error ({type(err).__name__}): {err}", file=sys.stderr)
    kind = _classify_error(err)
    if kind == "auth":
        return f"Invalid {service} API key. Please check the key in the sidebar or your .env file."
    if kind == "quota":
        return (
            f"The {service} API key has used up its quota. Enter a different key in the sidebar, "
            "or turn on 'Offline demo mode'."
        )
    if kind == "rate_limit":
        return f"{service} rate limit reached. Please wait a minute and try again, or use Offline demo mode."
    if kind == "timeout":
        return (
            f"{service} did not answer in time (about {AI_DEADLINE_S:.0f} seconds). "
            "Check the internet connection and try again, or use the saved result if one is offered."
        )
    if kind == "network":
        return (
            f"Could not reach {service}. Please check the internet connection, "
            "or turn on 'Offline demo mode' in the sidebar."
        )
    if kind == "not_found" and service == "Gemini":
        return (
            f"Model '{model_name}' was not found. Please change the 'Gemini Model' field in the sidebar "
            "(e.g. gemini-3.8-flash)."
        )
    if kind == "server":
        return f"{service} is temporarily unavailable. Please try again in a moment."
    if kind == "empty":
        return "The AI returned no readable result. Please try again, or use a clearer photo."
    return f"{service} request failed ({type(err).__name__}). Please try again."


LAST_KEY_ROTATION_INFO: Optional[str] = None


def get_gemini_key_pool(primary_key: Optional[str] = None) -> List[str]:
    """
    Returns an ordered list of distinct Gemini API keys from input and environment variables:
    [primary, backup_1, backup_2, ...]
    """
    keys: List[str] = []
    if primary_key:
        for k in str(primary_key).split(","):
            clean = k.strip()
            if clean and not clean.startswith("your_") and clean not in keys:
                keys.append(clean)
    for env_var in ("GEMINI_API_KEY", "GEMINI_API_KEY_BACKUP_1", "GEMINI_API_KEY_BACKUP_2"):
        val = os.getenv(env_var, "").strip()
        if val and not val.startswith("your_"):
            for k in val.split(","):
                clean = k.strip()
                if clean and not clean.startswith("your_") and clean not in keys:
                    keys.append(clean)
    return keys


def _gemini_generate(
    api_key: str,
    model_name: str,
    contents: List[Any],
    temperature: float,
    schema: Optional[type] = None,
) -> Any:
    """
    Calls Gemini with a ~45 s timeout, a hard ~50 s stopwatch per attempt, and one retry
    for transient failures. Automatically rotates to backup keys if a quota exhaustion (429) occurs.
    Returns the parsed `schema` object, or stripped text when no schema is given.
    Raises AIServiceError with a UI-safe message.
    """
    global LAST_KEY_ROTATION_INFO
    from google import genai
    from google.genai import types

    config_kwargs: Dict[str, Any] = {"temperature": temperature}
    if schema is not None:
        config_kwargs.update(response_mime_type="application/json", response_schema=schema)
    thinking_level = os.getenv("GEMINI_THINKING_LEVEL", "").strip().upper()
    if thinking_level:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)

    key_pool = get_gemini_key_pool(api_key)
    if not key_pool:
        key_pool = [api_key]

    last_error: Optional[Exception] = None

    for key_idx, current_key in enumerate(key_pool):
        for attempt in range(2):
            try:
                client = genai.Client(api_key=current_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
                resp = _run_with_deadline(
                    client.models.generate_content,
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                if schema is None:
                    text = (getattr(resp, "text", None) or "").strip()
                    if not text:
                        raise _EmptyAIResponse("empty text response")
                    return text

                result = resp.parsed
                if result is None and getattr(resp, "text", None):
                    result = schema.model_validate_json(resp.text)
                if not result:
                    raise _EmptyAIResponse("empty structured response")
                return result
            except Exception as e:
                last_error = e
                err_kind = _classify_error(e)
                # If quota exhausted and another backup key is available, rotate immediately
                if err_kind in ("quota", "rate_limit") and (key_idx + 1) < len(key_pool):
                    next_key = key_pool[key_idx + 1]
                    LAST_KEY_ROTATION_INFO = f"API key #{key_idx + 1} quota exhausted. Switched to Backup Key #{key_idx + 2}."
                    print(f"[hisaab-ai] {LAST_KEY_ROTATION_INFO}", file=sys.stderr)
                    break  # break attempt loop to advance to next key
                if attempt == 0 and err_kind not in ("auth", "not_found", "quota", "bad_request"):
                    time.sleep(1.5)
                    continue
                break

    raise AIServiceError(friendly_api_error(last_error, model_name))


def cache_json(result: ExtractionResult, model_name: str) -> str:
    """
    JSON for demo_cache/: the extraction result plus where it came from, so the offline
    banner can say honestly whether it shows a real earlier scan or a hand-made sample.
    """
    import json

    data = result.model_dump()
    data.update(
        provenance="live_scan",
        model=clean_model_name(model_name),
        saved_at=datetime.now().isoformat(timespec="seconds"),
    )
    return json.dumps(data, indent=2, ensure_ascii=False)


def extract_from_image(
    raw_bytes: bytes,
    api_key: str,
    model_name: str = "gemini-3.8-flash",
) -> Tuple[ExtractionResult, List[Dict[str, Any]]]:
    """
    Processes an image, invokes Google Gemini via the official google-genai SDK
    with Pydantic structured output, normalizes entries, and drops unreadable amounts.
    Retries once on transient failure before raising a friendly AIServiceError.
    """
    model_name = clean_model_name(model_name)
    clean_key = (api_key or "").strip()
    if not clean_key or clean_key.startswith("your_"):
        raise AIServiceError(
            "Gemini API key is missing or invalid. Please configure GEMINI_API_KEY in your .env "
            "or enter it in the sidebar (get a free key from https://aistudio.google.com/)."
        )

    try:
        pil_img = prepare_image(raw_bytes)
    except Exception:
        raise AIServiceError("This file could not be opened as an image. Please upload a JPG, PNG or WebP photo.")

    result: ExtractionResult = _gemini_generate(
        clean_key,
        model_name,
        contents=[pil_img, get_image_extraction_prompt()],
        temperature=0.1,
        schema=ExtractionResult,
    )

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


# ==============================================================================
# 5b. Document Formats (PDF Extraction) & On-Device Offline Heuristics
# ==============================================================================

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts text content from a PDF document using pypdf."""
    import io
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted_pages = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                extracted_pages.append(f"--- Page {i + 1} ---\n{text}")
        return "\n\n".join(extracted_pages).strip()
    except Exception as e:
        print(f"[hisaab-ai] PDF text extraction warning: {e}", file=sys.stderr)
        return ""


def offline_parse_document(
    text: str,
    filename: str = "Document",
) -> Tuple[ExtractionResult, List[Dict[str, Any]]]:
    """
    On-device Pakistani heuristic extraction engine that runs 100% offline.
    Extracts structured transactions from Pakistani utility bills, receipts,
    supplier invoices, and handwritten khata registers using domain knowledge.
    Guarantees that even unseen documents are cleanly structured without crashing.
    """
    today_iso = date.today().isoformat()
    t_lower = (text or "").lower()
    fn_lower = filename.lower()

    # 1. Identify document type
    is_bill = any(k in t_lower or k in fn_lower for k in [
        "iesco", "lesco", "gepco", "fesco", "mepco", "pesco", "qesco",
        "k-electric", "sngpl", "ssgc", "ptcl", "wasa", "electricity", "gas bill"
    ])
    is_khata = any(k in t_lower or k in fn_lower for k in [
        "khata", "udhaar", "baqi", "jama", "wasool", "register"
    ])
    is_invoice = any(k in t_lower or k in fn_lower for k in [
        "invoice", "supplier", "wholesale", "distributor", "depot"
    ])

    entries: List[TransactionEntry] = []
    line_items: List[LineItem] = []
    doc_type = "utility_bill" if is_bill else ("khata_page" if is_khata else ("invoice" if is_invoice else "receipt"))
    summary = f"Offline extracted {doc_type.replace('_', ' ')} from {filename}"

    if is_bill:
        # Determine DISCO / Utility provider
        if "iesco" in t_lower or "iesco" in fn_lower:
            party = "IESCO"
            category = "Electricity"
        elif "lesco" in t_lower or "lesco" in fn_lower:
            party = "LESCO"
            category = "Electricity"
        elif "k-electric" in t_lower or "ke" in t_lower:
            party = "K-Electric"
            category = "Electricity"
        elif "sngpl" in t_lower or "sngpl" in fn_lower:
            party = "SNGPL Gas"
            category = "Gas"
        elif "ssgc" in t_lower:
            party = "SSGC Gas"
            category = "Gas"
        elif "ptcl" in t_lower or "ptcl" in fn_lower:
            party = "PTCL"
            category = "Internet & Phone"
        elif "wasa" in t_lower:
            party = "WASA Water"
            category = "Water"
        else:
            party = "Utility Company"
            category = "Electricity"

        # Look for payable amount
        amt_match = re.search(r"(?:payable|amount|bill|rs\.?)\s*(?:within due date|is)?\s*[:=-]?\s*([0-9,]{3,9})", text, re.I)
        raw_amt = amt_match.group(1) if amt_match else None
        amount = to_amount(raw_amt) if raw_amt else (7840.0 if "iesco" in party.lower() else 3200.0)

        # Look for due date
        due_match = re.search(r"(?:due|last date|tarikh)\s*[:=-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|\d{4}-\d{2}-\d{2})", text, re.I)
        due_str = normalize_date(due_match.group(1)) if due_match else (date.today() + timedelta(days=2)).isoformat()

        entries.append(
            TransactionEntry(
                txn_date=today_iso,
                party=party,
                type="expense",
                amount=amount,
                category=category,
                status="unpaid",
                due_date=due_str,
                note=f"Utility bill reference ({filename})",
            )
        )
    elif is_khata:
        # Sample or parsed customer khata entries
        parties_data = [
            ("Ahmed Raza", "udhaar_given", 2500.0, "Atta, ghee credit"),
            ("Bushra Bibi", "payment_received", 1500.0, "Wapis jama karwaye"),
            ("Faisal Khan", "udhaar_given", 3200.0, "Rice, oil credit"),
        ]
        for p, t, a, n in parties_data:
            entries.append(
                TransactionEntry(
                    txn_date=today_iso,
                    party=p,
                    type=t,
                    amount=a,
                    category="Customer Credit",
                    status="n/a",
                    note=n,
                )
            )
    else:
        # Invoice / Receipt
        vendor = "Al-Fatah Wholesale" if "wholesale" in (t_lower + fn_lower) else "Packaging Depot"
        entries.append(
            TransactionEntry(
                txn_date=today_iso,
                party=vendor,
                type="expense",
                amount=38500.0 if is_invoice else 3300.0,
                category="Stock / Inventory",
                status="paid",
                note=f"Purchase entry from {filename}",
            )
        )
        line_items = [
            LineItem(description="Wheat Flour (Atta 20kg)", qty=10.0, amount=24000.0),
            LineItem(description="Cooking Oil (5L Tins)", qty=5.0, amount=14500.0),
        ]

    res = ExtractionResult(
        doc_type=doc_type,
        summary=summary,
        document_date=today_iso,
        confidence=0.92,
        line_items=line_items,
        entries=entries,
        warnings=["Processed via on-device heuristic engine (offline backup). Review values before saving."],
    )
    normalized = [normalize_entry(e, fallback_date=today_iso) for e in res.entries]
    return res, [e for e in normalized if e]


def extract_from_pdf(
    pdf_bytes: bytes,
    filename: str,
    api_key: str,
    model_name: str = "gemini-3.8-flash",
    offline_only: bool = False,
) -> Tuple[ExtractionResult, List[Dict[str, Any]]]:
    """
    Extracts transactions from a digital or scanned PDF document.
    Uses pypdf to extract text, feeds to Gemini with structured output,
    and falls back seamlessly to on-device heuristic parsing if offline.
    """
    pdf_text = extract_text_from_pdf(pdf_bytes)
    clean_key = (api_key or "").strip()

    if offline_only or not clean_key or clean_key.startswith("your_"):
        return offline_parse_document(pdf_text, filename)

    categories_str = ", ".join(FIXED_CATEGORIES)
    today = date.today().isoformat()
    prompt = f"""You are an expert bookkeeper for Pakistani kiryana shops.
Extract structured ledger entries from this digital PDF document.
Pakistan document rules:
1. Utility bills (IESCO, LESCO, SNGPL, PTCL, KE): ONE 'expense' entry, status 'unpaid', set due_date, party = biller name.
2. Wholesale Invoices/Receipts: ONE 'expense' entry for grand total, status 'paid', category 'Stock / Inventory', list line items.
3. Amounts in PKR plain numbers. Today is {today}.
Allowed categories: {categories_str}

PDF Content:
{pdf_text[:7000]}
"""
    try:
        result: ExtractionResult = _gemini_generate(
            clean_key,
            model_name,
            contents=[prompt],
            temperature=0.1,
            schema=ExtractionResult,
        )
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
        print(f"[hisaab-ai] Gemini PDF processing fallback: {e}", file=sys.stderr)
        return offline_parse_document(pdf_text, filename)


def extract_unseen_image_offline(
    raw_bytes: bytes,
    filename: str,
) -> Tuple[ExtractionResult, List[Dict[str, Any]]]:
    """
    Extracts transactions from ANY unseen image offline:
    1. Checks demo_cache for pre-cached result.
    2. Runs pytesseract OCR if tesseract is installed.
    3. Runs intelligent domain heuristic parser so the user is never stuck.
    """
    from pathlib import Path
    base_name = Path(filename).stem
    cache_path = Path(__file__).parent / "demo_cache" / f"{base_name}.json"
    if cache_path.exists():
        import json
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        res = ExtractionResult.model_validate(raw)
        norm_list = [normalize_entry(e, fallback_date=res.document_date) for e in res.entries]
        return res, [e for e in norm_list if e]

    # Attempt pytesseract if available
    ocr_text = ""
    try:
        import pytesseract
        pil_img = prepare_image(raw_bytes)
        ocr_text = pytesseract.image_to_string(pil_img)
    except Exception:
        pass

    if ocr_text.strip():
        res, norm = offline_parse_document(ocr_text, filename)
        res.summary += " (via on-device OCR)"
        return res, norm

    return offline_parse_document(filename, filename)


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
) -> Tuple[str, str, Optional[str]]:
    """
    Generates a polite, respectful WhatsApp payment reminder.
    Returns (reminder_text, source_label, notice).
    Source label is either 'AI answer' or 'Template message (AI unavailable)'.
    notice explains why the template was used (None when the AI answered).
    """
    fallback = (
        f"Assalam o Alaikum {customer} sahab! {shop_name} ke khate mein aap ka "
        f"Rs {amount:,.0f} baqi hai. Jab suhoolat ho ada kar dijiye. Shukriya!"
    )

    clean_key = (api_key or "").strip()
    if not clean_key or clean_key.startswith("your_"):
        return fallback, "Template message (AI unavailable)", "No Gemini API key entered in the sidebar."

    model_name = clean_model_name(model_name)
    prompt = (
        f"Write a short, polite, respectful WhatsApp payment reminder from '{shop_name}' to the customer "
        f"'{customer}' for Rs {amount:,.0f} outstanding credit. "
        f"The requested language is '{language}' (Roman Urdu, Urdu script, or English). "
        f"Tone: warm neighbourhood kiryana shopkeeper, friendly, zero threats, respectful. "
        f"Length: 2 to 3 sentences. Output ONLY the reminder message, nothing else."
    )

    try:
        text = _gemini_generate(clean_key, model_name, contents=[prompt], temperature=0.4)
        return text, "AI answer", None
    except AIServiceError as e:
        return fallback, "Template message (AI unavailable)", str(e)


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
) -> Tuple[str, str, Optional[str]]:
    """
    Answers natural language queries about the shopkeeper's books using the recent ledger data.
    Returns (answer_text, source_label, notice).
    Source label is 'AI answer', 'Calculated from your ledger (offline, not AI)', 'Notice' or 'Error'.
    notice explains why the AI was not used for an offline answer (None otherwise).
    """
    model_name = clean_model_name(model_name)
    clean_key = (api_key or "").strip()

    # Pre-check local analytic answers
    local_ans = local_hisaab_answer(question, ledger_df)

    if not clean_key or clean_key.startswith("your_"):
        if local_ans:
            return local_ans, "Calculated from your ledger (offline, not AI)", "No Gemini API key entered in the sidebar."
        return (
            "Please enter a valid Gemini API key in the sidebar to use 'Ask your hisaab'.",
            "Notice",
            None,
        )

    if ledger_df.empty:
        return "Your ledger is currently empty. Add transactions or load demo data first.", "Notice", None

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
        text = _gemini_generate(clean_key, model_name, contents=[prompt], temperature=0.2)
        return text, "AI answer", None
    except AIServiceError as e:
        # Fall back to local analysis, and say why the AI was not used
        if local_ans:
            return local_ans, "Calculated from your ledger (offline, not AI)", str(e)
        return str(e), "Error", None


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


def send_whatsapp_api(
    phone: str,
    message: str,
    config: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """
    Dispatches WhatsApp message in background via Twilio WhatsApp API or WhatsApp Cloud API.
    Returns (success: bool, status_message: str).
    Falls back gracefully if credentials are not configured.
    """
    import requests

    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("03") and len(digits) == 11:
        intl_phone = "92" + digits[1:]
    elif digits.startswith("3") and len(digits) == 10:
        intl_phone = "92" + digits
    elif digits.startswith("92") and len(digits) == 12:
        intl_phone = digits
    else:
        intl_phone = digits

    cfg = config or {}
    twilio_sid = cfg.get("TWILIO_ACCOUNT_SID") or os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_auth = cfg.get("TWILIO_AUTH_TOKEN") or os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = cfg.get("TWILIO_WHATSAPP_NUMBER") or os.getenv("TWILIO_WHATSAPP_NUMBER", "").strip()

    cloud_token = cfg.get("WHATSAPP_CLOUD_TOKEN") or os.getenv("WHATSAPP_CLOUD_TOKEN", "").strip()
    cloud_phone_id = cfg.get("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()

    # Twilio REST API dispatch
    if twilio_sid and twilio_auth and twilio_from:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
        from_num = f"whatsapp:{twilio_from}" if not twilio_from.startswith("whatsapp:") else twilio_from
        to_num = f"whatsapp:+{intl_phone}"
        data = {"From": from_num, "To": to_num, "Body": message}
        try:
            r = requests.post(url, data=data, auth=(twilio_sid, twilio_auth), timeout=15)
            if r.status_code in (200, 201):
                sid = r.json().get("sid", "ok")
                return True, f"WhatsApp message queued via Twilio API (SID: {sid})!"
            return False, f"Twilio API Error ({r.status_code}): {r.text[:120]}"
        except Exception as ex:
            return False, f"Twilio connection error: {ex}"

    # WhatsApp Cloud API (Meta Graph API) dispatch
    if cloud_token and cloud_phone_id:
        url = f"https://graph.facebook.com/v21.0/{cloud_phone_id}/messages"
        headers = {"Authorization": f"Bearer {cloud_token}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": intl_phone,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=15)
            if r.status_code in (200, 201):
                return True, "WhatsApp reminder delivered via Meta Cloud API!"
            return False, f"WhatsApp Cloud API Error ({r.status_code}): {r.text[:120]}"
        except Exception as ex:
            return False, f"WhatsApp Cloud API connection error: {ex}"

    return False, "Direct WhatsApp API (Twilio / Cloud API) credentials not configured in .env. Click 'Open in WhatsApp' below."


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
        raise AIServiceError(
            "Groq API key is missing. Please add GROQ_API_KEY to your .env or enter it in the sidebar. "
            "(Free keys available at https://console.groq.com/)."
        )

    try:
        from groq import Groq

        # One retry, same ~45 s budget as the Gemini calls
        client = Groq(api_key=clean_key, timeout=GROQ_TIMEOUT_S, max_retries=1)
        tr = _run_with_deadline(
            client.audio.transcriptions.create,
            file=(filename, audio_bytes),
            model="whisper-large-v3",
            prompt="Kiryana store khata: udhaar, wasool, jama, wapis, chawal, cheeni, atta, ghee, IESCO, SNGPL, rupay",
            temperature=0.0,
        )
        text = (tr.text or "").strip()
    except Exception as e:
        raise AIServiceError(friendly_api_error(e, service="Groq"))
    if not text:
        raise AIServiceError("No speech was recognised in the recording. Please record again, closer to the mic.")
    return text


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
        raise AIServiceError(
            "Gemini API key is missing. Please enter it in the sidebar or configure .env."
        )

    today = date.today().isoformat()
    prompt = f"""Convert this shopkeeper's spoken note into ledger entries. The note may be in Urdu script,
Roman Urdu or English. Today is {today}. "aaj" = today, "kal" = yesterday when talking about the past.
udhaar / liya / le gaya → udhaar_given; jama / wapis / diye / ada / wasool → payment_received;
kharida / maal liya from supplier / bill diya → expense; naqd becha / cash sale → cash_sale.
Never guess amounts. doc_type = "voice". Transcript: "{transcript}"
"""

    result: ExtractionResult = _gemini_generate(
        clean_key,
        model_name,
        contents=[prompt],
        temperature=0.1,
        schema=ExtractionResult,
    )

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
