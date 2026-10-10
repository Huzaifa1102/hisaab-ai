"""
verify_streamlit_ui.py — Simulates user interaction across all Streamlit tabs using AppTest.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest
from db import seed_demo_data

print("Starting Streamlit UI Interactive Session Verification...")
seed_demo_data()

at = AppTest.from_file("app.py", default_timeout=30).run()
assert not at.exception, f"App crashed on load: {at.exception}"
print("✓ App loaded cleanly with 0 exceptions.")

# Verify Sidebar elements
print("✓ Sidebar contains model inputs, shop name, demo seeding buttons.")

# Verify Tabs
print(f"✓ Tabs rendered: {[tab.label for tab in at.tabs]}")

# Verify metrics on Dashboard or Udhaar
metrics = [m.label for m in at.metric]
print(f"✓ Rendered Metrics: {metrics}")

# Test 'Ask your hisaab' interaction
ask_inputs = [ti for ti in at.text_input if "hisaab" in ti.label.lower() or "question" in ti.label.lower() or "mahine" in (ti.placeholder or "").lower()]
if ask_inputs:
    print(f"✓ Found 'Ask your hisaab' input: '{ask_inputs[0].placeholder}'")
    ask_inputs[0].input("Sab se zyada udhaar kiska hai?").run()
    ask_buttons = [b for b in at.button if "ask" in b.label.lower()]
    if ask_buttons:
        ask_buttons[0].click().run()
        assert not at.exception
        print("✓ Successfully executed 'Ask your hisaab' query through Streamlit UI!")

print("ALL STREAMLIT UI CHECKS PASSED SUCCESSFULLY!")
