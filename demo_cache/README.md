# Offline Demo Mode Cache

This directory holds pre-saved extraction JSON files for **Offline Demo Mode**.

## Why this exists
In live hackathons, trade expos, or rural kiryana store demos, internet connectivity may drop or be completely unavailable. 
Offline Demo Mode guarantees a 100% resilient fallback that judges and shopkeepers can test without delay.

## How it works
1. **Automatic Caching**: Whenever a live extraction succeeds, Hisaab AI automatically saves the structured output JSON into this folder under the image filename without extension (e.g. `electricity_bill.json` for `electricity_bill.jpg`).
2. **Offline Toggle**: When the shopkeeper or presenter turns on the "Offline demo mode (use saved results)" toggle in the sidebar, the application loads these pre-extracted JSON results instead of sending API requests over the internet.
3. **Transparent Banner**: When an offline result is loaded, Hisaab AI displays a clear warning banner:
   `"Offline demo mode: showing a saved result for this image."`
   This ensures complete transparency with no silent substitutions.
4. **Fallback on Failure**: If a live API call fails due to internet interruption and a cached entry exists for the image, the UI offers an explicit "Use saved result for this image" button. Nothing is ever loaded from here without the toggle or that click.
5. **Camera photos** are never cached or matched, because their file name does not identify the document.

## Where these files must come from
Only real API results belong here. Regenerate them with a valid key in `.env`:

```
python test_live_images.py
```

This scans every image in `test_images/` three times and saves the first successful real result of each.
