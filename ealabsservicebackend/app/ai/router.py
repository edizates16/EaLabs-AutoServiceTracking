# app/ai/router.py
from fastapi import APIRouter, UploadFile, File
from typing import List
from .schemas import ExtractResponse, ApproveRequest
from .service import extract_from_images

router = APIRouter(prefix="/ai", tags=["AI"])

@router.post("/extract", response_model=ExtractResponse)
async def extract(files: List[UploadFile] = File(...)):
    # accept: image/*, application/pdf (pdf ileride)
    result, raw_text = extract_from_images(files)
    return {"result": result, "raw_text": raw_text}

@router.post("/approve")
async def approve(payload: ApproveRequest):
    # Şimdilik DB’ye yazmıyoruz. İlerde: orders, order_items oluştur.
    # Şu an yalnızca onaylı veriyi geri döndürelim.
    return {"status": "ok", "normalized": payload.result}
