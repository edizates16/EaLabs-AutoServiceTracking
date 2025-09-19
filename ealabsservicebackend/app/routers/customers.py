from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..deps import get_db
from .. import models, schemas

router = APIRouter(prefix="/customers", tags=["customers"])

@router.post("", response_model=schemas.CustomerRead)
def create_customer(payload: schemas.CustomerCreate, db: Session = Depends(get_db)):
    obj = models.Customer(**payload.model_dump())
    db.add(obj)
    db.commit(); db.refresh(obj)
    return obj

@router.get("", response_model=List[schemas.CustomerRead])
def list_customers(db: Session = Depends(get_db)):
    return db.query(models.Customer).order_by(models.Customer.created_at.desc()).all()