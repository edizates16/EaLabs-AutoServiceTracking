from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..deps import get_db
from .. import models, schemas

router = APIRouter(prefix="/service-orders", tags=["service_orders"])

@router.post("", response_model=schemas.ServiceOrderRead)
def create_order(payload: schemas.ServiceOrderCreate, db: Session = Depends(get_db)):
    v = db.query(models.Vehicle).filter(models.Vehicle.id == payload.vehicle_id).first()
    c = db.query(models.Customer).filter(models.Customer.id == payload.customer_id).first()
    if not v or not c:
        raise HTTPException(400, "Araç veya müşteri geçersiz")
    obj = models.ServiceOrder(**payload.model_dump())
    db.add(obj)
    db.commit(); db.refresh(obj)
    return obj

@router.get("/{order_id}", response_model=schemas.ServiceOrderRead)
def get_order(order_id: str, db: Session = Depends(get_db)):
    o = db.query(models.ServiceOrder).filter(models.ServiceOrder.id == order_id).first()
    if not o:
        raise HTTPException(404, "İş emri bulunamadı")
    return o

@router.get("/{order_id}/items", response_model=List[schemas.ServiceItemRead])
def list_items(order_id: str, db: Session = Depends(get_db)):
    o = db.query(models.ServiceOrder).filter(models.ServiceOrder.id == order_id).first()
    if not o:
        raise HTTPException(404, "İş emri bulunamadı")
    return o.items

@router.post("/{order_id}/items", response_model=schemas.ServiceItemRead)
def add_item(order_id: str, item: schemas.ServiceItemCreate, db: Session = Depends(get_db)):
    o = db.query(models.ServiceOrder).filter(models.ServiceOrder.id == order_id).first()
    if not o:
        raise HTTPException(404, "İş emri bulunamadı")
    it = models.ServiceItem(service_order_id=order_id, **item.model_dump())
    db.add(it)
    db.commit(); db.refresh(it)
    return it

@router.put("/{order_id}/items-bulk", response_model=List[schemas.ServiceItemRead])
def replace_items(order_id: str, payload: schemas.ItemsBulkPayload, db: Session = Depends(get_db)):
    o = db.query(models.ServiceOrder).filter(models.ServiceOrder.id == order_id).first()
    if not o:
        raise HTTPException(404, "İş emri bulunamadı")

    # mevcutları sil
    db.query(models.ServiceItem).filter(models.ServiceItem.service_order_id == order_id).delete()
    db.flush()

    # yenilerini ekle
    created = []
    for it in payload.items:
        row = models.ServiceItem(service_order_id=order_id, **it.model_dump())
        db.add(row); db.flush(); created.append(row)

    db.commit()
    # taze nesneleri tekrar yükleyelim
    return db.query(models.ServiceItem).filter(models.ServiceItem.service_order_id == order_id).all()