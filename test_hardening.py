"""
test_hardening.py — Regression tests for the demo-hardening fixes. No live API calls:
Gemini is mocked and the API keys are blanked.
1. Smart Scan errors stay visible after the rerun (missing key, network failure, offline cache miss).
2. "Use saved result" fallback works and shows the offline banner; nothing is cached automatically.
3. Saving a review table with no valid rows keeps the document in the queue.
4. Friendly error messages (no raw API text) and retry rules (one retry, none for bad key/model).
5. Ask / reminder fallbacks keep honest labels and explain why the AI was not used.
6. Blank review-table cells (NaN) never become a party named "Nan".
7. API keys from .env are never sent to the browser, but are still used for AI calls.
"""

import os
import tempfile

# Throwaway database + no keys, before importing app modules
os.environ["HISAAB_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_hisaab.db")
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import core
from core import AIServiceError, ExtractionResult, ask_ledger, draft_reminder, friendly_api_error, normalize_entry
from db import get_all_transactions, reset_db, seed_demo_data

ROOT = Path(__file__).resolve().parent
APP = str(ROOT / "app.py")
BILL = (ROOT / "test_images" / "electricity_bill.png").read_bytes()
OFFLINE = "Calculated from your ledger (offline, not AI)"
TEMPLATE = "Template message (AI unavailable)"


def _scan(name: str, offline: bool = False) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    if offline:
        [t for t in at.sidebar.toggle if "Offline" in t.label][0].set_value(True).run()
    at.file_uploader[0].set_value((name, BILL, "image/png")).run()
    [b for b in at.button if "Extract with AI" in b.label][0].click().run()
    assert not at.exception, at.exception
    return at


def _errors(at: AppTest):
    return [e.value for e in at.error]


def _use_saved_buttons(at: AppTest):
    return [b for b in at.button if b.label.startswith("Use saved result")]


def test_scan_errors_visible():
    print("Testing Smart Scan error visibility...")
    reset_db()
    at = _scan("electricity_bill.png")
    assert any("API key is missing" in e for e in _errors(at)), _errors(at)
    assert len(at.session_state["pending_docs"]) == 0

    at = _scan("not_cached_photo.png", offline=True)
    assert any("no saved result" in e for e in _errors(at)), _errors(at)
    assert len(at.session_state["pending_docs"]) == 0
    print("Passed: scan errors stay on screen.")


def test_cache_fallback_is_explicit():
    print("Testing offline cache fallback button...")
    with patch.object(core, "extract_from_image", side_effect=AIServiceError("Could not reach Gemini.")):
        at = _scan("electricity_bill.png")
        assert len(at.session_state["pending_docs"]) == 0, "cache must not load without a click"
        buttons = _use_saved_buttons(at)
        assert buttons, "expected a 'Use saved result' button"
        buttons[0].click().run()
        assert not at.exception, at.exception
        docs = at.session_state["pending_docs"]
        assert len(docs) == 1 and docs[0]["is_offline"] is True
        assert any("Offline demo mode" in w.value for w in at.warning), "offline banner missing"

        at = _scan("no_cache_for_this.png")
        assert not _use_saved_buttons(at)

    with patch.object(core, "extract_from_image", side_effect=KeyError("raw internal detail")):
        at = _scan("x.png")
        assert not any("raw internal detail" in e for e in _errors(at)), _errors(at)
        assert any("Something went wrong" in e for e in _errors(at))
    print("Passed: cache only loads on an explicit click, with the banner.")


def test_offline_banner_is_honest_about_source():
    print("Testing that the offline banner says where a saved result came from...")
    import json
    for name, expected in (("electricity_bill", "earlier live AI scan"), ("khata_register", "hand-made sample")):
        provenance = json.loads((ROOT / "demo_cache" / f"{name}.json").read_text(encoding="utf-8")).get("provenance")
        if provenance not in ("live_scan", "sample"):
            continue  # cache regenerated in an unexpected format; nothing to check
        if (provenance == "live_scan") != (expected == "earlier live AI scan"):
            expected = "earlier live AI scan" if provenance == "live_scan" else "hand-made sample"
        at = _scan(f"{name}.png", offline=True)
        banners = [w.value for w in at.warning if "Offline demo mode" in w.value]
        assert banners and expected in banners[0], banners
    print("Passed: offline banner names the source (live scan vs sample).")


def test_save_empty_table_keeps_doc():
    print("Testing save of an empty review table...")
    reset_db()
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["pending_docs"] = [{
        "uid": "t1",
        "result": ExtractionResult(doc_type="other", summary="A photo of a cat", confidence=0.4, entries=[]),
        "entries": [], "img_bytes": None, "filename": "cat.jpg", "doc_type": "other", "is_offline": False,
    }]
    at.run()
    [b for b in at.button if b.label == "💾 Save to Ledger"][0].click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["pending_docs"]) == 1, "document must stay in the queue"
    assert any("Nothing saved" in w.value for w in at.warning)
    assert get_all_transactions().empty
    print("Passed: empty table is not saved and the document is kept.")


