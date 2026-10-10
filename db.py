"""
db.py — Database Layer for Hisaab AI
SQLite storage for kiryana store ledger transactions and customer khata contacts.
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import sqlite3
import pandas as pd

# HISAAB_DB_PATH lets test scripts use a throwaway database instead of the real ledger.
DB_FILE = Path(os.getenv("HISAAB_DB_PATH") or (Path(__file__).parent / "hisaab.db"))

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
    """Creates the ledger, customers, inventory, galla, and shops tables if they do not exist."""
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
                    doc_type TEXT NOT NULL,
                    shop_id TEXT DEFAULT 'madina_store'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    party_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    phone TEXT,
                    shop_id TEXT DEFAULT 'madina_store'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shop_id TEXT DEFAULT 'madina_store',
                    item_name TEXT NOT NULL,
                    category TEXT DEFAULT 'Stock / Inventory',
                    quantity REAL DEFAULT 0.0,
                    unit TEXT DEFAULT 'kg',
                    cost_price REAL DEFAULT 0.0,
                    sale_price REAL DEFAULT 0.0,
                    min_stock REAL DEFAULT 5.0,
                    last_updated TEXT,
                    UNIQUE(shop_id, item_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS galla_reconciliations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reconciled_at TEXT NOT NULL,
                    recon_date TEXT NOT NULL,
                    shop_id TEXT DEFAULT 'madina_store',
                    opening_cash REAL DEFAULT 0.0,
                    cash_sales REAL DEFAULT 0.0,
                    cash_repayments REAL DEFAULT 0.0,
                    cash_expenses REAL DEFAULT 0.0,
                    expected_cash REAL DEFAULT 0.0,
                    actual_cash REAL DEFAULT 0.0,
                    difference REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'balanced',
                    notes TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shops (
                    shop_id TEXT PRIMARY KEY,
                    shop_name TEXT NOT NULL,
                    pin_code TEXT DEFAULT '1234',
                    owner_name TEXT,
                    phone TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Schema migrations if columns don't exist
            for alter_sql in [
                "ALTER TABLE ledger ADD COLUMN shop_id TEXT DEFAULT 'madina_store'",
                "ALTER TABLE customers ADD COLUMN shop_id TEXT DEFAULT 'madina_store'",
            ]:
                try:
                    conn.execute(alter_sql)
                except Exception:
                    pass

            # Helpful indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_party ON ledger(party)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_txn_date ON ledger(txn_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_shop ON ledger(shop_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_shop ON inventory(shop_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_galla_shop ON galla_reconciliations(shop_id)")
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

    inserted = add_transactions(seed_entries, source="demo", doc_type="demo", db_path=db_path)

    # Seed default shops
    create_or_get_shop("madina_store", "Madina General Store", "1234", db_path=db_path)
    create_or_get_shop("bismillah_store", "Bismillah Kiryana", "1234", db_path=db_path)

    # Seed demo inventory for Pakistani Kiryana store
    demo_inventory = [
        {"item_name": "Atta (Wheat Flour)", "category": "Stock / Inventory", "quantity": 25.0, "unit": "bag (20kg)", "cost_price": 2400.0, "sale_price": 2650.0, "min_stock": 5.0},
        {"item_name": "Cheeni (Sugar)", "category": "Stock / Inventory", "quantity": 18.0, "unit": "bag (50kg)", "cost_price": 6800.0, "sale_price": 7200.0, "min_stock": 4.0},
        {"item_name": "Super Basmati Rice", "category": "Stock / Inventory", "quantity": 14.0, "unit": "bag (25kg)", "cost_price": 7500.0, "sale_price": 8200.0, "min_stock": 3.0},
        {"item_name": "Cooking Oil / Ghee", "category": "Stock / Inventory", "quantity": 22.0, "unit": "tin (5L)", "cost_price": 2450.0, "sale_price": 2700.0, "min_stock": 5.0},
        {"item_name": "Dal Chana", "category": "Stock / Inventory", "quantity": 40.0, "unit": "kg", "cost_price": 260.0, "sale_price": 310.0, "min_stock": 10.0},
        {"item_name": "Dal Moong", "category": "Stock / Inventory", "quantity": 35.0, "unit": "kg", "cost_price": 290.0, "sale_price": 340.0, "min_stock": 8.0},
        {"item_name": "Chai Patti (Danedar)", "category": "Stock / Inventory", "quantity": 45.0, "unit": "pack (450g)", "cost_price": 620.0, "sale_price": 700.0, "min_stock": 10.0},
        {"item_name": "Milk Pack (Carton)", "category": "Stock / Inventory", "quantity": 12.0, "unit": "carton", "cost_price": 3100.0, "sale_price": 3400.0, "min_stock": 4.0},
    ]
    for item in demo_inventory:
        add_or_update_stock(
            item_name=item["item_name"],
            quantity=item["quantity"],
            unit=item["unit"],
            cost_price=item["cost_price"],
            sale_price=item["sale_price"],
            min_stock=item["min_stock"],
            category=item["category"],
            shop_id="madina_store",
            db_path=db_path,
        )

    # Seed an initial Galla Reconciliation record
    save_galla_reconciliation(
        {
            "recon_date": today.isoformat(),
            "opening_cash": 5000.0,
            "cash_sales": 8300.0,
            "cash_repayments": 0.0,
            "cash_expenses": 0.0,
            "expected_cash": 13300.0,
            "actual_cash": 13300.0,
            "difference": 0.0,
            "status": "balanced",
            "notes": "Morning counter opening reconciliation",
        },
        shop_id="madina_store",
        db_path=db_path,
    )

    return inserted


# ==============================================================================
# INVENTORY MANAGEMENT
# ==============================================================================

def get_inventory(shop_id: str = "madina_store", db_path: Path | str = DB_FILE) -> pd.DataFrame:
    """Returns inventory items for the given shop_id as a pandas DataFrame."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        query = """
            SELECT id, shop_id, item_name, category, quantity, unit,
                   cost_price, sale_price, min_stock, last_updated,
                   (quantity * cost_price) AS total_cost_value,
                   (quantity * sale_price) AS total_sale_value
            FROM inventory
            WHERE shop_id = ?
            ORDER BY item_name ASC
        """
        df = pd.read_sql_query(query, conn, params=(shop_id,))
        return df
    finally:
        conn.close()


def add_or_update_stock(
    item_name: str,
    quantity: float,
    unit: str = "kg",
    cost_price: float = 0.0,
    sale_price: float = 0.0,
    min_stock: float = 5.0,
    category: str = "Stock / Inventory",
    shop_id: str = "madina_store",
    db_path: Path | str = DB_FILE,
) -> bool:
    """Adds or updates an inventory item stock level."""
    init_db(db_path)
    conn = get_connection(db_path)
    clean_name = item_name.strip()
    if not clean_name:
        return False
    now_iso = datetime.now().isoformat()

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO inventory (
                    shop_id, item_name, category, quantity, unit,
                    cost_price, sale_price, min_stock, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shop_id, item_name) DO UPDATE SET
                    quantity = excluded.quantity,
                    unit = excluded.unit,
                    cost_price = CASE WHEN excluded.cost_price > 0 THEN excluded.cost_price ELSE inventory.cost_price END,
                    sale_price = CASE WHEN excluded.sale_price > 0 THEN excluded.sale_price ELSE inventory.sale_price END,
                    min_stock = excluded.min_stock,
                    last_updated = excluded.last_updated
                """,
                (shop_id, clean_name, category, quantity, unit, cost_price, sale_price, min_stock, now_iso),
            )
            return True
    finally:
        conn.close()


