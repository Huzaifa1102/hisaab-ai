"""
db.py — Database Layer for Hisaab AI
SQLite storage for kiryana store ledger transactions and customer khata contacts.
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import sqlite3
import pandas as pd

DB_FILE = Path(__file__).parent / "hisaab.db"

ALLOWED_TYPES = ["expense", "udhaar_given", "payment_received", "cash_sale"]

FIXED_CATEGORIES = [
    "Stock / Inventory",
    "Electricity",
    "Gas",
    "Water",
    "Internet & Phone",
    "Rent",
    "Salaries",
    "Transport",
    "Maintenance",
    "Customer Credit",
    "Sales",
    "Other",
]


def get_connection(db_path: Path | str = DB_FILE) -> sqlite3.Connection:
    """Returns a SQLite connection with check_same_thread=False for Streamlit concurrency."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str = DB_FILE) -> None:
    """Creates the ledger and customers tables if they do not exist."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    txn_date TEXT NOT NULL,
                    party TEXT NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    due_date TEXT,
                    note TEXT,
                    source TEXT NOT NULL,
                    doc_type TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    party_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    phone TEXT
                )
                """
            )
            # Helpful indexes for performance on larger ledgers
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_party ON ledger(party)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_txn_date ON ledger(txn_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger(type)")
    finally:
        conn.close()


def add_transactions(
    rows: List[Dict[str, Any]],
    source: str = "manual",
    doc_type: str = "manual",
    db_path: Path | str = DB_FILE,
) -> int:
    """
    Inserts a list of validated/normalized transaction dictionaries into the ledger.
    Also registers parties into the customers table if they represent udhaar/payment.
    Returns the count of successfully inserted records.
    """
    if not rows:
        return 0

    conn = get_connection(db_path)
    inserted_count = 0
    now_iso = datetime.now().isoformat()

    try:
        with conn:
            for r in rows:
                txn_date = str(r.get("txn_date") or date.today().isoformat())
                party = str(r.get("party") or "Unknown").strip()
                t_type = str(r.get("type") or "expense").strip()
                amount = float(r.get("amount") or 0.0)
                category = str(r.get("category") or "Other").strip()
                status = str(r.get("status") or "paid").strip()
                due_date = r.get("due_date")
                due_date_str = str(due_date).strip() if due_date else None
                note = str(r.get("note") or "").strip()
                row_source = str(r.get("source") or source).strip()
                row_doc_type = str(r.get("doc_type") or doc_type).strip()

                if amount <= 0:
                    continue  # Guard against non-positive amounts

                conn.execute(
                    """
                    INSERT INTO ledger (
                        created_at, txn_date, party, type, amount,
                        category, status, due_date, note, source, doc_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        txn_date,
                        party,
                        t_type,
                        amount,
                        category,
                        status,
                        due_date_str,
                        note,
                        row_source,
                        row_doc_type,
                    ),
                )
                inserted_count += 1

                # If this party is a customer involved in khata, register or keep their display name
                if t_type in ("udhaar_given", "payment_received"):
                    party_key = party.lower()
                    conn.execute(
                        """
                        INSERT INTO customers (party_key, display_name, phone)
                        VALUES (?, ?, NULL)
                        ON CONFLICT(party_key) DO UPDATE SET
                            display_name = excluded.display_name
                        """,
                        (party_key, party),
                    )
        return inserted_count
    finally:
        conn.close()


def get_all_transactions(db_path: Path | str = DB_FILE) -> pd.DataFrame:
    """Returns all ledger records as a pandas DataFrame, newest transactions first."""
    conn = get_connection(db_path)
    try:
        query = """
            SELECT id, created_at, txn_date, party, type, amount,
                   category, status, due_date, note, source, doc_type
            FROM ledger
            ORDER BY txn_date DESC, id DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        conn.close()


def find_duplicates(rows: List[Dict[str, Any]], db_path: Path | str = DB_FILE) -> List[Dict[str, Any]]:
    """
    Checks if any row in the given batch matches an existing record
    by lower(party) + amount + txn_date. Returns the list of matched existing records.
    """
    if not rows:
        return []

    conn = get_connection(db_path)
    duplicates = []
    try:
        cursor = conn.cursor()
        for r in rows:
            party_key = str(r.get("party") or "").strip().lower()
            try:
                amount = float(r.get("amount") or 0.0)
            except (ValueError, TypeError):
                continue
            txn_date = str(r.get("txn_date") or "").strip()

            cursor.execute(
                """
                SELECT id, txn_date, party, type, amount, category, status
                FROM ledger
                WHERE LOWER(TRIM(party)) = ? AND ABS(amount - ?) < 0.01 AND txn_date = ?
                LIMIT 1
                """,
                (party_key, amount, txn_date),
            )
            match = cursor.fetchone()
            if match:
                duplicates.append(dict(match))
        return duplicates
    finally:
        conn.close()


def get_customer_balances(db_path: Path | str = DB_FILE) -> pd.DataFrame:
    """
    Computes customer udhaar balances.
    Columns: party, udhaar_given, payment_received, balance, last_activity, phone.
    Group case-insensitively by party. Sort by balance descending.
    """
    conn = get_connection(db_path)
    try:
        query = """
            SELECT 
                COALESCE(c.display_name, MIN(l.party)) AS party,
                COALESCE(SUM(CASE WHEN l.type = 'udhaar_given' THEN l.amount ELSE 0 END), 0.0) AS udhaar_given,
                COALESCE(SUM(CASE WHEN l.type = 'payment_received' THEN l.amount ELSE 0 END), 0.0) AS payment_received,
                (COALESCE(SUM(CASE WHEN l.type = 'udhaar_given' THEN l.amount ELSE 0 END), 0.0) -
                 COALESCE(SUM(CASE WHEN l.type = 'payment_received' THEN l.amount ELSE 0 END), 0.0)) AS balance,
                MAX(l.txn_date) AS last_activity,
                c.phone AS phone
            FROM ledger l
            LEFT JOIN customers c ON LOWER(TRIM(l.party)) = c.party_key
            WHERE l.type IN ('udhaar_given', 'payment_received')
            GROUP BY LOWER(TRIM(l.party))
            ORDER BY balance DESC, party ASC
        """
        df = pd.read_sql_query(query, conn)
        if df.empty:
            return pd.DataFrame(
                columns=["party", "udhaar_given", "payment_received", "balance", "last_activity", "phone"]
            )
        return df
    finally:
        conn.close()


def get_unpaid_bills(db_path: Path | str = DB_FILE) -> pd.DataFrame:
    """Returns unpaid expenses sorted by due_date ascending."""
    conn = get_connection(db_path)
    try:
        query = """
            SELECT id, created_at, txn_date, party, type, amount,
                   category, status, due_date, note, source, doc_type
            FROM ledger
            WHERE type = 'expense' AND LOWER(status) = 'unpaid'
            ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date ASC, id ASC
        """
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def mark_paid(txn_id: int, db_path: Path | str = DB_FILE) -> bool:
    """Marks an unpaid expense as paid."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE ledger SET status = 'paid' WHERE id = ? AND type = 'expense'",
                (txn_id,),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


def delete_transactions(ids: List[int], db_path: Path | str = DB_FILE) -> int:
    """Deletes transactions by their IDs."""
    if not ids:
        return 0
    conn = get_connection(db_path)
    try:
        with conn:
            placeholders = ",".join("?" for _ in ids)
            cursor = conn.execute(
                f"DELETE FROM ledger WHERE id IN ({placeholders})",
                tuple(ids),
            )
            return cursor.rowcount
    finally:
        conn.close()


def set_customer_phone(party: str, phone: str, db_path: Path | str = DB_FILE) -> None:
    """Updates or sets phone number for a customer (identified case-insensitively)."""
    party_clean = party.strip()
    if not party_clean:
        return
    party_key = party_clean.lower()
    clean_phone = phone.strip()

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO customers (party_key, display_name, phone)
                VALUES (?, ?, ?)
                ON CONFLICT(party_key) DO UPDATE SET
                    phone = excluded.phone,
                    display_name = CASE WHEN display_name = '' THEN excluded.display_name ELSE display_name END
                """,
                (party_key, party_clean, clean_phone),
            )
    finally:
        conn.close()


def get_customer_phone(party: str, db_path: Path | str = DB_FILE) -> Optional[str]:
    """Retrieves customer phone number if saved."""
    party_key = party.strip().lower()
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT phone FROM customers WHERE party_key = ?", (party_key,))
        row = cursor.fetchone()
        return row["phone"] if row and row["phone"] else None
    finally:
        conn.close()


def reset_db(db_path: Path | str = DB_FILE) -> None:
    """Deletes all rows from both ledger and customers tables."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM ledger")
            conn.execute("DELETE FROM customers")
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('ledger')")
    finally:
        conn.close()


def seed_demo_data(db_path: Path | str = DB_FILE) -> int:
    """
    Resets the database and seeds ~22 realistic entries across the last ~60 days,
    using dates relative to today.
    Includes:
    - Stock purchases from wholesalers (Metro Cash & Carry, Al-Fatah Wholesale, Engro Foods Distributor)
    - Shop rent and helper salary
    - Utility bills: one paid SNGPL bill, one UNPAID IESCO bill due in 2 days, one UNPAID PTCL bill due in 9 days
    - Udhaar for 5 customers (Ahmed Raza, Bushra Bibi, Faisal Khan, Zainab Ali, Hamza) with partial repayments
    - Daily cash sales
    - Phone numbers for customers
    """
    reset_db(db_path)
    today = date.today()

    # Pre-register phone numbers for key customers
    set_customer_phone("Ahmed Raza", "03001234567", db_path)
    set_customer_phone("Bushra Bibi", "03219876543", db_path)
    set_customer_phone("Faisal Khan", "03335551234", db_path)
    set_customer_phone("Zainab Ali", "03451122334", db_path)

    def d_offset(days_ago: int) -> str:
        return (today - timedelta(days=days_ago)).isoformat()

    def d_future(days_ahead: int) -> str:
        return (today + timedelta(days=days_ahead)).isoformat()

    seed_entries = [
        # 1-3: Wholesaler inventory purchases
        {
            "txn_date": d_offset(55),
            "party": "Metro Cash & Carry",
            "type": "expense",
            "amount": 42500.0,
            "category": "Stock / Inventory",
            "status": "paid",
            "due_date": None,
            "note": "Wholesale pulses, rice (50kg), cooking oil boxes",
            "source": "demo",
            "doc_type": "invoice",
        },
        {
            "txn_date": d_offset(35),
            "party": "Al-Fatah Wholesale",
            "type": "expense",
            "amount": 28400.0,
            "category": "Stock / Inventory",
            "status": "paid",
            "due_date": None,
            "note": "Spices, tea packs, flour sacks",
            "source": "demo",
            "doc_type": "invoice",
        },
        {
            "txn_date": d_offset(12),
            "party": "Engro Foods Distributor",
            "type": "expense",
            "amount": 19600.0,
            "category": "Stock / Inventory",
            "status": "paid",
            "due_date": None,
            "note": "Packaged milk cartons, tea whitener, juices",
            "source": "demo",
            "doc_type": "invoice",
        },
        # 4-5: Operational overheads (Rent & Salaries)
        {
            "txn_date": d_offset(30),
            "party": "Haji Rasheed (Landlord)",
            "type": "expense",
            "amount": 25000.0,
            "category": "Rent",
            "status": "paid",
            "due_date": None,
            "note": "Shop monthly rent",
            "source": "demo",
            "doc_type": "receipt",
        },
        {
            "txn_date": d_offset(10),
            "party": "Tariq Mahmood (Helper)",
            "type": "expense",
            "amount": 18000.0,
            "category": "Salaries",
            "status": "paid",
            "due_date": None,
            "note": "Monthly shop assistant salary",
            "source": "demo",
            "doc_type": "receipt",
        },
        # 6-8: Utility Bills
        {
            "txn_date": d_offset(25),
            "party": "SNGPL Gas",
            "type": "expense",
            "amount": 2450.0,
            "category": "Gas",
            "status": "paid",
            "due_date": d_offset(22),
            "note": "Commercial gas bill — paid at Habib Bank counter",
            "source": "demo",
            "doc_type": "utility_bill",
        },
        {
            "txn_date": d_offset(3),
            "party": "IESCO",
            "type": "expense",
            "amount": 7840.0,
            "category": "Electricity",
            "status": "unpaid",
            "due_date": d_future(2),  # Due in 2 days!
            "note": "Electricity commercial billing reference 0812345678",
            "source": "demo",
            "doc_type": "utility_bill",
        },
        {
            "txn_date": d_offset(1),
            "party": "PTCL",
            "type": "expense",
            "amount": 3200.0,
            "category": "Internet & Phone",
            "status": "unpaid",
            "due_date": d_future(9),  # Due in 9 days!
            "note": "Broadband + shop landline bill",
            "source": "demo",
            "doc_type": "utility_bill",
        },
        # 9-17: Udhaar transactions and repayments for 5 customers
        # Customer 1: Ahmed Raza
        {
            "txn_date": d_offset(20),
            "party": "Ahmed Raza",
            "type": "udhaar_given",
            "amount": 4500.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Grocery: 5kg ghee, 10kg atta, tea",
            "source": "demo",
            "doc_type": "khata_page",
        },
        {
            "txn_date": d_offset(8),
            "party": "Ahmed Raza",
            "type": "payment_received",
            "amount": 2000.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Partial payment handed over by son",
            "source": "demo",
            "doc_type": "khata_page",
        },
        # Customer 2: Bushra Bibi
        {
            "txn_date": d_offset(18),
            "party": "Bushra Bibi",
            "type": "udhaar_given",
            "amount": 3200.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Spices, soap, cooking oil",
            "source": "demo",
            "doc_type": "khata_page",
        },
        {
            "txn_date": d_offset(5),
            "party": "Bushra Bibi",
            "type": "payment_received",
            "amount": 1500.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Paid cash at counter",
            "source": "demo",
            "doc_type": "khata_page",
        },
        # Customer 3: Faisal Khan
        {
            "txn_date": d_offset(15),
            "party": "Faisal Khan",
            "type": "udhaar_given",
            "amount": 6200.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Baqi: 20kg super basmati rice and cooking oil tin",
            "source": "demo",
            "doc_type": "khata_page",
        },
        # Customer 4: Zainab Ali
        {
            "txn_date": d_offset(14),
            "party": "Zainab Ali",
            "type": "udhaar_given",
            "amount": 2800.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Sugar, milk powder, biscuits",
            "source": "demo",
            "doc_type": "khata_page",
        },
        {
            "txn_date": d_offset(4),
            "party": "Zainab Ali",
            "type": "payment_received",
            "amount": 1000.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "EasyPaisa transfer received",
            "source": "demo",
            "doc_type": "khata_page",
        },
        # Customer 5: Hamza
        {
            "txn_date": d_offset(7),
            "party": "Hamza",
            "type": "udhaar_given",
            "amount": 1450.0,
            "category": "Customer Credit",
            "status": "n/a",
            "due_date": None,
            "note": "Cold drinks, cigarettes, snacks",
            "source": "demo",
            "doc_type": "khata_page",
        },
        # 18-22: Daily Cash Sales
        {
            "txn_date": d_offset(10),
            "party": "Counter Cash Sale",
            "type": "cash_sale",
            "amount": 16500.0,
            "category": "Sales",
            "status": "n/a",
            "due_date": None,
            "note": "Full day counter cash register",
            "source": "demo",
            "doc_type": "receipt",
        },
        {
            "txn_date": d_offset(6),
            "party": "Counter Cash Sale",
            "type": "cash_sale",
            "amount": 19200.0,
            "category": "Sales",
            "status": "n/a",
            "due_date": None,
            "note": "Friday counter rush sale",
            "source": "demo",
            "doc_type": "receipt",
        },
        {
            "txn_date": d_offset(3),
            "party": "Counter Cash Sale",
            "type": "cash_sale",
            "amount": 14800.0,
            "category": "Sales",
            "status": "n/a",
            "due_date": None,
            "note": "Counter cash register",
            "source": "demo",
            "doc_type": "receipt",
        },
        {
            "txn_date": d_offset(1),
            "party": "Counter Cash Sale",
            "type": "cash_sale",
            "amount": 17900.0,
            "category": "Sales",
            "status": "n/a",
            "due_date": None,
            "note": "Weekend cash collection",
            "source": "demo",
            "doc_type": "receipt",
        },
        {
            "txn_date": d_offset(0),
            "party": "Counter Cash Sale",
            "type": "cash_sale",
            "amount": 8300.0,
            "category": "Sales",
            "status": "n/a",
            "due_date": None,
            "note": "Morning counter cash takings",
            "source": "demo",
            "doc_type": "receipt",
        },
        # Shop maintenance
        {
            "txn_date": d_offset(16),
            "party": "Refrigeration Mechanic",
            "type": "expense",
            "amount": 3500.0,
            "category": "Maintenance",
            "status": "paid",
            "due_date": None,
            "note": "Deep freezer compressor gas recharge",
            "source": "demo",
            "doc_type": "receipt",
        },
    ]

    return add_transactions(seed_entries, source="demo", doc_type="demo", db_path=db_path)