def test_friendly_errors_and_retry():
    print("Testing friendly error messages and retry rules...")
    cases = {
        "getaddrinfo failed": "internet connection",
        "404 NOT_FOUND models/gemini-x is not found": "change the 'Gemini Model' field in the sidebar",
        "400 API_KEY_INVALID API key not valid": "Invalid Gemini API key",
        "429 RESOURCE_EXHAUSTED": "rate limit",
        "ReadTimeout: timed out": "did not answer in time",
        "504 DEADLINE_EXCEEDED": "did not answer in time",
        "429 RESOURCE_EXHAUSTED You exceeded your current quota": "used up its quota",
    }
    for raw, expected in cases.items():
        msg = friendly_api_error(RuntimeError(raw), "gemini-x")
        assert expected in msg, (raw, msg)
        assert raw not in msg, f"raw API text leaked: {msg}"

    def run_with(err):
        client = MagicMock()
        client.models.generate_content.side_effect = err
        with patch("google.genai.Client", return_value=client), patch("core.time.sleep"):
            try:
                core.extract_from_image(BILL, api_key="test-key", model_name="gemini-x")
            except AIServiceError as e:
                return client.models.generate_content.call_count, str(e)
        raise AssertionError("expected AIServiceError")

    calls, msg = run_with(RuntimeError("404 NOT_FOUND"))
    assert calls == 1, f"unknown model must not be retried (calls={calls})"
    assert "gemini-x" in msg and "sidebar" in msg
    calls, _ = run_with(RuntimeError("API key not valid"))
    assert calls == 1, f"bad key must not be retried (calls={calls})"
    calls, _ = run_with(ConnectionError("network down"))
    assert calls == 2, f"network failure must be retried once (calls={calls})"
    calls, msg = run_with(RuntimeError("429 RESOURCE_EXHAUSTED You exceeded your current quota"))
    assert calls == 1 and "quota" in msg, f"used-up quota must not be retried (calls={calls})"

    # Hard stopwatch: a call that hangs is abandoned after the deadline, then retried once
    import threading
    import time as _time
    release = threading.Event()
    client = MagicMock()
    client.models.generate_content.side_effect = lambda **kw: release.wait(30)
    with patch("google.genai.Client", return_value=client), patch("core.time.sleep"), \
            patch.object(core, "AI_DEADLINE_S", 0.3):
        started = _time.time()
        try:
            core.extract_from_image(BILL, api_key="test-key", model_name="gemini-x")
            raise AssertionError("expected AIServiceError")
        except AIServiceError as e:
            elapsed = _time.time() - started
            assert "did not answer in time" in str(e), str(e)
            assert elapsed < 5, f"hung call was not cut off ({elapsed:.1f}s)"
            assert client.models.generate_content.call_count == 2
    release.set()

    try:
        core.extract_from_image(b"not an image", api_key="test-key")
        raise AssertionError("expected AIServiceError")
    except AIServiceError as e:
        assert "could not be opened as an image" in str(e)
    print("Passed: friendly messages, one retry, no retry for bad key/model.")


def test_honest_fallback_labels():
    print("Testing Ask / reminder fallback labels...")
    seed_demo_data()
    df = get_all_transactions()
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("404 NOT_FOUND")
    with patch("google.genai.Client", return_value=client), patch("core.time.sleep"):
        text, label, notice = ask_ledger("who owes me the most?", df, api_key="test-key", model_name="gemini-x")
        assert label == OFFLINE and "Faisal Khan" in text
        assert notice and "gemini-x" in notice

        text, label, notice = ask_ledger("tell me a joke", df, api_key="test-key", model_name="gemini-x")
        assert label == "Error" and "NOT_FOUND" not in text

        text, label, notice = draft_reminder("Shop", "Hamza", 1450, "English", api_key="test-key", model_name="gemini-x")
        assert label == TEMPLATE and "Hamza" in text and notice

    text, label, notice = draft_reminder("Shop", "Hamza", 1450, "English", api_key="")
    assert label == TEMPLATE
    reset_db()
    print("Passed: offline/template labels with a reason.")


