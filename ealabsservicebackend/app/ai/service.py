# app/ai/service.py
from .schemas import ExtractResult, CustomerGuess, VehicleGuess, OrderItemGuess
from .ocr import image_bytes_to_text
from . import parsers

def merge_texts(texts):
    # çoklu görselde birleştir, sırayla
    return "\n\n---PAGE BREAK---\n\n".join(texts)

def compute_confidence(value, fallback=0.7):
    return 0.9 if value else 0.0 if value is None else fallback

def extract_from_images(files) -> (ExtractResult, str):
    raw_texts = []
    for f in files:
        content = f.file.read()
        raw_texts.append(image_bytes_to_text(content))

    raw_text = merge_texts(raw_texts)
    basic = parsers.extract_simple_fields(raw_text)
    items_raw = parsers.extract_items(raw_text)

    low = []

    customer = CustomerGuess(
        name=None,
        phone=basic["phone"],
        email=basic["email"],
        confidence=compute_confidence(basic["phone"] or basic["email"], 0.6)
    )
    if customer.confidence < 0.75: low.append("customer")

    vehicle = VehicleGuess(
        plate=basic["plate"],
        vin=None,
        brand=None,
        model=None,
        year=None,
        km=basic["km"],
        confidence=compute_confidence(basic["plate"] or basic["km"], 0.6)
    )
    if vehicle.confidence < 0.75: low.append("vehicle")

    items = [
        OrderItemGuess(type="labor", name=n, qty=q, unit_price=u, confidence=0.6)
        for (n,q,u) in items_raw
    ]
    if not items: low.append("items")

    subtotal = basic["monetary"].get("ara toplam") or basic["monetary"].get("subtotal")
    vat = basic["monetary"].get("kdv") or basic["monetary"].get("vat")
    total = basic["monetary"].get("toplam") or basic["monetary"].get("total")

    result = ExtractResult(
        customer=customer,
        vehicle=vehicle,
        complaint=None,
        items=items,
        currency="TRY",
        subtotal=subtotal,
        vat=vat,
        total=total,
        low_confidence_fields=low
    )
    return result, raw_text
