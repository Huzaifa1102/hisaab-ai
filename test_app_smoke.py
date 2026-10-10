"""
test_app_smoke.py — Streamlit AppTest automated smoke test suite for Hisaab AI.
Tests:
1. Clean render on fresh/empty DB.
2. Seed demo data (~22 records).
3. Clean render with all tabs, charts, metrics on populated DB.
4. Verify no uncaught exceptions on all components.
"""

from streamlit.testing.v1 import AppTest
from db import seed_demo_data, reset_db

def test_app():
    print("Step 1: Running smoke test on unseeded/fresh DB...")
    reset_db()
    at1 = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at1.exception, f"Exception occurred during empty app render: {at1.exception}"
    print("Step 1 passed: Clean render with 0 exceptions on unseeded DB.")

    print("Step 2: Seeding demo data...")
    seeded_count = seed_demo_data()
    print(f"Seeded {seeded_count} realistic records.")

    print("Step 3: Running smoke test on populated DB...")
    at2 = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at2.exception, f"Exception occurred during populated app render: {at2.exception}"
    print("Step 3 passed: Clean render with 0 exceptions on populated DB.")

    print("Step 4: Testing Voice Tab safety switch (hiding Voice Khata)...")
    voice_cb = [c for c in at2.sidebar.checkbox if c.label == "Show Voice Khata tab"][0]
    voice_cb.uncheck().run()
    assert not at2.exception, f"Exception occurred with voice tab hidden: {at2.exception}"
    print("Step 4 passed: Clean render with Voice Khata tab hidden.")

    print("ALL STREAMLIT SMOKE TESTS PASSED!")

if __name__ == "__main__":
    test_app()
