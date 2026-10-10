#!/usr/bin/env python3
"""
Hisaab AI — Live Accuracy & Consistency Test Script
Tests the real Gemini extraction pipeline across all images in test_images/.
Runs 3 passes per image to benchmark consistency, measures latency,
and automatically builds the offline cache in demo_cache/ from real API scans.

Usage:
    python test_live_images.py
"""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Ensure local modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import clean_model_name, extract_from_image, ExtractionResult

# Load environment configuration (.env)
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = clean_model_name(os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))

ROOT_DIR = Path(__file__).resolve().parent
TEST_IMAGES_DIR = ROOT_DIR / "test_images"
DEMO_CACHE_DIR = ROOT_DIR / "demo_cache"


def format_currency(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    return f"Rs {val:,.0f}"


def run_benchmark():
    print("=" * 80)
    print("      HISAAB AI — LIVE GEMINI ACCURACY & CONSISTENCY BENCHMARK")
    print("=" * 80)

    # Validate API key presence without revealing the secret
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("your_"):
        print("\n[ERROR] GEMINI_API_KEY is not configured in .env!")
        print("Please set a valid Gemini API key in your .env file before running this benchmark.")
        sys.exit(1)

    print(f"[*] Target Model    : {GEMINI_MODEL}")
    print(f"[*] Images Directory: {TEST_IMAGES_DIR}")
    print(f"[*] Cache Output    : {DEMO_CACHE_DIR}")
    print(f"[*] Runs Per Image  : 3")
    print("=" * 80)

    DEMO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Locate image files
    valid_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    image_files = sorted([p for p in TEST_IMAGES_DIR.iterdir() if p.suffix.lower() in valid_extensions])

    if not image_files:
        print(f"[!] No test images found in {TEST_IMAGES_DIR}. Place sample receipts/bills there and re-run.")
        sys.exit(0)

    overall_results = {}

    for img_idx, img_path in enumerate(image_files, 1):
        filename = img_path.name
        stem = img_path.stem
        cache_dest = DEMO_CACHE_DIR / f"{stem}.json"

        print(f"\n[{img_idx}/{len(image_files)}] Testing Image: {filename} ({img_path.stat().st_size / 1024:.1f} KB)")
        print("-" * 80)

        runs_data: List[Dict[str, Any]] = []

        try:
            img_bytes = img_path.read_bytes()
        except Exception as read_err:
            print(f"  [ERROR] Could not read file: {read_err}")
            continue

        for run_num in range(1, 4):
            print(f"  --> Run {run_num}/3 initiating API extraction...", end="", flush=True)
            t_start = time.time()
            try:
                result, norm_entries = extract_from_image(
                    img_bytes,
                    api_key=GEMINI_API_KEY,
                    model_name=GEMINI_MODEL,
                )
                t_elapsed = round(time.time() - t_start, 2)
                print(f" [DONE] ({t_elapsed}s)")

                # Save the first successful run directly to demo_cache
                if not any(r["success"] for r in runs_data):
                    try:
                        cache_dest.write_text(result.model_dump_json(indent=2), encoding="utf-8")
                        print(f"      [CACHE SAVED] Live scan stored -> demo_cache/{stem}.json")
                    except Exception as cache_err:
                        print(f"      [CACHE WARNING] Could not write cache: {cache_err}")

                conf_pct = int(result.confidence * 100) if result.confidence else 0
                print(f"      Doc Type   : {result.doc_type}")
                print(f"      Confidence : {conf_pct}%")
                print(f"      Summary    : {result.summary}")
                print(f"      Entries ({len(norm_entries)} detected):")

                for e_idx, e in enumerate(norm_entries, 1):
                    p_name = e.get("party", "Unknown")
                    p_type = e.get("type", "unknown")
                    p_amt = format_currency(e.get("amount"))
                    p_dt = e.get("txn_date", "No date")
                    p_due = e.get("due_date") or "-"
                    print(f"        {e_idx}. Party: '{p_name}' | Type: {p_type} | Amt: {p_amt} | Date: {p_dt} | Due: {p_due}")

                if result.warnings:
                    print(f"      Warnings   : {result.warnings}")

                runs_data.append({
                    "success": True,
                    "elapsed": t_elapsed,
                    "doc_type": result.doc_type,
                    "entries": norm_entries,
                    "warnings": result.warnings,
                })

            except Exception as run_err:
                t_elapsed = round(time.time() - t_start, 2)
                print(f" [FAILED] ({t_elapsed}s)")
                print(f"      Error: {run_err}")
                runs_data.append({
                    "success": False,
                    "elapsed": t_elapsed,
                    "error": str(run_err),
                })

            # Small breather between API calls to avoid rate limits
            if run_num < 3:
                time.sleep(1.0)

        # Consistency Summary for this image
        print(f"\n  --- Consistency Summary for '{filename}' ---")
        successful_runs = [r for r in runs_data if r["success"]]
        if not successful_runs:
            print(f"  [X] All 3 runs failed for {filename}.")
        elif len(successful_runs) < 3:
            print(f"  [!] {len(successful_runs)}/3 runs succeeded. Incomplete consistency comparison.")
        else:
            # Check entry counts
            counts = [len(r["entries"]) for r in successful_runs]
            doc_types = [r["doc_type"] for r in successful_runs]
            amounts_lists = [[e.get("amount") for e in r["entries"]] for r in successful_runs]
            parties_lists = [[e.get("party") for e in r["entries"]] for r in successful_runs]

            same_counts = len(set(counts)) == 1
            same_types = len(set(doc_types)) == 1
            same_amounts = all(amounts_lists[0] == a for a in amounts_lists[1:])
            same_parties = all(parties_lists[0] == p for p in parties_lists[1:])

            avg_latency = round(sum(r["elapsed"] for r in successful_runs) / len(successful_runs), 2)

            if same_counts and same_types and same_amounts and same_parties:
                print(f"  [OK] 100% CONSISTENT across all 3 runs.")
                print(f"       Entries: {counts[0]}, Amounts: {amounts_lists[0]}, Avg latency: {avg_latency}s")
            else:
                print(f"  [~] Variations observed between runs:")
                print(f"       Doc types : {doc_types}")
                print(f"       Counts    : {counts}")
                print(f"       Amounts   : {amounts_lists}")
                print(f"       Parties   : {parties_lists}")

        overall_results[filename] = runs_data

    # Final Summary Table
    print("\n" + "=" * 80)
    print("                      OVERALL BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"{'Image Filename':<26} | {'Runs Succeeded':<15} | {'Avg Latency':<12} | {'Consistent?'}")
    print("-" * 80)
    for fname, runs in overall_results.items():
        succ = [r for r in runs if r.get("success")]
        succ_str = f"{len(succ)}/3"
        avg_lat = f"{sum(r['elapsed'] for r in succ)/len(succ):.1f}s" if succ else "N/A"
        if len(succ) == 3:
            amts = [[e.get("amount") for e in r["entries"]] for r in succ]
            consistent = "YES (Identical)" if all(amts[0] == a for a in amts[1:]) else "MINOR VARIATION"
        else:
            consistent = "FAILED" if not succ else "PARTIAL"
        print(f"{fname:<26} | {succ_str:<15} | {avg_lat:<12} | {consistent}")
    print("=" * 80)
    print("[*] Completed. Real API results from the first run of each image have been")
    print("    saved into demo_cache/ for offline demo mode verification.")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
