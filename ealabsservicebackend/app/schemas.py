from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional, List

# ---- Customers
class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None  # NEW
    type: Optional[str] = "individual"

class CustomerRead(CustomerCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)

# ---- Vehicles
class VehicleCreate(BaseModel):
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    notes: Optional[str] = None

class PlateRead(BaseModel):
    id: str
    plate_normalized: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class VehicleRead(VehicleCreate):
    id: str
    plates: List[PlateRead] = []
    model_config = ConfigDict(from_attributes=True)

class PlateCreate(BaseModel):
    vehicle_id: str
    plate: str

# ---- Service Orders & Items
class ServiceItemCreate(BaseModel):
    type: str  # labor|part
    description: str
    qty: float = 1.0
    unit_price: float = 0.0
    vat_rate: float = 0.20

class ServiceItemRead(ServiceItemCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)

class ServiceOrderCreate(BaseModel):
    vehicle_id: str
    customer_id: str
    odometer_km: int
    status: str = "open"
    notes: Optional[str] = None

class ServiceOrderRead(BaseModel):
    id: str
    vehicle_id: str
    customer_id: str
    opened_at: str
    closed_at: Optional[str] = None
    odometer_km: Optional[int] = None
    status: str
    notes: Optional[str] = None
    items: List[ServiceItemRead] = []
    model_config = ConfigDict(from_attributes=True)

class VehicleDetail(VehicleRead):
    service_orders: List[ServiceOrderRead] = []

class FileRead(BaseModel):
    id: str
    path: str
    kind: str
    status: str
    model_config = ConfigDict(from_attributes=True)

# ---- Smart (prefill + quick order)
class QuickOrderCustomer(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None

class QuickOrderVehicle(BaseModel):
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None

class QuickOrderPayload(BaseModel):
    customer: QuickOrderCustomer
    plate: str
    vehicle: QuickOrderVehicle = QuickOrderVehicle()
    odometer_km: int
    notes: Optional[str] = None

class QuickOrderResponse(BaseModel):
    service_order: ServiceOrderRead
    vehicle: VehicleRead
    customer: CustomerRead

class PrefillByPlateResponse(BaseModel):
    vehicle: Optional[VehicleRead] = None
    last_customer: Optional[CustomerRead] = None

class ItemsBulkPayload(BaseModel):
    items: List[ServiceItemCreate]

class CreateUserIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    roles: List[str]   # ["STAFF"] veya ["AI_DIRECTOR"], vs.

class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    roles: List[str]   # roller listesi

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginIn(BaseModel):
    email: EmailStr
    password: str