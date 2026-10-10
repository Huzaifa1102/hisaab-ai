# Demo runbook: Hisaab AI, 11 October 2026, 09:14

## Tonight (one person, about 15 minutes)

1. **Fix the model in `.env`.** Open `.env` and set:
   ```
   GEMINI_MODEL=gemini-3.8-flash
   ```
   `gemini-2.5-flash` is no longer available to new users, and every live scan fails with it. (You can also type the model into the sidebar, but `.env` makes it stick.)
2. **Check the Gemini quota.** On 10 Oct the key returned "You exceeded your current quota" after the test runs. If it still fails tomorrow morning, put a second key in the sidebar's "Use a different Gemini API Key" box, or present in Offline demo mode.
3. **Update and install:**
   ```
   git pull origin main
   pip install -r requirements.txt
   ```
4. **Optional, if the quota allows:** turn the two sample cache files into real scans:
   ```
   python test_live_images.py
   ```

## Morning pre-flight (09:00)

- [ ] Laptop on charger, notifications off, browser zoom 100%.
- [ ] `streamlit run app.py`. The header shows **Live AI Engine (gemini-3.8-flash)**.
- [ ] Sidebar shows both keys as "loaded from .env (hidden)".
- [ ] Tick "Replace current ledger with demo data", then click **Load Demo Ledger**.
- [ ] One test scan of `test_images/electricity_bill.png`. If it takes more than about 50 seconds or fails, plan to present in Offline demo mode.

## The demo (about 3 minutes)

1. **The problem (20 s).** Hold up a paper khata: "Every entry here is typed again by hand in today's khata apps, or never digitised."
2. **Scan (60 s).** Smart Scan → upload `electricity_bill.png` → Extract with AI. Point out the review table: the AI proposes and the shopkeeper confirms. Save.
   - With the demo ledger loaded on 11 Oct, the scanned IESCO bill (Rs 7,840, 8 Oct) matches the demo entry, so a **"Potential duplicate"** warning appears. Use it: "it caught that this bill is already in the khata", then click Discard instead of Save.
   - *Fallback:* if it fails, click **Use saved result** (the banner says it is an earlier live scan), or turn on Offline demo mode first.
3. **Bill alert (20 s).** Dashboard: the IESCO bill shows as due in 2 days.
4. **Udhaar and WhatsApp (40 s).** Udhaar → Faisal Khan → Draft AI Reminder in Roman Urdu → Open in WhatsApp.
5. **Ask your hisaab (20 s).** "Sab se zyada udhaar kis ka hai?" The answer is labelled as AI or offline.
6. **Why we're different (20 s).** "No Pakistani khata app we checked reads a photo of the register, scans utility bills or takes Urdu voice. We never guess an amount."

## Offline demo mode: what is real

| Image | Saved result |
|---|---|
| `electricity_bill.png` | Real gemini-3.8-flash scan (10 Oct) |
| `grocery_receipt.png` | Real gemini-3.8-flash scan (10 Oct) |
| `khata_register.png` | Hand-made sample; the banner says so |
| `supplier_invoice.png` | Hand-made sample; the banner says so |

Prefer the first two when demonstrating offline.

## If something goes wrong

| Symptom | Do this |
|---|---|
| "Model … was not found" | Type `gemini-3.8-flash` in the sidebar's Gemini Model field. |
| "API key has used up its quota" | Paste a second key in the sidebar, or turn on Offline demo mode. |
| "did not answer in time" | Click **Use saved result**, or turn on Offline demo mode. |
| "Could not reach Gemini" | No internet: turn on Offline demo mode. |
| Camera permission prompt | Only appears after turning on "Use device camera". Upload a file instead. |

## Likely judge questions

See "Where competitors are stronger" in [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md) for prepared answers on scale, mobile apps, payments, cost and accuracy.