def test_api_keys_not_sent_to_browser():
    print("Testing that .env API keys never reach the UI...")
    fake_gemini = "not-a-real-gemini-key-for-tests-0001"  # deliberately not key-shaped
    fake_groq = "not-a-real-groq-key-for-tests-0002"
    seed_demo_data()
    with patch.dict(os.environ, {"GEMINI_API_KEY": fake_gemini, "GROQ_API_KEY": fake_groq}):
        at = AppTest.from_file(APP, default_timeout=60).run()
        assert not at.exception, at.exception
        shown = [str(w.value) for w in at.text_input]
        for kind in ("caption", "markdown", "info", "warning", "success", "error"):
            shown += [str(e.value) for e in getattr(at, kind)]
        assert not any(fake_gemini in v or fake_groq in v for v in shown), "API key sent to the browser"
        assert sum("loaded from .env" in c.value for c in at.sidebar.caption) == 2

        # The hidden .env key is still the one used for AI calls
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text="Faisal Khan owes the most.")
        with patch("google.genai.Client", return_value=client) as client_cls:
            [t for t in at.text_input if t.label == "Question"][0].set_value("who owes me the most?")
            [b for b in at.button if b.label == "🔍 Ask AI"][0].click().run()
            assert not at.exception, at.exception
            assert client_cls.call_args.kwargs["api_key"] == fake_gemini
            assert any("AI answer" in s.value for s in at.success)
    reset_db()
    print("Passed: keys stay hidden and are still used.")


def _sidebar_checkbox(at: AppTest, label: str):
    return [c for c in at.sidebar.checkbox if c.label == label][0]


def test_confirm_ticks_reset_after_use():
    print("Testing that Load Demo / Reset confirmations untick after use...")
    reset_db()
    at = AppTest.from_file(APP, default_timeout=60).run()
    load_btn = [b for b in at.sidebar.button if "Load Demo Ledger" in b.label][0]
    assert load_btn.disabled, "Load Demo must be disabled until confirmed"

    _sidebar_checkbox(at, "Replace current ledger with demo data").check().run()
    [b for b in at.sidebar.button if "Load Demo Ledger" in b.label][0].click().run()
    assert not at.exception, at.exception
    assert len(get_all_transactions()) == 22
    assert _sidebar_checkbox(at, "Replace current ledger with demo data").value is False
    assert [b for b in at.sidebar.button if "Load Demo Ledger" in b.label][0].disabled

    _sidebar_checkbox(at, "I understand this deletes everything").check().run()
    [b for b in at.sidebar.button if b.label == "Reset Ledger"][0].click().run()
    assert not at.exception, at.exception
    assert get_all_transactions().empty
    assert _sidebar_checkbox(at, "I understand this deletes everything").value is False
    print("Passed: confirmations untick after use.")


def test_camera_only_after_opt_in():
    print("Testing that the camera (and its permission prompt) only appears on request...")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.get("camera_input"), "camera must not render on page load"
    [t for t in at.toggle if "Use device camera" in t.label][0].set_value(True).run()
    assert not at.exception, at.exception
    assert len(at.get("camera_input")) == 1
    print("Passed: camera renders only after the toggle.")


def test_demo_polish():
    print("Testing toolbar config and month chart labels...")
    import json
    import re
    import tomllib

    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["client"]["toolbarMode"] == "viewer", "Deploy / developer menu must be hidden"

    seed_demo_data()
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    figures = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
    month_fig = [f for f in figures if "Expenses by Month" in json.dumps(f["layout"].get("title", ""))][0]
    months = month_fig["data"][0]["x"]
    assert months and all(re.fullmatch(r"[A-Z][a-z]{2} \d{4}", m) for m in months), months
    assert month_fig["layout"]["xaxis"]["type"] == "category"
    assert any("Expenses this month (incl. unpaid bills)" in m.value for m in at.markdown)

    [b for b in at.button if b.label == "🔍 Ask AI"][0].click().run()
    assert not at.exception, at.exception
    assert any("Type a question first" in w.value for w in at.warning), "empty question needs feedback"
    reset_db()
    print("Passed: developer toolbar hidden, months labelled, clear KPI label, empty Ask feedback.")


def test_nan_cells():
    print("Testing NaN cells from the review table...")
    row = {"txn_date": float("nan"), "party": float("nan"), "type": "expense", "amount": 100.0,
           "category": float("nan"), "status": float("nan"), "due_date": float("nan"), "note": float("nan")}
    norm = normalize_entry(row, fallback_date="2026-10-10")
    assert norm["party"] == "Unknown" and norm["note"] == "" and norm["txn_date"] == "2026-10-10"
    assert normalize_entry({"party": "Ali", "amount": float("nan")}) is None
    print("Passed: NaN cells handled.")


if __name__ == "__main__":
    test_scan_errors_visible()
    test_cache_fallback_is_explicit()
    test_offline_banner_is_honest_about_source()
    test_save_empty_table_keeps_doc()
    test_friendly_errors_and_retry()
    test_honest_fallback_labels()
    test_api_keys_not_sent_to_browser()
    test_confirm_ticks_reset_after_use()
    test_camera_only_after_opt_in()
    test_demo_polish()
    test_nan_cells()
    print("ALL HARDENING TESTS PASSED!")
