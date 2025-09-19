import os
from fastapi import APIRouter, Depends, UploadFile, File as F
from sqlalchemy.orm import Session
from ..deps import get_db
from .. import models, schemas

UPLOAD_DIR = "uploads"

router = APIRouter(prefix="/files", tags=["files"])

@router.post("")
async def upload_file(file: UploadFile = F(...), db: Session = Depends(get_db)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(UPLOAD_DIR, file.filename)
    with open(dest, "wb") as out:
        out.write(await file.read())
    obj = models.File(path=dest, kind="scan", status="raw")
    db.add(obj); db.commit(); db.refresh(obj)
    return {"id": obj.id, "path": obj.path}