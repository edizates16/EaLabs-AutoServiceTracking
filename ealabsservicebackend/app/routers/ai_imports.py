# app/routers/ai_imports.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
import os, uuid, re
import requests, json

from ..deps import get_db, require_roles, get_current_user

# ---- OCR / Görüntü işleme (offline) ----
# Sistem:  brew install tesseract poppler tesseract-lang
# Python:  pip install pytesseract pillow opencv-python pdf2image numpy pillow-heif
import pytesseract
from PIL import Image
import cv2
import numpy as np
from pdf2image import convert_from_path

router = APIRouter(
    prefix="/ai/imports",
    tags=["ai-imports"],
    dependencies=[Depends(require_roles(["AI_DIRECTOR", "OWNER"]))],  # sadece AI_DIRECTOR/OWNER
)

STORAGE_DIR = "./storage_uploads"
os.makedirs(STORAGE_DIR, exist_ok=True)

# In-memory import store (MVP)
IMPORTS: dict[int, dict] = {}
AUTO_ID = 0


# =========================================================
#                    OCR & PARSING
# =========================================================

def _pdf_to_images(path: str):
    # PDF -> PIL Image list (poppler gerekir)
    return convert_from_path(path, dpi=400)


def _prep_for_ocr(pil_img: Image.Image) -> Image.Image:
    """
    Gelişmiş hazırlık: unsharp, Otsu/Adaptive karşılaştırma, morfoloji ve otomatik döndürme.
    """
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Unsharp mask (kontrast/arttırma)
    blur = cv2.GaussianBlur(gray, (0, 0), 2.0)
    sharp = cv2.addWeighted(gray, 1.7, blur, -0.7, 0)

    # Otsu vs Adaptive: hangisi daha doluysa onu kullan
    th1 = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    th2 = cv2.adaptiveThreshold(
        sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
    )
    bw = th2 if cv2.countNonZero(th2) > cv2.countNonZero(th1) else th1

    # Hafif gürültü temizliği
    kernel = np.ones((2, 2), np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel, iterations=1)

    # Tesseract OSD ile deskew
    try:
        osd = pytesseract.image_to_osd(Image.fromarray(bw))
        m = re.search(r"Rotate:\s*(\d+)", osd)
        if m:
            angle = int(m.group(1)) % 360
            if angle:
                (h, w) = bw.shape[:2]
                M = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
                bw = cv2.warpAffine(
                    bw, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
                )
    except Exception:
        pass

    return Image.fromarray(bw)


def _ocr_image(pil_img: Image.Image) -> str:
    """
    Farklı PSM/OEM kombinasyonları ile dene. Türkçe varsa tur+eng.
    """
    tries = [
        ("tur+eng", "--oem 1 --psm 6"),  # tek sütun/karışık blok
        ("tur+eng", "--oem 1 --psm 4"),  # sütunlu
        ("eng",     "--oem 1 --psm 6"),
        ("eng",     "--oem 1 --psm 4"),
    ]
    for lang, cfg in tries:
        try:
            txt = pytesseract.image_to_string(pil_img, lang=lang, config=cfg)
            if txt and len(txt.strip()) > 10:
                return txt
        except Exception:
            continue
    return pytesseract.image_to_string(pil_img)


def _ocr_singleline(pil_img: Image.Image, lang="tur+eng") -> str:
    """
    Tek satırlık alanlar için (psm 7) — plaka, marka, model gibi.
    """
    try:
        return (pytesseract.image_to_string(pil_img, lang=lang, config="--oem 1 --psm 7") or "").strip()
    except Exception:
        return ""


def _load_and_ocr(path: str) -> str:
    """
    Tüm sayfayı OCR et (kalemler/Toplam için). HEIC desteği ve düşük çözünürlük büyütme var.
    """
    # HEIC desteği
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except Exception:
        pass

    text_chunks = []
    try:
        if path.lower().endswith(".pdf"):
            pages = _pdf_to_images(path)
            for p in pages[:5]:
                prepped = _prep_for_ocr(p)
                text_chunks.append(_ocr_image(prepped))
        else:
            pil = Image.open(path)
            if min(pil.size) < 1400:
                pil = pil.resize((int(pil.width * 1.6), int(pil.height * 1.6)))
            prepped = _prep_for_ocr(pil)
            text_chunks.append(_ocr_image(prepped))
    except Exception:
        return ""
    return "\n".join(text_chunks)


