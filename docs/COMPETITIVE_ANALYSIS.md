# Hisaab AI: competitive analysis

Researched on 10 October 2026 from public sources (vendor sites, app stores, press). In the table, ✗ means **not found in public information**, not proven absent. "?" means unverified. Sources are listed at the end. Re-check anything marked "?" on a phone's Play Store before quoting it.

## Where Hisaab AI stands

| App (country) | Photo / receipt scan | Handwritten khata scan | Utility bill scan + due alerts | Urdu voice entry | Ask questions about the ledger | AI-written WhatsApp reminders | Review before save | Price | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Hisaab AI** (PK) | ✓ | ✓ | ✓ | ✓ | ✓ (Urdu, Roman Urdu, English) | ✓ (3 scripts) | ✓ | Free, open source | Hackathon prototype (web app) |
| Udhaar Book (PK) | ✗ | ✗ | ✗ (pays bills for a fee; no scanning or alerts) | ✗ | ✗ | Template only | n/a | Free | Active; claims 5.1M merchants |
| DigiKhata (PK) | ✗ | ✗ | ✗ | ✗ | ✗ | Template only | n/a | Free; Pro on iOS | Active; payments, QR/NFC, small loans |
| Easy Khata / Bazaar (PK) | ✗ | ✗ | ✗ | ? | ✗ | Template only | n/a | Free | ? (5M+ installs; no longer featured by Bazaar) |
| CreditBook (PK) | ✗ | ✗ | ✗ | ✗ | ✗ | Was SMS/WhatsApp | n/a | n/a | Pivoted to SME lending |
| Sauda (PK) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Free | Active; offline POS and inventory |
| Khatabook (IN) | ✗ | ✗ | ✗ | ✗ (IVR call reminders) | ✗ | Template only | n/a | Freemium | Active; about 10M merchants; no Urdu found |
| OkCredit (IN) | ✗ | ✗ | ✗ | ✗ | ✗ | Template + UPI link | n/a | Freemium | Active; 11 Indian languages, no Urdu |
| Vyapar (IN) | ✓ (printed, English only) | ? | ✗ | ✗ | ✗ | ? | ✓ | Premium for OCR | Active |
| VoiceKhata (IN) | ✗ | ✗ | ✗ | ✗ (Hindi/Hinglish) | Partial | One-tap WhatsApp | ? | ₹199/month | Active |
| KhataBuddy / INVBot / Khata Bhai (IN) | ✓ | ✓ claimed | ✗ | Hindi/English | ? | ✓ (Khata Bhai) | ✓ (KhataBuddy) | Trial / unlisted | Active; India GST focus |

## What makes Hisaab AI different

1. **It reads the paper khata the shopkeeper already keeps.** None of the Pakistani khata apps checked (Udhaar Book, DigiKhata, Easy Khata, CreditBook, Sauda) offer photo entry at all. The Indian scanning tools target English, GST-style invoices; Vyapar says its OCR works best in English. No public product was found that reads handwritten Urdu or Roman Urdu khata pages.
2. **It takes entries by Urdu voice.** VoiceKhata shows the demand in India, but supports Hindi/Hinglish only. No Pakistani khata app with voice entry was found.
3. **It knows Pakistani bills.** It scans IESCO, LESCO, K-Electric, SNGPL, SSGC and PTCL bills and warns before the due date. Udhaar Book lets shops pay bills for a commission, but no app was found that scans them or tracks due dates.
4. **AI you can audit.** It never guesses an amount: unreadable amounts are dropped with a warning, every extraction is reviewed before saving, and every answer is labelled "AI answer" or "Calculated from your ledger (offline, not AI)".
5. **It talks like the shop.** It drafts polite reminders in Roman Urdu, Urdu script or English, and answers questions about the ledger in the language they were asked in. Competitors send fixed templates.

## Where competitors are stronger (prepare answers)

| Judge may say | Honest answer |
|---|---|
| "Udhaar Book and DigiKhata have millions of users." | They digitise *typing*. We remove typing: a photo of the existing register or a voice note. That is the step that keeps most shops on paper. |
| "No mobile app, no cloud backup or sync." | Correct for this prototype. The AI pipeline (scan, normalise, review, save) is separate from the UI (`core.py`), so it can sit behind a mobile app or WhatsApp bot next. |
| "No payments, inventory or loans." | Deliberate scope. We integrate with payments via WhatsApp links rather than compete; the ledger data we create is what lenders like CreditBook need. |
| "Needs internet and paid AI calls." | Yes. Each scan is one Gemini call. Offline demo mode shows saved results with a clear banner, and the app never invents data when offline. |
| "Can incumbents just add OCR?" | They can add printed-receipt OCR. Urdu handwriting, Roman Urdu voice and Pakistani bill formats need local tuning, which is our focus. |
| "How accurate is it?" | In a live test on 10 Oct, gemini-3.8-flash read the IESCO bill (Rs 7,840, due 12 Oct) and a cash receipt (Rs 3,300) correctly, with identical results on repeated runs. Those are clean generated images; accuracy on real handwritten pages is not measured yet and is the next step. |

## Market (estimates, no official census)

- **700,000+** kiryana stores in Pakistan, handling about **70%** of grocery purchases (Dawn Aurora; the figure dates from 2012).
- **900,000** grocery retailers, many "still run on pen-and-paper systems" (SnappRetail CEO, TechCrunch, September 2022).
- **5.2 million** SMEs, about 40% of GDP (Prime Minister's briefing, August 2024).
- No survey was found that measures the share of shops using paper khatas, so don't quote a percentage.

## Still unverified

Khatabook's current in-app features; whether Easy Khata is still maintained; whether a "Dukaan AI" bill scanner exists; Vyapar's availability in Pakistan.

## Sources

- Udhaar Book: https://udhaar.pk/ · https://www.dawn.com/news/1656795/pakistani-digital-bookkeeping-app-raises-6m-in-seed-funding
- DigiKhata: https://digikhata.pk/ · https://apps.apple.com/app/id1571599845
- Easy Khata / Bazaar: https://apkcombo.com/easy-khata-apka-digital-khata/com.tech.bazaar.easykhata/ · https://www.bazaartech.com/
- CreditBook: https://creditbook.pk/ · https://techcrunch.com/2021/12/16/tiger-global-backs-fintech-creditbook-in-first-pakistan-investment/
- Sauda: https://www.saudaapps.com/blog/quickbooks-alternative-pakistan
- Khatabook: https://varindia.com/news/khatabook-launches-automated-bot-call-reminder-feature
- OkCredit: https://okcredit.in/
- Vyapar: https://vyaparapp.in/ocr-scanner-software
- VoiceKhata: https://voicekhata.com/
- KhataBuddy / INVBot / Khata Bhai: https://khatabuddy.ai/bill-scanning-software/ · https://www.capterra.com/p/10039639/Khata-Bhai/
- Market: https://aurora.dawn.com/news/1141706 · https://techcrunch.com/2022/09/06/snappretail-helps-pakistans-kiryanas-compete-against-supermarkets · https://www.pakistantoday.com.pk/2024/08/23/smes-act-as-backbone-of-the-countrys-economy-pm-emphasizes
