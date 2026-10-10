"""
test_voice_and_offline.py — Phase 2 verification:
1. Mocks Gemini output for extract_from_text and verifies full normalization pipeline.
2. Verifies offline demo mode extraction against all files in demo_cache/.
3. Verifies customer khata balance logic, debt metrics, and duplicate detection.
"""

from unittest.mock import MagicMock, patch
from pathlib import Path
import json
import os
import tempfile

# Use a throwaway database so running tests never wipes the real hisaab.db
os.environ["HISAAB_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_hisaab.db")

from core import (
    ExtractionResult,
    TransactionEntry,
    LineItem,
    extract_from_text,
    normalize_entry,
)
from db import (
    seed_demo_data,
    get_customer_balances,
    get_all_transactions,
    find_duplicates,
    get_unpaid_bills,
    mark_paid,
)

def test_extract_from_text_mocked():
    print("Testing extract_from_text with mock Gemini response...")
    mock_result = ExtractionResult(
        doc_type="voice",
        summary="Customer Ahmed Raza took 500 PKR worth of atta on credit.",
        document_date="2026-10-10",
        confidence=0.98,
        line_items=[],
        entries=[
            TransactionEntry(
                txn_date="2026-10-10",
                party="Ahmed Raza",
                type="udhaar_given",
                amount=500.0,
                category="Customer Credit",
                status="n/a",
                due_date=None,
                note="atta udhaar liya"
            ),
            # Also test an unreadable entry that should be dropped
            TransactionEntry(
                txn_date="2026-10-10",
                party="Unknown Person",
                type="udhaar_given",
                amount=None,  # unreadable amount
                category="Customer Credit",
                status="n/a",
                due_date=None,
                note="unreadable amount"
            )
        ],
        warnings=[]
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.parsed = mock_result
        mock_client.models.generate_content.return_value = mock_response

        res, norm_entries = extract_from_text(
            transcript="Ahmed ne 500 rupay ka atta udhaar liya",
            api_key="mock_test_key",
            model_name="gemini-2.5-flash"
        )

        assert res.doc_type == "voice"
        assert len(norm_entries) == 1, f"Expected 1 normalized entry (unreadable dropped), got {len(norm_entries)}"
        assert norm_entries[0]["party"] == "Ahmed Raza"
        assert norm_entries[0]["amount"] == 500.0
        assert norm_entries[0]["type"] == "udhaar_given"
        assert any("skipped: amount unreadable" in w for w in res.warnings), "Expected unreadable amount warning"

    print("Passed: extract_from_text mock test passed!")

def test_demo_cache_files():
    print("Testing all demo_cache JSON files for schema validity...")
    cache_dir = Path(__file__).parent / "demo_cache"
    # Cache files come from real scans (test_live_images.py), so any number may exist and a real
    # result may contain entries with unreadable (null) amounts. Each file must still load cleanly.
    json_files = list(cache_dir.glob("*.json"))
    if not json_files:
        print("  (no demo cache files yet; run test_live_images.py with a real key to create them)")

    for jf in json_files:
        content = jf.read_text(encoding="utf-8")
        parsed = ExtractionResult.model_validate_json(content)
        assert 0.0 <= parsed.confidence <= 1.0, f"{jf.name}: confidence out of range"
        for e in parsed.entries:
            norm = normalize_entry(e, fallback_date=parsed.document_date)
            if norm is None:
                continue  # unreadable amount: the app drops it with a warning
            assert norm["amount"] > 0
            assert norm["party"]
            assert norm["type"] in ("expense", "udhaar_given", "payment_received", "cash_sale")
    print(f"Passed: All {len(json_files)} demo cache files validated successfully!")

def test_db_logic():
    print("Testing DB seed, balance calculations, duplicate detection, and mark_paid...")
    seed_demo_data()
    df = get_all_transactions()
    assert len(df) >= 20

    # Balances
    bals = get_customer_balances()
    assert not bals.empty
    ahmed_row = bals[bals["party"] == "Ahmed Raza"]
    assert not ahmed_row.empty
    # Ahmed: 4500 udhaar - 2000 paid = 2500 balance
    assert ahmed_row.iloc[0]["balance"] == 2500.0

    # Unpaid bills
    unpaid = get_unpaid_bills()
    assert len(unpaid) >= 2
    iesco_row = unpaid[unpaid["party"] == "IESCO"]
    assert not iesco_row.empty
    iesco_id = int(iesco_row.iloc[0]["id"])

    # Mark paid
    mark_paid(iesco_id)
    unpaid_after = get_unpaid_bills()
    assert iesco_id not in unpaid_after["id"].values

    # Duplicate detection
    dup_test = [{
        "party": "Metro Cash & Carry",
        "amount": 42500.0,
        "txn_date": df[df["party"] == "Metro Cash & Carry"].iloc[0]["txn_date"],
    }]
    dups = find_duplicates(dup_test)
    assert len(dups) == 1
    assert dups[0]["party"] == "Metro Cash & Carry"

    print("Passed: All DB business logic tests passed!")

if __name__ == "__main__":
    test_extract_from_text_mocked()
    test_demo_cache_files()
    test_db_logic()
    print("ALL PHASE 2 AND BUSINESS LOGIC TESTS PASSED!")