def deduct_stock(
    item_name: str,
    quantity_to_deduct: float,
    shop_id: str = "madina_store",
    db_path: Path | str = DB_FILE,
) -> bool:
    """Deducts stock when an item is sold."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE inventory
                SET quantity = MAX(0.0, quantity - ?),
                    last_updated = ?
                WHERE shop_id = ? AND LOWER(TRIM(item_name)) = LOWER(TRIM(?))
                """,
                (quantity_to_deduct, datetime.now().isoformat(), shop_id, item_name),
            )
            return True
    finally:
        conn.close()


def update_inventory_from_line_items(
    line_items: List[Dict[str, Any]],
    shop_id: str = "madina_store",
    db_path: Path | str = DB_FILE,
) -> int:
    """
    Automatically increments or adds inventory stock when a wholesale invoice with line items is saved.
    Returns the count of updated stock items.
    """
    if not line_items:
        return 0
    init_db(db_path)
    updated = 0
    for item in line_items:
        desc = str(item.get("description") or "").strip()
        if not desc:
            continue
        qty = float(item.get("qty") or 1.0)
        amount = float(item.get("amount") or 0.0)
        rate = amount / qty if qty > 0 and amount > 0 else 0.0

        conn = get_connection(db_path)
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT quantity, cost_price FROM inventory WHERE shop_id = ? AND LOWER(TRIM(item_name)) = LOWER(TRIM(?))",
                    (shop_id, desc),
                )
                row = cursor.fetchone()
                now_iso = datetime.now().isoformat()
                if row:
                    new_qty = float(row["quantity"]) + qty
                    new_cost = rate if rate > 0 else float(row["cost_price"])
                    cursor.execute(
                        "UPDATE inventory SET quantity = ?, cost_price = ?, last_updated = ? WHERE shop_id = ? AND LOWER(TRIM(item_name)) = LOWER(TRIM(?))",
                        (new_qty, new_cost, now_iso, shop_id, desc),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO inventory (shop_id, item_name, quantity, unit, cost_price, sale_price, last_updated)
                        VALUES (?, ?, ?, 'unit', ?, ?, ?)
                        """,
                        (shop_id, desc, qty, rate, rate * 1.15, now_iso),
                    )
                updated += 1
        finally:
            conn.close()
    return updated


# ==============================================================================
# GALLA HISAAB (CASH DRAWER RECONCILIATION)
# ==============================================================================

def get_today_cash_summary(
    date_str: Optional[str] = None,
    shop_id: str = "madina_store",
    db_path: Path | str = DB_FILE,
) -> Dict[str, float]:
    """
    Computes cash movements for a given date (defaults to today):
    - Recorded cash sales (+)
    - Recorded cash repayments received from credit customers (+)
    - Recorded cash expenses (-)
    """
    init_db(db_path)
    target_date = date_str or date.today().isoformat()
    conn = get_connection(db_path)
    try:
        # Cash sales
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0.0) AS total FROM ledger WHERE shop_id = ? AND txn_date = ? AND type = 'cash_sale'",
            (shop_id, target_date),
        )
        sales = float(cursor.fetchone()["total"])

        # Cash repayments received
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0.0) AS total FROM ledger WHERE shop_id = ? AND txn_date = ? AND type = 'payment_received'",
            (shop_id, target_date),
        )
        repayments = float(cursor.fetchone()["total"])

        # Cash expenses paid today
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0.0) AS total FROM ledger WHERE shop_id = ? AND txn_date = ? AND type = 'expense' AND LOWER(status) = 'paid'",
            (shop_id, target_date),
        )
        expenses = float(cursor.fetchone()["total"])

        return {
            "date": target_date,
            "cash_sales": sales,
            "cash_repayments": repayments,
            "cash_expenses": expenses,
            "net_cash_flow": sales + repayments - expenses,
        }
    finally:
        conn.close()


def save_galla_reconciliation(
    recon_data: Dict[str, Any],
    shop_id: str = "madina_store",
    db_path: Path | str = DB_FILE,
) -> int:
    """Saves a daily cash drawer reconciliation record."""
    init_db(db_path)
    conn = get_connection(db_path)
    now_iso = datetime.now().isoformat()
    recon_date = str(recon_data.get("recon_date") or date.today().isoformat())
    opening = float(recon_data.get("opening_cash") or 0.0)
    sales = float(recon_data.get("cash_sales") or 0.0)
    repayments = float(recon_data.get("cash_repayments") or 0.0)
    expenses = float(recon_data.get("cash_expenses") or 0.0)
    expected = float(recon_data.get("expected_cash") or (opening + sales + repayments - expenses))
    actual = float(recon_data.get("actual_cash") or 0.0)
    diff = float(recon_data.get("difference") or (actual - expected))

    if abs(diff) < 1.0:
        status = "balanced"
    elif diff > 0:
        status = "surplus"
    else:
        status = "shortage"

    notes = str(recon_data.get("notes") or "").strip()

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO galla_reconciliations (
                    reconciled_at, recon_date, shop_id, opening_cash,
                    cash_sales, cash_repayments, cash_expenses,
                    expected_cash, actual_cash, difference, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso, recon_date, shop_id, opening, sales,
                    repayments, expenses, expected, actual, diff, status, notes
                ),
            )
            return cursor.lastrowid
    finally:
        conn.close()


def get_galla_history(
    shop_id: str = "madina_store",
    db_path: Path | str = DB_FILE,
) -> pd.DataFrame:
    """Returns past cash drawer reconciliations for the shop."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        query = """
            SELECT id, recon_date, reconciled_at, opening_cash,
                   cash_sales, cash_repayments, cash_expenses,
                   expected_cash, actual_cash, difference, status, notes
            FROM galla_reconciliations
            WHERE shop_id = ?
            ORDER BY recon_date DESC, id DESC
        """
        return pd.read_sql_query(query, conn, params=(shop_id,))
    finally:
        conn.close()


# ==============================================================================
# SHOPS & SECURITY PIN MANAGEMENT
# ==============================================================================

def get_all_shops(db_path: Path | str = DB_FILE) -> List[Dict[str, Any]]:
    """Returns all registered shop profiles."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT shop_id, shop_name, pin_code, owner_name, phone, created_at FROM shops ORDER BY shop_name ASC")
        rows = cursor.fetchall()
        if not rows:
            create_or_get_shop("madina_store", "Madina General Store", "1234", db_path=db_path)
            return [{"shop_id": "madina_store", "shop_name": "Madina General Store", "pin_code": "1234"}]
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_or_get_shop(
    shop_id: str,
    shop_name: str,
    pin_code: str = "1234",
    owner_name: str = "Shopkeeper",
    phone: str = "",
    db_path: Path | str = DB_FILE,
) -> Dict[str, Any]:
    """Ensures a shop profile exists or creates it with a default PIN."""
    init_db(db_path)
    conn = get_connection(db_path)
    clean_id = shop_id.strip().lower().replace(" ", "_")
    clean_name = shop_name.strip()
    clean_pin = str(pin_code).strip() or "1234"
    now_iso = datetime.now().isoformat()

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO shops (shop_id, shop_name, pin_code, owner_name, phone, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(shop_id) DO UPDATE SET
                    shop_name = excluded.shop_name
                """,
                (clean_id, clean_name, clean_pin, owner_name, phone, now_iso),
            )
        return {"shop_id": clean_id, "shop_name": clean_name, "pin_code": clean_pin}
    finally:
        conn.close()


def verify_shop_pin(
    shop_id: str,
    pin: str,
    db_path: Path | str = DB_FILE,
) -> bool:
    """Verifies the 4-digit PIN for a shop profile."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT pin_code FROM shops WHERE shop_id = ?", (shop_id,))
        row = cursor.fetchone()
        if not row:
            return pin.strip() == "1234"
        return row["pin_code"].strip() == pin.strip()
    finally:
        conn.close()


def update_shop_pin(
    shop_id: str,
    new_pin: str,
    db_path: Path | str = DB_FILE,
) -> bool:
    """Updates the security PIN for a shop."""
    clean_pin = new_pin.strip()
    if len(clean_pin) < 4:
        return False
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("UPDATE shops SET pin_code = ? WHERE shop_id = ?", (clean_pin, shop_id))
            return cursor.rowcount > 0
    finally:
        conn.close()
