"""
test_normalization.py — Verifies normalization edge cases required by Phase 1 check:
1. "Rs 1,250/-" -> 1250.0
2. "۱۲۵۰" -> 1250.0
3. "08/10/2026" -> "2026-10-08"
4. Entry with amount None -> dropped (returns None)
5. "IESCO" -> preserves casing
6. Invalid type -> coerced to "expense"
"""

from core import to_amount, normalize_date, normalize_entry, TransactionEntry

def run_tests():
    # 1. Currency with prefixes and suffixes
    amt1 = to_amount("Rs 1,250/-")
    assert amt1 == 1250.0, f"Expected 1250.0, got {amt1}"

    # 2. Urdu digits
    amt2 = to_amount("۱۲۵۰")
    assert amt2 == 1250.0, f"Expected 1250.0, got {amt2}"

    # Arabic-Indic digits
    amt_ar = to_amount("٥٤٠")
    assert amt_ar == 540.0, f"Expected 540.0, got {amt_ar}"

    # 3. Date normalization
    d1 = normalize_date("08/10/2026")
    assert d1 == "2026-10-08", f"Expected 2026-10-08, got {d1}"

    d2 = normalize_date("08 Oct 2026")
    assert d2 == "2026-10-08", f"Expected 2026-10-08, got {d2}"

    # 4. Entry with amount None -> must be dropped
    entry_none = {
        "txn_date": "2026-10-08",
        "party": "Ahmed",
        "type": "udhaar_given",
        "amount": None,
        "category": "Customer Credit",
        "status": "n/a",
    }
    res_none = normalize_entry(entry_none)
    assert res_none is None, f"Expected None for null amount, got {res_none}"

    entry_zero = {
        "txn_date": "2026-10-08",
        "party": "Ahmed",
        "type": "udhaar_given",
        "amount": 0,
        "category": "Customer Credit",
        "status": "n/a",
    }
    assert normalize_entry(entry_zero) is None, "Expected None for 0 amount"

    # 5. Casing preservation for abbreviations like IESCO
    entry_iesco = {
        "txn_date": "2026-10-08",
        "party": "IESCO",
        "type": "expense",
        "amount": 7840.0,
        "category": "Electricity",
        "status": "unpaid",
    }
    res_iesco = normalize_entry(entry_iesco)
    assert res_iesco is not None
    assert res_iesco["party"] == "IESCO", f"Expected 'IESCO', got {res_iesco['party']}"

    # Lowercase names should be title-cased
    entry_lower = {
        "txn_date": "2026-10-08",
        "party": "tariq mahmood",
        "type": "expense",
        "amount": 500.0,
        "category": "Salaries",
        "status": "paid",
    }
    res_lower = normalize_entry(entry_lower)
    assert res_lower["party"] == "Tariq Mahmood", f"Expected 'Tariq Mahmood', got {res_lower['party']}"

    # 6. Invalid type should be coerced to 'expense'
    entry_bad_type = {
        "txn_date": "2026-10-08",
        "party": "Shop Supplies",
        "type": "random_invalid_type",
        "amount": 250.0,
        "category": "Maintenance",
        "status": "paid",
    }
    res_bad_type = normalize_entry(entry_bad_type)
    assert res_bad_type["type"] == "expense", f"Expected 'expense', got {res_bad_type['type']}"

    # 7. Test TransactionEntry Pydantic model passing through normalize_entry
    pyd_entry = TransactionEntry(
        txn_date="08-10-2026",
        party="PTCL",
        type="expense",
        amount=3200.0,
        category="Internet & Phone",
        status="unpaid",
        due_date="17-10-2026",
        note="broadband"
    )
    res_pyd = normalize_entry(pyd_entry)
    assert res_pyd["party"] == "PTCL"
    assert res_pyd["amount"] == 3200.0
    assert res_pyd["txn_date"] == "2026-10-08"
    assert res_pyd["due_date"] == "2026-10-17"
    assert res_pyd["status"] == "unpaid"

    print("ALL NORMALIZATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    run_tests()