# ---------- Basit kural tabanlı ayrıştırıcılar ----------
_PLATE_RE = re.compile(r"\b(\d{2}\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,5})\b")
_DATE_RE  = re.compile(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b")
_MONEY_RE = re.compile(r"(?P<val>\d{1,3}(?:[\.\s]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?", re.IGNORECASE)

_BRANDS = [
    "RENAULT","FIAT","FORD","MERCEDES","MERCEDES-BENZ","VOLKSWAGEN","VW","OPEL","PEUGEOT",
    "BMW","AUDI","TOYOTA","HYUNDAI","HONDA","CITROEN","SKODA","DACIA","NISSAN","KIA"
]


def _extract_plate(text: str):
    m = _PLATE_RE.search(text.replace("I", "1"))  # I/1 karışıklığı
    if m:
        return re.sub(r"\s+", "", m.group(1).upper())
    return None


def _extract_date(text: str):
    m = _DATE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            pass
    return None


def _extract_brand_model(text: str):
    up = text.upper()
    brand = next((b for b in _BRANDS if b in up), None)
    model = None
    if brand:
        i = up.find(brand)
        tail = up[i + len(brand):].strip()
        cand = re.split(r"[^A-Z0-9ÇĞİÖŞÜ-]+", tail)
        if cand and cand[0] and len(cand[0]) >= 3:
            model = cand[0][:20]
    return (brand, model)


def _money_to_float(s: str) -> float:
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")  # 1.234,56 -> 1234.56
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _extract_totals(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    totals = {"subtotal": None, "vat_rate": 0.20, "vat_amount": None, "grand_total": None}
    for l in lines:
        low = l.lower()
        if "genel toplam" in low or "geneltoplam" in low:
            m = list(_MONEY_RE.finditer(l))
            if m:
                totals["grand_total"] = _money_to_float(m[-1].group("val"))
        elif "kdv" in low:
            perc = re.search(r"%\s*(\d+(?:[.,]\d+)?)", low)
            if perc:
                try:
                    totals["vat_rate"] = float(perc.group(1).replace(",", ".")) / 100.0
                except Exception:
                    pass
            m = list(_MONEY_RE.finditer(l))
            if m:
                totals["vat_amount"] = _money_to_float(m[-1].group("val"))
        elif "toplam" in low:
            m = list(_MONEY_RE.finditer(l))
            if m:
                totals["subtotal"] = _money_to_float(m[-1].group("val"))
    return totals


def _extract_items(text: str):
    """
    Para geçen satırları kalem sayar. 3x150, 2 x 120, 4 adet gibi miktarları yakalar.
    """
    items = []
    for line in text.splitlines():
        l = line.strip()
        if not l:
            continue
        prices = list(_MONEY_RE.finditer(l))
        if not prices:
            continue
        price = _money_to_float(prices[-1].group("val"))
        qty = 1
        mqty = re.search(r"(\d+)\s*[xX*]\s*\d", l)
        if mqty:
            qty = int(mqty.group(1))
        else:
            madet = re.search(r"(\d+)\s*(?:adet|psc|qty)", l, re.IGNORECASE)
            if madet:
                qty = int(madet.group(1))
        name = re.sub(_MONEY_RE, "", l)
        name = re.sub(r"\b(\d+\s*[xX*]\s*\d+)\b", "", name)
        name = re.sub(r"\s{2,}", " ", name).strip(":-— ").strip()
        if len(name) < 3:
            name = "Kalem"
        items.append({
            "type": "labor" if any(k in l.lower() for k in ["işçilik", "iscilik", "emek", "labour", "labor"]) else "part",
            "name": name[:120],
            "qty": qty,
            "price": round(price / max(qty, 1), 2) if qty > 1 else price
        })
    return items[:20]


# --------- Form'a özel: ROI okuma (üst-sağ kutular) ---------

def _ocr_roi_singleline(full_pil: Image.Image, box: tuple[float, float, float, float]) -> str:
    """
    box: (x1, y1, x2, y2) yüzde cinsinden (0..1)
    """
    W, H = full_pil.size
    x1, y1, x2, y2 = box
    crop = full_pil.crop((int(W * x1), int(H * y1), int(W * x2), int(H * y2)))
    # küçükse büyüt
    if min(crop.size) < 200:
        crop = crop.resize((crop.width * 2, crop.height * 2))
    crop_prep = _prep_for_ocr(crop)
    return _ocr_singleline(crop_prep)


def _extract_by_roi(full_pil: Image.Image) -> dict:
    """
    Paylaştığın form fotoğrafına göre ROI yüzdeleri.
    Gerekirse milim oynarız; çözünürlükten bağımsız çalışır.
    """
    # (sol, üst, sağ, alt) — yüzdeler
    roi_date  = (0.60, 0.11, 0.95, 0.17)
    roi_plate = (0.60, 0.17, 0.95, 0.23)
    roi_brand = (0.60, 0.23, 0.95, 0.29)
    roi_model = (0.60, 0.29, 0.95, 0.35)
    roi_km    = (0.60, 0.35, 0.95, 0.41)

    date_txt  = _ocr_roi_singleline(full_pil, roi_date)
    plate_txt = _ocr_roi_singleline(full_pil, roi_plate)
    brand_txt = _ocr_roi_singleline(full_pil, roi_brand)
    model_txt = _ocr_roi_singleline(full_pil, roi_model)
    km_txt    = _ocr_roi_singleline(full_pil, roi_km)

    # normalize plaka
    plate = plate_txt.upper().replace(" ", "").replace("|", "I")
    if len(plate) >= 6:
        plate = plate.replace("O", "0").replace("I", "1").replace("Z", "2")

    # tarih
    dt = None
    cleaned_date = re.sub(r"[^\d./-]", "", date_txt).strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(cleaned_date, fmt)
            break
        except Exception:
            continue

    # km
    km_num = None
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d+)", km_txt.replace(" ", ""))
    if m:
        val = m.group(1).replace(".", "").replace(",", "")
        try:
            km_num = int(val)
        except Exception:
            pass

    return {
        "plate": plate if len(plate) >= 6 else None,
        "brand": (brand_txt or "").strip().upper() or None,
        "model": (model_txt or "").strip().title() or None,
        "km": km_num,
        "date": dt,
    }


def parse_document_ocr(path: str) -> dict:
    # HEIC desteği
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except Exception:
        pass

    pil = Image.open(path)

    # ROI alanları
    roi = _extract_by_roi(pil)

    # Tam sayfa OCR (kalemler/toplamlar için). Fallback de var.
    text = _load_and_ocr(path)
    if not text or len(text.strip()) < 8:
        big = pil if min(pil.size) >= 1400 else pil.resize((int(pil.width * 1.6), int(pil.height * 1.6)))
        text = pytesseract.image_to_string(_prep_for_ocr(big), lang="tur+eng", config="--oem 1 --psm 6")

    items = _extract_items(text)
    brand2, model2 = _extract_brand_model(text)

    brand = roi.get("brand") or brand2
    model = roi.get("model") or model2
    plate = roi.get("plate")
    date  = roi.get("date") or _extract_date(text) or datetime.utcnow()
    km    = roi.get("km")

    # Müşteri adı (soldaki kutudan yakalama denemesi)
    cust_name = None
    for key in ["müşteri", "musteri"]:
        m = re.search(rf"{key}\s*[:\-]\s*([^\r\n]+)", text, flags=re.IGNORECASE)
        if m:
            cust_name = m.group(1).strip()[:120]
            break

    if not items:
        items = [{"type": "labor", "name": "İşçilik", "qty": 1, "price": 0.0}]

    return {
        "customer": {"type": "person", "name": cust_name or "Bilinmeyen", "phone": None, "email": None},
        "vehicle": {"plate": plate, "brand": brand, "model": model, "year": None, "km": km},
        "startedAt": date.isoformat(),
        "notes": None,
        "items": items,
        "status": "open",
    }


# =========================================================
#                 LLM ENTEGRASYONU (OLLAMA)
# =========================================================

def _build_llm_prompt(ocr_text: str) -> str:
    return f"""
Aşağıdaki metin bir servis iş emri/iş formundan OCR ile çekildi.
Dağınık, eksik, farklı formatlarda olabilir.
Sadece aşağıdaki JSON şemasını GEÇERLİ JSON olarak üret (yorum, açıklama, kod bloğu ekleme!):

ŞEMA:
{{
  "customer": {{"type": "person"|"company"|null, "name": string|null, "phone": string|null, "email": string|null}},
  "vehicle": {{"plate": string|null, "brand": string|null, "model": string|null, "year": int|null, "km": int|null}},
  "startedAt": string (ISO8601) | null,
  "notes": string|null,
  "items": [{{"type": "labor"|"part", "name": string, "qty": int, "price": float}}],
  "status": "open"|"closed"
}}

Kurallar:
- Uydurma bilgi koyma. Bulamadığını null bırak.
- "items" boşsa boş liste [] yap.
- "qty" yoksa 1, "price" yoksa 0.0 ver.
- "status" yoksa "open".
- Tarih bulamazsan null ver (bugünün tarihini icat etme).
- SADECE SAF JSON döndür.

OCR_METNİ:
---
{ocr_text}
---
""".strip()


def _ask_ollama_for_json(model: str, prompt: str, host: str = "http://localhost:11434") -> dict | None:
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = (data.get("response") or "").strip()

        # Kod bloğu/ek metin geldiyse temizle
        if raw.startswith("```"):
            # ör: ```json\n{...}\n```
            first = raw.find("{")
            last = raw.rfind("}")
            if first != -1 and last != -1:
                raw = raw[first:last+1]

        # İlk JSON bloğunu al
        if "{" in raw and "}" in raw:
            raw = raw[raw.find("{"): raw.rfind("}") + 1]

        return json.loads(raw)
    except Exception:
        return None


def _normalize_llm_json(d: dict) -> dict:
    # güvenli alan erişimi
    cust = (d.get("customer") or {}) if isinstance(d, dict) else {}
    veh  = (d.get("vehicle") or {}) if isinstance(d, dict) else {}
    items = d.get("items") or []
    if not isinstance(items, list): items = []

    def to_int(x):
        try:
            if x is None or x == "": return None
            return int(str(x).replace(".", "").replace(",", ""))
        except: return None

    def to_float(x):
        try:
            if x is None or x == "": return 0.0
            s = str(x).replace(" ", "").replace("TL","").replace("₺","")
            s = s.replace(".", "").replace(",", ".") if ("," in s and "." in s) else s.replace(",", ".")
            return float(s)
        except: return 0.0

    veh["year"] = to_int(veh.get("year"))
    veh["km"]   = to_int(veh.get("km"))

    norm_items = []
    for it in items:
        if not isinstance(it, dict): continue
        name = (it.get("name") or "").strip()
        if not name: continue
        qty_i = to_int(it.get("qty")) or 1
        price_f = to_float(it.get("price"))
        typ = (it.get("type") or "").lower()
        if typ not in ("labor","part"):
            typ = "labor" if any(k in name.lower() for k in ["işçilik","iscilik","emek","labour","labor"]) else "part"
        norm_items.append({"type": typ, "name": name[:120], "qty": qty_i, "price": price_f})

    startedAt = d.get("startedAt")
    if isinstance(startedAt, str):
        try:
            _ = datetime.fromisoformat(startedAt.replace("Z","+00:00"))
        except:
            startedAt = None

    status = d.get("status") or "open"
    if status not in ("open","closed"): status = "open"

    return {
        "customer": {
            "type": cust.get("type") if cust.get("type") in ("person","company") else "person",
            "name": cust.get("name") or "Bilinmeyen",
            "phone": cust.get("phone"),
            "email": cust.get("email"),
        },
        "vehicle": {
            "plate": veh.get("plate"),
            "brand": veh.get("brand"),
            "model": veh.get("model"),
            "year": veh.get("year"),
            "km": veh.get("km"),
        },
        "startedAt": startedAt or datetime.utcnow().isoformat(),
        "notes": d.get("notes"),
        "items": norm_items,
        "status": status,
    }


# =========================================================
#                       ENDPOINTS
# =========================================================

@router.post("", summary="Belge yükle ve AI ile taslak oluştur (yalnızca AI Director/Owner)")
async def import_document(
    file: UploadFile = File(...),
    user = Depends(get_current_user),
    include_debug: bool = Query(False, description="Ham OCR metnini ilk 1500 karakterle döndür")
):
    global AUTO_ID
    # 1) Dosyayı kaydet
    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(STORAGE_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(await file.read())

    # ---------- OCR ham metni ----------
    ocr_text = _load_and_ocr(fpath)

    # ---------- LLM ile alan çıkarımı (öncelik LLM) ----------
    parsed = None
    llm_used = False
    llm_model = os.getenv("OLLAMA_MODEL", "llama3")
    llm_host  = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    if ocr_text and len(ocr_text.strip()) > 0:
        prompt = _build_llm_prompt(ocr_text)
        llm_raw = _ask_ollama_for_json(llm_model, prompt, host=llm_host)
        if llm_raw:
            try:
                parsed_llm = _normalize_llm_json(llm_raw)
                if parsed_llm and isinstance(parsed_llm, dict) and parsed_llm.get("items") is not None:
                    parsed = parsed_llm
                    llm_used = True
            except Exception:
                parsed = None

    # ---------- LLM başarısızsa: kural tabanlı OCR fallback ----------
    if not parsed:
        parsed = parse_document_ocr(fpath)

    debug_raw = (ocr_text or "") if include_debug else None

    # 3) Bellekte import kaydı
    AUTO_ID += 1
    IMPORTS[AUTO_ID] = {
        "id": AUTO_ID,
        "file_path": fpath,
        "owner_user_id": user.id,
        "status": "parsed",            # queued/parsed/failed/committed
        "parsed_json": parsed,         # UI düzeltmesi için
        "raw_text": debug_raw,         # sadece debug amaçlı
        "created_at": datetime.utcnow().isoformat(),
        "llm_used": llm_used,
        "llm_model": llm_model if llm_used else None,
    }
    resp = {"import_id": AUTO_ID, "status": "parsed", "parsed_json": parsed, "llm_used": llm_used}
    if include_debug:
        resp["debug_raw"] = (debug_raw or "")[:1500]
    return resp


@router.get("/{import_id}", summary="Import durum/taslak getir")
def get_import(import_id: int):
    imp = IMPORTS.get(import_id)
    if not imp:
        raise HTTPException(404, "Import not found")
    return imp


@router.patch("/{import_id}/parsed", summary="Parsed JSON'ı güncelle (UI düzeltmesi)")
def patch_parsed(import_id: int, payload: dict):
    imp = IMPORTS.get(import_id)
    if not imp:
        raise HTTPException(404, "Import not found")
    base = imp["parsed_json"]
    base.update(payload)  # shallow merge
    imp["parsed_json"] = base
    return {"ok": True, "parsed_json": base}


@router.post("/{import_id}/to-order", summary="Taslak veriden sipariş (Order) oluştur")
def import_to_order(import_id: int, db: Session = Depends(get_db)):
    # Döngüyü kırmak için lazy import
    from ..main import Customer, Vehicle, Order, OrderItem

    imp = IMPORTS.get(import_id)
    if not imp:
        raise HTTPException(404, "Import not found")
    data = imp["parsed_json"] or {}

    # --- Customer upsert (basit) ---
    cust_name = (data.get("customer", {}) or {}).get("name") or "Müşteri"
    customer = db.query(Customer).filter(Customer.name.ilike(cust_name)).first()
    if not customer:
        cdata = data.get("customer") or {}
        customer = Customer(
            type=cdata.get("type") or "person",
            name=cust_name,
            phone=cdata.get("phone"),
            email=cdata.get("email"),
        )
        db.add(customer)
        db.flush()

    # --- Vehicle upsert (basit) ---
    vdata = data.get("vehicle", {}) or {}
    plate = (vdata.get("plate") or "").strip().upper()
    vehicle = db.query(Vehicle).filter(Vehicle.plate == plate).first() if plate else None
    if not vehicle:
        vehicle = Vehicle(
            plate=plate or "PLAKASIZ",
            brand=vdata.get("brand"),
            model=vdata.get("model"),
            year=vdata.get("year"),
            km=vdata.get("km"),
        )
        db.add(vehicle)
        db.flush()
    else:
        for k in ("brand", "model", "year", "km"):
            val = vdata.get(k)
            if val not in (None, "", 0):
                setattr(vehicle, k, val)

    # --- Order ---
    started = data.get("startedAt") or datetime.utcnow().isoformat()
    started_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00")) if isinstance(started, str) else started
    order = Order(
        customer=customer,
        vehicle=vehicle,
        started_at=started_dt,
        notes=data.get("notes"),
        status=data.get("status") or "open",
    )
    db.add(order)
    db.flush()

    # --- Items ---
    for it in data.get("items", []):
        db.add(OrderItem(
            order=order,
            type=it.get("type") or "labor",
            name=it.get("name") or "Kalem",
            qty=int(it.get("qty") or 1),
            price=float(it.get("price") or 0.0),
        ))

    db.commit()
    db.refresh(order)

    imp["status"] = "committed"
    imp["order_id"] = order.id

    total = sum(i.qty * (i.price or 0) for i in order.items)
    return {
        "order_id": order.id,
        "plate": vehicle.plate,
        "customer": customer.name,
        "status": order.status,
        "item_count": len(order.items),
        "total": round(total, 2),
    }