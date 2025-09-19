# app/ai/parsers.py
import re
from typing import Dict, List, Tuple

PLATE_RE = re.compile(r"\b([0-9]{2}\s?[A-Z]{1,3}\s?[0-9]{2,4})\b")
PHONE_RE = re.compile(r"(\+?90\s?)?0?\s?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
KM_RE = re.compile(r"\b(\d{4,7})\s?km\b", re.IGNORECASE)
CURRENCY_LINE_RE = re.compile(r"(ara toplam|subtotal|toplam|total|kdv|vat)\s*[:\-]?\s*([\d\.,]+)", re.IGNORECASE)

ITEM_LINE_RE = re.compile(
    r"(?P<name>[A-Za-zÇĞİÖŞÜçğışöü0-9\.\-\/\s]+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s*[xX×]\s*(?P<unit>[\d\.,]+)",
    re.UNICODE
)

def extract_simple_fields(text: str) -> Dict:
    plate = PLATE_RE.search(text)
    phone = PHONE_RE.search(text)
    email = EMAIL_RE.search(text)
    km = KM_RE.search(text)

    monetary = {}
    for m in CURRENCY_LINE_RE.finditer(text):
        k = m.group(1).lower()
        v = m.group(2).replace(".", "").replace(",", ".")
        try:
            monetary[k] = float(v)
        except:
            pass

    return {
        "plate": plate.group(1) if plate else None,
        "phone": phone.group(1) if phone else None,
        "email": email.group(0) if email else None,
        "km": int(km.group(1)) if km else None,
        "monetary": monetary,
    }

def extract_items(text: str) -> List[Tuple[str,float,float]]:
    items = []
    for m in ITEM_LINE_RE.finditer(text):
        name = m.group("name").strip()
        qty = float(m.group("qty").replace(",", "."))
        unit = float(m.group("unit").replace(".", "").replace(",", "."))
        items.append((name, qty, unit))
    return items
