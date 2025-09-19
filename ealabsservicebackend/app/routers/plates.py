from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import update
from datetime import date
from ..deps import get_db
from .. import models, schemas
from ..utils import norm_plate

router = APIRouter(prefix="/plates", tags=["plates"])

@router.post("", response_model=schemas.PlateRead)
def add_plate(payload: schemas.PlateCreate, db: Session = Depends(get_db)):
    # Eski aktif plakayı kapat
    db.query(models.Plate).filter(
        models.Plate.vehicle_id == payload.vehicle_id,
        models.Plate.valid_to.is_(None)
    ).update({models.Plate.valid_to: date.today()})

    obj = models.Plate(
        vehicle_id=payload.vehicle_id,
        plate_normalized=norm_plate(payload.plate)
    )
    db.add(obj)
    db.commit(); db.refresh(obj)
    return obj