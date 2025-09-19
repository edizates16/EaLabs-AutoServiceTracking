from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_db
from .. import models
from ..utils import norm_plate

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/plate/{plate}")
def search_plate(plate: str, db: Session = Depends(get_db)):
    p = norm_plate(plate)
    active = db.query(models.Plate).filter(
        models.Plate.plate_normalized == p,
        models.Plate.valid_to.is_(None)
    ).order_by(models.Plate.valid_from.desc()).first()
    if not active:
        raise HTTPException(404, "Bu plakaya ait aktif araç bulunamadı")
    return {"vehicle_id": active.vehicle_id}