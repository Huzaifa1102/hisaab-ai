"""
create_test_images.py — Generates test images for Hisaab AI in test_images/
Creates realistic mock photos of:
1. IESCO Utility Bill
2. Handwritten Khata Page
3. Supplier Wholesale Invoice
4. Cash Purchase Receipt
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent / "test_images"
OUT_DIR.mkdir(exist_ok=True)

def create_bill_image():
    img = Image.new("RGB", (900, 1200), color="#FBFBEE")
    draw = ImageDraw.Draw(img)
    
    # Header
    draw.rectangle([(20, 20), (880, 110)], fill="#1E3A8A")
    draw.text((40, 35), "ISLAMABAD ELECTRIC SUPPLY COMPANY (IESCO)", fill="#FFFFFF")
    draw.text((40, 70), "COMMERCIAL POWER BILL — SUB DIVISION: G-9 ISLAMABAD", fill="#93C5FD")
    
    # Consumer details
    draw.rectangle([(20, 130), (880, 240)], outline="#CBD5E1", width=2)
    draw.text((40, 145), "Consumer: MADINA GENERAL STORE", fill="#0F172A")
    draw.text((40, 175), "Consumer No: 08-1423-098234-U", fill="#334155")
    draw.text((40, 205), "Tariff: A-2 Commercial Single Phase", fill="#334155")
    draw.text((500, 145), "Bill Month: OCT 2026", fill="#0F172A")
    draw.text((500, 175), "Issue Date: 08/10/2026", fill="#334155")
    draw.text((500, 205), "Due Date: 12/10/2026", fill="#DC2626")
    
    # Units table
    draw.rectangle([(20, 260), (880, 520)], outline="#CBD5E1", width=2)
    draw.rectangle([(20, 260), (880, 300)], fill="#F1F5F9")
    draw.text((40, 272), "Description", fill="#0F172A")
    draw.text((650, 272), "Amount (PKR)", fill="#0F172A")
    
    draw.text((40, 320), "Cost of Electricity (240 Units @ commercial slab)", fill="#334155")
    draw.text((650, 320), "Rs 6,200", fill="#334155")
    
    draw.text((40, 360), "Fuel Price Adjustment (FPA)", fill="#334155")
    draw.text((650, 360), "Rs 1,140", fill="#334155")
    
    draw.text((40, 400), "General Sales Tax (GST) & TV License", fill="#334155")
    draw.text((650, 400), "Rs 500", fill="#334155")
    
    # Totals box
    draw.rectangle([(450, 550), (880, 680)], fill="#FEF2F2", outline="#DC2626", width=3)
    draw.text((470, 565), "AMOUNT PAYABLE WITHIN DUE DATE:", fill="#991B1B")
    draw.text((470, 605), "Rs 7,840/-", fill="#B91C1C")
    draw.text((470, 645), "(Late Payment Surcharge: Rs 8,350)", fill="#64748B")
    
    img.save(OUT_DIR / "electricity_bill.png")

def create_khata_image():
    img = Image.new("RGB", (900, 1100), color="#FFFDF7")
    draw = ImageDraw.Draw(img)
    
    # Ruled register lines
    for y in range(80, 1050, 60):
        draw.line([(30, y), (870, y)], fill="#E2E8F0", width=1)
    draw.line([(30, 80), (30, 1040)], fill="#CBD5E1", width=2)
    draw.line([(280, 80), (280, 1040)], fill="#CBD5E1", width=2)
    draw.line([(620, 80), (620, 1040)], fill="#CBD5E1", width=2)
    draw.line([(870, 80), (870, 1040)], fill="#CBD5E1", width=2)
    
    # Title
    draw.text((40, 35), "KIRYANA KHATA REGISTER — 09/10/2026", fill="#0F172A")
    draw.text((40, 95), "Customer Name", fill="#1E293B")
    draw.text((290, 95), "Tafseel (Details)", fill="#1E293B")
    draw.text((630, 95), "Raqam (PKR)", fill="#1E293B")
    
    rows = [
        ("Ahmed Raza", "Aata 10kg + ghee 2.5kg (udhaar)", "2,500/-"),
        ("Bushra Bibi", "jama karwaye wasool (cash wapis)", "1,500/-"),
        ("Faisal Khan", "Sugar 5kg + basmati chawal (baqi)", "3,400/-"),
        ("Naqd Bikri", "Counter cash sale subah", "4,200/-"),
        ("Total Baqi Balance", "Pichla khata total (record)", "7,400"),
    ]
    
    curr_y = 155
    for name, desc, amt in rows:
        draw.text((40, curr_y), name, fill="#0F172A")
        draw.text((290, curr_y), desc, fill="#334155")
        draw.text((630, curr_y), amt, fill="#0F172A")
        curr_y += 60
        
    img.save(OUT_DIR / "khata_register.png")

def create_invoice_image():
    img = Image.new("RGB", (900, 1100), color="#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(20, 20), (880, 130)], fill="#047857")
    draw.text((40, 40), "AL-FATAH WHOLESALE GRAIN & SPICE MERCHANTS", fill="#FFFFFF")
    draw.text((40, 75), "Gunj Mandi, Rawalpindi | Phone: 051-5559821", fill="#A7F3D0")
    
    draw.text((40, 150), "Billed To: Madina General Store", fill="#0F172A")
    draw.text((40, 180), "Invoice #: AF-8942", fill="#334155")
    draw.text((550, 150), "Date: 07-10-2026", fill="#0F172A")
    draw.text((550, 180), "Payment Terms: Paid in Cash", fill="#334155")
    
    # Table headers
    draw.rectangle([(20, 230), (880, 270)], fill="#F1F5F9")
    draw.text((40, 240), "Item / Description", fill="#0F172A")
    draw.text((420, 240), "Qty", fill="#0F172A")
    draw.text((550, 240), "Rate", fill="#0F172A")
    draw.text((700, 240), "Total (PKR)", fill="#0F172A")
    
    items = [
        ("Sugar (Cheeni) 50kg Bag", "2 bags", "7,250", "Rs 14,500"),
        ("Super Basmati Rice 25kg", "3 bags", "6,200", "Rs 18,600"),
        ("Daal Chana Fine 20kg", "1 sack", "5,400", "Rs 5,400"),
    ]
    
    y = 290
    for it, q, r, t in items:
        draw.text((40, y), it, fill="#1E293B")
        draw.text((420, y), q, fill="#1E293B")
        draw.text((550, y), r, fill="#1E293B")
        draw.text((700, y), t, fill="#1E293B")
        draw.line([(20, y + 35), (880, y + 35)], fill="#E2E8F0", width=1)
        y += 50
        
    draw.rectangle([(500, 480), (880, 560)], fill="#ECFDF5", outline="#059669", width=2)
    draw.text((520, 495), "GRAND TOTAL (PAID):", fill="#065F46")
    draw.text((520, 525), "PKR 38,500/-", fill="#047857")
    
    img.save(OUT_DIR / "supplier_invoice.png")

def create_receipt_image():
    img = Image.new("RGB", (800, 900), color="#FAFAFA")
    draw = ImageDraw.Draw(img)
    
    draw.text((250, 40), "PACKAGING DEPOT", fill="#0F172A")
    draw.text((220, 70), "Wholesale Plastic & Paper Bags", fill="#475569")
    draw.text((270, 95), "Date: 06/10/2026", fill="#475569")
    draw.line([(50, 130), (750, 130)], fill="#CBD5E1", width=2)
    
    draw.text((70, 160), "1. Polythene Bags (Large 5kg pack)", fill="#1E293B")
    draw.text((580, 160), "Rs 2,500", fill="#1E293B")
    draw.text((70, 210), "2. Wrapping Paper Rolls (2 pcs)", fill="#1E293B")
    draw.text((580, 210), "Rs 800", fill="#1E293B")
    
    draw.line([(50, 270), (750, 270)], fill="#CBD5E1", width=2)
    draw.text((70, 300), "TOTAL CASH PAID:", fill="#0F172A")
    draw.text((580, 300), "Rs 3,300/-", fill="#0F172A")
    
    img.save(OUT_DIR / "grocery_receipt.png")

if __name__ == "__main__":
    create_bill_image()
    create_khata_image()
    create_invoice_image()
    create_receipt_image()
    print("Test images generated successfully in test_images/!")
