from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit

# Basit bir PDF oluşturucu – tek sayfa iş emri özeti

def render_service_order_pdf(filepath: str, order: dict, items: list):
    c = canvas.Canvas(filepath, pagesize=A4)
    W, H = A4

    def text(x, y, s):
        c.drawString(x, y, s)

    c.setFont("Helvetica-Bold", 16)
    text(20*mm, 280*mm, "Bilgi Otomotiv – İş Emri")

    c.setFont("Helvetica", 10)
    y = 265*mm
    for line in [
        f"İş Emri ID: {order['id']}",
        f"Araç ID: {order['vehicle_id']}",
        f"Müşteri ID: {order['customer_id']}",
        f"Açılış: {order['opened_at']}",
        f"KM: {order.get('odometer_km')}",
        f"Durum: {order.get('status')}",
        f"Not: {order.get('notes') or '-'}",
    ]:
        text(20*mm, y, line)
        y -= 6*mm

    y -= 4*mm
    c.setFont("Helvetica-Bold", 12)
    text(20*mm, y, "Kalemler")
    y -= 8*mm

    c.setFont("Helvetica", 10)
    for it in items:
        line = f"[{it['type']}] {it['description']}  x{it['qty']}  birim:{it['unit_price']}  KDV:{int(float(it['vat_rate'])*100)}%"
        wrapped = simpleSplit(line, 'Helvetica', 10, 170*mm)
        for w in wrapped:
            text(20*mm, y, w)
            y -= 5*mm
        y -= 2*mm
        if y < 20*mm:
            c.showPage(); y = 280*mm

    c.showPage()
    c.save()