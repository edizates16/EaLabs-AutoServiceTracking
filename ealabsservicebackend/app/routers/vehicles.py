# app/routers/vehicles.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.deps import get_db
from app.models import Vehicle, Customer, Plate, Ownership, ServiceOrder

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


# ---- Frontend'in beklediği düz cevap şeması ----
class VehicleByPlateResponse(BaseModel):
    plate: str
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    km: Optional[int] = None
    customerName: Optional[str] = None
    customerEmail: Optional[str] = None
    customerPhone: Optional[str] = None

    class Config:
        from_attributes = True


def normalize_plate_for_lookup(plate: str) -> str:
    """
    Plate.plate_normalized ile eşleşmesi için:
    - Büyük harfe çevir
    - Harf/rakam dışındaki karakterleri kaldır (boşluk, -, . vs.)
    """
    p = (plate or "").strip().upper()
    return "".join(ch for ch in p if ch.isalnum())


@router.get("/by-plate/{plate}", response_model=VehicleByPlateResponse)
def get_by_plate(plate: str, db: Session = Depends(get_db)):
    """
    Plakadan aracı ve (varsa) güncel müşterisini döndürür.
    Ayrıca son iş emrinden km bilgisini de ekler.
    Dönen alanlar frontend'e FLAT şekilde gider (customerName, ...).
    """
    if not plate:
        raise HTTPException(status_code=400, detail="Plaka gerekli")

    norm = normalize_plate_for_lookup(plate)

    # En güncel plate kaydını bul (valid_to IS NULL öncelik; sonra valid_from'a göre en yeni)
    plate_row: Optional[Plate] = (
        db.query(Plate)
        .filter(Plate.plate_normalized == norm)
        .order_by(Plate.valid_to.is_(None).desc(), desc(Plate.valid_from))
        .first()
    )
    if not plate_row:
        raise HTTPException(status_code=404, detail="Araç bulunamadı")

    vehicle: Optional[Vehicle] = plate_row.vehicle
    if not vehicle:
        raise HTTPException(status_code=404, detail="Araç bilgisi eksik")

    # Güncel (veya en son) sahipliği bul
    ownership: Optional[Ownership] = (
        db.query(Ownership)
        .filter(Ownership.vehicle_id == vehicle.id)
        .order_by(Ownership.to_date.is_(None).desc(), desc(Ownership.from_date))
        .first()
    )
    customer: Optional[Customer] = ownership.customer if ownership else None

    # Son servis emrinden km (varsa)
    last_order: Optional[ServiceOrder] = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.vehicle_id == vehicle.id)
        .order_by(
            ServiceOrder.closed_at.is_(None).desc(),
            desc(ServiceOrder.closed_at),
            desc(ServiceOrder.opened_at),
        )
        .first()
    )
    last_km = last_order.odometer_km if last_order and last_order.odometer_km is not None else None

    # Frontend'in beklediği FLAT cevap
    return VehicleByPlateResponse(
        plate=plate.upper(),
        brand=vehicle.brand,
        model=vehicle.model,
        year=vehicle.year,
        km=last_km,
        customerName=(customer.name if customer else None),
        customerEmail=(customer.email if customer else None),
        customerPhone=(customer.phone if customer else None),
    )
