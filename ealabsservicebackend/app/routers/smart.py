from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from ..deps import get_db, require_roles
from .. import models, schemas
from ..utils import norm_plate

router = APIRouter(
    prefix="/smart",
    tags=["smart"],
    dependencies=[Depends(require_roles(["AI_DIRECTOR","OWNER"]))]
)


@router.get("/prefill-by-plate/{plate}", response_model=schemas.PrefillByPlateResponse)
def prefill_by_plate(plate: str, db: Session = Depends(get_db)):
    p = norm_plate(plate)
    active = db.query(models.Plate).filter(
        models.Plate.plate_normalized == p,
        models.Plate.valid_to.is_(None)
    ).order_by(models.Plate.valid_from.desc()).first()

    if not active:
        return {"vehicle": None, "last_customer": None}

    vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == active.vehicle_id).first()

    last_order = (
        db.query(models.ServiceOrder)
        .filter(models.ServiceOrder.vehicle_id == vehicle.id)
        .order_by(models.ServiceOrder.opened_at.desc())
        .first()
    )
    last_customer = None
    if last_order:
        last_customer = db.query(models.Customer).filter(models.Customer.id == last_order.customer_id).first()

    return {"vehicle": vehicle, "last_customer": last_customer}

@router.get("/find-customer", response_model=list[schemas.CustomerRead])
def find_customer(q: str = Query(..., min_length=2), db: Session = Depends(get_db)):
    # Basit, case-insensitive LIKE
    return (
        db.query(models.Customer)
        .filter(func.lower(models.Customer.name).like(f"%{q.lower()}%"))
        .order_by(models.Customer.created_at.desc())
        .limit(20).all()
    )

@router.post("/quick-order", response_model=schemas.QuickOrderResponse)
def quick_order(payload: schemas.QuickOrderPayload, db: Session = Depends(get_db)):
    # 1) Customer upsert (ismi birebir eşleşiyorsa onu güncelle)
    cust = (
        db.query(models.Customer)
        .filter(func.lower(models.Customer.name) == payload.customer.name.lower())
        .first()
    )
    if not cust:
        cust = models.Customer(
            name=payload.customer.name,
            phone=payload.customer.phone,
            email=payload.customer.email,
        )
        db.add(cust); db.flush()
    else:
        # geldi ise bilgileri güncelle (varsa)
        if payload.customer.phone: cust.phone = payload.customer.phone
        if payload.customer.email: cust.email = payload.customer.email

    # 2) Vehicle + Plate
    p = norm_plate(payload.plate)
    active = db.query(models.Plate).filter(
        models.Plate.plate_normalized == p,
        models.Plate.valid_to.is_(None)
    ).order_by(models.Plate.valid_from.desc()).first()

    if active:
        vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == active.vehicle_id).first()
        # marka/model/yıl boşsa gelen verilerle doldur
        vdata = payload.vehicle
        if vdata.brand and not vehicle.brand: vehicle.brand = vdata.brand
        if vdata.model and not vehicle.model: vehicle.model = vdata.model
        if vdata.year and not vehicle.year: vehicle.year = vdata.year
    else:
        # yeni araç oluştur + aktif plaka ata
        vdata = payload.vehicle
        vehicle = models.Vehicle(
            vin=vdata.vin, brand=vdata.brand, model=vdata.model, year=vdata.year
        )
        db.add(vehicle); db.flush()

        # eski aktif plaka kapatma bu araç için gereksiz (yeni araç)
        plate = models.Plate(vehicle_id=vehicle.id, plate_normalized=p)
        db.add(plate)

    # 3) İş emri oluştur
    order = models.ServiceOrder(
        vehicle_id=vehicle.id,
        customer_id=cust.id,
        odometer_km=payload.odometer_km,
        notes=payload.notes,
        status="open",
        source="manual",
    )
    db.add(order)
    db.commit()
    db.refresh(order); db.refresh(vehicle); db.refresh(cust)

    # Pydantic response_model dönüş
    return {
        "service_order": order,
        "vehicle": vehicle,
        "customer": cust
    }