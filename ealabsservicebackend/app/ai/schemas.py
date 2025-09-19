# app/ai/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

class CustomerGuess(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    confidence: float = 0.0

class VehicleGuess(BaseModel):
    plate: Optional[str] = None
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    km: Optional[int] = None
    confidence: float = 0.0

class OrderItemGuess(BaseModel):
    type: str = Field(default="labor", description="labor|part")
    name: str
    qty: float = 1
    unit_price: float = 0.0
    confidence: float = 0.5

class ExtractResult(BaseModel):
    customer: CustomerGuess
    vehicle: VehicleGuess
    complaint: Optional[str] = None
    items: List[OrderItemGuess] = []
    currency: Optional[str] = "TRY"
    subtotal: Optional[float] = None
    vat: Optional[float] = None
    total: Optional[float] = None
    low_confidence_fields: List[str] = []

class ExtractResponse(BaseModel):
    result: ExtractResult
    raw_text: str

class ApproveRequest(BaseModel):
    # Onaylanmış payload; şimdilik DB’ye yazmıyoruz, sadece normalleştirilmiş veri döner.
    result: ExtractResult
