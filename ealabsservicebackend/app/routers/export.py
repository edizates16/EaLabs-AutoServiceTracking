from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse
from pydantic import BaseModel, UUID4
from typing import List
import io, zipfile, datetime, os

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm

router = APIRouter(prefix="/export", tags=["export"])

# Türkçe karakter desteği için bir TTF font ekleyin (projeye koyun: app/assets/DejaVuSans.ttf)
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "DejaVuSans.ttf")
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("DejaVu", FONT_PATH))
    BASE_FONT = "DejaVu"
else:
    BASE_FONT = "Helvetica"  # geçici fallback

class ExportRequest(BaseModel):
    order_ids: List[UUID4]

# ---- Bu fonksiyonu kendi ORM/CRUD’unla eşleştir ----
def fetch_orders_by_ids(ids: List[str]):
    """
    Her order için şu alanlar döndüğünü varsayıyoruz:
    {
      "id": "...", "number": "BLG-2025-0001",
      "created_at": datetime, "total": 1234.56, "vat": 224.22,
      "customer": {"name": "ACME Ltd", "email": "x@y.com", "phone": "5xx..."},
      "vehicle": {"plate":"16ABC123","brand":"Ford","model":"Focus","year":2009,"km":226000},
      "items": [{"desc":"Yağ filtresi","qty":1,"unit_price":300.0},
                {"desc":"Motor yağı 5W-30","qty":4,"unit_price":180.0}]
    }
    """
    # TODO: DB sorgusu
    raise NotImplementedError

def _draw_order_pdf(order) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    c.setTitle(f"IsEmri_{order['number']}")
    c.setFont(BASE_FONT, 14)

    # Üst başlık
    c.drawString(20*mm, H - 20*mm, "BİLGİ OTOMOTİV - SERVİS İŞ EMRİ")
    c.setFont(BASE_FONT, 10)
    c.drawString(20*mm, H - 27*mm, f"İş Emri No: {order['number']}")
    c.drawString(90*mm, H - 27*mm, f"Tarih: {order['created_at'].strftime('%d.%m.%Y %H:%M')}")

    # Müşteri & Araç
    y = H - 40*mm
    c.drawString(20*mm, y, f"Müşteri: {order['customer'].get('name','')}")
    c.drawString(20*mm, y-6*mm, f"E-posta: {order['customer'].get('email','-')}")
    c.drawString(20*mm, y-12*mm, f"Telefon: {order['customer'].get('phone','-')}")
    c.drawString(110*mm, y, f"Plaka: {order['vehicle'].get('plate','')}")
    c.drawString(110*mm, y-6*mm, f"Marka/Model: {order['vehicle'].get('brand','')} {order['vehicle'].get('model','')}")
    c.drawString(110*mm, y-12*mm, f"Yıl/Km: {order['vehicle'].get('year','-')} / {order['vehicle'].get('km','-')}")

    # Kalemler tablosu
    y = y - 22*mm
    c.setFont(BASE_FONT, 10)
    c.drawString(20*mm, y, "Açıklama")
    c.drawString(120*mm, y, "Adet")
    c.drawString(140*mm, y, "B.Fiyat")
    c.drawString(165*mm, y, "Tutar")
    y -= 5*mm
    c.line(20*mm, y, 190*mm, y)
    y -= 6*mm

    for it in order["items"]:
        line_total = it["qty"] * it["unit_price"]
        c.drawString(20*mm, y, str(it["desc"])[:60])
        c.drawRightString(135*mm, y, f"{it['qty']}")
        c.drawRightString(160*mm, y, f"{it['unit_price']:.2f} ₺")
        c.drawRightString(190*mm, y, f"{line_total:.2f} ₺")
        y -= 6*mm
        if y < 30*mm:  # yeni sayfa
            c.showPage()
            c.setFont(BASE_FONT, 10)
            y = H - 20*mm

    # Toplamlar
    y = max(y, 40*mm)
    c.line(120*mm, y, 190*mm, y)
    y -= 8*mm
    c.drawRightString(160*mm, y, "Ara Toplam:")
    c.drawRightString(190*mm, y, f"{(order['total'] - order.get('vat',0)):.2f} ₺")
    y -= 6*mm
    c.drawRightString(160*mm, y, "KDV:")
    c.drawRightString(190*mm, y, f"{order.get('vat',0):.2f} ₺")
    y -= 6*mm
    c.setFont(BASE_FONT, 11)
    c.drawRightString(160*mm, y, "Genel Toplam:")
    c.drawRightString(190*mm, y, f"{order['total']:.2f} ₺")

    c.showPage()
    c.save()
    return buf.getvalue()

@router.post("/pdf-zip")
def export_orders_as_pdf_zip(req: ExportRequest):
    try:
        orders = fetch_orders_by_ids([str(i) for i in req.order_ids])
    except NotImplementedError:
        raise HTTPException(500, "fetch_orders_by_ids() bağlanmalı")

    if not orders:
        raise HTTPException(404, "Kayıt bulunamadı")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for o in orders:
            pdf_bytes = _draw_order_pdf(o)
            safe_no = o["number"].replace("/", "-")
            zf.writestr(f"{safe_no}.pdf", pdf_bytes)

    zip_buf.seek(0)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    headers = {
        "Content-Disposition": f'attachment; filename="is_emirleri_{stamp}.zip"'
    }
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)